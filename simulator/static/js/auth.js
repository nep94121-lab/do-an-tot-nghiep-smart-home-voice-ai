if (typeof window !== 'undefined' && typeof window.fetch === 'function' && !window._shAuthFetchWrapped) {
  const _origFetch = window.fetch.bind(window);
  window.fetch = function(input, init) {
    const urlStr = typeof input === 'string' ? input : (input && input.url ? input.url : '');
    if (urlStr.startsWith('/api/')) {
      let tok = '';
      try {
        tok = (window.sessionStorage && window.sessionStorage.getItem('session_token')) ||
              (window.localStorage && window.localStorage.getItem('session_token')) || '';
        if (!tok && window.localStorage) {
          const rawSess = window.localStorage.getItem('smarthome_auth_session');
          if (rawSess) {
            const parsed = JSON.parse(rawSess);
            tok = (parsed && parsed.session_token) || '';
          }
        }
      } catch (_) {}
      const nextInit = Object.assign({ credentials: 'same-origin' }, init || {});
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

const tierBadgeClass = (t) => t === 1 ? 'badge-tier1' : (t === 2 ? 'badge-tier2' : 'badge-tier3');
const tierRoleLabel = (t) => t === 1 ? 'Chủ nhà (Cấp 1)' : (t === 2 ? 'Gia đình (Cấp 2)' : 'Khách (Cấp 3)');

let currentSessionUser = null;

function escapeAuthHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function setAuthStatusBox(box, text, isError) {
  if (!box) return;
  box.style.borderColor = isError ? 'var(--red-border)' : '#cce5e3';
  box.style.background = isError ? 'var(--red-soft)' : 'var(--accent-soft)';
  box.textContent = text;
}

function formatAuthApiError(res, data, fallbackMsg) {
  let msg = (data && (data.error || data.message)) || fallbackMsg;
  if (res && res.status === 429) {
    const retryAfter = Number((data && data.retry_after_seconds) || (res.headers && res.headers.get && res.headers.get('Retry-After')) || 0);
    if (retryAfter > 0 && msg.indexOf(String(retryAfter)) === -1) {
      msg += ` (Thử lại sau ${retryAfter} giây.)`;
    }
  }
  return msg;
}

async function requestForgotPasswordOtpAuthPage() {
  const emailEl = document.getElementById('loginEmail');
  const email = emailEl ? emailEl.value.trim() : '';
  const box = document.getElementById('loginStatusBox');
  const btn = document.getElementById('btnSendForgotOtpAuth') || document.querySelector('button[onclick*="requestForgotPasswordOtpAuthPage"]');
  const resendBtn = document.getElementById('btnResendForgotOtpAuth');

  if (!email) {
    setAuthStatusBox(box, 'Vui lòng nhập Email tài khoản cần khôi phục mật khẩu.', true);
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="btn-spinner"></span> Đang gửi mã...';
    btn.classList.add('loading');
  }
  if (resendBtn && resendBtn !== btn) {
    resendBtn.disabled = true;
  }

  try {
    const res = await fetch('/api/auth3/forgot_password_send_otp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, send_gmail: true, source: 'auth_page_forgot' })
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok && data.ok && (!data.gmail_delivery || data.gmail_delivery.sent_real_gmail !== false)) {
      const resetSec = document.getElementById('authForgotResetSection');
      if (resetSec) {
        resetSec.style.display = 'grid';
        resetSec.hidden = false;
      }
      setAuthStatusBox(box, data.message || `Đã gửi mã OTP khôi phục mật khẩu tới ${email}.`, false);
      let remainingSec = Number(data.cooldown_remaining_seconds) || 60;
      const targetBtns = [btn, resendBtn].filter(Boolean);
      targetBtns.forEach((b) => {
        b.disabled = true;
        b.classList.remove('loading');
        b.textContent = `Gửi lại sau (${remainingSec}s)`;
      });
      if (window._authForgotOtpTimer) clearInterval(window._authForgotOtpTimer);
      window._authForgotOtpTimer = setInterval(() => {
        remainingSec--;
        if (remainingSec <= 0) {
          clearInterval(window._authForgotOtpTimer);
          window._authForgotOtpTimer = null;
          if (btn) {
            btn.disabled = false;
            btn.innerHTML = 'Gửi mã OTP';
          }
          if (resendBtn) {
            resendBtn.disabled = false;
            resendBtn.textContent = 'Gửi lại OTP';
          }
        } else {
          targetBtns.forEach((b) => {
            b.textContent = `Gửi lại sau (${remainingSec}s)`;
          });
        }
      }, 1000);
    } else {
      const errNote = (data.gmail_delivery && data.gmail_delivery.note) || 'Không gửi được mã OTP.';
      setAuthStatusBox(box, formatAuthApiError(res, data, errNote), true);
      if (btn) {
        btn.disabled = false;
        btn.classList.remove('loading');
        btn.innerHTML = 'Gửi mã OTP';
      }
      if (resendBtn) {
        resendBtn.disabled = false;
        resendBtn.textContent = 'Gửi lại OTP';
      }
    }
  } catch (err) {
    setAuthStatusBox(box, 'Lỗi kết nối máy chủ khi gửi OTP.', true);
    if (btn) {
      btn.disabled = false;
      btn.classList.remove('loading');
      btn.innerHTML = 'Gửi mã OTP';
    }
    if (resendBtn) {
      resendBtn.disabled = false;
      resendBtn.textContent = 'Gửi lại OTP';
    }
  }
}

async function submitForgotPasswordResetAuthPage() {
  const emailEl = document.getElementById('loginEmail');
  const otpEl = document.getElementById('otpInput');
  const pwEl = document.getElementById('authForgotNewPassword');
  const confirmEl = document.getElementById('authForgotConfirmPassword');
  const btn = document.getElementById('btnSubmitForgotResetAuth');
  const box = document.getElementById('loginStatusBox');

  const email = emailEl ? emailEl.value.trim() : '';
  const otpCode = otpEl ? otpEl.value.trim() : '';
  const newPassword = pwEl ? pwEl.value : '';
  const confirmPassword = confirmEl ? confirmEl.value : '';

  if (!email || !otpCode || !newPassword || !confirmPassword) {
    setAuthStatusBox(box, 'Vui lòng nhập đầy đủ Email, mã OTP 6 số và 2 ô mật khẩu mới.', true);
    return;
  }
  if (newPassword.length < 6) {
    setAuthStatusBox(box, 'Mật khẩu mới phải có tối thiểu 6 ký tự.', true);
    return;
  }
  if (newPassword !== confirmPassword) {
    setAuthStatusBox(box, 'Hai ô mật khẩu mới không khớp nhau.', true);
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Đang đặt lại...';
  }
  try {
    const res = await fetch('/api/auth3/forgot_password_reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email,
        otp_code: otpCode,
        new_password: newPassword,
        confirm_password: confirmPassword,
        source: 'auth_page_forgot'
      })
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok && data.ok) {
      setAuthStatusBox(box, data.message || 'Đặt lại mật khẩu thành công. Hãy đăng nhập bằng mật khẩu mới.', false);
      if (otpEl) otpEl.value = '';
      if (pwEl) pwEl.value = '';
      if (confirmEl) confirmEl.value = '';
    } else {
      setAuthStatusBox(box, formatAuthApiError(res, data, 'Không đặt lại được mật khẩu.'), true);
    }
  } catch (err) {
    setAuthStatusBox(box, 'Lỗi kết nối máy chủ khi đặt lại mật khẩu.', true);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Đặt lại mật khẩu';
    }
  }
}

