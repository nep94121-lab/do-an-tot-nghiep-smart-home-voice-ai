STATUS: ALL_DONE

# Smart Home Voice AI — KiCad 10 Full-System 3D Assembly Report (`agyhwasm1_20261121`)

## 1. Summary & Goal

**User Goal.** Build a separate, generic, re-runnable KiCad 10 assembly project (`hardware/kicad/smarthome_assembly/`) that displays the merged `100.00 x 80.00 mm` single-layer DIY central hub PCB (with `Q1` S8050 + `R10` 1k buzzer driver) together with NodeMCU ESP8266 v2 Amica and all **14 off-board modules** in datasheet-accurate real-world scale, wired with color-coded 3D Dupont/screw-terminal wires and crisp readable labels, so a single 3D render showcases the complete Smart Home Voice AI hardware system on any hub board size.

**Execution Architecture (`/teamwork`).** Work was divided across four specialist roles inheriting high-effort reasoning, with a completely separate read-only independent reviewer cross-checking every deliverable across three verification rounds:
- **3D Model / CAD Engineer (`cad-3d-engineer`):** Verified all 15 module dimensions against real datasheets and wrote `hardware/kicad/smarthome_assembly/build_3dmodels.py` (FreeCAD 1.1 OpenCASCADE B-Rep) emitting 15 multi-color `.wrl` (VRML 2.0) + 15 `.step` (AP214) models, `modules_manifest.json`, `modules_dimensions.csv`, and `modules_dimensions.md`.
- **KiCad Scripting Engineer (`kicad-script-engineer`):** Built `hardware/kicad/smarthome_assembly/build_assembly.py` (pure Python stdlib + KiCad 10 `pcbnew`), the 17-footprint `smarthome_modules.pretty/` library, `smarthome_assembly.kicad_pro`, `fp-lib-table`, dynamic hub parser, zero-overlap placement engine, pad-exact 3D colored VRML wire harness (`wiring_harness.wrl`), raised 3D label plaques (`assembly_labels.wrl`), 2D overlays, and `README.md`.
- **QA / Render Engineer (`qa-render-engineer`):** Validated `build_assembly.py` on both the current `80 x 65 mm` hub board and an isolated temporary `100 x 80 mm` placeholder hub board (4x M3 Ø3.2 mm mounting holes at 5 mm inset), exported all four high-resolution raytraced `kicad-cli pcb render` PNGs (`96..99`), and visually verified every frame.
- **Independent Reviewer (`independent-reviewer`, separate from all authors):** Audited raw `.wrl` vertices and signed mesh volumes (214 shapes across 17 files), FreeCAD `.step` B-Rep bounds, firmware/KiCad pin-map alignment, 3D wire clearances, clean-checkout regeneration from scratch on both board sizes, and all four screenshots (`96..99`). Caught 1 MAJOR (inverted wire normals) and 4 MINOR findings in Round 1; verified every fix across Round 2 and Round 3 to **`VERDICT: PASS` (0 CRITICAL, 0 MAJOR, 0 MINOR)**.

**Safety & Scope Compliance.**
- `hardware/kicad/smarthome_hub/` is **100% unmodified** (`git status` / `git diff` empty).
- **Zero fan, zero AC (220 V), zero IR (`VS1838B` / 940 nm LED)** anywhere in models, footprints, wiring, or docs.
- Branch-only run on `hwasm-20261121` (branched from `master` `131bdc2`); no merge to `master`, no deploy, no secrets/tokens/WAVs touched.

---

## 2. Module Dimensions Table (All 15 Modules — Datasheet vs Measured 3D CAD)

All 15 models live in `hardware/kicad/smarthome_assembly/3dmodels/` as both multi-color VRML 2.0 (`.wrl`, `1 unit = 2.54 mm`) and OpenCASCADE B-Rep STEP (`.step`, `1 unit = 1.00 mm`). Machine-readable tables are stored in `3dmodels/modules_dimensions.csv`, `3dmodels/modules_dimensions.md`, and `3dmodels/modules_manifest.json`.

