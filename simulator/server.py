"""Máy chủ Mô phỏng Nhà Thông Minh 3D (Smart Home Voice AI Simulator) kết nối Gemini 3.8 Live.

Hỗ trợ đầy đủ:
1. Hẹn giờ & Sửa/Hủy hẹn giờ theo Giây, Phút, Giờ hoặc theo Giờ Việt Nam (AM/PM, GMT+7).
2. Đổi từ (Word/Vocabulary Mapping): Đổi cách gọi tên thiết bị hoặc hành động.
3. Đổi lệnh (Command Phrase Remapping): Gán khẩu lệnh mới (VD: "Vừng ơi mở ra" -> mở cửa).
4. Quan hệ IF-THEN-ELSE theo Trạng thái Thiết bị (State-Driven) vs theo Khẩu lệnh:
   - Khi có luật IF-ELSE "Nếu cửa mở thì bật điều hòa, nếu cửa đóng thì tắt điều hòa":
   - Bất kể cửa được mở bằng câu gốc "Mở cửa", hay bằng khẩu lệnh đã đổi "Vừng ơi mở ra",
     hay bằng hẹn giờ, sự kiện `main_door -> OPEN` đều tự động kéo theo `ac -> ON` (Điều hòa bật)!
"""

from __future__ import annotations

import asyncio
import base64
import json
import pathlib
import time
import wave
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types

from simulator.knowledge_rag import SmartHomeKnowledgeRAG
from simulator.rule_engine import SmartHomeEngine, format_vn_time_ampm
from simulator.voice_auth import VoiceAuthManager, extract_voice_features

ROOT = pathlib.Path(__file__).resolve().parent.parent
SIM_DIR = pathlib.Path(__file__).resolve().parent
STATIC_DIR = SIM_DIR / "static"
AUDIO_DIR = ROOT / "test_audio"
MODEL = "gemini-3.8-live"

# Khởi tạo sẵn 2 mẫu giọng (Giọng 1: Chủ nhà được phép, Giọng 2: Người lạ không được phép)
_BOOT_VOICE_AUTH = VoiceAuthManager(AUDIO_DIR)
_KNOWLEDGE_RAG: SmartHomeKnowledgeRAG | None = None


def get_knowledge_rag() -> SmartHomeKnowledgeRAG:
    global _KNOWLEDGE_RAG
    if _KNOWLEDGE_RAG is None:
        _KNOWLEDGE_RAG = SmartHomeKnowledgeRAG(api_key=KEY)
    return _KNOWLEDGE_RAG

CHUNK_MS = 20
CHUNK_SAMPLES = 16000 * CHUNK_MS // 1000
SILENCE = b"\x00\x00" * CHUNK_SAMPLES

VOICE_SAMPLES_META: dict[str, str] = {
    "giong_1_chu_nha_mo_cua": "✅ Giọng 1 (Được phép): Mở cửa chính",
    "giong_2_nguoi_la_mo_cua": "🚫 Giọng 2 (Không phép): Mở cửa chính",
    "mo_cua_chinh": "Mở cửa chính",
    "bat_den_phong_khach": "Bật đèn phòng khách",
    "tat_quat": "Tắt quạt",
    "bat_quat_va_dieu_hoa": "Bật quạt trần và bật điều hòa giúp tôi",
    "hen_gio_5s_tat_den": "Năm giây nữa tắt đèn phòng khách nhé",
    "day_lenh_di_ngu": "Từ giờ khi tôi nói chế độ đi ngủ thì tắt đèn phòng khách và đóng cửa chính nhé",
    "kich_hoat_di_ngu": "Chế độ đi ngủ",
    "reset_he_thong": "Reset hệ thống về mặc định",
}


def load_key() -> str:
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("Không tìm thấy GEMINI_API_KEY trong .env")


KEY = load_key()


def safe_str(msg: object) -> str:
    return str(msg).replace(KEY, "***")


# ---------------------------------------------------------------------------
# Khai báo các Function Declarations cho Gemini 3.8 Live
# ---------------------------------------------------------------------------
DEVICE_ENUM = [
    "main_door",
    "living_room_light",
    "bedroom_light",
    "fan",
    "ac",
    "alarm_siren",
    "garden_pump",
    "all_lights",
    "all_devices",
]
ACTION_ENUM = ["open", "close", "turn_on", "turn_off"]

fn_control_device = types.FunctionDeclaration(
    name="control_device",
    description=(
        "Bật/tắt hoặc mở/đóng thiết bị trong nhà ngay lập tức. "
        "Lưu ý: Nếu người dùng dùng từ đã đổi (word_mapping) hoặc khẩu lệnh đã đổi (alias), "
        "hãy dịch sang device_id và action chuẩn rồi gọi hàm này (hoặc gọi execute_alias_rule). "
        "Hệ thống sẽ tự động kích hoạt các luật IF-ELSE gắn với trạng thái mới của thiết bị."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "device_id": {
                "type": "STRING",
                "enum": DEVICE_ENUM,
                "description": (
                    "Mã thiết bị: main_door (cửa chính), living_room_light (đèn phòng khách), "
                    "bedroom_light (đèn phòng ngủ), fan (quạt trần), ac (điều hòa), "
                    "alarm_siren (còi báo động), garden_pump (máy bơm tưới cây), "
                    "all_lights (tất cả đèn), all_devices (tất cả thiết bị)."
                ),
            },
            "action": {
                "type": "STRING",
                "enum": ACTION_ENUM,
                "description": "Hành động: open (mở), close (đóng), turn_on (bật), turn_off (tắt).",
            },
        },
        "required": ["device_id", "action"],
    },
)

fn_schedule_action = types.FunctionDeclaration(
    name="schedule_action",
    description=(
        "Đặt hẹn giờ để bật/tắt/mở/đóng thiết bị:\n"
        "- MẶC ĐỊNH HẸN GIỜ 1 LẦN (`repeat='once'`): chạy xong 1 lần là tự dừng.\n"
        "- Khi người dùng nói 'hàng ngày'/'mỗi ngày' -> `repeat='daily'`; 'hàng tuần'/'mỗi tuần' -> `repeat='weekly'`; 'hàng giờ' -> `repeat='hourly'`; 'hàng tháng' -> `repeat='monthly'`.\n"
        "- Hẹn đếm ngược ('10 giây nữa'): truyền `seconds`/`minutes`/`hours`, để trống `vn_time_ampm=''` và `vn_date=''`.\n"
        "- Hẹn giờ có AM/PM ('8:00 AM', '8:00 PM'): truyền `vn_time_ampm='8:00 PM'`.\n"
        "- Hẹn giờ KHÔNG nói AM/PM ('8:00'): truyền `vn_time_ampm='8:00'` (hệ thống tự đặt cả 8:00 AM và 8:00 PM).\n"
        "- Hẹn kèm ngày/tháng ('ngày 25/10', 'ngày mai'): truyền `vn_date='25/10'`."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "device_id": {"type": "STRING", "enum": DEVICE_ENUM},
            "action": {"type": "STRING", "enum": ACTION_ENUM},
            "hours": {"type": "NUMBER", "description": "Số giờ đếm ngược (chỉ dùng khi nói '... giờ nữa')."},
            "minutes": {"type": "NUMBER", "description": "Số phút đếm ngược (chỉ dùng khi nói '... phút nữa')."},
            "seconds": {"type": "NUMBER", "description": "Số giây đếm ngược (chỉ dùng khi nói '... giây nữa')."},
            "vn_time_ampm": {
                "type": "STRING",
                "description": (
                    "Mốc giờ đồng hồ (VD: '8:00 AM', '8:00 PM', hoặc '8:00' nếu người dùng không nói AM/PM). "
                    "BẮT BUỘC ĐỂ TRỐNG '' nếu người dùng hẹn theo giây/phút/giờ đếm ngược."
                ),
            },
            "vn_date": {
                "type": "STRING",
                "description": "Ngày/tháng nếu người dùng có nói rõ (VD: '25/10', 'ngày mai'). BẮT BUỘC ĐỂ TRỐNG '' nếu người dùng không nhắc tới ngày.",
            },
            "repeat": {
                "type": "STRING",
                "enum": ["once", "daily", "weekly", "hourly", "monthly"],
                "description": "Mặc định 'once' (chỉ chạy 1 lần rồi dừng). Chọn 'daily' (hàng ngày), 'weekly' (hàng tuần), 'hourly' (hàng giờ), 'monthly' (hàng tháng) khi người dùng nói lặp lại.",
            },
        },
        "required": ["device_id", "action"],
    },
)

fn_update_timer = types.FunctionDeclaration(
    name="update_timer",
    description=(
        "Sửa đổi thời gian/hành động của một bộ hẹn giờ đang chạy hoặc hủy hẹn giờ "
        "(VD: 'Sửa lại hẹn giờ tắt đèn thành 15 giây nữa', 'Đổi hẹn giờ điều hòa sang 8:00 PM', 'Hủy hẹn giờ quạt')."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "device_id": {"type": "STRING", "enum": DEVICE_ENUM},
            "operation": {
                "type": "STRING",
                "enum": ["modify", "cancel"],
                "description": "modify (sửa lại thời gian hẹn giờ) hoặc cancel (hủy bỏ hẹn giờ).",
            },
            "new_action": {"type": "STRING", "enum": ACTION_ENUM},
            "hours": {"type": "NUMBER", "description": "Số giờ đếm ngược mới."},
            "minutes": {"type": "NUMBER", "description": "Số phút đếm ngược mới."},
            "seconds": {"type": "NUMBER", "description": "Số giây đếm ngược mới."},
            "vn_time_ampm": {
                "type": "STRING",
                "description": "Mốc giờ đồng hồ mới (VD: '8:00 AM', '8:00 PM', hoặc '8:00' cho cả AM và PM).",
            },
            "vn_date": {
                "type": "STRING",
                "description": "Ngày/tháng mới nếu người dùng có nói rõ (VD: '25/10', 'ngày mai').",
            },
            "repeat": {
                "type": "STRING",
                "enum": ["once", "daily", "weekly", "hourly", "monthly"],
                "description": "Mặc định 'once' (1 lần rồi dừng). Chọn 'daily'/'weekly'/'hourly'/'monthly' nếu người dùng nói lặp lại.",
            },
        },
        "required": ["device_id", "operation"],
    },
)

fn_set_word_mapping = types.FunctionDeclaration(
    name="set_word_mapping",
    description=(
        "ĐỔI TỪ (Word / Vocabulary Mapping): Khi người dùng muốn đổi tên gọi của một thiết bị hoặc một từ hành động "
        "(VD: 'Từ giờ gọi điều hòa là máy lạnh', 'Gọi cửa chính là cổng rồng', 'Từ khởi động nghĩa là bật')."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "custom_word": {
                "type": "STRING",
                "description": "Từ hoặc tên gọi mới do người dùng đặt (VD: 'máy lạnh', 'cổng rồng', 'khởi động').",
            },
            "target_meaning": {
                "type": "STRING",
                "description": "Thiết bị hoặc hành động gốc tương ứng (VD: 'ac (Điều hòa)', 'main_door (Cửa chính)', 'turn_on (Bật)').",
            },
        },
        "required": ["custom_word", "target_meaning"],
    },
)

