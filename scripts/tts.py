#!/usr/bin/env python3
"""Wrapper CLI autour de Piper TTS avec deux stratégies :

- mode "fast" : réponse courte (Q/R), voix légère, latence minimale.
- mode "read" : texte plus long, voix de meilleure qualité, découpé en
  phrases et joué en pipeline (synthèse de la phrase suivante pendant
  la lecture de la précédente) pour garder <2s avant le début du son.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
PIPER_BIN = ROOT / "piper" / "piper"
MODELS = {
    "fast": ROOT / "models" / "fr_FR-siwis-low.onnx",
    "read": ROOT / "models" / "fr_FR-siwis-medium.onnx",
}
AUDIO_DEVICE = os.environ.get("TTS_AUDIO_DEVICE", "default")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def synth_to_file(text: str, model_path: Path, out_path: Path) -> None:
    subprocess.run(
        [str(PIPER_BIN), "--model", str(model_path), "--output_file", str(out_path)],
        input=text.encode("utf-8"),
        check=True,
        stderr=subprocess.DEVNULL,
    )


def play(wav_path: Path) -> None:
    subprocess.run(["aplay", "-q", "-D", AUDIO_DEVICE, str(wav_path)], check=True)


def speak_fast(text: str) -> None:
    model = MODELS["fast"]
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out = Path(f.name)
    try:
        synth_to_file(text, model, out)
        play(out)
    finally:
        out.unlink(missing_ok=True)


def speak_read(text: str) -> None:
    model = MODELS["read"]
    sentences = [s.strip() for s in SENTENCE_RE.split(text.strip()) if s.strip()]
    if not sentences:
        return

    files: List[Optional[Path]] = [None] * len(sentences)
    ready = [threading.Event() for _ in sentences]

    def synth_all() -> None:
        for i, sentence in enumerate(sentences):
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                out = Path(f.name)
            synth_to_file(sentence, model, out)
            files[i] = out
            ready[i].set()

    worker = threading.Thread(target=synth_all, daemon=True)
    worker.start()
    try:
        for i in range(len(sentences)):
            ready[i].wait()
            play(files[i])
    finally:
        for f in files:
            if f:
                f.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Synthèse vocale offline (Piper) - mode rapide ou lecture"
    )
    parser.add_argument("mode", choices=["fast", "read"])
    parser.add_argument("text", nargs="?", help="Texte à synthétiser (sinon lu sur stdin)")
    args = parser.parse_args()

    text = args.text if args.text else sys.stdin.read()
    if not text.strip():
        print("Aucun texte fourni.", file=sys.stderr)
        sys.exit(1)

    model_path = MODELS[args.mode]
    if not model_path.exists():
        print(f"Modèle manquant: {model_path}. Lance install.sh d'abord.", file=sys.stderr)
        sys.exit(1)

    if args.mode == "fast":
        speak_fast(text)
    else:
        speak_read(text)


if __name__ == "__main__":
    main()
