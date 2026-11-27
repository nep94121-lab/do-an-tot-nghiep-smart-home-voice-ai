# Complete Hardware Wiring Reference Table — Smart Home Voice AI (Type 1 Hub PCB)

> **Single Source of Truth (SSOT):** Auto-generated deterministically by `scripts/generate_wiring_docs.py` directly from `hardware/wiring_contract.py`.
> **Verified Wiring Totals:** **40 physical wires** = **36 Hub PCB plug-in wires** (`J1`..`J15`, 100% of all 36 connector pins) + **4 off-board inter-module wires** (`PAM8403 → Mini Speaker ×2`, `LM393 → YL-69 Soil Probe ×2`).
> **Removed Legacy Parts Policy (Strict Confirmation):** **NO fan, NO AC, NO IR** (`VS1838B`, `IR LED 940nm`, cooling fan, or AC mains relay do NOT exist anywhere in firmware, KiCad schematic/PCB, Blender 3D, or wiring harnesses).
> **Companion 2D Vector Diagram:** [`wiring_diagram_2d.svg`](wiring_diagram_2d.svg) · [`wiring_diagram_2d.pdf`](wiring_diagram_2d.pdf) · [`wiring_diagram_2d.png`](wiring_diagram_2d.png)

## 1. Master Point-to-Point Wiring Table (All 40 Physical Wires)

Every single physical plug-in wire is listed one row per wire (`W01`–`W40`), covering all 15 Hub PCB connectors (`J1`–`J15`) and all off-board module-to-module links.

