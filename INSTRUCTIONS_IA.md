# Instructions pour un modèle IA générant du texte à faire parler

Ce document est destiné à être donné en contexte à un modèle IA (system
prompt ou instructions) qui génère du texte destiné à être synthétisé par
ce serveur vocal Piper TTS. Il couvre : comment appeler le serveur, et
comment écrire un texte qui se synthétise bien sur ce moteur/matériel.

## 1. Comment utiliser le serveur vocal

Le serveur (`scripts/tts_server.py`) doit déjà être lancé et rester actif
en arrière-plan (voir README.md du repo pour le démarrage). Il écoute sur
un socket Unix (`/tmp/piper_tts.sock` par défaut) et accepte une requête
JSON par ligne :

```json
{"mode": "fast", "text": "Bonjour."}
```

Réponse :
```json
{"status": "ok", "synth_seconds": 1.23}
```

**Deux modes, à choisir selon la longueur de la réponse :**

| Mode | Quand l'utiliser | Comportement |
|---|---|---|
| `fast` | Réponse courte : une phrase, une confirmation, une valeur | Synthèse + lecture directe, quasi instantané |
| `read` | Réponse longue : plusieurs phrases, explication, résultat détaillé | Découpe et lit en pipeline avec une phrase d'accroche immédiate ("Voici ma réponse :") pendant que la suite se synthétise |

**Règle simple pour le modèle IA** : si le texte généré tient en une
phrase courte (< ~10 mots), utiliser `fast`. Dès qu'il y a plusieurs
phrases ou une phrase longue, utiliser `read`.

Exemple d'appel en ligne de commande (utile pour tester) :
```bash
echo "Texte à dire" | python3 scripts/tts.py fast
python3 scripts/tts.py read < fichier_texte.txt
```

## 2. Écrire un texte qui se synthétise bien

Le moteur (Piper, voix `fr_FR-siwis-low`) et le pipeline de lecture ont
des contraintes concrètes sur ce Raspberry Pi. Un texte mal structuré peut
sonner robotique, mal se découper, ou provoquer des coupures audio.
Règles à respecter, par ordre d'impact :

### a. Toujours terminer chaque phrase par une ponctuation forte (`.`, `!`, `?`)

Le serveur détecte les frontières de phrase uniquement via cette
ponctuation. Une phrase non terminée casse le découpage : elle peut se
retrouver fusionnée avec la suivante, trop longue à synthétiser d'un bloc,
et provoquer un silence perceptible avant qu'elle ne soit jouée.

### b. Phrases courtes à moyennes (viser 8 à 20 mots)

Le moteur synthétise plus lentement que le temps réel dans certains cas ;
une phrase très longue met plus de temps à être prête qu'il n'en faut pour
la jouer, ce qui peut créer un silence audible avant qu'elle ne démarre.
Préférer plusieurs phrases courtes à une phrase longue avec plusieurs
idées empilées.

### c. Utiliser des virgules aux vraies pauses de respiration, pas pour la décoration

Le pipeline découpe aussi sur les virgules (en plus des fins de phrase)
pour commencer à parler plus tôt. Une virgule placée à un endroit où l'on
marquerait naturellement une pause à l'oral sonnera bien. Une virgule
purement grammaticale/décorative (ex: énumérations très denses) peut
créer une pause qui sonne hachée à l'oral.

- Bien : `"Le trajet dure environ deux heures, selon la circulation."`
- À éviter : `"Le trajet, qui dépend de plusieurs facteurs, dure environ deux heures."` *(incise qui casse le flux)*

### d. Préférer des connecteurs explicites plutôt que des phrases très imbriquées

Le pipeline reconnaît des mots de liaison courants (afin de, parce que,
car, mais, donc, pendant que, quand, lorsque...) comme points de pause
naturels. Une phrase construite avec ces connecteurs, plutôt qu'avec des
propositions imbriquées ou des incises entre virgules, se découpe et se
lit mieux.

- Bien : `"Le service est fermé aujourd'hui, car c'est un jour férié."`
- À éviter : `"Le service, qui est habituellement ouvert, est fermé aujourd'hui, un jour férié."`

### e. Éviter les incises entre parenthèses ou tirets

Le moteur synthétise chaque segment de façon isolée ; une incise
parenthétique casse la prosodie et se détecte mal comme point de pause.
Préférer reformuler en deux phrases séparées.

- Bien : `"Il pleuvra demain. Prévois un parapluie."`
- À éviter : `"Il pleuvra demain (selon les prévisions) donc prévois un parapluie."`

### f. Pas de mise en forme, symboles ou markdown

Le texte est lu tel quel par le moteur de synthèse. Ne jamais inclure :
`**gras**`, `*italique*`, `# titres`, listes à puces (`-`, `*`), blocs de
code, emojis, ou liens. Tout ceci sera soit lu littéralement (mal), soit
ignoré de façon imprévisible. Écrire en prose simple uniquement.

### g. Écrire les nombres et unités de façon naturelle

Préférer une forme que l'espeak-ng (moteur de phonémisation utilisé par
Piper) prononce correctement en français :
- Nombres simples en chiffres : `"23 degrés"` (se lit correctement).
- Éviter les formats ambigus (`"12/03"`, `"3.5k"`) : préférer
  `"le 12 mars"`, `"trois mille cinq cents"` si la précision compte.
- Éviter les abréviations non standard (`"env."`, `"qqch"`) : écrire en
  toutes lettres (`"environ"`, `"quelque chose"`).

### h. Développer les acronymes et sigles à la 1ère occurrence

Un sigle non familier (`"API"`, `"CPU"`) peut être épelé lettre par lettre
de façon peu naturelle. Si le sigle doit être dit, préférer développer :
`"l'interface de programmation"` plutôt que `"l'API"`, sauf s'il s'agit
d'un sigle très courant et déjà lexicalisé à l'oral (`"le PDF"`).

### i. Ne jamais tronquer une phrase avec des points de suspension pour "couper court"

`"..."` en fin de texte peut être interprété de façon imprévisible par la
phonémisation. Toujours terminer une pensée avec une ponctuation forte
propre.

## 3. Résumé express (checklist)

- [ ] Chaque phrase se termine par `.`, `!` ou `?`
- [ ] Phrases de 8 à 20 mots en moyenne, pas de phrase-fleuve
- [ ] Virgules = vraies pauses de respiration, pas de décoration
- [ ] Connecteurs explicites (car, donc, afin de...) plutôt que incises
- [ ] Pas de parenthèses/tirets pour les asides : deux phrases séparées
- [ ] Aucun markdown, symbole, emoji, lien
- [ ] Nombres/unités écrits simplement, sans abréviation ambiguë
- [ ] Sigles développés sauf s'ils sont très courants à l'oral
- [ ] `fast` pour une réponse courte, `read` pour plusieurs phrases
