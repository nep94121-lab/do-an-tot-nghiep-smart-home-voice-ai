/*
 * ============================================================================
 * ĐỒ ÁN TỐT NGHIỆP CỬ NHÂN KỸ THUẬT ĐIỆN TỬ – VIỄN THÔNG
 * Trường Điện – Điện tử (SEEE), Đại học Bách khoa Hà Nội (HUST)
 * Sinh viên thực hiện: Nguyễn Tuấn Anh (Admin Cấp 1)
 *
 * Firmware Vi điều khiển: NodeMCU ESP8266 v2 Amica (ESP-12E/F, CP2102, 4MB Flash)
 * Hợp đồng 10 chân không xung đột boot (6 Thiết bị + 3 Cảm biến):
 *  - D0 (GPIO16): Đèn phòng khách (`living_room_light`) + nháy `enroll_blink` + chỉ báo ngoại tuyến
 *  - D1 (GPIO5) : Cửa chính Servo SG90 (`main_door`, 0° đóng / 90° mở — KHÓA MỞ NGOẠI TUYẾN A3)
 *  - D2 (GPIO4) : Cảm biến Nhiệt độ & Độ ẩm `DHT11`
 *  - D3 (GPIO0) : Ngõ ra âm thanh PWM tới `PAM8403` qua `R4 10k` pull-up, tụ chặn DC `C4 10uF 16V` + cầu phân áp `R5/R6 2.2k` + `C5 10nF` (IDLE = INPUT)
 *  - D4 (GPIO2) : Đèn phòng ngủ (`bedroom_light`, Active-LOW an toàn boot)
 *  - D5 (GPIO14): Cảm biến âm thanh `KY-037/038 DO` (ngắt + debounce >= 400ms -> `smarthome/telemetry/sound`)
 *  - D6 (GPIO12): Relay 1 xanh dương 5V -> Máy bơm tưới cây (`garden_pump`) + `1N4007` + tụ `470uF 16V` (tự ngắt tối đa 120s)
 *  - D7 (GPIO13): Relay 2 đỏ opto 5V -> Nguồn mạch loa PAM8403 (`speaker_amp`, tự bật khi phát chuông, tự tắt sau 1.5s)
 *  - D8 (GPIO15): Còi báo động Buzzer 5V (`alarm_siren`, qua `R10 1k` -> `Q1 S8050` NPN, `R9 10k` pull-down, `D2 1N4007`, tự ngắt ngoại tuyến 30s)
 *  - A0 (ADC0)  : Cảm biến độ ẩm đất (`soil_moisture`, LM393 nguồn 3.3V -> 0-100%, tự bơm <40% ON / >=70% OFF)
 *
 * Kiến trúc Ngoại tuyến & Mất kết nối (Session S2 — Addendum A1..A4):
 *  1. Kết nối lại theo hàm mũ không chặn (Wi-Fi/MQTT/HTTP: 1s -> 2s -> ... -> 30s, an toàn Watchdog).
 *  2. Addendum A1: ESP8266WebServer cổng 80 (`POST /offline/cmd`, `GET /offline/status`), mDNS & SoftAP dự phòng.
 *  3. Addendum A2: Tập lệnh bật/tắt cơ bản cố định cho 6 thiết bị, không phân quyền Tầng 1/2/3 ngoại tuyến, từ chối lệnh tùy chỉnh/đặt lịch.
 *  4. Addendum A3: Tuyệt đối cấm mở cửa chính (90°) khi ngoại tuyến ngay trong firmware (`OfflineFsm` + `setMainDoorState`).
 *  5. Addendum A4: Theo dõi thay đổi vật lý ngoại tuyến và tự đồng bộ lại (`POST /api/hardware/resync` + MQTT) trước khi kéo state từ Server.
 * ============================================================================
 */

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <ESP8266WebServer.h>
#include <ESP8266mDNS.h>
#include <WiFiClient.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <LittleFS.h>
#include <Servo.h>
#include <DHT.h>
#include <time.h>

#include "offline_safety_config.h"
#include "offline_command_grammar.h"
#include "offline_fsm.h"

using namespace smarthome::offline;

// ---------------- CẤU HÌNH MẠNG WI-FI & SERVER LAPTOP ----------------
// LƯU Ý KHI NẠP MẠCH THẬT: Điền đúng tên Wi-Fi, mật khẩu Wi-Fi, IP Laptop & API key (nếu bật)
const char* WIFI_SSID     = "SmartHome_WiFi";
const char* WIFI_PASSWORD = "password123";
const char* SERVER_IP     = "192.168.1.100";  // IP máy Laptop đang chạy Server (cổng 8088)
#ifndef SMARTHOME_SERVER_PORT
#define SMARTHOME_SERVER_PORT 8088
#endif
const int   SERVER_PORT   = SMARTHOME_SERVER_PORT;
const char* MQTT_SERVER   = "192.168.1.100";
const int   MQTT_PORT     = 1883;
#ifndef SMARTHOME_HARDWARE_API_KEY
#define SMARTHOME_HARDWARE_API_KEY ""
#endif
const char* HARDWARE_API_KEY = SMARTHOME_HARDWARE_API_KEY;
const char* NODE_ID          = "esp8266_node_01";

// ---------------- SƠ ĐỒ 10 CHÂN CHUẨN TRÊN NODEMCU ESP8266 -----------
#define PIN_LIVING_LIGHT     16  // D0 (GPIO 16) - LED phòng khách + nháy enroll_blink
#define PIN_MAIN_DOOR_SERVO  5   // D1 (GPIO 5)  - Servo SG90 Cửa chính
#define PIN_DHT11            4   // D2 (GPIO 4)  - Cảm biến Nhiệt độ & Độ ẩm DHT11
#define PIN_AUDIO_PWM        0   // D3 (GPIO 0)  - PWM Audio ra PAM8403 (qua tụ chặn DC + cầu phân áp RC)
#define PIN_BEDROOM_LIGHT    2   // D4 (GPIO 2)  - LED phòng ngủ (Active-LOW an toàn boot)
#define PIN_KY037_DO         14  // D5 (GPIO 14) - Cảm biến âm thanh KY-037/038 DO (vỗ tay/tiếng động lớn)
#define PIN_GARDEN_PUMP      12  // D6 (GPIO 12) - Relay 1 (Xanh) Máy bơm tưới cây + Diode 1N4007
#define PIN_SPEAKER_AMP      13  // D7 (GPIO 13) - Relay 2 (Đỏ Opto, jumper H) Nguồn 5V mạch loa PAM8403
#define PIN_ALARM_SIREN      15  // D8 (GPIO 15) - Còi báo động Buzzer 5V (active-HIGH, im lặng khi boot)
#define PIN_SOIL_MOISTURE    A0  // A0 (ADC0)    - Cảm biến độ ẩm đất (LM393 nguồn 3.3V)

