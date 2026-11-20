"""Comprehensive verification tests for Permanent Server (S0/S0b/S0c), Real-Time Push (P1-A),
Fast Gemini Live Aoede SQLite Cache (P1-C), Rate Limits (P2-2), and Cookie Hardening (P2-3).
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import pathlib
import socket
import subprocess
import sys
import time
from typing import Any

from fastapi.testclient import TestClient
import httpx
import pytest

from tests.live_auth_helpers import login_live_owner, prepare_live_auth

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_server_ready(base_url: str, timeout_sec: float = 15.0) -> None:
    import urllib.request

    deadline = time.monotonic() + timeout_sec
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/api/health", timeout=2.0) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:
            last_err = exc
        time.sleep(0.15)
    raise RuntimeError(f"Server at {base_url} failed to become ready: {last_err}")


def test_s0_health_and_3nf_sqlite_migration(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify idempotent 3NF SQLite WAL migration, online backup integrity, and /api/health."""
    from scripts.backup_sqlite import run_online_backup
    from scripts.migrate_to_sqlite import migrate_all
    from simulator.db_migrations import NORMALIZED_TABLE_ORDER, open_wal_connection
    from simulator.server import app

    data_dir = tmp_path / "data"
    backup_dir = tmp_path / "backups"
    data_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Copy canonical legacy seed files into isolated tmp data dir
    src_data = ROOT / "simulator" / "data"
    for fname in ("accounts_3layer.json", "user_profiles.json", "device_state.json", "timers_pool.json"):
        if (src_data / fname).exists():
            (data_dir / fname).write_bytes((src_data / fname).read_bytes())

    db_path = data_dir / "smarthome.db"
    monkeypatch.setenv("SMARTHOME_DATA_DIR", str(data_dir))
    monkeypatch.setenv("SMARTHOME_SQLITE_PATH", str(db_path))
    monkeypatch.setenv("SMARTHOME_BACKUP_DIR", str(backup_dir))
    monkeypatch.setenv("SIMULATOR_OFFLINE_SANDBOX", "1")

    res1 = migrate_all(
        target_db=db_path,
        source_dir=data_dir,
        fetch_github=False,
        seed_assets=False,
        upgrade_repo_db=False,
    )
    res2 = migrate_all(
        target_db=db_path,
        source_dir=data_dir,
        fetch_github=False,
        seed_assets=False,
        upgrade_repo_db=False,
    )
    assert res1["ok"] is True
    assert res2["ok"] is True
    assert len(res1["after_target_counts"]) >= len(NORMALIZED_TABLE_ORDER)
    assert res1["foreign_key_errors"] == []
    assert res2["foreign_key_errors"] == []

    conn = open_wal_connection(db_path, readonly=True)
    try:
        jm = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert str(jm).lower() == "wal"
        fk_rows = conn.execute("PRAGMA foreign_key_check;").fetchall()
        assert fk_rows == []
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        for tbl in NORMALIZED_TABLE_ORDER:
            assert tbl in tables, f"Missing normalized table: {tbl}"
    finally:
        conn.close()

    bk = run_online_backup(source_db=db_path, backup_dir=backup_dir, retention_days=14)
    assert bk["ok"] is True
    assert bk["integrity_check"] == "ok"
    assert pathlib.Path(bk["backup_file"]).exists()

    with TestClient(app) as client:
        h = client.get("/api/health")
        assert h.status_code == 200
        body = h.json()
        assert body["ok"] is True
        assert body["sqlite_ok"] is True
        assert body["journal_mode"] == "wal"
        assert body["table_count"] >= len(NORMALIZED_TABLE_ORDER)
        assert body["commit_sha"] and body["commit_sha"] != "unknown"


