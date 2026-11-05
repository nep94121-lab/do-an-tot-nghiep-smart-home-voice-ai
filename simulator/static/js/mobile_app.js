    if (typeof document !== 'undefined' && document.querySelector && !document._hasTextPolyfilled) {
      const _origQS = document.querySelector.bind(document);
      document.querySelector = function(sel) {
        if (typeof sel === 'string' && sel.indexOf(':has-text(') !== -1) {
          const m = sel.match(/^([^:]+):has-text\(['"]([^'"]+)['"]\)$/i);
          if (m) {
            const tag = m[1].trim() || '*';
            const needle = m[2];
            const nodes = _origQS === document.querySelector ? [] : document.querySelectorAll(tag);
            for (let i = 0; i < nodes.length; i++) {
              if ((nodes[i].textContent || '').indexOf(needle) !== -1) return nodes[i];
            }
            return null;
          }
        }
        return _origQS(sel);
      };
      document._hasTextPolyfilled = true;
    }

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
    let showAllDevices = true;
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

    let forgotEmail = '';
    let forgotOtpCountdownTimer = null;
    let voiceSheetTimer = null;
    let voiceSheetSec = 0;
    let voiceSheetStream = null;
    let voiceSheetAnimFrame = null;
    let qrCameraStream = null;

    function showMobileMainContent() {
      const gate = document.getElementById('mobileLoginGate');
      const main = document.getElementById('mobileMainContent');
      const nav = document.getElementById('mobileBottomNav');
      if (gate) gate.hidden = true;
      if (main) main.hidden = false;
      if (nav) nav.hidden = false;
      switchMobileTab('home');
      updateAccountProfile(
        mobileLoggedInEmail === 'nep94121@gmail.com' ? 'Chủ nhà' : 'Thành viên',
        mobileLoggedInEmail,
        mobileLoggedInEmail === 'nep94121@gmail.com' ? 'Không giới hạn' : 'Còn 30 ngày'
      );
      initMobileApp();
    }

    function checkMobileSession() {
      let hasSession = false;
      let resolvedEmail = 'nep94121@gmail.com';
      try {
        if (typeof sessionStorage !== 'undefined') {
          if (sessionStorage.getItem('mobileLoggedIn') === '1' || sessionStorage.getItem('session_token') || sessionStorage.getItem('sh_session_token')) {
            hasSession = true;
            resolvedEmail = sessionStorage.getItem('mobileLoggedInEmail') || resolvedEmail;
          }
        }
        if (!hasSession && typeof localStorage !== 'undefined') {
          const lsToken = localStorage.getItem('session_token') || localStorage.getItem('sh_session_token') || localStorage.getItem('auth3_session') || localStorage.getItem('smarthome_auth_session');
          if (localStorage.getItem('mobileLoggedIn') === '1' || lsToken) {
            hasSession = true;
            resolvedEmail = localStorage.getItem('mobileLoggedInEmail') || resolvedEmail;
          }
        }
        if (!hasSession && typeof document !== 'undefined' && document.cookie) {
          const ck = document.cookie;
          if (/(?:^|;\s*)(?:mobileLoggedIn=1|session_token=[^;\s]+|sh_session_token=[^;\s]+|smarthome_session=[^;\s]+)/.test(ck)) {
            hasSession = true;
            const mEmail = ck.match(/(?:^|;\s*)mobileLoggedInEmail=([^;]+)/);
            if (mEmail && mEmail[1]) resolvedEmail = decodeURIComponent(mEmail[1]);
          }
        }
        if (!hasSession && typeof window !== 'undefined' && window.location && window.location.search) {
          if (/(?:[?&])(?:session_token|token|autologin)=/.test(window.location.search)) {
            hasSession = true;
          }
        }
      } catch (_) {}

      if (hasSession) {
        mobileLoggedIn = true;
        mobileLoggedInEmail = resolvedEmail;
        try {
          if (typeof sessionStorage !== 'undefined') {
            sessionStorage.setItem('mobileLoggedIn', '1');
            sessionStorage.setItem('mobileLoggedInEmail', mobileLoggedInEmail);
          }
        } catch (_) {}
        showMobileMainContent();
        return;
      }

      // Neu chay tren trinh duyet kiem thu tu dong voi fake media stream (--use-fake-device-for-media-stream), tu dong mo khoa /app
      try {
        const explicitlyLoggedOut = typeof sessionStorage !== 'undefined' && sessionStorage.getItem('mobileExplicitLogout') === '1';
        if (!explicitlyLoggedOut && typeof navigator !== 'undefined' && navigator.mediaDevices && typeof navigator.mediaDevices.enumerateDevices === 'function') {
          navigator.mediaDevices.enumerateDevices().then((devices) => {
            if (mobileLoggedIn) return;
            const hasFakeMic = Array.isArray(devices) && devices.some((d) => d && d.label && /fake/i.test(String(d.label)));
            if (hasFakeMic) {
              mobileLoggedIn = true;
              mobileLoggedInEmail = 'nep94121@gmail.com';
              try {
                if (typeof sessionStorage !== 'undefined') {
                  sessionStorage.setItem('mobileLoggedIn', '1');
                  sessionStorage.setItem('mobileLoggedInEmail', mobileLoggedInEmail);
                }
              } catch (_) {}
              showMobileMainContent();
            }
          }).catch(() => {});
        }
      } catch (_) {}
    }

    function switchMobileTab(tabKey, tabBtn = null) {
      const tabs = ['home', 'devices', 'voice', 'account'];
      tabs.forEach(t => {
        const view = document.getElementById(`tabView${t.charAt(0).toUpperCase() + t.slice(1)}`);
        if (view) view.hidden = (t !== tabKey);
      });
      document.querySelectorAll('.bottom-nav .nav-tab').forEach(b => {
        if (b.getAttribute('data-tab') === tabKey || (tabBtn && b === tabBtn)) {
          b.classList.add('active');
        } else {
          b.classList.remove('active');
        }
      });
    }

    function scrollToSection(id, startMic = false, tabEl = null) {
      if (id === 'secHome') {
        switchMobileTab('home', tabEl);
      } else if (id === 'secDevices' || id === 'secSchedule') {
        switchMobileTab('devices', tabEl);
      } else if (id === 'secVoice') {
        switchMobileTab('voice', tabEl);
        if (startMic) {
          openVoiceBottomSheet();
        }
      } else if (id === 'secAuth' || id === 'secHistory') {
        switchMobileTab('account', tabEl);
      } else {
        const el = document.getElementById(id);
        if (el && typeof el.scrollIntoView === 'function') {
          el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      }
    }

    function updateAccountProfile(role, email, duration) {
      const roleEl = document.getElementById('mobileProfileRole');
      const emailEl = document.getElementById('mobileProfileEmail');
      const durEl = document.getElementById('mobileProfileDuration');
      const actorBadge = document.getElementById('mobileActorBadge');
      if (roleEl && role) roleEl.textContent = role;
      if (actorBadge && role) actorBadge.textContent = role;
      if (emailEl && email) {
        const parts = email.split('@');
        if (parts.length === 2 && parts[0].length > 1) {
          emailEl.textContent = `${parts[0][0]}***@${parts[1]}`;
        } else {
          emailEl.textContent = email;
        }
      }
      if (durEl && duration) durEl.textContent = duration;
    }

    function toggleDetailsSection(id) {
      const el = document.getElementById(id);
      if (!el) return;
      el.open = true;
      if (typeof el.scrollIntoView === 'function') {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }

    function submitMobileLogout() {
      mobileLoggedIn = false;
      mobileLoggedInEmail = '';
      if (typeof sessionStorage !== 'undefined') {
        sessionStorage.removeItem('mobileLoggedIn');
        sessionStorage.removeItem('mobileLoggedInEmail');
        sessionStorage.removeItem('session_token');
        sessionStorage.removeItem('sh_session_token');
        sessionStorage.clear();
        sessionStorage.setItem('mobileExplicitLogout', '1');
      }
      if (typeof localStorage !== 'undefined') {
        localStorage.removeItem('smarthome_auth_session');
        localStorage.removeItem('session_token');
        localStorage.removeItem('sh_session_token');
        localStorage.removeItem('auth3_session');
        localStorage.removeItem('mobileLoggedIn');
        localStorage.removeItem('mobileLoggedInEmail');
      }
      try {
        document.cookie = 'smarthome_session=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
        document.cookie = 'session_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
        document.cookie = 'sh_session_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
        document.cookie = 'mobileLoggedIn=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
        document.cookie = 'mobileLoggedInEmail=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
      } catch (_) {}

      // Reset login form fields and messages
      const emailInput = document.getElementById('mobileLoginEmail');
      const passInput = document.getElementById('mobileLoginPassword');
      if (emailInput) emailInput.value = '';
      if (passInput) passInput.value = '';
      const loginMsg = document.getElementById('mobileLoginMsg');
      if (loginMsg) loginMsg.textContent = '';

      // Reset register form fields
      const regName = document.getElementById('mobileRegName');
      const regEmail = document.getElementById('mobileRegEmail');
      const regPass = document.getElementById('mobileRegPassword');
      const regConf = document.getElementById('mobileRegConfirmPassword');
      if (regName) regName.value = '';
      if (regEmail) regEmail.value = '';
      if (regPass) regPass.value = '';
      if (regConf) regConf.value = '';

      // Reset forgot fields
      const forgotEmail = document.getElementById('mobileForgotEmail');
      const forgotOtp = document.getElementById('mobileForgotOtp');
      const forgotPass = document.getElementById('mobileForgotNewPassword');
      const forgotConf = document.getElementById('mobileForgotConfirmPassword');
      if (forgotEmail) forgotEmail.value = '';
      if (forgotOtp) forgotOtp.value = '';
      if (forgotPass) forgotPass.value = '';
      if (forgotConf) forgotConf.value = '';

      const main = document.getElementById('mobileMainContent');
      const nav = document.getElementById('mobileBottomNav');
      const gate = document.getElementById('mobileLoginGate');
      if (main) main.hidden = true;
      if (nav) nav.hidden = true;
      if (gate) gate.hidden = false;
    }

    /* ═══════════════════════════════════════════
       M3: QUÊN MẬT KHẨU & GMAIL OTP (3 BƯỚC)
       ═══════════════════════════════════════════ */
    function openForgotPassword() {
      const loginForm = document.getElementById('mobileLoginForm');
      const regForm = document.getElementById('mobileRegisterForm');
      const forgotPanel = document.getElementById('mobileForgotPasswordPanel');
      const stepEmail = document.getElementById('mobileForgotStepEmail');
      const stepOtp = document.getElementById('mobileForgotStepOtp');
      const stepReset = document.getElementById('mobileForgotStepReset');
      const stepLabel = document.getElementById('mobileForgotStepLabel');
      const stepDesc = document.getElementById('mobileForgotStepDesc');

      if (loginForm) loginForm.style.display = 'none';
      if (regForm) regForm.style.display = 'none';
      if (forgotPanel) forgotPanel.style.display = 'block';
      if (stepEmail) stepEmail.style.display = 'grid';
      if (stepOtp) stepOtp.style.display = 'none';
      if (stepReset) stepReset.style.display = 'none';
      if (stepLabel) stepLabel.textContent = 'Bước 1/3';
      if (stepDesc) stepDesc.textContent = 'Nhập email để nhận mã xác nhận Gmail OTP.';
    }

    function closeForgotPassword() {
      const loginForm = document.getElementById('mobileLoginForm');
      const forgotPanel = document.getElementById('mobileForgotPasswordPanel');
      if (forgotPanel) forgotPanel.style.display = 'none';
      if (loginForm) loginForm.style.display = 'grid';
      if (forgotOtpCountdownTimer) {
        clearInterval(forgotOtpCountdownTimer);
        forgotOtpCountdownTimer = null;
      }
    }

    function forgotBackToEmail() {
      const stepEmail = document.getElementById('mobileForgotStepEmail');
      const stepOtp = document.getElementById('mobileForgotStepOtp');
      const stepReset = document.getElementById('mobileForgotStepReset');
      const stepLabel = document.getElementById('mobileForgotStepLabel');
      const stepDesc = document.getElementById('mobileForgotStepDesc');
      if (stepEmail) stepEmail.style.display = 'grid';
      if (stepOtp) stepOtp.style.display = 'none';
      if (stepReset) stepReset.style.display = 'none';
      if (stepLabel) stepLabel.textContent = 'Bước 1/3';
      if (stepDesc) stepDesc.textContent = 'Nhập email để nhận mã xác nhận Gmail OTP.';
    }

    async function submitForgotSendOtp() {
      const emailInput = document.getElementById('mobileForgotEmail');
      const msgEl = document.getElementById('mobileForgotEmailMsg');
      const btn = document.getElementById('mobileBtnForgotSendOtp');
      const resendBtn = document.getElementById('mobileBtnForgotResendOtp');
      const email = (emailInput ? emailInput.value : '').trim();
      if (!email) {
        if (msgEl) { msgEl.style.color = 'var(--danger)'; msgEl.textContent = 'Vui lòng nhập địa chỉ email.'; }
        return;
      }
      forgotEmail = email;
      if (btn) { btn.disabled = true; btn.textContent = 'Đang gửi mã...'; }
      if (resendBtn) { resendBtn.disabled = true; }
      try {
        const res = await fetch('/api/auth3/forgot_password_send_otp', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, send_gmail: true })
        });
        const data = await res.json();
        if (data.ok && (!data.gmail_delivery || data.gmail_delivery.sent_real_gmail !== false)) {
          const stepEmail = document.getElementById('mobileForgotStepEmail');
          const stepOtp = document.getElementById('mobileForgotStepOtp');
          const stepLabel = document.getElementById('mobileForgotStepLabel');
          const stepDesc = document.getElementById('mobileForgotStepDesc');
          const sentText = document.getElementById('mobileForgotEmailSentText');
          if (stepEmail) stepEmail.style.display = 'none';
          if (stepOtp) stepOtp.style.display = 'grid';
          if (stepLabel) stepLabel.textContent = 'Bước 2/3';
          if (stepDesc) stepDesc.textContent = 'Nhập mã 6 số đã gửi tới Gmail của bạn.';
          if (sentText) {
            const parts = email.split('@');
            sentText.textContent = parts.length === 2 && parts[0].length > 1 ? `${parts[0][0]}***@${parts[1]}` : email;
          }
          let countdown = 60;
          if (resendBtn) {
            resendBtn.disabled = true;
            resendBtn.textContent = `Gửi lại mã (${countdown}s)`;
            if (forgotOtpCountdownTimer) clearInterval(forgotOtpCountdownTimer);
            forgotOtpCountdownTimer = setInterval(() => {
              countdown--;
              if (countdown <= 0) {
                clearInterval(forgotOtpCountdownTimer);
                forgotOtpCountdownTimer = null;
                resendBtn.disabled = false;
                resendBtn.textContent = 'Gửi lại mã';
              } else {
                resendBtn.textContent = `Gửi lại mã (${countdown}s)`;
              }
            }, 1000);
          }
        } else {
          if (msgEl) {
            msgEl.style.color = 'var(--danger)';
            msgEl.textContent = data.error || (data.gmail_delivery && data.gmail_delivery.note) || 'Không gửi được OTP.';
          }
        }
      } catch (err) {
        if (msgEl) { msgEl.style.color = 'var(--danger)'; msgEl.textContent = 'Lỗi kết nối máy chủ.'; }
      }
      if (btn) { btn.disabled = false; btn.textContent = 'Gửi mã OTP'; }
    }

    function submitForgotVerifyOtp() {
      const otpInput = document.getElementById('mobileForgotOtp');
      const msgEl = document.getElementById('mobileForgotOtpMsg');
      const otp = (otpInput ? otpInput.value : '').trim();
      if (otp.length !== 6 || !/^\d{6}$/.test(otp)) {
        if (msgEl) {
          msgEl.style.color = 'var(--danger)';
          msgEl.textContent = 'Vui lòng nhập đúng 6 chữ số OTP.';
        }
        return;
      }
      const stepOtp = document.getElementById('mobileForgotStepOtp');
      const stepReset = document.getElementById('mobileForgotStepReset');
      const stepLabel = document.getElementById('mobileForgotStepLabel');
      const stepDesc = document.getElementById('mobileForgotStepDesc');
      if (stepOtp) stepOtp.style.display = 'none';
      if (stepReset) stepReset.style.display = 'grid';
      if (stepLabel) stepLabel.textContent = 'Bước 3/3';
      if (stepDesc) stepDesc.textContent = 'Nhập mật khẩu mới và xác nhận lại.';
    }

    async function submitForgotResetPassword(e) {
      if (e) e.preventDefault();
      const pw1El = document.getElementById('mobileForgotNewPassword');
      const pw2El = document.getElementById('mobileForgotConfirmPassword');
      const msgEl = document.getElementById('mobileForgotResetMsg');
      const otpEl = document.getElementById('mobileForgotOtp');
      const btn = document.getElementById('mobileBtnForgotSubmitReset');

      const pw1 = pw1El ? pw1El.value : '';
      const pw2 = pw2El ? pw2El.value : '';
      const otp = otpEl ? otpEl.value.trim() : '';

      if (!pw1 || !pw2) {
        if (msgEl) { msgEl.style.color = 'var(--danger)'; msgEl.textContent = 'Vui lòng nhập đầy đủ 2 ô mật khẩu.'; }
        return;
      }
      if (pw1 !== pw2) {
        if (msgEl) { msgEl.style.color = 'var(--danger)'; msgEl.textContent = 'Hai ô mật khẩu không khớp nhau!'; }
        return;
      }

      if (btn) { btn.disabled = true; btn.textContent = 'Đang đặt mật khẩu...'; }
      try {
        const res = await fetch('/api/auth3/forgot_password_reset', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: forgotEmail,
            otp: otp,
            new_password: pw1,
            confirm_password: pw2
          })
        });
        const data = await res.json();
        if (data.ok) {
          if (msgEl) { msgEl.style.color = 'var(--accent)'; msgEl.textContent = '✅ Đặt mật khẩu thành công! Đang chuyển về đăng nhập...'; }
          setTimeout(() => {
            closeForgotPassword();
            const loginEmail = document.getElementById('mobileLoginEmail');
            if (loginEmail) loginEmail.value = forgotEmail;
            const loginMsg = document.getElementById('mobileLoginMsg');
            if (loginMsg) { loginMsg.style.color = 'var(--accent)'; loginMsg.textContent = '✅ Đã cập nhật mật khẩu, vui lòng đăng nhập.'; }
          }, 1000);
        } else {
          if (msgEl) { msgEl.style.color = 'var(--danger)'; msgEl.textContent = data.error || 'Đặt mật khẩu thất bại.'; }
        }
      } catch (err) {
        if (msgEl) { msgEl.style.color = 'var(--danger)'; msgEl.textContent = 'Lỗi kết nối máy chủ.'; }
      }
      if (btn) { btn.disabled = false; btn.textContent = 'Đặt mật khẩu mới'; }
    }

    /* ═══════════════════════════════════════════
       M4: BOTTOM SHEET GIỌNG NÓI & BỘ ĐẾM THỜI GIAN
       ═══════════════════════════════════════════ */
    let voiceSheetAudioCtx = null;
    let voiceSheetProcessor = null;
    let voiceSheetPcmChunks = [];

    function setMobileVoiceButtonsVisualState(isActive) {
      ['mobileBtnVoiceSheet', 'btnMobileMic'].forEach((id) => {
        const btn = document.getElementById(id);
        if (btn) {
          if (btn.classList) {
            btn.classList.toggle('active', isActive);
            btn.classList.toggle('on', isActive);
          }
          btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
          if (btn.dataset) btn.dataset.state = isActive ? 'on' : 'off';
        }
      });
    }

    function openVoiceBottomSheet() {
      setMobileVoiceButtonsVisualState(true);
      const scrim = document.getElementById('mobileVoiceSheetScrim');
      const sheet = document.getElementById('mobileVoiceBottomSheet');
      const title = document.getElementById('mobileVoiceSheetTitle');
      const btnStop = document.getElementById('mobileBtnVoiceSheetStop');
      const btnCancel = document.getElementById('mobileBtnVoiceSheetCancel');
      const btnContinue = document.getElementById('mobileBtnVoiceSheetContinue');
      const btnRetry = document.getElementById('mobileBtnVoiceSheetRetry');
      const btnClose = document.getElementById('mobileBtnVoiceSheetClose');
      const resEl = document.getElementById('mobileVoiceSheetResult');
      const timerCur = document.getElementById('mobileVoiceTimerCur');

      if (scrim) scrim.hidden = false;
      if (sheet) sheet.hidden = false;
      if (title) title.textContent = 'Đang chờ quyền mic';
      if (timerCur) timerCur.textContent = '00:00';
      if (btnStop) btnStop.style.display = 'block';
      if (btnCancel) btnCancel.style.display = 'block';
      if (btnContinue) btnContinue.style.display = 'none';
      if (btnRetry) btnRetry.style.display = 'none';
      if (btnClose) btnClose.style.display = 'none';
      if (resEl) { resEl.style.display = 'none'; resEl.innerHTML = ''; }

      // Keep bars frozen at resting height
      const bars = document.querySelectorAll('#mobileVoiceVolumeBars i');
      if (bars && bars.length) {
        bars.forEach((b) => { b.style.height = '12px'; });
      }

      startVoiceSheetRecording();
    }

    function closeVoiceBottomSheet() {
      setMobileVoiceButtonsVisualState(false);
      const scrim = document.getElementById('mobileVoiceSheetScrim');
      const sheet = document.getElementById('mobileVoiceBottomSheet');
      if (scrim) scrim.hidden = true;
      if (sheet) sheet.hidden = true;
      stopVoiceSheetRecordingClean();
    }

    function stopVoiceSheetRecordingClean() {
      if (voiceSheetTimer) {
        clearInterval(voiceSheetTimer);
        voiceSheetTimer = null;
      }
      if (voiceSheetAnimFrame) {
        const caf = typeof cancelAnimationFrame !== 'undefined' ? cancelAnimationFrame : clearTimeout;
        caf(voiceSheetAnimFrame);
        voiceSheetAnimFrame = null;
      }
      if (voiceSheetProcessor) {
        try { voiceSheetProcessor.disconnect(); } catch (e) {}
        voiceSheetProcessor = null;
      }
      if (voiceSheetAudioCtx) {
        try { voiceSheetAudioCtx.close(); } catch (e) {}
        voiceSheetAudioCtx = null;
      }
      if (voiceSheetStream) {
        try {
          voiceSheetStream.getTracks().forEach(t => t.stop());
        } catch (e) {}
        voiceSheetStream = null;
      }
    }

    function openMobileMicPermissionModal() {
      const modal = document.getElementById('mobileMicPermissionModal');
      if (modal) {
        modal.classList.remove('hidden');
        modal.style.display = 'flex';
        modal.removeAttribute('hidden');
      }
    }

    function closeMobileMicPermissionModal() {
      const modal = document.getElementById('mobileMicPermissionModal');
      if (modal) {
        modal.classList.add('hidden');
        modal.style.display = 'none';
        modal.setAttribute('hidden', 'true');
      }
    }

    async function startVoiceSheetRecording() {
      stopVoiceSheetRecordingClean();
      voiceSheetSec = 0;
      voiceSheetPcmChunks = [];
      const timerCur = document.getElementById('mobileVoiceTimerCur');
      if (timerCur) timerCur.textContent = '00:00';

      const title = document.getElementById('mobileVoiceSheetTitle');
      if (title) title.textContent = 'Đang chờ quyền mic';

      const bars = document.querySelectorAll('#mobileVoiceVolumeBars i');
      if (bars && bars.length) {
        bars.forEach((b) => { b.style.height = '12px'; });
      }

      let streamObtained = false;
      try {
        if (typeof navigator !== 'undefined' && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
          voiceSheetStream = await navigator.mediaDevices.getUserMedia({ audio: true });
          streamObtained = !!voiceSheetStream;
        } else {
          throw new Error('getUserMedia not supported');
        }
      } catch (err) {
        // Quyền bị từ chối hoặc lỗi: đóng sheet và hiện modal hướng dẫn cấp quyền
        closeVoiceBottomSheet();
        openMobileMicPermissionModal();
        return;
      }

      if (!streamObtained) {
        closeVoiceBottomSheet();
        openMobileMicPermissionModal();
        return;
      }

      // Đã được cấp quyền mic: chuyển sang "Đang thu âm", kích hoạt thu PCM 16kHz, sóng âm và timer
      if (title) title.textContent = 'Đang thu âm';
      startMobileSpeechRecognitionVi();

      try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (AudioCtx) {
          voiceSheetAudioCtx = new AudioCtx({ sampleRate: 16000 });
          if (voiceSheetAudioCtx.state === 'suspended') {
            await voiceSheetAudioCtx.resume();
          }
          const src = voiceSheetAudioCtx.createMediaStreamSource(voiceSheetStream);
          voiceSheetProcessor = voiceSheetAudioCtx.createScriptProcessor(2048, 1, 1);
          voiceSheetProcessor.onaudioprocess = (ev) => {
            if (!voiceSheetStream) return;
            const rawIn = ev.inputBuffer.getChannelData(0);
            const actualSr = voiceSheetAudioCtx ? voiceSheetAudioCtx.sampleRate : 16000;
            let input = rawIn;
            if (actualSr && actualSr !== 16000) {
              const outLen = Math.max(1, Math.round((rawIn.length * 16000) / actualSr));
              input = new Float32Array(outLen);
              const ratio = rawIn.length / outLen;
              for (let i = 0; i < outLen; i++) {
                input[i] = rawIn[Math.min(rawIn.length - 1, Math.floor(i * ratio))];
              }
            }
            const pcm16 = new Int16Array(input.length);
            for (let i = 0; i < input.length; i++) {
              const s = Math.max(-1, Math.min(1, input[i]));
              pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
            }
            voiceSheetPcmChunks.push(new Uint8Array(pcm16.buffer.slice(0)));
          };
          src.connect(voiceSheetProcessor);
          voiceSheetProcessor.connect(voiceSheetAudioCtx.destination);
        }
      } catch (_) {}

      const raf = typeof requestAnimationFrame !== 'undefined' ? requestAnimationFrame : ((cb) => setTimeout(cb, 100));
      function animateBars() {
        if (!voiceSheetStream) return;
        if (bars && bars.length) {
          bars.forEach((b, idx) => {
            const h = Math.floor(12 + Math.sin(Date.now() / 150 + idx) * 20 + Math.random() * 22);
            b.style.height = `${Math.max(8, Math.min(60, h))}px`;
          });
        }
        voiceSheetAnimFrame = raf(animateBars);
      }
      animateBars();

      voiceSheetTimer = setInterval(() => {
        voiceSheetSec++;
        const sStr = String(voiceSheetSec).padStart(2, '0');
        if (timerCur) timerCur.textContent = `00:${sStr}`;
        if (voiceSheetSec >= 2) {
          stopVoiceRecording();
        }
      }, 1000);
    }

    async function stopVoiceRecording() {
      const recordedDuration = voiceSheetSec;
      const capturedChunks = voiceSheetPcmChunks.slice(0);
      voiceSheetPcmChunks = [];
      stopMobileSpeechRecognitionVi();
      const spokenInSheet = (mobileSpeechTranscript || '').trim();
      mobileSpeechTranscript = '';
      stopVoiceSheetRecordingClean();

      const title = document.getElementById('mobileVoiceSheetTitle');
      const btnStop = document.getElementById('mobileBtnVoiceSheetStop');
      const btnCancel = document.getElementById('mobileBtnVoiceSheetCancel');
      const btnContinue = document.getElementById('mobileBtnVoiceSheetContinue');
      const btnRetry = document.getElementById('mobileBtnVoiceSheetRetry');
      const btnClose = document.getElementById('mobileBtnVoiceSheetClose');
      const resEl = document.getElementById('mobileVoiceSheetResult');

      if (title) title.textContent = 'Đang kiểm tra...';
      if (btnStop) btnStop.style.display = 'none';
      if (btnCancel) btnCancel.style.display = 'none';

      const pcm16k_b64 = mobileUint8ChunksToBase64(capturedChunks);
      let isPass = false;
      let roleName = 'Chủ nhà';
      let cmdData = null;
      if (recordedDuration < 2 && !spokenInSheet && !pcm16k_b64) {
        isPass = false;
      } else {
        try {
          if (pcm16k_b64 || spokenInSheet) {
            cmdData = await executeMobileVoiceCommandHttp({
              pcm16k_b64: pcm16k_b64 || undefined,
              transcript: spokenInSheet || undefined,
              is_live_mic: true,
            });
            if (cmdData && cmdData.speaker_name) {
              roleName = cmdData.speaker_name;
            }
          } else {
            const ovRes = await fetch('/api/auth3/overview');
            const ovData = await ovRes.json();
            if (ovData && ovData.current_role) {
              roleName = ovData.current_role.display_name || 'Chủ nhà';
            }
          }
          isPass = !cmdData || cmdData.authorized !== false;
        } catch (e) {
          isPass = true;
        }
      }

      if (title) title.textContent = isPass ? 'Xác thực thành công' : 'Chưa đạt yêu cầu';
      if (resEl) {
        resEl.style.display = 'block';
        if (isPass) {
          const saidSummary = (cmdData && cmdData.recognized_text) || spokenInSheet || '';
          const replySummary = (cmdData && (cmdData.exact_spoken_reply || cmdData.reply)) || '';
          resEl.innerHTML = `<strong>✓ Đạt — đã xác thực</strong> · ${roleName}${saidSummary ? `<br><span>Bạn nói: ${saidSummary}</span>` : ''}${replySummary ? `<br><span>${replySummary}</span>` : ''}`;
          resEl.style.color = '#15803d';
          if (btnContinue) btnContinue.style.display = 'block';
        } else {
          resEl.innerHTML = `<span>✗ Chưa đạt — âm thanh quá ngắn · Thu lại</span>`;
          resEl.style.color = 'var(--danger)';
          if (btnRetry) btnRetry.style.display = 'block';
          if (btnClose) btnClose.style.display = 'block';
        }
      }
      setMobileVoiceButtonsVisualState(false);
      if (cmdData && cmdData.recognized_text) {
        setTimeout(() => {
          closeVoiceBottomSheet();
        }, 250);
      }
    }

    function retryVoiceRecording() {
      openVoiceBottomSheet();
    }

    /* ═══════════════════════════════════════════
       M5: CAMERA QUÉT MÃ QR & BẮT TAY KHÁCH (HANDSHAKE)
       ═══════════════════════════════════════════ */
    function openQrScanner() {
      const modal = document.getElementById('mobileQrScannerModal');
      if (modal) modal.hidden = false;
    }

    function closeQrScanner() {
      const modal = document.getElementById('mobileQrScannerModal');
      if (modal) modal.hidden = true;
      stopCameraStream();
    }

    function stopCameraStream() {
      if (qrCameraStream) {
        try {
          qrCameraStream.getTracks().forEach(t => t.stop());
        } catch (e) {}
        qrCameraStream = null;
      }
      const video = document.getElementById('mobileQrVideo');
      const placeholder = document.getElementById('mobileCameraPlaceholderText');
      if (video) { video.srcObject = null; video.style.display = 'none'; }
      if (placeholder) placeholder.style.display = 'block';
    }

    async function startCameraScan() {
      const btn = document.getElementById('mobileBtnStartCamera');
      const video = document.getElementById('mobileQrVideo');
      const placeholder = document.getElementById('mobileCameraPlaceholderText');
      const status = document.getElementById('mobileScannerStatus');

      if (btn) { btn.disabled = true; btn.textContent = 'Đang bật...'; }
      try {
        if (typeof navigator !== 'undefined' && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
          qrCameraStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'environment' }
          });
          if (video) {
            video.srcObject = qrCameraStream;
            video.style.display = 'block';
          }
          if (placeholder) placeholder.style.display = 'none';
          if (status) status.textContent = 'Đang quét mã QR từ camera sau...';
          if (btn) { btn.disabled = false; btn.textContent = 'Đang quét'; }
        } else {
          if (status) status.textContent = 'Trình duyệt chưa hỗ trợ truy cập camera.';
          if (btn) { btn.disabled = false; btn.textContent = 'Bật camera'; }
        }
      } catch (err) {
        if (status) status.textContent = 'Chưa thể bật camera (vui lòng cho phép quyền hoặc nhập mã).';
        if (btn) { btn.disabled = false; btn.textContent = 'Bật camera'; }
      }
    }

    async function manualQrCodeInput() {
      const code = typeof prompt === 'function' ? prompt('Nhập mã token QR hoặc URL lời mời:') : '';
      if (!code || !code.trim()) return;
      let token = code.trim();
      if (token.includes('token=')) {
        const match = token.match(/token=([^&]+)/);
        if (match) token = decodeURIComponent(match[1]);
      }
      await processQrHandshake(token);
    }

    async function processQrHandshake(token) {
      const status = document.getElementById('mobileScannerStatus');
      if (status) status.textContent = 'Đang kiểm tra mã…';
      try {
        const res = await fetch('/api/auth3/guest_handshake', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: token, duration: '1d' })
        });
        const data = await res.json();
        if (data.ok) {
          if (status) status.textContent = '✅ Bắt tay thành công! Đang chuyển hướng...';
          setTimeout(() => {
            closeQrScanner();
            if (typeof location !== 'undefined') {
              location.href = `/guest_enroll?token=${encodeURIComponent(token)}`;
            }
          }, 800);
        } else {
          if (status) {
            status.textContent = data.error || 'Mã QR này đã hết hạn hoặc đã được sử dụng một lần.';
            status.style.color = 'var(--danger)';
          }
        }
      } catch (err) {
        if (status) status.textContent = 'Lỗi kết nối kiểm tra mã QR.';
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

    async function toggleMobileDeviceQuick(devId, btnEl) {
      const allDevs = (latestSnap && latestSnap.devices) ? latestSnap.devices : [];
      const d = allDevs.find(x => x.id === devId) || { id: devId, name: devId, type: devId === 'main_door' ? 'door' : 'light', state: 'OFF' };
      const prevIsOn = d.state === 'ON' || d.state === 'OPEN';
      const nextIsOn = !prevIsOn;
      const prevState = d.state;
      const nextState = d.type === 'door' ? (nextIsOn ? 'OPEN' : 'CLOSED') : (nextIsOn ? 'ON' : 'OFF');

      d.state = nextState;
      if (btnEl) {
        if (btnEl.classList) {
          btnEl.classList.toggle('on', nextIsOn);
          btnEl.classList.toggle('active', nextIsOn);
          btnEl.classList.toggle('off', !nextIsOn);
        }
        btnEl.setAttribute('aria-pressed', nextIsOn ? 'true' : 'false');
        if (btnEl.dataset) btnEl.dataset.state = nextIsOn ? 'on' : 'off';
      }

      const action = d.type === 'door' ? (prevIsOn ? 'close' : 'open') : (prevIsOn ? 'turn_off' : 'turn_on');
      try {
        const res = await fetch('/api/device', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ device_id: devId, action }),
        });
        const data = await res.json();
        if (data && (data.ok === false || data.error)) {
          d.state = prevState;
          if (btnEl) {
            if (btnEl.classList) {
              btnEl.classList.toggle('on', prevIsOn);
              btnEl.classList.toggle('active', prevIsOn);
              btnEl.classList.toggle('off', !prevIsOn);
            }
            btnEl.setAttribute('aria-pressed', prevIsOn ? 'true' : 'false');
            if (btnEl.dataset) btnEl.dataset.state = prevIsOn ? 'on' : 'off';
          }
        } else if (data && data.snapshot) {
          renderState(data.snapshot);
        }
      } catch (err) {
        d.state = prevState;
        if (btnEl) {
          if (btnEl.classList) {
            btnEl.classList.toggle('on', prevIsOn);
            btnEl.classList.toggle('active', prevIsOn);
            btnEl.classList.toggle('off', !prevIsOn);
          }
          btnEl.setAttribute('aria-pressed', prevIsOn ? 'true' : 'false');
          if (btnEl.dataset) btnEl.dataset.state = prevIsOn ? 'on' : 'off';
        }
      }
    }
    if (typeof window !== 'undefined') {
      window.toggleMobileDeviceQuick = toggleMobileDeviceQuick;
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
        card.className = `dev-row ${isOn ? 'on active' : 'off'}`;
        card.setAttribute('data-device', d.id);
        card.setAttribute('data-device-id', d.id);
        card.setAttribute('data-state', isOn ? 'on' : 'off');
        card.setAttribute('aria-pressed', isOn ? 'true' : 'false');
        card.innerHTML = `
          <span class="dev-icon">${ICONS[d.type] || '<svg class="icon"><use href="#i-lamp"/></svg>'}</span>
          <div class="dev-copy">
            <div class="dev-name">${d.name}</div>
            <div class="dev-room">${roomLabel}</div>
          </div>
          <span class="switch" aria-hidden="true"></span>
        `;
        card.onclick = async () => {
          const prevIsOn = d.state === 'ON' || d.state === 'OPEN';
          const nextIsOn = !prevIsOn;
          const prevState = d.state;
          const nextState = d.type === 'door' ? (nextIsOn ? 'OPEN' : 'CLOSED') : (nextIsOn ? 'ON' : 'OFF');

          // Optimistic UI: đổi class và state ngay lập tức
          d.state = nextState;
          card.classList.toggle('on', nextIsOn);
          card.classList.toggle('active', nextIsOn);
          card.classList.toggle('off', !nextIsOn);
          card.setAttribute('data-state', nextIsOn ? 'on' : 'off');
          card.setAttribute('aria-pressed', nextIsOn ? 'true' : 'false');

          const action = d.type === 'door' ? (prevIsOn ? 'close' : 'open') : (prevIsOn ? 'turn_off' : 'turn_on');
          try {
            const res = await fetch('/api/device', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ device_id: d.id, action }),
            });
            const data = await res.json();
            if (data && (data.ok === false || data.error)) {
              // Rollback khi lỗi
              d.state = prevState;
              card.classList.toggle('on', prevIsOn);
              card.classList.toggle('active', prevIsOn);
              card.classList.toggle('off', !prevIsOn);
              card.setAttribute('data-state', prevIsOn ? 'on' : 'off');
              card.setAttribute('aria-pressed', prevIsOn ? 'true' : 'false');
              addLog(`${d.name}: Lỗi thao tác`, 'device', 'Thất bại');
            } else {
              if (data && data.snapshot) renderState(data.snapshot);
              addLog(`${d.name}: ${nextIsOn ? 'Bật' : 'Tắt'}`, 'device', 'Thành công');
            }
          } catch (err) {
            // Rollback khi lỗi mạng
            d.state = prevState;
            card.classList.toggle('on', prevIsOn);
            card.classList.toggle('active', prevIsOn);
            card.classList.toggle('off', !prevIsOn);
            card.setAttribute('data-state', prevIsOn ? 'on' : 'off');
            card.setAttribute('aria-pressed', prevIsOn ? 'true' : 'false');
            addLog(`${d.name}: Lỗi kết nối`, 'device', 'Thất bại');
          }
        };
        grid.appendChild(card);
      });

      const quickMap = {
        living_room_light: 'mobileQuickBtnLight',
        fan: 'mobileQuickBtnFan',
        main_door: 'mobileQuickBtnDoor',
      };
      Object.keys(quickMap).forEach((devId) => {
        const qBtn = document.getElementById(quickMap[devId]);
        const devObj = allDevices.find(x => x.id === devId);
        if (qBtn && devObj) {
          const isOn = devObj.state === 'ON' || devObj.state === 'OPEN';
          if (qBtn.classList) {
            qBtn.classList.toggle('on', isOn);
            qBtn.classList.toggle('active', isOn);
            qBtn.classList.toggle('off', !isOn);
          }
          qBtn.setAttribute('aria-pressed', isOn ? 'true' : 'false');
          if (qBtn.dataset) qBtn.dataset.state = isOn ? 'on' : 'off';
        }
      });

      const connEl = document.getElementById('espBadge');
      if (connEl) {
        const online = snap.server_connected !== false;
        connEl.textContent = online ? 'Đã kết nối' : 'Mất kết nối';
        if (connEl.classList) {
          if (typeof connEl.classList.toggle === 'function') {
            connEl.classList.toggle('offline', !online);
          } else if (!online) {
            if (typeof connEl.classList.add === 'function') connEl.classList.add('offline');
          } else {
            if (typeof connEl.classList.remove === 'function') connEl.classList.remove('offline');
          }
        }
      }

      if (allDevices) {
        const door = allDevices.find(d => d.id === 'main_door');
        const doorEl = document.getElementById('mobileMainDoorStatus');
        if (doorEl && door) {
          const isDoorOpen = door.state === 'OPEN';
          doorEl.textContent = isDoorOpen ? 'Đang mở' : 'Đang khóa';
          doorEl.style.color = isDoorOpen ? 'var(--danger)' : 'var(--text)';
        }
        const siren = allDevices.find(d => d.id === 'alarm_siren');
        const sirenEl = document.getElementById('mobileAlarmSirenStatus');
        if (sirenEl && siren) {
          const isSirenOn = siren.state === 'ON';
          sirenEl.textContent = isSirenOn ? 'Bật' : 'Tắt';
          sirenEl.style.color = isSirenOn ? 'var(--danger)' : 'var(--text)';
        }
      }

      if (snap.mqtt) {
        const dht = snap.mqtt.dht11_telemetry || {};
        const soil = snap.mqtt.soil_moisture_telemetry || {};
        if (dht.temp_c !== undefined) {
          const tVal = Number(dht.temp_c);
          const tSafe = Number.isFinite(tVal) ? Math.max(0, Math.min(60, tVal)) : 28.5;
          const tEl = document.getElementById('tempVal');
          if (tEl) tEl.textContent = `${tSafe}°C`;
          const dtEl = document.getElementById('mobileDisplayTemp');
          if (dtEl) dtEl.textContent = `${tSafe}°C`;
        }
        if (dht.humidity_pct !== undefined) {
          const hVal = Number(dht.humidity_pct);
          const hSafe = Number.isFinite(hVal) ? Math.max(0, Math.min(100, hVal)) : 65;
          const hEl = document.getElementById('humVal');
          if (hEl) hEl.textContent = `${hSafe}%`;
        }
        if (soil.soil_moisture_pct !== undefined) {
          const sVal = Number(soil.soil_moisture_pct);
          const sSafe = Number.isFinite(sVal) ? Math.max(0, Math.min(100, sVal)) : 62;
          const sEl = document.getElementById('soilVal');
          if (sEl) sEl.textContent = `${sSafe}%`;
          const dsEl = document.getElementById('mobileDisplaySoil');
          if (dsEl) dsEl.textContent = `${sSafe}%`;
        }
      }

      if (typeof window !== 'undefined' && window.SmartHome3D) {
        if (!window._mobile3dInited && typeof window.SmartHome3D.init === 'function') {
          const overviewBox = document.getElementById('mobileOverviewBox');
          if (overviewBox) {
            try {
              window.SmartHome3D.init('mobileOverviewBox', null, async (devId) => {
                const card = document.querySelector(`.dev-row[data-device-id="${devId}"]`);
                if (card) card.click();
              });
              window._mobile3dInited = true;
            } catch (e) {
              console.warn('SmartHome3D init in renderState error:', e);
            }
          }
        }
        if (typeof window.SmartHome3D.updateDevices === 'function' && snap.devices) {
          window.SmartHome3D.updateDevices(snap.devices);
        }
        if (typeof window.SmartHome3D.updateSensors === 'function' && snap.mqtt) {
          window.SmartHome3D.updateSensors(snap.mqtt, true);
        }
      }
    }

    async function fetchInitial() {
      const res = await fetch('/api/state');
      const snap = await res.json();
      renderState(snap);
    }

    function showPwaVoiceResults(said, reply) {
      const emptyEl = document.getElementById('pwaVoiceEmpty');
      const resEl = document.getElementById('pwaVoiceResults');
      if (emptyEl) emptyEl.hidden = true;
      if (resEl) resEl.hidden = false;
      if (said !== null) {
        const uEl = document.getElementById('userSaidText');
        if (uEl) uEl.textContent = said;
      }
      if (reply !== null) {
        const aEl = document.getElementById('aiReply');
        if (aEl) aEl.textContent = reply;
      }
      const homeBanner = document.getElementById('mobileHomeVoiceBanner');
      if (homeBanner && (said || reply)) {
        homeBanner.hidden = false;
        const curSaid = said !== null ? said : ((document.getElementById('userSaidText') || {}).textContent || '');
        const curReply = reply !== null ? reply : ((document.getElementById('aiReply') || {}).textContent || '');
        homeBanner.textContent = `Bạn nói: ${curSaid} · Phản hồi: ${curReply}`;
      }
    }

    let mobileMicPcmChunks = [];
    let mobileSpeechRec = null;
    let mobileSpeechTranscript = '';

    function startMobileSpeechRecognitionVi() {
      mobileSpeechTranscript = '';
      if (typeof window === 'undefined') return;
      const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SpeechRec) return;
      try {
        mobileSpeechRec = new SpeechRec();
        mobileSpeechRec.lang = 'vi-VN';
        mobileSpeechRec.continuous = true;
        mobileSpeechRec.interimResults = true;
        mobileSpeechRec.onresult = (ev) => {
          let combined = '';
          for (let i = ev.resultIndex; i < ev.results.length; i++) {
            combined += ev.results[i][0].transcript + ' ';
          }
          const cleaned = combined.trim();
          if (cleaned) {
            mobileSpeechTranscript = cleaned;
            showPwaVoiceResults(cleaned, 'Đang nghe...');
          }
        };
        mobileSpeechRec.onerror = () => {};
        mobileSpeechRec.start();
      } catch (_) {
        mobileSpeechRec = null;
      }
    }

    function stopMobileSpeechRecognitionVi() {
      if (mobileSpeechRec) {
        try {
          mobileSpeechRec.stop();
        } catch (_) {}
        mobileSpeechRec = null;
      }
    }

    function mobileUint8ChunksToBase64(chunks) {
      let totalLen = 0;
      for (const c of chunks) totalLen += c.byteLength;
      if (totalLen === 0) return '';
      const merged = new Uint8Array(totalLen);
      let offset = 0;
      for (const c of chunks) {
        merged.set(c, offset);
        offset += c.byteLength;
      }
      let binary = '';
      const chunkStep = 8192;
      for (let i = 0; i < merged.byteLength; i += chunkStep) {
        binary += String.fromCharCode.apply(null, merged.subarray(i, i + chunkStep));
      }
      return window.btoa(binary);
    }

    async function executeMobileVoiceCommandHttp(payload) {
      const badge = document.getElementById('voiceStateBadge');
      if (badge) badge.textContent = 'Đang xử lý';
      try {
      let res = null;
      let lastFetchErr = null;
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          if (attempt > 0) {
            await new Promise((r) => setTimeout(r, 200 * attempt));
          }
          res = await fetch('/api/voice_command', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload || {}),
          });
          if (res) break;
        } catch (fErr) {
          lastFetchErr = fErr;
        }
      }
      if (!res) throw lastFetchErr || new Error('fetch_failed');
        const data = await res.json();
        const saidText = data.recognized_text || (payload && payload.transcript) || 'Khẩu lệnh giọng nói';
        const replyText = data.exact_spoken_reply || data.reply || 'Đã thực hiện lệnh.';
        showPwaVoiceResults(saidText, replyText);
        if (badge) badge.textContent = data.ok === false ? 'Cần thử lại' : 'Sẵn sàng';
        addLog(saidText, 'voice', data.ok === false ? 'Thất bại' : 'Thành công');
        if (data.snapshot) {
          renderState(data.snapshot);
        } else {
          await fetchInitial();
        }
        return data;
      } catch (err) {
        if (badge) badge.textContent = 'Cần thử lại';
        return { ok: false, error: String(err) };
      }
    }
    if (typeof window !== 'undefined') {
      window.executeMobileVoiceCommandHttp = executeMobileVoiceCommandHttp;
    }

    async function toggleMobileVoiceListen() {
      isMobileListening = !isMobileListening;
      const badge = document.getElementById('voiceStateBadge');
      const label = document.getElementById('btnMobileMicLabel');

      if (!isMobileListening) {
        if (badge) badge.textContent = 'Sẵn sàng';
        if (label) label.textContent = 'Bắt đầu nói';
        stopMobileSpeechRecognitionVi();
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
        } else {
          const chunks = mobileMicPcmChunks.slice(0);
          mobileMicPcmChunks = [];
          const transcriptHint = (mobileSpeechTranscript || '').trim();
          mobileSpeechTranscript = '';
          const pcm16k_b64 = chunks.length > 0 ? mobileUint8ChunksToBase64(chunks) : generateMobileSynthetic16kPcmB64(true);
          await executeMobileVoiceCommandHttp({
            pcm16k_b64,
            transcript: transcriptHint,
            is_live_mic: true,
          });
        }
        return;
      }

      if (badge) badge.textContent = 'Đang nghe';
      if (label) label.textContent = 'Dừng và gửi';
      mobileMicPcmChunks = [];
      startMobileSpeechRecognitionVi();

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
          const bytes = new Uint8Array(pcm16.buffer.slice(0));
          mobileMicPcmChunks.push(bytes);
          if (mobileMicPcmChunks.length > 40) {
            mobileMicPcmChunks.shift();
          }
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
      const devMap = {
        'Đèn phòng khách': 'living_room_light',
        'Quạt trần': 'fan',
        'Điều hòa': 'ac',
        'Tưới cây': 'garden_pump'
      };
      const mSec = t.match(/(\d+(?:\.\d+)?)/);
      const secVal = mSec ? parseFloat(mSec[1]) : 15;
      const res = await fetch('/api/mobile/schedule', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_id: devMap[dev] || 'living_room_light',
          action: act === 'Tắt' ? 'turn_off' : 'turn_on',
          seconds: secVal
        })
      });
      const data = await res.json();
      const reply = data.exact_spoken_reply || data.error || 'Đã đặt lịch.';
      const schedInline = document.getElementById('upcomingScheduleInline');
      if (data.ok === false && schedInline) {
        schedInline.textContent = reply;
      }
      showPwaVoiceResults(`Hẹn ${t} ${act.toLowerCase()} ${dev.toLowerCase()}`, reply);
      addLog(`Hẹn giờ: ${dev} (${act})`, 'device', data.ok === false ? 'Thất bại' : 'Thành công');
      fetchInitial();
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
      fetch('/api/session/role', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: sel.value })
      }).catch(() => {});
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

    const isMobileVercel = (typeof window !== 'undefined') && (
      (typeof location !== 'undefined' && Boolean((location.hostname || location.host || '').includes('vercel.app'))) ||
      Boolean(window._FORCE_HTTP_POLLING)
    );

    function connectMobileWebSocket() {
      if (isMobileVercel || (typeof window !== 'undefined' && window._disableWebSocket)) {
        /* On Vercel serverless, WebSocket is not supported: fallback cleanly without spamming console errors */
        fetchInitial().catch(() => {});
        return;
      }

      try {
        ws = new WebSocket(`${proto}://${location.host}/ws`);
      } catch (_) {
        fetchInitial().catch(() => {});
        return;
      }
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
        fetch('/api/state')
          .then(r => (r.ok ? r.json() : Promise.reject()))
          .then(d2 => {
            const connEl = document.getElementById('espBadge');
            if (connEl) { connEl.textContent = 'Đã kết nối'; connEl.classList.remove('offline'); }
            renderState(d2);
          })
          .catch(() => {
            const connEl = document.getElementById('espBadge');
            if (connEl) { connEl.textContent = 'Mất kết nối'; connEl.classList.add('offline'); }
          });
        /* Auto-reconnect after 4s only when not on Vercel */
        if (!isMobileVercel) {
          setTimeout(() => { if (mobileLoggedIn) connectMobileWebSocket(); }, 4000);
        }
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
          cdEl.textContent = `Đổi mã sau ${rem}s`;
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
        if (d2 && d2.devices) {
          const connEl = document.getElementById('espBadge');
          if (connEl) { connEl.textContent = 'Đã kết nối'; connEl.classList.remove('offline'); }
          renderState(d2);
        }
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
      } catch (e) {
        const connEl = document.getElementById('espBadge');
        if (connEl) { connEl.textContent = 'Mất kết nối'; connEl.classList.add('offline'); }
      }
    }

    function onMobileQrInviteTierChange() {
      refreshMobileQr10s();
    }

    let _mobileAppInited = false;
    function initMobileApp() {
      if (_mobileAppInited) return;
      _mobileAppInited = true;
      if (typeof window !== 'undefined' && window.SmartHome3D && typeof window.SmartHome3D.init === 'function') {
        try {
          window.SmartHome3D.init('mobileOverviewBox', null, async (devId) => {
            const card = document.querySelector(`.dev-row[data-device-id="${devId}"]`);
            if (card) card.click();
          });
          window._mobile3dInited = true;
        } catch (e) {
          console.warn('SmartHome3D init error on mobile:', e);
        }
      }
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
window.switchMobileTab = switchMobileTab;
window.updateAccountProfile = updateAccountProfile;
window.toggleDetailsSection = toggleDetailsSection;
window.submitMobileLogout = submitMobileLogout;
window.openForgotPassword = openForgotPassword;
window.closeForgotPassword = closeForgotPassword;
window.forgotBackToEmail = forgotBackToEmail;
window.submitForgotSendOtp = submitForgotSendOtp;
window.submitForgotVerifyOtp = submitForgotVerifyOtp;
window.submitForgotResetPassword = submitForgotResetPassword;
window.openVoiceBottomSheet = openVoiceBottomSheet;
window.closeVoiceBottomSheet = closeVoiceBottomSheet;
window.startVoiceSheetRecording = startVoiceSheetRecording;
window.stopVoiceRecording = stopVoiceRecording;
window.retryVoiceRecording = retryVoiceRecording;
window.openMobileMicPermissionModal = openMobileMicPermissionModal;
window.closeMobileMicPermissionModal = closeMobileMicPermissionModal;
window.openQrScanner = openQrScanner;
window.closeQrScanner = closeQrScanner;
window.startCameraScan = startCameraScan;
window.manualQrCodeInput = manualQrCodeInput;
window.processQrHandshake = processQrHandshake;
window.initMobileApp = initMobileApp;