// ---------------- CẤU HÌNH CỰC TÍNH PHẦN CỨNG AN TOÀN BOOT -----------
// D4 (GPIO2) đấu Active-LOW: 3.3V -> Trở -> LED(+) -> LED(-) -> D4 để GPIO2 luôn HIGH khi reset
#define BEDROOM_LED_ACTIVE_LOW    true
// Relay 1 (D6) & Relay 2 (D7 - đặt jumper H) mặc định kích mức HIGH
#define PUMP_RELAY_ACTIVE_LOW     false
#define SPEAKER_RELAY_ACTIVE_LOW  false
// KY-037 DO chuyển từ LOW -> HIGH khi phát hiện tiếng vỗ tay/âm thanh vượt ngưỡng
#define KY037_TRIGGER_EDGE        RISING
#define KY037_DEBOUNCE_MS         400UL
#define SPEAKER_AMP_IDLE_TAIL_MS  1500UL

static_assert(SPEAKER_AMP_IDLE_TAIL_MS == SPEAKER_AMP_IDLE_TAIL_DEFAULT_MS,
              "SPEAKER_AMP_IDLE_TAIL_MS must match offline_safety_config.h");

#define DHTTYPE DHT11

WiFiClient espClient;
WiFiClient httpWifiClient;
PubSubClient mqtt(espClient);
ESP8266WebServer offlineServer(OFFLINE_HTTP_PORT);
Servo doorServo;
DHT dht(PIN_DHT11, DHTTYPE);

// ---------------- TRẠNG THÁI CHẤP HÀNH & BỘ MÁY NGOẠI TUYẾN ---------
bool livingLightState = false;
bool bedroomLightState = false;
bool gardenPumpState = false;
bool alarmSirenState = false;
bool mainDoorOpen = false;

bool speakerAmpManualOn = false;
bool speakerAmpChimeActive = false;
unsigned long speakerAmpAutoOffAtMs = 0;

bool pumpAutoTriggered = false;  // Ngưỡng trễ Hysteresis <40% ON / >=70% OFF + tự ngắt tối đa 120s
bool httpServerReachable = false;
bool mdnsStarted = false;
bool softApEnabled = false;

volatile bool ky037EdgePending = false;
unsigned long lastSoundEventMs = 0;
uint32_t soundEventCount = 0;

float lastTempC = 0.0f;
float lastHumidityPct = 0.0f;
bool lastDhtValid = false;
float lastSoilPct = 50.0f;
bool lastSoundDetected = false;

unsigned long lastTelemetryMs = 0;
unsigned long lastHttpPollMs = 0;
unsigned long lastHeartbeatMs = 0;

// Máy trạng thái ngoại tuyến, backoff không chặn và chỉ báo cục bộ
OfflineFsm offlineFsm;
ExponentialBackoff wifiBackoff(WIFI_BACKOFF_INITIAL_MS, WIFI_BACKOFF_MAX_MS, WIFI_BACKOFF_MULTIPLIER);
ExponentialBackoff mqttBackoff(SERVER_BACKOFF_INITIAL_MS, SERVER_BACKOFF_MAX_MS, SERVER_BACKOFF_MULTIPLIER);
ExponentialBackoff httpBackoff(SERVER_BACKOFF_INITIAL_MS, SERVER_BACKOFF_MAX_MS, SERVER_BACKOFF_MULTIPLIER);
OfflineDisconnectBeeper disconnectBeeper;

// Nháy đèn enroll_blink không chặn trên D0
bool enrollBlinkActive = false;
unsigned long enrollBlinkEndMs = 0;
bool enrollBlinkPrevState = false;

// Bộ phát âm báo PWM không chặn trên D3 (luôn trả D3 về INPUT sau khi phát xong)
struct NonBlockingTonePlayer {
  bool active;
  int mode;
  uint8_t step;
  unsigned long nextStepMs;
} tonePlayer = {false, 0, 0, 0};

void IRAM_ATTR onKy037Interrupt() {
  ky037EdgePending = true;
}

bool isServerOnline() {
  return (WiFi.status() == WL_CONNECTED && (mqtt.connected() || httpServerReachable));
}

void writeLivingLightHardware(bool levelOn) {
  digitalWrite(PIN_LIVING_LIGHT, levelOn ? HIGH : LOW);
}

void setLivingLightPin(bool on) {
  livingLightState = on;
  writeLivingLightHardware(on);
  offlineFsm.syncHardwareState(DEV_LIVING_ROOM_LIGHT, on, millis());
}

void setBedroomLightPin(bool on) {
  bedroomLightState = on;
  if (BEDROOM_LED_ACTIVE_LOW) {
    digitalWrite(PIN_BEDROOM_LIGHT, on ? LOW : HIGH);
  } else {
    digitalWrite(PIN_BEDROOM_LIGHT, on ? HIGH : LOW);
  }
  offlineFsm.syncHardwareState(DEV_BEDROOM_LIGHT, on, millis());
}

void setGardenPumpPin(bool on) {
  gardenPumpState = on;
  if (PUMP_RELAY_ACTIVE_LOW) {
    digitalWrite(PIN_GARDEN_PUMP, on ? LOW : HIGH);
  } else {
    digitalWrite(PIN_GARDEN_PUMP, on ? HIGH : LOW);
  }
  offlineFsm.syncHardwareState(DEV_GARDEN_PUMP, on, millis());
}

void setAlarmSirenPin(bool on) {
  alarmSirenState = on;
  digitalWrite(PIN_ALARM_SIREN, on ? HIGH : LOW);
  offlineFsm.syncHardwareState(DEV_ALARM_SIREN, on, millis());
}

