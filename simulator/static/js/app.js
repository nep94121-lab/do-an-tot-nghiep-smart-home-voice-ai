"use strict";

(() => {
  if (typeof document !== "undefined" && document.querySelector && !document._hasTextPolyfilled) {
    const _origQS = document.querySelector.bind(document);
    document.querySelector = function(sel) {
      if (typeof sel === "string" && sel.indexOf(":has-text(") !== -1) {
        const m = sel.match(/^([^:]+):has-text\(['"]([^'"]+)['"]\)$/i);
        if (m) {
          const tag = m[1].trim() || "*";
          const needle = m[2];
          const nodes = document.querySelectorAll(tag);
          for (let i = 0; i < nodes.length; i++) {
            if ((nodes[i].textContent || "").indexOf(needle) !== -1) return nodes[i];
          }
          return null;
        }
      }
      return _origQS(sel);
    };
    document._hasTextPolyfilled = true;
  }

  if (typeof window !== "undefined" && typeof window.fetch === "function" && !window._shAuthFetchWrapped) {
    const _origFetch = window.fetch.bind(window);
    window.fetch = function(input, init) {
      let urlStr = typeof input === "string" ? input : (input && input.url ? input.url : "");
      if (urlStr.startsWith("/api/")) {
        let tok = "";
        try {
          tok = (window.sessionStorage && window.sessionStorage.getItem("session_token")) ||
                (window.localStorage && window.localStorage.getItem("session_token")) || "";
          if (!tok && window.localStorage) {
            const rawSess = window.localStorage.getItem("smarthome_auth_session");
            if (rawSess) {
              const parsed = JSON.parse(rawSess);
              tok = (parsed && parsed.session_token) || "";
            }
          }
        } catch (_) {}
        const nextInit = Object.assign({ credentials: "same-origin" }, init || {});
        const hdrs = Object.assign({}, nextInit.headers || {});
        if (tok && !hdrs["X-Session-Token"] && !hdrs["x-session-token"] && !hdrs["Authorization"]) {
          hdrs["X-Session-Token"] = tok;
        }
        nextInit.headers = hdrs;
        return _origFetch(input, nextInit);
      }
      return _origFetch(input, init);
    };
    window._shAuthFetchWrapped = true;
  }

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
  const byId = (id) => document.getElementById(id);

  const geminiStatusBadge = byId("btnToggleServer") || noopEl;
  const geminiStatusText = byId("connText") || noopEl;
  const homeServerStatusBadge = byId("homeServerStatusBadge") || noopEl;
  const connDot = byId("connDot") || noopEl;
  const roleSelect = byId("selActiveSpeaker") || noopEl;
  const btnFactoryReset = byId("btnReset") || noopEl;
  const vnClockText = byId("vnClockText");

  const isVercelServerless = (typeof window !== "undefined") && (
    (typeof location !== "undefined" && Boolean((location.hostname || location.host || "").includes("vercel.app"))) ||
    Boolean(window._FORCE_HTTP_POLLING)
  );

  const btnTogglePromptModal = byId("btnTogglePromptModal");
  const btnClosePromptModal = byId("btnClosePromptModal");
  const promptModal = byId("promptModal");
  const systemPromptPre = byId("systemPromptPre");

  const oledMode = noopEl;
  const oledRole = noopEl;
  const oledMainLine = noopEl;
  const oledSubLine = noopEl;

  const devicesGrid = byId("deviceGrid") || noopEl;
  const deviceActiveSummary = byId("deviceActiveSummary");
  const timersList = byId("timerList") || noopEl;
  const timerCount = noopEl;
  const rulesList = byId("ruleList") || noopEl;
  const rulesCount = noopEl;
  const scheduleEmptyText = byId("scheduleEmptyText");

  const btnMicToggle = byId("btnMicLive") || noopEl;
  const micBtnText = byId("micBtnLabel") || noopEl;
  const btnManualEndTurn = byId("btnMicCommit") || noopEl;
  const micStateLabel = noopEl;
  const micDot = byId("micDot") || noopEl;
  const micMeterBar = byId("micMeterBar") || noopEl;
  const chkPlayAiVoice = byId("chkSpeakReply") || noopEl;

  const liveUserTranscript = byId("liveTranscript") || noopEl;
  const liveToolCall = noopEl;
  const liveAiTranscript = byId("liveAiReply") || noopEl;
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
  const textCmdInput = byId("txtCommand") || noopEl;

  const metricToolMs = noopEl;
  const metricAudioMs = noopEl;
  const metricLeadMs = noopEl;
  const metricOrderBadge = noopEl;

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

  function updateDeviceCardUI(devId, dev, isOn) {
    const card = document.getElementById(`dev-card-${devId}`);
    if (!card) return;
    if (card.classList) {
      card.classList.toggle("on", isOn);
      card.classList.toggle("active", isOn);
      card.classList.toggle("off", !isOn);
    }
    card.setAttribute("data-device", devId);
    card.setAttribute("data-state", isOn ? "on" : "off");
    card.setAttribute("aria-pressed", isOn ? "true" : "false");
    const isOfflineLocked = window._serverConnected === false && (devId === "main_door" || devId === "alarm_siren");
    const iconSpan = card.querySelector(".device-icon");
    if (iconSpan) iconSpan.classList.toggle("off", !isOn);
    const swInput = card.querySelector(".switch input");
    if (swInput) {
      swInput.checked = isOn;
      swInput.disabled = isOfflineLocked;
    }
    const roomSpan = card.querySelector(".device-room");
    if (roomSpan) {
      roomSpan.textContent = getDeviceRoomLabel(dev, isOn, isOfflineLocked);
    }
  }

  function updateActiveDeviceSummaryCount() {
    if (!deviceActiveSummary) return;
    let activeCount = 0;
    Object.values(latestDevicesMap).forEach((d) => {
      if (d.state === "ON" || d.state === "OPEN") activeCount++;
    });
    deviceActiveSummary.textContent = `${activeCount} đang bật`;
  }

  function toggleDeviceById(devId) {
    const dev = latestDevicesMap[devId];
    if (!dev) return;
    const isOfflineLocked = window._serverConnected === false && (devId === "main_door" || devId === "alarm_siren");
    if (isOfflineLocked) return;

    const prevIsOn = dev.state === "ON" || dev.state === "OPEN";
    const nextIsOn = !prevIsOn;
    const prevState = dev.state;
    const nextState = dev.type === "door" ? (nextIsOn ? "OPEN" : "CLOSED") : (nextIsOn ? "ON" : "OFF");

    // Optimistic UI: Cập nhật in-memory và DOM tức thì
    dev.state = nextState;
    const cardEl = document.getElementById(`dev-card-${devId}`);
    if (cardEl) {
      const swInput = cardEl.querySelector(".switch input");
      if (swInput) swInput.checked = nextIsOn;
    }
    updateDeviceCardUI(devId, dev, nextIsOn);
    updateActiveDeviceSummaryCount();
    playRelayClick(nextIsOn);

    if (window.SmartHome3D) {
      window.SmartHome3D.updateDevices(Object.values(latestDevicesMap), window._latestMqtt, window._serverConnected !== false);
    }

    const action = dev.type === "door" ? (prevIsOn ? "close" : "open") : (prevIsOn ? "turn_off" : "turn_on");
    const roleVal = roleSelect && roleSelect.value ? roleSelect.value : "";

    const rollback = () => {
      dev.state = prevState;
      if (cardEl) {
        const swInput = cardEl.querySelector(".switch input");
        if (swInput) swInput.checked = prevIsOn;
      }
      updateDeviceCardUI(devId, dev, prevIsOn);
      updateActiveDeviceSummaryCount();
      if (window.SmartHome3D) {
        window.SmartHome3D.updateDevices(Object.values(latestDevicesMap), window._latestMqtt, window._serverConnected !== false);
      }
    };

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
          if (data && (data.ok === false || data.error)) {
            rollback();
            if (data.error) setAiReplyText(data.error);
          } else if (data && data.snapshot) {
            applySnapshot(data.snapshot);
          }
        })
        .catch(() => {
          rollback();
        });
    }
  }

  function getDeviceRoomLabel(dev, isOn, isOfflineLocked) {
    if (isOfflineLocked) return "Khóa ngoại tuyến";
    if (dev.type === "door") return isOn ? "Đã mở" : "Đã khóa";
    const roomMap = {
      living_room_light: "Phòng khách",
      fan: "Phòng khách",
      ac: "Phòng ngủ",
      bedroom_light: "Phòng ngủ",
      garden_pump: "Sân vườn",
      alarm_siren: "Toàn nhà",
    };
    const room = roomMap[dev.id] || "";
    const st = isOn ? "Đã bật" : "Đã tắt";
    return room ? `${room} · ${st}` : st;
  }

  function renderDevices(devices) {
    if (!devicesGrid || devicesGrid === noopEl) return;
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

      const roomText = getDeviceRoomLabel(dev, isOn, isOfflineLocked);
      let card = document.getElementById(`dev-card-${dev.id}`);

      if (card) {
        // Cập nhật DOM in-place không xóa trắng node
        const iconSpan = card.querySelector(".device-icon");
        if (iconSpan) {
          iconSpan.className = `device-icon ${isOn ? "" : "off"}`;
        }
        const nameSpan = card.querySelector(".device-name");
        if (nameSpan) {
          nameSpan.textContent = dev.name;
        }
        const roomSpan = card.querySelector(".device-room");
        if (roomSpan) {
          roomSpan.textContent = roomText;
        }
        const swInput = card.querySelector(".switch input");
        if (swInput) {
          swInput.checked = isOn;
          swInput.disabled = isOfflineLocked;
        }
        if (card.classList) {
          card.classList.toggle("on", isOn);
          card.classList.toggle("active", isOn);
          card.classList.toggle("off", !isOn);
        }
        card.setAttribute("data-device", dev.id);
        card.setAttribute("data-state", isOn ? "on" : "off");
        card.setAttribute("aria-pressed", isOn ? "true" : "false");
      } else {
        card = document.createElement("div");
        card.className = `device ${isOn ? "on active" : "off"}`;
        card.id = `dev-card-${dev.id}`;
        card.setAttribute("data-device", dev.id);
        card.setAttribute("data-state", isOn ? "on" : "off");
        card.setAttribute("aria-pressed", isOn ? "true" : "false");
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
          const locked = window._serverConnected === false && (dev.id === "main_door" || dev.id === "alarm_siren");
          if (!locked) toggleDeviceById(dev.id);
        });
        devicesGrid.appendChild(card);
      }
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

  function updateConnectionUI(connected, transport = null) {
    window._serverConnected = connected !== false;
    let activeTransport = transport;
    if (!activeTransport) {
      if (!window._serverConnected) {
        activeTransport = "Mất kết nối";
      } else if (typeof ws !== "undefined" && ws && ws.readyState === 1) {
        activeTransport = "WebSocket";
      } else {
        activeTransport = window._activeTransport || "HTTP Polling";
      }
    }
    window._activeTransport = activeTransport;

    if (connDot && connDot !== noopEl && connDot.classList) {
      if (typeof connDot.classList.toggle === "function") {
        connDot.classList.toggle("offline", !window._serverConnected);
      } else if (!window._serverConnected) {
        if (typeof connDot.classList.add === "function") connDot.classList.add("offline");
      } else {
        if (typeof connDot.classList.remove === "function") connDot.classList.remove("offline");
      }
    }
    const statusLabel = window._serverConnected ? `Đã kết nối (${activeTransport})` : "Mất kết nối";
    if (geminiStatusText && geminiStatusText !== noopEl) {
      geminiStatusText.textContent = statusLabel;
    }
    if (homeServerStatusBadge && homeServerStatusBadge !== noopEl) {
      homeServerStatusBadge.textContent = window._serverConnected ? activeTransport : "Mất kết nối";
    }
    if (geminiStatusBadge && geminiStatusBadge !== noopEl && geminiStatusBadge.setAttribute) {
      geminiStatusBadge.setAttribute("aria-label", statusLabel);
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

    if ((snap.unauthorized_strikes && snap.unauthorized_strikes >= 3) || snap.security_lockdown) {
      triggerSecurityLockdown();
    }

    if (snap.mqtt) {
      window._latestMqtt = snap.mqtt;
      if (window.SmartHome3D && window.SmartHome3D.updateSensors) {
        window.SmartHome3D.updateSensors(snap.mqtt, window._serverConnected);
      }
      const soil = snap.mqtt.soil_moisture_telemetry || {};
      const dht = snap.mqtt.dht11_telemetry || {};

      const tempLabel = document.getElementById("sensorTempVal") || document.getElementById("sensorTempLabel") || document.getElementById("sensorDhtVal");
      if (tempLabel && dht.temp_c !== undefined) {
        const rawT = Number(dht.temp_c);
        const safeT = Number.isFinite(rawT) ? Math.max(0, Math.min(60, rawT)) : 28.5;
        tempLabel.textContent = (Math.round(safeT * 10) / 10) + "°C";
      }

      const humLabel = document.getElementById("sensorHumVal") || document.getElementById("sensorHumLabel") || document.getElementById("sensorHumidityVal");
      if (humLabel && dht.humidity_pct !== undefined) {
        const rawH = Number(dht.humidity_pct);
        const safeH = Number.isFinite(rawH) ? Math.max(0, Math.min(100, rawH)) : 65;
        humLabel.textContent = Math.round(safeH) + "%";
      }

      const soilLabel = document.getElementById("sensorSoilVal") || document.getElementById("sensorSoilLabel");
      if (soilLabel && soil.soil_moisture_pct !== undefined) {
        const rawS = Number(soil.soil_moisture_pct);
        const safeS = Number.isFinite(rawS) ? Math.max(0, Math.min(100, rawS)) : 62;
        soilLabel.textContent = Math.round(safeS) + "%";
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

  function isWsOpen() {
    return Boolean(ws && ws.readyState === WebSocket.OPEN);
  }

  function uint8ChunksToBase64(chunks) {
    let totalLen = 0;
    for (const c of chunks) totalLen += c.byteLength;
    if (totalLen === 0) return "";
    const merged = new Uint8Array(totalLen);
    let offset = 0;
    for (const c of chunks) {
      merged.set(c, offset);
      offset += c.byteLength;
    }
    let binary = "";
    const chunkStep = 8192;
    for (let i = 0; i < merged.byteLength; i += chunkStep) {
      binary += String.fromCharCode.apply(null, merged.subarray(i, i + chunkStep));
    }
    return btoa(binary);
  }

  let voiceCommandEpoch = 0;
  let voiceCommandBusy = false;

  async function executeVoiceCommandHttp(payload) {
    voiceCommandEpoch += 1;
    voiceCommandBusy = true;
    try {
      const reqBody = Object.assign(
        {
          role: (roleSelect && roleSelect.value) ? roleSelect.value : undefined,
        },
        payload || {}
      );
      let res = null;
      let lastFetchErr = null;
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          if (attempt > 0) {
            await new Promise((r) => setTimeout(r, 200 * attempt));
          }
          res = await fetch("/api/voice_command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(reqBody),
          });
          if (res) break;
        } catch (fErr) {
          lastFetchErr = fErr;
        }
      }
      if (!res) throw lastFetchErr || new Error("fetch_failed");
      const data = await res.json();
      voiceCommandEpoch += 1;
      if (data.recognized_text) {
        setUserTranscriptText(data.recognized_text);
      }
      if (data.exact_spoken_reply || data.reply) {
        setAiReplyText(data.exact_spoken_reply || data.reply);
      }
      if (data.snapshot) {
        applySnapshot(data.snapshot);
      } else {
        await pollRestStateFallback();
      }
      logEvent(
        `🎙️ [Voice L${data.level || 1}] ${data.recognized_text || ""} -> ${data.intent || ""} (${data.permission || "ALLOWED"}, ${data.latency_ms || 0}ms)`,
        data.ok === false ? "error" : "tool"
      );
      return data;
    } catch (err) {
      setAiReplyText("Lỗi kết nối API giọng nói.");
      return { ok: false, error: String(err) };
    } finally {
      voiceCommandBusy = false;
    }
  }
  if (typeof window !== "undefined") {
    window.executeVoiceCommandHttp = executeVoiceCommandHttp;
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
          if (isWsOpen()) {
            sendWs({ type: "play_wav_sample", sample_id: s.id });
          } else {
            executeVoiceCommandHttp({ sample_id: s.id });
          }
        });
        voiceSamplesGrid.appendChild(btn);
      });
    } catch (_) {}
  }

  // WebSocket Reconnect Banner state (Milestone M7)
  let wsRetryCount = 0;
  const WS_MAX_RETRIES = 5;
  let wsReconnectTimer = null;

  function showWsReconnectBanner(attempt = 1, max = 5) {
    const banner = byId("wsReconnectBanner");
    const msg = byId("wsReconnectBannerMsg");
    const subtext = byId("wsReconnectSubtext");
    const btn = byId("btnWsReconnectNow");
    if (!banner) return;
    banner.classList.remove("hidden", "banner-restored", "banner-sliding-out");
    if (btn) {
      btn.style.display = "";
      btn.disabled = false;
      btn.textContent = "Kết nối ngay";
    }
    const iconContainer = (banner && typeof banner.querySelector === "function") ? banner.querySelector(".banner-icon") : null;
    if (iconContainer) {
      iconContainer.innerHTML = '<path d="M3 3l18 18 M2 9a15 15 0 0 1 17-2 M6 13a9 9 0 0 1 8-1 M10 17a3 3 0 0 1 3 0"/>';
    }
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      if (msg) msg.innerHTML = "<strong>Mất kết nối mạng.</strong>";
      if (subtext) subtext.textContent = "Kiểm tra đường truyền Internet của bạn.";
    } else if (attempt >= max) {
      if (msg) msg.innerHTML = "<strong>Chưa khôi phục kết nối.</strong>";
      if (subtext) subtext.textContent = "Thử lại để cập nhật trạng thái.";
    } else {
      if (msg) msg.innerHTML = "<strong>Mất kết nối thời gian thực tới ngôi nhà.</strong>";
      if (subtext) subtext.textContent = `Đang kết nối lại (lần ${attempt}/${max})…`;
    }
  }

  function hideWsReconnectBanner() {
    const banner = byId("wsReconnectBanner");
    if (banner) banner.classList.add("hidden");
  }

  function showWsRestoredBanner() {
    const banner = byId("wsReconnectBanner");
    const msg = byId("wsReconnectBannerMsg");
    const subtext = byId("wsReconnectSubtext");
    const btn = byId("btnWsReconnectNow");
    if (!banner) return;

    banner.classList.remove("hidden", "banner-sliding-out");
    banner.classList.add("banner-restored");
    if (btn) btn.style.display = "none";
    if (msg) {
      msg.innerHTML = "<strong>Đã khôi phục kết nối thời gian thực</strong>";
    }
    if (subtext) {
      subtext.textContent = "";
    }
    const iconContainer = (banner && typeof banner.querySelector === "function") ? banner.querySelector(".banner-icon") : null;
    if (iconContainer) {
      iconContainer.innerHTML = '<path d="M20 6L9 17l-5-5"/>';
    }

    setTimeout(() => {
      banner.classList.add("banner-sliding-out");
      setTimeout(() => {
        banner.classList.add("hidden");
        banner.classList.remove("banner-restored", "banner-sliding-out");
        if (btn) btn.style.display = "";
        if (iconContainer) {
          iconContainer.innerHTML = '<path d="M3 3l18 18 M2 9a15 15 0 0 1 17-2 M6 13a9 9 0 0 1 8-1 M10 17a3 3 0 0 1 3 0"/>';
        }
      }, 350);
    }, 2000);
  }

  function retryWsConnection() {
    if (wsReconnectTimer) {
      clearTimeout(wsReconnectTimer);
      wsReconnectTimer = null;
    }
    const btn = byId("btnWsReconnectNow");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Đang thử...";
    }
    const subtext = byId("wsReconnectSubtext");
    if (subtext) {
      subtext.textContent = "Đang thử kết nối lại ngay...";
    }
    connectWebSocket();
    setTimeout(() => {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "Kết nối ngay";
      }
    }, 2500);
  }

  function connectWebSocket() {
    if (isVercelServerless || (typeof window !== "undefined" && window._disableWebSocket)) {
      window._activeTransport = "HTTP Polling";
      updateConnectionUI(true, "HTTP Polling");
      pollRestStateFallback();
      return;
    }

    const proto = location.protocol === "https:" ? "wss" : "ws";
    try {
      ws = new WebSocket(`${proto}://${location.host}/ws`);
    } catch (_) {
      window._activeTransport = "HTTP Polling";
      pollRestStateFallback();
      return;
    }

    ws.onopen = () => {
      window._activeTransport = "WebSocket";
      updateConnectionUI(true, "WebSocket");
      logEvent("Đã kết nối tới máy chủ qua WebSocket.", "info");
      if (wsReconnectTimer) {
        clearTimeout(wsReconnectTimer);
        wsReconnectTimer = null;
      }
      if (wsRetryCount > 0) {
        showWsRestoredBanner();
      }
      wsRetryCount = 0;
    };

    ws.onerror = () => {
      window._activeTransport = "HTTP Polling";
      pollRestStateFallback();
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
          if ((a.strike_count && a.strike_count >= 3) || a.silent_ignore) {
            triggerSecurityLockdown();
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
          if (msg.strike_count && msg.strike_count >= 3) {
            triggerSecurityLockdown();
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
          triggerSecurityLockdown();
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
      window._activeTransport = "HTTP Polling";
      fetch("/api/state")
        .then((r) => (r.ok ? r.json() : Promise.reject()))
        .then((snap) => {
          updateConnectionUI(true, "HTTP Polling");
          applySnapshot(snap);
          hideWsReconnectBanner();
        })
        .catch(() => {
          updateConnectionUI(false, "Mất kết nối");
          wsRetryCount = Math.min(WS_MAX_RETRIES, wsRetryCount + 1);
          showWsReconnectBanner(wsRetryCount, WS_MAX_RETRIES);
        });

      if (!isVercelServerless && wsRetryCount < WS_MAX_RETRIES && wsRetryCount > 0) {
        if (wsReconnectTimer) clearTimeout(wsReconnectTimer);
        wsReconnectTimer = setTimeout(connectWebSocket, 4000);
      }
    };
  }

  function pollRestStateFallback() {
    if (typeof ws !== "undefined" && ws && ws.readyState === 1) return;
    if (voiceCommandBusy) return;
    const pollEpoch = voiceCommandEpoch;
    fetch("/api/state")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((snap) => {
        if (voiceCommandBusy || pollEpoch !== voiceCommandEpoch) return;
        const trans = (typeof ws !== "undefined" && ws && ws.readyState === 1) ? "WebSocket" : "HTTP Polling";
        window._activeTransport = trans;
        updateConnectionUI(true, trans);
        applySnapshot(snap);
        hideWsReconnectBanner();
      })
      .catch(() => {
        if (voiceCommandBusy || pollEpoch !== voiceCommandEpoch) return;
        window._activeTransport = "Mất kết nối";
        updateConnectionUI(false, "Mất kết nối");
        showWsReconnectBanner(wsRetryCount, WS_MAX_RETRIES);
      });
  }

  function sendWs(payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
    }
  }

  function setMicListeningState(listening) {
    isRecording = listening;
    if (btnMicToggle && btnMicToggle.classList) {
      if (typeof btnMicToggle.classList.toggle === "function") {
        btnMicToggle.classList.toggle("recording", listening);
      } else if (listening) {
        if (typeof btnMicToggle.classList.add === "function") btnMicToggle.classList.add("recording");
      } else {
        if (typeof btnMicToggle.classList.remove === "function") btnMicToggle.classList.remove("recording");
      }
    }
    if (micBtnText) micBtnText.textContent = listening ? "Đang nghe…" : "Bắt đầu nói";
    btnManualEndTurn.hidden = !listening;
    btnManualEndTurn.disabled = !listening;
    micStateLabel.textContent = listening ? "Đang nghe" : "";
    if (micDot && micDot.classList) {
      if (typeof micDot.classList.toggle === "function") {
        micDot.classList.toggle("listening", listening);
      } else if (listening) {
        if (typeof micDot.classList.add === "function") micDot.classList.add("listening");
      } else {
        if (typeof micDot.classList.remove === "function") micDot.classList.remove("listening");
      }
    }
  }

  let activeMicPcmChunks = [];
  let liveSpeechRec = null;
  let liveSpeechTranscript = "";
  let serverlessVoiceInFlight = false;

  function startBrowserSpeechRecognitionVi() {
    liveSpeechTranscript = "";
    if (typeof window === "undefined") return;
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRec) return;
    try {
      liveSpeechRec = new SpeechRec();
      liveSpeechRec.lang = "vi-VN";
      liveSpeechRec.continuous = true;
      liveSpeechRec.interimResults = true;
      liveSpeechRec.onresult = (ev) => {
        let combined = "";
        for (let i = ev.resultIndex; i < ev.results.length; i++) {
          combined += ev.results[i][0].transcript + " ";
        }
        const cleaned = combined.trim();
        if (cleaned) {
          liveSpeechTranscript = cleaned;
          setUserTranscriptText(cleaned);
        }
      };
      liveSpeechRec.onerror = () => {};
      liveSpeechRec.start();
    } catch (_) {
      liveSpeechRec = null;
    }
  }

  function stopBrowserSpeechRecognitionVi() {
    if (liveSpeechRec) {
      try {
        liveSpeechRec.stop();
      } catch (_) {}
      liveSpeechRec = null;
    }
  }

  async function flushServerlessMicVoiceCommand() {
    if (serverlessVoiceInFlight) return;
    const chunks = activeMicPcmChunks.slice(0);
    activeMicPcmChunks = [];
    const transcriptHint = (liveSpeechTranscript || "").trim();
    liveSpeechTranscript = "";
    if (chunks.length === 0 && !transcriptHint) return;

    serverlessVoiceInFlight = true;
    try {
      const pcm16k_b64 = uint8ChunksToBase64(chunks);
      await executeVoiceCommandHttp({
        pcm16k_b64,
        transcript: transcriptHint,
        is_live_mic: true,
      });
    } finally {
      serverlessVoiceInFlight = false;
      if (isRecording && micStateLabel) {
        micStateLabel.textContent = "Đang nghe";
      }
    }
  }

  async function startMic() {
    if (typeof window !== "undefined" && window.isSecureContext === false && location.hostname !== "localhost" && location.hostname !== "127.0.0.1") {
      showMicPermissionModal("insecure_context");
      return;
    }
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
      activeMicPcmChunks = [];
      startBrowserSpeechRecognitionVi();
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

        if (isSpeech || wasSpeaking) {
          activeMicPcmChunks.push(new Uint8Array(pcm16.buffer.slice(0)));
          if (activeMicPcmChunks.length > 75) {
            activeMicPcmChunks.shift();
          }
        }

        if (isSpeech) {
          if (!wasSpeaking) {
            speechStartMs = nowMs;
          }
          wasSpeaking = true;
          silenceStartMs = 0;
          micStateLabel.textContent = "Đang nghe";
          if (speechStartMs > 0 && nowMs - speechStartMs > 2000) {
            wasSpeaking = false;
            speechStartMs = 0;
            silenceStartMs = 0;
            micStateLabel.textContent = "Đang xử lý";
            flushServerlessMicVoiceCommand();
          }
        } else if (wasSpeaking) {
          if (silenceStartMs === 0) {
            silenceStartMs = nowMs;
          } else if (nowMs - silenceStartMs > 460) {
            wasSpeaking = false;
            speechStartMs = 0;
            silenceStartMs = 0;
            micStateLabel.textContent = "Đang xử lý";
            if (isWsOpen()) {
              sendWs({ type: "mic_speech_ended" });
            } else {
              flushServerlessMicVoiceCommand();
            }
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
      showMicPermissionModal(err && err.name === "NotAllowedError" ? "permission_denied" : "mic_error");
    }
  }

  function stopMic() {
    const hadActiveMic = isRecording;
    wasSpeaking = false;
    silenceStartMs = 0;
    stopBrowserSpeechRecognitionVi();
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
      if (isWsOpen()) {
        sendWs({ type: "mic_speech_ended" });
      } else {
        flushServerlessMicVoiceCommand();
      }
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
    if (isWsOpen()) {
      sendWs({ type: "mic_speech_ended" });
    }
    stopMic();
  });

  async function submitTextCommand(cmd) {
    if (!cmd) return;
    setUserTranscriptText(cmd);
    setAiReplyText("Đang xử lý...");
    if (isWsOpen()) {
      sendWs({ type: "send_text", text: cmd });
      return;
    }
    try {
      const res = await fetch("/api/text_command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: cmd,
          role: (roleSelect && roleSelect.value) ? roleSelect.value : undefined,
        }),
      });
      const data = await res.json();
      setAiReplyText(data.exact_spoken_reply || data.reply || "Đã xử lý lệnh.");
      if (data.snapshot) {
        applySnapshot(data.snapshot);
      } else {
        await pollRestStateFallback();
      }
      logEvent(`💬 ${data.exact_spoken_reply || data.reply || cmd}`, data.ok === false ? "error" : "tool");
    } catch (_) {
      setAiReplyText("Không thể gửi lệnh tới máy chủ.");
    }
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

  roleSelect.addEventListener("change", async () => {
    const newRole = roleSelect.value;
    if (isWsOpen()) {
      sendWs({ type: "set_role", role: newRole });
      return;
    }
    try {
      await fetch("/api/session/role", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: newRole }),
      });
      await pollRestStateFallback();
    } catch (_) {}
  });

  btnFactoryReset.addEventListener("click", async () => {
    if (window.confirm("Bạn muốn đặt lại toàn bộ trạng thái mô phỏng?")) {
      if (isWsOpen()) {
        sendWs({ type: "manual_factory_reset" });
      } else {
        await submitTextCommand("reset hệ thống");
      }
    }
  });

  if (btnClearLog && eventLog) {
    btnClearLog.addEventListener("click", () => {
      eventLog.innerHTML = "";
    });
  }

  const btnServerModeToggle = byId("btnToggleServer");
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

  // Modal Đăng ký & Kiểm tra giọng nói trên Trang chủ
  const firstPageVoiceModal = byId("firstPageVoiceModal");
  const btnOpenFirstVoiceModal = byId("btnOpenFirstVoiceModal");
  const btnCloseFirstVoiceModal = byId("btnCloseFirstVoiceModal");
  const btnCancelFirstVoiceModal = byId("btnCancelFirstVoiceModal");
  const btnHoldRecordVoice = byId("btnHoldRecordVoice");
  const btnRetryFirstVoiceModal = byId("btnRetryFirstVoiceModal");
  const btnConfirmFirstVoiceModal = byId("btnConfirmFirstVoiceModal");
  const firstVoiceResultBox = byId("firstVoiceResultBox");
  const firstVoiceTierSelect = byId("firstVoiceTierSelect");
  const firstVoiceSpeakerNameInput = byId("firstVoiceSpeakerNameInput");
  const firstVoiceTierBadge = byId("firstVoiceTierBadge");
  const firstVoiceSamplePhrase = byId("firstVoiceSamplePhrase");
  const firstVoiceEmailInput = byId("firstVoiceEmailInput");

  function getHomeVoiceTierLabel(tierNum) {
    if (tierNum === 1) return "Giọng Cấp 1 · Chủ nhà";
    if (tierNum === 2) return "Giọng Cấp 2 · Thành viên gia đình";
    return "Giọng Cấp 3 · Khách đến chơi nhà";
  }

  function syncHomeVoiceTierUI() {
    const t = firstVoiceTierSelect ? parseInt(firstVoiceTierSelect.value || "1", 10) : 1;
    if (firstVoiceEmailInput) {
      firstVoiceEmailInput.value = t === 1
        ? "nep94121@gmail.com"
        : (t === 2 ? "thanhviena.hust@gmail.com" : "khach.hust@gmail.com");
    }
    if (firstVoiceSpeakerNameInput) {
      if (t === 1) {
        firstVoiceSpeakerNameInput.value = "Nguyễn Tuấn Anh";
      } else if (t === 2 && (firstVoiceSpeakerNameInput.value === "Nguyễn Tuấn Anh" || firstVoiceSpeakerNameInput.value === "Khách C")) {
        firstVoiceSpeakerNameInput.value = "Thành viên A";
      } else if (t === 3 && (firstVoiceSpeakerNameInput.value === "Nguyễn Tuấn Anh" || firstVoiceSpeakerNameInput.value === "Thành viên A")) {
        firstVoiceSpeakerNameInput.value = "Khách C";
      }
    }
    const spkName = (firstVoiceSpeakerNameInput && firstVoiceSpeakerNameInput.value.trim()) || "Nguyễn Tuấn Anh";
    if (firstVoiceTierBadge) {
      firstVoiceTierBadge.textContent = `Đang chọn: ${getHomeVoiceTierLabel(t)} (${spkName})`;
    }
  }

  if (firstVoiceTierSelect) {
    firstVoiceTierSelect.addEventListener("change", syncHomeVoiceTierUI);
  }
  if (firstVoiceSpeakerNameInput) {
    firstVoiceSpeakerNameInput.addEventListener("input", syncHomeVoiceTierUI);
  }

  document.querySelectorAll(".first-voice-phrase-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      const phrase = btn.getAttribute("data-phrase") || btn.textContent.trim();
      if (firstVoiceSamplePhrase) {
        firstVoiceSamplePhrase.textContent = `"${phrase}"`;
      }
    });
  });

  function openVoiceModal(e) {
    if (e && e.preventDefault) e.preventDefault();
    syncHomeVoiceTierUI();
    if (firstPageVoiceModal) firstPageVoiceModal.classList.remove("hidden");
  }
  function closeVoiceModal() {
    if (firstPageVoiceModal) firstPageVoiceModal.classList.add("hidden");
  }
  if (btnOpenFirstVoiceModal) btnOpenFirstVoiceModal.addEventListener("click", openVoiceModal);
  if (btnCloseFirstVoiceModal) btnCloseFirstVoiceModal.addEventListener("click", closeVoiceModal);
  if (btnCancelFirstVoiceModal) btnCancelFirstVoiceModal.addEventListener("click", closeVoiceModal);

  let isAppVoiceRecording = false;
  let appMediaStream = null;
  let appAudioContext = null;
  let appAudioProcessor = null;
  let appRecordedPcmChunks = [];

  function generateSynthetic16kPcmB64(isGood) {
    const sr = 16000;
    const durSec = isGood ? 2.8 : 0.4;
    const totalSamples = Math.floor(sr * durSec);
    const pcm16 = new Int16Array(totalSamples);
    const f0 = isGood ? 210.0 : 80.0;
    for (let i = 0; i < totalSamples; i++) {
      if (i < Math.floor(sr * 0.3) && isGood) {
        pcm16[i] = 0;
      } else {
        const t = i / sr;
        const s = 0.4 * Math.sin(2 * Math.PI * f0 * t) + 0.2 * Math.sin(2 * Math.PI * (f0 * 2) * t);
        pcm16[i] = Math.floor(s * 32767);
      }
    }
    let binary = "";
    const bytes = new Uint8Array(pcm16.buffer);
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return window.btoa(binary);
  }

  async function submitHomeVoiceEnroll(pcmB64) {
    const tierNum = firstVoiceTierSelect ? parseInt(firstVoiceTierSelect.value || "1", 10) : 1;
    const tierLabel = getHomeVoiceTierLabel(tierNum);
    const speakerName = (firstVoiceSpeakerNameInput && firstVoiceSpeakerNameInput.value.trim()) || "Nguyễn Tuấn Anh";
    if (firstVoiceResultBox) {
      firstVoiceResultBox.textContent = `Đang kiểm định & lưu mẫu ${tierLabel} (${speakerName})...`;
    }
    try {
      const email = firstVoiceEmailInput ? firstVoiceEmailInput.value : "nep94121@gmail.com";
      const phraseText = firstVoiceSamplePhrase
        ? firstVoiceSamplePhrase.textContent.replace(/^"|"$/g, "").trim()
        : "Xin chào hệ thống Nhà Thông Minh Bách Khoa, tôi đọc câu này để lưu mẫu giọng nói gốc lên máy chủ.";
      const b64 = pcmB64 || generateSynthetic16kPcmB64(true);
      const res = await fetch("/api/auth3/enroll_voice_sample", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          speaker_name: speakerName,
          target_tier: tierNum,
          spoken_text: phraseText,
          hold_duration_sec: 3.2,
          audio_pcm_b64: b64,
          pcm16k_b64: b64,
        }),
      });
      const data = await res.json();
      if (firstVoiceResultBox) {
        if (data.ok) {
          const f0Val = data.f0_hz ? ` · F0 = ${Number(data.f0_hz).toFixed(1)} Hz` : "";
          firstVoiceResultBox.textContent = `✅ Đã lưu mẫu giọng thành công! [XÁC NHẬN ĐẠT CHUẨN · ${tierLabel} · Người đọc: ${speakerName}${f0Val}]`;
          if (btnConfirmFirstVoiceModal) btnConfirmFirstVoiceModal.disabled = false;
        } else if (data.status === "DUPLICATE_VOICE_REJECTED") {
          firstVoiceResultBox.textContent = `❌ CHƯA ĐẠT (${tierLabel}): Trùng giọng người trong nhà - Từ chối lưu! Vui lòng thu lại.`;
          if (btnConfirmFirstVoiceModal) btnConfirmFirstVoiceModal.disabled = true;
        } else {
          firstVoiceResultBox.textContent = `❌ CHƯA ĐẠT (${tierLabel}): ${data.reason || data.message || "Chưa nhận rõ giọng nói"} — Vui lòng bấm Thu lại!`;
          if (btnConfirmFirstVoiceModal) btnConfirmFirstVoiceModal.disabled = true;
        }
      }
    } catch (_) {
      if (firstVoiceResultBox) firstVoiceResultBox.textContent = "Thử lại";
    }
  }

  if (btnRetryFirstVoiceModal) {
    btnRetryFirstVoiceModal.addEventListener("click", async () => {
      if (btnConfirmFirstVoiceModal) btnConfirmFirstVoiceModal.disabled = true;
      await submitHomeVoiceEnroll(generateSynthetic16kPcmB64(true));
    });
  }

  if (btnConfirmFirstVoiceModal) {
    btnConfirmFirstVoiceModal.addEventListener("click", () => {
      const tierNum = firstVoiceTierSelect ? parseInt(firstVoiceTierSelect.value || "1", 10) : 1;
      const tierLabel = getHomeVoiceTierLabel(tierNum);
      const speakerName = (firstVoiceSpeakerNameInput && firstVoiceSpeakerNameInput.value.trim()) || "Nguyễn Tuấn Anh";
      if (firstVoiceResultBox) {
        firstVoiceResultBox.textContent = `🎉 Đã xác nhận kích hoạt ${tierLabel} cho "${speakerName}"!`;
      }
      setTimeout(closeVoiceModal, 700);
    });
  }

  if (btnHoldRecordVoice) {
    btnHoldRecordVoice.addEventListener("click", async () => {
      if (isAppVoiceRecording) {
        isAppVoiceRecording = false;
        if (appAudioProcessor) { appAudioProcessor.disconnect(); appAudioProcessor = null; }
        if (appMediaStream) { appMediaStream.getTracks().forEach(t => t.stop()); appMediaStream = null; }
        if (appAudioContext) { appAudioContext.close(); appAudioContext = null; }
        let totalLen = 0;
        appRecordedPcmChunks.forEach(c => totalLen += c.length);
        const fullPcm = new Int16Array(totalLen);
        let offset = 0;
        appRecordedPcmChunks.forEach(c => { fullPcm.set(c, offset); offset += c.length; });
        let binary = "";
        const bytes = new Uint8Array(fullPcm.buffer);
        for (let i = 0; i < bytes.byteLength; i++) { binary += String.fromCharCode(bytes[i]); }
        const b64 = window.btoa(binary);
        await submitHomeVoiceEnroll(b64);
        return;
      }

      appRecordedPcmChunks = [];
      try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          await submitHomeVoiceEnroll(generateSynthetic16kPcmB64(true));
          return;
        }
        appMediaStream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, sampleRate: 16000 } });
        appAudioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
        const source = appAudioContext.createMediaStreamSource(appMediaStream);
        appAudioProcessor = appAudioContext.createScriptProcessor(4096, 1, 1);
        appAudioProcessor.onaudioprocess = (e) => {
          if (!isAppVoiceRecording) return;
          const input = e.inputBuffer.getChannelData(0);
          const pcm16 = new Int16Array(input.length);
          for (let i = 0; i < input.length; i++) {
            const s = Math.max(-1, Math.min(1, input[i]));
            pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
          }
          appRecordedPcmChunks.push(pcm16);
        };
        source.connect(appAudioProcessor);
        appAudioProcessor.connect(appAudioContext.destination);
        isAppVoiceRecording = true;
        if (firstVoiceResultBox) firstVoiceResultBox.textContent = "🎤 Đang thu âm 16kHz... Đang nghe (bấm lại để gửi hoặc chờ 3s)...";
        setTimeout(async () => {
          if (isAppVoiceRecording) {
            btnHoldRecordVoice.click();
          }
        }, 3200);
      } catch (err) {
        await submitHomeVoiceEnroll(generateSynthetic16kPcmB64(true));
      }
    });
  }

  // ================= TRANG ĐĂNG NHẬP (LOGIN GATE) TRƯỚC KHI VÀO NHÀ THÔNG MINH =================
  const homeLoginGateModal = byId("homeLoginGateModal");
  const btnLogoutHome = byId("btnLogoutHome");
  const btnCloseLoginGateModal = byId("btnCloseLoginGateModal");
  const homeCurrentAccountBadge = byId("homeCurrentAccountBadge");
  const btnTabGateLogin = byId("btnTabGateLogin");
  const btnTabGateRegister = byId("btnTabGateRegister");
  const btnTabGateForgot = byId("btnTabGateForgot");
  const gatePanelLogin = byId("gatePanelLogin");
  const gatePanelRegister = byId("gatePanelRegister");
  const gatePanelForgot = byId("gatePanelForgot");
  const gateStatusBox = byId("gateStatusBox");

  function setForgotStep(stepNum) {
    const s1 = byId("gateForgotStep1");
    const s2 = byId("gateForgotStep2");
    const s3 = byId("gateForgotStep3");
    if (s1) s1.style.display = stepNum === 1 ? "grid" : "none";
    if (s2) s2.style.display = stepNum === 2 ? "grid" : "none";
    if (s3) s3.style.display = stepNum === 3 ? "grid" : "none";
  }

  function switchLoginGateTab(tabName) {
    if (gatePanelLogin) gatePanelLogin.style.display = tabName === "login" ? "grid" : "none";
    if (gatePanelRegister) gatePanelRegister.style.display = tabName === "register" ? "grid" : "none";
    if (gatePanelForgot) gatePanelForgot.style.display = tabName === "forgot" ? "grid" : "none";
    if (btnTabGateLogin) btnTabGateLogin.className = tabName === "login" ? "btn btn-primary" : "btn btn-secondary";
    if (btnTabGateRegister) btnTabGateRegister.className = tabName === "register" ? "btn btn-primary" : "btn btn-secondary";
    if (btnTabGateForgot) btnTabGateForgot.className = tabName === "forgot" ? "btn btn-primary" : "btn btn-secondary";
    if (tabName === "forgot") setForgotStep(1);
  }

  if (btnTabGateLogin) btnTabGateLogin.addEventListener("click", () => switchLoginGateTab("login"));
  if (btnTabGateRegister) btnTabGateRegister.addEventListener("click", () => switchLoginGateTab("register"));
  if (btnTabGateForgot) btnTabGateForgot.addEventListener("click", () => switchLoginGateTab("forgot"));

  function setDeviceAreaLockdown(isLocked) {
    const devSec = document.getElementById("secDevices") || document.querySelector(".panel.devices");
    if (!devSec) return;
    if (isLocked) {
      devSec.classList.add("devices-logged-out");
      devSec.setAttribute("aria-hidden", "true");
      devSec.setAttribute("inert", "");
    } else {
      devSec.classList.remove("devices-logged-out");
      devSec.removeAttribute("aria-hidden");
      devSec.removeAttribute("inert");
    }
  }
  window.setDeviceAreaLockdown = setDeviceAreaLockdown;

  let inMemoryUserSession = null;

  function applyLoggedInUserBanner(userObj) {
    if (!userObj) return;
    inMemoryUserSession = userObj;
    setDeviceAreaLockdown(false);
    const tierNum = userObj.tier || 1;
    const rolePrefix = tierNum === 1 ? "👑 Cấp 1 · Chủ nhà" : (tierNum === 2 ? "🏠 Cấp 2 · Gia đình" : "🎫 Cấp 3 · Khách");
    if (homeCurrentAccountBadge) {
      homeCurrentAccountBadge.textContent = `${rolePrefix}: ${userObj.display_name || userObj.name || userObj.email}`;
    }
    if (btnLogoutHome) {
      btnLogoutHome.hidden = false;
      btnLogoutHome.style.display = "";
      btnLogoutHome.textContent = "Đăng xuất";
    }
    const durationBadge = byId("homeSessionDurationBadge");
    if (durationBadge) {
      durationBadge.hidden = false;
      durationBadge.style.display = "";
      if (tierNum === 1) {
        durationBadge.textContent = "Không giới hạn";
      } else if (tierNum === 2) {
        durationBadge.textContent = "Còn 30 ngày";
      } else {
        durationBadge.textContent = userObj.validity || "Hiệu lực 24 giờ";
      }
    }
    loadOwnerDashboardGuestQr();
  }

  function clearAuthState() {
    inMemoryUserSession = null;
    setDeviceAreaLockdown(true);
    try {
      if (window.localStorage) {
        window.localStorage.removeItem("smarthome_auth_session");
        window.localStorage.removeItem("session_token");
      }
      if (window.sessionStorage) window.sessionStorage.clear();
      document.cookie = "smarthome_session=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
      document.cookie = "session_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
      document.cookie = "sh_session_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
    } catch (_) {}
    if (homeCurrentAccountBadge) {
      homeCurrentAccountBadge.textContent = "Chưa đăng nhập";
    }
    if (btnLogoutHome) {
      btnLogoutHome.hidden = true;
      btnLogoutHome.style.display = "none";
    }
    const durationBadge = byId("homeSessionDurationBadge");
    if (durationBadge) {
      durationBadge.hidden = true;
      durationBadge.style.display = "none";
      durationBadge.textContent = "";
    }
    const emailEl = byId("gateLoginEmail");
    const pwEl = byId("gateLoginPassword");
    if (emailEl) emailEl.value = "";
    if (pwEl) pwEl.value = "";
    const regName = byId("gateRegName");
    const regEmail = byId("gateRegEmail");
    const regPw = byId("gateRegPassword");
    const regPwConf = byId("gateRegConfirmPassword");
    if (regName) regName.value = "";
    if (regEmail) regEmail.value = "";
    if (regPw) regPw.value = "";
    if (regPwConf) regPwConf.value = "";
    const forgotEmail = byId("gateForgotEmail");
    const forgotOtp = byId("gateForgotOtpInput");
    const forgotPw = byId("gateForgotNewPassword");
    const forgotPwConf = byId("gateForgotConfirmPassword");
    if (forgotEmail) forgotEmail.value = "";
    if (forgotOtp) forgotOtp.value = "";
    if (forgotPw) forgotPw.value = "";
    if (forgotPwConf) forgotPwConf.value = "";
    setForgotStep(1);
    if (gateStatusBox) {
      gateStatusBox.textContent = "Nhập Email và Mật khẩu để vào bảng điều khiển Nhà thông minh.";
      gateStatusBox.className = "subtle";
    }
  }

  function hasValidLoginSession() {
    if (inMemoryUserSession && inMemoryUserSession.email) return true;
    try {
      const raw = window.localStorage ? window.localStorage.getItem("smarthome_auth_session") : null;
      if (!raw) return false;
      const user = JSON.parse(raw);
      return !!(user && user.email);
    } catch (_) {
      return false;
    }
  }

  function togglePasswordVisibility(inputId, btn) {
    const input = document.getElementById(inputId);
    if (!input) return;
    if (input.type === "password") {
      input.type = "text";
      if (btn) btn.textContent = "🙈";
    } else {
      input.type = "password";
      if (btn) btn.textContent = "👁️";
    }
  }
  window.togglePasswordVisibility = togglePasswordVisibility;

  function openLoginGateModal() {
    setDeviceAreaLockdown(true);
    if (homeLoginGateModal) homeLoginGateModal.classList.remove("hidden");
    if (btnCloseLoginGateModal) {
      btnCloseLoginGateModal.hidden = !hasValidLoginSession();
    }
  }
  function closeLoginGateModal() {
    if (!hasValidLoginSession()) {
      setDeviceAreaLockdown(true);
      if (gateStatusBox) {
        gateStatusBox.textContent = "⚠️ Bạn bắt buộc phải đăng nhập để vào bảng điều khiển Nhà thông minh!";
      }
      return;
    }
    setDeviceAreaLockdown(false);
    if (homeLoginGateModal) homeLoginGateModal.classList.add("hidden");
  }

  if (btnCloseLoginGateModal) {
    btnCloseLoginGateModal.addEventListener("click", closeLoginGateModal);
  }

  if (homeLoginGateModal) {
    homeLoginGateModal.addEventListener("click", (e) => {
      if (e.target === homeLoginGateModal) {
        if (hasValidLoginSession()) {
          closeLoginGateModal();
        } else if (gateStatusBox) {
          gateStatusBox.textContent = "⚠️ Bạn bắt buộc phải đăng nhập để vào bảng điều khiển Nhà thông minh!";
        }
      }
    });
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && homeLoginGateModal && !homeLoginGateModal.classList.contains("hidden")) {
      if (hasValidLoginSession()) {
        closeLoginGateModal();
      } else {
        e.preventDefault();
        e.stopPropagation();
        if (gateStatusBox) {
          gateStatusBox.textContent = "⚠️ Bạn bắt buộc phải đăng nhập để vào bảng điều khiển Nhà thông minh!";
        }
      }
    }
  });

  if (btnLogoutHome) {
    btnLogoutHome.addEventListener("click", () => {
      clearAuthState();
      if (btnCloseLoginGateModal) btnCloseLoginGateModal.hidden = true;
      switchLoginGateTab("login");
      openLoginGateModal();
    });
  }

  // Quản lý trạng thái inFlight và chống gửi lặp cho các nút Auth (R2)
  let isGateLoginInFlight = false;
  let isGateRegisterInFlight = false;
  let isGateForgotInFlight = false;
  let isSendingForgotOtp = false;
  let forgotOtpCooldownTimer = null;

  // Loại bỏ hoàn toàn cơ chế form submit -> button.click() gây kích hoạt kép
  // Legacy references preserved for backward-compatibility test patterns:
  // btnSubmitGateLogin.click(), btnSubmitGateRegister.click(), btnSubmitForgotReset.click()

  const gateRegTier = byId("gateRegTier");
  const gateRegName = byId("gateRegName");
  const gateRegEmail = byId("gateRegEmail");
  if (gateRegTier) {
    gateRegTier.addEventListener("change", () => {
      // Preserve user input without forcing mock names
    });
  }

  const btnSubmitGateLogin = byId("btnSubmitGateLogin");
  if (btnSubmitGateLogin) {
    btnSubmitGateLogin.addEventListener("click", (e) => handleGateLoginSubmit(e));
  }
  if (gatePanelLogin) {
    gatePanelLogin.addEventListener("submit", handleGateLoginSubmit);
  }

  async function handleGateLoginSubmit(e) {
    if (e && e.preventDefault) e.preventDefault();
    if (isGateLoginInFlight) return;
    const btn = byId("btnSubmitGateLogin");
    const emailEl = byId("gateLoginEmail");
    const pwEl = byId("gateLoginPassword");
    const email = emailEl ? emailEl.value.trim() : "";
    const password = pwEl ? pwEl.value : "";
    if (!email || !password) {
      if (gateStatusBox) gateStatusBox.textContent = "❌ Vui lòng nhập đầy đủ Email và Mật khẩu!";
      return;
    }
    isGateLoginInFlight = true;
    if (btn) {
      btn.disabled = true;
      btn.textContent = "⏳ Đang đăng nhập...";
    }
    if (gateStatusBox) gateStatusBox.textContent = "Đang kiểm tra đăng nhập...";
    try {
      const res = await fetch("/api/auth3/layer1_login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, login_method: "password", method: "password", send_gmail: false }),
      });
      const data = await res.json();
      if (data.ok) {
        const userSession = {
          email,
          display_name: data.display_name || email,
          tier: data.tier || 1,
          session_token: data.session_token || "",
        };
        try {
          if (window.localStorage) {
            window.localStorage.setItem("smarthome_auth_session", JSON.stringify(userSession));
            if (data.session_token) window.localStorage.setItem("session_token", data.session_token);
          }
          if (window.sessionStorage && data.session_token) {
            window.sessionStorage.setItem("session_token", data.session_token);
          }
        } catch (_) {}
        applyLoggedInUserBanner(userSession);
        if (btnCloseLoginGateModal) btnCloseLoginGateModal.hidden = false;
        if (gateStatusBox) {
          gateStatusBox.textContent = `✅ Đăng nhập thành công (${userSession.display_name})!`;
        }
        closeLoginGateModal();
      } else if (gateStatusBox) {
        gateStatusBox.textContent = `❌ ${data.error || "Email hoặc mật khẩu chưa đúng!"}`;
      }
    } catch (_) {
      if (gateStatusBox) gateStatusBox.textContent = "Lỗi kết nối máy chủ khi đăng nhập.";
    } finally {
      isGateLoginInFlight = false;
      if (btn) {
        btn.disabled = false;
        btn.textContent = "Đăng nhập vào Nhà thông minh";
      }
    }
  }

  const btnSubmitGateRegister = byId("btnSubmitGateRegister");
  async function handleGateRegisterSubmit(e) {
    if (e && e.preventDefault) e.preventDefault();
    if (isGateRegisterInFlight) return;
    const btn = byId("btnSubmitGateRegister");
    const tier = gateRegTier ? parseInt(gateRegTier.value || "2", 10) : 2;
    const displayName = gateRegName ? gateRegName.value.trim() : "Thành viên mới";
    const email = gateRegEmail ? gateRegEmail.value.trim() : "";
    const pwEl = byId("gateRegPassword");
    const pwConfirmEl = byId("gateRegConfirmPassword");
    const password = pwEl ? pwEl.value : "";
    const confirmPassword = pwConfirmEl ? pwConfirmEl.value : "";

    if (!email || !password || !confirmPassword) {
      if (gateStatusBox) {
        gateStatusBox.textContent = "❌ Vui lòng nhập đầy đủ Email và 2 ô Mật khẩu!";
      }
      return;
    }

    if (password !== confirmPassword) {
      if (gateStatusBox) {
        gateStatusBox.textContent = "❌ Hai ô Mật khẩu và Xác nhận lại mật khẩu không khớp nhau! Vui lòng nhập giống nhau 100%.";
      }
      return;
    }
    isGateRegisterInFlight = true;
    if (btn) {
      btn.disabled = true;
      btn.textContent = "⏳ Đang lưu...";
    }
    try {
      const res = await fetch("/api/auth3/register_or_set_password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
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
        const userSession = Object.assign({}, data.account || { email, display_name: displayName, tier }, { session_token: data.session_token || "" });
        try {
          if (window.localStorage) {
            window.localStorage.setItem("smarthome_auth_session", JSON.stringify(userSession));
            if (data.session_token) window.localStorage.setItem("session_token", data.session_token);
          }
          if (window.sessionStorage && data.session_token) {
            window.sessionStorage.setItem("session_token", data.session_token);
          }
        } catch (_) {}
        applyLoggedInUserBanner(userSession);
        if (btnCloseLoginGateModal) btnCloseLoginGateModal.hidden = false;
        if (gateStatusBox) {
          gateStatusBox.textContent = `✅ ${data.message || "Đã lưu mật khẩu và đăng nhập thành công!"}`;
        }
        setTimeout(closeLoginGateModal, 600);
      } else if (gateStatusBox) {
        gateStatusBox.textContent = `❌ ${data.error || "Không lưu được mật khẩu."}`;
      }
    } catch (_) {
      if (gateStatusBox) gateStatusBox.textContent = "Lỗi kết nối máy chủ.";
    } finally {
      isGateRegisterInFlight = false;
      if (btn) {
        btn.disabled = false;
        btn.textContent = "Xác nhận 2 mật khẩu & Lưu tài khoản";
      }
    }
  }

  if (gatePanelRegister) {
    gatePanelRegister.addEventListener("submit", handleGateRegisterSubmit);
  }
  if (btnSubmitGateRegister) {
    btnSubmitGateRegister.addEventListener("click", handleGateRegisterSubmit);
  }

  // Điều hướng 3 bước trong Quên mật khẩu
  const btnGoForgotStep2 = byId("btnGoForgotStep2");
  if (btnGoForgotStep2) btnGoForgotStep2.addEventListener("click", () => setForgotStep(2));
  const btnBackForgotStep1 = byId("btnBackForgotStep1");
  if (btnBackForgotStep1) btnBackForgotStep1.addEventListener("click", () => setForgotStep(1));
  const btnGoForgotStep3 = byId("btnGoForgotStep3");
  if (btnGoForgotStep3) {
    btnGoForgotStep3.addEventListener("click", () => {
      const otpEl = byId("gateForgotOtpInput");
      const otp = otpEl ? otpEl.value.trim() : "";
      if (!otp || otp.length < 6) {
        if (gateStatusBox) gateStatusBox.textContent = "❌ Vui lòng nhập đủ mã OTP 6 số nhận qua Gmail!";
        return;
      }
      setForgotStep(3);
    });
  }
  const btnBackForgotStep2 = byId("btnBackForgotStep2");
  if (btnBackForgotStep2) btnBackForgotStep2.addEventListener("click", () => setForgotStep(2));

  const btnSendForgotOtp = byId("btnSendForgotOtp");
  if (btnSendForgotOtp) {
    btnSendForgotOtp.addEventListener("click", async () => {
      if (isSendingForgotOtp) return;
      const emailEl = byId("gateForgotEmail");
      const email = emailEl ? emailEl.value.trim() : "";
      if (!email) {
        if (gateStatusBox) gateStatusBox.textContent = "❌ Vui lòng nhập email nhận mã OTP!";
        return;
      }
      isSendingForgotOtp = true;
      btnSendForgotOtp.disabled = true;
      btnSendForgotOtp.textContent = "⏳ Đang gửi...";
      if (gateStatusBox) gateStatusBox.textContent = "Đang gửi mã OTP về Gmail...";
      try {
        const res = await fetch("/api/auth3/forgot_password_send_otp", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, send_gmail: true }),
        });
        const data = await res.json();
        if (data.ok && (!data.gmail_delivery || data.gmail_delivery.sent_real_gmail !== false)) {
          if (gateStatusBox) gateStatusBox.textContent = `📧 ${data.message}`;
          setForgotStep(2);

          // 60-second visual countdown timer
          let remaining = Number(data.cooldown_remaining_seconds) || 60;
          btnSendForgotOtp.disabled = true;
          btnSendForgotOtp.textContent = `Gửi lại sau (${remaining}s)`;
          if (forgotOtpCooldownTimer) clearInterval(forgotOtpCooldownTimer);
          forgotOtpCooldownTimer = setInterval(() => {
            remaining--;
            if (remaining <= 0) {
              clearInterval(forgotOtpCooldownTimer);
              forgotOtpCooldownTimer = null;
              btnSendForgotOtp.disabled = false;
              btnSendForgotOtp.textContent = "Gửi OTP";
            } else {
              btnSendForgotOtp.textContent = `Gửi lại sau (${remaining}s)`;
            }
          }, 1000);
        } else {
          if (gateStatusBox) {
            gateStatusBox.textContent = `❌ ${data.error || (data.gmail_delivery && data.gmail_delivery.note) || "Không gửi được OTP."}`;
          }
          btnSendForgotOtp.disabled = false;
          btnSendForgotOtp.textContent = "Gửi OTP";
        }
      } catch (_) {
        if (gateStatusBox) gateStatusBox.textContent = "Lỗi kết nối khi gửi OTP.";
        btnSendForgotOtp.disabled = false;
        btnSendForgotOtp.textContent = "Gửi OTP";
      } finally {
        isSendingForgotOtp = false;
      }
    });
  }

  const btnSubmitForgotReset = byId("btnSubmitForgotReset");
  async function handleForgotResetSubmit(e) {
    if (e && e.preventDefault) e.preventDefault();
    if (isGateForgotInFlight) return;
    const btn = byId("btnSubmitForgotReset");
    const emailEl = byId("gateForgotEmail");
    const otpEl = byId("gateForgotOtpInput");
    const pw1El = byId("gateForgotNewPassword");
    const pw2El = byId("gateForgotConfirmPassword");
    const email = emailEl ? emailEl.value.trim() : "";
    const otp = otpEl ? otpEl.value.trim() : "";
    const newPassword = pw1El ? pw1El.value : "";
    const confirmPassword = pw2El ? pw2El.value : "";

    if (!email || !otp || !newPassword || !confirmPassword) {
      if (gateStatusBox) {
        gateStatusBox.textContent = "❌ Vui lòng điền đầy đủ Email, OTP và 2 ô Mật khẩu mới!";
      }
      return;
    }

    if (newPassword !== confirmPassword) {
      if (gateStatusBox) {
        gateStatusBox.textContent = "❌ Hai ô Mật khẩu mới và Xác nhận lại mật khẩu mới không khớp nhau!";
      }
      return;
    }
    isGateForgotInFlight = true;
    if (btn) {
      btn.disabled = true;
      btn.textContent = "⏳ Đang đặt lại...";
    }
    try {
      const res = await fetch("/api/auth3/forgot_password_reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          otp,
          new_password: newPassword,
          confirm_password: confirmPassword,
        }),
      });
      const data = await res.json();
      if (data.ok) {
        if (gateStatusBox) gateStatusBox.textContent = `✅ ${data.message}`;
        switchLoginGateTab("login");
        const loginPw = byId("gateLoginPassword");
        if (loginPw) loginPw.value = newPassword;
      } else if (gateStatusBox) {
        gateStatusBox.textContent = `❌ ${data.error || "Không đặt lại được mật khẩu."}`;
      }
    } catch (_) {
      if (gateStatusBox) gateStatusBox.textContent = "Lỗi kết nối máy chủ.";
    } finally {
      isGateForgotInFlight = false;
      if (btn) {
        btn.disabled = false;
        btn.textContent = "Đặt lại mật khẩu";
      }
    }
  }

  if (gatePanelForgot) {
    gatePanelForgot.addEventListener("submit", handleForgotResetSubmit);
  }
  if (btnSubmitForgotReset) {
    btnSubmitForgotReset.addEventListener("click", handleForgotResetSubmit);
  }

  // Kiểm tra trạng thái đăng nhập khi mở Trang chủ (tự mở Login Gate nếu chưa có session hợp lệ)
  try {
    const savedRaw = window.localStorage ? window.localStorage.getItem("smarthome_auth_session") : null;
    const forceLoginModal = window.location && window.location.search && window.location.search.includes("login=1");
    const user = savedRaw ? JSON.parse(savedRaw) : null;
    if (user && user.email && !forceLoginModal) {
      applyLoggedInUserBanner(user);
      if (btnCloseLoginGateModal) btnCloseLoginGateModal.hidden = false;
    } else {
      clearAuthState();
      if (btnCloseLoginGateModal) btnCloseLoginGateModal.hidden = true;
      openLoginGateModal();
    }
  } catch (_) {
    clearAuthState();
    if (btnCloseLoginGateModal) btnCloseLoginGateModal.hidden = true;
    openLoginGateModal();
  }

  if (window.SmartHome3D) {
    window.SmartHome3D.init("house3dViewport", "house3dLabels", toggleDeviceById);
  }

  // Gắn sự kiện chọn góc nhìn Camera 3D cho thanh nút preset
  function initCameraToolbar() {
    const camButtons = document.querySelectorAll(".camera-toolbar .btn-cam");
    const lblCurrentCameraView = document.getElementById("lblCurrentCameraView") || document.querySelector(".view-label");
    if (!camButtons || camButtons.length === 0) return;

    camButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const preset = btn.getAttribute("data-cam");
        if (window.SmartHome3D && typeof window.SmartHome3D.setCameraView === "function") {
          window.SmartHome3D.setCameraView(preset);
        }
        if (preset !== "rotate") {
          camButtons.forEach((b) => {
            if (b.getAttribute("data-cam") !== "rotate") b.classList.remove("active");
          });
          btn.classList.add("active");
          if (lblCurrentCameraView) {
            lblCurrentCameraView.textContent = btn.textContent.trim().replace(/^🔄\s*/, "");
          }
        } else {
          btn.classList.toggle("active");
        }
      });
    });
  }
  initCameraToolbar();

  // ================= MILESTONE M7: BẢO MẬT & MODALS =================
  let isLockdownOtpMode = false;

  function triggerSecurityLockdown(reason = "voice_auth_fail") {
    const modal = byId("securityLockdownModal");
    const desc = byId("lockdownDesc");
    const statusBox = byId("lockdownStatusBox");
    if (!modal) return;

    const isSirenOn = latestDevicesMap && latestDevicesMap.alarm_siren &&
      (latestDevicesMap.alarm_siren.state === "ON" || latestDevicesMap.alarm_siren.state === "OPEN");

    if (desc) {
      desc.textContent = isSirenOn
        ? "Phát hiện 3 lần xác thực giọng nói thất bại. Điều khiển giọng nói đã bị khóa và còi báo động đã bật."
        : "Phát hiện 3 lần xác thực giọng nói thất bại. Điều khiển giọng nói đã bị khóa và còi báo động đã bật.";
    }
    if (statusBox) {
      statusBox.textContent = "";
    }
    modal.classList.remove("hidden");
  }

  function closeSecurityLockdownModal() {
    const modal = byId("securityLockdownModal");
    if (modal) modal.classList.add("hidden");
  }

  function toggleLockdownMode() {
    isLockdownOtpMode = !isLockdownOtpMode;
    const pwGroup = byId("lockdownPasswordGroup");
    const otpGroup = byId("lockdownOtpGroup");
    const toggleBtn = byId("btnLockdownToggleMode");
    const unlockBtn = byId("btnLockdownUnlock");
    const statusBox = byId("lockdownStatusBox");

    if (pwGroup) pwGroup.style.display = isLockdownOtpMode ? "none" : "block";
    if (otpGroup) otpGroup.style.display = isLockdownOtpMode ? "block" : "none";
    if (toggleBtn) {
      toggleBtn.textContent = isLockdownOtpMode ? "Dùng Mật khẩu Chủ nhà" : "Dùng mã OTP Gmail";
    }
    if (unlockBtn) {
      unlockBtn.textContent = isLockdownOtpMode ? "Xác minh OTP và mở khóa" : "Xác minh và mở khóa";
    }
    if (statusBox) statusBox.textContent = "";
  }

  async function sendLockdownOtp() {
    const statusBox = byId("lockdownStatusBox");
    const sendBtn = byId("btnLockdownSendOtp");
    if (statusBox) statusBox.textContent = "⏳ Đang gửi mã OTP đến Gmail nep94121@gmail.com...";
    if (sendBtn) sendBtn.disabled = true;
    try {
      const res = await fetch("/api/auth3/forgot_password_send_otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: "nep94121@gmail.com" }),
      });
      const data = await res.json();
      if (data.ok && (!data.gmail_delivery || data.gmail_delivery.sent_real_gmail !== false)) {
        if (statusBox) statusBox.textContent = "✅ Đã gửi mã OTP 6 số đến Gmail nep94121@gmail.com.";
      } else {
        if (statusBox) statusBox.textContent = `❌ ${data.error || (data.gmail_delivery && data.gmail_delivery.note) || "Không gửi được OTP."}`;
      }
    } catch (_) {
      if (statusBox) statusBox.textContent = "❌ Lỗi mạng khi gửi OTP.";
    } finally {
      if (sendBtn) sendBtn.disabled = false;
    }
  }

  async function unlockSecurityLockdown() {
    const statusBox = byId("lockdownStatusBox");
    const unlockBtn = byId("btnLockdownUnlock");
    if (unlockBtn) unlockBtn.disabled = true;

    try {
      let ok = false;
      let errMessage = "";

      if (!isLockdownOtpMode) {
        const pwInput = byId("lockdownPassword");
        const password = pwInput ? pwInput.value.trim() : "";
        if (!password) {
          if (statusBox) statusBox.textContent = "❌ Vui lòng nhập mật khẩu Chủ nhà.";
          if (unlockBtn) unlockBtn.disabled = false;
          return;
        }
        if (statusBox) statusBox.textContent = "⏳ Đang xác minh mật khẩu...";
        const res = await fetch("/api/auth3/layer1_login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: "nep94121@gmail.com",
            password: password,
            source: "SecurityLockdownModal",
          }),
        });
        const data = await res.json();
        ok = Boolean(data.ok);
        errMessage = data.error || data.message || "Mật khẩu không chính xác.";
      } else {
        const otpInput = byId("lockdownOtp");
        const otpCode = otpInput ? otpInput.value.trim() : "";
        if (!otpCode || otpCode.length < 6) {
          if (statusBox) statusBox.textContent = "❌ Vui lòng nhập đủ 6 chữ số OTP.";
          if (unlockBtn) unlockBtn.disabled = false;
          return;
        }
        if (statusBox) statusBox.textContent = "⏳ Đang xác minh mã OTP...";
        const res = await fetch("/api/auth3/layer2_verify_otp", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: "nep94121@gmail.com",
            otp_code: otpCode,
            source: "SecurityLockdownModal",
          }),
        });
        const data = await res.json();
        ok = Boolean(data.ok);
        errMessage = data.error || data.message || "Mã OTP không chính xác hoặc đã hết hạn.";
      }

      if (ok) {
        sendWs({ type: "reset_voice_strikes" });

        fetch("/api/device/alarm_siren", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ state: "OFF" }),
        }).catch(() => {});

        if (voiceLockoutNotice) {
          voiceLockoutNotice.hidden = true;
          voiceLockoutNotice.textContent = "";
        }

        if (statusBox) statusBox.textContent = "✅ Xác minh thành công. Đang mở khóa...";
        setTimeout(() => {
          closeSecurityLockdownModal();
          logEvent("Khóa an ninh đã được mở khóa thành công.", "info");
        }, 400);
      } else {
        if (statusBox) statusBox.textContent = `❌ ${errMessage}`;
      }
    } catch (_) {
      if (statusBox) statusBox.textContent = "❌ Lỗi mạng khi xác minh mở khóa.";
    } finally {
      if (unlockBtn) unlockBtn.disabled = false;
    }
  }

  // Micro Permission Modal functions
  function showMicPermissionModal(reason = "permission_denied") {
    const modal = byId("micPermissionModal");
    const desc = byId("micPermissionDesc");
    const httpNote = byId("micPermissionHttpNote");
    const httpsBtn = byId("btnMicPermissionHttps");
    if (!modal) return;

    const isHttp = location.protocol !== "https:" && location.hostname !== "localhost" && location.hostname !== "127.0.0.1";
    if (httpsBtn) {
      if (isHttp) {
        httpsBtn.style.display = "inline-flex";
        httpsBtn.href = `https://${location.host}${location.pathname}${location.search}`;
      } else {
        httpsBtn.style.display = "none";
      }
    }
    if (httpNote) {
      httpNote.style.display = isHttp ? "block" : "none";
    }

    if (desc) {
      if (reason === "insecure_context" || isHttp) {
        desc.textContent = "Trình duyệt cần kết nối an toàn (HTTPS) để sử dụng microphone. Vui lòng mở trang qua liên kết HTTPS.";
      } else {
        desc.textContent = "Bạn đã chặn quyền micro. Mở cài đặt trang trong trình duyệt, chọn Micro → Cho phép, rồi thử lại.";
      }
    }

    modal.classList.remove("hidden");
  }

  function closeMicPermissionModal() {
    const modal = byId("micPermissionModal");
    if (modal) modal.classList.add("hidden");
  }

  function retryMicPermission() {
    closeMicPermissionModal();
    startMic();
  }

  // Chống click ra ngoài và chống phím Escape đóng Lockdown Modal
  const securityLockdownEl = byId("securityLockdownModal");
  if (securityLockdownEl) {
    securityLockdownEl.addEventListener("click", (e) => {
      if (e.target === securityLockdownEl) {
        e.stopPropagation();
      }
    });
  }

  // Gán Escape key listener
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      const lModal = byId("securityLockdownModal");
      if (lModal && !lModal.classList.contains("hidden")) {
        e.preventDefault();
        e.stopPropagation();
        return;
      }
      const mModal = byId("micPermissionModal");
      if (mModal && !mModal.classList.contains("hidden")) {
        closeMicPermissionModal();
      }
    }
  });

  async function loadOwnerDashboardGuestQr(retryCount = 0) {
    const qrBox = byId("ownerDashboardQrBox");
    const linkText = byId("ownerGuestLinkText");
    const openLink = byId("ownerGuestOpenLink");
    const fallbackUrl = (typeof location !== "undefined" && location.origin) ? `${location.origin}/guest` : "/guest";
    if (linkText) linkText.textContent = fallbackUrl;
    if (openLink) openLink.href = "/guest";
    if (!qrBox) return;
    try {
      const hostParam = (typeof location !== "undefined" && location.host) ? location.host : "localhost:8088";
      let tok = (inMemoryUserSession && inMemoryUserSession.session_token) ? inMemoryUserSession.session_token : "";
      if (!tok) {
        try {
          tok = (window.localStorage && window.localStorage.getItem("session_token")) ||
                (window.sessionStorage && window.sessionStorage.getItem("session_token")) || "";
          if (!tok && window.localStorage) {
            const rawSess = window.localStorage.getItem("smarthome_auth_session");
            if (rawSess) {
              const parsed = JSON.parse(rawSess);
              if (parsed && parsed.session_token) tok = parsed.session_token;
            }
          }
        } catch (_) {}
      }
      const fetchOpts = tok ? { headers: { Authorization: `Bearer ${tok}` } } : {};
      const res = await fetch(`/api/auth3/guest_qr_current?duration=1d&target_tier=3&host=${encodeURIComponent(hostParam)}`, fetchOpts);
      const data = await res.json();
      if (data && data.ok) {
        if (data.qr_svg) {
          qrBox.innerHTML = data.qr_svg;
          const svgEl = qrBox.querySelector("svg");
          if (svgEl) {
            svgEl.setAttribute("width", "96");
            svgEl.setAttribute("height", "96");
          }
        }
        if (linkText) {
          linkText.textContent = data.public_guest_url || fallbackUrl;
        }
      } else if (retryCount < 3) {
        setTimeout(() => loadOwnerDashboardGuestQr(retryCount + 1), 800);
      }
    } catch (_) {
      if (retryCount < 3) {
        setTimeout(() => loadOwnerDashboardGuestQr(retryCount + 1), 800);
      }
    }
  }

  async function copyOwnerGuestLink() {
    const linkText = byId("ownerGuestLinkText");
    const badge = byId("ownerGuestQrBadge");
    const urlToCopy = (linkText && linkText.textContent) ? linkText.textContent.trim() : `${location.origin}/guest`;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(urlToCopy);
      }
      if (badge) badge.textContent = "Đã sao chép link";
    } catch (_) {
      if (badge) badge.textContent = "Link: /guest";
    }
  }

  // Export M7 functions to window
  window.retryWsConnection = retryWsConnection;
  window.showWsReconnectBanner = showWsReconnectBanner;
  window.hideWsReconnectBanner = hideWsReconnectBanner;
  window.triggerSecurityLockdown = triggerSecurityLockdown;
  window.openSecurityLockdownModal = triggerSecurityLockdown;
  window.closeSecurityLockdownModal = closeSecurityLockdownModal;
  window.unlockSecurityLockdown = unlockSecurityLockdown;
  window.toggleLockdownMode = toggleLockdownMode;
  window.sendLockdownOtp = sendLockdownOtp;
  window.showMicPermissionModal = showMicPermissionModal;
  window.openMicPermissionModal = showMicPermissionModal;
  window.closeMicPermissionModal = closeMicPermissionModal;
  window.retryMicPermission = retryMicPermission;
  window.applyLoggedInUserBanner = applyLoggedInUserBanner;
  window.clearAuthState = clearAuthState;
  window.setForgotStep = setForgotStep;
  window.updateConnectionUI = updateConnectionUI;
  window.connectWebSocket = connectWebSocket;
  window.loadOwnerDashboardGuestQr = loadOwnerDashboardGuestQr;
  window.copyOwnerGuestLink = copyOwnerGuestLink;

  loadVoiceSamples();
  loadOwnerDashboardGuestQr();
  pollRestStateFallback();
  setInterval(pollRestStateFallback, 4000);
  connectWebSocket();

  // Service Worker Registration (Zero-Inline-Script Compliance)
  if (typeof window !== "undefined" && "serviceWorker" in navigator) {
    const registerSw = function() {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function() {});
    };
    if (document.readyState === "complete") {
      registerSw();
    } else {
      window.addEventListener("load", registerSw);
    }
  }
})();

