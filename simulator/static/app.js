"use strict";

(() => {
  const geminiStatusBadge = document.getElementById("geminiStatusBadge");
  const geminiStatusText = document.getElementById("geminiStatusText");
  const roleSelect = document.getElementById("roleSelect");
  const btnFactoryReset = document.getElementById("btnFactoryReset");
  const vnClockText = document.getElementById("vnClockText");

  const btnTogglePromptModal = document.getElementById("btnTogglePromptModal");
  const btnClosePromptModal = document.getElementById("btnClosePromptModal");
  const promptModal = document.getElementById("promptModal");
  const systemPromptPre = document.getElementById("systemPromptPre");

  const oledMode = document.getElementById("oledMode");
  const oledRole = document.getElementById("oledRole");
  const oledMainLine = document.getElementById("oledMainLine");
  const oledSubLine = document.getElementById("oledSubLine");

  const devicesGrid = document.getElementById("devicesGrid");
  const timersList = document.getElementById("timersList");
  const timerCount = document.getElementById("timerCount");
  const rulesList = document.getElementById("rulesList");
  const rulesCount = document.getElementById("rulesCount");

  const btnMicToggle = document.getElementById("btnMicToggle");
  const micBtnText = document.getElementById("micBtnText");
  const btnManualEndTurn = document.getElementById("btnManualEndTurn");
  const micStateLabel = document.getElementById("micStateLabel");
  const micMeterBar = document.getElementById("micMeterBar");
  const chkPlayAiVoice = document.getElementById("chkPlayAiVoice");

  const liveUserTranscript = document.getElementById("liveUserTranscript");
  const liveToolCall = document.getElementById("liveToolCall");
  const liveAiTranscript = document.getElementById("liveAiTranscript");

  const textCmdForm = document.getElementById("textCmdForm");
  const textCmdInput = document.getElementById("textCmdInput");

  const metricToolMs = document.getElementById("metricToolMs");
  const metricAudioMs = document.getElementById("metricAudioMs");
  const metricLeadMs = document.getElementById("metricLeadMs");
  const metricOrderBadge = document.getElementById("metricOrderBadge");

  const btnScheduleVnTime = document.getElementById("btnScheduleVnTime");
  const voiceSamplesGrid = document.getElementById("voiceSamplesGrid");
  const eventLog = document.getElementById("eventLog");
  const btnClearLog = document.getElementById("btnClearLog");

  let ws = null;
  let audioCtxOut = null;
  let nextPlayTime = 0;
  let latestDevicesMap = {};

  // Mic capture state
  let isRecording = false;
  let micStream = null;
  let micAudioCtx = null;
  let micProcessor = null;
  let wasSpeaking = false;
  let silenceStartMs = 0;
  let isCapturingEnrollment = false;
  let enrollmentChunks = [];

  // Đồng hồ Giờ Việt Nam (GMT+7 AM/PM)
  function updateVnClock() {
    const now = new Date();
    const vnFmt = new Intl.DateTimeFormat("en-US", {
      timeZone: "Asia/Ho_Chi_Minh",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: true,
    }).format(now);
    if (vnClockText) vnClockText.textContent = vnFmt;

    // Cập nhật nút hẹn giờ +1 phút theo giờ VN AM/PM
    if (btnScheduleVnTime) {
      const plus1Min = new Date(now.getTime() + 60 * 1000);
      const hmAmPm = new Intl.DateTimeFormat("en-US", {
        timeZone: "Asia/Ho_Chi_Minh",
        hour: "2-digit",
        minute: "2-digit",
        hour12: true,
      }).format(plus1Min);
      btnScheduleVnTime.setAttribute("data-cmd", `Hẹn đúng ${hmAmPm} bật quạt trần nhé`);
      btnScheduleVnTime.textContent = `🕒 Hẹn theo Giờ VN: ${hmAmPm} bật quạt`;
    }
  }
  setInterval(updateVnClock, 1000);
  updateVnClock();

  if (btnTogglePromptModal) {
    btnTogglePromptModal.addEventListener("click", () => {
      promptModal.classList.toggle("hidden");
    });
  }
  if (btnClosePromptModal) {
    btnClosePromptModal.addEventListener("click", () => {
      promptModal.classList.add("hidden");
    });
  }

  function logEvent(text, level = "info") {
    const line = document.createElement("div");
    line.className = `log-line ${level}`;
    const now = new Date();
    const ts = now.toTimeString().split(" ")[0] + "." + String(now.getMilliseconds()).padStart(3, "0");
    line.innerHTML = `<span class="ts">[${ts}]</span> ${escapeHtml(text)}`;
    eventLog.prepend(line);
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function playRelayClick(isOpenOrOn) {
    try {
      if (!audioCtxOut) {
        audioCtxOut = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
      }
      if (audioCtxOut.state === "suspended") {
        audioCtxOut.resume();
      }
      const osc = audioCtxOut.createOscillator();
      const gain = audioCtxOut.createGain();
      osc.type = "triangle";
      osc.frequency.setValueAtTime(isOpenOrOn ? 1450 : 850, audioCtxOut.currentTime);
      gain.gain.setValueAtTime(0.18, audioCtxOut.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, audioCtxOut.currentTime + 0.045);
      osc.connect(gain);
      gain.connect(audioCtxOut.destination);
      osc.start();
      osc.stop(audioCtxOut.currentTime + 0.05);
    } catch (_) {}
  }

  function playPcm24kChunk(base64Data) {
    if (!chkPlayAiVoice.checked) return;
    try {
      if (!audioCtxOut) {
        audioCtxOut = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
      }
      if (audioCtxOut.state === "suspended") {
        audioCtxOut.resume();
      }
      const binaryStr = atob(base64Data);
      const len = binaryStr.length;
      const int16Arr = new Int16Array(len / 2);
      for (let i = 0; i < len; i += 2) {
        int16Arr[i / 2] = binaryStr.charCodeAt(i) | (binaryStr.charCodeAt(i + 1) << 8);
      }
      const float32Arr = new Float32Array(int16Arr.length);
      for (let i = 0; i < int16Arr.length; i++) {
        float32Arr[i] = int16Arr[i] / 32768.0;
      }

      const audioBuffer = audioCtxOut.createBuffer(1, float32Arr.length, 24000);
      audioBuffer.getChannelData(0).set(float32Arr);

      const source = audioCtxOut.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(audioCtxOut.destination);

      const now = audioCtxOut.currentTime;
      if (nextPlayTime < now) {
        nextPlayTime = now + 0.02;
      }
      source.start(nextPlayTime);
      nextPlayTime += audioBuffer.duration;
    } catch (err) {
      console.error("Audio playback error:", err);
    }
  }

  function clearAudioQueue() {
    if (audioCtxOut) {
      try {
        audioCtxOut.close();
      } catch (_) {}
      audioCtxOut = null;
      nextPlayTime = 0;
    }
  }

  function toggleDeviceById(devId) {
    const dev = latestDevicesMap[devId];
    if (!dev) return;
    const isOn = dev.state === "ON" || dev.state === "OPEN";
    const action = dev.type === "door" ? (isOn ? "close" : "open") : isOn ? "turn_off" : "turn_on";
    sendWs({ type: "manual_toggle", device_id: devId, action });
  }

  function renderDevices(devices) {
    devicesGrid.innerHTML = "";
    latestDevicesMap = {};
    devices.forEach((dev) => {
      latestDevicesMap[dev.id] = dev;
      const isOn = dev.state === "ON" || dev.state === "OPEN";
      let icon = "🔌";
      let activeClass = "";
      if (dev.type === "door") {
        icon = isOn ? "🔓" : "🚪";
        activeClass = isOn ? "active-on" : "";
      } else if (dev.type === "light") {
        icon = isOn ? "💡" : "🌑";
        activeClass = isOn ? "active-light" : "";
      } else if (dev.type === "fan") {
        icon = "🌀";
        activeClass = isOn ? "active-on" : "";
      } else if (dev.type === "ac") {
        icon = isOn ? "❄️" : "🌡️";
        activeClass = isOn ? "active-on" : "";
      } else if (dev.type === "siren") {
        icon = isOn ? "🚨" : "🔔";
        activeClass = isOn ? "active-siren" : "";
      } else if (dev.type === "pump") {
        icon = isOn ? "💧" : "🚰";
        activeClass = isOn ? "active-on" : "";
      }

      const isOfflineLocked =
        window._serverConnected === false &&
        (dev.id === "main_door" || dev.id === "alarm_siren");
      const stateLabel = isOfflineLocked ? "🔒 KHÓA" : dev.state;
      const chip = document.createElement("button");
      chip.className = `dev-chip ${activeClass}`;
      if (isOfflineLocked) {
        chip.style.borderColor = "#f59e0b";
        chip.style.opacity = "0.88";
      }
      chip.id = `dev-card-${dev.id}`;
      chip.title = isOfflineLocked
        ? `🔒 Đang ở chế độ Mạch Độc Lập (Offline): Khóa an ninh ${dev.name}`
        : `Bấm để bật/tắt ${dev.name} (${dev.gpio})`;
      chip.innerHTML = `
        <div class="dev-chip-top">
          <span class="dev-chip-icon">${isOfflineLocked ? "🔒" : icon}</span>
          <span class="dev-chip-state dev-state-pill ${isOn ? "on" : ""}">${stateLabel}</span>
        </div>
        <div class="dev-chip-name">${escapeHtml(dev.name)}</div>
        <div class="dev-chip-gpio">${escapeHtml(dev.gpio.split(" ")[0])} • ${isOfflineLocked ? "KHÓA OFFLINE" : "≥" + escapeHtml(dev.min_role)}</div>
      `;
      chip.addEventListener("click", () => toggleDeviceById(dev.id));
      devicesGrid.appendChild(chip);
    });

    if (window.SmartHome3D) {
      window.SmartHome3D.updateDevices(devices, window._latestMqtt, window._serverConnected !== false);
    }
  }

  function renderTimers(timers) {
    timerCount.textContent = String(timers.length);
    timersList.innerHTML = "";
    timers.forEach((t) => {
      const div = document.createElement("div");
      div.className = "timer-item";
      const rightLabel = t.target_vn_time
        ? `🕒 ${t.target_vn_time}`
        : `⏳ ${t.remaining_label || t.remaining_seconds + "s"}`;
      const ownerBadge = t.owner_name ? ` <small style="color:#38bdf8;">[T${t.owner_tier || 1}: ${escapeHtml(t.owner_name)}]</small>` : "";
      div.innerHTML = `
        <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
          <strong>${escapeHtml(t.device_name)}</strong> ➡️ <code>${escapeHtml(t.action_vi || t.action)}</code>${ownerBadge}
        </span>
        <span class="timer-countdown">${escapeHtml(rightLabel)}</span>
      `;
      timersList.appendChild(div);
    });
  }

  function renderRules(wordMappings, customAliases, ifElseRules, factoryAliases, systemPolicies) {
    const wordEntries = Object.entries(wordMappings || {});
    const aliasEntries = Object.entries(customAliases || {});
    const factoryEntries = Object.entries(factoryAliases || {});
    const ifElseList = ifElseRules || [];
    const customDirectives = (systemPolicies && Array.isArray(systemPolicies.custom_system_directives))
      ? systemPolicies.custom_system_directives
      : [];

    const total = wordEntries.length + aliasEntries.length + ifElseList.length + customDirectives.length;
    rulesCount.textContent = String(total);
    rulesList.innerHTML = "";

    // 0. Luật Hệ Thống do Admin Cấp 1 sửa bằng giọng nói
    customDirectives.forEach((d) => {
      const div = document.createElement("div");
      div.className = "rule-item";
      div.style.borderLeftColor = "#38bdf8";
      div.innerHTML = `
        <div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
          <span style="color:#38bdf8;font-weight:700;">[Luật Admin]</span> ${escapeHtml(d)}
        </div>
      `;
      rulesList.appendChild(div);
    });

    // 1. Đổi từ (Word Mappings)
    wordEntries.forEach(([w, m]) => {
      const div = document.createElement("div");
      div.className = "rule-item";
      div.style.borderLeftColor = "#f59e0b";
      div.innerHTML = `
        <div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
          <span style="color:#fbbf24;font-weight:700;">[Đổi từ]</span> "${escapeHtml(w)}" ➡️ ${escapeHtml(m)}
        </div>
      `;
      rulesList.appendChild(div);
    });

    // 2. Đổi lệnh / Khẩu lệnh (Command Phrases)
    aliasEntries.forEach(([phrase, steps]) => {
      const stepStr = steps.map((s) => `${s.device_id}:${s.action}`).join(", ");
      const div = document.createElement("div");
      div.className = "rule-item";
      div.style.borderLeftColor = "#22c55e";
      div.innerHTML = `
        <div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
          <span style="color:#4ade80;font-weight:700;">[Đổi lệnh]</span> "${escapeHtml(phrase)}" ➡️ ${escapeHtml(stepStr)}
        </div>
      `;
      rulesList.appendChild(div);
    });

    // 3. Quan hệ IF sát nghĩa (1 chiều hoặc 2 chiều) theo trạng thái thiết bị
    ifElseList.forEach((r) => {
      const div = document.createElement("div");
      div.className = "rule-item";
      div.style.borderLeftColor = "#a855f7";
      const elsePart = r.else_device_id
        ? ` | ELSE ➡️ ${r.else_action} ${r.else_device_name}`
        : ` (1 chiều: đóng/tắt giữ nguyên)`;
      const delayPart = r.delay_seconds > 0 ? ` (${r.delay_seconds}s)` : "";
      div.innerHTML = `
        <div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
          <span style="color:#c084fc;font-weight:700;">[IF]</span> NẾU ${escapeHtml(r.when_device_name)}=${escapeHtml(r.when_state)} THÌ${escapeHtml(delayPart)} ${escapeHtml(r.then_action)} ${escapeHtml(r.then_device_name)}${escapeHtml(elsePart)}
        </div>
      `;
      rulesList.appendChild(div);
    });

    // 4. Lệnh gốc nhà sản xuất
    factoryEntries.forEach(([phrase, steps]) => {
      const stepStr = steps.map((s) => `${s.device_id}:${s.action}`).join(", ");
      const div = document.createElement("div");
      div.className = "rule-item";
      div.style.borderLeftColor = "#64748b";
      div.innerHTML = `
        <div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#94a3b8;">
          <strong>[Gốc]</strong> "${escapeHtml(phrase)}" ➡️ ${escapeHtml(stepStr)}
        </div>
      `;
      rulesList.appendChild(div);
    });
  }

  function applySnapshot(snap) {
    if (Array.isArray(snap.users) && roleSelect) {
      snap.users.forEach((u) => {
        if (!u || !u.id) return;
        const exists = Array.from(roleSelect.options).some((o) => o.value === u.id);
        if (!exists) {
          const opt = document.createElement("option");
          opt.value = u.id;
          const icon = u.tier === 1 ? "👑" : u.tier === 2 ? "👨‍👩‍👧" : "🧒";
          const f0Tag = u.voice_f0_hz ? ` • F0: ${u.voice_f0_hz}Hz` : "";
          opt.textContent = `${icon} Tầng ${u.tier}: ${u.name}${f0Tag}`;
          roleSelect.insertBefore(opt, roleSelect.lastElementChild);
        }
      });
    }
    if (snap.current_user_id && Array.from(roleSelect.options).some((o) => o.value === snap.current_user_id)) {
      roleSelect.value = snap.current_user_id;
    } else if (snap.role && Array.from(roleSelect.options).some((o) => o.value === snap.role)) {
      roleSelect.value = snap.role;
    }
    window._serverConnected = snap.server_connected !== false;
    const btnServerToggle = document.getElementById("btnServerModeToggle");
    if (btnServerToggle) {
      if (window._serverConnected) {
        btnServerToggle.textContent = "🟢 Server Laptop: ONLINE";
        btnServerToggle.style.background = "linear-gradient(135deg,#059669,#0284c7)";
        btnServerToggle.style.borderColor = "#34d399";
        oledMode.textContent = "NodeMCU ESP8266: ONLINE";
      } else {
        btnServerToggle.textContent = "🟠 Mạch Độc Lập: OFFLINE (Mặc Định + Khóa Cửa)";
        btnServerToggle.style.background = "linear-gradient(135deg,#d97706,#b45309)";
        btnServerToggle.style.borderColor = "#fbbf24";
        oledMode.textContent = "ESP8266: OFFLINE (MẶC ĐỊNH)";
      }
    }

    oledRole.textContent = snap.current_user_name
      ? `T${snap.current_tier || 1}: ${snap.current_user_name}`
      : snap.role;
    renderDevices(snap.devices || []);

    // Cập nhật dữ liệu cảm biến từ MQTT snapshot
    if (snap.mqtt) {
      window._latestMqtt = snap.mqtt;
      if (window.SmartHome3D && window.SmartHome3D.updateSensors) {
        window.SmartHome3D.updateSensors(snap.mqtt, window._serverConnected);
      }
      const soil = snap.mqtt.soil_moisture_telemetry || {};
      const dht = snap.mqtt.dht11_telemetry || {};
      const soilVal = document.getElementById("sensorSoilVal");
      const soilSlider = document.getElementById("sensorSoilSlider");
      if (soilVal && soil.soil_moisture_pct !== undefined) {
        soilVal.textContent = Math.round(soil.soil_moisture_pct) + "% (" + (soil.status_label || "") + ")";
        if (soilSlider) soilSlider.value = Math.round(soil.soil_moisture_pct);
      }
      const dhtVal = document.getElementById("sensorDhtVal");
      const tempSlider = document.getElementById("sensorTempSlider");
      const tempLabel = document.getElementById("sensorTempLabel");
      const humLabel = document.getElementById("sensorHumLabel");
      if (dhtVal && dht.temp_c !== undefined) {
        dhtVal.textContent = Number(dht.temp_c).toFixed(1) + "°C | " + Math.round(dht.humidity_pct || 65) + "%";
        if (tempSlider) tempSlider.value = Number(dht.temp_c);
        if (tempLabel) tempLabel.textContent = Number(dht.temp_c).toFixed(1) + "°C";
        if (humLabel) humLabel.textContent = Math.round(dht.humidity_pct || 65) + "%";
      }
    }

    renderTimers(snap.timers || []);
    renderRules(
      snap.word_mappings,
      snap.custom_aliases,
      snap.if_else_rules || snap.chains,
      snap.factory_aliases,
      snap.system_policies
    );
  }

  function updateLatencyUI(toolMs, audioMs, leadMs) {
    if (toolMs !== null && toolMs !== undefined) {
      metricToolMs.textContent = `${toolMs} ms`;
    }
    if (audioMs !== null && audioMs !== undefined) {
      metricAudioMs.textContent = `${audioMs} ms`;
    }
    if (leadMs !== null && leadMs !== undefined) {
      if (leadMs >= 0) {
        metricLeadMs.textContent = `+${leadMs} ms`;
        metricOrderBadge.textContent = "✅ Bật TRƯỚC khi nói:";
        metricOrderBadge.style.color = "#4ade80";
      } else {
        metricLeadMs.textContent = `${leadMs} ms`;
        metricOrderBadge.textContent = "⚠️ Âm thanh trước:";
        metricOrderBadge.style.color = "#fbbf24";
      }
    }
  }

  async function loadVoiceSamples() {
    try {
      const res = await fetch("/api/voice_samples");
      const data = await res.json();
      voiceSamplesGrid.innerHTML = "";
      (data.samples || []).forEach((s) => {
        const btn = document.createElement("button");
        btn.className = "btn-wav-sample";
        btn.setAttribute("data-sample-id", s.id);
        btn.title = s.label;
        btn.innerHTML = `
          <span>🔊 "${escapeHtml(s.label)}"</span>
          <span style="font-size:10px;color:#38bdf8;flex-shrink:0;">${s.duration_sec}s</span>
        `;
        btn.addEventListener("click", () => {
          try {
            const sampleAudio = new Audio(`/test_audio/${s.id}.wav`);
            sampleAudio.volume = 0.9;
            sampleAudio.play().catch(() => {});
          } catch (_) {}
          liveUserTranscript.textContent = `[WAV 16kHz]: "${s.label}"...`;
          liveToolCall.innerHTML = "<em>(Đang chờ Gemini 3.8 Live gọi hàm...)</em>";
          liveAiTranscript.innerHTML = "<em>(Đang chờ phản hồi...)</em>";
          metricToolMs.textContent = "...";
          metricAudioMs.textContent = "...";
          metricLeadMs.textContent = "...";
          oledMainLine.textContent = `NGHE: "${s.label.toUpperCase()}"`;
          sendWs({ type: "play_wav_sample", sample_id: s.id });
        });
        voiceSamplesGrid.appendChild(btn);
      });
    } catch (e) {
      console.error("Failed to load voice samples:", e);
    }
  }

  function connectWebSocket() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);

    ws.onopen = () => {
      logEvent("Đã kết nối WebSocket tới Gateway Server.", "info");
    };

    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      switch (msg.type) {
        case "gemini_status":
          if (msg.connected) {
            geminiStatusBadge.className = "status-badge online";
            geminiStatusText.textContent = msg.message || "Đã kết nối Gemini 3.8 Live";
            oledMode.textContent = "NodeMCU ESP8266: ONLINE";
            logEvent(msg.message || "Đã kết nối Gemini 3.8 Live", "tool");
          } else {
            geminiStatusBadge.className = "status-badge connecting";
            geminiStatusText.textContent = msg.error || msg.message || "Đang kết nối...";
            if (msg.error) {
              geminiStatusBadge.className = "status-badge offline";
              oledMode.textContent = "ESP8266: STANDALONE";
              logEvent(msg.error, "err");
            }
          }
          break;

        case "system_prompt_updated":
          if (systemPromptPre) {
            systemPromptPre.textContent = msg.system_prompt;
          }
          break;

        case "state_snapshot":
          applySnapshot(msg.snapshot);
          break;

        case "server_mode_changed":
          window._serverConnected = msg.server_connected !== false;
          oledMainLine.textContent = window._serverConnected
            ? "🟢 SERVER LAPTOP: ONLINE (AI + CUSTOM + MỞ CỬA)"
            : "🟠 MẠCH OFFLINE: VỀ MẶC ĐỊNH & KHÓA CỬA CHÍNH";
          oledSubLine.textContent = msg.message || "";
          logEvent(msg.message || "Đã chuyển chế độ kết nối Server", window._serverConnected ? "tool" : "warn");
          break;

        case "device_updated":
          playRelayClick(msg.new_state === "ON" || msg.new_state === "OPEN");
          oledMainLine.textContent = `⚡ ${msg.device_name.toUpperCase()} -> ${msg.new_state}`;
          oledSubLine.textContent = `${msg.gpio} | Nguồn: ${msg.source}`;
          logEvent(
            `[3D & GPIO] ${msg.device_name}: ${msg.old_state} -> ${msg.new_state} (${msg.source})`,
            "tool"
          );
          break;

        case "rbac_blocked":
          oledMainLine.textContent = `🚫 CHẶN QUYỀN (${msg.role})`;
          oledSubLine.textContent = msg.reason;
          logEvent(`[RBAC CHẶN] ${msg.reason}`, "err");
          break;

        case "tool_call_executed": {
          const argStr = JSON.stringify(msg.args);
          liveToolCall.textContent = `${msg.name}(${argStr}) — ${msg.tool_ms} ms!`;
          updateLatencyUI(msg.tool_ms, null, null);
          logEvent(
            `⚡ [TOOL_CALL ${msg.tool_ms} ms] ${msg.name} -> ${msg.result?.summary || msg.result?.message || "OK"}`,
            msg.result?.ok === false ? "err" : "tool"
          );
          break;
        }

        case "input_transcription":
          liveUserTranscript.textContent = msg.full_text;
          break;

        case "output_transcription":
          liveAiTranscript.textContent = msg.full_text;
          break;

        case "first_audio_metrics":
          updateLatencyUI(msg.tool_ms, msg.audio_ms, msg.lead_ms);
          logEvent(
            `🔊 [AUDIO ${msg.audio_ms} ms] Công tắc bật trước giọng nói: ${
              msg.lead_ms !== null ? "+" + msg.lead_ms + " ms" : "N/A"
            }`,
            "info"
          );
          break;

        case "audio_chunk":
          playPcm24kChunk(msg.pcm24k_b64);
          break;

        case "interrupted":
          clearAudioQueue();
          logEvent("Người dùng ngắt lời — đã dừng phát âm thanh cũ.", "warn");
          break;

        case "turn_complete":
          updateLatencyUI(msg.tool_ms, msg.audio_ms, msg.lead_ms);
          logEvent(
            `✅ [XONG] "${msg.heard}" -> "${msg.said}" (tool=${msg.tool_ms ?? "-"}ms, audio=${msg.audio_ms ?? "-"}ms)`,
            "info"
          );
          break;

        case "device_already_in_state":
          oledMainLine.textContent = `ℹ️ ${msg.message.toUpperCase()}`;
          oledSubLine.textContent = `${msg.device_name} đang ở sẵn trạng thái ${msg.state}`;
          logEvent(`ℹ️ [ĐÃ Ở SẴN TRẠNG THÁI] ${msg.message}`, "warn");
          break;

        case "rule_confirmation_requested":
          oledMainLine.textContent = "❓ XÁC NHẬN CÀI ĐẶT LUẬT MỚI";
          oledSubLine.textContent = msg.message;
          logEvent(`❓ [CHỜ XÁC NHẬN LUẬT] ${msg.message}`, "warn");
          break;

        case "voice_auth_result": {
          const a = msg.analysis || {};
          const badge = document.getElementById("voiceAuthBadge");
          if (badge) {
            if (a.authorized) {
              badge.style.color = "#4ade80";
              badge.textContent = `✅ ${a.speaker_label} (F0: ${a.f0_hz} Hz • Khớp: ${Math.round((a.similarity || 0.95) * 100)}%)`;
            } else {
              badge.style.color = "#f87171";
              const stTxt = a.silent_ignore
                ? `Lần ${a.strike_count}: 🔇 IM LẶNG TUYỆT ĐỐI`
                : `Lần ${a.strike_count}/2: Chặn & Cảnh báo`;
              badge.textContent = `🚫 ${a.speaker_label} (F0: ${a.f0_hz} Hz • ${stTxt})`;
            }
          }
          break;
        }

        case "voice_auth_rejected":
          oledMainLine.textContent = `🚫 GIỌNG LẠ (LẦN ${msg.strike_count}/2): KHÔNG CÓ QUYỀN`;
          oledSubLine.textContent = `F0=${msg.f0_hz}Hz -> "${msg.rejection_speech}"`;
          liveUserTranscript.textContent = `[Giọng 2 - F0: ${msg.f0_hz}Hz]: "${msg.label}"`;
          liveToolCall.textContent = `🚫 CHẶN QUYỀN GIỌNG NÓI (Lần ${msg.strike_count}/2)`;
          liveAiTranscript.textContent = msg.rejection_speech;
          logEvent(
            `🚫 [GIỌNG KHÔNG ĐƯỢC PHÉP - LẦN ${msg.strike_count}/2] F0=${msg.f0_hz}Hz -> AI đáp: "${msg.rejection_speech}"`,
            "err"
          );
          break;

        case "voice_auth_silent_ignored":
          oledMainLine.textContent = `🔇 ĐÃ NGHE GIỌNG LẠ (LẦN ${msg.strike_count}) — IM LẶNG!`;
          oledSubLine.textContent = `Quá 2 lần cảnh báo -> Nghe nhưng KHÔNG phản hồi`;
          liveUserTranscript.textContent = `[Giọng 2 - Lần ${msg.strike_count} (Đã nghe)]: "${msg.label}"`;
          liveToolCall.textContent = `🔇 ĐÃ NGHE NHƯNG BỎ QUA (Lần ${msg.strike_count} > 2)`;
          liveAiTranscript.innerHTML = `<strong style="color:#f87171;">🔇 (Im lặng tuyệt đối — Không phản hồi từ lần thứ 3)</strong>`;
          metricToolMs.textContent = "CHẶN";
          metricAudioMs.textContent = "IM LẶNG";
          metricLeadMs.textContent = "0 ms";
          logEvent(
            `🔇 [LẦN ${msg.strike_count} — IM LẶNG TUYỆT ĐỐI] Vẫn nghe "${msg.label}" (F0=${msg.f0_hz}Hz) nhưng KHÔNG phản hồi!`,
            "warn"
          );
          break;

        case "voice_enrolled": {
          const r = msg.result || {};
          if (r.ok) {
            const badge = document.getElementById("voiceAuthBadge");
            if (badge && r.profile) {
              badge.style.color = "#4ade80";
              badge.textContent = `✅ ${r.profile.name} (F0: ${r.profile.f0_hz} Hz • Phổ: ${r.profile.centroid_hz} Hz)`;
            }
            oledMainLine.textContent = "✅ ĐÃ LƯU TẦN SỐ GIỌNG CHỦ NHÀ";
            oledSubLine.textContent = r.message;
            logEvent(`🎙️ ${r.message}`, "tool");
          } else {
            logEvent(`⚠️ Lỗi thu âm giọng: ${r.error}`, "err");
          }
          break;
        }

        case "reset_confirmation_requested":
          oledMainLine.textContent = "❓ BẠN MUỐN RESET TẤT CẢ ĐÚNG KHÔNG?";
          oledSubLine.textContent = "Chờ xác nhận: Nói 'Đúng rồi' hoặc 'Không'";
          logEvent(`❓ [XÁC NHẬN RESET] ${msg.message}`, "warn");
          break;

        case "factory_reset_completed":
          oledMainLine.textContent = "🔄 ĐÃ RESET VỀ NGUYÊN BẢN 100%";
          oledSubLine.textContent = msg.message;
          logEvent(`🔄 ${msg.message}`, "warn");
          break;

        case "voice_enrollment_countdown":
          oledMainLine.textContent = `⏳ CẤP QUYỀN TRONG 3, 2, 1...`;
          oledSubLine.textContent = msg.message || "Chờ đèn nháy 1 phát để bắt đầu nói...";
          logEvent(`🎙️ [CHUẨN BỊ THU ÂM] ${msg.message}`, "warn");
          break;

        case "start_voice_capture":
          oledMainLine.textContent = `💡 ĐÈN ĐÃ NHÁY — HÃY NÓI TRONG ${msg.duration_seconds || 5} GIÂY!`;
          oledSubLine.textContent = msg.message || "Đang thu âm giọng nói người mới...";
          logEvent(`💡 [BẮT ĐẦU THU ÂM ${msg.duration_seconds || 5}s] ${msg.message}`, "tool");
          runBrowserVoiceEnrollmentCapture(msg.duration_seconds || 5);
          break;

        case "voice_enrollment_captured":
          oledMainLine.textContent = `✅ ĐÃ THU ÂM ĐỦ — ĐANG PHÂN TÍCH...`;
          oledSubLine.textContent = msg.message;
          logEvent(`🧬 ${msg.message}`, "info");
          break;

        case "voice_enrollment_analyzed": {
          const badge = document.getElementById("voiceAuthBadge");
          if (badge) {
            badge.style.color = "#38bdf8";
            badge.textContent = `🧬 Đã phân tích (F0: ${msg.f0_hz} Hz • Cấp ${msg.target_tier}) — Chờ đặt tên...`;
          }
          oledMainLine.textContent = `🧬 ĐÃ PHÂN TÍCH XONG (F0: ${msg.f0_hz} Hz)`;
          oledSubLine.textContent = `Sẵn sàng cấp Cấp ${msg.target_tier} — Người ấy tên là gì?`;
          logEvent(`🧬 [PHÂN TÍCH XONG] ${msg.message}`, "tool");
          break;
        }

        case "permission_granted": {
          const u = msg.target_user || {};
          const badge = document.getElementById("voiceAuthBadge");
          if (badge && u.name) {
            badge.style.color = "#4ade80";
            const f0Str = u.voice_f0_hz ? ` • F0: ${u.voice_f0_hz} Hz` : "";
            badge.textContent = `✅ Đã cấp Cấp ${u.tier}: ${u.name}${f0Str}`;
          }
          oledMainLine.textContent = `✅ ĐÃ CẤP QUYỀN CẤP ${u.tier}: ${(u.name || "").toUpperCase()}`;
          oledSubLine.textContent = msg.message;
          logEvent(`🛡️ ${msg.message}`, "tool");
          break;
        }

        case "permission_revoked":
          oledMainLine.textContent = `🚫 ĐÃ HỦY QUYỀN: ${(msg.target_user?.name || "").toUpperCase()}`;
          oledSubLine.textContent = msg.message;
          logEvent(`🚫 ${msg.message}`, "warn");
          break;

        case "query_policy_updated":
          oledMainLine.textContent = `🔐 QUYỀN HỎI: ${msg.query_permission_mode === "open_all" ? "MỞ TẤT CẢ" : "THEO TỪNG CẤP"}`;
          oledSubLine.textContent = msg.message;
          logEvent(`🔐 ${msg.message}`, "tool");
          break;

        case "system_policy_updated":
          oledMainLine.textContent = `👑 ĐÃ SỬA LUẬT HỆ THỐNG BẰNG GIỌNG NÓI`;
          oledSubLine.textContent = msg.message;
          logEvent(`👑 [LUẬT HỆ THỐNG CẤP 1] ${msg.message}`, "tool");
          break;

        case "error":
          logEvent(`LỖI: ${msg.message}`, "err");
          break;
      }
    };

    ws.onclose = () => {
      geminiStatusBadge.className = "status-badge offline";
      geminiStatusText.textContent = "Mất kết nối — Đang kết nối lại...";
      oledMode.textContent = "ESP8266: STANDALONE";
      setTimeout(connectWebSocket, 2000);
    };
  }

  function sendWs(payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
    }
  }

  async function startMic() {
    try {
      micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      micAudioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      const source = micAudioCtx.createMediaStreamSource(micStream);
      micProcessor = micAudioCtx.createScriptProcessor(2048, 1, 1);

      wasSpeaking = false;
      silenceStartMs = 0;

      micProcessor.onaudioprocess = (e) => {
        if (!isRecording) return;
        const input = e.inputBuffer.getChannelData(0);
        let sumSq = 0;
        const pcm16 = new Int16Array(input.length);
        for (let i = 0; i < input.length; i++) {
          const s = Math.max(-1, Math.min(1, input[i]));
          sumSq += s * s;
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }
        const rms = Math.sqrt(sumSq / input.length);
        const pct = Math.min(100, Math.round(rms * 450));
        micMeterBar.style.width = `${pct}%`;

        if (isCapturingEnrollment) {
          enrollmentChunks.push(new Uint8Array(pcm16.buffer.slice(0)));
          return;
        }

        const isSpeech = rms > 0.018;
        const nowMs = performance.now();

        if (isSpeech) {
          wasSpeaking = true;
          silenceStartMs = 0;
          micStateLabel.textContent = "🟢 Đang nói...";
        } else if (wasSpeaking) {
          if (silenceStartMs === 0) {
            silenceStartMs = nowMs;
          } else if (nowMs - silenceStartMs > 450) {
            wasSpeaking = false;
            silenceStartMs = 0;
            micStateLabel.textContent = "⏳ Chờ AI...";
            sendWs({ type: "mic_speech_ended" });
          }
        }

        const bytes = new Uint8Array(pcm16.buffer);
        let binary = "";
        for (let i = 0; i < bytes.byteLength; i++) {
          binary += String.fromCharCode(bytes[i]);
        }
        sendWs({
          type: "mic_chunk",
          pcm16k_b64: btoa(binary),
          is_speech: isSpeech,
        });
      };

      source.connect(micProcessor);
      micProcessor.connect(micAudioCtx.destination);

      isRecording = true;
      btnMicToggle.classList.add("recording");
      micBtnText.textContent = "TẮT MIC";
      btnManualEndTurn.disabled = false;
      micStateLabel.textContent = "Đang nghe";
      logEvent("🎙️ Đã bật Microphone trực tiếp (16kHz PCM).", "tool");
    } catch (err) {
      logEvent(`Không thể mở Mic: ${err.message}`, "err");
    }
  }

  function stopMic() {
    isRecording = false;
    if (micProcessor) {
      micProcessor.disconnect();
      micProcessor = null;
    }
    if (micAudioCtx) {
      micAudioCtx.close();
      micAudioCtx = null;
    }
    if (micStream) {
      micStream.getTracks().forEach((t) => t.stop());
      micStream = null;
    }
    btnMicToggle.classList.remove("recording");
    micBtnText.textContent = "BẬT MIC NÓI CHUYỆN";
    btnManualEndTurn.disabled = true;
    micStateLabel.textContent = "Tắt";
    micMeterBar.style.width = "0%";
    logEvent("Đã tắt Microphone.", "info");
  }

  async function runBrowserVoiceEnrollmentCapture(durationSec = 5) {
    isCapturingEnrollment = true;
    enrollmentChunks = [];
    let tempStream = null;
    let tempCtx = null;
    let tempProc = null;

    if (!isRecording) {
      try {
        tempStream = await navigator.mediaDevices.getUserMedia({
          audio: {
            channelCount: 1,
            sampleRate: 16000,
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        });
        tempCtx = new (window.AudioContext || window.webkitAudioContext)({
          sampleRate: 16000,
        });
        const src = tempCtx.createMediaStreamSource(tempStream);
        tempProc = tempCtx.createScriptProcessor(2048, 1, 1);
        tempProc.onaudioprocess = (ev) => {
          const input = ev.inputBuffer.getChannelData(0);
          let sumSq = 0;
          const pcm16 = new Int16Array(input.length);
          for (let i = 0; i < input.length; i++) {
            const s = Math.max(-1, Math.min(1, input[i]));
            sumSq += s * s;
            pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
          }
          const rms = Math.sqrt(sumSq / input.length);
          micMeterBar.style.width = `${Math.min(100, Math.round(rms * 450))}%`;
          if (isCapturingEnrollment) {
            enrollmentChunks.push(new Uint8Array(pcm16.buffer.slice(0)));
          }
        };
        src.connect(tempProc);
        tempProc.connect(tempCtx.destination);
      } catch (err) {
        logEvent(`⚠️ Không mở được Mic vật lý (${err.message}), dùng mẫu thu âm mô phỏng 16kHz.`, "warn");
      }
    }

    let remaining = durationSec;
    micStateLabel.textContent = `🔴 Thu âm mẫu (${remaining}s)...`;
    oledMainLine.textContent = `ĐANG THU ÂM GIỌNG NÓI (${remaining}s)...`;
    const timer = setInterval(() => {
      remaining -= 1;
      if (remaining > 0) {
        micStateLabel.textContent = `🔴 Thu âm mẫu (${remaining}s)...`;
        oledMainLine.textContent = `ĐANG THU ÂM GIỌNG NÓI (${remaining}s)...`;
      }
    }, 1000);

    setTimeout(() => {
      clearInterval(timer);
      isCapturingEnrollment = false;
      if (tempProc) tempProc.disconnect();
      if (tempCtx) tempCtx.close();
      if (tempStream) tempStream.getTracks().forEach((t) => t.stop());
      if (!isRecording) micMeterBar.style.width = "0%";
      micStateLabel.textContent = isRecording ? "Đang nghe" : "Đang phân tích giọng...";

      let totalLen = 0;
      for (const c of enrollmentChunks) totalLen += c.byteLength;
      const merged = new Uint8Array(totalLen);
      let offset = 0;
      for (const c of enrollmentChunks) {
        merged.set(c, offset);
        offset += c.byteLength;
      }
      let binary = "";
      const chunkStep = 8192;
      for (let i = 0; i < merged.byteLength; i += chunkStep) {
        binary += String.fromCharCode.apply(null, merged.subarray(i, i + chunkStep));
      }
      sendWs({
        type: "complete_voice_enrollment",
        pcm16k_b64: btoa(binary),
      });
    }, durationSec * 1000);
  }

  btnMicToggle.addEventListener("click", () => {
    if (isRecording) stopMic();
    else startMic();
  });

  btnManualEndTurn.addEventListener("click", () => {
    sendWs({ type: "mic_speech_ended" });
    micStateLabel.textContent = "⚡ Đã ngắt!";
  });

  function submitTextCommand(cmd) {
    if (!cmd) return;
    liveUserTranscript.textContent = cmd;
    liveToolCall.innerHTML = "<em>(Đang chờ Gemini 3.8 Live gọi hàm...)</em>";
    liveAiTranscript.innerHTML = "<em>(Đang chờ phản hồi...)</em>";
    metricToolMs.textContent = "...";
    metricAudioMs.textContent = "...";
    metricLeadMs.textContent = "...";
    oledMainLine.textContent = `LỆNH: "${cmd.toUpperCase()}"`;
    sendWs({ type: "send_text", text: cmd });
  }

  textCmdForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const val = textCmdInput.value.trim();
    if (!val) return;
    submitTextCommand(val);
    textCmdInput.value = "";
  });

  document.querySelectorAll(".btn-scenario").forEach((btn) => {
    btn.addEventListener("click", () => {
      const cmd = btn.getAttribute("data-cmd");
      submitTextCommand(cmd);
    });
  });

  document.querySelectorAll(".btn-cam").forEach((btn) => {
    btn.addEventListener("click", () => {
      const preset = btn.getAttribute("data-cam");
      if (preset !== "rotate") {
        document.querySelectorAll(".btn-cam").forEach((b) => {
          if (b.getAttribute("data-cam") !== "rotate") b.classList.remove("active");
        });
        btn.classList.add("active");
      } else {
        btn.classList.toggle("active");
      }
      if (window.SmartHome3D) {
        window.SmartHome3D.setCameraView(preset);
      }
    });
  });

  roleSelect.addEventListener("change", () => {
    const newRole = roleSelect.value;
    sendWs({ type: "set_role", role: newRole });
    logEvent(`🛡️ Đã chuyển vai trò RBAC sang: ${newRole}`, "warn");
  });

  btnFactoryReset.addEventListener("click", () => {
    sendWs({ type: "manual_factory_reset" });
  });

  btnClearLog.addEventListener("click", () => {
    eventLog.innerHTML = "";
  });

  // Nút chuyển chế độ Kết nối Server Laptop (Online) <-> Mạch Độc Lập (Offline Mặc Định)
  const btnServerModeToggle = document.getElementById("btnServerModeToggle");
  if (btnServerModeToggle) {
    btnServerModeToggle.addEventListener("click", async () => {
      const nextConnected = window._serverConnected === false ? true : false;
      sendWs({ type: "set_server_mode", server_connected: nextConnected });
      try {
        await fetch("/api/server_mode", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ server_connected: nextConnected }),
        });
      } catch (_) {}
    });
  }

  // Nút thu âm tự do 8 giây để lấy Tần số Giọng Chủ Nhà
  const btnEnroll8s = document.getElementById("btnEnroll8s");
  if (btnEnroll8s) {
    btnEnroll8s.addEventListener("click", async () => {
      try {
        btnEnroll8s.disabled = true;
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: { channelCount: 1, sampleRate: 16000 },
        });
        const ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
        const src = ctx.createMediaStreamSource(stream);
        const proc = ctx.createScriptProcessor(4096, 1, 1);
        const chunks = [];
        proc.onaudioprocess = (ev) => {
          const inp = ev.inputBuffer.getChannelData(0);
          const p16 = new Int16Array(inp.length);
          for (let i = 0; i < inp.length; i++) {
            const s = Math.max(-1, Math.min(1, inp[i]));
            p16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
          }
          chunks.push(new Uint8Array(p16.buffer));
        };
        src.connect(proc);
        proc.connect(ctx.destination);

        for (let sec = 8; sec >= 1; sec--) {
          btnEnroll8s.textContent = `🔴 Đang thu tần số (${sec}s)... Hãy nói tự do!`;
          oledMainLine.textContent = `🎙️ ĐANG THU VÂN GIỌNG (${sec}s)...`;
          await new Promise((r) => setTimeout(r, 1000));
        }

        proc.disconnect();
        src.disconnect();
        stream.getTracks().forEach((t) => t.stop());
        ctx.close();

        const totalLen = chunks.reduce((acc, c) => acc + c.byteLength, 0);
        const merged = new Uint8Array(totalLen);
        let offset = 0;
        for (const c of chunks) {
          merged.set(c, offset);
          offset += c.byteLength;
        }
        let binary = "";
        for (let i = 0; i < merged.byteLength; i++) {
          binary += String.fromCharCode(merged[i]);
        }
        sendWs({ type: "enroll_owner_voice", pcm16k_b64: btoa(binary) });
        btnEnroll8s.textContent = "✅ Đã Thu Xong 8s (Bấm để thu lại)";
        btnEnroll8s.disabled = false;
      } catch (e) {
        logEvent(`Không thể thu âm 8s: ${e.message}`, "err");
        btnEnroll8s.textContent = "🎙️ Thu Âm 8s Đăng Ký Giọng";
        btnEnroll8s.disabled = false;
      }
    });
  }

  // ──────── Thanh Slider / Nút Cảm biến 3D (Đồng bộ 1:1 với Wokwi) ────────
  const sensorSoilSlider = document.getElementById("sensorSoilSlider");
  if (sensorSoilSlider) {
    sensorSoilSlider.addEventListener("input", async () => {
      const pct = parseFloat(sensorSoilSlider.value);
      const soilVal = document.getElementById("sensorSoilVal");
      if (soilVal) soilVal.textContent = pct + "%";
      try {
        await fetch("/api/soil_moisture", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ soil_moisture_pct: pct }),
        });
      } catch (_) {}
    });
  }

  const sensorTempSlider = document.getElementById("sensorTempSlider");
  if (sensorTempSlider) {
    sensorTempSlider.addEventListener("input", async () => {
      const t = parseFloat(sensorTempSlider.value);
      const tempLabel = document.getElementById("sensorTempLabel");
      if (tempLabel) tempLabel.textContent = t.toFixed(1) + "°C";
      const dhtVal = document.getElementById("sensorDhtVal");
      const humLabel = document.getElementById("sensorHumLabel");
      const hum = humLabel ? parseInt(humLabel.textContent) || 65 : 65;
      if (dhtVal) dhtVal.textContent = t.toFixed(1) + "°C | " + hum + "%";
      try {
        await fetch("/api/dht11", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ temp_c: t, humidity_pct: hum }),
        });
      } catch (_) {}
    });
  }

  const btnIrLearn = document.getElementById("btnIrLearn3d");
  if (btnIrLearn) {
    btnIrLearn.addEventListener("click", async () => {
      btnIrLearn.textContent = "📡 Đang thu ĐH...";
      try {
        const res = await fetch("/api/ir_learn", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ device_name: "Điều hòa Casper", command_action: "open" }),
        });
        const data = await res.json();
        const irVal = document.getElementById("sensorIrVal");
        if (irVal) irVal.textContent = (data.learned && data.learned.hex_code) || data.hex_code || "0x20DF10EF";
        btnIrLearn.textContent = "✅ Đã thu ĐH";
        if (window.SmartHome3D && window.SmartHome3D.triggerIr38kHzVisualBlast) {
          window.SmartHome3D.triggerIr38kHzVisualBlast();
        }
      } catch (_) {
        btnIrLearn.textContent = "⚠️ Lỗi IR";
      }
      setTimeout(() => {
        btnIrLearn.textContent = "❄️ Thu mã ĐH";
      }, 2500);
    });
  }

  const btnIrLearnFan = document.getElementById("btnIrLearnFan3d");
  if (btnIrLearnFan) {
    btnIrLearnFan.addEventListener("click", async () => {
      btnIrLearnFan.textContent = "📡 Đang thu Quạt...";
      try {
        const res = await fetch("/api/ir_learn", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ device_name: "Quạt trần", command_action: "open" }),
        });
        const data = await res.json();
        const irVal = document.getElementById("sensorIrVal");
        if (irVal) irVal.textContent = (data.learned && data.learned.hex_code) || data.hex_code || "0xA90";
        btnIrLearnFan.textContent = "✅ Đã thu Quạt";
        if (window.SmartHome3D && window.SmartHome3D.triggerIr38kHzVisualBlast) {
          window.SmartHome3D.triggerIr38kHzVisualBlast();
        }
      } catch (_) {
        btnIrLearnFan.textContent = "⚠️ Lỗi IR";
      }
      setTimeout(() => {
        btnIrLearnFan.textContent = "🌀 Thu mã Quạt";
      }, 2500);
    });
  }

  if (window.SmartHome3D) {
    window.SmartHome3D.init("house3dViewport", "house3dLabels", toggleDeviceById);
  }
  loadVoiceSamples();
  connectWebSocket();
})();
