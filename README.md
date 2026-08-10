# CA TRANS — Fiche de calcul convoi

Application web Flask pour l'établissement de devis de convoi de bus en Côte d'Ivoire.
Remplace la recherche manuelle sur Google Maps par un calcul d'itinéraire automatique
et reproduit fidèlement le moteur de calcul du fichier Excel original.

Interface 100 % custom (HTML/CSS/JS + Leaflet) — aucun framework de dashboard.

## Fonctionnalités

- **Résolution de lieux en 4 étapes** (zéro configuration requise) :
  1. Base locale `lieux_connus` (GeoNames + OSM pré-importés, enrichissement automatique)
  2. Nominatim (OpenStreetMap) — résultat sauvegardé pour les prochains appels
  3. Overpass API (OSM) — fallback ciblé sur la Côte d'Ivoire
  4. Clic manuel sur la carte
- **Autocomplétion dynamique** sur 16 000+ lieux ivoiriens (GeoNames)
- **Tracé réel** de l'itinéraire sur la carte (OSRM)
- **Cadrage automatique** sur le trajet + bouton « Recentrer »
- **Marqueurs différenciés** : pin vert (départ) / pin rouge (arrivée)
- **Instructions de navigation** turn-by-turn (French) pliables sous la carte
- **Base de 70 trajets connus** avec édition/suppression via modal
- **Moteur de devis** : carburant × 4, frais de mission, TVA 18 %, prix par place

## Architecture

```
├── app.py                        # backend Flask (9 endpoints API JSON)
├── core/
│   ├── routing.py                # OSRM + Nominatim + Overpass (sans clé API)
│   ├── osm_overpass.py           # geocodage de secours via Overpass API
│   ├── pricing.py                # moteur de calcul du devis (formules Excel)
│   └── db.py                     # SQLite : trajets + lieux_connus
├── data/
│   ├── seed_trajets.py           # 70 trajets connus (peuplement idempotent)
│   ├── import_geonames.py        # import GeoNames CI (~16 917 lieux)
│   └── import_osm.py             # import OSM CI via pyosmium (~60 Mo)
├── templates/index.html
├── static/css/style.css
├── static/js/app.js
└── tests/test_app.py             # 16 tests (pytest)
```

## Installation

```bash
git clone <url-du-repo>
cd "Logistique App"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Peupler la base de lieux

L'application fonctionne immédiatement avec les 70 trajets connus et le
géocodage automatique. Pour une autocomplétion complète sur les 16 000+ lieux
ivoiriens, lancez les imports une fois après le clone :

```bash
# GeoNames (nécessite data/CI/CI.txt — téléchargeable sur geonames.org)
python data/import_geonames.py

# OSM — télécharge ~60 Mo depuis Geofabrik puis insère dans lieux_connus
python data/import_osm.py
```

Ces deux commandes sont **idempotentes** : relancer n'insère pas de doublons.

## Lancement local

```bash
python app.py
# → http://localhost:5000
```

## Tests

```bash
pytest tests/
```

16 tests couvrent le moteur de calcul, les endpoints API, le CRUD trajets
et l'autocomplétion.

## Déploiement sur Render

1. Poussez sur GitHub et connectez le dépôt sur [Render](https://render.com).
2. Render détecte `render.yaml` automatiquement (build : `pip install -r
   requirements.txt`, start : `gunicorn app:app`).
3. La base SQLite (`data/ca_trans.db`, avec les 70 trajets connus + ~35 000
   lieux GeoNames/OSM déjà importés) est **committée dans le repo** pour
   survivre au système de fichiers éphémère du plan gratuit Render. Toute
   modification faite en production (nouveaux trajets, lieux ajoutés au clic)
   sera donc perdue au prochain redéploiement, sauf à re-committer la base
   mise à jour ou à passer à un disque persistant Render.

## Note importante sur le moteur de calcul

Le coût carburant est multiplié par **4** dans la formule — règle métier
propre à CA TRANS, reproduction fidèle de l'Excel d'origine. Ne pas modifier.
