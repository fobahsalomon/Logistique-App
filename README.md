# CA TRANS — Fiche de calcul convoi

Application web (Flask) qui remplace la recherche manuelle de distance sur
Google Maps par un calcul d'itinéraire fiable via **OpenRouteService**
(profil poids lourd `driving-hgv`, qui exclut les routes interdites aux gros
véhicules), et reproduit fidèlement le moteur de calcul de devis du fichier
Excel original (`FICHE DE CALCUL CONVOI CA TRANS.xlsx`).

Interface 100% custom (HTML/CSS/JS + Leaflet pour la carte) — aucun
framework de dashboard type Streamlit, contrôle total du design.

## Fonctionnement

1. La distance d'un trajet est d'abord cherchée dans une base SQLite de
   trajets déjà connus (recherche tolérante : accents, casse, abréviations
   « SP » → San Pedro, « ABJ » → Abidjan).
2. Si le trajet est inconnu, origine et destination sont géocodées puis
   l'itinéraire routier réel est calculé via OpenRouteService.
3. Si le géocodage échoue, la distance peut être saisie manuellement.
4. Le moteur de devis (`core/pricing.py`) calcule ensuite tous les postes
   (carburant, frais, marge, TVA, prix par place...) à l'identique de
   l'Excel original.

## Architecture

```
ca-trans-devis/
├── app.py                     # backend Flask (routes HTML + API JSON)
├── requirements.txt
├── Procfile                   # démarrage Render/Heroku (gunicorn)
├── render.yaml                # blueprint de déploiement Render
├── .env.example                # modèle de variables d'environnement
├── data/seed_trajets.py       # peuple la base avec les 70 trajets connus
├── core/
│   ├── routing.py             # OpenRouteService (géocodage + itinéraire)
│   ├── pricing.py             # moteur de calcul du devis
│   └── db.py                  # SQLite : recherche tolérante, CRUD
├── templates/index.html       # page unique (Jinja2)
├── static/css/style.css       # design custom
├── static/js/app.js           # carte Leaflet + appels API + fiche de devis
└── tests/test_pricing.py
```

`core/` est indépendant du framework web : `pricing.py`, `db.py` et
`routing.py` ne dépendent que de la stdlib et d'`openrouteservice`.

## Installation

```bash
git clone <url-du-repo>
cd ca-trans-devis
python3 -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
```

## Obtenir une clé API OpenRouteService

1. Créez un compte gratuit sur https://openrouteservice.org/dev/#/signup
   (2000 requêtes/jour gratuites).
2. Récupérez votre clé API dans le tableau de bord ORS.

### Configuration en local

Copiez le modèle et renseignez votre clé :

```bash
cp .env.example .env
```

Éditez `.env` :

```
ORS_API_KEY=votre_clé_api_ici
```

Ce fichier est listé dans `.gitignore` et ne doit **jamais** être commité.
La clé n'est utilisée que côté serveur (`os.environ`), jamais exposée au
navigateur.

## Initialiser la base de trajets connus

`app.py` crée automatiquement la base (`data/ca_trans.db`) et y insère les 70
trajets connus au premier démarrage (insertion idempotente : si les trajets
« excel » sont déjà présents, rien n'est ré-inséré). Vous pouvez aussi lancer
le seed manuellement :

```bash
python data/seed_trajets.py
```

Relancer avec `--reset` pour repartir d'une base vide :

```bash
python data/seed_trajets.py --reset
```

## Lancement local

```bash
python app.py
```

L'application est accessible sur http://localhost:5000.

Pour tester avec un serveur de production (comme sur Render) :

```bash
gunicorn app:app
```

## Tests

```bash
pytest tests/
```

Les tests valident le moteur de calcul (`core/pricing.py`) avec le cas de
référence issu du fichier Excel original (distance 437 km).

## Déploiement sur Render

1. Poussez ce dépôt sur GitHub (public ou privé). GitHub héberge uniquement
   du contenu statique (GitHub Pages) — Render exécute réellement l'app
   Flask, connectée en continu à votre repo GitHub (déploiement automatique
   à chaque push, comme Streamlit Cloud).
2. Sur https://dashboard.render.com, cliquez sur **New +** → **Web Service**,
   connectez votre compte GitHub et sélectionnez ce dépôt.
3. Render détecte `render.yaml` automatiquement (build : `pip install -r
   requirements.txt`, démarrage : `gunicorn app:app`). Sans `render.yaml`,
   renseignez ces commandes manuellement dans les paramètres du service.
4. Dans **Environment**, ajoutez la variable :

   ```
   ORS_API_KEY = votre_clé_api_ici
   ```

5. Déployez. À chaque push sur la branche configurée, le service se
   redéploie automatiquement.

Note : le système de fichiers de Render (plan gratuit) est éphémère — la
base SQLite (`data/ca_trans.db`) est recréée à chaque redéploiement.
`app.py` réinitialise le schéma et réinsère automatiquement les 70 trajets
connus à chaque démarrage, donc aucune action manuelle n'est nécessaire.
Les trajets ajoutés en production via l'application (source `ors`/`manuel`)
ne survivent en revanche pas à un redéploiement, puisque le disque n'est pas
persistant (passer à un disque persistant Render si cette persistance est
nécessaire).

## Ce que l'application ne modifie pas

Les formules du moteur de calcul reproduisent exactement l'Excel d'origine,
y compris le facteur ×4 appliqué au coût du carburant — une règle métier
propre à CA TRANS, non une erreur à corriger.
