# Smart Home Open-Cutaway Acrylic (Mica) House — Panel Schedule & Assembly Guide

- **FreeCAD Parametric Source:** `hardware/freecad/mica/smarthome_mica_house.FCStd` (built via `hardware/freecad/mica/build_mica.py`)
- **Default Material:** Clear Cast Acrylic (Mica), thickness **`T = 3.0 mm`** (parametric Spreadsheet `Params.T_mm` verified for `2.0`, `3.0`, and `5.0 mm`)
- **Joint Type:** Interlocking tab-and-slot (finger) joints with **`slot_width = T + 0.15 mm`** laser kerf / slip clearance
- **House Outer Footprint:** `356.0 x 178.0 x 135.0 mm` (exact match to Blender `SCENE_SPEC.json`) on a `380.0 x 286.0 mm` base plate
- **Hardware Scope:** Locked 6 devices + 3 sensors on ESP8266 NodeMCU v2 Amica + `80 x 65 mm` KiCad Central Hub PCB (**zero fan, zero AC, zero IR**)

## 1. Panel Cutting Schedule (15 Panels)

| Panel ID | Name | Qty | Size L x W (mm) | Thickness | Holes / Cutouts | DXF / Drawing | Notes |
|---|---|---:|---:|---:|---:|---|---|
| `P01_BASE` | Main Base Plate | 1 | `380.0 x 286.0` | `3.0 mm` | 47 (14H / 33R) | [DXF](panels_dxf/P01_BASE.dxf) / [PDF](drawings/P01_BASE.pdf) | Houses Living Room, Bedroom, Tech Bay (KiCad PCB H1..H4, 2x Relays, PAM8403), Water Tank & Garden Planter. |
| `P02_WALL_BACK` | Rear Wall (Living + Bedroom) | 1 | `356.0 x 135.0` | `3.0 mm` | 10 (5H / 5R) | [DXF](panels_dxf/P02_WALL_BACK.dxf) / [PDF](drawings/P02_WALL_BACK.pdf) | Full-height rear wall with Bedroom panoramic window, Living/Bedroom 5mm LED holes, DHT11 airflow vent + M3 hole, cable holes. |
| `P03_WALL_LEFT` | Left Cutaway Side Wall | 1 | `178.0 x 135.0` | `3.0 mm` | 1 (1H / 0R) | [DXF](panels_dxf/P03_WALL_LEFT.dxf) / [PDF](drawings/P03_WALL_LEFT.pdf) | Open-cutaway side wall: full height 132mm rear, low 28mm cutaway front. |
| `P04_WALL_RIGHT` | Right Cutaway Side Wall | 1 | `178.0 x 135.0` | `3.0 mm` | 0 (0H / 0R) | [DXF](panels_dxf/P04_WALL_RIGHT.dxf) / [PDF](drawings/P04_WALL_RIGHT.pdf) | Open-cutaway side wall: full height 132mm rear, low 28mm cutaway front. |
| `P05_WALL_FRONT` | Front Cutaway Facade & Door Portal | 1 | `356.0 x 135.0` | `3.0 mm` | 8 (5H / 3R) | [DXF](panels_dxf/P05_WALL_FRONT.dxf) / [PDF](drawings/P05_WALL_FRONT.pdf) | Open-cutaway front facade with 54x96mm Main Door portal, SG90 shelf slot, KY-037 mic aperture+M3, 12mm Buzzer pillar, cable holes. |
| `P06_WALL_MID` | Center Dividing Wall (Living/Bedroom) | 1 | `178.0 x 135.0` | `3.0 mm` | 1 (1H / 0R) | [DXF](panels_dxf/P06_WALL_MID.dxf) / [PDF](drawings/P06_WALL_MID.pdf) | Divides Living Room and Bedroom with 48x96mm doorway passage and Dia 10mm inter-room cable pass-through. |
| `P07_SERVO_SHELF` | SG90 Door Servo Mount Shelf | 1 | `28.0 x 43.0` | `3.0 mm` | 3 (2H / 1R) | [DXF](panels_dxf/P07_SERVO_SHELF.dxf) / [PDF](drawings/P07_SERVO_SHELF.pdf) | Slots into P05 left door jamb inside Living Room; holds TowerPro SG90 vertically so horn swings door around Z axis. |
| `P08_DOOR_LEAF` | Main Door Leaf | 1 | `51.0 x 93.0` | `3.0 mm` | 4 (3H / 1R) | [DXF](panels_dxf/P08_DOOR_LEAF.dxf) / [PDF](drawings/P08_DOOR_LEAF.pdf) | Fits 54x96mm opening with 1.5mm clearance; includes decorative window, M2 hinge holes & SG90 linkage hole. |
| `P09_GARDEN_LEFT` | Water Tank Left Wall | 1 | `74.0 x 47.0` | `3.0 mm` | 0 (0H / 0R) | [DXF](panels_dxf/P09_GARDEN_LEFT.dxf) / [PDF](drawings/P09_GARDEN_LEFT.pdf) | Water reservoir left wall with 8x7mm top pump cable notch; seal inner seams with silicone. |
| `P10_WATER_DIVIDER` | Water-to-Garden Divider Wall | 1 | `74.0 x 47.0` | `3.0 mm` | 1 (1H / 0R) | [DXF](panels_dxf/P10_WATER_DIVIDER.dxf) / [PDF](drawings/P10_WATER_DIVIDER.pdf) | Separates water tank (left) from garden soil planter (right) with Dia 9.5mm silicone water tube pass-through. |
| `P11_GARDEN_RIGHT` | Garden Planter Right Wall | 1 | `74.0 x 43.0` | `3.0 mm` | 0 (0H / 0R) | [DXF](panels_dxf/P11_GARDEN_RIGHT.dxf) / [PDF](drawings/P11_GARDEN_RIGHT.pdf) | Outer right wall of garden soil planter box. |
| `P12_GARDEN_FRONT` | Water & Garden Front Wall | 1 | `134.0 x 47.0` | `3.0 mm` | 2 (1H / 1R) | [DXF](panels_dxf/P12_GARDEN_FRONT.dxf) / [PDF](drawings/P12_GARDEN_FRONT.pdf) | Encloses Water Reservoir + Garden Planter front; mounts dry LM393 board on exterior (M3). |
| `P13_GARDEN_BACK` | Water & Garden Rear Wall | 1 | `134.0 x 47.0` | `3.0 mm` | 1 (0H / 1R) | [DXF](panels_dxf/P13_GARDEN_BACK.dxf) / [PDF](drawings/P13_GARDEN_BACK.pdf) | Encloses Water Reservoir + Garden Planter rear (8mm dry air gap from bedroom wall). |
| `P14_SOIL_BRIDGE` | Garden Soil Probe Holder Bridge | 1 | `24.0 x 74.0` | `3.0 mm` | 1 (0H / 1R) | [DXF](panels_dxf/P14_SOIL_BRIDGE.dxf) / [PDF](drawings/P14_SOIL_BRIDGE.pdf) | Slots across top of Garden Planter to hold YL-69 2-prong soil probe vertically in soil (22.0x3.2mm slot). |
| `P15_TECH_FASCIA` | Tech Bay Power & Speaker Fascia | 1 | `210.0 x 45.0` | `3.0 mm` | 23 (22H / 1R) | [DXF](panels_dxf/P15_TECH_FASCIA.dxf) / [PDF](drawings/P15_TECH_FASCIA.pdf) | Front technical fascia: 12x10mm 5V power opening, 3mm power LED, open USB cutout, and 19-hole Dia 28mm speaker grille. |