fn_create_alias_rule = types.FunctionDeclaration(
    name="create_alias_rule",
    description=(
        "ĐỔI LỆNH / GÁN KHẨU LỆNH (Command Phrase Remapping): Khi người dùng muốn đổi cả câu lệnh mở/đóng/bật/tắt "
        "hoặc tạo khẩu lệnh riêng cho 1 hay nhiều thiết bị. "
        "VD: 'Đổi lệnh mở cửa thành Vừng ơi mở ra' -> phrase='vừng ơi mở ra', target_devices_csv='main_door', target_actions_csv='open'. "
        "Lưu ý: Đổi lệnh cho 1 hành động KHÁC với luật IF-ELSE giữa 2 thiết bị."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "phrase": {
                "type": "STRING",
                "description": "Khẩu lệnh bằng tiếng Việt (VD: 'vừng ơi mở ra', 'chế độ đi ngủ').",
            },
            "target_devices_csv": {
                "type": "STRING",
                "description": "Danh sách mã thiết bị cách nhau dấu phẩy (VD: 'main_door' hoặc 'living_room_light,main_door').",
            },
            "target_actions_csv": {
                "type": "STRING",
                "description": "Danh sách hành động tương ứng cách nhau dấu phẩy (VD: 'open' hoặc 'turn_off,close').",
            },
        },
        "required": ["phrase", "target_devices_csv", "target_actions_csv"],
    },
)

fn_execute_alias_rule = types.FunctionDeclaration(
    name="execute_alias_rule",
    description=(
        "Kích hoạt một khẩu lệnh / kịch bản đã được đổi hoặc dạy trước đó (VD: 'vừng ơi mở ra', 'chế độ đi ngủ', 'ra ngoài'). "
        "Khi hàm này chạy, các thiết bị trong khẩu lệnh sẽ đổi trạng thái và TỰ ĐỘNG kích hoạt luôn mọi luật IF-ELSE liên quan!"
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "phrase": {
                "type": "STRING",
                "description": "Khẩu lệnh cần kích hoạt.",
            },
        },
        "required": ["phrase"],
    },
)

fn_set_if_else_rule = types.FunctionDeclaration(
    name="set_if_else_rule",
    description=(
        "Thiết lập QUAN HỆ IF SÁT NGHĨA giữa các thiết bị theo TRẠNG THÁI (State-Driven).\n"
        "- QUY TẮC SÁT NGHĨA 1 CHIỀU (CỰC KỲ QUAN TRỌNG): Nếu người dùng chỉ nói 1 chiều (VD: 'Nếu mở cửa chính thì mở điều hòa'), "
        "BẮT BUỘC ĐỂ TRỐNG `else_device_id=''` và `else_action=''`! TUYỆT ĐỐI KHÔNG tự suy diễn 'đóng cửa thì tắt điều hòa'. "
        "Khi đó, nếu đóng cửa chính thì điều hòa vẫn giữ nguyên không tắt.\n"
        "- Chỉ khi nào người dùng nói rõ cả chiều ngược lại (VD: 'Nếu mở cửa thì mở điều hòa, còn đóng cửa thì tắt điều hòa' "
        "hoặc 'Cho cửa chính và điều hòa đồng bộ đóng mở cùng nhau') thì mới điền `else_device_id` và `else_action`.\n"
        "- Nhờ bám theo trạng thái phần cứng `main_door=OPEN`, nên dù mở cửa bằng lệnh gốc hay lệnh đã đổi ('Vừng ơi mở ra'), "
        "hễ cửa mở là điều hòa tự động mở theo!"
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "when_device_id": {"type": "STRING", "enum": DEVICE_ENUM[:7]},
            "when_state": {
                "type": "STRING",
                "enum": ["ON", "OFF", "OPEN", "CLOSED"],
                "description": "Trạng thái điều kiện IF của thiết bị nguồn (ON, OFF, OPEN, CLOSED).",
            },
            "then_device_id": {"type": "STRING", "enum": DEVICE_ENUM[:7]},
            "then_action": {"type": "STRING", "enum": ACTION_ENUM},
            "delay_seconds": {
                "type": "NUMBER",
                "description": "Độ trễ (giây) trước khi thực thi nhánh THEN (mặc định 0 = làm ngay lập tức).",
            },
            "else_device_id": {
                "type": "STRING",
                "description": "(Tùy chọn) BẮT BUỘC ĐỂ TRỐNG '' nếu người dùng chỉ nói 1 chiều. Chỉ điền khi người dùng nói rõ cả vế ngược lại.",
            },
            "else_action": {
                "type": "STRING",
                "description": "(Tùy chọn) BẮT BUỘC ĐỂ TRỐNG '' nếu người dùng chỉ nói 1 chiều. Chỉ điền khi người dùng nói rõ cả vế ngược lại.",
            },
            "evaluate_now": {
                "type": "BOOLEAN",
                "description": "True nếu chỉ muốn kiểm tra trạng thái hiện tại và chạy 1 lần ngay lập tức; False (mặc định) nếu lưu làm luật tự động.",
            },
        },
        "required": ["when_device_id", "when_state", "then_device_id", "then_action"],
    },
)

fn_query_pools = types.FunctionDeclaration(
    name="query_pools",
    description=(
        "Truy vấn thông tin 2 BỂ hoặc hỏi lệnh của 1 thiết bị:\n"
        "- `query_type='timers'`: Khi hỏi đang có bao nhiêu lịch hẹn giờ, là những lịch nào.\n"
        "- `query_type='rules'`: Khi hỏi đang có những luật/đổi từ/đổi lệnh nào.\n"
        "- `query_type='device_command'` kèm `target_device_id`: Khi hỏi lệnh của 1 thiết bị (VD: 'Lệnh mở cửa là như nào?' -> target_device_id='main_door').\n"
        "- `query_type='all'`: Khi hỏi tổng quan cả 2 bể."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "query_type": {
                "type": "STRING",
                "enum": ["timers", "rules", "device_command", "all"],
                "description": "Loại thông tin cần hỏi: 'timers' (hẹn giờ), 'rules' (luật/đổi từ/đổi lệnh), 'device_command' (hỏi lệnh của 1 thiết bị), hoặc 'all' (cả 2 bể).",
            },
            "target_device_id": {
                "type": "STRING",
                "description": "Mã thiết bị nếu người dùng hỏi lệnh của thiết bị cụ thể (VD: 'main_door' khi hỏi 'lệnh mở cửa là như nào?').",
            },
        },
    },
)

fn_query_knowledge_rag = types.FunctionDeclaration(
    name="query_knowledge_rag",
    description=(
        "Truy xuất Bể Tri Thức RAG (sử dụng Google Embedding `gemini-embedding-001`) khi người dùng hỏi:\n"
        "- 'Bạn là ai?', 'Bạn tên gì?'\n"
        "- 'Bạn được ai tạo ra?', 'Ai làm ra bạn?'\n"
        "- 'Bạn được làm những gì?', 'Bạn có thể làm những gì?', 'Chức năng của bạn là gì?'\n"
        "- Hoặc hỏi về giới hạn quyền hạn, số lượng thiết bị phần cứng trong nhà."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "question": {
                "type": "STRING",
                "description": "Câu hỏi nguyên văn của người dùng (VD: 'Bạn là ai và được ai tạo ra?').",
            },
        },
        "required": ["question"],
    },
)

fn_request_factory_reset = types.FunctionDeclaration(
    name="request_factory_reset",
    description=(
        "Bước 1 của 4 loại Reset (có hỏi xác nhận):\n"
        "- `scope='voice'`: Khi người dùng nói 'reset giọng nói', 'xóa giọng nói', 'reset quyền giọng nói chỉ về của tôi'.\n"
        "- `scope='timers'`: Khi người dùng nói 'reset đặt thời gian', 'reset thời gian', 'reset hẹn giờ', 'xóa hết hẹn giờ'.\n"
        "- `scope='rules'`: Khi người dùng nói 'reset luật', 'reset đổi từ đổi lệnh', 'xóa hết luật'.\n"
        "- `scope='all'`: Khi người dùng nói 'reset', 'reset tất cả', 'reset hệ thống'."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "scope": {
                "type": "STRING",
                "enum": ["voice", "timers", "rules", "all"],
                "description": "Phạm vi cần reset: 'voice' (chỉ giọng nói về của bạn), 'timers' (chỉ đặt thời gian/hẹn giờ), 'rules' (chỉ luật/đổi từ/đổi lệnh), hoặc 'all' (tất cả).",
            },
        },
    },
)

fn_confirm_factory_reset = types.FunctionDeclaration(
    name="confirm_factory_reset",
    description=(
        "Xác nhận (hoặc hủy) hành động đang chờ xác nhận (bao gồm Xác nhận Lưu Luật Mới hoặc Xác nhận Reset Hệ Thống). "
        "Gọi hàm này khi người dùng trả lời 'Đúng rồi', 'Có', 'Ok', 'Đồng ý', 'Xác nhận' (-> confirmed=True) "
        "hoặc 'Không', 'Hủy' (-> confirmed=False)."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "confirmed": {
                "type": "BOOLEAN",
                "description": "True nếu người dùng đồng ý xác nhận; False nếu người dùng từ chối/hủy.",
            },
        },
        "required": ["confirmed"],
    },
)

fn_confirm_pending_action = types.FunctionDeclaration(
    name="confirm_pending_action",
    description=(
        "Bước 2 khi Xét Luật / Đổi Lệnh / Đổi Từ hoặc Reset: Gọi hàm này khi người dùng trả lời xác nhận "
        "('Đúng rồi', 'Ok', 'Đồng ý', 'Xác nhận' -> confirmed=True; 'Không', 'Hủy' -> confirmed=False) "
        "sau khi AI đã nhắc lại luật hoặc hỏi xác nhận reset."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "confirmed": {
                "type": "BOOLEAN",
                "description": "True nếu người dùng đồng ý; False nếu từ chối.",
            },
        },
        "required": ["confirmed"],
    },
)

fn_start_voice_enrollment = types.FunctionDeclaration(
    name="start_voice_enrollment",
    description=(
        "BẬT THU ÂM GIỌNG NÓI ĐỂ CẤP QUYỀN CHO NGƯỜI MỚI (Cấp 2 hoặc Cấp 3):\n"
        "- Gọi hàm này khi người dùng nói: 'Tôi cần thêm người mới, bật ghi âm để thu âm', 'Thu âm giọng nói để cấp quyền', 'Cấp quyền giọng nói cho cấp 2 / cấp 3', 'Ghi âm cấp quyền'.\n"
        "- Hệ thống sẽ tự động: Đếm 3, 2, 1 -> Nháy đèn 1 phát báo hiệu bắt đầu -> Thu âm giọng nói trong vài giây -> Báo đã thu âm đủ -> Phân tích tần số giọng nói -> Báo đã phân tích xong và hỏi tên người được cấp quyền (nếu chưa có tên).\n"
        "- Lưu ý: Cấp 1 (Nguyễn Tuấn Anh) được thu âm cấp quyền cho Cấp 2 hoặc Cấp 3; Cấp 2 chỉ được thu âm cấp quyền cho Cấp 3 (Khách)."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "target_tier": {
                "type": "INTEGER",
                "description": "Cấp quyền muốn cấp: 2 (Thành viên gia đình) hoặc 3 (Khách). Mặc định là 3.",
            },
            "target_name": {
                "type": "STRING",
                "description": "Tên người được cấp quyền nếu người dùng đã nói sẵn (VD: 'Minh', 'Nam'). Để trống '' nếu chưa nói tên (hệ thống sẽ hỏi tên sau khi phân tích xong).",
            },
            "duration_seconds": {
                "type": "INTEGER",
                "description": "Số giây thu âm (mặc định 5 giây).",
            },
        },
    },
)