function renderFamilyAllowlist(list) {
  const tbody = document.getElementById('familyAllowlistTableBody');
  if (!tbody) return;
  tbody.innerHTML = '';
  (list || []).forEach((item) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${escapeAuthHtml(item.email)}</td>
      <td><span class="badge ${tierBadgeClass(item.target_tier)}">${tierRoleLabel(item.target_tier)}</span></td>
      <td style="font-size:11px; color:var(--muted);">${escapeAuthHtml(item.added_by_email || 'Chủ nhà')}</td>
      <td><span class="badge badge-pass">Hoàn tất</span></td>
    `;
    tbody.appendChild(tr);
  });
}

async function submitAddFamilyEmail() {
  if (!currentSessionUser || Number(currentSessionUser.tier) !== 1) return;
  const targetTier = parseInt((document.getElementById('allowlistTargetTierSelect') || {}).value || '2', 10);
  const targetEmailEl = document.getElementById('allowlistTargetEmail');
  const targetEmail = targetEmailEl ? targetEmailEl.value.trim() : '';
  const box = document.getElementById('allowlistStatusBox');

  if (!targetEmail) {
    setAuthStatusBox(box, 'Vui lòng nhập email thành viên cần thêm.', true);
    return;
  }

  try {
    const res = await fetch('/api/auth3/family_allowlist/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        actor_email: currentSessionUser.email || '',
        target_email: targetEmail,
        target_tier: targetTier
      })
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok && data.ok) {
      setAuthStatusBox(box, data.message || 'Đã thêm thành viên vào danh sách.', false);
      if (targetEmailEl) targetEmailEl.value = '';
      renderFamilyAllowlist(data.family_allowlist || []);
      loadOverview();
    } else {
      setAuthStatusBox(box, data.error || 'Chưa thêm được email. Vui lòng kiểm tra lại.', true);
    }
  } catch (_) {
    setAuthStatusBox(box, 'Lỗi kết nối máy chủ.', true);
  }
}

async function execOwnerVoicePermission(cmdText) {
  if (!currentSessionUser || Number(currentSessionUser.tier) !== 1) return;
  const inputEl = document.getElementById('voicePermCommandInput');
  const box = document.getElementById('voicePermStatusBox');
  const cmd = String(cmdText || (inputEl ? inputEl.value : '') || '').trim();
  if (!cmd) {
    setAuthStatusBox(box, 'Vui lòng nhập lệnh phân quyền.', true);
    return;
  }
  try {
    const res = await fetch('/api/auth3/voice_permission_command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command_text: cmd, caller_tier: 1 })
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok && data.ok) {
      setAuthStatusBox(box, data.message || 'Đã cập nhật quyền truy cập.', false);
    } else {
      setAuthStatusBox(box, data.error || 'Không thể cập nhật quyền.', true);
    }
    loadOverview();
  } catch (_) {
    setAuthStatusBox(box, 'Lỗi kết nối máy chủ.', true);
  }
}

async function generateAuthGuestQr() {
  if (!currentSessionUser || Number(currentSessionUser.tier) !== 1) return;
  const durSel = document.getElementById('authQrDurationSelect');
  const tierSel = document.getElementById('authQrTargetTierSelect');
  const pinEl = document.getElementById('authQrPinInput');
  const pinConfirmEl = document.getElementById('authQrPinConfirmInput');
  const tokenBox = document.getElementById('authQrTokenBox');
  const badge = document.getElementById('authQrCountdownBadge');
  const svgBox = document.getElementById('authDynamicQrBox');

  const ttlSec = parseInt((durSel && durSel.value) || '600', 10);
  const targetTier = parseInt((tierSel && tierSel.value) || '3', 10);
  const pin = pinEl ? pinEl.value.trim() : '';
  const pinConfirm = pinConfirmEl ? pinConfirmEl.value.trim() : '';

  try {
    const res = await fetch('/api/auth3/guest_invites', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tier: targetTier, ttl_sec: ttlSec, pin, pin_confirm: pinConfirm })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) {
      if (data && data.needs_pin_setup && pinConfirmEl) {
        pinConfirmEl.style.display = 'inline-block';
        pinConfirmEl.hidden = false;
      }
      setAuthStatusBox(tokenBox, data.error || 'Không tạo được mã QR mời.', true);
      return;
    }

    if (svgBox && data.qr_svg) {
      svgBox.innerHTML = data.qr_svg;
      const svgEl = svgBox.querySelector('svg');
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
    }
    if (badge) {
      badge.textContent = 'Đang hiệu lực';
      badge.className = 'badge badge-tier1';
    }
    const openLink = document.getElementById('authQrOpenLink');
    if (openLink && data.path) {
      openLink.href = data.path;
    } else if (openLink && data.token) {
      openLink.href = `/guest?token=${encodeURIComponent(data.token)}`;
    }
    const roleDesc = targetTier === 2 ? 'Thành viên gia đình (Cấp 2)' : 'Khách đến chơi nhà (Cấp 3)';
    setAuthStatusBox(tokenBox, `Đã tạo mã QR cho: ${roleDesc}.`, false);
  } catch (_) {
    setAuthStatusBox(tokenBox, 'Lỗi kết nối máy chủ khi tạo mã QR.', true);
  }
}

async function checkOwnerPinStatusForAuthPage() {
  if (!currentSessionUser || Number(currentSessionUser.tier) !== 1) return;
  try {
    const res = await fetch('/api/auth3/owner_pin/status');
    if (!res.ok) return;
    const data = await res.json().catch(() => ({}));
    const pinConfirmEl = document.getElementById('authQrPinConfirmInput');
    if (pinConfirmEl && data && data.pin_set === false) {
      pinConfirmEl.style.display = 'inline-block';
      pinConfirmEl.hidden = false;
    }
  } catch (_) {}
}

async function loadOverview() {
  if (!currentSessionUser || Number(currentSessionUser.tier) !== 1) return;
  try {
    const res = await fetch('/api/auth3/overview');
    if (!res.ok) return;
    const data = await res.json().catch(() => ({}));
    if (!data || !data.ok) return;

    if (data.security_status) {
      const st = data.security_status;
      const strikeBadge = document.getElementById('globalStrikeBadge');
      if (strikeBadge) {
        if (st.Lockout_active || st.lockout_active) {
          strikeBadge.hidden = false;
          strikeBadge.textContent = 'Tạm khóa điều khiển do thử sai nhiều lần. Vui lòng thử lại sau.';
        } else {
          strikeBadge.hidden = true;
        }
      }
    }

    renderFamilyAllowlist(data.family_allowlist || []);

    const accBody = document.getElementById('accountsTableBody');
    if (accBody) {
      accBody.innerHTML = '';
      (data.accounts || []).forEach((a) => {
        const tr = document.createElement('tr');
        const activeBadge = a.active === false
          ? '<span class="badge badge-fail">Đã thu hồi / Chờ duyệt</span>'
          : '<span class="badge badge-pass">Đang hoạt động</span>';
        tr.innerHTML = `
          <td><span class="badge ${tierBadgeClass(a.tier)}">${tierRoleLabel(a.tier)}</span></td>
          <td><span style="font-weight:500;">${escapeAuthHtml(a.name || a.display_name || '')}</span><div style="color:var(--muted); font-size:11px;">${escapeAuthHtml(a.email || '')}</div></td>
          <td>${activeBadge}</td>
          <td><span class="badge">RBAC Cấp ${Number(a.tier || 3)}</span></td>
        `;
        accBody.appendChild(tr);
      });
    }

    const logBody = document.getElementById('authLogsTableBody');
    if (logBody) {
      logBody.innerHTML = '';
      (data.recent_logs || []).forEach((l) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${escapeAuthHtml(l.time || '')}</td>
          <td>${escapeAuthHtml(l.event || '')}</td>
          <td>${escapeAuthHtml(l.email || '—')}</td>
          <td style="color:var(--muted);">${escapeAuthHtml(l.detail || '')}</td>
        `;
        logBody.appendChild(tr);
      });
    }
  } catch (_) {}
}

