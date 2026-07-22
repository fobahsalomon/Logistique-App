"""Appels à OpenRouteService : géocodage et calcul d'itinéraire poids lourd.

Profil utilisé : `driving-hgv` (poids lourd), qui exclut les routes interdites
aux gros véhicules — contrairement à un itinéraire piéton/voiture classique.
"""

from dataclasses import dataclass

import openrouteservice
from openrouteservice.exceptions import ApiError

PROFIL_CAR = "driving-hgv"

# Zone de recherche par défaut : Côte d'Ivoire (pour focaliser le géocodage)
CI_FOCUS_POINT = (-5.5471, 7.5399)  # (lon, lat) approx. centre du pays


@dataclass
class PointGeocode:
    label: str
    lon: float
    lat: float


@dataclass
class Itineraire:
    distance_km: float
    duree_min: float
    geometrie: dict  # GeoJSON LineString


class RoutingError(Exception):
    """Erreur lors du géocodage ou du calcul d'itinéraire."""


def get_client(api_key: str) -> openrouteservice.Client:
    if not api_key:
        raise RoutingError("Clé API OpenRouteService manquante.")
    return openrouteservice.Client(key=api_key)


def geocoder(client: openrouteservice.Client, texte: str) -> PointGeocode | None:
    """Géocode un texte libre (nom de lieu) en coordonnées via Pelias."""
    try:
        resultat = client.pelias_search(
            text=texte,
            focus_point=CI_FOCUS_POINT,
            country="CIV",
            size=1,
        )
    except ApiError as exc:
        raise RoutingError(f"Erreur de géocodage pour « {texte} » : {exc}") from exc

    features = resultat.get("features") or []
    if not features:
        return None

    feature = features[0]
    lon, lat = feature["geometry"]["coordinates"]
    label = feature["properties"].get("label", texte)
    return PointGeocode(label=label, lon=lon, lat=lat)


def calculer_itineraire(
    client: openrouteservice.Client,
    origine: tuple[float, float],
    destination: tuple[float, float],
) -> Itineraire:
    """Calcule l'itinéraire routier réel (profil poids lourd) entre deux points (lon, lat)."""
    try:
        resultat = client.directions(
            coordinates=[list(origine), list(destination)],
            profile=PROFIL_CAR,
            format="geojson",
        )
    except ApiError as exc:
        raise RoutingError(f"Erreur de calcul d'itinéraire : {exc}") from exc

    feature = resultat["features"][0]
    summary = feature["properties"]["summary"]
    distance_km = summary["distance"] / 1000
    duree_min = summary["duration"] / 60

    return Itineraire(
        distance_km=distance_km,
        duree_min=duree_min,
        geometrie=feature["geometry"],
    )


def resoudre_itineraire(
    client: openrouteservice.Client, origine_texte: str, destination_texte: str
) -> tuple[PointGeocode, PointGeocode, Itineraire]:
    """Géocode origine et destination puis calcule l'itinéraire routier entre les deux.

    Lève RoutingError si l'une des deux destinations est introuvable.
    """
    o = geocoder(client, origine_texte)
    if o is None:
        raise RoutingError(f"Origine introuvable : « {origine_texte} ».")

    d = geocoder(client, destination_texte)
    if d is None:
        raise RoutingError(f"Destination introuvable : « {destination_texte} ».")

    itineraire = calculer_itineraire(client, (o.lon, o.lat), (d.lon, d.lat))
    return o, d, itineraire
