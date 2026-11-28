"""Chapters 1 & 2: Tổng quan về đề tài & Khảo sát và phân tích yêu cầu."""

from __future__ import annotations

import pathlib

from .docx_helpers import ReportBuilder


def build_chapter_1(rb: ReportBuilder, assets_dir: pathlib.Path) -> None:
    _ = assets_dir
    rb.add_chapter(1, "TỔNG QUAN VỀ ĐỀ TÀI", first_chapter=True)
    rb.add_para(
        "Trong Chương 1, em trình bày bối cảnh thực tế và những hạn chế còn gặp ở các hệ thống nhà thông minh hiện nay. "
        "Từ đó, chương xác định mục tiêu, phạm vi phần cứng – phần mềm của đồ án và phương pháp thực hiện xuyên suốt quá trình xây dựng hệ thống."
    )

    rb.add_h2("1.1. Đặt vấn đề")
    rb.add_para(
        "Những năm gần đây, thiết bị Internet vạn vật (IoT) có giá thành ngày càng hợp lý giúp khái niệm nhà thông minh "
        "trở nên gần gũi hơn với người dùng phổ thông. Chỉ với một vi điều khiển hỗ trợ Wi-Fi và điện thoại thông minh, "
        "người dùng có thể bật tắt đèn hay theo dõi nhiệt độ trong phòng từ xa. Tuy nhiên, trong sinh hoạt hàng ngày, "
        "việc liên tục mở điện thoại, tìm đúng ứng dụng rồi bấm từng nút công tắc vẫn khá bất tiện, nhất là khi tay đang bận nấu ăn, "
        "đang mang đồ hoặc chuẩn bị đi ngủ. Do đó, điều khiển thiết bị bằng giọng nói tiếng Việt tự nhiên kết hợp các kịch bản tự động "
        "là nhu cầu rất thiết thực."
    )
    rb.add_para(
        "Qua tìm hiểu các nền tảng thương mại và một số mô hình đồ án mẫu, em nhận thấy vẫn còn nhiều điểm bất cập khi đưa vào sử dụng thực tế. "
        "Thứ nhất là vấn đề tương tác giọng nói tiếng Việt. Nhiều sản phẩm phổ thông chủ yếu tối ưu cho tiếng Anh nên còn hạn chế "
        "khi hiểu các câu nói tiếng Việt dài hoặc chứa nhiều yêu cầu gộp trong một lượt. Với hướng tự ghép nối từng bước riêng lẻ "
        "(nhận dạng giọng nói thành văn bản, xử lý từ khóa rồi tổng hợp giọng đọc), độ trễ phản hồi thường kéo dài vài giây. "
        "Ngoài ra, nếu loa phát phản hồi đặt gần micro mà không có cơ chế chống dội âm, trợ lý rất dễ tự nghe lại tiếng của mình và kích hoạt nhầm."
    )
    rb.add_para(
        "Thứ hai là bài toán phân quyền sử dụng trong hộ gia đình. Một ngôi nhà thường có nhiều đối tượng cùng tương tác với thiết bị "
        "như chủ nhà, các thành viên khác và khách đến chơi trong vài giờ. Phần lớn ứng dụng IoT hiện nay chỉ cho phép chia sẻ toàn bộ tài khoản "
        "hoặc cấp quyền cố định dài hạn. Nếu muốn cho khách bật tắt đèn phòng khách trong một buổi tối, chủ nhà phải tạo tài khoản mới hoặc chia sẻ quyền quá rộng, "
        "gây rủi ro khi khách hoặc người dùng không có thẩm quyền vô tình mở cửa chính hay kích hoạt còi báo động."
    )
    rb.add_para(
        "Thứ ba là độ ổn định của phần cứng và an toàn khi mất mạng. Ở nhiều mô hình thử nghiệm, mạch điện thường được lắp tạm trên bảng cắm thử (breadboard) "
        "nên dây nối dễ lỏng, tiếp xúc kém. Khi động cơ servo hoặc máy bơm mini 5V khởi động, dòng tăng đột biến mà thiếu tụ lọc nguồn và diode dập xung ngược "
        "sẽ gây sụt áp, làm vi điều khiển ESP8266 tự khởi động lại. Bên cạnh đó, các hệ thống phụ thuộc hoàn toàn vào máy chủ từ xa sẽ tê liệt khi mất Internet; "
        "ngược lại, nếu cho phép điều khiển cục bộ không ràng buộc, khóa cửa chính lại có nguy cơ bị kích mở ngoài ý muốn khi hệ thống mất kết nối."
    )
    rb.add_para(
        "Thứ tư là vấn đề bảo mật thông tin mạng Wi-Fi và tính trực quan khi giám sát. Cách làm quen thuộc là ghi thẳng tên mạng (SSID) và mật khẩu Wi-Fi "
        "trong mã nguồn nhúng buộc người làm phải biên dịch và nạp lại chương trình mỗi khi đổi địa điểm thử nghiệm, đồng thời dễ làm lộ thông tin mạng. "
        "Song song với đó, giao diện quản lý dạng danh sách nút bấm thuần túy chưa thể hiện trực quan vị trí của từng đèn, cửa hay cảm biến trong không gian nhà, "
        "khiến người dùng khó bao quát nhanh trạng thái chung."
    )
    rb.add_para(
        "Từ những vấn đề thực tế nêu trên, em chọn thực hiện đề tài “Thiết kế và xây dựng hệ thống nhà thông minh điều khiển bằng giọng nói AI "
        "tích hợp mô hình 3D và ứng dụng di động”. Đồ án hướng tới xây dựng một mô hình thử nghiệm điện áp thấp 5V DC hoàn chỉnh từ mạch điện tử, "
        "chương trình nhúng đến máy chủ và giao diện người dùng, bảo đảm dễ vận hành, an toàn và có thể kiểm chứng rõ ràng từng chức năng."
    )

    rb.add_h2("1.2. Mục tiêu đề ra")
    rb.add_para(
        "Thay vì mở rộng dàn trải sang nhiều loại tải điện lưới 220V AC tiềm ẩn nguy cơ mất an toàn trong môi trường thử nghiệm, "
        "em giới hạn phạm vi phần cứng ở cấu hình gọn và cố định để tập trung vào độ tin cậy. Hệ thống sử dụng một vi điều khiển "
        "NodeMCU ESP8266 v2 (Amica) quản lý đúng 6 thiết bị chấp hành gồm đèn phòng khách, đèn phòng ngủ, cửa chính dùng động cơ servo SG90, "
        "máy bơm tưới cây mini 5V, nguồn mạch khuếch đại loa PAM8403 và còi báo động 5V; đồng thời thu thập dữ liệu từ 3 cảm biến gồm "
        "nhiệt độ – độ ẩm không khí DHT11, độ ẩm đất LM393/YL-69 và cảm biến âm thanh KY-037."
    )
    rb.add_para(
        "Về mạch điện tử, mục tiêu của em là loại bỏ hoàn toàn bảng cắm thử bằng cách thiết kế bo mạch trung tâm PCB Hub DIY v3 một lớp "
        "(kích thước 100 × 80 × 1,6 mm) đi dây trực tiếp tới các khối thiết bị và cảm biến theo hợp đồng 10 chân cố định. Bo mạch tích hợp đầy đủ "
        "9 tụ lọc nguồn (C1–C9), 2 diode dập xung ngược 1N4007 (D1, D2) và mạch lái transistor S8050 cho tải bơm, bảo đảm không còn lỗi nguyên lý (ERC) "
        "hay lỗi mạch in (DRC) và tránh xung đột các chân khởi động của ESP8266. Bên cạnh phần mạch điện, em cũng thiết kế thêm một vỏ mô hình nhà in 3D "
        "làm khung bảo vệ và gá lắp cố định các cảm biến, đèn, cửa và máy bơm cho gọn gàng khi thử nghiệm."
    )
    rb.add_para(
        "Về điều khiển thông minh, hệ thống tích hợp dịch vụ nhận dạng và hội thoại giọng nói (Gemini Live) qua kết nối WebSocket hai chiều bằng tiếng Việt, "
        "đi kèm bộ chống dội âm phía máy chủ để loa phát lại không gây kích hoạt nhầm micro. Trợ lý được cung cấp bộ hàm công cụ điều khiển thiết bị "
        "theo nguyên tắc thực thi lệnh trước rồi phản hồi ngắn gọn. Người dùng cũng có thể dạy tổ hợp lệnh mới trực tiếp bằng lời nói "
        "(có bước hỏi xác nhận đúng một lần trước khi lưu), kết hợp sử dụng hai nhóm tự động hóa độc lập gồm hẹn giờ – lịch lặp và luật điều kiện theo cảm biến."
    )
    rb.add_para(
        "Về bảo mật và an toàn ngoại tuyến, hệ thống áp dụng phân quyền 3 tầng (Chủ nhà, Thành viên gia đình và Khách tạm thời đăng nhập bằng mã QR động có thời hạn) "
        "và kiểm tra quyền chặt phía máy chủ trên cả giao diện bấm nút lẫn lệnh giọng nói. Thông tin Wi-Fi và địa chỉ máy chủ được cấu hình động qua cổng USB Serial "
        "và lưu trong bộ nhớ LittleFS của ESP8266 để không lộ mật khẩu trong mã nguồn. Khi mất mạng hoặc mất kết nối máy chủ, vi điều khiển tự chuyển sang chế độ ngoại tuyến an toàn, "
        "khóa cứng cửa chính ở trạng thái đóng, ngắt bơm và còi, rồi tự đồng bộ lại trạng thái khi mạng ổn định."
    )
    rb.add_para(
        "Về giao diện sử dụng, đồ án xây dựng trang Web hiển thị mô hình nhà 3D bằng Three.js phản ánh trực tiếp trạng thái hoạt động của từng thiết bị "
        "cùng trang kiểm tra sơ đồ đấu nối /wokwi, đồng thời phát triển ứng dụng di động Android viết bằng Kotlin và Jetpack Compose hỗ trợ quét mã QR và điều khiển giọng nói. "
        "Trong phạm vi thử nghiệm của đồ án, máy chủ chạy trên laptop cá nhân, hỗ trợ truy cập trong mạng nội bộ và qua Internet."
    )

    rb.add_h2("1.3. Phương pháp thực hiện")
    rb.add_para(
        "Để tránh tình trạng sơ đồ mạch, chương trình nhúng và giao diện phần mềm không khớp chân hoặc sai tên thiết bị trong quá trình làm, "
        "em bắt đầu bằng việc lập một bảng quy ước phần cứng thống nhất cho cả 10 chân sử dụng trên NodeMCU ESP8266. Bảng quy ước này ghi rõ "
        "chân kết nối, điện áp hoạt động, linh kiện bảo vệ và mã định danh từng thiết bị. Dựa trên đó, em thiết kế sơ đồ nguyên lý và bố trí mạch in "
        "trên phần mềm KiCad, chạy kiểm tra ERC và DRC trước khi viết chương trình nhúng bằng PlatformIO."
    )
    rb.add_para(
        "Ở tầng máy chủ, em chọn ngôn ngữ Python với nền tảng FastAPI chạy theo cơ chế bất đồng bộ (asyncio). Cách tổ chức này phù hợp khi máy chủ "
        "phải duy trì song song nhiều kết nối thời gian thực gồm luồng âm thanh WebSocket tới dịch vụ Gemini Live, kênh cập nhật giao diện SSE "
        "và giao tiếp MQTT/HTTP với vi điều khiển ESP8266. Toàn bộ dữ liệu tài khoản, phiên đăng nhập, lịch hẹn, luật tự động, lệnh tùy chỉnh "
        "và nhật ký kiểm toán được lưu trên cơ sở dữ liệu SQLite bật chế độ ghi trước (WAL) để giảm tranh chấp khi nhiều yêu cầu truy cập cùng lúc."
    )
    rb.add_para(
        "Ở phía ứng dụng người dùng, trang Web được xây dựng bằng HTML, CSS, JavaScript kết hợp thư viện Three.js để dựng mô hình nhà 3D tương tác trực tiếp trên trình duyệt, "
        "hỗ trợ cả màn hình máy tính và điện thoại. Ứng dụng Android được xây dựng bằng Kotlin và Jetpack Compose, dùng chung bộ giao tiếp REST API và WebSocket của máy chủ "
        "nhằm giữ hành vi điều khiển và kiểm soát phân quyền giống hệt trên nền Web."
    )
    rb.add_para(
        "Về kiểm chứng, em áp dụng cách kiểm thử theo từng lớp ngay sau khi hoàn thiện mỗi chức năng. Các phần logic quan trọng như máy trạng thái ngoại tuyến của firmware, "
        "kiểm tra ranh giới phân quyền 3 tầng, bộ lập lịch hẹn giờ, luật cảm biến và bộ lọc chống dội âm được kiểm tra bằng kịch bản tự động. "
        "Giao diện Web và ứng dụng Android cũng được kiểm tra đầy đủ theo cả 3 vai trò người dùng để phát hiện sớm lỗi hiển thị và lỗi vượt quyền trước khi tổng hợp kết quả."
    )

    rb.add_h2("1.4. Kết luận Chương 1")
    rb.add_para(
        "Chương 1 đã trình bày lý do chọn đề tài, phân tích bốn nhóm hạn chế thực tế của các hệ thống nhà thông minh hiện nay và xác định rõ mục tiêu, "
        "phạm vi phần cứng 6 thiết bị – 3 cảm biến cùng phương pháp triển khai xuyên suốt từ bo mạch điện tử PCB-Direct đến máy chủ giọng nói và ứng dụng người dùng. "
        "So sánh chi tiết hệ thống với các sản phẩm nhà thông minh thương mại sẽ được trình bày ở Chương 4. "
        "Tiếp theo, Chương 2 sẽ khảo sát sâu hơn bài toán sử dụng trong hộ gia đình và đặc tả đầy đủ các yêu cầu chức năng, phân quyền cũng như yêu cầu phi chức năng của hệ thống."
    )


