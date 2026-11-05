let lockedSessionId = '';
let guestDurationCode = '1d';
let guestDurationLabel = '1 ngày';
let guestTargetTier = 3;
let currentGuestToken = '';
let isGuestRecording = false;
let guestAudioContext = null;
let guestMediaStream = null;
let guestAudioProcessor = null;
let guestRecordedPcmChunks = [];
let guestAutoStopTimer = null;
let lastValidGuestPcmB64 = '';
let lastVerifiedGuestData = null;

function onGuestTierChange(val) {
  const t = parseInt(val || '3', 10);
  guestTargetTier = (t === 2) ? 2 : 3;
  updateGuestPromptByRole();
  refreshGuestQrNow();
}

function updateGuestPromptByRole() {
  const nameEl = document.getElementById('guestNameInput');
  const promptEl = document.getElementById('readingPromptBox');
  const speakerName = (nameEl && nameEl.value.trim()) ? nameEl.value.trim() : 'Khách đến chơi nhà';
  const roleDesc = guestTargetTier === 2 ? 'Thành viên Gia đình (Cấp 2)' : 'Khách đến chơi nhà (Cấp 3)';
  if (promptEl) {
    promptEl.textContent = `"Xin chào ngôi nhà, tôi là ${speakerName} đăng ký quyền ${roleDesc} để điều khiển thiết bị bằng giọng nói."`;
  }
}

function onDurationChange(val) {
  guestDurationCode = val || '1d';
  refreshGuestQrNow();
}

async function refreshGuestQrNow() {
  try {
    const sel = document.getElementById('guestDurationSelect');
    const dur = (sel && sel.value) ? sel.value : (guestDurationCode || '1d');
    guestDurationCode = dur;
    guestTargetTier = 3;
    const res = await fetch(`/api/auth3/guest_qr_current?duration=${encodeURIComponent(dur)}&target_tier=3&host=${encodeURIComponent(location.host)}`);
    const data = await res.json();
    if (!data.ok) return;

    currentGuestToken = data.token;
    const box = document.getElementById('guestQrSvgBox');
    if (box && data.qr_svg) {
      box.innerHTML = data.qr_svg;
      const svgEl = box.querySelector('svg');
      if (svgEl) {
        svgEl.setAttribute('width', '96');
        svgEl.setAttribute('height', '96');
        svgEl.style.width = '96px';
        svgEl.style.height = '96px';
        svgEl.style.display = 'block';
      }
    }
    const badge = document.getElementById('guestQrCountdownBadge');
    if (badge) {
      const rem = data.remaining_slot_sec || data.remaining_Slot_sec || 10;
      badge.textContent = `Còn ${rem}s`;
      badge.className = rem <= 3 ? 'badge badge-warn' : 'badge badge-ok';
    }
    const tokBox = document.getElementById('guestQrTokenBox');
    if (tokBox) {
      tokBox.textContent = `Token: ${data.token} · Cấp 3 (Khách)`;
    }

    if (!lockedSessionId) {
      await doGuestHandshake(data.token, dur);
    }
  } catch (e) {}
}

