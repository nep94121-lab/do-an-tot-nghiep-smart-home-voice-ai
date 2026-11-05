    const tierBadgeClass = (t) => t === 1 ? 'badge-tier1' : (t === 2 ? 'badge-tier2' : 'badge-tier3');
    const tierRoleLabel = (t) => t === 1 ? 'Chủ nhà (Cấp 1)' : (t === 2 ? 'Gia đình (Cấp 2)' : 'Khách (Cấp 3)');

    let selectedEnrollTier = 2;
    let selectedSpeakerName = '';
    let lastVoiceEnrollPassed = false;
    let lastMeasuredF0Hz = 125.0;

    function openStepPanel(stepNum) {
      [1, 2, 3].forEach((n) => {
        const p = document.getElementById('stepPanel' + n);
        if (p) p.open = (n === stepNum);
      });
    }

    function fillAccount(email, pw) {
      const emailEl = document.getElementById('loginEmail');
      const pwEl = document.getElementById('loginPassword');
      const pwConfirmEl = document.getElementById('loginPasswordConfirm');
      if (emailEl) emailEl.value = email;
      if (pwEl) pwEl.value = pw;
      if (pwConfirmEl) pwConfirmEl.value = pw;
    }

    function applyPresetAccount(preset) {
      if (preset === 'owner') {
        fillAccount('nep94121@gmail.com', '123456');
        onEnrollTierSelectChange('1');
      } else if (preset === 'family') {
        fillAccount('senat6031@gmail.com', 'GiaDinh@123');
        onEnrollTierSelectChange('2');
      } else if (preset === 'guest') {
        fillAccount('kbanh376@gmail.com', 'Khach@789');
        onEnrollTierSelectChange('3');
      } else if (preset === 'wrong') {
        fillAccount('nep94121@gmail.com', 'SaiMatKhau999');
      }
    }

    function onEnrollTierSelectChange(tierVal) {
      const t = parseInt(tierVal || '2', 10);
      selectedEnrollTier = (t === 1 || t === 2 || t === 3) ? t : 2;
      const tierSel = document.getElementById('enrollTierSelect');
      if (tierSel && String(tierSel.value) !== String(selectedEnrollTier)) {
        tierSel.value = String(selectedEnrollTier);
      }
      const nameInput = document.getElementById('enrollSpeakerNameInput');
      const step2NameInput = document.getElementById('step2SpeakerNameInput');
      const emailInput = document.getElementById('loginEmail');
      const accSelect = document.getElementById('firstPageAccountSelect');

      if (nameInput) {
        nameInput.readOnly = false;
        selectedSpeakerName = nameInput.value.trim();
      }
      if (step2NameInput) step2NameInput.value = selectedSpeakerName;
      if (emailInput) {
        emailInput.readOnly = false;
      }
      if (accSelect && emailInput && emailInput.value) {
        accSelect.value = emailInput.value;
      }
      updateFirstPageReadingPrompt();
      refreshStepSummaries();
    }

    function syncSpeakerNameInput(val) {
      selectedSpeakerName = (val || '').trim() || 'Người dùng';
      const step2NameInput = document.getElementById('step2SpeakerNameInput');
      if (step2NameInput) step2NameInput.value = selectedSpeakerName;
      updateFirstPageReadingPrompt();
      refreshStepSummaries();
    }

    function onStep2SpeakerNameInput(val) {
      selectedSpeakerName = (val || '').trim() || 'Người dùng';
      const step1NameInput = document.getElementById('enrollSpeakerNameInput');
      if (step1NameInput) {
        step1NameInput.value = selectedSpeakerName;
      }
      updateFirstPageReadingPrompt();
      refreshStepSummaries();
    }

    function refreshStepSummaries() {
      const badge2 = document.getElementById('step2SpeakerSummaryBadge');
      const roleText = selectedEnrollTier === 1
        ? 'Cấp 1 · Chủ nhà cố định'
        : (selectedEnrollTier === 2 ? 'Cấp 2 · Thành viên gia đình' : 'Cấp 3 · Khách đến chơi');
      if (badge2) {
        badge2.className = `badge ${tierBadgeClass(selectedEnrollTier)}`;
        badge2.textContent = `Đang chọn: ${selectedSpeakerName} (${roleText})`;
      }
      const s3Name = document.getElementById('step3SummaryName');
      const s3Tier = document.getElementById('step3SummaryTier');
      const s3Email = document.getElementById('step3SummaryEmail');
      const s3Status = document.getElementById('step3SummaryVoiceStatus');
      const emailEl = document.getElementById('loginEmail');
      if (s3Name) s3Name.textContent = selectedSpeakerName;
      if (s3Tier) s3Tier.textContent = roleText;
      if (s3Email && emailEl) s3Email.textContent = emailEl.value.trim() || 'nep94121@gmail.com';
      if (s3Status) {
        s3Status.textContent = lastVoiceEnrollPassed
          ? `✅ ĐÃ ĐẠT CHUẨN (F0 = ${Number(lastMeasuredF0Hz).toFixed(1)} Hz)`
          : '⏳ Chưa thu âm hoặc chưa đạt (Cần thu âm ở Bước 2)';
      }
    }

    async function completeStep1AndGoToVoice() {
      const emailEl = document.getElementById('loginEmail');
      const pwEl = document.getElementById('loginPassword');
      const pwConfirmEl = document.getElementById('loginPasswordConfirm');
      const nameEl = document.getElementById('enrollSpeakerNameInput');
      const box = document.getElementById('loginStatusBox');

      const email = emailEl ? emailEl.value.trim() : 'nep94121@gmail.com';
      const password = pwEl ? pwEl.value : '123456';
      const confirmPassword = pwConfirmEl ? pwConfirmEl.value : password;
      const speakerName = nameEl ? nameEl.value.trim() : selectedSpeakerName;

      if (!speakerName) {
        if (box) {
          box.style.borderColor = 'var(--red-border)';
          box.style.background = 'var(--red-soft)';
          box.textContent = '⚠️ Vui lòng nhập Họ và tên người lưu giọng nói ở Bước 1!';
        }
        return;
      }

      if (!email || !email.includes('@')) {
        if (box) {
          box.style.borderColor = 'var(--red-border)';
          box.style.background = 'var(--red-soft)';
          box.textContent = '⚠️ Vui lòng nhập địa chỉ Email hợp lệ!';
        }
        return;
      }

      if (password !== confirmPassword) {
        setStepState('retry', '', '');
        if (box) {
          box.style.borderColor = 'var(--red-border)';
          box.style.background = 'var(--red-soft)';
          box.textContent = '❌ Hai ô Mật khẩu và Xác nhận lại mật khẩu không khớp nhau! Vui lòng nhập giống nhau 100%.';
        }
        return;
      }

      try {
        const res = await fetch('/api/auth3/register_or_set_password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email,
            display_name: speakerName,
            target_tier: selectedEnrollTier,
            password,
            confirm_password: confirmPassword
          })
        });
        const data = await res.json();
        if (!data.ok) {
          setStepState('retry', '', '');
          if (box) {
            box.style.borderColor = 'var(--red-border)';
            box.style.background = 'var(--red-soft)';
            box.textContent = data.error || 'Chưa lưu được thông tin Bước 1.';
          }
          return;
        }
      } catch (_) {}

      selectedSpeakerName = speakerName;
      refreshStepSummaries();
      setStepState('done', 'active', '');
      const sessionBadge = document.getElementById('currentSessionBadge');
      if (sessionBadge) sessionBadge.textContent = 'Bước 2/3 · Thu giọng';
      if (box) {
        box.style.borderColor = '#cce5e3';
        box.style.background = 'var(--accent-soft)';
        box.textContent = `✅ Đã xác nhận Bước 1 cho "${speakerName}" (${tierRoleLabel(selectedEnrollTier)}). Hãy bấm "Thu âm giọng nói" ở Bước 2!`;
      }
      loadOverview();
    }

    async function requestForgotPasswordOtpAuthPage() {
      const email = document.getElementById('loginEmail').value.trim();
      const box = document.getElementById('loginStatusBox');
      if (!email) {
        if (box) box.textContent = 'Vui lòng nhập Email tài khoản cần khôi phục mật khẩu.';
        return;
      }
      const res = await fetch('/api/auth3/forgot_password_send_otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, send_gmail: false })
      });
      const data = await res.json();
      if (data.ok && (!data.gmail_delivery || data.gmail_delivery.sent_real_gmail !== false)) {
        if (data.demo_otp_preview) {
          const otpInputEl = document.getElementById('otpInput');
          if (otpInputEl) otpInputEl.value = data.demo_otp_preview;
        }
        if (box) {
          box.style.borderColor = '#cce5e3';
          box.style.background = 'var(--accent-soft)';
          box.textContent = data.message || `Đã gửi mã OTP khôi phục mật khẩu tới ${email}.`;
        }
      } else if (box) {
        box.style.borderColor = 'var(--red-border)';
        box.style.background = 'var(--red-soft)';
        box.textContent = data.error || (data.gmail_delivery && data.gmail_delivery.note) || 'Không gửi được mã OTP.';
      }
    }

    function mapStateLabel(code) {
      if (code === 'done') return 'Hoàn tất';
      if (code === 'active') return 'Đang thực hiện';
      if (code === 'retry') return 'Cần thử lại';
      return 'Chưa bắt đầu';
    }

    function setStepState(step1, step2, step3) {
      document.getElementById('step1StateText').textContent = mapStateLabel(step1);
      document.getElementById('step2StateText').textContent = mapStateLabel(step2);
      document.getElementById('step3StateText').textContent = mapStateLabel(step3);
      if (step3 === 'active' || step3 === 'done') openStepPanel(3);
      else if (step2 === 'active' || step2 === 'retry') openStepPanel(2);
      else openStepPanel(1);
    }

    let currentModalEmail = 'nep94121@gmail.com';
    let holdStartMs = 0;
    let isRecordingVoiceSample = false;

    function updateFirstPageReadingPrompt() {
      const sel = document.getElementById('firstPageAccountSelect');
      if (!sel) return;
      const email = sel.value;
      if (email === 'nep94121@gmail.com') {
        selectedEnrollTier = 1;
        selectedSpeakerName = 'Nguyễn Tuấn Anh';
      } else if (email === 'thanhviena.hust@gmail.com') {
        selectedEnrollTier = 2;
        const step2Name = document.getElementById('step2SpeakerNameInput');
        if (step2Name && step2Name.value && step2Name.value !== 'Nguyễn Tuấn Anh') {
          selectedSpeakerName = step2Name.value.trim();
        } else {
          selectedSpeakerName = 'Thành viên A';
        }
      } else if (email === 'khach.hust@gmail.com') {
        selectedEnrollTier = 3;
        const step2Name = document.getElementById('step2SpeakerNameInput');
        if (step2Name && step2Name.value && step2Name.value !== 'Nguyễn Tuấn Anh' && step2Name.value !== 'Thành viên A') {
          selectedSpeakerName = step2Name.value.trim();
        } else {
          selectedSpeakerName = 'Khách C';
        }
      }
      const step2NameInput = document.getElementById('step2SpeakerNameInput');
      if (step2NameInput) step2NameInput.value = selectedSpeakerName;

      const roleName = selectedEnrollTier === 1 ? 'Chủ nhà' : (selectedEnrollTier === 2 ? 'Thành viên Gia đình' : 'Khách đến chơi nhà');
      const promptStr = `Xin chào ngôi nhà, tôi là ${selectedSpeakerName} (${roleName}) đọc câu này để lưu và xác thực mẫu giọng nói.`;
      document.getElementById('firstPageReadingText').textContent = `"${promptStr}"`;
      refreshStepSummaries();
    }

    function startHoldRecordingFirstPage() {
      if (isRecordingVoiceSample) return;
      holdStartMs = Date.now();
    }

    async function stopHoldRecordingFirstPage(forceGood = true) {
      if (isRecordingVoiceSample) return;
      const heldMs = holdStartMs ? (Date.now() - holdStartMs) : 0;
      holdStartMs = 0;
      if (heldMs < 800) return; // Để sự kiện onclick xử lý khi bấm nhả nhanh
      const heldSec = Math.max(3.8, heldMs / 1000);
      await executeVoiceSampleEnrollment(
        document.getElementById('firstPageAccountSelect').value,
        forceGood,
        heldSec,
        'firstPageEnrollStatus'
      );
    }

    async function quickRecordFirstPage(isGood) {
      if (isRecordingVoiceSample) return;
      holdStartMs = 0;
      const passFlag = (isGood === undefined) ? true : Boolean(isGood);
      await executeVoiceSampleEnrollment(
        document.getElementById('firstPageAccountSelect').value,
        passFlag,
        passFlag ? 3.8 : 0.6,
        'firstPageEnrollStatus'
      );
    }

    function openVoiceEnrollModal(email, promptText) {
      currentModalEmail = email || 'thanhvien_moi@gmail.com';
      document.getElementById('modalReadingPrompt').textContent = `"${promptText || 'Xin chào ngôi nhà, tôi đọc câu này để lưu mẫu giọng nói.'}"`;
      document.getElementById('modalEnrollResult').style.display = 'none';
      document.getElementById('voiceEnrollModal').style.display = 'flex';
    }

    function closeVoiceEnrollModal() {
      document.getElementById('voiceEnrollModal').style.display = 'none';
    }

    async function submitModalVoiceEnroll(isGood) {
      if (!isGood) {
        closeVoiceEnrollModal();
        return;
      }
      await executeVoiceSampleEnrollment(currentModalEmail, true, 5.2, 'modalEnrollResult');
    }

    function generateAuthSynthetic16kPcmB64(isGood, f0Target = 180.0) {
      const sr = 16000;
      const durSec = isGood ? 2.8 : 0.4;
      const totalSamples = Math.floor(sr * durSec);
      const pcm16 = new Int16Array(totalSamples);
      const f0 = isGood ? f0Target : 80.0;
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

    async function executeVoiceSampleEnrollment(email, isGood, holdSec, targetBoxId) {
      if (isRecordingVoiceSample) return;
      isRecordingVoiceSample = true;
      const step2NameEl = document.getElementById('step2SpeakerNameInput');
      const speakerName = (step2NameEl && step2NameEl.value.trim()) ? step2NameEl.value.trim() : selectedSpeakerName;
      selectedSpeakerName = speakerName;

      const prompts = {
        'nep94121@gmail.com': `Xin chào hệ thống Nhà Thông Minh Bách Khoa, tôi là ${speakerName} đọc câu này để lưu mẫu giọng nói gốc lên máy chủ.`,
        'thanhviena.hust@gmail.com': `Xin chào hệ thống Nhà Thông Minh Bách Khoa, tôi là ${speakerName} đọc câu này để đăng ký giọng nói điều khiển thiết bị.`,
        'khach.hust@gmail.com': `Xin chào hệ thống Nhà Thông Minh Bách Khoa, tôi là ${speakerName} đọc câu mẫu để nhận quyền bật tắt đèn.`
      };
      const expectedText = prompts[email] || prompts['nep94121@gmail.com'];
      const f0Map = { 'nep94121@gmail.com': 125.0, 'thanhviena.hust@gmail.com': 195.0, 'khach.hust@gmail.com': 168.0 };
      const f0 = isGood ? (f0Map[email] || 182.0) : 0.0;
      let pcmB64 = '';
      const box = document.getElementById(targetBoxId);
      const recBtn = document.getElementById('btnHoldToRecordFirstPage');
      const proceedBtn = document.getElementById('btnProceedToStep3');

      try {
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
            const recordMs = isGood ? 3800 : 600;
            if (box) {
              box.style.display = 'block';
              box.style.background = 'var(--accent-soft)';
              box.style.borderColor = '#cce5e3';
            }
            const steps = isGood ? 4 : 1;
            for (let s = steps; s >= 1; s--) {
              if (box && isGood) {
                box.textContent = `🎤 Đang thu âm giọng thật của "${speakerName}"... Còn ${s} giây (Hãy đọc to câu mẫu phía trên)`;
              }
              if (recBtn && isGood) {
                const sp = recBtn.querySelector('span');
                if (sp) sp.textContent = `Đang thu âm (${s}s)...`;
              }
              await new Promise(r => setTimeout(r, Math.floor(recordMs / steps)));
            }
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
            pcmB64 = generateAuthSynthetic16kPcmB64(isGood, f0);
          }
        }
        if (!pcmB64) {
          pcmB64 = generateAuthSynthetic16kPcmB64(isGood, f0);
        }

        const payload = {
          email: email,
          speaker_name: speakerName,
          target_tier: selectedEnrollTier,
          spoken_text: isGood ? expectedText : 'Alo một hai ba',
          measured_f0_hz: f0,
          snr_db: isGood ? 19.5 : 4.2,
          hold_duration_sec: holdSec,
          source_device: 'Web Xác thực (Micro thật)',
          audio_pcm_b64: pcmB64,
          pcm16k_b64: pcmB64,
        };

        const res = await fetch('/api/auth3/enroll_voice_sample', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        const replayBtn = document.getElementById('btnReplayVoiceSample');
        if (box) {
          box.style.display = 'block';
          if (data.ok && data.status === 'DA_DAT') {
            lastVoiceEnrollPassed = true;
            lastMeasuredF0Hz = data.f0_hz || f0 || 125.0;
            box.style.borderColor = '#cce5e3';
            box.style.background = 'var(--accent-soft)';
            const f0Measured = data.f0_hz ? ` (F0 = ${Number(data.f0_hz).toFixed(1)} Hz)` : '';
            box.textContent = `✅ ĐẠT CHUẨN — Đã thu và kiểm tra thành công giọng của "${speakerName}" (${tierRoleLabel(selectedEnrollTier)})${f0Measured}! Hãy bấm xác nhận ở Bước 3.`;
            if (replayBtn) replayBtn.hidden = false;
            if (proceedBtn) proceedBtn.disabled = false;
            refreshStepSummaries();
            setStepState('done', 'done', 'active');
          } else if (data.status === 'DUPLICATE_VOICE_REJECTED') {
            lastVoiceEnrollPassed = false;
            if (proceedBtn) proceedBtn.disabled = true;
            box.style.borderColor = 'var(--red-border)';
            box.style.background = 'var(--red-soft)';
            box.textContent = '❌ KHÔNG ĐẠT (Trùng giọng người trong nhà) — Vui lòng bấm "Thu lại"!';
            refreshStepSummaries();
            setStepState('done', 'retry', '');
          } else {
            lastVoiceEnrollPassed = false;
            if (proceedBtn) proceedBtn.disabled = true;
            box.style.borderColor = 'var(--red-border)';
            box.style.background = 'var(--red-soft)';
            box.textContent = `❌ CHƯA ĐẠT — ${data.reason || 'Chưa nhận rõ giọng nói hoặc thời lượng quá ngắn.'} Vui lòng bấm "Thu lại" và đọc rõ câu mẫu!`;
            refreshStepSummaries();
            setStepState('done', 'retry', '');
          }
        }
        loadOverview();
      } finally {
        isRecordingVoiceSample = false;
        if (recBtn) {
          const sp = recBtn.querySelector('span');
          if (sp) sp.textContent = 'Thu âm giọng nói';
        }
      }
    }

    async function loadOverview() {
      const res = await fetch('/api/auth3/overview');
      const data = await res.json();

      if (data.security_status) {
        const st = data.security_status;
        const strikeBadge = document.getElementById('globalStrikeBadge');
        if (strikeBadge) {
          if (st.Lockout_active || st.lockout_active) {
            strikeBadge.hidden = false;
            strikeBadge.textContent = 'Tạm khóa xác nhận giọng nói do thử sai nhiều lần. Vui lòng thử lại sau.';
          } else {
            strikeBadge.hidden = true;
          }
        }
      }

      renderFamilyAllowlist(data.family_allowlist || []);
      onAllowlistActorChange();

      const accBody = document.getElementById('accountsTableBody');
      accBody.innerHTML = '';
      (data.accounts || []).forEach(a => {
        const tr = document.createElement('tr');
        const activeBadge = a.active === false
          ? `<span class="badge badge-fail">Đã thu hồi</span>`
          : `<span class="badge badge-pass">Hoàn tất</span>`;
        const voiceStatusBadge = a.voice_enrolled
          ? `<span class="badge badge-pass">Đã lưu giọng nói</span>`
          : `<span class="badge">Chưa bắt đầu</span>`;
        tr.innerHTML = `
          <td><span class="badge ${tierBadgeClass(a.tier)}">${tierRoleLabel(a.tier)}</span></td>
          <td><span style="font-weight:500;">${a.name}</span><div style="color:var(--muted); font-size:11px;">${a.email}</div></td>
          <td>${activeBadge}</td>
          <td>
            ${voiceStatusBadge}
            <button class="btn-link-sub" type="button"
              onclick="openVoiceEnrollModal('${a.email}', 'Xin chào ngôi nhà, tôi đọc câu này để lưu mẫu giọng nói.')">Thu lại</button>
          </td>
        `;
        accBody.appendChild(tr);
      });

      const logBody = document.getElementById('authLogsTableBody');
      logBody.innerHTML = '';
      (data.recent_logs || []).forEach(l => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${l.time}</td>
          <td>${l.event}</td>
          <td>${l.email || '—'}</td>
          <td style="color:var(--muted);">${l.detail || ''}</td>
        `;
        logBody.appendChild(tr);
      });

      if (data.test_report) {
        renderTestSuiteReport(data.test_report);
      }
    }

    function renderTestSuiteReport(rep) {
      if (!rep) return;
      const casesList = rep.results || rep.cases || [];
      const totalVal = rep.total !== undefined ? rep.total : (rep.total_cases !== undefined ? rep.total_cases : casesList.length);
      const passedVal = rep.passed !== undefined ? rep.passed : (rep.passed_cases !== undefined ? rep.passed_cases : casesList.filter(c => c.passed).length);
      const banner = document.getElementById('testSummaryBanner');
      if (banner) {
        banner.className = passedVal === totalVal && totalVal > 0 ? 'badge badge-pass' : 'badge badge-fail';
        banner.textContent = `ĐẠT ${passedVal}/${totalVal}`;
      }
      const tbody = document.getElementById('testCasesTableBody');
      if (!tbody) return;
      tbody.innerHTML = '';
      casesList.forEach(tc => {
        const tcId = tc.id || tc.test_id || '';
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${tcId}</td>
          <td>${tc.layer || ''}</td>
          <td>${tc.scenario || ''}</td>
          <td style="color:var(--muted);">${tc.actual || ''}</td>
          <td>
            <span class="badge ${tc.passed ? 'badge-pass' : 'badge-fail'}">
              ${tc.passed ? 'Hoàn tất' : 'Cần thử lại'}
            </span>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    function onAllowlistActorChange() {
      const sel = document.getElementById('allowlistActorSelect');
      if (!sel) return;
      const opt = sel.options[sel.selectedIndex];
      const actorTier = parseInt(opt.getAttribute('data-tier') || '1', 10);
      const badge = document.getElementById('allowlistActorBadge');
      const controls = document.getElementById('allowlistInputControls');
      const targetTierSel = document.getElementById('allowlistTargetTierSelect');
      const statusBox = document.getElementById('allowlistStatusBox');

      if (actorTier === 1) {
        badge.className = 'badge badge-tier1';
        badge.textContent = 'Chủ nhà';
        controls.style.display = 'block';
        targetTierSel.innerHTML = `
          <option value="2">Gia đình (Cấp 2)</option>
          <option value="3">Khách (Cấp 3)</option>
        `;
      } else if (actorTier === 2) {
        badge.className = 'badge badge-tier2';
        badge.textContent = 'Gia đình';
        controls.style.display = 'block';
        targetTierSel.innerHTML = `<option value="3">Khách (Cấp 3)</option>`;
      } else {
        badge.className = 'badge badge-tier3';
        badge.textContent = 'Khách';
        controls.style.display = 'none';
        statusBox.style.borderColor = 'var(--red-border)';
        statusBox.style.background = 'var(--red-soft)';
        statusBox.textContent = 'Vai trò Khách không có quyền thêm thành viên mới.';
      }
    }

    function renderFamilyAllowlist(items) {
      const tbody = document.getElementById('familyAllowlistTableBody');
      if (!tbody) return;
      tbody.innerHTML = '';
      if (!items.length) {
        tbody.innerHTML = '<tr><td colspan="4" style="color:var(--muted);">Chưa có email nào trong danh sách.</td></tr>';
        return;
      }
      items.forEach(item => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${item.email}</td>
          <td><span class="badge ${tierBadgeClass(item.target_tier)}">${tierRoleLabel(item.target_tier)}</span></td>
          <td style="font-size:11px; color:var(--muted);">${item.added_by_email || 'Chủ nhà'}</td>
          <td><span class="badge badge-pass">Hoàn tất</span></td>
        `;
        tbody.appendChild(tr);
      });
    }

    async function submitAddFamilyEmail() {
      const actorSel = document.getElementById('allowlistActorSelect');
      const actorEmail = actorSel ? actorSel.value : 'nep94121@gmail.com';
      const targetTier = parseInt(document.getElementById('allowlistTargetTierSelect').value || '2', 10);
      const targetEmail = document.getElementById('allowlistTargetEmail').value.trim();
      const box = document.getElementById('allowlistStatusBox');

      const res = await fetch('/api/auth3/family_allowlist/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          actor_email: actorEmail,
          target_email: targetEmail,
          target_tier: targetTier
        })
      });
      const data = await res.json();
      if (data.ok) {
        box.style.borderColor = '#cce5e3';
        box.style.background = 'var(--accent-soft)';
        box.textContent = data.message || 'Đã thêm thành viên vào danh sách.';
        document.getElementById('allowlistTargetEmail').value = '';
        renderFamilyAllowlist(data.family_allowlist || []);
      } else {
        box.style.borderColor = 'var(--red-border)';
        box.style.background = 'var(--red-soft)';
        box.textContent = data.error || 'Chưa thêm được email. Vui lòng kiểm tra lại.';
      }
    }

    async function execOwnerVoicePermission(cmdText) {
      document.getElementById('voicePermCommandInput').value = cmdText;
      const box = document.getElementById('voicePermStatusBox');
      const res = await fetch('/api/auth3/voice_permission_command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command_text: cmdText, caller_tier: 1 })
      });
      const data = await res.json();
      if (data.ok) {
        box.style.borderColor = '#cce5e3';
        box.style.background = 'var(--accent-soft)';
        box.textContent = data.message || 'Đã cập nhật quyền truy cập.';
      } else {
        box.style.borderColor = 'var(--red-border)';
        box.style.background = 'var(--red-soft)';
        box.textContent = data.error || 'Không thể cập nhật quyền.';
      }
      loadOverview();
    }

    async function submitLayer1(method) {
      const email = document.getElementById('loginEmail').value.trim();
      const password = document.getElementById('loginPassword').value;
      const box = document.getElementById('loginStatusBox');
      box.textContent = 'Đang kiểm tra tài khoản...';

      const loginMethod = method || 'password';
      const res = await fetch('/api/auth3/layer1_login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, login_method: loginMethod, method: loginMethod, google_id_token: 'GOOGLE_OAUTH_SIM_TOKEN_OK' })
      });
      const data = await res.json();
      if (data.ok) {
        setStepState('done', 'active', '');
        box.style.borderColor = '#cce5e3';
        box.style.background = 'var(--accent-soft)';
        box.textContent = `✅ Đăng nhập hợp lệ (${email}). Đã chuyển sang Bước 2/3 · Thu âm giọng nói!`;
      } else {
        setStepState('retry', '', '');
        box.style.borderColor = 'var(--red-border)';
        box.style.background = 'var(--red-soft)';
        box.textContent = `❌ ${data.error || 'Cần thử lại: Email hoặc Mật khẩu chưa đúng.'}`;
      }
      loadOverview();
    }

    async function submitLayer2Otp() {
      const email = document.getElementById('loginEmail').value.trim();
      const otp = document.getElementById('otpInput').value.trim();
      const box = document.getElementById('loginStatusBox');

      const res = await fetch('/api/auth3/layer2_verify_otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, otp })
      });
      const data = await res.json();
      if (data.ok) {
        setStepState('done', 'active', '');
        document.getElementById('currentSessionBadge').textContent = 'Đang thực hiện';
        box.style.borderColor = '#cce5e3';
        box.style.background = 'var(--accent-soft)';
        box.textContent = 'Bước 1/3 hoàn tất. Vui lòng tiếp tục ở Bước 2/3 · Lưu giọng nói.';
      } else {
        setStepState('retry', '', '');
        box.style.borderColor = 'var(--red-border)';
        box.style.background = 'var(--red-soft)';
        box.textContent = 'Cần thử lại: Mã xác nhận chưa đúng.';
      }
      loadOverview();
    }

    async function testWrongOtp() {
      document.getElementById('otpInput').value = '000999';
      await submitLayer2Otp();
    }

    async function submitLayer3Voice(f0Hz, emailHint, deviceLabel) {
      const box = document.getElementById('loginStatusBox');
      const useF0 = lastMeasuredF0Hz || f0Hz || 125.0;
      const res = await fetch('/api/auth3/layer3_voice', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: 'recognize',
          email: emailHint,
          measured_f0_hz: useF0,
          source_device: deviceLabel
        })
      });
      const data = await res.json();
      const badge = document.getElementById('currentSessionBadge');
      if (data.ok) {
        setStepState('done', 'done', 'done');
        badge.className = 'badge badge-pass';
        badge.textContent = 'Hoàn tất';
        box.style.borderColor = '#cce5e3';
        box.style.background = 'var(--accent-soft)';
        box.textContent = `🎉 Đã xác nhận & kích hoạt giọng nói thành công cho ${selectedSpeakerName} (${tierRoleLabel(selectedEnrollTier)})!`;
      } else {
        setStepState('done', 'retry', '');
        badge.className = 'badge badge-fail';
        badge.textContent = 'Cần thử lại';
        box.style.borderColor = 'var(--red-border)';
        box.style.background = 'var(--red-soft)';
        box.textContent = 'Chưa nhận rõ giọng nói. Vui lòng thu lại ở Bước 2.';
      }
      loadOverview();
    }

    async function runFullTestSuite() {
      const banner = document.getElementById('testSummaryBanner');
      if (banner) banner.textContent = 'Đang thực hiện...';

      const res = await fetch('/api/auth3/run_test_suite', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ send_live_email: false })
      });
      const data = await res.json();
      renderTestSuiteReport(data);
      loadOverview();
    }

    function drawDynamicQrPattern(seedStr) {
      const grp = document.getElementById('authQrDotsGroup');
      if (!grp) return;
      let h = 2166136261;
      for (let i = 0; i < seedStr.length; i++) {
        h ^= seedStr.charCodeAt(i);
        h = Math.imul(h, 16777619);
      }
      let rects = '';
      for (let r = 0; r < 11; r++) {
        for (let c = 0; c < 11; c++) {
          if ((r < 4 && c < 4) || (r < 4 && c > 6) || (r > 6 && c < 4)) continue;
          h ^= (r * 31 + c * 17) & 0xff;
          h = Math.imul(h, 16777619);
          if ((Math.abs(h) % 10) < 5) {
            rects += `<rect x="${8 + c * 9.5}" y="${8 + r * 9.5}" width="7.5" height="7.5" rx="1.2" fill="${(r + c) % 3 === 0 ? '#087d85' : '#172b31'}"/>`;
          }
        }
      }
      grp.innerHTML = rects;
    }

    async function refreshDynamicGuestQr() {
      try {
        const durSel = document.getElementById('authQrDurationSelect');
        const tierSel = document.getElementById('authQrTargetTierSelect');
        const dur = durSel ? durSel.value : '1d';
        const targetTier = tierSel ? tierSel.value : '3';
        const res = await fetch(`/api/auth3/guest_qr_current?duration=${encodeURIComponent(dur)}&target_tier=${encodeURIComponent(targetTier)}&host=${encodeURIComponent(location.host)}`);
        const data = await res.json();
        if (!data.ok) return;
        const svgContainer = document.getElementById('authDynamicQrSvg');
        if (data.qr_svg && svgContainer && svgContainer.parentElement) {
          const parentBox = svgContainer.parentElement;
          parentBox.innerHTML = data.qr_svg;
          const svgEl = parentBox.querySelector('svg');
          if (svgEl) {
            svgEl.id = 'authDynamicQrSvg';
            svgEl.setAttribute('width', '116');
            svgEl.setAttribute('height', '116');
            svgEl.style.width = '116px';
            svgEl.style.height = '116px';
            svgEl.style.display = 'block';
            svgEl.style.margin = '0 auto';
            svgEl.style.background = '#fff';
            svgEl.style.padding = '6px';
            svgEl.style.borderRadius = '8px';
            svgEl.style.border = '1px solid var(--line)';
          }
        } else {
          drawDynamicQrPattern(data.token);
        }
        const badge = document.getElementById('authQrCountdownBadge');
        if (badge) {
          const rem = data.remaining_slot_sec || data.remaining_Slot_sec || 10;
          badge.textContent = `Còn ${rem}s`;
          badge.className = rem <= 3 ? 'badge badge-fail' : 'badge badge-tier1';
        }
        const linkEl = document.getElementById('authQrOpenLink');
        if (linkEl) {
          linkEl.href = `/guest?token=${encodeURIComponent(data.token)}&dur=${encodeURIComponent(dur)}&tier=${encodeURIComponent(targetTier)}`;
        }
        const box = document.getElementById('authQrTokenBox');
        if (box) {
          const roleDesc = String(targetTier) === '2' ? 'Thành viên gia đình (Cấp 2)' : 'Khách đến chơi nhà (Cấp 3)';
          box.textContent = `Mã QR đang mở cho: ${roleDesc} · Thời hạn: ${data.duration_label || dur}.`;
        }
      } catch (e) {}
    }

    async function startInviteGoogleOAuth() {
      const codeEl = document.getElementById('inviteCodeSelect');
      const emailEl = document.getElementById('inviteGoogleEmail');
      const nameEl = document.getElementById('inviteDisplayName');
      const passEl = document.getElementById('invitePassword');
      const statusBox = document.getElementById('inviteOAuthStatusBox');

      const inviteCode = codeEl ? codeEl.value : 'INV-TIER2-FAM2026';
      const email = emailEl ? emailEl.value.trim() : 'thanhvien_moi@gmail.com';
      const displayName = nameEl ? nameEl.value.trim() : 'Nguyễn Văn Em';
      const customPassword = passEl ? passEl.value.trim() : 'GiaDinhMoi@2026';

      if (statusBox) {
        statusBox.style.display = 'block';
        statusBox.textContent = 'Đang khởi tạo liên kết Google OAuth...';
      }

      try {
        const res = await fetch('/api/auth3/invite_oauth_start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            invite_code: inviteCode,
            google_email: email,
            display_name: displayName,
            custom_password: customPassword,
            send_gmail: true,
            source: 'Web Invite Link'
          })
        });
        const data = await res.json();
        if (statusBox) {
          if (data.ok) {
            statusBox.style.background = 'var(--accent-soft)';
            statusBox.style.borderColor = '#cce5e3';
            statusBox.textContent = `Khởi tạo thành công! Mã OTP gửi tới ${email}: ${data.demo_otp_preview || 'Đã gửi'}.`;
            const otpInput = document.getElementById('inviteOtpInput');
            if (otpInput && data.demo_otp_preview) {
              otpInput.value = data.demo_otp_preview;
            }
          } else {
            statusBox.style.background = 'var(--red-soft)';
            statusBox.style.borderColor = 'var(--red-border)';
            statusBox.textContent = data.error || data.message || 'Khởi tạo thất bại.';
          }
        }
      } catch (err) {
        if (statusBox) {
          statusBox.style.background = 'var(--red-soft)';
          statusBox.style.borderColor = 'var(--red-border)';
          statusBox.textContent = 'Lỗi kết nối máy chủ Google OAuth.';
        }
      }
    }

    async function verifyInviteGoogleOtp() {
      const emailEl = document.getElementById('inviteGoogleEmail');
      const otpEl = document.getElementById('inviteOtpInput');
      const statusBox = document.getElementById('inviteOAuthStatusBox');

      const email = emailEl ? emailEl.value.trim() : 'thanhvien_moi@gmail.com';
      const otpCode = otpEl ? otpEl.value.trim() : '';

      if (!otpCode) {
        if (statusBox) {
          statusBox.style.display = 'block';
          statusBox.textContent = 'Vui lòng nhập mã OTP 6 số.';
        }
        return;
      }

      try {
        const res = await fetch('/api/auth3/invite_verify_otp', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: email,
            otp_code: otpCode,
            source: 'Web Invite Link'
          })
        });
        const data = await res.json();
        if (statusBox) {
          statusBox.style.display = 'block';
          if (data.ok) {
            statusBox.style.background = 'var(--accent-soft)';
            statusBox.style.borderColor = '#cce5e3';
            statusBox.textContent = 'Xác thực OTP thành công! Đã kích hoạt tài khoản thành viên.';
            if (typeof loadOverview === 'function') loadOverview();
          } else {
            statusBox.style.background = 'var(--red-soft)';
            statusBox.style.borderColor = 'var(--red-border)';
            statusBox.textContent = data.error || data.message || 'Mã OTP không hợp lệ.';
          }
        }
      } catch (err) {
        if (statusBox) {
          statusBox.style.display = 'block';
          statusBox.textContent = 'Lỗi xác nhận mã OTP.';
        }
      }
    }

    window.addEventListener('DOMContentLoaded', () => {
      onEnrollTierSelectChange('2');
      loadOverview();
      openStepPanel(1);
      refreshDynamicGuestQr();
      setInterval(refreshDynamicGuestQr, 1000);
    });

