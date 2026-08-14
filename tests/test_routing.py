"""Tests du géocodage Nominatim, en particulier la recherche structurée
rue+quartier (voir core/routing.py::_geocoder_nominatim_structure).

Aucun appel réseau réel : requests.get est mocké. Les appels à
time.sleep sont aussi mockés pour ne pas subir le throttling 1 req/s.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import routing


def _reponse(json_data, status_ok=True):
    rep = MagicMock()
    rep.json.return_value = json_data
    rep.raise_for_status = MagicMock() if status_ok else MagicMock(side_effect=Exception("HTTP error"))
    return rep


@patch("core.routing.time.sleep", return_value=None)
@patch("core.routing.requests.get")
def test_structure_utilisee_quand_virgule_presente(mock_get, _mock_sleep):
    """« Rue X, Quartier » doit d'abord interroger Nominatim avec des champs
    street=/city= distincts plutôt qu'un unique q= texte libre."""
    mock_get.return_value = _reponse([
        {"lat": "5.36", "lon": "-4.00", "display_name": "Boulevard Latrille, Cocody, Abidjan"}
    ])

    point = routing._geocoder_nominatim("Boulevard Latrille, Cocody")

    assert point is not None
    assert point.lat == 5.36
    params_envoyes = mock_get.call_args.kwargs["params"]
    assert params_envoyes.get("street") == "Boulevard Latrille"
    assert params_envoyes.get("city") == "Cocody"
    assert "q" not in params_envoyes


@patch("core.routing.time.sleep", return_value=None)
@patch("core.routing.requests.get")
def test_repli_texte_libre_si_structure_vide(mock_get, _mock_sleep):
    """Si la recherche structurée ne renvoie rien, on retombe sur la
    recherche en texte libre historique (pas de régression de couverture)."""
    appels = []

    def side_effect(*args, **kwargs):
        appels.append(kwargs["params"])
        if "street" in kwargs["params"]:
            return _reponse([])  # structuré : rien trouvé
        return _reponse([{"lat": "5.30", "lon": "-4.01", "display_name": "Résultat texte libre"}])

    mock_get.side_effect = side_effect

    point = routing._geocoder_nominatim("Rue Fantaisiste, QuartierInconnu")

    assert point is not None
    assert point.label == "Résultat texte libre"
    assert len(appels) == 2
    assert "street" in appels[0]
    assert appels[1].get("q") == "Rue Fantaisiste, QuartierInconnu"


@patch("core.routing.time.sleep", return_value=None)
@patch("core.routing.requests.get")
def test_sans_virgule_va_direct_en_texte_libre(mock_get, _mock_sleep):
    """Un nom de lieu simple (sans virgule) ne doit pas déclencher de
    recherche structurée : un seul appel, en q= texte libre."""
    mock_get.return_value = _reponse([{"lat": "6.5", "lon": "-5.5", "display_name": "San Pedro"}])

    point = routing._geocoder_nominatim("San Pedro")

    assert point is not None
    assert mock_get.call_count == 1
    assert mock_get.call_args.kwargs["params"].get("q") == "San Pedro"


@patch("core.routing.time.sleep", return_value=None)
@patch("core.routing.requests.get")
def test_multi_place_les_resultats_structures_en_tete(mock_get, _mock_sleep):
    """En mode autocomplétion, les correspondances structurées (quartier
    confirmé) doivent apparaître avant les résultats texte libre non filtrés
    par quartier, et les doublons de coordonnées sont supprimés."""

    def side_effect(*args, **kwargs):
        params = kwargs["params"]
        if "street" in params:
            return _reponse([
                {"lat": "5.360000", "lon": "-3.980000", "display_name": "Boulevard Latrille, Cocody"}
            ])
        return _reponse([
            {"lat": "5.360000", "lon": "-3.980000", "display_name": "Boulevard Latrille, Cocody",
             "type": "road"},
            {"lat": "5.250000", "lon": "-3.700000", "display_name": "Boulevard Latrille, Grand-Bassam",
             "type": "road"},
        ])

    mock_get.side_effect = side_effect

    resultats = routing._geocoder_nominatim_multi("Boulevard Latrille, Cocody", limit=8)

    assert len(resultats) == 2  # le doublon structuré/texte-libre à Cocody est fusionné
    assert "Cocody" in resultats[0].label  # le résultat structuré (quartier confirmé) est en tête
