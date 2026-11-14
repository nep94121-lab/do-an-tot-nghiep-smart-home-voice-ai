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

    if (typeof window !== 'undefined' && typeof window.fetch === 'function' && !window._shAuthFetchWrapped) {
      const _origFetch = window.fetch.bind(window);
      window.fetch = function(input, init) {
        let urlStr = typeof input === 'string' ? input : (input && input.url ? input.url : '');
        if (urlStr.startsWith('/api/')) {
          let tok = '';
          try {
            tok = (window.sessionStorage && window.sessionStorage.getItem('session_token')) ||
                  (window.localStorage && window.localStorage.getItem('session_token')) || '';
          } catch (_) {}
          const nextInit = Object.assign({ credentials: 'include' }, init || {});
          const hdrs = Object.assign({}, nextInit.headers || {});
          if (tok && !hdrs['X-Session-Token'] && !hdrs['x-session-token'] && !hdrs['Authorization']) {
            hdrs['X-Session-Token'] = tok;
          }
          nextInit.headers = hdrs;
          return _origFetch(input, nextInit);
        }
        return _origFetch(input, init);
      };
      window._shAuthFetchWrapped = true;
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
    const pendingDeviceMutations = new Map();
    const MUTATION_GUARD_WINDOW_MS = 4000;
    const MOBILE_DEVICE_DEBOUNCE_MS = 50;
    const MOBILE_CLIENT_ID =
      (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function')
        ? `mob_${crypto.randomUUID()}`
        : `mob_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
    const mobileDeviceControlState = {};
    let mobileLastRevisionSeq = 0;
    let mobilePollInFlight = false;
    if (typeof window !== 'undefined') {
      window.__mobileDeviceControlState = mobileDeviceControlState;
      window.__mobileClientId = MOBILE_CLIENT_ID;
    }
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
    let mobileRole = null;
    let mobileTier = null;
    let mobileDisplayName = '';
    let mobilePendingOtpEmail = '';
    let mobileSessionGeneration = 0;
    let mobilePollIntervalId = null;

    function isHttpOk(res) {
      return Boolean(res && (res.ok !== undefined ? res.ok : (res.status !== undefined ? (res.status >= 200 && res.status < 300) : true)));
    }

    function getMobileTierLabel(tier, roleName) {
      const t = Number(tier);
      if (t === 1 || roleName === 'owner') return 'Chủ nhà';
      if (t === 2 || roleName === 'family') return 'Thành viên gia đình';
      if (t === 3 || roleName === 'guest') return 'Khách';
      return 'Thành viên';
    }

    function clearMobileClientTokens() {
      try {
        if (typeof sessionStorage !== 'undefined') {
          sessionStorage.removeItem('mobileLoggedIn');
          sessionStorage.removeItem('mobileLoggedInEmail');
          sessionStorage.removeItem('session_token');
          sessionStorage.removeItem('sh_session_token');
        }
      } catch (_) {}
      try {
        if (typeof localStorage !== 'undefined') {
          localStorage.removeItem('smarthome_auth_session');
          localStorage.removeItem('session_token');
          localStorage.removeItem('sh_session_token');
          localStorage.removeItem('auth3_session');
          localStorage.removeItem('mobileLoggedIn');
          localStorage.removeItem('mobileLoggedInEmail');
        }
      } catch (_) {}
    }

    function clearMobileAuthState() {
      mobileSessionGeneration += 1;
      mobileLoggedIn = false;
      mobileLoggedInEmail = '';
      mobileRole = null;
      mobileTier = null;
      mobileDisplayName = '';
      clearMobileClientTokens();
    }

    function showMobileActionError(msg, requireLogin = false) {
      ['mobileActionStatus', 'mobileDevicesAuthStatus'].forEach((elId) => {
        const el = document.getElementById(elId);
        if (!el) return;
        if (!msg) {
          el.hidden = true;
          el.innerHTML = '';
          return;
        }
        el.hidden = false;
        el.textContent = '';
        const span = document.createElement('span');
        span.textContent = msg;
        el.appendChild(span);
        if (requireLogin) {
          const btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'btn primary';
          btn.style.marginLeft = '8px';
          btn.style.padding = '4px 10px';
          btn.style.fontSize = '12px';
          btn.textContent = 'Đăng nhập';
          btn.onclick = () => openMobileLoginGate(true);
          el.appendChild(btn);
        }
      });
    }

    function openMobileLoginGate(focusInput = true) {
      const gate = document.getElementById('mobileLoginGate');
      const main = document.getElementById('mobileMainContent');
      const nav = document.getElementById('mobileBottomNav');
      if (gate) gate.hidden = false;
      if (main) main.hidden = true;
      if (nav) nav.hidden = true;
      cancelMobileOtpPanel(true);
      if (focusInput) {
        const emailEl = document.getElementById('mobileLoginEmail');
        if (emailEl && typeof emailEl.focus === 'function') {
          try { emailEl.focus(); } catch (_) {}
        }
      }
    }

    function handleMobileUnauthorized(msg) {
      clearMobileAuthState();
      updateMobileAuthUiState(false);
      showMobileActionError(msg || 'Vui lòng đăng nhập để tiếp tục.', true);
      openMobileLoginGate(true);
      const loginMsg = document.getElementById('mobileLoginMsg');
      if (loginMsg && msg) {
        loginMsg.style.color = 'var(--danger)';
        loginMsg.textContent = msg;
      }
    }

    let mobileOtpCooldownTimer = null;

    function startMobileOtpCooldown(seconds) {
      const sendBtn = document.getElementById('btnMobileSendOtp');
      let remaining = Math.max(1, parseInt(seconds || 60, 10) || 60);
      if (mobileOtpCooldownTimer) clearInterval(mobileOtpCooldownTimer);
      if (!sendBtn) return;
      sendBtn.disabled = true;
      sendBtn.textContent = `Gửi lại (${remaining}s)`;
      mobileOtpCooldownTimer = setInterval(() => {
        remaining -= 1;
        if (remaining <= 0) {
          clearInterval(mobileOtpCooldownTimer);
          mobileOtpCooldownTimer = null;
          sendBtn.disabled = false;
          sendBtn.textContent = 'Gửi lại mã OTP';
        } else {
          sendBtn.textContent = `Gửi lại (${remaining}s)`;
        }
      }, 1000);
    }

    function showMobileOtpPanel(email, initialMsg = '') {
      mobilePendingOtpEmail = email || '';
      const loginForm = document.getElementById('mobileLoginForm');
      const regForm = document.getElementById('mobileRegisterForm');
      const forgotPanel = document.getElementById('mobileForgotPasswordPanel');
      const otpPanel = document.getElementById('mobileOtpPanel');
      const otpInput = document.getElementById('mobileOtpInput');
      const otpStatus = document.getElementById('mobileOtpStatus');
      if (loginForm) loginForm.style.display = 'none';
      if (regForm) regForm.style.display = 'none';
      if (forgotPanel) forgotPanel.style.display = 'none';
      if (otpPanel) {
        otpPanel.hidden = false;
        otpPanel.style.display = 'grid';
      }
      if (otpInput) {
        otpInput.value = '';
        if (typeof otpInput.focus === 'function') {
          try { otpInput.focus(); } catch (_) {}
        }
      }
      if (otpStatus) {
        otpStatus.style.color = initialMsg ? 'var(--accent)' : 'var(--muted)';
        otpStatus.textContent = initialMsg || 'Đang gửi mã OTP tới Gmail Chủ nhà...';
      }
    }

    function cancelMobileOtpPanel(keepMsg = false) {
      mobilePendingOtpEmail = '';
      if (mobileOtpCooldownTimer) {
        clearInterval(mobileOtpCooldownTimer);
        mobileOtpCooldownTimer = null;
      }
      const sendBtn = document.getElementById('btnMobileSendOtp');
      if (sendBtn) {
        sendBtn.disabled = false;
        sendBtn.textContent = 'Gửi lại mã OTP';
      }
      const loginForm = document.getElementById('mobileLoginForm');
      const otpPanel = document.getElementById('mobileOtpPanel');
      const otpInput = document.getElementById('mobileOtpInput');
      const otpStatus = document.getElementById('mobileOtpStatus');
      if (otpPanel) {
        otpPanel.hidden = true;
        otpPanel.style.display = 'none';
      }
      if (loginForm) loginForm.style.display = 'grid';
      if (otpInput) otpInput.value = '';
      if (otpStatus && !keepMsg) otpStatus.textContent = '';
    }

    async function sendMobileLayer2Otp() {
      const statusEl = document.getElementById('mobileOtpStatus');
      const sendBtn = document.getElementById('btnMobileSendOtp');
      const email = (mobilePendingOtpEmail || (document.getElementById('mobileLoginEmail') || {}).value || '').trim();
      if (!email) {
        if (statusEl) {
          statusEl.style.color = 'var(--danger)';
          statusEl.textContent = 'Thiếu email tài khoản để gửi OTP.';
        }
        return;
      }
      if (sendBtn) { sendBtn.disabled = true; sendBtn.textContent = 'Đang gửi OTP...'; }
      try {
        const res = await fetch('/api/auth3/layer2_send_otp', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, source: 'Mobile App' }),
        });
        const data = await res.json().catch(() => ({}));
        if (isHttpOk(res) && data.ok) {
          if (statusEl) {
            statusEl.style.color = 'var(--accent)';
            statusEl.textContent = data.message || (
              data.masked_email
                ? ('Đã gửi mã OTP 6 số tới ' + data.masked_email + ', hiệu lực 5 phút')
                : 'Đã gửi mã OTP 6 số tới Gmail Chủ nhà, hiệu lực 5 phút'
            );
          }
          const cooldownSec = Number(data.cooldown_remaining_seconds ?? data.retry_after_seconds ?? 60);
          if (cooldownSec > 0) {
            startMobileOtpCooldown(cooldownSec);
          } else if (sendBtn) {
            sendBtn.disabled = false;
            sendBtn.textContent = 'Gửi lại mã OTP';
          }
        } else {
          if (statusEl) {
            statusEl.style.color = 'var(--danger)';
            statusEl.textContent = data.error || data.message || 'Không gửi được mã OTP Gmail.';
          }
          const retrySec = Number(data.cooldown_remaining_seconds ?? data.retry_after_seconds ?? 0);
          if (res.status === 429 && retrySec > 0) {
            startMobileOtpCooldown(retrySec);
          } else if (sendBtn) {
            sendBtn.disabled = false;
            sendBtn.textContent = 'Gửi lại mã OTP';
          }
        }
      } catch (_) {
        if (statusEl) {
          statusEl.style.color = 'var(--danger)';
          statusEl.textContent = 'Lỗi kết nối máy chủ khi gửi OTP.';
        }
        if (sendBtn) { sendBtn.disabled = false; sendBtn.textContent = 'Gửi lại mã OTP'; }
      }
    }

    async function verifyMobileLayer2Otp() {
      const otpInput = document.getElementById('mobileOtpInput');
      const statusEl = document.getElementById('mobileOtpStatus');
      const verifyBtn = document.getElementById('btnMobileVerifyOtp');
      const email = (mobilePendingOtpEmail || (document.getElementById('mobileLoginEmail') || {}).value || '').trim();
      const otpCode = (otpInput ? otpInput.value : '').trim();
      if (!email) {
        if (statusEl) { statusEl.style.color = 'var(--danger)'; statusEl.textContent = 'Vui lòng đăng nhập lại Bước 1.'; }
        return;
      }
      if (!/^\d{6}$/.test(otpCode)) {
        if (statusEl) { statusEl.style.color = 'var(--danger)'; statusEl.textContent = 'Vui lòng nhập đúng 6 chữ số OTP.'; }
        return;
      }
      if (verifyBtn) { verifyBtn.disabled = true; verifyBtn.textContent = 'Đang xác nhận...'; }
      try {
        const res = await fetch('/api/auth3/layer2_verify_otp', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, otp_code: otpCode, purpose: 'layer2_login', source: 'Mobile App' }),
        });
        const data = await res.json().catch(() => ({}));
        if (isHttpOk(res) && data.ok && data.session_token) {
          const acct = data.account || {};
          mobileSessionGeneration += 1;
          mobilePendingOtpEmail = '';
          if (typeof sessionStorage !== 'undefined' && data.session_token) {
            sessionStorage.setItem('session_token', data.session_token);
          }
          try {
            if (typeof localStorage !== 'undefined' && data.session_token) {
              localStorage.setItem('session_token', data.session_token);
            }
          } catch (_) {}
          const verified = await fetchServerSessionRole({
            authenticated: true,
            email: acct.email || email,
            display_name: acct.display_name || '',
            tier: Number(data.tier || acct.tier || 1),
            role: Number(data.tier || acct.tier || 1) === 1 ? 'owner' : 'member',
          });
          if (!verified) {
            if (statusEl) {
              statusEl.style.color = 'var(--danger)';
              statusEl.textContent = 'Không thể xác minh phiên đăng nhập từ máy chủ.';
            }
          } else {
            cancelMobileOtpPanel(true);
            if (statusEl) statusEl.textContent = '';
          }
        } else {
          const retryAfter = res.headers && res.headers.get ? res.headers.get('Retry-After') : '';
          const lockoutHint = res.status === 429 && retryAfter ? ` (Thử lại sau ${retryAfter}s)` : '';
          if (statusEl) {
            statusEl.style.color = 'var(--danger)';
            statusEl.textContent = (data.error || data.message || 'Mã OTP không đúng hoặc đã hết hạn.') + lockoutHint;
          }
        }
      } catch (_) {
        if (statusEl) {
          statusEl.style.color = 'var(--danger)';
          statusEl.textContent = 'Lỗi kết nối máy chủ khi xác nhận OTP.';
        }
      }
      if (verifyBtn) { verifyBtn.disabled = false; verifyBtn.textContent = 'Xác nhận OTP & Đăng nhập'; }
    }

    async function fetchServerSessionRole(fallbackAuth = null) {
      const reqGen = mobileSessionGeneration;
      let res = null;
      try {
        res = await fetch('/api/session/role', { method: 'GET', credentials: 'include' });
        if (res && res.status === 405) {
          res = await fetch('/api/session/role', {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: '{}',
          });
        }
      } catch (_) {
        res = null;
      }
      if (reqGen !== mobileSessionGeneration) return mobileLoggedIn;
      let data = null;
      if (res) {
        try { data = await res.json(); } catch (_) { data = null; }
      }
      if (reqGen !== mobileSessionGeneration) return mobileLoggedIn;

      const explicitUnauthorized = Boolean(
        res && (res.status === 401 || res.status === 403 || (data && data.authenticated === false))
      );
      if (explicitUnauthorized) {
        clearMobileAuthState();
        updateMobileAuthUiState(false);
        const main = document.getElementById('mobileMainContent');
        const nav = document.getElementById('mobileBottomNav');
        const gate = document.getElementById('mobileLoginGate');
        if (main) main.hidden = true;
        if (nav) nav.hidden = true;
        if (gate) gate.hidden = false;
        return false;
      }

      if (isHttpOk(res) && data && data.authenticated === true) {
        const tierNum = Number(data.tier) || (data.role === 'owner' ? 1 : data.role === 'family' ? 2 : data.role === 'guest' ? 3 : null);
        mobileLoggedIn = true;
        mobileLoggedInEmail = String(data.email || '');
        mobileDisplayName = String(data.display_name || '');
        mobileRole = data.role || (tierNum === 1 ? 'owner' : tierNum === 2 ? 'family' : tierNum === 3 ? 'guest' : null);
        mobileTier = tierNum;
        try {
          if (typeof sessionStorage !== 'undefined') {
            sessionStorage.setItem('mobileLoggedIn', '1');
            if (mobileLoggedInEmail) sessionStorage.setItem('mobileLoggedInEmail', mobileLoggedInEmail);
          }
        } catch (_) {}
        showMobileActionError('');
        showMobileMainContent();
        return true;
      }

      if (fallbackAuth && fallbackAuth.authenticated === true && !explicitUnauthorized) {
        mobileLoggedIn = true;
        mobileLoggedInEmail = String(fallbackAuth.email || '');
        mobileDisplayName = String(fallbackAuth.display_name || '');
        mobileTier = Number(fallbackAuth.tier) || null;
        mobileRole = fallbackAuth.role || (mobileTier === 1 ? 'owner' : mobileTier === 2 ? 'family' : mobileTier === 3 ? 'guest' : null);
        showMobileActionError('');
        showMobileMainContent();
        return true;
      }

      clearMobileAuthState();
      updateMobileAuthUiState(false);
      return false;
    }

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
      if (msgEl) { msgEl.style.color = 'var(--muted)'; msgEl.textContent = ''; }
      if (btnEl) { btnEl.disabled = true; btnEl.textContent = 'Đang đăng nhập...'; }
      try {
        const res = await fetch('/api/auth3/layer1_login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password, login_method: 'password', source: 'Mobile App', send_gmail: false }),
        });
        const data = await res.json().catch(() => ({}));
        if (res.status === 429) {
          const retryAfter = res.headers && res.headers.get ? res.headers.get('Retry-After') : '';
          const waitTxt = retryAfter ? ` (Thử lại sau ${retryAfter}s)` : '';
          if (msgEl) {
            msgEl.style.color = 'var(--danger)';
            msgEl.textContent = (data.error || data.message || 'Tài khoản tạm thời bị khóa do nhập sai nhiều lần.') + waitTxt;
          }
        } else if (!isHttpOk(res) || !data.ok) {
          if (msgEl) {
            msgEl.style.color = 'var(--danger)';
            msgEl.textContent = data.error || data.message || 'Sai email hoặc mật khẩu.';
          }
        } else if (data.otp_required === true) {
          mobileLoggedIn = false;
          mobileRole = null;
          mobileTier = null;
          const targetEmail = (data.account && data.account.email) || email;
          const sentNotice = data.otp_sent === true
            ? (
                data.message || (
                  data.masked_email
                    ? ('Đã gửi mã OTP 6 số tới ' + data.masked_email + ', hiệu lực 5 phút')
                    : 'Đã gửi mã OTP 6 số tới Gmail Chủ nhà, hiệu lực 5 phút'
                )
              )
            : '';
          showMobileOtpPanel(targetEmail, sentNotice);
          if (data.otp_sent === true) {
            const firstCd = Number(data.cooldown_remaining_seconds ?? 60);
            if (firstCd > 0) startMobileOtpCooldown(firstCd);
          } else {
            await sendMobileLayer2Otp();
          }
        } else {
          const acct = data.account || {};
          const resolvedEmail = acct.email || email;
          const resolvedTier = Number(data.tier || acct.tier || 0) || null;
          mobileSessionGeneration += 1;
          if (typeof sessionStorage !== 'undefined') {
            sessionStorage.setItem('mobileLoggedIn', '1');
            sessionStorage.setItem('mobileLoggedInEmail', resolvedEmail);
            if (data.session_token) sessionStorage.setItem('session_token', data.session_token);
          }
          try {
            if (typeof localStorage !== 'undefined' && data.session_token) {
              localStorage.setItem('session_token', data.session_token);
            }
          } catch (_) {}
          await fetchServerSessionRole({
            authenticated: true,
            email: resolvedEmail,
            display_name: acct.display_name || '',
            tier: resolvedTier,
            role: resolvedTier === 1 ? 'owner' : resolvedTier === 2 ? 'family' : resolvedTier === 3 ? 'guest' : null,
          });
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
      const otpPanel = document.getElementById('mobileOtpPanel');
      const forgotPanel = document.getElementById('mobileForgotPasswordPanel');
      const btnLogin = document.getElementById('btnMobileTabLogin');
      const btnReg = document.getElementById('btnMobileTabRegister');
      if (otpPanel) { otpPanel.hidden = true; otpPanel.style.display = 'none'; }
      if (forgotPanel) forgotPanel.style.display = 'none';
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
      const helperEl = document.getElementById('mobileRegisterHelper');
      if (!tierEl || !helperEl) return;
      const t = parseInt(tierEl.value || '2', 10);
      if (t === 1) {
        helperEl.textContent = 'Tài khoản Chủ nhà dùng email quản trị đã cấu hình và cần xác thực OTP khi đăng nhập.';
      } else {
        helperEl.textContent = 'Tài khoản mới đăng ký cần chờ Chủ nhà phê duyệt cấp quyền trước khi đăng nhập.';
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

      const strictEmailRe = /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$/;
      if (!email || !strictEmailRe.test(email)) {
        if (msgEl) {
          msgEl.style.color = 'var(--danger)';
          msgEl.textContent = 'Vui lòng nhập địa chỉ Email hợp lệ!';
        }
        return;
      }
      if (!password || password.length < 6) {
        if (msgEl) {
          msgEl.style.color = 'var(--danger)';
          msgEl.textContent = 'Mật khẩu phải có từ 6 ký tự trở lên!';
        }
        return;
      }
      if (!confirmPassword) {
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
        const params = typeof window !== 'undefined' && window.location && window.location.search ? new URLSearchParams(window.location.search) : null;
        const inviteToken = params ? (params.get('invite_token') || params.get('token') || params.get('invite') || '').trim() : '';
        const reqBody = {
          email,
          display_name: displayName,
          target_tier: tier,
          password,
          confirm_password: confirmPassword,
        };
        if (inviteToken) reqBody.invite_token = inviteToken;
        const res = await fetch('/api/auth3/register_or_set_password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(reqBody),
        });
        const data = await res.json();
        if (isHttpOk(res) && data.ok) {
          const hasActiveSession = Boolean(data.session_token && data.permission_active !== false);
          if (hasActiveSession) {
            const acct = data.account || {};
            const resolvedEmail = acct.email || email;
            const resolvedTier = Number(data.tier || acct.tier || tier || 2);
            mobileSessionGeneration += 1;
            mobileLoggedIn = true;
            mobileLoggedInEmail = resolvedEmail;
            mobileDisplayName = acct.display_name || name || '';
            mobileTier = resolvedTier;
            mobileRole = resolvedTier === 1 ? 'owner' : resolvedTier === 2 ? 'family' : 'guest';
            if (typeof sessionStorage !== 'undefined') {
              sessionStorage.setItem('mobileLoggedIn', '1');
              sessionStorage.setItem('mobileLoggedInEmail', resolvedEmail);
              sessionStorage.setItem('session_token', data.session_token);
            }
            if (typeof localStorage !== 'undefined') {
              localStorage.setItem('session_token', data.session_token);
            }
            if (msgEl) {
              msgEl.style.color = 'var(--accent)';
              msgEl.textContent = `✅ ${data.message || 'Đặt mật khẩu thành công!'}`;
            }
            setTimeout(showMobileMainContent, 500);
          } else {
            clearMobileAuthState();
            updateMobileAuthUiState(false);
            if (msgEl) {
              msgEl.style.color = 'var(--muted)';
              msgEl.textContent = data.message || 'Đã tạo tài khoản. Chờ chủ nhà cấp quyền trước khi đăng nhập.';
            }
          }
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
      if (btnEl) { btnEl.disabled = false; btnEl.textContent = 'Đăng ký tài khoản'; }
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

    function updateMobileAuthUiState(serverConnected = true) {
      const isAuthed = Boolean(mobileLoggedIn);
      const isOwner = isAuthed && Number(mobileTier) === 1;
      const badgeIds = ['espBadge', 'mobileDevicesConnBadge', 'mobileVoiceConnBadge', 'mobileAccountConnBadge'];
      badgeIds.forEach((bId) => {
        const el = document.getElementById(bId);
        if (!el) return;
        const label = !isAuthed ? 'Chưa đăng nhập' : (serverConnected ? 'Đã kết nối' : 'Mất kết nối');
        el.innerHTML = `<span class="dot"></span>${label}`;
        if (el.classList) {
          if (typeof el.classList.toggle === 'function') {
            el.classList.toggle('offline', !isAuthed || !serverConnected);
          } else if (!isAuthed || !serverConnected) {
            if (typeof el.classList.add === 'function') el.classList.add('offline');
          } else if (typeof el.classList.remove === 'function') {
            el.classList.remove('offline');
          }
        }
      });

      const voiceBadge = document.getElementById('voiceStateBadge');
      if (voiceBadge && (!isAuthed || voiceBadge.textContent === 'Chưa đăng nhập')) {
        voiceBadge.textContent = isAuthed ? 'Sẵn sàng' : 'Chưa đăng nhập';
      }

      if (typeof document !== 'undefined' && typeof document.querySelectorAll === 'function') {
        document.querySelectorAll('[data-owner-only="true"]').forEach((el) => {
          el.hidden = !isOwner;
        });
      }

      const btnLogout = document.getElementById('mobileBtnLogout');
      const btnOpenLogin = document.getElementById('mobileBtnOpenLogin');
      if (btnLogout) btnLogout.hidden = !isAuthed;
      if (btnOpenLogin) btnOpenLogin.hidden = isAuthed;

      if (!isAuthed) {
        updateAccountProfile('Chưa đăng nhập', '', '—');
      }
    }

    function showMobileMainContent() {
      const gate = document.getElementById('mobileLoginGate');
      const main = document.getElementById('mobileMainContent');
      const nav = document.getElementById('mobileBottomNav');
      if (gate) gate.hidden = true;
      if (main) main.hidden = false;
      if (nav) nav.hidden = false;
      switchMobileTab('home');
      const roleLabel = mobileLoggedIn ? getMobileTierLabel(mobileTier, mobileRole) : 'Chưa đăng nhập';
      const durLabel = !mobileLoggedIn ? '—' : (Number(mobileTier) === 1 ? 'Không giới hạn' : (Number(mobileTier) === 3 ? 'Tạm thời' : 'Theo quyền tài khoản'));
      updateAccountProfile(roleLabel, mobileLoggedIn ? mobileLoggedInEmail : '', durLabel);
      updateMobileAuthUiState(mobileLoggedIn);
      initMobileApp();
    }

    function checkMobileSession() {
      // Fail-closed: derive authentication, role, tier exclusively from server /api/session/role
      updateMobileAuthUiState(false);
      return fetchServerSessionRole();
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
      const regNameEl = document.getElementById('mobileVoiceRegName');
      const safeRole = role || 'Chưa đăng nhập';
      if (roleEl) roleEl.textContent = safeRole;
      if (actorBadge) actorBadge.textContent = safeRole;
      if (regNameEl) regNameEl.textContent = safeRole;
      if (emailEl) {
        if (!email) {
          emailEl.textContent = '—';
        } else {
          const parts = email.split('@');
          if (parts.length === 2 && parts[0].length > 1) {
            emailEl.textContent = `${parts[0][0]}***@${parts[1]}`;
          } else {
            emailEl.textContent = email;
          }
        }
      }
      if (durEl) durEl.textContent = duration || '—';
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
      clearMobileAuthState();
      if (mobilePollIntervalId) {
        clearInterval(mobilePollIntervalId);
        mobilePollIntervalId = null;
      }
      _mobileAppInited = false;
      if (typeof sessionStorage !== 'undefined') {
        sessionStorage.clear();
      }
      try {
        if (typeof window !== 'undefined' && typeof window.fetch === 'function' && window.location && window.location.host) {
          Promise.resolve(window.fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })).catch(() => {});
        }
      } catch (_) {}
      try {
        document.cookie = 'smarthome_session=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
        document.cookie = 'session_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
        document.cookie = 'sh_session_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
        document.cookie = 'mobileLoggedIn=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
        document.cookie = 'mobileLoggedInEmail=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
      } catch (_) {}

      // Reset login & OTP fields and messages
      const emailInput = document.getElementById('mobileLoginEmail');
      const passInput = document.getElementById('mobileLoginPassword');
      if (emailInput) emailInput.value = '';
      if (passInput) passInput.value = '';
      const loginMsg = document.getElementById('mobileLoginMsg');
      if (loginMsg) loginMsg.textContent = '';
      cancelMobileOtpPanel();

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
      const forgotEmailInput = document.getElementById('mobileForgotEmail');
      const forgotOtp = document.getElementById('mobileForgotOtp');
      const forgotPass = document.getElementById('mobileForgotNewPassword');
      const forgotConf = document.getElementById('mobileForgotConfirmPassword');
      if (forgotEmailInput) forgotEmailInput.value = '';
      if (forgotOtp) forgotOtp.value = '';
      if (forgotPass) forgotPass.value = '';
      if (forgotConf) forgotConf.value = '';

      showMobileActionError('');
      updateMobileAuthUiState(false);

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
      const otpPanel = document.getElementById('mobileOtpPanel');
      const forgotPanel = document.getElementById('mobileForgotPasswordPanel');
      const stepEmail = document.getElementById('mobileForgotStepEmail');
      const stepOtp = document.getElementById('mobileForgotStepOtp');
      const stepReset = document.getElementById('mobileForgotStepReset');
      const stepLabel = document.getElementById('mobileForgotStepLabel');
      const stepDesc = document.getElementById('mobileForgotStepDesc');
      const emailMsg = document.getElementById('mobileForgotEmailMsg');
      const otpMsg = document.getElementById('mobileForgotOtpMsg');
      const resetMsg = document.getElementById('mobileForgotResetMsg');

      if (loginForm) loginForm.style.display = 'none';
      if (regForm) regForm.style.display = 'none';
      if (otpPanel) { otpPanel.hidden = true; otpPanel.style.display = 'none'; }
      if (forgotPanel) forgotPanel.style.display = 'block';
      if (stepEmail) stepEmail.style.display = 'grid';
      if (stepOtp) stepOtp.style.display = 'none';
      if (stepReset) stepReset.style.display = 'none';
      if (stepLabel) stepLabel.textContent = 'Bước 1/3';
      if (stepDesc) stepDesc.textContent = 'Nhập email để nhận mã xác nhận Gmail OTP.';
      if (emailMsg) emailMsg.textContent = '';
      if (otpMsg) otpMsg.textContent = '';
      if (resetMsg) resetMsg.textContent = '';
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
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="btn-spinner"></span> Đang gửi mã...';
        btn.classList.add('loading');
      }
      if (resendBtn) {
        resendBtn.disabled = true;
      }
      try {
        const res = await fetch('/api/auth3/forgot_password_send_otp', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, send_gmail: true })
        });
        const data = await res.json().catch(() => ({}));
        if (isHttpOk(res) && data.ok && (!data.gmail_delivery || data.gmail_delivery.sent_real_gmail !== false)) {
          const stepEmail = document.getElementById('mobileForgotStepEmail');
          const stepOtp = document.getElementById('mobileForgotStepOtp');
          const stepLabel = document.getElementById('mobileForgotStepLabel');
          const stepDesc = document.getElementById('mobileForgotStepDesc');
          const sentText = document.getElementById('mobileForgotEmailSentText');
          const otpMsg = document.getElementById('mobileForgotOtpMsg');
          if (msgEl) msgEl.textContent = '';
          if (otpMsg) { otpMsg.style.color = 'var(--accent)'; otpMsg.textContent = '✅ Đã gửi mã OTP tới Gmail của bạn.'; }
          if (stepEmail) stepEmail.style.display = 'none';
          if (stepOtp) stepOtp.style.display = 'grid';
          if (stepLabel) stepLabel.textContent = 'Bước 2/3';
          if (stepDesc) stepDesc.textContent = 'Nhập mã 6 số đã gửi tới Gmail của bạn.';
          if (sentText) {
            const parts = email.split('@');
            sentText.textContent = parts.length === 2 && parts[0].length > 1 ? `${parts[0][0]}***@${parts[1]}` : email;
          }
          let countdown = Number(data.cooldown_remaining_seconds) || 60;
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
          const serverCooldown = Number(data.cooldown_remaining_seconds || 0);
          if (serverCooldown > 0 && resendBtn) {
            let countdown = serverCooldown;
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
          } else if (resendBtn && !forgotOtpCountdownTimer) {
            resendBtn.disabled = false;
          }
        }
      } catch (err) {
        if (msgEl) { msgEl.style.color = 'var(--danger)'; msgEl.textContent = 'Lỗi kết nối máy chủ.'; }
        if (resendBtn && !forgotOtpCountdownTimer) {
          resendBtn.disabled = false;
        }
      }
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = 'Gửi mã OTP';
        btn.classList.remove('loading');
      }
    }

    async function submitForgotVerifyOtp() {
      const otpInput = document.getElementById('mobileForgotOtp');
      const msgEl = document.getElementById('mobileForgotOtpMsg');
      const btn = document.getElementById('mobileBtnForgotVerifyOtp');
      const stepOtp = document.getElementById('mobileForgotStepOtp');
      const stepReset = document.getElementById('mobileForgotStepReset');
      const stepLabel = document.getElementById('mobileForgotStepLabel');
      const stepDesc = document.getElementById('mobileForgotStepDesc');
      const otp = (otpInput ? otpInput.value : '').trim();
      if (!forgotEmail) {
        if (msgEl) {
          msgEl.style.color = 'var(--danger)';
          msgEl.textContent = 'Thiếu địa chỉ email. Vui lòng quay lại Bước 1.';
        }
        return;
      }
      if (otp.length !== 6 || !/^\d{6}$/.test(otp)) {
        if (msgEl) {
          msgEl.style.color = 'var(--danger)';
          msgEl.textContent = 'Vui lòng nhập đúng 6 chữ số OTP.';
        }
        return;
      }
      if (msgEl) msgEl.textContent = '';
      if (btn) {
        btn.disabled = true;
        btn.textContent = 'Đang kiểm tra OTP...';
      }
      try {
        const res = await fetch('/api/auth3/layer2_verify_otp', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: forgotEmail,
            otp_code: otp,
            purpose: 'forgot_password',
            source: 'mobile_app_forgot_step2'
          })
        });
        const data = await res.json().catch(() => ({}));
        if (isHttpOk(res) && data && data.ok) {
          if (stepOtp) stepOtp.style.display = 'none';
          if (stepReset) stepReset.style.display = 'grid';
          if (stepLabel) stepLabel.textContent = 'Bước 3/3';
          if (stepDesc) stepDesc.textContent = 'Nhập mật khẩu mới và xác nhận lại.';
        } else {
          if (stepOtp) stepOtp.style.display = 'grid';
          if (stepReset) stepReset.style.display = 'none';
          if (stepLabel) stepLabel.textContent = 'Bước 2/3';
          const errRaw = (data && (data.error || data.message)) || '';
          const errText = (res.status === 429 || /hết hạn|chưa có/i.test(errRaw))
            ? errRaw
            : 'Mã OTP không chính xác';
          if (msgEl) {
            msgEl.style.color = 'var(--danger)';
            msgEl.textContent = errText;
          }
        }
      } catch (_err) {
        if (stepOtp) stepOtp.style.display = 'grid';
        if (stepReset) stepReset.style.display = 'none';
        if (stepLabel) stepLabel.textContent = 'Bước 2/3';
        if (msgEl) {
          msgEl.style.color = 'var(--danger)';
          msgEl.textContent = 'Lỗi kết nối máy chủ khi kiểm tra OTP.';
        }
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.textContent = 'Xác nhận mã';
        }
      }
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

      if (!forgotEmail || !/^\d{6}$/.test(otp)) {
        if (msgEl) { msgEl.style.color = 'var(--danger)'; msgEl.textContent = 'Thiếu email hoặc mã OTP 6 chữ số.'; }
        return;
      }
      if (!pw1 || !pw2) {
        if (msgEl) { msgEl.style.color = 'var(--danger)'; msgEl.textContent = 'Vui lòng nhập đầy đủ 2 ô mật khẩu.'; }
        return;
      }
      if (pw1.length < 6) {
        if (msgEl) { msgEl.style.color = 'var(--danger)'; msgEl.textContent = 'Mật khẩu phải có từ 6 ký tự trở lên!'; }
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
            otp_code: otp,
            otp: otp,
            new_password: pw1,
            confirm_password: pw2
          })
        });
        const data = await res.json().catch(() => ({}));
        if (isHttpOk(res) && data.ok) {
          const successMsg = data.message || 'Đặt lại mật khẩu thành công. Hãy đăng nhập bằng mật khẩu mới.';
          if (msgEl) { msgEl.style.color = 'var(--accent)'; msgEl.textContent = successMsg; }
          if (pw1El) pw1El.value = '';
          if (pw2El) pw2El.value = '';
          if (otpEl) otpEl.value = '';
          setTimeout(() => {
            closeForgotPassword();
            const loginEmail = document.getElementById('mobileLoginEmail');
            if (loginEmail) loginEmail.value = forgotEmail;
            const loginMsg = document.getElementById('mobileLoginMsg');
            if (loginMsg) { loginMsg.style.color = 'var(--accent)'; loginMsg.textContent = successMsg; }
          }, 900);
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
      if (!mobileLoggedIn) {
        const scrim = document.getElementById('mobileVoiceSheetScrim');
        const sheet = document.getElementById('mobileVoiceBottomSheet');
        if (scrim) scrim.hidden = true;
        if (sheet) sheet.hidden = true;
        setMobileVoiceButtonsVisualState(false);
        showMobileActionError('Vui lòng đăng nhập trước khi sử dụng điều khiển giọng nói.', true);
        openMobileLoginGate(true);
        return;
      }
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
      if (!mobileLoggedIn) {
        closeVoiceBottomSheet();
        showMobileActionError('Vui lòng đăng nhập trước khi sử dụng điều khiển giọng nói.', true);
        openMobileLoginGate(true);
        return;
      }
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

      if (!mobileLoggedIn) {
        closeVoiceBottomSheet();
        showMobileActionError('Vui lòng đăng nhập trước khi sử dụng điều khiển giọng nói.', true);
        openMobileLoginGate(true);
        return;
      }

      const pcm16k_b64 = mobileUint8ChunksToBase64(capturedChunks);
      let isPass = false;
      let roleName = getMobileTierLabel(mobileTier, mobileRole);
      let errMessage = 'Không thu được giọng nói hợp lệ. Vui lòng thử lại.';
      let cmdData = null;

      if (!pcm16k_b64 && !spokenInSheet) {
        isPass = false;
        errMessage = recordedDuration < 1
          ? 'Âm thanh quá ngắn hoặc không thu được micro.'
          : 'Không có âm thanh hoặc nội dung giọng nói để xử lý.';
      } else {
        try {
          cmdData = await executeMobileVoiceCommandHttp({
            pcm16k_b64: pcm16k_b64 || undefined,
            transcript: spokenInSheet || undefined,
            is_live_mic: true,
          });
          if (cmdData && cmdData.speaker_name) {
            roleName = cmdData.speaker_name;
          }
          if (cmdData && cmdData.ok === true && cmdData.authorized !== false && !cmdData.rbac_blocked && !cmdData.silent) {
            isPass = true;
          } else {
            isPass = false;
            errMessage = (cmdData && (cmdData.error || cmdData.rejection_speech || cmdData.exact_spoken_reply || cmdData.reply))
              || 'Không nhận diện được lệnh hoặc phiên không hợp lệ.';
          }
        } catch (e) {
          isPass = false;
          errMessage = 'Lỗi kết nối máy chủ khi xử lý giọng nói.';
        }
      }

      if (title) title.textContent = isPass ? 'Đã thực hiện lệnh' : 'Không thành công';
      if (resEl) {
        resEl.style.display = 'block';
        if (isPass) {
          const saidSummary = (cmdData && cmdData.recognized_text) || spokenInSheet || '';
          const replySummary = (cmdData && (cmdData.exact_spoken_reply || cmdData.reply)) || '';
          resEl.textContent = '';
          const strong = document.createElement('strong');
          strong.textContent = `✓ Đã xử lý · ${roleName}`;
          resEl.appendChild(strong);
          if (saidSummary) {
            resEl.appendChild(document.createElement('br'));
            const sp1 = document.createElement('span');
            sp1.textContent = `Bạn nói: ${saidSummary}`;
            resEl.appendChild(sp1);
          }
          if (replySummary) {
            resEl.appendChild(document.createElement('br'));
            const sp2 = document.createElement('span');
            sp2.textContent = replySummary;
            resEl.appendChild(sp2);
          }
          resEl.style.color = '#15803d';
          if (btnContinue) btnContinue.style.display = 'block';
        } else {
          resEl.textContent = `✗ ${errMessage}`;
          resEl.style.color = 'var(--danger)';
          if (btnRetry) btnRetry.style.display = 'block';
          if (btnClose) btnClose.style.display = 'block';
        }
      }
      setMobileVoiceButtonsVisualState(false);
      if (isPass && cmdData && cmdData.recognized_text) {
        setTimeout(() => {
          closeVoiceBottomSheet();
        }, 450);
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
        const data = await res.json().catch(() => ({}));
        if (isHttpOk(res) && data.ok) {
          if (status) status.textContent = '✅ Bắt tay thành công! Đang chuyển hướng...';
          setTimeout(() => {
            closeQrScanner();
            if (typeof location !== 'undefined') {
              location.href = `/guest?token=${encodeURIComponent(token)}`;
            }
          }, 800);
        } else {
          if (status) {
            status.textContent = data.error || 'Mã QR này không hợp lệ hoặc đã hết hạn.';
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

    function getMobileDeviceControl(devId, fallbackState = 'OFF') {
      if (!mobileDeviceControlState[devId]) {
        const initSt = String(fallbackState || 'OFF').toUpperCase();
        mobileDeviceControlState[devId] = {
          seq: 0,
          desiredState: initSt,
          confirmedState: initSt,
          serverKnownState: initSt,
          serverKnownVersion: 0,
          serverKnownRevisionSeq: mobileLastRevisionSeq,
          needsServerKnownSync: false,
          lastConfirmedSeq: 0,
          pendingCount: 0,
          debounceTimer: null,
          lastClickTs: 0,
          lastVersion: 0,
        };
      }
      return mobileDeviceControlState[devId];
    }

    function applyMobileDeviceOptimisticUI(devId, nextState, explicitBtnEl = null) {
      const nextIsOn = nextState === 'ON' || nextState === 'OPEN';
      if (latestSnap && Array.isArray(latestSnap.devices)) {
        const d = latestSnap.devices.find(x => x.id === devId);
        if (d) d.state = nextState;
      }

      const grid = document.getElementById('devGrid');
      const card = grid ? grid.querySelector(`[data-device-id="${devId}"]`) : null;
      if (card) {
        card.classList.toggle('on', nextIsOn);
        card.classList.toggle('off', !nextIsOn);
        card.setAttribute('data-state', nextIsOn ? 'on' : 'off');
      }

      const quickMap = {
        living_room_light: 'mobileQuickBtnLight',
        fan: 'mobileQuickBtnFan',
        main_door: 'mobileQuickBtnDoor',
      };
      const qBtn = explicitBtnEl || (quickMap[devId] ? document.getElementById(quickMap[devId]) : null);
      if (qBtn) {
        if (qBtn.classList) {
          qBtn.classList.toggle('on', nextIsOn);
          qBtn.classList.toggle('active', nextIsOn);
          qBtn.classList.toggle('off', !nextIsOn);
        }
        qBtn.setAttribute('aria-pressed', nextIsOn ? 'true' : 'false');
        if (qBtn.dataset) qBtn.dataset.state = nextIsOn ? 'on' : 'off';
      }
    }

    function reconcileMobileIdleToServerKnown(devId, ctrl, dType = 'light', btnEl = null) {
      if (!ctrl || ctrl.pendingCount > 0 || ctrl.debounceTimer !== null) return false;
      const knownVer = Number(ctrl.serverKnownVersion || 0);
      const curVer = Number(ctrl.lastVersion || 0);
      if (!ctrl.needsServerKnownSync && !(knownVer > 0 && knownVer > curVer)) {
        return false;
      }
      pendingDeviceMutations.delete(devId);
      const authNewer = String(
        ctrl.serverKnownState || ctrl.confirmedState || (dType === 'door' ? 'CLOSED' : 'OFF')
      ).toUpperCase();
      ctrl.confirmedState = authNewer;
      ctrl.desiredState = authNewer;
      ctrl.lastVersion = Math.max(curVer, knownVer);
      ctrl.needsServerKnownSync = false;
      if (latestSnap && Array.isArray(latestSnap.devices)) {
        const sd = latestSnap.devices.find(x => x.id === devId);
        if (sd) {
          sd.state = authNewer;
          sd.version = ctrl.lastVersion;
        }
      }
      applyMobileDeviceOptimisticUI(devId, authNewer, btnEl);
      return true;
    }

    function dispatchMobileDeviceSetState(devId, dName, dType, mySeq, targetState, myTs, btnEl = null) {
      const ctrl = getMobileDeviceControl(devId, targetState);
      if (mySeq < ctrl.seq) return Promise.resolve(null);

      const isTargetOn = targetState === 'ON' || targetState === 'OPEN';
      const action = dType === 'door' ? (isTargetOn ? 'open' : 'close') : (isTargetOn ? 'turn_on' : 'turn_off');
      const reqId = `${MOBILE_CLIENT_ID}:${devId}:${mySeq}`;
      ctrl.pendingCount += 1;

      const rollbackIfLatest = () => {
        if (mySeq !== ctrl.seq) {
          reconcileMobileIdleToServerKnown(devId, ctrl, dType, btnEl);
          return;
        }
        pendingDeviceMutations.delete(devId);
        const hasNewerKnown =
          Number(ctrl.serverKnownVersion || 0) > Number(ctrl.lastVersion || 0) && Boolean(ctrl.serverKnownState);
        const revertState = String(
          hasNewerKnown ? ctrl.serverKnownState : (ctrl.confirmedState || (dType === 'door' ? 'CLOSED' : 'OFF'))
        ).toUpperCase();
        ctrl.confirmedState = revertState;
        ctrl.desiredState = revertState;
        if (hasNewerKnown) {
          ctrl.lastVersion = Math.max(Number(ctrl.lastVersion || 0), Number(ctrl.serverKnownVersion || 0));
        }
        ctrl.needsServerKnownSync = false;
        applyMobileDeviceOptimisticUI(devId, revertState, btnEl);
      };

      return fetch('/api/device', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_id: devId,
          action,
          target_state: targetState,
          state: targetState,
          client_id: MOBILE_CLIENT_ID,
          client_seq: mySeq,
          client_ts_ms: myTs,
          request_id: reqId,
          source: 'mobile_app',
        }),
      })
        .then(async res => {
          const data = await res.json().catch(() => ({}));
          return { httpStatus: res.status, okHttp: isHttpOk(res), data };
        })
        .then(({ httpStatus, okHttp, data }) => {
          ctrl.pendingCount = Math.max(0, ctrl.pendingCount - 1);
          if (mySeq < ctrl.seq) {
            reconcileMobileIdleToServerKnown(devId, ctrl, dType, btnEl);
            return data;
          }
          if (!okHttp || !data || data.ok === false || data.error) {
            rollbackIfLatest();
            const errTxt = (data && (data.error || data.message)) ||
              (httpStatus === 401
                ? 'Vui lòng đăng nhập để điều khiển thiết bị.'
                : httpStatus === 403
                  ? 'Bạn không có quyền điều khiển thiết bị này.'
                  : 'Không thể điều khiển thiết bị.');
            if (httpStatus === 401) {
              handleMobileUnauthorized(errTxt);
            } else {
              showMobileActionError(errTxt, false);
            }
            addLog(`${dName}: ${errTxt}`, 'device', 'Thất bại');
            return Object.assign({ ok: false, _httpStatus: httpStatus }, data || {});
          }
          const respVer = Number(
            data && data.device_version !== undefined && data.device_version !== null ? data.device_version : 0
          );
          const respRev = Number(
            data && data.revision_seq !== undefined && data.revision_seq !== null
              ? data.revision_seq
              : (data && data.snapshot && data.snapshot.revision_seq ? data.snapshot.revision_seq : 0)
          );
          const maxKnownVer = Math.max(Number(ctrl.lastVersion || 0), Number(ctrl.serverKnownVersion || 0));
          const maxKnownDevRev = Math.max(
            Number(mobileLastRevisionSeq || 0),
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
            reconcileMobileIdleToServerKnown(devId, ctrl, dType, btnEl);
            return data;
          }
          if (data && data.stale_ignored) {
            pendingDeviceMutations.delete(devId);
            const authState = String((data && data.state) || ctrl.confirmedState || (dType === 'door' ? 'CLOSED' : 'OFF')).toUpperCase();
            ctrl.confirmedState = authState;
            ctrl.desiredState = authState;
            ctrl.serverKnownState = authState;
            ctrl.needsServerKnownSync = false;
            if (respVer > 0) {
              ctrl.lastVersion = Math.max(ctrl.lastVersion, respVer);
              ctrl.serverKnownVersion = Math.max(ctrl.serverKnownVersion || 0, respVer);
            }
            if (respRev > 0) {
              mobileLastRevisionSeq = Math.max(mobileLastRevisionSeq, respRev);
              ctrl.serverKnownRevisionSeq = Math.max(ctrl.serverKnownRevisionSeq || 0, respRev);
            }
            applyMobileDeviceOptimisticUI(devId, authState, btnEl);
            if (data.snapshot) {
              renderState(data.snapshot);
            }
            return data;
          }
          showMobileActionError('');
          const finalState = String((data && data.state) || targetState).toUpperCase();
          ctrl.confirmedState = finalState;
          ctrl.desiredState = finalState;
          ctrl.serverKnownState = finalState;
          ctrl.needsServerKnownSync = false;
          ctrl.lastConfirmedSeq = Math.max(ctrl.lastConfirmedSeq, mySeq);
          if (respVer > 0) {
            ctrl.lastVersion = Math.max(ctrl.lastVersion, respVer);
            ctrl.serverKnownVersion = Math.max(ctrl.serverKnownVersion || 0, respVer);
          }
          if (respRev > 0) {
            mobileLastRevisionSeq = Math.max(mobileLastRevisionSeq, respRev);
            ctrl.serverKnownRevisionSeq = Math.max(ctrl.serverKnownRevisionSeq || 0, respRev);
          }
          if (ctrl.pendingCount === 0 && ctrl.debounceTimer === null) {
            pendingDeviceMutations.delete(devId);
          }
          applyMobileDeviceOptimisticUI(devId, finalState, btnEl);
          if (data && data.snapshot) {
            renderState(data.snapshot);
          }
          addLog(`${dName}: ${isTargetOn ? 'Bật' : 'Tắt'}`, 'device', 'Thành công');
          return data;
        })
        .catch(() => {
          ctrl.pendingCount = Math.max(0, ctrl.pendingCount - 1);
          if (mySeq < ctrl.seq) {
            reconcileMobileIdleToServerKnown(devId, ctrl, dType, btnEl);
            return null;
          }
          rollbackIfLatest();
          showMobileActionError('Lỗi kết nối khi điều khiển thiết bị.', false);
          addLog(`${dName}: Lỗi kết nối`, 'device', 'Thất bại');
          return null;
        });
    }

    function scheduleMobileDeviceToggle(devId, btnEl = null, explicitTargetState = null) {
      if (!mobileLoggedIn) {
        const msg = 'Vui lòng đăng nhập để điều khiển thiết bị.';
        showMobileActionError(msg, true);
        addLog(`${devId}: ${msg}`, 'device', 'Thất bại');
        openMobileLoginGate(true);
        return Promise.resolve({ ok: false, error: msg });
      }
      const allDevs = (latestSnap && latestSnap.devices) ? latestSnap.devices : [];
      const d = allDevs.find(x => x.id === devId) || {
        id: devId,
        name: devId,
        type: devId === 'main_door' ? 'door' : 'light',
        state: 'OFF',
      };
      const ctrl = getMobileDeviceControl(devId, d.state);
      const effectiveState =
        ctrl.pendingCount > 0 || ctrl.debounceTimer !== null
          ? ctrl.desiredState || d.state
          : d.state;
      const prevIsOn = effectiveState === 'ON' || effectiveState === 'OPEN';
      let nextState;
      if (explicitTargetState && typeof explicitTargetState === 'string') {
        nextState = explicitTargetState.toUpperCase();
      } else {
        const nextIsOn = !prevIsOn;
        nextState = d.type === 'door' ? (nextIsOn ? 'OPEN' : 'CLOSED') : (nextIsOn ? 'ON' : 'OFF');
      }

      ctrl.seq += 1;
      const mySeq = ctrl.seq;
      const myTs = Date.now();
      ctrl.lastClickTs = myTs;
      ctrl.desiredState = nextState;

      pendingDeviceMutations.set(devId, {
        seq: mySeq,
        targetState: nextState,
        expiresAt: myTs + MUTATION_GUARD_WINDOW_MS,
      });

      applyMobileDeviceOptimisticUI(devId, nextState, btnEl);

      if (ctrl.debounceTimer !== null) {
        clearTimeout(ctrl.debounceTimer);
        ctrl.debounceTimer = null;
      }
      return new Promise(resolve => {
        ctrl.debounceTimer = setTimeout(() => {
          ctrl.debounceTimer = null;
          dispatchMobileDeviceSetState(devId, d.name || devId, d.type, mySeq, nextState, myTs, btnEl).then(resolve);
        }, MOBILE_DEVICE_DEBOUNCE_MS);
      });
    }

    async function toggleMobileDeviceQuick(devId, btnEl) {
      return scheduleMobileDeviceToggle(devId, btnEl);
    }
    if (typeof window !== 'undefined') {
      window.toggleMobileDeviceQuick = toggleMobileDeviceQuick;
    }

    function renderState(snap) {
      if (!snap) return;
      const snapRev = Number(snap.revision_seq || 0);
      const isStaleRevision = snapRev > 0 && mobileLastRevisionSeq > 0 && snapRev < mobileLastRevisionSeq;
      if (snapRev > mobileLastRevisionSeq) {
        mobileLastRevisionSeq = snapRev;
      }

      const rawDevices = Array.isArray(snap.devices) ? snap.devices : [];
      const now = Date.now();
      const allDevices = rawDevices.map(rawD => {
        if (!rawD || !rawD.id) return rawD;
        const d = Object.assign({}, rawD);
        const ctrl = getMobileDeviceControl(d.id, d.state);
        const serverSeq = Number(d.last_client_seq || 0);
        const serverVer = Number(d.version || 0);
        const sameClient = Boolean(d.last_client_id && d.last_client_id === MOBILE_CLIENT_ID);
        const hasPending = ctrl.debounceTimer !== null || ctrl.pendingCount > 0;
        const pendingMut = pendingDeviceMutations.get(d.id);

        if (
          !isStaleRevision &&
          (serverVer > Number(ctrl.serverKnownVersion || 0) ||
            (snapRev > Number(ctrl.serverKnownRevisionSeq || 0) &&
              serverVer >= Number(ctrl.serverKnownVersion || 0)))
        ) {
          ctrl.serverKnownVersion = Math.max(Number(ctrl.serverKnownVersion || 0), serverVer);
          if (snapRev > 0) {
            ctrl.serverKnownRevisionSeq = Math.max(Number(ctrl.serverKnownRevisionSeq || 0), snapRev);
          }
          if (rawD.state) {
            const nextKnownSt = String(rawD.state).toUpperCase();
            ctrl.serverKnownState = nextKnownSt;
            ctrl.confirmedState = nextKnownSt;
          }
          if (hasPending && !(sameClient && serverSeq >= ctrl.seq)) {
            ctrl.needsServerKnownSync = true;
          }
        }

        if (isStaleRevision && latestSnap && Array.isArray(latestSnap.devices)) {
          const prevD = latestSnap.devices.find(x => x.id === d.id);
          if (prevD) {
            if (prevD.state) d.state = prevD.state;
            if (prevD.version !== undefined) d.version = prevD.version;
            if (prevD.last_client_seq !== undefined) d.last_client_seq = prevD.last_client_seq;
            if (prevD.last_client_id !== undefined) d.last_client_id = prevD.last_client_id;
          }
          return d;
        }

        if (hasPending && !(sameClient && serverSeq >= ctrl.seq)) {
          d.state = ctrl.desiredState;
          return d;
        }

        if (serverVer > 0 && ctrl.lastVersion > 0 && serverVer < ctrl.lastVersion) {
          const prevD = (latestSnap && Array.isArray(latestSnap.devices))
            ? latestSnap.devices.find(x => x.id === d.id)
            : null;
          d.state = (prevD && prevD.state) ? prevD.state : (ctrl.confirmedState || d.state);
          d.version = ctrl.lastVersion;
          return d;
        }

        if (
          sameClient &&
          ctrl.lastConfirmedSeq > 0 &&
          serverSeq > 0 &&
          serverSeq < ctrl.lastConfirmedSeq &&
          serverVer <= ctrl.lastVersion
        ) {
          d.state = ctrl.desiredState;
          return d;
        }

        if (pendingMut) {
          if (
            now < pendingMut.expiresAt &&
            (!d.last_client_id || sameClient) &&
            serverSeq < ctrl.seq &&
            serverVer <= ctrl.lastVersion
          ) {
            if (d.state === pendingMut.targetState && !hasPending) {
              pendingDeviceMutations.delete(d.id);
            } else {
              d.state = pendingMut.targetState;
              return d;
            }
          } else if (!hasPending) {
            pendingDeviceMutations.delete(d.id);
          }
        }

        ctrl.confirmedState = d.state;
        ctrl.serverKnownState = String(d.state || '').toUpperCase();
        if (!hasPending) {
          ctrl.desiredState = d.state;
          ctrl.needsServerKnownSync = false;
          if (sameClient && serverSeq > ctrl.seq) ctrl.seq = serverSeq;
        }
        if (sameClient && serverSeq > ctrl.lastConfirmedSeq) ctrl.lastConfirmedSeq = serverSeq;
        if (serverVer > ctrl.lastVersion) ctrl.lastVersion = serverVer;
        ctrl.serverKnownVersion = Math.max(Number(ctrl.serverKnownVersion || 0), ctrl.lastVersion);
        if (snapRev > 0) {
          ctrl.serverKnownRevisionSeq = Math.max(Number(ctrl.serverKnownRevisionSeq || 0), snapRev);
        }
        return d;
      });

      const effectiveSnapRev = isStaleRevision ? mobileLastRevisionSeq : Math.max(snapRev, mobileLastRevisionSeq);
      snap = Object.assign({}, snap, { revision_seq: effectiveSnapRev, devices: allDevices });
      latestSnap = snap;
      const filtered = allDevices.filter(d => {
        const roomLabel = d.room || ROOM_NAMES[d.id] || 'Phòng khách';
        return selectedRoomFilter === 'all' || roomLabel === selectedRoomFilter;
      });
      const visibleDevices = showAllDevices ? filtered : filtered.slice(0, 4);

      const grid = document.getElementById('devGrid');
      if (!grid) return;

      // 2. In-place DOM update without wiping grid.innerHTML
      const currentCards = Array.from(grid.querySelectorAll('[data-device-id]'));
      const visibleIds = new Set(visibleDevices.map(d => d.id));

      // Remove cards that are no longer visible (e.g. room filtering)
      currentCards.forEach((c) => {
        const id = c.getAttribute('data-device-id');
        if (!visibleIds.has(id)) {
          grid.removeChild(c);
        }
      });

      // Update existing cards or append new ones
      visibleDevices.forEach((d) => {
        const isOn = d.state === 'ON' || d.state === 'OPEN';
        const roomLabel = d.room || ROOM_NAMES[d.id] || 'Phòng khách';
        let card = grid.querySelector(`[data-device-id="${d.id}"]`);

        if (!card) {
          card = document.createElement('div');
          card.setAttribute('data-device-id', d.id);
          card.setAttribute('data-state', isOn ? 'on' : 'off');
          card.className = `dev-row ${isOn ? 'on' : 'off'}`;
          card.innerHTML = `
            <span class="dev-icon">${ICONS[d.type] || '<svg class="icon"><use href="#i-lamp"/></svg>'}</span>
            <div class="dev-copy">
              <div class="dev-name">${d.name}</div>
              <div class="dev-room">${roomLabel}</div>
            </div>
            <span class="switch" aria-hidden="true"></span>
          `;
          if (!card.dataset.toggleListenerBound) {
            card.dataset.toggleListenerBound = '1';
            card._toggleListenerCount = 1;
            card.addEventListener('click', (e) => {
              e.preventDefault();
              toggleDev(d.id);
            });
          }
          grid.appendChild(card);
        } else {
          // In-place update class without rebinding listener
          card.classList.toggle('on', isOn);
          card.classList.toggle('off', !isOn);
          card.setAttribute('data-state', isOn ? 'on' : 'off');
          const nameEl = card.querySelector('.dev-name');
          if (nameEl && nameEl.textContent !== d.name) nameEl.textContent = d.name;
          const roomEl = card.querySelector('.dev-room');
          if (roomEl && roomEl.textContent !== roomLabel) roomEl.textContent = roomLabel;
        }
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

      const online = snap.server_connected !== false;
      if (snap.authenticated === false && mobileLoggedIn) {
        updateMobileAuthUiState(false);
      } else {
        updateMobileAuthUiState(online);
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

    async function toggleDev(devId, explicitTargetState = null) {
      return scheduleMobileDeviceToggle(devId, null, explicitTargetState);
    }
    if (typeof window !== 'undefined') {
      window.toggleDev = toggleDev;
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

    let mobileOutAudioCtx = null;
    let mobileNextPlayTime = 0;

    function resampleMobileFloat32AntiAliased(rawInput, actualSr, targetSr = 16000) {
      if (!actualSr || actualSr === targetSr || !rawInput || rawInput.length === 0) {
        return rawInput;
      }
      const outLen = Math.max(1, Math.round((rawInput.length * targetSr) / actualSr));
      const output = new Float32Array(outLen);
      const ratio = rawInput.length / outLen;
      for (let i = 0; i < outLen; i++) {
        const start = i * ratio;
        const end = (i + 1) * ratio;
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
      return output;
    }

    function playMobilePcm24kOrSpeakVi(pcm24kB64, fallbackText) {
      if (pcm24kB64) {
        try {
          const AudioCtx = window.AudioContext || window.webkitAudioContext;
          if (AudioCtx) {
            if (!mobileOutAudioCtx) {
              mobileOutAudioCtx = new AudioCtx({ sampleRate: 24000 });
            }
            if (mobileOutAudioCtx.state === 'suspended') {
              mobileOutAudioCtx.resume();
            }
            const binaryStr = window.atob(pcm24kB64);
            const len = binaryStr.length;
            const int16Arr = new Int16Array(len / 2);
            for (let i = 0; i < len; i += 2) {
              int16Arr[i / 2] = binaryStr.charCodeAt(i) | (binaryStr.charCodeAt(i + 1) << 8);
            }
            const float32Arr = new Float32Array(int16Arr.length);
            for (let i = 0; i < int16Arr.length; i++) {
              float32Arr[i] = int16Arr[i] / 32768.0;
            }
            const audioBuffer = mobileOutAudioCtx.createBuffer(1, float32Arr.length, 24000);
            audioBuffer.getChannelData(0).set(float32Arr);
            const source = mobileOutAudioCtx.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(mobileOutAudioCtx.destination);
            const now = mobileOutAudioCtx.currentTime;
            if (mobileNextPlayTime < now) {
              mobileNextPlayTime = now + 0.02;
            }
            source.start(mobileNextPlayTime);
            mobileNextPlayTime += audioBuffer.duration;
            return;
          }
        } catch (_) {}
      }
      // Chỉ phát âm thanh 24kHz PCM từ giọng Aoede của Gemini Live (không dùng browser TTS fallback)
    }

    async function executeMobileVoiceCommandHttp(payload) {
      const badge = document.getElementById('voiceStateBadge');
      if (!mobileLoggedIn) {
        const msg = 'Vui lòng đăng nhập trước khi sử dụng điều khiển giọng nói.';
        if (badge) badge.textContent = 'Chưa đăng nhập';
        showPwaVoiceResults(null, msg);
        showMobileActionError(msg, true);
        openMobileLoginGate(true);
        return { ok: false, authorized: false, error: msg };
      }
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
        const data = await res.json().catch(() => ({}));
        const saidText = data.recognized_text || (payload && payload.transcript) || 'Khẩu lệnh giọng nói';
        if (!isHttpOk(res) || data.ok === false || data.authorized === false || data.rbac_blocked) {
          const errReply = data.error || data.rejection_speech || data.exact_spoken_reply ||
            (res.status === 401
              ? 'Vui lòng đăng nhập trước khi sử dụng điều khiển giọng nói.'
              : res.status === 403
                ? 'Bạn không có quyền thực hiện lệnh giọng nói này.'
                : 'Không thể xử lý lệnh giọng nói.');
          showPwaVoiceResults(saidText, errReply);
          if (badge) badge.textContent = res.status === 401 ? 'Chưa đăng nhập' : 'Thất bại';
          addLog(saidText, 'voice', 'Thất bại');
          if (res.status === 401) {
            handleMobileUnauthorized(errReply);
          } else {
            showMobileActionError(errReply, false);
          }
          return Object.assign({ ok: false, authorized: false, _httpStatus: res.status, error: errReply }, data);
        }
        const replyText = data.exact_spoken_reply || data.reply || 'Đã thực hiện lệnh.';
        showPwaVoiceResults(saidText, replyText);
        playMobilePcm24kOrSpeakVi(data.pcm24k_b64, replyText);
        if (badge) badge.textContent = 'Sẵn sàng';
        addLog(saidText, 'voice', 'Thành công');
        if (data.snapshot) {
          renderState(data.snapshot);
        } else {
          await fetchInitial();
        }
        return data;
      } catch (err) {
        if (badge) badge.textContent = 'Thất bại';
        showPwaVoiceResults(null, 'Lỗi kết nối máy chủ khi gửi lệnh giọng nói.');
        return { ok: false, authorized: false, error: String(err) };
      }
    }
    if (typeof window !== 'undefined') {
      window.executeMobileVoiceCommandHttp = executeMobileVoiceCommandHttp;
    }

    async function toggleMobileVoiceListen() {
      const badge = document.getElementById('voiceStateBadge');
      const label = document.getElementById('btnMobileMicLabel');
      if (!mobileLoggedIn) {
        isMobileListening = false;
        if (badge) badge.textContent = 'Chưa đăng nhập';
        if (label) label.textContent = 'Bắt đầu nói';
        const msg = 'Vui lòng đăng nhập trước khi sử dụng điều khiển giọng nói.';
        showPwaVoiceResults(null, msg);
        showMobileActionError(msg, true);
        openMobileLoginGate(true);
        return;
      }
      isMobileListening = !isMobileListening;

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
          const pcm16k_b64 = chunks.length > 0 ? mobileUint8ChunksToBase64(chunks) : '';
          if (!pcm16k_b64 && !transcriptHint) {
            if (badge) badge.textContent = 'Thất bại';
            showPwaVoiceResults(null, 'Không thu được âm thanh micro hoặc kết nối giọng nói chưa sẵn sàng.');
            return;
          }
          await executeMobileVoiceCommandHttp({
            pcm16k_b64: pcm16k_b64 || undefined,
            transcript: transcriptHint || undefined,
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
          isMobileListening = false;
          stopMobileSpeechRecognitionVi();
          if (badge) badge.textContent = 'Thất bại';
          if (label) label.textContent = 'Bắt đầu nói';
          showPwaVoiceResults(null, 'Trình duyệt không hỗ trợ thu âm micro.');
          openMobileMicPermissionModal();
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
          const rawInput = e.inputBuffer.getChannelData(0);
          const actualSr = mobileAudioContext ? mobileAudioContext.sampleRate : 16000;
          const input = resampleMobileFloat32AntiAliased(rawInput, actualSr, 16000);
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
        isMobileListening = false;
        stopMobileSpeechRecognitionVi();
        if (badge) badge.textContent = 'Thất bại';
        if (label) label.textContent = 'Bắt đầu nói';
        showPwaVoiceResults(null, 'Không thể truy cập micro. Vui lòng cấp quyền micro.');
        openMobileMicPermissionModal();
      }
    }

    async function executeMobileCommand(text) {
      const badge = document.getElementById('voiceStateBadge');
      if (!mobileLoggedIn) {
        const msg = 'Vui lòng đăng nhập trước khi sử dụng điều khiển giọng nói.';
        if (badge) badge.textContent = 'Chưa đăng nhập';
        showPwaVoiceResults(text, msg);
        showMobileActionError(msg, true);
        openMobileLoginGate(true);
        return { ok: false, error: msg };
      }
      showPwaVoiceResults(text, 'Đang xử lý...');
      if (badge) badge.textContent = 'Đang xử lý';
      try {
        const res = await fetch('/api/text_command', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text }),
        });
        const data = await res.json().catch(() => ({}));
        if (!isHttpOk(res) || data.ok === false || data.rbac_blocked) {
          const errReply = data.error || data.rejection_speech || data.exact_spoken_reply ||
            (res.status === 401
              ? 'Vui lòng đăng nhập để điều khiển thiết bị.'
              : res.status === 403
                ? 'Bạn không có quyền thực hiện lệnh này.'
                : 'Không thể thực hiện lệnh.');
          showPwaVoiceResults(text, errReply);
          if (badge) badge.textContent = res.status === 401 ? 'Chưa đăng nhập' : 'Thất bại';
          addLog(text, 'voice', 'Thất bại');
          if (res.status === 401) {
            handleMobileUnauthorized(errReply);
          } else {
            showMobileActionError(errReply, false);
          }
          return Object.assign({ ok: false, _httpStatus: res.status, error: errReply }, data);
        }
        const reply = data.said || data.exact_spoken_reply || data.reply || 'Đã thực hiện lệnh.';
        showPwaVoiceResults(text, reply);
        if (badge) badge.textContent = 'Sẵn sàng';
        addLog(text, 'voice', 'Thành công');
        showMobileActionError('');
        fetchInitial().catch(() => {});
        return data;
      } catch (err) {
        if (badge) badge.textContent = 'Thất bại';
        showPwaVoiceResults(text, 'Lỗi kết nối máy chủ.');
        return { ok: false, error: String(err) };
      }
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
      const badge = document.getElementById('mobileActorBadge');
      const form = document.getElementById('mobileAddEmailForm');
      const targetTierSel = document.getElementById('mobileTargetTierSelect');
      const msg = document.getElementById('mobileAllowlistMsg');
      const tierInfoEl = document.getElementById('mobileVoiceTierInfo');
      const regNameEl = document.getElementById('mobileVoiceRegName');

      const tier = mobileLoggedIn ? (Number(mobileTier) || 0) : 0;
      const tierDescs = {
        1: 'Cấp 1 — Chủ nhà: toàn quyền điều khiển',
        2: 'Cấp 2 — Gia đình: điều khiển cơ bản',
        3: 'Cấp 3 — Khách: quyền hạn tạm thời'
      };
      const label = mobileLoggedIn ? getMobileTierLabel(tier, mobileRole) : 'Chưa đăng nhập';

      if (badge) badge.textContent = label;
      if (tierInfoEl) tierInfoEl.textContent = tierDescs[tier] || 'Chưa đăng nhập';
      if (regNameEl) regNameEl.textContent = label;

      if (mobileLoggedIn && tier === 1) {
        if (form) form.style.display = 'grid';
        if (targetTierSel) targetTierSel.innerHTML = `<option value="2">Gia đình</option><option value="3">Khách</option>`;
        if (msg) {
          msg.style.color = 'var(--muted)';
          msg.textContent = 'Chủ nhà được thêm Gia đình và Khách.';
        }
      } else {
        if (form) form.style.display = 'none';
        if (msg) {
          msg.style.color = 'var(--danger)';
          msg.textContent = 'Chỉ Chủ nhà (Cấp 1) mới có quyền thêm thành viên.';
        }
      }
    }

    async function submitMobileAddEmail() {
      const msg = document.getElementById('mobileAllowlistMsg');
      if (!mobileLoggedIn || Number(mobileTier) !== 1) {
        if (msg) {
          msg.style.color = 'var(--danger)';
          msg.textContent = 'Chỉ Chủ nhà (Cấp 1) mới có quyền thêm thành viên.';
        }
        return;
      }
      const targetTier = parseInt((document.getElementById('mobileTargetTierSelect') || {}).value || '2', 10);
      const targetEmailEl = document.getElementById('mobileTargetEmail');
      const targetEmail = (targetEmailEl ? targetEmailEl.value : '').trim();
      if (!targetEmail) {
        if (msg) {
          msg.style.color = 'var(--danger)';
          msg.textContent = 'Vui lòng nhập email thành viên.';
        }
        return;
      }
      try {
        const res = await fetch('/api/auth3/family_allowlist/add', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            actor_email: mobileLoggedInEmail,
            target_email: targetEmail,
            target_tier: targetTier,
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (isHttpOk(res) && data.ok) {
          if (msg) {
            msg.style.color = 'var(--accent)';
            msg.textContent = data.message || 'Đã lưu tài khoản thành viên.';
          }
          if (targetEmailEl) targetEmailEl.value = '';
          addLog(`Thêm quyền cho ${targetEmail}`, 'device', 'Thành công');
        } else {
          if (res.status === 401) {
            handleMobileUnauthorized('Vui lòng đăng nhập lại.');
            return;
          }
          if (msg) {
            msg.style.color = 'var(--danger)';
            msg.textContent = data.error || 'Không thể thêm tài khoản.';
          }
        }
      } catch (_) {
        if (msg) {
          msg.style.color = 'var(--danger)';
          msg.textContent = 'Lỗi kết nối máy chủ.';
        }
      }
    }

    async function submitMobileVoiceSample() {
      const box = document.getElementById('mobileVoiceRes');
      const errMsg = 'Tính năng thu mẫu giọng nói trên trình duyệt đã bị tắt.';
      if (box) {
        box.textContent = errMsg;
        box.style.color = 'var(--muted)';
      }
      return { ok: false, error: errMsg };
    }

    async function copyMobileGuestLink() {
      const url = document.getElementById('mobileQrUrlText')?.textContent || location.origin + '/guest';
      try {
        await navigator.clipboard.writeText(url);
        document.getElementById('mobileQrCountdown').textContent = 'Đã sao chép';
      } catch (e) {}
    }

    const proto = location.protocol === 'https:' ? 'wss' : 'ws';

    const isLocalMobileHost = (typeof location !== 'undefined') && (
      location.hostname === 'localhost' || location.hostname === '127.0.0.1'
    );

    const isMobileVercel = (typeof window !== 'undefined') && (
      (typeof location !== 'undefined' && Boolean((location.hostname || location.host || '').includes('vercel.app'))) ||
      !isLocalMobileHost ||
      Boolean(window._FORCE_HTTP_POLLING)
    );

    function connectMobileWebSocket() {
      if (isMobileVercel || !isLocalMobileHost || (typeof window !== 'undefined' && window._disableWebSocket)) {
        /* On Vercel serverless or non-localhost domains, skip WebSocket and poll HTTP cleanly */
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
        if (msg.type === 'device_updated' && msg.device_id) {
          const devId = msg.device_id;
          const ctrl = getMobileDeviceControl(devId, msg.new_state || 'OFF');
          const msgVer = Number(msg.version || 0);
          const msgSeq = Number(msg.last_client_seq || 0);
          const msgRev = Number(msg.revision_seq || 0);
          const sameClient = Boolean(msg.last_client_id && msg.last_client_id === MOBILE_CLIENT_ID);
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
            if (hasPending && !(sameClient && msgSeq >= ctrl.seq)) {
              ctrl.needsServerKnownSync = true;
            }
          }
          const pendingMut = pendingDeviceMutations.get(devId);
          const hasActiveHold = Boolean(
            pendingMut &&
            Date.now() < pendingMut.expiresAt &&
            (!msg.last_client_id || sameClient) &&
            msgSeq < ctrl.seq &&
            msgVer <= ctrl.lastVersion
          );
          const isStaleMsg =
            (msgRev > 0 && mobileLastRevisionSeq > 0 && msgRev < mobileLastRevisionSeq) ||
            (msgVer > 0 && ctrl.lastVersion > 0 && msgVer < ctrl.lastVersion) ||
            (sameClient && ctrl.lastConfirmedSeq > 0 && msgSeq > 0 && msgSeq < ctrl.lastConfirmedSeq && msgVer <= ctrl.lastVersion) ||
            (hasPending && !(sameClient && msgSeq >= ctrl.seq)) ||
            hasActiveHold;

          if (!isStaleMsg && msg.new_state) {
            const nextSt = String(msg.new_state).toUpperCase();
            if (msgVer > ctrl.lastVersion) ctrl.lastVersion = msgVer;
            if (msgRev > mobileLastRevisionSeq) mobileLastRevisionSeq = msgRev;
            if (sameClient && msgSeq > ctrl.lastConfirmedSeq) {
              ctrl.lastConfirmedSeq = msgSeq;
              if (msgSeq > ctrl.seq) ctrl.seq = msgSeq;
            }
            ctrl.confirmedState = nextSt;
            if (!hasPending) {
              ctrl.desiredState = nextSt;
              ctrl.needsServerKnownSync = false;
              pendingDeviceMutations.delete(devId);
            }
            if (latestSnap && Array.isArray(latestSnap.devices)) {
              const nextDevs = latestSnap.devices.map(d => {
                if (!d || d.id !== devId) return d;
                return Object.assign({}, d, {
                  state: nextSt,
                  version: msgVer > 0 ? Math.max(Number(d.version || 0), msgVer) : d.version,
                  last_client_seq: msgSeq > 0 ? msgSeq : d.last_client_seq,
                  last_client_id: msg.last_client_id || d.last_client_id,
                });
              });
              renderState(Object.assign({}, latestSnap, {
                revision_seq: msgRev > 0 ? Math.max(Number(latestSnap.revision_seq || 0), msgRev) : latestSnap.revision_seq,
                devices: nextDevs,
              }));
            } else {
              applyMobileDeviceOptimisticUI(devId, nextSt);
            }
            addLog(`${msg.device_name || devId}: ${nextSt}`, 'device');
          }
        }
        if (msg.type === 'input_transcription') {
          showPwaVoiceResults(msg.full_text, null);
        }
        if (msg.type === 'output_transcription') {
          showPwaVoiceResults(null, msg.full_text);
          const badge = document.getElementById('voiceStateBadge');
          if (badge) badge.textContent = 'Sẵn sàng';
        }
        if (msg.type === 'audio_chunk' && msg.pcm24k_b64) {
          window._lastMobileGeminiAudioChunkTs = performance.now();
          playMobilePcm24kOrSpeakVi(msg.pcm24k_b64, '');
        }
        if (msg.type === 'voice_auth_rejected') {
          const rejText = msg.rejection_speech || 'Tôi không nhận ra giọng của bạn.';
          showPwaVoiceResults(msg.label || null, rejText);
          const rejTs = performance.now();
          setTimeout(() => {
            if ((window._lastMobileGeminiAudioChunkTs || 0) < rejTs) {
              playMobilePcm24kOrSpeakVi('', rejText);
            }
          }, 650);
          const badge = document.getElementById('voiceStateBadge');
          if (badge) badge.textContent = 'Cần thử lại';
        }
      };
      ws.onclose = () => {
        fetch('/api/state')
          .then(r => (r.ok ? r.json() : Promise.reject()))
          .then(d2 => {
            updateMobileAuthUiState(d2 && d2.server_connected !== false);
            renderState(d2);
          })
          .catch(() => {
            updateMobileAuthUiState(false);
          });
        /* Auto-reconnect after 4s only when on localhost and logged in */
        if (!isMobileVercel && isLocalMobileHost) {
          setTimeout(() => { if (mobileLoggedIn) connectMobileWebSocket(); }, 4000);
        }
      };
      ws.onerror = () => {};
    }

    function updateMobileQrCountdownLabel(rem) {
      const cdEl = document.getElementById('mobileQrCountdown');
      if (cdEl) {
        cdEl.textContent = `Đổi mã sau ${rem}s`;
        cdEl.style.color = rem <= 3 ? '#c83e3b' : 'var(--muted)';
      }
    }

    async function refreshMobileQr10s() {
      // Auto QR polling disabled; Owner creates invites explicitly via POST /api/auth3/guest_invites with PIN
      return;
    }

    async function createMobileGuestInvite() {
      const statusEl = document.getElementById('mobileQrInviteStatus');
      const btn = document.getElementById('mobileBtnCreateGuestQr');
      if (!mobileLoggedIn || Number(mobileTier) !== 1) {
        if (statusEl) {
          statusEl.style.color = 'var(--danger)';
          statusEl.textContent = 'Chỉ Chủ nhà (Cấp 1) mới có quyền tạo lời mời QR.';
        }
        return;
      }
      const durSel = document.getElementById('mobileGuestDurSelect');
      const tierSel = document.getElementById('mobileQrInviteTierSelect');
      const pinEl = document.getElementById('mobileQrPinInput');
      const pinConfEl = document.getElementById('mobileQrPinConfirmInput');
      const dur = durSel ? durSel.value : '1d';
      const ttlMap = { '1d': 86400, '2d': 172800, '1w': 604800, '1m': 2592000, '1y': 31536000 };
      const ttlSec = ttlMap[dur] || 86400;
      const inviteTier = parseInt((tierSel ? tierSel.value : '3') || '3', 10);
      const pin = (pinEl ? pinEl.value : '').trim();
      const pinConfirm = (pinConfEl ? pinConfEl.value : '').trim();

      if (!/^\d{4,6}$/.test(pin)) {
        if (statusEl) {
          statusEl.style.color = 'var(--danger)';
          statusEl.textContent = 'Vui lòng nhập mã PIN Chủ nhà gồm 4–6 chữ số.';
        }
        return;
      }
      if (btn) { btn.disabled = true; btn.textContent = 'Đang tạo mã...'; }
      try {
        const res = await fetch('/api/auth3/guest_invites', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            tier: inviteTier,
            ttl_sec: ttlSec,
            duration: dur,
            pin: pin,
            pin_confirm: pinConfirm || pin,
          }),
        });
        const d = await res.json().catch(() => ({}));
        if (!isHttpOk(res) || !d.ok) {
          if (statusEl) {
            statusEl.style.color = 'var(--danger)';
            statusEl.textContent = d.error || 'Không thể tạo lời mời QR.';
          }
        } else {
          const inviteUrl = d.public_guest_url || d.full_url || d.qr_url || d.url || (`/guest?token=${encodeURIComponent(d.token || '')}`);
          const tokEl = document.getElementById('mobileQrTokenText');
          const urlEl = document.getElementById('mobileQrUrlText');
          const linkEl = document.getElementById('mobileQrOpenLink');
          const cdEl = document.getElementById('mobileQrCountdown');
          if (tokEl) tokEl.textContent = `${d.token || ''}`;
          if (urlEl) urlEl.textContent = inviteUrl;
          if (linkEl) {
            linkEl.href = inviteUrl;
            linkEl.style.display = 'inline-flex';
          }
          if (cdEl) cdEl.textContent = 'Đã tạo mã mời';
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
          }
          if (statusEl) {
            statusEl.style.color = 'var(--accent)';
            statusEl.textContent = '✅ Đã tạo lời mời QR thành công.';
          }
        }
      } catch (_) {
        if (statusEl) {
          statusEl.style.color = 'var(--danger)';
          statusEl.textContent = 'Lỗi kết nối khi tạo lời mời QR.';
        }
      }
      if (btn) { btn.disabled = false; btn.textContent = 'Tạo lời mời QR'; }
    }

    async function pollMobileSecurityAndTimers() {
      if (!mobileLoggedIn) {
        updateMobileAuthUiState(false);
        return;
      }
      if (mobilePollInFlight) return;
      mobilePollInFlight = true;
      try {
        const r2 = await fetch('/api/state');
        const d2 = await r2.json().catch(() => ({}));
        let d1 = {};
        if (mobileLoggedIn && Number(mobileTier) === 1) {
          try {
            const r1 = await fetch('/api/auth3/overview');
            if (r1.ok) d1 = await r1.json();
          } catch (_) {}
        }
        if (d2 && d2.devices) {
          renderState(d2);
        }
        const stBadge = document.getElementById('mobileStrikeBadge');
        if (stBadge && d1.security_status) {
          const st = d1.security_status;
          const fails = st.failed_voice_attempts ?? st.failed_attempts ?? 0;
          const maxAtt = st.max_attempts ?? 3;
          stBadge.textContent = `${fails}/${maxAtt}`;
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
        updateMobileAuthUiState(false);
      } finally {
        mobilePollInFlight = false;
      }
    }

    function onMobileQrInviteTierChange() {
      const statusEl = document.getElementById('mobileQrInviteStatus');
      if (statusEl) statusEl.textContent = '';
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
      fetchInitial().catch(() => {});
      renderMobileHistory();
      if (!mobilePollIntervalId) {
        mobilePollIntervalId = setInterval(pollMobileSecurityAndTimers, 2000);
      }
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
window.createMobileGuestInvite = createMobileGuestInvite;
window.pollMobileSecurityAndTimers = pollMobileSecurityAndTimers;
window.submitMobileLogin = submitMobileLogin;
window.sendMobileLayer2Otp = sendMobileLayer2Otp;
window.verifyMobileLayer2Otp = verifyMobileLayer2Otp;
window.cancelMobileOtpPanel = cancelMobileOtpPanel;
window.openMobileLoginGate = openMobileLoginGate;
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
window.connectMobileWebSocket = connectMobileWebSocket;
