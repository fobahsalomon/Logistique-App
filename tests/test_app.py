import re
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


@pytest.fixture()
def client_admin(tmp_path, monkeypatch):
    """Client de test connecté avec le rôle ADMIN."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("core.db.DB_PATH", db_path)
    monkeypatch.setattr("core.routing.resoudre_itineraire", _routing_indisponible)
    monkeypatch.setattr("core.routing.calculer_itineraire", _routing_indisponible)
    app_module.app.secret_key = "cle-de-test"
    app_module.init_db()
    app_module.seed_trajets()
    app_module.definir_mot_de_passe("adminuser", "adminpass")
    app_module.definir_role("adminuser", "ADMIN")
    app_module.app.config.update(TESTING=True)
    with app_module.app.test_client() as c:
        c.post("/login", data={"username": "adminuser", "password": "adminpass"})
        yield c


def _payload_devis():
    return {
        "distance_km": 250,
        "nb_places": 63,
        "origine": "Abidjan",
        "destination": "San Pedro",
        "client_nom": "ACME",
        "responsable_flotte": "GNAYE SARAH",
        "date_debut": "2026-09-10",
        "date_fin": "2026-09-12",
    }


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


def test_supprimer_trajet_reellement(client):
    trajets_avant = client.get("/api/trajets").get_json()
    trajet = trajets_avant[0]

    rep = client.delete(f"/api/trajet/{trajet['id']}")
    assert rep.status_code == 200
    assert rep.get_json() == {"ok": True}

    trajets_apres = client.get("/api/trajets").get_json()
    assert all(itineraire["id"] != trajet["id"] for itineraire in trajets_apres)


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


def test_api_itineraire_accepte_lng_au_lieu_de_lon(client):
    rep = client.post(
        "/api/itineraire",
        json={
            "origine": {"lat": 5.33, "lng": -4.02},
            "destination": {"lat": 5.35, "lng": -3.98},
        },
    )
    assert rep.status_code == 200
    data = rep.get_json()
    assert data["statut"] == "erreur" or "distance_km" in data


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
    for capacite in (73, 63, 58, 51, 49):
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


# --------------------------------------------------------------- RBAC / rôles

def test_agent_ne_peut_pas_acceder_a_la_queue_de_validation(client):
    rep = client.get("/admin/proformas")
    assert rep.status_code == 403


def test_agent_ne_peut_pas_valider_une_proforma(client):
    rep = client.post("/api/proformas", json=_payload_devis())
    proforma_id = rep.get_json()["id"]

    rep = client.post(f"/admin/proformas/{proforma_id}/valider")
    assert rep.status_code == 403

    row = app_module.obtenir_proforma_par_id(proforma_id)
    assert row["statut"] == "EN_ATTENTE_VALIDATION"


def test_anonyme_redirige_pour_routes_admin(client_anonyme):
    for route in ("/admin/proformas", "/admin/proformas/historique", "/admin/utilisateurs", "/admin/audit"):
        rep = client_anonyme.get(route, follow_redirects=False)
        assert rep.status_code == 302
        assert "/login" in rep.headers["Location"]


# --------------------------------------------------------- workflow proformas

def test_soumission_proforma_sans_numero(client):
    rep = client.post("/api/proformas", json=_payload_devis())
    assert rep.status_code == 201
    data = rep.get_json()
    assert data["statut"] == "EN_ATTENTE_VALIDATION"

    row = app_module.obtenir_proforma_par_id(data["id"])
    assert row["numero_proforma"] is None


def test_apercu_pdf_ne_contient_jamais_de_numero_officiel(client):
    payload = dict(_payload_devis())
    payload["num_proforma"] = "CAT-PRO-999999"  # tentative de forcer un numéro côté client
    rep = client.post("/api/devis/pdf", json=payload)
    assert rep.status_code == 200
    assert rep.mimetype == "application/pdf"
    assert b"999999" not in rep.data


def test_admin_peut_valider_une_proforma(client_admin):
    rep = client_admin.post("/api/proformas", json=_payload_devis())
    proforma_id = rep.get_json()["id"]

    rep = client_admin.post(f"/admin/proformas/{proforma_id}/valider")
    assert rep.status_code == 200
    numero = rep.get_json()["numero_proforma"]
    assert re.fullmatch(r"PRO-\d{6}-\d{3}", numero)

    row = app_module.obtenir_proforma_par_id(proforma_id)
    assert row["statut"] == "VALIDE"
    assert row["numero_proforma"] == numero


def test_proforma_deja_validee_ne_peut_pas_etre_revalidee(client_admin):
    rep = client_admin.post("/api/proformas", json=_payload_devis())
    proforma_id = rep.get_json()["id"]

    rep = client_admin.post(f"/admin/proformas/{proforma_id}/valider")
    assert rep.status_code == 200

    rep = client_admin.post(f"/admin/proformas/{proforma_id}/valider")
    assert rep.status_code == 409


def test_numerotation_sequence_le_meme_jour(client_admin):
    id1 = client_admin.post("/api/proformas", json=_payload_devis()).get_json()["id"]
    id2 = client_admin.post("/api/proformas", json=_payload_devis()).get_json()["id"]

    numero1 = client_admin.post(f"/admin/proformas/{id1}/valider").get_json()["numero_proforma"]
    numero2 = client_admin.post(f"/admin/proformas/{id2}/valider").get_json()["numero_proforma"]

    jour1, seq1 = numero1.rsplit("-", 1)
    jour2, seq2 = numero2.rsplit("-", 1)
    assert jour1 == jour2
    assert int(seq2) == int(seq1) + 1


def test_numerotation_se_reinitialise_par_jour():
    """Teste directement core.db pour ne pas dépendre de la date système."""
    import tempfile
    from pathlib import Path as _Path

    import core.db as db

    with tempfile.TemporaryDirectory() as tmp:
        original_path = db.DB_PATH
        db.DB_PATH = _Path(tmp) / "test_numerotation.db"
        try:
            db.init_db()
            agent_id = db.creer_utilisateur("agent-jour", "x")
            admin_id = db.creer_utilisateur("admin-jour", "x", role="ADMIN")

            id_a = db.creer_proforma(agent_id, "{}", "{}", "2026-09-08T10:00:00")
            id_b = db.creer_proforma(agent_id, "{}", "{}", "2026-09-09T10:00:00")

            numero_a = db.valider_proforma(id_a, admin_id, jour="080926")
            numero_b = db.valider_proforma(id_b, admin_id, jour="090926")

            assert numero_a == "PRO-080926-001"
            assert numero_b == "PRO-090926-001"
        finally:
            db.DB_PATH = original_path


def test_rejet_proforma(client_admin):
    proforma_id = client_admin.post("/api/proformas", json=_payload_devis()).get_json()["id"]

    rep = client_admin.post(f"/admin/proformas/{proforma_id}/rejeter", json={"motif": "Client injoignable"})
    assert rep.status_code == 200

    row = app_module.obtenir_proforma_par_id(proforma_id)
    assert row["statut"] == "REJETE"
    assert row["motif_rejet"] == "Client injoignable"


def test_telechargement_pdf_proforma_validee(client_admin):
    proforma_id = client_admin.post("/api/proformas", json=_payload_devis()).get_json()["id"]
    numero = client_admin.post(f"/admin/proformas/{proforma_id}/valider").get_json()["numero_proforma"]

    rep = client_admin.get(f"/admin/proformas/{proforma_id}/pdf")
    assert rep.status_code == 200
    assert rep.mimetype == "application/pdf"
    assert numero in rep.headers["Content-Disposition"]


def test_proforma_rejetee_ne_peut_pas_etre_validee(client_admin):
    """Une proforma déjà rejetée ne peut plus être numérotée."""
    proforma_id = client_admin.post("/api/proformas", json=_payload_devis()).get_json()["id"]
    client_admin.post(f"/admin/proformas/{proforma_id}/rejeter", json={"motif": "Prix hors barème"})

    rep = client_admin.post(f"/admin/proformas/{proforma_id}/valider")
    assert rep.status_code == 409

    row = app_module.obtenir_proforma_par_id(proforma_id)
    assert row["statut"] == "REJETE"
    assert row["numero_proforma"] is None


def test_agent_ne_peut_pas_previsualiser(client):
    proforma_id = client.post("/api/proformas", json=_payload_devis()).get_json()["id"]
    rep = client.get(f"/admin/proformas/{proforma_id}/preview")
    assert rep.status_code == 403


def test_admin_peut_previsualiser_avant_validation(client_admin):
    proforma_id = client_admin.post("/api/proformas", json=_payload_devis()).get_json()["id"]

    rep = client_admin.get(f"/admin/proformas/{proforma_id}/preview")
    assert rep.status_code == 200
    assert rep.mimetype == "application/pdf"

    # La validation reste possible après un simple aperçu, la prévisualisation
    # ne consomme pas la proforma.
    row = app_module.obtenir_proforma_par_id(proforma_id)
    assert row["statut"] == "EN_ATTENTE_VALIDATION"


def test_previsualisation_indisponible_pour_proforma_validee(client_admin):
    proforma_id = client_admin.post("/api/proformas", json=_payload_devis()).get_json()["id"]
    client_admin.post(f"/admin/proformas/{proforma_id}/valider")

    rep = client_admin.get(f"/admin/proformas/{proforma_id}/preview")
    assert rep.status_code == 404


def test_mes_proformas_liste_les_demandes_de_lagent(client):
    client.post("/api/proformas", json=_payload_devis())

    rep = client.get("/mes-proformas")
    assert rep.status_code == 200
    assert b"EN ATTENTE" in rep.data


def test_rejet_enregistre_une_entree_audit(client_admin):
    proforma_id = client_admin.post("/api/proformas", json=_payload_devis()).get_json()["id"]
    client_admin.post(f"/admin/proformas/{proforma_id}/rejeter", json={"motif": "Trajet incorrect"})

    logs = app_module.lister_audit_logs(action="PROFORMA_REJETEE")
    assert any(log["details"] == "Trajet incorrect" for log in logs)


# ------------------------------------------------------------------- audit

def test_login_cree_une_entree_audit(client):
    logs = app_module.lister_audit_logs(action="LOGIN")
    assert any(log["username"] == "testuser" for log in logs)


def test_validation_proforma_cree_une_entree_audit(client_admin):
    proforma_id = client_admin.post("/api/proformas", json=_payload_devis()).get_json()["id"]
    numero = client_admin.post(f"/admin/proformas/{proforma_id}/valider").get_json()["numero_proforma"]

    logs = app_module.lister_audit_logs(action="PROFORMA_VALIDEE")
    assert any(log["details"] == numero for log in logs)


def test_reinitialisation_mot_de_passe_cree_une_entree_audit(client_admin):
    import core.db as db

    autre_id = db.creer_utilisateur("collegue-test", "ancien-mdp")

    rep = client_admin.post(
        f"/admin/utilisateurs/{autre_id}/reinitialiser-mot-de-passe",
        json={"password": "nouveau-mdp-1234"},
    )
    assert rep.status_code == 200

    logs = app_module.lister_audit_logs(action="MOT_DE_PASSE_REINITIALISE")
    assert any(log["details"] == "collegue-test" for log in logs)


# --------------------------------------------------------------- migration

def test_ajout_colonne_role_sur_db_existante(tmp_path):
    """Simule une DB de prod créée avant l'ajout de la colonne role."""
    import sqlite3

    db_path = tmp_path / "ancienne.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE utilisateurs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute("INSERT INTO utilisateurs (username, password_hash) VALUES ('ancien', 'hash')")
    conn.commit()

    import core.db as db
    db.init_db(conn)

    colonnes = {row[1] for row in conn.execute("PRAGMA table_info(utilisateurs)").fetchall()}
    assert "role" in colonnes

    role = conn.execute("SELECT role FROM utilisateurs WHERE username = 'ancien'").fetchone()[0]
    assert role == "AGENT"
    conn.close()


