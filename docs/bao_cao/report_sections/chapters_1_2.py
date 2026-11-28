"""Chapters 1 & 2: Tổng quan về đề tài & Khảo sát và phân tích yêu cầu."""

from __future__ import annotations

import pathlib

from .docx_helpers import ReportBuilder


def build_chapter_1(rb: ReportBuilder, assets_dir: pathlib.Path) -> None:
    sw_dir = assets_dir / "software"
    rb.add_chapter(1, "TỔNG QUAN VỀ ĐỀ TÀI", first_chapter=True)
    rb.add_para(
        "Trong Chương 1, báo cáo trình bày bối cảnh thực tiễn và các hạn chế của những hệ thống nhà thông minh hiện hành, "
        "xác định mục tiêu tổng quát và các mục tiêu kỹ thuật cụ thể của đề tài, đồng thời nêu rõ định hướng giải pháp liên ngành "
        "từ phần cứng nhúng, cơ khí in 3D đến máy chủ trí tuệ nhân tạo điều khiển bằng giọng nói tiếng Việt."
    )

    rb.add_h2("1.1. Đặt vấn đề")
    rb.add_para(
        "Sự phát triển mạnh mẽ của Internet vạn vật (IoT), điện toán đám mây và các mô hình ngôn ngữ lớn đa phương thức "
        "đã đưa khái niệm nhà thông minh (Smart Home) từ các mô hình thử nghiệm phòng thí nghiệm trở thành một nhu cầu thiết thực "
        "trong đời sống hiện đại. Người dùng ngày nay không chỉ kỳ vọng bật/tắt đèn hay quạt từ xa qua điện thoại, mà còn mong muốn "
        "tương tác tự nhiên bằng ngôn ngữ nói hàng ngày, thiết lập các kịch bản tự động hóa theo thời gian và cảm biến môi trường, "
        "đồng thời kiểm soát chặt chẽ an ninh cho các thiết bị nhạy cảm như cửa ra vào hay còi báo động."
    )
    rb.add_para(
        "Tuy nhiên, qua khảo sát các hệ thống thương mại cũng như nhiều đề tài mẫu thử trong môi trường đào tạo đại học, "
        "vẫn tồn tại năm khoảng trống kỹ thuật đáng kể chưa được giải quyết triệt để một cách đồng bộ:"
    )
    rb.add_bullet(
        "Trải nghiệm giọng nói tiếng Việt còn cứng nhắc và độ trễ cao: ",
        "Phần lớn hệ thống thương mại (Google Assistant, Amazon Alexa) hoặc các giải pháp ghép nối rời rạc (STT → NLP quy tắc → TTS) "
        "thường gặp độ trễ phản hồi 3–6 giây, khó hiểu câu lệnh ghép tự nhiên bằng tiếng Việt, dễ bị kích hoạt nhầm do dội âm từ loa phát lại "
        "và thiếu cơ chế dạy lệnh tùy chỉnh linh hoạt có xác nhận an toàn.",
    )
    rb.add_bullet(
        "Thiếu phân quyền chi tiết theo vai trò cho hộ gia đình và khách vãng lai: ",
        "Các ứng dụng IoT phổ thông thường áp dụng mô hình chia sẻ tài khoản toàn quyền hoặc cấp quyền cố định dài hạn. "
        "Khi có khách tới chơi hoặc người thân ghé thăm, chủ nhà khó cấp quyền chỉ bật/tắt đèn trong thời gian giới hạn vài giờ "
        "mà vẫn chặn tuyệt đối khả năng mở cửa chính, tác động còi báo động hay xem nhật ký hoạt động của gia đình.",
    )
    rb.add_bullet(
        "Hạn chế về an toàn vật lý và khả năng chịu lỗi khi mất Internet: ",
        "Nhiều hệ thống phụ thuộc hoàn toàn vào máy chủ đám mây nên tê liệt khi đứt mạng, hoặc ngược lại mở chế độ điều khiển cục bộ "
        "không ràng buộc an ninh khiến khóa cửa dễ bị kích mở trái phép khi ngoại tuyến. Ở lớp điện tử, việc lắp thử trên bảng cắm breadboard "
        "gây tiếp xúc lỏng, thiếu tụ lọc xung dòng đỉnh cho động cơ servo/máy bơm và thiếu diode dập xung ngược (flyback) làm reset vi điều khiển.",
    )
    rb.add_bullet(
        "Thiếu tính trực quan không gian và khả năng kiểm chứng trước khi gia công phần cứng: ",
        "Giao diện dạng công tắc danh sách truyền thống không phản ánh vị trí không gian thực của từng cảm biến và cơ cấu chấp hành. "
        "Trong khi đó, quá trình thiết kế mạch in PCB, đi dây 40 sợi và chế tạo vỏ mô hình thường tách rời nhau, dễ dẫn đến xung đột cơ khí, "
        "hụt chiều dài dây nối hoặc tiêu tốn quá nhiều vật liệu in 3D.",
    )
    rb.add_bullet(
        "Rủi ro lộ thông tin mạng Wi-Fi trong mã nguồn nhúng: ",
        "Thói quen ghi cứng tên mạng (SSID) và mật khẩu Wi-Fi ngay trong mã nguồn C/C++ của ESP8266 buộc phải biên dịch lại firmware "
        "mỗi khi chuyển địa điểm trình diễn và tạo nguy cơ rò rỉ thông tin đăng nhập khi lưu trữ mã nguồn trên Git.",
    )
    rb.add_para(
        "Xuất phát từ các yêu cầu thực tiễn nêu trên, đề tài “Thiết kế và xây dựng hệ thống nhà thông minh điều khiển bằng giọng nói AI "
        "tích hợp mô hình 3D và ứng dụng di động” được thực hiện nhằm xây dựng một hệ thống hoàn chỉnh, đồng nhất dữ liệu từ một nguồn sự thật duy nhất (SSOT), "
        "đảm bảo tính an toàn điện tử, bảo mật phân quyền, khả năng kiểm chứng tự động và sẵn sàng đưa vào vận hành thực tế."
    )

    rb.add_h2("1.2. Mục tiêu đề ra")
    rb.add_para(
        "Đề tài hướng tới hoàn thiện đồng bộ cả bốn trụ cột: phần cứng điện tử an toàn, cơ khí vỏ nhà in 3D tối ưu, "
        "hệ thống máy chủ tích hợp AI giọng nói tiếng Việt và bộ giao diện đa nền tảng (Web 3D + Android APK). Các mục tiêu cụ thể gồm:"
    )
    rb.add_bullet(
        "Mục tiêu 1 — Kiến trúc phần cứng PCB-Direct không dùng breadboard: ",
        "Khóa cứng hợp đồng 10 chân trên vi điều khiển NodeMCU ESP8266 v2 Amica điều khiển đúng 6 thiết bị chấp hành và đọc 3 cảm biến "
        "(ánh xạ đầy đủ 14 khối/module vật lý). Thiết kế bo mạch PCB Hub trung tâm DIY v3 một lớp (100 × 80 × 1,6 mm, 51 footprints) "
        "đạt 0 lỗi ERC và 0 lỗi DRC, tích hợp đủ 9 tụ lọc C1–C9, 2 diode flyback 1N4007 (D1, D2) và mạch lái transistor Q1 S8050; "
        "bảo đảm 40/40 dây nối vật lý có chiều dài định tuyến 3D <= 30 cm.",
    )
    rb.add_bullet(
        "Mục tiêu 2 — Mô hình nhà thông minh in 3D lắp mộng tự khóa, tối ưu vật liệu: ",
        "Thiết kế bộ chi tiết vỏ nhà và giá đỡ bằng FreeCAD 1.1.4 áp dụng 100% khớp mộng tự khóa (không ốc vít, không keo dán, 0% support), "
        "tương thích bàn in phổ thông 180 × 200 × 250 mm, cắt giảm trên 35% khối lượng nhựa PLA (đạt <= 680 g) nhưng vẫn bảo đảm độ võng đáy <= 0,50 mm "
        "và 0 va chạm trong lắp ráp ảo 3D BRep.",
    )
    rb.add_bullet(
        "Mục tiêu 3 — Trợ lý giọng nói AI tiếng Việt thời gian thực & Tự động hóa 2 bể: ",
        "Tích hợp Gemini 3.8 Live API (giọng Aoede 100% tiếng Việt) qua WebSocket hai chiều độ trễ thấp, trang bị bộ chống dội âm ServerEchoGuard, "
        "20 hàm công cụ điều khiển trực tiếp (Actuate-First), cơ chế dạy lệnh tùy chỉnh xác nhận đúng 1 lần, cùng 2 bể tự động hóa độc lập "
        "(TimersPool cho hẹn giờ/lịch lặp và RulesPool cho luật điều kiện cảm biến – thiết bị).",
    )
    rb.add_bullet(
        "Mục tiêu 4 — Bảo mật phân quyền 3 tầng RBAC & Chịu lỗi ngoại tuyến: ",
        "Áp dụng cơ chế xác thực và phân quyền chặt phía máy chủ (Chủ nhà Cấp 1, Thành viên Cấp 2, Khách Cấp 3 vào bằng mã QR động TOTP chu kỳ 10 giây); "
        "nạp cấu hình Wi-Fi động qua USB lưu vào LittleFS (/wifi_config.json) không lộ mật khẩu trong mã nguồn; cài đặt máy trạng thái ngoại tuyến "
        "(Offline FSM A1–A4) trên ESP8266 khóa cứng cấm mở cửa chính khi mất kết nối.",
    )
    rb.add_bullet(
        "Mục tiêu 5 — Giao diện Web 3D Digital Twin & Ứng dụng Android hoàn chỉnh: ",
        "Xây dựng Web Dashboard mô phỏng 3D thời gian thực 14 module bằng Three.js (chế độ Sáng/Tối, hỗ trợ máy tính và điện thoại), "
        "trang kiểm tra đấu nối /wokwi PCB-Direct, triển khai truy cập từ xa an toàn qua Tailscale Funnel và Vercel; "
        "đóng gói ứng dụng Android thuần Kotlin/Jetpack Compose (APK v1.0, minSdk 26) và kiểm thử triệt để qua công cụ tự động.",
    )

    rb.add_h2("1.3. Định hướng phương pháp nghiên cứu và giải quyết vấn đề")
    rb.add_para(
        "Để tránh tình trạng không đồng bộ giữa sơ đồ mạch, mã nguồn firmware, mô hình 3D và tài liệu vận hành, đồ án áp dụng "
        "phương pháp thiết kế hướng đặc tả kết hợp Nguồn sự thật duy nhất (Single Source of Truth — SSOT) và kiểm chứng liên tầng:"
    )
    rb.add_bullet(
        "Tầng phần cứng & cơ khí đồng bộ bằng mã nguồn (Hardware-as-Code): ",
        "Mọi chân kết nối, màu dây, mã linh kiện bảo vệ và kích thước datasheet được định nghĩa tập trung trong hardware/wiring_contract.py "
        "và hardware/component_dimensions_ssot.py. Từ đây, hệ thống tự động đối chiếu với sơ đồ nguyên lý/mạch in KiCad 10.0, firmware ESP8266, "
        "kịch bản dựng khối tham số FreeCAD 1.1.4, cảnh kết xuất Blender 5.2.2 LTS và mô hình Web 3D Three.js.",
    )
    rb.add_bullet(
        "Tầng máy chủ bất đồng bộ và lưu trữ bền vững: ",
        "Sử dụng FastAPI 0.141.1 chạy trên Uvicorn 0.53.0 theo kiến trúc hướng sự kiện bất đồng bộ (asyncio) để phục vụ đồng thời nhiều luồng "
        "WebSocket âm thanh PCM 16/24 kHz, SSE đẩy trạng thái giao diện và cầu nối MQTT/HTTP tới ESP8266. Toàn bộ dữ liệu người dùng, trạng thái, "
        "lịch hẹn, luật tự động và nhật ký kiểm toán được lưu trên SQLite 3.53.2 chuẩn hóa 3NF ở chế độ Write-Ahead Logging (WAL).",
    )
    rb.add_bullet(
        "Tầng kiểm chứng tự động đa cấp: ",
        "Áp dụng kiểm thử đơn vị và tích hợp bằng pytest 9.1.1 (116 tệp kiểm thử bao phủ logic firmware ngoại tuyến, phân quyền RBAC, hẹn giờ, "
        "lệnh tùy chỉnh và luồng giọng nói), kiểm thử giao diện người dùng thực bằng Playwright trên trình duyệt ẩn, và kiểm thử ứng dụng Android "
        "qua ADB theo đầy đủ 3 tầng phân quyền.",
    )

    rb.add_figure(
        sw_dir / "sw_arch_system_diagram.png",
        "Sơ đồ kiến trúc tổng thể ba tầng của hệ thống Smart Home Voice AI",
        max_width_cm=15.0,
        max_height_cm=9.5,
    )

    rb.add_para(
        "Bảng 1.1 tổng hợp so sánh những đặc điểm cốt lõi giữa hệ thống Smart Home Voice AI được đề xuất với các nhóm giải pháp nhà thông minh phổ biến hiện nay."
    )
    rb.add_table(
        "So sánh hệ thống Smart Home Voice AI đề xuất với các giải pháp nhà thông minh phổ biến",
        ["Tiêu chí đánh giá", "Google Home / Alexa", "Home Assistant + ESPHome", "Tuya / Zigbee phổ thông", "Smart Home Voice AI (Đề tài)"],
        [
            ("Giọng nói tiếng Việt tự nhiên đa lượt", "Hạn chế ngữ cảnh phức tạp", "Cần tự ghép STT/TTS rời, trễ cao", "Phụ thuộc bên thứ 3", "Gemini 3.8 Live 2 chiều (Aoede, 100% VI)"),
            ("Dạy lệnh tùy chỉnh qua lời nói", "Thiết lập thủ công bằng Routine", "Cấu hình YAML / UI thủ công", "Cấu hình Scene trên App", "Dạy trực tiếp bằng lời nói, xác nhận 1 lần"),
            ("Phân quyền 3 tầng & Khách QR động", "Chia sẻ Home cố định", "Phân quyền cơ bản, chưa có QR TOTP", "Chia sẻ tài khoản/thiết bị", "RBAC 3 tầng + QR TOTP đổi mỗi 10 giây"),
            ("Mô phỏng 3D Digital Twin & /wokwi", "Không có", "Cần cài plugin vẽ tay thủ công", "Không có", "Tích hợp sẵn Three.js 14 module & /wokwi"),
            ("An toàn mất mạng (Offline Safety)", "Mất điều khiển giọng nói", "Chạy LAN nhưng chưa khóa cửa riêng", "Phụ thuộc Cloud nhiều", "Offline FSM A1–A4, khóa cứng cửa chính D1"),
            ("Thiết kế mạch & vỏ in 3D mở", "Đóng hoàn toàn", "Phần cứng rời không đồng bộ vỏ", "Đóng hoàn toàn", "PCB DIY v3 0 DRC + 16 bàn in 3D 660,64 g"),
            ("Chi phí mô hình mẫu triển khai", "Cao (loa + hub riêng)", "Trung bình (cần Raspberry Pi + hub)", "Trung bình – cao", "Thấp, tận dụng laptop/PC + ESP8266 5V DC"),
        ],
        col_widths_cm=[3.2, 2.8, 3.1, 2.7, 3.7],
        font_pt=10.5,
    )

    rb.add_h2("1.4. Kết luận Chương 1")
    rb.add_para(
        "Chương 1 đã làm rõ bối cảnh ứng dụng, năm vấn đề kỹ thuật còn bỏ ngỏ của các hệ thống nhà thông minh hiện nay và thiết lập "
        "bộ mục tiêu xuyên suốt cho đồ án. Với định hướng kiến trúc ba tầng kết hợp Nguồn sự thật duy nhất (SSOT) giữa phần cứng, "
        "mô hình 3D và phần mềm AI, hệ thống đảm bảo tính nhất quán, an toàn và dễ dàng kiểm chứng. Chương 2 tiếp tục khảo sát chi tiết "
        "hiện trạng và đặc tả đầy đủ các yêu cầu chức năng, phân quyền và phi chức năng làm cơ sở cho quá trình lựa chọn công nghệ và thiết kế."
    )


