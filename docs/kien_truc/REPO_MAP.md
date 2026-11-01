# 🗺️ BẢN ĐỒ KHUNG XƯƠNG DỰ ÁN & MA TRẬN ẢNH HƯỞNG CHÉO (`REPO_MAP.md`)

> **QUY TẮC BẮT BUỘC CHO AI AGENT:**
> 1. **Đọc file này ĐẦU TIÊN** để lấy đúng số dòng `#Lstart-Lend` trước khi gọi `read_file` (cấm đọc cả file dài hàng nghìn dòng gây tràn Context Window).
> 2. **Trước khi sửa bất kỳ hàm, MQTT Topic hay API nào**, bắt buộc chạy lệnh kiểm tra bán kính ảnh hưởng:
>    `python -X utf8 scripts/code_graph_guard.py --impact <tên_hàm_hoặc_topic>`
> 3. **Sau khi sửa code**, bắt buộc chạy:
>    `python -X utf8 scripts/code_graph_guard.py --verify` và `python -X utf8 scripts/test_simulator_e2e.py`

---

## 1. TOP 15 HÀM TÂM CHẤN (HIGH BLAST-RADIUS — SỬA LÀ ẢNH HƯỞNG NHIỀU NƠI NHẤT)

| Hạng | Hàm / Phương thức | Vị trí (`#Lstart-Lend`) | Số nơi gọi (Callers) | Gọi xuống (Callees) | Điểm ảnh hưởng |
| :---: | :--- | :--- | :---: | :---: | :---: |
| 1 | `get_snapshot()` | [`simulator/rule_engine.py#L1246-L1298`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1246-L1298) | 29 | 5 | **92** |
| 2 | `emit()` | [`simulator/rule_engine.py#L949-L997`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L949-L997) | 25 | 2 | **77** |
| 3 | `get_current_user_name()` | [`simulator/rule_engine.py#L832-L836`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L832-L836) | 16 | 0 | **48** |
| 4 | `execute_device_action()` | [`simulator/rule_engine.py#L1801-L1938`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1801-L1938) | 12 | 9 | **45** |
| 5 | `_get_user_pool()` | [`simulator/rule_engine.py#L930-L938`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L930-L938) | 14 | 0 | **42** |
| 6 | `_save_overlay()` | [`simulator/rule_engine.py#L940-L947`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L940-L947) | 10 | 1 | **31** |
| 7 | `handle_tool_call()` | [`simulator/server.py#L1289-L1580`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1289-L1580) | 1 | 27 | **30** |
| 8 | `send_ws_json()` | [`simulator/server.py#L1096-L1147`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1096-L1147) | 9 | 2 | **29** |
| 9 | `_broadcast_rest_state_to_bridges()` | [`simulator/server.py#L822-L834`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L822-L834) | 9 | 2 | **29** |
| 10 | `run()` | [`simulator/server.py#L1847-L2044`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1847-L2044) | 1 | 21 | **24** |
| 11 | `publish()` | [`simulator/mqtt_bridge.py#L147-L182`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L147-L182) | 7 | 0 | **21** |
| 12 | `factory_reset()` | [`simulator/rule_engine.py#L3107-L3238`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L3107-L3238) | 4 | 7 | **19** |
| 13 | `get_if_else_rules()` | [`simulator/rule_engine.py#L1014-L1018`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1014-L1018) | 5 | 1 | **16** |
| 14 | `check_permission()` | [`simulator/rule_engine.py#L1300-L1314`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1300-L1314) | 5 | 1 | **16** |
| 15 | `get_merged_aliases()` | [`simulator/rule_engine.py#L999-L1006`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L999-L1006) | 5 | 1 | **16** |

---

## 2. CẦU NỐI ĐỒNG BỘ LIÊN TẦNG (CROSS-LAYER CONTRACTS)

### 2.1. 19 Công cụ Gemini Live (`FunctionDeclaration` trong `server.py` <-> `rule_engine.py`)
- Danh sách: `control_device`, `schedule_action`, `update_timer`, `set_word_mapping`, `create_alias_rule`, `execute_alias_rule`, `set_if_else_rule`, `query_pools`, `query_knowledge_rag`, `request_factory_reset`, `confirm_factory_reset`, `confirm_pending_action`, `start_voice_enrollment`, `finalize_voice_enrollment`, `grant_user_permission`, `revoke_user_permission`, `set_query_permission_policy`, `admin_update_system_policy`, `admin_upsert_knowledge_rag`, `set_or_query_sensors`

