# CA TRANS — Fiche de calcul convoi

Application web de gestion de devis et d'itinéraires pour le transport de voyageurs en Côte d'Ivoire. Elle centralise la recherche de lieux, le calcul d'itinéraire réel, la comparaison de trajets connus et la génération de devis/PDF sans dépendre d'une clé API payante.

## Fonctionnalités

- Résolution de lieux en plusieurs étapes : base locale, Nominatim, Overpass, puis clic manuel.
- Autocomplétion dynamique avec support de recherche approximative (rapidfuzz) et résultats en ligne si la base locale est insuffisante.
- Ajout explicite de nouveaux lieux depuis la carte, immédiatement disponibles dans l'autocomplétion.
- Calcul d'itinéraire réel via OSRM avec tracé sur carte, fitBounds automatique et bouton de recentrage.
- Gestion des trajets connus (CRUD) et comparaison avec un trajet standard déjà enregistré.
- Moteur de devis basé sur les formules Excel CA TRANS, incluant consommation, coûts carburant, frais de mission, péages, marge et TVA.
- Génération de PDF proforma simplifié pour l'impression côté client.
- Interface responsive et protection par login.

## Stack technique

- Backend : Python 3.13 + Flask 3
- Base de données : SQLite
- Frontend : HTML/CSS/JS vanilla + Leaflet
- Géocodage / routage : OSRM, Nominatim, Overpass
- PDF : ReportLab
- Recherche approximative : rapidfuzz
- Tests : pytest

## Structure du projet

```text
.
├── app.py
├── core/
│   ├── db.py
│   ├── devis_pdf.py
│   ├── devis_service.py
│   ├── pricing.py
│   ├── proforma_pdf.py
│   └── routing.py
├── data/
│   ├── ca_trans.db
│   ├── seed_trajets.py
│   └── ...
├── static/
│   ├── css/
│   └── js/
├── templates/
│   ├── index.html
│   └── login.html
├── tests/
│   └── test_app.py
├── requirements.txt
├── .env.example
├── README.md
└── render.yaml
```

## Installation

```bash
git clone <url-du-repo>
cd "Logistique App"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Variables d'environnement

Aucune clé API n'est obligatoire. Le projet fonctionne avec les services OpenStreetMap/OSRM gratuits.

Exemple de `.env` facultatif :

```bash
PORT=5000
SECRET_KEY=votre-cle-secrete
```

## Démarrage local

```bash
python app.py
```

L'application est ensuite disponible sur `http://localhost:5000`.

## Tests

```bash
pytest tests/
```

## Note

Le dépôt contient plusieurs branches fonctionnelles qui ont été fusionnées dans cette branche de test `main-test` afin de permettre une validation unifiée des modifications.
