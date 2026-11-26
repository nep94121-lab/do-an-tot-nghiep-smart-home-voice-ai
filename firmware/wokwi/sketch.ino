/*
 * ============================================================================
 * BẢN MÔ PHỎNG WOKWI SIMULATOR (10 CHÂN KHÓA CỨNG — 6 THIẾT BỊ + 3 CẢM BIẾN)
 * Đồ án Tốt nghiệp: Smart Home Voice AI — Nguyễn Tuấn Anh (HUST SEEE)
 *
 * Khớp 100% mạch PCB Hub 1 lớp 100x80mm (NodeMCU ESP8266 v2 Amica):
 *  D0=GPIO16, D1=GPIO5, D2=GPIO4, D3=GPIO0, D4=GPIO2,
 *  D5=GPIO14, D6=GPIO12, D7=GPIO13, D8=GPIO15, A0=ADC0
 *
 * Tích hợp chính sách an toàn ngoại tuyến (Session S2 — Addendum A2/A3):
 *  - Chia sẻ hằng số với `../esp8266_smarthome/offline_safety_config.h`
 *  - Tự ngắt máy bơm sau tối đa 120s chạy liên tục (`PUMP_MAX_CONTINUOUS_RUN_MS`)
 *  - Tự tắt còi báo động ngoại tuyến sau tối đa 30s (`SIREN_MAX_OFFLINE_RUN_MS`)
 *  - Khóa cứng mở cửa chính (`main_door` = 0°) khi ngoại tuyến (Addendum A3)
 * ============================================================================
 */

#include <ESP8266WiFi.h>
#include <Servo.h>

#if defined(__has_include)
#if __has_include("../esp8266_smarthome/offline_fsm.h")
#define SMARTHOME_WOKWI_SHARED_OFFLINE_HEADERS 1
#include "../esp8266_smarthome/offline_safety_config.h"
#include "../esp8266_smarthome/offline_command_grammar.h"
#include "../esp8266_smarthome/offline_fsm.h"
#endif
#endif

// Đồng bộ dự phòng khi chạy độc lập trên trình duyệt Wokwi không có thư mục cha
#ifndef SMARTHOME_WOKWI_SHARED_OFFLINE_HEADERS
#define WOKWI_PUMP_MAX_CONTINUOUS_RUN_MS  120000UL
#define WOKWI_SIREN_MAX_OFFLINE_RUN_MS    30000UL
#define WOKWI_SOIL_PUMP_ON_THRESHOLD_PCT  40.0f
#define WOKWI_SOIL_PUMP_OFF_THRESHOLD_PCT 70.0f
#define WOKWI_OFFLINE_LED_CYCLE_MS        4000UL
#define WOKWI_OFFLINE_LED_PULSE_MS        120UL
#define WOKWI_OFFLINE_LED_GAP_MS          160UL
static const char* WOKWI_REPLY_DOOR_FORBIDDEN_VI =
    "Đang mất kết nối máy chủ, tuyệt đối không được phép mở cửa chính.";
static const char* WOKWI_REPLY_CUSTOM_FORBIDDEN_VI =
    "Đang ngoại tuyến, chỉ hỗ trợ các lệnh bật tắt cơ bản cố định, không hỗ trợ lệnh tùy chỉnh hay đặt lịch.";
#else
#define WOKWI_PUMP_MAX_CONTINUOUS_RUN_MS  smarthome::offline::PUMP_MAX_CONTINUOUS_RUN_MS
#define WOKWI_SIREN_MAX_OFFLINE_RUN_MS    smarthome::offline::SIREN_MAX_OFFLINE_RUN_MS
#define WOKWI_SOIL_PUMP_ON_THRESHOLD_PCT  smarthome::offline::SOIL_PUMP_ON_THRESHOLD_PCT
#define WOKWI_SOIL_PUMP_OFF_THRESHOLD_PCT smarthome::offline::SOIL_PUMP_OFF_THRESHOLD_PCT
#define WOKWI_OFFLINE_LED_CYCLE_MS        smarthome::offline::OFFLINE_LED_CYCLE_MS
#define WOKWI_OFFLINE_LED_PULSE_MS        smarthome::offline::OFFLINE_LED_PULSE_MS
#define WOKWI_OFFLINE_LED_GAP_MS          smarthome::offline::OFFLINE_LED_GAP_MS
static const char* WOKWI_REPLY_DOOR_FORBIDDEN_VI =
    smarthome::offline::REPLY_DOOR_OPEN_FORBIDDEN_VI;
