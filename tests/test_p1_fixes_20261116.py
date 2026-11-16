"""Regression suite for P1 bug fixes F01..F06 (2026-11-16)."""

from __future__ import annotations

import pathlib
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from simulator.api.deps import _BOOT_VOICE_AUTH, _REST_ENGINE
from simulator.automation_repo import (
    can_user_create_links,
    list_automation_rules,
    list_custom_commands,
    list_pending_timers,
    list_schedules,
    reset_custom_commands_scoped,
    reset_links_scoped,
    reset_timers_and_schedules_scoped,
    set_user_can_create_links,
)
from simulator.db_migrations import open_wal_connection, resolve_sqlite_db_path
from simulator.server import app

H_TIER1 = {"X-Session-Token": "sess_owner_t1_nep94121"}
H_TIER2 = {"X-Session-Token": "sess_family_t2_member_a"}
H_TIER3 = {"X-Session-Token": "sess_guest_t3_visitor_c"}


def _reset_automation_db() -> None:
    reset_custom_commands_scoped(clear_all=True)
    reset_links_scoped(clear_all=True)
    reset_timers_and_schedules_scoped(clear_all=True)
    set_user_can_create_links("thanh_vien_a", False, owner_tier=2, display_name="Thành viên A")
    conn = open_wal_connection(resolve_sqlite_db_path(), readonly=False)
    try:
        conn.execute("DELETE FROM pending_confirmations")
        conn.commit()
    finally:
        conn.close()
    _REST_ENGINE.sync_automation_pools_from_sqlite(emit_snapshot=False)
    for tid in list(_REST_ENGINE.active_timers.keys()):
        task = _REST_ENGINE._timer_tasks.pop(tid, None)
        if task is not None:
            task.cancel()
        _REST_ENGINE.active_timers.pop(tid, None)


