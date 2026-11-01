---
name: archify-interactive-architecture
description: Hệ thống Tạo Sơ Đồ Kiến Trúc Tương Tác & Trang Giải Thích Trực Quan (Archify v3.2.0 - tt-a1i/archify, #1 GitHub Trending, 130K+ installs) dành riêng cho Đồ án Tốt nghiệp Smart Home Voice AI. Tự động biên dịch mã nguồn thành file HTML độc lập có gắn chứng cứ file/dòng lệnh, truy vết luồng Upstream/Downstream Reach, tô sáng đường đi (Route) và đồng bộ trực tiếp lên cổng /archify của Web Server.
---

# 🗺️ Kỹ Năng Trực Quan Hóa Kiến Trúc Tương Tác (Archify Engine v3.2.0)

> **Nguồn gốc tích hợp:** Kho mã nguồn chính thức [`tt-a1i/archify`](https://github.com/tt-a1i/archify) (đã tải về máy tại [`docs/tai_lieu_tham_khao/archify/`](file:///c:/Users/LENOVO/Desktop/đồ%20án%20tốt%20nghiệp/docs/tai_lieu_tham_khao/archify/README.md)).

## 1. Mục Đích & Giá Trị Trong Đồ Án Smart Home Voice AI
Thay vì chỉ vẽ hình ảnh tĩnh không thể tương tác, `Archify` biến toàn bộ kiến trúc **Smart Home Voice AI** và **Quy trình CI/CD DevOps** thành các **trang HTML tương tác độc lập (Standalone Interactive HTML)**:
- **Gắn chứng cứ mã nguồn thật (`Repository-Backed Sources`):** Bấm vào bất kỳ khối nào (Micro `MAX9814 RX`, Bộ lọc 2 tầng `26d/64d`, `RuleEngine`, `MQTT Bridge`, `NodeMCU ESP8266 LittleFS Tiny-DSP 16ms`, `SQLite KB Logger`) sẽ hiển thị ngay đường dẫn file, số dòng `#Lstart-Lend` và mã commit `HEAD`.
- **Truy vết bán kính ảnh hưởng (`Upstream / Downstream Reach`):** Chọn 1 khối để xem toàn bộ các thành phần đầu vào và đầu ra phụ thuộc vào nó.
- **Tô sáng luồng xử lý (`Guided Views & Route Highlighting`):** Chuyển đổi nhanh giữa 4 góc nhìn:
  1. `Luồng Giọng Nói Online (Khử ồn Quạt + Lọc 2 Tầng 26d/64d)`
  2. `Luồng Mạch Độc Lập Offline (Tiny-DSP 16.4ms - Chỉ Tầng 1 & 2)`
  3. `Luồng Phần Cứng ESP8266 (8 Chân GPIO + ADC A0 + Loa D4 + Mic RX)`
  4. `Luồng Lưu Trữ & Giám Sát (SQLite WAL + Write-Through Cache)`

## 2. Lệnh Biên Dịch & Kiểm Định Tự Động (`Archify CLI`)
Bộ công cụ `archify.mjs` chạy trực tiếp trên `Node.js` (không cần cài đặt thêm):

```powershell
# 1. Kiểm tra sức khỏe bộ dựng Archify (10 loại sơ đồ + Explainer)
node docs/tai_lieu_tham_khao/archify/archify/bin/archify.mjs doctor

# 2. Kiểm định & Xuất bản Sơ đồ Kiến trúc Tương tác (Architecture HTML)
node docs/tai_lieu_tham_khao/archify/archify/bin/archify.mjs deliver architecture docs/kien_truc/smart-home-voice-ai.architecture.json docs/kien_truc/smart-home-voice-ai.architecture.html --repo-root . --quality showcase --json

# 3. Kiểm định & Xuất bản Sơ đồ Quy trình DevOps CI/CD (Workflow HTML)
node docs/tai_lieu_tham_khao/archify/archify/bin/archify.mjs deliver workflow docs/kien_truc/devops-cicd-pipeline.workflow.json docs/kien_truc/devops-cicd-pipeline.workflow.html --repo-root . --quality showcase --json
```

## 3. Cổng Truy Cập Trực Tiếp Trên Web Simulator
- **Sơ đồ Kiến trúc Hệ thống Tương tác:** `http://127.0.0.1:8088/archify`
- **Sơ đồ Quy trình DevOps & CI/CD Tương tác:** `http://127.0.0.1:8088/archify/devops`
