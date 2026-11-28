"""Chapter 3: Công nghệ và linh kiện sử dụng (Electronic Circuit, PCB Hub DIY v3, Firmware & Core Tech)."""

from __future__ import annotations

import pathlib

from .code_excerpts import load_code_excerpt
from .docx_helpers import ReportBuilder


def build_chapter_3(rb: ReportBuilder, assets_dir: pathlib.Path) -> None:
    demo_dir = assets_dir / "demo"
    diagrams_dir = assets_dir / "diagrams"
    logos_dir = assets_dir / "logos"
    sw_dir = assets_dir / "software"

    rb.add_chapter(3, "CÔNG NGHỆ VÀ LINH KIỆN SỬ DỤNG")
    rb.add_para(
        "Trong chương này, em trình bày chi tiết thiết kế mạch điện tử làm trung tâm của hệ thống nhà thông minh, "
        "từ vi điều khiển NodeMCU ESP8266 v2 Amica, các cảm biến, thiết bị chấp hành, khối nguồn và mạch bảo vệ "
        "hàn trực tiếp trên bo PCB Hub DIY v3, đến lưu đồ hoạt động firmware và các công nghệ phần mềm cốt lõi. "
        "Toàn bộ sơ đồ chân, danh mục linh kiện và bảng 40 dây đấu nối được đồng bộ nhất quán giữa bản thiết kế KiCad "
        "và mã nguồn firmware để hạn chế tối đa sai sót khi thi công mạch thực tế."
    )

    # ===== 3.1. KIẾN TRÚC MẠCH ĐIỆN TỬ & NODEMCU ESP8266 =====
    rb.add_h2("3.1. Kiến trúc mạch điện tử và vi điều khiển NodeMCU ESP8266 v2 Amica")
    rb.add_para(
        "Để đảm bảo an toàn điện tuyệt đối trong môi trường học tập và trình diễn mô hình, em thiết kế toàn bộ hệ thống "
        "vận hành ở mức điện áp một chiều thấp 5V DC và 3,3V DC, không dùng tải xoay chiều 220V AC. "
        "Thay vì cắm dây rải rác trên bảng thử nghiệm breadboard trắng dễ lỏng tiếp xúc, em xây dựng một bo mạch tập trung "
        "PCB Hub DIY v3 cắm trực tiếp vi điều khiển và toàn bộ 15 cổng kết nối ngoại vi."
    )
    rb.add_para(
        "Vi điều khiển trung tâm em lựa chọn là NodeMCU ESP8266 v2 Amica dùng mô-đun ESP-12E/F. "
        "Bo mạch có nhân xử lý 32-bit xung nhịp 80/160 MHz, bộ nhớ Flash 4 MB đủ lớn để chia phân vùng hệ thống tệp LittleFS "
        "lưu thông tin Wi-Fi khi chạy thực tế, tích hợp Wi-Fi 2,4 GHz chuẩn IEEE 802.11 b/g/n và chip nạp USB-UART CP2102 "
        "ổn định trên Windows. Bản v2 Amica có kích thước gọn 48,26 × 25,40 mm với khoảng cách hai hàng chân tiêu chuẩn "
        "0,9 inch (22,86 mm), cắm khớp trực tiếp vào cặp đế cái 1×15 chân U1 và U2 trên bo mạch PCB Hub."
    )

    rb.add_figure(
        diagrams_dir / "diag_hw_block.png",
        "Sơ đồ khối phần cứng mạch điện tử tổng thể trên bo mạch PCB Hub DIY v3",
        max_width_cm=13.8,
        max_height_cm=6.6,
        kind="diagram",
    )

    rb.add_para(
        "Khi phân chân cho ESP8266, khó khăn lớn nhất là ba chân định chế độ khởi động (boot-strap): "
        "D3 (GPIO0) và D4 (GPIO2) bắt buộc ở mức cao (HIGH) lúc bật nguồn để chạy chương trình bình thường, "
        "còn D8 (GPIO15) bắt buộc ở mức thấp (LOW). Nếu đấu tải trực tiếp không có điện trở kéo hoặc mạch cách ly, "
        "ESP8266 sẽ bị treo khi khởi động hoặc làm còi báo động kêu giả mỗi lần cấp điện. "
        "Em đã khóa cứng toàn bộ 10 chân sử dụng trên NodeMCU kèm mạch bảo vệ boot-strap như trình bày ở Bảng 3.1."
    )

    rb.add_table(
        "Bảng khóa cứng 10 chân NodeMCU ESP8266 v2 Amica và cơ chế an toàn khởi động (boot-strap)",
        ["Chân", "GPIO", "Macro firmware", "Cổng PCB", "Thiết bị / Cảm biến", "Cực tính & Cơ chế an toàn khởi động"],
        [
            ("D0", "GPIO16", "PIN_LIVING_LIGHT", "J4", "Đèn LED phòng khách", "Active-HIGH qua R1 220 Ω; kiêm nháy báo mất kết nối"),
            ("D1", "GPIO5", "PIN_MAIN_DOOR_SERVO", "J3", "Servo SG90 cửa chính", "PWM 50 Hz (0° đóng / 90° mở); nguồn +5V lọc C1 470 µF"),
            ("D2", "GPIO4", "PIN_DHT11", "J13", "Cảm biến DHT11", "Giao tiếp 1-Wire 3,3V; trở kéo lên R3 10 kΩ trên bo"),
            ("D3", "GPIO0", "PIN_AUDIO_PWM", "J12", "Tín hiệu loa PAM8403", "Boot HIGH: R4 10 kΩ kéo lên + C4 10 µF chặn DC; nghỉ = INPUT"),
            ("D4", "GPIO2", "PIN_BEDROOM_LIGHT", "J5", "Đèn LED phòng ngủ", "Boot HIGH: đấu Active-LOW qua R2 220 Ω + R7 10 kΩ kéo lên"),
            ("D5", "GPIO14", "PIN_KY037_DO", "J15", "Âm thanh KY-037 (DO)", "Nguồn chuẩn 3,3V; ngắt cạnh lên RISING, chống dội ≥ 400 ms"),
            ("D6", "GPIO12", "PIN_GARDEN_PUMP", "J7/J8/J2", "Relay 1 → Máy bơm 5V", "Active-HIGH; bơm có D1 1N4007 + C2 470 µF; tối đa 120 s"),
            ("D7", "GPIO13", "PIN_SPEAKER_AMP", "J9/J10/J11", "Relay 2 → PAM8403", "Active-HIGH (jumper H); tự ngắt nguồn loa 1,5 s sau chuông"),
            ("D8", "GPIO15", "PIN_ALARM_SIREN", "J6", "Còi báo động 5V", "Boot LOW: R9 10 kΩ kéo xuống + R10 1 kΩ → Q1 S8050 + D2 1N4007"),
            ("A0", "ADC0", "PIN_SOIL_MOISTURE", "J14", "Độ ẩm đất LM393 (AO)", "ADC 10-bit 0–3,3V lọc C7 100 nF; LM393 bắt buộc cấp 3,3V"),
        ],
        col_widths_cm=[1.1, 1.4, 3.8, 1.5, 2.7, 5.0],
        font_pt=8.8,
        center_cols=(0, 1, 3),
    )

    # ===== 3.2. CẢM BIẾN, THIẾT BỊ CHẤP HÀNH VÀ KHỐI NGUỒN =====
    rb.add_h2("3.2. Cảm biến, thiết bị chấp hành và khối nguồn")
    rb.add_para(
        "Hệ thống gồm 3 cảm biến đầu vào, 6 thiết bị chấp hành đầu ra và 1 khối nguồn 5V–2A cấp chung cho toàn bộ mô hình. "
        "Hình 3.2 minh họa bộ linh kiện điện tử thực tế em sử dụng khi kiểm tra kích thước, sơ đồ chân và mức điện áp hoạt động."
    )

    rb.add_figure(
        demo_dir / "components_shopee_grid.png",
        "Tổng hợp các linh kiện điện tử thực tế sử dụng trong hệ thống nhà thông minh",
        max_width_cm=10.8,
        max_height_cm=6.4,
        kind="hardware_photo",
    )

    rb.add_para(
        "Về nhóm cảm biến (tất cả cấp nguồn 3,3V từ ổn áp AMS1117 trên NodeMCU kèm tụ lọc C8 100 nF trên bo): "
        "Cảm biến nhiệt độ – độ ẩm DHT11 nối vào cổng J13 (chân D2) có điện trở kéo lên R3 10 kΩ cho đường dữ liệu 1-Wire. "
        "Cảm biến độ ẩm đất YL-69 kèm mạch so sánh LM393 nối cổng J14 (chân A0) bắt buộc cấp đúng 3,3V — tuyệt đối không cấp 5V — "
        "để điện áp ngõ ra tương tự AO luôn nằm trong vùng an toàn của bộ ADC0 trên NodeMCU và được lọc nhiễu bởi tụ gốm C7 100 nF. "
        "Tương tự, cảm biến âm thanh KY-037/038 nối cổng J15 (chân D5) cũng cấp nghiêm ngặt 3,3V để ngõ ra số DO xuất mức logic 3,3V "
        "phát hiện tiếng vỗ tay hoặc tiếng động lớn theo ngắt cạnh lên RISING."
    )
    rb.add_para(
        "Về nhóm 6 thiết bị chấp hành: Cửa chính dùng động cơ Servo SG90 9g nối cổng J3 (chân D1, xung PWM 50 Hz góc 0° đóng / 90° mở). "
        "Máy bơm nước chìm mini 3–6V DC được đóng cắt qua tiếp điểm thường mở (COM–NO) của Relay 1 xanh 5V điều khiển từ chân D6 (cổng J7, J8, J2). "
        "Khối phát chuông phần cứng gồm Relay 2 đỏ 5V cách ly quang PC817 (đặt jumper ở mức H, chân D7) đóng cắt nguồn 5V cho mạch khuếch đại "
        "Class-D PAM8403, kết hợp chân D3 xuất xung âm tần qua tụ chặn DC C4 (10 µF) và mạch chia áp – lọc thông thấp RC (R5, R6 = 2,2 kΩ; C5 = 10 nF, "
        "tần số cắt khoảng 14,5 kHz) đưa ra loa tròn mini 28 mm (8 Ω, 0,5 W). Do PAM8403 xuất ngõ ra cầu vi sai BTL (L_OUT+ và L_OUT-), "
        "em tuyệt đối không nối chân loa âm xuống GND để tránh chập tầng công suất."
    )
    rb.add_para(
        "Còi báo động chủ động 5V TMB12A05 nối cổng J6 được lái cực âm (low-side) qua transistor NPN Q1 (S8050) với trở cực nền R10 1 kΩ "
        "và trở kéo xuống R9 10 kΩ trên chân D8, giúp cách ly dòng cuộn còi khỏi vi điều khiển và giữ còi im lặng khi khởi động. "
        "Hai đèn LED 5 mm chiếu sáng phòng khách (cổng J4, chân D0 Active-HIGH qua R1 220 Ω) và phòng ngủ (cổng J5, chân D4 Active-LOW "
        "qua R2 220 Ω từ +3,3V) hoàn thiện 6 thiết bị chấp hành."
    )
    rb.add_para(
        "Về khối nguồn và mạch bảo vệ trên bo: Nguồn ngoài 5V–2A cấp vào domino J1 được lọc bằng hai tụ hóa dung lượng lớn C1, C2 (470 µF 16V) "
        "đặt gần nhánh Servo và máy bơm để hấp thụ dòng xung đỉnh (tránh sụt áp gây reset ESP8266), kết hợp tụ gốm cao tần C3 (100 nF) "
        "và đèn báo nguồn R8 (1 kΩ) + LED xanh D3. Nhánh nguồn 5V đóng cắt qua Relay 2 cấp cho PAM8403 được lọc riêng bằng C6 (100 nF) và C9 (100 µF 16V). "
        "Hai tải cảm ứng là máy bơm (J2) và còi từ TMB12A05 (J6) đều có diode dập xung ngược D1 và D2 (1N4007) hàn trực tiếp trên PCB "
        "để triệt sức điện động cảm ứng khi ngắt tải. Bảng 3.2 tóm tắt thông số kỹ thuật chính của các khối phần cứng."
    )

    rb.add_table(
        "Thông số kỹ thuật các cảm biến, thiết bị chấp hành và khối nguồn chính",
        ["Khối / Linh kiện", "Nguồn cấp", "Dòng / Công suất", "Giao tiếp / Chân", "Ghi chú thiết kế & Bảo vệ"],
        [
            ("NodeMCU ESP8266 v2 Amica", "5V (VIN) / 3,3V lõi", "80 mA TB; đỉnh ~300 mA", "Wi-Fi 2,4 GHz, CP2102", "Flash 4 MB, LittleFS, cắm đế U1/U2 0,9\""),
            ("Cảm biến DHT11 (3 chân)", "3,3V DC", "0,3–2,5 mA", "1-Wire (J13 · D2)", "Đo 0–50 °C, 20–90% RH; kéo lên R3 10 kΩ"),
            ("Độ ẩm đất YL-69 + LM393", "3,3V DC (bắt buộc)", "< 15 mA", "Tương tự AO (J14 · A0)", "Lọc C7 100 nF; tưới trễ <40% bật / ≥70% tắt"),
            ("Âm thanh KY-037 / KY-038", "3,3V DC (bắt buộc)", "< 10 mA", "Số DO (J15 · D5)", "Ngắt RISING chống dội ≥ 400 ms; bỏ trống AO"),
            ("Servo SG90 9g (cửa chính)", "5,0V DC", "100–250 mA; kẹt ~600 mA", "PWM 50 Hz (J3 · D1)", "Mô-men 1,8 kg·cm; lọc nguồn C1 470 µF"),
            ("Relay 1 xanh + Máy bơm 5V", "5,0V DC", "Relay ~70 mA; bơm ~200 mA", "Active-HIGH (J7/J8/J2 · D6)", "Đóng cắt qua NO; bảo vệ D1 1N4007 + C2 470 µF"),
            ("Relay 2 đỏ opto (PC817)", "5,0V DC", "~70 mA khi đóng", "Active-HIGH Jmp=H (J9/J10 · D7)", "Ngắt hẳn nguồn PAM8403 sau chuông 1,5 s"),
            ("PAM8403 + Loa 28 mm 8 Ω", "5,0V (qua Relay 2)", "Class-D >85%; loa 0,5 W", "L vào (J12 · D3), ra cầu BTL", "Lọc C6 100 nF + C9 100 µF; không nối L_OUT- GND"),
            ("Còi chủ động TMB12A05", "5,0V DC", "~30 mA (~85 dB)", "Low-side Q1 S8050 (J6 · D8)", "R9 10 kΩ giữ LOW khi boot; D2 1N4007 dập xung"),
            ("2× LED 5 mm (Khách / Ngủ)", "3,3V DC", "~5–10 mA / bóng", "J4 (D0) & J5 (D4 Active-LOW)", "Hạn dòng R1, R2 = 220 Ω; R7 10 kΩ giữ D4 HIGH"),
            ("Nguồn ngoài 5V–2A + Bảo vệ", "5V DC (±5%)", "Tối đa 2,0 A (10 W)", "DC-022 → Domino J1", "Tụ C1–C9 và diode D1–D2 hàn 100% trên PCB"),
        ],
        col_widths_cm=[3.2, 2.2, 2.7, 3.0, 4.4],
        font_pt=9.2,
    )

    # ===== 3.3. THIẾT KẾ SƠ ĐỒ NGUYÊN LÝ VÀ BO MẠCH PCB HUB DIY v3 =====
    rb.add_h2("3.3. Thiết kế sơ đồ nguyên lý và bo mạch PCB Hub DIY v3 (KiCad)")
    rb.add_para(
        "Toàn bộ mạch điện tử tập trung được em vẽ sơ đồ nguyên lý và thiết kế mạch in trên phần mềm KiCad 10.0. "
        "Để phù hợp với phương pháp gia công mạch thủ công một mặt đồng tại xưởng thực hành nhưng vẫn đảm bảo độ tin cậy cơ – điện, "
        "em chọn kích thước bo 100 × 80 × 1,6 mm (vật liệu FR4, 1 lớp đồng đáy B.Cu), dùng hoàn toàn linh kiện cắm lỗ (THT) dễ hàn "
        "và bố trí 7 cầu nối dây mặt trên (JP1–JP7) để vượt chéo tín hiệu mà không cần bo 2 lớp."
    )
    rb.add_para(
        "Bo mạch PCB Hub DIY v3 gồm đúng 51 footprints (47 linh kiện hàn và 4 lỗ bắt ốc M3 H1–H4 ở bốn góc), "
        "tích hợp trọn vẹn 15 cổng kết nối J1–J15 bố trí dọc theo các cạnh bo theo đúng hướng đi dây tới từng phòng trong mô hình. "
        "Kết quả kiểm tra quy tắc điện (ERC) và quy tắc thiết kế mạch in (DRC) trên KiCad đều đạt 0 lỗi (0 ERC / 0 DRC) "
        "với khoảng cách đồng tối thiểu ≥ 0,60 mm, loại bỏ hoàn toàn breadboard trắng. Các hình 3.3, 3.4, 3.5 và 3.6 "
        "lần lượt trình bày sơ đồ nguyên lý, bản vẽ đồng 2D tỷ lệ 1:1, mô hình 3D bo mạch và sơ đồ đấu nối tổng thể 40 dây."
    )

    rb.add_figure(
        sw_dir / "sw_kicad_schematic.png",
        "Sơ đồ nguyên lý bo mạch PCB Hub DIY v3 thiết kế trên KiCad 10.0",
        max_width_cm=13.6,
        max_height_cm=6.5,
        kind="schematic",
    )
    rb.add_figure(
        demo_dir / "kicad_2d_copper_layout.png",
        "Bố trí mạch in 2D lớp đồng đáy (B.Cu) tỷ lệ 1:1 kích thước 100×80 mm của PCB Hub DIY v3",
        max_width_cm=10.8,
        max_height_cm=6.4,
        kind="pcb_2d",
    )
    rb.add_figure(
        demo_dir / "kicad_3d_iso.png",
        "Mô hình 3D bo mạch PCB Hub DIY v3 với 51 footprints linh kiện cắm lỗ và 15 cổng J1–J15",
        max_width_cm=11.6,
        max_height_cm=6.3,
        kind="pcb_3d",
    )
    rb.add_figure(
        demo_dir / "wiring_diagram_2d.png",
        "Sơ đồ đấu nối 2D chuẩn hóa 40 dây vật lý giữa PCB Hub DIY v3 và các module ngoại vi",
        max_width_cm=13.6,
        max_height_cm=6.5,
        kind="diagram",
    )

    rb.add_para(
        "Bảng 3.3 liệt kê danh mục vật tư đầy đủ (BOM) trích trực tiếp từ tệp bom.csv của KiCad (tổng 51 footprints trên bo PCB Hub) "
        "cùng các bo mạch và module ngoại vi đi kèm."
    )

    rb.add_table(
        "Danh mục vật tư linh kiện (BOM) bo mạch PCB Hub DIY v3 (51 footprints) và module ngoại vi",
        ["Nhóm", "Ký hiệu (Refs)", "Giá trị / Tên linh kiện", "Kiểu chân / Quy cách", "SL", "Vai trò mạch điện tử"],
        [
            ("Tụ điện", "C1, C2", "470 µF 16V", "Tụ hóa Ø8×P3,5 mm", "2", "Lọc xung dòng đỉnh nguồn +5V cho Servo và máy bơm"),
            ("Tụ điện", "C9", "100 µF 16V", "Tụ hóa Ø6,3×P3,5 mm", "1", "Dự trữ năng lượng cạnh J11 cho mạch loa PAM8403"),
            ("Tụ điện", "C4", "10 µF 16V", "Tụ hóa Ø5×P3,5 mm", "1", "Chặn thành phần DC cô lập chân boot D3 (GPIO0)"),
            ("Tụ điện", "C3, C6, C7, C8", "100 nF 50V (104)", "Tụ gốm P5,0 mm", "4", "Lọc nhiễu cao tần nhánh +5V, AMP_5V, ADC0 và +3,3V"),
            ("Tụ điện", "C5", "10 nF 50V (103)", "Tụ gốm P5,0 mm", "1", "Lọc thông thấp RC làm mịn xung PWM âm thanh D3"),
            ("Điện trở", "R1, R2", "220 Ω (1/4W)", "Axial P10,16 mm", "2", "Hạn dòng bảo vệ 2 đèn LED 5 mm phòng khách, phòng ngủ"),
            ("Điện trở", "R8, R10", "1 kΩ (1/4W)", "Axial P10,16 mm", "2", "Hạn dòng LED nguồn D3 (R8) và cực B Q1 S8050 (R10)"),
            ("Điện trở", "R5, R6", "2,2 kΩ (1/4W)", "Axial P10,16 mm", "2", "Cầu phân áp giảm ~50% biên độ âm thanh vào PAM8403"),
            ("Điện trở", "R3, R4, R7, R9", "10 kΩ (1/4W)", "Axial P10,16 mm", "4", "Kéo lên DHT11/D3/D4 và kéo xuống boot-strap D8 (R9)"),
            ("Bán dẫn", "Q1", "S8050 (NPN 0,7A)", "TO-92 Wide", "1", "Transistor lái low-side đóng cắt còi báo động 5V"),
            ("Diode / LED", "D1, D2", "1N4007 (1000V/1A)", "DO-41 P10,16 mm", "2", "Diode dập xung cảm ứng cho máy bơm (J2) và còi (J6)"),
            ("Diode / LED", "D3", "LED xanh 3 mm", "LED Ø3 mm P5,08 mm", "1", "Chỉ thị nguồn chính +5V đang hoạt động trên PCB"),
            ("Đế & Cổng", "U1, U2", "Đế cái 1×15 chân", "PinSocket P2,54 mm", "2", "Cắm rời NodeMCU ESP8266 v2 Amica (bước 0,9\")"),
            ("Đế & Cổng", "J1, J2", "Domino vặn vít 2P", "MKDS 1×2 P5,08 mm", "2", "Cấp nguồn chính +5V (J1) và ngõ ra máy bơm (J2)"),
            ("Đế & Cổng", "J4–J6, J8, J10–J12", "Header đực 1×2 chân", "PinHeader P2,54 mm", "7", "Kết nối 2 LED, còi, tiếp điểm Relay và nguồn/tín hiệu loa"),
            ("Đế & Cổng", "J3, J7, J9, J13–J15", "Header đực 1×3 chân", "PinHeader P2,54 mm", "6", "Kết nối Servo SG90, 2 cuộn Relay và 3 cảm biến 3,3V"),
            ("Cầu & Lỗ", "JP1–JP7 / H1–H4", "Cầu nối dây / Lỗ M3", "7,62–35,56 mm / Ø3,2 mm", "7 + 4", "7 cầu nhảy mặt trên 1 lớp và 4 lỗ định vị cơ khí M3"),
            ("Module ngoài", "Bo lõi & 14 module", "NodeMCU + 3 CB + 6 CH + Nguồn", "Cắm Dupont / Domino", "15", "NodeMCU v2, 5V-2A, SG90, 2 LED, 2 Relay, Bơm, Còi, PAM8403, Loa, DHT11, LM393, YL-69, KY-037"),
        ],
        col_widths_cm=[1.7, 2.4, 2.8, 2.7, 0.9, 5.0],
        font_pt=8.8,
        center_cols=(4,),
    )

    rb.add_para(
        "Để đảm bảo việc đi dây trong mô hình gọn gàng và đúng tuyệt đối từng chân linh kiện, em lập bảng chuẩn hóa "
        "toàn bộ 40 dây nối vật lý (W01–W40), bao gồm 36 dây cắm vào 15 cổng J1–J15 trên PCB Hub và 4 dây nối liên module "
        "(PAM8403 tới loa 28 mm và LM393 tới đầu dò YL-69). Chiều dài định tuyến 3D thực tế (đã cộng 18% độ chùng đi dây) "
        "dao động từ 3,84 cm (W29) đến 27,48 cm (W08), tổng cộng 654,99 cm — đạt 40/40 dây ≤ 30 cm nên chỉ cần dùng "
        "dây Dupont tiêu chuẩn 10/20/30 cm có sẵn ngoài thị trường (Bảng 3.4)."
    )

    rb.add_table(
        "Bảng đấu nối chuẩn hóa 40 dây vật lý (W01–W40) giữa PCB Hub DIY v3 và các module (tổng 654,99 cm)",
        ["Mã", "Đầu nguồn / PCB", "Module đích (Chân)", "Chân MCU / Lưới KiCad", "Màu dây", "Dài (cm)"],
        [
            ("W01", "J1.1 (PWR_5V_IN)", "Nguồn 5V–2A (+5V)", "VIN (+5V)", "Đỏ", "9,58"),
            ("W02", "J1.2 (PWR_5V_IN)", "Nguồn 5V–2A (GND)", "GND chung", "Đen", "9,10"),
            ("W03", "J3.1 (SERVO_D1)", "Servo SG90 (PWM)", "D1 / GPIO5 (D1_SERVO)", "Cam", "18,24"),
            ("W04", "J3.2 (SERVO_D1)", "Servo SG90 (VCC)", "VIN (+5V, lọc C1)", "Đỏ", "18,28"),
            ("W05", "J3.3 (SERVO_D1)", "Servo SG90 (GND)", "GND", "Đen", "18,35"),
            ("W06", "J4.1 (LED_LR_D0)", "LED Phòng khách (+)", "D0 / GPIO16 qua R1 (LED_LR_A)", "Vàng", "21,16"),
            ("W07", "J4.2 (LED_LR_D0)", "LED Phòng khách (-)", "GND", "Đen", "20,72"),
            ("W08", "J5.1 (LED_BR_D4)", "LED Phòng ngủ (+)", "+3V3 qua R2 220 Ω (LED_BR_A)", "Tím", "27,48"),
            ("W09", "J5.2 (LED_BR_D4)", "LED Phòng ngủ (-)", "D4 / GPIO2 Active-LOW (D4_LED_BR)", "Trắng", "27,45"),
            ("W10", "J7.1 (RLY1_PUMP)", "Relay 1 Bơm (VCC)", "VIN (+5V)", "Đỏ", "7,89"),
            ("W11", "J7.2 (RLY1_PUMP)", "Relay 1 Bơm (GND)", "GND", "Đen", "7,89"),
            ("W12", "J7.3 (RLY1_PUMP)", "Relay 1 Bơm (IN)", "D6 / GPIO12 (D6_RLY1_PUMP)", "Xanh lá", "7,89"),
            ("W13", "J8.1 (RLY1_SW)", "Relay 1 Bơm (COM)", "VIN (+5V)", "Đỏ", "17,91"),
            ("W14", "J8.2 (RLY1_SW)", "Relay 1 Bơm (NO)", "PUMP_5V → J2.1 + D1", "Vàng", "17,94"),
            ("W15", "J2.1 (PUMP_OUT)", "Máy bơm 5V (+)", "PUMP_5V (qua Relay 1 + D1)", "Đỏ", "26,45"),
            ("W16", "J2.2 (PUMP_OUT)", "Máy bơm 5V (-)", "GND (cực A của D1)", "Đen", "26,22"),
            ("W17", "J6.1 (BUZZ_D8)", "Còi TMB12A05 (+)", "+5V (cực K của D2)", "Đỏ", "25,41"),
            ("W18", "J6.2 (BUZZ_D8)", "Còi TMB12A05 (-)", "D8 / GPIO15 qua Q1 (BUZZ_K)", "Cam", "25,81"),
            ("W19", "J9.1 (RLY2_AMP)", "Relay 2 Loa (DC+)", "VIN (+5V)", "Đỏ", "6,26"),
            ("W20", "J9.2 (RLY2_AMP)", "Relay 2 Loa (DC-)", "GND", "Đen", "6,26"),
            ("W21", "J9.3 (RLY2_AMP)", "Relay 2 Loa (IN)", "D7 / GPIO13 (D7_RLY2_AMP)", "Xanh ngọc", "6,26"),
            ("W22", "J10.1 (RLY2_SW)", "Relay 2 Loa (COM)", "VIN (+5V)", "Đỏ", "18,75"),
            ("W23", "J10.2 (RLY2_SW)", "Relay 2 Loa (NO)", "AMP_5V → J11.1 + C6/C9", "Cam", "18,53"),
            ("W24", "J11.1 (PAM8403_PWR)", "PAM8403 (5V+)", "AMP_5V (sau Relay 2)", "Đỏ", "15,71"),
            ("W25", "J11.2 (PAM8403_PWR)", "PAM8403 (5V-)", "GND", "Đen", "15,76"),
            ("W26", "J12.1 (AUDIO_D3)", "PAM8403 (L In)", "D3 / GPIO0 qua C4/R5/R6/C5 (AUD_OUT)", "Trắng", "13,08"),
            ("W27", "J12.2 (AUDIO_D3)", "PAM8403 (Audio GND)", "GND", "Đen", "13,13"),
            ("W28", "PAM8403 L_OUT+", "Loa 28 mm 8 Ω (+)", "Ngõ ra cầu BTL+ (SPK_BTL_P)", "Vàng", "4,04"),
            ("W29", "PAM8403 L_OUT-", "Loa 28 mm 8 Ω (-)", "Ngõ ra cầu BTL- (SPK_BTL_N, cấm GND)", "Nâu", "3,84"),
            ("W30", "J13.1 (DHT11_D2)", "DHT11 (VCC)", "+3V3 (từ NodeMCU + C8)", "Đỏ", "19,15"),
            ("W31", "J13.2 (DHT11_D2)", "DHT11 (DATA)", "D2 / GPIO4 + R3 10 kΩ (D2_DHT11)", "Xanh dương", "19,59"),
            ("W32", "J13.3 (DHT11_D2)", "DHT11 (GND)", "GND", "Đen", "20,05"),
            ("W33", "J14.1 (SOIL_A0)", "LM393 Đất (VCC)", "+3V3 (nghiêm ngặt 3,3V)", "Đỏ", "26,36"),
            ("W34", "J14.2 (SOIL_A0)", "LM393 Đất (GND)", "GND (chân DO bỏ trống)", "Đen", "26,36"),
            ("W35", "J14.3 (SOIL_A0)", "LM393 Đất (AO)", "A0 / ADC0 + C7 100 nF (A0_SOIL)", "Xanh lá", "26,36"),
            ("W36", "LM393 Probe+", "Đầu dò YL-69 (Nhánh A)", "SOIL_PROBE_A (nối ngoài bo)", "Vàng", "13,82"),
            ("W37", "LM393 Probe-", "Đầu dò YL-69 (Nhánh B)", "SOIL_PROBE_B (nối ngoài bo)", "Cam", "13,40"),
            ("W38", "J15.1 (KY037_D5)", "KY-037 Âm thanh (+)", "+3V3 (nghiêm ngặt 3,3V)", "Đỏ", "11,22"),
            ("W39", "J15.2 (KY037_D5)", "KY-037 Âm thanh (G)", "GND (chân AO bỏ trống)", "Đen", "11,49"),
            ("W40", "J15.3 (KY037_D5)", "KY-037 Âm thanh (DO)", "D5 / GPIO14 ngắt RISING (D5_MIC_DO)", "Vàng", "11,80"),
        ],
        col_widths_cm=[1.1, 2.7, 3.2, 5.2, 1.7, 1.6],
        font_pt=8.0,
        center_cols=(0, 4, 5),
    )

    # ===== 3.4. LƯU ĐỒ HOẠT ĐỘNG FIRMWARE ESP8266 VÀ GIAO THỨC KẾT NỐI =====
    rb.add_h2("3.4. Lưu đồ hoạt động firmware ESP8266 và giao thức kết nối")
    rb.add_para(
        "Firmware ESP8266 được em lập trình bằng C/C++ trên nền tảng PlatformIO theo mô hình vòng lặp không chặn "
        "(non-blocking) để không bao giờ gây treo bộ đếm giám sát Watchdog. Ngay khi cấp điện, hàm setup() thiết lập trạng thái "
        "an toàn cho các chân boot-strap trước tiên, sau đó nạp thông tin Wi-Fi và địa chỉ máy chủ từ tệp /wifi_config.json "
        "trong bộ nhớ LittleFS (không ghi cứng mật khẩu trong mã nguồn). Lưu đồ hoạt động tổng thể của firmware cùng "
        "máy trạng thái ngoại tuyến A1–A4 được trình bày ở Hình 3.7."
    )

    rb.add_figure(
        diagrams_dir / "diag_fw_flow.png",
        "Lưu đồ hoạt động firmware ESP8266 và máy trạng thái ngoại tuyến (Offline FSM A1–A4)",
        max_width_cm=13.8,
        max_height_cm=6.5,
        kind="diagram",
    )

    rb.add_para(
        "Đoạn mã 3.1 trích trực tiếp phần khởi tạo chân trong hàm setup() của firmware: chân D3 (GPIO0) được giữ ở chế độ "
        "INPUT (trở kháng cao), chân D4 (GPIO2) được ghi mức HIGH trước khi chuyển OUTPUT để đèn phòng ngủ Active-LOW luôn tắt lúc boot, "
        "chân D8 (GPIO15) ghi mức LOW để còi im lặng, đồng thời Servo cửa chính D1 đưa ngay về góc đóng 0°."
    )
    cap_pin, ref_pin, start_pin, lines_pin = load_code_excerpt("fw_bootstrap_pins")
    rb.add_code_listing(cap_pin, lines_pin, source_ref=ref_pin, start_line=start_pin)

    rb.add_para(
        "Khi mất Wi-Fi hoặc máy chủ không phản hồi, máy trạng thái ngoại tuyến OfflineFsm chuyển mạch sang chế độ an toàn A1–A3: "
        "nháy đèn D0 báo mất mạng, mở điểm phát dự phòng SoftAP và trang điều khiển cục bộ cổng 80 cho phép bật/tắt cơ bản "
        "các thiết bị không nhạy cảm (đèn, bơm, còi) nhưng khóa cứng tuyệt đối cửa chính. Như thể hiện ở Đoạn mã 3.2, "
        "hàm canSetMainDoor() luôn trả về false khi ngoại tuyến và tự động kéo cửa về 0°; mọi thay đổi cục bộ được đánh dấu "
        "vào mặt nạ dirty_mask để đồng bộ ngược lên máy chủ qua API /api/hardware/resync (trạng thái A4) ngay khi có mạng trở lại."
    )
    cap_off, ref_off, start_off, lines_off = load_code_excerpt("fw_offline_door_lock")
    rb.add_code_listing(cap_off, lines_off, source_ref=ref_off, start_line=start_off)

    rb.add_para(
        "Để kết nối xuyên suốt từ lớp linh kiện phần cứng đến máy chủ, trình duyệt Web và ứng dụng Android, "
        "em phối hợp năm nhóm giao thức tiêu chuẩn trình bày trong Bảng 3.5. Ở lớp vật lý, vi điều khiển dùng GPIO, "
        "1-Wire, PWM và ADC; ở lớp mạng, hệ thống kết hợp MQTT siêu nhẹ cho ESP8266, HTTP REST cho quản lý phiên và cấu hình, "
        "WebSocket song công cho luồng giọng nói thời gian thực và Server-Sent Events (SSE) đẩy trạng thái tức thời tới mọi màn hình."
    )

    rb.add_table(
        "Tổng hợp các giao thức tín hiệu phần cứng và truyền thông mạng trong hệ thống",
        ["Giao thức", "Chiều truyền", "Tuyến kết nối", "Vai trò trong hệ thống"],
        [
            ("GPIO / 1-Wire / PWM / ADC", "Mức vật lý cục bộ", "ESP8266 ↔ 3 Cảm biến & 6 Chấp hành", "Đọc DHT11, LM393, KY-037; lái Servo 50 Hz, 2 Relay, còi Q1, 2 LED và chuông PAM8403."),
            ("MQTT (TCP cổng 1883)", "Publish / Subscribe", "Máy chủ FastAPI ↔ ESP8266", "Gửi lệnh điều khiển smarthome/cmd/+ và nhận dữ liệu cảm biến smarthome/telemetry/+ nhẹ, độ trễ thấp."),
            ("HTTP / HTTPS REST", "Yêu cầu – Phản hồi", "Web / Android / ESP8266 ↔ FastAPI", "Đăng nhập, phân quyền RBAC, sinh/quét QR động, đặt hẹn giờ và đồng bộ ngoại tuyến /api/hardware/resync."),
            ("WebSocket (WS / WSS)", "Song công toàn phần", "Web / Android ↔ FastAPI ↔ Gemini Live", "Truyền luồng âm thanh PCM hai chiều (16 kHz vào / 24 kHz ra) và thực thi gọi hàm điều khiển thời gian thực."),
            ("Server-Sent Events (SSE)", "Một chiều (Server → Client)", "FastAPI → Web 3D & Android", "Đẩy tức thời trạng thái 6 thiết bị, số đo 3 cảm biến và thông báo sự kiện đến mọi ứng dụng đang mở."),
        ],
        col_widths_cm=[3.2, 2.7, 3.6, 6.0],
        font_pt=9.5,
    )

    # ===== 3.5. CÔNG NGHỆ PHẦN MỀM SỬ DỤNG =====
    rb.add_h2("3.5. Công nghệ phần mềm sử dụng")
    rb.add_para(
        "Song song với mạch điện tử và firmware nhúng, em lựa chọn các công nghệ phần mềm mã nguồn mở gọn nhẹ và phổ biến "
        "để xây dựng hoàn chỉnh bốn tầng ứng dụng: máy chủ điều phối backend, giao diện Web kèm mô phỏng 3D, "
        "ứng dụng di động Android và bộ công cụ thiết kế phần cứng. Máy chủ viết bằng Python 3.14.7 và FastAPI 0.141.1 "
        "giúp xử lý bất đồng bộ nhiều luồng WebSocket/SSE cùng lúc; dữ liệu lưu bằng SQLite 3.53.2 ở chế độ WAL "
        "nên không cần cài đặt hệ quản trị cơ sở dữ liệu rời mà vẫn giữ tính toàn vẹn giao dịch. "
        "Phần trợ lý giọng nói tiếng Việt dùng Google Gemini 3.8 Live theo cơ chế âm thanh-sang-âm thanh trực tiếp."
    )
    rb.add_para(
        "Giao diện Web được viết thuần bằng HTML5, CSS3 và JavaScript kết hợp thư viện Three.js đóng gói cục bộ "
        "để hiển thị mô hình 3D tương tác trạng thái từng thiết bị. Ứng dụng di động Android viết bằng Kotlin 2.3.20 "
        "trên Jetpack Compose (Material 3, hỗ trợ từ Android 8.0 / minSdk 26) cho phép ghi âm giọng nói PCM trực tiếp "
        "và quét mã QR phân quyền. Toàn bộ firmware ESP8266 được biên dịch trên PlatformIO 6.2.0 và mạch in thiết kế trên KiCad 10.0. "
        "Bảng 3.6 tổng hợp danh mục công nghệ cốt lõi kèm phiên bản sử dụng, cùng hai lưới biểu trưng minh họa tại Hình 3.8 và Hình 3.9."
    )

    rb.add_table(
        "Tổng hợp các công nghệ phần mềm cốt lõi sử dụng trong đồ án",
        ["Tầng hệ thống", "Công nghệ / Công cụ", "Phiên bản", "Vai trò cụ thể trong đồ án"],
        [
            ("Máy chủ & AI", "Python", "3.14.7", "Ngôn ngữ phát triển máy chủ điều phối, xử lý bất đồng bộ và giao tiếp phần cứng."),
            ("Máy chủ & AI", "FastAPI / Uvicorn / Pydantic", "0.141.1 / 0.53.0 / 2.13.4", "Cung cấp API REST, WebSocket, SSE, kiểm tra dữ liệu đầu vào và xác thực phiên."),
            ("Cơ sở dữ liệu", "SQLite / aiosqlite", "3.53.2 / 0.22.1", "Lưu người dùng, phiên đăng nhập, phân quyền 3 tầng, hẹn giờ, lệnh tùy chỉnh và nhật ký."),
            ("Trợ lý giọng nói", "Google Gemini Live (google-genai)", "gemini-3.8-live / SDK 2.33.0", "Xử lý hội thoại tiếng Việt trực tiếp hai chiều và gọi hàm điều khiển thiết bị."),
            ("Giao diện Web 3D", "HTML5 / CSS3 / JavaScript / Three.js", "ES2022+ / Three.js nội bộ", "Hiển thị bảng điều khiển đa trang và mô hình nhà 3D đồng bộ thời gian thực."),
            ("Ứng dụng di động", "Kotlin / Android Jetpack Compose", "Kotlin 2.3.20 / minSdk 26", "Xây dựng ứng dụng Android Material 3 hỗ trợ giọng nói, quét QR và điều khiển thiết bị."),
            ("Firmware nhúng", "PlatformIO Core / Espressif8266", "PlatformIO 6.2.0 / nodemcuv2", "Biên dịch, quản lý thư viện (PubSubClient, ArduinoJson, DHT) và nạp firmware ESP8266."),
            ("Thiết kế mạch", "KiCad EDA", "KiCad 10.0", "Vẽ sơ đồ nguyên lý, đi dây mạch in 1 lớp PCB Hub DIY v3 và kiểm tra 0 ERC / 0 DRC."),
        ],
        col_widths_cm=[2.4, 3.8, 3.2, 6.1],
        font_pt=9.5,
    )

    rb.add_logo_showcase_figure(
        [
            ("Python 3.14.7", logos_dir / "logo_python.png"),
            ("FastAPI 0.141.1", logos_dir / "logo_fastapi.png"),
            ("SQLite 3.53.2", logos_dir / "logo_sqlite.png"),
            ("Google Gemini 3.8 Live", logos_dir / "logo_gemini.png"),
        ],
        "Biểu trưng các công nghệ cốt lõi tầng Máy chủ, Cơ sở dữ liệu và Trợ lý giọng nói AI",
        cols=4,
        logo_max_h_cm=1.1,
    )
    rb.add_logo_showcase_figure(
        [
            ("Kotlin 2.3.20", logos_dir / "logo_kotlin.png"),
            ("Android (minSdk 26)", logos_dir / "logo_android.png"),
            ("Espressif / ESP8266", logos_dir / "logo_espressif.png"),
            ("KiCad 10.0", logos_dir / "logo_kicad.png"),
        ],
        "Biểu trưng các nền tảng phát triển Ứng dụng Android, Vi điều khiển ESP8266 và Thiết kế mạch KiCad",
        cols=4,
        logo_max_h_cm=1.1,
    )

    # ===== 3.6. KẾT LUẬN CHƯƠNG 3 =====
    rb.add_h2("3.6. Kết luận Chương 3")
    rb.add_para(
        "Chương 3 đã trình bày hoàn chỉnh thiết kế mạch điện tử làm nền tảng phần cứng cho toàn hệ thống: "
        "từ vi điều khiển NodeMCU ESP8266 v2 Amica với hợp đồng khóa cứng 10 chân an toàn boot-strap, "
        "3 cảm biến 3,3V, 6 thiết bị chấp hành và hệ thống bảo vệ nguồn – dập xung hàn trực tiếp trên bo mạch 1 lớp "
        "PCB Hub DIY v3 (100×80 mm, 51 footprints, 0 ERC / 0 DRC, 40 dây đấu nối ≤ 30 cm), đến lưu đồ hoạt động firmware "
        "có bảo vệ ngoại tuyến và bộ công nghệ phần mềm cốt lõi. Trong Chương 4, em sẽ trình bày chi tiết quy trình "
        "thiết kế và triển khai phần mềm ở tầng máy chủ, xử lý giọng nói AI, phân quyền 3 tầng, giao diện Web 3D và ứng dụng Android."
    )