async function logoutFromAuthPage() {
  try {
    await fetch('/api/auth/logout', { method: 'POST' });
  } catch (_) {}
  try {
    if (window.localStorage) {
      window.localStorage.removeItem('smarthome_auth_session');
      window.localStorage.removeItem('session_token');
    }
    if (window.sessionStorage) window.sessionStorage.clear();
    document.cookie = 'sh_session_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
    document.cookie = 'session_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
  } catch (_) {}
  window.location.href = '/login';
}

function showUnauthenticatedAuthView() {
  currentSessionUser = null;
  const gate = document.getElementById('authUnauthGate');
  const authShell = document.getElementById('authAuthenticatedPanels');
  const ownerSec = document.getElementById('authOwnerAdminSection');
  const nonOwnerSec = document.getElementById('authNonOwnerNotice');
  const badge = document.getElementById('currentSessionBadge');

  if (gate) {
    gate.style.display = 'block';
    gate.hidden = false;
  }
  if (authShell) {
    authShell.style.display = 'none';
    authShell.hidden = true;
  }
  if (ownerSec) {
    ownerSec.style.display = 'none';
    ownerSec.hidden = true;
  }
  if (nonOwnerSec) {
    nonOwnerSec.style.display = 'none';
    nonOwnerSec.hidden = true;
  }
  if (badge) {
    badge.className = 'badge';
    badge.textContent = 'Chưa đăng nhập';
  }
}

