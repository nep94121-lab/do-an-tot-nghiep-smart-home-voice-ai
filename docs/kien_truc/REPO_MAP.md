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
| 1 | `get_snapshot()` | [`simulator/rule_engine.py#L1265-L1317`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1265-L1317) | 29 | 5 | **92** |
| 2 | `emit()` | [`simulator/rule_engine.py#L964-L1016`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L964-L1016) | 25 | 2 | **77** |
| 3 | `get_current_user_name()` | [`simulator/rule_engine.py#L843-L847`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L843-L847) | 16 | 0 | **48** |
| 4 | `execute_device_action()` | [`simulator/rule_engine.py#L1820-L1957`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1820-L1957) | 12 | 9 | **45** |
| 5 | `_get_user_pool()` | [`simulator/rule_engine.py#L941-L949`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L941-L949) | 14 | 0 | **42** |
| 6 | `_save_overlay()` | [`simulator/rule_engine.py#L951-L962`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L951-L962) | 10 | 1 | **31** |
| 7 | `handle_tool_call()` | [`simulator/server.py#L1301-L1592`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1301-L1592) | 1 | 27 | **30** |
| 8 | `send_ws_json()` | [`simulator/server.py#L1108-L1159`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1108-L1159) | 9 | 2 | **29** |
| 9 | `_broadcast_rest_state_to_bridges()` | [`simulator/server.py#L827-L839`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L827-L839) | 9 | 2 | **29** |
| 10 | `run()` | [`simulator/server.py#L1886-L2083`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1886-L2083) | 1 | 21 | **24** |
| 11 | `publish()` | [`simulator/mqtt_bridge.py#L147-L182`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L147-L182) | 7 | 0 | **21** |
| 12 | `factory_reset()` | [`simulator/rule_engine.py#L3151-L3282`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L3151-L3282) | 4 | 7 | **19** |
| 13 | `get_if_else_rules()` | [`simulator/rule_engine.py#L1033-L1037`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1033-L1037) | 5 | 1 | **16** |
| 14 | `check_permission()` | [`simulator/rule_engine.py#L1319-L1333`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1319-L1333) | 5 | 1 | **16** |
| 15 | `get_merged_aliases()` | [`simulator/rule_engine.py#L1018-L1025`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1018-L1025) | 5 | 1 | **16** |

---

## 2. CẦU NỐI ĐỒNG BỘ LIÊN TẦNG (CROSS-LAYER CONTRACTS)

### 2.1. 19 Công cụ Gemini Live (`FunctionDeclaration` trong `server.py` <-> `rule_engine.py`)
- Danh sách: `control_device`, `schedule_action`, `update_timer`, `set_word_mapping`, `create_alias_rule`, `execute_alias_rule`, `set_if_else_rule`, `query_pools`, `query_knowledge_rag`, `request_factory_reset`, `confirm_factory_reset`, `confirm_pending_action`, `start_voice_enrollment`, `finalize_voice_enrollment`, `grant_user_permission`, `revoke_user_permission`, `set_query_permission_policy`, `admin_update_system_policy`, `admin_upsert_knowledge_rag`, `set_or_query_sensors`

### 2.2. 9 Chủ đề MQTT Chuẩn (`mqtt_bridge.py` <-> `rule_engine.py` <-> `esp8266_smarthome.ino`)
- Danh sách: `smarthome/cmd/actuate`, `smarthome/cmd/enroll_blink`, `smarthome/ir/blast`, `smarthome/ir/learn_start`, `smarthome/ir/learned_result`, `smarthome/state/report`, `smarthome/status/esp8266`, `smarthome/sync/pools`, `smarthome/telemetry/dht11`, `smarthome/telemetry/soil_moisture`

### 2.3. Các cổng HTTP REST API (`server.py` <-> `mobile_app/index.html` & `app.js`)
- Danh sách: `/`, `/api/clear_audit_logs`, `/api/device`, `/api/devops/status`, `/api/dht11`, `/api/ir_learn`, `/api/kb_upsert`, `/api/server_logs_and_db`, `/api/server_mode`, `/api/soil_moisture`, `/api/sqlite/overview`, `/api/sqlite/query`, `/api/state`, `/api/text_command`, `/api/voice_samples`, `/api/wokwi_files`, `/app`, `/archify`, `/archify/devops`, `/archify/erd`, `/logs`, `/wokwi`

