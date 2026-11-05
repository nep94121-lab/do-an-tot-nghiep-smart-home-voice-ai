"""TDD Security Gate & Email/Credential Masking Suite for Branch p8-logs-gate.

Verifies all requirements for p8-logs-gate:
1. Unauthenticated requests to all log endpoints -> HTTP 401.
2. Authenticated non-admin sessions (Tier 2 MEMBER, Tier 3 CHILD_GUEST) -> HTTP 403.
3. Admin view (Tier 1 ADMIN) returns HTTP 200, masks all email addresses (e.g. n***@gmail.com),
   and never shows OTP codes, passwords, or password hints anywhere in the payload.
4. Web dashboard / log pages (/logs + logs.js + auth_pages.js) work seamlessly for a logged-in admin.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
from typing import Any

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.auth.session_store import get_session_store
from simulator.rule_engine import append_audit_log
from simulator.server import app

ADMIN_SESSION_ID = "sess_owner_t1_nep94121"
MEMBER_SESSION_ID = "sess_family_t2_member_a"
GUEST_SESSION_ID = "sess_guest_t3_visitor_c"

ALL_GET_LOG_ENDPOINTS: tuple[str, ...] = (
    "/api/logs/dashboard",
    "/api/server_logs_and_db",
    "/api/sqlite/overview",
    "/api/devops/status",
)

ALL_POST_LOG_ENDPOINTS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("/api/logs/sql_query", {"sql": "SELECT log_id, user_name, summary FROM audit_logs LIMIT 5;"}),
    ("/api/sqlite/query", {"sql": "SELECT log_id, user_name, summary FROM audit_logs LIMIT 5;"}),
    (
        "/api/logs/knowledge/add",
        {"topic": "p8_kb_test", "content": "Kiểm thử cổng bảo mật nhật ký", "keywords": "p8,security", "min_tier": 3},
    ),
    (
        "/api/kb_upsert",
        {"topic": "p8_kb_alias", "content": "Kiểm thử alias kb_upsert", "keywords": "p8,alias", "min_tier": 3},
    ),
    (
        "/api/logs/append",
        {"category": "SECURITY", "event": "P8 Test Log", "actor": "Admin", "detail": "OK", "level": "INFO"},
    ),
    ("/api/logs/clear", {}),
    ("/api/clear_audit_logs", {}),
)

RAW_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
MASKED_EMAIL_RE = re.compile(r"^[A-Za-z0-9]\*\*\*@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


class TestRequirement1UnauthenticatedLogEndpointsReturn401:
    """Requirement 1: Unauthenticated requests to all log endpoints -> 401."""

    @pytest.mark.parametrize("endpoint", ALL_GET_LOG_ENDPOINTS)
    def test_unauthenticated_get_log_endpoints_return_401(
        self, client: TestClient, endpoint: str
    ) -> None:
        resp = client.get(endpoint)
        assert resp.status_code == 401, (
            f"Unauthenticated GET {endpoint} must return 401, got {resp.status_code}: {resp.text[:200]}"
        )
        data = resp.json()
        assert data.get("ok") is False
        assert data.get("authenticated") is False

    @pytest.mark.parametrize("endpoint,payload", ALL_POST_LOG_ENDPOINTS)
    def test_unauthenticated_post_log_endpoints_return_401(
        self, client: TestClient, endpoint: str, payload: dict[str, Any]
    ) -> None:
        resp = client.post(endpoint, json=payload)
        assert resp.status_code == 401, (
            f"Unauthenticated POST {endpoint} must return 401, got {resp.status_code}: {resp.text[:200]}"
        )
        data = resp.json()
        assert data.get("ok") is False
        assert data.get("authenticated") is False

    @pytest.mark.parametrize("endpoint", ALL_GET_LOG_ENDPOINTS)
    def test_invalid_or_expired_token_on_get_log_endpoints_returns_401(
        self, client: TestClient, endpoint: str
    ) -> None:
        resp = client.get(
            endpoint,
            headers={"X-Session-Token": "sess_forged_invalid_token.000000000000"},
        )
        assert resp.status_code == 401
        assert resp.json().get("ok") is False

    @pytest.mark.parametrize("endpoint,payload", ALL_POST_LOG_ENDPOINTS)
    def test_payload_identity_spoofing_without_valid_session_token_returns_401(
        self, client: TestClient, endpoint: str, payload: dict[str, Any]
    ) -> None:
        """Client must not bypass 401 on POST log endpoints by passing role=ADMIN or user_id=tuan_anh in JSON body."""
        spoofed_body = {
            **payload,
            "role": "ADMIN",
            "tier": 1,
            "user_id": "tuan_anh",
            "email": "nep94121@gmail.com",
        }
        resp = client.post(endpoint, json=spoofed_body)
        assert resp.status_code == 401, (
            f"Payload identity spoofing on POST {endpoint} must be rejected with 401, got {resp.status_code}"
        )


class TestRequirement2NonAdminSessionsReturn403:
    """Requirement 2: Authenticated non-admin sessions -> 403."""

    @pytest.mark.parametrize("non_admin_token", [MEMBER_SESSION_ID, GUEST_SESSION_ID])
    @pytest.mark.parametrize("endpoint", ALL_GET_LOG_ENDPOINTS)
    def test_non_admin_get_log_endpoints_return_403(
        self, client: TestClient, non_admin_token: str, endpoint: str
    ) -> None:
        resp = client.get(endpoint, headers={"X-Session-Token": non_admin_token})
        assert resp.status_code == 403, (
            f"Non-admin GET {endpoint} with {non_admin_token} must return 403, got {resp.status_code}"
        )
        data = resp.json()
        assert data.get("ok") is False
        assert data.get("authenticated") is True
        assert data.get("rbac_blocked") is True

    @pytest.mark.parametrize("non_admin_token", [MEMBER_SESSION_ID, GUEST_SESSION_ID])
    @pytest.mark.parametrize("endpoint,payload", ALL_POST_LOG_ENDPOINTS)
    def test_non_admin_post_log_endpoints_return_403(
        self,
        client: TestClient,
        non_admin_token: str,
        endpoint: str,
        payload: dict[str, Any],
    ) -> None:
        resp = client.post(
            endpoint,
            json=payload,
            headers={"X-Session-Token": non_admin_token},
        )
        assert resp.status_code == 403, (
            f"Non-admin POST {endpoint} with {non_admin_token} must return 403, got {resp.status_code}"
        )
        data = resp.json()
        assert data.get("ok") is False
        assert data.get("authenticated") is True
        assert data.get("rbac_blocked") is True

    def test_non_admin_cookie_and_bearer_sessions_return_403(self, client: TestClient) -> None:
        store = get_session_store()
        dyn_t2 = store.create_session(
            user_id="thanh_vien_a",
            email="senat6031@gmail.com",
            display_name="Thành viên A",
            tier=2,
            role="MEMBER",
        )
        dyn_t3 = store.create_session(
            user_id="khach_c",
            email="kbanh376@gmail.com",
            display_name="Khách C",
            tier=3,
            role="CHILD_GUEST",
        )
        r_bearer = client.get(
            "/api/logs/dashboard",
            headers={"Authorization": f"Bearer {dyn_t2.session_id}"},
        )
        assert r_bearer.status_code == 403

        client.cookies.set("sh_session_token", dyn_t3.session_id)
        try:
            r_cookie = client.get("/api/server_logs_and_db")
            assert r_cookie.status_code == 403
        finally:
            client.cookies.clear()


class TestRequirement3AdminEmailAndSecretMasking:
    """Requirement 3: Admin view masks emails (e.g. n***@gmail.com) and never shows OTP codes, passwords or password hints."""

    def test_mask_email_helper_formats_emails_correctly(self) -> None:
        from simulator.api.routes_logs import mask_sensitive_log_data

        sample = {
            "owner_email": "nep94121@gmail.com",
            "member_email": "senat6031@gmail.com",
            "guest_email": "kbanh376@gmail.com",
            "summary": "Gửi OTP tới khach_moi.hust@gmail.com bởi nep94121@gmail.com (Cấp 1)",
            "otp_text": "Đăng nhập Lớp 1 hợp lệ. Mã OTP: 482910 — Bảng Test (482910)",
            "hint_text": "Sai mật khẩu! (Mật khẩu gợi ý: PlainHint999) password_hint=UnquotedHint777 otp_code: 918273",
            "details_json": json.dumps(
                {
                    "email": "thanhviena.hust@gmail.com",
                    "otp_code": "839201",
                    "password_plain_hint": "HintSecret123",
                },
                ensure_ascii=False,
            ),
        }
        masked = mask_sensitive_log_data(sample)
        assert masked["owner_email"] == "n***@gmail.com"
        assert masked["member_email"] == "s***@gmail.com"
        assert masked["guest_email"] == "k***@gmail.com"
        assert "n***@gmail.com" in masked["summary"]
        assert "k***@gmail.com" in masked["summary"]
        assert "nep94121@gmail.com" not in masked["summary"]
        assert "khach_moi.hust@gmail.com" not in masked["summary"]
        assert "482910" not in masked["otp_text"]
        assert "PlainHint999" not in masked["hint_text"]
        assert "UnquotedHint777" not in masked["hint_text"]
        assert "918273" not in masked["hint_text"]
        assert "thanhviena.hust@gmail.com" not in masked["details_json"]
        assert "t***@gmail.com" in masked["details_json"]
        assert "839201" not in masked["details_json"]
        assert "HintSecret123" not in masked["details_json"]

    def test_admin_dashboard_and_sibling_endpoints_mask_all_emails_and_secrets(
        self, client: TestClient
    ) -> None:
        admin_headers = {"X-Session-Token": ADMIN_SESSION_ID}

        # Seed audit log with raw emails, OTP codes, and password hints
        append_audit_log(
            category="AUTH_3LAYER",
            event_type="p8_mask_verification",
            summary=(
                "Gửi OTP xác thực cho senat6031@gmail.com và nep94121@gmail.com. "
                "Mã OTP: 739182 — Bảng Test (739182). Mật khẩu gợi ý: LegacyHint888"
            ),
            user_name="senat6031@gmail.com",
            tier=2,
            details={
                "email": "senat6031@gmail.com",
                "invited_by": "nep94121@gmail.com (Cấp 1)",
                "otp_code": "739182",
                "otp_code_for_test_table": "739182",
                "demo_otp_preview": "739182",
                "password": "PlainPasswordValue999",
                "password_plain_hint": "LegacyHint888",
                "password_hint": "LegacyHint888",
            },
        )

        for ep in ("/api/logs/dashboard", "/api/server_logs_and_db", "/api/sqlite/overview"):
            resp = client.get(ep, headers=admin_headers)
            assert resp.status_code == 200, f"Admin GET {ep} failed: {resp.status_code}"
            payload = resp.json()
            assert payload.get("ok") is True

            raw_dump = json.dumps(payload, ensure_ascii=False)

            # 1. No unmasked email address anywhere in the entire JSON payload
            unmasked_emails = [
                m.group(0)
                for m in RAW_EMAIL_RE.finditer(raw_dump)
                if not MASKED_EMAIL_RE.match(m.group(0))
            ]
            assert not unmasked_emails, (
                f"Endpoint {ep} leaked unmasked email addresses in admin payload: {set(unmasked_emails)}"
            )

            # 2. Verify masked email format (e.g. n***@gmail.com, s***@gmail.com) is present
            if ep in ("/api/logs/dashboard", "/api/server_logs_and_db"):
                assert "n***@gmail.com" in raw_dump
                assert "s***@gmail.com" in raw_dump

            # 3. Never shows OTP codes, passwords, or password hints
            assert "739182" not in raw_dump, f"OTP code leaked in {ep}"
            assert "LegacyHint888" not in raw_dump, f"Password hint leaked in {ep}"
            assert "PlainPasswordValue999" not in raw_dump, f"Password leaked in {ep}"

        # Also check SQL query output masks emails and secrets in returned rows
        r_sql = client.post(
            "/api/logs/sql_query",
            headers=admin_headers,
            json={"sql": "SELECT user_name, summary, details_json FROM audit_logs ORDER BY log_id DESC LIMIT 10;"},
        )
        assert r_sql.status_code == 200
        sql_dump = json.dumps(r_sql.json(), ensure_ascii=False)
        unmasked_sql_emails = [
            m.group(0)
            for m in RAW_EMAIL_RE.finditer(sql_dump)
            if not MASKED_EMAIL_RE.match(m.group(0))
        ]
        assert not unmasked_sql_emails, f"SQL query rows leaked unmasked emails: {set(unmasked_sql_emails)}"
        assert "739182" not in sql_dump
        assert "LegacyHint888" not in sql_dump


class TestRequirement4WebDashboardWorksForLoggedInAdmin:
    """Requirement 4: Web dashboard / log pages still work for a logged-in admin."""

    def test_logs_page_and_api_work_with_admin_cookie_and_header(self, client: TestClient) -> None:
        page_resp = client.get("/logs")
        assert page_resp.status_code == 200
        assert "auditLogsTbody" in page_resp.text

        client.cookies.set("sh_session_token", ADMIN_SESSION_ID)
        try:
            dash_resp = client.get("/api/logs/dashboard")
            assert dash_resp.status_code == 200
            dash_data = dash_resp.json()
            assert dash_data.get("ok") is True
            assert isinstance(dash_data.get("audit_logs"), list)
        finally:
            client.cookies.clear()

    def test_logs_js_attaches_session_token_header_and_masks_emails_in_node_vm(self) -> None:
        node_script = """
