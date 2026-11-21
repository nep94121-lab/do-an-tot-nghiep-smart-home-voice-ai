STATUS: ALL_DONE

# SmartHome Hub DIY Single-Layer PCB Redesign Report (`agyhwdiy2_20261121`)

- **Branch / Worktree**: `hwdiy-20261121` (`C:\Users\LENOVO\datn-wt\hwdiy`, branched from `master` @ `131bdc2`)
- **Run Directory**: `C:\Users\LENOVO\datn-wt\agyhwdiy2_20261121`
- **Design & Deliverables Commit**: `a83b9ac` (`a83b9ac8090f0fcf65b0303786e28b86706cf831`)
- **Independent Reviewer Verdict**: **`PASS`** (Round 1 flagged 2 blocking, 2 moderate, 5 minor findings; all 9 resolved and independently re-verified `CLOSED / PASS` in Round 2)

---

## 1. Executive Summary

`hardware/kicad/smarthome_hub` has been completely redesigned as a **single-layer (`B.Cu` only)**, maker-friendly PCB engineered specifically for **home toner-transfer etching and hand drilling**. The circuit retains the exact locked ESP8266 NodeMCU v2 Amica 10-GPIO hardware contract (6 actuators + 3 sensors; zero fan, zero AC, zero IR) and achieves:

- **0 ERC errors / 0 ERC warnings** (`kicad-cli sch erc --severity-all` across both schematic sheets).
- **0 DRC violations / 0 unconnected pads / 0 schematic-parity errors** (`kicad-cli pcb drc --schematic-parity --severity-all`, 47/47 footprints synchronized with schematic and `bom.csv`).
- **True single copper layer (`B.Cu`)**: `0` vias, `175/175` track segments on `B.Cu`, `0` zones, `0` SMD pads, `0` `F.Cu` tracks/graphics, single-sided Gerber set omits `F_Cu.gtl`, and `smarthome_hub-B_Cu.gbl` contains all `118/118` PTH solder pad flashes + `175` track draws.
- **Forgiving DIY geometry**: signal traces `>= 1.00 mm`, power & GND traces `>= 2.00 mm`, copper clearance `>= 0.60 mm` (zero clearance exceptions), round pads `>= 2.60 mm`, non-header annular rings `>= 0.75 mm`, and **exact 4 drill classes** (`0.9 mm`, `1.1 mm`, `1.3 mm`, `3.2 mm`) enforced by `.kicad_dru` and `.kicad_pro`.
- **Minimal 7 top-side wire jumpers (`JP1..JP7` / silkscreen `J-1..J-7`)**: `0` jumpers on `GND` (closed perimeter ring on `B.Cu`) and `0` jumpers on all 15 signal/GPIO nets; all 7 jumpers are strictly on `+3.3V` (3) and `+5V` (4) rails and modeled as real BOM/schematic components.
- **Exact 1:1 printable PDFs verified by PyMuPDF**: `toner_B.Cu_MIRRORED_1to1.pdf` (text reads backwards, board `100.00 x 80.00 mm`, scale bar `50.00 mm`), `toner_B.Cu_check_NOT_mirrored_1to1.pdf` (text reads forward), `placement_top_silk_1to1.pdf`, and true 1:1 `drill_map.pdf` (all 122 holes matching `smarthome_hub.drl` and `drill_table.csv` 100%).

---

## 2. Final Board Facts & Datasheet Verification

### 2.1 Mechanical & Fixed Specifications

| Parameter | Requirement | Final Verified Board |
| :--- | :--- | :--- |
| Board Outline (`Edge.Cuts`) | `100 x 80 mm` rectangular, `<= 3 mm` corner radius, `1.6 mm` thick | **`100.000 x 80.000 x 1.6 mm`**, `R = 3.000 mm` corner arcs |
| 4x M3 Mounting Holes | `3.2 mm` NPTH @ `(5,5), (95,5), (5,75), (95,75)` mm (`90 x 70 mm`) | `H1(5,75)`, `H2(95,75)`, `H3(5,5)`, `H4(95,5)` mm, `3.20 mm` NPTH |
| Copper Layers & Vias | Single layer `B.Cu` only, `0` vias, no `F.Cu` copper | `B.Cu` only, `0` vias, `175` B.Cu segments, `118/118` B.Cu PTH pads, no `F_Cu.gtl` |
| Pin Map (NodeMCU v2 Amica) | `D0` LR LED, `D1` Servo, `D2` DHT11, `D3` Audio PWM, `D4` BR LED, `D5` KY-037 DO, `D6` Relay1, `D7` Relay2, `D8` Buzzer, `A0` Soil | 100% unchanged; verified via schematic netlist + `tests/test_hw_contract_6devices_20261120.py` (`14/14` passed) |
| Excluded Devices | Zero fan, zero AC, zero IR | Confirmed `0` fan, `0` AC, `0` IR parts |

