"""Front matter builder (Pages 1-11): Cover, Inner Cover (with real HUST logo),
Thesis Topic, Declaration, Acknowledgements, Abstract, TOC, Abbreviations,
List of Figures, List of Tables, and List of Code Listings.
"""

from __future__ import annotations

import pathlib

from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
from docx.shared import Cm, Pt

from .docx_helpers import (
    LISTING_SEQ_ID,
    ReportBuilder,
    set_cell_margins,
    set_footer_page_number,
    set_row_cant_split,
    set_run_font,
    set_section_page_border,
    set_section_page_numbering,
    set_table_borders,
)

THESIS_TITLE = (
    "THIẾT KẾ VÀ XÂY DỰNG HỆ THỐNG NHÀ THÔNG MINH "
    "ĐIỀU KHIỂN BẰNG GIỌNG NÓI AI TÍCH HỢP MÔ HÌNH 3D VÀ ỨNG DỤNG DI ĐỘNG"
)

DEFAULT_ASSETS_DIR = pathlib.Path(__file__).resolve().parent.parent / "assets"


def _add_cover_page(
    rb: ReportBuilder,
    logo_path: pathlib.Path,
    is_inner: bool = False,
) -> None:
    doc = rb.doc

    # School header (yellow highlighted for student confirmation)
    p_school = doc.add_paragraph()
    p_school.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_school.paragraph_format.first_line_indent = Cm(0)
    p_school.paragraph_format.space_before = Pt(4)
    p_school.paragraph_format.space_after = Pt(4)
    p_school.paragraph_format.line_spacing = 1.15
    r_sc = p_school.add_run("[ĐIỀN: ĐẠI HỌC BÁCH KHOA HÀ NỘI — cần xác nhận]")
    set_run_font(r_sc, size_pt=15, bold=True, highlight=WD_COLOR_INDEX.YELLOW)

    p_fac = doc.add_paragraph()
    p_fac.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_fac.paragraph_format.first_line_indent = Cm(0)
    p_fac.paragraph_format.space_before = Pt(0)
    p_fac.paragraph_format.space_after = Pt(10)
    p_fac.paragraph_format.line_spacing = 1.15
    r_fa = p_fac.add_run("[ĐIỀN: TRƯỜNG ĐIỆN - ĐIỆN TỬ / KHOA ...]")
    set_run_font(r_fa, size_pt=13, bold=True, highlight=WD_COLOR_INDEX.YELLOW)

    # Real official HUST emblem (preserves portrait aspect ratio)
    if logo_path.exists():
        rb.add_cover_logo(
            logo_path,
            max_height_cm=3.5,
            max_width_cm=3.8,
            label="Logo Đại học Bách khoa Hà Nội (HUST)",
        )
    else:
        raise FileNotFoundError(f"Không tìm thấy tệp biểu trưng HUST tại: {logo_path}")

    # Thesis banner (Bold 25pt per HUST template)
    p_ban = doc.add_paragraph()
    p_ban.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_ban.paragraph_format.first_line_indent = Cm(0)
    p_ban.paragraph_format.space_before = Pt(18)
    p_ban.paragraph_format.space_after = Pt(12)
    p_ban.paragraph_format.line_spacing = 1.15
    r_ban = p_ban.add_run("ĐỒ ÁN TỐT NGHIỆP" if not is_inner else "ĐỒ ÁN TỐT NGHIỆP (BÌA PHỤ)")
    set_run_font(r_ban, size_pt=25 if not is_inner else 22, bold=True)

    # Thesis title
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.first_line_indent = Cm(0)
    p_title.paragraph_format.space_before = Pt(4)
    p_title.paragraph_format.space_after = Pt(16)
    p_title.paragraph_format.line_spacing = 1.15
    r_t = p_title.add_run(THESIS_TITLE)
    set_run_font(r_t, size_pt=20 if not is_inner else 19, bold=True)

    # Student Name (Bold 14pt per HUST template)
    p_sv = doc.add_paragraph()
    p_sv.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_sv.paragraph_format.first_line_indent = Cm(0)
    p_sv.paragraph_format.space_before = Pt(4)
    p_sv.paragraph_format.space_after = Pt(4)
    p_sv.paragraph_format.line_spacing = 1.15
    r_sv = p_sv.add_run("NGUYỄN TUẤN ANH")
    set_run_font(r_sv, size_pt=14, bold=True)

    # MSSV / Email (yellow)
    p_mail = doc.add_paragraph()
    p_mail.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_mail.paragraph_format.first_line_indent = Cm(0)
    p_mail.paragraph_format.space_before = Pt(0)
    p_mail.paragraph_format.space_after = Pt(6)
    p_mail.paragraph_format.line_spacing = 1.15
    r_m = p_mail.add_run("[ĐIỀN: MSSV / Email SV]")
    set_run_font(r_m, size_pt=13, bold=False, highlight=WD_COLOR_INDEX.YELLOW)

    # Program / Major (Bold 14pt, yellow)
    p_prog = doc.add_paragraph()
    p_prog.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_prog.paragraph_format.first_line_indent = Cm(0)
    p_prog.paragraph_format.space_before = Pt(0)
    p_prog.paragraph_format.space_after = Pt(22)
    p_prog.paragraph_format.line_spacing = 1.15
    r_p = p_prog.add_run("[ĐIỀN: Chương trình / Ngành đào tạo — Lớp ...]")
    set_run_font(r_p, size_pt=14, bold=True, highlight=WD_COLOR_INDEX.YELLOW)

    # Advisor & Faculty borderless 3-column block (matching HUST cover + signature line)
    tbl_info = doc.add_table(rows=2, cols=3)
    tbl_info.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_info.autofit = False
    set_table_borders(tbl_info, val="none", sz="0", color="FFFFFF")
    widths = [4.9, 6.4, 3.8]
    for r_idx in range(2):
        set_row_cant_split(tbl_info.rows[r_idx])
        for c_idx, w in enumerate(widths):
            cell = tbl_info.cell(r_idx, c_idx)
            cell.width = Cm(w)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
            set_cell_margins(cell, top=55, bottom=55, left=40, right=40)

    # Row 0: Giảng viên hướng dẫn
    p00 = tbl_info.cell(0, 0).paragraphs[0]
    p00.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p00.paragraph_format.first_line_indent = Cm(0)
    set_run_font(p00.add_run("Giảng viên hướng dẫn:"), size_pt=13, bold=True)

    p01 = tbl_info.cell(0, 1).paragraphs[0]
    p01.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p01.paragraph_format.first_line_indent = Cm(0)
    set_run_font(
        p01.add_run("[ĐIỀN: Học hàm, học vị & Họ tên GVHD]"),
        size_pt=13,
        bold=False,
        highlight=WD_COLOR_INDEX.YELLOW,
    )

    p02 = tbl_info.cell(0, 2).paragraphs[0]
    p02.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p02.paragraph_format.first_line_indent = Cm(0)
    set_run_font(p02.add_run("____________________"), size_pt=11)
    p02b = tbl_info.cell(0, 2).add_paragraph()
    p02b.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p02b.paragraph_format.first_line_indent = Cm(0)
    set_run_font(p02b.add_run("Chữ ký của GVHD"), size_pt=10, italic=True)

    # Row 1: Khoa
    p10 = tbl_info.cell(1, 0).paragraphs[0]
    p10.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p10.paragraph_format.first_line_indent = Cm(0)
    set_run_font(p10.add_run("KHOA / VIỆN:"), size_pt=13, bold=True)

    p11 = tbl_info.cell(1, 1).paragraphs[0]
    p11.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p11.paragraph_format.first_line_indent = Cm(0)
    set_run_font(
        p11.add_run("[ĐIỀN: Khoa / Viện]"),
        size_pt=13,
        bold=False,
        highlight=WD_COLOR_INDEX.YELLOW,
    )

    # Bottom city + date
    p_bot = doc.add_paragraph()
    p_bot.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_bot.paragraph_format.first_line_indent = Cm(0)
    p_bot.paragraph_format.space_before = Pt(76)
    p_bot.paragraph_format.space_after = Pt(0)
    p_bot.paragraph_format.line_spacing = 1.15
    set_run_font(p_bot.add_run("HÀ NỘI, "), size_pt=13, bold=True)
    set_run_font(p_bot.add_run("[ĐIỀN: THÁNG/NĂM]"), size_pt=13, bold=True, highlight=WD_COLOR_INDEX.YELLOW)