# --------------------------------------------------- protection dernier admin

def test_dernier_admin_ne_peut_pas_se_retrograder(tmp_path, monkeypatch):
    import core.db as db

    monkeypatch.setattr("core.db.DB_PATH", tmp_path / "test.db")
    db.init_db()
    db.creer_utilisateur("seul-admin", "x", role="ADMIN")

    with pytest.raises(db.DernierAdminError):
        db.definir_role("seul-admin", "AGENT")

    row = db.verifier_mot_de_passe("seul-admin", "x")
    assert row["role"] == "ADMIN"


def test_retrogradation_possible_si_plusieurs_admins(tmp_path, monkeypatch):
    import core.db as db

    monkeypatch.setattr("core.db.DB_PATH", tmp_path / "test.db")
    db.init_db()
    db.creer_utilisateur("admin1", "x", role="ADMIN")
    db.creer_utilisateur("admin2", "x", role="ADMIN")

    assert db.definir_role("admin1", "AGENT") is True

    row = db.verifier_mot_de_passe("admin1", "x")
    assert row["role"] == "AGENT"


def test_dernier_admin_ne_peut_pas_etre_supprime(tmp_path, monkeypatch):
    import core.db as db

    monkeypatch.setattr("core.db.DB_PATH", tmp_path / "test.db")
    db.init_db()
    db.creer_utilisateur("seul-admin", "x", role="ADMIN")

    with pytest.raises(db.DernierAdminError):
        db.supprimer_utilisateur("seul-admin")

    assert db.verifier_mot_de_passe("seul-admin", "x") is not None


