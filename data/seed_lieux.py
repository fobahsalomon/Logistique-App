"""Peuple lieux_connus depuis data/lieux_seed.csv (export GeoNames/OSM/manuel).

Contrairement à seed_trajets.py, ce fichier ne contient pas les données en
dur : elles sont trop volumineuses (35 000+ lignes) pour rester lisibles en
Python. Le CSV est régénéré via `python -c "..."` en exportant la table
lieux_connus d'un environnement déjà peuplé (voir historique du projet) ou
via data/import_geonames.py / data/import_osm.py pour repartir de zéro.

Usage : python data/seed_lieux.py
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.db import get_connection, init_db, normaliser

CSV_PATH = Path(__file__).resolve().parent / "lieux_seed.csv"


def seed(reset: bool = False) -> int:
    """Insère les lieux du CSV. Si reset=True, vide d'abord la table."""
    conn = get_connection()
    init_db(conn)

    if reset:
        conn.execute("DELETE FROM lieux_connus")
        conn.commit()

    existing = conn.execute("SELECT COUNT(*) FROM lieux_connus").fetchone()[0]
    if existing and not reset:
        print(f"{existing} lieux déjà présents, seed ignoré (utilisez reset=True).")
        conn.close()
        return 0

    if not CSV_PATH.exists():
        print(f"Fichier introuvable : {CSV_PATH} — seed ignoré.")
        conn.close()
        return 0

    rows = []
    with open(CSV_PATH, encoding="utf-8", newline="") as f:
        for entree in csv.DictReader(f):
            nom = (entree.get("nom") or "").strip()
            if not nom:
                continue
            try:
                lat = float(entree["latitude"])
                lon = float(entree["longitude"])
            except (KeyError, ValueError):
                continue
            rows.append((
                nom,
                normaliser(nom),
                lat,
                lon,
                entree.get("source") or "manuel",
                entree.get("feature_type") or None,
            ))

    conn.executemany(
        """INSERT INTO lieux_connus
           (nom, nom_normalise, latitude, longitude, source, feature_type)
           VALUES (?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    count = len(rows)
    conn.close()
    print(f"{count} lieux insérés depuis {CSV_PATH.name}.")
    return count


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