const fs = require('fs');
const vm = require('vm');

const jsCode = fs.readFileSync('simulator/static/js/logs.js', 'utf8');
let capturedHeaders = null;
let capturedCredentials = null;

const sandbox = {
  window: {
    sessionStorage: { getItem: (k) => k === 'session_token' ? 'sess_owner_t1_nep94121' : null },
    localStorage: { getItem: () => null },
    addEventListener: () => {},
    confirm: () => true,
  },
  document: {
    getElementById: () => ({
      value: '',
      textContent: '',
      innerHTML: '',
      style: {},
      addEventListener: () => {},
      appendChild: () => {},
    }),
    querySelectorAll: () => [],
  },
  navigator: { clipboard: { writeText: () => Promise.resolve() } },
  console,
  setTimeout,
  clearTimeout,
};
sandbox.window.fetch = async (url, init) => {
  capturedHeaders = (init && init.headers) || {};
  capturedCredentials = init && init.credentials;
  return {
    ok: true,
    status: 200,
    json: async () => ({ ok: true, audit_logs: [], rows: [] }),
  };
};
sandbox.fetch = (...args) => sandbox.window.fetch(...args);

vm.createContext(sandbox);
vm.runInContext(jsCode, sandbox);

(async () => {
  await sandbox.window.loadDashboard();
  if (!capturedHeaders || capturedHeaders['X-Session-Token'] !== 'sess_owner_t1_nep94121') {
    console.error('Missing X-Session-Token header:', capturedHeaders);
    process.exit(1);
  }
  if (capturedCredentials !== 'same-origin') {
    console.error('Missing credentials same-origin:', capturedCredentials);
    process.exit(1);
  }
  const masked = sandbox.window.maskSensitiveLogText('Liên hệ nep94121@gmail.com hoặc Mã OTP: 123456');
  if (masked.includes('nep94121@gmail.com') || !masked.includes('n***@gmail.com') || masked.includes('123456')) {
    console.error('maskSensitiveLogText did not mask email/OTP:', masked);
    process.exit(1);
  }
  console.log('NODE_VM_LOGS_JS_OK');
})();
"""
        proc = subprocess.run(
            ["node", "-e", node_script],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert proc.returncode == 0, f"Node VM logs.js check failed: {proc.stderr or proc.stdout}"
        assert "NODE_VM_LOGS_JS_OK" in proc.stdout