def build_chapter_2(rb: ReportBuilder, assets_dir: pathlib.Path) -> None:
    sw_dir = assets_dir / "software"
    rb.add_chapter(2, "KHẢO SÁT VÀ PHÂN TÍCH YÊU CẦU")
    rb.add_para(
        "Trong Chương 2, em khảo sát các tình huống sử dụng thực tế trong hộ gia đình, phân chia rõ ba nhóm người dùng và đặc tả bộ yêu cầu chức năng, "
        "ma trận phân quyền 3 tầng RBAC cùng các yêu cầu phi chức năng làm cơ sở cho quá trình thiết kế."
    )

    rb.add_h2("2.1. Khảo sát bài toán và phân nhóm người dùng")
    rb.add_para(
        "Trong sinh hoạt hằng ngày, người dùng tương tác với thiết bị trong nhà theo ba bối cảnh quen thuộc: điều khiển tại chỗ bằng giọng nói rảnh tay "
        "(khi đang nấu ăn, mang đồ hoặc chuẩn bị đi ngủ), theo dõi và điều khiển từ xa qua Internet (kiểm tra cửa chính, tưới cây khi vắng nhà), "
        "và để hệ thống tự phản ứng theo cảm biến hoặc lịch trình (đất khô tự tưới, tiếng vỗ tay bật đèn)."
    )
    rb.add_para(
        "Để tiện sử dụng mà vẫn giữ an toàn cho các thiết bị nhạy cảm, hệ thống chia người dùng thành ba nhóm vai trò tách biệt. "
        "Chủ nhà (Cấp 1) có toàn quyền với cả 6 thiết bị chấp hành, bao gồm hai thiết bị an ninh là cửa chính (servo SG90, D1) và còi báo động (D8); "
        "đồng thời quản lý lịch hẹn, luật tự động, lệnh tùy chỉnh, nhật ký hoạt động (/logs), tài khoản thành viên và mã QR cho khách."
    )
    rb.add_para(
        "Thành viên gia đình (Cấp 2) sử dụng thường xuyên các tiện ích sinh hoạt gồm đèn phòng khách, đèn phòng ngủ, máy bơm tưới cây và nguồn mạch loa, "
        "xem thông số cảm biến, trang sơ đồ đấu nối (/wokwi) và đặt hẹn giờ cơ bản. Hệ thống chặn cứng quyền đóng mở cửa chính, bật tắt còi báo động, "
        "xem nhật ký hệ thống và quản trị tài khoản đối với nhóm này để tránh thao tác nhầm."
    )
    rb.add_para(
        "Khách tạm thời (Cấp 3) là người ghé chơi trong vài giờ nên không cần tài khoản cố định mà đăng nhập bằng mã QR động có thời hạn phiên (TTL). "
        "Khách chỉ được bật tắt hai đèn và hỏi nhiệt độ, độ ẩm cơ bản; mọi lệnh chạm vào cửa, còi, bơm, loa hoặc trang cấu hình đều bị chặn ở cả giao diện lẫn máy chủ. "
        "Song song với ba nhóm người dùng, nút phần cứng NodeMCU ESP8266 đóng vai trò chấp hành lệnh, gửi dữ liệu cảm biến định kỳ và tự giữ trạng thái an toàn khi mất mạng."
    )

    rb.add_h2("2.2. Yêu cầu chức năng")
    rb.add_para(
        "Bám sát cấu hình phần cứng 6 thiết bị chấp hành và 3 cảm biến, em tổng hợp 14 yêu cầu chức năng chính (FR-01 đến FR-14) trong Bảng 2.1."
    )
    rb.add_table(
        "Đặc tả 14 nhóm yêu cầu chức năng của hệ thống",
        ["Mã YC", "Nhóm chức năng", "Mô tả yêu cầu chi tiết", "Phạm vi"],
        [
            ("FR-01", "Điều khiển 6 thiết bị", "Bật/tắt đèn phòng khách (D0), đèn ngủ (D4), máy bơm (D6), nguồn loa PAM8403 (D7), còi báo động (D8); đóng/mở cửa servo SG90 (D1: 0°/90°).", "Web, App, Thoại, ESP8266"),
            ("FR-02", "Giám sát 3 cảm biến", "Đọc và cập nhật liên tục nhiệt độ/độ ẩm không khí (DHT11, D2), độ ẩm đất 0–100% (LM393+YL-69, A0) và tiếng vỗ tay/âm thanh (KY-037, D5).", "ESP8266 → Máy chủ → UI"),
            ("FR-03", "Giọng nói tiếng Việt", "Hội thoại hai chiều qua dịch vụ nhận dạng và hội thoại giọng nói (Gemini Live), thực thi lệnh thiết bị trước rồi phản hồi tiếng Việt ngắn gọn.", "Web, App, Máy chủ"),
            ("FR-04", "Chống dội âm micro", "Chặn thu âm khi loa trợ lý đang phát (ServerEchoGuard) kết hợp nhận diện tiếng nói tiếng Việt để tránh trợ lý tự nghe lại giọng mình.", "Cầu nối âm thanh"),
            ("FR-05", "Dạy lệnh tùy chỉnh", "Dạy tổ hợp lệnh mới bằng lời nói (ví dụ: 'Chế độ đi ngủ'); hỏi xác nhận đúng 1 lần trước khi lưu và chạy trực tiếp cho các lần sau.", "Trợ lý thoại + SQLite"),
            ("FR-06", "Hẹn giờ & lịch lặp", "Đặt hẹn đếm ngược hoặc theo mốc giờ (TimersPool), lặp một lần/hàng ngày/hàng tuần/hàng tháng; hỗ trợ sửa và hủy hẹn bằng thoại hoặc UI.", "Máy chủ, Web, App"),
            ("FR-07", "Luật tự động hóa", "Cài đặt luật điều kiện theo cảm biến và trạng thái (RulesPool), gồm tự bật bơm khi độ ẩm đất < 40% và tắt khi >= 70% tránh bật tắt liên tục.", "Máy chủ, ESP8266"),
            ("FR-08", "Xác thực nhiều lớp", "Đăng nhập mật khẩu băm an toàn, OTP email khi đăng ký/quên mật khẩu, mã PIN chủ nhà và giới hạn tần suất nhập sai.", "Máy chủ, Web, App"),
            ("FR-09", "Phân quyền 3 tầng", "Kiểm tra quyền Cấp 1/2/3 phía máy chủ trên mọi REST API, WebSocket và hàm công cụ thoại; từ chối bằng câu tiếng Việt cố định nếu vượt quyền.", "Máy chủ + Thoại"),
            ("FR-10", "Mã QR động cho Khách", "Sinh mã QR chứa chữ ký TOTP đổi mỗi 10 giây (chờ quét tối đa 180 giây), gắn thời hạn phiên (TTL) và cho phép Chủ nhà thu hồi ngay.", "Web, App QR, Máy chủ"),
            ("FR-11", "Nhà 3D và /wokwi", "Hiển thị mô hình nhà 3D (Three.js) đồng bộ trạng thái đèn, cửa 90°, bơm nước; cung cấp trang /wokwi kiểm tra sơ đồ đấu nối PCB-Direct.", "Giao diện Web 3D"),
            ("FR-12", "Nhật ký & tra cứu", "Lưu lịch sử mọi lệnh thành công và bị từ chối kèm giờ UTC+7, tài khoản, nguồn lệnh; hỗ trợ xem trên /logs và hỏi lại qua giọng nói.", "SQLite WAL, /logs"),
            ("FR-13", "Cấu hình Wi-Fi USB", "Nạp SSID, mật khẩu Wi-Fi và địa chỉ máy chủ qua cổng USB Serial lưu vào LittleFS (/wifi_config.json), không ghi cứng mật khẩu trong mã nguồn.", "Firmware ESP8266"),
            ("FR-14", "Ngoại tuyến an toàn", "Khi mất mạng/máy chủ, ESP8266 chạy Offline FSM (A1–A4): phục vụ HTTP cục bộ, khóa cứng cửa chính (D1 = 0°), tắt bơm/còi và tự đồng bộ lại.", "Firmware ESP8266"),
        ],
        col_widths_cm=[1.4, 3.1, 8.2, 2.8],
        font_pt=10.0,
        center_cols=(0,),
    )

    rb.add_para(
        "Theo nguyên tắc đặc quyền tối thiểu, toàn bộ quyền hạn được cưỡng chế phía máy chủ thay vì chỉ ẩn nút ở giao diện. "
        "Bảng 2.2 trình bày ma trận phân quyền 3 tầng RBAC, còn Hình 2.1 minh họa cấu trúc ba nhóm quyền cùng luồng bắt tay mã QR động TOTP chu kỳ 10 giây "
        "nhằm chống việc chụp màn hình mã QR cũ để đăng nhập lại."
    )
    rb.add_table(
        "Ma trận phân quyền 3 tầng RBAC theo thiết bị và chức năng hệ thống",
        ["Thiết bị / Chức năng", "Cấp 1 (Chủ nhà)", "Cấp 2 (Thành viên)", "Cấp 3 (Khách QR)", "Ghi chú bảo mật"],
        [
            ("Đèn phòng khách (D0) & Đèn ngủ (D4)", "Cho phép", "Cho phép", "Cho phép", "Phục vụ sinh hoạt cơ bản"),
            ("Máy bơm (D6) & Nguồn loa (D7)", "Cho phép", "Cho phép", "Chặn cứng", "Khách không tác động bơm/loa"),
            ("Cửa chính Servo SG90 (D1)", "Cho phép", "Chặn cứng", "Chặn cứng", "Khóa cứng đóng khi mất mạng"),
            ("Còi báo động 5V TMB12A05 (D8)", "Cho phép", "Chặn cứng", "Chặn cứng", "Chỉ Chủ nhà kích/tắt báo động"),
            ("Xem 3 cảm biến (DHT11, Đất, KY-037)", "Đầy đủ", "Đầy đủ", "Nhiệt / Ẩm", "Giới hạn thông tin với Khách"),
            ("Giọng nói Gemini Live (/ws/live)", "Toàn quyền", "Lọc theo Cấp 2", "Lọc theo Cấp 3", "Kiểm tra quyền trên từng lệnh"),
            ("Hẹn giờ / Luật tự động / Lệnh tùy chỉnh", "Toàn quyền", "Hẹn giờ cơ bản", "Chặn cứng", "Kiểm tra lại khi đến giờ chạy"),
            ("Trang sơ đồ đấu nối (/wokwi)", "Cho phép", "Cho phép", "Chặn cứng", "Chặn ở cả giao diện và máy chủ"),
            ("Nhật ký (/logs) & Quản trị TK/QR", "Cho phép", "Chặn cứng", "Chặn cứng", "Chỉ Chủ nhà xem log, thu hồi QR"),
        ],
        col_widths_cm=[4.5, 2.2, 2.4, 2.4, 4.0],
        font_pt=10.0,
        center_cols=(1, 2, 3),
    )

    rb.add_figure(
        sw_dir / "sw_arch_rbac_qr.png",
        "Mô hình phân quyền 3 tầng RBAC và luồng bắt tay mã QR động TOTP chu kỳ 10 giây",
        max_width_cm=15.0,
        max_height_cm=7.8,
        kind="diagram",
    )

    rb.add_para(
        "Mọi phiên hội thoại qua dịch vụ Gemini Live đều gắn trực tiếp với phiên đăng nhập của người dùng hiện tại. "
        "Trước khi gửi lệnh xuống ESP8266, máy chủ đối chiếu lại quyền của vai trò đang đăng nhập; khi Khách hết hạn phiên hoặc bị Chủ nhà thu hồi, "
        "kết nối WebSocket đang mở cũng lập tức bị ngắt."
    )

    rb.add_h2("2.3. Yêu cầu phi chức năng")
    rb.add_para(
        "Bên cạnh các chức năng trên, hệ thống có phần cứng thực tế cần đáp ứng sáu nhóm chỉ tiêu phi chức năng về tốc độ phản hồi, "
        "an toàn điện áp thấp, bảo mật và khả năng tự phục hồi như tổng hợp trong Bảng 2.3."
    )
    rb.add_table(
        "Đặc tả các yêu cầu phi chức năng và chỉ tiêu kiểm tra",
        ["Hạng mục", "Chỉ tiêu mục tiêu cụ thể", "Phương pháp kiểm tra"],
        [
            ("Độ trễ điều khiển", "Lệnh bật/tắt trong mạng nội bộ < 300 ms; đồng bộ trạng thái lên Web và Android qua SSE < 500 ms.", "Đo thực nghiệm và kiểm thử tích hợp"),
            ("Luồng thoại tiếng Việt", "Thu âm PCM 16 kHz (khung 20 ms), phản hồi tiếng Việt 24 kHz từ dịch vụ Gemini Live; không tự kích hoạt do dội loa.", "Thử nghiệm hội thoại trên Web và Android"),
            ("An toàn điện & ESP8266", "Toàn mạch chạy 5V DC / 3,3V DC (0 mạch 220V AC); khởi động ổn định không treo ở D3, D4, D8; PCB đạt 0 lỗi ERC và 0 lỗi DRC.", "KiCad ERC/DRC và kiểm tra sơ đồ chân"),
            ("Bảo mật và truy cập", "Không ghi cứng mật khẩu Wi-Fi hay khóa API trong mã nguồn; băm mật khẩu an toàn; phiên khách QR hết hạn tự hủy; truy cập an toàn trong mạng nội bộ và qua Internet.", "Rà soát mã nguồn và kiểm thử quyền"),
            ("Dữ liệu và ngoại tuyến", "SQLite WAL đọc ghi đồng thời không khóa; khi mất mạng, ESP8266 khóa cứng cửa chính 0°, tắt bơm/còi, tự kết nối lại không treo Watchdog và đồng bộ lại.", "Kiểm thử máy trạng thái ngoại tuyến"),
            ("Tương thích giao diện", "Web hiển thị rõ trên máy tính và điện thoại ở chế độ Sáng/Tối; Android hỗ trợ từ Android 8.0 trở lên (minSdk 26), hoạt động ổn định không văng ứng dụng.", "Kiểm thử đa kích thước màn hình và Android"),
        ],
        col_widths_cm=[3.2, 8.8, 3.5],
        font_pt=10.0,
    )

    rb.add_h2("2.4. Kết luận Chương 2")
    rb.add_para(
        "Chương 2 đã phân tích bài toán sử dụng thực tế trong hộ gia đình, xác định rõ giới hạn quyền của ba nhóm người dùng cùng vai trò nút phần cứng ESP8266. "
        "Bộ 14 yêu cầu chức năng, ma trận phân quyền 3 tầng RBAC kèm mã QR động 10 giây và 6 nhóm yêu cầu phi chức năng này là căn cứ trực tiếp "
        "để Chương 3 trình bày cơ sở lý thuyết và lựa chọn các linh kiện phần cứng, giao thức truyền thông cùng công nghệ phần mềm phù hợp."
    )
