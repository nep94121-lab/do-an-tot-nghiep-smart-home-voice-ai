"""Orthogonal Integrity & Anti-Facade Test Suite for Milestone 2.

Executed by Auditor (Role: Forensic Integrity Auditor)
Tests all DOM contracts, runtime simulation, and backend authentication integration.
"""

import json
import pathlib
import sys
from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def test_web_html_contracts():
    print("[TEST 1] Verifying simulator/static/index.html contracts...")
    html_path = ROOT / "simulator" / "static" / "index.html"
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")

    # 1. Check close button hidden attribute
    close_btn = soup.find(id="btnCloseLoginGateModal")
    assert close_btn is not None, "Missing #btnCloseLoginGateModal"
    assert close_btn.has_attr("hidden"), "#btnCloseLoginGateModal must have hidden attribute by default"

    # 2. Check forms
    for fid in ["gatePanelLogin", "gatePanelRegister", "gatePanelForgot"]:
        form_el = soup.find(id=fid)
        assert form_el is not None, f"Missing form {fid}"
        assert form_el.name == "form", f"{fid} must be a <form> tag, found {form_el.name}"
        sub_btn = form_el.find("button", attrs={"type": "submit"})
        assert sub_btn is not None, f"{fid} missing <button type='submit'>"

    # 3. Check password inputs and eye buttons
    web_pws = [
        "gateLoginPassword",
        "gateRegPassword",
        "gateRegConfirmPassword",
        "gateForgotNewPassword",
        "gateForgotConfirmPassword",
    ]
    for pid in web_pws:
        el = soup.find(id=pid)
        assert el is not None, f"Missing password input {pid}"
        btn = el.parent.find("button", class_="btn-toggle-pw")
        assert btn is not None, f"Missing toggle button for {pid}"
        assert f"togglePasswordVisibility('{pid}'" in btn.get("onclick", "")

    print(" -> PASSED: Web HTML contracts valid.")

def test_mobile_html_contracts():
    print("[TEST 2] Verifying mobile_app/index.html contracts...")
    html_path = ROOT / "mobile_app" / "index.html"
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")

    # 1. Check global body SVG sprite
    body = soup.find("body")
    assert body is not None, "Missing <body>"
    body_svg = body.find("svg", recursive=False)
    assert body_svg is not None, "Missing <svg> sprite directly under <body>"
    sym_home = body_svg.find("symbol", id="i-home")
    assert sym_home is not None, "Missing #i-home in global SVG sprite"

    # 2. Check main content hidden and lacks #i-home
    main_c = soup.find(id="mobileMainContent")
    assert main_c is not None, "Missing #mobileMainContent"
    assert main_c.has_attr("hidden"), "#mobileMainContent must be hidden by default"
    assert main_c.find("symbol", id="i-home") is None, "#i-home MUST NOT be inside #mobileMainContent"

    # 3. Check login gate icon
    login_gate = soup.find(id="mobileLoginGate")
    assert login_gate is not None, "Missing #mobileLoginGate"
    gate_use = login_gate.find("use")
    assert gate_use is not None and gate_use.get("href") == "#i-home"

    # 4. Check mobile forms
    for fid in ["mobileLoginForm", "mobileRegisterForm", "mobileChangePasswordForm"]:
        form_el = soup.find(id=fid)
        assert form_el is not None, f"Missing mobile form {fid}"
        assert form_el.name == "form", f"{fid} must be a <form> tag"
        sub_btn = form_el.find("button", attrs={"type": "submit"})
        assert sub_btn is not None, f"{fid} missing submit button"

    # 5. Check mobile password inputs
    mob_pws = [
        "mobileLoginPassword",
        "mobileRegPassword",
        "mobileRegConfirmPassword",
        "mobileChangeNewPassword",
        "mobileChangeConfirmPassword",
    ]
    for pid in mob_pws:
        el = soup.find(id=pid)
        assert el is not None, f"Missing mobile password input {pid}"
        btn = el.parent.find("button", class_="btn-toggle-pw")
        assert btn is not None, f"Missing toggle button for {pid}"
        assert f"togglePasswordVisibility('{pid}'" in btn.get("onclick", "")

    print(" -> PASSED: Mobile HTML contracts valid.")

def test_auth_js_read_only_removed():
    print("[TEST 3] Verifying simulator/static/js/auth.js readOnly removal...")
    auth_js = (ROOT / "simulator" / "static" / "js" / "auth.js").read_text(encoding="utf-8")
    assert "nameInput.readOnly = true" not in auth_js, "Found forbidden 'nameInput.readOnly = true' in auth.js"
    assert "emailInput.readOnly = true" not in auth_js, "Found forbidden 'emailInput.readOnly = true' in auth.js"
    assert "nameInput.readOnly = false" in auth_js, "Expected 'nameInput.readOnly = false' in auth.js"
    assert "emailInput.readOnly = false" in auth_js, "Expected 'emailInput.readOnly = false' in auth.js"
    print(" -> PASSED: auth.js readOnly unlocked.")

