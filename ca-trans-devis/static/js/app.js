(() => {
  "use strict";

  const CI_CENTER = [7.5399, -5.5471];

  const state = {
    distanceKm: null,
    origineMarker: null,
    destinationMarker: null,
    routeLayer: null,
    modeClic: "origine",
    origineTexte: "",
    destinationTexte: "",
    statut: null,
  };

  // ---------------------------------------------------------------- carte
  const carte = L.map("carte").setView(CI_CENTER, 7);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap",
  }).addTo(carte);

  const iconeOrigine = L.icon({
    iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
    shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
    iconSize: [25, 41], iconAnchor: [12, 41], className: "marker-vert",
  });
  const iconeDestination = L.icon({
    iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
    shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
    iconSize: [25, 41], iconAnchor: [12, 41], className: "marker-rouge",
  });

  function placerMarqueur(latlng, type) {
    const icone = type === "origine" ? iconeOrigine : iconeDestination;
    const cle = type === "origine" ? "origineMarker" : "destinationMarker";
    if (state[cle]) {
      state[cle].setLatLng(latlng);
    } else {
      state[cle] = L.marker(latlng, { icon: icone, title: type }).addTo(carte);
    }
    majBoutonsCarte();
  }

  function dessinerItineraire(geometrie) {
    if (state.routeLayer) {
      carte.removeLayer(state.routeLayer);
      state.routeLayer = null;
    }
    if (!geometrie) return;
    state.routeLayer = L.geoJSON(geometrie, { style: { color: "#4fa695", weight: 5, opacity: 0.85 } }).addTo(carte);
    carte.fitBounds(state.routeLayer.getBounds(), { padding: [30, 30] });
  }

  carte.on("click", (e) => {
    placerMarqueur(e.latlng, state.modeClic);
  });

  document.querySelectorAll('input[name="mode-clic"]').forEach((el) => {
    el.addEventListener("change", (e) => { state.modeClic = e.target.value; });
  });

  function majBoutonsCarte() {
    const boutonItineraire = document.getElementById("btn-itineraire-carte");
    boutonItineraire.hidden = !(state.origineMarker && state.destinationMarker);
  }

  document.getElementById("btn-itineraire-carte").addEventListener("click", async () => {
    const o = state.origineMarker.getLatLng();
    const d = state.destinationMarker.getLatLng();
    const reponse = await appelApi("/api/itineraire", {
      origine: { lat: o.lat, lon: o.lng },
      destination: { lat: d.lat, lon: d.lng },
    });
    if (reponse.statut === "erreur") {
      afficherStatut("erreur", reponse.message);
      return;
    }
    state.distanceKm = reponse.distance_km;
    state.statut = "ors";
    afficherStatut("ors", reponse.message);
    dessinerItineraire(reponse.geometrie);
    document.getElementById("btn-enregistrer-trajet").hidden = false;
    calculerDevis();
  });

  // ------------------------------------------------------------ résolution
  async function appelApi(url, corps) {
    const options = corps
      ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps) }
      : { method: "GET" };
    const rep = await fetch(url, options);
    return rep.json();
  }

  function afficherStatut(type, message) {
    const el = document.getElementById("statut");
    el.hidden = false;
    el.className = `statut ${type}`;
    el.textContent = message;
  }

  function cacherBlocManuel() {
    document.getElementById("bloc-manuel").hidden = true;
  }

  document.getElementById("btn-resoudre").addEventListener("click", async () => {
    const origine = document.getElementById("origine").value.trim();
    const destination = document.getElementById("destination").value.trim();
    state.origineTexte = origine;
    state.destinationTexte = destination;

    if (!origine || !destination) {
      afficherStatut("erreur", "Renseignez l'origine et la destination.");
      return;
    }

    const reponse = await appelApi("/api/resoudre", { origine, destination });

    if (reponse.statut === "erreur") {
      afficherStatut("erreur", reponse.message);
      document.getElementById("bloc-manuel").hidden = false;
      state.distanceKm = null;
      return;
    }

    cacherBlocManuel();
    state.distanceKm = reponse.distance_km;
    state.statut = reponse.statut;
    afficherStatut(reponse.statut, reponse.message);

    if (reponse.origine_point) {
      placerMarqueur([reponse.origine_point.lat, reponse.origine_point.lon], "origine");
    }
    if (reponse.destination_point) {
      placerMarqueur([reponse.destination_point.lat, reponse.destination_point.lon], "destination");
    }
    dessinerItineraire(reponse.geometrie);

    document.getElementById("btn-enregistrer-trajet").hidden = reponse.statut !== "ors";

    calculerDevis();
  });

  document.getElementById("btn-distance-manuelle").addEventListener("click", () => {
    const valeur = parseFloat(document.getElementById("distance-manuelle").value);
    if (!valeur || valeur <= 0) return;
    state.distanceKm = valeur;
    state.statut = "manuel";
    afficherStatut("manuel", `Distance saisie manuellement : ${valeur} km`);
    cacherBlocManuel();
    document.getElementById("btn-enregistrer-trajet").hidden = false;
    calculerDevis();
  });

  document.getElementById("btn-enregistrer-trajet").addEventListener("click", async () => {
    if (!state.distanceKm) return;
    await appelApi("/api/trajet", {
      origine: state.origineTexte || "Point carte",
      destination: state.destinationTexte || "Point carte",
      distance_km: state.distanceKm,
      source: state.statut === "ors" ? "ors" : "manuel",
    });
    await chargerTrajets();
    afficherStatut(state.statut, "Trajet enregistré dans la base.");
  });

  // ------------------------------------------------------------- devis
  const champsDevis = [
    "nb-places", "conso-100km", "prix-litre", "frais-chauffeur",
    "frais-convoyeur", "peage", "marge-pct", "remise-montant",
  ];
  champsDevis.forEach((id) => {
    document.getElementById(id).addEventListener("input", calculerDevis);
  });

  document.querySelectorAll('input[name="nb-jours"]').forEach((el) => {
    el.addEventListener("change", async (e) => {
      const reponse = await appelApi(`/api/frais-mission?jours=${e.target.value}`);
      document.getElementById("frais-chauffeur").value = reponse.frais_chauffeur;
      document.getElementById("frais-convoyeur").value = reponse.frais_convoyeur;
      calculerDevis();
    });
  });

  function formaterFcfa(valeur) {
    return `${valeur.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} F CFA`;
  }

  async function calculerDevis() {
    const conteneur = document.getElementById("fiche-devis");
    if (!state.distanceKm) {
      conteneur.innerHTML = '<p class="muted">Résolvez d\'abord un itinéraire pour obtenir la distance.</p>';
      return;
    }

    const corps = {
      distance_km: state.distanceKm,
      nb_places: parseInt(document.getElementById("nb-places").value, 10) || 63,
      conso_100km: parseFloat(document.getElementById("conso-100km").value) || 0,
      prix_litre: parseFloat(document.getElementById("prix-litre").value) || 0,
      frais_chauffeur: parseFloat(document.getElementById("frais-chauffeur").value) || 0,
      frais_convoyeur: parseFloat(document.getElementById("frais-convoyeur").value) || 0,
      peage: parseFloat(document.getElementById("peage").value) || 0,
      marge_pct: parseFloat(document.getElementById("marge-pct").value) || 0,
      remise_montant: parseFloat(document.getElementById("remise-montant").value) || 0,
    };

    const r = await appelApi("/api/devis", corps);
    if (r.erreur) {
      conteneur.innerHTML = `<p class="statut erreur">${r.erreur}</p>`;
      return;
    }

    const lignesPlaces = r.prix_par_place
      .map((p) => `<tr><td>${p.places} places</td><td>${formaterFcfa(p.prix)}</td></tr>`)
      .join("");

    conteneur.innerHTML = `
      <dl>
        <dt>Distance aller simple</dt><dd>${state.distanceKm} km</dd>
        <dt>Consommation totale</dt><dd>${r.consommation_totale.toFixed(2)} L</dd>
        <dt>Coût carburant</dt><dd>${formaterFcfa(r.cout_carburant)}</dd>
        <dt>Coût carburant × 4 (facturé)</dt><dd>${formaterFcfa(r.cout_carburant_x4)}</dd>
        <dt>Total autres frais</dt><dd>${formaterFcfa(r.total_autres_frais)}</dd>
        <dt>Coût de revient total</dt><dd>${formaterFcfa(r.cout_revient_total)}</dd>
        <dt>Marge</dt><dd>${formaterFcfa(r.marge)}</dd>
        <dt>Prix de vente aller simple</dt><dd>${formaterFcfa(r.prix_vente_aller)}</dd>
        <dt>Montant HT aller-retour</dt><dd>${formaterFcfa(r.ht_aller_retour)}</dd>
        <dt>TVA (18 %)</dt><dd>${formaterFcfa(r.tva)}</dd>
        <dt>TTC aller-retour</dt><dd>${formaterFcfa(r.ttc_aller_retour)}</dd>
        <dt>TTC après remise</dt><dd>${formaterFcfa(r.ttc_apres_remise)}</dd>
        <div class="highlight"><span>TTC aller simple</span><span>${formaterFcfa(r.ttc_aller_simple)}</span></div>
      </dl>
      <table class="table-places">
        <thead><tr><th>Places</th><th>Prix / place (aller simple, sans TVA)</th></tr></thead>
        <tbody>${lignesPlaces}</tbody>
      </table>
      <p class="muted" style="margin-top:10px;">58 places × 2 (VIP, sans TVA) : ${formaterFcfa(r.prix_par_place_vip_58)}</p>
    `;
  }

  // ------------------------------------------------------- base de trajets
  let trajetsCache = [];

  async function chargerTrajets() {
    trajetsCache = await appelApi("/api/trajets");
    remplirDatalist();
    afficherTableTrajets(trajetsCache);
  }

  function remplirDatalist() {
    const datalist = document.getElementById("liste-lieux");
    const lieux = new Set();
    trajetsCache.forEach((t) => { lieux.add(t.origine); lieux.add(t.destination); });
    datalist.innerHTML = [...lieux].sort().map((l) => `<option value="${l}">`).join("");
  }

  function afficherTableTrajets(trajets) {
    const corpsTable = document.querySelector("#table-trajets tbody");
    corpsTable.innerHTML = trajets
      .map(
        (t) => `
        <tr data-id="${t.id}">
          <td>${t.origine}</td>
          <td>${t.destination}</td>
          <td>${t.distance_km ?? ""}</td>
          <td>${t.montant_aller ?? ""}</td>
          <td>${t.source}</td>
        </tr>`
      )
      .join("");

    corpsTable.querySelectorAll("tr").forEach((tr) => {
      tr.addEventListener("click", () => {
        const id = parseInt(tr.dataset.id, 10);
        const trajet = trajetsCache.find((t) => t.id === id);
        if (!trajet) return;
        document.getElementById("origine").value = trajet.origine;
        document.getElementById("destination").value = trajet.destination;
        if (trajet.distance_km) {
          state.distanceKm = trajet.distance_km;
          state.statut = "base";
          state.origineTexte = trajet.origine;
          state.destinationTexte = trajet.destination;
          afficherStatut("base", `Trajet réutilisé : ${trajet.origine} → ${trajet.destination} (${trajet.distance_km} km)`);
          calculerDevis();
        }
      });
    });
  }

  document.getElementById("filtre-trajets").addEventListener("input", (e) => {
    const f = e.target.value.trim().toLowerCase();
    const filtres = trajetsCache.filter(
      (t) => t.origine.toLowerCase().includes(f) || t.destination.toLowerCase().includes(f)
    );
    afficherTableTrajets(filtres);
  });

  chargerTrajets();
})();
