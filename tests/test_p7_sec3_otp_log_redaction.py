"""TDD Test Suite for Branch p7-sec3:
Remove plaintext OTP codes from all logs and API responses.

Requirements verified:
1. Stop writing OTP codes into any log/extra/detail field at source:
   auth_3layer.py, invite_and_gmail_mixin.py, test_suite_mixin.py, routes_auth.py,
   and all SQL/JSON/JSONL log writers.
2. Redact existing stored log entries (migration and startup redaction of stored logs)
   so old OTP codes, password hints, and voiceprint embeddings are removed from stored logs.
3. Recursive response sanitizer (`sanitize_overview_and_logs_payload`) that strips
   otp/code/password/voiceprint keys and redacts OTP strings from the overview and logs endpoints.
4. Keep all p7-sec fixes and p6-otp behavior (no OTP leak in responses, cooldown, 429 rate limit).
"""

from __future__ import annotations

import json
import pathlib
import re
import secrets
import sqlite3
import sys
from typing import Any

import pytest
from starlette.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.auth.constants_and_crypto import hash_password
from simulator.auth_3layer import ThreeLayerAuthManager, get_auth_3layer_manager
from simulator.database_sqlite import SQLITE_DB_PATH
from simulator.rule_engine import AUDIT_LOG_FILE, append_audit_log, read_audit_logs
from simulator.server import app

OWNER_HEADERS = {"X-Session-Token": "sess_owner_t1_nep94121"}

FORBIDDEN_LOG_AND_OVERVIEW_KEYS = {
    "otp",
    "otp_code",
    "otp_input",
    "input_otp",
    "otp_code_for_test",
    "otp_code_for_test_table",
    "demo_otp_preview",
    "extracted_otp",
    "active_otp",
    "pending_otp",
    "pending_otps",
    "auth_otp",
    "code",
    "auth_code",
    "verification_code",
    "reset_code",
    "security_code",
    "secret_code",
    "passcode",
    "pin_code",
    "password",
    "passwords",
    "password_hash",
    "password_salt",
    "password_hint",
    "password_plain_hint",
    "issued_password",
    "issued_password_for_test",
    "new_password",
    "confirm_password",
    "custom_password",
    "pin_hash",
    "voiceprint",
    "voiceprints",
    "voiceprint_json",
    "embedding",
    "embeddings",
    "deep_embedding",
    "deep_embedding_64d",
    "embedding_26d_json",
    "embedding_64d_json",
    "embedding_256d",
    "baseline_embedding",
    "baseline_deep_embedding",
    "baseline_embedding_256d",
    "formants_hz",
}


