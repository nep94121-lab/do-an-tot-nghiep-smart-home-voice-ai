"""Bộ Xây Dựng Prompt Hệ Thống & Cấu Hình Live Gemini 3.8 (Prompt Builder).

Chức năng:
1. Định nghĩa 20 Function Declarations cho Gemini 3.8 Live API.
2. Xây dựng Dynamic System Instruction thích ứng theo RBAC 3 Tầng và tình trạng thực tế của ngôi nhà.
3. 4 Bức tường lửa bảo vệ AI: Vietnamese Prompt Guard, Filler Sound Guard, Domain Guard, Concise Actuation.
4. Cấu hình Live Connect Config (Audio 24kHz, Voice 'Aoede', VAD sensitivity).
"""

from __future__ import annotations

import os
from typing import Any
from google.genai import types

from simulator.rule_engine import SmartHomeEngine

DEVICE_ENUM = [
    "main_door",
    "living_room_light",
    "bedroom_light",
    "garden_pump",
    "alarm_siren",
    "speaker_amp",
    "all_lights",
    "all_devices",
]
ACTION_ENUM = ["open", "close", "turn_on", "turn_off"]

fn_control_device = types.FunctionDeclaration(
    name="control_device",
    description=(
        "Bật/tắt hoặc mở/đóng thiết bị trong nhà NGAY LẬP TỨC sau khi kiểm tra phân quyền phía server. "
        "KHÔNG hỏi xác nhận trước với lệnh bật/tắt/mở/đóng trực tiếp; sau khi thực thi chỉ báo ngắn gọn bằng tiếng Việt (VD: 'Đã mở cửa chính.', 'Đã bật đèn phòng khách.')."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "device_id": {
                "type": "STRING",
                "enum": DEVICE_ENUM,
                "description": (
                    "Mã thiết bị: main_door (cửa chính), living_room_light (đèn phòng khách), "
                    "bedroom_light (đèn phòng ngủ), garden_pump (máy bơm tưới cây), "
                    "alarm_siren (còi báo động), speaker_amp (nguồn mạch loa PAM8403), "
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
        "(VD: 'Sửa lại hẹn giờ tắt đèn thành 15 giây nữa', 'Đổi hẹn giờ máy bơm sang 8:00 PM', 'Hủy hẹn giờ nguồn mạch loa')."
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
        "(VD: 'Từ giờ gọi nguồn mạch loa là loa chính', 'Gọi cửa chính là cổng rồng', 'Từ khởi động nghĩa là bật')."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "custom_word": {
                "type": "STRING",
                "description": "Từ hoặc tên gọi mới do người dùng đặt (VD: 'loa chính', 'cổng rồng', 'khởi động').",
            },
            "target_meaning": {
                "type": "STRING",
                "description": "Thiết bị hoặc hành động gốc tương ứng (VD: 'speaker_amp (Nguồn mạch loa PAM8403)', 'main_door (Cửa chính)', 'turn_on (Bật)').",
            },
        },
        "required": ["custom_word", "target_meaning"],
    },
)

fn_create_alias_rule = types.FunctionDeclaration(
    name="create_alias_rule",
    description=(
        "ĐỔI LỆNH / GÁN KHẨU LỆNH (Command Phrase Remapping): Khi người dùng muốn đổi câu lệnh mở/đóng/bật/tắt "
        "hoặc tạo khẩu lệnh riêng cho 1 hay nhiều thiết bị. Server sẽ lưu nháp chờ xác nhận (TTL 20s) và trả câu '... đúng không ạ?' — BẮT BUỘC đọc nguyên văn để người dùng xác nhận rồi mới ghi SQLite."
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
        "Thiết lập LIÊN KẾT / LUẬT TỰ ĐỘNG IF-THEN giữa các thiết bị hoặc cảm biến (VD: 'khi mở cửa chính thì bật đèn phòng khách', 'khi đất khô thì bật bơm', 'khi có tiếng động lớn thì bật còi'). "
        "Chỉ điền `else_device_id` khi người dùng nói rõ vế ngược lại. "
        "Khi gọi tool, server kiểm tra phân quyền (Cấp 2 cần được Cấp 1 cấp quyền liên kết) rồi lưu nháp chờ xác nhận và trả `exact_spoken_reply` — BẮT BUỘC đọc nguyên văn để hỏi xác nhận."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "when_device_id": {
                "type": "STRING",
                "enum": DEVICE_ENUM[:6] + ["soil_sensor", "sound_sensor"],
            },
            "when_state": {
                "type": "STRING",
                "enum": ["ON", "OFF", "OPEN", "CLOSED", "DRY", "WET", "LOUD", "QUIET"],
                "description": "Trạng thái điều kiện IF của thiết bị hoặc cảm biến nguồn (ON, OFF, OPEN, CLOSED, DRY, WET, LOUD, QUIET).",
            },
            "then_device_id": {"type": "STRING", "enum": DEVICE_ENUM[:6]},
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
        "Bật thu âm giọng nói để cấp quyền cho người mới (Cấp 2 hoặc Cấp 3 — chỉ dành cho Chủ nhà Cấp 1 Nguyễn Tuấn Anh):\n"
        "- Gọi hàm này khi Cấp 1 nói muốn thêm người mới hoặc thu âm cấp quyền giọng nói.\n"
        "- Hệ thống sẽ đếm 3, 2, 1, nháy đèn báo hiệu, thu âm giọng nói, phân tích đặc trưng giọng và hỏi tên người được cấp quyền (nếu chưa có tên).\n"
        "- Chỉ Cấp 1 (Nguyễn Tuấn Anh) mới có quyền thu âm và cấp quyền giọng nói cho Cấp 2 hoặc Cấp 3; Cấp 2 và Cấp 3 không có quyền."
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
        "Cấp quyền cho người dùng theo hệ thống phân quyền 3 tầng (chỉ dành cho Chủ nhà Cấp 1 Nguyễn Tuấn Anh):\n"
        "- Chỉ Cấp 1 (Nguyễn Tuấn Anh) được cấp quyền cho Cấp 2 (Thành viên gia đình) hoặc Cấp 3 (Khách).\n"
        "- Cấp 2 và Cấp 3 không có quyền cấp quyền cho bất kỳ ai."
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
        "Thu hồi quyền của người dùng theo hệ thống phân quyền 3 tầng (chỉ dành cho Chủ nhà Cấp 1 Nguyễn Tuấn Anh):\n"
        "- Chỉ Cấp 1 (Nguyễn Tuấn Anh) mới có quyền hủy/thu hồi quyền của bất kỳ ai ở Cấp 2 và Cấp 3.\n"
        "- Cấp 2 và Cấp 3 không có quyền hủy quyền của bất kỳ ai."
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
        "Sửa đổi quy tắc hệ thống, phân quyền thiết bị hoặc luật ứng xử bằng giọng nói (chỉ dành cho Admin Cấp 1 Nguyễn Tuấn Anh):\n"
        "- Gọi hàm này khi Admin Cấp 1 ra lệnh sửa luật hệ thống bằng giọng nói:\n"
        "  + 'Cho phép cấp 3 được hẹn giờ' -> policy_key='tier3_can_schedule_timer', policy_value='true'\n"
        "  + 'Cấm cấp 3 hẹn giờ' -> policy_key='tier3_can_schedule_timer', policy_value='false'\n"
        "  + 'Cho phép cấp 3 được đổi lệnh và đặt luật IF-ELSE' -> policy_key='tier3_can_custom_rules', policy_value='true'\n"
        "  + 'Cho phép cấp 2 sửa hẹn giờ hoặc luật của cấp 1' -> policy_key='tier2_can_override_tier1', policy_value='true'\n"
        "  + 'Khi xét luật mới không cần hỏi xác nhận lại nữa, lưu thẳng luôn' -> policy_key='require_rule_confirmation', policy_value='false'\n"
        "  + 'Khi gọi reset thì reset luôn không cần hỏi lại' -> policy_key='require_reset_confirmation', policy_value='false'\n"
        "  + 'Khi thu âm cấp quyền thì nháy đèn phòng ngủ thay vì đèn phòng khách' -> policy_key='enrollment_signal_device_id', target_device_id='bedroom_light'\n"
        "  + 'Chỉnh thời gian thu âm cấp quyền thành 8 giây' -> policy_key='enrollment_duration_seconds', policy_value='8'\n"
        "  + 'Cấm cấp 3 mở cửa chính, chỉ cấp 1 và cấp 2 mới được mở cửa chính' -> policy_key='device_min_tier', target_device_id='main_door', policy_value='2'\n"
        "  + 'Chỉ mình tôi cấp 1 mới được bật còi báo động' -> policy_key='device_min_tier', target_device_id='alarm_siren', policy_value='1'\n"
        "  + Quy định/luật mới Admin nói tự nhiên -> policy_key='custom_directive_add', policy_value='<nội dung quy định>'."
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

fn_set_or_query_sensors = types.FunctionDeclaration(
    name="set_or_query_sensors",
    description=(
        "ĐỌC HOẶC TỰ SET (GIẢ LẬP) NHIỆT ĐỘ PHÒNG, ĐỘ ẨM KHÔNG KHÍ (DHT11 - CHÂN D2), ĐỘ ẨM ĐẤT (CHÂN A0) VÀ CẢM BIẾN ÂM THANH KY-037/038 (DO - CHÂN D5) BẰNG GIỌNG NÓI:\n"
        "- Khi người dùng hỏi nhiệt độ, độ ẩm phòng, độ ẩm đất hoặc cảm biến âm thanh KY-037 hiện tại -> gọi với `operation='query'` (Gemini Voice AI thu âm qua micro/loa web hoặc thiết bị, còn KY-037 DO trên D5 phát hiện vỗ tay/tiếng động lớn).\n"
        "- Khi người dùng ra lệnh chỉnh/set nhiệt độ hoặc độ ẩm không khí DHT11 (VD: 'Chỉnh nhiệt độ lên 32 độ', 'Set nhiệt độ 26 độ, độ ẩm 60%') -> gọi với `operation='set'`, truyền `temp_c` và/hoặc `humidity_pct`.\n"
        "- Khi người dùng ra lệnh chỉnh/set độ ẩm đất (VD: 'Set độ ẩm đất xuống 25%', 'Chỉnh độ ẩm đất 80%') -> gọi với `operation='set'`, truyền `soil_moisture_pct`. Nếu đất khô < 40% máy bơm (D6) sẽ tự bật, đủ ẩm >= 70% máy bơm tự tắt!"
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "operation": {
                "type": "STRING",
                "enum": ["query", "set"],
                "description": "'query' để hỏi thông số hiện tại; 'set' để chỉnh/giả lập nhiệt độ, độ ẩm không khí hoặc độ ẩm đất.",
            },
            "temp_c": {
                "type": "NUMBER",
                "description": "Nhiệt độ phòng (°C) muốn set cho cảm biến DHT11 (chân D2), ví dụ 32.0.",
            },
            "humidity_pct": {
                "type": "NUMBER",
                "description": "Độ ẩm không khí (%) muốn set cho cảm biến DHT11 (chân D2), ví dụ 65.0.",
            },
            "soil_moisture_pct": {
                "type": "NUMBER",
                "description": "Độ ẩm đất (%) muốn set cho cảm biến độ ẩm đất (chân A0), ví dụ 25.0 (khô < 40% tự bật bơm, >= 70% tự tắt bơm).",
            },
        },
        "required": ["operation"],
    },
)

fn_create_schedule_clock = types.FunctionDeclaration(
    name="create_schedule_clock",
    description=(
        "Đặt LỊCH ĐỒNG HỒ THEO GIỜ THỰC TẾ múi giờ Việt Nam Asia/Saigon (1 lần hoặc hằng ngày). "
        "Server kiểm tra xung đột lịch Cấp 2 với Cấp 1 (+/-60s) và tạo nháp chờ xác nhận 20s; BẮT BUỘC đọc nguyên văn `exact_spoken_reply` trả về."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "device_id": {"type": "STRING", "enum": DEVICE_ENUM[:6]},
            "action": {"type": "STRING", "enum": ACTION_ENUM},
            "time_hhmm": {"type": "STRING", "description": "Giờ định dạng HH:MM 24h theo Asia/Saigon (VD: '14:35', '22:30')."},
            "schedule_type": {"type": "STRING", "enum": ["once", "daily"], "description": "'once' (1 lần) hoặc 'daily' (hằng ngày)."},
        },
        "required": ["device_id", "action", "time_hhmm"],
    },
)

fn_create_custom_scene = types.FunctionDeclaration(
    name="create_custom_scene",
    description=(
        "Tạo LỆNH TÙY CHỈNH / NGỮ CẢNH nhiều bước (VD: 'tạo lệnh mới giờ đi ngủ là tắt hết đèn'). "
        "Server lưu nháp chờ xác nhận 20s và trả `exact_spoken_reply` ('... đúng không ạ?'); BẮT BUỘC đọc nguyên văn rồi chờ người dùng nói 'xác nhận'/'không'."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "phrase": {"type": "STRING", "description": "Tên ngữ cảnh/khẩu lệnh (VD: 'chế độ ngủ')."},
            "steps_text": {"type": "STRING", "description": "Mô tả các hành động thiết bị (VD: 'tắt hết đèn và đóng cửa chính')."},
        },
        "required": ["phrase", "steps_text"],
    },
)

