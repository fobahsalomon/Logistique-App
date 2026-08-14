"""Accès SQLite à la base des trajets connus de CA TRANS."""

import re
import sqlite3
import unicodedata
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

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
    """Crée les tables si elles n'existent pas déjà."""
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lieux_connus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL,
            nom_normalise TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            source TEXT DEFAULT 'manuel',
            feature_type TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_lieux_nom_normalise ON lieux_connus(nom_normalise)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS utilisateurs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
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


# ---------------------------------------------------------------- trajets

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
    """Recherche tolérante d'un trajet connu, dans les deux sens."""
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


def mettre_a_jour_trajet(
    trajet_id: int,
    origine: str,
    destination: str,
    distance_km: float | None,
    montant_aller: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> bool:
    close = conn is None
    conn = conn or get_connection()
    cur = conn.execute(
        "UPDATE trajets SET origine=?, destination=?, distance_km=?, montant_aller=? WHERE id=?",
        (origine, destination, distance_km, montant_aller, trajet_id),
    )
    conn.commit()
    affected = cur.rowcount > 0
    if close:
        conn.close()
    return affected


def supprimer_trajet(trajet_id: int, conn: sqlite3.Connection | None = None) -> bool:
    close = conn is None
    conn = conn or get_connection()
    cur = conn.execute("DELETE FROM trajets WHERE id=?", (trajet_id,))
    conn.commit()
    affected = cur.rowcount > 0
    if close:
        conn.close()
    return affected


# ---------------------------------------------------------------- lieux_connus

def rechercher_lieu(texte: str, conn: sqlite3.Connection | None = None) -> sqlite3.Row | None:
    """Recherche tolérante dans lieux_connus — retourne le premier résultat pertinent."""
    t = normaliser(texte)
    if not t:
        return None
    close = conn is None
    conn = conn or get_connection()
    row = conn.execute(
        """SELECT * FROM lieux_connus
           WHERE nom_normalise = ?
           ORDER BY LENGTH(nom) LIMIT 1""",
        (t,),
    ).fetchone()
    if not row:
        row = conn.execute(
            """SELECT * FROM lieux_connus
               WHERE nom_normalise LIKE ?
               ORDER BY LENGTH(nom) LIMIT 1""",
            (f"%{t}%",),
        ).fetchone()
    if close:
        conn.close()
    return row


def rechercher_lieux(
    texte: str, limit: int = 8, conn: sqlite3.Connection | None = None
) -> list[sqlite3.Row]:
    """Recherche pour l'autocomplétion — scoring rapidfuzz avec fallback SQL LIKE."""
    t = normaliser(texte)
    if not t or len(t) < 2:
        return []
    close = conn is None
    conn = conn or get_connection()

    try:
        from rapidfuzz import fuzz, process as rfprocess

        # Étape 1 : candidats par sous-chaîne SQL (rapide, ≤50 entrées)
        candidates = conn.execute(
            "SELECT * FROM lieux_connus WHERE nom_normalise LIKE ? LIMIT 50",
            (f"%{t}%",),
        ).fetchall()

        # Étape 2 : si peu de résultats et requête suffisamment longue,
        # faire un scan rapide complet avec rapidfuzz pour tolérer les fautes
        if len(candidates) < 3 and len(t) >= 3:
            all_rows = conn.execute("SELECT * FROM lieux_connus").fetchall()
            names = [r["nom_normalise"] for r in all_rows]
            fuzzy = rfprocess.extract(t, names, scorer=fuzz.WRatio, limit=20, score_cutoff=60)
            seen = {r["id"] for r in candidates}
            for _, _, idx in fuzzy:
                r = all_rows[idx]
                if r["id"] not in seen:
                    candidates.append(r)
                    seen.add(r["id"])

        if close:
            conn.close()

        scored = [(r, fuzz.WRatio(t, r["nom_normalise"])) for r in candidates]
        scored.sort(key=lambda x: -x[1])
        return [r for r, _ in scored[:limit]]

    except ImportError:
        # Fallback sans rapidfuzz
        rows = conn.execute(
            """SELECT * FROM lieux_connus
               WHERE nom_normalise LIKE ?
               ORDER BY CASE WHEN nom_normalise LIKE ? THEN 0 ELSE 1 END,
                        LENGTH(nom)
               LIMIT ?""",
            (f"%{t}%", f"{t}%", limit),
        ).fetchall()
        if close:
            conn.close()
        return rows


def inserer_lieu(
    nom: str,
    lat: float,
    lon: float,
    source: str = "manuel",
    feature_type: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> int | None:
    """Insère un lieu dans lieux_connus (idempotent : ignore si même nom normalisé + coordonnées proches)."""
    nom_normalise = normaliser(nom)
    if not nom_normalise:
        return None
    close = conn is None
    conn = conn or get_connection()
    existing = conn.execute(
        "SELECT id FROM lieux_connus WHERE nom_normalise=? "
        "AND ROUND(latitude,3)=ROUND(?,3) AND ROUND(longitude,3)=ROUND(?,3)",
        (nom_normalise, lat, lon),
    ).fetchone()
    if existing:
        if close:
            conn.close()
        return existing["id"]
    cur = conn.execute(
        "INSERT INTO lieux_connus (nom, nom_normalise, latitude, longitude, source, feature_type) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (nom, nom_normalise, lat, lon, source, feature_type),
    )
    conn.commit()
    lieu_id = cur.lastrowid
    if close:
        conn.close()
    return lieu_id


# ------------------------------------------------------------- utilisateurs

def creer_utilisateur(
    username: str, password: str, conn: sqlite3.Connection | None = None
) -> int | None:
    """Crée un compte (mot de passe haché). Idempotent : si le nom d'utilisateur
    existe déjà, ne fait rien et renvoie son id existant."""
    close = conn is None
    conn = conn or get_connection()
    existant = conn.execute(
        "SELECT id FROM utilisateurs WHERE username = ?", (username,)
    ).fetchone()
    if existant:
        if close:
            conn.close()
        return existant["id"]
    cur = conn.execute(
        "INSERT INTO utilisateurs (username, password_hash) VALUES (?, ?)",
        (username, generate_password_hash(password)),
    )
    conn.commit()
    user_id = cur.lastrowid
    if close:
        conn.close()
    return user_id


def obtenir_utilisateur_par_id(
    user_id: int, conn: sqlite3.Connection | None = None
) -> sqlite3.Row | None:
    close = conn is None
    conn = conn or get_connection()
    row = conn.execute("SELECT * FROM utilisateurs WHERE id = ?", (user_id,)).fetchone()
    if close:
        conn.close()
    return row


def verifier_mot_de_passe(
    username: str, password: str, conn: sqlite3.Connection | None = None
) -> sqlite3.Row | None:
    """Renvoie la ligne utilisateur si identifiant + mot de passe sont valides, sinon None."""
    close = conn is None
    conn = conn or get_connection()
    row = conn.execute("SELECT * FROM utilisateurs WHERE username = ?", (username,)).fetchone()
    if close:
        conn.close()
    if row is None or not check_password_hash(row["password_hash"], password):
        return None
    return row


def aucun_utilisateur(conn: sqlite3.Connection | None = None) -> bool:
    close = conn is None
    conn = conn or get_connection()
    total = conn.execute("SELECT COUNT(*) FROM utilisateurs").fetchone()[0]
    if close:
        conn.close()
    return total == 0
