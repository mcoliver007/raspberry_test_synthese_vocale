# raspberry_test_synthese_vocale

Synthèse vocale française **100% offline** sur Raspberry Pi 3 (1 Go RAM),
avec sortie sur enceinte Bluetooth. Moteur retenu : [Piper TTS](https://github.com/rhasspy/piper)
(neuronal, léger, rapide même sur Pi 3).

## Matériel testé

- Raspberry Pi 3 Model B (armv7l, 32-bit), Raspbian 11 Bullseye
- Sortie audio via enceinte Bluetooth appairée et connectée en A2DP,
  routée via PulseAudio (ex: Bose Flex SoundLink)

## Architecture en bref

- **`scripts/tts_server.py`** : serveur persistant qui garde les modèles
  Piper chargés en mémoire et un flux audio ouvert en continu vers
  l'enceinte. À lancer une fois, en arrière-plan.
- **`scripts/tts.py`** : client léger, envoie du texte au serveur via un
  socket Unix (`/tmp/piper_tts.sock`).
- **`scripts/benchmark.py`** : mesure la latence de synthèse des deux modes.
- Deux modes, avec la voix `fr_FR-siwis-low` :

  | Mode | Usage | Comportement |
  |---|---|---|
  | `fast` | réponses courtes (Q/R) | synthèse + lecture directe, quasi instantané (~1-2s) |
  | `read` | lecture de textes plus longs | découpe le texte aux points de pause naturels (fins de phrase, virgules, conjonctions), lit en pipeline (le segment suivant se synthétise pendant que le précédent joue), avec une phrase d'accroche mise en cache pour un retour audio immédiat |

  La voix `fr_FR-siwis-medium` (meilleure qualité mais ~2x plus lente que
  le temps réel sur ce Pi) est téléchargée mais pas utilisée en direct —
  voir [Historique](#historique-du-projet--difficultés-rencontrées) et la
  section [Comparer les voix manuellement](#comparer-les-voix-manuellement).

## Installation

```bash
./install.sh
```

Télécharge le binaire Piper (armv7l, release GitHub officielle) et les
voix françaises `fr_FR-siwis-low` + `fr_FR-siwis-medium` (index
[rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices)) dans
`piper/` et `models/`.

## Utilisation

**1. Vérifier la sortie audio disponible**

```bash
aplay -L
pactl list short sinks        # si tu utilises PulseAudio (cas Bluetooth)
pactl info | grep "Default Sink"
```

Repère le nom du sink à utiliser (ex: `pulse` si l'enceinte Bluetooth est
déjà le sink PulseAudio par défaut).

**2. Démarrer le serveur** (une fois, à laisser tourner en arrière-plan)

```bash
export TTS_AUDIO_DEVICE=pulse   # à adapter selon ce que renvoie aplay -L / pactl
python3 scripts/tts_server.py &
```

Le serveur affiche le device utilisé et le chargement des modèles au
démarrage. Le laisser tourner : c'est lui qui garde tout chaud en mémoire.

**3. Utiliser le client**

```bash
echo "Bonjour, ceci est un test." | python3 scripts/tts.py fast

python3 scripts/tts.py read < exemple_texte_long.txt
```

**4. Mesurer les latences**

```bash
python3 scripts/benchmark.py
```

**5. Redémarrer le serveur** (après un `git pull`, un changement de
config, ou si plusieurs instances tournent par erreur)

```bash
pkill -f tts_server.py
export TTS_AUDIO_DEVICE=pulse
python3 scripts/tts_server.py &
```

## Utiliser comme service (pour d'autres programmes sur la Pi)

Pour que d'autres services tournant sur la même Raspberry Pi puissent
utiliser la synthèse vocale (au lieu de lancer `tts_server.py` à la main
dans un terminal), installe-le comme service `systemd --user` :

```bash
./install_service.sh
```

Ça installe `systemd/piper-tts.service` dans `~/.config/systemd/user/`,
démarre le serveur immédiatement, l'active au démarrage (via
`loginctl enable-linger`, pour qu'il tourne même sans session ouverte), et
le relance automatiquement en cas de plantage.

**Un service `--user` plutôt qu'un service système** : la sortie audio
passe par PulseAudio dans la session de l'utilisateur (nécessaire pour
l'enceinte Bluetooth). Un service système classique (lancé en root) n'a
pas accès à cette session audio.

Commandes utiles :

```bash
systemctl --user status piper-tts.service     # état du service
journalctl --user -u piper-tts.service -f     # logs en direct
systemctl --user restart piper-tts.service    # redémarrer (ex: après git pull)
systemctl --user stop piper-tts.service       # arrêter
```

**Comment un autre service se connecte** : le protocole ne change pas, un
programme (Python, Node, script shell...) écrit sur la même machine se
connecte simplement au socket Unix `/tmp/piper_tts.sock` (ou la valeur de
`TTS_SOCKET_PATH`) et envoie une ligne JSON `{"mode": "fast"|"read",
"text": "..."}` — voir `INSTRUCTIONS_IA.md` pour le détail du protocole.
Le socket est accessible à tout processus local, quel que soit le
langage ; il n'y a pas d'API réseau à exposer séparément.

### Comparer les voix manuellement

`fr_FR-siwis-medium` sonne mieux mais ne tient pas le temps réel en
pipeline sur ce Pi. Pour l'écouter sur une phrase courte, hors flux temps
réel :

```bash
echo "Ceci est un test avec la voix medium." | \
  piper/piper --model models/fr_FR-siwis-medium.onnx --output_file /tmp/medium.wav
aplay -D pulse /tmp/medium.wav
```

## Configuration (variables d'environnement)

À définir **avant** de lancer `tts_server.py` (elles sont lues une seule
fois au démarrage) :

| Variable | Défaut | Rôle |
|---|---|---|
| `TTS_AUDIO_DEVICE` | `default` | Device ALSA/PulseAudio de sortie (ex: `pulse`) |
| `TTS_SOCKET_PATH` | `/tmp/piper_tts.sock` | Socket Unix serveur ↔ client |
| `TTS_INTRO_TEXT` | `Voici ma réponse :` | Phrase d'accroche jouée en tête du mode `read` |

## Dépannage

**Le serveur ne charge pas / erreur "Modèle manquant"**
→ Relancer `./install.sh` (voir sa sortie pour une erreur de téléchargement).

**`tts.py` répond "Le serveur TTS n'est pas démarré"**
→ Le serveur n'est pas lancé, ou plusieurs instances se battent pour le
socket. Vérifier / nettoyer :
```bash
ps aux | grep tts_server
pkill -f tts_server.py
python3 scripts/tts_server.py &
```

**Aucun son ne sort**
1. Vérifier que `TTS_AUDIO_DEVICE` était bien exporté **avant** de lancer
   le serveur (son log de démarrage affiche la valeur utilisée).
2. Tester le device directement : `speaker-test -D pulse -c2 -t wav -l1`
3. Vérifier le sink Bluetooth : `pactl list short sinks` (doit lister
   `bluez_sink...`) et `pactl info | grep "Default Sink"`.
4. Regarder les logs du serveur : les erreurs `aplay` (device invalide,
   sink déconnecté...) s'affichent dans son terminal, préfixées
   `[erreur lecture audio]` ou `[aplay]`.

**Coupures / `underrun` pendant la lecture (mode `read`)**
→ Normalement résolu par le découpage aux points de pause naturels et le
flux audio persistant (voir Historique). S'il en reste occasionnellement
sur de longs segments, ce n'est pas bloquant : ça se confond avec une
pause de fin de phrase. Si ça devient gênant, réduire la liste de
conjonctions de découpe dans `tts_server.py` (`CLAUSE_BREAK_WORDS`) pour
des segments plus courts.

**Le service systemd ne joue aucun son (mais fonctionne en lançant `tts_server.py` à la main)**
→ Vérifier que le service tourne bien en `--user` (pas en `sudo systemctl`,
qui l'installerait comme service système sans accès à la session
PulseAudio). Vérifier aussi `loginctl enable-linger $USER` (nécessaire si
le service doit tourner sans session ouverte) et les logs :
`journalctl --user -u piper-tts.service -f`.

**Latence trop élevée en mode `fast`**
→ Vérifier que le serveur est bien resté démarré (chaque relance recharge
les modèles, ~plusieurs secondes) et qu'aucune autre charge CPU ne tourne
en même temps (l'encodage audio Bluetooth (SBC) consomme du CPU sur ce Pi).

## Historique du projet & difficultés rencontrées

Résumé chronologique des blocages et de leurs solutions (le détail des
itérations est dans l'historique git de la branche `feature/piper-tts-poc`).

1. **Choix du moteur** — Piper TTS retenu pour tourner offline sur Pi 3
   32-bit avec une qualité vocale neuronale correcte, contre `espeak-ng`
   (moins naturel) ou des moteurs plus lourds (Coqui XTTS, trop gourmands
   pour 1 Go de RAM).

2. **Latence de ~4s même sur une phrase courte** — Piper rechargeait
   entièrement le modèle (ONNX + espeak-ng) à chaque appel, coût dominant
   sur ce CPU. → **Serveur persistant** (`tts_server.py`) qui garde les
   modèles chargés en mémoire via `--json-input` ; `tts.py` devient un
   client léger qui ne paie plus que le vrai temps de synthèse.

3. **Lectures longues encore lentes à démarrer** — La 1ère phrase entière
   devait être synthétisée avant le premier son. → Découpage en plus
   petits segments pour démarrer plus vite (étape intermédiaire, revue à
   l'étape 6).

4. **Erreurs de lecture invisibles** — La lecture audio tournait en tâche
   de fond sans remonter ses erreurs. → Logs explicites des échecs `aplay`
   côté serveur, utile pour diagnostiquer les problèmes de device.

5. **Silence audible entre chaque phrase** — Un nouveau processus `aplay`
   était relancé à chaque segment, ce qui remettait en veille (SUSPENDED)
   la liaison Bluetooth A2DP à chaque fois. → **Flux audio persistant**
   (`RawPlayer`) : un seul processus `aplay` par voix, gardé ouvert en
   continu, alimenté en PCM brut au fil de la synthèse.

6. **Coupures malgré le flux continu (`underrun`)** — La voix
   `fr_FR-siwis-medium` s'est révélée ~2x plus lente que le temps réel sur
   ce CPU (mesuré via des logs de ratio synthèse/audio ajoutés pour
   diagnostiquer), donc incapable d'alimenter un flux continu quelle que
   soit l'architecture logicielle. → Bascule du mode `read` sur la voix
   `fr_FR-siwis-low` (proche du temps réel), `medium` gardée disponible
   pour des tests manuels hors flux continu.

7. **Coupures encore présentes, cette fois dues à des phrases qui
   s'allongent** — Une tentative de découpage systématique par nombre de
   mots (~8 mots/segment) a bien réduit les `underrun`, mais a introduit
   des coupures **artificielles en plein milieu de groupes de mots**,
   Piper traitant chaque segment comme un énoncé isolé (perte de
   prosodie). → **Découpage aux points de pause naturels uniquement** :
   fins de phrase, virgules, et une liste de conjonctions de
   subordination/coordination courantes (afin de, parce que, pendant
   que, car, mais...), là où une pause sonne normale à l'oreille.

8. **Latence de démarrage encore perceptible en mode `read`** → Ajout
   d'une **phrase d'accroche mise en cache** ("Voici ma réponse :"),
   synthétisée une seule fois au démarrage du serveur et jouée quasi
   instantanément à chaque requête, le temps que le vrai contenu continue
   de se synthétiser en arrière-plan.

**État actuel** : voix jugée satisfaisante, mode `fast` ~1-2s, mode `read`
démarre vite (grâce à l'accroche) et lit sans coupure gênante à l'oreille,
avec un `underrun` technique résiduel occasionnel sur les segments les
plus longs (non perceptible, coïncide avec une pause de fin de phrase).
