"""OOXML & python-docx formatting helpers for HUST-compliant Graduation Report (v2).

Implements exact specifications from TEMPLATE_ANALYSIS.md, GRILL_ANSWERS.md, and v2 feedback:
- A4 paper (21.0 x 29.7 cm), Left 3.5 cm, Right 2.0 cm, Top 2.0 cm, Bottom 2.0 cm
- Times New Roman across all ASCII/HAnsi/EastAsia/CS runs (body 13 pt, line spacing 1.3)
- Consolas (10 pt) shaded bordered text code listings with line numbers and real SEQ Đoạn_mã fields
- Double border for Cover / Inner Cover section with real HUST logo helper
- Roman numeral footers (i, ii, ...) for Front Matter; right-aligned Arabic footers (1, 2, ...) from Chapter 1
- Real Word fields: TOC (1-3), TOC \\c "Hình", TOC \\c "Bảng", TOC \\c "Đoạn_mã", SEQ Hình, SEQ Bảng, SEQ Đoạn_mã, PAGE
- Automatic image compression/optimization helper so final .docx stays well under 10 MB
"""

from __future__ import annotations

import hashlib
import pathlib
from typing import Iterable, Sequence

from PIL import Image
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt, RGBColor


FONT_NAME = "Times New Roman"
CODE_FONT_NAME = "Consolas"
BODY_PT = 13
CAPTION_PT = 12
TABLE_PT = 11.0
CODE_PT = 10.0
FOOTER_PT = 12
TEXT_WIDTH_CM = 15.5  # 21.0 - 3.5 - 2.0

# Verified in Phase 0 LibreOffice 26.8.3.1 UNO & Microsoft Word compatibility test
LISTING_SEQ_ID = "Đoạn_mã"


def set_run_font(
    run,
    size_pt: float = BODY_PT,
    bold: bool = False,
    italic: bool = False,
    color: RGBColor | None = None,
    highlight: WD_COLOR_INDEX | None = None,
    font_name: str = FONT_NAME,
) -> None:
    run.font.name = font_name
    run.font.size = Pt(size_pt)
    run.bold = bold
    run.italic = italic
    if color is not None:
        run.font.color.rgb = color
    if highlight is not None:
        run.font.highlight_color = highlight
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rFonts.set(qn(attr), font_name)


def configure_section_a4(section) -> None:
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(3.5)
    section.right_margin = Cm(2.0)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.header_distance = Cm(1.2)
    section.footer_distance = Cm(1.2)


def set_section_page_border(section, double: bool = True, color: str = "000000") -> None:
    sectPr = section._sectPr
    existing = sectPr.find(qn("w:pgBorders"))
    if existing is not None:
        sectPr.remove(existing)
    if not double:
        return
    pgBorders = parse_xml(
        f'<w:pgBorders {nsdecls("w")} w:offsetFrom="page">'
        f'  <w:top w:val="double" w:sz="12" w:space="24" w:color="{color}"/>'
        f'  <w:left w:val="double" w:sz="12" w:space="24" w:color="{color}"/>'
        f'  <w:bottom w:val="double" w:sz="12" w:space="24" w:color="{color}"/>'
        f'  <w:right w:val="double" w:sz="12" w:space="24" w:color="{color}"/>'
        f'</w:pgBorders>'
    )
    sectPr.append(pgBorders)


def set_section_page_numbering(section, fmt: str = "decimal", start: int | None = 1) -> None:
    """fmt: 'lowerRoman' or 'decimal'."""
    sectPr = section._sectPr
    existing = sectPr.find(qn("w:pgNumType"))
    if existing is not None:
        sectPr.remove(existing)
    pgNum = OxmlElement("w:pgNumType")
    pgNum.set(qn("w:fmt"), fmt)
    if start is not None:
        pgNum.set(qn("w:start"), str(start))
    sectPr.append(pgNum)


def enable_update_fields_on_open(doc: Document) -> None:
    settings = doc.settings.element
    if settings.find(qn("w:updateFields")) is None:
        el = OxmlElement("w:updateFields")
        el.set(qn("w:val"), "true")
        settings.append(el)


