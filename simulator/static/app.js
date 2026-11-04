"use strict";

(() => {
  const noopEl = {
    textContent: "",
    innerHTML: "",
    value: "",
    checked: true,
    disabled: false,
    hidden: false,
    className: "",
    style: {},
    classList: { add() {}, remove() {}, toggle() {} },
    addEventListener() {},
    prepend() {},
    appendChild() {},
    setAttribute() {},
    getAttribute() { return ""; },
  };
  const byId = (a, b) => document.getElementById(a) || (b ? document.getElementById(b) : null);

  const geminiStatusBadge = byId("geminiStatusBadge", "btnToggleServer") || noopEl;
  const geminiStatusText = byId("geminiStatusText", "connText") || noopEl;
  const connDot = byId("connDot") || noopEl;
  const roleSelect = byId("roleSelect", "selActiveSpeaker") || noopEl;
  const btnFactoryReset = byId("btnFactoryReset", "btnReset") || noopEl;
  const vnClockText = byId("vnClockText");

  const btnTogglePromptModal = byId("btnTogglePromptModal");
  const btnClosePromptModal = byId("btnClosePromptModal");
  const promptModal = byId("promptModal");
  const systemPromptPre = byId("systemPromptPre");

  const oledMode = byId("oledMode") || noopEl;
  const oledRole = byId("oledRole") || noopEl;
  const oledMainLine = byId("oledMainLine") || noopEl;
  const oledSubLine = byId("oledSubLine") || noopEl;

  const devicesGrid = byId("devicesGrid", "deviceGrid") || noopEl;
  const deviceActiveSummary = byId("deviceActiveSummary");
  const timersList = byId("timersList", "timerList") || noopEl;
  const timerCount = byId("timerCount") || noopEl;
  const rulesList = byId("rulesList", "ruleList") || noopEl;
  const rulesCount = byId("rulesCount") || noopEl;
  const scheduleEmptyText = byId("scheduleEmptyText");

  const btnMicToggle = byId("btnMicToggle", "btnMicLive") || noopEl;
  const micBtnText = byId("micBtnText", "micBtnLabel") || noopEl;
  const btnManualEndTurn = byId("btnManualEndTurn", "btnMicCommit") || noopEl;
  const micStateLabel = byId("micStateLabel", "micStatus") || noopEl;
  const micDot = byId("micDot") || noopEl;
  const micMeterBar = byId("micMeterBar") || noopEl;
  const chkPlayAiVoice = byId("chkPlayAiVoice", "chkSpeakReply") || noopEl;

  const liveUserTranscript = byId("liveUserTranscript", "liveTranscript") || noopEl;
  const liveToolCall = byId("liveToolCall") || noopEl;
  const liveAiTranscript = byId("liveAiTranscript", "liveAiReply") || noopEl;
  const emptyVoice = byId("emptyVoice");
  const voiceResults = byId("voiceResults");
  const voiceLockoutNotice = byId("voiceLockoutNotice");

  function showVoiceResults() {
    if (emptyVoice) emptyVoice.hidden = true;
    if (voiceResults && voiceResults.classList) voiceResults.classList.add("visible");
  }
  function setUserTranscriptText(txt) {
    showVoiceResults();
    liveUserTranscript.textContent = txt;
  }
  function setAiReplyText(txt) {
    showVoiceResults();
    liveAiTranscript.textContent = txt;
  }

  const textCmdForm = byId("textCmdForm") || noopEl;
  const textCmdInput = byId("textCmdInput", "txtCommand") || noopEl;

  const metricToolMs = byId("metricToolMs") || noopEl;
  const metricAudioMs = byId("metricAudioMs") || noopEl;
  const metricLeadMs = byId("metricLeadMs") || noopEl;
  const metricOrderBadge = byId("metricOrderBadge") || noopEl;

  const btnScheduleVnTime = byId("btnScheduleVnTime");
  const voiceSamplesGrid = byId("voiceSamplesGrid");
  const eventLog = byId("eventLog");
  const btnClearLog = byId("btnClearLog");

  let ws = null;
  let audioCtxOut = null;
  let nextPlayTime = 0;
  let latestDevicesMap = {};
  let currentTimersCount = 0;
  let currentRulesCount = 0;

  // Mic capture state
  let isRecording = false;
  let micStream = null;
  let micAudioCtx = null;
  let micProcessor = null;
  let wasSpeaking = false;
  let silenceStartMs = 0;
  let isCapturingEnrollment = false;
  let enrollmentChunks = [];

  function updateScheduleEmptyState() {
    const hasAny = currentTimersCount > 0 || currentRulesCount > 0;
    if (scheduleEmptyText) {
      scheduleEmptyText.hidden = hasAny;
    }
    if (timersList && timersList !== noopEl) {
      timersList.hidden = currentTimersCount === 0;
    }
    if (rulesList && rulesList !== noopEl) {
      rulesList.hidden = currentRulesCount === 0;
    }
  }

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

    if (btnScheduleVnTime) {
      const plus1Min = new Date(now.getTime() + 60 * 1000);
      const hmAmPm = new Intl.DateTimeFormat("en-US", {
        timeZone: "Asia/Ho_Chi_Minh",
        hour: "2-digit",
        minute: "2-digit",
        hour12: true,
      }).format(plus1Min);
      btnScheduleVnTime.setAttribute("data-cmd", `Hẹn đúng ${hmAmPm} bật quạt trần nhé`);
      btnScheduleVnTime.textContent = `Hẹn ${hmAmPm} bật quạt`;
    }
  }
  setInterval(updateVnClock, 1000);
  updateVnClock();

  if (btnTogglePromptModal && promptModal) {
    btnTogglePromptModal.addEventListener("click", () => {
      promptModal.style.display = promptModal.style.display === "none" ? "flex" : "none";
    });
  }
  if (btnClosePromptModal && promptModal) {
    btnClosePromptModal.addEventListener("click", () => {
      promptModal.style.display = "none";
    });
  }

  function logEvent(text, level = "info") {
    if (!eventLog) return;
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
    if (chkPlayAiVoice && chkPlayAiVoice.checked === false) return;
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
    const roleVal = roleSelect && roleSelect.value ? roleSelect.value : "";
    if (ws && ws.readyState === WebSocket.OPEN) {
      sendWs({ type: "manual_toggle", device_id: devId, action, role: roleVal });
    } else {
      fetch("/api/device", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_id: devId, action, source: "MANUAL_UI" }),
      })
        .then((r) => r.json())
        .then((data) => {
          if (data && data.snapshot) applySnapshot(data.snapshot);
        })
        .catch(() => {});
    }
  }

  function getDeviceRoomLabel(dev, isOn, isOfflineLocked) {
    if (isOfflineLocked) return "Khóa ngoại tuyến";
    if (dev.type === "door") return isOn ? "Đang mở" : "Đã khóa";
    const roomMap = {
      living_room_light: "Phòng khách",
      fan: "Phòng khách",
      ac: "Phòng ngủ",
      bedroom_light: "Phòng ngủ",
      garden_pump: "Sân vườn",
      alarm_siren: "Toàn nhà",
    };
    const room = roomMap[dev.id] || "";
    const st = isOn ? "Đang bật" : "Đang tắt";
    return room ? `${room} · ${st}` : st;
  }

  function renderDevices(devices) {
    if (!devicesGrid || devicesGrid === noopEl) return;
    devicesGrid.innerHTML = "";
    latestDevicesMap = {};
    let activeCount = 0;

    devices.forEach((dev) => {
      latestDevicesMap[dev.id] = dev;
      const isOn = dev.state === "ON" || dev.state === "OPEN";
      if (isOn) activeCount++;

      let iconId = "i-lamp";
      if (dev.type === "door") iconId = "i-door";
      else if (dev.type === "light") iconId = "i-lamp";
      else if (dev.type === "fan") iconId = "i-fan";
      else if (dev.type === "ac") iconId = "i-snow";
      else if (dev.type === "siren") iconId = "i-bell";
      else if (dev.type === "pump") iconId = "i-drop";

      const isOfflineLocked =
        window._serverConnected === false &&
        (dev.id === "main_door" || dev.id === "alarm_siren");

      const card = document.createElement("div");
      card.className = "device";
      card.id = `dev-card-${dev.id}`;
      const roomText = getDeviceRoomLabel(dev, isOn, isOfflineLocked);

      card.innerHTML = `
        <span class="device-icon ${isOn ? "" : "off"}">
          <svg class="icon"><use href="#${iconId}"/></svg>
        </span>
        <span class="device-copy">
          <span class="device-name">${escapeHtml(dev.name)}</span><br>
          <span class="device-room">${escapeHtml(roomText)}</span>
        </span>
        <label class="switch" aria-label="${escapeHtml(dev.name)}">
          <input type="checkbox" ${isOn ? "checked" : ""} ${isOfflineLocked ? "disabled" : ""}>
          <span></span>
        </label>
      `;

      const swInput = card.querySelector(".switch input");
      const swLabel = card.querySelector(".switch");
      if (swLabel) {
        swLabel.addEventListener("click", (e) => {
          e.stopPropagation();
        });
      }
      if (swInput) {
        swInput.addEventListener("change", (e) => {
          e.stopPropagation();
          toggleDeviceById(dev.id);
        });
      }
      card.addEventListener("click", () => {
        if (!isOfflineLocked) toggleDeviceById(dev.id);
      });
      devicesGrid.appendChild(card);
    });

    if (deviceActiveSummary) {
      deviceActiveSummary.textContent = `${activeCount} đang bật`;
    }

    if (window.SmartHome3D) {
      window.SmartHome3D.updateDevices(devices, window._latestMqtt, window._serverConnected !== false);
    }
  }

  function renderTimers(timers) {
    currentTimersCount = timers.length;
    timerCount.textContent = String(timers.length);
    timersList.innerHTML = "";
    timers.forEach((t) => {
      const div = document.createElement("div");
      div.className = "timer-item";
      const rightLabel = t.target_vn_time
        ? `${t.target_vn_time}`
        : `${t.remaining_label || t.remaining_seconds + "s"}`;
      div.innerHTML = `
        <span>${escapeHtml(t.device_name)} · ${escapeHtml(t.action_vi || t.action)}</span>
        <span class="timer-countdown">${escapeHtml(rightLabel)}</span>
      `;
      timersList.appendChild(div);
    });
    updateScheduleEmptyState();
  }

  function renderRules(wordMappings, customAliases, ifElseRules, factoryAliases, systemPolicies) {
    const wordEntries = Object.entries(wordMappings || {});
    const aliasEntries = Object.entries(customAliases || {});
    const ifElseList = ifElseRules || [];
    const customDirectives = (systemPolicies && Array.isArray(systemPolicies.custom_system_directives))
      ? systemPolicies.custom_system_directives
      : [];

    const total = wordEntries.length + aliasEntries.length + ifElseList.length + customDirectives.length;
    currentRulesCount = total;
    rulesCount.textContent = String(total);
    rulesList.innerHTML = "";

    customDirectives.forEach((d) => {
      const div = document.createElement("div");
      div.className = "rule-item";
      div.innerHTML = `<span>${escapeHtml(d)}</span>`;
      rulesList.appendChild(div);
    });

    wordEntries.forEach(([w, m]) => {
      const div = document.createElement("div");
      div.className = "rule-item";
      div.innerHTML = `<span>"${escapeHtml(w)}" → ${escapeHtml(m)}</span>`;
      rulesList.appendChild(div);
    });

    aliasEntries.forEach(([phrase, steps]) => {
      const stepStr = steps.map((s) => `${s.device_id}:${s.action}`).join(", ");
      const div = document.createElement("div");
      div.className = "rule-item";
      div.innerHTML = `<span>"${escapeHtml(phrase)}" → ${escapeHtml(stepStr)}</span>`;
      rulesList.appendChild(div);
    });

    ifElseList.forEach((r) => {
      const div = document.createElement("div");
      div.className = "rule-item";
      const delayPart = r.delay_seconds > 0 ? ` (${r.delay_seconds}s)` : "";
      div.innerHTML = `<span>Khi ${escapeHtml(r.when_device_name)} ${escapeHtml(r.when_state)}${escapeHtml(delayPart)} → ${escapeHtml(r.then_action)} ${escapeHtml(r.then_device_name)}</span>`;
      rulesList.appendChild(div);
    });

    updateScheduleEmptyState();
  }

  function updateConnectionUI(connected) {
    window._serverConnected = connected !== false;
    if (connDot && connDot !== noopEl) {
      connDot.classList.toggle("offline", !window._serverConnected);
    }
    if (geminiStatusText && geminiStatusText !== noopEl) {
      geminiStatusText.textContent = window._serverConnected ? "Đã kết nối" : "Mất kết nối";
    }
    if (geminiStatusBadge && geminiStatusBadge !== noopEl && geminiStatusBadge.setAttribute) {
      geminiStatusBadge.setAttribute("aria-label", window._serverConnected ? "Đã kết nối" : "Mất kết nối");
    }
  }

  function applySnapshot(snap) {
    if (Array.isArray(snap.users) && roleSelect && roleSelect.options) {
      snap.users.forEach((u) => {
        if (!u || !u.id) return;
        const exists = Array.from(roleSelect.options).some((o) => o.value === u.id);
        if (!exists) {
          const opt = document.createElement("option");
          opt.value = u.id;
          const roleName = u.tier === 1 ? "Chủ nhà" : u.tier === 2 ? "Gia đình" : "Khách";
          opt.textContent = `${roleName} · ${u.name}`;
          roleSelect.insertBefore(opt, roleSelect.lastElementChild);
        }
      });
    }
    if (roleSelect && roleSelect.options) {
      if (snap.current_user_id && Array.from(roleSelect.options).some((o) => o.value === snap.current_user_id)) {
        roleSelect.value = snap.current_user_id;
      } else if (snap.role && Array.from(roleSelect.options).some((o) => o.value === snap.role)) {
        roleSelect.value = snap.role;
      }
    }

    updateConnectionUI(snap.server_connected !== false);
    renderDevices(snap.devices || []);

    if (snap.mqtt) {
      window._latestMqtt = snap.mqtt;
      if (window.SmartHome3D && window.SmartHome3D.updateSensors) {
        window.SmartHome3D.updateSensors(snap.mqtt, window._serverConnected);
      }
      const soil = snap.mqtt.soil_moisture_telemetry || {};
      const dht = snap.mqtt.dht11_telemetry || {};
      const soilLabel = document.getElementById("sensorSoilLabel") || document.getElementById("sensorSoilVal");
      if (soilLabel && soil.soil_moisture_pct !== undefined) {
        soilLabel.textContent = Math.round(soil.soil_moisture_pct) + "%";
      }
      const tempLabel = document.getElementById("sensorTempLabel") || document.getElementById("sensorDhtVal");
      if (tempLabel && dht.temp_c !== undefined) {
        tempLabel.textContent = Math.round(Number(dht.temp_c)) + "°C";
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
      metricLeadMs.textContent = leadMs >= 0 ? `+${leadMs} ms` : `${leadMs} ms`;
    }
  }

  async function loadVoiceSamples() {
    if (!voiceSamplesGrid) return;
    try {
      const res = await fetch("/api/voice_samples");
      const data = await res.json();
      voiceSamplesGrid.innerHTML = "";
      (data.samples || []).forEach((s) => {
        const btn = document.createElement("button");
        btn.className = "quick";
        btn.setAttribute("data-sample-id", s.id);
        btn.textContent = s.label;
        btn.addEventListener("click", () => {
          liveUserTranscript.textContent = s.label;
          liveUserTranscript.classList.remove("muted");
          sendWs({ type: "play_wav_sample", sample_id: s.id });
        });
        voiceSamplesGrid.appendChild(btn);
      });
    } catch (_) {}
  }

  function connectWebSocket() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);

    ws.onopen = () => {
      updateConnectionUI(true);
      logEvent("Đã kết nối tới máy chủ.", "info");
    };

    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      switch (msg.type) {
        case "gemini_status":
          if (msg.connected !== false) {
            updateConnectionUI(true);
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
          updateConnectionUI(msg.server_connected !== false);
          if (msg.message) {
            setAiReplyText(msg.message);
          }
          break;

        case "device_updated":
          playRelayClick(msg.new_state === "ON" || msg.new_state === "OPEN");
          logEvent(`${msg.device_name}: ${msg.old_state} -> ${msg.new_state}`, "tool");
          break;

        case "rbac_blocked":
          setAiReplyText(msg.reason || "Bạn chưa có quyền thực hiện thao tác này.");
          logEvent(msg.reason, "err");
          renderDevices(Object.values(latestDevicesMap));
          break;

        case "tool_call_executed":
          updateLatencyUI(msg.tool_ms, null, null);
          break;

        case "input_transcription":
          setUserTranscriptText(msg.full_text);
          break;

        case "output_transcription":
          setAiReplyText(msg.full_text);
          break;

        case "first_audio_metrics":
          updateLatencyUI(msg.tool_ms, msg.audio_ms, msg.lead_ms);
          break;

        case "audio_chunk":
          window._lastGeminiAudioChunkTs = performance.now();
          playPcm24kChunk(msg.pcm24k_b64);
          break;

        case "interrupted":
          clearAudioQueue();
          break;

        case "turn_complete":
          updateLatencyUI(msg.tool_ms, msg.audio_ms, msg.lead_ms);
          break;

        case "device_already_in_state":
          setAiReplyText(msg.message);
          break;

        case "rule_confirmation_requested":
          setAiReplyText(msg.message);
          break;

        case "voice_auth_result": {
          const a = msg.analysis || {};
          if (a.active_user_id && roleSelect && roleSelect.options) {
            const hasOpt = Array.from(roleSelect.options).some((o) => o.value === a.active_user_id);
            if (hasOpt) {
              roleSelect.value = a.active_user_id;
            }
          }
          if (voiceLockoutNotice) {
            if (!a.authorized && a.strike_count) {
              voiceLockoutNotice.hidden = false;
              voiceLockoutNotice.textContent = a.silent_ignore
                ? "Tạm khóa điều khiển giọng nói do thử sai nhiều lần."
                : "Chưa xác thực được giọng nói. Vui lòng thử lại.";
            } else {
              voiceLockoutNotice.hidden = true;
            }
          }
          break;
        }

        case "voice_auth_rejected": {
          const rejSpeech = msg.rejection_speech || (msg.strike_count === 1
            ? "Tôi không được phép nhận lệnh từ người lạ."
            : "Tôi sẽ không trả lời bạn lần nữa.");
          if (msg.label && msg.label !== "Giọng nói trực tiếp qua Mic") {
            setUserTranscriptText(msg.label);
          }
          setAiReplyText(rejSpeech);
          if (voiceLockoutNotice) {
            voiceLockoutNotice.hidden = false;
            voiceLockoutNotice.textContent = rejSpeech;
          }
          // Server-Side Rejection TTS 24kHz: phát âm thanh server qua Web Audio API (không dùng speechSynthesis)
          if (msg.pcm24k_b64) {
            playPcm24kChunk(msg.pcm24k_b64);
          }
          break;
        }

        case "voice_auth_silent_ignored":
          clearAudioQueue();
          if (msg.label && msg.label !== "Giọng nói trực tiếp qua Mic") {
            setUserTranscriptText(msg.label);
          }
          setAiReplyText("Đã tạm ngưng phản hồi với giọng nói chưa đăng ký.");
          break;

        case "voice_enrolled": {
          const r = msg.result || {};
          if (r.ok) {
            setAiReplyText("Đã lưu giọng nói.");
          } else {
            setAiReplyText("Chưa nhận rõ giọng nói. Vui lòng thu lại.");
          }
          break;
        }

        case "reset_confirmation_requested":
          setAiReplyText(msg.message || "Bạn muốn đặt lại toàn bộ cài đặt?");
          break;

        case "factory_reset_completed":
          setAiReplyText(msg.message || "Đã đặt lại mô phỏng.");
          break;

        case "voice_enrollment_countdown":
          setAiReplyText(msg.message || "Chuẩn bị thu âm mẫu giọng...");
          break;

        case "start_voice_capture":
          setAiReplyText(msg.message || "Đang thu âm mẫu giọng...");
          runBrowserVoiceEnrollmentCapture(msg.duration_seconds || 5);
          break;

        case "voice_enrollment_captured":
          setAiReplyText(msg.message || "Đang kiểm tra mẫu giọng...");
          break;

        case "voice_enrollment_analyzed":
          setAiReplyText(msg.message || "Đã nhận mẫu giọng. Vui lòng đọc tên người dùng.");
          break;

        case "permission_granted":
          setAiReplyText(msg.message || "Đã cập nhật quyền truy cập.");
          break;

        case "permission_revoked":
          setAiReplyText(msg.message || "Đã thu hồi quyền truy cập.");
          break;

        case "query_policy_updated":
        case "system_policy_updated":
          setAiReplyText(msg.message || "Đã cập nhật cài đặt.");
          break;

        case "error":
          setAiReplyText(msg.message || "Có lỗi xảy ra, vui lòng thử lại.");
          break;
      }
    };

    ws.onclose = () => {
      updateConnectionUI(false);
      setTimeout(connectWebSocket, 2000);
    };
  }

  function sendWs(payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
    }
  }

  function setMicListeningState(listening) {
    isRecording = listening;
    btnMicToggle.classList.toggle("recording", listening);
    micBtnText.textContent = listening ? "Đang nghe…" : "Bắt đầu nói";
    btnManualEndTurn.hidden = !listening;
    btnManualEndTurn.disabled = !listening;
    micStateLabel.textContent = listening ? "Đang nghe" : "";
    micDot.classList.toggle("listening", listening);
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
      if (micAudioCtx.state === "suspended") {
        await micAudioCtx.resume();
      }
      const source = micAudioCtx.createMediaStreamSource(micStream);
      micProcessor = micAudioCtx.createScriptProcessor(2048, 1, 1);

      wasSpeaking = false;
      silenceStartMs = 0;
      let noiseFloorRms = 0.008;
      let speechStartMs = 0;

      micProcessor.onaudioprocess = (e) => {
        if (!isRecording) return;
        const rawInput = e.inputBuffer.getChannelData(0);
        const actualSr = micAudioCtx ? micAudioCtx.sampleRate : 16000;
        let input = rawInput;
        if (actualSr && actualSr !== 16000) {
          const outLen = Math.max(1, Math.round((rawInput.length * 16000) / actualSr));
          input = new Float32Array(outLen);
          const ratio = rawInput.length / outLen;
          for (let i = 0; i < outLen; i++) {
            input[i] = rawInput[Math.min(rawInput.length - 1, Math.floor(i * ratio))];
          }
        }
        let sumSq = 0;
        const pcm16 = new Int16Array(input.length);
        for (let i = 0; i < input.length; i++) {
          const s = Math.max(-1, Math.min(1, input[i]));
          sumSq += s * s;
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }
        const rms = Math.sqrt(sumSq / input.length);
        const pct = Math.min(100, Math.round(rms * 550));
        micMeterBar.style.width = `${pct}%`;

        if (isCapturingEnrollment) {
          enrollmentChunks.push(new Uint8Array(pcm16.buffer.slice(0)));
          return;
        }

        const aiBusy = Boolean(
          audioCtxOut && nextPlayTime > audioCtxOut.currentTime + 0.08
        );
        if (aiBusy) {
          return;
        }

        const speechThreshold = Math.min(0.05, Math.max(0.018, noiseFloorRms * 2.1));
        const isSpeech = rms > speechThreshold;
        if (!isSpeech) {
          noiseFloorRms = noiseFloorRms * 0.9 + rms * 0.1;
        } else {
          noiseFloorRms = Math.min(0.025, noiseFloorRms * 0.995 + rms * 0.005);
        }
        const nowMs = performance.now();

        if (isSpeech) {
          if (!wasSpeaking) {
            speechStartMs = nowMs;
          }
          wasSpeaking = true;
          silenceStartMs = 0;
          micStateLabel.textContent = "Đang nghe";
          if (speechStartMs > 0 && nowMs - speechStartMs > 4500) {
            wasSpeaking = false;
            speechStartMs = 0;
            silenceStartMs = 0;
            micStateLabel.textContent = "Đang xử lý";
            sendWs({ type: "mic_speech_ended" });
          }
        } else if (wasSpeaking) {
          if (silenceStartMs === 0) {
            silenceStartMs = nowMs;
          } else if (nowMs - silenceStartMs > 460) {
            wasSpeaking = false;
            speechStartMs = 0;
            silenceStartMs = 0;
            micStateLabel.textContent = "Đang xử lý";
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
      setMicListeningState(true);
    } catch (err) {
      liveAiTranscript.textContent = "Không thể mở microphone. Vui lòng kiểm tra quyền truy cập.";
    }
  }

  function stopMic() {
    const hadActiveMic = isRecording;
    wasSpeaking = false;
    silenceStartMs = 0;
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
    if (hadActiveMic) {
      sendWs({ type: "mic_speech_ended" });
    }
    setMicListeningState(false);
    micMeterBar.style.width = "0%";
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
          const pcm16 = new Int16Array(input.length);
          for (let i = 0; i < input.length; i++) {
            const s = Math.max(-1, Math.min(1, input[i]));
            pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
          }
          if (isCapturingEnrollment) {
            enrollmentChunks.push(new Uint8Array(pcm16.buffer.slice(0)));
          }
        };
        src.connect(tempProc);
        tempProc.connect(tempCtx.destination);
      } catch (_) {}
    }

    setTimeout(() => {
      isCapturingEnrollment = false;
      if (tempProc) tempProc.disconnect();
      if (tempCtx) tempCtx.close();
      if (tempStream) tempStream.getTracks().forEach((t) => t.stop());

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
    stopMic();
  });

  function submitTextCommand(cmd) {
    if (!cmd) return;
    setUserTranscriptText(cmd);
    setAiReplyText("Đang xử lý...");
    sendWs({ type: "send_text", text: cmd });
  }

  textCmdForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const val = textCmdInput.value.trim();
    if (!val) return;
    submitTextCommand(val);
    textCmdInput.value = "";
  });

  document.querySelectorAll(".btn-scenario, .quick-cmd, .quick").forEach((btn) => {
    btn.addEventListener("click", () => {
      const cmd = btn.getAttribute("data-cmd") || btn.getAttribute("data-text") || btn.textContent.trim();
      submitTextCommand(cmd);
    });
  });

  roleSelect.addEventListener("change", () => {
    const newRole = roleSelect.value;
    sendWs({ type: "set_role", role: newRole });
  });

  btnFactoryReset.addEventListener("click", () => {
    if (window.confirm("Bạn muốn đặt lại toàn bộ trạng thái mô phỏng?")) {
      sendWs({ type: "manual_factory_reset" });
    }
  });

  if (btnClearLog && eventLog) {
    btnClearLog.addEventListener("click", () => {
      eventLog.innerHTML = "";
    });
  }

  const btnServerModeToggle = byId("btnServerModeToggle", "btnToggleServer");
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

  // Modal Đăng ký giọng nói
  const firstPageVoiceModal = byId("firstPageVoiceModal");
  const btnCloseFirstVoiceModal = byId("btnCloseFirstVoiceModal");
  const btnCancelFirstVoiceModal = byId("btnCancelFirstVoiceModal");
  const btnHoldRecordVoice = byId("btnHoldRecordVoice");
  const firstVoiceResultBox = byId("firstVoiceResultBox");

  function closeVoiceModal() {
    if (firstPageVoiceModal) firstPageVoiceModal.classList.add("hidden");
  }
  if (btnCloseFirstVoiceModal) btnCloseFirstVoiceModal.addEventListener("click", closeVoiceModal);
  if (btnCancelFirstVoiceModal) btnCancelFirstVoiceModal.addEventListener("click", closeVoiceModal);
  if (btnHoldRecordVoice) {
    btnHoldRecordVoice.addEventListener("click", async () => {
      if (firstVoiceResultBox) firstVoiceResultBox.textContent = "Đang thu âm...";
      try {
        const emailEl = byId("firstVoiceEmailInput");
        const email = emailEl ? emailEl.value : "nep94121@gmail.com";
        const res = await fetch("/api/auth3/enroll_voice_sample", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email,
            spoken_text: "Xin chào hệ thống Nhà Thông Minh Bách Khoa, tôi đọc câu này để lưu mẫu giọng nói gốc lên máy chủ.",
            hold_duration_sec: 3.2,
          }),
        });
        const data = await res.json();
        if (firstVoiceResultBox) {
          firstVoiceResultBox.textContent = data.ok ? "Đã lưu mẫu giọng" : "Thử lại";
        }
      } catch (_) {
        if (firstVoiceResultBox) firstVoiceResultBox.textContent = "Thử lại";
      }
    });
  }

  if (window.SmartHome3D) {
    window.SmartHome3D.init("house3dViewport", "house3dLabels", toggleDeviceById);
  }
  loadVoiceSamples();
  connectWebSocket();
})();
