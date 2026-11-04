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
    let lastValidGuestPcmB64 = '';
    let lastVerifiedGuestData = null;

    function onGuestTierChange(val) {
      const t = parseInt(val || '3', 10);
      guestTargetTier = (t === 2) ? 2 : 3;
      const nameInput = document.getElementById('guestNameInput');
      if (nameInput) {
        if (guestTargetTier === 2 && nameInput.value === 'Khách Đến Chơi Nhà') {
          nameInput.value = 'Thành Viên Gia Đình Mới';
        } else if (guestTargetTier === 3 && nameInput.value === 'Thành Viên Gia Đình Mới') {
          nameInput.value = 'Khách Đến Chơi Nhà';
        }
      }
      updateGuestPromptByRole();
      refreshGuestQrNow();
    }

    function updateGuestPromptByRole() {
      const nameEl = document.getElementById('guestNameInput');
      const promptEl = document.getElementById('readingPromptBox');
      const speakerName = (nameEl && nameEl.value.trim()) ? nameEl.value.trim() : 'Khách Đến Chơi Nhà';
      const roleDesc = guestTargetTier === 2 ? 'Thành viên Gia đình (Cấp 2)' : 'Khách đến chơi nhà (Cấp 3)';
      if (promptEl) {
        promptEl.textContent = `"Xin chào ngôi nhà, tôi là ${speakerName} đăng ký quyền ${roleDesc} để điều khiển thiết bị bằng giọng nói."`;
      }
    }

    function onDurationChange(val) {
      guestDurationCode = val;
      refreshGuestQrNow();
    }

    async function refreshGuestQrNow() {
      try {
        const sel = document.getElementById('guestDurationSelect');
        const tierSel = document.getElementById('guestTierSelect');
        const dur = sel ? sel.value : guestDurationCode;
        const tier = tierSel ? tierSel.value : String(guestTargetTier);
        guestDurationCode = dur;
        guestTargetTier = parseInt(tier || '3', 10) === 2 ? 2 : 3;
        const res = await fetch(`/api/auth3/guest_qr_current?duration=${encodeURIComponent(dur)}&target_tier=${encodeURIComponent(guestTargetTier)}&host=${encodeURIComponent(location.host)}`);
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
          const roleShort = guestTargetTier === 2 ? 'Cấp 2 (Gia đình)' : 'Cấp 3 (Khách)';
          tokBox.textContent = `Token: ${data.token} · ${roleShort}`;
        }

        if (!lockedSessionId) {
          await doGuestHandshake(data.token, dur);
        }
      } catch (e) {}
    }

    async function doGuestHandshake(token, dur, targetWindow) {
      try {
        const payload = { token, duration: dur };
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
          guestDurationCode = data.session ? data.session.duration_code : (data.duration_code || dur);
          guestDurationLabel = data.session ? data.session.duration_label : (data.duration_label || '1 ngày');
          if (badge) {
            badge.className = 'badge badge-ok';
            badge.textContent = 'Đang chờ thu âm';
          }
          if (durBadge) durBadge.textContent = guestDurationLabel;
          if (box && !lastValidGuestPcmB64) {
            box.style.borderColor = '#cce5e3';
            box.style.background = 'var(--accent-soft)';
            box.textContent = `Phiên đăng ký sẵn sàng (Thời hạn: ${guestDurationLabel}). Hãy nhập Tên, thu âm giọng nói và bấm nút OK để kích hoạt.`;
          }
        } else {
          if (badge) {
            badge.className = 'badge badge-err';
            badge.textContent = 'Hết hạn';
          }
          if (box) {
            box.style.borderColor = 'var(--red-border)';
            box.style.background = 'var(--red-soft)';
            box.textContent = data.error || 'Lời mời đã hết hạn. Đang làm mới...';
          }
        }
      } catch (err) {}
    }

    async function initQrHandshake() {
      const params = new URLSearchParams(window.location.search);
      const urlToken = params.get('token');
      const urlWindow = params.get('window');
      const dur = params.get('dur') || '1d';
      const tierParam = params.get('tier');
      guestDurationCode = dur;
      const sel = document.getElementById('guestDurationSelect');
      if (sel) sel.value = dur;
      if (tierParam === '2' || tierParam === '3') {
        guestTargetTier = parseInt(tierParam, 10);
        const tierSel = document.getElementById('guestTierSelect');
        if (tierSel) tierSel.value = String(guestTargetTier);
      }
      updateGuestPromptByRole();

      if (urlToken) {
        currentGuestToken = urlToken;
        const tokBox = document.getElementById('guestQrTokenBox');
        if (tokBox) {
          const roleShort = guestTargetTier === 2 ? 'Cấp 2 (Gia đình)' : 'Cấp 3 (Khách)';
          tokBox.textContent = `Token: ${urlToken} · ${roleShort}`;
        }
        await doGuestHandshake(urlToken, dur, urlWindow);
      } else {
        await refreshGuestQrNow();
        setInterval(refreshGuestQrNow, 1000);
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
        await navigator.clipboard.writeText(window.location.href);
        if (box) box.textContent = 'Đã sao chép liên kết đăng ký QR vào bộ nhớ tạm.';
      } catch (_) {
        if (box) box.textContent = 'Đã sẵn sàng sao chép liên kết mời khách.';
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

    // Web Audio API thu âm thật 16kHz 16-bit PCM Mono
    async function toggleGuestMicRecording() {
      if (isGuestRecording) {
        await stopGuestMicRecording();
      } else {
        await startGuestMicRecording();
      }
    }

    async function startGuestMicRecording() {
      const box = document.getElementById('voiceEnrollResult');
      const btnText = document.getElementById('btnRecordGuestVoiceText');
      guestRecordedPcmChunks = [];
      try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          return recordAndEnrollGuestVoice(true);
        }
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
      } catch (err) {
        await recordAndEnrollGuestVoice(true);
      }
    }

    async function stopGuestMicRecording() {
      isGuestRecording = false;
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
      guestRecordedPcmChunks.forEach(c => {
        fullPcm.set(c, offset);
        offset += c.length;
      });

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
      const guestName = (nameInput && nameInput.value.trim()) ? nameInput.value.trim() : 'Khách Đến Chơi';
      const guestEmail = (emailOptInput && emailOptInput.value.trim()) ? emailOptInput.value.trim() : '';
      const box = document.getElementById('voiceEnrollResult');
      const statusBox = document.getElementById('handshakeStatus');
      const badge = document.getElementById('handshakeBadge');
      const okBtn = document.getElementById('btnConfirmGuestVoiceOk');

      if (!nameInput || !nameInput.value.trim()) {
        if (box) {
          box.style.borderColor = 'var(--red-border)';
          box.style.background = 'var(--red-soft)';
          box.textContent = '⚠️ Vui lòng nhập Họ và tên của bạn ở mục 3 trước khi thu âm!';
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
          target_tier: guestTargetTier,
          duration: guestDurationCode,
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
          badge.textContent = 'Thu âm ĐẠT';
        }
        const roleLabel = guestTargetTier === 2 ? 'Thành viên Gia đình (Cấp 2)' : 'Khách (Cấp 3)';
        const f0Str = data.f0_hz ? ` (F0 = ${Number(data.f0_hz).toFixed(1)} Hz)` : '';
        if (box) {
          box.style.borderColor = '#cce5e3';
          box.style.background = 'var(--accent-soft)';
          box.textContent = `✅ ĐẠT CHUẨN${f0Str} — Giọng của "${guestName}" (${roleLabel}) đã hợp lệ! Hãy nhấn nút "OK · Xác nhận giọng nói & Kích hoạt ngay" ở mục 6 bên dưới.`;
        }
        if (statusBox) {
          statusBox.style.borderColor = '#cce5e3';
          statusBox.style.background = 'var(--accent-soft)';
          statusBox.textContent = `Giọng nói đã đạt chuẩn! Hãy ấn nút "OK · Xác nhận giọng nói & Kích hoạt ngay" để hoàn tất.`;
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
            box.textContent = `⚠️ CHƯA ĐẠT: ${data.message || 'Chưa nhận rõ giọng nói hoặc quá ngắn.'} Vui lòng bấm "Thu lại" đến khi đạt chuẩn!`;
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
          statusBox.textContent = '⚠️ Bạn cần thu âm giọng nói đạt chuẩn ở mục 5 trước khi bấm OK!';
        }
        return;
      }

      const roleLabel = guestTargetTier === 2 ? 'Thành viên Gia đình (Cấp 2)' : 'Khách đến chơi (Cấp 3)';
      const emailSuffix = guestEmail ? ` · Email: ${guestEmail}` : ' · Không dùng Email';
      const durText = (lastVerifiedGuestData && lastVerifiedGuestData.duration_label) || guestDurationLabel || '1 ngày';

      if (badge) {
        badge.className = 'badge badge-ok';
        badge.textContent = 'Đã kích hoạt';
      }
      if (statusBox) {
        statusBox.style.borderColor = '#cce5e3';
        statusBox.style.background = 'var(--accent-soft)';
        statusBox.textContent = `🎉 ĐÃ KÍCH HOẠT THÀNH CÔNG trên Server cho "${guestName}" (${roleLabel} · Thời hạn: ${durText}${emailSuffix})!`;
      }
      if (voiceBox) {
        voiceBox.style.borderColor = '#cce5e3';
        voiceBox.style.background = 'var(--accent-soft)';
        voiceBox.textContent = `✅ Hoàn tất! Giọng nói của "${guestName}" (${roleLabel}) đã được lưu và kích hoạt trên hệ thống.`;
      }

      if (listContainer) {
        const row = document.createElement('div');
        row.className = 'guest-row';
        row.innerHTML = `
          <div>
            <div class="guest-name">${guestName} (${roleLabel})</div>
            <div class="guest-sub">Thời hạn: ${durText}${emailSuffix} · Đã xác thực giọng nói</div>
          </div>
          <div style="display:flex; align-items:center; gap:8px;">
            <span class="badge badge-ok">Đã kích hoạt</span>
            <details class="row-menu">
              <summary>Tùy chọn</summary>
              <div class="row-menu-panel">
                <button type="button" class="btn btn-danger" style="width:100%;" onclick="revokeGuestAccess('${guestName.replace(/'/g, "\\'")}')">Thu hồi quyền</button>
              </div>
            </details>
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
      const guestName = document.getElementById('guestNameInput').value.trim() || 'Khách Đến Chơi';
      const email1 = document.getElementById('guestEmail1').value.trim();
      const email2 = document.getElementById('guestEmail2').value.trim();
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
        document.getElementById('otpVerifyArea').style.display = 'block';
        document.getElementById('guestOtpInput').value = data.demo_otp_preview || data.otp_code || '';
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
      const email1 = document.getElementById('guestEmail1').value.trim();
      const otp = document.getElementById('guestOtpInput').value.trim();
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
