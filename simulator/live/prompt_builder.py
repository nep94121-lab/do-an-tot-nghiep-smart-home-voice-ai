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

fn_set_or_query_sensors = types.FunctionDeclaration(
    name="set_or_query_sensors",
    description=(
        "ĐỌC HOẶC TỰ SET (GIẢ LẬP) NHIỆT ĐỘ PHÒNG, ĐỘ ẨM KHÔNG KHÍ (CẢM BIẾN DHT11 - CHÂN D6) VÀ ĐỘ ẨM ĐẤT (CẢM BIẾN YL-69 - CHÂN A0) BẰNG GIỌNG NÓI:\n"
        "- Khi người dùng hỏi nhiệt độ, độ ẩm phòng, hoặc độ ẩm đất hiện tại (VD: 'Nhiệt độ phòng bao nhiêu?', 'Độ ẩm đất thế nào?') -> gọi với `operation='query'`.\n"
        "- Khi người dùng ra lệnh chỉnh/set nhiệt độ hoặc độ ẩm không khí DHT11 (VD: 'Chỉnh nhiệt độ lên 32 độ', 'Set nhiệt độ 26 độ, độ ẩm 60%') -> gọi với `operation='set'`, truyền `temp_c` và/hoặc `humidity_pct`.\n"
        "- Khi người dùng ra lệnh chỉnh/set độ ẩm đất YL-69 (VD: 'Set độ ẩm đất xuống 25%', 'Chỉnh độ ẩm đất 80%') -> gọi với `operation='set'`, truyền `soil_moisture_pct`. Nếu đất khô < 40% máy bơm (D3) sẽ tự bật, đủ ẩm >= 70% máy bơm tự tắt!"
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
                "description": "Nhiệt độ phòng (°C) muốn set cho cảm biến DHT11 (chân D6), ví dụ 32.0.",
            },
            "humidity_pct": {
                "type": "NUMBER",
                "description": "Độ ẩm không khí (%) muốn set cho cảm biến DHT11 (chân D6), ví dụ 65.0.",
            },
            "soil_moisture_pct": {
                "type": "NUMBER",
                "description": "Độ ẩm đất (%) muốn set cho cảm biến YL-69 (chân A0), ví dụ 25.0 (khô < 40% tự bật bơm, >= 70% tự tắt bơm).",
            },
        },
        "required": ["operation"],
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
            fn_set_or_query_sensors,
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
        "- BỨC TƯỜNG LỬA NGÔN NGỮ (VIETNAMESE PROMPT GUARD - BẮT BUỘC 100% TIẾNG VIỆT):\n"
        "  + BẮT BUỘC 100% PHẢN HỒI BẰNG TIẾNG VIỆT CHUẨN XÁC, TỰ NHIÊN, SÚC TÍCH TRONG MỌI TÌNH HUỐNG.\n"
        "  + TUYỆT ĐỐI KHÔNG BAO GIỜ TRẢ LỜI BẰNG TIẾNG ANH, TIẾNG TRUNG, TIẾNG PHÁP, TIẾNG TÂY BAN NHA, TIẾNG HÀN HOẶC BẤT KỲ NGOẠI NGỮ NÀO KHÁC.\n"
        "- BẢO VỆ ÂM ĐỆM & NGẬP NGỪNG (FILLER SOUND & HESITATION GUARD):\n"
        "  + Khi người dùng phát âm ngập ngừng hoặc nói từ đệm ('ừm', 'ờ', 'à', 'ừ', 'ê', 'aló', 'chờ tí', 'đợi tí', 'e hèm') hoặc có tiếng thở/ồn:\n"
        "    -> TUYỆT ĐỐI KHÔNG dịch hay phiên âm sang từ ngữ tiếng nước ngoài (không dịch thành 'Hola', 'boycott', 'voyage', '저거', v.v.); KHÔNG suy diễn lung tung.\n"
        "    -> Hãy tập trung trích xuất mệnh lệnh điều khiển tiếng Việt đi kèm.\n"
        "    -> Nếu cả câu CHỈ CHỨA ÂM ĐỆM VÔ NGHĨA hoặc tiếng ồn: Hãy giữ im lặng hoặc chỉ hỏi 1 câu nhẹ nhàng duy nhất: 'Tôi có thể giúp gì cho bạn?'.\n"
        "- GIỚI HẠN PHẠM VI NHÀ THÔNG MINH (SMART HOME DOMAIN GUARD):\n"
        "  + Bạn CHỈ LÀ TRỢ LÝ ĐIỀU KHIỂN 7 THIẾT BỊ NHÀ THÔNG MINH: Cửa chính (D1), Đèn phòng khách (D2), Đèn phòng ngủ (D7), Quạt trần (D6), Điều hòa Casper (D2 IR), Còi báo động (D8), Máy bơm tưới cây (D3) và giải đáp thông tin phân quyền 3 tầng.\n"
        "  + TUYỆT ĐỐI KHÔNG trả lời lan man sang các chủ đề ngoài lề (như tư vấn du lịch, dịch thuật, thơ ca, thời tiết nước ngoài, trò chuyện phiếm).\n"
        "  + Nếu người dùng hỏi chủ đề ngoài phạm vi nhà thông minh, chỉ đáp ngắn gọn đúng 1 câu: 'Tôi chỉ hỗ trợ điều khiển thiết bị trong nhà thông minh.'.\n"
        "- NGUYÊN TẮC TỐI THƯỢNG: HỎI GÌ ĐÁP NẤY, CỰC KỲ NGẮN GỌN, KHÔNG DÀI DÒNG (BẮT BUỘC 100%):\n"
        "  + Khi người dùng hỏi cái gì thì CHỈ TRẢ LỜI ĐÚNG CÁI ĐÓ trong 1 câu ngắn gọn (dưới 20 từ). TUYỆT ĐỐI KHÔNG liệt kê sang các thiết bị khác, KHÔNG đọc chân GPIO trừ khi được hỏi đích danh!\n"
        "  + Ví dụ: Hỏi 'Còi báo động nghĩa là gì?' -> Chỉ đáp: 'Còi báo động dùng để phát âm thanh cảnh báo an ninh trong nhà.' (TUYỆT ĐỐI KHÔNG kể lể nhà có 7 thiết bị, cửa chính, đèn, quạt!).\n"
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
        speech_config=types.SpeechConfig(
            language_code="vi-VN",
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
            ),
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                silence_duration_ms=1000,
                end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_LOW,
                prefix_padding_ms=300,
            )
        ),
        system_instruction=types.Content(parts=[types.Part(text=build_system_instruction(engine))]),
        tools=ALL_TOOLS,
    )
