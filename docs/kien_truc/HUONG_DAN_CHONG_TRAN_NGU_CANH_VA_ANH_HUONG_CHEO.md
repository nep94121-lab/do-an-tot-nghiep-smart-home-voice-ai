# 🛡️ HỆ THỐNG CHỐNG TRÀN NGỮ CẢNH & CHỐNG LỖI DÂY CHUYỀN ("SỬA CÁI NÀY HỎNG CÁI KIA")

> **Mục đích:** Khi dự án phình to hàng chục nghìn dòng code với nhiều tầng liên kết chặt chẽ (`Web 3D` $\leftrightarrow$ `Mobile App` $\leftrightarrow$ `Server / Rule Engine / Gemini 3.8 Live / MQTT` $\leftrightarrow$ `Firmware C++ ESP8266`), tài liệu này quy định rõ **Công cụ nằm Ở ĐÂU** và **KHI NÀO BẮT BUỘC PHẢI DÙNG** để AI không bao giờ bị tràn Context Window hoặc sửa hàm A làm hỏng ngầm hàm B.

---

## PHẦN 1: BẢNG TỔNG HỢP "Ở ĐÂU" & "KHI NÀO CẦN DÙNG" (5 THỜI ĐIỂM VÀNG)

| STT | KHI NÀO CẦN DÙNG (Tình huống thực tế) | DÙNG CÁI GÌ & Ở ĐÂU (File / Repo / Lệnh) | TÁC DỤNG THỰC TẾ |
| :---: | :--- | :--- | :--- |
| **1** | **TRƯỚC KHI AI ĐỌC CODE**<br>*(Khi bắt đầu tìm hiểu hoặc định vị 1 tính năng trong các file dài như `rule_engine.py` 2.858 dòng hay `server.py` 1.671 dòng)* | 📄 Đọc file bản đồ:<br>[`docs/kien_truc/REPO_MAP.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/docs/kien_truc/REPO_MAP.md)<br>*(Áp dụng kỹ thuật **Aider RepoMap + PageRank**)* | - Giúp AI biết chính xác **hàm nào nằm ở dòng `#Lstart-Lend` nào**.<br>- Chỉ đọc đúng 50–100 dòng của hàm đó thay vì đọc cả file 2.858 dòng $\rightarrow$ **Tiết kiệm 90% cửa sổ ngữ cảnh (Context Window)**. |
| **2** | **TRƯỚC KHI SỬA BẤT KỲ HÀM, TOPIC MQTT HAY API NÀO**<br>*(Khi bạn bảo: "Sửa cho tôi tính năng X", "Đổi cách chạy của hàm Y")* | ⚡ Chạy lệnh phân tích bán kính ảnh hưởng:<br>`python -X utf8 scripts/code_graph_guard.py --impact <tên_hàm>`<br>*(Kỹ thuật Call-Graph của [`oraios/serena`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/docs/tai_lieu_tham_khao/serena) & [`CODEBASE_GRAPH.json`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/docs/kien_truc/CODEBASE_GRAPH.json))* | - Liệt kê **100% những nơi đang gọi hàm này (`Callers`)** và **những hàm con mà nó gọi (`Callees`)**.<br>- Cảnh báo ngay nếu hàm đó nằm trong **Top 15 Hàm Tâm Chấn** để không làm gãy các tính năng khác. |
| **3** | **NGAY SAU KHI SỬA CODE XONG**<br>*(Trước khi báo cáo hoàn thành hoặc đẩy code lên GitHub)* | 🛡️ Chạy bộ đôi lệnh khóa hợp đồng:<br>1. `python -X utf8 scripts/code_graph_guard.py --verify`<br>2. `python -X utf8 scripts/test_simulator_e2e.py` | - Kiểm tra **5 Cổng Đồng Bộ Liên Tầng** (19 Gemini Tools, 9 MQTT Topics, 8 REST APIs, 6 chân GPIO ESP8266, WebSocket Events).<br>- Chạy kiểm thử tự động toàn bộ tính năng cũ + mới (`Exit Code: 0`). |
| **4** | **KHI THIẾT KẾ TÍNH NĂNG MỚI HOẶC MỞ RỘNG KIẾN TRÚC**<br>*(Khi thêm phần cứng mới, cảm biến mới, hàng đợi, cache hoặc viết báo cáo đồ án)* | 📚 Tham chiếu:<br>- Kho [`docs/tai_lieu_tham_khao/system-design-primer`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/docs/tai_lieu_tham_khao/system-design-primer)<br>- Tài liệu [`01_SYSTEM_DESIGN_PRIMER_TRONG_DO_AN.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/kenh_do_an_thay_duyet/01_SYSTEM_DESIGN_PRIMER_TRONG_DO_AN.md) | - Đảm bảo mọi tính năng mới tuân thủ đúng chuẩn **Message Queue (Backpressure)**, **Write-Through Cache**, và **CAP Theorem (AP Failover tại biên ESP8266)**. |
| **5** | **KHI PHIÊN CHAT QUÁ DÀI HOẶC SANG CUỘC TRÒ CHUYỆN MỚI**<br>*(Khi thấy phiên làm việc đã kéo dài nhiều ngày hoặc muốn nén toàn bộ dự án cho AI khác đọc)* | 📦 Dùng 1 trong 2 cách:<br>- Gõ lệnh `/compact` trên khung chat.<br>- Hoặc đóng gói bằng [`docs/tai_lieu_tham_khao/repomix`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/docs/tai_lieu_tham_khao/repomix) (`npx repomix --ignore "docs/tai_lieu_tham_khao/**,.env"`) | - Nén gọn ngữ cảnh lịch sử mà vẫn giữ nguyên 100% cấu trúc qua [`REPO_MAP.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/docs/kien_truc/REPO_MAP.md) và [`CODEBASE_GRAPH.json`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/docs/kien_truc/CODEBASE_GRAPH.json). |

---

## PHẦN 2: CHI TIẾT VỊ TRÍ CÁC KHO VÀ CÔNG CỤ ĐÃ CÀI ĐẶT TRONG MÁY

### 1. Các Kho Mã Nguồn Mở Uy Tín Đã Tải Về (`docs/tai_lieu_tham_khao/`)
*(Đã cấu hình trong [`.gitignore`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/.gitignore) để lưu trên máy phục vụ tra cứu mà không làm nặng GitHub của đồ án)*:
1. **[`docs/tai_lieu_tham_khao/system-design-primer/`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/docs/tai_lieu_tham_khao/system-design-primer)** (`donnemartin/system-design-primer` — 300.000+ ⭐):
   - Dùng khi: Thiết kế kiến trúc Backend, IoT MQTT Queue, Caching, Database, CAP Theorem và viết luận văn Chương 1–2–3.
2. **[`docs/tai_lieu_tham_khao/serena/`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/docs/tai_lieu_tham_khao/serena)** (`oraios/serena` — 10.000+ ⭐):
   - Dùng khi: Tham chiếu kiến trúc Semantic Symbol Navigation & Call-Graph cho AI Agent.
3. **[`docs/tai_lieu_tham_khao/repomix/`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/docs/tai_lieu_tham_khao/repomix)** (`yamadashy/repomix` — 15.000+ ⭐):
   - Dùng khi: Cần đóng gói toàn bộ mã nguồn dự án thành 1 file XML/Markdown duy nhất để kiểm định chéo (Cross-AI Audit).

### 2. Bộ Công Cụ Thực Thi Trực Tiếp Của Đồ Án (`scripts/` & `docs/kien_truc/`)
1. **Trình Phân tích Đồ thị AST & Kiểm định Liên tầng:** [`scripts/code_graph_guard.py`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/scripts/code_graph_guard.py)
   - Lệnh 1 — Cập nhật Bản đồ & Kiểm định 5 Cổng:
     ```powershell
     python -X utf8 scripts/code_graph_guard.py
     ```
   - Lệnh 2 — Kiểm tra "Sửa hàm X thì ảnh hưởng những đâu?":
     ```powershell
     python -X utf8 scripts/code_graph_guard.py --impact execute_device_action
     python -X utf8 scripts/code_graph_guard.py --impact get_snapshot
     python -X utf8 scripts/code_graph_guard.py --impact smarthome/cmd/actuate
     ```
2. **Bản đồ Khung xương Tinh gọn cho AI (`RepoMap`):** [`docs/kien_truc/REPO_MAP.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/docs/kien_truc/REPO_MAP.md)
   - Liệt kê **Top 15 Hàm Tâm Chấn (High Blast-Radius)** và chỉ mục `#Lstart-Lend` của toàn bộ 127 Class/Hàm trong dự án.
3. **Đồ thị Quan hệ Mã nguồn Chi tiết (JSON):** [`docs/kien_truc/CODEBASE_GRAPH.json`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/docs/kien_truc/CODEBASE_GRAPH.json)
   - Lưu toàn bộ mạng lưới `callers` $\leftrightarrow$ `callees`, điểm `pagerank`, `blast_score` và hợp đồng 4 tầng.
4. **Skill Tự động kích hoạt cho AI Agent:** [`C:\Users\LENOVO\.gemini\config\skills\codebase-context-guard\SKILL.md`](file:///C:/Users/LENOVO/.gemini/config/skills/codebase-context-guard/SKILL.md)
   - Đảm bảo AI tự động tuân thủ quy trình 3 bước (**Đọc `REPO_MAP.md` $\rightarrow$ Chạy `--impact` trước khi sửa $\rightarrow$ Chạy `--verify` + `test_simulator_e2e.py` sau khi sửa**) mà người dùng không cần nhắc lại.