## 2. Material Area & Sheet Nesting Summary

- **Total Panel Count:** `15` unique panels (`15` pieces total)
- **Total Net Acrylic Area:** `2451.5 cm²` (`0.2452 m²`)
- **Total Bounding-Box Area:** `3168.0 cm²` (`0.3168 m²`)
- **Standard A3 Sheets (`420 x 297 mm`, 5 mm margin, 4 mm kerf spacing):** **`3` sheets** — see `sheet_layout_A3.dxf` & `sheet_layout_A3.png`:
  - **A3 Sheet #1** (Net utilization `87.2%`): `P01_BASE`, `P14_SOIL_BRIDGE`
  - **A3 Sheet #2** (Net utilization `48.4%`): `P02_WALL_BACK`, `P05_WALL_FRONT`, `P15_TECH_FASCIA`, `P07_SERVO_SHELF`
  - **A3 Sheet #3** (Net utilization `61.0%`): `P03_WALL_LEFT`, `P04_WALL_RIGHT`, `P06_WALL_MID`, `P12_GARDEN_FRONT`, `P13_GARDEN_BACK`, `P08_DOOR_LEAF`, `P09_GARDEN_LEFT`, `P10_WATER_DIVIDER`, `P11_GARDEN_RIGHT`
- **Standard A4 Sheets (`297 x 210 mm`, partial layout for smaller panels):** **`3` A4 sheets** hold the 12 smaller panels (`sheet_layout_A4.dxf` & `sheet_layout_A4.png`); oversized panels requiring A3 (`420 x 297 mm`): `P01_BASE`, `P02_WALL_BACK`, `P05_WALL_FRONT`.

