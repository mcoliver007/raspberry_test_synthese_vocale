#!/usr/bin/env bash
# Installe le serveur TTS comme service systemd --user : démarrage
# automatique à la connexion/boot, redémarrage auto en cas de plantage.
#
# On utilise un service --user (et non un service système classique) car
# la sortie audio passe par PulseAudio dans la session de l'utilisateur
# (nécessaire pour l'enceinte Bluetooth A2DP) : un service système lancé
# en root n'y aurait pas accès.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_NAME="piper-tts.service"

mkdir -p "$UNIT_DIR"
cp "$ROOT_DIR/systemd/$UNIT_NAME" "$UNIT_DIR/$UNIT_NAME"

read -rp "Device audio à utiliser (TTS_AUDIO_DEVICE) [pulse]: " device
device=${device:-pulse}
sed -i "s/^Environment=TTS_AUDIO_DEVICE=.*/Environment=TTS_AUDIO_DEVICE=${device}/" "$UNIT_DIR/$UNIT_NAME"

systemctl --user daemon-reload
systemctl --user enable --now "$UNIT_NAME"

# Permet au service de démarrer au boot même sans session graphique/SSH
# ouverte, et de continuer à tourner après une déconnexion.
loginctl enable-linger "$USER"

echo
echo "Service installé et démarré."
echo "Statut :   systemctl --user status $UNIT_NAME"
echo "Logs :     journalctl --user -u $UNIT_NAME -f"
echo "Redémarrer : systemctl --user restart $UNIT_NAME"
echo "Arrêter :  systemctl --user stop $UNIT_NAME"
