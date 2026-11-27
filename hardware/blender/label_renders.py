#!/usr/bin/env python3
"""Crisp Vietnamese Callout Labeler for Smart Home 3D Blender Renders (HW13 R2/R4).

Uses Pillow + Windows Segoe UI TrueType fonts (full Vietnamese diacritic support,
zero mojibake) and exact camera-projected 2D anchor coordinates from
`hardware/blender/render_projections.json` to overlay:
  - Top header banner (title + technical subtitle)
  - Non-overlapping rounded badges arranged cleanly in left/right/top/bottom rails
  - High-contrast leader lines with outlined target dots pointing precisely to each module
"""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
PROJ_JSON = REPO_ROOT / "hardware" / "blender" / "render_projections.json"

FONT_BOLD_PATH = r"C:\Windows\Fonts\segoeuib.ttf"
FONT_REG_PATH = r"C:\Windows\Fonts\segoeui.ttf"

# Category accent colors (R, G, B)
CAT_COLORS = {
    "power":    (239, 68, 68),    # Red-coral (PSU / J1)
    "pcb":      (34, 197, 94),    # Emerald (Hub PCB / NodeMCU)
    "servo":    (59, 130, 246),   # Royal blue (SG90 / Door mechanism)
    "coupler":  (249, 115, 22),   # Vivid orange (SUP10B / End-stops)
    "light":    (250, 204, 21),   # Warm gold (5mm LEDs)
    "audio":    (168, 85, 247),   # Purple (PAM8403 / Speaker / Buzzer)
    "relay":    (14, 165, 233),   # Sky cyan (Relays 1/2 / Switched outputs)
    "garden":   (16, 185, 129),   # Teal-green (Pump / Soil / LM393)
    "sensor":   (244, 114, 182),  # Pink-rose (DHT11 / KY-037)
}


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", size)


