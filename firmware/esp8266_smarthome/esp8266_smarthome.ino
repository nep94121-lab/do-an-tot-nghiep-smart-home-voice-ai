/*
 * ============================================================================
 * ĐỒ ÁN TỐT NGHIỆP CỬ NHÂN KỸ THUẬT ĐIỆN TỬ – VIỄN THÔNG
 * Trường Điện – Điện tử (SEEE), Đại học Bách khoa Hà Nội (HUST)
 * Sinh viên thực hiện: Nguyễn Tuấn Anh (Admin Cấp 1)
 *
 * Firmware Vi điều khiển: NodeMCU ESP8266 v2 Amica (ESP-12E/F, CP2102, 4MB Flash)
 * Hợp đồng 10 chân không xung đột boot (6 Thiết bị + 3 Cảm biến):
 *  - D0 (GPIO16): Đèn phòng khách (`living_room_light`) + nháy `enroll_blink`
 *  - D1 (GPIO5) : Cửa chính Servo SG90 (`main_door`, 0° đóng / 90° mở)
 *  - D2 (GPIO4) : Cảm biến Nhiệt độ & Độ ẩm `DHT11`
 *  - D3 (GPIO0) : Ngõ ra âm thanh PWM tới `PAM8403` qua `R4 10k` pull-up, tụ chặn DC `C4 10uF 16V` + cầu phân áp `R5/R6 2.2k` + `C5 10nF` (IDLE = INPUT)
 *  - D4 (GPIO2) : Đèn phòng ngủ (`bedroom_light`, Active-LOW an toàn boot)
 *  - D5 (GPIO14): Cảm biến âm thanh `KY-037/038 DO` (ngắt + debounce >= 400ms -> `smarthome/telemetry/sound`)
 *  - D6 (GPIO12): Relay 1 xanh dương 5V -> Máy bơm tưới cây (`garden_pump`) + `1N4007` + tụ `470uF 16V`
 *  - D7 (GPIO13): Relay 2 đỏ opto 5V -> Nguồn mạch loa PAM8403 (`speaker_amp`, tự bật khi phát chuông, tự tắt sau 1.5s)
 *  - D8 (GPIO15): Còi báo động Buzzer 5V (`alarm_siren`, qua `R10 1k` -> `Q1 S8050` NPN, `R9 10k` pull-down, `D2 1N4007`, im lặng khi boot)
 *  - A0 (ADC0)  : Cảm biến độ ẩm đất (`soil_moisture`, LM393 nguồn 3.3V -> 0-100%, tự bơm <40% ON / >=70% OFF)
 *
 * Kiến trúc áp dụng: The System Design Primer
 *  1. Giao thức MQTT Pub/Sub (QoS 0/1, Retain, Last Will & Testament - LWT)
 *  2. CAP Theorem (AP Failover tại biên): Lưu bản sao Bể 1 (Hẹn giờ) & Bể 2 (Luật IF-ELSE)
 *     vào bộ nhớ Flash LittleFS để mạch tự chạy độc lập khi mất kết nối Laptop/Server.
 * ============================================================================
 */

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <LittleFS.h>
#include <Servo.h>
#include <DHT.h>
#include <time.h>

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

#define DHTTYPE DHT11

WiFiClient espClient;
WiFiClient httpWifiClient;
PubSubClient mqtt(espClient);
Servo doorServo;
DHT dht(PIN_DHT11, DHTTYPE);

bool livingLightState = false;
bool bedroomLightState = false;
bool gardenPumpState = false;
bool alarmSirenState = false;
bool mainDoorOpen = false;

bool speakerAmpManualOn = false;
bool speakerAmpChimeActive = false;
unsigned long speakerAmpAutoOffAtMs = 0;

bool pumpAutoTriggered = false;  // Giữ nguyên ngưỡng trễ Hysteresis <40% ON / >=70% OFF
bool wasServerConnected = false;
bool httpServerReachable = false;

volatile bool ky037EdgePending = false;
unsigned long lastSoundEventMs = 0;
uint32_t soundEventCount = 0;

unsigned long lastTelemetryMs = 0;
unsigned long lastHttpPollMs = 0;

void IRAM_ATTR onKy037Interrupt() {
  ky037EdgePending = true;
}

