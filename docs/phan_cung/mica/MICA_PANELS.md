# Smart Home Open-Cutaway Acrylic (Mica) House — MICA2 Panel Schedule & Fabrication Spec

- **FreeCAD Parametric Source:** [`../../../hardware/freecad/mica/smarthome_mica_house.FCStd`](../../../hardware/freecad/mica/smarthome_mica_house.FCStd) (built via `hardware/freecad/mica/build_mica.py`, verified in FreeCAD `1.1.4.20260928 (Git shallow)`)
- **Default Material:** Clear Cast Acrylic (Mica), thickness **`T = 3.0 mm`** (single-cell parametric `Params.T_mm` verified for `2.0`, `3.0`, and `5.0 mm`)
- **Hand-Cut Friendly Joint Clearance:** **`tab_clr = 0.25 mm`** (`slot_w = T + tab_clr = 3.25 mm`; verified for `0.20 / 0.25 / 0.30 mm`); minimum finger tab width **`14.0 mm`** (`>= 12.0 mm`); **`59`** tab-slot/notch joints total
- **Enlarged Footprint:** `406.0 × 390.0 mm` split interlocking base (`P01A_BASE_TECH` + `P01B_BASE_HOUSE` + `2× P17_BASE_JOINER`), `386.0 × 190.0 × 150.0 mm` house
- **Hub PCB Mounting:** Dedicated removable `P16_PCB_PLATE` (`130.0 × 110.0 mm`) with exact **`90.0 × 70.0 mm`** `4× Ø3.40 mm` M3 pattern and **`15.0 mm` free margin** on all 4 sides around the `100 × 80 mm` Hub PCB
- **Hardware Scope:** `100 × 80 mm` Hub PCB + **14 off-board modules** + `3 mm` Power Indicator LED (**zero fan, zero AC, zero IR**); minimum inter-module wiring gap **`18.0 mm`** (`>= 15.0 mm` across all `135` checked pairs)
- **Companion Guides & Data:**
  - Vietnamese Step-by-Step Build & Hand-Cutting Guide: [`ASSEMBLY_GUIDE.md`](ASSEMBLY_GUIDE.md)
  - Complete Circular Hole Coordinates CSV: [`holes_table.csv`](holes_table.csv) (`76` unique circular holes across `18` unique panels; `80` physical holes across `19` pieces counting `2× P17_BASE_JOINER`, bottom-left `(0, 0)` datum)
  - Master 40-Wire & Locked 10-Pin ESP8266 Contract: [`../WIRING_TABLE.md`](../WIRING_TABLE.md)
  - 3D Exploded Assembly View: [`assembly_exploded.pdf`](assembly_exploded.pdf) · [`assembly_exploded.png`](assembly_exploded.png)

## 1. Panel Cutting Schedule (18 Unique Panels / 19 Physical Pieces)

