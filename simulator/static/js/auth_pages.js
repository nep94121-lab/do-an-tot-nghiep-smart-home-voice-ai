/**
 * auth_pages.js — Controller for dedicated /login and /register pages.
 * Conforms to Smart Home Voice AI Design System (v1 light) and 0-inline-script security invariant.
 */

(function () {
  'use strict';

  function initLoginPage() {
    const loginForm = document.getElementById('loginForm');
    if (!loginForm) return;

    const emailInput = document.getElementById('pageLoginEmail');
    const passwordInput = document.getElementById('pageLoginPassword');
    const submitBtn = document.getElementById('pageLoginSubmitBtn');
    const statusBox = document.getElementById('loginStatusBox');
    const forgotLink = document.getElementById('linkForgotPassword');
    const forgotPanel = document.getElementById('forgotPasswordPanel');
    const btnSendForgotOtp = document.getElementById('btnSendForgotOtp');
    const forgotEmailInput = document.getElementById('forgotEmailInput');
    const forgotStatusBox = document.getElementById('forgotStatusBox');

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

        const data = await response.json();

        if (response.ok && data.ok) {
          showStatus(statusBox, 'Đăng nhập thành công! Đang chuyển hướng...', false);
          try {
            const sessionData = data.session || data;
            localStorage.setItem('smarthome_auth_session', JSON.stringify(sessionData));
            sessionStorage.setItem('mobileLoggedIn', '1');
            sessionStorage.setItem('mobileLoggedInEmail', email);
          } catch (storageErr) {
            console.warn('Storage warning:', storageErr);
          }
          setTimeout(function () {
            window.location.href = '/';
          }, 600);
        } else {
          const errMsg = data.error || data.message || 'Email hoặc mật khẩu không chính xác.';
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

    if (forgotLink && forgotPanel) {
      forgotLink.addEventListener('click', function (e) {
        e.preventDefault();
        const isHidden = forgotPanel.style.display === 'none' || forgotPanel.hidden;
        if (isHidden) {
          forgotPanel.style.display = 'block';
          forgotPanel.hidden = false;
          if (forgotEmailInput && emailInput) {
            forgotEmailInput.value = emailInput.value;
          }
        } else {
          forgotPanel.style.display = 'none';
          forgotPanel.hidden = true;
        }
      });
    }

    if (btnSendForgotOtp) {
      btnSendForgotOtp.addEventListener('click', async function () {
        const fEmail = forgotEmailInput ? forgotEmailInput.value.trim() : '';
        if (!fEmail) {
          showStatus(forgotStatusBox, 'Vui lòng nhập email nhận mã OTP.', true);
          return;
        }
        btnSendForgotOtp.disabled = true;
        btnSendForgotOtp.textContent = 'Đang gửi...';
        try {
          const resp = await fetch('/api/auth3/forgot_password_send_otp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: fEmail }),
          });
          const resData = await resp.json();
          if (resp.ok && resData.ok) {
            showStatus(forgotStatusBox, 'Mã OTP đã được gửi vào hộp thư ' + fEmail, false);
          } else {
            showStatus(forgotStatusBox, resData.error || 'Gửi OTP thất bại.', true);
          }
        } catch (fErr) {
          showStatus(forgotStatusBox, 'Lỗi kết nối máy chủ.', true);
        } finally {
          btnSendForgotOtp.disabled = false;
          btnSendForgotOtp.textContent = 'Gửi mã OTP';
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

    registerForm.addEventListener('submit', async function (e) {
      e.preventDefault();
      clearStatus(statusBox);

      const name = nameInput ? nameInput.value.trim() : '';
      const email = emailInput ? emailInput.value.trim() : '';
      const password = passwordInput ? passwordInput.value : '';
      const confirmPassword = confirmPasswordInput ? confirmPasswordInput.value : '';

      if (!name) {
        showStatus(statusBox, 'Vui lòng nhập họ và tên.', true);
        if (nameInput) nameInput.focus();
        return;
      }
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
      if (password.length < 6) {
        showStatus(statusBox, 'Mật khẩu phải có tối thiểu 6 ký tự.', true);
        if (passwordInput) passwordInput.focus();
        return;
      }
      if (password !== confirmPassword) {
        showStatus(statusBox, 'Hai ô mật khẩu không khớp nhau!', true);
        if (confirmPasswordInput) confirmPasswordInput.focus();
        return;
      }

      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Đang xử lý đăng ký...';
      }

      try {
        const response = await fetch('/api/auth3/register_or_set_password', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            display_name: name,
            email: email,
            password: password,
            confirm_password: confirmPassword,
            target_tier: 2,
            source: 'dedicated_web_register',
          }),
        });

        const data = await response.json();

        if (response.ok && data.ok) {
          showStatus(statusBox, 'Đăng ký tài khoản thành công! Đang chuyển tới trang đăng nhập...', false);
          setTimeout(function () {
            window.location.href = '/login';
          }, 1000);
        } else {
          const errMsg = data.error || data.message || 'Đăng ký không thành công. Vui lòng kiểm tra lại thông tin.';
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
