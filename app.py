"""CA TRANS — Fiche de calcul convoi (API Flask).

Calcul d'itinéraire via OSRM + Nominatim (sans clé API).
Moteur de devis reproduisant exactement les formules Excel d'origine.
"""

import os
from dataclasses import asdict

from flask import Flask, jsonify, render_template, request

from core.db import (
    init_db,
    inserer_lieu,
    inserer_trajet,
    list_trajets,
    mettre_a_jour_trajet,
    rechercher_lieux,
    rechercher_trajet,
    supprimer_trajet,
)
from core.pricing import DevisInput, calculer_devis, frais_mission_defaut
from core.routing import RoutingError, calculer_itineraire, get_client, resoudre_itineraire
from data.seed_trajets import seed as seed_trajets

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)

with app.app_context():
    init_db()
    seed_trajets()  # idempotent : n'insère les 70 trajets connus que si absents


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


@app.post("/api/devis")
def api_devis():
    payload = request.get_json(force=True) or {}
    try:
        entree = DevisInput(
            distance_km=float(payload["distance_km"]),
            nb_places=int(payload.get("nb_places", 63)),
            conso_100km=float(payload.get("conso_100km", 35)),
            prix_litre=float(payload.get("prix_litre", 700)),
            frais_chauffeur=float(payload.get("frais_chauffeur", 12000)),
            frais_convoyeur=float(payload.get("frais_convoyeur", 5000)),
            peage=float(payload.get("peage", 0)),
            marge_pct=float(payload.get("marge_pct", 10)),
            remise_montant=float(payload.get("remise_montant", 0)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({"erreur": f"Paramètres invalides : {exc}"}), 400

    resultat = calculer_devis(entree)
    resultat_json = asdict(resultat)
    resultat_json["prix_par_place"] = [
        {"places": n, "prix": v} for n, v in sorted(resultat.prix_par_place.items())
    ]
    return jsonify(resultat_json)


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
