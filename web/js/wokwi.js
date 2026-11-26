    if (typeof window !== 'undefined' && typeof window.fetch === 'function' && !window._shAuthFetchWrapped) {
      const _origWokwiFetch = window.fetch.bind(window);
      window.fetch = function(input, init) {
        const urlStr = typeof input === 'string' ? input : (input && input.url ? input.url : '');
        if (urlStr.startsWith('/api/')) {
          let tok = '';
          try {
            tok = (window.sessionStorage && window.sessionStorage.getItem('session_token')) ||
                  (window.localStorage && window.localStorage.getItem('session_token')) || '';
            if (!tok && window.localStorage) {
              const rawSess = window.localStorage.getItem('smarthome_auth_session');
              if (rawSess) {
                const parsed = JSON.parse(rawSess);
                tok = (parsed && parsed.session_token) || '';
              }
            }
          } catch (_) {}
          const nextInit = Object.assign({ credentials: 'same-origin' }, init || {});
          const hdrs = Object.assign({}, nextInit.headers || {});
          if (tok && !hdrs['X-Session-Token'] && !hdrs['x-session-token'] && !hdrs['Authorization']) {
            hdrs['X-Session-Token'] = tok;
          }
          nextInit.headers = hdrs;
          return _origWokwiFetch(input, nextInit);
        }
        return _origWokwiFetch(input, init);
      };
      window._shAuthFetchWrapped = true;
    }

    function isLocalWokwiHost() {
      if (typeof location === 'undefined') return true;
      const h = location.hostname || '';
      return h === 'localhost' || h === '127.0.0.1';
    }

    function showWokwiAuthError(msg) {
      const banner = document.getElementById('wokwiAuthBanner');
      const msgEl = document.getElementById('wokwiAuthBannerMsg');
      const cleanMsg = msg || 'Bạn chưa đăng nhập hoặc phiên đã hết hạn. Vui lòng đăng nhập để điều khiển thiết bị.';
      if (msgEl) msgEl.textContent = cleanMsg;
      if (banner) {
        banner.style.display = 'flex';
        banner.hidden = false;
      }
      logSerial(`[XÁC THỰC] ${cleanMsg} (Đăng nhập tại /login)`, 'warn');
    }

    function hideWokwiAuthError() {
      const banner = document.getElementById('wokwiAuthBanner');
      if (banner) {
        banner.style.display = 'none';
        banner.hidden = true;
      }
    }

    // =========================================================================
    // 1. VẼ BẢNG CẮM MẠCH BREADBOARD 400 LỖ THỰC TẾ (CHUẨN WOKWI.COM)
    // =========================================================================
    const BB_ORIGIN = { x: 295, y: 45 }; // Tọa độ góc trái trên của Breadboard trong .circuit-stage
    const HOLE_MAP = {}; // Lưu tọa độ tuyệt đối (x, y) của toàn bộ 400 lỗ cắm: tp1..tp25, tn1..tn25, a1..e30, f1..j30, bp1..bp25, bn1..bn25

    function buildBreadboard400() {
      const svg = document.getElementById('bbSvg');
      let html = `
        <!-- Thân nhựa trắng Breadboard 400 lỗ -->
        <rect x="0" y="0" width="490" height="310" rx="10" fill="#f8fafc" stroke="#cbd5e1" stroke-width="3"/>
        <rect x="6" y="6" width="478" height="298" rx="7" fill="#f1f5f9" stroke="#e2e8f0" stroke-width="1"/>

        <!-- Vạch Đỏ (+) và Xanh (-) ở Rãnh Nguồn Trên (3.3V & GND) -->
        <line x1="34" y1="16" x2="462" y2="16" stroke="#fb923c" stroke-width="2.2"/>
        <text x="16" y="21" font-size="12" fill="#ea580c" font-weight="bold">+3V3</text>
        <line x1="34" y1="45" x2="462" y2="45" stroke="#2563eb" stroke-width="2.2"/>
        <text x="16" y="49" font-size="12" fill="#1d4ed8" font-weight="bold">GND</text>

        <!-- Rãnh lõm giữa Breadboard (IC Channel) -->
        <rect x="12" y="146" width="466" height="18" rx="3" fill="#cbd5e1"/>
        <line x1="12" y1="155" x2="478" y2="155" stroke="#94a3b8" stroke-width="1" stroke-dasharray="6 4"/>

        <!-- Vạch Đỏ (+) và Xanh (-) ở Rãnh Nguồn Dưới (5V & GND) -->
        <line x1="34" y1="265" x2="462" y2="265" stroke="#ef4444" stroke-width="2.2"/>
        <text x="16" y="269" font-size="12" fill="#dc2626" font-weight="bold">+5V</text>
        <line x1="34" y1="294" x2="462" y2="294" stroke="#2563eb" stroke-width="2.2"/>
        <text x="16" y="298" font-size="12" fill="#1d4ed8" font-weight="bold">GND</text>
      `;

      // Hàm tạo 1 lỗ cắm vuông chuẩn 2.54mm
      function addHole(id, localX, localY, title) {
        HOLE_MAP[id] = { x: BB_ORIGIN.x + localX, y: BB_ORIGIN.y + localY };
        html += `<g style="cursor:pointer" onmouseenter="showHole('${id}', '${title}')">
          <rect x="${localX - 3.2}" y="${localY - 3.2}" width="6.4" height="6.4" rx="1" fill="#334155" stroke="#94a3b8" stroke-width="0.7"/>
          <rect x="${localX - 1.8}" y="${localY - 1.8}" width="3.6" height="3.6" fill="#0f172a"/>
        </g>`;
      }

      // 1. Rãnh nguồn trên (tp1..tp25, tn1..tn25) & Rãnh nguồn dưới (bp1..bp25, bn1..bn25)
      let pIdx = 1;
      for (let grp = 0; grp < 5; grp++) {
        for (let k = 0; k < 5; k++) {
          const colX = 46 + (grp * 6 + k) * 14.5;
          addHole(`tp${pIdx}`, colX, 25, `Rãnh Nguồn Dương Trên (+3.3V) - Lỗ ${pIdx}`);
          addHole(`tn${pIdx}`, colX, 37, `Rãnh Nguồn Âm Trên (GND) - Lỗ ${pIdx}`);
          addHole(`bp${pIdx}`, colX, 274, `Rãnh Nguồn Dương Dưới (+5V) - Lỗ ${pIdx}`);
          addHole(`bn${pIdx}`, colX, 286, `Rãnh Nguồn Âm Dưới (GND) - Lỗ ${pIdx}`);
          pIdx++;
        }
      }

      // 2. Các lỗ cắm chính: Cột 1..30, Hàng a,b,c,d,e (trên) và f,g,h,i,j (dưới)
      const rowsTop = ['a', 'b', 'c', 'd', 'e'];
      const rowsBot = ['f', 'g', 'h', 'i', 'j'];

      for (let r = 0; r < 5; r++) {
        const yT = 72 + r * 14;
        const yB = 180 + r * 14;
        html += `<text x="23" y="${yT + 4}" font-family="Consolas,monospace" font-size="10.5" font-weight="bold" fill="#475569">${rowsTop[r]}</text>`;
        html += `<text x="472" y="${yT + 4}" font-family="Consolas,monospace" font-size="10.5" font-weight="bold" fill="#475569">${rowsTop[r]}</text>`;
        html += `<text x="23" y="${yB + 4}" font-family="Consolas,monospace" font-size="10.5" font-weight="bold" fill="#475569">${rowsBot[r]}</text>`;
        html += `<text x="472" y="${yB + 4}" font-family="Consolas,monospace" font-size="10.5" font-weight="bold" fill="#475569">${rowsBot[r]}</text>`;
      }

      for (let col = 1; col <= 30; col++) {
        const x = 38 + (col - 1) * 14.5;
        if (col === 1 || col % 5 === 0) {
          html += `<text x="${x}" y="61" font-family="Consolas,monospace" font-size="9.5" text-anchor="middle" font-weight="bold" fill="#64748b">${col}</text>`;
          html += `<text x="${x}" y="252" font-family="Consolas,monospace" font-size="9.5" text-anchor="middle" font-weight="bold" fill="#64748b">${col}</text>`;
        }
        for (let r = 0; r < 5; r++) {
          const rTop = rowsTop[r];
          const rBot = rowsBot[r];
          addHole(`${rTop}${col}`, x, 72 + r * 14, `Cột ${col}, Hàng ${rTop}`);
          addHole(`${rBot}${col}`, x, 180 + r * 14, `Cột ${col}, Hàng ${rBot}`);
        }
      }

      svg.innerHTML = html;
    }

    let liveTelemetryString = 'Nhiệt độ: 28.5°C · Độ ẩm: 65% · Độ ẩm đất: 62%';
    let isHoleHovered = false;

    function updateLiveTelemetryHeader(temp, hum, soil) {
      const t = temp !== undefined ? Number(temp).toFixed(1) : '28.5';
      const h = hum !== undefined ? Number(hum).toFixed(0) : '65';
      const s = soil !== undefined ? Number(soil).toFixed(0) : '62';
      liveTelemetryString = `Nhiệt độ: ${t}°C · Độ ẩm: ${h}% · Độ ẩm đất: ${s}%`;
      const el = document.getElementById('hoverHoleInfo');
      if (el && !isHoleHovered) {
        el.textContent = liveTelemetryString;
      }
    }

    function showHole(id, desc) {
      isHoleHovered = true;
      const el = document.getElementById('hoverHoleInfo');
      if (el) el.textContent = `Đang trỏ vào: [${id.toUpperCase()}] — ${desc}`;
    }

    function clearHoleHover() {
      isHoleHovered = false;
      const el = document.getElementById('hoverHoleInfo');
      if (el) el.textContent = liveTelemetryString;
    }

    // =========================================================================
    // 1.5. VẼ 30 CHÂN MẠ VÀNG CỦA MẠCH NODEMCU ESP8266 (15 TRÁI + 15 PHẢI ĐÚNG THỨ TỰ THỰC TẾ)
    // =========================================================================
    const NODEMCU_ORIGIN = { x: 28, y: 42 };
    const NODEMCU_PIN_MAP = {};

    function buildNodeMCUPins() {
      const g = document.getElementById('nodemcuPinsGroup');
      if (!g) return;

      // Thứ tự 15 chân bên TRÁI từ trên xuống dưới (nhìn mặt trên NodeMCU cổng USB hướng lên):
      const leftPins = [
        { key: 'A0',    label: 'A0',  active: '#facc15', desc: 'Chân số 1 Trái: A0 (ADC0) — Cảm biến Độ ẩm Đất (LM393 nguồn 3.3V)' },
        { key: 'RSV1',  label: 'RSV', active: null,      desc: 'Chân số 2 Trái: RSV (Không dùng)' },
        { key: 'RSV2',  label: 'RSV', active: null,      desc: 'Chân số 3 Trái: RSV (Không dùng)' },
        { key: 'SD3',   label: 'SD3', active: null,      desc: 'Chân số 4 Trái: SD3' },
        { key: 'SD2',   label: 'SD2', active: null,      desc: 'Chân số 5 Trái: SD2' },
        { key: 'SD1',   label: 'SD1', active: null,      desc: 'Chân số 6 Trái: SD1' },
        { key: 'CMD',   label: 'CMD', active: null,      desc: 'Chân số 7 Trái: CMD' },
        { key: 'SD0',   label: 'SD0', active: null,      desc: 'Chân số 8 Trái: SD0' },
        { key: 'CLK',   label: 'CLK', active: null,      desc: 'Chân số 9 Trái: CLK' },
        { key: 'GND_L1',label: 'GND', active: null,      desc: 'Chân số 10 Trái: GND' },
        { key: 'V33_L', label: '3V3', active: null,      desc: 'Chân số 11 Trái: 3V3' },
        { key: 'EN',    label: 'EN',  active: null,      desc: 'Chân số 12 Trái: EN' },
        { key: 'RST',   label: 'RST', active: null,      desc: 'Chân số 13 Trái: RST' },
        { key: 'GND_L2',label: 'GND', active: '#94a3b8', desc: 'Chân số 14 Trái: GND (Mass)' },
        { key: 'VIN',   label: 'VIN', active: '#ef4444', desc: 'Chân số 15 Cuối Trái: VIN (+5V cấp xuống Rãnh Dưới Breadboard)' }
      ];

      // Thứ tự 15 chân bên PHẢI từ trên xuống dưới (D0 -> D8, RX, TX, GND, 3V3):
      const rightPins = [
        { key: 'D0',    label: 'D0',  active: '#22c55e', desc: 'Chân số 1 Phải: D0 (GPIO16) — Đèn phòng khách LED Đỏ & nháy enroll_blink' },
        { key: 'D1',    label: 'D1',  active: '#facc15', desc: 'Chân số 2 Phải: D1 (GPIO5) — Cửa chính Servo SG90 (0°/90°)' },
        { key: 'D2',    label: 'D2',  active: '#06b6d4', desc: 'Chân số 3 Phải: D2 (GPIO4) — Cảm biến Nhiệt độ & Độ ẩm DHT11 (kèm trở kéo lên R3 10kΩ)' },
        { key: 'D3',    label: 'D3',  active: '#a855f7', desc: 'Chân số 4 Phải: D3 (GPIO0) — Ngõ ra PWM tới PAM8403 qua R4 10kΩ kéo lên 3.3V, tụ C4 10µF 16V, cầu R5/R6 2.2kΩ và C5 10nF (nghỉ = INPUT)' },
        { key: 'D4',    label: 'D4',  active: '#fde047', desc: 'Chân số 5 Phải: D4 (GPIO2) — Đèn phòng ngủ Active-LOW từ 3.3V qua R2 220Ω + R7 10kΩ (an toàn boot)' },
        { key: 'V33',   label: '3V3', active: '#fb923c', desc: 'Chân số 6 Phải: 3V3 — Cấp nguồn +3.3V sang Rãnh Trên Breadboard' },
        { key: 'GND_R', label: 'GND', active: '#94a3b8', desc: 'Chân số 7 Phải: GND — Cấp Mass chung sang Breadboard' },
        { key: 'D5',    label: 'D5',  active: '#f87171', desc: 'Chân số 8 Phải: D5 (GPIO14) — Cảm biến Âm thanh KY-037 DO (vỗ tay/tiếng động)' },
        { key: 'D6',    label: 'D6',  active: '#38bdf8', desc: 'Chân số 9 Phải: D6 (GPIO12) — Relay 1 Xanh Máy bơm tưới cây + D1 1N4007 + C2 470µF' },
        { key: 'D7',    label: 'D7',  active: '#c084fc', desc: 'Chân số 10 Phải: D7 (GPIO13) — Relay 2 Đỏ Opto (Jumper H) Nguồn 5V PAM8403 (COM/NO → 5V)' },
        { key: 'D8',    label: 'D8',  active: '#f43f5e', desc: 'Chân số 11 Phải: D8 (GPIO15) — Còi 5V qua R9 10kΩ kéo xuống GND, R10 1kΩ → Q1 S8050 (NPN), Còi(+)→5V, Còi(-)→Q1.C, D2 1N4007 dập xung' },
        { key: 'RX',    label: 'RX',  active: null,      desc: 'Chân số 12 Phải: RX (GPIO3) — Serial Debug 115200 baud (Voice AI Gemini dùng mic/loa web)' },
        { key: 'TX',    label: 'TX',  active: null,      desc: 'Chân số 13 Phải: TX' },
        { key: 'GND_R2',label: 'GND', active: null,      desc: 'Chân số 14 Phải: GND' },
        { key: 'V33_R2',label: '3V3', active: null,      desc: 'Chân số 15 Phải: 3V3' }
      ];

      let html = '';
      for (let i = 0; i < 15; i++) {
        const y = 44 + i * 18.2;

        // Chân Trái (localX = 36)
        const pL = leftPins[i];
        NODEMCU_PIN_MAP[pL.key] = { x: NODEMCU_ORIGIN.x + 36, y: NODEMCU_ORIGIN.y + y };
        const fillL = pL.active || '#eab308';
        const txtFillL = pL.active || '#94a3b8';
        html += `<g style="cursor:pointer" data-nodemcu-pin="${pL.key}" onmouseenter="showHole('ESP8266:${pL.label}', '${pL.desc}')" onclick="onNodeMcuPinClick('${pL.key}')">
          <rect x="31" y="${y - 4}" width="10" height="8" rx="1.5" fill="#0f172a" stroke="#475569" stroke-width="0.8"/>
          <circle cx="36" cy="${y}" r="${pL.active ? 3.6 : 2.5}" fill="${fillL}"/>
          <text x="45" y="${y + 3.2}" font-family="Consolas,monospace" font-size="${pL.active ? 9.5 : 8}" font-weight="${pL.active ? '900' : '600'}" fill="${txtFillL}">${pL.label}</text>
          ${pL.active ? `<rect x="0" y="${y - 6.5}" width="26" height="13" rx="3" fill="#0f172a" stroke="${pL.active}" stroke-width="1"/><text x="13" y="${y + 3}" font-family="Consolas,monospace" font-size="8.5" text-anchor="middle" font-weight="bold" fill="${pL.active}">${pL.label}</text>` : ''}
        </g>`;

        // Chân Phải (localX = 174)
        const pR = rightPins[i];
        NODEMCU_PIN_MAP[pR.key] = { x: NODEMCU_ORIGIN.x + 174, y: NODEMCU_ORIGIN.y + y };
        const fillR = pR.active || '#eab308';
        const txtFillR = pR.active || '#94a3b8';
        html += `<g style="cursor:pointer" data-nodemcu-pin="${pR.key}" onmouseenter="showHole('ESP8266:${pR.label}', '${pR.desc}')" onclick="onNodeMcuPinClick('${pR.key}')">
          <rect x="169" y="${y - 4}" width="10" height="8" rx="1.5" fill="#0f172a" stroke="#475569" stroke-width="0.8"/>
          <circle cx="174" cy="${y}" r="${pR.active ? 3.6 : 2.5}" fill="${fillR}"/>
          <text x="165" y="${y + 3.2}" font-family="Consolas,monospace" font-size="${pR.active ? 9.5 : 8}" text-anchor="end" font-weight="${pR.active ? '900' : '600'}" fill="${txtFillR}">${pR.label}</text>
          ${pR.active ? `<rect x="184" y="${y - 6.5}" width="26" height="13" rx="3" fill="#0f172a" stroke="${pR.active}" stroke-width="1"/><text x="197" y="${y + 3}" font-family="Consolas,monospace" font-size="8.5" text-anchor="middle" font-weight="bold" fill="${pR.active}">${pR.label}</text>` : ''}
        </g>`;
      }
      g.innerHTML = html;
    }

    // =========================================================================
    // 2. VẼ HỆ THỐNG DÂY JUMPER WOKWI TỌA ĐỘ CHÍNH XÁC (TỪ CHÂN THẬT NODEMCU ESP8266 -> LỖ BREADBOARD)
    // =========================================================================
    function getElementPinXY(elId, pinName, fallbackX, fallbackY) {
      const el = document.getElementById(elId);
      if (el && Array.isArray(el.pinInfo)) {
        const p = el.pinInfo.find(item => item.name === pinName);
        if (p && el.parentElement) {
          return {
            x: el.parentElement.offsetLeft + p.x,
            y: el.parentElement.offsetTop + p.y
          };
        }
      }
      return { x: fallbackX, y: fallbackY };
    }

    let wokwiWiringController = null;
    let wokwiActiveDiagramMode = 'breadboard';
    let pcb2dSvgLoaded = false;
    let pcb2dSvgLoadingPromise = null;

    function drawWires() {
      const svg = document.getElementById('wireLayer');
      if (!svg) return;
      const H = (holeId) => HOLE_MAP[holeId] || { x: 300, y: 100 };
      const P = (pinKey) => NODEMCU_PIN_MAP[pinKey] || { x: 200, y: 100 };

      const SERVO_PINS = {
        GND: getElementPinXY('w_servo', 'GND', 880, 92.0),
        VCC: getElementPinXY('w_servo', 'V+',  880, 101.5),
        PWM: getElementPinXY('w_servo', 'PWM', 880, 111.0)
      };

      function wirePath(points, color, wireIds, moduleIds, dashed = false) {
        const d = points.map((p, idx) => `${idx === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
        const p0 = points[0];
        const pN = points[points.length - 1];
        const dashAttr = dashed ? `stroke-dasharray="6 4"` : '';
        const wList = Array.isArray(wireIds) ? wireIds : [wireIds];
        const mList = Array.isArray(moduleIds) ? moduleIds : [moduleIds];
        const primaryWire = wList[0] || '';
        return `<g class="wg-wire-item" data-wire-ids="${wList.join(',')}" data-primary-wire-id="${primaryWire}" data-module-ids="${mList.join(',')}" data-start-x="${p0.x.toFixed(1)}" data-start-y="${p0.y.toFixed(1)}" data-end-x="${pN.x.toFixed(1)}" data-end-y="${pN.y.toFixed(1)}">
          <path d="${d}" fill="none" stroke="rgba(0,0,0,0.45)" stroke-width="5.2" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="${d}" fill="none" stroke="${color}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" ${dashAttr}/>
          <circle cx="${p0.x.toFixed(1)}" cy="${p0.y.toFixed(1)}" r="3.8" fill="#0f172a" stroke="${color}" stroke-width="1.8"/>
          <circle cx="${pN.x.toFixed(1)}" cy="${pN.y.toFixed(1)}" r="3.8" fill="#0f172a" stroke="${color}" stroke-width="1.8"/>
          <path class="wg-wire-hit" d="${d}" fill="none" stroke="transparent" stroke-width="14" stroke-linecap="round" stroke-linejoin="round"/>
        </g>`;
      }

      const groups = {
        power: [
          wirePath([P('V33'), { x: 246, y: P('V33').y }, { x: 246, y: H('tp1').y }, H('tp1')], '#fb923c', ['W01', 'W08', 'W30', 'W33', 'W38'], ['psu_5v', 'led_bedroom', 'dht11_sensor', 'soil_lm393', 'ky037_sound']),
          wirePath([P('VIN'), { x: 18, y: P('VIN').y }, { x: 18, y: 390 }, { x: H('bp1').x, y: 390 }, H('bp1')], '#ef4444', ['W01'], ['psu_5v']),
          wirePath([P('GND_R'), { x: 254, y: P('GND_R').y }, { x: 254, y: H('tn1').y }, H('tn1')], '#64748b', ['W02'], ['psu_5v']),
          wirePath([H('tn25'), { x: 775, y: H('tn25').y }, { x: 775, y: H('bn25').y }, H('bn25')], '#64748b', ['W02'], ['psu_5v'])
        ],
        d0_living: [
          wirePath([P('D0'), { x: 258, y: P('D0').y }, { x: 258, y: H('c4').y }, H('c4')], '#22c55e', ['W06'], ['led_living']),
          wirePath([H('a9'), H('tn6')], '#64748b', ['W07'], ['led_living'])
        ],
        d1_servo: [
          wirePath([P('D1'), { x: 238, y: P('D1').y }, { x: 238, y: 34 }, { x: 845, y: 34 }, { x: 845, y: SERVO_PINS.PWM.y }, SERVO_PINS.PWM], '#facc15', ['W03'], ['sg90_servo']),
          wirePath([H('bp24'), { x: H('bp24').x, y: 348 }, { x: 798, y: 348 }, { x: 798, y: SERVO_PINS.VCC.y }, SERVO_PINS.VCC], '#ef4444', ['W04'], ['sg90_servo']),
          wirePath([H('bn24'), { x: H('bn24').x, y: 356 }, { x: 808, y: 356 }, { x: 808, y: SERVO_PINS.GND.y }, SERVO_PINS.GND], '#78350f', ['W05'], ['sg90_servo'])
        ],
        d2_dht11: [
          wirePath([P('D2'), { x: 264, y: P('D2').y }, { x: 264, y: H('j15').y }, H('j15')], '#06b6d4', ['W31'], ['dht11_sensor']),
          wirePath([H('f14'), { x: 468, y: H('f14').y }, { x: 468, y: H('tp9').y }, H('tp9')], '#fb923c', ['W30'], ['dht11_sensor']),
          wirePath([H('j17'), H('bn12')], '#64748b', ['W32'], ['dht11_sensor'])
        ],
        d3_d7_speaker: [
          wirePath([P('D3'), { x: 232, y: P('D3').y }, { x: 232, y: 196 }, { x: 464, y: 196 }, { x: 464, y: 128 }, { x: 482, y: 128 }], '#a855f7', ['W26'], ['pam8403_amp']),
          wirePath([H('tp10'), { x: 496, y: H('tp10').y }, { x: 496, y: 90 }], '#fb923c', ['W26'], ['pam8403_amp']),
          wirePath([{ x: 590, y: 172 }, { x: 590, y: 190 }, { x: 632, y: 190 }, { x: 632, y: H('tn18').y }, H('tn18')], '#64748b', ['W27'], ['pam8403_amp']),
          wirePath([{ x: 618, y: 128 }, { x: 626, y: 128 }, { x: 626, y: 196 }, { x: 240, y: 196 }, { x: 240, y: 404 }, { x: 180, y: 404 }, { x: 180, y: 486 }], '#c084fc', ['W26'], ['pam8403_amp']),
          wirePath([P('D7'), { x: 224, y: P('D7').y }, { x: 224, y: 396 }, { x: 46, y: 396 }, { x: 46, y: 486 }], '#c084fc', ['W21'], ['relay2_speaker']),
          wirePath([H('bp4'), { x: H('bp4').x, y: 372 }, { x: 78, y: 372 }, { x: 78, y: 486 }], '#ef4444', ['W19', 'W22'], ['relay2_speaker']),
          wirePath([H('bn4'), { x: H('bn4').x, y: 380 }, { x: 102, y: 380 }, { x: 102, y: 486 }], '#64748b', ['W20', 'W25'], ['relay2_speaker', 'pam8403_amp']),
          wirePath([{ x: 126, y: 508 }, { x: 140, y: 508 }], '#ea580c', ['W23', 'W24'], ['relay2_speaker', 'pam8403_amp']),
          wirePath([{ x: 222, y: 500 }, { x: 242, y: 500 }], '#eab308', ['W28'], ['speaker_mini']),
          wirePath([{ x: 222, y: 510 }, { x: 242, y: 510 }], '#78350f', ['W29'], ['speaker_mini'])
        ],
        d4_bedroom: [
          wirePath([H('tp20'), { x: H('tp20').x, y: H('a22').y }, H('a22')], '#fb923c', ['W08'], ['led_bedroom']),
          wirePath([P('D4'), { x: 274, y: P('D4').y }, { x: 274, y: H('c26').y }, H('c26')], '#fde047', ['W09'], ['led_bedroom'])
        ],
        d5_ky037: [
          wirePath([P('D5'), { x: 260, y: P('D5').y }, { x: 260, y: H('j6').y }, H('j6')], '#f87171', ['W40'], ['ky037_sound']),
          wirePath([H('j7'), H('bn5')], '#64748b', ['W39'], ['ky037_sound']),
          wirePath([H('f8'), H('tp6')], '#fb923c', ['W38'], ['ky037_sound'])
        ],
        d6_pump: [
          wirePath([P('D6'), { x: 270, y: P('D6').y }, { x: 270, y: 384 }, { x: 815, y: 384 }, { x: 815, y: 290 }, { x: 858, y: 290 }], '#38bdf8', ['W12'], ['relay1_pump']),
          wirePath([H('bp22'), { x: H('bp22').x, y: 392 }, { x: 825, y: 392 }, { x: 825, y: 314 }, { x: 858, y: 314 }], '#ef4444', ['W10', 'W13'], ['relay1_pump']),
          wirePath([H('bn22'), { x: H('bn22').x, y: 402 }, { x: 832, y: 402 }, { x: 832, y: 302 }, { x: 858, y: 302 }], '#64748b', ['W11'], ['relay1_pump']),
          wirePath([{ x: 983, y: 280 }, { x: 1093, y: 280 }, { x: 1093, y: 316 }], '#ef4444', ['W14', 'W15'], ['relay1_pump', 'pump_unit']),
          wirePath([{ x: 1007, y: 270 }, { x: 1007, y: 338 }, { x: 1020, y: 338 }], '#18181b', ['W16'], ['pump_unit'])
        ],
        d8_buzzer: [
          wirePath([P('D8'), { x: 284, y: P('D8').y }, { x: 284, y: 344 }, { x: 564, y: 344 }, { x: 564, y: 250 }, { x: 582, y: 250 }], '#f43f5e', ['W18'], ['buzzer_alarm']),
          wirePath([{ x: 632, y: 316 }, { x: 632, y: H('bn18').y }, H('bn18')], '#64748b', ['W18'], ['buzzer_alarm']),
          wirePath([{ x: 706, y: 242 }, { x: 722, y: 242 }, { x: 722, y: 278 }, { x: 732.7, y: 278 }, { x: 732.7, y: 270.1 }], '#f97316', ['W18'], ['buzzer_alarm']),
          wirePath([H('bp23'), { x: 754, y: H('bp23').y }, { x: 754, y: 278 }, { x: 738.9, y: 278 }, { x: 738.9, y: 270.1 }], '#ef4444', ['W17'], ['buzzer_alarm']),
          wirePath([{ x: 754, y: 278 }, { x: 754, y: 226 }, { x: 706, y: 226 }], '#ef4444', ['W17'], ['buzzer_alarm'])
        ],
        a0_soil: [
          wirePath([P('A0'), { x: 10, y: P('A0').y }, { x: 10, y: 665 }, { x: 872, y: 665 }, { x: 872, y: 575 }], '#eab308', ['W35'], ['soil_lm393']),
          wirePath([H('tp24'), { x: 785, y: H('tp24').y }, { x: 785, y: 595 }, { x: 922, y: 595 }, { x: 922, y: 575 }], '#fb923c', ['W33'], ['soil_lm393']),
          wirePath([H('bn20'), { x: H('bn20').x, y: 645 }, { x: 906, y: 645 }, { x: 906, y: 575 }], '#64748b', ['W34'], ['soil_lm393']),
          wirePath([{ x: 947, y: 530 }, { x: 1005, y: 505 }, { x: 1050, y: 523 }], '#eab308', ['W36'], ['soil_probe']),
          wirePath([{ x: 947, y: 550 }, { x: 1005, y: 525 }, { x: 1080, y: 523 }], '#ea580c', ['W37'], ['soil_probe'])
        ]
      };

      svg.innerHTML =
        Object.entries(groups)
          .map(([k, arr]) => `<g id="wg_${k}" class="w-group">${arr.join('')}</g>`)
          .join('') + '<g id="wgEndpointOverlay"></g>';

      if (wokwiWiringController) {
        wokwiWiringController.refresh();
      }
    }

    // =========================================================================
    // 3. HƯỚNG DẪN & BẢNG NỐI DÂY ĐỒNG BỘ TỪ HỢP ĐỒNG PHẦN CỨNG (SSOT JSON)
    // =========================================================================
    function renderSsotTechGuides(stepKey, contract) {
      const guideEl = document.getElementById('guideItems');
      if (!guideEl || !contract || !Array.isArray(contract.wires)) return;
      const matched =
        !stepKey || stepKey === 'all'
          ? contract.wires
          : contract.wires.filter((w) => w.wokwi_group === stepKey);
      const esc = (s) =>
        String(s == null ? '' : s)
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;');
      guideEl.innerHTML = matched
        .map(
          (w) =>
            `<li><strong>${esc(w.wire_id)} (${esc(w.module_label_vi)}):</strong> ${esc(w.instruction_vi)} <em>${esc(
              w.power_gnd_note_vi
            )}</em></li>`
        )
        .join('');
    }

    function renderSsotPinoutTable(contract) {
      const tbody = document.getElementById('ssotPinoutTableBody');
      if (!tbody || !contract || !Array.isArray(contract.wires)) return;
      const esc = (s) =>
        String(s == null ? '' : s)
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;');
      tbody.innerHTML = contract.wires
        .map(
          (w) => `<tr style="border-bottom:1px solid var(--line); cursor:pointer;" data-wire-row="${esc(w.wire_id)}">
            <td style="padding:6px 8px;"><span class="hole-badge">${esc(w.wire_id)}</span></td>
            <td style="padding:6px 8px;">${esc(w.color_vi)}</td>
            <td style="padding:6px 8px;">${esc(w.module_label_vi)} · <code>${esc(w.module_pin)}</code></td>
            <td style="padding:6px 8px;"><span class="hole-badge">${esc(w.hub_label)}</span></td>
            <td style="padding:6px 8px;"><code>${esc(w.nodemcu_pin)}</code> (${esc(w.gpio)})</td>
          </tr>`
        )
        .join('');
      tbody.querySelectorAll('tr[data-wire-row]').forEach((row) => {
        row.addEventListener('click', () => {
          const wid = row.getAttribute('data-wire-row');
          if (wid && wokwiWiringController) {
            wokwiWiringController.jumpToWireId(wid, true);
          }
        });
      });
    }

    function filterStep(stepKey, btnEl) {
      document.querySelectorAll('.step-btn').forEach(b => b.classList.remove('active'));
      if (btnEl) btnEl.classList.add('active');

      document.querySelectorAll('.w-group').forEach(g => {
        if (stepKey === 'all') {
          g.classList.remove('dimmed', 'active-step');
        } else if (g.id === 'wg_' + stepKey) {
          g.classList.remove('dimmed');
          g.classList.add('active-step');
        } else {
          g.classList.remove('active-step');
          g.classList.add('dimmed');
        }
      });

      const contract = wokwiWiringController && wokwiWiringController.getContract();
      if (contract) {
        renderSsotTechGuides(stepKey, contract);
      }
    }

    function onNodeMcuPinClick(pinKey) {
      if (!wokwiWiringController) return;
      const contract = wokwiWiringController.getContract();
      if (!contract || !Array.isArray(contract.wires)) return;
      const token = String(pinKey || '').replace(/_[LR]\d?$/, '');
      const match = contract.wires.find((w) => {
        const np = String(w.nodemcu_pin || '').toUpperCase();
        if (token === 'V33') return np.includes('3V3');
        if (token === 'GND') return np.includes('GND');
        return np.startsWith(token.toUpperCase());
      });
      if (match) {
        wokwiWiringController.inspectWire(match.wire_id);
      }
    }

    function loadPcb2dSvgOnce() {
      if (pcb2dSvgLoaded) return Promise.resolve();
      if (pcb2dSvgLoadingPromise) return pcb2dSvgLoadingPromise;
      const host = document.getElementById('pcb2dSvgHost');
      if (!host) return Promise.resolve();
      pcb2dSvgLoadingPromise = fetch('/docs/phan_cung/wiring_diagram_2d.svg', { cache: 'no-cache' })
        .then((res) => {
          if (!res || !res.ok) throw new Error('Không tải được sơ đồ PCB 2D.');
          return res.text();
        })
        .then((svgText) => {
          host.innerHTML = svgText;
          const svgEl = host.querySelector('svg');
          if (svgEl) {
            svgEl.setAttribute('id', 'pcb2dInteractiveSvg');
            const ns = 'http://www.w3.org/2000/svg';
            const ov = document.createElementNS(ns, 'g');
            ov.setAttribute('id', 'pcb2dEndpointOverlay');
            svgEl.appendChild(ov);
            svgEl.addEventListener('click', (ev) => {
              const target = ev.target && ev.target.closest ? ev.target.closest('[data-wire-id]') : null;
              if (target && wokwiWiringController) {
                const wid = target.getAttribute('data-wire-id');
                if (wid) wokwiWiringController.inspectWire(wid);
              }
            });
          }
          pcb2dSvgLoaded = true;
          if (wokwiWiringController) wokwiWiringController.refresh();
        })
        .catch(() => {
          pcb2dSvgLoadingPromise = null;
          host.innerHTML = '<p class="pcb2d-loading">Không thể tải sơ đồ PCB 2D lúc này.</p>';
        });
      return pcb2dSvgLoadingPromise;
    }

    function setWokwiDiagramMode(mode) {
      wokwiActiveDiagramMode = mode === 'pcb2d' ? 'pcb2d' : 'breadboard';
      const bbScroll = document.getElementById('workbenchScroll');
      const pcbScroll = document.getElementById('pcb2dScroll');
      if (bbScroll) bbScroll.hidden = wokwiActiveDiagramMode !== 'breadboard';
      if (pcbScroll) pcbScroll.hidden = wokwiActiveDiagramMode !== 'pcb2d';
      document.querySelectorAll('[data-wokwi-mode]').forEach((btn) => {
        const active = btn.getAttribute('data-wokwi-mode') === wokwiActiveDiagramMode;
        btn.classList.toggle('is-active', active);
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
      });
      if (wokwiActiveDiagramMode === 'pcb2d') {
        loadPcb2dSvgOnce();
      } else {
        requestAnimationFrame(fitCircuitStageToWorkbench);
      }
      if (wokwiWiringController) wokwiWiringController.refresh();
    }

    function renderEndpointRings(overlayEl, coords) {
      if (!overlayEl) return;
      overlayEl.innerHTML = (coords || [])
        .map(
          ([x, y]) =>
            `<circle class="wg-endpoint-pulse" cx="${Number(x).toFixed(1)}" cy="${Number(y).toFixed(1)}" r="9"/>` +
            `<circle class="wg-endpoint-core" cx="${Number(x).toFixed(1)}" cy="${Number(y).toFixed(1)}" r="4.2"/>`
        )
        .join('');
    }

    function clearLegacyWireGroupFilter() {
      document.querySelectorAll('#wireLayer .w-group').forEach((g) => {
        g.classList.remove('dimmed', 'active-step');
      });
      document.querySelectorAll('.step-btn').forEach((b) => {
        const onclickAttr = b.getAttribute('onclick') || '';
        const isAll = onclickAttr.includes("'all'") || onclickAttr.includes('"all"');
        b.classList.toggle('active', isAll);
      });
    }

    function initWokwiWiringGuide() {
      if (!window.SmartHomeWiringGuide || wokwiWiringController) return;
      const modeSwitchHtml = `
        <div class="wg-mode-switch" role="group" aria-label="Chế độ xem sơ đồ">
          <button type="button" class="wg-mode-btn is-active" data-wokwi-mode="breadboard" aria-pressed="true">Mạch Breadboard</button>
          <button type="button" class="wg-mode-btn" data-wokwi-mode="pcb2d" aria-pressed="false">Sơ đồ PCB 2D</button>
        </div>
      `;

      wokwiWiringController = window.SmartHomeWiringGuide.createController({
        instanceId: 'wokwi',
        toolbarMount: 'wokwiWiringToolbar',
        panelMount: 'wokwiWiringPanelMount',
        inspectMount: 'wokwiWireInspect',
        extraToolbarHtml: modeSwitchHtml,
        adapter: {
          onContractReady(contract) {
            renderSsotPinoutTable(contract);
            renderSsotTechGuides('all', contract);
            document.querySelectorAll('[data-wokwi-mode]').forEach((btn) => {
              btn.addEventListener('click', () => setWokwiDiagramMode(btn.getAttribute('data-wokwi-mode')));
            });
          },
          bindInteractions(onSelectWire) {
            const wireSvg = document.getElementById('wireLayer');
            if (wireSvg && !wireSvg.dataset.wgClickBound) {
              wireSvg.dataset.wgClickBound = '1';
              wireSvg.addEventListener('click', (ev) => {
                const item = ev.target && ev.target.closest ? ev.target.closest('.wg-wire-item') : null;
                if (!item) return;
                const wid = item.getAttribute('data-primary-wire-id');
                if (wid) onSelectWire(wid);
              });
            }
          },
          setWiresVisible(visible) {
            const wireSvg = document.getElementById('wireLayer');
            const pcbHost = document.getElementById('pcb2dSvgHost');
            if (wireSvg) wireSvg.classList.toggle('wg-wires-hidden', !visible);
            if (pcbHost) pcbHost.classList.toggle('wg-wires-hidden', !visible);
          },
          applyModuleFilter(moduleId, visibleWireIds) {
            if (moduleId !== 'all') {
              clearLegacyWireGroupFilter();
            }
            const wireSvg = document.getElementById('wireLayer');
            if (wireSvg) {
              wireSvg.querySelectorAll('.wg-wire-item').forEach((item) => {
                const ids = (item.getAttribute('data-wire-ids') || '').split(',').filter(Boolean);
                const match = moduleId === 'all' || ids.some((id) => visibleWireIds.has(id));
                item.classList.toggle('wg-wire-filtered-out', !match);
              });
            }
            const pcbHost = document.getElementById('pcb2dSvgHost');
            if (pcbHost) {
              pcbHost.querySelectorAll('.pcb-wire').forEach((item) => {
                const wid = item.getAttribute('data-wire-id') || '';
                const match = moduleId === 'all' || visibleWireIds.has(wid);
                item.classList.toggle('wg-wire-filtered-out', !match);
              });
            }
          },
          highlightStep(activeWire, visibleWireIds, meta) {
            if (activeWire) {
              clearLegacyWireGroupFilter();
            }
            const layoutEl = document.getElementById('wokwiStageLayout');
            if (layoutEl) {
              layoutEl.classList.toggle('has-guide-open', Boolean(meta && meta.guideOpen));
              requestAnimationFrame(fitCircuitStageToWorkbench);
            }

            const wireSvg = document.getElementById('wireLayer');
            const bbOverlay = document.getElementById('wgEndpointOverlay');
            if (wireSvg) {
              const items = Array.from(wireSvg.querySelectorAll('.wg-wire-item'));
              const ringCoords = [];
              items.forEach((item) => {
                if (!activeWire) {
                  item.classList.remove('wg-wire-highlighted', 'wg-wire-dimmed');
                  return;
                }
                const ids = (item.getAttribute('data-wire-ids') || '').split(',').filter(Boolean);
                const isMatch = ids.includes(activeWire.wire_id);
                item.classList.toggle('wg-wire-highlighted', isMatch);
                item.classList.toggle('wg-wire-dimmed', !isMatch);
                if (isMatch && ringCoords.length < 4) {
                  const sx = Number(item.getAttribute('data-start-x'));
                  const sy = Number(item.getAttribute('data-start-y'));
                  const ex = Number(item.getAttribute('data-end-x'));
                  const ey = Number(item.getAttribute('data-end-y'));
                  if (Number.isFinite(sx) && Number.isFinite(sy)) ringCoords.push([sx, sy]);
                  if (Number.isFinite(ex) && Number.isFinite(ey)) ringCoords.push([ex, ey]);
                }
              });
              renderEndpointRings(bbOverlay, activeWire ? ringCoords : []);
            }

            const pcbHost = document.getElementById('pcb2dSvgHost');
            const pcbOverlay = document.getElementById('pcb2dEndpointOverlay');
            if (pcbHost) {
              pcbHost.querySelectorAll('.pcb-wire').forEach((item) => {
                if (!activeWire) {
                  item.classList.remove('wg-wire-highlighted', 'wg-wire-dimmed');
                  return;
                }
                const isMatch = item.getAttribute('data-wire-id') === activeWire.wire_id;
                item.classList.toggle('wg-wire-highlighted', isMatch);
                item.classList.toggle('wg-wire-dimmed', !isMatch);
              });
              const pinCoords = [];
              pcbHost.querySelectorAll('.pcb-pin').forEach((pinEl) => {
                const isMatch = Boolean(activeWire && pinEl.getAttribute('data-wire-id') === activeWire.wire_id);
                pinEl.classList.toggle('wg-pin-highlighted', isMatch);
                if (isMatch) {
                  const cx = Number(pinEl.getAttribute('data-cx'));
                  const cy = Number(pinEl.getAttribute('data-cy'));
                  if (Number.isFinite(cx) && Number.isFinite(cy)) pinCoords.push([cx, cy]);
                }
              });
              renderEndpointRings(pcbOverlay, activeWire ? pinCoords : []);
            }
          }
        }
      });
      window.wokwiWiringController = wokwiWiringController;
    }

    // =========================================================================
    // 4. ĐỒNG BỘ TRẠNG THÁI LIVE VỚI CÁC LINH KIỆN @WOKWI/ELEMENTS
    // =========================================================================
    let devState = {
      main_door: 'CLOSED',
      living_room_light: 'OFF',
      bedroom_light: 'OFF',
      garden_pump: 'OFF',
      alarm_siren: 'OFF',
      speaker_amp: 'OFF'
    };
    let pumpTimer = null;
    let pumpDeg = 0;

    function logSerial(text, cls = '') {
      const box = document.getElementById('serialBox');
      const d = document.createElement('div');
      d.className = 'serial-line ' + cls;
      d.textContent = `[${new Date().toTimeString().split(' ')[0]}] ${text}`;
      box.appendChild(d);
      box.scrollTop = box.scrollHeight;
    }

    window._wokwiServerConnected = true;
    window._simRunning = false;

    function setSimulationRunning(running) {
      window._simRunning = !!running;
      const runBtn = document.getElementById('btnRunSim');
      const stopBtn = document.getElementById('btnStopSim');
      if (runBtn) runBtn.style.display = window._simRunning ? 'none' : 'inline-flex';
      if (stopBtn) stopBtn.style.display = window._simRunning ? 'inline-flex' : 'none';
      logSerial(window._simRunning ? 'Đã bắt đầu mô phỏng mạch.' : 'Đã dừng mô phỏng mạch.', 'cmd');
      if (window._simRunning) fetchState();
    }

    function openTechSpecsPanel() {
      const panel = document.getElementById('techSpecsPanel');
      if (panel) {
        panel.open = !panel.open;
        if (panel.open) panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }

    const wokwiControlState = {};
    const WOKWI_DEBOUNCE_MS = 50;
    const WOKWI_CLIENT_ID =
      (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function')
        ? `wokwi_${crypto.randomUUID()}`
        : `wokwi_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
    let wokwiLastRevisionSeq = 0;
    let wokwiPollInFlight = false;
    if (typeof window !== 'undefined') {
      window.__wokwiControlState = wokwiControlState;
      window.__wokwiClientId = WOKWI_CLIENT_ID;
    }

    function getWokwiControl(devId) {
      if (!wokwiControlState[devId]) {
        const initSt = devState[devId] || 'OFF';
        wokwiControlState[devId] = {
          seq: 0,
          lastConfirmedSeq: 0,
          lastVersion: 0,
          serverKnownState: String(initSt).toUpperCase(),
          serverKnownVersion: 0,
          serverKnownRevisionSeq: wokwiLastRevisionSeq,
          needsServerKnownSync: false,
          desiredState: initSt,
          confirmedState: initSt,
          pendingCount: 0,
          debounceTimer: null,
          lastClickTs: 0,
        };
      }
      return wokwiControlState[devId];
    }

    function formatHumanDeviceState(id, st, locked) {
      if (locked) return 'Đã khóa';
      if (id === 'main_door') return st === 'OPEN' ? 'Đang mở' : 'Đang đóng';
      return (st === 'ON' || st === 'OPEN') ? 'Đang bật' : 'Đang tắt';
    }

    function applyWokwiSingleDeviceUI(id, st) {
      devState[id] = st;
      const btn = document.getElementById('btn_' + id);
      const lb = document.getElementById('st_' + id);
      const on = (st === 'OPEN' || st === 'ON');
      const isLockedOffline = !window._wokwiServerConnected && (id === 'main_door' || id === 'alarm_siren');
      if (btn) btn.classList.toggle('on', on);
      if (lb) lb.textContent = formatHumanDeviceState(id, st, isLockedOffline);
      if (id === 'main_door') {
        const servoEl = document.getElementById('w_servo');
        if (servoEl) servoEl.angle = (st === 'OPEN') ? 90 : 0;
      } else if (id === 'living_room_light') {
        const ledLiv = document.getElementById('w_led_living');
        if (ledLiv) ledLiv.value = (st === 'ON');
      } else if (id === 'bedroom_light') {
        const ledBed = document.getElementById('w_led_bedroom');
        if (ledBed) ledBed.value = (st === 'ON');
      } else if (id === 'alarm_siren') {
        const buzEl = document.getElementById('w_buzzer');
        if (buzEl) buzEl.hasSignal = (st === 'ON');
      } else if (id === 'garden_pump') {
        const pumpOn = (st === 'ON');
        const rLed = document.getElementById('relay_act_led');
        const pTxt = document.getElementById('pump_state_txt');
        if (rLed) rLed.setAttribute('fill', pumpOn ? '#ef4444' : '#450a0a');
        if (pTxt) {
          pTxt.textContent = pumpOn ? 'ĐANG BƠM (ON)' : 'ĐANG TẮT (OFF)';
          pTxt.setAttribute('fill', pumpOn ? '#0284c7' : '#64748b');
        }
        if (pumpOn && !pumpTimer) {
          pumpTimer = setInterval(() => {
            pumpDeg = (pumpDeg + 35) % 360;
            const w = document.getElementById('pump_wheel');
            if (w) w.setAttribute('transform', `rotate(${pumpDeg}, 116, 30)`);
          }, 60);
        } else if (!pumpOn && pumpTimer) {
          clearInterval(pumpTimer);
          pumpTimer = null;
        }
      } else if (id === 'speaker_amp') {
        const ampOn = (st === 'ON');
        const r2Led = document.getElementById('relay2_act_led');
        const spkLed = document.getElementById('hw_spk_led');
        const pwrTxt = document.getElementById('pam8403_pwr_txt');
        if (r2Led) r2Led.setAttribute('fill', ampOn ? '#ef4444' : '#450a0a');
        if (spkLed) spkLed.setAttribute('fill', ampOn ? '#22c55e' : '#334155');
        if (pwrTxt) {
          pwrTxt.textContent = ampOn ? 'NGUỒN PAM8403: ĐANG BẬT (D7 ON)' : 'NGUỒN PAM8403: ĐANG TẮT (Tự bật khi phát chuông)';
          pwrTxt.setAttribute('fill', ampOn ? '#4ade80' : '#94a3b8');
        }
      }
    }

    function reconcileWokwiIdleToServerKnown(devId, ctrl) {
      if (!ctrl || ctrl.pendingCount > 0 || ctrl.debounceTimer !== null) return false;
      const knownVer = Number(ctrl.serverKnownVersion || 0);
      const curVer = Number(ctrl.lastVersion || 0);
      if (!ctrl.needsServerKnownSync && !(knownVer > 0 && knownVer > curVer)) {
        return false;
      }
      const authNewer = String(
        ctrl.serverKnownState || ctrl.confirmedState || (devId === 'main_door' ? 'CLOSED' : 'OFF')
      ).toUpperCase();
      ctrl.confirmedState = authNewer;
      ctrl.desiredState = authNewer;
      ctrl.lastVersion = Math.max(curVer, knownVer);
      ctrl.needsServerKnownSync = false;
      applyWokwiSingleDeviceUI(devId, authNewer);
      return true;
    }

    function syncWokwiComponents(snap) {
      if (!snap || !snap.devices) return;
      const snapRev = Number(snap.revision_seq || 0);
      if (snapRev > 0 && wokwiLastRevisionSeq > 0 && snapRev < wokwiLastRevisionSeq) {
        return;
      }
      if (snapRev > wokwiLastRevisionSeq) {
        wokwiLastRevisionSeq = snapRev;
      }

      window._wokwiServerConnected = snap.server_connected !== false;

      const connDot = document.getElementById('wokwiConnDot');
      if (connDot) {
        connDot.textContent = window._wokwiServerConnected
          ? (isLocalWokwiHost() ? 'Đã kết nối' : 'Đồng bộ HTTP Cloud')
          : 'Mất kết nối';
        connDot.classList.toggle('offline', !window._wokwiServerConnected);
      }
      const btnReconnect = document.getElementById('btnReconnectWokwi');
      if (btnReconnect) {
        btnReconnect.style.display = window._wokwiServerConnected ? 'none' : 'inline-flex';
      }

      const btnSrv = document.getElementById('btnWokwiServerMode');
      if (btnSrv) {
        if (window._wokwiServerConnected) {
          btnSrv.textContent = 'Đã kết nối máy chủ';
          btnSrv.style.background = 'var(--accent-soft)';
          btnSrv.style.borderColor = '#cce5e3';
          btnSrv.style.color = 'var(--accent)';
        } else {
          btnSrv.textContent = 'Chế độ độc lập (Khóa cửa)';
          btnSrv.style.background = 'var(--amber-soft)';
          btnSrv.style.borderColor = 'var(--amber-border)';
          btnSrv.style.color = 'var(--amber)';
        }
      }

      const incomingList = Array.isArray(snap.devices)
        ? snap.devices
        : Object.keys(devState)
            .filter(k => Boolean(snap.devices[k]))
            .map(k => Object.assign({ id: k }, snap.devices[k]));

      for (const d of incomingList) {
        if (d && d.id && devState.hasOwnProperty(d.id)) {
          const ctrl = getWokwiControl(d.id);
          const srvSeq = Number(d.last_client_seq || 0);
          const srvVer = Number(d.version || 0);
          const sameClient = Boolean(d.last_client_id && d.last_client_id === WOKWI_CLIENT_ID);
          const hasPending = ctrl.pendingCount > 0 || ctrl.debounceTimer !== null;

          if (
            srvVer > Number(ctrl.serverKnownVersion || 0) ||
            (snapRev > Number(ctrl.serverKnownRevisionSeq || 0) &&
              srvVer >= Number(ctrl.serverKnownVersion || 0))
          ) {
            ctrl.serverKnownVersion = Math.max(Number(ctrl.serverKnownVersion || 0), srvVer);
            if (snapRev > 0) {
              ctrl.serverKnownRevisionSeq = Math.max(Number(ctrl.serverKnownRevisionSeq || 0), snapRev);
            }
            if (d.state) {
              const nextKnownSt = String(d.state).toUpperCase();
              ctrl.serverKnownState = nextKnownSt;
              ctrl.confirmedState = nextKnownSt;
            }
            if (hasPending && !(sameClient && srvSeq >= ctrl.seq)) {
              ctrl.needsServerKnownSync = true;
            }
          }

          if (hasPending && !(sameClient && srvSeq >= ctrl.seq)) {
            devState[d.id] = ctrl.desiredState;
          } else if (srvVer > 0 && ctrl.lastVersion > 0 && srvVer < ctrl.lastVersion) {
            devState[d.id] = ctrl.confirmedState;
          } else if (
            sameClient &&
            ctrl.lastConfirmedSeq > 0 &&
            srvSeq > 0 &&
            srvSeq < ctrl.lastConfirmedSeq &&
            srvVer <= ctrl.lastVersion
          ) {
            devState[d.id] = ctrl.desiredState;
          } else {
            devState[d.id] = d.state;
            ctrl.confirmedState = d.state;
            ctrl.serverKnownState = String(d.state || '').toUpperCase();
            if (!hasPending) {
              ctrl.desiredState = d.state;
              ctrl.needsServerKnownSync = false;
              if (sameClient && srvSeq > ctrl.seq) ctrl.seq = srvSeq;
            }
            if (sameClient && srvSeq > ctrl.lastConfirmedSeq) ctrl.lastConfirmedSeq = srvSeq;
            if (srvVer > ctrl.lastVersion) ctrl.lastVersion = srvVer;
            ctrl.serverKnownVersion = Math.max(Number(ctrl.serverKnownVersion || 0), ctrl.lastVersion);
            if (snapRev > 0) {
              ctrl.serverKnownRevisionSeq = Math.max(Number(ctrl.serverKnownRevisionSeq || 0), snapRev);
            }
          }
        }
      }

      // Cập nhật nút bên phải
      for (const [id, st] of Object.entries(devState)) {
        const btn = document.getElementById('btn_' + id);
        const lb = document.getElementById('st_' + id);
        const on = (st === 'OPEN' || st === 'ON');
        const isLockedOffline = !window._wokwiServerConnected && (id === 'main_door' || id === 'alarm_siren');
        if (btn) btn.classList.toggle('on', on);
        if (lb) lb.textContent = formatHumanDeviceState(id, st, isLockedOffline);
      }

      // 1. <wokwi-servo id="w_servo"> (Chân D1)
      const servoEl = document.getElementById('w_servo');
      if (servoEl) servoEl.angle = (devState.main_door === 'OPEN') ? 90 : 0;

      // 2. <wokwi-led id="w_led_living"> (Chân D0)
      const ledLiv = document.getElementById('w_led_living');
      if (ledLiv) ledLiv.value = (devState.living_room_light === 'ON');

      // 3. <wokwi-led id="w_led_bedroom"> (Chân D4 Active-LOW)
      const ledBed = document.getElementById('w_led_bedroom');
      if (ledBed) ledBed.value = (devState.bedroom_light === 'ON');

      // 4. <wokwi-buzzer id="w_buzzer"> (Chân D8)
      const buzEl = document.getElementById('w_buzzer');
      if (buzEl) buzEl.hasSignal = (devState.alarm_siren === 'ON');

      // 5. Relay 1 Xanh & Máy Bơm Nước Mini (Chân D6)
      const pumpOn = (devState.garden_pump === 'ON');
      const rLed = document.getElementById('relay_act_led');
      const pTxt = document.getElementById('pump_state_txt');
      if (rLed) rLed.setAttribute('fill', pumpOn ? '#ef4444' : '#450a0a');
      if (pTxt) {
        pTxt.textContent = pumpOn ? 'ĐANG BƠM (ON)' : 'ĐANG TẮT (OFF)';
        pTxt.setAttribute('fill', pumpOn ? '#0284c7' : '#64748b');
      }
      if (pumpOn && !pumpTimer) {
        pumpTimer = setInterval(() => {
          pumpDeg = (pumpDeg + 35) % 360;
          const w = document.getElementById('pump_wheel');
          if (w) w.setAttribute('transform', `rotate(${pumpDeg}, 116, 30)`);
        }, 60);
      } else if (!pumpOn && pumpTimer) {
        clearInterval(pumpTimer);
        pumpTimer = null;
      }

      // 6. Relay 2 Đỏ Opto & Nguồn PAM8403 (Chân D7)
      const ampOn = (devState.speaker_amp === 'ON');
      const r2Led = document.getElementById('relay2_act_led');
      const spkLed = document.getElementById('hw_spk_led');
      const pwrTxt = document.getElementById('pam8403_pwr_txt');
      if (r2Led) r2Led.setAttribute('fill', ampOn ? '#ef4444' : '#450a0a');
      if (spkLed) spkLed.setAttribute('fill', ampOn ? '#22c55e' : '#334155');
      if (pwrTxt) {
        pwrTxt.textContent = ampOn ? 'NGUỒN PAM8403: ĐANG BẬT (D7 ON)' : 'NGUỒN PAM8403: ĐANG TẮT (Tự bật khi phát chuông)';
        pwrTxt.setAttribute('fill', ampOn ? '#4ade80' : '#94a3b8');
      }

      // 7. Telemetry từ snap.mqtt hoặc snap.mqtt_hardware
      const dht = (snap.mqtt && snap.mqtt.dht11_telemetry) || (snap.mqtt_hardware && snap.mqtt_hardware.esp8266_status) || null;
      const soil = (snap.mqtt && snap.mqtt.soil_moisture_telemetry) || (snap.mqtt_hardware && snap.mqtt_hardware.esp8266_status) || null;
      const sound = (snap.mqtt && (snap.mqtt.sound_telemetry || snap.mqtt.ky037_telemetry)) || (snap.sensors && snap.sensors.sound) || null;
      let curT = 28.5;
      let curH = 65;
      let curS = 62;
      if (dht && dht.temp_c !== undefined) {
        const rawT = Number(dht.temp_c);
        const safeT = Number.isFinite(rawT) ? Math.max(0, Math.min(60, rawT)) : 28.5;
        const rawH = Number(dht.humidity_pct);
        const hum = Number.isFinite(rawH) ? Math.max(0, Math.min(100, rawH)) : 65;
        curT = safeT;
        curH = hum;
        const lblDht = document.getElementById('lblDht');
        if (lblDht) lblDht.textContent = `${safeT.toFixed(1)}°C | ${hum.toFixed(0)}%`;
        const mainTemp = document.getElementById('mainTempValue');
        if (mainTemp) mainTemp.textContent = `${safeT.toFixed(1)}°C`;
        const dhtEl = document.getElementById('w_dht');
        if (dhtEl) {
          dhtEl.temperature = safeT;
          dhtEl.humidity = hum;
        }
      }
      if (soil && soil.soil_moisture_pct !== undefined) {
        const rawS = Number(soil.soil_moisture_pct);
        const sPct = Number.isFinite(rawS) ? Math.max(0, Math.min(100, rawS)) : 62;
        curS = sPct;
        const adc = Math.round(1024 - (sPct / 100) * 724);
        const lblSoil = document.getElementById('lblSoil');
        if (lblSoil) lblSoil.textContent = `${sPct.toFixed(0)}% (ADC: ${adc})`;
        const mainSoil = document.getElementById('mainSoilValue');
        if (mainSoil) mainSoil.textContent = `${sPct.toFixed(0)}%`;
        const svgLbl = document.getElementById('soil_svg_label');
        if (svgLbl) svgLbl.textContent = `Độ ẩm đất: ${sPct.toFixed(0)}% (${sPct < 40 ? 'ĐẤT KHÔ!' : (sPct >= 70 ? 'ĐỦ ẨM' : 'Bình thường')})`;
        const doLed = document.getElementById('lm393_do_led');
        if (doLed) doLed.setAttribute('fill', sPct < 40 ? '#ef4444' : '#450a0a');
      }
      if (sound) {
        const cnt = Number(sound.event_count || 0);
        const det = Boolean(sound.sound_detected);
        const lblKy = document.getElementById('lblKy037');
        const pCnt = document.getElementById('ky037_panel_count');
        const pLed = document.getElementById('ky037_panel_led');
        const wKy = document.getElementById('w_ky037');
        if (lblKy) lblKy.textContent = det ? `Phát hiện tiếng động! (${cnt} lần)` : `Im lặng (${cnt} lần)`;
        if (pCnt) pCnt.textContent = `${cnt} lần`;
        if (pLed) pLed.style.background = det ? '#ef4444' : '#450a0a';
        if (wKy) wKy.led2 = det;
      }
      updateLiveTelemetryHeader(curT, curH, curS);
    }

    async function toggleWokwiServerMode() {
      const nextConnected = !window._wokwiServerConnected;
      const r = await fetch('/api/server_mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ server_connected: nextConnected })
      });
      const data = await r.json().catch(() => ({}));
      if (r.status === 401 || r.status === 403 || (data && data.authenticated === false)) {
        showWokwiAuthError((data && data.error) || 'Bạn cần đăng nhập để thay đổi trạng thái máy chủ.');
        return;
      }
      hideWokwiAuthError();
      logSerial(
        nextConnected
          ? 'Đã kết nối lại máy chủ.'
          : 'Mất kết nối máy chủ: chuyển sang chế độ độc lập và khóa cửa chính.',
        nextConnected ? 'cmd' : 'warn'
      );
      if (data.snapshot) syncWokwiComponents(data.snapshot);
      else fetchState();
    }

    async function fetchState() {
      if (wokwiPollInFlight) return;
      wokwiPollInFlight = true;
      try {
        const r = await fetch('/api/state', { credentials: 'same-origin' });
        if (r.status === 401 || r.status === 403) {
          if (typeof window._stopWokwiHttpPolling === 'function') {
            window._stopWokwiHttpPolling();
          }
          const wsEl = document.querySelector('.workspace');
          const techEl = document.getElementById('techSpecsPanel');
          if (wsEl) { wsEl.hidden = true; wsEl.style.display = 'none'; }
          if (techEl) { techEl.hidden = true; techEl.style.display = 'none'; }
          showWokwiAuthError('Vui lòng đăng nhập để xem và điều khiển mạch phần cứng.');
          if (window.SmartHomeNavGuard && typeof window.SmartHomeNavGuard.applyNavAuthState === 'function') {
            window.SmartHomeNavGuard.applyNavAuthState({ authenticated: false });
          }
          return;
        }
        if (!r.ok) return;
        const wsElOk = document.querySelector('.workspace');
        const techElOk = document.getElementById('techSpecsPanel');
        if (wsElOk && wsElOk.hidden) { wsElOk.hidden = false; wsElOk.style.display = ''; }
        if (techElOk && techElOk.hidden) { techElOk.hidden = false; techElOk.style.display = ''; }
        hideWokwiAuthError();
        const snap = await r.json();
        if (window.SmartHomeNavGuard && typeof window.SmartHomeNavGuard.applyNavAuthState === 'function') {
          window.SmartHomeNavGuard.applyNavAuthState({
            authenticated: snap.authenticated !== false,
            tier: snap.current_tier || 3,
            role: snap.role || '',
          });
        }
        if (snap.authenticated !== false && !RAW_ESP8266_INO) {
          loadRealInoCode();
        }
        syncWokwiComponents(snap);
      } catch (e) {
      } finally {
        wokwiPollInFlight = false;
      }
    }

    async function toggleDevice(devId) {
      if (!window._wokwiServerConnected && (devId === 'main_door' || devId === 'alarm_siren')) {
        logSerial(`Chặn lệnh ${devId}: Mạch đang ở chế độ độc lập, không mở cửa chính hoặc còi.`, 'warn');
        return;
      }
      const ctrl = getWokwiControl(devId);
      const cur = (ctrl.pendingCount > 0 || ctrl.debounceTimer !== null) ? ctrl.desiredState : (devState[devId] || 'OFF');
      const isCurOn = cur === 'OPEN' || cur === 'ON';
      const nextIsOn = !isCurOn;
      const nextState = devId === 'main_door' ? (nextIsOn ? 'OPEN' : 'CLOSED') : (nextIsOn ? 'ON' : 'OFF');
      const nextAct = devId === 'main_door' ? (nextIsOn ? 'open' : 'close') : (nextIsOn ? 'turn_on' : 'turn_off');

      ctrl.seq += 1;
      const mySeq = ctrl.seq;
      const myTs = Date.now();
      const reqId = `${WOKWI_CLIENT_ID}:${devId}:${mySeq}`;
      ctrl.lastClickTs = myTs;
      ctrl.desiredState = nextState;
      applyWokwiSingleDeviceUI(devId, nextState);

      logSerial(`Cập nhật thiết bị ${devId} -> ${nextAct}`, 'cmd');

      if (ctrl.debounceTimer !== null) {
        clearTimeout(ctrl.debounceTimer);
        ctrl.debounceTimer = null;
      }
      return new Promise(resolve => {
        ctrl.debounceTimer = setTimeout(async () => {
          ctrl.debounceTimer = null;
          if (mySeq < ctrl.seq) {
            resolve();
            return;
          }
          ctrl.pendingCount += 1;
          try {
            const r = await fetch('/api/device', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                device_id: devId,
                action: nextAct,
                target_state: nextState,
                state: nextState,
                client_id: WOKWI_CLIENT_ID,
                client_seq: mySeq,
                client_ts_ms: myTs,
                request_id: reqId,
                source: 'wokwi_ui',
              }),
            });
            const data = await r.json().catch(() => ({}));
            ctrl.pendingCount = Math.max(0, ctrl.pendingCount - 1);
            if (r.status === 401 || r.status === 403 || (data && data.authenticated === false)) {
              showWokwiAuthError((data && data.error) || 'Vui lòng đăng nhập để điều khiển công tắc phần cứng.');
            } else if (r.ok && data && data.ok !== false) {
              hideWokwiAuthError();
            }
            if (mySeq < ctrl.seq) {
              reconcileWokwiIdleToServerKnown(devId, ctrl);
              resolve();
              return;
            }
            const respVer = Number(
              data && data.device_version !== undefined && data.device_version !== null ? data.device_version : 0
            );
            const respRev = Number(
              data && data.revision_seq !== undefined && data.revision_seq !== null
                ? data.revision_seq
                : (data && data.snapshot && data.snapshot.revision_seq ? data.snapshot.revision_seq : 0)
            );
            const maxKnownVer = Math.max(Number(ctrl.lastVersion || 0), Number(ctrl.serverKnownVersion || 0));
            const maxKnownDevRev = Math.max(
              Number(wokwiLastRevisionSeq || 0),
              Number(ctrl.serverKnownRevisionSeq || 0)
            );
            const isSupersededResponse =
              (respVer > 0 && maxKnownVer > 0 && respVer < maxKnownVer) ||
              (respRev > 0 &&
                maxKnownDevRev > 0 &&
                respRev < maxKnownDevRev &&
                (respVer === 0 || maxKnownVer === 0 || respVer <= maxKnownVer));
            if (isSupersededResponse) {
              ctrl.lastConfirmedSeq = Math.max(ctrl.lastConfirmedSeq || 0, mySeq);
              ctrl.needsServerKnownSync = true;
              reconcileWokwiIdleToServerKnown(devId, ctrl);
              resolve();
              return;
            }
            if (data && data.stale_ignored) {
              const authState = String((data && data.state) || ctrl.confirmedState || (devId === 'main_door' ? 'CLOSED' : 'OFF')).toUpperCase();
              ctrl.confirmedState = authState;
              ctrl.desiredState = authState;
              ctrl.serverKnownState = authState;
              ctrl.needsServerKnownSync = false;
              if (respVer > 0) {
                ctrl.lastVersion = Math.max(ctrl.lastVersion, respVer);
                ctrl.serverKnownVersion = Math.max(ctrl.serverKnownVersion || 0, respVer);
              }
              if (respRev > 0) {
                wokwiLastRevisionSeq = Math.max(wokwiLastRevisionSeq, respRev);
                ctrl.serverKnownRevisionSeq = Math.max(ctrl.serverKnownRevisionSeq || 0, respRev);
              }
              applyWokwiSingleDeviceUI(devId, authState);
              if (data.snapshot) syncWokwiComponents(data.snapshot);
              resolve();
              return;
            }
            if (!r.ok || (data && (data.ok === false || data.error))) {
              if (data && data.error) logSerial(`[CHẶN] ${data.error}`, 'warn');
              const hasNewerKnown =
                Number(ctrl.serverKnownVersion || 0) > Number(ctrl.lastVersion || 0) && Boolean(ctrl.serverKnownState);
              const revertState = String(
                hasNewerKnown ? ctrl.serverKnownState : (ctrl.confirmedState || (devId === 'main_door' ? 'CLOSED' : 'OFF'))
              ).toUpperCase();
              ctrl.confirmedState = revertState;
              ctrl.desiredState = revertState;
              if (hasNewerKnown) {
                ctrl.lastVersion = Math.max(Number(ctrl.lastVersion || 0), Number(ctrl.serverKnownVersion || 0));
              }
              ctrl.needsServerKnownSync = false;
              applyWokwiSingleDeviceUI(devId, revertState);
              if (data.snapshot) syncWokwiComponents(data.snapshot);
              resolve();
              return;
            }
            const finalState = String((data && data.state) || nextState).toUpperCase();
            ctrl.confirmedState = finalState;
            ctrl.desiredState = finalState;
            ctrl.serverKnownState = finalState;
            ctrl.needsServerKnownSync = false;
            ctrl.lastConfirmedSeq = Math.max(ctrl.lastConfirmedSeq, mySeq);
            if (respVer > 0) {
              ctrl.lastVersion = Math.max(ctrl.lastVersion, respVer);
              ctrl.serverKnownVersion = Math.max(ctrl.serverKnownVersion || 0, respVer);
            }
            if (respRev > 0) {
              wokwiLastRevisionSeq = Math.max(wokwiLastRevisionSeq, respRev);
              ctrl.serverKnownRevisionSeq = Math.max(ctrl.serverKnownRevisionSeq || 0, respRev);
            }
            applyWokwiSingleDeviceUI(devId, finalState);
            if (data && data.snapshot) syncWokwiComponents(data.snapshot);
            else fetchState();
          } catch (_) {
            ctrl.pendingCount = Math.max(0, ctrl.pendingCount - 1);
            if (mySeq < ctrl.seq) {
              reconcileWokwiIdleToServerKnown(devId, ctrl);
            } else if (mySeq === ctrl.seq) {
              const hasNewerKnown =
                Number(ctrl.serverKnownVersion || 0) > Number(ctrl.lastVersion || 0) && Boolean(ctrl.serverKnownState);
              const revertState = String(
                hasNewerKnown ? ctrl.serverKnownState : (ctrl.confirmedState || (devId === 'main_door' ? 'CLOSED' : 'OFF'))
              ).toUpperCase();
              ctrl.confirmedState = revertState;
              ctrl.desiredState = revertState;
              if (hasNewerKnown) {
                ctrl.lastVersion = Math.max(Number(ctrl.lastVersion || 0), Number(ctrl.serverKnownVersion || 0));
              }
              ctrl.needsServerKnownSync = false;
              applyWokwiSingleDeviceUI(devId, revertState);
            }
          }
          resolve();
        }, WOKWI_DEBOUNCE_MS);
      });
    }

    function onSoilSlide(val) {
      const sPct = parseFloat(val);
      const adc = Math.round(1024 - (sPct / 100) * 724);
      document.getElementById('lblSoil').textContent = `${sPct.toFixed(0)}% (ADC: ${adc})`;
      const mainSoil = document.getElementById('mainSoilValue');
      if (mainSoil) mainSoil.textContent = `${sPct.toFixed(0)}%`;
    }

    async function commitSoilSlide(val) {
      const sPct = parseFloat(val);
      logSerial(`Độ ẩm đất = ${sPct.toFixed(0)}%`, 'warn');
      const r = await fetch('/api/soil_moisture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ soil_moisture_pct: sPct })
      });
      const data = await r.json().catch(() => ({}));
      if (r.status === 401 || r.status === 403 || (data && data.authenticated === false)) {
        showWokwiAuthError((data && data.error) || 'Vui lòng đăng nhập để thay đổi giá trị cảm biến.');
        return;
      }
      if (data.auto_action === 'AUTO_PUMP_ON') {
        logSerial(`Độ ẩm đất thấp (${sPct}% < 40%) -> Tự bật máy bơm.`, 'cmd');
      } else if (data.auto_action === 'AUTO_PUMP_OFF') {
        logSerial(`Độ ẩm đất đạt mức (${sPct}% >= 70%) -> Tự tắt máy bơm.`, 'cmd');
      }
      fetchState();
    }

    function onTempSlide(val) {
      const t = parseFloat(val);
      document.getElementById('lblDht').textContent = `${t.toFixed(1)}°C | 65%`;
      const mainTemp = document.getElementById('mainTempValue');
      if (mainTemp) mainTemp.textContent = `${t.toFixed(1)}°C`;
    }

    async function commitTempSlide(val) {
      const t = parseFloat(val);
      logSerial(`Nhiệt độ = ${t.toFixed(1)}°C, Độ ẩm = 65%`, 'cmd');
      const r = await fetch('/api/dht11', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ temp_c: t, humidity_pct: 65 })
      });
      if (r.status === 401 || r.status === 403) {
        const d = await r.json().catch(() => ({}));
        showWokwiAuthError((d && d.error) || 'Vui lòng đăng nhập để thay đổi giá trị cảm biến.');
        return;
      }
      fetchState();
    }

    async function triggerKy037SoundDemo() {
      const pLed = document.getElementById('ky037_panel_led');
      const wKy = document.getElementById('w_ky037');
      if (pLed) pLed.style.background = '#ef4444';
      if (wKy) wKy.led2 = true;

      logSerial('[KY-037 D5/GPIO14] Giả lập xung vỗ tay / âm thanh lớn -> POST /api/sound_sensor', 'cmd');
      try {
        const r = await fetch('/api/sound_sensor', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            node_id: 'esp8266_node_01',
            sound_detected: true,
            pin: 'D5 (GPIO 14)',
            gpio: 14,
            source: 'wokwi_ui'
          })
        });
        const data = await r.json().catch(() => ({}));
        if (r.status === 401 || r.status === 403 || (data && data.authenticated === false)) {
          showWokwiAuthError((data && data.error) || 'Vui lòng đăng nhập để gửi sự kiện cảm biến âm thanh.');
        } else {
          hideWokwiAuthError();
          const cnt = Number((data.telemetry && data.telemetry.event_count) || (data.sound_telemetry && data.sound_telemetry.event_count) || data.event_count || 1);
          const lblKy = document.getElementById('lblKy037');
          const pCnt = document.getElementById('ky037_panel_count');
          if (lblKy) lblKy.textContent = `Phát hiện tiếng động! (${cnt} lần)`;
          if (pCnt) pCnt.textContent = `${cnt} lần`;
        }
      } catch (e) {}

      setTimeout(() => {
        if (pLed) pLed.style.background = '#450a0a';
        if (wKy) wKy.led2 = false;
      }, 900);
      fetchState();
    }

    function playHardwareSpeakerTone(mode = 1) {
      try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const playBeep = (freq, startSec, durSec) => {
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.type = 'sine';
          osc.frequency.setValueAtTime(freq, ctx.currentTime + startSec);
          gain.gain.setValueAtTime(0.14, ctx.currentTime + startSec);
          gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + startSec + durSec);
          osc.connect(gain);
          gain.connect(ctx.destination);
          osc.start(ctx.currentTime + startSec);
          osc.stop(ctx.currentTime + startSec + durSec);
        };
        if (mode === 1) {
          playBeep(1180, 0.0, 0.09);
          playBeep(1560, 0.1, 0.13);
        } else if (mode === 2) {
          playBeep(1350, 0.0, 0.09);
          playBeep(920, 0.1, 0.13);
        } else {
          playBeep(440, 0.0, 0.11);
          playBeep(440, 0.15, 0.11);
          playBeep(440, 0.30, 0.14);
        }
      } catch (e) {}
    }

    function testSpeakerChimeDemo() {
      const r2Led = document.getElementById('relay2_act_led');
      const spkLed = document.getElementById('hw_spk_led');
      const spkCone = document.getElementById('hw_spk_cone');
      const pwrTxt = document.getElementById('pam8403_pwr_txt');
      if (r2Led) r2Led.setAttribute('fill', '#ef4444');
      if (spkLed) spkLed.setAttribute('fill', '#22c55e');
      if (spkCone) spkCone.setAttribute('stroke', '#a855f7');
      if (pwrTxt) {
        pwrTxt.textContent = 'NGUỒN PAM8403: TỰ BẬT PHÁT CHUÔNG (D7 + D3)';
        pwrTxt.setAttribute('fill', '#4ade80');
      }
      playHardwareSpeakerTone(1);
      logSerial('[PAM8403 D7+D3] Relay 2 tự bật nguồn 5V -> phát chuông PWM trên D3 -> tự ngắt sau 1.5s.', 'cmd');
      setTimeout(() => {
        if (devState.speaker_amp !== 'ON') {
          if (r2Led) r2Led.setAttribute('fill', '#450a0a');
          if (spkLed) spkLed.setAttribute('fill', '#334155');
          if (pwrTxt) {
            pwrTxt.textContent = 'NGUỒN PAM8403: ĐANG TẮT (Tự bật khi phát chuông)';
            pwrTxt.setAttribute('fill', '#94a3b8');
          }
        }
        if (spkCone) spkCone.setAttribute('stroke', '#64748b');
      }, 1500);
    }

    let RAW_ESP8266_INO = '';

    async function loadRealInoCode() {
      try {
        const res = await fetch('/api/wokwi_files', { credentials: 'same-origin' });
        if (!res.ok) {
          if (res.status === 401 || res.status === 403) {
            const pre = document.getElementById('inoCodePre');
            if (pre) pre.textContent = 'Vui lòng đăng nhập để xem mã nguồn ESP8266.';
          }
          return;
        }
        const data = await res.json();
        RAW_ESP8266_INO = data.esp8266_ino || data.sketch_ino || '';
        refreshInoCodePreview();
      } catch (e) {}
    }

    function getConfiguredInoText() {
      if (!RAW_ESP8266_INO) return '';
      const ssid = (document.getElementById('inpWifiSsid')?.value || 'TEN_WIFI_NHA_BAN').trim();
      const pass = (document.getElementById('inpWifiPass')?.value || 'MAT_KHAU_WIFI').trim();
      const host = (document.getElementById('inpServerIp')?.value || '192.168.1.100').trim();
      const escCpp = (s) => s.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
      return RAW_ESP8266_INO
        .replace(/const\s+char\*\s+WIFI_SSID\s*=\s*"[^"]*";/, () => `const char* WIFI_SSID     = "${escCpp(ssid)}";`)
        .replace(/const\s+char\*\s+WIFI_PASSWORD\s*=\s*"[^"]*";/, () => `const char* WIFI_PASSWORD = "${escCpp(pass)}";`)
        .replace(/const\s+char\*\s+SERVER_IP\s*=\s*"[^"]*";/, () => `const char* SERVER_IP     = "${escCpp(host)}";  // IP máy Laptop đang chạy Server (cổng 8088)`)
        .replace(/const\s+char\*\s+MQTT_SERVER\s*=\s*"[^"]*";/, () => `const char* MQTT_SERVER   = "${escCpp(host)}";`);
    }

    function refreshInoCodePreview() {
      const pre = document.getElementById('inoCodePre');
      if (pre && RAW_ESP8266_INO) {
        pre.textContent = getConfiguredInoText();
      }
    }

    async function copyConfiguredInoCode() {
      const txt = getConfiguredInoText();
      if (!txt) {
        await copyWokwiFile('sketch');
        return;
      }
      await navigator.clipboard.writeText(txt);
      logSerial('Đã copy toàn bộ code esp8266_smarthome.ino (kèm cấu hình Wi-Fi & IP Server) vào Clipboard!', 'cmd');
      alert('Đã copy toàn bộ code esp8266_smarthome.ino! Bạn mở Arduino IDE -> chọn mạch NodeMCU 1.0 (ESP-12E Module) -> Dán (Ctrl+V) và bấm Upload.');
    }

    async function copyWokwiFile(kind) {
      const res = await fetch('/api/wokwi_files', { credentials: 'same-origin' });
      if (!res.ok) {
        if (res.status === 401 || res.status === 403) {
          showWokwiAuthError('Vui lòng đăng nhập để sao chép sơ đồ và mã nguồn phần cứng.');
        }
        return;
      }
      const data = await res.json();
      const txt = kind === 'diagram' ? data.diagram_json : (getConfiguredInoText() || data.esp8266_ino || data.sketch_ino);
      await navigator.clipboard.writeText(txt);
      logSerial(`Đã copy ${kind === 'diagram' ? 'diagram.json' : 'esp8266_smarthome.ino'} vào Clipboard!`, 'cmd');
      if (kind === 'diagram') {
        alert('Đã sao chép diagram.json (NodeMCU ESP8266, khớp PCB 100×80mm)! Bạn có thể dán trực tiếp vào trình mô phỏng Wokwi.');
      } else {
        alert('Đã sao chép esp8266_smarthome.ino! Mở Arduino IDE và dán (Ctrl+V) để nạp vào mạch NodeMCU ESP8266.');
      }
    }

    const CIRCUIT_STAGE_BASE_W = 1220;
    const CIRCUIT_STAGE_BASE_H = 710;
    let _workbenchResizeObserver = null;

    function fitCircuitStageToWorkbench() {
      const scrollEl = document.getElementById('workbenchScroll') || document.querySelector('.workbench-scroll');
      const wrapEl = document.getElementById('circuitStageWrap');
      const stageEl = document.getElementById('circuitStage');
      if (!scrollEl || !wrapEl || !stageEl) return 1;

      const isMobile = typeof window !== 'undefined' && window.innerWidth <= 768;
      if (isMobile) {
        stageEl.style.transform = '';
        wrapEl.style.width = `${CIRCUIT_STAGE_BASE_W}px`;
        wrapEl.style.height = `${CIRCUIT_STAGE_BASE_H}px`;
        return 1;
      }

      const cs = typeof window !== 'undefined' && window.getComputedStyle ? window.getComputedStyle(scrollEl) : null;
      const padL = cs ? parseFloat(cs.paddingLeft) || 0 : 8;
      const padR = cs ? parseFloat(cs.paddingRight) || 0 : 8;
      const availW = Math.max(320, scrollEl.clientWidth - padL - padR);
      const scale = Math.min(1, availW / CIRCUIT_STAGE_BASE_W);

      stageEl.style.transformOrigin = 'top left';
      stageEl.style.transform = scale < 0.999 ? `scale(${scale.toFixed(4)})` : '';
      wrapEl.style.width = `${Math.floor(CIRCUIT_STAGE_BASE_W * scale)}px`;
      wrapEl.style.height = `${Math.ceil(CIRCUIT_STAGE_BASE_H * scale)}px`;
      return scale;
    }

    // Lắng nghe sự kiện xoay chiết áp <wokwi-potentiometer id="w_soil_pot">
    let _wokwiPageInitialized = false;
    function initWokwiPageOnce() {
      if (_wokwiPageInitialized) {
        fetchState();
        requestAnimationFrame(() => {
          drawWires();
          fitCircuitStageToWorkbench();
        });
        return;
      }
      _wokwiPageInitialized = true;
      buildNodeMCUPins();
      buildBreadboard400();
      drawWires();
      initWokwiWiringGuide();
      fitCircuitStageToWorkbench();
      setTimeout(() => {
        drawWires();
        fitCircuitStageToWorkbench();
      }, 250);
      if (typeof window !== 'undefined') {
        window.addEventListener('resize', fitCircuitStageToWorkbench);
        const scrollEl = document.getElementById('workbenchScroll') || document.querySelector('.workbench-scroll');
        if (scrollEl && typeof ResizeObserver === 'function' && !_workbenchResizeObserver) {
          _workbenchResizeObserver = new ResizeObserver(() => fitCircuitStageToWorkbench());
          _workbenchResizeObserver.observe(scrollEl);
        }
      }
      fetchState();

      const pot = document.getElementById('w_soil_pot');
      if (pot) {
        pot.addEventListener('input', (e) => {
          const val = Math.round((pot.value / 1023) * 90 + 5);
          document.getElementById('rngSoil').value = val;
          onSoilSlide(val);
          commitSoilSlide(val);
        });
      }

      let wokwiHttpPollTimer = null;
      window._stopWokwiHttpPolling = () => {
        if (wokwiHttpPollTimer) {
          clearInterval(wokwiHttpPollTimer);
          wokwiHttpPollTimer = null;
        }
      };
      const startWokwiHttpPolling = () => {
        const connDot = document.getElementById('wokwiConnDot');
        if (connDot) {
          connDot.textContent = 'Đồng bộ HTTP Cloud';
          connDot.classList.remove('offline');
        }
        if (!wokwiHttpPollTimer) {
          wokwiHttpPollTimer = setInterval(fetchState, 2000);
        }
      };

      const isLocal = isLocalWokwiHost();
      if (!isLocal) {
        startWokwiHttpPolling();
        logSerial('Đang chạy ở chế độ Đồng bộ HTTP Cloud (GET /api/state mỗi 2s).', 'cmd');
        return;
      }

      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = new WebSocket(`${proto}//${location.host}/ws`);
      ws.onerror = () => {
        startWokwiHttpPolling();
      };
      ws.onclose = () => {
        startWokwiHttpPolling();
      };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === 'state_snapshot' && msg.snapshot) {
            syncWokwiComponents(msg.snapshot);
          } else if (msg.type === 'device_updated' && msg.device_id && devState.hasOwnProperty(msg.device_id)) {
            const ctrl = getWokwiControl(msg.device_id);
            const msgVer = Number(msg.version || 0);
            const msgSeq = Number(msg.last_client_seq || 0);
            const msgRev = Number(msg.revision_seq || 0);
            const sameClient = Boolean(msg.last_client_id && msg.last_client_id === WOKWI_CLIENT_ID);
            const hasPending = ctrl.pendingCount > 0 || ctrl.debounceTimer !== null;
            if (
              msgVer > Number(ctrl.serverKnownVersion || 0) ||
              (msgRev > Number(ctrl.serverKnownRevisionSeq || 0) && msgVer >= Number(ctrl.serverKnownVersion || 0))
            ) {
              ctrl.serverKnownVersion = Math.max(Number(ctrl.serverKnownVersion || 0), msgVer);
              if (msgRev > 0) {
                ctrl.serverKnownRevisionSeq = Math.max(Number(ctrl.serverKnownRevisionSeq || 0), msgRev);
              }
              if (msg.new_state) {
                const nextKnownSt = String(msg.new_state).toUpperCase();
                ctrl.serverKnownState = nextKnownSt;
                ctrl.confirmedState = nextKnownSt;
              }
              if (hasPending && !(sameClient && msgSeq >= ctrl.seq)) {
                ctrl.needsServerKnownSync = true;
              }
            }
            const isStale =
              (msgRev > 0 && wokwiLastRevisionSeq > 0 && msgRev < wokwiLastRevisionSeq) ||
              (msgVer > 0 && ctrl.lastVersion > 0 && msgVer < ctrl.lastVersion) ||
              (sameClient && ctrl.lastConfirmedSeq > 0 && msgSeq > 0 && msgSeq < ctrl.lastConfirmedSeq && msgVer <= ctrl.lastVersion) ||
              (hasPending && !(sameClient && msgSeq >= ctrl.seq));
            if (!isStale && msg.new_state) {
              const nextSt = String(msg.new_state).toUpperCase();
              if (msgVer > ctrl.lastVersion) ctrl.lastVersion = msgVer;
              if (msgRev > wokwiLastRevisionSeq) wokwiLastRevisionSeq = msgRev;
              if (sameClient && msgSeq > ctrl.lastConfirmedSeq) {
                ctrl.lastConfirmedSeq = msgSeq;
                if (msgSeq > ctrl.seq) ctrl.seq = msgSeq;
              }
              ctrl.confirmedState = nextSt;
              if (!hasPending) {
                ctrl.desiredState = nextSt;
                ctrl.needsServerKnownSync = false;
              }
              applyWokwiSingleDeviceUI(msg.device_id, ctrl.desiredState);
            }
          } else if (msg.type === 'device_actuated') {
            fetchState();
          }
        } catch (e) {}
      };
    }
    if (document.readyState === 'loading') {
      window.addEventListener('DOMContentLoaded', initWokwiPageOnce);
    } else {
      initWokwiPageOnce();
    }
    window.addEventListener('smarthome:spa-navigated', (ev) => {
      if (ev && ev.detail && ev.detail.to === '/wokwi') {
        initWokwiPageOnce();
      } else if (window._stopWokwiHttpPolling) {
        window._stopWokwiHttpPolling();
      }
    });
  

