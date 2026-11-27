"""Comprehensive automated tests for agyfix11 R1-R4 (Voice custom command no-reconfirm,
short exact Vietnamese replies, ambiguity/negation/management guards, RBAC & offline board,
confirmation invariants, VAD config, server stutter-gap detector, and client jitter buffer).
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import re
import subprocess
import time
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.ai_tool_registry import dispatch_tool
from backend.auth.session_store import UserSession, get_session_store
from backend.automation_nlu import (
    handle_confirmation_reply,
    prepare_pending_mutation,
    process_automation_nlu_command,
)
from backend.automation_repo import (
    PENDING_CONFIRM_TTL_SEC,
    clear_all_rules_and_commands,
    get_pending_confirmation,
    list_automation_rules,
    list_custom_commands,
    list_pending_timers,
    list_schedules,
    match_custom_command_with_ambiguity,
    reset_timers_and_schedules_scoped,
    upsert_custom_command,
)
from backend.database_sqlite import init_sqlite_database
from backend.engine.constants_and_time import get_board_heartbeat_timeout_sec
from backend.live.gemini_bridge import LiveBridgeSession
from backend.live.prompt_builder import build_system_instruction, make_live_config
from backend.rule_engine import SmartHomeEngine
from backend.server import app
from backend.voice.session_voice_command import (
    process_session_voice_command,
    reset_session_echo_guards,
)
from backend.voice.vietnamese_policy import classify_small_talk_vi

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
APP_JS = REPO_ROOT / "web" / "js" / "app.js"
MOBILE_APP_JS = REPO_ROOT / "web" / "js" / "mobile_app.js"

FORBIDDEN_REPLY_PATTERNS = (
    "đúng không",
    "chắc chắn rồi",
    "bạn cần giúp gì thêm",
    "main_door",
    "living_room_light",
    "bedroom_light",
    "garden_pump",
    "alarm_siren",
    "speaker_amp",
    "control_device",
    "run_custom_command",
    "run_custom_scene",
    "execute_alias_rule",
    "{",
    "}",
)


def _make_user_session(
    session_id: str,
    user_id: str,
    display_name: str,
    tier: int,
    role: str,
) -> UserSession:
    now = time.time()
    return UserSession(
        session_id=session_id,
        user_id=user_id,
        email=f"{user_id}@test.local",
        display_name=display_name,
        tier=tier,
        role=role,
        created_at=now,
        expires_at=now + 3600.0,
        source="test_agyfix11",
        is_authenticated=True,
    )


def _assert_short_exact_reply_vi(reply: str, *, expected_substring: str | None = None, max_words: int = 12) -> None:
    clean = str(reply or "").strip()
    assert clean, "Reply must be non-empty Vietnamese"
    low = clean.lower()
    for bad in FORBIDDEN_REPLY_PATTERNS:
        assert bad not in low, f"Reply {clean!r} must not contain forbidden pattern {bad!r}"
    words = [w for w in re.split(r"\s+", clean) if w]
    assert len(words) <= max_words, f"Reply {clean!r} has {len(words)} words > {max_words}"
    if expected_substring is not None:
        assert expected_substring.lower() in low, f"Expected {expected_substring!r} in {clean!r}"


class _DummyWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_text(self, data: str) -> None:
        self.sent.append(json.loads(data))


def _make_live_bridge(engine: SmartHomeEngine, session: UserSession) -> tuple[LiveBridgeSession, _DummyWebSocket]:
    ws = _DummyWebSocket()
    bridge = LiveBridgeSession(websocket=ws, engine=engine, ws_session=session)
    bridge._cached_ws_actor = session
    bridge._cached_ws_actor_ts = time.time()
    return bridge, ws


def _call_live_tool(bridge: LiveBridgeSession, name: str, args: dict[str, Any]) -> dict[str, Any]:
    fc = SimpleNamespace(name=name, args=args, id=f"fc_{name}_{int(time.time() * 1000)}")
    return asyncio.run(bridge.handle_tool_call(fc))


@pytest.fixture(autouse=True)
def _clean_automation_state() -> Any:
    init_sqlite_database()
    reset_session_echo_guards()
    clear_all_rules_and_commands()
    reset_timers_and_schedules_scoped(clear_all=True)
    yield
    clear_all_rules_and_commands()
    reset_timers_and_schedules_scoped(clear_all=True)


# ==============================================================================
# R1 + R2: SAVED CUSTOM COMMAND EXECUTES IMMEDIATELY WITH 5+ NATURAL VARIANTS
# ==============================================================================


PHRASING_VARIANTS: list[str] = [
    "đọc sách tối",
    "tối đọc sách",
    "à... ừm... đọc sách tối nhé",
    "đọc sách tối giúp tôi đi ạ",
    "chạy lệnh đọc sách tối",
    "kích hoạt khẩu lệnh đọc sách tối luôn",
]


class TestCustomCommandNoReconfirmAndShortReplies:
    def test_create_confirms_once_then_live_dispatcher_runs_immediately_all_variants(self) -> None:
        engine = SmartHomeEngine()
        owner = _make_user_session("sess_live_owner_1", "owner_fix11", "Chủ Nhà", 1, "ADMIN")
        bridge, _ = _make_live_bridge(engine, owner)

        # 1. Creating custom command MUST require confirmation once
        staged = _call_live_tool(
            bridge,
            "create_custom_scene",
            {"phrase": "đọc sách tối", "steps_text": "mở cửa chính"},
        )
        assert staged["ok"] is True
        assert staged.get("requires_confirmation") is True
        assert staged.get("executed") is not True
        assert len(list_custom_commands(include_disabled=False)) == 0

        # 2. Confirm ONCE -> saved in SQLite
        confirmed = _call_live_tool(bridge, "confirm_or_cancel_pending_action", {"confirmed": True})
        assert confirmed["ok"] is True
        assert len(list_custom_commands(include_disabled=False)) == 1

        # 3. Invoke across run_custom_command, run_custom_scene, execute_alias_rule with 5+ natural variants
        tool_calls = [
            ("run_custom_command", lambda p: {"phrase": p}),
            ("run_custom_scene", lambda p: {"phrase_or_id": p}),
            ("execute_alias_rule", lambda p: {"phrase": p}),
        ]
        for tool_name, arg_fn in tool_calls:
            for variant in PHRASING_VARIANTS:
                asyncio.run(engine.execute_device_action("main_door", "close", bypass_rbac=True))
                assert engine.devices["main_door"]["state"] == "CLOSED"

                res = _call_live_tool(bridge, tool_name, arg_fn(variant))
                assert res.get("ok") is True, f"{tool_name}({variant!r}) failed: {res}"
                assert res.get("requires_confirmation") is False, f"{tool_name}({variant!r}) asked re-confirm!"
                assert res.get("executed") is True, f"{tool_name}({variant!r}) did not execute!"
                assert engine.devices["main_door"]["state"] == "OPEN"
                _assert_short_exact_reply_vi(
                    str(res.get("exact_spoken_reply") or res.get("reply") or ""),
                    expected_substring="Đã mở cửa chính",
                    max_words=12,
                )

    @pytest.mark.parametrize("variant", PHRASING_VARIANTS)
    def test_voice_command_executes_saved_custom_command_immediately_all_variants(self, variant: str) -> None:
        engine = SmartHomeEngine()
        owner = _make_user_session("sess_voice_owner_1", "owner_fix11", "Chủ Nhà", 1, "ADMIN")

        # Create once via voice command (requires confirmation once)
        r_create, st_create = asyncio.run(
            process_session_voice_command(
                engine=engine,
                session=owner,
                payload={"transcript": "tạo lệnh đọc sách tối là mở cửa chính"},
            )
        )
        assert st_create == 200 and r_create["ok"] is True
        assert r_create["requires_confirmation"] is True
        assert r_create["executed"] is False
        assert len(list_custom_commands(include_disabled=False)) == 0

        r_ok, st_ok = asyncio.run(
            process_session_voice_command(
                engine=engine,
                session=owner,
                payload={"transcript": "ok"},
            )
        )
        assert st_ok == 200 and r_ok["ok"] is True
        assert len(list_custom_commands(include_disabled=False)) == 1

        # Reset door closed, then invoke saved custom command with natural variant
        asyncio.run(engine.execute_device_action("main_door", "close", bypass_rbac=True))
        assert engine.devices["main_door"]["state"] == "CLOSED"

        r_run, st_run = asyncio.run(
            process_session_voice_command(
                engine=engine,
                session=owner,
                payload={"transcript": variant},
            )
        )
        assert st_run == 200 and r_run["ok"] is True, f"Voice variant {variant!r} failed: {r_run}"
        assert r_run.get("requires_confirmation") is False
        assert r_run.get("executed") is True
        assert engine.devices["main_door"]["state"] == "OPEN"
        _assert_short_exact_reply_vi(
            str(r_run.get("exact_spoken_reply") or r_run.get("reply") or ""),
            expected_substring="Đã mở cửa chính",
            max_words=12,
        )

    def test_text_command_endpoint_executes_saved_custom_command_immediately_all_variants(self) -> None:
        import backend.api.deps as api_deps

        store = get_session_store()
        owner_sess = store.create_session(
            user_id="owner_text_fix11",
            email="owner_text_fix11@test.local",
            display_name="Chủ Nhà",
            tier=1,
            role="ADMIN",
            source="test_agyfix11",
        )
        client = TestClient(app)
        headers = {"X-Session-Token": owner_sess.session_id}
        try:
            # 1. Create custom command -> requires confirmation once
            resp_c = client.post(
                "/api/text_command",
                headers=headers,
                json={"text": "tạo lệnh đọc sách tối là mở cửa chính"},
            )
            assert resp_c.status_code == 200
            body_c = resp_c.json()
            assert body_c["ok"] is True
            assert body_c["requires_confirmation"] is True
            assert body_c.get("executed") is not True

            # 2. Confirm once
            resp_ok = client.post("/api/text_command", headers=headers, json={"text": "đồng ý"})
            assert resp_ok.status_code == 200 and resp_ok.json()["ok"] is True
            assert len(list_custom_commands(include_disabled=False)) == 1

            # 3. Run all 5+ natural phrasing variants -> immediate execution, no confirmation
            for variant in PHRASING_VARIANTS:
                asyncio.run(api_deps._REST_ENGINE.execute_device_action("main_door", "close", bypass_rbac=True))
                assert api_deps._REST_ENGINE.devices["main_door"]["state"] == "CLOSED"

                resp_run = client.post("/api/text_command", headers=headers, json={"text": variant})
                assert resp_run.status_code == 200, f"/api/text_command({variant!r}) -> {resp_run.status_code}: {resp_run.text}"
                body_run = resp_run.json()
                assert body_run["ok"] is True
                assert body_run.get("requires_confirmation") is False
                assert body_run.get("executed") is True
                assert api_deps._REST_ENGINE.devices["main_door"]["state"] == "OPEN"
                _assert_short_exact_reply_vi(
                    str(body_run.get("exact_spoken_reply") or body_run.get("reply") or ""),
                    expected_substring="Đã mở cửa chính",
                    max_words=12,
                )
        finally:
            if hasattr(store, "revoke_session"):
                store.revoke_session(owner_sess.session_id)

    def test_short_exact_replies_small_talk_and_prompt_rules(self) -> None:
        engine = SmartHomeEngine()
        for phrase in ("xin chào", "cảm ơn", "tạm biệt", "chào buổi sáng"):
            st = classify_small_talk_vi(phrase, user_name="Tuấn Anh")
            assert st is not None
            _assert_short_exact_reply_vi(str(st["reply"]), max_words=10)

        prompt = build_system_instruction(engine)
        assert "THỰC THI NGAY" in prompt
        assert "KHÔNG HỎI XÁC NHẬN" in prompt
        assert "Bạn cần giúp gì thêm không?" in prompt  # explicitly listed under TUYỆT ĐỐI KHÔNG


# ==============================================================================
# AMBIGUITY, UNMATCHED, NEGATION & POLITE MANAGEMENT GUARDS
# ==============================================================================


class TestAmbiguityNegationAndManagementGuards:
    def test_ambiguous_custom_commands_ask_one_short_clarification_without_mutation(self) -> None:
        engine = SmartHomeEngine()
        owner = _make_user_session("sess_ambig_1", "owner_ambig", "Chủ Nhà", 1, "ADMIN")
        asyncio.run(engine.execute_device_action("living_room_light", "turn_off", bypass_rbac=True))
        asyncio.run(engine.execute_device_action("bedroom_light", "turn_off", bypass_rbac=True))

        upsert_custom_command(
            phrase="chế độ nghỉ ngơi sáng",
            steps=[{"device_id": "living_room_light", "action": "turn_on"}],
            owner_user_id=owner.user_id,
            owner_tier=owner.tier,
            owner_name=owner.display_name,
        )
        upsert_custom_command(
            phrase="chế độ nghỉ ngơi tối",
            steps=[{"device_id": "bedroom_light", "action": "turn_on"}],
            owner_user_id=owner.user_id,
            owner_tier=owner.tier,
            owner_name=owner.display_name,
        )

        # Direct matcher check
        m = match_custom_command_with_ambiguity("chế độ nghỉ ngơi", owner_user_id=owner.user_id)
        assert m["status"] == "ambiguous"
        assert len(m["candidates"]) == 2
        assert "?" in str(m["clarification_question"])

        # Voice command path
        r_v, s_v = asyncio.run(
            process_session_voice_command(engine=engine, session=owner, payload={"transcript": "chế độ nghỉ ngơi"})
        )
        assert s_v == 200 and r_v["ok"] is True
        assert r_v.get("needs_clarification") is True
        assert r_v.get("executed") is False
        assert r_v.get("requires_confirmation") is False
        assert engine.devices["living_room_light"]["state"] == "OFF"
        assert engine.devices["bedroom_light"]["state"] == "OFF"
        q_v = str(r_v.get("exact_spoken_reply") or r_v.get("reply") or "")
        assert q_v.count("?") == 1

        # LiveBridgeSession tools (run_custom_command, run_custom_scene, execute_alias_rule)
        bridge, _ = _make_live_bridge(engine, owner)
        for tname, targs in (
            ("run_custom_command", {"phrase": "chế độ nghỉ ngơi"}),
            ("run_custom_scene", {"phrase_or_id": "chế độ nghỉ ngơi"}),
            ("execute_alias_rule", {"phrase": "chế độ nghỉ ngơi"}),
        ):
            r_t = _call_live_tool(bridge, tname, targs)
            assert r_t.get("needs_clarification") is True, f"{tname} did not clarify: {r_t}"
            assert r_t.get("executed") is False
            assert engine.devices["living_room_light"]["state"] == "OFF"
            assert engine.devices["bedroom_light"]["state"] == "OFF"

    def test_unmatched_negated_and_polite_management_never_execute_custom_command(self) -> None:
        engine = SmartHomeEngine()
        owner = _make_user_session("sess_guard_1", "owner_guard", "Chủ Nhà", 1, "ADMIN")
        asyncio.run(engine.execute_device_action("main_door", "close", bypass_rbac=True))
        asyncio.run(engine.execute_device_action("living_room_light", "turn_off", bypass_rbac=True))

        upsert_custom_command(
            phrase="chế độ đọc sách",
            steps=[
                {"device_id": "main_door", "action": "open"},
                {"device_id": "living_room_light", "action": "turn_on"},
            ],
            owner_user_id=owner.user_id,
            owner_tier=owner.tier,
            owner_name=owner.display_name,
        )

        # Unmatched phrase must not mutate any device
        r_un, _ = asyncio.run(
            process_session_voice_command(
                engine=engine,
                session=owner,
                payload={"transcript": "chế độ đi du lịch mặt trăng"},
            )
        )
        assert r_un.get("executed") is not True
        assert engine.devices["main_door"]["state"] == "CLOSED"
        assert engine.devices["living_room_light"]["state"] == "OFF"

        # Negated utterances must NEVER execute
        for neg in ("đừng chạy chế độ đọc sách", "không chạy chế độ đọc sách"):
            assert match_custom_command_with_ambiguity(neg, owner_user_id=owner.user_id)["status"] == "none"
            r_neg, _ = asyncio.run(
                process_session_voice_command(engine=engine, session=owner, payload={"transcript": neg})
            )
            assert r_neg.get("executed") is not True, f"Negated {neg!r} must never execute: {r_neg}"
            assert engine.devices["main_door"]["state"] == "CLOSED"
            assert engine.devices["living_room_light"]["state"] == "OFF"

        # Polite management phrases must NEVER run the custom command immediately
        for mgmt in ("tôi muốn xóa lệnh chế độ đọc sách", "vui lòng sửa lệnh chế độ đọc sách"):
            assert match_custom_command_with_ambiguity(mgmt, owner_user_id=owner.user_id)["status"] == "none"
            r_mg, _ = asyncio.run(
                process_session_voice_command(engine=engine, session=owner, payload={"transcript": mgmt})
            )
            assert r_mg.get("executed") is not True, f"Management phrase {mgmt!r} executed unexpectedly: {r_mg}"
            assert engine.devices["main_door"]["state"] == "CLOSED"
            assert engine.devices["living_room_light"]["state"] == "OFF"


# ==============================================================================
# CONFIRMATION STILL REQUIRED ONCE FOR ALL MUTATION/ADMIN OPERATIONS
# ==============================================================================


class TestMutationsStillRequireConfirmationAndInvariants:
    def test_mutations_require_confirmation_once(self) -> None:
        engine = SmartHomeEngine()
        owner = _make_user_session("sess_mut_1", "owner_mut", "Chủ Nhà", 1, "ADMIN")
        bridge, _ = _make_live_bridge(engine, owner)

        # Pre-seed a custom command so edit/delete have a target
        seeded = upsert_custom_command(
            phrase="chế độ tối",
            steps=[{"device_id": "living_room_light", "action": "turn_off"}],
            owner_user_id=owner.user_id,
            owner_tier=owner.tier,
            owner_name=owner.display_name,
        )

        # 1. Create custom command
        r1 = _call_live_tool(bridge, "create_custom_scene", {"phrase": "chế độ sáng", "steps_text": "bật đèn phòng khách"})
        assert r1["requires_confirmation"] is True and r1.get("executed") is not True
        assert len(list_custom_commands(include_disabled=False)) == 1

        # 2. Edit custom command (via registry tool)
        r2 = asyncio.run(
            dispatch_tool(
                name="edit_custom_command",
                args={"command_id": seeded["command_id"], "new_phrase": "chế độ tối mới"},
                engine=engine,
                session=owner,
                source="gemini_live",
                session_key="live:sess_mut_1",
            )
        )
        assert r2["requires_confirmation"] is True and r2.get("executed") is not True

        # 3. Delete custom command
        r3 = _call_live_tool(bridge, "delete_automation_item", {"kind": "scene", "keyword_or_id": seeded["command_id"]})
        assert r3["requires_confirmation"] is True and r3.get("executed") is not True
        assert len(list_custom_commands(include_disabled=False)) == 1

        # 4. Create timer
        r4 = _call_live_tool(bridge, "create_timer", {"device_id": "living_room_light", "action": "turn_off", "seconds": 300})
        assert r4["requires_confirmation"] is True and r4.get("executed") is not True
        assert len(list_pending_timers()) == 0

        # 5. Update & Delete timer
        r5a = _call_live_tool(bridge, "update_timer", {"operation": "cancel", "device_id": "living_room_light"})
        assert r5a["requires_confirmation"] is True and r5a.get("executed") is not True
        r5b = _call_live_tool(bridge, "delete_timer", {"device_id": "living_room_light"})
        assert r5b["requires_confirmation"] is True and r5b.get("executed") is not True

        # 6. Create & Delete schedule (confirm create once so delete targets a real saved schedule)
        r6a = _call_live_tool(
            bridge,
            "create_schedule_clock",
            {"device_id": "living_room_light", "action": "turn_on", "time_hhmm": "07:30", "schedule_type": "daily"},
        )
        assert r6a["requires_confirmation"] is True and r6a.get("executed") is not True
        assert len(list_schedules(include_disabled=False)) == 0
        r6_ok = _call_live_tool(bridge, "confirm_or_cancel_pending_action", {"confirmed": True})
        assert r6_ok["ok"] is True and len(list_schedules(include_disabled=False)) == 1
        r6b = _call_live_tool(bridge, "delete_schedule", {"time_hhmm": "07:30"})
        assert r6b["requires_confirmation"] is True and r6b.get("executed") is not True
        assert len(list_schedules(include_disabled=False)) == 1

        # 7. Reset
        r7 = _call_live_tool(bridge, "reset_user_pool", {"pool_kind": "timers"})
        assert r7["requires_confirmation"] is True and r7.get("executed") is not True

        # 8. Create automation rule / link
        r8 = _call_live_tool(
            bridge,
            "set_if_else_rule",
            {
                "when_device_id": "main_door",
                "when_state": "OPEN",
                "then_device_id": "living_room_light",
                "then_action": "turn_on",
            },
        )
        assert r8["requires_confirmation"] is True and r8.get("executed") is not True
        assert len(list_automation_rules(include_disabled=False)) == 0

    @pytest.mark.parametrize("bad_confirmed", ["true", "True", 1, False, None, "yes"])
    def test_confirm_or_cancel_requires_strict_boolean_true(self, bad_confirmed: Any) -> None:
        engine = SmartHomeEngine()
        owner = _make_user_session("sess_strict_1", "owner_strict", "Chủ Nhà", 1, "ADMIN")
        bridge, _ = _make_live_bridge(engine, owner)

        # Test via LiveBridgeSession
        r_stage = _call_live_tool(bridge, "create_custom_scene", {"phrase": "lệnh chặt", "steps_text": "bật đèn phòng khách"})
        assert r_stage["requires_confirmation"] is True
        r_bad = _call_live_tool(bridge, "confirm_or_cancel_pending_action", {"confirmed": bad_confirmed})
        assert r_bad.get("executed") is not True
        assert len(list_custom_commands(include_disabled=False)) == 0

        # Test via unified ai_tool_registry.dispatch_tool
        skey = "reg_strict_key"
        asyncio.run(
            prepare_pending_mutation(
                engine=engine,
                session=owner,
                source="gemini_live",
                session_key=skey,
                action_kind="create_custom_command",
                payload={"phrase": "lệnh chặt 2", "steps": [{"device_id": "living_room_light", "action": "turn_on"}]},
                prompt_summary="Tạo lệnh 'lệnh chặt 2'",
            )
        )
        r_reg_bad = asyncio.run(
            dispatch_tool(
                name="confirm_or_cancel_pending_action",
                args={"confirmed": bad_confirmed},
                engine=engine,
                session=owner,
                source="gemini_live",
                session_key=skey,
            )
        )
        assert r_reg_bad.get("executed") is not True
        assert len(list_custom_commands(include_disabled=False)) == 0

    def test_pending_ttl_at_least_60s_and_new_pending_replaces_old(self) -> None:
        assert PENDING_CONFIRM_TTL_SEC >= 60.0

        engine = SmartHomeEngine()
        owner = _make_user_session("sess_ttl_1", "owner_ttl", "Chủ Nhà", 1, "ADMIN")
        skey = "live:sess_ttl_1"

        # Stage first pending mutation
        asyncio.run(
            prepare_pending_mutation(
                engine=engine,
                session=owner,
                source="gemini_live",
                session_key=skey,
                action_kind="create_custom_command",
                payload={"phrase": "lệnh cũ", "steps": [{"device_id": "living_room_light", "action": "turn_on"}]},
                prompt_summary="Tạo lệnh 'lệnh cũ'",
            )
        )
        # Stage second pending mutation -> MUST replace the old one
        asyncio.run(
            prepare_pending_mutation(
                engine=engine,
                session=owner,
                source="gemini_live",
                session_key=skey,
                action_kind="create_custom_command",
                payload={"phrase": "lệnh mới", "steps": [{"device_id": "bedroom_light", "action": "turn_on"}]},
                prompt_summary="Tạo lệnh 'lệnh mới'",
            )
        )
        pending, expired = get_pending_confirmation(owner_user_id=owner.user_id, session_key=skey)
        assert expired is False
        assert pending is not None
        assert pending["payload"]["phrase"] == "lệnh mới"
        assert float(pending["expires_at"]) - float(pending["created_at"]) >= 60.0

        # Confirming executes ONLY the new pending action
        res = asyncio.run(
            handle_confirmation_reply(
                raw_text="ok",
                engine=engine,
                session=owner,
                source="gemini_live",
                session_key=skey,
            )
        )
        assert res is not None and res["payload"]["ok"] is True
        cmds = list_custom_commands(include_disabled=False)
        assert [c["phrase"] for c in cmds] == ["lệnh mới"]


# ==============================================================================
# RBAC AT EXECUTION TIME & BOARD OFFLINE HTTP 503
# ==============================================================================


class TestCustomCommandRbacAndBoardOffline:
    def test_rbac_guest_denied_and_tier2_restricted_vs_allowed(self) -> None:
        engine = SmartHomeEngine()
        owner = _make_user_session("sess_rbac_1", "owner_rbac", "Chủ Nhà", 1, "ADMIN")
        family = _make_user_session("sess_rbac_2", "family_rbac", "Thành Viên", 2, "FAMILY")
        guest = _make_user_session("sess_rbac_3", "guest_rbac", "Khách", 3, "GUEST")

        # Seed a privileged custom command (main_door) and a family-safe custom command (living_room_light + garden_pump)
        upsert_custom_command(
            phrase="chế độ mở khóa an ninh",
            steps=[{"device_id": "main_door", "action": "open"}],
            owner_user_id=family.user_id,
            owner_tier=family.tier,
            owner_name=family.display_name,
        )
        upsert_custom_command(
            phrase="chế độ cảnh báo khẩn",
            steps=[{"device_id": "alarm_siren", "action": "turn_on"}],
            owner_user_id=family.user_id,
            owner_tier=family.tier,
            owner_name=family.display_name,
        )
        upsert_custom_command(
            phrase="chế độ tưới vườn buổi sáng",
            steps=[
                {"device_id": "living_room_light", "action": "turn_on"},
                {"device_id": "garden_pump", "action": "turn_on"},
            ],
            owner_user_id=family.user_id,
            owner_tier=family.tier,
            owner_name=family.display_name,
        )

        # Cap 3 (Guest) -> 403 denied on LiveBridgeSession & voice command
        guest_bridge, _ = _make_live_bridge(engine, guest)
        r_g_live = _call_live_tool(guest_bridge, "run_custom_command", {"phrase": "chế độ tưới vườn buổi sáng"})
        assert r_g_live.get("status_code") == 403 or r_g_live.get("rbac_blocked") is True
        assert r_g_live.get("executed") is not True

        r_g_voice, st_g_voice = asyncio.run(
            process_session_voice_command(
                engine=engine, session=guest, payload={"transcript": "tạo lệnh test là bật đèn phòng khách"}
            )
        )
        assert st_g_voice == 403 and r_g_voice["ok"] is False

        # Cap 2 (Family) -> 403 denied on main_door and alarm_siren
        family_bridge, _ = _make_live_bridge(engine, family)
        for denied_phrase in ("chế độ mở khóa an ninh", "chế độ cảnh báo khẩn"):
            r_f_deny = _call_live_tool(family_bridge, "run_custom_command", {"phrase": denied_phrase})
            assert r_f_deny.get("status_code") == 403 or r_f_deny.get("rbac_blocked") is True
            assert r_f_deny.get("executed") is not True
            assert engine.devices["main_door"]["state"] == "CLOSED"
            assert engine.devices["alarm_siren"]["state"] == "OFF"

        # Cap 2 (Family) -> ALLOWED immediately (no confirmation) for lights/pump/speaker
        asyncio.run(engine.execute_device_action("living_room_light", "turn_off", bypass_rbac=True))
        asyncio.run(engine.execute_device_action("garden_pump", "turn_off", bypass_rbac=True))
        r_f_ok = _call_live_tool(family_bridge, "run_custom_command", {"phrase": "chế độ tưới vườn buổi sáng"})
        assert r_f_ok["ok"] is True
        assert r_f_ok.get("requires_confirmation") is False
        assert r_f_ok.get("executed") is True
        assert engine.devices["living_room_light"]["state"] == "ON"
        assert engine.devices["garden_pump"]["state"] == "ON"

        # Verify owner can also run privileged command immediately
        owner_bridge, _ = _make_live_bridge(engine, owner)
        r_o_ok = _call_live_tool(owner_bridge, "run_custom_command", {"phrase": "chế độ mở khóa an ninh"})
        assert r_o_ok["ok"] is True and r_o_ok.get("executed") is True
        assert engine.devices["main_door"]["state"] == "OPEN"

    def test_board_offline_returns_503_no_false_success_on_custom_command(self) -> None:
        from backend.engine.board_health import BoardHealthTracker

        engine = SmartHomeEngine()
        owner = _make_user_session("sess_off_1", "owner_off", "Chủ Nhà", 1, "ADMIN")
        asyncio.run(engine.execute_device_action("living_room_light", "turn_off", bypass_rbac=True))
        upsert_custom_command(
            phrase="chế độ tiếp khách",
            steps=[{"device_id": "living_room_light", "action": "turn_on"}],
            owner_user_id=owner.user_id,
            owner_tier=owner.tier,
            owner_name=owner.display_name,
        )

        # Simulate hardware attached then disconnected past heartbeat timeout
        engine.record_board_heartbeat(node_id="esp8266_node_01", persist=False)
        engine.board_health.last_seen = time.time() - (get_board_heartbeat_timeout_sec() + 5.0)
        engine.persist_to_shared_store()
        try:
            r_off, st_off = asyncio.run(
                process_session_voice_command(
                    engine=engine,
                    session=owner,
                    payload={"transcript": "chế độ tiếp khách"},
                )
            )
            assert st_off == 503
            assert r_off["ok"] is False
            assert r_off["executed"] is False
            assert r_off.get("board_offline") is True
            assert engine.devices["living_room_light"]["state"] == "OFF"
            reply = str(r_off.get("exact_spoken_reply") or r_off.get("reply") or "").lower()
            assert "đã bật" not in reply
            assert "mất kết nối" in reply or "ngoại tuyến" in reply
        finally:
            engine.board_health = BoardHealthTracker()
            engine.persist_to_shared_store()


# ==============================================================================
# R4: VAD CONFIG, SERVER STUTTER-GAP DETECTOR & CLIENT JITTER BUFFER / 1450ms VAD
# ==============================================================================


class TestAudioVadStutterAndClientJitterBuffer:
    def test_live_vad_config_and_aoede_vietnamese_settings(self) -> None:
        from google.genai import types

        engine = SmartHomeEngine()
        cfg = make_live_config(engine, strict_lang_fields=True)
        aad = cfg.realtime_input_config.automatic_activity_detection
        assert aad.silence_duration_ms >= 1300
        assert aad.end_of_speech_sensitivity == types.EndSensitivity.END_SENSITIVITY_LOW
        assert aad.prefix_padding_ms >= 200
        assert aad.start_of_speech_sensitivity == types.StartSensitivity.START_SENSITIVITY_HIGH

        pvc = cfg.speech_config.voice_config.prebuilt_voice_config
        assert pvc.voice_name == "Aoede"
        lang_code = getattr(cfg.speech_config, "language_code", None)
        if lang_code is not None:
            assert lang_code == "vi-VN"

    def test_server_stutter_gap_detector_records_gaps_gt_300ms_in_turn_complete(self) -> None:
        engine = SmartHomeEngine()
        owner = _make_user_session("sess_stutter_1", "owner_stutter", "Chủ Nhà", 1, "ADMIN")
        bridge, ws = _make_live_bridge(engine, owner)
        bridge.speech_end_ts = time.perf_counter()

        pcm_frame = b"\x00\x01" * 960  # 40ms @ 24kHz PCM16

        def _audio_msg(pcm: bytes) -> Any:
            return SimpleNamespace(
                server_content=SimpleNamespace(
                    input_transcription=None,
                    output_transcription=None,
                    model_turn=SimpleNamespace(
                        parts=[SimpleNamespace(inline_data=SimpleNamespace(data=pcm))]
                    ),
                    interrupted=False,
                    turn_complete=False,
                ),
                tool_call=None,
            )

        def _turn_complete_msg() -> Any:
            return SimpleNamespace(
                server_content=SimpleNamespace(
                    input_transcription=None,
                    output_transcription=SimpleNamespace(text="Đã bật đèn phòng khách."),
                    model_turn=None,
                    interrupted=False,
                    turn_complete=True,
                ),
                tool_call=None,
            )

        class _FakeGeminiSession:
            def __init__(self, delays_sec: list[float]) -> None:
                self._delays = delays_sec
                self._delivered = False

            async def receive(self) -> Any:
                if self._delivered:
                    bridge._closed = True
                    return
                self._delivered = True
                for idx, d in enumerate(self._delays):
                    if d > 0:
                        await asyncio.sleep(d)
                    yield _audio_msg(pcm_frame)
                yield _turn_complete_msg()
                bridge._closed = True

        class _FakeConnectCtx:
            def __init__(self, delays_sec: list[float]) -> None:
                self._sess = _FakeGeminiSession(delays_sec)

            async def __aenter__(self) -> Any:
                return self._sess

            async def __aexit__(self, *args: Any) -> bool:
                return False

        # Case 1: 360ms gap (> 300ms) -> stutter_count >= 1 & max_chunk_gap_ms > 300
        bridge.client = SimpleNamespace(
            aio=SimpleNamespace(live=SimpleNamespace(connect=lambda **kw: _FakeConnectCtx([0.0, 0.03, 0.36])))
        )
        old_sandbox = os.environ.pop("SIMULATOR_OFFLINE_SANDBOX", None)
        try:
            asyncio.run(bridge.gemini_receive_loop())
        finally:
            if old_sandbox is not None:
                os.environ["SIMULATOR_OFFLINE_SANDBOX"] = old_sandbox

        tc_events = [m for m in ws.sent if m.get("type") == "turn_complete"]
        assert len(tc_events) == 1
        tc = tc_events[0]
        assert tc["audio_chunks"] == 3
        assert len(tc["chunk_gaps_ms"]) == 2
        assert tc["max_chunk_gap_ms"] > 300.0
        assert tc["stutter_count"] >= 1

        # Case 2: Smooth chunks (~20ms gaps) -> stutter_count == 0
        bridge2, ws2 = _make_live_bridge(engine, owner)
        bridge2.speech_end_ts = time.perf_counter()

        class _FakeSmoothSession:
            def __init__(self) -> None:
                self._done = False

            async def receive(self) -> Any:
                if self._done:
                    bridge2._closed = True
                    return
                self._done = True
                for _ in range(3):
                    yield _audio_msg(pcm_frame)
                    await asyncio.sleep(0.02)
                yield _turn_complete_msg()
                bridge2._closed = True

        class _FakeSmoothCtx:
            async def __aenter__(self) -> Any:
                return _FakeSmoothSession()

            async def __aexit__(self, *args: Any) -> bool:
                return False

        bridge2.client = SimpleNamespace(
            aio=SimpleNamespace(live=SimpleNamespace(connect=lambda **kw: _FakeSmoothCtx()))
        )
        old_sandbox = os.environ.pop("SIMULATOR_OFFLINE_SANDBOX", None)
        try:
            asyncio.run(bridge2.gemini_receive_loop())
        finally:
            if old_sandbox is not None:
                os.environ["SIMULATOR_OFFLINE_SANDBOX"] = old_sandbox

        tc2 = [m for m in ws2.sent if m.get("type") == "turn_complete"][0]
        assert tc2["audio_chunks"] == 3
        assert tc2["stutter_count"] == 0
        assert tc2["max_chunk_gap_ms"] < 300.0

    def test_nodejs_client_webaudio_jitter_buffer_and_1450ms_silence_timer(self) -> None:
        assert APP_JS.exists() and MOBILE_APP_JS.exists()
        node_script = r"""