fn_finalize_voice_enrollment = types.FunctionDeclaration(
    name="finalize_voice_enrollment",
    description=(
        "Lưu tên cho người vừa được thu âm và phân tích giọng nói xong (khi người dùng trả lời câu hỏi 'Người ấy tên là gì?', VD: 'Tên là Minh', 'Người đó là Hùng')."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "target_name": {
                "type": "STRING",
                "description": "Tên của người vừa được thu âm giọng nói (VD: 'Minh', 'Hùng', 'Lan').",
            },
            "target_tier": {
                "type": "INTEGER",
                "description": "Cấp quyền (2 hoặc 3, tùy chọn).",
            },
        },
        "required": ["target_name"],
    },
)

fn_grant_permission = types.FunctionDeclaration(
    name="grant_user_permission",
    description=(
        "Cấp quyền cho người dùng theo hệ thống phân quyền 3 tầng (hoặc hoàn tất đặt tên sau khi thu âm giọng nói):\n"
        "- Tầng 1 (Nguyễn Tuấn Anh) được cấp quyền Tầng 2 (Thành viên gia đình) hoặc Tầng 3 (Khách).\n"
        "- Tầng 2 (Thành viên gia đình) chỉ được cấp quyền cho Tầng 3 (Khách).\n"
        "- Tầng 3 (Khách) không được cấp quyền cho ai."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "target_name": {
                "type": "STRING",
                "description": "Tên người được cấp quyền (VD: 'Khách D', 'Thành viên B', 'Minh').",
            },
            "target_tier": {
                "type": "INTEGER",
                "description": "Tầng quyền muốn cấp: 2 (Thành viên gia đình) hoặc 3 (Khách). Mặc định là 3.",
            },
        },
        "required": ["target_name"],
    },
)

fn_revoke_permission = types.FunctionDeclaration(
    name="revoke_user_permission",
    description=(
        "Hủy quyền của người dùng theo hệ thống phân quyền 3 tầng:\n"
        "- Tầng 1 (Nguyễn Tuấn Anh) hủy được quyền của bất kỳ ai ở Tầng 2 và Tầng 3.\n"
        "- Những ai được Tầng 1 trực tiếp cấp quyền (dù ở Tầng 2 hay Tầng 3) thì ngoài Tầng 1 ra KHÔNG AI được phép hủy.\n"
        "- Tầng 2 chỉ được hủy quyền của Khách Tầng 3 do Tầng 2 cấp; KHÔNG được hủy cùng cấp Tầng 2."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "target_name": {
                "type": "STRING",
                "description": "Tên người cần hủy quyền (VD: 'Khách C', 'Khách D', 'Thành viên B').",
            },
        },
        "required": ["target_name"],
    },
)

fn_set_query_permission_policy = types.FunctionDeclaration(
    name="set_query_permission_policy",
    description=(
        "Thay đổi quy tắc phân quyền trả lời câu hỏi của hệ thống (CHỈ Cấp 1 Nguyễn Tuấn Anh mới có quyền gọi):\n"
        "- `mode='open_all'`: Khi Cấp 1 nói 'Chỉnh tất cả ai cũng có thể hỏi', 'Bạn có thể trả lời tất cả những cái gì mà bạn biết', 'Mở quyền hỏi cho tất cả các cấp'.\n"
        "- `mode='tier_restricted'`: Khi Cấp 1 nói 'Từng tầng chỉ được hỏi của quyền tầng đấy thôi', 'Giới hạn quyền hỏi theo từng cấp'."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "mode": {
                "type": "STRING",
                "enum": ["open_all", "tier_restricted"],
                "description": "'open_all' (ai hỏi cũng trả lời tất cả) hoặc 'tier_restricted' (cấp nào chỉ được trả lời trong phạm vi quyền của cấp đó; riêng Cấp 1 được trả lời tất cả).",
            },
        },
        "required": ["mode"],
    },
)

fn_admin_update_system_policy = types.FunctionDeclaration(
    name="admin_update_system_policy",
    description=(
        "SỬA ĐỔI BẤT KỲ QUY TẮC HỆ THỐNG, PHÂN QUYỀN CẤP 2 / CẤP 3, QUYỀN THIẾT BỊ HOẶC LUẬT ỨNG XỬ BẰNG GIỌNG NÓI (CHỈ DÀNH CHO ADMIN CẤP 1 NGUYỄN TUẤN ANH):\n"
        "- Gọi hàm này khi Admin Cấp 1 ra lệnh sửa luật hệ thống bằng giọng nói mà không cần sửa code, ví dụ:\n"
        "  + 'Cho phép cấp 3 được hẹn giờ' -> policy_key='tier3_can_schedule_timer', policy_value='true'\n"
        "  + 'Cấm cấp 3 hẹn giờ' -> policy_key='tier3_can_schedule_timer', policy_value='false'\n"
        "  + 'Cho phép cấp 3 được đổi lệnh và đặt luật IF-ELSE' -> policy_key='tier3_can_custom_rules', policy_value='true'\n"
        "  + 'Cho phép cấp 3 cấp quyền' -> policy_key='tier3_can_grant_revoke', policy_value='true'\n"
        "  + 'Cho phép cấp 2 được cấp quyền cấp 2' -> policy_key='tier2_can_grant_tier2', policy_value='true'\n"
        "  + 'Cho phép cấp 2 hủy quyền cùng cấp' -> policy_key='tier2_can_revoke_same_tier', policy_value='true'\n"
        "  + 'Cho phép cấp 2 sửa hẹn giờ hoặc luật của cấp 1' -> policy_key='tier2_can_override_tier1', policy_value='true'\n"
        "  + 'Khi xét luật mới không cần hỏi xác nhận lại nữa, lưu thẳng luôn' -> policy_key='require_rule_confirmation', policy_value='false'\n"
        "  + 'Khi gọi reset thì reset luôn không cần hỏi lại' -> policy_key='require_reset_confirmation', policy_value='false'\n"
        "  + 'Khi thu âm cấp quyền thì nháy đèn phòng ngủ thay vì đèn phòng khách' -> policy_key='enrollment_signal_device_id', target_device_id='bedroom_light'\n"
        "  + 'Chỉnh thời gian thu âm cấp quyền thành 8 giây' -> policy_key='enrollment_duration_seconds', policy_value='8'\n"
        "  + 'Cấm cấp 3 mở cửa chính, chỉ cấp 1 và cấp 2 mới được mở cửa chính' -> policy_key='device_min_tier', target_device_id='main_door', policy_value='2'\n"
        "  + 'Chỉ mình tôi cấp 1 mới được bật còi báo động' -> policy_key='device_min_tier', target_device_id='alarm_siren', policy_value='1'\n"
        "  + Bất kỳ quy định/luật mới nào Admin nói tự nhiên (không cần câu mở đầu máy móc, VD: 'Sau 11 giờ đêm cấm cấp 3 mở cửa chính', 'Khi trả lời nhớ gọi tôi là anh Tuấn Anh') -> policy_key='custom_directive_add', policy_value='<nội dung quy định>'."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "policy_key": {
                "type": "STRING",
                "enum": [
                    "query_permission_mode",
                    "tier3_can_schedule_timer",
                    "tier3_can_custom_rules",
                    "tier3_can_grant_revoke",
                    "tier2_can_grant_tier2",
                    "tier2_can_revoke_same_tier",
                    "tier2_can_override_tier1",
                    "require_rule_confirmation",
                    "require_reset_confirmation",
                    "enrollment_signal_device_id",
                    "enrollment_duration_seconds",
                    "device_min_tier",
                    "custom_directive_add",
                    "custom_directive_remove",
                ],
                "description": "Mã quy tắc hệ thống cần sửa.",
            },
            "policy_value": {
                "type": "STRING",
                "description": "Giá trị mới ('true'/'false', số cấp '1'/'2'/'3', số giây, hoặc nội dung quy tắc tự do).",
            },
            "target_device_id": {
                "type": "STRING",
                "description": "(Tùy chọn) Mã thiết bị khi chỉnh quyền thiết bị ('device_min_tier') hoặc đổi thiết bị nháy tín hiệu thu âm ('enrollment_signal_device_id').",
            },
        },
        "required": ["policy_key", "policy_value"],
    },
)

fn_admin_upsert_knowledge_rag = types.FunctionDeclaration(
    name="admin_upsert_knowledge_rag",
    description=(
        "DẠY THÊM HOẶC SỬA NỘI DUNG TRONG BỘ NHỚ TRI THỨC RAG BẰNG GIỌNG NÓI (CHỈ DÀNH CHO ADMIN CẤP 1 NGUYỄN TUẤN ANH):\n"
        "- Gọi hàm này khi Admin Cấp 1 bảo: 'Cập nhật vào bộ nhớ: ...', 'Từ giờ ai hỏi ... thì trả lời là ...', 'Ghi nhớ thêm thông tin: ...'."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "topic": {
                "type": "STRING",
                "description": "Chủ đề hoặc câu hỏi cần ghi nhớ/sửa (VD: 'Địa chỉ nhà', 'Mật khẩu wifi khách').",
            },
            "content": {
                "type": "STRING",
                "description": "Câu trả lời ngắn gọn chuẩn xác mà AI sẽ nói khi được hỏi về chủ đề này.",
            },
            "keywords": {
                "type": "STRING",
                "description": "Các từ khóa liên quan cách nhau bằng dấu phẩy.",
            },
            "min_tier": {
                "type": "INTEGER",
                "description": "Cấp tối thiểu được phép hỏi thông tin này (1, 2, hoặc 3; mặc định 3).",
            },
        },
        "required": ["topic", "content"],
    },
)

ALL_TOOLS = [
    types.Tool(
        function_declarations=[
            fn_control_device,
            fn_schedule_action,
            fn_update_timer,
            fn_set_word_mapping,
            fn_create_alias_rule,
            fn_execute_alias_rule,
            fn_set_if_else_rule,
            fn_query_pools,
            fn_query_knowledge_rag,
            fn_start_voice_enrollment,
            fn_finalize_voice_enrollment,
            fn_grant_permission,
            fn_revoke_permission,
            fn_set_query_permission_policy,
            fn_admin_update_system_policy,
            fn_admin_upsert_knowledge_rag,
            fn_request_factory_reset,
            fn_confirm_factory_reset,
            fn_confirm_pending_action,
        ]
    )
]


