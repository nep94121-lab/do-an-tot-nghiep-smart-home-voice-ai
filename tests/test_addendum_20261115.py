"""Comprehensive P0/P1/P2 + ADDENDUM A-F regression tests (2026-11-15)."""

from __future__ import annotations

import asyncio
import datetime
import json
import pathlib
import re
import time
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api.deps import _BOOT_VOICE_AUTH, _REST_ENGINE
from backend.api.routes_auth import set_dual_session_cookies
from backend.auth.guest_invites import create_invite, get_invite, inspect_token
from backend.auth.session_store import UserSession
from backend.automation_nlu import (
    handle_confirmation_reply,
    prepare_pending_mutation,
    process_automation_nlu_command,
)
from backend.automation_repo import (
    GUEST_ONLY_TOGGLE_MSG_VI,
    TIER1_SCHEDULE_CONFLICT_MSG_VI,
    can_user_create_links,
    create_schedule,
    find_custom_command_by_text,
    list_automation_rules,
    list_custom_commands,
    list_pending_timers,
    list_schedules,
    reset_custom_commands_scoped,
    reset_links_scoped,
    reset_timers_and_schedules_scoped,
    set_user_can_create_links,
    upsert_custom_command,
)
from backend.db_migrations import (
    NORMALIZED_TABLE_ORDER,
    open_wal_connection,
    resolve_sqlite_db_path,
)
from backend.engine.audit_logger import read_audit_logs
from backend.live.gemini_bridge import LiveBridgeSession
from backend.rule_engine import SmartHomeEngine
from backend.server import app

ROOT = pathlib.Path(__file__).resolve().parent.parent

H_TIER1 = {"X-Session-Token": "sess_owner_t1_nep94121"}
H_TIER2 = {"X-Session-Token": "sess_family_t2_member_a"}
H_TIER3 = {"X-Session-Token": "sess_guest_t3_visitor_c"}

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001F9FF"
    "\U0001FA70-\U0001FAFF"
    "\u2600-\u26FF"
    "\u2700-\u27BF"
    "\u2B00-\u2BFF"
    "\u231A-\u23FF"
    "\u2794"
    "]",
    flags=re.UNICODE,
)


def _clear_all_automation_state() -> None:
    reset_custom_commands_scoped(clear_all=True)
    reset_links_scoped(clear_all=True)
    reset_timers_and_schedules_scoped(clear_all=True)
    set_user_can_create_links("thanh_vien_a", False, owner_tier=2, display_name="Thành viên A")
    dbp = resolve_sqlite_db_path()
    conn = open_wal_connection(dbp, readonly=False)
    try:
        conn.execute("DELETE FROM pending_confirmations")
        conn.commit()
    finally:
        conn.close()
    _REST_ENGINE.sync_automation_pools_from_sqlite(emit_snapshot=False)
    for tid in list(_REST_ENGINE.active_timers.keys()):
        t = _REST_ENGINE._timer_tasks.pop(tid, None)
        if t is not None:
            t.cancel()
        _REST_ENGINE.active_timers.pop(tid, None)


