(function () {
  "use strict";

  var DEVICE_LABELS = {
    living_room_light: "Đèn phòng khách",
    bedroom_light: "Đèn phòng ngủ",
    fan: "Quạt",
    ac: "Điều hòa",
    garden_pump: "Máy bơm vườn",
    main_door: "Cửa chính",
    alarm_siren: "Còi báo động"
  };
  var DEVICE_MIN_TIERS = {
    main_door: 1,
    alarm_siren: 1,
    ac: 2,
    garden_pump: 2,
    living_room_light: 3,
    bedroom_light: 3,
    fan: 3
  };
  var TOGGLE_ON = { main_door: "open", alarm_siren: "on", ac: "on", garden_pump: "on", living_room_light: "on", bedroom_light: "on", fan: "on" };
  var TOGGLE_OFF = { main_door: "close", alarm_siren: "off", ac: "off", garden_pump: "off", living_room_light: "off", bedroom_light: "off", fan: "off" };

  var sessionToken = "";
  var sessionTier = 99;
  var snapshot = {};
  var recognizing = false;
  var recognition = null;

  function $(id) { return document.getElementById(id); }
  function tokenFromUrl() {
    var params = new URLSearchParams(window.location.search);
    return (params.get("token") || params.get("invite") || "").trim();
  }
  function showInvalid() {
    $("guestApp").hidden = true;
    $("guestInvalid").hidden = false;
  }
  function setMsg(text, kind) {
    var el = $("guestMsg");
    el.textContent = text || "";
    el.className = "guest-msg" + (kind ? " " + kind : "");
  }
  function allowedDevices(tier) {
    return Object.keys(DEVICE_MIN_TIERS).filter(function (id) {
      return Number(tier) <= Number(DEVICE_MIN_TIERS[id]);
    });
  }
  function authHeaders() {
    var h = { "Content-Type": "application/json" };
    if (sessionToken) {
      h["Authorization"] = "Bearer " + sessionToken;
      h["x-session-token"] = sessionToken;
    }
    return h;
  }
  function deviceState(id) {
    var devices = (snapshot && snapshot.devices) || snapshot || {};
    var rec = devices[id] || {};
    return rec.state || rec.status || rec.power || rec.value || "";
  }
  function renderDevices() {
    var grid = $("guestDeviceGrid");
    grid.innerHTML = "";
    allowedDevices(sessionTier).forEach(function (id) {
      var card = document.createElement("article");
      card.className = "device-card";
      card.setAttribute("data-device-id", id);
      var state = String(deviceState(id) || "—");
      card.innerHTML = "<h2>" + (DEVICE_LABELS[id] || id) + "</h2><div class=\"state\">Trạng thái: " + state + "</div>";
      var btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = "Bật / Tắt";
      btn.addEventListener("click", function () { toggleDevice(id, state); });
      card.appendChild(btn);
      grid.appendChild(card);
    });
  }
  async function toggleDevice(id, current) {
    var lowered = String(current || "").toLowerCase();
    var action = (lowered === "on" || lowered === "open" || lowered === "true") ? (TOGGLE_OFF[id] || "off") : (TOGGLE_ON[id] || "on");
    try {
      var res = await fetch("/api/device", {
        method: "POST",
        headers: authHeaders(),
        credentials: "include",
        body: JSON.stringify({ device_id: id, action: action, source: "guest_web" })
      });
      var data = await res.json().catch(function () { return {}; });
      if (data && data.snapshot) snapshot = data.snapshot;
      if (!res.ok || data.ok === false) {
        setMsg(data.error || data.exact_spoken_reply || "Không thực hiện được lệnh này.", "error");
      } else {
        setMsg("Đã gửi lệnh " + (DEVICE_LABELS[id] || id) + ".", "ok");
      }
      renderDevices();
    } catch (err) {
      setMsg("Không gửi được lệnh.", "error");
    }
  }
  async function sendVoiceCommand(transcript) {
    var text = String(transcript || "").trim();
    if (!text) {
      $("guestVoiceStatus").textContent = "Không nhận được lời nói — im lặng, không hỏi nói lại.";
      return;
    }
    try {
      var res = await fetch("/api/voice_command", {
        method: "POST",
        headers: authHeaders(),
        credentials: "include",
        body: JSON.stringify({ transcript: text, source: "guest_web_voice" })
      });
      var data = await res.json().catch(function () { return {}; });
      if (data && data.snapshot) snapshot = data.snapshot;
      if (data && data.ask_repeat) {
        /* Máy chủ không được phép phát vòng nhắc nói lại. */
      }
      if (!res.ok || data.ok === false) {
        setMsg(data.error || data.reply_text || "Lệnh không được phép hoặc không hiểu.", "error");
      } else {
        setMsg(data.reply_text || data.exact_spoken_reply || ("Đã thực hiện: " + text), "ok");
      }
      renderDevices();
    } catch (err) {
      setMsg("Không gửi được lệnh giọng nói.", "error");
    }
  }
  function startVoice() {
    var SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRec) {
      setMsg("Trình duyệt không hỗ trợ nhận giọng nói. Hãy dùng nút bấm.", "error");
      return;
    }
    if (recognizing) {
      try { recognition && recognition.stop(); } catch (e) {}
      recognizing = false;
      $("guestVoiceStatus").textContent = "Đã dừng nghe.";
      return;
    }
    recognition = new SpeechRec();
    recognition.lang = "vi-VN";
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.onresult = function (ev) {
      var text = "";
      if (ev.results && ev.results[0] && ev.results[0][0]) text = ev.results[0][0].transcript || "";
      sendVoiceCommand(text);
    };
    recognition.onerror = function () {
      recognizing = false;
      $("guestVoiceStatus").textContent = "Không nhận được lời nói — không hỏi nói lại.";
    };
    recognition.onend = function () { recognizing = false; };
    recognizing = true;
    $("guestVoiceStatus").textContent = "Đang nghe…";
    recognition.start();
  }
  async function boot() {
    var token = tokenFromUrl();
    if (!token) {
      showInvalid();
      return;
    }
    try {
      var res = await fetch("/api/guest/redeem", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ token: token })
      });
      var data = await res.json().catch(function () { return {}; });
      if (!res.ok || !data.ok) {
        showInvalid();
        return;
      }
      sessionToken = data.session_token || "";
      sessionTier = Number(data.tier || 99);
      $("guestInvalid").hidden = true;
      $("guestApp").hidden = false;
      $("guestTierBadge").textContent = "Cấp " + sessionTier + " · " + (data.display_name || "Khách");
      try {
        var st = await fetch("/api/state", { headers: authHeaders(), credentials: "include" });
        if (st.ok) snapshot = await st.json();
      } catch (e) {}
      renderDevices();
      $("guestMicBtn").addEventListener("click", startVoice);
    } catch (err) {
      showInvalid();
    }
  }
  boot();
})();
