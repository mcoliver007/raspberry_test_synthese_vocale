#!/usr/bin/env python3
"""Mesure la latence de synthèse (temps avant le début du son) via le
serveur TTS persistant.

Nécessite que le serveur soit lancé :
    python3 scripts/tts_server.py &
"""
from __future__ import annotations

import json
import os
import socket
import sys

SOCKET_PATH = os.environ.get("TTS_SOCKET_PATH", "/tmp/piper_tts.sock")
SAMPLES = {
    "fast": "Il fait beau aujourd'hui.",
    "read": (
        "Voici un texte plus long pour tester la latence de lecture en pipeline. "
        "Chaque phrase est synthétisée puis jouée pendant que la suivante se prépare."
    ),
}


def request(mode: str, text: str) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(SOCKET_PATH)
        sock.sendall((json.dumps({"mode": mode, "text": text}) + "\n").encode("utf-8"))
        raw = sock.makefile("r").readline()
    return json.loads(raw)


def main() -> None:
    try:
        for mode in ("fast", "read"):
            request(mode, ".")  # requête de chauffe, hors mesure
            resp = request(mode, SAMPLES[mode])
            if resp.get("status") != "ok":
                print(f"[{mode}] erreur: {resp.get('error')}")
                continue
            print(f"[{mode}] latence avant le son (modèle chaud): {resp['synth_seconds']}s")
    except (FileNotFoundError, ConnectionRefusedError):
        print(
            "Le serveur TTS n'est pas démarré. Lance-le d'abord :\n"
            "  python3 scripts/tts_server.py &",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
