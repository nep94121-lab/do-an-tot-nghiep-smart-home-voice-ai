# 🏠 ĐỒ ÁN TỐT NGHIỆP CỬ NHÂN ĐIỆN TỬ – VIỄN THÔNG (SEEE - HUST)
**Đề tài:** Hệ thống Nhà thông minh điều khiển bằng Giọng nói AI thời gian thực, Xác thực 3 Lớp (Google OAuth / Gmail OTP + Mật khẩu + Vân tay Giọng nói), Phân cấp Link Mời Đăng Ký 3 Tầng, Tự động hóa 2 Bể (Hẹn giờ & Luật liên động) kết hợp Bản sao số 3D (Digital Twin), Ứng dụng Android Native và Vi điều khiển NodeMCU ESP8266.
- **Tác giả / Admin Cấp 1:** Nguyễn Tuấn Anh (`nep94121@gmail.com`)

---

## 🔗 LIÊN KẾT DỰ ÁN & TRIỂN KHAI (TỔNG HỢP GỌN)

- **GitHub Repository:** https://github.com/nep94121-lab/do-an-tot-nghiep-smart-home-voice-ai (branch: `master`)
- **Production (Vercel Base URL):** https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/
  - **Routes chính:** `/` (Web 3D Desktop), `/mobile` hoặc `/app` (Mobile PWA), `/auth` (Xác thực 3 Lớp), `/guest_enroll` (Khách QR), `/wokwi` (Mạch ESP8266), `/logs` (Nhật ký & SQLite), `/architecture` (Kiến trúc), `/api/state` (Snapshot API)
- **Vercel Dashboard:** https://vercel.com/tuananhs-projects-8aea56ce/do-an-tot-nghiep-smart-home-voice-ai

---

## 📚 MỤC LỤC TÀI LIỆU KỸ THUẬT TRONG REPO (`docs/`)

