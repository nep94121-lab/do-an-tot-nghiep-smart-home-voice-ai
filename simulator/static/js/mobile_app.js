    const ICONS = {
      door: '<svg class="icon"><use href="#i-door"/></svg>',
      light: '<svg class="icon"><use href="#i-lamp"/></svg>',
      fan: '<svg class="icon"><use href="#i-fan"/></svg>',
      ac: '<svg class="icon"><use href="#i-snow"/></svg>',
      siren: '<svg class="icon"><use href="#i-bell"/></svg>',
      pump: '<svg class="icon"><use href="#i-drop"/></svg>',
    };

    const ROOM_NAMES = {
      main_door: 'Lối vào',
      living_room_light: 'Phòng khách',
      bedroom_light: 'Phòng ngủ',
      ac: 'Phòng ngủ',
      fan: 'Phòng khách',
      alarm_siren: 'Lối vào',
      garden_pump: 'Sân vườn'
    };

    let latestSnap = null;
    let showAllDevices = false;
    let selectedRoomFilter = 'all';
    let mobileHistoryItems = [
      { time: new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }), event: 'Đồng bộ trạng thái nhà', result: 'Thành công', type: 'device' }
    ];
    let mobileHistoryFilter = 'all';
    let isMobileListening = false;
    let ws = null;
    let mobileMediaStream = null;
    let mobileAudioContext = null;
    let mobileAudioProcessor = null;
    let mobileLoggedIn = false;
    let mobileLoggedInEmail = '';

    /* ═══════════════════════════════════════════
       LOGIN GATE
       ═══════════════════════════════════════════ */
    async function submitMobileLogin(e) {
      if (e) e.preventDefault();
      const emailEl = document.getElementById('mobileLoginEmail');
      const passEl = document.getElementById('mobileLoginPassword');
      const msgEl = document.getElementById('mobileLoginMsg');
      const btnEl = document.getElementById('mobileLoginBtn');
      const email = (emailEl ? emailEl.value : '').trim();
      const password = (passEl ? passEl.value : '').trim();
      if (!email || !password) {
        if (msgEl) { msgEl.style.color = 'var(--danger)'; msgEl.textContent = 'Vui lòng nhập email và mật khẩu.'; }
        return;
      }
      if (btnEl) { btnEl.disabled = true; btnEl.textContent = 'Đang đăng nhập...'; }
      try {
        const res = await fetch('/api/auth3/layer1_login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password, login_method: 'password', source: 'Mobile App', send_gmail: false }),
        });
        const data = await res.json();
        if (data.ok) {
          mobileLoggedIn = true;
          mobileLoggedInEmail = email;
          if (typeof sessionStorage !== 'undefined') {
            sessionStorage.setItem('mobileLoggedIn', '1');
            sessionStorage.setItem('mobileLoggedInEmail', email);
          }
          showMobileMainContent();
        } else {
          if (msgEl) { msgEl.style.color = 'var(--danger)'; msgEl.textContent = data.error || data.message || 'Sai email hoặc mật khẩu.'; }
        }
      } catch (err) {
        if (msgEl) { msgEl.style.color = 'var(--danger)'; msgEl.textContent = 'Lỗi kết nối server.'; }
      }
      if (btnEl) { btnEl.disabled = false; btnEl.textContent = 'Đăng nhập'; }
    }

    function togglePasswordVisibility(inputId, btn) {
      const input = document.getElementById(inputId);
      if (!input) return;
      if (input.type === 'password') {
        input.type = 'text';
        if (btn) btn.textContent = '🙈';
      } else {
        input.type = 'password';
        if (btn) btn.textContent = '👁️';
      }
    }

    function switchMobileLoginTab(tab) {
      const loginForm = document.getElementById('mobileLoginForm');
      const regForm = document.getElementById('mobileRegisterForm');
      const btnLogin = document.getElementById('btnMobileTabLogin');
      const btnReg = document.getElementById('btnMobileTabRegister');
      if (tab === 'login') {
        if (loginForm) loginForm.style.display = 'grid';
        if (regForm) regForm.style.display = 'none';
        if (btnLogin) btnLogin.className = 'btn primary';
        if (btnReg) btnReg.className = 'btn secondary';
      } else {
        if (loginForm) loginForm.style.display = 'none';
        if (regForm) regForm.style.display = 'grid';
        if (btnLogin) btnLogin.className = 'btn secondary';
        if (btnReg) btnReg.className = 'btn primary';
      }
    }

    function onMobileRegTierChange() {
      const tierEl = document.getElementById('mobileRegTier');
      const nameEl = document.getElementById('mobileRegName');
      const emailEl = document.getElementById('mobileRegEmail');
      if (!tierEl) return;
      const t = parseInt(tierEl.value || '1', 10);
      if (t === 1) {
        if (nameEl) nameEl.value = 'Nguyễn Tuấn Anh';
        if (emailEl) emailEl.value = 'nep94121@gmail.com';
      } else if (t === 2) {
        if (nameEl && (nameEl.value === 'Nguyễn Tuấn Anh' || !nameEl.value)) nameEl.value = 'Thành viên A';
        if (emailEl && (emailEl.value === 'nep94121@gmail.com' || !emailEl.value)) emailEl.value = 'thanhviena.hust@gmail.com';
      } else {
        if (nameEl && (nameEl.value === 'Nguyễn Tuấn Anh' || !nameEl.value)) nameEl.value = 'Khách C';
        if (emailEl && (emailEl.value === 'nep94121@gmail.com' || !emailEl.value)) emailEl.value = 'khach.hust@gmail.com';
      }
    }

    async function submitMobileRegister(e) {
      if (e) e.preventDefault();
      const tierEl = document.getElementById('mobileRegTier');
      const nameEl = document.getElementById('mobileRegName');
      const emailEl = document.getElementById('mobileRegEmail');
      const pwEl = document.getElementById('mobileRegPassword');
      const pwConfirmEl = document.getElementById('mobileRegConfirmPassword');
      const msgEl = document.getElementById('mobileRegMsg');
      const btnEl = document.getElementById('mobileRegisterBtn');

      const tier = tierEl ? parseInt(tierEl.value || '2', 10) : 2;
      const displayName = nameEl ? nameEl.value.trim() : 'Thành viên mới';
      const email = emailEl ? emailEl.value.trim() : '';
      const password = pwEl ? pwEl.value : '';
      const confirmPassword = pwConfirmEl ? pwConfirmEl.value : '';

      if (!email || !password || !confirmPassword) {
        if (msgEl) {
          msgEl.style.color = 'var(--danger)';
          msgEl.textContent = 'Vui lòng nhập đầy đủ email và cả 2 ô mật khẩu.';
        }
        return;
      }
      if (password !== confirmPassword) {
        if (msgEl) {
          msgEl.style.color = 'var(--danger)';
          msgEl.textContent = 'Hai ô mật khẩu không khớp nhau! Vui lòng nhập giống nhau 100%.';
        }
        return;
      }

      if (btnEl) { btnEl.disabled = true; btnEl.textContent = 'Đang xử lý...'; }
      try {
        const res = await fetch('/api/auth3/register_or_set_password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email,
            display_name: displayName,
            target_tier: tier,
            password,
            confirm_password: confirmPassword,
          }),
        });
        const data = await res.json();
        if (data.ok) {
          mobileLoggedIn = true;
          mobileLoggedInEmail = email;
          if (typeof sessionStorage !== 'undefined') {
            sessionStorage.setItem('mobileLoggedIn', '1');
            sessionStorage.setItem('mobileLoggedInEmail', email);
          }
          if (msgEl) {
            msgEl.style.color = 'var(--accent)';
            msgEl.textContent = '✅ Đặt mật khẩu thành công!';
          }
          setTimeout(showMobileMainContent, 500);
        } else {
          if (msgEl) {
            msgEl.style.color = 'var(--danger)';
            msgEl.textContent = data.error || 'Không lưu được mật khẩu.';
          }
        }
      } catch (err) {
        if (msgEl) {
          msgEl.style.color = 'var(--danger)';
          msgEl.textContent = 'Lỗi kết nối máy chủ.';
        }
      }
      if (btnEl) { btnEl.disabled = false; btnEl.textContent = 'Xác nhận 2 mật khẩu & Đăng nhập'; }
    }

    async function submitMobileChangePassword(e) {
      if (e) e.preventDefault();
      const emailEl = document.getElementById('mobileChangeEmail');
      const pw1El = document.getElementById('mobileChangeNewPassword');
      const pw2El = document.getElementById('mobileChangeConfirmPassword');
      const msgEl = document.getElementById('mobileChangePasswordMsg');
      const btnEl = document.getElementById('mobileChangePasswordBtn');

      const email = (emailEl ? emailEl.value : '').trim();
      const pw1 = pw1El ? pw1El.value : '';
      const pw2 = pw2El ? pw2El.value : '';

      if (!email || !pw1 || !pw2) {
        if (msgEl) {
          msgEl.style.color = 'var(--danger)';
          msgEl.textContent = 'Vui lòng nhập email và cả 2 ô mật khẩu.';
        }
        return;
      }
      if (pw1 !== pw2) {
        if (msgEl) {
          msgEl.style.color = 'var(--danger)';
          msgEl.textContent = 'Hai ô mật khẩu không khớp nhau!';
        }
        return;
      }

      if (btnEl) { btnEl.disabled = true; btnEl.textContent = 'Đang đổi mật khẩu...'; }
      try {
        const res = await fetch('/api/auth3/register_or_set_password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email,
            password: pw1,
            confirm_password: pw2,
          }),
        });
        const data = await res.json();
        if (data.ok) {
          if (msgEl) {
            msgEl.style.color = 'var(--accent)';
            msgEl.textContent = '✅ Đổi mật khẩu thành công!';
          }
        } else {
          if (msgEl) {
            msgEl.style.color = 'var(--danger)';
            msgEl.textContent = data.error || 'Không đổi được mật khẩu.';
          }
        }
      } catch (err) {
        if (msgEl) {
          msgEl.style.color = 'var(--danger)';
          msgEl.textContent = 'Lỗi kết nối máy chủ.';
        }
      }
      if (btnEl) { btnEl.disabled = false; btnEl.textContent = 'Xác nhận đổi mật khẩu'; }
    }

    function showMobileMainContent() {
      const gate = document.getElementById('mobileLoginGate');
      const main = document.getElementById('mobileMainContent');
      const nav = document.getElementById('mobileBottomNav');
      if (gate) gate.hidden = true;
      if (main) main.hidden = false;
      if (nav) nav.hidden = false;
      initMobileApp();
    }

    function checkMobileSession() {
      if (typeof sessionStorage !== 'undefined' && sessionStorage.getItem('mobileLoggedIn') === '1') {
        mobileLoggedIn = true;
        mobileLoggedInEmail = sessionStorage.getItem('mobileLoggedInEmail') || '';
        showMobileMainContent();
      }
    }

    function scrollToSection(id, startMic = false, tabEl = null) {
      if (tabEl) {
        document.querySelectorAll('.bottom-nav .nav-tab').forEach(b => b.classList.remove('active'));
        tabEl.classList.add('active');
      }
      const el = document.getElementById(id);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      if (startMic && !isMobileListening) {
        toggleMobileVoiceListen();
      }
    }

    function toggleShowAllDevices() {
      showAllDevices = !showAllDevices;
      const btn = document.getElementById('btnToggleShowAllDevices');
      if (btn) btn.textContent = showAllDevices ? 'Thu gọn' : 'Xem tất cả';
      if (latestSnap) renderState(latestSnap);
    }

    function filterDevicesByRoom(room, btn) {
      selectedRoomFilter = room;
      showAllDevices = true;
      document.querySelectorAll('#roomFilterPills .pill').forEach(p => p.classList.remove('active'));
      if (btn) btn.classList.add('active');
      if (latestSnap) renderState(latestSnap);
    }

    function addLog(msg, type = 'device', result = 'Thành công') {
      const t = new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
      mobileHistoryItems.unshift({ time: t, event: msg, result, type });
      if (mobileHistoryItems.length > 20) mobileHistoryItems.pop();
      renderMobileHistory();
    }

    function filterMobileHistory(kind, btn) {
      mobileHistoryFilter = kind;
      document.querySelectorAll('#secHistory .pill').forEach(p => p.classList.remove('active'));
      if (btn) btn.classList.add('active');
      renderMobileHistory();
    }

    function renderMobileHistory() {
      const box = document.getElementById('mqttLog');
      if (!box) return;
      const list = mobileHistoryItems.filter(i => mobileHistoryFilter === 'all' || i.type === mobileHistoryFilter);
      if (list.length === 0) {
        box.innerHTML = '<div class="log-line"><span class="muted">Chưa có sự kiện</span></div>';
        return;
      }
      box.innerHTML = list.map(i => `
        <div class="log-line">
          <span>${i.time} · ${i.event}</span>
          <span class="muted">${i.result}</span>
        </div>
      `).join('');
    }

    function renderState(snap) {
      if (!snap) return;
      latestSnap = snap;
      const allDevices = snap.devices || [];
      const filtered = allDevices.filter(d => {
        const roomLabel = d.room || ROOM_NAMES[d.id] || 'Phòng khách';
        return selectedRoomFilter === 'all' || roomLabel === selectedRoomFilter;
      });
      const visibleDevices = showAllDevices ? filtered : filtered.slice(0, 4);

      const grid = document.getElementById('devGrid');
      grid.innerHTML = '';

      visibleDevices.forEach((d) => {
        const isOn = d.state === 'ON' || d.state === 'OPEN';
        const roomLabel = d.room || ROOM_NAMES[d.id] || 'Phòng khách';
        const card = document.createElement('div');
        card.className = `dev-row ${isOn ? 'on' : 'off'}`;
        card.innerHTML = `
          <span class="dev-icon">${ICONS[d.type] || '<svg class="icon"><use href="#i-lamp"/></svg>'}</span>
          <div class="dev-copy">
            <div class="dev-name">${d.name}</div>
            <div class="dev-room">${roomLabel}</div>
          </div>
          <span class="switch" aria-hidden="true"></span>
        `;
        card.onclick = async () => {
          const action = d.type === 'door' ? (isOn ? 'close' : 'open') : (isOn ? 'turn_off' : 'turn_on');
          const res = await fetch('/api/device', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_id: d.id, action }),
          });
          const data = await res.json();
          if (data.snapshot) renderState(data.snapshot);
          addLog(`${d.name}: ${!isOn ? 'Bật' : 'Tắt'}`, 'device', data.ok === false ? 'Thất bại' : 'Thành công');
        };
        grid.appendChild(card);
      });

      const connEl = document.getElementById('espBadge');
      if (connEl) {
        const online = snap.server_connected !== false;
        connEl.textContent = online ? 'Đã kết nối' : 'Mất kết nối';
        connEl.classList.toggle('offline', !online);
      }

      if (snap.mqtt) {
        const dht = snap.mqtt.dht11_telemetry || {};
        const soil = snap.mqtt.soil_moisture_telemetry || {};
        if (dht.temp_c !== undefined) document.getElementById('tempVal').textContent = `${dht.temp_c}°C`;
        if (dht.humidity_pct !== undefined) document.getElementById('humVal').textContent = `${dht.humidity_pct}%`;
        if (soil.soil_moisture_pct !== undefined) {
          document.getElementById('soilVal').textContent = `${soil.soil_moisture_pct}%`;
        }
      }
    }

    async function fetchInitial() {
      const res = await fetch('/api/state');
      const snap = await res.json();
      renderState(snap);
    }

    function showPwaVoiceResults(said, reply) {
      document.getElementById('pwaVoiceEmpty').hidden = true;
      document.getElementById('pwaVoiceResults').hidden = false;
      if (said !== null) document.getElementById('userSaidText').textContent = said;
      if (reply !== null) document.getElementById('aiReply').textContent = reply;
    }

    async function toggleMobileVoiceListen() {
      isMobileListening = !isMobileListening;
      const badge = document.getElementById('voiceStateBadge');
      const label = document.getElementById('btnMobileMicLabel');

      if (!isMobileListening) {
        if (badge) badge.textContent = 'Sẵn sàng';
        if (label) label.textContent = 'Bắt đầu nói';
        if (mobileAudioProcessor) {
          mobileAudioProcessor.disconnect();
          mobileAudioProcessor = null;
        }
        if (mobileMediaStream) {
          mobileMediaStream.getTracks().forEach(t => t.stop());
          mobileMediaStream = null;
        }
        if (mobileAudioContext) {
          mobileAudioContext.close();
          mobileAudioContext = null;
        }
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'mic_speech_ended' }));
        }
        return;
      }

      if (badge) badge.textContent = 'Đang nghe';
      if (label) label.textContent = 'Dừng và gửi';

      try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
              type: 'mic_chunk',
              pcm16k_b64: generateMobileSynthetic16kPcmB64(true),
              is_speech: true,
            }));
            setTimeout(() => {
              if (isMobileListening) toggleMobileVoiceListen();
            }, 3000);
          }
          return;
        }

        mobileMediaStream = await navigator.mediaDevices.getUserMedia({
          audio: { channelCount: 1, sampleRate: 16000 }
        });
        mobileAudioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
        const source = mobileAudioContext.createMediaStreamSource(mobileMediaStream);
        mobileAudioProcessor = mobileAudioContext.createScriptProcessor(4096, 1, 1);
        mobileAudioProcessor.onaudioprocess = (e) => {
          if (!isMobileListening) return;
          const input = e.inputBuffer.getChannelData(0);
          const pcm16 = new Int16Array(input.length);
          for (let i = 0; i < input.length; i++) {
            const s = Math.max(-1, Math.min(1, input[i]));
            pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
          }
          const bytes = new Uint8Array(pcm16.buffer);
          let binary = '';
          for (let i = 0; i < bytes.byteLength; i++) {
            binary += String.fromCharCode(bytes[i]);
          }
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
              type: 'mic_chunk',
              pcm16k_b64: window.btoa(binary),
              is_speech: true,
            }));
          }
        };
        source.connect(mobileAudioProcessor);
        mobileAudioProcessor.connect(mobileAudioContext.destination);
      } catch (err) {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({
            type: 'mic_chunk',
            pcm16k_b64: generateMobileSynthetic16kPcmB64(true),
            is_speech: true,
          }));
        }
      }
    }

    async function executeMobileCommand(text) {
      showPwaVoiceResults(text, 'Đang xử lý...');
      document.getElementById('voiceStateBadge').textContent = 'Đang xử lý';
      const res = await fetch('/api/text_command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      const data = await res.json();
      const reply = data.said || data.exact_spoken_reply || 'Đã thực hiện lệnh.';
      showPwaVoiceResults(text, reply);
      document.getElementById('voiceStateBadge').textContent = data.ok === false ? 'Cần thử lại' : 'Sẵn sàng';
      addLog(text, 'voice', data.ok === false ? 'Thất bại' : 'Thành công');
      fetchInitial();
    }

    document.getElementById('cmdForm').onsubmit = async (e) => {
      e.preventDefault();
      const inp = document.getElementById('cmdInput');
      const text = inp.value.trim();
      if (!text) return;
      inp.value = '';
      await executeMobileCommand(text);
    };

    async function submitPwaSchedule(e) {
      e.preventDefault();
      const t = document.getElementById('pwaSchedTime').value.trim() || '10 giây nữa';
      const dev = document.getElementById('pwaSchedDevice').value;
      const act = document.getElementById('pwaSchedAction').value;
      document.getElementById('pwaScheduleForm').hidden = true;
      await executeMobileCommand(`Hẹn ${t} ${act.toLowerCase()} ${dev.toLowerCase()}`);
    }

    document.getElementById('btnLearnIr').onclick = async () => {
      const res = await fetch('/api/ir_learn', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_name: 'ac', command_action: 'turn_on_24c' }),
      });
      const data = await res.json();
      if (data.learned) {
        showPwaVoiceResults('Học lệnh điều hòa', 'Đã lưu tín hiệu điều khiển điều hòa.');
        addLog('Lưu tín hiệu điều khiển điều hòa', 'device');
      }
    };

    document.getElementById('btnTestDrySoil').onclick = async () => {
      await fetch('/api/soil_moisture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ soil_moisture_pct: 32.0 }),
      });
      showPwaVoiceResults('Kiểm tra độ ẩm đất', 'Độ ẩm đất thấp, đã tự động bật tưới cây.');
      addLog('Tự động bật tưới cây', 'device');
      fetchInitial();
    };

    function onMobileActorChange() {
      const sel = document.getElementById('mobileActorSelect');
      if (!sel) return;
      const tier = parseInt(sel.options[sel.selectedIndex].getAttribute('data-tier') || '1', 10);
      const badge = document.getElementById('mobileActorBadge');
      const form = document.getElementById('mobileAddEmailForm');
      const targetTierSel = document.getElementById('mobileTargetTierSelect');
      const msg = document.getElementById('mobileAllowlistMsg');
      const tierInfoEl = document.getElementById('mobileVoiceTierInfo');
      const regNameEl = document.getElementById('mobileVoiceRegName');

      const tierLabels = { 1: 'Chủ nhà', 2: 'Gia đình', 3: 'Khách' };
      const tierDescs = {
        1: 'Cấp 1 — Chủ nhà: toàn quyền điều khiển',
        2: 'Cấp 2 — Gia đình: điều khiển cơ bản',
        3: 'Cấp 3 — Khách: chỉ xem trạng thái'
      };
      const label = tierLabels[tier] || 'Không rõ';

      if (badge) badge.textContent = label;
      if (tierInfoEl) tierInfoEl.textContent = tierDescs[tier] || '';
      if (regNameEl) regNameEl.textContent = label;

      if (tier === 1) {
        form.style.display = 'grid';
        targetTierSel.innerHTML = `<option value="2">Gia đình</option><option value="3">Khách</option>`;
        msg.style.color = 'var(--muted)';
        msg.textContent = 'Chủ nhà được thêm Gia đình và Khách.';
      } else if (tier === 2) {
        form.style.display = 'grid';
        targetTierSel.innerHTML = `<option value="3">Khách</option>`;
        msg.style.color = 'var(--muted)';
        msg.textContent = 'Gia đình chỉ được thêm Khách.';
      } else {
        form.style.display = 'none';
        msg.style.color = 'var(--danger)';
        msg.textContent = 'Khách không có quyền thêm thành viên.';
      }
    }

    async function submitMobileAddEmail() {
      const actorEmail = document.getElementById('mobileActorSelect').value;
      const targetTier = parseInt(document.getElementById('mobileTargetTierSelect').value || '2', 10);
      const targetEmail = document.getElementById('mobileTargetEmail').value.trim();
      const msg = document.getElementById('mobileAllowlistMsg');

      const res = await fetch('/api/auth3/family_allowlist/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          actor_email: actorEmail,
          target_email: targetEmail,
          target_tier: targetTier,
        }),
      });
      const data = await res.json();
      if (data.ok) {
        msg.style.color = 'var(--accent)';
        msg.textContent = data.message || 'Đã lưu tài khoản thành viên.';
        document.getElementById('mobileTargetEmail').value = '';
        addLog(`Thêm quyền cho ${targetEmail}`, 'device', 'Thành công');
      } else {
        msg.style.color = 'var(--danger)';
        msg.textContent = data.error || 'Không thể thêm tài khoản.';
      }
    }

    function generateMobileSynthetic16kPcmB64(isGood) {
      const sr = 16000;
      const durSec = isGood ? 2.8 : 0.4;
      const totalSamples = Math.floor(sr * durSec);
      const pcm16 = new Int16Array(totalSamples);
      const f0 = isGood ? 188.0 : 80.0;
      for (let i = 0; i < totalSamples; i++) {
        if (i < Math.floor(sr * 0.3) && isGood) {
          pcm16[i] = 0;
        } else {
          const t = i / sr;
          const s = 0.4 * Math.sin(2 * Math.PI * f0 * t) + 0.2 * Math.sin(2 * Math.PI * (f0 * 2) * t);
          pcm16[i] = Math.floor(s * 32767);
        }
      }
      let binary = '';
      const bytes = new Uint8Array(pcm16.buffer);
      for (let i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
      }
      return window.btoa(binary);
    }

    async function submitMobileVoiceSample(isGood) {
      const promptText = 'Xin chào hệ thống Nhà Thông Minh Bách Khoa, tôi là Thành viên Gia đình đọc câu này để đăng ký giọng nói điều khiển thiết bị.';
      let pcmB64 = '';
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, sampleRate: 16000 } });
          const audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
          const source = audioCtx.createMediaStreamSource(stream);
          const processor = audioCtx.createScriptProcessor(4096, 1, 1);
          const chunks = [];
          processor.onaudioprocess = (e) => {
            const input = e.inputBuffer.getChannelData(0);
            const pcm16 = new Int16Array(input.length);
            for (let i = 0; i < input.length; i++) {
              const s = Math.max(-1, Math.min(1, input[i]));
              pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
            }
            chunks.push(pcm16);
          };
          source.connect(processor);
          processor.connect(audioCtx.destination);
          await new Promise(r => setTimeout(r, 600));
          processor.disconnect();
          stream.getTracks().forEach(t => t.stop());
          audioCtx.close();
          let totalLen = 0;
          chunks.forEach(c => totalLen += c.length);
          const fullPcm = new Int16Array(totalLen);
          let offset = 0;
          chunks.forEach(c => { fullPcm.set(c, offset); offset += c.length; });
          let binary = '';
          const bytes = new Uint8Array(fullPcm.buffer);
          for (let i = 0; i < bytes.byteLength; i++) { binary += String.fromCharCode(bytes[i]); }
          pcmB64 = window.btoa(binary);
        } catch (_) {
          pcmB64 = generateMobileSynthetic16kPcmB64(isGood);
        }
      }
      if (!pcmB64) {
        pcmB64 = generateMobileSynthetic16kPcmB64(isGood);
      }

      const res = await fetch('/api/auth3/enroll_voice_sample', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: 'em_mobile.hust@gmail.com',
          spoken_text: isGood ? promptText : 'Alo 1 2',
          measured_f0_hz: isGood ? 188.0 : 0.0,
          snr_db: isGood ? 18.5 : 3.2,
          hold_duration_sec: isGood ? 3.2 : 0.6,
          source_device: 'Mobile App Web',
          audio_pcm_b64: pcmB64,
          pcm16k_b64: pcmB64,
        }),
      });
      const data = await res.json();
      const box = document.getElementById('mobileVoiceRes');
      const metricsEl = document.getElementById('mobileVoiceMetrics');
      const f0El = document.getElementById('mobileVoiceF0');
      const snrEl = document.getElementById('mobileVoiceSNR');
      const stepLabel = document.getElementById('mobileVoiceStepLabel');
      const retryBtn = document.getElementById('mobileVoiceRetryBtn');

      /* Hiển thị metrics F0/SNR */
      if (metricsEl) {
        metricsEl.style.display = 'block';
        if (f0El) f0El.textContent = data.measured_f0_hz != null ? data.measured_f0_hz.toFixed(1) : (isGood ? '188.0' : '0.0');
        if (snrEl) snrEl.textContent = data.snr_db != null ? data.snr_db.toFixed(1) : (isGood ? '18.5' : '3.2');
      }

      if (box) {
        if (data.ok && data.status === 'DA_DAT') {
          box.innerHTML = '<span class="voice-result-badge pass">✓ ĐẠT — Đã lưu giọng nói</span>';
          if (stepLabel) stepLabel.textContent = 'Hoàn tất ✓';
          if (retryBtn) retryBtn.textContent = 'Thu lại';
        } else if (data.status === 'DUPLICATE_VOICE_REJECTED') {
          box.innerHTML = '<span class="voice-result-badge fail">✗ KHÔNG ĐẠT — Trùng giọng người trong nhà</span>';
          if (retryBtn) retryBtn.textContent = 'Thu lại';
        } else {
          box.innerHTML = '<span class="voice-result-badge fail">✗ KHÔNG ĐẠT — Chưa nhận rõ giọng nói</span>';
          if (retryBtn) retryBtn.textContent = 'Thu lại';
        }
      }
    }

    async function copyMobileGuestLink() {
      const url = document.getElementById('mobileQrUrlText')?.textContent || location.origin + '/guest_enroll';
      try {
        await navigator.clipboard.writeText(url);
        document.getElementById('mobileQrCountdown').textContent = 'Đã sao chép';
      } catch (e) {}
    }

    const proto = location.protocol === 'https:' ? 'wss' : 'ws';

    function connectMobileWebSocket() {
      ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onopen = () => {
        addLog('WebSocket kết nối', 'device', 'Thành công');
      };
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.type === 'state_snapshot') renderState(msg.snapshot);
        if (msg.type === 'device_updated') {
          /* Cập nhật device ngay lập tức trong latestSnap để render tức thì */
          if (latestSnap && latestSnap.devices && msg.device_id) {
            const dev = latestSnap.devices.find(d => d.id === msg.device_id);
            if (dev) {
              dev.state = msg.new_state;
              renderState(latestSnap);
            }
          }
          addLog(`${msg.device_name || msg.device_id}: ${msg.new_state}`, 'device');
        }
        if (msg.type === 'input_transcription') {
          showPwaVoiceResults(msg.full_text, null);
        }
        if (msg.type === 'output_transcription') {
          showPwaVoiceResults(null, msg.full_text);
          const badge = document.getElementById('voiceStateBadge');
          if (badge) badge.textContent = 'Sẵn sàng';
        }
      };
      ws.onclose = () => {
        const connEl = document.getElementById('espBadge');
        if (connEl) { connEl.textContent = 'Mất kết nối'; connEl.classList.add('offline'); }
        /* Auto-reconnect after 3s */
        setTimeout(() => { if (mobileLoggedIn) connectMobileWebSocket(); }, 3000);
      };
      ws.onerror = () => {};
    }

    async function refreshMobileQr10s() {
      try {
        const durSel = document.getElementById('mobileGuestDurSelect');
        const dur = durSel ? durSel.value : '1d';
        const tierSel = document.getElementById('mobileQrInviteTierSelect');
        const inviteTier = tierSel ? tierSel.value : '3';
        const r = await fetch(`/api/auth3/guest_qr_current?duration=${encodeURIComponent(dur)}&host=${encodeURIComponent(location.host)}&tier=${encodeURIComponent(inviteTier)}`);
        const d = await r.json();
        if (!d.ok) return;
        const rem = d.remaining_slot_sec || d.remaining_Slot_sec || 10;
        const cdEl = document.getElementById('mobileQrCountdown');
        if (cdEl) {
          cdEl.textContent = `Còn ${rem}s`;
          cdEl.style.color = rem <= 3 ? '#c83e3b' : 'var(--muted)';
        }
        document.getElementById('mobileQrTokenText').textContent = `${d.token}`;
        document.getElementById('mobileQrUrlText').textContent = d.full_url || d.qr_url;
        document.getElementById('mobileQrOpenLink').href = `/guest_enroll?token=${encodeURIComponent(d.token)}&dur=${encodeURIComponent(dur)}&tier=${encodeURIComponent(inviteTier)}`;
        const qrContainer = document.getElementById('mobileQrSvgContainer');
        if (d.qr_svg && qrContainer) {
          qrContainer.innerHTML = d.qr_svg;
          const svgEl = qrContainer.querySelector('svg');
          if (svgEl) {
            svgEl.id = 'mobileDynamicQrSvg';
            svgEl.setAttribute('width', '104');
            svgEl.setAttribute('height', '104');
            svgEl.style.width = '104px';
            svgEl.style.height = '104px';
            svgEl.style.display = 'block';
            svgEl.style.background = '#fff';
            svgEl.style.padding = '4px';
            svgEl.style.borderRadius = '10px';
            svgEl.style.border = '1px solid var(--line)';
          }
        } else {
          const g = document.getElementById('mobileQrDots');
          if (g) {
            let h = 2166136261;
            for (let i = 0; i < d.token.length; i++) h = Math.imul(h ^ d.token.charCodeAt(i), 16777619);
            let rects = '';
            for (let r = 0; r < 9; r++) {
              for (let c = 0; c < 9; c++) {
                if ((r < 3 && c < 3) || (r < 3 && c > 5) || (r > 5 && c < 3)) continue;
                h = Math.imul(h ^ (r * 29 + c * 13), 16777619);
                if (Math.abs(h) % 10 < 6) {
                  rects += `<rect x="${6 + c * 9.8}" y="${6 + r * 9.8}" width="7.2" height="7.2" rx="1" fill="${(r + c) % 2 === 0 ? '#087d85' : '#172b31'}"/>`;
                }
              }
            }
            g.innerHTML = rects;
          }
        }
      } catch (e) {}
    }

    async function pollMobileSecurityAndTimers() {
      refreshMobileQr10s();
      try {
        const [r1, r2] = await Promise.all([fetch('/api/auth3/overview'), fetch('/api/state')]);
        const d1 = await r1.json();
        const d2 = await r2.json();
        const stBadge = document.getElementById('mobileStrikeBadge');
        if (stBadge && d1.security_status) {
          const st = d1.security_status;
          stBadge.textContent = `${st.failed_voice_Attempts}/${st.max_attempts}`;
        }
        const schedInline = document.getElementById('upcomingScheduleInline');
        if (schedInline && d2.timers) {
          if (d2.timers.length > 0) {
            const t = d2.timers[0];
            schedInline.textContent = `${t.device_name} · ${t.action_vi || t.action} (${t.remaining_seconds}s)`;
          } else {
            schedInline.textContent = 'Chưa có lịch';
          }
        }
      } catch (e) {}
    }

    function onMobileQrInviteTierChange() {
      refreshMobileQr10s();
    }

    let _mobileAppInited = false;
    function initMobileApp() {
      if (_mobileAppInited) return;
      _mobileAppInited = true;
      connectMobileWebSocket();
      fetchInitial();
      refreshMobileQr10s();
      renderMobileHistory();
      setInterval(pollMobileSecurityAndTimers, 1000);
    }

    /* Kiểm tra session khi load trang */
    checkMobileSession();