### 2.2 Hole Table (Exact 4 Drill Classes — 122 Holes Total)

| Drill Step | Bit Size | Type | Hole Count | Parts Using This Drill | Pin / Mechanical Basis |
| :---: | :---: | :---: | :---: | :--- | :--- |
| 1 | **`0.9 mm`** | PTH (`B.Cu`) | **48** | `R1..R9`, `C1..C7`, `D3`, `JP1..JP7` | Round component leads & 22 AWG jumper wire (`0.50–0.64 mm` dia) |
| 2 | **`1.1 mm`** | PTH (`B.Cu`) | **66** | `U1`, `U2`, `J3..J15`, `D1`, `D2` | `0.64 mm` sq header pins (`0.905 mm` diag), DO-41 leads (`0.86 mm` max), forgiving 15-pin hand-drill tolerance |
| 3 | **`1.3 mm`** | PTH (`B.Cu`) | **4** | `J1`, `J2` | Phoenix MKDS 1,5/2-5,08 (`0.9 x 0.9 mm` pin = `1.27 mm` diag, datasheet `1.30 mm` drill) |
| 4 | **`3.2 mm`** | NPTH | **4** | `H1..H4` | ISO 273 Medium clearance hole for M3 machine screws |
| **Total** | **4 classes** | — | **122** | **47 footprints** | **122/122 exact match across PCB, Excellon `.drl`, `drill_table.csv`, `drill_table.md`, and `drill_map.pdf`** |

### 2.3 Trace, Pad, Clearance, Silkscreen & Annular Ring Stats

- **Track segments**: `175` total (all on `B.Cu`): `61` signal segments at `1.00 mm` wide (rule `>= 1.00 mm`); `114` power & GND segments at `2.00 mm` wide (rule `>= 2.00 mm`).
- **Copper clearance**: `>= 0.60 mm` globally across all nets and board edge (`0` DRC clearance violations, zero clearance waivers).
- **Round pads**: `41` round pads, minimum diameter **`2.60 mm`** (`R1..R9`, `C3, C5, C6, C7`), `2.80 mm` on `D3` and `JP1..JP7` (rule `>= 2.50 mm`).
- **Non-header pads**: `56` pads (`R`, `C`, `D`, `LED`, `J1/J2`, `JP1..JP7`), minimum annular ring **`0.75 mm`** (strictly `>= 0.60 mm`).
- **2.54 mm header/socket pads (`U1, U2, J3..J15`, 62 pads) — Euclidean bound documentation**: Along a `2.54 mm` pitch with `1.10 mm` drill, available space between adjacent holes is `2.54 - 1.10 = 1.44 mm = 2 * ring_longitudinal + clearance`. Achieving both `clearance >= 0.60 mm` and `ring_longitudinal >= 0.60 mm` simultaneously requires `1.10 + 1.20 + 0.60 = 2.90 mm > 2.54 mm` (mathematically impossible). This design preserves **full `>= 0.60 mm` copper clearance everywhere** (actual `0.74 mm` inter-pad gap to prevent home toner-transfer bridging) using elongated **`3.80 x 1.80 mm`** oval/rect pads (`1.35 mm` transverse annular ring `>> 0.60 mm`, `0.35 mm` longitudinal ring, scoped in `.kicad_dru` rule `DIY_Header_254mm_Oval_Annular_Ring`).
- **`F.SilkS` labels**: `52` visible labels, min height **`1.50 mm`**, min thickness **`0.25 mm`**, `0` pad overlaps, `0` silk overlaps. Every header (`J1..J15`) displays module name, NodeMCU pin, and per-pin `VCC/GND/SIG` polarity; electrolytic caps (`C1, C2, C4`), diodes (`D1, D2`), and green LED (`D3`) carry clear polarity marks; board title `HUB DIY v3 / 1L B.Cu / 100x80mm / NODEMCU / USB v` is centered cleanly.