const fs = require('fs');
const appSrc = fs.readFileSync(process.argv[1], 'utf8');
const mobSrc = fs.readFileSync(process.argv[2], 'utf8');

function extractNum(src, name) {
  const m = src.match(new RegExp(`const\\s+${name}\\s*=\\s*([0-9.]+)\\s*;`));
  if (!m) throw new Error(`Missing constant ${name}`);
  return Number(m[1]);
}

const desktopPreroll = extractNum(appSrc, 'AUDIO_INITIAL_PREROLL_SEC');
const desktopSilence = extractNum(appSrc, 'CLIENT_SILENCE_END_MS');
const desktopMaxUtt = extractNum(appSrc, 'CLIENT_MAX_UTTERANCE_MS');
const mobilePreroll = extractNum(mobSrc, 'MOBILE_AUDIO_INITIAL_PREROLL_SEC');
const mobileSilence = extractNum(mobSrc, 'MOBILE_SILENCE_END_MS');
const mobileMaxUtt = extractNum(mobSrc, 'MOBILE_MAX_UTTERANCE_MS');

if (!(desktopPreroll >= 0.08 && mobilePreroll >= 0.08)) {
  throw new Error(`Preroll too small: desktop=${desktopPreroll}, mobile=${mobilePreroll}`);
}
if (!(desktopSilence === 1450 && mobileSilence === 1450)) {
  throw new Error(`Expected 1450ms silence timer, got desktop=${desktopSilence}, mobile=${mobileSilence}`);
}
if (!(desktopMaxUtt >= 15000 && mobileMaxUtt >= 15000)) {
  throw new Error(`Max utterance too short: desktop=${desktopMaxUtt}, mobile=${mobileMaxUtt}`);
}
if (!appSrc.includes('finalizeVoiceAudioTurn') || !mobSrc.includes('finalizeMobileVoiceAudioTurn')) {
  throw new Error('Missing turn_complete telemetry finalizer in app.js or mobile_app.js');
}
if (!appSrc.includes('clearAudioQueue') || !mobSrc.includes('clearMobileAudioQueue')) {
  throw new Error('Missing interrupted audio queue clear handler');
}

