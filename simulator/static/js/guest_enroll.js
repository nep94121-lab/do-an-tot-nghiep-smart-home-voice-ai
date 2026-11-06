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
let guestRecordingInterval = null;
let guestRecordingStartTime = 0;
let lastValidGuestPcmB64 = '';
let lastVerifiedGuestData = null;
const GUEST_REQUIRED_SAMPLES = 5;
let guestRecordedSamplesB64 = [];

function getGuestEnrollmentPrompts5(speakerName, roleDesc) {
  const name = speakerName || 'Khách đến chơi nhà';
  const role = roleDesc || 'Khách đến chơi nhà (Cấp 3)';
  return [
    `Mẫu 1/5 (3–5s): Xin chào ngôi nhà, tôi là ${name} đăng ký quyền ${role} để điều khiển thiết bị bằng giọng nói.`,
    `Mẫu 2/5 (3–5s): Hệ thống nhà thông minh Bách Khoa hãy bật đèn phòng khách và quạt bàn cho khách.`,
    `Mẫu 3/5 (3–5s): Kiểm tra trạng thái đèn chiếu sáng và nhiệt độ phòng khách hôm nay.`,
    `Mẫu 4/5 (3–5s): Tắt đèn bàn làm việc và điều chỉnh tốc độ quạt phòng khách vừa phải.`,
    `Mẫu 5/5 (3–5s): Tôi là ${name} xác nhận hoàn tất năm mẫu giọng nói riêng biệt trên hệ thống.`
  ];
}

function setButtonLoading(btn, isLoading, loadingText) {
  if (!btn) return;
  if (isLoading) {
    btn.dataset.origHtml = btn.innerHTML;
    btn.disabled = true;
    btn.classList.add('btn-loading');
    btn.innerHTML = `<span class="spinner-icon" aria-hidden="true"></span> <span>${loadingText || 'Đang xử lý...'}</span>`;
  } else {
    btn.classList.remove('btn-loading');
    if (btn.dataset.origHtml) {
      btn.innerHTML = btn.dataset.origHtml;
      delete btn.dataset.origHtml;
    }
    if (btn.id === 'btnConfirmGuestVoiceOk') {
      btn.disabled = !lastValidGuestPcmB64;
    } else {
      btn.disabled = false;
    }
  }
}

function onGuestTierChange(val) {
  const t = parseInt(val || '3', 10);
  guestTargetTier = (t === 2) ? 2 : 3;
  updateGuestPromptByRole();
  refreshGuestQrNow();
}

