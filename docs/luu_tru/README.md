# Kho Lưu Trữ Tài Liệu Lịch Sử (`docs/luu_tru/`)

> **Cảnh báo quan trọng:** **Tài liệu lịch sử/khảo sát giai đoạn đầu — không phản ánh kiến trúc phần cứng/phần mềm chốt hiện tại.**

Thư mục này lưu giữ các tài liệu khảo sát đề tài, bản nháp thiết kế ban đầu, nhật ký kiểm thử độ trễ sơ khai và tài liệu kiến trúc trước đợt tái cấu trúc `v1.0` / `v3.8.0` (`agyhw12`–`agyhw14`, `agyclean15`) nhằm phục vụ tra cứu lịch sử tiến hóa đồ án.

## Không dùng các tài liệu trong thư mục này làm nguồn tham chiếu vận hành

Các nội dung trong thư mục này có thể chứa những thông tin **đã lỗi thời hoặc đã bị loại bỏ**:
- Đường dẫn mã nguồn cũ (`simulator/server.py`, `simulator/auth_3layer.py`, `android_app/`, `mobile_app/`).
- Các thiết bị phần cứng cũ đã loại bỏ khỏi hợp đồng chốt (**không** dùng breadboard trắng, quạt `fan`, điều hòa `ac`, hay hồng ngoại `IR / VS1838B`).
- Các endpoint thu giọng nói / đăng ký giọng nói trang đầu cũ đã bị gỡ bỏ (`HTTP 410`).

## Danh mục tệp lưu trữ

| Tệp lưu trữ | Nội dung lịch sử | Tài liệu hiện hành thay thế |
| :--- | :--- | :--- |
| `SESSION_RBAC_20261112.md` | Ghi chép thiết kế phiên đăng nhập & RBAC đợt đầu (`simulator/auth/tier_permissions.py`) | [`../kien_truc/KIEN_TRUC_HE_THONG.md`](../kien_truc/KIEN_TRUC_HE_THONG.md), [`../TIER_PERMISSIONS.md`](../TIER_PERMISSIONS.md) |
| `TAI_LIEU_XAC_THUC_3_LOP_PHAN_CAP_LINK_MOI_VA_GIONG_NOI.md` | Đặc tả xác thực 3 lớp kèm thu âm giọng gốc trang đầu giai đoạn đầu | [`../kien_truc/KIEN_TRUC_HE_THONG.md`](../kien_truc/KIEN_TRUC_HE_THONG.md), [`../../USER_GUIDE.md`](../../USER_GUIDE.md) |
| `HUONG_DAN_CHONG_TRAN_NGU_CANH_VA_ANH_HUONG_CHEO.md` | Ghi chú công cụ ngữ cảnh AI giai đoạn `simulator/` | [`../kien_truc/REPO_MAP.md`](../kien_truc/REPO_MAP.md) |
| `de_tai_do_an_cu_nhan_1_nguoi_bach_khoa.md`, `de_tai_smart_home_voice_ai_jev_1_nguoi.md`, `de_tai_smart_home_voice_ai_v2.md` | Bản đề xuất & khảo sát hướng đề tài ban đầu | [`../../README.md`](../../README.md), [`../../KE_HOACH_DO_AN_TOT_NGHIEP.md`](../../KE_HOACH_DO_AN_TOT_NGHIEP.md) |
| `hardware_ai_simulation_pcb_benchmark.md` | Khảo sát mô phỏng phần cứng & benchmark PCB sơ khai | [`../phan_cung/TONG_QUAN_PHAN_CUNG_VA_IN_3D.md`](../phan_cung/TONG_QUAN_PHAN_CUNG_VA_IN_3D.md) |
| `KE_HOACH_VOICE_ID_ANTI_SPOOFING.md` | Kế hoạch nghiên cứu nhận dạng người nói & chống giả mạo giai đoạn đầu | [`../kien_truc/KIEN_TRUC_HE_THONG.md`](../kien_truc/KIEN_TRUC_HE_THONG.md) |
| `quy_tac_va_khung_do_an_tot_nghiep_bach_khoa.md` | Quy cách khung báo cáo tham khảo | Thư mục báo cáo `docs/bao_cao/` |
| `latency_results_20261019_*.json` | 5 bản ghi đo độ trễ thử nghiệm ngày 19/10/2026 | Bộ kiểm thử tự động trong `tests/` |