| Wire ID | Hub Connector / Pin | Wire Color | Target Module | Module Pin | NodeMCU Pin (Dx) | GPIO | KiCad Net | Wire Type | Firmware Reference | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| `W01` | `J1.1 (PWR_5V_IN)` | **Red** (`#DC2626`) | 5V 2A External Supply | `+5V` | `VIN (U1.15)` | `Power (+5V)` | `+5V` | Screw Terminal 22AWG | `esp8266_smarthome.ino:15-16` | Main +5V rail; on-board C1/C2 (470uF 16V) + C3 (100nF) bulk decoupling + D3 power LED |
| `W02` | `J1.2 (PWR_5V_IN)` | **Black** (`#18181B`) | 5V 2A External Supply | `GND` | `GND (U1.10/14, U2.7/14)` | `Ground` | `GND` | Screw Terminal 22AWG | `esp8266_smarthome.ino:15-16` | Common system ground reference shared with NodeMCU and all modules |
| `W03` | `J3.1 (SERVO_D1)` | **Orange** (`#EA580C`) | SG90 Micro Servo | `PWM (Orange)` | `D1 (U2.2)` | `GPIO5` | `D1_SERVO` | Dupont 1x3 F-M | `esp8266_smarthome.ino:56` | 50Hz PWM control: 0 deg closed / 90 deg open (main_door) |
| `W04` | `J3.2 (SERVO_D1)` | **Red** (`#DC2626`) | SG90 Micro Servo | `VCC (Red)` | `VIN (U1.15)` | `Power (+5V)` | `+5V` | Dupont 1x3 F-M | `esp8266_smarthome.ino:56` | +5V servo supply decoupled by on-board C1 470uF 16V |
| `W05` | `J3.3 (SERVO_D1)` | **Black** (`#18181B`) | SG90 Micro Servo | `GND (Brown)` | `GND` | `Ground` | `GND` | Dupont 1x3 F-M | `esp8266_smarthome.ino:56` | Common GND (connects to SG90 brown pigtail wire) |
| `W06` | `J4.1 (LED_LR_D0)` | **Yellow** (`#CA8A04`) | 5mm LED (Living Room) | `Anode (+)` | `D0 (U2.1) via R1 220R` | `GPIO16` | `LED_LR_A` | Dupont 1x2 F-F | `esp8266_smarthome.ino:55` | Active-HIGH through on-board 220R series resistor R1; also enroll_blink |
| `W07` | `J4.2 (LED_LR_D0)` | **Black** (`#18181B`) | 5mm LED (Living Room) | `Cathode (-)` | `GND` | `Ground` | `GND` | Dupont 1x2 F-F | `esp8266_smarthome.ino:55` | LED cathode return to common GND |
| `W08` | `J5.1 (LED_BR_D4)` | **Purple** (`#9333EA`) | 5mm LED (Bedroom) | `Anode (+)` | `+3V3 via R2 220R` | `Power (+3V3 limited)` | `LED_BR_A` | Dupont 1x2 F-F | `esp8266_smarthome.ino:59,68` | Current-limited +3.3V via on-board R2 220R for boot-safe Active-LOW LED |
| `W09` | `J5.2 (LED_BR_D4)` | **White** (`#94A3B8`) | 5mm LED (Bedroom) | `Cathode (-)` | `D4 (U2.5)` | `GPIO2` | `D4_LED_BR` | Dupont 1x2 F-F | `esp8266_smarthome.ino:59,68` | Active-LOW sink (BEDROOM_LED_ACTIVE_LOW=true); on-board R7 10k pull-up keeps GPIO2 HIGH at boot |
| `W10` | `J7.1 (RLY1_PUMP_D6)` | **Red** (`#DC2626`) | Relay 1 (Blue 5V 1-ch) | `VCC` | `VIN (U1.15)` | `Power (+5V)` | `+5V` | Dupont 1x3 F-F | `esp8266_smarthome.ino:61,70` | 5V coil power for blue 1-channel Songle SRD-05VDC-SL-C relay module |
| `W11` | `J7.2 (RLY1_PUMP_D6)` | **Black** (`#18181B`) | Relay 1 (Blue 5V 1-ch) | `GND` | `GND` | `Ground` | `GND` | Dupont 1x3 F-F | `esp8266_smarthome.ino:61,70` | Relay 1 module logic/coil ground |
| `W12` | `J7.3 (RLY1_PUMP_D6)` | **Green** (`#16A34A`) | Relay 1 (Blue 5V 1-ch) | `IN` | `D6 (U2.9)` | `GPIO12` | `D6_RLY1_PUMP` | Dupont 1x3 F-F | `esp8266_smarthome.ino:61,70` | Relay 1 trigger input (PUMP_RELAY_ACTIVE_LOW=false, active-HIGH) |
| `W13` | `J8.1 (RLY1_SW)` | **Red** (`#DC2626`) | Relay 1 (Blue 5V 1-ch) | `COM (Screw)` | `VIN (U1.15)` | `Power (+5V)` | `+5V` | Dupont F-Pin (22AWG) | `esp8266_smarthome.ino:61` | Feeds +5V power rail into Relay 1 COM screw terminal |
| `W14` | `J8.2 (RLY1_SW)` | **Yellow** (`#CA8A04`) | Relay 1 (Blue 5V 1-ch) | `NO (Screw)` | `Switched +5V -> J2.1` | `Switched +5V` | `PUMP_5V` | Dupont F-Pin (22AWG) | `esp8266_smarthome.ino:61` | Switched +5V return from Relay 1 NO to Hub PCB D1 (1N4007 flyback) & J2.1 |
| `W15` | `J2.1 (PUMP_OUT)` | **Red** (`#DC2626`) | Mini Submersible Pump (3-6V) | `Pump + (Red)` | `Switched +5V (via RLY1)` | `Switched +5V` | `PUMP_5V` | Screw Terminal 22AWG | `esp8266_smarthome.ino:61,572` | Switched +5V to pump motor; protected by on-board D1 1N4007 flyback & C2 470uF 16V |
| `W16` | `J2.2 (PUMP_OUT)` | **Black** (`#18181B`) | Mini Submersible Pump (3-6V) | `Pump - (Black)` | `GND` | `Ground` | `GND` | Screw Terminal 22AWG | `esp8266_smarthome.ino:61,572` | Pump motor return to GND (anode of on-board D1 1N4007) |
| `W17` | `J6.1 (BUZZ_D8)` | **Red** (`#DC2626`) | Active 5V Buzzer (TMB12A05) | `Buzzer (+)` | `VIN (+5V)` | `Power (+5V)` | `+5V` | Dupont 1x2 F-F | `esp8266_smarthome.ino:63,399` | +5V supply to TMB12A05 buzzer anode; protected by on-board D2 1N4007 flyback across J6.1-J6.2 |
| `W18` | `J6.2 (BUZZ_D8)` | **Orange** (`#EA580C`) | Active 5V Buzzer (TMB12A05) | `Buzzer (-)` | `D8 (U2.11) via Q1 S8050` | `GPIO15 (NPN low-side)` | `BUZZ_K` | Dupont 1x2 F-F | `esp8266_smarthome.ino:63,399` | Low-side switched by on-board Q1 (S8050 NPN) + R10 1k base resistor; R9 10k pull-down keeps GPIO15 LOW at boot |
| `W19` | `J9.1 (RLY2_AMP_D7)` | **Red** (`#DC2626`) | Relay 2 (Red Opto 5V, Jmp=H) | `DC+` | `VIN (U1.15)` | `Power (+5V)` | `+5V` | Dupont 1x3 F-F | `esp8266_smarthome.ino:62,71` | 5V coil/opto supply for red opto-isolated 1-ch relay module (jumper set to H) |
| `W20` | `J9.2 (RLY2_AMP_D7)` | **Black** (`#18181B`) | Relay 2 (Red Opto 5V, Jmp=H) | `DC-` | `GND` | `Ground` | `GND` | Dupont 1x3 F-F | `esp8266_smarthome.ino:62,71` | Relay 2 module ground |
| `W21` | `J9.3 (RLY2_AMP_D7)` | **Cyan** (`#0891B2`) | Relay 2 (Red Opto 5V, Jmp=H) | `IN` | `D7 (U2.10)` | `GPIO13` | `D7_RLY2_AMP` | Dupont 1x3 F-F | `esp8266_smarthome.ino:62,71` | Active-HIGH trigger (SPEAKER_RELAY_ACTIVE_LOW=false); auto-off 1.5s after chime |
| `W22` | `J10.1 (RLY2_SW)` | **Red** (`#DC2626`) | Relay 2 (Red Opto 5V, Jmp=H) | `COM (Screw)` | `VIN (U1.15)` | `Power (+5V)` | `+5V` | Dupont F-Pin | `esp8266_smarthome.ino:62` | Feeds +5V rail into Relay 2 COM screw terminal |
| `W23` | `J10.2 (RLY2_SW)` | **Orange** (`#EA580C`) | Relay 2 (Red Opto 5V, Jmp=H) | `NO (Screw)` | `Switched +5V -> J11.1` | `Switched +5V` | `AMP_5V` | Dupont F-Pin | `esp8266_smarthome.ino:62` | Switched +5V return from Relay 2 NO to Hub C6 (100nF) & J11.1 |
| `W24` | `J11.1 (PAM8403_PWR)` | **Red** (`#DC2626`) | PAM8403 Audio Amplifier | `5V+` | `Switched +5V (via RLY2)` | `Switched +5V` | `AMP_5V` | Dupont 1x2 F-F | `esp8266_smarthome.ino:62,163` | Relay-switched +5V supply to PAM8403 (decoupled by on-board C6 100nF) |
| `W25` | `J11.2 (PAM8403_PWR)` | **Black** (`#18181B`) | PAM8403 Audio Amplifier | `5V-` | `GND` | `Ground` | `GND` | Dupont 1x2 F-F | `esp8266_smarthome.ino:62,163` | PAM8403 power ground |
| `W26` | `J12.1 (AUDIO_D3)` | **White** (`#94A3B8`) | PAM8403 Audio Amplifier | `L (Audio In)` | `D3 (U2.4) via C4/R5/R6/C5` | `GPIO0` | `AUD_OUT` | Dupont 1x2 F-F | `esp8266_smarthome.ino:58,166-184` | DC-blocked (C4 10uF) & RC-attenuated (R5/R6 2.2k, C5 10nF) audio; R4 10k pull-up + IDLE=INPUT for boot safety |
| `W27` | `J12.2 (AUDIO_D3)` | **Black** (`#18181B`) | PAM8403 Audio Amplifier | `GND (Audio ⊥)` | `GND` | `Ground` | `GND` | Dupont 1x2 F-F | `esp8266_smarthome.ino:58` | Audio input signal ground reference |
| `W28` | `PAM8403 L_OUT+` | **Yellow** (`#CA8A04`) | Mini Speaker (28mm 8Ω 0.5W) | `SPK +` | `Off-board (PAM8403 BTL)` | `BTL Audio +` | `SPK_BTL_P` | 2-Wire Pair | `esp8266_smarthome.ino:16,58` | Bridge-Tied Load (BTL) positive output; DO NOT short to GND |
| `W29` | `PAM8403 L_OUT-` | **Brown** (`#78350F`) | Mini Speaker (28mm 8Ω 0.5W) | `SPK -` | `Off-board (PAM8403 BTL)` | `BTL Audio -` | `SPK_BTL_N` | 2-Wire Pair | `esp8266_smarthome.ino:16,58` | Bridge-Tied Load (BTL) negative output; NEVER tie to GND |
| `W30` | `J13.1 (DHT11_D2)` | **Red** (`#DC2626`) | DHT11 3-Pin Breakout | `VCC (+)` | `3V3 (U1.11/U2.6)` | `Power (+3V3)` | `+3V3` | Dupont 1x3 F-F | `esp8266_smarthome.ino:57,83` | 3.3V sensor supply |
| `W31` | `J13.2 (DHT11_D2)` | **Blue** (`#2563EB`) | DHT11 3-Pin Breakout | `DATA (OUT)` | `D2 (U2.3)` | `GPIO4` | `D2_DHT11` | Dupont 1x3 F-F | `esp8266_smarthome.ino:57,83,544` | 1-wire data bus with on-board R3 10k pull-up to +3V3 |
| `W32` | `J13.3 (DHT11_D2)` | **Black** (`#18181B`) | DHT11 3-Pin Breakout | `GND (-)` | `GND` | `Ground` | `GND` | Dupont 1x3 F-F | `esp8266_smarthome.ino:57` | DHT11 sensor ground |
| `W33` | `J14.1 (SOIL_A0)` | **Red** (`#DC2626`) | Soil LM393 Comparator Module | `VCC` | `3V3 (U1.11/U2.6)` | `Power (+3V3)` | `+3V3` | Dupont 1x3 F-F | `esp8266_smarthome.ino:18,64` | STRICTLY 3.3V (never 5V) so AO stays within ESP8266 ADC0 safe range |
| `W34` | `J14.2 (SOIL_A0)` | **Black** (`#18181B`) | Soil LM393 Comparator Module | `GND` | `GND` | `Ground` | `GND` | Dupont 1x3 F-F | `esp8266_smarthome.ino:18,64` | Soil sensor ground (LM393 DO pin intentionally left NC / unconnected) |
| `W35` | `J14.3 (SOIL_A0)` | **Green** (`#16A34A`) | Soil LM393 Comparator Module | `AO` | `A0 (U1.1)` | `ADC0` | `A0_SOIL` | Dupont 1x3 F-F | `esp8266_smarthome.ino:64,568` | Analog moisture output (filtered by on-board C7 100nF); <40% ON / >=70% OFF |
| `W36` | `LM393 Probe +` | **Yellow** (`#CA8A04`) | YL-69 Soil Fork Probe | `Prong A` | `Off-board (LM393)` | `Analog Probe` | `SOIL_PROBE_A` | Dupont 1x2 F-F | `esp8266_smarthome.ino:18,64` | 2-wire fork probe pair from LM393 2-pin header to YL-69 resistive prongs |
| `W37` | `LM393 Probe -` | **Orange** (`#EA580C`) | YL-69 Soil Fork Probe | `Prong B` | `Off-board (LM393)` | `Analog Probe` | `SOIL_PROBE_B` | Dupont 1x2 F-F | `esp8266_smarthome.ino:18,64` | 2-wire fork probe pair from LM393 2-pin header to YL-69 resistive prongs |
| `W38` | `J15.1 (KY037_D5)` | **Red** (`#DC2626`) | KY-037 / KY-038 Sound Module | `+ (VCC)` | `3V3 (U1.11/U2.6)` | `Power (+3V3)` | `+3V3` | Dupont 1x3 F-F | `esp8266_smarthome.ino:14,60` | STRICTLY 3.3V so DO logic HIGH matches ESP8266 3.3V GPIO14 |
| `W39` | `J15.2 (KY037_D5)` | **Black** (`#18181B`) | KY-037 / KY-038 Sound Module | `G (GND)` | `GND` | `Ground` | `GND` | Dupont 1x3 F-F | `esp8266_smarthome.ino:14,60` | KY-037 ground (AO pin intentionally left NC / unconnected) |
| `W40` | `J15.3 (KY037_D5)` | **Yellow** (`#CA8A04`) | KY-037 / KY-038 Sound Module | `DO` | `D5 (U2.8)` | `GPIO14` | `D5_MIC_DO` | Dupont 1x3 F-F | `esp8266_smarthome.ino:60,412` | Digital clap/loud-sound interrupt (RISING edge, debounce >= 400ms) |

