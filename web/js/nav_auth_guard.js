(function initSmartHomeNavAuthGuard() {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return;
  }

  let currentAuthState = { authenticated: false, tier: null, role: "" };

  function setElemHidden(el, hidden) {
    if (!el) return;
    if (typeof el.setAttribute === "function" && typeof el.removeAttribute === "function") {
      if (hidden) {
        el.setAttribute("aria-hidden", "true");
        el.setAttribute("inert", "");
        if (el.tagName === "A" || el.tagName === "BUTTON") {
          el.setAttribute("tabindex", "-1");
        }
      } else {
        el.removeAttribute("aria-hidden");
        el.removeAttribute("inert");
        if (el.getAttribute("tabindex") === "-1") {
          el.removeAttribute("tabindex");
        }
      }
    }
    el.hidden = !!hidden;
  }

  function guardUnauthHash(isAuthed) {
    if (isAuthed) return;
    try {
      if (window.location && window.location.hash && window.location.hash.length > 1) {
        if (window.history && typeof window.history.replaceState === "function") {
          window.history.replaceState(null, "", window.location.pathname + window.location.search);
        }
      }
    } catch (_) {}
  }

  function applyNavAuthState(sessionInfo) {
    const isAuthed = Boolean(sessionInfo && sessionInfo.authenticated === true);
    const tierNum = isAuthed ? Number(sessionInfo.tier || 0) : 0;
    const isOwner = isAuthed && tierNum === 1;
    currentAuthState = {
      authenticated: isAuthed,
      tier: isAuthed ? tierNum : null,
      role: isAuthed ? String(sessionInfo.role || "") : "",
    };

    try {
      if (document.body && document.body.classList) {
        document.body.classList.toggle("nav-authed", isAuthed);
        document.body.classList.toggle("nav-unauthed", !isAuthed);
      }
      if (typeof document.querySelectorAll === "function") {
        document.querySelectorAll('[data-auth-nav="true"]').forEach((el) => {
          setElemHidden(el, !isAuthed);
        });
        document.querySelectorAll('[data-auth-required="true"]').forEach((el) => {
          const ownerOnly = el.getAttribute("data-owner-only") === "true";
          setElemHidden(el, ownerOnly ? !isOwner : !isAuthed);
        });
        document.querySelectorAll('[data-owner-only="true"]').forEach((el) => {
          if (el.closest && (el.closest(".mobile-nav") || el.closest(".sidebar") || el.closest(".nav-sidebar") || el.closest("nav"))) {
            setElemHidden(el, !isOwner);
          }
        });
        document.querySelectorAll("[data-max-tier]").forEach((el) => {
          const maxTier = Number(el.getAttribute("data-max-tier") || 0);
          if (maxTier > 0) {
            setElemHidden(el, !isAuthed || tierNum <= 0 || tierNum > maxTier);
          }
        });
        document.querySelectorAll('[data-guest-only="true"]').forEach((el) => {
          setElemHidden(el, isAuthed);
        });
      }
    } catch (_) {}

    if (!isAuthed) {
      guardUnauthHash(false);
    }
  }

  async function syncFromServer() {
    applyNavAuthState({ authenticated: false });
    if (typeof window.fetch !== "function") return currentAuthState;
    try {
      const res = await fetch("/api/session/role", { credentials: "same-origin" });
      if (!res || !res.ok) {
        applyNavAuthState({ authenticated: false });
        return currentAuthState;
      }
      const data = await res.json().catch(() => ({}));
      if (data && data.authenticated === true) {
        applyNavAuthState(data);
        return currentAuthState;
      }
      applyNavAuthState({ authenticated: false });
      return currentAuthState;
    } catch (_) {
      applyNavAuthState({ authenticated: false });
      return currentAuthState;
    }
  }

  window.addEventListener("hashchange", () => {
    if (!currentAuthState.authenticated) {
      guardUnauthHash(false);
    }
  });

  window.addEventListener("smarthome:auth-changed", (ev) => {
    const detail = (ev && ev.detail) || {};
    applyNavAuthState(detail);
  });

  window.addEventListener("smarthome:spa-navigated", () => {
    applyNavAuthState(currentAuthState);
  });

  function hasClientAuthHint() {
    try {
      if (window.sessionStorage && (window.sessionStorage.getItem("session_token") || window.sessionStorage.getItem("mobileLoggedIn"))) {
        return true;
      }
      if (window.localStorage) {
        if (window.localStorage.getItem("session_token")) return true;
        const raw = window.localStorage.getItem("smarthome_auth_session");
        if (raw) {
          const parsed = JSON.parse(raw);
          if (parsed && (parsed.email || parsed.session_token)) return true;
        }
      }
    } catch (_) {}
    return false;
  }

  function bootAutoSync() {
    if (document.body && document.body.getAttribute("data-nav-guard-auto") === "true") {
      syncFromServer();
    } else if (!currentAuthState.authenticated) {
      guardUnauthHash(false);
    }
  }

  if (document.readyState === "loading") {
    window.addEventListener("DOMContentLoaded", bootAutoSync);
  } else {
    bootAutoSync();
  }

  window.SmartHomeNavGuard = {
    applyNavAuthState,
    syncFromServer,
    guardUnauthHash,
    getState: () => ({ ...currentAuthState }),
  };
})();