// Window exports for inline event handlers
window.buildBreadboard400 = buildBreadboard400;
window.showHole = showHole;
window.clearHoleHover = clearHoleHover;
window.updateLiveTelemetryHeader = updateLiveTelemetryHeader;
window.buildNodeMCUPins = buildNodeMCUPins;
window.getElementPinXY = getElementPinXY;
window.drawWires = drawWires;
window.fitCircuitStageToWorkbench = fitCircuitStageToWorkbench;
window.filterStep = filterStep;
window.logSerial = logSerial;
window.playHardwareSpeakerTone = playHardwareSpeakerTone;
window.testSpeakerChimeDemo = testSpeakerChimeDemo;
window.triggerKy037SoundDemo = triggerKy037SoundDemo;
window.syncWokwiComponents = syncWokwiComponents;
window.formatHumanDeviceState = formatHumanDeviceState;
window.fetchState = fetchState;
window.toggleDevice = toggleDevice;
window.toggleWokwiServerMode = toggleWokwiServerMode;
window.setSimulationRunning = setSimulationRunning;
window.openTechSpecsPanel = openTechSpecsPanel;
window.onSoilSlide = onSoilSlide;
window.commitSoilSlide = commitSoilSlide;
window.onTempSlide = onTempSlide;
window.commitTempSlide = commitTempSlide;
window.loadRealInoCode = loadRealInoCode;
window.getConfiguredInoText = getConfiguredInoText;
window.refreshInoCodePreview = refreshInoCodePreview;
window.copyConfiguredInoCode = copyConfiguredInoCode;
window.copyWokwiFile = copyWokwiFile;
window.setWokwiDiagramMode = setWokwiDiagramMode;
window.onNodeMcuPinClick = onNodeMcuPinClick;
window.initWokwiWiringGuide = initWokwiWiringGuide;