fn_run_custom_scene = types.FunctionDeclaration(
    name="run_custom_scene",
    description="Chạy một ngữ cảnh / lệnh tùy chỉnh đã lưu trong bể của người đang nói (VD: 'chế độ ngủ', 'giờ đi ngủ').",
    parameters={
        "type": "OBJECT",
        "properties": {
            "phrase_or_id": {"type": "STRING", "description": "Tên khẩu lệnh hoặc ID ngữ cảnh cần chạy."},
        },
        "required": ["phrase_or_id"],
    },
)

fn_delete_automation_item = types.FunctionDeclaration(
    name="delete_automation_item",
    description="Yêu cầu xóa 1 lịch theo giờ (schedule), liên kết (rule) hoặc lệnh custom (scene) cụ thể. Server lưu nháp chờ xác nhận 20s.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "kind": {"type": "STRING", "enum": ["schedule", "rule", "scene"]},
            "keyword_or_id": {"type": "STRING", "description": "Từ khóa, giờ HH:MM, tên lệnh hoặc ID cần xóa."},
        },
        "required": ["kind"],
    },
)

fn_confirm_or_cancel_pending_action = types.FunctionDeclaration(
    name="confirm_or_cancel_pending_action",
    description=(
        "Bước 2 luồng xác nhận 4 bước: BẮT BUỘC gọi khi người dùng trả lời 'xác nhận', 'đúng', 'ừ', 'ok', 'đồng ý' (-> confirmed=True) "
        "hoặc 'không', 'hủy', 'thôi', 'đừng' (-> confirmed=False) để chốt hoặc hủy thay đổi đang chờ xác nhận trong bể."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "confirmed": {
                "type": "BOOLEAN",
                "description": "True để xác nhận ghi SQLite ('Đã xác nhận. Xong rồi ạ.'); False để hủy ('Đã hủy.').",
            },
        },
        "required": ["confirmed"],
    },
)

