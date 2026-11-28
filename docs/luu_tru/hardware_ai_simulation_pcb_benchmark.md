<metadata>
Title: Báo Cáo Khảo Sát & Đánh Giá Nền Tảng Giả Lập Phần Cứng và Thiết Kế PCB Tích Hợp AI (MCP & Web UI)
Author: Antigravity Executive Agent
Project: Đồ án tốt nghiệp
Target_MCUs: ESP32, STM32, Arduino Uno/Mega/Nano, RP2040
Protocols: Model Context Protocol (MCP), REST API, CLI Automation
Generated_Date: 2026-09-22
Status: COMPLETED
</metadata>

<context>
Nghiên cứu và chọn lọc các giải pháp phần mềm/nền tảng đáp ứng đồng thời 2 yêu cầu then chốt của Sếp:
1. AI Agent có thể trực tiếp "chui vào" làm việc (thông qua chuẩn Model Context Protocol - MCP hoặc API/CLI tự động hóa).
2. Người dùng có giao diện màn hình trực quan (Visual Web/GUI) để theo dõi trực tiếp linh kiện, dây nối, màn hình hiển thị (OLED/LCD), đèn LED, tín hiệu mô phỏng và layout bo mạch PCB 2D/3D.
</context>

<specifications>
# 1. NỀN TẢNG GIẢ LẬP PHẦN CỨNG VI ĐIỀU KHIỂN (HARDWARE SIMULATORS)

### Top 1 (Khuyên dùng số 1): Wokwi (Wokwi Web Simulator & Wokwi MCP)
- **Website:** https://wokwi.com
- **Phần cứng hỗ trợ:**
  + **ESP32:** Đầy đủ ESP32 (WROOM), ESP32-S2, ESP32-S3, ESP32-C3, ESP32-C6. Hỗ trợ cả WiFi ảo (kết nối internet thật, MQTT, HTTP request).
  + **STM32:** STM32F401, STM32F103 (BluePill).
  + **Arduino:** Arduino Uno, Mega, Nano, ATtiny85.
  + **RP2040:** Raspberry Pi Pico / Pico W.
  + **Ngoại vi phong phú:** Màn hình OLED (SSD1306), LCD1602 (I2C), cảm biến DHT22/DHT11, nút bấm, potentiometer, servo motor, LED ma trận, còi buzzer, máy phân tích logic (Logic Analyzer), máy hiện sóng (Oscilloscope).
- **Cơ chế cho AI "chui vào":**
  + **Official MCP Server:** Công cụ `wokwi-cli` đã tích hợp sẵn lệnh `wokwi-cli mcp`. AI kết nối qua giao thức MCP stdio tiêu chuẩn để khởi động mô phỏng, nạp firmware, đọc serial monitor, kích hoạt chân tín hiệu ảo.
  + **Định dạng mạch hoàn toàn mở (JSON):** Toàn bộ sơ đồ nối dây, toạ độ linh kiện nằm trong file `diagram.json`. AI có thể tự sinh code mạch, tự nối dây giữa các pin (`"connections": [["esp:TX", "uno:RX", "green"]]`), tự đổi trị số linh kiện mà không sợ lỗi đồ họa.
- **Giao diện màn hình cho Sếp:**
  + Giao diện Web cực kỳ mượt mà, chân thực. Sếp thấy rõ bo mạch breadboard, đèn LED nhấp nháy theo thời gian thực, chữ chạy trên OLED/LCD, đồ thị xung trên Logic Analyzer.
  + Có extension "Wokwi for VS Code" giúp hiển thị trực tiếp tab mô phỏng ngay trong IDE.

---

