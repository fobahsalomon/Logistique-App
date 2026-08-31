# CA TRANS — Application de gestion de devis et proforma

Application web de gestion de devis, de comparaison d'itinéraires et de génération de facture Proforma pour CA TRANS SARL U.

Le projet permet de :
- calculer un itinéraire réel sur carte,
- comparer le devis réel avec un trajet standard présent dans la base,
- mettre en avant les montants HT (Aller simple / Aller-retour),
- compléter les informations client et administratives,
- générer une proforma PDF conforme au format officiel CA TRANS.

## Fonctionnalités principales

- Calculateur d'itinéraires réels et pré-sélection de trajets standards
- Comparateur côte à côte entre itinéraire réel et trajet standard
- Mise en avant des montants HT dans la fiche devis
- Formulaire dynamique d'informations voyage/client
- Génération de facture Proforma PDF conforme au modèle officiel
- Gestion des trajets connus et autocomplétion intelligente
- Interface Dark Mode orientée utilisateur et responsive
- Protection d'accès par login

## Stack technique

- Backend : Python 3.13 + Flask 3
- Base de données : SQLite
- Frontend : HTML / CSS / JavaScript vanilla + Leaflet
- Routage / géocodage : OSRM, Nominatim, Overpass
- PDF : ReportLab
- Recherche approximative : rapidfuzz
- Tests : pytest

## Architecture du projet

```text
.
├── app.py
├── core/
│   ├── db.py
│   ├── devis_service.py
│   ├── pricing.py
│   ├── proforma_pdf.py
│   ├── routing.py
│   └── ...
├── static/
│   ├── css/
│   ├── js/
│   └── catrans-logo.png
├── templates/
│   ├── index.html
│   └── login.html
├── assets/
│   ├── README.md
│   └── branding/
│       └── catrans-logo.png
├── ui/
│   └── README.md
├── utils/
│   └── README.md
├── data/
│   ├── ca_trans.db
│   ├── seed_trajets.py
│   └── ...
├── tests/
│   └── ...
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── Procfile
├── render.yaml
└── PRO FORMA CONVOI CATRANS-M OBITE.pdf
```

> Le dépôt a été préparé pour une organisation plus claire : les éléments de marque sont regroupés dans `assets/`, la logique d'interface est documentée dans `ui/`, et les utilitaires partagés sont structurés dans `utils/` sans casser le fonctionnement actuel de l'application.

## Installation et lancement local

### Prérequis

- Python 3.11+
- Pip / venv
- Accès à internet standard pour OSRM / Nominatim / Overpass

### 1) Cloner et entrer dans le projet

```bash
git clone <url-du-repo>
cd "Logistique App"
```

### 2) Créer un environnement virtuel

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3) Installer les dépendances

```bash
pip install -r requirements.txt
```

### 4) Configurer les variables d'environnement (optionnel)

```bash
cp .env.example .env
```

Exemple de contenu `.env` :

```bash
PORT=5000
SECRET_KEY=votre-cle-secrete
```

### 5) Lancer l'application

```bash
python app.py
```

Ou, si vous préférez Flask CLI :

```bash
export FLASK_APP=app.py
flask run --debug
```

L'application est ensuite accessible sur :
- `http://localhost:5000`

## Guide d'utilisation

### 1. Recherche / saisie du trajet

- Saisissez la ville ou le lieu de départ et de destination.
- L'application propose des suggestions locales, puis enrichit la recherche via Nominatim / Overpass si nécessaire.
- Sélectionnez le point de départ et la destination.
- Validez le parcours et la carte affiche l'itinéraire réel calculé.

### 2. Comparaison et sélection du devis retenu

- Vérifiez la comparaison côte à côte entre :
  - Itinéraire réel calculé
  - Trajet standard enregistré dans la base
- Analysez les montants HT, les distances, les paramètres clés et les prix par place.
- Sélectionnez le devis qui correspond le mieux à la demande.

### 3. Remplissage des informations administratives

- Ouvrez le formulaire Proforma.
- Saisissez :
  - nom / raison sociale du client,
  - responsable de la flotte,
  - dates exactes de location,
  - numéro Proforma généré automatiquement.
- Validez le récapitulatif avant génération du PDF.

### 4. Téléchargement et impression de la Proforma

- Cliquez sur le bouton de génération PDF.
- Le document est généré au format CA TRANS avec en-tête, totaux, signatures et pied de page.
- Vous pouvez ensuite l'imprimer ou le télécharger au format PDF.

## Tests

```bash
pytest tests/
```

## Bonnes pratiques de production

- Ne jamais committer les clés ou fichiers `.env` sensibles.
- Conserver les fichiers de log dans un répertoire dédié, hors du dépôt.
- Vérifier la conformité des dépendances avant déploiement.
- Faire tourner le projet derrière un WSGI robuste en environnement de production (ex. Gunicorn/Render).

## Déploiement

Le projet est prêt pour un déploiement sur des plateformes Flask classiques (Render, Heroku, VPS Linux, etc.).

Le fichier `Procfile` et `render.yaml` inclus permettent une mise en œuvre rapide sur Render.
