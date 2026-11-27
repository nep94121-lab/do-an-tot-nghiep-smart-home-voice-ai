"""TDD Automated Reproduction and Verification Test Suite for Milestone M17 (Bug R2).

Bug R2: /wokwi Breadboard and KY-037 / PAM8403 Label Layout Fixes.
Verifies:
1. KY-037 (D5) label does not overlap DHT11 label at top: 360px (ensuring 'D5)' is 100% visible).
2. Breadboard tag does not overlap NodeMCU tag or Servo tag, wraps cleanly, and fits inside 1280px desktop initial viewport (~618px).
3. Bottom row Relay 2 PAM8403 + Speaker tag does not collide with KY-037 Panel tag at top: 418px.
4. Comprehensive 2D pairwise bounding box non-overlap check across all 11 .comp-tag elements in static DOM geometry.
5. Real Chrome browser rendering across 3 viewports:
   - 1280x800 Desktop
   - 390x844 Mobile (iPhone 12/13/14)
   - 414x896 Mobile (iPhone XR/11/Plus)
   confirming 0 bounding-box overlaps in real browser rendering with full CSS loaded.
"""
from __future__ import annotations

import http.server
import pathlib
import re
import socketserver
import threading
from bs4 import BeautifulSoup
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "web"
WOKWI_HTML_PATH = STATIC_DIR / "wokwi.html"
WOKWI_CSS_PATH = STATIC_DIR / "css" / "wokwi.css"


def parse_tag_style(style_str: str) -> dict[str, str]:
    """Parse inline CSS style string into a dictionary."""
    res = {}
    for part in style_str.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            res[k.strip().lower()] = v.strip().lower()
    return res


def parse_px(val: str, default: float = 0.0) -> float:
    """Extract numeric pixel value."""
    m = re.search(r"([\d\.]+)\s*px", val)
    return float(m.group(1)) if m else default


def estimate_text_width(text: str, font_size_px: float = 11.0) -> float:
    """Conservative width estimate based on Be Vietnam Pro average char width (~0.62 * font_size) + padding (14px) + border (2px)."""
    clean_text = " ".join(text.split())
    char_w = font_size_px * 0.62
    return len(clean_text) * char_w + 16.0


