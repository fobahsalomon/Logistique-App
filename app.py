"""CA TRANS — Fiche de calcul convoi (API Flask).

Calcul d'itinéraire via OSRM + Nominatim (sans clé API).
Moteur de devis reproduisant exactement les formules Excel d'origine.
"""

import dataclasses
import json
import os
import secrets as secrets_module
from datetime import datetime
from functools import wraps
from io import BytesIO

from flask import Flask, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)

from core.db import (
    DernierAdminError,
    definir_mot_de_passe,
    definir_role,
    enregistrer_audit,
    init_db,
    inserer_lieu,
    inserer_trajet,
    lister_audit_logs,
    lister_proformas_en_attente,
    lister_proformas_historique,
    lister_proformas_par_agent,
    lister_utilisateurs,
    list_trajets,
    mettre_a_jour_trajet,
    creer_proforma,
    obtenir_proforma_par_id,
    obtenir_trajet_par_id,
    obtenir_utilisateur_par_id,
    rechercher_lieux,
    rechercher_trajet,
    rejeter_proforma,
    supprimer_trajet,
    valider_proforma,
    verifier_mot_de_passe,
)
from core.devis_pdf import generer_pdf_devis
from core.devis_service import DevisValidationError, devis_input_from_payload, serialiser_devis
from core.proforma_pdf import generer_proforma_pdf
from core.pricing import calculer_devis, frais_mission_defaut
from core.routing import RoutingError, _geocoder_nominatim, _geocoder_nominatim_multi, calculer_itineraire, get_client, resoudre_itineraire
from data.seed_trajets import seed as seed_trajets

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)

_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    print(
        "ATTENTION : SECRET_KEY non définie — utilisation d'une clé de session "
        "générée aléatoirement (les connexions ne survivront pas à un redémarrage). "
        "À ne jamais laisser ainsi en production, définissez SECRET_KEY."
    )
    _secret_key = secrets_module.token_hex(32)
app.secret_key = _secret_key


def _bootstrap_comptes_env() -> None:
    """Synchronise les comptes définis dans AUTH_USERS (format
    "user:pass,user2:pass2" ou "user:pass:role,...") à chaque démarrage :
    AUTH_USERS fait foi pour le mot de passe, donc un mot de passe changé
    dans la variable d'environnement est repris ici plutôt que de rester
    figé sur la première valeur créée. Ne stocke jamais les mots de passe
    en clair — seul le hash est écrit en base.

    Le rôle n'est appliqué QUE s'il est explicitement présent dans la
    variable d'environnement (3e segment) — sinon le rôle existant en base
    n'est jamais touché, pour ne pas rétrograder silencieusement un admin
    promu depuis le panneau d'administration à chaque redémarrage."""
    brut = os.environ.get("AUTH_USERS", "")
    for paire in brut.split(","):
        paire = paire.strip()
        if not paire or ":" not in paire:
            continue
        segments = paire.split(":")
        username = segments[0].strip()
        password = segments[1].strip() if len(segments) > 1 else ""
        role = segments[2].strip().upper() if len(segments) > 2 else None
        if username and password:
            definir_mot_de_passe(username, password)
            if role in ("AGENT", "ADMIN"):
                definir_role(username, role)


with app.app_context():
    init_db()
    seed_trajets()  # idempotent : n'insère les 70 trajets connus que si absents
    _bootstrap_comptes_env()