def test_p2_2_aoede_phrase_rate_limit_and_unknown_phrase_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """P2-2: Unknown/empty phrases return 400; exceeding per-IP unauth limit returns 429 + Retry-After."""
    from simulator.api.routes_devices import AOEDE_UNAUTH_RATE_LIMIT, _reset_aoede_unauth_rate_limits
    from simulator.live.tts_rejection_vi import FIXED_REJECTION_PHRASE_VI
    from simulator.server import app

    _reset_aoede_unauth_rate_limits()
    monkeypatch.setenv("SIMULATOR_OFFLINE_SANDBOX", "1")

    with TestClient(app) as client:
        # Empty & unknown unauthenticated phrases must return 400 cleanly
        r_empty = client.post("/api/voice/aoede_phrase", json={"phrase": ""})
        assert r_empty.status_code == 400
        r_unknown = client.post(
            "/api/voice/aoede_phrase",
            json={"phrase": "Day la mot cau hoan toan la chua duoc dang ky"},
        )
        assert r_unknown.status_code == 400

        # Public allowed phrase works up to limit (AOEDE_UNAUTH_RATE_LIMIT), then 429 on next
        for i in range(AOEDE_UNAUTH_RATE_LIMIT):
            ok_resp = client.post(
                "/api/voice/aoede_phrase",
                json={"phrase": FIXED_REJECTION_PHRASE_VI},
                headers={"X-Forwarded-For": "203.0.113.77"},
            )
            assert ok_resp.status_code == 200, f"Attempt {i + 1} failed: {ok_resp.text}"

        limited = client.post(
            "/api/voice/aoede_phrase",
            json={"phrase": FIXED_REJECTION_PHRASE_VI},
            headers={"X-Forwarded-For": "203.0.113.77"},
        )
        assert limited.status_code == 429
        assert "Retry-After" in limited.headers
        assert int(limited.json().get("retry_after_seconds", 0)) >= 1

        # Separate IP is unaffected
        other_ip = client.post(
            "/api/voice/aoede_phrase",
            json={"phrase": FIXED_REJECTION_PHRASE_VI},
            headers={"X-Forwarded-For": "203.0.113.88"},
        )
        assert other_ip.status_code == 200

        # Authenticated session bypasses unauth limit and can speak arbitrary phrase
        auth_ok = client.post(
            "/api/voice/aoede_phrase",
            json={"phrase": "Xin chào Chủ nhà, hệ thống sẵn sàng."},
            headers={"X-Session-Token": "sess_owner_t1_nep94121", "X-Forwarded-For": "203.0.113.77"},
        )
        assert auth_ok.status_code == 200
        assert auth_ok.json()["voice_name"] == "Aoede"

    _reset_aoede_unauth_rate_limits()


def _assert_session_cookies_hardened(set_cookie_headers: list[str]) -> None:
    by_name: dict[str, str] = {}
    for hdr in set_cookie_headers:
        name = hdr.split("=", 1)[0].strip()
        by_name[name] = hdr
    assert "sh_session_token" in by_name
    assert "session_token" in by_name
    for cname in ("sh_session_token", "session_token"):
        low = by_name[cname].lower()
        assert "httponly" in low, f"Cookie {cname} missing HttpOnly: {by_name[cname]}"
        assert "secure" in low, f"Cookie {cname} missing Secure on HTTPS: {by_name[cname]}"


