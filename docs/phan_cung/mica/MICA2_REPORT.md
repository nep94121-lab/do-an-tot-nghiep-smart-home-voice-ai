STATUS: ALL_DONE

# Smart Home Parametric Acrylic (Mica) House — MICA2 Report (`agyhwmica2_20261121`)

## 1. Goal & Summary (Old MICA1 vs New MICA2)

**Goal.** Enlarge and redesign the parametric FreeCAD acrylic (mica) Smart Home house (`hardware/freecad/mica/smarthome_mica_house.FCStd`) so hand cutting and hand drilling are forgiving, with a dedicated mounting plate for the redesigned `100.0 × 80.0 mm` Hub PCB (`90.0 × 70.0 mm` M3 hole pattern, `Ø3.4 mm` holes, `>= 10 mm` free margin), generous `>= 15.0 mm` internal wiring gaps across all 14 off-board modules, `+0.5 mm` datasheet hole/cutout clearances, `>= 3.0 mm` minimum hole diameter (documenting only physical datasheet exceptions), `0.25 mm` (`0.20–0.30 mm`) tab-slot clearance, `>= 14.0 mm` tabs (`>= 12.0 mm`), and single-cell `2 / 3 / 5 mm` thickness recompute.

- **Worktree & Branch:** `C:\Users\LENOVO\datn-wt\hwmica2` on branch `hwmica2-20261121` (branched from `master` `131bdc2`; branch-only, not merged to `master`, prod port `8088` and sibling runs untouched).
- **Deliverables Commit Hash:** `e8f0e68a5a27691ebf0785d5a16614b2b7eabc59` (`feat(mica2): enlarge parametric FreeCAD acrylic house for hand-cutting & 100x80 Hub PCB`, `106` files exclusively under `hardware/freecad/mica/` and `docs/phan_cung/mica/`).
- **Removed Hardware Compliance:** Zero `fan`, zero `ac`, zero `VS1838B`, zero `IR` anywhere in CAD, DXFs, drawings, CSV, verification reports, or docs.
- **Locked 10-Pin ESP8266 Contract:** `D0` Living LED, `D1` SG90 Servo, `D2` DHT11, `D3` PWM Audio (PAM8403), `D4` Bedroom LED (Active-LOW), `D5` KY-037 DO, `D6` Relay 1 (Pump), `D7` Relay 2 (PAM8403 Power, Jumper `H`), `D8` Buzzer (TMB12A05), `A0` Soil Moisture (YL-69 + LM393 AO).

| Metric | Old (MICA1) | New (MICA2) | Change / Improvement |
|---|---:|---:|---|
| **Assembled Base Footprint** | `380.0 × 286.0 mm` (`1086.8 cm²`) | **`406.0 × 390.0 mm`** (`1583.4 cm²`) | **+45.7% floor area**, split into `P01A` (`406×181.9`) + `P01B` (`406×215.9`) + `2× P17` so 100% fits A3 |
| **House Outer Envelope (L×D×H)** | `356.0 × 178.0 × 135.0 mm` | **`386.0 × 190.0 × 150.0 mm`** | `+30 mm` wider, `+12 mm` deeper, `+15 mm` taller |
| **Technical Bay Interior** | `200 × 94 mm` (`188.0 cm²`) | **`248 × 145 mm`** (`359.6 cm²`) | **+91% usable Tech Bay area**; `18.0 mm` minimum wiring gap (`>= 15.0 mm`) |
| **Water Tank & Garden Box** | `134 × 74 × 44/40 mm` | **`130 × 126 × 54/48 mm`** | **+103% water/planter volume**, `40 mm` dry gap from house front wall |
| **Hub PCB & Mount Pattern** | `80 × 65 mm` direct on base (`71 × 56`, `Ø3.2`) | **`100 × 80 mm`** on removable **`P16_PCB_PLATE` (`130 × 110 mm`)**, `90 × 70 mm` **`Ø3.4 mm`** | **`15.0 mm` free margin** on all 4 sides (`>= 10.0 mm` req), removable for service |
| **Panel & Piece Count** | `15` panels (`15` pieces) | **`18` unique panels (`19` pieces)** | Added split base (`P01A`/`P01B`), `P16_PCB_PLATE`, `2× P17_BASE_JOINER` |
| **Tab-Slot Joints / Clearance** | `55` joints, `kerf = 0.15 mm` | **`59` joints, `tab_clr = 0.25 mm`** | Verified across `0.20 / 0.25 / 0.30 mm` & `T = 2 / 3 / 5 mm` |
| **Minimum Tab Width** | `10.0 mm` | **`14.0 mm`** (`14 / 16 / 18 / 24 mm`) | Exceeds `>= 12.0 mm` hand-cut rule |
| **Minimum General Hole Dia** | `2.0 mm` (SG90/door), `2.5 mm` (grille), `2.7 mm` (PAM) | **`3.0 mm`** (only `< 3 mm` exception: `2× Ø2.5 mm` SG90 M2 ears) | Forgiving for hand drilling; all 14 datasheet features `>= +0.5 mm` |
| **Cable Pass-Through Holes** | `Ø10.0 mm` | **`Ø14.0 mm`** (`6×` across `P02`/`P03`/`P05`/`P06`) | Easy bundled 2.54 mm Dupont routing |
| **5V 2A DC Input & USB Access** | `12 × 10 mm` rect opening, `114 mm` USB lip | **DC-022 `Ø12.5 mm`** round M12 mount + **`128 mm`** low USB cutaway | Direct panel-mount 5.5×2.1 mm jack & unobstructed Micro-USB plug-in |
| **Net Acrylic Area / A3 Sheets** | `2451.5 cm²` / `3` A3 sheets | **`3516.4 cm²`** / **`6` A3 sheets** (`19/19` pcs) | True 1:1 printable PDFs for A3 (`6` sheets) + A4 (`5` sheets + `9`-page tiled oversized PDF) |

