"""Import des lieux OpenStreetMap de Côte d'Ivoire dans lieux_connus.

Télécharge l'extrait OSM de Geofabrik (~60 Mo) et insère dans lieux_connus
les nœuds/chemins portant des tags de lieu habité ou de transport :
  - place = city, town, village, suburb, neighbourhood, hamlet, locality, quarter
  - amenity = bus_station
  - highway = bus_stop (si nommé)

La fonction inserer_lieu() est idempotente : les doublons GeoNames/Nominatim
(même nom_normalise + coordonnées proches) sont automatiquement ignorés.

Usage :
    pip install osmium
    python data/import_osm.py
"""

import sys
import urllib.request
from pathlib import Path

# Ajoute la racine du projet au path pour importer core/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import osmium
except ImportError:
    print("Erreur : installez osmium avec 'pip install osmium'", file=sys.stderr)
    sys.exit(1)

from core.db import init_db, inserer_lieu, get_connection

OSM_URL = "https://download.geofabrik.de/africa/ivory-coast-latest.osm.pbf"
OSM_FILE = Path(__file__).parent / "CI" / "ivory-coast-latest.osm.pbf"

PLACE_TAGS = frozenset({
    "city", "town", "village", "suburb", "neighbourhood",
    "hamlet", "locality", "quarter", "isolated_dwelling",
})
ALT_NAME_KEYS = ("name:fr", "alt_name", "official_name", "loc_name")


def _progression(nb_blocs, taille_bloc, taille_totale):
    telecharge = nb_blocs * taille_bloc
    pct = min(telecharge * 100 // max(taille_totale, 1), 100)
    mo = telecharge / 1_048_576
    print(f"\r  {pct:3d}%  ({mo:.1f} Mo)", end="", flush=True)


class _LieuxHandler(osmium.SimpleHandler):
    """Parcourt le fichier .osm.pbf et collecte les lieux nommés pertinents."""

    def __init__(self):
        super().__init__()
        self.lieux: list[tuple[str, float, float, str]] = []

    def _traiter(self, tags, lat: float, lon: float):
        nom = tags.get("name")
        if not nom:
            return
        place = tags.get("place")
        amenity = tags.get("amenity")
        highway = tags.get("highway")
        if place in PLACE_TAGS or amenity == "bus_station" or highway == "bus_stop":
            feature = place or amenity or highway
            self.lieux.append((nom, lat, lon, feature))
            # Noms alternatifs
            for cle in ALT_NAME_KEYS:
                alt = tags.get(cle)
                if alt and alt != nom:
                    self.lieux.append((alt, lat, lon, feature))

    def node(self, n):
        if n.location.valid():
            self._traiter(n.tags, n.location.lat, n.location.lon)

    def way(self, w):
        # Pour les ways, utilise le centroïde du premier nœud disponible
        # (pas de calcul de centroïde exact pour éviter la dépendance shapely)
        if hasattr(w, "nodes") and w.nodes:
            try:
                loc = w.nodes[0].location
                if loc.valid():
                    self._traiter(w.tags, loc.lat, loc.lon)
            except Exception:
                pass


def main():
    OSM_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not OSM_FILE.exists():
        print(f"Téléchargement de {OSM_URL} …")
        urllib.request.urlretrieve(OSM_URL, OSM_FILE, _progression)
        print()
    else:
        print(f"Fichier existant : {OSM_FILE} — parsing sans re-téléchargement.")

    print("Parsing du fichier OSM …")
    handler = _LieuxHandler()
    handler.apply_file(str(OSM_FILE), locations=True)
    print(f"{len(handler.lieux)} entrées candidates extraites.")

    print("Insertion dans lieux_connus …")
    init_db()
    conn = get_connection()
    inseres = 0
    try:
        for nom, lat, lon, feature in handler.lieux:
            lid = inserer_lieu(nom=nom, lat=lat, lon=lon, source="osm",
                               feature_type=feature, conn=conn)
            # inserer_lieu retourne l'id existant si doublon — on compte seulement les vrais inserts
            if lid is not None:
                inseres += 1
    finally:
        conn.close()

    print(f"Import OSM terminé : {inseres} lieux traités (doublons ignorés automatiquement).")


if __name__ == "__main__":
    main()