def build_system_instruction(engine: SmartHomeEngine) -> str:
    pools = engine.get_pools_summary()
    words = engine.get_word_mappings()
    aliases = engine.get_merged_aliases()
    if_else_list = engine.get_if_else_rules()
    cur_user = engine.get_current_user_name()
    cur_tier = engine.current_tier
    q_mode = engine.query_permission_mode
    pol = engine.system_policies

    words_txt = (
        ", ".join(f"'{k}' => {v}" for k, v in words.items())
        if words
        else "Chưa có"
    )
    alias_txt = (
        ", ".join(
            f"'{k}' => [{', '.join(s['device_id'] + ':' + s['action'] for s in steps)}]"
            for k, steps in aliases.items()
        )
        if aliases
        else "Chưa có"
    )
    ifelse_txt = (
        "; ".join(
            f"NẾU {r['when_device_id']}={r['when_state']} THÌ {r['then_device_id']}:{r['then_action']}"
            + (f" (ELSE {r['else_device_id']}:{r['else_action']})" if r.get("else_device_id") else " [1 CHIỀU - ngược lại giữ nguyên]")
            for r in if_else_list
        )
        if if_else_list
        else "Chưa có"
    )
    timers_txt = (
        "; ".join(pools["timer_pool_items"])
        if pools["timer_pool_items"]
        else "Đang trống (0 hẹn giờ)"
    )

    if q_mode == "open_all":
        query_policy_txt = (
            "CHẾ ĐỘ HỎI ĐÁP HIỆN TẠI: MỞ TOÀN BỘ ('open_all' - do Cấp 1 Nguyễn Tuấn Anh cho phép) -> "
            "Ai hỏi cũng được trả lời tất cả những gì bạn biết (nhưng vẫn phải trả lời CỰC NGẮN GỌN, hỏi gì đáp nấy)."
        )
    else:
        query_policy_txt = (
            "CHẾ ĐỘ HỎI ĐÁP HIỆN TẠI: THEO ĐÚNG PHÂN QUYỀN TỪNG CẤP ('tier_restricted') ->\n"
            "  + Nếu người hỏi là Cấp 1 (Nguyễn Tuấn Anh): Bạn BẮT BUỘC trả lời TẤT CẢ mọi câu hỏi và thông tin mà bạn biết.\n"
            "  + Nếu người hỏi là Cấp 2 (Thành viên gia đình): Chỉ trả lời các thông tin thuộc quyền của Cấp 2 (thiết bị, bể lệnh riêng và lịch hẹn riêng của người đó, quyền Cấp 3). Không tiết lộ lịch hẹn riêng hay luật riêng của Cấp 1.\n"
            "  + Nếu người hỏi là Cấp 3 (Khách): Chỉ trả lời về trạng thái đóng/mở thiết bị và lệnh đóng/mở cố định cơ bản. Nếu hỏi về hẹn giờ, luật IF-ELSE hay phân quyền -> từ chối ngắn gọn: 'Bạn ở Cấp 3, chỉ được hỏi về lệnh đóng mở thiết bị cơ bản.'\n"
            "  + Chỉ Cấp 1 (Nguyễn Tuấn Anh) mới có quyền ra lệnh thay đổi quy tắc hỏi đáp này (gọi `set_query_permission_policy` hoặc `admin_update_system_policy`)."
        )

    custom_directives = pol.get("custom_system_directives", [])
    custom_directives_txt = (
        "\n".join(f"  * {d}" for d in custom_directives)
        if custom_directives
        else "  * (Chưa có chỉ thị tùy chỉnh thêm)"
    )
    dev_tiers_txt = ", ".join(
        f"{k}:<=Cấp {v}" for k, v in pol.get("device_min_tiers", {}).items()
    )

    return (
        "Bạn là trợ lý ảo điều khiển nhà thông minh do Nguyễn Tuấn Anh tạo ra.\n"
        f"- NGƯỜI DÙNG ĐANG RA LỆNH HIỆN TẠI: {cur_user} (Cấp {cur_tier} — Vai trò: {engine.current_role}).\n"
        "- NGUYÊN TẮC TỐI THƯỢNG: HỎI GÌ ĐÁP NẤY, CỰC KỲ NGẮN GỌN, KHÔNG DÀI DÒNG (BẮT BUỘC 100%):\n"
        "  + Khi người dùng hỏi cái gì thì CHỈ TRẢ LỜI ĐÚNG CÁI ĐÓ trong 1 câu ngắn gọn (dưới 20 từ). TUYỆT ĐỐI KHÔNG liệt kê sang các thiết bị khác, KHÔNG đọc chân GPIO trừ khi được hỏi đích danh!\n"
        "  + Ví dụ: Hỏi 'Còi báo động nghĩa là gì?' -> Chỉ đáp: 'Còi báo động dùng để phát âm thanh cảnh báo an ninh trong nhà.' (TUYỆT ĐỐI KHÔNG kể lể nhà có 6 thiết bị, cửa chính, đèn, quạt!).\n"
        "  + TUYỆT ĐỐI KHÔNG dùng từ lễ nghi hay nịnh bợ như: 'Dạ', 'Vâng ạ', 'Thưa bạn', 'Rất sẵn lòng'.\n"
        "  + Khi hàm công cụ trả về `exact_spoken_reply`, chỉ đọc ngắn gọn đúng nội dung đó.\n"
        "  + Khi đóng/mở/bật/tắt thiết bị: Chỉ nói 'Cửa chính đã mở.', 'Đèn phòng khách đã bật.', 'Cửa chính đã mở sẵn rồi.', hoặc 'Đèn phòng khách và điều hòa đã mở.'\n\n"
        "=== ĐẶC QUYỀN TỐI CAO CỦA ADMIN CẤP 1 (NGUYỄN TUẤN ANH) SỬA MỌI LUẬT BẰNG GIỌNG NÓI ===\n"
        "  + Nguyễn Tuấn Anh (Cấp 1) có TOÀN QUYỀN ra lệnh bằng giọng nói để sửa bất kỳ quy tắc hệ thống, quyền hạn của Cấp 2/Cấp 3, quyền thiết bị, quy tắc hỏi xác nhận, tín hiệu thu âm, hoặc dạy thêm tri thức RAG ngay lập tức:\n"
        "    -> Khi Cấp 1 nói tự nhiên để sửa quy định hoặc phân quyền (VD: 'Cho cấp 3 hẹn giờ luôn đi', 'Cấm cấp 3 mở cửa chính', 'Từ giờ đặt luật không cần hỏi lại nữa', 'Đổi đèn nháy thu âm sang đèn ngủ', hoặc bất kỳ quy định mới nào) -> BẮT BUỘC tự hiểu ý và gọi ngay `admin_update_system_policy(...)`!\n"
        "    -> Khi Cấp 1 dạy thêm hoặc sửa câu trả lời kiến thức (VD: 'Từ giờ ai hỏi ... thì trả lời là ...') -> BẮT BUỘC gọi ngay `admin_upsert_knowledge_rag(...)`!\n"
        "    -> Nếu Cấp 2 hoặc Cấp 3 cố tình ra lệnh sửa luật hệ thống hay phân quyền -> Gọi hàm để hệ thống chặn và từ chối ngay.\n"
        f"  + Trạng thái Cấu hình Động hiện tại: Cấp 3 hẹn giờ={pol.get('tier3_can_schedule_timer')}, Cấp 3 custom luật={pol.get('tier3_can_custom_rules')}, Cấp 2 hủy cùng cấp={pol.get('tier2_can_revoke_same_tier')}, Hỏi xác nhận luật={pol.get('require_rule_confirmation')}, Hỏi xác nhận reset={pol.get('require_reset_confirmation')}, Thiết bị nháy thu âm={pol.get('enrollment_signal_device_id')} ({pol.get('enrollment_duration_seconds')}s), Quyền thiết bị=[{dev_tiers_txt}].\n"
        f"  + Các quy tắc/chỉ thị tùy chỉnh do Admin Cấp 1 đã thêm bằng giọng nói:\n{custom_directives_txt}\n\n"
        f"=== PHÂN QUYỀN TRẢ LỜI CÂU HỎI (ĐỘNG) ===\n{query_policy_txt}\n\n"
        "=== THU ÂM GIỌNG NÓI ĐỂ CẤP QUYỀN (CẤP 2 / CẤP 3) & QUẢN LÝ 3 TẦNG ===\n"
        "  + Khi người dùng nói muốn thêm người mới, bật ghi âm, hoặc thu âm giọng nói để cấp quyền (VD: 'Tôi cần thêm người mới, bật ghi âm lên', 'Thu âm cấp quyền cấp 3'):\n"
        "    -> BẮT BUỘC gọi ngay hàm `start_voice_enrollment(target_tier=..., target_name=...)`! TUYỆT ĐỐI KHÔNG ĐƯỢC nói 'Tôi không hỗ trợ tính năng bật ghi âm'!\n"
        "    -> Hệ thống sẽ đếm '3, 2, 1', nháy đèn tín hiệu 1 phát báo hiệu bắt đầu, thu âm, báo 'Đã thu âm đủ', phân tích tần số giọng rồi hỏi 'Người ấy tên là gì?'.\n"
        "  + Khi người dùng trả lời tên của người vừa thu âm (VD: 'Tên là Minh', 'Người ấy là Nam') -> gọi `finalize_voice_enrollment(target_name=...)`.\n"
        "  + Khi yêu cầu hủy quyền -> gọi `revoke_user_permission(target_name)`.\n\n"
        "=== QUY TẮC XỬ LÝ LỆNH & XÁC NHẬN LUẬT ===\n"
        "1. BỂ 1 — HẸN GIỜ (MẶC ĐỊNH 1 LẦN RỒI DỪNG, HOẶC LẶP HÀNG NGÀY / HÀNG TUẦN):\n"
        "   - MẶC ĐỊNH HẸN GIỜ 1 LẦN (`repeat='once'`): chạy xong lần đó là dừng hẳn. Khi người dùng nói 'hàng ngày'/'mỗi ngày' -> truyền `repeat='daily'`; 'hàng tuần'/'mỗi tuần' -> `repeat='weekly'`; 'hàng giờ' -> `repeat='hourly'`; 'hàng tháng' -> `repeat='monthly'`.\n"
        "   - Quy tắc 1 (Hẹn đếm ngược giây/phút/giờ, VD '10 giây nữa bật đèn'): gọi `schedule_action(device_id, action, seconds=10)`, ĐỂ TRỐNG `vn_time_ampm=''` và `vn_date=''`. Chỉ trả lời: 'Đã hẹn 10 giây nữa bật đèn phòng khách.'\n"
        "   - Quy tắc 2 (Hẹn giờ có nói rõ AM hoặc PM, VD '8:00 AM' hoặc '8:00 PM'): gọi `schedule_action(device_id, action, vn_time_ampm='8:00 PM')`.\n"
        "   - Quy tắc 3 (Hẹn giờ chỉ nói số giờ 8:00 mà KHÔNG nói AM/PM): gọi `schedule_action(device_id, action, vn_time_ampm='8:00')`. Hệ thống tự đặt CẢ 8:00 AM và 8:00 PM.\n"
        "   - Quy tắc 4 (Có nói thêm ngày/tháng, VD '8:00 PM ngày 25/10'): truyền thêm `vn_date='25/10'`.\n"
        f"   - Trạng thái Bể Hẹn Giờ ({pools['timer_pool_count']} mục): {timers_txt}.\n\n"
        f"2. BỂ 2 (BỂ LỆNH RIÊNG CỦA {cur_user.upper()}) — XÉT LUẬT / ĐỔI TỪ / ĐỔI LỆNH:\n"
        "   - Khi người dùng yêu cầu Đổi từ (`set_word_mapping`), Đổi lệnh (`create_alias_rule`), hoặc Đặt luật IF (`set_if_else_rule`), hãy gọi hàm tương ứng.\n"
        "   - Khi người dùng xác nhận ('Đúng rồi', 'Ok', 'Có', 'Đồng ý'), gọi `confirm_pending_action(confirmed=True)`.\n"
        f"   - Bảng từ đã đổi của {cur_user}: {words_txt} | Bảng khẩu lệnh của {cur_user}: {alias_txt} | Luật IF: {ifelse_txt}.\n\n"
        "3. TRUY VẤN 2 BỂ, HỎI LỆNH THIẾT BỊ & TRI THỨC RAG:\n"
        "   - Hỏi hẹn giờ -> `query_pools(query_type='timers')`; hỏi luật -> `query_pools(query_type='rules')`; hỏi lệnh 1 thiết bị -> `query_pools(query_type='device_command', target_device_id=...)`.\n"
        "   - Hỏi thông tin chung ('Bạn là ai?', 'Ai tạo ra bạn?', 'Còi báo động là gì?', 'Quy định 3 tầng') -> `query_knowledge_rag(question=...)`.\n\n"
        "4. BỐN LOẠI RESET:\n"
        "   - Gọi `request_factory_reset(scope='voice'|'timers'|'rules'|'all')`, khi xác nhận gọi `confirm_pending_action(confirmed=True)`."
    )