fn_query_pools_or_members = types.FunctionDeclaration(
    name="query_pools_or_members",
    description=(
        "Đọc ĐÚNG bể dữ liệu SQLite theo chủ sở hữu đang đăng nhập (Cấp 1 xem toàn bộ kèm 'của <tên>', Cấp 2 chỉ xem của chính mình, Cấp 3 bị từ chối):\n"
        "- 'timers': 'tôi có những hẹn giờ nào', 'hẹn giờ của Mẹ'\n"
        "- 'custom_commands': 'tôi có những lệnh custom nào'\n"
        "- 'links': 'có những liên kết nào'\n"
        "- 'members': 'nhà có mấy thành viên, tên gì, cấp mấy'."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "pool_kind": {
                "type": "STRING",
                "enum": ["timers", "custom_commands", "links", "members"],
                "description": "Loại dữ liệu cần đọc từ SQLite.",
            },
            "target_member_name": {
                "type": "STRING",
                "description": "(Chỉ Cấp 1) Tên thành viên khi hỏi riêng của người đó (VD: 'Mẹ'). Để trống nếu hỏi mặc định.",
            },
        },
        "required": ["pool_kind"],
    },
)

fn_reset_user_pool = types.FunctionDeclaration(
    name="reset_user_pool",
    description=(
        "Yêu cầu reset bể dữ liệu ('reset lệnh custom', 'reset liên kết', 'xóa hẹn giờ'). "
        "Mặc định chỉ reset bể của chính người đang nói; chỉ Cấp 1 mới được truyền `target_member_name` hoặc `clear_all=True`. "
        "Server tạo nháp chờ xác nhận 20s và trả '... đúng không ạ?'."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "pool_kind": {
                "type": "STRING",
                "enum": ["custom_commands", "links", "timers", "all"],
                "description": "Bể cần reset.",
            },
            "target_member_name": {
                "type": "STRING",
                "description": "(Chỉ Cấp 1) Tên thành viên cần reset bể (VD: 'Mẹ'). Để trống nếu reset bể của chính mình.",
            },
            "clear_all": {
                "type": "BOOLEAN",
                "description": "(Chỉ Cấp 1) True nếu nói 'của mọi người'.",
            },
        },
        "required": ["pool_kind"],
    },
)

