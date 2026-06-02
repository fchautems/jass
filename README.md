# Jass Chibre romand

Ce dépôt contient une première version de moteur de jeu pour le **Jass suisse, variante Chibre romand à 4 joueurs**. L'objectif de cette étape est de poser un noyau de règles fiable avant d'ajouter des bots ou une IA entraînable.

## État actuel

Le moteur implémente :

- 4 joueurs et 2 équipes fixes : `0 + 2` contre `1 + 3` ;
- paquet de 36 cartes, distribution de 9 cartes par joueur ;
- premier donneur/choisisseur déterminé par le détenteur du `7 de carreau` ;
- rotation du donneur/choisisseur au joueur suivant après une donne terminée ;
- choix direct de l'atout ou `chibre` vers le partenaire, sans re-chibre ;
- force et points des cartes à l'atout et hors-atout ;
- validation des plis, obligation de fournir, coupe, défausse et sous-coupe interdite ;
- exception du bour : le valet d'atout n'est jamais forcé ;
- points de plis, dernier pli à +5 et match à +100 ;
- annonces automatiques révélées à la première carte posée par chaque joueur ;
- comparaison des annonces et attribution des annonces ordinaires à l'équipe gagnante ;
- stöck révélé automatiquement à la pose de la seconde carte roi/dame d'atout ;
- option future `pique double` via `GameOptions.with_pique_double()` ;
- vue joueur limitée (`PlayerView`) pour ne pas exposer les mains cachées ni tous les anciens plis.

## Points d'interprétation à confirmer

La règle demande de ne pas inventer silencieusement une règle ambiguë. Les choix suivants sont donc documentés explicitement :

1. **Suites et réutilisation des cartes** : le moteur détecte toutes les sous-suites contiguës valides de longueur au moins 3 dans une même couleur. Par exemple, une suite `6-7-8-9-10` compte la suite de 5, les deux suites de 4 et les trois suites de 3. Cela maximise la règle « une même carte peut participer à plusieurs annonces ».
2. **Bour jamais forcé** : le moteur exclut le bour des obligations de fournir/couper. Si l'atout est demandé et que le joueur ne possède que le bour comme atout, il peut jouer une autre carte de sa main.
3. **Pique double** : l'option double actuellement l'ensemble des points de la donne calculés par le moteur, y compris plis, match, annonces ordinaires et stöck. Si la variante pratiquée ne double qu'une partie de ces points, il faudra ajuster cette option.

Ces points sont volontairement visibles pour pouvoir les corriger avant d'entraîner des IA sur une règle différente de la variante souhaitée.

## Utilisation rapide

```python
from jass_chibre import GameState, Suit, TrumpChoice

jeu = GameState()
donne = jeu.start_deal(seed=42)
donne.choose_trump(donne.chooser, TrumpChoice.direct(Suit.HEARTS))

joueur = donne.current_leader
cartes_legales = donne.legal_cards_for(joueur)
donne.play_card(joueur, cartes_legales[0])
```

## Tests

```bash
pytest -q
```
