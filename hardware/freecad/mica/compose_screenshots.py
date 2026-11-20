"""Compose final high-resolution screenshots (>= 1400 px wide) into run directory.

Reads Coin3D offscreen renders from `render_freecad_views.py` and annotated drawings
from `export_drawings_and_verify.py`, produces crisp PNGs:
  - 12_mica_freecad_assembly.png
  - 13_mica_exploded.png
  - 14_mica_panel_drawings_sample.png
and removes temporary `_tmp_*` scratch files from `hardware/freecad/mica/`.
"""

from __future__ import annotations

import json
import pathlib
import sys

from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
DRAW_DIR = REPO_ROOT / "docs" / "phan_cung" / "mica" / "drawings"
SHOT_DIR = pathlib.Path(r"C:\Users\LENOVO\datn-wt\agyhwmica1_20261120\screenshots")

ASM_RGB = SCRIPT_DIR / "_tmp_assembly.rgb"
EXP_RGB = SCRIPT_DIR / "_tmp_exploded.rgb"
META_JSON = SCRIPT_DIR / "_tmp_render_meta.json"


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/calibrib.ttf"]
        if bold
        else ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/calibri.ttf"]
    )
    for path in candidates:
        if pathlib.Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _draw_banner(img: Image.Image, title: str, subtitle: str) -> None:
    draw = ImageDraw.Draw(img)
    w, h = img.size
    draw.rectangle([(0, 0), (w, 78)], fill=(15, 41, 66))
    draw.line([(0, 78), (w, 78)], fill=(56, 189, 248), width=3)
    draw.text((28, 14), title, fill=(255, 255, 255), font=_load_font(26, bold=True))
    draw.text((28, 48), subtitle, fill=(186, 230, 253), font=_load_font(16, bold=False))
    # Subtle footer
    draw.rectangle([(0, h - 36), (w, h)], fill=(241, 245, 249))
    draw.line([(0, h - 36), (w, h - 36)], fill=(203, 213, 225), width=2)
    draw.text(
        (28, h - 27),
        "FreeCAD 1.1.4 Parametric Model (hardware/freecad/mica/smarthome_mica_house.FCStd)  |  T = 3.0 mm (Verified 2 / 3 / 5 mm)  |  Zero Fan / AC / IR",
        fill=(51, 65, 85), font=_load_font(15, bold=False),
    )


def _draw_badge(draw: ImageDraw.ImageDraw, x: float, y: float, text: str, bg=(255, 255, 255), border=(15, 41, 66), fg=(15, 23, 42), font=None):
    if font is None:
        font = _load_font(15, bold=True)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y = 8, 5
    rx0, ry0 = int(x - tw / 2 - pad_x), int(y - th / 2 - pad_y)
    rx1, ry1 = int(x + tw / 2 + pad_x), int(y + th / 2 + pad_y)
    draw.rounded_rectangle([(rx0, ry0), (rx1, ry1)], radius=5, fill=bg, outline=border, width=2)
    draw.text((rx0 + pad_x - bbox[0], ry0 + pad_y - bbox[1]), text, fill=fg, font=font)


def _deconflict_labels(items: list[dict], min_dx: float = 115.0, min_dy: float = 30.0, y_min: float = 95.0, y_max: float = 1130.0):
    """Simple greedy vertical push to keep projected callout badges from overlapping."""
    placed = []
    # Sort top-to-bottom so pushes stay tidy
    for it in sorted(items, key=lambda d: (d["xy"][1], d["xy"][0])):
        lx, ly = float(it["xy"][0]), float(it["xy"][1])
        lx = max(95.0, min(1810.0, lx))
        ly = max(y_min, min(y_max, ly))
        for _ in range(12):
            hit = False
            for px, py in placed:
                if abs(lx - px) < min_dx and abs(ly - py) < min_dy:
                    ly = py + min_dy + 4.0
                    hit = True
            if not hit:
                break
        ly = max(y_min, min(y_max, ly))
        placed.append((lx, ly))
        it["label_xy"] = (lx, ly)
    return items


