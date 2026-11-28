"""Front matter builder (Pages 1-10): Cover, Inner Cover, Thesis Topic, Declaration,
Acknowledgements, Abstract, TOC, Abbreviations, List of Figures, List of Tables.
"""

from __future__ import annotations

from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt, RGBColor

from .docx_helpers import (
    ReportBuilder,
    set_cell_margins,
    set_cell_shading,
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


def _add_cover_page(rb: ReportBuilder, is_inner: bool = False) -> None:
    doc = rb.doc

    # School header (yellow highlighted per Q1)
    p_school = doc.add_paragraph()
    p_school.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_school.paragraph_format.first_line_indent = Cm(0)
    p_school.paragraph_format.space_before = Pt(6)
    p_school.paragraph_format.space_after = Pt(4)
    p_school.paragraph_format.line_spacing = 1.15
    r_sc = p_school.add_run("[ĐIỀN: ĐẠI HỌC BÁCH KHOA HÀ NỘI — cần xác nhận]")
    set_run_font(r_sc, size_pt=15, bold=True, highlight=WD_COLOR_INDEX.YELLOW)

    p_fac = doc.add_paragraph()
    p_fac.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_fac.paragraph_format.first_line_indent = Cm(0)
    p_fac.paragraph_format.space_before = Pt(0)
    p_fac.paragraph_format.space_after = Pt(12)
    p_fac.paragraph_format.line_spacing = 1.15
    r_fa = p_fac.add_run("[ĐIỀN: TRƯỜNG ĐIỆN - ĐIỆN TỬ / KHOA ...]")
    set_run_font(r_fa, size_pt=13, bold=True, highlight=WD_COLOR_INDEX.YELLOW)

    # Logo dashed placeholder box
    tbl_logo = doc.add_table(rows=1, cols=1)
    tbl_logo.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_logo.autofit = False
    set_table_borders(tbl_logo, val="dashed", sz="10", color="64748B")
    c_logo = tbl_logo.cell(0, 0)
    c_logo.width = Cm(4.2)
    c_logo.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    set_cell_shading(c_logo, "FFFBEB")
    trPr = tbl_logo.rows[0]._tr.get_or_add_trPr()
    trPr.append(parse_xml(f'<w:trHeight {nsdecls("w")} w:val="{int(3.6 * 567)}" w:hRule="exact"/>'))
    p_l = c_logo.paragraphs[0]
    p_l.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_l.paragraph_format.first_line_indent = Cm(0)
    p_l.paragraph_format.space_before = Pt(0)
    p_l.paragraph_format.space_after = Pt(0)
    r_l = p_l.add_run("[ĐIỀN: LOGO TRƯỜNG]")
    set_run_font(r_l, size_pt=11, bold=True, highlight=WD_COLOR_INDEX.YELLOW)

    # Thesis banner (Bold 25pt per HUST template)
    p_ban = doc.add_paragraph()
    p_ban.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_ban.paragraph_format.first_line_indent = Cm(0)
    p_ban.paragraph_format.space_before = Pt(22)
    p_ban.paragraph_format.space_after = Pt(14)
    p_ban.paragraph_format.line_spacing = 1.15
    r_ban = p_ban.add_run("ĐỒ ÁN TỐT NGHIỆP" if not is_inner else "ĐỒ ÁN TỐT NGHIỆP (BÌA PHỤ)")
    set_run_font(r_ban, size_pt=25 if not is_inner else 22, bold=True)

    # Thesis title (Bold 23pt per HUST template, compact line spacing to fit cleanly on 1 page)
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.first_line_indent = Cm(0)
    p_title.paragraph_format.space_before = Pt(4)
    p_title.paragraph_format.space_after = Pt(18)
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
    p_prog.paragraph_format.space_after = Pt(24)
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
            set_cell_margins(cell, top=60, bottom=60, left=40, right=40)

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
    p_bot.paragraph_format.space_before = Pt(46)
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
    p1.paragraph_format.space_before = Pt(14)
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
    p3.paragraph_format.space_after = Pt(42)
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


def build_front_matter(rb: ReportBuilder) -> None:
    # ===== SECTION 1: BÌA CHÍNH & BÌA PHỤ (Double Border, No Page Number) =====
    sec1 = rb.doc.sections[0]
    set_section_page_border(sec1, double=True, color="000000")
    set_footer_page_number(sec1, align=WD_ALIGN_PARAGRAPH.CENTER, clear=True)

    # Page 1: Bìa chính
    _add_cover_page(rb, is_inner=False)
    rb.add_page_break()
    # Page 2: Bìa phụ
    _add_cover_page(rb, is_inner=True)

    # ===== SECTION 2: FRONT MATTER PAGES 3..10 (No Border, Roman Numerals i, ii, ...) =====
    sec2 = rb.add_new_section()
    set_section_page_border(sec2, double=False)
    set_section_page_numbering(sec2, fmt="lowerRoman", start=1)
    set_footer_page_number(sec2, align=WD_ALIGN_PARAGRAPH.RIGHT, clear=False)

    # Page 3 (i): ĐỀ TÀI TỐT NGHIỆP
    rb.add_front_title("ĐỀ TÀI TỐT NGHIỆP", space_after=18)
    p_dt = rb.doc.add_paragraph()
    p_dt.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_dt.paragraph_format.first_line_indent = Cm(0)
    p_dt.paragraph_format.space_before = Pt(6)
    p_dt.paragraph_format.space_after = Pt(18)
    p_dt.paragraph_format.line_spacing = 1.25
    set_run_font(p_dt.add_run(THESIS_TITLE), size_pt=17, bold=True)

    rb.add_rich_para([
        ("Sinh viên thực hiện: ", True, False, None),
        ("NGUYỄN TUẤN ANH", True, False, None),
        (" — MSSV: ", False, False, None),
        ("[ĐIỀN: MSSV]", False, False, WD_COLOR_INDEX.YELLOW),
    ], indent_cm=0.5)
    rb.add_rich_para([
        ("Lớp / Ngành đào tạo: ", True, False, None),
        ("[ĐIỀN: Lớp / Chương trình đào tạo]", False, False, WD_COLOR_INDEX.YELLOW),
    ], indent_cm=0.5)
    rb.add_rich_para([
        ("Giảng viên hướng dẫn: ", True, False, None),
        ("[ĐIỀN: Học hàm, học vị & Họ tên GVHD]", False, False, WD_COLOR_INDEX.YELLOW),
    ], indent_cm=0.5)

    rb.add_para("Nhiệm vụ và phạm vi nghiên cứu chính của đề tài:", bold=True, indent_cm=0.5, space_after=6)
    rb.add_bullet(
        "Thiết kế phần cứng và bo mạch PCB Hub trung tâm DIY v3: ",
        "Xây dựng mạch điều khiển dựa trên vi điều khiển NodeMCU ESP8266 v2 Amica quản lý chặt chẽ 6 thiết bị chấp hành và 3 cảm biến (tương ứng 14 khối/module vật lý), tích hợp toàn bộ linh kiện bảo vệ (C1–C9, D1–D2 1N4007, Q1 S8050) trực tiếp trên mạch in 1 lớp 100 × 80 mm đạt 0 ERC / 0 DRC, loại bỏ hoàn toàn bảng cắm thử nghiệm breadboard và chuẩn hóa 40/40 dây nối có chiều dài <= 30 cm.",
    )
    rb.add_bullet(
        "Thiết kế cơ khí mô hình nhà thông minh in 3D lắp mộng tự khóa: ",
        "Thiết kế và tối ưu hóa giảm nhựa 51 chi tiết vỏ và giá đỡ cơ khí (83 bản thể) theo công nghệ lắp mộng 100% không ốc vít, không keo dán, không cần chống đỡ in (0% support), phân bổ tự động trên 16 bàn in khổ 180 × 200 × 250 mm với tổng khối lượng nhựa PLA chỉ 660,64 g.",
    )
    rb.add_bullet(
        "Xây dựng máy chủ trung tâm, trợ lý giọng nói AI tiếng Việt và cơ chế bảo mật 3 tầng RBAC: ",
        "Phát triển máy chủ FastAPI (Python), cơ sở dữ liệu SQLite chuẩn hóa 3NF chế độ WAL, cầu nối âm thanh hai chiều thời gian thực Gemini 3.8 Live (giọng Aoede 100% tiếng Việt) tích hợp ServerEchoGuard, 20 hàm công cụ điều khiển, cơ chế xác nhận đúng 1 lần cho lệnh tùy chỉnh, 2 bể tự động hóa độc lập (TimersPool & RulesPool), phân quyền 3 tầng (Chủ nhà / Thành viên / Khách QR TOTP 10 giây) và khả năng hoạt động an toàn ngoại tuyến trên firmware ESP8266.",
    )
    rb.add_bullet(
        "Xây dựng giao diện Web 3D Digital Twin và ứng dụng di động Android: ",
        "Triển khai giao diện Web mô phỏng nhà 3D tương tác thời gian thực bằng Three.js, trang mô phỏng đấu nối phần cứng /wokwi PCB-Direct, ứng dụng Android thuần bằng Kotlin/Jetpack Compose (minSdk 26) hỗ trợ điều khiển thiết bị, hội thoại giọng nói tiếng Việt và quét mã QR khách.",
    )
    _add_signature_block(rb, "GIẢNG VIÊN HƯỚNG DẪN", "[ĐIỀN: Họ tên GVHD]", highlight_name=True)

    # Page 4 (ii): LỜI CAM ĐOAN
    rb.add_page_break()
    rb.add_front_title("LỜI CAM ĐOAN", space_after=14)
    rb.add_para(
        "Em xin cam đoan toàn bộ nội dung trình bày trong báo cáo Đồ án Tốt nghiệp với đề tài "
        "“Thiết kế và xây dựng hệ thống nhà thông minh điều khiển bằng giọng nói AI tích hợp mô hình 3D và ứng dụng di động” "
        "là kết quả nghiên cứu, thiết kế, lập trình, mô phỏng và kiểm thử do chính em thực hiện dưới sự hướng dẫn tận tình của "
        "Giảng viên hướng dẫn."
    )
    rb.add_para(
        "Mọi số liệu đo đạc, kết quả kiểm tra quy tắc mạch in (KiCad ERC/DRC), thông số chiều dài dây định tuyến 3D, "
        "khối lượng nhựa in 3D đo bằng PrusaSlicer CLI, kết quả kiểm thử tự động (pytest), kiểm thử giao diện Web và "
        "kiểm thử ứng dụng Android đều trung thực, có nguồn mã nguồn tái lập được và không sao chép bất hợp pháp từ bất kỳ công trình nào khác. "
        "Các thư viện mã nguồn mở, chuẩn giao thức, datasheet linh kiện và tài liệu tham khảo sử dụng trong đồ án đều được trích dẫn đầy đủ, minh bạch trong danh mục Tài liệu tham khảo và hồ sơ nguồn biểu trưng."
    )
    rb.add_para(
        "Em xin hoàn toàn chịu trách nhiệm trước Nhà trường và Hội đồng bảo vệ Đồ án Tốt nghiệp về lời cam đoan này."
    )
    _add_signature_block(rb, "SINH VIÊN THỰC HIỆN", "NGUYỄN TUẤN ANH", highlight_name=False)

    # Page 5 (iii): LỜI CẢM ƠN
    rb.add_page_break()
    rb.add_front_title("LỜI CẢM ƠN", space_after=14)
    rb.add_rich_para([
        ("Lời đầu tiên, em xin gửi lời cảm ơn chân thành và sâu sắc nhất tới ", False, False, None),
        ("[ĐIỀN: Học hàm, học vị & Họ tên GVHD]", True, False, WD_COLOR_INDEX.YELLOW),
        (" — người đã trực tiếp định hướng đề tài, tận tâm chỉ bảo, góp ý chặt chẽ về kiến trúc phần cứng, chuẩn an toàn điện tử cũng như phương pháp trình bày báo cáo khoa học trong suốt quá trình em thực hiện Đồ án Tốt nghiệp.", False, False, None),
    ])
    rb.add_rich_para([
        ("Em xin trân trọng cảm ơn quý thầy cô giáo thuộc ", False, False, None),
        ("[ĐIỀN: Khoa / Viện — Trường Điện - Điện tử, Đại học Bách khoa Hà Nội]", False, False, WD_COLOR_INDEX.YELLOW),
        (" đã truyền đạt nền tảng kiến thức vững chắc về kỹ thuật điện tử, hệ thống nhúng, mạng truyền thông và lập trình ứng dụng trong suốt những năm học đại học, tạo tiền đề quan trọng để em hoàn thiện một hệ thống liên ngành hoàn chỉnh từ mạch điện tử, cơ khí in 3D đến máy chủ trí tuệ nhân tạo.", False, False, None),
    ])
    rb.add_para(
        "Em cũng xin bày tỏ lòng biết ơn tới gia đình và bạn bè đã luôn động viên, hỗ trợ về tinh thần và góp ý thực tế trong quá trình thử nghiệm giao diện người dùng, kịch bản điều khiển bằng giọng nói tiếng Việt và hoàn thiện tài liệu."
    )
    rb.add_para(
        "Do thời gian và kinh nghiệm thực tế còn những giới hạn nhất định, báo cáo khó tránh khỏi những điểm có thể tiếp tục tối ưu hơn nữa. Em rất mong nhận được những ý kiến đóng góp quý báu từ quý thầy cô trong Hội đồng để đề tài ngày càng hoàn thiện."
    )
    rb.add_para("Em xin chân thành cảm ơn!", align=WD_ALIGN_PARAGRAPH.RIGHT, indent_cm=0)

    # Page 6 (iv): TÓM TẮT NỘI DUNG ĐỒ ÁN
    rb.add_page_break()
    rb.add_front_title("TÓM TẮT NỘI DUNG ĐỒ ÁN", space_after=14)
    rb.add_para(
        "Đề tài tập trung nghiên cứu, thiết kế và xây dựng trọn gói hệ thống Nhà thông minh điều khiển bằng giọng nói tiếng Việt tích hợp trí tuệ nhân tạo thời gian thực (Smart Home Voice AI), mô hình song sinh số 3D trên nền Web (Web 3D Digital Twin) và ứng dụng di động Android thuần. Khác với các hệ thống mẫu thử rời rạc sử dụng bảng cắm breadboard dễ lỏng dây hoặc chỉ hỗ trợ câu lệnh đơn giản bằng tiếng Anh, đề tài giải quyết đồng bộ năm bài toán kỹ thuật cốt lõi từ lớp vật lý đến lớp ứng dụng."
    )
    rb.add_para(
        "Ở lớp phần cứng và cơ khí, hệ thống khóa chặt hợp đồng 10 chân trên vi điều khiển NodeMCU ESP8266 v2 Amica để điều khiển 6 thiết bị chấp hành (đèn phòng khách, đèn phòng ngủ đấu Active-LOW an toàn boot, cửa chính dẫn động đồng trục bằng Servo SG90, máy bơm tưới cây 5V qua Relay 1, mạch khuếch đại loa PAM8403 qua Relay 2 và còi báo động 5V TMB12A05 lái low-side qua transistor NPN S8050) cùng 3 cảm biến dùng nguồn chuẩn 3,3V (nhiệt độ – độ ẩm DHT11, độ ẩm đất LM393 + đầu dò YL-69 và cảm biến âm thanh KY-037/038). Toàn bộ 23 linh kiện bảo vệ và lọc nguồn (R1–R10, Q1, C1–C9, D1–D2 1N4007, D3) được tích hợp trực tiếp trên bo mạch PCB Hub trung tâm DIY v3 một lớp kích thước 100 × 80 × 1,6 mm (51 footprints, 0 lỗi ERC, 0 lỗi DRC) kết nối bằng 40 sợi dây chuẩn có chiều dài tối đa 27,48 cm (<= 30 cm). Vỏ mô hình ngôi nhà được thiết kế bằng FreeCAD 1.1.4 gồm 51 chi tiết (83 bản thể) lắp mộng 100% không ốc vít, không keo dán, tối ưu giảm 36,77% nhựa xuống còn 660,64 g PLA trên 16 bàn in khổ 180 × 200 × 250 mm (0% support, 0 va chạm)."
    )
    rb.add_para(
        "Ở lớp phần mềm, máy chủ trung tâm FastAPI (Python 3.14.7) kết hợp cơ sở dữ liệu SQLite 3.53.2 chuẩn hóa 3NF chế độ WAL cung cấp cầu nối WebSocket hai chiều tới Gemini 3.8 Live (giọng Aoede 100% tiếng Việt) với bộ lọc dội âm ServerEchoGuard, 20 hàm công cụ (Function Declarations), cơ chế xác nhận đúng 1 lần khi dạy lệnh tùy chỉnh, hai bể tự động hóa độc lập (TimersPool và RulesPool) và hệ thống phân quyền 3 tầng RBAC (Chủ nhà Cấp 1, Thành viên Cấp 2, Khách Cấp 3 vào bằng mã QR động TOTP chu kỳ 10 giây). Trên firmware ESP8266, cấu hình Wi-Fi được nạp động qua cổng USB lưu vào phân vùng LittleFS (/wifi_config.json) không lưu cứng mật khẩu trong mã nguồn, kèm máy trạng thái ngoại tuyến (Offline FSM A1–A4) khóa cứng cấm mở cửa chính khi mất kết nối máy chủ."
    )
    rb.add_para(
        "Tại thời điểm hoàn thiện báo cáo, toàn bộ hệ thống phần mềm máy chủ, giao diện Web 3D Digital Twin, trang mô phỏng mạch /wokwi, ứng dụng Android APK v1.0, thiết kế PCB Hub DIY v3 và bộ tệp in 3D 16 bàn đã hoàn thiện 100% và vượt qua kiểm thử tự động; hạng mục duy nhất còn lại để chạy thực tế ngoài mô hình là gia công lắp ráp phần cứng, cắm cáp USB nạp firmware và cấp nguồn 5V 2A cho bo mạch thật."
    )
    _add_signature_block(rb, "SINH VIÊN THỰC HIỆN", "NGUYỄN TUẤN ANH", highlight_name=False)

    # Page 7 (v): MỤC LỤC
    rb.add_page_break()
    rb.add_front_title("MỤC LỤC", space_after=10)
    rb.add_toc_field(
        'TOC \\o "1-3" \\h \\z \\u',
        "[Trường Mục lục tự động của Microsoft Word — cập nhật bằng Fields.Update() / TablesOfContents.Update() trong Word COM]",
    )

    # Page 8 (vi): DANH MỤC TỪ VIẾT TẮT
    rb.add_page_break()
    rb.add_front_title("DANH MỤC TỪ VIẾT TẮT", space_after=10)
    abbr_rows = [
        ("3NF", "Third Normal Form", "Dạng chuẩn thứ ba trong thiết kế cơ sở dữ liệu quan hệ"),
        ("ADC", "Analog-to-Digital Converter", "Bộ chuyển đổi tín hiệu tương tự sang số"),
        ("AI", "Artificial Intelligence", "Trí tuệ nhân tạo"),
        ("ANR", "Application Not Responding", "Lỗi ứng dụng Android không phản hồi"),
        ("API", "Application Programming Interface", "Giao diện lập trình ứng dụng"),
        ("APK", "Android Package Kit", "Gói cài đặt ứng dụng hệ điều hành Android"),
        ("BJT", "Bipolar Junction Transistor", "Transistor lưỡng cực (Q1 S8050 lái còi báo động)"),
        ("BOM", "Bill of Materials", "Danh mục định mức linh kiện vật tư"),
        ("BTL", "Bridge-Tied Load", "Mạch khuếch đại tải cầu vi sai (ngõ ra loa PAM8403)"),
        ("CAD", "Computer-Aided Design", "Thiết kế cơ khí có sự hỗ trợ của máy tính"),
        ("CLI", "Command-Line Interface", "Giao diện dòng lệnh"),
        ("COM", "Component Object Model / Serial Port", "Cổng nối tiếp USB-UART hoặc giao diện tự động hóa Word"),
        ("CSS", "Cascading Style Sheets", "Ngôn ngữ định kiểu giao diện Web"),
        ("DC", "Direct Current", "Dòng điện một chiều (5V DC / 3,3V DC)"),
        ("DRC", "Design Rule Check", "Kiểm tra quy tắc thiết kế mạch in PCB"),
        ("ERC", "Electrical Rules Check", "Kiểm tra quy tắc kết nối điện trên sơ đồ nguyên lý"),
        ("ERD", "Entity-Relationship Diagram", "Sơ đồ thực thể liên kết cơ sở dữ liệu"),
        ("FDM", "Fused Deposition Modeling", "Công nghệ in 3D đùn sợi nhựa nóng chảy (PLA)"),
        ("FEA", "Finite Element Analysis", "Phân tích phần tử hữu hạn kiểm tra độ bền kết cấu"),
        ("FSM", "Finite State Machine", "Máy trạng thái hữu hạn (cơ chế ngoại tuyến ESP8266)"),
        ("GPIO", "General-Purpose Input/Output", "Chân vào/ra số đa dụng trên vi điều khiển"),
        ("HTML", "HyperText Markup Language", "Ngôn ngữ đánh dấu siêu văn bản"),
        ("HTTP", "HyperText Transfer Protocol", "Giao thức truyền tải siêu văn bản"),
        ("IoT", "Internet of Things", "Internet vạn vật"),
        ("JSON", "JavaScript Object Notation", "Định dạng trao đổi dữ liệu có cấu trúc nhẹ"),
        ("LED", "Light-Emitting Diode", "Đi-ốt phát quang"),
        ("MQTT", "Message Queuing Telemetry Transport", "Giao thức truyền thông điệp nhẹ mô hình Publish/Subscribe"),
        ("OTP", "One-Time Password", "Mật khẩu xác thực dùng một lần gửi qua email"),
        ("PCB", "Printed Circuit Board", "Bo mạch in điện tử"),
        ("PCM", "Pulse-Code Modulation", "Điều chế xung mã cho luồng âm thanh số 16/24 kHz"),
        ("PLA", "Polylactic Acid", "Vật liệu sợi nhựa sinh học dùng cho in 3D FDM"),
        ("PWM", "Pulse-Width Modulation", "Điều chế độ rộng xung (điều khiển Servo SG90, âm thanh)"),
        ("QR", "Quick Response Code", "Mã phản hồi nhanh dùng cấp quyền khách động"),
        ("RAG", "Retrieval-Augmented Generation", "Tăng cường sinh ngôn ngữ bằng truy xuất tri thức"),
        ("RBAC", "Role-Based Access Control", "Kiểm soát truy cập dựa trên vai trò (3 tầng)"),
        ("REST", "Representational State Transfer", "Kiến trúc giao diện dịch vụ Web theo tài nguyên"),
        ("SSE", "Server-Sent Events", "Kênh đẩy sự kiện một chiều từ máy chủ tới trình duyệt"),
        ("SSOT", "Single Source of Truth", "Nguồn sự thật duy nhất đồng bộ tài liệu và mã nguồn"),
        ("TOTP", "Time-Based One-Time Password", "Mã xác thực một lần thay đổi theo chu kỳ thời gian (10 giây)"),
        ("UART", "Universal Asynchronous Receiver-Transmitter", "Giao tiếp nối tiếp không đồng bộ"),
        ("UI / UX", "User Interface / User Experience", "Giao diện người dùng / Trải nghiệm người dùng"),
        ("USB", "Universal Serial Bus", "Chuẩn kết nối và nạp firmware qua cổng nối tiếp đa dụng"),
        ("VAD", "Voice Activity Detection", "Bộ phát hiện hoạt động tiếng nói"),
        ("WAL", "Write-Ahead Logging", "Cơ chế ghi nhật ký trước của SQLite giúp đọc ghi đồng thời"),
        ("WS", "WebSocket", "Giao thức kết nối song công toàn phần trên nền TCP"),
    ]
    rb.add_table(
        caption=None,
        headers=["Từ viết tắt", "Tên đầy đủ tiếng Anh", "Ý nghĩa tiếng Việt"],
        rows=abbr_rows,
        col_widths_cm=[2.6, 5.9, 7.0],
        font_pt=10.5,
        center_cols=(0,),
    )

    # Page 9 (vii): DANH MỤC HÌNH VẼ
    rb.add_page_break()
    rb.add_front_title("DANH MỤC HÌNH VẼ", space_after=10)
    rb.add_toc_field(
        'TOC \\h \\z \\c "Hình"',
        "[Trường Danh mục Hình vẽ tự động của Microsoft Word — thu thập toàn bộ chú thích SEQ Hình]",
    )

    # Page 10 (viii): DANH MỤC BẢNG BIỂU
    rb.add_page_break()
    rb.add_front_title("DANH MỤC BẢNG BIỂU", space_after=10)
    rb.add_toc_field(
        'TOC \\h \\z \\c "Bảng"',
        "[Trường Danh mục Bảng biểu tự động của Microsoft Word — thu thập toàn bộ chú thích SEQ Bảng]",
    )