// Simulate WebAudio jitter-buffer scheduling with exact preroll rule from app.js
function simulatePlayback(chunkArrivalsMs, chunkDurSec, prerollSec) {
  let nextPlayTime = 0;
  let underrunCount = 0;
  let stutterCount = 0;
  let lastPerf = null;
  let maxGapMs = 0;
  const scheduled = [];

  for (let i = 0; i < chunkArrivalsMs.length; i++) {
    const arrivalMs = chunkArrivalsMs[i];
    const nowSec = arrivalMs / 1000.0;
    if (lastPerf !== null) {
      const gap = arrivalMs - lastPerf;
      if (gap > maxGapMs) maxGapMs = gap;
      if (gap > 300) stutterCount += 1;
    }
    lastPerf = arrivalMs;

    if (nextPlayTime <= nowSec) {
      if (i > 0 && nextPlayTime > 0) {
        underrunCount += 1;
      }
      const leadSec = chunkDurSec >= 0.8 ? (nowSec > 0 ? 0.02 : 0.0) : prerollSec;
      nextPlayTime = nowSec + leadSec;
    }
    scheduled.push(nextPlayTime);
    nextPlayTime += chunkDurSec;
  }
  return { underrunCount, stutterCount, maxGapMs, scheduled };
}

// 1. Network jitter (60-75ms between 80ms chunks): 90ms preroll absorbs jitter cleanly (0 underruns, 0 stutters)
const smoothRes = simulatePlayback([100, 170, 245, 315, 390, 465], 0.08, desktopPreroll);
if (smoothRes.underrunCount !== 0 || smoothRes.stutterCount !== 0) {
  throw new Error(`Expected 0 underrun & 0 stutter on jittered stream, got ${JSON.stringify(smoothRes)}`);
}

