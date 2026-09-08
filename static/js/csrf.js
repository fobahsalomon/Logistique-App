// Attache automatiquement le jeton CSRF (cookie non-httponly déposé par
// Flask-WTF à chaque réponse) à toute requête fetch() non-GET, sans avoir à
// modifier chaque appel individuellement. À charger avant tout script qui
// utilise fetch() pour une action POST/PUT/DELETE/PATCH.
(function () {
  function lireCookie(nom) {
    const match = document.cookie.match(new RegExp("(?:^|; )" + nom + "=([^;]*)"));
    return match ? decodeURIComponent(match[1]) : null;
  }

  const fetchNatif = window.fetch;
  window.fetch = function (ressource, options) {
    options = options || {};
    const methode = (options.method || "GET").toUpperCase();
    if (!["GET", "HEAD", "OPTIONS"].includes(methode)) {
      const jeton = lireCookie("csrf_token");
      if (jeton) {
        const entetes = new Headers(options.headers || {});
        entetes.set("X-CSRFToken", jeton);
        options = { ...options, headers: entetes };
      }
    }
    return fetchNatif(ressource, options);
  };
})();
