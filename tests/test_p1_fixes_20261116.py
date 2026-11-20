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
    _REST_ENGINE.server_connected = True
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
                {"device_id": "speaker_amp", "action": "turn_on", "seconds": 30, "confirmed": True},
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
                {"device_id": "speaker_amp", "action": "turn_on", "time_hhmm": "21:15", "schedule_type": "daily", "confirmed": True},
                H_TIER1,
                "create_schedule",
                lambda: len(list_schedules(include_disabled=True)),
            ),
            (
                "POST",
                "/api/scenes",
                {"phrase": "nghỉ trưa f01", "steps": [{"device_id": "speaker_amp", "action": "turn_on"}], "confirmed": True},
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
                json={"when_device_id": "living_room_light", "when_state": "ON", "then_device_id": "speaker_amp", "then_action": "turn_on"},
            )
            assert r1.status_code == 200 and r1.json()["requires_confirmation"] is True
            assert len(list_automation_rules(owner_user_id="thanh_vien_a")) == 0

            # Token kind mismatch against /api/scenes must fail 400 and leave token unconsumed or rejected
            mismatch = client.post(
                "/api/scenes",
                headers=H_TIER2,
                json={"phrase": "hack", "steps": [{"device_id": "speaker_amp", "action": "turn_on"}], "confirm_token": r1.json()["pending_id"]},
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
            t1 = client.post("/api/timers", headers=H_TIER2, json={"device_id": "speaker_amp", "action": "turn_on", "seconds": 40})
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

            su1 = client.put(f"/api/scenes/{cid}", headers=H_TIER1, json={"phrase": "ban đêm mới", "steps_text": "bật đèn phòng ngủ"})
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
                    "command": {"owner_user_id": "thanh_vien_a", "phrase": "lệnh riêng A", "steps": [{"device_id": "speaker_amp", "action": "turn_on"}]},
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
                    "schedules": [{"schedule_id": "sc_revoked", "owner_user_id": "thanh_vien_a", "device_id": "speaker_amp", "action": "turn_on", "time_hhmm": "20:00"}],
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

    def test_scene_executed_owner_scope_executor_separation_and_deny_by_default(self) -> None:
        import json as _json
        from simulator import automation_repo as repo
        from simulator.api import deps
        from simulator.auth.session_store import get_session_store
        from simulator.auth.tier_permissions import filter_ws_event_for_session
        from simulator.live.gemini_bridge import LiveBridgeSession
        from simulator.realtime_hub import RealtimePushHub

        class _Sink:
            def __init__(self) -> None:
                self.frames: list[dict[str, Any]] = []

            async def send_text(self, raw: str) -> None:
                self.frames.append(_json.loads(raw))

        def _make_bridge(sess: Any) -> tuple[LiveBridgeSession, _Sink]:
            sink = _Sink()
            br = LiveBridgeSession.__new__(LiveBridgeSession)
            br.ws = sink
            br._closed = False
            br._cached_ws_actor = sess
            br._is_cached_actor_fresh = lambda *a: True
            br.engine = _REST_ENGINE
            return br, sink

        store = get_session_store()
        s1 = store.create_session(user_id="tuan_anh", tier=1, role="ADMIN", display_name="Owner")
        s2a = store.create_session(user_id="thanh_vien_a", tier=2, role="MEMBER", display_name="Member A")
        s2b = store.create_session(user_id="thanh_vien_b", tier=2, role="MEMBER", display_name="Member B")
        s3 = store.create_session(user_id="khach_c", tier=3, role="CHILD_GUEST", display_name="Guest C")

        br1, sink1 = _make_bridge(s1)
        br2a, sink2a = _make_bridge(s2a)
        br2b, sink2b = _make_bridge(s2b)
        br3, sink3 = _make_bridge(s3)
        br_none, sink_none = _make_bridge(None)

        owner_scene = repo.upsert_custom_command(
            phrase="bí mật chủ nhà f02",
            steps=[{"device_id": "speaker_amp", "action": "turn_on"}],
            owner_user_id="tuan_anh",
            owner_tier=1,
        )
        member_a_scene = repo.upsert_custom_command(
            phrase="ngữ cảnh riêng của A",
            steps=[{"device_id": "speaker_amp", "action": "turn_off"}],
            owner_user_id="thanh_vien_a",
            owner_tier=2,
        )

        deps._ACTIVE_BRIDGES.extend([br1, br2a, br2b, br3, br_none])
        try:
            with TestClient(app) as client:
                client.post("/api/device", headers=H_TIER1, json={"device_id": "speaker_amp", "action": "turn_off"})
                for sk in (sink1, sink2a, sink2b, sink3, sink_none):
                    sk.frames.clear()

                # 1. Owner executes Owner's private scene -> Tier 2A/2B/3 and unauth never receive scene_executed or phrase in device_updated.source
                r_own = client.post(
                    f"/api/scenes/{owner_scene['command_id']}/run",
                    headers={"X-Session-Token": s1.session_id},
                )
                assert r_own.status_code == 200 and r_own.json().get("ok") is True

                assert any(f.get("type") == "scene_executed" and f.get("phrase") == "bí mật chủ nhà f02" for f in sink1.frames)
                for sk in (sink2a, sink2b, sink3, sink_none):
                    assert all(f.get("type") != "scene_executed" for f in sk.frames)
                    assert all("bí mật chủ nhà f02" not in _json.dumps(f, ensure_ascii=False) for f in sk.frames)

                for sk in (sink1, sink2a, sink2b, sink3, sink_none):
                    sk.frames.clear()

                # 2. Owner executes Member A's scene -> Tier 1 and owner Member A receive scene_executed, Member B / Tier 3 / unauth do not
                r_m = client.post(
                    f"/api/scenes/{member_a_scene['command_id']}/run",
                    headers={"X-Session-Token": s1.session_id},
                )
                assert r_m.status_code == 200 and r_m.json().get("ok") is True

                assert any(f.get("type") == "scene_executed" and f.get("command_id") == member_a_scene["command_id"] for f in sink1.frames)
                m_a_events = [f for f in sink2a.frames if f.get("type") == "scene_executed"]
                assert len(m_a_events) == 1
                assert m_a_events[0].get("owner_user_id") == "thanh_vien_a"
                assert m_a_events[0].get("actor_user_id") == "tuan_anh"
                for sk in (sink2b, sink3, sink_none):
                    assert all(f.get("type") != "scene_executed" for f in sk.frames)
                    assert all("ngữ cảnh riêng của A" not in _json.dumps(f, ensure_ascii=False) for f in sk.frames)
        finally:
            for b in (br1, br2a, br2b, br3, br_none):
                if b in deps._ACTIVE_BRIDGES:
                    deps._ACTIVE_BRIDGES.remove(b)

        # 3. Direct filter_ws_event_for_session checks: schedule_fired, missing owner on scene_executed, forbidden step device, and deny-by-default
        sc_t1 = {"type": "schedule_fired", "schedule": {"schedule_id": "sc1", "owner_user_id": "tuan_anh", "device_id": "speaker_amp", "action": "turn_on"}}
        sc_t2a = {"type": "schedule_fired", "schedule": {"schedule_id": "sc2", "owner_user_id": "thanh_vien_a", "device_id": "speaker_amp", "action": "turn_on"}}
        assert filter_ws_event_for_session(sc_t1, s1, broadcast=True) is not None
        assert filter_ws_event_for_session(sc_t1, s2a, broadcast=True) is None
        assert filter_ws_event_for_session(sc_t1, s3, broadcast=True) is None
        assert filter_ws_event_for_session(sc_t2a, s2a, broadcast=True) is not None
        assert filter_ws_event_for_session(sc_t2a, s2b, broadcast=True) is None
        assert filter_ws_event_for_session(sc_t2a, s3, broadcast=True) is None

        # scene_executed without owner_user_id (only executor user_id) must never leak to Tier 2A
        no_owner_scene_ev = {"type": "scene_executed", "phrase": "x", "steps": [{"device_id": "speaker_amp", "action": "turn_on"}], "user_id": "thanh_vien_a"}
        assert filter_ws_event_for_session(no_owner_scene_ev, s2a, broadcast=True) is None

        # scene_executed owned by Tier 2A but referencing main_door must be blocked for Tier 2A
        door_scene_ev = {"type": "scene_executed", "owner_user_id": "thanh_vien_a", "phrase": "cửa", "steps": [{"device_id": "main_door", "action": "open"}]}
        assert filter_ws_event_for_session(door_scene_ev, s2a, broadcast=True) is None

        # Unclassified event containing pool payload is denied by default for Tier 2, Tier 3, and unauth
        unclassified = {"type": "unclassified_pool_leak", "phrase": "bí mật", "steps": [{"device_id": "speaker_amp", "action": "turn_on"}]}
        for sess_chk in (s2a, s3, None):
            assert filter_ws_event_for_session(unclassified, sess_chk, broadcast=True) is None
            assert filter_ws_event_for_session(unclassified, sess_chk, broadcast=False) is None

        # Direct-session-only event must never pass broadcast=True
        assert filter_ws_event_for_session({"type": "rbac_blocked", "action": "x"}, s1, broadcast=True) is None

        # SSE hub must not leak private reason string to Tier 2/3/unauth
        import asyncio as _asyncio

        hub = RealtimePushHub()

        async def _check_sse_reasons() -> dict[int, str]:
            sub1 = hub.register(s1)
            sub2 = hub.register(s2a)
            sub3 = hub.register(s3)
            sub_none = hub.register(None)
            hub.publish_snapshot(_REST_ENGINE, reason="scene_executed")
            out_reasons = {}
            for tier_k, sub_obj in ((1, sub1), (2, sub2), (3, sub3), (99, sub_none)):
                raw = await sub_obj.queue.get()
                out_reasons[tier_k] = _json.loads(raw.split("data: ", 1)[1].strip())["reason"]
                hub.unregister(sub_obj.sub_id)
            return out_reasons

        reasons = _asyncio.run(_check_sse_reasons())
        assert reasons[1] == "scene_executed"
        assert reasons[2] == "state_sync"
        assert reasons[3] == "state_sync"
        assert reasons[99] == "state_sync"


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

    def test_interleaved_stale_snapshot_writer_cannot_resurrect_qr_or_otp(self, tmp_path: pathlib.Path) -> None:
        import json
        import os
        import secrets
        import subprocess
        import sys
        import time
        from unittest.mock import patch
        from simulator.auth.guest_invites import _claim_invite_redemption, create_invite
        from simulator.auth.session_store import get_session_store
        from simulator.auth.sqlite_security_repo import (
            load_accounts_sqlite,
            load_invites_sqlite,
            save_accounts_sqlite,
            save_invites_sqlite,
        )
        from simulator.auth_3layer import ThreeLayerAuthManager

        repo_root = pathlib.Path(__file__).resolve().parent.parent
        data_dir = tmp_path / "f03_stale_data"
        data_dir.mkdir(parents=True, exist_ok=True)
        prev_env = {
            k: os.environ.get(k)
            for k in ("SMARTHOME_DATA_DIR", "SMARTHOME_SECURITY_BACKEND", "SMARTHOME_SESSION_SECRET")
        }
        env = dict(
            os.environ,
            SMARTHOME_DATA_DIR=str(data_dir),
            SMARTHOME_SECURITY_BACKEND="sqlite",
            SIMULATOR_OFFLINE_SANDBOX="1",
            SMARTHOME_SESSION_SECRET="f03_stale_secret_" + secrets.token_hex(16),
            PYTHONPATH=str(repo_root),
            PYTHONIOENCODING="utf-8",
        )
        os.environ["SMARTHOME_DATA_DIR"] = env["SMARTHOME_DATA_DIR"]
        os.environ["SMARTHOME_SECURITY_BACKEND"] = "sqlite"
        os.environ["SMARTHOME_SESSION_SECRET"] = env["SMARTHOME_SESSION_SECRET"]
        store = get_session_store()
        prev_store_path = store.db_path
        store.db_path = data_dir / "smarthome.db"

        child_code = (
            "import pathlib, sys, time; "
            "from unittest.mock import patch; "
            "kind, barrier_s = sys.argv[1], sys.argv[2]; "
            "barrier = pathlib.Path(barrier_s)\n"
            "def gate():\n"
            "    (barrier / 'ready').write_text('ready', encoding='utf-8')\n"
            "    end = time.monotonic() + 30\n"
            "    while not (barrier / 'release').exists():\n"
            "        if time.monotonic() > end:\n"
            "            raise TimeoutError('barrier timeout')\n"
            "        time.sleep(0.01)\n"
            "if kind == 'qr':\n"
            "    from simulator.auth import guest_invites as g\n"
            "    orig = g._save\n"
            "    def wrapped(d):\n"
            "        gate()\n"
            "        return orig(d)\n"
            "    with patch.object(g, '_save', side_effect=wrapped):\n"
            "        res = g.create_invite(owner_user_id='tuan_anh', tier=3, duration_code='1d')\n"
            "else:\n"
            "    from simulator.auth_3layer import ThreeLayerAuthManager\n"
            "    mgr = ThreeLayerAuthManager()\n"
            "    t2 = next(a for a in mgr.accounts if int(a.get('tier', 3)) == 2)\n"
            "    orig = mgr._save_accounts\n"
            "    def wrapped():\n"
            "        gate()\n"
            "        return orig()\n"
            "    with patch.object(mgr, '_save_accounts', side_effect=wrapped), patch.object(mgr, '_log_event'):\n"
            "        res = mgr.request_password_reset_otp(t2['email'], send_gmail=False)\n"
            "print('WRITE_OK' if res.get('ok') else 'WRITE_FAIL')\n"
        )

        children: list[subprocess.Popen[str]] = []

        def _spawn_at_barrier(kind: str) -> tuple[pathlib.Path, subprocess.Popen[str]]:
            barrier = tmp_path / f"barrier_{kind}"
            barrier.mkdir(parents=True, exist_ok=True)
            for item in barrier.iterdir():
                item.unlink()
            proc = subprocess.Popen(
                [sys.executable, "-c", child_code, kind, str(barrier)],
                cwd=str(repo_root),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            children.append(proc)
            end = time.monotonic() + 30
            while not (barrier / "ready").exists():
                if proc.poll() is not None or time.monotonic() > end:
                    out_s, err_s = proc.communicate(timeout=5) if proc.poll() is not None else ("", "")
                    raise RuntimeError(f"writer {kind} failed before barrier: rc={proc.returncode} {out_s} {err_s}")
                time.sleep(0.01)
            return barrier, proc

        try:
            # (a) Interleaved QR stale writer vs claim
            invite = create_invite(owner_user_id="tuan_anh", tier=3, duration_code="1d")
            qr_barrier, qr_proc = _spawn_at_barrier("qr")
            first_qr = _claim_invite_redemption(invite["token"])
            assert first_qr.get("ok") is True
            (qr_barrier / "release").write_text("release", encoding="utf-8")
            qr_out, qr_err = qr_proc.communicate(timeout=30)
            assert qr_proc.returncode == 0, qr_err
            assert qr_out.strip().endswith("WRITE_OK"), qr_out
            second_qr = _claim_invite_redemption(invite["token"])
            assert second_qr.get("ok") is False
            assert second_qr.get("reason") == "used"

            # (b) Interleaved OTP stale writer on Tier 2 vs Tier 1 OTP consume
            mgr = ThreeLayerAuthManager()
            acc = next(a for a in mgr.accounts if int(a.get("tier", 3)) == 1)
            email = str(acc["email"])
            code = f"{100000 + secrets.randbelow(900000)}"
            salt, dig = mgr._hash_otp_code(code)
            pending = {
                "challenge_id": "otp_" + secrets.token_hex(12),
                "email": email,
                "display_name": acc["display_name"],
                "account_id": acc["account_id"],
                "tier": 1,
                "purpose": "layer2_login",
                "otp_salt": salt,
                "otp_hash": dig,
                "created_at": time.time(),
                "expires_at": time.time() + 300,
                "consumed": False,
            }
            acc["pending_otp"] = pending
            mgr.pending_otps[email] = pending
            assert mgr._save_accounts() is True

            otp_barrier, otp_proc = _spawn_at_barrier("otp")
            with patch.object(mgr, "_log_event"), patch.object(mgr, "_clear_login_failures"):
                first_otp = mgr.layer2_verify_otp(email, code, expected_purpose="layer2_login")
                assert first_otp.get("ok") is True
                (otp_barrier / "release").write_text("release", encoding="utf-8")
                otp_out, otp_err = otp_proc.communicate(timeout=30)
                assert otp_proc.returncode == 0, otp_err
                assert otp_out.strip().endswith("WRITE_OK"), otp_out
                second_otp = mgr.layer2_verify_otp(email, code, expected_purpose="layer2_login")
                assert second_otp.get("ok") is False

            # (c) Direct SQLite repository stale full-snapshot overwrites cannot resurrect consumed QR or OTP
            invite2 = create_invite(owner_user_id="tuan_anh", tier=3, duration_code="1d")
            stale_invites_bytes = load_invites_sqlite(data_dir)
            assert stale_invites_bytes is not None
            assert _claim_invite_redemption(invite2["token"]).get("ok") is True
            save_invites_sqlite(stale_invites_bytes, data_dir)
            reclaim = _claim_invite_redemption(invite2["token"])
            assert reclaim.get("ok") is False
            assert reclaim.get("reason") == "used"

            code2 = f"{100000 + secrets.randbelow(900000)}"
            salt2, dig2 = mgr._hash_otp_code(code2)
            pending2 = {
                "challenge_id": "otp_" + secrets.token_hex(12),
                "email": email,
                "display_name": acc["display_name"],
                "account_id": acc["account_id"],
                "tier": 1,
                "purpose": "layer2_login",
                "otp_salt": salt2,
                "otp_hash": dig2,
                "created_at": time.time(),
                "expires_at": time.time() + 300,
                "consumed": False,
            }
            mgr._sync_accounts_from_cas_if_enabled()
            acc_cur = next(a for a in mgr.accounts if int(a.get("tier", 3)) == 1)
            acc_cur["pending_otp"] = pending2
            mgr.pending_otps[email] = pending2
            assert mgr._save_accounts() is True
            stale_accounts_bytes = load_accounts_sqlite(data_dir)
            assert stale_accounts_bytes is not None
            with patch.object(mgr, "_log_event"), patch.object(mgr, "_clear_login_failures"):
                assert mgr.layer2_verify_otp(email, code2, expected_purpose="layer2_login").get("ok") is True
                save_accounts_sqlite(stale_accounts_bytes, data_dir)
                mgr_check = ThreeLayerAuthManager()
                mgr_check._sync_accounts_from_cas_if_enabled()
                replay = mgr_check.layer2_verify_otp(email, code2, expected_purpose="layer2_login")
                assert replay.get("ok") is False
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                child.communicate(timeout=5)
            store.db_path = prev_store_path
            for k, old_v in prev_env.items():
                if old_v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = old_v

    @pytest.fixture
    def sqlite_auth_manager(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
        import secrets
        from simulator.auth.session_store import get_session_store
        from simulator.auth_3layer import ThreeLayerAuthManager

        data_dir = tmp_path / "f03_transition_data"
        data_dir.mkdir()
        monkeypatch.setenv("SMARTHOME_DATA_DIR", str(data_dir))
        monkeypatch.setenv("SMARTHOME_SECURITY_BACKEND", "sqlite")
        monkeypatch.setenv("SMARTHOME_SESSION_SECRET", secrets.token_hex(32))
        monkeypatch.delenv("SIMULATOR_SECURITY_STATE_DIR", raising=False)
        store = get_session_store()
        previous_path = store.db_path
        store.db_path = data_dir / "smarthome.db"
        try:
            manager = ThreeLayerAuthManager()
            manager.reset_to_factory_defaults()
            yield manager, data_dir
        finally:
            store.db_path = previous_path

    def test_multiple_account_saves_in_one_transition_preserve_both_updates(self, sqlite_auth_manager) -> None:
        import json
        from simulator.auth.sqlite_security_repo import load_accounts_sqlite

        manager, data_dir = sqlite_auth_manager
        ids = [account["account_id"] for account in manager.accounts[:2]]

        def update_two_accounts() -> None:
            first = next(account for account in manager.accounts if account["account_id"] == ids[0])
            first["display_name"] = "First persisted update"
            assert manager._save_accounts() is True
            second = next(account for account in manager.accounts if account["account_id"] == ids[1])
            second["display_name"] = "Second persisted update"
            assert manager._save_accounts() is True

        manager._with_cas_accounts(update_two_accounts)
        persisted = {account["account_id"]: account for account in json.loads(load_accounts_sqlite(data_dir))["accounts"]}
        assert persisted[ids[0]]["display_name"] == "First persisted update"
        assert persisted[ids[1]]["display_name"] == "Second persisted update"

    def test_owner_pin_stale_snapshot_cannot_restore_old_otp_after_new_issue(self, sqlite_auth_manager) -> None:
        import time
        from unittest.mock import patch
        from simulator.auth import owner_pin
        from simulator.auth.security_state import StateConflict
        from simulator.auth.sqlite_security_repo import load_owner_pin_sqlite, save_owner_pin_sqlite

        _, data_dir = sqlite_auth_manager
        issued, previous_code = owner_pin.issue_reset_otp()
        assert issued.get("ok") is True
        stale_payload = load_owner_pin_sqlite(data_dir)
        assert stale_payload is not None
        assert owner_pin.reset_pin_with_otp(previous_code, "4829", "4829").get("ok") is True
        later = time.time() + 61
        with patch("simulator.auth.owner_pin.time.time", return_value=later), patch(
            "simulator.auth.owner_pin.secrets.randbelow", return_value=(int(previous_code) + 1) % 1_000_000
        ):
            issued_again, next_code = owner_pin.issue_reset_otp()
            assert issued_again.get("ok") is True
            with pytest.raises(StateConflict):
                save_owner_pin_sqlite(stale_payload, data_dir)
            assert owner_pin.reset_pin_with_otp(previous_code, "4829", "4829").get("ok") is False
            assert owner_pin.reset_pin_with_otp(next_code, "4829", "4829").get("ok") is True

    def test_different_purpose_issue_and_consume_prevents_stale_login_otp_revival(self, sqlite_auth_manager) -> None:
        import secrets
        import time
        from unittest.mock import patch
        from simulator.auth_3layer import ThreeLayerAuthManager

        manager, _ = sqlite_auth_manager
        account = next(account for account in manager.accounts if int(account.get("tier", 3)) == 1)
        email = account["email"]
        previous_code = str(100000 + secrets.randbelow(900000))
        next_code = str((int(previous_code) - 100000 + 1) % 900000 + 100000)
        salt, digest = manager._hash_otp_code(previous_code)
        pending = {
            "challenge_id": "otp_" + secrets.token_hex(12),
            "email": email,
            "display_name": account["display_name"],
            "account_id": account["account_id"],
            "tier": 1,
            "purpose": "layer2_login",
            "otp_salt": salt,
            "otp_hash": digest,
            "created_at": time.time() - 120,
            "expires_at": time.time() + 300,
            "consumed": False,
        }
        account["pending_otp"] = pending
        manager.pending_otps[email] = pending
        assert manager._save_accounts() is True
        stale_writer = ThreeLayerAuthManager()

        with patch("simulator.auth_3layer.random.randint", return_value=int(next_code)), patch.object(manager, "_log_event"):
            assert manager.request_password_reset_otp(email, send_gmail=False).get("ok") is True
            assert manager.layer2_verify_otp(
                email, next_code, expected_purpose="forgot_password", consume_on_success=True
            ).get("ok") is True

        stale_account = next(account for account in stale_writer.accounts if account["email"] == email)
        stale_account["display_name"] = "Metadata saved after another purpose was consumed"
        assert stale_writer._save_accounts() is True
        reader = ThreeLayerAuthManager()
        with patch.object(reader, "_log_event"), patch.object(reader, "_clear_login_failures"):
            assert reader.layer2_verify_otp(email, previous_code, expected_purpose="layer2_login").get("ok") is False

    @pytest.mark.parametrize("legacy_used", [0, 1])
    def test_legacy_consumed_login_row_blocks_stale_snapshot_without_challenge_id(self, sqlite_auth_manager, legacy_used: int) -> None:
        import json
        import secrets
        import sqlite3
        import time
        from unittest.mock import patch
        from simulator.auth.sqlite_security_repo import load_accounts_sqlite, save_accounts_sqlite
        from simulator.auth_3layer import ThreeLayerAuthManager

        manager, data_dir = sqlite_auth_manager
        stale_payload = json.loads(load_accounts_sqlite(data_dir))
        account = next(account for account in stale_payload["accounts"] if int(account.get("tier", 3)) == 1)
        email = account["email"]
        code = str(100000 + secrets.randbelow(900000))
        salt, digest = manager._hash_otp_code(code)
        now = time.time()
        pending = {
            "email": email,
            "display_name": account["display_name"],
            "account_id": account["account_id"],
            "tier": 1,
            "purpose": "layer2_login",
            "otp_salt": salt,
            "otp_hash": digest,
            "created_at": now,
            "expires_at": now + 300,
            "consumed": False,
        }
        account["pending_otp"] = pending
        with sqlite3.connect(data_dir / "smarthome.db", timeout=10) as connection:
            connection.execute(
                """
                INSERT INTO otp_challenges (
                    challenge_id, email, purpose, otp_salt, otp_hash,
                    issued_at, expires_at, used, failed_attempts, meta_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    "login_" + email, email, "layer2_login", salt, digest,
                    now, now + 300, legacy_used, json.dumps({"account_id": account["account_id"]}),
                ),
            )
        save_accounts_sqlite(json.dumps(stale_payload).encode("utf-8"), data_dir)
        reader = ThreeLayerAuthManager()
        persisted_account = next(account for account in reader.accounts if account["email"] == email)
        assert bool(persisted_account.get("pending_otp")) is (not bool(legacy_used))
        with patch.object(reader, "_log_event"), patch.object(reader, "_clear_login_failures"):
            if not legacy_used:
                assert reader.layer2_verify_otp(email, code, expected_purpose="layer2_login").get("ok") is True
            assert reader.layer2_verify_otp(email, code, expected_purpose="layer2_login").get("ok") is False

    def test_resend_supersedes_previous_otp_despite_stale_metadata_save(self, sqlite_auth_manager) -> None:
        import secrets
        import time
        from unittest.mock import patch
        from simulator.auth_3layer import ThreeLayerAuthManager

        manager, _ = sqlite_auth_manager
        account = next(account for account in manager.accounts if int(account.get("tier", 3)) == 1)
        email = account["email"]
        previous_code = str(100000 + secrets.randbelow(900000))
        next_code = str((int(previous_code) - 100000 + 1) % 900000 + 100000)
        salt, digest = manager._hash_otp_code(previous_code)
        pending = {
            "challenge_id": "otp_" + secrets.token_hex(12),
            "email": email,
            "display_name": account["display_name"],
            "account_id": account["account_id"],
            "tier": 1,
            "purpose": "layer2_login",
            "otp_salt": salt,
            "otp_hash": digest,
            "created_at": time.time() - 120,
            "expires_at": time.time() + 300,
            "consumed": False,
        }
        account["pending_otp"] = pending
        manager.pending_otps[email] = pending
        assert manager._save_accounts() is True
        stale_writer = ThreeLayerAuthManager()

        with patch("simulator.auth_3layer.random.randint", return_value=int(next_code)), patch.object(
            manager, "send_real_gmail_otp", return_value={"sent_real_gmail": True}
        ):
            assert manager.send_layer2_login_otp(email).get("ok") is True

        stale_account = next(account for account in stale_writer.accounts if account["email"] == email)
        stale_account["display_name"] = "Metadata saved by old process"
        assert stale_writer._save_accounts() is True
        reader = ThreeLayerAuthManager()
        with patch.object(reader, "_log_event"), patch.object(reader, "_clear_login_failures"):
            assert reader.layer2_verify_otp(email, previous_code, expected_purpose="layer2_login").get("ok") is False
            assert reader.layer2_verify_otp(email, next_code, expected_purpose="layer2_login").get("ok") is True

    def test_legacy_used_1_missing_challenge_id_verify_fails(self, sqlite_auth_manager) -> None:
        import json
        import secrets
        import sqlite3
        import time
        from unittest.mock import patch
        from simulator.auth.sqlite_security_repo import load_accounts_sqlite, save_accounts_sqlite
        from simulator.auth_3layer import ThreeLayerAuthManager

        manager, data_dir = sqlite_auth_manager
        stale_payload = json.loads(load_accounts_sqlite(data_dir))
        account = next(account for account in stale_payload["accounts"] if int(account.get("tier", 3)) == 1)
        email = account["email"]
        code = str(100000 + secrets.randbelow(900000))
        salt, digest = manager._hash_otp_code(code)
        now = time.time()
        pending = {
            "email": email,
            "display_name": account["display_name"],
            "account_id": account["account_id"],
            "tier": 1,
            "purpose": "layer2_login",
            "otp_salt": salt,
            "otp_hash": digest,
            "created_at": now,
            "expires_at": now + 300,
            "consumed": False,
        }
        account["pending_otp"] = pending
        with sqlite3.connect(data_dir / "smarthome.db", timeout=10) as connection:
            connection.execute(
                """
                INSERT INTO otp_challenges (
                    challenge_id, email, purpose, otp_salt, otp_hash,
                    issued_at, expires_at, used, failed_attempts, meta_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, ?)
                """,
                (
                    "login_" + email, email, "layer2_login", salt, digest,
                    now, now + 300, json.dumps({"account_id": account["account_id"]}),
                ),
            )
        save_accounts_sqlite(json.dumps(stale_payload).encode("utf-8"), data_dir)
        reader = ThreeLayerAuthManager()
        persisted_account = next(account for account in reader.accounts if account["email"] == email)
        assert persisted_account.get("pending_otp") is None
        with patch.object(reader, "_log_event"), patch.object(reader, "_clear_login_failures"):
            verify_res = reader.layer2_verify_otp(email, code, expected_purpose="layer2_login")
            assert verify_res.get("ok") is False

    def test_qr_already_redeemed_stale_snapshot_lower_redeem_count_rejected(self, sqlite_auth_manager) -> None:
        from simulator.auth.guest_invites import create_invite, redeem_token
        from simulator.auth.sqlite_security_repo import load_invites_sqlite, save_invites_sqlite

        _, data_dir = sqlite_auth_manager
        invite = create_invite(owner_user_id="tuan_anh", tier=3, duration_code="1d")
        token = invite["token"]
        stale_invites_raw = load_invites_sqlite(data_dir)
        assert stale_invites_raw is not None

        redeem_res_1 = redeem_token(token)
        assert redeem_res_1.get("ok") is True

        # Stale snapshot with lower redeem_count (0) cannot reset redeem_count or allow second redemption
        save_invites_sqlite(stale_invites_raw, data_dir)
        redeem_res_2 = redeem_token(token)
        assert redeem_res_2.get("ok") is False

    def test_owner_pin_legacy_snapshot_missing_revision_cannot_resurrect_consumed_otp_or_supersede_new_otp(
        self, sqlite_auth_manager
    ) -> None:
        import json
        import time
        from unittest.mock import patch
        from simulator.auth import owner_pin
        from simulator.auth.sqlite_security_repo import load_owner_pin_sqlite, save_owner_pin_sqlite

        _, data_dir = sqlite_auth_manager
        issued, previous_code = owner_pin.issue_reset_otp()
        assert issued.get("ok") is True

        legacy_payload = json.loads(load_owner_pin_sqlite(data_dir))
        assert "revision" in legacy_payload
        legacy_payload.pop("revision", None)

        first_consume = owner_pin.reset_pin_with_otp(previous_code, "4829", "4829")
        assert first_consume.get("ok") is True

        later = time.time() + 61
        with patch("simulator.auth.owner_pin.time.time", return_value=later), patch(
            "simulator.auth.owner_pin.secrets.randbelow", return_value=(int(previous_code) + 1) % 1_000_000
        ):
            issued_again, next_code = owner_pin.issue_reset_otp()
            assert issued_again.get("ok") is True

            # Legacy snapshot without revision must NOT resurrect previous_code or supersede next_code
            save_owner_pin_sqlite(json.dumps(legacy_payload).encode("utf-8"), data_dir)

            legitimate = owner_pin.reset_pin_with_otp(next_code, "4829", "4829")
            replay = owner_pin.reset_pin_with_otp(previous_code, "4829", "4829")

            assert legitimate.get("ok") is True, f"Next OTP was superseded/invalidated: {legitimate}"
            assert replay.get("ok") is False, f"Consumed legacy OTP was resurrected: {replay}"

    def test_owner_pin_legacy_snapshot_missing_revision_unused_otp_accepted_exactly_once(
        self, sqlite_auth_manager
    ) -> None:
        import json
        from simulator.auth import owner_pin
        from simulator.auth.sqlite_security_repo import load_owner_pin_sqlite, save_owner_pin_sqlite

        _, data_dir = sqlite_auth_manager
        issued, code = owner_pin.issue_reset_otp()
        assert issued.get("ok") is True

        legacy_payload = json.loads(load_owner_pin_sqlite(data_dir))
        legacy_payload.pop("revision", None)

        # Legacy snapshot without revision containing valid unused OTP is saved
        save_owner_pin_sqlite(json.dumps(legacy_payload).encode("utf-8"), data_dir)

        # Must be usable exactly once
        consume1 = owner_pin.reset_pin_with_otp(code, "4829", "4829")
        assert consume1.get("ok") is True, f"Valid unused OTP rejected: {consume1}"

        consume2 = owner_pin.reset_pin_with_otp(code, "4829", "4829")
        assert consume2.get("ok") is False, f"OTP consumed twice: {consume2}"

    def test_owner_pin_multiprocess_interleaved_legacy_writer_and_race_two_consumers(
        self, tmp_path: pathlib.Path
    ) -> None:
        import concurrent.futures
        import json
        import os
        import secrets
        import subprocess
        import sys
        import time
        from unittest.mock import patch
        from simulator.auth import owner_pin
        from simulator.auth.session_store import get_session_store
        from simulator.auth.sqlite_security_repo import load_owner_pin_sqlite, save_owner_pin_sqlite

        repo_root = pathlib.Path(__file__).resolve().parent.parent
        data_dir = tmp_path / "f03_pin_race_data"
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
            # 1. Issue OTP A
            issued1, code_a = owner_pin.issue_reset_otp()
            assert issued1.get("ok") is True

            # 2. Capture legacy snapshot without revision
            legacy_doc = json.loads(load_owner_pin_sqlite(data_dir))
            legacy_doc.pop("revision", None)
            legacy_bytes = json.dumps(legacy_doc).encode("utf-8")

            # 3. Consume OTP A
            res_a = owner_pin.reset_pin_with_otp(code_a, "4829", "4829")
            assert res_a.get("ok") is True

            # 4. 61s later, issue OTP B
            later = time.time() + 61
            with patch("simulator.auth.owner_pin.time.time", return_value=later), patch(
                "simulator.auth.owner_pin.secrets.randbelow", return_value=(int(code_a) + 1) % 1_000_000
            ):
                issued2, code_b = owner_pin.issue_reset_otp()
                assert issued2.get("ok") is True

            # 5. Multiprocess: Process 1 tries to write legacy snapshot, while Process 2 and 3 race to consume OTP B
            writer_script = (
                "import sys; "
                "from simulator.auth.sqlite_security_repo import save_owner_pin_sqlite; "
                "save_owner_pin_sqlite(sys.argv[1].encode('utf-8'), None); "
                "print('WROTE')"
            )
            consumer_script = (
                "import sys; "
                "from simulator.auth.owner_pin import reset_pin_with_otp; "
                "r = reset_pin_with_otp(sys.argv[1], '4829', '4829'); "
                "print('OK' if r.get('ok') else 'REJECT')"
            )
            replay_script = (
                "import sys; "
                "from simulator.auth.owner_pin import reset_pin_with_otp; "
                "r = reset_pin_with_otp(sys.argv[1], '4829', '4829'); "
                "print('REPLAY_OK' if r.get('ok') else 'REPLAY_REJECT')"
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                p_writer = pool.submit(
                    subprocess.run,
                    [sys.executable, "-c", writer_script, legacy_bytes.decode("utf-8")],
                    text=True, capture_output=True, env=env, cwd=str(repo_root), timeout=30,
                )
                p_consumer1 = pool.submit(
                    subprocess.run,
                    [sys.executable, "-c", consumer_script, code_b],
                    text=True, capture_output=True, env=env, cwd=str(repo_root), timeout=30,
                )
                p_consumer2 = pool.submit(
                    subprocess.run,
                    [sys.executable, "-c", consumer_script, code_b],
                    text=True, capture_output=True, env=env, cwd=str(repo_root), timeout=30,
                )
                writer_res = p_writer.result()
                c1_res = p_consumer1.result()
                c2_res = p_consumer2.result()

            assert writer_res.returncode == 0, writer_res.stderr
            c_outs = [c1_res.stdout.strip(), c2_res.stdout.strip()]
            assert c_outs.count("OK") == 1
            assert c_outs.count("REJECT") == 1

            # 6. Replay of OTP A MUST still be rejected!
            replay_proc = subprocess.run(
                [sys.executable, "-c", replay_script, code_a],
                text=True, capture_output=True, env=env, cwd=str(repo_root), timeout=30,
            )
            assert replay_proc.stdout.strip() == "REPLAY_REJECT"
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
            o1 = client.post("/api/schedules", headers=H_TIER1, json={"device_id": "speaker_amp", "action": "turn_on", "time_hhmm": "14:00", "schedule_type": "once"})
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
            o2 = client.post("/api/schedules", headers=H_TIER1, json={"device_id": "speaker_amp", "action": "turn_off", "time_hhmm": "18:00", "schedule_type": "once"})
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
            repo.create_schedule(owner_user_id="tuan_anh", owner_tier=1, device_id="speaker_amp", action="turn_on", time_hhmm="09:00", schedule_type="once", run_date_vn="2026-11-17")
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
            t1 = await _REST_ENGINE.schedule_timer_flexible("speaker_amp", "turn_on", seconds=120)
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


class TestF05LosslessMigrationAndFailLoudly:
    """F05: SQLite migration copies automation tables and timer execution columns losslessly and fails loudly on data loss."""

    def test_lossless_automation_migration_idempotent_and_corrupt_source_raises(self, tmp_path: pathlib.Path) -> None:
        import sqlite3
        from scripts.migrate_to_sqlite import MigrationDataLossError, migrate_all
        from simulator.automation_repo import create_automation_rule, create_schedule, set_user_can_create_links, upsert_custom_command, upsert_timer_row
        from simulator.database_sqlite import init_sqlite_database
        from simulator.db_migrations import _migrate_custom_commands_per_owner, apply_schema_migrations, open_wal_connection

        src_dir = tmp_path / "src"
        tgt_dir = tmp_path / "tgt"
        src_dir.mkdir(parents=True, exist_ok=True)
        src_db = src_dir / "smarthome.db"
        init_sqlite_database(src_db)

        future_epoch = time.time() + 900.0
        set_user_can_create_links("thanh_vien_a", True, owner_tier=2, display_name="Thành viên A", db_path=src_db)
        upsert_timer_row(
            timer_id="t_f05",
            owner_user_id="thanh_vien_a",
            owner_tier=2,
            device_id="speaker_amp",
            action="turn_on",
            fire_at_epoch=future_epoch,
            delay_seconds=900.0,
            repeat_rule="daily",
            label="F05 timer",
            db_path=src_db,
        )
        create_schedule(
            owner_user_id="thanh_vien_a",
            owner_tier=2,
            device_id="speaker_amp",
            action="turn_off",
            time_hhmm="22:15",
            schedule_id="sc_f05",
            db_path=src_db,
        )
        create_automation_rule(
            owner_user_id="thanh_vien_a",
            owner_tier=2,
            when_device_id="living_room_light",
            when_state="ON",
            then_device_id="speaker_amp",
            then_action="turn_on",
            rule_id="rl_f05",
            db_path=src_db,
        )
        upsert_custom_command(
            phrase="ngủ trưa f05",
            steps=[{"device_id": "speaker_amp", "action": "turn_on"}],
            owner_user_id="thanh_vien_a",
            owner_tier=2,
            command_id="cc_f05",
            db_path=src_db,
        )

        tgt_db = tgt_dir / "smarthome.db"
        r1 = migrate_all(tgt_db, src_dir, fetch_github=False, seed_assets=False, upgrade_repo_db=False)
        r2 = migrate_all(tgt_db, src_dir, fetch_github=False, seed_assets=False, upgrade_repo_db=False)
        assert r1["ok"] is True and r2["ok"] is True
        assert r1["after_target_counts"] == r2["after_target_counts"]
        assert r1["after_target_counts"]["schedules"] == 1
        assert r1["after_target_counts"]["automation_rules"] == 1
        assert r1["after_target_counts"]["custom_commands"] == 1

        c_tgt = open_wal_connection(tgt_db, readonly=True)
        try:
            t_row = dict(c_tgt.execute("SELECT * FROM timers_pool WHERE timer_id = 't_f05'").fetchone())
            assert t_row["owner_tier"] == 2
            assert round(float(t_row["delay_seconds"]), 1) == 900.0
            assert round(float(t_row["fire_at_epoch"]), 1) == round(future_epoch, 1)
            u_row = dict(c_tgt.execute("SELECT can_create_links FROM users WHERE user_id = 'thanh_vien_a'").fetchone())
            assert u_row["can_create_links"] == 1
            assert c_tgt.execute("PRAGMA foreign_key_check").fetchall() == []
        finally:
            c_tgt.close()

        # Corrupt JSONL source must fail loudly rather than silently drop log entries
        corrupt_dir = tmp_path / "corrupt_src"
        corrupt_dir.mkdir(parents=True, exist_ok=True)
        (corrupt_dir / "system_audit_logs.jsonl").write_text("{not-valid-json\n", encoding="utf-8")
        with pytest.raises(MigrationDataLossError):
            migrate_all(tmp_path / "corrupt_tgt" / "smarthome.db", corrupt_dir, fetch_github=False, seed_assets=False, upgrade_repo_db=False)

        # Lossy duplicate (owner_user_id, phrase_norm) rebuild in _migrate_custom_commands_per_owner must raise RuntimeError
        dup_db = tmp_path / "dup_cc.db"
        conn_dup = open_wal_connection(dup_db, readonly=False)
        try:
            apply_schema_migrations(conn_dup)
            conn_dup.execute("DROP TABLE custom_commands")
            conn_dup.execute(
                """
                CREATE TABLE custom_commands (
                    command_id TEXT PRIMARY KEY,
                    phrase TEXT NOT NULL,
                    phrase_norm TEXT NOT NULL,
                    owner_user_id TEXT NOT NULL,
                    owner_tier INTEGER NOT NULL DEFAULT 1,
                    steps_json TEXT NOT NULL DEFAULT '[]',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL DEFAULT 0
                )
                """
            )
            conn_dup.execute("INSERT INTO custom_commands VALUES ('c1', 'a', 'a', 'tuan_anh', 1, '[]', 1, 0, 0)")
            conn_dup.execute("INSERT INTO custom_commands VALUES ('c2', 'a', 'a', 'tuan_anh', 1, '[]', 1, 0, 0)")
            conn_dup.commit()
            with pytest.raises(RuntimeError):
                _migrate_custom_commands_per_owner(conn_dup)
        finally:
            conn_dup.close()


class TestF06HttpAudioNoWeSpeaker:
    """F06: HTTP audio endpoints never call WeSpeaker/speaker verification and derive auth strictly from session tier."""

    def test_http_voice_command_zero_wespeaker_and_session_tier_rbac(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import array
        import base64
        import math
        from simulator.voice import stt_pipeline as stt

        called = {"n": 0}

        def _forbid_wespeaker(*args: Any, **kwargs: Any) -> Any:
            called["n"] += 1
            raise AssertionError("extract_wespeaker_embedding must not be called on HTTP audio paths")

        monkeypatch.setattr(stt, "extract_wespeaker_embedding", _forbid_wespeaker)

        root_dir = pathlib.Path(__file__).resolve().parent.parent
        cau2 = (root_dir / "test_audio" / "cac_cau_lenh_cua_sep" / "cau_2_mo_cua_chinh.wav").read_bytes()
        cau3 = (root_dir / "test_audio" / "cac_cau_lenh_cua_sep" / "cau_3_dong_cua_chinh.wav").read_bytes()
        cau4 = (root_dir / "test_audio" / "cac_cau_lenh_cua_sep" / "cau_4_bat_den_phong_khach.wav").read_bytes()

        # Pure catalog matching with mismatching verified_tier=3 must ignore tier filtering & WeSpeaker
        pcm_c4, raw_c4 = stt.decode_audio_bytes_to_pcm16k(cau4)
        matched_sig, score = stt.match_signature_from_catalog(pcm_c4, raw_c4, verified_tier=3)
        assert matched_sig is not None and score == 1.0
        assert called["n"] == 0

        with TestClient(app) as client:
            # 1. Synthetic tone PCM16k -> 200 silent empty_transcript, zero WeSpeaker calls
            pcm_sine = array.array("h", (int(5000 * math.sin(2 * math.pi * 175 * i / 16000)) for i in range(32000))).tobytes()
            r_sine = client.post("/api/voice_command", headers=H_TIER1, json={"pcm16k_b64": base64.b64encode(pcm_sine).decode()})
            assert r_sine.status_code == 200
            d_sine = r_sine.json()
            assert d_sine.get("silent") is True and d_sine.get("reason") == "empty_transcript"
            assert called["n"] == 0

            # Reset baseline states before testing confirmation + session RBAC flow
            client.post("/api/device", headers=H_TIER1, json={"device_id": "living_room_light", "action": "turn_off"})
            client.post("/api/device", headers=H_TIER1, json={"device_id": "main_door", "action": "close"})

            # 2. Owner's WAV ("bật đèn phòng khách") sent with Tier 3 guest session -> prompts then executes after "ok"
            r_g_light = client.post("/api/voice_command", headers=H_TIER3, json={"wav_b64": base64.b64encode(cau4).decode()})
            assert r_g_light.status_code == 200
            assert r_g_light.json().get("authorized") is True and r_g_light.json().get("permission") == "ALLOWED"
            assert r_g_light.json().get("requires_confirmation") is True
            assert _REST_ENGINE.devices["living_room_light"]["state"] == "OFF"
            r_g_light_ok = client.post("/api/voice_command", headers=H_TIER3, json={"transcript": "ok"})
            assert r_g_light_ok.status_code == 200 and r_g_light_ok.json().get("ok") is True
            assert _REST_ENGINE.devices["living_room_light"]["state"] == "ON"

            # 3. Owner's WAV ("mở cửa chính") sent with Tier 3 guest session -> denied 403 immediately by session RBAC
            r_g_door = client.post("/api/voice_command", headers=H_TIER3, json={"wav_b64": base64.b64encode(cau2).decode()})
            assert r_g_door.status_code == 403
            assert r_g_door.json().get("rbac_blocked") is True
            assert _REST_ENGINE.devices["main_door"]["state"] == "CLOSED"

            # 4. Owner's WAV ("mở cửa chính" / "đóng cửa chính") sent with Tier 1 owner session -> prompts then executes on "ok"
            r_o_open = client.post("/api/voice_command", headers=H_TIER1, json={"wav_b64": base64.b64encode(cau2).decode()})
            assert r_o_open.status_code == 200 and r_o_open.json().get("requires_confirmation") is True
            assert _REST_ENGINE.devices["main_door"]["state"] == "CLOSED"
            r_o_open_ok = client.post("/api/voice_command", headers=H_TIER1, json={"transcript": "ok"})
            assert r_o_open_ok.status_code == 200 and _REST_ENGINE.devices["main_door"]["state"] == "OPEN"

            r_o_close = client.post("/api/voice_command", headers=H_TIER1, json={"wav_b64": base64.b64encode(cau3).decode()})
            assert r_o_close.status_code == 200 and r_o_close.json().get("requires_confirmation") is True
            assert _REST_ENGINE.devices["main_door"]["state"] == "OPEN"
            r_o_close_ok = client.post("/api/voice_command", headers=H_TIER1, json={"transcript": "ok"})
            assert r_o_close_ok.status_code == 200 and _REST_ENGINE.devices["main_door"]["state"] == "CLOSED"
            client.post("/api/device", headers=H_TIER1, json={"device_id": "living_room_light", "action": "turn_off"})
            assert called["n"] == 0




