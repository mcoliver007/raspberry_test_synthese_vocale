#!/usr/bin/env bash
# Installe Piper TTS (binaire ARMv7) et télécharge les voix françaises
# utilisées par ce projet (mode rapide + mode lecture).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPER_VERSION="2023.11.14-2"
PIPER_ARCHIVE="piper_linux_armv7l.tar.gz"
PIPER_URL="https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/${PIPER_ARCHIVE}"
VOICES_INDEX_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/voices.json"

VOICES=(
  "fr_FR-siwis-low"
  "fr_FR-siwis-medium"
)

echo "== Installation de Piper TTS (${PIPER_VERSION}, armv7l) =="

mkdir -p "$ROOT_DIR/models"

if [ ! -x "$ROOT_DIR/piper/piper" ]; then
  echo "Téléchargement du binaire Piper..."
  curl -L -o /tmp/piper.tar.gz "$PIPER_URL"
  tar -xzf /tmp/piper.tar.gz -C "$ROOT_DIR"
  rm -f /tmp/piper.tar.gz
else
  echo "Piper déjà installé, on passe."
fi

echo "Récupération de l'index des voix (voices.json)..."
curl -sL -o /tmp/voices.json "$VOICES_INDEX_URL"

for voice in "${VOICES[@]}"; do
  echo "-- Voix: $voice --"
  python3 "$ROOT_DIR/scripts/download_voice.py" "$voice" /tmp/voices.json "$ROOT_DIR/models"
done

rm -f /tmp/voices.json

echo
echo "Installation terminée."
echo
echo "1) Vérifie les sorties audio disponibles :"
echo "     aplay -L"
echo "   Si tu utilises une enceinte Bluetooth déjà appairée (bluealsa ou PulseAudio),"
echo "   indique le device correspondant via la variable TTS_AUDIO_DEVICE, ex:"
echo "     export TTS_AUDIO_DEVICE=bluealsa"
echo
echo "2) Démarre le serveur TTS (garde les modèles chargés, une seule fois) :"
echo "     python3 scripts/tts_server.py &"
echo
echo "3) Teste les deux modes :"
echo "     echo 'Bonjour, ceci est un test.' | python3 scripts/tts.py fast"
echo "     python3 scripts/tts.py read < exemple_texte_long.txt"
echo
echo "4) Compare les latences :"
echo "     python3 scripts/benchmark.py"