def make_live_config(engine: SmartHomeEngine) -> types.LiveConnectConfig:
    return types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                silence_duration_ms=500,
            )
        ),
        system_instruction=types.Content(parts=[types.Part(text=build_system_instruction(engine))]),
        tools=ALL_TOOLS,
    )


app = FastAPI(title="Smart Home Voice AI Simulator - Gemini 3.8 Live")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/test_audio", StaticFiles(directory=str(AUDIO_DIR)), name="test_audio")
MOBILE_APP_DIR = ROOT / "mobile_app"
_REST_ENGINE = SmartHomeEngine()
_ACTIVE_BRIDGES: list[Any] = []


async def _broadcast_rest_state_to_bridges() -> None:
    snap = _REST_ENGINE.get_snapshot()
    for br in list(_ACTIVE_BRIDGES):
        try:
            br.engine.devices = copy.deepcopy(_REST_ENGINE.devices)
            await br.send_ws_json({"type": "state_snapshot", "snapshot": snap})
        except Exception:
            pass


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/app")
async def mobile_app_index() -> FileResponse:
    return FileResponse(MOBILE_APP_DIR / "index.html")


@app.get("/wokwi")
async def wokwi_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "wokwi.html")


@app.get("/translate")
async def translate_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "translate.html")


@app.get("/api/state")
async def api_get_state() -> JSONResponse:
    return JSONResponse(_REST_ENGINE.get_snapshot())


@app.post("/api/device")
async def api_control_device(payload: dict[str, Any]) -> JSONResponse:
    dev_id = str(payload.get("device_id", "main_door"))
    act = str(payload.get("action", "open"))
    res = await _REST_ENGINE.execute_device_action(dev_id, act, source="mobile_app")
    await _broadcast_rest_state_to_bridges()
    return JSONResponse(res)


@app.post("/api/ir_learn")
async def api_ir_learn(payload: dict[str, Any]) -> JSONResponse:
    dev_name = str(payload.get("device_name", "Điều hòa Casper"))
    act = str(payload.get("command_action", "open"))
    res = await _REST_ENGINE.learn_ir_remote_command(device_name=dev_name, command_action=act)
    await _broadcast_rest_state_to_bridges()
    return JSONResponse(res)


@app.post("/api/dht11")
async def api_update_dht11(payload: dict[str, Any]) -> JSONResponse:
    temp_c = float(payload.get("temp_c", 28.5))
    hum_pct = float(payload.get("humidity_pct", 65.0))
    rssi = int(payload.get("wifi_rssi_dbm", -52))
    res = await _REST_ENGINE.update_sensor_telemetry(temp_c, hum_pct, rssi)
    await _broadcast_rest_state_to_bridges()
    return JSONResponse(res)


@app.post("/api/soil_moisture")
async def api_update_soil_moisture(payload: dict[str, Any]) -> JSONResponse:
    pct = float(payload.get("soil_moisture_pct", 62.0))
    res = await _REST_ENGINE.update_soil_moisture_telemetry(pct)
    await _broadcast_rest_state_to_bridges()
    return JSONResponse(res)


@app.post("/api/text_command")
async def api_text_command(payload: dict[str, Any]) -> JSONResponse:
    text = str(payload.get("text", "")).strip()
    t_low = text.lower()
    if "độ ẩm đất" in t_low or "cảm biến đất" in t_low:
        soil = _REST_ENGINE.mqtt_bridge.soil_moisture_telemetry
        spoken = f"Độ ẩm đất hiện tại là {soil['soil_moisture_pct']}% ({soil['status_label']})."
        return JSONResponse({"ok": True, "reply": spoken, "exact_spoken_reply": spoken})
    if "tưới cây" in t_low or "bật máy bơm" in t_low:
        res = await _REST_ENGINE.execute_device_action("garden_pump", "turn_on", source="mobile_app")
        return JSONResponse({"ok": True, "reply": res["exact_spoken_reply"], "exact_spoken_reply": res["exact_spoken_reply"]})
    if "tắt máy bơm" in t_low:
        res = await _REST_ENGINE.execute_device_action("garden_pump", "turn_off", source="mobile_app")
        return JSONResponse({"ok": True, "reply": res["exact_spoken_reply"], "exact_spoken_reply": res["exact_spoken_reply"]})
    if "nhiệt độ" in t_low or "độ ẩm" in t_low:
        dht = _REST_ENGINE.mqtt_bridge.dht11_telemetry
        spoken = f"Nhiệt độ phòng là {dht['temp_c']}°C, độ ẩm {dht['humidity_pct']}%."
        return JSONResponse({"ok": True, "reply": spoken, "exact_spoken_reply": spoken})
    if "học lệnh" in t_low or "remote" in t_low:
        res = await _REST_ENGINE.learn_ir_remote_command("Điều hòa", "open")
        return JSONResponse({"ok": True, "reply": res["exact_spoken_reply"], "exact_spoken_reply": res["exact_spoken_reply"]})
    # Kiểm tra khẩu lệnh alias trước
    for phrase in _REST_ENGINE.get_merged_aliases():
        if phrase in t_low:
            res = await _REST_ENGINE.execute_alias_rule(phrase)
            return JSONResponse({"ok": True, "reply": res["exact_spoken_reply"], "exact_spoken_reply": res["exact_spoken_reply"]})
    return JSONResponse({"ok": True, "reply": f"Đã nhận lệnh: {text}", "exact_spoken_reply": f"Đã nhận lệnh: {text}"})


@app.get("/api/voice_samples")
async def list_voice_samples() -> JSONResponse:
    samples = []
    for key, label in VOICE_SAMPLES_META.items():
        wav_path = AUDIO_DIR / f"{key}.wav"
        if wav_path.exists():
            with wave.open(str(wav_path), "rb") as w:
                dur = round(w.getnframes() / float(w.getframerate()), 2)
            samples.append({"id": key, "label": label, "duration_sec": dur})
    return JSONResponse({"samples": samples})