def add_field(
    paragraph,
    instruction: str,
    display_text: str = "",
    size_pt: float = BODY_PT,
    bold: bool = False,
    italic: bool = False,
    color: RGBColor | None = None,
) -> None:
    r_begin = paragraph.add_run()
    set_run_font(r_begin, size_pt=size_pt, bold=bold, italic=italic, color=color)
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    fld_begin.set(qn("w:dirty"), "true")
    r_begin._r.append(fld_begin)

    r_instr = paragraph.add_run()
    set_run_font(r_instr, size_pt=size_pt, bold=bold, italic=italic, color=color)
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" {instruction} "
    r_instr._r.append(instr)

    r_sep = paragraph.add_run()
    set_run_font(r_sep, size_pt=size_pt, bold=bold, italic=italic, color=color)
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    r_sep._r.append(fld_sep)

    r_val = paragraph.add_run(display_text)
    set_run_font(r_val, size_pt=size_pt, bold=bold, italic=italic, color=color)

    r_end = paragraph.add_run()
    set_run_font(r_end, size_pt=size_pt, bold=bold, italic=italic, color=color)
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    r_end._r.append(fld_end)


def set_footer_page_number(section, align=WD_ALIGN_PARAGRAPH.RIGHT, clear: bool = False) -> None:
    section.footer.is_linked_to_previous = False
    section.header.is_linked_to_previous = False
    for p in list(section.header.paragraphs):
        p.text = ""
    footer = section.footer
    p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    p.text = ""
    p.alignment = align
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    if not clear:
        add_field(p, "PAGE", display_text="", size_pt=FOOTER_PT, bold=False, italic=False)


def configure_document_styles(doc: Document, line_spacing: float = 1.3) -> None:
    enable_update_fields_on_open(doc)
    normal = doc.styles["Normal"]
    normal.font.name = FONT_NAME
    normal.font.size = Pt(BODY_PT)
    normal.font.color.rgb = RGBColor(0x00, 0x00, 0x00)
    rPr = normal.element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rFonts.set(qn(attr), FONT_NAME)
    pf = normal.paragraph_format
    pf.line_spacing = line_spacing
    pf.space_before = Pt(0)
    pf.space_after = Pt(5)
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    pf.first_line_indent = Cm(1.27)

    heading_specs = [
        ("Heading 1", 13, True, False, WD_ALIGN_PARAGRAPH.CENTER, 0, 8, 10, True),
        ("Heading 2", 13, True, False, WD_ALIGN_PARAGRAPH.LEFT, 0, 8, 5, False),
        ("Heading 3", 13, True, False, WD_ALIGN_PARAGRAPH.LEFT, 0.5, 6, 3, False),
        ("Heading 4", 13, False, True, WD_ALIGN_PARAGRAPH.LEFT, 1.0, 5, 3, False),
    ]
    for name, sz, bld, itl, aln, left_cm, sb, sa, pb in heading_specs:
        st = doc.styles[name]
        st.font.name = FONT_NAME
        st.font.size = Pt(sz)
        st.font.bold = bld
        st.font.italic = itl
        st.font.color.rgb = RGBColor(0x00, 0x00, 0x00)
        hrPr = st.element.get_or_add_rPr()
        hrFonts = hrPr.find(qn("w:rFonts"))
        if hrFonts is None:
            hrFonts = OxmlElement("w:rFonts")
            hrPr.insert(0, hrFonts)
        for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
            hrFonts.set(qn(attr), FONT_NAME)
        hpf = st.paragraph_format
        hpf.alignment = aln
        hpf.left_indent = Cm(left_cm)
        hpf.first_line_indent = Cm(0)
        hpf.line_spacing = line_spacing
        hpf.space_before = Pt(sb)
        hpf.space_after = Pt(sa)
        hpf.keep_with_next = True
        hpf.page_break_before = pb


def set_cell_shading(cell, fill_hex: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)


def set_cell_margins(cell, top=70, bottom=70, left=100, right=100) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tcPr.append(tcMar)


def set_table_borders(table, val: str = "single", sz: str = "4", color: str = "334155") -> None:
    tblPr = table._tbl.tblPr
    existing = tblPr.find(qn("w:tblBorders"))
    if existing is not None:
        tblPr.remove(existing)
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'<w:top w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:left w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:bottom w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:right w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:insideH w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:insideV w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)


def set_row_cant_split(row) -> None:
    trPr = row._tr.get_or_add_trPr()
    trPr.append(OxmlElement("w:cantSplit"))