| Panel ID | Name | Qty | Size L x H (mm) | Thickness | Features (Holes/Rects) | Exports (DXF / PDF / PNG / SVG) | Notes |
|---|---|---:|---:|---:|---:|---|---|
| `P01A_BASE_TECH` | Base Plate Front (Tech Bay & Garden) | 1 | `406.0 x 181.9` | `3.0 mm` | 33 (18H / 15R) | [DXF](panels_dxf/P01A_BASE_TECH.dxf) / [PDF](drawings/P01A_BASE_TECH.pdf) / [PNG](drawings/P01A_BASE_TECH.png) / [SVG](drawings/P01A_BASE_TECH.svg) | Front A3-sized base half (406x182 mm): Tech Fascia, P16_PCB_PLATE standoffs, Relay1, Relay2, PAM8403, Water Tank & Garden Planter, interlocking seam tabs. |
| `P01B_BASE_HOUSE` | Base Plate Rear (Living & Bedroom House) | 1 | `406.0 x 215.9` | `3.0 mm` | 22 (4H / 18R) | [DXF](panels_dxf/P01B_BASE_HOUSE.dxf) / [PDF](drawings/P01B_BASE_HOUSE.pdf) / [PNG](drawings/P01B_BASE_HOUSE.png) / [SVG](drawings/P01B_BASE_HOUSE.svg) | Rear A3-sized base half (406x216 mm): Living Room & Bedroom floor with slots for P02..P06 and interlocking seam notches. |
| `P02_WALL_BACK` | Rear Wall (Living + Bedroom) | 1 | `386.0 x 150.0` | `3.0 mm` | 10 (5H / 5R) | [DXF](panels_dxf/P02_WALL_BACK.dxf) / [PDF](drawings/P02_WALL_BACK.pdf) / [PNG](drawings/P02_WALL_BACK.png) / [SVG](drawings/P02_WALL_BACK.svg) | Full-height rear wall (386x147) with 124x64 Bedroom window, Living/Bedroom 5mm LEDs (Dia 5.5), DHT11 vent (12.5x16.0) + M3 (Dia 3.5), Dia 14 cable holes. |
| `P03_WALL_LEFT` | Left Cutaway Side Wall | 1 | `190.0 x 150.0` | `3.0 mm` | 1 (1H / 0R) | [DXF](panels_dxf/P03_WALL_LEFT.dxf) / [PDF](drawings/P03_WALL_LEFT.pdf) / [PNG](drawings/P03_WALL_LEFT.png) / [SVG](drawings/P03_WALL_LEFT.svg) | Open-cutaway side wall: full height 147mm rear, low 34mm cutaway front (step u=64mm). |
| `P04_WALL_RIGHT` | Right Cutaway Side Wall | 1 | `190.0 x 150.0` | `3.0 mm` | 0 (0H / 0R) | [DXF](panels_dxf/P04_WALL_RIGHT.dxf) / [PDF](drawings/P04_WALL_RIGHT.pdf) / [PNG](drawings/P04_WALL_RIGHT.png) / [SVG](drawings/P04_WALL_RIGHT.svg) | Open-cutaway side wall: full height 147mm rear, low 34mm cutaway front (step u=72mm). |
| `P05_WALL_FRONT` | Front Cutaway Facade & Door Portal | 1 | `386.0 x 150.0` | `3.0 mm` | 8 (5H / 3R) | [DXF](panels_dxf/P05_WALL_FRONT.dxf) / [PDF](drawings/P05_WALL_FRONT.pdf) / [PNG](drawings/P05_WALL_FRONT.png) / [SVG](drawings/P05_WALL_FRONT.svg) | Open-cutaway front facade (386x147) with 60x104 Door portal, P07 servo shelf slot, KY-037 mic+M3, Dia 12.5 Buzzer pillar, Dia 14 cable holes. |
| `P06_WALL_MID` | Center Dividing Wall (Living/Bedroom) | 1 | `190.0 x 150.0` | `3.0 mm` | 1 (1H / 0R) | [DXF](panels_dxf/P06_WALL_MID.dxf) / [PDF](drawings/P06_WALL_MID.pdf) / [PNG](drawings/P06_WALL_MID.png) / [SVG](drawings/P06_WALL_MID.svg) | Divides Living Room & Bedroom: 52x104 doorway, Dia 14 cable hole, top-front buzzer relief step (u<22, Z>112). |
| `P07_SERVO_SHELF` | SG90 Door Servo Mount Shelf | 1 | `34.0 x 49.1` | `3.0 mm` | 3 (2H / 1R) | [DXF](panels_dxf/P07_SERVO_SHELF.dxf) / [PDF](drawings/P07_SERVO_SHELF.pdf) / [PNG](drawings/P07_SERVO_SHELF.png) / [SVG](drawings/P07_SERVO_SHELF.svg) | Slots into P05 left door jamb (16mm tab); 12.7x23.3mm SG90 cutout + 2x Dia 2.5mm M2 holes (only <3mm exception, use M2 washers). |
| `P08_DOOR_LEAF` | Main Door Leaf | 1 | `56.0 x 100.0` | `3.0 mm` | 4 (3H / 1R) | [DXF](panels_dxf/P08_DOOR_LEAF.dxf) / [PDF](drawings/P08_DOOR_LEAF.pdf) / [PNG](drawings/P08_DOOR_LEAF.png) / [SVG](drawings/P08_DOOR_LEAF.svg) | Fits 60x104mm opening with 2.0mm clearance all sides; decorative 26x30mm window & 3x Dia 3.0mm hinge/linkage holes. |
| `P09_GARDEN_LEFT` | Water Tank Left Wall | 1 | `126.0 x 57.0` | `3.0 mm` | 0 (0H / 0R) | [DXF](panels_dxf/P09_GARDEN_LEFT.dxf) / [PDF](drawings/P09_GARDEN_LEFT.pdf) / [PNG](drawings/P09_GARDEN_LEFT.png) / [SVG](drawings/P09_GARDEN_LEFT.svg) | Water reservoir left wall (126x54) with 10x8mm top pump cable notch; seal inner seams with silicone. |
| `P10_WATER_DIVIDER` | Water-to-Garden Divider Wall | 1 | `126.0 x 57.0` | `3.0 mm` | 1 (1H / 0R) | [DXF](panels_dxf/P10_WATER_DIVIDER.dxf) / [PDF](drawings/P10_WATER_DIVIDER.pdf) / [PNG](drawings/P10_WATER_DIVIDER.png) / [SVG](drawings/P10_WATER_DIVIDER.svg) | Separates water tank (52mm) from soil planter (78mm) with Dia 10.0mm silicone pump tube hole. |
| `P11_GARDEN_RIGHT` | Garden Planter Right Wall | 1 | `126.0 x 51.0` | `3.0 mm` | 0 (0H / 0R) | [DXF](panels_dxf/P11_GARDEN_RIGHT.dxf) / [PDF](drawings/P11_GARDEN_RIGHT.pdf) / [PNG](drawings/P11_GARDEN_RIGHT.png) / [SVG](drawings/P11_GARDEN_RIGHT.svg) | Outer right wall of garden soil planter box (126x48). |
| `P12_GARDEN_FRONT` | Water & Garden Front Wall | 1 | `130.0 x 57.0` | `3.0 mm` | 2 (1H / 1R) | [DXF](panels_dxf/P12_GARDEN_FRONT.dxf) / [PDF](drawings/P12_GARDEN_FRONT.pdf) / [PNG](drawings/P12_GARDEN_FRONT.png) / [SVG](drawings/P12_GARDEN_FRONT.svg) | Encloses Water Tank + Garden Planter front (130x54/48) with exterior LM393 M3 hole (Dia 3.5). |
| `P13_GARDEN_BACK` | Water & Garden Rear Wall | 1 | `130.0 x 57.0` | `3.0 mm` | 1 (0H / 1R) | [DXF](panels_dxf/P13_GARDEN_BACK.dxf) / [PDF](drawings/P13_GARDEN_BACK.pdf) / [PNG](drawings/P13_GARDEN_BACK.png) / [SVG](drawings/P13_GARDEN_BACK.svg) | Encloses Water Tank + Garden Planter rear (40mm dry air gap from house front wall). |
| `P14_SOIL_BRIDGE` | Garden Soil Probe Holder Bridge | 1 | `32.0 x 126.0` | `3.0 mm` | 1 (0H / 1R) | [DXF](panels_dxf/P14_SOIL_BRIDGE.dxf) / [PDF](drawings/P14_SOIL_BRIDGE.pdf) / [PNG](drawings/P14_SOIL_BRIDGE.png) / [SVG](drawings/P14_SOIL_BRIDGE.svg) | Slots across top of Garden Planter (14mm tabs) to hold YL-69 2-prong soil probe vertically (22.0x3.5mm slot). |
| `P15_TECH_FASCIA` | Tech Bay Power & Speaker Fascia | 1 | `246.0 x 51.0` | `3.0 mm` | 23 (23H / 0R) | [DXF](panels_dxf/P15_TECH_FASCIA.dxf) / [PDF](drawings/P15_TECH_FASCIA.pdf) / [PNG](drawings/P15_TECH_FASCIA.png) / [SVG](drawings/P15_TECH_FASCIA.svg) | Front technical fascia (246x48): DC-022 Dia 12.5mm power jack, 3mm Power LED, 128mm open USB service cutaway, 19-hole Dia 3.0mm speaker grille + 2x M3 clamps. |
| `P16_PCB_PLATE` | Hub PCB Mounting Plate (100x80 / 90x70 M3) | 1 | `130.0 x 110.0` | `3.0 mm` | 8 (8H / 0R) | [DXF](panels_dxf/P16_PCB_PLATE.dxf) / [PDF](drawings/P16_PCB_PLATE.pdf) / [PNG](drawings/P16_PCB_PLATE.png) / [SVG](drawings/P16_PCB_PLATE.svg) | Removable 130x110 mm PCB mounting plate: exact 90x70 mm Dia 3.4mm M3 pattern with 15.0 mm free margin on all 4 sides around 100x80 mm Hub PCB. |
| `P17_BASE_JOINER` | Base Seam Joiner Plate (qty=2) | 2 | `64.0 x 28.0` | `3.0 mm` | 4 (4H / 0R) | [DXF](panels_dxf/P17_BASE_JOINER.dxf) / [PDF](drawings/P17_BASE_JOINER.pdf) / [PNG](drawings/P17_BASE_JOINER.png) / [SVG](drawings/P17_BASE_JOINER.svg) | Cut 2 pieces (64x28 mm); bolted underneath P01A+P01B seam at X=100 and X=306 with 4x M3x12 screws & nuts each. |

