#!/usr/bin/env python3
"""Télécharge les fichiers d'une voix Piper à partir de l'index voices.json
de https://huggingface.co/rhasspy/piper-voices.
"""
import json
import sys
import urllib.request
from pathlib import Path

BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"


def main():
    if len(sys.argv) != 4:
        sys.exit(f"Usage: {sys.argv[0]} <voice_key> <voices_index.json> <dest_dir>")

    voice_key, index_path, dest_dir = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    dest_dir.mkdir(parents=True, exist_ok=True)

    with open(index_path, encoding="utf-8") as f:
        voices = json.load(f)

    if voice_key not in voices:
        sys.exit(f"Voix inconnue dans l'index: {voice_key}")

    for rel_path in voices[voice_key]["files"]:
        filename = Path(rel_path).name
        dest = dest_dir / filename
        if dest.exists():
            print(f"  {filename} déjà présent")
            continue
        url = BASE_URL + rel_path
        print(f"  Téléchargement {filename}...")
        urllib.request.urlretrieve(url, dest)


if __name__ == "__main__":
    main()
