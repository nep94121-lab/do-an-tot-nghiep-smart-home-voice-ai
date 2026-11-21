"""Compose all 5 MICA2 high-resolution screenshots (100..104) into run screenshots dir
and update docs/phan_cung/mica/assembly_exploded.{png,pdf} with the FreeCAD Coin3D render.

Outputs in C:\\Users\\LENOVO\\datn-wt\\agyhwmica2_20261121\\screenshots\\:
  - 100_mica_3d_assembled.png
  - 101_mica_exploded.png
  - 102_mica_pcb_plate_drawing.png
  - 103_mica_sheet_layout_A3.png
  - 104_mica_internal_layout.png

Also removes temporary `_tmp_*` scratch files from `hardware/freecad/mica/`.
"""

from __future__ import annotations

import json
import pathlib
import shutil

from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
DOCS_MICA_DIR = REPO_ROOT / "docs" / "phan_cung" / "mica"
DRAW_DIR = DOCS_MICA_DIR / "drawings"
SHOT_DIR = pathlib.Path(r"C:\Users\LENOVO\datn-wt\agyhwmica2_20261121\screenshots")

ASM_RGB = SCRIPT_DIR / "_tmp_assembly.rgb"
EXP_RGB = SCRIPT_DIR / "_tmp_exploded.rgb"
INT_RGB = SCRIPT_DIR / "_tmp_internal_layout.rgb"
META_JSON = SCRIPT_DIR / "_tmp_render_meta.json"
VER_JSON = DOCS_MICA_DIR / "verification_report.json"


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


def _draw_banner(img: Image.Image, title: str, subtitle: str, footer_extra: str = "") -> None:
    draw = ImageDraw.Draw(img)
    w, h = img.size
    draw.rectangle([(0, 0), (w, 80)], fill=(15, 41, 66))
    draw.line([(0, 80), (w, 80)], fill=(56, 189, 248), width=3)
    draw.text((28, 12), title, fill=(255, 255, 255), font=_load_font(25, bold=True))
    draw.text((28, 48), subtitle, fill=(186, 230, 253), font=_load_font(15, bold=False))

    draw.rectangle([(0, h - 36), (w, h)], fill=(241, 245, 249))
    draw.line([(0, h - 36), (w, h - 36)], fill=(203, 213, 225), width=2)
    footer = (
        "FreeCAD 1.1.4 Parametric Model (hardware/freecad/mica/smarthome_mica_house.FCStd)  |  "
        "T = 3.0 mm (Verified 2 / 3 / 5 mm), tab_clr = 0.25 mm  |  Zero Fan / AC / IR"
    )
    if footer_extra:
        footer += "  |  " + footer_extra
    draw.text((28, h - 27), footer, fill=(51, 65, 85), font=_load_font(14, bold=False))


def _badge_box(draw: ImageDraw.ImageDraw, x: float, y: float, text: str, font, pad_x: int = 8, pad_y: int = 4):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    return (
        int(x - tw / 2 - pad_x),
        int(y - th / 2 - pad_y),
        int(x + tw / 2 + pad_x),
        int(y + th / 2 + pad_y),
        bbox,
        pad_x,
        pad_y,
    )


def _draw_badge(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    text: str,
    bg=(255, 255, 255),
    border=(15, 41, 66),
    fg=(15, 23, 42),
    font=None,
):
    if font is None:
        font = _load_font(14, bold=True)
    rx0, ry0, rx1, ry1, bbox, pad_x, pad_y = _badge_box(draw, x, y, text, font)
    draw.rounded_rectangle([(rx0, ry0), (rx1, ry1)], radius=5, fill=bg, outline=border, width=2)
    draw.text((rx0 + pad_x - bbox[0], ry0 + pad_y - bbox[1]), text, fill=fg, font=font)


def _deconflict_labels(
    items: list[dict],
    min_dx: float = 155.0,
    min_dy: float = 34.0,
    x_min: float = 115.0,
    x_max: float = 1805.0,
    y_min: float = 98.0,
    y_max: float = 1138.0,
):
    """Greedy vertical deconfliction keeping all badge centers inside safe viewport margins."""
    placed: list[tuple[float, float]] = []
    for it in sorted(items, key=lambda d: (d["xy"][1], d["xy"][0])):
        lx = max(x_min, min(x_max, float(it["xy"][0])))
        ly = max(y_min, min(y_max, float(it["xy"][1])))
        for _ in range(18):
            hit = False
            for px, py in placed:
                if abs(lx - px) < min_dx and abs(ly - py) < min_dy:
                    ly = py + min_dy + 4.0
                    hit = True
            if not hit:
                break
        if ly > y_max:
            ly = y_max
            for _ in range(18):
                hit = False
                for px, py in placed:
                    if abs(lx - px) < min_dx and abs(ly - py) < min_dy:
                        ly = py - min_dy - 4.0
                        hit = True
                if not hit:
                    break
        ly = max(y_min, min(y_max, ly))
        placed.append((lx, ly))
        it["label_xy"] = (lx, ly)
    return items