// Window exports for inline event handlers
window.scrollToSection = scrollToSection;
window.toggleShowAllDevices = toggleShowAllDevices;
window.filterDevicesByRoom = filterDevicesByRoom;
window.addLog = addLog;
window.filterMobileHistory = filterMobileHistory;
window.renderMobileHistory = renderMobileHistory;
window.renderState = renderState;
window.fetchInitial = fetchInitial;
window.showPwaVoiceResults = showPwaVoiceResults;
window.toggleMobileVoiceListen = toggleMobileVoiceListen;
window.executeMobileCommand = executeMobileCommand;
window.submitPwaSchedule = submitPwaSchedule;
window.onMobileActorChange = onMobileActorChange;
window.submitMobileAddEmail = submitMobileAddEmail;
window.submitMobileVoiceSample = submitMobileVoiceSample;
window.copyMobileGuestLink = copyMobileGuestLink;
window.refreshMobileQr10s = refreshMobileQr10s;
window.pollMobileSecurityAndTimers = pollMobileSecurityAndTimers;
window.submitMobileLogin = submitMobileLogin;
window.onMobileQrInviteTierChange = onMobileQrInviteTierChange;
window.switchMobileLoginTab = switchMobileLoginTab;
window.onMobileRegTierChange = onMobileRegTierChange;
window.submitMobileRegister = submitMobileRegister;
window.submitMobileChangePassword = submitMobileChangePassword;
window.togglePasswordVisibility = togglePasswordVisibility;