static const char* WOKWI_REPLY_CUSTOM_FORBIDDEN_VI =
    smarthome::offline::REPLY_CUSTOM_FORBIDDEN_VI;
#endif

// Hợp đồng 10 chân khóa cứng trên NodeMCU ESP8266 v2 Amica:
#define PIN_LIVING_LIGHT     16  // D0 (GPIO 16) - Đèn phòng khách qua R1 220R
#define PIN_MAIN_DOOR_SERVO  5   // D1 (GPIO 5)  - Servo SG90 Cửa chính
#define PIN_DHT11            4   // D2 (GPIO 4)  - Cảm biến DHT11 (kèm R3 10k pull-up)
#define PIN_AUDIO_PWM        0   // D3 (GPIO 0)  - PWM Audio ra PAM8403 qua R4 10k pull-up, C4 10uF 16V, R5/R6 2.2k, C5 10nF (IDLE = INPUT)
#define PIN_BEDROOM_LIGHT    2   // D4 (GPIO 2)  - Đèn phòng ngủ Active-LOW (3.3V -> R2 220R -> LED -> D4, R7 10k pull-up)
#define BEDROOM_LED_ACTIVE_LOW true
#define PIN_KY037_DO         14  // D5 (GPIO 14) - Cảm biến âm thanh KY-037 DO
#define PIN_GARDEN_PUMP      12  // D6 (GPIO 12) - Relay 1 (Xanh) Máy bơm + D1 1N4007 + C2 470uF
#define PIN_SPEAKER_AMP      13  // D7 (GPIO 13) - Relay 2 (Đỏ Opto, COM/NO -> +5V) Nguồn PAM8403 + C6 100nF
#define PIN_ALARM_SIREN      15  // D8 (GPIO 15) - Còi 5V qua R10 1k -> Q1 S8050 (NPN), R9 10k pull-down -> GND, D2 1N4007
#define PIN_SOIL_MOISTURE    A0  // A0 (ADC0)    - Cảm biến Độ ẩm Đất LM393 (3.3V) + C7 100nF

Servo doorServo;
bool livingLightState = false;
bool bedroomLightState = false;
bool gardenPumpState = false;
bool alarmSirenState = false;
bool speakerAmpState = false;
bool pumpAutoTriggered = false;
bool pumpSafetyLocked = false;
unsigned long pumpStartedMs = 0;
unsigned long sirenStartedMs = 0;
unsigned long offlineBootMs = 0;

int lastKy037State = LOW;
unsigned long lastKy037Ms = 0;
unsigned long lastCheckMs = 0;

#ifdef SMARTHOME_WOKWI_SHARED_OFFLINE_HEADERS
smarthome::offline::OfflineFsm wokwiOfflineFsm;
#endif

void setWokwiLivingLight(bool on) {
  livingLightState = on;
  digitalWrite(PIN_LIVING_LIGHT, on ? HIGH : LOW);
}

void setWokwiBedroomLight(bool on) {
  bedroomLightState = on;
  digitalWrite(PIN_BEDROOM_LIGHT, BEDROOM_LED_ACTIVE_LOW ? (on ? LOW : HIGH) : (on ? HIGH : LOW));
}

void setWokwiPump(bool on, unsigned long nowMs) {
  gardenPumpState = on;
  digitalWrite(PIN_GARDEN_PUMP, on ? HIGH : LOW);
  if (on) {
    pumpStartedMs = nowMs;
  } else {
    pumpStartedMs = 0;
  }
}

void setWokwiSiren(bool on, unsigned long nowMs) {
  alarmSirenState = on;
  digitalWrite(PIN_ALARM_SIREN, on ? HIGH : LOW);
  if (on) {
    sirenStartedMs = nowMs;
  } else {
    sirenStartedMs = 0;
  }
}

void setWokwiSpeakerAmp(bool on) {
  speakerAmpState = on;
  digitalWrite(PIN_SPEAKER_AMP, on ? HIGH : LOW);
}

// Addendum A3: Tuyệt đối khóa mở cửa chính (90 deg) trong chế độ ngoại tuyến mô phỏng
bool setWokwiMainDoorOffline(bool openDoor) {
  if (openDoor) {
    doorServo.write(0);
    Serial.print("[A3 KHOA CUA OFFLINE] ");
    Serial.println(WOKWI_REPLY_DOOR_FORBIDDEN_VI);
    return false;
  }
  doorServo.write(0);
  return true;
}

