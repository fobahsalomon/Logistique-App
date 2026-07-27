"""Import GeoNames CI → table lieux_connus.

Lance une seule fois après le premier clone du repo :
    python data/import_geonames.py

Source : data/CI/CI.txt (export GeoNames Côte d'Ivoire, feature_class P = lieux habités).
Idempotent : ne réinsère pas les entrées déjà présentes (même nom normalisé + coordonnées).
"""

import sys
from pathlib import Path

# Permet d'importer core/ depuis n'importe quel répertoire
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.db import get_connection, init_db, normaliser

CI_TXT = Path(__file__).resolve().parent / "CI" / "CI.txt"

COLONNES = [
    "geonameid", "name", "asciiname", "alternatenames",
    "latitude", "longitude", "feature_class", "feature_code",
    "country_code", "cc2", "admin1_code", "admin2_code",
    "admin3_code", "admin4_code", "population", "elevation",
    "dem", "timezone", "modification_date",
]


def _charger_existants(conn) -> set[tuple]:
    """Retourne l'ensemble des (nom_normalise, lat_arrondi, lon_arrondi) déjà en base."""
    rows = conn.execute(
        "SELECT nom_normalise, ROUND(latitude,3), ROUND(longitude,3) FROM lieux_connus"
    ).fetchall()
    return {(r[0], r[1], r[2]) for r in rows}


def importer(verbose: bool = True) -> int:
    conn = get_connection()
    init_db(conn)
    existants = _charger_existants(conn)
    inseres = 0

    with open(CI_TXT, encoding="utf-8") as fh:
        for ligne in fh:
            champs = ligne.rstrip("\n").split("\t")
            if len(champs) < 7:
                continue
            row = dict(zip(COLONNES, champs))
            if row["feature_class"] != "P":
                continue

            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
            except ValueError:
                continue

            lat_r = round(lat, 3)
            lon_r = round(lon, 3)

            # Noms à insérer : nom principal + variantes utiles
            noms = [row["name"]]
            if row.get("alternatenames"):
                for alt in row["alternatenames"].split(","):
                    alt = alt.strip()
                    if alt and normaliser(alt) != normaliser(row["name"]):
                        noms.append(alt)

            for nom in noms:
                nom_n = normaliser(nom)
                if not nom_n:
                    continue
                cle = (nom_n, lat_r, lon_r)
                if cle in existants:
                    continue
                conn.execute(
                    "INSERT INTO lieux_connus (nom, nom_normalise, latitude, longitude, source, feature_type) "
                    "VALUES (?, ?, ?, ?, 'geonames', ?)",
                    (nom, nom_n, lat, lon, row.get("feature_code")),
                )
                existants.add(cle)
                inseres += 1

    conn.commit()
    conn.close()

    if verbose:
        print(f"Import terminé : {inseres} lieu(x) ajouté(s) dans lieux_connus.")
    return inseres


if __name__ == "__main__":
    importer()