void applySpeakerAmpRelay() {
  bool relayEnergized = (speakerAmpManualOn || speakerAmpChimeActive);
  if (SPEAKER_RELAY_ACTIVE_LOW) {
    digitalWrite(PIN_SPEAKER_AMP, relayEnergized ? LOW : HIGH);
  } else {
    digitalWrite(PIN_SPEAKER_AMP, relayEnergized ? HIGH : LOW);
  }
}

void setSpeakerAmpManual(bool on) {
  speakerAmpManualOn = on;
  applySpeakerAmpRelay();
  offlineFsm.syncHardwareState(DEV_SPEAKER_AMP, on, millis());
}

void playSpeakerFeedbackTone(int mode);

// Addendum A3: Khóa cứng mở cửa chính ngay tại tầng chấp hành Servo SG90 (D1) khi ngoại tuyến!
bool setMainDoorState(bool openDoor) {
  if (openDoor && (!isServerOnline() || !offlineFsm.canSetMainDoor(true))) {
    mainDoorOpen = false;
    doorServo.write(0);
    offlineFsm.syncHardwareState(DEV_MAIN_DOOR, false, millis());
    playSpeakerFeedbackTone(3);
    Serial.print("[A3 KHOA CUA OFFLINE] ");
    Serial.println(REPLY_DOOR_OPEN_FORBIDDEN_VI);
    return false;
  }
  mainDoorOpen = openDoor;
  doorServo.write(openDoor ? 90 : 0);
  offlineFsm.syncHardwareState(DEV_MAIN_DOOR, openDoor, millis());
  return true;
}

void applyDeviceHardwareByIndex(uint8_t devIdx, bool stateOn) {
  switch (devIdx) {
    case DEV_MAIN_DOOR:
      setMainDoorState(stateOn);
      break;
    case DEV_LIVING_ROOM_LIGHT:
      setLivingLightPin(stateOn);
      break;
    case DEV_BEDROOM_LIGHT:
      setBedroomLightPin(stateOn);
      break;
    case DEV_GARDEN_PUMP:
      setGardenPumpPin(stateOn);
      break;
    case DEV_ALARM_SIREN:
      setAlarmSirenPin(stateOn);
      break;
    case DEV_SPEAKER_AMP:
      setSpeakerAmpManual(stateOn);
      break;
    default:
      break;
  }
}

void addHardwareAuthHeaders(HTTPClient& http) {
  if (HARDWARE_API_KEY[0] != '\0') {
    http.addHeader("X-Hardware-Key", HARDWARE_API_KEY);
  }
}

// Phát âm thanh phản hồi không chặn qua Relay 2 PAM8403 (D7) & PWM (D3 - GPIO0)
// Sau khi phát xong, luôn gọi noTone() và trả D3 về INPUT để bảo vệ boot-strap GPIO0!
// mode = 1: Bật/Mở thành công | mode = 2: Tắt/Đóng thành công | mode = 3: Cảnh báo từ chối
void playSpeakerFeedbackTone(int mode) {
  speakerAmpChimeActive = true;
  applySpeakerAmpRelay();
  tonePlayer.active = true;
  tonePlayer.mode = mode;
  tonePlayer.step = 0;
  tonePlayer.nextStepMs = millis() + 15UL;  // Chờ tiếp điểm Relay 2 ổn định không chặn CPU
  speakerAmpAutoOffAtMs = millis() + SPEAKER_AMP_IDLE_TAIL_MS;
}

void finishTonePlayback(unsigned long nowMs) {
  noTone(PIN_AUDIO_PWM);
  pinMode(PIN_AUDIO_PWM, INPUT);  // Trả D3 về high-Z (trở kéo lên trên NodeMCU giữ HIGH)
  tonePlayer.active = false;
  speakerAmpAutoOffAtMs = nowMs + SPEAKER_AMP_IDLE_TAIL_MS;
}

void updateTonePlayer(unsigned long nowMs) {
  if (!tonePlayer.active) return;
  if (static_cast<long>(nowMs - tonePlayer.nextStepMs) < 0) return;

  if (tonePlayer.mode == 1) {
    if (tonePlayer.step == 0) {
      pinMode(PIN_AUDIO_PWM, OUTPUT);
      tone(PIN_AUDIO_PWM, 1180, 90);
      tonePlayer.step = 1;
      tonePlayer.nextStepMs = nowMs + 100UL;
    } else if (tonePlayer.step == 1) {
      tone(PIN_AUDIO_PWM, 1560, 130);
      tonePlayer.step = 2;
      tonePlayer.nextStepMs = nowMs + 140UL;
    } else {
      finishTonePlayback(nowMs);
    }
  } else if (tonePlayer.mode == 2) {
    if (tonePlayer.step == 0) {
      pinMode(PIN_AUDIO_PWM, OUTPUT);
      tone(PIN_AUDIO_PWM, 1350, 90);
      tonePlayer.step = 1;
      tonePlayer.nextStepMs = nowMs + 100UL;
    } else if (tonePlayer.step == 1) {
      tone(PIN_AUDIO_PWM, 920, 130);
      tonePlayer.step = 2;
      tonePlayer.nextStepMs = nowMs + 140UL;
    } else {
      finishTonePlayback(nowMs);
    }
  } else {
    // mode 3: 3 tiếng bíp từ chối 440Hz
    if (tonePlayer.step < 3) {
      pinMode(PIN_AUDIO_PWM, OUTPUT);
      tone(PIN_AUDIO_PWM, 440, 110);
      tonePlayer.step++;
      tonePlayer.nextStepMs = nowMs + 145UL;
    } else {
      finishTonePlayback(nowMs);
    }
  }
}

void populateDevicesJson(JsonObject devsObj) {
  devsObj["main_door"] = mainDoorOpen ? "OPEN" : "CLOSED";
  devsObj["living_room_light"] = livingLightState ? "ON" : "OFF";
  devsObj["bedroom_light"] = bedroomLightState ? "ON" : "OFF";
  devsObj["garden_pump"] = gardenPumpState ? "ON" : "OFF";
  devsObj["alarm_siren"] = alarmSirenState ? "ON" : "OFF";
  devsObj["speaker_amp"] = speakerAmpManualOn ? "ON" : "OFF";
}

void populateSensorsJson(JsonObject senObj) {
  senObj["temp_c"] = lastDhtValid ? lastTempC : 0.0f;
  senObj["humidity_pct"] = lastDhtValid ? lastHumidityPct : 0.0f;
  senObj["soil_moisture_pct"] = lastSoilPct;
  senObj["sound_detected"] = lastSoundDetected;
}