## 2. Material Area, Sheet Nesting & Estimated Cost Note

### 2.1 Area & Nesting Summary
- **Total Panel Count:** `18` unique panels (`19` physical pieces including `2× P17_BASE_JOINER`)
- **Total Net Acrylic Area:** `3516.4 cm²` (`0.3516 m²`)
- **Total Bounding-Box Area:** `4401.3 cm²` (`0.4401 m²`)
- **A3 Sheets (`420 × 297 mm`, 5 mm margin, 4 mm spacing):** **`6` A3 sheets** hold all **19/19** pieces (`0` oversized) — [`sheet_layout_A3.dxf`](sheet_layout_A3.dxf) | [`sheet_layout_A3.png`](sheet_layout_A3.png) | [`sheet_layout_A3_1to1.pdf`](sheet_layout_A3_1to1.pdf):
  - **A3 Sheet #1** ([`sheet_layout_A3_sheet1.pdf`](sheet_layout_A3_sheet1.pdf), net util `79.8%`): `P01B_BASE_HOUSE`, `P15_TECH_FASCIA`, `P12_GARDEN_FRONT`
  - **A3 Sheet #2** ([`sheet_layout_A3_sheet2.pdf`](sheet_layout_A3_sheet2.pdf), net util `79.2%`): `P01A_BASE_TECH`, `P13_GARDEN_BACK`, `P09_GARDEN_LEFT`, `P10_WATER_DIVIDER`, `P14_SOIL_BRIDGE`, `P17_BASE_JOINER_L`, `P17_BASE_JOINER_R`, `P07_SERVO_SHELF`
  - **A3 Sheet #3** ([`sheet_layout_A3_sheet3.pdf`](sheet_layout_A3_sheet3.pdf), net util `58.5%`): `P02_WALL_BACK`, `P16_PCB_PLATE`, `P11_GARDEN_RIGHT`, `P08_DOOR_LEAF`
  - **A3 Sheet #4** ([`sheet_layout_A3_sheet4.pdf`](sheet_layout_A3_sheet4.pdf), net util `15.4%`): `P05_WALL_FRONT`
  - **A3 Sheet #5** ([`sheet_layout_A3_sheet5.pdf`](sheet_layout_A3_sheet5.pdf), net util `32.0%`): `P03_WALL_LEFT`, `P04_WALL_RIGHT`
  - **A3 Sheet #6** ([`sheet_layout_A3_sheet6.pdf`](sheet_layout_A3_sheet6.pdf), net util `17.0%`): `P06_WALL_MID`
