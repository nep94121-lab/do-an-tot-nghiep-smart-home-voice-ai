"""Adversarial Verification Suite for Milestone 2.

Author: empirical_challenger (Challenger 1)
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
from bs4 import BeautifulSoup
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent

MODIFIED_FILES = [
    ROOT / "simulator" / "static" / "index.html",
    ROOT / "simulator" / "static" / "js" / "app.js",
    ROOT / "simulator" / "static" / "js" / "auth.js",
    ROOT / "mobile_app" / "index.html",
    ROOT / "simulator" / "static" / "js" / "mobile_app.js",
]


class TestMilestone2AdversarialIntegrity:
    """Kiểm thử đối kháng thực nghiệm độc lập Milestone 2."""

    def test_file_encoding_and_zero_crlf(self):
        """Bảo đảm 100% tệp sửa đổi chuẩn UTF-8 không BOM và 0 CRLF (POSIX LF)."""
        for p in MODIFIED_FILES:
            raw = p.read_bytes()
            assert not raw.startswith(b"\xef\xbb\xbf"), f"Tệp {p.name} chứa UTF-8 BOM"
            assert b"\r\n" not in raw, f"Tệp {p.name} chứa ký tự CRLF (Windows format)"

    def test_web_login_gate_dom_lockdown(self):
        """Kiểm tra thuộc tính hidden trên nút đóng modal và form bọc hỗ trợ Enter."""
        html_p = ROOT / "simulator" / "static" / "index.html"
        soup = BeautifulSoup(html_p.read_text(encoding="utf-8"), "html.parser")

        btn_close = soup.find(id="btnCloseLoginGateModal")
        assert btn_close is not None, "Thiếu phần tử #btnCloseLoginGateModal"
        assert btn_close.has_attr("hidden"), "#btnCloseLoginGateModal không có thuộc tính hidden ban đầu"

        for form_id in ["gatePanelLogin", "gatePanelRegister", "gatePanelForgot"]:
            form_el = soup.find(id=form_id)
            assert form_el is not None, f"Thiếu phần tử #{form_id}"
            assert form_el.name == "form", f"#{form_id} phải là thẻ <form> nhưng tìm thấy <{form_el.name}>"

        web_pw_ids = [
            "gateLoginPassword",
            "gateRegPassword",
            "gateRegConfirmPassword",
            "gateForgotNewPassword",
            "gateForgotConfirmPassword",
        ]
        for pw_id in web_pw_ids:
            inp = soup.find(id=pw_id)
            assert inp is not None, f"Thiếu input #{pw_id}"
            parent = inp.parent
            btn_eye = parent.find("button", class_="btn-toggle-pw")
            assert btn_eye is not None, f"Input #{pw_id} thiếu nút toggle 👁️ trong container cha"

    def test_mobile_svg_sprite_placement_and_eye_buttons(self):
        """Kiểm tra <symbol id='i-home'> nằm ngoài #mobileMainContent hidden."""
        html_p = ROOT / "mobile_app" / "index.html"
        soup = BeautifulSoup(html_p.read_text(encoding="utf-8"), "html.parser")

        body = soup.find("body")
        assert body is not None, "mobile_app/index.html thiếu <body>"

        body_svg = body.find("svg")
        assert body_svg is not None, "Thiếu <svg> sprite toàn cục ngay trong body"
        assert body_svg.parent == body, "Thẻ <svg> sprite không nằm trực tiếp dưới body"

        sym_home = body_svg.find("symbol", id="i-home")
        assert sym_home is not None, "<symbol id='i-home'> không tồn tại trong <svg> sprite body"

        main_div = soup.find(id="mobileMainContent")
        assert main_div is not None, "Thiếu #mobileMainContent"
        assert main_div.has_attr("hidden"), "#mobileMainContent thiếu thuộc tính hidden"

        sym_in_main = main_div.find("symbol", id="i-home")
        assert sym_in_main is None, "<symbol id='i-home'> vẫn bị nhốt bên trong #mobileMainContent hidden!"

        gate_div = soup.find(id="mobileLoginGate")
        assert gate_div is not None, "Thiếu #mobileLoginGate"
        assert gate_div.parent == body, "#mobileLoginGate phải nằm trực tiếp dưới body"
        use_home = gate_div.find("use", href="#i-home")
        assert use_home is not None, "#mobileLoginGate thiếu icon <use href='#i-home'/>"

        mobile_pw_ids = [
            "mobileLoginPassword",
            "mobileRegPassword",
            "mobileRegConfirmPassword",
            "mobileChangeNewPassword",
            "mobileChangeConfirmPassword",
        ]
        for pw_id in mobile_pw_ids:
            inp = soup.find(id=pw_id)
            assert inp is not None, f"Thiếu mobile input #{pw_id}"
            parent = inp.parent
            btn_eye = parent.find("button", class_="btn-toggle-pw")
            assert btn_eye is not None, f"Mobile input #{pw_id} thiếu nút toggle 👁️"

    def test_auth_js_unlocked_inputs(self):
        """Kiểm tra auth.js không còn bất kỳ dòng readOnly = true nào cho name & email."""
        js_p = ROOT / "simulator" / "static" / "js" / "auth.js"
        code = js_p.read_text(encoding="utf-8")

        assert "nameInput.readOnly = true" not in code, "Vẫn còn tồn tại nameInput.readOnly = true"
        assert "emailInput.readOnly = true" not in code, "Vẫn còn tồn tại emailInput.readOnly = true"
        assert "nameInput.readOnly = false" in code, "Thiếu nameInput.readOnly = false"
        assert "emailInput.readOnly = false" in code, "Thiếu emailInput.readOnly = false"

    def test_backend_password_mismatch_rejection(self):
        """Thử tấn công trực tiếp backend API với mật khẩu không khớp."""
        from simulator.auth_3layer import get_auth_3layer_manager

        mgr = get_auth_3layer_manager()

        res_reg = mgr.register_or_update_password(
            email="adversarial_test@example.com",
            password="Password_A_123",
            confirm_password="Password_B_456",
            display_name="Attacker",
            target_tier=2,
        )
        assert res_reg["ok"] is False, "Backend không chặn đăng ký khi confirm_password không khớp!"
        assert "không khớp" in res_reg["error"].lower()

        res_reset = mgr.reset_password_with_otp(
            email="nep94121@gmail.com",
            otp_code="999999",
            new_password="NewPass123",
            confirm_password="MismatchedPass456",
        )
        assert res_reset["ok"] is False, "Backend không chặn reset password khi confirm_password không khớp!"
        assert "không khớp" in res_reset["error"].lower()

    def test_execute_node_adversarial_harness(self):
        """Thực thi toàn bộ 52 kịch bản stress-test trong adversarial_harness.js."""
        harness_path = pathlib.Path(__file__).parent / "adversarial_harness.js"
        proc = subprocess.run(
            ["node", str(harness_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert proc.returncode == 0, f"Adversarial harness thất bại:\n{proc.stdout}\n{proc.stderr}"
        assert "TOTAL ADVERSARIAL TESTS: 52" in proc.stdout
        assert "FAILED: 0" in proc.stdout
