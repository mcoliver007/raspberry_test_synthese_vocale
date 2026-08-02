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
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIPER_BIN = ROOT / "piper" / "piper"
MODELS = {
    "fast": ROOT / "models" / "fr_FR-siwis-low.onnx",
    "read": ROOT / "models" / "fr_FR-siwis-medium.onnx",
}
SOCKET_PATH = os.environ.get("TTS_SOCKET_PATH", "/tmp/piper_tts.sock")
AUDIO_DEVICE = os.environ.get("TTS_AUDIO_DEVICE", "default")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

WORKERS: dict[str, "PiperWorker"] = {}
PLAY_LOCK = threading.Lock()


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


def _play_bg(wav_path: Path) -> None:
    def run() -> None:
        with PLAY_LOCK:
            try:
                subprocess.run(
                    ["aplay", "-q", "-D", AUDIO_DEVICE, str(wav_path)], check=True
                )
            finally:
                wav_path.unlink(missing_ok=True)

    threading.Thread(target=run, daemon=True).start()


def speak_fast(text: str) -> float:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out = Path(f.name)
    start = time.monotonic()
    WORKERS["fast"].synth(text, out)
    elapsed = time.monotonic() - start
    _play_bg(out)
    return elapsed


def speak_read(text: str) -> float:
    sentences = [s.strip() for s in SENTENCE_RE.split(text.strip()) if s.strip()]
    if not sentences:
        return 0.0

    first_elapsed = 0.0
    for i, sentence in enumerate(sentences):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            out = Path(f.name)
        start = time.monotonic()
        WORKERS["read"].synth(sentence, out)
        elapsed = time.monotonic() - start
        if i == 0:
            first_elapsed = elapsed
        # La lecture se fait en tâche de fond (file d'attente via PLAY_LOCK),
        # donc la synthèse de la phrase suivante démarre sans attendre la fin
        # de la lecture de la phrase courante : c'est le pipeline.
        _play_bg(out)
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
    for mode, model_path in MODELS.items():
        if not model_path.exists():
            raise SystemExit(f"Modèle manquant: {model_path} (lance install.sh)")
        print(f"Chargement du modèle {mode}: {model_path.name}...")
        WORKERS[mode] = PiperWorker(model_path)

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
        if os.path.exists(SOCKET_PATH):
            os.remove(SOCKET_PATH)


if __name__ == "__main__":
    main()