def compose_assembly(meta: dict) -> pathlib.Path:
    img = Image.open(ASM_RGB).convert("RGB")
    _draw_banner(
        img,
        "FreeCAD 3D Assembly — Smart Home Open-Cutaway Acrylic (Mica) House",
        "15 Interlocking Parametric Clear Acrylic Panels (356 x 178 x 135 mm House on 380 x 286 mm Base) + Real PCB & Modules",
    )
    draw = ImageDraw.Draw(img)

    # Clean hardware legend box in upper-left corner
    legend_x, legend_y = 26, 98
    legend_rows = [
        ("KiCad Hub PCB (80x65) + NodeMCU v2", (20, 115, 46)),
        ("2x 5V 1-Ch Relays (Blue & Red Opto)", (24, 82, 198)),
        ("PAM8403 Amp + Dia 28mm Mini Speaker", (140, 146, 156)),
        ("SG90 Door Servo + Hinged Door Leaf", (30, 115, 230)),
        ("DHT11 + KY-037 Mic + 12mm Buzzer", (210, 36, 40)),
        ("Submersible Pump + Soil Probe + LM393", (56, 165, 210)),
        ("2x 5mm Room LEDs + 3mm Power LED", (235, 185, 50)),
    ]
    draw.rounded_rectangle([(legend_x, legend_y), (legend_x + 365, legend_y + 236)], radius=8, fill=(255, 255, 255), outline=(148, 163, 184), width=2)
    draw.text((legend_x + 14, legend_y + 10), "REAL HARDWARE MODULES (VISIBLE):", fill=(15, 41, 66), font=_load_font(15, bold=True))
    f_leg = _load_font(14, bold=False)
    for idx, (txt, rgb) in enumerate(legend_rows):
        ry = legend_y + 40 + idx * 27
        draw.rectangle([(legend_x + 14, ry + 2), (legend_x + 32, ry + 18)], fill=rgb, outline=(30, 41, 59), width=1)
        draw.text((legend_x + 42, ry), txt, fill=(30, 41, 59), font=f_leg)

    # Callout badges for key hardware anchors
    wanted = {
        "PCB": "KiCad Hub PCB + NodeMCU",
        "RELAY1": "2x 5V Relays",
        "SPEAKER": "28mm Speaker + Fascia",
        "SG90": "SG90 Door Servo",
        "BUZZER": "12mm Buzzer",
        "DHT11": "DHT11 + Airflow",
        "KY037": "KY-037 Mic",
        "PUMP": "Submersible Pump",
        "SOIL_PROBE": "YL-69 Soil Probe",
        "LED_LR": "Living 5mm LED",
        "LED_BR": "Bedroom 5mm LED",
    }
    lbl_items = []
    for h in meta["hw_labels"]:
        if h["id"] in wanted:
            lbl_items.append({"text": wanted[h["id"]], "xy": h["xy"], "orig_xy": h["xy"]})

    # Manual nudge offsets to keep callouts crisp & away from legend
    nudge = {
        "KiCad Hub PCB + NodeMCU": (-140, 125),
        "2x 5V Relays": (-20, 155),
        "28mm Speaker + Fascia": (20, 175),
        "SG90 Door Servo": (-170, -45),
        "12mm Buzzer": (15, -75),
        "DHT11 + Airflow": (-65, -75),
        "KY-037 Mic": (-10, 45),
        "Submersible Pump": (125, 110),
        "YL-69 Soil Probe": (155, -25),
        "Living 5mm LED": (-90, -60),
        "Bedroom 5mm LED": (85, -60),
    }
    for it in lbl_items:
        dx, dy = nudge.get(it["text"], (0, -45))
        it["xy"] = (it["orig_xy"][0] + dx, it["orig_xy"][1] + dy)

    _deconflict_labels(lbl_items, min_dx=155.0, min_dy=32.0, y_min=96.0, y_max=1140.0)
    f_badge = _load_font(14, bold=True)
    for it in lbl_items:
        ox, oy = it["orig_xy"]
        lx, ly = it["label_xy"]
        draw.line([(ox, oy), (lx, ly)], fill=(15, 41, 66), width=2)
        draw.ellipse([(ox - 4, oy - 4), (ox + 4, oy + 4)], fill=(220, 38, 38), outline=(255, 255, 255), width=1)
        _draw_badge(draw, lx, ly, it["text"], bg=(255, 255, 255), border=(15, 41, 66), fg=(15, 41, 66), font=f_badge)

    out = SHOT_DIR / "12_mica_freecad_assembly.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out), optimize=True)
    return out


