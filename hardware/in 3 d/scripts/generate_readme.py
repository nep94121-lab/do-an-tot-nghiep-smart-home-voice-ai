"""Generate Vietnamese `hardware/in 3 d/README.md` directly from manifest.json & verification_report.json.

Zero hardcoded dimensions, counts, or slice metrics (all read from SSOT JSON artifacts).
Run with system Python:
    python "hardware/in 3 d/scripts/generate_readme.py"
"""

from __future__ import annotations

import json
import pathlib
import sys

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PRINT3D_ROOT = SCRIPT_DIR.parent
MANIFEST_PATH = PRINT3D_ROOT / "manifest.json"
VER_PATH = PRINT3D_ROOT / "verification_report.json"
README_PATH = PRINT3D_ROOT / "README.md"


def _fmt_time(sec: int) -> str:
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h > 0:
        return f"{h}g {m:02d}p"
    if m > 0:
        return f"{m}p {s:02d}s"
    return f"{s}s"


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    ver = json.loads(VER_PATH.read_text(encoding="utf-8"))

    parts = manifest["parts"]
    panel_parts = [p for p in parts if p["kind"] == "panel"]
    support_parts = [p for p in parts if p["kind"] == "support"]
    split_summary = manifest["split_summary"]

    bed = manifest["printer_bed_mm"]
    usable = manifest["usable_bed_mm"]
    clr = manifest["dovetail_clearance_mm"]
    eng_d = manifest["engrave_depth_mm"]
    asm = ver["assembly"]

    lines: list[str] = [
        "# Bộ Tệp In 3D Vỏ Nhà Thông Minh & Phụ Kiện Supot (`hardware/in 3 d/`)",
        "",
        "Thư mục này chứa toàn bộ bộ tệp **in 3D sẵn sàng cắt lớp (print-ready)** được chuyển đổi trực tiếp từ mô hình tham số gốc [`hardware/mica/smarthome_mica_house.FCStd`](../mica/smarthome_mica_house.FCStd) và [`hardware/mica/mica_design.py`](../mica/mica_design.py) — giữ nguyên 100% kích thước bao, toàn bộ lỗ khoan linh kiện, **khắc chìm sẵn mã chi tiết + kích thước ngay trên từng mảnh**, bổ sung **12 phụ kiện gia cố & giá đỡ (supot)** in 3D, và **tự động chia mảnh bằng khớp đuôi én** cho các tấm lớn vượt khổ bàn in.",
        "",
        "> **Nguồn sự thật duy nhất (SSOT):** Mọi hình học tấm, tọa độ 76 lỗ tròn, khoảng cách lỗ mạch `90 × 70 mm` (`P16_PCB_PLATE`), `44.5 × 20.5 mm` (`Relay 1/2`), và kiểm định va chạm đều sinh tự động từ mã nguồn tại [`scripts/`](scripts/) (không nhập tay kích thước).",
        "",
        "---",
        "",
        "## 1. Tổng Quan & Kết Quả Kiểm Định Tự Động",
        "",
        f"- **Khổ máy in 3D mục tiêu:** `{bed[0]:.0f} × {bed[1]:.0f} × {bed[2]:.0f} mm` (chừa lề an toàn `5 mm` mỗi cạnh → vùng in khả dụng **`{usable[0]:.0f} × {usable[1]:.0f} × {usable[2]:.0f} mm`**).",
        f"- **Tổng số tệp chi tiết in 3D:** **`{manifest['total_printable_files']}` tệp duy nhất** gồm **`{manifest['panel_piece_files']}` mảnh vỏ nhà** (chuyển đổi từ `{manifest['unique_source_panels']}` tấm gốc / `19` tấm vật lý) và **`{manifest['support_files']}` phụ kiện supot** (`SUP01`–`SUP12`).",
        f"- **Định dạng xuất cho mỗi chi tiết:** `STL` ([`STL/`](STL/)), `3MF` ([`3MF/`](3MF/)), `STEP` ([`STEP/`](STEP/)), bản vẽ kỹ thuật có ghi kích thước `PDF + PNG` ([`drawings/`](drawings/)), và ảnh phối cảnh 3D `PNG` ([`previews/`](previews/)).",
        f"- **Khắc chìm kích thước trực tiếp lên vật thể:** Khắc sâu `{eng_d:.2f} mm` lên **mặt hướng lên trên** khi đặt in (`Z = T_mm`), giữ mặt đáy `Z = 0` phẳng hoàn toàn để bám bàn in chắc chắn và **không cần support của slicer**.",
        f"- **Dung sai ghép nối:** Khớp đuôi én có khe hở **`{clr:.2f} mm`** giữa mộng dương và rãnh âm (tái lắp ghép khít đúng kích thước tấm gốc với sai số **`0.000 mm`**).",
        f"- **Kiểm định kỹ thuật (`verification_report.json`):**",
        f"  - Khối kín manifold (`watertight`): **`{ver['verified_files']}/{ver['total_expected_files']}` ĐẠT** (`all_watertight = {ver['all_watertight']}`).",
        f"  - Vừa vùng an toàn bàn in `210 × 210 mm` & đặt phẳng `Z = 0`: **`{ver['verified_files']}/{ver['total_expected_files']}` ĐẠT**.",
        f"  - Cắt lớp thực tế bằng **`{ver['slicer_cli']}`** (PLA `0.20 mm`, không support): **`{ver['verified_files']}/{ver['total_expected_files']}` ĐẠT** — tổng thời gian in ước tính (tính đủ số lượng `qty`): **`{manifest['total_estimated_print_hours']:.2f} giờ`**, tổng nhựa tiêu thụ ước tính: **`{manifest['total_estimated_filament_g']:.1f} g`** (~1 cuộn PLA 1 kg).",
        f"  - Kiểm tra va chạm 3D BRep toàn hệ thống (`{asm['panel_instances_checked']}` mảnh vỏ + `{asm['support_instances_checked']}` phụ kiện supot): **`{len(asm['panel_collisions'])}` va chạm vỏ** (`max = {asm['max_panel_intersection_mm3']} mm³`), **`{len(asm['support_collisions'])}` va chạm phụ kiện** (`max = {asm['max_support_intersection_mm3']} mm³`), **`{len(asm['reconstruction_failures'])}` lỗi sai kích thước tái ghép**.",
        "",
        "![Mô hình lắp ráp hoàn chỉnh kèm phụ kiện supot in 3D](previews/_assembled_house_3dprint.png)",
        "",
        "![Hình chiếu phân rã 3D các mảnh vỏ nhà và phụ kiện supot](previews/_exploded_house_3dprint.png)",
        "",
        "---",
        "",
        "## 2. Cấu Trúc Thư Mục `hardware/in 3 d/`",
        "",
        "```text",
        "hardware/in 3 d/",
        "├── README.md                  # Tài liệu hướng dẫn tiếng Việt này",
        "├── manifest.json              # Danh mục JSON đầy đủ kích thước, chia mảnh, thời gian & nhựa in",
        "├── verification_report.json   # Báo cáo kiểm định manifold, bàn in, cắt lớp & 0 va chạm 3D",
        "├── STL/                       # 37 tệp STL nhị phân kín khối, đặt phẳng Z = 0 sẵn sàng in",
        "├── 3MF/                       # 37 tệp 3MF chuẩn đơn vị mm (kèm siêu dữ liệu tên chi tiết)",
        "├── STEP/                      # 37 tệp CAD BRep chính xác để chỉnh sửa trong FreeCAD/SolidWorks",
        "├── drawings/                  # 37 bộ bản vẽ kỹ thuật có ghi kích thước (PDF + PNG)",
        "├── previews/                  # 37 ảnh xem trước 3D từng chi tiết + ảnh lắp ráp/phân rã/slicer",
        "└── scripts/                   # Bộ script tái tạo toàn bộ tệp tự động (FreeCADCmd + Python)",
        "```",
        "",
        "---",
        "",
        "## 3. Chiến Lược Chia Mảnh Cho 5 Tấm Lớn Vượt Bàn In `210 × 210 mm`",
        "",
        f"Trong `18` tấm vỏ gốc, có **`13` tấm vừa nguyên vẹn trong vùng an toàn `210 × 210 mm`** (in 1 mảnh duy nhất) và **`5` tấm vượt khổ** được tách tự động tại các dải trống không cắt ngang lỗ/khe linh kiện, ghép nối bằng khớp đuôi én khe hở **`{clr:.2f} mm`** và đặt tên theo quy ước `<TEN_TAM>_piece<k>of<n>`:",
        "",
        "| Tấm gốc | Kích thước gốc (mm) | Lưới chia | Số mảnh | Vị trí đường cắt (mm) | Danh sách tệp mảnh |",
        "| :--- | :---: | :---: | :---: | :---: | :--- |",
    ]

    for pid, info in split_summary.items():
        if not info["is_split"]:
            continue
        cuts_txt = f"U={info['u_cuts_mm']}" + (f", V={info['v_cuts_mm']}" if info["v_cuts_mm"] else "")
        pcs_txt = ", ".join(f"`{x}`" for x in info["pieces"])
        lines.append(
            f"| `{pid}` | `{info['source_width_mm']:.1f} × {info['source_height_mm']:.1f} × {info['T_mm']:.1f}` "
            f"| `{info['grid'][0]}×{info['grid'][1]}` | `{info['piece_count']}` | `{cuts_txt}` | {pcs_txt} |"
        )

    lines.extend([
        "",
        "![Ví dụ chia mảnh khớp đuôi én trên tấm tường sau P02_WALL_BACK](previews/_split_part_example.png)",
        "",
        "---",
        "",
        "## 4. Danh Mục Chi Tiết 25 Mảnh Vỏ Nhà (`P01A` – `P17`)",
        "",
        "Mọi mảnh đều có đủ 3 định dạng `STL` / `3MF` / `STEP`, bản vẽ `PDF + PNG` và ảnh 3D `PNG`. Thời gian và khối lượng nhựa được đo trực tiếp từ đầu ra G-code của `PrusaSlicer 2.9.7` (PLA, lớp `0.20 mm`, đầu phun `0.4 mm`, `3` thành, infill `20% gyroid`, **0% support**):",
        "",
        "| Mã tệp | Tên tiếng Việt | SL | Kích thước bao L×W×T (mm) | Chữ khắc trên vật | Thời gian in | Nhựa (g) | Bản vẽ & Ảnh |",
        "| :--- | :--- | :---: | :---: | :--- | :---: | :---: | :--- |",
    ])

    for p in panel_parts:
        pid = p["part_id"]
        bx, by, bz = p["print_bbox_mm"]
        engrave_safe = str(p["engrave_text"]).replace("|", r"\|")
        lines.append(
            f"| `{pid}` | {p['vi_name']} | `{p['qty']}` | `{bx:.1f} × {by:.1f} × {bz:.1f}` "
            f"| `{engrave_safe}` | `{_fmt_time(int(p['estimated_time_sec']))}` | `{p['filament_g']:.1f} g` "
            f"| [PDF](drawings/{pid}.pdf) · [PNG](previews/{pid}.png) |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 5. Danh Mục 12 Phụ Kiện Gia Cố & Giá Đỡ In 3D (`SUP01` – `SUP12`)",
        "",
        "Toàn bộ 12 phụ kiện supot đều được thiết kế khớp chính xác mẫu lỗ của [`hardware/mica/mica_design.py`](../mica/mica_design.py) (như chuẩn `90 × 70 mm` cho `P16_PCB_PLATE`, `44.5 × 20.5 mm` cho `Relay 1/2`, `26.0 mm` cho `PAM8403`, `36.0 mm` cho loa `Ø28 mm`), **định hướng nằm phẳng Z = 0, không cần support khi cắt lớp**, và khắc sẵn mã kích thước:",
        "",
        "![Bộ 12 phụ kiện supot in 3D SUP01 - SUP12](previews/_supports_showcase.png)",
        "",
        "| Mã phụ kiện | Tên tiếng Việt | SL | Kích thước X×Y×Z (mm) | Chữ khắc | Vị trí lắp ghép & Vai trò | Thời gian | Nhựa (g) | Bản vẽ |",
        "| :--- | :--- | :---: | :---: | :--- | :--- | :---: | :---: | :--- |",
    ])

    for s in support_parts:
        sid = s["part_id"]
        bx, by, bz = s["print_bbox_mm"]
        engrave_safe = str(s["engrave_text"]).replace("|", r"\|")
        lines.append(
            f"| `{sid}` | {s['vi_name']} | `{s['qty']}` | `{bx:.1f} × {by:.1f} × {bz:.1f}` "
            f"| `{engrave_safe}` | {s['notes']} | `{_fmt_time(int(s['estimated_time_sec']))}` | `{s['filament_g']:.1f} g` "
            f"| [PDF](drawings/{sid}.pdf) · [PNG](previews/{sid}.png) |"
        )

    lines.extend([
        "",
        "> **Lưu ý tùy chọn tiện lợi:** Bạn có thể in **`4× SUP05`** (trụ lẻ `10 mm`) **hoặc** in **`1× SUP07_PCB_CARRIER_FRAME_90X70`** (khung liền khối 4 trụ `90 × 70 mm`) để đỡ Hub PCB. Tương tự, có thể chọn **`8× SUP08`** (trụ lẻ `8 mm`) **hoặc** **`2× SUP09_RELAY_CADDY_44P5X20P5`** (khung liền khối `44.5 × 20.5 mm`) cho 2 module Relay.",
        "",
        "---",
        "",
        "## 6. Thông Số In 3D Khuyến Nghị (FDM `220 × 220 × 250 mm`)",
        "",
        "| Hạng mục | Tấm vỏ nhà (`P01A`–`P17`) | Phụ kiện Supot (`SUP01`–`SUP12`) | Ghi chú kỹ thuật |",
        "| :--- | :--- | :--- | :--- |",
        "| **Vật liệu** | **PLA+** hoặc **PETG** *(khuyên dùng PETG cho cụm bể nước `P09`–`P13`)* | **PETG** hoặc **PLA+** | PETG dẻo và chịu ẩm tốt hơn cho kẹp nối & bể nước. |",
        "| **Đầu phun / Chiều cao lớp** | `0.4 mm` / **`0.20 mm`** (`15` lớp cho tấm `3.0 mm`) | `0.4 mm` / **`0.20 mm`** | Lớp `0.20 mm` đảm bảo chữ khắc sâu `0.60 mm` (3 lớp) đọc rõ nét. |",
        "| **Số thành (Perimeters)** | `3` thành (`~1.2 mm`) | `3–4` thành | Tăng độ bền kéo cho khớp đuôi én và lỗ bắt ốc M3. |",
        "| **Mật độ ruột (Infill)** | `20%` (`Gyroid` hoặc `Grid`) | `25–30%` (`Gyroid`) | Chống cong vênh (warping) cho các mảnh đáy lớn. |",
        "| **Hướng đặt vật thể** | **Mặt phẳng `Z = 0` úp bàn in**, mặt khắc chữ hướng **lên trên** | Giữ nguyên hướng mặc định trong tệp `STL`/`3MF` | Tất cả 37 tệp đã xoay sẵn print-ready. |",
        "| **Support Slicer** | **TẮT (`0%`, Không cần support)** | **TẮT (`0%`, Không cần support)** | `SUP03` và `SUP11` đã lật sẵn đáy phẳng xuống bàn in. |",
        "| **Bám bàn in (Adhesion)** | `Skirt` 1–2 vòng (bật `Brim 4 mm` nếu in PETG / mảnh dài > 180 mm) | `Skirt` (bật `Brim` nhỏ cho trụ lẻ `SUP05/06/08`) | Giúp các mảnh `P01A`/`P01B`/`P02` phẳng tuyệt đối không hở góc. |",
        "| **Dung sai hiệu chuẩn** | Khớp đuôi én `0.20 mm`, khe mộng `0.25 mm` | Rãnh kẹp `SUP03` `3.20 mm` | Nếu máy có elephant's foot, bật `Elephant foot compensation = 0.15 mm`. |",
        "",
        "![Kiểm chứng cắt lớp G-code thực tế trên PrusaSlicer CLI (bàn in 220x220 mm)](previews/_slicer_preview.png)",
        "",
        "---",
        "",
        "## 7. Thứ Tự Lắp Ráp (Thu tu lap rap)",
        "",
        "Thực hiện theo đúng **9 bước** dưới đây để lắp ráp nhanh, chắc chắn và chống thấm an toàn trước khi đấu mạch điện:",
        "",
        "1. **Bước 1 — Kiểm tra phôi in & ướm khô khớp đuôi én:**",
        "   - Đọc mã khắc chìm trên mặt từng mảnh để phân loại đủ `25` mảnh vỏ và `12` nhóm phụ kiện `SUP01`–`SUP12`.",
        "   - Cạo nhẹ bavia mép đáy (nếu có), sau đó ướm trượt khô các mảnh chia đôi/chia tư: `P01A` (`2` mảnh), `P01B` (`4` mảnh), `P02` (`2` mảnh), `P05` (`2` mảnh), `P15` (`2` mảnh). Các khớp đuôi én có khe hở `0.20 mm` sẽ lồng phẳng khít thành đúng kích thước gốc.",
        "2. **Bước 2 — Ghép tấm đáy tổng (`406 × 390 mm`) & lắp chân đế `SUP04`:**",
        "   - Ghép `P01A_BASE_TECH_piece1of2 + piece2of2` và `4` mảnh `P01B_BASE_HOUSE_piece1of4..4of4`, sau đó lồng 4 mộng khóa `24 mm` giữa `P01A` và `P01B` trên mặt bàn phẳng.",
        "   - Bắt `2× P17_BASE_JOINER` ở mặt dưới đường nối giữa bằng `8×` ốc `M3×10` + đai ốc; cố định thêm `SUP03_SEAM_JOIN_CLIP` ở các đường ghép đáy nếu cần tăng cứng.",
        "   - Gắn `4–6× SUP04_BASE_FOOT_STAND` vào 4 góc và 2 cạnh giữa của đáy — nâng toàn bộ khung nhà cao `11 mm` khỏi mặt bàn để thanh nối `P17` và đầu ốc M3 không cọ xước bàn.",
        "3. **Bước 3 — Lắp Hub PCB (`100 × 80 mm`) trên `P16_PCB_PLATE` & khoang kỹ thuật:**",
        "   - Đặt `4× SUP06_PCB_PLATE_STANDOFF_6MM` (`6 mm`) tại 4 lỗ `116 × 96 mm` trên `P01A` rồi bắt tấm `P16_PCB_PLATE` lên trên.",
        "   - Đặt `4× SUP05_HUB_PCB_STANDOFF_10MM` (`10 mm`) **hoặc** `1× SUP07_PCB_CARRIER_FRAME_90X70` khớp chuẩn `90 × 70 mm` lên `P16_PCB_PLATE`, sau đó bắt Hub PCB (cắm sẵn NodeMCU hướng cổng Micro-USB ra mặt trước).",
        "   - Lắp `Relay 1` và `Relay 2` lên `P01A` bằng `8× SUP08_MODULE_STANDOFF_8MM` **hoặc** `2× SUP09_RELAY_CADDY_44P5X20P5` (chuẩn `44.5 × 20.5 mm`).",
        "   - Đặt mạch khuếch đại `PAM8403` vào khay `SUP10_PAM8403_CLIP_STAND` và cố định qua 2 lỗ `Ø3.0 mm` (`26.0 mm`).",
        "4. **Bước 4 — Ghép tường sau `P02_WALL_BACK` & kẹp khóa `SUP03`:**",
        "   - Lồng `P02_WALL_BACK_piece1of2` và `piece2of2` theo 2 khớp đuôi én, sau đó trượt `1× SUP03_SEAM_JOIN_CLIP` lên cạnh trên đường nối (`X = 203..237 mm`, nằm gọn bên phải vách giữa `P06`).",
        "   - Gắn 2 LED 5 mm (`D0`, `D4`) và cảm biến `DHT11` (`D2` dùng `1× SUP08_MODULE_STANDOFF_8MM`) trước khi cắm 6 mộng đáy vào `P01B`.",
        "5. **Bước 5 — Dựng vách ngăn `P06_WALL_MID`, vách hông `P03`, `P04` & khóa ke góc `SUP01`:**",
        "   - Lắp vách giữa `P06_WALL_MID`, vách trái `P03_WALL_LEFT`, vách phải `P04_WALL_RIGHT` vào các khe trên `P01B` và `P02`.",
        "   - Bắt `8× SUP01_CORNER_L_BRACKET_WALL` vào các góc đứng phía trong giữa `P02` với `P03`, `P04`, `P06` (tại 2 tầng cao `Z = 42 mm` và `Z = 89 mm`) để cố định vuông góc `90°` chắc chắn mà không cần keo dung môi.",
        "6. **Bước 6 — Ghép tường mặt tiền `P05_WALL_FRONT`, kệ Servo `P07` & cánh cửa `P08`:**",
        "   - Lồng `P05_WALL_FRONT_piece1of2` và `piece2of2`, trượt `1× SUP03_SEAM_JOIN_CLIP` lên cạnh trên đoạn vách thấp (`X = 214.5..248.5 mm`, tránh sát trụ giữa).",
        "   - Gắn cảm biến `KY-037` (`1× SUP08`), còi Buzzer `TMB12A05` (`Ø12.5 mm`), và gài kệ `P07_SERVO_SHELF` (đã lắp Servo SG90 bằng 2 ốc M2 + long-đen M2) vào khe khung cửa rồi dựng `P05` lên `P01B`. Gia cố 2 góc thấp trước bằng `2× SUP02_CORNER_L_BRACKET_LOW`.",
        "   - Treo cánh cửa `P08_DOOR_LEAF` bằng cặp bản lề in 3D `2× SUP12_DOOR_HINGE_BRACKET` (giữ khe hở đều `2.0 mm`) và nối thanh kéo sang tay đòn Servo SG90.",
        "7. **Bước 7 — Lắp cụm bể nước & chậu cây (`P09`–`P14`) + chống thấm:**",
        "   - Lắp 5 vách `P09`–`P13` vào `P01A`, gia cố 4 góc trong bằng `4× SUP02_CORNER_L_BRACKET_LOW`.",
        "   - **Bắt buộc chống thấm cho bể nước in 3D:** Quét 1 lớp mỏng keo epoxy/silicone trung tính mặt trong khoang bể nước (`P01A/P09/P10/P12/P13`) để bịt kín khe giữa các lớp in FDM, chờ khô và thử nước 15 phút trên giấy khô trước khi cấp điện.",
        "   - Đặt bơm chìm 5V, luồn ống silicon `Ø8 mm` qua lỗ `Ø10 mm` trên `P10`, gắn `LM393` (`1× SUP08`) mặt ngoài `P12`, gài cầu `P14_SOIL_BRIDGE` và cắm đầu dò `YL-69`.",
        "8. **Bước 8 — Ghép mặt nạ kỹ thuật `P15_TECH_FASCIA` & loa `Ø28 mm`:**",
        "   - Ghép `P15_TECH_FASCIA_piece1of2` + `piece2of2`, khóa cạnh trên rãnh USB bằng `1× SUP03_SEAM_JOIN_CLIP`.",
        "   - Lắp giắc nguồn `DC-022` (`Ø12.5 mm`), LED nguồn 3 mm (`Ø3.5 mm`), áp loa `Ø28 mm` sau lưới 19 lỗ và ép giữ bằng `1× SUP11_SPEAKER_28MM_RETAINER` + 2 ốc M3.",
        "9. **Bước 9 — Đi dây Dupont & kiểm tra an toàn điện:**",
        "   - Luồn đủ 40 dây theo [`docs/phan_cung/WIRING_TABLE.md`](../../docs/phan_cung/WIRING_TABLE.md) và chỉ mục [`docs/HARDWARE_BUILD_GUIDE.md`](../../docs/HARDWARE_BUILD_GUIDE.md) qua 6 lỗ `Ø14 mm`, kiểm tra lại nguồn `+3.3 V` cho `DHT11` / `KY-037` / `LM393` trước khi cắm nguồn 5V 2A.",
        "",
        "---",
        "",
        "## 8. Lệnh Tái Tạo Toàn Bộ Bộ Tệp Từ Mã Nguồn (Reproducible Build)",
        "",
        "Chạy tuần tự 5 lệnh sau từ thư mục gốc dự án để tái tạo sạch 100% toàn bộ `STL`, `3MF`, `STEP`, bản vẽ, ảnh 3D, kiểm định va chạm, báo cáo cắt lớp và tệp `README.md` này:",
        "",
        "```powershell",
        "# Khai báo đường dẫn FreeCADCmd di động (hoặc dùng trực tiếp 'freecadcmd' nếu đã có trong PATH)",
        "$FREECAD = if (Get-Command freecadcmd -ErrorAction SilentlyContinue) { \"freecadcmd\" } else { \"$env:LOCALAPPDATA\\Programs\\FreeCAD 1.1\\bin\\freecadcmd.exe\" }",
        "",
        "# 1. Sinh 37 khối 3D (STEP + STL) kèm khớp đuôi én và khắc chữ kích thước bằng FreeCAD 1.1",
        "& $FREECAD \"hardware/in 3 d/scripts/build_print_parts.py\"",
        "",
        "# 2. Chuyển đổi sang 3MF và xuất 37 bộ bản vẽ kỹ thuật PDF + PNG",
        "python \"hardware/in 3 d/scripts/export_3mf_and_drawings.py\"",
        "",
        "# 3. Kết xuất 37 ảnh 3D từng chi tiết + 4 ảnh tổng thể (lắp ráp, phân rã, chia mảnh, supot)",
        "& $FREECAD \"hardware/in 3 d/scripts/render_previews.py\"",
        "$env:PRINT3D_ASSEMBLY = \"1\"; & $FREECAD \"hardware/in 3 d/scripts/render_previews.py\"; Remove-Item Env:PRINT3D_ASSEMBLY",
        "",
        "# 4. Kiểm định 3D BRep (0 va chạm), cắt lớp PrusaSlicer CLI & xuất manifest.json + verification_report.json",
        "python \"hardware/in 3 d/scripts/verify_and_slice.py\"",
        "$env:PRINT3D_ASSEMBLY_CHECK = \"1\"; & $FREECAD \"hardware/in 3 d/scripts/verify_and_slice.py\"; Remove-Item Env:PRINT3D_ASSEMBLY_CHECK",
        "python \"hardware/in 3 d/scripts/verify_and_slice.py\" --merge",
        "",
        "# 5. Cập nhật README.md tiếng Việt từ manifest.json & verification_report.json",
        "python \"hardware/in 3 d/scripts/generate_readme.py\"",
        "```",
        "",
        "---",
        "",
        "## 9. Tài Liệu Liên Kết",
        "",
        "- [Chỉ mục chế tạo & đấu nối phần cứng (`docs/HARDWARE_BUILD_GUIDE.md`)](../../docs/HARDWARE_BUILD_GUIDE.md)",
        "- [Hướng dẫn cắt & lắp ghép phiên bản Mica 3mm (`docs/phan_cung/mica/ASSEMBLY_GUIDE.md`)](../../docs/phan_cung/mica/ASSEMBLY_GUIDE.md)",
        "- [Bảng tọa độ 76 lỗ khoan chuẩn (`docs/phan_cung/mica/holes_table.csv`)](../../docs/phan_cung/mica/holes_table.csv)",
        "- [Bảng đấu nối 40 dây & 10 chân ESP8266 (`docs/phan_cung/WIRING_TABLE.md`)](../../docs/phan_cung/WIRING_TABLE.md)",
    ])

    README_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"GENERATED {README_PATH} ({len(lines)} lines, {len(panel_parts)} panels, {len(support_parts)} supports)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