- **A4 Sheets (`297 × 210 mm`, 5 mm margin, 4 mm spacing):** **`5` A4 sheets** hold `15` pieces — [`sheet_layout_A4.dxf`](sheet_layout_A4.dxf) | [`sheet_layout_A4.png`](sheet_layout_A4.png) | [`sheet_layout_A4_1to1.pdf`](sheet_layout_A4_1to1.pdf):
  - **A4 Sheet #1** ([`sheet_layout_A4_sheet1.pdf`](sheet_layout_A4_sheet1.pdf), net util `56.9%`): `P03_WALL_LEFT`, `P12_GARDEN_FRONT`, `P14_SOIL_BRIDGE`, `P17_BASE_JOINER_L`, `P17_BASE_JOINER_R`, `P07_SERVO_SHELF`
  - **A4 Sheet #2** ([`sheet_layout_A4_sheet2.pdf`](sheet_layout_A4_sheet2.pdf), net util `41.8%`): `P04_WALL_RIGHT`, `P13_GARDEN_BACK`
  - **A4 Sheet #3** ([`sheet_layout_A4_sheet3.pdf`](sheet_layout_A4_sheet3.pdf), net util `44.5%`): `P06_WALL_MID`, `P09_GARDEN_LEFT`
  - **A4 Sheet #4** ([`sheet_layout_A4_sheet4.pdf`](sheet_layout_A4_sheet4.pdf), net util `45.0%`): `P16_PCB_PLATE`, `P15_TECH_FASCIA`, `P10_WATER_DIVIDER`
  - **A4 Sheet #5** ([`sheet_layout_A4_sheet5.pdf`](sheet_layout_A4_sheet5.pdf), net util `17.2%`): `P11_GARDEN_RIGHT`, `P08_DOOR_LEAF`