## 2. Locked 10-Pin ESP8266 NodeMCU v2 Amica Contract vs Firmware

Cross-verified against `firmware/esp8266_smarthome/esp8266_smarthome.ino` (`#define PIN_*` lines 55–64 and `setup()` lines 389–416):

| Firmware Macro | NodeMCU Pin | ESP8266 GPIO | Hub Connector / Signal | Socket Pad | Firmware Line | Boot / Logic Polarity |
|---|---|---|---|---|---|---|
| `PIN_LIVING_LIGHT` | **D0** | `GPIO16` | `LED_LR_D0 / J4` | `U2.1` | `firmware/esp8266_smarthome/esp8266_smarthome.ino:88` | Active-HIGH via R1 (220Ω); also `enroll_blink` |
| `PIN_MAIN_DOOR_SERVO` | **D1** | `GPIO5` | `SERVO_D1 / J3` | `U2.2` | `firmware/esp8266_smarthome/esp8266_smarthome.ino:89` | 50 Hz PWM (`0°` closed / `90°` open); failsafe close on offline |
| `PIN_DHT11` | **D2** | `GPIO4` | `DHT11_D2 / J13` | `U2.3` | `firmware/esp8266_smarthome/esp8266_smarthome.ino:90` | 1-Wire data bus with on-board R3 (10kΩ) pull-up to +3V3 |
| `PIN_AUDIO_PWM` | **D3** | `GPIO0` | `AUDIO_D3 / J12` | `U2.4` | `firmware/esp8266_smarthome/esp8266_smarthome.ino:91` | **Boot-strap HIGH:** `C4 10µF` DC-block + `R5/R6 2.2kΩ` + `C5 10nF` + `R4 10kΩ` pull-up; `IDLE = INPUT` |
| `PIN_BEDROOM_LIGHT` | **D4** | `GPIO2` | `LED_BR_D4 / J5` | `U2.5` | `firmware/esp8266_smarthome/esp8266_smarthome.ino:92` | **Boot-strap HIGH:** Active-LOW (`BEDROOM_LED_ACTIVE_LOW = true`, line 68) + `R2 220Ω` + `R7 10kΩ` pull-up |
| `PIN_KY037_DO` | **D5** | `GPIO14` | `KY037_D5 / J15` | `U2.8` | `firmware/esp8266_smarthome/esp8266_smarthome.ino:93` | 3.3V digital input (`RISING` interrupt, `debounce >= 400ms`, lines 73–74, 412) |
| `PIN_GARDEN_PUMP` | **D6** | `GPIO12` | `RLY1_PUMP_D6 / J7` | `U2.9` | `firmware/esp8266_smarthome/esp8266_smarthome.ino:94` | Active-HIGH (`PUMP_RELAY_ACTIVE_LOW = false`, line 70); soil hysteresis `<40% ON / >=70% OFF` |
| `PIN_SPEAKER_AMP` | **D7** | `GPIO13` | `RLY2_AMP_D7 / J9` | `U2.10` | `firmware/esp8266_smarthome/esp8266_smarthome.ino:95` | Active-HIGH (`SPEAKER_RELAY_ACTIVE_LOW = false`, line 71; Relay 2 Jumper=`H`); auto-off `1.5s` |
| `PIN_ALARM_SIREN` | **D8** | `GPIO15` | `BUZZ_D8 / J6` | `U2.11` | `firmware/esp8266_smarthome/esp8266_smarthome.ino:96` | **Boot-strap LOW:** Active-HIGH via `R10 1kΩ → Q1 S8050` (NPN low-side) + `R9 10kΩ` pull-down (silent at boot) + `D2 1N4007` flyback |
| `PIN_SOIL_MOISTURE` | **A0** | `ADC0` | `SOIL_A0 / J14` | `U1.1` | `firmware/esp8266_smarthome/esp8266_smarthome.ino:97` | 10-bit ADC0 (`0–3.3V` via NodeMCU divider) + `C7 100nF` filter; LM393 strictly powered by `+3V3` |