def test_api_refuse_de_retrograder_le_dernier_admin(client_admin):
    users = app_module.lister_utilisateurs()
    admin_id = next(u["id"] for u in users if u["username"] == "adminuser")

    rep = client_admin.post(
        f"/admin/utilisateurs/{admin_id}/role", json={"role": "AGENT"}
    )
    assert rep.status_code == 409

    row = app_module.obtenir_utilisateur_par_id(admin_id)
    assert row["role"] == "ADMIN"


# --------------------------------------------------- auto-changement de mot de passe

def test_page_mon_compte_accessible(client):
    rep = client.get("/mon-compte")
    assert rep.status_code == 200
    assert b"Changer mon mot de passe" in rep.data


def test_mon_compte_inaccessible_sans_connexion(client_anonyme):
    rep = client_anonyme.get("/mon-compte", follow_redirects=False)
    assert rep.status_code == 302
    assert "/login" in rep.headers["Location"]


def test_changement_mot_de_passe_reussi(client):
    rep = client.post("/mon-compte/changement-mot-de-passe", json={
        "ancien_mot_de_passe": "testpass",
        "nouveau_mot_de_passe": "nouveau-mdp-1234",
        "confirmation": "nouveau-mdp-1234",
    })
    assert rep.status_code == 200

    from core.db import verifier_mot_de_passe
    assert verifier_mot_de_passe("testuser", "nouveau-mdp-1234") is not None
    assert verifier_mot_de_passe("testuser", "testpass") is None


