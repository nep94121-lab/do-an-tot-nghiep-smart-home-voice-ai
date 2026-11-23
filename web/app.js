// Forwarder script for legacy /static/app.js -> /static/js/app.js
(function () {
  "use strict";
  if (typeof document !== "undefined" && document.createElement) {
    var s = document.createElement("script");
    s.src = "/static/js/app.js";
    s.async = true;
    (document.head || document.documentElement).appendChild(s);
  }
})();