void populateChangedDevicesArray(JsonArray arr) {
  for (uint8_t i = 0; i < DEV_COUNT; ++i) {
    if (offlineFsm.isDeviceDirtyOffline(i)) {
      arr.add(DEVICE_POLICIES[i].id);
    }
  }
}

// ---------------- ADDENDUM A1 + A2 + A3: HTTP SERVER NGOẠI TUYẾN CỔNG 80 ----
void sendOfflineCorsHeaders() {
  offlineServer.sendHeader("Access-Control-Allow-Origin", "*");
  offlineServer.sendHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  offlineServer.sendHeader("Access-Control-Allow-Headers", "Content-Type");
}

void handleHttpOfflineOptions() {
  sendOfflineCorsHeaders();
  offlineServer.send(204);
}

void handleHttpOfflineStatus() {
  sendOfflineCorsHeaders();
  StaticJsonDocument<768> doc;
  doc["ok"] = true;
  doc["node_id"] = NODE_ID;
  doc["offline_mode"] = !isServerOnline();
  doc["ap_active"] = softApEnabled;
  doc["sta_connected"] = (WiFi.status() == WL_CONNECTED);
  doc["sta_ip"] = (WiFi.status() == WL_CONNECTED) ? WiFi.localIP().toString() : "";
  doc["ap_ip"] = softApEnabled ? WiFi.softAPIP().toString() : "";
  doc["offline_events_count"] = offlineFsm.events().count();

  populateDevicesJson(doc.createNestedObject("devices"));
  populateSensorsJson(doc.createNestedObject("sensors"));
  populateChangedDevicesArray(doc.createNestedArray("offline_changed_devices"));

  String out;
  serializeJson(doc, out);
  offlineServer.send(200, "application/json; charset=utf-8", out);
}

void applyOfflineCommandResultToHardware(const OfflineCommandResult& res) {
  if (res.ok && res.state_changed && res.device_index >= 0) {
    applyDeviceHardwareByIndex(static_cast<uint8_t>(res.device_index), res.new_state_on);
    if (res.device_index == DEV_GARDEN_PUMP && !res.new_state_on) {
      pumpAutoTriggered = false;
    }
  } else if (res.refused && res.device_index == DEV_MAIN_DOOR) {
    // Khóa cứng servo 0 độ khi có yêu cầu mở cửa ngoại tuyến (A3)
    setMainDoorState(false);
  }
  if (res.tone_mode > 0) {
    playSpeakerFeedbackTone(res.tone_mode);
  }
}

void handleHttpOfflineCmd() {
  sendOfflineCorsHeaders();
  String body = offlineServer.arg("plain");
  StaticJsonDocument<512> reqDoc;
  DeserializationError err = deserializeJson(reqDoc, body);

  OfflineCommandResult res{};
  const unsigned long nowMs = millis();

  if (err) {
    // Cho phép gửi chuỗi thô không bọc JSON
    body.trim();
    res = offlineFsm.handleOfflineTextCommand(body.c_str(), nowMs, "offline_voice");
  } else if (reqDoc.containsKey("device_id") && reqDoc.containsKey("action")) {
    const char* devId = reqDoc["device_id"] | "";
    const char* action = reqDoc["action"] | "";
    res = offlineFsm.handleOfflineStructuredCommand(devId, action, nowMs, "offline_voice");
  } else {
    const char* text = reqDoc["text"] | "";
    res = offlineFsm.handleOfflineTextCommand(text, nowMs, "offline_voice");
  }

  applyOfflineCommandResultToHardware(res);

  StaticJsonDocument<768> respDoc;
  respDoc["ok"] = res.ok;
  respDoc["offline_mode"] = true;
  respDoc["refused"] = res.refused;
  respDoc["reason_code"] = res.reason_code;
  if (res.device_index >= 0 && res.device_index < DEV_COUNT) {
    const uint8_t idx = static_cast<uint8_t>(res.device_index);
    respDoc["device_id"] = DEVICE_POLICIES[idx].id;
    respDoc["state"] = getDeviceStateString(idx, offlineFsm.getDeviceState(idx));
  }
  respDoc["reply_vi"] = res.reply_vi;
  populateDevicesJson(respDoc.createNestedObject("devices"));

  String out;
  serializeJson(respDoc, out);
  offlineServer.send(res.http_status, "application/json; charset=utf-8", out);
}

void publishKy037SoundEvent() {
  lastSoundDetected = true;
  StaticJsonDocument<256> sndDoc;
  sndDoc["node_id"] = NODE_ID;
  sndDoc["sound_detected"] = true;
  sndDoc["pin"] = "D5 (GPIO 14)";
  sndDoc["gpio"] = 14;
  sndDoc["event_count"] = soundEventCount;
  String out;
  serializeJson(sndDoc, out);

  Serial.print("[KY-037 D5] Phat hien tieng vo tay / am thanh lon #");
  Serial.println(soundEventCount);

  if (mqtt.connected()) {
    mqtt.publish("smarthome/telemetry/sound", out.c_str(), false);
  } else if (httpServerReachable && WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    String url = String("http://") + SERVER_IP + ":" + String(SERVER_PORT) + "/api/sound_sensor";
    http.setTimeout(HTTP_REQUEST_TIMEOUT_MS);
    if (http.begin(httpWifiClient, url)) {
      http.addHeader("Content-Type", "application/json");
      addHardwareAuthHeaders(http);
      http.POST(out);
      http.end();
    }
  }
}

// ----------------------------------------------------------------------------
// CHẾ ĐỘ NGOẠI TUYẾN CỤC BỘ (Serial UART & LAN `/offline/cmd` dùng chung OfflineFsm):
// - Addendum A2: Tập lệnh bật/tắt cơ bản cố định cho 6 thiết bị, KHÔNG phân quyền Cấp 1/2/3.
// - Addendum A3: Tuyệt đối cấm mở cửa chính (main_door -> 90 deg) khi ngoại tuyến.
// ----------------------------------------------------------------------------
void processOfflineDefaultCommand(String rawCmd) {
  rawCmd.trim();
  if (rawCmd.length() == 0) return;

  OfflineCommandResult res =
      offlineFsm.handleOfflineTextCommand(rawCmd.c_str(), millis(), "offline_serial");
  applyOfflineCommandResultToHardware(res);

  Serial.print(res.ok ? "[OFFLINE OK] " : "[OFFLINE TU CHOI] ");
  Serial.print(res.reason_code);
  Serial.print(" | ");
  Serial.println(res.reply_vi);
}

