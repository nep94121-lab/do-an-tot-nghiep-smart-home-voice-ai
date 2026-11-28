# Bộ Hồ Sơ Báo Cáo Đồ Án Tốt Nghiệp (`docs/bao_cao/`)

Thư mục này chứa kịch bản tái tạo tự động Báo cáo Đồ án Tốt nghiệp (`.docx`), toàn bộ tài nguyên hình ảnh, biểu trưng chính thức (`LOGO_SOURCES.md`) và các mô-đun nội dung chuẩn hóa theo mẫu Đại học Bách khoa Hà Nội (HUST — Trường Điện - Điện tử).

## 1. Cấu trúc thư mục

```text
docs/bao_cao/
├── README.md                                  # Tài liệu hướng dẫn này
├── LOGO_SOURCES.md                            # Nguồn URL, ngày tải và điều khoản bản quyền 21 logo chính thức
├── build_graduation_report.py                 # Kịch bản python-docx tái chạy được (hỗ trợ --line-spacing, --run-dir)
├── Bao_Cao_DATN_Smart_Home_Voice_AI.docx      # Tệp báo cáo Word đầu ra (cập nhật TOC/TOF/TOT bằng Word COM)
├── Bao_Cao_DATN_Smart_Home_Voice_AI.pdf       # Tệp PDF xuất từ Word COM ở Pha 1C
├── report_sections/                           # Các mô-đun nội dung & định dạng OOXML
│   ├── docx_helpers.py                        # Thiết lập A4, lề, Times New Roman, viền đôi, trường Word TOC/SEQ
│   ├── front_matter.py                        # 10 trang phần đầu (Bìa chính, Bìa phụ, Đề tài, Cam đoan, Cảm ơn, Tóm tắt, Mục lục, Từ viết tắt, DM Hình, DM Bảng)
│   ├── chapters_1_2.py                        # Chương 1 (Tổng quan) & Chương 2 (Khảo sát & phân tích yêu cầu)
│   ├── chapter_3.py                           # Chương 3 (Công nghệ & linh kiện SSOT 14 module, 21 logo, phần mềm)
│   ├── chapter_4.py                           # Chương 4 (Thiết kế & triển khai 7 phân hệ + PCB v3 + In 3D 16 bàn)
│   └── chapters_5_6_refs.py                   # Chương 5 (Kết quả, tự nạp ảnh APK Pha 1C), Chương 6 & Tài liệu tham khảo
└── assets/
    ├── logos/                                 # 21 biểu trưng phần mềm/công cụ chính thức (PNG chuẩn hóa nền trắng)
    ├── demo/                                  # 33 ảnh kết xuất 3D Blender/FreeCAD, KiCad PCB, PrusaSlicer 16 bàn, Web 3D & /wokwi
    └── software/                              # 11 ảnh chụp dòng lệnh CLI/OpenAPI, sơ đồ nguyên lý KiCad và 5 sơ đồ kiến trúc tiếng Việt
```

## 2. Quy chuẩn định dạng và lựa chọn giãn dòng

- **Khổ giấy & Lề trang:** A4 (`21,0 × 29,7 cm`), lề Trái `3,5 cm`, Phải `2,0 cm`, Trên `2,0 cm`, Dưới `2,0 cm`.
- **Phông chữ:** `Times New Roman` xuyên suốt toàn văn bản (thân bài `13 pt` căn đều, thụt đầu dòng `1,27 cm`; chú thích `12 pt` in nghiêng căn giữa; số trang chân trang `12 pt`).
- **Giãn dòng (`--line-spacing`):**
  - Mặc định **`1.3`** (chuẩn HUST Multiple `1.3`, tương đương `~19,5 pt` cho chữ `13 pt`) theo quyết định **Q1** trong `GRILL_ANSWERS.md`.
  - Hỗ trợ tham số `--line-spacing 1.15` nếu cần đối chiếu mật độ dòng chặt giống bản mẫu PDF đo thực tế (`~16,4 pt`). Khi chạy Word COM xuất PDF ở Pha 1C, ghi nhận lựa chọn cuối cùng sau khi kiểm tra thị giác ảnh trang PDF.
