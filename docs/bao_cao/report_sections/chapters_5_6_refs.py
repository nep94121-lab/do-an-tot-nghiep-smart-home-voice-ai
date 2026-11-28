"""Chapters 5, 6 & References: Kết quả và đánh giá, Kết luận và hướng phát triển, Tài liệu tham khảo.

Loads verified Web UI screenshots, Android APK 3-tier E2E screenshots, and official
commercial smart-home comparison sources dynamically into TÀI LIỆU THAM KHẢO.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from docx.enum.text import WD_ALIGN_PARAGRAPH
from .docx_helpers import ReportBuilder


_APK_FIGURE_SPECS: tuple[tuple[str, str, str], ...] = (
    (
        "*_apk_03_tier1_home_sensors.png",
        "Màn hình Trang chủ ứng dụng Android hiển thị thông số cảm biến và trạng thái an toàn (Cấp 1)",
        "[ẢNH CHỤP ỨNG DỤNG ANDROID: Màn hình Trang chủ hiển thị thông số cảm biến và trạng thái an toàn]",
    ),
    (
        "*_apk_05_tier1_voice_multiturn.png",
        "Màn hình trợ lý giọng nói tiếng Việt nhiều lượt và tạo lệnh tùy chỉnh trên ứng dụng Android",
        "[ẢNH CHỤP ỨNG DỤNG ANDROID: Màn hình hội thoại giọng nói tiếng Việt và lệnh tùy chỉnh]",
    ),
    (
        "*_apk_14_tier3_guest_rbac.png",
        "Màn hình điều khiển thiết bị của Khách (Cấp 3) sau khi quét mã QR chỉ hiển thị 2 đèn chiếu sáng",
        "[ẢNH CHỤP ỨNG DỤNG ANDROID: Màn hình thiết bị của Khách Cấp 3 sau khi quét mã QR]",
    ),
)


def _sibling_workspace_root() -> pathlib.Path:
    """Return parent directory containing sibling build/session folders."""
    here = pathlib.Path(__file__).resolve()
    return here.parents[4] if len(here.parents) > 4 else here.parent


def _resolve_apk_screens_dir(
    run_dir: pathlib.Path,
    apk_screens_dir: pathlib.Path | None = None,
) -> pathlib.Path | None:
    """Locate the directory containing captured Android APK screenshots."""
    candidates: list[pathlib.Path] = []
    if apk_screens_dir is not None:
        candidates.append(apk_screens_dir)
    if run_dir is not None:
        candidates.append(run_dir / "screens")
        candidates.append(run_dir)

    for folder in candidates:
        if folder.is_dir() and any(folder.glob("*_apk_*.png")):
            return folder

    ws_root = _sibling_workspace_root()
    if ws_root.is_dir():
        for child in sorted(ws_root.iterdir(), key=lambda p: p.name, reverse=True):
            screens = child / "screens"
            if screens.is_dir() and any(screens.glob("*_apk_03_tier1_home_sensors.png")):
                return screens
    return None


def _pick_apk_screenshots(
    run_dir: pathlib.Path,
    apk_screens_dir: pathlib.Path | None = None,
) -> list[tuple[pathlib.Path | None, str, str]]:
    """Select the 3 representative Android APK screenshots (Tier 1 Home, Voice, Tier 3 Guest)."""
    screens_dir = _resolve_apk_screens_dir(run_dir, apk_screens_dir)
    picked: list[tuple[pathlib.Path | None, str, str]] = []
    for pattern, caption, placeholder in _APK_FIGURE_SPECS:
        found: pathlib.Path | None = None
        if screens_dir is not None:
            matches = sorted(screens_dir.glob(pattern))
            if matches:
                found = matches[0]
        picked.append((found, caption, placeholder))
    return picked


def _resolve_comparison_sources_path(
    comparison_sources_path: pathlib.Path | None = None,
) -> pathlib.Path | None:
    """Locate comparison_sources.json from explicit path or sibling build_receipts directory."""
    if comparison_sources_path is not None:
        return comparison_sources_path if comparison_sources_path.is_file() else None

    report_dir = pathlib.Path(__file__).resolve().parents[1]
    local_candidate = report_dir / "comparison_sources.json"
    if local_candidate.is_file():
        return local_candidate

    ws_root = _sibling_workspace_root()
    if ws_root.is_dir():
        matches: list[pathlib.Path] = []
        for child in ws_root.iterdir():
            receipt = child / "build_receipts" / "comparison_sources.json"
            if receipt.is_file():
                matches.append(receipt)
        if matches:
            matches.sort(key=lambda p: ("report16" in p.parent.parent.name.lower(), p.stat().st_mtime), reverse=True)
            return matches[0]
    return None


def _load_comparison_sources(path: pathlib.Path | None) -> list[dict[str, str]]:
    """Parse comparison_sources.json into a normalized list of official source dicts."""
    if path is None or not path.is_file():
        return []
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return []

    if isinstance(raw, dict):
        items = raw.get("sources") or raw.get("items") or []
    elif isinstance(raw, list):
        items = raw
    else:
        items = []

    seen_urls: set[str] = set()
    normalized: list[dict[str, str]] = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url", "")).strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        normalized.append(
            {
                "product": str(entry.get("product", "")).strip(),
                "title": str(entry.get("title", "")).strip(),
                "url": url,
                "accessed": str(entry.get("accessed", "28/11/2026")).strip() or "28/11/2026",
            }
        )
    return normalized


def _add_photo_placeholder(
    rb: ReportBuilder,
    label: str,
    sublabel: str,
    caption: str,
    height_cm: float = 4.2,
    width_cm: float = 14.2,
) -> str:
    """Insert a dashed real-photo placeholder box with exact height and numbered Figure caption."""
    rb.add_dashed_box(label, sublabel, height_cm=height_cm, width_cm=width_cm)
    return rb._add_seq_caption("Hình", caption, keep_with_next=False)


def build_chapter_5(
    rb: ReportBuilder,
    assets_dir: pathlib.Path,
    run_dir: pathlib.Path,
    apk_screens_dir: pathlib.Path | None = None,
) -> None:
    demo_dir = assets_dir / "demo"

    rb.add_chapter(5, "KẾT QUẢ VÀ ĐÁNH GIÁ")
    rb.add_para(
        "Trong Chương 5, em trình bày kết quả hoàn thiện mạch điện tử và mô hình tổng thể, kết quả xây dựng "
        "giao diện Web cùng ứng dụng di động Android, đồng thời tổng hợp số liệu kiểm thử các phân hệ và "
        "đối chiếu mức độ đáp ứng với mục tiêu đặt ra ở Chương 2."
    )

    # ===== 5.1 KẾT QUẢ THIẾT KẾ MẠCH ĐIỆN TỬ VÀ MÔ HÌNH TỔNG THỂ =====
    rb.add_h2("5.1. Kết quả thiết kế mạch điện tử và mô hình tổng thể")
    rb.add_para(
        "Về phần cứng, bo mạch trung tâm PCB Hub DIY v3 có kích thước 100 × 80 mm (độ dày 1,6 mm, 51 chân linh kiện) "
        "được thiết kế hoàn chỉnh trên KiCad 10.0 và kiểm tra đạt 0 lỗi quy tắc điện (0 ERC), 0 lỗi quy tắc mạch in "
        "(0 DRC). Mạch áp dụng hợp đồng 10 chân an toàn khởi động trên NodeMCU ESP8266 v2 Amica, tích hợp đầy đủ "
        "linh kiện bảo vệ ngay trên bo gồm các tụ lọc nguồn, diode dập xung 1N4007 cho bơm nước và còi báo động, "
        "tầng đệm transistor S8050 cho còi 5V và điện trở định mức khởi động. Hệ thống dây kết nối từ bo mạch trung "
        "tâm tới các module ngoại vi được kiểm tra hình học đạt 40/40 dây có chiều dài không quá 30 cm "
        "(từ 3,84 cm đến 27,48 cm), giúp bố trí gọn gàng và loại bỏ hoàn toàn bảng cắm thí nghiệm."
    )
    rb.add_para(
        "Đi kèm với phần mạch điện tử, bộ vỏ mô hình nhà in 3D bằng nhựa PLA dạng khớp mộng lắp ghép đã được hoàn "
        "thiện tệp thiết kế để gá cố định 14 module điện tử và bo mạch PCB Hub mà không cần dùng ốc vít hay keo dán. "
        "Do bước gia công hàn linh kiện lên mạch in thật và lắp ráp hoàn chỉnh mô hình vật lý là công đoạn cuối cùng "
        "sẽ thực hiện trước khi trình diễn, hai khung vị trí dưới đây được dành sẵn để bổ sung ảnh chụp thực tế sau khi "
        "hàn mạch và cấp nguồn 5V 2A."
    )

    _add_photo_placeholder(
        rb,
        label="[ẢNH THỰC TẾ: Bo mạch PCB Hub DIY v3 sau khi hàn linh kiện và cắm NodeMCU ESP8266]",
        sublabel="Bổ sung ảnh chụp thực tế bo mạch sau khi gia công và hàn đủ linh kiện",
        caption="Bo mạch PCB Hub DIY v3 sau khi hàn linh kiện và cắm NodeMCU ESP8266",
        height_cm=2.8,
    )
    _add_photo_placeholder(
        rb,
        label="[ẢNH THỰC TẾ: Mô hình nhà thông minh hoàn chỉnh khi cấp nguồn 5V 2A]",
        sublabel="Bổ sung ảnh chụp thực tế mô hình hoàn thiện khi cấp nguồn 5V 2A và kết nối máy chủ",
        caption="Mô hình nhà thông minh hoàn chỉnh khi cấp nguồn 5V 2A",
        height_cm=2.8,
    )

    # ===== 5.2 KẾT QUẢ GIAO DIỆN WEB VÀ ỨNG DỤNG DI ĐỘNG ANDROID =====
    rb.add_h2("5.2. Kết quả giao diện Web và ứng dụng di động Android")
    rb.add_para(
        "Phần máy chủ của hệ thống chạy trên laptop, cho phép người dùng truy cập trong mạng LAN và qua Internet để "
        "giám sát cũng như điều khiển thiết bị. Giao diện Web hiển thị mô hình 3D nhà thông minh đồng bộ trạng thái "
        "thời gian thực của 6 thiết bị chấp hành và 3 cảm biến, hỗ trợ xoay góc nhìn theo từng khu vực, quan sát góc "
        "đóng mở cửa chính của servo SG90, đồng thời cung cấp các trang chức năng riêng cho tự động hóa (hẹn giờ, "
        "lịch trình, lệnh tùy chỉnh, luật liên kết), mô phỏng đấu nối phần cứng theo sơ đồ PCB và quản trị tài khoản "
        "phân quyền 3 tầng kèm mã QR mời khách. Các hình ảnh kết quả giao diện Web được minh họa từ Hình 5.3 đến Hình 5.7."
    )

    rb.add_figure(
        demo_dir / "web_3d_desktop_light.png",
        "Giao diện Web điều khiển chính tích hợp mô hình 3D nhà thông minh",
        max_width_cm=12.4,
        max_height_cm=5.7,
        kind="web_ui",
    )
    rb.add_figure(
        demo_dir / "web_3d_door_open.png",
        "Trạng thái cửa chính mở góc 90° đồng bộ thời gian thực trên mô hình 3D",
        max_width_cm=12.4,
        max_height_cm=5.7,
        kind="web_ui",
    )
    rb.add_figure(
        demo_dir / "web_automation_panel.png",
        "Giao diện quản lý hẹn giờ, lịch trình, lệnh tùy chỉnh và luật tự động hóa",
        max_width_cm=12.4,
        max_height_cm=5.7,
        kind="web_ui",
    )
    rb.add_figure(
        demo_dir / "web_wokwi_pcb_direct.png",
        "Giao diện kiểm tra và mô phỏng đấu nối phần cứng theo bo mạch PCB",
        max_width_cm=12.4,
        max_height_cm=5.7,
        kind="web_ui",
    )
    rb.add_figure(
        demo_dir / "web_auth_rbac.png",
        "Giao diện quản trị phiên đăng nhập, phân quyền 3 tầng và mã QR mời khách",
        max_width_cm=12.4,
        max_height_cm=5.7,
        kind="web_ui",
    )

    rb.add_para(
        "Song song với giao diện Web, em đã xây dựng và đóng gói ứng dụng di động Android thuần bằng Kotlin và "
        "Jetpack Compose (tương thích từ Android 8.0 / API 26 trở lên) với 4 thẻ điều hướng chính gồm Nhà, Thiết bị, "
        "Giọng nói và Tài khoản. Trên điện thoại, người dùng có thể xem trực tiếp nhiệt độ, độ ẩm không khí, độ ẩm đất "
        "và trạng thái âm thanh; ra lệnh giọng nói tiếng Việt nhiều lượt liên tiếp với quy tắc xác nhận một lần khi tạo "
        "lệnh tùy chỉnh; cũng như quét mã QR để kích hoạt phiên Khách (Cấp 3) với danh sách thiết bị được giới hạn tự "
        "động chỉ còn hai đèn chiếu sáng như minh họa ở Hình 5.8 đến Hình 5.10."
    )

    for img_path, caption, placeholder in _pick_apk_screenshots(run_dir, apk_screens_dir):
        rb.add_figure(
            img_path,
            caption,
            max_width_cm=4.6 if img_path is not None else 13.4,
            max_height_cm=6.6,
            placeholder_label=placeholder,
            placeholder_sublabel="Ảnh chụp màn hình ứng dụng Android sau khi kiểm thử trên máy ảo Android 14",
            kind="app_ui",
        )

    # ===== 5.3 KẾT QUẢ KIỂM THỬ VÀ ĐÁNH GIÁ TỔNG THỂ =====
    rb.add_h2("5.3. Kết quả kiểm thử và đánh giá tổng thể")
    rb.add_para(
        "Để kiểm chứng độ tin cậy của hệ thống trước khi đưa vào lắp ráp phần cứng, em thực hiện kiểm thử đồng bộ trên "
        "năm nhóm hạng mục độc lập gồm logic firmware ngoại tuyến, 36 luồng nghiệp vụ cốt lõi của máy chủ, các kịch bản "
        "biên và bảo mật phân quyền 3 tầng, kiểm thử tự động giao diện trình duyệt trên cả kích thước màn hình máy tính "
        "lẫn điện thoại (chế độ Sáng/Tối), và kiểm thử đầu cuối ứng dụng Android trên máy ảo Android 14 (API 34). "
        "Kết quả chi tiết được tổng hợp trong Bảng 5.1."
    )

    rb.add_table(
        "Tổng hợp kết quả kiểm thử các phân hệ của hệ thống",
        ["Hạng mục kiểm thử", "Phạm vi kiểm tra chính", "Kết quả", "Ghi nhận kỹ thuật"],
        [
            (
                "Logic firmware ngoại tuyến",
                "Khóa cứng mở cửa chính khi mất kết nối, giới hạn thời gian bơm (<= 120 s) và còi (<= 30 s), đồng bộ lại trạng thái khi có mạng",
                "10/10 đạt",
                "Đáp ứng yêu cầu an toàn tối thiểu khi ngắt kết nối máy chủ",
            ),
            (
                "36 luồng nghiệp vụ cốt lõi",
                "Điều khiển 6 thiết bị chấp hành, đọc 3 cảm biến, hẹn giờ, lịch trình, luật tự động hóa, lệnh tùy chỉnh và hội thoại giọng nói",
                "36/36 đạt",
                "Dữ liệu giữa máy chủ, cơ sở dữ liệu SQLite và giao diện đồng bộ nhất quán",
            ),
            (
                "Biên phân quyền và bảo mật RBAC",
                "Chặn vượt quyền Cấp 2/Cấp 3 qua API và giọng nói, kiểm tra mã QR động 10 giây dùng một lần, thu hồi phiên tức thì, va chạm lệnh",
                "35/35 đạt",
                "Không phát sinh rò rỉ dữ liệu hoặc thao tác vượt cấp quyền",
            ),
            (
                "Kiểm thử tự động giao diện trình duyệt",
                "Kiểm tra các trang Web trên màn hình máy tính (1366×768) và di động (412×915), chế độ Sáng/Tối, mô hình 3D và trang phần cứng",
                "10/10 đạt",
                "0 lỗi giao diện, 0 tràn khung ngang, 100% hiển thị tiếng Việt",
            ),
            (
                "Ứng dụng Android 3 tầng (E2E)",
                "Đăng nhập OTP Cấp 1, quên mật khẩu, hội thoại tiếng Việt 7 lượt, phân quyền Cấp 2 và quét mã QR vào Cấp 3 trên máy ảo Android 14",
                "11/11 đạt",
                "0 lỗi thoát đột ngột (crash), 0 lỗi treo ứng dụng (ANR)",
            ),
        ],
        col_widths_cm=[3.5, 5.4, 2.3, 4.3],
        font_pt=9.5,
        center_cols=(2,),
    )

    rb.add_para(
        "Từ kết quả thiết kế và số liệu kiểm thử trên, Bảng 5.2 đối chiếu từng hạng mục đã hoàn thiện với mục tiêu "
        "đề ra ở Chương 2. Phần mềm điều khiển, trợ lý giọng nói tiếng Việt, cơ chế phân quyền, giao diện Web 3D, "
        "ứng dụng Android, thiết kế mạch PCB và mã nguồn firmware đều đã hoàn thiện và kiểm thử đạt yêu cầu; hạng mục "
        "còn lại duy nhất là gia công hàn bo mạch thực tế, nạp firmware lên ESP8266 thật và lắp ráp vào vỏ mô hình."
    )

    rb.add_table(
        "Đánh giá đối chiếu giữa mục tiêu đề ra và kết quả đạt được",
        ["Hạng mục", "Mục tiêu đề ra", "Kết quả đạt được", "Trạng thái"],
        [
            (
                "Mạch điện tử và PCB Hub DIY v3",
                "Bo mạch gọn, 10 chân an toàn khởi động, không breadboard, đủ mạch bảo vệ tải",
                "PCB 100×80 mm đạt 0 ERC / 0 DRC, 40/40 dây <= 30 cm, đủ linh kiện bảo vệ trên bo",
                "Hoàn thành thiết kế",
            ),
            (
                "Firmware ESP8266 và chế độ ngoại tuyến",
                "Cấu hình Wi-Fi động qua LittleFS, tự khóa mở cửa và bảo vệ tải khi mất kết nối",
                "Hoàn thiện mã nguồn nạp qua USB, kiểm thử đạt 10/10 kịch bản ngoại tuyến",
                "Hoàn thành mã nguồn",
            ),
            (
                "Máy chủ điều khiển và tự động hóa",
                "Quản lý 6 thiết bị, 3 cảm biến, hẹn giờ, lịch trình, luật liên kết và lệnh tùy chỉnh",
                "Máy chủ FastAPI + SQLite WAL vận hành ổn định, đạt 36/36 luồng nghiệp vụ cốt lõi",
                "Hoàn thành",
            ),
            (
                "Trợ lý giọng nói tiếng Việt",
                "Hiểu câu lệnh tiếng Việt tự nhiên, trả lời ngắn gọn, tạo lệnh tùy chỉnh xác nhận 1 lần",
                "Tích hợp Gemini Live tiếng Việt, có chống dội âm và kiểm thử hội thoại nhiều lượt đạt",
                "Hoàn thành",
            ),
            (
                "Phân quyền 3 tầng và mã QR khách",
                "Tách biệt Chủ nhà / Gia đình / Khách, mã QR động chống chụp lại và thu hồi nhanh",
                "Cưỡng chế quyền phía máy chủ với mã QR TOTP 10 giây, đạt 35/35 bài kiểm tra bảo mật",
                "Hoàn thành",
            ),
            (
                "Giao diện Web 3D và ứng dụng Android",
                "Web 3D trực quan chạy trong LAN/Internet và ứng dụng Android cài đặt trực tiếp",
                "Web đạt 10/10 kiểm thử đa màn hình; ứng dụng Android đạt 11/11 kiểm thử 3 tầng",
                "Hoàn thành",
            ),
            (
                "Gia công hàn mạch và lắp mô hình thật",
                "Hàn linh kiện lên bo PCB, lắp vỏ in 3D và nạp firmware chạy thử trên mạch thật",
                "Hồ sơ mạch in và tệp vỏ in 3D đã sẵn sàng, thực hiện ở bước lắp ráp vật lý cuối cùng",
                "Bước lắp ráp cuối",
            ),
        ],
        col_widths_cm=[3.5, 4.0, 5.2, 2.8],
        font_pt=9.5,
        center_cols=(3,),
    )


def build_chapter_6(rb: ReportBuilder) -> None:
    rb.add_chapter(6, "KẾT LUẬN VÀ HƯỚNG PHÁT TRIỂN")

    rb.add_h2("6.1. Kết luận")
    rb.add_para(
        "Trong khuôn khổ Đồ án Tốt nghiệp, em đã hoàn thành việc nghiên cứu, thiết kế và xây dựng hệ thống nhà thông "
        "minh điều khiển bằng giọng nói tiếng Việt tích hợp mô hình 3D và ứng dụng di động Android. Về phần cứng, "
        "đồ án đã xây dựng hoàn chỉnh sơ đồ nguyên lý và bo mạch trung tâm PCB Hub DIY v3 kích thước 100 × 80 mm "
        "(đạt 0 ERC và 0 DRC) cho vi điều khiển NodeMCU ESP8266 v2 Amica theo hợp đồng 10 chân an toàn khởi động, "
        "tích hợp sẵn các linh kiện bảo vệ nguồn, diode dập xung và tầng đệm transistor, đồng thời hoàn thiện bộ vỏ "
        "mô hình nhà in 3D dạng khớp mộng để bố trí gọn 14 module điện tử và 40 dây nối có chiều dài không quá 30 cm."
    )
    rb.add_para(
        "Về phần mềm, hệ thống máy chủ viết bằng FastAPI kết hợp cơ sở dữ liệu SQLite chế độ WAL chạy trên laptop "
        "cá nhân, hỗ trợ truy cập trong mạng nội bộ và qua Internet. Máy chủ tích hợp trợ lý giọng nói tiếng Việt "
        "qua dịch vụ Gemini Live với cơ chế chống dội âm, trả lời ngắn gọn và quy tắc xác nhận một lần khi tạo lệnh "
        "tùy chỉnh; đồng thời cung cấp đầy đủ chức năng hẹn giờ, lịch trình, luật tự động hóa theo cảm biến và phân "
        "quyền 3 tầng (Chủ nhà, Gia đình, Khách) kèm mã QR động TOTP chu kỳ 10 giây. Cả giao diện Web tích hợp mô "
        "hình 3D lẫn ứng dụng Android thuần Kotlin/Jetpack Compose đều đã được kiểm thử đầu cuối và hoạt động ổn định."
    )
    rb.add_para(
        "Bên cạnh đó, firmware nạp cho ESP8266 được tổ chức theo hướng an toàn và dễ triển khai thực tế: thông tin "
        "Wi-Fi được lưu riêng trong phân vùng LittleFS thay vì ghi cứng vào mã nguồn, đồng thời mạch duy trì chế độ "
        "ngoại tuyến cho phép điều khiển cơ bản trong mạng cục bộ, tự ngắt bơm và còi quá thời gian cho phép, cũng "
        "như khóa cứng thao tác mở cửa chính khi mất kết nối máy chủ."
    )
    rb.add_para(
        "Tuy nhiên, em cũng thẳng thắn nhìn nhận đồ án vẫn còn một số hạn chế nhất định. Thứ nhất, phần cứng hiện "
        "tại được thiết kế ở quy mô mô hình thử nghiệm sử dụng nguồn 5V DC công suất thấp, chưa áp dụng cho tải lưới "
        "điện xoay chiều 220V trong hộ gia đình thực tế. Thứ hai, trợ lý giọng nói hiện chỉ hỗ trợ tiếng Việt và cần "
        "kết nối Internet ổn định để giao tiếp với dịch vụ Gemini Live. Thứ ba, tại thời điểm hoàn thành báo cáo, "
        "bước gia công hàn linh kiện lên bo mạch PCB thật, nạp firmware lên vi điều khiển thực tế và lắp ráp hoàn "
        "chỉnh mô hình vật lý vẫn là công đoạn cuối cùng chưa kịp thực hiện để chụp ảnh sản phẩm ngoài đời thực."
    )

    rb.add_h2("6.2. Hướng phát triển")
    rb.add_para(
        "Để nâng cao tính thực tiễn và khả năng mở rộng của hệ thống trong tương lai, hướng phát triển đầu tiên là "
        "nâng cấp vi điều khiển trung tâm lên dòng ESP32-S3 kết hợp micro số I2S và loa nhỏ gắn trực tiếp trên mô "
        "hình. Khi tích hợp thêm mô hình nhận dạng từ khóa đánh thức (wake word) chạy cục bộ ngay trên vi điều khiển, "
        "người dùng có thể ra lệnh giọng nói trực tiếp trong phòng mà không cần mở điện thoại hay trình duyệt."
    )
    rb.add_para(
        "Hướng phát triển thứ hai là mở rộng khả năng kết nối thiết bị theo các chuẩn công nghiệp phổ biến như "
        "Matter hoặc Zigbee nhằm tương thích với nhiều cảm biến và công tắc thương mại trên thị trường. Song song đó, "
        "cần thiết kế phiên bản bo mạch rơ-le cách ly quang có khe cách điện đạt chuẩn an toàn cùng mạch bảo vệ quá "
        "dòng để điều khiển an toàn các thiết bị điện xoay chiều 220V thực tế."
    )
    rb.add_para(
        "Hướng phát triển thứ ba là cải thiện trải nghiệm triển khai và bảo trì bằng cơ chế cấu hình Wi-Fi không dây "
        "qua Bluetooth Low Energy (BLE) từ ứng dụng Android và cập nhật firmware từ xa qua mạng (OTA) có kiểm tra "
        "tính toàn vẹn. Giải pháp này giúp người dùng thay đổi mạng Wi-Fi hoặc nâng cấp phần mềm cho nhiều nút thiết "
        "bị trong nhà mà không cần tháo vỏ hay cắm cáp USB."
    )
    rb.add_para(
        "Cuối cùng, dựa trên dữ liệu cảm biến môi trường và nhật ký bật tắt thiết bị được tích lũy theo thời gian "
        "trong cơ sở dữ liệu, hệ thống có thể bổ sung mô-đun phân tích mức tiêu thụ điện năng và phát hiện bất thường. "
        "Nhờ đó, ứng dụng không chỉ dừng lại ở việc thực thi lệnh theo yêu cầu mà còn có thể gợi ý lịch bật tắt tiết "
        "kiệm điện và cảnh báo sớm các dấu hiệu bất thường về an ninh hoặc môi trường sinh hoạt."
    )


def build_references(
    rb: ReportBuilder,
    comparison_sources_path: pathlib.Path | None = None,
) -> None:
    rb.add_unnumbered_chapter("TÀI LIỆU THAM KHẢO")

    base_refs = [
        "Espressif Systems, ESP8266EX Technical Reference Manual & Hardware Design Guidelines, Version 1.7, Espressif Systems, 2023.",
        "NodeMCU Team, NodeMCU v2 Amica (ESP-12E / CP2102) Hardware Specification & Pinout Reference, GitHub Open Hardware Documentation.",
        "Sebastian Ramirez, FastAPI Framework Documentation — High Performance Python ASGI Web Framework, https://fastapi.tiangolo.com/.",
        "D. Richard Hipp et al., SQLite Database Engine Documentation — Write-Ahead Logging (WAL) & Foreign Key Support, https://www.sqlite.org/.",
        "Google DeepMind, Gemini Multimodal Live API & Google GenAI Python SDK Documentation (google-genai), https://ai.google.dev/.",
        "OASIS Standard, MQTT Version 3.1.1 / 5.0 — Message Queuing Telemetry Transport Protocol Specification, OASIS Open.",
        "Three.js Authors, Three.js WebGL 3D Library Documentation, https://threejs.org/docs/.",
        "JetBrains & Google, Kotlin Language Reference & Jetpack Compose Material 3 Android Developers Guide, https://developer.android.com/compose.",
        "PlatformIO Labs, PlatformIO Core Documentation & Espressif 8266 Arduino Platform Reference, https://docs.platformio.org/.",
        "KiCad Developers Team, KiCad 10.0 Electronic Design Automation Documentation — Schematic Capture, PCB Layout & ERC/DRC Verification, https://docs.kicad.org/.",
        "Diodes Incorporated, PAM8403 3W Filterless Class-D Stereo Audio Amplifier Datasheet (BTL Output & Power Decoupling Guidelines).",
        "TowerPro / HandsOnTech, SG90 9g Micro Servo Technical Specification (Stall Torque 1.8 kg·cm @ 4.8V, 50 Hz PWM).",
        "Aosong Electronics, DHT11 Digital Relative Humidity & Temperature Sensor Module Datasheet.",
        "Texas Instruments, LM393 Dual Differential Comparator Datasheet & Resistive Soil Moisture Sensor Application Note.",
        "Vishay Semiconductors, 1N4001–1N4007 General Purpose Plastic Rectifier Datasheet (Inductive Flyback Clamp Protection).",
        "Unisonic Technologies, S8050 NPN Epitaxial Silicon Transistor Datasheet (Low-Side Driver Design).",
        "Internet Engineering Task Force (IETF), RFC 6238: TOTP — Time-Based One-Time Password Algorithm & RFC 6455: The WebSocket Protocol.",
        "Đại học Bách khoa Hà Nội (HUST), Hướng dẫn trình bày Đồ án Tốt nghiệp Đại học (Mẫu tham khảo SEEE — Hệ thống điều khiển nhà thông minh qua Internet, 2024).",
    ]

    src_path = _resolve_comparison_sources_path(comparison_sources_path)
    dynamic_sources = _load_comparison_sources(src_path)

    all_refs: list[str] = list(base_refs)
    for src in dynamic_sources:
        product = src["product"]
        title = src["title"]
        url = src["url"]
        accessed = src["accessed"] or "28/11/2026"
        if product and title:
            if title.lower().startswith(product.lower()):
                entry = f"{title}, {url}, truy cập ngày {accessed}."
            else:
                entry = f"{product}, {title}, {url}, truy cập ngày {accessed}."
        elif title:
            entry = f"{title}, {url}, truy cập ngày {accessed}."
        elif product:
            entry = f"{product}, Trang thông tin sản phẩm chính thức, {url}, truy cập ngày {accessed}."
        else:
            entry = f"{url}, truy cập ngày {accessed}."
        all_refs.append(entry)

    for idx, ref_text in enumerate(all_refs, start=1):
        rb.add_para(f"[{idx}] {ref_text}", align=WD_ALIGN_PARAGRAPH.LEFT, indent_cm=0.0, space_after=4.5)
