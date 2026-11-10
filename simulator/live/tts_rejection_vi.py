"""Module Hằng Số Câu Thoại Từ Chối Tiếng Việt Chuẩn Cho Giọng Aoede (Gemini Live).

Mọi câu từ chối (Người lạ & Vượt quyền) và yêu cầu nói lại (Safe-Deny) chỉ được phát
thông qua duy nhất giọng đọc tích hợp `Aoede` của Gemini Live (tuyệt đối không dùng
TTS riêng bên ngoài hay Web Speech API).
"""

from __future__ import annotations

SAMPLE_RATE = 24000
AOEDE_VOICE_NAME = "Aoede"

FIXED_REJECTION_PHRASE_VI = "Xin lỗi, bạn không có quyền thực hiện lệnh này."
FIXED_SAFE_DENY_REPEAT_PHRASE_VI = "Âm thanh chưa rõ, vui lòng nói lại."
UNIFIED_REJECTION_PHRASE_VI = FIXED_REJECTION_PHRASE_VI
SAFE_DENY_REPEAT_PHRASE_VI = FIXED_SAFE_DENY_REPEAT_PHRASE_VI

REJECTION_SCRIPTS: dict[str, str] = {
    "STRANGER_BLOCKED": FIXED_REJECTION_PHRASE_VI,
    "STRANGER_BLOCKED_2": FIXED_REJECTION_PHRASE_VI,
    "DUPLICATE_VOICE": "Trùng giọng người đã có trong nhà - Từ chối lưu.",
    "VOICE_EXPIRED": FIXED_REJECTION_PHRASE_VI,
    "RATE_LIMITED": "Thao tác quá nhanh, vui lòng thử lại sau.",
    "TIER3_PERMISSION_DENIED": FIXED_REJECTION_PHRASE_VI,
    "TIER2_PERMISSION_DENIED": FIXED_REJECTION_PHRASE_VI,
    "OVER_PERMISSION_DENIED": FIXED_REJECTION_PHRASE_VI,
    "SAFE_DENY_REPEAT": FIXED_SAFE_DENY_REPEAT_PHRASE_VI,
    "VAD_BLOCKED": FIXED_SAFE_DENY_REPEAT_PHRASE_VI,
}

EXTENDED_TTS_SCRIPTS: dict[str, str] = {
    **REJECTION_SCRIPTS,
    "REST_STRANGER_BLOCKED": FIXED_REJECTION_PHRASE_VI,
    "VAD_NOISE_BLOCKED": FIXED_SAFE_DENY_REPEAT_PHRASE_VI,
    "ASK_REPEAT_AUDIO_QUALITY": FIXED_SAFE_DENY_REPEAT_PHRASE_VI,
    "OPEN_MAIN_DOOR": "Cửa chính đã mở.",
    "CLOSE_MAIN_DOOR": "Cửa chính đã đóng.",
    "TURN_ON_LIVING_ROOM_LIGHT": "Đèn phòng khách đã bật.",
    "TURN_OFF_LIVING_ROOM_LIGHT": "Đèn phòng khách đã tắt.",
    "TURN_ON_BEDROOM_LIGHT": "Đèn phòng ngủ đã bật.",
    "TURN_OFF_BEDROOM_LIGHT": "Đèn phòng ngủ đã tắt.",
    "TURN_ON_FAN": "Quạt trần đã bật.",
    "TURN_OFF_FAN": "Quạt trần đã tắt.",
    "TURN_ON_AC": "Điều hòa đã bật.",
    "TURN_OFF_AC": "Điều hòa đã tắt.",
}


def get_rejection_speech_text(reason_code: str) -> str:
    """Trả về nội dung văn bản tiếng Việt của câu từ chối cố định dành cho giọng Aoede."""
    code = (reason_code or "").strip()
    if code in EXTENDED_TTS_SCRIPTS:
        return EXTENDED_TTS_SCRIPTS[code]
    if code in REJECTION_SCRIPTS:
        return REJECTION_SCRIPTS[code]
    low = code.lower()
    if any(
        k in low
        for k in (
            "safe_deny",
            "ask_repeat",
            "vad",
            "noise",
            "chưa rõ",
            "nói lại",
            "quá ngắn",
            "nói đè",
        )
    ):
        return FIXED_SAFE_DENY_REPEAT_PHRASE_VI
    return FIXED_REJECTION_PHRASE_VI
