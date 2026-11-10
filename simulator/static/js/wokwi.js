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
        { key: 'A0',    label: 'A0',  active: '#facc15', desc: 'Chân số 1 Trái: A0 (ADC0) — Cảm biến Độ ẩm Đất YL-69' },
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
        { key: 'D0',    label: 'D0',  active: null,      desc: 'Chân số 1 Phải: D0 (GPIO16)' },
        { key: 'D1',    label: 'D1',  active: '#facc15', desc: 'Chân số 2 Phải: D1 (GPIO5) — Cửa chính Servo SG90' },
        { key: 'D2',    label: 'D2',  active: '#22c55e', desc: 'Chân số 3 Phải: D2 (GPIO4) — Đèn Khách LED Đỏ + Phát IR 38kHz' },
        { key: 'D3',    label: 'D3',  active: '#38bdf8', desc: 'Chân số 4 Phải: D3 (GPIO0) — Relay Đỏ + Máy Bơm Nước Mini' },
        { key: 'D4',    label: 'D4',  active: '#38bdf8', desc: 'Chân số 5 Phải: D4 (GPIO2) — Phát âm thanh ra Loa 8Ω 3W (PAM8403)' },
        { key: 'V33',   label: '3V3', active: '#fb923c', desc: 'Chân số 6 Phải: 3V3 — Cấp nguồn +3.3V sang Rãnh Trên Breadboard' },
        { key: 'GND_R', label: 'GND', active: '#94a3b8', desc: 'Chân số 7 Phải: GND — Cấp Mass chung sang Breadboard' },
        { key: 'D5',    label: 'D5',  active: '#c084fc', desc: 'Chân số 8 Phải: D5 (GPIO14) — Mắt thu hồng ngoại VS1838B' },
        { key: 'D6',    label: 'D6',  active: '#06b6d4', desc: 'Chân số 9 Phải: D6 (GPIO12) — Cảm biến Nhiệt độ & Độ ẩm DHT11' },
        { key: 'D7',    label: 'D7',  active: '#fde047', desc: 'Chân số 10 Phải: D7 (GPIO13) — Đèn Phòng Ngủ LED Vàng' },
        { key: 'D8',    label: 'D8',  active: '#f43f5e', desc: 'Chân số 11 Phải: D8 (GPIO15) — Còi báo động Buzzer 5V' },
        { key: 'RX',    label: 'RX',  active: '#34d399', desc: 'Chân số 12 Phải: RX (GPIO3) — Nhận lệnh từ Module Micro Thu Âm Giọng Nói (VC-02 / MAX9814)' },
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
          // Chân 3V3 (Chân số 6 bên phải NodeMCU) -> lỗ tp1 (Rãnh Dương Trên +3.3V)
          wirePath([P('V33'), { x: 246, y: P('V33').y }, { x: 246, y: H('tp1').y }, H('tp1')], '#fb923c'),
          // Chân VIN (Chân số 15 cuối bên trái NodeMCU) -> lỗ bp1 (Rãnh Dương Dưới +5V)
          wirePath([P('VIN'), { x: 18, y: P('VIN').y }, { x: 18, y: 390 }, { x: H('bp1').x, y: 390 }, H('bp1')], '#ef4444'),
          // Chân GND (Chân số 7 bên phải NodeMCU) -> lỗ tn1 (Rãnh Âm Trên GND) & nối thông xuống bn25
          wirePath([P('GND_R'), { x: 254, y: P('GND_R').y }, { x: 254, y: H('tn1').y }, H('tn1')], '#64748b'),
          wirePath([H('tn25'), { x: 775, y: H('tn25').y }, { x: 775, y: H('bn25').y }, H('bn25')], '#64748b')
        ],

        // BƯỚC 1: CỬA CHÍNH SERVO SG90 (Chân D1 — Chân số 2 bên phải NodeMCU)
        d1_servo: [
          wirePath([P('D1'), { x: 238, y: P('D1').y }, { x: 238, y: 34 }, { x: 845, y: 34 }, { x: 845, y: SERVO_PINS.PWM.y }, SERVO_PINS.PWM], '#facc15'),
          wirePath([H('bp24'), { x: H('bp24').x, y: 348 }, { x: 798, y: 348 }, { x: 798, y: SERVO_PINS.VCC.y }, SERVO_PINS.VCC], '#ef4444'),
          wirePath([H('bn24'), { x: H('bn24').x, y: 356 }, { x: 808, y: 356 }, { x: 808, y: SERVO_PINS.GND.y }, SERVO_PINS.GND], '#78350f')
        ],

        // BƯỚC 2: ĐÈN PHÒNG KHÁCH LED ĐỎ + PHÁT IR 940NM (Chân D2 — Chân số 3 bên phải NodeMCU)
        d2_light_ir: [
          wirePath([P('D2'), { x: 262, y: P('D2').y }, { x: 262, y: H('c4').y }, H('c4')], '#22c55e'),
          wirePath([H('b4'), { x: H('b4').x, y: H('b12').y }, H('c12')], '#a855f7'),
          wirePath([H('a9'), H('tn6')], '#64748b'),
          wirePath([H('a16'), H('tn11')], '#64748b')
        ],

        // BƯỚC 3: MODULE RELAY ĐỎ + MÁY BƠM NƯỚC MINI + DIODE 1N4007 (Chân D3 — Chân số 4 bên phải NodeMCU)
        d3_pump: [
          wirePath([P('D3'), { x: 270, y: P('D3').y }, { x: 270, y: 382 }, { x: 815, y: 382 }, { x: 815, y: 290 }, { x: 858, y: 290 }], '#38bdf8'),
          wirePath([H('bp22'), { x: H('bp22').x, y: 392 }, { x: 825, y: 392 }, { x: 825, y: 314 }, { x: 858, y: 314 }], '#ef4444'),
          wirePath([H('bn22'), { x: H('bn22').x, y: 402 }, { x: 832, y: 402 }, { x: 832, y: 302 }, { x: 858, y: 302 }], '#64748b')
        ],

        // BƯỚC 4: CẢM BIẾN ĐỘ ẨM ĐẤT YL-69 + MẠCH LM393 (Chân A0 — Chân số 1 trên cùng bên trái NodeMCU)
        a0_soil: [
          wirePath([P('A0'), { x: 10, y: P('A0').y }, { x: 10, y: 665 }, { x: 872, y: 665 }, { x: 872, y: 575 }], '#eab308'),
          wirePath([H('tp24'), { x: 785, y: H('tp24').y }, { x: 785, y: 595 }, { x: 922, y: 595 }, { x: 922, y: 575 }], '#fb923c'),
          wirePath([H('bn20'), { x: H('bn20').x, y: 645 }, { x: 906, y: 645 }, { x: 906, y: 575 }], '#64748b')
        ],

        // BƯỚC 5: MẮT THU HỒNG NGOẠI VS1838B 38KHZ (Chân D5 — Chân số 8 bên phải NodeMCU)
        d5_ir_rx: [
          wirePath([P('D5'), { x: 260, y: P('D5').y }, { x: 260, y: H('j6').y }, H('j6')], '#c084fc'),
          wirePath([H('j7'), H('bn5')], '#64748b'),
          wirePath([H('f8'), H('tp6')], '#fb923c')
        ],

        // BƯỚC 6: CẢM BIẾN NHIỆT ĐỘ & ĐỘ ẨM DHT11 (Chân D6 — Chân số 9 bên phải NodeMCU)
        d6_dht11: [
          wirePath([P('D6'), { x: 268, y: P('D6').y }, { x: 268, y: H('j15').y }, H('j15')], '#06b6d4'),
          wirePath([H('f14'), H('tp12')], '#fb923c'),
          wirePath([H('j17'), H('bn12')], '#64748b')
        ],

        // BƯỚC 7: ĐÈN PHÒNG NGỦ LED VÀNG + TRỞ 220Ω (Chân D7 — Chân số 10 bên phải NodeMCU)
        d7_bed: [
          wirePath([P('D7'), { x: 276, y: P('D7').y }, { x: 276, y: H('c22').y }, H('c22')], '#facc15'),
          wirePath([H('a26'), H('tn20')], '#64748b')
        ],

        // BƯỚC 8: CÒI BÁO ĐỘNG BUZZER 5V (Chân D8 — Chân số 11 bên phải NodeMCU)
        d8_buzzer: [
          wirePath([P('D8'), { x: 284, y: P('D8').y }, { x: 284, y: H('j25').y }, H('j25')], '#f43f5e'),
          wirePath([H('j24'), H('bn19')], '#64748b')
        ],

        // BƯỚC 9: CỤM MICRO THU ÂM GIỌNG NÓI (Chân RX) & LOA PHÁT 8Ω 3W (Chân D4)
        rx_d4_mic_spk: [
          // Dây Xanh ngọc từ chân RX (GPIO3) -> chân MIC_OUT của Module Micro
          wirePath([P('RX'), { x: 224, y: P('RX').y }, { x: 224, y: 398 }, { x: 84, y: 398 }, { x: 84, y: 580 }], '#34d399'),
          // Dây Xanh lam từ chân D4 (GPIO2) -> chân SPK_IN của Mạch khuếch đại Loa PAM8403
          wirePath([P('D4'), { x: 232, y: P('D4').y }, { x: 232, y: 404 }, { x: 128, y: 404 }, { x: 128, y: 580 }], '#38bdf8'),
          // Nguồn +3.3V (TP4), +5V (BP4) & Mass GND (BN4) nuôi Cụm Mic & Loa
          wirePath([H('tp4'), { x: H('tp4').x, y: 372 }, { x: 172, y: 372 }, { x: 172, y: 580 }], '#fb923c'),
          wirePath([H('bp4'), { x: H('bp4').x, y: 368 }, { x: 216, y: 368 }, { x: 216, y: 580 }], '#ef4444'),
          wirePath([H('bn4'), { x: H('bn4').x, y: 376 }, { x: 260, y: 376 }, { x: 260, y: 580 }], '#64748b')
        ]
      };

      svg.innerHTML = Object.entries(groups)
        .map(([k, arr]) => `<g id="wg_${k}" class="w-group">${arr.join('')}</g>`)
        .join('');
    }

    // =========================================================================
    // 3. BỘ LỌC HƯỚNG DẪN TỪNG BƯỚC CẮM DÂY VẬT LÝ
    // =========================================================================
    const GUIDES = {
      all: [
        "<strong>Bước 0 (Cấp nguồn trước tiên):</strong> Cắm dây Cam từ chân <span class='hole-badge'>3V3</span> vào lỗ <span class='hole-badge'>TP1 (Rãnh + Trên)</span>; dây Đỏ từ chân <span class='hole-badge'>VIN (5V)</span> vào lỗ <span class='hole-badge'>BP1 (Rãnh + Dưới)</span>; dây Đen từ <span class='hole-badge'>GND</span> vào <span class='hole-badge'>BN1 &amp; TN25</span>.",
        "<strong>Cắm linh kiện lên đúng cột Breadboard:</strong> Đèn Khách + Trở 220Ω ở <span class='hole-badge'>Cột 4 → 9</span>; Mạch phát IR + Transistor ở <span class='hole-badge'>Cột 12 → 18</span>; Đèn Ngủ ở <span class='hole-badge'>Cột 22 → 26</span>; VS1838B ở <span class='hole-badge'>Cột 6–8</span>; DHT11 ở <span class='hole-badge'>Cột 14–17</span>; Buzzer ở <span class='hole-badge'>Cột 24–26</span>."
      ],
      power: [
        "<strong>Dây Cam (+3.3V nuôi Cảm biến):</strong> Từ chân <span class='hole-badge'>3V3</span> của ESP8266 cắm vào lỗ <span class='hole-badge'>TP1</span> (Rãnh Dương ngang phía TRÊN Breadboard).",
        "<strong>Dây Đỏ (+5V nuôi Servo, Relay &amp; Máy bơm):</strong> Từ chân <span class='hole-badge'>VIN</span> của ESP8266 cắm vào lỗ <span class='hole-badge'>BP1</span> (Rãnh Dương ngang phía DƯỚI Breadboard).",
        "<strong>2 Dây Đen (Mass chung GND):</strong> Từ chân <span class='hole-badge'>GND</span> cắm vào lỗ <span class='hole-badge'>BN1</span>, và lấy 1 sợi dây Đen nối từ <span class='hole-badge'>BN25</span> lên <span class='hole-badge'>TN25</span>."
      ],
      d1_servo: [
        "<strong>Dây Vàng/Cam của Servo SG90 (PWM):</strong> Cắm thẳng vào chân <span class='hole-badge'>D1 (GPIO5)</span> của ESP8266.",
        "<strong>Dây Đỏ của Servo (+5V):</strong> Cắm vào lỗ <span class='hole-badge'>BP24</span> (Rãnh +5V phía dưới Breadboard).",
        "<strong>Dây Nâu của Servo (GND):</strong> Cắm vào lỗ <span class='hole-badge'>BN24</span> (Rãnh -GND phía dưới Breadboard)."
      ],
      d2_light_ir: [
        "<strong>Dây tín hiệu D2:</strong> Từ chân <span class='hole-badge'>D2 (GPIO4)</span> cắm vào lỗ <span class='hole-badge'>E4</span>. Cắm 1 con <strong>Điện trở 220Ω</strong> từ lỗ <span class='hole-badge'>D4</span> sang lỗ <span class='hole-badge'>D8</span>.",
        "<strong>Bóng LED Đỏ Phòng Khách:</strong> Chân dài (+) cắm vào lỗ <span class='hole-badge'>C8</span>, chân ngắn (-) cắm vào lỗ <span class='hole-badge'>C9</span>, rồi nối dây Đen từ <span class='hole-badge'>A9</span> lên rãnh âm <span class='hole-badge'>TN6</span>.",
        "<strong>Nhánh phát Hồng ngoại (IR 940nm + Transistor đen):</strong> Nối dây từ <span class='hole-badge'>D4</span> sang <span class='hole-badge'>E12</span> → qua <strong>Trở 1kΩ</strong> vào chân giữa Transistor ở <span class='hole-badge'>D15</span>."
      ],
      d3_pump: [
        "<strong>Dây kích Relay (Xanh dương):</strong> Từ chân <span class='hole-badge'>D3 (GPIO0)</span> cắm vào chân <span class='hole-badge'>IN</span> của Module Relay Đỏ; chân <span class='hole-badge'>DC+</span> cắm vào lỗ <span class='hole-badge'>BP22 (+5V)</span>; chân <span class='hole-badge'>DC-</span> cắm vào lỗ <span class='hole-badge'>BN22 (GND)</span>.",
        "<strong>Đấu Máy bơm nước mini trắng &amp; Diode 1N4007:</strong> Dây Đỏ (+) của Máy bơm vặn vào cổng <span class='hole-badge'>NO</span> của Relay; cổng <span class='hole-badge'>COM</span> nối vào +5V; kẹp song song con <strong>Diode 1N4007 (vạch trắng quay về phía dây Đỏ của Bơm)</strong>."
      ],
      a0_soil: [
        "<strong>Dây tín hiệu Analog (Vàng):</strong> Từ chân <span class='hole-badge'>A0</span> (góc trên bên trái ESP8266) cắm vào chân <span class='hole-badge'>AO</span> của mạch xanh <code>LM393</code>.",
        "<strong>Dây nguồn cảm biến đất:</strong> Chân <span class='hole-badge'>VCC</span> của <code>LM393</code> cắm vào lỗ <span class='hole-badge'>TP24 (+3.3V)</span>; chân <span class='hole-badge'>GND</span> cắm vào lỗ <span class='hole-badge'>BN20 (GND)</span>."
      ],
      d5_ir_rx: [
        "<strong>Cắm 3 chân mắt thu VS1838B vào hàng F (Cột 6, 7, 8):</strong> Chân trái (OUT) ở <span class='hole-badge'>F6</span>, chân giữa (GND) ở <span class='hole-badge'>F7</span>, chân phải (VCC) ở <span class='hole-badge'>F8</span>.",
        "<strong>Đi dây:</strong> Lỗ <span class='hole-badge'>J6</span> nối về chân <span class='hole-badge'>D5 (GPIO14)</span>; lỗ <span class='hole-badge'>J7</span> nối xuống <span class='hole-badge'>BN5 (GND)</span>; lỗ <span class='hole-badge'>F8</span> nối lên <span class='hole-badge'>TP6 (+3.3V)</span>."
      ],
      d6_dht11: [
        "<strong>Cắm cảm biến DHT11 vào hàng F (Cột 14 → 17):</strong> Chân VCC ở <span class='hole-badge'>F14</span>, chân DATA ở <span class='hole-badge'>F15</span>, chân GND ở <span class='hole-badge'>F17</span>.",
        "<strong>Đi dây:</strong> Lỗ <span class='hole-badge'>J15</span> nối về chân <span class='hole-badge'>D6 (GPIO12)</span>; lỗ <span class='hole-badge'>F14</span> nối lên <span class='hole-badge'>TP12 (+3.3V)</span>; lỗ <span class='hole-badge'>J17</span> nối xuống <span class='hole-badge'>BN12 (GND)</span>."
      ],
      d7_bed: [
        "<strong>Đèn Phòng Ngủ (Chân D7):</strong> Từ chân <span class='hole-badge'>D7 (GPIO13)</span> cắm dây vàng vào lỗ <span class='hole-badge'>E22</span> → qua <strong>Điện trở 220Ω</strong> sang lỗ <span class='hole-badge'>E25</span>.",
        "<strong>Bóng LED Vàng:</strong> Chân dài (+) cắm vào <span class='hole-badge'>C25</span>, chân ngắn (-) cắm vào <span class='hole-badge'>C26</span>, nối <span class='hole-badge'>A26</span> lên <span class='hole-badge'>TN20 (GND)</span>."
      ],
      d8_buzzer: [
        "<strong>Còi báo động Buzzer 5V (Chân D8):</strong> Cắm 2 chân Còi vào lỗ <span class='hole-badge'>F24 (-)</span> và <span class='hole-badge'>F26 (+)</span>.",
        "<strong>Đi dây:</strong> Lỗ <span class='hole-badge'>J26 (+)</span> nối về chân <span class='hole-badge'>D8 (GPIO15)</span>; lỗ <span class='hole-badge'>J24 (-)</span> nối xuống <span class='hole-badge'>BN19 (GND)</span>."
      ],
      rx_d4_mic_spk: [
        "<strong>Micro Thu Âm Giọng Nói (Module VC-02 Offline ASR / MAX9814):</strong> Chân tín hiệu <span class='hole-badge'>TX/OUT</span> của Mic cắm dây Xanh ngọc về chân <span class='hole-badge'>RX (GPIO3)</span> (Chân số 12 bên phải ESP8266); chân <span class='hole-badge'>VCC</span> vào lỗ <span class='hole-badge'>TP4 (+3.3V)</span>; chân <span class='hole-badge'>GND</span> vào lỗ <span class='hole-badge'>BN4</span>.",
        "<strong>Mạch Khuếch Đại PAM8403 + Loa Phát 8Ω 3W:</strong> Chân tín hiệu âm thanh <span class='hole-badge'>IN+</span> cắm dây Xanh lam về chân <span class='hole-badge'>D4 (GPIO2)</span> (Chân số 5 bên phải ESP8266); nguồn <span class='hole-badge'>+5V</span> cắm vào lỗ <span class='hole-badge'>BP4 (Rãnh +5V Dưới)</span>; chân <span class='hole-badge'>GND</span> vào lỗ <span class='hole-badge'>BN4</span>."
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
      ac: 'OFF',
      fan: 'OFF',
      alarm_siren: 'OFF',
      garden_pump: 'OFF'
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

    function getWokwiControl(devId) {
      if (!wokwiControlState[devId]) {
        const initSt = devState[devId] || 'OFF';
        wokwiControlState[devId] = {
          seq: 0,
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

    function syncWokwiComponents(snap) {
      if (!snap || !snap.devices) return;
      window._wokwiServerConnected = snap.server_connected !== false;

      const connDot = document.getElementById('wokwiConnDot');
      if (connDot) {
        connDot.textContent = window._wokwiServerConnected ? 'Đã kết nối' : 'Mất kết nối';
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

      if (Array.isArray(snap.devices)) {
        for (const d of snap.devices) {
          if (d && d.id && devState.hasOwnProperty(d.id)) {
            const ctrl = getWokwiControl(d.id);
            const srvSeq = Number(d.last_client_seq || 0);
            if ((ctrl.pendingCount > 0 || ctrl.debounceTimer !== null) && srvSeq < ctrl.seq) {
              devState[d.id] = ctrl.desiredState;
            } else if (ctrl.seq > 0 && srvSeq > 0 && srvSeq < ctrl.seq) {
              devState[d.id] = ctrl.desiredState;
            } else {
              devState[d.id] = d.state;
              ctrl.confirmedState = d.state;
              ctrl.desiredState = d.state;
            }
          }
        }
      } else {
        for (const k of Object.keys(devState)) {
          if (snap.devices[k]) devState[k] = snap.devices[k].state;
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

      // 2. <wokwi-led id="w_led_living"> (Chân D2)
      const ledLiv = document.getElementById('w_led_living');
      if (ledLiv) ledLiv.value = (devState.living_room_light === 'ON');

      // 3. <wokwi-led id="w_led_bedroom"> (Chân D7)
      const ledBed = document.getElementById('w_led_bedroom');
      if (ledBed) ledBed.value = (devState.bedroom_light === 'ON');

      // 4. <wokwi-buzzer id="w_buzzer"> (Chân D8)
      const buzEl = document.getElementById('w_buzzer');
      if (buzEl) buzEl.hasSignal = (devState.alarm_siren === 'ON');

      // 5. Module Relay Đỏ & Máy Bơm Nước Mini (Chân D3)
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

      // 6. Telemetry từ snap.mqtt hoặc snap.mqtt_hardware
      const dht = (snap.mqtt && snap.mqtt.dht11_telemetry) || (snap.mqtt_hardware && snap.mqtt_hardware.esp8266_status) || null;
      const soil = (snap.mqtt && snap.mqtt.soil_moisture_telemetry) || (snap.mqtt_hardware && snap.mqtt_hardware.esp8266_status) || null;
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
      updateLiveTelemetryHeader(curT, curH, curS);
    }

    async function toggleWokwiServerMode() {
      const nextConnected = !window._wokwiServerConnected;
      const r = await fetch('/api/server_mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ server_connected: nextConnected })
      });
      const data = await r.json();
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
      try {
        const r = await fetch('/api/state');
        const snap = await r.json();
        syncWokwiComponents(snap);
      } catch (e) {}
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
      const nextAct = nextIsOn ? 'open' : 'close';

      ctrl.seq += 1;
      const mySeq = ctrl.seq;
      const myTs = Date.now();
      ctrl.lastClickTs = myTs;
      ctrl.desiredState = nextState;
      devState[devId] = nextState;

      const btn = document.getElementById('btn_' + devId);
      const lb = document.getElementById('st_' + devId);
      if (btn) btn.classList.toggle('on', nextIsOn);
      if (lb) lb.textContent = formatHumanDeviceState(devId, nextState, false);

      if (devId === 'ac' || devId === 'fan') {
        const irLed = document.getElementById('w_led_ir');
        if (irLed) {
          irLed.value = true;
          setTimeout(() => { irLed.value = false; }, 450);
        }
        logSerial(`Phát tín hiệu hồng ngoại (${devId} -> ${nextAct})`, 'ir');
      } else {
        logSerial(`Cập nhật thiết bị ${devId} -> ${nextAct}`, 'cmd');
      }

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
                client_seq: mySeq,
                client_ts_ms: myTs,
              }),
            });
            const data = await r.json();
            ctrl.pendingCount = Math.max(0, ctrl.pendingCount - 1);
            if (mySeq < ctrl.seq || (data && data.stale_ignored)) {
              resolve();
              return;
            }
            if (data.ok === false && data.error) {
              logSerial(`[CHẶN] ${data.error}`, 'warn');
              devState[devId] = ctrl.confirmedState;
              ctrl.desiredState = ctrl.confirmedState;
            }
            if (data.snapshot) syncWokwiComponents(data.snapshot);
            else fetchState();
          } catch (_) {
            ctrl.pendingCount = Math.max(0, ctrl.pendingCount - 1);
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
      const data = await r.json();
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
      await fetch('/api/dht11', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ temp_c: t, humidity_pct: 65 })
      });
      fetchState();
    }

    async function triggerIrLearnDemo(devName = 'Điều hòa Casper', act = 'open') {
      logSerial(`[VS1838B D5] Đang thu sóng hồng ngoại 38kHz cho "${devName}"...`, 'ir');
      const r = await fetch('/api/ir_learn', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_name: devName, command_action: act })
      });
      const data = await r.json();
      if (data.learned) {
        logSerial(`[IR LEARNED] Đã lưu mã ${data.learned.protocol} (${data.learned.hex_code})`, 'ir');
      }
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

    async function speakIntoHardwareMic(cmdText) {
      const micLed = document.getElementById('hw_mic_led');
      const spkLed = document.getElementById('hw_spk_led');
      const spkCone = document.getElementById('hw_spk_cone');
      if (micLed) micLed.setAttribute('fill', '#fde047');

      logSerial(`[MIC RX/GPIO3] Thu giọng nói trực tiếp trên mạch: "${cmdText}"`, 'cmd');
      try {
        const r = await fetch('/api/text_command', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: cmdText })
        });
        const data = await r.json();
        const reply = data.exact_spoken_reply || data.reply || data.error || '';
        const isOk = data.ok !== false;

        if (spkLed) spkLed.setAttribute('fill', isOk ? '#34d399' : '#ef4444');
        if (spkCone) spkCone.setAttribute('stroke', isOk ? '#34d399' : '#ef4444');
        playHardwareSpeakerTone(isOk ? 1 : 3);
        logSerial(`[LOA 8Ω 3W - D4/GPIO2] Phát phản hồi: "${reply}"`, isOk ? 'cmd' : 'warn');

        setTimeout(() => {
          if (micLed) micLed.setAttribute('fill', '#22c55e');
          if (spkLed) spkLed.setAttribute('fill', '#38bdf8');
          if (spkCone) spkCone.setAttribute('stroke', '#f59e0b');
        }, 900);
        fetchState();
      } catch (e) {}
    }

    let RAW_ESP8266_INO = '';

    async function loadRealInoCode() {
      try {
        const res = await fetch('/api/wokwi_files');
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
      return RAW_ESP8266_INO
        .replace(/const\s+char\*\s+WIFI_SSID\s*=\s*"[^"]*";/, `const char* WIFI_SSID     = "${ssid}";`)
        .replace(/const\s+char\*\s+WIFI_PASSWORD\s*=\s*"[^"]*";/, `const char* WIFI_PASSWORD = "${pass}";`)
        .replace(/const\s+char\*\s+SERVER_IP\s*=\s*"[^"]*";/, `const char* SERVER_IP     = "${host}";  // IP máy Laptop đang chạy Server (cổng 8088)`)
        .replace(/const\s+char\*\s+MQTT_SERVER\s*=\s*"[^"]*";/, `const char* MQTT_SERVER   = "${host}";`);
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
      const res = await fetch('/api/wokwi_files');
      const data = await res.json();
      const txt = kind === 'diagram' ? data.diagram_json : (getConfiguredInoText() || data.esp8266_ino || data.sketch_ino);
      await navigator.clipboard.writeText(txt);
      logSerial(`Đã copy ${kind === 'diagram' ? 'diagram.json' : 'esp8266_smarthome.ino'} vào Clipboard!`, 'cmd');
      alert(`Đã copy ${kind === 'diagram' ? 'diagram.json' : 'esp8266_smarthome.ino'}! Mở Arduino IDE và dán (Ctrl+V) để nạp vào mạch NodeMCU ESP8266.`);
    }

    // Lắng nghe sự kiện xoay chiết áp <wokwi-potentiometer id="w_soil_pot">
    window.addEventListener('DOMContentLoaded', () => {
      buildNodeMCUPins();
      buildBreadboard400();
      drawWires();
      setTimeout(drawWires, 250);
      fetchState();
      loadRealInoCode();

      const pot = document.getElementById('w_soil_pot');
      if (pot) {
        pot.addEventListener('input', (e) => {
          const val = Math.round((pot.value / 1023) * 90 + 5);
          document.getElementById('rngSoil').value = val;
          onSoilSlide(val);
          commitSoilSlide(val);
        });
      }

      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = new WebSocket(`${proto}//${location.host}/ws`);
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === 'state_snapshot' && msg.snapshot) syncWokwiComponents(msg.snapshot);
          else if (msg.type === 'device_actuated') fetchState();
        } catch (e) {}
      };
    });
  

// Window exports for inline event handlers
window.buildBreadboard400 = buildBreadboard400;
window.showHole = showHole;
window.clearHoleHover = clearHoleHover;
window.updateLiveTelemetryHeader = updateLiveTelemetryHeader;
window.buildNodeMCUPins = buildNodeMCUPins;
window.getElementPinXY = getElementPinXY;
window.drawWires = drawWires;
window.filterStep = filterStep;
window.logSerial = logSerial;
window.playHardwareSpeakerTone = playHardwareSpeakerTone;
window.speakIntoHardwareMic = speakIntoHardwareMic;
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
window.triggerIrLearnDemo = triggerIrLearnDemo;
window.loadRealInoCode = loadRealInoCode;
window.getConfiguredInoText = getConfiguredInoText;
window.refreshInoCodePreview = refreshInoCodePreview;
window.copyConfiguredInoCode = copyConfiguredInoCode;
window.copyWokwiFile = copyWokwiFile;