def test_p2_3_https_cookies_httponly_and_secure_and_ws_ticket(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P2-3 + P1-A ticket: HTTPS auth sets HttpOnly+Secure on both session cookies & ws_ticket authenticates SSE."""
    from scripts.migrate_to_sqlite import migrate_all
    from simulator import auth_3layer, durable_store
    from simulator.auth import session_store
    from simulator.auth_3layer import get_auth_3layer_manager, hash_password
    from simulator.server import app
    from simulator.voice_config import OWNER_EMAIL

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    seed_accounts = ROOT / "simulator" / "data" / "accounts_3layer.json"
    accounts = json.loads(seed_accounts.read_text(encoding="utf-8"))
    for acc in accounts:
        if str(acc.get("email") or "").lower() == OWNER_EMAIL.lower():
            acc["password_hash"] = hash_password("TestPass!2026")
            acc.pop("pending_otp", None)
    (data_dir / "accounts_3layer.json").write_text(
        json.dumps(accounts, ensure_ascii=False), encoding="utf-8"
    )

    db_path = data_dir / "smarthome.db"
    monkeypatch.setenv("SMARTHOME_DATA_DIR", str(data_dir))
    monkeypatch.setenv("SMARTHOME_DURABLE_DIR", str(tmp_path / "durable"))
    monkeypatch.setenv("SMARTHOME_SQLITE_PATH", str(db_path))
    monkeypatch.setenv("SMARTHOME_SECURITY_BACKEND", "sqlite")
    monkeypatch.setenv("PYTEST", "1")
    monkeypatch.delenv("SIMULATOR_SECURITY_STATE_DIR", raising=False)
    monkeypatch.setenv("SIMULATOR_OFFLINE_SANDBOX", "1")
    monkeypatch.setattr(durable_store, "_GLOBAL_DURABLE_STORE", None)
    monkeypatch.setattr(auth_3layer, "_AUTH_MANAGER", None)
    isolated_store = session_store.SessionStore(db_path=db_path)
    monkeypatch.setattr(session_store, "_SESSION_STORE", isolated_store)

    mig = migrate_all(
        target_db=db_path,
        source_dir=data_dir,
        fetch_github=False,
        seed_assets=False,
        upgrade_repo_db=False,
    )
    assert mig["ok"] is True
    mgr = get_auth_3layer_manager()

    https_headers = {
        "X-Forwarded-Proto": "https",
        "Host": "laptop-6i654f8c.tail3020d6.ts.net",
    }
    with TestClient(app) as client:
        # 1. Owner Layer-1 -> OTP -> Layer-2 verify sets hardened cookies
        r1 = client.post(
            "/api/auth3/layer1_login",
            json={"email": OWNER_EMAIL, "password": "TestPass!2026", "send_gmail": False},
            headers=https_headers,
        )
        assert r1.status_code == 200 and r1.json()["ok"], r1.text
        otp = r1.json().get("otp_code_for_test") or mgr.pending_otps[OWNER_EMAIL.lower()]["otp_code"]
        r2 = client.post(
            "/api/auth3/layer2_verify_otp",
            json={"email": OWNER_EMAIL, "otp_code": otp},
            headers=https_headers,
        )
        assert r2.status_code == 200 and r2.json()["ok"], r2.text
        _assert_session_cookies_hardened(r2.headers.get_list("set-cookie"))
        owner_tok = r2.json()["session_token"]

        # 2. Mint realtime ws_ticket and authenticate GET /api/state?ticket=...
        unauth_t = client.post("/api/auth/ws_ticket")
        assert unauth_t.status_code == 401
        t_resp = client.post("/api/auth/ws_ticket", headers={"X-Session-Token": owner_tok})
        assert t_resp.status_code == 200
        ticket = t_resp.json()["ticket"]
        assert ticket and "." in ticket

        st_via_ticket = client.get(f"/api/state?ticket={ticket}")
        assert st_via_ticket.status_code == 200
        assert st_via_ticket.json()["authenticated"] is True

        # 3. Guest invite + redeem sets hardened cookies over HTTPS
        inv = client.post(
            "/api/auth3/guest_invites",
            json={"tier": 3, "ttl_sec": 3600, "pin": "2468", "pin_confirm": "2468"},
            headers={"X-Session-Token": owner_tok},
        )
        assert inv.status_code == 200
        redeem = client.post(
            "/api/guest/redeem",
            json={"token": inv.json()["token"]},
            headers=https_headers,
        )
        assert redeem.status_code == 200 and redeem.json()["ok"]
        _assert_session_cookies_hardened(redeem.headers.get_list("set-cookie"))


def test_s0c_vercel_proxy_app_preserves_cookies_and_streams_sse(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S0c: api.index.create_vercel_proxy_app forwards REST, strips cookie Domain, and streams SSE."""
    from api.index import create_vercel_proxy_app
    from scripts.migrate_to_sqlite import migrate_all

    env = os.environ.copy()
    password = prepare_live_auth(env, str(tmp_path))
    data_dir = pathlib.Path(env["SMARTHOME_DATA_DIR"])
    db_path = data_dir / "smarthome.db"
    env["SMARTHOME_SQLITE_PATH"] = str(db_path)
    env["SIMULATOR_OFFLINE_SANDBOX"] = "1"
    env.pop("PYTEST_CURRENT_TEST", None)

    mig = migrate_all(
        target_db=db_path,
        source_dir=data_dir,
        fetch_github=False,
        seed_assets=False,
        upgrade_repo_db=False,
    )
    assert mig["ok"] is True

    port = _free_port()
    proxy_port = _free_port()
    upstream_url = f"http://127.0.0.1:{port}"
    proxy_url = f"http://127.0.0.1:{proxy_port}"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "simulator.server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    proxy_env = env.copy()
    proxy_env["VERCEL"] = "1"
    proxy_env["SMARTHOME_UPSTREAM_ORIGIN"] = upstream_url
    proxy_env.pop("SMARTHOME_DISABLE_UPSTREAM_PROXY", None)
    proxy_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "api.index:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(proxy_port),
            "--log-level",
            "warning",
        ],
        cwd=str(ROOT),
        env=proxy_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_server_ready(upstream_url, timeout_sec=15.0)
        _wait_server_ready(proxy_url, timeout_sec=15.0)
        owner_token = login_live_owner(upstream_url, password)

        async def _exercise_proxy() -> None:
            fwd_headers = {
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "do-an-tot-nghiep-smart-home-voice-a.vercel.app",
            }
            async with httpx.AsyncClient(
                base_url=proxy_url,
                timeout=httpx.Timeout(10.0),
            ) as client:
                # 1. Proxied /api/health
                h = await client.get("/api/health", headers=fwd_headers)
                assert h.status_code == 200
                assert h.json()["ok"] is True

                # 2. Proxied /api/device mutation
                d = await client.post(
                    "/api/device",
                    json={"device_id": "speaker_amp", "action": "on"},
                    headers={**fwd_headers, "X-Session-Token": owner_token},
                )
                assert d.status_code == 200
                assert d.json()["ok"] is True

                # 3. Proxied login strips Domain= and keeps HttpOnly + Secure
                login_r = await client.post(
                    "/api/auth3/layer1_login",
                    json={"email": "nep94121@gmail.com", "password": password, "send_gmail": False},
                    headers=fwd_headers,
                )
                assert login_r.status_code == 200 and login_r.json()["ok"]
                otp_code = login_r.json().get("otp_code_for_test") or login_r.json().get("demo_otp_preview")
                assert otp_code
                verify_r = await client.post(
                    "/api/auth3/layer2_verify_otp",
                    json={"email": "nep94121@gmail.com", "otp_code": otp_code},
                    headers=fwd_headers,
                )
                assert verify_r.status_code == 200 and verify_r.json()["ok"]
                sc_list = verify_r.headers.get_list("set-cookie")
                _assert_session_cookies_hardened(sc_list)
                assert all("domain=" not in c.lower() for c in sc_list), sc_list

                # 4. Proxied SSE /api/events streams initial frame over real TCP
                async with client.stream(
                    "GET",
                    "/api/events",
                    headers={**fwd_headers, "X-Session-Token": owner_token},
                ) as sse_resp:
                    assert sse_resp.status_code == 200
                    assert "text/event-stream" in sse_resp.headers.get("content-type", "")
                    collected: list[str] = []
                    async for line in sse_resp.aiter_lines():
                        collected.append(line)
                        if line.startswith("data: "):
                            payload = json.loads(line[6:])
                            assert payload["type"] == "state_snapshot"
                            assert "devices" in payload["snapshot"]
                            break
                    assert any(l.startswith("data: ") for l in collected)

                # 5. Offline upstream returns clean 502
                offline_proxy = create_vercel_proxy_app("http://127.0.0.1:1")
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=offline_proxy),
                    base_url="https://do-an-tot-nghiep-smart-home-voice-a.vercel.app",
                ) as off_client:
                    bad = await off_client.get("/api/health")
                    assert bad.status_code == 502
                    assert bad.json()["ok"] is False

        asyncio.run(_exercise_proxy())
    finally:
        for child in (proxy_proc, proc):
            child.terminate()
            try:
                child.wait(timeout=5)
            except Exception:
                child.kill()


