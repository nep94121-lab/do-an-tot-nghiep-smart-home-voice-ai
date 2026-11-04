## 2026-11-04T12:24:39Z
Chia việc theo nhóm: (a) web error pages + sw.js, (b) banner/modal bảo mật + mic + WS, (c) mobile /app 5 màn, (d) Android Compose, (e) QA agent test luồng thật như người dùng cho cả 3 vai (Chủ nhà/Gia đình/Khách) + pytest, (f) review agent kiểm tra khớp DESIGN_NEW_PAGES.md.
Triển khai PHASE 2: hiện thực hóa chính xác toàn bộ các trang và màn hình theo đúng thiết kế Codex trong ui_mockups/v2_new_pages/DESIGN_NEW_PAGES.md, KHÔNG thiết kế lại, bảo đảm toàn bộ hệ thống web, mobile và kiểm thử hoạt động đồng bộ.

Integrity mode: development

Reference material:
- ui_mockups/v2_new_pages/DESIGN_NEW_PAGES.md
- Các HTML mockup np_*.html trong ui_mockups/v2_new_pages/
- FIX_PLAN_20261104.md (Phase 2 + Nhóm 1–3 + Phần 2 mobile)
- DESIGN_SYSTEM.md / REVISION_2.md

## Requirements
### R1. Triển khai các trang lỗi Web và Service Worker
- Hiện thực chính xác offline + sw.js, trang 404, 500/503, QR expired, 403 theo đúng mockup np_*.html và đặc tả DESIGN_NEW_PAGES.md.
- Không tự sáng tạo layout/icon khác spec. Giữ nguyên cấu trúc house3d.js / Toàn cảnh.
- FastAPI 404 handler chỉ trả HTML cho điều hướng trình duyệt, giữ nguyên JSON 404 cho /api/*.

### R2. Banner và Modal Bảo Mật, Quyền Mic và WebSocket Reconnect
- Triển khai lockdown modal, quyền microphone, và banner WebSocket reconnect theo đúng spec.
- Bảo toàn các DOM IDs và window.* hooks hiện có trong mobile_app/index.html, simulator/static/index.html, simulator/static/guest_enroll.html, simulator/static/auth.html để không làm gãy các bài test E2E/Challenger.

### R3. Triển khai 5 màn Mobile Part 2 và Android Scope
- Triển khai chính xác 5 màn hình mobile /app theo đúng Phần 2 của DESIGN_NEW_PAGES.md.
- Ưu tiên hoàn thiện toàn bộ trên Web và Mobile Web (`mobile_app/` / `/app`); chỉ chỉnh sửa Android Compose nếu có phần liên quan trực tiếp và đảm bảo assembleDebug PASS nếu đụng tới.

### R4. Bảo Mật và Dữ Liệu Nhạy Cảm
- Không ghi mật khẩu, secret, OTP vào bất kỳ file hoặc log nào mới.
- Không tự login Gmail; dùng tài khoản test Chủ nhà nep94121@gmail.com với mật khẩu mặc định có sẵn trong seed/code dự án.
- Sử dụng các tài khoản mẫu có sẵn trong database seed / fixtures test của dự án cho vai Gia đình và Khách (kèm luồng QR handshake cho Khách).

### R5. Kiểm Thử, Bàn Giao và Triển Khai
- Test luồng thật trên http://localhost:8088 cho các trang mới với đủ 3 vai (Chủ nhà, Gia đình, Khách).
- Bổ sung pytest cần thiết; toàn bộ pytest phải PASS khi chạy bằng `python -X utf8 -m pytest tests/ --basetemp=.pytest_tmp`. Không dừng khi còn test FAIL; sửa đến khi PASS.
- Nếu chỉnh sửa mã nguồn Android: `./gradlew assembleDebug` phải hoàn thành thành công.
- Hoàn thiện FIX_REPORT_20261104.md (gộp kết quả Phase 1 + Phase 2).
- Commit và push lên nhánh đang track (master). Deploy Vercel production nếu CLI đã login + verify URL; nếu CLI chưa login, ghi nhận cảnh báo vào báo cáo và không dừng tiến trình.