---

## 2. Parametric Spreadsheet Table (`Params` in `smarthome_mica_house.FCStd`)

All `38` named parameters live in FreeCAD Spreadsheet `Params` (single-source-of-truth in `hardware/freecad/mica/mica_design.py`):

| Alias | Label | Value / Formula | Unit & Engineering Note |
|---|---|---:|---|
| `T_mm` | T (Sheet Thickness mm) | `3.0` | mm (single cell `B2`; verified at `2.0`, `3.0`, `5.0 mm`) |
| `tab_clr` | Tab-Slot Joint Clearance | `0.25` | mm (cell `B3`; verified at `0.20`, `0.25`, `0.30 mm`) |
| `slot_w` | Slot Width (`= T_mm + tab_clr`) | `=T_mm + tab_clr` | mm (`3.25 mm` default) |
| `base_L` | Base Plate Total Length (X) | `406.0` | mm (fits A3 usable `410 × 287 mm`) |
| `base_W` | Base Plate Total Width (Y) | `390.0` | mm (split at `Y = 174` into `P01A` + `P01B`) |
| `house_L` | House Outer Length (X) | `386.0` | mm (`X: 10..396`) |
| `house_D` | House Outer Depth (Y) | `190.0` | mm (`Y: 192..382`) |
| `wall_H` | Full Wall Height (Z) | `147.0` | mm (`+3 mm` base = `150.0 mm` total height) |
| `cut_H` | Cutaway Low Wall Height (Z) | `34.0` | mm (front & side cutaway waist) |
| `door_W` | Main Door Opening Width | `60.0` | mm (door leaf `56 × 100 mm`, `2.0 mm` clearance) |
| `door_H` | Main Door Opening Height | `104.0` | mm |
| `tab_W` | House Wall Finger Tab Width | `18.0` | mm (`>= 12 mm`) |
| `tab_G` | Garden & Corner Tab Width | `14.0` | mm (`>= 12 mm`) |
| `tab_S` | Base Seam Finger Tab Width | `24.0` | mm (`P01A`/`P01B` interlocking seam) |
| `pcb_L` | Hub PCB Length (X) | `100.0` | mm (redesigned `100 × 80 × 1.6 mm` Hub PCB) |
| `pcb_W` | Hub PCB Width (Y) | `80.0` | mm |
| `pcb_hx` | Hub PCB M3 Pattern X | `90.0` | mm (`5.0 mm` corner inset) |
| `pcb_hy` | Hub PCB M3 Pattern Y | `70.0` | mm (`5.0 mm` corner inset) |
| `pcb_margin` | PCB Mounting Plate Margin | `15.0` | mm (`P16_PCB_PLATE = 130 × 110 mm >= 10 mm`) |
| `pcb_m3_d` | PCB / Plate / Joiner M3 Dia | `3.4` | mm (`90×70` PCB holes, `P16` corner & `P17` joiner holes) |
| `m3_mod_d` | Module M3 Mount Hole Dia | `3.5` | mm (M3 `3.0 + 0.5 mm`: Relays, DHT11, KY-037, LM393, Speaker clamps) |
| `clamp_d` | Clamp / Hinge / Linkage Dia | `3.0` | mm (PAM8403 ties, door hinges & servo linkage) |
| `sg90_m2_d` | SG90 M2 Ear Screw Hole Dia | `2.5` | mm (**ONLY `< 3 mm` exception:** M2 `2.0 + 0.5 mm`; use M2 washers) |
| `sg90_L` | SG90 Body Cutout Length | `23.3` | mm (`22.8 + 0.5 mm`) |
| `sg90_W` | SG90 Body Cutout Width | `12.7` | mm (`12.2 + 0.5 mm`) |
| `sg90_pitch` | SG90 M2 Hole Spacing | `27.8` | mm (TowerPro SG90 datasheet pitch) |
| `led5_d` | 5 mm LED Mount Hole Dia | `5.5` | mm (`5.0 + 0.5 mm`, Living & Bedroom LEDs) |
| `led3_d` | 3 mm Power LED Hole Dia | `3.5` | mm (`3.0 + 0.5 mm`, Front Power Indicator) |
| `buzzer_d` | 12 mm Active Buzzer Hole Dia | `12.5` | mm (`TMB12A05` `12.0 + 0.5 mm`) |
| `mic_d` | KY-037 Mic Aperture Dia | `10.5` | mm (`9.7 + 0.8 mm >= +0.5 mm`) |
| `dcjack_d` | DC-022 5V Barrel Jack Dia | `12.5` | mm (M12 barrel `12.0 + 0.5 mm`, fits `2/3/5 mm` panels) |
| `cable_d` | Cable Pass-Through Hole Dia | `14.0` | mm (generous Dupont bundle routing) |
| `tube_d` | Silicone Water Tube Hole Dia | `10.0` | mm (`8.0 mm` OD pump tube `+ 2.0 mm`) |
| `spk_hd` | Speaker Grille Hole Dia | `3.0` | mm (19-hole concentric grille `R6 / R12`, all webs `>= 3.0 mm`) |
| `dht_w` | DHT11 Vent Cutout Width | `12.5` | mm (`12.0 + 0.5 mm`) |
| `dht_h` | DHT11 Vent Cutout Height | `16.0` | mm (`15.5 + 0.5 mm`) |
| `soil_slot_L` | YL-69 Soil Probe Slot Length | `22.0` | mm (`20.0 + 2.0 mm`) |
| `soil_slot_W` | YL-69 Soil Probe Slot Width | `3.5` | mm (`1.6/2.5 + >= 0.5 mm`) |

