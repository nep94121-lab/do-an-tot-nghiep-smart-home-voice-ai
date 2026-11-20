"""End-to-End User Journey suite (>= 170 utterances across 10 journeys & 6 personas).

Covers ALL 10 Mandatory Coverage Matrix categories:
  1. Session start (greetings, small talk, identity, help)
  2. Simple direct device commands (all 6 devices + all_lights + redundant + multi-device)
  3. Sensor & status readings (DHT11 temp/hum, soil moisture, KY-037 sound, device status, auto-pump)
  4. Custom commands (create, use, list, edit, delete — confirmation required)
  5. Schedules & timers (clock, countdown, daily, list, modify, VERIFY real fire, cancel — confirmation required)
  6. Cross-connected rules (door->light, soil_dry->pump, loud_sound->siren — VERIFY all 3 trigger, list, delete)
  7. Reset (reset device states, reset rules/timers, factory reset — confirmation required, verify state)
  8. Confirmation edge flows (yes variants, no variants, timeout/expired, unrelated reply, mid-confirm interruption)
  9. Error & edge cases (unknown devices, partial/ambiguous, nonsense, pure noise, foreign speech, Tier 2 & Tier 3 RBAC)
 10. Session end & resume
"""

from __future__ import annotations

import dataclasses
from typing import Any


COVERAGE_CATEGORIES: dict[int, str] = {
    1: "Session Start (Greetings / Identity / Help)",
    2: "Simple Direct Device Commands (Act-First)",
    3: "Sensor & Device Status Readings",
    4: "Custom Commands (Create / Use / Edit / Delete)",
    5: "Schedules & Timers (Create / List / Modify / Fire / Cancel)",
    6: "Cross-Connected Rules (Create / Trigger / List / Delete)",
    7: "Reset (Device States / Rules / Factory Reset)",
    8: "Confirmation Edge Flows (Yes / No / Timeout / Unrelated / Interrupt)",
    9: "Error, Noise, Foreign Speech & RBAC Edge Cases",
    10: "Session End & Resume",
}


@dataclasses.dataclass(frozen=True)
class JourneyStep:
    step_id: str
    journey_id: str
    category: int  # 1..10
    subcat: str
    persona: str  # bac_male | nam_female | trung_adult | elderly | kid_fast | mumbler_guest
    tier: int  # 1 (owner) | 2 (family) | 3 (guest)
    text: str  # Utterance text (for TTS & /api/text_command)
    expected_behavior: str
    # Supported expected_behavior values:
    #   small_talk | immediate_device | sensor_query | status_query | pool_query
    #   confirm_prompt | confirm_yes | confirm_no | confirm_expired | confirm_reminder
    #   clarify_no_action | rbac_denied | noise_no_action | foreign_no_action
    lang: str = "vi"
    audio_kind: str = "speech"  # speech | pure_white_noise | pure_babble_noise
    expected_http_status: int = 200
    expected_device_states: dict[str, str] = dataclasses.field(default_factory=dict)
    expected_reply_substrings: tuple[str, ...] = ()
    forbidden_reply_substrings: tuple[str, ...] = ("không có quyền",)
    pre_setup: str = ""  # Optional harness hook BEFORE running step
    post_verify: str = ""  # Optional harness hook AFTER running step (e.g. wait_timer_fire, trigger_cross_rule)
    degraded_sample: bool = False  # Include in 11-degradation audio matrix


@dataclasses.dataclass(frozen=True)
class UserJourney:
    journey_id: str
    title: str
    persona: str
    tier: int
    description: str
    steps: tuple[JourneyStep, ...]


def _s(
    sid: str,
    jid: str,
    cat: int,
    subcat: str,
    persona: str,
    tier: int,
    text: str,
    beh: str,
    **kw: Any,
) -> JourneyStep:
    if beh == "rbac_denied":
        kw.setdefault("expected_http_status", 403)
        kw.setdefault("forbidden_reply_substrings", ())
    return JourneyStep(
        step_id=sid,
        journey_id=jid,
        category=cat,
        subcat=subcat,
        persona=persona,
        tier=tier,
        text=text,
        expected_behavior=beh,
        **kw,
    )