| STT | Tài liệu chuyên sâu | Nội dung chính |
| :---: | :--- | :--- |
| **1** | **[`TAI_LIEU_XAC_THUC_3_LOP_PHAN_CAP_LINK_MOI_VA_GIONG_NOI.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/docs/kien_truc/TAI_LIEU_XAC_THUC_3_LOP_PHAN_CAP_LINK_MOI_VA_GIONG_NOI.md)** | Phân cấp gửi Link mời (`Cấp 1 ➔ 2,3` \| `Cấp 2 ➔ 3` \| `Cấp 3 ➔ Ẩn`), Đăng ký Google OAuth gửi/đọc Gmail OTP thật, Trang Đầu đọc dòng chữ mẫu & giữ thu âm lên Server, Chủ nhà xóa/bật lại quyền bằng giọng nói, và Bảng Test 14 Kịch Bản (`14/14 PASS`). |
| **2** | **[`DANH_SACH_LINH_KIEN_HIEN_CO_VA_CAN_MUA.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/docs/phan_cung/DANH_SACH_LINH_KIEN_HIEN_CO_VA_CAN_MUA.md)** | Sơ đồ chân NodeMCU ESP8266 (`D1..D8`, `A0`), danh sách linh kiện đã có và bảng 10 linh kiện mua bổ sung kèm ảnh đối chiếu thực tế. |
| **3** | **[`REPO_MAP.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/docs/kien_truc/REPO_MAP.md)** | Bản đồ kiến trúc toàn bộ mã nguồn, đồ thị gọi hàm (`CODEBASE_GRAPH.json`) và phân tích bán kính ảnh hưởng. |
| **4** | **[`HUONG_DAN_CHONG_TRAN_NGU_CANH_VA_ANH_HUONG_CHEO.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/docs/kien_truc/HUONG_DAN_CHONG_TRAN_NGU_CANH_VA_ANH_HUONG_CHEO.md)** | Quy chuẩn kiến trúc chống tràn ngữ cảnh và kiểm soát phụ thuộc liên tầng (Backend $\leftrightarrow$ Web 3D $\leftrightarrow$ App Android $\leftrightarrow$ ESP8266). |
| **5** | **[`KE_HOACH_DO_AN_TOT_NGHIEP.md`](file:///c:/Users/LENOVO/Desktop/%C4%91%E1%BB%93%20%C3%A1n%20t%E1%BB%91t%20nghi%E1%BB%87p/KE_HOACH_DO_AN_TOT_NGHIEP.md)** | Lộ trình tổng thể thực hiện Đồ án Tốt nghiệp từ mô phỏng đến lắp mạch phần cứng thật. |

---

## 📂 SƠ ĐỒ TỔ CHỨC THƯ MỤC DỰ ÁN

```text
đồ án tốt nghiệp/
├── README.md                                 # Bản đồ tổng quan & mục lục tài liệu toàn dự án (file này)
├── KE_HOACH_DO_AN_TOT_NGHIEP.md              # Lộ trình chi tiết thực hiện Đồ án Tốt nghiệp
├── requirements.txt                          # Danh sách thư viện Python của Backend Server
│
├── simulator/                                # [PHÂN KHU 1] BACKEND SERVER & WEB DASHBOARD 3D + TRUNG TÂM 3 LỚP
│   ├── server.py                             # Máy chủ FastAPI + WebSocket + Gemini 3.8 Live + REST API (/api/auth3/*)
│   ├── auth_3layer.py                        # Lõi Xác thực 3 Lớp, Phân cấp Link Mời, OAuth Gmail OTP, Thu âm Trang Đầu & Giọng nói Xóa/Bật Quyền
│   ├── rule_engine.py                        # Lõi xử lý Phân quyền 3 tầng, Bể 1 (Hẹn giờ), Bể 2 (Luật IF-ELSE/Đổi lệnh), 4 Reset
│   ├── voice_auth.py                         # Xử lý tín hiệu DSP giọng nói (F0 Hz, FFT, Mel 26-D) & Chặn 2-Strike
│   ├── knowledge_rag.py                      # Kho tri thức Vector RAG (gemini-embedding-001, 3072 chiều)
│   ├── db_sqlite.py                          # Cơ sở dữ liệu quan hệ SQLite 3 (smarthome.db, chuẩn 3NF, 8 bảng)
│   ├── data/                                 # Cơ sở dữ liệu nội bộ (JSON + SQLite + Hồ sơ Tài khoản & Link Mời)
│   │   ├── accounts_3layer.json              # CSDL Tài khoản 3 Tầng, trạng thái Quyền (ACTIVE/REVOKED) & Mẫu giọng F0
│   │   ├── invite_links_3layer.json          # CSDL các đường Link Mời phân cấp (Cấp 1 -> 2,3 | Cấp 2 -> 3)
│   │   ├── auth_3layer_events.json           # Nhật ký xác thực 3 lớp, gửi Gmail OTP & thu hồi quyền
│   │   └── smarthome.db                      # Cơ sở dữ liệu SQLite 3 lưu trữ bền vững
│   └── static/                               # [PHÂN KHU 2] GIAO DIỆN WEB TRÊN MÁY TÍNH
│       ├── index.html                        # Trang Đầu: Nhà 3D Digital Twin + Thanh Đọc Câu Mẫu & Giữ Thu Âm
│       ├── auth.html                         # Trung tâm Xác thực 3 Lớp, Phân cấp Link Mời, OAuth Gmail & Bảng Test 14 Kịch Bản
│       ├── mobile.html                       # Giao diện Web Mobile (/app)
│       ├── wokwi.html                        # Trang Sơ đồ Mạch & Dây Cắm NodeMCU ESP8266 (/wokwi)
│       └── logs.html                         # Trung tâm Nhật ký & Quản trị CSDL SQLite (/logs)
│
├── android_app/                              # [PHÂN KHU 3] ỨNG DỤNG ANDROID NATIVE (KOTLIN + JETPACK COMPOSE)
│   ├── app-core/src/main/kotlin/.../MainScreen.kt # Giao diện 4 Tab (🏠 Trang chủ, 🔑 3 Lớp, ⏰ Hẹn giờ, 📜 Lịch sử)
│   └── build/SmartHomeVoiceAI-debug.apk      # File gói cài đặt APK chạy trên điện thoại Samsung Galaxy S9
│
├── firmware_esp8266/                         # [PHÂN KHU 4] FIRMWARE VI ĐIỀU KHIỂN NODEMCU ESP8266 (.ino / C++)
│   └── esp8266_smarthome/esp8266_smarthome.ino # Code thực thi 7 thiết bị + 3 cảm biến + Tiny-DSP Offline
│
├── scripts/                                  # BỘ KỊCH BẢN KIỂM THỬ TỰ ĐỘNG (E2E TESTS)
│   ├── test_auth_3layer_and_invite.py        # Kiểm thử 14 kịch bản: 3 Lớp, Link Mời, Gửi & Đọc Gmail Thật, Thu âm Trang Đầu, Xóa/Bật Quyền
│   ├── test_simulator_e2e.py                 # Kiểm thử E2E Rule Engine 3 tầng, Hẹn giờ, Reset, RAG
│   └── verify_all_gates.py                   # Kiểm thử cổng CI/CD liên tầng
│
└── docs/                                     # TÀI LIỆU KỸ THUẬT, KIẾN TRÚC & DANH MỤC PHẦN CỨNG
    ├── kien_truc/                            # Tài liệu kiến trúc hệ thống, Xác thực 3 lớp, ERD & CI/CD
    └── phan_cung/                            # Tài liệu linh kiện phần cứng & sơ đồ đấu nối ESP8266
```

---

## 🔐 TÓM TẮT CƠ CHẾ PHÂN CẤP LINK MỜI, OAUTH GMAIL, THU ÂM TRANG ĐẦU & XÓA/BẬT QUYỀN BẰNG GIỌNG NÓI

1. **Phân cấp Gửi Link Mời Đăng Ký (`Hierarchical Invite Links`):**
   - **Cấp 1 (Chủ nhà Nguyễn Tuấn Anh):** Có **2 đường link mời** để gửi xuống cấp dưới:
     - Link mời Cấp 2 (Người nhà): `http://localhost:8088/auth?invite=INV-T1-TO-TIER2`
     - Link mời Cấp 3 (Khách): `http://localhost:8088/auth?invite=INV-T1-TO-TIER3`
   - **Cấp 2 (Thành viên gia đình):** Chỉ có **1 đường link mời duy nhất xuống Cấp 3 (Khách):** `http://localhost:8088/auth?invite=INV-T2-TO-TIER3` (bị chặn nếu cố tạo link Cấp 1 hoặc Cấp 2).
   - **Cấp 3 (Khách):** **Không có phần gửi link mời cấp dưới** (`0 link`).
2. **Đăng ký qua Link Mời bằng Google OAuth (Gmail) & Cấp Mật Khẩu + OTP:**
   - Khi ấn vào link mời và chọn **Đăng nhập bằng Google OAuth (Gmail)**, Server dùng địa chỉ Gmail đó gửi thư thật qua `gws gmail` chứa **Mã xác nhận OTP 6 số** kèm **Mật khẩu cấp phát**.
   - Hệ thống hỗ trợ tự động đọc ngược hộp thư Gmail (`nep94121@gmail.com`) để lấy đúng mã OTP vừa gửi và xác nhận tự động.
3. **Vào Trang Đầu Hiển Thị Dòng Chữ Mẫu & Nhấn Giữ Để Thu Âm (`Hold-to-Record Voice Enrollment`):**
   - Sau khi đăng ký xong và vào Trang Đầu (`/` hoặc `/auth` trên Web, hoặc Tab `🏠 Trang chủ` trên App Android), màn hình hiển thị **Dòng chữ mẫu bắt buộc đọc**.
   - Người dùng **nhấn giữ nút thu âm**, đọc câu mẫu và thả tay ra $\rightarrow$ Gói âm thanh được đẩy lên Server để trích xuất tần số `F0 (Hz)` lưu làm mẫu giọng gốc chính chủ.
4. **Chủ Nhà Xóa Cấp Quyền & Bật Lại Quyền Bằng Giọng Nói Trên Thiết Bị:**
   - Khi Chủ nhà (Cấp 1) ở nhà nói *"Xóa cấp quyền của Thành viên A"*: **Tài khoản của người đó vẫn còn nguyên trên hệ thống** nhưng hiện trạng thái **`🚫 KHÔNG CÓ QUYỀN (REVOKED)`** và không thể điều khiển thiết bị.
   - Khi Chủ nhà nói *"Bật lại quyền cho Thành viên A"*: Tài khoản lập tức được khôi phục về **`✅ CÓ QUYỀN (ACTIVE)`** đúng cấp độ và mẫu giọng như cũ.

---

## 🚀 HƯỚNG DẪN CHẠY & KIỂM THỬ TOÀN DIỆN

1. **Khởi động Backend Server (`http://localhost:8088` & `http://localhost:8088/auth`):**
   ```powershell
   python -X utf8 -m uvicorn simulator.server:app --host 0.0.0.0 --port 8088
   ```
2. **Chạy Kiểm thử Tự động 14 Kịch bản Xác thực 3 Lớp, Link Mời, Đọc/Gửi Gmail Thật & Giọng nói Xóa/Bật Quyền (`14/14 PASS`):**
   ```powershell
   python -X utf8 scripts/test_auth_3layer_and_invite.py
   ```
3. **Chạy Kiểm thử Tự động Rule Engine & IoT (`100% PASS`):**
   ```powershell
   python -X utf8 scripts/test_simulator_e2e.py
   ```
