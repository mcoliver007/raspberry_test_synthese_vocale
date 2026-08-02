#!/usr/bin/env bash
# Installe le serveur TTS comme service systemd --user : démarrage
# automatique à la connexion/boot, redémarrage auto en cas de plantage.
#
# On utilise un service --user (et non un service système classique) car
# la sortie audio passe par PulseAudio dans la session de l'utilisateur
# (nécessaire pour l'enceinte Bluetooth A2DP) : un service système lancé
# en root n'y aurait pas accès.
#
# Le fichier .service reste dans le dépôt (pas de copie) : on utilise
# `systemctl --user link`, qui crée un symlink vers ce fichier. Un
# `git pull` qui modifie systemd/piper-tts.service est donc pris en compte
# au prochain `systemctl --user daemon-reload`, sans réinstallation.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_NAME="piper-tts.service"
UNIT_PATH="$ROOT_DIR/systemd/$UNIT_NAME"

echo "Device audio configuré dans le fichier : $(grep '^Environment=TTS_AUDIO_DEVICE=' "$UNIT_PATH")"
echo "Pour changer, édite $UNIT_PATH avant de continuer (Ctrl+C pour annuler)."

systemctl --user link "$UNIT_PATH"
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
