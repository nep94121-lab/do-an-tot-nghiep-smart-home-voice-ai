"""Fixed permission table for Smart Home session tiers (owner / family / guest).

A session may control a device only when session.tier <= device min_tier.
This table is the server-side source of truth and is not client-writable.
"""
from __future__ import annotations

from typing import Any

# Lower number = higher privilege. 1 owner, 2 family, 3 guest.
DEVICE_MIN_TIER: dict[str, int] = {
    "main_door": 1,
    "alarm_siren": 1,
    "garden_pump": 2,
    "speaker_amp": 2,
    "living_room_light": 3,
    "bedroom_light": 3,
}

DEVICE_LABELS_VI: dict[str, str] = {
    "main_door": "Cửa chính",
    "alarm_siren": "Còi báo động",
    "garden_pump": "Máy bơm tưới cây",
    "speaker_amp": "Nguồn mạch loa PAM8403",
    "living_room_light": "Đèn phòng khách",
    "bedroom_light": "Đèn phòng ngủ",
}

TIER_LABELS_VI: dict[int, str] = {
    1: "Cấp 1 · Chủ nhà",
    2: "Cấp 2 · Thành viên gia đình",
    3: "Cấp 3 · Khách",
}

ROLE_FOR_TIER: dict[int, str] = {1: "ADMIN", 2: "MEMBER", 3: "CHILD_GUEST"}


def min_tier_for_device(device_id: str) -> int:
    key = str(device_id or "").strip()
    return int(DEVICE_MIN_TIER.get(key, 1))


def can_control_device(session_tier: int, device_id: str) -> bool:
    try:
        tier = int(session_tier)
    except (TypeError, ValueError):
        return False
    if tier not in (1, 2, 3):
        return False
    return tier <= min_tier_for_device(device_id)


def devices_visible_for_tier(tier: int) -> list[str]:
    try:
        t = int(tier)
    except (TypeError, ValueError):
        return []
    return [dev_id for dev_id, min_t in DEVICE_MIN_TIER.items() if t <= min_t]


def filter_device_list(devices: list[dict[str, Any]] | None, tier: int) -> list[dict[str, Any]]:
    allowed = set(devices_visible_for_tier(tier))
    out: list[dict[str, Any]] = []
    for dev in devices or []:
        if not isinstance(dev, dict):
            continue
        dev_id = str(dev.get("id") or dev.get("device_id") or "")
        if dev_id in allowed:
            item = dict(dev)
            item["min_tier"] = min_tier_for_device(dev_id)
            out.append(item)
    return out


def permission_table_payload() -> dict[str, Any]:
    rows = []
    for dev_id, min_tier in DEVICE_MIN_TIER.items():
        rows.append(
            {
                "device_id": dev_id,
                "name": DEVICE_LABELS_VI.get(dev_id, dev_id),
                "min_tier": min_tier,
                "tier1_owner": True,
                "tier2_family": min_tier >= 2,
                "tier3_guest": min_tier >= 3,
            }
        )
    return {
        "ok": True,
        "fixed": True,
        "tiers": TIER_LABELS_VI,
        "device_min_tiers": dict(DEVICE_MIN_TIER),
        "devices": rows,
        "notes": {
            1: "Chủ nhà: toàn quyền mọi thiết bị, tạo/thu hồi mã mời, quản lý PIN.",
            2: "Thành viên gia đình: đèn, máy bơm, nguồn mạch loa PAM8403. Không cửa chính, không còi báo động, không tạo mã mời.",
            3: "Khách: chỉ đèn phòng khách và đèn phòng ngủ.",
        },
    }


def enforce_fixed_policy(pol: dict[str, Any] | None) -> dict[str, Any]:
    """Force system_policies.device_min_tiers to the fixed table."""
    data = pol if isinstance(pol, dict) else {}
    data["device_min_tiers"] = dict(DEVICE_MIN_TIER)
    data["tier3_can_schedule_timer"] = False
    data["tier3_can_custom_rules"] = False
    return data