// 2. Network stall (380ms gap): records underrun & stutter
const stallRes = simulatePlayback([100, 160, 540, 600], 0.08, desktopPreroll);
if (stallRes.underrunCount < 1 || stallRes.stutterCount < 1) {
  throw new Error(`Expected underrun & stutter on 380ms stall, got ${JSON.stringify(stallRes)}`);
}

// 3. Simulate 1450ms silence timer: 900ms pause mid-sentence must NOT end utterance; 1450ms+ MUST end utterance
function simulateSilenceTimer(silenceEndMs, frameRmsTimeline) {
  let wasSpeaking = false;
  let silenceStartMs = 0;
  const endedAt = [];
  const frameMs = 64.0;
  for (let idx = 0; idx < frameRmsTimeline.length; idx++) {
    const nowMs = idx * frameMs;
    const isSpeech = frameRmsTimeline[idx] > 0.01;
    if (isSpeech) {
      wasSpeaking = true;
      silenceStartMs = 0;
    } else if (wasSpeaking) {
      if (silenceStartMs === 0) silenceStartMs = nowMs - frameMs;
      if (nowMs - silenceStartMs >= silenceEndMs) {
        wasSpeaking = false;
        silenceStartMs = 0;
        endedAt.push(nowMs);
      }
    }
  }
  return endedAt;
}

