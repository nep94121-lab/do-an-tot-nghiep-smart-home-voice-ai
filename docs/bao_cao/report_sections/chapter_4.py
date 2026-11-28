"""Chapter 4: Thiết kế và triển khai (Backend, Voice AI, Web 3D, Android, ESP8266, KiCad PCB, 3D-Print House)."""

from __future__ import annotations

import pathlib

from .docx_helpers import ReportBuilder


def build_chapter_4(rb: ReportBuilder, assets_dir: pathlib.Path) -> None:
    demo_dir = assets_dir / "demo"
    sw_dir = assets_dir / "software"

    rb.add_chapter(4, "THIẾT KẾ VÀ TRIỂN KHAI")
    rb.add_para(
        "Trong Chương 4, báo cáo trình bày thiết kế kiến trúc chi tiết và phương án triển khai kỹ thuật cho toàn bộ bảy phân hệ cốt lõi "
        "của hệ thống Smart Home Voice AI: máy chủ FastAPI và cơ sở dữ liệu SQLite WAL, cầu nối giọng nói thời gian thực Gemini 3.8 Live, "
        "giao diện Web 3D Digital Twin kèm trang /wokwi PCB-Direct, ứng dụng di động Android Kotlin/Compose, firmware ESP8266 nạp Wi-Fi runtime "
        "với cơ chế ngoại tuyến A1–A4, bo mạch PCB Hub DIY v3 (KiCad 10.0) và mô hình nhà in 3D lắp mộng tối ưu giảm nhựa (FreeCAD 1.1.4 + PrusaSlicer 2.9.7)."
    )

    # ===== 4.1 THIẾT KẾ MÁY CHỦ BACKEND, CSDL VÀ PHÂN QUYỀN =====
    rb.add_h2("4.1. Thiết kế máy chủ Backend FastAPI, Cơ sở dữ liệu SQLite 3NF và RBAC")

    rb.add_h3("4.1.1. Kiến trúc mô-đun hóa của máy chủ FastAPI")
    rb.add_para(
        "Máy chủ trung tâm được khởi chạy tại điểm vào backend/server.py bằng Uvicorn ASGI trên cổng cục bộ 8088 (môi trường kiểm thử cô lập "
        "sử dụng cổng 8097 với tệp cơ sở dữ liệu tạm độc lập). Để đảm bảo tính dễ bảo trì và phân tách trách nhiệm rõ ràng, "
        "tầng API được chia thành các router chuyên biệt: routes_devices.py (điều khiển 6 thiết bị, nhận telemetry 3 cảm biến, đồng bộ MQTT và Wokwi), "
        "routes_auth.py (đăng nhập, đăng ký, OTP Gmail, quản lý tài khoản 3 tầng và khóa mã PIN Chủ nhà), routes_qr.py và routes_guest.py "
        "(phát hành/xác minh mã QR động TOTP 10 giây, bắt tay 180 giây và thu hồi phiên Khách Cấp 3), routes_automation.py "
        "(quản lý 2 bể tự động hóa độc lập TimersPool và RulesPool cùng lệnh tùy chỉnh) và routes_logs.py (nhật ký kiểm toán và tri thức RAG)."
    )
    rb.add_para(
        "Các sự kiện thay đổi trạng thái từ bất kỳ nguồn nào (nút bấm Web, Android APK, giọng nói Gemini Live, cảm biến phần cứng hay luật tự động) "
        "đều đi qua một trung tâm phát sóng thời gian thực (Realtime Hub — backend/realtime_hub.py) sử dụng đồng thời Server-Sent Events (SSE) "
        "và danh sách cầu nối WebSocket đang hoạt động (_ACTIVE_BRIDGES). Nhờ vậy, mọi trình duyệt và điện thoại đều cập nhật tức thì mà không cần tải lại trang. "
        "Bảng 4.1 liệt kê các nhóm điểm cuối API chính của máy chủ."
    )
    rb.add_table(
        "Danh mục các nhóm giao diện lập trình API REST, WebSocket và SSE của máy chủ Backend",
        ["Nhóm API", "Đường dẫn tiêu biểu", "Quyền yêu cầu", "Chức năng nghiệp vụ chính"],
        [
            ("Hệ thống & Sức khỏe", "GET /api/version, GET /api/health", "Công khai", "Trả về mã phiên bản Git, trạng thái máy chủ, tình trạng kết nối bo mạch ESP8266."),
            ("Thiết bị & Cảm biến", "GET /api/state, POST /api/device/{id}", "Cấp 1 / 2 / 3 (lọc)", "Đọc trạng thái 6 thiết bị & 3 cảm biến; bật/tắt thiết bị sau kiểm tra RBAC."),
            ("Đồng bộ Phần cứng", "POST /api/hardware/resync, /api/sound_sensor", "Hardware Key / LAN", "Nhận dữ liệu DHT11, đất A0, KY-037 D5; đồng bộ ngược sau giai đoạn ngoại tuyến A4."),
            ("Xác thực & Tài khoản", "POST /api/auth/login, /otp, /users", "Công khai / Cấp 1", "Đăng nhập mật khẩu/OTP, quản lý danh sách email được mời, đặt PIN Chủ nhà."),
            ("Mã QR động Khách", "POST /api/qr/generate, /api/qr/claim", "Cấp 1 / Khách", "Tạo mã QR đổi chữ ký TOTP mỗi 10 giây (chờ 180 giây), cấp/thu hồi phiên Cấp 3."),
            ("Tự động hóa 2 Pool", "GET/POST /api/automation/*, /schedules", "Cấp 1 / Cấp 2", "Quản lý TimersPool (hẹn giờ/lịch lặp), RulesPool (luật cảm biến) và custom_commands."),
            ("Nhật ký & Tri thức", "GET /api/logs, /api/rag/query", "Chỉ Cấp 1", "Truy vấn lịch sử audit_logs theo thời gian/thiết bị/người dùng và tra cứu RAG."),
            ("Thời gian thực Live", "WS /ws/live, GET /api/events (SSE)", "Phiên hợp lệ", "Kênh âm thanh hai chiều Gemini 3.8 Live (PCM 16/24 kHz) và đẩy trạng thái SSE."),
        ],
        col_widths_cm=[2.8, 4.4, 2.5, 5.8],
        font_pt=9.8,
    )

    rb.add_h3("4.1.2. Thiết kế cơ sở dữ liệu SQLite 3.53.2 chuẩn hóa 3NF (chế độ WAL)")
    rb.add_para(
        "Cơ sở dữ liệu quan hệ được quản trị bằng cơ chế di trú phiên bản tự động (backend/db_migrations.py), bật đồng thời hai cờ quan trọng là "
        "PRAGMA journal_mode = WAL (Write-Ahead Logging) để cho phép nhiều yêu cầu đọc SSE/REST diễn ra song song với giao dịch ghi nhật ký mà không gặp lỗi khóa bảng, "
        "và PRAGMA foreign_keys = ON để cưỡng chế toàn vẹn tham chiếu. Lược đồ chuẩn hóa 3NF gồm trên 20 bảng chia làm 4 cụm nghiệp vụ chính: "
        "(1) Cụm danh tính và bảo mật (roles, users, user_sessions, invites, otp_challenges, trusted_devices, owner_pin_security, login_rate_limits); "
        "(2) Cụm thiết bị và trạng thái (devices, device_state, system_state_meta); "
        "(3) Cụm tự động hóa hai bể và lệnh tùy chỉnh (timers_pool, schedules, rules_pool, automation_rules, compound_automation_rules, custom_commands, pending_confirmations); "
        "(4) Cụm nhật ký kiểm toán và tri thức (audit_logs, knowledge_rag, aoede_audio_cache, durable_kv). Hình 4.1 minh họa lược đồ thực thể liên kết (ERD)."
    )
    rb.add_figure(
        sw_dir / "sw_arch_db_erd.png",
        "Sơ đồ thực thể liên kết (ERD) cơ sở dữ liệu SQLite 3.53.2 chuẩn hóa 3NF chế độ WAL",
        max_width_cm=15.0,
        max_height_cm=9.0,
    )

    rb.add_h3("4.1.3. Cơ chế Tự động hóa 2 Pool độc lập và Bảo mật QR động TOTP 10 giây")
    rb.add_para(
        "Để tránh xung đột giữa các bộ hẹn giờ một lần (như '5 phút nữa tắt đèn phòng khách') và các luật phản ứng cảm biến liên tục "
        "(như 'khi độ ẩm đất nhỏ hơn 40% thì bật bơm tưới'), kiến trúc bộ máy quy tắc (backend/rule_engine.py) tách thành hai bể thực thi hoàn toàn độc lập: "
        "TimersPool (backend/engine/timers_pool.py) chuyên quản lý lịch đếm ngược và lịch đồng hồ lặp (once/hourly/daily/weekly/monthly) với khả năng sửa/hủy tức thì, "
        "và RulesPool (backend/engine/rules_pool.py kết hợp compound_automation_rules) chuyên đánh giá điều kiện tổ hợp đa cảm biến kèm khoảng nghỉ chống dao động (cooldown)."
    )
    rb.add_para(
        "Đối với tính năng mời Khách Cấp 3 (backend/auth/qr_totp_mixin.py), mỗi khi Chủ nhà bấm tạo mã QR, máy chủ sinh một phiên chờ bắt tay "
        "có hiệu lực tối đa 180 giây kèm khóa bí mật ngẫu nhiên. Mã QR hiển thị trên màn hình Chủ nhà tự động đổi chữ ký HMAC-SHA256 theo cửa sổ thời gian "
        "TOTP đúng 10 giây (cho phép độ lệch nhỏ ở biên chuyển cửa sổ). Cơ chế này vô hiệu hóa hoàn toàn nguy cơ chụp ảnh màn hình mã QR gửi cho người ngoài "
        "sử dụng sau đó, đồng thời Chủ nhà có thể bấm thu hồi phiên khách ngay lập tức làm ngắt mọi kết nối WebSocket đang hoạt động."
    )

    # ===== 4.2 TRỢ LÝ GIỌNG NÓI GEMINI 3.8 LIVE =====
    rb.add_h2("4.2. Thiết kế Trợ lý giọng nói Gemini 3.8 Live, Echo Guard và Lệnh tùy chỉnh")
    rb.add_para(
        "Phân hệ trợ lý giọng nói (backend/live/gemini_bridge.py và backend/live/prompt_builder.py) thiết lập một cầu nối WebSocket song công toàn phần "
        "giữa trình duyệt/ứng dụng di động với dịch vụ Gemini 3.8 Live API thông qua SDK google-genai 2.33.0. Luồng âm thanh đầu vào từ micro người dùng "
        "được chuẩn hóa thành PCM 16 kHz, 16-bit Mono, chia khung đều 20 ms (320 mẫu = 640 byte/khung); luồng phản hồi từ giọng đọc tiếng Việt Aoede "
        "có tần số lấy mẫu 24 kHz PCM 16-bit Mono được phát nối tiếp mượt mà."
    )
    rb.add_para(
        "Bốn giải pháp kỹ thuật trọng yếu đã được triển khai để bảo đảm độ ổn định hội thoại tiếng Việt dài hơi:"
    )
    rb.add_bullet(
        "Chống dội âm phía máy chủ (ServerEchoGuard) và lọc tiếng nói tiếng Việt (VietnameseVAD): ",
        "Khi trợ lý Aoede đang phát âm thanh phản hồi qua loa điện thoại hoặc laptop, ServerEchoGuard (backend/live/echo_and_speech_guard.py) "
        "theo dõi cửa sổ phát âm thực tế kết hợp ngưỡng năng lượng và bộ phát hiện giọng nói VietnameseVAD để chặn luồng vọng loa đi ngược vào mô hình, "
        "đồng thời vẫn cho phép người dùng ngắt lời chủ động (barge-in) khi cần thiết.",
    )
    rb.add_bullet(
        "Cơ chế Zero-Drop Reconnect với hàng đợi In-Flight PCM: ",
        "Nếu phiên WebSocket với thượng nguồn Gemini Live bị ngắt đột ngột do mạng chập chờn hoặc quá thời lượng phiên, LiveBridgeSession tự động "
        "đệm các khung PCM đang nói vào hàng đợi bộ nhớ, tái thiết lập kết nối ngầm kèm ngữ cảnh trạng thái nhà mới nhất và phát tiếp không làm rơi câu lệnh.",
    )
    rb.add_bullet(
        "Mô hình thực thi Actuate-First và 4 bức tường lửa Prompt: ",
        "Hệ thống khai báo 20 Function Declarations cho Gemini 3.8 Live (Bảng 4.2). Với lệnh điều khiển trực tiếp hợp lệ, máy chủ cưỡng chế thực thi ngay lập tức "
        "trước khi trả kết quả cho AI phát câu xác nhận ngắn gọn 100% tiếng Việt (VD: 'Đã bật đèn phòng khách.'). Bộ lọc sanitize_spoken_vietnamese_text "
        "loại bỏ hoàn toàn từ khóa kỹ thuật tiếng Anh hay ký hiệu Markdown trước khi hiển thị phụ đề.",
    )
    rb.add_bullet(
        "Quy tắc xác nhận đúng 1 lần cho lệnh tùy chỉnh (chuẩn hành vi agyfix11): ",
        "Khi người dùng dạy một lệnh ngữ cảnh mới bằng lời nói (VD: 'Từ giờ khi tôi nói chế độ đi ngủ thì tắt hết đèn và đóng cửa chính'), "
        "hệ thống ghi nhận yêu cầu vào bảng pending_confirmations và chỉ hỏi xác nhận đúng 1 lần duy nhất. Ngay sau khi người dùng xác nhận ('Đồng ý'/'Đúng rồi'), "
        "lệnh được lưu vào custom_commands và kể từ lần gọi kế tiếp sẽ thực thi trực tiếp toàn bộ chuỗi thiết bị mà không hỏi lại.",
    )

    rb.add_table(
        "Danh mục các nhóm hàm công cụ (Function Declarations) tiêu biểu cấp cho Gemini 3.8 Live API",
        ["Tên hàm công cụ", "Tham số cốt lõi", "Hành vi thực thi & Kiểm tra RBAC"],
        [
            ("control_device", "device_id, action", "Bật/tắt/mở/đóng ngay 1 trong 6 thiết bị hoặc nhóm all_lights/all_devices; kiểm tra quyền Cấp 1/2/3 phía server."),
            ("schedule_action", "device_id, action, seconds/minutes/hours, vn_time_ampm, repeat", "Đặt hẹn đếm ngược hoặc mốc giờ đồng hồ (once/daily/weekly/monthly) vào TimersPool."),
            ("update_timer", "device_id, operation (modify/cancel), thời gian mới", "Sửa đổi mốc giờ hoặc hủy bỏ một bộ hẹn giờ đang hoạt động mà không cần tạo mới."),
            ("create_automation_rule", "condition (cảm biến/trạng thái), actions, cooldown", "Tạo luật tự động hóa phản ứng cảm biến/tổ hợp lưu vào RulesPool."),
            ("teach_custom_command", "trigger_phrase, actions_list", "Khởi tạo lệnh tùy chỉnh mới → lưu pending_confirmations → hỏi xác nhận đúng 1 lần."),
            ("confirm_custom_command", "confirmation_decision (approve/cancel)", "Hoàn tất lưu custom_commands sau khi người dùng xác nhận hoặc hủy bỏ bản nháp."),
            ("get_home_status / query_rag", "scope / question_vi", "Trả về trạng thái 6 thiết bị, 3 cảm biến, lịch hẹn đang chạy và lịch sử từ Knowledge RAG."),
        ],
        col_widths_cm=[3.8, 4.7, 7.0],
        font_pt=9.8,
    )

    # ===== 4.3 GIAO DIỆN WEB 3D DIGITAL TWIN & ANDROID APP =====
    rb.add_h2("4.3. Thiết kế Giao diện Web 3D Digital Twin, /wokwi và Ứng dụng Android")

    rb.add_h3("4.3.1. Giao diện Web đa trang, 3D Digital Twin (Three.js) và /wokwi PCB-Direct")
    rb.add_para(
        "Giao diện Web đặt trong thư mục web/ được tổ chức thành sáu màn hình chuyên biệt tương ứng với thanh điều hướng bên trái: "
        "Tổng quan 3D (/), Tự động hóa (/automation), Xác thực & Phân quyền (/auth), Mô phỏng Phần cứng (/wokwi, giới hạn data-max-tier=2), "
        "Nhật ký kiểm toán (/logs, giới hạn data-owner-only=true) và Cổng cài đặt ứng dụng (/app). Toàn bộ nhãn hiển thị, thông báo lỗi và hộp thoại "
        "đều sử dụng 100% tiếng Việt chuẩn mực, hỗ trợ chuyển đổi mượt mà giữa giao diện Sáng (Light) và Tối (Dark) cũng như bố cục đáp ứng "
        "từ màn hình máy tính 1366×768 đến điện thoại 412×915."
    )
    rb.add_para(
        "Điểm nhấn trực quan của giao diện là mô hình song sinh số 3D (Web 3D Digital Twin) xây dựng bằng Three.js đồng bộ hình học "
        "với thiết kế cơ khí vỏ nhà và đủ 14 module điện tử: khi người dùng bật đèn phòng khách/phòng ngủ, nguồn sáng điểm PointLight phát sáng trực tiếp "
        "tại đúng vị trí LED 5 mm trên vách ngăn giữa; khi mở cửa chính, cánh cửa P08 xoay mượt quanh trục bản lề đồng trục Servo SG90 từ 0° đến 90°; "
        "khi bật máy bơm tưới cây, hệ thống hạt mô phỏng dòng nước phun vào chậu đất. Trang /wokwi PCB-Direct hiển thị sơ đồ đấu nối 10 chân "
        "và 40 sợi dây trực tiếp lên PCB Hub DIY v3 (0 breadboard) kèm công cụ bật/tắt kiểm thử trực quan từng thiết bị."
    )

    rb.add_h3("4.3.2. Thiết kế ứng dụng di động Android thuần (Kotlin + Jetpack Compose)")
    rb.add_para(
        "Ứng dụng di động đặt trong thư mục app/ (mã gói vn.edu.hust.seee.smarthome, phiên bản 1.0, compileSdk 36, targetSdk 34, minSdk 26 hỗ trợ từ Android 8.0 trở lên) "
        "được chia làm hai mô-đun kiến trúc rõ ràng: app-core chứa tầng mạng REST/SSE/WebSocket, mô hình trạng thái, quản lý phiên RBAC và lõi giao diện Compose; "
        "app chứa điểm khởi chạy Activity và cấu hình đóng gói APK qua Lightbuild 0.0.30. Giao diện chính (MainScreen) bố trí 4 tab điều hướng dưới đáy theo chuẩn Material Design 3:"
    )
    rb.add_bullet("Tab Trang chủ (HomeScreenTab): ", "Hiển thị thẻ trạng thái kết nối máy chủ, thông số 3 cảm biến thời gian thực (Nhiệt độ/Độ ẩm DHT11, Độ ẩm đất %, Trạng thái âm thanh KY-037) và nhóm nút điều khiển nhanh theo đúng phân quyền phiên hiện tại.")
    rb.add_bullet("Tab Thiết bị (DevicesScreenTab): ", "Quản lý chi tiết 6 thiết bị chấp hành kèm phản hồi trạng thái tức thì, tự động khóa/ẩn các điều khiển ngoài thẩm quyền Cấp 2 (Cửa chính, Còi) và Cấp 3 (chỉ giữ 2 đèn).")
    rb.add_bullet("Tab Giọng nói (VoiceScreenTab & VoiceBottomSheet): ", "Thu âm PCM 16 kHz trực tiếp bằng AudioRecord, phát luồng phản hồi Aoede 24 kHz qua AudioTrack với độ trễ thấp, hiển thị hội thoại tiếng Việt trực tiếp và hỗ trợ lệnh tùy chỉnh xác nhận 1 lần.")
    rb.add_bullet("Tab Tài khoản & Quét QR (AccountScreenTab, QrScannerScreen, ForgotPasswordScreen): ", "Hiển thị vai trò Cấp 1/2/3, đồng hồ đếm ngược thời hạn phiên khách, cấu hình địa chỉ máy chủ cục bộ/từ xa, luồng quên mật khẩu và màn hình quét mã QR động TOTP 10 giây.")

    # ===== 4.4 FIRMWARE ESP8266, NẠP WI-FI LITTLEFS & OFFLINE FSM =====
    rb.add_h2("4.4. Thiết kế Firmware ESP8266, Nạp Wi-Fi LittleFS và Chịu lỗi ngoại tuyến")
    rb.add_para(
        "Firmware đặt tại firmware/esp8266_smarthome/ (esp8266_smarthome.ino cùng bộ thư viện lõi offline_safety_config.h, offline_command_grammar.h, offline_fsm.h) "
        "được biên dịch bằng PlatformIO Core 6.2.0 cho đích nodemcuv2. Ngay trong hàm setup(), firmware thực thi quy trình khởi tạo an toàn boot-strap: "
        "thiết lập PIN_AUDIO_PWM (D3/GPIO0) ở trạng thái trở kháng cao INPUT, ghi sẵn mức HIGH trước khi đặt OUTPUT cho PIN_BEDROOM_LIGHT (D4/GPIO2 Active-LOW) "
        "và ghi sẵn mức LOW cho PIN_ALARM_SIREN (D8/GPIO15) để đảm bảo còi hoàn toàn im lặng và đèn tắt sạch khi vừa cấp nguồn."
    )
    rb.add_para(
        "Thay vì lưu cứng thông tin mạng vào mã nguồn, firmware đọc tệp cấu hình động /wifi_config.json từ phân vùng hệ thống tệp LittleFS trong bộ nhớ Flash 4 MB "
        "ngay khi khởi động. Kịch bản turnkey hardware/flash_and_setup.ps1 tự động hóa trọn gói 3 bước: (1) kiểm tra driver CP2102/CH340 và tự nhận cổng COM USB; "
        "(2) biên dịch và nạp firmware qua PlatformIO; (3) truyền tên Wi-Fi, mật khẩu, địa chỉ IP máy chủ (cổng 8088) và khóa phần cứng qua cổng Serial 115200 baud "
        "(không bao giờ in mật khẩu ra màn hình hay tệp log), lưu vào LittleFS rồi tự chạy kiểm tra SELF_TEST và WIFI_STATUS."
    )
    rb.add_para(
        "Khi mất kết nối Wi-Fi hoặc máy chủ trung tâm không phản hồi, firmware kích hoạt Máy trạng thái ngoại tuyến (Offline FSM — Addendum A1 đến A4) "
        "như minh họa trên Hình 4.2: áp dụng thuật toán thử nối lại theo hàm mũ không chặn (1 s → 2 s → 4 s → ... → 30 s) tránh treo Watchdog; "
        "bật máy chủ web cục bộ ESP8266WebServer cổng 80 (/offline/cmd, /offline/status) chỉ nhận tập lệnh bật/tắt cơ bản (A1, A2); "
        "áp đặt khóa cứng an ninh A3 ngay trong tầng phần cứng — tuyệt đối cấm mở cửa chính (giữ Servo D1 ở 0°) trong mọi trạng thái ngoại tuyến; "
        "duy trì bộ định thời tự bảo vệ tải (tự ngắt máy bơm sau tối đa 120 giây, tự ngắt còi sau 30 giây, tự ngắt Relay 2 loa sau 1,5 giây); "
        "và ngay khi mạng phục hồi, tự động gọi POST /api/hardware/resync (A4) để đẩy mọi thay đổi vật lý ngoại tuyến lên máy chủ trước khi đồng bộ trạng thái mới."
    )
    rb.add_figure(
        sw_dir / "sw_arch_offline_fsm.png",
        "Quy trình nạp Wi-Fi runtime LittleFS qua USB và Máy trạng thái ngoại tuyến (Offline FSM A1–A4)",
        max_width_cm=15.0,
        max_height_cm=8.5,
    )

    # ===== 4.5 THIẾT KẾ MẠCH IN PCB HUB DIY v3 & ĐI DÂY 40 SỢI =====
    rb.add_h2("4.5. Thiết kế bo mạch PCB Hub DIY v3 (KiCad 10.0) và Định tuyến 40 dây nối")
    rb.add_para(
        "Để chấm dứt hoàn toàn tình trạng lỏng dây và sụt áp của bảng cắm breadboard, bo mạch PCB Hub trung tâm DIY v3 "
        "(hardware/kicad/smarthome_hub/smarthome_hub.kicad_pcb) được thiết kế trên KiCad 10.0 theo tiêu chuẩn một lớp đồng đáy (1-layer B.Cu) "
        "phù hợp cả gia công ủi nhiệt/ăn mòn DIY tại phòng thí nghiệm lẫn đặt xưởng PCB chuyên nghiệp. Kích thước bo mạch được chuẩn hóa 100,0 × 80,0 × 1,6 mm "
        "với 4 lỗ định vị góc đường kính 3,2 mm (bước 90,0 × 70,0 mm) khớp chính xác chốt đàn hồi trên vỏ nhà in 3D."
    )
    rb.add_para(
        "Tất cả 15 đầu nối ngoại vi (2 domino vít 5,08 mm J1/J2 chịu dòng lớn cho nguồn 5V và máy bơm, cùng 13 thanh rào 2,54 mm J3–J15) "
        "được bố trí dọc theo 4 mép bo mạch theo đúng hướng vật lý đi tới từng phòng trong mô hình nhà nhằm rút ngắn chiều dài bó dây. "
        "Chỉ cần 7 dây nhảy mặt trên (JP1–JP7) để hoàn thiện toàn bộ định tuyến một lớp với khe hở đồng tối thiểu >= 0,60 mm, đạt kết quả kiểm tra "
        "0 lỗi ERC trên sơ đồ nguyên lý và 0 lỗi DRC trên mạch in. Bảng 4.3 tổng hợp 40 sợi dây vật lý chuẩn (36 dây từ Hub J1–J15 + 4 dây liên module) "
        "và Bảng 4.4 tóm tắt thông số thiết kế bo mạch PCB."
    )

    rb.add_table(
        "Tóm tắt 40 dây nối vật lý chuẩn (W01–W40) và chiều dài định tuyến 3D thực tế (+18% dự phòng)",
        ["Nhóm dây (Mã)", "Cổng Hub ↔ Module", "Số dây", "Quy chuẩn màu dây chính", "Dài min–max (cm)", "Cỡ dây mua chuẩn"],
        [
            ("Nguồn tổng (W01–W02)", "J1 ↔ Nguồn 5V 2A DC-022", "2", "Đỏ (+5V), Đen (GND)", "9,10 – 9,58", "22AWG (10 cm)"),
            ("Cửa chính SG90 (W03–W05)", "J3 ↔ Servo SG90 (D1)", "3", "Cam (PWM), Đỏ (+5V), Đen (GND)", "18,24 – 18,35", "Dupont 1×3 (20 cm)"),
            ("Đèn phòng khách (W06–W07)", "J4 ↔ LED 5mm PK (D0)", "2", "Vàng (Anode R1), Đen (GND)", "20,72 – 21,16", "Dupont 1×2 (30 cm)"),
            ("Đèn phòng ngủ (W08–W09)", "J5 ↔ LED 5mm PN (D4)", "2", "Tím (+3V3 R2), Trắng (D4)", "27,45 – 27,48", "Dupont 1×2 (30 cm)"),
            ("Relay 1 & Bơm 5V (W10–W16)", "J7, J8, J2 ↔ Relay 1 & Bơm", "7", "Đỏ, Đen, Xanh lá (D6), Vàng (NO)", "7,89 – 26,45", "10 / 20 / 30 cm"),
            ("Còi báo động (W17–W18)", "J6 ↔ Buzzer TMB12A05 (D8)", "2", "Đỏ (+5V), Cam (Q1.C)", "25,41 – 25,81", "Dupont 1×2 (30 cm)"),
            ("Relay 2, PAM8403 & Loa (W19–W29)", "J9–J12 ↔ Rly2, PAM8403, Loa", "11", "Đỏ, Đen, Xanh lơ (D7), Trắng (D3), Vàng/Nâu (BTL)", "3,84 – 18,75", "10 / 20 cm"),
            ("Cảm biến DHT11 (W30–W32)", "J13 ↔ DHT11 (D2, 3,3V)", "3", "Đỏ (+3V3), Xanh dương (DATA), Đen", "19,15 – 20,05", "20 / 30 cm"),
            ("Cảm biến đất (W33–W37)", "J14 ↔ LM393 ↔ YL-69 (A0)", "5", "Đỏ (+3V3), Đen, Xanh lá (AO), Vàng/Cam", "13,40 – 26,36", "20 / 30 cm"),
            ("Cảm biến KY-037 (W38–W40)", "J15 ↔ KY-037 (D5, 3,3V)", "3", "Đỏ (+3V3), Đen, Vàng (DO)", "11,22 – 11,80", "Dupont 1×3 (20 cm)"),
            ("TỔNG HỆ THỐNG (W01–W40)", "15 cổng Hub + 2 cặp liên module", "40", "40/40 dây <= 30,0 cm (Tổng 654,99 cm)", "3,84 – 27,48", "10×10cm · 18×20cm · 12×30cm"),
        ],
        col_widths_cm=[3.2, 3.4, 1.1, 3.6, 2.0, 2.2],
        font_pt=9.2,
        center_cols=(2, 4),
    )

    rb.add_table(
        "Thông số kỹ thuật thiết kế bo mạch PCB Hub trung tâm DIY v3 (KiCad 10.0)",
        ["Thông số thiết kế PCB", "Giá trị đạt được", "Ghi chú kỹ thuật & Tiêu chuẩn kiểm tra"],
        [
            ("Kích thước & Độ dày vật liệu", "100,0 × 80,0 × 1,6 mm (FR4)", "Khớp khít khay giữ SUP06 trong khoang kỹ thuật vỏ in 3D."),
            ("Số lớp đồng & Gia công", "1 lớp đáy (B.Cu) + 7 dây nhảy JP1–JP7", "Tối ưu cho ăn mòn thủ công DIY (xuất PDF 1:1 lật gương) hoặc đặt xưởng."),
            ("Tổng số footprint trong BOM", "51 footprints (47 linh kiện hàn + 4 lỗ M3)", "Gồm U1–U2, J1–J15, R1–R10, Q1, C1–C9, D1–D3, JP1–JP7, H1–H4."),
            ("Khe hở đồng & Đường nguồn", "Clearance >= 0,60 mm; đường nguồn rộng", "Đảm bảo an toàn dòng đỉnh Servo SG90 + Bơm 5V và dễ hàn tay."),
            ("Kiểm tra ERC (Nguyên lý) & DRC (PCB)", "0 lỗi ERC / 0 lỗi DRC / 0 dây chưa nối", "Xác minh tự động bằng KiCad 10.0 CLI trước khi xuất bản vẽ."),
            ("Chính sách bảng cắm Breadboard", "0 breadboard (100% PCB-Direct)", "Loại bỏ hoàn toàn breadboard và toàn bộ chân [NC] được ghi chú rõ."),
        ],
        col_widths_cm=[4.2, 4.8, 6.5],
        font_pt=9.8,
    )

    rb.add_figure(sw_dir / "sw_kicad_harness.png", "Sơ đồ bó dây cắm ngoại vi hệ thống xuất từ KiCad 10.0", max_width_cm=14.6, max_height_cm=9.5)
    rb.add_figure(demo_dir / "kicad_2d_copper_layout.png", "Bố trí đường mạch đồng lớp đáy (B.Cu) bo mạch PCB Hub DIY v3 (100 × 80 mm)", max_width_cm=12.5, max_height_cm=10.5)
    rb.add_figure(demo_dir / "kicad_drill_map.png", "Bản đồ khoan lỗ và vị trí chân linh kiện bo mạch PCB Hub DIY v3", max_width_cm=14.5, max_height_cm=9.8)
    rb.add_figure(demo_dir / "kicad_3d_iso.png", "Mô hình 3D bo mạch PCB Hub DIY v3 góc nhìn đẳng giác", max_width_cm=14.0, max_height_cm=9.0)
    rb.add_figure(demo_dir / "kicad_3d_top.png", "Mô hình 3D bo mạch PCB Hub DIY v3 góc nhìn từ trên xuống", max_width_cm=14.0, max_height_cm=9.0)
    rb.add_figure(demo_dir / "kicad_drc_result.png", "Kết quả kiểm tra quy tắc thiết kế KiCad DRC đạt 0 lỗi và 0 chân chưa đi dây", max_width_cm=14.2, max_height_cm=9.2)
    rb.add_figure(demo_dir / "pcb_modules_wired_top.png", "Bố trí không gian 3D toàn bộ cụm PCB Hub và 14 module đã đi dây nhìn từ trên xuống", max_width_cm=14.0, max_height_cm=9.2)

    # ===== 4.6 THIẾT KẾ CƠ KHÍ MÔ HÌNH NHÀ IN 3D LẮP MỘNG (AGYHW14) =====
    rb.add_h2("4.6. Thiết kế cơ khí mô hình nhà in 3D lắp mộng tối ưu giảm nhựa (HW14)")
    rb.add_para(
        "Toàn bộ vỏ mô hình ngôi nhà thông minh được thiết kế tham số bằng FreeCAD 1.1.4 (hardware/in 3 d/scripts/) theo nguyên tắc cơ khí "
        "lắp mộng tự khóa 100% — không sử dụng bất kỳ ốc vít kim loại hay keo dán nào — giúp dễ dàng tháo lắp khi bảo trì mạch điện và vận chuyển bảo vệ đồ án. "
        "Hệ thống sử dụng 7 chuẩn khe hở dung sai đã tinh chỉnh cho máy in FDM đầu phun 0,4 mm vật liệu PLA: khớp mộng đuôi én tách mảnh tấm lớn (0,20 mm), "
        "mộng răng lược ghép tường–sàn (0,25 mm), kẹp chữ U khóa góc 90° (0,20 mm), chốt vuông ép khít mortise-and-tenon (0,15 mm), chốt đàn hồi chẻ đôi "
        "snap-fit giữ PCB và Relay (0,20 mm kèm gai khóa 0,25 mm), rãnh trượt cạnh bo mạch (0,20 mm) và trục xoay bản lề cửa chính đồng trục (0,30 mm)."
    )
    rb.add_para(
        "Đặc biệt, ở phiên bản tối ưu giảm nhựa HW14, ba kỹ thuật kết cấu được áp dụng đồng thời nhưng vẫn bảo toàn nguyên vẹn độ cứng vững: "
        "(1) Loại bỏ hoàn toàn 9 mã nội thất trang trí không phục vụ điện tử (FUR01–FUR09, 20 bản thể) và 10 lỗ mộng sàn tương ứng; "
        "(2) Làm mỏng vùng lòng các tấm sàn/tường lớn P01A, P01B, P02–P06 từ 3,0 mm xuống 2,2 mm (giữ đáy Z=0 phẳng hoàn toàn để đạt 0% support) "
        "kèm hệ gân tăng cứng 3,0 mm có nhịp không gân tối đa <= 85,0 mm; "
        "(3) Khoét 288 ô tổ ong lục giác kích thước 28 mm bám biên tại vùng không chịu lực (gân tối thiểu 3,2 mm, lề mép tối thiểu 6,5 mm), "
        "trong khi giữ kín tuyệt đối 100% khoang điện Relay/PSU và bể nước liền khối SUP15_WATER_TANK_LINER (cấu hình 4 lớp đáy 0,8 mm + 3 thành chống thấm không cần chất trám)."
    )
    rb.add_para(
        "Cụm cửa chính P08_DOOR_LEAF (khối lượng 17,6 g, rộng 56,0 mm) sử dụng cơ cấu dẫn động trực tiếp đồng trục (coaxial top-jamb direct-drive) "
        "đặt Servo SG90 trên kệ P07_SERVO_SHELF khóa bằng ngàm SUP11, nối thẳng trục bản lề SUP10 qua ngàm chữ U SUP10B giúp quét mượt góc 0°–90° "
        "với độ dư mô-men xoắn đạt 14,56× (vượt xa ngưỡng thiết kế >= 5×). Toàn bộ 51 chi tiết duy nhất (83 bản thể vật lý) được thuật toán 2D MaxRects "
        "xếp tự động vào đúng 16 bàn in khổ 180 × 200 × 250 mm (vùng khả dụng 170 × 190 × 245 mm) với thông số cắt lớp nhúng sẵn ngay trong từng tệp .3mf "
        "(lớp 0,20 mm, ruột 9% Gyroid, 2 thành cho tấm lớn và 3 thành cho 23 chi tiết khớp/ngàm/cửa chịu lực). Bảng 4.5 liệt kê chi tiết 16 bàn in."
    )

    rb.add_table(
        "Phân bổ 16 bàn in 3D PLA (180 × 200 × 250 mm, 9% Gyroid, 0% support, tổng 660,64 g)",
        ["Bàn in (.3mf)", "SL", "Chi tiết chính trên bàn", "Khung (mm)", "Thời gian in", "Nhựa (g)", "Manifold"],
        [
            ("PLATE01_base", "1", "P01A_piece3of3", "156,5×181,9×3,0", "5g 50p 30s", "51,20", "ĐẠT"),
            ("PLATE02_base", "1", "P01A_piece1of3", "149,9×181,9×3,0", "5g 32p 23s", "49,31", "ĐẠT"),
            ("PLATE03_base_tech", "5", "P01A_p2, P15_p1, SUP07, SUP14, SUP16", "169,4×181,9×16,5", "6g 42p 14s", "58,47", "ĐẠT"),
            ("PLATE04_base_garden", "3", "P01B_p5, P12_GARDEN_FRONT, P07_SERVO_SHELF", "169,4×189,4×13,0", "4g 09p 03s", "37,71", "ĐẠT"),
            ("PLATE05_base_garden", "7", "P01B_p6, P11, SUP04×4, SUP01", "169,5×189,4×14,0", "5g 00p 52s", "49,76", "ĐẠT"),
            ("PLATE06_base", "2", "P01B_piece3of6, P01B_piece1of6", "169,5×185,4×3,0", "2g 56p 14s", "26,67", "ĐẠT"),
            ("PLATE07_base_garden", "2", "P01B_piece4of6, P14_SOIL_BRIDGE", "131,4×167,0×3,0", "2g 45p 19s", "25,18", "ĐẠT"),
            ("PLATE08_walls_mounts", "11", "P05_p2, SUP06 Hub PCB, P17×2, SUP07, SUP02×6", "170,0×190,0×13,6", "6g 32p 18s", "57,48", "ĐẠT"),
            ("PLATE09_walls_mounts", "12", "P06, P05_p3, SUP11, SUP18, SUP03×3, SUP10B, SUP05B×4", "169,6×190,0×12,5", "5g 07p 03s", "44,31", "ĐẠT"),
            ("PLATE10_walls_tech", "14", "P02_p3, P15_p2, SUP08, SUP03×3, SUP17×2, SUP05×2, SUP05B×4", "170,0×189,5×9,0", "4g 57p 29s", "43,27", "ĐẠT"),
            ("PLATE11_walls_garden", "6", "P03_WALL_LEFT, P09, SUP09, SUP10×2, SUP05", "170,0×190,0×12,0", "4g 22p 45s", "37,77", "ĐẠT"),
            ("PLATE12_walls_mounts", "9", "P04_WALL_RIGHT, P05_p1, SUP13, SUP01B, SUP03×2, SUP05, SUP05B×2", "170,0×190,0×12,0", "4g 31p 53s", "40,42", "ĐẠT"),
            ("PLATE13_walls_garden", "4", "P02_p1, P13_GARDEN_BACK, SUP12, SUP01", "162,0×187,0×12,0", "3g 54p 18s", "35,76", "ĐẠT"),
            ("PLATE14_walls_base", "2", "P01B_piece2of6, P02_piece2of3", "169,4×189,4×3,0", "3g 31p 50s", "32,49", "ĐẠT"),
            ("PLATE15_tech_garden", "2", "P16_PCB_PLATE, P10_WATER_DIVIDER", "130,0×171,0×3,0", "3g 11p 21s", "28,77", "ĐẠT"),
            ("PLATE16_walls_mounts", "2", "SUP15_WATER_TANK_LINER (4 đáy), P08_DOOR_LEAF", "119,0×107,0×45,0", "4g 18p 17s", "42,07", "ĐẠT"),
            ("TỔNG (16 BÀN IN)", "83", "Đủ 51 chi tiết duy nhất (0 nội thất, 221,50 m sợi)", "<= 170×190×45", "73g 23p 49s", "660,64", "16/16"),
        ],
        col_widths_cm=[3.0, 0.8, 4.9, 2.5, 1.9, 1.2, 1.2],
        font_pt=8.8,
        center_cols=(1, 3, 4, 5, 6),
    )

    rb.add_figure(demo_dir / "in3d_exploded_v2.png", "Hình chiếu phân rã 3D bộ 51 chi tiết vỏ nhà và giá đỡ lắp mộng tự khóa v2", max_width_cm=14.4, max_height_cm=9.4)
    rb.add_figure(demo_dir / "in3d_joint_closeup_mong.png", "Bản vẽ kỹ thuật cận cảnh khớp mộng đuôi én, răng lược và cấu trúc tổ ong lục giác 28 mm", max_width_cm=14.5, max_height_cm=9.6)
    rb.add_figure(demo_dir / "in3d_pcb_module_fit_3d.png", "Cận cảnh 3D cụm lắp đặt Hub PCB, hai Relay và PAM8403 bằng chốt đàn hồi snap-fit", max_width_cm=13.8, max_height_cm=9.0)
    rb.add_figure(demo_dir / "in3d_pcb_module_fit_drawing.png", "Bản vẽ kỹ thuật kiểm chứng khe hở lắp khít giữa bo mạch PCB Hub và các module", max_width_cm=14.5, max_height_cm=9.6)
    rb.add_figure(demo_dir / "in3d_servo_door_closeup.png", "Cận cảnh 3D cụm cửa chính P08 dẫn động trực tiếp đồng trục bằng Servo SG90", max_width_cm=13.8, max_height_cm=9.0)
    rb.add_figure(demo_dir / "prusaslicer_gcode_gyroid.png", "Kiểm chứng đường chạy G-code trên PrusaSlicer 2.9.7 với ruột 9% Gyroid và 0% support", max_width_cm=14.8, max_height_cm=7.2)

    rb.add_h2("4.7. Kết luận Chương 4")
    rb.add_para(
        "Chương 4 đã trình bày trọn vẹn thiết kế và phương án triển khai của hệ thống Smart Home Voice AI xuyên suốt từ tầng đám mây/máy chủ "
        "(FastAPI, SQLite 3NF WAL, RBAC 3 tầng, QR TOTP 10 giây, Gemini 3.8 Live + ServerEchoGuard + 20 công cụ + 2 bể tự động hóa), "
        "tầng ứng dụng (Web 3D Digital Twin, /wokwi PCB-Direct, Android Kotlin/Compose), tầng nhúng (ESP8266 LittleFS Wi-Fi runtime, Offline FSM A1–A4) "
        "đến tầng điện tử và cơ khí (PCB Hub DIY v3 0 ERC/0 DRC, 40 dây <= 30 cm, 16 bàn in 3D PLA 660,64 g). "
        "Chương 5 sẽ trình bày kết quả kết xuất, chạy thử nghiệm đa nền tảng và đánh giá đối chiếu với các chỉ tiêu đặt ra."
    )