class Utilisateur(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.username = row["username"]
        self.role = row["role"]

    @property
    def is_admin(self) -> bool:
        return self.role == "ADMIN"


login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Merci de vous connecter pour accéder à l'application."


@login_manager.user_loader
def charger_utilisateur(user_id: str):
    row = obtenir_utilisateur_par_id(int(user_id))
    return Utilisateur(row) if row else None


@app.before_request
def exiger_connexion():
    """Protège toute l'application par défaut : seules /login et les fichiers
    statiques restent accessibles sans session valide."""
    endpoints_publics = {"login", "static"}
    if request.endpoint in endpoints_publics or current_user.is_authenticated:
        return None
    return login_manager.unauthorized()


def role_requis_api(*roles):
    """Restreint une route JSON aux utilisateurs ayant l'un des rôles donnés."""
    def decorateur(vue):
        @wraps(vue)
        def enveloppe(*args, **kwargs):
            if current_user.role not in roles:
                return jsonify({"erreur": "Accès réservé aux administrateurs."}), 403
            return vue(*args, **kwargs)
        return enveloppe
    return decorateur


def role_requis_page(*roles):
    """Restreint une route HTML aux utilisateurs ayant l'un des rôles donnés."""
    def decorateur(vue):
        @wraps(vue)
        def enveloppe(*args, **kwargs):
            if current_user.role not in roles:
                return render_template("erreur_403.html"), 403
            return vue(*args, **kwargs)
        return enveloppe
    return decorateur


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "GET":
        return render_template("login.html", erreur=None)

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    row = verifier_mot_de_passe(username, password)
    if row is None:
        return render_template("login.html", erreur="Identifiant ou mot de passe incorrect."), 401
    login_user(Utilisateur(row))
    enregistrer_audit(row["id"], "LOGIN", None, request.remote_addr)
    return redirect(request.args.get("next") or url_for("index"))


@app.get("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


def get_api_key() -> str:
    return os.environ.get("ORS_API_KEY", "")


def trajet_en_dict(row) -> dict:
    return {
        "id": row["id"],
        "origine": row["origine"],
        "destination": row["destination"],
        "distance_km": row["distance_km"],
        "montant_aller": row["montant_aller"],
        "source": row["source"],
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/trajets")
def api_trajets():
    return jsonify([trajet_en_dict(r) for r in list_trajets()])


@app.get("/api/frais-mission")
def api_frais_mission():
    nb_jours = request.args.get("jours", default=1, type=int)
    chauffeur, convoyeur = frais_mission_defaut(nb_jours)
    return jsonify({"frais_chauffeur": chauffeur, "frais_convoyeur": convoyeur})


@app.get("/api/lieux")
def api_lieux():
    """Autocomplétion des lieux — cherche dans lieux_connus."""
    q = request.args.get("q", "").strip()
    lieux = rechercher_lieux(q, limit=10)
    return jsonify([
        {"id": l["id"], "nom": l["nom"], "lat": l["latitude"], "lon": l["longitude"]}
        for l in lieux
    ])


@app.get("/api/adresses")
def api_adresses():
    """Recherche d'adresses et de rues via Nominatim, focalisée sur la CI."""
    q = request.args.get("q", "").strip()
    if len(q) < 3:
        return jsonify([])

    try:
        points = _geocoder_nominatim_multi(q, limit=8)
    except Exception:
        return jsonify([])

    return jsonify([
        {
            "label": p.label,
            "lat": p.lat,
            "lon": p.lon,
        }
        for p in points[:8]
    ])


@app.post("/api/lieu")
def api_enregistrer_lieu():
    """Enregistre un lieu nommé manuellement (clic sur la carte)."""
    payload = request.get_json(force=True) or {}
    nom = (payload.get("nom") or "").strip()
    lat = payload.get("lat")
    lon = payload.get("lon")
    if not nom or lat is None or lon is None:
        return jsonify({"erreur": "nom, lat et lon sont requis."}), 400
    lieu_id = inserer_lieu(nom=nom, lat=float(lat), lon=float(lon), source="manuel")
    return jsonify({"id": lieu_id}), 201


@app.get("/api/geocoder")
def api_geocoder():
    """Géocodage en ligne (Nominatim → Overpass) pour complémenter l'autocomplétion locale."""
    q = request.args.get("q", "").strip()
    if len(q) < 3:
        return jsonify([])

    from core.routing import _geocoder_nominatim, RoutingError
    from core.osm_overpass import geocoder_overpass

    # 1. Nominatim
    try:
        point = _geocoder_nominatim(q)
        if point:
            inserer_lieu(nom=q, lat=point.lat, lon=point.lon, source="nominatim")
            label = point.label.split(",")[0].strip()
            return jsonify([{"nom": label, "lat": point.lat, "lon": point.lon, "source": "online"}])
    except RoutingError:
        pass

    # 2. Overpass
    result = geocoder_overpass(q)
    if result:
        inserer_lieu(nom=q, lat=result["lat"], lon=result["lon"], source="overpass")
        return jsonify([{"nom": result["label"], "lat": result["lat"], "lon": result["lon"], "source": "online"}])

    return jsonify([])


@app.post("/api/resoudre")
def api_resoudre():
    payload = request.get_json(force=True) or {}
    origine_texte = (payload.get("origine") or "").strip()
    destination_texte = (payload.get("destination") or "").strip()

    if not origine_texte or not destination_texte:
        return jsonify({"statut": "erreur", "message": "Renseignez l'origine et la destination."}), 400

    trajet_connu = rechercher_trajet(origine_texte, destination_texte)
    if trajet_connu is not None and trajet_connu["distance_km"] is not None:
        return jsonify({
            "statut": "base",
            "distance_km": trajet_connu["distance_km"],
            "message": (
                f"Trajet trouvé en base : {trajet_connu['origine']} → "
                f"{trajet_connu['destination']} ({trajet_connu['distance_km']} km)"
            ),
            "origine_point": None,
            "destination_point": None,
            "geometrie": None,
            "trajet_id": trajet_connu["id"],
            "montant_aller": trajet_connu["montant_aller"],
        })

    try:
        client = get_client()
        o, d, itineraire = resoudre_itineraire(client, origine_texte, destination_texte)
    except RoutingError as exc:
        return jsonify({"statut": "erreur", "message": str(exc)}), 200

    distance_km = round(itineraire.distance_km, 1)
    duree_min = round(itineraire.duree_min)
    return jsonify({
        "statut": "ors",
        "distance_km": distance_km,
        "duree_min": duree_min,
        "message": (
            f"Itinéraire calculé : {o.label} → {d.label} "
            f"({distance_km} km, ~{duree_min} min)"
        ),
        "origine_point": {"lat": o.lat, "lon": o.lon, "label": o.label},
        "destination_point": {"lat": d.lat, "lon": d.lon, "label": d.label},
        "geometrie": itineraire.geometrie,
    })


def _point_to_tuple(point):
    """Normalise les coordonnées des points reçus par l'UI ou l'API.

    L'application peut recevoir `lon`/`lat` ou `lng`/`lat`, selon le client.
    """
    if not isinstance(point, dict):
        return None

    lat = point.get("lat")
    lon = point.get("lon")
    if lon is None:
        lon = point.get("lng")
    if lon is None:
        lon = point.get("longitude")
    if lat is None:
        lat = point.get("latitude")

    if lat is None or lon is None:
        return None

    try:
        return (float(lon), float(lat))
    except (TypeError, ValueError):
        return None


@app.post("/api/itineraire")
def api_itineraire():
    """Calcule l'itinéraire OSRM entre deux points placés manuellement sur la carte."""
    payload = request.get_json(force=True) or {}
    origine = payload.get("origine")
    destination = payload.get("destination")
    if not origine or not destination:
        return jsonify({"statut": "erreur", "message": "Deux points sont requis."}), 400

    origine_coord = _point_to_tuple(origine)
    destination_coord = _point_to_tuple(destination)
    if origine_coord is None or destination_coord is None:
        return jsonify({"statut": "erreur", "message": "Coordonnées invalides pour l'origine ou la destination."}), 400

    try:
        client = get_client()
        itineraire = calculer_itineraire(client, origine_coord, destination_coord)
    except RoutingError as exc:
        return jsonify({"statut": "erreur", "message": str(exc)}), 200

    distance_km = round(itineraire.distance_km, 1)
    duree_min = round(itineraire.duree_min)
    return jsonify({
        "statut": "ors",
        "distance_km": distance_km,
        "duree_min": duree_min,
        "message": f"Itinéraire calculé : {distance_km} km, ~{duree_min} min",
        "geometrie": itineraire.geometrie,
    })


@app.post("/api/trajet")
def api_enregistrer_trajet():
    payload = request.get_json(force=True) or {}
    origine = (payload.get("origine") or "").strip()
    destination = (payload.get("destination") or "").strip()
    distance_km = payload.get("distance_km")
    source = payload.get("source") or "ors"

    if not origine or not destination or distance_km is None:
        return jsonify({"erreur": "origine, destination et distance_km sont requis."}), 400

    trajet_id = inserer_trajet(
        origine=origine, destination=destination, distance_km=distance_km, source=source
    )
    return jsonify({"id": trajet_id}), 201


@app.put("/api/trajet/<int:trajet_id>")
def api_modifier_trajet(trajet_id: int):
    payload = request.get_json(force=True) or {}
    origine = (payload.get("origine") or "").strip()
    destination = (payload.get("destination") or "").strip()
    if not origine or not destination:
        return jsonify({"erreur": "origine et destination sont requis."}), 400
    distance_km = payload.get("distance_km")
    if distance_km is not None:
        try:
            distance_km = float(distance_km)
        except (TypeError, ValueError):
            distance_km = None
    montant_aller = payload.get("montant_aller")
    if montant_aller is not None:
        montant_aller = str(montant_aller).strip() or None
    ok = mettre_a_jour_trajet(trajet_id, origine, destination, distance_km, montant_aller)
    if not ok:
        return jsonify({"erreur": "Trajet introuvable."}), 404
    return jsonify({"ok": True})


@app.delete("/api/trajet/<int:trajet_id>")
def api_supprimer_trajet(trajet_id: int):
    ok = supprimer_trajet(trajet_id)
    if not ok:
        return jsonify({"erreur": "Trajet introuvable."}), 404
    return jsonify({"ok": True})


def _devis_depuis_requete():
    payload = request.get_json(silent=True)
    try:
        entree = devis_input_from_payload(payload)
    except DevisValidationError as exc:
        return None, None, (jsonify({"erreur": f"Paramètres invalides : {exc}"}), 400)
    return payload, entree, None


@app.post("/api/devis")
def api_devis():
    _, entree, erreur = _devis_depuis_requete()
    if erreur:
        return erreur
    return jsonify(serialiser_devis(calculer_devis(entree)))


@app.post("/api/devis/pdf")
def api_devis_pdf():
    """Génère un aperçu PDF non officiel — jamais de numéro de proforma ici,
    quel que soit le contenu du payload (voir /api/proformas pour soumettre
    un devis à validation, et /admin/proformas/<id>/pdf pour le document
    officiel numéroté une fois validé par un administrateur)."""
    payload, entree, erreur = _devis_depuis_requete()
    if erreur:
        return erreur

    resultat = calculer_devis(entree)
    montant_aller = payload.get("montant_aller")
    pdf = generer_proforma_pdf(
        entree,
        resultat,
        origine=payload.get("origine"),
        destination=payload.get("destination"),
        client_nom=payload.get("client_nom", "Client"),
        responsable_flotte=payload.get("responsable_flotte", "GNAYE SARAH"),
        date_debut=payload.get("date_debut"),
        date_fin=payload.get("date_fin"),
        montant_aller_stoque=float(montant_aller) if montant_aller else None,
    )
    return send_file(
        BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="apercu-devis-ca-trans.pdf",
    )


@app.post("/api/proformas")
def api_creer_proforma():
    """Soumet un devis pour validation admin — reste sans numéro officiel
    tant qu'un administrateur ne l'a pas validé."""
    payload, entree, erreur = _devis_depuis_requete()
    if erreur:
        return erreur

    resultat = calculer_devis(entree)
    emis_le = datetime.now().isoformat(timespec="seconds")
    proforma_id = creer_proforma(
        agent_id=current_user.id,
        devis_input_json=json.dumps(dataclasses.asdict(entree)),
        devis_result_json=json.dumps(dataclasses.asdict(resultat)),
        emis_le=emis_le,
        origine=payload.get("origine"),
        destination=payload.get("destination"),
        client_nom=payload.get("client_nom"),
        responsable_flotte=payload.get("responsable_flotte"),
        date_debut=payload.get("date_debut"),
        date_fin=payload.get("date_fin"),
    )
    enregistrer_audit(current_user.id, "DEVIS_SOUMIS", f"proforma #{proforma_id}", request.remote_addr)
    return jsonify({"id": proforma_id, "statut": "EN_ATTENTE_VALIDATION"}), 201


@app.post("/admin/proformas/<int:proforma_id>/valider")
@role_requis_api("ADMIN")
def api_valider_proforma(proforma_id: int):
    numero = valider_proforma(proforma_id, current_user.id)
    if numero is None:
        return jsonify({"erreur": "Cette proforma a déjà été traitée."}), 409
    enregistrer_audit(current_user.id, "PROFORMA_VALIDEE", numero, request.remote_addr)
    return jsonify({"numero_proforma": numero, "statut": "VALIDE"})


@app.post("/admin/proformas/<int:proforma_id>/rejeter")
@role_requis_api("ADMIN")
def api_rejeter_proforma(proforma_id: int):
    payload = request.get_json(force=True, silent=True) or {}
    motif = (payload.get("motif") or "").strip() or None
    ok = rejeter_proforma(proforma_id, current_user.id, motif)
    if not ok:
        return jsonify({"erreur": "Cette proforma a déjà été traitée."}), 409
    enregistrer_audit(current_user.id, "PROFORMA_REJETEE", motif, request.remote_addr)
    return jsonify({"statut": "REJETE"})


@app.get("/admin/proformas")
@role_requis_page("ADMIN")
def page_proformas_en_attente():
    return render_template("admin_proformas.html", proformas=lister_proformas_en_attente())


@app.get("/admin/proformas/historique")
@role_requis_page("ADMIN")
def page_proformas_historique():
    filtres = {
        "numero": request.args.get("numero") or None,
        "date_debut": request.args.get("date_debut") or None,
        "date_fin": request.args.get("date_fin") or None,
        "agent_username": request.args.get("agent") or None,
        "client_nom": request.args.get("client") or None,
        "trajet": request.args.get("trajet") or None,
    }
    return render_template(
        "admin_historique.html",
        proformas=lister_proformas_historique(**filtres),
        filtres=request.args,
    )


def _reconstituer_devis(row):
    from core.pricing import DevisInput, DevisResult

    entree = DevisInput(**json.loads(row["devis_input_json"]))
    resultat = DevisResult(**json.loads(row["devis_result_json"]))
    return entree, resultat


@app.get("/admin/proformas/<int:proforma_id>/pdf")
@role_requis_page("ADMIN")
def page_proforma_pdf(proforma_id: int):
    row = obtenir_proforma_par_id(proforma_id)
    if row is None or row["statut"] != "VALIDE":
        return render_template("erreur_403.html"), 404

    entree, resultat = _reconstituer_devis(row)
    pdf = generer_proforma_pdf(
        entree,
        resultat,
        origine=row["origine"],
        destination=row["destination"],
        numero_proforma=row["numero_proforma"],
        client_nom=row["client_nom"] or "Client",
        responsable_flotte=row["responsable_flotte"] or "GNAYE SARAH",
        date_debut=row["date_debut"],
        date_fin=row["date_fin"],
        emis_le=datetime.fromisoformat(row["emis_le"]),
    )
    return send_file(
        BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"proforma-{row['numero_proforma']}.pdf",
    )


@app.get("/admin/proformas/<int:proforma_id>/preview")
@role_requis_page("ADMIN")
def page_proforma_preview(proforma_id: int):
    """Aperçu du PDF avant validation — jamais de numéro officiel, quel que
    soit le statut de la proforma (toujours rendu comme "APERÇU — NON
    VALIDÉ", y compris pour relire une proforma déjà rejetée)."""
    row = obtenir_proforma_par_id(proforma_id)
    if row is None or row["statut"] == "VALIDE":
        return render_template("erreur_403.html"), 404

    entree, resultat = _reconstituer_devis(row)
    pdf = generer_proforma_pdf(
        entree,
        resultat,
        origine=row["origine"],
        destination=row["destination"],
        client_nom=row["client_nom"] or "Client",
        responsable_flotte=row["responsable_flotte"] or "GNAYE SARAH",
        date_debut=row["date_debut"],
        date_fin=row["date_fin"],
        emis_le=datetime.fromisoformat(row["emis_le"]),
    )
    return send_file(
        BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=False,
        download_name=f"apercu-proforma-{proforma_id}.pdf",
    )


@app.get("/admin/utilisateurs")
@role_requis_page("ADMIN")
def page_utilisateurs():
    return render_template("admin_utilisateurs.html", utilisateurs=lister_utilisateurs())


@app.post("/admin/utilisateurs/<int:user_id>/reinitialiser-mot-de-passe")
@role_requis_api("ADMIN")
def api_reinitialiser_mot_de_passe(user_id: int):
    payload = request.get_json(force=True, silent=True) or {}
    nouveau_mdp = (payload.get("password") or "").strip()
    if not nouveau_mdp:
        return jsonify({"erreur": "Nouveau mot de passe requis."}), 400
    row = obtenir_utilisateur_par_id(user_id)
    if row is None:
        return jsonify({"erreur": "Utilisateur introuvable."}), 404
    definir_mot_de_passe(row["username"], nouveau_mdp)
    enregistrer_audit(current_user.id, "MOT_DE_PASSE_REINITIALISE", row["username"], request.remote_addr)
    return jsonify({"ok": True})


@app.post("/admin/utilisateurs/<int:user_id>/role")
@role_requis_api("ADMIN")
def api_changer_role(user_id: int):
    payload = request.get_json(force=True, silent=True) or {}
    role = (payload.get("role") or "").strip().upper()
    if role not in ("AGENT", "ADMIN"):
        return jsonify({"erreur": "Rôle invalide."}), 400
    row = obtenir_utilisateur_par_id(user_id)
    if row is None:
        return jsonify({"erreur": "Utilisateur introuvable."}), 404
    try:
        definir_role(row["username"], role)
    except DernierAdminError as exc:
        return jsonify({"erreur": str(exc)}), 409
    enregistrer_audit(current_user.id, "ROLE_MODIFIE", f"{row['username']} -> {role}", request.remote_addr)
    return jsonify({"ok": True})


@app.get("/admin/audit")
@role_requis_page("ADMIN")
def page_audit():
    return render_template("admin_audit.html", logs=lister_audit_logs())


@app.get("/mes-proformas")
def page_mes_proformas():
    """Vue agent : suivi de ses propres devis soumis, avec statut et motif
    de rejet éventuel — accessible à tout utilisateur connecté (AGENT ou
    ADMIN), pas seulement aux administrateurs."""
    return render_template("mes_proformas.html", proformas=lister_proformas_par_agent(current_user.id))


@app.get("/mon-compte")
def page_mon_compte():
    return render_template("mon_compte.html")


@app.post("/mon-compte/changement-mot-de-passe")
def api_changer_mon_mot_de_passe():
    payload = request.get_json(force=True, silent=True) or {}
    ancien = payload.get("ancien_mot_de_passe") or ""
    nouveau = payload.get("nouveau_mot_de_passe") or ""
    confirmation = payload.get("confirmation") or ""

    if not ancien or not nouveau or not confirmation:
        return jsonify({"erreur": "Tous les champs sont requis."}), 400
    if len(nouveau) < 8:
        return jsonify({"erreur": "Le nouveau mot de passe doit contenir au moins 8 caractères."}), 400
    if nouveau != confirmation:
        return jsonify({"erreur": "La confirmation ne correspond pas au nouveau mot de passe."}), 400
    if verifier_mot_de_passe(current_user.username, ancien) is None:
        return jsonify({"erreur": "Mot de passe actuel incorrect."}), 403

    definir_mot_de_passe(current_user.username, nouveau)
    enregistrer_audit(current_user.id, "MOT_DE_PASSE_CHANGE", None, request.remote_addr)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
