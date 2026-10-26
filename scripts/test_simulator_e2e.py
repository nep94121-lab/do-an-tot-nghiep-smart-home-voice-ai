"""Kiểm thử toàn diện (Unit + E2E Gemini 3.8 Live) cho các tính năng mới:
1. Nhắc thiết bị đã mở/đóng/bật/tắt sẵn ("Cửa chính đã mở sẵn rồi.", "Đèn phòng khách đã bật sẵn rồi.").
2. Câu trả lời siêu ngắn gọn ("Cửa chính đã mở.", "Đèn phòng khách và điều hòa đã mở.").
3. Xét luật / Đổi lệnh / Đổi từ phải nhắc lại và hỏi xác nhận trước khi lưu vào Bể 2.
4. Phân tích giọng nói (VoiceAuthManager - 2 giọng test):
   - Giọng 1 (Chủ nhà - Được phép): Thực thi lệnh bình thường.
   - Giọng 2 (Người lạ - Không được phép):
     + Lần 1: "Không, bạn không có quyền."
     + Lần 2: "Bạn vẫn không đủ quyền."
     + Lần 3+: Vẫn nghe nhưng IM LẶNG TUYỆT ĐỐI (silent_ignore=True).
"""

from __future__ import annotations

import asyncio
import pathlib
import sys
import wave

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from simulator.rule_engine import SmartHomeEngine
from simulator.voice_auth import VoiceAuthManager

ROOT = pathlib.Path(__file__).resolve().parent.parent
AUDIO_DIR = ROOT / "test_audio"