def draw_rounded_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    radius: int,
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int],
    width: int = 2,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def place_rail_badges(
    items: list[dict[str, Any]],
    side: str,
    img_w: int,
    img_h: int,
    font_lbl: ImageFont.FreeTypeFont,
    y_min: int = 92,
    y_max: int = 950,
    min_gap: int = 8,
) -> list[dict[str, Any]]:
    """Arrange badges along left or right margin sorted by anchor Y, resolving all vertical overlaps."""
    if not items:
        return []

    pad_x = 12
    pad_y = 6
    margin_x = 18

    enriched = []
    for it in items:
        bbox = font_lbl.getbbox(it["text"])
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        bw = tw + pad_x * 2 + 12  # +12 for left accent bar
        bh = max(30, th + pad_y * 2 + 2)
        enriched.append({**it, "bw": bw, "bh": bh, "y_target": it["py"] + it.get("y_off", 0)})

    enriched.sort(key=lambda d: d["y_target"])

    # Assign vertical centers with guaranteed minimum gap
    cur_y = float(y_min)
    for d in enriched:
        desired_top = d["y_target"] - d["bh"] / 2.0
        top = max(cur_y, desired_top)
        d["top"] = top
        cur_y = top + d["bh"] + min_gap

    # Push back up if bottom overflows y_max
    overflow = (enriched[-1]["top"] + enriched[-1]["bh"]) - y_max
    if overflow > 0:
        enriched[-1]["top"] -= overflow
        for i in range(len(enriched) - 2, -1, -1):
            max_top = enriched[i + 1]["top"] - enriched[i]["bh"] - min_gap
            if enriched[i]["top"] > max_top:
                enriched[i]["top"] = max_top
        # If top went above y_min, compress evenly
        if enriched[0]["top"] < y_min:
            total_h = sum(d["bh"] for d in enriched)
            avail = max(1, (y_max - y_min) - total_h)
            gap = max(3.0, avail / max(1, len(enriched) - 1))
            y = float(y_min)
            for d in enriched:
                d["top"] = y
                y += d["bh"] + gap

    for d in enriched:
        top = int(round(d["top"]))
        bot = top + d["bh"]
        if side == "left":
            x0 = margin_x
            x1 = x0 + d["bw"]
            conn_x = x1
        else:
            x1 = img_w - margin_x
            x0 = x1 - d["bw"]
            conn_x = x0
        d["box"] = (x0, top, x1, bot)
        d["conn"] = (conn_x, (top + bot) // 2)
        d["side"] = side
    return enriched


def render_labeled_image(
    raw_path: pathlib.Path,
    out_path: pathlib.Path,
    title: str,
    subtitle: str,
    labels_spec: list[tuple[str, str, str, str]],  # (anchor_key, label_vi, category, preferred_side 'auto'|'left'|'right')
    points_2d: dict[str, list[float]],
    footer_note: str = "",
) -> None:
    base = Image.open(raw_path).convert("RGBA")
    W, H = base.size
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font_title = load_font(FONT_BOLD_PATH, 24)
    font_sub = load_font(FONT_REG_PATH, 15)
    font_lbl = load_font(FONT_BOLD_PATH, 15)
    font_foot = load_font(FONT_REG_PATH, 13)

    # Top title bar (semi-transparent dark navy)
    draw.rectangle((0, 0, W, 74), fill=(11, 18, 34, 224))
    draw.rectangle((0, 72, W, 75), fill=(56, 189, 248, 220))
    draw.text((22, 12), title, font=font_title, fill=(248, 250, 252, 255))
    draw.text((22, 44), subtitle, font=font_sub, fill=(148, 163, 184, 255))

    # Split labels into left/right rails
    left_items: list[dict[str, Any]] = []
    right_items: list[dict[str, Any]] = []

    for entry in labels_spec:
        akey, text, cat, pref = entry[:4]
        y_off = entry[4] if len(entry) > 4 else 0
        if akey not in points_2d:
            continue
        px, py, _depth = points_2d[akey]
        # Clamp anchor into image if slightly near edge
        px_c = max(40.0, min(W - 40.0, float(px)))
        py_c = max(84.0, min(H - 36.0, float(py)))
        item = {
            "key": akey,
            "text": text,
            "cat": cat,
            "color": CAT_COLORS.get(cat, (56, 189, 248)),
            "px": px_c,
            "py": py_c,
            "y_off": y_off,
        }
        if pref == "left":
            left_items.append(item)
        elif pref == "right":
            right_items.append(item)
        else:
            if px_c < W * 0.50:
                left_items.append(item)
            else:
                right_items.append(item)

    y_bottom_limit = H - (42 if footer_note else 16)
    placed = (
        place_rail_badges(left_items, "left", W, H, font_lbl, y_min=88, y_max=y_bottom_limit)
        + place_rail_badges(right_items, "right", W, H, font_lbl, y_min=88, y_max=y_bottom_limit)
    )

    # 1. Draw leader lines first (behind badges)
    for d in placed:
        cx, cy = d["conn"]
        px, py = int(round(d["px"])), int(round(d["py"]))
        col = d["color"]
        elbow_x = cx + (18 if d["side"] == "left" else -18)
        pts = [(cx, cy), (elbow_x, cy), (px, py)]
        # Dark halo stroke for contrast on any background
        draw.line(pts, fill=(8, 13, 25, 220), width=5, joint="curve")
        draw.line(pts, fill=(*col, 245), width=2, joint="curve")
        # Target dot
        r = 5
        draw.ellipse((px - r - 2, py - r - 2, px + r + 2, py + r + 2), fill=(8, 13, 25, 240))
        draw.ellipse((px - r, py - r, px + r, py + r), fill=(*col, 255), outline=(255, 255, 255, 255), width=2)

    # 2. Draw crisp rounded badges
    for d in placed:
        x0, y0, x1, y1 = d["box"]
        col = d["color"]
        draw_rounded_box(
            draw,
            (x0, y0, x1, y1),
            radius=7,
            fill=(15, 23, 42, 232),
            outline=(*col, 240),
            width=2,
        )
        # Left color accent bar
        draw.rounded_rectangle((x0 + 2, y0 + 2, x0 + 8, y1 - 2), radius=3, fill=(*col, 255))
        draw.text((x0 + 16, y0 + 6), d["text"], font=font_lbl, fill=(248, 250, 252, 255))

    if footer_note:
        draw.rectangle((0, H - 30, W, H), fill=(11, 18, 34, 218))
        draw.text((20, H - 24), footer_note, font=font_foot, fill=(203, 213, 225, 255))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    composed = Image.alpha_composite(base, overlay).convert("RGB")
    composed.save(out_path, format="PNG", optimize=True)
    print(f"[LABEL] Wrote {out_path} ({out_path.stat().st_size} bytes, {len(placed)} Vietnamese labels)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--proj-json", type=pathlib.Path, default=PROJ_JSON)
    ap.add_argument("--out-dir", type=pathlib.Path, required=True)
    args = ap.parse_args()

    data = json.loads(args.proj_json.read_text(encoding="utf-8"))
    views = data["views"]

    footer_std = "Hệ thống Smart Home Voice AI (PCB Hub trực tiếp 100×80 mm · 14 mô-đun · 40 dây đi thực tế ≤ 30 cm · 0 breadboard · 0 vít/keo)"

    # 1. Overview cutaway
    render_labeled_image(
        pathlib.Path(views["overview"]["raw_png"]),
        args.out_dir / "hw13_blender_overview_labeled.png",
        "Tổng Quan Mô Hình 3D Ngôi Nhà Thông Minh (Cắt Mái & Mặt Cắt Kỹ Thuật)",
        "14 mô-đun ngoại vi + NodeMCU v2 Amica + PCB Hub DIY v3 + 40 dây nối 3D thực tế",
        [
            ("SG90_DoorServo",   "1. Servo SG90 đồng trục cửa chính (D1 · J3)",       "servo",   "left"),
            ("main_door_leaf",   "Cửa chính 56×100 mm (trục bản lề & chốt nối)",     "coupler", "left"),
            ("psu_5v_dc_jack",   "2. Nguồn 5V 2A / Giắc DC-022 → J1 (W01–W02)",      "power",   "left"),
            ("nodemcu_esp8266",  "NodeMCU ESP8266 v2 Amica (U1/U2)",                 "pcb",     "left"),
            ("kicad_pcb_hub",    "PCB Hub DIY v3 (J1 vào · Ngõ ra J2/J8/J10/J11)",   "pcb",     "left"),
            ("sensor_mic_ky037", "6. Cảm biến âm thanh KY-037 (D5 · J15)",           "sensor",  "left"),
            ("buzzer_alarm",     "5. Còi báo động 5V TMB12A05 (D8 · J6)",            "audio",   "left"),
            ("led_living_room",  "3. Đèn LED 5mm Phòng khách (D0 · J4)",             "light",   "right"),
            ("led_bedroom",      "4. Đèn LED 5mm Phòng ngủ (D4 · J5)",               "light",   "right"),
            ("sensor_dht11",     "7. Cảm biến nhiệt/ẩm DHT11 (D2 · J13)",            "sensor",  "right"),
            ("soil_lm393_board", "8. Mạch so sánh đất LM393 (A0 · J14)",             "garden",  "right"),
            ("sensor_soil",      "9. Đầu dò độ ẩm đất YL-69",                        "garden",  "right"),
            ("pump_unit",        "10. Máy bơm chìm 5V + Ống nước (J2)",              "garden",  "right"),
            ("relay1_pump",      "13. Rơ-le 1 Bơm (D6 · J7/J8)",                     "relay",   "right"),
            ("relay2_speaker",   "14. Rơ-le 2 Loa (D7 · J9/J10)",                    "relay",   "right"),
            ("pam8403_module",   "12. Khuếch đại loa PAM8403 (J11/J12)",             "audio",   "right"),
            ("speaker_mini",     "11. Loa tròn mini 28mm (8Ω)",                      "audio",   "right"),
        ],
        views["overview"]["points"],
        footer_std,
    )

    # 2. Top-down cutaway (EVERY ONE of the 14 modules + PCB + NodeMCU + J1 visible & labeled!)
    render_labeled_image(
        pathlib.Path(views["topdown_cutaway"]["raw_png"]),
        args.out_dir / "hw13_blender_topdown_cutaway_labeled.png",
        "Mặt Bằng Cắt Mái Từ Trên Cao — Đầy Đủ 14 Mô-Đun, PCB Hub & 40 Dây Nối",
        "Kiểm tra bố trí toàn phần: 2 phòng chức năng + Khoang kỹ thuật + Bể nước & Vườn cây",
        [
            ("sensor_dht11",     "7. Cảm biến nhiệt/ẩm DHT11 (D2 · J13)",            "sensor",  "left"),
            ("led_living_room",  "3. Đèn LED 5mm Phòng khách (D0 · SUP17)",          "light",   "left"),
            ("SG90_DoorServo",   "1. Servo SG90 đỉnh cửa đồng trục (D1 · J3)",       "servo",   "left"),
            ("sensor_mic_ky037", "6. Cảm biến âm thanh KY-037 (D5 · J15)",           "sensor",  "left"),
            ("nodemcu_esp8266",  "NodeMCU ESP8266 v2 Amica (U1/U2)",                 "pcb",     "left"),
            ("kicad_pcb_hub",    "PCB Hub DIY v3 (100×80 mm · 51 linh kiện)",        "pcb",     "left"),
            ("PCB_J1_Input",     "Cầu đấu J1: Nguồn vào +5V / GND (từ DC-022)",      "power",   "left"),
            ("psu_5v_dc_jack",   "2. Nguồn 5V 2A + Giắc DC-022 & SUP16",             "power",   "left"),
            ("led_bedroom",      "4. Đèn LED 5mm Phòng ngủ (D4 · SUP17)",            "light",   "right"),
            ("buzzer_alarm",     "5. Còi báo động 5V TMB12A05 (D8 · SUP18)",         "audio",   "right"),
            ("soil_lm393_board", "8. Mạch so sánh đất LM393 (A0 · J14)",             "garden",  "right"),
            ("relay1_pump",      "13. Rơ-le 1 Bơm (D6 · Ngõ ra J2/J8)",              "relay",   "right"),
            ("relay2_speaker",   "14. Rơ-le 2 Loa (D7 · Ngõ ra J10/J11)",            "relay",   "right"),
            ("pump_unit",        "10. Máy bơm chìm 5V + Ống silicone (J2)",          "garden",  "right"),
            ("sensor_soil",      "9. Đầu dò độ ẩm đất YL-69 (trên cầu P14)",         "garden",  "right"),
            ("pam8403_module",   "12. Mạch loa PAM8403 3W Class-D (J11/J12)",        "audio",   "right"),
            ("speaker_mini",     "11. Loa tròn mini 28mm (8Ω · mặt trước P15)",      "audio",   "right"),
        ],
        views["topdown_cutaway"]["points"],
        footer_std,
    )

    # 3. Front Tech Bay (PSU/DC-022 + J1 input + switched outputs + relays + audio + garden + SG90)
    render_labeled_image(
        pathlib.Path(views["front_techbay"]["raw_png"]),
        args.out_dir / "hw13_blender_front_techbay_labeled.png",
        "Góc Chính Diện Khoang Kỹ Thuật — Nguồn 5V / DC-022 → J1 & Các Ngõ Ra Đóng Cắt",
        "Đường nguồn vào DC-022 → J1, phân phối qua Rơ-le 1/2 sang J2 (Bơm) & J11 (PAM8403/Loa)",
        [
            ("SG90_DoorServo",   "Servo SG90 đồng trục cửa chính (D1 · W03–W05)",    "servo",   "left", -60),
            ("PCB_J2_PumpOut",   "Ngõ ra đóng cắt J2: Nguồn bơm 5V (qua Rơ-le 1)",   "relay",   "left"),
            ("nodemcu_esp8266",  "NodeMCU ESP8266 v2 Amica (Micro-USB phía trước)",  "pcb",     "left"),
            ("PCB_J1_Input",     "Ngõ vào nguồn J1 (+5V / GND từ DC-022)",           "power",   "left"),
            ("PCB_J11_AmpPwr",   "Ngõ ra đóng cắt J11: Nguồn PAM8403 (qua Rơ-le 2)", "audio",   "left"),
            ("psu_5v_dc_jack",   "Nguồn 5V 2A · Phích cắm & Giắc DC-022 (SUP16)",    "power",   "left", 130),
            ("buzzer_alarm",     "Còi báo động 5V TMB12A05 (D8 · trụ giữa P05)",     "audio",   "right"),
            ("sensor_mic_ky037", "Cảm biến âm thanh KY-037 (D5 · J15)",              "sensor",  "right"),
            ("soil_lm393_board", "Mạch so sánh độ ẩm đất LM393 (A0 · mặt sau P13)",  "garden",  "right"),
            ("relay1_pump",      "Rơ-le 1 Xanh — Đóng cắt bơm (D6 · J7/J8)",         "relay",   "right"),
            ("relay2_speaker",   "Rơ-le 2 Đỏ Opto — Đóng cắt loa (D7 · J9/J10)",     "relay",   "right"),
            ("pump_unit",        "Máy bơm chìm mini 5V + Ống nước tưới cây",         "garden",  "right"),
            ("sensor_soil",      "Đầu dò độ ẩm đất YL-69 (chậu cây)",                "garden",  "right"),
            ("pam8403_module",   "Mạch khuếch đại PAM8403 (J11/J12 → Loa)",          "audio",   "right"),
            ("speaker_mini",     "Loa tròn mini 28mm (sau lưới 19 lỗ P15)",          "audio",   "right"),
        ],
        views["front_techbay"]["points"],
        footer_std,
    )

    # 4. Interior Rooms (Living Room LED, Bedroom LED, DHT11, Buzzer, KY-037, SG90 door mechanism)
    render_labeled_image(
        pathlib.Path(views["interior_rooms"]["raw_png"]),
        args.out_dir / "hw13_blender_interior_rooms_labeled.png",
        "Nội Thất Phòng Khách & Phòng Ngủ — Đèn LED 5mm, Cảm Biến & Cơ Cấu Cửa Servo",
        "Hai đèn LED 5mm gắn vòng giữ SUP17 phát sáng rõ, DHT11, Còi 5V, KY-037 & Servo SG90 đỉnh cửa",
        [
            ("SG90_DoorServo",   "Servo SG90 đồng trục trên giá P07 + Ngàm SUP11",   "servo",   "left", -210),
            ("sg90_horn_pivot",  "Tay đòn trắng SG90 + Ngàm kéo SUP10B đồng trục",   "coupler", "left", -225),
            ("main_door_leaf",   "Cánh cửa chính 56×100 mm (bản lề SUP10)",          "coupler", "left",  45),
            ("sensor_mic_ky037", "Cảm biến âm thanh KY-037 (D5 · gờ trước P05)",     "sensor",  "left",  50),
            ("led_bedroom",      "Đèn LED 5mm Phòng ngủ (D4 · Vòng giữ SUP17)",      "light",   "right"),
            ("led_living_room",  "Đèn LED 5mm Phòng khách (D0 · Vòng giữ SUP17)",    "light",   "right"),
            ("sensor_dht11",     "Cảm biến nhiệt độ & độ ẩm DHT11 (D2 · vách P06)",  "sensor",  "right"),
            ("buzzer_alarm",     "Còi báo động 5V TMB12A05 + Vòng giữ SUP18 (D8)",   "audio",   "right"),
        ],
        views["interior_rooms"]["points"],
        footer_std,
    )

    # 5. Servo Door CLOSED (0 deg)
    render_labeled_image(
        pathlib.Path(views["servo_door_closed"]["raw_png"]),
        args.out_dir / "hw13_blender_servo_door_closed.png",
        "Cận Cảnh Cơ Cấu Cửa Chính Servo SG90 Đồng Trục — TRẠNG THÁI ĐÓNG (0°)",
        "Truyền động trực tiếp đồng trục tại (X=77, Y=201.5 mm) · 0 vít · 0 keo · Chặn cơ học -2° / +92°",
        [
            ("SG90_DoorServo",     "Servo SG90 lật ngược (thân xanh nổi Z=107–130 mm)", "servo",   "left"),
            ("SUP11_Saddle",       "Ngàm kẹp SUP11 giữ tai SG90 (0 vít, 0 keo)",        "servo",   "left"),
            ("P07_ServoShelf",     "Giá đỡ P07_SERVO_SHELF (Z=108.5–111.5 mm)",         "servo",   "left"),
            ("P07_EndStop_Closed", "Chốt chặn hành trình ĐÓNG (-2°)",                   "coupler", "left"),
            ("SUP10B_Coupler",     "Ngàm chữ U SUP10B gắn cửa ôm tay đòn SG90",         "coupler", "left"),
            ("main_door_leaf",     "Cánh cửa chính ĐÓNG 0° (khít khung P05)",           "light",   "left"),
            ("P07_EndStop_Open",   "Chốt chặn hành trình MỞ (+92°)",                    "coupler", "right"),
            ("sg90_horn_pivot",    "Tay đòn trắng SG90 (Z=100.1 mm · hướng +X)",        "servo",   "right"),
            ("SUP10_HingeTop",     "Bản lề đồng trục trên SUP10 (Z=78 mm)",             "relay",   "right"),
            ("SUP10_HingeBot",     "Bản lề đồng trục dưới SUP10 (Z=18 mm)",             "relay",   "right"),
        ],
        views["servo_door_closed"]["points"],
        "Góc nhìn từ bên trong Phòng khách hướng ra khung cửa P05 · Dây servo W03–W05 luồn qua lỗ Cable_Servo_D1 (≤ 25 cm)",
    )

    # 6. Servo Door OPEN (90 deg inward)
    render_labeled_image(
        pathlib.Path(views["servo_door_open"]["raw_png"]),
        args.out_dir / "hw13_blender_servo_door_open.png",
        "Cận Cảnh Cơ Cấu Cửa Chính Servo SG90 Đồng Trục — TRẠNG THÁI MỞ (90° VÀO TRONG)",
        "Cửa và tay đòn SG90 xoay đồng bộ 90° vào Phòng khách · Không va chạm tường/nội thất",
        [
            ("SG90_DoorServo",     "Servo SG90 cố định trên giá P07 + Ngàm SUP11",      "servo",   "left"),
            ("P07_ServoShelf",     "Giá đỡ P07_SERVO_SHELF trên đỉnh khung cửa",        "servo",   "left"),
            ("P07_EndStop_Closed", "Chốt chặn ĐÓNG (-2° · đang trống)",                 "coupler", "left"),
            ("SUP10_HingeTop",     "Bản lề trên SUP10 xoay đồng trục 90°",              "relay",   "left"),
            ("SUP10_HingeBot",     "Bản lề dưới SUP10 xoay đồng trục 90°",              "relay",   "left"),
            ("P07_EndStop_Open",   "Chốt chặn MỞ (+92° · chặn an toàn chống kẹt)",      "coupler", "right"),
            ("sg90_horn_pivot",    "Tay đòn trắng SG90 đã xoay 90° đồng bộ",            "servo",   "right"),
            ("SUP10B_Coupler",     "Ngàm chữ U SUP10B bám khít tay đòn ở 90°",          "coupler", "right"),
            ("main_door_leaf",     "Cánh cửa chính MỞ 90° vào trong Phòng khách",       "light",   "right"),
        ],
        views["servo_door_open"]["points"],
        "Kiểm tra đồng trục 0°→90°: trục bản lề SUP10 trùng tuyệt đối trục răng SG90 (tx=-126.0, tz=+33.5 mm)",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