def compose_100_assembled(meta: dict) -> pathlib.Path:
    img = Image.open(ASM_RGB).convert("RGB")
    _draw_banner(
        img,
        "MICA2 FreeCAD 3D Assembly — Enlarged Open-Cutaway Acrylic House",
        "18 Unique Panels (19 Pieces, 59 Tab-Slot Joints) on 406 x 390 mm Split Base | 100x80 Hub PCB on P16_PCB_PLATE + 14 Off-Board Modules",
    )
    draw = ImageDraw.Draw(img)

    # Clean hardware legend in upper-left corner
    lx, ly = 24, 96
    legend_rows = [
        ("100x80 Hub PCB + NodeMCU on P16_PCB_PLATE", (20, 115, 46)),
        ("2x 5V 1-Ch Relays (Pump D6 & Amp D7)", (24, 82, 198)),
        ("PAM8403 Amp + Dia 28mm Mini Speaker", (140, 146, 156)),
        ("DC-022 5V Barrel Jack + 3mm Power LED", (45, 48, 55)),
        ("SG90 Door Servo + Hinged Door Leaf", (30, 115, 230)),
        ("DHT11 + KY-037 Sound Mic + 12mm Buzzer", (210, 36, 40)),
        ("Submersible Pump + YL-69 Probe + LM393", (56, 165, 210)),
        ("2x 5mm Room LEDs (Living D0 & Bed D4)", (235, 185, 50)),
    ]
    draw.rounded_rectangle(
        [(lx, ly), (lx + 382, ly + 258)],
        radius=8, fill=(255, 255, 255), outline=(148, 163, 184), width=2
    )
    draw.text((lx + 14, ly + 10), "REAL HARDWARE MODULES (17 SOLIDS):", fill=(15, 41, 66), font=_load_font(14, bold=True))
    f_leg = _load_font(13, bold=False)
    for idx, (txt, rgb) in enumerate(legend_rows):
        ry = ly + 38 + idx * 26
        draw.rectangle([(lx + 14, ry + 2), (lx + 30, ry + 16)], fill=rgb, outline=(30, 41, 59), width=1)
        draw.text((lx + 38, ry), txt, fill=(30, 41, 59), font=f_leg)

    wanted = {
        "PCB": "100x80 Hub PCB + P16 Plate",
        "RELAY1": "2x 5V Relays",
        "DC_JACK": "DC-022 5V Jack",
        "SPEAKER": "28mm Speaker + Fascia",
        "SG90": "SG90 Door Servo",
        "BUZZER": "12mm Buzzer",
        "DHT11": "DHT11 + Vent",
        "KY037": "KY-037 Mic",
        "PUMP": "Submersible Pump",
        "SOIL_PROBE": "YL-69 Soil Probe",
        "LM393": "LM393 Board",
        "LED_LR": "Living 5mm LED",
        "LED_BR": "Bedroom 5mm LED",
    }
    nudge = {
        "100x80 Hub PCB + P16 Plate": (-175, 100),
        "DC-022 5V Jack": (-180, 145),
        "2x 5V Relays": (-55, 165),
        "28mm Speaker + Fascia": (10, 175),
        "SG90 Door Servo": (-175, -55),
        "12mm Buzzer": (10, -78),
        "DHT11 + Vent": (-75, -75),
        "KY-037 Mic": (-15, 42),
        "Submersible Pump": (145, 95),
        "YL-69 Soil Probe": (170, -18),
        "LM393 Board": (140, 118),
        "Living 5mm LED": (-95, -62),
        "Bedroom 5mm LED": (95, -60),
    }

    lbl_items = []
    for h in meta["hw_labels_asm"]:
        if h["id"] in wanted:
            txt = wanted[h["id"]]
            dx, dy = nudge.get(txt, (0, -45))
            lbl_items.append({
                "text": txt,
                "orig_xy": h["xy"],
                "xy": (h["xy"][0] + dx, h["xy"][1] + dy),
            })

    _deconflict_labels(lbl_items, min_dx=175.0, min_dy=34.0, y_min=98.0, y_max=1140.0)
    f_badge = _load_font(13, bold=True)
    for it in lbl_items:
        ox, oy = it["orig_xy"]
        lx_p, ly_p = it["label_xy"]
        draw.line([(ox, oy), (lx_p, ly_p)], fill=(15, 41, 66), width=2)
        draw.ellipse([(ox - 4, oy - 4), (ox + 4, oy + 4)], fill=(220, 38, 38), outline=(255, 255, 255), width=1)
        _draw_badge(draw, lx_p, ly_p, it["text"], bg=(255, 255, 255), border=(15, 41, 66), fg=(15, 41, 66), font=f_badge)

    out = SHOT_DIR / "100_mica_3d_assembled.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out), optimize=True)
    return out