def _resolve_effective_session_tier(
    session: Any,
    *,
    treat_none_as_unauthenticated: bool = True,
) -> tuple[bool, int, str]:
    """Resolve live authenticated tier/user_id; revoked/expired/invalid sessions drop to tier 99."""
    if session is None:
        return (False, 99, "") if treat_none_as_unauthenticated else (True, 1, "")
    if not getattr(session, "is_authenticated", False):
        return False, 99, ""
    if getattr(session, "source", "") in ("unauthenticated", "invalid_token", "rejected_unknown"):
        return False, 99, ""
    if hasattr(session, "is_expired") and hasattr(session, "source") and hasattr(session, "email"):
        from simulator.auth.session_store import session_is_current

        if not session_is_current(session):
            return False, 99, ""
    elif getattr(session, "revoked", False):
        return False, 99, ""
    tier_raw = getattr(session, "tier", 99)
    try:
        tier = int(tier_raw)
    except (TypeError, ValueError):
        return False, 99, ""
    if tier not in (1, 2, 3):
        return False, 99, ""
    uid = str(getattr(session, "user_id", "") or "")
    return True, tier, uid


def _public_snapshot_only(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Strip all private automation, user, policy, and confirmation state for unauthenticated callers."""
    public_devices = []
    for d in (snapshot.get("devices") or []):
        if isinstance(d, dict):
            public_devices.append({
                k: d[k]
                for k in ("id", "name", "type", "state", "gpio", "version", "updated_at")
                if k in d
            })
    pub_mqtt = snapshot.get("mqtt") if isinstance(snapshot.get("mqtt"), dict) else {}
    return {
        "ok": True,
        "authenticated": False,
        "public_only": True,
        "current_tier": 99,
        "role": "UNKNOWN",
        "current_user_id": "",
        "current_user_name": "",
        "revision_seq": snapshot.get("revision_seq", 0),
        "state_revision": snapshot.get("state_revision", snapshot.get("revision_seq", 0)),
        "revision_ts_ns": snapshot.get("revision_ts_ns", 0),
        "vn_time_now": snapshot.get("vn_time_now", ""),
        "server_connected": bool(snapshot.get("server_connected", False)),
        "offline_locked_devices": list(snapshot.get("offline_locked_devices") or ["main_door", "alarm_siren"]),
        "devices": public_devices,
        "mqtt": {
            k: pub_mqtt[k]
            for k in (
                "connected",
                "esp8266",
                "dht11",
                "soil_moisture",
                "esp8266_status",
                "dht11_telemetry",
                "soil_moisture_telemetry",
                "sound",
                "ky037",
                "sound_telemetry",
                "ky037_telemetry",
            )
            if k in pub_mqtt
        },
        **({"sensors": snapshot["sensors"]} if isinstance(snapshot.get("sensors"), dict) else {}),
    }


def restrict_guest_snapshot(
    snapshot: dict[str, Any],
    session: Any,
    *,
    treat_none_as_unauthenticated: bool = True,
) -> dict[str, Any]:
    if session is None and not treat_none_as_unauthenticated:
        return snapshot
    is_valid, tier, uid = _resolve_effective_session_tier(
        session, treat_none_as_unauthenticated=treat_none_as_unauthenticated
    )
    if not is_valid:
        return _public_snapshot_only(snapshot)
    if tier == 1:
        return snapshot

    snap = dict(snapshot)
    snap["devices"] = filter_device_list(list(snap.get("devices") or []), tier)
    snap["allowed_device_ids"] = [device["id"] for device in snap["devices"] if isinstance(device, dict) and device.get("id")]
    allowed_set = set(snap["allowed_device_ids"])
    for key in (
        "users",
        "system_policies",
        "pending_reset_confirmation",
        "pending_rule",
        "pending_voice_enrollment",
        "word_mappings",
        "factory_aliases",
        "custom_aliases",
        "if_else_rules",
        "t1_global_if_else_rules",
        "chains",
    ):
        snap.pop(key, None)
    snap["current_tier"] = tier
    snap["role"] = getattr(session, "role", ROLE_FOR_TIER.get(tier, "CHILD_GUEST"))
    snap["current_user_id"] = uid
    snap["current_user_name"] = str(getattr(session, "display_name", "") or uid)
    snap["role_name"] = f"Tầng {tier} — {snap['current_user_name']} ({snap['role']})"
    sess_email = str(getattr(session, "email", "") or "")
    if sess_email:
        snap["current_user_email"] = sess_email
    else:
        snap.pop("current_user_email", None)
    if isinstance(snap.get("mqtt"), dict):
        pub_mqtt = snap["mqtt"]
        snap["mqtt"] = {
            k: pub_mqtt[k]
            for k in (
                "connected",
                "esp8266",
                "dht11",
                "soil_moisture",
                "esp8266_status",
                "dht11_telemetry",
                "soil_moisture_telemetry",
                "sound",
                "ky037",
                "sound_telemetry",
                "ky037_telemetry",
                "queue_size",
                "max_queue_size",
                "dropped_backpressure_count",
                "retained_topics_count",
            )
            if k in pub_mqtt
        }
    if tier >= 3:
        for priv_key in ("timers", "schedules", "automation_rules", "compound_rules", "custom_commands", "scenes"):
            snap[priv_key] = []
        return snap

    snap["timers"] = [
        timer for timer in (snap.get("timers") or [])
        if isinstance(timer, dict)
        and timer.get("device_id") in allowed_set
        and str(timer.get("owner_user_id") or timer.get("owner_id") or "") == uid
    ]
    snap["schedules"] = [
        sc for sc in (snap.get("schedules") or [])
        if isinstance(sc, dict)
        and sc.get("device_id") in allowed_set
        and str(sc.get("owner_user_id") or sc.get("owner_id") or "") == uid
    ]
    snap["automation_rules"] = [
        rl for rl in (snap.get("automation_rules") or [])
        if isinstance(rl, dict)
        and rl.get("when_device_id") in allowed_set
        and rl.get("then_device_id") in allowed_set
        and str(rl.get("owner_user_id") or rl.get("owner_id") or "") == uid
    ]
    snap["compound_rules"] = [
        rl for rl in (snap.get("compound_rules") or [])
        if isinstance(rl, dict)
        and str(rl.get("owner_user_id") or rl.get("owner_id") or "") == uid
        and all(str(a.get("device_id") or "") in allowed_set for a in (rl.get("actions") or []))
    ]
    visible_scenes = []
    for cmd in (snap.get("custom_commands") or snap.get("scenes") or []):
        if not isinstance(cmd, dict):
            continue
        if str(cmd.get("owner_user_id") or cmd.get("owner_id") or "") != uid:
            continue
        steps = list(cmd.get("steps") or [])
        if steps and all(str(st.get("device_id") or "") in allowed_set for st in steps):
            visible_scenes.append(cmd)
    snap["custom_commands"] = visible_scenes
    snap["scenes"] = visible_scenes
    return snap


_OWNER_SCOPED_WS_EVENTS = frozenset({
    "custom_command_created",
    "custom_command_updated",
    "custom_command_deleted",
    "automation_rule_created",
    "automation_rule_updated",
    "automation_rule_deleted",
    "automation_rule_fired",
    "schedule_created",
    "schedule_updated",
    "schedule_deleted",
    "schedule_fired",
    "timer_created",
    "timer_updated",
    "timer_deleted",
    "timer_scheduled",
    "timer_fired",
    "timer_cancelled",
    "pending_confirmation_created",
    "pending_confirmation_cancelled",
    "pending_confirmation_expired",
    "rule_created",
    "rule_updated",
    "rule_deleted",
    "rule_executed",
    "rule_fired",
    "rule_triggered",
    "rule_confirmation_requested",
    "scene_executed",
    "alias_executed",
    "pool_reset_completed",
})

_TIER1_ONLY_WS_EVENTS = frozenset({
    "member_permission_updated",
    "permission_granted",
    "permission_revoked",
    "query_policy_updated",
    "system_policy_updated",
    "reset_confirmation_requested",
    "factory_reset_completed",
    "mqtt_packet",
    "voice_enrollment_started",
    "voice_enrollment_staged",
    "voice_enrollment_countdown",
    "voice_enrollment_analyzed",
    "start_voice_capture",
    "voice_enrollment_captured",
    "voice_enrollment_rejected_quality",
    "voice_enrollment_rejected_duplicate",
    "voice_enrolled",
})

_DIRECT_SESSION_ONLY_WS_EVENTS = frozenset({
    "rbac_blocked",
    "gemini_status",
    "system_prompt_updated",
    "aoede_voice_request",
    "audio_chunk",
    "interrupted",
    "first_audio_metrics",
    "input_transcription",
    "output_transcription",
    "turn_complete",
    "tool_call_executed",
    "manual_toggle_ack",
    "error",
    "wav_stream_started",
    "speech_ended_marker",
})

_PUBLIC_AUTHENTICATED_WS_EVENTS = frozenset({
    "server_mode_changed",
})

_POOL_DATA_KEYS = frozenset({
    "phrase",
    "steps",
    "command",
    "scene",
    "rule",
    "rules",
    "schedule",
    "schedules",
    "timer",
    "timers",
    "pending",
    "pending_rule",
    "word_mappings",
    "aliases",
    "if_else_rules",
    "custom_commands",
    "automation_rules",
})


def _extract_event_owner_id(event: dict[str, Any]) -> str:
    ev_type = str(event.get("type") or "").strip()
    for key in ("owner_user_id", "owner_id", "target_owner_id"):
        val = str(event.get(key) or "").strip()
        if val:
            return val
    for nested_key in ("command", "scene", "rule", "schedule", "timer", "pending", "pending_rule"):
        nested = event.get(nested_key)
        if isinstance(nested, dict):
            val = str(nested.get("owner_user_id") or nested.get("owner_id") or "").strip()
            if not val and nested_key in ("rule", "pending_rule"):
                val = str(nested.get("user_id") or "").strip()
            if val:
                return val
    schedules_list = event.get("schedules")
    if isinstance(schedules_list, list) and schedules_list:
        owners: set[str] = set()
        for item in schedules_list:
            if not isinstance(item, dict):
                return ""
            o_id = str(item.get("owner_user_id") or item.get("owner_id") or "").strip()
            if not o_id:
                return ""
            owners.add(o_id)
        if len(owners) == 1:
            return next(iter(owners))
        return ""
    if (
        ev_type != "scene_executed"
        and not event.get("actor_user_id")
        and not event.get("executed_by_user_id")
    ):
        val = str(event.get("user_id") or "").strip()
        if val:
            return val
    return ""


def _device_allowed_for_tier(tier: int, device_id: Any) -> bool:
    dev = str(device_id or "").strip()
    if not dev:
        return True
    if dev == "all_lights":
        return tier <= 3
    if dev == "all_devices":
        return tier == 1
    return can_control_device(tier, dev)


def _owner_event_devices_allowed_for_tier(event: dict[str, Any], tier: int) -> bool:
    if not _device_allowed_for_tier(tier, event.get("device_id")):
        return False
    for steps_holder in (event, event.get("command"), event.get("scene")):
        if isinstance(steps_holder, dict):
            steps = steps_holder.get("steps")
            if isinstance(steps, list):
                for st in steps:
                    if isinstance(st, dict) and not _device_allowed_for_tier(tier, st.get("device_id")):
                        return False
    for nested_key in ("schedule", "timer"):
        nested = event.get(nested_key)
        if isinstance(nested, dict) and not _device_allowed_for_tier(tier, nested.get("device_id")):
            return False
    schedules_list = event.get("schedules")
    if isinstance(schedules_list, list):
        for sc in schedules_list:
            if isinstance(sc, dict) and not _device_allowed_for_tier(tier, sc.get("device_id")):
                return False
    for rule_key in ("rule", "pending_rule"):
        rl = event.get(rule_key)
        if isinstance(rl, dict):
            for dk in ("when_device_id", "then_device_id", "else_device_id", "device_id"):
                if not _device_allowed_for_tier(tier, rl.get(dk)):
                    return False
    return True


def filter_ws_event_for_session(
    event: dict[str, Any],
    session: Any,
    *,
    broadcast: bool = False,
) -> dict[str, Any] | None:
    """Filter outbound WS event/snapshot by authenticated session tier and ownership."""
    if not isinstance(event, dict):
        return None
    is_valid, tier, uid = _resolve_effective_session_tier(
        session, treat_none_as_unauthenticated=True
    )
    out = dict(event)
    if isinstance(out.get("snapshot"), dict):
        out["snapshot"] = restrict_guest_snapshot(
            out["snapshot"], session, treat_none_as_unauthenticated=True
        )
    ev_type = str(out.get("type") or "").strip()
    if ev_type == "state_snapshot":
        return out
    if is_valid and tier == 1:
        if broadcast and ev_type in _DIRECT_SESSION_ONLY_WS_EVENTS:
            return None
        return out
    if ev_type == "voice_enrolled":
        if (
            not broadcast
            and isinstance(out.get("result"), dict)
            and out["result"].get("rbac_blocked") is True
            and not any(k in out for k in _POOL_DATA_KEYS)
        ):
            return out
        return None
    if ev_type in _TIER1_ONLY_WS_EVENTS:
        return None
    if ev_type in _OWNER_SCOPED_WS_EVENTS:
        if not is_valid or tier != 2 or not uid:
            return None
        if ev_type == "pool_reset_completed" and bool(out.get("clear_all", False)):
            return None
        owner_id = _extract_event_owner_id(out)
        if not owner_id or owner_id != uid:
            return None
        if not _owner_event_devices_allowed_for_tier(out, tier):
            return None
        return out
    if ev_type in ("device_updated", "device_already_in_state"):
        if not is_valid or any(k in out for k in _POOL_DATA_KEYS):
            return None
        dev_id = str(out.get("device_id") or "").strip()
        if not dev_id or not can_control_device(tier, dev_id):
            return None
        if tier >= 2 and "source" in out and str(out.get("source") or "") != "button_ui":
            out["source"] = "system"
        return out
    if ev_type in _PUBLIC_AUTHENTICATED_WS_EVENTS:
        if not is_valid or any(k in out for k in _POOL_DATA_KEYS):
            return None
        if tier >= 2:
            out.pop("auto_closed_door", None)
            if "message" in out:
                out["message"] = (
                    "Đã kết nối Server Laptop."
                    if out.get("server_connected")
                    else "Đang ở chế độ Mạch Độc Lập (Offline)."
                )
        return out
    if not broadcast and ev_type in _DIRECT_SESSION_ONLY_WS_EVENTS:
        if any(k in out for k in _POOL_DATA_KEYS):
            return None
        if ev_type == "system_prompt_updated" and not is_valid:
            out["system_prompt"] = (
                "Bạn là trợ lý Nhà Thông Minh Bách Khoa. Phiên hiện tại chưa đăng nhập hợp lệ nên không có quyền truy cập dữ liệu riêng tư hay điều khiển thiết bị."
            )
        if ev_type == "tool_call_executed":
            if not is_valid:
                return None
            if isinstance(out.get("result"), dict):
                res_copy = dict(out["result"])
                if isinstance(res_copy.get("snapshot"), dict):
                    res_copy["snapshot"] = restrict_guest_snapshot(
                        res_copy["snapshot"], session, treat_none_as_unauthenticated=True
                    )
                out["result"] = res_copy
        return out
    return None
