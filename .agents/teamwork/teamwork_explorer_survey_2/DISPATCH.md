## 2026-11-04T19:14:51Z
You are teamwork_explorer_survey_2.
Your working directory is: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\teamwork_explorer_survey_2\
Project root: C:\Users\LENOVO\Desktop\đồ án tốt nghiệp

MANDATORY FIRST STEP:
Read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\ORIGINAL_REQUEST.md
Also read C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\REAL_TEST_BUGS_20261105.md

Your mission in this Survey phase is to investigate and analyze the authoritative codebase for the following subset of bugs:
- Bug 3: WebSocket trên Vercel production lỗi (`wss://.../ws`); dashboard hiện banner "Mất kết nối thời gian thực" trong khi header ghi "Đã kết nối". Vercel serverless không giữ WebSocket → thêm fallback tự động sang HTTP polling /api/state; khi polling hoạt động không hiện banner đỏ/vàng. Banner và trạng thái header phải nhất quán, đúng sự thật. Sửa resource 404 trong console.
- Bug 10: Bật/tắt đèn chậm; trong lúc cập nhật nhãn bị trống và phụ đề bị cắt thành "Đã bột". Dùng optimistic UI, không nhãn trống, chữ đầy đủ ("Đã bật").
- Bug 11: Sheet ghi âm hiện "Đang thu âm" khi popup xin quyền mic còn chờ. Phải có trạng thái "đang chờ quyền mic", chỉ chạy timer/waveform sau khi được cấp quyền; bị từ chối thì hiện modal quyền mic.
- Bug 14: /wokwi: nhãn mạch bị cắt/chồng (vd "Cảm biến DHT11 (Chân D…"), trang hiện "Chưa có dữ liệu". Sửa layout nhãn và hiển thị dữ liệu mô phỏng.

Scope of investigation:
1. Examine code locations in frontend JS/HTML/CSS (WebSocket connection logic, reconnect banner, header connection pill, polling fallback mechanism, device toggle handler & optimistic update, audio recording sheet & navigator.mediaDevices.getUserMedia permission flow, wokwi simulation view & CSS/SVG/canvas layout) and backend endpoints (/api/state, simulation data endpoints).
2. Trace exact root causes with file paths, functions, and line numbers.
3. Formulate precise TDD reproduction test strategies (how to write automated pytest or Playwright tests that fail BEFORE fix and pass AFTER fix).
4. Verify all constraints: maintain all 68 DOM IDs, window hooks, re-exports, zero secrets/passwords logged, UTF-8 LF without BOM (0 CRLF).
5. Write your comprehensive survey report to C:\Users\LENOVO\Desktop\đồ án tốt nghiệp\.agents\teamwork\teamwork_explorer_survey_2\handoff.md.
6. When done, send a message to caller with a brief summary of findings and the path to handoff.md.