def set_row_header(row) -> None:
    trPr = row._tr.get_or_add_trPr()
    trPr.append(OxmlElement("w:tblHeader"))


def optimize_image_for_docx(
    src_path: pathlib.Path,
    optimize_dir: pathlib.Path | None,
    kind: str = "figure",
) -> tuple[pathlib.Path, int, int, int]:
    """Compress & resize raster images deterministically so final .docx stays < 10 MB.

    Returns (path_to_embed, width_px, height_px, file_size_bytes).
    """
    with Image.open(src_path) as im_orig:
        w0, h0 = im_orig.size
        if optimize_dir is None:
            return src_path, w0, h0, src_path.stat().st_size

        optimize_dir.mkdir(parents=True, exist_ok=True)
        h_key = hashlib.sha1(f"{src_path.resolve()}:{src_path.stat().st_mtime_ns}:{kind}".encode("utf-8")).hexdigest()[:10]

        use_jpeg = kind in ("photo", "3d_model", "web_ui", "app_ui", "pcb_3d", "hardware_photo")
        if kind == "logo":
            max_w = 500
            use_jpeg = False
        elif kind in ("diagram", "schematic", "pcb_2d"):
            max_w = 1600
            use_jpeg = False
        else:
            max_w = 1350

        ext = ".jpg" if use_jpeg else ".png"
        out_path = optimize_dir / f"{src_path.stem}_{h_key}{ext}"

        if out_path.exists():
            with Image.open(out_path) as im_cached:
                wc, hc = im_cached.size
            return out_path, wc, hc, out_path.stat().st_size

        im = im_orig.copy()
        if w0 > max_w:
            new_h = max(1, int(round(h0 * (max_w / float(w0)))))
            im = im.resize((max_w, new_h), Image.Resampling.LANCZOS)

        if use_jpeg:
            if im.mode in ("RGBA", "LA", "P"):
                rgba = im.convert("RGBA")
                bg = Image.new("RGB", rgba.size, (255, 255, 255))
                bg.paste(rgba, mask=rgba.split()[-1])
                im_rgb = bg
            else:
                im_rgb = im.convert("RGB")
            im_rgb.save(str(out_path), format="JPEG", quality=84, optimize=True, progressive=True)
            w_out, h_out = im_rgb.size
        else:
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA" if "transparency" in im.info else "RGB")
            im.save(str(out_path), format="PNG", optimize=True, compress_level=9)
            w_out, h_out = im.size

        # If optimized file is unexpectedly larger than original (e.g., tiny crisp PNG), keep original
        if out_path.stat().st_size >= src_path.stat().st_size and w0 <= max_w:
            out_path.unlink(missing_ok=True)
            return src_path, w0, h0, src_path.stat().st_size

        return out_path, w_out, h_out, out_path.stat().st_size


