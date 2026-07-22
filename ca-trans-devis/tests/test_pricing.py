import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.pricing import DevisInput, calculer_devis, frais_mission_defaut


def approx(a, b, tol=1e-6):
    return math.isclose(a, b, rel_tol=0, abs_tol=tol)


def test_cas_reference_excel():
    """Cas de référence issu du fichier Excel original (SP -> Yamoussoukro, 437 km)."""
    entree = DevisInput(
        distance_km=437,
        conso_100km=35,
        prix_litre=700,
        frais_chauffeur=6000,
        frais_convoyeur=2500,
        peage=0,
        marge_pct=10,
        remise_montant=0,
    )
    r = calculer_devis(entree)

    assert approx(r.consommation_totale, 152.95)
    assert approx(r.cout_carburant, 107065)
    assert approx(r.cout_carburant_x4, 428260)
    assert approx(r.total_autres_frais, 8500)
    assert approx(r.cout_revient_total, 436760)
    assert approx(r.marge, 43676)
    assert approx(r.prix_vente_aller, 480436)
    assert approx(r.ht_aller_retour, 960872)
    assert approx(r.tva, 172956.96)
    assert approx(r.ttc_aller_retour, 1133828.96)
    assert approx(r.ttc_apres_remise, 1133828.96)
    assert approx(r.ttc_aller_simple, 566914.48)

    assert approx(r.prix_par_place[63], 7625.968254, tol=1e-5)
    assert approx(r.prix_par_place[51], 9420.313725, tol=1e-5)
    assert approx(r.prix_par_place[49], 9804.816327, tol=1e-5)
    assert approx(r.prix_par_place_vip_58, 16566.758621, tol=1e-5)


def test_remise_impacte_ttc_aller_simple():
    entree = DevisInput(distance_km=437, frais_chauffeur=6000, frais_convoyeur=2500, remise_montant=100000)
    sans_remise = calculer_devis(DevisInput(distance_km=437, frais_chauffeur=6000, frais_convoyeur=2500))
    r = calculer_devis(entree)
    assert approx(r.ttc_apres_remise, sans_remise.ttc_aller_retour - 100000)
    assert approx(r.ttc_aller_simple, r.ttc_apres_remise / 2)


def test_frais_mission_defaut():
    assert frais_mission_defaut(1) == (12000, 5000)
    assert frais_mission_defaut(2) == (22000, 7000)