def _add_signature_block(rb: ReportBuilder, role_title: str, signer_name: str, highlight_name: bool = False) -> None:
    tbl = rb.doc.add_table(rows=1, cols=2)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    set_table_borders(tbl, val="none", sz="0", color="FFFFFF")
    tbl.cell(0, 0).width = Cm(8.0)
    tbl.cell(0, 1).width = Cm(7.5)
    set_row_cant_split(tbl.rows[0])

    c = tbl.cell(0, 1)
    p1 = c.paragraphs[0]
    p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p1.paragraph_format.first_line_indent = Cm(0)
    p1.paragraph_format.space_before = Pt(12)
    p1.paragraph_format.space_after = Pt(2)
    set_run_font(p1.add_run("Hà Nội, ngày "), size_pt=12, italic=True)
    set_run_font(p1.add_run("[ĐIỀN: ...]"), size_pt=12, italic=True, highlight=WD_COLOR_INDEX.YELLOW)

    p2 = c.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p2.paragraph_format.first_line_indent = Cm(0)
    p2.paragraph_format.space_after = Pt(2)
    set_run_font(p2.add_run(role_title), size_pt=13, bold=True)

    p3 = c.add_paragraph()
    p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p3.paragraph_format.first_line_indent = Cm(0)
    p3.paragraph_format.space_after = Pt(38)
    set_run_font(p3.add_run("(Ký và ghi rõ họ tên)"), size_pt=11, italic=True)

    p4 = c.add_paragraph()
    p4.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p4.paragraph_format.first_line_indent = Cm(0)
    set_run_font(
        p4.add_run(signer_name),
        size_pt=13,
        bold=True,
        highlight=WD_COLOR_INDEX.YELLOW if highlight_name else None,
    )


