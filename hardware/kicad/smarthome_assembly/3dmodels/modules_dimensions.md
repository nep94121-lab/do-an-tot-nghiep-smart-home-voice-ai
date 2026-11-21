# Smart Home Voice AI — KiCad 10 3D Module Dimensions & Datasheet Verification

> **Generator:** `hardware/kicad/smarthome_assembly/build_3dmodels.py` (FreeCAD 1.1 OpenCASCADE B-Rep -> `.wrl` VRML 2.0 + `.step`)
> **Policy:** 15 modules total (`nodemcu_v2_amica` + 14 off-board modules). Zero fan, zero AC, zero IR anywhere.
> **Coordinate System:** `.wrl` uses `1 unit = 2.54 mm` (`+X` right, `+Y` UP, `+Z` UP); `.step` uses `1 unit = 1.0 mm` (same axes); `modules_manifest.json` uses KiCad PCBnew local coordinates (`+X` right, `+Y` DOWN, `+Z` UP).
> **Verification Tolerance:** `<= 0.50 mm` for every rigid body dimension (`L x W x H`), and `<= 0.15 mm` between `.wrl` and `.step` read-back envelopes.

## 1. Datasheet vs Measured 3D Model Verification Table

| # | Module ID | Display Name | Datasheet Body `X × Y × Z` (mm) | Measured Body (mm) | Measured Full `.wrl` (mm) | Measured Full `.step` (mm) | Max Err (mm) | Status |
|---:|---|---|---:|---:|---:|---:|---:|:---:|
| 0 | `nodemcu_v2_amica` | NodeMCU ESP8266 v2 Amica (CP2102) | `25.40 × 49.43 × 7.14` | `25.40 × 49.43 × 7.14` | `25.40 × 49.43 × 13.14` | `25.40 × 49.43 × 13.14` | `0.000` | **PASS** |
| 1 | `sg90_servo` | TowerPro SG90 Micro Servo | `32.20 × 12.20 × 31.00` | `32.20 × 12.20 × 31.00` | `32.20 × 12.20 × 31.00` | `32.20 × 12.20 × 31.00` | `0.000` | **PASS** |
| 2 | `led_5mm_living` | 5mm LED Living Room (Warm Amber) | `5.80 × 5.80 × 8.60` | `5.55 × 5.80 × 8.60` | `5.55 × 5.80 × 8.60` | `5.55 × 5.80 × 8.60` | `0.251` | **PASS** |
| 3 | `led_5mm_bedroom` | 5mm LED Bedroom (Bright Red) | `5.80 × 5.80 × 8.60` | `5.55 × 5.80 × 8.60` | `5.55 × 5.80 × 8.60` | `5.55 × 5.80 × 8.60` | `0.251` | **PASS** |
| 4 | `relay1_blue_srd05` | Relay 1 Blue 1-Channel 5V Module | `50.00 × 26.00 × 18.50` | `50.00 × 26.00 × 18.50` | `50.00 × 26.00 × 18.50` | `50.00 × 26.00 × 18.50` | `0.000` | **PASS** |
| 5 | `relay2_red_opto` | Relay 2 Red Opto-Isolated 1-Channel 5V Module | `50.00 × 26.00 × 18.50` | `50.00 × 26.00 × 18.50` | `50.00 × 26.00 × 18.50` | `50.00 × 26.00 × 18.50` | `0.000` | **PASS** |
| 6 | `submersible_pump` | 3-6V Mini Submersible Water Pump + Silicone Tube | `45.00 × 24.00 × 33.00` | `45.00 × 23.99 × 33.00` | `45.00 × 23.99 × 41.87` | `45.00 × 24.00 × 41.98` | `0.007` | **PASS** |
| 7 | `buzzer_tmb12a05` | TMB12A05 Active 5V Buzzer | `12.00 × 12.00 × 9.50` | `12.00 × 12.00 × 9.50` | `12.00 × 12.00 × 9.50` | `12.00 × 12.00 × 9.50` | `0.004` | **PASS** |
| 8 | `pam8403_amp` | PAM8403 Mini Audio Amplifier Module | `21.00 × 18.00 × 3.10` | `21.00 × 18.00 × 3.10` | `21.00 × 18.00 × 3.10` | `21.00 × 18.00 × 3.10` | `0.000` | **PASS** |
| 9 | `speaker_28mm` | 28mm 8 Ohm 0.5W Mini Speaker | `28.00 × 28.00 × 5.20` | `28.00 × 27.99 × 5.20` | `28.00 × 27.99 × 5.20` | `28.00 × 28.00 × 5.20` | `0.009` | **PASS** |
| 10 | `dht11_module` | DHT11 3-Pin Breakout Module | `28.00 × 14.00 × 7.10` | `28.00 × 14.00 × 7.10` | `28.00 × 14.00 × 7.10` | `28.00 × 14.00 × 7.10` | `0.000` | **PASS** |
| 11 | `soil_lm393_board` | LM393 Soil Moisture Comparator Module | `32.00 × 14.00 × 12.10` | `32.00 × 14.00 × 12.10` | `32.00 × 14.00 × 12.10` | `32.00 × 14.00 × 12.10` | `0.000` | **PASS** |
| 12 | `yl69_soil_probe` | YL-69 Soil Moisture Fork Probe | `60.00 × 20.00 × 1.60` | `60.00 × 20.00 × 1.60` | `60.00 × 20.00 × 1.60` | `60.00 × 20.00 × 1.60` | `0.000` | **PASS** |
| 13 | `ky037_sound` | KY-037 / KY-038 Sound Sensor Module | `35.00 × 15.00 × 13.10` | `35.00 × 15.00 × 13.10` | `35.00 × 15.00 × 13.10` | `35.00 × 15.00 × 13.10` | `0.000` | **PASS** |
| 14 | `psu_5v2a_dc_jack` | 5V 2A DC Jack PSU Input (Adapter + 5.5x2.1mm Plug + Screw Terminal) | `118.00 × 34.00 × 24.00` | `118.00 × 34.00 × 24.00` | `118.00 × 34.00 × 24.00` | `118.00 × 34.00 × 24.00` | `0.000` | **PASS** |