void handleWokwiOfflineCommand(String cmd, unsigned long nowMs) {
  cmd.trim();
  if (cmd.length() == 0) return;

#ifdef SMARTHOME_WOKWI_SHARED_OFFLINE_HEADERS
  smarthome::offline::OfflineCommandResult res =
      wokwiOfflineFsm.handleOfflineTextCommand(cmd.c_str(), nowMs, "wokwi_serial");
  if (res.ok && res.state_changed) {
    switch (res.device_index) {
      case smarthome::offline::DEV_MAIN_DOOR:
        setWokwiMainDoorOffline(false);
        break;
      case smarthome::offline::DEV_LIVING_ROOM_LIGHT:
        setWokwiLivingLight(res.new_state_on);
        break;
      case smarthome::offline::DEV_BEDROOM_LIGHT:
        setWokwiBedroomLight(res.new_state_on);
        break;
      case smarthome::offline::DEV_GARDEN_PUMP:
        pumpSafetyLocked = false;
        if (!res.new_state_on) pumpAutoTriggered = false;
        setWokwiPump(res.new_state_on, nowMs);
        break;
      case smarthome::offline::DEV_ALARM_SIREN:
        setWokwiSiren(res.new_state_on, nowMs);
        break;
      case smarthome::offline::DEV_SPEAKER_AMP:
        setWokwiSpeakerAmp(res.new_state_on);
        break;
      default:
        break;
    }
  } else if (res.refused && res.device_index == smarthome::offline::DEV_MAIN_DOOR) {
    setWokwiMainDoorOffline(true);
  }
  Serial.print(res.ok ? "[WOKWI OFFLINE OK] " : "[WOKWI OFFLINE TU CHOI] ");
  Serial.print(res.reason_code);
  Serial.print(" | ");
  Serial.println(res.reply_vi);
#else
  String lower = cmd;
  lower.toLowerCase();
  if (lower.indexOf("hen gio") >= 0 || lower.indexOf("hẹn giờ") >= 0 ||
      lower.indexOf("vung oi") >= 0 || lower.indexOf("vừng ơi") >= 0) {
    Serial.print("[WOKWI OFFLINE TU CHOI] CUSTOM_OR_ADVANCED_FORBIDDEN_OFFLINE | ");
    Serial.println(WOKWI_REPLY_CUSTOM_FORBIDDEN_VI);
    return;
  }
  if (lower.indexOf("mo cua") >= 0 || lower.indexOf("mở cửa") >= 0) {
    setWokwiMainDoorOffline(true);
    return;
  }
  if (lower.indexOf("dong cua") >= 0 || lower.indexOf("đóng cửa") >= 0) {
    setWokwiMainDoorOffline(false);
    Serial.println("[WOKWI OFFLINE OK] OK | Da dong khoa cua chinh (D1 = 0 deg).");
    return;
  }
  bool turnOn = (lower.indexOf("bat") >= 0 || lower.indexOf("bật") >= 0);
  bool turnOff = (lower.indexOf("tat") >= 0 || lower.indexOf("tắt") >= 0);
  if (!turnOn && !turnOff) {
    Serial.print("[WOKWI OFFLINE TU CHOI] CUSTOM_OR_ADVANCED_FORBIDDEN_OFFLINE | ");
    Serial.println(WOKWI_REPLY_CUSTOM_FORBIDDEN_VI);
    return;
  }
  bool on = turnOn && !turnOff;
  if (lower.indexOf("phong khach") >= 0 || lower.indexOf("phòng khách") >= 0) {
    setWokwiLivingLight(on);
    Serial.println(on ? "[WOKWI OFFLINE OK] Den phong khach -> ON" : "[WOKWI OFFLINE OK] Den phong khach -> OFF");
  } else if (lower.indexOf("phong ngu") >= 0 || lower.indexOf("phòng ngủ") >= 0) {
    setWokwiBedroomLight(on);
    Serial.println(on ? "[WOKWI OFFLINE OK] Den phong ngu -> ON" : "[WOKWI OFFLINE OK] Den phong ngu -> OFF");
  } else if (lower.indexOf("bom") >= 0 || lower.indexOf("bơm") >= 0) {
    pumpSafetyLocked = false;
    if (!on) pumpAutoTriggered = false;
    setWokwiPump(on, nowMs);
    Serial.println(on ? "[WOKWI OFFLINE OK] May bom -> ON" : "[WOKWI OFFLINE OK] May bom -> OFF");
  } else if (lower.indexOf("coi") >= 0 || lower.indexOf("còi") >= 0) {
    setWokwiSiren(on, nowMs);
    Serial.println(on ? "[WOKWI OFFLINE OK] Coi bao dong -> ON" : "[WOKWI OFFLINE OK] Coi bao dong -> OFF");
  } else if (lower.indexOf("loa") >= 0 || lower.indexOf("pam8403") >= 0) {
    setWokwiSpeakerAmp(on);
    Serial.println(on ? "[WOKWI OFFLINE OK] Nguon mach loa -> ON" : "[WOKWI OFFLINE OK] Nguon mach loa -> OFF");
  } else {
    Serial.print("[WOKWI OFFLINE TU CHOI] CUSTOM_OR_ADVANCED_FORBIDDEN_OFFLINE | ");
    Serial.println(WOKWI_REPLY_CUSTOM_FORBIDDEN_VI);
  }
#endif
}