fn_manage_member_link_permission = types.FunctionDeclaration(
    name="manage_member_link_permission",
    description=(
        "(Chỉ Cấp 1) Cấp hoặc thu hồi quyền tạo liên kết thiết bị cho thành viên Cấp 2 (VD: 'cấp quyền tạo liên kết cho Mẹ'). "
        "Server lưu nháp chờ xác nhận 20s."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "target_member_name": {
                "type": "STRING",
                "description": "Tên thành viên cần cấp hoặc thu hồi quyền tạo liên kết.",
            },
            "allowed": {
                "type": "BOOLEAN",
                "description": "True để cấp quyền, False để thu hồi quyền.",
            },
        },
        "required": ["target_member_name", "allowed"],
    },
)

fn_list_devices = types.FunctionDeclaration(
    name="list_devices",
    description=(
        "Liệt kê danh sách các thiết bị trong nhà thuộc quyền sử dụng của người đang nói "
        "kèm trạng thái bật/tắt/đóng/mở và các thông số hiện tại (độ sáng đèn)."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {},
    },
)

fn_get_device_state = types.FunctionDeclaration(
    name="get_device_state",
    description=(
        "Đọc trạng thái hiện tại và thông số chi tiết của một thiết bị cụ thể "
        "(cửa chính, đèn phòng khách, đèn phòng ngủ, máy bơm tưới cây, còi báo động, nguồn mạch loa PAM8403)."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "device_id": {
                "type": "STRING",
                "enum": DEVICE_ENUM[:6],
                "description": "Thiết bị cần kiểm tra trạng thái.",
            },
        },
        "required": ["device_id"],
    },
)

fn_read_sensors = types.FunctionDeclaration(
    name="read_sensors",
    description=(
        "Đọc toàn bộ thông số 3 cảm biến hiện tại trong nhà và sân vườn gồm nhiệt độ phòng (°C), "
        "độ ẩm không khí (%), độ ẩm đất (%) và trạng thái cảm biến âm thanh KY-037 (chân D5)."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {},
    },
)

fn_set_device = types.FunctionDeclaration(
    name="set_device",
    description=(
        "Bật/tắt/mở/đóng hoặc đặt thông số (độ sáng đèn 0-100%) cho thiết bị NGAY LẬP TỨC sau khi kiểm tra quyền phía server. "
        "KHÔNG hỏi xác nhận trước với lệnh điều khiển trực tiếp; sau khi thực thi chỉ báo ngắn gọn (VD: 'Đã bật đèn phòng khách.')."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "device_id": {
                "type": "STRING",
                "enum": DEVICE_ENUM[:6],
                "description": "Thiết bị cần điều khiển hoặc đặt thông số.",
            },
            "action": {
                "type": "STRING",
                "enum": ["turn_on", "turn_off", "open", "close", "set_value"],
                "description": "Thao tác bật, tắt, mở, đóng hoặc đặt giá trị.",
            },
            "brightness_pct": {
                "type": "INTEGER",
                "description": "Độ sáng đèn theo phần trăm từ 0 đến 100 (chỉ dùng cho đèn phòng khách hoặc đèn phòng ngủ).",
            },
        },
        "required": ["device_id"],
    },
)

