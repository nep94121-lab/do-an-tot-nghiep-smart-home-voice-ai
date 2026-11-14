(function () {
  'use strict';

  const STRICT_EMAIL_RE = /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$/;

  function setFieldInvalid(el, isInvalid) {
    if (!el || typeof el.setAttribute !== 'function' || typeof el.removeAttribute !== 'function') return;
    if (isInvalid) {
      el.setAttribute('aria-invalid', 'true');
    } else {
      el.removeAttribute('aria-invalid');
    }
  }

  function persistClientSession(data, email) {
    try {
      const sessionData = (data && data.session) || data || {};
      localStorage.setItem('smarthome_auth_session', JSON.stringify(sessionData));
      const activeTok = (data && data.session_token) || (sessionData && sessionData.session_id) || '';
      if (activeTok) {
        const tokStr = String(activeTok);
        localStorage.setItem('session_token', tokStr);
        sessionStorage.setItem('session_token', tokStr);
        const secure = (typeof location !== 'undefined' && location.protocol === 'https:') ? '; Secure' : '';
        document.cookie = 'sh_session_token=' + tokStr + '; path=/; SameSite=Lax' + secure;
        document.cookie = 'session_token=' + tokStr + '; path=/; SameSite=Lax' + secure;
      }
      sessionStorage.setItem('mobileLoggedIn', '1');
      if (email) sessionStorage.setItem('mobileLoggedInEmail', email);
    } catch (storageErr) {
      console.warn('Storage warning:', storageErr);
    }
  }

  function formatApiError(resp, data, fallbackMsg) {
    let msg = (data && (data.error || data.message)) || fallbackMsg;
    if (resp && resp.status === 429) {
      const retrySec = Number((data && data.retry_after_seconds) || (resp.headers && resp.headers.get && resp.headers.get('Retry-After')) || 0);
      if (retrySec > 0 && msg.indexOf(String(retrySec)) === -1) {
        msg += ' (Thử lại sau ' + retrySec + ' giây.)';
      }
    }
    return msg;
  }

  function initLoginPage() {
    const loginForm = document.getElementById('loginForm');
    if (!loginForm) return;

    const emailInput = document.getElementById('pageLoginEmail');
    const passwordInput = document.getElementById('pageLoginPassword');
    const submitBtn = document.getElementById('pageLoginSubmitBtn');
    const statusBox = document.getElementById('loginStatusBox');
    const loginOtpSection = document.getElementById('loginOtpSection');
    const loginOtpDesc = document.getElementById('loginOtpDesc');
    const loginOtpInput = document.getElementById('loginOtpInput');
    const btnVerifyLoginOtp = document.getElementById('btnVerifyLoginOtp');
    const btnResendLoginOtp = document.getElementById('btnResendLoginOtp');
    const btnCancelLoginOtp = document.getElementById('btnCancelLoginOtp');
    const forgotLink = document.getElementById('linkForgotPassword');
    const forgotPanel = document.getElementById('forgotPasswordPanel');
    const btnSendForgotOtp = document.getElementById('btnSendForgotOtp');
    const forgotEmailInput = document.getElementById('forgotEmailInput');
    const forgotResetStep = document.getElementById('forgotResetStep');
    const forgotOtpInput = document.getElementById('forgotOtpInput');
    const forgotNewPasswordInput = document.getElementById('forgotNewPasswordInput');
    const forgotConfirmPasswordInput = document.getElementById('forgotConfirmPasswordInput');
    const btnSubmitForgotReset = document.getElementById('btnSubmitForgotReset');
    const btnResendForgotOtp = document.getElementById('btnResendForgotOtp');
    const forgotStatusBox = document.getElementById('forgotStatusBox');

    let pendingOtpEmail = '';
    let loginOtpCooldownTimer = null;
    let forgotCooldownTimer = null;

    function showStatus(box, msg, isError) {
      if (!box) return;
      box.textContent = msg;
      box.style.display = 'block';
      box.className = isError ? 'status-box status-error' : 'status-box status-success';
    }

    function clearStatus(box) {
      if (!box) return;
      box.textContent = '';
      box.style.display = 'none';
    }

    function startCooldownTimer(buttons, initialSec, defaultLabels, timerKind) {
      let remainingSec = Number(initialSec) || 60;
      if (remainingSec < 1) remainingSec = 1;
      const validBtns = (buttons || []).filter(Boolean);
      if (timerKind === 'login' && loginOtpCooldownTimer) clearInterval(loginOtpCooldownTimer);
      if (timerKind === 'forgot' && forgotCooldownTimer) clearInterval(forgotCooldownTimer);

      function applyTick() {
        validBtns.forEach(function (b) {
          b.disabled = true;
          b.textContent = 'Gửi lại sau (' + remainingSec + 's)';
        });
      }
      applyTick();

      const handle = setInterval(function () {
        remainingSec -= 1;
        if (remainingSec <= 0) {
          clearInterval(handle);
          if (timerKind === 'login') loginOtpCooldownTimer = null;
          if (timerKind === 'forgot') forgotCooldownTimer = null;
          validBtns.forEach(function (b, idx) {
            b.disabled = false;
            b.textContent = (defaultLabels && defaultLabels[idx]) || 'Gửi lại OTP';
          });
        } else {
          applyTick();
        }
      }, 1000);

      if (timerKind === 'login') loginOtpCooldownTimer = handle;
      if (timerKind === 'forgot') forgotCooldownTimer = handle;
    }

    async function sendLayer2OtpForLogin(targetEmail) {
      if (!targetEmail) return;
      if (btnResendLoginOtp) {
        btnResendLoginOtp.disabled = true;
        btnResendLoginOtp.textContent = 'Đang gửi OTP...';
      }
      try {
        const otpResp = await fetch('/api/auth3/layer2_send_otp', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: targetEmail, source: 'dedicated_web_login' }),
        });
        const otpData = await otpResp.json().catch(function () { return {}; });
        if (otpResp.ok && otpData.ok) {
          const cdSec = Number(otpData.cooldown_remaining_seconds || 0);
          showStatus(statusBox, otpData.message || ('Đã gửi mã OTP 6 số tới ' + targetEmail + '.'), false);
          if (cdSec > 0) {
            startCooldownTimer([btnResendLoginOtp], cdSec, ['Gửi lại OTP'], 'login');
          } else if (btnResendLoginOtp) {
            btnResendLoginOtp.disabled = false;
            btnResendLoginOtp.textContent = 'Gửi lại OTP';
          }
        } else {
          showStatus(statusBox, formatApiError(otpResp, otpData, 'Không gửi được mã OTP đăng nhập.'), true);
          if (btnResendLoginOtp) {
            btnResendLoginOtp.disabled = false;
            btnResendLoginOtp.textContent = 'Gửi lại OTP';
          }
        }
      } catch (err) {
        showStatus(statusBox, 'Không thể kết nối máy chủ để gửi OTP.', true);
        if (btnResendLoginOtp) {
          btnResendLoginOtp.disabled = false;
          btnResendLoginOtp.textContent = 'Gửi lại OTP';
        }
      }
    }

    loginForm.addEventListener('submit', async function (e) {
      e.preventDefault();
      clearStatus(statusBox);

      const email = emailInput ? emailInput.value.trim() : '';
      const password = passwordInput ? passwordInput.value : '';

      if (!email) {
        showStatus(statusBox, 'Vui lòng nhập địa chỉ email.', true);
        if (emailInput) emailInput.focus();
        return;
      }
      if (!password) {
        showStatus(statusBox, 'Vui lòng nhập mật khẩu.', true);
        if (passwordInput) passwordInput.focus();
        return;
      }

      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Đang đăng nhập...';
      }

      try {
        const response = await fetch('/api/auth3/layer1_login', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            email: email,
            password: password,
            login_method: 'password',
            source: 'dedicated_web_login',
            send_gmail: true,
          }),
        });

        const data = await response.json().catch(function () { return {}; });

        if (response.ok && data.ok && data.otp_required === true) {
          pendingOtpEmail = email;
          loginForm.style.display = 'none';
          if (loginOtpSection) {
            loginOtpSection.style.display = 'flex';
            loginOtpSection.hidden = false;
          }
          if (loginOtpDesc) {
            loginOtpDesc.textContent = 'Đã xác minh mật khẩu cho ' + email + '. Đang gửi mã OTP 6 số qua Gmail...';
          }
          if (loginOtpInput) {
            loginOtpInput.value = '';
            loginOtpInput.focus();
          }
          await sendLayer2OtpForLogin(email);
        } else if (response.ok && data.ok && data.session_token) {
          showStatus(statusBox, 'Đăng nhập thành công! Đang chuyển hướng...', false);
          persistClientSession(data, email);
          setTimeout(function () {
            window.location.href = '/';
          }, 500);
        } else {
          const errMsg = formatApiError(response, data, 'Email hoặc mật khẩu không chính xác.');
          showStatus(statusBox, errMsg, true);
        }
      } catch (err) {
        showStatus(statusBox, 'Không thể kết nối đến máy chủ. Vui lòng thử lại sau.', true);
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = 'Đăng nhập';
        }
      }
    });

    if (btnVerifyLoginOtp) {
      btnVerifyLoginOtp.addEventListener('click', async function () {
        const otpCode = loginOtpInput ? loginOtpInput.value.trim() : '';
        const activeEmail = pendingOtpEmail || (emailInput ? emailInput.value.trim() : '');
        if (!activeEmail) {
          showStatus(statusBox, 'Thiếu email tài khoản cần xác thực OTP.', true);
          return;
        }
        if (!otpCode || otpCode.length < 6) {
          showStatus(statusBox, 'Vui lòng nhập đủ 6 chữ số mã OTP.', true);
          if (loginOtpInput) loginOtpInput.focus();
          return;
        }
        btnVerifyLoginOtp.disabled = true;
        btnVerifyLoginOtp.textContent = 'Đang xác minh OTP...';
        try {
          const vResp = await fetch('/api/auth3/layer2_verify_otp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              email: activeEmail,
              otp_code: otpCode,
              purpose: 'layer2_login',
              source: 'dedicated_web_login',
            }),
          });
          const vData = await vResp.json().catch(function () { return {}; });
          if (vResp.ok && vData.ok && vData.session_token) {
            showStatus(statusBox, 'Xác thực OTP thành công! Đang chuyển hướng...', false);
            persistClientSession(vData, activeEmail);
            setTimeout(function () {
              window.location.href = '/';
            }, 500);
          } else {
            showStatus(statusBox, formatApiError(vResp, vData, 'Mã OTP không chính xác hoặc đã hết hạn.'), true);
          }
        } catch (err) {
          showStatus(statusBox, 'Lỗi kết nối máy chủ khi xác minh OTP.', true);
        } finally {
          btnVerifyLoginOtp.disabled = false;
          btnVerifyLoginOtp.textContent = 'Xác nhận OTP & Đăng nhập';
        }
      });
    }

    if (btnResendLoginOtp) {
      btnResendLoginOtp.addEventListener('click', async function () {
        const activeEmail = pendingOtpEmail || (emailInput ? emailInput.value.trim() : '');
        await sendLayer2OtpForLogin(activeEmail);
      });
    }

    if (btnCancelLoginOtp) {
      btnCancelLoginOtp.addEventListener('click', function () {
        pendingOtpEmail = '';
        if (loginOtpSection) {
          loginOtpSection.style.display = 'none';
          loginOtpSection.hidden = true;
        }
        loginForm.style.display = 'flex';
        clearStatus(statusBox);
      });
    }

    if (forgotLink && forgotPanel) {
      forgotLink.addEventListener('click', function (e) {
        e.preventDefault();
        const isHidden = forgotPanel.style.display === 'none' || forgotPanel.hidden;
        if (isHidden) {
          forgotPanel.style.display = 'block';
          forgotPanel.hidden = false;
          if (forgotEmailInput && emailInput && !forgotEmailInput.value) {
            forgotEmailInput.value = emailInput.value;
          }
        } else {
          forgotPanel.style.display = 'none';
          forgotPanel.hidden = true;
        }
      });
    }

    async function handleSendForgotOtp(triggerBtn) {
      const fEmail = forgotEmailInput ? forgotEmailInput.value.trim() : '';
      if (!fEmail) {
        showStatus(forgotStatusBox, 'Vui lòng nhập email nhận mã OTP.', true);
        return;
      }
      if (triggerBtn) {
        triggerBtn.disabled = true;
        triggerBtn.textContent = 'Đang gửi...';
      }
      try {
        const resp = await fetch('/api/auth3/forgot_password_send_otp', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: fEmail, send_gmail: true, source: 'dedicated_web_forgot' }),
        });
        const resData = await resp.json().catch(function () { return {}; });
        if (resp.ok && resData.ok && (!resData.gmail_delivery || resData.gmail_delivery.sent_real_gmail !== false)) {
          showStatus(forgotStatusBox, resData.message || ('Mã OTP đã được gửi tới ' + fEmail), false);
          if (forgotResetStep) {
            forgotResetStep.style.display = 'block';
            forgotResetStep.hidden = false;
          }
          if (resData.cooldown_remaining_seconds) {
            startCooldownTimer([btnSendForgotOtp, btnResendForgotOtp], resData.cooldown_remaining_seconds, ['Gửi mã OTP', 'Gửi lại OTP'], 'forgot');
          } else {
            if (btnSendForgotOtp) {
              btnSendForgotOtp.disabled = false;
              btnSendForgotOtp.textContent = 'Gửi mã OTP';
            }
            if (btnResendForgotOtp) {
              btnResendForgotOtp.disabled = false;
              btnResendForgotOtp.textContent = 'Gửi lại OTP';
            }
          }
        } else {
          const errNote = (resData.gmail_delivery && resData.gmail_delivery.note) || 'Gửi OTP thất bại.';
          showStatus(forgotStatusBox, formatApiError(resp, resData, errNote), true);
          if (btnSendForgotOtp) {
            btnSendForgotOtp.disabled = false;
            btnSendForgotOtp.textContent = 'Gửi mã OTP';
          }
          if (btnResendForgotOtp) {
            btnResendForgotOtp.disabled = false;
            btnResendForgotOtp.textContent = 'Gửi lại OTP';
          }
        }
      } catch (fErr) {
        showStatus(forgotStatusBox, 'Lỗi kết nối máy chủ.', true);
        if (btnSendForgotOtp) {
          btnSendForgotOtp.disabled = false;
          btnSendForgotOtp.textContent = 'Gửi mã OTP';
        }
        if (btnResendForgotOtp) {
          btnResendForgotOtp.disabled = false;
          btnResendForgotOtp.textContent = 'Gửi lại OTP';
        }
      }
    }

    if (btnSendForgotOtp) {
      btnSendForgotOtp.addEventListener('click', function () {
        handleSendForgotOtp(btnSendForgotOtp);
      });
    }
    if (btnResendForgotOtp) {
      btnResendForgotOtp.addEventListener('click', function () {
        handleSendForgotOtp(btnResendForgotOtp);
      });
    }

    if (btnSubmitForgotReset) {
      btnSubmitForgotReset.addEventListener('click', async function () {
        const fEmail = forgotEmailInput ? forgotEmailInput.value.trim() : '';
        const otpCode = forgotOtpInput ? forgotOtpInput.value.trim() : '';
        const newPassword = forgotNewPasswordInput ? forgotNewPasswordInput.value : '';
        const confirmPassword = forgotConfirmPasswordInput ? forgotConfirmPasswordInput.value : '';

        if (!fEmail || !otpCode || !newPassword || !confirmPassword) {
          showStatus(forgotStatusBox, 'Vui lòng nhập đầy đủ Email, mã OTP 6 số và 2 ô mật khẩu mới.', true);
          return;
        }
        if (newPassword.length < 6) {
          showStatus(forgotStatusBox, 'Mật khẩu mới phải có từ 6 ký tự trở lên!', true);
          return;
        }
        if (newPassword !== confirmPassword) {
          showStatus(forgotStatusBox, 'Hai ô mật khẩu mới không khớp nhau.', true);
          return;
        }

        btnSubmitForgotReset.disabled = true;
        btnSubmitForgotReset.textContent = 'Đang đặt lại...';
        try {
          const resetResp = await fetch('/api/auth3/forgot_password_reset', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              email: fEmail,
              otp_code: otpCode,
              new_password: newPassword,
              confirm_password: confirmPassword,
              source: 'dedicated_web_forgot',
            }),
          });
          const resetData = await resetResp.json().catch(function () { return {}; });
          if (resetResp.ok && resetData.ok) {
            showStatus(statusBox, resetData.message || 'Đặt lại mật khẩu thành công. Hãy đăng nhập bằng mật khẩu mới.', false);
            clearStatus(forgotStatusBox);
            if (emailInput) emailInput.value = fEmail;
            if (passwordInput) passwordInput.value = '';
            if (forgotOtpInput) forgotOtpInput.value = '';
            if (forgotNewPasswordInput) forgotNewPasswordInput.value = '';
            if (forgotConfirmPasswordInput) forgotConfirmPasswordInput.value = '';
            if (forgotPanel) {
              forgotPanel.style.display = 'none';
              forgotPanel.hidden = true;
            }
          } else {
            showStatus(forgotStatusBox, formatApiError(resetResp, resetData, 'Không đặt lại được mật khẩu.'), true);
          }
        } catch (err) {
          showStatus(forgotStatusBox, 'Lỗi kết nối máy chủ khi đặt lại mật khẩu.', true);
        } finally {
          btnSubmitForgotReset.disabled = false;
          btnSubmitForgotReset.textContent = 'Đặt lại mật khẩu';
        }
      });
    }
  }

  function initRegisterPage() {
    const registerForm = document.getElementById('registerForm');
    if (!registerForm) return;

    const nameInput = document.getElementById('pageRegisterName');
    const emailInput = document.getElementById('pageRegisterEmail');
    const passwordInput = document.getElementById('pageRegisterPassword');
    const confirmPasswordInput = document.getElementById('pageRegisterConfirmPassword');
    const submitBtn = document.getElementById('pageRegisterSubmitBtn');
    const statusBox = document.getElementById('registerStatusBox');

    function showStatus(box, msg, isError) {
      if (!box) return;
      box.textContent = msg;
      box.style.display = 'block';
      box.className = isError ? 'status-box status-error' : 'status-box status-success';
    }

    function clearStatus(box) {
      if (!box) return;
      box.textContent = '';
      box.style.display = 'none';
    }

    function clearAllInvalidStates() {
      setFieldInvalid(emailInput, false);
      setFieldInvalid(passwordInput, false);
      setFieldInvalid(confirmPasswordInput, false);
    }

    [emailInput, passwordInput, confirmPasswordInput].forEach(function (inp) {
      if (inp && typeof inp.addEventListener === 'function') {
        inp.addEventListener('input', function () {
          setFieldInvalid(inp, false);
        });
      }
    });

    registerForm.addEventListener('submit', async function (e) {
      e.preventDefault();
      clearStatus(statusBox);
      clearAllInvalidStates();

      const name = nameInput ? nameInput.value.trim() : '';
      const email = emailInput ? emailInput.value.trim() : '';
      const password = passwordInput ? passwordInput.value : '';
      const confirmPassword = confirmPasswordInput ? confirmPasswordInput.value : '';

      if (!email || !STRICT_EMAIL_RE.test(email)) {
        showStatus(statusBox, 'Vui lòng nhập địa chỉ Email hợp lệ!', true);
        setFieldInvalid(emailInput, true);
        if (emailInput) emailInput.focus();
        return;
      }
      if (!password || password.length < 6) {
        showStatus(statusBox, 'Mật khẩu phải có từ 6 ký tự trở lên!', true);
        setFieldInvalid(passwordInput, true);
        if (passwordInput) passwordInput.focus();
        return;
      }
      if (password !== confirmPassword) {
        showStatus(statusBox, 'Hai ô mật khẩu không khớp nhau!', true);
        setFieldInvalid(confirmPasswordInput, true);
        if (confirmPasswordInput) confirmPasswordInput.focus();
        return;
      }

      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Đang xử lý đăng ký...';
      }

      try {
        const params = new URLSearchParams(window.location.search);
        const inviteToken = (params.get('invite_token') || params.get('token') || params.get('invite') || '').trim();
        const payload = {
          display_name: name,
          email: email,
          password: password,
          confirm_password: confirmPassword,
          source: 'dedicated_web_register',
        };
        if (inviteToken) payload.invite_token = inviteToken;

        const response = await fetch('/api/auth3/register_or_set_password', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
        });

        const data = await response.json().catch(function () { return {}; });

        if (response.ok && data.ok) {
          const hasActiveSession = Boolean(data.session_token && data.permission_active !== false);
          if (hasActiveSession) {
            persistClientSession(data, email);
            showStatus(statusBox, data.message || 'Đăng ký tài khoản thành công! Đang chuyển vào hệ thống...', false);
            setTimeout(function () {
              window.location.href = '/';
            }, 800);
          } else {
            const pendingMsg = data.message || 'Đã tạo tài khoản. Chờ chủ nhà cấp quyền và phê duyệt trước khi đăng nhập.';
            showStatus(statusBox, pendingMsg, false);
          }
        } else {
          const errMsg = formatApiError(response, data, 'Đăng ký không thành công. Vui lòng kiểm tra lại thông tin.');
          showStatus(statusBox, errMsg, true);
        }
      } catch (err) {
        showStatus(statusBox, 'Không thể kết nối đến máy chủ. Vui lòng thử lại sau.', true);
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = 'Đăng ký';
        }
      }
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    initLoginPage();
    initRegisterPage();
  });
})();