// ---------------- LƯU BẢN SAO 2 BỂ VÀO FLASH LITTLEFS --------------
void savePoolsReplicaToFlash(const String& jsonPayload) {
  File f = LittleFS.open("/pools_replica.json", "w");
  if (f) {
    f.print(jsonPayload);
    f.close();
  }
}

void applyActuatorTarget(const String& devId, const String& state) {
  bool isOn = (state == "OPEN" || state == "ON");
  if (devId == "main_door") {
    setMainDoorState(isOn);
  } else if (devId == "living_room_light") {
    setLivingLightPin(isOn);
  } else if (devId == "bedroom_light") {
    setBedroomLightPin(isOn);
  } else if (devId == "garden_pump") {
    setGardenPumpPin(isOn);
    if (!isOn) pumpAutoTriggered = false;
  } else if (devId == "alarm_siren") {
    setAlarmSirenPin(isOn);
  } else if (devId == "speaker_amp") {
    setSpeakerAmpManual(isOn);
  }
}

// ---------------- XỬ LÝ BẢN TIN MQTT TỪ SERVER GỬI XUỐNG ------------
void onMqttMessage(char* topic, byte* payload, unsigned int length) {
  String msg;
  msg.reserve(length + 1);
  for (unsigned int i = 0; i < length; i++) {
    msg += (char)payload[i];
  }
  String topicStr(topic);

  // 4. Đồng bộ 2 Bể xuống bộ nhớ Flash LittleFS (smarthome/sync/pools)
  if (topicStr == "smarthome/sync/pools") {
    StaticJsonDocument<256> poolFilter;
    poolFilter["timers_count"] = true;
    poolFilter["if_else_rules_count"] = true;
    JsonObject tFilter = poolFilter["timers"].createNestedObject();
    tFilter["id"] = true;
    JsonObject rFilter = poolFilter["if_else_rules"].createNestedObject();
    rFilter["id"] = true;
    DynamicJsonDocument poolDoc(2048);
    DeserializationError poolErr =
        deserializeJson(poolDoc, msg, DeserializationOption::Filter(poolFilter));
    if (!poolErr && poolDoc.is<JsonObject>()) {
      savePoolsReplicaToFlash(msg);
    }
    return;
  }

  StaticJsonDocument<1024> doc;
  if (deserializeJson(doc, msg)) return;

  // 1. Lệnh đóng/mở 6 thiết bị thực tế (smarthome/cmd/actuate)
  if (topicStr == "smarthome/cmd/actuate") {
    JsonArray targets = doc["targets"].as<JsonArray>();
    for (JsonObject t : targets) {
      String devId = t["device_id"] | "";
      String state = t["state"] | "OFF";
      applyActuatorTarget(devId, state);
    }
  }
  // 2. Lệnh nháy đèn báo hiệu thu âm 3-2-1 trên D0 không chặn (smarthome/cmd/enroll_blink)
  else if (topicStr == "smarthome/cmd/enroll_blink") {
    unsigned long pulseMs = doc["pulse_ms"] | 350UL;
    if (pulseMs > 2000UL) pulseMs = 2000UL;
    enrollBlinkPrevState = livingLightState;
    enrollBlinkActive = true;
    enrollBlinkEndMs = millis() + pulseMs;
    writeLivingLightHardware(!enrollBlinkPrevState);
  }
  // 3. Phát âm thanh chuông phản hồi từ Server (smarthome/cmd/chime)
  else if (topicStr == "smarthome/cmd/chime") {
    int mode = doc["mode"] | 1;
    playSpeakerFeedbackTone(mode);
  }
}

void attemptMqttReconnect(unsigned long nowMs) {
  if (mqtt.connected()) return;
  if (!mqttBackoff.shouldAttempt(nowMs)) return;

  const char* lwtTopic = "smarthome/status/esp8266";
  const char* lwtPayload = "{\"node_id\":\"esp8266_node_01\",\"online\":false}";
  if (mqtt.connect(NODE_ID, nullptr, nullptr, lwtTopic, 1, true, lwtPayload)) {
    mqttBackoff.recordSuccess();
    mqtt.publish(lwtTopic, "{\"node_id\":\"esp8266_node_01\",\"online\":true}", true);
    mqtt.subscribe("smarthome/cmd/#", 1);
    mqtt.subscribe("smarthome/sync/pools", 1);
    Serial.println("[MQTT] Da ket noi lai thanh cong.");
  } else {
    unsigned long waitMs = mqttBackoff.recordFailure(nowMs);
    Serial.print("[MQTT] Mat ket noi, thu lai sau ");
    Serial.print(waitMs);
    Serial.println(" ms.");
  }
}

// ---------------- HEARTBEAT ĐỊNH KỲ (POST /api/hardware/heartbeat) ---------
bool sendHardwareHeartbeat(unsigned long nowMs) {
  if (WiFi.status() != WL_CONNECTED) {
    httpServerReachable = false;
    return false;
  }
  if (!httpBackoff.shouldAttempt(nowMs)) {
    return false;
  }

  HTTPClient http;
  String url = String("http://") + SERVER_IP + ":" + String(SERVER_PORT) + "/api/hardware/heartbeat";
  http.setTimeout(HTTP_REQUEST_TIMEOUT_MS);
  bool ok = false;
  if (http.begin(httpWifiClient, url)) {
    http.addHeader("Content-Type", "application/json");
    addHardwareAuthHeaders(http);
    StaticJsonDocument<256> hbDoc;
    hbDoc["node_id"] = NODE_ID;
    hbDoc["wifi_rssi_dbm"] = WiFi.RSSI();
    hbDoc["uptime_ms"] = nowMs;
    hbDoc["firmware_mode"] = "ONLINE";
    String body;
    serializeJson(hbDoc, body);
    int code = http.POST(body);
    if (code == 200) {
      ok = true;
      httpServerReachable = true;
      httpBackoff.recordSuccess();
    } else {
      httpServerReachable = false;
      httpBackoff.recordFailure(nowMs);
    }
    http.end();
  } else {
    httpServerReachable = false;
    httpBackoff.recordFailure(nowMs);
  }
  return ok;
}