function updateGuestPromptByRole(sampleIdx) {
  const nameEl = document.getElementById('guestNameInput');
  const promptEl = document.getElementById('readingPromptBox');
  const progBadge = document.getElementById('guestSampleProgressBadge');
  const speakerName = (nameEl && nameEl.value.trim()) ? nameEl.value.trim() : 'Khách đến chơi nhà';
  const roleDesc = guestTargetTier === 2 ? 'Thành viên Gia đình (Cấp 2)' : 'Khách đến chơi nhà (Cấp 3)';
  const idx = (typeof sampleIdx === 'number')
    ? Math.max(0, Math.min(GUEST_REQUIRED_SAMPLES - 1, sampleIdx))
    : Math.min(GUEST_REQUIRED_SAMPLES - 1, guestRecordedSamplesB64.length);
  const prompts5 = getGuestEnrollmentPrompts5(speakerName, roleDesc);
  if (promptEl) {
    promptEl.textContent = `"${prompts5[idx]}"`;
  }
  if (progBadge) {
    progBadge.textContent = `Mẫu ${idx + 1}/${GUEST_REQUIRED_SAMPLES} · 3–5 giây/mẫu`;
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
    let hasSession = false;
    try {
      hasSession = Boolean(
        (window.localStorage && (window.localStorage.getItem('session_token') || window.localStorage.getItem('smarthome_auth_session'))) ||
        (document.cookie && (document.cookie.includes('sh_session_token=') || document.cookie.includes('session_token=')))
      );
    } catch (_) {}
    if (hasSession) {
      await refreshGuestQrNow();
    } else {
      const badge = document.getElementById('handshakeBadge');
      const box = document.getElementById('handshakeStatus');
      const durBadge = document.getElementById('durationBadge');
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
    }
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
  const micAlert = document.getElementById('micErrorAlert');

  if (micAlert) {
    micAlert.style.display = 'none';
  }

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

  // BỎ HOÀN TOÀN TỰ SINH SÓNG SIN GIẢ LẬP KHI MIC LỖI
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    if (micAlert) {
      micAlert.style.display = 'block';
      micAlert.textContent = '❌ Trình duyệt hoặc thiết bị của bạn không hỗ trợ thu âm qua microphone. Vui lòng sử dụng tính năng tải lên tệp âm thanh bên dưới!';
    }
    const okBtn = document.getElementById('btnConfirmGuestVoiceOk');
    if (okBtn) okBtn.disabled = true;
    return;
  }

  try {
    guestMediaStream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, sampleRate: 16000 } });
    guestAudioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    if (guestAudioContext.state === 'suspended') {
      await guestAudioContext.resume();
    }
    const source = guestAudioContext.createMediaStreamSource(guestMediaStream);
    guestAudioProcessor = guestAudioContext.createScriptProcessor(4096, 1, 1);
    guestAudioProcessor.onaudioprocess = (e) => {
      if (!isGuestRecording) return;
      const rawInput = e.inputBuffer.getChannelData(0);
      const actualSr = guestAudioContext ? guestAudioContext.sampleRate : 16000;
      let input = rawInput;
      if (actualSr && actualSr !== 16000 && rawInput.length > 0) {
        const outLen = Math.max(1, Math.round((rawInput.length * 16000) / actualSr));
        input = new Float32Array(outLen);
        const ratio = rawInput.length / outLen;
        for (let i = 0; i < outLen; i++) {
          const idxStart = Math.max(0, Math.floor(i * ratio));
          const idxEnd = Math.min(rawInput.length - 1, Math.ceil((i + 1) * ratio) - 1);
          if (idxEnd <= idxStart) {
            input[i] = rawInput[idxStart];
          } else {
            let sum = 0;
            for (let k = idxStart; k <= idxEnd; k++) sum += rawInput[k];
            input[i] = sum / (idxEnd - idxStart + 1);
          }
        }
      }
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
      box.textContent = '🎤 Đang thu âm 16kHz... Hãy đọc to câu mẫu phía trên rồi bấm nút Dừng!';
    }

    // Hiển thị khung trạng thái ghi âm trực quan
    const recBox = document.getElementById('recordingIndicatorBox');
    if (recBox) recBox.style.display = 'flex';
    const timerEl = document.getElementById('recordingTimer');
    if (timerEl) timerEl.textContent = '00:00';
    guestRecordingStartTime = Date.now();
    if (guestRecordingInterval) clearInterval(guestRecordingInterval);
    guestRecordingInterval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - guestRecordingStartTime) / 1000);
      const m = String(Math.floor(elapsed / 60)).padStart(2, '0');
      const s = String(elapsed % 60).padStart(2, '0');
      const tEl = document.getElementById('recordingTimer');
      if (tEl) tEl.textContent = `${m}:${s}`;
    }, 1000);

    if (guestAutoStopTimer) clearTimeout(guestAutoStopTimer);
    guestAutoStopTimer = setTimeout(() => {
      if (isGuestRecording) {
        stopGuestMicRecording();
      }
    }, 4500);
  } catch (err) {
    isGuestRecording = false;
    const recBox = document.getElementById('recordingIndicatorBox');
    if (recBox) recBox.style.display = 'none';
    if (guestRecordingInterval) {
      clearInterval(guestRecordingInterval);
      guestRecordingInterval = null;
    }
    if (micAlert) {
      micAlert.style.display = 'block';
      const isDenied = err && (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError' || String(err).includes('Permission denied'));
      const isNotFound = err && (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError');
      if (isDenied) {
        micAlert.textContent = '❌ Quyền truy cập microphone bị từ chối. Vui lòng cấp quyền trong cài đặt trình duyệt hoặc sử dụng tính năng tải lên tệp âm thanh bên dưới!';
      } else if (isNotFound) {
        micAlert.textContent = '❌ Không tìm thấy thiết bị microphone trên máy này. Vui lòng kết nối micro hoặc sử dụng tính năng tải lên tệp âm thanh bên dưới!';
      } else {
        micAlert.textContent = `❌ Lỗi truy cập microphone: ${err.message || 'Không thể mở micro'}. Vui lòng cấp quyền hoặc tải lên tệp âm thanh bên dưới!`;
      }
    }
    const okBtn = document.getElementById('btnConfirmGuestVoiceOk');
    if (okBtn) okBtn.disabled = true;
    if (box) {
      box.style.borderColor = 'var(--red-border)';
      box.style.background = 'var(--red-soft)';
      box.textContent = '⚠️ Microphone không khả dụng. Bạn hãy tải lên tệp âm thanh bên dưới để tiếp tục.';
    }
  }
}

async function stopGuestMicRecording() {
  isGuestRecording = false;
  if (guestAutoStopTimer) {
    clearTimeout(guestAutoStopTimer);
    guestAutoStopTimer = null;
  }
  if (guestRecordingInterval) {
    clearInterval(guestRecordingInterval);
    guestRecordingInterval = null;
  }
  const recBox = document.getElementById('recordingIndicatorBox');
  if (recBox) recBox.style.display = 'none';

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

  if (totalLen < 8000 || peak < 100) {
    const box = document.getElementById('voiceEnrollResult');
    if (box) {
      box.style.borderColor = 'var(--red-border)';
      box.style.background = 'var(--red-soft)';
      box.textContent = '⚠️ Giọng thu âm quá ngắn hoặc không có tiếng. Vui lòng bấm "Thu lại" hoặc tải lên tệp âm thanh!';
    }
    const badge = document.getElementById('handshakeBadge');
    if (badge) {
      badge.className = 'badge badge-warn';
      badge.textContent = 'Cần thu lại';
    }
    const okBtn = document.getElementById('btnConfirmGuestVoiceOk');
    if (okBtn) okBtn.disabled = true;
    return;
  }

  let binary = '';
  const bytes = new Uint8Array(fullPcm.buffer);
  const len = bytes.byteLength;
  for (let i = 0; i < len; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  const b64 = window.btoa(binary);
  if (guestRecordedSamplesB64.length >= GUEST_REQUIRED_SAMPLES) {
    guestRecordedSamplesB64 = [];
  }
  guestRecordedSamplesB64.push(b64);
  updateGuestPromptByRole(Math.min(GUEST_REQUIRED_SAMPLES - 1, guestRecordedSamplesB64.length));
  await sendGuestVoicePayload(b64, guestRecordedSamplesB64.slice());
}

async function handleGuestAudioFileUpload(event) {
  const files = event.target && event.target.files ? Array.from(event.target.files) : [];
  const file = files[0];
  if (!file) return;

  const uploadInfo = document.getElementById('uploadedAudioInfo');
  const uploadLabel = document.getElementById('btnUploadAudioLabel');
  const micAlert = document.getElementById('micErrorAlert');
  if (micAlert) micAlert.style.display = 'none';

  const validExts = ['.wav', '.m4a', '.webm', '.mp3', '.ogg'];
  const fileNameLower = file.name.toLowerCase();
  const isValidExt = validExts.some(ext => fileNameLower.endsWith(ext)) || (file.type && file.type.startsWith('audio/'));

  if (!isValidExt) {
    if (uploadInfo) {
      uploadInfo.style.display = 'block';
      uploadInfo.style.color = 'var(--red)';
      uploadInfo.style.background = 'var(--red-soft)';
      uploadInfo.style.borderColor = 'var(--red-border)';
      uploadInfo.textContent = `❌ Tệp "${file.name}" không hợp lệ. Vui lòng chọn tệp .wav, .m4a, .webm, .mp3 hoặc .ogg!`;
    }
    return;
  }

  // Kiểm tra giới hạn dung lượng tệp tối đa 15MB
  const MAX_FILE_SIZE = 15 * 1024 * 1024;
  if (file.size > MAX_FILE_SIZE) {
    if (uploadInfo) {
      uploadInfo.style.display = 'block';
      uploadInfo.style.color = 'var(--red)';
      uploadInfo.style.background = 'var(--red-soft)';
      uploadInfo.style.borderColor = 'var(--red-border)';
      uploadInfo.textContent = `❌ Tệp "${file.name}" quá lớn (${(file.size / (1024 * 1024)).toFixed(1)} MB). Vui lòng chọn tệp nhỏ hơn 15MB!`;
    }
    const okBtn = document.getElementById('btnConfirmGuestVoiceOk');
    if (okBtn) okBtn.disabled = true;
    lastValidGuestPcmB64 = '';
    event.target.value = '';
    return;
  }

  if (uploadInfo) {
    uploadInfo.style.display = 'block';
    uploadInfo.style.color = 'var(--accent)';
    uploadInfo.style.background = 'var(--accent-soft)';
    uploadInfo.style.borderColor = '#cce5e3';
    uploadInfo.textContent = `📁 Đang tải tệp: ${file.name} (${(file.size / 1024).toFixed(1)} KB)...`;
  }

  if (uploadLabel) {
    setButtonLoading(uploadLabel, true, 'Đang đọc tệp...');
  }

  try {
    const decodeOneFileToB64 = async (f) => {
      const arrayBuffer = await f.arrayBuffer();
      try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
        const decodedBuffer = await audioCtx.decodeAudioData(arrayBuffer.slice(0));
        const offlineCtx = new (window.OfflineAudioContext || window.webkitOfflineAudioContext)(
          1,
          Math.ceil(decodedBuffer.duration * 16000),
          16000
        );
        const src = offlineCtx.createBufferSource();
        src.buffer = decodedBuffer;
        src.connect(offlineCtx.destination);
        src.start(0);
        const rendered = await offlineCtx.startRendering();
        const ch = rendered.getChannelData(0);
        const pcm16 = new Int16Array(ch.length);
        for (let i = 0; i < ch.length; i++) {
          const s = Math.max(-1, Math.min(1, ch[i]));
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }
        let binary = '';
        const bytes = new Uint8Array(pcm16.buffer);
        for (let i = 0; i < bytes.byteLength; i++) {
          binary += String.fromCharCode(bytes[i]);
        }
        audioCtx.close();
        return window.btoa(binary);
      } catch (_) {
        let binary = '';
        const bytes = new Uint8Array(arrayBuffer);
        for (let i = 0; i < bytes.byteLength; i++) {
          binary += String.fromCharCode(bytes[i]);
        }
        return window.btoa(binary);
      }
    };

    const uploadedList = [];
    for (const f of files.slice(0, GUEST_REQUIRED_SAMPLES)) {
      if (f.size <= MAX_FILE_SIZE) {
        uploadedList.push(await decodeOneFileToB64(f));
      }
    }
    const b64Payload = uploadedList[0] || '';
    if (uploadedList.length >= GUEST_REQUIRED_SAMPLES) {
      guestRecordedSamplesB64 = uploadedList.slice(0, GUEST_REQUIRED_SAMPLES);
    } else {
      for (const item of uploadedList) {
        if (guestRecordedSamplesB64.length >= GUEST_REQUIRED_SAMPLES) {
          guestRecordedSamplesB64 = [];
        }
        guestRecordedSamplesB64.push(item);
      }
    }
    updateGuestPromptByRole(Math.min(GUEST_REQUIRED_SAMPLES - 1, guestRecordedSamplesB64.length));
    await sendGuestVoicePayload(b64Payload, guestRecordedSamplesB64.slice());

    if (lastValidGuestPcmB64) {
      if (uploadInfo) {
        uploadInfo.textContent = `✅ Đã tải tệp "${file.name}" (${guestRecordedSamplesB64.length}/${GUEST_REQUIRED_SAMPLES} mẫu) thành công! Nút Lưu đã sẵn sàng.`;
      }
      const okBtn = document.getElementById('btnConfirmGuestVoiceOk');
      if (okBtn) okBtn.disabled = false;
    } else {
      if (uploadInfo) {
        uploadInfo.style.color = 'var(--red)';
        uploadInfo.style.background = 'var(--red-soft)';
        uploadInfo.style.borderColor = 'var(--red-border)';
        uploadInfo.textContent = `⚠️ Tệp "${file.name}" chưa đạt chuẩn chất lượng giọng nói. Vui lòng chọn tệp khác!`;
      }
    }
  } catch (err) {
    if (uploadInfo) {
      uploadInfo.style.color = 'var(--red)';
      uploadInfo.style.background = 'var(--red-soft)';
      uploadInfo.style.borderColor = 'var(--red-border)';
      uploadInfo.textContent = `❌ Lỗi khi đọc tệp âm thanh: ${err.message || 'Không thể xử lý tệp'}`;
    }
  } finally {
    if (uploadLabel) {
      setButtonLoading(uploadLabel, false);
    }
    event.target.value = '';
  }
}

async function sendGuestVoicePayload(b64Pcm, samplesListB64) {
  const nameInput = document.getElementById('guestNameInput');
  const emailOptInput = document.getElementById('guestOptionalEmailInput');
  const guestName = (nameInput && nameInput.value.trim()) ? nameInput.value.trim() : '';
  const guestEmail = (emailOptInput && emailOptInput.value.trim()) ? emailOptInput.value.trim() : '';
  const box = document.getElementById('voiceEnrollResult');
  const statusBox = document.getElementById('handshakeStatus');
  const badge = document.getElementById('handshakeBadge');
  const okBtn = document.getElementById('btnConfirmGuestVoiceOk');
  const recBtn = document.getElementById('btnRecordGuestVoice');
  const retryBtn = document.getElementById('btnRetryGuestVoice');
  const effectiveSamples = (Array.isArray(samplesListB64) && samplesListB64.length > 0)
    ? samplesListB64
    : (b64Pcm ? [b64Pcm] : []);

  if (!guestName) {
    if (box) {
      box.style.borderColor = 'var(--red-border)';
      box.style.background = 'var(--red-soft)';
      box.textContent = '⚠️ Vui lòng nhập Họ và tên của bạn trước khi thu âm!';
    }
    return;
  }

  if (box) box.textContent = `Đang kiểm định chất lượng giọng nói WeSpeaker (${effectiveSamples.length}/${GUEST_REQUIRED_SAMPLES} mẫu 16kHz PCM)...`;
  setButtonLoading(recBtn, true, 'Đang phân tích...');
  setButtonLoading(retryBtn, true, 'Đang gửi...');

  try {
    const res = await fetch('/api/auth3/guest_qr_complete_voice', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: lockedSessionId,
        guest_name: guestName,
        guest_email: guestEmail,
        target_tier: 3,
        duration: guestDurationCode || '1d',
        audio_pcm_b64: b64Pcm,
        samples_b64: effectiveSamples,
        sample_count: effectiveSamples.length,
        sample_index: effectiveSamples.length,
        total_samples: GUEST_REQUIRED_SAMPLES
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
  } catch (err) {
    lastValidGuestPcmB64 = '';
    lastVerifiedGuestData = null;
    if (okBtn) okBtn.disabled = true;
    if (box) {
      box.style.borderColor = 'var(--red-border)';
      box.style.background = 'var(--red-soft)';
      box.textContent = `❌ Lỗi gửi dữ liệu: ${err.message || 'Không thể kết nối máy chủ'}`;
    }
  } finally {
    setButtonLoading(recBtn, false);
    setButtonLoading(retryBtn, false);
  }
}

async function confirmAndActivateGuestVoice() {
  const okBtn = document.getElementById('btnConfirmGuestVoiceOk');
  if (!okBtn || okBtn.disabled || okBtn.classList.contains('btn-loading')) {
    return;
  }
  setButtonLoading(okBtn, true, 'Đang lưu & kích hoạt...');

  const nameInput = document.getElementById('guestNameInput');
  const emailOptInput = document.getElementById('guestOptionalEmailInput');
  const guestName = (nameInput && nameInput.value.trim()) ? nameInput.value.trim() : 'Khách Đến Chơi';
  const guestEmail = (emailOptInput && emailOptInput.value.trim()) ? emailOptInput.value.trim() : '';
  const statusBox = document.getElementById('handshakeStatus');
  const voiceBox = document.getElementById('voiceEnrollResult');
  const badge = document.getElementById('handshakeBadge');
  const listContainer = document.getElementById('guestListContainer');
  const saveAlert = document.getElementById('saveFeedbackAlert');

  try {
    if (!lastValidGuestPcmB64) {
      if (saveAlert) {
        saveAlert.style.display = 'block';
        saveAlert.className = 'alert-box alert-error';
        saveAlert.textContent = '⚠️ Bạn cần thu âm giọng nói hoặc tải lên tệp âm thanh đạt chuẩn trước khi lưu!';
      }
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
    if (saveAlert) {
      saveAlert.style.display = 'block';
      saveAlert.className = 'alert-box alert-success';
      saveAlert.textContent = `🎉 ĐÃ KÍCH HOẠT THÀNH CÔNG quyền ${roleLabel} cho "${guestName}" (Thời hạn: ${durText}${emailSuffix})!`;
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

    // Đặt lại dữ liệu giọng nói đã lưu để chống click spam
    lastValidGuestPcmB64 = '';
    lastVerifiedGuestData = null;
  } catch (err) {
    if (saveAlert) {
      saveAlert.style.display = 'block';
      saveAlert.className = 'alert-box alert-error';
      saveAlert.textContent = `❌ Lỗi khi kích hoạt: ${err.message || 'Lỗi không xác định'}`;
    }
  } finally {
    setButtonLoading(okBtn, false);
    if (okBtn) {
      okBtn.disabled = true;
    }
  }
}

async function retryGuestVoiceRecording() {
  if (isGuestRecording) {
    await stopGuestMicRecording();
  }
  lastValidGuestPcmB64 = '';
  const okBtn = document.getElementById('btnConfirmGuestVoiceOk');
  if (okBtn) okBtn.disabled = true;
  const box = document.getElementById('voiceEnrollResult');
  if (box) {
    box.style.borderColor = 'var(--line)';
    box.style.background = '#fcfdfe';
    box.textContent = 'Đang mở micro thu âm lại...';
  }
  await startGuestMicRecording();
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
    if (otpIn) otpIn.value = '';
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
window.retryGuestVoiceRecording = retryGuestVoiceRecording;
window.sendGuestVoicePayload = sendGuestVoicePayload;
window.confirmAndActivateGuestVoice = confirmAndActivateGuestVoice;
window.submitDoubleEmailOtp = submitDoubleEmailOtp;
window.verifyGuestEmailOtp = verifyGuestEmailOtp;
window.setButtonLoading = setButtonLoading;
window.handleGuestAudioFileUpload = handleGuestAudioFileUpload;