### 2.4 Minimal Top-Side Wire Jumpers (7 Total: `JP1..JP7`)

| ID | Silk Label | Power Rail | From Pad / Net (`X, Y` mm) | To Pad / Net (`X, Y` mm) | Length (mm) | Color Suggestion |
| :---: | :---: | :---: | :--- | :--- | ---: | :--- |
| `JP1` | `J-1` | `+3.3V` | `JP1.1` `+3V3` (43.00, 46.30) | `JP1.2` `/+3V3_R` (55.70, 46.30) | `12.70` | Orange (`+3.3V`) |
| `JP2` | `J-2` | `+3.3V` | `JP2.1` `+3V3` (40.50, 62.00) | `JP2.2` `/+3V3_SOIL` (22.72, 62.00) | `17.78` | Orange (`+3.3V`) |
| `JP3` | `J-3` | `+3.3V` | `JP3.1` `/+3V3_R` (76.00, 46.70) | `JP3.2` `/+3V3_TOP` (76.00, 54.32) | `7.62` | Orange (`+3.3V`) |
| `JP4` | `J-4` | `+5V` | `JP4.1` `+5V` (36.50, 20.00) | `JP4.2` `/+5V_RLY2` (72.06, 20.00) | `35.56` | Red (`+5V`) |
| `JP5` | `J-5` | `+5V` | `JP5.1` `/+5V_RLY2` (85.50, 15.72) | `JP5.2` `/+5V_RLY1` (85.50, 28.42) | `12.70` | Red (`+5V`) |
| `JP6` | `J-6` | `+5V` | `JP6.1` `/+5V_RLY1` (85.50, 33.00) | `JP6.2` `/+5V_TOP` (85.50, 53.32) | `20.32` | Red (`+5V`) |
| `JP7` | `J-7` | `+5V` | `JP7.1` `/+5V_TOP` (85.50, 67.30) | `JP7.2` `/+5V_SERVO` (60.10, 67.30) | `25.40` | Red (`+5V`) |

### 2.5 Component Footprint & Datasheet Citations