async function initAuthPageSessionGate() {
  try {
    const res = await fetch('/api/session/role');
    if (res.status === 401 || !res.ok) {
      showUnauthenticatedAuthView();
      return;
    }
    const data = await res.json().catch(() => ({}));
    if (!data || data.authenticated !== true) {
      showUnauthenticatedAuthView();
      return;
    }
    currentSessionUser = data;

    const gate = document.getElementById('authUnauthGate');
    const authShell = document.getElementById('authAuthenticatedPanels');
    const ownerSec = document.getElementById('authOwnerAdminSection');
    const nonOwnerSec = document.getElementById('authNonOwnerNotice');
    const badge = document.getElementById('currentSessionBadge');
    const summaryEl = document.getElementById('authCurrentAccountSummary');

    if (gate) {
      gate.style.display = 'none';
      gate.hidden = true;
    }
    if (authShell) {
      authShell.style.display = 'grid';
      authShell.hidden = false;
    }
    const tier = Number(data.tier || 3);
    if (badge) {
      badge.className = `badge ${tierBadgeClass(tier)}`;
      badge.textContent = tierRoleLabel(tier);
    }
    if (summaryEl) {
      const labelName = data.display_name || data.email || 'Người dùng';
      summaryEl.textContent = `${tierRoleLabel(tier)} · ${labelName}${data.email ? ' (' + data.email + ')' : ''}`;
    }

    if (tier === 1) {
      if (ownerSec) {
        ownerSec.style.display = 'grid';
        ownerSec.hidden = false;
      }
      if (nonOwnerSec) {
        nonOwnerSec.style.display = 'none';
        nonOwnerSec.hidden = true;
      }
      await loadOverview();
      await checkOwnerPinStatusForAuthPage();
    } else {
      if (ownerSec) {
        ownerSec.style.display = 'none';
        ownerSec.hidden = true;
      }
      if (nonOwnerSec) {
        nonOwnerSec.style.display = 'block';
        nonOwnerSec.hidden = false;
      }
    }
  } catch (_) {
    showUnauthenticatedAuthView();
  }
}

window.addEventListener('DOMContentLoaded', () => {
  initAuthPageSessionGate();
});

window.tierBadgeClass = tierBadgeClass;
window.tierRoleLabel = tierRoleLabel;
window.requestForgotPasswordOtpAuthPage = requestForgotPasswordOtpAuthPage;
window.submitForgotPasswordResetAuthPage = submitForgotPasswordResetAuthPage;
window.renderFamilyAllowlist = renderFamilyAllowlist;
window.submitAddFamilyEmail = submitAddFamilyEmail;
window.execOwnerVoicePermission = execOwnerVoicePermission;
window.generateAuthGuestQr = generateAuthGuestQr;
window.loadOverview = loadOverview;
window.logoutFromAuthPage = logoutFromAuthPage;
window.initAuthPageSessionGate = initAuthPageSessionGate;