// ---------------- ADDENDUM A4: ĐỒNG BỘ LẠI TRẠNG THÁI NGOẠI TUYẾN ----------
// Luôn chạy TRƯỚC pollLaptopHttpState() sau khi kết nối lại để Server tiếp nhận
// đúng trạng thái vật lý đã thay đổi khi ngoại tuyến!
bool performOfflineResync(unsigned long nowMs) {
  if (WiFi.status() != WL_CONNECTED) return false;
  if (!httpBackoff.shouldAttempt(nowMs) && !mqtt.connected()) return false;

  DynamicJsonDocument resyncDoc(2048);
  resyncDoc["node_id"] = NODE_ID;
  resyncDoc["offline_duration_ms"] = offlineFsm.lastOfflineDurationMs();
  resyncDoc["wifi_rssi_dbm"] = WiFi.RSSI();

  populateDevicesJson(resyncDoc.createNestedObject("device_states"));
  populateChangedDevicesArray(resyncDoc.createNestedArray("offline_changed_devices"));

  JsonArray evArr = resyncDoc.createNestedArray("offline_events");
  const OfflineEventRing& ring = offlineFsm.events();
  for (size_t i = 0; i < ring.count(); ++i) {
    const OfflineEvent* ev = ring.at(i);
    if (!ev || ev->device_index >= DEV_COUNT) continue;
    JsonObject obj = evArr.createNestedObject();
    obj["device_id"] = DEVICE_POLICIES[ev->device_index].id;
    obj["state"] = getDeviceStateString(ev->device_index, ev->state_on);
    obj["reason"] = ev->reason;
    obj["offset_ms"] = ev->offset_ms;
  }

  populateSensorsJson(resyncDoc.createNestedObject("sensors"));

  String payload;
  serializeJson(resyncDoc, payload);

  bool httpOk = false;
  if (httpBackoff.shouldAttempt(nowMs)) {
    HTTPClient http;
    String url = String("http://") + SERVER_IP + ":" + String(SERVER_PORT) + "/api/hardware/resync";
    http.setTimeout(HTTP_REQUEST_TIMEOUT_MS);
    if (http.begin(httpWifiClient, url)) {
      http.addHeader("Content-Type", "application/json");
      addHardwareAuthHeaders(http);
      int code = http.POST(payload);
      if (code == 200) {
        httpOk = true;
        httpServerReachable = true;
        httpBackoff.recordSuccess();
      } else {
        httpServerReachable = false;
        httpBackoff.recordFailure(nowMs);
      }
      http.end();
    } else {
      httpServerReachable = false;
      httpBackoff.recordFailure(nowMs);
    }
  }

  bool mqttOk = false;
  if (mqtt.connected()) {
    mqttOk = mqtt.publish("smarthome/state/report", payload.c_str(), true);
  }

  if (httpOk || mqttOk) {
    offlineFsm.markResyncCompleted();
    Serial.println("[A4 RESYNC] Da dong bo lai trang thai vat ly ngoai tuyen len Server.");
    return true;
  }
  return false;
}

// Đồng bộ trực tiếp qua HTTP với Server Laptop (:/api/state)
void pollLaptopHttpState(unsigned long nowMs) {
  if (WiFi.status() != WL_CONNECTED) {
    httpServerReachable = false;
    return;
  }
  if (!httpBackoff.shouldAttempt(nowMs)) return;

  HTTPClient http;
  String url = String("http://") + SERVER_IP + ":" + String(SERVER_PORT) + "/api/state";
  http.setTimeout(HTTP_REQUEST_TIMEOUT_MS);
  if (http.begin(httpWifiClient, url)) {
    addHardwareAuthHeaders(http);
    int code = http.GET();
    if (code == 200) {
      String payload = http.getString();
      StaticJsonDocument<128> filter;
      filter["server_connected"] = true;
      JsonObject devFilter = filter["devices"].createNestedObject();
      devFilter["id"] = true;
      devFilter["state"] = true;
      DynamicJsonDocument doc(2048);
      DeserializationError err =
          deserializeJson(doc, payload, DeserializationOption::Filter(filter));
      if (!err) {
        bool srvMode = doc["server_connected"] | true;
        httpServerReachable = srvMode;
        httpBackoff.recordSuccess();
        if (srvMode && !offlineFsm.hasPendingResync()) {
          JsonArray devs = doc["devices"].as<JsonArray>();
          for (JsonObject d : devs) {
            String id = d["id"] | "";
            String st = d["state"] | "OFF";
            applyActuatorTarget(id, st);
          }
        }
      }
    } else {
      httpServerReachable = false;
      httpBackoff.recordFailure(nowMs);
    }
    http.end();
  } else {
    httpServerReachable = false;
    httpBackoff.recordFailure(nowMs);
  }
}

void manageWifiAndSoftAp(unsigned long nowMs) {
  if (WiFi.status() == WL_CONNECTED) {
    wifiBackoff.recordSuccess();
    offlineFsm.shouldEnableSoftAp(true, nowMs);
    if (!mdnsStarted) {
      if (MDNS.begin(OFFLINE_MDNS_HOST)) {
        MDNS.addService("http", "tcp", OFFLINE_HTTP_PORT);
        mdnsStarted = true;
        Serial.print("[A1 mDNS] San sang tai http://");
        Serial.print(OFFLINE_MDNS_HOST);
        Serial.println(".local/offline/cmd");
      }
    } else {
      MDNS.update();
    }
    return;
  }

  httpServerReachable = false;
  mdnsStarted = false;

  // Bật SoftAP dự phòng sau WIFI_AP_FALLBACK_AFTER_MS (15s) để điều khiển giọng nói ngoại tuyến không cần router
  if (!softApEnabled && offlineFsm.shouldEnableSoftAp(false, nowMs)) {
    WiFi.mode(WIFI_AP_STA);
    if (OFFLINE_AP_PASSWORD[0] != '\0') {
      WiFi.softAP(OFFLINE_AP_SSID, OFFLINE_AP_PASSWORD);
    } else {
      WiFi.softAP(OFFLINE_AP_SSID);
    }
    softApEnabled = true;
    Serial.print("[A1 SoftAP] Da bat diem phat du phong ");
    Serial.print(OFFLINE_AP_SSID);
    Serial.print(" tai IP ");
    Serial.println(WiFi.softAPIP());
  }

  // Thử kết nối lại Wi-Fi STA theo hàm mũ không chặn (tuyệt đối không lặp khởi động lại mạch)
  if (wifiBackoff.shouldAttempt(nowMs)) {
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    unsigned long waitMs = wifiBackoff.recordFailure(nowMs);
    Serial.print("[WiFi] Dang ket noi lai STA, lan thu tiep theo sau ");
    Serial.print(waitMs);
    Serial.println(" ms.");
  }
}