def _pending_count() -> int:
    conn = open_wal_connection(resolve_sqlite_db_path(), readonly=True)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM pending_confirmations").fetchone()[0])
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def _isolate_p1_state(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("SIMULATOR_OFFLINE_SANDBOX", "1")
    _BOOT_VOICE_AUTH.reset_strikes()
    _reset_automation_db()
    yield
    _reset_automation_db()


class TestF01RestFourStepConfirmation:
    """F01: REST & text/Live automation mutations require server-issued single-use confirmation."""

    @pytest.mark.parametrize(
        ("method", "url", "body", "headers", "kind", "check_zero_fn"),
        [
            (
                "POST",
                "/api/timers",
                {"device_id": "fan", "action": "turn_on", "seconds": 30, "confirmed": True},
                H_TIER1,
                "create_timer",
                lambda: len(list_pending_timers()),
            ),
            (
                "POST",
                "/api/mobile/schedule",
                {"device_id": "living_room_light", "action": "turn_on", "seconds": 25, "confirmed": True},
                H_TIER1,
                "create_timer",
                lambda: len(list_pending_timers()),
            ),
            (
                "POST",
                "/api/schedules",
                {"device_id": "fan", "action": "turn_on", "time_hhmm": "21:15", "schedule_type": "daily", "confirmed": True},
                H_TIER1,
                "create_schedule",
                lambda: len(list_schedules(include_disabled=True)),
            ),
            (
                "POST",
                "/api/scenes",
                {"phrase": "nghỉ trưa f01", "steps": [{"device_id": "fan", "action": "turn_on"}], "confirmed": True},
                H_TIER2,
                "create_custom_command",
                lambda: len(list_custom_commands(include_disabled=True)),
            ),
            (
                "POST",
                "/api/members/thanh_vien_a/link_permission",
                {"allowed": True, "confirmed": True},
                H_TIER1,
                "set_member_link_permission",
                lambda: 1 if can_user_create_links("thanh_vien_a", 2) else 0,
            ),
        ],
    )
    def test_step1_never_mutates_even_with_forged_confirmed_true(
        self,
        method: str,
        url: str,
        body: dict[str, Any],
        headers: dict[str, str],
        kind: str,
        check_zero_fn: Any,
    ) -> None:
        with TestClient(app) as client:
            r = client.request(method, url, headers=headers, json=body)
            assert r.status_code == 200
            data = r.json()
            assert data.get("ok") is True
            assert data.get("confirmed") is False
            assert data.get("requires_confirmation") is True
            assert data.get("action_kind") == kind
            assert data.get("pending_id") and data.get("confirm_token") == data.get("pending_id")
            assert check_zero_fn() == 0
            assert _pending_count() >= 1

    def test_full_crud_confirm_replay_cross_owner_expiry_cancel(self) -> None:
        with TestClient(app) as client:
            # 1. Grant link permission via Step 1 + /api/confirmations/{id}
            g1 = client.post("/api/members/thanh_vien_a/link_permission", headers=H_TIER1, json={"allowed": True})
            assert g1.status_code == 200 and g1.json()["requires_confirmation"] is True
            g_pid = g1.json()["pending_id"]
            assert can_user_create_links("thanh_vien_a", 2) is False

            # Wrong owner cannot confirm Tier 1's pending token
            g_wrong = client.post(f"/api/confirmations/{g_pid}", headers=H_TIER2, json={"confirmed": True})
            assert g_wrong.status_code == 403
            assert can_user_create_links("thanh_vien_a", 2) is False

            # Owner confirms -> succeeds, replay -> 400
            g2 = client.post(f"/api/confirmations/{g_pid}", headers=H_TIER1, json={"confirmed": True})
            assert g2.status_code == 200 and g2.json().get("confirmed") is True
            assert can_user_create_links("thanh_vien_a", 2) is True
            g_replay = client.post(f"/api/confirmations/{g_pid}", headers=H_TIER1, json={"confirmed": True})
            assert g_replay.status_code == 400

            # 2. Tier 2 rule creation Step 1 + Step 2 + Step 1 delete + Step 2 delete
            r1 = client.post(
                "/api/rules",
                headers=H_TIER2,
                json={"when_device_id": "living_room_light", "when_state": "ON", "then_device_id": "fan", "then_action": "turn_on"},
            )
            assert r1.status_code == 200 and r1.json()["requires_confirmation"] is True
            assert len(list_automation_rules(owner_user_id="thanh_vien_a")) == 0

            # Token kind mismatch against /api/scenes must fail 400 and leave token unconsumed or rejected
            mismatch = client.post(
                "/api/scenes",
                headers=H_TIER2,
                json={"phrase": "hack", "steps": [{"device_id": "fan", "action": "turn_on"}], "confirm_token": r1.json()["pending_id"]},
            )
            assert mismatch.status_code == 400

            r2 = client.post("/api/automation/confirm", headers=H_TIER2, json={"pending_id": r1.json()["pending_id"], "confirmed": True})
            assert r2.status_code == 200
            rid = r2.json()["rule"]["rule_id"]
            assert len(list_automation_rules(owner_user_id="thanh_vien_a")) == 1

            # Delete rule requires Step 1 + Step 2; cancel leaves rule intact
            dr1 = client.delete(f"/api/rules/{rid}", headers=H_TIER2)
            assert dr1.status_code == 200 and dr1.json()["requires_confirmation"] is True
            assert len(list_automation_rules(owner_user_id="thanh_vien_a")) == 1
            dr_cancel = client.post("/api/automation/confirm", headers=H_TIER2, json={"pending_id": dr1.json()["pending_id"], "confirmed": False})
            assert dr_cancel.status_code == 200 and dr_cancel.json()["cancelled"] is True
            assert len(list_automation_rules(owner_user_id="thanh_vien_a")) == 1

            dr2 = client.delete(f"/api/rules/{rid}", headers=H_TIER2)
            dr2_c = client.post("/api/automation/confirm", headers=H_TIER2, json={"pending_id": dr2.json()["pending_id"], "confirmed": True})
            assert dr2_c.status_code == 200 and len(list_automation_rules(owner_user_id="thanh_vien_a")) == 0

            # 3. Timer create -> PATCH -> DELETE with 4-step confirmation + expiry 409 check
            t1 = client.post("/api/timers", headers=H_TIER2, json={"device_id": "fan", "action": "turn_on", "seconds": 40})
            t1_pid = t1.json()["pending_id"]
            assert len(list_pending_timers()) == 0
            t2 = client.post("/api/automation/confirm", headers=H_TIER2, json={"pending_id": t1_pid, "confirmed": True})
            assert t2.status_code == 200
            tid = t2.json()["timer_id"]
            assert len(list_pending_timers()) == 1

            tp1 = client.patch(f"/api/timers/{tid}", headers=H_TIER2, json={"seconds": 55, "action": "turn_off"})
            assert tp1.status_code == 200 and tp1.json()["requires_confirmation"] is True
            # Force-expire tp1
            conn = open_wal_connection(resolve_sqlite_db_path(), readonly=False)
            try:
                conn.execute("UPDATE pending_confirmations SET expires_at = ? WHERE pending_id = ?", (time.time() - 5.0, tp1.json()["pending_id"]))
                conn.commit()
            finally:
                conn.close()
            tp_exp = client.post("/api/automation/confirm", headers=H_TIER2, json={"pending_id": tp1.json()["pending_id"], "confirmed": True})
            assert tp_exp.status_code == 409 and tp_exp.json().get("expired") is True

            # Re-stage and confirm PATCH timer
            tp2 = client.patch(f"/api/timers/{tid}", headers=H_TIER2, json={"seconds": 55, "action": "turn_off"})
            tp2_c = client.post("/api/automation/confirm", headers=H_TIER2, json={"pending_id": tp2.json()["pending_id"], "confirmed": True})
            assert tp2_c.status_code == 200
            new_tid = tp2_c.json()["timer_id"]

            # Delete timer via Step 1 + Step 2
            td1 = client.delete(f"/api/timers/{new_tid}", headers=H_TIER2)
            assert td1.status_code == 200 and td1.json()["requires_confirmation"] is True
            assert len(list_pending_timers()) == 1
            td2 = client.post("/api/automation/confirm", headers=H_TIER2, json={"pending_id": td1.json()["pending_id"], "confirmed": True})
            assert td2.status_code == 200 and len(list_pending_timers()) == 0

            # 4. Schedule + Scene update/delete via confirm_token inline on endpoint
            s1 = client.post("/api/scenes", headers=H_TIER1, json={"phrase": "ban đêm f01", "steps_text": "tắt đèn phòng khách"})
            s2 = client.post(
                "/api/scenes",
                headers=H_TIER1,
                json={"phrase": "ban đêm f01", "steps_text": "tắt đèn phòng khách", "confirm_token": s1.json()["pending_id"]},
            )
            assert s2.status_code == 200 and s2.json().get("confirmed") is True
            cid = s2.json()["command"]["command_id"]

            su1 = client.put(f"/api/scenes/{cid}", headers=H_TIER1, json={"phrase": "ban đêm mới", "steps_text": "bật quạt trần"})
            assert su1.status_code == 200 and su1.json()["requires_confirmation"] is True
            assert list_custom_commands(include_disabled=True)[0]["phrase"] == "ban đêm f01"
            su2 = client.post("/api/automation/confirm", headers=H_TIER1, json={"pending_id": su1.json()["pending_id"], "confirmed": True})
            assert su2.status_code == 200 and list_custom_commands(include_disabled=True)[0]["phrase"] == "ban đêm mới"


class TestF02WsAndSsePoolIsolation:
    """F02: Private WS events and WS/SSE snapshots are isolated by session validity, tier, and owner."""

    def test_ws_emit_and_broadcast_isolation_and_revocation(self) -> None:
        import asyncio
        import json as _json
        from simulator.api import deps
        from simulator.auth.session_store import UserSession
        from simulator.auth.tier_permissions import restrict_guest_snapshot
        from simulator.live.gemini_bridge import LiveBridgeSession
        from simulator.realtime_hub import RealtimePushHub

        class _Sink:
            def __init__(self) -> None:
                self.frames: list[dict[str, Any]] = []

            async def send_text(self, raw: str) -> None:
                self.frames.append(_json.loads(raw))

        def _make_bridge(sess: UserSession | None) -> tuple[LiveBridgeSession, _Sink]:
            sink = _Sink()
            br = LiveBridgeSession.__new__(LiveBridgeSession)
            br.ws = sink
            br._closed = False
            br._cached_ws_actor = sess
            br._is_cached_actor_fresh = lambda *a: True
            br.engine = _REST_ENGINE
            return br, sink

        now_ts = time.time()
        s1 = UserSession(session_id="f02_t1", user_id="tuan_anh", email="", tier=1, role="ADMIN", display_name="Owner", created_at=now_ts, expires_at=now_ts + 600, source="seed")
        s2a = UserSession(session_id="f02_t2a", user_id="thanh_vien_a", email="", tier=2, role="MEMBER", display_name="Member A", created_at=now_ts, expires_at=now_ts + 600, source="seed")
        s2b = UserSession(session_id="f02_t2b", user_id="thanh_vien_b", email="", tier=2, role="MEMBER", display_name="Member B", created_at=now_ts, expires_at=now_ts + 600, source="seed")
        s3 = UserSession(session_id="f02_t3", user_id="khach_c", email="", tier=3, role="CHILD_GUEST", display_name="Guest C", created_at=now_ts, expires_at=now_ts + 600, source="seed")

        br1, sink1 = _make_bridge(s1)
        br2a, sink2a = _make_bridge(s2a)
        br2b, sink2b = _make_bridge(s2b)
        br3, sink3 = _make_bridge(s3)
        br_none, sink_none = _make_bridge(None)

        full_snap = _REST_ENGINE.get_snapshot(sync=False)
        restricted_none = restrict_guest_snapshot(full_snap, None)
        assert restricted_none.get("public_only") is True
        assert restricted_none.get("current_tier") == 99
        assert "custom_commands" not in restricted_none and "users" not in restricted_none

        deps._ACTIVE_BRIDGES.extend([br1, br2a, br2b, br3, br_none])
        try:
            async def _exercise() -> None:
                await deps._emit_to_all_active_bridges({
                    "type": "custom_command_created",
                    "command": {"owner_user_id": "tuan_anh", "phrase": "bí mật C1", "steps": [{"device_id": "main_door", "action": "open"}]},
                })
                await deps._emit_to_all_active_bridges({
                    "type": "custom_command_created",
                    "command": {"owner_user_id": "thanh_vien_a", "phrase": "lệnh riêng A", "steps": [{"device_id": "fan", "action": "turn_on"}]},
                })
                await deps._emit_to_all_active_bridges({
                    "type": "member_permission_updated",
                    "member": {"user_id": "thanh_vien_a", "can_create_links": True},
                })
                await deps._emit_to_all_active_bridges({
                    "type": "device_updated",
                    "device_id": "main_door",
                    "new_state": "OPEN",
                    "source": "Owner Voice",
                })
                await deps.broadcast_rest_state_to_bridges()

                # Revoke s2a via expiry and emit another private event for s2a: revoked bridge must drop it
                s2a.expires_at = time.time() - 10.0
                await deps._emit_to_all_active_bridges({
                    "type": "schedule_created",
                    "schedules": [{"schedule_id": "sc_revoked", "owner_user_id": "thanh_vien_a", "device_id": "fan", "action": "turn_on", "time_hhmm": "20:00"}],
                })

            asyncio.run(_exercise())
        finally:
            for b in (br1, br2a, br2b, br3, br_none):
                if b in deps._ACTIVE_BRIDGES:
                    deps._ACTIVE_BRIDGES.remove(b)

        t1_types = [f.get("type") for f in sink1.frames]
        assert "custom_command_created" in t1_types and "member_permission_updated" in t1_types

        t2a_cmds = [f["command"]["phrase"] for f in sink2a.frames if f.get("type") == "custom_command_created"]
        assert t2a_cmds == ["lệnh riêng A"]
        assert all(f.get("type") != "member_permission_updated" for f in sink2a.frames)
        assert all(f.get("device_id") != "main_door" for f in sink2a.frames if f.get("type") == "device_updated")
        # Revoked s2a did not receive subsequent schedule_created
        assert all(f.get("type") != "schedule_created" for f in sink2a.frames)

        # Tier 2B saw neither T1 nor T2A private events
        assert all(f.get("type") == "state_snapshot" for f in sink2b.frames)
        # Tier 3 saw zero private automation/door events
        assert all(f.get("type") == "state_snapshot" for f in sink3.frames)
        t3_snap = sink3.frames[-1]["snapshot"]
        assert t3_snap["custom_commands"] == [] and t3_snap["schedules"] == [] and t3_snap["timers"] == []
        assert all(f.get("type") == "state_snapshot" for f in sink_none.frames)
        assert sink_none.frames[-1]["snapshot"].get("public_only") is True

        # SSE hub re-checks session_is_current on every publish_snapshot
        hub = RealtimePushHub()
        s_sse = UserSession(session_id="f02_sse", user_id="tuan_anh", email="", tier=1, role="ADMIN", display_name="Owner", created_at=now_ts, expires_at=now_ts + 600, source="seed")

        async def _sse_check() -> tuple[dict[str, Any], dict[str, Any]]:
            sub = hub.register(s_sse)
            hub.publish_snapshot(_REST_ENGINE, reason="valid")
            raw1 = await sub.queue.get()
            s_sse.expires_at = time.time() - 5.0
            hub.publish_snapshot(_REST_ENGINE, reason="revoked")
            raw2 = await sub.queue.get()
            hub.unregister(sub.sub_id)
            ev1 = _json.loads(raw1.split("data: ", 1)[1].strip())["snapshot"]
            ev2 = _json.loads(raw2.split("data: ", 1)[1].strip())["snapshot"]
            return ev1, ev2

        snap_valid, snap_revoked = asyncio.run(_sse_check())
        assert snap_valid.get("current_tier") == 1 and snap_valid.get("public_only") is False
        assert snap_revoked.get("public_only") is True and "custom_commands" not in snap_revoked


class TestF03AtomicQrAndOtpMultiprocess:
    """F03: Single-use QR invite and OTP consume remain strictly single-winner across processes."""

    def test_concurrent_child_processes_qr_and_otp_single_winner(self, tmp_path: pathlib.Path) -> None:
        import concurrent.futures
        import os
        import secrets
        import subprocess
        import sys
        from simulator.auth.guest_invites import create_invite
        from simulator.auth.owner_pin import issue_reset_otp, reset_pin_with_otp
        from simulator.auth.session_store import get_session_store
        from simulator.auth_3layer import ThreeLayerAuthManager

        repo_root = pathlib.Path(__file__).resolve().parent.parent
        data_dir = tmp_path / "f03_mp_data"
        data_dir.mkdir(parents=True, exist_ok=True)
        prev_env = {k: os.environ.get(k) for k in ("SMARTHOME_DATA_DIR", "SMARTHOME_SECURITY_BACKEND", "SMARTHOME_SESSION_SECRET")}
        env = dict(
            os.environ,
            SMARTHOME_DATA_DIR=str(data_dir),
            SMARTHOME_SECURITY_BACKEND="sqlite",
            SIMULATOR_OFFLINE_SANDBOX="1",
            SMARTHOME_SESSION_SECRET="f03_test_secret_" + secrets.token_hex(16),
            PYTHONPATH=str(repo_root),
            PYTHONIOENCODING="utf-8",
        )
        os.environ["SMARTHOME_DATA_DIR"] = env["SMARTHOME_DATA_DIR"]
        os.environ["SMARTHOME_SECURITY_BACKEND"] = "sqlite"
        os.environ["SMARTHOME_SESSION_SECRET"] = env["SMARTHOME_SESSION_SECRET"]
        store = get_session_store()
        prev_store_path = store.db_path
        store.db_path = data_dir / "smarthome.db"
        try:
            # 1. Single-use QR invite across 2 child processes
            invite = create_invite(owner_user_id="tuan_anh", tier=3, duration_code="1d")
            qr_script = (
                "import os, sys; "
                "from simulator.auth.guest_invites import redeem_token; "
                "r = redeem_token(sys.argv[1]); "
                "print('OK' if r.get('ok') else r.get('reason', 'FAIL'))"
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                qr_outs = list(
                    pool.map(
                        lambda _: subprocess.run(
                            [sys.executable, "-c", qr_script, invite["token"]],
                            text=True,
                            capture_output=True,
                            env=env,
                            cwd=str(repo_root),
                            timeout=30,
                        ).stdout.strip(),
                        range(2),
                    )
                )
            assert qr_outs.count("OK") == 1
            assert qr_outs.count("used") == 1

            # 2. Layer-2 OTP verify across 2 child processes
            mgr = ThreeLayerAuthManager()
            acc = next(a for a in mgr.accounts if int(a.get("tier", 3)) == 1)
            email = str(acc["email"])
            code_l2 = f"{100000 + secrets.randbelow(900000)}"
            salt_l2, dig_l2 = mgr._hash_otp_code(code_l2)
            pending_l2 = {
                "email": email,
                "display_name": acc["display_name"],
                "account_id": acc["account_id"],
                "tier": 1,
                "purpose": "layer2_login",
                "otp_salt": salt_l2,
                "otp_hash": dig_l2,
                "created_at": time.time(),
                "expires_at": time.time() + 300,
                "consumed": False,
            }
            acc["pending_otp"] = pending_l2
            mgr.pending_otps[email] = pending_l2
            assert mgr._save_accounts() is True

            otp_script = (
                "import sys; "
                "from simulator.auth_3layer import ThreeLayerAuthManager; "
                "r = ThreeLayerAuthManager().layer2_verify_otp(sys.argv[1], sys.argv[2], expected_purpose='layer2_login'); "
                "print('OK' if r.get('ok') else 'REJECT')"
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                otp_outs = list(
                    pool.map(
                        lambda _: subprocess.run(
                            [sys.executable, "-c", otp_script, email, code_l2],
                            text=True,
                            capture_output=True,
                            env=env,
                            cwd=str(repo_root),
                            timeout=30,
                        ).stdout.strip(),
                        range(2),
                    )
                )
            assert otp_outs.count("OK") == 1
            assert otp_outs.count("REJECT") == 1

            # 3. forgot_password_reset consumes OTP atomically across 2 child processes
            code_fp = f"{100000 + secrets.randbelow(900000)}"
            salt_fp, dig_fp = mgr._hash_otp_code(code_fp)
            pending_fp = {
                "email": email,
                "display_name": acc["display_name"],
                "account_id": acc["account_id"],
                "tier": 1,
                "purpose": "forgot_password",
                "otp_salt": salt_fp,
                "otp_hash": dig_fp,
                "created_at": time.time(),
                "expires_at": time.time() + 300,
                "consumed": False,
            }
            acc["pending_otp"] = pending_fp
            mgr.pending_otps[email] = pending_fp
            assert mgr._save_accounts() is True

            fp_script = (
                "import sys; "
                "from simulator.auth_3layer import ThreeLayerAuthManager; "
                "r = ThreeLayerAuthManager().reset_password_with_otp(email=sys.argv[1], otp_code=sys.argv[2], new_password='NewStrong#Pass2026', confirm_password='NewStrong#Pass2026'); "
                "print('OK' if r.get('ok') else 'REJECT')"
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                fp_procs = list(
                    pool.map(
                        lambda _: subprocess.run(
                            [sys.executable, "-c", fp_script, email, code_fp],
                            text=True,
                            capture_output=True,
                            env=env,
                            cwd=str(repo_root),
                            timeout=30,
                        ),
                        range(2),
                    )
                )
            for p in fp_procs:
                assert p.returncode == 0, p.stderr
            fp_outs = [p.stdout.strip() for p in fp_procs]
            assert fp_outs.count("OK") == 1
            assert fp_outs.count("REJECT") == 1

            # 4. Owner PIN reset OTP across 2 child processes
            issued_meta, pin_otp = issue_reset_otp()
            assert issued_meta.get("ok") is True and len(pin_otp) == 6
            pin_script = (
                "import sys; "
                "from simulator.auth.owner_pin import reset_pin_with_otp; "
                "r = reset_pin_with_otp(sys.argv[1], '4829', '4829'); "
                "print('OK' if r.get('ok') else 'REJECT')"
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                pin_procs = list(
                    pool.map(
                        lambda _: subprocess.run(
                            [sys.executable, "-c", pin_script, pin_otp],
                            text=True,
                            capture_output=True,
                            env=env,
                            cwd=str(repo_root),
                            timeout=30,
                        ),
                        range(2),
                    )
                )
            for p in pin_procs:
                assert p.returncode == 0, p.stderr
            pin_outs = [p.stdout.strip() for p in pin_procs]
            assert pin_outs.count("OK") == 1
            assert pin_outs.count("REJECT") == 1
        finally:
            store.db_path = prev_store_path
            for k, old_v in prev_env.items():
                if old_v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = old_v


class TestF04PatchScheduleAndTimerTier1Conflict:
    """F04: PATCH/PUT schedule & update_timer enforce Tier 1 +-60s conflict on computed target state."""

    def test_patch_once_schedule_recomputed_date_conflict_returns_409(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import datetime
        from simulator import automation_repo as repo

        fixed_now = datetime.datetime(2026, 11, 16, 12, 0, tzinfo=repo.SAIGON_TZ)
        monkeypatch.setattr(repo, "now_saigon", lambda: fixed_now)

        with TestClient(app) as client:
            # Tier 1 creates 14:00 today (2026-11-16)
            o1 = client.post("/api/schedules", headers=H_TIER1, json={"device_id": "fan", "action": "turn_on", "time_hhmm": "14:00", "schedule_type": "once"})
            assert o1.status_code == 200
            oc = client.post("/api/automation/confirm", headers=H_TIER1, json={"pending_id": o1.json()["pending_id"], "confirmed": True})
            assert oc.status_code == 200 and oc.json()["schedule"]["run_date_vn"] == "2026-11-16"

            # Tier 2 creates 10:00 (tomorrow 2026-11-17) -> succeeds
            f1 = client.post("/api/schedules", headers=H_TIER2, json={"device_id": "bedroom_light", "action": "turn_on", "time_hhmm": "10:00", "schedule_type": "once"})
            fc = client.post("/api/automation/confirm", headers=H_TIER2, json={"pending_id": f1.json()["pending_id"], "confirmed": True})
            assert fc.status_code == 200 and fc.json()["schedule"]["run_date_vn"] == "2026-11-17"
            sid = fc.json()["schedule"]["schedule_id"]

            # PATCH time_hhmm -> 14:00 recomputes run_date_vn=2026-11-16 -> MUST reject 409 and preserve 10:00 on 2026-11-17
            upd = client.patch(f"/api/schedules/{sid}", headers=H_TIER2, json={"time_hhmm": "14:00"})
            assert upd.status_code == 409
            assert upd.json().get("conflict_tier1") is True

            # PATCH explicit run_date_vn onto Tier 1's slot + enabled=True transition -> 409
            o2 = client.post("/api/schedules", headers=H_TIER1, json={"device_id": "fan", "action": "turn_off", "time_hhmm": "18:00", "schedule_type": "once"})
            client.post("/api/automation/confirm", headers=H_TIER1, json={"pending_id": o2.json()["pending_id"], "confirmed": True})
            f2 = client.post("/api/schedules", headers=H_TIER2, json={"device_id": "bedroom_light", "action": "turn_off", "time_hhmm": "18:00", "schedule_type": "once", "run_date_vn": "2026-11-18"})
            f2c = client.post("/api/automation/confirm", headers=H_TIER2, json={"pending_id": f2.json()["pending_id"], "confirmed": True})
            assert f2c.status_code == 200
            sid2 = f2c.json()["schedule"]["schedule_id"]

            # Disable first, then try enabling onto 2026-11-16
            dis1 = client.patch(f"/api/schedules/{sid2}", headers=H_TIER2, json={"enabled": False})
            client.post("/api/automation/confirm", headers=H_TIER2, json={"pending_id": dis1.json()["pending_id"], "confirmed": True})
            en_conf = client.patch(f"/api/schedules/{sid2}", headers=H_TIER2, json={"enabled": True, "run_date_vn": "2026-11-16"})
            assert en_conf.status_code == 409

            # TOCTOU: if Tier 1 creates 2026-11-17 09:00 AFTER Tier 2 staged a PATCH for 09:00, confirm Step 2 must still return 409!
            st_p = client.patch(f"/api/schedules/{sid}", headers=H_TIER2, json={"time_hhmm": "09:00", "run_date_vn": "2026-11-17"})
            assert st_p.status_code == 200 and st_p.json()["requires_confirmation"] is True
            repo.create_schedule(owner_user_id="tuan_anh", owner_tier=1, device_id="fan", action="turn_on", time_hhmm="09:00", schedule_type="once", run_date_vn="2026-11-17")
            st_c = client.post("/api/automation/confirm", headers=H_TIER2, json={"pending_id": st_p.json()["pending_id"], "confirmed": True})
            assert st_c.status_code == 409 and st_c.json().get("conflict_tier1") is True

            # Verify Tier 2's first schedule remained untouched at 10:00 / 2026-11-17
            saved = next(s for s in list_schedules(include_disabled=True) if s["schedule_id"] == sid)
            assert saved["time_hhmm"] == "10:00" and saved["run_date_vn"] == "2026-11-17"

    def test_update_or_cancel_timer_conflict_preserves_existing_timer(self) -> None:
        import asyncio
        from simulator.automation_repo import ScheduleConflictError

        async def _check() -> None:
            _REST_ENGINE.set_active_user("tuan_anh")
            t1 = await _REST_ENGINE.schedule_timer_flexible("fan", "turn_on", seconds=120)
            assert t1["ok"] is True
            _REST_ENGINE.set_active_user("thanh_vien_a")
            t2 = await _REST_ENGINE.schedule_timer_flexible("bedroom_light", "turn_on", seconds=360)
            assert t2["ok"] is True
            t2_id = t2["timer_id"]

            mod = await _REST_ENGINE.update_or_cancel_timer(
                device_id="bedroom_light",
                operation="modify",
                seconds=120,
            )
            assert mod["ok"] is False and mod.get("conflict_tier1") is True
            assert t2_id in _REST_ENGINE.active_timers
            assert any(r["timer_id"] == t2_id for r in list_pending_timers())

        asyncio.run(_check())
        assert issubclass(ScheduleConflictError, ValueError)