### 2.2. 9 Chủ đề MQTT Chuẩn (`mqtt_bridge.py` <-> `rule_engine.py` <-> `esp8266_smarthome.ino`)
- Danh sách: `smarthome/cmd/actuate`, `smarthome/cmd/enroll_blink`, `smarthome/ir/blast`, `smarthome/ir/learn_start`, `smarthome/ir/learned_result`, `smarthome/state/report`, `smarthome/status/esp8266`, `smarthome/sync/pools`, `smarthome/telemetry/dht11`, `smarthome/telemetry/soil_moisture`

### 2.3. Các cổng HTTP REST API (`server.py` <-> `mobile_app/index.html` & `app.js`)
- Danh sách: `/`, `/api/clear_audit_logs`, `/api/device`, `/api/dht11`, `/api/ir_learn`, `/api/kb_upsert`, `/api/server_logs_and_db`, `/api/server_mode`, `/api/soil_moisture`, `/api/state`, `/api/text_command`, `/api/voice_samples`, `/api/wokwi_files`, `/app`, `/logs`, `/wokwi`

### 2.4. 6 Chân Phần cứng NodeMCU ESP8266 (`rule_engine.py` <-> `esp8266_smarthome.ino`)
- Danh sách: `D1`, `D2`, `D3`, `D4`, `D5`, `D6`, `D7`, `D8`

---

## 3. CHỈ MỤC HÀM & CLASS THEO TỪNG FILE (ĐỂ AI ĐỌC ĐÚNG DÒNG `#Lstart-Lend`)

### 📄 [`simulator/server.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py)
- [`L52-L56`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L52-L56) `def get_knowledge_rag()`
- [`L78-L84`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L78-L84) `def load_key()`
- [`L90-L91`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L90-L91) `def safe_str(msg)`
- [`L694-L796`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L694-L796) `def build_system_instruction(engine)`
- [`L799-L811`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L799-L811) `def make_live_config(engine)`
- [`L822-L834`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L822-L834) `async def _broadcast_rest_state_to_bridges()`
- [`L838-L839`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L838-L839) `async def index()`
- [`L843-L844`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L843-L844) `async def mobile_app_index()`
- [`L848-L849`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L848-L849) `async def wokwi_page()`
- [`L853-L854`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L853-L854) `async def logs_page()`
- [`L858-L897`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L858-L897) `async def api_get_server_logs_and_db()`
- [`L901-L922`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L901-L922) `async def api_kb_upsert(payload)`
- [`L926-L935`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L926-L935) `async def api_clear_audit_logs()`
- [`L939-L949`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L939-L949) `async def api_get_wokwi_files()`
- [`L953-L954`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L953-L954) `async def api_get_state()`
- [`L958-L963`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L958-L963) `async def api_control_device(payload)`
- [`L967-L972`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L967-L972) `async def api_ir_learn(payload)`
- [`L976-L982`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L976-L982) `async def api_update_dht11(payload)`
- [`L986-L990`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L986-L990) `async def api_update_soil_moisture(payload)`
- [`L994-L1003`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L994-L1003) `async def api_set_server_mode(payload)`
- [`L1007-L1052`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1007-L1052) `async def api_text_command(payload)`
- [`L1056-L1064`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1056-L1064) `async def list_voice_samples()`
- [`L1067-L2056`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1067-L2056) `class LiveBridgeSession` — *Quản lý kết nối giữa 1 tab trình duyệt và phiên Gemini 3.8 Live.*
  - [`L1070-L1094`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1070-L1094) `def __init__(ws)`
  - [`L1096-L1147`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1096-L1147) `async def send_ws_json(payload)`
  - [`L1149-L1155`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1149-L1155) `def _reset_turn_metrics(anchor_ts)`
  - [`L1157-L1183`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1157-L1183) `async def _sync_rules_context_to_gemini(event_note, send_to_model)` — *Cập nhật tức thì bảng Từ, Khẩu lệnh, Luật IF-ELSE và 2 Bể lên giao diện (và Gemini nếu cần).*
  - [`L1185-L1218`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1185-L1218) `async def _run_voice_enrollment_sequence(duration_seconds, target_tier, target_name)` — *Thực thi chuỗi tín hiệu phần cứng khi bắt đầu thu âm cấp quyền:*
  - [`L1220-L1287`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1220-L1287) `async def _process_completed_voice_enrollment(pcm_bytes)` — *Xử lý sau khi thu âm đủ: Nháy đèn báo kết thúc -> Báo thu âm đủ -> Phân tích tần số -> Báo phân tích xong & hỏi tên.*
  - [`L1289-L1580`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1289-L1580) `async def handle_tool_call(fc)`
  - [`L1582-L1711`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1582-L1711) `async def gemini_receive_loop()` — *Nhận liên tục các sự kiện từ Gemini 3.8 Live và đẩy về giao diện.*
  - [`L1713-L1845`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1713-L1845) `async def stream_wav_sample(sample_id)`
  - [`L1847-L2044`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1847-L2044) `async def run()`
  - [`L2046-L2056`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L2046-L2056) `async def _periodic_timer_sync()`