def test_p1c_text_command_under_3s_and_aoede_sqlite_cache(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1-C: /api/text_command <= 3.0s with non-empty Aoede audio and SQLite aoede_audio_cache hit."""
    from simulator.db_migrations import apply_schema_migrations, open_wal_connection
    from simulator.live import tts_rejection_vi as tts
    from simulator.server import app

    db_path = tmp_path / "smarthome.db"
    conn = open_wal_connection(db_path)
    apply_schema_migrations(conn)
    conn.close()

    monkeypatch.setenv("SMARTHOME_SQLITE_PATH", str(db_path))
    monkeypatch.setenv("SIMULATOR_OFFLINE_SANDBOX", "1")
    tts._LIVE_AOEDE_SESSION_CACHE.clear()
    tts._LIVE_AOEDE_SOURCE_CACHE.clear()
    tts._LIVE_AOEDE_MODEL_CACHE.clear()

    # Write a genuine-format 24kHz PCM sample to SQLite cache for the expected spoken reply
    fake_pcm = b"\x10\x00\xf0\xff" * 2400  # 9600 bytes (200ms @ 24kHz)
    phrase_a = "Đã mở cửa chính."
    phrase_b = "Cửa chính đã được mở."
    for p in (phrase_a, phrase_b):
        tts._write_sqlite_aoede_cache(p, fake_pcm, "gemini-2.5-flash-native-audio-preview-12-2025")

    # Also test end-to-end cache hit even after clearing RAM cache
    async def _verify_cache() -> None:
        tts._LIVE_AOEDE_SESSION_CACHE.clear()
        t0 = time.perf_counter()
        bundle = await tts.synthesize_aoede_phrase_audio(phrase_a, allow_live_refresh=False)
        elapsed = time.perf_counter() - t0
        assert elapsed < 0.25
        assert bundle["voice_name"] == "Aoede"
        assert len(base64.b64decode(bundle["pcm24k_b64"])) == len(fake_pcm)

    asyncio.run(_verify_cache())

    with TestClient(app) as client:
        # Ensure deterministic OFF -> ON transition first
        rst = client.post(
            "/api/device",
            json={"device_id": "living_room_light", "action": "off"},
            headers={"X-Session-Token": "sess_owner_t1_nep94121"},
        )
        assert rst.status_code == 200

        # Execute live text command to toggle living room light ON
        t0 = time.perf_counter()
        resp = client.post(
            "/api/text_command",
            json={"text": "Bật đèn phòng khách"},
            headers={"X-Session-Token": "sess_owner_t1_nep94121"},
        )
        dt = time.perf_counter() - t0
        assert resp.status_code == 200
        assert dt <= 3.0, f"/api/text_command took {dt:.3f}s (> 3.0s)"
        data = resp.json()
        assert data["ok"] is True
        spoken = str(data.get("exact_spoken_reply") or "")
        assert spoken

        # Seed SQLite cache with the exact spoken text returned by RuleEngine and confirm instant return
        tts._write_sqlite_aoede_cache(spoken, fake_pcm, "gemini-2.5-flash-native-audio-preview-12-2025")
        tts._LIVE_AOEDE_SESSION_CACHE.clear()
        t1 = time.perf_counter()
        resp2 = client.post(
            "/api/text_command",
            json={"text": "Tắt đèn phòng khách"},
            headers={"X-Session-Token": "sess_owner_t1_nep94121"},
        )
        dt2 = time.perf_counter() - t1
        assert resp2.status_code == 200
        assert dt2 <= 3.0
        # Seeded phrase returns pcm24k_b64 + Aoede cleanly on matching OFF -> ON reply
        tts._write_sqlite_aoede_cache(resp2.json()["exact_spoken_reply"], fake_pcm, "gemini-2.5-flash-native-audio-preview-12-2025")
        tts._LIVE_AOEDE_SESSION_CACHE.clear()
        resp3 = client.post(
            "/api/text_command",
            json={"text": "Bật đèn phòng khách"},
            headers={"X-Session-Token": "sess_owner_t1_nep94121"},
        )
        d3 = resp3.json()
        assert d3["exact_spoken_reply"] == spoken
        assert d3["voice_name"] == "Aoede"
        assert len(base64.b64decode(d3["pcm24k_b64"])) >= 2400


def test_p1a_live_server_playwright_optimistic_ui_and_bidirectional_1s_sync(tmp_path: pathlib.Path) -> None:
    """P1-A: Playwright real Chrome proof of <=300ms optimistic UI & 12/12 bidirectional <=1.0s sync + voice door."""
    from playwright.async_api import async_playwright
    from scripts.migrate_to_sqlite import migrate_all

    env = os.environ.copy()
    password = prepare_live_auth(env, str(tmp_path))
    data_dir = pathlib.Path(env["SMARTHOME_DATA_DIR"])
    sqlite_path = data_dir / "smarthome.db"
    env["SMARTHOME_SQLITE_PATH"] = str(sqlite_path)
    env["SIMULATOR_OFFLINE_SANDBOX"] = "1"
    env.pop("PYTEST_CURRENT_TEST", None)

    mig = migrate_all(
        target_db=sqlite_path,
        source_dir=data_dir,
        fetch_github=False,
        seed_assets=False,
        upgrade_repo_db=False,
    )
    assert mig["ok"] is True

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "simulator.server:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_server_ready(base_url, timeout_sec=15.0)
        owner_token = login_live_owner(base_url, password)

        async def _run_browsers() -> None:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, channel="chrome")
                try:
                    desktop_ctx = await browser.new_context(viewport={"width": 1366, "height": 768})
                    mobile_ctx = await browser.new_context(viewport={"width": 390, "height": 844})

                    # Authenticate both contexts via real HTTP login / cookie + storage
                    await desktop_ctx.add_cookies(
                        [
                            {"name": "sh_session_token", "value": owner_token, "url": base_url, "httpOnly": True},
                            {"name": "session_token", "value": owner_token, "url": base_url, "httpOnly": True},
                        ]
                    )
                    await mobile_ctx.add_cookies(
                        [
                            {"name": "sh_session_token", "value": owner_token, "url": base_url, "httpOnly": True},
                            {"name": "session_token", "value": owner_token, "url": base_url, "httpOnly": True},
                        ]
                    )

                    d_page = await desktop_ctx.new_page()
                    m_page = await mobile_ctx.new_page()

                    init_js = f"""
                    window._testOwnerSessionInit = true;
                    sessionStorage.setItem('mobileLoggedIn', '1');
                    sessionStorage.setItem('mobileLoggedInEmail', 'nep94121@gmail.com');
                    """
                    await m_page.add_init_script(init_js)

                    await d_page.goto(base_url, wait_until="domcontentloaded")
                    await m_page.goto(f"{base_url}/app", wait_until="domcontentloaded")

                    # Assert HttpOnly cookies are never exposed to document.cookie in either UI
                    d_cookie = await d_page.evaluate("() => document.cookie")
                    m_cookie = await m_page.evaluate("() => document.cookie")
                    assert "sh_session_token=" not in d_cookie
                    assert "session_token=" not in d_cookie
                    assert "sh_session_token=" not in m_cookie
                    assert "session_token=" not in m_cookie

                    # Wait for devices to render on both views
                    await d_page.wait_for_selector("#dev-card-living_room_light .switch", timeout=10000)
                    await m_page.wait_for_selector("#mobileNavTabDevices", state="visible", timeout=10000)
                    await m_page.click("#mobileNavTabDevices")
                    await m_page.wait_for_selector(
                        "#devGrid [data-device-id='living_room_light']",
                        state="attached",
                        timeout=10000,
                    )

                    # Give WS + SSE a moment to complete handshake
                    await asyncio.sleep(0.5)

                    dev_ids = [
                        "living_room_light",
                        "bedroom_light",
                        "garden_pump",
                        "main_door",
                        "alarm_siren",
                        "speaker_amp",
                    ]

                    async def _wait_state(page: Any, sel: str, expected: str, timeout_s: float = 1.0) -> float:
                        t_start = time.perf_counter()
                        deadline = t_start + timeout_s
                        while time.perf_counter() < deadline:
                            st = await page.get_attribute(sel, "data-state")
                            if st == expected:
                                return time.perf_counter() - t_start
                            await asyncio.sleep(0.02)
                        actual = await page.get_attribute(sel, "data-state")
                        raise AssertionError(f"Timeout {timeout_s}s waiting {sel} -> {expected}, got {actual}")

                    # 6 toggles Desktop -> Mobile
                    for idx, did in enumerate(dev_ids):
                        d_sel = f"#dev-card-{did}"
                        m_sel = f"#devGrid [data-device-id='{did}']"
                        cur = await d_page.get_attribute(d_sel, "data-state")
                        nxt = "off" if cur == "on" else "on"

                        t_click = time.perf_counter()
                        await d_page.click(f"{d_sel} .switch")
                        opt_dt = await _wait_state(d_page, d_sel, nxt, timeout_s=0.30)
                        assert opt_dt <= 0.30, f"Desktop optimistic UI too slow for {did}: {opt_dt:.3f}s"
                        await _wait_state(m_page, m_sel, nxt, timeout_s=1.0)
                        sync_dt = time.perf_counter() - t_click
                        assert sync_dt <= 1.0, f"Desktop -> Mobile sync >1.0s for {did}: {sync_dt:.3f}s"

                    # 6 toggles Mobile -> Desktop
                    for idx, did in enumerate(dev_ids):
                        d_sel = f"#dev-card-{did}"
                        m_sel = f"#devGrid [data-device-id='{did}']"
                        cur = await m_page.get_attribute(m_sel, "data-state")
                        nxt = "off" if cur == "on" else "on"

                        t_click = time.perf_counter()
                        await m_page.click(m_sel)
                        opt_dt = await _wait_state(m_page, m_sel, nxt, timeout_s=0.30)
                        assert opt_dt <= 0.30, f"Mobile optimistic UI too slow for {did}: {opt_dt:.3f}s"
                        await _wait_state(d_page, d_sel, nxt, timeout_s=1.0)
                        sync_dt = time.perf_counter() - t_click
                        assert sync_dt <= 1.0, f"Mobile -> Desktop sync >1.0s for {did}: {sync_dt:.3f}s"

                    # Voice & Text main_door sync <= 1.0s
                    import urllib.request

                    def _post_api(path: str, body: dict[str, Any]) -> dict[str, Any]:
                        req = urllib.request.Request(
                            f"{base_url}{path}",
                            data=json.dumps(body).encode("utf-8"),
                            headers={"Content-Type": "application/json", "X-Session-Token": owner_token},
                        )
                        with urllib.request.urlopen(req, timeout=5) as resp:
                            return json.loads(resp.read().decode("utf-8"))

                    cur_door = await d_page.get_attribute("#dev-card-main_door", "data-state")
                    txt_cmd = "Đóng cửa chính" if cur_door == "on" else "Mở cửa chính"
                    exp_txt = "off" if cur_door == "on" else "on"
                    _post_api("/api/text_command", {"text": txt_cmd})
                    _post_api("/api/text_command", {"text": "ok"})
                    await _wait_state(d_page, "#dev-card-main_door", exp_txt, timeout_s=1.0)
                    await _wait_state(m_page, "#devGrid [data-device-id='main_door']", exp_txt, timeout_s=1.0)

                    voice_cmd = "Đóng cửa chính" if exp_txt == "on" else "Mở cửa chính"
                    exp_voice = "off" if exp_txt == "on" else "on"
                    _post_api("/api/voice_command", {"transcript": voice_cmd})
                    _post_api("/api/voice_command", {"transcript": "ok"})
                    await _wait_state(d_page, "#dev-card-main_door", exp_voice, timeout_s=1.0)
                    await _wait_state(m_page, "#devGrid [data-device-id='main_door']", exp_voice, timeout_s=1.0)
                finally:
                    await browser.close()

        asyncio.run(_run_browsers())
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
