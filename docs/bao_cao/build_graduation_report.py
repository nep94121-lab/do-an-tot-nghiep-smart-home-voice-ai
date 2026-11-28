#!/usr/bin/env python3
"""Rerunnable Graduation Report Generator (.docx) for Smart Home Voice AI (v2).

Produces `Bao_Cao_DATN_Smart_Home_Voice_AI.docx` conforming strictly to:
- HUST SEEE thesis format (A4, Left 3.5cm, R/T/B 2.0cm, Times New Roman 13 pt, line spacing 1.3)
- Real official HUST emblem on Cover and Inner Cover (no logo placeholder)
- Natural Vietnamese student prose, electronic-circuit-centered hardware chapter, <= 1 page 3D housing
- Real text code listings (Consolas 10 pt, shaded bordered block, line numbers, 0 code screenshots)
- Four real Word TOC fields: MỤC LỤC, DANH MỤC HÌNH VẼ, DANH MỤC BẢNG BIỂU, DANH MỤC ĐOẠN MÃ
- Compressed image pipeline keeping final .docx well under 10 MB and 55-65 pages total

Usage:
    python docs/bao_cao/build_graduation_report.py
    python docs/bao_cao/build_graduation_report.py --summary-json build_summary.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from docx.enum.text import WD_ALIGN_PARAGRAPH
from report_sections.chapter_3 import build_chapter_3
from report_sections.chapter_4 import build_chapter_4
from report_sections.chapters_1_2 import build_chapter_1, build_chapter_2
from report_sections.chapters_5_6_refs import build_chapter_5, build_chapter_6, build_references
from report_sections.docx_helpers import (
    ReportBuilder,
    set_footer_page_number,
    set_section_page_border,
    set_section_page_numbering,
)
from report_sections.front_matter import build_front_matter


DEFAULT_OUTPUT = SCRIPT_DIR / "Bao_Cao_DATN_Smart_Home_Voice_AI.docx"
DEFAULT_ASSETS = SCRIPT_DIR / "assets"
DEFAULT_OPTIMIZED = DEFAULT_ASSETS / "optimized"
DEFAULT_RUN_DIR = pathlib.Path(r"C:\Users\LENOVO\datn-wt\agyreport16_20261128")
DEFAULT_APK_SCREENS_DIR = pathlib.Path(r"C:\Users\LENOVO\datn-wt\agyclean15_20261128\screens")


def build_report(
    output_path: pathlib.Path,
    assets_dir: pathlib.Path,
    run_dir: pathlib.Path,
    line_spacing: float = 1.3,
    optimize_dir: pathlib.Path | None = DEFAULT_OPTIMIZED,
    apk_screens_dir: pathlib.Path | None = DEFAULT_APK_SCREENS_DIR,
    comparison_sources_path: pathlib.Path | None = None,
) -> dict:
    rb = ReportBuilder(line_spacing=line_spacing, optimize_dir=optimize_dir)

    # 1. Front Matter (Covers with real HUST logo + Roman numerals i..ix including DANH MỤC ĐOẠN MÃ)
    build_front_matter(rb, assets_dir=assets_dir)

    # 2. Body Section (Arabic page numbers starting at 1, right-aligned footer, no page border)
    sec_body = rb.add_new_section()
    set_section_page_border(sec_body, double=False)
    set_section_page_numbering(sec_body, fmt="decimal", start=1)
    set_footer_page_number(sec_body, align=WD_ALIGN_PARAGRAPH.RIGHT, clear=False)

    # 3. Six Chapters + References
    build_chapter_1(rb, assets_dir)
    build_chapter_2(rb, assets_dir)
    build_chapter_3(rb, assets_dir)
    build_chapter_4(rb, assets_dir)
    build_chapter_5(rb, assets_dir, run_dir, apk_screens_dir=apk_screens_dir)
    build_chapter_6(rb)
    comp_path = comparison_sources_path or (run_dir / "build_receipts" / "comparison_sources.json")
    build_references(rb, comparison_sources_path=comp_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    rb.doc.save(str(output_path))

    summary = {
        "output_docx": str(output_path),
        "size_bytes": output_path.stat().st_size,
        "line_spacing": line_spacing,
        "run_dir": str(run_dir),
        "sections_count": len(rb.doc.sections),
        "paragraphs_count": len(rb.doc.paragraphs),
        "tables_total_xml": len(rb.doc.tables),
        "numbered_figures": rb.total_figures,
        "numbered_tables": rb.total_tables,
        "numbered_listings": rb.total_listings,
        "figures": rb.figure_registry,
        "tables": rb.table_registry,
        "listings": rb.listing_registry,
        "embedded_images": rb.embedded_images,
        "assets_counts": {
            "logos_png": len(list((assets_dir / "logos").glob("*.png"))) if (assets_dir / "logos").exists() else 0,
            "diagrams_png": len(list((assets_dir / "diagrams").glob("*.png"))) if (assets_dir / "diagrams").exists() else 0,
            "demo_png": len(list((assets_dir / "demo").glob("*.png"))) if (assets_dir / "demo").exists() else 0,
            "software_png": len(list((assets_dir / "software").glob("*.png"))) if (assets_dir / "software").exists() else 0,
        },
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Build HUST Graduation Report v2 .docx for Smart Home Voice AI")
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT, help="Output .docx path")
    parser.add_argument("--assets-dir", type=pathlib.Path, default=DEFAULT_ASSETS, help="Assets root directory")
    parser.add_argument("--optimize-dir", type=pathlib.Path, default=DEFAULT_OPTIMIZED, help="Optimized image cache dir")
    parser.add_argument("--run-dir", type=pathlib.Path, default=DEFAULT_RUN_DIR, help="Session run directory")
    parser.add_argument("--apk-screens-dir", type=pathlib.Path, default=DEFAULT_APK_SCREENS_DIR, help="Android APK screenshots dir")
    parser.add_argument("--comparison-sources", type=pathlib.Path, default=None, help="Verified comparison sources JSON")
    parser.add_argument("--line-spacing", type=float, default=1.3, help="Body line spacing multiplier (default: 1.3 HUST)")
    parser.add_argument("--summary-json", type=pathlib.Path, default=None, help="Optional JSON receipt output path")
    args = parser.parse_args()

    summary = build_report(
        output_path=args.output,
        assets_dir=args.assets_dir,
        run_dir=args.run_dir,
        line_spacing=args.line_spacing,
        optimize_dir=args.optimize_dir,
        apk_screens_dir=args.apk_screens_dir,
        comparison_sources_path=args.comparison_sources,
    )
    if args.summary_json:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"BUILT V2 OK: {summary['output_docx']} ({summary['size_bytes']:,} bytes) | "
        f"line_spacing={summary['line_spacing']} | figures={summary['numbered_figures']} | "
        f"tables={summary['numbered_tables']} | listings={summary['numbered_listings']} | "
        f"embedded_images={len(summary['embedded_images'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