## 3. On-Board Type-1 Hub PCB Active, Passive & Indicator Components (`R1`–`R10`, `Q1`, `C1`–`C7`, `D1`–`D3`)

All 21 on-board active/passive/indicator components (`R1`–`R10`, `Q1`, `C1`–`C7`, `D1`–`D3`) are permanently soldered onto the `100.0 × 80.0 × 1.6 mm` single-layer FR4 Hub PCB (`hardware/kicad/smarthome_hub/smarthome_hub.kicad_pcb`, **49 total BOM footprints** = **45 soldered parts + 4 M3 mounting holes**: 21 active/passive/indicator components, `U1`–`U2` sockets, `J1`–`J15` connectors, `JP1`–`JP7` top-side wire jumpers, and `H1`–`H4` mounting holes):

| Ref | Value | Package / Pitch | Verified KiCad Nets | Electrical & Protection Role |
|---|---|---|---|---|
| `R1` | **220 Ω** | 1/4W Axial (DIN0207) | `D0_LED_LR ↔ LED_LR_A` | Current-limiting resistor for Living Room 5mm LED (J4, Active-HIGH) |
| `R2` | **220 Ω** | 1/4W Axial (DIN0207) | `+3V3 ↔ LED_BR_A` | Current-limiting resistor for Bedroom 5mm LED (J5, Boot-Safe Active-LOW) |
| `R3` | **10 kΩ** | 1/4W Axial (DIN0207) | `+3V3 ↔ D2_DHT11` | DHT11 1-wire DATA bus pull-up resistor (J13) |
| `R4` | **10 kΩ** | 1/4W Axial (DIN0207) | `+3V3 ↔ D3_AUDIO_PWM` | GPIO0 (D3) boot-safety pull-up resistor (keeps GPIO0 HIGH at reset) |
| `R5` | **2.2 kΩ** | 1/4W Axial (DIN0207) | `AUD_AC ↔ AUD_OUT` | Upper leg of RC audio attenuator divider feeding PAM8403 (J12) |
| `R6` | **2.2 kΩ** | 1/4W Axial (DIN0207) | `AUD_OUT ↔ GND` | Lower leg of RC audio attenuator divider (~50% level into PAM8403) |
| `R7` | **10 kΩ** | 1/4W Axial (DIN0207) | `+3V3 ↔ D4_LED_BR` | GPIO2 (D4) boot-safety pull-up resistor (keeps GPIO2 HIGH at reset) |
| `R8` | **1 kΩ** | 1/4W Axial (DIN0207) | `+5V ↔ PWR_LED_A` | Current-limiting resistor for on-board +5V power indicator LED D3 |
| `R9` | **10 kΩ** | 1/4W Axial (DIN0207) | `D8_BUZZER ↔ GND` | GPIO15 (D8) boot-safety pull-down resistor (keeps GPIO15 LOW & buzzer silent at boot) |
| `R10` | **1 kΩ** | 1/4W Axial (DIN0207) | `D8_BUZZER ↔ BUZZ_BASE` | Base current-limiting resistor for low-side NPN buzzer driver Q1 (~2.6 mA base drive from 3.3V GPIO15) |
| `Q1` | **S8050** | TO-92 Wide (E-B-C) | `E=GND, B=BUZZ_BASE, C=BUZZ_K` | Low-side NPN BJT driver (S8050 / 2N2222A, 0.7A) switching 5V TMB12A05 buzzer safely off GPIO15 |
| `C1` | **470 µF 16V** | Radial Ø8.0×P3.5mm | `+5V ↔ GND` | Bulk electrolytic decoupling for SG90 servo peak current & main +5V rail |
| `C2` | **470 µF 16V** | Radial Ø8.0×P3.5mm | `+5V ↔ GND` | Bulk electrolytic decoupling near J1/J2 for garden pump inrush stabilization |
| `C3` | **100 nF** | Ceramic Disc P5.0mm | `+5V ↔ GND` | High-frequency noise decoupling on main +5V power rail |
| `C4` | **10 µF 16V** | Radial Ø5.0×P3.5mm | `D3_AUDIO_PWM ↔ AUD_AC` | DC-blocking coupling capacitor isolating GPIO0 boot strap from PAM8403 input |
| `C5` | **10 nF** | Ceramic Disc P5.0mm | `AUD_OUT ↔ GND` | RC low-pass filter capacitor smoothing PWM chime carrier into PAM8403 |
| `C6` | **100 nF** | Ceramic Disc P5.0mm | `AMP_5V ↔ GND` | High-frequency decoupling on Relay-2-switched +5V rail feeding PAM8403 (J11) |
| `C7` | **100 nF** | Ceramic Disc P5.0mm | `A0_SOIL ↔ GND` | Analog low-pass noise filter on ESP8266 ADC0 soil moisture input (J14) |
| `D1` | **1N4007** | DO-41 P10.16mm | `K=PUMP_5V, A=GND` | Inductive flyback clamp diode across 3–6V garden pump motor (J2) |
| `D2` | **1N4007** | DO-41 P10.16mm | `K=+5V, A=BUZZ_K` | Inductive flyback protection diode across 5V Active Buzzer coil (J6.1 +5V ↔ J6.2 Q1 Collector) |
| `D3` | **LED_PWR_GRN** | 3mm Green LED (T-1) | `A=PWR_LED_A, K=GND` | On-board +5V power rail indicator LED (in series with R8 1kΩ) |