| # | Module ID | Component | Datasheet Body `L × W × H` (mm) | Measured `.wrl` / `.step` Full (mm) | Max Body Err (mm) | Key Features & Seating | Verified Datasheet Source |
|---:|---|---|---:|---:|---:|---|---|
| 0 | `nodemcu_v2_amica` | NodeMCU ESP8266 v2 Amica (CP2102) | `25.40 × 49.43 × 7.14` *(PCB 48.26×25.40×1.60)* | `25.40 × 49.43 × 13.14` *(incl. 6 mm pins)* | `0.000` | 2×15 header P2.54 mm, row spacing 22.86 mm; ESP-12E shield 16×12×3 mm; antenna top, Micro-USB bottom; seated at `Z = +8.5 mm` on `U1`/`U2` | [Amica NodeMCU ESP8266 DevKit v1.0 (Components101)](https://components101.com/development-boards/nodemcu-esp8266-pinout-features-and-datasheet) |
| 1 | `sg90_servo` | TowerPro SG90 Micro Servo | `32.20 × 12.20 × 31.00` *(body 22.8×12.2×22.5)* | `32.20 × 12.20 × 31.00` | `0.000` | Translucent blue body, mounting tabs 32.2 mm at Z=15.9 mm w/ 2× Ø2.0 mm holes, gear boss 26.7 mm, white horn to 31.0 mm, 3-pin pigtail | [TowerPro SG90 9g Micro Servo Datasheet](https://www.handsontec.com/dataspecs/SG90-Servo.pdf) |
| 2 | `led_5mm_living` | 5 mm LED Living Room (Warm Amber) | `5.80 × 5.80 × 8.60` | `5.55 × 5.80 × 8.60` | `0.251` *(cathode flat)* | Kingbright WP7113 T-1 3/4: Ø5.0 mm dome, Ø5.8×1.0 mm flange with authentic cathode flat, H=8.60 mm, 2.54 mm lead pitch | [Kingbright WP7113 T-1 3/4 5mm LED Datasheet](https://www.kingbrightusa.com/images/catalog/spec/wp7113id.pdf) |
| 3 | `led_5mm_bedroom` | 5 mm LED Bedroom (Bright Red) | `5.80 × 5.80 × 8.60` | `5.55 × 5.80 × 8.60` | `0.251` *(cathode flat)* | Kingbright WP7113ID T-1 3/4: Ø5.0 mm dome, Ø5.8×1.0 mm flange with cathode flat, H=8.60 mm, 2.54 mm lead pitch | [Kingbright WP7113ID T-1 3/4 5mm LED Datasheet](https://www.kingbrightusa.com/images/catalog/spec/wp7113id.pdf) |
| 4 | `relay1_blue_srd05` | Relay 1 Blue 1-Channel 5 V Module (Pump) | `50.00 × 26.00 × 18.50` | `50.00 × 26.00 × 18.50` | `0.000` | Blue PCB 50×26×1.6 mm w/ 4× Ø3.1 mm holes (`44.5×20.5 mm` pitch, reconciled with Mica `P01A_BASE_TECH`), Songle SRD-05VDC-SL-C 19×15.5×15.5 mm, 3-pos 5.08 mm screw terminal, 1×3 2.54 mm header | [1-Ch 5V Relay Module SRD-05VDC-SL-C (Reichelt)](https://www.reichelt.com/de/en/shop/product/developer_boards_-_relay_1_channel_srd-05vdc-sl-c-371953) |
| 5 | `relay2_red_opto` | Relay 2 Red Opto-Isolated 1-Channel 5 V Module | `50.00 × 26.00 × 18.50` | `50.00 × 26.00 × 18.50` | `0.000` | Red PCB 50×26×1.6 mm w/ 4× Ø3.1 mm holes (`44.5×20.5 mm` pitch, reconciled with Mica `P01A_BASE_TECH`), Songle SRD-05VDC-SL-C, PC817 optocoupler, yellow H/L jumper on `H`, 3-pos 5.08 mm terminal, 1×3 header | [Songle SRD-05VDC-SL-C + PC817 Opto Relay (Electrokit)](https://www.electrokit.com/en/rela-srd-1-pol-vaxlande-5v) |
| 6 | `submersible_pump` | 3–6 V Mini Submersible Pump + Silicone Tube | `45.00 × 24.00 × 33.00` | `45.00 × 24.00 × 41.87` *(incl. Ø8 mm tube)* | `0.007` | White horizontal cylinder Ø24×45 mm, top outlet nozzle Ø7.5 mm OD to Z=33 mm, intake grille, recessed matte-black rear epoxy seal, Ø8 mm OD silicone tube | [Soldered 101844 Mini Water Pump Datasheet (Mouser)](https://www.mouser.lt/datasheet/2/1398/Soldered_101844_mini_water_pump-3532437.pdf) |
| 7 | `buzzer_tmb12a05` | TMB12A05 5 V Active Buzzer | `12.00 × 12.00 × 9.50` | `12.00 × 12.00 × 9.50` | `0.004` | Black cylinder Ø12.0×9.5 mm, top sound port Ø3.0 mm, white `+` polarity mark, 7.6 mm through-hole pin pitch | [TMB12A05 5V Active Buzzer Spec (Osoyoo)](https://osoyoo.com/2017/05/05/buzzer-5v-breadboard-friendlytmb12a05/) |
| 8 | `pam8403_amp` | PAM8403 Mini Audio Amplifier Module | `21.00 × 18.00 × 3.10` | `21.00 × 18.00 × 3.10` | `0.000` | Bare green PCB 21×18×1.6 mm, SOP-16 PAM8403 IC 9.9×3.9×1.5 mm (1.27 mm pitch), SMD passives, 2.54 mm power/audio/BTL pads | [Diodes Inc. PAM8403 Datasheet (Elecrow)](https://www.elecrow.com/download/PAM8403-datasheet.pdf) |
| 9 | `speaker_28mm` | 28 mm 8 Ω 0.5 W Mini Speaker | `28.00 × 28.00 × 5.20` | `28.00 × 28.00 × 5.20` | `0.009` | Silver metal basket Ø28.0×5.2 mm, black Mylar cone + silver dust cap, Ø14 mm rear magnet boss, 2 rim solder pads (`+` / `-`) | [PUI Audio AS02808MR-R Datasheet](https://puiaudio.com/file/specs-AS02808MR-R.pdf) |
| 10 | `dht11_module` | DHT11 3-Pin Breakout Module | `28.00 × 14.00 × 7.10` | `28.00 × 14.00 × 7.10` | `0.000` | Blue PCB 28×14×1.6 mm w/ Ø3.0 mm hole, light-blue ventilated DHT11 grid body 15.5×12.0×5.5 mm, 1×3 2.54 mm header | [Aosong DHT11 Datasheet (DFRobot)](https://image.dfrobot.com/image/data/KIT0003/DHT11%20datasheet.pdf) |
| 11 | `soil_lm393_board` | LM393 Soil Moisture Comparator Board | `32.00 × 14.00 × 12.10` | `32.00 × 14.00 × 12.10` | `0.000` | Blue PCB 32×14×1.6 mm w/ Ø3.0 mm hole, blue 3296W trimmer pot (H=12.1 mm), SOIC-8 LM393, 1×4 hub header + 1×2 probe header | [Soil Moisture Sensor LM393 + YL-69 Datasheet (HandsOnTech)](https://handsontec.com/dataspecs/sensor/Soil%20Moisture%20Sensor.pdf) |
| 12 | `yl69_soil_probe` | YL-69 Soil Moisture Fork Probe | `60.00 × 20.00 × 1.60` | `60.00 × 20.00 × 1.60` | `0.000` | Fork FR4 PCB 60×20×1.6 mm with 7.0 mm slot between two 6.5 mm gold-tinned sensing prongs and 1×2 2.54 mm handle header | [Soil Moisture Sensor LM393 + YL-69 Datasheet (HandsOnTech)](https://handsontec.com/dataspecs/sensor/Soil%20Moisture%20Sensor.pdf) |
| 13 | `ky037_sound` | KY-037 / KY-038 Sound Sensor Module | `35.00 × 15.00 × 13.10` | `35.00 × 15.00 × 13.10` | `0.000` | Red PCB 31.5×15×1.6 mm (35 mm w/ front mic), silver ECM-9767 mic Ø9.7×6.7 mm w/ black felt, blue 3296W pot (H=13.1 mm), LM393, 1×4 header (`DO/G/+/AO`) | [Joy-IT KY-038 / KY-037 Sound Sensor Docs](https://sensorkit.joy-it.net/en/sensors/ky-038) |
| 14 | `psu_5v2a_dc_jack` | 5 V 2 A DC Jack PSU Input (Adapter + 5.5×2.1 mm Plug/Lead) | `118.00 × 34.00 × 24.00` *(adapter 46×34×24 + DC-005 38×14×13)* | `118.00 × 34.00 × 24.00` | `0.000` | Matte-black 5 V 2 A wall adapter w/ prongs, coiled DC lead + mated 5.5×2.1 mm barrel plug into green/black DC-005 female screw-terminal adapter w/ raised `+`/`-` marks | [Mean Well SGA12U05-P1J Class Adapter Datasheet](https://www.mouser.com/datasheet/2/260/SGA12U-SPEC-1109436.pdf) & Adafruit #368 5.5×2.1 mm Screw Terminal Adapter |

---

## 3. Master Wiring Table (All 40 Physical Wires: 36 Hub-to-Module + 4 Inter-Module)

Synchronized 100% with `hardware/wiring_contract.py`, `hardware/kicad/smarthome_hub/smarthome_hub.kicad_pcb`, and `firmware_esp8266/esp8266_smarthome/esp8266_smarthome.ino` (lines 55–64).

| Wire | Module | Module Pin | Wire Color | Hub Header | Hub Pin | NodeMCU Pin | GPIO | KiCad Net | Wire Type |
|---|---|---|---|---|---|---|---|---|---|
| `W01` | 5V 2A DC Jack PSU | `+5V` | **Red** (`#DC2626`) | `J1 (PWR_5V_IN)` | `1` | `VIN (U1.15)` | `Power (+5V)` | `+5V` | Screw Terminal 22AWG |
| `W02` | 5V 2A DC Jack PSU | `GND` | **Black** (`#18181B`) | `J1 (PWR_5V_IN)` | `2` | `GND` | `Ground` | `GND` | Screw Terminal 22AWG |
| `W03` | SG90 Micro Servo | `PWM (Orange)` | **Orange** (`#EA580C`) | `J3 (SERVO_D1)` | `1` | `D1 (U2.2)` | `GPIO5` | `D1_SERVO` | Dupont 1×3 F-M |
| `W04` | SG90 Micro Servo | `VCC (Red)` | **Red** (`#DC2626`) | `J3 (SERVO_D1)` | `2` | `VIN (U1.15)` | `Power (+5V)` | `+5V` | Dupont 1×3 F-M |
| `W05` | SG90 Micro Servo | `GND (Brown)` | **Black** (`#18181B`) | `J3 (SERVO_D1)` | `3` | `GND` | `Ground` | `GND` | Dupont 1×3 F-M |
| `W06` | 5mm LED (Living Room) | `Anode (+)` | **Yellow** (`#CA8A04`) | `J4 (LED_LR_D0)` | `1` | `D0 (U2.1)` via R1 220Ω | `GPIO16` | `LED_LR_A` | Dupont 1×2 F-F |
| `W07` | 5mm LED (Living Room) | `Cathode (-)` | **Black** (`#18181B`) | `J4 (LED_LR_D0)` | `2` | `GND` | `Ground` | `GND` | Dupont 1×2 F-F |
| `W08` | 5mm LED (Bedroom) | `Anode (+)` | **Purple** (`#9333EA`) | `J5 (LED_BR_D4)` | `1` | `+3V3` via R2 220Ω | `Power (+3V3)` | `LED_BR_A` | Dupont 1×2 F-F |
| `W09` | 5mm LED (Bedroom) | `Cathode (-)` | **White** (`#94A3B8`) | `J5 (LED_BR_D4)` | `2` | `D4 (U2.5)` Active-LOW | `GPIO2` | `D4_LED_BR` | Dupont 1×2 F-F |
| `W10` | Relay 1 (Blue 5V 1-ch) | `VCC` | **Red** (`#DC2626`) | `J7 (RLY1_PUMP_D6)` | `1` | `VIN (U1.15)` | `Power (+5V)` | `+5V` | Dupont 1×3 F-F |
| `W11` | Relay 1 (Blue 5V 1-ch) | `GND` | **Black** (`#18181B`) | `J7 (RLY1_PUMP_D6)` | `2` | `GND` | `Ground` | `GND` | Dupont 1×3 F-F |
| `W12` | Relay 1 (Blue 5V 1-ch) | `IN` | **Green** (`#16A34A`) | `J7 (RLY1_PUMP_D6)` | `3` | `D6 (U2.9)` | `GPIO12` | `D6_RLY1_PUMP` | Dupont 1×3 F-F |
| `W13` | Relay 1 (Blue 5V 1-ch) | `COM (Screw)` | **Red** (`#DC2626`) | `J8 (RLY1_SW)` | `1` | `VIN (U1.15)` | `Power (+5V)` | `+5V` | Dupont F-Pin 22AWG |
| `W14` | Relay 1 (Blue 5V 1-ch) | `NO (Screw)` | **Yellow** (`#CA8A04`) | `J8 (RLY1_SW)` | `2` | `Switched +5V → J2.1` | `Switched +5V` | `PUMP_5V` | Dupont F-Pin 22AWG |
| `W15` | Mini Submersible Pump | `Pump + (Red)` | **Red** (`#DC2626`) | `J2 (PUMP_OUT)` | `1` | `Switched +5V (via RLY1)` | `Switched +5V` | `PUMP_5V` | Screw Terminal 22AWG |
| `W16` | Mini Submersible Pump | `Pump - (Black)` | **Black** (`#18181B`) | `J2 (PUMP_OUT)` | `2` | `GND` | `Ground` | `GND` | Screw Terminal 22AWG |
| `W17` | Active 5V Buzzer (TMB12A05) | `Buzzer (+)` | **Red** (`#DC2626`) | `J6 (BUZZ_D8)` | `1` | `VIN (+5V)` | `Power (+5V)` | `+5V` | Dupont 1×2 F-F |
| `W18` | Active 5V Buzzer (TMB12A05) | `Buzzer (-)` | **Orange** (`#EA580C`) | `J6 (BUZZ_D8)` | `2` | `D8 (U2.11) via Q1 S8050` | `GPIO15 (NPN low-side)` | `BUZZ_K` | Dupont 1×2 F-F |
| `W19` | Relay 2 (Red Opto 5V, Jmp=H) | `DC+` | **Red** (`#DC2626`) | `J9 (RLY2_AMP_D7)` | `1` | `VIN (U1.15)` | `Power (+5V)` | `+5V` | Dupont 1×3 F-F |
| `W20` | Relay 2 (Red Opto 5V, Jmp=H) | `DC-` | **Black** (`#18181B`) | `J9 (RLY2_AMP_D7)` | `2` | `GND` | `Ground` | `GND` | Dupont 1×3 F-F |
| `W21` | Relay 2 (Red Opto 5V, Jmp=H) | `IN` | **Cyan** (`#0891B2`) | `J9 (RLY2_AMP_D7)` | `3` | `D7 (U2.10)` | `GPIO13` | `D7_RLY2_AMP` | Dupont 1×3 F-F |
| `W22` | Relay 2 (Red Opto 5V, Jmp=H) | `COM (Screw)` | **Red** (`#DC2626`) | `J10 (RLY2_SW)` | `1` | `VIN (U1.15)` | `Power (+5V)` | `+5V` | Dupont F-Pin |
| `W23` | Relay 2 (Red Opto 5V, Jmp=H) | `NO (Screw)` | **Orange** (`#EA580C`) | `J10 (RLY2_SW)` | `2` | `Switched +5V → J11.1` | `Switched +5V` | `AMP_5V` | Dupont F-Pin |
| `W24` | PAM8403 Audio Amplifier | `5V+` | **Red** (`#DC2626`) | `J11 (PAM8403_PWR)` | `1` | `Switched +5V (via RLY2)` | `Switched +5V` | `AMP_5V` | Dupont 1×2 F-F |
| `W25` | PAM8403 Audio Amplifier | `5V-` | **Black** (`#18181B`) | `J11 (PAM8403_PWR)` | `2` | `GND` | `Ground` | `GND` | Dupont 1×2 F-F |
| `W26` | PAM8403 Audio Amplifier | `L (Audio In)` | **White** (`#94A3B8`) | `J12 (AUDIO_D3)` | `1` | `D3 (U2.4)` via C4/R5/R6/C5 | `GPIO0` | `AUD_OUT` | Dupont 1×2 F-F |
| `W27` | PAM8403 Audio Amplifier | `GND (Audio ⊥)` | **Black** (`#18181B`) | `J12 (AUDIO_D3)` | `2` | `GND` | `Ground` | `GND` | Dupont 1×2 F-F |
| `W28` | Mini Speaker (28mm 8Ω 0.5W) | `SPK +` | **Yellow** (`#CA8A04`) | `PAM8403` *(inter-mod)* | `L_OUT+` | Off-board BTL + | `BTL Audio +` | `SPK_BTL_P` | 2-Wire Pair |
| `W29` | Mini Speaker (28mm 8Ω 0.5W) | `SPK -` | **Brown** (`#78350F`) | `PAM8403` *(inter-mod)* | `L_OUT-` | Off-board BTL − *(NOT GND)* | `BTL Audio −` | `SPK_BTL_N` | 2-Wire Pair |
| `W30` | DHT11 3-Pin Breakout | `VCC (+)` | **Red** (`#DC2626`) | `J13 (DHT11_D2)` | `1` | `3V3 (U1.11/U2.6)` | `Power (+3V3)` | `+3V3` | Dupont 1×3 F-F |
| `W31` | DHT11 3-Pin Breakout | `DATA (OUT)` | **Blue** (`#2563EB`) | `J13 (DHT11_D2)` | `2` | `D2 (U2.3)` | `GPIO4` | `D2_DHT11` | Dupont 1×3 F-F |
| `W32` | DHT11 3-Pin Breakout | `GND (-)` | **Black** (`#18181B`) | `J13 (DHT11_D2)` | `3` | `GND` | `Ground` | `GND` | Dupont 1×3 F-F |
| `W33` | Soil LM393 Comparator | `VCC` | **Red** (`#DC2626`) | `J14 (SOIL_A0)` | `1` | `3V3 (U1.11/U2.6)` *(3.3V only)* | `Power (+3V3)` | `+3V3` | Dupont 1×3 F-F |
| `W34` | Soil LM393 Comparator | `GND` | **Black** (`#18181B`) | `J14 (SOIL_A0)` | `2` | `GND` | `Ground` | `GND` | Dupont 1×3 F-F |
| `W35` | Soil LM393 Comparator | `AO` | **Green** (`#16A34A`) | `J14 (SOIL_A0)` | `3` | `A0 (U1.1)` | `ADC0` | `A0_SOIL` | Dupont 1×3 F-F |
| `W36` | YL-69 Soil Fork Probe | `Prong A` | **Yellow** (`#CA8A04`) | `LM393` *(inter-mod)* | `P1` | Off-board Probe | `Analog Probe` | `SOIL_PROBE_A` | Dupont 1×2 F-F |
| `W37` | YL-69 Soil Fork Probe | `Prong B` | **Orange** (`#EA580C`) | `LM393` *(inter-mod)* | `P2` | Off-board Probe | `Analog Probe` | `SOIL_PROBE_B` | Dupont 1×2 F-F |
| `W38` | KY-037 / KY-038 Sound Module | `+ (VCC)` | **Red** (`#DC2626`) | `J15 (KY037_D5)` | `1` | `3V3 (U1.11/U2.6)` *(3.3V only)* | `Power (+3V3)` | `+3V3` | Dupont 1×3 F-F |
| `W39` | KY-037 / KY-038 Sound Module | `G (GND)` | **Black** (`#18181B`) | `J15 (KY037_D5)` | `2` | `GND` | `Ground` | `GND` | Dupont 1×3 F-F |
| `W40` | KY-037 / KY-038 Sound Module | `DO` | **Yellow** (`#CA8A04`) | `J15 (KY037_D5)` | `3` | `D5 (U2.8)` | `GPIO14` | `D5_MIC_DO` | Dupont 1×3 F-F |

---

## 4. How 3D Wires and Readable Labels Are Shown

- **True 3D Color-Coded Dupont Wires (`3dmodels/wiring_harness.wrl` + 2D User Layers):**
  - Rather than falling back to 2D-only traces, `build_assembly.py` generates true 3D smooth cubic-Bézier circular tubes (`Ø1.30 mm`, outward-verified triangle normals enforced via positive signed-volume assertion) for all **40 wires (`W01..W40`)** plus **49 matte-black Dupont connector boots** seated on every vertical 2.54 mm header pin, attached via footprint `WIRING_HARNESS` (`Assembly_Wiring_Harness.kicad_mod`).
  - Every wire endpoint is read directly from KiCad `pcbnew` (`pad.GetPosition()`) *after* placing and rotating each module footprint, guaranteeing exact 0.00 mm pin alignment with zero rotation sign bugs.
  - Cross-board bridge wires `W13`/`W14` (`J8 RLY1_SW` → Relay 1 `COM`/`NO`) arch cleanly over the hub (apex `Z = 23.0..24.6 mm`, verified `>= 1.61 mm` over NodeMCU top `15.64 mm` and `>= 0.55 mm` over Relay 1 cube `18.5 mm`, zero clipping).
  - Matching 2D wire polylines are also placed on KiCad `User.1` (power), `User.2` (GND), `User.3` (signals), and `User.4` (inter-module) for 2D PCB Editor inspection.
- **3D Beveled Nameplates + Native 2D Text Labels (`3dmodels/assembly_labels.wrl` + `F.SilkS` + `Dwgs.User`):**
  - Because KiCad 10's 3D viewer clips `F.SilkS` outside `Edge.Cuts`, each of the 14 off-board modules gets **both** native KiCad text on `F.SilkS`/`Dwgs.User` **and** a 3D dark-slate beveled nameplate (`Z = 0.0..0.75 mm`) with category-colored accent rim (blue = Sensor, amber = Actuator, red = Power, cyan = Title Banner) and raised bright-white geometric stroke-vector text (`Z = 0.75..1.40 mm`), plus a dynamic top banner showing the actual parsed hub board size (`SMARTHOME HUB ASSEMBLY (80X65 MM)` or `(100X80 MM)`).

---

## 5. How to Re-Run the Generator

All commands run headless with zero interactive prompts:

```powershell
# 1. Regenerate full KiCad 10 assembly from the default hub PCB (single command line):
& "C:\Users\LENOVO\AppData\Local\Programs\KiCad\10.0\bin\python.exe" `
    hardware/kicad/smarthome_assembly/build_assembly.py

# 2. Regenerate from ANY redesigned hub PCB (e.g., 100 x 80 mm board):
& "C:\Users\LENOVO\AppData\Local\Programs\KiCad\10.0\bin\python.exe" `
    hardware/kicad/smarthome_assembly/build_assembly.py `
    --hub-pcb path/to/hub_100x80.kicad_pcb `
    --out-dir path/to/output_assembly

# 3. Regenerate + export 3D renders via kicad-cli:
& "C:\Users\LENOVO\AppData\Local\Programs\KiCad\10.0\bin\python.exe" `
    hardware/kicad/smarthome_assembly/build_assembly.py `
    --render-dir path/to/renders --render-width 2400 --render-height 1800 --render-quality high

# 4. (Optional) Regenerate all 15 static .wrl + .step 3D CAD models via FreeCAD 1.1:
& "C:\Users\LENOVO\AppData\Local\Programs\FreeCAD 1.1\bin\python.exe" `
    hardware/kicad/smarthome_assembly/build_3dmodels.py
```

---

## 6. Merged `100 × 80 mm` Single-Layer DIY Hub Assembly Verification (`hwmerge3-20261121`)

`build_assembly.py` parses `Edge.Cuts` and every connector (`J1..J15`, `U1`, `U2`) dynamically directly from the merged `100.00 × 80.00 mm` single-layer DIY hub PCB (`hardware/kicad/smarthome_hub/smarthome_hub.kicad_pcb`, 49 footprints incl. `Q1 S8050` + `R10 1k`, 4× M3 Ø3.2 mm mounting holes at `(5,5)(95,5)(5,75)(95,75)`):

| Metric | Merged 1-Layer DIY Hub (`100 × 80 mm`, `hwmerge3-20261121`) |
|---|---:|
| Parsed Hub Outline (`Edge.Cuts`) | `100.00 × 80.00 mm` |
| Dynamic Banner Text | `SMARTHOME HUB ASSEMBLY (100X80 MM)` |
| Modules Placed | `15 / 15` (NodeMCU + 14 off-board) |
| Relay Mounting Holes (`relay1_blue_srd05` & `relay2_red_opto`) | `44.5 × 20.5 mm`, `Ø3.1 mm` (reconciled w/ Mica `P01A_BASE_TECH`) |
| NodeMCU `U1`/`U2` 30-Pad Alignment Error | `0.000 mm` |
| 3D Wires Resolved (+ Dupont Boots) | `40 / 40` (`49` boots; `W17` Red `+5V`, `W18` Orange `BUZZ_K` via `Q1`) |
| 3D Label Plaques Placed | `15 / 15` |
| XY Bounding-Box Overlaps | `0` |
| Min Inter-Module/Plaque Clearance | `8.0 mm` (`PLQ_dht11_module` ↔ `PLQ_sg90_servo`) |
| Min Module-to-Own-Plaque Clearance | `5.0 mm` (`MOD:buzzer_tmb12a05` ↔ `PLQ_buzzer_tmb12a05`) |
| Forbidden Tokens (fan / AC / IR) | `0` |
| Overall Verification Status | **PASS** |

---

## 7. Independent Review Verdict & Findings History

A separate read-only `independent-reviewer` role (distinct from the CAD, KiCad scripting, and QA/render authors) audited every deliverable across three rounds:

- **Round 1 Verdict: `FAIL`** (0 CRITICAL, **1 MAJOR**, **4 MINOR**, 1 OBSERVATION):
  1. **[MAJOR #1 — FIXED]** All 10 colored wire tube shapes in `wiring_harness.wrl` had inverted (inward-facing) triangle normals (`signed_vol < 0`), causing KiCad's `--quality high` raytracer to shade colored wires dark/muddy. **Fix:** Reversed tube wall and end-cap triangle winding in `build_assembly.py` (`add_tube_pcb`), added a mandatory positive signed-volume assertion inside `write_vrml()` so inverted meshes can never regress, rebuilt both assemblies, and re-rendered all 4 official screenshots (`96..99`).
  2. **[MINOR #2 — FIXED]** Coplanar face Z-fighting on `psu_5v2a_dc_jack` (`pol_plus`/`pol_minus` flush at `Z = 13.00 mm`) and `submersible_pump` (`rear_potting` coplanar with `motor_cyl` at `X = -22.50 mm`). **Fix:** Raised `+`/`-` polarity marks to `Z = 13.00..13.15 mm` and recessed a `1.55 mm` rear pocket into `pump_body` in `build_3dmodels.py`, preserving exact datasheet envelopes.
  3. **[MINOR #3 — FIXED]** `README.md` line 76 overstated `W13`/`W14` bridge clearances over NodeMCU/Relay 1. **Fix:** Updated `README.md` line 76 to exact verified values (`apex Z = 23.0..24.6 mm`, `>= 1.61 mm` above NodeMCU, `>= 0.55 mm` above Relay 1 cube, zero clipping).
  4. **[MINOR #4 — FIXED]** Untracked local KiCad GUI sidecar `smarthome_assembly.kicad_prl` left behind by `kicad-cli pcb render`. **Fix:** Added automatic cleanup of transient `.kicad_prl` in `build_assembly.py` (`render_assembly_views()`) and removed the sidecar from the repo.
  5. **[MINOR #5 — FIXED]** Mild isometric proximity between `SOIL LM393` P1/P2 Dupont boot and its plaque bottom rim. **Fix:** Increased `soil_lm393_board` top plaque gap to `12.5 mm`.
- **Round 2 Verification:** Independently parsed all **17 `.wrl` files (214 shapes)** and confirmed **0 inverted shapes (100% strictly positive signed volume)**, 0 FreeCAD `.step` mismatches across all 15 modules, 0 electrical/pin-map mismatches, vivid raytraced wire colors and clean `+`/`-` and rear pump seal in all 4 PNGs (`96..99`), and clean-checkout single-command regeneration PASS on both `80×65` and `100×80` boards. Caught that `kicad-cli pcb render` had recreated `.kicad_prl` during screenshot re-render (prompting the root-cause cleanup in `render_assembly_views()`).
- **Round 3 Final Verdict: `PASS` (0 CRITICAL, 0 MAJOR, 0 MINOR)** — Confirmed `.kicad_prl` absent in repo and after fresh temp `--render-dir` execution, `git status` strictly clean under `hardware/kicad/smarthome_assembly/`, `hardware/kicad/smarthome_hub/` untouched, and all 4 screenshots `96..99` intact (`2384×1768 px`, > 1 MB each).

---

## 8. Real `kicad-cli pcb render` Screenshots (`96..99`)

All 4 screenshots are genuine KiCad 10.0.6 raytraced exports (`--width 2400 --height 1800 --quality high --background opaque --light-top 0.85 --light-side 0.65 --light-camera 0.35`; KiCad outputs tile-aligned `2384×1768 px` PNGs), stored in `C:\Users\LENOVO\datn-wt\agyhwasm1_20261121\screenshots\`:

| File | Resolution & Size | Render Time | Camera Settings | What It Shows (Visually Verified) |
|---|---:|---:|---|---|
| `96_assembly_iso.png` | `2384 × 1768 px` (`1.79 MB`) | `109.4 s` | `--rotate -37,0,20 --perspective --zoom 0.258 --pan 1.0,0.4,0` | Full isometric assembly of the `80×65 mm` hub + seated NodeMCU v2 + all 14 off-board modules + 40 vivid color-coded 3D wires + 15 crisp plaques + `80X65 MM` banner with generous margins and zero overlaps/cropping. |
| `97_assembly_top.png` | `2384 × 1768 px` (`1.10 MB`) | `84.9 s` | `--side top --zoom 0.230` | Orthogonal top-down plan view showing real-world relative sizing of all 15 modules, clean wiring corridors, distinct wire color routing, and all 15 labels 100% legible. |
| `98_assembly_closeup.png` | `2384 × 1768 px` (`3.36 MB`) | `220.0 s` | `--rotate -35,0,18 --perspective --zoom 0.46 --pan 0.0,0.4,0` | Photorealistic raytraced close-up of the central hub header banks, NodeMCU seated flush on `U1`/`U2`, matte-black Dupont boots, Phoenix screw terminals `J1`/`J2`, vivid 3D arched wires casting soft shadows over the ESP-12E shield, crisp DC-005 `+`/`-` marks, clean matte-black pump rear seal, and adjacent modules. |
| `99_assembly_iso_100x80_placeholder.png` | `2384 × 1768 px` (`1.63 MB`) | `107.9 s` | `--rotate -37,0,20 --perspective --zoom 0.295 --pan 1.0,0.4,0` | Full isometric render generated dynamically from the `100×80 mm` placeholder hub board (4× M3 holes at 5 mm inset), displaying the visibly larger hub board, dynamic `SMARTHOME HUB ASSEMBLY (100X80 MM)` banner, centered NodeMCU, all 14 modules, 40 wires, and 15 plaques with zero overlaps. |

---

## 9. Git Branch & Commits

- **Branch:** `hwasm-20261121` (branched from `master` `131bdc2`; pushed with plain `git push origin hwasm-20261121`, no force-push).
- **Assembly Project Commit:** `b8df4d10e5dc12a43af90ffd510fd2167eb9a008` (`feat(hwasm): add generic KiCad 10 3D assembly project with 15 CAD models and 40 3D wires` — 59 files under `hardware/kicad/smarthome_assembly/`).
- **Report Copy in Worktree:** `docs/phan_cung/assembly/ASM_REPORT.md` (committed in the follow-up docs commit on `hwasm-20261121`).

---

## 10. Deferred Items

- **Optional sibling-branch test against `origin/hwdiy-20261121`:** Checked via read-only `git ls-remote --heads origin hwdiy-20261121` at session end; sibling branch `hwdiy-20261121` has not been pushed to `origin` yet (explicitly noted as optional and not required for `ALL_DONE`). Once `hwdiy-20261121` is pushed, the assembly can be regenerated against its actual `100 × 80 mm` DIY board in one command using `--hub-pcb`.