// 5 speech frames -> 14 silence frames (~896ms pause) -> 5 speech frames -> 25 silence frames (~1600ms)
const timeline = [
  ...Array(5).fill(0.05),
  ...Array(14).fill(0.001),
  ...Array(5).fill(0.05),
  ...Array(25).fill(0.001),
];
const ended = simulateSilenceTimer(desktopSilence, timeline);
if (ended.length !== 1) {
  throw new Error(`Expected exactly 1 speech end after final 1450ms silence, got ${JSON.stringify(ended)}`);
}
if (ended[0] < 24 * 64) {
  throw new Error(`Speech ended prematurely during 900ms mid-sentence pause at ${ended[0]}ms`);
}

console.log(JSON.stringify({
  ok: true,
  desktopPreroll,
  desktopSilence,
  mobilePreroll,
  mobileSilence,
  smoothUnderruns: smoothRes.underrunCount,
  stallUnderruns: stallRes.underrunCount,
  endedAtMs: ended[0],
}));
"""
        proc = subprocess.run(
            ["node", "-e", node_script, str(APP_JS), str(MOBILE_APP_JS)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert proc.returncode == 0, f"Node test failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        assert data["ok"] is True
        assert data["desktopSilence"] == 1450
        assert data["mobileSilence"] == 1450
        assert data["smoothUnderruns"] == 0
        assert data["stallUnderruns"] >= 1


class TestPhase5HumanConvoBugFixes:
    """Regression coverage for the 8 real defects uncovered during Phase 4 human-like QA."""

    def test_dung_lenh_executes_instead_of_deleting(self) -> None:
        engine = SmartHomeEngine()
        engine.devices["main_door"]["state"] = "CLOSED"
        owner = _make_user_session("sess_p5_1", "owner_p5_1", "Chủ Nhà", 1, "ADMIN")
        upsert_custom_command(
            phrase="vừng ơi mở ra",
            steps=[{"device_id": "main_door", "action": "open"}],
            owner_user_id=owner.user_id,
            owner_tier=1,
            owner_name=owner.display_name,
        )
        res = asyncio.run(
            process_automation_nlu_command(
                text="dùng lệnh vừng ơi mở ra",
                engine=engine,
                session=owner,
                source="text_command",
                session_key="p5:1",
            )
        )
        assert res is not None and res["payload"]["ok"] is True
        assert res["payload"]["executed"] is True
        assert res["payload"]["requires_confirmation"] is False
        assert engine.devices["main_door"]["state"] == "OPEN"

    def test_roi_confirms_pending_action(self) -> None:
        engine = SmartHomeEngine()
        owner = _make_user_session("sess_p5_2", "owner_p5_2", "Chủ Nhà", 1, "ADMIN")
        skey = "p5:2"
        asyncio.run(
            prepare_pending_mutation(
                engine=engine,
                session=owner,
                source="text_command",
                session_key=skey,
                action_kind="create_custom_command",
                payload={"phrase": "mở cửa nhanh", "steps": [{"device_id": "living_room_light", "action": "turn_on"}]},
                prompt_summary="Tạo lệnh 'mở cửa nhanh'",
            )
        )
        res = asyncio.run(
            handle_confirmation_reply(
                raw_text="rồi",
                engine=engine,
                session=owner,
                source="text_command",
                session_key=skey,
            )
        )
        assert res is not None and res["payload"]["ok"] is True
        assert any(c["phrase"] == "mở cửa nhanh" for c in list_custom_commands(include_disabled=False))

    def test_create_custom_command_with_house_mode_phrase_not_hijacked(self) -> None:
        from backend.compound_nlu import process_compound_nlu_command

        engine = SmartHomeEngine()
        owner = _make_user_session("sess_p5_3", "owner_p5_3", "Chủ Nhà", 1, "ADMIN")
        res_cmp = asyncio.run(
            process_compound_nlu_command(
                text="Tạo lệnh về nhà rồi là bật đèn phòng khách",
                engine=engine,
                session=owner,
                source="text_command",
                session_key="p5:3",
            )
        )
        assert res_cmp is None, f"House mode must NOT hijack custom command creation: {res_cmp}"

    def test_unsupported_device_reply_is_short_and_exact(self) -> None:
        from backend.compound_nlu import process_compound_nlu_command

        engine = SmartHomeEngine()
        owner = _make_user_session("sess_p5_4", "owner_p5_4", "Chủ Nhà", 1, "ADMIN")
        res = asyncio.run(
            process_compound_nlu_command(
                text="bật máy giặt lên",
                engine=engine,
                session=owner,
                source="text_command",
                session_key="p5:4",
            )
        )
        assert res is not None and res["payload"]["unsupported_device"] is True
        reply = str(res["payload"]["reply"])
        assert len(reply.split()) <= 14, f"Unsupported-device refusal too verbose: {reply!r}"

    def test_elliptical_status_query_and_self_correction_a_thoi(self) -> None:
        from backend.voice.vietnamese_policy import (
            handle_sensor_or_status_query_vi,
            parse_direct_device_intents_vi,
        )

        engine = SmartHomeEngine()
        engine.devices["bedroom_light"]["state"] = "ON"
        owner = _make_user_session("sess_p5_5", "owner_p5_5", "Chủ Nhà", 1, "ADMIN")
        q = handle_sensor_or_status_query_vi("còn đèn phòng ngủ thì sao", engine, owner)
        assert q is not None and "đang bật" in q["reply"].lower()

        intents = parse_direct_device_intents_vi("bật đèn phòng khách... à thôi bật đèn phòng ngủ")
        assert intents == [{"device_id": "bedroom_light", "action": "turn_on"}]

        intents_cancel = parse_direct_device_intents_vi("bật đèn phòng khách... à thôi")
        assert intents_cancel == []

    def test_ws_aoede_speak_denial_preserves_valid_reply_for_authenticated_user(self) -> None:
        from unittest.mock import AsyncMock
        from fastapi import WebSocketDisconnect

        engine = SmartHomeEngine()
        owner = _make_user_session("sess_p5_6", "owner_p5_6", "Chủ Nhà", 1, "ADMIN")
        sent_frames: list[dict[str, Any]] = []
        incoming = [json.dumps({"type": "aoede_speak_denial", "text": "Đã mở cửa chính."})]

        fake_ws = AsyncMock()
        fake_ws.headers = {}
        fake_ws.cookies = {}
        fake_ws.query_params = {}

        async def _recv_text() -> str:
            if incoming:
                return incoming.pop(0)
            raise WebSocketDisconnect(code=1000)

        async def _send_text(raw: str) -> None:
            sent_frames.append(json.loads(raw))

        fake_ws.receive_text = AsyncMock(side_effect=_recv_text)
        fake_ws.send_text = AsyncMock(side_effect=_send_text)

        bridge = LiveBridgeSession(ws=fake_ws, engine=engine.create_isolated_ws_view(), ws_session=owner)
        asyncio.run(bridge.run())
        aoede_reqs = [f for f in sent_frames if f.get("type") == "aoede_voice_request"]
        assert aoede_reqs and aoede_reqs[0].get("spoken_phrase") == "Đã mở cửa chính."