- **NodeMCU v2 Amica (`U1`, `U2`)**: `48.26 x 25.40–25.80 mm` PCB, 2×15 pins @ `2.54 mm` pitch, `22.86 mm` (`0.9 in`) row spacing; 8.5 mm vertical female sockets (`DIY_Hub:PinSocket_1x15_P2.54mm_DIY`, `1.1 mm` drill). Source: Amica NodeMCU v2 Mechanical Drawing & `docs/phan_cung/DIMENSIONS_AUDIT.md`. Only flat `R4` (`2.5 mm`) and `JP1` (`~2.0 mm`) sit beneath the NodeMCU belly.
- **Screw Terminals (`J1`, `J2`)**: Phoenix Contact MKDS 1,5/2-5,08 — `5.08 mm` pitch, `0.9 x 0.9 mm` solder pin (`1.27 mm` diagonal), datasheet drill `1.30 mm`, body `10.16 x 9.80 mm` (`DIY_Hub:TerminalBlock_MKDS_1x02_P5.08mm_DIY`, `3.20 x 4.40 mm` pads). Source: Phoenix Contact MKDS 1,5/2-5,08 Datasheet (1715721).
- **2.54 mm Pin Headers (`J3..J15`)**: `2.54 mm` pitch, `0.64 mm` sq pin (`0.905 mm` diagonal), `1.1 mm` forgiving hand-drill hole (`DIY_Hub:PinHeader_1x02/1x03_P2.54mm_DIY`). Source: Würth Elektronik 6130xx11121 / Samtec TSW Series.
- **Axial 1/4W Resistors (`R1..R9`)**: DIN 0207 (`L = 6.3 mm`, `D = 2.5 mm`, `0.60 mm` lead, `10.16 mm` pitch, `0.9 mm` drill, `2.60 mm` round pads). Source: Vishay MBA/SMA 0204 & Yageo CFR-25 Datasheet.
- **DO-41 Diodes (`D1`, `D2` — `1N4007`)**: SOD-81 / DO-41 (`L = 5.2 mm`, `D = 2.7 mm`, max lead `0.86 mm`, `10.16 mm` pitch, `1.1 mm` drill, `2.60 x 3.40 mm` pads). Source: Vishay 1N4001–1N4007 Datasheet (88503).
- **Bulk Electrolytic Caps (`C1`, `C2` — `470uF 16V`)**: Radial `D = 8.0 mm`, `H = 11.5 mm`, `P = 3.50 mm`, `0.60 mm` lead, `0.9 mm` drill, `2.60 x 3.60 mm` pads. Source: Nichicon UVR/UHE `470uF 16V` `8x11.5` Datasheet.
- **Audio Coupling Cap (`C4` — `10uF 16V`)**: Radial `D = 5.0 mm`, leads formed to `P = 3.50 mm` for `>= 0.60 mm` pad clearance, `0.9 mm` drill, `2.60 x 3.40 mm` pads. Documented low-profile (`H <= 7 mm`) / lay-flat assembly guidance in `DIY_GUIDE.md` and `BOM_DIY_SHOPPING.md` to clear bulky NodeMCU Micro-USB plug overmolds.
- **Ceramic Disc Caps (`C3, C5, C6, C7`)**: `D = 5.0 mm`, `P = 5.00 mm`, `0.50 mm` lead, `0.9 mm` drill, `2.60 mm` round pads. Source: Murata RDE / Vishay K-Series.
- **Green Power Indicator LED (`D3`)**: `3.0 mm` THT LED (`LED_D3.0mm_Green.step`), leads formed to `P = 5.08 mm`, `0.9 mm` drill, `2.80 mm` pads. Source: Kingbright WP710A10GD.
- **Wire Jumpers (`JP1..JP7`)**: 22 AWG solid insulated copper wire (`0.644 mm` core), `0.9 mm` drill, `2.80 mm` round pads, exact pitches `7.62–35.56 mm`.

---

## 3. Commands Run & Verification Counts

```powershell
# 1. Deterministically build footprints, schematic, PCB, .kicad_pro, .kicad_dru, bom.csv + run ERC/DRC
C:\Users\LENOVO\miniconda3\python.exe hardware/kicad/smarthome_hub/build_diy_hub.py

# 2. Export toner PDFs, placement PDF, true 1:1 drill map, Excellon .drl, single-layer Gerbers,
#    tables, BOM, screenshots 90..95, and run all automated assertions
C:\Users\LENOVO\miniconda3\python.exe hardware/kicad/smarthome_hub/export_and_verify_diy.py

# 3. Direct KiCad 10.0.6 CLI verification (also independently re-run by Independent Reviewer)
kicad-cli sch erc --severity-all --format report -o hardware/kicad/smarthome_hub/reports/erc.txt hardware/kicad/smarthome_hub/smarthome_hub.kicad_sch
kicad-cli pcb drc --schematic-parity --severity-all --format report -o hardware/kicad/smarthome_hub/reports/drc.txt hardware/kicad/smarthome_hub/smarthome_hub.kicad_pcb

# 4. Repository hardware contract tests (no prod server needed)
C:\Users\LENOVO\miniconda3\python.exe -m pytest --timeout=60 --basetemp=C:\Users\LENOVO\datn-wt\agyhwdiy2_20261121\scratch\pytest_tmp -v tests/test_hw_contract_6devices_20261120.py
```

### Verification Summary Counts

