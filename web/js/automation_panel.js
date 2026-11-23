"use strict";

(function initAutomationPanelModule() {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return;
  }

  // ==================== AUTH FETCH HELPER ====================
  function getSessionToken() {
    try {
      const tok =
        (window.sessionStorage && window.sessionStorage.getItem("session_token")) ||
        (window.localStorage && window.localStorage.getItem("session_token")) ||
        "";
      if (tok) return tok;
      if (window.localStorage) {
        const raw = window.localStorage.getItem("smarthome_auth_session");
        if (raw) {
          const parsed = JSON.parse(raw);
          if (parsed && parsed.session_token) return String(parsed.session_token);
        }
      }
    } catch (_) {}
    return "";
  }

  async function apiFetch(url, options) {
    const opts = Object.assign({ credentials: "same-origin" }, options || {});
    const headers = Object.assign({}, opts.headers || {});
    const tok = getSessionToken();
    if (tok && !headers["X-Session-Token"] && !headers["x-session-token"] && !headers["Authorization"]) {
      headers["X-Session-Token"] = tok;
    }
    opts.headers = headers;
    return window.fetch(url, opts);
  }

  // ==================== DOMAIN CONSTANTS (LOCKED 6 DEVICES + SENSORS) ====================
  const TARGET_DEVICES = [
    { id: "living_room_light", label: "Đèn phòng khách", kind: "relay" },
    { id: "bedroom_light", label: "Đèn phòng ngủ", kind: "relay" },
    { id: "garden_pump", label: "Máy bơm tưới cây", kind: "relay" },
    { id: "main_door", label: "Cửa chính", kind: "door" },
    { id: "alarm_siren", label: "Còi báo động", kind: "relay" },
    { id: "speaker_amp", label: "Nguồn mạch loa PAM8403", kind: "relay" },
    { id: "all_lights", label: "Tất cả đèn", kind: "group" },
    { id: "all_devices", label: "Tất cả thiết bị", kind: "group" },
  ];

  const DEVICE_LABELS = {
    living_room_light: "Đèn phòng khách",
    bedroom_light: "Đèn phòng ngủ",
    garden_pump: "Máy bơm tưới cây",
    main_door: "Cửa chính",
    alarm_siren: "Còi báo động",
    speaker_amp: "Nguồn mạch loa PAM8403",
    all_lights: "Tất cả đèn",
    all_devices: "Tất cả thiết bị",
  };

  const ACTION_LABELS = {
    turn_on: "Bật",
    turn_off: "Tắt",
    open: "Mở cửa",
    open_door: "Mở cửa",
    close: "Đóng cửa",
    close_door: "Đóng cửa",
  };

  const CONDITION_SOURCES = [
    { id: "temp_sensor", label: "Nhiệt độ DHT11 (°C)", kind: "numeric", unit: "°C", defaultOp: ">", defaultVal: 30, defaultHyst: 1 },
    { id: "humidity_sensor", label: "Độ ẩm không khí DHT11 (%)", kind: "numeric", unit: "%", defaultOp: ">", defaultVal: 75, defaultHyst: 2 },
    { id: "soil_sensor", label: "Độ ẩm đất A0 (%)", kind: "numeric", unit: "%", defaultOp: "<", defaultVal: 40, defaultHyst: 5 },
    { id: "sound_sensor", label: "Âm thanh KY-037", kind: "state", states: [{ v: "LOUD", l: "Có tiếng động lớn" }, { v: "QUIET", l: "Yên tĩnh" }] },
    { id: "main_door", label: "Cửa chính", kind: "state", states: [{ v: "OPEN", l: "Đang mở" }, { v: "CLOSED", l: "Đang đóng" }] },
    { id: "living_room_light", label: "Đèn phòng khách", kind: "state", states: [{ v: "ON", l: "Đang bật" }, { v: "OFF", l: "Đang tắt" }] },
    { id: "bedroom_light", label: "Đèn phòng ngủ", kind: "state", states: [{ v: "ON", l: "Đang bật" }, { v: "OFF", l: "Đang tắt" }] },
    { id: "garden_pump", label: "Máy bơm tưới cây", kind: "state", states: [{ v: "ON", l: "Đang bật" }, { v: "OFF", l: "Đang tắt" }] },
    { id: "alarm_siren", label: "Còi báo động", kind: "state", states: [{ v: "ON", l: "Đang bật" }, { v: "OFF", l: "Đang tắt" }] },
    { id: "speaker_amp", label: "Nguồn mạch loa PAM8403", kind: "state", states: [{ v: "ON", l: "Đang bật" }, { v: "OFF", l: "Đang tắt" }] },
    { id: "time_window", label: "Khung giờ", kind: "time_window" },
    { id: "house_mode", label: "Chế độ nhà", kind: "state", states: [{ v: "HOME", l: "Ở nhà" }, { v: "AWAY", l: "Vắng nhà" }] },
  ];

  const SOURCE_MAP = {};
  CONDITION_SOURCES.forEach((s) => {
    SOURCE_MAP[s.id] = s;
  });

  const WEEKDAY_NAMES_VI = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"];
  const WEEKDAY_SHORT_VI = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];

  const REPEAT_LABELS_VI = {
    once: "Một lần",
    daily: "Hằng ngày",
    hourly: "Mỗi giờ",
    weekly: "Theo thứ",
  };

  // ==================== MODULE STATE ====================
  const state = {
    registry: null,
    activeTab: "all",
    houseMode: "HOME",
    tier: 1,
    currentUserId: "",
    currentUserName: "",
    systemPolicies: {},
    timers: [],
    schedules: [],
    commands: [],
    rules: [],
    lastFetchAt: 0,
    sse: null,
    sseConnected: false,
    pollHandle: null,
    tickHandle: null,
    pendingModalConfirm: null,
    pendingPageConfirm: null,
    pendingAiConfirm: null,
    authState: "unknown", // "ok" | "unauth" | "guest"
  };

  // ==================== UTILITIES ====================
  function escapeHtml(str) {
    return String(str == null ? "" : str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function getActiveRoot() {
    const activeView = document.querySelector(".spa-route-view:not(.inactive)");
    return activeView || document;
  }

  function q(selector, root) {
    const scope = root || getActiveRoot();
    return scope ? scope.querySelector(selector) : null;
  }

  function qAll(selector, root) {
    const scope = root || getActiveRoot();
    return scope ? Array.from(scope.querySelectorAll(selector)) : [];
  }

  function isAutomationPageActive() {
    return Boolean(q("#autoSectionsGrid"));
  }

  function isDashboardPanelActive() {
    return Boolean(q("#secAutomation") || q("#compoundRuleList"));
  }

  function normalizeActionForDevice(deviceId, rawAction) {
    const act = String(rawAction || "").trim().toLowerCase();
    if (deviceId === "main_door") {
      if (act === "open" || act === "open_door" || act === "turn_on") return "open";
      return "close";
    }
    if (act === "turn_off" || act === "close" || act === "close_door") return "turn_off";
    return "turn_on";
  }

  function getActionOptionsForDevice(deviceId) {
    if (deviceId === "main_door") {
      return [
        { value: "open", label: "Mở cửa" },
        { value: "close", label: "Đóng cửa" },
      ];
    }
    return [
      { value: "turn_on", label: "Bật" },
      { value: "turn_off", label: "Tắt" },
    ];
  }

  function formatDeviceActionVi(deviceId, action) {
    const dev = DEVICE_LABELS[deviceId] || deviceId || "Thiết bị";
    const actKey = normalizeActionForDevice(deviceId, action);
    const act = ACTION_LABELS[actKey] || ACTION_LABELS[action] || action || "";
    return `${act} ${dev}`.trim();
  }

  function formatDurationCountdown(sec) {
    const s = Math.max(0, Math.round(Number(sec) || 0));
    if (s >= 3600) {
      const h = Math.floor(s / 3600);
      const m = Math.floor((s % 3600) / 60);
      const r = s % 60;
      return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
    }
    if (s >= 60) {
      const m = Math.floor(s / 60);
      const r = s % 60;
      return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
    }
    return `${s} giây`;
  }

  function parseWeekdayIndices(raw) {
    if (!raw) return [];
    const arr = Array.isArray(raw)
      ? raw
      : typeof raw === "string"
        ? raw.split(/[\s,;]+/).filter(Boolean)
        : [];
    const nameMap = {
      mon: 0, monday: 0, t2: 0, "thu2": 0, "thứ 2": 0,
      tue: 1, tuesday: 1, t3: 1, "thu3": 1, "thứ 3": 1,
      wed: 2, wednesday: 2, t4: 2, "thu4": 2, "thứ 4": 2,
      thu: 3, thursday: 3, t5: 3, "thu5": 3, "thứ 5": 3,
      fri: 4, friday: 4, t6: 4, "thu6": 4, "thứ 6": 4,
      sat: 5, saturday: 5, t7: 5, "thu7": 5, "thứ 7": 5,
      sun: 6, sunday: 6, cn: 6, "chu nhat": 6, "chủ nhật": 6,
    };
    const out = [];
    arr.forEach((item) => {
      if (typeof item === "number" && item >= 0 && item <= 6) {
        if (!out.includes(item)) out.push(item);
      } else {
        const s = String(item).trim().toLowerCase();
        if (/^[0-6]$/.test(s)) {
          const n = Number(s);
          if (!out.includes(n)) out.push(n);
        } else if (s in nameMap) {
          const n = nameMap[s];
          if (!out.includes(n)) out.push(n);
        }
      }
    });
    return out.sort((a, b) => a - b);
  }

  function formatScheduleRecurrence(sc) {
    const wd = parseWeekdayIndices(sc.weekdays);
    const stType = String(sc.schedule_type || sc.repeat || "once").toLowerCase();
    if (stType === "weekly" || wd.length > 0) {
      if (wd.length === 7) return "Hằng ngày";
      if (wd.length > 0) return wd.map((i) => WEEKDAY_NAMES_VI[i] || `T${i + 2}`).join(", ");
      return "Theo thứ";
    }
    if (stType === "daily") return "Hằng ngày";
    return sc.run_date_vn ? `Một lần (${sc.run_date_vn})` : "Một lần";
  }

  function formatConditionVi(cond) {
    if (!cond || typeof cond !== "object") return "";
    const src = String(cond.source || cond.device_id || cond.sensor || cond.type || "").trim();
    if (src === "time_window" || cond.type === "time_window") {
      const start = cond.start_hhmm || cond.start || "00:00";
      const end = cond.end_hhmm || cond.end || "23:59";
      return `Khung giờ ${start} – ${end}`;
    }
    if (src === "house_mode" || cond.type === "house_mode") {
      const val = String(cond.value || cond.state || "HOME").toUpperCase();
      return `Chế độ nhà: ${val === "AWAY" ? "Vắng nhà" : "Ở nhà"}`;
    }
    const meta = SOURCE_MAP[src];
    if (meta && meta.kind === "numeric") {
      const op = cond.operator || cond.op || ">";
      const val = cond.value !== undefined && cond.value !== null ? cond.value : cond.threshold;
      const hyst = Number(cond.hysteresis || 0);
      const unit = meta.unit || "";
      const shortName =
        src === "temp_sensor"
          ? "Nhiệt độ"
          : src === "humidity_sensor"
            ? "Độ ẩm KK"
            : "Độ ẩm đất";
      if (val === undefined || val === null || val === "") {
        const st = String(cond.state || "").toUpperCase();
        if (src === "soil_sensor") return st === "DRY" ? "Đất khô" : "Đất ẩm";
        return `${shortName}: ${st === "HIGH" ? "Cao" : st === "LOW" ? "Thấp" : st}`;
      }
      const hystStr = hyst > 0 ? ` (±${hyst}${unit})` : "";
      return `${shortName} ${op} ${val}${unit}${hystStr}`;
    }
    if (src === "sound_sensor") {
      const st = String(cond.value || cond.state || "LOUD").toUpperCase();
      return `Âm thanh: ${st === "LOUD" ? "Có tiếng động" : "Yên tĩnh"}`;
    }
    const devLabel = DEVICE_LABELS[src] || (meta && meta.label) || src;
    const rawState = String(cond.value || cond.state || "ON").toUpperCase();
    const stateViMap = {
      ON: "Bật",
      OFF: "Tắt",
      OPEN: "Mở",
      CLOSED: "Đóng",
      DRY: "Khô",
      WET: "Ẩm",
      LOUD: "Có tiếng động",
      QUIET: "Yên tĩnh",
      HIGH: "Cao",
      LOW: "Thấp",
      HOME: "Ở nhà",
      AWAY: "Vắng nhà",
    };
    return `${devLabel}: ${stateViMap[rawState] || rawState}`;
  }

  function normalizeRuleObject(r) {
    if (!r || typeof r !== "object") return null;
    const id = String(r.rule_id || r.id || "").trim();
    const logic = String(r.logic || r.condition_logic || "AND").toUpperCase() === "OR" ? "OR" : "AND";
    let conditions = Array.isArray(r.conditions) ? r.conditions.slice() : [];
    if (conditions.length === 0 && r.when_device_id) {
      conditions = [
        {
          source: r.when_device_id,
          device_id: r.when_device_id,
          operator: "==",
          state: String(r.when_state || "ON").toUpperCase(),
          value: String(r.when_state || "ON").toUpperCase(),
        },
      ];
    }
    let actions = Array.isArray(r.actions) ? r.actions.slice() : [];
    if (actions.length === 0 && r.then_device_id) {
      actions = [
        {
          device_id: r.then_device_id,
          action: normalizeActionForDevice(r.then_device_id, r.then_action || "turn_on"),
        },
      ];
    }
    let elseActions = Array.isArray(r.else_actions) ? r.else_actions.slice() : [];
    if (elseActions.length === 0 && r.else_device_id && r.else_action) {
      elseActions = [
        {
          device_id: r.else_device_id,
          action: normalizeActionForDevice(r.else_device_id, r.else_action),
        },
      ];
    }
    const cooldown = Number(r.cooldown_seconds !== undefined ? r.cooldown_seconds : r.cooldown || 0);
    const enabled = r.enabled === undefined ? true : Boolean(r.enabled);
    const label = String(r.name || r.label || "").trim();
    const isCompound =
      conditions.length > 1 ||
      actions.length > 1 ||
      conditions.some((c) => {
        const s = String((c && (c.source || c.type)) || "");
        return (
          s === "time_window" ||
          s === "house_mode" ||
          s === "temp_sensor" ||
          s === "humidity_sensor" ||
          s === "soil_sensor" ||
          s === "sound_sensor" ||
          (c && c.operator && c.operator !== "==")
        );
      }) ||
      Boolean(r.is_compound) ||
      Array.isArray(r.conditions);

    return {
      rule_id: id,
      name: label,
      logic,
      conditions,
      actions,
      else_actions: elseActions,
      cooldown_seconds: Number.isFinite(cooldown) ? cooldown : 0,
      delay_seconds: Number(r.delay_seconds || 0),
      enabled,
      owner_user_id: String(r.owner_user_id || ""),
      isCompound,
      raw: r,
    };
  }

  function extractRulesFromData(data) {
    const merged = [];
    const seenIds = new Set();
    const seenKeys = new Set();
    const lists = [
      data && data.automation_rules,
      data && data.compound_rules,
      data && data.rules,
      data && data.if_else_rules,
    ];
    lists.forEach((arr) => {
      if (!Array.isArray(arr)) return;
      arr.forEach((raw) => {
        const norm = normalizeRuleObject(raw);
        if (!norm) return;
        if (norm.rule_id && seenIds.has(norm.rule_id)) return;
        const sig = JSON.stringify({
          l: norm.logic,
          c: norm.conditions,
          a: norm.actions,
        });
        if (!norm.rule_id && seenKeys.has(sig)) return;
        if (norm.rule_id) seenIds.add(norm.rule_id);
        seenKeys.add(sig);
        merged.push(norm);
      });
    });
    return merged;
  }

  function canModifyItem(ownerUserId) {
    if (state.tier === 1) return true;
    if (state.tier >= 3) return false;
    if (!ownerUserId || !state.currentUserId) return true;
    return String(ownerUserId) === String(state.currentUserId);
  }

  // ==================== UI REGISTRY HYDRATION (SINGLE SOURCE OF TRUTH) ====================
  async function loadUiRegistry() {
    try {
      const res = await apiFetch("/api/ui_registry");
      if (!res || !res.ok) return;
      const reg = await res.json().catch(() => null);
      if (!reg || typeof reg !== "object") return;
      state.registry = reg;
      applyUiRegistryLabels(reg);
    } catch (_) {}
  }

  function applyUiRegistryLabels(reg) {
    if (!reg || typeof reg !== "object") return;
    // Hydrate sidebar nav labels if registry defines nav/routes
    const navItems = Array.isArray(reg.nav)
      ? reg.nav
      : Array.isArray(reg.routes)
        ? reg.routes
        : Array.isArray(reg.pages)
          ? reg.pages
          : [];
    navItems.forEach((item) => {
      if (!item || typeof item !== "object") return;
      const path = String(item.path || item.href || item.route || "").trim();
      const label = String(item.label || item.title || "").trim();
      if (!path || !label) return;
      document.querySelectorAll(`.sidebar .nav-list a[href="${path}"]`).forEach((a) => {
        const span = a.querySelector("span");
        if (span) span.textContent = label;
      });
    });

    // Hydrate automation tab labels from Single Source of Truth (/api/ui_registry)
    const tabsObj =
      (reg.automation_panel && reg.automation_panel.tabs) ||
      (reg.automation && reg.automation.tabs) ||
      reg.automation_tabs ||
      reg.tabs ||
      null;
    if (Array.isArray(tabsObj)) {
      tabsObj.forEach((t) => {
        if (!t || !t.id || !t.label) return;
        qAll(`[data-label-tab="${t.id}"]`).forEach((el) => {
          el.textContent = String(t.label);
        });
      });
    } else if (tabsObj && typeof tabsObj === "object") {
      Object.entries(tabsObj).forEach(([key, val]) => {
        const label = typeof val === "string" ? val : val && val.label;
        if (!label) return;
        qAll(`[data-label-tab="${key}"]`).forEach((el) => {
          el.textContent = String(label);
        });
      });
    }

    // Hydrate page title if specified
    const autoPageMeta =
      (reg.automation_panel && reg.automation_panel.page_title) ||
      (reg.automation && reg.automation.title) ||
      (navItems.find((x) => (x.path || x.href) === "/automation") || {}).label;
    const titleEl = q("#autoPageTitle");
    if (titleEl && autoPageMeta) {
      titleEl.textContent = String(autoPageMeta);
    }
  }

  // ==================== DATA SYNC (/api/automation, SSE, sh:snapshot) ====================
  function ingestAutomationData(data) {
    if (!data || typeof data !== "object") return;
    state.authState = "ok";
    if (data.tier !== undefined) state.tier = Number(data.tier);
    else if (data.current_tier !== undefined) state.tier = Number(data.current_tier);
    if (data.current_user_id) state.currentUserId = String(data.current_user_id);
    if (data.current_user_name) state.currentUserName = String(data.current_user_name);
    if (data.system_policies && typeof data.system_policies === "object") {
      state.systemPolicies = data.system_policies;
    }
    const hm = String(data.house_mode || (data.system_policies && data.system_policies.house_mode) || "").toUpperCase();
    if (hm === "HOME" || hm === "AWAY") {
      state.houseMode = hm;
    }
    if (Array.isArray(data.timers)) {
      const nowMs = Date.now();
      state.timers = data.timers.map((t) => {
        const rem = Number(t.remaining_seconds);
        const fireEpoch = Number(t.fire_epoch || t.fire_at_epoch || t.target_epoch || 0);
        return Object.assign({}, t, {
          _clientSyncMs: nowMs,
          _baseRemainingSec: Number.isFinite(rem) ? rem : fireEpoch > 0 ? Math.max(0, fireEpoch - nowMs / 1000) : 0,
        });
      });
    }
    if (Array.isArray(data.schedules)) {
      state.schedules = data.schedules.slice();
    }
    const rawCmds = data.custom_commands || data.scenes;
    if (Array.isArray(rawCmds)) {
      state.commands = rawCmds.slice();
    }
    if (
      Array.isArray(data.automation_rules) ||
      Array.isArray(data.compound_rules) ||
      Array.isArray(data.rules) ||
      Array.isArray(data.if_else_rules)
    ) {
      state.rules = extractRulesFromData(data);
    }
    state.lastFetchAt = Date.now();
    renderAll();
  }

  async function fetchAutomationState() {
    try {
      const res = await apiFetch("/api/automation");
      if (res.status === 401) {
        state.authState = "unauth";
        updateAuthNotice("Vui lòng đăng nhập để xem và quản lý tự động hóa.", false);
        updateConnectionBadge(false, "Chưa đăng nhập");
        return null;
      }
      if (res.status === 403) {
        state.authState = "guest";
        const errData = await res.json().catch(() => ({}));
        updateAuthNotice(
          errData.error || "Tài khoản Khách (Cấp 3) chỉ được bật/tắt thiết bị, chưa có quyền quản lý tự động hóa.",
          true
        );
        updateConnectionBadge(true, "Đã kết nối");
        return null;
      }
      if (!res.ok) return null;
      const data = await res.json().catch(() => null);
      if (data && data.ok !== false) {
        hideAuthNotice();
        updateConnectionBadge(true, "Đã kết nối");
        ingestAutomationData(data);
        return data;
      }
    } catch (_) {
      updateConnectionBadge(false, "Mất kết nối");
    }
    return null;
  }

  async function fetchSessionBadge() {
    const badge = q("#autoAccountBadge");
    if (!badge) return;
    try {
      const res = await apiFetch("/api/session/role");
      if (!res || !res.ok) {
        badge.textContent = "Chưa đăng nhập";
        return;
      }
      const info = await res.json().catch(() => ({}));
      if (info && info.authenticated) {
        state.tier = Number(info.tier || state.tier || 1);
        state.currentUserId = String(info.user_id || state.currentUserId || "");
        state.currentUserName = String(info.display_name || info.name || info.role || "");
        const tierLabel = state.tier === 1 ? "Chủ nhà" : state.tier === 2 ? "Gia đình" : "Khách";
        badge.textContent = `${tierLabel} · ${state.currentUserName || "Đã đăng nhập"}`;
        if (window.SmartHomeNavGuard && typeof window.SmartHomeNavGuard.applyNavAuthState === "function") {
          window.SmartHomeNavGuard.applyNavAuthState(info);
        }
        const isGuestTier3 = state.tier >= 3;
        ["#btnToggleHouseMode", "#btnAutoResetAll", "#btnAutoCreateTimer", "#btnAutoCreateSchedule", "#btnAutoCreateCommand", "#btnAutoCreateRule"].forEach((sel) => {
          const el = q(sel);
          if (el) el.hidden = isGuestTier3;
        });
      } else {
        badge.textContent = "Chưa đăng nhập";
        if (window.SmartHomeNavGuard && typeof window.SmartHomeNavGuard.applyNavAuthState === "function") {
          window.SmartHomeNavGuard.applyNavAuthState({ authenticated: false });
        }
      }
    } catch (_) {}
  }

  function updateConnectionBadge(connected, label) {
    const dot = q("#autoConnDot");
    const txt = q("#autoConnText");
    if (dot) dot.classList.toggle("offline", !connected);
    if (txt) txt.textContent = label || (connected ? "Đã kết nối" : "Mất kết nối");
  }

  function updateAuthNotice(msg, isGuest) {
    const box = q("#autoAuthNotice");
    const txt = q("#autoAuthNoticeText");
    if (!box || !txt) return;
    txt.textContent = msg;
    box.hidden = false;
    const link = box.querySelector("a");
    if (link) link.hidden = Boolean(isGuest);
  }

  function hideAuthNotice() {
    const box = q("#autoAuthNotice");
    if (box) box.hidden = true;
  }

  // ==================== SSE LIVE SYNC ====================
  function connectAutomationSse() {
    if (!isAutomationPageActive()) return;
    if (typeof window.EventSource !== "function") return;
    if (state.sse) return;
    try {
      const tok = getSessionToken();
      const sseUrl = tok ? `/api/events?session_token=${encodeURIComponent(tok)}` : "/api/events";
      const es = new EventSource(sseUrl, { withCredentials: true });
      state.sse = es;

      es.onopen = () => {
        state.sseConnected = true;
        updateConnectionBadge(true, "Đã kết nối");
      };
      es.onerror = () => {
        state.sseConnected = false;
        if (es.readyState === EventSource.CLOSED) {
          state.sse = null;
        }
      };

      const handleEventPayload = (raw) => {
        try {
          const parsed = JSON.parse(raw);
          const snap = (parsed && parsed.snapshot) || parsed;
          if (
            snap &&
            (Array.isArray(snap.timers) ||
              Array.isArray(snap.schedules) ||
              Array.isArray(snap.automation_rules) ||
              Array.isArray(snap.custom_commands) ||
              snap.house_mode)
          ) {
            ingestAutomationData(snap);
            return;
          }
          const evType = String((parsed && (parsed.type || parsed.event)) || "").toLowerCase();
          if (
            evType.includes("timer") ||
            evType.includes("schedule") ||
            evType.includes("rule") ||
            evType.includes("scene") ||
            evType.includes("auto") ||
            evType.includes("house_mode") ||
            evType.includes("snapshot") ||
            evType.includes("device")
          ) {
            fetchAutomationState();
          }
        } catch (_) {}
      };

      es.onmessage = (ev) => handleEventPayload(ev.data);
      ["snapshot", "state", "automation_updated", "timer_fired", "rule_fired", "house_mode_changed", "device_update"].forEach(
        (evName) => {
          es.addEventListener(evName, (ev) => handleEventPayload(ev.data));
        }
      );
    } catch (_) {}
  }

  function disconnectAutomationSse() {
    if (state.sse) {
      try {
        state.sse.close();
      } catch (_) {}
      state.sse = null;
      state.sseConnected = false;
    }
  }

  // ==================== RENDERING (DEDICATED /automation PAGE) ====================
  function renderHouseModeUI() {
    const isAway = state.houseMode === "AWAY";
    const modeText = isAway ? "Chế độ vắng nhà" : "Chế độ ở nhà";
    const shortModeText = isAway ? "Vắng nhà" : "Ở nhà";

    const btn = q("#btnToggleHouseMode");
    if (btn) {
      btn.setAttribute("data-mode", state.houseMode);
      btn.setAttribute("aria-pressed", isAway ? "true" : "false");
      const lbl = q("#houseModeLabel", btn) || btn.querySelector("span:last-child");
      if (lbl) lbl.textContent = modeText;
    }

    const dashBtn = q("#dashHouseModePill");
    if (dashBtn) {
      dashBtn.setAttribute("data-mode", state.houseMode);
      dashBtn.textContent = shortModeText;
      dashBtn.classList.toggle("accent", !isAway);
    }
  }

  function renderCountsAndTabs() {
    const cT = state.timers.length;
    const cS = state.schedules.length;
    const cC = state.commands.length;
    const cR = state.rules.length;
    const cAll = cT + cS + cC + cR;

    const setTxt = (sel, val) => {
      const el = q(sel);
      if (el) el.textContent = String(val);
    };

    setTxt("#autoKpiTimers", cT);
    setTxt("#autoKpiSchedules", cS);
    setTxt("#autoKpiCommands", cC);
    setTxt("#autoKpiRules", cR);
    setTxt("#autoTabCountAll", cAll);
    setTxt("#autoTabCountTimers", cT);
    setTxt("#autoTabCountSchedules", cS);
    setTxt("#autoTabCountCommands", cC);
    setTxt("#autoTabCountRules", cR);
    setTxt("#autoSecCountTimers", cT);
    setTxt("#autoSecCountSchedules", cS);
    setTxt("#autoSecCountCommands", cC);
    setTxt("#autoSecCountRules", cR);

    const grid = q("#autoSectionsGrid");
    if (grid) {
      grid.classList.toggle("is-single-tab", state.activeTab !== "all");
      qAll(".auto-section-card", grid).forEach((sec) => {
        const key = sec.getAttribute("data-section");
        sec.hidden = state.activeTab !== "all" && key !== state.activeTab;
      });
    }

    qAll("#autoTabBar .auto-tab-btn").forEach((btn) => {
      const tab = btn.getAttribute("data-auto-tab");
      const isAct = tab === state.activeTab;
      btn.classList.toggle("active", isAct);
      btn.setAttribute("aria-selected", isAct ? "true" : "false");
    });

    qAll(".auto-kpi-pill").forEach((pill) => {
      const tab = pill.getAttribute("data-kpi-tab");
      pill.classList.toggle("is-active", tab === state.activeTab);
    });
  }

  function computeRemainingSeconds(timer) {
    const nowSec = Date.now() / 1000;
    const fireEpoch = Number(timer.fire_epoch || timer.fire_at_epoch || timer.target_epoch || 0);
    if (fireEpoch > 0) {
      return Math.max(0, Math.round(fireEpoch - nowSec));
    }
    const elapsed = (Date.now() - (timer._clientSyncMs || Date.now())) / 1000;
    const base = Number(timer._baseRemainingSec !== undefined ? timer._baseRemainingSec : timer.remaining_seconds || 0);
    return Math.max(0, Math.round(base - elapsed));
  }

  function renderPageTimers() {
    const host = q("#autoPageTimerList");
    if (!host) return;
    if (!state.timers.length) {
      host.innerHTML = `<div class="auto-empty-state">Chưa có hẹn giờ nào đang chạy. Nhấn "Tạo hẹn giờ" hoặc ra lệnh bằng giọng nói.</div>`;
      return;
    }
    host.innerHTML = state.timers
      .map((t) => {
        const tid = String(t.id || t.timer_id || "");
        const devId = String(t.device_id || t.raw_target || "");
        const title = formatDeviceActionVi(devId, t.action || "turn_on");
        const remSec = computeRemainingSeconds(t);
        const remLabel = formatDurationCountdown(remSec);
        const targetClock = t.target_vn_time ? `Lúc ${t.target_vn_time}` : "";
        const repeatKey = String(t.repeat_rule || t.repeat || "once").toLowerCase();
        const repeatLabel = REPEAT_LABELS_VI[repeatKey] || repeatKey;
        const canEdit = canModifyItem(t.owner_user_id || t.owner_id);
        return `
          <article class="auto-item" data-item-type="timer" data-item-id="${escapeHtml(tid)}">
            <div class="auto-item-top">
              <div class="auto-item-title-wrap">
                <div class="auto-item-title">${escapeHtml(title)}</div>
                <div class="auto-item-sub">${escapeHtml(targetClock || "Đếm ngược trực tiếp")}</div>
              </div>
              <div class="auto-badges-row">
                <span class="auto-badge is-countdown" data-timer-countdown="${escapeHtml(tid)}">Còn ${escapeHtml(remLabel)}</span>
                <span class="auto-badge is-meta">${escapeHtml(repeatLabel)}</span>
              </div>
            </div>
            ${
              canEdit && tid
                ? `<div class="auto-item-actions">
                    <button type="button" class="btn-mini" data-ap-action="edit-timer" data-ap-id="${escapeHtml(tid)}">Sửa</button>
                    <button type="button" class="btn-mini danger" data-ap-action="delete-timer" data-ap-id="${escapeHtml(tid)}">Hủy</button>
                  </div>`
                : ""
            }
          </article>
        `;
      })
      .join("");
  }

  function renderPageSchedules() {
    const host = q("#autoPageScheduleList");
    if (!host) return;
    if (!state.schedules.length) {
      host.innerHTML = `<div class="auto-empty-state">Chưa có lịch trình cố định. Bạn có thể tạo lịch hằng ngày hoặc theo thứ trong tuần.</div>`;
      return;
    }
    host.innerHTML = state.schedules
      .map((sc) => {
        const sid = String(sc.schedule_id || sc.id || "");
        const enabled = sc.enabled === undefined ? true : Boolean(sc.enabled);
        const title = sc.label
          ? `${sc.time_hhmm || "00:00"} · ${sc.label}`
          : `${sc.time_hhmm || "00:00"} · ${formatDeviceActionVi(sc.device_id, sc.action)}`;
        const subAction = sc.label ? formatDeviceActionVi(sc.device_id, sc.action) : "";
        const recLabel = formatScheduleRecurrence(sc);
        const canEdit = canModifyItem(sc.owner_user_id);
        return `
          <article class="auto-item ${enabled ? "" : "is-disabled"}" data-item-type="schedule" data-item-id="${escapeHtml(sid)}">
            <div class="auto-item-top">
              <div class="auto-item-title-wrap">
                <div class="auto-item-title">${escapeHtml(title)}</div>
                ${subAction ? `<div class="auto-item-sub">${escapeHtml(subAction)}</div>` : ""}
              </div>
              <div class="auto-badges-row">
                <span class="auto-badge ${enabled ? "is-on" : "is-off"}">${enabled ? "Đang bật" : "Đang tắt"}</span>
                <span class="auto-badge is-meta">${escapeHtml(recLabel)}</span>
              </div>
            </div>
            ${
              canEdit && sid
                ? `<div class="auto-item-actions">
                    <button type="button" class="btn-mini ${enabled ? "" : "accent"}" data-ap-action="toggle-schedule" data-ap-id="${escapeHtml(sid)}" data-ap-enabled="${enabled ? "1" : "0"}">${enabled ? "Tắt" : "Bật"}</button>
                    <button type="button" class="btn-mini" data-ap-action="edit-schedule" data-ap-id="${escapeHtml(sid)}">Sửa</button>
                    <button type="button" class="btn-mini danger" data-ap-action="delete-schedule" data-ap-id="${escapeHtml(sid)}">Xóa</button>
                  </div>`
                : ""
            }
          </article>
        `;
      })
      .join("");
  }

  function renderPageCommands() {
    const host = q("#autoPageCommandList");
    if (!host) return;
    if (!state.commands.length) {
      host.innerHTML = `<div class="auto-empty-state">Chưa có lệnh tùy chỉnh nào. Tạo một câu lệnh để kích hoạt nhiều thiết bị cùng lúc.</div>`;
      return;
    }
    host.innerHTML = state.commands
      .map((cmd) => {
        const cid = String(cmd.command_id || cmd.id || "");
        const phrase = String(cmd.phrase || "");
        const steps = Array.isArray(cmd.steps) ? cmd.steps : [];
        const chipsHtml = steps
          .map((s) => `<span class="auto-chip is-action">→ ${escapeHtml(formatDeviceActionVi(s.device_id, s.action))}</span>`)
          .join("");
        const canEdit = canModifyItem(cmd.owner_user_id);
        return `
          <article class="auto-item" data-item-type="command" data-item-id="${escapeHtml(cid)}">
            <div class="auto-item-top">
              <div class="auto-item-title-wrap">
                <div class="auto-item-title">"${escapeHtml(phrase)}"</div>
              </div>
              <span class="auto-badge is-meta">${steps.length} bước</span>
            </div>
            <div class="auto-chips-wrap">${chipsHtml || '<span class="auto-item-sub">Chưa có bước</span>'}</div>
            <div class="auto-item-actions">
              <button type="button" class="btn-mini accent" data-ap-action="run-command" data-ap-id="${escapeHtml(cid)}">Chạy</button>
              ${
                canEdit && cid
                  ? `<button type="button" class="btn-mini" data-ap-action="edit-command" data-ap-id="${escapeHtml(cid)}">Sửa</button>
                     <button type="button" class="btn-mini danger" data-ap-action="delete-command" data-ap-id="${escapeHtml(cid)}">Xóa</button>`
                  : ""
              }
            </div>
          </article>
        `;
      })
      .join("");
  }

  function buildRuleCardHtml(rule, compact) {
    const rid = rule.rule_id;
    const logicText = rule.logic === "OR" ? "BẤT KỲ (HOẶC)" : "TẤT CẢ (VÀ)";
    const logicClass = rule.logic === "OR" ? "is-or" : "is-and";
    const condChips = rule.conditions
      .map((c) => `<span class="auto-chip is-cond">Nếu ${escapeHtml(formatConditionVi(c))}</span>`)
      .join("");
    const actChips = rule.actions
      .map((a) => `<span class="auto-chip is-action">→ ${escapeHtml(formatDeviceActionVi(a.device_id, a.action))}</span>`)
      .join("");
    const elseChips = rule.else_actions
      .map((a) => `<span class="auto-chip is-else">Ngược lại → ${escapeHtml(formatDeviceActionVi(a.device_id, a.action))}</span>`)
      .join("");
    const title =
      rule.name ||
      (rule.conditions.length
        ? `Khi ${rule.conditions.map(formatConditionVi).join(rule.logic === "OR" ? " hoặc " : " và ")}`
        : "Luật tự động");
    const canEdit = canModifyItem(rule.owner_user_id);
    const metaBadges = [];
    if (rule.cooldown_seconds > 0) {
      metaBadges.push(`<span class="auto-badge is-meta">Chờ lặp ${rule.cooldown_seconds}s</span>`);
    }
    const maxHyst = rule.conditions.reduce((mx, c) => Math.max(mx, Number((c && c.hysteresis) || 0)), 0);
    if (maxHyst > 0) {
      metaBadges.push(`<span class="auto-badge is-meta">Hồi trễ ±${maxHyst}</span>`);
    }
    return `
      <article class="auto-item ${rule.enabled ? "" : "is-disabled"}" data-item-type="rule" data-item-id="${escapeHtml(rid)}">
        <div class="auto-item-top">
          <div class="auto-item-title-wrap">
            <div class="auto-item-title">${escapeHtml(title)}</div>
          </div>
          <div class="auto-badges-row">
            <span class="auto-badge ${logicClass}">${logicText}</span>
            <span class="auto-badge ${rule.enabled ? "is-on" : "is-off"}">${rule.enabled ? "Đang bật" : "Đang tắt"}</span>
            ${compact ? "" : metaBadges.join("")}
          </div>
        </div>
        <div class="auto-chips-wrap">
          ${condChips}
          ${actChips}
          ${elseChips}
        </div>
        ${
          canEdit && rid
            ? `<div class="auto-item-actions">
                <button type="button" class="btn-mini ${rule.enabled ? "" : "accent"}" data-ap-action="toggle-rule" data-ap-id="${escapeHtml(rid)}" data-ap-enabled="${rule.enabled ? "1" : "0"}">${rule.enabled ? "Tắt" : "Bật"}</button>
                <button type="button" class="btn-mini" data-ap-action="edit-rule" data-ap-id="${escapeHtml(rid)}">Sửa</button>
                <button type="button" class="btn-mini danger" data-ap-action="delete-rule" data-ap-id="${escapeHtml(rid)}">Xóa</button>
              </div>`
            : ""
        }
      </article>
    `;
  }

  function renderPageRules() {
    const host = q("#autoPageRuleList");
    if (!host) return;
    if (!state.rules.length) {
      host.innerHTML = `<div class="auto-empty-state">Chưa có luật tự động nào. Nhấn "Tạo luật mới" để kết hợp nhiều cảm biến, khung giờ và thiết bị.</div>`;
      return;
    }
    host.innerHTML = state.rules.map((r) => buildRuleCardHtml(r, false)).join("");
  }

  function renderDashboardCompoundRules() {
    const container = q("#compoundRuleList");
    if (!container) return;
    const compoundRules = state.rules.filter((r) => r.isCompound || r.rule_id);
    const wrap = q("#compoundRuleWrap") || container;
    if (!compoundRules.length) {
      container.innerHTML = "";
      if (wrap !== container) wrap.hidden = true;
      container.hidden = true;
      return;
    }
    if (wrap !== container) wrap.hidden = false;
    container.hidden = false;
    container.innerHTML = compoundRules.map((r) => buildRuleCardHtml(r, true)).join("");

    const emptyTxt = q("#scheduleEmptyText");
    if (emptyTxt && compoundRules.length > 0) {
      emptyTxt.hidden = true;
    }
  }

  function renderAll() {
    renderHouseModeUI();
    if (isAutomationPageActive()) {
      renderCountsAndTabs();
      renderPageTimers();
      renderPageSchedules();
      renderPageCommands();
      renderPageRules();
    }
    if (isDashboardPanelActive()) {
      renderDashboardCompoundRules();
    }
  }

  // ==================== LIVE 1s COUNTDOWN TICKER ====================
  function startCountdownTicker() {
    if (state.tickHandle) return;
    state.tickHandle = setInterval(() => {
      if (!state.timers.length) return;
      let anyExpired = false;
      state.timers.forEach((t) => {
        const tid = String(t.id || t.timer_id || "");
        if (!tid) return;
        const rem = computeRemainingSeconds(t);
        if (rem <= 0) anyExpired = true;
        const escId = typeof CSS !== "undefined" && CSS.escape ? CSS.escape(tid) : tid;
        document.querySelectorAll(`[data-timer-countdown="${escId}"]`).forEach((el) => {
          el.textContent = rem > 0 ? `Còn ${formatDurationCountdown(rem)}` : "Đang thực thi...";
        });
      });
      if (anyExpired && Date.now() - state.lastFetchAt > 1200) {
        fetchAutomationState();
      }
    }, 1000);
  }

  function startFallbackPolling() {
    if (state.pollHandle) return;
    state.pollHandle = setInterval(() => {
      if (document.hidden) return;
      if (!isAutomationPageActive()) return;
      if (state.authState === "unauth" || state.authState === "guest") return;
      // Poll every 3s as fallback (or every 12s when SSE connected)
      const intervalMs = state.sseConnected ? 12000 : 3000;
      if (Date.now() - state.lastFetchAt >= intervalMs) {
        fetchAutomationState();
      }
    }, 3000);
  }

  // ==================== MODAL BUILDER & CRUD ====================
  function ensureModalInDom() {
    let modal = q("#automationModal") || document.getElementById("automationModal");
    if (modal) return modal;
    // Dynamically mount modal on dashboard `/` if opened from #btnAutoCreateRule
    const tpl = document.createElement("div");
    tpl.innerHTML = `
      <div id="automationModal" class="auto-modal-backdrop hidden" hidden>
        <div id="automationModalDialog" class="auto-modal-dialog" role="dialog" aria-modal="true" aria-labelledby="autoModalTitle">
          <div class="auto-modal-header">
            <h3 id="autoModalTitle">Tạo luật tự động mới</h3>
            <button type="button" class="btn-close" id="btnAutoModalClose" aria-label="Đóng hộp thoại">&times;</button>
          </div>
          <form id="autoModalForm" class="auto-modal-body" novalidate>
            <input type="hidden" id="autoModalKind" value="rule">
            <input type="hidden" id="autoModalEditId" value="">
            <div id="autoModalTimerFields" hidden>
              <div class="auto-grid-2">
                <div class="auto-field"><label for="autoModalTimerDevice">Thiết bị</label><select id="autoModalTimerDevice" class="auto-select"></select></div>
                <div class="auto-field"><label for="autoModalTimerAction">Hành động</label><select id="autoModalTimerAction" class="auto-select"></select></div>
              </div>
              <div class="auto-grid-3" style="margin-top:10px;">
                <div class="auto-field"><label for="autoModalTimerHours">Giờ</label><input type="number" id="autoModalTimerHours" class="auto-input" min="0" max="24" step="1" value="0"></div>
                <div class="auto-field"><label for="autoModalTimerMinutes">Phút</label><input type="number" id="autoModalTimerMinutes" class="auto-input" min="0" max="59" step="1" value="0"></div>
                <div class="auto-field"><label for="autoModalTimerSeconds">Giây</label><input type="number" id="autoModalTimerSeconds" class="auto-input" min="0" max="59" step="1" value="30"></div>
              </div>
              <div class="auto-field" style="margin-top:10px;">
                <label for="autoModalTimerRepeat">Lặp lại</label>
                <select id="autoModalTimerRepeat" class="auto-select">
                  <option value="once">Một lần</option>
                  <option value="hourly">Mỗi giờ</option>
                  <option value="daily">Hằng ngày</option>
                </select>
              </div>
            </div>
            <div id="autoModalScheduleFields" hidden>
              <div class="auto-grid-2">
                <div class="auto-field"><label for="autoModalScheduleDevice">Thiết bị</label><select id="autoModalScheduleDevice" class="auto-select"></select></div>
                <div class="auto-field"><label for="autoModalScheduleAction">Hành động</label><select id="autoModalScheduleAction" class="auto-select"></select></div>
              </div>
              <div class="auto-grid-2" style="margin-top:10px;">
                <div class="auto-field"><label for="autoModalScheduleTime">Giờ thực thi (HH:MM)</label><input type="time" id="autoModalScheduleTime" class="auto-input" value="07:00" required></div>
                <div class="auto-field">
                  <label for="autoModalScheduleType">Chu kỳ lặp</label>
                  <select id="autoModalScheduleType" class="auto-select">
                    <option value="once">Một lần</option>
                    <option value="daily">Hằng ngày</option>
                    <option value="weekly">Theo thứ trong tuần</option>
                  </select>
                </div>
              </div>
              <div id="autoModalWeekdaysWrap" class="auto-field" style="margin-top:10px;" hidden>
                <span class="auto-field-label">Chọn các thứ lặp lại</span>
                <div class="auto-weekday-grid" id="autoModalWeekdaysGrid">
                  <label class="auto-weekday-pill"><input type="checkbox" value="0">T2</label>
                  <label class="auto-weekday-pill"><input type="checkbox" value="1">T3</label>
                  <label class="auto-weekday-pill"><input type="checkbox" value="2">T4</label>
                  <label class="auto-weekday-pill"><input type="checkbox" value="3">T5</label>
                  <label class="auto-weekday-pill"><input type="checkbox" value="4">T6</label>
                  <label class="auto-weekday-pill"><input type="checkbox" value="5">T7</label>
                  <label class="auto-weekday-pill"><input type="checkbox" value="6">CN</label>
                </div>
              </div>
              <div class="auto-field" style="margin-top:10px;">
                <label for="autoModalScheduleLabel">Nhãn lịch trình (tùy chọn)</label>
                <input type="text" id="autoModalScheduleLabel" class="auto-input" placeholder="Ví dụ: Bật đèn buổi tối">
              </div>
            </div>
            <div id="autoModalCommandFields" hidden>
              <div class="auto-field">
                <label for="autoModalCommandPhrase">Câu lệnh kích hoạt</label>
                <input type="text" id="autoModalCommandPhrase" class="auto-input" placeholder="Ví dụ: chế độ đi ngủ, ra ngoài...">
              </div>
              <div class="auto-builder-section" style="margin-top:10px;">
                <div class="auto-builder-head">
                  <span class="auto-builder-title">Các bước thực hiện</span>
                  <button type="button" class="btn-mini accent" id="btnAutoAddCmdStep">+ Thêm bước</button>
                </div>
                <div id="autoModalCmdStepsList" class="auto-builder-list"></div>
              </div>
            </div>
            <div id="autoModalRuleFields" hidden>
              <div class="auto-field">
                <label for="autoRuleNameInput">Tên luật tự động (tùy chọn)</label>
                <input type="text" id="autoRuleNameInput" class="auto-input" placeholder="Nhập tên gợi nhớ cho luật tự động">
              </div>
              <div class="auto-field" style="margin-top:10px;">
                <span class="auto-field-label">Logic kết hợp điều kiện</span>
                <div class="auto-logic-group" id="autoRuleLogicGroup">
                  <label class="auto-logic-option is-selected" data-logic-opt="AND"><input type="radio" name="autoRuleLogic" value="AND" checked><span>Thỏa mãn TẤT CẢ điều kiện (VÀ)</span></label>
                  <label class="auto-logic-option" data-logic-opt="OR"><input type="radio" name="autoRuleLogic" value="OR"><span>Thỏa mãn BẤT KỲ điều kiện nào (HOẶC)</span></label>
                </div>
              </div>
              <div class="auto-builder-section" style="margin-top:10px;">
                <div class="auto-builder-head">
                  <span class="auto-builder-title">Điều kiện kích hoạt</span>
                  <button type="button" class="btn-mini accent" id="btnAutoAddCondition">+ Thêm điều kiện</button>
                </div>
                <div id="autoRuleConditionsList" class="auto-builder-list"></div>
              </div>
              <div class="auto-builder-section" style="margin-top:10px;">
                <div class="auto-builder-head">
                  <span class="auto-builder-title">Hành động thực thi</span>
                  <button type="button" class="btn-mini accent" id="btnAutoAddAction">+ Thêm hành động</button>
                </div>
                <div id="autoRuleActionsList" class="auto-builder-list"></div>
              </div>
              <div style="margin-top:10px; display:grid; gap:8px;">
                <label class="auto-toggle-line"><input type="checkbox" id="chkAutoEnableElse"><span>+ Hành động ngược lại khi hết điều kiện</span></label>
                <div id="autoRuleElseWrap" class="auto-builder-section" hidden>
                  <div class="auto-builder-head">
                    <span class="auto-builder-title">Hành động ngược lại (ELSE)</span>
                    <button type="button" class="btn-mini accent" id="btnAutoAddElseAction">+ Thêm hành động ngược lại</button>
                  </div>
                  <div id="autoRuleElseActionsList" class="auto-builder-list"></div>
                </div>
              </div>
              <div class="auto-field" style="margin-top:10px; max-width:240px;">
                <label for="autoRuleCooldownInput">Thời gian chờ lặp lại (giây)</label>
                <input type="number" id="autoRuleCooldownInput" class="auto-input" min="0" max="86400" step="1" value="10">
              </div>
            </div>
            <div id="autoModalFeedback" class="auto-modal-feedback" role="status" aria-live="polite" hidden></div>
            <div id="autoModalConfirmBanner" class="auto-confirm-banner" role="alert" aria-live="polite" hidden>
              <div class="auto-confirm-question" id="autoModalConfirmQuestion"></div>
              <div class="auto-confirm-actions">
                <button type="button" class="btn btn-primary" id="btnAutoModalConfirmYes" style="min-height:40px;">Đồng ý</button>
                <button type="button" class="btn btn-secondary" id="btnAutoModalConfirmNo" style="min-height:40px;">Hủy</button>
              </div>
            </div>
          </form>
          <div class="auto-modal-footer">
            <button type="button" class="btn btn-secondary" id="btnAutoModalCancel" style="min-height:42px;">Hủy</button>
            <button type="button" class="btn btn-primary" id="btnAutoModalSave" style="min-height:42px;">Lưu tự động hóa</button>
          </div>
        </div>
      </div>
    `;
    modal = tpl.firstElementChild;
    document.body.appendChild(modal);
    bindModalEvents(modal);
    return modal;
  }

  function getModalRoot() {
    return q("#automationModal") || document.getElementById("automationModal");
  }

  function populateDeviceSelect(selectEl, includeGroups, selectedValue) {
    if (!selectEl) return;
    const list = includeGroups
      ? TARGET_DEVICES
      : TARGET_DEVICES.filter((d) => d.kind !== "group");
    selectEl.innerHTML = list
      .map((d) => `<option value="${escapeHtml(d.id)}">${escapeHtml(d.label)}</option>`)
      .join("");
    if (selectedValue && list.some((d) => d.id === selectedValue)) {
      selectEl.value = selectedValue;
    }
  }

  function populateActionSelect(selectEl, deviceId, selectedAction) {
    if (!selectEl) return;
    const opts = getActionOptionsForDevice(deviceId);
    selectEl.innerHTML = opts
      .map((o) => `<option value="${escapeHtml(o.value)}">${escapeHtml(o.label)}</option>`)
      .join("");
    const norm = normalizeActionForDevice(deviceId, selectedAction || opts[0].value);
    selectEl.value = opts.some((o) => o.value === norm) ? norm : opts[0].value;
  }

  function setModalFeedback(msg, kind) {
    const modal = getModalRoot();
    const fb = modal && modal.querySelector("#autoModalFeedback");
    if (!fb) return;
    if (!msg) {
      fb.hidden = true;
      fb.textContent = "";
      fb.className = "auto-modal-feedback";
      return;
    }
    fb.hidden = false;
    fb.textContent = String(msg);
    fb.className = `auto-modal-feedback ${kind === "error" ? "is-error" : kind === "ok" ? "is-ok" : ""}`;
  }

  function hideModalConfirmBanner() {
    state.pendingModalConfirm = null;
    const modal = getModalRoot();
    const banner = modal && modal.querySelector("#autoModalConfirmBanner");
    if (banner) banner.hidden = true;
  }

  function showModalConfirmBanner(pendingData) {
    const modal = getModalRoot();
    if (!modal) return;
    const pid = String(pendingData.pending_id || pendingData.confirm_token || "");
    if (!pid) return;
    state.pendingModalConfirm = {
      pending_id: pid,
      confirm_token: String(pendingData.confirm_token || pid),
    };
    const banner = modal.querySelector("#autoModalConfirmBanner");
    const qEl = modal.querySelector("#autoModalConfirmQuestion");
    if (qEl) {
      qEl.textContent = String(
        pendingData.prompt_question || pendingData.reply || pendingData.exact_spoken_reply || "Bạn có xác nhận lưu cấu hình tự động hóa này không?"
      );
    }
    if (banner) banner.hidden = false;
  }

  function hidePageConfirmBanner() {
    state.pendingPageConfirm = null;
    const banner = q("#autoPageConfirmBanner");
    if (banner) banner.hidden = true;
  }

  function showPageConfirmBanner(pendingData) {
    const pid = String(pendingData.pending_id || pendingData.confirm_token || "");
    if (!pid) return;
    state.pendingPageConfirm = {
      pending_id: pid,
      confirm_token: String(pendingData.confirm_token || pid),
    };
    const banner = q("#autoPageConfirmBanner");
    const qEl = q("#autoPageConfirmQuestion");
    if (qEl) {
      qEl.textContent = String(
        pendingData.prompt_question || pendingData.reply || pendingData.exact_spoken_reply || "Bạn có xác nhận thao tác này không?"
      );
    }
    if (banner) {
      banner.hidden = false;
      banner.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  // ---- Dynamic Row Builders ----
  function createActionRow(container, initial) {
    const row = document.createElement("div");
    row.className = "auto-builder-row";
    const devSel = document.createElement("select");
    devSel.className = "auto-select";
    devSel.setAttribute("aria-label", "Thiết bị thực thi");
    devSel.setAttribute("data-field", "device_id");
    populateDeviceSelect(devSel, true, (initial && initial.device_id) || "living_room_light");

    const actSel = document.createElement("select");
    actSel.className = "auto-select";
    actSel.setAttribute("aria-label", "Hành động");
    actSel.setAttribute("data-field", "action");
    populateActionSelect(actSel, devSel.value, (initial && initial.action) || "turn_on");

    devSel.addEventListener("change", () => {
      populateActionSelect(actSel, devSel.value, actSel.value);
    });

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "auto-row-remove-btn";
    delBtn.textContent = "Xóa";
    delBtn.addEventListener("click", () => {
      if (container.children.length > 1) {
        row.remove();
      }
    });

    row.appendChild(devSel);
    row.appendChild(actSel);
    row.appendChild(delBtn);
    container.appendChild(row);
    return row;
  }

  function renderConditionInputs(row, sourceId, initial) {
    const dynamicWrap = row.querySelector("[data-cond-inputs]");
    if (!dynamicWrap) return;
    dynamicWrap.innerHTML = "";
    const meta = SOURCE_MAP[sourceId] || SOURCE_MAP.temp_sensor;

    if (meta.kind === "numeric") {
      const opSel = document.createElement("select");
      opSel.className = "auto-select auto-select-op";
      opSel.setAttribute("aria-label", "Toán tử so sánh");
      opSel.setAttribute("data-field", "operator");
      [">", ">=", "<", "<="].forEach((op) => {
        const o = document.createElement("option");
        o.value = op;
        o.textContent = op;
        opSel.appendChild(o);
      });
      opSel.value = (initial && (initial.operator || initial.op)) || meta.defaultOp || ">";

      const valInp = document.createElement("input");
      valInp.type = "number";
      valInp.step = "any";
      valInp.className = "auto-input auto-input-sm";
      valInp.setAttribute("aria-label", `Giá trị ngưỡng (${meta.unit})`);
      valInp.setAttribute("data-field", "value");
      valInp.placeholder = `Ngưỡng (${meta.unit})`;
      valInp.value =
        initial && initial.value !== undefined && initial.value !== ""
          ? String(initial.value)
          : String(meta.defaultVal);

      const hystInp = document.createElement("input");
      hystInp.type = "number";
      hystInp.min = "0";
      hystInp.step = "any";
      hystInp.className = "auto-input auto-input-sm";
      hystInp.setAttribute("aria-label", "Độ hồi trễ (hysteresis)");
      hystInp.setAttribute("data-field", "hysteresis");
      hystInp.placeholder = `Hồi trễ (±${meta.unit})`;
      hystInp.title = "Độ hồi trễ tránh bật tắt liên tục";
      hystInp.value =
        initial && initial.hysteresis !== undefined && initial.hysteresis !== ""
          ? String(initial.hysteresis)
          : String(meta.defaultHyst || 0);

      dynamicWrap.appendChild(opSel);
      dynamicWrap.appendChild(valInp);
      dynamicWrap.appendChild(hystInp);
    } else if (meta.kind === "time_window") {
      const startInp = document.createElement("input");
      startInp.type = "time";
      startInp.className = "auto-input";
      startInp.setAttribute("aria-label", "Từ giờ");
      startInp.setAttribute("data-field", "start_hhmm");
      startInp.value = (initial && (initial.start_hhmm || initial.start)) || "18:00";

      const endInp = document.createElement("input");
      endInp.type = "time";
      endInp.className = "auto-input";
      endInp.setAttribute("aria-label", "Đến giờ");
      endInp.setAttribute("data-field", "end_hhmm");
      endInp.value = (initial && (initial.end_hhmm || initial.end)) || "22:00";

      dynamicWrap.appendChild(startInp);
      dynamicWrap.appendChild(endInp);
    } else {
      const stateSel = document.createElement("select");
      stateSel.className = "auto-select";
      stateSel.setAttribute("aria-label", "Trạng thái điều kiện");
      stateSel.setAttribute("data-field", "state");
      const states = meta.states || [{ v: "ON", l: "Đang bật" }, { v: "OFF", l: "Đang tắt" }];
      states.forEach((st) => {
        const o = document.createElement("option");
        o.value = st.v;
        o.textContent = st.l;
        stateSel.appendChild(o);
      });
      const initVal = String((initial && (initial.value || initial.state)) || states[0].v).toUpperCase();
      stateSel.value = states.some((s) => s.v === initVal) ? initVal : states[0].v;
      dynamicWrap.appendChild(stateSel);
    }
  }

  function createConditionRow(container, initial) {
    const row = document.createElement("div");
    row.className = "auto-builder-row";

    const srcSel = document.createElement("select");
    srcSel.className = "auto-select";
    srcSel.setAttribute("aria-label", "Nguồn điều kiện");
    srcSel.setAttribute("data-field", "source");
    CONDITION_SOURCES.forEach((s) => {
      const o = document.createElement("option");
      o.value = s.id;
      o.textContent = s.label;
      srcSel.appendChild(o);
    });
    const initSource = (initial && (initial.source || initial.device_id || initial.type)) || "temp_sensor";
    srcSel.value = SOURCE_MAP[initSource] ? initSource : "temp_sensor";

    const dynWrap = document.createElement("div");
    dynWrap.style.display = "contents";
    dynWrap.setAttribute("data-cond-inputs", "1");

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "auto-row-remove-btn";
    delBtn.textContent = "Xóa";
    delBtn.addEventListener("click", () => {
      if (container.children.length > 1) {
        row.remove();
      }
    });

    row.appendChild(srcSel);
    row.appendChild(dynWrap);
    row.appendChild(delBtn);
    container.appendChild(row);

    renderConditionInputs(row, srcSel.value, initial);
    srcSel.addEventListener("change", () => {
      renderConditionInputs(row, srcSel.value, null);
    });
    return row;
  }

  function syncWeekdayPills(modal) {
    const grid = modal.querySelector("#autoModalWeekdaysGrid");
    if (!grid) return;
    grid.querySelectorAll(".auto-weekday-pill").forEach((lbl) => {
      const cb = lbl.querySelector('input[type="checkbox"]');
      lbl.classList.toggle("is-checked", Boolean(cb && cb.checked));
    });
  }

  function syncLogicOptionStyles(modal) {
    const grp = modal.querySelector("#autoRuleLogicGroup");
    if (!grp) return;
    grp.querySelectorAll(".auto-logic-option").forEach((lbl) => {
      const r = lbl.querySelector('input[type="radio"]');
      lbl.classList.toggle("is-selected", Boolean(r && r.checked));
    });
  }

  function openModal(kind, editItem) {
    const modal = ensureModalInDom();
    if (!modal) return;
    setModalFeedback("");
    hideModalConfirmBanner();

    const kindInput = modal.querySelector("#autoModalKind");
    const editIdInput = modal.querySelector("#autoModalEditId");
    const titleEl = modal.querySelector("#autoModalTitle");
    const saveBtn = modal.querySelector("#btnAutoModalSave");

    kindInput.value = kind;
    editIdInput.value = "";

    modal.querySelector("#autoModalTimerFields").hidden = kind !== "timer";
    modal.querySelector("#autoModalScheduleFields").hidden = kind !== "schedule";
    modal.querySelector("#autoModalCommandFields").hidden = kind !== "command";
    modal.querySelector("#autoModalRuleFields").hidden = kind !== "rule";

    if (kind === "timer") {
      const devSel = modal.querySelector("#autoModalTimerDevice");
      const actSel = modal.querySelector("#autoModalTimerAction");
      const hInp = modal.querySelector("#autoModalTimerHours");
      const mInp = modal.querySelector("#autoModalTimerMinutes");
      const sInp = modal.querySelector("#autoModalTimerSeconds");
      const repSel = modal.querySelector("#autoModalTimerRepeat");

      const initDev = (editItem && (editItem.device_id || editItem.raw_target)) || "living_room_light";
      populateDeviceSelect(devSel, true, initDev);
      populateActionSelect(actSel, devSel.value, (editItem && editItem.action) || "turn_on");

      if (editItem) {
        editIdInput.value = String(editItem.id || editItem.timer_id || "");
        const rem = Math.max(1, computeRemainingSeconds(editItem));
        hInp.value = String(Math.floor(rem / 3600));
        mInp.value = String(Math.floor((rem % 3600) / 60));
        sInp.value = String(rem % 60);
        repSel.value = String(editItem.repeat_rule || editItem.repeat || "once");
        titleEl.textContent = "Chỉnh sửa hẹn giờ";
        saveBtn.textContent = "Cập nhật hẹn giờ";
      } else {
        hInp.value = "0";
        mInp.value = "0";
        sInp.value = "30";
        repSel.value = "once";
        titleEl.textContent = "Tạo hẹn giờ mới";
        saveBtn.textContent = "Tạo hẹn giờ";
      }
    } else if (kind === "schedule") {
      const devSel = modal.querySelector("#autoModalScheduleDevice");
      const actSel = modal.querySelector("#autoModalScheduleAction");
      const timeInp = modal.querySelector("#autoModalScheduleTime");
      const typeSel = modal.querySelector("#autoModalScheduleType");
      const wdWrap = modal.querySelector("#autoModalWeekdaysWrap");
      const lblInp = modal.querySelector("#autoModalScheduleLabel");

      const initDev = (editItem && editItem.device_id) || "living_room_light";
      populateDeviceSelect(devSel, false, initDev);
      populateActionSelect(actSel, devSel.value, (editItem && editItem.action) || "turn_on");

      const wdChecks = modal.querySelectorAll('#autoModalWeekdaysGrid input[type="checkbox"]');
      wdChecks.forEach((cb) => {
        cb.checked = false;
      });

      if (editItem) {
        editIdInput.value = String(editItem.schedule_id || editItem.id || "");
        timeInp.value = String(editItem.time_hhmm || "07:00");
        const wds = parseWeekdayIndices(editItem.weekdays);
        const stType = wds.length > 0 ? "weekly" : String(editItem.schedule_type || "once").toLowerCase();
        typeSel.value = stType === "daily" || stType === "weekly" ? stType : "once";
        wdChecks.forEach((cb) => {
          cb.checked = wds.includes(Number(cb.value));
        });
        lblInp.value = String(editItem.label || "");
        titleEl.textContent = "Chỉnh sửa lịch trình";
        saveBtn.textContent = "Cập nhật lịch trình";
      } else {
        timeInp.value = "07:00";
        typeSel.value = "daily";
        lblInp.value = "";
        titleEl.textContent = "Tạo lịch trình mới";
        saveBtn.textContent = "Tạo lịch trình";
      }
      wdWrap.hidden = typeSel.value !== "weekly";
      syncWeekdayPills(modal);
    } else if (kind === "command") {
      const phraseInp = modal.querySelector("#autoModalCommandPhrase");
      const stepsList = modal.querySelector("#autoModalCmdStepsList");
      stepsList.innerHTML = "";
      if (editItem) {
        editIdInput.value = String(editItem.command_id || editItem.id || "");
        phraseInp.value = String(editItem.phrase || "");
        const steps = Array.isArray(editItem.steps) && editItem.steps.length ? editItem.steps : [{ device_id: "living_room_light", action: "turn_off" }];
        steps.forEach((st) => createActionRow(stepsList, st));
        titleEl.textContent = "Chỉnh sửa lệnh tùy chỉnh";
        saveBtn.textContent = "Cập nhật lệnh";
      } else {
        phraseInp.value = "";
        createActionRow(stepsList, { device_id: "living_room_light", action: "turn_off" });
        titleEl.textContent = "Tạo lệnh tùy chỉnh mới";
        saveBtn.textContent = "Tạo lệnh mới";
      }
    } else if (kind === "rule") {
      const nameInp = modal.querySelector("#autoRuleNameInput");
      const condList = modal.querySelector("#autoRuleConditionsList");
      const actList = modal.querySelector("#autoRuleActionsList");
      const elseChk = modal.querySelector("#chkAutoEnableElse");
      const elseWrap = modal.querySelector("#autoRuleElseWrap");
      const elseList = modal.querySelector("#autoRuleElseActionsList");
      const cooldownInp = modal.querySelector("#autoRuleCooldownInput");

      condList.innerHTML = "";
      actList.innerHTML = "";
      elseList.innerHTML = "";

      if (editItem) {
        const norm = normalizeRuleObject(editItem) || editItem;
        editIdInput.value = String(norm.rule_id || "");
        nameInp.value = String(norm.name || "");
        const logicVal = norm.logic === "OR" ? "OR" : "AND";
        const radio = modal.querySelector(`input[name="autoRuleLogic"][value="${logicVal}"]`);
        if (radio) radio.checked = true;
        const conds = norm.conditions && norm.conditions.length ? norm.conditions : [{ source: "temp_sensor", operator: ">", value: 30, hysteresis: 1 }];
        conds.forEach((c) => createConditionRow(condList, c));
        const acts = norm.actions && norm.actions.length ? norm.actions : [{ device_id: "living_room_light", action: "turn_on" }];
        acts.forEach((a) => createActionRow(actList, a));
        const hasElse = Array.isArray(norm.else_actions) && norm.else_actions.length > 0;
        elseChk.checked = hasElse;
        elseWrap.hidden = !hasElse;
        if (hasElse) {
          norm.else_actions.forEach((a) => createActionRow(elseList, a));
        }
        cooldownInp.value = String(norm.cooldown_seconds !== undefined ? norm.cooldown_seconds : 10);
        titleEl.textContent = "Chỉnh sửa luật tự động";
        saveBtn.textContent = "Cập nhật luật";
      } else {
        nameInp.value = "";
        const radioAnd = modal.querySelector('input[name="autoRuleLogic"][value="AND"]');
        if (radioAnd) radioAnd.checked = true;
        createConditionRow(condList, { source: "temp_sensor", operator: ">", value: 30, hysteresis: 1 });
        createActionRow(actList, { device_id: "living_room_light", action: "turn_on" });
        elseChk.checked = false;
        elseWrap.hidden = true;
        cooldownInp.value = "10";
        titleEl.textContent = "Tạo luật tự động mới";
        saveBtn.textContent = "Lưu luật tự động";
      }
      syncLogicOptionStyles(modal);
    }

    modal.hidden = false;
    modal.classList.remove("hidden");
    const focusable = modal.querySelector("input:not([type=hidden]):not([disabled]), select:not([disabled])");
    if (focusable) {
      setTimeout(() => focusable.focus(), 20);
    }
  }

  function closeModal() {
    const modal = getModalRoot();
    if (!modal) return;
    hideModalConfirmBanner();
    setModalFeedback("");
    modal.hidden = true;
    modal.classList.add("hidden");
  }

  function collectActionRows(container) {
    const rows = Array.from(container.querySelectorAll(".auto-builder-row"));
    return rows
      .map((row) => {
        const dev = row.querySelector('[data-field="device_id"]');
        const act = row.querySelector('[data-field="action"]');
        if (!dev || !act) return null;
        return {
          device_id: dev.value,
          action: normalizeActionForDevice(dev.value, act.value),
        };
      })
      .filter(Boolean);
  }

  function collectConditionRows(container) {
    const rows = Array.from(container.querySelectorAll(".auto-builder-row"));
    return rows
      .map((row) => {
        const srcEl = row.querySelector('[data-field="source"]');
        if (!srcEl) return null;
        const source = srcEl.value;
        const meta = SOURCE_MAP[source] || {};
        if (meta.kind === "numeric") {
          const opEl = row.querySelector('[data-field="operator"]');
          const valEl = row.querySelector('[data-field="value"]');
          const hystEl = row.querySelector('[data-field="hysteresis"]');
          const valNum = Number(valEl ? valEl.value : meta.defaultVal);
          const hystNum = Math.max(0, Number(hystEl ? hystEl.value : 0) || 0);
          return {
            type: "sensor",
            source,
            operator: (opEl && opEl.value) || ">",
            value: Number.isFinite(valNum) ? valNum : meta.defaultVal,
            hysteresis: hystNum,
          };
        }
        if (meta.kind === "time_window") {
          const sEl = row.querySelector('[data-field="start_hhmm"]');
          const eEl = row.querySelector('[data-field="end_hhmm"]');
          return {
            type: "time_window",
            source: "time_window",
            start_hhmm: (sEl && sEl.value) || "18:00",
            end_hhmm: (eEl && eEl.value) || "22:00",
          };
        }
        const stEl = row.querySelector('[data-field="state"]');
        const stVal = String((stEl && stEl.value) || "ON").toUpperCase();
        const isHouse = source === "house_mode";
        const isSound = source === "sound_sensor";
        return {
          type: isHouse ? "house_mode" : isSound ? "sensor" : "device",
          source,
          device_id: isHouse || isSound ? undefined : source,
          operator: "==",
          state: stVal,
          value: stVal,
        };
      })
      .filter(Boolean);
  }

  async function handleModalSave() {
    const modal = getModalRoot();
    if (!modal) return;
    const kind = modal.querySelector("#autoModalKind").value;
    const editId = modal.querySelector("#autoModalEditId").value.trim();
    const saveBtn = modal.querySelector("#btnAutoModalSave");

    let url = "";
    let method = "POST";
    let payload = {};

    if (kind === "timer") {
      const device_id = modal.querySelector("#autoModalTimerDevice").value;
      const action = normalizeActionForDevice(device_id, modal.querySelector("#autoModalTimerAction").value);
      const hours = Math.max(0, Number(modal.querySelector("#autoModalTimerHours").value) || 0);
      const minutes = Math.max(0, Number(modal.querySelector("#autoModalTimerMinutes").value) || 0);
      const seconds = Math.max(0, Number(modal.querySelector("#autoModalTimerSeconds").value) || 0);
      const repeat = modal.querySelector("#autoModalTimerRepeat").value || "once";
      if (hours <= 0 && minutes <= 0 && seconds <= 0) {
        setModalFeedback("Vui lòng nhập thời gian đếm ngược lớn hơn 0.", "error");
        return;
      }
      url = editId ? `/api/timers/${encodeURIComponent(editId)}` : "/api/timers";
      method = editId ? "PATCH" : "POST";
      payload = { device_id, action, new_action: action, hours, minutes, seconds, repeat };
    } else if (kind === "schedule") {
      const device_id = modal.querySelector("#autoModalScheduleDevice").value;
      const action = normalizeActionForDevice(device_id, modal.querySelector("#autoModalScheduleAction").value);
      const time_hhmm = modal.querySelector("#autoModalScheduleTime").value.trim();
      const schedule_type = modal.querySelector("#autoModalScheduleType").value;
      const label = modal.querySelector("#autoModalScheduleLabel").value.trim();
      if (!/^\d{2}:\d{2}$/.test(time_hhmm)) {
        setModalFeedback("Vui lòng chọn giờ thực thi hợp lệ (HH:MM).", "error");
        return;
      }
      const weekdays = [];
      if (schedule_type === "weekly") {
        modal.querySelectorAll('#autoModalWeekdaysGrid input[type="checkbox"]:checked').forEach((cb) => {
          weekdays.push(Number(cb.value));
        });
        if (!weekdays.length) {
          setModalFeedback("Vui lòng chọn ít nhất một thứ trong tuần.", "error");
          return;
        }
      }
      url = editId ? `/api/schedules/${encodeURIComponent(editId)}` : "/api/schedules";
      method = editId ? "PATCH" : "POST";
      payload = {
        device_id,
        action,
        time_hhmm,
        schedule_type,
        weekdays,
        label,
      };
    } else if (kind === "command") {
      const phrase = modal.querySelector("#autoModalCommandPhrase").value.trim();
      const steps = collectActionRows(modal.querySelector("#autoModalCmdStepsList"));
      if (!phrase) {
        setModalFeedback("Vui lòng nhập câu lệnh kích hoạt.", "error");
        return;
      }
      if (!steps.length) {
        setModalFeedback("Vui lòng thêm ít nhất một bước thực hiện.", "error");
        return;
      }
      url = editId ? `/api/scenes/${encodeURIComponent(editId)}` : "/api/scenes";
      method = editId ? "PUT" : "POST";
      payload = {
        phrase,
        steps,
        steps_text: steps.map((s) => formatDeviceActionVi(s.device_id, s.action)).join(" rồi "),
      };
    } else if (kind === "rule") {
      const name = modal.querySelector("#autoRuleNameInput").value.trim();
      const logicRadio = modal.querySelector('input[name="autoRuleLogic"]:checked');
      const logic = logicRadio && logicRadio.value === "OR" ? "OR" : "AND";
      const conditions = collectConditionRows(modal.querySelector("#autoRuleConditionsList"));
      const actions = collectActionRows(modal.querySelector("#autoRuleActionsList"));
      const enableElse = modal.querySelector("#chkAutoEnableElse").checked;
      const else_actions = enableElse ? collectActionRows(modal.querySelector("#autoRuleElseActionsList")) : [];
      const cooldown_seconds = Math.max(0, Number(modal.querySelector("#autoRuleCooldownInput").value) || 0);

      if (!conditions.length) {
        setModalFeedback("Vui lòng thêm ít nhất một điều kiện kích hoạt.", "error");
        return;
      }
      if (!actions.length) {
        setModalFeedback("Vui lòng thêm ít nhất một hành động thực thi.", "error");
        return;
      }

      url = editId ? `/api/rules/${encodeURIComponent(editId)}` : "/api/rules";
      method = editId ? "PATCH" : "POST";
      payload = {
        name,
        label: name,
        logic,
        conditions,
        actions,
        else_actions,
        cooldown_seconds,
      };

      // Backward-compatible top-level fields for single simple device/sensor rule
      const firstCond = conditions[0];
      const firstAct = actions[0];
      if (firstCond && firstAct && firstCond.source !== "time_window" && firstCond.source !== "house_mode") {
        payload.when_device_id = firstCond.source;
        payload.when_state = firstCond.state || (firstCond.operator === "<" || firstCond.operator === "<=" ? (firstCond.source === "soil_sensor" ? "DRY" : "LOW") : (firstCond.source === "soil_sensor" ? "WET" : "HIGH"));
        payload.then_device_id = firstAct.device_id;
        payload.then_action = firstAct.action;
        if (else_actions[0]) {
          payload.else_device_id = else_actions[0].device_id;
          payload.else_action = else_actions[0].action;
        }
      }
    }

    if (saveBtn) saveBtn.disabled = true;
    setModalFeedback("Đang lưu cấu hình...", "");
    try {
      const res = await apiFetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) {
        setModalFeedback(data.error || "Không thể lưu tự động hóa.", "error");
        return;
      }
      if (data.requires_confirmation && (data.pending_id || data.confirm_token)) {
        setModalFeedback("", "");
        showModalConfirmBanner(data);
        return;
      }
      if (data.snapshot) {
        ingestAutomationData(data.snapshot);
      } else {
        await fetchAutomationState();
      }
      closeModal();
    } catch (err) {
      setModalFeedback(`Lỗi kết nối máy chủ: ${err}`, "error");
    } finally {
      if (saveBtn) saveBtn.disabled = false;
    }
  }

  async function sendConfirmationDecision(pendingObj, confirmed, sourceContext) {
    if (!pendingObj || !pendingObj.pending_id) return;
    try {
      const res = await apiFetch("/api/automation/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pending_id: pendingObj.pending_id,
          confirm_token: pendingObj.confirm_token || pendingObj.pending_id,
          confirmed: Boolean(confirmed),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (sourceContext === "modal") {
        hideModalConfirmBanner();
        if (!res.ok || data.ok === false) {
          setModalFeedback(data.error || "Xác nhận thất bại.", "error");
          return;
        }
        if (data.snapshot) ingestAutomationData(data.snapshot);
        else await fetchAutomationState();
        closeModal();
      } else if (sourceContext === "page") {
        hidePageConfirmBanner();
        if (data.snapshot) ingestAutomationData(data.snapshot);
        else await fetchAutomationState();
      } else if (sourceContext === "ai") {
        state.pendingAiConfirm = null;
        const confirmRow = q("#autoAiConfirmRow");
        if (confirmRow) confirmRow.hidden = true;
        const replyEl = q("#autoAiReplyText");
        if (replyEl) {
          replyEl.textContent = String(
            data.reply || data.exact_spoken_reply || (confirmed ? "Đã xác nhận thực hiện." : "Đã hủy thao tác.")
          );
        }
        if (data.snapshot) ingestAutomationData(data.snapshot);
        else await fetchAutomationState();
      }
    } catch (_) {
      if (sourceContext === "modal") setModalFeedback("Lỗi kết nối khi gửi xác nhận.", "error");
    }
  }

  // ==================== ITEM & HEADER ACTIONS ====================
  async function handleItemAction(act, id, btnEl) {
    if (!act || !id) return;

    if (act === "edit-timer") {
      const found = state.timers.find((t) => String(t.id || t.timer_id) === id);
      if (found) openModal("timer", found);
      return;
    }
    if (act === "edit-schedule") {
      const found = state.schedules.find((s) => String(s.schedule_id || s.id) === id);
      if (found) openModal("schedule", found);
      return;
    }
    if (act === "edit-command") {
      const found = state.commands.find((c) => String(c.command_id || c.id) === id);
      if (found) openModal("command", found);
      return;
    }
    if (act === "edit-rule") {
      const found = state.rules.find((r) => String(r.rule_id) === id);
      if (found) openModal("rule", found);
      return;
    }

    let url = "";
    let method = "DELETE";
    let body = undefined;

    if (act === "delete-timer") {
      url = `/api/timers/${encodeURIComponent(id)}`;
    } else if (act === "delete-schedule") {
      url = `/api/schedules/${encodeURIComponent(id)}`;
    } else if (act === "toggle-schedule") {
      const curEnabled = btnEl && btnEl.getAttribute("data-ap-enabled") === "1";
      url = `/api/schedules/${encodeURIComponent(id)}`;
      method = "PATCH";
      body = JSON.stringify({ enabled: !curEnabled });
    } else if (act === "delete-command") {
      url = `/api/scenes/${encodeURIComponent(id)}`;
    } else if (act === "run-command") {
      url = `/api/scenes/${encodeURIComponent(id)}/run`;
      method = "POST";
    } else if (act === "delete-rule") {
      url = `/api/rules/${encodeURIComponent(id)}`;
    } else if (act === "toggle-rule") {
      const curEnabled = btnEl && btnEl.getAttribute("data-ap-enabled") === "1";
      url = `/api/rules/${encodeURIComponent(id)}`;
      method = "PATCH";
      body = JSON.stringify({ enabled: !curEnabled });
    }

    if (!url) return;
    if (btnEl) btnEl.disabled = true;
    try {
      const res = await apiFetch(url, {
        method,
        headers: body ? { "Content-Type": "application/json" } : {},
        body,
      });
      const data = await res.json().catch(() => ({}));
      if (data.requires_confirmation && (data.pending_id || data.confirm_token)) {
        showPageConfirmBanner(data);
        return;
      }
      if (data.snapshot) {
        ingestAutomationData(data.snapshot);
      } else {
        await fetchAutomationState();
      }
    } catch (_) {
    } finally {
      if (btnEl) btnEl.disabled = false;
    }
  }

  async function toggleHouseMode() {
    const nextMode = state.houseMode === "AWAY" ? "HOME" : "AWAY";
    const btn = q("#btnToggleHouseMode");
    const dashBtn = q("#dashHouseModePill");
    if (btn) btn.disabled = true;
    if (dashBtn) dashBtn.disabled = true;
    try {
      const res = await apiFetch("/api/house_mode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: nextMode }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.ok !== false) {
        state.houseMode = String(data.house_mode || data.mode || nextMode).toUpperCase() === "AWAY" ? "AWAY" : "HOME";
        if (data.snapshot) ingestAutomationData(data.snapshot);
        else renderHouseModeUI();
      }
    } catch (_) {
    } finally {
      if (btn) btn.disabled = false;
      if (dashBtn) dashBtn.disabled = false;
    }
  }

  async function triggerResetAutomation() {
    const btn = q("#btnAutoResetAll");
    if (btn) btn.disabled = true;
    try {
      const res = await apiFetch("/api/automation/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scope: "all" }),
      });
      const data = await res.json().catch(() => ({}));
      if (data.requires_confirmation && (data.pending_id || data.confirm_token)) {
        showPageConfirmBanner(data);
        return;
      }
      if (data.snapshot) ingestAutomationData(data.snapshot);
      else await fetchAutomationState();
    } catch (_) {
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function handleQuickAiCommand(ev) {
    ev.preventDefault();
    const input = q("#autoAiInput");
    const btn = q("#btnAutoAiSend");
    const outBox = q("#autoAiOutput");
    const userTxt = q("#autoAiUserText");
    const replyTxt = q("#autoAiReplyText");
    const confirmRow = q("#autoAiConfirmRow");
    if (!input) return;
    const text = input.value.trim();
    if (!text) return;

    if (outBox) outBox.hidden = false;
    if (userTxt) userTxt.textContent = text;
    if (replyTxt) replyTxt.textContent = "Đang xử lý...";
    if (confirmRow) confirmRow.hidden = true;
    state.pendingAiConfirm = null;
    if (btn) btn.disabled = true;

    try {
      const res = await apiFetch("/api/text_command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, command: text }),
      });
      const data = await res.json().catch(() => ({}));
      const replyStr = String(
        data.exact_spoken_reply || data.reply || data.prompt_question || data.error || "Đã xử lý lệnh."
      );
      if (replyTxt) replyTxt.textContent = replyStr;
      input.value = "";

      const needsConfirm = Boolean(
        data.requires_confirmation ||
          data.pending_confirmation ||
          data.awaiting_confirmation ||
          data.pending_id ||
          data.confirm_token
      );
      if (needsConfirm) {
        const pid = String(data.pending_id || data.confirm_token || "");
        state.pendingAiConfirm = {
          pending_id: pid,
          confirm_token: String(data.confirm_token || pid),
          viaText: !pid,
        };
        if (confirmRow) confirmRow.hidden = false;
      }

      if (data.snapshot) {
        ingestAutomationData(data.snapshot);
      } else {
        await fetchAutomationState();
      }
    } catch (err) {
      if (replyTxt) replyTxt.textContent = `Lỗi gửi lệnh: ${err}`;
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function handleAiConfirmClick(confirmed) {
    const pending = state.pendingAiConfirm;
    if (!pending) return;
    if (pending.pending_id && !pending.viaText) {
      await sendConfirmationDecision(pending, confirmed, "ai");
      return;
    }
    // Fallback to text_command confirmation when backend uses conversational confirmation
    const phrase = confirmed ? "Đồng ý" : "Hủy";
    const confirmRow = q("#autoAiConfirmRow");
    const replyTxt = q("#autoAiReplyText");
    state.pendingAiConfirm = null;
    if (confirmRow) confirmRow.hidden = true;
    try {
      const res = await apiFetch("/api/text_command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: phrase, command: phrase }),
      });
      const data = await res.json().catch(() => ({}));
      if (replyTxt) {
        replyTxt.textContent = String(data.exact_spoken_reply || data.reply || (confirmed ? "Đã xác nhận." : "Đã hủy."));
      }
      if (data.snapshot) ingestAutomationData(data.snapshot);
      else await fetchAutomationState();
    } catch (_) {}
  }

  // ==================== EVENT BINDING ====================
  function bindModalEvents(modal) {
    if (!modal || modal.dataset.apBound === "1") return;
    modal.dataset.apBound = "1";

    const closeBtn = modal.querySelector("#btnAutoModalClose");
    const cancelBtn = modal.querySelector("#btnAutoModalCancel");
    const saveBtn = modal.querySelector("#btnAutoModalSave");
    const form = modal.querySelector("#autoModalForm");

    if (closeBtn) closeBtn.addEventListener("click", closeModal);
    if (cancelBtn) cancelBtn.addEventListener("click", closeModal);
    if (saveBtn) saveBtn.addEventListener("click", handleModalSave);
    if (form) {
      form.addEventListener("submit", (ev) => {
        ev.preventDefault();
        handleModalSave();
      });
    }

    modal.addEventListener("click", (ev) => {
      if (ev.target === modal) closeModal();
    });

    const timerDev = modal.querySelector("#autoModalTimerDevice");
    const timerAct = modal.querySelector("#autoModalTimerAction");
    if (timerDev && timerAct) {
      timerDev.addEventListener("change", () => populateActionSelect(timerAct, timerDev.value, timerAct.value));
    }

    const schedDev = modal.querySelector("#autoModalScheduleDevice");
    const schedAct = modal.querySelector("#autoModalScheduleAction");
    if (schedDev && schedAct) {
      schedDev.addEventListener("change", () => populateActionSelect(schedAct, schedDev.value, schedAct.value));
    }

    const schedType = modal.querySelector("#autoModalScheduleType");
    const wdWrap = modal.querySelector("#autoModalWeekdaysWrap");
    if (schedType && wdWrap) {
      schedType.addEventListener("change", () => {
        wdWrap.hidden = schedType.value !== "weekly";
      });
    }

    const wdGrid = modal.querySelector("#autoModalWeekdaysGrid");
    if (wdGrid) {
      wdGrid.addEventListener("change", () => syncWeekdayPills(modal));
    }

    const logicGroup = modal.querySelector("#autoRuleLogicGroup");
    if (logicGroup) {
      logicGroup.addEventListener("change", () => syncLogicOptionStyles(modal));
    }

    const addCmdBtn = modal.querySelector("#btnAutoAddCmdStep");
    if (addCmdBtn) {
      addCmdBtn.addEventListener("click", () => {
        createActionRow(modal.querySelector("#autoModalCmdStepsList"), { device_id: "bedroom_light", action: "turn_off" });
      });
    }

    const addCondBtn = modal.querySelector("#btnAutoAddCondition");
    if (addCondBtn) {
      addCondBtn.addEventListener("click", () => {
        createConditionRow(modal.querySelector("#autoRuleConditionsList"), { source: "soil_sensor", operator: "<", value: 40, hysteresis: 5 });
      });
    }

    const addActBtn = modal.querySelector("#btnAutoAddAction");
    if (addActBtn) {
      addActBtn.addEventListener("click", () => {
        createActionRow(modal.querySelector("#autoRuleActionsList"), { device_id: "garden_pump", action: "turn_on" });
      });
    }

    const elseChk = modal.querySelector("#chkAutoEnableElse");
    const elseWrap = modal.querySelector("#autoRuleElseWrap");
    const elseList = modal.querySelector("#autoRuleElseActionsList");
    if (elseChk && elseWrap && elseList) {
      elseChk.addEventListener("change", () => {
        elseWrap.hidden = !elseChk.checked;
        if (elseChk.checked && elseList.children.length === 0) {
          createActionRow(elseList, { device_id: "garden_pump", action: "turn_off" });
        }
      });
    }

    const addElseBtn = modal.querySelector("#btnAutoAddElseAction");
    if (addElseBtn && elseList) {
      addElseBtn.addEventListener("click", () => {
        createActionRow(elseList, { device_id: "living_room_light", action: "turn_off" });
      });
    }

    const yesBtn = modal.querySelector("#btnAutoModalConfirmYes");
    const noBtn = modal.querySelector("#btnAutoModalConfirmNo");
    if (yesBtn) yesBtn.addEventListener("click", () => sendConfirmationDecision(state.pendingModalConfirm, true, "modal"));
    if (noBtn) noBtn.addEventListener("click", () => sendConfirmationDecision(state.pendingModalConfirm, false, "modal"));
  }

  function bindGlobalDelegatedEvents() {
    if (window.__shAutoPanelDelegatedBound) return;
    window.__shAutoPanelDelegatedBound = true;

    document.addEventListener("click", (ev) => {
      const target = ev.target;
      if (!target || typeof target.closest !== "function") return;

      // Open modal triggers (works on both /automation and / dashboard!)
      const openBtn = target.closest("[data-auto-open-modal]");
      if (openBtn) {
        const kind = openBtn.getAttribute("data-auto-open-modal") || "rule";
        openModal(kind, null);
        return;
      }

      // Tab buttons
      const tabBtn = target.closest("[data-auto-tab]");
      if (tabBtn) {
        state.activeTab = tabBtn.getAttribute("data-auto-tab") || "all";
        renderCountsAndTabs();
        return;
      }

      // KPI pill clicks filter to tab (click again returns to all)
      const kpiBtn = target.closest("[data-kpi-tab]");
      if (kpiBtn) {
        const key = kpiBtn.getAttribute("data-kpi-tab") || "all";
        state.activeTab = state.activeTab === key ? "all" : key;
        renderCountsAndTabs();
        return;
      }

      // House mode toggle
      if (target.closest("#btnToggleHouseMode") || target.closest("#dashHouseModePill")) {
        toggleHouseMode();
        return;
      }

      // Reset all automation
      if (target.closest("#btnAutoResetAll")) {
        triggerResetAutomation();
        return;
      }

      // Page-level confirmation
      if (target.closest("#btnAutoPageConfirmYes")) {
        sendConfirmationDecision(state.pendingPageConfirm, true, "page");
        return;
      }
      if (target.closest("#btnAutoPageConfirmNo")) {
        sendConfirmationDecision(state.pendingPageConfirm, false, "page");
        return;
      }

      // AI quick command confirmation
      if (target.closest("#btnAutoAiConfirmYes")) {
        handleAiConfirmClick(true);
        return;
      }
      if (target.closest("#btnAutoAiConfirmNo")) {
        handleAiConfirmClick(false);
        return;
      }

      // Item CRUD actions
      const actBtn = target.closest("[data-ap-action]");
      if (actBtn) {
        const act = actBtn.getAttribute("data-ap-action") || "";
        const id = actBtn.getAttribute("data-ap-id") || "";
        handleItemAction(act, id, actBtn);
      }
    });

    document.addEventListener("submit", (ev) => {
      if (ev.target && ev.target.id === "autoAiForm") {
        handleQuickAiCommand(ev);
      }
    });

    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") {
        const modal = getModalRoot();
        if (modal && !modal.hidden && !modal.classList.contains("hidden")) {
          closeModal();
        }
      }
    });

    // Live sync with dashboard app.js snapshots
    window.addEventListener("sh:snapshot", (ev) => {
      if (ev && ev.detail) {
        ingestAutomationData(ev.detail);
      }
    });

    // Re-init on SPA route transitions
    const onRouteChange = () => {
      initSmartHomeAutomationPanel();
    };
    window.addEventListener("smarthome:spa-navigated", onRouteChange);
    window.addEventListener("sh:spa-route", onRouteChange);
  }

  // ==================== PUBLIC INIT ====================
  function initSmartHomeAutomationPanel() {
    bindGlobalDelegatedEvents();
    const existingModal = getModalRoot();
    if (existingModal) {
      bindModalEvents(existingModal);
    }

    loadUiRegistry();
    startCountdownTicker();
    startFallbackPolling();

    if (isAutomationPageActive()) {
      fetchSessionBadge();
      fetchAutomationState();
      connectAutomationSse();
    } else {
      disconnectAutomationSse();
      if (isDashboardPanelActive()) {
        renderAll();
      }
    }
  }

  window.initSmartHomeAutomationPanel = initSmartHomeAutomationPanel;
  window.SmartHomeAutomationPanel = {
    init: initSmartHomeAutomationPanel,
    refresh: fetchAutomationState,
    openModal,
    closeModal,
    getState: () => state,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initSmartHomeAutomationPanel);
  } else {
    initSmartHomeAutomationPanel();
  }
})();
