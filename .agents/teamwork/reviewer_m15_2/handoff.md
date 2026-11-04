# Handoff Report - Reviewer M15 (Instance 2): Vercel Production Deploy & Routing Architecture (Requirements R1, R5, R6)

## 1. Observation

### 1.1. Cấu hình Định Tuyến `vercel.json`
Trực tiếp kiểm tra tệp [`vercel.json`](file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/vercel.json) tại gốc dự án (39 dòng, 2,175 bytes):
- **Quy tắc 307 Redirect `/mobile -> /app` (Dòng 16):**
  `{ "src": "^/mobile/?$", "status": 307, "headers": { "Location": "/app" } }`
  Xử lý chính xác cả `/mobile` và `/mobile/`, trả về HTTP status `307` và header `Location: /app`.
- **Quy tắc Service Worker `/sw.js` (Dòng 5-13 và 17):**
  Headers toàn cục và rewrite trực tiếp trỏ về `/simulator/static/sw.js` kèm theo headers:
  `Service-Worker-Allowed: /` và `Cache-Control: no-cache, no-store, must-revalidate`.
- **Quy tắc Các Trang Lỗi & Ngoại Tuyến (Dòng 18-22):**
  - `/offline` và `/offline.html`: `status: 200`, trỏ về `/simulator/static/offline.html`.
  - `/404` và `/404.html`: `status: 404`, trỏ về `/simulator/static/404.html`.
  - `/500` và `/500.html`: `status: 500`, trỏ về `/simulator/static/500.html`.
  - `/qr_expired`, `/qr-expired`, `/qr_expired.html`: `status: 200`, trỏ về `/simulator/static/qr_expired.html`.
  - `/403` và `/403.html`: `status: 403`, trỏ về `/simulator/static/403.html`.
- **Quy tắc Sơ đồ Kiến trúc Tương tác `/architecture` (Dòng 31-34):**
  - `/architecture/?$`: trỏ về `/docs/kien_truc/smart-home-voice-ai.architecture.html` (kích thước 862,456 bytes).
  - `/archify/?$`: trỏ về `/docs/kien_truc/smart-home-voice-ai.architecture.html`.
  - `/archify/devops/?$`: trỏ về `/docs/kien_truc/devops-cicd-pipeline.workflow.html`.
  - `/archify/erd/?$`: trỏ về `/docs/kien_truc/smarthome-database.erd.html`.
- **Quy tắc Catch-all Tùy Biến 404 (Dòng 36):**
  `{ "src": "^/(.*)$", "status": 404, "dest": "/simulator/static/404.html" }`
  Nằm ở vị trí cuối cùng của mảng `routes`, đảm bảo mọi đường dẫn không tồn tại đều được chuyển hướng về trang 404 tùy biến của dự án với mã trạng thái HTTP 404, ngăn chặn hoàn toàn màn hình lỗi NOT_FOUND thô mặc định của Vercel Edge.

### 1.2. Kiểm Tra Tài Nguyên Vật Lý Tại Đích Đến Trên Đĩa
Xác nhận sự tồn tại và kích thước thực tế của tất cả các tệp HTML/JS được trỏ tới bởi `vercel.json`:
- `simulator/static/404.html`: Tồn tại, kích thước 4,272 bytes.
- `simulator/static/offline.html`: Tồn tại, kích thước 7,441 bytes.
- `simulator/static/500.html`: Tồn tại, kích thước 4,633 bytes.
- `simulator/static/qr_expired.html`: Tồn tại, kích thước 4,502 bytes.
- `simulator/static/403.html`: Tồn tại, kích thước 4,989 bytes.
- `simulator/static/sw.js`: Tồn tại, kích thước 3,590 bytes.
- `simulator/static/index.html`: Tồn tại, kích thước 29,982 bytes.
- `mobile_app/index.html`: Tồn tại, kích thước 40,931 bytes.
- `docs/kien_truc/smart-home-voice-ai.architecture.html`: Tồn tại, kích thước 862,456 bytes.

