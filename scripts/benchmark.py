#!/usr/bin/env python3
"""Mesure le temps de synthèse (avant lecture) pour les deux modes,
afin de vérifier que la latence reste acceptable sur le Raspberry Pi 3."""
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIPER_BIN = ROOT / "piper" / "piper"
MODELS = {
    "fast": ROOT / "models" / "fr_FR-siwis-low.onnx",
    "read": ROOT / "models" / "fr_FR-siwis-medium.onnx",
}
SAMPLES = {
    "fast": "Il fait beau aujourd'hui.",
    "read": (
        "Voici un texte plus long pour tester la latence de lecture en pipeline. "
        "Chaque phrase est synthétisée puis jouée pendant que la suivante se prépare."
    ),
}


def bench(mode: str) -> None:
    model = MODELS[mode]
    if not model.exists():
        print(f"[{mode}] modèle manquant: {model} (lance install.sh)")
        return

    text = SAMPLES[mode]
    out = Path(f"/tmp/bench_{mode}.wav")
    start = time.monotonic()
    subprocess.run(
        [str(PIPER_BIN), "--model", str(model), "--output_file", str(out)],
        input=text.encode("utf-8"),
        check=True,
        stderr=subprocess.DEVNULL,
    )
    elapsed = time.monotonic() - start
    print(f"[{mode}] temps de synthèse: {elapsed:.2f}s -> {out}")


if __name__ == "__main__":
    for mode in ("fast", "read"):
        bench(mode)
