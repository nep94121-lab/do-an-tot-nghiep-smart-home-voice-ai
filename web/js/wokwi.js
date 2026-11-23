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
        html += `<g style="cursor:pointer" onmouseenter="showHole('ESP8266:${pL.label}', '${pL.desc}')">
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
        html += `<g style="cursor:pointer" onmouseenter="showHole('ESP8266:${pR.label}', '${pR.desc}')">
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

    function drawWires() {
      const svg = document.getElementById('wireLayer');
      const H = (holeId) => HOLE_MAP[holeId] || { x: 300, y: 100 };
      const P = (pinKey) => NODEMCU_PIN_MAP[pinKey] || { x: 200, y: 100 };

      const SERVO_PINS = {
        GND: getElementPinXY('w_servo', 'GND', 880, 92.0),
        VCC: getElementPinXY('w_servo', 'V+',  880, 101.5),
        PWM: getElementPinXY('w_servo', 'PWM', 880, 111.0)
      };

      function wirePath(points, color, dashed = false) {
        const d = points.map((p, idx) => `${idx === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
        const p0 = points[0];
        const pN = points[points.length - 1];
        const dashAttr = dashed ? `stroke-dasharray="6 4"` : '';
        return `
          <path d="${d}" fill="none" stroke="rgba(0,0,0,0.45)" stroke-width="5.2" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="${d}" fill="none" stroke="${color}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" ${dashAttr}/>
          <circle cx="${p0.x}" cy="${p0.y}" r="3.8" fill="#0f172a" stroke="${color}" stroke-width="1.8"/>
          <circle cx="${pN.x}" cy="${pN.y}" r="3.8" fill="#0f172a" stroke="${color}" stroke-width="1.8"/>
        `;
      }

      const groups = {
        // BƯỚC 0: CẤP NGUỒN 3.3V (Rãnh trên), 5V (Rãnh dưới) & GND CHUNG
        power: [
          wirePath([P('V33'), { x: 246, y: P('V33').y }, { x: 246, y: H('tp1').y }, H('tp1')], '#fb923c'),
          wirePath([P('VIN'), { x: 18, y: P('VIN').y }, { x: 18, y: 390 }, { x: H('bp1').x, y: 390 }, H('bp1')], '#ef4444'),
          wirePath([P('GND_R'), { x: 254, y: P('GND_R').y }, { x: 254, y: H('tn1').y }, H('tn1')], '#64748b'),
          wirePath([H('tn25'), { x: 775, y: H('tn25').y }, { x: 775, y: H('bn25').y }, H('bn25')], '#64748b')
        ],

        // BƯỚC 1: ĐÈN PHÒNG KHÁCH LED ĐỎ (Chân D0 / GPIO16)
        d0_living: [
          wirePath([P('D0'), { x: 258, y: P('D0').y }, { x: 258, y: H('c4').y }, H('c4')], '#22c55e'),
          wirePath([H('a9'), H('tn6')], '#64748b')
        ],

        // BƯỚC 2: CỬA CHÍNH SERVO SG90 (Chân D1 / GPIO5)
        d1_servo: [
          wirePath([P('D1'), { x: 238, y: P('D1').y }, { x: 238, y: 34 }, { x: 845, y: 34 }, { x: 845, y: SERVO_PINS.PWM.y }, SERVO_PINS.PWM], '#facc15'),
          wirePath([H('bp24'), { x: H('bp24').x, y: 348 }, { x: 798, y: 348 }, { x: 798, y: SERVO_PINS.VCC.y }, SERVO_PINS.VCC], '#ef4444'),
          wirePath([H('bn24'), { x: H('bn24').x, y: 356 }, { x: 808, y: 356 }, { x: 808, y: SERVO_PINS.GND.y }, SERVO_PINS.GND], '#78350f')
        ],

        // BƯỚC 3: CẢM BIẾN NHIỆT ĐỘ & ĐỘ ẨM DHT11 (Chân D2 / GPIO4)
        d2_dht11: [
          wirePath([P('D2'), { x: 264, y: P('D2').y }, { x: 264, y: H('j15').y }, H('j15')], '#06b6d4'),
          wirePath([H('f14'), { x: 468, y: H('f14').y }, { x: 468, y: H('tp9').y }, H('tp9')], '#fb923c'),
          wirePath([H('j17'), H('bn12')], '#64748b')
        ],

        // BƯỚC 4: RELAY 2 ĐỎ OPTO (D7) + MẠCH ÂM THANH D3 (R4 10k, C4 10µF 16V, R5/R6 2.2k, C5 10nF) + PAM8403 + LOA BẠC
        d3_d7_speaker: [
          wirePath([P('D3'), { x: 232, y: P('D3').y }, { x: 232, y: 196 }, { x: 464, y: 196 }, { x: 464, y: 128 }, { x: 482, y: 128 }], '#a855f7'),
          wirePath([H('tp10'), { x: 496, y: H('tp10').y }, { x: 496, y: 90 }], '#fb923c'),
          wirePath([{ x: 590, y: 172 }, { x: 590, y: 190 }, { x: 632, y: 190 }, { x: 632, y: H('tn18').y }, H('tn18')], '#64748b'),
          wirePath([{ x: 618, y: 128 }, { x: 626, y: 128 }, { x: 626, y: 196 }, { x: 240, y: 196 }, { x: 240, y: 404 }, { x: 180, y: 404 }, { x: 180, y: 486 }], '#c084fc'),
          wirePath([P('D7'), { x: 224, y: P('D7').y }, { x: 224, y: 396 }, { x: 46, y: 396 }, { x: 46, y: 486 }], '#c084fc'),
          wirePath([H('bp4'), { x: H('bp4').x, y: 372 }, { x: 78, y: 372 }, { x: 78, y: 486 }], '#ef4444'),
          wirePath([H('bn4'), { x: H('bn4').x, y: 380 }, { x: 102, y: 380 }, { x: 102, y: 486 }], '#64748b')
        ],

        // BƯỚC 5: ĐÈN PHÒNG NGỦ LED VÀNG ACTIVE-LOW TỪ 3.3V (Chân D4 / GPIO2, an toàn boot)
        d4_bedroom: [
          wirePath([H('tp20'), { x: H('tp20').x, y: H('a22').y }, H('a22')], '#fb923c'),
          wirePath([P('D4'), { x: 274, y: P('D4').y }, { x: 274, y: H('c26').y }, H('c26')], '#fde047')
        ],

        // BƯỚC 6: CẢM BIẾN ÂM THANH KY-037 DO (Chân D5 / GPIO14)
        d5_ky037: [
          wirePath([P('D5'), { x: 260, y: P('D5').y }, { x: 260, y: H('j6').y }, H('j6')], '#f87171'),
          wirePath([H('j7'), H('bn5')], '#64748b'),
          wirePath([H('f8'), H('tp6')], '#fb923c')
        ],

        // BƯỚC 7: RELAY 1 XANH + DIODE 1N4007 + TỤ 470µF + MÁY BƠM MINI (Chân D6 / GPIO12)
        d6_pump: [
          wirePath([P('D6'), { x: 270, y: P('D6').y }, { x: 270, y: 384 }, { x: 815, y: 384 }, { x: 815, y: 290 }, { x: 858, y: 290 }], '#38bdf8'),
          wirePath([H('bp22'), { x: H('bp22').x, y: 392 }, { x: 825, y: 392 }, { x: 825, y: 314 }, { x: 858, y: 314 }], '#ef4444'),
          wirePath([H('bn22'), { x: H('bn22').x, y: 402 }, { x: 832, y: 402 }, { x: 832, y: 302 }, { x: 858, y: 302 }], '#64748b')
        ],

        // BƯỚC 8: CÒI BÁO ĐỘNG BUZZER 5V QUA MẠCH LÁI NPN Q1 S8050 + R10 1k + R9 10k KÉO GND + D2 1N4007 (KHÔNG NỐI TRỰC TIẾP D8 → CÒI)
        d8_buzzer: [
          wirePath([P('D8'), { x: 284, y: P('D8').y }, { x: 284, y: 344 }, { x: 564, y: 344 }, { x: 564, y: 250 }, { x: 582, y: 250 }], '#f43f5e'),
          wirePath([{ x: 632, y: 316 }, { x: 632, y: H('bn18').y }, H('bn18')], '#64748b'),
          wirePath([{ x: 706, y: 242 }, { x: 722, y: 242 }, { x: 722, y: 278 }, { x: 732.7, y: 278 }, { x: 732.7, y: 270.1 }], '#f97316'),
          wirePath([H('bp23'), { x: 754, y: H('bp23').y }, { x: 754, y: 278 }, { x: 738.9, y: 278 }, { x: 738.9, y: 270.1 }], '#ef4444'),
          wirePath([{ x: 754, y: 278 }, { x: 754, y: 226 }, { x: 706, y: 226 }], '#ef4444')
        ],

        // BƯỚC 9: CẢM BIẾN ĐỘ ẨM ĐẤT + MẠCH LM393 NGUỒN 3.3V (Chân A0 / ADC0)
        a0_soil: [
          wirePath([P('A0'), { x: 10, y: P('A0').y }, { x: 10, y: 665 }, { x: 872, y: 665 }, { x: 872, y: 575 }], '#eab308'),
          wirePath([H('tp24'), { x: 785, y: H('tp24').y }, { x: 785, y: 595 }, { x: 922, y: 595 }, { x: 922, y: 575 }], '#fb923c'),
          wirePath([H('bn20'), { x: H('bn20').x, y: 645 }, { x: 906, y: 645 }, { x: 906, y: 575 }], '#64748b')
        ]
      };

      svg.innerHTML = Object.entries(groups)
        .map(([k, arr]) => `<g id="wg_${k}" class="w-group">${arr.join('')}</g>`)
        .join('');
    }

    // =========================================================================
    // 3. BỘ LỌC HƯỚNG DẪN TỪNG BƯỚC CẮM DÂY VẬT LÝ (10 CHÂN KHÓA CỨNG)
    // =========================================================================
    const GUIDES = {
      all: [
        "<strong>Bước 0 (Cấp nguồn trước tiên):</strong> Cắm dây Cam từ chân <span class='hole-badge'>3V3</span> vào lỗ <span class='hole-badge'>TP1 (Rãnh + Trên)</span>; dây Đỏ từ <span class='hole-badge'>VIN (5V)</span> vào <span class='hole-badge'>BP1 (Rãnh + Dưới)</span>; dây Đen từ <span class='hole-badge'>GND</span> vào <span class='hole-badge'>BN1 &amp; TN25</span>.",
        "<strong>Cắm linh kiện đúng mạch PCB Hub 100×80 mm:</strong> Đèn Khách (<span class='hole-badge'>D0</span> qua R1 220Ω), âm thanh (<span class='hole-badge'>D3</span> qua R4 10kΩ + C4 10µF 16V + R5/R6 2.2kΩ + C5 10nF), Đèn Ngủ Active-LOW (<span class='hole-badge'>D4</span> qua R2 220Ω + R7 10kΩ), KY-037 (<span class='hole-badge'>D5</span>), DHT11 (<span class='hole-badge'>D2</span> + R3 10kΩ) và Còi 5V (<span class='hole-badge'>D8</span> qua R9 10kΩ kéo GND + R10 1kΩ → Q1 S8050 + D2 1N4007)."
      ],
      power: [
        "<strong>Dây Cam (+3.3V nuôi Cảm biến &amp; LED ngủ):</strong> Từ chân <span class='hole-badge'>3V3</span> cắm vào lỗ <span class='hole-badge'>TP1</span> (nuôi DHT11, KY-037, LM393 đất &amp; cực dương LED D4).",
        "<strong>Dây Đỏ (+5V nuôi Servo, Relay 1, Relay 2 &amp; Còi 5V):</strong> Từ chân <span class='hole-badge'>VIN</span> cắm vào lỗ <span class='hole-badge'>BP1</span> (kèm tụ lọc C1/C2 470µF 16V, C3 100nF và LED nguồn D3 qua R8 1kΩ).",
        "<strong>2 Dây Đen (Mass chung GND):</strong> Nối từ <span class='hole-badge'>GND</span> vào <span class='hole-badge'>BN1</span> và nối thông <span class='hole-badge'>BN25</span> lên <span class='hole-badge'>TN25</span>."
      ],
      d0_living: [
        "<strong>Đèn Phòng Khách (Chân D0 / GPIO16):</strong> Từ chân <span class='hole-badge'>D0</span> cắm dây Xanh lá vào lỗ <span class='hole-badge'>C4</span> → qua trở <span class='hole-badge'>R1 220Ω</span> sang LED Đỏ (+) tại <span class='hole-badge'>C8</span>, chân (-) ở <span class='hole-badge'>C9</span>.",
        "<strong>Nối Mass &amp; nháy báo thu âm:</strong> Nối <span class='hole-badge'>A9</span> lên rãnh âm <span class='hole-badge'>TN6</span>. Chân D0 cũng dùng để nháy báo hiệu 3-2-1 khi thu âm cấp quyền."
      ],
      d1_servo: [
        "<strong>Dây Vàng/Cam của Servo SG90 (PWM):</strong> Cắm thẳng vào chân <span class='hole-badge'>D1 (GPIO5)</span> của ESP8266 (0° đóng / 90° mở).",
        "<strong>Dây Đỏ (+5V) &amp; Nâu (GND):</strong> Cắm lần lượt vào <span class='hole-badge'>BP24</span> (kèm tụ lọc C1 470µF 16V) và <span class='hole-badge'>BN24</span>."
      ],
      d2_dht11: [
        "<strong>Cắm cảm biến DHT11 vào hàng F (Cột 14 → 17):</strong> Chân VCC ở <span class='hole-badge'>F14</span>, chân DATA ở <span class='hole-badge'>F15</span> (kèm điện trở kéo lên <span class='hole-badge'>R3 10kΩ</span> lên +3.3V như trên PCB), chân GND ở <span class='hole-badge'>F17</span>.",
        "<strong>Đi dây:</strong> Lỗ <span class='hole-badge'>J15</span> nối về chân <span class='hole-badge'>D2 (GPIO4)</span>; lỗ <span class='hole-badge'>F14</span> nối lên <span class='hole-badge'>TP12 (+3.3V)</span>; lỗ <span class='hole-badge'>J17</span> nối xuống <span class='hole-badge'>BN12 (GND)</span>."
      ],
      d3_d7_speaker: [
        "<strong>Relay 2 Đỏ Opto (Chân D7 / GPIO13):</strong> Đặt jumper vàng về mức <span class='hole-badge'>H</span>; chân <span class='hole-badge'>IN</span> nối <span class='hole-badge'>D7</span>, <span class='hole-badge'>COM</span> nối <span class='hole-badge'>+5V</span> và <span class='hole-badge'>NO</span> cấp nguồn +5V (lọc bởi <span class='hole-badge'>C6 100nF</span>) cho mạch xanh <span class='hole-badge'>PAM8403</span>.",
        "<strong>Ngõ ra âm thanh PWM (Chân D3 / GPIO0):</strong> Gắn <span class='hole-badge'>R4 10kΩ</span> kéo lên <span class='hole-badge'>+3.3V</span> (an toàn boot), nối <span class='hole-badge'>D3</span> qua tụ chặn DC <span class='hole-badge'>C4 10µF 16V</span> → cầu phân áp <span class='hole-badge'>R5/R6 2.2kΩ</span> + tụ lọc <span class='hole-badge'>C5 10nF</span> xuống GND tới chân <span class='hole-badge'>L</span> của PAM8403; 2 dây loa bạc nối vào <span class='hole-badge'>L OUT + / -</span>."
      ],
      d4_bedroom: [
        "<strong>Đấu Active-LOW an toàn boot trên D4 (GPIO2):</strong> Nối từ <span class='hole-badge'>TP20 (+3.3V)</span> qua trở <span class='hole-badge'>R2 220Ω</span> tại <span class='hole-badge'>A22</span> vào cực dương (+) LED Vàng, cực âm (-) ở <span class='hole-badge'>C26</span> nối về <span class='hole-badge'>D4 (GPIO2)</span> kèm trở kéo lên <span class='hole-badge'>R7 10kΩ</span> lên +3.3V.",
        "<strong>Nguyên tắc boot:</strong> Cách đấu này đảm bảo chân <span class='hole-badge'>GPIO2</span> luôn ở mức HIGH khi reset (khớp <code>BEDROOM_LED_ACTIVE_LOW = true</code>)."
      ],
      d5_ky037: [
        "<strong>Cảm biến Âm thanh KY-037 (Chân D5 / GPIO14):</strong> Theo thứ tự chân trên PCB đỏ (<span class='hole-badge'>DO | G | + | AO</span>), cắm nguồn <span class='hole-badge'>+</span> vào <span class='hole-badge'>TP6 (+3.3V)</span> và <span class='hole-badge'>G</span> vào <span class='hole-badge'>BN5 (GND)</span>.",
        "<strong>Tín hiệu số DO:</strong> Nối chân <span class='hole-badge'>DO</span> về <span class='hole-badge'>D5 (GPIO14)</span> để bắt xung vỗ tay (chống dội ≥400ms). Voice AI Gemini dùng micro/loa trên Web/App."
      ],
      d6_pump: [
        "<strong>Relay 1 Xanh dương (Chân D6 / GPIO12):</strong> Nối chân <span class='hole-badge'>IN</span> về <span class='hole-badge'>D6</span>; <span class='hole-badge'>VCC</span> &amp; <span class='hole-badge'>COM</span> vào <span class='hole-badge'>BP22 (+5V)</span>; <span class='hole-badge'>GND</span> vào <span class='hole-badge'>BN22</span>.",
        "<strong>Bảo vệ Máy bơm trắng:</strong> Kẹp song song ngược cực con <strong>Diode D1 1N4007</strong> (vạch bạc quay về phía dây + bơm) và đặt tụ <strong>C2 470µF 16V</strong> sát đường 5V cấp bơm."
      ],
      d8_buzzer: [
        "<strong>Còi báo động Buzzer 5V (Chân D8 / GPIO15 — đúng PCB):</strong> Tuyệt đối KHÔNG nối trực tiếp còi vào D8. Đi theo đúng đường lái NPN low-side: <span class='hole-badge'>D8</span> → <span class='hole-badge'>R10 (1kΩ)</span> → cực Base (B) transistor <span class='hole-badge'>Q1 (S8050 NPN)</span>, cực Emitter (E) nối <span class='hole-badge'>GND</span>, cực dương còi <span class='hole-badge'>Buzzer(+)</span> nối <span class='hole-badge'>+5V</span>, cực âm <span class='hole-badge'>Buzzer(-)</span> nối cực Collector (C) của Q1, kẹp diode dập xung <span class='hole-badge'>D2 (1N4007)</span> song song 2 cực còi (Cathode về +5V, Anode về Q1.C).",
        "<strong>An toàn boot bắt buộc trên D8:</strong> Luôn gắn điện trở kéo xuống <span class='hole-badge'>R9 (10kΩ)</span> từ <span class='hole-badge'>D8 → GND</span> để GPIO15 giữ mức LOW khi khởi động và còi im lặng tuyệt đối (không gắn kéo lên 3.3V)."
      ],
      a0_soil: [
        "<strong>Cảm biến Độ ẩm Đất (Chân A0 / ADC0):</strong> Cấp nguồn <span class='hole-badge'>VCC</span> của mạch xanh <code>LM393</code> vào <span class='hole-badge'>TP24 (+3.3V)</span> để bảo vệ ngõ vào A0 (≤3.3V), lọc nhiễu bằng tụ <span class='hole-badge'>C7 100nF</span> xuống GND và nối <span class='hole-badge'>GND</span> vào <span class='hole-badge'>BN20</span>.",
        "<strong>Đọc Analog &amp; Tự tưới:</strong> Nối <span class='hole-badge'>AO</span> về <span class='hole-badge'>A0</span>. Tự động bật Relay 1 bơm (<span class='hole-badge'>D6</span>) khi độ ẩm &lt;40% và tắt khi ≥70%."
      ]
    };

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

      const items = GUIDES[stepKey] || GUIDES.all;
      document.getElementById('guideItems').innerHTML = items.map(i => `<li>${i}</li>`).join('');
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