### 2.4. 6 Chân Phần cứng NodeMCU ESP8266 (`rule_engine.py` <-> `esp8266_smarthome.ino`)
- Danh sách: `D1`, `D2`, `D3`, `D4`, `D5`, `D6`, `D7`, `D8`

---

## 3. CHỈ MỤC HÀM & CLASS THEO TỪNG FILE (ĐỂ AI ĐỌC ĐÚNG DÒNG `#Lstart-Lend`)

### 📄 [`simulator/server.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py)
- [`L57-L61`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L57-L61) `def get_knowledge_rag()`
- [`L83-L89`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L83-L89) `def load_key()`
- [`L95-L96`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L95-L96) `def safe_str(msg)`
- [`L699-L801`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L699-L801) `def build_system_instruction(engine)`
- [`L804-L816`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L804-L816) `def make_live_config(engine)`
- [`L827-L839`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L827-L839) `async def _broadcast_rest_state_to_bridges()`
- [`L843-L844`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L843-L844) `async def index()`
- [`L848-L849`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L848-L849) `async def mobile_app_index()`
- [`L853-L854`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L853-L854) `async def wokwi_page()`
- [`L858-L859`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L858-L859) `async def logs_page()`
- [`L863-L909`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L863-L909) `async def api_get_server_logs_and_db()`
- [`L913-L934`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L913-L934) `async def api_kb_upsert(payload)`
- [`L938-L947`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L938-L947) `async def api_clear_audit_logs()`
- [`L951-L961`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L951-L961) `async def api_get_wokwi_files()`
- [`L965-L966`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L965-L966) `async def api_get_state()`
- [`L970-L975`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L970-L975) `async def api_control_device(payload)`
- [`L979-L984`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L979-L984) `async def api_ir_learn(payload)`
- [`L988-L994`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L988-L994) `async def api_update_dht11(payload)`
- [`L998-L1002`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L998-L1002) `async def api_update_soil_moisture(payload)`
- [`L1006-L1015`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1006-L1015) `async def api_set_server_mode(payload)`
- [`L1019-L1064`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1019-L1064) `async def api_text_command(payload)`
- [`L1068-L1076`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1068-L1076) `async def list_voice_samples()`
- [`L1079-L2095`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1079-L2095) `class LiveBridgeSession` — *Quản lý kết nối giữa 1 tab trình duyệt và phiên Gemini 3.8 Live.*
  - [`L1082-L1106`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1082-L1106) `def __init__(ws)`
  - [`L1108-L1159`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1108-L1159) `async def send_ws_json(payload)`
  - [`L1161-L1167`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1161-L1167) `def _reset_turn_metrics(anchor_ts)`
  - [`L1169-L1195`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1169-L1195) `async def _sync_rules_context_to_gemini(event_note, send_to_model)` — *Cập nhật tức thì bảng Từ, Khẩu lệnh, Luật IF-ELSE và 2 Bể lên giao diện (và Gemini nếu cần).*
  - [`L1197-L1230`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1197-L1230) `async def _run_voice_enrollment_sequence(duration_seconds, target_tier, target_name)` — *Thực thi chuỗi tín hiệu phần cứng khi bắt đầu thu âm cấp quyền:*
  - [`L1232-L1299`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1232-L1299) `async def _process_completed_voice_enrollment(pcm_bytes)` — *Xử lý sau khi thu âm đủ: Nháy đèn báo kết thúc -> Báo thu âm đủ -> Phân tích tần số -> Báo phân tích xong & hỏi tên.*
  - [`L1301-L1592`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1301-L1592) `async def handle_tool_call(fc)`
  - [`L1594-L1723`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1594-L1723) `async def gemini_receive_loop()` — *Nhận liên tục các sự kiện từ Gemini 3.8 Live và đẩy về giao diện.*
  - [`L1725-L1884`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1725-L1884) `async def stream_wav_sample(sample_id)`
  - [`L1886-L2083`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L1886-L2083) `async def run()`
  - [`L2085-L2095`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L2085-L2095) `async def _periodic_timer_sync()`