- **A4 Tiled 1:1 Templates for Oversized Panels:** [`sheet_layout_A4_tiled_oversized_1to1.pdf`](sheet_layout_A4_tiled_oversized_1to1.pdf) (`9` A4 pages at true 1:1 mm scale with `50.0 mm` calibration bar & green registration crosshairs):
  - `P01A_BASE_TECH` (`406.0 × 181.875 mm`, A4 Landscape, `2` pages)
  - `P01B_BASE_HOUSE` (`406.0 × 215.875 mm`, A4 Portrait, `3` pages)
  - `P02_WALL_BACK` (`386.0 × 150.0 mm`, A4 Landscape, `2` pages)
  - `P05_WALL_FRONT` (`386.0 × 150.0 mm`, A4 Landscape, `2` pages)

### 2.2 Estimated Material & Fabrication Cost Note (Vietnam Student Market, ~25,000 VND/USD)

| Cost Item | Recommended Spec / Quantity | Est. Cost (VND) | Est. Cost (USD) | Notes |
|---|---|---:|---:|---|
| **Clear Cast Acrylic `3.0 mm` (Stock Sheet)** | `6×` A3 (`420×297 mm`) **or** `1× 600×900 mm` (`0.54 m²`) **or** `1× 600×1200 mm` (`0.72 m²`) | `150,000–280,000` | `$6.0–$11.2` | `600×900 mm` (`~150k–220k`) is tight for laser; `600×1200 mm` (`~220k–280k`) gives spare margin for hand cutting. |
| **M3 / M2 Standoffs, Screws, Nuts, Washers & Hinges** | `4×` M3×10 brass, `4×` M3×6, `11×` M3×8 nylon, `10×` M3×10/12, `2×` M2×8/10 + M2 washers, `2×` mini hinges, LED bezels | `45,000–70,000` | `$1.8–$2.8` | Easily sourced at local electronics markets (Chợ Trời / Nhật Tảo / Shopee). |
| **Acrylic Solvent Cement + Neutral Clear Silicone** | `1×` Chloroform / acrylic glue (`50–100 ml` + syringe) + `1×` clear neutral silicone tube | `35,000–55,000` | `$1.4–$2.2` | Neutral silicone required for waterproofing water tank (`P01A/P09/P10/P12/P13`). |
| **Option A — Local CO2 Laser Cutting Service** | Send `sheet_layout_A3.dxf` (`6` A3 sheets or nested on `600×900 mm`) | `80,000–150,000` | `$3.2–$6.0` | Fastest & cleanest edges; zero hand-tool cost. |
| **Option B — DIY Hand-Cutting Tools** *(reusable)* | Acrylic hook knife, masking tape, flat needle file, step/twist drills (`0 VND` cutting fee) | `120,000–200,000` | `$4.8–$8.0` | One-time reusable tool purchase if not already owned; cutting fee = `0 VND`. |
| **Total Mechanical Enclosure Budget** | **With Laser Cut (Option A)** / **DIY Hand-Cut (Option B, excl. owned drill)** | **`310k–555k`** / **`230k–405k`** *(materials only)* | **`$12.4–$22.2`** / **`$9.2–$16.2`** | Excludes electronics (NodeMCU, PCB, 14 modules). |

## 3. Circular Hole & Fastener Summary (`holes_table.csv`)

All `76` unique circular holes across the `18` panels (`80` physical holes across `19` pieces including the 2nd `P17_BASE_JOINER`) comply with `>= 3.0 mm` except the single documented SG90 M2 ear screw exception:

| Hole Diameter | Unique Count (`holes_table.csv`) | Physical Count (`19` pcs) | Assigned Purpose & Panels |
|---:|---:|---:|---|
| **`Ø2.5 mm`** | `2` | `2` | **ONLY `< 3.0 mm` exception:** TowerPro SG90 M2 mounting ear screws on `P07_SERVO_SHELF` (`27.8 mm` pitch; `1.00 mm` flange web — **use M2 washers**). |
| **`Ø3.0 mm`** | `24` | `24` | `19×` speaker grille (`P15_TECH_FASCIA`), `3×` door hinges & servo linkage (`P08_DOOR_LEAF`), `2×` PAM8403 tie/clamp holes (`P01A_BASE_TECH`). |
| **`Ø3.4 mm`** | `24` | `28` | `4×` Hub PCB `90×70 mm` M3 (`P16`), `4×` plate corners (`P16`) + `4×` matching base holes (`P01A`), `8×` base seam joiner holes (`P01A`+`P01B`) + `4×2` joiner plates (`2× P17`). |
| **`Ø3.5 mm`** | `14` | `14` | `4×` Relay 1 + `4×` Relay 2 (`P01A`), `1×` DHT11 (`P02`), `1×` KY-037 (`P05`), `1×` LM393 (`P12`), `1×` 3 mm Power LED + `2×` speaker M3 clamps (`P15`). |
| **`Ø5.5 mm`** | `2` | `2` | `2×` 5 mm LEDs (`LED_Living_5mm` D0 & `LED_Bedroom_5mm` D4 on `P02_WALL_BACK`). |
| **`Ø10.0 mm`** | `1` | `1` | Silicone pump tube pass-through (`OD 8.0 mm` tube through `P10_WATER_DIVIDER`). |
| **`Ø10.5 mm`** | `1` | `1` | KY-037/038 electret microphone acoustic aperture (`P05_WALL_FRONT`). |
| **`Ø12.5 mm`** | `2` | `2` | Active 5V Buzzer TMB12A05 (`P05_WALL_FRONT`) & DC-022 M12 panel-mount barrel jack (`P15_TECH_FASCIA`). |
| **`Ø14.0 mm`** | `6` | `6` | Generous Dupont bundle pass-throughs (`2×` `P02`, `1×` `P03`, `2×` `P05`, `1×` `P06`). |
| **Total** | **`76`** | **`80`** | Exact 1:1 match verified against DXF circles (`<= 0.001 mm`). |

## 4. Hardware Module Mounting Map (100×80 Hub PCB + 14 Off-Board Modules + 3mm Power LED)

