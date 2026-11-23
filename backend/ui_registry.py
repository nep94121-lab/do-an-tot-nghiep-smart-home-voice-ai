"""Single Source of Truth for Web UI navigation, Automation workspace, controls, and guidance."""

from __future__ import annotations

import copy
import unicodedata
from typing import Any


def _strip_accents(text: str) -> str:
    s = str(text or "").replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in nfkd if unicodedata.category(ch) != "Mn")


def _norm(text: str) -> str:
    cleaned = _strip_accents(str(text or "").strip().lower())
    return " ".join("".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in cleaned).split())


UI_NAV_ITEMS: tuple[dict[str, str], ...] = (
    {
        "id": "overview",
        "label": "Tổng quan",
        "path": "/",
        "description": "Bảng điều khiển chính gồm mô hình 3D, 6 thiết bị, 3 cảm biến, trợ lý giọng nói và bảng Tự động hóa nhanh.",
    },
    {
        "id": "automation",
        "label": "Tự động hóa",
        "path": "/automation",
        "description": "Trang quản lý tập trung Hẹn giờ, Lịch trình, Lệnh tùy chỉnh, Luật tự động phức hợp và chế độ Ở nhà / Vắng nhà.",
    },
    {
        "id": "auth",
        "label": "Xác thực",
        "path": "/auth",
        "description": "Quản lý tài khoản, mã mời QR cho thành viên và khách, phân quyền 3 tầng và mã PIN chủ nhà.",
    },
    {
        "id": "hardware",
        "label": "Phần cứng",
        "path": "/wokwi",
        "description": "Mô phỏng mạch NodeMCU ESP8266 10 chân, sơ đồ nối dây 6 thiết bị và 3 cảm biến, mã nguồn firmware.",
    },
    {
        "id": "logs",
        "label": "Nhật ký",
        "path": "/logs",
        "description": "Nhật ký kiểm toán thiết bị, cảm biến, bảo mật và cơ sở dữ liệu SQLite (chỉ dành cho Chủ nhà Cấp 1).",
    },
)

AUTOMATION_TABS: tuple[dict[str, str], ...] = (
    {
        "id": "timers",
        "label": "Hẹn giờ",
        "create_button_id": "btnAutoCreateTimer",
        "create_button_label": "Tạo hẹn giờ",
        "description": "Hẹn giờ đếm ngược theo giây, phút hoặc giờ để bật/tắt/mở/đóng thiết bị.",
    },
    {
        "id": "schedules",
        "label": "Lịch trình",
        "create_button_id": "btnAutoCreateSchedule",
        "create_button_label": "Tạo lịch mới",
        "description": "Lịch đồng hồ theo giờ Việt Nam (một lần, hằng ngày hoặc theo các thứ trong tuần).",
    },
    {
        "id": "commands",
        "label": "Lệnh tùy chỉnh",
        "create_button_id": "btnAutoCreateCommand",
        "create_button_label": "Tạo lệnh mới",
        "description": "Kịch bản nhiều bước điều khiển đồng thời nhiều thiết bị chỉ bằng một khẩu lệnh.",
    },
    {
        "id": "rules",
        "label": "Luật tự động",
        "create_button_id": "btnAutoCreateRule",
        "create_button_label": "Tạo luật mới",
        "description": "Luật tự động đơn giản và phức hợp (VÀ / HOẶC) kết hợp cảm biến, trạng thái thiết bị, khung giờ và chế độ Ở nhà / Vắng nhà.",
    },
)

AUTOMATION_CONTROLS: dict[str, str] = {
    "house_mode_toggle_id": "btnToggleHouseMode",
    "house_mode_label": "Chế độ ở nhà / Vắng nhà",
    "reset_button_id": "btnAutoResetAll",
    "reset_button_label": "Đặt lại tự động hóa",
    "open_full_page_id": "lnkOpenAutomationPage",
    "open_full_page_label": "Mở trang Tự động hóa",
}

AUTOMATION_PANEL: dict[str, Any] = {
    "page_path": "/automation",
    "page_title": "Tự động hóa",
    "dashboard_panel_id": "secAutomation",
    "dashboard_panel_title": "Tự động hóa",
    "tabs": [dict(t) for t in AUTOMATION_TABS],
    "controls": dict(AUTOMATION_CONTROLS),
}

_NAV_BY_ID: dict[str, dict[str, str]] = {item["id"]: item for item in UI_NAV_ITEMS}
_TAB_BY_ID: dict[str, dict[str, str]] = {item["id"]: item for item in AUTOMATION_TABS}


