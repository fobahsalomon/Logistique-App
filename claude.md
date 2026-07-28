# Prompt pour Claude Code — v4 : corrections carte, recherche, ajout de lieu, suppression trajet, retrait navigation

Ce prompt s'applique au projet Flask actuel (repo `github.com/fobahsalomon/Logistique-App`, stack Python 3.13 / Flask 3 / SQLite / Leaflet.js / OSRM + Nominatim). Colle-le dans Claude Code, dans le dossier du projet cloné.

Ne pas toucher au moteur de devis (`core/pricing.py`, formule ×4 incluse), à la structure des tables `trajets`/`lieux_connus`, ni aux endpoints existants sauf ceux explicitement mentionnés ci-dessous.

---

## 1. Retirer complètement le mode navigation / instructions turn-by-turn

Les instructions de navigation pas-à-pas ne correspondent pas au besoin et doivent être **entièrement retirées**, pas seulement masquées :

- Supprimer le panneau pliable d'instructions dans `templates/index.html`.
- Supprimer la logique de génération des instructions turn-by-turn (parsing des manœuvres OSRM) dans `static/js/app.js` et dans `core/routing.py` si elle s'y trouve.
- Si l'appel à OSRM demande explicitement les manœuvres (paramètre type `steps=true`), simplifier l'appel pour ne récupérer que la géométrie du tracé, la distance et la durée — pas les étapes détaillées.
- Conserver en revanche : le tracé réel de l'itinéraire sur la carte (couleur teal), le `fitBounds` automatique, l'affichage simple de la distance et de la durée totales, et le bouton "⟲ Recentrer". Seul le détail pas-à-pas doit disparaître.

## 2. Corriger le bouton supprimer (trajets connus)

Le bouton supprimer d'un trajet dans la liste ne fonctionne pas. Causes probables à vérifier dans l'ordre :

1. **Écouteur d'événement perdu après re-rendu** : si la liste des trajets est réinjectée dynamiquement (`innerHTML = ...`) après chaque chargement/modification, les écouteurs attachés individuellement à chaque bouton au premier rendu sont perdus. Vérifier si c'est le cas dans `static/js/app.js` ; si oui, remplacer par de la délégation d'événements (un seul écouteur sur le conteneur parent de la liste, qui vérifie `event.target` pour identifier le clic sur un bouton supprimer).
2. **Element `<dialog>` natif** : si la confirmation de suppression passe par un `<dialog>` avec un `<form method="dialog">`, ce type de formulaire ferme la boîte de dialogue sans déclencher d'appel réseau à moins que le `fetch` DELETE soit explicitement appelé dans le gestionnaire du bouton de confirmation. Vérifier que l'appel `fetch('/api/trajet/<id>', { method: 'DELETE' })` est bien exécuté avant/à la fermeture du dialogue, pas juste la fermeture visuelle.
3. **Type de l'identifiant** : vérifier que l'ID passé en JS (attribut `data-id` ou équivalent) correspond bien au type attendu par la route Flask (`<int:id>` vs chaîne).
4. **Vérification réseau** : ouvrir la console navigateur et l'onglet réseau pendant un clic sur supprimer, pour confirmer si la requête part réellement, son code de retour, et l'éventuelle erreur JS avant l'appel (un throw silencieux plus haut dans le gestionnaire empêcherait le fetch de se déclencher).
5. Une fois corrigé, s'assurer que la liste se rafraîchit réellement après suppression (recharger les données depuis `/api/trajets` ou retirer la ligne du DOM) plutôt que de laisser un état obsolète affiché.