void setup() {
  Serial.begin(115200);
  Serial.println("====================================================");
  Serial.println(" KHOI DONG MACH SMART HOME ESP8266 (6+3 LOCKED PINOUT)");
  Serial.println(" Sinh vien: Nguyen Tuan Anh - HUST SEEE");
  Serial.println("====================================================");

  pinMode(PIN_AUDIO_PWM, INPUT);
  digitalWrite(PIN_GARDEN_PUMP, LOW);
  pinMode(PIN_GARDEN_PUMP, OUTPUT);
  digitalWrite(PIN_SPEAKER_AMP, LOW);
  pinMode(PIN_SPEAKER_AMP, OUTPUT);
  digitalWrite(PIN_ALARM_SIREN, LOW);
  pinMode(PIN_ALARM_SIREN, OUTPUT);
  digitalWrite(PIN_LIVING_LIGHT, LOW);
  pinMode(PIN_LIVING_LIGHT, OUTPUT);
  digitalWrite(PIN_BEDROOM_LIGHT, BEDROOM_LED_ACTIVE_LOW ? HIGH : LOW);
  pinMode(PIN_BEDROOM_LIGHT, OUTPUT);
  pinMode(PIN_KY037_DO, INPUT);
  pinMode(PIN_DHT11, INPUT_PULLUP);

  doorServo.attach(PIN_MAIN_DOOR_SERVO, 500, 2400);
  doorServo.write(0);

  // Power-On Self Test (6 thiết bị + 3 cảm biến)
  Serial.println("[TEST 1] Bat Den Phong Khach (D0=16 Active-HIGH) & Den Phong Ngu (D4=2 Active-LOW)...");
  digitalWrite(PIN_LIVING_LIGHT, HIGH);
  digitalWrite(PIN_BEDROOM_LIGHT, BEDROOM_LED_ACTIVE_LOW ? LOW : HIGH);
  delay(250);
  digitalWrite(PIN_LIVING_LIGHT, LOW);
  digitalWrite(PIN_BEDROOM_LIGHT, BEDROOM_LED_ACTIVE_LOW ? HIGH : LOW);

  Serial.println("[TEST 2] Bat Relay 2 PAM8403 (D7=13, +5V COM/NO) & phat chuong PWM (D3=0 qua C4 10uF 16V)...");
  digitalWrite(PIN_SPEAKER_AMP, HIGH);
  delay(20);
  tone(PIN_AUDIO_PWM, 1180, 90);
  delay(110);
  tone(PIN_AUDIO_PWM, 1560, 110);
  delay(120);
  noTone(PIN_AUDIO_PWM);
  pinMode(PIN_AUDIO_PWM, INPUT);
  digitalWrite(PIN_SPEAKER_AMP, LOW);

  Serial.println("[TEST 3] Khoa Cua Chinh SG90 (D1=5 -> 0 deg), tat Coi Q1 S8050 (D8=15 -> LOW)...");
  doorServo.write(0);

  // Demo tự kiểm tra chính sách ngoại tuyến A2/A3 lúc khởi động
  offlineBootMs = millis();
#ifdef SMARTHOME_WOKWI_SHARED_OFFLINE_HEADERS
  wokwiOfflineFsm.begin(offlineBootMs);
#endif
  Serial.println("[TEST 4 - A3] Kiem tra khoa cung mo cua chinh ngoai tuyen:");
  handleWokwiOfflineCommand("mo cua chinh", offlineBootMs);
  Serial.println("[TEST 5 - A2] Kiem tra tu choi lenh hen gio/tuy chinh ngoai tuyen:");
  handleWokwiOfflineCommand("hen gio bat den phong khach 5 phut", offlineBootMs);

  Serial.println("WOKWI_POST_OK: 6_DEVICES_3_SENSORS");
}