def _collect_forbidden_keys(obj: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            k_low = str(k).strip().lower()
            if k_low in FORBIDDEN_LOG_AND_OVERVIEW_KEYS:
                found.append(f"{path}.{k}")
            found.extend(_collect_forbidden_keys(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            found.extend(_collect_forbidden_keys(item, f"{path}[{idx}]"))
    return found


@pytest.fixture(autouse=True)
def _preserve_data_files():
    """Preserve and restore stored log files and SQLite audit_logs around each test."""
    from simulator.auth import ACCOUNTS_FILE, AUTH_EVENTS_FILE
    from simulator.database_sqlite import get_connection
    from simulator.engine.constants_and_time import AUDIT_LOG_FILE

    orig_events = AUTH_EVENTS_FILE.read_bytes() if AUTH_EVENTS_FILE.exists() else None
    orig_jsonl = AUDIT_LOG_FILE.read_bytes() if AUDIT_LOG_FILE.exists() else None
    orig_accounts = ACCOUNTS_FILE.read_bytes() if ACCOUNTS_FILE.exists() else None
    conn = get_connection()
    max_id_row = conn.execute("SELECT COALESCE(MAX(log_id), 0) AS m FROM audit_logs").fetchone()
    orig_max_log_id = int(max_id_row["m"]) if max_id_row else 0
    conn.close()
    try:
        yield
    finally:
        if orig_events is not None:
            AUTH_EVENTS_FILE.write_bytes(orig_events)
        if orig_jsonl is not None:
            AUDIT_LOG_FILE.write_bytes(orig_jsonl)
        if orig_accounts is not None:
            ACCOUNTS_FILE.write_bytes(orig_accounts)
        conn2 = get_connection()
        try:
            conn2.execute("DELETE FROM audit_logs WHERE log_id > ?", (orig_max_log_id,))
            conn2.commit()
            conn2.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        finally:
            conn2.close()
        mgr = get_auth_3layer_manager()
        if orig_events is not None:
            mgr.verification_logs = json.loads(orig_events.decode("utf-8"))[:100]


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_overview_never_returns_otp_code_in_verification_logs_or_recent_logs(client: TestClient) -> None:
    """Authenticated GET /api/auth3/overview must never return otp_code or plaintext 6-digit OTPs
    in verification_logs[].extra, recent_logs[].extra, detail strings, or test_report."""
    mgr = get_auth_3layer_manager()
    owner_acc = mgr.find_account("tuan_anh")
    assert owner_acc is not None
    orig_hash = owner_acc.get("password_hash", "")
    temp_pw = "TempOwner_" + secrets.token_urlsafe(10)

    try:
        owner_acc["password_hash"] = hash_password(temp_pw)

        # Trigger layer 1 login, password reset OTP, and invite registration to generate fresh logs
        r_l1 = mgr.layer1_login(owner_acc["email"], temp_pw, login_method="password", send_gmail=False)
        assert r_l1.get("ok") is True
        issued_l1_otp = mgr.pending_otps[owner_acc["email"].lower()]["otp_code"]

        mgr.pending_otps.clear()
        r_rst = mgr.request_password_reset_otp(owner_acc["email"], send_gmail=False)
        assert r_rst.get("ok") is True
        issued_rst_otp = mgr.pending_otps[owner_acc["email"].lower()]["otp_code"]

        r_inv = mgr.start_invite_oauth_registration(
            invite_code="INV-T1-TO-TIER2",
            google_email="sec3_invite_check@gmail.com",
            display_name="Sec3 Invite Check",
            send_gmail=False,
        )
        assert r_inv.get("ok") is True
        issued_inv_otp = mgr.pending_invite_registrations["sec3_invite_check@gmail.com"]["otp_code"]
        issued_inv_pw = mgr.pending_invite_registrations["sec3_invite_check@gmail.com"]["issued_password"]

        # Force test suite re-run on overview
        mgr.latest_test_report = {}

        resp = client.get("/api/auth3/overview", headers=OWNER_HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("ok") is True

        # 1. No forbidden keys anywhere in /api/auth3/overview
        leaked_keys = _collect_forbidden_keys(body)
        assert not leaked_keys, f"/api/auth3/overview leaked forbidden keys: {leaked_keys}"

        # 2. Explicitly verify verification_logs[].extra and recent_logs[].extra
        for list_name in ("verification_logs", "recent_logs"):
            logs_list = body.get(list_name, [])
            assert isinstance(logs_list, list)
            for idx, entry in enumerate(logs_list):
                extra = entry.get("extra") or {}
                assert "otp_code" not in extra, f"{list_name}[{idx}].extra leaked otp_code: {extra}"
                assert "otp" not in extra, f"{list_name}[{idx}].extra leaked otp: {extra}"
                detail = str(entry.get("detail") or "")
                for secret_val in (issued_l1_otp, issued_rst_otp, issued_inv_otp, issued_inv_pw):
                    assert secret_val not in detail, f"{list_name}[{idx}].detail leaked secret {secret_val}: {detail}"

        # 3. Dump entire overview response and verify zero issued OTPs or 6-digit OTP patterns in text
        raw_overview = json.dumps(body, ensure_ascii=False)
        for secret_val in (issued_l1_otp, issued_rst_otp, issued_inv_otp, issued_inv_pw):
            assert secret_val not in raw_overview, f"/api/auth3/overview leaked secret {secret_val} in body"
        assert not re.search(r"OTP[:\s=(]+['\"]?\d{6}\b", raw_overview, re.IGNORECASE), (
            f"/api/auth3/overview contains 6-digit OTP pattern in text: {raw_overview}"
        )
    finally:
        owner_acc["password_hash"] = orig_hash
        mgr.pending_invite_registrations.pop("sec3_invite_check@gmail.com", None)


def test_log_writers_at_source_never_write_otp_or_passwords(client: TestClient) -> None:
    """Requirement 1: auth_3layer.py, invite_and_gmail_mixin.py, routes_auth.py,
    and SQL/JSON/JSONL log writers must never write OTP codes or passwords at source."""
    mgr = get_auth_3layer_manager()
    owner_acc = mgr.find_account("tuan_anh")
    assert owner_acc is not None
    orig_hash = owner_acc.get("password_hash", "")
    temp_pw = "TempOwner_" + secrets.token_urlsafe(10)

    try:
        owner_acc["password_hash"] = hash_password(temp_pw)
        mgr.pending_otps.clear()

        # 1. Layer 1 login via HTTP route (triggers _log_event + append_audit_log + SQLite)
        r1 = client.post(
            "/api/auth3/layer1_login",
            json={
                "email": owner_acc["email"],
                "password": temp_pw,
                "login_method": "password",
                "send_gmail": False,
            },
        )
        assert r1.status_code == 200
        otp_l1 = mgr.pending_otps[owner_acc["email"].lower()]["otp_code"]

        # 2. Layer 2 verify wrong OTP then right OTP
        client.post(
            "/api/auth3/layer2_verify_otp",
            json={"email": owner_acc["email"], "otp_code": "123456" if otp_l1 != "123456" else "654321"},
        )
        r2_ok = client.post(
            "/api/auth3/layer2_verify_otp",
            json={"email": owner_acc["email"], "otp_code": otp_l1},
        )
        assert r2_ok.status_code == 200

        # 3. Forgot password send OTP (fresh + cooldown)
        mgr.pending_otps.clear()
        client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": owner_acc["email"], "send_gmail": False},
        )
        otp_forgot = mgr.pending_otps[owner_acc["email"].lower()]["otp_code"]
        # Trigger cooldown log
        client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": owner_acc["email"], "send_gmail": False},
        )

        # 4. Invite OAuth HTTP endpoints return 410 Gone, and direct invite methods never write OTP/password to logs!
        http_inv_start = client.post(
            "/api/auth3/invite_oauth_start",
            json={
                "invite_code": "INV-T1-TO-TIER2",
                "google_email": "sec3_source_test@gmail.com",
                "display_name": "Sec3 Source Test",
                "send_gmail": False,
            },
        )
        assert http_inv_start.status_code == 410
        assert http_inv_start.json().get("gone") is True

        http_inv_verify = client.post(
            "/api/auth3/invite_verify_otp",
            json={
                "email": "sec3_source_test@gmail.com",
                "otp_code": "000000",
            },
        )
        assert http_inv_verify.status_code == 410
        assert http_inv_verify.json().get("gone") is True

        inv_start_res = mgr.start_invite_oauth_registration(
            invite_code="INV-T1-TO-TIER2",
            google_email="sec3_source_test@gmail.com",
            display_name="Sec3 Source Test",
            send_gmail=False,
        )
        assert inv_start_res.get("ok") is True
        pend_inv = mgr.pending_invite_registrations["sec3_source_test@gmail.com"]
        otp_inv = pend_inv["otp_code"]
        pw_inv = pend_inv["issued_password"]

        wrong_inv = mgr.verify_invite_otp_and_create_account(
            email="sec3_source_test@gmail.com",
            otp_input="000000" if otp_inv != "000000" else "999999",
        )
        wrong_inv_text = json.dumps(wrong_inv, ensure_ascii=False)
        assert otp_inv not in wrong_inv_text, f"Wrong invite OTP response leaked actual OTP {otp_inv}: {wrong_inv_text}"

        # Check in-memory verification_logs
        for lg in mgr.verification_logs[:15]:
            lg_str = json.dumps(lg, ensure_ascii=False)
            assert "otp_code" not in (lg.get("extra") or {}), f"verification_logs extra has otp_code: {lg}"
            for secret_val in (otp_l1, otp_forgot, otp_inv, pw_inv):
                assert secret_val not in lg_str, f"verification_logs leaked secret {secret_val}: {lg_str}"

        # Check persisted JSONL audit logs
        recent_audit = read_audit_logs(limit=25)
        for al in recent_audit:
            al_str = json.dumps(al, ensure_ascii=False)
            for secret_val in (otp_l1, otp_forgot, otp_inv, pw_inv):
                assert secret_val not in al_str, f"system_audit_logs.jsonl leaked secret {secret_val}: {al_str}"
            for banned_k in ("otp_code", "otp_code_for_test", "otp_code_for_test_table", "demo_otp_preview", "issued_password_for_test"):
                assert banned_k not in (al.get("details") or {}), f"system_audit_logs.jsonl details has {banned_k}: {al}"
    finally:
        owner_acc["password_hash"] = orig_hash
        mgr.pending_invite_registrations.pop("sec3_source_test@gmail.com", None)


def test_stored_log_files_on_disk_and_startup_redaction_have_zero_plaintext_otps() -> None:
    """Requirement 2: Existing stored log files (auth_3layer_events.json, system_audit_logs.jsonl,
    smarthome.db audit_logs) must have all old OTP codes removed, and startup redaction must
    clean any dirty stored log entries."""
    from simulator.auth import AUTH_EVENTS_FILE

    # 1. Check auth_3layer_events.json on disk
    if AUTH_EVENTS_FILE.exists():
        events_raw = AUTH_EVENTS_FILE.read_text(encoding="utf-8")
        events_list = json.loads(events_raw)
        assert not _collect_forbidden_keys(events_list), (
            f"auth_3layer_events.json contains forbidden keys: {_collect_forbidden_keys(events_list)}"
        )
        for old_otp in ("324093", "769837", "410464", "605597", "880970", "734774", "243757", "367495", "950374"):
            assert old_otp not in events_raw, f"Old plaintext OTP {old_otp} still present in auth_3layer_events.json"

    # 2. Check system_audit_logs.jsonl on disk
    if AUDIT_LOG_FILE.exists():
        jsonl_raw = AUDIT_LOG_FILE.read_text(encoding="utf-8")
        for old_otp in ("135544", "162364", "334085", "353992", "457219", "551167", "623859", "258332"):
            assert old_otp not in jsonl_raw, f"Old plaintext OTP {old_otp} still present in system_audit_logs.jsonl"
        for banned_key in ('"otp_code_for_test_table"', '"demo_otp_preview"', '"otp_code_for_test"', '"issued_password_for_test"'):
            assert banned_key not in jsonl_raw, f"Banned key {banned_key} still present in system_audit_logs.jsonl"

    # 3. Check SQLite smarthome.db audit_logs table
    if SQLITE_DB_PATH.exists():
        conn = sqlite3.connect(str(SQLITE_DB_PATH))
        try:
            rows = conn.execute("SELECT log_id, summary, details_json FROM audit_logs").fetchall()
            for log_id, summary, details_json in rows:
                combined = f"{summary} {details_json}"
                for old_otp in ("135544", "162364", "334085", "353992", "457219", "551167", "623859", "258332"):
                    assert old_otp not in combined, f"SQLite audit_logs row {log_id} still contains old OTP {old_otp}"
                for banned_key in ('"otp_code_for_test_table"', '"demo_otp_preview"', '"otp_code_for_test"', '"embedding"', '"deep_embedding"'):
                    assert banned_key not in details_json, f"SQLite audit_logs row {log_id} details_json contains {banned_key}"
        finally:
            conn.close()


def test_recursive_response_sanitizer_strips_otp_code_password_voiceprint_keys(client: TestClient) -> None:
    """Requirement 3: Response sanitizer must recursively strip otp/code/password/voiceprint keys
    from overview and logs endpoints."""
    from simulator.voice_config import sanitize_overview_and_logs_payload

    dirty_payload = {
        "ok": True,
        "invite_code": "INV-T1-TO-TIER2",
        "status_code": 200,
        "verification_logs": [
            {
                "id": 1,
                "detail": "Đăng nhập Lớp 1 hợp lệ (password). Mã OTP: 482910 — Đã giữ nguyên mã OTP đang hiệu lực (482910).",
                "extra": {
                    "otp_code": "482910",
                    "otp": "482910",
                    "code": "482910",
                    "verification_code": "482910",
                    "auth_code": "482910",
                    "reset_code": "482910",
                    "password": "PlainPassword123",
                    "issued_password": "IssuedPassword456",
                    "password_hash": "abcdef123456",
                    "password_plain_hint": "Hint123",
                    "voiceprint": {"f0_mean_hz": 126.0, "embedding": [0.1, 0.2]},
                    "voiceprints": [{"f0": 126.0}],
                    "tier": 1,
                },
            }
        ],
        "nested_sql_row": {
            "summary": "Đã gửi mã OTP đặt lại mật khẩu (739182) tới Gmail.",
            "details_json": json.dumps({
                "otp_code": "739182",
                "otp_code_for_test_table": "739182",
                "demo_otp_preview": "739182",
                "password": "Secret",
                "voiceprint": {"enrolled": True},
                "embedding": [0.1, 0.2, 0.3],
                "safe_field": "kept",
            }),
        },
    }

    cleaned = sanitize_overview_and_logs_payload(dirty_payload)
    assert cleaned["invite_code"] == "INV-T1-TO-TIER2"
    assert cleaned["status_code"] == 200
    assert cleaned["verification_logs"][0]["extra"] == {"tier": 1}
    assert not _collect_forbidden_keys(cleaned)
    dumped = json.dumps(cleaned, ensure_ascii=False)
    assert "482910" not in dumped
    assert "739182" not in dumped
    assert "PlainPassword123" not in dumped
    assert "IssuedPassword456" not in dumped

    # Live injection test into mgr.verification_logs right before GET /api/auth3/overview
    mgr = get_auth_3layer_manager()
    mgr.verification_logs.insert(
        0,
        {
            "id": 999999,
            "time_vn": "20:00:00 05/11/2026",
            "layer": "Test Layer",
            "action": "injected_dirty_log",
            "email": "nep94121@gmail.com",
            "status": "PASS",
            "detail": "Mã OTP: 519283 (519283)",
            "source": "Test",
            "extra": {
                "otp_code": "519283",
                "otp": "519283",
                "code": "519283",
                "password": "LeakedPassword999",
                "voiceprint": {"f0_mean_hz": 126.0},
                "tier": 1,
            },
        },
    )
    try:
        r_ov = client.get("/api/auth3/overview", headers=OWNER_HEADERS)
        assert r_ov.status_code == 200
        ov_data = r_ov.json()
        assert not _collect_forbidden_keys(ov_data)
        ov_text = json.dumps(ov_data, ensure_ascii=False)
        assert "519283" not in ov_text
        assert "LeakedPassword999" not in ov_text
    finally:
        mgr.verification_logs = [lg for lg in mgr.verification_logs if lg.get("id") != 999999]


def test_logs_api_masks_password_hints_with_asterisks_not_redacted_token(client: TestClient) -> None:
    """Password hints in logs must render as 'Mật khẩu gợi ý: ******' (never '[REDACTED]' or plaintext)
    so test_bug1_logs_api_masks_password_hints and adversarial masking checks pass."""
    append_audit_log(
        category="SECURITY",
        event_type="password_hint_mask_regression",
        summary="Đăng nhập thất bại. Mật khẩu gợi ý: SuperSecretHint2026 (Mật khẩu gợi ý: 123456 - Lớp 1)",
        user_name="admin",
        tier=1,
        details={"raw_event": "Đăng nhập thất bại. Mật khẩu gợi ý: SuperSecretHint2026"},
    )
    res_unauth = client.get("/api/logs/dashboard")
    assert res_unauth.status_code == 401
    res = client.get("/api/logs/dashboard", headers=OWNER_HEADERS)
    assert res.status_code == 200
    logs = res.json().get("audit_logs", [])
    assert logs
    for item in logs:
        text_corpus = (
            f"{item.get('event', '')} {item.get('detail', '')} "
            f"{item.get('summary', '')} {json.dumps(item.get('details', {}), ensure_ascii=False)}"
        )
        assert "SuperSecretHint2026" not in text_corpus
        assert not re.search(r"Mật khẩu gợi ý:\s*[^*\s]+", text_corpus), (
            f"Password hint was not masked with asterisks: {text_corpus}"
        )