## 3. Step-by-Step Assembly Order

See exploded diagram: `assembly_exploded.pdf` / `assembly_exploded.png`.

1. **Prepare `P01_BASE` (Base Plate):** Peel protective film from acrylic. Install 4× `M3×10 mm` brass standoffs in `PCB_H1..H4` (`71.0 × 56.0 mm` exact KiCad pattern), 8× `M3×8 mm` nylon standoffs for Relay 1 & Relay 2 (`44.5 × 20.5 mm` each), and stick a double-sided foam pad between the 2× `M2.5` PAM8403 tie-down holes.
2. **Pre-mount Rear Wall Modules on `P02_WALL_BACK`:** Press-fit the Living Room (`Ø5.2 mm`) and Bedroom (`Ø5.2 mm`) 5 mm LEDs, and bolt the DHT11 breakout board (`1× M3×8 mm` nylon standoff) aligned over the `12 × 14 mm` airflow vent. Slot `P02_WALL_BACK` bottom tabs into `P01_BASE`.
3. **Lock Center Dividing Wall (`P06_WALL_MID`):** Engage the 3 rear tabs of `P06_WALL_MID` into the vertical slots of `P02_WALL_BACK` while seating its 2 bottom tabs into `P01_BASE`.
4. **Attach Left & Right Cutaway Walls (`P03_WALL_LEFT`, `P04_WALL_RIGHT`):** Interlock their 3 rear finger tabs into the side notches of `P02_WALL_BACK` and drop their bottom tabs into `P01_BASE`.
5. **Sub-assemble Front Facade (`P05_WALL_FRONT`) & Servo Shelf (`P07_SERVO_SHELF`):**
   - Mount the SG90 servo body downward through the `23.0 × 12.4 mm` cutout in `P07_SERVO_SHELF` and fasten with 2× `M2×8 mm` screws, washers, and nuts (`27.8 mm` pitch).
   - Mount the KY-037 sound sensor (`1× M3×8 mm` nylon standoff, mic aligned with `Ø10.5 mm` hole) and press-fit the 12 mm active buzzer (`Ø12.2 mm` hole at `Z=114 mm`) on `P05_WALL_FRONT`.
   - Slot `P07_SERVO_SHELF` rear tab into `P05_WALL_FRONT` (inside Living Room), then lock `P05_WALL_FRONT` onto `P03_WALL_LEFT`, `P04_WALL_RIGHT`, `P06_WALL_MID`, and `P01_BASE`.
