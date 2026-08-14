import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import app as app_module
from core.routing import RoutingError


def _routing_indisponible(*args, **kwargs):
    raise RoutingError("service de routage non disponible (test)")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("core.db.DB_PATH", db_path)
    monkeypatch.setattr("core.routing.resoudre_itineraire", _routing_indisponible)
    monkeypatch.setattr("core.routing.calculer_itineraire", _routing_indisponible)
    app_module.app.secret_key = "cle-de-test"
    app_module.init_db()
    app_module.seed_trajets()
    app_module.definir_mot_de_passe("testuser", "testpass")
    app_module.app.config.update(TESTING=True)
    with app_module.app.test_client() as c:
        c.post("/login", data={"username": "testuser", "password": "testpass"})
        yield c


@pytest.fixture()
def client_anonyme(tmp_path, monkeypatch):
    """Client de test SANS session authentifiée, pour vérifier la protection des routes."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("core.db.DB_PATH", db_path)
    app_module.app.secret_key = "cle-de-test"
    app_module.init_db()
    app_module.seed_trajets()
    app_module.definir_mot_de_passe("testuser", "testpass")
    app_module.app.config.update(TESTING=True)
    with app_module.app.test_client() as c:
        yield c


def test_page_sans_connexion_redirige_vers_login(client_anonyme):
    rep = client_anonyme.get("/", follow_redirects=False)
    assert rep.status_code == 302
    assert "/login" in rep.headers["Location"]


def test_api_sans_connexion_redirige_vers_login(client_anonyme):
    rep = client_anonyme.get("/api/trajets", follow_redirects=False)
    assert rep.status_code == 302
    assert "/login" in rep.headers["Location"]


def test_login_identifiants_valides(client_anonyme):
    rep = client_anonyme.post(
        "/login", data={"username": "testuser", "password": "testpass"}, follow_redirects=False
    )
    assert rep.status_code == 302
    rep2 = client_anonyme.get("/")
    assert rep2.status_code == 200


def test_login_identifiants_invalides(client_anonyme):
    rep = client_anonyme.post("/login", data={"username": "testuser", "password": "mauvais"})
    assert rep.status_code == 401
    assert "incorrect".encode() in rep.data.lower()


def test_logout_puis_acces_refuse(client):
    rep = client.get("/logout", follow_redirects=False)
    assert rep.status_code == 302
    rep2 = client.get("/api/trajets", follow_redirects=False)
    assert rep2.status_code == 302
    assert "/login" in rep2.headers["Location"]


def test_bootstrap_comptes_env(tmp_path, monkeypatch):
    """AUTH_USERS crée les comptes manquants au démarrage."""
    monkeypatch.setattr("core.db.DB_PATH", tmp_path / "test.db")
    monkeypatch.setenv("AUTH_USERS", "alice:motdepasse1, bob:motdepasse2")
    app_module.init_db()
    app_module._bootstrap_comptes_env()

    from core.db import verifier_mot_de_passe

    assert verifier_mot_de_passe("alice", "motdepasse1") is not None
    assert verifier_mot_de_passe("bob", "motdepasse2") is not None
    assert verifier_mot_de_passe("bob", "mauvais") is None


def test_bootstrap_comptes_env_resynchronise_mot_de_passe(tmp_path, monkeypatch):
    """Régression : un mot de passe changé dans AUTH_USERS doit être repris au
    redémarrage suivant, pas rester figé sur la première valeur créée."""
    monkeypatch.setattr("core.db.DB_PATH", tmp_path / "test.db")
    app_module.init_db()

    monkeypatch.setenv("AUTH_USERS", "salomon:ancien-mdp")
    app_module._bootstrap_comptes_env()

    monkeypatch.setenv("AUTH_USERS", "salomon:nouveau-mdp")
    app_module._bootstrap_comptes_env()

    from core.db import verifier_mot_de_passe

    assert verifier_mot_de_passe("salomon", "nouveau-mdp") is not None
    assert verifier_mot_de_passe("salomon", "ancien-mdp") is None


def test_supprimer_utilisateur(tmp_path, monkeypatch):
    monkeypatch.setattr("core.db.DB_PATH", tmp_path / "test.db")
    from core.db import definir_mot_de_passe, init_db, supprimer_utilisateur, verifier_mot_de_passe

    init_db()
    definir_mot_de_passe("a-retirer", "motdepasse")
    assert verifier_mot_de_passe("a-retirer", "motdepasse") is not None

    assert supprimer_utilisateur("a-retirer") is True
    assert verifier_mot_de_passe("a-retirer", "motdepasse") is None
    assert supprimer_utilisateur("a-retirer") is False  # déjà supprimé


def test_page_accueil(client):
    rep = client.get("/")
    assert rep.status_code == 200
    assert b"CA TRANS" in rep.data
    assert b"btn-calculer-devis" in rep.data
    assert b"btn-telecharger-pdf" in rep.data
    assert b"btn-mode-active" in rep.data
    assert b"Adresses / Rues" in rep.data
    assert b"Portfolio" in rep.data


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


def test_resoudre_trajet_inconnu(client):
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
    assert data["ttc_aller_retour"] == pytest.approx(2 * 566914.48, abs=1e-6)


def test_devis_capacites_supportees(client):
    for capacite in (63, 58, 51, 49):
        rep = client.post("/api/devis", json={"distance_km": 100, "nb_places": capacite})
        assert rep.status_code == 200
        data = rep.get_json()
        assert "ttc_aller_retour" in data


def test_devis_capacite_invalide(client):
    rep = client.post("/api/devis", json={"distance_km": 100, "nb_places": 50})
    assert rep.status_code == 400


def test_devis_distance_manquante(client):
    rep = client.post("/api/devis", json={})
    assert rep.status_code == 400


def test_devis_distance_nulle(client):
    rep = client.post("/api/devis", json={"distance_km": 0})
    assert rep.status_code == 400


def test_devis_valeur_negative(client):
    rep = client.post("/api/devis", json={"distance_km": 100, "frais_chauffeur": -1})
    assert rep.status_code == 400


def test_devis_non_fini(client):
    rep = client.post("/api/devis", json={"distance_km": float("inf")})
    assert rep.status_code == 400


def test_devis_pdf_reponse(client):
    rep = client.post(
        "/api/devis/pdf",
        json={"distance_km": 150, "frais_chauffeur": 12000, "frais_convoyeur": 5000},
    )
    assert rep.status_code == 200
    assert rep.content_type.startswith("application/pdf")
    assert "attachment" in rep.headers.get("Content-Disposition", "")
    assert rep.data.startswith(b"%PDF-")


def test_devis_pdf_parametres_invalides(client):
    rep = client.post("/api/devis/pdf", json={})
    assert rep.status_code == 400


def test_enregistrer_trajet(client):
    rep = client.post(
        "/api/trajet",
        json={"origine": "Test A", "destination": "Test B", "distance_km": 42, "source": "manuel"},
    )
    assert rep.status_code == 201
    trajets = client.get("/api/trajets").get_json()
    assert any(t["origine"] == "Test A" for t in trajets)


def test_modifier_trajet(client):
    rep = client.post(
        "/api/trajet",
        json={"origine": "Avant", "destination": "Après", "distance_km": 100, "source": "manuel"},
    )
    trajet_id = rep.get_json()["id"]
    rep2 = client.put(
        f"/api/trajet/{trajet_id}",
        json={"origine": "Modifié A", "destination": "Modifié B", "distance_km": 200},
    )
    assert rep2.status_code == 200
    trajets = client.get("/api/trajets").get_json()
    assert any(t["origine"] == "Modifié A" for t in trajets)


def test_supprimer_trajet(client):
    rep = client.post(
        "/api/trajet",
        json={"origine": "A supprimer", "destination": "Dest", "distance_km": 50, "source": "manuel"},
    )
    trajet_id = rep.get_json()["id"]
    rep2 = client.delete(f"/api/trajet/{trajet_id}")
    assert rep2.status_code == 200
    trajets = client.get("/api/trajets").get_json()
    assert not any(t["id"] == trajet_id for t in trajets)


def test_autocomplete_lieux_vide(client):
    rep = client.get("/api/lieux?q=ab")
    assert rep.status_code == 200
    assert rep.get_json() == []


def test_autocomplete_lieux_apres_insertion(client):
    rep = client.post("/api/lieu", json={"nom": "Bouaké Centre", "lat": 7.69, "lon": -5.03})
    assert rep.status_code == 201
    rep2 = client.get("/api/lieux?q=bouake")
    lieux = rep2.get_json()
    assert any("Bouaké" in l["nom"] or "BOUAKE" in l["nom"].upper() for l in lieux)


def test_lieu_idempotent(client):
    from core.db import inserer_lieu, rechercher_lieu
    inserer_lieu("Yamoussoukro", 6.82, -5.27, source="test")
    inserer_lieu("Yamoussoukro", 6.82, -5.27, source="test")
    l = rechercher_lieu("Yamoussoukro")
    assert l is not None
    assert l["nom"] == "Yamoussoukro"


def test_supprimer_trajet_inexistant(client):
    rep = client.delete("/api/trajet/99999")
    assert rep.status_code == 404


def test_geocoder_requete_courte(client):
    rep = client.get("/api/geocoder?q=ab")
    assert rep.status_code == 200
    assert rep.get_json() == []


def test_adresses_resultats_courtes(client):
    rep = client.get("/api/adresses?q=ab")
    assert rep.status_code == 200
    assert rep.get_json() == []


def test_adresses_aucun_resultat(client):
    rep = client.get("/api/adresses?q=zzzzzz-inconnu-xxxx")
    assert rep.status_code == 200
    assert rep.get_json() == []