class LiveBridgeSession:
    """Quản lý kết nối giữa 1 tab trình duyệt và phiên Gemini 3.8 Live."""

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.voice_auth = VoiceAuthManager(AUDIO_DIR)
        self.engine = SmartHomeEngine(
            on_event=self.send_ws_json,
            on_voice_reset=self.voice_auth.reset_to_owner_only,
        )
        self.mic_utterance_pcm = bytearray()
        self.client = genai.Client(api_key=KEY)
        self.gemini_session: Any = None
        self.speech_end_ts: float | None = None
        self.turn_first_tool_ts: float | None = None
        self.turn_first_audio_ts: float | None = None
        self.turn_in_tx: list[str] = []
        self.turn_out_tx: list[str] = []
        self.turn_tools_called: list[str] = []
        self._wav_streaming_task: asyncio.Task | None = None
        self._closed = False
        _ACTIVE_BRIDGES.append(self)

    async def send_ws_json(self, payload: dict[str, Any]) -> None:
        if self._closed:
            if self in _ACTIVE_BRIDGES:
                _ACTIVE_BRIDGES.remove(self)
            return
        if payload.get("type") in ("device_actuated", "state_snapshot"):
            _REST_ENGINE.devices = copy.deepcopy(self.engine.devices)
        try:
            await self.ws.send_text(json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass

    def _reset_turn_metrics(self, anchor_ts: float | None = None) -> None:
        self.speech_end_ts = anchor_ts or time.perf_counter()
        self.turn_first_tool_ts = None
        self.turn_first_audio_ts = None
        self.turn_in_tx.clear()
        self.turn_out_tx.clear()
        self.turn_tools_called.clear()

    async def _sync_rules_context_to_gemini(self, event_note: str, send_to_model: bool = False) -> None:
        """Cập nhật tức thì bảng Từ, Khẩu lệnh, Luật IF-ELSE và 2 Bể lên giao diện (và Gemini nếu cần)."""
        prompt_now = build_system_instruction(self.engine)
        await self.send_ws_json({
            "type": "system_prompt_updated",
            "system_prompt": prompt_now,
        })
        if send_to_model and self.gemini_session is not None:
            try:
                await self.gemini_session.send_client_content(
                    turns=[
                        types.Content(
                            role="user",
                            parts=[
                                types.Part(
                                    text=(
                                        f"[CẬP NHẬT HỆ THỐNG ({format_vn_time_ampm()})]: {event_note}\n"
                                        f"Trạng thái luật hiện hành:\n{prompt_now}"
                                    )
                                )
                            ],
                        )
                    ],
                    turn_complete=False,
                )
            except Exception:
                pass

    async def _run_voice_enrollment_sequence(
        self, duration_seconds: int, target_tier: int, target_name: str
    ) -> None:
        """Thực thi chuỗi tín hiệu phần cứng khi bắt đầu thu âm cấp quyền:
        1. Đợi nhịp đếm 3, 2, 1 (~1.2s).
        2. Nháy đèn phòng khách (Bật -> Tắt 1 phát) làm tín hiệu bắt đầu thu âm.
        3. Yêu cầu trình duyệt mở Mic thu âm trong `duration_seconds` giây.
        4. Nếu trình duyệt không gửi gói âm thanh về (VD chưa bật quyền Mic trên trình duyệt), tự động hoàn tất sau `duration_seconds + 2.0` giây.
        """
        try:
            sig_dev = str(
                (self.engine.pending_voice_enrollment or {}).get("signal_device_id")
                or self.engine.system_policies.get("enrollment_signal_device_id", "living_room_light")
            )
            await asyncio.sleep(1.2)
            await self.engine.blink_signal_light(sig_dev, pulse_sec=0.35)
            await self.send_ws_json({
                "type": "start_voice_capture",
                "duration_seconds": duration_seconds,
                "target_tier": target_tier,
                "target_name": target_name,
                "message": f"💡 Đèn đã nháy! Hãy nói trong {duration_seconds} giây để thu âm cấp quyền Cấp {target_tier}...",
            })
            # Chờ trình duyệt thu âm xong và gửi complete_voice_enrollment; dự phòng timeout nếu chưa cấp quyền Mic
            await asyncio.sleep(float(duration_seconds) + 2.2)
            if (
                self.engine.pending_voice_enrollment
                and self.engine.pending_voice_enrollment.get("step") == "RECORDING"
            ):
                await self._process_completed_voice_enrollment(b"")
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    async def _process_completed_voice_enrollment(self, pcm_bytes: bytes) -> None:
        """Xử lý sau khi thu âm đủ: Nháy đèn báo kết thúc -> Báo thu âm đủ -> Phân tích tần số -> Báo phân tích xong & hỏi tên."""
        if not self.engine.pending_voice_enrollment:
            return
        if self.engine.pending_voice_enrollment.get("step") != "RECORDING":
            return

        # Đánh dấu đang phân tích để không chạy trùng
        self.engine.pending_voice_enrollment["step"] = "ANALYZING"
        sig_dev = str(
            self.engine.pending_voice_enrollment.get("signal_device_id")
            or self.engine.system_policies.get("enrollment_signal_device_id", "living_room_light")
        )

        # Nháy đèn 1 phát báo hiệu kết thúc thu âm
        await self.engine.blink_signal_light(sig_dev, pulse_sec=0.25)
        await self.send_ws_json({
            "type": "voice_enrollment_captured",
            "message": "✅ Đã thu âm đủ! Đang phân tích tần số giọng nói...",
        })

        analysis = self.voice_auth.analyze_voice_pcm16k(pcm_bytes)
        res = await self.engine.stage_voice_enrollment_analysis(
            f0_hz=analysis["f0_hz"],
            centroid_hz=analysis["centroid_hz"],
            embedding=analysis["embedding"],
            duration_sec=analysis.get("duration_sec", 5.0),
        )

        # Nếu đã có tên sẵn và hoàn tất luôn thì đăng ký profile giọng nói ngay
        if res.get("status") == "VOICE_ENROLLMENT_COMPLETED" and res.get("target_user"):
            u = res["target_user"]
            self.voice_auth.register_enrolled_user_profile(
                user_id=u["id"],
                user_name=u["name"],
                tier=u["tier"],
                role=u["role"],
                f0_hz=res.get("f0_hz", 185.0),
                centroid_hz=res.get("centroid_hz", 1520.0),
                embedding=res.get("embedding", [0.15] * 26),
            )

        spoken_msg = res.get("exact_spoken_reply", "Đã thu âm đủ và phân tích xong. Người ấy tên là gì?")
        await self._sync_rules_context_to_gemini(spoken_msg)

        # Yêu cầu Gemini 3.8 Live thông báo kết quả phân tích và hỏi tên người được cấp quyền
        if self.gemini_session is not None:
            try:
                self._reset_turn_metrics(anchor_ts=time.perf_counter())
                await self.gemini_session.send_client_content(
                    turns=[
                        types.Content(
                            role="user",
                            parts=[
                                types.Part(
                                    text=(
                                        f"[HỆ THỐNG ĐÃ THU ÂM ĐỦ VÀ PHÂN TÍCH XONG GIỌNG NÓI]: "
                                        f"KHÔNG gọi thêm tool nào lúc này. "
                                        f"BẮT BUỘC nói to, rõ ràng, ngắn gọn đúng câu này: '{spoken_msg}'"
                                    )
                                )
                            ],
                        )
                    ],
                    turn_complete=True,
                )
            except Exception:
                pass

    async def handle_tool_call(self, fc: Any) -> dict[str, Any]:
        name = fc.name
        args = dict(fc.args or {})

        if name == "control_device":
            return await self.engine.execute_device_action(
                device_id=str(args.get("device_id", "")),
                action=str(args.get("action", "")),
                source="gemini_live",
                trigger_chains=True,
            )

        if name == "schedule_action":
            sec = float(args.get("seconds", args.get("delay_seconds", 0)) or 0)
            hrs = float(args.get("hours", 0) or 0)
            mins = float(args.get("minutes", 0) or 0)
            vn_ampm = str(args.get("vn_time_ampm", "") or "")
            vn_date = str(args.get("vn_date", "") or "")
            repeat = str(args.get("repeat", "once") or "once")
            # Nếu người dùng hẹn đếm ngược (có hours/minutes/seconds > 0) thì ưu tiên đếm ngược, không gán giờ đồng hồ
            if (sec > 0 or mins > 0 or hrs > 0) and not vn_date:
                vn_ampm = ""
            res = await self.engine.schedule_timer_flexible(
                device_id=str(args.get("device_id", "")),
                action=str(args.get("action", "")),
                hours=hrs,
                minutes=mins,
                seconds=sec,
                vn_time_ampm=vn_ampm,
                vn_date=vn_date,
                repeat=repeat,
            )
            await self._sync_rules_context_to_gemini(res.get("message", "Đã đặt hẹn giờ."))
            return res

        if name == "update_timer":
            sec = float(args.get("seconds", 0) or 0)
            hrs = float(args.get("hours", 0) or 0)
            mins = float(args.get("minutes", 0) or 0)
            vn_ampm = str(args.get("vn_time_ampm", "") or "")
            vn_date = str(args.get("vn_date", "") or "")
            repeat = str(args.get("repeat", "once") or "once")
            if (sec > 0 or mins > 0 or hrs > 0) and not vn_date:
                vn_ampm = ""
            res = await self.engine.update_or_cancel_timer(
                device_id=str(args.get("device_id", "all_devices")),
                operation=str(args.get("operation", "modify")),
                new_action=str(args.get("new_action", "") or ""),
                hours=hrs,
                minutes=mins,
                seconds=sec,
                vn_time_ampm=vn_ampm,
                vn_date=vn_date,
                repeat=repeat,
            )
            await self._sync_rules_context_to_gemini(res.get("message", "Đã cập nhật hẹn giờ."))
            return res

        if name == "set_word_mapping":
            res = await self.engine.set_word_mapping(
                custom_word=str(args.get("custom_word", "")),
                target_meaning=str(args.get("target_meaning", "")),
                require_confirmation=True,
            )
            if res.get("ok"):
                await self._sync_rules_context_to_gemini(res.get("message", "Đang chờ xác nhận đổi từ."))
            return res

        if name == "create_alias_rule":
            res = await self.engine.create_alias_rule(
                phrase=str(args.get("phrase", "")),
                target_devices_csv=str(args.get("target_devices_csv", "")),
                target_actions_csv=str(args.get("target_actions_csv", "")),
                require_confirmation=True,
            )
            if res.get("ok"):
                await self._sync_rules_context_to_gemini(res.get("message", "Đang chờ xác nhận đổi khẩu lệnh."))
            return res

        if name == "execute_alias_rule":
            return await self.engine.execute_alias_rule(phrase=str(args.get("phrase", "")))

        if name in ("set_if_else_rule", "create_chain_rule"):
            eval_now = bool(args.get("evaluate_now", False))
            res = await self.engine.set_if_else_rule(
                when_device_id=str(args.get("when_device_id", "")),
                when_state=str(args.get("when_state", "")),
                then_device_id=str(args.get("then_device_id", "")),
                then_action=str(args.get("then_action", "")),
                delay_seconds=float(args.get("delay_seconds", 0) or 0),
                else_device_id=str(args.get("else_device_id", "") or ""),
                else_action=str(args.get("else_action", "") or ""),
                evaluate_now=eval_now,
                require_confirmation=not eval_now,
            )
            if res.get("ok"):
                await self._sync_rules_context_to_gemini(res.get("message", "Đang chờ xác nhận luật IF."))
            return res

        if name == "query_pools":
            q_type = str(args.get("query_type", "all") or "all")
            t_dev = str(args.get("target_device_id", "") or "")
            return self.engine.get_pools_summary(query_type=q_type, target_device_id=t_dev)

        if name == "query_knowledge_rag":
            q = str(args.get("question", "") or "")
            return get_knowledge_rag().retrieve(
                q,
                current_tier=self.engine.current_tier,
                query_permission_mode=self.engine.query_permission_mode,
            )

        if name == "start_voice_enrollment":
            target_tier = int(args.get("target_tier", 3) or 3)
            target_name = str(args.get("target_name", "") or "")
            dur = int(args.get("duration_seconds", 5) or 5)
            res = await self.engine.start_voice_enrollment(
                target_tier=target_tier,
                target_name=target_name,
                duration_seconds=dur,
            )
            if res.get("ok"):
                asyncio.create_task(
                    self._run_voice_enrollment_sequence(
                        duration_seconds=res.get("duration_seconds", 5),
                        target_tier=res.get("target_tier", 3),
                        target_name=res.get("target_name", ""),
                    )
                )
            return res

        if name == "finalize_voice_enrollment":
            target_name = str(args.get("target_name", "") or "")
            target_tier = int(args.get("target_tier", 0) or 0)
            res = await self.engine.finalize_voice_enrollment(
                target_name=target_name,
                target_tier=target_tier,
            )
            if res.get("ok") and res.get("target_user"):
                u = res["target_user"]
                self.voice_auth.register_enrolled_user_profile(
                    user_id=u["id"],
                    user_name=u["name"],
                    tier=u["tier"],
                    role=u["role"],
                    f0_hz=res.get("f0_hz", 185.0),
                    centroid_hz=res.get("centroid_hz", 1520.0),
                    embedding=res.get("embedding", [0.15] * 26),
                )
                await self._sync_rules_context_to_gemini(res.get("message", "Đã lưu giọng nói và cấp quyền."))
            return res

        if name == "grant_user_permission":
            target_name = str(args.get("target_name", "") or "")
            target_tier = int(args.get("target_tier", 3) or 3)
            # Nếu đang ở bước chờ đặt tên sau khi thu âm giọng nói, hoàn tất lưu cả giọng nói lẫn tên
            if (
                self.engine.pending_voice_enrollment
                and self.engine.pending_voice_enrollment.get("step") == "AWAITING_NAME"
            ):
                res = await self.engine.finalize_voice_enrollment(
                    target_name=target_name,
                    target_tier=target_tier,
                )
                if res.get("ok") and res.get("target_user"):
                    u = res["target_user"]
                    self.voice_auth.register_enrolled_user_profile(
                        user_id=u["id"],
                        user_name=u["name"],
                        tier=u["tier"],
                        role=u["role"],
                        f0_hz=res.get("f0_hz", 185.0),
                        centroid_hz=res.get("centroid_hz", 1520.0),
                        embedding=res.get("embedding", [0.15] * 26),
                    )
                    await self._sync_rules_context_to_gemini(res.get("message", "Đã lưu giọng nói và cấp quyền."))
                return res

            res = await self.engine.grant_user_permission(target_name=target_name, target_tier=target_tier)
            if res.get("ok"):
                await self._sync_rules_context_to_gemini(res.get("message", "Đã cấp quyền."))
            return res

        if name == "revoke_user_permission":
            target_name = str(args.get("target_name", "") or "")
            res = await self.engine.revoke_user_permission(target_name=target_name)
            if res.get("ok"):
                await self._sync_rules_context_to_gemini(res.get("message", "Đã hủy quyền."))
            return res

        if name == "set_query_permission_policy":
            mode = str(args.get("mode", "tier_restricted") or "tier_restricted")
            res = await self.engine.set_query_permission_policy(mode=mode)
            if res.get("ok"):
                await self._sync_rules_context_to_gemini(res.get("message", "Đã cập nhật quy tắc phân quyền hỏi."))
            return res

        if name == "admin_update_system_policy":
            policy_key = str(args.get("policy_key", "") or "")
            policy_value = str(args.get("policy_value", "") or "")
            target_device_id = str(args.get("target_device_id", "") or "")
            res = await self.engine.admin_update_system_policy(
                policy_key=policy_key,
                policy_value=policy_value,
                target_device_id=target_device_id,
            )
            if res.get("ok"):
                await self._sync_rules_context_to_gemini(res.get("message", "Đã cập nhật quy tắc hệ thống."))
            return res

        if name == "admin_upsert_knowledge_rag":
            topic = str(args.get("topic", "") or "")
            content = str(args.get("content", "") or "")
            keywords = str(args.get("keywords", "") or "")
            min_tier = int(args.get("min_tier", 3) or 3)
            res = get_knowledge_rag().upsert_knowledge_item(
                topic=topic,
                content=content,
                keywords=keywords,
                min_tier=min_tier,
                current_tier=self.engine.current_tier,
            )
            if res.get("ok"):
                await self.send_ws_json({
                    "type": "system_policy_updated",
                    "policy_key": "knowledge_rag",
                    "message": res.get("message", "Đã cập nhật tri thức RAG."),
                })
                await self._sync_rules_context_to_gemini(res.get("message", "Đã cập nhật tri thức RAG."))
            return res

        if name == "request_factory_reset":
            scope = str(args.get("scope", "all") or "all")
            return await self.engine.request_factory_reset(scope=scope)

        if name in ("confirm_pending_action", "confirm_factory_reset", "factory_reset_rules"):
            confirmed = bool(args.get("confirmed", True))
            res = await self.engine.confirm_pending_action(confirmed=confirmed)
            if res.get("ok"):
                if res.get("reset_scope") in ("voice", "all"):
                    await self.send_ws_json({
                        "type": "voice_auth_result",
                        "sample_id": "reset_voice",
                        "label": "Đã reset giọng nói chỉ về của Chủ nhà",
                        "analysis": self.voice_auth.last_analysis,
                    })
                await self._sync_rules_context_to_gemini(res.get("message", "Đã xử lý xác nhận."))
            return res

        return {"ok": False, "error": f"Hàm '{name}' không được hỗ trợ."}

    async def gemini_receive_loop(self) -> None:
        """Nhận liên tục các sự kiện từ Gemini 3.8 Live và đẩy về giao diện."""
        try:
            while not self._closed and self.gemini_session is not None:
                async for msg in self.gemini_session.receive():
                    now = time.perf_counter()

                    # 1. Xử lý tool_call NGAY LẬP TỨC (Actuate-First!)
                    if msg.tool_call and msg.tool_call.function_calls:
                        fn_responses = []
                        for fc in msg.tool_call.function_calls:
                            if self.turn_first_tool_ts is None:
                                self.turn_first_tool_ts = now
                            t_anchor = self.speech_end_ts or now
                            tool_ms = max(1, round((now - t_anchor) * 1000))
                            desc = f"{fc.name}({json.dumps(dict(fc.args or {}), ensure_ascii=False)})"
                            self.turn_tools_called.append(desc)

                            exec_result = await self.handle_tool_call(fc)

                            await self.send_ws_json({
                                "type": "tool_call_executed",
                                "name": fc.name,
                                "args": dict(fc.args or {}),
                                "result": exec_result,
                                "tool_ms": tool_ms,
                            })

                            fn_responses.append(
                                types.FunctionResponse(
                                    id=fc.id,
                                    name=fc.name,
                                    response={"result": exec_result},
                                )
                            )
                        try:
                            await self.gemini_session.send_tool_response(function_responses=fn_responses)
                        except Exception as e:
                            await self.send_ws_json({"type": "error", "message": f"Lỗi gửi tool_response: {safe_str(e)}"})

                    # 2. Xử lý server_content (phiên âm + gói âm thanh 24kHz)
                    sc = msg.server_content
                    if sc:
                        if sc.input_transcription and sc.input_transcription.text:
                            txt = sc.input_transcription.text
                            self.turn_in_tx.append(txt)
                            await self.send_ws_json({
                                "type": "input_transcription",
                                "text": txt,
                                "full_text": "".join(self.turn_in_tx).strip(),
                            })

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = sc.output_transcription.text
                            self.turn_out_tx.append(txt)
                            await self.send_ws_json({
                                "type": "output_transcription",
                                "text": txt,
                                "full_text": "".join(self.turn_out_tx).strip(),
                            })

                        if sc.model_turn and sc.model_turn.parts:
                            for part in sc.model_turn.parts:
                                if part.inline_data and part.inline_data.data:
                                    if self.turn_first_audio_ts is None:
                                        self.turn_first_audio_ts = now
                                        t_anchor = self.speech_end_ts or now
                                        audio_ms = max(1, round((now - t_anchor) * 1000))
                                        tool_ms = (
                                            max(1, round((self.turn_first_tool_ts - t_anchor) * 1000))
                                            if self.turn_first_tool_ts
                                            else None
                                        )
                                        lead_ms = (
                                            round((self.turn_first_audio_ts - self.turn_first_tool_ts) * 1000)
                                            if self.turn_first_tool_ts
                                            else None
                                        )
                                        await self.send_ws_json({
                                            "type": "first_audio_metrics",
                                            "tool_ms": tool_ms,
                                            "audio_ms": audio_ms,
                                            "lead_ms": lead_ms,
                                        })
                                    b64_pcm = base64.b64encode(part.inline_data.data).decode("ascii")
                                    await self.send_ws_json({
                                        "type": "audio_chunk",
                                        "pcm24k_b64": b64_pcm,
                                    })

                        if sc.interrupted:
                            await self.send_ws_json({"type": "interrupted"})

                        if sc.turn_complete and (
                            self.turn_first_audio_ts is not None or self.turn_first_tool_ts is None
                        ):
                            t_anchor = self.speech_end_ts or now
                            tool_ms = (
                                max(1, round((self.turn_first_tool_ts - t_anchor) * 1000))
                                if self.turn_first_tool_ts
                                else None
                            )
                            audio_ms = (
                                max(1, round((self.turn_first_audio_ts - t_anchor) * 1000))
                                if self.turn_first_audio_ts
                                else None
                            )
                            lead_ms = (
                                round((self.turn_first_audio_ts - self.turn_first_tool_ts) * 1000)
                                if (self.turn_first_tool_ts and self.turn_first_audio_ts)
                                else None
                            )
                            await self.send_ws_json({
                                "type": "turn_complete",
                                "heard": "".join(self.turn_in_tx).strip(),
                                "said": "".join(self.turn_out_tx).strip(),
                                "tools": list(self.turn_tools_called),
                                "tool_ms": tool_ms,
                                "audio_ms": audio_ms,
                                "lead_ms": lead_ms,
                            })
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if not self._closed:
                await self.send_ws_json({
                    "type": "gemini_status",
                    "connected": False,
                    "error": f"Mất kết nối Gemini Live: {safe_str(e)}",
                })

    async def stream_wav_sample(self, sample_id: str) -> None:
        wav_path = AUDIO_DIR / f"{sample_id}.wav"
        if not wav_path.exists():
            await self.send_ws_json({"type": "error", "message": f"Không tìm thấy mẫu âm thanh '{sample_id}.wav'"})
            return

        with wave.open(str(wav_path), "rb") as w:
            data = w.readframes(w.getnframes())

        label = VOICE_SAMPLES_META.get(sample_id, sample_id)

        # 1. Phân tích Tần số Giọng nói (Speaker ID) trên luồng PCM 16kHz
        auth_res = self.voice_auth.verify_pcm16k_and_apply_strikes(data)
        await self.send_ws_json({
            "type": "voice_auth_result",
            "sample_id": sample_id,
            "label": label,
            "analysis": auth_res,
        })

        # Nếu là Giọng KHÔNG ĐƯỢC PHÉP (Giọng 2 - Người lạ):
        if not auth_res["authorized"]:
            strike = auth_res["strike_count"]
            if auth_res["silent_ignore"]:
                # Từ lần thứ 3 trở đi: Vẫn nghe nhưng KHÔNG có bất kỳ phản hồi nào luôn!
                await self.send_ws_json({
                    "type": "voice_auth_silent_ignored",
                    "sample_id": sample_id,
                    "label": label,
                    "strike_count": strike,
                    "f0_hz": auth_res["f0_hz"],
                    "message": f"Đã nghe Giọng 2 (Lần {strike}) nhưng IM LẶNG TUYỆT ĐỐI (quá 2 lần cảnh báo).",
                })
                return

            # Lần 1 ("Không, bạn không có quyền.") và Lần 2 ("Bạn vẫn không đủ quyền."):
            rej_text = auth_res["rejection_speech"]
            self._reset_turn_metrics(anchor_ts=time.perf_counter())
            self.turn_in_tx.append(f"[{auth_res['speaker_label']}]: {label}")
            await self.send_ws_json({
                "type": "voice_auth_rejected",
                "sample_id": sample_id,
                "label": label,
                "strike_count": strike,
                "f0_hz": auth_res["f0_hz"],
                "rejection_speech": rej_text,
            })
            if self.gemini_session is not None:
                await self.gemini_session.send_client_content(
                    turns=[
                        types.Content(
                            role="user",
                            parts=[
                                types.Part(
                                    text=(
                                        f"[HỆ THỐNG CHẶN GIỌNG NÓI LẠ - LẦN {strike}]: "
                                        f"TUYỆT ĐỐI KHÔNG gọi bất kỳ tool nào. "
                                        f"Chỉ đọc nguyên văn câu này: '{rej_text}'"
                                    )
                                )
                            ],
                        )
                    ],
                    turn_complete=True,
                )
            return

        step = CHUNK_SAMPLES * 2
        chunks = [data[i : i + step] for i in range(0, len(data), step)]
        if chunks:
            chunks[-1] = chunks[-1].ljust(step, b"\x00")

        await self.send_ws_json({
            "type": "wav_stream_started",
            "sample_id": sample_id,
            "label": label,
            "duration_sec": round(len(chunks) * CHUNK_MS / 1000.0, 2),
        })

        start = time.perf_counter()
        for i, c in enumerate(chunks):
            delay = start + i * CHUNK_MS / 1000.0 - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            await self.gemini_session.send_realtime_input(
                audio=types.Blob(data=c, mime_type="audio/pcm;rate=16000")
            )

        self._reset_turn_metrics(anchor_ts=time.perf_counter())
        await self.send_ws_json({
            "type": "speech_ended_marker",
            "source": "wav_sample",
            "label": label,
        })

        sil_start = time.perf_counter()
        for i in range(65):
            if self.turn_first_tool_ts is not None or self.turn_first_audio_ts is not None:
                break
            delay = sil_start + i * CHUNK_MS / 1000.0 - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            await self.gemini_session.send_realtime_input(
                audio=types.Blob(data=SILENCE, mime_type="audio/pcm;rate=16000")
            )

    async def run(self) -> None:
        await self.send_ws_json({
            "type": "state_snapshot",
            "snapshot": self.engine.get_snapshot(),
        })
        await self.send_ws_json({
            "type": "system_prompt_updated",
            "system_prompt": build_system_instruction(self.engine),
        })
        await self.send_ws_json({
            "type": "gemini_status",
            "connected": False,
            "message": f"Đang kết nối tới {MODEL}...",
        })

        t0 = time.perf_counter()
        try:
            async with self.client.aio.live.connect(
                model=MODEL, config=make_live_config(self.engine)
            ) as session:
                self.gemini_session = session
                conn_ms = round((time.perf_counter() - t0) * 1000)
                await self.send_ws_json({
                    "type": "gemini_status",
                    "connected": True,
                    "model": MODEL,
                    "connect_ms": conn_ms,
                    "message": f"Đã kết nối {MODEL} ({conn_ms} ms)",
                })

                recv_task = asyncio.create_task(self.gemini_receive_loop())
                timer_tick_task = asyncio.create_task(self._periodic_timer_sync())
                try:
                    while True:
                        raw = await self.ws.receive_text()
                        msg = json.loads(raw)
                        mtype = msg.get("type")

                        if mtype == "mic_chunk":
                            pcm_bytes = base64.b64decode(msg["pcm16k_b64"])
                            if msg.get("is_speech", True):
                                self.speech_end_ts = time.perf_counter()
                                self.turn_first_tool_ts = None
                                self.turn_first_audio_ts = None
                            await session.send_realtime_input(
                                audio=types.Blob(data=pcm_bytes, mime_type="audio/pcm;rate=16000")
                            )

                        elif mtype == "mic_speech_ended":
                            self._reset_turn_metrics(anchor_ts=time.perf_counter())
                            await self.send_ws_json({
                                "type": "speech_ended_marker",
                                "source": "live_mic",
                            })

                        elif mtype == "play_wav_sample":
                            sample_id = str(msg.get("sample_id", ""))
                            if self._wav_streaming_task and not self._wav_streaming_task.done():
                                self._wav_streaming_task.cancel()
                            self._wav_streaming_task = asyncio.create_task(
                                self.stream_wav_sample(sample_id)
                            )

                        elif mtype == "send_text":
                            text = str(msg.get("text", "")).strip()
                            if text:
                                self._reset_turn_metrics(anchor_ts=time.perf_counter())
                                self.turn_in_tx.append(text)
                                await self.send_ws_json({
                                    "type": "input_transcription",
                                    "text": text,
                                    "full_text": text,
                                })
                                await session.send_client_content(
                                    turns=[
                                        types.Content(
                                            role="user",
                                            parts=[
                                                types.Part(
                                                    text=text
                                                )
                                            ],
                                        )
                                    ],
                                    turn_complete=True,
                                )

                        elif mtype == "set_role":
                            new_role = str(msg.get("role", "tuan_anh"))
                            self.engine.set_active_user(new_role)
                            await self.send_ws_json({
                                "type": "state_snapshot",
                                "snapshot": self.engine.get_snapshot(),
                            })
                            await self._sync_rules_context_to_gemini(
                                f"Đã chuyển người dùng sang {self.engine.get_current_user_name()} (Tầng {self.engine.current_tier})."
                            )

                        elif mtype == "manual_toggle":
                            dev_id = str(msg.get("device_id", ""))
                            action = str(msg.get("action", ""))
                            await self.engine.execute_device_action(
                                device_id=dev_id,
                                action=action,
                                source="button_ui",
                                bypass_rbac=True,
                                trigger_chains=True,
                            )

                        elif mtype == "manual_factory_reset":
                            self.voice_auth.reset_strikes()
                            await self.engine.factory_reset()
                            await self._sync_rules_context_to_gemini("Đã reset về mặc định gốc.")

                        elif mtype == "enroll_owner_voice":
                            pcm_bytes = base64.b64decode(msg.get("pcm16k_b64", ""))
                            res = self.voice_auth.enroll_owner_from_pcm16k(pcm_bytes)
                            await self.send_ws_json({
                                "type": "voice_enrolled",
                                "result": res,
                            })

                        elif mtype == "complete_voice_enrollment":
                            pcm_bytes = base64.b64decode(msg.get("pcm16k_b64", ""))
                            await self._process_completed_voice_enrollment(pcm_bytes)

                        elif mtype == "reset_voice_strikes":
                            self.voice_auth.reset_strikes()
                            await self.send_ws_json({
                                "type": "voice_auth_result",
                                "sample_id": "reset",
                                "label": "Đã reset bộ đếm giọng nói",
                                "analysis": self.voice_auth.last_analysis,
                            })

                except WebSocketDisconnect:
                    pass
                finally:
                    self._closed = True
                    recv_task.cancel()
                    timer_tick_task.cancel()
                    if self._wav_streaming_task:
                        self._wav_streaming_task.cancel()
        except Exception as e:
            await self.send_ws_json({
                "type": "gemini_status",
                "connected": False,
                "error": f"Lỗi khởi tạo Gemini Live: {safe_str(e)}",
            })

    async def _periodic_timer_sync(self) -> None:
        try:
            while not self._closed:
                await asyncio.sleep(0.5)
                if self.engine.active_timers:
                    await self.send_ws_json({
                        "type": "state_snapshot",
                        "snapshot": self.engine.get_snapshot(),
                    })
        except asyncio.CancelledError:
            raise


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    bridge = LiveBridgeSession(ws)
    await bridge.run()


TRANSLATOR_SYSTEM_INSTRUCTION = (
    "BẠN LÀ MÁY PHIÊN DỊCH CABIN 2 CHIỀU NGUYÊN VĂN (TIẾNG VIỆT <-> TIẾNG ANH). BẠN KHÔNG PHẢI TRỢ LÝ ẢO.\n"
    "LUẬT TỐI THƯỢNG BẮT BUỘC TUÂN THỦ 100% KHÔNG NGOẠI LỆ:\n"
    "1. TUYỆT ĐỐI KHÔNG BAO GIỜ TRẢ LỜI CÂU HỎI! Dù người nói có hỏi 'Bạn tên là gì?', 'Một cộng một bằng mấy?', "
    "'Mấy giờ rồi?', 'Bạn có khỏe không?', 'What is your name?', 'Can you help me?', bạn CHỈ ĐƯỢC DỊCH NGUYÊN VĂN câu hỏi đó sang ngôn ngữ kia!\n"
    "   - Ví dụ 1: Nghe 'Bạn tên là gì và một cộng một bằng mấy?' -> CHỈ ĐỌC: 'What is your name and what is one plus one?'\n"
    "   - Ví dụ 2: Nghe 'Cho tôi hỏi bây giờ là mấy giờ rồi?' -> CHỈ ĐỌC: 'May I ask what time it is right now?'\n"
    "   - Ví dụ 3: Nghe 'What is your name and how old are you?' -> CHỈ ĐỌC: 'Bạn tên là gì và bạn bao nhiêu tuổi?'\n"
    "   - Ví dụ 4: Nghe 'How much does this circuit board cost?' -> CHỈ ĐỌC: 'Mạch điện này giá bao nhiêu tiền?'\n"
    "2. TỰ ĐỘNG NHẬN DIỆN NGÔN NGỮ ĐẦU VÀO:\n"
    "   - Nếu câu đầu vào là TIẾNG VIỆT -> Dịch nguyên văn 100% sang TIẾNG ANH.\n"
    "   - Nếu câu đầu vào là TIẾNG ANH -> Dịch nguyên văn 100% sang TIẾNG VIỆT.\n"
    "3. KHÔNG BAO GIỜ thêm lời dẫn như 'Bản dịch là:', 'Translation:', 'Dạ', 'Sure'. Chỉ phát ra đúng câu đã dịch!"
)


class LiveTranslatorSession:
    """Phiên WebSocket Máy Phiên Dịch 2 Chiều Nguyên Văn (Việt <-> Anh) trên Gemini 3.8 Live."""

    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.client = genai.Client(api_key=KEY)
        self._closed = False
        self.turn_start_ts: float = time.perf_counter()
        self.first_audio_sent: bool = False
        self.in_chunks: list[str] = []
        self.out_chunks: list[str] = []

    async def send_ws_json(self, payload: dict[str, Any]) -> None:
        if self._closed:
            return
        try:
            await self.ws.send_text(json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass

    async def run(self) -> None:
        cfg = types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    silence_duration_ms=300,
                )
            ),
            system_instruction=types.Content(
                parts=[types.Part(text=TRANSLATOR_SYSTEM_INSTRUCTION)]
            ),
        )
        try:
            async with self.client.aio.live.connect(model=MODEL, config=cfg) as session:
                await self.send_ws_json({"type": "translator_ready", "model": MODEL})

                async def receive_from_gemini() -> None:
                    try:
                        while not self._closed:
                            async for msg in session.receive():
                                sc = msg.server_content
                                if sc is None:
                                    continue
                                if sc.input_transcription and sc.input_transcription.text:
                                    t = sc.input_transcription.text
                                    self.in_chunks.append(t)
                                    await self.send_ws_json({
                                        "type": "input_transcription",
                                        "text": t,
                                        "full_text": "".join(self.in_chunks).strip(),
                                    })
                                if sc.output_transcription and sc.output_transcription.text:
                                    t = sc.output_transcription.text
                                    self.out_chunks.append(t)
                                    await self.send_ws_json({
                                        "type": "output_transcription",
                                        "text": t,
                                        "full_text": "".join(self.out_chunks).strip(),
                                    })
                                if sc.model_turn and sc.model_turn.parts:
                                    for p in sc.model_turn.parts:
                                        if p.inline_data and p.inline_data.data:
                                            first_ms = None
                                            if not self.first_audio_sent:
                                                self.first_audio_sent = True
                                                first_ms = int((time.perf_counter() - self.turn_start_ts) * 1000)
                                            await self.send_ws_json({
                                                "type": "audio_out",
                                                "pcm24k_b64": base64.b64encode(p.inline_data.data).decode("ascii"),
                                                "first_audio_ms": first_ms,
                                            })
                                if sc.turn_complete:
                                    await self.send_ws_json({
                                        "type": "turn_complete",
                                        "input_text": "".join(self.in_chunks).strip(),
                                        "output_text": "".join(self.out_chunks).strip(),
                                    })
                                    self.in_chunks.clear()
                                    self.out_chunks.clear()
                                    self.first_audio_sent = False
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        await self.send_ws_json({"type": "error", "error": safe_str(e)})

                recv_task = asyncio.create_task(receive_from_gemini())
                try:
                    while not self._closed:
                        raw = await self.ws.receive_text()
                        data = json.loads(raw)
                        mtype = data.get("type")
                        if mtype == "mic_pcm16k":
                            pcm = base64.b64decode(data.get("pcm16k_b64", ""))
                            if not self.in_chunks and not self.first_audio_sent:
                                self.turn_start_ts = time.perf_counter()
                            await session.send_realtime_input(
                                audio=types.Blob(data=pcm, mime_type="audio/pcm;rate=16000")
                            )
                        elif mtype == "mic_stop":
                            self.turn_start_ts = time.perf_counter()
                            await session.send_realtime_input(audio_stream_end=True)
                        elif mtype == "translate_text":
                            txt = str(data.get("text", "")).strip()
                            if txt:
                                self.in_chunks = [txt]
                                self.out_chunks.clear()
                                self.first_audio_sent = False
                                self.turn_start_ts = time.perf_counter()
                                await session.send_client_content(
                                    turns=[
                                        types.Content(
                                            role="user",
                                            parts=[
                                                types.Part(
                                                    text=(
                                                        f"[CHỈ DỊCH NGUYÊN VĂN SANG NGÔN NGỮ ĐỐI DIỆN (VIỆT <-> ANH), "
                                                        f"TUYỆT ĐỐI KHÔNG TRẢ LỜI CÂU HỎI NÀY]: \"{txt}\""
                                                    )
                                                )
                                            ],
                                        )
                                    ],
                                    turn_complete=True,
                                )
                except WebSocketDisconnect:
                    pass
                finally:
                    self._closed = True
                    recv_task.cancel()
        except Exception as e:
            await self.send_ws_json({"type": "error", "error": safe_str(e)})


@app.websocket("/ws/translate")
async def websocket_translate_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    session = LiveTranslatorSession(ws)
    await session.run()