## 2. Sub-Feature Specifications & Verified Datasheet Sources

| # | Module ID | Key Sub-Features & Mounting Notes | Datasheet / Reference Source |
|---:|---|---|---|
| 0 | `nodemcu_v2_amica` | PCB 48.26x25.40x1.60mm; 2x15 header P2.54mm row 22.86mm; ESP-12E shield 16.0x12.0x3.0mm; Micro-USB +1.17mm overhang; CP2102 QFN; AMS1117; RST/FLASH buttons *(Seating: Z=0 is bottom of male header plastic strip; mount at offset Z=+8.5mm on U1/U2 female sockets so pins (Z=-6..0mm) plug cleanly inside sockets.)* | [Amica NodeMCU ESP8266 DevKit v1.0 (v2 CP2102)](https://components101.com/development-boards/nodemcu-esp8266-pinout-features-and-datasheet) |
| 1 | `sg90_servo` | Body 22.8x12.2x22.5mm; mounting ears 32.2x12.2x2.5mm at Z=15.9mm w/ 2x Ø2.0mm holes; gear boss Z=26.7mm; white output shaft & horn Z=31.0mm; 3-pin pigtail *(Seating: Mount flush on assembly top surface (Z offset = 0.0 mm))* | [TowerPro SG90 9g Micro Servo Datasheet](https://www.handsontec.com/dataspecs/SG90-Servo.pdf) |
| 2 | `led_5mm_living` | Ø5.0mm dome & barrel; Ø5.8x1.0mm base flange w/ cathode flat; body H=8.60mm; 2.54mm pitch Anode(+)/Cathode(-) pins *(Seating: Mount flush on assembly top surface (Z offset = 0.0 mm))* | [Kingbright WP7113 T-1 3/4 5mm LED (Warm Yellow/Amber)](https://www.kingbrightusa.com/images/catalog/spec/wp7113id.pdf) |
| 3 | `led_5mm_bedroom` | Ø5.0mm dome & barrel; Ø5.8x1.0mm base flange w/ cathode flat; body H=8.60mm; 2.54mm pitch Anode(+)/Cathode(-) pins *(Seating: Mount flush on assembly top surface (Z offset = 0.0 mm))* | [Kingbright WP7113 T-1 3/4 5mm LED (Bright Red WP7113ID)](https://www.kingbrightusa.com/images/catalog/spec/wp7113id.pdf) |
| 4 | `relay1_blue_srd05` | Blue PCB 50.0x26.0x1.6mm w/ 4x Ø3.1mm holes (44.5x20.5mm pitch); Songle SRD-05VDC-SL-C 19.0x15.5x15.5mm; 3-pos 5.08mm screw terminal (15.24mm); 1x3 2.54mm header *(Seating: Mount flush on assembly top surface (Z offset = 0.0 mm))* | [1-Ch 5V Relay Module w/ Songle SRD-05VDC-SL-C](https://www.reichelt.com/de/en/shop/product/developer_boards_-_relay_1_channel_srd-05vdc-sl-c-371953) |
| 5 | `relay2_red_opto` | Red PCB 50.0x26.0x1.6mm w/ 4x Ø3.1mm holes (44.5x20.5mm pitch); Songle SRD-05VDC-SL-C 19.0x15.5x15.5mm; PC817 optocoupler; yellow H/L jumper (set H); 3-pos 5.08mm terminal; 1x3 2.54mm header *(Seating: Mount flush on assembly top surface (Z offset = 0.0 mm))* | [1-Ch 5V Opto-Isolated Relay Module (SRD-05VDC-SL-C + PC817)](https://www.electrokit.com/en/rela-srd-1-pol-vaxlande-5v) |
| 6 | `submersible_pump` | White cylindrical motor Ø24.0x45.0mm; top vertical outlet nozzle Ø7.5mm OD to Z=33.0mm; front intake grille; curved Ø8.0mm OD translucent silicone tube stub *(Seating: Mount flush on assembly top surface (Z offset = 0.0 mm))* | [Horizontal 3-6V DC Mini Submersible Water Pump (Soldered 101844)](https://www.mouser.lt/datasheet/2/1398/Soldered_101844_mini_water_pump-3532437.pdf) |
| 7 | `buzzer_tmb12a05` | Black cylinder Ø12.0x9.5mm; top sound port Ø3.0mm; white '+' polarity mark; 7.6mm pin pitch *(Seating: Mount flush on assembly top surface (Z offset = 0.0 mm))* | [TMB12A05 5V Active Electromagnetic Buzzer](https://osoyoo.com/2017/05/05/buzzer-5v-breadboard-friendlytmb12a05/) |
| 8 | `pam8403_amp` | Bare green PCB 21.0x18.0x1.6mm; SOP-16 PAM8403 IC 9.9x3.9x1.5mm (1.27mm pitch); 2.54mm power/audio/BTL pads *(Seating: Mount flush on assembly top surface (Z offset = 0.0 mm))* | [Diodes Inc. PAM8403 3W Stereo Class-D Audio Amplifier](https://www.elecrow.com/download/PAM8403-datasheet.pdf) |
| 9 | `speaker_28mm` | Round silver metal frame Ø28.0x5.2mm; black Mylar cone + silver center dust cap; rear magnet boss Ø14.0mm; 2 rim solder pads *(Seating: Mount flush on assembly top surface (Z offset = 0.0 mm))* | [PUI Audio AS02808MR-R 28mm 8 Ohm 0.5W Speaker](https://puiaudio.com/file/specs-AS02808MR-R.pdf) |
| 10 | `dht11_module` | Blue PCB 28.0x14.0x1.6mm w/ Ø3.0mm hole; light-blue ventilated DHT11 grid body 15.5x12.0x5.5mm (H=7.1mm); 1x3 2.54mm header *(Seating: Mount flush on assembly top surface (Z offset = 0.0 mm))* | [Aosong DHT11 Digital Temperature & Humidity Sensor](https://image.dfrobot.com/image/data/KIT0003/DHT11%20datasheet.pdf) |
| 11 | `soil_lm393_board` | Blue PCB 32.0x14.0x1.6mm w/ Ø3.0mm hole; blue 3296W pot + brass screw (H=12.1mm); SOIC-8 LM393; 1x4 hub header + 1x2 probe header *(Seating: Mount flush on assembly top surface (Z offset = 0.0 mm))* | [LM393 Soil Moisture Sensor Comparator Board](https://handsontec.com/dataspecs/sensor/Soil%20Moisture%20Sensor.pdf) |
| 12 | `yl69_soil_probe` | Fork FR4 PCB 60.0x20.0x1.6mm w/ 7.0mm center slot between two 6.5mm prongs; gold-tinned sensing strips; 1x2 2.54mm header at handle *(Seating: Mount flush on assembly top surface (Z offset = 0.0 mm))* | [YL-69 / FC-28 Resistive Soil Moisture Fork Probe](https://handsontec.com/dataspecs/sensor/Soil%20Moisture%20Sensor.pdf) |
| 13 | `ky037_sound` | Red PCB 31.5x15.0x1.6mm (total L=35.0mm w/ front mic); ECM-9767 silver mic Ø9.7x6.7mm w/ black felt; blue 3296W pot (H=13.1mm); LM393; 1x4 header (DO/G/+/AO) *(Seating: Mount flush on assembly top surface (Z offset = 0.0 mm))* | [Joy-IT KY-038 / KY-037 Sound Sensor (ECM-9767 + LM393)](https://sensorkit.joy-it.net/en/sensors/ky-038) |
| 14 | `psu_5v2a_dc_jack` | Compact matte-black 5V 2A adapter body 46.0x34.0x24.0mm w/ metallic prongs; black DC cable + mated 5.5x2.1mm male barrel plug (Ø5.5mm sleeve); green/black DC-005 female screw-terminal adapter 38.0x14.0x13.0mm (+5V/GND facing +X) *(Seating: Mount flush on assembly top surface (Z offset = 0.0 mm))* | [5V 2A DC Wall Adapter (Mean Well SGA12U05-P1J class) + Adafruit #368 Female 5.5x2.1mm Screw Terminal Adapter](https://www.mouser.com/datasheet/2/260/SGA12U-SPEC-1109436.pdf) |

## 3. File Artifacts Generated

- `3dmodels/<module_id>.wrl` — 15 multi-color VRML 2.0 files (`#VRML V2.0 utf8`, `1 unit = 2.54 mm`) for KiCad 10 3D Viewer & `kicad-cli pcb render`.
- `3dmodels/<module_id>.step` — 15 exact OpenCASCADE B-Rep STEP files (`1 unit = 1.0 mm`) for MCAD & `kicad-cli pcb export step`.
- `3dmodels/modules_manifest.json` — Machine-readable PCBnew-coordinate `bbox_mm` & exact `pins` table for deterministic assembly wiring.
- `3dmodels/modules_dimensions.csv` — Machine-readable dimension & datasheet audit table.
