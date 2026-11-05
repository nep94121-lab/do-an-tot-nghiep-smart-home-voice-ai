"""Adversarial Challenge Test Suite for Milestone 1: Bugs 1 & 15.
Executed by teamwork_challenger_m1_2.

Focus Areas:
1. Bug 1: Complete and exhaustive scan of all HTML files for static credential values/hints.
2. Bug 1: Adversarial log injection to verify that /api/logs/dashboard and mask_sensitive_log_data
   thoroughly redact password hints and plaintext passwords under various formats.
3. Bug 15: #homeSessionDurationBadge DOM existence, rendering for tier 1 ("Không giới hạn"),
   tier 2 ("Còn 30 ngày"), tier 3, transitions between tiers, and state reset on logout.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.server import app
from simulator.api.routes_logs import mask_sensitive_log_data
from simulator.rule_engine import append_audit_log, clear_audit_logs


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


# =============================================================================
# ADVERSARIAL STRESS TEST: BUG 1 (Zero Credential / Password Hint Leakage)
# =============================================================================

class TestAdversarialBug1CredentialScan:
    """Toàn diện quét mọi file HTML trong dự án."""

    def test_all_html_files_zero_hardcoded_passwords_or_credentials(self):
        html_files = [
            ROOT / "simulator" / "static" / "index.html",
            ROOT / "simulator" / "static" / "auth.html",
            ROOT / "simulator" / "static" / "logs.html",
            ROOT / "simulator" / "static" / "wokwi.html",
            ROOT / "simulator" / "static" / "guest_enroll.html",
            ROOT / "simulator" / "static" / "403.html",
            ROOT / "simulator" / "static" / "404.html",
            ROOT / "simulator" / "static" / "500.html",
            ROOT / "simulator" / "static" / "offline.html",
            ROOT / "simulator" / "static" / "qr_expired.html",
            ROOT / "mobile_app" / "index.html",
        ]

        suspicious_inputs = []
        forbidden_regexes = [
            re.compile(r"mật\s*khẩu\s*mặc\s*định\s*:\s*[^*\s<]+", re.IGNORECASE),
            re.compile(r"mật\s*khẩu\s*gợi\s*ý\s*:\s*[^*\s<)]+", re.IGNORECASE),
            re.compile(r"\(mk\s*:\s*[^*\s<)]+\)", re.IGNORECASE),
            re.compile(r"mặc\s*định\s*:\s*123456", re.IGNORECASE),
        ]

        for html_path in html_files:
            content = html_path.read_text(encoding="utf-8", errors="ignore")
            soup = BeautifulSoup(content, "html.parser")

            # 1. Quét toàn bộ thẻ input
            for inp in soup.find_all("input"):
                val = inp.get("value", "")
                itype = inp.get("type", "text").lower()
                iid = inp.get("id", "")

                # Thẻ type password tuyệt đối không được có value bất kỳ (dù rỗng hay có)
                if itype == "password" and val:
                    suspicious_inputs.append((html_path.name, iid, f"password input has value '{val}'"))

                # Thẻ email không được có giá trị mặc định của chủ nhà hoặc mật khẩu
                if itype == "email" and val:
                    if any(email_seed in val.lower() for email_seed in ["nep94121", "senat6031", "kbanh376"]):
                        suspicious_inputs.append((html_path.name, iid, f"email input has prefilled seed '{val}'"))

                # Giá trị chứa mật khẩu thô
                if any(secret in val.lower() for secret in ["123456", "giadinh@", "khach@"]):
                    suspicious_inputs.append((html_path.name, iid, f"input value contains secret '{val}'"))

            # 2. Quét văn bản tĩnh
            for rgx in forbidden_regexes:
                match = rgx.search(content)
                assert not match, f"File {html_path.name} chứa văn bản lộ credential: '{match.group(0)}'"

        assert not suspicious_inputs, f"Phát hiện thẻ input bị lộ credential: {suspicious_inputs}"

    def test_adversarial_logs_endpoint_masking_under_pressure(self, client: TestClient):
        """Tiêm các bản ghi log giả định có chứa các dạng password hints phức tạp,
        sau đó gọi GET /api/logs/dashboard để chứng minh rằng backend và API
        hoàn toàn che giấu thông tin nhạy cảm."""
        clear_audit_logs()

        # Tiêm các biến thể nhạy cảm
        test_payloads = [
            ("AUTH_3LAYER", "Sai mật khẩu! (Mật khẩu gợi ý: 123456 - Lớp 1)"),
            ("SECURITY", "Đăng nhập thất bại. Mật khẩu gợi ý: SuperPass2026"),
            ("SYSTEM", 'Chi tiết lỗi: {"password": "PlainSecretPassword123", "password_plain_hint": "PlainHint456"}'),
            ("AUTH_3_LAYER", "User update: password_plain_hint='TopSecretHint'"),
            ("SYSTEM_EVENT", 'Thất bại xác thực: password="ActualPassword"'),
        ]

        for cat, text in test_payloads:
            append_audit_log(
                category=cat,
                event_type="adversarial_test",
                summary=text,
                user_name="Adversarial Tester",
                tier=1,
                details={"raw_event": text}
            )

        res = client.get(
            "/api/logs/dashboard",
            headers={"X-Session-Token": "sess_owner_t1_nep94121"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data.get("ok") is True

        audit_logs = data.get("audit_logs", [])
        assert len(audit_logs) >= len(test_payloads)

        for log in audit_logs:
            dumped = json.dumps(log, ensure_ascii=False)
            # Khẳng định không xuất hiện mật khẩu trần trong log summary/detail/raw_event
            assert "123456" not in dumped, f"Lộ 123456: {dumped}"
            assert "SuperPass2026" not in dumped, f"Lộ SuperPass2026: {dumped}"
            assert "PlainSecretPassword123" not in dumped, f"Lộ PlainSecretPassword123: {dumped}"
            assert "PlainHint456" not in dumped, f"Lộ PlainHint456: {dumped}"
            assert "TopSecretHint" not in dumped, f"Lộ TopSecretHint: {dumped}"
            assert "ActualPassword" not in dumped, f"Lộ ActualPassword: {dumped}"

    def test_adversarial_logs_dict_key_masking_edge_case(self, client: TestClient):
        """Kiểm tra phản ứng của mask_sensitive_log_data đối với cấu trúc dictionary trực tiếp."""
        sample_dict = {
            "normal_key": "Mật khẩu gợi ý: 123456 - Lớp 1",
            "password_plain_hint": "SecretHintInDictValue",
            "safe_nested": {"password": "SecretInNestedDict"}
        }
        masked = mask_sensitive_log_data(sample_dict)
        # Giá trị trong chuỗi thông thường được che:
        assert "123456" not in masked["normal_key"]
        assert "******" in masked["normal_key"]


# =============================================================================
# ADVERSARIAL STRESS TEST: BUG 15 (#homeSessionDurationBadge)
# =============================================================================

class TestAdversarialBug15SessionBadge:
    """Kiểm thử chuyên sâu vòng đời và logic hiển thị của #homeSessionDurationBadge."""

    def test_dom_existence_and_initial_hidden_state_in_index_html(self):
        index_html = ROOT / "simulator" / "static" / "index.html"
        assert index_html.exists()
        soup = BeautifulSoup(index_html.read_text(encoding="utf-8"), "html.parser")

        badge = soup.find(id="homeSessionDurationBadge")
        assert badge is not None, "Thẻ #homeSessionDurationBadge không tồn tại trong index.html!"
        # Khi chưa đăng nhập (file tĩnh), thẻ phải có style hidden / display:none
        assert badge.has_attr("hidden") or "display:none" in badge.get("style", "").replace(" ", ""), \
            f"Badge không được ẩn mặc định: {badge}"

    def test_node_execution_tier1_tier2_tier3_and_logout_transitions(self):
        """Chạy mô phỏng vòng đời JS thực tế trên app.js bằng Node.js."""
        node_script = """
const fs = require('fs');
const jsCode = fs.readFileSync(process.argv[1], 'utf8');

const elements = {};
function getEl(id) {
  if (!elements[id]) {
    elements[id] = {
      id,
      value: '',
      textContent: '',
      hidden: true,
      style: { display: 'none' },
      setAttribute(k, v) { this[k] = v; },
      removeAttribute(k) { delete this[k]; },
      classList: {
        _classes: new Set(),
        add(c) { this._classes.add(c); },
        remove(c) { this._classes.delete(c); },
        contains(c) { return this._classes.has(c); }
      },
      listeners: {},
      addEventListener(evt, fn) {
        if (!this.listeners[evt]) this.listeners[evt] = [];
        this.listeners[evt].push(fn);
      },
      click() {
        if (this.listeners['click']) {
          this.listeners['click'].forEach(fn => fn({ preventDefault: () => {} }));
        }
      }
    };
  }
  return elements[id];
}

['homeCurrentAccountBadge', 'homeSessionDurationBadge', 'btnLogoutHome',
 'gateLoginEmail', 'gateLoginPassword', 'gateStatusBox'].forEach(getEl);

global.document = {
  getElementById: getEl,
  querySelector: () => null,
  querySelectorAll: () => [],
  cookie: '',
  addEventListener: () => {}
};
global.window = {
  localStorage: {
    _data: {},
    getItem(k) { return this._data[k] || null; },
    setItem(k, v) { this._data[k] = v; },
    removeItem(k) { delete this._data[k]; }
  },
  sessionStorage: {
    _data: {},
    getItem(k) { return this._data[k] || null; },
    setItem(k, v) { this._data[k] = v; },
    removeItem(k) { delete this._data[k]; },
    clear() { this._data = {}; }
  },
  addEventListener: () => {}
};
global.location = { protocol: 'http:', host: 'localhost:8000', search: '' };
global.WebSocket = class { addEventListener() {} send() {} close() {} };
global.setInterval = () => {};
global.clearInterval = () => {};
global.setTimeout = () => {};
global.clearTimeout = () => {};

eval(jsCode);

const bannerFn = global.window.applyLoggedInUserBanner || applyLoggedInUserBanner;
const results = {};

// Test 1: Tier 1 (Chủ nhà)
bannerFn({ tier: 1, email: 'nep94121@gmail.com', display_name: 'Chủ nhà' });
results.tier1 = {
  text: getEl('homeSessionDurationBadge').textContent,
  hidden: getEl('homeSessionDurationBadge').hidden,
  display: getEl('homeSessionDurationBadge').style.display,
  logoutBtnVisible: getEl('btnLogoutHome').hidden === false && getEl('btnLogoutHome').style.display !== 'none'
};

// Test 2: Chuyển sang Tier 2 (Gia đình) không reload
bannerFn({ tier: 2, email: 'senat6031@gmail.com', display_name: 'Gia đình' });
results.tier2 = {
  text: getEl('homeSessionDurationBadge').textContent,
  hidden: getEl('homeSessionDurationBadge').hidden,
  display: getEl('homeSessionDurationBadge').style.display
};

// Test 3: Chuyển sang Tier 3 (Khách) có validity tùy chỉnh
bannerFn({ tier: 3, email: 'kbanh376@gmail.com', display_name: 'Khách', validity: 'Còn 12 giờ' });
results.tier3 = {
  text: getEl('homeSessionDurationBadge').textContent,
  hidden: getEl('homeSessionDurationBadge').hidden,
  display: getEl('homeSessionDurationBadge').style.display
};

// Test 4: Đăng xuất
getEl('btnLogoutHome').click();
results.afterLogout = {
  text: getEl('homeSessionDurationBadge').textContent,
  hidden: getEl('homeSessionDurationBadge').hidden,
  display: getEl('homeSessionDurationBadge').style.display,
  logoutBtnHidden: getEl('btnLogoutHome').hidden === true || getEl('btnLogoutHome').style.display === 'none',
  accountBadgeText: getEl('homeCurrentAccountBadge').textContent
};

process.stdout.write(JSON.stringify(results));
"""
        js_file = ROOT / "simulator" / "static" / "js" / "app.js"
        proc = subprocess.run(
            ["node", "-e", node_script, str(js_file)],
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
        assert proc.returncode == 0, f"Lỗi chạy Node.js: {proc.stderr}"
        res = json.loads(proc.stdout)

        # 1. Tier 1 assertions
        assert "Không giới hạn" in res["tier1"]["text"], f"Tier 1 text sai: {res['tier1']}"
        assert res["tier1"]["hidden"] is False, f"Tier 1 bị hidden"
        assert res["tier1"]["display"] != "none", f"Tier 1 display bị none"
        assert res["tier1"]["logoutBtnVisible"] is True, "Nút đăng xuất không hiện ở Tier 1"

        # 2. Tier 2 assertions
        assert "Còn 30 ngày" in res["tier2"]["text"], f"Tier 2 text sai: {res['tier2']}"
        assert res["tier2"]["hidden"] is False
        assert res["tier2"]["display"] != "none"

        # 3. Tier 3 assertions
        assert "Còn 12 giờ" in res["tier3"]["text"], f"Tier 3 text sai: {res['tier3']}"
        assert res["tier3"]["hidden"] is False
        assert res["tier3"]["display"] != "none"

        # 4. Logout assertions
        assert res["afterLogout"]["hidden"] is True or res["afterLogout"]["display"] == "none", \
            f"Badge không bị ẩn sau khi click đăng xuất: {res['afterLogout']}"
        assert res["afterLogout"]["logoutBtnHidden"] is True, "Nút đăng xuất không bị ẩn sau khi click đăng xuất"
        assert "Chưa đăng nhập" in res["afterLogout"]["accountBadgeText"], "Account badge không reset về Chưa đăng nhập"