async def test_unit_all_new_features() -> None:
    print("=== [1] KIỂM THỬ UNIT: NHẮC ĐÃ MỞ SẴN, TRẢ LỜI NGẮN GỌN, XÁC NHẬN LUẬT & PHÂN TÍCH GIỌNG 2-STRIKE ===", flush=True)
    eng = SmartHomeEngine()
    await eng.factory_reset()

    # 1. Mở cửa chính lần 1 -> "Cửa chính đã mở."
    r1 = await eng.execute_device_action("main_door", "open")
    assert r1["exact_spoken_reply"] == "Cửa chính đã mở.", f"Sai câu trả lời: {r1}"
    print(f"  [PASS] 1.1 Mở cửa lần 1 -> '{r1['exact_spoken_reply']}'")

    # 2. Mở cửa chính lần 2 khi cửa đang mở sẵn -> "Cửa chính đã mở sẵn rồi."
    r2 = await eng.execute_device_action("main_door", "open")
    assert r2["exact_spoken_reply"] == "Cửa chính đã mở sẵn rồi.", f"Sai câu nhắc mở sẵn: {r2}"
    print(f"  [PASS] 1.2 Mở cửa lần 2 (đang mở sẵn) -> '{r2['exact_spoken_reply']}'")

    # 3. Xét luật "Nếu bật đèn phòng khách thì mở điều hòa" (require_confirmation=True)
    prop = await eng.set_if_else_rule(
        when_device_id="living_room_light",
        when_state="ON",
        then_device_id="ac",
        then_action="turn_on",
        require_confirmation=True,
    )
    assert prop["status"] == "AWAITING_RULE_CONFIRMATION"
    assert len(eng.get_if_else_rules()) == 0, "Chưa xác nhận mà đã lưu luật!"
    print(f"  [PASS] 1.3 Xét luật (Bước 1 hỏi lại): '{prop['exact_spoken_reply']}'")

    # 4. Xác nhận lưu luật
    conf = await eng.confirm_pending_action(confirmed=True)
    assert conf["status"] == "RULE_CONFIRMED_AND_SAVED"
    assert len(eng.get_if_else_rules()) == 1
    print(f"  [PASS] 1.4 Xác nhận luật (Bước 2 lưu vào Bể 2): '{conf['exact_spoken_reply']}'")

    # 5. Bật đèn phòng khách -> kéo theo mở điều hòa -> trả lời siêu ngắn gọn: "Đèn phòng khách và điều hòa đã mở."
    r3 = await eng.execute_device_action("living_room_light", "turn_on")
    assert r3["exact_spoken_reply"] == "Đèn phòng khách và điều hòa đã mở.", f"Sai câu gộp: {r3}"
    print(f"  [PASS] 1.5 Luật liên tiếp (Đèn khách + Điều hòa) -> '{r3['exact_spoken_reply']}'")

    # 6. Kiểm thử Phân tích giọng nói (Giọng 1 Được phép vs Giọng 2 Không được phép - 2 lần rồi im lặng)
    vm = VoiceAuthManager(AUDIO_DIR)
    with wave.open(str(AUDIO_DIR / "giong_1_chu_nha_mo_cua.wav"), "rb") as w1:
        pcm_v1 = w1.readframes(w1.getnframes())
    with wave.open(str(AUDIO_DIR / "giong_2_nguoi_la_mo_cua.wav"), "rb") as w2:
        pcm_v2 = w2.readframes(w2.getnframes())

    v1_res = vm.verify_pcm16k_and_apply_strikes(pcm_v1)
    assert v1_res["authorized"] is True
    print(f"  [PASS] 1.6 Giọng 1 (Chủ nhà): F0={v1_res['f0_hz']}Hz -> Được phép (Authorized=True)")

    s1 = vm.verify_pcm16k_and_apply_strikes(pcm_v2)
    assert not s1["authorized"] and s1["strike_count"] == 1 and s1["should_reply"] is True
    print(f"  [PASS] 1.7 Giọng 2 (Lần 1): F0={s1['f0_hz']}Hz -> Chặn & Đáp: '{s1['rejection_speech']}'")

    s2 = vm.verify_pcm16k_and_apply_strikes(pcm_v2)
    assert not s2["authorized"] and s2["strike_count"] == 2 and s2["should_reply"] is True
    print(f"  [PASS] 1.8 Giọng 2 (Lần 2): F0={s2['f0_hz']}Hz -> Chặn & Đáp: '{s2['rejection_speech']}'")

    s3 = vm.verify_pcm16k_and_apply_strikes(pcm_v2)
    assert not s3["authorized"] and s3["strike_count"] == 3 and s3["silent_ignore"] is True and s3["should_reply"] is False
    print(f"  [PASS] 1.9 Giọng 2 (Lần 3): F0={s3['f0_hz']}Hz -> Vẫn nghe nhưng IM LẶNG TUYỆT ĐỐI (silent_ignore=True)")

    # 7. Kiểm thử 4 quy tắc Hẹn Giờ Thông Minh (Bể 1)
    await eng.factory_reset()

    # 7.1 Hẹn đếm ngược (10 giây nữa) -> KHÔNG kèm giờ đồng hồ hay ngày
    t1 = await eng.schedule_timer_flexible("living_room_light", "turn_on", seconds=10)
    assert t1["exact_spoken_reply"] == "Đã hẹn 10 giây nữa bật đèn phòng khách.", f"Sai 7.1: {t1}"
    p1 = eng.get_pools_summary()["timer_pool_items"]
    assert len(p1) == 1 and "AM" not in p1[0] and "PM" not in p1[0], f"Pool 7.1 vẫn lẫn giờ AM/PM: {p1}"
    print(f"  [PASS] 2.1 Hẹn đếm ngược 10s -> '{t1['exact_spoken_reply']}' | Bể 1: {p1}")
    await eng.factory_reset()

    # 7.2 Hẹn theo giờ có nói rõ AM hoặc PM ("8:00 PM") -> Tự hiểu mốc 8:00 PM tiếp theo, 1 lịch, không kèm ngày
    t2 = await eng.schedule_timer_flexible("ac", "open", vn_time_ampm="8:00 PM")
    assert t2["exact_spoken_reply"] == "Đã hẹn 8:00 PM mở điều hòa.", f"Sai 7.2: {t2}"
    p2 = eng.get_pools_summary()["timer_pool_items"]
    assert len(p2) == 1 and "#1: Mở Điều hòa lúc 8:00 PM" in p2[0], f"Pool 7.2 sai: {p2}"
    print(f"  [PASS] 2.2 Hẹn 8:00 PM -> '{t2['exact_spoken_reply']}' | Bể 1: {p2}")
    await eng.factory_reset()

    # 7.3 Hẹn theo giờ KHÔNG nói AM hay PM ("8:00") -> Tự hiểu đặt CẢ 8:00 AM VÀ 8:00 PM (2 lịch trong Bể 1)
    t3 = await eng.schedule_timer_flexible("living_room_light", "turn_on", vn_time_ampm="8:00")
    assert t3["exact_spoken_reply"] == "Đã hẹn 8:00 AM và 8:00 PM bật đèn phòng khách.", f"Sai 7.3: {t3}"
    p3 = eng.get_pools_summary()["timer_pool_items"]
    assert len(p3) == 2 and "8:00 AM" in p3[0] and "8:00 PM" in p3[1], f"Pool 7.3 sai: {p3}"
    print(f"  [PASS] 2.3 Hẹn 8:00 (không AM/PM) -> '{t3['exact_spoken_reply']}' | Bể 1 (2 lịch): {p3}")
    await eng.factory_reset()

    # 7.4 Hẹn kèm Ngày / Tháng ("8:00 PM", vn_date="25/10" và "8:00", vn_date="25/10")
    t4 = await eng.schedule_timer_flexible("main_door", "open", vn_time_ampm="8:00 PM", vn_date="25/10")
    assert t4["exact_spoken_reply"] == "Đã hẹn 8:00 PM ngày 25/10 mở cửa chính.", f"Sai 7.4a: {t4}"
    p4 = eng.get_pools_summary()["timer_pool_items"]
    print(f"  [PASS] 2.4a Hẹn 8:00 PM kèm ngày 25/10 -> '{t4['exact_spoken_reply']}' | Bể 1: {p4}")
    await eng.factory_reset()

    t4b = await eng.schedule_timer_flexible("main_door", "open", vn_time_ampm="8:00", vn_date="25/10")
    assert t4b["exact_spoken_reply"] == "Đã hẹn 8:00 AM và 8:00 PM ngày 25/10 mở cửa chính.", f"Sai 7.4b: {t4b}"
    p4b = eng.get_pools_summary()["timer_pool_items"]
    print(f"  [PASS] 2.4b Hẹn 8:00 (cả AM & PM) kèm ngày 25/10 -> '{t4b['exact_spoken_reply']}' | Bể 1: {p4b}")
    await eng.factory_reset()

    # 8. Kiểm thử Hẹn giờ 1 lần (chạy xong 1 lần tự dừng) vs Lặp lại (hàng ngày / hàng tuần)
    t_once = await eng.schedule_timer_flexible("living_room_light", "turn_on", seconds=1.0)
    assert t_once["repeat"] == "once" and len(eng.active_timers) == 1
    await asyncio.sleep(1.25)
    assert len(eng.active_timers) == 0 and eng.devices["living_room_light"]["state"] == "ON", "Hẹn giờ 1 lần chưa tự dừng sau khi chạy!"
    print("  [PASS] 3.1 Hẹn giờ 1 lần (repeat='once'): Chạy xong 1 lần tự động xóa khỏi Bể 1 và dừng hẳn!")

    t_daily = await eng.schedule_timer_flexible("ac", "open", vn_time_ampm="8:00 PM hàng ngày")
    assert t_daily["repeat"] == "daily" and t_daily["exact_spoken_reply"] == "Đã hẹn 8:00 PM hàng ngày mở điều hòa.", f"Sai daily: {t_daily}"
    print(f"  [PASS] 3.2 Hẹn giờ lặp hàng ngày -> '{t_daily['exact_spoken_reply']}' (repeat={t_daily['repeat']})")
    await eng.factory_reset()

    # 9. Kiểm thử 4 Loại Reset Riêng Biệt (voice, timers, rules, all) có xác nhận 2 bước
    eng_reset = SmartHomeEngine(on_voice_reset=vm.reset_to_owner_only)
    # Tạo dữ liệu ở cả Giọng nói (strikes=3), Bể 1 (1 hẹn giờ), Bể 2 (1 đổi từ)
    await eng_reset.schedule_timer_flexible("fan", "turn_on", seconds=60)
    await eng_reset.set_word_mapping("máy lạnh", "ac (Điều hòa)", require_confirmation=False)
    assert vm.unauthorized_strikes == 3 and len(eng_reset.active_timers) == 1 and len(eng_reset.get_word_mappings()) == 1

    # Reset 1: Reset giọng nói ('voice') -> chỉ reset giọng nói về của Chủ nhà, giữ nguyên Bể 1 và Bể 2
    rq_v = await eng_reset.request_factory_reset(scope="voice")
    assert rq_v["exact_spoken_reply"] == "Bạn muốn reset giọng nói chỉ về của bạn đúng không?"
    cf_v = await eng_reset.confirm_pending_action(confirmed=True)
    assert cf_v["exact_spoken_reply"] == "Đã reset giọng nói chỉ về của bạn."
    assert vm.unauthorized_strikes == 0 and len(eng_reset.active_timers) == 1 and len(eng_reset.get_word_mappings()) == 1
    print(f"  [PASS] 4.1 Reset 1 (Giọng nói): Hỏi '{rq_v['exact_spoken_reply']}' -> '{cf_v['exact_spoken_reply']}' (Giữ nguyên Bể 1 & Bể 2)")

    # Reset 2: Reset đặt thời gian ('timers') -> chỉ xóa Bể 1, giữ nguyên Bể 2
    rq_t = await eng_reset.request_factory_reset(scope="timers")
    assert rq_t["exact_spoken_reply"] == "Bạn muốn reset đặt thời gian đúng không?"
    cf_t = await eng_reset.confirm_pending_action(confirmed=True)
    assert cf_t["exact_spoken_reply"] == "Đã reset đặt thời gian."
    assert len(eng_reset.active_timers) == 0 and len(eng_reset.get_word_mappings()) == 1
    print(f"  [PASS] 4.2 Reset 2 (Đặt thời gian): Hỏi '{rq_t['exact_spoken_reply']}' -> '{cf_t['exact_spoken_reply']}' (Bể 1=0, giữ nguyên Bể 2)")

    # Reset 3: Reset luật ('rules') -> chỉ xóa Bể 2
    await eng_reset.schedule_timer_flexible("fan", "turn_on", seconds=60)
    rq_r = await eng_reset.request_factory_reset(scope="rules")
    assert rq_r["exact_spoken_reply"] == "Bạn muốn reset toàn bộ luật đúng không?"
    cf_r = await eng_reset.confirm_pending_action(confirmed=True)
    assert cf_r["exact_spoken_reply"] == "Đã reset toàn bộ luật về ngôn ngữ gốc."
    assert len(eng_reset.active_timers) == 1 and len(eng_reset.get_word_mappings()) == 0
    print(f"  [PASS] 4.3 Reset 3 (Luật & Ngôn ngữ): Hỏi '{rq_r['exact_spoken_reply']}' -> '{cf_r['exact_spoken_reply']}' (Bể 2=0, giữ nguyên Bể 1)")

    # Reset 4: Reset tất cả ('all') -> xóa sạch cả Giọng nói, Bể 1, Bể 2 và thiết bị
    rq_a = await eng_reset.request_factory_reset(scope="all")
    assert rq_a["exact_spoken_reply"] == "Bạn muốn reset tất cả đúng không?"
    cf_a = await eng_reset.confirm_pending_action(confirmed=True)
    assert cf_a["exact_spoken_reply"] == "Đã reset tất cả về nguyên bản."
    assert len(eng_reset.active_timers) == 0 and len(eng_reset.get_word_mappings()) == 0
    print(f"  [PASS] 4.4 Reset 4 (Tất cả): Hỏi '{rq_a['exact_spoken_reply']}' -> '{cf_a['exact_spoken_reply']}'")

    # 10. Kiểm thử Truy vấn 2 Bể (hỏi lịch hẹn giờ đang có những gì, hỏi lệnh mở cửa là như nào)
    await eng_reset.schedule_timer_flexible("living_room_light", "turn_on", vn_time_ampm="8:00")
    await eng_reset.create_alias_rule("vừng ơi mở ra", "main_door", "open", require_confirmation=False)
    await eng_reset.set_if_else_rule("main_door", "OPEN", "ac", "open", require_confirmation=False)

    qp_timers = eng_reset.get_pools_summary(query_type="timers")
    assert qp_timers["exact_spoken_reply"] == "Đang có 2 lịch hẹn giờ: 8:00 AM bật đèn phòng khách, 8:00 PM bật đèn phòng khách."
    print(f"  [PASS] 5.1 Hỏi Bể Hẹn Giờ -> '{qp_timers['exact_spoken_reply']}'")

    qp_door = eng_reset.get_pools_summary(query_type="device_command", target_device_id="main_door")
    assert "vừng ơi mở ra" in qp_door["exact_spoken_reply"] and "mở điều hòa" in qp_door["exact_spoken_reply"]
    print(f"  [PASS] 5.2 Hỏi 'Lệnh mở cửa là như nào?' -> '{qp_door['exact_spoken_reply']}'")
    await eng_reset.factory_reset()

    # 11. Kiểm thử RAG với Google Embedding API (`gemini-embedding-001` - 3072 chiều)
    from simulator.knowledge_rag import SmartHomeKnowledgeRAG

    rag = SmartHomeKnowledgeRAG()
    q1 = rag.retrieve("Bạn là ai?")
    assert q1["ok"] and q1["vector_dim"] == 3072 and "Nguyễn Tuấn Anh" in q1["exact_spoken_reply"]
    print(f"  [PASS] 6.1 RAG ('Bạn là ai?' - dim={q1['vector_dim']}): '{q1['exact_spoken_reply']}'")

    q2 = rag.retrieve("Bạn được ai tạo ra?")
    assert q2["ok"] and "Nguyễn Tuấn Anh" in q2["exact_spoken_reply"]
    print(f"  [PASS] 6.2 RAG ('Bạn được ai tạo ra?'): '{q2['exact_spoken_reply']}'")

    q3 = rag.retrieve("Quy định phân quyền 3 tầng là như thế nào?")
    assert q3["ok"] and "3 tầng" in q3["exact_spoken_reply"].lower()
    print(f"  [PASS] 6.3 RAG ('Quy định phân quyền 3 tầng'): '{q3['exact_spoken_reply']}'")

    # 12. KIỂM THỬ TOÀN DIỆN KIẾN TRÚC PHÂN QUYỀN 3 TẦNG (ADMIN NGUYỄN TUẤN ANH / GIA ĐÌNH / KHÁCH)
    print("\n=== [2] KIỂM THỬ PHÂN QUYỀN 3 TẦNG, BỂ LỆNH RIÊNG, CHẶN VƯỚNG TẦNG 1 & RESET CÔ LẬP ===", flush=True)
    eng3 = SmartHomeEngine()
    await eng3.factory_reset()

    # 12.1 Tầng 1 (Nguyễn Tuấn Anh) đặt luật IF và hẹn giờ ưu tiên
    eng3.set_active_user("tuan_anh")
    assert eng3.current_tier == 1
    await eng3.create_alias_rule("vừng ơi mở ra", "main_door", "open", require_confirmation=False)
    await eng3.set_if_else_rule("main_door", "OPEN", "ac", "open", require_confirmation=False)
    t1_sched = await eng3.schedule_timer_flexible("ac", "open", vn_time_ampm="8:00 PM")
    assert t1_sched["ok"]
    print("  [PASS] 7.1 Tầng 1 (Nguyễn Tuấn Anh): Đã tạo khẩu lệnh 'vừng ơi mở ra', luật IF (cửa mở -> mở ĐH) và hẹn giờ 8:00 PM cho Điều hòa.")

    # 12.2 Chuyển sang Tầng 2 (Thành viên A): Có bể lệnh riêng độc lập
    eng3.set_active_user("thanh_vien_a")
    assert eng3.current_tier == 2 and eng3.current_user_id == "thanh_vien_a"
    assert len(eng3.get_merged_aliases()) == 0, "Bể lệnh của Thành viên A phải độc lập, không lẫn khẩu lệnh riêng của người khác!"
    r_alias_a = await eng3.create_alias_rule("mở cửa cho a", "main_door", "open", require_confirmation=False)
    assert r_alias_a["ok"]
    r_if_a = await eng3.set_if_else_rule("bedroom_light", "ON", "fan", "turn_on", require_confirmation=False)
    assert r_if_a["ok"]
    print("  [PASS] 7.2 Tầng 2 (Thành viên A): Có bể lệnh riêng ('mở cửa cho a', luật đèn ngủ -> bật quạt).")

    # 12.3 Tầng 2 thử đặt luật IF đè lên cặp thiết bị của Tầng 1 -> BỊ CHẶN!
    r_conflict = await eng3.set_if_else_rule("main_door", "OPEN", "ac", "turn_off", require_confirmation=False)
    assert not r_conflict["ok"] and "Tầng 1 Nguyễn Tuấn Anh" in r_conflict["error"]
    print(f"  [PASS] 7.3 Chặn Tầng 2 đặt luật trái với Tầng 1: '{r_conflict['error']}'")

    # 12.4 Tầng 2 thử đặt hẹn giờ vướng khung giờ của Tầng 1 (8:10 PM trên Điều hòa) hoặc hủy hẹn giờ Tầng 1 -> BỊ CHẶN!
    t_conflict = await eng3.schedule_timer_flexible("ac", "turn_off", vn_time_ampm="8:10 PM")
    assert not t_conflict["ok"] and "Tầng 1 Nguyễn Tuấn Anh" in t_conflict["error"]
    print(f"  [PASS] 7.4a Chặn Tầng 2 đặt hẹn giờ vướng khung giờ Tầng 1: '{t_conflict['error']}'")

    t_cancel_t1 = await eng3.update_or_cancel_timer("ac", operation="cancel")
    assert not t_cancel_t1["ok"] and "Tầng 1 Nguyễn Tuấn Anh" in t_cancel_t1["error"]
    print(f"  [PASS] 7.4b Chặn Tầng 2 hủy hẹn giờ của Tầng 1: '{t_cancel_t1['error']}'")

    # Nhưng Tầng 2 đặt hẹn giờ trên thiết bị khác (Quạt trần 30s) -> ĐƯỢC PHÉP!
    t_own_t2 = await eng3.schedule_timer_flexible("fan", "turn_on", seconds=30)
    assert t_own_t2["ok"]
    print(f"  [PASS] 7.4c Tầng 2 đặt hẹn giờ riêng trên thiết bị không vướng Tầng 1 -> '{t_own_t2['exact_spoken_reply']}'")

    # 12.5 Cấp quyền & Hủy quyền của Tầng 2:
    # - Hủy cùng cấp Tầng 2 (Thành viên B) -> BỊ CHẶN!
    rev_same = await eng3.revoke_user_permission("Thành viên B")
    assert not rev_same["ok"]
    print(f"  [PASS] 7.5a Chặn Tầng 2 hủy quyền cùng cấp (Thành viên B): '{rev_same['error']}'")

    # - Hủy Khách C (dù ở Tầng 3 nhưng do Tầng 1 Nguyễn Tuấn Anh cấp quyền) -> BỊ CHẶN!
    rev_t1_guest = await eng3.revoke_user_permission("Khách C")
    assert not rev_t1_guest["ok"] and "Tầng 1 Nguyễn Tuấn Anh cấp quyền" in rev_t1_guest["error"]
    print(f"  [PASS] 7.5b Chặn Tầng 2 hủy quyền Khách C do Tầng 1 cấp: '{rev_t1_guest['error']}'")

    # - Cấp quyền Tầng 3 cho Khách E và Hủy quyền Khách D (do Tầng 2 cấp) -> ĐƯỢC PHÉP!
    gr_guest = await eng3.grant_user_permission("Khách E", target_tier=3)
    assert gr_guest["ok"]
    rev_t2_guest = await eng3.revoke_user_permission("Khách D")
    assert rev_t2_guest["ok"]
    print(f"  [PASS] 7.5c Tầng 2 cấp/hủy quyền Khách Tầng 3 do Tầng 2 quản lý: '{gr_guest['exact_spoken_reply']}' | '{rev_t2_guest['exact_spoken_reply']}'")

    # 12.6 Reset cô lập của Tầng 2: Chỉ xóa bể lệnh & hẹn giờ của Thành viên A, giữ nguyên 100% của Tầng 1 Nguyễn Tuấn Anh!
    rq_t2 = await eng3.request_factory_reset(scope="all")
    assert rq_t2["ok"] and "riêng của bạn" in rq_t2["exact_spoken_reply"]
    cf_t2 = await eng3.confirm_pending_action(confirmed=True)
    assert cf_t2["ok"]
    # Kiểm tra của Thành viên A đã sạch (0 luật, 0 hẹn giờ của A), nhưng của Tầng 1 vẫn còn nguyên!
    assert len(eng3.get_merged_aliases("thanh_vien_a")) == 0
    assert len(eng3.get_merged_aliases("tuan_anh")) == 1
    assert len(eng3.active_timers) == 1  # Lịch 8:00 PM của Tầng 1 vẫn còn nguyên!
    print(f"  [PASS] 7.6 Tầng 2 Reset cô lập: '{cf_t2['exact_spoken_reply']}' (Bể Tầng 1 & lịch hẹn 8:00 PM của Tầng 1 còn nguyên 100%!)")

    # 12.7 Tầng 3 (Khách C): Chỉ được đóng mở cố định, cấm custom lệnh/IF-ELSE/hẹn giờ/cấp quyền
    eng3.set_active_user("khach_c")
    assert eng3.current_tier == 3
    act_guest = await eng3.execute_device_action("main_door", "open")
    assert act_guest["ok"]
    blk_custom = await eng3.create_alias_rule("mở cửa khách", "main_door", "open")
    assert not blk_custom["ok"]
    blk_if = await eng3.set_if_else_rule("main_door", "OPEN", "fan", "turn_on")
    assert not blk_if["ok"]
    blk_timer = await eng3.schedule_timer_flexible("fan", "turn_on", seconds=10)
    assert not blk_timer["ok"]
    blk_grant = await eng3.grant_user_permission("Khách X", target_tier=3)
    assert not blk_grant["ok"]
    print("  [PASS] 7.7 Tầng 3 (Khách C): Mở cửa cố định OK; Chặn 100% custom lệnh, IF-ELSE, hẹn giờ và cấp/hủy quyền!")

    eng3.set_active_user("tuan_anh")
    await eng3.factory_reset()

    # 13. KIỂM THỬ 3 NÂNG CẤP MỚI: HỎI GÌ ĐÁP NẤY NGẮN GỌN + THU ÂM CẤP QUYỀN (3-2-1 NHÁY ĐÈN) + PHÂN QUYỀN KHI HỎI
    print("\n=== [3] KIỂM THỬ HỎI NGẮN GỌN, THU ÂM CẤP QUYỀN (3-2-1 NHÁY ĐÈN -> PHÂN TÍCH -> HỎI TÊN) & PHÂN QUYỀN HỎI ===", flush=True)

    # 13.1 Hỏi "Cái còi báo động ở đây nghĩa là gì đấy?" -> Trả lời đúng 1 câu, không liệt kê thiết bị khác
    q_siren = rag.retrieve("Cái còi báo động ở đây nghĩa là gì đấy?", current_tier=1, query_permission_mode="tier_restricted")
    assert q_siren["ok"] and q_siren["matched_id"] == "alarm_siren_meaning", f"Sai kết quả RAG còi báo động: {q_siren}"
    assert "GPIO" not in q_siren["exact_spoken_reply"] and "Quạt trần" not in q_siren["exact_spoken_reply"]
    print(f"  [PASS] 8.1 Hỏi 'Cái còi báo động ở đây nghĩa là gì đấy?' -> '{q_siren['exact_spoken_reply']}'")

    # 13.2 Quy trình Thu Âm Cấp Quyền Cấp 2 (Đếm 3-2-1 -> Nháy đèn -> Thu 5s -> Phân tích -> Hỏi tên -> Lưu)
    eng3.set_active_user("tuan_anh")
    st_enroll = await eng3.start_voice_enrollment(target_tier=2, duration_sec=5)
    assert st_enroll["ok"] and st_enroll["status"] == "VOICE_ENROLLMENT_COUNTDOWN"
    assert "3, 2, 1" in st_enroll["exact_spoken_reply"] and "Khi đèn nháy một phát" in st_enroll["exact_spoken_reply"]
    print(f"  [PASS] 8.2a Bước 1 (Bắt đầu thu âm cấp quyền Cấp 2): '{st_enroll['exact_spoken_reply']}'")

    await eng3.blink_signal_light("living_room_light")
    assert eng3.devices["living_room_light"]["state"] == "OFF"
    print("  [PASS] 8.2b Bước 2 (Nháy đèn phòng khách 1 phát làm tín hiệu bắt đầu thu âm): OK")

    v_feat = vm.analyze_voice_pcm16k(pcm_v1)
    st_analyzed = await eng3.stage_voice_enrollment_analysis(
        f0_hz=v_feat["f0_hz"],
        centroid_hz=v_feat["centroid_hz"],
        embedding=v_feat["embedding"],
    )
    assert st_analyzed["ok"] and st_analyzed["status"] == "VOICE_ENROLLMENT_ANALYZED_AWAITING_NAME"
    assert "Đã thu âm đủ và đã phân tích xong" in st_analyzed["exact_spoken_reply"]
    assert "Người ấy tên là gì?" in st_analyzed["exact_spoken_reply"]
    print(f"  [PASS] 8.2c Bước 3 (Thu âm đủ & Phân tích xong, hỏi tên): '{st_analyzed['exact_spoken_reply']}'")

    st_final = await eng3.finalize_voice_enrollment("Minh")
    assert st_final["ok"] and st_final["status"] == "VOICE_ENROLLMENT_COMPLETED"
    assert "minh" in eng3.users and eng3.users["minh"]["tier"] == 2
    vm.register_enrolled_user_profile(
        user_id=st_final["user_id"],
        user_name=st_final["target_name"],
        tier=st_final["target_tier"],
        role=eng3.users[st_final["user_id"]]["role"],
        f0_hz=st_final["voice_profile"]["f0_hz"],
        centroid_hz=st_final["voice_profile"]["centroid_hz"],
        embedding=st_final["voice_profile"]["embedding"],
    )
    print(f"  [PASS] 8.2d Bước 4 (Trả lời tên 'Minh' -> Lưu giọng nói & Cấp quyền Cấp 2): '{st_final['exact_spoken_reply']}'")

    # 13.3 Phân quyền khi hỏi (query_permission_mode: 'tier_restricted' vs 'open_all')
    eng3.set_active_user("tuan_anh")
    await eng3.schedule_timer_flexible("ac", "open", vn_time_ampm="8:00 PM")
    eng3.set_active_user("minh")
    await eng3.schedule_timer_flexible("fan", "turn_on", seconds=45)

    # Mặc định là 'tier_restricted':
    # - Cấp 2 (Minh) hỏi bể hẹn giờ -> chỉ thấy lịch của Minh (45 giây nữa bật quạt trần), không lộ lịch 8:00 PM của Cấp 1!
    q_minh_timers = eng3.get_pools_summary(query_type="timers")
    assert "quạt trần" in q_minh_timers["exact_spoken_reply"].lower() and "8:00 pm" not in q_minh_timers["exact_spoken_reply"].lower()
    print(f"  [PASS] 8.3a Khi 'tier_restricted', Cấp 2 (Minh) hỏi lịch hẹn giờ chỉ nghe lịch của mình: '{q_minh_timers['exact_spoken_reply']}'")

    # - Cấp 3 (Khách C) hỏi bể hẹn giờ -> bị chặn vì Cấp 3 chỉ được hỏi đóng/mở thiết bị cơ bản
    eng3.set_active_user("khach_c")
    q_guest_timers = eng3.get_pools_summary(query_type="timers")
    assert not q_guest_timers["ok"] and "Cấp 3 (Khách)" in q_guest_timers["exact_spoken_reply"]
    print(f"  [PASS] 8.3b Khi 'tier_restricted', Cấp 3 (Khách C) hỏi lịch hẹn giờ bị chặn: '{q_guest_timers['exact_spoken_reply']}'")

    # - Cấp 2 hoặc Cấp 3 thử tự mở quyền hỏi cho tất cả -> BỊ CHẶN!
    blk_policy_guest = await eng3.set_query_permission_policy("open_all")
    assert not blk_policy_guest["ok"]
    eng3.set_active_user("minh")
    blk_policy_t2 = await eng3.set_query_permission_policy("open_all")
    assert not blk_policy_t2["ok"]
    print(f"  [PASS] 8.3c Chặn Cấp 2 & Cấp 3 tự ý thay đổi quy tắc phân quyền hỏi: '{blk_policy_t2['exact_spoken_reply']}'")

    # - Cấp 1 (Nguyễn Tuấn Anh) nói: "Chỉnh tất cả ai cũng có thể hỏi" -> Mở 'open_all' thành công!
    eng3.set_active_user("tuan_anh")
    ok_open_all = await eng3.set_query_permission_policy("open_all")
    assert ok_open_all["ok"] and eng3.query_permission_mode == "open_all"
    print(f"  [PASS] 8.3d Cấp 1 (Nguyễn Tuấn Anh) mở quyền hỏi cho tất cả: '{ok_open_all['exact_spoken_reply']}'")

    # - Bây giờ Cấp 3 (Khách C) hỏi bể hẹn giờ -> Được trả lời toàn bộ cả 2 lịch hẹn giờ!
    eng3.set_active_user("khach_c")
    q_guest_open = eng3.get_pools_summary(query_type="timers")
    assert q_guest_open["ok"] and "2 lịch hẹn giờ" in q_guest_open["exact_spoken_reply"]
    print(f"  [PASS] 8.3e Sau khi Cấp 1 mở quyền hỏi, Cấp 3 hỏi lịch hẹn giờ được trả lời đủ: '{q_guest_open['exact_spoken_reply']}'")

    # - Cấp 1 khóa lại về 'tier_restricted'
    eng3.set_active_user("tuan_anh")
    ok_restrict = await eng3.set_query_permission_policy("tier_restricted")
    assert ok_restrict["ok"] and eng3.query_permission_mode == "tier_restricted"
    await eng3.factory_reset()
    print(f"  [PASS] 8.3f Cấp 1 khóa lại quyền hỏi theo từng tầng: '{ok_restrict['exact_spoken_reply']}'")

    # 14. KIỂM THỬ ADMIN CẤP 1 (NGUYỄN TUẤN ANH) SỬA MỌI LUẬT HỆ THỐNG, PHÂN QUYỀN & RAG TRỰC TIẾP BẰNG GIỌNG NÓI
    print("\n=== [4] KIỂM THỬ ADMIN CẤP 1 SỬA MỌI LUẬT HỆ THỐNG, QUYỀN CẤP 2/3, QUYỀN THIẾT BỊ & RAG BẰNG GIỌNG NÓI ===", flush=True)
    eng3.set_active_user("tuan_anh")
    await eng3.factory_reset()

    # 14.1 Cấp 1 ra lệnh giọng nói: "Cho phép cấp 3 được hẹn giờ" -> Cấp 3 đặt hẹn giờ được ngay!
    p_t3_timer = await eng3.admin_update_system_policy("tier3_can_schedule_timer", "true")
    assert p_t3_timer["ok"]
    eng3.set_active_user("khach_c")
    t_guest_ok = await eng3.schedule_timer_flexible("fan", "turn_on", seconds=20)
    assert t_guest_ok["ok"], f"Cấp 1 đã mở quyền hẹn giờ cho Cấp 3 nhưng Cấp 3 vẫn bị chặn: {t_guest_ok}"
    print(f"  [PASS] 9.1 Cấp 1 ra lệnh mở quyền hẹn giờ cho Cấp 3: '{p_t3_timer['exact_spoken_reply']}' -> Khách C hẹn giờ OK!")

    # 14.2 Cấp 1 ra lệnh giọng nói: "Cấm cấp 3 mở cửa chính (chỉ Cấp 1 & 2 mới được mở)"
    eng3.set_active_user("tuan_anh")
    p_door_tier = await eng3.admin_update_system_policy("device_min_tier", "2", target_device_id="main_door")
    assert p_door_tier["ok"]
    eng3.set_active_user("khach_c")
    blk_door_t3 = await eng3.execute_device_action("main_door", "open")
    assert not blk_door_t3["ok"] and "Cấp 2 trở lên" in blk_door_t3["exact_spoken_reply"]
    eng3.set_active_user("thanh_vien_a")
    ok_door_t2 = await eng3.execute_device_action("main_door", "open")
    assert ok_door_t2["ok"]
    print(f"  [PASS] 9.2 Cấp 1 đổi quyền thiết bị Cửa chính (>=Cấp 2): '{p_door_tier['exact_spoken_reply']}' -> Chặn Cấp 3, Cho phép Cấp 2!")

    # 14.3 Cấp 1 ra lệnh giọng nói: "Khi xét luật mới không cần hỏi xác nhận lại nữa, lưu thẳng luôn"
    eng3.set_active_user("tuan_anh")
    p_no_conf = await eng3.admin_update_system_policy("require_rule_confirmation", "false")
    assert p_no_conf["ok"]
    direct_save = await eng3.set_if_else_rule("living_room_light", "ON", "fan", "turn_on", require_confirmation=True)
    assert direct_save["ok"] and direct_save.get("status") != "AWAITING_RULE_CONFIRMATION"
    assert len(eng3.get_if_else_rules()) == 1
    print(f"  [PASS] 9.3 Cấp 1 tắt bước hỏi xác nhận luật: '{p_no_conf['exact_spoken_reply']}' -> Lưu thẳng vào Bể 2 ngay lập tức!")

    # 14.4 Cấp 1 thêm quy tắc tự do vào System Prompt & dạy thêm tri thức RAG bằng giọng nói
    p_custom_dir = await eng3.admin_update_system_policy(
        "custom_directive_add",
        "Sau 23h đêm không ai ở Cấp 3 được bật loa hay còi báo động",
    )
    assert p_custom_dir["ok"] and len(eng3.system_policies["custom_system_directives"]) == 1
    rag_up = rag.upsert_knowledge_item(
        topic="Mật khẩu wifi khách",
        content="Mật khẩu wifi khách của nhà Nguyễn Tuấn Anh là 12345678.",
        keywords="mật khẩu, wifi, khách, mạng",
        min_tier=3,
        current_tier=eng3.current_tier,
    )
    assert rag_up["ok"]
    q_wifi = rag.retrieve("Mật khẩu wifi khách là gì?", current_tier=3)
    assert q_wifi["ok"] and "12345678" in q_wifi["exact_spoken_reply"]
    print(f"  [PASS] 9.4 Cấp 1 thêm luật tự do & dạy RAG bằng giọng nói -> Hỏi wifi đáp: '{q_wifi['exact_spoken_reply']}'")

    # 14.5 Cấp 2 và Cấp 3 thử gọi lệnh sửa luật hệ thống -> BỊ CHẶN TUYỆT ĐỐI!
    eng3.set_active_user("thanh_vien_a")
    blk_admin_t2 = await eng3.admin_update_system_policy("tier2_can_revoke_same_tier", "true")
    assert not blk_admin_t2["ok"]
    blk_rag_t2 = rag.upsert_knowledge_item("Test", "Test", current_tier=eng3.current_tier)
    assert not blk_rag_t2["ok"]
    print(f"  [PASS] 9.5 Chặn Cấp 2/Cấp 3 tự ý sửa luật hệ thống bằng giọng nói: '{blk_admin_t2['exact_spoken_reply']}'")

    eng3.set_active_user("tuan_anh")
    rag.reset_custom_knowledge()
    await eng3.factory_reset()

    # 15. KIỂM THỬ KIẾN TRÚC SYSTEM DESIGN PRIMER: MQTT PUB/SUB, BACKPRESSURE, CAP FAILOVER FLASH, DHT11 & IR 38KHZ
    print("\n=== [5] KIỂM THỬ SYSTEM DESIGN PRIMER: MQTT PUB/SUB, CAP EDGE SYNC, CẢM BIẾN DHT11 & HỌC LỆNH IR 38KHZ ===", flush=True)
    await eng3.execute_device_action("ac", "open")
    mqtt_sum = eng3.mqtt_bridge.get_summary()
    topics_seen = [p["topic"] for p in mqtt_sum["recent_mqtt_packets"]]
    assert "smarthome/cmd/actuate" in topics_seen and "smarthome/ir/blast" in topics_seen and "smarthome/state/report" in topics_seen
    print(f"  [PASS] 10.1 MQTT Pub/Sub & IR Blast 38kHz khi bật Điều hòa -> Topics: {topics_seen[-3:]}")

    # 15.2 CAP Theorem (AP Edge Failover): Đồng bộ 2 Bể xuống bộ nhớ Flash LittleFS của ESP8266
    await eng3.schedule_timer_flexible("living_room_light", "turn_on", seconds=30)
    await eng3.set_if_else_rule("main_door", "OPEN", "living_room_light", "turn_on", require_confirmation=False)
    sync_pkt = await eng3.sync_edge_flash()
    assert sync_pkt["topic"] == "smarthome/sync/pools" and sync_pkt["retain"] is True
    assert sync_pkt["payload"]["timers_count"] == 1 and sync_pkt["payload"]["if_else_rules_count"] == 1
    print("  [PASS] 10.2 CAP Theorem (AP Failover): Đồng bộ Bể 1 & Bể 2 xuống Flash LittleFS ESP8266 (Retain=True) OK!")

    # 15.3 Cảm biến DHT11 (Chân D6) + Tự động kích hoạt Điều hòa khi vượt ngưỡng nhiệt độ
    await eng3.execute_device_action("ac", "close")
    await eng3.admin_update_system_policy("custom_directive_add", "Nếu nhiệt độ trên 30 độ thì mở điều hòa")
    tele_res = await eng3.update_sensor_telemetry(temp_c=31.5, humidity_pct=72.0)
    assert tele_res["ok"] and eng3.devices["ac"]["state"] == "ON"
    print(f"  [PASS] 10.3 Telemetry DHT11 (31.5°C > 30°C) tự động kích hoạt mở Điều hòa -> '{tele_res['exact_spoken_reply']}'")

    # 15.4 Học lệnh Chiếm quyền Remote Hồng ngoại 38kHz (VS1838B Chân D5 -> Write-Through Cache)
    ir_res = await eng3.learn_ir_remote_command("Quạt Mitsubishi", "open", protocol="MITSUBISHI_38KHZ", hex_code="0xE240A1")
    assert ir_res["ok"] and ir_res["hex_code"] == "0xE240A1"
    print(f"  [PASS] 10.4 Học lệnh Remote IR 38kHz (Write-Through Cache): '{ir_res['exact_spoken_reply']}'")

    await eng3.factory_reset()
    print("\n🎉 TẤT CẢ CÁC BÀI KIỂM THỬ ĐỀU ĐẠT 100% (EXIT CODE 0)!", flush=True)


if __name__ == "__main__":
    asyncio.run(test_unit_all_new_features())