fn_create_timer = types.FunctionDeclaration(
    name="create_timer",
    description=(
        "Tạo hẹn giờ đếm ngược để bật, tắt, mở hoặc đóng bất kỳ thiết bị nào trong quyền của người dùng "
        "(ví dụ tắt đèn phòng khách sau 10 phút). Lưu bản nháp và hỏi xác nhận bằng tiếng Việt tự nhiên trước khi tạo."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "device_id": {
                "type": "STRING",
                "enum": DEVICE_ENUM,
                "description": "Thiết bị cần hẹn giờ.",
            },
            "action": {
                "type": "STRING",
                "enum": ACTION_ENUM,
                "description": "Hành động sẽ thực hiện khi hết giờ.",
            },
            "hours": {"type": "NUMBER", "description": "Số giờ đếm ngược."},
            "minutes": {"type": "NUMBER", "description": "Số phút đếm ngược."},
            "seconds": {"type": "NUMBER", "description": "Số giây đếm ngược."},
            "repeat": {
                "type": "STRING",
                "enum": ["once", "daily", "weekly", "hourly", "monthly"],
                "description": "Chế độ lặp lại (mặc định một lần).",
            },
        },
        "required": ["device_id", "action"],
    },
)

fn_list_timers = types.FunctionDeclaration(
    name="list_timers",
    description="Đọc danh sách các hẹn giờ đếm ngược đang hoạt động thuộc phạm vi quyền của người dùng hiện tại.",
    parameters={
        "type": "OBJECT",
        "properties": {},
    },
)

fn_delete_timer = types.FunctionDeclaration(
    name="delete_timer",
    description=(
        "Yêu cầu hủy hoặc xóa một hẹn giờ đếm ngược đang chạy theo mã hẹn giờ hoặc theo thiết bị. "
        "Lưu bản nháp chờ xác nhận trước khi xóa."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "timer_id": {"type": "STRING", "description": "Mã hẹn giờ cần xóa (nếu biết)."},
            "device_id": {"type": "STRING", "enum": DEVICE_ENUM, "description": "Thiết bị cần hủy hẹn giờ."},
        },
    },
)

fn_create_schedule = types.FunctionDeclaration(
    name="create_schedule",
    description=(
        "Tạo lịch hẹn theo giờ đồng hồ Việt Nam (một lần hoặc hằng ngày) cho bất kỳ thiết bị nào thuộc quyền người dùng. "
        "Lưu bản nháp và hỏi xác nhận trước khi ghi."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "device_id": {"type": "STRING", "enum": DEVICE_ENUM[:6], "description": "Thiết bị cần đặt lịch."},
            "action": {"type": "STRING", "enum": ACTION_ENUM, "description": "Hành động sẽ thực hiện."},
            "time_hhmm": {"type": "STRING", "description": "Giờ thực hiện dạng 24 giờ HH:MM (ví dụ 22:30)."},
            "schedule_type": {
                "type": "STRING",
                "enum": ["once", "daily"],
                "description": "Một lần hoặc hằng ngày.",
            },
        },
        "required": ["device_id", "action", "time_hhmm"],
    },
)

fn_list_schedules = types.FunctionDeclaration(
    name="list_schedules",
    description="Đọc danh sách lịch đồng hồ đang có thuộc phạm vi quyền của người dùng hiện tại.",
    parameters={
        "type": "OBJECT",
        "properties": {},
    },
)

fn_delete_schedule = types.FunctionDeclaration(
    name="delete_schedule",
    description=(
        "Yêu cầu xóa một lịch đồng hồ theo mã lịch hoặc theo giờ HH:MM. "
        "Lưu bản nháp chờ xác nhận trước khi xóa."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "schedule_id": {"type": "STRING", "description": "Mã lịch cần xóa (nếu biết)."},
            "time_hhmm": {"type": "STRING", "description": "Mốc giờ HH:MM của lịch cần xóa."},
        },
    },
)

ALL_TOOLS = [
    types.Tool(
        function_declarations=[
            fn_list_devices,
            fn_get_device_state,
            fn_read_sensors,
            fn_set_device,
            fn_create_timer,
            fn_list_timers,
            fn_delete_timer,
            fn_create_schedule,
            fn_list_schedules,
            fn_delete_schedule,
            fn_control_device,
            fn_schedule_action,
            fn_update_timer,
            fn_create_schedule_clock,
            fn_create_custom_scene,
            fn_run_custom_scene,
            fn_delete_automation_item,
            fn_confirm_or_cancel_pending_action,
            fn_query_pools_or_members,
            fn_reset_user_pool,
            fn_manage_member_link_permission,
            fn_set_word_mapping,
            fn_create_alias_rule,
            fn_execute_alias_rule,
            fn_set_if_else_rule,
            fn_query_pools,
            fn_query_knowledge_rag,
            fn_grant_permission,
            fn_revoke_permission,
            fn_set_query_permission_policy,
            fn_admin_update_system_policy,
            fn_admin_upsert_knowledge_rag,
            fn_set_or_query_sensors,
            fn_request_factory_reset,
            fn_confirm_factory_reset,
            fn_confirm_pending_action,
        ]
    )
]