---

## 3. Panel Table (18 Unique Panels / 19 Physical Pieces at `T = 3.0 mm`)

| Panel ID | Name | Qty | Size L × H (mm) | Net Area (cm²) | Holes / Rects | Exports (`docs/phan_cung/mica/`) |
|---|---|---:|---:|---:|---:|---|
| `P01A_BASE_TECH` | Base Plate Front (Tech Bay & Garden) | 1 | `406.00 × 181.88` | `704.64` | `18H / 15R` | DXF, PDF, PNG, SVG |
| `P01B_BASE_HOUSE` | Base Plate Rear (Living & Bedroom) | 1 | `406.00 × 215.88` | `857.65` | `4H / 18R` | DXF, PDF, PNG, SVG |
| `P02_WALL_BACK` | Rear Wall (Living + Bedroom) | 1 | `386.00 × 150.00` | `480.45` | `5H / 5R` | DXF, PDF, PNG, SVG |
| `P03_WALL_LEFT` | Left Cutaway Side Wall | 1 | `190.00 × 150.00` | `203.53` | `1H / 0R` | DXF, PDF, PNG, SVG |
| `P04_WALL_RIGHT` | Right Cutaway Side Wall | 1 | `190.00 × 150.00` | `196.03` | `0H / 0R` | DXF, PDF, PNG, SVG |
| `P05_WALL_FRONT` | Front Cutaway Facade & Door Portal | 1 | `386.00 × 150.00` | `192.71` | `5H / 3R` | DXF, PDF, PNG, SVG |
| `P06_WALL_MID` | Center Dividing Wall (w/ Buzzer Relief) | 1 | `190.00 × 150.00` | `211.78` | `1H / 0R` | DXF, PDF, PNG, SVG |
| `P07_SERVO_SHELF` | SG90 Door Servo Mount Shelf | 1 | `34.00 × 49.12` | `13.08` | `2H / 1R` | DXF, PDF, PNG, SVG |
| `P08_DOOR_LEAF` | Main Door Leaf | 1 | `56.00 × 100.00` | `47.99` | `3H / 1R` | DXF, PDF, PNG, SVG |
| `P09_GARDEN_LEFT` | Water Tank Left Wall | 1 | `126.00 × 57.00` | `65.58` | `0H / 0R` | DXF, PDF, PNG, SVG |
| `P10_WATER_DIVIDER` | Water-to-Garden Divider Wall | 1 | `126.00 × 57.00` | `65.59` | `1H / 0R` | DXF, PDF, PNG, SVG |
| `P11_GARDEN_RIGHT` | Garden Planter Right Wall | 1 | `126.00 × 51.00` | `59.20` | `0H / 0R` | DXF, PDF, PNG, SVG |
| `P12_GARDEN_FRONT` | Water & Garden Front Wall | 1 | `130.00 × 57.00` | `64.88` | `1H / 1R` | DXF, PDF, PNG, SVG |
| `P13_GARDEN_BACK` | Water & Garden Rear Wall | 1 | `130.00 × 57.00` | `64.98` | `0H / 1R` | DXF, PDF, PNG, SVG |
| `P14_SOIL_BRIDGE` | Garden Soil Probe Holder Bridge | 1 | `32.00 × 126.00` | `38.43` | `0H / 1R` | DXF, PDF, PNG, SVG |
| `P15_TECH_FASCIA` | Tech Bay Power & Speaker Fascia | 1 | `246.00 × 51.00` | `72.52` | `23H / 0R` | DXF, PDF, PNG, SVG |
| `P16_PCB_PLATE` | Hub PCB Mounting Plate (`100×80` / `90×70`) | 1 | `130.00 × 110.00` | `142.27` | `8H / 0R` | DXF, PDF, PNG, SVG |
| `P17_BASE_JOINER` | Base Seam Joiner Plate (`L` & `R`) | 2 | `64.00 × 28.00` | `17.56 × 2` | `4H / 0R` | DXF, PDF, PNG, SVG |
| **Total** | **18 Unique Panels / 19 Physical Pieces** | **19** | **A3: `6` sheets (`19/19`) · A4: `5` sheets (`15/19`) + `9` tiled pages** | **`3516.4 cm²`** (`0.3516 m²`) | **`76` unique H (`80` phys) / `46` R** | All DXF/PDF/PNG/SVG + 1:1 PDFs |

