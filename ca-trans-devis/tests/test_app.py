import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import app as app_module


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "get_api_key", lambda: "")
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("core.db.DB_PATH", db_path)
    app_module.init_db()
    app_module.seed_trajets()
    app_module.app.config.update(TESTING=True)
    with app_module.app.test_client() as c:
        yield c


def test_page_accueil(client):
    rep = client.get("/")
    assert rep.status_code == 200
    assert b"CA TRANS" in rep.data


def test_liste_trajets(client):
    rep = client.get("/api/trajets")
    assert rep.status_code == 200
    trajets = rep.get_json()
    assert len(trajets) == 70


def test_resoudre_trajet_connu(client):
    rep = client.post("/api/resoudre", json={"origine": "SP", "destination": "Abidjan"})
    assert rep.status_code == 200
    data = rep.get_json()
    assert data["statut"] == "base"
    assert data["distance_km"] == 330.0


def test_resoudre_sans_cle_api(client):
    rep = client.post("/api/resoudre", json={"origine": "Ville inconnue X", "destination": "Ville inconnue Y"})
    assert rep.status_code == 200
    data = rep.get_json()
    assert data["statut"] == "erreur"


def test_resoudre_champs_manquants(client):
    rep = client.post("/api/resoudre", json={"origine": "", "destination": ""})
    assert rep.status_code == 400


def test_frais_mission(client):
    rep = client.get("/api/frais-mission?jours=2")
    assert rep.get_json() == {"frais_chauffeur": 22000, "frais_convoyeur": 7000}


def test_devis_cas_reference(client):
    rep = client.post(
        "/api/devis",
        json={
            "distance_km": 437,
            "frais_chauffeur": 6000,
            "frais_convoyeur": 2500,
        },
    )
    assert rep.status_code == 200
    data = rep.get_json()
    assert data["ttc_aller_simple"] == pytest.approx(566914.48, abs=1e-6)


def test_enregistrer_trajet(client):
    rep = client.post(
        "/api/trajet",
        json={"origine": "Test A", "destination": "Test B", "distance_km": 42, "source": "manuel"},
    )
    assert rep.status_code == 201
    trajets = client.get("/api/trajets").get_json()
    assert any(t["origine"] == "Test A" for t in trajets)
