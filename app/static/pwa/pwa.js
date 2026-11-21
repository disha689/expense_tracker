// Makes Spendly installable: registers the service worker and, when the browser allows installing,
// shows a small "Install Spendly" bar in the bottom corner (it can be closed, and stays closed for 30 days).
(function () {
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js").catch(function () {});
    });
  }

  var KEY = "spendly-install-closed";
  var THIRTY_DAYS = 30 * 24 * 3600 * 1000;
  var saved = null;
  var installed = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;

  function closedRecently() {
    try {
      var t = parseInt(localStorage.getItem(KEY) || "0", 10);
      return t > 0 && Date.now() - t < THIRTY_DAYS;
    } catch (e) {
      return false;
    }
  }

  var style = document.createElement("style");
  style.textContent =
    "#installBar{position:fixed;right:16px;bottom:16px;z-index:60;display:flex;align-items:center;gap:6px;" +
    "background:#14528f;color:#fff;border-radius:999px;padding:6px 6px 6px 18px;" +
    "box-shadow:0 6px 20px rgba(16,26,43,.3);font:600 14px/1.2 Inter,system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif}" +
    "#installBar button{font:inherit;cursor:pointer;border:0;border-radius:999px}" +
    "#installBtn{background:#fff;color:#14528f;padding:9px 16px}" +
    "#installClose{background:transparent;color:#fff;width:34px;height:34px;font-size:20px;line-height:1}" +
    "#installClose:hover,#installBtn:hover{opacity:.88}" +
    "#installBar button:focus-visible{outline:2px solid #fff;outline-offset:2px}" +
    "@media (max-width:800px){#installBar{left:16px;right:16px;justify-content:space-between;" +
    "bottom:calc(16px + env(safe-area-inset-bottom,0px))}}";
  document.head.appendChild(style);

  function removeBar() {
    var bar = document.getElementById("installBar");
    if (bar) bar.remove();
  }

  function showBar() {
    if (!saved || installed || closedRecently() || document.getElementById("installBar")) return;
    var bar = document.createElement("div");
    bar.id = "installBar";
    bar.setAttribute("role", "region");
    bar.setAttribute("aria-label", "Install Spendly");

    var text = document.createElement("span");
    text.textContent = "Install Spendly";

    var install = document.createElement("button");
    install.type = "button";
    install.id = "installBtn";
    install.textContent = "Install";
    install.onclick = function () {
      var event = saved;
      saved = null;
      removeBar();
      event.prompt();
    };

    var close = document.createElement("button");
    close.type = "button";
    close.id = "installClose";
    close.setAttribute("aria-label", "Hide this");
    close.textContent = "\u00D7";
    close.onclick = function () {
      try { localStorage.setItem(KEY, String(Date.now())); } catch (e) {}
      removeBar();
    };

    var actions = document.createElement("span");
    actions.style.cssText = "display:flex;align-items:center;gap:2px";
    actions.appendChild(install);
    actions.appendChild(close);
    bar.appendChild(text);
    bar.appendChild(actions);
    document.body.appendChild(bar);
  }

  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault();
    saved = event;
    showBar();
  });
  window.addEventListener("appinstalled", function () {
    saved = null;
    removeBar();
  });
})();