---

## 4. Hole Statistics (`docs/phan_cung/mica/holes_table.csv`)

- **CSV Schema:** Exact required header `panel,id,x,y,diameter,purpose` (UTF-8, `76` data rows matching all `18` DXFs within `<= 0.001 mm`).
- **Minimum General Hole Diameter:** **`3.0 mm`** (`74/76` unique holes `>= 3.0 mm`).
- **Documented `< 3.0 mm` Exception (Only 1 Module):** `P07_SERVO_SHELF` `SG90_M2_Front` & `SG90_M2_Rear` (`Ø2.50 mm` = M2 `2.0 + 0.5 mm`, datasheet `27.8 mm` pitch around `23.3 × 12.7 mm` cutout leaving `1.00 mm` flange web; M2 washers mandated in `MICA_PANELS.md` & `ASSEMBLY_GUIDE.md`).

| Diameter | Unique Count (`holes_table.csv`) | Physical Count (`19` pcs) | Panels & Purpose |
|---:|---:|---:|---|
| **`Ø2.5 mm`** | `2` | `2` | `P07_SERVO_SHELF`: TowerPro SG90 M2 ear screws *(documented exception; use M2 washers)* |
| **`Ø3.0 mm`** | `24` | `24` | `P15`: `19×` speaker grille; `P08`: `3×` door hinges & servo link; `P01A`: `2×` PAM8403 clamps |
| **`Ø3.4 mm`** | `24` | `28` | `P16`: `4×` Hub PCB `90×70` + `4×` corners; `P01A`: `4×` plate standoffs + `4×` joiner; `P01B`: `4×` joiner; `2× P17`: `8×` joiner |
| **`Ø3.5 mm`** | `14` | `14` | `P01A`: `4×` Relay 1 + `4×` Relay 2; `P02`: `1×` DHT11; `P05`: `1×` KY-037; `P12`: `1×` LM393; `P15`: `1×` Power LED + `2×` speaker clamps |
| **`Ø5.5 mm`** | `2` | `2` | `P02_WALL_BACK`: Living Room (`D0`) & Bedroom (`D4`) 5 mm LEDs |
| **`Ø10.0 mm`** | `1` | `1` | `P10_WATER_DIVIDER`: `6/8 mm` (`OD 8.0 mm`) silicone pump tube |
| **`Ø10.5 mm`** | `1` | `1` | `P05_WALL_FRONT`: KY-037/038 electret mic aperture (`Ø9.7 mm` capsule) |
| **`Ø12.5 mm`** | `2` | `2` | `P05_WALL_FRONT`: TMB12A05 Buzzer (`Ø12.0 mm`); `P15_TECH_FASCIA`: DC-022 M12 barrel jack |
| **`Ø14.0 mm`** | `6` | `6` | `P02` (`2×`), `P03` (`1×`), `P05` (`2×`), `P06` (`1×`): Dupont bundle cable pass-throughs |
| **Total** | **`76`** | **`80`** | 100% matched to DXF circles & engineering drawings |