def _build_guides() -> dict[str, dict[str, Any]]:
    nav_overview = _NAV_BY_ID["overview"]
    nav_auto = _NAV_BY_ID["automation"]
    nav_auth = _NAV_BY_ID["auth"]
    nav_hw = _NAV_BY_ID["hardware"]
    nav_logs = _NAV_BY_ID["logs"]

    tab_timers = _TAB_BY_ID["timers"]
    tab_schedules = _TAB_BY_ID["schedules"]
    tab_commands = _TAB_BY_ID["commands"]
    tab_rules = _TAB_BY_ID["rules"]

    panel_id = AUTOMATION_PANEL["dashboard_panel_id"]
    panel_title = AUTOMATION_PANEL["dashboard_panel_title"]
    open_page_btn = AUTOMATION_CONTROLS["open_full_page_label"]
    open_page_id = AUTOMATION_CONTROLS["open_full_page_id"]
    house_mode_btn = AUTOMATION_CONTROLS["house_mode_label"]
    house_mode_id = AUTOMATION_CONTROLS["house_mode_toggle_id"]
    reset_btn = AUTOMATION_CONTROLS["reset_button_label"]
    reset_id = AUTOMATION_CONTROLS["reset_button_id"]

    return {
        "timers": {
            "topic": "timers",
            "title": tab_timers["label"],
            "route": nav_auto["path"],
            "nav_id": nav_auto["id"],
            "nav_label": nav_auto["label"],
            "panel_id": panel_id,
            "panel_title": panel_title,
            "tab_id": tab_timers["id"],
            "tab_label": tab_timers["label"],
            "button_id": tab_timers["create_button_id"],
            "button_label": tab_timers["create_button_label"],
            "keywords": ("hen gio", "dem nguoc", "timer", "bao lau", "sau may phut", "sau may giay"),
            "steps": [
                f"Mở mục '{nav_auto['label']}' ({nav_auto['path']}) trên thanh điều hướng, hoặc xem khung '{panel_title}' ở trang '{nav_overview['label']}' ({nav_overview['path']}).",
                f"Chọn tab '{tab_timers['label']}'.",
                f"Nhấn nút '{tab_timers['create_button_label']}' để tạo mới, hoặc dùng các nút sửa/xóa trên từng hẹn giờ.",
            ],
        },
        "schedules": {
            "topic": "schedules",
            "title": tab_schedules["label"],
            "route": nav_auto["path"],
            "nav_id": nav_auto["id"],
            "nav_label": nav_auto["label"],
            "panel_id": panel_id,
            "panel_title": panel_title,
            "tab_id": tab_schedules["id"],
            "tab_label": tab_schedules["label"],
            "button_id": tab_schedules["create_button_id"],
            "button_label": tab_schedules["create_button_label"],
            "keywords": ("lich trinh", "dat lich", "lich dong ho", "hang ngay", "hang tuan", "schedule", "thu trong tuan"),
            "steps": [
                f"Mở mục '{nav_auto['label']}' ({nav_auto['path']}) trên thanh điều hướng, hoặc khung '{panel_title}' ở trang '{nav_overview['label']}'.",
                f"Chọn tab '{tab_schedules['label']}'.",
                f"Nhấn nút '{tab_schedules['create_button_label']}' để đặt giờ, chọn lặp hằng ngày hoặc các thứ trong tuần, hoặc bật/tắt/sửa/xóa lịch có sẵn.",
            ],
        },
        "custom_commands": {
            "topic": "custom_commands",
            "title": tab_commands["label"],
            "route": nav_auto["path"],
            "nav_id": nav_auto["id"],
            "nav_label": nav_auto["label"],
            "panel_id": panel_id,
            "panel_title": panel_title,
            "tab_id": tab_commands["id"],
            "tab_label": tab_commands["label"],
            "button_id": tab_commands["create_button_id"],
            "button_label": tab_commands["create_button_label"],
            "keywords": ("lenh tuy chinh", "lenh custom", "khau lenh", "ngu canh", "kich ban", "scene", "command"),
            "steps": [
                f"Mở mục '{nav_auto['label']}' ({nav_auto['path']}) trên thanh điều hướng, hoặc khung '{panel_title}' ở trang '{nav_overview['label']}'.",
                f"Chọn tab '{tab_commands['label']}'.",
                f"Nhấn nút '{tab_commands['create_button_label']}' để thêm khẩu lệnh nhiều bước, hoặc chạy/sửa/xóa các lệnh đã lưu.",
            ],
        },
        "rules": {
            "topic": "rules",
            "title": tab_rules["label"],
            "route": nav_auto["path"],
            "nav_id": nav_auto["id"],
            "nav_label": nav_auto["label"],
            "panel_id": panel_id,
            "panel_title": panel_title,
            "tab_id": tab_rules["id"],
            "tab_label": tab_rules["label"],
            "button_id": tab_rules["create_button_id"],
            "button_label": tab_rules["create_button_label"],
            "keywords": ("luat tu dong", "quy tac", "lien ket", "dieu kien", "rule", "tu dong bat", "tu dong tat"),
            "steps": [
                f"Mở mục '{nav_auto['label']}' ({nav_auto['path']}) trên thanh điều hướng, hoặc khung '{panel_title}' ở trang '{nav_overview['label']}'.",
                f"Chọn tab '{tab_rules['label']}'.",
                f"Nhấn nút '{tab_rules['create_button_label']}' để tạo luật điều kiện VÀ/HOẶC kèm hành động, hoặc bật/tắt/sửa/xóa luật hiện có.",
            ],
        },
        "house_mode": {
            "topic": "house_mode",
            "title": house_mode_btn,
            "route": nav_auto["path"],
            "nav_id": nav_auto["id"],
            "nav_label": nav_auto["label"],
            "panel_id": panel_id,
            "panel_title": panel_title,
            "tab_id": "",
            "tab_label": "",
            "button_id": house_mode_id,
            "button_label": house_mode_btn,
            "keywords": ("vang nha", "o nha", "che do nha", "hien dien", "house mode", "away", "home"),
            "steps": [
                f"Mở mục '{nav_auto['label']}' ({nav_auto['path']}) hoặc khung '{panel_title}' trên trang '{nav_overview['label']}'.",
                f"Nhấn nút '{house_mode_btn}' để chuyển nhanh giữa chế độ Ở nhà và Vắng nhà.",
            ],
        },
        "reset": {
            "topic": "reset",
            "title": reset_btn,
            "route": nav_auto["path"],
            "nav_id": nav_auto["id"],
            "nav_label": nav_auto["label"],
            "panel_id": panel_id,
            "panel_title": panel_title,
            "tab_id": "",
            "tab_label": "",
            "button_id": reset_id,
            "button_label": reset_btn,
            "keywords": ("dat lai", "reset", "xoa het", "khoi phuc"),
            "steps": [
                f"Mở mục '{nav_auto['label']}' ({nav_auto['path']}) hoặc khung '{panel_title}' trên trang '{nav_overview['label']}'.",
                f"Nhấn nút '{reset_btn}' và xác nhận để đặt lại các mục tự động hóa trong phạm vi quyền của bạn.",
            ],
        },
        "automation_overview": {
            "topic": "automation_overview",
            "title": nav_auto["label"],
            "route": nav_auto["path"],
            "nav_id": nav_auto["id"],
            "nav_label": nav_auto["label"],
            "panel_id": panel_id,
            "panel_title": panel_title,
            "tab_id": "",
            "tab_label": "",
            "button_id": open_page_id,
            "button_label": open_page_btn,
            "keywords": ("tu dong hoa", "automation", "trang tu dong", "bang tu dong", "cai dat tu dong"),
            "steps": [
                f"Nhấn mục '{nav_auto['label']}' trên thanh điều hướng để mở trang {nav_auto['path']}, hoặc bấm '{open_page_btn}' trong khung '{panel_title}' ở trang '{nav_overview['label']}'.",
                f"Tại đây có 4 tab: '{tab_timers['label']}', '{tab_schedules['label']}', '{tab_commands['label']}' và '{tab_rules['label']}', cùng nút '{house_mode_btn}' và '{reset_btn}'.",
            ],
        },
        "devices": {
            "topic": "devices",
            "title": "Điều khiển 6 thiết bị",
            "route": nav_overview["path"],
            "nav_id": nav_overview["id"],
            "nav_label": nav_overview["label"],
            "panel_id": "",
            "panel_title": "",
            "tab_id": "",
            "tab_label": "",
            "button_id": "",
            "button_label": "",
            "keywords": ("thiet bi", "cong tac", "bat tat", "den", "cua chinh", "may bom", "coi bao dong", "mach loa", "3d"),
            "steps": [
                f"Mở mục '{nav_overview['label']}' ({nav_overview['path']}) trên thanh điều hướng.",
                "Bạn có thể bấm trực tiếp trên thẻ thiết bị hoặc tương tác với mô hình nhà 3D để điều khiển 6 thiết bị trong quyền của mình.",
            ],
        },
        "sensors": {
            "topic": "sensors",
            "title": "Thông số cảm biến",
            "route": nav_overview["path"],
            "nav_id": nav_overview["id"],
            "nav_label": nav_overview["label"],
            "panel_id": "",
            "panel_title": "",
            "tab_id": "",
            "tab_label": "",
            "button_id": "",
            "button_label": "",
            "keywords": ("cam bien", "nhiet do", "do am", "do am dat", "am thanh", "dht11", "ky037", "ky 037", "sensor"),
            "steps": [
                f"Mở mục '{nav_overview['label']}' ({nav_overview['path']}) trên thanh điều hướng.",
                "Khu vực cảm biến hiển thị nhiệt độ và độ ẩm không khí DHT11, độ ẩm đất và trạng thái cảm biến âm thanh KY-037 theo thời gian thực.",
            ],
        },
        "voice": {
            "topic": "voice",
            "title": "Trợ lý giọng nói và lệnh văn bản",
            "route": nav_overview["path"],
            "nav_id": nav_overview["id"],
            "nav_label": nav_overview["label"],
            "panel_id": "",
            "panel_title": "",
            "tab_id": "",
            "tab_label": "",
            "button_id": "",
            "button_label": "",
            "keywords": ("giong noi", "micro", "mic", "tro ly", "noi lenh", "go lenh", "chat", "voice"),
            "steps": [
                f"Mở mục '{nav_overview['label']}' ({nav_overview['path']}) trên thanh điều hướng.",
                "Nhấn nút Micro để trò chuyện trực tiếp bằng giọng nói tiếng Việt hoặc nhập lệnh vào ô văn bản ngay tại khung Trợ lý AI.",
            ],
        },
        "auth": {
            "topic": "auth",
            "title": nav_auth["label"],
            "route": nav_auth["path"],
            "nav_id": nav_auth["id"],
            "nav_label": nav_auth["label"],
            "panel_id": "",
            "panel_title": "",
            "tab_id": "",
            "tab_label": "",
            "button_id": "",
            "button_label": "",
            "keywords": ("xac thuc", "tai khoan", "dang nhap", "phan quyen", "ma pin", "pin", "thanh vien", "auth"),
            "steps": [
                f"Nhấn mục '{nav_auth['label']}' ({nav_auth['path']}) trên thanh điều hướng.",
                "Tại đây bạn xem phiên đăng nhập, phân quyền 3 tầng, quản lý thành viên và mã PIN chủ nhà.",
            ],
        },
        "qr_invite": {
            "topic": "qr_invite",
            "title": "Mã mời QR cho thành viên và khách",
            "route": nav_auth["path"],
            "nav_id": nav_auth["id"],
            "nav_label": nav_auth["label"],
            "panel_id": "",
            "panel_title": "",
            "tab_id": "",
            "tab_label": "",
            "button_id": "",
            "button_label": "",
            "keywords": ("ma qr", "qr", "moi khach", "ma moi", "invite", "tao ma"),
            "steps": [
                f"Nhấn mục '{nav_auth['label']}' ({nav_auth['path']}) trên thanh điều hướng.",
                "Trong khu vực lời mời QR (chỉ dành cho Chủ nhà Cấp 1), bạn có thể tạo, xem thời hạn hoặc thu hồi mã mời cho Thành viên và Khách.",
            ],
        },
        "hardware": {
            "topic": "hardware",
            "title": nav_hw["label"],
            "route": nav_hw["path"],
            "nav_id": nav_hw["id"],
            "nav_label": nav_hw["label"],
            "panel_id": "",
            "panel_title": "",
            "tab_id": "",
            "tab_label": "",
            "button_id": "",
            "button_label": "",
            "keywords": ("phan cung", "wokwi", "esp8266", "mach", "so do chan", "firmware", "gpio", "hardware"),
            "steps": [
                f"Nhấn mục '{nav_hw['label']}' ({nav_hw['path']}) trên thanh điều hướng.",
                "Trang này hiển thị sơ đồ mạch Wokwi 10 chân ESP8266, bảng ánh xạ chân GPIO và mã nguồn firmware.",
            ],
        },
        "logs": {
            "topic": "logs",
            "title": nav_logs["label"],
            "route": nav_logs["path"],
            "nav_id": nav_logs["id"],
            "nav_label": nav_logs["label"],
            "panel_id": "",
            "panel_title": "",
            "tab_id": "",
            "tab_label": "",
            "button_id": "",
            "button_label": "",
            "keywords": ("nhat ky", "lich su", "log", "audit", "sqlite", "kiem toan"),
            "steps": [
                f"Nhấn mục '{nav_logs['label']}' ({nav_logs['path']}) trên thanh điều hướng (chỉ dành cho Chủ nhà Cấp 1).",
                "Tại đây bạn xem lịch sử thao tác thiết bị, sự kiện cảm biến, nhật ký bảo mật và trạng thái cơ sở dữ liệu.",
            ],
        },
    }


