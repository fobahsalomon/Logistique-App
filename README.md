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
- **Devis PDF** : génération serveur via ReportLab, téléchargement en un clic
- **Recalcul explicite** du devis après modification des paramètres
- **Sélecteur de catégorie** de car (63, 58 VIP, 51, 49 places)
- **Interface responsive** adaptée aux mobiles

## Architecture

```
├── app.py                        # backend Flask (10 endpoints API JSON + PDF)
├── core/
│   ├── routing.py                # OSRM + Nominatim + Overpass (sans clé API)
│   ├── osm_overpass.py           # geocodage de secours via Overpass API
│   ├── pricing.py                # moteur de calcul du devis (formules Excel)
│   ├── devis_service.py          # validation et sérialisation des devis
│   ├── devis_pdf.py              # génération PDF via ReportLab
│   └── db.py                     # SQLite : trajets + lieux_connus
├── data/
│   ├── seed_trajets.py           # 70 trajets connus (peuplement idempotent)
│   ├── import_geonames.py        # import GeoNames CI (~16 917 lieux)
│   └── import_osm.py             # import OSM CI via pyosmium (~60 Mo)
├── templates/index.html
├── static/css/style.css
├── static/js/app.js
└── tests/test_app.py             # 26 tests (pytest)
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

26 tests couvrent le moteur de calcul, les endpoints API (dont PDF), le CRUD trajets
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

## Usage du devis

1. Sélectionnez une **catégorie de car** (63, 58 VIP, 51 ou 49 places).
2. Résolvez un itinéraire ou saisissez une distance manuelle.
3. Modifiez les paramètres si nécessaire (consommation, frais, marge, remise...).
4. Cliquez sur **« Recalculer la fiche de devis »**.
5. Cliquez sur **« Télécharger le PDF »** pour obtenir la fiche de devis au format PDF.

Le PDF est généré côté serveur sans être sauvegardé sur le disque.

## Note importante sur le moteur de calcul

Le coût carburant est multiplié par **4** dans la formule — règle métier
propre à CA TRANS, reproduction fidèle de l'Excel d'origine. Ne pas modifier.

## Auteur

- GitHub : [@fobahsalomon](https://github.com/fobahsalomon)
- Email : fobahngouansalomon@gmail.com
- Portfolio : [fobahsalomon.github.io/portfolio](https://fobahsalomon.github.io/portfolio)