def compose_exploded(meta: dict) -> pathlib.Path:
    img = Image.open(EXP_RGB).convert("RGB")
    _draw_banner(
        img,
        "FreeCAD 3D Exploded View — All 15 Parametric Acrylic Panels & Panel IDs",
        "Tab-and-Slot Interlocking Finger Joints (55 Joint Pairs, Slot Width = T + 0.15 mm) — Red Dashed Lines Show Assembly Axis",
    )
    draw = ImageDraw.Draw(img)

    items = []
    for e in meta["exp_labels"]:
        items.append({
            "text": e["panel_id"],
            "xy": list(e["xy"]),
            "orig_xy": e["ctr_xy"],
        })

    # Clean directional offsets so all 15 panel IDs spread evenly around their panels
    offsets = {
        "P01_BASE": (0, 125),
        "P02_WALL_BACK": (45, -70),
        "P03_WALL_LEFT": (-130, -35),
        "P04_WALL_RIGHT": (130, -35),
        "P05_WALL_FRONT": (-85, -35),
        "P06_WALL_MID": (0, -65),
        "P07_SERVO_SHELF": (-110, -45),
        "P08_DOOR_LEAF": (-115, 55),
        "P09_GARDEN_LEFT": (-30, 80),
        "P10_WATER_DIVIDER": (65, 65),
        "P11_GARDEN_RIGHT": (135, 35),
        "P12_GARDEN_FRONT": (75, 115),
        "P13_GARDEN_BACK": (125, -25),
        "P14_SOIL_BRIDGE": (105, -55),
        "P15_TECH_FASCIA": (-120, 95),
    }
    for it in items:
        dx, dy = offsets.get(it["text"], (0, -30))
        it["xy"] = (it["xy"][0] + dx, it["xy"][1] + dy)

    _deconflict_labels(items, min_dx=145.0, min_dy=30.0, y_min=98.0, y_max=1140.0)
    f_badge = _load_font(15, bold=True)
    for it in items:
        ox, oy = it["orig_xy"]
        lx, ly = it["label_xy"]
        draw.line([(ox, oy), (lx, ly)], fill=(220, 38, 38), width=2)
        draw.ellipse([(ox - 4, oy - 4), (ox + 4, oy + 4)], fill=(220, 38, 38), outline=(255, 255, 255), width=1)
        _draw_badge(draw, lx, ly, it["text"], bg=(255, 255, 255), border=(185, 28, 28), fg=(15, 23, 42), font=f_badge)

    out = SHOT_DIR / "13_mica_exploded.png"
    img.save(str(out), optimize=True)
    return out


def compose_drawings_sample() -> pathlib.Path:
    """Create a razor-sharp 2x2 showcase sheet of 4 key dimensioned A4 drawings (2600 x 1860 px)."""
    picks = ["P01_BASE.png", "P02_WALL_BACK.png", "P05_WALL_FRONT.png", "P15_TECH_FASCIA.png"]
    imgs = [Image.open(DRAW_DIR / name).convert("RGB") for name in picks]

    # Each tile at 1280 x 905 keeps every single A4 drawing number & datum table crisp!
    tw, th = 1280, 905
    pad = 24
    header_h = 74
    W = tw * 2 + pad * 3
    H = header_h + th * 2 + pad * 3
    canvas = Image.new("RGB", (W, H), (226, 232, 240))
    draw = ImageDraw.Draw(canvas)

    draw.rectangle([(0, 0), (W, header_h)], fill=(15, 41, 66))
    draw.text(
        (pad, 14),
        "Dimensioned Panel Drawings Sample — Ready for Laser Cutting & A4 Printing (4 of 15 Panels Shown)",
        fill=(255, 255, 255), font=_load_font(26, bold=True),
    )
    draw.text(
        (pad, 46),
        "Full set of 15 panels (PDF + PNG + 1:1 mm DXF) in docs/phan_cung/mica/  |  Bottom-Left Datum (0,0)  |  Exact KiCad H1..H4 & Datasheet Holes",
        fill=(186, 230, 253), font=_load_font(16, bold=False),
    )

    positions = [
        (pad, header_h + pad),
        (pad * 2 + tw, header_h + pad),
        (pad, header_h + pad * 2 + th),
        (pad * 2 + tw, header_h + pad * 2 + th),
    ]
    for im, (px, py) in zip(imgs, positions):
        resized = im.resize((tw, th), Image.Resampling.LANCZOS)
        canvas.paste(resized, (px, py))
        draw.rectangle([(px - 1, py - 1), (px + tw, py + th)], outline=(15, 41, 66), width=2)

    out = SHOT_DIR / "14_mica_panel_drawings_sample.png"
    canvas.save(str(out), optimize=True)
    return out


