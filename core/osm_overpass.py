"""Géocodage de secours via Overpass API (OpenStreetMap).

Utilisé quand ni la base locale ni Nominatim ne trouvent un lieu.
Le résultat est automatiquement sauvegardé dans lieux_connus par l'appelant.
"""

import re
import time

import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_UA = "CA-TRANS-Devis/1.0"
_last_overpass_call: float = 0.0

# Bounding box Côte d'Ivoire : south,west,north,east
_CI_BBOX = "4.0,-8.6,10.8,-2.4"


def geocoder_overpass(texte: str) -> dict | None:
    """Cherche un lieu nommé dans OSM via Overpass API.

    Retourne {"lat": float, "lon": float, "label": str} ou None.
    Ne lève pas d'exception — Overpass est un fallback, pas une source primaire.
    """
    global _last_overpass_call
    elapsed = time.time() - _last_overpass_call
    if elapsed < 1.5:
        time.sleep(1.5 - elapsed)

    # Échappe les caractères spéciaux regex sauf lettres/espaces
    nom_esc = re.sub(r'[\\^$.|?*+(){}\[\]]', ".", texte)

    query = (
        f'[out:json][timeout:12][bbox:{_CI_BBOX}];\n'
        f'(\n'
        f'  node["place"]["name"~"{nom_esc}",i];\n'
        f'  node["amenity"="bus_station"]["name"~"{nom_esc}",i];\n'
        f'  way["place"]["name"~"{nom_esc}",i];\n'
        f');\n'
        f'out center 5;'
    )

    try:
        rep = requests.post(
            OVERPASS_URL,
            data={"data": query},
            headers={"User-Agent": _UA},
            timeout=15,
        )
        _last_overpass_call = time.time()
        rep.raise_for_status()
        elements = rep.json().get("elements", [])
        if not elements:
            return None
        # Trier par longueur du nom (plus court = correspondance plus précise)
        elements.sort(key=lambda e: len(e.get("tags", {}).get("name", "")))
        el = elements[0]
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        nom = el.get("tags", {}).get("name", texte)
        if lat is None or lon is None:
            return None
        return {"lat": float(lat), "lon": float(lon), "label": nom}
    except Exception:
        return None