def compose_101_exploded(meta: dict) -> pathlib.Path:
    img = Image.open(EXP_RGB).convert("RGB")
    _draw_banner(
        img,
        "MICA2 FreeCAD 3D Exploded View — All 18 Unique Panels (19 Physical Pieces)",
        "59 Interlocking Tab-Slot Joints (tab_clr = 0.25 mm, min tab 14 mm) | Split A3 Base (P01A+P01B+2xP17) + Removable P16_PCB_PLATE",
    )
    draw = ImageDraw.Draw(img)

    offsets = {
        "P01A_BASE_TECH": (-140, 115),
        "P01B_BASE_HOUSE": (175, 48),
        "P02_WALL_BACK": (55, -78),
        "P03_WALL_LEFT": (-165, -45),
        "P04_WALL_RIGHT": (165, -30),
        "P05_WALL_FRONT": (-235, -82),
        "P06_WALL_MID": (5, -75),
        "P07_SERVO_SHELF": (-185, -32),
        "P08_DOOR_LEAF": (-165, 58),
        "P09_GARDEN_LEFT": (-30, 82),
        "P10_WATER_DIVIDER": (95, 58),
        "P11_GARDEN_RIGHT": (175, 22),
        "P12_GARDEN_FRONT": (125, 160),
        "P13_GARDEN_BACK": (165, -28),
        "P14_SOIL_BRIDGE": (135, -62),
        "P15_TECH_FASCIA": (-175, 92),
        "P16_PCB_PLATE": (-185, -52),
        "P17_BASE_JOINER_L": (-70, 145),
        "P17_BASE_JOINER_R": (145, 105),
    }
    items = []
    for e in meta["exp_labels"]:
        pid = e["panel_id"]
        dx, dy = offsets.get(pid, (0, -30))
        items.append({
            "text": pid,
            "orig_xy": e["ctr_xy"],
            "xy": (e["xy"][0] + dx, e["xy"][1] + dy),
        })

    _deconflict_labels(items, min_dx=178.0, min_dy=32.0, x_min=118.0, x_max=1802.0, y_min=96.0, y_max=1142.0)
    f_badge = _load_font(13, bold=True)
    for it in items:
        ox, oy = it["orig_xy"]
        lx_p, ly_p = it["label_xy"]
        is_new = it["text"].startswith(("P01A", "P01B", "P16", "P17"))
        border = (21, 128, 61) if is_new else (185, 28, 28)
        bg = (240, 253, 244) if is_new else (255, 255, 255)
        draw.line([(ox, oy), (lx_p, ly_p)], fill=border, width=2)
        draw.ellipse([(ox - 4, oy - 4), (ox + 4, oy + 4)], fill=border, outline=(255, 255, 255), width=1)
        _draw_badge(draw, lx_p, ly_p, it["text"], bg=bg, border=border, fg=(15, 23, 42), font=f_badge)

    out = SHOT_DIR / "101_mica_exploded.png"
    img.save(str(out), optimize=True)
    return out


def compose_102_and_103() -> tuple[pathlib.Path, pathlib.Path]:
    """Copy native high-res matplotlib engineering renders for 102 (P16 PCB Plate) and 103 (A3 Nesting)."""
    src_102 = DRAW_DIR / "P16_PCB_PLATE.png"
    src_103 = DOCS_MICA_DIR / "sheet_layout_A3.png"
    dst_102 = SHOT_DIR / "102_mica_pcb_plate_drawing.png"
    dst_103 = SHOT_DIR / "103_mica_sheet_layout_A3.png"
    shutil.copy2(src_102, dst_102)
    shutil.copy2(src_103, dst_103)
    return dst_102, dst_103