Ajouter un test dans `tests/test_app.py` couvrant explicitement `DELETE /api/trajet/<id>` (suppression réelle + code retour + vérification que le trajet n'apparaît plus dans `/api/trajets`).

## 3. Améliorer le niveau de détail de la carte

- Passer le `maxZoom` du fond de carte à 19 (niveau rue) si ce n'est pas déjà le cas — seul le zoom minimum (verrouillage Côte d'Ivoire, `minZoom: 6`) doit rester contraint, pas le zoom maximum.
- Remplacer ou compléter le fond de carte OpenStreetMap standard par un fournisseur de tuiles gratuit et sans clé offrant plus de labels/détails visuels, par exemple CartoDB Voyager (`https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png`, attribution CARTO/OpenStreetMap requise). Objectif : plus de lisibilité des noms de rues/quartiers à un niveau de zoom donné, pas juste un changement esthétique.
- Ajouter un contrôle d'échelle (Leaflet `L.control.scale()`) sur la carte, absent actuellement.

## 4. Améliorer la pertinence et la couverture de la recherche

- Actuellement l'autocomplétion (`/api/lieux?q=`) ne cherche que dans `lieux_connus`. Si moins de 3 résultats sont trouvés localement pour une saisie de 3 caractères ou plus, compléter en direct avec un appel à Nominatim (et si toujours rien, Overpass) au moment de la frappe, pas seulement au moment de la résolution finale — pour que l'utilisatrice voie des suggestions même pour un lieu jamais recherché avant.
- Fusionner les deux types de résultats dans la liste de suggestions, avec un petit indicateur visuel différenciant "base locale" (résultat instantané) et "résultat en ligne" (légèrement plus lent, premier appel réseau) pour que l'utilisatrice comprenne pourquoi certaines suggestions apparaissent après un court délai.
- Remplacer la logique de correspondance par sous-chaîne simple par un scoring de similarité (bibliothèque `rapidfuzz`, `pip install rapidfuzz`) pour mieux classer les résultats les plus pertinents en premier, et tolérer les fautes de frappe légères.
- Limiter à un nombre raisonnable de suggestions affichées (8 maximum), triées par pertinence.

## 5. Refaire le workflow d'ajout d'un nouveau lieu

Le flux actuel (mode clic caché dans un `<details>` de secours) n'est pas clair. Le remplacer par un flux explicite et visible :

1. Ajouter un bouton toujours visible **"+ Ajouter un nouveau lieu"** dans l'interface principale (pas dans un élément replié).
2. Au clic, activer un "mode ajout" clairement signalé (bandeau ou changement de curseur sur la carte : "Cliquez sur la carte à l'endroit du nouveau lieu").
3. Au clic sur la carte en mode ajout, faire apparaître directement une popup Leaflet à l'endroit cliqué (pas une modale déconnectée de la position) contenant un champ texte pour le nom du lieu et un bouton "Enregistrer".
4. À l'enregistrement, appeler l'endpoint existant `POST /api/lieu`, poser un marqueur définitif à cet endroit, désactiver le mode ajout, et rendre ce nouveau lieu immédiatement disponible dans l'autocomplétion sans recharger la page.
5. Conserver le mode clic existant pour la résolution d'un trajet en cours (quand un lieu tapé est introuvable) mais le distinguer clairement de ce nouveau flux dédié à l'enrichissement volontaire de la base — deux intentions différentes ("je résous un trajet maintenant" vs "j'enrichis la base de lieux"), donc deux entrées différentes dans l'interface.

## Ce qu'il ne faut PAS faire

- Ne pas toucher au moteur de calcul de devis ni à la formule ×4.
- Ne pas modifier la structure des tables existantes.
- Ne pas réintroduire de dépendance à une clé API payante — rester sur OSRM/Nominatim/Overpass, sans clé.

## Livrables attendus

1. Panneau et logique d'instructions turn-by-turn entièrement supprimés.
2. Bouton supprimer fonctionnel, avec test couvrant le cas.
3. Carte avec zoom maximum élevé, fond de carte plus détaillé, contrôle d'échelle ajouté.
4. Recherche enrichie (scoring de pertinence + complément en ligne si peu de résultats locaux) avec indicateur d'origine des suggestions.
5. Nouveau workflow explicite et visible pour ajouter un lieu, distinct du mode clic de secours pendant la résolution d'un trajet.
6. `pytest tests/` toujours entièrement vert après ces changements.