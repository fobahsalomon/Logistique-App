"""Routage via OSRM (serveur public) + géocodage Nominatim.

Aucune clé API requise. Nominatim impose max 1 requête/seconde :
on insère un sleep entre les deux appels de géocodage.
"""

import time
from dataclasses import dataclass

import requests

OSRM_BASE = "http://router.project-osrm.org"
NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
_UA = "CA-TRANS-Devis/1.0"


class RoutingError(Exception):
    """Erreur lors du géocodage ou du calcul d'itinéraire."""


@dataclass
class PointGeocode:
    lat: float
    lon: float
    label: str


@dataclass
class Itineraire:
    distance_km: float
    duree_min: float
    geometrie: dict  # GeoJSON LineString


def get_client(api_key: str = ""):
    """Aucune clé requise avec OSRM/Nominatim. Retourne None."""
    return None


def geocoder(client, texte: str) -> PointGeocode | None:
    """Géocode un lieu via Nominatim, limité à la Côte d'Ivoire."""
    try:
        rep = requests.get(
            f"{NOMINATIM_BASE}/search",
            params={"q": texte, "format": "json", "limit": 1,
                    "countrycodes": "ci", "accept-language": "fr"},
            headers={"User-Agent": _UA},
            timeout=10,
        )
        rep.raise_for_status()
        data = rep.json()
        if not data:
            return None
        r = data[0]
        return PointGeocode(lat=float(r["lat"]), lon=float(r["lon"]),
                            label=r.get("display_name", texte))
    except RoutingError:
        raise
    except Exception as exc:
        raise RoutingError(f"Géocodage échoué pour « {texte} » : {exc}") from exc


def calculer_itineraire(client, origine: tuple, destination: tuple) -> Itineraire:
    """Calcule l'itinéraire routier via OSRM entre deux points (lon, lat)."""
    o_lon, o_lat = origine
    d_lon, d_lat = destination
    coords = f"{o_lon},{o_lat};{d_lon},{d_lat}"
    try:
        rep = requests.get(
            f"{OSRM_BASE}/route/v1/driving/{coords}",
            params={"overview": "full", "geometries": "geojson"},
            timeout=15,
        )
        rep.raise_for_status()
        data = rep.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            raise RoutingError(f"OSRM : pas de route trouvée ({data.get('code')})")
        route = data["routes"][0]
        return Itineraire(
            distance_km=route["distance"] / 1000,
            duree_min=route["duration"] / 60,
            geometrie=route["geometry"],
        )
    except RoutingError:
        raise
    except Exception as exc:
        raise RoutingError(f"Calcul d'itinéraire échoué : {exc}") from exc


def resoudre_itineraire(client, origine_texte: str, destination_texte: str):
    """Géocode les deux lieux puis calcule l'itinéraire."""
    o = geocoder(client, origine_texte)
    if o is None:
        raise RoutingError(f"Origine introuvable : « {origine_texte} »")
    # Nominatim exige max 1 req/s
    time.sleep(1.1)
    d = geocoder(client, destination_texte)
    if d is None:
        raise RoutingError(f"Destination introuvable : « {destination_texte} »")
    itineraire = calculer_itineraire(client, (o.lon, o.lat), (d.lon, d.lat))
    return o, d, itineraire
