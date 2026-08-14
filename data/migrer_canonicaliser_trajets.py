"""Harmonise les abréviations de villes dans la table trajets.

Certains des 70 trajets historiques utilisent « SP » ou « ABJ » comme
origine/destination alors que d'autres lignes épellent « SAN PEDRO » /
« ABIDJAN » en toutes lettres — un même trajet en base pouvait donc
apparaître sous deux libellés différents dans le tableau « Base de trajets
connus », même si la recherche (core.db.normaliser) traitait déjà ces
abréviations comme équivalentes pour la résolution d'itinéraire.

Ce script réécrit les valeurs stockées vers un nom canonique unique par
ville, sans toucher à la logique de recherche/normalisation elle-même.

Usage : python data/migrer_canonicaliser_trajets.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.db import get_connection

# Reprend exactement les abréviations déjà connues de core.db.ABBREVIATIONS,
# vers la même graphie (tout en majuscules) que les autres villes du jeu de
# données (ex : GAGNOA, BOUAKE, YAMOUSSOUKRO).
CANONIQUES = {
    "SP": "SAN PEDRO",
    "ABJ": "ABIDJAN",
}


def migrer(conn=None) -> int:
    """Réécrit les origine/destination abrégées vers leur forme canonique.

    Ne modifie que les valeurs qui correspondent EXACTEMENT à une
    abréviation connue (pas de remplacement de sous-chaîne, pour ne jamais
    toucher un nom de lieu contenant accidentellement ces lettres).
    Retourne le nombre de cellules modifiées.
    """
    close = conn is None
    conn = conn or get_connection()

    total = 0
    for colonne in ("origine", "destination"):
        for abrege, canonique in CANONIQUES.items():
            cur = conn.execute(
                f"UPDATE trajets SET {colonne} = ? WHERE {colonne} = ?",
                (canonique, abrege),
            )
            total += cur.rowcount

    conn.commit()
    if close:
        conn.close()
    return total


if __name__ == "__main__":
    nb = migrer()
    print(f"{nb} cellule(s) mise(s) à jour vers un nom canonique.")
