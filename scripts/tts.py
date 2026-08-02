#!/usr/bin/env python3
"""Client léger pour le serveur TTS persistant (voir tts_server.py).

Nécessite que le serveur soit lancé :
    python3 scripts/tts_server.py &

Usage :
    echo "Bonjour" | python3 scripts/tts.py fast
    python3 scripts/tts.py read < texte_long.txt
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys

SOCKET_PATH = os.environ.get("TTS_SOCKET_PATH", "/tmp/piper_tts.sock")


def request(mode: str, text: str) -> dict:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(SOCKET_PATH)
            sock.sendall((json.dumps({"mode": mode, "text": text}) + "\n").encode("utf-8"))
            raw = sock.makefile("r").readline()
    except (FileNotFoundError, ConnectionRefusedError):
        print(
            "Le serveur TTS n'est pas démarré. Lance-le d'abord :\n"
            "  python3 scripts/tts_server.py &",
            file=sys.stderr,
        )
        sys.exit(1)

    return json.loads(raw) if raw else {"status": "error", "error": "réponse vide"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Client TTS (mode rapide ou lecture) - nécessite tts_server.py lancé"
    )
    parser.add_argument("mode", choices=["fast", "read"])
    parser.add_argument("text", nargs="?", help="Texte à synthétiser (sinon lu sur stdin)")
    args = parser.parse_args()

    text = args.text if args.text else sys.stdin.read()
    if not text.strip():
        print("Aucun texte fourni.", file=sys.stderr)
        sys.exit(1)

    resp = request(args.mode, text)
    if resp.get("status") != "ok":
        print(f"Erreur de synthèse: {resp.get('error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