def build_front_matter(rb: ReportBuilder, assets_dir: pathlib.Path | None = None) -> None:
    resolved_assets = pathlib.Path(assets_dir) if assets_dir is not None else DEFAULT_ASSETS_DIR
    logo_path = resolved_assets / "logos" / "logo_hust.png"

    # ===== SECTION 1: BÌA CHÍNH & BÌA PHỤ (Double Border, No Page Number) =====
    sec1 = rb.doc.sections[0]
    set_section_page_border(sec1, double=True, color="000000")
    set_footer_page_number(sec1, align=WD_ALIGN_PARAGRAPH.CENTER, clear=True)

    # Page 1: Bìa chính
    _add_cover_page(rb, logo_path=logo_path, is_inner=False)
    rb.add_page_break()
    # Page 2: Bìa phụ
    _add_cover_page(rb, logo_path=logo_path, is_inner=True)

    # ===== SECTION 2: FRONT MATTER PAGES 3..11 (No Border, Roman Numerals i..ix) =====
    sec2 = rb.add_new_section()
    set_section_page_border(sec2, double=False)
    set_section_page_numbering(sec2, fmt="lowerRoman", start=1)
    set_footer_page_number(sec2, align=WD_ALIGN_PARAGRAPH.RIGHT, clear=False)

    # Page 3 (i): ĐỀ TÀI TỐT NGHIỆP
    rb.add_front_title("ĐỀ TÀI TỐT NGHIỆP", space_after=14)
    p_dt = rb.doc.add_paragraph()
    p_dt.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_dt.paragraph_format.first_line_indent = Cm(0)
    p_dt.paragraph_format.space_before = Pt(4)
    p_dt.paragraph_format.space_after = Pt(14)
    p_dt.paragraph_format.line_spacing = 1.25
    set_run_font(p_dt.add_run(THESIS_TITLE), size_pt=16, bold=True)

    rb.add_rich_para([
        ("Sinh viên thực hiện: ", True, False, None),
        ("NGUYỄN TUẤN ANH", True, False, None),
        (" — MSSV: ", False, False, None),
        ("[ĐIỀN: MSSV]", False, False, WD_COLOR_INDEX.YELLOW),
    ], indent_cm=0.5, space_after=4)
    rb.add_rich_para([
        ("Lớp / Ngành đào tạo: ", True, False, None),
        ("[ĐIỀN: Lớp / Chương trình đào tạo]", False, False, WD_COLOR_INDEX.YELLOW),
    ], indent_cm=0.5, space_after=4)
    rb.add_rich_para([
        ("Giảng viên hướng dẫn: ", True, False, None),
        ("[ĐIỀN: Học hàm, học vị & Họ tên GVHD]", False, False, WD_COLOR_INDEX.YELLOW),
    ], indent_cm=0.5, space_after=10)

    rb.add_para("Mục tiêu và nội dung nghiên cứu chính của đề tài:", bold=True, indent_cm=0.5, space_after=5)
    rb.add_para(
        "Đề tài thiết kế và xây dựng hệ thống nhà thông minh hoàn chỉnh từ mạch điện tử đến phần mềm điều "
        "khiển, hỗ trợ tương tác bằng giọng nói tiếng Việt song song với giao diện Web 3D và ứng dụng Android.",
        space_after=4,
    )
    rb.add_para(
        "Về phần cứng, em thiết kế sơ đồ nguyên lý và bo mạch PCB Hub trung tâm DIY v3 (1 lớp, 100 × 80 mm) "
        "dùng NodeMCU ESP8266 điều khiển 6 thiết bị chấp hành và đọc 3 cảm biến, tích hợp sẵn linh kiện lọc "
        "nguồn và bảo vệ trên mạch để thay thế breadboard, kèm khung vỏ mô hình dạng mô-đun in 3D gọn gàng.",
        space_after=4,
    )
    rb.add_para(
        "Về phần mềm, em phát triển máy chủ FastAPI kết hợp SQLite xử lý luồng âm thanh tiếng Việt thời gian "
        "thực cùng mô hình Gemini Live, hỗ trợ hẹn giờ, quy tắc tự động, dạy lệnh tùy chỉnh và phân quyền 3 "
        "tầng (Chủ nhà, Thành viên, Khách dùng mã QR động TOTP). Firmware ESP8266 nạp Wi-Fi qua USB và có cơ "
        "chế an toàn ngoại tuyến khóa mở cửa chính khi mất kết nối mạng.",
        space_after=4,
    )
    rb.add_para(
        "Về giao diện, em xây dựng trang Web 3D tương tác (Three.js), trang mô phỏng đấu nối phần cứng và ứng "
        "dụng di động Android (Kotlin) để theo dõi cảm biến, điều khiển thiết bị và hội thoại tiếng Việt.",
        space_after=4,
    )
    _add_signature_block(rb, "GIẢNG VIÊN HƯỚNG DẪN", "[ĐIỀN: Họ tên GVHD]", highlight_name=True)

    # Page 4 (ii): LỜI CAM ĐOAN
    rb.add_page_break()
    rb.add_front_title("LỜI CAM ĐOAN", space_after=14)
    rb.add_para(
        "Em xin cam đoan báo cáo Đồ án Tốt nghiệp với đề tài “Thiết kế và xây dựng hệ thống nhà thông minh "
        "điều khiển bằng giọng nói AI tích hợp mô hình 3D và ứng dụng di động” là kết quả quá trình tự nghiên "
        "cứu, thiết kế mạch điện tử, lập trình và thử nghiệm của bản thân em dưới sự hướng dẫn của Giảng viên "
        "hướng dẫn."
    )
    rb.add_para(
        "Các sơ đồ nguyên lý, bản vẽ mạch in PCB, mã nguồn máy chủ, firmware vi điều khiển, giao diện Web 3D, "
        "ứng dụng Android và các số liệu kiểm thử trình bày trong báo cáo đều được em thực hiện nghiêm túc, "
        "phản ánh đúng trạng thái hiện tại của hệ thống. Những tài liệu tham khảo, datasheet linh kiện và thư "
        "viện mã nguồn mở sử dụng trong đồ án đều được trích dẫn rõ ràng ở phần Tài liệu tham khảo."
    )
    rb.add_para(
        "Em xin chịu hoàn toàn trách nhiệm trước Nhà trường và Hội đồng chấm Đồ án Tốt nghiệp về tính trung "
        "thực của các nội dung đã trình bày."
    )
    _add_signature_block(rb, "SINH VIÊN THỰC HIỆN", "NGUYỄN TUẤN ANH", highlight_name=False)

    # Page 5 (iii): LỜI CẢM ƠN
    rb.add_page_break()
    rb.add_front_title("LỜI CẢM ƠN", space_after=14)
    rb.add_rich_para([
        ("Trước hết, em xin gửi lời cảm ơn chân thành tới ", False, False, None),
        ("[ĐIỀN: Học hàm, học vị & Họ tên GVHD]", True, False, WD_COLOR_INDEX.YELLOW),
        (", người đã tận tình hướng dẫn, góp ý cho em về phương án thiết kế mạch điện tử, cách tổ chức phần mềm "
         "cũng như cách trình bày báo cáo trong suốt thời gian em thực hiện Đồ án Tốt nghiệp.", False, False, None),
    ])
    rb.add_rich_para([
        ("Em xin bày tỏ lòng biết ơn tới các thầy cô thuộc ", False, False, None),
        ("[ĐIỀN: Khoa / Viện — Trường Điện - Điện tử, Đại học Bách khoa Hà Nội]", False, False, WD_COLOR_INDEX.YELLOW),
        (" đã giảng dạy và trang bị cho em nền tảng kiến thức về điện tử, vi điều khiển, mạng truyền thông và "
         "lập trình trong suốt những năm học vừa qua. Đó là cơ sở để em có thể kết nối phần cứng và phần mềm "
         "thành một hệ thống hoàn chỉnh.", False, False, None),
    ])
    rb.add_para(
        "Em cũng xin cảm ơn gia đình và bạn bè đã luôn động viên, hỗ trợ và dùng thử hệ thống để em kịp thời "
        "phát hiện, chỉnh sửa nhiều lỗi thực tế trong quá trình hoàn thiện giao diện và lệnh giọng nói tiếng Việt."
    )
    rb.add_para(
        "Do thời gian thực hiện và kinh nghiệm thực tế của em còn hạn chế, báo cáo khó tránh khỏi những thiếu "
        "sót. Em rất mong nhận được ý kiến nhận xét, đóng góp của quý thầy cô trong Hội đồng để em rút kinh "
        "nghiệm và hoàn thiện sản phẩm tốt hơn."
    )
    rb.add_para("Em xin chân thành cảm ơn!", align=WD_ALIGN_PARAGRAPH.RIGHT, indent_cm=0)

    # Page 6 (iv): TÓM TẮT NỘI DUNG ĐỒ ÁN
    rb.add_page_break()
    rb.add_front_title("TÓM TẮT NỘI DUNG ĐỒ ÁN", space_after=10)
    rb.add_para(
        "Báo cáo trình bày quá trình thiết kế và xây dựng hệ thống nhà thông minh điều khiển bằng giọng nói "
        "tiếng Việt, kết hợp mô hình nhà 3D trên Web và ứng dụng Android, giải quyết trọn vẹn từ mạch điện tử "
        "đến quy trình vận hành giọng nói, phân quyền và an toàn ngoại tuyến.",
        space_after=4,
    )
    rb.add_para(
        "Ở phần điện tử, NodeMCU ESP8266 v2 điều khiển 6 thiết bị chấp hành (2 đèn đấu Active-LOW tránh bật "
        "nhầm khi khởi động, cửa chính servo SG90, bơm 5V và mạch loa PAM8403 qua relay, còi 5V lái qua "
        "transistor S8050) cùng 3 cảm biến 3,3V (DHT11, độ ẩm đất YL-69/LM393, âm thanh KY-037). Toàn bộ linh "
        "kiện lọc nguồn và bảo vệ được tích hợp trên mạch in PCB Hub DIY v3 một lớp 100 × 80 mm (0 lỗi ERC, "
        "0 lỗi DRC trong KiCad), thay thế breadboard với dây nối dưới 30 cm. Khung vỏ mô hình cũng được thiết "
        "kế dạng mô-đun in 3D lắp ghép gọn gàng để cố định thiết bị khi trình diễn.",
        space_after=4,
    )
    rb.add_para(
        "Ở phần mềm, máy chủ FastAPI (Python) và SQLite chuẩn 3NF chế độ WAL thiết lập cầu nối âm thanh hai "
        "chiều qua WebSocket tới Gemini Live tiếng Việt kèm bộ lọc chống dội âm, 20 hàm công cụ, cơ chế xác "
        "nhận đúng một lần khi dạy câu lệnh tùy chỉnh cùng bộ xử lý hẹn giờ và quy tắc tự động. Hệ thống phân "
        "quyền 3 tầng (Chủ nhà, Thành viên, Khách dùng mã QR động TOTP 10 giây); firmware ESP8266 nạp Wi-Fi "
        "qua USB lưu vào LittleFS và có máy trạng thái ngoại tuyến khóa mở cửa chính khi mất kết nối máy chủ.",
        space_after=4,
    )
    rb.add_para(
        "Giao diện Web 3D (Three.js), trang mô phỏng mạch đấu nối và ứng dụng Android (Kotlin) đã hoàn thiện "
        "và vượt qua các kịch bản kiểm thử tự động. Bước tiếp theo để chạy thực nghiệm trên mô hình thật là "
        "gia công, hàn lắp bo mạch PCB Hub DIY v3 và cấp nguồn 5V 2A cho hệ thống.",
        space_after=4,
    )
    _add_signature_block(rb, "SINH VIÊN THỰC HIỆN", "NGUYỄN TUẤN ANH", highlight_name=False)

    # Page 7 (v): MỤC LỤC
    rb.add_page_break()
    rb.add_front_title("MỤC LỤC", space_after=10)
    rb.add_toc_field(
        'TOC \\o "1-3" \\h \\z \\u',
        "[Mục lục tự động]",
    )

    # Page 8 (vi): DANH MỤC TỪ VIẾT TẮT (tightened to fit cleanly on 1 page)
    rb.add_page_break()
    rb.add_front_title("DANH MỤC TỪ VIẾT TẮT", space_after=8)
    abbr_rows = [
        ("3NF", "Third Normal Form", "Dạng chuẩn thứ ba trong CSDL quan hệ"),
        ("ADC", "Analog-to-Digital Converter", "Bộ chuyển đổi tương tự sang số"),
        ("API", "Application Programming Interface", "Giao diện lập trình ứng dụng"),
        ("APK", "Android Package Kit", "Gói cài đặt ứng dụng Android"),
        ("BJT", "Bipolar Junction Transistor", "Transistor lưỡng cực (Q1 S8050)"),
        ("BOM", "Bill of Materials", "Bảng định mức linh kiện vật tư"),
        ("BTL", "Bridge-Tied Load", "Mạch khuếch đại tải cầu (PAM8403)"),
        ("DRC", "Design Rule Check", "Kiểm tra quy tắc thiết kế mạch in PCB"),
        ("ERC", "Electrical Rules Check", "Kiểm tra quy tắc điện sơ đồ nguyên lý"),
        ("ERD", "Entity-Relationship Diagram", "Sơ đồ thực thể liên kết CSDL"),
        ("FSM", "Finite State Machine", "Máy trạng thái hữu hạn ngoại tuyến"),
        ("GPIO", "General-Purpose Input/Output", "Chân vào/ra số trên vi điều khiển"),
        ("IoT", "Internet of Things", "Internet vạn vật"),
        ("MQTT", "Message Queuing Telemetry Transport", "Giao thức truyền tin Publish/Subscribe"),
        ("PCB", "Printed Circuit Board", "Bo mạch in điện tử"),
        ("PCM", "Pulse-Code Modulation", "Điều chế xung mã âm thanh số"),
        ("PWM", "Pulse-Width Modulation", "Điều chế độ rộng xung (Servo SG90)"),
        ("QR", "Quick Response Code", "Mã phản hồi nhanh cấp quyền khách"),
        ("RBAC", "Role-Based Access Control", "Kiểm soát truy cập theo 3 vai trò"),
        ("REST", "Representational State Transfer", "Kiến trúc giao diện dịch vụ Web"),
        ("SSE", "Server-Sent Events", "Kênh đẩy sự kiện từ máy chủ"),
        ("TOTP", "Time-Based One-Time Password", "Mã xác thực một lần theo thời gian"),
        ("UART", "Universal Asynchronous Receiver-Transmitter", "Giao tiếp nối tiếp không đồng bộ"),
        ("VAD", "Voice Activity Detection", "Bộ phát hiện hoạt động tiếng nói"),
        ("WAL", "Write-Ahead Logging", "Cơ chế ghi nhật ký trước của SQLite"),
        ("WS", "WebSocket", "Kết nối song công thời gian thực"),
    ]
    rb.add_table(
        caption=None,
        headers=["Từ viết tắt", "Tên đầy đủ tiếng Anh", "Ý nghĩa tiếng Việt"],
        rows=abbr_rows,
        col_widths_cm=[1.9, 5.8, 7.8],
        font_pt=9.5,
        center_cols=(0,),
    )

    # Page 9 (vii): DANH MỤC HÌNH VẼ
    rb.add_page_break()
    rb.add_front_title("DANH MỤC HÌNH VẼ", space_after=10)
    rb.add_toc_field(
        'TOC \\h \\z \\c "Hình"',
        "[Danh mục hình vẽ tự động]",
    )

    # Page 10 (viii): DANH MỤC BẢNG BIỂU
    rb.add_page_break()
    rb.add_front_title("DANH MỤC BẢNG BIỂU", space_after=10)
    rb.add_toc_field(
        'TOC \\h \\z \\c "Bảng"',
        "[Danh mục bảng biểu tự động]",
    )

    # Page 11 (ix): DANH MỤC ĐOẠN MÃ
    rb.add_page_break()
    rb.add_front_title("DANH MỤC ĐOẠN MÃ", space_after=10)
    rb.add_toc_field(
        f'TOC \\h \\z \\c "{LISTING_SEQ_ID}"',
        "[Danh mục đoạn mã tự động]",
    )