void setup() {
  // Khởi tạo an toàn boot TRƯỚC KHI bật ngõ ra:
  // - D3 (GPIO0): INPUT (high-Z, giữ HIGH qua trở kéo lên nội mạch)
  // - D4 (GPIO2): Ghi HIGH trước khi đặt OUTPUT để LED Active-LOW tắt và GPIO2 luôn HIGH
  // - D8 (GPIO15): Ghi LOW để còi Buzzer active-HIGH im lặng tuyệt đối khi boot
  pinMode(PIN_AUDIO_PWM, INPUT);

  digitalWrite(PIN_BEDROOM_LIGHT, BEDROOM_LED_ACTIVE_LOW ? HIGH : LOW);
  pinMode(PIN_BEDROOM_LIGHT, OUTPUT);

  digitalWrite(PIN_ALARM_SIREN, LOW);
  pinMode(PIN_ALARM_SIREN, OUTPUT);

  digitalWrite(PIN_LIVING_LIGHT, LOW);
  pinMode(PIN_LIVING_LIGHT, OUTPUT);

  digitalWrite(PIN_GARDEN_PUMP, PUMP_RELAY_ACTIVE_LOW ? HIGH : LOW);
  pinMode(PIN_GARDEN_PUMP, OUTPUT);

  digitalWrite(PIN_SPEAKER_AMP, SPEAKER_RELAY_ACTIVE_LOW ? HIGH : LOW);
  pinMode(PIN_SPEAKER_AMP, OUTPUT);

  pinMode(PIN_KY037_DO, INPUT);
  attachInterrupt(digitalPinToInterrupt(PIN_KY037_DO), onKy037Interrupt, KY037_TRIGGER_EDGE);

  doorServo.attach(PIN_MAIN_DOOR_SERVO);
  setMainDoorState(false);

  Serial.begin(115200);
  LittleFS.begin();
  dht.begin();

  offlineFsm.begin(millis());

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  wifiBackoff.recordFailure(millis());
  configTime(7 * 3600, 0, "pool.ntp.org", "time.nist.gov");

  if (!mqtt.setBufferSize(4096)) {
    Serial.println("[MQTT] Canh bao: khong cap phat duoc buffer 4096B!");
  }
  mqtt.setServer(MQTT_SERVER, MQTT_PORT);
  mqtt.setCallback(onMqttMessage);

  // Addendum A1: Khởi động HTTP Server ngoại tuyến cổng 80 ngay khi boot
  offlineServer.on("/offline/cmd", HTTP_POST, handleHttpOfflineCmd);
  offlineServer.on("/offline/cmd", HTTP_OPTIONS, handleHttpOfflineOptions);
  offlineServer.on("/offline/status", HTTP_GET, handleHttpOfflineStatus);
  offlineServer.on("/offline/status", HTTP_OPTIONS, handleHttpOfflineOptions);
  offlineServer.begin();
  Serial.println("[A1 HTTP] May chu ngoai tuyen cong 80 san sang (/offline/cmd, /offline/status).");
}