class ReportBuilder:
    """Stateful HUST graduation report writer with automatic chapter/figure/table/listing counters."""

    def __init__(self, line_spacing: float = 1.3, optimize_dir: pathlib.Path | None = None):
        self.doc = Document()
        self.line_spacing = line_spacing
        self.optimize_dir = optimize_dir
        configure_document_styles(self.doc, line_spacing=line_spacing)
        configure_section_a4(self.doc.sections[0])
        self.current_chapter = 0
        self.fig_in_chapter = 0
        self.tbl_in_chapter = 0
        self.listing_in_chapter = 0
        self.total_figures = 0
        self.total_tables = 0
        self.total_listings = 0
        self.figure_registry: list[str] = []
        self.table_registry: list[str] = []
        self.listing_registry: list[str] = []
        self.embedded_images: list[dict[str, object]] = []

    def add_new_section(self, start_type=WD_SECTION.NEW_PAGE):
        sec = self.doc.add_section(start_type)
        configure_section_a4(sec)
        return sec

    def add_page_break(self) -> None:
        self.doc.add_page_break()

    def add_front_title(self, title: str, space_after: float = 10) -> None:
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after = Pt(space_after)
        p.paragraph_format.line_spacing = self.line_spacing
        p.paragraph_format.keep_with_next = True
        r = p.add_run(title)
        set_run_font(r, size_pt=14, bold=True)

    def add_chapter(self, num: int, title: str, first_chapter: bool = False) -> None:
        self.current_chapter = num
        self.fig_in_chapter = 0
        self.tbl_in_chapter = 0
        self.listing_in_chapter = 0
        p = self.doc.add_paragraph(style="Heading 1")
        p.paragraph_format.page_break_before = not first_chapter
        r = p.add_run(f"CHƯƠNG {num}. {title.upper()}")
        set_run_font(r, size_pt=13, bold=True)

    def add_unnumbered_chapter(self, title: str) -> None:
        p = self.doc.add_paragraph(style="Heading 1")
        p.paragraph_format.page_break_before = True
        r = p.add_run(title.upper())
        set_run_font(r, size_pt=13, bold=True)

    def add_h2(self, text: str) -> None:
        p = self.doc.add_paragraph(style="Heading 2")
        r = p.add_run(text)
        set_run_font(r, size_pt=13, bold=True)

    def add_h3(self, text: str) -> None:
        p = self.doc.add_paragraph(style="Heading 3")
        r = p.add_run(text)
        set_run_font(r, size_pt=13, bold=True)

    def add_h4(self, text: str) -> None:
        p = self.doc.add_paragraph(style="Heading 4")
        r = p.add_run(text)
        set_run_font(r, size_pt=13, bold=False, italic=True)

    def add_para(
        self,
        text: str,
        bold: bool = False,
        italic: bool = False,
        align=WD_ALIGN_PARAGRAPH.JUSTIFY,
        indent_cm: float = 1.27,
        space_after: float = 5,
    ):
        p = self.doc.add_paragraph()
        p.alignment = align
        p.paragraph_format.first_line_indent = Cm(indent_cm)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(space_after)
        p.paragraph_format.line_spacing = self.line_spacing
        r = p.add_run(text)
        set_run_font(r, size_pt=BODY_PT, bold=bold, italic=italic)
        return p

    def add_rich_para(
        self,
        segments: Sequence[tuple[str, bool, bool, WD_COLOR_INDEX | None]],
        align=WD_ALIGN_PARAGRAPH.JUSTIFY,
        indent_cm: float = 1.27,
        space_after: float = 5,
    ):
        p = self.doc.add_paragraph()
        p.alignment = align
        p.paragraph_format.first_line_indent = Cm(indent_cm)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(space_after)
        p.paragraph_format.line_spacing = self.line_spacing
        for txt, bld, itl, hl in segments:
            r = p.add_run(txt)
            set_run_font(r, size_pt=BODY_PT, bold=bld, italic=itl, highlight=hl)
        return p

    def add_bullet(self, lead_bold: str, body: str) -> None:
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.left_indent = Cm(1.27)
        p.paragraph_format.first_line_indent = Cm(-0.45)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(3.5)
        p.paragraph_format.line_spacing = self.line_spacing
        r0 = p.add_run("–  ")
        set_run_font(r0, size_pt=BODY_PT)
        if lead_bold:
            r1 = p.add_run(lead_bold)
            set_run_font(r1, size_pt=BODY_PT, bold=True)
        r2 = p.add_run(body)
        set_run_font(r2, size_pt=BODY_PT)

    def add_toc_field(self, field_code: str, placeholder_note: str) -> None:
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.space_before = Pt(3)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.line_spacing = 1.15
        add_field(
            p,
            field_code,
            display_text=placeholder_note,
            size_pt=12,
            italic=True,
            color=RGBColor(0x47, 0x55, 0x69),
        )

    def add_cover_logo(
        self,
        image_path: pathlib.Path,
        max_height_cm: float = 3.2,
        max_width_cm: float = 4.0,
        label: str = "Logo ĐHBK Hà Nội (HUST)",
    ) -> None:
        embed_path, w_px, h_px, sz = optimize_image_for_docx(image_path, self.optimize_dir, kind="logo")
        aspect = w_px / max(h_px, 1)
        h_cm = max_height_cm
        w_cm = h_cm * aspect
        if w_cm > max_width_cm:
            w_cm = max_width_cm
            h_cm = w_cm / max(aspect, 0.1)

        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing = 1.0
        run = p.add_run()
        run.add_picture(str(embed_path), width=Cm(w_cm))
        self.embedded_images.append(
            {
                "source_file": image_path.name,
                "embedded_file": embed_path.name,
                "kind": "university_logo",
                "caption": label,
                "chapter": 0,
                "width_px": w_px,
                "height_px": h_px,
                "size_bytes": sz,
            }
        )

    def add_dashed_box(self, label: str, sublabel: str = "", height_cm: float = 4.6, width_cm: float = 14.2) -> None:
        tbl = self.doc.add_table(rows=1, cols=1)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl.autofit = False
        set_table_borders(tbl, val="dashed", sz="10", color="64748B")
        cell = tbl.cell(0, 0)
        cell.width = Cm(width_cm)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        set_cell_shading(cell, "F8FAFC")
        set_cell_margins(cell, top=140, bottom=140, left=180, right=180)
        trPr = tbl.rows[0]._tr.get_or_add_trPr()
        trHeight = parse_xml(f'<w:trHeight {nsdecls("w")} w:val="{int(height_cm * 567)}" w:hRule="atLeast"/>')
        trPr.append(trHeight)
        set_row_cant_split(tbl.rows[0])

        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.space_before = Pt(3)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.line_spacing = 1.15
        p.paragraph_format.keep_with_next = True
        r = p.add_run(label)
        set_run_font(r, size_pt=11.5, bold=True, color=RGBColor(0x33, 0x41, 0x55))
        if sublabel:
            p2 = cell.add_paragraph()
            p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p2.paragraph_format.first_line_indent = Cm(0)
            p2.paragraph_format.space_before = Pt(2)
            p2.paragraph_format.space_after = Pt(2)
            p2.paragraph_format.line_spacing = 1.15
            p2.paragraph_format.keep_with_next = True
            r2 = p2.add_run(sublabel)
            set_run_font(r2, size_pt=10.5, italic=True, color=RGBColor(0x64, 0x74, 0x8B))

    def _add_seq_caption(self, kind: str, caption_text: str, keep_with_next: bool = False) -> str:
        """kind: 'Hình', 'Bảng', or 'Đoạn mã'."""
        ch = self.current_chapter
        if kind == "Hình":
            self.fig_in_chapter += 1
            self.total_figures += 1
            idx = self.fig_in_chapter
            seq_cmd = 'SEQ Hình \\* ARABIC \\r 1' if idx == 1 else 'SEQ Hình \\* ARABIC'
            label_full = f"Hình {ch}.{idx}: {caption_text}"
            self.figure_registry.append(label_full)
            sb, sa = 3, 8
        elif kind == "Bảng":
            self.tbl_in_chapter += 1
            self.total_tables += 1
            idx = self.tbl_in_chapter
            seq_cmd = 'SEQ Bảng \\* ARABIC \\r 1' if idx == 1 else 'SEQ Bảng \\* ARABIC'
            label_full = f"Bảng {ch}.{idx}: {caption_text}"
            self.table_registry.append(label_full)
            sb, sa = 7, 3
        else:
            self.listing_in_chapter += 1
            self.total_listings += 1
            idx = self.listing_in_chapter
            seq_cmd = f'SEQ {LISTING_SEQ_ID} \\* ARABIC \\r 1' if idx == 1 else f'SEQ {LISTING_SEQ_ID} \\* ARABIC'
            label_full = f"Đoạn mã {ch}.{idx}: {caption_text}"
            self.listing_registry.append(label_full)
            sb, sa = 7, 3

        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.space_before = Pt(sb)
        p.paragraph_format.space_after = Pt(sa)
        p.paragraph_format.line_spacing = 1.15
        p.paragraph_format.keep_with_next = keep_with_next

        r_pre = p.add_run(f"{kind} {ch}.")
        set_run_font(r_pre, size_pt=CAPTION_PT, bold=True, italic=True)
        add_field(p, seq_cmd, display_text=str(idx), size_pt=CAPTION_PT, bold=True, italic=True)
        r_post = p.add_run(f": {caption_text}")
        set_run_font(r_post, size_pt=CAPTION_PT, bold=False, italic=True)
        return label_full

    def add_figure(
        self,
        image_path: pathlib.Path | None,
        caption: str,
        max_width_cm: float = 14.2,
        max_height_cm: float = 9.0,
        placeholder_label: str = "",
        placeholder_sublabel: str = "",
        kind: str = "diagram",
    ) -> str:
        if image_path is not None and image_path.exists():
            embed_path, w_px, h_px, sz = optimize_image_for_docx(image_path, self.optimize_dir, kind=kind)
            aspect = h_px / max(w_px, 1)
            w_cm = max_width_cm
            h_cm = w_cm * aspect
            if h_cm > max_height_cm:
                h_cm = max_height_cm
                w_cm = h_cm / max(aspect, 0.05)
            p_img = self.doc.add_paragraph()
            p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_img.paragraph_format.first_line_indent = Cm(0)
            p_img.paragraph_format.space_before = Pt(5)
            p_img.paragraph_format.space_after = Pt(2)
            p_img.paragraph_format.keep_with_next = True
            run = p_img.add_run()
            run.add_picture(str(embed_path), width=Cm(w_cm))
            cap_full = self._add_seq_caption("Hình", caption, keep_with_next=False)
            self.embedded_images.append(
                {
                    "source_file": image_path.name,
                    "embedded_file": embed_path.name,
                    "kind": kind,
                    "caption": cap_full,
                    "chapter": self.current_chapter,
                    "width_px": w_px,
                    "height_px": h_px,
                    "size_bytes": sz,
                }
            )
            return cap_full
        else:
            lbl = placeholder_label or f"[ẢNH THỰC TẾ: {caption}]"
            self.add_dashed_box(lbl, placeholder_sublabel, height_cm=4.5, width_cm=max_width_cm)
            return self._add_seq_caption("Hình", caption, keep_with_next=False)

    def add_code_listing(
        self,
        caption: str,
        code_lines: Sequence[str],
        source_ref: str = "",
        start_line: int = 1,
        font_pt: float = CODE_PT,
    ) -> str:
        """Render a text code listing: Consolas 10 pt, light-grey shaded block, thin border, line numbers.

        Caption "Đoạn mã x.y: ..." is placed ABOVE the block with keep_with_next=True (matching Table convention).
        """
        full_caption = f"{caption} ({source_ref})" if source_ref and source_ref not in caption else caption
        cap_full = self._add_seq_caption("Đoạn mã", full_caption, keep_with_next=True)

        tbl = self.doc.add_table(rows=1, cols=1)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl.autofit = False
        set_table_borders(tbl, val="single", sz="6", color="CBD5E1")
        cell = tbl.cell(0, 0)
        cell.width = Cm(TEXT_WIDTH_CM)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
        set_cell_shading(cell, "F3F4F6")
        set_cell_margins(cell, top=60, bottom=60, left=110, right=95)
        if len(code_lines) <= 32:
            set_row_cant_split(tbl.rows[0])

        max_ln = start_line + max(len(code_lines) - 1, 0)
        num_w = max(2, len(str(max_ln)))

        for idx, raw_line in enumerate(code_lines):
            p = cell.paragraphs[0] if idx == 0 else cell.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.first_line_indent = Cm(0)
            p.paragraph_format.left_indent = Cm(0)
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.03

            ln_no = start_line + idx
            r_num = p.add_run(f"{ln_no:>{num_w}d} | ")
            set_run_font(r_num, size_pt=font_pt, bold=False, color=RGBColor(0x64, 0x74, 0x8B), font_name=CODE_FONT_NAME)

            clean_line = raw_line.rstrip("\r\n").replace("\t", "  ")
            r_code = p.add_run(clean_line)
            set_run_font(r_code, size_pt=font_pt, bold=False, color=RGBColor(0x0F, 0x17, 0x2A), font_name=CODE_FONT_NAME)

        sp = self.doc.add_paragraph()
        sp.paragraph_format.space_before = Pt(0)
        sp.paragraph_format.space_after = Pt(4)
        sp.paragraph_format.line_spacing = 1.0
        return cap_full

    def add_logo_showcase_figure(
        self,
        items: Sequence[tuple[str, pathlib.Path]],
        caption: str,
        cols: int = 4,
        logo_max_h_cm: float = 1.45,
    ) -> str:
        """Render a compact border-subtle logo grid for core thesis technologies only."""
        n = len(items)
        cols = min(cols, max(n, 1))
        rows = (n + cols - 1) // cols
        tbl = self.doc.add_table(rows=rows, cols=cols)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl.autofit = False
        set_table_borders(tbl, val="single", sz="4", color="E2E8F0")
        col_w = TEXT_WIDTH_CM / cols
        for r_idx in range(rows):
            set_row_cant_split(tbl.rows[r_idx])
            for c_idx in range(cols):
                idx = r_idx * cols + c_idx
                cell = tbl.cell(r_idx, c_idx)
                cell.width = Cm(col_w)
                cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
                set_cell_margins(cell, top=80, bottom=65, left=70, right=70)
                p = cell.paragraphs[0]
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.paragraph_format.first_line_indent = Cm(0)
                p.paragraph_format.space_before = Pt(2)
                p.paragraph_format.space_after = Pt(2)
                p.paragraph_format.line_spacing = 1.08
                if idx < n:
                    label, path = items[idx]
                    if path.exists():
                        embed_path, w_px, h_px, sz = optimize_image_for_docx(path, self.optimize_dir, kind="logo")
                        aspect = w_px / max(h_px, 1)
                        h_cm = logo_max_h_cm
                        w_cm = h_cm * aspect
                        max_cell_w = col_w - 0.7
                        if w_cm > max_cell_w:
                            w_cm = max_cell_w
                            h_cm = w_cm / max(aspect, 0.1)
                        run = p.add_run()
                        run.add_picture(str(embed_path), width=Cm(w_cm))
                        self.embedded_images.append(
                            {
                                "source_file": path.name,
                                "embedded_file": embed_path.name,
                                "kind": "tech_logo",
                                "caption": f"{caption} ({label})",
                                "chapter": self.current_chapter,
                                "width_px": w_px,
                                "height_px": h_px,
                                "size_bytes": sz,
                            }
                        )
                    p_lbl = cell.add_paragraph()
                    p_lbl.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    p_lbl.paragraph_format.first_line_indent = Cm(0)
                    p_lbl.paragraph_format.space_before = Pt(2)
                    p_lbl.paragraph_format.space_after = Pt(0)
                    p_lbl.paragraph_format.line_spacing = 1.05
                    rl = p_lbl.add_run(label)
                    set_run_font(rl, size_pt=10.0, bold=True)
        return self._add_seq_caption("Hình", caption, keep_with_next=False)

    def add_table(
        self,
        caption: str | None,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
        col_widths_cm: Sequence[float] | None = None,
        font_pt: float = TABLE_PT,
        center_cols: Iterable[int] = (),
    ) -> str | None:
        cap_full = None
        if caption is not None:
            cap_full = self._add_seq_caption("Bảng", caption, keep_with_next=True)

        ncols = len(headers)
        if col_widths_cm is None:
            col_widths_cm = [TEXT_WIDTH_CM / ncols] * ncols
        else:
            total = sum(col_widths_cm)
            if abs(total - TEXT_WIDTH_CM) > 0.1:
                scale = TEXT_WIDTH_CM / total
                col_widths_cm = [w * scale for w in col_widths_cm]

        tbl = self.doc.add_table(rows=1 + len(rows), cols=ncols)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl.autofit = False
        set_table_borders(tbl, val="single", sz="4", color="475569")

        hdr_row = tbl.rows[0]
        set_row_header(hdr_row)
        set_row_cant_split(hdr_row)
        for ci, htext in enumerate(headers):
            cell = hdr_row.cells[ci]
            cell.width = Cm(col_widths_cm[ci])
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            set_cell_shading(cell, "E2E8F0")
            set_cell_margins(cell, top=60, bottom=60, left=75, right=75)
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.first_line_indent = Cm(0)
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.1
            r = p.add_run(str(htext))
            set_run_font(r, size_pt=font_pt, bold=True)

        center_set = set(center_cols)
        for ri, row_vals in enumerate(rows):
            row = tbl.rows[ri + 1]
            set_row_cant_split(row)
            bg_hex = "F8FAFC" if ri % 2 == 1 else None
            for ci, val in enumerate(row_vals):
                cell = row.cells[ci]
                cell.width = Cm(col_widths_cm[ci])
                cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
                if bg_hex:
                    set_cell_shading(cell, bg_hex)
                set_cell_margins(cell, top=48, bottom=48, left=75, right=75)
                p = cell.paragraphs[0]
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER if ci in center_set else WD_ALIGN_PARAGRAPH.LEFT
                p.paragraph_format.first_line_indent = Cm(0)
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.line_spacing = 1.1
                r = p.add_run(str(val))
                set_run_font(r, size_pt=font_pt, bold=False)

        sp = self.doc.add_paragraph()
        sp.paragraph_format.space_before = Pt(0)
        sp.paragraph_format.space_after = Pt(3)
        sp.paragraph_format.line_spacing = 1.0
        return cap_full
