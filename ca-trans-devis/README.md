# CA TRANS — Fiche de calcul convoi

Application web (Streamlit) qui remplace la recherche manuelle de distance
sur Google Maps par un calcul d'itinéraire fiable via **OpenRouteService**
(profil poids lourd `driving-hgv`, qui exclut les routes interdites aux gros
véhicules), et reproduit fidèlement le moteur de calcul de devis du fichier
Excel original (`FICHE DE CALCUL CONVOI CA TRANS.xlsx`).

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
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Éditez `.streamlit/secrets.toml` :

```toml
ors_api_key = "votre_clé_api_ici"
```

Ce fichier est listé dans `.gitignore` et ne doit **jamais** être commité.

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
streamlit run app.py
```

L'application est accessible sur http://localhost:8501.

## Tests

```bash
pytest tests/
```

Les tests valident le moteur de calcul (`core/pricing.py`) avec le cas de
référence issu du fichier Excel original (distance 437 km).

## Déploiement sur Streamlit Community Cloud

1. Poussez ce dépôt sur GitHub (public ou privé).
2. Rendez-vous sur https://share.streamlit.io et connectez votre compte
   GitHub.
3. Cliquez sur **New app**, sélectionnez le dépôt, la branche et
   `app.py` comme fichier principal.
4. Dans les **Secrets** du dashboard de l'application (Settings → Secrets),
   ajoutez :

   ```toml
   ors_api_key = "votre_clé_api_ici"
   ```

5. Déployez. À chaque push sur la branche configurée, l'application se
   redéploie automatiquement.

Note : sur Streamlit Community Cloud, le système de fichiers est éphémère —
la base SQLite (`data/ca_trans.db`) est recréée à chaque redéploiement.
`app.py` réinitialise le schéma et réinsère automatiquement les 70 trajets
connus à chaque démarrage, donc aucune action manuelle n'est nécessaire
après un redéploiement. Les trajets ajoutés en production via l'application
(source `ors`/`manuel`) ne survivent en revanche pas à un redéploiement,
puisque le disque n'est pas persistant.

## Arborescence

```
ca-trans-devis/
├── app.py                     # interface Streamlit
├── requirements.txt
├── .streamlit/secrets.toml.example
├── data/seed_trajets.py       # peuple la base avec les 70 trajets connus
├── core/
│   ├── routing.py             # OpenRouteService (géocodage + itinéraire)
│   ├── pricing.py             # moteur de calcul du devis
│   └── db.py                  # SQLite : recherche tolérante, CRUD
└── tests/test_pricing.py
```

## Ce que l'application ne modifie pas

Les formules du moteur de calcul reproduisent exactement l'Excel d'origine,
y compris le facteur ×4 appliqué au coût du carburant — une règle métier
propre à CA TRANS, non une erreur à corriger.
