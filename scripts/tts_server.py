#!/usr/bin/env python3
"""Serveur TTS persistant.

Garde les deux modèles Piper chargés en mémoire en permanence (au lieu de
relancer un processus Piper - et donc de recharger le modèle - à chaque
phrase). C'est le rechargement répété qui causait la latence de plusieurs
secondes observée en mode "fast".

Démarrage :
    python3 scripts/tts_server.py &

Le client `tts.py` communique avec ce serveur via un socket Unix.
"""
from __future__ import annotations

import json
import os
import re
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIPER_BIN = ROOT / "piper" / "piper"
# La voix "medium" (fr_FR-siwis-medium) synthétise ~2x plus lentement que le
# temps réel sur un Pi 3 (mesuré: ~0.75s/mot pour ~0.4s d'audio produit).
# Elle ne peut donc pas alimenter un flux de lecture en continu sans
# coupures (underruns) : les deux modes utilisent la voix "low", proche du
# temps réel. Le modèle medium reste téléchargé par install.sh pour des
# comparaisons manuelles de qualité (voir README).
MODELS = {
    "fast": ROOT / "models" / "fr_FR-siwis-low.onnx",
    "read": ROOT / "models" / "fr_FR-siwis-low.onnx",
}
SOCKET_PATH = os.environ.get("TTS_SOCKET_PATH", "/tmp/piper_tts.sock")
# Phrase d'accroche jouée en tout début de mode "read" : synthétisée une
# seule fois au démarrage du serveur et mise en cache, elle se joue quasi
# instantanément à chaque requête. Ça donne un retour audio immédiat à
# l'utilisateur (il sait qu'une réponse arrive) et gagne ~1-1.5s de marge
# pendant lesquelles le vrai contenu continue de se synthétiser.
INTRO_TEXT = os.environ.get("TTS_INTRO_TEXT", "Voici ma réponse :")
INTRO_PCM: bytes = b""
CLAUSE_BREAK_WORDS = [
    "afin de", "afin qu'", "afin que", "parce que", "puisque",
    "pendant que", "alors que", "bien que", "tandis que", "de sorte que",
    "car", "mais", "donc", "cependant", "toutefois", "quand", "lorsque",
    "lorsqu'",
]
_CONJ_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in CLAUSE_BREAK_WORDS) + r")\b",
    re.IGNORECASE,
)
AUDIO_DEVICE = os.environ.get("TTS_AUDIO_DEVICE", "default")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

WORKERS: dict[str, "PiperWorker"] = {}
PLAYERS: dict[str, "RawPlayer"] = {}
# Un seul verrou global : même avec un player par voix, on ne veut jamais
# deux phrases jouées en même temps (ordre + pas de son superposé).
PLAY_LOCK = threading.Lock()


def _sample_rate(model_path: Path) -> int:
    config_path = Path(str(model_path) + ".json")
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    return config["audio"]["sample_rate"]