- **ERC (`docs/phan_cung/diy_pcb/erc_report.txt` & `.json`)**: **`0` errors, `0` warnings** across both sheets (`/`, `/System Plug-In Wiring Harness/`).
- **DRC (`docs/phan_cung/diy_pcb/drc_report.txt` & `.json`)**: **`0` DRC violations, `0` unconnected pads, `0` footprint / schematic-parity errors**.
- **PyMuPDF PDF 1:1 & Mirror Proofs**:
  - `toner_B.Cu_MIRRORED_1to1.pdf`: A4 (`297.00 x 210.01 mm`), board `100.000 x 80.000 mm`, scale bar **`50.000 mm`**, text reads **BACKWARDS**, J1/J2 terminal blocks reflected to `X = 91.00 mm`.
  - `toner_B.Cu_check_NOT_mirrored_1to1.pdf`: A4 (`297.00 x 210.01 mm`), board `100.000 x 80.000 mm`, scale bar **`50.000 mm`**, text reads **FORWARD**, J1/J2 at `X = 9.00 mm`.
  - `placement_top_silk_1to1.pdf`: A4 (`297.00 x 210.01 mm`), board `100.000 x 80.000 mm`, scale bar **`50.000 mm`**, non-mirrored.
  - `drill_map.pdf`: A4 (`297.00 x 210.00 mm`), board `100.000 x 80.000 mm`, scale bar **`50.000 mm`**, non-mirrored, `122/122` holes.
- **Repository Hardware Contract Suite (`tests/test_hw_contract_6devices_20261120.py`)**: **`14 passed`**, `0 failed` (`15.73s`).

---

## 4. Independent Review (`/teamwork` Separate Reviewer Role)

A fresh, read-only Independent Reviewer subagent (`conversationId: 4bd436fb-1d87-4eb6-a408-ec7bd008b3ab`, inherited high-effort model) audited all deliverables across two rounds:

- **Round 1 Verdict**: `FAIL` — caught 2 blocking defects, 2 moderate issues, and 5 minor polish items:
  1. **[BLOCKING — FIXED]** `(remove_unused_layers yes)` stripped 12 NC NodeMCU socket pads (`U1.2..U1.9`, `U1.12..13`, `U2.12..13`) from `B_Cu.gbl` (`106` flashes vs `118` PTH holes). **Fix**: restored `(remove_unused_layers no)` so all `118/118` PTH pads render solidly on `B_Cu.gbl` and both toner PDFs, and exported true single-layer Gerbers (`B.Cu` only, omitting `F_Cu.gtl`).
  2. **[BLOCKING — FIXED]** KiCad's auto-fit `drill_map.pdf` scaled the board ~1.45x (`144.7 x 115.8 mm`), contradicting the 1:1 overlay guide. **Fix**: generated a true **1:1 `drill_map.pdf`** (`100.000 x 80.000 mm` outline + `50.000 mm` scale bar + 122 holes from `.drl` + 4-symbol legend), verified by PyMuPDF.
  3. **[MODERATE — FIXED]** `C4` (`10uF 16V`) proximity to the NodeMCU Micro-USB plug corridor. **Fix**: documented low-profile (`H <= 7 mm`) / lay-flat mounting guidance in `DIY_GUIDE.md` and `BOM_DIY_SHOPPING.md`.
  4. **[MODERATE — FIXED]** Untracked stale KiCad lock file `~smarthome_hub.kicad_pro.lck`. **Fix**: deleted cleanly.
  5. **[MINOR — FIXED]** `.kicad_dru` comments updated from `3.80 x 1.84 mm` to exact `3.80 x 1.80 mm / 0.35 mm / 0.74 mm`.
  6. **[MINOR — ACCEPTED]** KiCad 10 `FootprintSave()` writes `*.Cu` in `.kicad_mod` for THT pads; `lib_footprint_mismatch = 0` and single-sided Gerber export omits `F_Cu.gtl`.
  7. **[MINOR — FIXED]** `D3` 3D model updated to `LED_D3.0mm_Green.step` (now renders green in 3D).
  8. **[MINOR — FIXED]** `F.Fab` assembly labels for `C1, C2, C4, D3, U1, U2` repositioned clear of drill dots on `placement_top_silk_1to1.pdf`.
  9. **[MINOR — FIXED]** Regenerated all exports, ERC/DRC reports, and screenshots `90..95`.
- **Round 2 Final Verdict**: **`PASS`** — **0 blocking, 0 moderate, 0 open minor findings**.

---

## 5. Screenshots List (`C:\Users\LENOVO\datn-wt\agyhwdiy2_20261121\screenshots\`)

All 6 screenshots are real tool renders/rasterizations visually inspected by both the author and Independent Reviewer:

1. **`90_kicad_3d_iso.png`**: KiCad 10 `pcb render` isometric 3D view (`-45,0,35`) showing the `100 x 80 x 1.6 mm` board, green Phoenix screw terminals (`J1, J2`), green LED (`D3`), NodeMCU sockets (`U1, U2`), edge connectors, 4x M3 corner holes, and top-side jumper lines (`J-1..J-7`).
2. **`91_kicad_3d_top.png`**: KiCad 10 `pcb render` top orthographic view clearly displaying all 52 crisp `F.SilkS` labels (`>= 1.5 mm`), polarity markings, connector pinouts, and generous component spacing.
3. **`92_kicad_2d_copper_layout.png`**: KiCad 10 2D PDF export (`B.Cu, F.SilkS, Edge.Cuts, Dwgs.User`) rasterized at 250 DPI showing thick `2.0 mm` power/GND buses, `1.0 mm` signal traces, all `118/118` `B.Cu` PTH pads (including all 15/15 pins on `U1` and `U2`), 7 top jumper bridges, and the `50.00 mm` calibration scale bar.
4. **`93_toner_pdf_page.png`**: Full A4 Page 1 rasterization of `toner_B.Cu_MIRRORED_1to1.pdf` confirming black-on-white `B.Cu` copper with centered drill-guide pilot marks, `118/118` pads, crop marks, `50.00 mm` scale bar, and horizontally **mirrored (backwards)** text.
5. **`94_drill_map.png`**: Rasterization of the true 1:1 `drill_map.pdf` showing the `100.0 x 80.0 mm` outline, all 122 holes color-and-symbol coded into the exact 4 drill bits (`0.9 / 1.1 / 1.3 / 3.2 mm`), `50.00 mm` 1:1 verification scale bar, and step-by-step hand-drilling legend.
6. **`95_drc_result.png`**: Rendered summary of the actual `erc_report.txt` (`0 errors / 0 warnings`), `drc_report.txt` (`0 violations / 0 unconnected / 0 footprint errors`), and automated single-layer / Gerber / PDF 1:1 / mirror audit proofs.

---

## 6. Committed Deliverables (`docs/phan_cung/diy_pcb/` & `hardware/kicad/smarthome_hub/`)

- `docs/phan_cung/diy_pcb/toner_B.Cu_MIRRORED_1to1.pdf`
- `docs/phan_cung/diy_pcb/toner_B.Cu_check_NOT_mirrored_1to1.pdf`
- `docs/phan_cung/diy_pcb/placement_top_silk_1to1.pdf`
- `docs/phan_cung/diy_pcb/drill_map.pdf` & `drill_map.png`
- `docs/phan_cung/diy_pcb/smarthome_hub.drl` (Excellon, mm)
- `docs/phan_cung/diy_pcb/drill_table.csv` & `drill_table.md`
- `docs/phan_cung/diy_pcb/jumper_list.md`
- `docs/phan_cung/diy_pcb/BOM_DIY_SHOPPING.md` (+ updated `docs/phan_cung/DANH_SACH_LINH_KIEN_HIEN_CO_VA_CAN_MUA.md`)
- `docs/phan_cung/diy_pcb/DIY_GUIDE.md` (Vietnamese, full diacritics, UTF-8)
- `docs/phan_cung/diy_pcb/gerbers/` (single-layer `B.Cu` Gerber + PTH/NPTH/merged Excellon drill files)
- `docs/phan_cung/diy_pcb/erc_report.{txt,json}` & `drc_report.{txt,json}`
- `docs/phan_cung/diy_pcb/DIY_REPORT.md`
- `hardware/kicad/smarthome_hub/` (synchronized `smarthome_hub.{kicad_sch,kicad_pcb,kicad_pro,kicad_dru}`, `DIY_Hub.pretty/`, `fp-lib-table`, `bom.csv`, `gerbers/`, `reports/`, `build_diy_hub.py`, `export_and_verify_diy.py`)

---

## 7. Deferred Items

None. All requirements in `PROMPT.txt` are 100% completed, verified, independently reviewed (`PASS`), committed on `hwdiy-20261121`, and pushed to `origin/hwdiy-20261121`.