if hasattr(types, "Behavior"):
    for _tool_group in ALL_TOOLS:
        for _fn_decl in (_tool_group.function_declarations or []):
            _fn_decl.behavior = types.Behavior.BLOCKING


FIXED_REJECTION_PHRASE_VI = "Xin lỗi, bạn không có quyền thực hiện lệnh này."
FIXED_SAFE_DENY_REPEAT_PHRASE_VI = "Âm thanh chưa rõ, vui lòng nói lại."


def build_system_instruction(engine: SmartHomeEngine) -> str:
    pools = engine.get_pools_summary()
    words = engine.get_word_mappings()
    aliases = engine.get_merged_aliases()
    if_else_list = engine.get_if_else_rules()
    cur_user = engine.get_current_user_name()
    cur_tier = engine.current_tier
    cur_role = engine.current_role
    dht = getattr(getattr(engine, "mqtt_bridge", None), "dht11_telemetry", {}) or {}
    soil = getattr(getattr(engine, "mqtt_bridge", None), "soil_moisture_telemetry", {}) or {}
    sound = getattr(getattr(engine, "mqtt_bridge", None), "sound_telemetry", {}) or {}

    state_vi_map = {"ON": "đang bật", "OFF": "đang tắt", "OPEN": "đang mở", "CLOSED": "đang đóng"}
    act_vi_map = {"open": "mở", "close": "đóng", "turn_on": "bật", "turn_off": "tắt"}

    def _dev_name(did: str) -> str:
        return str(engine.devices.get(did, {}).get("name") or did)

    devs_txt = ", ".join(
        f"{v.get('name', k)} {state_vi_map.get(str(v.get('state', '')).upper(), str(v.get('state', '')).lower())}"
        for k, v in engine.devices.items()
    )
    words_txt = ", ".join(f"'{k}' hiểu là '{v}'" for k, v in words.items()) if words else "Chưa có"
    alias_txt = (
        ", ".join(
            f"'{k}' gồm {', '.join(act_vi_map.get(s['action'], s['action']) + ' ' + _dev_name(s['device_id']).lower() for s in steps)}"
            for k, steps in aliases.items()
        )
        if aliases else "Chưa có"
    )
    ifelse_txt = (
        "; ".join(
            f"Khi {_dev_name(r['when_device_id'])} {state_vi_map.get(str(r['when_state']).upper(), str(r['when_state']).lower())} "
            f"thì {act_vi_map.get(r['then_action'], r['then_action'])} {_dev_name(r['then_device_id']).lower()}"
            + (
                f", ngược lại {act_vi_map.get(r['else_action'], r['else_action'])} {_dev_name(r['else_device_id']).lower()}"
                if r.get("else_device_id")
                else ""
            )
            for r in if_else_list
        ) if if_else_list else "Chưa có"
    )
    timers_txt = "; ".join(pools["timer_pool_items"]) if pools["timer_pool_items"] else "0 hẹn giờ"
    cur_uid = str(getattr(engine, "_current_user_id", "") or "").strip()
    try:
        from simulator.automation_repo import (
            list_automation_rules,
            list_custom_commands,
            list_schedules,
        )

        if cur_tier >= 3:
            db_scheds, db_rules, db_scenes = [], [], []
        else:
            owner_q = None if cur_tier == 1 else (cur_uid or "__NO_OWNER__")
            db_scheds = list_schedules(include_disabled=False, owner_user_id=owner_q)
            db_rules = list_automation_rules(include_disabled=False, owner_user_id=owner_q)
            db_scenes = list_custom_commands(include_disabled=False, owner_user_id=owner_q)
    except Exception:
        db_scheds, db_rules, db_scenes = [], [], []
    if cur_tier >= 3:
        alias_txt = "Khách không có lệnh riêng"
        words_txt = "Không có"
        ifelse_txt = "Khách không có liên kết"
        timers_txt = "Khách không có hẹn giờ"
        scheds_txt = "Không có"
        db_rules_txt = "Không có"
        scenes_txt = "Không có"
    else:
        scheds_txt = "; ".join(
            f"{s['time_hhmm']} ({'hằng ngày' if s['schedule_type'] == 'daily' else 'một lần'}): {s['label']}"
            + (f" của {s.get('owner_name') or s.get('owner_user_id')}" if cur_tier == 1 else "")
            for s in db_scheds
        ) if db_scheds else "Chưa có"
        db_rules_txt = "; ".join(
            r["label"] + (f" của {r.get('owner_name') or r.get('owner_user_id')}" if cur_tier == 1 else "")
            for r in db_rules
        ) if db_rules else "Chưa có"
        scenes_txt = "; ".join(
            f"'{c['phrase']}': {c['steps_summary']}"
            + (f" của {c.get('owner_name') or c.get('owner_user_id')}" if cur_tier == 1 else "")
            for c in db_scenes
        ) if db_scenes else "Chưa có"

    return (
        "Bạn là trợ lý giọng nói Nhà Thông Minh Bách Khoa do Nguyễn Tuấn Anh tạo ra.\n"
        "Giọng đọc mặc định duy nhất: Aoede. Luôn trò chuyện bằng tiếng Việt tự nhiên, ngắn gọn trong 1-2 câu như người bình thường.\n"
        "\n"
        "1. DANH TÍNH & PHÂN QUYỀN HIỆN TẠI (ĐÃ XÁC THỰC PHÍA MÁY CHỦ):\n"
        f"- Người đang nói: {cur_user} (Cấp {cur_tier}, vai trò {cur_role}).\n"
        "- Cấp 1 (Chủ nhà): toàn quyền thiết bị, xem/sửa/xóa hẹn giờ, lịch và ngữ cảnh của mọi người.\n"
        "- Cấp 2 (Gia đình): điều khiển đèn phòng khách, đèn phòng ngủ, máy bơm tưới cây và nguồn mạch loa PAM8403; chỉ xem và quản lý hẹn giờ, lịch, ngữ cảnh của chính mình; không được mở cửa chính, bật còi báo động hay đặt lịch trùng trong 60 giây với Chủ nhà.\n"
        "- Cấp 3 (Khách): chỉ được bật tắt đèn phòng khách và đèn phòng ngủ. Mọi yêu cầu khác chỉ đáp: 'Khách chỉ được bật tắt thiết bị thôi ạ.'.\n"
        "\n"
        "2. QUY TẮC NÓI TỰ NHIÊN & PHẠM VI:\n"
        "- Ngôn ngữ (Vietnamese Prompt Guard): Phản hồi 100% bằng tiếng Việt tự nhiên, ngắn gọn trong 1-2 câu.\n"
        "- Tuyệt đối không đọc to cú pháp lệnh, JSON, tên hàm, mã kỹ thuật tiếng Anh hay dấu ngoặc; luôn diễn đạt kết quả từ công cụ thành lời nói tự nhiên.\n"
        "- Cấm ngoại ngữ: Không trả lời bằng tiếng Anh, tiếng Trung, tiếng Pháp, tiếng Tây Ban Nha, tiếng Hàn hoặc ngôn ngữ khác.\n"
        f'- Âm đệm & ngập ngừng (Filler Sound & Hesitation Guard): Khi có từ đệm (\'ừm\', \'ờ\', \'à\', \'alô\', \'aló\') đi kèm lệnh rõ ràng thì chỉ hiểu phần lệnh; nếu chỉ là âm đệm hoặc ồn quá ngắn, chỉ đáp: "Tôi có thể giúp gì cho bạn?" hoặc "{FIXED_SAFE_DENY_REPEAT_PHRASE_VI}".\n'
        "- Phạm vi (Smart Home Domain Guard): Chỉ hỗ trợ 6 thiết bị chấp hành và 3 cảm biến nhà thông minh:\n"
        "  + 6 thiết bị: Cửa chính (D1), Đèn phòng khách (D0), Đèn phòng ngủ (D4), Máy bơm tưới cây (D6), Còi báo động (D8), Nguồn mạch loa PAM8403 (D7, âm thanh PWM ra D3).\n"
        "  + 3 cảm biến: Nhiệt độ/độ ẩm DHT11 (D2), Độ ẩm đất (A0), Cảm biến âm thanh KY-037 DO (D5 phát hiện vỗ tay/tiếng động lớn). Trợ lý giọng nói thu âm và phát thoại qua micro/loa trên trình duyệt web hoặc thiết bị.\n"
        "  + Ngoài phạm vi nhà thông minh, chỉ đáp: 'Tôi chỉ hỗ trợ điều khiển thiết bị trong nhà thông minh.'.\n"
        "  + Cấm dịch thuật hay làm theo chỉ thị ngoài lề: chỉ đáp nguyên văn 'Tôi chỉ hỗ trợ điều khiển thiết bị trong nhà thông minh.'.\n"
        "\n"
        "3. TRẠNG THÁI NHÀ & CẢM BIẾN:\n"
        f"- Thiết bị: {devs_txt}.\n"
        f"- Cảm biến: Nhiệt độ {dht.get('temp_c', 28.5)} độ C, độ ẩm không khí {dht.get('humidity_pct', 65.0)}%, độ ẩm đất {soil.get('soil_moisture_pct', 55.0)}%, âm thanh KY-037 ({sound.get('status_label', 'Yên tĩnh')}).\n"
        f"- Hẹn giờ đang chạy: {timers_txt}.\n"
        f"- Lịch theo giờ: {scheds_txt}.\n"
        f"- Từ vựng riêng của {cur_user}: {words_txt}.\n"
        f"- Khẩu lệnh riêng của {cur_user}: {alias_txt}.\n"
        f"- Ngữ cảnh tùy chỉnh: {scenes_txt}.\n"
        f"- Luật liên kết của {cur_user}: {ifelse_txt}; Luật đã lưu: {db_rules_txt}.\n"
        "\n"
        "4. QUY TẮC HÀNH ĐỘNG & XÁC NHẬN (6 CHÍNH SÁCH BẮT BUỘC):\n"
        "- CHÍNH SÁCH 1 (HÀNH ĐỘNG NGAY với lệnh thiết bị đơn giản): Mọi lệnh bật/tắt/mở/đóng trực tiếp cho 6 thiết bị (VD: 'mở cửa', 'đóng cửa', 'bật đèn phòng khách', 'tắt tất cả đèn', 'bật máy bơm', 'tắt còi', 'bật loa') -> gọi ngay công cụ điều khiển thiết bị để thực thi NGAY LẬP TỨC (KHÔNG hỏi xác nhận trước) và chỉ báo lại CỰC NGẮN GỌN SAU KHI LÀM XONG (VD: 'Đã mở cửa chính.', 'Đã bật đèn phòng khách.').\n"
        "- CHÍNH SÁCH 2 (CHỈ XÁC NHẬN với cấu hình phức tạp/tự động hóa): CHỈ hỏi xác nhận ngắn bằng tiếng Việt (VD: 'Mình sẽ tắt đèn phòng khách sau 10 phút, bạn đồng ý không?') trước khi thực thi đối với: (1) tạo/sửa/xóa/chạy lệnh tùy chỉnh (custom command), (2) đặt/sửa/hủy hẹn giờ & lịch, (3) tạo/xóa luật liên kết giữa thiết bị hoặc cảm biến, (4) reset thiết bị / reset bể lệnh / khôi phục cài đặt gốc. Khi người dùng trả lời 'ok'/'đồng ý'/'được'/'đúng rồi'/'ừ'/'có' mới xác nhận; nói 'không'/'hủy'/'thôi' thì hủy và báo 'Đã hủy.'.\n"
        "- CHÍNH SÁCH 3 (HỎI CẢM BIẾN & TRẠNG THÁI): Khi hỏi nhiệt độ, độ ẩm, độ ẩm đất, âm thanh KY-037, trạng thái thiết bị hoặc chế độ bơm tự động -> gọi công cụ đọc tương ứng và trả lời ngay số liệu thực tế bằng tiếng Việt ngắn gọn.\n"
        "- CHÍNH SÁCH 4 (CHÀO HỎI & GIAO TIẾP TỰ NHIÊN): Các câu chào hỏi ('chào bạn', 'xin chào', 'bạn là ai', 'cảm ơn', 'tạm biệt', 'giúp tôi') luôn được trả lời thân thiện, ngắn gọn bằng tiếng Việt cho MỌI TẦNG QUYỀN (Cấp 1, 2, 3), TUYỆT ĐỐI KHÔNG báo lỗi không có quyền cho câu chào hỏi.\n"
        "- CHÍNH SÁCH 5 (KHÓA CỨNG 100% TIẾNG VIỆT): Luôn nghe hiểu và trả lời 100% bằng tiếng Việt. Nếu nghe ngoại ngữ, chỉ đáp bằng tiếng Việt: 'Tôi chỉ hỗ trợ tiếng Việt, bạn vui lòng nói lệnh bằng tiếng Việt nhé.' và KHÔNG thực hiện bất kỳ thao tác thiết bị nào.\n"
        "- CHÍNH SÁCH 6 (KHÔNG ĐOÁN BỪA KHI MƠ HỒ): Nếu thiếu hành động, thiếu thiết bị, thiết bị không hỗ trợ (quạt, điều hòa, tivi...) hoặc âm thanh nhiễu -> KHÔNG tác động thiết bị, chỉ hỏi lại ngắn gọn bằng tiếng Việt.\n"
        f'- Chỉ khi người dùng cố thực hiện lệnh thiết bị/tự động hóa vượt quá cấp quyền mới nói: "{FIXED_REJECTION_PHRASE_VI}".'
    )


def make_live_config(engine: SmartHomeEngine, *, strict_lang_fields: bool = True) -> types.LiveConnectConfig:
    voice_cfg = types.VoiceConfig(
        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
    )
    if strict_lang_fields:
        try:
            speech_cfg = types.SpeechConfig(voice_config=voice_cfg, language_code="vi-VN")
        except TypeError:
            speech_cfg = types.SpeechConfig(voice_config=voice_cfg)
        try:
            in_tx_cfg = types.AudioTranscriptionConfig(language_codes=["vi-VN"])
        except TypeError:
            in_tx_cfg = types.AudioTranscriptionConfig()
    else:
        speech_cfg = types.SpeechConfig(voice_config=voice_cfg)
        in_tx_cfg = types.AudioTranscriptionConfig()

    return types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        speech_config=speech_cfg,
        input_audio_transcription=in_tx_cfg,
        output_audio_transcription=types.AudioTranscriptionConfig(),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                silence_duration_ms=350,
                start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
                end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                prefix_padding_ms=100,
            )
        ),
        system_instruction=types.Content(parts=[types.Part(text=build_system_instruction(engine))]),
        tools=ALL_TOOLS,
    )
