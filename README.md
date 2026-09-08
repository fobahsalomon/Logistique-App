# CA TRANS — Fiche de calcul convoi & proformas

Application web Flask pour l'établissement de devis de convoi de bus en Côte d'Ivoire (CA TRANS SARL U), avec calcul d'itinéraire automatique, comparateur de devis, circuit de validation des proformas par un administrateur, et panneau d'administration.

## Sommaire

- [Fonctionnalités](#fonctionnalités)
- [Stack technique](#stack-technique)
- [Architecture du projet](#architecture-du-projet)
- [Rôles & permissions](#rôles--permissions)
- [Workflow métier : du devis à la proforma validée](#workflow-métier--du-devis-à-la-proforma-validée)
- [Installation locale](#installation-locale)
- [Variables d'environnement](#variables-denvironnement)
- [Base de données](#base-de-données)
- [Sécurité](#sécurité)
- [Tests](#tests)
- [Déploiement (Render)](#déploiement-render)
- [Limitations connues](#limitations-connues)

## Fonctionnalités

- **Résolution de lieux en 4 étapes** : base locale (`lieux_connus`, ~35 000 entrées GeoNames/OSM) → Nominatim → Overpass → clic manuel sur la carte.
- **Itinéraire réel** tracé sur carte (OSRM, sans clé API) avec repli sur plusieurs serveurs publics.
- **Comparateur de devis** : itinéraire réel calculé vs trajet standard connu en base, côte à côte.
- **Moteur de devis** reproduisant fidèlement les formules du fichier Excel d'origine (`core/pricing.py` — ne pas modifier ces formules, y compris le facteur ×4 sur le carburant).
- **Circuit de validation des proformas** : un agent soumet un devis, qui reste sans numéro officiel tant qu'un administrateur ne l'a pas validé (voir [Workflow métier](#workflow-métier--du-devis-à-la-proforma-validée)).
- **Panneau d'administration** : file de validation, historique filtrable des proformas validées, gestion des utilisateurs/rôles, réinitialisation de mot de passe, journal d'audit.
- **Auto-service** : chaque utilisateur peut changer son propre mot de passe (`/mon-compte`) ; demande de réinitialisation depuis la page de connexion si mot de passe oublié, avec notification pour l'admin.
- **Authentification** obligatoire sur toute l'application (y compris l'API JSON), rôles `AGENT` / `ADMIN`.

## Stack technique

- **Backend** : Python 3.11+, Flask 3, Flask-Login (auth), Flask-WTF (protection CSRF)
- **Base de données** : SQLite (`sqlite3` natif, pas d'ORM)
- **Frontend** : HTML / CSS / JavaScript vanilla + Leaflet — aucun framework
- **Routage / géocodage** : OSRM, Nominatim, Overpass (aucune clé API requise)
- **PDF** : ReportLab
- **Recherche approximative** : rapidfuzz
- **Serveur WSGI (prod)** : gunicorn
- **Tests** : pytest

## Architecture du projet

```text
.
├── app.py                       # routes Flask, auth, RBAC, CSRF, orchestration
├── core/
│   ├── db.py                    # accès SQLite : schéma + toutes les requêtes
│   ├── pricing.py                # moteur de calcul du devis (formules Excel — ne pas toucher)
│   ├── devis_service.py          # validation/sérialisation des payloads de devis
│   ├── proforma_pdf.py           # génération du PDF officiel (facture proforma CA TRANS)
│   ├── devis_pdf.py               # ancien générateur PDF, non utilisé par les routes actives
│   ├── routing.py                # OSRM + Nominatim (résolution d'itinéraire)
│   └── osm_overpass.py           # géocodage de secours via Overpass
├── templates/
│   ├── _nav.html                 # barre de navigation partagée (pilule flottante)
│   ├── _admin_subnav.html        # sous-navigation admin partagée
│   ├── index.html                # page principale (calcul de devis)
│   ├── login.html
│   ├── mon_compte.html           # changement de mot de passe en libre-service
│   ├── mes_proformas.html        # suivi des demandes de l'agent connecté
│   ├── admin_proformas.html      # file de validation
│   ├── admin_historique.html     # historique filtrable des proformas validées
│   ├── admin_utilisateurs.html   # gestion utilisateurs/rôles + demandes de réinitialisation
│   ├── admin_audit.html          # journal d'audit
│   └── erreur_403.html
├── static/
│   ├── css/style.css             # design system (tokens d'élévation, radius, nav pilule)
│   ├── js/app.js                 # logique frontend principale (carte, devis, comparateur)
│   └── js/csrf.js                # attache automatiquement le jeton CSRF à chaque fetch()
├── data/
│   ├── ca_trans.db               # base SQLite locale (générée, jamais versionnée — voir .gitignore)
│   ├── seed_trajets.py           # 70 trajets connus, insérés au démarrage si absents
│   ├── seed_lieux.py             # ~35 000 lieux connus, insérés au démarrage si absents
│   ├── lieux_seed.csv            # source de données pour seed_lieux.py
│   ├── import_geonames.py        # script d'import GeoNames (usage ponctuel, hors-ligne)
│   ├── import_osm.py             # script d'import OSM/pyosmium (usage ponctuel, hors-ligne)
│   └── FICHE DE CALCUL CONVOI CA TRANS.xlsx   # fichier Excel d'origine (référence des formules)
├── tests/
│   └── test_app.py               # suite pytest (routes, RBAC, proformas, CSRF, audit...)
├── requirements.txt
├── .env.example
├── Procfile                      # déploiement Render/Heroku (gunicorn app:app)
└── render.yaml                   # config Render
```

> Les dossiers `assets/`, `ui/` et `utils/` à la racine ne contiennent que des `README.md` vestigiaux (aucun code) — le code réel vit dans `core/`, `static/`, `templates/`.

## Rôles & permissions

Deux rôles, stockés dans `utilisateurs.role` :

| Rôle | Peut faire |
|---|---|
| `AGENT` | Rechercher des trajets, calculer des devis, générer un **aperçu** PDF non officiel, soumettre un devis pour validation, suivre ses propres proformas (`/mes-proformas`), changer son mot de passe |
| `ADMIN` | Tout ce que fait `AGENT`, plus : valider/rejeter une proforma (attribution du numéro officiel), gérer les utilisateurs et leurs rôles, réinitialiser un mot de passe, consulter l'historique et le journal d'audit |

Le contrôle d'accès repose sur deux couches (`app.py`) :
- `exiger_connexion()` (`@app.before_request`) : bloque tout accès non authentifié, sauf `/login`, les fichiers statiques et `/api/demande-reinitialisation`.
- `role_requis_api(*roles)` / `role_requis_page(*roles)` : décorateurs appliqués route par route pour les sections réservées aux admins.

**Protection contre le verrouillage** : `core.db.definir_role()` / `supprimer_utilisateur()` refusent de rétrograder ou supprimer le **dernier** compte `ADMIN` (`DernierAdminError`) — sans quoi plus personne ne pourrait accéder au panneau d'administration.

## Workflow métier : du devis à la proforma validée

1. Un agent calcule un devis (`POST /api/devis`) et peut télécharger un **aperçu** PDF non officiel (`POST /api/devis/pdf`) à tout moment — jamais de numéro de proforma dessus, quel que soit le contenu envoyé par le client.
2. Pour officialiser un devis, l'agent le **soumet** (`POST /api/proformas`) : il devient une ligne en base, statut `EN_ATTENTE_VALIDATION`, snapshot JSON du devis (input + résultat) conservé pour régénération fidèle ultérieure.
3. Un administrateur consulte la file (`/admin/proformas`), peut **prévisualiser** le PDF (toujours sans numéro) avant de décider, puis **valide** ou **rejette** (avec motif) :
   - Validation → `POST /admin/proformas/<id>/valider` : attribue le numéro officiel **`PRO-DDMMYY-NNN`** (jour de validation + compteur séquentiel remis à zéro chaque jour, incrémentation atomique via `core.db.prochain_numero_proforma` pour éviter toute collision), statut passe à `VALIDE`.
   - Rejet → `POST /admin/proformas/<id>/rejeter` : statut `REJETE`, motif enregistré, visible par l'agent dans `/mes-proformas`.
4. Le PDF officiel numéroté n'est téléchargeable que via `GET /admin/proformas/<id>/pdf` (réservé aux admins), régénéré de façon déterministe depuis le snapshot JSON stocké (même date d'émission qu'à la soumission).
5. Toutes ces actions (soumission, validation, rejet, connexion, changement de mot de passe, réinitialisation) sont journalisées dans `audit_logs`.

## Installation locale

```bash
git clone <url-du-repo>
cd "Logistique App"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # puis éditez SECRET_KEY et AUTH_USERS (voir ci-dessous)
python app.py
```

L'application est accessible sur `http://localhost:5000`. Au premier démarrage, `init_db()` crée le schéma, `seed_trajets()`/`seed_lieux()` peuplent les trajets et lieux connus (idempotent, ignoré si déjà présent), et `_bootstrap_comptes_env()` crée/synchronise les comptes définis dans `AUTH_USERS`.

## Variables d'environnement

Voir `.env.example` pour un modèle complet.

| Variable | Obligatoire | Description |
|---|---|---|
| `SECRET_KEY` | **Oui en prod** | Clé de session Flask (signe aussi les jetons CSRF). Sans elle, une clé aléatoire est générée au démarrage — les sessions ne survivent pas à un redémarrage. Générer avec `python -c "import secrets; print(secrets.token_hex(32))"`. |
| `AUTH_USERS` | Non (mais nécessaire pour créer le premier admin) | Comptes à créer/synchroniser au démarrage. Format : `user:motdepasse,user2:motdepasse2:ADMIN`. Le mot de passe fait toujours foi (resynchronisé à chaque démarrage). Le rôle (3ᵉ segment, `AGENT` ou `ADMIN`) n'est appliqué que s'il est explicitement présent — sinon un admin promu depuis le panneau n'est jamais rétrogradé silencieusement au redémarrage. |
| `PORT` | Non | Port d'écoute (défaut `5000`). |
| `FLASK_DEBUG` | Non | `1`/`true` pour activer le débogueur interactif Werkzeug en local (`python app.py` uniquement — sans effet derrière gunicorn). **Ne jamais activer en production.** |
| `FORCE_SECURE_COOKIES` | Non | `1`/`true` pour marquer le cookie de session `Secure` (HTTPS uniquement). À activer une fois le domaine de production confirmé en HTTPS (ex. sur Render). Laisser désactivé en local (`http://localhost`), sinon la session ne fonctionne plus. |

## Base de données

SQLite, fichier `data/ca_trans.db` (généré automatiquement, jamais versionné). Tables principales (`core/db.py`) :

- `trajets` — trajets standards connus (origine, destination, distance, montant).
- `lieux_connus` — lieux pour l'autocomplétion (nom, coordonnées, source).
- `utilisateurs` — comptes, mot de passe haché (werkzeug/scrypt), `role`.
- `proformas` — devis soumis, statut, snapshot JSON, numéro officiel une fois validé.
- `proforma_compteurs` — compteur séquentiel journalier pour la numérotation.
- `audit_logs` — journal des actions sensibles.
- `demandes_reinitialisation` — demandes de réinitialisation de mot de passe en attente.

Toutes les fonctions de `core/db.py` suivent le même idiome : `conn: sqlite3.Connection | None = None`, ouverture/fermeture automatique si aucune connexion n'est passée — à respecter pour toute nouvelle fonction.

⚠️ **Sur Render (plan gratuit), le système de fichiers est éphémère** : la base SQLite est réinitialisée à chaque déploiement/redémarrage (voir [Limitations connues](#limitations-connues)).

## Sécurité

Points déjà couverts :

- **Mots de passe** hachés (werkzeug `generate_password_hash`, scrypt), jamais stockés/journalisés en clair.
- **CSRF** : protection active sur toute l'application via Flask-WTF (`CSRFProtect`). Le jeton est déposé dans un cookie lisible par le JS (`csrf_token`, non-httponly) et attaché automatiquement à chaque `fetch()` non-GET par `static/js/csrf.js` (surcharge globale de `window.fetch`, aucun appel à modifier individuellement) ; le formulaire natif de connexion embarque le jeton via un champ caché.
- **Cookies de session** : `HttpOnly` (toujours), `SameSite=Lax` (toujours), `Secure` en option via `FORCE_SECURE_COOKIES` (voir tableau ci-dessus).
- **Autorisation** : décorateurs par rôle sur chaque route sensible (voir [Rôles & permissions](#rôles--permissions)), protection contre la suppression/rétrogradation du dernier admin.
- **Débogueur Werkzeug** désactivé par défaut (`FLASK_DEBUG` opt-in), jamais atteint en production (gunicorn importe l'objet `app` directement, sans passer par `if __name__ == "__main__":`).
- **SQL** : toutes les requêtes utilisent des paramètres liés (`?`), aucune concaténation de valeurs utilisateur dans le texte SQL.

Limitations connues à surveiller :

- **Pas de limitation de débit (rate limiting)** sur `/login` — un attaquant déterminé peut tenter un grand nombre de mots de passe (le hachage scrypt ralentit mais n'empêche pas). À envisager : `flask-limiter`.
- **`request.remote_addr`** (utilisé pour les entrées d'audit et les demandes de réinitialisation) reflète l'IP du proxy Render, pas nécessairement celle du visiteur, sans configuration `ProxyFix` — actuellement non configuré pour éviter tout risque de faire confiance à un en-tête `X-Forwarded-For` mal maîtrisé.
- **`/api/demande-reinitialisation`** est public et non limité en fréquence — peut être spammé (nuisance, pas de fuite de données : la route ne confirme jamais qu'un identifiant existe).

## Tests

```bash
pytest tests/
```

La suite couvre : authentification, RBAC (accès agent vs admin), workflow proforma complet (soumission → prévisualisation → validation/rejet → numérotation), protection du dernier admin, CSRF, changement de mot de passe, audit, migration de schéma sur une base existante.

## Déploiement (Render)

`render.yaml` et `Procfile` sont prêts pour Render (`gunicorn app:app`). Variables d'environnement à définir dans le tableau de bord Render (Settings → Environment) :

- `SECRET_KEY` (obligatoire)
- `AUTH_USERS` avec au moins un compte `:ADMIN` pour pouvoir accéder au panneau d'administration après le premier déploiement
- `FORCE_SECURE_COOKIES=1` une fois le domaine confirmé en HTTPS

## Limitations connues

- **Persistance des données sur Render (plan gratuit)** : le système de fichiers n'est pas persistant entre deux déploiements/redémarrages. `data/ca_trans.db` est recréée à chaque fois (schéma + trajets/lieux réinsérés automatiquement), mais **tout compte créé via le panneau d'administration, toute proforma validée, tout trajet ajouté manuellement, et le journal d'audit sont perdus**. Seuls les comptes définis dans `AUTH_USERS` sont automatiquement recréés. Pour une persistance réelle, passer à un plan Render avec disque persistant, ou externaliser la base (service managé).
- `core/devis_pdf.py` (`generer_pdf_devis`) est un générateur PDF plus simple, non branché sur aucune route active — `core/proforma_pdf.py` (`generer_proforma_pdf`) est le générateur réellement utilisé en production.
- La gestion des trajets connus (`POST/PUT/DELETE /api/trajet/<id>`) n'est pas restreinte au rôle `ADMIN` — tout utilisateur connecté peut modifier la base de trajets standards. C'est un choix fonctionnel actuel, pas un oubli, mais à reconsidérer si ce comportement doit changer.