class TestBugR2WokwiLabelLayoutStatic:
    """Static DOM and Geometric Analysis for Bug R2."""

    def test_r2_ky037_tag_does_not_overlap_dht11(self):
        """KY-037 (D5) label must not overlap DHT11 label at top: 360px."""
        assert WOKWI_HTML_PATH.exists(), f"File {WOKWI_HTML_PATH} does not exist!"
        soup = BeautifulSoup(WOKWI_HTML_PATH.read_text(encoding="utf-8"), "html.parser")
        tags = soup.find_all("div", class_="comp-tag")

        ky_tag = next(
            (
                t
                for t in tags
                if "KY-037" in t.text
                and "D5" in t.text
                and parse_px(parse_tag_style(t.get("style", "")).get("top", "0px")) == 360.0
            ),
            None,
        )
        dht_tag = next((t for t in tags if "DHT11" in t.text), None)
        assert ky_tag is not None, "Thẻ nhãn KY-037 (D5) ở hàng top:360px không tìm thấy!"
        assert dht_tag is not None, "Thẻ nhãn DHT11 không tìm thấy!"

        ky_style = parse_tag_style(ky_tag.get("style", ""))
        dht_style = parse_tag_style(dht_tag.get("style", ""))

        ky_left = parse_px(ky_style.get("left", "0px"))
        ky_top = parse_px(ky_style.get("top", "0px"))
        ky_font = parse_px(ky_style.get("font-size", "11px"), 11.0)

        dht_left = parse_px(dht_style.get("left", "0px"))
        dht_top = parse_px(dht_style.get("top", "0px"))

        # Calculate estimated right edge of KY-037 tag
        ky_width = estimate_text_width(ky_tag.text, ky_font)
        ky_right = ky_left + ky_width

        # They must not collide:
        # Either vertical separation >= 20px, OR horizontal gap (dht_left - ky_right) >= 10px
        top_diff = abs(dht_top - ky_top)
        horiz_gap = dht_left - ky_right

        assert top_diff >= 20 or horiz_gap >= 10, (
            f"LỖI R2: Nhãn KY-037 (left={ky_left}px, width~{ky_width:.1f}px, right~{ky_right:.1f}px, top={ky_top}px) "
            f"bị nhãn DHT11 (left={dht_left}px, top={dht_top}px) đè lấn lên chữ 'D5)'! "
            f"(Khoảng cách horiz_gap = {horiz_gap:.1f}px < 10px VÀ top_diff = {top_diff:.1f}px < 20px)"
        )

    def test_r2_breadboard_tag_does_not_overlap_nodemcu_or_servo(self):
        """Breadboard tag must not overlap NodeMCU tag on left or Servo tag on right, and must not truncate."""
        soup = BeautifulSoup(WOKWI_HTML_PATH.read_text(encoding="utf-8"), "html.parser")
        tags = soup.find_all("div", class_="comp-tag")

        mcu_tag = next((t for t in tags if "NodeMCU" in t.text), None)
        bb_tag = next((t for t in tags if "Breadboard 400" in t.text), None)
        servo_tag = next((t for t in tags if "Servo" in t.text), None)

        assert mcu_tag is not None, "Thẻ nhãn NodeMCU không tìm thấy!"
        assert bb_tag is not None, "Thẻ nhãn Breadboard không tìm thấy!"
        assert servo_tag is not None, "Thẻ nhãn Servo không tìm thấy!"

        mcu_style = parse_tag_style(mcu_tag.get("style", ""))
        bb_style = parse_tag_style(bb_tag.get("style", ""))
        servo_style = parse_tag_style(servo_tag.get("style", ""))

        mcu_left = parse_px(mcu_style.get("left", "0px"))
        mcu_top = parse_px(mcu_style.get("top", "0px"))
        mcu_font = parse_px(mcu_style.get("font-size", "11px"), 11.0)
        mcu_width = estimate_text_width(mcu_tag.text, mcu_font)
        mcu_right = mcu_left + mcu_width

        bb_left = parse_px(bb_style.get("left", "0px"))
        bb_top = parse_px(bb_style.get("top", "0px"))
        bb_font = parse_px(bb_style.get("font-size", "11px"), 11.0)

        # Check if breadboard wraps (white-space: normal and max-width)
        bb_is_wrapped = "normal" in bb_style.get("white-space", "") and "max-width" in bb_style
        bb_width = parse_px(bb_style.get("max-width", "0px")) if bb_is_wrapped else estimate_text_width(bb_tag.text, bb_font)
        bb_right = bb_left + bb_width

        servo_left = parse_px(servo_style.get("left", "0px"))
        servo_top = parse_px(servo_style.get("top", "0px"))

        # 1. MCU vs Breadboard:
        mcu_bb_top_diff = abs(bb_top - mcu_top)
        left_gap = bb_left - mcu_right
        assert mcu_bb_top_diff >= 20 or left_gap >= 10, (
            f"LỖI R2: Nhãn NodeMCU (right~{mcu_right:.1f}px) đè lấn lên Nhãn Breadboard (left={bb_left}px)! "
            f"(left_gap = {left_gap:.1f}px < 10px)"
        )

        # 2. Breadboard vs Servo:
        bb_servo_top_diff = abs(servo_top - bb_top)
        right_gap = servo_left - bb_right
        assert bb_servo_top_diff >= 20 or right_gap >= 10, (
            f"LỖI R2: Nhãn Breadboard (right~{bb_right:.1f}px) đè lấn lên Nhãn Servo (left={servo_left}px)! "
            f"(right_gap = {right_gap:.1f}px < 10px)"
        )

        # 3. Check that Breadboard tag does not overflow visible initial scroll viewport (~618px on 1280px desktop)
        assert bb_right <= 618.0, (
            f"LỖI R2: Nhãn Breadboard (right~{bb_right:.1f}px) vượt quá khung nhìn cuộn ban đầu (618px), "
            f"dẫn đến bị cắt cụt (truncation) tại '(tr…'!"
        )

    def test_r2_bottom_row_speaker_amp_does_not_overlap_ky037(self):
        """Relay 2 PAM8403 + Speaker tag must not overlap KY-037 sound panel tag."""
        soup = BeautifulSoup(WOKWI_HTML_PATH.read_text(encoding="utf-8"), "html.parser")
        tags = soup.find_all("div", class_="comp-tag")

        spk_tag = next((t for t in tags if "PAM8403" in t.text or "Loa" in t.text), None)
        ky_panel_tag = next((t for t in tags if "Cảm biến Âm thanh KY-037" in t.text), None)

        assert spk_tag is not None, "Thẻ nhãn PAM8403/Loa không tìm thấy!"
        assert ky_panel_tag is not None, "Thẻ nhãn Cảm biến Âm thanh KY-037 không tìm thấy!"

        spk_style = parse_tag_style(spk_tag.get("style", ""))
        ky_style = parse_tag_style(ky_panel_tag.get("style", ""))

        spk_left = parse_px(spk_style.get("left", "0px"))
        spk_top = parse_px(spk_style.get("top", "0px"))
        spk_width = estimate_text_width(spk_tag.text, parse_px(spk_style.get("font-size", "11px"), 11.0))
        spk_right = spk_left + spk_width

        ky_left = parse_px(ky_style.get("left", "0px"))
        ky_top = parse_px(ky_style.get("top", "0px"))

        top_diff = abs(ky_top - spk_top)
        gap = ky_left - spk_right

        assert top_diff >= 20 or gap >= 10, (
            f"LỖI R2: Nhãn PAM8403/Loa (right~{spk_right:.1f}px) đè lấn lên Nhãn KY-037 (left={ky_left}px)! "
            f"(gap = {gap:.1f}px < 10px)"
        )

    def test_r2_pairwise_all_tags_no_collision_static(self):
        """Pairwise 2D collision check across all .comp-tag elements in .circuit-stage."""
        soup = BeautifulSoup(WOKWI_HTML_PATH.read_text(encoding="utf-8"), "html.parser")
        circuit_stage = soup.find(id="circuitStage") or soup.find(class_="circuit-stage")
        assert circuit_stage is not None, "Khung #circuitStage không tìm thấy!"

        tags = circuit_stage.find_all("div", class_="comp-tag")
        assert len(tags) >= 10, f"Tìm thấy quá ít nhãn comp-tag: {len(tags)}"

        tag_boxes = []
        for i, tag in enumerate(tags):
            style = parse_tag_style(tag.get("style", ""))
            left = parse_px(style.get("left", "0px"))
            top = parse_px(style.get("top", "0px"))
            font_size = parse_px(style.get("font-size", "11px"), 11.0)
            is_wrapped = "normal" in style.get("white-space", "") and "max-width" in style
            if is_wrapped:
                width = parse_px(style.get("max-width", "0px"))
                height = 36.0  # Approx 2 lines of text
            else:
                width = estimate_text_width(tag.text, font_size)
                height = 20.0
            tag_boxes.append({
                "index": i,
                "text": " ".join(tag.text.split())[:30],
                "left": left,
                "top": top,
                "right": left + width,
                "bottom": top + height,
            })

        collisions = []
        for i in range(len(tag_boxes)):
            for j in range(i + 1, len(tag_boxes)):
                b1 = tag_boxes[i]
                b2 = tag_boxes[j]
                # AABB collision check
                overlap_x = max(0.0, min(b1["right"], b2["right"]) - max(b1["left"], b2["left"]))
                overlap_y = max(0.0, min(b1["bottom"], b2["bottom"]) - max(b1["top"], b2["top"]))
                if overlap_x > 0 and overlap_y > 0:
                    collisions.append(
                        f"Va chạm giữa '{b1['text']}' [{b1['left']:.0f}..{b1['right']:.0f}, {b1['top']:.0f}..{b1['bottom']:.0f}] "
                        f"và '{b2['text']}' [{b2['left']:.0f}..{b2['right']:.0f}, {b2['top']:.0f}..{b2['bottom']:.0f}] "
                        f"(dx={overlap_x:.1f}px, dy={overlap_y:.1f}px)"
                    )

        assert not collisions, f"Phát hiện {len(collisions)} va chạm comp-tag: " + "; ".join(collisions)