def test_changement_mot_de_passe_refuse_si_ancien_incorrect(client):
    rep = client.post("/mon-compte/changement-mot-de-passe", json={
        "ancien_mot_de_passe": "mauvais-mdp",
        "nouveau_mot_de_passe": "nouveau-mdp-1234",
        "confirmation": "nouveau-mdp-1234",
    })
    assert rep.status_code == 403

    from core.db import verifier_mot_de_passe
    assert verifier_mot_de_passe("testuser", "testpass") is not None


def test_changement_mot_de_passe_refuse_si_confirmation_differente(client):
    rep = client.post("/mon-compte/changement-mot-de-passe", json={
        "ancien_mot_de_passe": "testpass",
        "nouveau_mot_de_passe": "nouveau-mdp-1234",
        "confirmation": "autre-chose",
    })
    assert rep.status_code == 400


def test_changement_mot_de_passe_refuse_si_trop_court(client):
    rep = client.post("/mon-compte/changement-mot-de-passe", json={
        "ancien_mot_de_passe": "testpass",
        "nouveau_mot_de_passe": "court",
        "confirmation": "court",
    })
    assert rep.status_code == 400


def test_changement_mot_de_passe_cree_une_entree_audit(client):
    client.post("/mon-compte/changement-mot-de-passe", json={
        "ancien_mot_de_passe": "testpass",
        "nouveau_mot_de_passe": "nouveau-mdp-1234",
        "confirmation": "nouveau-mdp-1234",
    })
    logs = app_module.lister_audit_logs(action="MOT_DE_PASSE_CHANGE")
    assert any(log["username"] == "testuser" for log in logs)


def test_page_connexion_ne_contient_plus_de_donnees_personnelles(client_anonyme):
    rep = client_anonyme.get("/login")
    assert rep.status_code == 200
    contenu = rep.data.decode()
    assert "fobahsalomon" not in contenu
    assert "fobahngouansalomon" not in contenu
    assert "+225" not in contenu
    assert "administrateur de votre entreprise" in contenu
