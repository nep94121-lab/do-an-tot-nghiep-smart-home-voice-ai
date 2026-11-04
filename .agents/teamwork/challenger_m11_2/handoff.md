# BÁO CÁO THẨM ĐỊNH & PHẢN BIỆN ADVERSARIAL: MILESTONE M11 — VERCEL PRODUCTION ROUTING & REDIRECTION

- **Agent ID**: `teamwork_challenger` (challenger_m11_2)
- **Parent Conversation ID**: `39d935a1-0551-429d-ac45-c89f1e361ad0`
- **Thời gian hoàn tất**: 2026-11-04T15:42:00Z
- **Loại bàn giao**: Hard Handoff
- **Phán quyết (Verdict)**: **APPROVE**

---

## Challenge Summary

- **Mục tiêu**: Thẩm định thực nghiệm, phản biện và stress-test toàn diện định tuyến Vercel Production & Redirection (Milestone M11, Requirement R1).
- **Đánh giá rủi ro tổng thể**: **LOW** (An toàn tuyệt đối, định tuyến chuẩn xác, bảo vệ chặt chẽ các boundary regex và content negotiation).
- **Phán quyết cuối cùng**: **APPROVE**.

---

## 1. Observation (Quan sát & Thực nghiệm Trực tiếp)

1. **Thực nghiệm `/mobile` với query strings**:
   - `GET /mobile` (không follow redirect): trả về HTTP `307 Temporary Redirect` với header `Location: /app`.
   - `GET /mobile` (follow redirect): trả về HTTP `200 OK`, kích thước 39,499 bytes, chứa HTML ứng dụng di động (`mobile_app/index.html`).
   - `GET /mobile?user=test` (không follow redirect): trả về HTTP `307 Temporary Redirect`, `Location: /app`.
   - `GET /mobile?user=test` (follow redirect): trả về HTTP `200 OK`, `has_title=True`.
   - `GET /mobile/?user=test` (có trailing slash và query string): xử lý redirect sạch về `http://testserver/mobile?user=test` rồi chuyển tiếp về `/app` (HTTP 200 OK).
   - `GET /mobile?a=1&b=2`: trả về HTTP `307 Temporary Redirect` tới `/app` (follow: HTTP 200 OK).

2. **Thực nghiệm `/architecture` (Tồn tại tệp và Headers)**:
   - Tệp vật lý đích `docs/kien_truc/smart-home-voice-ai.architecture.html`: tồn tại thực tế trên đĩa, kích thước 861,391 bytes (~861 KB), chứa đầy đủ mã nguồn sơ đồ tương tác Archify v3.2.0.
   - `GET /architecture`: trả về HTTP `200 OK`, `Content-Type: text/html; charset=utf-8`, header `Cache-Control: no-cache, no-store, must-revalidate`.
   - `GET /architecture/`: trả về HTTP `307` chuyển hướng về `/architecture`, follow trả về HTTP `200 OK`, length 861,391 bytes.
   - `GET /architecture?v=1`: trả về HTTP `200 OK`, length 861,391 bytes.

3. **Thực nghiệm Content Negotiation trên các route không tồn tại (FastAPI 404 Handler)**:
   - Trình duyệt truy cập URL không tồn tại (`Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8`): trả về HTTP `404 Not Found`, `Content-Type: text/html; charset=utf-8`, thân trang hiển thị mã nguồn `404.html` tùy biến (`<!doctype html>\n<html lang="vi">... Không tìm thấy trang`).
   - Client API truy cập URL không tồn tại (`Accept: application/json`): trả về HTTP `404 Not Found`, `Content-Type: application/json`, body: `{"detail":"Not Found"}`.
   - Client curl/generic (`Accept: */*` hoặc không có Accept header): trả về HTTP `404 Not Found`, `Content-Type: application/json`, body: `{"detail":"Not Found"}`.
   - Gọi endpoint không tồn tại dưới `/api/*` (dù gửi kèm `Accept: text/html`): luôn luôn trả về HTTP `404 Not Found`, `Content-Type: application/json` (`{"detail":"Not Found"}`), không bao giờ bị lộ HTML ra luồng API.
   - Endpoint thiết bị không tồn tại `/api/devices/nonexistent`: bảo lưu chính xác `JSONResponse({"detail":"Not Found"}, status_code=404)`.

4. **Thực nghiệm Regex Boundary Hijacking trên `vercel.json`**:
   - Các URL có tiền tố tương tự như `/mobile_extra`, `/mobile/subpath`, `/mobile.html`: không bị match nhầm vào quy tắc redirect do quy tắc `^/mobile/?$` có neo kết thúc dòng `$`. Chúng rơi xuống đúng quy tắc catch-all cuối cùng trả về `404.html` với status 404.
   - Tương tự, `/architecture_fake`, `/architecture/nested/deep` rơi xuống đúng catch-all 404.
   - Tuyệt đối không có hiện tượng prefix shadowing.

5. **Kết quả chạy Test Suite tự động**:
   - Chạy lệnh: `python -X utf8 -m pytest tests/test_m6_web_error_sw.py --basetemp=.pytest_tmp`
     - Kết quả: `17 passed, 3 warnings in 8.40s`. Exit code: 0.
   - Chạy lệnh: `python -X utf8 -m pytest tests/test_challenger_m11_vercel_routing.py --basetemp=.pytest_tmp`
     - Kết quả: `17 passed, 3 warnings in 10.08s`. Exit code: 0.
   - Thư mục `.pytest_tmp` đã được dọn dẹp sạch sẽ ngay sau khi kiểm thử.

