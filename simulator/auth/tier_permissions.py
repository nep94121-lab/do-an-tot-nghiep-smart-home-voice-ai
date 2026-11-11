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
    "ac": 2,
    "garden_pump": 2,
    "living_room_light": 3,
    "bedroom_light": 3,
    "fan": 3,
}

DEVICE_LABELS_VI: dict[str, str] = {
    "main_door": "Cửa chính",
    "alarm_siren": "Còi báo động",
    "ac": "Điều hòa",
    "garden_pump": "Máy bơm tưới cây",
    "living_room_light": "Đèn phòng khách",
    "bedroom_light": "Đèn phòng ngủ",
    "fan": "Quạt trần",
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
            2: "Thành viên gia đình: đèn, quạt, điều hòa, máy bơm. Không cửa chính, không còi báo động, không tạo mã mời.",
            3: "Khách: chỉ đèn phòng khách, đèn phòng ngủ và quạt trần.",
        },
    }


def enforce_fixed_policy(pol: dict[str, Any] | None) -> dict[str, Any]:
    """Force system_policies.device_min_tiers to the fixed table."""
    data = pol if isinstance(pol, dict) else {}
    data["device_min_tiers"] = dict(DEVICE_MIN_TIER)
    return data
