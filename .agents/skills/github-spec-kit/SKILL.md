---
name: github-spec-kit
description: Quy trình Phát triển Hướng Đặc tả (Spec-Driven Development - GitHub Spec Kit 145k+ stars) kết hợp Chia Nhóm Subagent Team chống sửa chồng chéo (constitution -> specify -> clarify -> plan -> checklist -> tasks -> analyze -> implement -> converge).
---

# 🚀 GitHub Spec Kit (`github/spec-kit`) + Subagent Team Orchestration

Skill này tích hợp bộ công cụ chính thức **`github/spec-kit`** (đã cài tại [`.specify/`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/.specify)) cùng **Hiến pháp Hệ thống** ([`.specify/memory/constitution.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/.specify/memory/constitution.md)) và cơ chế **Chia Việc Theo Nhóm (Subagent Team / Fan-Out & Fan-In)** để chấm dứt hoàn toàn tình trạng *"sửa chỗ này hỏng chỗ kia do code chồng chéo"*.

---

## 1. Quy Trình 9 Lệnh Chuẩn Của GitHub Spec Kit
1. **`constitution`** ([`.specify/memory/constitution.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/.specify/memory/constitution.md)): Đọc 6 Điều bất biến của hệ thống trước khi chạm vào bất kỳ dòng code nào.
2. **`specify`** ([`specs/001-smart-home-voice-ai/spec.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/specs/001-smart-home-voice-ai/spec.md)): Xác định rõ hành vi người dùng mong muốn (What & Why).
3. **`clarify`**: Kiểm tra điểm mơ hồ trước khi lập kế hoạch.
4. **`plan`** ([`specs/001-smart-home-voice-ai/plan.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/specs/001-smart-home-voice-ai/plan.md)): Khoanh vùng đúng **Slice (A / B / C / D)** cần sửa, cấm sửa lan sang Slice khác nếu không đổi Contract.
5. **`checklist`** ([`specs/001-smart-home-voice-ai/checklist.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/specs/001-smart-home-voice-ai/checklist.md)): Tiêu chí nghiệm thu từng điều khoản.
6. **`tasks`** ([`specs/001-smart-home-voice-ai/tasks.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/specs/001-smart-home-voice-ai/tasks.md)): Chia nhỏ đầu việc theo thứ tự phụ thuộc.
7. **`analyze`**: Kiểm tra xung đột giữa Spec, Plan và các file liên quan.
8. **`implement`**: Thực thi code (trực tiếp nếu chỉ chạm 1 Slice, hoặc chia Subagent Team nếu chạm $\ge 2$ Slices).
9. **`converge`**: Chạy `python -X utf8 scripts/speckit_converge.py` và `scripts/test_simulator_e2e.py` để đối chiếu toàn bộ code với Hiến pháp.

---

## 2. Khi Nào Cần Chạy Lệnh Team (Subagent Team / `/teamwork`)?
- **Sửa nhỏ trong 1 Slice duy nhất** (ví dụ chỉ chỉnh câu chữ UI hoặc chỉnh 1 ngưỡng trong `voice_auth.py`): Agent chính sửa trực tiếp + chạy `speckit_converge.py` ngay (nhanh gọn trong 30 giây).
- **Sửa lớn hoặc tính năng liên tầng chạm từ 2–4 Slices trở lên** (ví dụ vừa sửa DSP giọng nói `Slice A`, vừa sửa WebSocket `Slice B`, vừa sửa phân quyền `Slice C` và giao diện `Slice D`):
  - Khởi chạy **Subagent Team (`invoke_subagent` với `Model: "inherit"`)** hoặc dùng lệnh `/teamwork`, chia việc độc lập theo 4 Slice trong [`plan.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/specs/001-smart-home-voice-ai/plan.md):
    - **Agent 1 (`Slice A`):** Chỉ phụ trách `simulator/voice_auth.py` & `voiceprints.json`.
    - **Agent 2 (`Slice B`):** Chỉ phụ trách `simulator/server.py` (Gemini Live & WebSocket).
    - **Agent 3 (`Slice C`):** Chỉ phụ trách `simulator/rule_engine.py`, `auth_system.py`, `database.py`.
    - **Agent 4 (`Slice D & Converge QA`):** Chỉ phụ trách `simulator/static/*` và chạy `python -X utf8 scripts/speckit_converge.py` để kiểm tra không ai làm gãy Hiến pháp của người kia.