UI_GUIDES: dict[str, dict[str, Any]] = _build_guides()


def get_ui_registry() -> dict[str, Any]:
    """Return the canonical UI navigation, automation panel, and guidance registry."""
    return {
        "ok": True,
        "version": "1.0",
        "nav": [dict(item) for item in UI_NAV_ITEMS],
        "automation_panel": copy.deepcopy(AUTOMATION_PANEL),
        "guides": {k: copy.deepcopy(v) for k, v in UI_GUIDES.items()},
    }


_TOPIC_ALIASES: dict[str, str] = {
    "timer": "timers",
    "timers": "timers",
    "hen_gio": "timers",
    "schedule": "schedules",
    "schedules": "schedules",
    "lich": "schedules",
    "lich_trinh": "schedules",
    "command": "custom_commands",
    "commands": "custom_commands",
    "custom_command": "custom_commands",
    "custom_commands": "custom_commands",
    "scene": "custom_commands",
    "scenes": "custom_commands",
    "rule": "rules",
    "rules": "rules",
    "automation_rule": "rules",
    "automation_rules": "rules",
    "compound_rules": "rules",
    "device": "devices",
    "devices": "devices",
    "sensor": "sensors",
    "sensors": "sensors",
    "voice": "voice",
    "mic": "voice",
    "house_mode": "house_mode",
    "presence": "house_mode",
    "away": "house_mode",
    "auth": "auth",
    "account": "auth",
    "qr": "qr_invite",
    "qr_invite": "qr_invite",
    "invite": "qr_invite",
    "log": "logs",
    "logs": "logs",
    "audit": "logs",
    "hardware": "hardware",
    "wokwi": "hardware",
    "reset": "reset",
    "automation": "automation_overview",
    "automation_overview": "automation_overview",
}