---

## 5. Verification Results (All Checks `PASS`)

1. **FreeCAD 1.1.4 Parametric Recompute & 3D BRep Collision Suite (`build_mica.py` → `freecad_recompute_check.log`, `joint_collision_check.json`):** **ALL_PASS**
   - `T = 2.0, 3.0, 5.0 mm` (at `tab_clr = 0.25 mm`) and `tab_clr = 0.20, 0.25, 0.30 mm` (at `T = 3.0 mm`): **`0` document errors**, **`19/19` valid single-solid panels**, **`0.0000%` max volume error**, **`0.00 mm` max dim error**.
   - **Panel-to-Panel 3D BRep Collision Check:** `171` pairs × `5` sweeps = **`0` collisions** (`max_intersection_vol_mm3 = 0.000000 mm³`).
   - **Tab-Slot 3D Joint-Fit Check:** **`59/59` joints engaged** (`0` failures; `len_gap = width_gap = 0.20 / 0.25 / 0.30 mm`, strictly inside `0.20–0.30 mm`).
   - **Hardware-vs-Panel 3D BRep Collision Check (`T = 3.0 mm`):** **`337` non-host pairs** (`18` hardware solids × `19` panels minus `5` host flange pairs) = **`0` collisions** (`max_intersection_vol_mm3 = 0.000000 mm³`).
2. **Automated 9-Gate Export & Geometry Suite (`export_drawings_and_verify.py` → `docs/phan_cung/mica/verification_report.json`):** **ALL_PASS (`9/9`)**
   - `dxf_closed_contours`: **PASS** (`18/18` panels, `$INSUNITS = 4`, closed contours, `0.000 mm` bbox error)
   - `min_hole_and_datasheet_clearance`: **PASS** (`76` holes, `14` datasheet `+0.5 mm` checks, `2` documented SG90 M2 exceptions)
   - `min_web_and_non_overlap`: **PASS** (`min_general_web_mm = 3.0 mm >= 2.0 mm`, `0` violations)
   - `tab_slot_matching_and_min_tab`: **PASS** (`59` joints, `min_tab_width_mm = 14.0 mm >= 12.0 mm`)
   - `freecad_recompute_and_3d_collision`: **PASS** (`0` panel-panel collisions, `0` HW-vs-panel collisions across `337` pairs, `0.0 mm` BRep-vs-DXF diff)
   - `pcb_plate_fit_90x70`: **PASS** (`P16_PCB_PLATE` `130 × 110 mm`, `90 × 70 mm` `Ø3.4 mm`, `15.0 mm` free margins on all 4 sides `>= 10.0 mm`)
   - `modules_fit_rooms_and_15mm_wiring_gaps`: **PASS** (`17` hardware entries, `135` non-mated pairs, **`min_wiring_gap_mm = 18.0 mm >= 15.0 mm`** between `HW_RELAY1` & `HW_RELAY2`, `0` forbidden fan/AC/IR hits)
   - `sheet_nesting_a3_and_a4`: **PASS** (`6` A3 sheets `19/19` pcs `0` oversized; `5` A4 sheets `15/19` pcs + `9`-page tiled 1:1 PDF for `4` oversized panels)
   - `holes_csv_consistency`: **PASS** (`76` rows, exact header, 1:1 match to DXFs)
