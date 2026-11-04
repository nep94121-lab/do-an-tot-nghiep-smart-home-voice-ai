# 🛡️ QUY TẮC RIÊNG CỦA DỰ ÁN: ĐỒ ÁN TỐT NGHIỆP SMART HOME VOICE AI (PROJECT-ONLY WORKSPACE RULE)

> **Phạm vi hiệu lực:** Rule này nằm tại [`.agents/rules/smart-home-do-an.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/.agents/rules/smart-home-do-an.md), **chỉ áp dụng riêng cho dự án `c:\Users\LENOVO\Desktop\đồ án tốt nghiệp`** (tuyệt đối không ghi vào Global Rules của Antigravity). Mỗi khi có yêu cầu sửa lỗi hoặc phát triển tính năng mới trong dự án này, Agent bắt buộc lôi Rule này và bộ [`.specify/`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/.specify/memory/constitution.md) ra thực thi.

---

## 1. Quy Trình 9 Bước GitHub Spec Kit Chống Sửa Chắp Vá & Chồng Chéo
Mọi yêu cầu sửa đổi hoặc nâng cấp sản phẩm phải đi theo lộ trình chuẩn Spec-Driven Development (`github/spec-kit`):
1. **`constitution`** ([`.specify/memory/constitution.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/.specify/memory/constitution.md)): Kiểm tra 6 Điều bất biến của sản phẩm để biết những chức năng nào tuyệt đối không được làm hỏng.
2. **`specify` & `clarify`** ([`specs/001-smart-home-voice-ai/spec.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/specs/001-smart-home-voice-ai/spec.md)): Xác định rõ đầu vào, đầu ra, câu thoại và hành vi kỳ vọng.
3. **`plan`, `checklist` & `tasks`** ([`specs/001-smart-home-voice-ai/plan.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/specs/001-smart-home-voice-ai/plan.md)): Khoanh vùng chính xác phân hệ (**Slice A / B / C / D**) và lập danh sách đầu việc chi tiết trước khi chạm vào code.
4. **`analyze`**: Chạy `python -X utf8 scripts/code_graph_guard.py --impact <tên_hàm_hoặc_api>` để kiểm tra bán kính ảnh hưởng chéo.
5. **`implement` & `converge`**: Sửa code đúng ranh giới Slice và chạy kiểm toán hội tụ `python -X utf8 scripts/speckit_converge.py`.

---

## 2. Ma Trận Đánh Giá Khi Nào Cần Dùng Lệnh Team (`Subagent Team` / `/teamwork`)
Trước khi bắt tay vào sửa, Agent phải đánh giá độ phức tạp theo 4 phân hệ (**Slice A..D**) trong [`plan.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/specs/001-smart-home-voice-ai/plan.md):

| Quy mô thay đổi | Dấu hiệu nhận biết | Quyết định điều phối |
| :--- | :--- | :--- |
| **Mức 1 — Đơn Tầng (1 Slice)** | Chỉ sửa trong 1 file hoặc 1 phân hệ độc lập (ví dụ: chỉnh ngưỡng DSP trong `voice_auth.py` hoặc chỉnh giao diện trong `static/app.js`, không đổi API/WebSocket contract). | **Không cần chạy Team.** Agent chính sửa trực tiếp + chạy bộ tự test ngay để đạt tốc độ nhanh nhất. |
| **Mức 2 — Liên Tầng ($\ge 2$ Slices)** | Thay đổi chạm từ 2 phân hệ trở lên (ví dụ: vừa sửa DSP giọng nói `Slice A`, vừa sửa cầu nối Gemini Live `Slice B`, vừa sửa phân quyền/OAuth `Slice C` và giao diện `Slice D`). | **Bắt buộc chia việc theo Subagent Team (`invoke_subagent` với `Model: "inherit"`)** hoặc dùng `/teamwork`:<br>• **Subagent 1 (`Slice A`):** `simulator/voice_auth.py`<br>• **Subagent 2 (`Slice B`):** `simulator/server.py` & `mqtt_bridge.py`<br>• **Subagent 3 (`SliceC`):** `simulator/rule_engine.py`, `auth_3layer.py`, `database_sqlite.py`<br>• **Subagent 4 (`Slice D & QA`):** `simulator/static/*` & kiểm định hội tụ. |

---

## 3. Cổng Tự Kiểm Thử Bắt Buộc Trước Khi Báo Cáo ("Chưa Tự Test Xong Cấm Báo Là Xong")
Nghiêm cấm báo cáo "đã xong" chỉ dựa trên suy đoán sau khi sửa code. Trước khi trả lời người dùng, Agent **bắt buộc phải tự chạy đủ 5 cổng kiểm thử thực tế (Exit Code = 0)**:
```powershell
# 1. Kiểm toán hội tụ 9 bước GitHub Spec Kit & 6 Điều Hiến pháp
python -X utf8 scripts/speckit_converge.py

# 2. Kiểm định đồng bộ liên tầng (Tools, MQTT, HTTP API, 8 Chân GPIO, WebSocket)
python -X utf8 scripts/code_graph_guard.py --verify

# 3. Kiểm thử 14 kịch bản Xác thực 3 Lớp, Link Mời Phân Cấp, OAuth Gmail OTP & Thu âm
python -X utf8 scripts/test_auth_3layer_and_invite.py

# 4. Kiểm thử toàn trình E2E (Thiết bị, Hẹn giờ AM/PM, Luật IF-ELSE, 2 Giọng nói, Offline 16.4ms, SQLite 3NF)
python -X utf8 scripts/test_simulator_e2e.py

# 5. Đóng gói & Xuất biên lai phát hành chuẩn thương mại (5-Gate DevOps Pipeline)
python -X utf8 scripts/devops_pipeline.py --package
```
