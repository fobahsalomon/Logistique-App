# Prompt pour Claude Code — v3 : enrichissement OSM + mode navigation

Ce prompt fait suite aux itérations précédentes (app Streamlit + ORS + SQLite + table `lieux_connus` + import GeoNames + carte verrouillée sur la Côte d'Ivoire, déjà en place et fonctionnelles). Colle-le dans Claude Code, dans le dossier du projet existant.

Ne pas modifier ce qui existe déjà (moteur de calcul, table `trajets`, logique de résolution en 3 étapes `lieux_connus → géocodage → clic carte`, import GeoNames). Ce qui suit s'ajoute.

---

## Partie A — Enrichir la base de lieux au-delà de GeoNames

### Contexte
GeoNames (déjà importé, 16 917 lieux) ne couvre que les localités habitées officielles. Pour se rapprocher de la densité de Google/Yandex, il faut ajouter les données d'OpenStreetMap, beaucoup plus riches en quartiers, lieux-dits et points de repère locaux.

### À faire

1. Ajouter un script `data/import_osm.py` qui :
   - Télécharge l'extrait OSM de Côte d'Ivoire depuis Geofabrik : `https://download.geofabrik.de/africa/ivory-coast-latest.osm.pbf`
   - Utilise `pyosmium` (`pip install osmium`) pour parcourir le fichier `.osm.pbf` et extraire les nœuds/lieux nommés pertinents : tags `place=*` (city, town, village, suburb, neighbourhood, hamlet, locality), et optionnellement quelques catégories utiles pour un transporteur (`amenity=bus_station`, `highway=bus_stop` si présents et nommés).
   - Pour chaque entité retenue avec un nom et des coordonnées, insérer dans `lieux_connus` avec `source='osm'`, en réutilisant la fonction `inserer_lieu()` déjà existante (idempotente) et la même normalisation (`nom_normalise`) que pour GeoNames.
   - Ne pas dupliquer les entrées déjà présentes via GeoNames (vérifier avant insertion par `nom_normalise` + proximité des coordonnées, ex. tolérance de quelques centaines de mètres).
   - Ne pas committer le fichier `.osm.pbf` téléchargé (l'ajouter au `.gitignore`), documenter la commande dans le `README.md` (`python data/import_osm.py`), à lancer une fois après clone.

2. Ajouter une fonction utilitaire (facultative mais utile) dans `core/routing.py` ou un nouveau `core/osm_overpass.py` qui interroge l'**Overpass API** (`https://overpass-api.de/api/interpreter`) à la demande, pour chercher un lieu précis (`place=*` avec un nom proche de la recherche, dans la bounding box Côte d'Ivoire) quand ni `lieux_connus` ni le géocodage habituel ne trouvent de résultat. Si un résultat Overpass est trouvé, l'insérer automatiquement dans `lieux_connus` (`source='overpass'`) comme les autres sources, avant de proposer le clic manuel sur la carte en dernier recours.

3. Mettre à jour l'ordre de résolution dans `core/routing.py` en conséquence : `lieux_connus` (GeoNames + OSM déjà importés + ajouts précédents) → géocodage habituel déjà en place → **Overpass API en complément ciblé** → clic sur la carte en dernier recours.

## Partie B — Mode navigation façon Google Maps

### Contexte
Actuellement le trajet est visualisé de façon basique. L'objectif est une visibilité proche de Google Maps/Yandex : tracé réel de la route, vue automatiquement cadrée, marqueurs de type navigation, et un panneau d'instructions.

### À faire

1. **Tracé réel de l'itinéraire** : utiliser la géométrie complète renvoyée par l'appel de routage ORS (pas seulement distance/durée) pour dessiner la route exacte suivie (grâce à `geometry=true` ou équivalent dans l'appel `directions` d'OpenRouteService), et l'afficher comme une polyligne stylée sur la carte (couleur distincte, épaisseur suffisante pour bien voir le tracé, par-dessus le fond de carte).

2. **Cadrage automatique sur le trajet** : dès qu'un itinéraire est calculé, la carte doit se recentrer et zoomer automatiquement pour que tout le trajet soit visible (`fit_bounds` sur l'enveloppe de la géométrie de la route), sans action manuelle de l'utilisatrice.

3. **Marqueurs de type navigation** : marqueur vert distinct pour le point de départ, marqueur rouge distinct pour l'arrivée (icônes plus lisibles que des points par défaut, par exemple des pins avec des icônes Folium adaptées), plutôt que deux marqueurs identiques.

4. **Panneau d'instructions turn-by-turn** : afficher sous ou à côté de la carte la liste des étapes de navigation renvoyées par ORS (l'API `directions` fournit un `segments[].steps[]` avec instruction textuelle, distance et durée par étape) — une liste simple, façon Google Maps ("Continuer sur X pendant 12 km", "Tourner à droite vers Y", etc.), avec la distance/durée de chaque étape.

5. **Bouton "recentrer"** : un petit bouton pour revenir au cadrage automatique sur le trajet si l'utilisatrice a zoomé/déplacé la carte manuellement entre-temps.

### Ce qu'il ne faut PAS faire
- Ne pas remplacer le fond de carte actuel (rester sur OpenStreetMap/Leaflet, pas besoin de style Google Maps précisément, juste un tracé et des marqueurs propres).
- Ne pas casser la logique de résolution de lieux existante (`lieux_connus → géocodage → Overpass → clic`), le mode navigation ne concerne que l'affichage une fois les deux points résolus.
- Ne pas rendre le panneau d'instructions obligatoire à lire — il doit être un complément visuel, pas bloquer le calcul du devis si l'utilisatrice l'ignore.

## Livrables attendus

1. `data/import_osm.py` fonctionnel, avec documentation dans le `README.md`.
2. `core/osm_overpass.py` (ou fonction équivalente) pour la recherche Overpass à la demande, intégrée dans l'ordre de résolution.
3. Carte mise à jour dans `app.py` : tracé réel de l'itinéraire, cadrage automatique, marqueurs différenciés départ/arrivée, panneau d'instructions turn-by-turn, bouton de recentrage.