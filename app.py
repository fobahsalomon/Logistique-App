"""CA TRANS — Fiche de calcul convoi (API Flask).

Calcul d'itinéraire via OSRM + Nominatim (sans clé API).
Moteur de devis reproduisant exactement les formules Excel d'origine.
"""

import os
import secrets as secrets_module
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
    creer_utilisateur,
    init_db,
    inserer_lieu,
    inserer_trajet,
    list_trajets,
    mettre_a_jour_trajet,
    obtenir_utilisateur_par_id,
    rechercher_lieux,
    rechercher_trajet,
    supprimer_trajet,
    verifier_mot_de_passe,
)
from core.devis_pdf import generer_pdf_devis
from core.devis_service import DevisValidationError, devis_input_from_payload, serialiser_devis
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
    """Crée les comptes définis dans AUTH_USERS (format "user:pass,user2:pass2")
    s'ils n'existent pas déjà. Ne stocke jamais les mots de passe en clair —
    seul le hash est écrit en base."""
    brut = os.environ.get("AUTH_USERS", "")
    for paire in brut.split(","):
        paire = paire.strip()
        if not paire or ":" not in paire:
            continue
        username, _, password = paire.partition(":")
        username, password = username.strip(), password.strip()
        if username and password:
            creer_utilisateur(username, password)


with app.app_context():
    init_db()
    seed_trajets()  # idempotent : n'insère les 70 trajets connus que si absents
    _bootstrap_comptes_env()


class Utilisateur(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.username = row["username"]


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


@app.post("/api/itineraire")
def api_itineraire():
    """Calcule l'itinéraire OSRM entre deux points placés manuellement sur la carte."""
    payload = request.get_json(force=True) or {}
    origine = payload.get("origine")
    destination = payload.get("destination")
    if not origine or not destination:
        return jsonify({"statut": "erreur", "message": "Deux points sont requis."}), 400

    try:
        client = get_client()
        itineraire = calculer_itineraire(
            client, (origine["lon"], origine["lat"]), (destination["lon"], destination["lat"])
        )
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
    payload, entree, erreur = _devis_depuis_requete()
    if erreur:
        return erreur

    resultat = calculer_devis(entree)
    pdf = generer_pdf_devis(
        entree,
        resultat,
        origine=payload.get("origine"),
        destination=payload.get("destination"),
    )
    return send_file(
        BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="devis-ca-trans.pdf",
    )


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