def compose_104_internal_layout(meta: dict) -> pathlib.Path:
    img = Image.open(INT_RGB).convert("RGB")
    _draw_banner(
        img,
        "MICA2 FreeCAD Internal Layout — 100x80 Hub PCB + All 14 Off-Board Modules",
        "High-Angle Cutaway View (Walls 80% Translucent) | >= 15 mm Wiring Clearances Verified (Min 18.0 mm Across 135 Non-Mated Pairs)",
    )
    draw = ImageDraw.Draw(img)

    hw_map = {h["id"]: h["mid_xy"] for h in meta["hw_labels_int"]}
    zones = meta["zone_anchors"]

    # Place callouts cleanly in Left, Top, and Right columns -> ZERO overlap & ZERO center occlusion!
    left_col = [
        ("LED_LR", "1. Living 5mm LED (D0)", (217, 119, 6)),
        ("SG90", "2. SG90 Door Servo (D1)", (29, 78, 216)),
        ("NODEMCU", "3. NodeMCU v2 Amica (on PCB)", (15, 23, 42)),
        ("PCB", "4. Hub PCB 100x80 mm (90x70 M3)", (21, 128, 61)),
        ("__P16__", "P16_PCB_PLATE 130x110 (15mm margin)", (15, 118, 110)),
        ("LED_PWR", "5. 3mm Power LED (Fascia)", (22, 163, 74)),
        ("DC_JACK", "6. DC-022 5V 2A Barrel Jack", (30, 41, 59)),
    ]
    top_row = [
        ("DHT11", "7. DHT11 Sensor + Vent (D2)", (2, 132, 199), 760, 116),
        ("BUZZER", "8. TMB12A05 12mm Buzzer (D8)", (15, 23, 42), 1070, 116),
        ("LED_BR", "9. Bedroom 5mm LED (D4)", (217, 119, 6), 1375, 116),
    ]
    right_col = [
        ("KY037", "10. KY-037 Sound Mic (D5)", (185, 28, 28)),
        ("RELAY1", "11. Relay 1 Blue SRD-05VDC (D6)", (29, 78, 216)),
        ("RELAY2", "12. Relay 2 Opto Audio Pwr (D7)", (185, 28, 28)),
        ("PUMP", "13. 3-6V Submersible Pump + Tube", (2, 132, 199)),
        ("SOIL_PROBE", "14. YL-69 Soil Moisture Probe (A0)", (21, 128, 61)),
        ("LM393", "15. LM393 Soil Comparator (Dry Ext)", (29, 78, 216)),
        ("PAM8403", "16. PAM8403 3W Class-D Amp (D3)", (21, 128, 61)),
        ("SPEAKER", "17. Dia 28mm 8 Ohm Mini Speaker", (71, 85, 105)),
    ]

    f_badge = _load_font(13, bold=True)
    f_zone = _load_font(14, bold=True)

    # Left column badges (x = 188, evenly distributed from y=170 to y=1040)
    ly_start, ly_step = 185, 138
    for idx, (hid, label, col) in enumerate(left_col):
        target = zones["P16_PLATE"] if hid == "__P16__" else hw_map.get(hid)
        if not target:
            continue
        bx, by = 195.0, ly_start + idx * ly_step
        rx0, ry0, rx1, ry1, _, _, _ = _badge_box(draw, bx, by, label, f_badge)
        # Leader line from right edge of badge -> elbow -> target point
        draw.line([(rx1, by), (rx1 + 22, by), (target[0], target[1])], fill=col, width=2)
        draw.ellipse([(target[0] - 4.5, target[1] - 4.5), (target[0] + 4.5, target[1] + 4.5)], fill=col, outline=(255, 255, 255), width=2)
        bg = (240, 253, 244) if hid in ("PCB", "__P16__") else (255, 255, 255)
        _draw_badge(draw, bx, by, label, bg=bg, border=col, fg=(15, 23, 42), font=f_badge)

    # Top row badges
    for hid, label, col, bx, by in top_row:
        target = hw_map.get(hid)
        if not target:
            continue
        rx0, ry0, rx1, ry1, _, _, _ = _badge_box(draw, bx, by, label, f_badge)
        draw.line([(bx, ry1), (target[0], target[1])], fill=col, width=2)
        draw.ellipse([(target[0] - 4.5, target[1] - 4.5), (target[0] + 4.5, target[1] + 4.5)], fill=col, outline=(255, 255, 255), width=2)
        _draw_badge(draw, bx, by, label, bg=(255, 255, 255), border=col, fg=(15, 23, 42), font=f_badge)

    # Right column badges (x = 1720, evenly distributed from y=185 to y=1060)
    ry_start, ry_step = 185, 122
    for idx, (hid, label, col) in enumerate(right_col):
        target = hw_map.get(hid)
        if not target:
            continue
        bx, by = 1715.0, ry_start + idx * ry_step
        rx0, ry0, rx1, ry1, _, _, _ = _badge_box(draw, bx, by, label, f_badge)
        draw.line([(rx0, by), (rx0 - 22, by), (target[0], target[1])], fill=col, width=2)
        draw.ellipse([(target[0] - 4.5, target[1] - 4.5), (target[0] + 4.5, target[1] + 4.5)], fill=col, outline=(255, 255, 255), width=2)
        _draw_badge(draw, bx, by, label, bg=(255, 255, 255), border=col, fg=(15, 23, 42), font=f_badge)

    # Bottom-center wiring clearance verification callout badge
    wx, wy = 960.0, 1120.0
    wg_target = zones["WIRING_GAP"]
    draw.line([(wx, wy - 18), (wg_target[0], wg_target[1])], fill=(21, 128, 61), width=2)
    draw.ellipse([(wg_target[0] - 5, wg_target[1] - 5), (wg_target[0] + 5, wg_target[1] + 5)], fill=(21, 128, 61), outline=(255, 255, 255), width=2)
    _draw_badge(
        draw, wx, wy,
        "WIRING CORRIDORS VERIFIED: Min Gap = 18.0 mm (>= 15.0 mm req across all 135 non-mated pairs)  |  0 Overlaps  |  USB Cutaway Open",
        bg=(240, 253, 244), border=(21, 128, 61), fg=(20, 83, 45), font=f_zone,
    )

    out = SHOT_DIR / "104_mica_internal_layout.png"
    img.save(str(out), optimize=True)
    return out