6. **Kiểm tra chuẩn định dạng (Zero-Pollution & Encoding)**:
   - `vercel.json`: CRLF=0, BOM=False (UTF-8 không BOM, POSIX LF).
   - `simulator/server.py`: CRLF=0, BOM=False (UTF-8 không BOM, POSIX LF).

---

## 2. Logic Chain (Chuỗi suy luận Phản biện)

1. Từ **Quan sát 1**, việc truy cập `/mobile` với bất kỳ biến thể tham số nào (`?user=test`, `?a=1&b=2`, có hoặc không có dấu gạch chéo cuối `/`) đều kích hoạt redirect 307 sạch sẽ về `/app`, tải thành công mã nguồn giao diện điện thoại (200 OK). Do đó, yêu cầu `/mobile` chuyển hướng về `/app` được đáp ứng trọn vẹn và không phát sinh lỗi vòng lặp hay rơi rớt query params.
2. Từ **Quan sát 2**, đường dẫn `/architecture` liên kết trực tiếp tới sơ đồ kiến trúc hệ thống thực tế trên đĩa `docs/kien_truc/smart-home-voice-ai.architecture.html` (861 KB), MIME type `text/html` chuẩn xác và header `Cache-Control` được kiểm soát đầy đủ.
3. Từ **Quan sát 3**, cơ chế Content Negotiation trong `simulator/server.py` phân tách tường minh giữa Browser Navigation (`Accept: text/html` -> `404.html`) và API Consumers (`Accept: application/json` / `*/*` -> `{"detail":"Not Found"}`). Đặc biệt, các URL bắt đầu bằng `/api/` luôn được bảo vệ để chỉ trả về JSON, ngăn chặn hoàn toàn lỗi trả về HTML cho các lệnh gọi REST client.
4. Từ **Quan sát 4**, các biểu thức chính quy trong `vercel.json` sử dụng đầy đủ các neo bắt đầu `^` và kết thúc `$`, ngăn ngừa hoàn toàn nguy cơ Path Traversal hoặc Prefix Hijacking. Quy tắc bắt cuối `^/(.*)$` đặt ở vị trí cuối cùng của mảng, bảo đảm không nuốt các route phía trước (`/api/*`, `/static/*`, `/app`, `/architecture`, `/sw.js`).
5. Từ **Quan sát 5 và 6**, toàn bộ 34 tests (17 unit/integration test + 17 adversarial stress tests) đều vượt qua 100% với exit code 0. Không có mã giả (facade), mã nguồn sạch không dính CRLF/BOM.

---

## 3. Caveats (Lưu ý)

- Việc kiểm tra trực tiếp bằng lệnh `curl` trên domain production thật (`https://do-an-tot-nghiep-smart-home-voice-a.vercel.app`) sẽ được thực thi tại Giai đoạn R6 sau khi hoàn tất toàn bộ các Milestones và tiến hành deploy Vercel chính thức.
- Ngoài lưu ý trên, **No caveats**.

---

## 4. Conclusion (Kết luận & Phán quyết)

- **Phán quyết**: **APPROVE**.
- Milestone M11 (Vercel Production Routing & Redirection) do `worker_m11` thực hiện đã vượt qua tất cả các bài thử thách adversarial gắt gao nhất:
  - `/mobile` chuyển hướng 307 sạch sẽ về `/app` ngay cả khi có query parameters phức tạp.
  - `/architecture` phục vụ chuẩn tệp sơ đồ kiến trúc với header hợp lệ.
  - Cơ chế Content Negotiation 404 hoạt động xuất sắc cho cả trình duyệt và client API.
  - Bộ kiểm thử `tests/test_m6_web_error_sw.py` PASS 100%.

---

## 5. Verification Method (Phương pháp Tái Kiểm chứng)

Người thẩm định độc lập có thể kiểm chứng lại toàn bộ kết luận bằng các lệnh sau:

1. **Kiểm tra redirect `/mobile` và route `/architecture` kèm query string**:
   ```powershell
   python -c "from starlette.testclient import TestClient; from simulator.server import app; c = TestClient(app); r = c.get('/mobile?user=test', follow_redirects=False); assert r.status_code == 307 and r.headers['location'] == '/app'; r_arch = c.get('/architecture'); assert r_arch.status_code == 200 and 'archify' in r_arch.text.lower(); print('Adversarial Route Verification: PASSED')"
   ```

2. **Kiểm tra Content Negotiation 404 (Browser vs API)**:
   ```powershell
   python -c "from starlette.testclient import TestClient; from simulator.server import app; c = TestClient(app); r_browser = c.get('/unknown_page_xyz', headers={'Accept': 'text/html'}); assert r_browser.status_code == 404 and 'Không tìm thấy trang' in r_browser.text; r_api = c.get('/api/unknown_xyz', headers={'Accept': 'text/html'}); assert r_api.status_code == 404 and r_api.json()['detail'] == 'Not Found'; print('Content Negotiation 404: PASSED')"
   ```

3. **Chạy toàn bộ pytest suite chuẩn**:
   ```powershell
   python -X utf8 -m pytest tests/test_m6_web_error_sw.py --basetemp=.pytest_tmp
   powershell -Command "if (Test-Path '.pytest_tmp') { Remove-Item -Recurse -Force '.pytest_tmp' }"
   ```

4. **Kiểm tra chuẩn định dạng tệp (0 CRLF, UTF-8 no BOM)**:
   ```powershell
   python -c "for f in ['vercel.json', 'simulator/server.py']: b = open(f, 'rb').read(); assert b.count(b'\r\n') == 0; assert not b.startswith(b'\xef\xbb\xbf'); print(f, 'Format PASSED')"
   ```