- **Đánh số trang & Trường tự động Word:**
  - Phần Bìa chính và Bìa phụ (Section 1): khung viền đôi (`double`), không đánh số trang.
  - Phần đầu mở rộng (Section 2 — 8 trang từ `ĐỀ TÀI TỐT NGHIỆP` đến `DANH MỤC BẢNG BIỂU`): đánh số La Mã (`i, ii, iii, ...`) ở chân trang.
  - Nội dung chính từ Chương 1 đến Tài liệu tham khảo (Section 3): đánh số Ả-rập (`1, 2, 3, ...`) **căn phải chân trang**; luôn ngắt trang sạch đầu mỗi chương.
  - Sử dụng trường Word thật: `TOC \o "1-3" \h \z \u` (Mục lục), `TOC \h \z \c "Hình"` (Danh mục hình vẽ), `TOC \h \z \c "Bảng"` (Danh mục bảng biểu), `SEQ Hình` (đặt **DƯỚI** hình) và `SEQ Bảng` (đặt **TRÊN** bảng).
- **Ký hiệu cần sinh viên điền trước khi in nộp:**
  - Các mục thông tin cá nhân/trường lớp chưa khóa cứng được tô nền vàng nổi bật `[ĐIỀN: ...]` (bao gồm `[ĐIỀN: ĐẠI HỌC BÁCH KHOA HÀ NỘI — cần xác nhận]`, `[ĐIỀN: LOGO TRƯỜNG]`, MSSV, Email, Lớp/Ngành, GVHD, Tháng/Năm).
  - Các ảnh phần cứng thực tế chưa gia công hoặc giao diện GUI không chụp ẩn được đặt trong khung nét đứt `[ẢNH THỰC TẾ: ...]` / `[ẢNH CHỤP PHẦN MỀM: ...]`.

## 3. Lệnh chạy lại báo cáo

```powershell
# Tạo bản báo cáo .docx chuẩn HUST (giãn dòng 1.3 mặc định, tự động nạp ảnh APK nếu có trong RUN DIR)
python docs/bao_cao/build_graduation_report.py

# Tùy chọn giãn dòng 1.15 hoặc chỉ định thư mục RUN DIR khác
python docs/bao_cao/build_graduation_report.py --line-spacing 1.15 --run-dir "C:\Users\LENOVO\datn-wt\agyclean15_20261128"
```

Sau khi tạo `.docx`, cập nhật toàn bộ trường `TOC` / `Danh mục hình vẽ` / `Danh mục bảng biểu` / `SEQ` và xuất `.pdf` bằng Microsoft Word COM chế độ ẩn (`Visible = False`, `DisplayAlerts = 0`, `Fields.Update()`, `TablesOfContents.Update()`, `ExportAsFixedFormat`), hoặc phương án dự phòng LibreOffice headless nếu môi trường không có Word COM.

---

## Thông số bản xuất cuối cùng (`agyclean15_20261128`)

- **Giãn dòng đã chọn (Q1):** **Multiple `1.3`** (bước dòng đo thực tế trên PDF là `19.4 pt` với cỡ chữ `13 pt` Times New Roman). Lý do chọn: khớp trực tiếp quy chuẩn trình bày ĐATN HUST và đúng băng bước dòng `19.4 pt` của mẫu PDF gốc, kiểm tra thị giác các trang in (`clean15_report_p01..p78`) cho bố cục thoáng, cân đối, đạt tổng **82 trang** (nằm gọn trong mục tiêu 70–85 trang theo Q4).
- **Công cụ cập nhật trường & xuất PDF (Q3):** Đã thử Microsoft Word COM (`16.0`) trước theo mặc định, nhưng trong phiên nền không tương tác trên LENOVO lệnh `Documents.Open()` trả `None` và `Documents.Add(Template=...)` trả mã lỗi `0x800A1409`. Do đó phiên đã kích hoạt đúng phương án dự phòng Q3 là **LibreOffice 26.8.3.1 headless UNO** (`export_report_lo_uno.py`), tự động cập nhật cả 3 trường mục lục Word thật (`Mục lục`, `53/53 Danh mục hình vẽ`, `19/19 Danh mục bảng biểu`) và xuất tệp `Bao_Cao_DATN_Smart_Home_Voice_AI.pdf` (`82` trang, `0` lỗi trường tham chiếu).
- **Bản kiểm thử APK tích hợp (S4):** Đã nhúng tự động kết quả `11/11 DUNG` (`0` crash, `0` ANR), mã SHA-256 APK `22124F426ADCD847A578A85B6CEB08A2C79888EFD4EDA6E449A194602143C8F7` và ảnh chụp `adb screencap` thật vào Chương 5.