- [`L2099-L2102`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L2099-L2102) `async def serve_archify_architecture()` — *Phục vụ Sơ đồ Kiến trúc Tương tác Archify (Repository-Backed Interactive HTML).*
- [`L2106-L2109`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L2106-L2109) `async def serve_archify_devops_workflow()` — *Phục vụ Sơ đồ Quy trình DevOps & CI/CD 5 Cổng Archify (Workflow Interactive HTML).*
- [`L2113-L2116`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L2113-L2116) `async def serve_archify_database_erd()` — *Phục vụ Sơ đồ Thực thể Kết hợp (ERD) 8 Bảng SQLite 3 (ERD Interactive HTML).*
- [`L2120-L2124`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L2120-L2124) `async def api_sqlite_overview()` — *Trả về thống kê chi tiết 8 bảng SQLite 3 (`smarthome.db`, WAL Mode, Foreign Keys).*
- [`L2128-L2132`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L2128-L2132) `async def api_sqlite_query(payload)` — *Thực thi câu lệnh SQL chỉ đọc (SELECT / PRAGMA / EXPLAIN) trực tiếp trên `smarthome.db`.*
- [`L2136-L2144`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L2136-L2144) `async def get_devops_pipeline_status()` — *Trả về Biên lai Kiểm định DevOps 5 Cổng & Mã băm SHA-256 mới nhất.*
- [`L2148-L2151`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py#L2148-L2151) `async def websocket_endpoint(ws)`

### 📄 [`simulator/rule_engine.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py)
- [`L45-L46`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L45-L46) `def get_vn_now()`
- [`L49-L51`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L49-L51) `def format_vn_time_ampm(dt)`
- [`L54-L81`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L54-L81) `def append_audit_log(category, event_type, summary, user_name, tier, details)` — *Ghi nhật ký bền vững (Persistent Audit Log) xuống đĩa tại simulator/data/system_audit_logs.jsonl.*
- [`L84-L100`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L84-L100) `def read_audit_logs(limit)` — *Đọc danh sách log mới nhất từ simulator/data/system_audit_logs.jsonl.*
- [`L103-L108`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L103-L108) `def clear_audit_logs()` — *Xóa toàn bộ log trong simulator/data/system_audit_logs.jsonl.*
- [`L271-L278`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L271-L278) `def _format_clock_12h(hour_24, minute, second)`
- [`L281-L367`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L281-L367) `def _extract_vn_date(time_str, date_str, now_vn)` — *Tách thông tin ngày/tháng (nếu người dùng có nói rõ) ra khỏi chuỗi giờ.*
- [`L386-L409`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L386-L409) `def detect_repeat_mode(text, explicit_repeat)` — *Tự động nhận diện chu kỳ lặp nếu người dùng nói 'hàng ngày', 'hàng tuần', 'hàng giờ', 'hàng tháng'.*
- [`L412-L432`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L412-L432) `def normalize_reset_scope(raw_scope)` — *Chuẩn hóa 4 loại Reset:*
- [`L435-L523`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L435-L523) `def parse_vn_clock_and_date(time_str, date_str, repeat, now_vn)` — *Phân tích chuỗi giờ Việt Nam theo đúng 4 quy tắc của Sếp + chu kỳ lặp (1 lần vs hàng ngày/tuần):*
- [`L526-L532`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L526-L532) `def parse_vn_time_string(time_str)` — *Hàm tương thích ngược trả về (hh, mm, ss) của mốc đầu tiên.*
- [`L535-L545`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L535-L545) `def ensure_factory_file()` — *Mặc định gốc hoàn toàn nguyên bản: mở cửa chỉ mở cửa, bật đèn chỉ bật đèn (không có luật phụ).*
- [`L548-L3282`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L548-L3282) `class SmartHomeEngine`
  - [`L549-L577`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L549-L577) `def __init__(on_event, on_voice_reset)`
  - [`L580-L617`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L580-L617) `def system_policies()`
  - [`L620-L621`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L620-L621) `def query_permission_mode()`
  - [`L623-L655`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L623-L655) `async def set_query_permission_policy(mode)` — *Thay đổi quy tắc phân quyền hỏi đáp (CHỈ Cấp 1 Nguyễn Tuấn Anh mới có quyền thay đổi):*
  - [`L657-L808`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L657-L808) `async def admin_update_system_policy(policy_key, policy_value, target_device_id)` — *Cho phép Admin Cấp 1 (Nguyễn Tuấn Anh) sửa BẤT KỲ quy tắc hệ thống, quyền hạn của Cấp 2/Cấp 3,*
  - [`L810-L820`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L810-L820) `def _init_users()`
  - [`L823-L824`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L823-L824) `def current_user_id()`
  - [`L827-L841`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L827-L841) `def current_tier()`
  - [`L843-L847`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L843-L847) `def get_current_user_name()`
  - [`L854-L882`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L854-L882) `def current_role(val)`
  - [`L884-L900`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L884-L900) `def set_active_user(user_or_role)`
  - [`L902-L914`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L902-L914) `def _default_overlay()`
  - [`L916-L939`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L916-L939) `def _load_overlay()`
  - [`L941-L949`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L941-L949) `def _get_user_pool(user_id)`
  - [`L951-L962`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L951-L962) `def _save_overlay()`
  - [`L964-L1016`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L964-L1016) `async def emit(event)`
  - [`L1018-L1025`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1018-L1025) `def get_merged_aliases(user_id)`
  - [`L1027-L1031`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1027-L1031) `def get_word_mappings(user_id)`
  - [`L1033-L1037`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1033-L1037) `def get_if_else_rules(user_id)`
  - [`L1039-L1040`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1039-L1040) `def get_chains()`
  - [`L1042-L1054`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1042-L1054) `def format_duration_vi(total_sec)`
  - [`L1056-L1072`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1056-L1072) `def _action_device_phrase_vi(device_id, action)`
  - [`L1074-L1115`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1074-L1115) `def describe_device_command(device_id)` — *Trả lời ngắn gọn lệnh điều khiển hiện tại của một thiết bị (gồm mặc định, từ đổi, khẩu lệnh đổi và luật IF).*
  - [`L1117-L1263`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1117-L1263) `def get_pools_summary(query_type, target_device_id)` — *Trả về thông tin chi tiết của 2 Bể (Bể Hẹn Giờ & Bể Luật Động) hoặc lệnh của 1 thiết bị.*
  - [`L1265-L1317`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1265-L1317) `def get_snapshot()`
  - [`L1319-L1333`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1319-L1333) `def check_permission(required_role)`
  - [`L1335-L1381`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1335-L1381) `def _check_custom_directive_device_lock(dev_id)` — *Kiểm tra xem có quy định tự nhiên nào của Admin Cấp 1 (trong custom_system_directives)*
  - [`L1383-L1401`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1383-L1401) `def check_device_permission(dev_id)`
  - [`L1406-L1419`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1406-L1419) `def _find_or_slug_user(target_name)`
  - [`L1421-L1458`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1421-L1458) `async def blink_signal_light(device_id, pulse_sec)` — *Nháy đèn 1 phát (Bật -> Tắt hoặc Tắt -> Bật) để làm tín hiệu bắt đầu/kết thúc thu âm cấp quyền.*
  - [`L1460-L1523`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1460-L1523) `async def start_voice_enrollment(target_tier, target_name, duration_seconds, duration_sec)` — *Bước 1 của Thu âm cấp quyền giọng nói:*
  - [`L1525-L1575`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1525-L1575) `async def stage_voice_enrollment_analysis(f0_hz, centroid_hz, embedding, duration_sec)` — *Bước 2 của Thu âm cấp quyền: Sau khi thu âm đủ -> Báo đã thu âm đủ, đã phân tích xong -> Hỏi tên (hoặc lưu luôn nếu đã có tên).*
  - [`L1577-L1623`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1577-L1623) `async def finalize_voice_enrollment(target_name, target_tier)` — *Bước 3 của Thu âm cấp quyền: Gán tên cho người vừa thu âm phân tích xong và lưu quyền chính thức.*
  - [`L1625-L1695`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1625-L1695) `async def grant_user_permission(target_name, target_tier)` — *Cấp quyền theo 3 Tầng (Tôn trọng cấu hình động `system_policies` do Admin Cấp 1 thiết lập).*
  - [`L1697-L1750`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1697-L1750) `async def revoke_user_permission(target_name)` — *Hủy quyền theo 3 Tầng (Tôn trọng cấu hình động `system_policies` do Admin Cấp 1 thiết lập).*
  - [`L1752-L1773`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1752-L1773) `def _expand_targets(device_id, action)`
  - [`L1775-L1781`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1775-L1781) `def _state_verb_vi(dev_type, state, already)`
  - [`L1783-L1818`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1783-L1818) `def _build_concise_spoken_reply(results)`
  - [`L1820-L1957`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1820-L1957) `async def execute_device_action(device_id, action, source, bypass_rbac, trigger_chains)`
  - [`L1959-L1969`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1959-L1969) `async def sync_edge_flash()` — *Đồng bộ bản sao 2 Bể (Bể 1 Hẹn giờ & Bể 2 Luật IF-ELSE) xuống Flash LittleFS của ESP8266.*
  - [`L1971-L1991`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1971-L1991) `async def update_sensor_telemetry(temp_c, humidity_pct, wifi_rssi_dbm)` — *Cập nhật thông số cảm biến DHT11 từ mạch ESP8266 và tự động kiểm tra luật ngưỡng nhiệt độ/độ ẩm.*
  - [`L1993-L2030`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L1993-L2030) `async def update_soil_moisture_telemetry(soil_moisture_pct, auto_pump_below_pct, auto_stop_above_pct)` — *Cập nhật thông số cảm biến Độ ẩm Đất YL-69 (Chân A0) và tự động điều khiển Máy bơm tưới cây (Chân D3).*
  - [`L2032-L2047`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2032-L2047) `async def learn_ir_remote_command(device_name, command_action, protocol, hex_code)` — *Chiếm quyền / Học lệnh Remote Hồng ngoại 38kHz (VS1838B D5 -> Lưu Write-Through -> Phát IR LED D2).*
  - [`L2049-L2128`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2049-L2128) `async def _evaluate_reactive_if_else(changed_dev_id, new_state)` — *Kiểm tra luật IF khi `changed_dev_id` chuyển sang `new_state`.*
  - [`L2133-L2153`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2133-L2153) `def _check_t1_timer_conflict(device_id, new_fire_at)` — *Kiểm tra xem cấp dưới có đặt lệnh vướng vào khung giờ hẹn giờ của Tầng 1 Nguyễn Tuấn Anh hay không.*
  - [`L2155-L2249`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2155-L2249) `async def schedule_timer_flexible(device_id, action, hours, minutes, seconds, vn_time_ampm, vn_date, repeat, reason)`
  - [`L2251-L2370`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2251-L2370) `async def schedule_action(device_id, action, delay_seconds, reason, bypass_rbac, trigger_chains, target_vn_time, repeat)`
  - [`L2372-L2461`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2372-L2461) `async def update_or_cancel_timer(device_id, operation, new_action, hours, minutes, seconds, vn_time_ampm, vn_date, repeat)`
  - [`L2466-L2516`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2466-L2516) `async def set_word_mapping(custom_word, target_meaning, require_confirmation)`
  - [`L2518-L2591`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2518-L2591) `async def create_alias_rule(phrase, target_devices_csv, target_actions_csv, require_confirmation)`
  - [`L2593-L2643`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2593-L2643) `async def set_server_connection_mode(connected)` — *Chuyển đổi giữa Chế độ Kết nối Server Laptop (Online) và Chế độ Mạch Độc Lập (Offline Default):*
  - [`L2645-L2788`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2645-L2788) `async def execute_offline_default_command(text, source)` — *Bộ giải mã Lệnh Mặc Định Cơ Bản khi Mạch chạy Độc Lập không kết nối Server (Offline Mode):*
  - [`L2790-L2832`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2790-L2832) `async def execute_alias_rule(phrase)`
  - [`L2834-L2861`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2834-L2861) `def _has_cycle(rules)`
  - [`L2863-L2878`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2863-L2878) `def _check_t1_rule_conflict(new_rule)` — *Kiểm tra xem luật IF-ELSE của Tầng 2 có mâu thuẫn hoặc vướng luật ưu tiên của Tầng 1 Nguyễn Tuấn Anh hay không.*
  - [`L2880-L3013`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L2880-L3013) `async def set_if_else_rule(when_device_id, when_state, then_device_id, then_action, delay_seconds, else_device_id, else_action, evaluate_now, require_confirmation)`
  - [`L3015-L3066`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L3015-L3066) `async def confirm_pending_action(confirmed)` — *Xác nhận hoặc hủy hành động đang chờ (bao gồm cả Xét Luật mới lẫn Reset Hệ Thống).*
  - [`L3075-L3125`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L3075-L3125) `async def request_factory_reset(scope)` — *Bước 1: Khi người dùng nói 'Reset ...', chưa xóa ngay mà bật cờ chờ xác nhận đúng theo loại reset và tầng.*
  - [`L3127-L3149`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L3127-L3149) `async def confirm_factory_reset(confirmed)` — *Bước 2: Thực thi hoặc hủy Reset (hoặc Luật đang chờ) sau khi người dùng trả lời câu hỏi xác nhận.*
  - [`L3151-L3282`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py#L3151-L3282) `async def factory_reset(scope)`

### 📄 [`simulator/mqtt_bridge.py`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py)
- [`L76-L494`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L76-L494) `class SmartHomeMQTTBridge` — *Bộ điều phối bản tin MQTT chuẩn System Design Primer:*
  - [`L84-L129`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L84-L129) `def __init__(on_event)`
  - [`L131-L141`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L131-L141) `def _load_ir_db()`
  - [`L143-L145`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L143-L145) `def _save_ir_db_write_through()` — *Write-Through Cache: Cập nhật RAM đồng thời ghi xuyên suốt xuống đĩa.*
  - [`L147-L182`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L147-L182) `async def publish(topic, payload, qos, retain, direction)` — *Phát hành gói tin MQTT với cơ chế kiểm soát Back Pressure.*
  - [`L184-L259`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L184-L259) `async def publish_actuate_command(device_id, state, action, source, user_name, tier)` — *Xuất bản tin MQTT điều khiển phần cứng ESP8266 (`smarthome/cmd/actuate`)*
  - [`L261-L276`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L261-L276) `async def publish_enrollment_blink(device_id, pulse_ms)` — *Xuất bản tin MQTT `smarthome/cmd/enroll_blink` để ESP8266 nháy đèn báo hiệu bắt đầu thu âm 3-2-1.*
  - [`L278-L329`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L278-L329) `async def sync_pools_to_esp8266_flash(timers, if_else_rules, system_policies)` — *CAP Theorem (AP Failover): Đồng bộ bản sao Bể 1 (Hẹn giờ) và Bể 2 (Luật IF-ELSE)*
  - [`L331-L358`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L331-L358) `async def update_dht11_telemetry(temp_c, humidity_pct, wifi_rssi_dbm)` — *Nhận bản tin cảm biến `smarthome/telemetry/dht11` từ chân D6 của ESP8266.*
  - [`L360-L387`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L360-L387) `async def update_soil_moisture_telemetry(soil_moisture_pct, adc_raw)` — *Nhận bản tin cảm biến Độ ẩm Đất `smarthome/telemetry/soil_moisture` từ chân A0 (YL-69 + LM393).*
  - [`L389-L413`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L389-L413) `async def start_ir_learning(device_name, command_action)` — *Bật chế độ Học lệnh chiếm quyền Remote (`smarthome/ir/learn_start`) trên chân D5 (`VS1838B`).*
  - [`L415-L479`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L415-L479) `async def complete_ir_learning(protocol, hex_code, raw_timings_us)` — *Nhận kết quả giải mã xung hồng ngoại từ ESP8266 (`smarthome/ir/learned_result`) và lưu Write-Through.*
  - [`L481-L494`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/mqtt_bridge.py#L481-L494) `def get_summary()`

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

