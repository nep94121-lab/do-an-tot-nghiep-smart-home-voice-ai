# 🛡️ QUY TẮC RIÊNG CỦA DỰ ÁN: ĐỒ ÁN TỐT NGHIỆP SMART HOME VOICE AI (WORKSPACE RULE)

> **Phạm vi:** Rule này nằm tại `.agents/rules/smart-home-do-an.md`, **chỉ có hiệu lực bên trong thư mục dự án `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp`** và không ảnh hưởng tới các dự án khác trên Antigravity.

## 1. Quy Trình 3 Bước Chống Tràn Ngữ Cảnh & Chống "Sửa A Hỏng B"
1. **Trước khi đọc code (`read_file`):**
   - Tra cứu [`docs/kien_truc/REPO_MAP.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/docs/kien_truc/REPO_MAP.md) để lấy chính xác dòng `#Lstart-Lend` của hàm cần xem. Không đọc toàn bộ file dài hàng nghìn dòng.
2. **Trước khi sửa bất kỳ hàm, MQTT Topic hoặc API nào (`edit_file`):**
   - Chạy lệnh kiểm tra bán kính ảnh hưởng:
     ```powershell
     python -X utf8 scripts/code_graph_guard.py --impact <tên_hàm_hoặc_topic_hoặc_api>
     ```
   - Kiểm tra toàn bộ `Callers` và `Callees` để đảm bảo không làm gãy tính năng liên đới ở 4 tầng (`Web 3D`, `Mobile App`, `Server/Engine/MQTT`, `Firmware ESP8266`).
3. **Ngay sau khi sửa code xong:**
   - Bắt buộc chạy bộ đôi lệnh kiểm định liên tầng và kiểm thử E2E (đạt `Exit Code: 0`):
     ```powershell
     python -X utf8 scripts/code_graph_guard.py --verify
     python -X utf8 scripts/test_simulator_e2e.py
     ```

## 2. Bảo Toàn Hợp Đồng Hệ Thống Cốt Lõi
- **6 chân phần cứng NodeMCU ESP8266:** `D1` (Cửa chính), `D2` (Đèn khách & Phát IR 38kHz), `D5` (Thu IR `VS1838B` 38kHz), `D6` (Cảm biến `DHT11` & Quạt), `D7` (Đèn ngủ), `D8` (Còi báo động).
- **2 Bể độc lập & Phân quyền 3 Tầng:** Tầng 1 (`Nguyễn Tuấn Anh` - Admin tối cao), Tầng 2 (Thành viên - cô lập bể riêng), Tầng 3 (Khách - chỉ điều khiển cơ bản).
- **Không lưu Skill/Rule của đồ án ra ngoài Global (`~/.gemini/config/`):** Mọi Skill và Rule của đồ án đều đặt trong `.agents/skills/` và `.agents/rules/` ngay tại thư mục dự án này.