### 3.1 Complete Capacitor & Flyback Diode Protection Audit (`C1`–`C9` & `D1`–`D2`)

Audited against component datasheets (`Nichicon UVR/UHE`, `Murata RDE`, `Vishay 1N4007`, `Espressif ESP8266 Hardware Design Guidelines Sec. 2.1`, `AMS1117-3.3`, and `Diodes Inc. PAM8403`). `C1`–`C7` and `D1`–`D2` are soldered on the 1-layer Hub PCB (`0 ERC / 0 DRC`, `49 footprints`), while `C8` (`+3V3` 100nF HF bypass) and `C9` (`AMP_5V` 100µF 16V bulk electrolytic) are mounted off-board on header pins / breadboard so the home-etchable single-layer PCB preserves `>= 0.60 mm` copper clearance and 0 DRC violations.

| Ref | Kind | Value | Voltage / Rating | Polarity | Placement / Exact Pins | Nets (`+ ↔ -`) | Location | Role & Datasheet Reference |
|---|---|---|---|---|---|---|---|---|
| `C1` | Capacitor | **470µF** | `16V` | Có cực (+/-): chân (+) nối +5V, chân (-) vạch trắng nối GND | Hàn trên PCB Hub cạnh J1/J3 Servo (+5V ↔ GND, CP_Radial D8.0×P3.5mm) | `+5V ↔ GND` | On-Board PCB | Tụ hóa lọc nguồn chính +5V, cấp dòng xung đỉnh khi Servo SG90 quay để chống sụt áp reset ESP8266. *(Nichicon UVR/UHE 470µF 16V; TowerPro SG90 stall surge ~500–650mA)* |
| `C2` | Capacitor | **470µF** | `16V` | Có cực (+/-): chân (+) nối +5V, chân (-) vạch trắng nối GND | Hàn trên PCB Hub cạnh J1/J2 Bơm (+5V ↔ GND, CP_Radial D8.0×P3.5mm) | `+5V ↔ GND` | On-Board PCB | Tụ hóa lọc nguồn +5V gần ngõ máy bơm/rơ-le, ổn áp khi máy bơm mini 3–6V khởi động. *(Nichicon UVR/UHE 470µF 16V; Songle SRD-05VDC + DC pump inrush)* |
| `C3` | Capacitor | **100nF (104)** | `50V` | Không phân cực (tụ gốm) | Hàn trên PCB Hub cạnh U1.15 VIN (+5V ↔ GND, C_Disc D5.0×P5.0mm) | `+5V ↔ GND` | On-Board PCB | Tụ gốm lọc nhiễu cao tần trên đường nguồn +5V trước chân VIN NodeMCU. *(Murata RDE / Vishay K-series 100nF 50V Ceramic)* |
| `C4` | Capacitor | **10µF** | `16V` | Có cực (+/-): chân (+) về D3 (GPIO0), chân (-) về R5 (AUD_AC) | Hàn trên PCB Hub nối tiếp U2.4 (D3_AUDIO_PWM) → R5 (AUD_AC, CP_Radial D5.0×P3.5mm) | `D3_AUDIO_PWM ↔ AUD_AC` | On-Board PCB | Tụ hóa chặn thành phần một chiều (DC-block), cô lập chân boot-strap D3 (GPIO0) khỏi ngõ vào PAM8403. *(Diodes Inc. PAM8403 Datasheet (AC input coupling); ESP8266 GPIO0 boot-strap)* |
| `C5` | Capacitor | **10nF (103)** | `50V` | Không phân cực (tụ gốm) | Hàn trên PCB Hub tại nút J12.1 (AUD_OUT) ↔ GND (C_Disc D5.0×P5.0mm) | `AUD_OUT ↔ GND` | On-Board PCB | Tụ gốm lọc thông thấp RC (cùng R5/R6 2.2kΩ, fc ≈ 14.5 kHz) làm mịn tín hiệu PWM vào PAM8403. *(Murata RDE 10nF 50V; RC Low-Pass fc = 1/(2π·1.1kΩ·10nF))* |
| `C6` | Capacitor | **100nF (104)** | `50V` | Không phân cực (tụ gốm) | Hàn trên PCB Hub sát J11.1 (AMP_5V) ↔ J11.2 (GND) (C_Disc D5.0×P5.0mm) | `AMP_5V ↔ GND` | On-Board PCB | Tụ gốm lọc nhiễu cao tần trên nhánh nguồn +5V đóng cắt qua Rơ-le 2 cấp cho PAM8403. *(Diodes Inc. PAM8403 Datasheet (Power Supply Decoupling: 0.1µF HF bypass))* |
| `C7` | Capacitor | **100nF (104)** | `50V` | Không phân cực (tụ gốm) | Hàn trên PCB Hub sát J14.3 (A0_SOIL) ↔ GND (C_Disc D5.0×P5.0mm) | `A0_SOIL ↔ GND` | On-Board PCB | Tụ gốm lọc nhiễu tương tự cho chân ADC0 (A0) đọc cảm biến độ ẩm đất LM393. *(Espressif ESP8266 Technical Reference (ADC0 filtering); Murata 100nF 50V)* |
| `C8` | Capacitor | **100nF (104)** | `50V` | Không phân cực (tụ gốm) | Gắn ngoài bo trên Breadboard / chân header +3V3 ↔ GND sát NodeMCU 3V3 (U1.11/U2.6) và cảm biến J13/J14/J15 (kết hợp tụ Tantalum 10µF của AMS1117-3.3 có sẵn trên NodeMCU v2 Amica) | `+3V3 ↔ GND` | Off-Board (Header / Breadboard) | Tụ gốm tách nhiễu cao tần cho đường nguồn +3.3V nuôi ESP8266 và 3 cảm biến 3.3V (DHT11, LM393, KY-037). *(Espressif ESP8266 Hardware Design Guidelines Sec. 2.1; AMS1117-3.3 Datasheet (onboard 10µF tantalum on NodeMCU v2 Amica))* |
| `C9` | Capacitor | **100µF** | `16V` | Có cực (+/-): chân (+) nối AMP_5V (5V+), chân (-) vạch trắng nối GND (5V-) | Gắn ngoài bo tại chân header J11 (AMP_5V ↔ GND) hoặc trực tiếp trên pad 5V+/5V- của module PAM8403 (song song C6 100nF) | `AMP_5V ↔ GND` | Off-Board (Header / Breadboard) | Tụ hóa dự trữ năng lượng cho tầng khuếch đại Class-D PAM8403, giảm méo tiếng và sụt áp xung khi phát chuông loa 8Ω. *(Diodes Inc. PAM8403 Datasheet (Power Supply Decoupling: 100µF–470µF bulk + 0.1µF ceramic))* |
| `D1` | Flyback Diode | **1N4007** | `1000V / 1A` | Có cực (K/A): vạch bạc Cathode (K) nối PUMP_5V (+), Anode (A) nối GND (-) | Hàn trên PCB Hub mắc ngược song song ngõ ra bơm J2 (J2.1 PUMP_5V ↔ J2.2 GND, DO-41) | `PUMP_5V ↔ GND` | On-Board PCB | Diode dập xung ngược (Flyback) triệt xung cảm ứng khi Rơ-le 1 ngắt động cơ bơm 3–6V, bảo vệ tiếp điểm và ESP8266. *(Vishay 1N4007 Datasheet (VRRM=1000V, IF=1A, DO-41 inductive flyback clamp))* |
| `D2` | Flyback Diode | **1N4007** | `1000V / 1A` | Có cực (K/A): vạch bạc Cathode (K) nối +5V (J6.1), Anode (A) nối BUZZ_K / Q1.C (J6.2) | Hàn trên PCB Hub mắc ngược song song còi 5V tại J6 (J6.1 +5V ↔ J6.2 BUZZ_K / Q1 Collector, DO-41) | `+5V ↔ BUZZ_K` | On-Board PCB | Diode dập xung ngược (Flyback) bảo vệ transistor lái NPN Q1 (S8050) trước xung điện áp ngược từ cuộn dây còi TMB12A05. *(Vishay 1N4007 Datasheet; Unisonic S8050 VCEO=20V inductive load protection)* |