@pytest.fixture(autouse=True)
def _clean_addendum_pools(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("SIMULATOR_OFFLINE_SANDBOX", "1")
    _BOOT_VOICE_AUTH.reset_strikes()
    _clear_all_automation_state()
    yield
    _clear_all_automation_state()
    _BOOT_VOICE_AUTH.reset_strikes()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


# ==============================================================================
# 1. P2 SCHEMA (25 TABLES, FKs, HASHED INVITES, COOKIE HYGIENE) & STATIC ASSETS
# ==============================================================================


class TestSchemaSecurityAndDelivery:
    """Verify 25 normalized tables, FKs, invite hashing, cookies, caching, ERD & Vercel."""

    def test_sqlite_25_tables_and_foreign_keys(self) -> None:
        dbp = resolve_sqlite_db_path()
        conn = open_wal_connection(dbp, readonly=True)
        try:
            fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            assert int(fk) == 1
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            tbls = {str(r[0]) for r in rows}
            assert len(NORMALIZED_TABLE_ORDER) == 25
            assert set(NORMALIZED_TABLE_ORDER).issubset(tbls)
            assert len(tbls) >= 25

            fk_sessions = [str(r[2]) for r in conn.execute("PRAGMA foreign_key_list(sessions)").fetchall()]
            fk_user_sessions = [str(r[2]) for r in conn.execute("PRAGMA foreign_key_list(user_sessions)").fetchall()]
            assert "users" in fk_sessions
            assert "users" in fk_user_sessions
        finally:
            conn.close()

    def test_invites_store_hash_only_never_plaintext(self) -> None:
        import hashlib

        created = create_invite(owner_user_id="tuan_anh", tier=3)
        raw_token = str(created["token"])
        jti = str(created["invite_id"])
        expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        assert raw_token.startswith("inv_")

        stored = get_invite(jti)
        assert stored is not None
        assert "token" not in stored
        assert stored.get("token_hash") == expected_hash
        assert len(str(stored.get("token_hash"))) == 64

        conn = open_wal_connection(resolve_sqlite_db_path(), readonly=True)
        try:
            row = conn.execute(
                "SELECT jti, token_hash, tier, revoked FROM invites WHERE jti = ?",
                (jti,),
            ).fetchone()
            if row is not None:
                assert row[1] == expected_hash
                assert raw_token not in str(row[1])
        finally:
            conn.close()

        verified = inspect_token(raw_token)
        assert verified.get("valid") is True
        assert verified.get("invite_id") == jti

    def test_dual_session_cookies_delete_mobile_email_cookie(self) -> None:
        from fastapi.responses import JSONResponse

        resp = JSONResponse({"ok": True})
        set_dual_session_cookies(resp, "sess_test_123", None, email="owner@example.com")
        set_cookies = resp.headers.getlist("set-cookie")
        joined = "\n".join(set_cookies)
        assert "sh_session_token=sess_test_123" in joined
        assert "HttpOnly" in joined
        assert "mobileLoggedInEmail=" in joined
        email_hdr = [h for h in set_cookies if h.startswith("mobileLoggedInEmail=")]
        assert len(email_hdr) == 1
        assert "Max-Age=0" in email_hdr[0] or "expires=" in email_hdr[0].lower()

    def test_caching_etag_304_gzip_health_and_erd_and_vercel(self, client: TestClient) -> None:
        r_js = client.get("/static/js/app.js", headers={"Accept-Encoding": "gzip"})
        assert r_js.status_code == 200
        assert "public, max-age=3600" in (r_js.headers.get("cache-control") or "")
        etag = r_js.headers.get("etag")
        assert etag
        assert "gzip" in (r_js.headers.get("content-encoding") or "").lower()

        r_304 = client.get("/static/js/app.js", headers={"If-None-Match": etag})
        assert r_304.status_code == 304

        r_health = client.get("/api/health")
        assert r_health.status_code == 200
        assert "no-store" in (r_health.headers.get("cache-control") or "")
        body_h = r_health.json()
        assert int(body_h.get("table_count", 0)) >= 25

        r_erd = client.get("/archify/erd")
        assert r_erd.status_code == 200
        html_erd = r_erd.text
        for tbl in NORMALIZED_TABLE_ORDER:
            assert tbl in html_erd

        v_cfg = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        redirects = v_cfg.get("redirects") or []
        assert any(
            isinstance(rd, dict)
            and bool(rd.get("permanent"))
            and "laptop-6i654f8c.tail3020d6.ts.net" in str(rd.get("destination", ""))
            for rd in redirects
        )
        v_ign = (ROOT / ".vercelignore").read_text(encoding="utf-8")
        assert "backend" in v_ign and "firmware" in v_ign and "hardware" in v_ign


# ==============================================================================
# 2. P0 ZERO SPEAKER VERIFICATION & STRIKE COUNTER RESET
# ==============================================================================


class TestZeroSpeakerVerification:
    """Verify speaker verification is removed on voice HTTP & Live mic paths."""

    def test_voice_auth_boot_strikes_zero_and_http_voice_ignores_voiceprint(self, client: TestClient) -> None:
        _BOOT_VOICE_AUTH.unauthorized_strikes = 5
        _BOOT_VOICE_AUTH.reset_strikes()
        assert _BOOT_VOICE_AUTH.unauthorized_strikes == 0

        # Tier 3 guest sends transcript via /api/voice_command without matching owner voiceprint
        r_ok = client.post(
            "/api/voice_command",
            headers=H_TIER3,
            json={"transcript": "bật đèn phòng khách", "source": "web_voice"},
        )
        assert r_ok.status_code == 200
        data_ok = r_ok.json()
        assert data_ok.get("ok") is True
        assert data_ok.get("ask_repeat") is False
        assert "vui lòng nói lại" not in str(data_ok.get("exact_spoken_reply", "")).lower()
        assert _BOOT_VOICE_AUTH.unauthorized_strikes == 0

        # Unauthenticated voice_command fails closed cleanly with 401
        r_unauth = client.post("/api/voice_command", json={"transcript": "bật đèn phòng khách"})
        assert r_unauth.status_code == 401

    def test_live_bridge_streams_mic_pcm_without_speaker_block(self) -> None:
        async def _run() -> None:
            sent_frames: list[Any] = []

            class _DummyGemini:
                async def send_realtime_input(self, **kwargs: Any) -> None:
                    sent_frames.append(kwargs)

            t3_sess = UserSession(
                session_id="sess_guest_live_t3",
                user_id="khach_c",
                email="",
                display_name="Khách C",
                tier=3,
                role="CHILD_GUEST",
                created_at=time.time(),
                expires_at=time.time() + 3600,
                source="qr_invite",
                is_authenticated=True,
            )
            br = LiveBridgeSession(engine=_REST_ENGINE, ws_session=t3_sess)
            br.gemini_session = _DummyGemini()
            br.send_ws_json = lambda payload: asyncio.sleep(0)  # type: ignore[method-assign]
            pcm_chunk = b"\x05\x00" * 320
            for _ in range(4):
                await br.handle_mic_chunk(pcm_chunk, is_sp=True)
            await br.mic_speech_ended()

            assert br.last_mic_turn_blocked is False
            assert br.voice_auth.unauthorized_strikes == 0
            assert len(sent_frames) >= 4
            assert br.engine.current_tier == 3

        asyncio.run(_run())


# ==============================================================================
# 3. ADDENDUM A/B/C: 3 POOLS ISOLATION, 4-STEP CONFIRMATION (20s TTL), QUERIES & RESETS
# ==============================================================================


class TestAddendumPoolsConfirmAndQueries:
    """Test isolated per-user pools, 4-step confirmation + 20s TTL, queries, and scoped resets."""

    def test_per_user_custom_command_pool_isolation(self) -> None:
        upsert_custom_command(
            owner_user_id="tuan_anh",
            owner_tier=1,
            owner_name="Nguyễn Tuấn Anh",
            phrase="chế độ ngủ",
            steps=[{"device_id": "living_room_light", "action": "turn_off"}],
        )
        upsert_custom_command(
            owner_user_id="thanh_vien_a",
            owner_tier=2,
            owner_name="Thành viên A",
            phrase="chế độ ngủ",
            steps=[{"device_id": "bedroom_light", "action": "turn_on"}],
        )

        c1 = find_custom_command_by_text("chế độ ngủ", owner_user_id="tuan_anh")
        c2 = find_custom_command_by_text("chế độ ngủ", owner_user_id="thanh_vien_a")
        assert c1 is not None and c2 is not None
        assert c1["command_id"] != c2["command_id"]
        assert c1["steps"][0]["device_id"] == "living_room_light"
        assert c2["steps"][0]["device_id"] == "bedroom_light"

        all_cmds = list_custom_commands(include_disabled=False)
        assert len(all_cmds) == 2

    def test_immediate_toggle_skips_confirmation(self, client: TestClient) -> None:
        # Both direct UI toggle (/api/device) and simple text command execute immediately (act-first policy).
        r_ui = client.post("/api/device", headers=H_TIER1, json={"device_id": "living_room_light", "action": "turn_on"})
        assert r_ui.status_code == 200 and r_ui.json().get("ok") is True
        assert _REST_ENGINE.devices["living_room_light"]["state"] == "ON"
        client.post("/api/device", headers=H_TIER1, json={"device_id": "living_room_light", "action": "turn_off"})

        r = client.post("/api/text_command", headers=H_TIER1, json={"text": "bật đèn phòng khách"})
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert not data.get("requires_confirmation")
        assert _REST_ENGINE.devices["living_room_light"]["state"] == "ON"

    @pytest.mark.parametrize("confirm_word", ["xác nhận", "đúng", "ừ", "ok"])
    def test_4step_confirmation_commits_on_positive_words(self, client: TestClient, confirm_word: str) -> None:
        r1 = client.post(
            "/api/text_command",
            headers=H_TIER1,
            json={"text": "5 giây nữa bật đèn phòng ngủ"},
        )
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1.get("requires_confirmation") is True
        assert str(d1.get("exact_spoken_reply", "")).endswith("đúng không ạ?")
        assert len(list_pending_timers()) == 0

        r2 = client.post("/api/text_command", headers=H_TIER1, json={"text": confirm_word})
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2.get("ok") is True
        assert len(list_pending_timers()) == 1

    @pytest.mark.parametrize("cancel_word", ["không", "hủy", "đừng", "dừng"])
    def test_4step_confirmation_cancels_including_dung_vs_duong(self, client: TestClient, cancel_word: str) -> None:
        r1 = client.post(
            "/api/text_command",
            headers=H_TIER1,
            json={"text": "tạo lệnh chế độ đi ngủ gồm tắt đèn phòng khách"},
        )
        assert r1.status_code == 200
        assert r1.json().get("requires_confirmation") is True
        assert len(list_custom_commands()) == 0

        r2 = client.post("/api/text_command", headers=H_TIER1, json={"text": cancel_word})
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2.get("cancelled") is True
        assert "Đã hủy" in str(d2.get("exact_spoken_reply", ""))
        assert len(list_custom_commands()) == 0

    def test_4step_confirmation_20s_ttl_expiration(self) -> None:
        async def _run() -> None:
            t1_sess = UserSession(
                session_id="sess_ttl_t1",
                user_id="tuan_anh",
                email="",
                display_name="Nguyễn Tuấn Anh",
                tier=1,
                role="ADMIN",
                created_at=time.time(),
                expires_at=time.time() + 3600,
                source="text_command",
                is_authenticated=True,
            )
            staged = await prepare_pending_mutation(
                engine=_REST_ENGINE,
                session=t1_sess,
                source="text_command",
                action_kind="create_timer",
                payload={"device_id": "living_room_light", "action": "turn_on", "seconds": 15.0},
                prompt_summary="Đặt hẹn giờ sau 15 giây sẽ bật đèn phòng khách",
                ttl_sec=1.0,
            )
            pid = staged["payload"]["pending_id"]
            conn = open_wal_connection(resolve_sqlite_db_path(), readonly=False)
            try:
                conn.execute(
                    "UPDATE pending_confirmations SET expires_at = ? WHERE pending_id = ?",
                    (time.time() - 5.0, pid),
                )
                conn.commit()
            finally:
                conn.close()

            reply = await handle_confirmation_reply(
                raw_text="xác nhận",
                engine=_REST_ENGINE,
                session=t1_sess,
                source="text_command",
            )
            assert reply is not None
            assert reply["payload"].get("expired") is True
            assert "Đã hủy" in str(reply["payload"].get("exact_spoken_reply", ""))
            assert len(list_pending_timers()) == 0

        asyncio.run(_run())

    def test_scoped_resets_and_queries(self, client: TestClient) -> None:
        upsert_custom_command(
            owner_user_id="tuan_anh",
            owner_tier=1,
            owner_name="Nguyễn Tuấn Anh",
            phrase="lệnh chủ nhà",
            steps=[{"device_id": "living_room_light", "action": "turn_on"}],
        )
        upsert_custom_command(
            owner_user_id="thanh_vien_a",
            owner_tier=2,
            owner_name="Thành viên A",
            phrase="lệnh thành viên",
            steps=[{"device_id": "bedroom_light", "action": "turn_on"}],
        )

        # Tier 2 reset own custom commands -> Tier 1 preserved
        r_rst = client.post("/api/text_command", headers=H_TIER2, json={"text": "reset lệnh custom"})
        assert r_rst.status_code == 200 and r_rst.json().get("requires_confirmation") is True
        r_cfm = client.post("/api/text_command", headers=H_TIER2, json={"text": "xác nhận"})
        assert r_cfm.status_code == 200 and r_cfm.json().get("ok") is True

        assert len(list_custom_commands(owner_user_id="thanh_vien_a")) == 0
        assert len(list_custom_commands(owner_user_id="tuan_anh")) == 1

        # Tier 1 queries custom commands, timers/schedules, and household members
        r_q_cmd = client.post("/api/text_command", headers=H_TIER1, json={"text": "có những lệnh tùy chỉnh nào"})
        assert r_q_cmd.status_code == 200
        assert "lệnh chủ nhà" in str(r_q_cmd.json().get("exact_spoken_reply", "")).lower()

        create_schedule(
            owner_user_id="tuan_anh",
            owner_tier=1,
            owner_name="Nguyễn Tuấn Anh",
            device_id="living_room_light",
            action="turn_on",
            time_hhmm="07:00",
            schedule_type="daily",
        )
        r_q_tm = client.post("/api/text_command", headers=H_TIER1, json={"text": "đang có hẹn giờ nào"})
        assert r_q_tm.status_code == 200
        assert "07:00" in str(r_q_tm.json().get("exact_spoken_reply", ""))

        r_q_mem = client.post("/api/text_command", headers=H_TIER1, json={"text": "nhà có những thành viên nào"})
        assert r_q_mem.status_code == 200
        assert "Tuấn Anh" in str(r_q_mem.json().get("exact_spoken_reply", ""))

        # Tier 1 clears all timers/schedules across household
        r_all_rst = client.post("/api/text_command", headers=H_TIER1, json={"text": "xóa tất cả hẹn giờ của mọi người"})
        assert r_all_rst.status_code == 200 and r_all_rst.json().get("requires_confirmation") is True
        r_all_cfm = client.post("/api/text_command", headers=H_TIER1, json={"text": "xác nhận"})
        assert r_all_cfm.status_code == 200 and r_all_cfm.json().get("ok") is True
        assert len(list_schedules(include_disabled=False)) == 0


# ==============================================================================
# 4. ADDENDUM D: STRICT RBAC MATRIX, TIER 2 LINK PERMISSION, TIER 1 CONFLICT (409)
# ==============================================================================


class TestAddendumRBACAndConflicts:
    """Test Tier 1/2/3 RBAC across REST, NLU, and LiveBridgeSession tool calls."""

    def test_tier3_guest_only_toggles_allowed_devices(self, client: TestClient) -> None:
        # Allowed light toggle
        r_light = client.post(
            "/api/device",
            headers=H_TIER3,
            json={"device_id": "living_room_light", "action": "turn_on", "source": "web"},
        )
        assert r_light.status_code == 200
        assert r_light.json().get("ok") is True

        # Denied door & siren
        for restricted in ("main_door", "siren"):
            r_sec = client.post(
                "/api/device",
                headers=H_TIER3,
                json={"device_id": restricted, "action": "open" if restricted == "main_door" else "turn_on"},
            )
            assert r_sec.status_code == 403

        # Denied automation REST endpoints with exact spoken refusal
        for method, path, body in (
            ("get", "/api/automation", None),
            ("post", "/api/timers", {"device_id": "living_room_light", "action": "turn_off", "seconds": 15}),
            ("post", "/api/schedules", {"device_id": "living_room_light", "action": "turn_off", "time_hhmm": "09:00"}),
            ("post", "/api/rules", {"when_device_id": "main_door", "when_state": "OPEN", "then_device_id": "living_room_light", "then_action": "turn_on"}),
            ("post", "/api/scenes", {"phrase": "khách thử", "steps": [{"device_id": "living_room_light", "action": "turn_on"}]}),
        ):
            r = getattr(client, method)(path, headers=H_TIER3, **({"json": body} if body else {}))
            assert r.status_code == 403
            d = r.json()
            assert d.get("rbac_blocked") is True
            assert d.get("exact_spoken_reply") == GUEST_ONLY_TOGGLE_MSG_VI

        # Denied via text & voice NLU
        r_txt = client.post("/api/text_command", headers=H_TIER3, json={"text": "5 phút nữa tắt đèn phòng khách"})
        assert r_txt.status_code == 403
        assert r_txt.json().get("exact_spoken_reply") == GUEST_ONLY_TOGGLE_MSG_VI

        r_voc = client.post("/api/voice_command", headers=H_TIER3, json={"transcript": "5 phút nữa tắt đèn phòng khách"})
        assert r_voc.status_code == 403
        assert r_voc.json().get("exact_spoken_reply") == GUEST_ONLY_TOGGLE_MSG_VI

    def test_live_bridge_tier3_denied_automation_tools(self) -> None:
        async def _run() -> None:
            t3_sess = UserSession(
                session_id="sess_guest_tool_t3",
                user_id="khach_c",
                email="",
                display_name="Khách C",
                tier=3,
                role="CHILD_GUEST",
                created_at=time.time(),
                expires_at=time.time() + 3600,
                source="qr_invite",
                is_authenticated=True,
            )
            br = LiveBridgeSession(engine=_REST_ENGINE, ws_session=t3_sess)
            br.send_ws_json = lambda payload: asyncio.sleep(0)  # type: ignore[method-assign]
            res = await br.handle_tool_call(
                SimpleNamespace(name="schedule_action", args={"device_id": "living_room_light", "action": "turn_off", "seconds": 30})
            )
            assert res.get("ok") is False
            assert res.get("rbac_blocked") is True
            assert res.get("exact_spoken_reply") == GUEST_ONLY_TOGGLE_MSG_VI

        asyncio.run(_run())

    def test_tier2_link_permission_default_denied_grant_and_revoke(self, client: TestClient) -> None:
        assert can_user_create_links("thanh_vien_a", 2) is False
        rule_body = {
            "when_device_id": "living_room_light",
            "when_state": "ON",
            "then_device_id": "speaker_amp",
            "then_action": "turn_on",
        }
        r_denied = client.post("/api/rules", headers=H_TIER2, json=rule_body)
        assert r_denied.status_code == 403

        # Tier 2 cannot grant itself link permission
        r_self_grant = client.post(
            "/api/members/thanh_vien_a/link_permission",
            headers=H_TIER2,
            json={"allowed": True},
        )
        assert r_self_grant.status_code == 403

        # Tier 1 grants -> Step 1 stages confirmation -> Step 2 confirms -> Tier 2 succeeds -> Tier 1 revokes
        r_grant = client.post(
            "/api/members/thanh_vien_a/link_permission",
            headers=H_TIER1,
            json={"allowed": True},
        )
        assert r_grant.status_code == 200 and r_grant.json().get("requires_confirmation") is True
        assert can_user_create_links("thanh_vien_a", 2) is False
        r_grant2 = client.post(
            "/api/automation/confirm",
            headers=H_TIER1,
            json={"pending_id": r_grant.json()["pending_id"], "confirmed": True},
        )
        assert r_grant2.status_code == 200
        assert can_user_create_links("thanh_vien_a", 2) is True

        r_allowed = client.post("/api/rules", headers=H_TIER2, json=rule_body)
        assert r_allowed.status_code == 200 and r_allowed.json().get("requires_confirmation") is True
        assert len(list_automation_rules(owner_user_id="thanh_vien_a")) == 0
        r_allowed2 = client.post(
            "/api/automation/confirm",
            headers=H_TIER2,
            json={"pending_id": r_allowed.json()["pending_id"], "confirmed": True},
        )
        assert r_allowed2.status_code == 200
        assert len(list_automation_rules(owner_user_id="thanh_vien_a")) == 1

        r_revoke = client.post(
            "/api/members/thanh_vien_a/link_permission",
            headers=H_TIER1,
            json={"allowed": False},
        )
        assert r_revoke.status_code == 200 and r_revoke.json().get("requires_confirmation") is True
        r_revoke2 = client.post(
            "/api/automation/confirm",
            headers=H_TIER1,
            json={"pending_id": r_revoke.json()["pending_id"], "confirmed": True},
        )
        assert r_revoke2.status_code == 200
        r_denied2 = client.post(
            "/api/rules",
            headers=H_TIER2,
            json={
                "when_device_id": "bedroom_light",
                "when_state": "ON",
                "then_device_id": "garden_pump",
                "then_action": "turn_on",
            },
        )
        assert r_denied2.status_code == 403

    def test_tier2_schedule_conflict_within_60s_returns_409(self, client: TestClient) -> None:
        r_t1 = client.post(
            "/api/schedules",
            headers=H_TIER1,
            json={
                "device_id": "living_room_light",
                "action": "turn_on",
                "time_hhmm": "08:00",
                "schedule_type": "daily",
            },
        )
        assert r_t1.status_code == 200 and r_t1.json().get("requires_confirmation") is True
        r_t1_c = client.post(
            "/api/automation/confirm",
            headers=H_TIER1,
            json={"pending_id": r_t1.json()["pending_id"], "confirmed": True},
        )
        assert r_t1_c.status_code == 200

        # Same minute / +-60s by Tier 2 triggers 409 exact message
        r_t2_exact = client.post(
            "/api/schedules",
            headers=H_TIER2,
            json={
                "device_id": "bedroom_light",
                "action": "turn_off",
                "time_hhmm": "08:00",
                "schedule_type": "daily",
            },
        )
        assert r_t2_exact.status_code == 409
        d_exact = r_t2_exact.json()
        assert d_exact.get("conflict_tier1") is True
        assert d_exact.get("exact_spoken_reply") == TIER1_SCHEDULE_CONFLICT_MSG_VI

        # Within 1 minute (08:01 = +60s) also blocked with 409
        r_t2_60s = client.post(
            "/api/schedules",
            headers=H_TIER2,
            json={
                "device_id": "bedroom_light",
                "action": "turn_off",
                "time_hhmm": "08:01",
                "schedule_type": "once",
            },
        )
        assert r_t2_60s.status_code == 409
        assert r_t2_60s.json().get("exact_spoken_reply") == TIER1_SCHEDULE_CONFLICT_MSG_VI

        # Outside +-60s (08:05) stages cleanly then confirms
        r_t2_far = client.post(
            "/api/schedules",
            headers=H_TIER2,
            json={
                "device_id": "bedroom_light",
                "action": "turn_off",
                "time_hhmm": "08:05",
                "schedule_type": "daily",
            },
        )
        assert r_t2_far.status_code == 200 and r_t2_far.json().get("requires_confirmation") is True
        r_t2_far_c = client.post(
            "/api/automation/confirm",
            headers=H_TIER2,
            json={"pending_id": r_t2_far.json()["pending_id"], "confirmed": True},
        )
        assert r_t2_far_c.status_code == 200


# ==============================================================================
# 5. LOGS ZERO-EMOJI & TIMER RESTART SURVIVAL
# ==============================================================================


class TestLogsZeroEmojiAndRestartSurvival:
    """Verify /logs entries have 0 emojis and persisted timers survive restart."""

    def test_addendum_audit_logs_contain_zero_emojis(self, client: TestClient) -> None:
        client.post("/api/text_command", headers=H_TIER3, json={"text": "5 phút nữa tắt đèn phòng khách"})
        client.post("/api/text_command", headers=H_TIER1, json={"text": "5 giây nữa bật đèn phòng khách"})
        client.post("/api/text_command", headers=H_TIER1, json={"text": "xác nhận"})
        client.post("/api/device", headers=H_TIER1, json={"device_id": "living_room_light", "action": "turn_on"})

        logs = read_audit_logs(limit=40)
        assert len(logs) >= 3
        for item in logs[:10]:
            text_blob = f"{item.get('category', '')} {item.get('event_type', '')} {item.get('summary', '')}"
            assert not EMOJI_PATTERN.search(text_blob), f"Found forbidden emoji in audit log: {text_blob!r}"

    def test_restore_timers_from_sqlite_reloads_and_fires(self) -> None:
        async def _run() -> None:
            res = await _REST_ENGINE.schedule_timer_flexible(
                device_id="bedroom_light",
                action="turn_on",
                seconds=0.8,
                repeat="once",
                reason="Restart survival test",
            )
            assert res.get("ok") is True
            tid = str(res["timer_id"])

            await _REST_ENGINE.execute_device_action("bedroom_light", "turn_off", source="test_reset", bypass_rbac=True)
            assert len(list_pending_timers()) == 1

            eng2 = SmartHomeEngine()
            restore_stats = await eng2.restore_timers_from_sqlite()
            assert restore_stats["restored"] >= 1
            assert tid in eng2.active_timers

            for _ in range(25):
                if eng2.devices["bedroom_light"]["state"] == "ON":
                    break
                await asyncio.sleep(0.1)
            assert eng2.devices["bedroom_light"]["state"] == "ON"
            for t in list(eng2._timer_tasks.values()):
                t.cancel()

        asyncio.run(_run())
