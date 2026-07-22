"""Accès SQLite à la base des trajets connus de CA TRANS."""

import re
import sqlite3
import unicodedata
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "ca_trans.db"

ABBREVIATIONS = {
    "SP": "SAN PEDRO",
    "ABJ": "ABIDJAN",
}


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    """Crée la table trajets si elle n'existe pas déjà."""
    close = conn is None
    conn = conn or get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trajets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            origine TEXT NOT NULL,
            destination TEXT NOT NULL,
            distance_km REAL,
            montant_aller TEXT,
            source TEXT DEFAULT 'excel'
        )
        """
    )
    conn.commit()
    if close:
        conn.close()


def _strip_accents(texte: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normaliser(texte: str) -> str:
    """Majuscules, sans accents, sans contenu entre parenthèses, abréviations développées."""
    if not texte:
        return ""
    t = _strip_accents(texte).upper()
    t = re.sub(r"\([^)]*\)", " ", t)
    t = re.sub(r"[^A-Z0-9'\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    mots = [ABBREVIATIONS.get(mot, mot) for mot in t.split(" ") if mot]
    return " ".join(mots).strip()


def list_trajets(conn: sqlite3.Connection | None = None) -> list[sqlite3.Row]:
    close = conn is None
    conn = conn or get_connection()
    rows = conn.execute("SELECT * FROM trajets ORDER BY origine, destination").fetchall()
    if close:
        conn.close()
    return rows


def rechercher_trajet(
    origine: str, destination: str, conn: sqlite3.Connection | None = None
) -> sqlite3.Row | None:
    """Recherche tolérante d'un trajet connu, dans les deux sens (origine/destination
    ou destination/origine, car le sens du trajet n'est pas toujours celui de la base)."""
    o = normaliser(origine)
    d = normaliser(destination)
    if not o or not d:
        return None

    close = conn is None
    conn = conn or get_connection()
    rows = conn.execute("SELECT * FROM trajets").fetchall()
    if close:
        conn.close()

    for row in rows:
        ro = normaliser(row["origine"])
        rd = normaliser(row["destination"])
        sens_direct = (o in ro or ro in o) and (d in rd or rd in d)
        sens_inverse = (o in rd or rd in o) and (d in ro or ro in d)
        if sens_direct or sens_inverse:
            return row
    return None


def inserer_trajet(
    origine: str,
    destination: str,
    distance_km: float | None,
    montant_aller: str | None = None,
    source: str = "ors",
    conn: sqlite3.Connection | None = None,
) -> int:
    close = conn is None
    conn = conn or get_connection()
    cur = conn.execute(
        "INSERT INTO trajets (origine, destination, distance_km, montant_aller, source) "
        "VALUES (?, ?, ?, ?, ?)",
        (origine, destination, distance_km, montant_aller, source),
    )
    conn.commit()
    trajet_id = cur.lastrowid
    if close:
        conn.close()
    return trajet_id
