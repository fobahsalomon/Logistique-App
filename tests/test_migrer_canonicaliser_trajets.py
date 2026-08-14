import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.db import get_connection, inserer_trajet, rechercher_trajet
from data.migrer_canonicaliser_trajets import migrer


def test_migrer_reecrit_abreviations_vers_nom_canonique(tmp_path, monkeypatch):
    monkeypatch.setattr("core.db.DB_PATH", tmp_path / "test.db")
    from core.db import init_db

    conn = get_connection()
    init_db(conn)
    inserer_trajet("SP", "ABJ", 100, source="excel", conn=conn)
    inserer_trajet("ABIDJAN", "GAGNOA", 200, source="excel", conn=conn)  # déjà canonique

    nb = migrer(conn)

    lignes = conn.execute("SELECT origine, destination FROM trajets ORDER BY id").fetchall()
    assert nb == 2  # SP->SAN PEDRO (origine) et ABJ->ABIDJAN (destination) de la 1re ligne
    assert lignes[0]["origine"] == "SAN PEDRO"
    assert lignes[0]["destination"] == "ABIDJAN"
    assert lignes[1]["origine"] == "ABIDJAN"  # inchangé
    conn.close()


def test_migrer_ne_touche_pas_aux_sous_chaines(tmp_path, monkeypatch):
    """« SP » ne doit être remplacé que si c'est la valeur EXACTE de la
    cellule — jamais en tant que sous-chaîne d'un nom de lieu plus long."""
    monkeypatch.setattr("core.db.DB_PATH", tmp_path / "test.db")
    from core.db import init_db

    conn = get_connection()
    init_db(conn)
    inserer_trajet("SPECIAL VILLE", "ABJALA", 50, source="excel", conn=conn)

    nb = migrer(conn)

    ligne = conn.execute("SELECT origine, destination FROM trajets").fetchone()
    assert nb == 0
    assert ligne["origine"] == "SPECIAL VILLE"
    assert ligne["destination"] == "ABJALA"
    conn.close()


def test_recherche_toujours_valide_apres_migration(tmp_path, monkeypatch):
    """La recherche tolérante doit toujours reconnaître SP/ABJ en saisie,
    même si la base ne stocke plus que la forme canonique."""
    monkeypatch.setattr("core.db.DB_PATH", tmp_path / "test.db")
    from core.db import init_db

    conn = get_connection()
    init_db(conn)
    inserer_trajet("SP", "ABJ", 330, source="excel", conn=conn)
    migrer(conn)

    row = rechercher_trajet("SP", "ABJ", conn=conn)
    assert row is not None
    assert row["origine"] == "SAN PEDRO"
    assert row["destination"] == "ABIDJAN"
    conn.close()