def _match_guide_topic(query: str = "", topic: str = "") -> str:
    t_key = _norm(topic).replace(" ", "_")
    if t_key in _TOPIC_ALIASES:
        return _TOPIC_ALIASES[t_key]
    if t_key in UI_GUIDES:
        return t_key

    q_norm = _norm(query)
    if not q_norm:
        return "automation_overview"
    padded = f" {q_norm} "

    # Score by longest keyword matches so specific tabs win over general overview
    best_topic = ""
    best_score = 0
    for key, guide in UI_GUIDES.items():
        score = 0
        for kw in guide.get("keywords", ()):
            kw_n = _norm(kw)
            if kw_n and (f" {kw_n} " in padded or kw_n in q_norm):
                score = max(score, len(kw_n) + (5 if key != "automation_overview" else 0))
        if score > best_score:
            best_score = score
            best_topic = key

    return best_topic or "automation_overview"


def get_ui_guidance(query: str = "", topic: str = "") -> dict[str, Any]:
    """Answer UI navigation / 'where is X / what to click' questions strictly from the registry."""
    matched_topic = _match_guide_topic(query=query, topic=topic)
    guide = copy.deepcopy(UI_GUIDES[matched_topic])
    steps = list(guide.get("steps") or [])

    if guide.get("tab_label") and guide.get("button_label"):
        reply = (
            f"Bạn mở mục '{guide['nav_label']}' ({guide['route']}) hoặc khung '{guide['panel_title']}' "
            f"trên trang '{_NAV_BY_ID['overview']['label']}', chọn tab '{guide['tab_label']}', "
            f"rồi bấm nút '{guide['button_label']}'."
        )
    elif guide.get("button_label"):
        reply = (
            f"Bạn mở mục '{guide['nav_label']}' ({guide['route']}) hoặc khung '{guide['panel_title']}' "
            f"trên trang '{_NAV_BY_ID['overview']['label']}', rồi bấm nút '{guide['button_label']}'."
        )
    else:
        reply = " ".join(steps)

    return {
        "ok": True,
        "topic": matched_topic,
        "title": guide["title"],
        "route": guide["route"],
        "nav_id": guide["nav_id"],
        "nav_label": guide["nav_label"],
        "panel_id": guide.get("panel_id", ""),
        "panel_title": guide.get("panel_title", ""),
        "tab_id": guide.get("tab_id", ""),
        "tab_label": guide.get("tab_label", ""),
        "button_id": guide.get("button_id", ""),
        "button_label": guide.get("button_label", ""),
        "steps": steps,
        "reply": reply,
        "exact_spoken_reply": reply,
    }