### Top 2: Antmicro Renode
- **Website:** https://renode.io / https://github.com/renode/renode
- **Phần cứng hỗ trợ:** STM32, ESP32, RISC-V, ARM Cortex-M/R/A, mạng IoT đa node (mô phỏng 10-20 thiết bị truyền thông BLE/Zigbee/WiFi cùng lúc).
- **Cơ chế cho AI "chui vào":**
  + Có tích hợp **MCP Server** (stdio newline-delimited JSON-RPC, PR #974 / Issue #975).
  + Điều khiển qua kịch bản `.resc`, dòng lệnh Renode Monitor, kết nối GDB Debugger tự động.
- **Giao diện màn hình cho Sếp:**
  + Thiên về dòng lệnh và debug mức vi điều khiển (Registers, Waveform, Wireshark packet capture).
  + **Hạn chế:** Không có giao diện breadboard đồ hoạ cắm dây màu sắc như Wokwi. Phù hợp làm kiểm thử firmware tự động (HIL / CI-CD) hơn là nhìn trực quan linh kiện.

---

### Các công cụ khác (Không khuyến khích cho AI):
- **Tinkercad Circuits:** Có giao diện web đẹp cho Arduino cơ bản, nhưng hoàn toàn đóng kín, không có API, không có MCP, không hỗ trợ ESP32/STM32 chuyên sâu.
- **Proteus VSM:** Phần mềm desktop Windows trả phí đắt đỏ, không hỗ trợ giao thức MCP hiện đại.

---

# 2. PHẦN MỀM & NỀN TẢNG THIẾT KẾ PCB CHO AI (PCB DESIGN & EDA)

### Top 1 (AI-Native & Web 3D Live): tscircuit
- **Website:** https://tscircuit.com / https://github.com/tscircuit/tscircuit
- **Bản chất:** "React / TypeScript for Circuit Design" (Thiết kế phần cứng bằng code).
- **Cơ chế cho AI "chui vào":**
  + Có **Official tscircuit MCP Server** (`@tscircuit/mcp-server` hoặc CLI `tsci`).
  + AI không phải "vẽ chuột" mà AI viết code JSX:
    ```tsx
    <board width="40mm" height="30mm">
      <chip name="U1" footprint="soic8" />
      <resistor name="R1" resistance="10k" footprint="0603" />
      <trace from=".U1 > .pin1" to=".R1 > .pin1" />
    </board>
    ```
  + AI có thể tự tìm kiếm linh kiện trong Registry qua MCP (`tsci search`), tự tính toán đường mạch và tự sửa lỗi DRC.
- **Giao diện màn hình cho Sếp:**
  + Có Web Viewer trực tiếp trên trình duyệt: Xem được cả sơ đồ nguyên lý (Schematic), đường mạch PCB 2D, và render mô hình 3D xoay 360 độ cực kỳ trực quan.
  + Hỗ trợ xuất file Gerber tiêu chuẩn để gửi xưởng JLCPCB/PCBWay in mạch thật ngay lập tức.

---

### Top 2 (Web EDA Đầy Đủ Tính Năng): Flux.ai
- **Website:** https://flux.ai
- **Bản chất:** Nền tảng thiết kế EDA trên nền web đám mây (Cloud-based EDA) có tích hợp AI Copilot mạnh nhất hiện nay.
- **Cơ chế cho AI "chui vào":**
  + Có **Official Flux MCP Server** (`https://app.flux.ai/mcp`).
  + AI bên ngoài (Claude, Gemini, Cursor, Antigravity) có thể kết nối vào dự án Flux của Sếp, đọc danh sách linh kiện, netlist, và ra lệnh chỉnh sửa schematic/layout trực tiếp.
- **Giao diện màn hình cho Sếp:**
  + Giao diện web 100% cực đẹp, mô phỏng 3D PCB mượt mà, cộng tác thời gian thực (giống Figma cho phần cứng).
  + Sếp mở tab trình duyệt là thấy ngay AI đang thêm linh kiện, đi dây mạch.

---

### Top 3 (Chuẩn Công Nghiệp Mã Nguồn Mở): KiCad + KiCad MCP Server
- **Website:** https://kicad.org
- **Bản chất:** Phần mềm thiết kế mạch tiêu chuẩn công nghiệp phổ biến nhất thế giới cho kỹ sư phần cứng.
- **Cơ chế cho AI "chui vào":**
  + Cộng đồng và các hãng phần cứng lớn đã phát triển các MCP Server rất hoàn thiện:
    * **`Seeed-Studio/kicad-mcp-server`**: Do hãng Seeed Studio phát triển, hỗ trợ AI đọc sơ đồ nguyên lý, kiểm tra net, phân tích lỗi ERC/DRC.
    * **`lamaalrajih/kicad-mcp`**: Server MCP đa nền tảng (Windows/Linux/Mac) hỗ trợ Claude/Gemini.
    * **`mixelpixx/KiCAD-MCP-Server` & `Konnect`**: Native plugin viết bằng Rust cho KiCad.
  + Định dạng file KiCad (`.kicad_sch`, `.kicad_pcb`) là văn bản dạng S-Expression cực kỳ rõ ràng, AI đọc/ghi rất dễ dàng.
- **Giao diện màn hình cho Sếp:**
  + Chạy trực tiếp trên máy tính Sếp (Windows 11). Có công cụ 3D Viewer raytracing siêu nét, mở một cái là thấy toàn bộ bo mạch thật.
</specifications>

<evaluation_matrix>
# 3. BẢNG MA TRẬN SO SÁNH ĐÁNH GIÁ (COMPARISON MATRIX)

### Bảng 1: Giả lập vi điều khiển & phần cứng (Hardware Simulation)

| Tiêu Chí | Wokwi (Khuyên Dùng #1) | Antmicro Renode | Tinkercad Circuits |
| :--- | :--- | :--- | :--- |
| **Vi Điều Khiển Hỗ Trợ** | ESP32 (S2/S3/C3/C6), STM32, Arduino, RP2040 | STM32, ESP32, RISC-V, ARM | Chỉ có Arduino Uno cơ bản |
| **Mức Độ Sẵn Sàng MCP** | ⭐⭐⭐⭐⭐ (Official `wokwi-cli mcp`) | ⭐⭐⭐⭐ (PR stdio MCP server) | ❌ Không có |
| **Giao Diện Trực Quan (UI)** | ⭐⭐⭐⭐⭐ (Web / VS Code, có LED, OLED, Sensor thật) | ⭐⭐ (Chủ yếu là CLI, Log, Waveform) | ⭐⭐⭐⭐ (Kéo thả hoạt hình) |
| **Độ Dễ Cho AI Điều Khiển** | ⭐⭐⭐⭐⭐ (File `diagram.json` chuẩn cấu trúc) | ⭐⭐⭐ (Kịch bản `.resc` phức tạp) | ❌ Không hỗ trợ |
| **Mô Phỏng Mạng / WiFi** | Có (WiFi ảo, MQTT, HTTP) | Có (BLE, Zigbee, Multi-node) | ❌ Không |
| **Chi Phí** | Miễn phí (Bản Club cho tính năng nâng cao) | Hoàn toàn mã nguồn mở (Free) | Miễn phí |

---

### Bảng 2: Thiết kế bo mạch & vẽ PCB (PCB Design)

| Tiêu Chí | tscircuit (Khuyên Dùng cho AI) | Flux.ai (Cloud Web UI) | KiCad + MCP (Chuẩn Công Nghiệp) |
| :--- | :--- | :--- | :--- |
| **Môi Trường Hoạt Động** | Web + Local CLI (TypeScript/React) | 100% Web Browser | Ứng dụng Desktop Windows |
| **Hỗ Trợ MCP** | ⭐⭐⭐⭐⭐ (Official MCP Registry) | ⭐⭐⭐⭐⭐ (Official Flux MCP Server) | ⭐⭐⭐⭐ (Nhiều MCP mã nguồn mở uy tín) |
| **Màn Hình Trực Quan** | Web Viewer 2D & 3D sống động | Web Canvas 3D cực mượt | KiCad 3D Raytracing đẳng cấp |
| **Khả Năng AI Sinh Mạch** | ⭐⭐⭐⭐⭐ (Sinh code TSX cực chuẩn, 0 lỗi định dạng) | ⭐⭐⭐⭐ (AI tác động qua API/MCP đám mây) | ⭐⭐⭐⭐ (AI can thiệp file S-Expression / IPC) |
| **Sẵn Sàng Sản Xuất (Gerber)** | Có (Xuất Gerber, BOM, Pick&Place) | Có (Xuất Gerber trực tiếp) | Chuẩn quốc tế 100% (JLCPCB, PCBWay) |
| **Chi Phí** | Hoàn toàn miễn phí, Open-source | Miễn phí cơ bản (Bản Pro trả phí) | Hoàn toàn miễn phí, Open-source |
</evaluation_matrix>

<implementation_guide>
# 4. HƯỚNG DẪN CẤU HÌNH MCP ĐỂ AI "CHUI VÀO" LÀM VIỆC NGAY

### A. Cấu hình Wokwi MCP cho AI Agent
1. **Cài đặt Wokwi CLI:**
   ```powershell
   npm install -g wokwi-cli
   # Hoặc tải binary từ GitHub wokwi/wokwi-cli
   ```
2. **Lấy Token:** Đăng nhập vào https://wokwi.com, vào mục **CI** để lấy token bí mật `WOKWI_CLI_TOKEN`.
3. **Khai báo MCP Server trong cấu hình AI (Cursor / Claude Desktop / Antigravity):**
   ```json
   {
     "mcpServers": {
       "wokwi": {
         "command": "wokwi-cli",
         "args": ["mcp"],
         "env": {
           "WOKWI_CLI_TOKEN": "YOUR_WOKWI_CLI_TOKEN_HERE"
         }
       }
     }
   }
   ```
4. **Cách AI vận hành:**
   - AI tạo tệp `diagram.json` định nghĩa ESP32/STM32 và nối dây LED/màn hình OLED.
   - AI viết code `main.cpp` hoặc `main.py`.
   - AI gọi MCP chạy mô phỏng và đọc log Serial trả về. Sếp mở link trình duyệt hoặc VS Code để xem mô phỏng chạy bằng mắt!

---

### B. Cấu hình PCB với tscircuit MCP
1. **Cài đặt tscircuit:**
   ```powershell
   npm install -g tscircuit
   ```
2. **Khai báo MCP Server:**
   ```json
   {
     "mcpServers": {
       "tscircuit": {
         "command": "npx",
         "args": ["-y", "@tscircuit/mcp-server"]
       }
     }
   }
   ```
3. **Cách AI vận hành:**
   - AI dùng tool MCP để tìm linh kiện và tạo file mạch `MyBoard.tsx`.
   - AI chạy lệnh `tsci dev` hoặc mở web tscircuit để Sếp xem bản 3D của bo mạch đang được thiết kế.

---

### C. Cấu hình KiCad MCP (Giải pháp làm đồ án thực tế in mạch)
1. **Cài đặt KiCad 8 hoặc 9** trên Windows 11.
2. **Cài đặt KiCad MCP Server (từ Seeed Studio hoặc lamaalrajih):**
   ```powershell
   git clone https://github.com/Seeed-Studio/kicad-mcp-server.git
   cd kicad-mcp-server
   npm install
   npm run build
   ```
3. **Khai báo MCP Server:**
   ```json
   {
     "mcpServers": {
       "kicad": {
         "command": "node",
         "args": ["C:/path/to/kicad-mcp-server/dist/index.js"],
         "env": {
           "KICAD_CLI_PATH": "C:/Program Files/KiCad/8.0/bin/kicad-cli.exe"
         }
       }
     }
   }
   ```
</implementation_guide>

<recommendation>
# 5. ĐÁNH GIÁ VÀ LỜI KHUYÊN DÀNH RIÊNG CHO ĐỒ ÁN TỐT NGHIỆP CỦA SẾP

1. **Về Giả lập Vi Điều Khiển (ESP32, STM32, Arduino):**
   - **Lựa chọn duy nhất hoàn hảo:** **Wokwi**.
   - Không có nền tảng nào vượt qua Wokwi ở thời điểm hiện tại về: độ mượt trên web, giao diện sinh động (Sếp nhìn thấy cảm biến, còi kêu, màn hình hiển thị số liệu như thật), và khả năng tự động hóa qua `wokwi-cli mcp`.

2. **Về Thiết Kế Vẽ Mạch PCB:**
   - **Nếu Sếp muốn AI vẽ cực nhanh, vừa gõ prompt là có mạch 3D xem ngay trên web:** Chọn **tscircuit** hoặc **Flux.ai**. Hai con này sinh ra cho kỷ nguyên AI, giao diện web cực kỳ hiện đại.
   - **Nếu Đồ án tốt nghiệp yêu cầu nộp file đồ án chuẩn kỹ thuật và mang đi in mạch gia công thật:** Chọn **KiCad + KiCad MCP Server**. KiCad là chuẩn công nghiệp tại các trường đại học và viện nghiên cứu, giáo viên chấm điểm sẽ chấm trên KiCad hoặc file Gerber xuất từ KiCad.
</recommendation>
