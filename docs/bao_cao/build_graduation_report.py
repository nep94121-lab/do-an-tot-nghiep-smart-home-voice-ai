#!/usr/bin/env python3
"""Rerunnable Graduation Report Generator (.docx) for Smart Home Voice AI.

Produces `Bao_Cao_DATN_Smart_Home_Voice_AI.docx` conforming strictly to:
- TEMPLATE_ANALYSIS.md (HUST SEEE thesis format, A4, Left 3.5cm, R/T/B 2.0cm, Times New Roman)
- GRILL_ANSWERS.md (Q1-Q6, Q12: double-border cover, yellow [ĐIỀN: ...], dashed [ẢNH THỰC TẾ: ...],
  real Word TOC / List of Figures / List of Tables / SEQ fields, Table captions ABOVE, Figure captions BELOW)
- Hardware SSOT (`hardware/wiring_contract.py`, `bom.csv`, `WIRING_TABLE.md`, `hardware/in 3 d/README.md`)
- Dynamic Phase 1C integration: automatically embeds `clean15_apk_*.png` and `apk_test_results.json`
  from `--run-dir` when present, otherwise inserts clean framed placeholders.

Usage:
    python docs/bao_cao/build_graduation_report.py
    python docs/bao_cao/build_graduation_report.py --line-spacing 1.15 --run-dir C:\\Users\\LENOVO\\datn-wt\\agyclean15_20261128
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

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
from docx.enum.text import WD_ALIGN_PARAGRAPH


DEFAULT_OUTPUT = SCRIPT_DIR / "Bao_Cao_DATN_Smart_Home_Voice_AI.docx"
DEFAULT_ASSETS = SCRIPT_DIR / "assets"
DEFAULT_RUN_DIR = pathlib.Path(r"C:\Users\LENOVO\datn-wt\agyclean15_20261128")


def build_report(
    output_path: pathlib.Path,
    assets_dir: pathlib.Path,
    run_dir: pathlib.Path,
    line_spacing: float = 1.3,
) -> dict:
    rb = ReportBuilder(line_spacing=line_spacing)

    # 1. Front Matter (Pages 1-2 Cover/Inner Cover w/ double border; Pages 3-10 Roman numerals i..viii)
    build_front_matter(rb)

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
    build_chapter_5(rb, assets_dir, run_dir)
    build_chapter_6(rb)
    build_references(rb)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    rb.doc.save(str(output_path))

    # Collect deterministic build summary
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
        "figures": rb.figure_registry,
        "tables": rb.table_registry,
        "assets_counts": {
            "logos_png": len(list((assets_dir / "logos").glob("*.png"))) if (assets_dir / "logos").exists() else 0,
            "demo_png": len(list((assets_dir / "demo").glob("*.png"))) if (assets_dir / "demo").exists() else 0,
            "software_png": len(list((assets_dir / "software").glob("*.png"))) if (assets_dir / "software").exists() else 0,
            "apk_screens_detected": len(list((run_dir / "screens").glob("clean15_apk_*.png"))) if (run_dir / "screens").exists() else 0,
        },
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Build HUST Graduation Report .docx for Smart Home Voice AI")
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT, help="Output .docx path")
    parser.add_argument("--assets-dir", type=pathlib.Path, default=DEFAULT_ASSETS, help="Assets root directory")
    parser.add_argument("--run-dir", type=pathlib.Path, default=DEFAULT_RUN_DIR, help="Session run directory for dynamic APK screens/results")
    parser.add_argument("--line-spacing", type=float, default=1.3, help="Body line spacing multiplier (default: 1.3 HUST; option: 1.15)")
    parser.add_argument("--summary-json", type=pathlib.Path, default=None, help="Optional JSON receipt output path")
    args = parser.parse_args()

    summary = build_report(
        output_path=args.output,
        assets_dir=args.assets_dir,
        run_dir=args.run_dir,
        line_spacing=args.line_spacing,
    )
    if args.summary_json:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"BUILT OK: {summary['output_docx']} ({summary['size_bytes']:,} bytes) | "
        f"line_spacing={summary['line_spacing']} | figures={summary['numbered_figures']} | "
        f"tables={summary['numbered_tables']} | paragraphs={summary['paragraphs_count']} | "
        f"assets={summary['assets_counts']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