def build_chapter_2(rb: ReportBuilder, assets_dir: pathlib.Path) -> None:
    sw_dir = assets_dir / "software"
    rb.add_chapter(2, "KHẢO SÁT VÀ PHÂN TÍCH YÊU CẦU")
    rb.add_para(
        "Trong Chương 2, báo cáo đi sâu khảo sát bài toán sử dụng thực tế trong không gian nhà ở gia đình, "
        "phân tích các nhóm người dùng mục tiêu và đặc tả chi tiết bộ yêu cầu chức năng, ma trận phân quyền 3 tầng RBAC "
        "cũng như các chỉ tiêu phi chức năng nghiêm ngặt về độ trễ, an toàn điện – cơ khí và khả năng phục hồi sự cố."
    )

    rb.add_h2("2.1. Khảo sát và phân tích hiện trạng")
    rb.add_para(
        "Trong một căn hộ gia đình điển hình có nhiều thành viên cùng sinh sống và thường xuyên tiếp đón khách ngắn hạn, "
        "các tác vụ điều khiển thiết bị diễn ra ở ba bối cảnh chính: điều khiển trực tiếp tại chỗ bằng giọng nói rảnh tay "
        "(khi đang nấu ăn, đi ngủ hoặc bưng đồ), giám sát và điều khiển từ xa qua Internet (khi đi làm, đi học cần kiểm tra cửa chính "
        "hoặc tưới cây), và tự động phản ứng theo biến đổi môi trường (độ ẩm đất xuống thấp tự bật bơm tưới, tiếng vỗ tay kích hoạt đèn)."
    )
    rb.add_para(
        "Từ phân tích bối cảnh trên, hệ thống xác định rõ 3 nhóm tác nhân (Actor) với nhu cầu và giới hạn trách nhiệm tách biệt:"
    )
    rb.add_bullet(
        "Tác nhân Cấp 1 — Chủ nhà (Owner / Admin): ",
        "Chịu trách nhiệm quản trị toàn diện ngôi nhà. Có toàn quyền điều khiển cả 6 thiết bị chấp hành (bao gồm các thiết bị trọng yếu "
        "về an ninh là Cửa chính Servo SG90 và Còi báo động TMB12A05), theo dõi cảm biến, thiết lập luật tự động hóa và hẹn giờ, "
        "dạy lệnh giọng nói tùy chỉnh, xem toàn bộ nhật ký kiểm toán (/logs), quản lý danh sách thành viên Cấp 2 và phát hành/thu hồi mã QR động cho Khách Cấp 3.",
    )
    rb.add_bullet(
        "Tác nhân Cấp 2 — Thành viên gia đình (Family Member): ",
        "Sử dụng thường xuyên các tiện ích sinh hoạt như đèn phòng khách, đèn phòng ngủ, máy bơm tưới cây và mạch loa phản hồi, "
        "xem thông số môi trường và đặt lịch sinh hoạt cơ bản. Tuy nhiên, để hạn chế rủi ro thao tác nhầm hoặc lạm quyền từ xa, "
        "hệ thống chặn cứng quyền đóng/mở cửa chính D1 và kích hoạt còi báo động D8 cũng như quyền xem nhật ký hệ thống và quản trị tài khoản.",
    )
    rb.add_bullet(
        "Tác nhân Cấp 3 — Khách tạm thời (Temporary Guest): ",
        "Người đến chơi trong vài giờ, không cần đăng ký mật khẩu dài hạn. Chủ nhà tạo mã QR động có thời hạn (TTL) cho khách quét "
        "trực tiếp bằng điện thoại. Trong thời hạn phiên, khách chỉ được phép bật/tắt đèn phòng khách, đèn phòng ngủ và hỏi nhiệt độ/độ ẩm phòng; "
        "mọi yêu cầu chạm tới cửa chính, còi báo động, máy bơm, loa hay trang cấu hình phần cứng đều bị chặn tuyệt đối ở cả giao diện lẫn máy chủ.",
    )
    rb.add_para(
        "Ngoài ba nhóm tác nhân người dùng, hệ thống còn tương tác với tác nhân phần cứng là nút vi điều khiển NodeMCU ESP8266 v2 Amica "
        "đóng vai trò cầu nối chấp hành – thu thập cảm biến và đảm bảo vận hành an toàn tối thiểu khi đường truyền mạng bị gián đoạn."
    )

    rb.add_h2("2.2. Yêu cầu chức năng")
    rb.add_para(
        "Bộ yêu cầu chức năng của hệ thống được chuẩn hóa thành 14 nhóm chức năng chính (FR-01 đến FR-14), bảo đảm phạm vi tinh gọn "
        "với đúng 6 thiết bị chấp hành và 3 cảm biến khóa cứng (không mở rộng sang quạt, điều hòa 220V hay hồng ngoại IR để tập trung độ tin cậy). "
        "Bảng 2.1 trình bày đặc tả chi tiết các yêu cầu chức năng."
    )
    rb.add_table(
        "Đặc tả 14 nhóm yêu cầu chức năng của hệ thống Smart Home Voice AI",
        ["Mã YC", "Nhóm chức năng", "Mô tả yêu cầu chi tiết", "Phạm vi áp dụng"],
        [
            ("FR-01", "Điều khiển 6 thiết bị chấp hành", "Bật/tắt đèn phòng khách (D0), đèn phòng ngủ (D4), máy bơm tưới cây (D6), nguồn loa PAM8403 (D7), còi báo động (D8); mở/đóng cửa chính SG90 (D1: 0°/90°).", "Web, Android, Voice AI, ESP8266"),
            ("FR-02", "Giám sát 3 cảm biến thời gian thực", "Đọc và hiển thị liên tục nhiệt độ/độ ẩm không khí (DHT11 D2), độ ẩm đất phần trăm 0–100% (LM393+YL-69 A0), sự kiện tiếng vỗ tay/âm thanh lớn (KY-037 D5).", "ESP8266 → Server → Web/App"),
            ("FR-03", "Điều khiển giọng nói AI tiếng Việt", "Hội thoại hai chiều thời gian thực bằng tiếng Việt với Gemini 3.8 Live (giọng Aoede), thực thi công cụ ngay lập tức (Actuate-First), phản hồi ngắn gọn chính xác.", "Web, Android, Backend Live"),
            ("FR-04", "Chống dội âm & lọc tạp âm", "Tự động chặn tín hiệu thu âm khi loa trợ lý đang phát (ServerEchoGuard) kết hợp phát hiện tiếng nói tiếng Việt (VietnameseVAD) để tránh AI tự nghe giọng mình.", "Backend Live Bridge"),
            ("FR-05", "Dạy lệnh tùy chỉnh xác nhận 1 lần", "Cho phép người dùng dạy tổ hợp lệnh mới bằng lời nói (VD: 'Chế độ đi ngủ'). Hệ thống hỏi xác nhận đúng 1 lần trước khi lưu và chạy trực tiếp cho các lần sau.", "Voice AI + SQLite"),
            ("FR-06", "Bể Hẹn giờ & Lịch lặp (Pool 1)", "Đặt hẹn đếm ngược (giây/phút/giờ) hoặc mốc đồng hồ (AM/PM/cả hai), lặp 1 lần/hàng ngày/hàng tuần/hàng tháng; cho phép sửa đổi hoặc hủy hẹn giờ bằng giọng nói hoặc UI.", "TimersPool, Web, App"),
            ("FR-07", "Bể Luật tự động hóa (Pool 2)", "Thiết lập luật điều kiện kết hợp cảm biến/thời gian/trạng thái (bao gồm tự bơm tưới khi đất <40% và tắt khi >=70% có độ trễ chống bật tắt liên tục).", "RulesPool, ESP8266"),
            ("FR-08", "Xác thực đa lớp & Quên mật khẩu", "Đăng nhập bằng tài khoản/mật khẩu băm an toàn, xác thực OTP qua Gmail (cho tài khoản quản trị/đăng ký), khóa mã PIN Chủ nhà, chống dò mật khẩu theo tần suất.", "Backend Auth, Web, App"),
            ("FR-09", "Phân quyền 3 tầng RBAC phía máy chủ", "Cưỡng chế quyền truy cập theo đúng vai trò Cấp 1/2/3 trên mọi API REST, WebSocket và hàm AI; từ chối bằng câu tiếng Việt cố định nếu vượt quyền.", "Backend Auth + Live"),
            ("FR-10", "Cấp quyền Khách bằng mã QR động", "Chủ nhà sinh mã QR chứa chữ ký TOTP thay đổi mỗi 10 giây (chờ quét tối đa 180 giây), gắn thời hạn phiên (TTL) và cho phép thu hồi tức thì.", "Web, Android QR, Backend"),
            ("FR-11", "Mô hình 3D Digital Twin & /wokwi", "Hiển thị nhà 3D tương tác 14 module đồng bộ trạng thái thật (đèn sáng, cửa xoay 90°, bơm phun nước); trang /wokwi kiểm tra đấu nối PCB-Direct 40 dây.", "Web Three.js"),
            ("FR-12", "Nhật ký kiểm toán & Tri thức RAG", "Ghi nhận đầy đủ mọi lệnh thành công/bị từ chối kèm thời điểm UTC+7, tài khoản, nguồn lệnh; hỗ trợ trợ lý tra cứu lịch sử qua Knowledge RAG.", "SQLite WAL, Web /logs"),
            ("FR-13", "Nạp USB & Cấu hình Wi-Fi động", "Hỗ trợ script 1 lệnh nạp firmware qua USB và truyền SSID/Mật khẩu/IP Server qua Serial lưu vào LittleFS (/wifi_config.json), không lưu cứng mật khẩu trong mã nguồn.", "Firmware ESP8266, PowerShell"),
            ("FR-14", "Vận hành ngoại tuyến an toàn A1–A4", "Khi mất Wi-Fi/Server, ESP8266 chuyển sang Offline FSM: phục vụ HTTP cục bộ cổng 80 cho lệnh cơ bản, khóa cứng cấm mở cửa chính (D1=0°), tự ngắt bơm/còi và tự đồng bộ lại khi có mạng.", "Firmware ESP8266 + Resync"),
        ],
        col_widths_cm=[1.6, 3.2, 7.6, 3.1],
        font_pt=10.5,
        center_cols=(0,),
    )

    rb.add_para(
        "Để đảm bảo nguyên tắc đặc quyền tối thiểu (Principle of Least Privilege), Bảng 2.2 và Hình 2.1 đặc tả ma trận phân quyền 3 tầng RBAC "
        "cùng cơ chế bắt tay mã QR động TOTP 10 giây chống chụp màn hình dùng lại."
    )
    rb.add_table(
        "Ma trận phân quyền 3 tầng RBAC theo thiết bị, giao diện và hành động hệ thống",
        ["Thiết bị / Tính năng", "Cấp 1 (Chủ nhà)", "Cấp 2 (Thành viên)", "Cấp 3 (Khách QR)", "Ghi chú bảo mật"],
        [
            ("Đèn phòng khách (D0) & Đèn phòng ngủ (D4)", "Cho phép", "Cho phép", "Cho phép", "Cơ bản cho sinh hoạt"),
            ("Máy bơm tưới cây (D6) & Mạch loa (D7)", "Cho phép", "Cho phép", "Chặn cứng", "Khách không tác động bơm/loa"),
            ("Cửa chính Servo SG90 (D1)", "Cho phép", "Chặn cứng", "Chặn cứng", "Khóa cứng khi mất mạng (A3)"),
            ("Còi báo động 5V TMB12A05 (D8)", "Cho phép", "Chặn cứng", "Chặn cứng", "Chỉ Chủ nhà kích/tắt báo động"),
            ("Xem 3 cảm biến (DHT11, Đất, KY-037)", "Đầy đủ", "Đầy đủ", "Cơ bản (Nhiệt/Ẩm)", "Ẩn chi tiết quản trị với Khách"),
            ("Giọng nói Gemini 3.8 Live (/ws/live)", "Toàn quyền 20 tool", "Lọc theo quyền C2", "Lọc theo quyền C3", "Cưỡng chế trên từng Function Call"),
            ("Hẹn giờ / Luật tự động / Lệnh tùy chỉnh", "Toàn quyền", "Hẹn giờ cơ bản", "Chặn cứng", "Tự kiểm tra quyền tại thời điểm chạy"),
            ("Trang mô phỏng phần cứng (/wokwi)", "Cho phép", "Cho phép", "Chặn cứng", "Thuộc tính data-max-tier=2 + Server guard"),
            ("Nhật ký kiểm toán (/logs) & Quản trị TK/QR", "Cho phép", "Chặn cứng", "Chặn cứng", "Chỉ Cấp 1 xem log và tạo/thu hồi QR"),
        ],
        col_widths_cm=[4.4, 2.3, 2.5, 2.5, 3.8],
        font_pt=10.5,
        center_cols=(1, 2, 3),
    )

    rb.add_figure(
        sw_dir / "sw_arch_rbac_qr.png",
        "Mô hình phân quyền 3 tầng RBAC và luồng bắt tay mã QR động TOTP 10 giây",
        max_width_cm=15.0,
        max_height_cm=8.0,
    )

    rb.add_para(
        "Luồng tương tác giọng nói AI tiếng Việt đóng vai trò trung tâm của trải nghiệm người dùng. Hình 2.2 mô tả trình tự xử lý "
        "một lượt hội thoại từ lúc thu âm PCM 16 kHz trên trình duyệt hoặc ứng dụng Android, đi qua lớp lọc dội âm ServerEchoGuard, "
        "chuyển tiếp tới Gemini 3.8 Live API, kiểm tra phân quyền phía máy chủ, thực thi theo ba nhánh (lệnh trực tiếp, lệnh tùy chỉnh xác nhận 1 lần, "
        "hoặc từ chối vượt quyền) và phản hồi bằng giọng nói Aoede PCM 24 kHz."
    )
    rb.add_figure(
        sw_dir / "sw_arch_voice_flow.png",
        "Sơ đồ tuần tự luồng xử lý giọng nói Gemini 3.8 Live, Echo Guard, RBAC và lệnh tùy chỉnh",
        max_width_cm=15.0,
        max_height_cm=8.5,
    )

    rb.add_h2("2.3. Yêu cầu phi chức năng")
    rb.add_para(
        "Bên cạnh tính đầy đủ của chức năng, hệ thống nhà thông minh có yếu tố phần cứng thực tế đòi hỏi các ràng buộc phi chức năng chặt chẽ "
        "về hiệu năng thời gian thực, độ bền cơ điện, bảo mật thông tin và khả năng bảo trì lâu dài. Các chỉ tiêu mục tiêu được định lượng trong Bảng 2.3."
    )
    rb.add_table(
        "Đặc tả các yêu cầu phi chức năng và chỉ tiêu kỹ thuật mục tiêu",
        ["Hạng mục", "Chỉ tiêu mục tiêu cụ thể", "Phương pháp kiểm chứng"],
        [
            ("Độ trễ điều khiển cục bộ", "Lệnh REST/MQTT bật tắt thiết bị < 300 ms trong mạng LAN; đồng bộ giao diện Web/App qua SSE < 500 ms.", "Đo thực nghiệm & pytest tích hợp"),
            ("Độ trễ & chất lượng giọng nói AI", "Luồng PCM 16 kHz khung 20 ms (640 B), phản hồi âm thanh Aoede 24 kHz; 100% tiếng Việt, không lẫn tiếng Anh; 0 tự kích hoạt lại do dội loa.", "Kiểm thử luồng thoại dài trên Web & APK"),
            ("An toàn điện & Boot-strap ESP8266", "Hoạt động hoàn toàn ở điện áp thấp an toàn 5V DC / 3,3V DC (0 mạch 220V AC); khởi động ổn định 100% không treo boot ở D3/D4/D8; 0 ERC & 0 DRC trên PCB.", "KiCad ERC/DRC, kiểm tra mạch thực tế"),
            ("Ràng buộc cơ khí & In 3D", "0 ốc vít, 0 keo dán, 0% support; 0 va chạm 3D BRep; độ võng đáy <= 0,50 mm dưới tải 250 g; hệ số an toàn mô-men Servo SG90 >= 5×; khối lượng nhựa <= 680 g.", "FreeCAD BRep verify, FEA-lite, PrusaSlicer CLI"),
            ("Bảo mật thông tin & Truy cập từ xa", "Không lưu mật khẩu Wi-Fi hay API key vào Git; mật khẩu tài khoản băm PBKDF2/scrypt; truy cập từ xa mã hóa TLS qua Tailscale Funnel + Vercel không mở port NAT.", "Kiểm toán mã nguồn & kiểm thử bảo mật"),
            ("Độ tin cậy dữ liệu & Khả năng phục hồi", "SQLite 3NF chế độ WAL đọc/ghi đồng thời không khóa; kết nối lại Wi-Fi/MQTT theo hàm mũ 1s–30s không reset Watchdog; tự đồng bộ trạng thái sau mất mạng.", "pytest offline FSM & kiểm thử hồi quy"),
            ("Tính nhất quán đa nền tảng", "Giao diện Web đáp ứng tốt cả máy tính (1366×768) và di động (412×915) ở chế độ Sáng/Tối; Android APK tương thích Android >= 8.0 (minSdk 26), 0 crash/ANR.", "Playwright headless QA & ADB E2E APK"),
        ],
        col_widths_cm=[3.4, 8.3, 3.8],
        font_pt=10.5,
    )

    rb.add_h2("2.4. Kết luận Chương 2")
    rb.add_para(
        "Chương 2 đã hoàn thiện bức tranh phân tích bài toán thông qua mô hình 3 nhóm tác nhân, 14 yêu cầu chức năng trọng tâm, "
        "ma trận phân quyền 3 tầng RBAC gắn với mã QR động TOTP 10 giây và 7 nhóm tiêu chí phi chức năng có thể đo kiểm định lượng. "
        "Những đặc tả này là căn cứ trực tiếp để Chương 3 lựa chọn linh kiện phần cứng, giao thức truyền thông và bộ công cụ phần mềm tối ưu."
    )