- [`L2060-L2063`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L2060-L2063) `async def websocket_endpoint(ws)`

### 📄 [`simulator/rule_engine.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py)
- [`L40-L41`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L40-L41) `def get_vn_now()`
- [`L44-L46`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L44-L46) `def format_vn_time_ampm(dt)`
- [`L49-L75`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L49-L75) `def append_audit_log(category, event_type, summary, user_name, tier, details)` — *Ghi nhật ký bền vững (Persistent Audit Log) xuống đĩa tại simulator/data/system_audit_logs.jsonl.*
- [`L78-L94`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L78-L94) `def read_audit_logs(limit)` — *Đọc danh sách log mới nhất từ simulator/data/system_audit_logs.jsonl.*
- [`L97-L102`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L97-L102) `def clear_audit_logs()` — *Xóa toàn bộ log trong simulator/data/system_audit_logs.jsonl.*
- [`L265-L272`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L265-L272) `def _format_clock_12h(hour_24, minute, second)`
- [`L275-L361`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L275-L361) `def _extract_vn_date(time_str, date_str, now_vn)` — *Tách thông tin ngày/tháng (nếu người dùng có nói rõ) ra khỏi chuỗi giờ.*
- [`L380-L403`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L380-L403) `def detect_repeat_mode(text, explicit_repeat)` — *Tự động nhận diện chu kỳ lặp nếu người dùng nói 'hàng ngày', 'hàng tuần', 'hàng giờ', 'hàng tháng'.*
- [`L406-L426`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L406-L426) `def normalize_reset_scope(raw_scope)` — *Chuẩn hóa 4 loại Reset:*
- [`L429-L517`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L429-L517) `def parse_vn_clock_and_date(time_str, date_str, repeat, now_vn)` — *Phân tích chuỗi giờ Việt Nam theo đúng 4 quy tắc của Sếp + chu kỳ lặp (1 lần vs hàng ngày/tuần):*
- [`L520-L526`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L520-L526) `def parse_vn_time_string(time_str)` — *Hàm tương thích ngược trả về (hh, mm, ss) của mốc đầu tiên.*
- [`L529-L539`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L529-L539) `def ensure_factory_file()` — *Mặc định gốc hoàn toàn nguyên bản: mở cửa chỉ mở cửa, bật đèn chỉ bật đèn (không có luật phụ).*
- [`L542-L3238`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L542-L3238) `class SmartHomeEngine`
  - [`L543-L566`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L543-L566) `def __init__(on_event, on_voice_reset)`
  - [`L569-L606`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L569-L606) `def system_policies()`
  - [`L609-L610`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L609-L610) `def query_permission_mode()`
  - [`L612-L644`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L612-L644) `async def set_query_permission_policy(mode)` — *Thay đổi quy tắc phân quyền hỏi đáp (CHỈ Cấp 1 Nguyễn Tuấn Anh mới có quyền thay đổi):*
  - [`L646-L797`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L646-L797) `async def admin_update_system_policy(policy_key, policy_value, target_device_id)` — *Cho phép Admin Cấp 1 (Nguyễn Tuấn Anh) sửa BẤT KỲ quy tắc hệ thống, quyền hạn của Cấp 2/Cấp 3,*
  - [`L799-L809`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L799-L809) `def _init_users()`
  - [`L812-L813`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L812-L813) `def current_user_id()`
  - [`L816-L830`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L816-L830) `def current_tier()`
  - [`L832-L836`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L832-L836) `def get_current_user_name()`
  - [`L843-L871`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L843-L871) `def current_role(val)`
  - [`L873-L889`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L873-L889) `def set_active_user(user_or_role)`
  - [`L891-L903`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L891-L903) `def _default_overlay()`
  - [`L905-L928`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L905-L928) `def _load_overlay()`
  - [`L930-L938`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L930-L938) `def _get_user_pool(user_id)`
  - [`L940-L947`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L940-L947) `def _save_overlay()`
  - [`L949-L997`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L949-L997) `async def emit(event)`
  - [`L999-L1006`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L999-L1006) `def get_merged_aliases(user_id)`
  - [`L1008-L1012`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1008-L1012) `def get_word_mappings(user_id)`
  - [`L1014-L1018`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1014-L1018) `def get_if_else_rules(user_id)`
  - [`L1020-L1021`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1020-L1021) `def get_chains()`
  - [`L1023-L1035`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1023-L1035) `def format_duration_vi(total_sec)`
  - [`L1037-L1053`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1037-L1053) `def _action_device_phrase_vi(device_id, action)`
  - [`L1055-L1096`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1055-L1096) `def describe_device_command(device_id)` — *Trả lời ngắn gọn lệnh điều khiển hiện tại của một thiết bị (gồm mặc định, từ đổi, khẩu lệnh đổi và luật IF).*
  - [`L1098-L1244`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1098-L1244) `def get_pools_summary(query_type, target_device_id)` — *Trả về thông tin chi tiết của 2 Bể (Bể Hẹn Giờ & Bể Luật Động) hoặc lệnh của 1 thiết bị.*
  - [`L1246-L1298`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1246-L1298) `def get_snapshot()`
  - [`L1300-L1314`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1300-L1314) `def check_permission(required_role)`
  - [`L1316-L1362`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1316-L1362) `def _check_custom_directive_device_lock(dev_id)` — *Kiểm tra xem có quy định tự nhiên nào của Admin Cấp 1 (trong custom_system_directives)*
  - [`L1364-L1382`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1364-L1382) `def check_device_permission(dev_id)`
  - [`L1387-L1400`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1387-L1400) `def _find_or_slug_user(target_name)`
  - [`L1402-L1439`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1402-L1439) `async def blink_signal_light(device_id, pulse_sec)` — *Nháy đèn 1 phát (Bật -> Tắt hoặc Tắt -> Bật) để làm tín hiệu bắt đầu/kết thúc thu âm cấp quyền.*
  - [`L1441-L1504`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1441-L1504) `async def start_voice_enrollment(target_tier, target_name, duration_seconds, duration_sec)` — *Bước 1 của Thu âm cấp quyền giọng nói:*
  - [`L1506-L1556`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1506-L1556) `async def stage_voice_enrollment_analysis(f0_hz, centroid_hz, embedding, duration_sec)` — *Bước 2 của Thu âm cấp quyền: Sau khi thu âm đủ -> Báo đã thu âm đủ, đã phân tích xong -> Hỏi tên (hoặc lưu luôn nếu đã có tên).*
  - [`L1558-L1604`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1558-L1604) `async def finalize_voice_enrollment(target_name, target_tier)` — *Bước 3 của Thu âm cấp quyền: Gán tên cho người vừa thu âm phân tích xong và lưu quyền chính thức.*
  - [`L1606-L1676`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1606-L1676) `async def grant_user_permission(target_name, target_tier)` — *Cấp quyền theo 3 Tầng (Tôn trọng cấu hình động `system_policies` do Admin Cấp 1 thiết lập).*
  - [`L1678-L1731`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1678-L1731) `async def revoke_user_permission(target_name)` — *Hủy quyền theo 3 Tầng (Tôn trọng cấu hình động `system_policies` do Admin Cấp 1 thiết lập).*
  - [`L1733-L1754`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1733-L1754) `def _expand_targets(device_id, action)`
  - [`L1756-L1762`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1756-L1762) `def _state_verb_vi(dev_type, state, already)`
  - [`L1764-L1799`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1764-L1799) `def _build_concise_spoken_reply(results)`
  - [`L1801-L1938`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1801-L1938) `async def execute_device_action(device_id, action, source, bypass_rbac, trigger_chains)`
  - [`L1940-L1950`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1940-L1950) `async def sync_edge_flash()` — *Đồng bộ bản sao 2 Bể (Bể 1 Hẹn giờ & Bể 2 Luật IF-ELSE) xuống Flash LittleFS của ESP8266.*
  - [`L1952-L1972`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1952-L1972) `async def update_sensor_telemetry(temp_c, humidity_pct, wifi_rssi_dbm)` — *Cập nhật thông số cảm biến DHT11 từ mạch ESP8266 và tự động kiểm tra luật ngưỡng nhiệt độ/độ ẩm.*
  - [`L1974-L2011`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1974-L2011) `async def update_soil_moisture_telemetry(soil_moisture_pct, auto_pump_below_pct, auto_stop_above_pct)` — *Cập nhật thông số cảm biến Độ ẩm Đất YL-69 (Chân A0) và tự động điều khiển Máy bơm tưới cây (Chân D3).*
  - [`L2013-L2028`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2013-L2028) `async def learn_ir_remote_command(device_name, command_action, protocol, hex_code)` — *Chiếm quyền / Học lệnh Remote Hồng ngoại 38kHz (VS1838B D5 -> Lưu Write-Through -> Phát IR LED D2).*
  - [`L2030-L2109`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2030-L2109) `async def _evaluate_reactive_if_else(changed_dev_id, new_state)` — *Kiểm tra luật IF khi `changed_dev_id` chuyển sang `new_state`.*
  - [`L2114-L2134`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2114-L2134) `def _check_t1_timer_conflict(device_id, new_fire_at)` — *Kiểm tra xem cấp dưới có đặt lệnh vướng vào khung giờ hẹn giờ của Tầng 1 Nguyễn Tuấn Anh hay không.*
  - [`L2136-L2230`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2136-L2230) `async def schedule_timer_flexible(device_id, action, hours, minutes, seconds, vn_time_ampm, vn_date, repeat, reason)`
  - [`L2232-L2351`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2232-L2351) `async def schedule_action(device_id, action, delay_seconds, reason, bypass_rbac, trigger_chains, target_vn_time, repeat)`
  - [`L2353-L2442`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2353-L2442) `async def update_or_cancel_timer(device_id, operation, new_action, hours, minutes, seconds, vn_time_ampm, vn_date, repeat)`
  - [`L2447-L2497`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2447-L2497) `async def set_word_mapping(custom_word, target_meaning, require_confirmation)`
  - [`L2499-L2572`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2499-L2572) `async def create_alias_rule(phrase, target_devices_csv, target_actions_csv, require_confirmation)`
  - [`L2574-L2624`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2574-L2624) `async def set_server_connection_mode(connected)` — *Chuyển đổi giữa Chế độ Kết nối Server Laptop (Online) và Chế độ Mạch Độc Lập (Offline Default):*
  - [`L2626-L2744`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2626-L2744) `async def execute_offline_default_command(text, source)` — *Bộ giải mã Lệnh Mặc Định Cơ Bản khi Mạch chạy Độc Lập không kết nối Server (Offline Mode):*
  - [`L2746-L2788`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2746-L2788) `async def execute_alias_rule(phrase)`
  - [`L2790-L2817`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2790-L2817) `def _has_cycle(rules)`
  - [`L2819-L2834`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2819-L2834) `def _check_t1_rule_conflict(new_rule)` — *Kiểm tra xem luật IF-ELSE của Tầng 2 có mâu thuẫn hoặc vướng luật ưu tiên của Tầng 1 Nguyễn Tuấn Anh hay không.*
  - [`L2836-L2969`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2836-L2969) `async def set_if_else_rule(when_device_id, when_state, then_device_id, then_action, delay_seconds, else_device_id, else_action, evaluate_now, require_confirmation)`
  - [`L2971-L3022`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2971-L3022) `async def confirm_pending_action(confirmed)` — *Xác nhận hoặc hủy hành động đang chờ (bao gồm cả Xét Luật mới lẫn Reset Hệ Thống).*
  - [`L3031-L3081`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L3031-L3081) `async def request_factory_reset(scope)` — *Bước 1: Khi người dùng nói 'Reset ...', chưa xóa ngay mà bật cờ chờ xác nhận đúng theo loại reset và tầng.*
  - [`L3083-L3105`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L3083-L3105) `async def confirm_factory_reset(confirmed)` — *Bước 2: Thực thi hoặc hủy Reset (hoặc Luật đang chờ) sau khi người dùng trả lời câu hỏi xác nhận.*
  - [`L3107-L3238`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L3107-L3238) `async def factory_reset(scope)`

