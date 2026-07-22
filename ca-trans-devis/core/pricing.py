"""Moteur de calcul de devis CA TRANS.

Reproduit exactement les formules du fichier Excel d'origine
("FICHE DE CALCUL CONVOI CA TRANS.xlsx"). Ne pas modifier ces formules,
y compris le facteur x4 appliqué au coût du carburant : c'est une règle
métier reprise telle quelle de l'Excel d'origine.
"""

from dataclasses import dataclass, field


@dataclass
class DevisInput:
    distance_km: float
    nb_places: int = 63
    conso_100km: float = 35
    prix_litre: float = 700
    frais_chauffeur: float = 12000
    frais_convoyeur: float = 5000
    peage: float = 0
    marge_pct: float = 10
    remise_montant: float = 0


@dataclass
class DevisResult:
    consommation_totale: float
    cout_carburant: float
    cout_carburant_x4: float
    total_autres_frais: float
    cout_revient_total: float
    marge: float
    prix_vente_aller: float
    ht_aller_retour: float
    tva: float
    ttc_aller_retour: float
    ttc_apres_remise: float
    ttc_aller_simple: float
    prix_par_place: dict = field(default_factory=dict)
    prix_par_place_vip_58: float = 0.0


def calculer_devis(entree: DevisInput) -> DevisResult:
    """Calcule le devis complet à partir des paramètres du voyage."""

    consommation_totale = (entree.distance_km * entree.conso_100km) / 100
    cout_carburant = consommation_totale * entree.prix_litre
    cout_carburant_x4 = cout_carburant * 4  # règle Excel d'origine, ne pas "corriger"
    total_autres_frais = entree.frais_chauffeur + entree.peage + entree.frais_convoyeur
    cout_revient_total = cout_carburant_x4 + total_autres_frais
    marge = cout_revient_total * (entree.marge_pct / 100)
    prix_vente_aller = cout_revient_total + marge
    ht_aller_retour = prix_vente_aller * 2
    tva = ht_aller_retour * 0.18
    ttc_aller_retour = ht_aller_retour + tva
    ttc_apres_remise = ttc_aller_retour - entree.remise_montant
    ttc_aller_simple = ttc_apres_remise / 2

    prix_par_place = {
        n: prix_vente_aller / n for n in (63, 51, 49) if n
    }
    # Toujours inclure le nombre de places demandé par l'utilisateur
    if entree.nb_places:
        prix_par_place[entree.nb_places] = prix_vente_aller / entree.nb_places

    prix_par_place_vip_58 = (prix_vente_aller / 58) * 2

    return DevisResult(
        consommation_totale=consommation_totale,
        cout_carburant=cout_carburant,
        cout_carburant_x4=cout_carburant_x4,
        total_autres_frais=total_autres_frais,
        cout_revient_total=cout_revient_total,
        marge=marge,
        prix_vente_aller=prix_vente_aller,
        ht_aller_retour=ht_aller_retour,
        tva=tva,
        ttc_aller_retour=ttc_aller_retour,
        ttc_apres_remise=ttc_apres_remise,
        ttc_aller_simple=ttc_aller_simple,
        prix_par_place=prix_par_place,
        prix_par_place_vip_58=prix_par_place_vip_58,
    )


def frais_mission_defaut(nb_jours: int) -> tuple[float, float]:
    """Renvoie (frais_chauffeur, frais_convoyeur) par défaut selon le nombre de jours."""
    if nb_jours >= 2:
        return 22000, 7000
    return 12000, 5000