6. **Hang Main Door (`P08_DOOR_LEAF`):** Mount two mini hobby hinges (or nylon hinge pins) at the `M2` door holes (`4.5 mm` inset) to the left jamb of `P05_WALL_FRONT`. Link the SG90 white servo horn to the door linkage hole (`Ø2.2 mm`) using a short stiff wire push-rod (`Ø1 mm`).
7. **Assemble Water Tank & Garden Planter (`P09`–`P14`):**
   - Interlock `P09_GARDEN_LEFT`, `P10_WATER_DIVIDER`, `P11_GARDEN_RIGHT`, `P12_GARDEN_FRONT`, and `P13_GARDEN_BACK` into `P01_BASE`.
   - **Waterproofing:** Seal all interior seams of the left water reservoir (`P01`/`P09`/`P10`/`P12`/`P13`) with clear neutral-cure silicone or acrylic solvent cement and leak-test for 15 minutes before placing electronics.
   - Place the horizontal `3–6 V` submersible pump inside the water reservoir, route its 2-wire cable through the top notch of `P09_GARDEN_LEFT`, and push the `6/8 mm` silicone tube through the `Ø9.5 mm` hole of `P10_WATER_DIVIDER` into the soil chamber.
   - Mount the LM393 comparator board on the **dry exterior** of `P12_GARDEN_FRONT` (`1× M3×8 mm` nylon standoff). Slot `P14_SOIL_BRIDGE` across the top notches of `P12`/`P13` and insert the YL-69 fork probe through the `22.0 × 3.2 mm` slot.
8. **Mount Front Tech Fascia (`P15_TECH_FASCIA`) & Final Wiring:** Clamp the `Ø28 mm` mini speaker behind the 19-hole grille using 2× `M3×10 mm` screws + wide nylon washers, press-fit the 3 mm green Power LED, and slot `P15_TECH_FASCIA` into `P01_BASE`. Mount the KiCad Hub PCB (`80 × 65 mm`), plug in NodeMCU v2 Amica, mount Relays 1 & 2 and PAM8403, route cables through the `Ø10 mm` pass-through holes, and connect 5 V power through the `12 × 10 mm` front terminal opening.

## 4. Module Mounting & Fastener Map (with Datasheet Sources)