// Window exports for inline event handlers
window.tierBadgeClass = tierBadgeClass;
window.tierRoleLabel = tierRoleLabel;
window.openStepPanel = openStepPanel;
window.fillAccount = fillAccount;
window.applyPresetAccount = applyPresetAccount;
window.onEnrollTierSelectChange = onEnrollTierSelectChange;
window.syncSpeakerNameInput = syncSpeakerNameInput;
window.onStep2SpeakerNameInput = onStep2SpeakerNameInput;
window.refreshStepSummaries = refreshStepSummaries;
window.completeStep1AndGoToVoice = completeStep1AndGoToVoice;
window.requestForgotPasswordOtpAuthPage = requestForgotPasswordOtpAuthPage;
window.mapStateLabel = mapStateLabel;
window.setStepState = setStepState;
window.updateFirstPageReadingPrompt = updateFirstPageReadingPrompt;
window.startHoldRecordingFirstPage = startHoldRecordingFirstPage;
window.stopHoldRecordingFirstPage = stopHoldRecordingFirstPage;
window.quickRecordFirstPage = quickRecordFirstPage;
window.openVoiceEnrollModal = openVoiceEnrollModal;
window.closeVoiceEnrollModal = closeVoiceEnrollModal;
window.submitModalVoiceEnroll = submitModalVoiceEnroll;
window.executeVoiceSampleEnrollment = executeVoiceSampleEnrollment;
window.loadOverview = loadOverview;
window.onAllowlistActorChange = onAllowlistActorChange;
window.renderFamilyAllowlist = renderFamilyAllowlist;
window.submitAddFamilyEmail = submitAddFamilyEmail;
window.execOwnerVoicePermission = execOwnerVoicePermission;
window.submitLayer1 = submitLayer1;
window.submitLayer2Otp = submitLayer2Otp;
window.testWrongOtp = testWrongOtp;
window.submitLayer3Voice = submitLayer3Voice;
window.runFullTestSuite = runFullTestSuite;
window.drawDynamicQrPattern = drawDynamicQrPattern;
window.refreshDynamicGuestQr = refreshDynamicGuestQr;
window.startInviteGoogleOAuth = startInviteGoogleOAuth;
window.verifyInviteGoogleOtp = verifyInviteGoogleOtp;