### 1.3. Xác Minh Triển Khai Vercel Production Độc Lập
Thực thi lệnh kiểm tra chính thức:
`npx --yes vercel inspect dpl_EtgiuDsSv8qdpa5zFA8H8K9XGEKh`
Kết quả trả về nguyên văn:
```text
Vercel CLI 59.16.0 (Node.js 26.7.0)
Fetching deployment "dpl_EtgiuDsSv8qdpa5zFA8H8K9XGEKh" in tuananhs-projects-8aea56ce
> Fetched deployment "do-an-tot-nghiep-smart-home-voice-29lakxlcw.vercel.app" in tuananhs-projects-8aea56ce [453ms]

  General
    id          dpl_EtgiuDsSv8qdpa5zFA8H8K9XGEKh
    name        do-an-tot-nghiep-smart-home-voice-ai
    target      production
    status      ● Ready
    url         https://do-an-tot-nghiep-smart-home-voice-29lakxlcw.vercel.app

  Aliases
    ╶ https://do-an-tot-nghiep-smart-home-voice-a.vercel.app
    ╶ https://do-an-tot-nghiep-smart-home-voice-ai-tuananhs-projects-8aea56ce.vercel.app

  Builds
    ┌ .        [0ms]
    └── λ api/index (68.07MB) [iad1]
```
Xác nhận: Trạng thái `● Ready`, Target `production`, Domain chính thức `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app` đã gán alias thành công.

### 1.4. Kiểm Chứng Trực Tiếp Qua `curl.exe` Trên Domain Production Thật
Thực thi kiểm tra mạng thực tế trực tiếp tới CDN Vercel:
1. `curl.exe -s -i https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/mobile`
   -> `HTTP/1.1 307 Temporary Redirect`, Header: `Location: /app`.
2. `curl.exe -s -i https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/mobile/`
   -> `HTTP/1.1 307 Temporary Redirect`, Header: `Location: /app`.
3. `curl.exe -s -i https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/architecture`
   -> `HTTP/1.1 200 OK`, `Content-Length: 862455`.
4. `curl.exe -s -i https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/offline`
   -> `HTTP/1.1 200 OK`, `Content-Length: 7440`.
5. `curl.exe -s -i https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/404`
   -> `HTTP/1.1 404 Not Found`, `Content-Length: 4271`.
6. `curl.exe -s -i https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/403`
   -> `HTTP/1.1 403 Forbidden`, `Content-Length: 4988`.
7. `curl.exe -s -i https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/500`
   -> `HTTP/1.1 500 Internal Server Error`, `Content-Length: 4632`.
8. `curl.exe -s -i https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/qr_expired`
   -> `HTTP/1.1 200 OK`, `Content-Length: 4501`.
9. `curl.exe -s -i https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/sw.js`
   -> `HTTP/1.1 200 OK`, `Service-Worker-Allowed: /`, `Cache-Control: no-cache, no-store, must-revalidate`.
10. `curl.exe -s -i https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/duong-dan-khong-ton-tai-xyz-404`
    -> `HTTP/1.1 404 Not Found`, `Content-Length: 4271`.
    Nội dung trả về: HTML tiêu đề `<title>Không tìm thấy trang · Nhà thông minh</title>`, chứa font `Be Vietnam Pro` và CSS layout tùy biến, hoàn toàn không có lỗi thô Vercel NOT_FOUND.

### 1.5. Kết Quả Kiểm Thử Đối Kháng (Adversarial Probe & Stress Tests)
- Chạy bộ kiểm thử đối kháng `tests/test_challenger_m11_vercel_routing.py`:
  - `17 passed, 3 warnings in 59.49s` (`Exit Code: 0`).
  - Kiểm tra toàn bộ regex compile, anchor `^` và `$`, chống prefix hijacking (`/mobile_fake`), bảo vệ `/api/*` và `/static/*`, kiểm tra tương thích ngược giữa FastAPI TestClient và Vercel Edge.