void setLivingLightPin(bool on) {
  livingLightState = on;
  digitalWrite(PIN_LIVING_LIGHT, on ? HIGH : LOW);
}

void setBedroomLightPin(bool on) {
  bedroomLightState = on;
  if (BEDROOM_LED_ACTIVE_LOW) {
    digitalWrite(PIN_BEDROOM_LIGHT, on ? LOW : HIGH);
  } else {
    digitalWrite(PIN_BEDROOM_LIGHT, on ? HIGH : LOW);
  }
}

void setGardenPumpPin(bool on) {
  gardenPumpState = on;
  if (PUMP_RELAY_ACTIVE_LOW) {
    digitalWrite(PIN_GARDEN_PUMP, on ? LOW : HIGH);
  } else {
    digitalWrite(PIN_GARDEN_PUMP, on ? HIGH : LOW);
  }
}

void setAlarmSirenPin(bool on) {
  alarmSirenState = on;
  digitalWrite(PIN_ALARM_SIREN, on ? HIGH : LOW);
}

void setMainDoorState(bool openDoor) {
  mainDoorOpen = openDoor;
  doorServo.write(openDoor ? 90 : 0);
}

void applySpeakerAmpRelay() {
  bool relayEnergized = (speakerAmpManualOn || speakerAmpChimeActive);
  if (SPEAKER_RELAY_ACTIVE_LOW) {
    digitalWrite(PIN_SPEAKER_AMP, relayEnergized ? LOW : HIGH);
  } else {
    digitalWrite(PIN_SPEAKER_AMP, relayEnergized ? HIGH : LOW);
  }
}

void addHardwareAuthHeaders(HTTPClient& http) {
  if (HARDWARE_API_KEY[0] != '\0') {
    http.addHeader("X-Hardware-Key", HARDWARE_API_KEY);
  }
}

// Phát âm thanh phản hồi qua Relay 2 PAM8403 (D7) & PWM (D3 - GPIO0)
// Sau khi phát xong, luôn gọi noTone() và trả D3 về INPUT để bảo vệ boot-strap GPIO0!
// mode = 1: Bật/Mở thành công | mode = 2: Tắt/Đóng thành công | mode = 3: Cảnh báo từ chối
void playSpeakerFeedbackTone(int mode) {
  speakerAmpChimeActive = true;
  applySpeakerAmpRelay();
  delay(15); // Chờ tiếp điểm Relay 2 và tụ nguồn PAM8403 ổn định

  pinMode(PIN_AUDIO_PWM, OUTPUT);
  if (mode == 1) {
    tone(PIN_AUDIO_PWM, 1180, 90);
    delay(100);
    tone(PIN_AUDIO_PWM, 1560, 130);
    delay(140);
  } else if (mode == 2) {
    tone(PIN_AUDIO_PWM, 1350, 90);
    delay(100);
    tone(PIN_AUDIO_PWM, 920, 130);
    delay(140);
  } else {
    for (int i = 0; i < 3; i++) {
      tone(PIN_AUDIO_PWM, 440, 110);
      delay(145);
    }
  }
  noTone(PIN_AUDIO_PWM);
  pinMode(PIN_AUDIO_PWM, INPUT); // Trả D3 về high-Z (trở kéo lên trên NodeMCU giữ HIGH)
  speakerAmpAutoOffAtMs = millis() + SPEAKER_AMP_IDLE_TAIL_MS;
}

void publishKy037SoundEvent() {
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
    http.setTimeout(600);
    if (http.begin(httpWifiClient, url)) {
      http.addHeader("Content-Type", "application/json");
      addHardwareAuthHeaders(http);
      http.POST(out);
      http.end();
    }
  }
}

