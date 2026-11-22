(function initSmartHomeSpaRouter() {
  if (typeof window === "undefined" || typeof document === "undefined" || window.__shSpaRouterLoaded) {
    return;
  }
  window.__shSpaRouterLoaded = true;

  const SPA_ROUTES = new Set(["/", "/automation", "/auth", "/wokwi", "/logs"]);
  const ROUTE_CSS = {
    "/": "/static/css/style.css",
    "/automation": "/static/css/automation_panel.css",
    "/auth": "/static/css/auth.css",
    "/wokwi": "/static/css/wokwi.css",
    "/logs": "/static/css/logs.css",
  };
  const ROUTE_TITLES = {
    "/": "Tổng quan · Nhà thông minh",
    "/automation": "Tự động hóa · Nhà thông minh",
    "/auth": "Xác thực & Phân quyền · Nhà thông minh",
    "/wokwi": "Phần cứng — Nhà thông minh",
    "/logs": "Nhật ký · Nhà thông minh",
  };

  const viewCache = new Map();
  const htmlCache = new Map();
  const inflightHtml = new Map();
  const routeStyles = new Map();
  const loadedScriptSrcs = new Set();
  let currentRoute = normalizeRoute(window.location.pathname) || "/";
  let initialized = false;
  let navSerial = 0;

  function normalizeRoute(pathname) {
    const clean = String(pathname || "/").replace(/\/+$/, "") || "/";
    return SPA_ROUTES.has(clean) ? clean : "";
  }

  function injectSpaBaseCss() {
    if (document.getElementById("shSpaBaseCss")) return;
    const styleEl = document.createElement("style");
    styleEl.id = "shSpaBaseCss";
    styleEl.textContent = [
      ".spa-route-view.inactive{content-visibility:hidden;position:fixed;top:0;left:0;width:100%;height:0;overflow:hidden;pointer-events:none;visibility:hidden;}",
      "@supports not (content-visibility: hidden){.spa-route-view.inactive{display:none;}}",
      "::view-transition-old(root),::view-transition-new(root){animation-duration:90ms;}",
      "@media (prefers-reduced-motion:reduce){::view-transition-group(*),::view-transition-old(*),::view-transition-new(*){animation:none !important;}}",
    ].join("\n");
    document.head.appendChild(styleEl);
  }

  function recordLoadedScripts() {
    document.querySelectorAll("script[src]").forEach((s) => {
      try {
        const u = new URL(s.getAttribute("src"), window.location.origin);
        loadedScriptSrcs.add(u.pathname);
      } catch (_) {}
    });
  }

  function tagInitialRouteStyles(route) {
    const list = [];
    const expectedCss = ROUTE_CSS[route] || "";
    document.querySelectorAll('link[rel="stylesheet"]').forEach((lnk) => {
      try {
        const u = new URL(lnk.getAttribute("href"), window.location.origin);
        if (u.pathname === expectedCss || u.pathname.startsWith("/static/css/")) {
          lnk.setAttribute("data-spa-route-css", route);
          list.push(lnk);
        }
      } catch (_) {}
    });
    document.querySelectorAll("head style:not(#shSpaBaseCss)").forEach((st) => {
      st.setAttribute("data-spa-route-css", route);
      list.push(st);
    });
    routeStyles.set(route, list);
  }

  function wrapInitialBodyView(route) {
    if (viewCache.has(route)) return viewCache.get(route);
    const wrapper = document.createElement("div");
    wrapper.className = "spa-route-view";
    wrapper.setAttribute("data-spa-route", route);
    wrapper.setAttribute("tabindex", "-1");
    const children = Array.from(document.body.childNodes);
    for (const node of children) {
      if (node.nodeType === 1 && node.tagName === "SCRIPT") continue;
      wrapper.appendChild(node);
    }
    document.body.insertBefore(wrapper, document.body.firstChild);
    viewCache.set(route, wrapper);
    return wrapper;
  }

  function ensureInitialized() {
    if (initialized) return;
    initialized = true;
    injectSpaBaseCss();
    recordLoadedScripts();
    tagInitialRouteStyles(currentRoute);
    wrapInitialBodyView(currentRoute);
  }

  function prefetchHtml(route) {
    if (!SPA_ROUTES.has(route) || viewCache.has(route) || htmlCache.has(route)) {
      return Promise.resolve(htmlCache.get(route) || null);
    }
    if (inflightHtml.has(route)) return inflightHtml.get(route);
    const p = fetch(route, {
      credentials: "same-origin",
      headers: { "X-Requested-With": "sh-spa" },
    })
      .then((res) => (res.ok ? res.text() : ""))
      .then((html) => {
        if (html) htmlCache.set(route, html);
        return html;
      })
      .catch(() => "")
      .finally(() => {
        inflightHtml.delete(route);
      });
    inflightHtml.set(route, p);
    return p;
  }

  function isBlockedByAuthGate() {
    try {
      if (document.body && document.body.classList) {
        if (document.body.classList.contains("dashboard-logged-out") || document.body.classList.contains("login-gate-open")) {
          return true;
        }
      }
      const gate = document.getElementById("homeLoginGateModal");
      if (gate && !gate.classList.contains("hidden")) {
        return true;
      }
    } catch (_) {}
    return false;
  }

  function scheduleIdlePrefetch() {
    const run = () => {
      if (isBlockedByAuthGate()) return;
      SPA_ROUTES.forEach((r) => {
        if (r !== currentRoute) {
          prefetchHtml(r);
          const cssHref = ROUTE_CSS[r];
          if (cssHref && !document.querySelector(`link[rel="prefetch"][href="${cssHref}"]`)) {
            const l = document.createElement("link");
            l.rel = "prefetch";
            l.href = cssHref;
            l.as = "style";
            document.head.appendChild(l);
          }
        }
      });
    };
    if (typeof window.requestIdleCallback === "function") {
      window.requestIdleCallback(run, { timeout: 600 });
    } else {
      setTimeout(run, 120);
    }
  }

  function loadRouteStylesFromDoc(route, parsedDoc) {
    if (routeStyles.has(route)) return Promise.resolve();
    const list = [];
    const promises = [];
    const expectedCss = ROUTE_CSS[route] || "";
    parsedDoc.querySelectorAll('link[rel="stylesheet"]').forEach((lnk) => {
      const href = lnk.getAttribute("href") || "";
      let pathname = href;
      try {
        pathname = new URL(href, window.location.origin).pathname;
      } catch (_) {}
      if (pathname === expectedCss || pathname.startsWith("/static/css/")) {
        const cloned = document.createElement("link");
        cloned.rel = "stylesheet";
        cloned.href = href;
        cloned.media = "not all";
        cloned.setAttribute("data-spa-route-css", route);
        promises.push(
          new Promise((resolve) => {
            const done = () => resolve();
            cloned.addEventListener("load", done, { once: true });
            cloned.addEventListener("error", done, { once: true });
            setTimeout(done, 180);
          })
        );
        document.head.appendChild(cloned);
        list.push(cloned);
      }
    });
    parsedDoc.querySelectorAll("head style").forEach((st) => {
      const cloned = document.createElement("style");
      cloned.textContent = st.textContent || "";
      cloned.media = "not all";
      cloned.setAttribute("data-spa-route-css", route);
      document.head.appendChild(cloned);
      list.push(cloned);
    });
    routeStyles.set(route, list);
    return Promise.all(promises);
  }

  async function loadRouteScriptsSequentially(parsedDoc) {
    const scripts = Array.from(parsedDoc.querySelectorAll("script[src]"));
    for (const sc of scripts) {
      const src = sc.getAttribute("src") || "";
      let pathname = "";
      try {
        pathname = new URL(src, window.location.origin).pathname;
      } catch (_) {}
      if (!pathname || pathname === "/static/js/spa_nav.js" || loadedScriptSrcs.has(pathname)) {
        continue;
      }
      loadedScriptSrcs.add(pathname);
      await new Promise((resolve) => {
        const el = document.createElement("script");
        el.src = src;
        el.async = false;
        el.onload = resolve;
        el.onerror = resolve;
        document.body.appendChild(el);
      });
    }
  }

  function applyActiveRouteStyles(targetRoute) {
    routeStyles.forEach((els, r) => {
      const active = r === targetRoute;
      for (const el of els) {
        if ("media" in el) el.media = active ? "all" : "not all";
        if ("disabled" in el) el.disabled = !active;
      }
    });
  }

  function applyActiveViewVisibility(targetRoute) {
    viewCache.forEach((wrapper, r) => {
      if (r === targetRoute) {
        wrapper.classList.remove("inactive");
        wrapper.setAttribute("aria-hidden", "false");
        wrapper.removeAttribute("inert");
      } else {
        wrapper.classList.add("inactive");
        wrapper.setAttribute("aria-hidden", "true");
        wrapper.setAttribute("inert", "inert");
      }
    });
  }

  function focusActiveView(route) {
    const activeView = viewCache.get(route);
    if (!activeView) return;
    const focusTarget = activeView.querySelector("main h1, header h1, h1, main") || activeView;
    if (focusTarget && typeof focusTarget.focus === "function") {
      if (!focusTarget.hasAttribute("tabindex")) {
        focusTarget.setAttribute("tabindex", "-1");
      }
      try {
        focusTarget.focus({ preventScroll: true });
      } catch (_) {}
    }
  }

  async function navigateSpa(rawTarget, options = {}) {
    ensureInitialized();
    const targetUrl = new URL(rawTarget, window.location.origin);
    if (targetUrl.origin !== window.location.origin) {
      window.location.href = targetUrl.href;
      return;
    }
    const targetRoute = normalizeRoute(targetUrl.pathname);
    if (!targetRoute) {
      window.location.href = targetUrl.href;
      return;
    }
    if (isBlockedByAuthGate()) {
      return;
    }
    const nextHref = `${targetUrl.pathname}${targetUrl.search}${targetUrl.hash}`;
    const prevRoute = currentRoute;
    if (targetRoute === prevRoute && !options.force) {
      if (options.pushHistory !== false && nextHref !== window.location.pathname + window.location.search + window.location.hash) {
        window.history.pushState({ spaRoute: targetRoute }, "", nextHref);
      }
      return;
    }

    const mySerial = ++navSerial;
    const t0 = performance.now();
    let parsedDoc = null;
    let isFirstMount = !viewCache.has(targetRoute);

    if (isFirstMount) {
      const html = htmlCache.get(targetRoute) || (await prefetchHtml(targetRoute));
      if (mySerial !== navSerial) return;
      if (!html) {
        window.location.href = targetUrl.href;
        return;
      }
      parsedDoc = new DOMParser().parseFromString(html, "text/html");
      await loadRouteStylesFromDoc(targetRoute, parsedDoc);
      if (mySerial !== navSerial) return;

      const wrapper = document.createElement("div");
      wrapper.className = "spa-route-view inactive";
      wrapper.setAttribute("data-spa-route", targetRoute);
      wrapper.setAttribute("aria-hidden", "true");
      wrapper.setAttribute("inert", "inert");
      wrapper.setAttribute("tabindex", "-1");
      const nodes = Array.from(parsedDoc.body.childNodes);
      for (const n of nodes) {
        if (n.nodeType === 1 && n.tagName === "SCRIPT") continue;
        wrapper.appendChild(document.importNode(n, true));
      }
      document.body.insertBefore(wrapper, document.body.firstChild);
      viewCache.set(targetRoute, wrapper);
    }

    const nextTitle = (parsedDoc && parsedDoc.title) || ROUTE_TITLES[targetRoute] || document.title;
    const updateDom = () => {
      applyActiveRouteStyles(targetRoute);
      applyActiveViewVisibility(targetRoute);
      document.title = nextTitle;
      currentRoute = targetRoute;
      if (options.pushHistory !== false) {
        window.history.pushState({ spaRoute: targetRoute }, nextTitle, nextHref);
      }
    };

    const reduceMotion = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (typeof document.startViewTransition === "function" && !reduceMotion) {
      let finishedPromise = Promise.resolve();
      try {
        const vt = document.startViewTransition(() => updateDom());
        finishedPromise = vt.finished.catch(() => {});
      } catch (_) {
        updateDom();
      }
      window.__lastSpaSwapMs = Math.round((performance.now() - t0) * 100) / 100;
      await finishedPromise;
      focusActiveView(targetRoute);
    } else {
      updateDom();
      window.__lastSpaSwapMs = Math.round((performance.now() - t0) * 100) / 100;
      focusActiveView(targetRoute);
    }

    if (isFirstMount && parsedDoc) {
      await loadRouteScriptsSequentially(parsedDoc);
    }

    const totalMs = Math.round((performance.now() - t0) * 100) / 100;
    window.__lastSpaNavMs = totalMs;
    window.dispatchEvent(
      new CustomEvent("smarthome:spa-navigated", {
        detail: {
          from: prevRoute,
          to: targetRoute,
          firstMount: isFirstMount,
          durationMs: totalMs,
          swapMs: window.__lastSpaSwapMs,
        },
      })
    );
    window.dispatchEvent(
      new CustomEvent("sh:spa-route", {
        detail: { from: prevRoute, to: targetRoute, firstMount: isFirstMount },
      })
    );
    if (typeof window.initSmartHomeAutomationPanel === "function") {
      try {
        window.initSmartHomeAutomationPanel();
      } catch (_) {}
    }
  }

  document.addEventListener("click", (ev) => {
    if (ev.defaultPrevented || ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) {
      return;
    }
    const anchor = ev.target && ev.target.closest ? ev.target.closest("a[href]") : null;
    if (!anchor) return;
    if (anchor.hasAttribute("download") || (anchor.getAttribute("target") && anchor.getAttribute("target") !== "_self")) {
      return;
    }
    const rawHref = anchor.getAttribute("href") || "";
    if (!rawHref || rawHref.startsWith("#") || rawHref.startsWith("mailto:") || rawHref.startsWith("tel:")) {
      return;
    }
    let parsedUrl;
    try {
      parsedUrl = new URL(anchor.href, window.location.origin);
    } catch (_) {
      return;
    }
    if (parsedUrl.origin !== window.location.origin) return;
    const targetRoute = normalizeRoute(parsedUrl.pathname);
    if (!targetRoute) return;
    if (isBlockedByAuthGate()) {
      ev.preventDefault();
      return;
    }
    ev.preventDefault();
    navigateSpa(parsedUrl.href, { pushHistory: true });
  });

  document.addEventListener(
    "pointerenter",
    (ev) => {
      const anchor = ev.target && ev.target.closest ? ev.target.closest("a[href]") : null;
      if (!anchor) return;
      try {
        const u = new URL(anchor.href, window.location.origin);
        const r = u.origin === window.location.origin ? normalizeRoute(u.pathname) : "";
        if (r && r !== currentRoute) prefetchHtml(r);
      } catch (_) {}
    },
    { capture: true, passive: true }
  );

  window.addEventListener("popstate", () => {
    const r = normalizeRoute(window.location.pathname);
    if (r) {
      navigateSpa(window.location.href, { pushHistory: false });
    }
  });

  if (document.readyState === "loading") {
    window.addEventListener("DOMContentLoaded", () => {
      ensureInitialized();
      scheduleIdlePrefetch();
    });
  } else {
    ensureInitialized();
    scheduleIdlePrefetch();
  }

  window.shNavigateSpa = navigateSpa;
})();