| Module | ESP8266 Pin / Hub Port | Room / Zone | Mounted On | Fasteners / Clearance Fit | Datasheet Dimensions | Datasheet Source |
|---|---|---|---|---|---|---|
| **Smart Home Central Hub PCB (Redesigned 100x80)** | `J1`–`J15`, `U1/U2` | Technical Bay | `P16_PCB_PLATE` | 4x M3x10 brass standoffs on P16_PCB_PLATE (90x70 mm pattern, Dia 3.4 mm) | 100.0 x 80.0 x 1.6 mm; 4x M3 (3.2 mm) holes at 5 mm corner inset -> 90.0 x 70.0 mm | [Project Fixed Spec (Hub PCB Redesign 100x80)](../../../hardware/kicad/smarthome_hub/smarthome_hub.kicad_pcb) |
| **ESP8266 NodeMCU v2 Amica (CP2102)** | `D0`–`D8`, `A0` | Technical Bay | `P16_PCB_PLATE (plugged into Hub PCB U1/U2 sockets)` | 2x 1x15 female pin sockets on Hub PCB (22.86 mm row spacing); Micro-USB faces open cutaway | 48.26 x 25.40 x 1.60 mm PCB (49.4 mm w/ Micro-USB), 22.86 mm row spacing | [Components101 NodeMCU ESP8266 Datasheet](https://components101.com/development-boards/nodemcu-esp8266-pinout-features-and-datasheet) |
| **5V 1-Channel Relay Module #1 (Blue SRD-05VDC, Pump D6)** | `D6 (GPIO12)` · `J7/J8` | Technical Bay | `P01A_BASE_TECH` | 4x M3x8 nylon standoffs + M3 screws/nuts (Dia 3.5 mm holes at 44.5 x 20.5 mm) | 50.0 x 26.0 x 18.5 mm; 4x M3 (3.1 mm) holes at 44.5 x 20.5 mm | [Reichelt / HandsOnTech 1-Ch SRD-05VDC Relay Spec](https://www.reichelt.com/de/en/shop/product/developer_boards_-_relay_1_channel_srd-05vdc-sl-c-371953) |
| **5V 1-Channel Relay Module #2 (Red Opto, PAM8403 Power D7)** | `D7 (GPIO13)` · `J9/J10` (`Jmp=H`) | Technical Bay | `P01A_BASE_TECH` | 4x M3x8 nylon standoffs + M3 screws/nuts (Dia 3.5 mm holes at 44.5 x 20.5 mm) | 50.0 x 26.0 x 18.5 mm; 4x M3 (3.1 mm) holes at 44.5 x 20.5 mm | [Electrokit SRD-05VDC Opto Relay Spec](https://www.electrokit.com/en/rela-srd-1-pol-vaxlande-5v) |
| **PAM8403 3W Class-D Audio Amplifier Module (PWM D3)** | `D3 (GPIO0)` · `J11/J12` | Technical Bay | `P01A_BASE_TECH` | 2x Dia 3.0 mm nylon tie/clamp holes (26.0 mm span) + double-sided foam pad | 21.0 x 18.0 x 3.4 mm (bare stamp PCB, no internal screw holes) | [Elecrow PAM8403 Datasheet](https://www.elecrow.com/download/PAM8403-datasheet.pdf) |
| **Mini Round Speaker 8 Ohm 0.5 W (Dia 28 mm, PUI AS02808MR-R)** | `PAM8403 L_OUT+/-` (BTL) | Technical Bay (Front Fascia) | `P15_TECH_FASCIA` | 2x M3x10 screws + wide nylon washers (Dia 3.5 mm holes, 36.0 mm span) behind 19-hole grille | Dia 28.0 mm x 5.2 mm slim round metal-frame micro speaker (8 Ohm 0.5 W) | [PUI Audio AS02808MR-R Datasheet](https://puiaudio.com/file/specs-AS02808MR-R.pdf) |
| **DC-022 5V 2A Panel-Mount Barrel Power Jack (5.5x2.1 mm)** | `+5V / GND` · `J1` | Technical Bay (Front Fascia) | `P15_TECH_FASCIA` | M12 threaded barrel + hex nut through Dia 12.5 mm hole (fits 2/3/5 mm panels) | M12x1.0 panel cutout Dia 12.0 mm, flange Dia 14.0 mm, rear body length 21.0 mm (5.5x2.1 mm center-positive) | [Adafruit Product 610 / DC-022 Panel Mount 2.1mm DC Barrel Jack](https://www.adafruit.com/product/610) |
| **Power Indicator 3mm LED (Kingbright WP710A10)** | `+5V` via `1kΩ` | Technical Bay (Front Fascia) | `P15_TECH_FASCIA` | Dia 3.5 mm hole + 3mm LED bezel/clip | Standard T-1 (3.0 mm lens, 3.8 mm flange, 5.3 mm height) | [Kingbright WP710A10 Datasheet](http://www.kingbrightusa.com/webimages/catalog/2012-2013%20KC%20eCatalog.pdf) |
| **TowerPro SG90 9g Micro Servo (Main Door D1)** | `D1 (GPIO5)` · `J3` | Living Room (Door Jamb) | `P07_SERVO_SHELF` | 2x M2x10 screws + M2 nuts + M2 washers (Dia 2.5 mm holes, 27.8 mm pitch — only <3mm exception) | Body 22.8 x 12.2 x 22.5 mm; tab span 32.2 mm; M2 holes 27.8 mm apart | [HandsOnTech TowerPro SG90 Datasheet](https://www.handsontec.com/dataspecs/SG90-Servo.pdf) |
| **5V Active Electromagnetic Buzzer (TMB12A05, D8)** | `D8 (GPIO15)` · `J6` | Center Pillar (Front) | `P05_WALL_FRONT` | Dia 12.5 mm clearance hole + silicone/hot-glue bead on rear | Dia 12.0 mm x 9.5 mm body, 7.6 mm pin pitch | [Osoyoo TMB12A05 Buzzer Datasheet](https://osoyoo.com/2017/05/05/buzzer-5v-breadboard-friendlytmb12a05/) |
| **Living Room 5mm LED (Kingbright WP7113, D0)** | `D0 (GPIO16)` · `J4` | Living Room | `P02_WALL_BACK` | Dia 5.5 mm hole + 5mm LED panel bezel | Standard T-1 3/4 (5.0 mm dome, 5.8 mm flange, 8.6 mm height) | [Kingbright WP7113 Datasheet](https://www.kingbrightusa.com/images/catalog/spec/wp7113id.pdf) |
| **Bedroom 5mm LED (Kingbright WP7113, D4)** | `D4 (GPIO2)` · `J5` (Active-LOW) | Bedroom | `P02_WALL_BACK` | Dia 5.5 mm hole + 5mm LED panel bezel | Standard T-1 3/4 (5.0 mm dome, 5.8 mm flange, 8.6 mm height) | [Kingbright WP7113 Datasheet](https://www.kingbrightusa.com/images/catalog/spec/wp7113id.pdf) |
| **DHT11 Temperature & Humidity 3-Pin Breakout Module (D2)** | `D2 (GPIO4)` · `J13` (`3.3V`) | Living Room | `P02_WALL_BACK` | 1x M3x8 nylon standoff + screw (Dia 3.5 mm) above 12.5 x 16.0 mm airflow vent | Breakout PCB 28.0 x 14.0 x 1.6 mm; Aosong sensor 15.5 x 12.0 x 5.5 mm | [Aosong / DFRobot DHT11 Datasheet](https://image.dfrobot.com/image/data/KIT0003/DHT11%20datasheet.pdf) |
| **KY-037 / KY-038 Sound Sensor Module (D5)** | `D5 (GPIO14)` · `J15` (`3.3V`, `DO`) | Living Room (Front Ledge) | `P05_WALL_FRONT` | 1x M3x8 nylon standoff + screw (Dia 3.5 mm); Dia 9.7 mm mic behind Dia 10.5 mm aperture | PCB 35.0 x 15.0 x 1.6 mm (H 13.1 mm w/ 3296W pot); mic Dia 9.7x6.7 mm; M3 hole | [Joy-IT KY-038 / KY-037 Datasheet](https://sensorkit.joy-it.net/en/sensors/ky-038) |
| **YL-69 / FC-28 Soil Moisture 2-Prong Probe (A0)** | Via `LM393` (`A0`) | Garden Planter | `P14_SOIL_BRIDGE` | Inserted vertically through 22.0 x 3.5 mm slot in P14_SOIL_BRIDGE | Fork PCB 60.0 x 20.0 x 1.6 mm (2-prong resistive probe) | [HandsOnTech Soil Moisture Sensor Spec](https://handsontec.com/dataspecs/sensor/Soil%20Moisture%20Sensor.pdf) |
| **LM393 Soil Comparator Board (YL-38, A0)** | `A0 (ADC0)` · `J14` (`3.3V`, `AO`) | Garden Planter (Dry Exterior) | `P12_GARDEN_FRONT` | 1x M3x8 nylon standoff + screw (Dia 3.5 mm) on dry exterior of planter front wall | PCB 32.0 x 14.0 x 1.6 mm (H 12.0 mm w/ 3296W pot); 1x M3 mounting hole | [HandsOnTech Soil Moisture Sensor Spec](https://handsontec.com/dataspecs/sensor/Soil%20Moisture%20Sensor.pdf) |
| **3-6V DC Mini Submersible Water Pump + 6/8mm Silicone Tube** | `J2` (via Relay 1 `D6`) | Water Reservoir | `P01A_BASE_TECH / P10_WATER_DIVIDER` | Horizontal free-standing inside sealed water tank; OD 8.0 mm tube through Dia 10.0 mm hole | Horizontal cylinder 45.0 (L) x 24.0 (Dia) x 33.0 (H) mm; nozzle OD 7.5 mm; tube OD 8.0 mm | [Soldered / Mouser Mini Water Pump Datasheet](https://www.mouser.lt/datasheet/2/1398/Soldered_101844_mini_water_pump-3532437.pdf) |

## 5. Automated Verification Summary

- **Overall Result:** `ALL_PASS` (`9/9` checks passed, see [`verification_report.json`](verification_report.json))
- `dxf_closed_contours`: `PASS`
- `min_hole_and_datasheet_clearance`: `PASS`
- `min_web_and_non_overlap`: `PASS`
- `tab_slot_matching_and_min_tab`: `PASS`
- `freecad_recompute_and_3d_collision`: `PASS`
- `pcb_plate_fit_90x70`: `PASS`
- `modules_fit_rooms_and_15mm_wiring_gaps`: `PASS`
- `sheet_nesting_a3_and_a4`: `PASS`
- `holes_csv_consistency`: `PASS`

See detailed Vietnamese step-by-step build & hand-cutting guide in [`ASSEMBLY_GUIDE.md`](ASSEMBLY_GUIDE.md) and exploded view in [`assembly_exploded.pdf`](assembly_exploded.pdf) / [`assembly_exploded.png`](assembly_exploded.png).