def compose_exploded_sheet_doc(exploded_png: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    """Compose crisp publication-grade docs/phan_cung/mica/assembly_exploded.png & .pdf
    using the MICA2 FreeCAD Coin3D exploded render + updated 8-step MICA2 build sidebar."""
    a3_sheets = 4
    if VER_JSON.exists():
        vdata = json.loads(VER_JSON.read_text(encoding="utf-8"))
        a3_sheets = int(vdata.get("nesting_A3", {}).get("sheet_count", 4))

    exp_im = Image.open(exploded_png).convert("RGB")
    ew, eh = exp_im.size
    body = exp_im.crop((0, 80, ew, eh - 36))

    W, H = 2400, 1500
    canvas = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    draw.rectangle([(0, 0), (W, 88)], fill=(15, 41, 66))
    draw.line([(0, 88), (W, 88)], fill=(56, 189, 248), width=4)
    draw.text(
        (32, 14),
        "SMART HOME OPEN-CUTAWAY ACRYLIC HOUSE (MICA2) — EXPLODED ASSEMBLY & 9-STEP BUILD ORDER",
        fill=(255, 255, 255), font=_load_font(27, bold=True),
    )
    draw.text(
        (32, 52),
        "18 Unique Panels / 19 Pieces (T = 3.0 mm; verified 2/3/5 mm)  |  59 Tab-Slot Joints (tab_clr = 0.25 mm)  |  100x80 Hub PCB + 14 Modules  |  Zero Fan/AC/IR",
        fill=(186, 230, 253), font=_load_font(16, bold=False),
    )

    left_w = 1785
    left_h = H - 88 - 48
    body_resized = body.resize((left_w, left_h), Image.Resampling.LANCZOS)
    canvas.paste(body_resized, (16, 98))
    draw.rectangle([(16, 98), (16 + left_w, 98 + left_h)], outline=(30, 58, 95), width=2)

    sx0, sx1 = 1818, W - 18
    draw.rectangle([(sx0, 98), (sx1, 98 + left_h)], fill=(248, 250, 252), outline=(30, 58, 95), width=2)
    draw.rectangle([(sx0, 98), (sx1, 142)], fill=(30, 58, 95))
    draw.text((sx0 + 18, 107), "MICA2 ASSEMBLY ORDER (9 STEPS)", fill=(255, 255, 255), font=_load_font(19, bold=True))

    steps = [
        ("Step 1: Dry-Fit & Join Base (P01A+P01B+2xP17)", "Interlock P01A & P01B 24mm seam tabs; bolt 2x\nP17_BASE_JOINER underneath with 8x M3x10/12."),
        ("Step 2: Mount Hub PCB on P16_PCB_PLATE", "Bolt 100x80 PCB + NodeMCU (USB forward) on P16\n(90x70, 4x M3x10); mount P16 on P01A (4x M3x6)."),
        ("Step 3: Mount Relays & PAM8403 on P01A", "Mount Relay 1 (D6) & Relay 2 (D7, Jmp=H) on M3x8\nstandoffs; tie PAM8403 (D3); verify >=18mm gaps."),
        ("Step 4: Pre-Mount & Slot P02_WALL_BACK", "Fit Living/Bed 5mm LEDs (Ø5.5) + DHT11 (M3 over\n12.5x16 vent); slot P02 bottom tabs into P01B."),
        ("Step 5: Lock P06_WALL_MID, P03 & P04", "Slot P06 (w/ buzzer relief) into P02 & P01B;\ninterlock P03_WALL_LEFT & P04_WALL_RIGHT."),
        ("Step 6: Install P07_SERVO_SHELF + P05", "Mount SG90 on P07 (2x M2+washers), KY-037 &\n12mm Buzzer on P05; lock P05 onto P03/P04/P06."),
        ("Step 7: Hang Main Door P08_DOOR_LEAF", "Attach 2x mini hinges (Ø3.0 holes, 2mm gap all\nsides); connect SG90 horn push-rod to door link."),
        ("Step 8: Water/Garden Box (P09-P14) & Pump", "Interlock P09..P13; seal water tank w/ silicone &\n15m leak test; add pump/tube, LM393, P14+YL-69."),
        ("Step 9: Fit P15_TECH_FASCIA, Wire & Check", "Fit DC-022 (Ø12.5), 3mm LED & 28mm speaker on P15;\nroute 40 wires (Ø14 holes) & run boot-safety check."),
    ]
    f_st = _load_font(15, bold=True)
    f_sd = _load_font(13, bold=False)
    y_cur = 152
    for title, desc in steps:
        draw.rounded_rectangle([(sx0 + 12, y_cur), (sx1 - 12, y_cur + 122)], radius=8, fill=(255, 255, 255), outline=(148, 163, 184), width=2)
        draw.text((sx0 + 20, y_cur + 10), title, fill=(12, 74, 110), font=f_st)
        draw.multiline_text((sx0 + 20, y_cur + 38), desc, fill=(51, 65, 85), font=f_sd, spacing=5)
        y_cur += 133

    draw.rectangle([(0, H - 36), (W, H)], fill=(241, 245, 249))
    draw.text(
        (32, H - 28),
        f"Source: hardware/freecad/mica/smarthome_mica_house.FCStd  |  18 DXFs, PDF/PNG/SVG Drawings & holes_table.csv in docs/phan_cung/mica/  |  {a3_sheets}x A3 Sheets",
        fill=(51, 65, 85), font=_load_font(15, bold=False),
    )

    out_png = DOCS_MICA_DIR / "assembly_exploded.png"
    out_pdf = DOCS_MICA_DIR / "assembly_exploded.pdf"
    canvas.save(str(out_png), optimize=True)
    canvas.save(str(out_pdf), "PDF", resolution=200.0)
    return out_png, out_pdf


def main() -> int:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    meta = json.loads(META_JSON.read_text(encoding="utf-8"))

    p100 = compose_100_assembled(meta)
    p101 = compose_101_exploded(meta)
    p102, p103 = compose_102_and_103()
    p104 = compose_104_internal_layout(meta)
    epng, epdf = compose_exploded_sheet_doc(p101)

    for p in (p100, p101, p102, p103, p104, epng):
        im = Image.open(p)
        print(f"[compose] Saved {p} ({im.size[0]}x{im.size[1]}, {p.stat().st_size:,} bytes)")
    print(f"[compose] Saved {epdf} ({epdf.stat().st_size:,} bytes)")

    for tmp in (ASM_RGB, EXP_RGB, INT_RGB, META_JSON):
        if tmp.exists():
            tmp.unlink()
    print("[compose] Cleaned temporary _tmp_* scratch files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
