"""Canonical unified AI tool registry shared by Gemini Live and typed text NLU."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

from google.genai import types

from simulator.auth.tier_permissions import DEVICE_LABELS_VI, can_control_device
from simulator.automation_engine import (
    CANONICAL_6_DEVICES,
    REMOVED_DEVICE_HINT_VI,
    clear_compound_rules_scoped,
    create_compound_rule,
    delete_compound_rule,
    format_compound_rule_vi,
    format_weekdays_vi,
    get_compound_rule,
    list_compound_rules,
    normalize_weekdays,
    toggle_compound_rule,
    update_compound_rule,
    validate_compound_rule_input,
)
from simulator.automation_nlu import (
    _deny_mutation_error,
    _expand_targets,
    _resolve_session_key,
    _session_actor,
    handle_confirmation_reply,
    parse_multi_steps_from_text,
    prepare_pending_mutation,
)
from simulator.automation_repo import (
    GUEST_ONLY_TOGGLE_MSG_VI,
    _normalize_steps,
    _parse_hhmm_parts,
    can_user_create_links,
    check_steps_rbac,
    check_tier1_schedule_conflict,
    compute_candidate_schedule_state,
    delete_automation_rule,
    find_custom_command_by_text,
    format_device_action_vi,
    format_duration_vi,
    list_automation_rules,
    list_custom_commands,
    list_pending_timers,
    list_schedules,
    normalize_phrase,
    reset_custom_commands_scoped,
    reset_links_scoped,
    reset_timers_and_schedules_scoped,
    update_schedule,
    validate_automation_rule_input,
)
from simulator.engine.audit_logger import append_audit_log
from simulator.engine.constants_and_time import ACTION_TO_STATE, DEFAULT_DEVICES
from simulator.ui_registry import get_ui_guidance as _get_ui_guidance_from_registry

DEVICE_ENUM = list(CANONICAL_6_DEVICES)
DEVICE_OR_GROUP_ENUM = list(CANONICAL_6_DEVICES) + ["all_lights", "all_devices"]
ACTION_ENUM = ["open", "close", "turn_on", "turn_off"]
CONDITION_SOURCE_ENUM = list(CANONICAL_6_DEVICES) + [
    "temp_sensor",
    "humidity_sensor",
    "soil_sensor",
    "sound_sensor",
    "time_window",
    "house_mode",
]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    requires_confirmation: bool
    category: str


_CONDITION_ITEM_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "source": {
            "type": "STRING",
            "enum": CONDITION_SOURCE_ENUM,
            "description": (
                "Nguồn điều kiện: cảm biến (temp_sensor, humidity_sensor, soil_sensor, sound_sensor), "
                "thiết bị trong 6 thiết bị hỗ trợ, khung giờ (time_window) hoặc chế độ nhà (house_mode)."
            ),
        },
        "operator": {
            "type": "STRING",
            "enum": [">", ">=", "<", "<=", "==", "!="],
            "description": "Toán tử so sánh số cho cảm biến nhiệt độ, độ ẩm không khí hoặc độ ẩm đất.",
        },
        "value": {
            "type": "NUMBER",
            "description": "Giá trị ngưỡng số tương ứng với toán tử so sánh.",
        },
        "state": {
            "type": "STRING",
            "description": (
                "Trạng thái điều kiện: OPEN/CLOSED (cửa chính), ON/OFF (5 thiết bị còn lại), "
                "HIGH/LOW (nhiệt độ, độ ẩm không khí), DRY/WET (độ ẩm đất), LOUD/QUIET (âm thanh), "
                "HOME/AWAY (chế độ nhà)."
            ),
        },
        "start_hhmm": {
            "type": "STRING",
            "description": "Giờ bắt đầu HH:MM cho điều kiện khung giờ (hỗ trợ qua nửa đêm).",
        },
        "end_hhmm": {
            "type": "STRING",
            "description": "Giờ kết thúc HH:MM cho điều kiện khung giờ.",
        },
        "weekdays": {
            "type": "ARRAY",
            "items": {"type": "INTEGER"},
            "description": "Danh sách thứ trong tuần áp dụng (0=Thứ 2 đến 6=Chủ nhật).",
        },
        "hysteresis": {
            "type": "NUMBER",
            "description": "Độ rộng vùng trễ chống bật tắt liên tục quanh ngưỡng cảm biến.",
        },
    },
    "required": ["source"],
}

_ACTION_ITEM_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "device_id": {
            "type": "STRING",
            "enum": DEVICE_OR_GROUP_ENUM,
            "description": "Mã thiết bị chấp hành thuộc 6 thiết bị hoặc nhóm thiết bị hợp lệ.",
        },
        "action": {
            "type": "STRING",
            "enum": ACTION_ENUM,
            "description": "Hành động: open, close, turn_on hoặc turn_off.",
        },
    },
    "required": ["device_id", "action"],
}


TOOL_REGISTRY: tuple[ToolSpec, ...] = (
    # --- Devices / Sensors / Presence ---
    ToolSpec(
        name="list_devices",
        description="Liệt kê các thiết bị trong phạm vi quyền của người dùng kèm trạng thái hiện tại.",
        parameters={"type": "OBJECT", "properties": {}},
        requires_confirmation=False,
        category="devices",
    ),
    ToolSpec(
        name="get_device_state",
        description="Đọc trạng thái chi tiết của một thiết bị cụ thể trong danh mục 6 thiết bị.",
        parameters={
            "type": "OBJECT",
            "properties": {"device_id": {"type": "STRING", "enum": DEVICE_ENUM}},
            "required": ["device_id"],
        },
        requires_confirmation=False,
        category="devices",
    ),
    ToolSpec(
        name="control_device",
        description="Bật, tắt, mở hoặc đóng trực tiếp thiết bị trong danh mục 6 thiết bị ngay sau khi kiểm tra phân quyền.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "device_id": {"type": "STRING", "enum": DEVICE_OR_GROUP_ENUM},
                "action": {"type": "STRING", "enum": ACTION_ENUM},
            },
            "required": ["device_id", "action"],
        },
        requires_confirmation=False,
        category="devices",
    ),
    ToolSpec(
        name="set_device",
        description="Điều khiển bật/tắt/mở/đóng hoặc đặt độ sáng đèn trực tiếp sau khi kiểm tra quyền.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "device_id": {"type": "STRING", "enum": DEVICE_ENUM},
                "action": {"type": "STRING", "enum": ["turn_on", "turn_off", "open", "close", "set_value"]},
                "brightness_pct": {"type": "INTEGER", "description": "Độ sáng từ 0 đến 100 cho đèn."},
            },
            "required": ["device_id"],
        },
        requires_confirmation=False,
        category="devices",
    ),
    ToolSpec(
        name="read_sensors",
        description="Đọc toàn bộ giá trị 3 cảm biến hiện tại gồm nhiệt độ, độ ẩm không khí, độ ẩm đất và cảm biến âm thanh.",
        parameters={"type": "OBJECT", "properties": {}},
        requires_confirmation=False,
        category="sensors",
    ),
    ToolSpec(
        name="set_or_query_sensors",
        description="Đọc hoặc mô phỏng cập nhật giá trị cảm biến nhiệt độ, độ ẩm không khí hoặc độ ẩm đất.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "operation": {"type": "STRING", "enum": ["query", "set"]},
                "temp_c": {"type": "NUMBER"},
                "humidity_pct": {"type": "NUMBER"},
                "soil_moisture_pct": {"type": "NUMBER"},
            },
            "required": ["operation"],
        },
        requires_confirmation=False,
        category="sensors",
    ),
    ToolSpec(
        name="set_house_mode",
        description="Chuyển đổi trạng thái hiện diện của ngôi nhà giữa chế độ ở nhà (HOME) và vắng nhà (AWAY), đồng thời đánh giá các luật tự động liên quan.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "mode": {
                    "type": "STRING",
                    "enum": ["HOME", "AWAY"],
                    "description": "HOME (ở nhà) hoặc AWAY (vắng nhà).",
                },
            },
            "required": ["mode"],
        },
        requires_confirmation=False,
        category="presence",
    ),
    # --- Timers ---
    ToolSpec(
        name="create_timer",
        description="Tạo hẹn giờ đếm ngược cho thiết bị và lưu nháp hỏi xác nhận bằng tiếng Việt tự nhiên trước khi kích hoạt.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "device_id": {"type": "STRING", "enum": DEVICE_OR_GROUP_ENUM},
                "action": {"type": "STRING", "enum": ACTION_ENUM},
                "hours": {"type": "NUMBER"},
                "minutes": {"type": "NUMBER"},
                "seconds": {"type": "NUMBER"},
                "repeat": {"type": "STRING", "enum": ["once", "daily", "weekly", "hourly", "monthly"]},
            },
            "required": ["device_id", "action"],
        },
        requires_confirmation=True,
        category="timers",
    ),
    ToolSpec(
        name="list_timers",
        description="Liệt kê các hẹn giờ đếm ngược đang chờ chạy trong phạm vi quyền của người dùng.",
        parameters={"type": "OBJECT", "properties": {}},
        requires_confirmation=False,
        category="timers",
    ),
    ToolSpec(
        name="edit_timer",
        description="Chỉnh sửa thời gian hoặc hành động của một hẹn giờ đếm ngược đang chờ chạy và hỏi xác nhận trước khi lưu.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "timer_id": {"type": "STRING", "description": "Mã hẹn giờ cần sửa (tùy chọn nếu đã chỉ định thiết bị)."},
                "device_id": {"type": "STRING", "enum": DEVICE_OR_GROUP_ENUM},
                "new_action": {"type": "STRING", "enum": ACTION_ENUM},
                "hours": {"type": "NUMBER"},
                "minutes": {"type": "NUMBER"},
                "seconds": {"type": "NUMBER"},
                "repeat": {"type": "STRING", "enum": ["once", "daily", "weekly", "hourly", "monthly"]},
            },
        },
        requires_confirmation=True,
        category="timers",
    ),
    ToolSpec(
        name="delete_timer",
        description="Hủy một hẹn giờ đếm ngược theo mã hoặc thiết bị, hỏi xác nhận trước khi xóa.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "timer_id": {"type": "STRING"},
                "device_id": {"type": "STRING", "enum": DEVICE_OR_GROUP_ENUM},
            },
        },
        requires_confirmation=True,
        category="timers",
    ),
    # --- Schedules ---
    ToolSpec(
        name="create_schedule",
        description=(
            "Tạo lịch đồng hồ theo giờ Việt Nam (một lần, hằng ngày hoặc lặp theo các thứ trong tuần). "
            "Lưu bản nháp và hỏi xác nhận trước khi ghi."
        ),
        parameters={
            "type": "OBJECT",
            "properties": {
                "device_id": {"type": "STRING", "enum": DEVICE_ENUM},
                "action": {"type": "STRING", "enum": ACTION_ENUM},
                "time_hhmm": {"type": "STRING", "description": "Giờ 24h dạng HH:MM theo múi giờ Việt Nam."},
                "schedule_type": {"type": "STRING", "enum": ["once", "daily", "weekly"]},
                "weekdays": {
                    "type": "ARRAY",
                    "items": {"type": "INTEGER"},
                    "description": "Các thứ lặp lại trong tuần (0=Thứ 2 đến 6=Chủ nhật).",
                },
                "run_date_vn": {"type": "STRING", "description": "Ngày chạy YYYY-MM-DD nếu là lịch một lần."},
                "label": {"type": "STRING"},
            },
            "required": ["device_id", "action", "time_hhmm"],
        },
        requires_confirmation=True,
        category="schedules",
    ),
    ToolSpec(
        name="list_schedules",
        description="Đọc danh sách lịch đồng hồ (bao gồm cả trạng thái bật/tắt và các thứ lặp lại) trong phạm vi quyền của người dùng.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "include_disabled": {"type": "BOOLEAN", "description": "True để xem cả lịch đang tạm tắt."},
            },
        },
        requires_confirmation=False,
        category="schedules",
    ),
    ToolSpec(
        name="edit_schedule",
        description="Chỉnh sửa giờ, thiết bị, hành động, chế độ lặp hoặc các thứ trong tuần của một lịch đồng hồ và hỏi xác nhận trước khi lưu.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "schedule_id": {"type": "STRING"},
                "device_id": {"type": "STRING", "enum": DEVICE_ENUM},
                "action": {"type": "STRING", "enum": ACTION_ENUM},
                "time_hhmm": {"type": "STRING"},
                "schedule_type": {"type": "STRING", "enum": ["once", "daily", "weekly"]},
                "weekdays": {"type": "ARRAY", "items": {"type": "INTEGER"}},
                "enabled": {"type": "BOOLEAN"},
                "label": {"type": "STRING"},
            },
        },
        requires_confirmation=True,
        category="schedules",
    ),
    ToolSpec(
        name="toggle_schedule",
        description="Bật hoặc tạm tắt một lịch đồng hồ hiện có theo mã lịch hoặc giờ/thiết bị, hỏi xác nhận trước khi áp dụng.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "schedule_id": {"type": "STRING"},
                "time_hhmm": {"type": "STRING"},
                "device_id": {"type": "STRING", "enum": DEVICE_ENUM},
                "enabled": {"type": "BOOLEAN", "description": "True để bật lịch, False để tạm tắt lịch."},
            },
            "required": ["enabled"],
        },
        requires_confirmation=True,
        category="schedules",
    ),
    ToolSpec(
        name="delete_schedule",
        description="Xóa một lịch đồng hồ theo mã lịch hoặc giờ/thiết bị, hỏi xác nhận trước khi xóa.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "schedule_id": {"type": "STRING"},
                "time_hhmm": {"type": "STRING"},
                "device_id": {"type": "STRING", "enum": DEVICE_ENUM},
            },
        },
        requires_confirmation=True,
        category="schedules",
    ),
    # --- Custom Commands ---
    ToolSpec(
        name="create_custom_command",
        description="Tạo lệnh tùy chỉnh (kịch bản nhiều thiết bị) theo tên khẩu lệnh và danh sách bước hành động; hỏi xác nhận trước khi lưu.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "phrase": {"type": "STRING", "description": "Tên khẩu lệnh kích hoạt."},
                "steps": {"type": "ARRAY", "items": _ACTION_ITEM_SCHEMA},
                "steps_text": {"type": "STRING", "description": "Mô tả tiếng Việt các hành động nếu không truyền mảng steps."},
            },
            "required": ["phrase"],
        },
        requires_confirmation=True,
        category="custom_commands",
    ),
    ToolSpec(
        name="list_custom_commands",
        description="Liệt kê các lệnh tùy chỉnh (kịch bản nhiều bước) đã lưu trong phạm vi quyền của người dùng.",
        parameters={
            "type": "OBJECT",
            "properties": {"include_disabled": {"type": "BOOLEAN"}},
        },
        requires_confirmation=False,
        category="custom_commands",
    ),
    ToolSpec(
        name="run_custom_command",
        description="Chạy một lệnh tùy chỉnh đã lưu theo tên khẩu lệnh hoặc mã lệnh; hỏi xác nhận trước khi thực thi.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "command_id": {"type": "STRING"},
                "phrase": {"type": "STRING"},
            },
        },
        requires_confirmation=True,
        category="custom_commands",
    ),
    ToolSpec(
        name="edit_custom_command",
        description="Sửa tên khẩu lệnh, danh sách bước hành động hoặc trạng thái bật/tắt của lệnh tùy chỉnh; hỏi xác nhận trước khi lưu.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "command_id": {"type": "STRING"},
                "phrase": {"type": "STRING", "description": "Tên khẩu lệnh hiện tại hoặc mới."},
                "new_phrase": {"type": "STRING"},
                "steps": {"type": "ARRAY", "items": _ACTION_ITEM_SCHEMA},
                "steps_text": {"type": "STRING"},
                "enabled": {"type": "BOOLEAN"},
            },
        },
        requires_confirmation=True,
        category="custom_commands",
    ),
    ToolSpec(
        name="delete_custom_command",
        description="Xóa một lệnh tùy chỉnh theo mã lệnh hoặc tên khẩu lệnh; hỏi xác nhận trước khi xóa.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "command_id": {"type": "STRING"},
                "phrase": {"type": "STRING"},
            },
        },
        requires_confirmation=True,
        category="custom_commands",
    ),
    # --- Compound & Simple Automation Rules ---
    ToolSpec(
        name="create_automation_rule",
        description=(
            "Tạo luật tự động đơn giản hoặc phức hợp kết hợp nhiều điều kiện bằng AND/OR "
            "(cảm biến có ngưỡng số hoặc trạng thái, thiết bị, khung giờ, chế độ nhà) với một hoặc nhiều hành động thiết bị, "
            "kèm chống vòng lặp, vùng trễ ngưỡng và thời gian nghỉ. Luôn đọc lại toàn bộ điều kiện và hành động để người dùng xác nhận."
        ),
        parameters={
            "type": "OBJECT",
            "properties": {
                "name": {"type": "STRING"},
                "logic": {"type": "STRING", "enum": ["AND", "OR"], "description": "AND (đồng thời thỏa tất cả) hoặc OR (chỉ cần một điều kiện đúng)."},
                "conditions": {"type": "ARRAY", "items": _CONDITION_ITEM_SCHEMA},
                "actions": {"type": "ARRAY", "items": _ACTION_ITEM_SCHEMA},
                "else_actions": {"type": "ARRAY", "items": _ACTION_ITEM_SCHEMA},
                "cooldown_seconds": {"type": "NUMBER", "description": "Khoảng nghỉ tối thiểu giữa hai lần kích hoạt (giây)."},
                "hysteresis": {"type": "NUMBER", "description": "Vùng trễ ngưỡng tùy chọn ghi đè mặc định."},
                "label": {"type": "STRING"},
            },
            "required": ["conditions", "actions"],
        },
        requires_confirmation=True,
        category="rules",
    ),
    ToolSpec(
        name="list_automation_rules",
        description="Liệt kê tất cả luật tự động (cả luật phức hợp lẫn luật liên kết đơn giản) trong phạm vi quyền của người dùng.",
        parameters={
            "type": "OBJECT",
            "properties": {"include_disabled": {"type": "BOOLEAN"}},
        },
        requires_confirmation=False,
        category="rules",
    ),
    ToolSpec(
        name="edit_automation_rule",
        description="Chỉnh sửa điều kiện, logic AND/OR, hành động, độ trễ hoặc tên của một luật tự động hiện có và đọc lại luật mới để xác nhận.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "rule_id": {"type": "STRING"},
                "keyword": {"type": "STRING", "description": "Từ khóa tìm luật nếu chưa biết mã rule_id."},
                "name": {"type": "STRING"},
                "logic": {"type": "STRING", "enum": ["AND", "OR"]},
                "conditions": {"type": "ARRAY", "items": _CONDITION_ITEM_SCHEMA},
                "actions": {"type": "ARRAY", "items": _ACTION_ITEM_SCHEMA},
                "else_actions": {"type": "ARRAY", "items": _ACTION_ITEM_SCHEMA},
                "cooldown_seconds": {"type": "NUMBER"},
                "hysteresis": {"type": "NUMBER"},
                "enabled": {"type": "BOOLEAN"},
                "label": {"type": "STRING"},
            },
        },
        requires_confirmation=True,
        category="rules",
    ),
    ToolSpec(
        name="toggle_automation_rule",
        description="Bật hoặc tạm tắt một luật tự động theo mã luật hoặc từ khóa mô tả; hỏi xác nhận trước khi thay đổi.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "rule_id": {"type": "STRING"},
                "keyword": {"type": "STRING"},
                "enabled": {"type": "BOOLEAN", "description": "True để bật luật, False để tạm tắt luật."},
            },
            "required": ["enabled"],
        },
        requires_confirmation=True,
        category="rules",
    ),
    ToolSpec(
        name="delete_automation_rule",
        description="Xóa một luật tự động (đơn giản hoặc phức hợp) theo mã luật hoặc từ khóa; hỏi xác nhận trước khi xóa.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "rule_id": {"type": "STRING"},
                "keyword": {"type": "STRING"},
                "device_id": {"type": "STRING", "enum": DEVICE_OR_GROUP_ENUM},
            },
        },
        requires_confirmation=True,
        category="rules",
    ),
    # --- Reset & Confirmation ---
    ToolSpec(
        name="reset_automations",
        description=(
            "Đặt lại một phần hoặc toàn bộ tự động hóa theo phạm vi (timers, schedules, custom_commands, rules, all, devices, factory). "
            "Luôn hỏi xác nhận trước khi thực hiện."
        ),
        parameters={
            "type": "OBJECT",
            "properties": {
                "scope": {
                    "type": "STRING",
                    "enum": ["timers", "schedules", "custom_commands", "rules", "all", "devices", "factory"],
                    "description": "Phạm vi cần đặt lại.",
                },
                "clear_all_users": {
                    "type": "BOOLEAN",
                    "description": "(Chỉ Cấp 1) True nếu đặt lại dữ liệu của toàn bộ thành viên.",
                },
            },
            "required": ["scope"],
        },
        requires_confirmation=True,
        category="reset",
    ),
    ToolSpec(
        name="confirm_or_cancel_pending_action",
        description="Xác nhận hoặc hủy thao tác tự động hóa đang chờ xác nhận trong phiên hiện tại.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "confirmed": {"type": "BOOLEAN"},
            },
            "required": ["confirmed"],
        },
        requires_confirmation=False,
        category="confirmation",
    ),
    # --- UI Guidance ---
    ToolSpec(
        name="get_ui_guidance",
        description=(
            "Tra cứu hướng dẫn vị trí trang, thanh điều hướng, khung chức năng, tab và tên nút bấm trên giao diện web "
            "từ danh mục giao diện chuẩn của hệ thống."
        ),
        parameters={
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Câu hỏi hoặc nội dung tính năng người dùng cần tìm trên giao diện."},
                "topic": {
                    "type": "STRING",
                    "description": "Chủ đề giao diện tùy chọn (timers, schedules, custom_commands, rules, devices, sensors, voice, house_mode, auth, qr_invite, logs, hardware, reset, automation_overview).",
                },
            },
        },
        requires_confirmation=False,
        category="ui_guidance",
    ),
)

TOOL_SPECS_BY_NAME: dict[str, ToolSpec] = {spec.name: spec for spec in TOOL_REGISTRY}


def get_tool_specs() -> list[dict[str, Any]]:
    """Return structured JSON-serializable metadata for all canonical AI tools."""
    return [
        {
            "name": s.name,
            "description": s.description,
            "parameters": s.parameters,
            "requires_confirmation": s.requires_confirmation,
            "category": s.category,
        }
        for s in TOOL_REGISTRY
    ]


def build_gemini_function_declarations() -> list[types.FunctionDeclaration]:
    """Build Google GenAI FunctionDeclaration objects directly from TOOL_REGISTRY."""
    decls: list[types.FunctionDeclaration] = []
    for spec in TOOL_REGISTRY:
        fd = types.FunctionDeclaration(
            name=spec.name,
            description=spec.description,
            parameters=spec.parameters,
        )
        if hasattr(types, "Behavior"):
            fd.behavior = types.Behavior.BLOCKING
        decls.append(fd)
    return decls


def _wrap_payload(payload: dict[str, Any], status_code: int = 200) -> dict[str, Any]:
    out = dict(payload)
    out.setdefault("status_code", int(status_code))
    spoken = str(
        out.get("exact_spoken_reply")
        or out.get("reply")
        or out.get("error")
        or ""
    ).strip()
    if spoken:
        out.setdefault("reply", spoken)
        out.setdefault("exact_spoken_reply", spoken)
        out.setdefault("message", spoken)
        out.setdefault("instruction_for_ai", f"BẮT BUỘC nói ngắn gọn, đúng ý bằng tiếng Việt: '{spoken}'")
    return out


def _err_resp(msg: str, *, status_code: int = 400, rbac_blocked: bool = False, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return _wrap_payload(
        {
            "ok": False,
            "rbac_blocked": rbac_blocked or status_code == 403,
            "error": msg,
            "reply": msg,
            "exact_spoken_reply": msg,
            **(extra or {}),
        },
        status_code=status_code,
    )


def _match_compound_or_simple_rule(
    *,
    rule_id: str = "",
    keyword: str = "",
    device_id: str = "",
    actor_uid: str = "",
    actor_tier: int = 1,
) -> tuple[bool, dict[str, Any] | None]:
    """Find matching rule across compound_automation_rules first, then legacy automation_rules.

    Returns (is_compound, rule_dict_or_None).
    """
    rid = str(rule_id or "").strip()
    kw_norm = normalize_phrase(keyword)
    owner_filter = None if actor_tier == 1 else actor_uid

    comp_rules = list_compound_rules(include_disabled=True, owner_user_id=owner_filter)
    if rid:
        hit = next((r for r in list_compound_rules(include_disabled=True) if r["rule_id"] == rid), None)
        if hit is not None:
            return True, hit
    if kw_norm:
        for r in comp_rules:
            hay = normalize_phrase(f"{r.get('name', '')} {r.get('label', '')} {r.get('rule_id', '')}")
            if kw_norm in hay:
                return True, r
    if device_id and not rid:
        for r in comp_rules:
            devs = {c.get("source") for c in (r.get("conditions") or [])} | {
                a.get("device_id") for a in (r.get("actions") or [])
            }
            if device_id in devs:
                return True, r

    simple_rules = list_automation_rules(include_disabled=True, owner_user_id=owner_filter)
    if rid:
        hit_s = next((r for r in list_automation_rules(include_disabled=True) if r["rule_id"] == rid), None)
        if hit_s is not None:
            return False, hit_s
    if kw_norm:
        for r in simple_rules:
            hay = normalize_phrase(f"{r.get('label', '')} {r.get('rule_id', '')}")
            if kw_norm in hay:
                return False, r
    if device_id:
        for r in simple_rules:
            if r.get("when_device_id") == device_id or r.get("then_device_id") == device_id:
                return False, r

    if not rid and not kw_norm and not device_id:
        if len(comp_rules) == 1 and not simple_rules:
            return True, comp_rules[0]
        if len(simple_rules) == 1 and not comp_rules:
            return False, simple_rules[0]
    return True, None


def _toggle_legacy_simple_rule(rule_id: str, enabled: bool) -> bool:
    from simulator.database_sqlite import _DB_LOCK, get_connection
    from simulator.automation_repo import _resolve_db, invalidate_automation_cache
    from simulator.db_migrations import run_write_transaction
    import json as _json

    now_ts = time.time()
    with _DB_LOCK:
        target = _resolve_db()
        conn = get_connection(target)
        try:
            def _tx(c: Any) -> int:
                cur = c.execute(
                    "UPDATE automation_rules SET enabled = ?, updated_at = ? WHERE rule_id = ?",
                    (1 if enabled else 0, now_ts, str(rule_id)),
                )
                if int(cur.rowcount or 0) > 0:
                    return 1
                row = c.execute(
                    "SELECT else_action FROM rules_pool WHERE rule_id = ? AND rule_category = 'sensor_link'",
                    (str(rule_id),),
                ).fetchone()
                if row is not None:
                    try:
                        meta = _json.loads(str(row["else_action"] or "{}"))
                    except Exception:
                        meta = {}
                    if not isinstance(meta, dict):
                        meta = {}
                    meta["enabled"] = bool(enabled)
                    meta["updated_at"] = now_ts
                    c.execute(
                        "UPDATE rules_pool SET else_action = ? WHERE rule_id = ?",
                        (_json.dumps(meta, ensure_ascii=False), str(rule_id)),
                    )
                    return 1
                return 0

            changed = run_write_transaction(conn, _tx) > 0
        finally:
            conn.close()
    if changed:
        invalidate_automation_cache()
    return changed


# =============================================================================
# EXTENDED CONFIRMED MUTATION EXECUTOR
# =============================================================================


async def execute_extended_confirmed_mutation(
    *,
    engine: Any,
    session: Any,
    source: str,
    action_kind: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """Execute newly added confirmed automation mutations cleanly (called from execute_confirmed_mutation)."""
    user_id, tier, user_name, role = _session_actor(session)
    if tier >= 3:
        return _deny_mutation_error(
            session=session,
            source=source,
            category=f"rbac_deny_{action_kind}",
            msg=GUEST_ONLY_TOGGLE_MSG_VI,
            status_code=403,
            target=action_kind,
        )

    if action_kind == "create_compound_rule":
        try:
            rule = create_compound_rule(
                owner_user_id=user_id,
                owner_tier=tier,
                owner_name=user_name,
                name=str(payload.get("name") or ""),
                logic=str(payload.get("logic") or "AND"),
                conditions=list(payload.get("conditions") or []),
                actions=list(payload.get("actions") or []),
                else_actions=list(payload.get("else_actions") or []),
                cooldown_seconds=float(payload.get("cooldown_seconds") if payload.get("cooldown_seconds") is not None else 10.0),
                hysteresis=payload.get("hysteresis"),
                label=str(payload.get("label") or ""),
                enabled=bool(payload.get("enabled", True)),
                engine=engine,
            )
        except PermissionError as exc:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_compound_rule",
                msg=str(exc),
                status_code=403,
                target="compound_rules",
            )
        except ValueError as exc:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="invalid_compound_rule",
                msg=str(exc),
                status_code=400,
                target="compound_rules",
            )
        engine.sync_automation_pools_from_sqlite(emit_snapshot=False)
        append_audit_log("AUTOMATION", "compound_rule_created", f"Tạo luật phức hợp {rule['rule_id']} ({rule['label']})", user_name=user_name, tier=tier)
        await engine.emit({"type": "automation_rule_created", "rule": rule, "is_compound": True})
        snap = engine.get_snapshot(session=session, sync=False)
        spoken = "Đã xác nhận. Đã lưu luật tự động rồi ạ."
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "confirmed": True,
                "kind": "compound_rule_created",
                "rule": rule,
                "compound_rules": snap.get("compound_rules", []),
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": snap,
            },
        }

    if action_kind == "update_compound_rule":
        rid = str(payload.get("rule_id") or "").strip()
        try:
            updated = update_compound_rule(
                rid,
                name=payload.get("name"),
                logic=payload.get("logic"),
                conditions=payload.get("conditions"),
                actions=payload.get("actions"),
                else_actions=payload.get("else_actions"),
                cooldown_seconds=payload.get("cooldown_seconds"),
                hysteresis=payload.get("hysteresis"),
                enabled=payload.get("enabled"),
                label=payload.get("label"),
                actor_user_id=user_id,
                actor_tier=tier,
                engine=engine,
            )
        except PermissionError as exc:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_update_compound_rule",
                msg=str(exc),
                status_code=403,
                target=rid,
            )
        except ValueError as exc:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="invalid_update_compound_rule",
                msg=str(exc),
                status_code=400,
                target=rid,
            )
        if updated is None:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="compound_rule_not_found",
                msg="Không tìm thấy luật tự động cần sửa.",
                status_code=404,
                target=rid,
            )
        engine.sync_automation_pools_from_sqlite(emit_snapshot=False)
        append_audit_log("AUTOMATION", "compound_rule_updated", f"Cập nhật luật {rid} ({updated['label']})", user_name=user_name, tier=tier)
        await engine.emit({"type": "automation_rule_updated", "rule": updated, "is_compound": True})
        snap = engine.get_snapshot(session=session, sync=False)
        spoken = "Đã xác nhận. Đã cập nhật luật tự động rồi ạ."
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "confirmed": True,
                "kind": "compound_rule_updated",
                "rule": updated,
                "compound_rules": snap.get("compound_rules", []),
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": snap,
            },
        }

    if action_kind == "toggle_compound_rule":
        rid = str(payload.get("rule_id") or "").strip()
        is_compound = bool(payload.get("is_compound", True))
        enabled = bool(payload.get("enabled", True))
        if is_compound:
            existing = get_compound_rule(rid)
            if existing is None:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="compound_rule_not_found",
                    msg="Không tìm thấy luật tự động.",
                    status_code=404,
                    target=rid,
                )
            if tier > 1 and existing["owner_user_id"] != user_id:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="rbac_deny_toggle_rule",
                    msg="Bạn chỉ có quyền bật tắt luật tự động của chính mình.",
                    status_code=403,
                    target=rid,
                )
            updated = toggle_compound_rule(rid, enabled)
        else:
            existing_s = next((r for r in list_automation_rules(include_disabled=True) if r["rule_id"] == rid), None)
            if existing_s is None:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="rule_not_found",
                    msg="Không tìm thấy luật tự động.",
                    status_code=404,
                    target=rid,
                )
            if tier > 1 and existing_s["owner_user_id"] != user_id:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="rbac_deny_toggle_rule",
                    msg="Bạn chỉ có quyền bật tắt luật tự động của chính mình.",
                    status_code=403,
                    target=rid,
                )
            _toggle_legacy_simple_rule(rid, enabled)
            updated = next((r for r in list_automation_rules(include_disabled=True) if r["rule_id"] == rid), existing_s)

        engine.sync_automation_pools_from_sqlite(emit_snapshot=False)
        st_vi = "bật" if enabled else "tạm tắt"
        append_audit_log("AUTOMATION", "rule_toggled", f"Đã {st_vi} luật {rid}", user_name=user_name, tier=tier)
        await engine.emit({"type": "automation_rule_updated", "rule": updated, "enabled": enabled})
        snap = engine.get_snapshot(session=session, sync=False)
        spoken = f"Đã xác nhận. Đã {st_vi} luật tự động rồi ạ."
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "confirmed": True,
                "kind": "automation_rule_toggled",
                "rule": updated,
                "enabled": enabled,
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": snap,
            },
        }

    if action_kind == "delete_compound_rule":
        rid = str(payload.get("rule_id") or "").strip()
        existing = get_compound_rule(rid)
        if existing is None:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="compound_rule_not_found",
                msg="Không tìm thấy luật tự động cần xóa.",
                status_code=404,
                target=rid,
            )
        if tier > 1 and existing["owner_user_id"] != user_id:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_delete_compound_rule",
                msg="Bạn chỉ có quyền xóa luật tự động của chính mình.",
                status_code=403,
                target=rid,
            )
        delete_compound_rule(rid)
        engine.sync_automation_pools_from_sqlite(emit_snapshot=False)
        append_audit_log("AUTOMATION", "compound_rule_deleted", f"Xóa luật phức hợp {rid}", user_name=user_name, tier=tier)
        await engine.emit({"type": "automation_rule_deleted", "rule_id": rid, "is_compound": True})
        snap = engine.get_snapshot(session=session, sync=False)
        spoken = "Đã xác nhận. Đã xóa luật tự động rồi ạ."
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "confirmed": True,
                "deleted": True,
                "rule_id": rid,
                "kind": "compound_rule_deleted",
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": snap,
            },
        }

    if action_kind == "toggle_schedule":
        sid = str(payload.get("schedule_id") or "").strip()
        enabled = bool(payload.get("enabled", True))
        existing = next((s for s in list_schedules(include_disabled=True) if s["schedule_id"] == sid), None)
        if existing is None:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="schedule_not_found",
                msg="Không tìm thấy lịch trình.",
                status_code=404,
                target=sid,
            )
        if tier > 1 and existing["owner_user_id"] != user_id:
            return _deny_mutation_error(
                session=session,
                source=source,
                category="rbac_deny_toggle_schedule",
                msg="Bạn chỉ có quyền bật tắt lịch trình của chính mình.",
                status_code=403,
                target=sid,
            )
        try:
            updated = update_schedule(sid, enabled=enabled, actor_tier=tier, engine=engine)
        except Exception as exc:
            err_s = str(exc)
            return _deny_mutation_error(
                session=session,
                source=source,
                category="toggle_schedule_failed",
                msg=err_s,
                status_code=409 if "Trùng lịch" in err_s else 400,
                target=sid,
            )
        engine.sync_automation_pools_from_sqlite(emit_snapshot=False)
        st_vi = "bật" if enabled else "tạm tắt"
        append_audit_log("AUTOMATION", "schedule_toggled", f"Đã {st_vi} lịch {sid}", user_name=user_name, tier=tier)
        await engine.emit({"type": "schedule_updated", "schedule": updated})
        snap = engine.get_snapshot(session=session, sync=False)
        spoken = f"Đã xác nhận. Đã {st_vi} lịch trình rồi ạ."
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "confirmed": True,
                "kind": "schedule_toggled",
                "schedule": updated,
                "enabled": enabled,
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": snap,
            },
        }

    if action_kind == "reset_automations":
        scope = str(payload.get("scope") or "all").strip().lower()
        clear_all_users = bool(payload.get("clear_all_users", False)) and tier == 1
        target_uid = None if clear_all_users else user_id

        if scope == "factory":
            if tier != 1:
                return _deny_mutation_error(
                    session=session,
                    source=source,
                    category="rbac_deny_factory_reset",
                    msg="Chỉ chủ nhà cấp 1 mới được khôi phục cài đặt gốc ạ.",
                    status_code=403,
                    target="factory",
                )
            res_f = await engine.factory_reset(scope="all", bypass_rbac=True)
            clear_compound_rules_scoped(clear_all=True)
            snap = engine.get_snapshot(session=session, sync=False)
            spoken = str(res_f.get("exact_spoken_reply") or "Đã khôi phục toàn bộ hệ thống về mặc định.")
            return {
                "handled": True,
                "status_code": 200,
                "payload": {
                    "ok": True,
                    "confirmed": True,
                    "kind": "automations_reset",
                    "scope": scope,
                    "reply": spoken,
                    "exact_spoken_reply": spoken,
                    "snapshot": snap,
                },
            }

        removed = 0
        if scope in ("timers", "schedules", "all"):
            removed += reset_timers_and_schedules_scoped(
                target_owner_id=target_uid,
                clear_all=clear_all_users,
                engine=engine,
            )
        if scope in ("custom_commands", "all"):
            removed += reset_custom_commands_scoped(
                target_owner_id=target_uid,
                clear_all=clear_all_users,
                engine=engine,
            )
        if scope in ("rules", "all"):
            removed += reset_links_scoped(
                target_owner_id=target_uid,
                clear_all=clear_all_users,
                engine=engine,
            )
            removed += clear_compound_rules_scoped(
                target_owner_id=target_uid,
                clear_all=clear_all_users,
            )
        if scope == "devices":
            device_plan = [
                ("living_room_light", "turn_off"),
                ("bedroom_light", "turn_off"),
                ("garden_pump", "turn_off"),
                ("alarm_siren", "turn_off"),
                ("speaker_amp", "turn_off"),
                ("main_door", "close"),
            ]
            for did, act in device_plan:
                if can_control_device(tier, did):
                    await engine.execute_device_action(
                        did,
                        act,
                        source=source,
                        request_tier=tier,
                        request_user_name=user_name,
                        request_role=role,
                        trigger_chains=False,
                    )
                    removed += 1

        engine.sync_automation_pools_from_sqlite(emit_snapshot=False)
        append_audit_log("AUTOMATION", "automations_reset", f"Đặt lại tự động hóa phạm vi '{scope}' ({removed} mục)", user_name=user_name, tier=tier)
        await engine.emit({"type": "pool_reset_completed", "scope": scope, "removed": removed})
        snap = engine.get_snapshot(session=session, sync=False)
        spoken = "Đã xác nhận. Đã đặt lại xong rồi ạ."
        return {
            "handled": True,
            "status_code": 200,
            "payload": {
                "ok": True,
                "confirmed": True,
                "kind": "automations_reset",
                "scope": scope,
                "removed": removed,
                "reply": spoken,
                "exact_spoken_reply": spoken,
                "snapshot": snap,
            },
        }

    return None


# =============================================================================
# UNIFIED TOOL DISPATCHER
# =============================================================================


async def dispatch_tool(
    name: str,
    args: dict[str, Any] | None,
    *,
    engine: Any,
    session: Any,
    source: str = "tool",
    session_key: str = "",
) -> dict[str, Any]:
    """Unified tool dispatcher shared by Gemini Live and typed text NLU."""
    tool_args = dict(args or {})
    user_id, tier, user_name, role = _session_actor(session)
    skey = session_key or _resolve_session_key(session, source)

    # --- UI Guidance (available to all authenticated tiers) ---
    if name == "get_ui_guidance":
        res_ui = _get_ui_guidance_from_registry(
            query=str(tool_args.get("query") or ""),
            topic=str(tool_args.get("topic") or ""),
        )
        return _wrap_payload({"kind": "ui_guidance", "guidance": res_ui, **res_ui}, status_code=200)

    # --- Confirmation ---
    if name == "confirm_or_cancel_pending_action":
        confirmed = bool(tool_args.get("confirmed", False))
        conf_res = await handle_confirmation_reply(
            raw_text="xác nhận" if confirmed else "hủy",
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
        )
        if conf_res is None:
            return _wrap_payload({"ok": True, "reply": "Hiện không có thao tác nào đang chờ xác nhận."})
        return _wrap_payload(dict(conf_res.get("payload") or {}), status_code=int(conf_res.get("status_code") or 200))

    # --- Devices & Sensors ---
    if name == "list_devices":
        devices = engine.list_accessible_devices(actor_tier=tier)
        summary = ", ".join(f"{d['name']} {d['state_vi']}" for d in devices)
        return _wrap_payload({"ok": True, "count": len(devices), "devices": devices, "reply": summary})

    if name == "get_device_state":
        dev_id = str(tool_args.get("device_id") or "").strip()
        rec = engine.get_device_state_record(dev_id, actor_tier=tier)
        if not rec.get("ok"):
            return _err_resp(
                str(rec.get("exact_spoken_reply") or rec.get("error") or "Không tìm thấy thiết bị."),
                status_code=403 if rec.get("rbac_blocked") else 404,
                rbac_blocked=bool(rec.get("rbac_blocked")),
            )
        return _wrap_payload({"ok": True, "device": rec, "reply": f"{rec['name']} hiện {rec['state_vi']}."})

    if name in ("control_device", "set_device"):
        dev_id = str(tool_args.get("device_id") or "").strip()
        act = str(tool_args.get("action") or "turn_on").strip().lower()
        if name == "set_device":
            res_set = await engine.set_device_parameters(
                device_id=dev_id,
                action=act,
                brightness_pct=tool_args.get("brightness_pct"),
                source=source,
                request_tier=tier,
                request_role=role,
                request_user_name=user_name,
            )
            res_set.setdefault("executed", bool(res_set.get("ok")))
            res_set.setdefault("requires_confirmation", False)
            return _wrap_payload(res_set, status_code=403 if res_set.get("rbac_blocked") else (200 if res_set.get("ok") else 400))
        res_ctrl = await engine.execute_device_action(
            device_id=dev_id,
            action=act,
            source=source,
            request_tier=tier,
            request_role=role,
            request_user_name=user_name,
        )
        res_ctrl.setdefault("executed", bool(res_ctrl.get("ok")))
        res_ctrl.setdefault("requires_confirmation", False)
        return _wrap_payload(res_ctrl, status_code=403 if res_ctrl.get("rbac_blocked") else (200 if res_ctrl.get("ok") else 400))

    if name == "read_sensors":
        sensors = engine.read_all_sensors()
        snd_lbl = "có tiếng động lớn" if sensors.get("sound_detected") else "yên tĩnh"
        reply = (
            f"Nhiệt độ phòng {float(sensors.get('temperature_c', 28.5)):.1f} độ C, "
            f"độ ẩm không khí {float(sensors.get('humidity_pct', 65.0)):.0f}%, "
            f"độ ẩm đất {float(sensors.get('soil_moisture_pct', 55.0)):.0f}%, "
            f"cảm biến âm thanh đang {snd_lbl}."
        )
        return _wrap_payload({"ok": True, "sensors": sensors, "reply": reply})

    if name == "set_or_query_sensors":
        op = str(tool_args.get("operation") or "query").strip().lower()
        if op == "query":
            return await dispatch_tool("read_sensors", {}, engine=engine, session=session, source=source, session_key=skey)
        if tier != 1:
            return _err_resp("Chỉ chủ nhà cấp 1 mới được chỉnh thông số cảm biến mô phỏng.", status_code=403, rbac_blocked=True)
        replies: list[str] = []
        if tool_args.get("temp_c") is not None or tool_args.get("humidity_pct") is not None:
            cur_dht = engine.mqtt_bridge.dht11_telemetry
            t_v = float(tool_args["temp_c"]) if tool_args.get("temp_c") is not None else float(cur_dht.get("temp_c", 28.5))
            h_v = float(tool_args["humidity_pct"]) if tool_args.get("humidity_pct") is not None else float(cur_dht.get("humidity_pct", 65.0))
            r_d = await engine.update_sensor_telemetry(t_v, h_v)
            replies.append(str(r_d.get("exact_spoken_reply") or ""))
        if tool_args.get("soil_moisture_pct") is not None:
            r_s = await engine.update_soil_moisture_telemetry(float(tool_args["soil_moisture_pct"]))
            replies.append(str(r_s.get("exact_spoken_reply") or ""))
        return _wrap_payload({"ok": True, "executed": True, "reply": " ".join(r for r in replies if r) or "Đã cập nhật cảm biến."})

    # --- House Mode ---
    if name == "set_house_mode":
        if tier >= 3:
            return _err_resp(GUEST_ONLY_TOGGLE_MSG_VI, status_code=403, rbac_blocked=True)
        raw_mode = str(tool_args.get("mode") or "").strip().upper()
        if raw_mode in ("VANG_NHA", "VANG", "ABSENT", "OUT"):
            raw_mode = "AWAY"
        elif raw_mode in ("O_NHA", "PRESENT", "IN"):
            raw_mode = "HOME"
        if raw_mode not in ("HOME", "AWAY"):
            return _err_resp("Chế độ nhà chỉ hỗ trợ Ở nhà (HOME) hoặc Vắng nhà (AWAY).", status_code=400)
        res_hm = await engine.set_house_mode(raw_mode, source=source, actor_name=user_name, actor_tier=tier)
        return _wrap_payload(
            {
                **res_hm,
                "kind": "house_mode_updated",
                "executed": True,
                "requires_confirmation": False,
                "snapshot": engine.get_snapshot(session=session, sync=False),
            },
            status_code=200,
        )

    # All remaining tools are automation management -> Tier 3 blocked immediately!
    if tier >= 3:
        denied = _deny_mutation_error(
            session=session,
            source=source,
            category=f"rbac_deny_{name}",
            msg=GUEST_ONLY_TOGGLE_MSG_VI,
            status_code=403,
            target=name,
        )
        return _wrap_payload(dict(denied["payload"]), status_code=403)

    owner_filter = None if tier == 1 else user_id

    # --- Timers ---
    if name == "list_timers":
        db_timers = list_pending_timers(owner_user_id=owner_filter)
        now_ep = time.time()
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for t in db_timers:
            tid = str(t.get("timer_id") or "")
            seen.add(tid)
            rem = max(0, int(round(float(t.get("fire_at") or 0.0) - now_ep)))
            items.append({**t, "remaining_seconds": rem})
        for tid, info in list(getattr(engine, "active_timers", {}).items()):
            if tid in seen:
                continue
            t_owner = str(info.get("owner_user_id") or info.get("owner_id") or "")
            if tier > 1 and t_owner != user_id:
                continue
            rem = max(0, int(round(float(info.get("fire_at") or 0.0) - now_ep)))
            items.append({
                "timer_id": tid,
                "device_id": info.get("raw_target") or info.get("device_id"),
                "action": info.get("action"),
                "label": info.get("label") or format_device_action_vi(str(info.get("device_id") or ""), str(info.get("action") or "")),
                "remaining_seconds": rem,
                "repeat": info.get("repeat") or "once",
                "owner_user_id": t_owner,
            })
        if not items:
            reply = "Hiện chưa có hẹn giờ đếm ngược nào."
        else:
            desc = "; ".join(f"{it.get('label') or it.get('device_id')} (còn {format_duration_vi(it.get('remaining_seconds', 0))})" for it in items)
            reply = f"Đang có {len(items)} hẹn giờ: {desc}."
        return _wrap_payload({"ok": True, "count": len(items), "timers": items, "reply": reply})

    if name == "create_timer":
        dev_id = engine.resolve_canonical_device_id(str(tool_args.get("device_id") or ""))
        act = str(tool_args.get("action") or "").strip().lower()
        if dev_id not in CANONICAL_6_DEVICES and dev_id not in ("all_lights", "all_devices"):
            return _err_resp(f"Thiết bị không hợp lệ. {REMOVED_DEVICE_HINT_VI}", status_code=400)
        if act not in ACTION_TO_STATE:
            return _err_resp("Hành động hẹn giờ không hợp lệ.", status_code=400)
        if dev_id == "main_door" and act in ("turn_on", "turn_off"):
            act = "open" if act == "turn_on" else "close"
        try:
            hrs = max(0.0, float(tool_args.get("hours") or 0.0))
            mins = max(0.0, float(tool_args.get("minutes") or 0.0))
            secs = max(0.0, float(tool_args.get("seconds") or 0.0))
        except (TypeError, ValueError):
            return _err_resp("Thời gian hẹn giờ không hợp lệ.", status_code=400)
        total_sec = hrs * 3600.0 + mins * 60.0 + secs
        if total_sec <= 0:
            return _err_resp("Bạn muốn hẹn giờ sau bao lâu?", status_code=400)
        repeat = str(tool_args.get("repeat") or "once").strip().lower()
        for td in _expand_targets(dev_id):
            if not can_control_device(tier, td):
                return _err_resp("Xin lỗi, bạn không có quyền thực hiện lệnh này.", status_code=403, rbac_blocked=True)
        c_msg = check_tier1_schedule_conflict(actor_tier=tier, fire_epoch=time.time() + total_sec, schedule_type=repeat, engine=engine)
        if c_msg:
            return _err_resp(c_msg, status_code=409)
        prompt_q = f"Mình sẽ {format_device_action_vi(dev_id, act).lower()} sau {format_duration_vi(total_sec)}, bạn đồng ý không?"
        staged = await prepare_pending_mutation(
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            action_kind="create_timer",
            payload={"device_id": dev_id, "action": act, "hours": hrs, "minutes": mins, "seconds": secs, "repeat": repeat},
            prompt_summary=prompt_q,
        )
        return _wrap_payload(dict(staged["payload"]), status_code=int(staged["status_code"]))

    if name == "edit_timer":
        tid = str(tool_args.get("timer_id") or "").strip()
        dev_id = str(tool_args.get("device_id") or "").strip()
        existing_t = None
        if tid:
            existing_t = engine.active_timers.get(tid) or next(
                (r for r in list_pending_timers() if str(r.get("timer_id") or "") == tid),
                None,
            )
        elif dev_id:
            cid = engine.resolve_canonical_device_id(dev_id)
            for t_id, info in engine.active_timers.items():
                if info.get("device_id") == cid or info.get("raw_target") == cid:
                    if tier == 1 or str(info.get("owner_user_id") or info.get("owner_id") or "") == user_id:
                        existing_t = {**info, "timer_id": t_id}
                        tid = t_id
                        break
        if existing_t is None:
            return _err_resp("Không tìm thấy hẹn giờ cần sửa.", status_code=404)
        t_owner = str(existing_t.get("owner_user_id") or existing_t.get("owner_id") or "")
        if tier > 1 and (int(existing_t.get("owner_tier") or 1) == 1 or t_owner != user_id):
            return _err_resp("Bạn chỉ có quyền sửa hẹn giờ của chính mình.", status_code=403, rbac_blocked=True)
        target_dev = engine.resolve_canonical_device_id(str(dev_id or existing_t.get("raw_target") or existing_t.get("device_id") or ""))
        new_act = str(tool_args.get("new_action") or tool_args.get("action") or existing_t.get("action") or "turn_on").strip().lower()
        if target_dev == "main_door" and new_act in ("turn_on", "turn_off"):
            new_act = "open" if new_act == "turn_on" else "close"
        hrs = max(0.0, float(tool_args.get("hours") or 0.0))
        mins = max(0.0, float(tool_args.get("minutes") or 0.0))
        secs = max(0.0, float(tool_args.get("seconds") or 0.0))
        total_sec = hrs * 3600.0 + mins * 60.0 + secs
        if total_sec <= 0:
            secs = max(1.0, float(existing_t.get("delay_seconds") or 10.0))
            total_sec = secs
        repeat = str(tool_args.get("repeat") or existing_t.get("repeat") or "once").strip().lower()
        for td in _expand_targets(target_dev):
            if not can_control_device(tier, td):
                return _err_resp("Xin lỗi, bạn không có quyền thực hiện lệnh này.", status_code=403, rbac_blocked=True)
        c_msg = check_tier1_schedule_conflict(actor_tier=tier, fire_epoch=time.time() + total_sec, schedule_type=repeat, exclude_timer_id=tid, engine=engine)
        if c_msg:
            return _err_resp(c_msg, status_code=409)
        prompt_q = f"Cập nhật hẹn giờ sau {format_duration_vi(total_sec)} sẽ {format_device_action_vi(target_dev, new_act).lower()}"
        staged = await prepare_pending_mutation(
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            action_kind="modify_timer",
            payload={"timer_id": tid, "device_id": target_dev, "new_action": new_act, "hours": hrs, "minutes": mins, "seconds": secs, "repeat": repeat},
            prompt_summary=prompt_q,
        )
        return _wrap_payload(dict(staged["payload"]), status_code=int(staged["status_code"]))

    if name == "delete_timer":
        tid = str(tool_args.get("timer_id") or "").strip()
        dev_id = str(tool_args.get("device_id") or "").strip()
        if not tid and not dev_id:
            return _err_resp("Cần chỉ rõ mã hẹn giờ hoặc thiết bị cần hủy.", status_code=400)
        if tid:
            existing_t = engine.active_timers.get(tid) or next(
                (r for r in list_pending_timers() if str(r.get("timer_id") or "") == tid),
                None,
            )
            if existing_t is None:
                return _err_resp("Không tìm thấy hẹn giờ cần hủy.", status_code=404)
            t_owner = str(existing_t.get("owner_user_id") or existing_t.get("owner_id") or "")
            if tier > 1 and (int(existing_t.get("owner_tier") or 1) == 1 or t_owner != user_id):
                return _err_resp("Bạn chỉ có quyền hủy hẹn giờ của chính mình.", status_code=403, rbac_blocked=True)
            lbl = str(existing_t.get("label") or tid)
            prompt_q = f"Hủy hẹn giờ {lbl}"
        else:
            dev_id = engine.resolve_canonical_device_id(dev_id)
            if dev_id not in CANONICAL_6_DEVICES and dev_id not in ("all_lights", "all_devices"):
                return _err_resp(f"Thiết bị không hợp lệ. {REMOVED_DEVICE_HINT_VI}", status_code=400)
            prompt_q = f"Hủy hẹn giờ của {DEVICE_LABELS_VI.get(dev_id, dev_id).lower()}"
        staged = await prepare_pending_mutation(
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            action_kind="delete_timer",
            payload={"timer_id": tid, "device_id": dev_id},
            prompt_summary=prompt_q,
        )
        return _wrap_payload(dict(staged["payload"]), status_code=int(staged["status_code"]))

    # --- Schedules ---
    if name == "list_schedules":
        inc_dis = bool(tool_args.get("include_disabled", True))
        scheds = list_schedules(include_disabled=inc_dis, owner_user_id=owner_filter)
        if not scheds:
            reply = "Hiện chưa có lịch trình nào."
        else:
            parts = []
            for s in scheds:
                wd_str = format_weekdays_vi(s.get("weekdays"))
                rep_lbl = wd_str or ("hằng ngày" if s.get("schedule_type") == "daily" else "một lần")
                st_lbl = "" if s.get("enabled") else " [đang tắt]"
                parts.append(f"{s['time_hhmm']} ({rep_lbl}): {s['label']}{st_lbl}")
            reply = f"Đang có {len(scheds)} lịch trình: {'; '.join(parts)}."
        return _wrap_payload({"ok": True, "count": len(scheds), "schedules": scheds, "reply": reply})

    if name == "create_schedule":
        dev_id = engine.resolve_canonical_device_id(str(tool_args.get("device_id") or ""))
        act = str(tool_args.get("action") or "").strip().lower()
        hhmm_raw = str(tool_args.get("time_hhmm") or "").strip()
        weekdays = normalize_weekdays(tool_args.get("weekdays"))
        sc_type_raw = str(tool_args.get("schedule_type") or ("daily" if weekdays else "once")).strip().lower()
        sc_type = "daily" if sc_type_raw in ("daily", "weekly") or weekdays else "once"
        if dev_id not in CANONICAL_6_DEVICES:
            return _err_resp(f"Thiết bị không hợp lệ. {REMOVED_DEVICE_HINT_VI}", status_code=400)
        if act not in ACTION_TO_STATE:
            return _err_resp("Hành động đặt lịch không hợp lệ.", status_code=400)
        if dev_id == "main_door" and act in ("turn_on", "turn_off"):
            act = "open" if act == "turn_on" else "close"
        if not can_control_device(tier, dev_id):
            return _err_resp("Xin lỗi, bạn không có quyền thực hiện lệnh này.", status_code=403, rbac_blocked=True)
        try:
            _, _, hhmm_norm = _parse_hhmm_parts(hhmm_raw)
        except Exception:
            return _err_resp("Bạn muốn đặt lịch vào lúc mấy giờ (định dạng HH:MM)?", status_code=400)
        run_date_vn = str(tool_args.get("run_date_vn") or "").strip()
        c_msg = check_tier1_schedule_conflict(actor_tier=tier, time_hhmm=hhmm_norm, schedule_type=sc_type, run_date_vn=run_date_vn, engine=engine)
        if c_msg:
            return _err_resp(c_msg, status_code=409)
        rep_vi = format_weekdays_vi(weekdays) if weekdays else ("hằng ngày" if sc_type == "daily" else "một lần")
        prompt_q = f"Đặt lịch {format_device_action_vi(dev_id, act).lower()} lúc {hhmm_norm} ({rep_vi})"
        staged = await prepare_pending_mutation(
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            action_kind="create_schedule",
            payload={
                "target_devs": [dev_id],
                "action": act,
                "time_hhmm": hhmm_norm,
                "schedule_type": sc_type,
                "weekdays": weekdays,
                "run_date_vn": run_date_vn,
                "label": str(tool_args.get("label") or "").strip(),
            },
            prompt_summary=prompt_q,
        )
        return _wrap_payload(dict(staged["payload"]), status_code=int(staged["status_code"]))

    if name == "edit_schedule":
        sid = str(tool_args.get("schedule_id") or "").strip()
        all_s = list_schedules(include_disabled=True)
        existing = next((s for s in all_s if s["schedule_id"] == sid), None) if sid else None
        if existing is None and tool_args.get("device_id"):
            cid = engine.resolve_canonical_device_id(str(tool_args["device_id"]))
            cands = [s for s in all_s if s["device_id"] == cid and (tier == 1 or s["owner_user_id"] == user_id)]
            existing = cands[0] if cands else None
            if existing:
                sid = existing["schedule_id"]
        if existing is None:
            return _err_resp("Không tìm thấy lịch trình cần sửa.", status_code=404)
        if tier > 1 and existing["owner_user_id"] != user_id:
            return _err_resp("Bạn chỉ có quyền sửa lịch trình của chính mình.", status_code=403, rbac_blocked=True)
        new_dev = engine.resolve_canonical_device_id(str(tool_args["device_id"])) if tool_args.get("device_id") else None
        if new_dev is not None:
            if new_dev not in CANONICAL_6_DEVICES:
                return _err_resp(f"Thiết bị không hợp lệ. {REMOVED_DEVICE_HINT_VI}", status_code=400)
            if not can_control_device(tier, new_dev):
                return _err_resp("Xin lỗi, bạn không có quyền thực hiện lệnh này.", status_code=403, rbac_blocked=True)
        new_act = str(tool_args.get("action") or "").strip().lower() or None
        new_hhmm = None
        if tool_args.get("time_hhmm"):
            try:
                _, _, new_hhmm = _parse_hhmm_parts(str(tool_args["time_hhmm"]))
            except Exception:
                return _err_resp("Định dạng giờ mới không hợp lệ (cần HH:MM).", status_code=400)
        new_weekdays = normalize_weekdays(tool_args["weekdays"]) if "weekdays" in tool_args and tool_args["weekdays"] is not None else None
        new_type = str(tool_args.get("schedule_type") or "").strip().lower() or None
        if new_type == "weekly" or new_weekdays:
            new_type = "daily"
        cand_hhmm, cand_type, cand_date, cand_enabled = compute_candidate_schedule_state(
            existing,
            time_hhmm=new_hhmm,
            schedule_type=new_type,
            enabled=tool_args.get("enabled"),
        )
        if cand_enabled:
            c_msg = check_tier1_schedule_conflict(
                actor_tier=tier,
                time_hhmm=cand_hhmm,
                schedule_type=cand_type,
                run_date_vn=cand_date,
                exclude_schedule_id=sid,
                engine=engine,
            )
            if c_msg:
                return _err_resp(c_msg, status_code=409)
        cand_dev = new_dev or existing["device_id"]
        cand_act = new_act or existing["action"]
        wd_eff = new_weekdays if new_weekdays is not None else existing.get("weekdays", [])
        rep_vi = format_weekdays_vi(wd_eff) if wd_eff else ("hằng ngày" if cand_type == "daily" else "một lần")
        prompt_q = f"Cập nhật lịch {format_device_action_vi(cand_dev, cand_act).lower()} lúc {cand_hhmm} ({rep_vi})"
        staged = await prepare_pending_mutation(
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            action_kind="update_schedule",
            payload={
                "schedule_id": sid,
                "device_id": new_dev,
                "action": new_act,
                "time_hhmm": new_hhmm,
                "schedule_type": new_type,
                "weekdays": new_weekdays,
                "enabled": tool_args.get("enabled") if "enabled" in tool_args else None,
                "label": tool_args.get("label"),
            },
            prompt_summary=prompt_q,
        )
        return _wrap_payload(dict(staged["payload"]), status_code=int(staged["status_code"]))

    if name == "toggle_schedule":
        sid = str(tool_args.get("schedule_id") or "").strip()
        hhmm = str(tool_args.get("time_hhmm") or "").strip()
        dev_id = str(tool_args.get("device_id") or "").strip()
        enabled = bool(tool_args.get("enabled", True))
        all_s = list_schedules(include_disabled=True)
        target_s = None
        if sid:
            target_s = next((s for s in all_s if s["schedule_id"] == sid), None)
        else:
            cands = [s for s in all_s if tier == 1 or s["owner_user_id"] == user_id]
            if hhmm:
                cands = [s for s in cands if s["time_hhmm"] == hhmm]
            if dev_id:
                cid = engine.resolve_canonical_device_id(dev_id)
                cands = [s for s in cands if s["device_id"] == cid]
            target_s = cands[0] if cands else None
        if target_s is None:
            return _err_resp("Không tìm thấy lịch trình phù hợp.", status_code=404)
        if tier > 1 and target_s["owner_user_id"] != user_id:
            return _err_resp("Bạn chỉ có quyền bật tắt lịch trình của chính mình.", status_code=403, rbac_blocked=True)
        verb = "Bật lại" if enabled else "Tạm tắt"
        prompt_q = f"{verb} lịch trình '{target_s['label']}'"
        staged = await prepare_pending_mutation(
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            action_kind="toggle_schedule",
            payload={"schedule_id": target_s["schedule_id"], "enabled": enabled},
            prompt_summary=prompt_q,
        )
        return _wrap_payload(dict(staged["payload"]), status_code=int(staged["status_code"]))

    if name == "delete_schedule":
        sid = str(tool_args.get("schedule_id") or "").strip()
        hhmm = str(tool_args.get("time_hhmm") or "").strip()
        dev_id = str(tool_args.get("device_id") or "").strip()
        all_s = list_schedules(include_disabled=True)
        target_s = next((s for s in all_s if s["schedule_id"] == sid), None) if sid else None
        if target_s is None:
            cands = [s for s in all_s if tier == 1 or s["owner_user_id"] == user_id]
            if hhmm:
                cands = [s for s in cands if s["time_hhmm"] == hhmm]
            if dev_id:
                cid = engine.resolve_canonical_device_id(dev_id)
                cands = [s for s in cands if s["device_id"] == cid]
            target_s = cands[0] if cands else None
        if target_s is None:
            return _err_resp("Không tìm thấy lịch trình cần xóa.", status_code=404)
        if tier > 1 and target_s["owner_user_id"] != user_id:
            return _err_resp("Bạn chỉ có quyền xóa lịch trình của chính mình.", status_code=403, rbac_blocked=True)
        prompt_q = f"Xóa lịch trình '{target_s['label']}'"
        staged = await prepare_pending_mutation(
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            action_kind="delete_schedule",
            payload={"schedule_id": target_s["schedule_id"]},
            prompt_summary=prompt_q,
        )
        return _wrap_payload(dict(staged["payload"]), status_code=int(staged["status_code"]))

    # --- Custom Commands ---
    if name == "list_custom_commands":
        inc_dis = bool(tool_args.get("include_disabled", True))
        cmds = list_custom_commands(include_disabled=inc_dis, owner_user_id=owner_filter)
        if not cmds:
            reply = "Hiện chưa có lệnh tùy chỉnh nào."
        else:
            desc = "; ".join(f"'{c['phrase']}': {c['steps_summary']}" for c in cmds)
            reply = f"Đang có {len(cmds)} lệnh tùy chỉnh: {desc}."
        return _wrap_payload({"ok": True, "count": len(cmds), "commands": cmds, "scenes": cmds, "reply": reply})

    if name == "create_custom_command":
        phrase = str(tool_args.get("phrase") or "").strip()
        if not normalize_phrase(phrase):
            return _err_resp("Bạn muốn đặt tên cho lệnh tùy chỉnh là gì?", status_code=400)
        steps = tool_args.get("steps")
        if not isinstance(steps, list) or not steps:
            steps = parse_multi_steps_from_text(str(tool_args.get("steps_text") or ""))
        clean_steps = _normalize_steps(steps if isinstance(steps, list) else [])
        if not clean_steps:
            return _err_resp("Chưa xác định được bước thiết bị hợp lệ cho lệnh tùy chỉnh.", status_code=400)
        ok_rb, rb_msg = check_steps_rbac(clean_steps, tier)
        if not ok_rb:
            return _err_resp(rb_msg, status_code=403, rbac_blocked=True)
        summary = ", ".join(format_device_action_vi(s["device_id"], s["action"]).lower() for s in clean_steps)
        staged = await prepare_pending_mutation(
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            action_kind="create_custom_command",
            payload={"phrase": phrase, "steps": clean_steps},
            prompt_summary=f"Tạo lệnh '{phrase}' gồm: {summary}",
        )
        return _wrap_payload(dict(staged["payload"]), status_code=int(staged["status_code"]))

    if name == "run_custom_command":
        cid = str(tool_args.get("command_id") or "").strip()
        phrase = str(tool_args.get("phrase") or "").strip()
        all_cmds = list_custom_commands(include_disabled=False, owner_user_id=owner_filter)
        cmd_hit = next((c for c in all_cmds if c["command_id"] == cid), None) if cid else None
        if cmd_hit is None and phrase:
            cmd_hit = find_custom_command_by_text(phrase, owner_user_id=owner_filter)
        if cmd_hit is None:
            return _err_resp(f"Không tìm thấy lệnh tùy chỉnh '{phrase or cid}'.", status_code=404)
        ok_rb, rb_msg = check_steps_rbac(cmd_hit.get("steps") or [], tier)
        if not ok_rb:
            return _err_resp(rb_msg, status_code=403, rbac_blocked=True)
        staged = await prepare_pending_mutation(
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            action_kind="run_custom_command",
            payload={"command_id": cmd_hit["command_id"], "phrase": cmd_hit["phrase"]},
            prompt_summary=f"Chạy lệnh '{cmd_hit['phrase']}' ({cmd_hit['steps_summary']})",
        )
        return _wrap_payload(dict(staged["payload"]), status_code=int(staged["status_code"]))

    if name == "edit_custom_command":
        cid = str(tool_args.get("command_id") or "").strip()
        phrase = str(tool_args.get("phrase") or "").strip()
        all_cmds = list_custom_commands(include_disabled=True)
        existing = next((c for c in all_cmds if c["command_id"] == cid), None) if cid else None
        if existing is None and phrase:
            existing = find_custom_command_by_text(phrase, owner_user_id=owner_filter)
        if existing is None:
            return _err_resp("Không tìm thấy lệnh tùy chỉnh cần sửa.", status_code=404)
        if tier > 1 and existing["owner_user_id"] != user_id:
            return _err_resp("Bạn chỉ có quyền sửa lệnh tùy chỉnh của chính mình.", status_code=403, rbac_blocked=True)
        new_phrase = str(tool_args.get("new_phrase") or existing["phrase"]).strip()
        steps = tool_args.get("steps")
        if not isinstance(steps, list) or not steps:
            st_txt = str(tool_args.get("steps_text") or "").strip()
            steps = parse_multi_steps_from_text(st_txt) if st_txt else existing["steps"]
        clean_steps = _normalize_steps(steps if isinstance(steps, list) else [])
        if not clean_steps:
            return _err_resp("Danh sách bước thiết bị không hợp lệ.", status_code=400)
        ok_rb, rb_msg = check_steps_rbac(clean_steps, tier)
        if not ok_rb:
            return _err_resp(rb_msg, status_code=403, rbac_blocked=True)
        enabled = bool(tool_args["enabled"]) if "enabled" in tool_args and tool_args["enabled"] is not None else bool(existing["enabled"])
        summary = ", ".join(format_device_action_vi(s["device_id"], s["action"]).lower() for s in clean_steps)
        staged = await prepare_pending_mutation(
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            action_kind="update_custom_command",
            payload={"command_id": existing["command_id"], "phrase": new_phrase, "steps": clean_steps, "enabled": enabled},
            prompt_summary=f"Cập nhật lệnh '{new_phrase}' thành: {summary}",
        )
        return _wrap_payload(dict(staged["payload"]), status_code=int(staged["status_code"]))

    if name == "delete_custom_command":
        cid = str(tool_args.get("command_id") or "").strip()
        phrase = str(tool_args.get("phrase") or "").strip()
        all_cmds = list_custom_commands(include_disabled=True)
        existing = next((c for c in all_cmds if c["command_id"] == cid), None) if cid else None
        if existing is None and phrase:
            existing = find_custom_command_by_text(phrase, owner_user_id=owner_filter)
        if existing is None:
            return _err_resp("Không tìm thấy lệnh tùy chỉnh cần xóa.", status_code=404)
        if tier > 1 and existing["owner_user_id"] != user_id:
            return _err_resp("Bạn chỉ có quyền xóa lệnh tùy chỉnh của chính mình.", status_code=403, rbac_blocked=True)
        staged = await prepare_pending_mutation(
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            action_kind="delete_custom_command",
            payload={"command_id": existing["command_id"], "phrase": existing["phrase"]},
            prompt_summary=f"Xóa lệnh tùy chỉnh '{existing['phrase']}'",
        )
        return _wrap_payload(dict(staged["payload"]), status_code=int(staged["status_code"]))

    # --- Automation Rules (Simple + Compound) ---
    if name == "list_automation_rules":
        inc_dis = bool(tool_args.get("include_disabled", True))
        comp_rules = list_compound_rules(include_disabled=inc_dis, owner_user_id=owner_filter)
        simple_rules = list_automation_rules(include_disabled=inc_dis, owner_user_id=owner_filter)
        combined = comp_rules + simple_rules
        if not combined:
            reply = "Hiện chưa có luật tự động nào."
        else:
            descs = [
                f"{r.get('label') or r.get('rule_id')}" + ("" if r.get("enabled", True) else " [đang tắt]")
                for r in combined
            ]
            reply = f"Đang có {len(combined)} luật tự động: {'; '.join(descs)}."
        return _wrap_payload(
            {
                "ok": True,
                "count": len(combined),
                "compound_rules": comp_rules,
                "simple_rules": simple_rules,
                "rules": combined,
                "reply": reply,
            }
        )

    if name == "create_automation_rule":
        conds = tool_args.get("conditions")
        acts = tool_args.get("actions")
        # Support legacy single-condition shorthand if passed directly
        if not conds and tool_args.get("when_device_id"):
            conds = [{"source": tool_args["when_device_id"], "state": tool_args.get("when_state", "ON")}]
        if not acts and tool_args.get("then_device_id") and tool_args.get("then_action"):
            acts = [{"device_id": tool_args["then_device_id"], "action": tool_args["then_action"]}]
        try:
            validated = validate_compound_rule_input(
                owner_user_id=user_id,
                owner_tier=tier,
                logic=str(tool_args.get("logic") or "AND"),
                conditions=conds if isinstance(conds, list) else [],
                actions=acts if isinstance(acts, list) else [],
                else_actions=tool_args.get("else_actions") if isinstance(tool_args.get("else_actions"), list) else [],
                cooldown_seconds=float(tool_args.get("cooldown_seconds") if tool_args.get("cooldown_seconds") is not None else 10.0),
                hysteresis=tool_args.get("hysteresis"),
                engine=engine,
            )
        except PermissionError as exc:
            return _err_resp(str(exc), status_code=403, rbac_blocked=True)
        except ValueError as exc:
            return _err_resp(str(exc), status_code=400)

        label_vi = str(tool_args.get("label") or "").strip() or format_compound_rule_vi(
            validated["logic"],
            validated["conditions"],
            validated["actions"],
            validated["else_actions"],
        )
        staged = await prepare_pending_mutation(
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            action_kind="create_compound_rule",
            payload={
                "name": str(tool_args.get("name") or "").strip() or label_vi[:180],
                "logic": validated["logic"],
                "conditions": validated["conditions"],
                "actions": validated["actions"],
                "else_actions": validated["else_actions"],
                "cooldown_seconds": validated["cooldown_seconds"],
                "hysteresis": validated["hysteresis"],
                "label": label_vi,
            },
            prompt_summary=f"Tạo luật tự động: {label_vi}",
        )
        return _wrap_payload(dict(staged["payload"]), status_code=int(staged["status_code"]))

    if name == "edit_automation_rule":
        is_comp, target_r = _match_compound_or_simple_rule(
            rule_id=str(tool_args.get("rule_id") or ""),
            keyword=str(tool_args.get("keyword") or ""),
            actor_uid=user_id,
            actor_tier=tier,
        )
        if target_r is None:
            return _err_resp("Không tìm thấy luật tự động cần sửa.", status_code=404)
        if tier > 1 and target_r["owner_user_id"] != user_id:
            return _err_resp("Bạn chỉ có quyền sửa luật tự động của chính mình.", status_code=403, rbac_blocked=True)
        if not is_comp:
            return _err_resp("Luật liên kết cũ không hỗ trợ sửa từng phần; vui lòng xóa và tạo luật mới.", status_code=400)
        cand_logic = str(tool_args.get("logic") or target_r["logic"])
        cand_conds = tool_args.get("conditions") if tool_args.get("conditions") is not None else target_r["conditions"]
        cand_acts = tool_args.get("actions") if tool_args.get("actions") is not None else target_r["actions"]
        cand_else = tool_args.get("else_actions") if tool_args.get("else_actions") is not None else target_r["else_actions"]
        cand_cd = tool_args.get("cooldown_seconds") if tool_args.get("cooldown_seconds") is not None else target_r["cooldown_seconds"]
        cand_hyst = tool_args.get("hysteresis") if "hysteresis" in tool_args else target_r["hysteresis"]
        try:
            validated = validate_compound_rule_input(
                owner_user_id=target_r["owner_user_id"],
                owner_tier=tier,
                logic=cand_logic,
                conditions=cand_conds,
                actions=cand_acts,
                else_actions=cand_else,
                cooldown_seconds=float(cand_cd),
                hysteresis=cand_hyst,
                exclude_rule_id=target_r["rule_id"],
                engine=engine,
            )
        except PermissionError as exc:
            return _err_resp(str(exc), status_code=403, rbac_blocked=True)
        except ValueError as exc:
            return _err_resp(str(exc), status_code=400)

        new_label = str(tool_args.get("label") or "").strip() or format_compound_rule_vi(
            validated["logic"],
            validated["conditions"],
            validated["actions"],
            validated["else_actions"],
        )
        staged = await prepare_pending_mutation(
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            action_kind="update_compound_rule",
            payload={
                "rule_id": target_r["rule_id"],
                "name": tool_args.get("name"),
                "logic": validated["logic"],
                "conditions": validated["conditions"],
                "actions": validated["actions"],
                "else_actions": validated["else_actions"],
                "cooldown_seconds": validated["cooldown_seconds"],
                "hysteresis": validated["hysteresis"],
                "enabled": tool_args.get("enabled") if "enabled" in tool_args else None,
                "label": new_label,
            },
            prompt_summary=f"Cập nhật luật tự động thành: {new_label}",
        )
        return _wrap_payload(dict(staged["payload"]), status_code=int(staged["status_code"]))

    if name == "toggle_automation_rule":
        enabled = bool(tool_args.get("enabled", True))
        is_comp, target_r = _match_compound_or_simple_rule(
            rule_id=str(tool_args.get("rule_id") or ""),
            keyword=str(tool_args.get("keyword") or ""),
            actor_uid=user_id,
            actor_tier=tier,
        )
        if target_r is None:
            return _err_resp("Không tìm thấy luật tự động phù hợp.", status_code=404)
        if tier > 1 and target_r["owner_user_id"] != user_id:
            return _err_resp("Bạn chỉ có quyền bật tắt luật tự động của chính mình.", status_code=403, rbac_blocked=True)
        verb = "Bật lại" if enabled else "Tạm tắt"
        staged = await prepare_pending_mutation(
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            action_kind="toggle_compound_rule",
            payload={"rule_id": target_r["rule_id"], "is_compound": is_comp, "enabled": enabled},
            prompt_summary=f"{verb} luật tự động '{target_r.get('label') or target_r['rule_id']}'",
        )
        return _wrap_payload(dict(staged["payload"]), status_code=int(staged["status_code"]))

    if name == "delete_automation_rule":
        is_comp, target_r = _match_compound_or_simple_rule(
            rule_id=str(tool_args.get("rule_id") or ""),
            keyword=str(tool_args.get("keyword") or ""),
            device_id=str(tool_args.get("device_id") or ""),
            actor_uid=user_id,
            actor_tier=tier,
        )
        if target_r is None:
            return _err_resp("Không tìm thấy luật tự động cần xóa.", status_code=404)
        if tier > 1 and target_r["owner_user_id"] != user_id:
            return _err_resp("Bạn chỉ có quyền xóa luật tự động của chính mình.", status_code=403, rbac_blocked=True)
        staged = await prepare_pending_mutation(
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            action_kind="delete_compound_rule" if is_comp else "delete_automation_rule",
            payload={"rule_id": target_r["rule_id"]},
            prompt_summary=f"Xóa luật tự động '{target_r.get('label') or target_r['rule_id']}'",
        )
        return _wrap_payload(dict(staged["payload"]), status_code=int(staged["status_code"]))

    # --- Reset ---
    if name == "reset_automations":
        scope = str(tool_args.get("scope") or "all").strip().lower()
        if scope not in ("timers", "schedules", "custom_commands", "rules", "all", "devices", "factory"):
            return _err_resp("Phạm vi đặt lại không hợp lệ.", status_code=400)
        if scope == "factory" and tier != 1:
            return _err_resp("Chỉ chủ nhà cấp 1 mới được khôi phục cài đặt gốc ạ.", status_code=403, rbac_blocked=True)
        clear_all_users = bool(tool_args.get("clear_all_users", False))
        if clear_all_users and tier > 1:
            return _err_resp("Chỉ chủ nhà cấp 1 mới được đặt lại dữ liệu của toàn bộ thành viên ạ.", status_code=403, rbac_blocked=True)
        scope_vi = {
            "timers": "tất cả hẹn giờ",
            "schedules": "tất cả lịch trình",
            "custom_commands": "tất cả lệnh tùy chỉnh",
            "rules": "tất cả luật tự động",
            "all": "toàn bộ tự động hóa",
            "devices": "trạng thái các thiết bị về mặc định",
            "factory": "toàn bộ hệ thống về cài đặt gốc",
        }[scope]
        owner_note = " của mọi người" if (clear_all_users and tier == 1) else ""
        staged = await prepare_pending_mutation(
            engine=engine,
            session=session,
            source=source,
            session_key=skey,
            action_kind="reset_automations",
            payload={"scope": scope, "clear_all_users": clear_all_users},
            prompt_summary=f"Đặt lại {scope_vi}{owner_note}",
        )
        return _wrap_payload(dict(staged["payload"]), status_code=int(staged["status_code"]))

    return _err_resp(f"Công cụ '{name}' chưa được hỗ trợ.", status_code=400)
