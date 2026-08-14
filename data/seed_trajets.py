"""Peuple la base SQLite avec les 70 trajets connus du fichier Excel d'origine.

Usage : python data/seed_trajets.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.db import get_connection, init_db

# (origine, destination, distance_km, montant_aller)
TRAJETS = [
    ("SAN PEDRO", "ABIDJAN", 330, "6600"),
    ("SAN PEDRO", "BONOUA", 395, "Environ 8000"),
    ("SAN PEDRO", "SOUBRE", 135, "2000"),
    ("SAN PEDRO", "GAGNOA", 233, "3000"),
    ("ABIDJAN", "GAGNOA (péages)", 270, "3500"),
    ("ABIDJAN", "LAUZOUA", 165, None),
    ("ABIDJAN", "BONOUA", 63, "Environ 1500 ou 2000"),
    ("ABIDJAN", "BOUAKE (péages)", 345, "7100"),
    ("ABIDJAN", "YAMOUSSOUKRO (péages)", 230, "4500"),
    ("ABIDJAN", "DALOA", 370, None),
    ("ABIDJAN", "GUIBEROUA (péages)", 300, "4000"),
    ("SAN PEDRO", "GUIGLO", 350, "7000"),
    ("SOUBRE", "BONOUA", 430, None),
    ("SAN PEDRO", "SASSANDRA", 80, "2000"),
    ("MOUSSADOUGOU", "M'BAHIAKRO", 558, None),
    ("ABIDJAN", "DABOU", 50, None),
    ("ABIDJAN", "BEOUMI (351km/SAKASSOU) (389km/Bouaké)", 389, "6100 / 8000"),
    ("SAN PEDRO", "BEOUMI (443km/DALOA) (562km/YAKRO)", 562, None),
    ("ABIDJAN", "LAKOTA (péages)", 220, "3000"),
    ("SAN PEDRO", "BONDOUKOU", 713, "13000"),
    ("ABIDJAN", "ASSINIE", 95, None),
    ("SAN PEDRO", "G. BEREBY", 55, "1000"),
    ("ABIDJAN", "G. BEREBY", 375, "7100"),
    ("SAN PEDRO", "FRESCO", 141, "4000"),
    ("SAN PEDRO", "G. LAHOU", 337, "5000"),
    ("SAN PEDRO", "MOUSSADOUGOU", 44, "2500"),
    ("Treichville", "Zokolilié", 245, None),
    ("Yop Rue Princesse", "Zokolilié", 233, None),
    ("Abidjan", "Zohoa (péages)", 308, "4000"),
    ("SOGB", "Bouaké", 603, "10500"),
    ("SOGB", "YAKRO", 491, "8000"),
    ("SOGB", "TIEBISSOU", 537, "Environ 9000"),
    ("SAN PEDRO", "Yamoussoukro", 439, "7100"),
    ("ABIDJAN", "SASSANDRA", 262, "5000"),
    ("SAN PEDRO", "DALOA", 268, "5000"),
    ("G. BEREBY", "DIMBOKRO", 483, None),
    ("Yopougon", "Zikisso", 247, "Environ 3500"),
    ("ABIDJAN", "ABOISSO", 118, "2300"),
    ("SAN PEDRO", "AZAGUIE", 351, "Environ 6600"),
    ("GAGNOA", "BOUAKE", 275, "6100"),
    ("ABIDJAN", "MEAGUI", 349, "6000"),
    ("ABIDJAN", "MONDOUKOU (Péage)", 55, "1900"),
    ("ADJAME", "ASSINIE", 96, None),
    ("YOPOUGON", "SOUBRE", 363, "5000"),
    ("ADJAME", "JACQUEVILLE", 60, None),
    ("ABIDJAN", "GALEBRE (péage)", 289, "5000"),
    ("LAKOTA", "SINFRA", 107, None),
    ("SAN PEDRO", "BOUAKE", 551, "9000"),
    ("SAN PEDRO", "BLOLEQUIN", None, "9000"),
    ("SAN PEDRO", "DUEKOUE", None, "7000"),
    ("SAN PEDRO", "ISSIA", None, "4000"),
    ("SAN PEDRO", "DIVO", None, "5000"),
    ("SAN PEDRO", "LAKOTA", None, "5000"),
    ("SAN PEDRO", "SOGB", None, "1500"),
    ("SAN PEDRO", "TABOU", None, "2000"),
    ("SAN PEDRO", "MEAGUI", None, "2000"),
    ("SAN PEDRO", "GABIADJI", None, "2000"),
    ("SAN PEDRO", "TIASSALE", None, "6500"),
    ("SAN PEDRO", "N'DOUCI", None, "6500"),
    ("ABIDJAN", "TIASSALE", None, "2500"),
    ("ABIDJAN", "DIVO", None, "2500"),
    ("ABIDJAN", "N'DOUCI", None, "2500"),
    ("ABIDJAN", "YABAYO", None, "5000"),
    ("ABIDJAN", "CARRIERE", None, "5000"),
    ("ABIDJAN", "OUPOYO", None, "6100"),
    ("ABIDJAN", "MEAGUI", None, "6100"),
    ("ABIDJAN", "TUHI", None, "6600"),
    ("ABIDJAN", "GABIADJI", None, "6600"),
    ("G. BASSAM", "SOUBRE", 413, None),
    ("SAN PEDRO", "ABENGOUROU", 521, "9100"),
]


def seed(reset: bool = False) -> int:
    """Insère les trajets connus. Si reset=True, vide d'abord la table."""
    conn = get_connection()
    init_db(conn)

    if reset:
        conn.execute("DELETE FROM trajets")
        conn.commit()

    existing = conn.execute("SELECT COUNT(*) FROM trajets WHERE source = 'excel'").fetchone()[0]
    if existing and not reset:
        print(f"{existing} trajets 'excel' déjà présents, seed ignoré (utilisez reset=True).")
        conn.close()
        return 0

    conn.executemany(
        "INSERT INTO trajets (origine, destination, distance_km, montant_aller, source) "
        "VALUES (?, ?, ?, ?, 'excel')",
        TRAJETS,
    )
    conn.commit()
    count = len(TRAJETS)
    conn.close()
    print(f"{count} trajets insérés dans {conn}.")
    return count


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