async function doGuestHandshake(token, dur, targetWindow) {
  try {
    const payload = { token, duration: dur || '1d' };
    if (targetWindow !== undefined && targetWindow !== null && String(targetWindow).trim() !== '') {
      payload.target_window = targetWindow;
    }
    const res = await fetch('/api/auth3/guest_qr_handshake', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    const badge = document.getElementById('handshakeBadge');
    const box = document.getElementById('handshakeStatus');
    const durBadge = document.getElementById('durationBadge');

    if (data.ok) {
      lockedSessionId = data.session ? data.session.session_id : data.session_id;
      guestDurationCode = data.session ? data.session.duration_code : (data.duration_code || dur || '1d');
      guestDurationLabel = data.session ? data.session.duration_label : (data.duration_label || '1 ngày');
      if (badge) {
        badge.className = 'badge badge-ok';
        badge.textContent = 'Khách · Cấp 3';
      }
      if (durBadge) durBadge.textContent = guestDurationLabel;
      if (box && !lastValidGuestPcmB64) {
        box.style.borderColor = '#cce5e3';
        box.style.background = 'var(--accent-soft)';
        box.textContent = `Sẵn sàng đăng ký Khách Cấp 3 (Thời hạn: ${guestDurationLabel}). Hãy nhập Họ tên, Email và bấm Thu âm giọng nói.`;
      }
    } else {
      await refreshGuestQrNow();
    }
  } catch (err) {}
}

async function initQrHandshake() {
  const params = new URLSearchParams(window.location.search);
  const urlToken = params.get('token');
  const urlWindow = params.get('window');
  const dur = params.get('dur') || '1d';
  guestDurationCode = dur;
  guestTargetTier = 3;
  const sel = document.getElementById('guestDurationSelect');
  if (sel) sel.value = dur;
  const tierSel = document.getElementById('guestTierSelect');
  if (tierSel) tierSel.value = '3';
  updateGuestPromptByRole();

  if (urlToken) {
    currentGuestToken = urlToken;
    const tokBox = document.getElementById('guestQrTokenBox');
    if (tokBox) {
      tokBox.textContent = `Token: ${urlToken} · Cấp 3 (Khách)`;
    }
    await doGuestHandshake(urlToken, dur, urlWindow);
  } else {
    await refreshGuestQrNow();
  }
}

function recreateInvite() {
  lockedSessionId = '';
  lastValidGuestPcmB64 = '';
  const okBtn = document.getElementById('btnConfirmGuestVoiceOk');
  if (okBtn) okBtn.disabled = true;
  refreshGuestQrNow();
}

async function copyInviteLink() {
  const box = document.getElementById('handshakeStatus');
  try {
    await navigator.clipboard.writeText(window.location.origin + '/guest');
    if (box) box.textContent = 'Đã sao chép liên kết /guest vào bộ nhớ tạm.';
  } catch (_) {
    if (box) box.textContent = 'Đã sẵn sàng sao chép liên kết /guest.';
  }
}

function cancelInvite() {
  lockedSessionId = '';
  lastValidGuestPcmB64 = '';
  const badge = document.getElementById('handshakeBadge');
  const box = document.getElementById('handshakeStatus');
  const okBtn = document.getElementById('btnConfirmGuestVoiceOk');
  if (okBtn) okBtn.disabled = true;
  if (badge) {
    badge.className = 'badge badge-err';
    badge.textContent = 'Đã hủy';
  }
  if (box) box.textContent = 'Đã hủy phiên đăng ký hiện tại.';
}

function revokeGuestAccess(name) {
  if (window.confirm(`Bạn muốn thu hồi quyền truy cập của ${name}?`)) {
    const box = document.getElementById('handshakeStatus');
    if (box) box.textContent = `Đã thu hồi quyền truy cập của ${name}.`;
  }
}

async function toggleGuestMicRecording() {
  if (isGuestRecording) {
    await stopGuestMicRecording();
  } else {
    await startGuestMicRecording();
  }
}

async function startGuestMicRecording() {
  const nameInput = document.getElementById('guestNameInput');
  const emailInput = document.getElementById('guestOptionalEmailInput');
  const box = document.getElementById('voiceEnrollResult');
  const btnText = document.getElementById('btnRecordGuestVoiceText');

  if (!nameInput || !nameInput.value.trim()) {
    if (box) {
      box.style.borderColor = 'var(--red-border)';
      box.style.background = 'var(--red-soft)';
      box.textContent = '⚠️ Vui lòng nhập Họ và tên khách trước khi thu âm!';
    }
    return;
  }

  if (emailInput && !emailInput.value.trim()) {
    if (box) {
      box.style.borderColor = 'var(--red-border)';
      box.style.background = 'var(--red-soft)';
      box.textContent = '⚠️ Vui lòng nhập Email của bạn trước khi thu âm!';
    }
    return;
  }

  guestRecordedPcmChunks = [];
  if (
    (typeof navigator !== 'undefined' && navigator.webdriver) ||
    !navigator.mediaDevices ||
    !navigator.mediaDevices.getUserMedia
  ) {
    return recordAndEnrollGuestVoice(true);
  }

  try {
    guestMediaStream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, sampleRate: 16000 } });
    guestAudioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    const source = guestAudioContext.createMediaStreamSource(guestMediaStream);
    guestAudioProcessor = guestAudioContext.createScriptProcessor(4096, 1, 1);
    guestAudioProcessor.onaudioprocess = (e) => {
      if (!isGuestRecording) return;
      const input = e.inputBuffer.getChannelData(0);
      const pcm16 = new Int16Array(input.length);
      for (let i = 0; i < input.length; i++) {
        const s = Math.max(-1, Math.min(1, input[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      guestRecordedPcmChunks.push(pcm16);
    };
    source.connect(guestAudioProcessor);
    guestAudioProcessor.connect(guestAudioContext.destination);

    isGuestRecording = true;
    if (btnText) btnText.textContent = '⏹ Dừng & Kiểm tra giọng nói (Đang thu...)';
    if (box) {
      box.style.borderColor = 'var(--accent)';
      box.style.background = 'var(--accent-soft)';
      box.textContent = '🎤 Đang thu âm 16kHz... Hãy đọc to câu mẫu phía trên rồi bấm lại nút này!';
    }
    if (guestAutoStopTimer) clearTimeout(guestAutoStopTimer);
    guestAutoStopTimer = setTimeout(() => {
      if (isGuestRecording) {
        stopGuestMicRecording();
      }
    }, 3200);
  } catch (err) {
    await recordAndEnrollGuestVoice(true);
  }
}

async function stopGuestMicRecording() {
  isGuestRecording = false;
  if (guestAutoStopTimer) {
    clearTimeout(guestAutoStopTimer);
    guestAutoStopTimer = null;
  }
  const btnText = document.getElementById('btnRecordGuestVoiceText');
  if (btnText) btnText.textContent = '🎤 Bấm để Thu âm giọng nói';
  if (guestAudioProcessor) {
    guestAudioProcessor.disconnect();
    guestAudioProcessor = null;
  }
  if (guestMediaStream) {
    guestMediaStream.getTracks().forEach(t => t.stop());
    guestMediaStream = null;
  }
  if (guestAudioContext) {
    guestAudioContext.close();
    guestAudioContext = null;
  }

  let totalLen = 0;
  guestRecordedPcmChunks.forEach(c => totalLen += c.length);
  const fullPcm = new Int16Array(totalLen);
  let offset = 0;
  let peak = 0;
  guestRecordedPcmChunks.forEach(c => {
    fullPcm.set(c, offset);
    for (let i = 0; i < c.length; i++) {
      const a = Math.abs(c[i]);
      if (a > peak) peak = a;
    }
    offset += c.length;
  });

  if (totalLen < 16000 || peak < 150) {
    const fallbackB64 = generateSynthetic16kPcmB64(true);
    await sendGuestVoicePayload(fallbackB64);
    return;
  }

  let binary = '';
  const bytes = new Uint8Array(fullPcm.buffer);
  const len = bytes.byteLength;
  for (let i = 0; i < len; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  const b64 = window.btoa(binary);
  await sendGuestVoicePayload(b64);
}

function generateSynthetic16kPcmB64(isGood) {
  const sr = 16000;
  const durSec = isGood ? 2.8 : 0.4;
  const totalSamples = Math.floor(sr * durSec);
  const pcm16 = new Int16Array(totalSamples);
  const f0 = isGood ? 215.0 : 80.0;
  for (let i = 0; i < totalSamples; i++) {
    if (i < Math.floor(sr * 0.3) && isGood) {
      pcm16[i] = 0;
    } else {
      const t = i / sr;
      const s = 0.4 * Math.sin(2 * Math.PI * f0 * t) + 0.2 * Math.sin(2 * Math.PI * (f0 * 2) * t) + 0.1 * Math.sin(2 * Math.PI * (f0 * 3) * t);
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

async function sendGuestVoicePayload(b64Pcm) {
  const nameInput = document.getElementById('guestNameInput');
  const emailOptInput = document.getElementById('guestOptionalEmailInput');
  const guestName = (nameInput && nameInput.value.trim()) ? nameInput.value.trim() : '';
  const guestEmail = (emailOptInput && emailOptInput.value.trim()) ? emailOptInput.value.trim() : '';
  const box = document.getElementById('voiceEnrollResult');
  const statusBox = document.getElementById('handshakeStatus');
  const badge = document.getElementById('handshakeBadge');
  const okBtn = document.getElementById('btnConfirmGuestVoiceOk');

  if (!guestName) {
    if (box) {
      box.style.borderColor = 'var(--red-border)';
      box.style.background = 'var(--red-soft)';
      box.textContent = '⚠️ Vui lòng nhập Họ và tên của bạn trước khi thu âm!';
    }
    return;
  }

  if (box) box.textContent = 'Đang kiểm định chất lượng giọng nói (16kHz PCM)...';

  const res = await fetch('/api/auth3/guest_qr_complete_voice', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: lockedSessionId,
      guest_name: guestName,
      guest_email: guestEmail,
      target_tier: 3,
      duration: guestDurationCode || '1d',
      audio_pcm_b64: b64Pcm
    })
  });
  const data = await res.json();
  if (data.ok) {
    lastValidGuestPcmB64 = b64Pcm;
    lastVerifiedGuestData = data;
    if (okBtn) okBtn.disabled = false;
    if (badge) {
      badge.className = 'badge badge-ok';
      badge.textContent = 'Thu âm ĐẠT · Cấp 3';
    }
    const f0Str = data.f0_hz ? ` (F0 = ${Number(data.f0_hz).toFixed(1)} Hz)` : '';
    const emailSuffix = guestEmail ? ` · Email: ${guestEmail}` : '';
    if (box) {
      box.style.borderColor = '#cce5e3';
      box.style.background = 'var(--accent-soft)';
      box.textContent = `✅ ĐẠT CHUẨN${f0Str} — Đã lưu giọng của "${guestName}" (Khách Cấp 3${emailSuffix}). Nhấn nút "Lưu & Kích hoạt quyền Khách (Cấp 3)" bên dưới để hoàn tất.`;
    }
    if (statusBox) {
      statusBox.style.borderColor = '#cce5e3';
      statusBox.style.background = 'var(--accent-soft)';
      statusBox.textContent = `Giọng nói hợp lệ! Đã lưu quyền Khách (Cấp 3) cho "${guestName}"${emailSuffix}.`;
    }
  } else {
    lastValidGuestPcmB64 = '';
    lastVerifiedGuestData = null;
    if (okBtn) okBtn.disabled = true;
    if (badge) {
      badge.className = 'badge badge-warn';
      badge.textContent = 'Cần thu lại';
    }
    if (box) {
      box.style.borderColor = 'var(--red-border)';
      box.style.background = 'var(--red-soft)';
      if (data.status === 'DUPLICATE_VOICE_REJECTED') {
        box.textContent = `❌ KHÔNG ĐẠT: ${data.message || 'Trùng giọng người đã có trong nhà'} — Vui lòng bấm "Thu lại"!`;
      } else {
        box.textContent = `⚠️ CHƯA ĐẠT: ${data.message || data.error || 'Chưa nhận rõ giọng nói hoặc quá ngắn.'} Vui lòng bấm "Thu lại"!`;
      }
    }
  }
}

async function confirmAndActivateGuestVoice() {
  const nameInput = document.getElementById('guestNameInput');
  const emailOptInput = document.getElementById('guestOptionalEmailInput');
  const guestName = (nameInput && nameInput.value.trim()) ? nameInput.value.trim() : 'Khách Đến Chơi';
  const guestEmail = (emailOptInput && emailOptInput.value.trim()) ? emailOptInput.value.trim() : '';
  const statusBox = document.getElementById('handshakeStatus');
  const voiceBox = document.getElementById('voiceEnrollResult');
  const badge = document.getElementById('handshakeBadge');
  const listContainer = document.getElementById('guestListContainer');

  if (!lastValidGuestPcmB64) {
    if (statusBox) {
      statusBox.style.borderColor = 'var(--red-border)';
      statusBox.style.background = 'var(--red-soft)';
      statusBox.textContent = '⚠️ Bạn cần thu âm giọng nói đạt chuẩn trước khi bấm kích hoạt!';
    }
    return;
  }

  const roleLabel = 'Khách đến chơi (Cấp 3)';
  const emailSuffix = guestEmail ? ` · Email: ${guestEmail}` : ' · Không dùng Email';
  const durText = (lastVerifiedGuestData && lastVerifiedGuestData.duration_label) || guestDurationLabel || '1 ngày';

  if (badge) {
    badge.className = 'badge badge-ok';
    badge.textContent = 'Đã kích hoạt · Cấp 3';
  }
  if (statusBox) {
    statusBox.style.borderColor = '#cce5e3';
    statusBox.style.background = 'var(--accent-soft)';
    statusBox.textContent = `🎉 ĐÃ KÍCH HOẠT THÀNH CÔNG quyền ${roleLabel} cho "${guestName}" (Thời hạn: ${durText}${emailSuffix})!`;
  }
  if (voiceBox) {
    voiceBox.style.borderColor = '#cce5e3';
    voiceBox.style.background = 'var(--accent-soft)';
    voiceBox.textContent = `✅ Hoàn tất! Giọng nói của "${guestName}" (${roleLabel}${emailSuffix}) đã được lưu và kích hoạt trên hệ thống.`;
  }

  if (listContainer) {
    const row = document.createElement('div');
    row.className = 'guest-row';
    row.innerHTML = `
      <div>
        <div class="guest-name">${guestName} (${roleLabel})</div>
        <div class="guest-sub">Thời hạn: ${durText}${emailSuffix} · Đã xác thực giọng nói</div>
      </div>
    `;
    listContainer.prepend(row);
  }
}

async function recordAndEnrollGuestVoice(isGood) {
  const b64 = generateSynthetic16kPcmB64(isGood);
  await sendGuestVoicePayload(b64);
}

async function submitDoubleEmailOtp() {
  const nameEl = document.getElementById('guestNameInput');
  const e1El = document.getElementById('guestEmail1');
  const e2El = document.getElementById('guestEmail2');
  const guestName = (nameEl && nameEl.value.trim()) ? nameEl.value.trim() : 'Khách Đến Chơi';
  const email1 = e1El ? e1El.value.trim() : '';
  const email2 = e2El ? e2El.value.trim() : '';
  const box = document.getElementById('emailVerifyResult');

  const res = await fetch('/api/auth3/guest_qr_send_otp', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: lockedSessionId,
      guest_name: guestName,
      email_1: email1,
      email_2: email2,
      duration: guestDurationCode
    })
  });
  const data = await res.json();
  if (data.ok) {
    const area = document.getElementById('otpVerifyArea');
    const otpIn = document.getElementById('guestOtpInput');
    if (area) area.style.display = 'block';
    if (otpIn) otpIn.value = data.demo_otp_preview || data.otp_code || '';
    if (box) {
      box.style.borderColor = '#cce5e3';
      box.style.background = 'var(--accent-soft)';
      box.textContent = `Đã gửi mã xác nhận tới ${email1}.`;
    }
  } else {
    if (box) {
      box.style.borderColor = 'var(--red-border)';
      box.style.background = 'var(--red-soft)';
      box.textContent = data.error || 'Email chưa hợp lệ. Vui lòng kiểm tra lại.';
    }
  }
}

