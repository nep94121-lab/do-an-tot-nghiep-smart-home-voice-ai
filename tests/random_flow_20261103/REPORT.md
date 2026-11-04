# Báo cáo kiểm thử luồng ngẫu nhiên / đối kháng

- Thời gian (Asia/Saigon): 2026-11-03 19:54:14 (UTC+7)
- Seed: `20261103`
- Dự án: `C:\Users\LENOVO\Desktop\đồ án tốt nghiệp`
- Server: `http://127.0.0.1:8088`
- Backup: `C:\Users\LENOVO\Desktop\datn-backup-flowtest-20261103`
- Tổng: **48** tình huống — PASS=32 FAIL=2 QUESTIONABLE=14

## Pytest tham chiếu
- returncode: `0`
```
........................................................................ [ 55%]
..........................................................               [100%]
============================== warnings summary ===============================
..\..\miniconda3\Lib\site-packages\fastapi\testclient.py:1
  C:\Users\LENOVO\miniconda3\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

..\..\miniconda3\Lib\site-packages\starlette\testclient.py:53
  C:\Users\LENOVO\miniconda3\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

..\..\miniconda3\Lib\site-packages\google\genai\types.py:42
  C:\Users\LENOVO\miniconda3\Lib\site-packages\google\genai\types.py:42: DeprecationWarning: '_UnionGenericAlias' is deprecated and slated for removal in Python 3.17
    VersionedUnionType = Union[builtin_types.UnionType, _UnionGenericAlias]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
130 passed, 3 warnings in 68.99s (0:01:08)
```

## Khôi phục dữ liệu
- verify_ok: **True**
- restored_files: 13

> Lưu ý: tiến trình FastAPI đang chạy trên :8088 có thể vẫn giữ state trong RAM sau khi restore file; cần restart server nếu muốn memory khớp disk.

