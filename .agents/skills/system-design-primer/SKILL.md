---
name: system-design-primer
description: Chuẩn kiến trúc System Design Primer (300k+ stars GitHub) dành riêng cho Đồ án Tốt nghiệp Smart Home Voice AI. Sử dụng khi phân tích, thiết kế kiến trúc hệ thống (Backend, IoT, MQTT Pub/Sub, Caching, CAP Theorem) hoặc viết báo cáo đồ án.
---

# 🏗️ SKILL (WORKSPACE-ONLY): System Design Primer (`system-design-primer`)

> **Phạm vi:** Chỉ áp dụng trong thư mục dự án `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp` (nằm tại `.agents/skills/system-design-primer/SKILL.md`).

Tài liệu gốc đã được tải sẵn tại thư mục dự án:
- **Bản đầy đủ (`README.md`):** [`docs/tai_lieu_tham_khao/system-design-primer/README.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/docs/tai_lieu_tham_khao/system-design-primer/README.md)
- **Bản áp dụng trực tiếp vào đồ án:** [`kenh_do_an_thay_duyet/01_SYSTEM_DESIGN_PRIMER_TRONG_DO_AN.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/kenh_do_an_thay_duyet/01_SYSTEM_DESIGN_PRIMER_TRONG_DO_AN.md)

---

## QUY TRÌNH 4 BƯỚC THIẾT KẾ HỆ THỐNG CHUẨN (4-STEP SYSTEM DESIGN METHODOLOGY)

1. **Bước 1 — Xác định Use Cases, Ràng buộc và Giả định:**
   - Phân tầng người dùng: Tầng 1 Admin (Nguyễn Tuấn Anh), Tầng 2 Thành viên, Tầng 3 Khách.
   - Ràng buộc hiệu năng: $< 50\text{ ms}$ cho điều khiển cục bộ/MQTT, $< 500\text{ ms}$ cho AI Voice.
2. **Bước 2 — Thiết kế Kiến trúc Mức cao (4 Tầng):**
   - Client/Edge (`Web 3D`, `Mobile App /app`, `NodeMCU ESP8266`) $\leftrightarrow$ Gateway (`WebSocket`, `REST API`, `MQTT Broker 9 Topics`) $\leftrightarrow$ Core Engine (`Voice DSP`, `Rule Engine 2 Bể`, `Gemini 3.8 Live + Vector RAG`) $\leftrightarrow$ Storage (`In-Memory Cache + Write-Through JSON + ESP8266 LittleFS`).
3. **Bước 3 — Thiết kế Chi tiết Thành phần Cốt lõi:**
   - **CAP Theorem (AP Failover):** Đồng bộ bản sao 2 Bể qua `smarthome/sync/pools` (`Retain=True`) xuống Flash `LittleFS` của ESP8266.
   - **Write-Through Cache:** Lưu mã sóng Remote IR 38kHz (`VS1838B` chân `D5` $\rightarrow$ `IR LED` chân `D2`) vào RAM và `simulator/data/ir_devices_db.json`.
   - **Asynchronism & Back Pressure:** Hàng đợi `asyncio.Queue(maxsize=256)` trong `simulator/mqtt_bridge.py`.
4. **Bước 4 — Loại bỏ Điểm nghẽn (SPOF):**
   - Mạch `NodeMCU ESP8266` chạy nguồn độc lập 5V, tự kết nối lại Wi-Fi/MQTT và tự chạy hẹn giờ/luật IF-ELSE khi tắt Server.