## 4. Standard Wire Color Legend (Consistent Across 2D Diagram, 3D Blender & Docs)

| Color | Hex Code | System Role / Assigned Signals |
|---|---|---|
| **Red** | `#DC2626` | Power (+5V / +3V3 / Switched 5V output) |
| **Black** | `#18181B` | Ground (GND) |
| **Orange** | `#EA580C` | Signal (SG90 D1, Buzzer D8, Relay2 NO, Probe B) |
| **Yellow** | `#CA8A04` | Signal (LED LR D0, KY-037 D5, Relay1 NO, Spk+, Probe A) |
| **Green** | `#16A34A` | Signal (Relay1 IN D6, Soil AO A0) |
| **Blue** | `#2563EB` | Signal (DHT11 DATA D2) |
| **Cyan** | `#0891B2` | Signal (Relay2 IN D7) |
| **Purple** | `#9333EA` | Signal (LED BR Anode via R2 220R) |
| **White** | `#94A3B8` | Signal (LED BR Cathode D4, Audio PWM Out D3) |
| **Brown** | `#78350F` | Differential Audio (PAM8403 L_OUT- to Speaker-, BTL NOT GND) |

## 5. Boot-Safety, Electrical Protection & Intentionally Unconnected (`[NC]`) Checklist

### Boot-Strap & Electrical Safety Verification
- [x] **`D3` (`GPIO0`) Audio PWM (`J12` → `PAM8403 L`):** Protected by on-board `R4` (`10 kΩ` pull-up to `+3V3`), `C4` (`10 µF 16V` DC-blocking cap), `R5/R6` (`2.2 kΩ / 2.2 kΩ` attenuator), and `C5` (`10 nF` RC filter). Firmware keeps `PIN_AUDIO_PWM` in `INPUT` (high-Z) during idle and returns to `INPUT` immediately after `noTone()` (`esp8266_smarthome.ino:166-184, 394`), preventing accidental UART flash mode entry.
- [x] **`D4` (`GPIO2`) Bedroom LED (`J5`):** Wired **Active-LOW** (`+3V3 → R2 220Ω → J5.1 → LED(+) → LED(-) → J5.2 → D4`) with on-board `R7` (`10 kΩ` pull-up). Firmware sets `BEDROOM_LED_ACTIVE_LOW = true` and pre-writes `HIGH` before `pinMode(OUTPUT)` (`esp8266_smarthome.ino:68, 396-397`), ensuring `GPIO2` stays `HIGH` during reset.
- [x] **`D8` (`GPIO15`) Alarm Buzzer (`J6`):** Driven low-side via on-board `R10` (`1 kΩ` base resistor) → `Q1` (`S8050` NPN, `E=GND`, `Buzzer(+)=+5V`, `Buzzer(-)=Q1 Collector`), with `R9` (`10 kΩ` pull-down from `D8` to `GND`) and `D2` (`1N4007` flyback diode across `J6.1–J6.2`). Firmware pre-writes `LOW` before `pinMode(OUTPUT)` (`esp8266_smarthome.ino:63, 399-400`), ensuring boot success and zero startup chirp.
- [x] **Strictly 3.3V-Only Sensor Modules (`LM393` on `J14`, `KY-037/038` on `J15`):** Both sensor boards are fed exclusively from the NodeMCU `+3V3` rail (NEVER `+5V`), guaranteeing `LM393 AO` stays safely within the ESP8266 `ADC0` input window and `KY-037 DO` outputs 3.3V-safe logic levels into `D5 (GPIO14)`.
- [x] **PAM8403 Bridge-Tied Load (BTL) Speaker Warning (`W28`, `W29`):** The Mini Speaker (`28 mm, 8 Ω, 0.5 W`) connects differentially across `PAM8403 L_OUT+` (Yellow) and `L_OUT-` (Brown). **NEVER tie `L_OUT-` to system `GND`** — doing so shorts the Class-D H-bridge output stage and damages the PAM8403 IC.
- [x] **Inductive Flyback & Power Rail Decoupling (`D1`, `D2`, `C1`–`C9`):** `D1` (`1N4007`, K=`PUMP_5V`, A=`GND`) clamps back-EMF across the 3–6V submersible pump (`J2`); `D2` (`1N4007`, K=`+5V`, A=`BUZZ_K`) clamps the active buzzer (`J6`); `C1` & `C2` (`470 µF 16V` each) absorb SG90 servo and pump startup current surges on `+5V`; `C3`/`C6`/`C7` (`100 nF 50V`) suppress HF noise on `+5V`, `AMP_5V`, and `A0_SOIL`; `C4` (`10 µF 16V`) & `C5` (`10 nF 50V`) perform DC-block + RC smoothing on `D3` audio; off-board `C8` (`100 nF 50V` across `+3V3 ↔ GND` at NodeMCU `U1.11/U2.6` & `J13`–`J15`, paired with NodeMCU v2 Amica onboard AMS1117-3.3 `10 µF` tantalum bulk cap) decouples `+3V3`; and off-board `C9` (`100 µF 16V` electrolytic across `AMP_5V ↔ GND` at `J11` / PAM8403 `5V+/5V-` parallel to `C6`) supplies Class-D audio current peaks.
- [x] **Relay 2 Trigger Jumper (`J9`):** Red opto-isolated 1-channel relay module jumper MUST be set to **`H` (High-Level Trigger)** to match `SPEAKER_RELAY_ACTIVE_LOW = false` (`esp8266_smarthome.ino:71`).
- [x] **Strict Scope Confirmation — Zero Legacy Hardware:** **NO fan**, **NO AC (220V mains)**, and **NO IR (`VS1838B` / `940nm LED`)** exist anywhere in the system. The entire system runs safely on low-voltage **5V DC / 3.3V DC**.

