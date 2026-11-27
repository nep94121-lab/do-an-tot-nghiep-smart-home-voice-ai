(function initSmartHomeWiringGuide() {
  "use strict";

  if (typeof window === "undefined" || typeof document === "undefined") {
    return;
  }

  const STORAGE_KEY = "smarthome_wiring_prefs_v1";
  const CONTRACT_URL = "/static/data/wiring_contract.json";

  let contractPromise = null;
  let cachedContract = null;

  function loadContract() {
    if (cachedContract) return Promise.resolve(cachedContract);
    if (contractPromise) return contractPromise;
    contractPromise = fetch(CONTRACT_URL, { cache: "no-cache", credentials: "same-origin" })
      .then((res) => {
        if (!res || !res.ok) {
          throw new Error("Không thể tải dữ liệu sơ đồ nối dây từ máy chủ.");
        }
        return res.json();
      })
      .then((data) => {
        cachedContract = data;
        return data;
      })
      .catch((err) => {
        contractPromise = null;
        throw err;
      });
    return contractPromise;
  }

  function readPrefs() {
    const defaults = { wiresVisible: true, selectedModuleId: "all" };
    try {
      const raw = window.localStorage && window.localStorage.getItem(STORAGE_KEY);
      if (!raw) return defaults;
      const parsed = JSON.parse(raw);
      return {
        wiresVisible: parsed && typeof parsed.wiresVisible === "boolean" ? parsed.wiresVisible : true,
        selectedModuleId:
          parsed && typeof parsed.selectedModuleId === "string" && parsed.selectedModuleId.trim()
            ? parsed.selectedModuleId.trim()
            : "all",
      };
    } catch (_) {
      return defaults;
    }
  }

  function writePrefs(prefs) {
    try {
      if (window.localStorage) {
        window.localStorage.setItem(
          STORAGE_KEY,
          JSON.stringify({
            wiresVisible: Boolean(prefs.wiresVisible),
            selectedModuleId: String(prefs.selectedModuleId || "all"),
          })
        );
      }
    } catch (_) {}
  }

  function escHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function isWarningNote(wire) {
    if (!wire) return false;
    const text = `${wire.notes || ""} ${wire.power_gnd_note_vi || ""}`.toLowerCase();
    return (
      text.includes("strictly 3.3v") ||
      text.includes("bắt buộc") ||
      text.includes("tuyệt đối không") ||
      text.includes("btl") ||
      text.includes("active-low") ||
      text.includes("q1")
    );
  }

  function createController(options) {
    const opts = options || {};
    const instanceId = opts.instanceId || "default";
    const toolbarMount =
      typeof opts.toolbarMount === "string" ? document.getElementById(opts.toolbarMount) : opts.toolbarMount;
    const panelMount =
      typeof opts.panelMount === "string" ? document.getElementById(opts.panelMount) : opts.panelMount;
    const inspectMount =
      typeof opts.inspectMount === "string" ? document.getElementById(opts.inspectMount) : opts.inspectMount;
    const adapter = opts.adapter || {};
    const extraToolbarHtml = opts.extraToolbarHtml || "";
    const onStateChange = typeof opts.onStateChange === "function" ? opts.onStateChange : null;

    const initialPrefs = readPrefs();
    const state = {
      loaded: false,
      contract: null,
      guideOpen: false,
      wiresVisible: initialPrefs.wiresVisible,
      selectedModuleId: initialPrefs.selectedModuleId,
      stepIndex: 0,
      inspectedWireId: null,
    };

    const dom = {
      btnGuide: null,
      btnToggleWires: null,
      selModule: null,
      panel: null,
      inspectBox: null,
    };

    function getFilteredWires() {
      if (!state.contract || !Array.isArray(state.contract.wires)) return [];
      if (!state.selectedModuleId || state.selectedModuleId === "all") {
        return state.contract.wires;
      }
      return state.contract.wires.filter((w) => w.module_id === state.selectedModuleId);
    }

    function getWireById(wireId) {
      if (!state.contract || !Array.isArray(state.contract.wires)) return null;
      return state.contract.wires.find((w) => w.wire_id === wireId) || null;
    }

    function getActiveWire() {
      const list = getFilteredWires();
      if (!list.length) return null;
      const clamped = Math.max(0, Math.min(state.stepIndex, list.length - 1));
      state.stepIndex = clamped;
      return list[clamped];
    }

    function getVisibleWireIdSet() {
      const list = getFilteredWires();
      return new Set(list.map((w) => w.wire_id));
    }

    function renderToolbar() {
      if (!toolbarMount) return;
      const totalWires = state.contract ? state.contract.wires.length : 0;
      const modules = state.contract ? state.contract.modules : [];
      const moduleOptions = [
        `<option value="all">Tất cả mô-đun (${totalWires} dây)</option>`,
        ...modules.map(
          (m) =>
            `<option value="${escHtml(m.module_id)}">${escHtml(m.label_vi)} (${m.wire_count} dây)</option>`
        ),
      ].join("");

      toolbarMount.innerHTML = `
        <div class="wg-toolbar" data-wg-instance="${escHtml(instanceId)}">
          <div class="wg-toolbar-group">
            <button type="button" class="wg-btn wg-btn-guide" data-wg-action="toggle-guide" aria-expanded="false">
              <span class="wg-btn-icon" aria-hidden="true"><svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor" aria-hidden="true"><path d="M9.5 1 3 9h4.5L6.5 15 13 7H8.5L9.5 1z"/></svg></span>
              <span>Hướng dẫn nối dây</span>
            </button>
            <button type="button" class="wg-btn wg-btn-wires" data-wg-action="toggle-wires" aria-pressed="true">
              <span data-wg-role="wires-label">Ẩn dây nối</span>
            </button>
            <label class="wg-filter-wrap">
              <span class="wg-filter-label">Mô-đun:</span>
              <select class="wg-module-select" data-wg-action="module-filter" aria-label="Lọc dây nối theo mô-đun">
                ${moduleOptions}
              </select>
            </label>
          </div>
          ${extraToolbarHtml ? `<div class="wg-toolbar-extra">${extraToolbarHtml}</div>` : ""}
        </div>
      `;

      dom.btnGuide = toolbarMount.querySelector('[data-wg-action="toggle-guide"]');
      dom.btnToggleWires = toolbarMount.querySelector('[data-wg-action="toggle-wires"]');
      dom.selModule = toolbarMount.querySelector('[data-wg-action="module-filter"]');

      if (dom.btnGuide) {
        dom.btnGuide.addEventListener("click", () => {
          setGuideOpen(!state.guideOpen);
        });
      }
      if (dom.btnToggleWires) {
        dom.btnToggleWires.addEventListener("click", () => {
          setWiresVisible(!state.wiresVisible);
        });
      }
      if (dom.selModule) {
        dom.selModule.addEventListener("change", () => {
          setModuleFilter(dom.selModule.value || "all");
        });
      }
    }

    function renderPanelSkeleton() {
      if (!panelMount) return;
      panelMount.innerHTML = `
        <aside class="wg-panel" data-wg-instance="${escHtml(instanceId)}" role="region" aria-label="Hướng dẫn nối dây" hidden>
          <div class="wg-panel-head">
            <div class="wg-panel-title-wrap">
              <h3 class="wg-panel-title">Hướng dẫn nối dây</h3>
              <span class="wg-step-counter" data-wg-role="step-counter">Bước 1/1</span>
            </div>
            <button type="button" class="wg-close-btn" data-wg-action="close-guide" aria-label="Đóng hướng dẫn nối dây">Đóng</button>
          </div>
          <div class="wg-panel-body" data-wg-role="panel-body"></div>
          <div class="wg-panel-foot">
            <button type="button" class="wg-btn wg-btn-nav" data-wg-action="prev-step">← Trước</button>
            <select class="wg-step-jump" data-wg-action="jump-step" aria-label="Chọn nhanh bước nối dây"></select>
            <button type="button" class="wg-btn wg-btn-primary wg-btn-nav" data-wg-action="next-step">Tiếp →</button>
          </div>
        </aside>
      `;
      dom.panel = panelMount.querySelector(".wg-panel");

      const btnClose = dom.panel.querySelector('[data-wg-action="close-guide"]');
      const btnPrev = dom.panel.querySelector('[data-wg-action="prev-step"]');
      const btnNext = dom.panel.querySelector('[data-wg-action="next-step"]');
      const selJump = dom.panel.querySelector('[data-wg-action="jump-step"]');

      if (btnClose) btnClose.addEventListener("click", () => setGuideOpen(false));
      if (btnPrev) btnPrev.addEventListener("click", () => stepBy(-1));
      if (btnNext) btnNext.addEventListener("click", () => stepBy(1));
      if (selJump) {
        selJump.addEventListener("change", () => {
          const idx = Number(selJump.value);
          if (Number.isFinite(idx)) {
            goToStep(idx);
          }
        });
      }
    }

    function renderInspectSkeleton() {
      if (!inspectMount) return;
      inspectMount.innerHTML = `<div class="wg-inspect-card" data-wg-instance="${escHtml(instanceId)}" role="status" aria-live="polite" hidden></div>`;
      dom.inspectBox = inspectMount.querySelector(".wg-inspect-card");
    }

    function syncToolbarUi() {
      if (dom.btnGuide) {
        dom.btnGuide.classList.toggle("is-active", state.guideOpen);
        dom.btnGuide.setAttribute("aria-expanded", state.guideOpen ? "true" : "false");
      }
      if (dom.btnToggleWires) {
        dom.btnToggleWires.classList.toggle("is-hidden-state", !state.wiresVisible);
        dom.btnToggleWires.setAttribute("aria-pressed", state.wiresVisible ? "true" : "false");
        const lbl = dom.btnToggleWires.querySelector('[data-wg-role="wires-label"]');
        if (lbl) {
          lbl.textContent = state.wiresVisible ? "Ẩn dây nối" : "Hiện dây nối";
        }
      }
      if (dom.selModule) {
        dom.selModule.value = state.selectedModuleId;
      }
    }

    function syncPanelUi() {
      if (!dom.panel) return;
      dom.panel.hidden = !state.guideOpen;
      if (panelMount && panelMount.classList) {
        panelMount.classList.toggle("wg-panel-open", state.guideOpen);
      }
      if (!state.guideOpen) return;

      const list = getFilteredWires();
      const counterEl = dom.panel.querySelector('[data-wg-role="step-counter"]');
      const bodyEl = dom.panel.querySelector('[data-wg-role="panel-body"]');
      const btnPrev = dom.panel.querySelector('[data-wg-action="prev-step"]');
      const btnNext = dom.panel.querySelector('[data-wg-action="next-step"]');
      const selJump = dom.panel.querySelector('[data-wg-action="jump-step"]');

      if (!list.length) {
        if (counterEl) counterEl.textContent = "Bước 0/0";
        if (bodyEl) bodyEl.innerHTML = `<p class="wg-empty">Không có dây nối cho mô-đun đã chọn.</p>`;
        if (btnPrev) btnPrev.disabled = true;
        if (btnNext) btnNext.disabled = true;
        if (selJump) selJump.innerHTML = "";
        return;
      }

      const wire = getActiveWire();
      const idx = state.stepIndex;
      const total = list.length;

      if (counterEl) {
        counterEl.textContent = `Bước ${idx + 1}/${total}`;
      }
      if (btnPrev) btnPrev.disabled = idx <= 0;
      if (btnNext) btnNext.disabled = idx >= total - 1;
      if (selJump) {
        selJump.innerHTML = list
          .map(
            (w, i) =>
              `<option value="${i}"${i === idx ? " selected" : ""}>${i + 1}. ${escHtml(w.wire_id)} · ${escHtml(
                w.module_pin
              )} → ${escHtml(w.hub_ref)}.${escHtml(w.hub_pin)}</option>`
          )
          .join("");
        selJump.value = String(idx);
      }

      if (bodyEl && wire) {
        const warnClass = isWarningNote(wire) ? " wg-note-warn" : "";
        const hiddenNotice = !state.wiresVisible
          ? `<div class="wg-hidden-hint">
               <span>Dây nối đang bị ẩn trên sơ đồ.</span>
               <button type="button" class="wg-mini-link" data-wg-action="show-wires-inline">Hiện dây nối</button>
             </div>`
          : "";
        const colorBorder = wire.color === "White" ? "border:1.5px solid #475569;" : "";
        const relatedProt =
          state.contract && Array.isArray(state.contract.protection_components) && wire.net && wire.net !== "GND"
            ? state.contract.protection_components.filter(
                (p) => p.net_pos === wire.net || p.net_neg === wire.net
              )
            : [];
        const protHtml = relatedProt.length
          ? `<div class="wg-prot-inline">
               <strong>Tụ / Diode bảo vệ liên quan:</strong>
               ${relatedProt
                 .map(
                   (p) =>
                     `<span class="wg-prot-pill">${escHtml(p.ref)} ${escHtml(p.value)} (${escHtml(
                       p.voltage_rating
                     )})</span>`
                 )
                 .join(" ")}
             </div>`
          : "";

        const lengthHtml =
          typeof wire.length_cm === "number" && Number.isFinite(wire.length_cm)
            ? `<div class="wg-length-row">
                 <span class="wg-length-pill">Chiều dài thực tế: <strong>${wire.length_cm.toFixed(2)} cm</strong></span>
                 ${
                   wire.recommended_std_cm
                     ? `<span class="wg-std-pill">Khuyến nghị mua dây chuẩn: <strong>${escHtml(
                         wire.recommended_std_cm
                       )} cm</strong></span>`
                     : ""
                 }
                 <span class="wg-pass-pill">${wire.within_30cm === false ? "Cần chú ý > 30 cm" : "Đạt ≤ 30 cm"}</span>
               </div>`
            : "";
        const routeVi = wire.route_channel ? (WG_ROUTE_VI_MAP[wire.route_channel] || wire.route_channel) : "";
        const routeHtml = routeVi
          ? `<div class="wg-route-line"><strong>Đường đi dây 3D:</strong> ${escHtml(routeVi)}</div>`
          : "";
        const pcbXyHtml =
          Array.isArray(wire.hub_pin_xy_mm) && wire.hub_pin_xy_mm.length >= 2
            ? `<span>Tọa độ PCB: <code>X=${Number(wire.hub_pin_xy_mm[0]).toFixed(2)} mm, Y=${Number(
                wire.hub_pin_xy_mm[1]
              ).toFixed(2)} mm</code></span>`
            : "";
        let extraMechHtml = "";
        if (wire.module_id === "sg90_servo" && state.contract && state.contract.door_torque_margin) {
          const tm = state.contract.door_torque_margin;
          extraMechHtml = `<div class="wg-note-box"><strong>Cơ cấu truyền động đồng tâm SG90:</strong> Lắp đảo trục trên kệ <code>P07</code> + đai gài <code>SUP11</code> + khớp ngàm tay đòn <code>SUP10B</code> (0 vít/keo, cữ chặn −2°/+92°, dự phòng mô-men <strong>${escHtml(
            tm.worst_case_safety_margin_x
          )}×</strong>).</div>`;
        } else if (wire.module_id === "psu_5v") {
          extraMechHtml = `<div class="wg-note-box"><strong>Phân phối nguồn từ J1:</strong> Giắc DC-022 (5V 2A) → <code>J1</code> cấp rail <code>+5V</code> cho NodeMCU <code>VIN</code>, Servo <code>J3</code>, Còi <code>J6</code> và 2 ngõ ra đóng cắt qua rơ-le: <code>J8→J2</code> (Bơm 5V) và <code>J10→J11</code> (Loa PAM8403).</div>`;
        }

        bodyEl.innerHTML = `
          ${hiddenNotice}
          <div class="wg-meta-row">
            <span class="wg-wire-badge">${escHtml(wire.wire_id)}</span>
            <span class="wg-color-chip">
              <span class="wg-color-dot" style="background:${escHtml(wire.color_hex)};${colorBorder}"></span>
              <span>Dây màu <strong>${escHtml(wire.color_vi)}</strong></span>
            </span>
            <span class="wg-type-chip">${escHtml(wire.wire_type_vi)}</span>
          </div>

          ${lengthHtml}

          <div class="wg-endpoint-flow">
            <div class="wg-endpoint-box">
              <span class="wg-endpoint-tag">Đầu PCB Hub / ESP8266</span>
              <strong class="wg-endpoint-name">${escHtml(wire.hub_label)}</strong>
              <code class="wg-pin-code">${escHtml(wire.nodemcu_pin)} · ${escHtml(wire.gpio)}</code>
            </div>
            <div class="wg-endpoint-arrow" aria-hidden="true">→</div>
            <div class="wg-endpoint-box">
              <span class="wg-endpoint-tag">Mô-đun &amp; Chân đích</span>
              <strong class="wg-endpoint-name">${escHtml(wire.module_label_vi)}</strong>
              <code class="wg-pin-code">${escHtml(wire.module_pin)}</code>
            </div>
          </div>

          <p class="wg-instruction">${escHtml(wire.instruction_vi)}</p>
          ${routeHtml}

          <div class="wg-note-box${warnClass}">
            <strong>Lưu ý nguồn / GND &amp; tín hiệu:</strong> ${escHtml(wire.power_gnd_note_vi)}
          </div>
          ${extraMechHtml}
          ${protHtml}
          <div class="wg-tech-meta">
            <span>Mạng PCB: <code>${escHtml(wire.net)}</code></span>
            ${pcbXyHtml}
            <span>Firmware: <code>${escHtml(wire.fw_ref)}</code></span>
          </div>
        `;

        const showInlineBtn = bodyEl.querySelector('[data-wg-action="show-wires-inline"]');
        if (showInlineBtn) {
          showInlineBtn.addEventListener("click", () => setWiresVisible(true));
        }
      }
    }

    const WG_ROUTE_VI_MAP = {
      "Tech Bay front channel (PAM8403 -> P15 Speaker)": "Rãnh trước khoang kỹ thuật (PAM8403 → Loa trên mặt nạ P15)",
      "Garden rim channel (LM393 -> YL-69 Probe)": "Mép trên vách vườn (LM393 → Đầu dò đất YL-69)",
      "Tech Bay left power channel (J1 -> DC-022)": "Rãnh nguồn trái khoang kỹ thuật (Cầu vít J1 → Giắc DC-022)",
      "Tech Bay -> P05 front cable slot -> P07 SG90 shelf": "Khoang kỹ thuật → Lỗ dây mặt tiền P05 → Kệ Servo SG90 (P07)",
      "Tech Bay -> P05 Cable_Servo_D1 (X=48, Z=110) -> Coaxial top-jamb SG90": "Khoang kỹ thuật → Lỗ dây Cable_Servo_D1 trên P05 (X=48, Z=110 mm) → Servo SG90 đồng tâm đỉnh bản lề",
      "P05 open front cutaway (Z=56 above KY037 ledge) -> P06_WALL_MID Living Room chase": "Khoảng mở mặt tiền P05 (Z=56 mm trên bệ KY-037) → Vách giữa P06 phía phòng khách",
      "P05 Cable_Front_BR (X=224) -> P06_WALL_MID Bedroom vertical chase": "Lỗ dây P05 (X=224 mm) → Rãnh dọc vách giữa P06 phía phòng ngủ",
      "Tech Bay -> P05 center pillar vertical chase -> Buzzer": "Khoang kỹ thuật → Trụ giữa mặt tiền P05 → Còi báo động 5V",
      "Tech Bay -> P05 front wall KY-037 cradle": "Khoang kỹ thuật → Giá đỡ cảm biến KY-037 trên vách trước P05",
      "Tech Bay direct inter-board harness": "Bó dây trực tiếp trong khoang kỹ thuật (PCB Hub ↔ Rơ-le 1/2)",
      "Tech Bay front audio/power tray (J11/J12 -> PAM8403)": "Khay dây âm thanh & nguồn phía trước (J11/J12 → PAM8403)",
      "Tech Bay center channel -> P09 water tank wire notch (Y=99) -> Pump": "Rãnh giữa khoang kỹ thuật → Khe dây bể nước P09 (Y=99 mm) → Bơm tưới cây",
      "Tech Bay rear dry tray -> P13 dry rear LM393 cradle": "Rãnh khô phía sau khoang kỹ thuật → Giá đỡ khô LM393 sau vách P13",
      "Direct routed path": "Đường dây đi thẳng trong khoang kỹ thuật",
    };

    function syncInspectUi() {
      if (!dom.inspectBox) return;
      if (!state.inspectedWireId) {
        dom.inspectBox.hidden = true;
        dom.inspectBox.innerHTML = "";
        return;
      }
      const wire = getWireById(state.inspectedWireId);
      if (!wire) {
        dom.inspectBox.hidden = true;
        return;
      }
      const colorBorder = wire.color === "White" ? "border:1.5px solid #475569;" : "";
      const lenBadge =
        typeof wire.length_cm === "number" && Number.isFinite(wire.length_cm)
          ? `<span class="wg-length-pill"><strong>${wire.length_cm.toFixed(2)} cm</strong>${
              wire.recommended_std_cm ? ` · Chuẩn ${escHtml(wire.recommended_std_cm)} cm` : ""
            }</span>`
          : "";
      dom.inspectBox.hidden = false;
      dom.inspectBox.innerHTML = `
        <div class="wg-inspect-head">
          <span class="wg-wire-badge">${escHtml(wire.wire_id)}</span>
          <span class="wg-color-chip">
            <span class="wg-color-dot" style="background:${escHtml(wire.color_hex)};${colorBorder}"></span>
            <span>${escHtml(wire.color_vi)}</span>
          </span>
          ${lenBadge}
          <strong class="wg-inspect-title">${escHtml(wire.hub_label)} → ${escHtml(wire.module_label_vi)} (${escHtml(wire.module_pin)})</strong>
          <div class="wg-inspect-actions">
            <button type="button" class="wg-mini-link" data-wg-action="open-inspected-step">Xem từng bước</button>
            <button type="button" class="wg-close-mini" data-wg-action="close-inspect" aria-label="Đóng thông tin dây">×</button>
          </div>
        </div>
        <div class="wg-inspect-sub">
          <span>ESP8266: <code>${escHtml(wire.nodemcu_pin)}</code> (${escHtml(wire.gpio)}) · Mạng: <code>${escHtml(wire.net)}</code>${
            wire.route_channel ? ` · Đường dây: ${escHtml(WG_ROUTE_VI_MAP[wire.route_channel] || wire.route_channel)}` : ""
          }</span>
          <span>${escHtml(wire.power_gnd_note_vi)}</span>
        </div>
      `;

      const openBtn = dom.inspectBox.querySelector('[data-wg-action="open-inspected-step"]');
      const closeBtn = dom.inspectBox.querySelector('[data-wg-action="close-inspect"]');
      if (openBtn) {
        openBtn.addEventListener("click", () => jumpToWireId(wire.wire_id, true));
      }
      if (closeBtn) {
        closeBtn.addEventListener("click", () => {
          state.inspectedWireId = null;
          syncInspectUi();
          syncAdapter();
        });
      }
    }

    function syncAdapter() {
      const visibleSet = getVisibleWireIdSet();
      const activeWire = state.guideOpen ? getActiveWire() : state.inspectedWireId ? getWireById(state.inspectedWireId) : null;
      if (typeof adapter.setWiresVisible === "function") {
        adapter.setWiresVisible(state.wiresVisible);
      }
      if (typeof adapter.applyModuleFilter === "function") {
        adapter.applyModuleFilter(state.selectedModuleId, visibleSet);
      }
      if (typeof adapter.highlightStep === "function") {
        adapter.highlightStep(activeWire, visibleSet, {
          guideOpen: state.guideOpen,
          wiresVisible: state.wiresVisible,
          selectedModuleId: state.selectedModuleId,
        });
      }
      if (onStateChange) {
        onStateChange(getSnapshot());
      }
    }

    function setGuideOpen(open) {
      state.guideOpen = Boolean(open);
      if (state.guideOpen) {
        state.inspectedWireId = null;
      }
      syncToolbarUi();
      syncPanelUi();
      syncInspectUi();
      syncAdapter();
    }

    function setWiresVisible(visible) {
      state.wiresVisible = Boolean(visible);
      writePrefs(state);
      syncToolbarUi();
      syncPanelUi();
      syncAdapter();
    }

    function setModuleFilter(moduleId) {
      const validIds = new Set(["all", ...((state.contract && state.contract.modules) || []).map((m) => m.module_id)]);
      state.selectedModuleId = validIds.has(moduleId) ? moduleId : "all";
      state.stepIndex = 0;
      writePrefs(state);
      syncToolbarUi();
      syncPanelUi();
      syncAdapter();
    }

    function goToStep(index) {
      const list = getFilteredWires();
      if (!list.length) return;
      state.stepIndex = Math.max(0, Math.min(Number(index) || 0, list.length - 1));
      syncPanelUi();
      syncAdapter();
    }

    function stepBy(delta) {
      goToStep(state.stepIndex + delta);
    }

    function jumpToWireId(wireId, openPanel = true) {
      const wire = getWireById(wireId);
      if (!wire) return;
      let list = getFilteredWires();
      let idx = list.findIndex((w) => w.wire_id === wireId);
      if (idx === -1) {
        state.selectedModuleId = "all";
        writePrefs(state);
        list = getFilteredWires();
        idx = list.findIndex((w) => w.wire_id === wireId);
      }
      if (idx >= 0) {
        state.stepIndex = idx;
      }
      if (openPanel) {
        state.guideOpen = true;
        state.inspectedWireId = null;
      } else {
        state.inspectedWireId = wireId;
      }
      syncToolbarUi();
      syncPanelUi();
      syncInspectUi();
      syncAdapter();
    }

    function inspectWire(wireId) {
      if (!wireId) return;
      const wire = getWireById(wireId);
      if (!wire) return;
      if (state.guideOpen) {
        jumpToWireId(wireId, true);
        return;
      }
      state.inspectedWireId = wireId;
      syncInspectUi();
      syncAdapter();
    }

    function getSnapshot() {
      const list = getFilteredWires();
      return {
        instanceId,
        loaded: state.loaded,
        guideOpen: state.guideOpen,
        wiresVisible: state.wiresVisible,
        selectedModuleId: state.selectedModuleId,
        stepIndex: state.stepIndex,
        totalSteps: list.length,
        activeWire: state.guideOpen ? getActiveWire() : null,
        inspectedWireId: state.inspectedWireId,
        contract: state.contract,
      };
    }

    function handleKeydown(ev) {
      if (!state.guideOpen) return;
      const tag = ev.target && ev.target.tagName ? ev.target.tagName.toUpperCase() : "";
      if (tag === "INPUT" || tag === "TEXTAREA" || (ev.target && ev.target.isContentEditable)) {
        return;
      }
      if (ev.key === "ArrowRight") {
        ev.preventDefault();
        stepBy(1);
      } else if (ev.key === "ArrowLeft") {
        ev.preventDefault();
        stepBy(-1);
      } else if (ev.key === "Escape") {
        ev.preventDefault();
        setGuideOpen(false);
      }
    }

    document.addEventListener("keydown", handleKeydown);

    const ready = loadContract().then((contract) => {
      state.contract = contract;
      state.loaded = true;
      const validIds = new Set(["all", ...contract.modules.map((m) => m.module_id)]);
      if (!validIds.has(state.selectedModuleId)) {
        state.selectedModuleId = "all";
        writePrefs(state);
      }
      renderToolbar();
      renderPanelSkeleton();
      renderInspectSkeleton();
      if (typeof adapter.onContractReady === "function") {
        adapter.onContractReady(contract, controller);
      }
      if (typeof adapter.bindInteractions === "function") {
        adapter.bindInteractions((wireId) => inspectWire(wireId));
      }
      syncToolbarUi();
      syncPanelUi();
      syncInspectUi();
      syncAdapter();
      return controller;
    });

    function clearInspect() {
      state.inspectedWireId = null;
      syncInspectUi();
      syncAdapter();
    }

    const controller = {
      ready,
      getSnapshot,
      setGuideOpen,
      setWiresVisible,
      setModuleFilter,
      goToStep,
      stepBy,
      jumpToWireId,
      inspectWire,
      clearInspect,
      refresh: syncAdapter,
      getContract: () => state.contract,
    };

    return controller;
  }

  function renderProtectionTable(mountEl, contract) {
    const host = typeof mountEl === "string" ? document.getElementById(mountEl) : mountEl;
    if (!host || !contract || !Array.isArray(contract.protection_components)) return;
    const rows = contract.protection_components
      .map((item) => {
        const badgeCls = item.kind === "flyback_diode" ? "wg-prot-kind-diode" : "wg-prot-kind-cap";
        const locCls = item.pcb_status === "onboard_pcb" ? "wg-prot-loc-pcb" : "wg-prot-loc-off";
        const isC8C9 = item.ref === "C8" || item.ref === "C9";
        const rowCls = isC8C9 ? ' class="wg-prot-row-highlight"' : "";
        const newTag = isC8C9 ? '<span class="wg-prot-v3-pill">Hàn trên PCB v3</span>' : "";
        return `<tr${rowCls}>
          <td><span class="wg-prot-ref ${badgeCls}">${escHtml(item.ref)}</span></td>
          <td><strong>${escHtml(item.value)}</strong><div class="wg-prot-sub">${escHtml(item.voltage_rating)}</div></td>
          <td>${escHtml(item.polarity)}</td>
          <td>
            <div>${escHtml(item.placement_pins)}</div>
            <div class="wg-prot-meta-line">
              <code>${escHtml(item.net_pos)} ↔ ${escHtml(item.net_neg)}</code>
              <span class="wg-prot-loc ${locCls}">${escHtml(item.pcb_status_vi || "Hàn trực tiếp trên PCB Hub")}</span>
              ${newTag}
            </div>
          </td>
          <td>
            <div>${escHtml(item.role_vi)}</div>
            <div class="wg-prot-ds">${escHtml(item.datasheet_ref)}</div>
          </td>
        </tr>`;
      })
      .join("");

    host.innerHTML = `
      <div class="wg-prot-banner">
        <strong>100% hàn trực tiếp trên PCB Hub DIY v3 (100×80 mm, 51 footprints, 0 ERC/DRC):</strong>
        Toàn bộ <strong>9 tụ điện (C1–C9, nhấn mạnh C8 100 nF &amp; C9 100 µF 16V đã tích hợp trực tiếp trên bo)</strong> và <strong>2 diode dập xung 1N4007 (D1–D2)</strong> đều nằm gọn trên mạch PCB — <strong>không dùng breadboard trắng</strong>.
      </div>
      <div class="wg-table-scroll">
        <table class="wg-protection-table" aria-label="Bảng tụ điện C1–C9 và diode bảo vệ D1–D2 trên PCB Hub DIY v3">
          <thead>
            <tr>
              <th>Ký hiệu</th>
              <th>Giá trị</th>
              <th>Phân cực</th>
              <th>Vị trí trên PCB &amp; Mạng nối</th>
              <th>Vai trò &amp; Datasheet</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }

  function createDiagramViewport(options) {
    const opts = options || {};
    const viewportEl =
      typeof opts.viewportEl === "string" ? document.getElementById(opts.viewportEl) : opts.viewportEl;
    const contentEl =
      typeof opts.contentEl === "string" ? document.getElementById(opts.contentEl) : opts.contentEl;
    const baseWidth = Number(opts.baseWidth) || 1220;
    const baseHeight = Number(opts.baseHeight) || 710;
    const minZoom = Number(opts.minZoom) || 0.4;
    const maxZoom = Number(opts.maxZoom) || 3.5;
    const zoomStep = Number(opts.zoomStep) || 0.2;
    const onChange = typeof opts.onChange === "function" ? opts.onChange : null;

    if (!viewportEl || !contentEl) {
      return {
        fit: () => 1,
        reset: () => 1,
        zoomIn: () => 1,
        zoomOut: () => 1,
        setScale: () => 1,
        handleResize: () => 1,
        getState: () => ({ scale: 1, tx: 0, ty: 0, fitScale: 1, mode: "fit", minZoom, maxZoom }),
      };
    }

    const vp = {
      scale: 1,
      tx: 0,
      ty: 0,
      fitScale: 1,
      mode: "fit",
    };

    const DRAG_THRESHOLD = 5;
    const activePointers = new Map();
    let dragPointerId = null;
    let dragStartX = 0;
    let dragStartY = 0;
    let dragLastX = 0;
    let dragLastY = 0;
    let isDragging = false;
    let suppressNextClick = false;
    let pinchLastDist = 0;
    let pinchLastMidX = 0;
    let pinchLastMidY = 0;
    let touchPinchActive = false;
    let touchLastDist = 0;
    let touchLastMidX = 0;
    let touchLastMidY = 0;

    function getViewportSize() {
      const rect = viewportEl.getBoundingClientRect();
      const w = viewportEl.clientWidth || rect.width || 0;
      const h = viewportEl.clientHeight || rect.height || 0;
      return { w, h, rect };
    }

    function isInteractiveTarget(target) {
      if (!target || typeof target.closest !== "function") return false;
      return Boolean(target.closest("button, a, input, select, textarea, wokwi-potentiometer"));
    }

    function clampPan(tx, ty, scale) {
      const { w, h } = getViewportSize();
      if (w < 20 || h < 20) return { tx, ty };
      const scaledW = baseWidth * scale;
      const scaledH = baseHeight * scale;
      const marginX = Math.min(80, w * 0.25);
      const marginY = Math.min(80, h * 0.25);

      let nextX = tx;
      let nextY = ty;
      if (scaledW <= w) {
        nextX = Math.max(-marginX, Math.min(w - scaledW + marginX, tx));
      } else {
        nextX = Math.max(w - scaledW - marginX, Math.min(marginX, tx));
      }
      if (scaledH <= h) {
        nextY = Math.max(-marginY, Math.min(h - scaledH + marginY, ty));
      } else {
        nextY = Math.max(h - scaledH - marginY, Math.min(marginY, ty));
      }
      return { tx: nextX, ty: nextY };
    }

    function applyTransform() {
      contentEl.style.transformOrigin = "0 0";
      contentEl.style.transform = `translate3d(${vp.tx.toFixed(2)}px, ${vp.ty.toFixed(2)}px, 0) scale(${vp.scale.toFixed(4)})`;
      viewportEl.setAttribute("data-wg-scale", vp.scale.toFixed(4));
      viewportEl.setAttribute("data-wg-pan-x", vp.tx.toFixed(1));
      viewportEl.setAttribute("data-wg-pan-y", vp.ty.toFixed(1));
      viewportEl.setAttribute("data-wg-zoom-mode", vp.mode);

      const { w, h } = getViewportSize();
      const canPan =
        vp.scale > vp.fitScale + 0.01 ||
        baseWidth * vp.scale > w + 2 ||
        baseHeight * vp.scale > h + 2;
      viewportEl.classList.toggle("wg-can-pan", canPan);

      if (onChange) {
        onChange(getState());
      }
    }

    function getState() {
      return {
        scale: vp.scale,
        tx: vp.tx,
        ty: vp.ty,
        fitScale: vp.fitScale,
        mode: vp.mode,
        minZoom,
        maxZoom,
      };
    }

    function computeFitScale() {
      const { w, h } = getViewportSize();
      if (w < 20 || h < 20) return vp.fitScale || 1;
      const sx = w / baseWidth;
      const sy = h / baseHeight;
      return Math.max(0.18, Math.min(1.0, sx, sy));
    }

    function fit() {
      const { w, h } = getViewportSize();
      if (w < 20 || h < 20) return vp.scale;
      const fs = computeFitScale();
      vp.fitScale = fs;
      vp.scale = fs;
      vp.mode = "fit";
      vp.tx = (w - baseWidth * fs) / 2;
      vp.ty = (h - baseHeight * fs) / 2;
      applyTransform();
      return vp.scale;
    }

    function reset() {
      vp.fitScale = computeFitScale();
      vp.mode = "manual";
      vp.scale = 1.0;
      vp.tx = 0;
      vp.ty = 0;
      applyTransform();
      return vp.scale;
    }

    function setScale(nextScale, anchorX, anchorY, allowBelowMin) {
      const { w, h } = getViewportSize();
      const effMin = allowBelowMin ? Math.min(minZoom, vp.fitScale) : minZoom;
      const clamped = Math.max(effMin, Math.min(maxZoom, nextScale));
      const ax = Number.isFinite(anchorX) ? anchorX : w / 2;
      const ay = Number.isFinite(anchorY) ? anchorY : h / 2;
      const worldX = (ax - vp.tx) / vp.scale;
      const worldY = (ay - vp.ty) / vp.scale;

      vp.mode = "manual";
      vp.scale = clamped;
      const rawTx = ax - worldX * clamped;
      const rawTy = ay - worldY * clamped;
      const c = clampPan(rawTx, rawTy, clamped);
      vp.tx = c.tx;
      vp.ty = c.ty;
      applyTransform();
      return vp.scale;
    }

    function zoomIn() {
      const next = Math.min(maxZoom, Math.max(minZoom, Math.round((vp.scale + zoomStep) * 100) / 100));
      return setScale(next, undefined, undefined, false);
    }

    function zoomOut() {
      const next = Math.max(minZoom, Math.round((vp.scale - zoomStep) * 100) / 100);
      return setScale(next, undefined, undefined, false);
    }

    function handleResize() {
      const { w, h } = getViewportSize();
      if (w < 20 || h < 20) return vp.scale;
      vp.fitScale = computeFitScale();
      if (vp.mode === "fit") {
        return fit();
      }
      const c = clampPan(vp.tx, vp.ty, vp.scale);
      vp.tx = c.tx;
      vp.ty = c.ty;
      applyTransform();
      return vp.scale;
    }

    // Mouse wheel zoom anchored around cursor position
    viewportEl.addEventListener(
      "wheel",
      (ev) => {
        ev.preventDefault();
        const { rect } = getViewportSize();
        const cx = ev.clientX - rect.left;
        const cy = ev.clientY - rect.top;
        const factor = ev.deltaY < 0 ? 1.15 : 1 / 1.15;
        setScale(vp.scale * factor, cx, cy, false);
      },
      { passive: false }
    );

    // Suppress accidental click right after a drag pan
    viewportEl.addEventListener(
      "click",
      (ev) => {
        if (suppressNextClick) {
          suppressNextClick = false;
          ev.preventDefault();
          ev.stopPropagation();
        }
      },
      true
    );

    // Pointer drag-pan & two-finger pinch-to-zoom
    viewportEl.addEventListener("pointerdown", (ev) => {
      if (ev.pointerType === "mouse" && ev.button !== 0) return;
      if (isInteractiveTarget(ev.target)) return;
      activePointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });

      if (activePointers.size === 1) {
        dragPointerId = ev.pointerId;
        dragStartX = ev.clientX;
        dragStartY = ev.clientY;
        dragLastX = ev.clientX;
        dragLastY = ev.clientY;
        isDragging = false;
      } else if (activePointers.size === 2) {
        dragPointerId = null;
        isDragging = false;
        viewportEl.classList.remove("wg-is-panning");
        const pts = Array.from(activePointers.values());
        pinchLastDist = Math.hypot(pts[1].x - pts[0].x, pts[1].y - pts[0].y) || 1;
        pinchLastMidX = (pts[0].x + pts[1].x) / 2;
        pinchLastMidY = (pts[0].y + pts[1].y) / 2;
      }
    });

    viewportEl.addEventListener("pointermove", (ev) => {
      if (!activePointers.has(ev.pointerId)) return;
      activePointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });

      if (activePointers.size === 2) {
        ev.preventDefault();
        const pts = Array.from(activePointers.values());
        const dist = Math.hypot(pts[1].x - pts[0].x, pts[1].y - pts[0].y) || 1;
        const midX = (pts[0].x + pts[1].x) / 2;
        const midY = (pts[0].y + pts[1].y) / 2;
        const { rect } = getViewportSize();
        const localMidX = midX - rect.left;
        const localMidY = midY - rect.top;

        vp.tx += midX - pinchLastMidX;
        vp.ty += midY - pinchLastMidY;
        const ratio = dist / (pinchLastDist || dist);
        pinchLastDist = dist;
        pinchLastMidX = midX;
        pinchLastMidY = midY;
        suppressNextClick = true;
        setScale(vp.scale * ratio, localMidX, localMidY, true);
        return;
      }

      if (activePointers.size === 1 && dragPointerId === ev.pointerId) {
        const totalDist = Math.hypot(ev.clientX - dragStartX, ev.clientY - dragStartY);
        if (!isDragging && totalDist >= DRAG_THRESHOLD) {
          isDragging = true;
          viewportEl.classList.add("wg-is-panning");
          try {
            if (typeof viewportEl.setPointerCapture === "function") {
              viewportEl.setPointerCapture(ev.pointerId);
            }
          } catch (_) {}
        }
        if (isDragging) {
          ev.preventDefault();
          const dx = ev.clientX - dragLastX;
          const dy = ev.clientY - dragLastY;
          dragLastX = ev.clientX;
          dragLastY = ev.clientY;
          vp.mode = "manual";
          const c = clampPan(vp.tx + dx, vp.ty + dy, vp.scale);
          vp.tx = c.tx;
          vp.ty = c.ty;
          applyTransform();
        }
      }
    });

    function endPointer(ev) {
      if (activePointers.has(ev.pointerId)) {
        activePointers.delete(ev.pointerId);
      }
      if (dragPointerId === ev.pointerId) {
        if (isDragging) {
          suppressNextClick = true;
          setTimeout(() => {
            suppressNextClick = false;
          }, 0);
        }
        dragPointerId = null;
        isDragging = false;
        viewportEl.classList.remove("wg-is-panning");
        try {
          if (typeof viewportEl.releasePointerCapture === "function" && viewportEl.hasPointerCapture(ev.pointerId)) {
            viewportEl.releasePointerCapture(ev.pointerId);
          }
        } catch (_) {}
      }
      if (activePointers.size === 1) {
        const [remainId, pt] = Array.from(activePointers.entries())[0];
        dragPointerId = remainId;
        dragStartX = pt.x;
        dragStartY = pt.y;
        dragLastX = pt.x;
        dragLastY = pt.y;
        isDragging = false;
      }
    }

    viewportEl.addEventListener("pointerup", endPointer);
    viewportEl.addEventListener("pointercancel", endPointer);

    // TouchEvent fallback for two-finger pinch when synthetic TouchEvents are dispatched
    viewportEl.addEventListener(
      "touchstart",
      (ev) => {
        if (ev.touches && ev.touches.length === 2 && activePointers.size < 2) {
          ev.preventDefault();
          touchPinchActive = true;
          const t0 = ev.touches[0];
          const t1 = ev.touches[1];
          touchLastDist = Math.hypot(t1.clientX - t0.clientX, t1.clientY - t0.clientY) || 1;
          touchLastMidX = (t0.clientX + t1.clientX) / 2;
          touchLastMidY = (t0.clientY + t1.clientY) / 2;
        }
      },
      { passive: false }
    );

    viewportEl.addEventListener(
      "touchmove",
      (ev) => {
        if (touchPinchActive && ev.touches && ev.touches.length === 2 && activePointers.size < 2) {
          ev.preventDefault();
          const t0 = ev.touches[0];
          const t1 = ev.touches[1];
          const dist = Math.hypot(t1.clientX - t0.clientX, t1.clientY - t0.clientY) || 1;
          const midX = (t0.clientX + t1.clientX) / 2;
          const midY = (t0.clientY + t1.clientY) / 2;
          const { rect } = getViewportSize();
          vp.tx += midX - touchLastMidX;
          vp.ty += midY - touchLastMidY;
          const ratio = dist / (touchLastDist || dist);
          touchLastDist = dist;
          touchLastMidX = midX;
          touchLastMidY = midY;
          setScale(vp.scale * ratio, midX - rect.left, midY - rect.top, true);
        }
      },
      { passive: false }
    );

    viewportEl.addEventListener("touchend", (ev) => {
      if (!ev.touches || ev.touches.length < 2) {
        touchPinchActive = false;
      }
    });

    return {
      fit,
      reset,
      zoomIn,
      zoomOut,
      setScale,
      handleResize,
      getState,
    };
  }

  window.SmartHomeWiringGuide = {
    STORAGE_KEY,
    CONTRACT_URL,
    loadContract,
    createController,
    createDiagramViewport,
    renderProtectionTable,
  };
})();