- Thử nghiệm tấn công trực tiếp lên Live CDN:
  - `/mobile?src=home`: Trả về `307` (giữ nguyên quy tắc redirect).
  - `/architecture?tab=erd`: Trả về `200` (hiển thị trang kiến trúc).
  - `/offline?retry=true`: Trả về `200`.
  - `/sw.js?v=2.0`: Trả về `200`.
  - `/../../etc/passwd`: Trả về `403 Forbidden` (Vercel Edge WAF chặn triệt để Path Traversal).
  - `/%2e%2e/%2e%2e/secret`: Trả về `404 Not Found` (Custom 404).
  - `/MOBILE`: Trả về `404 Not Found` (Custom 404).
  - `/.git/config` & `/.env.production`: Trả về `404 Not Found` (Custom 404, không rò rỉ dữ liệu).

### 1.6. Kiểm Tra Toàn Vẹn & Chống Gian Lận (Integrity Violation Check)
- Không phát hiện bất kỳ đoạn mã hardcode kết quả test hay facade nào trong mã nguồn.
- Kiểm thử chạy qua các engine độc lập (Starlette TestClient, Vercel CLI inspect, Windows `curl.exe`).
- Báo cáo và mã nguồn đã được đồng bộ lên remote GitHub `origin/master` tại Commit `02a715e` và `9cf67dc`.

---

## 2. Logic Chain

1. Từ yêu cầu nghiệm thu Milestone M15 (Requirements R1, R5, R6): Mục tiêu là xác thực kiến trúc định tuyến Vercel, kiểm tra các quy tắc redirect, rewrite, status code của các trang lỗi và trang kiến trúc, xác thực deployment ID trên production, và kiểm tra không có lỗi NOT_FOUND thô của Vercel.
2. Kiểm tra tĩnh tệp `vercel.json` (Quan sát 1.1) chứng minh cú pháp JSON hoàn toàn hợp lệ, các biểu thức chính quy đều có anchor chặn đầu cuối (`^`, `$`), quy tắc 307 cho `/mobile` hoạt động với cả dấu gạch chéo cuối (`/?$`), các trang lỗi `/offline`, `/404`, `/403`, `/500`, `/qr_expired` trả đúng status code quy định, và quy tắc catch-all `^/(.*)$` đặt ở cuối mảng để bắt tất cả các yêu cầu còn lại về `404.html`.
3. Kiểm tra tệp vật lý (Quan sát 1.2) chứng minh mọi đích đến (`dest`) trong `vercel.json` đều là tệp thực tế trên đĩa với dung lượng đầy đủ, không phải dummy hay placeholder.
4. Kiểm tra dịch vụ đám mây thông qua `vercel inspect` (Quan sát 1.3) chứng minh deployment `dpl_EtgiuDsSv8qdpa5zFA8H8K9XGEKh` đang ở trạng thái `Ready`, thuộc môi trường `production`, và liên kết trực tiếp với domain `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app`.
5. Kiểm tra thực nghiệm trực tiếp bằng `curl.exe` (Quan sát 1.4) và kiểm thử đối kháng (Quan sát 1.5) chứng minh rằng cả 9 tuyến đường được chỉ định lẫn các tuyến đường biên (trailing slashes, query parameters, URL không tồn tại, tấn công path traversal) đều trả về mã HTTP chuẩn xác 100%, nội dung trang lỗi 404 là trang giao diện tùy biến của Đồ án.
6. Toàn bộ chuỗi bằng chứng độc lập từ mã nguồn tĩnh, test unit đối kháng, cho tới thực nghiệm mạng CDN công cộng đều đồng nhất, nhất quán và trung thực.

---

## 3. Caveats

