---
name: codebase-context-guard
description: Hệ thống Quản trị Ngữ cảnh (RepoMap PageRank) và Phân tích Bán kính Ảnh hưởng Chéo (AST Call-Graph & Blast-Radius Guard từ Serena/Aider/Repomix) dành riêng cho Đồ án Tốt nghiệp Smart Home Voice AI.
---

# 🛡️ SKILL (WORKSPACE-ONLY): QUẢN TRỊ NGỮ CẢNH & CHỐNG LỖI DÂY CHUYỀN (`codebase-context-guard`)

> **Phạm vi:** Chỉ áp dụng trong thư mục dự án `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp` (nằm tại `.agents/skills/codebase-context-guard/SKILL.md`).

Skill này kết hợp 3 kiến trúc tốt nhất thế giới cho AI Coding Agent trên dự án lớn:
1. **Aider RepoMap (`PageRank` + `#Lstart-Lend` Symbol Index):** Đọc bản đồ khung xương trước, chỉ đọc đúng dòng của hàm cần sửa (tiết kiệm 90% Context Window).
2. **Serena / Codebase-Memory (`AST Call-Graph` & `Blast-Radius Impact`):** Kiểm tra toàn bộ `Callers` (ai gọi hàm này) và `Callees` (hàm này gọi ai) trước khi sửa.
3. **Cross-Layer Contract Verification:** Tự động đối chiếu sự đồng bộ giữa Frontend (Web 3D / Mobile App) $\leftrightarrow$ Backend (Server / Rule Engine / MQTT) $\leftrightarrow$ Firmware C++ (`ESP8266`).

---

## 🧭 KHI NÀO CẦN DÙNG & DÙNG Ở ĐÂU (QUY TRÌNH 3 BƯỚC BẮT BUỘC)

### Bước 1 — TRƯỚC KHI ĐỌC CODE (Chống tràn cửa sổ ngữ cảnh)
- **Khi nào dùng:** Ngay khi bắt đầu tìm hiểu hoặc định vị 1 tính năng trong dự án.
- **Ở đâu:** Đọc file [`docs/kien_truc/REPO_MAP.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/docs/kien_truc/REPO_MAP.md).
- **Quy tắc:** Lấy chính xác `StartLine` và `EndLine` từ `REPO_MAP.md` rồi mới gọi `read_file(Path=..., StartLine=..., EndLine=...)`. **Tuyệt đối không** đọc tràn lan cả file dài hàng nghìn dòng.

### Bước 2 — TRƯỚC KHI SỬA BẤT KỲ HÀM, TOPIC MQTT HOẶC API NÀO (Chống "Sửa A hỏng B")
- **Khi nào dùng:** Trước khi dùng `edit_file` sửa bất kỳ hàm, biến trạng thái, MQTT topic hoặc REST/WebSocket API nào.
- **Ở đâu / Lệnh chạy:**
  ```powershell
  python -X utf8 scripts/code_graph_guard.py --impact <tên_hàm_hoặc_topic_hoặc_api>
  ```
- **Quy tắc:** Kiểm tra danh sách `Callers` (những nơi gọi hàm này) và các tầng liên quan (`Web 3D`, `Mobile App`, `ESP8266 Firmware`) để đảm bảo thay đổi tương thích 100% với mọi nơi đang gọi nó.

### Bước 3 — NGAY SAU KHI SỬA CODE XONG (Khóa Hợp Đồng 5 Cổng & Kiểm thử Hồi quy)
- **Khi nào dùng:** Sau mỗi lần sửa code và trước khi báo cáo kết quả cho người dùng.
- **Ở đâu / Lệnh chạy:**
  ```powershell
  python -X utf8 scripts/code_graph_guard.py --verify
  python -X utf8 scripts/test_simulator_e2e.py
  ```
- **Quy tắc:** Cả 2 lệnh bắt buộc phải đạt `Exit Code: 0` (100% PASS cả 5 cổng liên tầng và toàn bộ kịch bản E2E).