## Các FAIL
### S02 — Khách giả mạo tier=1 qua /api/device để mở cửa
- Quan sát: Cửa mở được (before=CLOSED, after=OPEN); resp={'ok': True, 'results': [{'ok': True, 'device_id': 'main_door', 'device_name': 'Cửa chính', 'state': 'OPEN', 'already_in_state': False}], 'exact_spoken_reply': 'Cửa chính đã mở.', 'instruction_for_ai'
- Kỳ vọng: Phải từ chối: API không được tin tier do client gửi; cửa chỉ mở khi session Cấp 1 đã xác thực
- Nghi ngờ: `simulator/server.py:api_control_device (bypass_rbac=(tier==1) từ payload)`

### S03 — Gọi /api/device mở cửa với payload tier=3 (engine vẫn C1)
- Quan sát: Cửa OPEN dù payload khai tier=3; engine.current_tier không đổi theo payload. resp={'ok': True, 'results': [{'ok': True, 'device_id': 'main_door', 'device_name': 'Cửa chính', 'state': 'OPEN', 'already_in_state': False}], 'exact_spoken_reply': 'Cửa chính đã mở.', 
- Kỳ vọng: Phải gắn session/user đã xác thực; tier trong payload không được bỏ qua cũng không được dùng để bypass khi engine đang C1 mặc định
- Nghi ngờ: `simulator/server.py:api_control_device + rule_engine.current_tier`

## Các QUESTIONABLE
### S04 — Bật đèn phòng khách qua /api/device (khách được phép theo spec)
- Quan sát: Đèn ON (đúng quyền C3 theo catalog) nhưng API không chứng minh session C3 — đang chạy dưới engine C1. resp={'ok': True, 'results': [{'ok': True, 'device_id': 'living_room_light', 'device_name': 'Đèn phòng khách', 'state': 'ON',
- Kỳ vọng/ghi chú: Cho phép C3 bật đèn khi đã xác thực C3; cần session thật
- Liên quan: `simulator/server.py:api_control_device`

### S11 — Xung đột: tắt bơm thủ công khi đất khô — luật tự tưới bật lại
- Quan sát: pump=ON (luật sensor thắng lệnh tay ngay khi cập nhật lại soil)
- Kỳ vọng/ghi chú: Cần chính sách rõ: khóa tạm / cooldown / ưu tiên lệnh tay
- Liên quan: `rule_engine.update_soil_moisture_telemetry vs execute_device_action`

### S12 — DHT11 giá trị vô lý (999°C, -5% RH)
- Quan sát: HTTP 200 accepted=True resp={'ok': True, 'telemetry': {'temp_c': 999.0, 'humidity_pct': -5.0, 'heat_index_c': 998.8, 'sensor_pin': 'D6 (GPIO 12)', 'updated_at': 1793710345.0586228}, 'mqtt_packet': {'topic': 'smarthome/telemetry/
- Kỳ vọng/ghi chú: Nên validate/clamp (vd temp [-40,85], RH [0,100]) thay vì nuốt số vô lý
- Liên quan: `server.api_update_dht11 / rule_engine.update_sensor_telemetry`

### S13 — soil_moisture_pct = 'NaN' / malformed
- Quan sát: HTTP 200 resp={'ok': True, 'telemetry': {'soil_moisture_pct': 100.0, 'adc_raw': 324, 'status_label': 'Ẩm ướt', 'sensor_pin': 'A0 (ADC0 - Cảm biến đất YL-69 + LM393)', 'auto_p
- Kỳ vọng/ghi chú: Từ chối hoặc báo lỗi rõ, không đưa NaN vào luật bơm
- Liên quan: `server.api_update_soil_moisture`

### S16a — text_command: 'tắt hết đi'
- Quan sát: HTTP 200 reply=Đã nhận lệnh: tắt hết đi; door=CLOSED light=OFF
- Kỳ vọng/ghi chú: Tắt all_lights/all_devices hoặc hỏi lại làm rõ
- Liên quan: `server.api_text_command (NLU rất mỏng, nhiều lệnh chỉ echo)`

### S16b — text_command: 'mở cửa rồi bật đèn'
- Quan sát: HTTP 200 reply=Đã nhận lệnh: mở cửa rồi bật đèn; door=CLOSED light=OFF
- Kỳ vọng/ghi chú: Thực thi compound: mở cửa + bật đèn (nếu đã auth)
- Liên quan: `server.api_text_command (NLU rất mỏng, nhiều lệnh chỉ echo)`

### S16c — text_command: 'điều hòa 99 độ'
- Quan sát: HTTP 200 reply=Đã nhận lệnh: điều hòa 99 độ; door=CLOSED light=OFF
- Kỳ vọng/ghi chú: Chặn/clamp setpoint ngoài biên hoặc hỏi lại
- Liên quan: `server.api_text_command (NLU rất mỏng, nhiều lệnh chỉ echo)`

### S16d — text_command: 'xyzabc lệnh không tồn tại'
- Quan sát: HTTP 200 reply=Đã nhận lệnh: xyzabc lệnh không tồn tại; door=CLOSED light=OFF
- Kỳ vọng/ghi chú: Báo không hiểu / không thực thi ngầm
- Liên quan: `server.api_text_command (NLU rất mỏng, nhiều lệnh chỉ echo)`

### S16e — text_command: ''
- Quan sát: HTTP 200 reply=Đã nhận lệnh: ; door=CLOSED light=OFF
- Kỳ vọng/ghi chú: Từ chối lệnh rỗng
- Liên quan: `server.api_text_command (NLU rất mỏng, nhiều lệnh chỉ echo)`

### S17 — text_command 'mở cửa chính' không mở cửa (chỉ echo)
- Quan sát: Cửa vẫn CLOSED; reply=Đã nhận lệnh: mở cửa chính — endpoint text không map lệnh cửa
- Kỳ vọng/ghi chú: Hoặc thực thi có auth, hoặc từ chối rõ; không nên im lặng nuốt lệnh an ninh
- Liên quan: `server.api_text_command`

### S22 — Cấp 3 thêm family email (RBAC)
- Quan sát: HTTP 401 resp={'ok': False, 'status_code': 401, 'error': 'Thiếu thông tin người thêm (actor_id)'} — cần xác nhận API lấy actor từ đâu
- Kỳ vọng/ghi chú: C3 bị chặn 100% khi add_family_email
- Liên quan: `server.api + auth_3layer.add_family_email`

### S24 — Khách C3 đặt hẹn giờ qua /api/mobile/schedule
- Quan sát: HTTP 200 {'ok': True, 'timer_id': 'timer_1', 'timer_ids': ['timer_1'], 'both_ampm': False, 'has_date': False, 'repeat': 'once', 'timer_pool_count': 1, 'exact_spoken_repl — API nhận tier từ client, engine có thể vẫn C1
- Kỳ vọng/ghi chú: C3 bị chặn đặt hẹn giờ (tier3_can_schedule_timer=False) khi session thật là C3
- Liên quan: `server.api_mobile_schedule / rule_engine.schedule_timer_flexible`

### S34 — DSP mẫu thành viên C2
- Quan sát: auth=True tier=2 speaker=user_voice_thanh_vien_a reason=None
- Kỳ vọng/ghi chú: Nếu đã enroll C2: authorized tier=2; nếu chưa: xử lý như người lạ/strike — phụ thuộc data hiện tại
- Liên quan: `voice_auth.verify_pcm16k_and_apply_strikes / voiceprints.json`

### S35 — DSP mẫu khách C3
- Quan sát: auth=True tier=3 speaker=user_voice_khach_c expires=None
- Kỳ vọng/ghi chú: Nếu profile C3 còn hạn: tier=3 auth; hết hạn: GUEST_EXPIRED
- Liên quan: `voice_auth.verify + expires_at`

## Toàn bộ kết quả
- **PASS** `S01` GET /api/state trả về snapshot hợp lệ: HTTP 200; keys=['vn_time_now', 'server_connected', 'offline_locked_devices', 'current_user_id', 'current_user_name', 'current_tier', 'query_permission_mode', 'system_policies']
- **FAIL** `S02` Khách giả mạo tier=1 qua /api/device để mở cửa: Cửa mở được (before=CLOSED, after=OPEN); resp={'ok': True, 'results': [{'ok': True, 'device_id': 'main_door', 'device_name': 'Cửa chính', 'state': 'OPEN', 'already_in_state': False}], 'exact_spoken_reply': 'Cửa chính đã mở.', 'instruction_for_ai'
- **FAIL** `S03` Gọi /api/device mở cửa với payload tier=3 (engine vẫn C1): Cửa OPEN dù payload khai tier=3; engine.current_tier không đổi theo payload. resp={'ok': True, 'results': [{'ok': True, 'device_id': 'main_door', 'device_name': 'Cửa chính', 'state': 'OPEN', 'already_in_state': False}], 'exact_spoken_reply': 'Cửa chính đã mở.', 
- **QUESTIONABLE** `S04` Bật đèn phòng khách qua /api/device (khách được phép theo spec): Đèn ON (đúng quyền C3 theo catalog) nhưng API không chứng minh session C3 — đang chạy dưới engine C1. resp={'ok': True, 'results': [{'ok': True, 'device_id': 'living_room_light', 'device_name': 'Đèn phòng khách', 'state': 'ON',
- **PASS** `S05` QR single-use: handshake lần 1 OK, reuse bị chặn: 1st ok session=guest_sess_1793710338_ddaf99; 2nd blocked={'ok': False, 'error': 'Mã QR này đã được sử dụng một lần (Single-Use Token). Vui lòng quét mã mới trên màn hình!', 'sta
- **PASS** `S06` Handshake với window cũ (mô phỏng QR >10s): blocked=True HTTP 401 resp={'ok': False, 'error': 'Mã QR đã hết hạn 10 giây, vui lòng quét lại mã mới trên màn hình!', 'status_code': 401}
- **PASS** `S07` Cấp 3 không được sinh QR mời khách: HTTP 403 resp={'ok': False, 'error': 'Chỉ Cấp 1 (Chủ nhà) hoặc Cấp 2 (Thành viên gia đình) mới có quyền tạo mã QR động cho khách!', 'status_code': 403}
- **PASS** `S08` duration_type không hợp lệ: HTTP 400 {'ok': False, 'error': "Thời hạn '99z' không hợp lệ (chỉ hỗ trợ: 1d, 2d, 1w, 1m, 1y).", 'status_code': 400}
- **PASS** `S09` Độ ẩm đất 25% tự bật máy bơm: pump=ON; resp={'ok': True, 'telemetry': {'soil_moisture_pct': 25.0, 'adc_raw': 849, 'status_label': 'Khô - Cần tưới', 'sensor_pin': 'A0 (ADC0 - Cảm biến đ
- **PASS** `S10` Độ ẩm đất 85% tự tắt máy bơm: pump=OFF
- **QUESTIONABLE** `S11` Xung đột: tắt bơm thủ công khi đất khô — luật tự tưới bật lại: pump=ON (luật sensor thắng lệnh tay ngay khi cập nhật lại soil)
- **QUESTIONABLE** `S12` DHT11 giá trị vô lý (999°C, -5% RH): HTTP 200 accepted=True resp={'ok': True, 'telemetry': {'temp_c': 999.0, 'humidity_pct': -5.0, 'heat_index_c': 998.8, 'sensor_pin': 'D6 (GPIO 12)', 'updated_at': 1793710345.0586228}, 'mqtt_packet': {'topic': 'smarthome/telemetry/
- **QUESTIONABLE** `S13` soil_moisture_pct = 'NaN' / malformed: HTTP 200 resp={'ok': True, 'telemetry': {'soil_moisture_pct': 100.0, 'adc_raw': 324, 'status_label': 'Ẩm ướt', 'sensor_pin': 'A0 (ADC0 - Cảm biến đất YL-69 + LM393)', 'auto_p
- **PASS** `S14` Offline: khóa cứng cửa chính kể cả Cấp 1: after=CLOSED resp={'ok': False, 'results': [{'ok': False, 'device_id': 'main_door', 'error': '🔒 [KHÓA AN NINH OFFLINE]: Mạch không kết nối Server xác thực giọng nói -> Cửa chính 
- **PASS** `S15` Offline: vẫn bật được đèn sinh hoạt: light=ON resp={'ok': True, 'results': [{'ok': True, 'device_id': 'living_room_light', 'device_name': 'Đèn phòng khách', 'state': 'ON',
- **QUESTIONABLE** `S16a` text_command: 'tắt hết đi': HTTP 200 reply=Đã nhận lệnh: tắt hết đi; door=CLOSED light=OFF
- **QUESTIONABLE** `S16b` text_command: 'mở cửa rồi bật đèn': HTTP 200 reply=Đã nhận lệnh: mở cửa rồi bật đèn; door=CLOSED light=OFF
- **QUESTIONABLE** `S16c` text_command: 'điều hòa 99 độ': HTTP 200 reply=Đã nhận lệnh: điều hòa 99 độ; door=CLOSED light=OFF
- **QUESTIONABLE** `S16d` text_command: 'xyzabc lệnh không tồn tại': HTTP 200 reply=Đã nhận lệnh: xyzabc lệnh không tồn tại; door=CLOSED light=OFF
- **QUESTIONABLE** `S16e` text_command: '': HTTP 200 reply=Đã nhận lệnh: ; door=CLOSED light=OFF
- **QUESTIONABLE** `S17` text_command 'mở cửa chính' không mở cửa (chỉ echo): Cửa vẫn CLOSED; reply=Đã nhận lệnh: mở cửa chính — endpoint text không map lệnh cửa
- **PASS** `S18` Race/rapid 12 lệnh bật-tắt quạt liên tiếp: final=OFF expected=OFF elapsed=6.32s results_ok=True
- **PASS** `S19a` Malformed /api/device: HTTP 200 {'ok': False, 'results': [{'ok': False, 'device_id': 'no_such_device', 'error': "Thiết bị 'no_such_device' không tồn tại."}], 'exact_spoken_
- **PASS** `S19b` Malformed /api/device: HTTP 200 {'ok': True, 'results': [{'ok': True, 'device_id': 'main_door', 'device_name': 'Cửa chính', 'state': 'CLOSED', 'already_in_state': True}], '
- **PASS** `S19c` Malformed /api/auth3/guest/handshake: HTTP 400 {'ok': False, 'error': 'Thiếu mã token QR động!', 'status_code': 400}
- **PASS** `S19d` Malformed /api/auth3/guest/enroll_voice: HTTP 400 {'ok': False, 'verified': False, 'status': 'CHUA_DAT', 'message': 'Giọng thu âm chưa đạt chuẩn (Chưa được)', 'reason': 'Dữ liệu âm thanh rỗn
- **PASS** `S19e` Malformed /api/auth3/layer1_login: HTTP 200 {'ok': False, 'layer': 1, 'error': "Không tìm thấy tài khoản 'not-an-email'!"}
- **PASS** `S20` Email xác nhận không khớp: HTTP 400 {'ok': False, 'error': 'Hai ô nhập email không khớp nhau (Email và Xác nhận Email phải giống nhau 100%)!', 'status_code': 400}
- **PASS** `S21` DNS MX tên miền giả .invalid: HTTP 400 {'ok': False, 'error': "Tên miền 'this-domain-should-not-exist-zzz-datn-test.invalid' không có bản ghi MX thực tế (DNS MX Lookup failed)", 'status_code': 400}
- **QUESTIONABLE** `S22` Cấp 3 thêm family email (RBAC): HTTP 401 resp={'ok': False, 'status_code': 401, 'error': 'Thiếu thông tin người thêm (actor_id)'} — cần xác nhận API lấy actor từ đâu
- **PASS** `S23` Bật đèn ngủ khi đã ON (already-in-state): resp={'ok': True, 'results': [{'ok': True, 'device_id': 'bedroom_light', 'device_name': 'Đèn phòng ngủ', 'state': 'ON', 'already_in_state': True}], 'exact_spoken_reply': 'Đèn phòng ngủ 
- **QUESTIONABLE** `S24` Khách C3 đặt hẹn giờ qua /api/mobile/schedule: HTTP 200 {'ok': True, 'timer_id': 'timer_1', 'timer_ids': ['timer_1'], 'both_ampm': False, 'has_date': False, 'repeat': 'once', 'timer_pool_count': 1, 'exact_spoken_repl — API nhận tier từ client, engine có thể vẫn C1
- **PASS** `S39` HTTP guest enroll bằng giọng chủ nhà → chống trùng: HTTP 400 rejected=True resp={'ok': False, 'status': 'DUPLICATE_VOICE_REJECTED', 'reason': 'TRUNG_GIONG_NGUOI_TRONG_NHA', 'error': 'Trùng giọng người đã có trong nhà - Từ chối lưu', 'message': 'Trùng giọng người đã có trong nhà -
- **PASS** `S40` GET /api/voice_auth/profiles có owner_voice_1: HTTP 200 n_profiles=4
- **PASS** `S25` DSP: nhận diện chủ nhà C1: auth=True tier=1 speaker=owner_voice_1 strikes=0
- **PASS** `S26` Replay cùng wav chủ nhà 2 lần: r1=True r2=True strikes=0
- **PASS** `S27` Người lạ 3-strike (cảnh báo rồi im lặng): strikes=[1, 2, 3] silent3=True speech1=Tôi không được phép nhận lệnh từ người lạ.
- **PASS** `S28` Sau 3-strike người lạ, chủ nhà vẫn ra lệnh được: auth=True tier=1 strikes_after=0 vm.strikes=0
- **PASS** `S29` Hai người nói cùng lúc → ưu tiên C1: auth=True tier=1 speaker=owner_voice_1 multi=None
- **PASS** `S30` Chủ nhà + tiếng ồn quạt vẫn nhận diện: auth=True tier=1
- **PASS** `S31` Cổng chống trùng: thu âm giọng C1 để đăng ký C3: is_duplicate=True reason=TRUNG_GIONG_NGUOI_TRONG_NHA
- **PASS** `S32` Quality gate từ chối PCM quá ngắn: ok=False status=CHUA_DAT reason=Thời lượng mẫu thu âm quá ngắn (0.10s < 2.0s). Vui lòng nhấn giữ và đọc trọn vẹn câu mẫu!
- **PASS** `S33` Quality gate trên mẫu khách thật: ok=True status=DA_DAT f0=150.0
- **QUESTIONABLE** `S34` DSP mẫu thành viên C2: auth=True tier=2 speaker=user_voice_thanh_vien_a reason=None
- **QUESTIONABLE** `S35` DSP mẫu khách C3: auth=True tier=3 speaker=user_voice_khach_c expires=None
- **PASS** `S36` 5 mốc duration QR (in-process): fails=0 sample=[]
- **PASS** `S37` RBAC engine C3: đèn OK; cửa/còi/ĐH/bơm chặn: tier=3 door_ok=False light_ok=True ac_ok=False siren_ok=False pump_ok=False
- **PASS** `S38` RBAC engine C2: ĐH/bơm OK; cửa/còi chặn: tier=2 door=False ac=True pump=True siren=False
