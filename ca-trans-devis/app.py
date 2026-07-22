"""CA TRANS — Fiche de calcul convoi.

Application Streamlit qui remplace la recherche manuelle de distance sur
Google Maps par un calcul d'itinéraire fiable (OpenRouteService, profil
poids lourd) et reproduit le moteur de calcul de devis de l'Excel original.
"""

import sys
from pathlib import Path

import folium
import streamlit as st
from streamlit_folium import st_folium

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.db import init_db, inserer_trajet, list_trajets, rechercher_trajet
from core.pricing import DevisInput, calculer_devis, frais_mission_defaut
from core.routing import RoutingError, get_client, resoudre_itineraire
from data.seed_trajets import seed as seed_trajets

CI_CENTER = (7.5399, -5.5471)

st.set_page_config(page_title="CA TRANS — Fiche de calcul convoi", layout="wide")
init_db()
seed_trajets()  # idempotent : n'insère les 70 trajets connus que si absents


def get_api_key() -> str:
    try:
        cle = st.secrets.get("ors_api_key", "")
    except Exception:
        cle = ""  # pas de secrets.toml (ex: premier lancement local)
    if not cle:
        cle = st.session_state.get("ors_api_key_manuel", "")
    return cle


def init_session_state():
    defaults = {
        "origine_texte": "",
        "destination_texte": "",
        "origine_point": None,  # (lat, lon)
        "destination_point": None,
        "distance_km": None,
        "duree_min": None,
        "geometrie": None,
        "statut": None,  # "base" | "ors" | "manuel" | "erreur"
        "statut_message": "",
        "mode_clic": "Origine",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_session_state()

st.title("CA TRANS — Fiche de calcul convoi")
st.caption("Résolution d'itinéraire fiable (OpenRouteService, profil poids lourd) + moteur de devis")

col_main, col_side = st.columns([1.6, 1])

# ---------------------------------------------------------------------------
# Colonne principale : carte + résolution d'itinéraire
# ---------------------------------------------------------------------------
with col_main:
    st.subheader("Trajet")

    c1, c2 = st.columns(2)
    with c1:
        st.session_state["origine_texte"] = st.text_input(
            "Origine", value=st.session_state["origine_texte"], placeholder="Ex: San Pedro"
        )
    with c2:
        st.session_state["destination_texte"] = st.text_input(
            "Destination", value=st.session_state["destination_texte"], placeholder="Ex: Abidjan"
        )

    bouton_resoudre = st.button("Résoudre l'itinéraire", type="primary")

    if bouton_resoudre:
        origine_texte = st.session_state["origine_texte"].strip()
        destination_texte = st.session_state["destination_texte"].strip()

        if not origine_texte or not destination_texte:
            st.session_state["statut"] = "erreur"
            st.session_state["statut_message"] = "Renseignez l'origine et la destination."
        else:
            trajet_connu = rechercher_trajet(origine_texte, destination_texte)
            if trajet_connu is not None and trajet_connu["distance_km"] is not None:
                st.session_state["distance_km"] = trajet_connu["distance_km"]
                st.session_state["duree_min"] = None
                st.session_state["geometrie"] = None
                st.session_state["origine_point"] = None
                st.session_state["destination_point"] = None
                st.session_state["statut"] = "base"
                st.session_state["statut_message"] = (
                    f"Trajet trouvé en base : {trajet_connu['origine']} → "
                    f"{trajet_connu['destination']} ({trajet_connu['distance_km']} km)"
                )
            else:
                api_key = get_api_key()
                try:
                    client = get_client(api_key)
                    o, d, itineraire = resoudre_itineraire(client, origine_texte, destination_texte)
                    st.session_state["distance_km"] = round(itineraire.distance_km, 1)
                    st.session_state["duree_min"] = round(itineraire.duree_min, 0)
                    st.session_state["geometrie"] = itineraire.geometrie
                    st.session_state["origine_point"] = (o.lat, o.lon)
                    st.session_state["destination_point"] = (d.lat, d.lon)
                    st.session_state["statut"] = "ors"
                    st.session_state["statut_message"] = (
                        f"Itinéraire calculé via OpenRouteService : {o.label} → {d.label} "
                        f"({st.session_state['distance_km']} km, ~{int(st.session_state['duree_min'])} min)"
                    )
                except RoutingError as exc:
                    st.session_state["statut"] = "erreur"
                    st.session_state["statut_message"] = str(exc)
                    st.session_state["distance_km"] = None

    # --- Statut de résolution ---
    statut = st.session_state["statut"]
    if statut == "base":
        st.success(st.session_state["statut_message"])
    elif statut == "ors":
        st.info(st.session_state["statut_message"])
    elif statut == "erreur":
        st.warning(st.session_state["statut_message"])

    if statut == "erreur" or (bouton_resoudre and st.session_state["distance_km"] is None):
        st.markdown("**Destination introuvable : saisissez la distance manuellement.**")
        distance_manuelle = st.number_input(
            "Distance aller simple (km)", min_value=0.0, step=1.0, key="distance_manuelle"
        )
        if st.button("Utiliser cette distance"):
            st.session_state["distance_km"] = distance_manuelle
            st.session_state["statut"] = "manuel"
            st.session_state["statut_message"] = f"Distance saisie manuellement : {distance_manuelle} km"
            st.rerun()

    # --- Carte interactive ---
    st.session_state["mode_clic"] = st.radio(
        "Point à placer au prochain clic sur la carte", ["Origine", "Destination"], horizontal=True
    )

    carte = folium.Map(location=CI_CENTER, zoom_start=7, tiles="OpenStreetMap")

    if st.session_state["origine_point"]:
        folium.Marker(
            st.session_state["origine_point"],
            tooltip="Origine",
            icon=folium.Icon(color="green", icon="play"),
        ).add_to(carte)
    if st.session_state["destination_point"]:
        folium.Marker(
            st.session_state["destination_point"],
            tooltip="Destination",
            icon=folium.Icon(color="red", icon="stop"),
        ).add_to(carte)
    if st.session_state["geometrie"]:
        folium.GeoJson(
            st.session_state["geometrie"],
            style_function=lambda _: {"color": "#1f77b4", "weight": 5, "opacity": 0.8},
        ).add_to(carte)

    resultat_carte = st_folium(carte, height=460, width=None, key="carte_principale")

    if resultat_carte and resultat_carte.get("last_clicked"):
        lat = resultat_carte["last_clicked"]["lat"]
        lon = resultat_carte["last_clicked"]["lng"]
        if st.session_state["mode_clic"] == "Origine":
            st.session_state["origine_point"] = (lat, lon)
        else:
            st.session_state["destination_point"] = (lat, lon)

    if st.session_state["origine_point"] and st.session_state["destination_point"]:
        if st.button("Calculer l'itinéraire entre ces deux points de carte"):
            api_key = get_api_key()
            try:
                from core.routing import calculer_itineraire

                client = get_client(api_key)
                o_lat, o_lon = st.session_state["origine_point"]
                d_lat, d_lon = st.session_state["destination_point"]
                itineraire = calculer_itineraire(client, (o_lon, o_lat), (d_lon, d_lat))
                st.session_state["distance_km"] = round(itineraire.distance_km, 1)
                st.session_state["duree_min"] = round(itineraire.duree_min, 0)
                st.session_state["geometrie"] = itineraire.geometrie
                st.session_state["statut"] = "ors"
                st.session_state["statut_message"] = (
                    f"Itinéraire calculé via OpenRouteService (points carte) : "
                    f"{st.session_state['distance_km']} km, ~{int(st.session_state['duree_min'])} min"
                )
                st.rerun()
            except RoutingError as exc:
                st.warning(str(exc))

    if st.session_state["distance_km"] and st.session_state["statut"] in ("ors", "manuel"):
        if st.button("Enregistrer ce trajet dans la base"):
            inserer_trajet(
                origine=st.session_state["origine_texte"] or "Point carte",
                destination=st.session_state["destination_texte"] or "Point carte",
                distance_km=st.session_state["distance_km"],
                montant_aller=None,
                source="ors" if st.session_state["statut"] == "ors" else "manuel",
            )
            st.success("Trajet enregistré dans la base.")

    if not get_api_key():
        with st.expander("Clé API OpenRouteService non configurée"):
            st.write(
                "Aucune clé trouvée dans `.streamlit/secrets.toml`. "
                "Vous pouvez en saisir une temporairement ci-dessous (non sauvegardée)."
            )
            st.text_input("Clé API ORS", type="password", key="ors_api_key_manuel")

# ---------------------------------------------------------------------------
# Colonne latérale : paramètres du voyage + fiche de devis
# ---------------------------------------------------------------------------
with col_side:
    st.subheader("Paramètres du voyage")

    nb_places = st.number_input("Nombre de places souhaitées", min_value=1, value=63, step=1)
    nb_jours = st.radio("Nombre de jours avec le véhicule", [1, 2], horizontal=True)
    frais_chauffeur_defaut, frais_convoyeur_defaut = frais_mission_defaut(nb_jours)

    conso_100km = st.number_input("Consommation / 100 km (L)", min_value=0.0, value=35.0, step=1.0)
    prix_litre = st.number_input("Prix du litre (F CFA)", min_value=0.0, value=700.0, step=10.0)
    frais_chauffeur = st.number_input(
        "Frais de mission chauffeur (F CFA)", min_value=0.0, value=float(frais_chauffeur_defaut), step=500.0
    )
    frais_convoyeur = st.number_input(
        "Frais de mission convoyeur (F CFA)", min_value=0.0, value=float(frais_convoyeur_defaut), step=500.0
    )
    peage = st.number_input("Péage (F CFA)", min_value=0.0, value=0.0, step=500.0)
    marge_pct = st.number_input("Marge souhaitée (%)", min_value=0.0, value=10.0, step=1.0)
    remise_montant = st.number_input("Remise (montant en F CFA)", min_value=0.0, value=0.0, step=500.0)

    distance_km = st.session_state["distance_km"]

    st.divider()
    st.subheader("Fiche de devis")

    if not distance_km:
        st.info("Résolvez d'abord un itinéraire pour obtenir la distance.")
    else:
        entree = DevisInput(
            distance_km=distance_km,
            nb_places=int(nb_places),
            conso_100km=conso_100km,
            prix_litre=prix_litre,
            frais_chauffeur=frais_chauffeur,
            frais_convoyeur=frais_convoyeur,
            peage=peage,
            marge_pct=marge_pct,
            remise_montant=remise_montant,
        )
        r = calculer_devis(entree)

        def fcfa(v: float) -> str:
            return f"{v:,.2f}".replace(",", " ").replace(".", ",") + " F CFA"

        st.metric("Distance aller simple", f"{distance_km} km")
        st.write(f"**Consommation totale :** {r.consommation_totale:.2f} L")
        st.write(f"**Coût carburant :** {fcfa(r.cout_carburant)}")
        st.write(f"**Coût carburant × 4 (facturé) :** {fcfa(r.cout_carburant_x4)}")
        st.write(f"**Total autres frais :** {fcfa(r.total_autres_frais)}")
        st.write(f"**Coût de revient total :** {fcfa(r.cout_revient_total)}")
        st.write(f"**Marge ({marge_pct:.0f} %) :** {fcfa(r.marge)}")
        st.write(f"**Prix de vente aller simple :** {fcfa(r.prix_vente_aller)}")
        st.write(f"**Montant HT aller-retour :** {fcfa(r.ht_aller_retour)}")
        st.write(f"**TVA (18 %) :** {fcfa(r.tva)}")
        st.write(f"**TTC aller-retour :** {fcfa(r.ttc_aller_retour)}")
        st.write(f"**TTC après remise :** {fcfa(r.ttc_apres_remise)}")
        st.markdown(f"### TTC aller simple : {fcfa(r.ttc_aller_simple)}")

        st.markdown("**Prix par place (aller simple, sans TVA) :**")
        lignes = []
        for n in sorted(r.prix_par_place):
            lignes.append({"Places": n, "Prix / place (F CFA)": round(r.prix_par_place[n], 2)})
        st.dataframe(lignes, hide_index=True, width='stretch')
        st.write(f"**58 places × 2 (VIP, sans TVA) :** {fcfa(r.prix_par_place_vip_58)}")

# ---------------------------------------------------------------------------
# Base de trajets connus
# ---------------------------------------------------------------------------
with st.expander("Base de trajets connus"):
    trajets = list_trajets()
    filtre = st.text_input("Filtrer (origine ou destination)", key="filtre_trajets")
    lignes_trajets = [dict(row) for row in trajets]
    if filtre:
        f = filtre.strip().lower()
        lignes_trajets = [
            row for row in lignes_trajets
            if f in row["origine"].lower() or f in row["destination"].lower()
        ]

    evenement = st.dataframe(
        lignes_trajets,
        hide_index=True,
        width='stretch',
        on_select="rerun",
        selection_mode="single-row",
        key="table_trajets",
    )

    lignes_selectionnees = evenement.selection.rows if evenement and evenement.selection else []
    if lignes_selectionnees:
        ligne = lignes_trajets[lignes_selectionnees[0]]
        st.session_state["origine_texte"] = ligne["origine"]
        st.session_state["destination_texte"] = ligne["destination"]
        if ligne["distance_km"]:
            st.session_state["distance_km"] = ligne["distance_km"]
            st.session_state["statut"] = "base"
            st.session_state["statut_message"] = (
                f"Trajet réutilisé : {ligne['origine']} → {ligne['destination']} ({ligne['distance_km']} km)"
            )
        st.rerun()
