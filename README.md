# 🏠 ĐỒ ÁN TỐT NGHIỆP CỬ NHÂN ĐIỆN TỬ – VIỄN THÔNG
**Đề tài:** Hệ thống Nhà thông minh điều khiển bằng Giọng nói AI thời gian thực, Phân quyền Sinh trắc học 3 tầng, Tự động hóa 2 Bể (Hẹn giờ & Luật liên động) kết hợp Bản sao số 3D (Digital Twin) và Thu – Phát Sóng Hồng Ngoại trên Vi điều khiển ESP8266.
- **Tác giả / Admin Cấp 1:** Nguyễn Tuấn Anh

---

## 📂 SƠ ĐỒ TỔ CHỨC THƯ MỤC DỰ ÁN (ĐÃ SẮP XẾP CHUẨN)

```text
đồ án tốt nghiệp/
├── README.md                        # Bản đồ tổng quan & ghi chú cấu trúc toàn dự án (file này)
├── KE_HOACH_DO_AN_TOT_NGHIEP.md     # Lộ trình chi tiết: Việc đã xong, linh kiện cần mua & việc cần làm tiếp
├── requirements.txt                 # Danh sách thư viện Python của Backend Server
├── .gitignore                       # Bảo vệ file .env (API Key) & chặn file rác khỏi Git
│
├── simulator/                       # [PHÂN KHU 1] BACKEND SERVER TỰ XÂY DỰNG & WEB DASHBOARD 3D
│   ├── server.py                    # Máy chủ FastAPI + WebSocket + Gemini 3.8 Live + API điều khiển
│   ├── rule_engine.py               # Lõi xử lý Phân quyền 3 tầng, Bể 1 (Hẹn giờ), Bể 2 (Luật IF-ELSE/Đổi lệnh), 4 Reset
│   ├── voice_auth.py                # Xử lý tín hiệu DSP giọng nói (F0 Hz, FFT, Mel 26-D) & Chặn 2-Strike
│   ├── knowledge_rag.py             # Kho tri thức Vector RAG (gemini-embedding-001, 3072 chiều)
│   ├── data/                        # Cơ sở dữ liệu nội bộ (JSON/Vector, không dùng Firebase/Supabase)
│   │   ├── factory_defaults.json    # Cấu hình 6 thiết bị & khẩu lệnh mặc định gốc
│   │   ├── custom_rules_overlay.json# Lưu Bể lệnh riêng từng người, lịch hẹn & quy tắc Admin Cấp 1
│   │   ├── voiceprints.json         # Lưu hồ sơ tần số giọng nói đã đăng ký
│   │   └── knowledge_base.json      # Lưu tri thức RAG và vector nhúng 3072 chiều
│   └── static/                      # [PHÂN KHU 2] GIAO DIỆN WEB DASHBOARD & NHÀ 3D (TRÊN MÁY TÍNH)
│       ├── index.html               # Giao diện chính của Web Dashboard 3D
│       ├── style.css                # Giao diện CSS Dark Mode
│       ├── house3d.js               # Mô hình ngôi nhà 3D Digital Twin (Three.js)
│       └── app.js                   # Kết nối WebSocket thời gian thực, thu âm Mic & đồng bộ 2 Bể
│
├── mobile_app/                      # [PHÂN KHU 3] GIAO DIỆN APP ĐIỆN THOẠI RIÊNG (Độc lập với Web 3D)
│   └── README.md                    # Ghi chú thiết kế App di động (Điều khiển giọng nói, xem DHT11, học lệnh IR)
│
├── firmware_esp8266/                # [PHÂN KHU 4] CODE NẠP VI ĐIỀU KHIỂN NODEMCU ESP8266 (.ino / C++)
│   └── README.md                    # Sơ đồ chân chuẩn D1..D8, cảm biến DHT11 & thu phát hồng ngoại 38kHz
│
├── scripts/                         # BỘ KỊCH BẢN KIỂM THỬ TỰ ĐỘNG (E2E TESTS)
│   ├── test_simulator_e2e.py        # Kiểm thử toàn diện 100% tính năng (Rule 3 tầng, Hẹn giờ, Reset, RAG, Thu âm)
│   ├── check_gemini_live.py         # Kiểm tra kết nối Gemini Live API
│   ├── make_test_audio.py           # Tạo mẫu âm thanh kiểm thử chuẩn 16kHz PCM
│   └── measure_live_latency.py      # Đo độ trễ phản hồi thời gian thực (ms)
│
├── test_audio/                      # Các file âm thanh mẫu (.wav 16kHz) phục vụ kiểm thử tự động
└── docs/                            # Thư mục lưu trữ tài liệu thuyết minh & đề cương tham khảo
    └── tai_lieu_tham_khao/          # Các bản nháp đề cương cũ được gom gọn vào một chỗ
```

---

## 🚀 HƯỚNG DẪN CHẠY & KIỂM THỬ NHANH

1. **Khởi động Backend Server & Giao diện Web 3D (`http://127.0.0.1:8088`):**
   ```powershell
   python -X utf8 -m uvicorn simulator.server:app --host 127.0.0.1 --port 8088
   ```
2. **Chạy bộ kiểm thử tự động toàn diện (E2E Test — xác nhận 100% PASS):**
   ```powershell
   python -X utf8 scripts/test_simulator_e2e.py
   ```
