"""Chapter 4: Thiết kế và triển khai (Quy trình vận hành, chức năng chi tiết, ngoại tuyến, giao diện & so sánh)."""

from __future__ import annotations

import pathlib

from .code_excerpts import load_code_excerpt
from .docx_helpers import ReportBuilder


def _embed_listing(rb: ReportBuilder, excerpt_key: str) -> None:
    caption, source_ref, start_line, lines = load_code_excerpt(excerpt_key)
    rb.add_code_listing(
        caption=caption,
        code_lines=lines,
        source_ref=source_ref,
        start_line=start_line,
        font_pt=10.0,
    )


def build_chapter_4(rb: ReportBuilder, assets_dir: pathlib.Path) -> None:
    diag_dir = assets_dir / "diagrams"
    demo_dir = assets_dir / "demo"
    sw_dir = assets_dir / "software"

    rb.add_chapter(4, "THIẾT KẾ VÀ TRIỂN KHAI")
    rb.add_para(
        "Trong Chương 4, em trình bày thiết kế chi tiết và phương án triển khai thực tế của hệ thống nhà thông minh "
        "điều khiển bằng giọng nói tiếng Việt. Nội dung chương đi từ quy trình vận hành tổng thể và luồng xử lý "
        "đầu–cuối của một câu lệnh giọng nói, tiếp đến phân tích cơ chế hoạt động bên trong từng phân hệ chức năng "
        "(giọng nói tự nhiên, điều khiển thiết bị và cơ sở dữ liệu, tự động hóa hai bể và lệnh tùy chỉnh, phân quyền "
        "ba tầng kèm mã QR động, chế độ hoạt động ngoại tuyến), sau đó mô tả giao diện Web 3D, ứng dụng Android, "
        "vỏ mô hình nhà in 3D, và cuối cùng đối chiếu khách quan hệ thống với các sản phẩm nhà thông minh thương mại "
        "phổ biến hiện nay."
    )

    # ===== 4.1 QUY TRÌNH VẬN HÀNH TỔNG THỂ & LUỒNG XỬ LÝ LỆNH GIỌNG NÓI =====
    rb.add_h2("4.1. Quy trình vận hành tổng thể và luồng xử lý lệnh giọng nói")

    rb.add_h3("4.1.1. Quy trình vận hành tổng thể của hệ thống")
    rb.add_para(
        "Toàn bộ hệ thống được tổ chức theo mô hình bốn tầng phối hợp chặt chẽ nhằm bảo đảm tính phản hồi tức thì "
        "trong mạng gia đình và giữ an toàn phần cứng khi mất kết nối mạng. Ở tầng trung tâm, máy chủ điều phối viết "
        "bằng FastAPI kết hợp cơ sở dữ liệu quan hệ SQLite được vận hành trực tiếp trên máy tính xách tay (laptop) "
        "đặt trong mạng nội bộ. Người dùng tương tác với ngôi nhà thông qua giao diện Web 3D trên trình duyệt hoặc "
        "ứng dụng Android cài trên điện thoại; các thiết bị đầu cuối này có thể truy cập máy chủ qua mạng LAN nội bộ "
        "khi ở trong nhà hoặc qua kết nối Internet khi ở bên ngoài."
    )
    rb.add_para(
        "Ở nhánh xử lý hội thoại, máy chủ duy trì kết nối WebSocket song công tới dịch vụ nhận dạng và hội thoại "
        "giọng nói Gemini Live để hiểu tiếng Việt tự nhiên và gọi các hàm công cụ tương ứng. Ở nhánh phần cứng, máy "
        "chủ trao đổi lệnh điều khiển và dữ liệu cảm biến với vi điều khiển NodeMCU ESP8266 gắn trên bo mạch PCB Hub "
        "trung tâm qua giao thức MQTT và HTTP trong mạng LAN. Từ bo mạch PCB Hub, tín hiệu điện áp 5V và 3,3V được "
        "phân phối ổn định tới 6 thiết bị chấp hành (cửa chính dùng Servo SG90, đèn phòng khách, đèn phòng ngủ, máy "
        "bơm tưới cây, còi báo động, nguồn mạch loa PAM8403) và thu nhận liên tục dữ liệu từ 3 cảm biến (nhiệt độ và "
        "độ ẩm không khí DHT11, độ ẩm đất YL-69 qua mạch LM393, cảm biến âm thanh KY-037). Khi máy chủ hoặc đường "
        "truyền mạng gián đoạn, thiết bị đầu cuối trong cùng mạng LAN vẫn có thể gửi lệnh bật/tắt cơ bản trực tiếp "
        "tới máy chủ HTTP cục bộ cổng 80 của ESP8266 theo chế độ dự phòng ngoại tuyến. Hình 4.1 thể hiện sơ đồ khối "
        "vận hành tổng thể của hệ thống."
    )
    rb.add_figure(
        diag_dir / "diag_system_block.png",
        "Sơ đồ khối vận hành tổng thể hệ thống nhà thông minh điều khiển giọng nói",
        max_width_cm=13.4,
        max_height_cm=6.4,
        kind="diagram",
    )

    rb.add_h3("4.1.2. Luồng xử lý đầu–cuối của một câu lệnh giọng nói")
    rb.add_para(
        "Để người dùng có thể ra lệnh bằng tiếng Việt tự nhiên mà vẫn bảo đảm tuyệt đối kỷ luật phân quyền và đồng "
        "bộ trạng thái vật lý, mỗi câu lệnh giọng nói đi qua bảy bước xử lý liên hoàn trên Hình 4.2. Trước hết, "
        "micro trên giao diện Web hoặc ứng dụng Android thu âm tín hiệu tiếng nói chuẩn PCM 16 kHz, 16-bit đơn kênh, "
        "chia đều từng khung 20 ms và truyền qua WebSocket lên máy chủ. Tại đây, bộ lọc chống dội âm phía máy chủ "
        "(ServerEchoGuard) kết hợp phát hiện hoạt động tiếng nói (VAD) loại bỏ tiếng vọng phát ra từ loa để tránh "
        "trợ lý tự nghe nhầm giọng của chính mình."
    )
    rb.add_para(
        "Tiếp theo, luồng âm thanh sạch được chuyển tiếp tới dịch vụ Gemini Live. Mô hình nhận dạng tiếng nói tiếng "
        "Việt theo thời gian thực, hiểu ý định ngữ cảnh và lựa chọn hàm công cụ phù hợp (chẳng hạn control_device, "
        "schedule_action hoặc gọi lệnh tùy chỉnh) kèm tham số thiết bị đã chuẩn hóa. Nếu câu lệnh thuộc nhánh lệnh "
        "tùy chỉnh, hệ thống tách làm hai trường hợp rõ ràng: khi người dùng tạo hoặc chỉnh sửa một lệnh mới, máy "
        "chủ lưu tạm vào hàng đợi chờ và hỏi xác nhận đúng một lần duy nhất; còn khi gọi lại lệnh đã lưu từ các lần "
        "sau, bộ đối khớp cụm từ kích hoạt sẽ bỏ qua bước hỏi lại và chuyển thẳng danh sách thao tác đi thực thi ngay."
    )
    rb.add_para(
        "Trước khi bất kỳ tín hiệu điều khiển nào được phép rời khỏi máy chủ, bước kiểm tra phân quyền RBAC ba tầng "
        "(1/2/3) luôn được thực thi bắt buộc dựa trên phiên đăng nhập thực tế của người dùng, hoàn toàn không phụ "
        "thuộc vào suy luận của mô hình AI. Nếu phiên không đủ quyền (ví dụ Khách Cấp 3 yêu cầu mở cửa chính hoặc "
        "bật còi báo động), máy chủ lập tức chặn yêu cầu với mã HTTP 403, ghi nhận sự kiện từ chối vào nhật ký kiểm "
        "toán và trả câu từ chối tiếng Việt cố định để trợ lý đọc lại. Ngược lại, khi yêu cầu hợp lệ, máy chủ áp "
        "dụng nguyên tắc Actuate-First: gửi ngay lệnh điều khiển xuống ESP8266 qua MQTT hoặc HTTP LAN trước, chờ "
        "xác nhận cập nhật trạng thái vào SQLite WAL và phát sự kiện SSE làm mới tức thì giao diện Web 3D cùng ứng "
        "dụng Android, sau cùng mới để trợ lý phát câu phản hồi tiếng Việt ngắn gọn khớp đúng kết quả vừa thực thi "
        "(ví dụ: \"Đã bật đèn phòng khách.\")."
    )
    rb.add_figure(
        diag_dir / "diag_voice_e2e.png",
        "Luồng xử lý đầu–cuối của một câu lệnh giọng nói tiếng Việt kèm nhánh lệnh tùy chỉnh và phân quyền RBAC",
        max_width_cm=13.4,
        max_height_cm=6.4,
        kind="diagram",
    )

    # ===== 4.2 THIẾT KẾ VÀ CƠ CHẾ HOẠT ĐỘNG TỪNG CHỨC NĂNG CHÍNH =====
    rb.add_h2("4.2. Thiết kế và cơ chế hoạt động từng chức năng chính")

    # --- 4.2.1 ---
    rb.add_h3("4.2.1. Điều khiển giọng nói tiếng Việt tự nhiên")
    rb.add_para(
        "Phân hệ trợ lý giọng nói được triển khai trong cụm mô-đun backend/live/ (gồm gemini_bridge.py, "
        "tool_dispatcher_mixin.py, prompt_builder.py và echo_and_speech_guard.py). Máy chủ thiết lập cầu nối "
        "WebSocket song công toàn phần giữa trình duyệt hoặc điện thoại với Gemini Live API thông qua thư viện "
        "google-genai. Luồng âm thanh đầu vào chuẩn PCM 16 kHz (320 mẫu tương đương 640 byte mỗi khung 20 ms) được "
        "đẩy liên tục theo thời gian thực, trong khi luồng âm thanh phản hồi từ giọng đọc tiếng Việt Aoede có tần số "
        "lấy mẫu 24 kHz PCM 16-bit được trả về để phát ngay qua AudioWorklet trên Web hoặc AudioTrack trên Android."
    )
    rb.add_para(
        "Trong thử nghiệm hội thoại thực tế trên loa điện thoại và laptop, hiện tượng loa phát câu trả lời rồi lọt "
        "ngược vào micro rất dễ làm mô hình hiểu nhầm thành lệnh mới hoặc lặp vô hạn. Em giải quyết bài toán này "
        "bằng lớp bảo vệ ServerEchoGuard đặt ngay trên máy chủ: trong suốt thời gian trợ lý đang phát âm thanh cộng "
        "thêm khoảng đuôi 400 ms và cửa sổ đối chiếu bản ghi 8 giây, hệ thống theo dõi mức năng lượng RMS cùng hệ "
        "số tương quan đường bao tín hiệu để triệt tiêu tiếng vọng, nhưng vẫn nhận biết khi người dùng chủ động nói "
        "đè vào (barge-in) với biên độ vượt trội để dừng câu trả lời hiện tại và nghe lệnh mới. Song song đó, cơ chế "
        "tái kết nối không rơi khung âm thanh (Zero-Drop Reconnect) đệm các khung PCM đang nói vào hàng đợi bộ nhớ "
        "khi kết nối thượng nguồn gặp gián đoạn ngắn, giúp câu lệnh không bị đứt giữa chừng."
    )
    rb.add_para(
        "Về phong cách phản hồi và kỷ luật thực thi, hệ thống kết hợp mô hình Actuate-First với bộ lọc văn bản "
        "sanitize_spoken_vietnamese_text nhằm loại bỏ hoàn toàn tên hàm, chuỗi JSON hay ký hiệu định dạng kỹ thuật "
        "trước khi hiển thị phụ đề và phát âm. Nhờ vậy, câu trả lời của trợ lý luôn ngắn gọn, tự nhiên, 100% tiếng "
        "Việt và chỉ xác nhận sau khi lệnh đã thực sự đi qua tầng kiểm tra quyền và tầng điều khiển thiết bị. Bảng "
        "4.1 tóm tắt các nhóm hàm công cụ chính được cấp cho trợ lý giọng nói, và Đoạn mã 4.1 trích trực tiếp phần "
        "chuẩn hóa định danh thiết bị kèm kiểm tra phân quyền RBAC trong bộ điều phối công cụ control_device."
    )
    rb.add_table(
        "Danh mục các nhóm hàm công cụ (Function Declarations) cấp cho dịch vụ giọng nói Gemini Live",
        ["Tên hàm công cụ", "Tham số cốt lõi", "Hành vi thực thi & Kiểm tra RBAC"],
        [
            (
                "control_device",
                "device_id, action",
                "Bật/tắt/mở/đóng ngay 1 trong 6 thiết bị hoặc nhóm all_lights/all_devices; kiểm tra quyền Cấp 1/2/3 trên máy chủ trước khi gửi lệnh.",
            ),
            (
                "schedule_action",
                "device_id, action, thời gian trễ / giờ đồng hồ, repeat",
                "Đặt bộ hẹn giờ đếm ngược hoặc lịch lặp theo chu kỳ (once/hourly/daily/weekly/monthly) vào bể TimersPool.",
            ),
            (
                "update_timer",
                "device_id, thao tác sửa/hủy, mốc thời gian mới",
                "Điều chỉnh giờ kích hoạt hoặc hủy bỏ hẹn giờ đang chờ mà không cần xóa tạo lại thủ công.",
            ),
            (
                "set_if_else_rule",
                "điều kiện cảm biến / thiết bị, chuỗi hành động, cooldown",
                "Tạo luật tự động hóa phản ứng cảm biến hoặc trạng thái liên động lưu vào bể RulesPool.",
            ),
            (
                "create_alias_rule & confirm_pending_action",
                "phrase, steps / quyết định xác nhận",
                "Dạy lệnh tùy chỉnh mới qua bước hỏi xác nhận đúng 1 lần, lưu vào custom_commands sau khi người dùng đồng ý.",
            ),
            (
                "execute_alias_rule",
                "phrase",
                "Đối khớp cụm từ lệnh tùy chỉnh đã lưu và thực thi ngay chuỗi thiết bị mà không hỏi xác nhận lại (chặn đối với Cấp 3).",
            ),
            (
                "read_sensors / query_knowledge_rag",
                "phạm vi thiết bị / câu hỏi tiếng Việt",
                "Đọc số liệu DHT11, độ ẩm đất, âm thanh KY-037, trạng thái lịch hẹn và tra cứu nhật ký tri thức.",
            ),
        ],
        col_widths_cm=[3.9, 4.4, 7.2],
        font_pt=9.6,
    )
    _embed_listing(rb, "be_voice_control")

    # --- 4.2.2 ---
    rb.add_h3("4.2.2. Điều khiển thiết bị và giám sát cảm biến")
    rb.add_para(
        "Máy chủ trung tâm khởi chạy bằng Uvicorn ASGI trên cổng cục bộ 8088 tại điểm vào backend/server.py và "
        "được phân tách rõ ràng thành các router FastAPI theo từng miền nghiệp vụ: routes_devices.py đảm nhiệm điều "
        "khiển 6 thiết bị chấp hành, tiếp nhận dữ liệu cảm biến và đồng bộ phần cứng ESP8266; routes_auth.py xử lý "
        "đăng nhập, đăng ký, mã OTP qua email, quản lý tài khoản và mã PIN Chủ nhà; routes_qr.py và routes_guest.py "
        "phụ trách vòng đời mã QR động mời khách; routes_automation.py quản lý hai bể tự động hóa cùng lệnh tùy "
        "chỉnh; và routes_logs.py phục vụ truy vấn nhật ký kiểm toán cùng cơ sở tri thức RAG. Bảng 4.2 tổng hợp "
        "các nhóm giao diện lập trình chính của máy chủ."
    )
    rb.add_table(
        "Danh mục các nhóm giao diện lập trình API REST, WebSocket và SSE của máy chủ FastAPI",
        ["Nhóm API", "Đường dẫn tiêu biểu", "Tầng quyền", "Chức năng nghiệp vụ chính"],
        [
            (
                "Hệ thống & Sức khỏe",
                "GET /api/version, GET /api/health",
                "Công khai",
                "Trả thông tin phiên bản, tình trạng máy chủ và trạng thái kết nối bo mạch ESP8266.",
            ),
            (
                "Thiết bị & Cảm biến",
                "GET /api/state, POST /api/device/{id}",
                "Cấp 1 / 2 / 3 (lọc)",
                "Trả snapshot thiết bị lọc theo đúng phiên và thực thi bật/tắt/mở/đóng sau kiểm tra RBAC.",
            ),
            (
                "Đồng bộ Phần cứng",
                "POST /api/hardware/resync, /api/sound_sensor",
                "Khóa phần cứng / LAN",
                "Nhận telemetry DHT11, độ ẩm đất A0, cảm biến âm thanh D5 và đồng bộ ngược sau khi mất mạng.",
            ),
            (
                "Xác thực & Tài khoản",
                "POST /api/auth/login, /otp, /users",
                "Công khai / Cấp 1",
                "Đăng nhập mật khẩu/OTP, quản lý danh sách email thành viên và bảo vệ PIN Chủ nhà.",
            ),
            (
                "Mã QR động Khách",
                "POST /api/qr/generate, /api/qr/claim",
                "Cấp 1 / Khách",
                "Sinh mã QR đổi chữ ký mỗi 10 giây, xác thực bắt tay 180 giây và thu hồi phiên khách tức thì.",
            ),
            (
                "Tự động hóa & Lệnh",
                "GET/POST /api/automation/*, /schedules",
                "Cấp 1 / Cấp 2",
                "Quản lý TimersPool, RulesPool và danh sách lệnh tùy chỉnh custom_commands.",
            ),
            (
                "Nhật ký & Thời gian thực",
                "GET /api/logs, WS /ws/live, GET /api/events",
                "Cấp 1 / Phiên hợp lệ",
                "Truy vấn lịch sử kiểm toán audit_logs, kênh thoại Gemini Live và luồng đồng bộ SSE.",
            ),
        ],
        col_widths_cm=[2.8, 4.3, 2.5, 5.9],
        font_pt=9.6,
    )
    rb.add_para(
        "Toàn bộ dữ liệu bền vững được lưu trữ trong cơ sở dữ liệu SQLite chuẩn hóa dạng chuẩn 3 (3NF) do mô-đun "
        "backend/db_migrations.py tự động khởi tạo và nâng cấp lược đồ. Em bật đồng thời hai tùy chọn cốt lõi là "
        "PRAGMA journal_mode = WAL (Write-Ahead Logging) để nhiều yêu cầu đọc trạng thái và kênh SSE diễn ra song "
        "song với giao dịch ghi nhật ký mà không phát sinh lỗi khóa tệp, và PRAGMA foreign_keys = ON để bảo đảm "
        "toàn vẹn khóa ngoại. Hơn 20 bảng dữ liệu được quy hoạch thành bốn cụm nghiệp vụ rõ ràng như trên Hình 4.3: "
        "cụm danh tính và bảo mật (roles, users, user_sessions, invites, otp_challenges, trusted_devices), cụm "
        "thiết bị và trạng thái cảm biến (devices, device_state, system_state_meta), cụm tự động hóa và lệnh tùy "
        "chỉnh (timers_pool, schedules, rules_pool, compound_automation_rules, custom_commands, "
        "pending_confirmations) và cụm nhật ký kiểm toán cùng tri thức (audit_logs, knowledge_rag, durable_kv)."
    )
    rb.add_figure(
        sw_dir / "sw_arch_db_erd.png",
        "Sơ đồ thực thể liên kết (ERD) cơ sở dữ liệu SQLite chuẩn hóa 3NF ở chế độ WAL",
        max_width_cm=14.0,
        max_height_cm=7.0,
        kind="diagram",
    )
    rb.add_para(
        "Mọi thay đổi trạng thái thiết bị hoặc số liệu cảm biến mới từ DHT11, YL-69 và KY-037 sau khi cập nhật "
        "vào lõi điều phối đều đi qua trung tâm phát sóng thời gian thực backend/realtime_hub.py. Trung tâm này "
        "phát đồng thời sự kiện qua Server-Sent Events (SSE) tới tất cả trình duyệt Web 3D và ứng dụng Android đang "
        "mở, nhờ đó trạng thái hiển thị đồng bộ gần như tức thì mà không cần tải lại trang. Đoạn mã 4.2 minh họa "
        "hàm xử lý yêu cầu điều khiển thiết bị trên FastAPI: mọi thao tác đều truyền đầy đủ tầng quyền và thông tin "
        "người gọi xuống lõi xử lý (bypass_rbac=False), rồi chỉ trả về bản chụp snapshot đã lọc đúng theo quyền của "
        "phiên đó."
    )
    _embed_listing(rb, "be_fastapi_device")

    # --- 4.2.3 ---
    rb.add_h3("4.2.3. Tự động hóa, hẹn giờ, lịch lặp và lệnh tùy chỉnh")
    rb.add_para(
        "Trong thực tế vận hành nhà thông minh, các tác vụ theo thời gian (ví dụ \"5 phút nữa tắt đèn phòng khách\" "
        "hoặc \"6 giờ sáng mỗi ngày bật máy bơm\") và các quy tắc phản ứng theo cảm biến (ví dụ \"nếu độ ẩm đất "
        "dưới 40% thì bật máy bơm tưới cây\") có vòng đời và cơ chế kích hoạt rất khác nhau. Nếu gộp chung vào một "
        "bảng duy nhất sẽ dễ phát sinh xung đột khi người dùng yêu cầu hủy lịch hẹn hoặc chỉnh sửa luật cảm biến. "
        "Vì vậy, bộ máy tự động hóa (backend/rule_engine.py) được thiết kế tách biệt thành hai bể độc lập: "
        "TimersPool (backend/engine/timers_pool.py) chuyên quản lý hẹn giờ đếm ngược một lần và lịch đồng hồ lặp "
        "(một lần, theo giờ, hàng ngày, hàng tuần, hàng tháng) với khả năng cập nhật hoặc hủy tức thì; còn RulesPool "
        "(backend/engine/rules_pool.py kết hợp compound_automation_rules) chuyên đánh giá điều kiện cảm biến hoặc "
        "tổ hợp đa điều kiện có kèm thời gian nghỉ chống bật/tắt liên tục (cooldown)."
    )
    rb.add_para(
        "Bên cạnh hẹn giờ và luật cảm biến, tính năng lệnh tùy chỉnh cho phép Chủ nhà và Thành viên tự định nghĩa "
        "khẩu lệnh ngữ cảnh theo thói quen riêng, chẳng hạn \"Từ giờ khi tôi nói chế độ đi ngủ thì tắt tất cả đèn "
        "và đóng cửa chính\". Để vừa tránh tạo nhầm lệnh do nghe sai, vừa không gây phiền hà khi sử dụng hàng ngày, "
        "em áp dụng quy tắc xác nhận đúng một lần: khi tạo mới hoặc chỉnh sửa một lệnh tùy chỉnh, hàm "
        "prepare_pending_mutation lưu bản nháp vào bảng pending_confirmations và để trợ lý đọc tóm tắt chuỗi thiết "
        "bị hỏi người dùng xác nhận một lần duy nhất. Ngay sau khi người dùng đồng ý, lệnh được lưu cố định vào "
        "bảng custom_commands; từ mọi lần gọi về sau, hàm execute_alias_rule đối khớp cụm từ kích hoạt và thực thi "
        "ngay toàn bộ chuỗi hành động mà không hỏi xác nhận lại. Đối với Khách Cấp 3, cả quyền tạo lẫn quyền chạy "
        "lệnh tùy chỉnh đều bị chặn ở tầng máy chủ. Đoạn mã 4.3 trích trực tiếp phần khởi tạo bản nháp xác nhận 1 "
        "lần và nhánh đối khớp thực thi lệnh tùy chỉnh đã lưu."
    )
    _embed_listing(rb, "be_custom_cmd_noreconfirm")

    # --- 4.2.4 ---
    rb.add_h3("4.2.4. Phân quyền 3 tầng (1/2/3) và mời khách bằng mã QR động")
    rb.add_para(
        "An ninh truy cập là một yêu cầu trọng tâm khi nhiều đối tượng cùng sử dụng chung ngôi nhà. Hệ thống áp "
        "dụng mô hình kiểm soát truy cập theo vai trò (RBAC) ba tầng được khóa cứng trên máy chủ tại mô-đun "
        "backend/auth/tier_permissions.py, trong đó chỉ số tầng càng nhỏ tương ứng với thẩm quyền càng cao:"
    )
    rb.add_bullet(
        "Tầng 1 — Chủ nhà (ADMIN): ",
        "Có toàn quyền điều khiển đủ 6 thiết bị chấp hành (bao gồm hai thiết bị nhạy cảm là cửa chính và còi báo "
        "động), quản trị tài khoản thành viên, thiết lập mã PIN Chủ nhà, phát hành và thu hồi mã QR mời khách, "
        "tạo/sửa mọi lịch tự động hóa và xem toàn bộ nhật ký kiểm toán audit_logs.",
    )
    rb.add_bullet(
        "Tầng 2 — Thành viên gia đình (MEMBER): ",
        "Được phép điều khiển 4 thiết bị sinh hoạt (đèn phòng khách, đèn phòng ngủ, máy bơm tưới cây, nguồn mạch "
        "loa), đặt hẹn giờ và quản lý lệnh tùy chỉnh cá nhân, nhưng bị chặn thao tác đối với cửa chính, còi báo "
        "động, quản trị người dùng và nhật ký hệ thống.",
    )
    rb.add_bullet(
        "Tầng 3 — Khách (CHILD_GUEST): ",
        "Chỉ được phép bật/tắt đúng 2 thiết bị chiếu sáng (đèn phòng khách và đèn phòng ngủ) qua giao diện hoặc "
        "giọng nói cơ bản; mọi yêu cầu mở cửa, bật bơm, bật còi, tạo tự động hóa hay chạy lệnh tùy chỉnh đều bị "
        "máy chủ từ chối với mã HTTP 403 và ẩn hoàn toàn các thẻ thiết bị ngoài quyền hạn trên giao diện.",
    )
    rb.add_para(
        "Đoạn mã 4.4 thể hiện hàm kiểm tra quyền điều khiển can_control_device và hàm lọc danh sách thiết bị hiển "
        "thị devices_visible_for_tier. Việc dùng chung một nguồn quy định duy nhất trên máy chủ giúp ngăn chặn triệt "
        "để trường hợp người dùng gọi thẳng API hoặc dùng câu nói đánh lừa trợ lý để vượt quyền."
    )
    _embed_listing(rb, "be_rbac_check_fn")
    rb.add_para(
        "Để giải quyết tình huống có người thân hoặc bạn bè ghé thăm nhà trong thời gian ngắn mà không cần tạo tài "
        "khoản lâu dài hay chia sẻ mật khẩu Wi-Fi/tài khoản chính, em thiết kế luồng mời Khách Cấp 3 bằng mã QR "
        "động trong backend/auth/qr_totp_mixin.py. Chỉ Chủ nhà Cấp 1 mới có quyền bấm sinh mã QR kèm thời hạn sử "
        "dụng tùy chọn (1 ngày, 2 ngày, 1 tuần, 1 tháng hoặc 1 năm). Mã QR trên màn hình Chủ nhà tự động xoay vòng "
        "chữ ký HMAC-SHA256 theo chu kỳ TOTP đúng 10 giây (Đoạn mã 4.5). Khi khách quét mã bằng điện thoại hoặc "
        "ứng dụng Android, máy chủ kiểm tra token trong cửa sổ bắt tay tối đa 180 giây (18 chu kỳ 10 giây, có tính "
        "sai lệch đồng hồ nhỏ) và đánh dấu ngay vào tập used_qr_tokens theo cơ chế dùng một lần (Single-Use Token). "
        "Cách thiết kế này ngăn chặn hiệu quả hành vi chụp ảnh màn hình mã QR gửi lại cho người ngoài quét sau đó. "
        "Ngoài ra, Chủ nhà có thể bấm thu hồi phiên khách bất kỳ lúc nào; máy chủ sẽ vô hiệu hóa token phiên và "
        "ngắt lập tức mọi kết nối WebSocket giọng nói của vị khách đó."
    )
    _embed_listing(rb, "be_qr_totp")

    # --- 4.2.5 ---
    rb.add_h3("4.2.5. Chế độ hoạt động ngoại tuyến (Offline Mode)")
    rb.add_para(
        "Một nhược điểm phổ biến của nhiều hệ thống nhà thông minh phụ thuộc hoàn toàn vào đám mây là ngôi nhà sẽ "
        "mất khả năng điều khiển hoặc rơi vào trạng thái nguy hiểm (như máy bơm chạy khô liên tục hay cửa mở không "
        "kiểm soát) khi đứt cáp Internet hoặc máy chủ trung tâm tắt nguồn. Để khắc phục thực chất vấn đề này mà "
        "vẫn trung thực về phạm vi kỹ thuật, em xây dựng hợp đồng hành vi ngoại tuyến thống nhất giữa máy chủ "
        "(backend/engine/offline_contract.py) và firmware vi điều khiển (firmware/esp8266_smarthome/offline_fsm.h "
        "và offline_safety_config.h). Tất cả các trạng thái chuyển đổi và giới hạn an toàn dưới đây đều đã được "
        "lập trình đầy đủ trong mã nguồn và kiểm thử xác định."
    )
    rb.add_para(
        "Khi ESP8266 phát hiện mất kết nối Wi-Fi hoặc mất nhịp tim (heartbeat chu kỳ 3 giây) với máy chủ laptop, "
        "máy trạng thái ngoại tuyến (OfflineFsm) chuyển sang cơ chế thử kết nối lại không chặn theo hàm mũ "
        "(ExponentialBackoff) với chu kỳ tăng dần 1 s → 2 s → 4 s → 8 s → 16 s → tối đa 30 s nhằm tránh làm treo "
        "bộ đếm Watchdog. Nếu mất Wi-Fi quá 15 giây, bo mạch có thể kích hoạt điểm phát dự phòng cục bộ "
        "(SoftAP SmartHome-Offline-AP). Trong giai đoạn ngoại tuyến, đèn LED trên chân D0 thực hiện kiểu nháy kép "
        "chu kỳ 4 giây (không chặn) kết hợp tiếng bíp báo mất kết nối một lần để người dùng nhận biết trạng thái "
        "bằng mắt thường. Đồng thời, máy chủ web cục bộ ESP8266WebServer cổng 80 (/offline/cmd, /offline/status) "
        "vẫn cho phép gửi các lệnh bật/tắt cơ bản cho đèn phòng khách, đèn phòng ngủ, máy bơm tưới cây, nguồn mạch "
        "loa, còi báo động, lệnh đóng cửa chính và lệnh hỏi trạng thái thiết bị."
    )
    rb.add_para(
        "Ở tầng bảo vệ phần cứng chạy độc lập trên ESP8266, bộ hẹn giờ an toàn tickSafetyTimers liên tục giám sát "
        "hai phụ tải rủi ro cao: máy bơm tưới cây vẫn duy trì logic tự bảo vệ theo cảm biến độ ẩm đất (tự bật dưới "
        "40%, tự ngắt từ 70% trở lên) và bị cưỡng chế ngắt sau tối đa 120 giây chạy liên tục (khóa an toàn cho tới "
        "khi đất đủ ẩm hoặc có thao tác đặt lại); còi báo động ở chế độ ngoại tuyến tự ngắt sau tối đa 30 giây; "
        "rơ-le nguồn mạch loa tự ngắt trễ sau 1,5 giây không phát. Đặc biệt, ngay trong tầng firmware áp đặt quy "
        "tắc khóa cứng an ninh (Addendum A3): khi chuyển từ trực tuyến sang ngoại tuyến, cửa chính tự động đóng về "
        "góc an toàn 0°, và mọi yêu cầu mở cửa chính khi đang mất kết nối máy chủ đều bị hàm canSetMainDoor từ chối "
        "tuyệt đối (OFFLINE_MAIN_DOOR_OPEN_ALLOWED = false, trả HTTP 403). Mọi thay đổi vật lý xảy ra trong lúc "
        "ngoại tuyến được ghi vào bộ đệm vòng OfflineEventRing (16 phần tử); ngay khi kết nối máy chủ phục hồi, "
        "ESP8266 tự động gửi POST /api/hardware/resync để đồng bộ ngược trạng thái thực tế lên cơ sở dữ liệu trước "
        "khi tiếp nhận lệnh mới."
    )
    rb.add_para(
        "Ngược lại, hệ thống quy định rõ những chức năng không khả dụng khi ngoại tuyến để bảo đảm tính minh bạch "
        "và an toàn: dịch vụ nhận dạng và hội thoại giọng nói tự nhiên Gemini Live đòi hỏi kết nối Internet nên "
        "không hoạt động khi đứt mạng ngoài; tầng ngoại tuyến trên ESP8266 không thực thi kiểm tra phân quyền 3 tầng "
        "(OFFLINE_ROLE_CHECK_ENABLED = false), không cho phép tạo hay chạy lệnh tùy chỉnh "
        "(OFFLINE_CUSTOM_COMMANDS_ALLOWED = false) và không cho phép tạo hoặc chỉnh sửa lịch hẹn, luật tự động hóa "
        "(OFFLINE_AUTOMATION_MUTATION_ALLOWED = false). Bảng 4.3 tóm tắt đầy đủ ranh giới chức năng ngoại tuyến "
        "và Hình 4.4 minh họa máy trạng thái Offline FSM cùng quy trình nạp cấu hình Wi-Fi động qua LittleFS."
    )
    rb.add_table(
        "Tổng hợp phạm vi hoạt động và giới hạn an toàn ở chế độ ngoại tuyến (Offline Mode)",
        ["Nhóm chức năng / Cơ chế", "Trạng thái khi ngoại tuyến", "Chi tiết thực thi đã kiểm thử trong mã nguồn"],
        [
            (
                "Bật/tắt 5 thiết bị cơ bản & đóng cửa chính",
                "Hoạt động (qua LAN :80)",
                "ESP8266WebServer cổng 80 (/offline/cmd, /offline/status) nhận lệnh bật/tắt 2 đèn, bơm, loa, còi, đóng cửa và hỏi trạng thái.",
            ),
            (
                "Tự bảo vệ bơm tưới, còi & mạch loa",
                "Hoạt động độc lập trên MCU",
                "Ngưỡng độ ẩm đất cục bộ (<40% bật, >=70% tắt); tự ngắt cứng bơm <= 120 s, còi <= 30 s, rơ-le loa trễ 1,5 s.",
            ),
            (
                "Tự kết nối lại, chỉ báo & đồng bộ ngược",
                "Hoạt động tự động",
                "ExponentialBackoff 1 s..30 s không chặn, nháy kép LED D0 chu kỳ 4 s, đệm 16 sự kiện và tự gọi POST /api/hardware/resync.",
            ),
            (
                "Mở cửa chính (main_door → OPEN)",
                "Bị khóa cứng (HTTP 403)",
                "Cấm tuyệt đối tại firmware canSetMainDoor() (Addendum A3); tự đóng cửa về 0° khi chuyển sang ngoại tuyến.",
            ),
            (
                "Giọng nói tiếng Việt tự nhiên (Gemini Live)",
                "Không hoạt động",
                "Cần kết nối Internet để truyền luồng âm thanh tới dịch vụ Gemini Live; máy chủ/ứng dụng thông báo trạng thái mất mạng.",
            ),
            (
                "Lệnh tùy chỉnh, hẹn giờ/luật mới & RBAC 3 tầng",
                "Vô hiệu hóa ngoại tuyến",
                "Chính sách SSOT đặt rõ các cờ tắt trên ESP8266; hệ thống từ chối bằng câu phản hồi tiếng Việt chuẩn khi ngoại tuyến.",
            ),
        ],
        col_widths_cm=[3.8, 3.3, 8.4],
        font_pt=9.5,
    )
    rb.add_figure(
        sw_dir / "sw_arch_offline_fsm.png",
        "Quy trình nạp cấu hình Wi-Fi runtime LittleFS và Máy trạng thái ngoại tuyến (Offline FSM A1–A4)",
        max_width_cm=14.0,
        max_height_cm=6.8,
        kind="diagram",
    )

    # ===== 4.3 GIAO DIỆN WEB 3D, ỨNG DỤNG ANDROID VÀ VỎ MÔ HÌNH NHÀ IN 3D =====
    rb.add_h2("4.3. Giao diện Web 3D, ứng dụng Android và vỏ mô hình nhà in 3D")

    rb.add_h3("4.3.1. Giao diện Web 3D và ứng dụng Android")
    rb.add_para(
        "Giao diện Web đặt trong thư mục web/ sử dụng hoàn toàn tiếng Việt chuẩn mực, hỗ trợ hai chế độ giao diện "
        "Sáng (Light) và Tối (Dark) cùng bố cục đáp ứng mượt mà từ màn hình máy tính tới điện thoại. Hệ thống tổ "
        "chức thành sáu màn hình chức năng gắn trên thanh điều hướng: Tổng quan 3D (/), Tự động hóa (/automation), "
        "Xác thực và Phân quyền (/auth), Mô phỏng đấu nối phần cứng (/wokwi, giới hạn cho Cấp 1 và Cấp 2), Nhật ký "
        "kiểm toán (/logs, chỉ dành cho Chủ nhà Cấp 1) và Cổng hướng dẫn cài đặt ứng dụng (/app). Toàn bộ nút điều "
        "khiển và mục trình đơn tự động ẩn hoặc khóa tương ứng theo tầng quyền của phiên đang đăng nhập."
    )
    rb.add_para(
        "Điểm nhấn trực quan của ứng dụng Web là mô hình song sinh số 3D (Web 3D Digital Twin) xây dựng bằng "
        "Three.js, mô phỏng đồng bộ hình học ngôi nhà và đủ 6 thiết bị chấp hành: khi bật đèn phòng khách hoặc "
        "phòng ngủ, nguồn sáng điểm phát sáng ngay đúng vị trí đèn trên vách ngăn; khi mở cửa chính, cánh cửa xoay "
        "mượt quanh bản lề từ 0° đến 90° đồng bộ với góc quay Servo SG90; khi bật máy bơm tưới cây, hiệu ứng dòng "
        "nước hoạt động tại khu vực chậu đất; đồng thời các thẻ thông số nhiệt độ, độ ẩm không khí, độ ẩm đất và "
        "trạng thái âm thanh cập nhật theo thời gian thực qua luồng SSE."
    )
    rb.add_para(
        "Song song với bản Web, ứng dụng di động Android thuần trong thư mục app/ (mã gói "
        "vn.edu.hust.seee.smarthome, hỗ trợ từ Android 8.0 trở lên) được phát triển bằng Kotlin và Jetpack Compose "
        "theo ngôn ngữ thiết kế Material Design 3. Ứng dụng tách thành hai mô-đun rõ ràng là app-core (chứa tầng "
        "mạng REST/SSE/WebSocket, mô hình trạng thái, kiểm soát phiên RBAC và giao diện lõi) và app (điểm khởi chạy "
        "đóng gói APK). Giao diện chính bố trí bốn thẻ điều hướng dưới đáy gồm Trang chủ (hiển thị kết nối máy chủ, "
        "số liệu ba cảm biến và thao tác nhanh), Thiết bị (điều khiển chi tiết các thiết bị trong thẩm quyền), Giọng "
        "nói (thu âm PCM 16 kHz bằng AudioRecord, phát tiếng nói Aoede 24 kHz qua AudioTrack kèm phụ đề tiếng Việt) "
        "và Tài khoản (hiển thị tầng quyền, đồng hồ đếm ngược phiên khách, thiết lập địa chỉ máy chủ và máy quét mã "
        "QR động 10 giây)."
    )

    rb.add_h3("4.3.2. Thiết kế vỏ mô hình nhà in 3D")
    rb.add_para(
        "Để trình diễn trực quan hệ thống trong không gian gọn gàng, sạch sẽ và an toàn khi vận chuyển bảo vệ đồ án, "
        "em thiết kế vỏ mô hình ngôi nhà vật liệu nhựa PLA theo nguyên tắc cơ khí lắp mộng tự khóa (mortise-and-tenon) "
        "hoàn toàn không dùng ốc vít kim loại hay keo dán. Toàn bộ 14 mô-đun điện tử cùng bo mạch PCB Hub trung tâm "
        "100 × 80 mm được bố trí cố định vào các ngàm gài và khay trượt riêng biệt: khoang kỹ thuật đặt PCB Hub, hai "
        "mô-đun rơ-le và mạch khuếch đại loa được vây kín tách biệt hoàn toàn với bể nước liền khối của khu vườn tưới "
        "cây, còn cửa chính sử dụng cơ cấu dẫn động đồng trục trực tiếp với Servo SG90 ở đỉnh khung cửa. Hình 4.5 và "
        "Hình 4.6 lần lượt thể hiện tổng thể vỏ mô hình nhà lắp mộng và mặt cắt bố trí 14 mô-đun điện tử bên trong."
    )
    rb.add_figure(
        diag_dir / "house_3d_assembled_clean.png",
        "Tổng thể vỏ mô hình nhà thông minh in 3D lắp mộng chứa bo mạch PCB Hub và các khoang chức năng",
        max_width_cm=11.6,
        max_height_cm=5.4,
        kind="3d_model",
    )
    rb.add_figure(
        demo_dir / "blender_cutaway_14modules.png",
        "Mặt cắt bố trí 14 mô-đun điện tử, bo mạch PCB Hub và đường đi dây gọn bên trong mô hình nhà",
        max_width_cm=11.6,
        max_height_cm=5.4,
        kind="3d_model",
    )

    # ===== 4.4 SO SÁNH VỚI CÁC SẢN PHẨM NHÀ THÔNG MINH HIỆN CÓ =====
    rb.add_h2("4.4. So sánh với các sản phẩm nhà thông minh hiện có")
    rb.add_para(
        "Để đánh giá khách quan vị trí kỹ thuật, điểm mạnh cũng như các giới hạn còn tồn tại của đề tài, em tiến "
        "hành đối chiếu hệ thống đồ án với sáu nền tảng nhà thông minh thương mại phổ biến trên thị trường quốc tế "
        "và Việt Nam gồm Google Home, Amazon Alexa, Xiaomi Mi Home, Tuya / Smart Life, Lumi SmartHome và Bkav "
        "SmartHome. Toàn bộ đặc tính của các nền tảng thương mại trong Bảng 4.4 được tổng hợp theo thông tin công "
        "bố trên trang chủ và tài liệu hỗ trợ chính thức của các nhà sản xuất tại thời điểm tháng 11/2026 (chi tiết "
        "nguồn dẫn được liệt kê đầy đủ trong mục Tài liệu tham khảo)."
    )
    rb.add_table(
        "So sánh hệ thống đồ án với các sản phẩm nhà thông minh thương mại hiện có (cập nhật tháng 11/2026)",
        [
            "Sản phẩm",
            "Tiếng Việt tự nhiên",
            "Chi phí",
            "Điều khiển cục bộ",
            "Lệnh tùy chỉnh",
            "Phân quyền / vai trò",
            "Ghi chú",
        ],
        [
            (
                "Google Home",
                "Tiếng Việt hỗ trợ trên ứng dụng di động; loa thông minh Nest/Gemini for Home chưa hỗ trợ chính thức tiếng Việt bản địa trên phần cứng.",
                "Miễn phí ứng dụng; chi phí mua loa thông minh và thiết bị tương thích theo hãng.",
                "Có (qua Matter/Thread và một số thiết bị hỗ trợ thực thi cục bộ); suy luận giọng nói phụ thuộc đám mây.",
                "Có (Household Automations và Personal Routines cấu hình trên ứng dụng).",
                "2 nhóm chính: Admin và Member (Admin bật/tắt tùy chọn Settings và Activity); hỗ trợ trẻ em qua Family Link.",
                "Hệ sinh thái quốc tế rộng, hỗ trợ chuẩn Matter mạnh.",
            ),
            (
                "Amazon Alexa",
                "Chưa hỗ trợ tiếng Việt bản địa (chỉ hỗ trợ các ngôn ngữ lớn như Anh, Tây Ban Nha, Pháp, Đức, Nhật...).",
                "Miễn phí ứng dụng; cần mua loa Echo và thiết bị tương thích.",
                "Có mức cục bộ cho thiết bị chuẩn Matter/Thread qua Echo hỗ trợ; nhận dạng giọng nói qua đám mây.",
                "Có (Alexa Routines theo câu nói ngôn ngữ được hỗ trợ, lịch hoặc cảm biến).",
                "Chia sẻ hộ gia đình qua Amazon Household (hồ sơ thành viên).",
                "Thư viện kỹ năng (Skills) và thiết bị tương thích rất lớn ở thị trường quốc tế.",
            ),
            (
                "Xiaomi Mi Home",
                "Ứng dụng có giao diện tiếng Việt; giọng nói tiếng Việt cần liên kết trợ lý ngoài (trợ lý nội bộ XiaoAI dùng tiếng Trung).",
                "Phân khúc phổ thông; chi phí tùy số lượng cảm biến, công tắc và bộ trung tâm Hub.",
                "Có (tự động hóa cục bộ khi trang bị bộ trung tâm Xiaomi Smart Home Hub).",
                "Có (Smart Scenes theo lịch, cảm biến hoặc chạm kích hoạt trên ứng dụng).",
                "Chia sẻ nhà (Home Sharing) và chia sẻ từng thiết bị riêng lẻ theo tài khoản Xiaomi.",
                "Danh mục phần cứng đa dạng, dễ mở rộng trong hộ gia đình.",
            ),
            (
                "Tuya / Smart Life",
                "Giao diện ứng dụng hỗ trợ tiếng Việt; điều khiển giọng nói chủ yếu qua liên kết Google Assistant hoặc Alexa.",
                "Phân khúc phổ thông rộng; nhiều hãng phần cứng giá thấp dùng chung nền tảng.",
                "Có liên kết cục bộ (Local Linkage) khi sử dụng cổng Zigbee / Multi-Mode Gateway.",
                "Có (kịch bản Tap-to-Run và tự động hóa điều kiện trên ứng dụng Smart Life).",
                "Phân vai trong Home Management: Home Owner, Administrator, Common Member và chia sẻ từng thiết bị.",
                "Nền tảng mở phổ biến nhất ở phân khúc thiết bị Wi-Fi/Zigbee giá rẻ.",
            ),
            (
                "Lumi SmartHome (Việt Nam)",
                "Có hỗ trợ tiếng Việt qua loa thông minh OLLI MAIKA và liên kết Google Assistant, Siri, Alexa.",
                "Giải pháp thương mại trọn gói phân khúc trung–cao cấp; báo giá theo cấu hình công trình.",
                "Vận hành theo hạ tầng thiết bị chuyên dụng của hãng và ứng dụng Lumi Life+.",
                "Có (thiết lập kịch bản sống như Đi ngủ, Về nhà, Tiếp khách... trên ứng dụng).",
                "Có quản lý phân quyền người dùng và bảo vệ mã PIN trên ứng dụng Lumi Life+.",
                "Thương hiệu Việt Nam có mạng lưới lắp đặt, bảo hành và thiết bị điện 220V hoàn chỉnh.",
            ),
            (
                "Bkav SmartHome (Việt Nam)",
                "Có hỗ trợ giọng nói tiếng Việt 3 miền và tích hợp các trợ lý phổ biến (MAIKA, Google Assistant, Alexa...).",
                "Giải pháp thương mại phân khúc cao cấp; báo giá trọn gói theo công trình.",
                "Hệ thống điều khiển trung tâm chuyên dụng đồng bộ với bảng điều khiển và ứng dụng.",
                "Có (kịch bản ngữ cảnh Đi ngủ, Thức dậy, Tiếp khách, Xem phim và gợi ý thói quen).",
                "Hỗ trợ cá nhân hóa và phân quyền quản trị theo thành viên gia đình.",
                "Tối ưu cho biệt thự, nhà ở cao cấp với tiêu chuẩn phần cứng thương mại.",
            ),
            (
                "Hệ thống đồ án (nguyên mẫu)",
                "Hội thoại tiếng Việt tự nhiên trực tiếp qua Gemini Live, phản hồi giọng đọc tiếng Việt ngắn gọn, đúng trạng thái.",
                "Nguyên mẫu học thuật tự lắp linh kiện ESP8266/cảm biến chi phí thấp; phí API giọng nói tính theo mức sử dụng thực tế.",
                "Có dự phòng LAN HTTP :80 cho bật/tắt cơ bản, bảo vệ bơm <=120 s, khóa cứng mở cửa chính; giọng nói cần Internet.",
                "Dạy lệnh tùy chỉnh bằng lời nói tiếng Việt (xác nhận 1 lần khi tạo, chạy ngay không hỏi lại ở các lần sau).",
                "RBAC 3 tầng khóa cứng phía server (Chủ nhà / Thành viên / Khách) + mời khách bằng QR động TOTP 10 s, thu hồi tức thì.",
                "Nguyên mẫu học thuật quy mô mô hình 5V DC; chưa có chứng nhận an toàn điện công nghiệp 220V AC.",
            ),
        ],
        col_widths_cm=[2.0, 2.5, 2.1, 2.3, 2.2, 2.3, 2.1],
        font_pt=8.4,
    )
    rb.add_para(
        "Từ Bảng 4.4 có thể thấy rõ mỗi nhóm giải pháp đều có ưu thế và phạm vi phù hợp riêng. Các sản phẩm thương "
        "mại quốc tế như Google Home, Amazon Alexa, Xiaomi Mi Home và Tuya sở hữu hệ sinh thái hàng nghìn thiết bị "
        "đạt chuẩn điện công nghiệp, khả năng mở rộng chuẩn Matter/Zigbee phong phú và độ hoàn thiện phần cứng cao; "
        "các thương hiệu trong nước như Lumi SmartHome và Bkav SmartHome lại nổi bật về thiết bị điện 220V chuẩn "
        "tại Việt Nam, khả năng hỗ trợ tiếng Việt kết hợp dịch vụ thi công, bảo hành chuyên nghiệp."
    )
    rb.add_para(
        "Ở góc độ một đề tài tốt nghiệp kỹ thuật, hệ thống của em giải quyết tập trung ba nhu cầu còn nhiều khoảng "
        "trống khi triển khai thực nghiệm: (1) tương tác hội thoại tiếng Việt tự nhiên kèm khả năng dạy lệnh tùy "
        "chỉnh bằng lời nói theo quy tắc xác nhận một lần duy nhất; (2) phân quyền chặt chẽ ba tầng cưỡng chế phía "
        "máy chủ kết hợp luồng mời khách tạm thời bằng mã QR động xoay vòng 10 giây, dùng một lần và thu hồi tức "
        "thì; và (3) kiến trúc mở, tự chủ dữ liệu cục bộ trên laptop kèm cơ chế dự phòng ngoại tuyến khóa cứng an "
        "ninh cửa chính ở tầng vi điều khiển. Tuy nhiên, em cũng nhìn nhận thẳng thắn các giới hạn hiện tại của "
        "nguyên mẫu: hệ thống mới tập trung cho ngôn ngữ tiếng Việt, tính năng giọng nói tự nhiên vẫn phụ thuộc kết "
        "nối Internet tới dịch vụ Gemini Live, toàn bộ mạch điện tử đang dừng ở quy mô mô hình bàn 5V DC với 6 thiết "
        "bị chấp hành và chưa trải qua quy trình kiểm định chứng nhận an toàn điện công nghiệp 220V AC như sản phẩm "
        "thương mại."
    )

    # ===== 4.5 KẾT LUẬN CHƯƠNG 4 =====
    rb.add_h2("4.5. Kết luận Chương 4")
    rb.add_para(
        "Chương 4 đã trình bày đầy đủ kiến trúc vận hành và cách thức triển khai từng phân hệ của hệ thống nhà "
        "thông minh điều khiển bằng giọng nói tiếng Việt, từ luồng xử lý đầu–cuối một câu lệnh thoại, cơ chế điều "
        "khiển thiết bị trên FastAPI và SQLite WAL, tự động hóa hai bể cùng lệnh tùy chỉnh xác nhận một lần, phân "
        "quyền RBAC ba tầng và mã QR động TOTP 10 giây, chế độ dự phòng ngoại tuyến khóa cứng cửa chính ở tầng "
        "firmware, tới giao diện Web 3D, ứng dụng Android, vỏ mô hình nhà in 3D và bảng đối chiếu khách quan với "
        "các sản phẩm thương mại. Trong Chương 5, em sẽ trình bày kịch bản kiểm thử thực nghiệm, kết quả đo đạc "
        "hiệu năng và đánh giá mức độ đáp ứng yêu cầu của toàn hệ thống."
    )