def test_app_js_login_gate_hardening():
    print("[TEST 4] Verifying simulator/static/js/app.js Login Gate hardening...")
    app_js = (ROOT / "simulator" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "function hasValidLoginSession()" in app_js, "Missing hasValidLoginSession() declaration"
    assert "window.togglePasswordVisibility = togglePasswordVisibility;" in app_js, "Missing togglePasswordVisibility export"
    assert "btnCloseLoginGateModal.hidden = !hasValidLoginSession();" in app_js, "Missing dynamic hidden toggle"
    assert "if (!hasValidLoginSession()) {" in app_js, "Missing login gate close protection"
    print(" -> PASSED: app.js Login Gate logic verified.")

def test_mobile_app_js_exports():
    print("[TEST 5] Verifying simulator/static/js/mobile_app.js exports...")
    mobile_js = (ROOT / "simulator" / "static" / "js" / "mobile_app.js").read_text(encoding="utf-8")
    expected_exports = [
        "window.submitMobileLogin = submitMobileLogin;",
        "window.switchMobileLoginTab = switchMobileLoginTab;",
        "window.onMobileRegTierChange = onMobileRegTierChange;",
        "window.submitMobileRegister = submitMobileRegister;",
        "window.submitMobileChangePassword = submitMobileChangePassword;",
        "window.togglePasswordVisibility = togglePasswordVisibility;",
    ]
    for exp in expected_exports:
        assert exp in mobile_js, f"Missing export: {exp}"
    print(" -> PASSED: mobile_app.js exports verified.")

def test_live_backend_auth():
    print("[TEST 6] Verifying Live Backend Auth & Password endpoints...")
    from starlette.testclient import TestClient
    from simulator.server import app

    client = TestClient(app)

    # 1. Test Layer 1 login with correct master owner account
    res1 = client.post("/api/auth3/layer1_login", json={
        "email": "nep94121@gmail.com",
        "password": "wrong_password_test_probe"
    })
    data1 = res1.json()
    assert res1.status_code == 200
    assert data1.get("ok") is False, "Login with wrong password must return ok: False"
    print("   -> Wrong password rejected properly.")

    # 2. Test Layer 1 login with default password
    res2 = client.post("/api/auth3/layer1_login", json={
        "email": "nep94121@gmail.com",
        "password": "123456"
    })
    data2 = res2.json()
    assert res2.status_code == 200
    assert data2.get("ok") is True, f"Login with default password failed: {data2}"
    print("   -> Default password login passed.")

    # 3. Test register_or_set_password with mismatching passwords
    res3 = client.post("/api/auth3/register_or_set_password", json={
        "email": "test_mismatch@gmail.com",
        "password": "password_alpha",
        "confirm_password": "password_beta"
    })
    data3 = res3.json()
    assert res3.status_code == 400 or data3.get("ok") is False
    assert "khớp" in data3.get("error", "").lower() or "mismatch" in data3.get("error", "").lower() or data3.get("ok") is False
    print("   -> Password mismatch rejected properly.")

    # 4. Test register_or_set_password with matching passwords
    import uuid
    nonce = uuid.uuid4().hex[:8]
    test_email = f"auditor_test_{nonce}@gmail.com"
    res4 = client.post("/api/auth3/register_or_set_password", json={
        "email": test_email,
        "display_name": f"Auditor Nonce {nonce}",
        "target_tier": 2,
        "password": f"SecurePass_{nonce}",
        "confirm_password": f"SecurePass_{nonce}"
    })
    data4 = res4.json()
    assert data4.get("ok") is True, f"Registration failed with valid payload: {data4}"
    print("   -> Valid registration with random nonce passed.")

    # 5. Immediately test login with the new registered account
    res5 = client.post("/api/auth3/layer1_login", json={
        "email": test_email,
        "password": f"SecurePass_{nonce}"
    })
    data5 = res5.json()
    assert data5.get("ok") is True, f"Login with newly registered account failed: {data5}"
    print("   -> Newly registered account login passed.")

    print(" -> PASSED: Live Backend endpoints verified with nonces.")

if __name__ == "__main__":
    test_web_html_contracts()
    test_mobile_html_contracts()
    test_auth_js_read_only_removed()
    test_app_js_login_gate_hardening()
    test_mobile_app_js_exports()
    test_live_backend_auth()
    print("\n==========================================")
    print("ALL ORTHOGONAL INTEGRITY TESTS PASSED 100%!")
    print("==========================================")
