# raspberry_test_synthese_vocale

Ce repo permet de tester sur une Raspberry Pi 3 Model B (1 Go RAM), une
synthèse vocale offline pour en juger la qualité sonore.

## Matériel de test

- Raspberry Pi 3 Model B (armv7l, 32-bit), Raspbian 11 Bullseye
- Sortie audio via enceinte Bluetooth déjà appairée (ex: Bose Flex SoundLink)

## Moteur retenu : Piper TTS

[Piper](https://github.com/rhasspy/piper) est un moteur de synthèse vocale
neuronal, 100% offline, léger et rapide même sur Raspberry Pi 3.

Deux voix françaises sont utilisées pour deux stratégies différentes :

| Mode | Voix | Usage | Objectif de latence |
|---|---|---|---|
| `fast` | `fr_FR-siwis-low` | réponses courtes (Q/R) | quasi instantané |
| `read` | `fr_FR-siwis-medium` | lecture de textes plus longs | 1ère phrase jouée en <2s, puis lecture en pipeline |

Le mode `read` découpe le texte en phrases et synthétise la phrase suivante
pendant que la précédente est jouée, ce qui garde une latence perçue faible
même pour un texte long.

## Installation

```bash
./install.sh
```

Ce script :
1. télécharge le binaire Piper (armv7l) depuis les releases GitHub officielles,
2. télécharge les deux voix françaises depuis
   [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices).

Vérifie ensuite les sorties audio disponibles :

```bash
aplay -L
```

Si tu utilises l'enceinte Bluetooth comme sortie (via `bluealsa` ou
PulseAudio), indique le device correspondant :

```bash
export TTS_AUDIO_DEVICE=bluealsa   # ou le nom de sink exact, ex: bluealsa:DEV=XX:XX:XX:XX:XX:XX
```

## Utilisation

Piper met plusieurs secondes à charger un modèle en mémoire sur un Pi 3.
Pour ne pas payer ce coût à chaque phrase, un **serveur persistant** garde
les deux modèles chargés en permanence ; `tts.py` n'est qu'un client léger
qui lui envoie le texte.

Démarrer le serveur (une fois, à laisser tourner en arrière-plan) :

```bash
python3 scripts/tts_server.py &
```

Puis utiliser le client autant de fois que voulu, sans latence de
rechargement :

```bash
echo "Bonjour, ceci est un test." | python3 scripts/tts.py fast

python3 scripts/tts.py read < exemple_texte_long.txt
```

## Comparer les latences

```bash
python3 scripts/benchmark.py
```

Affiche la latence de synthèse (modèle déjà chaud) pour chaque mode, à
comparer aux objectifs (<2s pour `fast`, 1ère phrase de `read` jouée en <2s
puis lecture en pipeline).