### 📄 [`simulator/mqtt_bridge.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py)
- [`L76-L488`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L76-L488) `class SmartHomeMQTTBridge` — *Bộ điều phối bản tin MQTT chuẩn System Design Primer:*
  - [`L84-L129`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L84-L129) `def __init__(on_event)`
  - [`L131-L141`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L131-L141) `def _load_ir_db()`
  - [`L143-L145`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L143-L145) `def _save_ir_db_write_through()` — *Write-Through Cache: Cập nhật RAM đồng thời ghi xuyên suốt xuống đĩa.*
  - [`L147-L182`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L147-L182) `async def publish(topic, payload, qos, retain, direction)` — *Phát hành gói tin MQTT với cơ chế kiểm soát Back Pressure.*
  - [`L184-L259`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L184-L259) `async def publish_actuate_command(device_id, state, action, source, user_name, tier)` — *Xuất bản tin MQTT điều khiển phần cứng ESP8266 (`smarthome/cmd/actuate`)*
  - [`L261-L276`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L261-L276) `async def publish_enrollment_blink(device_id, pulse_ms)` — *Xuất bản tin MQTT `smarthome/cmd/enroll_blink` để ESP8266 nháy đèn báo hiệu bắt đầu thu âm 3-2-1.*
  - [`L278-L323`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L278-L323) `async def sync_pools_to_esp8266_flash(timers, if_else_rules, system_policies)` — *CAP Theorem (AP Failover): Đồng bộ bản sao Bể 1 (Hẹn giờ) và Bể 2 (Luật IF-ELSE)*
  - [`L325-L352`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L325-L352) `async def update_dht11_telemetry(temp_c, humidity_pct, wifi_rssi_dbm)` — *Nhận bản tin cảm biến `smarthome/telemetry/dht11` từ chân D6 của ESP8266.*
  - [`L354-L381`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L354-L381) `async def update_soil_moisture_telemetry(soil_moisture_pct, adc_raw)` — *Nhận bản tin cảm biến Độ ẩm Đất `smarthome/telemetry/soil_moisture` từ chân A0 (YL-69 + LM393).*
  - [`L383-L407`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L383-L407) `async def start_ir_learning(device_name, command_action)` — *Bật chế độ Học lệnh chiếm quyền Remote (`smarthome/ir/learn_start`) trên chân D5 (`VS1838B`).*
  - [`L409-L473`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L409-L473) `async def complete_ir_learning(protocol, hex_code, raw_timings_us)` — *Nhận kết quả giải mã xung hồng ngoại từ ESP8266 (`smarthome/ir/learned_result`) và lưu Write-Through.*
  - [`L475-L488`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L475-L488) `def get_summary()`

