(() => {
  "use strict";

  // Côte d'Ivoire — centre et limites géographiques
  const CI_CENTER = [6.5, -5.5];
  const CI_BOUNDS = [[4.0, -8.6], [10.8, -2.4]];

  const state = {
    distanceKm: null,
    origineMarker: null,
    destinationMarker: null,
    originePoint: null,      // {lat, lon} résolu (autocomplete ou résolution texte)
    destinationPoint: null,
    routeLayer: null,
    routeBounds: null,       // L.LatLngBounds du tracé courant
    modeClic: "origine",
    origineTexte: "",
    destinationTexte: "",
    statut: null,
  };

  // ---------------------------------------------------------------- carte
  const carte = L.map("carte", {
    maxBounds: CI_BOUNDS,
    maxBoundsViscosity: 1.0,
    minZoom: 6,
  }).setView(CI_CENTER, 7);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap",
  }).addTo(carte);

  // Icônes de navigation : pins SVG colorés (vert départ, rouge arrivée)
  function _creerIconePin(couleur, bordure) {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 42" width="28" height="42">
      <path d="M14 0C6.27 0 0 6.27 0 14c0 5.26 2.87 9.87 7.13 12.34L14 42l6.87-15.66C25.13 23.87 28 19.26 28 14 28 6.27 21.73 0 14 0z"
        fill="${couleur}" stroke="${bordure}" stroke-width="1.5"/>
      <circle cx="14" cy="14" r="6" fill="white" opacity="0.85"/>
    </svg>`;
    return L.divIcon({
      html: svg,
      className: "",
      iconSize: [28, 42],
      iconAnchor: [14, 42],
      popupAnchor: [0, -42],
    });
  }

  const iconeOrigine      = _creerIconePin("#4caf6d", "#2d7a48");
  const iconeDestination  = _creerIconePin("#e2574c", "#a83128");

  function placerMarqueur(latlng, type) {
    const icone = type === "origine" ? iconeOrigine : iconeDestination;
    const cle   = type === "origine" ? "origineMarker" : "destinationMarker";
    if (state[cle]) {
      state[cle].setLatLng(latlng);
    } else {
      state[cle] = L.marker(latlng, { icon: icone, title: type }).addTo(carte);
    }
    majBoutonsCarte();
  }

  function dessinerItineraire(geometrie, etapes) {
    if (state.routeLayer) {
      carte.removeLayer(state.routeLayer);
      state.routeLayer = null;
    }
    state.routeBounds = null;
    afficherInstructions(etapes || []);

    if (!geometrie) {
      document.getElementById("btn-recentrer").hidden = true;
      return;
    }
    state.routeLayer = L.geoJSON(geometrie, {
      style: { color: "#4fa695", weight: 5, opacity: 0.85 },
    }).addTo(carte);
    state.routeBounds = state.routeLayer.getBounds();
    carte.fitBounds(state.routeBounds, { padding: [30, 30] });
    document.getElementById("btn-recentrer").hidden = false;
  }

  // --------------------------------------------------------- bouton recentrer
  document.getElementById("btn-recentrer").addEventListener("click", () => {
    if (state.routeBounds) {
      carte.fitBounds(state.routeBounds, { padding: [30, 30] });
    }
  });

  // ------------------------------------------------------ instructions turn-by-turn
  function afficherInstructions(etapes) {
    const panneau = document.getElementById("panneau-instructions");
    const liste   = document.getElementById("liste-instructions");
    if (!etapes || !etapes.length) {
      panneau.hidden = true;
      liste.innerHTML = "";
      return;
    }
    liste.innerHTML = etapes.map((e) => {
      const dist = e.distance_m >= 1000
        ? `${(e.distance_m / 1000).toFixed(1)} km`
        : `${Math.round(e.distance_m)} m`;
      const duree = e.duree_s >= 60
        ? `${Math.round(e.duree_s / 60)} min`
        : `${Math.round(e.duree_s)} s`;
      const li = document.createElement("li");
      li.className = "instruction-step";
      const texte = document.createElement("span");
      texte.className = "inst-texte";
      texte.textContent = e.instruction;
      const meta = document.createElement("span");
      meta.className = "inst-meta";
      meta.textContent = `${dist} · ${duree}`;
      li.appendChild(texte);
      li.appendChild(meta);
      return li.outerHTML;
    }).join("");
    panneau.hidden = false;
  }

  carte.on("click", (e) => {
    const pointKey = state.modeClic === "origine" ? "originePoint" : "destinationPoint";
    state[pointKey] = { lat: e.latlng.lat, lon: e.latlng.lng };
    placerMarqueur(e.latlng, state.modeClic);
  });

  document.querySelectorAll('input[name="mode-clic"]').forEach((el) => {
    el.addEventListener("change", (e) => { state.modeClic = e.target.value; });
  });

  function majBoutonsCarte() {
    document.getElementById("btn-itineraire-carte").hidden =
      !(state.origineMarker && state.destinationMarker);
  }

  document.getElementById("btn-itineraire-carte").addEventListener("click", async () => {
    const o = state.origineMarker.getLatLng();
    const d = state.destinationMarker.getLatLng();
    const reponse = await appelApi("/api/itineraire", {
      origine:      { lat: o.lat, lon: o.lng },
      destination:  { lat: d.lat, lon: d.lng },
    });
    if (reponse.statut === "erreur") {
      afficherStatut("erreur", reponse.message);
      return;
    }
    state.distanceKm = reponse.distance_km;
    state.statut = "ors";
    afficherStatut("ors", reponse.message);
    dessinerItineraire(reponse.geometrie, reponse.etapes);
    document.getElementById("btn-enregistrer-trajet").hidden = false;
    calculerDevis();
  });

  // ------------------------------------------------------------ API helper
  async function appelApi(url, corps, methode) {
    const method = methode || (corps != null ? "POST" : "GET");
    const options = { method };
    if (corps != null) {
      options.headers = { "Content-Type": "application/json" };
      options.body = JSON.stringify(corps);
    }
    const rep = await fetch(url, options);
    if (rep.status === 204) return {};
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

  // --------------------------------------------------------- autocomplete
  function setupAutocomplete(inputId, suggestionsId, type) {
    const input    = document.getElementById(inputId);
    const liste    = document.getElementById(suggestionsId);
    const pointKey = type === "origine" ? "originePoint" : "destinationPoint";
    const texteKey = type === "origine" ? "origineTexte" : "destinationTexte";
    let timer;

    input.addEventListener("input", () => {
      // Désynchronisation : le texte a changé, les coords ne sont plus valides
      state[pointKey] = null;
      clearTimeout(timer);
      const q = input.value.trim();
      if (q.length < 2) { liste.hidden = true; return; }
      timer = setTimeout(async () => {
        const lieux = await appelApi(`/api/lieux?q=${encodeURIComponent(q)}`);
        if (!Array.isArray(lieux) || !lieux.length) { liste.hidden = true; return; }
        liste.innerHTML = "";
        lieux.forEach((l) => {
          const li = document.createElement("li");
          li.textContent = l.nom;
          li.dataset.lat = l.lat;
          li.dataset.lon = l.lon;
          liste.appendChild(li);
        });
        liste.hidden = false;
      }, 250);
    });

    liste.addEventListener("click", (e) => {
      const li = e.target.closest("li");
      if (!li) return;
      const lat = parseFloat(li.dataset.lat);
      const lon = parseFloat(li.dataset.lon);
      const nom = li.textContent;
      input.value = nom;
      liste.hidden = true;
      state[pointKey] = { lat, lon };
      state[texteKey] = nom;
      placerMarqueur([lat, lon], type);
      carte.flyTo([lat, lon], 11);
      // Si les deux points sont connus → calcul automatique
      if (state.originePoint && state.destinationPoint) {
        calculerItineraireAuto();
      }
    });

    document.addEventListener("click", (e) => {
      if (!input.contains(e.target) && !liste.contains(e.target)) {
        liste.hidden = true;
      }
    });
  }

  setupAutocomplete("origine",     "suggestions-origine",     "origine");
  setupAutocomplete("destination", "suggestions-destination", "destination");

  async function calculerItineraireAuto() {
    const o = state.originePoint;
    const d = state.destinationPoint;
    const reponse = await appelApi("/api/itineraire", {
      origine:     { lat: o.lat, lon: o.lon },
      destination: { lat: d.lat, lon: d.lon },
    });
    if (reponse.statut === "erreur") {
      afficherStatut("erreur", reponse.message);
      return;
    }
    state.distanceKm = reponse.distance_km;
    state.statut = "ors";
    afficherStatut("ors", reponse.message);
    dessinerItineraire(reponse.geometrie, reponse.etapes);
    if (state.origineTexte && state.destinationTexte) {
      document.getElementById("btn-enregistrer-trajet").hidden = false;
    }
    calculerDevis();
  }

  // ------------------------------------------------------------ résolution texte
  document.getElementById("btn-resoudre").addEventListener("click", async () => {
    const origine     = document.getElementById("origine").value.trim();
    const destination = document.getElementById("destination").value.trim();
    state.origineTexte     = origine;
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
    state.statut     = reponse.statut;
    afficherStatut(reponse.statut, reponse.message);

    if (reponse.origine_point) {
      const o = reponse.origine_point;
      state.originePoint = { lat: o.lat, lon: o.lon };
      placerMarqueur([o.lat, o.lon], "origine");
    }
    if (reponse.destination_point) {
      const d = reponse.destination_point;
      state.destinationPoint = { lat: d.lat, lon: d.lon };
      placerMarqueur([d.lat, d.lon], "destination");
      carte.flyTo([d.lat, d.lon], 10);
    }
    dessinerItineraire(reponse.geometrie, reponse.etapes);

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
      origine:     state.origineTexte || "Point carte",
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

  document.getElementById("nb-jours").addEventListener("change", async (e) => {
    const jours = parseInt(e.target.value, 10) || 1;
    const reponse = await appelApi(`/api/frais-mission?jours=${jours}`);
    document.getElementById("frais-chauffeur").value = reponse.frais_chauffeur;
    document.getElementById("frais-convoyeur").value = reponse.frais_convoyeur;
    calculerDevis();
  });

  function formaterFcfa(valeur) {
    return `${valeur.toLocaleString("fr-FR", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })} F CFA`;
  }

  async function calculerDevis() {
    const conteneur = document.getElementById("fiche-devis");
    if (!state.distanceKm) {
      conteneur.innerHTML = '<p class="muted">Résolvez d\'abord un itinéraire pour obtenir la distance.</p>';
      return;
    }

    const corps = {
      distance_km:      state.distanceKm,
      nb_places:        parseInt(document.getElementById("nb-places").value, 10) || 63,
      conso_100km:      parseFloat(document.getElementById("conso-100km").value) || 0,
      prix_litre:       parseFloat(document.getElementById("prix-litre").value) || 0,
      frais_chauffeur:  parseFloat(document.getElementById("frais-chauffeur").value) || 0,
      frais_convoyeur:  parseFloat(document.getElementById("frais-convoyeur").value) || 0,
      peage:            parseFloat(document.getElementById("peage").value) || 0,
      marge_pct:        parseFloat(document.getElementById("marge-pct").value) || 0,
      remise_montant:   parseFloat(document.getElementById("remise-montant").value) || 0,
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
        <div class="highlight">
          <span>TTC aller simple</span>
          <span>${formaterFcfa(r.ttc_aller_simple)}</span>
        </div>
      </dl>
      <table class="table-places">
        <thead><tr><th>Places</th><th>Prix / place (aller simple, sans TVA)</th></tr></thead>
        <tbody>${lignesPlaces}</tbody>
      </table>
      <p class="muted" style="margin-top:10px;">
        58 places × 2 (VIP, sans TVA) : ${formaterFcfa(r.prix_par_place_vip_58)}
      </p>
    `;
  }

  // ------------------------------------------------------- base de trajets
  let trajetsCache = [];
  const corpsTable = document.querySelector("#table-trajets tbody");

  corpsTable.addEventListener("click", (e) => {
    const btnEdit = e.target.closest(".btn-edit");
    if (btnEdit) {
      e.stopPropagation();
      const id = parseInt(btnEdit.dataset.id, 10);
      const trajet = trajetsCache.find((t) => t.id === id);
      if (trajet) ouvrirModalEdition(trajet);
      return;
    }
    const tr = e.target.closest("tr[data-id]");
    if (tr) {
      const id = parseInt(tr.dataset.id, 10);
      const trajet = trajetsCache.find((t) => t.id === id);
      if (!trajet) return;
      document.getElementById("origine").value     = trajet.origine;
      document.getElementById("destination").value = trajet.destination;
      if (trajet.distance_km) {
        state.distanceKm     = trajet.distance_km;
        state.statut         = "base";
        state.origineTexte   = trajet.origine;
        state.destinationTexte = trajet.destination;
        state.originePoint   = null;
        state.destinationPoint = null;
        afficherStatut("base",
          `Trajet réutilisé : ${trajet.origine} → ${trajet.destination} (${trajet.distance_km} km)`
        );
        calculerDevis();
      }
    }
  });

  async function chargerTrajets() {
    trajetsCache = await appelApi("/api/trajets");
    afficherTableTrajets(trajetsCache);
  }

  function afficherTableTrajets(trajets) {
    corpsTable.innerHTML = trajets.map((t) => `
      <tr data-id="${t.id}">
        <td>${t.origine}</td>
        <td>${t.destination}</td>
        <td>${t.distance_km ?? ""}</td>
        <td>${t.montant_aller ?? ""}</td>
        <td>${t.source}</td>
        <td class="col-actions">
          <button class="btn btn-sm btn-edit" data-id="${t.id}">Modifier</button>
        </td>
      </tr>`).join("");
  }

  document.getElementById("filtre-trajets").addEventListener("input", (e) => {
    const f = e.target.value.trim().toLowerCase();
    const filtres = trajetsCache.filter(
      (t) => t.origine.toLowerCase().includes(f) || t.destination.toLowerCase().includes(f)
    );
    afficherTableTrajets(filtres);
  });

  // --------------------------------------------------- modal d'édition
  const modal = document.getElementById("modal-edition");

  function ouvrirModalEdition(trajet) {
    document.getElementById("edit-id").value          = trajet.id;
    document.getElementById("edit-origine").value     = trajet.origine;
    document.getElementById("edit-destination").value = trajet.destination;
    document.getElementById("edit-distance").value    = trajet.distance_km ?? "";
    document.getElementById("edit-montant").value     = trajet.montant_aller ?? "";
    modal.showModal();
  }

  document.getElementById("btn-annuler-edition").addEventListener("click", () => modal.close());

  document.getElementById("btn-sauvegarder-edition").addEventListener("click", async () => {
    const id = parseInt(document.getElementById("edit-id").value, 10);
    const distanceVal = document.getElementById("edit-distance").value;
    const corps = {
      origine:      document.getElementById("edit-origine").value.trim(),
      destination:  document.getElementById("edit-destination").value.trim(),
      distance_km:  distanceVal !== "" ? parseFloat(distanceVal) : null,
      montant_aller: document.getElementById("edit-montant").value.trim() || null,
    };
    if (!corps.origine || !corps.destination) return;
    await appelApi(`/api/trajet/${id}`, corps, "PUT");
    modal.close();
    await chargerTrajets();
  });

  document.getElementById("btn-supprimer-edition").addEventListener("click", async () => {
    if (!confirm("Supprimer ce trajet définitivement ?")) return;
    const id = parseInt(document.getElementById("edit-id").value, 10);
    await appelApi(`/api/trajet/${id}`, null, "DELETE");
    modal.close();
    await chargerTrajets();
  });

  chargerTrajets();
})();
