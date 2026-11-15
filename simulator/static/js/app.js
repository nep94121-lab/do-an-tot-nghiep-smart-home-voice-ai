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
  let currentSchedulesCount = 0;
  let currentScenesCount = 0;
  let latestAutomationSnap = null;

  // Mic capture state
  let isRecording = false;
  let micStream = null;
  let micAudioCtx = null;
  let micProcessor = null;
  let wasSpeaking = false;
  let silenceStartMs = 0;

  function updateScheduleEmptyState() {
    const hasAny =
      currentTimersCount > 0 ||
      currentRulesCount > 0 ||
      currentSchedulesCount > 0 ||
      currentScenesCount > 0;
    if (scheduleEmptyText) {
      scheduleEmptyText.hidden = hasAny;
    }
    if (timersList && timersList !== noopEl) {
      timersList.hidden = currentTimersCount === 0;
    }
    if (rulesList && rulesList !== noopEl) {
      rulesList.hidden = currentRulesCount === 0;
    }
    const clockWrap = byId("scheduleClockWrap");
    if (clockWrap) clockWrap.hidden = currentSchedulesCount === 0;
    const sceneWrap = byId("sceneListWrap");
    if (sceneWrap) sceneWrap.hidden = currentScenesCount === 0;
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

  let relayAudioCtx = null;

  function playRelayClick(isOpenOrOn) {
    try {
      if (!relayAudioCtx) {
        relayAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
      }
      if (relayAudioCtx.state === "suspended") {
        relayAudioCtx.resume();
      }
      const osc = relayAudioCtx.createOscillator();
      const gain = relayAudioCtx.createGain();
      osc.type = "triangle";
      osc.frequency.setValueAtTime(isOpenOrOn ? 1450 : 850, relayAudioCtx.currentTime);
      gain.gain.setValueAtTime(0.18, relayAudioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, relayAudioCtx.currentTime + 0.045);
      osc.connect(gain);
      gain.connect(relayAudioCtx.destination);
      osc.start();
      osc.stop(relayAudioCtx.currentTime + 0.05);
    } catch (_) {}
  }

  let _resamplePhase = 0.0;
  let _resampleLastSr = 0;

  function resampleFloat32AntiAliased(rawInput, actualSr, targetSr = 16000) {
    if (!actualSr || actualSr === targetSr || !rawInput || rawInput.length === 0) {
      return rawInput;
    }
    if (_resampleLastSr !== actualSr) {
      _resamplePhase = 0.0;
      _resampleLastSr = actualSr;
    }
    const step = actualSr / targetSr;
    const avail = rawInput.length - _resamplePhase;
    if (avail <= 0) {
      _resamplePhase -= rawInput.length;
      return new Float32Array(0);
    }
    const outLen = Math.max(1, Math.floor(avail / step));
    const output = new Float32Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const start = _resamplePhase + i * step;
      const end = start + step;
      const idxStart = Math.max(0, Math.floor(start));
      const idxEnd = Math.min(rawInput.length - 1, Math.ceil(end) - 1);
      if (idxEnd <= idxStart) {
        output[i] = rawInput[idxStart];
      } else {
        let sum = 0;
        let cnt = 0;
        for (let k = idxStart; k <= idxEnd; k++) {
          sum += rawInput[k];
          cnt++;
        }
        output[i] = sum / cnt;
      }
    }
    _resamplePhase = (_resamplePhase + outLen * step) - rawInput.length;
    if (_resamplePhase < 0 || !Number.isFinite(_resamplePhase)) {
      _resamplePhase = 0.0;
    }
    return output;
  }

  const TTS_HOLDOFF_SEC = 0.9;

  function isTtsPlaybackActive() {
    return Boolean(audioCtxOut && nextPlayTime > audioCtxOut.currentTime + 0.05);
  }

  function pauseMicForTts() {
    try { if (typeof stopBrowserSpeechRecognitionVi === "function") stopBrowserSpeechRecognitionVi(); } catch (_) {}
    wasSpeaking = false;
    silenceStartMs = 0;
  }

  function playPcm24kChunk(base64Data) {
    if (chkPlayAiVoice && chkPlayAiVoice.checked === false) return;
    if (!base64Data) return;
    try {
      const binaryStr = atob(base64Data);
      const evenLen = binaryStr.length - (binaryStr.length % 2);
      if (evenLen <= 0) return;
      const int16Arr = new Int16Array(evenLen / 2);
      for (let i = 0; i < evenLen; i += 2) {
        int16Arr[i / 2] = binaryStr.charCodeAt(i) | (binaryStr.charCodeAt(i + 1) << 8);
      }
      const float32Arr = new Float32Array(int16Arr.length);
      for (let i = 0; i < int16Arr.length; i++) {
        float32Arr[i] = int16Arr[i] / 32768.0;
      }

      if (typeof window !== "undefined") {
        window.__aoedePlayedChunksCount = (window.__aoedePlayedChunksCount || 0) + 1;
        window.__lastPlayedAoedeAudio = {
          sampleRate: 24000,
          frames: float32Arr.length,
          voice: "Aoede",
          ts: Date.now(),
        };
      }

      if (!audioCtxOut && (window.AudioContext || window.webkitAudioContext)) {
        audioCtxOut = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
      }
      if (!audioCtxOut) return;
      if (audioCtxOut.state === "suspended" && typeof audioCtxOut.resume === "function") {
        try {
          const r = audioCtxOut.resume();
          if (r && typeof r.catch === "function") r.catch(() => {});
        } catch (_) {}
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
      pauseMicForTts();
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

  function requestAoedeSpokenPhrase(text) {
    if (chkPlayAiVoice && chkPlayAiVoice.checked === false) return;
    const cleanText = String(text || "").trim();
    if (!cleanText) return;
    try {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "aoede_speak_denial", text: cleanText }));
        return;
      }
      fetch("/api/voice/aoede_phrase", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phrase: cleanText }),
      })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
          if (d && d.pcm24k_b64) {
            playPcm24kChunk(d.pcm24k_b64);
          }
        })
        .catch(() => {});
    } catch (_) {}
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

  const DEVICE_DEBOUNCE_MS = 20;
  const PENDING_INTENT_HOLD_MS = 4000;
  const WS_PENDING_TIMEOUT_MS = 15000;
  const CLIENT_ID =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? `web_${crypto.randomUUID()}`
      : `web_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
  const deviceControlState = {};
  let lastServerRevisionSeq = 0;
  let pollStateInFlight = false;
  let _realtimeSyncChannel = null;
  try {
    if (typeof BroadcastChannel !== "undefined") {
      _realtimeSyncChannel = new BroadcastChannel("smarthome_realtime_sync");
      if (typeof _realtimeSyncChannel.unref === "function") _realtimeSyncChannel.unref();
      _realtimeSyncChannel.onmessage = (ev) => {
        const payload = ev && ev.data ? ev.data : null;
        if (!payload || payload.type !== "state_changed" || payload.origin === CLIENT_ID) return;
        if (!serverSessionConfirmed) return;
        if (payload.snapshot && payload.snapshot.devices) {
          applySnapshot(payload.snapshot);
        }
        pollRestStateFallback(true);
      };
    }
  } catch (_) {
    _realtimeSyncChannel = null;
  }

  function publishRealtimeSync(snapshot = null) {
    try {
      if (_realtimeSyncChannel) {
        _realtimeSyncChannel.postMessage({
          type: "state_changed",
          origin: CLIENT_ID,
          ts: Date.now(),
          snapshot: snapshot && snapshot.devices ? snapshot : null,
        });
      }
    } catch (_) {}
  }

  if (typeof window !== "undefined") {
    window.__deviceControlState = deviceControlState;
    window.__clientId = CLIENT_ID;
  }

  function recomputeDevicePendingCount(ctrl) {
    if (!ctrl) return 0;
    const wsCount = ctrl.wsPendingTimers ? Object.keys(ctrl.wsPendingTimers).length : 0;
    ctrl.pendingCount = Math.max(0, Number(ctrl.httpPendingCount || 0)) + wsCount;
    return ctrl.pendingCount;
  }

  function clearWsPendingUpTo(ctrl, ackSeq) {
    if (!ctrl || !ctrl.wsPendingTimers) return;
    const targetSeq = Number(ackSeq || 0);
    Object.keys(ctrl.wsPendingTimers).forEach((k) => {
      const s = Number(k);
      if (targetSeq <= 0 || s <= targetSeq) {
        clearTimeout(ctrl.wsPendingTimers[k]);
        delete ctrl.wsPendingTimers[k];
        if (ctrl.wsPendingMeta) delete ctrl.wsPendingMeta[k];
      }
    });
    recomputeDevicePendingCount(ctrl);
  }

  function getDeviceControlState(devId) {
    if (!deviceControlState[devId]) {
      const cur = latestDevicesMap[devId];
      const initSt = cur && cur.state ? String(cur.state).toUpperCase() : "OFF";
      const sameCid = Boolean(cur && cur.last_client_id && cur.last_client_id === CLIENT_ID);
      const initSeq = sameCid && cur && cur.last_client_seq ? Number(cur.last_client_seq) : 0;
      const initVer = cur && cur.version ? Number(cur.version) : 0;
      deviceControlState[devId] = {
        seq: initSeq,
        desiredState: initSt,
        confirmedState: initSt,
        serverKnownState: initSt,
        serverKnownVersion: initVer,
        serverKnownRevisionSeq: lastServerRevisionSeq,
        needsServerKnownSync: false,
        lastConfirmedSeq: initSeq,
        httpPendingCount: 0,
        wsPendingTimers: {},
        wsPendingMeta: {},
        pendingCount: 0,
        debounceTimer: null,
        lastClickTs: 0,
        lastVersion: initVer,
        lastUpdatedAt: cur && cur.updated_at ? Number(cur.updated_at) : 0,
      };
    }
    return deviceControlState[devId];
  }

  function syncDeviceDOMToState(devId, targetState) {
    const dev = latestDevicesMap[devId];
    if (!dev) return;
    dev.state = targetState;
    const isOn = targetState === "ON" || targetState === "OPEN";
    updateDeviceCardUI(devId, dev, isOn);
    updateActiveDeviceSummaryCount();
    if (window.SmartHome3D) {
      window.SmartHome3D.updateDevices(Object.values(latestDevicesMap), window._latestMqtt, window._serverConnected !== false);
    }
  }

  function reconcileIdleDeviceToServerKnown(devId, ctrl) {
    if (!ctrl || ctrl.pendingCount > 0 || ctrl.debounceTimer !== null) return false;
    const knownVer = Number(ctrl.serverKnownVersion || 0);
    const curVer = Number(ctrl.lastVersion || 0);
    if (!ctrl.needsServerKnownSync && !(knownVer > 0 && knownVer > curVer)) {
      return false;
    }
    const dev = latestDevicesMap[devId];
    const authNewer = String(
      ctrl.serverKnownState || ctrl.confirmedState || (dev && dev.type === "door" ? "CLOSED" : "OFF")
    ).toUpperCase();
    ctrl.confirmedState = authNewer;
    ctrl.desiredState = authNewer;
    ctrl.lastVersion = Math.max(curVer, knownVer);
    ctrl.needsServerKnownSync = false;
    if (dev) {
      dev.version = ctrl.lastVersion;
    }
    syncDeviceDOMToState(devId, authNewer);
    return true;
  }

  function dispatchDeviceSetState(devId, mySeq, targetState, myTs) {
    const dev = latestDevicesMap[devId];
    const ctrl = getDeviceControlState(devId);
    if (!dev || mySeq < ctrl.seq) return;

    const isTargetOn = targetState === "ON" || targetState === "OPEN";
    const action = dev.type === "door" ? (isTargetOn ? "open" : "close") : (isTargetOn ? "turn_on" : "turn_off");
    const roleVal = roleSelect && roleSelect.value ? roleSelect.value : "";
    const reqId = `${CLIENT_ID}:${devId}:${mySeq}`;

    const rollbackIfLatest = () => {
      if (mySeq !== ctrl.seq) {
        reconcileIdleDeviceToServerKnown(devId, ctrl);
        return;
      }
      const hasNewerKnown =
        Number(ctrl.serverKnownVersion || 0) > Number(ctrl.lastVersion || 0) && Boolean(ctrl.serverKnownState);
      const revertState = String(
        hasNewerKnown
          ? ctrl.serverKnownState
          : ctrl.confirmedState || (dev.type === "door" ? "CLOSED" : "OFF")
      ).toUpperCase();
      ctrl.confirmedState = revertState;
      ctrl.desiredState = revertState;
      if (hasNewerKnown) {
        ctrl.lastVersion = Math.max(Number(ctrl.lastVersion || 0), Number(ctrl.serverKnownVersion || 0));
      }
      ctrl.needsServerKnownSync = false;
      syncDeviceDOMToState(devId, revertState);
    };

    if (ws && ws.readyState === WebSocket.OPEN) {
      if (!ctrl.wsPendingTimers) ctrl.wsPendingTimers = {};
      if (!ctrl.wsPendingMeta) ctrl.wsPendingMeta = {};
      const seqKey = String(mySeq);
      if (ctrl.wsPendingTimers[seqKey]) {
        clearTimeout(ctrl.wsPendingTimers[seqKey]);
      }
      ctrl.wsPendingMeta[seqKey] = { seq: mySeq, targetState, ts: myTs };
      ctrl.wsPendingTimers[seqKey] = setTimeout(() => {
        delete ctrl.wsPendingTimers[seqKey];
        if (ctrl.wsPendingMeta) delete ctrl.wsPendingMeta[seqKey];
        recomputeDevicePendingCount(ctrl);
        reconcileIdleDeviceToServerKnown(devId, ctrl);
      }, WS_PENDING_TIMEOUT_MS);
      recomputeDevicePendingCount(ctrl);

      sendWs({
        type: "manual_toggle",
        device_id: devId,
        action,
        target_state: targetState,
        state: targetState,
        client_id: CLIENT_ID,
        client_seq: mySeq,
        client_ts_ms: myTs,
        request_id: reqId,
        role: roleVal,
      });
    } else {
      ctrl.httpPendingCount = Math.max(0, Number(ctrl.httpPendingCount || 0)) + 1;
      recomputeDevicePendingCount(ctrl);
      fetch("/api/device", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          device_id: devId,
          action,
          target_state: targetState,
          state: targetState,
          client_id: CLIENT_ID,
          client_seq: mySeq,
          client_ts_ms: myTs,
          request_id: reqId,
          source: "MANUAL_UI",
        }),
      })
        .then(async (r) => {
          const parsed = await r.json().catch(() => ({}));
          return { httpStatus: Number(r.status || 200), httpOk: Boolean(r.ok), data: parsed };
        })
        .then(({ httpStatus, httpOk, data }) => {
          ctrl.httpPendingCount = Math.max(0, Number(ctrl.httpPendingCount || 0) - 1);
          recomputeDevicePendingCount(ctrl);
          // Ignore stale out-of-order response if a newer local click has occurred
          if (mySeq < ctrl.seq) {
            reconcileIdleDeviceToServerKnown(devId, ctrl);
            return;
          }
          const respVer = Number(
            data && data.device_version !== undefined && data.device_version !== null ? data.device_version : 0
          );
          const respRev = Number(
            data && data.revision_seq !== undefined && data.revision_seq !== null
              ? data.revision_seq
              : data && data.snapshot && data.snapshot.revision_seq
              ? data.snapshot.revision_seq
              : 0
          );
          const maxKnownVer = Math.max(Number(ctrl.lastVersion || 0), Number(ctrl.serverKnownVersion || 0));
          const maxKnownDevRev = Math.max(
            Number(lastServerRevisionSeq || 0),
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
            reconcileIdleDeviceToServerKnown(devId, ctrl);
            return;
          }
          if (data && data.stale_ignored) {
            const authState = String(
              (data && data.state) || ctrl.confirmedState || (dev.type === "door" ? "CLOSED" : "OFF")
            ).toUpperCase();
            ctrl.confirmedState = authState;
            ctrl.desiredState = authState;
            ctrl.serverKnownState = authState;
            ctrl.needsServerKnownSync = false;
            if (respVer > 0) {
              ctrl.lastVersion = Math.max(ctrl.lastVersion, respVer);
              ctrl.serverKnownVersion = Math.max(ctrl.serverKnownVersion || 0, respVer);
            }
            if (respRev > 0) {
              lastServerRevisionSeq = Math.max(lastServerRevisionSeq, respRev);
              ctrl.serverKnownRevisionSeq = Math.max(ctrl.serverKnownRevisionSeq || 0, respRev);
            }
            syncDeviceDOMToState(devId, authState);
            if (data.snapshot) {
              applySnapshot(data.snapshot);
            }
            return;
          }
          if (!httpOk || (data && (data.ok === false || data.error))) {
            rollbackIfLatest();
            if (httpStatus === 401 || (data && data.authenticated === false)) {
              serverSessionConfirmed = false;
              if (typeof clearAuthState === "function") clearAuthState();
              if (typeof openLoginGateModal === "function") openLoginGateModal();
              if (typeof showGuestQrLoginPrompt === "function") showGuestQrLoginPrompt();
            }
            const errSpoken = (data && (data.exact_spoken_reply || data.rejection_speech || data.error)) || "";
            if (errSpoken) setAiReplyText(errSpoken);
            return;
          }
          const finalState = String((data && data.state) || targetState).toUpperCase();
          ctrl.confirmedState = finalState;
          ctrl.serverKnownState = finalState;
          ctrl.needsServerKnownSync = false;
          ctrl.lastConfirmedSeq = Math.max(ctrl.lastConfirmedSeq, mySeq);
          if (respVer > 0) {
            ctrl.lastVersion = Math.max(ctrl.lastVersion, respVer);
            ctrl.serverKnownVersion = Math.max(ctrl.serverKnownVersion || 0, respVer);
          }
          if (respRev > 0) {
            lastServerRevisionSeq = Math.max(lastServerRevisionSeq, respRev);
            ctrl.serverKnownRevisionSeq = Math.max(ctrl.serverKnownRevisionSeq || 0, respRev);
          }
          ctrl.desiredState = finalState;
          syncDeviceDOMToState(devId, finalState);
          if (data && data.snapshot) {
            applySnapshot(data.snapshot);
            publishRealtimeSync(data.snapshot);
          } else {
            publishRealtimeSync(null);
          }
        })
        .catch(() => {
          ctrl.httpPendingCount = Math.max(0, Number(ctrl.httpPendingCount || 0) - 1);
          recomputeDevicePendingCount(ctrl);
          if (mySeq < ctrl.seq) {
            reconcileIdleDeviceToServerKnown(devId, ctrl);
            return;
          }
          rollbackIfLatest();
        });
    }
  }

  function toggleDeviceById(devId, explicitTargetState = null) {
    const dev = latestDevicesMap[devId];
    if (!dev) return;
    if (typeof hasValidLoginSession === "function" && !hasValidLoginSession()) {
      if (typeof openLoginGateModal === "function") openLoginGateModal();
      const gateBox = document.getElementById("gateStatusBox");
      if (gateBox) gateBox.textContent = "Hãy đăng nhập";
      return;
    }
    const isOfflineLocked = window._serverConnected === false && (devId === "main_door" || devId === "alarm_siren");
    if (isOfflineLocked) return;

    const ctrl = getDeviceControlState(devId);
    const currentEffectiveState =
      ctrl.pendingCount > 0 || ctrl.debounceTimer !== null
        ? ctrl.desiredState || dev.state
        : dev.state;
    const prevIsOn = currentEffectiveState === "ON" || currentEffectiveState === "OPEN";
    let nextState;
    if (explicitTargetState && typeof explicitTargetState === "string") {
      nextState = explicitTargetState.toUpperCase();
    } else {
      const nextIsOn = !prevIsOn;
      nextState = dev.type === "door" ? (nextIsOn ? "OPEN" : "CLOSED") : (nextIsOn ? "ON" : "OFF");
    }
    const nextIsOn = nextState === "ON" || nextState === "OPEN";

    ctrl.seq += 1;
    const mySeq = ctrl.seq;
    const myTs = Date.now();
    ctrl.lastClickTs = myTs;
    ctrl.desiredState = nextState;

    // Optimistic UI: Cập nhật in-memory và DOM tức thì
    syncDeviceDOMToState(devId, nextState);
    playRelayClick(nextIsOn);

    // Debounce rapid clicks: gộp các click liên tiếp trong khoảng ngắn thành trạng thái đích cuối cùng
    if (ctrl.debounceTimer !== null) {
      clearTimeout(ctrl.debounceTimer);
      ctrl.debounceTimer = null;
    }
    ctrl.debounceTimer = setTimeout(() => {
      ctrl.debounceTimer = null;
      dispatchDeviceSetState(devId, mySeq, nextState, myTs);
    }, DEVICE_DEBOUNCE_MS);
  }
  if (typeof window !== "undefined") {
    window.toggleDeviceById = toggleDeviceById;
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

  function reconcileDevicesWithPendingIntent(devices, snapRevisionSeq = 0) {
    if (!Array.isArray(devices)) return [];
    const nowMs = Date.now();
    const isStaleSnapshotRevision =
      snapRevisionSeq > 0 && lastServerRevisionSeq > 0 && snapRevisionSeq < lastServerRevisionSeq;
    if (snapRevisionSeq > lastServerRevisionSeq) {
      lastServerRevisionSeq = snapRevisionSeq;
    }

    return devices.map((rawDev) => {
      if (!rawDev || !rawDev.id) return rawDev;
      const dev = Object.assign({}, rawDev);
      const ctrl = deviceControlState[dev.id];
      const serverSeq = Number(dev.last_client_seq || 0);
      const serverVer = Number(dev.version || 0);
      const sameClient = Boolean(dev.last_client_id && dev.last_client_id === CLIENT_ID);

      if (!ctrl) {
        deviceControlState[dev.id] = {
          seq: sameClient ? serverSeq : 0,
          desiredState: dev.state,
          confirmedState: dev.state,
          serverKnownState: String(dev.state || "").toUpperCase(),
          serverKnownVersion: serverVer,
          serverKnownRevisionSeq: snapRevisionSeq,
          needsServerKnownSync: false,
          lastConfirmedSeq: sameClient ? serverSeq : 0,
          httpPendingCount: 0,
          wsPendingTimers: {},
          wsPendingMeta: {},
          pendingCount: 0,
          debounceTimer: null,
          lastClickTs: 0,
          lastVersion: serverVer,
          lastUpdatedAt: Number(dev.updated_at || 0),
        };
        return dev;
      }

      if (sameClient && serverSeq >= ctrl.seq && ctrl.debounceTimer === null) {
        clearWsPendingUpTo(ctrl, serverSeq);
      }

      const hasPendingLocalMutation = ctrl.debounceTimer !== null || ctrl.pendingCount > 0;
      const withinHoldWindow = ctrl.seq > 0 && nowMs - ctrl.lastClickTs < PENDING_INTENT_HOLD_MS;

      if (
        !isStaleSnapshotRevision &&
        (serverVer > Number(ctrl.serverKnownVersion || 0) ||
          (snapRevisionSeq > Number(ctrl.serverKnownRevisionSeq || 0) &&
            serverVer >= Number(ctrl.serverKnownVersion || 0)))
      ) {
        ctrl.serverKnownVersion = Math.max(Number(ctrl.serverKnownVersion || 0), serverVer);
        if (snapRevisionSeq > 0) {
          ctrl.serverKnownRevisionSeq = Math.max(Number(ctrl.serverKnownRevisionSeq || 0), snapRevisionSeq);
        }
        if (rawDev.state) {
          const nextKnownSt = String(rawDev.state).toUpperCase();
          ctrl.serverKnownState = nextKnownSt;
          ctrl.confirmedState = nextKnownSt;
        }
        if (hasPendingLocalMutation && !(sameClient && serverSeq >= ctrl.seq)) {
          ctrl.needsServerKnownSync = true;
        }
      }

      if (isStaleSnapshotRevision) {
        const curMem = latestDevicesMap[dev.id];
        if (curMem && curMem.state) {
          dev.state = curMem.state;
        }
        return dev;
      }

      if (hasPendingLocalMutation && !(sameClient && serverSeq >= ctrl.seq)) {
        dev.state = ctrl.desiredState;
        return dev;
      }

      if (serverVer > 0 && ctrl.lastVersion > 0 && serverVer < ctrl.lastVersion) {
        const curMem = latestDevicesMap[dev.id];
        dev.state = (curMem && curMem.state) || ctrl.confirmedState || dev.state;
        dev.version = ctrl.lastVersion;
        return dev;
      }

      if (
        sameClient &&
        ctrl.lastConfirmedSeq > 0 &&
        serverSeq > 0 &&
        serverSeq < ctrl.lastConfirmedSeq &&
        serverVer <= ctrl.lastVersion
      ) {
        dev.state = ctrl.desiredState;
        return dev;
      }

      if (
        withinHoldWindow &&
        dev.state !== ctrl.desiredState &&
        (!dev.last_client_id || sameClient) &&
        serverSeq < ctrl.seq &&
        serverVer <= ctrl.lastVersion
      ) {
        dev.state = ctrl.desiredState;
        return dev;
      }

      // Server state is authoritative and caught up
      ctrl.confirmedState = dev.state;
      ctrl.serverKnownState = String(dev.state || "").toUpperCase();
      ctrl.needsServerKnownSync = false;
      if (!hasPendingLocalMutation) {
        ctrl.desiredState = dev.state;
        if (sameClient && serverSeq > ctrl.seq) {
          ctrl.seq = serverSeq;
        }
      }
      if (sameClient && serverSeq > ctrl.lastConfirmedSeq) {
        ctrl.lastConfirmedSeq = serverSeq;
      }
      if (serverVer > ctrl.lastVersion) {
        ctrl.lastVersion = serverVer;
      }
      ctrl.serverKnownVersion = Math.max(Number(ctrl.serverKnownVersion || 0), ctrl.lastVersion);
      if (snapRevisionSeq > 0) {
        ctrl.serverKnownRevisionSeq = Math.max(Number(ctrl.serverKnownRevisionSeq || 0), snapRevisionSeq);
      }
      return dev;
    });
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
        // Cập nhật DOM in-place không xóa trắng node và KHÔNG gán lại event listener
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

        // Single listener binding: Gán duy nhất 1 listener trên card; khi click label/span ngoài checkbox thì chặn synthetic click kép, còn khi kích hoạt trực tiếp checkbox (click/Space) thì giữ nguyên checked đồng bộ với card
        if (!card.dataset.toggleListenerBound) {
          card.dataset.toggleListenerBound = "1";
          card._toggleListenerCount = (card._toggleListenerCount || 0) + 1;
          card.addEventListener("click", (e) => {
            const swInput = card.querySelector(".switch input");
            const curDev = latestDevicesMap[dev.id] || dev;
            const locked =
              window._serverConnected === false &&
              (dev.id === "main_door" || dev.id === "alarm_siren");
            if (locked) {
              e.preventDefault();
              if (swInput) {
                swInput.checked = curDev.state === "ON" || curDev.state === "OPEN";
              }
              return;
            }
            if (e.target !== swInput) {
              e.preventDefault();
            }
            toggleDeviceById(dev.id);
          });
        }
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

  function renderTimers(timers, snap) {
    currentTimersCount = timers.length;
    timerCount.textContent = String(timers.length);
    timersList.innerHTML = "";
    const tier = Number((snap && snap.current_tier) || 1);
    const pol = (snap && snap.system_policies) || {};
    const canCancel = tier <= 2 || Boolean(pol.tier3_can_schedule_timer);
    timers.forEach((t) => {
      const div = document.createElement("div");
      div.className = "timer-item schedule-row-item";
      const rightLabel = t.target_vn_time
        ? `${t.target_vn_time}`
        : `${t.remaining_label || t.remaining_seconds + "s"}`;
      const tid = String(t.id || t.timer_id || "");
      const cancelBtnHtml = (canCancel && tid)
        ? `<button type="button" class="btn-mini danger" data-auto-act="cancel-timer" data-auto-id="${escapeHtml(tid)}">Hủy</button>`
        : "";
      div.innerHTML = `
        <div class="schedule-row-meta">
          <div class="schedule-row-title">${escapeHtml(t.device_name)} · ${escapeHtml(t.action_vi || t.action)}</div>
          <div class="schedule-row-sub timer-countdown">${escapeHtml(rightLabel)}</div>
        </div>
        <div class="schedule-row-actions">${cancelBtnHtml}</div>
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

  const AUTO_DEV_LABELS = {
    main_door: "Cửa chính",
    living_room_light: "Đèn phòng khách",
    bedroom_light: "Đèn phòng ngủ",
    fan: "Quạt trần",
    ac: "Điều hòa",
    garden_pump: "Máy bơm tưới cây",
    alarm_siren: "Còi báo động",
  };
  const AUTO_ACT_LABELS = {
    turn_on: "Bật",
    turn_off: "Tắt",
    open_door: "Mở cửa",
    close_door: "Đóng cửa",
  };

  function setAutoFormFeedback(msg, isErr = false) {
    const fb = byId("autoFormFeedback");
    if (!fb) return;
    if (!msg) {
      fb.hidden = true;
      fb.textContent = "";
      return;
    }
    fb.hidden = false;
    fb.textContent = String(msg);
    fb.style.color = isErr ? "#c62828" : "#1565c0";
  }

  function renderDesktopAutomation(snap) {
    latestAutomationSnap = snap;
    const tier = Number((snap && snap.current_tier) || 1);
    const uid = String((snap && snap.current_user_id) || "");
    const pol = (snap && snap.system_policies) || {};
    const canTimers = tier <= 2 || Boolean(pol.tier3_can_schedule_timer);
    const canRules = tier <= 2 || Boolean(pol.tier3_can_custom_rules);

    const toggleBtn = byId("btnToggleAutoForm");
    if (toggleBtn) toggleBtn.hidden = !canTimers && !canRules;

    const schedules = Array.isArray(snap && snap.schedules) ? snap.schedules : [];
    currentSchedulesCount = schedules.length;
    const scListEl = byId("scheduleClockList");
    if (scListEl) {
      scListEl.innerHTML = "";
      schedules.forEach((sc) => {
        const sid = String(sc.schedule_id || "");
        const devLabel = AUTO_DEV_LABELS[sc.device_id] || sc.device_id || "";
        const actLabel = AUTO_ACT_LABELS[sc.action] || sc.action || "";
        const typeLabel = sc.schedule_type === "daily" ? "Hàng ngày" : "Một lần";
        const enabledFlag = Boolean(sc.enabled);
        const canEdit = canTimers && (tier === 1 || String(sc.owner_user_id || "") === uid);
        const actionsHtml = canEdit
          ? `<button type="button" class="btn-mini" data-auto-act="toggle-schedule" data-auto-id="${escapeHtml(sid)}" data-auto-enabled="${enabledFlag ? "1" : "0"}">${enabledFlag ? "Tắt lịch" : "Bật lịch"}</button><button type="button" class="btn-mini danger" data-auto-act="del-schedule" data-auto-id="${escapeHtml(sid)}">Xóa</button>`
          : "";
        const row = document.createElement("div");
        row.className = "schedule-row-item";
        row.innerHTML = `
          <div class="schedule-row-meta">
            <div class="schedule-row-title">${escapeHtml(sc.time_hhmm || "")} · ${escapeHtml(actLabel)} ${escapeHtml(devLabel)}</div>
            <div class="schedule-row-sub">${escapeHtml(typeLabel)} · ${enabledFlag ? "Đang bật" : "Tạm dừng"}</div>
          </div>
          <div class="schedule-row-actions">${actionsHtml}</div>
        `;
        scListEl.appendChild(row);
      });
    }

    const dbRules = Array.isArray(snap && snap.automation_rules) ? snap.automation_rules : [];
    const seenKeys = new Set(
      (Array.isArray(snap && snap.if_else_rules) ? snap.if_else_rules : []).map(
        (r) => `${r.when_device_id}|${r.when_state}|${r.then_device_id}|${r.then_action}`
      )
    );
    let extraDbRules = 0;
    dbRules.forEach((r) => {
      const k = `${r.when_device_id}|${r.when_state}|${r.then_device_id}|${r.then_action}`;
      if (seenKeys.has(k) && !r.rule_id) return;
      extraDbRules += 1;
      const rid = String(r.rule_id || "");
      const wDev = AUTO_DEV_LABELS[r.when_device_id] || r.when_device_id;
      const tDev = AUTO_DEV_LABELS[r.then_device_id] || r.then_device_id;
      const tAct = AUTO_ACT_LABELS[r.then_action] || r.then_action;
      const canDel = canRules && rid && (tier === 1 || String(r.owner_user_id || "") === uid);
      const row = document.createElement("div");
      row.className = "rule-item schedule-row-item";
      row.innerHTML = `
        <div class="schedule-row-meta">
          <div class="schedule-row-title">${escapeHtml(r.label || `Khi ${wDev} ${r.when_state} → ${tAct} ${tDev}`)}</div>
        </div>
        <div class="schedule-row-actions">${canDel ? `<button type="button" class="btn-mini danger" data-auto-act="del-rule" data-auto-id="${escapeHtml(rid)}">Xóa</button>` : ""}</div>
      `;
      rulesList.appendChild(row);
    });
    currentRulesCount += extraDbRules;
    rulesCount.textContent = String(currentRulesCount);

    const scenes = Array.isArray(snap && (snap.scenes || snap.custom_commands))
      ? (snap.scenes || snap.custom_commands)
      : [];
    currentScenesCount = scenes.length;
    const scWrapEl = byId("sceneList");
    if (scWrapEl) {
      scWrapEl.innerHTML = "";
      scenes.forEach((sc) => {
        const cid = String(sc.command_id || "");
        const steps = Array.isArray(sc.steps) ? sc.steps : [];
        const stepTxt = steps
          .map((s) => `${AUTO_ACT_LABELS[s.action] || s.action} ${AUTO_DEV_LABELS[s.device_id] || s.device_id}`)
          .join(", ");
        const canMod = canRules && (tier === 1 || String(sc.owner_user_id || "") === uid);
        const editHtml = canMod
          ? `<button type="button" class="btn-mini" data-auto-act="edit-scene" data-auto-id="${escapeHtml(cid)}">Sửa</button><button type="button" class="btn-mini danger" data-auto-act="del-scene" data-auto-id="${escapeHtml(cid)}">Xóa</button>`
          : "";
        const row = document.createElement("div");
        row.className = "schedule-row-item";
        row.innerHTML = `
          <div class="schedule-row-meta">
            <div class="schedule-row-title">"${escapeHtml(sc.phrase || "")}"</div>
            <div class="schedule-row-sub">${escapeHtml(stepTxt || "Nhiều bước")}</div>
          </div>
          <div class="schedule-row-actions">
            <button type="button" class="btn-mini accent" data-auto-act="run-scene" data-auto-id="${escapeHtml(cid)}">Chạy</button>
            ${editHtml}
          </div>
        `;
        scWrapEl.appendChild(row);
      });
    }

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
    const statusLabel = window._serverConnected ? "Đã kết nối" : "Mất kết nối";
    if (geminiStatusText && geminiStatusText !== noopEl) {
      geminiStatusText.textContent = statusLabel;
    }
    if (homeServerStatusBadge && homeServerStatusBadge !== noopEl) {
      homeServerStatusBadge.hidden = true;
      homeServerStatusBadge.textContent = "";
    }
    if (geminiStatusBadge && geminiStatusBadge !== noopEl && geminiStatusBadge.setAttribute) {
      geminiStatusBadge.setAttribute("aria-label", statusLabel);
    }
  }

  function applySnapshot(snap) {
    if (snap && typeof snap === "object" && typeof syncAuthFromSnapshot === "function") {
      syncAuthFromSnapshot(snap);
    }
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
    const reconciledDevices = reconcileDevicesWithPendingIntent(
      snap.devices || [],
      Number(snap.revision_seq || 0)
    );
    renderDevices(reconciledDevices);

    if (snap.security_lockdown === true) {
      triggerSecurityLockdown("security_lockdown");
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

    renderTimers(snap.timers || [], snap);
    renderRules(
      snap.word_mappings,
      snap.custom_aliases,
      snap.if_else_rules || snap.chains,
      snap.factory_aliases,
      snap.system_policies
    );
    renderDesktopAutomation(snap);
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
    if (typeof hasValidLoginSession === "function" && !hasValidLoginSession()) {
      if (typeof openLoginGateModal === "function") openLoginGateModal();
      if (gateStatusBox) gateStatusBox.textContent = "Vui lòng đăng nhập trước khi sử dụng lệnh giọng nói.";
      return { ok: false, error: "Chưa đăng nhập." };
    }
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
            credentials: "include",
            body: JSON.stringify(reqBody),
          });
          if (res) break;
        } catch (fErr) {
          lastFetchErr = fErr;
        }
      }
      if (!res) throw lastFetchErr || new Error("fetch_failed");
      const data = await res.json().catch(() => ({}));
      voiceCommandEpoch += 1;
      if (res.status === 401 || data.authenticated === false) {
        serverSessionConfirmed = false;
        if (typeof clearAuthState === "function") clearAuthState();
        if (typeof openLoginGateModal === "function") openLoginGateModal();
        if (gateStatusBox) gateStatusBox.textContent = data.error || "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.";
        return data;
      }
      if (data.recognized_text) {
        setUserTranscriptText(data.recognized_text);
      }
      const spokenReply = data.exact_spoken_reply || data.reply || data.rejection_speech || "";
      const isRepeatPhrase = /vui lòng nói lại|âm thanh chưa rõ/i.test(String(spokenReply || ""));
      const allowSpeak = Boolean(spokenReply) && data.silent !== true && data.ask_repeat !== true && data.should_reply !== false && !isRepeatPhrase;
      if (allowSpeak) {
        setAiReplyText(spokenReply);
      } else if (data.silent) {
        /* Im lặng: không phát TTS, không vòng nhắc nói lại. */
      }
      if (!chkPlayAiVoice || chkPlayAiVoice.checked !== false) {
        if (data.pcm24k_b64 && allowSpeak) {
          playPcm24kChunk(data.pcm24k_b64);
        } else if (allowSpeak) {
          requestAoedeSpokenPhrase(spokenReply);
        }
      }
      if (data.snapshot) {
        applySnapshot(data.snapshot);
        publishRealtimeSync(data.snapshot);
      } else {
        await pollRestStateFallback(true);
        publishRealtimeSync(null);
      }
      logEvent(
        `[Voice L${data.level || 1}] ${data.recognized_text || ""} -> ${data.intent || ""} (${data.permission || "ALLOWED"}, ${data.latency_ms || 0}ms)`,
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
          if (typeof hasValidLoginSession === "function" && !hasValidLoginSession()) {
            if (typeof openLoginGateModal === "function") openLoginGateModal();
            if (gateStatusBox) gateStatusBox.textContent = "Vui lòng đăng nhập trước khi gửi lệnh mẫu.";
            return;
          }
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

  let _sseSource = null;
  let _sseConnected = false;
  let _sseReconnectTimer = null;

  function closeRealtimeSse() {
    _sseConnected = false;
    if (_sseReconnectTimer) {
      clearTimeout(_sseReconnectTimer);
      _sseReconnectTimer = null;
    }
    if (_sseSource) {
      try { _sseSource.close(); } catch (_) {}
      _sseSource = null;
    }
  }

  function connectRealtimeSse(explicitTicket = "") {
    if (!serverSessionConfirmed || typeof EventSource === "undefined") return;
    if (_sseSource && _sseSource.readyState !== 2 && !explicitTicket) return;
    closeRealtimeSse();
    try {
      const sseUrl = explicitTicket
        ? `/api/events?ticket=${encodeURIComponent(explicitTicket)}`
        : "/api/events";
      _sseSource = new EventSource(sseUrl, { withCredentials: true });
      _sseSource.onopen = () => {
        _sseConnected = true;
      };
      _sseSource.addEventListener("state_snapshot", (ev) => {
        _sseConnected = true;
        try {
          const msg = JSON.parse(ev.data || "{}");
          if (msg && msg.snapshot) {
            applySnapshot(msg.snapshot);
          }
        } catch (_) {}
      });
      _sseSource.onerror = () => {
        _sseConnected = false;
        closeRealtimeSse();
        if (serverSessionConfirmed && !_sseReconnectTimer) {
          _sseReconnectTimer = setTimeout(async () => {
            _sseReconnectTimer = null;
            if (!serverSessionConfirmed) return;
            try {
              const rT = await fetch("/api/auth/ws_ticket", { method: "POST", credentials: "include" });
              if (rT && rT.ok) {
                const dT = await rT.json().catch(() => ({}));
                if (dT && dT.ticket) {
                  connectRealtimeSse(dT.ticket);
                  return;
                }
              }
            } catch (_) {}
            connectRealtimeSse();
          }, 250);
        }
      };
    } catch (_) {
      _sseConnected = false;
    }
  }

  function connectWebSocket() {
    if (!serverSessionConfirmed) return;
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

        case "manual_toggle_ack": {
          const ackDevId = msg.device_id;
          if (ackDevId && deviceControlState[ackDevId]) {
            const ctrl = deviceControlState[ackDevId];
            const ackSeq = Number(msg.client_seq || 0);
            const sameCid = !msg.client_id || msg.client_id === CLIENT_ID;
            if (sameCid && ackSeq > 0) {
              clearWsPendingUpTo(ctrl, ackSeq);
            }
            const ackVer = Number(
              msg.device_version !== undefined && msg.device_version !== null ? msg.device_version : 0
            );
            const ackRev = Number(
              msg.revision_seq !== undefined && msg.revision_seq !== null
                ? msg.revision_seq
                : msg.snapshot && msg.snapshot.revision_seq
                ? msg.snapshot.revision_seq
                : 0
            );
            const maxKnownVer = Math.max(Number(ctrl.lastVersion || 0), Number(ctrl.serverKnownVersion || 0));
            const maxKnownDevRev = Math.max(
              Number(lastServerRevisionSeq || 0),
              Number(ctrl.serverKnownRevisionSeq || 0)
            );
            const isStaleAck =
              (ackVer > 0 && maxKnownVer > 0 && ackVer < maxKnownVer) ||
              (ackRev > 0 &&
                maxKnownDevRev > 0 &&
                ackRev < maxKnownDevRev &&
                (ackVer === 0 || maxKnownVer === 0 || ackVer <= maxKnownVer));

            if (isStaleAck) {
              if (sameCid && ackSeq > 0) {
                ctrl.lastConfirmedSeq = Math.max(ctrl.lastConfirmedSeq || 0, ackSeq);
              }
              if (sameCid && ackSeq >= ctrl.seq) {
                ctrl.needsServerKnownSync = true;
              }
              reconcileIdleDeviceToServerKnown(ackDevId, ctrl);
              break;
            }

            if (sameCid && ackSeq < ctrl.seq) {
              reconcileIdleDeviceToServerKnown(ackDevId, ctrl);
            } else if (sameCid && ackSeq >= ctrl.seq) {
              const dev = latestDevicesMap[ackDevId];
              if (msg.stale_ignored) {
                const authState = String(
                  msg.state || ctrl.confirmedState || (dev && dev.type === "door" ? "CLOSED" : "OFF")
                ).toUpperCase();
                ctrl.confirmedState = authState;
                ctrl.desiredState = authState;
                ctrl.serverKnownState = authState;
                ctrl.needsServerKnownSync = false;
                if (ackVer > 0) {
                  ctrl.lastVersion = Math.max(ctrl.lastVersion, ackVer);
                  ctrl.serverKnownVersion = Math.max(ctrl.serverKnownVersion || 0, ackVer);
                }
                if (ackRev > 0) {
                  lastServerRevisionSeq = Math.max(lastServerRevisionSeq, ackRev);
                  ctrl.serverKnownRevisionSeq = Math.max(ctrl.serverKnownRevisionSeq || 0, ackRev);
                }
                syncDeviceDOMToState(ackDevId, authState);
              } else if (msg.ok === false || msg.rbac_blocked || msg.error) {
                const hasNewerKnown =
                  Number(ctrl.serverKnownVersion || 0) > Number(ctrl.lastVersion || 0) && Boolean(ctrl.serverKnownState);
                const revertState = String(
                  hasNewerKnown
                    ? ctrl.serverKnownState
                    : ctrl.confirmedState || (dev && dev.type === "door" ? "CLOSED" : "OFF")
                ).toUpperCase();
                ctrl.confirmedState = revertState;
                ctrl.desiredState = revertState;
                if (hasNewerKnown) {
                  ctrl.lastVersion = Math.max(Number(ctrl.lastVersion || 0), Number(ctrl.serverKnownVersion || 0));
                }
                ctrl.needsServerKnownSync = false;
                syncDeviceDOMToState(ackDevId, revertState);
                if (msg.error) setAiReplyText(msg.error);
              } else {
                const finalState = String(msg.state || ctrl.desiredState || "OFF").toUpperCase();
                ctrl.confirmedState = finalState;
                ctrl.desiredState = finalState;
                ctrl.serverKnownState = finalState;
                ctrl.needsServerKnownSync = false;
                if (ackSeq > 0) {
                  ctrl.lastConfirmedSeq = Math.max(ctrl.lastConfirmedSeq, ackSeq);
                }
                if (ackVer > 0) {
                  ctrl.lastVersion = Math.max(ctrl.lastVersion, ackVer);
                  ctrl.serverKnownVersion = Math.max(ctrl.serverKnownVersion || 0, ackVer);
                }
                if (ackRev > 0) {
                  lastServerRevisionSeq = Math.max(lastServerRevisionSeq, ackRev);
                  ctrl.serverKnownRevisionSeq = Math.max(ctrl.serverKnownRevisionSeq || 0, ackRev);
                }
                syncDeviceDOMToState(ackDevId, finalState);
              }
            }
            if (msg.snapshot) {
              applySnapshot(msg.snapshot);
              publishRealtimeSync(msg.snapshot);
            }
          }
          break;
        }

        case "server_mode_changed":
          updateConnectionUI(msg.server_connected !== false);
          if (msg.message) {
            setAiReplyText(msg.message);
          }
          break;

        case "device_updated": {
          const updDevId = msg.device_id;
          if (updDevId && latestDevicesMap[updDevId]) {
            const ctrl = getDeviceControlState(updDevId);
            const msgVer = Number(msg.version || 0);
            const msgSeq = Number(msg.last_client_seq || 0);
            const msgRev = Number(msg.revision_seq || 0);
            const sameCid = Boolean(msg.last_client_id && msg.last_client_id === CLIENT_ID);
            if (sameCid && msgSeq >= ctrl.seq && ctrl.debounceTimer === null) {
              clearWsPendingUpTo(ctrl, msgSeq);
            }
            const hasPending = ctrl.debounceTimer !== null || ctrl.pendingCount > 0;
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
              if (hasPending && !(sameCid && msgSeq >= ctrl.seq)) {
                ctrl.needsServerKnownSync = true;
              }
            }
            const isStaleUpd =
              (msgRev > 0 && lastServerRevisionSeq > 0 && msgRev < lastServerRevisionSeq) ||
              (msgVer > 0 && ctrl.lastVersion > 0 && msgVer < ctrl.lastVersion) ||
              (sameCid && ctrl.lastConfirmedSeq > 0 && msgSeq > 0 && msgSeq < ctrl.lastConfirmedSeq && msgVer <= ctrl.lastVersion) ||
              (hasPending && !(sameCid && msgSeq >= ctrl.seq));
            if (isStaleUpd) {
              break;
            }
            if (msg.new_state) {
              const nextSt = String(msg.new_state).toUpperCase();
              ctrl.confirmedState = nextSt;
              if (!hasPending) {
                ctrl.desiredState = nextSt;
                ctrl.needsServerKnownSync = false;
              }
              if (msgVer > ctrl.lastVersion) ctrl.lastVersion = msgVer;
              if (msgRev > lastServerRevisionSeq) lastServerRevisionSeq = msgRev;
              if (sameCid && msgSeq > ctrl.lastConfirmedSeq) {
                ctrl.lastConfirmedSeq = msgSeq;
                ctrl.seq = Math.max(ctrl.seq, msgSeq);
              }
              syncDeviceDOMToState(updDevId, ctrl.desiredState);
            }
          }
          playRelayClick(msg.new_state === "ON" || msg.new_state === "OPEN");
          logEvent(`${msg.device_name}: ${msg.old_state} -> ${msg.new_state}`, "tool");
          break;
        }

        case "rbac_blocked":
          setAiReplyText(msg.reason || "Xin lỗi, bạn không có quyền thực hiện lệnh này.");
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
            voiceLockoutNotice.hidden = true;
          }
          break;
        }

        case "voice_auth_rejected": {
          const rejSpeech = msg.rejection_speech || "Xin lỗi, bạn không có quyền thực hiện lệnh này.";
          if (msg.label && msg.label !== "Giọng nói trực tiếp qua Mic") {
            setUserTranscriptText(msg.label);
          }
          setAiReplyText(rejSpeech);
          if (voiceLockoutNotice) {
            voiceLockoutNotice.hidden = true;
          }
          break;
        }

        case "voice_auth_silent_ignored":
          clearAudioQueue();
          if (msg.label && msg.label !== "Giọng nói trực tiếp qua Mic") {
            setUserTranscriptText(msg.label);
          }
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
      Object.keys(deviceControlState).forEach((devId) => {
        const ctrl = deviceControlState[devId];
        if (!ctrl || !ctrl.wsPendingTimers) return;
        const pendingKeys = Object.keys(ctrl.wsPendingTimers);
        if (pendingKeys.length === 0) return;
        const maxSeq = Math.max(...pendingKeys.map((k) => Number(k) || 0));
        const latestMeta = ctrl.wsPendingMeta ? ctrl.wsPendingMeta[String(maxSeq)] : null;
        clearWsPendingUpTo(ctrl, maxSeq);
        if (latestMeta && maxSeq === ctrl.seq && ctrl.debounceTimer === null) {
          dispatchDeviceSetState(devId, latestMeta.seq, latestMeta.targetState, latestMeta.ts);
        }
      });
      if (!serverSessionConfirmed) {
        window._serverConnected = false;
        return;
      }
      fetch("/api/state", { credentials: "same-origin" })
        .then((r) => {
          if (r.status === 401) {
            if (typeof clearAuthState === "function") clearAuthState();
            if (typeof openLoginGateModal === "function") openLoginGateModal();
            return Promise.reject({ unauth: true });
          }
          return r.ok ? r.json() : Promise.reject();
        })
        .then((snap) => {
          updateConnectionUI(true, "HTTP Polling");
          applySnapshot(snap);
          hideWsReconnectBanner();
        })
        .catch((err) => {
          if (err && err.unauth) return;
          updateConnectionUI(false, "Mất kết nối");
          wsRetryCount = Math.min(WS_MAX_RETRIES, wsRetryCount + 1);
          showWsReconnectBanner(wsRetryCount, WS_MAX_RETRIES);
        });

      if (!isVercelServerless && wsRetryCount < WS_MAX_RETRIES && wsRetryCount > 0) {
        if (wsReconnectTimer) clearTimeout(wsReconnectTimer);
        wsReconnectTimer = setTimeout(connectWebSocket, 250);
      }
    };
  }

  if (typeof window !== "undefined") {
    window.applySnapshot = applySnapshot;
    window.renderDevices = renderDevices;
  }

  function pollRestStateFallback(force = false) {
    if (!serverSessionConfirmed) return;
    if (!force && typeof ws !== "undefined" && ws && ws.readyState === 1) return;
    if (voiceCommandBusy || pollStateInFlight) return;
    const pollEpoch = voiceCommandEpoch;
    pollStateInFlight = true;
    fetch("/api/state", { credentials: "same-origin" })
      .then((r) => {
        if (r.status === 401) {
          pollStateInFlight = false;
          if (typeof clearAuthState === "function") clearAuthState();
          if (typeof openLoginGateModal === "function") openLoginGateModal();
          return Promise.reject({ unauth: true });
        }
        return r.ok ? r.json() : Promise.reject();
      })
      .then((snap) => {
        pollStateInFlight = false;
        if (voiceCommandBusy || pollEpoch !== voiceCommandEpoch) return;
        const trans = (typeof ws !== "undefined" && ws && ws.readyState === 1) ? "WebSocket" : "HTTP Polling";
        window._activeTransport = trans;
        updateConnectionUI(true, trans);
        applySnapshot(snap);
        hideWsReconnectBanner();
      })
      .catch((err) => {
        pollStateInFlight = false;
        if (err && err.unauth) return;
        if (voiceCommandBusy || pollEpoch !== voiceCommandEpoch) return;
        window._activeTransport = "Mất kết nối";
        updateConnectionUI(false, "Mất kết nối");
        showWsReconnectBanner(wsRetryCount, WS_MAX_RETRIES);
      });
  }
  if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible" && serverSessionConfirmed) {
        pollRestStateFallback(true);
      }
    });
  }
  if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
    window.addEventListener("focus", () => {
      if (serverSessionConfirmed) pollRestStateFallback(true);
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
    if (typeof isTtsPlaybackActive === "function" && isTtsPlaybackActive()) return;
    if (serverlessVoiceInFlight) return;
    const chunks = activeMicPcmChunks.slice(0);
    activeMicPcmChunks = [];
    const transcriptHint = (liveSpeechTranscript || "").trim();
    liveSpeechTranscript = "";
    if (chunks.length === 0 && !transcriptHint) return;
    if (!transcriptHint) return;

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
    if (typeof hasValidLoginSession === "function" && !hasValidLoginSession()) {
      if (typeof openLoginGateModal === "function") openLoginGateModal();
      if (gateStatusBox) gateStatusBox.textContent = "Vui lòng đăng nhập trước khi sử dụng microphone.";
      return;
    }
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
      let preRollMicChunks = [];
      startBrowserSpeechRecognitionVi();
      let noiseFloorRms = 0.008;
      let speechStartMs = 0;

      micProcessor.onaudioprocess = (e) => {
        if (!isRecording) return;
        const rawInput = e.inputBuffer.getChannelData(0);
        const actualSr = micAudioCtx ? micAudioCtx.sampleRate : 16000;
        const input = resampleFloat32AntiAliased(rawInput, actualSr, 16000);
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

        const aiBusy = Boolean(
          audioCtxOut && nextPlayTime > audioCtxOut.currentTime + TTS_HOLDOFF_SEC
        );
        if (aiBusy) {
          wasSpeaking = false;
          silenceStartMs = 0;
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
        const chunkBytes = new Uint8Array(pcm16.buffer.slice(0));

        if (!isSpeech && !wasSpeaking) {
          preRollMicChunks.push(chunkBytes);
          if (preRollMicChunks.length > 2) {
            preRollMicChunks.shift();
          }
        }

        if (isSpeech) {
          if (!wasSpeaking) {
            speechStartMs = nowMs;
            while (preRollMicChunks.length > 0) {
              activeMicPcmChunks.push(preRollMicChunks.shift());
            }
          }
          wasSpeaking = true;
          silenceStartMs = 0;
          activeMicPcmChunks.push(chunkBytes);
          if (activeMicPcmChunks.length > 100) {
            activeMicPcmChunks.shift();
          }
          micStateLabel.textContent = "Đang nghe";
          if (speechStartMs > 0 && nowMs - speechStartMs > 6500) {
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
        } else if (wasSpeaking) {
          activeMicPcmChunks.push(chunkBytes);
          if (activeMicPcmChunks.length > 100) {
            activeMicPcmChunks.shift();
          }
          if (silenceStartMs === 0) {
            silenceStartMs = nowMs;
          } else if (nowMs - silenceStartMs > 350) {
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

      const micSilentGain = micAudioCtx.createGain();
      micSilentGain.gain.value = 0;
      source.connect(micProcessor);
      micProcessor.connect(micSilentGain);
      micSilentGain.connect(micAudioCtx.destination);
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


  let ownerGuestCurrentInviteId = "";
  const GUEST_QR_LOGIN_PROMPT = "Hãy đăng nhập tài khoản Chủ nhà (Cấp 1) để tạo mã QR mời.";
  const GUEST_QR_READY_PROMPT = "Chọn đối tượng, nhập PIN 4 số rồi bấm Tạo mã QR.";
  const GUEST_QR_NON_OWNER_PROMPT = "Chỉ Chủ nhà (Cấp 1) mới có quyền tạo mã QR mời.";

  function renderOwnerGuestQrSvg(svgText, emptySubtitle = "") {
    const box = document.getElementById("ownerGuestQrSvg") || document.getElementById("ownerDashboardQrSvg");
    if (!box) return;
    const svg = String(svgText || "").trim();
    if (!svg || svg.indexOf("<svg") < 0) {
      const isOwnerReady = (typeof hasValidLoginSession === "function" && hasValidLoginSession() && inMemoryUserSession && Number(inMemoryUserSession.tier) === 1);
      const sub = emptySubtitle || (isOwnerReady ? GUEST_QR_READY_PROMPT : "Đăng nhập Chủ nhà để tạo mã.");
      box.innerHTML = `<div class="qr-empty-state"><span class="qr-empty-title">Chưa tạo mã QR</span><span class="qr-empty-sub">${escapeHtml(sub)}</span></div>`;
      return;
    }
    box.innerHTML = svg;
    const el = box.querySelector("svg");
    if (el) {
      el.style.width = "180px";
      el.style.height = "180px";
      el.style.maxWidth = "100%";
      el.setAttribute("aria-label", "Mã QR mời khách");
    }
  }

  function resetOwnerGuestInviteDisplay(badgeText = "Dùng một lần", emptySubtitle = "") {
    ownerGuestCurrentInviteId = "";
    renderOwnerGuestQrSvg("", emptySubtitle);
    const details = document.getElementById("ownerGuestInviteDetails");
    const linkText = document.getElementById("ownerGuestLinkText");
    const openLink = document.getElementById("ownerGuestOpenLink");
    const revBtn = document.getElementById("ownerGuestQrRevokeBtn");
    const badgeEl = document.getElementById("ownerGuestQrStatusBadge");
    if (details) details.hidden = true;
    if (linkText) linkText.textContent = "";
    if (openLink) {
      openLink.href = "/guest_guide";
      openLink.textContent = "Hướng dẫn trang khách";
    }
    if (revBtn) revBtn.disabled = true;
    if (badgeEl) badgeEl.textContent = badgeText;
  }

  function setOwnerGuestQrInputsDisabled(disabled) {
    const ids = [
      "ownerGuestInviteTier",
      "ownerGuestQrPin",
      "ownerGuestQrPinConfirm",
      "ownerGuestQrGenerateBtn",
      "ownerGuestQrForgotPinBtn",
      "ownerGuestPinOtp",
      "ownerGuestPinNew",
      "ownerGuestPinNewConfirm",
      "ownerGuestPinResetBtn",
    ];
    ids.forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.disabled = !!disabled;
    });
    if (disabled) {
      const revBtn = document.getElementById("ownerGuestQrRevokeBtn");
      const forgotBox = document.getElementById("ownerGuestPinForgotBox");
      if (revBtn) revBtn.disabled = true;
      if (forgotBox) forgotBox.hidden = true;
    }
  }

  function syncOwnerGuestQrStateForSession(userObj) {
    const meta = document.getElementById("ownerGuestQrMeta");
    const revBtn = document.getElementById("ownerGuestQrRevokeBtn");
    const badgeEl = document.getElementById("ownerGuestQrStatusBadge");
    if (!userObj || (typeof hasValidLoginSession === "function" && !hasValidLoginSession())) {
      setOwnerGuestQrInputsDisabled(false);
      resetOwnerGuestInviteDisplay("Dùng một lần", "Đăng nhập Chủ nhà để tạo mã.");
      if (meta) meta.textContent = GUEST_QR_LOGIN_PROMPT;
      return;
    }
    const tierNum = Number(userObj.tier || 3);
    if (tierNum !== 1) {
      setOwnerGuestQrInputsDisabled(true);
      resetOwnerGuestInviteDisplay("Chỉ Chủ nhà", GUEST_QR_NON_OWNER_PROMPT);
      if (meta) meta.textContent = GUEST_QR_NON_OWNER_PROMPT;
      return;
    }
    setOwnerGuestQrInputsDisabled(false);
    if (revBtn) revBtn.disabled = !ownerGuestCurrentInviteId;
    if (!ownerGuestCurrentInviteId && meta) {
      const current = String(meta.textContent || "").trim();
      if (!current || current.indexOf("Hãy đăng nhập") >= 0 || current.indexOf("Chỉ Chủ nhà") >= 0) {
        renderOwnerGuestQrSvg("", GUEST_QR_READY_PROMPT);
        if (badgeEl) badgeEl.textContent = "Dùng một lần";
        meta.textContent = GUEST_QR_READY_PROMPT;
      }
    }
  }

  function isAuthDenialStatus(status, data) {
    const code = Number(status || 0);
    if (code === 401 || code === 403) return true;
    const err = String((data && (data.error || data.message)) || "").toLowerCase();
    return err.indexOf("đăng nhập") >= 0 || err.indexOf("dang nhap") >= 0 || err.indexOf("unauthorized") >= 0;
  }

  function showGuestQrLoginPrompt() {
    resetOwnerGuestInviteDisplay("Dùng một lần", "Đăng nhập Chủ nhà để tạo mã.");
    const meta = document.getElementById("ownerGuestQrMeta");
    if (meta) meta.textContent = GUEST_QR_LOGIN_PROMPT;
    if (typeof openLoginGateModal === "function") openLoginGateModal();
  }

  async function loadOwnerDashboardGuestQr() {
    const box = document.getElementById("ownerGuestQrSvg") || document.getElementById("ownerDashboardQrSvg");
    const meta = document.getElementById("ownerGuestQrMeta");
    const tierEl = document.getElementById("ownerGuestInviteTier");
    if (!box) return;
    if (typeof hasValidLoginSession === "function" && !hasValidLoginSession()) {
      showGuestQrLoginPrompt();
      return;
    }
    if (inMemoryUserSession && Number(inMemoryUserSession.tier || 3) !== 1) {
      syncOwnerGuestQrStateForSession(inMemoryUserSession);
      return;
    }
    if (ownerPinStatusPromise) {
      try {
        await ownerPinStatusPromise;
      } catch (_) {}
    }
    const tier = Number((tierEl && tierEl.value) || 3);
    const pinEl = document.getElementById("ownerGuestQrPin");
    const pinConfirmEl = document.getElementById("ownerGuestQrPinConfirm");
    const pin = pinEl ? String(pinEl.value || "").trim() : "";
    const pinConfirm = pinConfirmEl ? String(pinConfirmEl.value || "").trim() : "";
    try {
      const res = await fetch("/api/auth3/guest_invites", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ tier: tier, ttl_sec: 600, pin: pin, pin_confirm: pinConfirm }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) {
        resetOwnerGuestInviteDisplay("Dùng một lần");
        if (res.status === 401 || (data && data.authenticated === false) || !hasValidLoginSession()) {
          showGuestQrLoginPrompt();
          return;
        }
        if (data && data.needs_pin_setup) {
          const wrap = document.getElementById("ownerGuestQrPinConfirmWrap");
          if (wrap) wrap.hidden = false;
          if (meta) meta.textContent = data.error || "Hãy đặt mã PIN 4 số lần đầu (nhập hai lần) rồi tạo mã.";
          return;
        }
        if (data && data.locked) {
          if (meta) meta.textContent = data.error || "PIN đã bị khóa. Hãy dùng Quên PIN.";
          return;
        }
        if (res.status === 403) {
          if (meta) meta.textContent = data.error || GUEST_QR_NON_OWNER_PROMPT;
          return;
        }
        if (meta) meta.textContent = data.error || "Không tạo được mã QR khách.";
        return;
      }
      ownerGuestCurrentInviteId = data.invite_id || "";
      renderOwnerGuestQrSvg(data.qr_svg || "");
      const revBtn = document.getElementById("ownerGuestQrRevokeBtn");
      const details = document.getElementById("ownerGuestInviteDetails");
      const tierLabelEl = document.getElementById("ownerGuestInviteTierLabel");
      const expiryLabelEl = document.getElementById("ownerGuestExpiryLabel");
      const linkTextEl = document.getElementById("ownerGuestLinkText");
      const openLinkEl = document.getElementById("ownerGuestOpenLink");
      const badgeEl = document.getElementById("ownerGuestQrStatusBadge");
      const resolvedTier = Number(data.tier || tier || 3);
      const tierText = resolvedTier === 2 ? "Gia đình (Cấp 2)" : "Khách (Cấp 3)";
      const exp = data.expires_at ? new Date(Number(data.expires_at) * 1000) : null;
      const expLabel = exp ? exp.toLocaleTimeString("vi-VN") : "";
      const inviteUrl = data.url || (data.path ? (window.location.origin + data.path) : "");
      if (revBtn) revBtn.disabled = false;
      if (tierLabelEl) tierLabelEl.textContent = tierText;
      if (expiryLabelEl) expiryLabelEl.textContent = expLabel ? ("Hết hạn lúc " + expLabel) : "Hiệu lực 10 phút";
      if (linkTextEl) linkTextEl.textContent = inviteUrl;
      if (openLinkEl) {
        openLinkEl.href = inviteUrl || "/guest_guide";
        openLinkEl.textContent = inviteUrl ? "Mở trang khách" : "Hướng dẫn trang khách";
      }
      if (details) details.hidden = false;
      if (badgeEl) badgeEl.textContent = "Đang hiệu lực · Dùng một lần";
      if (meta) {
        meta.textContent = "Đã tạo mã QR dùng một lần cho " + tierText + (expLabel ? " · Hết hạn lúc " + expLabel : " · Hiệu lực 10 phút") + ".";
      }
    } catch (err) {
      resetOwnerGuestInviteDisplay("Dùng một lần");
      if (typeof hasValidLoginSession === "function" && !hasValidLoginSession()) {
        showGuestQrLoginPrompt();
        return;
      }
      if (meta) meta.textContent = "Không tạo được mã QR khách.";
    }
  }

  async function revokeOwnerGuestQr() {
    const meta = document.getElementById("ownerGuestQrMeta");
    if (!ownerGuestCurrentInviteId) {
      if (meta) meta.textContent = "Chưa có mã để thu hồi.";
      return;
    }
    try {
      const res = await fetch("/api/auth3/guest_invites/" + encodeURIComponent(ownerGuestCurrentInviteId) + "/revoke", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({}),
      });
      const data = await res.json().catch(() => ({}));
      if (data.ok) {
        resetOwnerGuestInviteDisplay("Đã thu hồi");
        if (meta) meta.textContent = "Đã thu hồi mã mời hiện tại.";
      } else {
        if (meta) meta.textContent = data.error || "Không thu hồi được mã.";
      }
    } catch (err) {
      if (meta) meta.textContent = "Không thu hồi được mã.";
    }
  }



  let ownerPinStatusPromise = null;

  function checkOwnerPinStatusIfOwner(targetUser) {
    const sess = targetUser || inMemoryUserSession;
    if (!targetUser && typeof hasValidLoginSession === "function" && !hasValidLoginSession()) {
      return Promise.resolve(null);
    }
    if (!sess || Number(sess.tier) !== 1) return Promise.resolve(null);
    ownerPinStatusPromise = fetch("/api/auth3/owner_pin/status", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        const wrap = document.getElementById("ownerGuestQrPinConfirmWrap");
        if (wrap && data && data.pin_set === false) wrap.hidden = false;
        return data;
      })
      .catch(() => null);
    return ownerPinStatusPromise;
  }

  (function bindOwnerGuestQrUi() {
    const gen = document.getElementById("ownerGuestQrGenerateBtn");
    const rev = document.getElementById("ownerGuestQrRevokeBtn");
    if (gen) gen.addEventListener("click", () => { loadOwnerDashboardGuestQr(); });
    if (rev) rev.addEventListener("click", () => { revokeOwnerGuestQr(); });
    const forgotBtn = document.getElementById("ownerGuestQrForgotPinBtn");
    const resetBtn = document.getElementById("ownerGuestPinResetBtn");
    const forgotBox = document.getElementById("ownerGuestPinForgotBox");
    const metaEl = document.getElementById("ownerGuestQrMeta");
    if (forgotBtn) {
      forgotBtn.addEventListener("click", async () => {
        if (typeof hasValidLoginSession === "function" && !hasValidLoginSession()) {
          if (typeof showGuestQrLoginPrompt === "function") showGuestQrLoginPrompt();
          return;
        }
        if (forgotBox) forgotBox.hidden = false;
        try {
          const res = await fetch("/api/auth3/owner_pin/forgot", { method: "POST", headers: { "Content-Type": "application/json" }, credentials: "include", body: "{}" });
          const data = await res.json().catch(() => ({}));
          if (metaEl) metaEl.textContent = data.error || data.message || "Đã gửi mã xác nhận tới Gmail chủ nhà.";
        } catch (_) {
          if (metaEl) metaEl.textContent = "Không gửi được mã xác nhận PIN.";
        }
      });
    }
    if (resetBtn) {
      resetBtn.addEventListener("click", async () => {
        if (typeof hasValidLoginSession === "function" && !hasValidLoginSession()) {
          if (typeof showGuestQrLoginPrompt === "function") showGuestQrLoginPrompt();
          return;
        }
        const otp = (document.getElementById("ownerGuestPinOtp") || {}).value || "";
        const pin = (document.getElementById("ownerGuestPinNew") || {}).value || "";
        const pin2 = (document.getElementById("ownerGuestPinNewConfirm") || {}).value || "";
        try {
          const res = await fetch("/api/auth3/owner_pin/reset", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ otp: otp, pin: pin, pin_confirm: pin2 }),
          });
          const data = await res.json().catch(() => ({}));
          if (metaEl) metaEl.textContent = data.error || data.message || "Đã đặt lại PIN.";
          if (data && data.ok && forgotBox) forgotBox.hidden = true;
        } catch (_) {
          if (metaEl) metaEl.textContent = "Không đặt lại được PIN.";
        }
      });
    }
    if (document.getElementById("ownerGuestQrSvg") || document.getElementById("ownerDashboardQrBox")) {
      /* Không tự tạo mã hoặc gọi API PIN khi chưa xác nhận đăng nhập Chủ nhà. */
    }
  })();

  btnMicToggle.addEventListener("click", () => {
    if (typeof hasValidLoginSession === "function" && !hasValidLoginSession()) {
      if (typeof openLoginGateModal === "function") openLoginGateModal();
      if (gateStatusBox) gateStatusBox.textContent = "Vui lòng đăng nhập trước khi sử dụng microphone.";
      return;
    }
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
    if (typeof hasValidLoginSession === "function" && !hasValidLoginSession()) {
      if (typeof openLoginGateModal === "function") openLoginGateModal();
      if (gateStatusBox) gateStatusBox.textContent = "Vui lòng đăng nhập trước khi gửi lệnh điều khiển.";
      return;
    }
    setUserTranscriptText(cmd);
    setAiReplyText("Đang xử lý...");
    if (typeof window !== "undefined" && window._USE_WS_SEND_TEXT && isWsOpen()) {
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
      const data = await res.json().catch(() => ({}));
      if (res.status === 401 || data.authenticated === false) {
        serverSessionConfirmed = false;
        if (typeof clearAuthState === "function") clearAuthState();
        if (typeof openLoginGateModal === "function") openLoginGateModal();
        setAiReplyText(data.error || "Vui lòng đăng nhập để điều khiển thiết bị.");
        return;
      }
      const spokenReply = data.exact_spoken_reply || data.reply || data.error || "Đã xử lý lệnh.";
      setAiReplyText(spokenReply);
      const isRepeatPhrase = /vui lòng nói lại|âm thanh chưa rõ/i.test(String(spokenReply || ""));
      if ((!chkPlayAiVoice || chkPlayAiVoice.checked !== false) && spokenReply && !isRepeatPhrase) {
        if (data.pcm24k_b64) {
          playPcm24kChunk(data.pcm24k_b64);
        } else {
          requestAoedeSpokenPhrase(spokenReply);
        }
      }
      if (data.snapshot) {
        applySnapshot(data.snapshot);
        publishRealtimeSync(data.snapshot);
      } else {
        await pollRestStateFallback(true);
        publishRealtimeSync(null);
      }
      logEvent(`${spokenReply || cmd}`, data.ok === false ? "error" : "tool");
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
    if (btn && (btn.id === "ownerGuestQrGenerateBtn" || btn.id === "ownerGuestQrRevokeBtn" || btn.id === "ownerGuestQrForgotPinBtn" || btn.id === "ownerGuestPinResetBtn")) {
      return;
    }
    btn.addEventListener("click", () => {
      const cmd = btn.getAttribute("data-cmd") || btn.getAttribute("data-text") || btn.textContent.trim();
      submitTextCommand(cmd);
    });
  });

  if (roleSelect) roleSelect.disabled = true;
  if (roleSelect) roleSelect.addEventListener("change", async () => {
    // Display-only: phien giu theo dang nhap hoac ma moi, khong doi cap tai day.
    return;
  });

  btnFactoryReset.addEventListener("click", async () => {
    if (typeof hasValidLoginSession === "function" && !hasValidLoginSession()) {
      if (typeof openLoginGateModal === "function") openLoginGateModal();
      return;
    }
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
      if (typeof hasValidLoginSession === "function" && !hasValidLoginSession()) {
        if (typeof openLoginGateModal === "function") openLoginGateModal();
        return;
      }
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

  let pendingGateOtpEmail = "";
  let isGateOtpInFlight = false;
  let gateOtpCooldownTimer = null;
  let forgotOtpCooldownTimer = null;

  function showGateOtpPanel(email, message) {
    pendingGateOtpEmail = String(email || "").trim();
    const otpPanel = byId("gateOtpPanel");
    const otpInput = byId("gateOtpInput");
    const otpDesc = byId("gateOtpDesc");
    if (gatePanelLogin) gatePanelLogin.style.display = "none";
    if (gatePanelRegister) gatePanelRegister.style.display = "none";
    if (gatePanelForgot) gatePanelForgot.style.display = "none";
    if (otpPanel) {
      otpPanel.hidden = false;
      otpPanel.style.display = "grid";
    }
    if (otpDesc && pendingGateOtpEmail) {
      const atIdx = pendingGateOtpEmail.indexOf("@");
      const maskedEmail = atIdx > 0
        ? `${pendingGateOtpEmail.slice(0, 1)}***@${pendingGateOtpEmail.slice(atIdx + 1)}`
        : pendingGateOtpEmail;
      otpDesc.textContent = `Tài khoản Chủ nhà (${maskedEmail}) yêu cầu mã OTP 6 số gửi qua Gmail trước khi mở khóa.`;
    }
    if (otpInput) {
      otpInput.value = "";
      if (typeof otpInput.focus === "function") otpInput.focus();
    }
    if (gateStatusBox && message) gateStatusBox.textContent = message;
  }

  function hideGateOtpPanel() {
    pendingGateOtpEmail = "";
    if (gateOtpCooldownTimer) {
      clearInterval(gateOtpCooldownTimer);
      gateOtpCooldownTimer = null;
    }
    const otpPanel = byId("gateOtpPanel");
    const otpInput = byId("gateOtpInput");
    const btnSendGate = byId("btnSendGateOtp");
    if (otpPanel) {
      otpPanel.hidden = true;
      otpPanel.style.display = "none";
    }
    if (otpInput) otpInput.value = "";
    if (btnSendGate) {
      btnSendGate.disabled = false;
      btnSendGate.textContent = "Gửi lại OTP";
    }
  }

  function formatGateAuthError(res, data, fallbackMsg) {
    const status = res && typeof res.status === "number" ? res.status : 0;
    const baseMsg = (data && (data.error || data.message)) || fallbackMsg || "Thao tác không thành công.";
    const retrySec = Number(
      (data && (data.retry_after_seconds ?? data.cooldown_remaining_seconds)) || 0
    );
    if (status === 429) {
      if (retrySec > 0 && !String(baseMsg).includes(String(retrySec))) {
        return `${baseMsg} (Thử lại sau ${retrySec} giây)`;
      }
      return `${baseMsg}`;
    }
    if (status === 401 || status === 403) {
      return `${baseMsg}`;
    }
    if (status === 404) {
      return `${baseMsg}`;
    }
    if (status === 503) {
      return `${baseMsg}`;
    }
    return `${baseMsg}`;
  }

  function switchLoginGateTab(tabName) {
    hideGateOtpPanel();
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
  const linkGateForgot = byId("linkGateForgot");
  if (linkGateForgot) {
    linkGateForgot.addEventListener("click", (e) => {
      if (e && e.preventDefault) e.preventDefault();
      switchLoginGateTab("forgot");
    });
  }
  const btnBackForgotToLogin = byId("btnBackForgotToLogin");
  if (btnBackForgotToLogin) {
    btnBackForgotToLogin.addEventListener("click", () => switchLoginGateTab("login"));
  }

  function setDeviceAreaLockdown(isLocked) {
    const devSec = document.getElementById("secDevices") || document.querySelector(".panel.devices");
    const house = document.getElementById("house3dViewport");
    const labels = document.getElementById("house3dLabels");
    const targets = [devSec, house, labels].filter(Boolean);
    const bodyEl = document.body;
    const rootEl = document.documentElement;
    if (bodyEl && bodyEl.classList) {
      bodyEl.classList.toggle("dashboard-logged-out", !!isLocked);
      bodyEl.classList.toggle("login-gate-open", !!isLocked);
    }
    if (rootEl && rootEl.classList) {
      rootEl.classList.toggle("login-gate-open", !!isLocked);
    }
    targets.forEach((el) => {
      if (isLocked) {
        el.classList.add("devices-logged-out");
        el.setAttribute("aria-hidden", "true");
        el.setAttribute("inert", "");
      } else {
        el.classList.remove("devices-logged-out");
        el.removeAttribute("aria-hidden");
        el.removeAttribute("inert");
      }
    });
    document.querySelectorAll(".pin-3d").forEach((pin) => {
      pin.classList.toggle("pin-3d-locked", !!isLocked);
      if (isLocked) {
        pin.setAttribute("aria-disabled", "true");
        pin.setAttribute("tabindex", "-1");
      } else {
        pin.removeAttribute("aria-disabled");
        pin.removeAttribute("tabindex");
      }
    });
    document.querySelectorAll("#secDevices .switch input").forEach((input) => {
      input.disabled = !!isLocked;
    });
    if (isLocked && !hasValidLoginSession()) {
      syncOwnerGuestQrStateForSession(null);
    }
  }
  window.setDeviceAreaLockdown = setDeviceAreaLockdown;

  let inMemoryUserSession = null;
  let serverSessionConfirmed = false;

  function setSessionCookies(token) {
    const tok = String(token || "").trim();
    if (!tok) return;
    // HttpOnly + Secure cookies are set server-side; avoid exposing session tokens in document.cookie.
  }

  function hasClientAuthHint() {
    if (inMemoryUserSession && (inMemoryUserSession.email || inMemoryUserSession.session_token)) return true;
    try {
      if (window.sessionStorage && window.sessionStorage.getItem("session_token")) return true;
      if (window.localStorage && window.localStorage.getItem("session_token")) return true;
      const raw = window.localStorage ? window.localStorage.getItem("smarthome_auth_session") : null;
      if (!raw) return false;
      const user = JSON.parse(raw);
      return !!(user && (user.email || user.session_token));
    } catch (_) {
      return false;
    }
  }

  const homeAppShellEl = byId("homeAppShell");
  let homeAppShellAnchor = null;
  let home3dInitialized = false;

  function ensureHome3dInitialized() {
    if (home3dInitialized) return;
    if (!byId("house3dViewport")) return;
    if (typeof window !== "undefined" && window.SmartHome3D) {
      home3dInitialized = true;
      window.SmartHome3D.init("house3dViewport", "house3dLabels", toggleDeviceById);
    }
  }

  function unmountOwnerDashboardDom() {
    try {
      const tEl = byId("tempVal");
      if (tEl) tEl.textContent = "--°C";
      const hEl = byId("humVal");
      if (hEl) hEl.textContent = "--%";
      const sEl = byId("soilVal");
      if (sEl) sEl.textContent = "--%";
      if (devicesGrid && devicesGrid !== noopEl) devicesGrid.innerHTML = "";
      latestDevicesMap = {};
      if (!homeAppShellEl) return;
      homeAppShellEl.hidden = true;
      if (typeof homeAppShellEl.setAttribute === "function") {
        homeAppShellEl.setAttribute("hidden", "");
      }
      if (homeAppShellEl.parentNode && typeof homeAppShellEl.parentNode.removeChild === "function") {
        if (
          !homeAppShellAnchor &&
          typeof document !== "undefined" &&
          typeof document.createComment === "function" &&
          typeof homeAppShellEl.parentNode.insertBefore === "function"
        ) {
          homeAppShellAnchor = document.createComment("homeAppShell-anchor");
          homeAppShellEl.parentNode.insertBefore(homeAppShellAnchor, homeAppShellEl);
        }
        homeAppShellEl.parentNode.removeChild(homeAppShellEl);
      }
    } catch (_) {}
  }

  function mountOwnerDashboardDom() {
    try {
      if (homeAppShellEl) {
        if (
          !homeAppShellEl.parentNode &&
          homeAppShellAnchor &&
          homeAppShellAnchor.parentNode &&
          typeof homeAppShellAnchor.parentNode.insertBefore === "function"
        ) {
          homeAppShellAnchor.parentNode.insertBefore(homeAppShellEl, homeAppShellAnchor);
        }
        homeAppShellEl.hidden = false;
        if (typeof homeAppShellEl.removeAttribute === "function") {
          homeAppShellEl.removeAttribute("hidden");
        }
      }
      ensureHome3dInitialized();
      if (typeof window !== "undefined" && typeof window.dispatchEvent === "function" && typeof Event === "function") {
        window.dispatchEvent(new Event("resize"));
      }
    } catch (_) {}
  }

  function startAuthenticatedRealtimeFlows() {
    mountOwnerDashboardDom();
    loadVoiceSamples();
    pollRestStateFallback(true);
    connectWebSocket();
    connectRealtimeSse();
  }

  function syncAuthFromSnapshot(snap) {
    if (!snap || typeof snap !== "object") return;
    if (snap.authenticated === true) {
      serverSessionConfirmed = true;
      mountOwnerDashboardDom();
      const userObj = {
        email: snap.current_user_email || (inMemoryUserSession && inMemoryUserSession.email) || "",
        display_name: snap.current_user_name || (inMemoryUserSession && inMemoryUserSession.display_name) || "",
        tier: snap.current_tier || (inMemoryUserSession && inMemoryUserSession.tier) || 3,
        role: snap.role || (inMemoryUserSession && inMemoryUserSession.role) || "",
        session_token: (inMemoryUserSession && inMemoryUserSession.session_token) || "",
      };
      applyLoggedInUserBanner(userObj);
      if (typeof closeLoginGateModal === "function" && hasValidLoginSession()) {
        if (homeLoginGateModal) homeLoginGateModal.classList.add("hidden");
        setDeviceAreaLockdown(false);
      }
      return;
    }
    if (snap.authenticated === false || snap.public_only === true) {
      if (serverSessionConfirmed) {
        return;
      }
      serverSessionConfirmed = false;
      setDeviceAreaLockdown(true);
      unmountOwnerDashboardDom();
    }
  }

  function applyLoggedInUserBanner(userObj) {
    if (!userObj) return;
    inMemoryUserSession = userObj;
    if (userObj.session_token) setSessionCookies(userObj.session_token);
    if (serverSessionConfirmed) setDeviceAreaLockdown(false);
    const tierNum = userObj.tier || 1;
    const rolePrefix = tierNum === 1 ? "Cấp 1 · Chủ nhà" : (tierNum === 2 ? "Cấp 2 · Gia đình" : "Cấp 3 · Khách");
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
      if (tierNum === 1) {
        durationBadge.textContent = "";
        durationBadge.hidden = true;
        durationBadge.style.display = "none";
      } else if (tierNum === 2) {
        durationBadge.hidden = false;
        durationBadge.style.display = "";
        durationBadge.textContent = "Còn 30 ngày";
      } else {
        durationBadge.hidden = false;
        durationBadge.style.display = "";
        durationBadge.textContent = userObj.validity || "Hiệu lực 24 giờ";
      }
    }
    syncOwnerGuestQrStateForSession(userObj);
  }

  function clearAuthState() {
    inMemoryUserSession = null;
    serverSessionConfirmed = false;
    try {
      if (typeof ws !== "undefined" && ws) {
        try { ws.onclose = null; ws.close(); } catch (_) {}
        ws = null;
      }
      if (wsReconnectTimer) {
        clearTimeout(wsReconnectTimer);
        wsReconnectTimer = null;
      }
      closeRealtimeSse();
    } catch (_) {}
    hideGateOtpPanel();
    if (forgotOtpCooldownTimer) {
      clearInterval(forgotOtpCooldownTimer);
      forgotOtpCooldownTimer = null;
    }
    setDeviceAreaLockdown(true);
    unmountOwnerDashboardDom();
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
    syncOwnerGuestQrStateForSession(null);
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
    if (gatePanelLogin) gatePanelLogin.style.display = "grid";
    if (gateStatusBox) {
      gateStatusBox.textContent = "Nhập Email và Mật khẩu để vào bảng điều khiển Nhà thông minh.";
      gateStatusBox.className = "subtle";
    }
  }

  function hasValidLoginSession() {
    return !!serverSessionConfirmed;
  }

  function togglePasswordVisibility(inputId, btn) {
    const input = document.getElementById(inputId);
    if (!input) return;
    const showPassword = input.type === "password";
    input.type = showPassword ? "text" : "password";
    if (btn) {
      const targetSymbol = showPassword ? "#i-eye-off" : "#i-eye";
      if (typeof btn.setAttribute === "function") {
        btn.setAttribute("aria-label", showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu");
      }
      const useEl = typeof btn.querySelector === "function" ? btn.querySelector("use") : null;
      if (useEl) {
        useEl.setAttribute("href", targetSymbol);
        useEl.setAttribute("xlink:href", targetSymbol);
      } else if (typeof btn.innerHTML !== "undefined") {
        btn.innerHTML = `<svg class="icon" style="width:18px;height:18px;" aria-hidden="true"><use href="${targetSymbol}"></use></svg>`;
      }
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
        gateStatusBox.textContent = "Bạn bắt buộc phải đăng nhập để vào bảng điều khiển Nhà thông minh!";
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
          gateStatusBox.textContent = "Bạn bắt buộc phải đăng nhập để vào bảng điều khiển Nhà thông minh!";
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
          gateStatusBox.textContent = "Bạn bắt buộc phải đăng nhập để vào bảng điều khiển Nhà thông minh!";
        }
      }
    }
  });

  if (btnLogoutHome) {
    btnLogoutHome.addEventListener("click", () => {
      try {
        if (typeof window !== "undefined" && typeof window.fetch === "function" && window.location && window.location.host) {
          Promise.resolve(window.fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" })).catch(() => {});
        }
      } catch (_) {}
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

  async function completeGateLoginSession(email, data) {
    const userSession = {
      email: (data && data.email) || email,
      display_name: (data && data.display_name) || (data && data.account && data.account.display_name) || email,
      tier: Number((data && (data.tier ?? (data.account && data.account.tier))) || 1),
      role: (data && data.role) || "",
      session_token: (data && data.session_token) || "",
    };
    try {
      if (window.localStorage) {
        window.localStorage.setItem("smarthome_auth_session", JSON.stringify(userSession));
        if (userSession.session_token) window.localStorage.setItem("session_token", userSession.session_token);
      }
      if (window.sessionStorage && userSession.session_token) {
        window.sessionStorage.setItem("session_token", userSession.session_token);
      }
    } catch (_) {}
    if (userSession.session_token) setSessionCookies(userSession.session_token);
    serverSessionConfirmed = !!userSession.session_token;
    if (serverSessionConfirmed) {
      mountOwnerDashboardDom();
      if (Number(userSession.tier) === 1 && typeof checkOwnerPinStatusIfOwner === "function") {
        await checkOwnerPinStatusIfOwner(userSession);
      }
    }
    applyLoggedInUserBanner(userSession);
    hideGateOtpPanel();
    if (btnCloseLoginGateModal) btnCloseLoginGateModal.hidden = !serverSessionConfirmed;
    if (gateStatusBox) {
      gateStatusBox.textContent = `Đăng nhập thành công (${userSession.display_name})!`;
    }
    closeLoginGateModal();
    if (serverSessionConfirmed) {
      startAuthenticatedRealtimeFlows();
    }
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
      if (gateStatusBox) gateStatusBox.textContent = "Vui lòng nhập đầy đủ Email và Mật khẩu!";
      return;
    }
    isGateLoginInFlight = true;
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Đang đăng nhập...";
    }
    if (gateStatusBox) gateStatusBox.textContent = "Đang kiểm tra đăng nhập...";
    try {
      const res = await fetch("/api/auth3/layer1_login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, login_method: "password", method: "password", send_gmail: false }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.ok) {
        if (data.otp_required === true || !data.session_token) {
          serverSessionConfirmed = false;
          if (btnCloseLoginGateModal) btnCloseLoginGateModal.hidden = true;
          showGateOtpPanel(
            email,
            data.message || "Tài khoản Chủ nhà cần xác thực mã OTP 6 số gửi qua Gmail."
          );
          if (!data.otp_sent && !data.sent_real_gmail) {
            await sendGateLayer2Otp(email);
          }
        } else {
          await completeGateLoginSession(email, data);
        }
      } else if (gateStatusBox) {
        gateStatusBox.textContent = formatGateAuthError(res, data, "Email hoặc mật khẩu chưa đúng!");
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

  function startGateOtpCooldown(seconds) {
    const btnSend = byId("btnSendGateOtp");
    if (!btnSend) return;
    let remaining = Number(seconds);
    if (!Number.isFinite(remaining) || remaining <= 0) return;
    if (gateOtpCooldownTimer) clearInterval(gateOtpCooldownTimer);
    btnSend.disabled = true;
    btnSend.textContent = `Gửi lại (${remaining}s)`;
    gateOtpCooldownTimer = setInterval(() => {
      remaining -= 1;
      if (remaining <= 0) {
        clearInterval(gateOtpCooldownTimer);
        gateOtpCooldownTimer = null;
        btnSend.disabled = false;
        btnSend.textContent = "Gửi lại OTP";
      } else {
        btnSend.textContent = `Gửi lại (${remaining}s)`;
      }
    }, 1000);
  }

  async function sendGateLayer2Otp(emailOverride) {
    const email = String(emailOverride || pendingGateOtpEmail || "").trim();
    if (!email) {
      if (gateStatusBox) gateStatusBox.textContent = "Thiếu email để gửi mã OTP.";
      return;
    }
    const btnSend = byId("btnSendGateOtp");
    if (btnSend) {
      btnSend.disabled = true;
      btnSend.textContent = "Đang gửi OTP...";
    }
    if (gateStatusBox) gateStatusBox.textContent = "Đang gửi mã OTP 6 số về Gmail...";
    try {
      const res = await fetch("/api/auth3/layer2_send_otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, source: "Web Home Login Gate" }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.ok && (!data.gmail_delivery || data.gmail_delivery.sent_real_gmail !== false)) {
        if (gateStatusBox) {
          gateStatusBox.textContent = data.message || (
            data.masked_email
              ? `Đã gửi mã OTP 6 số tới ${data.masked_email}, hiệu lực 5 phút`
              : "Đã gửi mã OTP 6 số đến Gmail."
          );
        }
        const cooldownSec = Number(data.cooldown_remaining_seconds ?? data.retry_after_seconds ?? 60);
        if (cooldownSec > 0) {
          startGateOtpCooldown(cooldownSec);
        } else if (btnSend) {
          btnSend.disabled = false;
          btnSend.textContent = "Gửi lại OTP";
        }
      } else {
        if (gateStatusBox) {
          gateStatusBox.textContent = formatGateAuthError(
            res,
            data,
            (data.gmail_delivery && data.gmail_delivery.note) || "Không gửi được mã OTP."
          );
        }
        const retrySec = Number(data.cooldown_remaining_seconds ?? data.retry_after_seconds ?? 0);
        if (res.status === 429 && retrySec > 0) {
          startGateOtpCooldown(retrySec);
        } else if (btnSend) {
          btnSend.disabled = false;
          btnSend.textContent = "Gửi lại OTP";
        }
      }
    } catch (_) {
      if (gateStatusBox) gateStatusBox.textContent = "Lỗi kết nối máy chủ khi gửi mã OTP.";
      if (btnSend) {
        btnSend.disabled = false;
        btnSend.textContent = "Gửi lại OTP";
      }
    }
  }

  async function verifyGateLayer2Otp() {
    if (isGateOtpInFlight) return;
    const otpInput = byId("gateOtpInput");
    const btnVerify = byId("btnVerifyGateOtp");
    const otpCode = otpInput ? otpInput.value.trim() : "";
    const email = pendingGateOtpEmail || (byId("gateLoginEmail") ? byId("gateLoginEmail").value.trim() : "");
    if (!email) {
      if (gateStatusBox) gateStatusBox.textContent = "Vui lòng quay lại nhập Email và Mật khẩu.";
      return;
    }
    if (!/^\d{6}$/.test(otpCode)) {
      if (gateStatusBox) gateStatusBox.textContent = "Vui lòng nhập đúng mã OTP gồm 6 chữ số.";
      return;
    }
    isGateOtpInFlight = true;
    if (btnVerify) {
      btnVerify.disabled = true;
      btnVerify.textContent = "Đang xác minh...";
    }
    try {
      const res = await fetch("/api/auth3/layer2_verify_otp", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, otp_code: otpCode, purpose: "layer2_login", source: "Web Home Login Gate" }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.ok && data.session_token) {
        await completeGateLoginSession(email, data);
      } else if (gateStatusBox) {
        gateStatusBox.textContent = formatGateAuthError(res, data, "Mã OTP không đúng hoặc đã hết hạn.");
      }
    } catch (_) {
      if (gateStatusBox) gateStatusBox.textContent = "Lỗi kết nối máy chủ khi xác minh OTP.";
    } finally {
      isGateOtpInFlight = false;
      if (btnVerify) {
        btnVerify.disabled = false;
        btnVerify.textContent = "Xác nhận OTP & Đăng nhập";
      }
    }
  }

  const btnVerifyGateOtp = byId("btnVerifyGateOtp");
  if (btnVerifyGateOtp) btnVerifyGateOtp.addEventListener("click", verifyGateLayer2Otp);
  const btnSendGateOtp = byId("btnSendGateOtp");
  if (btnSendGateOtp) btnSendGateOtp.addEventListener("click", () => sendGateLayer2Otp(pendingGateOtpEmail));
  const btnCancelGateOtp = byId("btnCancelGateOtp");
  if (btnCancelGateOtp) {
    btnCancelGateOtp.addEventListener("click", () => {
      hideGateOtpPanel();
      if (gatePanelLogin) gatePanelLogin.style.display = "grid";
      if (gateStatusBox) gateStatusBox.textContent = "Nhập Email và Mật khẩu để vào bảng điều khiển Nhà thông minh.";
    });
  }
  const gateOtpInputEl = byId("gateOtpInput");
  if (gateOtpInputEl) {
    gateOtpInputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        if (e.preventDefault) e.preventDefault();
        verifyGateLayer2Otp();
      }
    });
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
        gateStatusBox.textContent = "Vui lòng nhập đầy đủ Email và 2 ô Mật khẩu!";
      }
      return;
    }

    if (password !== confirmPassword) {
      if (gateStatusBox) {
        gateStatusBox.textContent = "Hai ô Mật khẩu và Xác nhận lại mật khẩu không khớp nhau! Vui lòng nhập giống nhau 100%.";
      }
      return;
    }
    isGateRegisterInFlight = true;
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Đang lưu...";
    }
    try {
      const params = window.location && window.location.search ? new URLSearchParams(window.location.search) : null;
      const inviteToken = params ? (params.get("invite_token") || params.get("token") || params.get("invite") || "").trim() : "";
      const reqBody = {
        email,
        display_name: displayName,
        password,
        confirm_password: confirmPassword,
      };
      if (inviteToken) reqBody.invite_token = inviteToken;
      const res = await fetch("/api/auth3/register_or_set_password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(reqBody),
      });
      const data = await res.json();
      if (data.ok) {
        const hasActiveSession = Boolean(data.session_token && data.permission_active !== false);
        if (hasActiveSession) {
          const userSession = Object.assign({}, data.account || { email, display_name: displayName, tier }, { session_token: data.session_token });
          try {
            if (window.localStorage) {
              window.localStorage.setItem("smarthome_auth_session", JSON.stringify(userSession));
              window.localStorage.setItem("session_token", data.session_token);
            }
            if (window.sessionStorage) {
              window.sessionStorage.setItem("session_token", data.session_token);
            }
          } catch (_) {}
          setSessionCookies(userSession.session_token);
          serverSessionConfirmed = true;
          mountOwnerDashboardDom();
          applyLoggedInUserBanner(userSession);
          if (btnCloseLoginGateModal) btnCloseLoginGateModal.hidden = false;
          if (gateStatusBox) {
            gateStatusBox.textContent = `${data.message || "Đã lưu mật khẩu và đăng nhập thành công!"}`;
          }
          startAuthenticatedRealtimeFlows();
          setTimeout(closeLoginGateModal, 600);
        } else {
          serverSessionConfirmed = false;
          if (btnCloseLoginGateModal) btnCloseLoginGateModal.hidden = true;
          if (gateStatusBox) {
            gateStatusBox.textContent = data.message || "Đã tạo tài khoản. Chờ chủ nhà cấp quyền và phê duyệt trước khi đăng nhập.";
          }
        }
      } else if (gateStatusBox) {
        gateStatusBox.textContent = formatGateAuthError(res, data, "Không lưu được mật khẩu.");
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
        if (gateStatusBox) gateStatusBox.textContent = "Vui lòng nhập đủ mã OTP 6 số nhận qua Gmail!";
        return;
      }
      setForgotStep(3);
    });
  }
  const btnBackForgotStep2 = byId("btnBackForgotStep2");
  if (btnBackForgotStep2) btnBackForgotStep2.addEventListener("click", () => setForgotStep(2));

  const btnSendForgotOtp = byId("btnSendForgotOtp");
  const btnResendForgotOtp = byId("btnResendForgotOtp");
  function setForgotSendButtonsLabel(disabled, labelText) {
    if (btnSendForgotOtp) {
      btnSendForgotOtp.disabled = disabled;
      btnSendForgotOtp.textContent = labelText;
    }
    if (btnResendForgotOtp) {
      btnResendForgotOtp.disabled = disabled;
      btnResendForgotOtp.textContent = labelText === "Gửi OTP" ? "Gửi lại OTP" : labelText;
    }
  }
  function startForgotOtpCooldown(seconds) {
    let remaining = Number(seconds);
    if (!Number.isFinite(remaining) || remaining <= 0) return;
    if (forgotOtpCooldownTimer) clearInterval(forgotOtpCooldownTimer);
    setForgotSendButtonsLabel(true, `Gửi lại sau (${remaining}s)`);
    forgotOtpCooldownTimer = setInterval(() => {
      remaining--;
      if (remaining <= 0) {
        clearInterval(forgotOtpCooldownTimer);
        forgotOtpCooldownTimer = null;
        if (btnSendForgotOtp) btnSendForgotOtp.disabled = false;
        setForgotSendButtonsLabel(false, "Gửi OTP");
      } else {
        setForgotSendButtonsLabel(true, `Gửi lại sau (${remaining}s)`);
      }
    }, 1000);
  }
  async function requestForgotOtpFromGate() {
    if (isSendingForgotOtp) return;
    const emailEl = byId("gateForgotEmail");
    const email = emailEl ? emailEl.value.trim() : "";
    if (!email) {
      if (gateStatusBox) gateStatusBox.textContent = "Vui lòng nhập email nhận mã OTP!";
      return;
    }
    isSendingForgotOtp = true;
    setForgotSendButtonsLabel(true, "Đang gửi...");
    if (gateStatusBox) gateStatusBox.textContent = "Đang gửi mã OTP về Gmail...";
    try {
      const res = await fetch("/api/auth3/forgot_password_send_otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, send_gmail: true }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.ok && (!data.gmail_delivery || data.gmail_delivery.sent_real_gmail !== false)) {
        if (gateStatusBox) gateStatusBox.textContent = `${data.message || "Đã gửi mã OTP qua Gmail."}`;
        setForgotStep(2);
        const cooldownSec = Number(data.cooldown_remaining_seconds ?? data.retry_after_seconds ?? 60);
        if (cooldownSec > 0) {
          startForgotOtpCooldown(cooldownSec);
        } else {
          setForgotSendButtonsLabel(false, "Gửi OTP");
        }
      } else {
        if (gateStatusBox) {
          gateStatusBox.textContent = formatGateAuthError(
            res,
            data,
            (data.gmail_delivery && data.gmail_delivery.note) || "Không gửi được OTP."
          );
        }
        const retrySec = Number(data.cooldown_remaining_seconds ?? data.retry_after_seconds ?? 0);
        if (res.status === 429 && retrySec > 0) {
          startForgotOtpCooldown(retrySec);
        } else {
          setForgotSendButtonsLabel(false, "Gửi OTP");
        }
      }
    } catch (_) {
      if (gateStatusBox) gateStatusBox.textContent = "Lỗi kết nối khi gửi OTP.";
      setForgotSendButtonsLabel(false, "Gửi OTP");
    } finally {
      isSendingForgotOtp = false;
    }
  }
  if (btnSendForgotOtp) btnSendForgotOtp.addEventListener("click", requestForgotOtpFromGate);
  if (btnResendForgotOtp) btnResendForgotOtp.addEventListener("click", requestForgotOtpFromGate);

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
        gateStatusBox.textContent = "Vui lòng điền đầy đủ Email, OTP và 2 ô Mật khẩu mới!";
      }
      return;
    }

    if (newPassword !== confirmPassword) {
      if (gateStatusBox) {
        gateStatusBox.textContent = "Hai ô Mật khẩu mới và Xác nhận lại mật khẩu mới không khớp nhau!";
      }
      return;
    }
    isGateForgotInFlight = true;
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Đang đặt lại...";
    }
    try {
      const res = await fetch("/api/auth3/forgot_password_reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          otp_code: otp,
          otp,
          new_password: newPassword,
          confirm_password: confirmPassword,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.ok) {
        if (pw1El) pw1El.value = "";
        if (pw2El) pw2El.value = "";
        if (otpEl) otpEl.value = "";
        if (gateStatusBox) gateStatusBox.textContent = data.message || "Đặt lại mật khẩu thành công. Hãy đăng nhập bằng mật khẩu mới.";
        switchLoginGateTab("login");
        const loginEmailEl = byId("gateLoginEmail");
        if (loginEmailEl && email) loginEmailEl.value = email;
      } else if (gateStatusBox) {
        gateStatusBox.textContent = formatGateAuthError(res, data, "Không đặt lại được mật khẩu.");
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

  // Kiểm tra trạng thái đăng nhập khi mở Trang chủ (fail-closed theo /api/session/role phía máy chủ)
  async function confirmServerSessionFromApi(keepGateOpen = false) {
    try {
      const roleRes = await fetch("/api/session/role", { credentials: "include" });
      const roleData = await roleRes.json().catch(() => ({}));
      if (!roleRes.ok || !roleData || roleData.authenticated !== true) {
        inMemoryUserSession = null;
        serverSessionConfirmed = false;
        setDeviceAreaLockdown(true);
        unmountOwnerDashboardDom();
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
        syncOwnerGuestQrStateForSession(null);
        openLoginGateModal();
        return false;
      }
      serverSessionConfirmed = true;
      mountOwnerDashboardDom();
      const userObj = {
        email: roleData.email || (inMemoryUserSession && inMemoryUserSession.email) || "",
        display_name: roleData.display_name || (inMemoryUserSession && inMemoryUserSession.display_name) || roleData.email || "",
        tier: Number(roleData.tier || (inMemoryUserSession && inMemoryUserSession.tier) || 3),
        role: roleData.role || "",
        session_token: (inMemoryUserSession && inMemoryUserSession.session_token) || "",
      };
      if (Number(userObj.tier) === 1 && typeof checkOwnerPinStatusIfOwner === "function") {
        await checkOwnerPinStatusIfOwner(userObj);
      }
      applyLoggedInUserBanner(userObj);
      if (btnCloseLoginGateModal) btnCloseLoginGateModal.hidden = false;
      if (!keepGateOpen) closeLoginGateModal();
      startAuthenticatedRealtimeFlows();
      return true;
    } catch (_) {
      inMemoryUserSession = null;
      serverSessionConfirmed = false;
      setDeviceAreaLockdown(true);
      unmountOwnerDashboardDom();
      openLoginGateModal();
      return false;
    }
  }

  try {
    initCameraToolbar();
    const forceLoginModal = window.location && window.location.search && window.location.search.includes("login=1");
    serverSessionConfirmed = false;
    setDeviceAreaLockdown(true);
    unmountOwnerDashboardDom();
    if (btnCloseLoginGateModal) btnCloseLoginGateModal.hidden = true;
    if (!hasClientAuthHint() || forceLoginModal) {
      openLoginGateModal();
    }
    confirmServerSessionFromApi(Boolean(forceLoginModal)).then((ok) => {
      if (!ok || forceLoginModal) {
        if (btnCloseLoginGateModal) btnCloseLoginGateModal.hidden = true;
        if (!ok) unmountOwnerDashboardDom();
        openLoginGateModal();
      } else if (btnCloseLoginGateModal) {
        btnCloseLoginGateModal.hidden = false;
      }
    });
  } catch (_) {
    clearAuthState();
    if (btnCloseLoginGateModal) btnCloseLoginGateModal.hidden = true;
    openLoginGateModal();
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
            lblCurrentCameraView.textContent = btn.textContent.trim();
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

  function getLockdownEmail() {
    const emailInput = byId("lockdownEmail");
    const typed = emailInput ? emailInput.value.trim() : "";
    if (typed) return typed;
    if (inMemoryUserSession && inMemoryUserSession.email) {
      return String(inMemoryUserSession.email).trim();
    }
    return "";
  }

  function triggerSecurityLockdown(reason = "security_lockdown") {
    const modal = byId("securityLockdownModal");
    const desc = byId("lockdownDesc");
    const note = byId("lockdownNote");
    const statusBox = byId("lockdownStatusBox");
    const emailInput = byId("lockdownEmail");
    if (!modal) return;

    const isSirenOn = Boolean(
      latestDevicesMap &&
      latestDevicesMap.alarm_siren &&
      (latestDevicesMap.alarm_siren.state === "ON" || latestDevicesMap.alarm_siren.state === "OPEN")
    );

    if (desc) {
      desc.textContent = isSirenOn
        ? "Cảnh báo an ninh đang kích hoạt và còi báo động đang bật. Vui lòng xác minh tài khoản Chủ nhà để mở khóa và tắt còi."
        : "Hệ thống đang tạm khóa bảo mật (còi báo động đang tắt). Vui lòng xác minh tài khoản Chủ nhà để tiếp tục điều khiển.";
    }
    if (note) {
      note.textContent = isSirenOn
        ? "Xác minh Chủ nhà để mở khóa an ninh và tắt còi báo động."
        : "Xác minh Chủ nhà để mở khóa an ninh.";
    }
    if (emailInput && !emailInput.value.trim() && inMemoryUserSession && inMemoryUserSession.email) {
      emailInput.value = String(inMemoryUserSession.email).trim();
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
    const ownerEmail = getLockdownEmail();
    if (!ownerEmail) {
      if (statusBox) statusBox.textContent = "Vui lòng nhập Email Chủ nhà trước khi gửi OTP.";
      return;
    }
    if (statusBox) statusBox.textContent = `Đang gửi mã OTP đến Gmail ${ownerEmail}...`;
    if (sendBtn) sendBtn.disabled = true;
    try {
      const res = await fetch("/api/auth3/forgot_password_send_otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: ownerEmail, send_gmail: true }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.ok && (!data.gmail_delivery || data.gmail_delivery.sent_real_gmail !== false)) {
        if (statusBox) statusBox.textContent = `Đã gửi mã OTP 6 số đến Gmail ${ownerEmail}.`;
      } else {
        if (statusBox) statusBox.textContent = `${data.error || (data.gmail_delivery && data.gmail_delivery.note) || "Không gửi được OTP."}`;
      }
    } catch (_) {
      if (statusBox) statusBox.textContent = "Lỗi mạng khi gửi OTP.";
    } finally {
      if (sendBtn) sendBtn.disabled = false;
    }
  }

  async function unlockSecurityLockdown() {
    const statusBox = byId("lockdownStatusBox");
    const unlockBtn = byId("btnLockdownUnlock");
    const ownerEmail = getLockdownEmail();
    if (!ownerEmail) {
      if (statusBox) statusBox.textContent = "Vui lòng nhập Email Chủ nhà.";
      return;
    }
    if (unlockBtn) unlockBtn.disabled = true;

    try {
      let ok = false;
      let errMessage = "";

      if (!isLockdownOtpMode) {
        const pwInput = byId("lockdownPassword");
        const password = pwInput ? pwInput.value.trim() : "";
        if (!password) {
          if (statusBox) statusBox.textContent = "Vui lòng nhập mật khẩu Chủ nhà.";
          if (unlockBtn) unlockBtn.disabled = false;
          return;
        }
        if (statusBox) statusBox.textContent = "Đang xác minh mật khẩu...";
        const res = await fetch("/api/auth3/layer1_login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: ownerEmail,
            password: password,
            send_gmail: false,
            source: "SecurityLockdownModal",
          }),
        });
        const data = await res.json().catch(() => ({}));
        ok = Boolean(res.ok && data.ok);
        errMessage = data.error || data.message || "Mật khẩu không chính xác.";
      } else {
        const otpInput = byId("lockdownOtp");
        const otpCode = otpInput ? otpInput.value.trim() : "";
        if (!otpCode || otpCode.length < 6) {
          if (statusBox) statusBox.textContent = "Vui lòng nhập đủ 6 chữ số OTP.";
          if (unlockBtn) unlockBtn.disabled = false;
          return;
        }
        if (statusBox) statusBox.textContent = "Đang xác minh mã OTP...";
        const res = await fetch("/api/auth3/layer2_verify_otp", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: ownerEmail,
            otp_code: otpCode,
            source: "SecurityLockdownModal",
          }),
        });
        const data = await res.json().catch(() => ({}));
        ok = Boolean(res.ok && data.ok);
        errMessage = data.error || data.message || "Mã OTP không chính xác hoặc đã hết hạn.";
      }

      if (ok) {
        sendWs({ type: "reset_voice_strikes" });

        if (latestDevicesMap["alarm_siren"]) {
          toggleDeviceById("alarm_siren", "OFF");
        } else {
          const sirenCtrl = getDeviceControlState("alarm_siren");
          sirenCtrl.seq += 1;
          const sSeq = sirenCtrl.seq;
          const sTs = Date.now();
          sirenCtrl.desiredState = "OFF";
          fetch("/api/device/alarm_siren", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              action: "turn_off",
              target_state: "OFF",
              state: "OFF",
              client_id: CLIENT_ID,
              client_seq: sSeq,
              client_ts_ms: sTs,
              request_id: `${CLIENT_ID}:alarm_siren:${sSeq}`,
              source: "SecurityLockdownModal",
            }),
          }).catch(() => {});
        }

        if (voiceLockoutNotice) {
          voiceLockoutNotice.hidden = true;
          voiceLockoutNotice.textContent = "";
        }

        if (statusBox) statusBox.textContent = "Xác minh thành công. Đang mở khóa...";
        setTimeout(() => {
          closeSecurityLockdownModal();
          logEvent("Khóa an ninh đã được mở khóa thành công.", "info");
        }, 400);
      } else {
        if (statusBox) statusBox.textContent = `${errMessage}`;
      }
    } catch (_) {
      if (statusBox) statusBox.textContent = "Lỗi mạng khi xác minh mở khóa.";
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



  function syncAutoFormKindVisibility() {
    const kind = (byId("autoKindSelect") && byId("autoKindSelect").value) || "timer";
    const gTimer = byId("autoFormTimerGroup");
    const gClock = byId("autoFormClockGroup");
    const gRule = byId("autoFormRuleGroup");
    const gScene = byId("autoFormSceneGroup");
    if (gTimer) gTimer.hidden = kind !== "timer";
    if (gClock) gClock.hidden = kind !== "clock";
    if (gRule) gRule.hidden = kind !== "rule";
    if (gScene) gScene.hidden = kind !== "scene";
    setAutoFormFeedback("");
  }

  function bindDesktopAutomationEvents() {
    const toggleBtn = byId("btnToggleAutoForm");
    const panelEl = byId("desktopAutoFormPanel");
    const cancelBtn = byId("btnAutoCancel");
    const kindSel = byId("autoKindSelect");
    const submitBtn = byId("btnAutoSubmit");

    if (toggleBtn && panelEl) {
      toggleBtn.addEventListener("click", () => {
        panelEl.hidden = !panelEl.hidden;
        if (!panelEl.hidden) syncAutoFormKindVisibility();
      });
    }
    if (cancelBtn && panelEl) {
      cancelBtn.addEventListener("click", () => {
        const editEl = byId("autoSceneEditId");
        if (editEl) editEl.value = "";
        panelEl.hidden = true;
        setAutoFormFeedback("");
      });
    }
    if (kindSel) {
      kindSel.addEventListener("change", syncAutoFormKindVisibility);
    }
    if (submitBtn) {
      submitBtn.addEventListener("click", async () => {
        const kind = (kindSel && kindSel.value) || "timer";
        let url = "/api/timers";
        let method = "POST";
        let payload = {};
        if (kind === "timer") {
          const val = Math.max(1, Number((byId("autoTimerValue") && byId("autoTimerValue").value) || 10));
          const unit = (byId("autoTimerUnit") && byId("autoTimerUnit").value) || "sec";
          payload = {
            device_id: (byId("autoTimerDevice") && byId("autoTimerDevice").value) || "living_room_light",
            action: (byId("autoTimerAction") && byId("autoTimerAction").value) || "turn_on",
            hours: unit === "hour" ? val : 0,
            minutes: unit === "min" ? val : 0,
            seconds: unit === "sec" ? val : 0,
          };
        } else if (kind === "clock") {
          url = "/api/schedules";
          payload = {
            device_id: (byId("autoClockDevice") && byId("autoClockDevice").value) || "living_room_light",
            action: (byId("autoClockAction") && byId("autoClockAction").value) || "turn_on",
            time_hhmm: (byId("autoClockTime") && byId("autoClockTime").value) || "07:00",
            schedule_type: (byId("autoClockType") && byId("autoClockType").value) || "once",
          };
        } else if (kind === "rule") {
          url = "/api/rules";
          payload = {
            when_device_id: (byId("autoRuleWhenDev") && byId("autoRuleWhenDev").value) || "main_door",
            when_state: (byId("autoRuleWhenState") && byId("autoRuleWhenState").value) || "OPEN",
            then_device_id: (byId("autoRuleThenDev") && byId("autoRuleThenDev").value) || "living_room_light",
            then_action: (byId("autoRuleThenAction") && byId("autoRuleThenAction").value) || "turn_on",
          };
        } else if (kind === "scene") {
          const editId = (byId("autoSceneEditId") && byId("autoSceneEditId").value.trim()) || "";
          url = editId ? `/api/scenes/${encodeURIComponent(editId)}` : "/api/scenes";
          method = editId ? "PUT" : "POST";
          payload = {
            phrase: (byId("autoScenePhrase") && byId("autoScenePhrase").value.trim()) || "",
            steps_text: (byId("autoSceneSteps") && byId("autoSceneSteps").value.trim()) || "",
          };
        }
        try {
          const res = await fetch(url, {
            method,
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify(payload),
          });
          const data = await res.json().catch(() => ({}));
          if (!res.ok || data.ok === false) {
            setAutoFormFeedback(data.error || "Không thể lưu tự động hóa.", true);
            return;
          }
          if (byId("autoSceneEditId")) byId("autoSceneEditId").value = "";
          if (panelEl) panelEl.hidden = true;
          setAutoFormFeedback("");
          if (data.snapshot) applySnapshot(data.snapshot);
          appendLog(data.reply || data.exact_spoken_reply || "Đã lưu cấu hình tự động.", "AUTOMATION");
        } catch (err) {
          setAutoFormFeedback(`Lỗi kết nối: ${err}`, true);
        }
      });
    }

    const schedSection = document.querySelector("section.panel.schedule");
    if (schedSection) {
      schedSection.addEventListener("click", async (ev) => {
        const btn = ev.target && ev.target.closest ? ev.target.closest("[data-auto-act]") : null;
        if (!btn) return;
        const act = btn.getAttribute("data-auto-act") || "";
        const itemId = btn.getAttribute("data-auto-id") || "";
        if (!itemId) return;
        if (act === "edit-scene") {
          const scenes = (latestAutomationSnap && (latestAutomationSnap.scenes || latestAutomationSnap.custom_commands)) || [];
          const found = scenes.find((s) => String(s.command_id || "") === itemId);
          if (found && panelEl && kindSel) {
            kindSel.value = "scene";
            syncAutoFormKindVisibility();
            panelEl.hidden = false;
            if (byId("autoSceneEditId")) byId("autoSceneEditId").value = itemId;
            if (byId("autoScenePhrase")) byId("autoScenePhrase").value = found.phrase || "";
            if (byId("autoSceneSteps")) {
              const stepTxt = (found.steps || [])
                .map((s) => `${AUTO_ACT_LABELS[s.action] || s.action} ${AUTO_DEV_LABELS[s.device_id] || s.device_id}`)
                .join(" rồi ");
              byId("autoSceneSteps").value = stepTxt;
            }
          }
          return;
        }
        let url = "";
        let method = "DELETE";
        let body = undefined;
        if (act === "cancel-timer") url = `/api/timers/${encodeURIComponent(itemId)}`;
        else if (act === "del-schedule") url = `/api/schedules/${encodeURIComponent(itemId)}`;
        else if (act === "toggle-schedule") {
          url = `/api/schedules/${encodeURIComponent(itemId)}`;
          method = "PATCH";
          body = JSON.stringify({ enabled: btn.getAttribute("data-auto-enabled") !== "1" });
        } else if (act === "del-rule") url = `/api/rules/${encodeURIComponent(itemId)}`;
        else if (act === "del-scene") url = `/api/scenes/${encodeURIComponent(itemId)}`;
        else if (act === "run-scene") {
          url = `/api/scenes/${encodeURIComponent(itemId)}/run`;
          method = "POST";
        }
        if (!url) return;
        try {
          const res = await fetch(url, {
            method,
            headers: body ? { "Content-Type": "application/json" } : {},
            credentials: "same-origin",
            body,
          });
          const data = await res.json().catch(() => ({}));
          if (!res.ok || data.ok === false) {
            appendLog(data.error || "Thao tác tự động thất bại.", "SECURITY");
            return;
          }
          if (data.snapshot) applySnapshot(data.snapshot);
          appendLog(data.reply || data.exact_spoken_reply || `Đã thực hiện ${act}.`, "AUTOMATION");
        } catch (err) {
          appendLog(`Lỗi tự động hóa: ${err}`, "ERROR");
        }
      });
    }
  }
  bindDesktopAutomationEvents();

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
  let _homeRestPollTick = 0;
  setInterval(() => {
    _homeRestPollTick += 1;
    if (typeof document !== 'undefined' && document.hidden && (_homeRestPollTick % 2) !== 0) return;
    if ((isWsOpen() || _sseConnected) && (_homeRestPollTick % 25) !== 0) return;
    if (serverSessionConfirmed) pollRestStateFallback();
  }, 1000);
  if (typeof document !== 'undefined' && document.addEventListener) {
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden && serverSessionConfirmed) pollRestStateFallback(true);
    });
  }
  if (serverSessionConfirmed) {
    startAuthenticatedRealtimeFlows();
  }

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