### Intentionally Unconnected (`[NC]`) Off-Board Module Pins
| Module | Pin | Status | Engineering Reason |
|---|---|---|---|
| Soil LM393 Comparator | `DO` | `[NC]` | Firmware reads continuous analog moisture percentage (`0–100%`) via `AO → A0` (`esp8266_smarthome.ino:568-569`) for software hysteresis (`<40% ON / >=70% OFF`). |
| KY-037 / KY-038 Sound Sensor | `AO` | `[NC]` | ESP8266 has only one ADC (`A0`, dedicated to Soil Moisture); clap/sound detection uses hardware comparator threshold `DO → D5` (`RISING` interrupt). |
| Relay 1 (Blue 5V, Pump) | `NC` (Screw) | `[NC]` | Pump switches via Normally-Open (`COM → NO`) path so pump stays safely OFF when unpowered or idle. |
| Relay 2 (Red Opto 5V, Amp) | `NC` (Screw) | `[NC]` | PAM8403 power switches via Normally-Open (`COM → NO`) path so amplifier is completely powered off between chimes. |
| PAM8403 Audio Amplifier | `R`, `R_OUT+`, `R_OUT-` | `[NC]` | Single mono speaker driven by Left channel (`L` input, `L_OUT+`/`L_OUT-` BTL output); Right channel unused. |