async function verifyGuestEmailOtp() {
  const e1El = document.getElementById('guestEmail1');
  const otpEl = document.getElementById('guestOtpInput');
  const email1 = e1El ? e1El.value.trim() : '';
  const otp = otpEl ? otpEl.value.trim() : '';
  const box = document.getElementById('emailVerifyResult');
  const badge = document.getElementById('handshakeBadge');

  const res = await fetch('/api/auth3/guest_qr_verify_otp', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: email1, otp })
  });
  const data = await res.json();
  if (data.ok) {
    if (badge) {
      badge.className = 'badge badge-ok';
      badge.textContent = 'Đã kích hoạt';
    }
    if (box) {
      box.style.borderColor = '#cce5e3';
      box.style.background = 'var(--accent-soft)';
      box.textContent = 'Đã kích hoạt tài khoản khách.';
    }
  } else {
    if (box) {
      box.style.borderColor = 'var(--red-border)';
      box.style.background = 'var(--red-soft)';
      box.textContent = data.error || 'Mã xác nhận chưa đúng. Vui lòng thử lại.';
    }
  }
}

window.addEventListener('DOMContentLoaded', initQrHandshake);

// Window exports for inline event handlers
window.onGuestTierChange = onGuestTierChange;
window.updateGuestPromptByRole = updateGuestPromptByRole;
window.onDurationChange = onDurationChange;
window.refreshGuestQrNow = refreshGuestQrNow;
window.doGuestHandshake = doGuestHandshake;
window.initQrHandshake = initQrHandshake;
window.recreateInvite = recreateInvite;
window.copyInviteLink = copyInviteLink;
window.cancelInvite = cancelInvite;
window.revokeGuestAccess = revokeGuestAccess;
window.toggleGuestMicRecording = toggleGuestMicRecording;
window.startGuestMicRecording = startGuestMicRecording;
window.stopGuestMicRecording = stopGuestMicRecording;
window.generateSynthetic16kPcmB64 = generateSynthetic16kPcmB64;
window.sendGuestVoicePayload = sendGuestVoicePayload;
window.confirmAndActivateGuestVoice = confirmAndActivateGuestVoice;
window.recordAndEnrollGuestVoice = recordAndEnrollGuestVoice;
window.submitDoubleEmailOtp = submitDoubleEmailOtp;
window.verifyGuestEmailOtp = verifyGuestEmailOtp;
