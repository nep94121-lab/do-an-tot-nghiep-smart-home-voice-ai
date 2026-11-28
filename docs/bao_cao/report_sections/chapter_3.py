"""Chapter 3: Công nghệ và linh kiện sử dụng (Hardware SSOT, Protocols, Official Logos, Software/Versions)."""

from __future__ import annotations

import pathlib

from .docx_helpers import ReportBuilder


def build_chapter_3(rb: ReportBuilder, assets_dir: pathlib.Path) -> None:
    demo_dir = assets_dir / "demo"
    logos_dir = assets_dir / "logos"
    sw_dir = assets_dir / "software"

    rb.add_chapter(3, "CÔNG NGHỆ VÀ LINH KIỆN SỬ DỤNG")
    rb.add_para(
        "Trong Chương 3, báo cáo trình bày chi tiết cơ sở lựa chọn phần cứng theo Nguồn sự thật duy nhất (SSOT) của dự án, "
        "bảng ánh xạ đầy đủ 14 khối/module vật lý sang 6 thiết bị chấp hành và 3 cảm biến, hợp đồng 10 chân khóa cứng trên NodeMCU ESP8266 v2 Amica, "
        "hệ thống linh kiện bảo vệ hàn trực tiếp trên PCB Hub DIY v3, các giao thức truyền thông và toàn bộ nền tảng phần mềm kèm phiên bản thực tế."
    )

    # ===== 3.1 LỰA CHỌN LINH KIỆN PHẦN CỨNG =====
    rb.add_h2("3.1. Lựa chọn linh kiện phần cứng và ánh xạ SSOT")
    rb.add_para(
        "Để đảm bảo tính an toàn điện tuyệt đối trong mô hình trình diễn đồ án và tối ưu chi phí chế tạo, toàn bộ hệ thống vận hành "
        "ở điện áp thấp 5V DC / 3,3V DC từ một bộ nguồn ngoài duy nhất 5V–2A cấp vào domino J1 của bo mạch PCB Hub trung tâm DIY v3. "
        "Mọi kích thước vật lý, cổng cắm và mã chân được đối chiếu thống nhất từ bốn tệp SSOT của kho mã nguồn: "
        "hardware/wiring_contract.py, hardware/kicad/smarthome_hub/bom.csv, docs/phan_cung/WIRING_TABLE.md và "
        "docs/phan_cung/DANH_SACH_LINH_KIEN_HIEN_CO_VA_CAN_MUA.md."
    )
    rb.add_para(
        "Ghi chú về phạm vi khóa cứng và các hạng mục cũ đã loại bỏ: So với các phiên bản phác thảo sơ khai ban đầu, "
        "hệ thống hoàn thiện đã loại bỏ hoàn toàn bảng cắm thử nghiệm breadboard trắng 400 lỗ (thay bằng kiến trúc cắm trực tiếp 100% lên "
        "PCB Hub DIY v3 — PCB-Direct), đồng thời không sử dụng quạt làm mát, không sử dụng tải xoay chiều 220V AC và không sử dụng khối thu phát hồng ngoại IR "
        "(VS1838B / LED phát 940 nm) ở bất kỳ lớp nào từ firmware, sơ đồ KiCad đến mô hình 3D. Bảng 3.1 trình bày ánh xạ đầy đủ "
        "14 khối/module vật lý ngoại vi và 2 bo lõi trung tâm sang đúng 6 thiết bị chấp hành và 3 cảm biến."
    )

    rb.add_table(
        "Bảng ánh xạ SSOT từ 14 khối/module vật lý và 2 bo lõi sang 6 thiết bị chấp hành + 3 cảm biến",
        ["STT", "Mã module SSOT", "Tên khối/module vật lý", "Vai trò hệ thống", "Cổng PCB & Chân MCU", "Kích thước (mm)"],
        [
            ("1", "sg90_servo", "Động cơ Servo SG90 9g", "Chấp hành 1: Cửa chính (main_door)", "J3 · D1 (GPIO5)", "22,8 × 12,2 × 22,5"),
            ("2", "led_living", "Đèn LED 5mm Phòng khách", "Chấp hành 2: Đèn phòng khách (living_room_light)", "J4 · D0 (GPIO16)", "Ø5,8 × 8,6"),
            ("3", "led_bedroom", "Đèn LED 5mm Phòng ngủ", "Chấp hành 3: Đèn phòng ngủ Active-LOW (bedroom_light)", "J5 · D4 (GPIO2)", "Ø5,8 × 8,6"),
            ("4", "relay1_pump", "Relay 1 kênh 5V xanh (SRD-05VDC)", "Đóng cắt nguồn 5V cho Chấp hành 4 (Bơm)", "J7, J8 · D6 (GPIO12)", "50,0 × 26,0 × 18,5"),
            ("5", "pump_unit", "Máy bơm nước chìm mini 3–6V DC", "Chấp hành 4: Máy bơm tưới cây (garden_pump)", "J2 (qua Relay 1 + D1)", "45,0 × 24,0 × 33,0"),
            ("6", "buzzer_alarm", "Còi chủ động 5V TMB12A05", "Chấp hành 5: Còi báo động (alarm_siren)", "J6 · D8 (GPIO15 qua Q1)", "Ø12,0 × 9,5"),
            ("7", "relay2_speaker", "Relay 2 đỏ 5V opto PC817 (Jmp=H)", "Đóng cắt nguồn 5V cho Chấp hành 6 (Loa)", "J9, J10 · D7 (GPIO13)", "50,0 × 26,0 × 18,5"),
            ("8", "pam8403_amp", "Mạch khuếch đại Class-D PAM8403", "Chấp hành 6: Khuếch đại âm thanh (speaker_amp)", "J11, J12 · D3 (GPIO0)", "21,0 × 18,0 × 3,1"),
            ("9", "speaker_mini", "Loa tròn mini 28 mm (8 Ω, 0,5 W)", "Ngõ ra âm thanh cầu BTL cho PAM8403", "PAM8403 L_OUT+/L_OUT-", "Ø28,0 × 5,2"),
            ("10", "dht11_sensor", "Cảm biến DHT11 3 chân", "Cảm biến 1: Nhiệt độ & Độ ẩm không khí", "J13 · D2 (GPIO4, 3,3V)", "28,0 × 14,0 × 7,1"),
            ("11", "soil_lm393", "Mạch so sánh độ ẩm đất LM393", "Cảm biến 2: Xử lý tín hiệu tương tự độ ẩm đất", "J14 · A0 (ADC0, 3,3V)", "32,0 × 14,0 × 12,1"),
            ("12", "soil_probe", "Đầu dò 2 nhánh YL-69", "Cảm biến 2: Đầu dò cắm chậu cây", "Nối 2 dây vào LM393", "60,0 × 20,0 × 1,6"),
            ("13", "ky037_sound", "Cảm biến âm thanh KY-037/038", "Cảm biến 3: Phát hiện tiếng vỗ tay/tiếng động (DO)", "J15 · D5 (GPIO14, 3,3V)", "35,0 × 15,0 × 13,1"),
            ("14", "psu_5v", "Nguồn ngoài 5V 2A + Giắc DC-022", "Khối nguồn DC tổng toàn hệ thống", "J1 (PWR_5V_IN)", "34,0 × 22,0 × 16,0"),
            ("Lõi 1", "nodemcu", "NodeMCU ESP8266 v2 Amica (CP2102)", "Vi điều khiển trung tâm Wi-Fi 2,4 GHz", "Đế U1, U2 (2 × 15 chân)", "48,3 × 25,4 × 7,1"),
            ("Lõi 2", "hub_pcb", "Bo mạch PCB Hub Trung Tâm DIY v3", "Bo kết nối trực tiếp, tích hợp C1–C9, D1–D2, Q1", "J1–J15, U1–U2, JP1–JP7", "100,0 × 80,0 × 1,6"),
        ],
        col_widths_cm=[1.0, 2.2, 3.4, 3.8, 2.9, 2.2],
        font_pt=9.5,
        center_cols=(0, 5),
    )

    rb.add_figure(
        demo_dir / "components_shopee_grid.png",
        "Tổng hợp bộ linh kiện điện tử thực tế sử dụng trong hệ thống Smart Home Voice AI",
        max_width_cm=12.5,
        max_height_cm=10.5,
    )

    rb.add_h3("3.1.1. Vi điều khiển trung tâm NodeMCU ESP8266 v2 Amica và hợp đồng 10 chân")
    rb.add_para(
        "Vi điều khiển được chọn là NodeMCU ESP8266 v2 Amica sử dụng mô-đun ESP-12E/F (lõi Tensilica L106 32-bit xung nhịp 80/160 MHz, "
        "bộ nhớ Flash 4 MB hỗ trợ phân vùng hệ thống tệp LittleFS, Wi-Fi chuẩn IEEE 802.11 b/g/n băng tần 2,4 GHz) kết hợp chip nạp USB-UART "
        "Silicon Labs CP2102 cho độ ổn định driver cao trên Windows. Phiên bản v2 Amica có kích thước gọn 48,26 × 25,40 mm với khoảng cách hai hàng chân "
        "hẹp tiêu chuẩn 0,9 inch (22,86 mm), cắm trực tiếp vào cặp đế cái 1×15 chân (U1, U2) trên PCB Hub DIY v3 (không dùng bản v3 LoLin bản rộng 31 mm)."
    )
    rb.add_para(
        "Do dòng ESP8266 có ba chân cấu hình chế độ khởi động (boot-strap) đặc thù là GPIO0 (D3), GPIO2 (D4) và GPIO15 (D8), "
        "việc gán chân tùy tiện rất dễ làm mạch không thể khởi động hoặc kích còi giả khi cấp nguồn. Bảng 3.2 trình bày hợp đồng 10 chân khóa cứng "
        "đồng bộ tuyệt đối giữa sơ đồ KiCad và tệp firmware esp8266_smarthome.ino."
    )

    rb.add_table(
        "Hợp đồng khóa cứng 10 chân NodeMCU ESP8266 v2 Amica và cơ chế an toàn khởi động (Boot-Strap)",
        ["Chân MCU", "GPIO", "Macro Firmware", "Cổng Hub", "Thiết bị / Cảm biến", "Cơ chế cực tính & An toàn khởi động"],
        [
            ("D0", "GPIO16", "PIN_LIVING_LIGHT", "J4", "Đèn phòng khách", "Active-HIGH qua trở R1 220 Ω; kiêm nháy báo mất mạng"),
            ("D1", "GPIO5", "PIN_MAIN_DOOR_SERVO", "J3", "Servo SG90 Cửa chính", "PWM 50 Hz (0° đóng / 90° mở); nguồn +5V lọc C1 470 µF"),
            ("D2", "GPIO4", "PIN_DHT11", "J13", "Cảm biến DHT11", "Bus 1-Wire cấp 3,3V; kéo lên bằng trở R3 10 kΩ trên PCB"),
            ("D3", "GPIO0", "PIN_AUDIO_PWM", "J12", "Audio PWM → PAM8403", "Boot HIGH: R4 10 kΩ kéo lên + tụ chặn DC C4 10 µF; nghỉ = INPUT"),
            ("D4", "GPIO2", "PIN_BEDROOM_LIGHT", "J5", "Đèn phòng ngủ", "Boot HIGH: đấu Active-LOW qua R2 220 Ω + R7 10 kΩ kéo lên"),
            ("D5", "GPIO14", "PIN_KY037_DO", "J15", "Âm thanh KY-037 DO", "Cấp chuẩn 3,3V; ngắt cạnh lên RISING, chống dội >= 400 ms"),
            ("D6", "GPIO12", "PIN_GARDEN_PUMP", "J7/J8/J2", "Relay 1 → Máy bơm 5V", "Active-HIGH; bơm có diode D1 1N4007 + C2 470 µF; tối đa 120 s"),
            ("D7", "GPIO13", "PIN_SPEAKER_AMP", "J9/J10/J11", "Relay 2 → PAM8403", "Active-HIGH (jumper H); tự tắt nguồn loa 1,5 s sau khi phát chuông"),
            ("D8", "GPIO15", "PIN_ALARM_SIREN", "J6", "Còi báo động 5V", "Boot LOW: R9 10 kΩ kéo xuống + R10 1 kΩ lái Q1 S8050 + D2 1N4007"),
            ("A0", "ADC0", "PIN_SOIL_MOISTURE", "J14", "Độ ẩm đất LM393 AO", "ADC 10-bit 0–3,3V lọc C7 100 nF; LM393 bắt buộc cấp 3,3V"),
        ],
        col_widths_cm=[1.4, 1.5, 3.0, 1.6, 2.7, 5.3],
        font_pt=9.5,
        center_cols=(0, 1, 3),
    )

    rb.add_h3("3.1.2. Đặc tính kỹ thuật các thiết bị chấp hành, cảm biến và phân tách khối âm thanh")
    rb.add_para(
        "Một điểm quan trọng trong kiến trúc phần cứng của đề tài là sự phân tách rạch ròi ba chức năng âm thanh khác nhau "
        "nhằm tránh nhầm lẫn khi trình bày và đảm bảo hiệu năng xử lý: (1) Micro và loa phục vụ hội thoại AI Gemini 3.8 Live sử dụng trực tiếp "
        "phần cứng âm thanh của trình duyệt Web và điện thoại Android với chất lượng PCM 16/24 kHz; (2) Cảm biến KY-037/038 nối chân D5 chỉ đọc "
        "ngõ ra số DO để phát hiện tiếng vỗ tay hoặc âm thanh đột ngột vượt ngưỡng chỉnh trên biến trở W104; (3) Mạch khuếch đại PAM8403 kết hợp "
        "loa tròn 28 mm (8 Ω, 0,5 W) nối cầu vi sai BTL (tuyệt đối không nối đầu L_OUT- xuống GND) đóng vai trò loa phát chuông phản hồi phần cứng tại mô hình, "
        "được Relay 2 ngắt hẳn nguồn 5V lúc nghỉ để triệt tiêu hoàn toàn tiếng sôi nền Class-D."
    )
    rb.add_para(
        "Bảng 3.3 tóm tắt thông số điện – cơ chính của các khối chấp hành và cảm biến trích từ datasheet nhà sản xuất."
    )
    rb.add_table(
        "Thông số kỹ thuật các thiết bị chấp hành và cảm biến chính trong hệ thống",
        ["Linh kiện", "Điện áp hoạt động", "Dòng tiêu thụ / Công suất", "Giao tiếp / Tín hiệu", "Đặc tính nổi bật & Ghi chú thiết kế"],
        [
            ("NodeMCU ESP8266 v2 Amica", "5V (VIN) / 3,3V lõi", "80 mA TB, đỉnh ~300 mA Wi-Fi", "Wi-Fi 2,4 GHz, UART CP2102", "Flash 4 MB, LittleFS, 1 ADC 10-bit"),
            ("Servo SG90 9g (TowerPro)", "4,8V – 6,0V DC", "100–250 mA chạy, ~600 mA kẹt", "PWM 50 Hz (1–2 ms)", "Mô-men xoắn 1,8 kg·cm @ 4,8V; góc 0°–180°"),
            ("Máy bơm chìm mini DC", "3,0V – 6,0V DC", "130–220 mA @ 5V", "Đóng cắt qua Relay 1 (NO)", "Lưu lượng 80–120 L/h, đầu xả OD 7,5 mm"),
            ("Relay 1 xanh & Relay 2 đỏ opto", "5,0V DC (cuộn hút)", "~70 mA / kênh khi đóng", "Logic mức HIGH (Jumper H)", "Tiếp điểm SRD-05VDC 10A; Relay 2 cách ly quang PC817"),
            ("PAM8403 + Loa 28 mm 8 Ω", "2,5V – 5,5V DC", "Hiệu suất >85% (Class-D)", "Vào đơn L, ra cầu BTL", "Không nối L_OUT- với GND; lọc C6 100 nF + C9 100 µF"),
            ("Còi chủ động TMB12A05", "5,0V DC", "~30 mA @ 5V", "Lái low-side NPN S8050", "Cường độ ~85 dB @ 10 cm, tần số ~2,3 kHz"),
            ("Cảm biến DHT11 (3 chân)", "3,3V DC", "0,3–2,5 mA", "1-Wire số (D2)", "Đo 0–50 °C (±2 °C), 20–90% RH (±5%), chu kỳ >= 2 s"),
            ("LM393 + Đầu dò YL-69", "3,3V DC (bắt buộc)", "< 15 mA", "Tương tự AO → A0", "Ngưỡng tưới trễ: <40% bật bơm, >=70% tắt bơm"),
            ("Cảm biến âm thanh KY-037", "3,3V DC (bắt buộc)", "< 10 mA", "Số DO → D5 (RISING)", "Micro electret Ø9,7 mm, chỉnh ngưỡng bằng W104"),
        ],
        col_widths_cm=[3.2, 2.2, 2.8, 2.7, 4.6],
        font_pt=9.5,
    )

    rb.add_h3("3.1.3. Hệ thống 23 linh kiện bảo vệ và lọc nguồn hàn trên PCB Hub DIY v3")
    rb.add_para(
        "Điểm khác biệt quan trọng giúp hệ thống đạt độ ổn định cao so với mạch thử nghiệm thông thường là việc tính toán và tích hợp "
        "đủ 23 linh kiện thụ động, bán dẫn và chỉ thị (R1–R10, Q1, C1–C9, D1–D3) trực tiếp trên bo mạch PCB Hub trung tâm DIY v3 "
        "(tổng 51 footprints trong BOM bao gồm thêm U1–U2, J1–J15, JP1–JP7 và 4 lỗ bắt ốc M3 H1–H4). Bảng 3.4 liệt kê vai trò bảo vệ điện tử của từng linh kiện."
    )
    rb.add_table(
        "Kiểm kê 23 linh kiện bảo vệ, lọc nguồn và lái công suất hàn trực tiếp trên PCB Hub DIY v3",
        ["Ký hiệu", "Giá trị / Mã", "Kiểu chân", "Lưới kết nối KiCad", "Chức năng bảo vệ và ổn định điện tử"],
        [
            ("R1, R2", "220 Ω (1/4W)", "Axial P10,16 mm", "D0/LED_LR, +3V3/LED_BR", "Hạn dòng bảo vệ 2 bóng LED 5 mm (~5–10 mA)"),
            ("R3, R4, R7", "10 kΩ (1/4W)", "Axial P10,16 mm", "+3V3 ↔ D2, D3, D4", "Điện trở kéo lên cho bus DHT11 và an toàn boot GPIO0/GPIO2"),
            ("R5, R6", "2,2 kΩ (1/4W)", "Axial P10,16 mm", "AUD_AC → AUD_OUT → GND", "Cầu phân áp suy giảm ~50% biên độ tín hiệu PWM vào PAM8403"),
            ("R8, D3", "1 kΩ + LED xanh", "Axial + LED 3 mm", "+5V → R8 → D3 → GND", "Đèn chỉ thị nguồn chính +5V đang hoạt động trên bo mạch"),
            ("R9, R10", "10 kΩ / 1 kΩ", "Axial P10,16 mm", "D8 ↔ GND / BUZZ_BASE", "R9 giữ GPIO15 LOW khi boot; R10 cấp dòng cực B ~2,6 mA cho Q1"),
            ("Q1", "S8050 (NPN)", "TO-92 Wide", "E=GND, B=R10, C=BUZZ_K", "Transistor lái low-side 0,7A cách ly dòng còi 5V khỏi chân D8"),
            ("C1, C2", "470 µF 16V", "Hóa Ø8×P3,5 mm", "+5V ↔ GND (cạnh J1/J2/J3)", "Tụ dự trữ năng lượng chống sụt áp reset ESP8266 khi Servo/Bơm chạy"),
            ("C3, C6, C7, C8", "100 nF 50V (104)", "Gốm P5,0 mm", "+5V, AMP_5V, A0, +3V3", "Lọc nhiễu cao tần nguồn +5V, nguồn loa, ADC0 đất và nguồn +3,3V"),
            ("C4", "10 µF 16V", "Hóa Ø5×P3,5 mm", "D3_AUDIO_PWM → AUD_AC", "Tụ chặn thành phần DC cô lập chân boot GPIO0 khỏi ngõ vào PAM8403"),
            ("C5", "10 nF 50V (103)", "Gốm P5,0 mm", "AUD_OUT ↔ GND", "Tụ lọc thông thấp RC (fc ≈ 14,5 kHz) làm mịn sóng mang PWM âm thanh"),
            ("C9", "100 µF 16V", "Hóa Ø6,3×P3,5 mm", "AMP_5V ↔ GND (cạnh J11)", "Tụ hóa dự trữ dòng đỉnh cho tầng khuếch đại Class-D PAM8403"),
            ("D1", "1N4007 (1000V/1A)", "DO-41 P10,16 mm", "K=PUMP_5V, A=GND (J2)", "Diode dập xung ngược (flyback) triệt sức điện động cảm ứng máy bơm"),
            ("D2", "1N4007 (1000V/1A)", "DO-41 P10,16 mm", "K=+5V, A=BUZZ_K (J6)", "Diode dập xung ngược bảo vệ cực C transistor Q1 S8050 khi ngắt còi"),
        ],
        col_widths_cm=[1.9, 2.3, 2.3, 3.2, 5.8],
        font_pt=9.5,
    )

    rb.add_figure(
        demo_dir / "pcb_modules_wired_3d_iso.png",
        "Mô hình 3D bo mạch PCB Hub DIY v3 kết nối trực tiếp đầy đủ 14 module ngoại vi",
        max_width_cm=14.2,
        max_height_cm=9.5,
    )
    rb.add_figure(
        demo_dir / "wiring_diagram_2d.png",
        "Sơ đồ đấu nối chuẩn 2D của 40 dây nối vật lý giữa PCB Hub DIY v3 và các module",
        max_width_cm=14.8,
        max_height_cm=9.8,
    )

    # ===== 3.2 & 3.3 GIAO THỨC TRUYỀN THÔNG =====
    rb.add_h2("3.2. Giao thức giao tiếp giữa vi điều khiển và cảm biến, chấp hành")
    rb.add_para(
        "Ở tầng nhúng, NodeMCU ESP8266 giao tiếp với 9 thiết bị và cảm biến thông qua 4 cơ chế tín hiệu vật lý tiêu chuẩn: "
        "(1) Giao tiếp số GPIO mức logic 3,3V cho đèn phòng khách, đèn phòng ngủ (Active-LOW), hai kênh Relay kích mức HIGH, "
        "mạch lái còi Q1 và ngắt cạnh lên RISING đọc cảm biến âm thanh KY-037 với thời gian chống dội 400 ms; "
        "(2) Giao thức 1-Wire đơn dây bán song công trên chân D2 cho cảm biến DHT11 có điện trở kéo lên 10 kΩ; "
        "(3) Điều chế độ rộng xung PWM tần số 50 Hz trên chân D1 (độ rộng xung 0,5–2,4 ms) điều khiển góc quay 0°/90° cho Servo SG90 "
        "và xung âm tần tone() trên chân D3 qua mạch lọc thông thấp RC tới PAM8403; "
        "(4) Bộ chuyển đổi tương tự – số ADC 10-bit (0–1023) trên chân A0 đọc điện áp đầu ra AO từ mạch LM393 (được lọc nhiễu bằng C7 100 nF) "
        "để quy đổi tuyến tính thành phần trăm độ ẩm đất 0–100%."
    )

    rb.add_h2("3.3. Giao thức truyền thông dữ liệu mạng và thời gian thực")
    rb.add_para(
        "Để đáp ứng đồng thời yêu cầu độ trễ cực thấp của âm thanh hai chiều, tính nhẹ nhàng cho vi điều khiển tài nguyên hạn chế "
        "và khả năng vượt tường lửa NAT an toàn khi điều khiển từ xa, hệ thống phối hợp bốn giao thức tầng ứng dụng gồm HTTP/REST, "
        "WebSocket, Server-Sent Events (SSE) và MQTT trên nền TCP/IP (kèm đường hầm mã hóa WireGuard/TLS qua Tailscale Funnel). "
        "Bảng 3.5 so sánh vai trò và thông số cấu hình từng giao thức."
    )
    rb.add_table(
        "Tổng hợp các giao thức truyền thông và tín hiệu sử dụng trong hệ thống",
        ["Giao thức", "Chiều truyền", "Tuyến kết nối", "Vai trò trong hệ thống Smart Home Voice AI"],
        [
            ("HTTP/HTTPS REST", "Yêu cầu – Phản hồi", "Web/Android/ESP8266 ↔ FastAPI", "Đăng nhập, OTP, RBAC, QR động, bật/tắt thiết bị, cài hẹn giờ, đồng bộ phục hồi /api/hardware/resync."),
            ("WebSocket (WS/WSS)", "Song công toàn phần", "Web/Android ↔ FastAPI ↔ Gemini Live", "Truyền luồng âm thanh PCM 16 kHz vào / 24 kHz ra theo khung 20 ms và gọi 20 Function Tools thời gian thực."),
            ("Server-Sent Events", "Một chiều (Server → Client)", "FastAPI → Web/Android", "Đẩy tức thời trạng thái 6 thiết bị, 3 cảm biến và thông báo sự kiện tới mọi màn hình đang mở."),
            ("MQTT (TCP 1883)", "Publish / Subscribe", "FastAPI (paho-mqtt) ↔ ESP8266", "Truyền lệnh điều khiển smarthome/cmd/+ và nhận telemetry cảm biến smarthome/telemetry/+ siêu nhẹ."),
            ("Tailscale Funnel + Vercel", "Đường hầm TLS đầu cuối", "Internet → Vercel → Tailscale → :8088", "Xuất bản hệ thống cục bộ ra Internet có chứng chỉ HTTPS tự động mà không cần mở port Router."),
            ("1-Wire / PWM / ADC / UART", "Mức vật lý cục bộ", "ESP8266 ↔ 14 Module & USB PC", "Đọc cảm biến DHT11/LM393/KY-037, lái Servo SG90/Loa, nạp firmware và cấu hình Wi-Fi 115200 baud."),
        ],
        col_widths_cm=[3.2, 2.7, 3.6, 6.0],
        font_pt=10.0,
    )

    # ===== 3.4 NGÔN NGỮ LẬP TRÌNH, PHẦN MỀM VÀ CÔNG CỤ PHÁT TRIỂN =====
    rb.add_h2("3.4. Ngôn ngữ lập trình, phần mềm và bộ công cụ phát triển")
    rb.add_para(
        "Toàn bộ công cụ phần mềm, ngôn ngữ lập trình và thư viện cốt lõi sử dụng trong dự án đều là mã nguồn mở hoặc nền tảng chuẩn công nghiệp, "
        "được kiểm kê phiên bản trực tiếp từ máy triển khai (build_receipts/env_inventory.json) và các tệp cấu hình khóa phiên bản của kho mã nguồn "
        "(requirements.txt, platformio.ini, app/project.lightbuild.yaml, app/app-core/lightbuild.yaml). Bảng 3.6 tổng hợp đầy đủ danh mục công nghệ và phiên bản thực tế."
    )
    rb.add_table(
        "Danh mục ngôn ngữ, thư viện và công cụ phần mềm sử dụng kèm phiên bản chính xác",
        ["Nhóm công cụ", "Tên công nghệ / Phần mềm", "Phiên bản đo thực tế", "Vai trò cụ thể trong đồ án"],
        [
            ("Backend & AI", "Python", "3.14.7 (64-bit)", "Ngôn ngữ chính phát triển máy chủ, công cụ tự động hóa và sinh báo cáo."),
            ("Backend & AI", "FastAPI / Uvicorn / Pydantic", "0.141.1 / 0.53.0 / 2.13.4", "Khung máy chủ ASGI bất đồng bộ, tự sinh đặc tả OpenAPI 3.1 và kiểm định dữ liệu."),
            ("Backend & AI", "SQLite / aiosqlite", "3.53.2 / 0.22.1", "Cơ sở dữ liệu quan hệ 3NF nhúng chế độ WAL lưu người dùng, phiên, luật và nhật ký."),
            ("Backend & AI", "Google Gemini Live (google-genai)", "Model gemini-3.8-live / SDK 2.33.0", "Mô hình giọng nói đa phương thức thời gian thực (giọng Aoede 100% tiếng Việt)."),
            ("Backend & AI", "paho-mqtt / websockets / httpx", "2.2.0 / 15.0.1 / 0.28.1", "Giao tiếp MQTT với ESP8266, WebSocket hai chiều và gọi HTTP bất đồng bộ."),
            ("Web & 3D", "HTML5 / CSS3 / JavaScript", "Chuẩn ES2022+", "Xây dựng giao diện đa trang (/, /automation, /auth, /wokwi, /logs) đáp ứng Sáng/Tối."),
            ("Web & 3D", "Three.js", "Đóng gói nội bộ web/vendor/three.min.js", "Kết xuất mô hình song sinh số 3D nhà thông minh tương tác 14 module thời gian thực."),
            ("Android Mobile", "Kotlin / Java / Jetpack Compose", "Kotlin 2.3.20 / JDK 17 / Compose 1.10.4", "Phát triển ứng dụng Android thuần Material 3 (1.4.0), Navigation3 (1.0.1), minSdk 26."),
            ("Android Mobile", "Lightbuild / Android SDK", "Lightbuild 0.0.30 (CLI 0.0.1) / API 34–36", "Biên dịch và đóng gói tệp cài đặt Android SmartHomeVoiceAI-v1.0.apk."),
            ("Nhúng & Mạch", "PlatformIO Core / Espressif8266", "PlatformIO 6.2.0 / Arduino nodemcuv2", "Biên dịch, nạp firmware C/C++ ESP8266 (PubSubClient 2.8, ArduinoJson 6.21.5, DHT 1.4.6)."),
            ("Nhúng & Mạch", "KiCad EDA", "KiCad 10.0 (rev 3.0-DIY)", "Thiết kế sơ đồ nguyên lý, định tuyến mạch in 1 lớp PCB Hub DIY v3 và kiểm tra ERC/DRC."),
            ("Cơ khí & In 3D", "FreeCAD / Blender / PrusaSlicer", "FreeCAD 1.1.4 / Blender 5.2.2 LTS / PrusaSlicer 2.9.7", "Thiết kế CAD tham số 51 chi tiết lắp mộng, kết xuất 3D minh họa và cắt lớp 16 bàn in PLA."),
            ("Kiểm thử & Ops", "Git / GitHub / VS Code", "Git 2.50.0 / VS Code", "Quản lý mã nguồn phân nhánh, soát lỗi và phát triển toàn hệ thống."),
            ("Kiểm thử & Ops", "Pytest / Playwright / Tailscale / Vercel", "pytest 9.1.1 / Playwright 1.63.0 / Tailscale 1.104.6", "Kiểm thử hồi quy tự động 116 tệp, kiểm thử trình duyệt ẩn và triển khai truy cập từ xa."),
        ],
        col_widths_cm=[2.4, 3.9, 3.6, 5.6],
        font_pt=9.5,
    )

    rb.add_h3("3.4.1. Bộ công cụ phát triển Backend, Cơ sở dữ liệu và Trí tuệ nhân tạo")
    rb.add_para(
        "Python 3.14.7 kết hợp FastAPI 0.141.1 được lựa chọn cho tầng máy chủ nhờ khả năng xử lý đồng thời hiệu suất cao dựa trên vòng lặp sự kiện asyncio, "
        "tích hợp sẵn kiểm tra kiểu dữ liệu Pydantic 2.13.4 và tài liệu OpenAPI 3.1 trực quan. SQLite 3.53.2 bật chế độ WAL loại bỏ hoàn toàn "
        "gánh nặng cài đặt dịch vụ cơ sở dữ liệu rời trên máy tính gia đình nhưng vẫn đảm bảo toàn vẹn khóa ngoại và giao dịch ACID. "
        "Google Gemini 3.8 Live đóng vai trò bộ não hội thoại tiếng Việt trực tiếp âm thanh-sang-âm thanh (speech-to-speech), rút ngắn đáng kể độ trễ so với chuỗi STT–LLM–TTS truyền thống."
    )
    rb.add_logo_showcase_figure(
        [
            ("Python 3.14.7", logos_dir / "logo_python.png"),
            ("FastAPI 0.141.1", logos_dir / "logo_fastapi.png"),
            ("SQLite 3.53.2", logos_dir / "logo_sqlite.png"),
            ("Google Gemini 3.8 Live", logos_dir / "logo_gemini.png"),
        ],
        "Biểu trưng các công nghệ lõi tầng Máy chủ Backend, Cơ sở dữ liệu và Trí tuệ nhân tạo",
        cols=4,
    )
    rb.add_figure(
        sw_dir / "sw_fastapi_openapi.png",
        "Giao diện đặc tả OpenAPI 3.1 tự sinh từ máy chủ FastAPI của hệ thống Smart Home Voice AI",
        max_width_cm=14.8,
        max_height_cm=8.6,
    )

    rb.add_h3("3.4.2. Bộ công cụ phát triển giao diện Web 3D và Ứng dụng di động Android")
    rb.add_para(
        "Giao diện Web được xây dựng thuần bằng HTML5, CSS3 và JavaScript hiện đại không phụ thuộc khung đóng gói nặng nề, giúp tải trang nhanh "
        "và dễ bảo trì lâu dài; thư viện đồ họa WebGL Three.js (đóng gói cục bộ trong web/vendor/three.min.js để không phụ thuộc CDN khi chạy LAN) "
        "đảm nhiệm dựng cảnh ngôi nhà 3D tương tác đủ 14 module. Ở phía di động, ứng dụng Android được viết 100% bằng Kotlin 2.3.20 với giao diện khai báo "
        "Jetpack Compose 1.10.4 (Material Design 3) và biên dịch nhanh qua Lightbuild, bảo đảm hiệu năng gốc và khả năng gọi trực tiếp API ghi âm PCM cũng như camera quét mã QR."
    )
    rb.add_logo_showcase_figure(
        [
            ("HTML5", logos_dir / "logo_html5.png"),
            ("CSS3", logos_dir / "logo_css3.png"),
            ("JavaScript", logos_dir / "logo_javascript.png"),
            ("Three.js", logos_dir / "logo_threejs.png"),
        ],
        "Biểu trưng các công nghệ phát triển Giao diện Web và Mô phỏng 3D Digital Twin",
        cols=4,
    )
    rb.add_logo_showcase_figure(
        [
            ("Kotlin 2.3.20", logos_dir / "logo_kotlin.png"),
            ("Android (minSdk 26)", logos_dir / "logo_android.png"),
        ],
        "Biểu trưng nền tảng và ngôn ngữ phát triển Ứng dụng Di động Android",
        cols=2,
    )
    rb.add_figure(
        sw_dir / "sw_cli_lightbuild_android.png",
        "Môi trường dòng lệnh Lightbuild và cấu hình dự án ứng dụng Android Kotlin Compose",
        max_width_cm=14.6,
        max_height_cm=8.5,
    )
    rb.add_figure(
        None,
        "Giao diện môi trường phát triển Android Studio / Lightbuild IDE mở mã nguồn ứng dụng",
        max_width_cm=14.2,
        placeholder_label="[ẢNH CHỤP PHẦN MỀM: Giao diện Android Studio mở dự án Android Kotlin Compose (app/)]",
        placeholder_sublabel="Môi trường GUI máy tính để bàn — chụp và thay thế trực tiếp khi bàn giao bản in cuối cùng",
    )

    rb.add_h3("3.4.3. Công cụ lập trình nhúng, thiết kế mạch điện tử và chế tạo cơ khí in 3D")
    rb.add_para(
        "Hệ thống sử dụng PlatformIO Core 6.2.0 thay cho Arduino IDE truyền thống để quản lý chặt chẽ phiên bản thư viện (PubSubClient, ArduinoJson, DHT) "
        "và hỗ trợ tự động hóa biên dịch/nạp firmware qua kịch bản PowerShell. Thiết kế sơ đồ nguyên lý và mạch in PCB Hub DIY v3 được thực hiện hoàn toàn trên KiCad 10.0 "
        "cho phép xuất trực tiếp bản in 1:1 lật gương phục vụ ăn mòn thủ công hoặc đặt mạch công nghiệp. Toàn bộ phần vỏ nhà lắp mộng 51 chi tiết được mô hình hóa "
        "tham số bằng FreeCAD 1.1.4, kết xuất hình ảnh minh họa bằng Blender 5.2.2 LTS và kiểm chứng cắt lớp G-code bằng PrusaSlicer 2.9.7."
    )
    rb.add_logo_showcase_figure(
        [
            ("Espressif / ESP8266", logos_dir / "logo_espressif.png"),
            ("PlatformIO 6.2.0", logos_dir / "logo_platformio.png"),
            ("KiCad 10.0", logos_dir / "logo_kicad.png"),
        ],
        "Biểu trưng bộ công cụ lập trình nhúng ESP8266 và thiết kế mạch điện tử PCB",
        cols=3,
    )
    rb.add_logo_showcase_figure(
        [
            ("FreeCAD 1.1.4", logos_dir / "logo_freecad.png"),
            ("Blender 5.2.2 LTS", logos_dir / "logo_blender.png"),
            ("PrusaSlicer 2.9.7", logos_dir / "logo_prusaslicer.png"),
        ],
        "Biểu trưng bộ công cụ thiết kế cơ khí 3D tham số, kết xuất 3D và cắt lớp in 3D",
        cols=3,
    )
    rb.add_figure(
        sw_dir / "sw_cli_platformio.png",
        "Kết quả biên dịch firmware NodeMCU ESP8266 v2 Amica bằng PlatformIO Core 6.2.0",
        max_width_cm=14.6,
        max_height_cm=8.5,
    )
    rb.add_figure(
        sw_dir / "sw_kicad_schematic.png",
        "Sơ đồ nguyên lý bo mạch PCB Hub trung tâm DIY v3 thiết kế trên KiCad 10.0",
        max_width_cm=14.8,
        max_height_cm=9.8,
    )

    rb.add_h3("3.4.4. Công cụ quản lý mã nguồn, kiểm thử tự động và triển khai vận hành")
    rb.add_para(
        "Quá trình phát triển áp dụng quy trình kiểm soát phiên bản chặt chẽ bằng Git 2.50.0 và GitHub trên môi trường soạn thảo Visual Studio Code. "
        "Chất lượng phần mềm được bảo chứng liên tục bằng bộ kiểm thử tự động pytest 9.1.1 kết hợp Playwright 1.63.0 kiểm thử giao diện trình duyệt thực, "
        "trong khi tầng vận hành từ xa sử dụng Tailscale Funnel 1.104.6 phối hợp Vercel Edge Proxy. Hồ sơ nguồn và giấy phép sử dụng học thuật của toàn bộ "
        "21 biểu trưng phần mềm được lưu đầy đủ tại tệp docs/bao_cao/LOGO_SOURCES.md."
    )
    rb.add_logo_showcase_figure(
        [
            ("GitHub", logos_dir / "logo_github.png"),
            ("Visual Studio Code", logos_dir / "logo_vscode.png"),
            ("Playwright 1.63.0", logos_dir / "logo_playwright.png"),
            ("Tailscale 1.104.6", logos_dir / "logo_tailscale.png"),
            ("Vercel", logos_dir / "logo_vercel.png"),
        ],
        "Biểu trưng bộ công cụ quản lý mã nguồn, kiểm thử tự động và triển khai truy cập từ xa",
        cols=5,
        logo_max_h_cm=1.35,
    )
    rb.add_figure(
        sw_dir / "sw_cli_pytest_git.png",
        "Môi trường quản lý mã nguồn Git 2.50.0 và kiểm thử tự động bằng Pytest 9.1.1",
        max_width_cm=14.6,
        max_height_cm=8.5,
    )
    rb.add_figure(
        None,
        "Giao diện soạn thảo mã nguồn Visual Studio Code quản lý toàn bộ dự án đa tầng",
        max_width_cm=14.2,
        placeholder_label="[ẢNH CHỤP PHẦN MỀM: Giao diện Visual Studio Code mở kho mã nguồn Smart Home Voice AI]",
        placeholder_sublabel="Môi trường GUI máy tính để bàn — chụp và thay thế trực tiếp khi bàn giao bản in cuối cùng",
    )

    rb.add_h2("3.5. Kết luận Chương 3")
    rb.add_para(
        "Chương 3 đã trình bày đầy đủ cơ sở kỹ thuật cho việc lựa chọn 14 module phần cứng (ánh xạ vào 6 thiết bị chấp hành + 3 cảm biến khóa cứng), "
        "hợp đồng 10 chân an toàn boot-strap trên NodeMCU ESP8266 v2 Amica, 23 linh kiện bảo vệ điện tử hàn trên PCB Hub DIY v3, "
        "bộ giao thức truyền thông đa lớp và toàn bộ 21 công cụ phần mềm kèm phiên bản thực tế. Chương 4 sẽ đi sâu vào thiết kế chi tiết và triển khai "
        "từng phân hệ từ máy chủ AI, giao diện Web/Android đến firmware nhúng, mạch in KiCad và vỏ nhà in 3D."
    )
