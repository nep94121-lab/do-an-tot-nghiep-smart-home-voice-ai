"""Single Source of Truth (SSOT) hardware wiring contract for Smart Home Voice AI.

Maps every hub PCB connector pin (J1..J15) and NodeMCU socket (U1, U2) on the
Type-1 Central Hub PCB (`hardware/kicad/smarthome_hub/smarthome_hub.kicad_pcb`)
to every off-board module pin, wire color, NodeMCU Dx/GPIO, KiCad net name,
datasheet dimensions (`docs/phan_cung/DIMENSIONS_AUDIT.md`), and firmware line
reference (`firmware/esp8266_smarthome/esp8266_smarthome.ino`).

Zero fan, zero AC, zero IR anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Wire Color Palette (consistent across KiCad notes, 3D Blender, 2D SVG, Docs)
# Rule: Red = VCC / +5V / +3V3 power rails; Black = GND; distinct colors = signals
# ---------------------------------------------------------------------------
WIRE_COLORS: dict[str, dict[str, object]] = {
    "Red":    {"hex": "#DC2626", "rgb": (0.76, 0.08, 0.08), "role": "Power (+5V / +3V3 / Switched 5V output)"},
    "Black":  {"hex": "#18181B", "rgb": (0.06, 0.06, 0.07), "role": "Ground (GND)"},
    "Orange": {"hex": "#EA580C", "rgb": (0.90, 0.36, 0.04), "role": "Signal (SG90 D1, Buzzer D8, Relay2 NO, Probe B)"},
    "Yellow": {"hex": "#CA8A04", "rgb": (0.86, 0.68, 0.05), "role": "Signal (LED LR D0, KY-037 D5, Relay1 NO, Spk+, Probe A)"},
    "Green":  {"hex": "#16A34A", "rgb": (0.08, 0.60, 0.18), "role": "Signal (Relay1 IN D6, Soil AO A0)"},
    "Blue":   {"hex": "#2563EB", "rgb": (0.10, 0.34, 0.86), "role": "Signal (DHT11 DATA D2)"},
    "Cyan":   {"hex": "#0891B2", "rgb": (0.04, 0.56, 0.72), "role": "Signal (Relay2 IN D7)"},
    "Purple": {"hex": "#9333EA", "rgb": (0.54, 0.16, 0.82), "role": "Signal (LED BR Anode via R2 220R)"},
    "White":  {"hex": "#94A3B8", "rgb": (0.86, 0.88, 0.90), "role": "Signal (LED BR Cathode D4, Audio PWM Out D3)"},
    "Brown":  {"hex": "#78350F", "rgb": (0.42, 0.20, 0.08), "role": "Differential Audio (PAM8403 L_OUT- to Speaker-, BTL NOT GND)"},
}


@dataclass(frozen=True)
class HubConnector:
    ref: str
    value: str
    kind: str  # "screw_508" or "header_254"
    edge: str  # "left", "top", "right", "bottom", "left_inner"
    rot_deg: float
    # Exact pin coordinates in PCB local mm (origin = PCB top-left 0..100, 0..80)
    # Matching KiCad board origin (50.0, 45.0) for 100x80mm 1-layer DIY hub PCB
    pins: tuple[tuple[str, float, float, str], ...]  # (pin_num, rel_x, rel_y, net)


HUB_CONNECTORS: tuple[HubConnector, ...] = (
    HubConnector(
        ref="J1", value="PWR_5V_IN", kind="screw_508", edge="left", rot_deg=-90.0,
        pins=(
            ("1", 9.00, 53.50, "+5V"),
            ("2", 9.00, 58.58, "GND"),
        ),
    ),
    HubConnector(
        ref="J2", value="PUMP_OUT", kind="screw_508", edge="left", rot_deg=-90.0,
        pins=(
            ("1", 9.00, 22.00, "PUMP_5V"),
            ("2", 9.00, 27.08, "GND"),
        ),
    ),
    HubConnector(
        ref="J3", value="SERVO_D1", kind="header_254", edge="top", rot_deg=90.0,
        pins=(
            ("1", 58.00, 9.00, "D1_SERVO"),
            ("2", 60.54, 9.00, "+5V"),
            ("3", 63.08, 9.00, "GND"),
        ),
    ),
    HubConnector(
        ref="J4", value="LED_LR_D0", kind="header_254", edge="top", rot_deg=90.0,
        pins=(
            ("1", 40.50, 9.00, "LED_LR_A"),
            ("2", 43.04, 9.00, "GND"),
        ),
    ),
    HubConnector(
        ref="J5", value="LED_BR_D4", kind="header_254", edge="right", rot_deg=0.0,
        pins=(
            ("1", 91.00, 18.00, "LED_BR_A"),
            ("2", 91.00, 20.54, "D4_LED_BR"),
        ),
    ),
    HubConnector(
        ref="J6", value="BUZZ_D8", kind="header_254", edge="bottom", rot_deg=-90.0,
        pins=(
            ("1", 85.00, 72.00, "+5V"),
            ("2", 82.46, 72.00, "BUZZ_K"),
        ),
    ),
    HubConnector(
        ref="J7", value="RLY1_PUMP_D6", kind="header_254", edge="right", rot_deg=180.0,
        pins=(
            ("1", 91.00, 51.58, "+5V"),
            ("2", 91.00, 49.04, "GND"),
            ("3", 91.00, 46.50, "D6_RLY1_PUMP"),
        ),
    ),
    HubConnector(
        ref="J8", value="RLY1_SW", kind="header_254", edge="left_inner", rot_deg=180.0,
        pins=(
            ("1", 23.50, 24.54, "+5V"),
            ("2", 23.50, 22.00, "PUMP_5V"),
        ),
    ),
    HubConnector(
        ref="J9", value="RLY2_AMP_D7", kind="header_254", edge="right", rot_deg=180.0,
        pins=(
            ("1", 91.00, 64.58, "+5V"),
            ("2", 91.00, 62.04, "GND"),
            ("3", 91.00, 59.50, "D7_RLY2_AMP"),
        ),
    ),
    HubConnector(
        ref="J10", value="RLY2_SW", kind="header_254", edge="bottom", rot_deg=90.0,
        pins=(
            ("1", 16.50, 71.50, "+5V"),
            ("2", 19.04, 71.50, "AMP_5V"),
        ),
    ),
    HubConnector(
        ref="J11", value="PAM8403_PWR", kind="header_254", edge="bottom", rot_deg=90.0,
        pins=(
            ("1", 29.00, 71.50, "AMP_5V"),
            ("2", 31.54, 71.50, "GND"),
        ),
    ),
    HubConnector(
        ref="J12", value="AUDIO_D3", kind="header_254", edge="bottom", rot_deg=90.0,
        pins=(
            ("1", 53.50, 71.50, "AUD_OUT"),
            ("2", 56.04, 71.50, "GND"),
        ),
    ),
    HubConnector(
        ref="J13", value="DHT11_D2", kind="header_254", edge="top", rot_deg=-90.0,
        pins=(
            ("1", 81.58, 7.50, "+3V3"),
            ("2", 79.04, 7.50, "D2_DHT11"),
            ("3", 76.50, 7.50, "GND"),
        ),
    ),
    HubConnector(
        ref="J14", value="SOIL_A0", kind="header_254", edge="top", rot_deg=90.0,
        pins=(
            ("1", 16.50, 9.00, "+3V3"),
            ("2", 19.04, 9.00, "GND"),
            ("3", 21.58, 9.00, "A0_SOIL"),
        ),
    ),
    HubConnector(
        ref="J15", value="KY037_D5", kind="header_254", edge="right", rot_deg=0.0,
        pins=(
            ("1", 91.00, 33.00, "+3V3"),
            ("2", 91.00, 35.54, "GND"),
            ("3", 91.00, 38.08, "D5_MIC_DO"),
        ),
    ),
)

HUB_CONNECTOR_MAP: dict[str, HubConnector] = {c.ref: c for c in HUB_CONNECTORS}


@dataclass(frozen=True)
class WireEntry:
    wire_id: str
    group: str
    hub_ref: str       # e.g. "J3" or "PAM8403" / "LM393" for off-board module-to-module links
    hub_pin: str       # e.g. "1" or "L_OUT+"
    hub_label: str     # e.g. "J3.1 (SERVO_D1)"
    color: str         # Key in WIRE_COLORS
    module_id: str     # Canonical off-board module ID
    module_name: str   # Human-readable module name
    module_pin: str    # Pin label on the off-board module
    nodemcu_pin: str   # e.g. "D1", "A0", "VIN (+5V)", "3V3", "GND", "Switched +5V"
    gpio: str          # e.g. "GPIO5", "ADC0", "Power", "Ground", "BTL Audio"
    net: str           # Exact KiCad net name (or off-board net name)
    fw_ref: str        # File:line in firmware/esp8266_smarthome/esp8266_smarthome.ino
    wire_type: str     # "Dupont F-F", "Screw-to-Wire", "Dupont F-M", "Soldered Pair"
    notes: str


# Every single physical plug-in wire in the system (36 Hub->Module wires + 4 Off-board inter-module wires = 40 wires)
WIRING_TABLE: tuple[WireEntry, ...] = (
    # --- Power Input (J1 -> 5V 2A External PSU) ---
    WireEntry("W01", "Power Supply", "J1", "1", "J1.1 (PWR_5V_IN)", "Red",
              "psu_5v", "5V 2A External Supply", "+5V", "VIN (U1.15)", "Power (+5V)", "+5V",
              "esp8266_smarthome.ino:15-16", "Screw Terminal 22AWG",
              "Main +5V rail; on-board C1/C2 (470uF 16V) + C3 (100nF) bulk decoupling + D3 power LED"),
    WireEntry("W02", "Power Supply", "J1", "2", "J1.2 (PWR_5V_IN)", "Black",
              "psu_5v", "5V 2A External Supply", "GND", "GND (U1.10/14, U2.7/14)", "Ground", "GND",
              "esp8266_smarthome.ino:15-16", "Screw Terminal 22AWG",
              "Common system ground reference shared with NodeMCU and all modules"),

    # --- Device 1: Main Door Servo SG90 (J3 -> SG90) ---
    WireEntry("W03", "Main Door (SG90)", "J3", "1", "J3.1 (SERVO_D1)", "Orange",
              "sg90_servo", "SG90 Micro Servo", "PWM (Orange)", "D1 (U2.2)", "GPIO5", "D1_SERVO",
              "esp8266_smarthome.ino:56", "Dupont 1x3 F-M",
              "50Hz PWM control: 0 deg closed / 90 deg open (main_door)"),
    WireEntry("W04", "Main Door (SG90)", "J3", "2", "J3.2 (SERVO_D1)", "Red",
              "sg90_servo", "SG90 Micro Servo", "VCC (Red)", "VIN (U1.15)", "Power (+5V)", "+5V",
              "esp8266_smarthome.ino:56", "Dupont 1x3 F-M",
              "+5V servo supply decoupled by on-board C1 470uF 16V"),
    WireEntry("W05", "Main Door (SG90)", "J3", "3", "J3.3 (SERVO_D1)", "Black",
              "sg90_servo", "SG90 Micro Servo", "GND (Brown)", "GND", "Ground", "GND",
              "esp8266_smarthome.ino:56", "Dupont 1x3 F-M",
              "Common GND (connects to SG90 brown pigtail wire)"),

    # --- Device 2: Living Room 5mm LED (J4 -> LED_LR) ---
    WireEntry("W06", "Living Room LED", "J4", "1", "J4.1 (LED_LR_D0)", "Yellow",
              "led_living", "5mm LED (Living Room)", "Anode (+)", "D0 (U2.1) via R1 220R", "GPIO16", "LED_LR_A",
              "esp8266_smarthome.ino:55", "Dupont 1x2 F-F",
              "Active-HIGH through on-board 220R series resistor R1; also enroll_blink"),
    WireEntry("W07", "Living Room LED", "J4", "2", "J4.2 (LED_LR_D0)", "Black",
              "led_living", "5mm LED (Living Room)", "Cathode (-)", "GND", "Ground", "GND",
              "esp8266_smarthome.ino:55", "Dupont 1x2 F-F",
              "LED cathode return to common GND"),

    # --- Device 3: Bedroom 5mm LED (J5 -> LED_BR, Boot-Safe Active-LOW) ---
    WireEntry("W08", "Bedroom LED", "J5", "1", "J5.1 (LED_BR_D4)", "Purple",
              "led_bedroom", "5mm LED (Bedroom)", "Anode (+)", "+3V3 via R2 220R", "Power (+3V3 limited)", "LED_BR_A",
              "esp8266_smarthome.ino:59,68", "Dupont 1x2 F-F",
              "Current-limited +3.3V via on-board R2 220R for boot-safe Active-LOW LED"),
    WireEntry("W09", "Bedroom LED", "J5", "2", "J5.2 (LED_BR_D4)", "White",
              "led_bedroom", "5mm LED (Bedroom)", "Cathode (-)", "D4 (U2.5)", "GPIO2", "D4_LED_BR",
              "esp8266_smarthome.ino:59,68", "Dupont 1x2 F-F",
              "Active-LOW sink (BEDROOM_LED_ACTIVE_LOW=true); on-board R7 10k pull-up keeps GPIO2 HIGH at boot"),

    # --- Device 4: Garden Pump (J7 -> Relay1 Coil, J8 -> Relay1 Contacts, J2 -> Pump) ---
    WireEntry("W10", "Garden Pump (Relay 1)", "J7", "1", "J7.1 (RLY1_PUMP_D6)", "Red",
              "relay1_pump", "Relay 1 (Blue 5V 1-ch)", "VCC", "VIN (U1.15)", "Power (+5V)", "+5V",
              "esp8266_smarthome.ino:61,70", "Dupont 1x3 F-F",
              "5V coil power for blue 1-channel Songle SRD-05VDC-SL-C relay module"),
    WireEntry("W11", "Garden Pump (Relay 1)", "J7", "2", "J7.2 (RLY1_PUMP_D6)", "Black",
              "relay1_pump", "Relay 1 (Blue 5V 1-ch)", "GND", "GND", "Ground", "GND",
              "esp8266_smarthome.ino:61,70", "Dupont 1x3 F-F",
              "Relay 1 module logic/coil ground"),
    WireEntry("W12", "Garden Pump (Relay 1)", "J7", "3", "J7.3 (RLY1_PUMP_D6)", "Green",
              "relay1_pump", "Relay 1 (Blue 5V 1-ch)", "IN", "D6 (U2.9)", "GPIO12", "D6_RLY1_PUMP",
              "esp8266_smarthome.ino:61,70", "Dupont 1x3 F-F",
              "Relay 1 trigger input (PUMP_RELAY_ACTIVE_LOW=false, active-HIGH)"),
    WireEntry("W13", "Garden Pump (Relay 1)", "J8", "1", "J8.1 (RLY1_SW)", "Red",
              "relay1_pump", "Relay 1 (Blue 5V 1-ch)", "COM (Screw)", "VIN (U1.15)", "Power (+5V)", "+5V",
              "esp8266_smarthome.ino:61", "Dupont F-Pin (22AWG)",
              "Feeds +5V power rail into Relay 1 COM screw terminal"),
    WireEntry("W14", "Garden Pump (Relay 1)", "J8", "2", "J8.2 (RLY1_SW)", "Yellow",
              "relay1_pump", "Relay 1 (Blue 5V 1-ch)", "NO (Screw)", "Switched +5V -> J2.1", "Switched +5V", "PUMP_5V",
              "esp8266_smarthome.ino:61", "Dupont F-Pin (22AWG)",
              "Switched +5V return from Relay 1 NO to Hub PCB D1 (1N4007 flyback) & J2.1"),
    WireEntry("W15", "Garden Pump (Motor)", "J2", "1", "J2.1 (PUMP_OUT)", "Red",
              "pump_unit", "Mini Submersible Pump (3-6V)", "Pump + (Red)", "Switched +5V (via RLY1)", "Switched +5V", "PUMP_5V",
              "esp8266_smarthome.ino:61,572", "Screw Terminal 22AWG",
              "Switched +5V to pump motor; protected by on-board D1 1N4007 flyback & C2 470uF 16V"),
    WireEntry("W16", "Garden Pump (Motor)", "J2", "2", "J2.2 (PUMP_OUT)", "Black",
              "pump_unit", "Mini Submersible Pump (3-6V)", "Pump - (Black)", "GND", "Ground", "GND",
              "esp8266_smarthome.ino:61,572", "Screw Terminal 22AWG",
              "Pump motor return to GND (anode of on-board D1 1N4007)"),

    # --- Device 5: Alarm Siren Buzzer (J6 -> Buzzer, low-side NPN driver Q1 S8050 + R10 1k) ---
    WireEntry("W17", "Alarm Siren (Buzzer)", "J6", "1", "J6.1 (BUZZ_D8)", "Red",
              "buzzer_alarm", "Active 5V Buzzer (TMB12A05)", "Buzzer (+)", "VIN (+5V)", "Power (+5V)", "+5V",
              "esp8266_smarthome.ino:63,399", "Dupont 1x2 F-F",
              "+5V supply to TMB12A05 buzzer anode; protected by on-board D2 1N4007 flyback across J6.1-J6.2"),
    WireEntry("W18", "Alarm Siren (Buzzer)", "J6", "2", "J6.2 (BUZZ_D8)", "Orange",
              "buzzer_alarm", "Active 5V Buzzer (TMB12A05)", "Buzzer (-)", "D8 (U2.11) via Q1 S8050", "GPIO15 (NPN low-side)", "BUZZ_K",
              "esp8266_smarthome.ino:63,399", "Dupont 1x2 F-F",
              "Low-side switched by on-board Q1 (S8050 NPN) + R10 1k base resistor; R9 10k pull-down keeps GPIO15 LOW at boot"),

    # --- Device 6: Speaker Amp (J9/J10 -> Relay 2, J11/J12 -> PAM8403, PAM8403 -> Speaker) ---
    WireEntry("W19", "Speaker Amp (Relay 2)", "J9", "1", "J9.1 (RLY2_AMP_D7)", "Red",
              "relay2_speaker", "Relay 2 (Red Opto 5V, Jmp=H)", "DC+", "VIN (U1.15)", "Power (+5V)", "+5V",
              "esp8266_smarthome.ino:62,71", "Dupont 1x3 F-F",
              "5V coil/opto supply for red opto-isolated 1-ch relay module (jumper set to H)"),
    WireEntry("W20", "Speaker Amp (Relay 2)", "J9", "2", "J9.2 (RLY2_AMP_D7)", "Black",
              "relay2_speaker", "Relay 2 (Red Opto 5V, Jmp=H)", "DC-", "GND", "Ground", "GND",
              "esp8266_smarthome.ino:62,71", "Dupont 1x3 F-F",
              "Relay 2 module ground"),
    WireEntry("W21", "Speaker Amp (Relay 2)", "J9", "3", "J9.3 (RLY2_AMP_D7)", "Cyan",
              "relay2_speaker", "Relay 2 (Red Opto 5V, Jmp=H)", "IN", "D7 (U2.10)", "GPIO13", "D7_RLY2_AMP",
              "esp8266_smarthome.ino:62,71", "Dupont 1x3 F-F",
              "Active-HIGH trigger (SPEAKER_RELAY_ACTIVE_LOW=false); auto-off 1.5s after chime"),
    WireEntry("W22", "Speaker Amp (Relay 2)", "J10", "1", "J10.1 (RLY2_SW)", "Red",
              "relay2_speaker", "Relay 2 (Red Opto 5V, Jmp=H)", "COM (Screw)", "VIN (U1.15)", "Power (+5V)", "+5V",
              "esp8266_smarthome.ino:62", "Dupont F-Pin",
              "Feeds +5V rail into Relay 2 COM screw terminal"),
    WireEntry("W23", "Speaker Amp (Relay 2)", "J10", "2", "J10.2 (RLY2_SW)", "Orange",
              "relay2_speaker", "Relay 2 (Red Opto 5V, Jmp=H)", "NO (Screw)", "Switched +5V -> J11.1", "Switched +5V", "AMP_5V",
              "esp8266_smarthome.ino:62", "Dupont F-Pin",
              "Switched +5V return from Relay 2 NO to Hub C6 (100nF) & J11.1"),
    WireEntry("W24", "Speaker Amp (PAM8403)", "J11", "1", "J11.1 (PAM8403_PWR)", "Red",
              "pam8403_amp", "PAM8403 Audio Amplifier", "5V+", "Switched +5V (via RLY2)", "Switched +5V", "AMP_5V",
              "esp8266_smarthome.ino:62,163", "Dupont 1x2 F-F",
              "Relay-switched +5V supply to PAM8403 (decoupled by on-board C6 100nF)"),
    WireEntry("W25", "Speaker Amp (PAM8403)", "J11", "2", "J11.2 (PAM8403_PWR)", "Black",
              "pam8403_amp", "PAM8403 Audio Amplifier", "5V-", "GND", "Ground", "GND",
              "esp8266_smarthome.ino:62,163", "Dupont 1x2 F-F",
              "PAM8403 power ground"),
    WireEntry("W26", "Speaker Amp (Audio PWM)", "J12", "1", "J12.1 (AUDIO_D3)", "White",
              "pam8403_amp", "PAM8403 Audio Amplifier", "L (Audio In)", "D3 (U2.4) via C4/R5/R6/C5", "GPIO0", "AUD_OUT",
              "esp8266_smarthome.ino:58,166-184", "Dupont 1x2 F-F",
              "DC-blocked (C4 10uF) & RC-attenuated (R5/R6 2.2k, C5 10nF) audio; R4 10k pull-up + IDLE=INPUT for boot safety"),
    WireEntry("W27", "Speaker Amp (Audio PWM)", "J12", "2", "J12.2 (AUDIO_D3)", "Black",
              "pam8403_amp", "PAM8403 Audio Amplifier", "GND (Audio ⊥)", "GND", "Ground", "GND",
              "esp8266_smarthome.ino:58", "Dupont 1x2 F-F",
              "Audio input signal ground reference"),
    WireEntry("W28", "Speaker Output (BTL)", "PAM8403", "L_OUT+", "PAM8403 L_OUT+", "Yellow",
              "speaker_mini", "Mini Speaker (28mm 8Ω 0.5W)", "SPK +", "Off-board (PAM8403 BTL)", "BTL Audio +", "SPK_BTL_P",
              "esp8266_smarthome.ino:16,58", "2-Wire Pair",
              "Bridge-Tied Load (BTL) positive output; DO NOT short to GND"),
    WireEntry("W29", "Speaker Output (BTL)", "PAM8403", "L_OUT-", "PAM8403 L_OUT-", "Brown",
              "speaker_mini", "Mini Speaker (28mm 8Ω 0.5W)", "SPK -", "Off-board (PAM8403 BTL)", "BTL Audio -", "SPK_BTL_N",
              "esp8266_smarthome.ino:16,58", "2-Wire Pair",
              "Bridge-Tied Load (BTL) negative output; NEVER tie to GND"),

    # --- Sensor 1: DHT11 Temp & Humidity (J13 -> DHT11) ---
    WireEntry("W30", "DHT11 Sensor", "J13", "1", "J13.1 (DHT11_D2)", "Red",
              "dht11_sensor", "DHT11 3-Pin Breakout", "VCC (+)", "3V3 (U1.11/U2.6)", "Power (+3V3)", "+3V3",
              "esp8266_smarthome.ino:57,83", "Dupont 1x3 F-F",
              "3.3V sensor supply"),
    WireEntry("W31", "DHT11 Sensor", "J13", "2", "J13.2 (DHT11_D2)", "Blue",
              "dht11_sensor", "DHT11 3-Pin Breakout", "DATA (OUT)", "D2 (U2.3)", "GPIO4", "D2_DHT11",
              "esp8266_smarthome.ino:57,83,544", "Dupont 1x3 F-F",
              "1-wire data bus with on-board R3 10k pull-up to +3V3"),
    WireEntry("W32", "DHT11 Sensor", "J13", "3", "J13.3 (DHT11_D2)", "Black",
              "dht11_sensor", "DHT11 3-Pin Breakout", "GND (-)", "GND", "Ground", "GND",
              "esp8266_smarthome.ino:57", "Dupont 1x3 F-F",
              "DHT11 sensor ground"),

    # --- Sensor 2: Soil Moisture LM393 + YL-69 Probe (J14 -> LM393 -> YL-69) ---
    WireEntry("W33", "Soil Sensor (LM393)", "J14", "1", "J14.1 (SOIL_A0)", "Red",
              "soil_lm393", "Soil LM393 Comparator Module", "VCC", "3V3 (U1.11/U2.6)", "Power (+3V3)", "+3V3",
              "esp8266_smarthome.ino:18,64", "Dupont 1x3 F-F",
              "STRICTLY 3.3V (never 5V) so AO stays within ESP8266 ADC0 safe range"),
    WireEntry("W34", "Soil Sensor (LM393)", "J14", "2", "J14.2 (SOIL_A0)", "Black",
              "soil_lm393", "Soil LM393 Comparator Module", "GND", "GND", "Ground", "GND",
              "esp8266_smarthome.ino:18,64", "Dupont 1x3 F-F",
              "Soil sensor ground (LM393 DO pin intentionally left NC / unconnected)"),
    WireEntry("W35", "Soil Sensor (LM393)", "J14", "3", "J14.3 (SOIL_A0)", "Green",
              "soil_lm393", "Soil LM393 Comparator Module", "AO", "A0 (U1.1)", "ADC0", "A0_SOIL",
              "esp8266_smarthome.ino:64,568", "Dupont 1x3 F-F",
              "Analog moisture output (filtered by on-board C7 100nF); <40% ON / >=70% OFF"),
    WireEntry("W36", "Soil Sensor (Probe)", "LM393", "P1", "LM393 Probe +", "Yellow",
              "soil_probe", "YL-69 Soil Fork Probe", "Prong A", "Off-board (LM393)", "Analog Probe", "SOIL_PROBE_A",
              "esp8266_smarthome.ino:18,64", "Dupont 1x2 F-F",
              "2-wire fork probe pair from LM393 2-pin header to YL-69 resistive prongs"),
    WireEntry("W37", "Soil Sensor (Probe)", "LM393", "P2", "LM393 Probe -", "Orange",
              "soil_probe", "YL-69 Soil Fork Probe", "Prong B", "Off-board (LM393)", "Analog Probe", "SOIL_PROBE_B",
              "esp8266_smarthome.ino:18,64", "Dupont 1x2 F-F",
              "2-wire fork probe pair from LM393 2-pin header to YL-69 resistive prongs"),

    # --- Sensor 3: KY-037 / KY-038 Sound Sensor (J15 -> KY-037) ---
    WireEntry("W38", "Sound Sensor (KY-037)", "J15", "1", "J15.1 (KY037_D5)", "Red",
              "ky037_sound", "KY-037 / KY-038 Sound Module", "+ (VCC)", "3V3 (U1.11/U2.6)", "Power (+3V3)", "+3V3",
              "esp8266_smarthome.ino:14,60", "Dupont 1x3 F-F",
              "STRICTLY 3.3V so DO logic HIGH matches ESP8266 3.3V GPIO14"),
    WireEntry("W39", "Sound Sensor (KY-037)", "J15", "2", "J15.2 (KY037_D5)", "Black",
              "ky037_sound", "KY-037 / KY-038 Sound Module", "G (GND)", "GND", "Ground", "GND",
              "esp8266_smarthome.ino:14,60", "Dupont 1x3 F-F",
              "KY-037 ground (AO pin intentionally left NC / unconnected)"),
    WireEntry("W40", "Sound Sensor (KY-037)", "J15", "3", "J15.3 (KY037_D5)", "Yellow",
              "ky037_sound", "KY-037 / KY-038 Sound Module", "DO", "D5 (U2.8)", "GPIO14", "D5_MIC_DO",
              "esp8266_smarthome.ino:60,412", "Dupont 1x3 F-F",
              "Digital clap/loud-sound interrupt (RISING edge, debounce >= 400ms)"),
)


# Datasheet dimensions (exact match to docs/phan_cung/DIMENSIONS_AUDIT.md)
MODULE_DIMENSIONS_MM: dict[str, dict[str, object]] = {
    "hub_pcb":        {"label": "Central Hub DIY PCB (100x80mm, 1-Layer)", "dims_mm": (100.0, 80.0, 1.6), "overall_h_mm": 17.3, "source": "smarthome_hub.kicad_pcb"},
    "nodemcu":        {"label": "NodeMCU v2 Amica (ESP8266)",     "dims_mm": (48.26, 25.4, 1.6), "overall_h_mm": 7.14,  "source": "Amica DevKit v1.0"},
    "psu_5v":         {"label": "5V 2A Power Supply Terminal",    "dims_mm": (34.0, 22.0, 16.0), "overall_h_mm": 16.0,  "source": "External 5V/2A DC-005 + Screw Breakout"},
    "sg90_servo":     {"label": "SG90 Micro Servo",               "dims_mm": (22.8, 12.2, 22.5), "overall_h_mm": 31.0,  "source": "TowerPro SG90 (tab 32.2mm)"},
    "led_living":     {"label": "5mm LED (Living Room, D0)",      "dims_mm": (5.8, 5.8, 8.6),    "overall_h_mm": 8.6,   "source": "Kingbright WP7113 T-1 3/4"},
    "led_bedroom":    {"label": "5mm LED (Bedroom, D4)",          "dims_mm": (5.8, 5.8, 8.6),    "overall_h_mm": 8.6,   "source": "Kingbright WP7113 T-1 3/4"},
    "relay1_pump":    {"label": "Relay 1 (Blue 5V 1-ch, D6)",     "dims_mm": (50.0, 26.0, 18.5), "overall_h_mm": 18.5,  "source": "Songle SRD-05VDC-SL-C 1-ch"},
    "pump_unit":      {"label": "Mini Submersible Pump (3-6V)",   "dims_mm": (45.0, 24.0, 33.0), "overall_h_mm": 33.0,  "source": "Horizontal 3-6V DC Pump (nozzle OD 7.5mm)"},
    "buzzer_alarm":   {"label": "Active 5V Buzzer (D8)",          "dims_mm": (12.0, 12.0, 9.5),  "overall_h_mm": 9.5,   "source": "TMB12A05 (pin pitch 7.6mm)"},
    "relay2_speaker": {"label": "Relay 2 (Red Opto 5V, D7)",      "dims_mm": (50.0, 26.0, 18.5), "overall_h_mm": 18.5,  "source": "SRD-05VDC-SL-C + PC817 Opto (Jumper=H)"},
    "pam8403_amp":    {"label": "PAM8403 Mini Audio Amp",         "dims_mm": (21.0, 18.0, 3.1),  "overall_h_mm": 3.1,   "source": "Diodes Inc PAM8403 bare green PCB"},
    "speaker_mini":   {"label": "Mini Speaker (28mm 8Ω 0.5W)",    "dims_mm": (28.0, 28.0, 5.2),  "overall_h_mm": 5.2,   "source": "PUI Audio AS02808MR-R"},
    "dht11_sensor":   {"label": "DHT11 3-Pin Breakout (D2)",      "dims_mm": (28.0, 14.0, 7.1),  "overall_h_mm": 7.1,   "source": "Aosong DHT11 (body 15.5x12.0x5.5mm)"},
    "soil_lm393":     {"label": "Soil LM393 Comparator (A0)",     "dims_mm": (32.0, 14.0, 12.1), "overall_h_mm": 12.1,  "source": "LM393 Soil Breakout (3296W pot)"},
    "soil_probe":     {"label": "YL-69 Soil Fork Probe",          "dims_mm": (60.0, 20.0, 1.6),  "overall_h_mm": 1.6,   "source": "YL-69 2-Prong Probe"},
    "ky037_sound":    {"label": "KY-037/038 Sound Sensor (D5)",   "dims_mm": (35.0, 15.0, 13.1), "overall_h_mm": 13.1,  "source": "Joy-IT KY-038 (ECM-9767 mic Ø9.7x6.7mm)"},
}

# Locked 10-pin firmware table for deterministic cross-checking
FIRMWARE_PIN_CONTRACT: dict[str, tuple[str, int, str]] = {
    "PIN_LIVING_LIGHT":    ("D0", 16, "LED_LR_D0 / J4"),
    "PIN_MAIN_DOOR_SERVO": ("D1", 5,  "SERVO_D1 / J3"),
    "PIN_DHT11":           ("D2", 4,  "DHT11_D2 / J13"),
    "PIN_AUDIO_PWM":       ("D3", 0,  "AUDIO_D3 / J12"),
    "PIN_BEDROOM_LIGHT":   ("D4", 2,  "LED_BR_D4 / J5"),
    "PIN_KY037_DO":        ("D5", 14, "KY037_D5 / J15"),
    "PIN_GARDEN_PUMP":     ("D6", 12, "RLY1_PUMP_D6 / J7"),
    "PIN_SPEAKER_AMP":     ("D7", 13, "RLY2_AMP_D7 / J9"),
    "PIN_ALARM_SIREN":     ("D8", 15, "BUZZ_D8 / J6"),
    "PIN_SOIL_MOISTURE":   ("A0", -1, "SOIL_A0 / J14"),
}
