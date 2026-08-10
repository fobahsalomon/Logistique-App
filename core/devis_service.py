"""Validation et sérialisation communes des devis CA TRANS."""

from dataclasses import asdict
from math import isfinite
from typing import Any

from core.pricing import DevisInput, DevisResult

CAPACITES_CAR = (63, 58, 51, 49)


class DevisValidationError(ValueError):
    """Erreur de paramètres envoyés pour un devis."""


def _nombre(payload: dict[str, Any], nom: str, default: float | None = None) -> float:
    valeur = payload.get(nom, default)
    if valeur is None:
        raise DevisValidationError(f"Le paramètre {nom} est requis.")
    try:
        nombre = float(valeur)
    except (TypeError, ValueError) as exc:
        raise DevisValidationError(f"Le paramètre {nom} doit être numérique.") from exc
    if not isfinite(nombre):
        raise DevisValidationError(f"Le paramètre {nom} doit être un nombre fini.")
    if nombre < 0:
        raise DevisValidationError(f"Le paramètre {nom} ne peut pas être négatif.")
    return nombre


def devis_input_from_payload(payload: dict[str, Any]) -> DevisInput:
    """Construit une entrée valide depuis les paramètres API d'un devis."""
    if not isinstance(payload, dict):
        raise DevisValidationError("Le corps de la requête doit être un objet JSON.")

    distance_km = _nombre(payload, "distance_km")
    if distance_km <= 0:
        raise DevisValidationError("La distance_km doit être supérieure à zéro.")

    try:
        nb_places = int(payload.get("nb_places", 63))
    except (TypeError, ValueError) as exc:
        raise DevisValidationError("Le paramètre nb_places doit être un entier.") from exc
    if nb_places not in CAPACITES_CAR:
        capacites = ", ".join(str(capacite) for capacite in CAPACITES_CAR)
        raise DevisValidationError(f"Le nombre de places doit être l'une des valeurs suivantes : {capacites}.")

    return DevisInput(
        distance_km=distance_km,
        nb_places=nb_places,
        conso_100km=_nombre(payload, "conso_100km", 35),
        prix_litre=_nombre(payload, "prix_litre", 700),
        frais_chauffeur=_nombre(payload, "frais_chauffeur", 12000),
        frais_convoyeur=_nombre(payload, "frais_convoyeur", 5000),
        peage=_nombre(payload, "peage", 0),
        marge_pct=_nombre(payload, "marge_pct", 10),
        remise_montant=_nombre(payload, "remise_montant", 0),
    )


def serialiser_devis(resultat: DevisResult) -> dict[str, Any]:
    """Prépare le résultat métier pour la réponse JSON historique."""
    resultat_json = asdict(resultat)
    resultat_json["prix_par_place"] = [
        {"places": places, "prix": prix}
        for places, prix in sorted(resultat.prix_par_place.items())
    ]
    return resultat_json