3. **Repository Hardware Contract Pytest Suite (`tests/test_hw_contract_6devices_20261120.py`):** **PASS (`14 passed in 13.80s`, exit code `0`)**.

---

## 6. Independent Review Verdict & Findings (`/teamwork` Separate Reviewer)

A separate, strictly read-only **Independent Reviewer** role (did not author any CAD, drawing, or documentation files) audited every deliverable across two rounds:

- **Round 1 Verdict: `FAIL`** — caught **1 CRITICAL**, **3 MAJOR**, and **3 MINOR** technical findings (plus pending final report):
  1. **[CRITICAL — FIXED]** `HW_BUZZER` (TMB12A05 on `P05_WALL_FRONT`) penetrated `6.425 mm` through `P06_WALL_MID`, and `build_mica.py` lacked a `Hardware_Reference × Acrylic_Panels` BRep check. **Fix:** Added a clean top-front corner relief step (`u < 22.0 mm, Z > 112.0 mm`) in `P06_WALL_MID` giving `12.45 mm` rear Y clearance and `8.0 mm` vertical clearance around the buzzer + rear Dupont pins, and added `_check_hardware_vs_panel_collisions()` in `build_mica.py` verifying all `337` non-host 3D BRep pairs (`0.000000 mm³` interference).
  2. **[MAJOR — FIXED]** Clipped 3rd suptitle line in `docs/phan_cung/mica/sheet_layout_A4.png`. **Fix:** Wrapped oversized panel list onto clean multi-line header with `fontsize = 10.0`.
  3. **[MAJOR — FIXED]** Overlapping hole labels on `P05_WALL_FRONT.png` (`H2`/`H3`) and `P15_TECH_FASCIA.png` (`H3`/`H4` over speaker grille), badge crowding on `101_mica_exploded.png`, and overlapping `NodeMCU`/`Hub PCB` anchor dots + mis-anchored wiring-gap arrow on `104_mica_internal_layout.png`. **Fix:** Added per-panel leader offsets, nudged exploded badges into open whitespace, anchored `4. Hub PCB` to exposed green corner `(118, 125, 20.6)`, and anchored `Min Gap = 18.0 mm` directly to `(196, 114, 17)` between `HW_RELAY1` and `HW_RELAY2`.
  4. **[MAJOR — FIXED]** 8-step sidebar in `assembly_exploded.png`/`.pdf` contradicted the 9-step order in `ASSEMBLY_GUIDE.md`. **Fix:** Updated `compose_screenshots.py` to match the exact 9-step sequence (`Bước 1 → Bước 9`).
  5. **[MINOR — FIXED]** Stale `"17 unique panels (18 physical pieces)"` docstrings in `mica_design.py` and `build_mica.py`. **Fix:** Updated to `"18 unique panels (19 physical pieces)"`.
  6. **[MINOR — FIXED]** Mid-word `...` truncation in drawing title-block notes and 2-decimal rounding of `.125`/`.225`/`.025` coordinates. **Fix:** Wrapped notes cleanly to 2 lines and formatted 3 decimals whenever the 3rd decimal digit is non-zero.
  7. **[MINOR — FIXED]** Horizontal label overflow on narrow `P11_GARDEN_RIGHT` on A3 Sheet #3 and `"1 pieces"` plural grammar on Sheets #4 & #6. **Fix:** Rotated labels `90°` on narrow tall panels and fixed singular `"1 piece"`.
- **Round 2 Verdict (Fresh Independent Reviewer): `PASS`** — All 7 Round-1 findings verified **FIXED** directly against FreeCAD logs, JSONs, DXFs, CSV, Markdown docs, and visually inspected PNGs; **zero new findings** (`0 CRITICAL / 0 MAJOR / 0 MINOR`).

---

## 7. Real Tool-Export Screenshots (`C:\Users\LENOVO\datn-wt\agyhwmica2_20261121\screenshots\`)

Every screenshot was produced directly by headless FreeCAD 1.1.4 Coin3D (`SoOffscreenRenderer`) or matplotlib engineering drawing/nesting exports and visually inspected by both the author team and the Independent Reviewer:

| # | File | Resolution | Size (Bytes) | Tool Source & What It Shows |
|---:|---|---:|---:|---|
| 100 | `100_mica_3d_assembled.png` | `1920 × 1200` | `199,288` | **FreeCAD 1.1.4 Coin3D 3D Assembly:** Enlarged translucent 19-piece acrylic house on `406 × 390 mm` split base with all 17 vivid hardware solids, water tube arch, visible `P06_WALL_MID` buzzer relief step, legend, and unclipped callouts. |
| 101 | `101_mica_exploded.png` | `1920 × 1200` | `158,083` | **FreeCAD 1.1.4 Coin3D 3D Exploded View:** All 18 unique panels (`19` physical pieces including `P01A`, `P01B`, `P16_PCB_PLATE`, `P17_BASE_JOINER_L/R`) exploded along assembly axes with red dashed guides and non-overlapping badges. |
| 102 | `102_mica_pcb_plate_drawing.png` | `2571 × 1819` | `465,633` | **Matplotlib Dimensioned Engineering Drawing (`P16_PCB_PLATE`):** `130.00 × 110.00 mm` plate, dashed green `100.0 × 80.0 × 1.6 mm` Hub PCB outline, red `90.00 × 70.00 mm` `4× Ø3.40 mm` holes, blue `116.00 × 96.00 mm` base standoff holes, all four `15.0 mm` margins, coordinate table, and verification summary. |
| 103 | `103_mica_sheet_layout_A3.png` | `3040 × 3420` | `490,659` | **Matplotlib A3 Sheet Nesting Layout:** All 6 A3 (`420 × 297 mm`) sheets packing all `19/19` physical pieces (`5 mm` border margin, `4 mm` spacing), `P16_PCB_PLATE` highlighted on Sheet #3, vertical rotated labels on narrow panels, stepped `P06_WALL_MID` on Sheet #6 (`17.0%`). |
| 104 | `104_mica_internal_layout.png` | `1920 × 1200` | `196,883` | **FreeCAD 1.1.4 Coin3D High-Angle Internal Cutaway:** Walls 80% translucent showing all 14 off-board modules + `100 × 80 mm` Hub PCB + `P16_PCB_PLATE` + 3 mm Power LED (`17` callouts in clean perimeter columns), separated `NodeMCU`/`Hub PCB` anchors, visible buzzer relief behind `TMB12A05`, and green verification banner pointing to the `18.0 mm` gap between `Relay 1` and `Relay 2`. |

---

## 8. How to Regenerate Everything Deterministically

From `C:\Users\LENOVO\datn-wt\hwmica2` (PowerShell):

```powershell
# 1. Build parametric smarthome_mica_house.FCStd & run T=2/3/5 + tab_clr=0.20/0.25/0.30 + 3D BRep collision sweeps
& "C:\Users\LENOVO\AppData\Local\Programs\FreeCAD 1.1\bin\freecadcmd.exe" hardware\freecad\mica\build_mica.py

# 2. Export 18 DXFs, 54 PDF/PNG/SVG drawings, holes_table.csv, A3/A4 1:1 PDFs, MICA_PANELS.md & run 9-gate verifier
python hardware/freecad/mica/export_drawings_and_verify.py

# 3. Render 3 headless FreeCAD Coin3D views & compose screenshots 100..104 + assembly_exploded.{png,pdf}
& "C:\Users\LENOVO\AppData\Local\Programs\FreeCAD 1.1\bin\freecadcmd.exe" hardware\freecad\mica\render_freecad_views.py
python hardware/freecad/mica/compose_screenshots.py
```

To change acrylic thickness (`2.0`, `3.0`, or `5.0 mm`) or joint clearance (`0.20`–`0.30 mm`) interactively inside FreeCAD, open `hardware/freecad/mica/smarthome_mica_house.FCStd`, edit `Params.B2` (`T_mm`) or `Params.B3` (`tab_clr`), and click **Recompute**.

---

## 9. Deferred Items

- **None within MICA2 scope.** All 9 tasks in `PROMPT.txt` Section 3 are complete and verified.
- *(Out of branch scope by rule)* Merging `hwmica2-20261121` into `master`, live KiCad PCB footprint regeneration (`100 × 80 mm` handled by sibling session), and production deployment are intentionally excluded per Section 1 hard safety rules.
