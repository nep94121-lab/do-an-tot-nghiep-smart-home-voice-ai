# Bộ Hồ Sơ Báo Cáo Đồ Án Tốt Nghiệp (`docs/bao_cao/`) — Phiên Bản 2

Thư mục này chứa kịch bản tái tạo tự động Báo cáo Đồ án Tốt nghiệp (`.docx` và `.pdf`), toàn bộ tài nguyên sơ đồ/hình ảnh, biểu trưng chính thức (`LOGO_SOURCES.md`) và các mô-đun nội dung chuẩn hóa theo mẫu trình bày Đại học Bách khoa Hà Nội (HUST — Trường Điện - Điện tử).

## 1. Cấu trúc thư mục

```text
docs/bao_cao/
├── README.md                                  # Tài liệu hướng dẫn này
├── LOGO_SOURCES.md                            # Nguồn URL, giấy phép, ngày tải và SHA-256 của logo HUST & công nghệ lõi
├── build_graduation_report.py                 # Kịch bản python-docx tái chạy được kèm tối ưu nén ảnh
├── Bao_Cao_DATN_Smart_Home_Voice_AI.docx      # Tệp báo cáo Word đầu ra (cập nhật đủ 4 mục lục tự động)
├── Bao_Cao_DATN_Smart_Home_Voice_AI.pdf       # Tệp PDF xuất từ bản báo cáo đã cập nhật mục lục
├── report_sections/                           # Các mô-đun nội dung & định dạng OOXML
│   ├── docx_helpers.py                        # A4, lề, Times New Roman 13 pt, đoạn mã Consolas 10 pt, tối ưu ảnh, trường TOC/SEQ
│   ├── code_excerpts.py                       # Trích trực tiếp 10–30 dòng mã thật từ firmware/ và backend/
│   ├── front_matter.py                        # Bìa chính/phụ có logo HUST thật + phần đầu La Mã + DANH MỤC ĐOẠN MÃ
│   ├── chapters_1_2.py                        # Chương 1 (Tổng quan) & Chương 2 (Khảo sát và phân tích yêu cầu)
│   ├── chapter_3.py                           # Chương 3 (Trọng tâm mạch điện tử ESP8266, KiCad PCB Hub, 40 dây SSOT, BOM, firmware)
│   ├── chapter_4.py                           # Chương 4 (Quy trình vận hành, chức năng, đoạn mã, vỏ 3D <= 1 trang, so sánh sản phẩm)
│   └── chapters_5_6_refs.py                   # Chương 5 (Kết quả), Chương 6 (Kết luận & hướng phát triển) & Tài liệu tham khảo
└── assets/
    ├── logos/                                 # Logo HUST chính thức và biểu trưng công nghệ cốt lõi
    ├── diagrams/                              # 4 sơ đồ khối & lưu đồ tiếng Việt vẽ mới cho v2
    ├── demo/                                  # Ảnh kết xuất mạch KiCad, đấu nối 2D, giao diện Web 3D & mô hình nhà
    ├── software/                              # Sơ đồ nguyên lý KiCad, ERD SQLite, RBAC QR, Offline FSM
    └── optimized/                             # Ảnh đã nén tự động (JPEG/PNG tối ưu) giúp .docx < 10 MB
```

## 2. Quy chuẩn trình bày phiên bản 2

- **Khổ giấy & Lề trang:** A4 (`21,0 × 29,7 cm`), lề Trái `3,5 cm`, Phải `2,0 cm`, Trên `2,0 cm`, Dưới `2,0 cm`.
- **Phông chữ & Giãn dòng:** `Times New Roman` xuyên suốt văn bản chính (`13 pt`, giãn dòng Multiple `1.3`, căn đều, thụt đầu dòng `1,27 cm`); chú thích `12 pt` in nghiêng căn giữa; khối mã nguồn dùng `Consolas 10 pt` có nền xám nhạt, viền mảnh và đánh số dòng.
- **Quy ước chú thích & 4 mục lục trường Word thật:**
  - `MỤC LỤC`: `TOC \o "1-3" \h \z \u`
  - `DANH MỤC HÌNH VẼ`: `TOC \h \z \c "Hình"` (chú thích `Hình x.y:` đặt **DƯỚI** hình)
  - `DANH MỤC BẢNG BIỂU`: `TOC \h \z \c "Bảng"` (chú thích `Bảng x.y:` đặt **TRÊN** bảng)
  - `DANH MỤC ĐOẠN MÃ`: `TOC \h \z \c "Đoạn_mã"` (chú thích `Đoạn mã x.y:` đặt **TRÊN** khối mã)
- **Đánh số trang:** Bìa chính và Bìa phụ (viền đôi, có logo ĐHBK Hà Nội thật, không số trang); phần đầu từ `ĐỀ TÀI TỐT NGHIỆP` đến `DANH MỤC ĐOẠN MÃ` đánh số La Mã (`i, ii, ...`); từ Chương 1 trở đi đánh số Ả-rập (`1, 2, ...`) căn phải chân trang, mỗi chương bắt đầu trang mới.
- **Thông tin sinh viên cần điền trước khi in:** Các trường cá nhân (khoa, lớp/ngành, MSSV, email, GVHD, tháng/năm) và tên trường có chú thích xác nhận giữ tô nền vàng `[ĐIỀN: ...]`. Hai ảnh sản phẩm lắp ráp ngoài đời giữ khung nét đứt `[ẢNH THỰC TẾ: ...]`.

## 3. Lệnh dựng lại báo cáo và xuất PDF

```powershell
# Bước 1: Tạo tệp .docx (nén ảnh tự động, trích mã nguồn thật)
python docs/bao_cao/build_graduation_report.py --summary-json build_summary.json

# Bước 2: Cập nhật đủ 4 trường mục lục tự động và xuất .pdf bằng LibreOffice headless UNO
& "C:\Program Files\LibreOffice\program\python.exe" export_report_v2_lo_uno.py `
    docs/bao_cao/Bao_Cao_DATN_Smart_Home_Voice_AI.docx `
    docs/bao_cao/Bao_Cao_DATN_Smart_Home_Voice_AI.pdf
```