class RawPlayer:
    """Processus aplay unique et persistant par voix : on lui écrit du PCM
    brut en continu au lieu de relancer aplay à chaque phrase. Ça évite que
    la liaison Bluetooth A2DP se remette en veille (SUSPENDED) entre deux
    phrases, ce qui causait le silence audible entre chaque segment lu."""

    def __init__(self, device: str, sample_rate: int, channels: int = 1):
        self.proc = subprocess.Popen(
            [
                "aplay", "-q", "-D", device,
                "-f", "S16_LE", "-r", str(sample_rate), "-c", str(channels),
                "-t", "raw", "-",
            ],
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def _drain_stderr(self) -> None:
        assert self.proc.stderr is not None
        for line in self.proc.stderr:
            sys.stderr.write(f"[aplay] {line.decode('utf-8', 'replace')}")

    def write(self, pcm_data: bytes) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(pcm_data)
        self.proc.stdin.flush()

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except OSError:
            pass
        self.proc.terminate()


class PiperWorker:
    """Un unique processus Piper gardé vivant, piloté via --json-input."""

    def __init__(self, model_path: Path):
        self.proc = subprocess.Popen(
            [str(PIPER_BIN), "--model", str(model_path), "--json-input"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.lock = threading.Lock()

    def synth(self, text: str, out_path: Path, timeout: float = 30.0) -> None:
        with self.lock:
            line = json.dumps({"text": text, "output_file": str(out_path)}) + "\n"
            assert self.proc.stdin is not None
            self.proc.stdin.write(line.encode("utf-8"))
            self.proc.stdin.flush()
            self._wait_ready(out_path, timeout)

    @staticmethod
    def _wait_ready(path: Path, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        last_size = -1
        stable = 0
        while time.monotonic() < deadline:
            if path.exists():
                size = path.stat().st_size
                if size > 44 and size == last_size:
                    stable += 1
                    if stable >= 2:
                        return
                else:
                    stable = 0
                last_size = size
            time.sleep(0.03)
        raise TimeoutError(f"Synthèse trop longue pour {path}")

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except OSError:
            pass
        self.proc.terminate()


def _play_pcm_bg(mode: str, pcm_data: bytes) -> None:
    def run() -> None:
        try:
            with PLAY_LOCK:
                PLAYERS[mode].write(pcm_data)
        except Exception as exc:  # noqa: BLE001 - on log, on ne bloque pas la synthèse
            print(f"[erreur lecture audio] mode={mode}: {exc}", file=sys.stderr)

    threading.Thread(target=run, daemon=True).start()


def _play_bg(mode: str, wav_path: Path) -> None:
    def run() -> None:
        try:
            with wave.open(str(wav_path), "rb") as wf:
                pcm_data = wf.readframes(wf.getnframes())
            with PLAY_LOCK:
                PLAYERS[mode].write(pcm_data)
        except Exception as exc:  # noqa: BLE001 - on log, on ne bloque pas la synthèse
            print(f"[erreur lecture audio] mode={mode}: {exc}", file=sys.stderr)
        finally:
            wav_path.unlink(missing_ok=True)

    threading.Thread(target=run, daemon=True).start()


def speak_fast(text: str) -> float:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out = Path(f.name)
    start = time.monotonic()
    WORKERS["fast"].synth(text, out)
    elapsed = time.monotonic() - start
    _play_bg("fast", out)
    return elapsed


def _split_clauses(sentence: str) -> list[str]:
    """Découpe une phrase uniquement aux points de pause naturels : virgules
    et avant certaines conjonctions de subordination/coordination. Couper à
    un endroit sans raison syntaxique (ex: nombre de mots arbitraire) casse
    la prosodie de Piper et s'entend comme une coupure artificielle."""
    parts = re.split(r"(?<=,)\s+", sentence)
    chunks: list[str] = []
    for part in parts:
        pos = 0
        for m in _CONJ_RE.finditer(part):
            if m.start() > pos:
                chunks.append(part[pos:m.start()].strip())
                pos = m.start()
        chunks.append(part[pos:].strip())
    return [c for c in chunks if c]


def speak_read(text: str) -> float:
    # Découpage aux frontières de phrase, puis aux points de pause naturels
    # à l'intérieur de chaque phrase (virgules, conjonctions). Une pause à
    # un endroit où on respirerait naturellement sonne normale ; une
    # coupure ailleurs sonne cassée.
    chunks: list[str] = []
    for sentence in SENTENCE_RE.split(text.strip()):
        sentence = sentence.strip()
        if sentence:
            chunks.extend(_split_clauses(sentence))
    if not chunks:
        return 0.0

    if INTRO_PCM:
        _play_pcm_bg("read", INTRO_PCM)

    first_elapsed = 0.0
    for i, sentence in enumerate(chunks):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            out = Path(f.name)
        start = time.monotonic()
        WORKERS["read"].synth(sentence, out)
        elapsed = time.monotonic() - start
        with wave.open(str(out), "rb") as wf:
            audio_duration = wf.getnframes() / wf.getframerate()
        ratio = elapsed / audio_duration if audio_duration else float("inf")
        print(
            f"[read] chunk {i} ({len(sentence.split())} mots): "
            f"synth={elapsed:.2f}s audio={audio_duration:.2f}s ratio={ratio:.2f}",
            file=sys.stderr,
        )
        if i == 0:
            first_elapsed = elapsed
        # La lecture se fait en tâche de fond (file d'attente via PLAY_LOCK),
        # donc la synthèse de la phrase suivante démarre sans attendre la fin
        # de la lecture de la phrase courante : c'est le pipeline.
        _play_bg("read", out)
    return first_elapsed


class Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        raw = self.rfile.readline()
        if not raw:
            return
        try:
            req = json.loads(raw.decode("utf-8"))
            mode = req["mode"]
            text = req["text"]
            if mode == "fast":
                elapsed = speak_fast(text)
            elif mode == "read":
                elapsed = speak_read(text)
            else:
                raise ValueError(f"mode inconnu: {mode}")
            resp = {"status": "ok", "synth_seconds": round(elapsed, 3)}
        except Exception as exc:  # noqa: BLE001 - renvoyé tel quel au client
            resp = {"status": "error", "error": str(exc)}
        self.wfile.write((json.dumps(resp) + "\n").encode("utf-8"))


class ThreadingUnixStreamServer(
    socketserver.ThreadingMixIn, socketserver.UnixStreamServer
):
    daemon_threads = True


def main() -> None:
    global INTRO_PCM

    print(f"Sortie audio (TTS_AUDIO_DEVICE): {AUDIO_DEVICE!r}")
    for mode, model_path in MODELS.items():
        if not model_path.exists():
            raise SystemExit(f"Modèle manquant: {model_path} (lance install.sh)")
        print(f"Chargement du modèle {mode}: {model_path.name}...")
        WORKERS[mode] = PiperWorker(model_path)
        PLAYERS[mode] = RawPlayer(AUDIO_DEVICE, _sample_rate(model_path))

    print(f"Préparation de l'intro de lecture: {INTRO_TEXT!r}")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        intro_path = Path(f.name)
    WORKERS["read"].synth(INTRO_TEXT, intro_path)
    with wave.open(str(intro_path), "rb") as wf:
        INTRO_PCM = wf.readframes(wf.getnframes())
    intro_path.unlink(missing_ok=True)

    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)

    server = ThreadingUnixStreamServer(SOCKET_PATH, Handler)
    print(f"Serveur TTS prêt sur {SOCKET_PATH} (Ctrl+C pour arrêter)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for worker in WORKERS.values():
            worker.close()
        for player in PLAYERS.values():
            player.close()
        if os.path.exists(SOCKET_PATH):
            os.remove(SOCKET_PATH)


if __name__ == "__main__":
    main()