## 6. Physical Module Dimensions Summary (Matched to `DIMENSIONS_AUDIT.md`)

| Module ID | Component Name | Dimensions (L × W × H, mm) | Overall H (mm) | Datasheet / Source |
|---|---|---:|---:|---|
| `hub_pcb` | Central Hub DIY PCB (100x80mm, 1-Layer) | `100.0 × 80.0 × 1.6` | `17.3` | smarthome_hub.kicad_pcb |
| `nodemcu` | NodeMCU v2 Amica (ESP8266) | `48.3 × 25.4 × 1.6` | `7.1` | Amica DevKit v1.0 |
| `psu_5v` | 5V 2A Power Supply Terminal | `34.0 × 22.0 × 16.0` | `16.0` | External 5V/2A DC-005 + Screw Breakout |
| `sg90_servo` | SG90 Micro Servo | `22.8 × 12.2 × 22.5` | `31.0` | TowerPro SG90 (tab 32.2mm) |
| `led_living` | 5mm LED (Living Room, D0) | `5.8 × 5.8 × 8.6` | `8.6` | Kingbright WP7113 T-1 3/4 |
| `led_bedroom` | 5mm LED (Bedroom, D4) | `5.8 × 5.8 × 8.6` | `8.6` | Kingbright WP7113 T-1 3/4 |
| `relay1_pump` | Relay 1 (Blue 5V 1-ch, D6) | `50.0 × 26.0 × 18.5` | `18.5` | Songle SRD-05VDC-SL-C 1-ch |
| `pump_unit` | Mini Submersible Pump (3-6V) | `45.0 × 24.0 × 33.0` | `33.0` | Horizontal 3-6V DC Pump (nozzle OD 7.5mm) |
| `buzzer_alarm` | Active 5V Buzzer (D8) | `12.0 × 12.0 × 9.5` | `9.5` | TMB12A05 (pin pitch 7.6mm) |
| `relay2_speaker` | Relay 2 (Red Opto 5V, D7) | `50.0 × 26.0 × 18.5` | `18.5` | SRD-05VDC-SL-C + PC817 Opto (Jumper=H) |
| `pam8403_amp` | PAM8403 Mini Audio Amp | `21.0 × 18.0 × 3.1` | `3.1` | Diodes Inc PAM8403 bare green PCB |
| `speaker_mini` | Mini Speaker (28mm 8Ω 0.5W) | `28.0 × 28.0 × 5.2` | `5.2` | PUI Audio AS02808MR-R |
| `dht11_sensor` | DHT11 3-Pin Breakout (D2) | `28.0 × 14.0 × 7.1` | `7.1` | Aosong DHT11 (body 15.5x12.0x5.5mm) |
| `soil_lm393` | Soil LM393 Comparator (A0) | `32.0 × 14.0 × 12.1` | `12.1` | LM393 Soil Breakout (3296W pot) |
| `soil_probe` | YL-69 Soil Fork Probe | `60.0 × 20.0 × 1.6` | `1.6` | YL-69 2-Prong Probe |
| `ky037_sound` | KY-037/038 Sound Sensor (D5) | `35.0 × 15.0 × 13.1` | `13.1` | Joy-IT KY-038 (ECM-9767 mic Ø9.7x6.7mm) |