void loop() {
  const unsigned long now = millis();

  // 1. Luôn phục vụ HTTP Server ngoại tuyến cổng 80 (Addendum A1) & nhường CPU cho Watchdog
  offlineServer.handleClient();
  yield();

  // 2. Quản lý kết nối Wi-Fi STA không chặn + SoftAP dự phòng + mDNS
  manageWifiAndSoftAp(now);

  // 3. Quản lý MQTT & HTTP Server với Exponential Backoff + Heartbeat định kỳ
  if (WiFi.status() == WL_CONNECTED) {
    if (!mqtt.connected()) {
      attemptMqttReconnect(now);
    } else {
      mqtt.loop();
    }

    if (now - lastHeartbeatMs >= HEARTBEAT_INTERVAL_MS) {
      lastHeartbeatMs = now;
      sendHardwareHeartbeat(now);
    }
  }

  // 4. Đánh giá chuyển trạng thái kết nối ONLINE <-> OFFLINE
  const bool onlineNow = isServerOnline();
  ConnectivityTransition tr = offlineFsm.onConnectivityChanged(onlineNow, now);
  if (tr.became_offline) {
    setMainDoorState(false);
    if (tr.trigger_disconnect_beep) {
      disconnectBeeper.trigger(now);
    }
    Serial.println("[OFFLINE FAIL-SAFE] Mat ket noi Server -> Tu dong DONG KHOA Cua chinh (D1 = 0 deg)!");
  } else if (tr.became_online) {
    disconnectBeeper.cancel();
    if (!alarmSirenState) {
      digitalWrite(PIN_ALARM_SIREN, LOW);
    }
    writeLivingLightHardware(livingLightState);
    Serial.println("[ONLINE RECOVERED] Da ket noi lai Server -> Chuan bi dong bo A4...");
  }

  // 5. Addendum A4: Nếu có trạng thái chờ đồng bộ lại, PHẢI đẩy resync TRƯỚC khi poll `/api/state`
  if (onlineNow && offlineFsm.hasPendingResync()) {
    performOfflineResync(now);
  } else if (onlineNow && (now - lastHttpPollMs >= HTTP_POLL_INTERVAL_MS)) {
    lastHttpPollMs = now;
    pollLaptopHttpState(now);
  }

  // 6. Cập nhật các bộ hẹn giờ an toàn cục bộ (Bơm tối đa 120s, Còi ngoại tuyến tối đa 30s)
  SafetyTripResult trips = offlineFsm.tickSafetyTimers(now);
  if (trips.pump_tripped) {
    pumpAutoTriggered = false;
    setGardenPumpPin(false);
    Serial.println("[SAFETY CUTOFF] May bom tuoi cay (D6) da chay qua 120s -> Tu dong NGAT!");
  }
  if (trips.siren_tripped) {
    setAlarmSirenPin(false);
    Serial.println("[SAFETY CUTOFF] Coi bao dong (D8) ngoai tuyen qua 30s -> Tu dong TAT!");
  }

  // 7. Cập nhật âm báo PWM không chặn & tự tắt Relay 2 PAM8403 sau 1.5s nghỉ
  updateTonePlayer(now);
  if (!tonePlayer.active && speakerAmpChimeActive &&
      static_cast<long>(now - speakerAmpAutoOffAtMs) >= 0) {
    speakerAmpChimeActive = false;
    applySpeakerAmpRelay();
  }

  // 8. Cập nhật nháy enroll_blink hoặc chỉ báo LED kép ngoại tuyến không chặn trên D0
  if (enrollBlinkActive) {
    if (static_cast<long>(now - enrollBlinkEndMs) >= 0) {
      enrollBlinkActive = false;
      writeLivingLightHardware(livingLightState);
    }
  } else {
    bool desiredLed =
        OfflineLedPattern::computeLedOutput(livingLightState, onlineNow, now, offlineFsm.offlineSinceMs());
    writeLivingLightHardware(desiredLed);
  }

  // 9. Cập nhật 2 tiếng bíp báo mất kết nối 1 lần duy nhất không chặn (không ảnh hưởng khi còi đang ON)
  if (!alarmSirenState) {
    bool beepOn = disconnectBeeper.update(now);
    digitalWrite(PIN_ALARM_SIREN, beepOn ? HIGH : LOW);
  }

  // 10. Kiểm tra sự kiện cảm biến âm thanh KY-037 DO (D5) với debounce >= 400ms
  if (ky037EdgePending) {
    ky037EdgePending = false;
    if (now - lastSoundEventMs >= KY037_DEBOUNCE_MS) {
      lastSoundEventMs = now;
      soundEventCount++;
      publishKy037SoundEvent();
    }
  }

  // 11. Nhận lệnh kiểm thử qua cổng Serial (115200 baud)
  if (Serial.available() > 0) {
    String localCmd = Serial.readStringUntil('\n');
    localCmd.trim();
    if (localCmd.length() > 0) {
      if (onlineNow && httpServerReachable) {
        HTTPClient http;
        String url = String("http://") + SERVER_IP + ":" + String(SERVER_PORT) + "/api/text_command";
        http.setTimeout(HTTP_REQUEST_TIMEOUT_MS);
        if (http.begin(httpWifiClient, url)) {
          http.addHeader("Content-Type", "application/json");
          addHardwareAuthHeaders(http);
          StaticJsonDocument<256> cmdDoc;
          cmdDoc["text"] = localCmd;
          String body;
          serializeJson(cmdDoc, body);
          int code = http.POST(body);
          if (code == 200) {
            playSpeakerFeedbackTone(1);
            pollLaptopHttpState(now);
          }
          http.end();
        }
      } else {
        processOfflineDefaultCommand(localCmd);
      }
    }
  }

  // 12. Đọc cảm biến Nhiệt độ & Độ ẩm DHT11 (D2) & Độ ẩm đất (A0) mỗi 3 giây
  if (now - lastTelemetryMs >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryMs = now;
    float h = dht.readHumidity();
    float t = dht.readTemperature();
    if (!isnan(h) && !isnan(t)) {
      lastTempC = t;
      lastHumidityPct = h;
      lastDhtValid = true;
      StaticJsonDocument<256> teleDoc;
      teleDoc["node_id"] = NODE_ID;
      teleDoc["temp_c"] = t;
      teleDoc["humidity_pct"] = h;
      teleDoc["wifi_rssi_dbm"] = WiFi.RSSI();
      String out;
      serializeJson(teleDoc, out);
      if (mqtt.connected()) {
        mqtt.publish("smarthome/telemetry/dht11", out.c_str(), false);
      } else if (httpServerReachable) {
        HTTPClient http;
        http.setTimeout(HTTP_REQUEST_TIMEOUT_MS);
        if (http.begin(httpWifiClient, String("http://") + SERVER_IP + ":" + String(SERVER_PORT) + "/api/dht11")) {
          http.addHeader("Content-Type", "application/json");
          addHardwareAuthHeaders(http);
          http.POST(out);
          http.end();
        }
      }
    }

    // Đọc cảm biến Độ ẩm Đất (LM393 nguồn 3.3V -> Chân A0) & Tự động bật/tắt Máy bơm (Chân D6)
    int adcSoil = analogRead(PIN_SOIL_MOISTURE);
    float soilPct = constrain(map(adcSoil, 1024, 300, 0, 100), 0, 100);
    lastSoilPct = soilPct;

    if (soilPct >= SOIL_PUMP_OFF_THRESHOLD_PCT) {
      offlineFsm.notifySoilMoistureWet();
    }

    if (soilPct < 40.0f && !pumpAutoTriggered && !offlineFsm.isPumpSafetyLocked()) {
      pumpAutoTriggered = true;
      setGardenPumpPin(true);  // Đất khô < 40% -> Tự bật Relay 1 Máy bơm (D6)
      offlineFsm.recordDeviceChange(DEV_GARDEN_PUMP, true, now, "soil_auto_offline");
    } else if (soilPct >= 70.0f && pumpAutoTriggered) {
      pumpAutoTriggered = false;
      setGardenPumpPin(false);  // Đất đủ ẩm >= 70% -> Tự tắt Relay 1 Máy bơm (D6)
      offlineFsm.recordDeviceChange(DEV_GARDEN_PUMP, false, now, "soil_auto_offline");
    }

    StaticJsonDocument<256> soilDoc;
    soilDoc["node_id"] = NODE_ID;
    soilDoc["soil_moisture_pct"] = soilPct;
    soilDoc["adc_raw"] = adcSoil;
    String soilOut;
    serializeJson(soilDoc, soilOut);
    if (mqtt.connected()) {
      mqtt.publish("smarthome/telemetry/soil_moisture", soilOut.c_str(), false);
    } else if (httpServerReachable) {
      HTTPClient http;
      http.setTimeout(HTTP_REQUEST_TIMEOUT_MS);
      if (http.begin(httpWifiClient, String("http://") + SERVER_IP + ":" + String(SERVER_PORT) + "/api/soil_moisture")) {
        http.addHeader("Content-Type", "application/json");
        addHardwareAuthHeaders(http);
        http.POST(soilOut);
        http.end();
      }
    }
  }
}