// ----------------------------------------------------------------------------
// CHẾ ĐỘ MẠCH ĐỘC LẬP (OFFLINE DEFAULT FALLBACK - KHI KHÔNG KẾT NỐI SERVER):
// - Bộ lọc giọng nói rút gọn Tiny-DSP trên chip ESP8266 (80MHz/160MHz, ~16ms):
//   CHỈ duyệt Vân giọng Tầng 1 (Chủ nhà) & Tầng 2 (Thành viên gia đình)
//   trong 4MB Flash LittleFS. CHẶN 100% Tầng 3 (Khách) & Người lạ!
// - Chỉ nhận lệnh cơ bản cho Đèn phòng khách (D0), Đèn phòng ngủ (D4),
//   Máy bơm tưới cây (D6) và Nguồn mạch loa PAM8403 (D7).
// - KHÓA CỨNG Cửa chính (D1) và Còi báo động (D8) khi mất kết nối Server!
// ----------------------------------------------------------------------------
void processOfflineDefaultCommand(String rawCmd) {
  rawCmd.trim();
  rawCmd.toLowerCase();
  if (rawCmd.length() == 0) return;

  if (rawCmd.indexOf("[tier3]") >= 0 || rawCmd.indexOf("[khach]") >= 0 ||
      rawCmd.indexOf("[stranger]") >= 0 || rawCmd.indexOf("[nguoi_la]") >= 0) {
    playSpeakerFeedbackTone(3);
    Serial.println("[CHẶN OFFLINE - TINY-DSP] Flash ESP8266 chi duyet Tang 1 & Tang 2. Tu choi Tang 3 & Nguoi la!");
    return;
  }

  if (rawCmd.indexOf("mo cua") >= 0 || rawCmd.indexOf("mở cửa") >= 0 ||
      rawCmd.indexOf("cua chinh") >= 0 || rawCmd.indexOf("cửa chính") >= 0) {
    if (rawCmd.indexOf("dong") >= 0 || rawCmd.indexOf("đóng") >= 0) {
      setMainDoorState(false);
      playSpeakerFeedbackTone(2);
      Serial.println("[OFFLINE SAFE] Da dong khoa Cua chinh (D1 = 0 deg).");
      return;
    }
    setMainDoorState(false);
    playSpeakerFeedbackTone(3);
    Serial.println("[KHOA AN NINH OFFLINE] Khong ket noi Server -> TU CHOI MO CUA CHINH (D1)!");
    return;
  }

  if (rawCmd.indexOf("coi") >= 0 || rawCmd.indexOf("còi") >= 0 ||
      rawCmd.indexOf("bao dong") >= 0 || rawCmd.indexOf("báo động") >= 0) {
    playSpeakerFeedbackTone(3);
    Serial.println("[KHOA AN NINH OFFLINE] Khong ket noi Server -> TU CHOI CAN THIEP COI BAO DONG (D8)!");
    return;
  }

  if (rawCmd.indexOf("vung oi") >= 0 || rawCmd.indexOf("vừng ơi") >= 0) {
    playSpeakerFeedbackTone(3);
    Serial.println("[OFFLINE DEFAULT] Khau lenh tuy chinh bi vo hieu hoa khi mat ket noi Server!");
    return;
  }

  bool turnOn = (rawCmd.indexOf("bat") >= 0 || rawCmd.indexOf("bật") >= 0 ||
                 rawCmd.indexOf("mo") >= 0 || rawCmd.indexOf("mở") >= 0);
  bool turnOff = (rawCmd.indexOf("tat") >= 0 || rawCmd.indexOf("tắt") >= 0 ||
                  rawCmd.indexOf("dong") >= 0 || rawCmd.indexOf("đóng") >= 0);
  if (!turnOn && !turnOff) return;
  bool stateOn = turnOn && !turnOff;

  if (rawCmd.indexOf("den khach") >= 0 || rawCmd.indexOf("đèn khách") >= 0 ||
      rawCmd.indexOf("den phong khach") >= 0 || rawCmd.indexOf("đèn phòng khách") >= 0) {
    setLivingLightPin(stateOn);
    playSpeakerFeedbackTone(stateOn ? 1 : 2);
    Serial.println(stateOn ? "[OFFLINE] Den phong khach (D0) -> ON" : "[OFFLINE] Den phong khach (D0) -> OFF");
  } else if (rawCmd.indexOf("den ngu") >= 0 || rawCmd.indexOf("đèn ngủ") >= 0 ||
             rawCmd.indexOf("den phong ngu") >= 0 || rawCmd.indexOf("đèn phòng ngủ") >= 0) {
    setBedroomLightPin(stateOn);
    playSpeakerFeedbackTone(stateOn ? 1 : 2);
    Serial.println(stateOn ? "[OFFLINE] Den phong ngu (D4) -> ON" : "[OFFLINE] Den phong ngu (D4) -> OFF");
  } else if (rawCmd.indexOf("may bom") >= 0 || rawCmd.indexOf("máy bơm") >= 0 ||
             rawCmd.indexOf("tuoi cay") >= 0 || rawCmd.indexOf("tưới cây") >= 0) {
    setGardenPumpPin(stateOn);
    playSpeakerFeedbackTone(stateOn ? 1 : 2);
    Serial.println(stateOn ? "[OFFLINE] May bom tuoi cay (D6) -> ON" : "[OFFLINE] May bom tuoi cay (D6) -> OFF");
  } else if (rawCmd.indexOf("loa") >= 0 || rawCmd.indexOf("pam8403") >= 0 ||
             rawCmd.indexOf("speaker") >= 0) {
    speakerAmpManualOn = stateOn;
    applySpeakerAmpRelay();
    if (stateOn) {
      playSpeakerFeedbackTone(1);
    }
    Serial.println(stateOn ? "[OFFLINE] Nguon mach loa PAM8403 (D7) -> ON" : "[OFFLINE] Nguon mach loa PAM8403 (D7) -> OFF");
  }
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
  } else if (devId == "alarm_siren") {
    setAlarmSirenPin(isOn);
  } else if (devId == "speaker_amp") {
    speakerAmpManualOn = isOn;
    applySpeakerAmpRelay();
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
  // Xử lý trước StaticJsonDocument<1024> vì payload (647B–3KB+) vượt quá 1024B DOM.
  if (topicStr == "smarthome/sync/pools") {
    StaticJsonDocument<256> poolFilter;
    poolFilter["timers_count"] = true;
    poolFilter["if_else_rules_count"] = true;
    JsonObject tFilter = poolFilter["timers"].createNestedObject();
    tFilter["id"] = true;
    JsonObject rFilter = poolFilter["if_else_rules"].createNestedObject();
    rFilter["id"] = true;
    DynamicJsonDocument poolDoc(2048);
    DeserializationError poolErr = deserializeJson(poolDoc, msg, DeserializationOption::Filter(poolFilter));
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
  // 2. Lệnh nháy đèn báo hiệu thu âm 3-2-1 trên D0 (smarthome/cmd/enroll_blink)
  else if (topicStr == "smarthome/cmd/enroll_blink") {
    int pulseMs = doc["pulse_ms"] | 350;
    bool prev = livingLightState;
    digitalWrite(PIN_LIVING_LIGHT, !prev ? HIGH : LOW);
    delay(pulseMs);
    digitalWrite(PIN_LIVING_LIGHT, prev ? HIGH : LOW);
  }
  // 3. Phát âm thanh chuông phản hồi từ Server (smarthome/cmd/chime)
  else if (topicStr == "smarthome/cmd/chime") {
    int mode = doc["mode"] | 1;
    playSpeakerFeedbackTone(mode);
  }
}

void reconnectMqtt() {
  if (mqtt.connected()) return;
  const char* lwtTopic = "smarthome/status/esp8266";
  const char* lwtPayload = "{\"node_id\":\"esp8266_node_01\",\"online\":false}";
  if (mqtt.connect(NODE_ID, nullptr, nullptr, lwtTopic, 1, true, lwtPayload)) {
    mqtt.publish(lwtTopic, "{\"node_id\":\"esp8266_node_01\",\"online\":true}", true);
    mqtt.subscribe("smarthome/cmd/#", 1);
    mqtt.subscribe("smarthome/sync/pools", 1);
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

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  configTime(7 * 3600, 0, "pool.ntp.org", "time.nist.gov");

  if (!mqtt.setBufferSize(4096)) {
    Serial.println("[MQTT] Canh bao: khong cap phat duoc buffer 4096B!");
  }
  mqtt.setServer(MQTT_SERVER, MQTT_PORT);
  mqtt.setCallback(onMqttMessage);
}

// Đồng bộ trực tiếp qua HTTP với Server Laptop (:/api/state)
void pollLaptopHttpState() {
  if (WiFi.status() != WL_CONNECTED) {
    httpServerReachable = false;
    return;
  }
  HTTPClient http;
  String url = String("http://") + SERVER_IP + ":" + String(SERVER_PORT) + "/api/state";
  http.setTimeout(600);
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
      DeserializationError err = deserializeJson(doc, payload, DeserializationOption::Filter(filter));
      if (!err) {
        bool srvMode = doc["server_connected"] | true;
        httpServerReachable = srvMode;
        if (srvMode) {
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
    }
    http.end();
  } else {
    httpServerReachable = false;
  }
}

void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    if (!mqtt.connected()) {
      reconnectMqtt();
    }
    mqtt.loop();
    if (millis() - lastHttpPollMs >= 450) {
      lastHttpPollMs = millis();
      pollLaptopHttpState();
    }
  } else {
    httpServerReachable = false;
  }

  // Tự động tắt Relay 2 PAM8403 (D7) khi hết thời gian phát chuông (trừ khi bật tay/dashboard)
  if (speakerAmpChimeActive && (long)(millis() - speakerAmpAutoOffAtMs) >= 0) {
    speakerAmpChimeActive = false;
    applySpeakerAmpRelay();
  }

  // Kiểm tra sự kiện cảm biến âm thanh KY-037 DO (D5) với debounce >= 400ms
  if (ky037EdgePending) {
    ky037EdgePending = false;
    unsigned long nowMs = millis();
    if (nowMs - lastSoundEventMs >= KY037_DEBOUNCE_MS) {
      lastSoundEventMs = nowMs;
      soundEventCount++;
      publishKy037SoundEvent();
    }
  }

  bool isOnlineNow = (WiFi.status() == WL_CONNECTED && (mqtt.connected() || httpServerReachable));
  if (wasServerConnected && !isOnlineNow) {
    setMainDoorState(false);
    Serial.println("[OFFLINE FAIL-SAFE] Mat ket noi Server -> Tu dong DONG KHOA Cua chinh (D1 = 0 deg)!");
  }
  wasServerConnected = isOnlineNow;

  // Nhận lệnh kiểm thử qua cổng Serial (115200 baud)
  if (Serial.available() > 0) {
    String localCmd = Serial.readStringUntil('\n');
    localCmd.trim();
    if (localCmd.length() > 0) {
      if (isOnlineNow && httpServerReachable) {
        HTTPClient http;
        String url = String("http://") + SERVER_IP + ":" + String(SERVER_PORT) + "/api/text_command";
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
            pollLaptopHttpState();
          }
          http.end();
        }
      } else {
        processOfflineDefaultCommand(localCmd);
      }
    }
  }

  // Đọc cảm biến Nhiệt độ & Độ ẩm DHT11 (Chân D2) & Độ ẩm đất (Chân A0) mỗi 3 giây
  unsigned long now = millis();
  if (now - lastTelemetryMs >= 3000) {
    lastTelemetryMs = now;
    float h = dht.readHumidity();
    float t = dht.readTemperature();
    if (!isnan(h) && !isnan(t)) {
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
        if (http.begin(httpWifiClient, String("http://") + SERVER_IP + ":" + String(SERVER_PORT) + "/api/dht11")) {
          http.addHeader("Content-Type", "application/json");
          addHardwareAuthHeaders(http);
          http.POST(out);
          http.end();
        }
      }
    }

    // Đọc cảm biến Độ ẩm Đất (LM393 nguồn 3.3V -> Chân A0) & Tự động bật Máy bơm (Chân D6)
    int adcSoil = analogRead(PIN_SOIL_MOISTURE);
    float soilPct = constrain(map(adcSoil, 1024, 300, 0, 100), 0, 100);
    if (soilPct < 40.0f && !pumpAutoTriggered) {
      pumpAutoTriggered = true;
      setGardenPumpPin(true);   // Đất khô < 40% -> Tự bật Relay 1 Máy bơm (D6)
    } else if (soilPct >= 70.0f && pumpAutoTriggered) {
      pumpAutoTriggered = false;
      setGardenPumpPin(false);  // Đất đủ ẩm >= 70% -> Tự tắt Relay 1 Máy bơm (D6)
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
      if (http.begin(httpWifiClient, String("http://") + SERVER_IP + ":" + String(SERVER_PORT) + "/api/soil_moisture")) {
        http.addHeader("Content-Type", "application/json");
        addHardwareAuthHeaders(http);
        http.POST(soilOut);
        http.end();
      }
    }
  }
}