def compose_exploded_sheet_doc(exploded_png: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    """Compose crisp publication-grade docs/phan_cung/mica/assembly_exploded.png & .pdf combining
    the Coin3D FreeCAD exploded view (zero occluded labels) with the 8-step assembly sidebar."""
    exp_im = Image.open(exploded_png).convert("RGB")
    # Crop main 3D area (exclude top banner 78px and bottom footer 36px)
    ew, eh = exp_im.size
    body = exp_im.crop((0, 78, ew, eh - 36))

    W, H = 2400, 1500
    canvas = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    # Top header
    draw.rectangle([(0, 0), (W, 86)], fill=(15, 41, 66))
    draw.line([(0, 86), (W, 86)], fill=(56, 189, 248), width=4)
    draw.text(
        (32, 16),
        "SMART HOME OPEN-CUTAWAY ACRYLIC HOUSE — EXPLODED ASSEMBLY & 8-STEP BUILD ORDER",
        fill=(255, 255, 255), font=_load_font(28, bold=True),
    )
    draw.text(
        (32, 52),
        "15 Parametric Clear Cast Acrylic Panels (T = 3.0 mm; verified 2/3/5 mm)  |  55 Interlocking Tab-and-Slot Joints (Kerf +0.15 mm)  |  Zero Fan / AC / IR",
        fill=(186, 230, 253), font=_load_font(17, bold=False),
    )

    # Left 3D exploded FreeCAD panel
    left_w = 1790
    left_h = H - 86 - 48
    body_resized = body.resize((left_w, left_h), Image.Resampling.LANCZOS)
    canvas.paste(body_resized, (16, 98))
    draw.rectangle([(16, 98), (16 + left_w, 98 + left_h)], outline=(30, 58, 95), width=2)

    # Right 8-step assembly sidebar
    sx0, sx1 = 1824, W - 20
    draw.rectangle([(sx0, 98), (sx1, 98 + left_h)], fill=(248, 250, 252), outline=(30, 58, 95), width=2)
    draw.rectangle([(sx0, 98), (sx1, 144)], fill=(30, 58, 95))
    draw.text((sx0 + 18, 108), "ASSEMBLY ORDER (8 STEPS)", fill=(255, 255, 255), font=_load_font(20, bold=True))

    steps = [
        ("Step 1: Prepare P01_BASE", "Install 4x M3x10 standoffs (KiCad H1..H4),\n8x M3x8 nylon standoffs (2x Relays), PAM8403 pad."),
        ("Step 2: Pre-mount P02_WALL_BACK", "Fit Living & Bedroom 5mm LEDs + DHT11 module\n(M3 over airflow vent); slot P02 into P01_BASE."),
        ("Step 3: Lock P06_WALL_MID", "Engage 3 rear tabs into P02 vertical slots\nand drop 2 bottom tabs into P01_BASE."),
        ("Step 4: Attach P03 & P04 Side Walls", "Interlock rear finger tabs into P02 corner\nnotches; seat bottom tabs into P01_BASE."),
        ("Step 5: Install P07 + P05 Facade", "Bolt SG90 on P07 (2x M2), KY-037 + 12mm Buzzer\non P05; lock P05 onto P03, P04, P06 & Base."),
        ("Step 6: Hang P08_DOOR_LEAF", "Attach 2x mini hobby hinges to left jamb;\nconnect SG90 white horn to door linkage hole."),
        ("Step 7: Water & Garden Box (P09-P14)", "Interlock P09..P13; seal water seams; place\npump + 6/8mm tube; mount LM393; fit P14 bridge."),
        ("Step 8: Fit P15_TECH_FASCIA & Wire", "Clamp Dia 28mm speaker + 3mm LED on P15;\nslot into base; bolt PCB, NodeMCU & Dupont wires."),
    ]
    f_st = _load_font(17, bold=True)
    f_sd = _load_font(14, bold=False)
    y_cur = 158
    for title, desc in steps:
        draw.rounded_rectangle([(sx0 + 14, y_cur), (sx1 - 14, y_cur + 136)], radius=8, fill=(255, 255, 255), outline=(148, 163, 184), width=2)
        draw.text((sx0 + 26, y_cur + 12), title, fill=(12, 74, 110), font=f_st)
        draw.multiline_text((sx0 + 26, y_cur + 42), desc, fill=(51, 65, 85), font=f_sd, spacing=6)
        y_cur += 149

    # Footer
    draw.rectangle([(0, H - 36), (W, H)], fill=(241, 245, 249))
    draw.text(
        (32, H - 28),
        "Source: hardware/freecad/mica/smarthome_mica_house.FCStd  |  All 15 DXFs & A4 Drawings in docs/phan_cung/mica/  |  3x A3 Sheets Required",
        fill=(51, 65, 85), font=_load_font(16, bold=False),
    )

    out_png = REPO_ROOT / "docs" / "phan_cung" / "mica" / "assembly_exploded.png"
    out_pdf = REPO_ROOT / "docs" / "phan_cung" / "mica" / "assembly_exploded.pdf"
    canvas.save(str(out_png), optimize=True)
    canvas.save(str(out_pdf), "PDF", resolution=200.0)
    return out_png, out_pdf


def main() -> int:
    meta = json.loads(META_JSON.read_text(encoding="utf-8"))
    p12 = compose_assembly(meta)
    p13 = compose_exploded(meta)
    p14 = compose_drawings_sample()
    epng, epdf = compose_exploded_sheet_doc(p13)
    for p in (p12, p13, p14, epng):
        im = Image.open(p)
        print(f"[compose] Saved {p} ({im.size[0]}x{im.size[1]}, {p.stat().st_size:,} bytes)")
    print(f"[compose] Saved {epdf} ({epdf.stat().st_size:,} bytes)")

    # Remove temporary scratch files inside repo
    for tmp in (ASM_RGB, EXP_RGB, META_JSON):
        if tmp.exists():
            tmp.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