void loop() {
  unsigned long now = millis();

  // Chỉ báo LED kép ngoại tuyến không chặn trên D0 (2x120ms mỗi 4000ms)
  unsigned long ledElapsed = (now - offlineBootMs) % WOKWI_OFFLINE_LED_CYCLE_MS;
  bool ledPulse = (ledElapsed < WOKWI_OFFLINE_LED_PULSE_MS) ||
                  (ledElapsed >= (WOKWI_OFFLINE_LED_PULSE_MS + WOKWI_OFFLINE_LED_GAP_MS) &&
                   ledElapsed < (2UL * WOKWI_OFFLINE_LED_PULSE_MS + WOKWI_OFFLINE_LED_GAP_MS));
  digitalWrite(PIN_LIVING_LIGHT, (ledPulse ? !livingLightState : livingLightState) ? HIGH : LOW);

  // Bộ hẹn giờ an toàn cục bộ: tự ngắt bơm sau 120s và còi ngoại tuyến sau 30s
  if (gardenPumpState && pumpStartedMs > 0 && (now - pumpStartedMs >= WOKWI_PUMP_MAX_CONTINUOUS_RUN_MS)) {
    pumpAutoTriggered = false;
    pumpSafetyLocked = true;
    setWokwiPump(false, now);
    Serial.println("[SAFETY CUTOFF] May bom tuoi cay (D6) chay qua 120s -> Tu dong NGAT!");
  }
  if (alarmSirenState && sirenStartedMs > 0 && (now - sirenStartedMs >= WOKWI_SIREN_MAX_OFFLINE_RUN_MS)) {
    setWokwiSiren(false, now);
    Serial.println("[SAFETY CUTOFF] Coi bao dong (D8) ngoai tuyen qua 30s -> Tu dong TAT!");
  }

  // Nhận lệnh kiểm thử ngoại tuyến qua Serial
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    handleWokwiOfflineCommand(cmd, now);
  }

  // Giám sát cảm biến âm thanh KY-037 DO (D5/GPIO14) với debounce 400ms
  int kyState = digitalRead(PIN_KY037_DO);
  if (kyState == HIGH && lastKy037State == LOW && (now - lastKy037Ms >= 400)) {
    lastKy037Ms = now;
    Serial.println("[KY-037 D5] Phat hien am thanh / tieng vo tay (DO=HIGH)!");
  }
  lastKy037State = kyState;

  if (now - lastCheckMs >= 2000) {
    lastCheckMs = now;

    // Đọc giá trị Độ ẩm Đất từ LM393 (ADC0 10-bit 0..1023) trên A0
    int rawAdc = analogRead(PIN_SOIL_MOISTURE);
    float soilPct = constrain(map(rawAdc, 1023, 0, 0, 100), 0, 100);

    Serial.print("[CAM BIEN A0] Do am dat = ");
    Serial.print(soilPct, 1);
    Serial.print("% | ");

    if (soilPct >= WOKWI_SOIL_PUMP_OFF_THRESHOLD_PCT) {
      pumpSafetyLocked = false;
    }

    // Tự động bật/tắt Relay 1 Máy bơm (D6/GPIO12) theo ngưỡng Hysteresis SSOT
    if (soilPct < WOKWI_SOIL_PUMP_ON_THRESHOLD_PCT && !pumpAutoTriggered && !pumpSafetyLocked) {
      pumpAutoTriggered = true;
      setWokwiPump(true, now);
      Serial.println("DAT KHO (<SOIL_PUMP_ON_THRESHOLD_PCT) -> TU DONG BAT RELAY 1 MAY BOM (D6=HIGH)!");
    } else if (soilPct >= WOKWI_SOIL_PUMP_OFF_THRESHOLD_PCT && pumpAutoTriggered) {
      pumpAutoTriggered = false;
      setWokwiPump(false, now);
      Serial.println("DAT DU AM (>=SOIL_PUMP_OFF_THRESHOLD_PCT) -> TU DONG TAT RELAY 1 MAY BOM (D6=LOW)!");
    } else {
      Serial.println(gardenPumpState ? "May bom dang CHAY (ON)" : "May bom dang TAT (OFF)");
    }
  }
}