- Các API phần cứng đặc thù như streaming âm thanh 2 chiều qua WebSocket (`ws://` hoặc `wss://`) và trích xuất sinh trắc học giọng nói thời gian thực được thiết kế để chạy trực tiếp trên máy chủ cục bộ (`simulator/server.py`) hoặc backend server chuyên dụng, không phụ thuộc vào hạ tầng serverless tĩnh của Vercel Edge.
- Không có caveat nào khác.

---

## 4. Conclusion

Milestone M15 và các yêu cầu R1, R5, R6 đã được Worker triển khai và hoàn thành **XUẤT SẮC, ĐẦY ĐỦ VÀ CHÍNH XÁC 100%**. 
- Cấu hình `vercel.json` chuẩn mực, không có xung đột thứ tự rule.
- Quy tắc 307 redirect `/mobile -> /app` hoạt động hoàn hảo.
- Quy tắc `/architecture` dẫn tới trang kiến trúc tương tác Archify v3.2.0 hoàn chỉnh.
- Toàn bộ các trang `/offline`, `/404`, `/403`, `/500`, `/qr_expired`, `/sw.js` trả về đúng mã trạng thái và headers.
- Catch-all 404 trả về giao diện tùy biến `404.html` chuẩn Design System tiếng Việt, loại bỏ triệt để lỗi NOT_FOUND thô của Vercel.
- Domain `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app` và Deployment `dpl_EtgiuDsSv8qdpa5zFA8H8K9XGEKh` đã sẵn sàng hoạt động ở cấp độ sản xuất.

**PHÁN QUYẾT CHÍNH THỨC:**
# `VERDICT: APPROVE`

---

## 5. Verification Method

Bất kỳ bên thứ ba hoặc thành viên nhóm nào cũng có thể kiểm chứng độc lập kết quả nghiệm thu này bằng các bước sau:

1. **Kiểm tra thông tin Deployment qua Vercel CLI:**
   ```bash
   npx --yes vercel inspect dpl_EtgiuDsSv8qdpa5zFA8H8K9XGEKh
   ```
   *Điều kiện đạt:* Target là `production`, Status là `Ready`, Aliases chứa `https://do-an-tot-nghiep-smart-home-voice-a.vercel.app`.

2. **Kiểm tra trực tiếp các đường dẫn qua curl.exe:**
   ```powershell
   # 1. Redirect /mobile -> /app (307)
   curl.exe -s -o NUL -w "%{http_code}" https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/mobile
   # Output: 307

   # 2. Trang Kiến trúc (200)
   curl.exe -s -o NUL -w "%{http_code}" https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/architecture
   # Output: 200

   # 3. Trang Ngoại tuyến (200)
   curl.exe -s -o NUL -w "%{http_code}" https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/offline
   # Output: 200

   # 4. Trang 404 Not Found (404)
   curl.exe -s -o NUL -w "%{http_code}" https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/404
   # Output: 404

   # 5. Trang 403 Forbidden (403)
   curl.exe -s -o NUL -w "%{http_code}" https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/403
   # Output: 403

   # 6. Trang 500 Server Error (500)
   curl.exe -s -o NUL -w "%{http_code}" https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/500
   # Output: 500

   # 7. Trang QR hết hạn (200)
   curl.exe -s -o NUL -w "%{http_code}" https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/qr_expired
   # Output: 200

   # 8. Service Worker (200 & Service-Worker-Allowed header)
   curl.exe -s -i https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/sw.js | findstr /i "Service-Worker-Allowed"
   # Output: Service-Worker-Allowed: /

   # 9. Catch-all URL ngẫu nhiên (404 tùy biến)
   curl.exe -s -o NUL -w "%{http_code}" https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/duong-dan-khong-ton-tai-xyz-404
   # Output: 404
   ```

3. **Chạy bộ kiểm thử đối kháng Vercel:**
   ```bash
   python -X utf8 -m pytest tests/test_challenger_m11_vercel_routing.py -v
   ```
   *Điều kiện đạt:* 17/17 tests PASSED với Exit Code 0.