class TestBugR2WokwiPlaywrightRendering:
    """Real Browser Rendering Verification with Playwright across multiple viewports."""

    @pytest.fixture(scope="class")
    @classmethod
    def static_server(cls):
        """Spin up a lightweight HTTP server serving web/ on an ephemeral port."""
        class WokwiStaticServerHandler(http.server.SimpleHTTPRequestHandler):
            def translate_path(self, path):
                clean = path.split("?")[0].split("#")[0].lstrip("/")
                if clean.startswith("static/"):
                    clean = clean[7:]
                return str(STATIC_DIR / clean)

            def log_message(self, format, *args):
                pass

        socketserver.TCPServer.allow_reuse_address = True
        httpd = socketserver.TCPServer(("127.0.0.1", 0), WokwiStaticServerHandler)
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        yield f"http://127.0.0.1:{port}"
        httpd.shutdown()

    @pytest.mark.parametrize("width,height,viewport_name", [
        (1280, 800, "Desktop 1280px"),
        (390, 844, "Mobile iPhone 390px"),
        (414, 896, "Mobile iPhone 414px"),
    ])
    def test_r2_real_browser_layout_across_viewports(self, static_server: str, width: int, height: int, viewport_name: str):
        """Verify zero bounding-box overlaps in actual Chromium engine across desktop and mobile viewports."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            pytest.skip("Playwright package not installed.")

        try:
            pw = sync_playwright().start()
            browser = pw.chromium.launch(channel="chrome", headless=True)
        except Exception as e:
            pytest.skip(f"Chrome browser not available for Playwright launch: {e}")

        try:
            page = browser.new_page()
            page.set_viewport_size({"width": width, "height": height})
            page.goto(f"{static_server}/wokwi.html")
            # Legacy breadboard stage is hidden by default (PCB-direct default); unhide to inspect static .comp-tag spacing
            page.evaluate("""() => {
                if (typeof setWokwiDiagramMode === 'function') setWokwiDiagramMode('breadboard');
                const wb = document.getElementById('workbenchScroll');
                if (wb) wb.hidden = false;
            }""")

            tags_data = page.evaluate("""() => {
                const tags = Array.from(document.querySelectorAll('.comp-tag'));
                return tags.map((el, idx) => {
                    const r = el.getBoundingClientRect();
                    return {
                        idx,
                        text: el.innerText.trim(),
                        rect: {
                            left: r.left,
                            right: r.right,
                            top: r.top,
                            bottom: r.bottom,
                            width: r.width,
                            height: r.height
                        }
                    };
                });
            }""")

            assert len(tags_data) >= 10, f"Expected at least 10 comp-tags, got {len(tags_data)}"

            overlaps = []
            for i in range(len(tags_data)):
                for j in range(i + 1, len(tags_data)):
                    t1 = tags_data[i]
                    t2 = tags_data[j]
                    r1 = t1["rect"]
                    r2 = t2["rect"]
                    intersect_x = max(0, min(r1["right"], r2["right"]) - max(r1["left"], r2["left"]))
                    intersect_y = max(0, min(r1["bottom"], r2["bottom"]) - max(r1["top"], r2["top"]))
                    if intersect_x > 0 and intersect_y > 0:
                        overlaps.append(
                            f"'{t1['text']}' and '{t2['text']}' overlap by dx={intersect_x:.1f}px, dy={intersect_y:.1f}px"
                        )

            assert not overlaps, (
                f"Viewport {viewport_name} ({width}x{height}) has {len(overlaps)} overlaps: "
                + "; ".join(overlaps)
            )

            # Specific Bug R2 Checks:
            # 1. KY-037 (D5) vs DHT11 gap
            ky = next((t for t in tags_data if "KY-037" in t["text"] and "Chân D5" in t["text"]), None)
            dht = next((t for t in tags_data if "DHT11" in t["text"]), None)
            assert ky and dht, "Missing KY-037 or DHT11 tag in DOM"
            ky_dht_gap = dht["rect"]["left"] - ky["rect"]["right"]
            assert ky_dht_gap > 0, f"KY-037 and DHT11 collision: gap = {ky_dht_gap} <= 0"

            # 2. NodeMCU vs Breadboard gap
            mcu = next((t for t in tags_data if "NodeMCU" in t["text"]), None)
            bb = next((t for t in tags_data if "Breadboard 400" in t["text"]), None)
            servo = next((t for t in tags_data if "Servo" in t["text"]), None)
            assert mcu and bb and servo, "Missing MCU, BB, or Servo tag in DOM"
            mcu_bb_gap = bb["rect"]["left"] - mcu["rect"]["right"]
            bb_servo_gap = servo["rect"]["left"] - bb["rect"]["right"]
            assert mcu_bb_gap > 0, f"MCU and Breadboard collision: gap = {mcu_bb_gap} <= 0"
            assert bb_servo_gap > 0, f"Breadboard and Servo collision: gap = {bb_servo_gap} <= 0"

            page.close()
        finally:
            browser.close()
            pw.stop()