### 📄 [`simulator/voice_auth.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py)
- [`L40-L171`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L40-L171) `def denoise_and_isolate_human_voice(pcm16, sr)` — *Khử tiếng ồn nền (quạt trần, điều hòa, tạp âm) và chỉ giữ lại dải tần tiếng người nói (85Hz - 3900Hz).*
- [`L174-L278`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L174-L278) `def extract_voice_features(pcm16, sr)` — *[BỘ LỌC TẦNG 1 - NHANH ~1ms]: Trích xuất tần số cơ bản F0 (Hz), Spectral Centroid (Hz),*
- [`L281-L440`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L281-L440) `def extract_stage2_deep_features(pcm16, sr)` — *[BỘ LỌC TẦNG 2 - CHUYÊN SÂU ~2.5ms]:*
- [`L443-L635`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L443-L635) `def detect_multi_speaker_and_resolve_priority(pcm16_clean, profiles, sr)` — *Phát hiện khi có 2 người cùng nói (nói nối nhau hoặc nói đè lên nhau)*
- [`L638-L645`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L638-L645) `def cosine_sim(v1, v2)`
- [`L648-L673`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L648-L673) `def transform_pcm_to_intruder_voice(pcm16, sr)` — *Biến đổi tần số giọng nói gốc thành Giọng số 2 (Giọng người lạ - Không được phép).*
- [`L676-L689`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L676-L689) `def synthesize_noisy_fan_voice(pcm16_owner, sr)` — *Tạo mẫu kiểm thử: Giọng Chủ nhà nói trong môi trường có tiếng quạt trần ù mạnh + tiếng gió nền.*
- [`L692-L707`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L692-L707) `def synthesize_two_speakers_audio(pcm16_owner, pcm16_intruder, sr)` — *Tạo mẫu kiểm thử: 2 người cùng nói trong 1 lượt (Người lạ nói chèn khúc đầu + Chủ nhà Cấp 1 nói chính).*
- [`L710-L1166`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L710-L1166) `class VoiceAuthManager` — *Quản lý Xác Thực Giọng Nói Kép 2 Tầng (Bộ lọc 1 nhanh + Bộ lọc 2 sinh trắc học sâu),*
  - [`L716-L742`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L716-L742) `def __init__(audio_dir)`
  - [`L744-L812`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L744-L812) `def _init_or_load_profiles()` — *Tạo sẵn mẫu giọng Chủ nhà, Người lạ, Mẫu có tiếng ồn quạt, và Mẫu 2 người cùng nói.*
  - [`L815-L820`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L815-L820) `def _write_wav16k(path, pcm16)`
  - [`L822-L859`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L822-L859) `def enroll_owner_from_pcm16k(pcm_bytes, label)` — *Đăng ký vân giọng mới từ đoạn thu âm tự do 5 - 10 giây (16kHz PCM),*
  - [`L861-L888`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L861-L888) `def analyze_voice_pcm16k(pcm_bytes)` — *Phân tích đoạn thu âm giọng nói 16kHz vừa thu được (đã qua lọc tiếng ồn + trích xuất 2 tầng) để cấp quyền.*
  - [`L890-L933`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L890-L933) `def register_enrolled_user_profile(user_id, user_name, tier, role, f0_hz, centroid_hz, embedding, formants_hz, deep_embedding)` — *Lưu hồ sơ giọng nói 2 tầng của người dùng mới được cấp quyền (Cấp 2 hoặc Cấp 3).*
  - [`L935-L1122`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L935-L1122) `def verify_pcm16k_and_apply_strikes(pcm_bytes)` — *Quy trình Xác Thực Giọng Nói Kép 2 Tầng + Khử Tiếng Ồn + Tách 2 Người Cùng Nói:*
  - [`L1124-L1126`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L1124-L1126) `def reset_strikes()`
  - [`L1128-L1166`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/voice_auth.py#L1128-L1166) `def reset_to_owner_only()` — *Reset quyền giọng nói: Xóa mọi giọng phụ khác, chỉ giữ lại duy nhất giọng của Chủ nhà (owner_voice_1) và mẫu đối chứng.*

### 📄 [`simulator/knowledge_rag.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py)
- [`L102-L112`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L102-L112) `def ensure_kb_file()`
- [`L115-L327`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L115-L327) `class SmartHomeKnowledgeRAG` — *Bộ RAG sử dụng Google Embedding (`gemini-embedding-001`) để trả lời ngắn gọn về trợ lý ảo và quy định 3 tầng.*
  - [`L118-L123`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L118-L123) `def __init__(api_key)`
  - [`L125-L126`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L125-L126) `def _doc_text_for_embedding(item)`
  - [`L128-L168`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L128-L168) `def _load_or_build_embeddings()`
  - [`L171-L177`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L171-L177) `def _cosine(a, b)`
  - [`L179-L256`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L179-L256) `def retrieve(query, current_tier, query_permission_mode, top_k)` — *Truy xuất đoạn tri thức khớp nhất bằng Google Embedding (`gemini-embedding-001`) + Cosine Similarity.*
  - [`L258-L321`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L258-L321) `def upsert_knowledge_item(topic, content, keywords, min_tier, current_tier)` — *Cho phép Admin Cấp 1 (Nguyễn Tuấn Anh) dạy thêm hoặc sửa nội dung RAG bằng giọng nói và nhúng vector ngay.*
  - [`L323-L327`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/knowledge_rag.py#L323-L327) `def reset_custom_knowledge()`