def build_user_journeys() -> list[UserJourney]:
    """Build 10 complete ordered End-to-End user journeys totaling >= 170 utterances."""
    journeys: list[UserJourney] = []

    # ------------------------------------------------------------------
    # JOURNEY 1: Northern Adult Male Owner (Full End-to-End Lifecycle)
    # start -> simple -> sensor -> custom -> schedule+fire -> cross-rules+3 triggers -> reset -> end/resume
    # ------------------------------------------------------------------
    j1 = "J01_bac_male_full_lifecycle"
    p1 = "bac_male"
    journeys.append(
        UserJourney(
            journey_id=j1,
            title="Chủ nhà giọng Bắc — Hành trình trọn vẹn từ đầu tới cuối",
            persona=p1,
            tier=1,
            description="Full E2E lifecycle: start -> all 6 devices + all_lights + multi-device -> sensors -> custom CRUD -> schedule+real fire -> all 3 cross-rules+real triggers -> reset -> end/resume.",
            steps=(
                # Cat 1: Session start
                _s("J01_01", j1, 1, "greeting", p1, 1, "chào buổi sáng", "small_talk", degraded_sample=True),
                _s("J01_02", j1, 1, "identity", p1, 1, "bạn là ai", "small_talk", degraded_sample=True),
                _s("J01_03", j1, 1, "help", p1, 1, "bạn có thể làm những gì", "small_talk"),
                # Cat 2: All 6 devices + redundant + all_lights + multi-device
                _s("J01_04", j1, 2, "main_door_open", p1, 1, "mở cửa", "immediate_device", pre_setup="reset_devices_off", expected_device_states={"main_door": "OPEN"}, degraded_sample=True),
                _s("J01_05", j1, 2, "main_door_redundant", p1, 1, "mở cửa chính", "immediate_device", expected_device_states={"main_door": "OPEN"}, expected_reply_substrings=("đang mở",)),
                _s("J01_06", j1, 2, "living_light_on", p1, 1, "bật đèn phòng khách", "immediate_device", expected_device_states={"living_room_light": "ON"}, degraded_sample=True),
                _s("J01_07", j1, 2, "bedroom_light_on", p1, 1, "bật đèn phòng ngủ", "immediate_device", expected_device_states={"bedroom_light": "ON"}, degraded_sample=True),
                _s("J01_08", j1, 2, "all_lights_off", p1, 1, "tắt tất cả đèn", "immediate_device", expected_device_states={"living_room_light": "OFF", "bedroom_light": "OFF"}, degraded_sample=True),
                _s("J01_09", j1, 2, "pump_on", p1, 1, "bật máy bơm tưới cây", "immediate_device", expected_device_states={"garden_pump": "ON"}, degraded_sample=True),
                _s("J01_10", j1, 2, "pump_off", p1, 1, "tắt máy bơm", "immediate_device", expected_device_states={"garden_pump": "OFF"}),
                _s("J01_11", j1, 2, "siren_on", p1, 1, "bật còi báo động", "immediate_device", expected_device_states={"alarm_siren": "ON"}, degraded_sample=True),
                _s("J01_12", j1, 2, "siren_off", p1, 1, "tắt còi báo động", "immediate_device", expected_device_states={"alarm_siren": "OFF"}),
                _s("J01_13", j1, 2, "speaker_on", p1, 1, "bật nguồn mạch loa", "immediate_device", expected_device_states={"speaker_amp": "ON"}, degraded_sample=True),
                _s("J01_14", j1, 2, "speaker_off", p1, 1, "tắt nguồn mạch loa", "immediate_device", expected_device_states={"speaker_amp": "OFF"}),
                _s("J01_15", j1, 2, "multi_device", p1, 1, "bật đèn phòng khách và đóng cửa chính", "immediate_device", expected_device_states={"living_room_light": "ON", "main_door": "CLOSED"}, degraded_sample=True),
                # Cat 3: Sensor & status queries
                _s("J01_16", j1, 3, "temp_hum", p1, 1, "nhiệt độ và độ ẩm hiện tại là bao nhiêu", "sensor_query", pre_setup="set_sensors_known", expected_reply_substrings=("28.5", "65"), degraded_sample=True),
                _s("J01_17", j1, 3, "soil", p1, 1, "độ ẩm đất hiện tại bao nhiêu", "sensor_query", expected_reply_substrings=("58",), degraded_sample=True),
                _s("J01_18", j1, 3, "sound", p1, 1, "cảm biến âm thanh thế nào", "sensor_query", degraded_sample=True),
                _s("J01_19", j1, 3, "door_status", p1, 1, "cửa chính đang mở hay đóng", "status_query", expected_reply_substrings=("đang đóng",)),
                _s("J01_20", j1, 3, "auto_pump", p1, 1, "chế độ bơm tự động thế nào", "sensor_query", expected_reply_substrings=("40%", "70%")),
                # Cat 4: Custom command CRUD (create -> confirm -> use -> confirm -> edit -> confirm -> delete -> confirm)
                _s("J01_21", j1, 4, "custom_create", p1, 1, "tạo lệnh đi làm là tắt tất cả đèn và đóng cửa chính", "confirm_prompt", pre_setup="prep_custom_di_lam", degraded_sample=True),
                _s("J01_22", j1, 4, "custom_create_ok", p1, 1, "ok", "confirm_yes"),
                _s("J01_23", j1, 4, "custom_use", p1, 1, "đi làm", "confirm_prompt"),
                _s("J01_24", j1, 4, "custom_use_ok", p1, 1, "được", "confirm_yes", expected_device_states={"living_room_light": "OFF", "bedroom_light": "OFF", "main_door": "CLOSED"}),
                _s("J01_25", j1, 4, "custom_edit", p1, 1, "sửa lệnh đi làm thành bật đèn phòng khách và đóng cửa chính", "confirm_prompt"),
                _s("J01_26", j1, 4, "custom_edit_ok", p1, 1, "ừ", "confirm_yes"),
                _s("J01_27", j1, 4, "custom_delete", p1, 1, "xóa lệnh đi làm", "confirm_prompt"),
                _s("J01_28", j1, 4, "custom_delete_ok", p1, 1, "đồng ý", "confirm_yes"),
                # Cat 5: Schedules & timers (daily clock, short timer + REAL FIRE, list, modify, delete)
                _s("J01_29", j1, 5, "schedule_daily", p1, 1, "đặt lịch 7 giờ sáng hằng ngày mở cửa chính", "confirm_prompt", degraded_sample=True),
                _s("J01_30", j1, 5, "schedule_daily_ok", p1, 1, "ok", "confirm_yes"),
                _s("J01_31", j1, 5, "timer_short_create", p1, 1, "hẹn giờ 2 giây bật đèn phòng ngủ", "confirm_prompt", pre_setup="ensure_bedroom_off", degraded_sample=True),
                _s("J01_32", j1, 5, "timer_short_ok_fire", p1, 1, "có", "confirm_yes", post_verify="wait_timer_bedroom_on"),
                _s("J01_33", j1, 5, "schedule_list", p1, 1, "có những lịch hẹn nào", "pool_query", expected_reply_substrings=("07:00",)),
                _s("J01_34", j1, 5, "schedule_modify", p1, 1, "sửa lịch 07:00 thành 08:00", "confirm_prompt"),
                _s("J01_35", j1, 5, "schedule_modify_ok", p1, 1, "đồng ý", "confirm_yes"),
                _s("J01_36", j1, 5, "schedule_delete", p1, 1, "xóa lịch 08:00", "confirm_prompt"),
                _s("J01_37", j1, 5, "schedule_delete_ok", p1, 1, "ok", "confirm_yes"),
                # Cat 6: Cross-connected rules (create & REAL TRIGGER all 3 + list + delete)
                _s("J01_38", j1, 6, "rule_door_light", p1, 1, "khi mở cửa chính thì bật đèn phòng khách", "confirm_prompt", pre_setup="prep_door_light_rule", degraded_sample=True),
                _s("J01_39", j1, 6, "rule_door_light_ok", p1, 1, "ok", "confirm_yes", post_verify="trigger_door_to_light"),
                _s("J01_40", j1, 6, "rule_soil_pump", p1, 1, "khi đất khô thì bật máy bơm tưới cây", "confirm_prompt", pre_setup="prep_soil_pump_rule", degraded_sample=True),
                _s("J01_41", j1, 6, "rule_soil_pump_ok", p1, 1, "được", "confirm_yes", post_verify="trigger_soil_to_pump"),
                _s("J01_42", j1, 6, "rule_sound_siren", p1, 1, "khi có tiếng động lớn thì bật còi báo động", "confirm_prompt", pre_setup="prep_sound_siren_rule", degraded_sample=True),
                _s("J01_43", j1, 6, "rule_sound_siren_ok", p1, 1, "ừ", "confirm_yes", post_verify="trigger_sound_to_siren"),
                _s("J01_44", j1, 6, "rule_list", p1, 1, "liệt kê các liên kết", "pool_query"),
                _s("J01_45", j1, 6, "rule_delete", p1, 1, "xóa liên kết đèn phòng khách", "confirm_prompt"),
                _s("J01_46", j1, 6, "rule_delete_ok", p1, 1, "ok", "confirm_yes"),
                # Cat 7: Reset device states & reset links
                _s("J01_47", j1, 7, "reset_devices", p1, 1, "reset trạng thái thiết bị", "confirm_prompt", degraded_sample=True),
                _s("J01_48", j1, 7, "reset_devices_ok", p1, 1, "đồng ý", "confirm_yes", expected_device_states={"main_door": "CLOSED", "living_room_light": "OFF", "bedroom_light": "OFF", "garden_pump": "OFF", "alarm_siren": "OFF", "speaker_amp": "OFF"}),
                _s("J01_49", j1, 7, "reset_links", p1, 1, "reset liên kết", "confirm_prompt"),
                _s("J01_50", j1, 7, "reset_links_ok", p1, 1, "ok", "confirm_yes"),
                # Cat 10: Session end & resume
                _s("J01_51", j1, 10, "thanks", p1, 1, "cảm ơn bạn", "small_talk"),
                _s("J01_52", j1, 10, "goodbye", p1, 1, "tạm biệt", "small_talk", degraded_sample=True),
                _s("J01_53", j1, 10, "resume_hi", p1, 1, "xin chào", "small_talk"),
                _s("J01_54", j1, 10, "resume_cmd", p1, 1, "bật đèn phòng khách", "immediate_device", expected_device_states={"living_room_light": "ON"}),
            ),
        )
    )

    # ------------------------------------------------------------------
    # JOURNEY 2: Southern Female Owner (Colloquial + Filler Words + ALL Confirmation Edge Flows)
    # ------------------------------------------------------------------
    j2 = "J02_nam_female_confirm_flows"
    p2 = "nam_female"
    journeys.append(
        UserJourney(
            journey_id=j2,
            title="Chủ nhà giọng Nam — Khẩu ngữ + Toàn bộ luồng xác nhận",
            persona=p2,
            tier=1,
            description="Southern colloquial phrasing, filler words (ờ/à/ừm/này), yes/no variants, timeout, unrelated reply, and mid-confirm interruption.",
            steps=(
                _s("J02_01", j2, 1, "greeting", p2, 1, "xin chào trợ lý", "small_talk"),
                _s("J02_02", j2, 1, "help", p2, 1, "hướng dẫn giúp mình", "small_talk"),
                # Cat 2: Southern colloquial & fillers
                _s("J02_03", j2, 2, "filler_door", p2, 1, "ờ mở cổng giúp mình nha", "immediate_device", pre_setup="reset_devices_off", expected_device_states={"main_door": "OPEN"}, degraded_sample=True),
                _s("J02_04", j2, 2, "colloq_living", p2, 1, "à bật bóng đèn khách đi", "immediate_device", expected_device_states={"living_room_light": "ON"}),
                _s("J02_05", j2, 2, "colloq_bed", p2, 1, "ừm bật bóng đèn ngủ giùm mình", "immediate_device", expected_device_states={"bedroom_light": "ON"}),
                _s("J02_06", j2, 2, "filler_pump", p2, 1, "này bật bơm nước luôn", "immediate_device", expected_device_states={"garden_pump": "ON"}),
                _s("J02_07", j2, 2, "colloq_pump_off", p2, 1, "ngừng tưới cây nhé", "immediate_device", expected_device_states={"garden_pump": "OFF"}),
                _s("J02_08", j2, 2, "colloq_speaker_on", p2, 1, "bật loa nha", "immediate_device", expected_device_states={"speaker_amp": "ON"}),
                _s("J02_09", j2, 2, "colloq_speaker_off", p2, 1, "tắt âm ly đi", "immediate_device", expected_device_states={"speaker_amp": "OFF"}),
                _s("J02_10", j2, 2, "colloq_door_lock", p2, 1, "khóa cửa chính đi", "immediate_device", expected_device_states={"main_door": "CLOSED"}),
                _s("J02_11", j2, 2, "all_lights_off", p2, 1, "tắt hết đèn", "immediate_device", expected_device_states={"living_room_light": "OFF", "bedroom_light": "OFF"}),
                _s("J02_12", j2, 2, "all_lights_on", p2, 1, "bật cả hai đèn", "immediate_device", expected_device_states={"living_room_light": "ON", "bedroom_light": "ON"}),
                # Cat 3: Status & sensor
                _s("J02_13", j2, 3, "all_status", p2, 1, "xem trạng thái tất cả thiết bị", "status_query"),
                _s("J02_14", j2, 3, "light_status", p2, 1, "đèn phòng khách có đang bật không", "status_query", expected_reply_substrings=("đang bật",)),
                # Cat 8: ALL Confirmation Edge Flows
                _s("J02_15", j2, 8, "confirm_prompt_ok", p2, 1, "10 phút nữa tắt đèn phòng khách", "confirm_prompt", degraded_sample=True),
                _s("J02_16", j2, 8, "confirm_yes_ok", p2, 1, "ok", "confirm_yes"),
                _s("J02_17", j2, 8, "confirm_prompt_duoc", p2, 1, "15 phút nữa bật đèn phòng ngủ", "confirm_prompt"),
                _s("J02_18", j2, 8, "confirm_yes_duoc", p2, 1, "được", "confirm_yes"),
                _s("J02_19", j2, 8, "confirm_prompt_u", p2, 1, "20 phút nữa tắt máy bơm", "confirm_prompt"),
                _s("J02_20", j2, 8, "confirm_yes_u", p2, 1, "ừ", "confirm_yes"),
                _s("J02_21", j2, 8, "confirm_prompt_co", p2, 1, "25 phút nữa mở cửa chính", "confirm_prompt"),
                _s("J02_22", j2, 8, "confirm_yes_co", p2, 1, "có", "confirm_yes"),
                _s("J02_23", j2, 8, "confirm_prompt_dongy", p2, 1, "30 phút nữa đóng cửa chính", "confirm_prompt"),
                _s("J02_24", j2, 8, "confirm_yes_dongy", p2, 1, "đồng ý", "confirm_yes"),
                _s("J02_25", j2, 8, "cancel_prompt_khong", p2, 1, "10 phút nữa bật còi báo động", "confirm_prompt"),
                _s("J02_26", j2, 8, "cancel_no_khong", p2, 1, "không", "confirm_no"),
                _s("J02_27", j2, 8, "cancel_prompt_thoi", p2, 1, "12 phút nữa bật loa", "confirm_prompt"),
                _s("J02_28", j2, 8, "cancel_no_thoi", p2, 1, "thôi", "confirm_no"),
                _s("J02_29", j2, 8, "cancel_prompt_huy", p2, 1, "14 phút nữa mở cửa chính", "confirm_prompt"),
                _s("J02_30", j2, 8, "cancel_no_huy", p2, 1, "hủy", "confirm_no"),
                # Unrelated reply mid-confirm -> reminds without executing
                _s("J02_31", j2, 8, "unrelated_stage", p2, 1, "8 phút nữa tắt đèn phòng khách", "confirm_prompt"),
                _s("J02_32", j2, 8, "unrelated_reply", p2, 1, "hôm nay trời mát quá nhỉ", "confirm_reminder"),
                _s("J02_33", j2, 8, "unrelated_cancel", p2, 1, "hủy", "confirm_no"),
                # Interruption mid-confirm with valid direct command -> cancels pending & runs new command immediately
                _s("J02_34", j2, 8, "interrupt_stage", p2, 1, "9 phút nữa bật đèn phòng ngủ", "confirm_prompt"),
                _s("J02_35", j2, 8, "interrupt_cmd", p2, 1, "tắt đèn phòng khách", "immediate_device", expected_device_states={"living_room_light": "OFF"}),
                # Timeout/expired confirmation -> MUST NOT execute
                _s("J02_36", j2, 8, "timeout_stage", p2, 1, "7 phút nữa tắt đèn phòng ngủ", "confirm_prompt"),
                _s("J02_37", j2, 8, "timeout_expired", p2, 1, "ok", "confirm_expired", pre_setup="expire_pending_confirmations"),
                # Cat 7: Clear timers
                _s("J02_38", j2, 7, "reset_timers", p2, 1, "xóa hết hẹn giờ", "confirm_prompt"),
                _s("J02_39", j2, 7, "reset_timers_ok", p2, 1, "ok", "confirm_yes"),
                # Cat 10: End & resume
                _s("J02_40", j2, 10, "goodnight", p2, 1, "chúc ngủ ngon", "small_talk"),
                _s("J02_41", j2, 10, "resume_greet", p2, 1, "chào bạn", "small_talk"),
            ),
        )
    )

    # ------------------------------------------------------------------
    # JOURNEY 3: Central Adult Owner (Regional + Redundant + Multi-Device + Timer Modify)
    # ------------------------------------------------------------------
    j3 = "J03_trung_adult_multi_and_custom"
    p3 = "trung_adult"
    journeys.append(
        UserJourney(
            journey_id=j3,
            title="Chủ nhà giọng Trung — Đa thiết bị, lệnh lặp, ngữ cảnh & sửa hẹn giờ",
            persona=p3,
            tier=1,
            description="Central regional speaker testing redundant commands, 2-3 device compound sentences, custom scene listing, and timer modification.",
            steps=(
                _s("J03_01", j3, 1, "greeting", p3, 1, "chào buổi trưa", "small_talk"),
                _s("J03_02", j3, 1, "identity", p3, 1, "bạn tên là gì", "small_talk"),
                _s("J03_03", j3, 2, "door_open", p3, 1, "mở cửa lớn", "immediate_device", pre_setup="reset_devices_off", expected_device_states={"main_door": "OPEN"}),
                _s("J03_04", j3, 2, "door_close", p3, 1, "đóng cửa lớn", "immediate_device", expected_device_states={"main_door": "CLOSED"}),
                _s("J03_05", j3, 2, "door_redundant_closed", p3, 1, "đóng cửa chính", "immediate_device", expected_device_states={"main_door": "CLOSED"}, expected_reply_substrings=("đang đóng",)),
                _s("J03_06", j3, 2, "light_on", p3, 1, "bật đèn phòng khách", "immediate_device", expected_device_states={"living_room_light": "ON"}),
                _s("J03_07", j3, 2, "light_redundant_on", p3, 1, "bật đèn phòng khách", "immediate_device", expected_device_states={"living_room_light": "ON"}, expected_reply_substrings=("đang bật",)),
                _s("J03_08", j3, 2, "multi_2", p3, 1, "bật đèn phòng ngủ và bật nguồn mạch loa", "immediate_device", expected_device_states={"bedroom_light": "ON", "speaker_amp": "ON"}),
                _s("J03_09", j3, 2, "multi_3", p3, 1, "tắt đèn phòng khách, tắt đèn phòng ngủ và tắt nguồn mạch loa", "immediate_device", expected_device_states={"living_room_light": "OFF", "bedroom_light": "OFF", "speaker_amp": "OFF"}),
                _s("J03_10", j3, 2, "siren_on_colloq", p3, 1, "bật còi hú", "immediate_device", expected_device_states={"alarm_siren": "ON"}),
                _s("J03_11", j3, 2, "siren_off_colloq", p3, 1, "tắt còi hú", "immediate_device", expected_device_states={"alarm_siren": "OFF"}),
                _s("J03_12", j3, 3, "air_hum", p3, 1, "độ ẩm không khí hiện tại là bao nhiêu", "sensor_query"),
                _s("J03_13", j3, 3, "siren_status", p3, 1, "còi báo động có đang kêu không", "status_query", expected_reply_substrings=("đang tắt",)),
                _s("J03_14", j3, 4, "custom_ve_nha", p3, 1, "tạo lệnh về nhà là mở cửa chính và bật đèn phòng khách", "confirm_prompt"),
                _s("J03_15", j3, 4, "custom_ve_nha_ok", p3, 1, "ok", "confirm_yes"),
                _s("J03_16", j3, 4, "custom_list", p3, 1, "có những lệnh custom nào", "pool_query", expected_reply_substrings=("về nhà",)),
                _s("J03_17", j3, 4, "custom_delete", p3, 1, "xóa lệnh về nhà", "confirm_prompt"),
                _s("J03_18", j3, 4, "custom_delete_ok", p3, 1, "ok", "confirm_yes"),
                _s("J03_19", j3, 5, "timer_create_for_mod", p3, 1, "hẹn giờ 60 giây tắt đèn phòng khách", "confirm_prompt"),
                _s("J03_20", j3, 5, "timer_create_ok", p3, 1, "ok", "confirm_yes"),
                _s("J03_21", j3, 5, "timer_modify", p3, 1, "đổi hẹn giờ đèn phòng khách thành 30 giây", "confirm_prompt"),
                _s("J03_22", j3, 5, "timer_modify_ok", p3, 1, "đồng ý", "confirm_yes"),
                _s("J03_23", j3, 5, "timer_cancel", p3, 1, "hủy hẹn giờ đèn phòng khách", "confirm_prompt"),
                _s("J03_24", j3, 5, "timer_cancel_ok", p3, 1, "ok", "confirm_yes"),
                _s("J03_25", j3, 10, "goodbye", p3, 1, "hẹn gặp lại", "small_talk"),
            ),
        )
    )

    # ------------------------------------------------------------------
    # JOURNEY 4: Elderly Owner (Slow/Polite Speech + Factory Reset)
    # ------------------------------------------------------------------
    j4 = "J04_elderly_polite_and_factory_reset"
    p4 = "elderly"
    journeys.append(
        UserJourney(
            journey_id=j4,
            title="Người lớn tuổi — Nói chậm, lịch sự & Khôi phục cài đặt gốc",
            persona=p4,
            tier=1,
            description="Elderly slow speaker using polite phrasing ('làm ơn', 'ạ', 'giúp tôi') and running a confirmed factory reset.",
            steps=(
                _s("J04_01", j4, 1, "greeting", p4, 1, "chào em", "small_talk"),
                _s("J04_02", j4, 1, "creator", p4, 1, "ai tạo ra bạn", "small_talk"),
                _s("J04_03", j4, 2, "polite_living_on", p4, 1, "làm ơn bật đèn phòng khách giúp tôi ạ", "immediate_device", pre_setup="reset_devices_off", expected_device_states={"living_room_light": "ON"}, degraded_sample=True),
                _s("J04_04", j4, 2, "polite_door_open", p4, 1, "mở cửa chính cho tôi nhé", "immediate_device", expected_device_states={"main_door": "OPEN"}),
                _s("J04_05", j4, 2, "polite_door_close", p4, 1, "khép cửa chính lại ạ", "immediate_device", expected_device_states={"main_door": "CLOSED"}),
                _s("J04_06", j4, 2, "polite_bed_on", p4, 1, "bật đèn phòng ngủ lên nhé", "immediate_device", expected_device_states={"bedroom_light": "ON"}),
                _s("J04_07", j4, 2, "polite_bed_off", p4, 1, "tắt đèn buồng đi ạ", "immediate_device", expected_device_states={"bedroom_light": "OFF"}),
                _s("J04_08", j4, 2, "polite_pump_on", p4, 1, "bật máy bơm tưới vườn nhé", "immediate_device", expected_device_states={"garden_pump": "ON"}),
                _s("J04_09", j4, 2, "polite_pump_off", p4, 1, "dừng tưới vườn ạ", "immediate_device", expected_device_states={"garden_pump": "OFF"}),
                _s("J04_10", j4, 3, "all_sensors", p4, 1, "kiểm tra tất cả cảm biến", "sensor_query"),
                _s("J04_11", j4, 3, "bed_status", p4, 1, "đèn phòng ngủ đang bật hay tắt", "status_query", expected_reply_substrings=("đang tắt",)),
                _s("J04_12", j4, 5, "clock_7am", p4, 1, "7 giờ sáng mở cửa chính", "confirm_prompt"),
                _s("J04_13", j4, 5, "clock_7am_ok", p4, 1, "vâng", "confirm_yes"),
                _s("J04_14", j4, 7, "factory_reset", p4, 1, "khôi phục cài đặt gốc", "confirm_prompt", degraded_sample=True),
                _s("J04_15", j4, 7, "factory_reset_ok", p4, 1, "đồng ý", "confirm_yes", expected_device_states={"main_door": "CLOSED", "living_room_light": "OFF", "bedroom_light": "OFF", "garden_pump": "OFF", "alarm_siren": "OFF", "speaker_amp": "OFF"}),
                _s("J04_16", j4, 10, "thanks_end", p4, 1, "cảm ơn nhiều", "small_talk"),
            ),
        )
    )

    # ------------------------------------------------------------------
    # JOURNEY 5: Fast Talker / Kid (Short Clipped Commands + Short Timer Fire)
    # ------------------------------------------------------------------
    j5 = "J05_kid_fast_short_commands"
    p5 = "kid_fast"
    journeys.append(
        UserJourney(
            journey_id=j5,
            title="Giọng trẻ / nói nhanh — Khẩu lệnh ngắn gọn & hẹn giờ nhanh",
            persona=p5,
            tier=1,
            description="High-pitch fast talker giving terse smart-home commands with fillers and a 3-second countdown timer.",
            steps=(
                _s("J05_01", j5, 1, "greeting", p5, 1, "chào bạn", "small_talk", degraded_sample=True),
                _s("J05_02", j5, 2, "door_open", p5, 1, "mở cửa", "immediate_device", pre_setup="reset_devices_off", expected_device_states={"main_door": "OPEN"}),
                _s("J05_03", j5, 2, "door_close", p5, 1, "đóng cửa", "immediate_device", expected_device_states={"main_door": "CLOSED"}, degraded_sample=True),
                _s("J05_04", j5, 2, "living_on", p5, 1, "bật đèn khách", "immediate_device", expected_device_states={"living_room_light": "ON"}),
                _s("J05_05", j5, 2, "living_off", p5, 1, "tắt đèn khách", "immediate_device", expected_device_states={"living_room_light": "OFF"}),
                _s("J05_06", j5, 2, "all_lights_on", p5, 1, "bật hết đèn", "immediate_device", expected_device_states={"living_room_light": "ON", "bedroom_light": "ON"}),
                _s("J05_07", j5, 2, "pump_short", p5, 1, "bật bơm", "immediate_device", expected_device_states={"garden_pump": "ON"}),
                _s("J05_08", j5, 2, "pump_short_off", p5, 1, "tắt bơm", "immediate_device", expected_device_states={"garden_pump": "OFF"}),
                _s("J05_09", j5, 2, "siren_short", p5, 1, "bật còi", "immediate_device", expected_device_states={"alarm_siren": "ON"}),
                _s("J05_10", j5, 2, "siren_short_off", p5, 1, "tắt còi", "immediate_device", expected_device_states={"alarm_siren": "OFF"}),
                _s("J05_11", j5, 2, "speaker_short", p5, 1, "bật loa", "immediate_device", expected_device_states={"speaker_amp": "ON"}),
                _s("J05_12", j5, 2, "speaker_short_off", p5, 1, "tắt loa", "immediate_device", expected_device_states={"speaker_amp": "OFF"}),
                _s("J05_13", j5, 3, "temp_short", p5, 1, "nhiệt độ bao nhiêu", "sensor_query"),
                _s("J05_14", j5, 5, "timer_3s_off", p5, 1, "sau 3 giây tắt đèn phòng khách", "confirm_prompt"),
                _s("J05_15", j5, 5, "timer_3s_ok", p5, 1, "ok", "confirm_yes", post_verify="wait_timer_living_off"),
                _s("J05_16", j5, 10, "praise", p5, 1, "tốt lắm", "small_talk"),
            ),
        )
    )

    # ------------------------------------------------------------------
    # JOURNEY 6: Mumbler / Noisy Room — Unknown Devices, Partial/Ambiguous, Nonsense, Pure Noise
    # ZERO FALSE ACTIONS ALLOWED!
    # ------------------------------------------------------------------
    j6 = "J06_mumbler_unknown_ambiguous_noise"
    p6 = "mumbler_guest"
    journeys.append(
        UserJourney(
            journey_id=j6,
            title="Phòng ồn / nói lầm bầm — Thiết bị lạ, câu thiếu, vô nghĩa & nhiễu thuần",
            persona=p6,
            tier=1,
            description="Adversarial unknown devices, partial/ambiguous utterances, pure fillers, gibberish, and pure white/babble noise. Target: 0% false actions.",
            steps=(
                # Unknown / removed devices -> Vietnamese refusal, ZERO action
                _s("J06_01", j6, 9, "unknown_fan", p6, 1, "bật quạt trần", "clarify_no_action", pre_setup="reset_devices_off", degraded_sample=True),
                _s("J06_02", j6, 9, "unknown_ac", p6, 1, "tắt điều hòa", "clarify_no_action", degraded_sample=True),
                _s("J06_03", j6, 9, "unknown_tv", p6, 1, "mở tivi", "clarify_no_action"),
                _s("J06_04", j6, 9, "unknown_washer", p6, 1, "bật máy giặt", "clarify_no_action"),
                _s("J06_05", j6, 9, "unknown_curtain", p6, 1, "đóng rèm cửa", "clarify_no_action"),
                _s("J06_06", j6, 9, "unknown_heater", p6, 1, "bật bình nóng lạnh", "clarify_no_action"),
                _s("J06_07", j6, 9, "unknown_ir", p6, 1, "học lệnh hồng ngoại", "clarify_no_action"),
                # Partial / ambiguous -> short Vietnamese clarification, ZERO action
                _s("J06_08", j6, 9, "ambig_door", p6, 1, "cửa chính", "clarify_no_action", degraded_sample=True),
                _s("J06_09", j6, 9, "ambig_light", p6, 1, "đèn phòng khách", "clarify_no_action"),
                _s("J06_10", j6, 9, "ambig_pump", p6, 1, "máy bơm", "clarify_no_action"),
                _s("J06_11", j6, 9, "ambig_all_lights", p6, 1, "tất cả đèn", "clarify_no_action"),
                _s("J06_12", j6, 9, "ambig_verb_on", p6, 1, "bật lên đi", "clarify_no_action", degraded_sample=True),
                _s("J06_13", j6, 9, "ambig_verb_off", p6, 1, "tắt đi", "clarify_no_action"),
                # Pure fillers / nonsense / gibberish -> ZERO action
                _s("J06_14", j6, 9, "filler_only", p6, 1, "ờ à ừm", "clarify_no_action", degraded_sample=True),
                _s("J06_15", j6, 9, "gibberish_1", p6, 1, "asdfghjkl", "clarify_no_action"),
                _s("J06_16", j6, 9, "digits_only", p6, 1, "123456", "clarify_no_action"),
                # Pure noise audio -> ZERO action (silent or Vietnamese clarification)
                _s("J06_17", j6, 9, "pure_white_noise_1", p6, 1, "nhiễu trắng 1", "noise_no_action", audio_kind="pure_white_noise", degraded_sample=True),
                _s("J06_18", j6, 9, "pure_white_noise_2", p6, 1, "nhiễu trắng 2", "noise_no_action", audio_kind="pure_white_noise"),
                _s("J06_19", j6, 9, "pure_babble_noise_1", p6, 1, "tạp âm hội thoại", "noise_no_action", audio_kind="pure_babble_noise", degraded_sample=True),
            ),
        )
    )

    # ------------------------------------------------------------------
    # JOURNEY 7: Foreign Language Adversarial Speech (EN / FR / KO / ES / DE)
    # 100% Vietnamese output required, ZERO device actions!
    # ------------------------------------------------------------------
    j7 = "J07_foreign_language_adversarial"
    p7 = "bac_male"
    journeys.append(
        UserJourney(
            journey_id=j7,
            title="Thử thách ngoại ngữ (Anh / Pháp / Hàn / Tây Ban Nha / Đức)",
            persona=p7,
            tier=1,
            description="Foreign-language speech & text inputs must NEVER switch reply language out of Vietnamese and must NEVER execute device actions.",
            steps=(
                _s("J07_01", j7, 9, "foreign_en_door", p7, 1, "Hello please open the main door", "foreign_no_action", lang="en", pre_setup="reset_devices_off", degraded_sample=True),
                _s("J07_02", j7, 9, "foreign_en_light", p7, 1, "Turn on the living room light now", "foreign_no_action", lang="en", degraded_sample=True),
                _s("J07_03", j7, 9, "foreign_en_temp", p7, 1, "What is the current temperature", "foreign_no_action", lang="en"),
                _s("J07_04", j7, 9, "foreign_en_alloff", p7, 1, "Turn off all lights please", "foreign_no_action", lang="en"),
                _s("J07_05", j7, 9, "foreign_fr_door", p7, 1, "Bonjour ouvre la porte principale", "foreign_no_action", lang="fr", degraded_sample=True),
                _s("J07_06", j7, 9, "foreign_fr_light", p7, 1, "Allume la lumière du salon", "foreign_no_action", lang="fr"),
                _s("J07_07", j7, 9, "foreign_ko_light", p7, 1, "안녕하세요 불 켜주세요", "foreign_no_action", lang="ko"),
                _s("J07_08", j7, 9, "foreign_es_door", p7, 1, "Hola abre la puerta principal", "foreign_no_action", lang="es"),
                _s("J07_09", j7, 9, "foreign_de_light", p7, 1, "Guten Morgen schalte das Licht ein", "foreign_no_action", lang="de"),
                _s("J07_10", j7, 9, "foreign_en_chat", p7, 1, "Sorry I only speak English", "foreign_no_action", lang="en"),
            ),
        )
    )

    # ------------------------------------------------------------------
    # JOURNEY 8: Tier 2 Family Member (Allowed devices work; Restricted devices/actions 403)
    # ------------------------------------------------------------------
    j8 = "J08_tier2_family_rbac"
    p8 = "nam_female"
    journeys.append(
        UserJourney(
            journey_id=j8,
            title="Thành viên gia đình (Cấp 2) — Kiểm thử phân quyền RBAC",
            persona=p8,
            tier=2,
            description="Tier 2 family member can greet, read sensors, control lights/pump/speaker, but MUST get 403 on main_door, alarm_siren, factory_reset, and ungranted links.",
            steps=(
                _s("J08_01", j8, 1, "t2_greeting", p8, 2, "chào bạn", "small_talk", pre_setup="reset_devices_off"),
                _s("J08_02", j8, 2, "t2_living_on", p8, 2, "bật đèn phòng khách", "immediate_device", expected_device_states={"living_room_light": "ON"}),
                _s("J08_03", j8, 2, "t2_pump_on", p8, 2, "bật máy bơm tưới cây", "immediate_device", expected_device_states={"garden_pump": "ON"}),
                _s("J08_04", j8, 2, "t2_pump_off", p8, 2, "tắt máy bơm", "immediate_device", expected_device_states={"garden_pump": "OFF"}),
                _s("J08_05", j8, 2, "t2_speaker_on", p8, 2, "bật nguồn mạch loa", "immediate_device", expected_device_states={"speaker_amp": "ON"}),
                _s("J08_06", j8, 2, "t2_speaker_off", p8, 2, "tắt nguồn mạch loa", "immediate_device", expected_device_states={"speaker_amp": "OFF"}),
                _s("J08_07", j8, 3, "t2_sensor", p8, 2, "nhiệt độ bao nhiêu", "sensor_query"),
                # Restricted for Tier 2 -> HTTP 403, ZERO mutation!
                _s("J08_08", j8, 9, "t2_deny_door", p8, 2, "mở cửa chính", "rbac_denied", expected_device_states={"main_door": "CLOSED"}),
                _s("J08_09", j8, 9, "t2_deny_siren", p8, 2, "bật còi báo động", "rbac_denied", expected_device_states={"alarm_siren": "OFF"}),
                _s("J08_10", j8, 9, "t2_deny_factory_reset", p8, 2, "khôi phục cài đặt gốc", "rbac_denied"),
                _s("J08_11", j8, 9, "t2_deny_ungranted_link", p8, 2, "khi đèn phòng khách bật thì bật đèn phòng ngủ", "rbac_denied"),
                _s("J08_12", j8, 10, "t2_thanks", p8, 2, "cảm ơn em", "small_talk"),
            ),
        )
    )

    # ------------------------------------------------------------------
    # JOURNEY 9: Tier 3 Guest (Bug (b) Regression: Greetings 200 OK; Restricted actions 403)
    # ------------------------------------------------------------------
    j9 = "J09_tier3_guest_rbac_and_greetings"
    p9 = "mumbler_guest"
    journeys.append(
        UserJourney(
            journey_id=j9,
            title="Khách (Cấp 3) — Chào hỏi luôn thân thiện, chặn nghiêm thiết bị & tự động hóa",
            persona=p9,
            tier=3,
            description="Tier 3 guest proves Bug (b) is permanently fixed (greetings never 403), lights work act-first, and door/siren/pump/speaker/schedules/custom/links/resets return 403.",
            steps=(
                _s("J09_01", j9, 1, "t3_chao_ban", p9, 3, "chào bạn", "small_talk", pre_setup="reset_devices_off", degraded_sample=True),
                _s("J09_02", j9, 1, "t3_xin_chao", p9, 3, "xin chào", "small_talk"),
                _s("J09_03", j9, 1, "t3_identity", p9, 3, "bạn là ai", "small_talk"),
                _s("J09_04", j9, 1, "t3_help", p9, 3, "giúp mình", "small_talk"),
                # Allowed for Tier 3: lights ONLY (act-first)
                _s("J09_05", j9, 2, "t3_living_on", p9, 3, "bật đèn phòng khách", "immediate_device", expected_device_states={"living_room_light": "ON"}),
                _s("J09_06", j9, 2, "t3_living_off", p9, 3, "tắt đèn phòng khách", "immediate_device", expected_device_states={"living_room_light": "OFF"}),
                _s("J09_07", j9, 2, "t3_bed_on", p9, 3, "bật đèn phòng ngủ", "immediate_device", expected_device_states={"bedroom_light": "ON"}),
                _s("J09_08", j9, 2, "t3_bed_off", p9, 3, "tắt đèn phòng ngủ", "immediate_device", expected_device_states={"bedroom_light": "OFF"}),
                # Restricted for Tier 3 -> HTTP 403, ZERO mutation!
                _s("J09_09", j9, 9, "t3_deny_door_open", p9, 3, "mở cửa chính", "rbac_denied", expected_device_states={"main_door": "CLOSED"}, degraded_sample=True),
                _s("J09_10", j9, 9, "t3_deny_door_close", p9, 3, "đóng cửa chính", "rbac_denied", expected_device_states={"main_door": "CLOSED"}),
                _s("J09_11", j9, 9, "t3_deny_pump", p9, 3, "bật máy bơm tưới cây", "rbac_denied", expected_device_states={"garden_pump": "OFF"}),
                _s("J09_12", j9, 9, "t3_deny_siren", p9, 3, "bật còi báo động", "rbac_denied", expected_device_states={"alarm_siren": "OFF"}),
                _s("J09_13", j9, 9, "t3_deny_speaker", p9, 3, "bật nguồn mạch loa", "rbac_denied", expected_device_states={"speaker_amp": "OFF"}),
                _s("J09_14", j9, 9, "t3_deny_timer", p9, 3, "10 phút nữa tắt đèn phòng khách", "rbac_denied"),
                _s("J09_15", j9, 9, "t3_deny_custom", p9, 3, "tạo lệnh khách là bật đèn phòng khách", "rbac_denied"),
                _s("J09_16", j9, 9, "t3_deny_link", p9, 3, "khi đèn phòng khách bật thì bật đèn phòng ngủ", "rbac_denied"),
                _s("J09_17", j9, 9, "t3_deny_reset", p9, 3, "reset trạng thái thiết bị", "rbac_denied"),
                _s("J09_18", j9, 10, "t3_bye", p9, 3, "tạm biệt", "small_talk"),
            ),
        )
    )

    # ------------------------------------------------------------------
    # JOURNEY 10: Evening Session End + New Session Resume
    # ------------------------------------------------------------------
    j10 = "J10_evening_end_and_resume"
    p10 = "trung_adult"
    journeys.append(
        UserJourney(
            journey_id=j10,
            title="Phiên buổi tối — Đóng phiên và khôi phục phiên mới",
            persona=p10,
            tier=1,
            description="Evening owner session exercising all_lights, all_devices off, evening schedule, clean session close, and fresh session resume.",
            steps=(
                _s("J10_01", j10, 1, "evening_hi", p10, 1, "chào buổi tối", "small_talk"),
                _s("J10_02", j10, 2, "all_lights_on", p10, 1, "bật tất cả đèn", "immediate_device", pre_setup="reset_devices_off", expected_device_states={"living_room_light": "ON", "bedroom_light": "ON"}),
                _s("J10_03", j10, 2, "open_door", p10, 1, "mở cửa chính", "immediate_device", expected_device_states={"main_door": "OPEN"}),
                _s("J10_04", j10, 2, "all_devices_off", p10, 1, "tắt tất cả thiết bị", "immediate_device", expected_device_states={"living_room_light": "OFF", "bedroom_light": "OFF", "garden_pump": "OFF", "alarm_siren": "OFF", "speaker_amp": "OFF", "main_door": "CLOSED"}),
                _s("J10_05", j10, 3, "all_dev_status", p10, 1, "trạng thái các thiết bị trong nhà", "status_query"),
                _s("J10_06", j10, 5, "evening_sched", p10, 1, "đặt lịch 21 giờ tối tắt đèn phòng ngủ", "confirm_prompt"),
                _s("J10_07", j10, 5, "evening_sched_ok", p10, 1, "ok", "confirm_yes"),
                _s("J10_08", j10, 5, "evening_sched_del", p10, 1, "xóa lịch 21:00", "confirm_prompt"),
                _s("J10_09", j10, 5, "evening_sched_del_ok", p10, 1, "được", "confirm_yes"),
                _s("J10_10", j10, 10, "session_end", p10, 1, "tạm biệt bạn", "small_talk"),
                _s("J10_11", j10, 10, "session_resume_greet", p10, 1, "chào buổi sáng", "small_talk", pre_setup="rotate_owner_session"),
                _s("J10_12", j10, 10, "session_resume_act", p10, 1, "mở cửa chính", "immediate_device", expected_device_states={"main_door": "OPEN"}),
                _s("J10_13", j10, 10, "session_resume_close", p10, 1, "đóng cửa chính", "immediate_device", expected_device_states={"main_door": "CLOSED"}),
            ),
        )
    )

    return journeys


def flatten_steps(journeys: list[UserJourney] | None = None) -> list[JourneyStep]:
    jlist = journeys if journeys is not None else build_user_journeys()
    return [st for j in jlist for st in j.steps]


def get_degraded_eval_steps(journeys: list[UserJourney] | None = None) -> list[JourneyStep]:
    """Return the >=25 representative utterances spanning all categories, noise & foreign speech."""
    all_steps = flatten_steps(journeys)
    return [st for st in all_steps if st.degraded_sample]