| Module | Room / Zone | Mounted On | Fasteners / Fit | Physical Dimensions | Datasheet Source |
|---|---|---|---|---|---|
| **Smart Home Central Hub PCB (KiCad)** | Technical Bay | `P01_BASE` | 4x M3x10 brass standoffs + 4x M3x6 screws + 4x M3 nuts | 80.0 x 65.0 x 1.6 mm; H1..H4 M3 (3.2 mm) at 71.0 x 56.0 mm (inset 4.5 mm) | [Repo KiCad PCB (smarthome_hub.kicad_pcb)](hardware/kicad/smarthome_hub/smarthome_hub.kicad_pcb) |
| **ESP8266 NodeMCU v2 Amica (CP2102)** | Technical Bay | `P01_BASE (plugged into PCB U1/U2 sockets)` | 2x 1x15 female pin sockets on Hub PCB (22.86 mm row spacing) | 48.26 x 25.40 x 1.60 mm PCB (49.4 mm w/ Micro-USB), 22.86 mm row spacing | [DIMENSIONS_AUDIT.md + Components101 NodeMCU Datasheet](https://components101.com/development-boards/nodemcu-esp8266-pinout-features-and-datasheet) |
| **5V 1-Channel Relay Module #1 (Blue, Pump)** | Technical Bay | `P01_BASE` | 4x M3x8 nylon standoffs + 4x M3 screws/nuts | 50.0 x 26.0 x 18.5 mm; 4x M3 (3.1 mm) holes at 44.5 x 20.5 mm | [DIMENSIONS_AUDIT.md + Reichelt/HandsOnTech 1-Ch Relay Spec](https://www.reichelt.com/de/en/shop/product/developer_boards_-_relay_1_channel_srd-05vdc-sl-c-371953) |
| **5V 1-Channel Relay Module #2 (Red Opto, Amp)** | Technical Bay | `P01_BASE` | 4x M3x8 nylon standoffs + 4x M3 screws/nuts | 50.0 x 26.0 x 18.5 mm; 4x M3 (3.1 mm) holes at 44.5 x 20.5 mm | [DIMENSIONS_AUDIT.md + Electrokit SRD-05VDC Opto Relay Spec](https://www.electrokit.com/en/rela-srd-1-pol-vaxlande-5v) |
| **PAM8403 3W Class-D Audio Amplifier Module** | Technical Bay | `P01_BASE` | 2x M2.5 nylon tie/clip holes (26 mm span) + double-sided foam pad | 21.0 x 18.0 x 3.4 mm (bare stamp PCB, no internal screw holes) | [DIMENSIONS_AUDIT.md + Elecrow PAM8403 Datasheet](https://www.elecrow.com/download/PAM8403-datasheet.pdf) |
| **Mini Round Speaker 8 Ohm 0.5 W (Dia 28 mm, PUI AS02808MR-R)** | Technical Bay | `P15_TECH_FASCIA` | 2x M3x10 screws + large nylon washers clamping Dia 28mm rim behind grille | Dia 28.0 mm x 5.2 mm slim round metal-frame micro speaker (8 Ohm 0.5 W) | [DIMENSIONS_AUDIT.md + PUI Audio AS02808MR-R Datasheet](https://puiaudio.com/file/specs-AS02808MR-R.pdf) |
| **TowerPro SG90 9g Micro Servo (Main Door)** | Living Room (Door Jamb) | `P07_SERVO_SHELF` | 2x M2x8 screws + M2 nuts + M2 washers (27.8 mm pitch) | Body 22.8 x 12.2 x 22.5 mm; tab span 32.2 mm; M2 holes 27.8 mm apart | [DIMENSIONS_AUDIT.md + HandsOnTech SG90 Datasheet](https://www.handsontec.com/dataspecs/SG90-Servo.pdf) |
| **5V Active Electromagnetic Buzzer (TMB12A05)** | Center Pillar (Front) | `P05_WALL_FRONT` | Dia 12.2 mm press-fit hole + drop of hot glue / silicone on rear | Dia 12.0 mm x 9.5 mm body, 7.6 mm pin pitch | [DIMENSIONS_AUDIT.md + Osoyoo TMB12A05 Datasheet](https://osoyoo.com/2017/05/05/buzzer-5v-breadboard-friendlytmb12a05/) |
| **Living Room 5mm LED (Kingbright WP7113)** | Living Room | `P02_WALL_BACK` | Dia 5.2 mm press-fit / 5mm LED panel bezel | Standard T-1 3/4 (5.0 mm dome, 5.8 mm flange, 8.6 mm height) | [DIMENSIONS_AUDIT.md + Kingbright WP7113 Datasheet](https://www.kingbrightusa.com/images/catalog/spec/wp7113id.pdf) |
| **Bedroom 5mm LED (Kingbright WP7113)** | Bedroom | `P02_WALL_BACK` | Dia 5.2 mm press-fit / 5mm LED panel bezel | Standard T-1 3/4 (5.0 mm dome, 5.8 mm flange, 8.6 mm height) | [DIMENSIONS_AUDIT.md + Kingbright WP7113 Datasheet](https://www.kingbrightusa.com/images/catalog/spec/wp7113id.pdf) |
| **Power Indicator 3mm LED (Kingbright WP710A10)** | Technical Bay (Front Fascia) | `P15_TECH_FASCIA` | Dia 3.2 mm press-fit / 3mm LED clip | Standard T-1 (3.0 mm lens, 3.8 mm flange, 5.3 mm height) | [DIMENSIONS_AUDIT.md + Kingbright WP710A10 Datasheet](http://www.kingbrightusa.com/webimages/catalog/2012-2013%20KC%20eCatalog.pdf) |
| **DHT11 Temperature & Humidity 3-Pin Breakout Module** | Living Room | `P02_WALL_BACK` | 1x M3x8 nylon standoff + screw above 12x14 mm airflow window | Breakout PCB 28.0 x 14.0 x 1.6 mm; Aosong sensor 15.5 x 12.0 x 5.5 mm | [DIMENSIONS_AUDIT.md + Aosong/DFRobot DHT11 Datasheet](https://image.dfrobot.com/image/data/KIT0003/DHT11%20datasheet.pdf) |
| **KY-037 / KY-038 Sound Sensor Module** | Living Room (Front Ledge) | `P05_WALL_FRONT` | 1x M3x8 nylon standoff + screw; Dia 9.7mm mic aligned with Dia 10.5mm aperture | PCB 35.0 x 15.0 x 1.6 mm (H 13.1 mm w/ 3296W pot); mic Dia 9.7x6.7 mm; M3 hole | [DIMENSIONS_AUDIT.md + Joy-IT KY-038 Datasheet](https://sensorkit.joy-it.net/en/sensors/ky-038) |
| **YL-69 / FC-28 Soil Moisture 2-Prong Probe** | Garden Planter | `P14_SOIL_BRIDGE` | Inserted vertically through 22.0 x 3.2 mm slot in soil bridge | Fork PCB 60.0 x 20.0 x 1.6 mm (2-prong resistive probe) | [DIMENSIONS_AUDIT.md + HandsOnTech Soil Moisture Spec](https://handsontec.com/dataspecs/sensor/Soil%20Moisture%20Sensor.pdf) |
| **LM393 Soil Comparator Board (YL-38)** | Garden Planter (Dry Exterior) | `P12_GARDEN_FRONT` | 1x M3x8 nylon standoff + screw on dry exterior of planter front wall | PCB 32.0 x 14.0 x 1.6 mm (H 12.0 mm w/ 3296W pot); 1x M3 mounting hole | [DIMENSIONS_AUDIT.md + HandsOnTech Soil Moisture Spec](https://handsontec.com/dataspecs/sensor/Soil%20Moisture%20Sensor.pdf) |
| **3-6V DC Mini Submersible Water Pump + 6/8mm Tube** | Water Reservoir | `P01_BASE / P10_WATER_DIVIDER` | Horizontal free-standing inside sealed water box; OD 8.0mm tube through Dia 9.5mm hole | Horizontal cylinder 45.0 (L) x 24.0 (Dia) x 33.0 (H) mm; nozzle OD 7.5 mm; tube OD 8.0 mm | [DIMENSIONS_AUDIT.md + Soldered/Mouser Mini Water Pump Datasheet](https://www.mouser.lt/datasheet/2/1398/Soldered_101844_mini_water_pump-3532437.pdf) |

## 5. Suggested Fabrication & Hardware Shopping List (Reference Only)

- **Acrylic (Mica) Sheets:** `3× A3 (420 × 297 mm) × 3.0 mm` clear cast acrylic sheets (or 1 sheet `600 × 900 mm × 3.0 mm` cut down at laser shop — leaves spare material for test cuts).
- **Brass / Nylon Standoffs & Screws:**
  - `4× M3 × 10 mm` brass hex standoffs + `8× M3 × 6 mm` screws (KiCad Hub PCB)
  - `12× M3 × 8 mm` nylon standoffs + `12× M3` screws & nuts (2× Relay modules, DHT11, KY-037, LM393)
  - `2× M3 × 10 mm` screws + wide nylon washers (Dia 28 mm speaker clamp on `P15_TECH_FASCIA`)
  - `2× M2 × 8 mm` screws + `M2` nuts + `M2` washers (SG90 door servo on `P07_SERVO_SHELF`)
  - `4× M2 × 8 mm` screws + 2× mini nylon/acrylic hobby hinges `16 × 13 mm` (Main Door `P08_DOOR_LEAF`)
  - Small zip-ties (`2.5 mm` wide) + 3M double-sided foam tape (PAM8403 amp)
- **Adhesives & Waterproofing:** Acrylic solvent cement (chloroform / Weld-On #3 or #4) for permanent structural joints + clear neutral-cure silicone sealant for the water reservoir seams; 4× adhesive rubber feet (`Ø10 mm`) under `P01_BASE`.
- **Manual Cutting Alternative:** If cutting by hand instead of CO2 laser, print each `drawings/<ID>.pdf` at 100% scale, glue onto the acrylic protective film, score straight cuts with an acrylic hook knife, and drill holes with brad-point / stepped plastic drill bits at low RPM.

## 6. Automated Verification Status

- **Overall Result:** `ALL_PASS`
- `dxf_closed_contours`: `PASS`
- `min_web_and_non_overlap`: `PASS`
- `tab_slot_matching`: `PASS`
- `kicad_pcb_hole_match`: `PASS`
- `freecad_recompute_T_2_3_5`: `PASS`
- `modules_fit_rooms_and_zero_removed`: `PASS`
- `a3_nesting_complete`: `PASS`
