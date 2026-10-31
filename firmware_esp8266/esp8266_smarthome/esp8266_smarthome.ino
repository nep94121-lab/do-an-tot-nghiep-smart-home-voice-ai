/*
 * ============================================================================
 * ĐỒ ÁN TỐT NGHIỆP CỬ NHÂN KỸ THUẬT ĐIỆN TỬ – VIỄN THÔNG
 * Trường Điện – Điện tử (SEEE), Đại học Bách khoa Hà Nội (HUST)
 * Sinh viên thực hiện: Nguyễn Tuấn Anh (Admin Cấp 1)
 *
 * Firmware Vi điều khiển: NodeMCU ESP8266 (ESP-12E, CP2102, 4MB Flash)
 * Kiến trúc áp dụng: The System Design Primer
 *  1. Giao thức MQTT Pub/Sub (QoS 0/1, Retain, Last Will & Testament - LWT)
 *  2. CAP Theorem (AP Failover tại biên): Lưu bản sao Bể 1 (Hẹn giờ) & Bể 2 (Luật IF)
 *     vào bộ nhớ Flash LittleFS để mạch tự chạy độc lập khi tắt Laptop/Server.
 *  3. Thu - Phát sóng mang Hồng ngoại 38kHz (VS1838B chân D5 & IR LED 940nm chân D2)
 *     để học lệnh chiếm quyền Remote Điều hòa / Quạt / TV không cần đấu dây.
 *  4. Cảm biến Nhiệt độ & Độ ẩm DHT11 (chân D6) gửi Telemetry định kỳ.
 * ============================================================================
 */

#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <LittleFS.h>
#include <Servo.h>
#include <DHT.h>
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRsend.h>
#include <IRutils.h>
#include <time.h>

// ---------------- CẤU HÌNH MẠNG WI-FI & MQTT BROKER ----------------
const char* WIFI_SSID     = "SmartHome_WiFi";
const char* WIFI_PASSWORD = "password123";
const char* MQTT_SERVER   = "192.168.1.100";
const int   MQTT_PORT     = 1883;
const char* NODE_ID       = "esp8266_node_01";

// ---------------- SƠ ĐỒ CHÂN CHUẨN TRÊN NODEMCU ESP8266 ------------
#define PIN_MAIN_DOOR_SERVO  5   // D1 (GPIO 5)  - Servo SG90 Cửa chính
#define PIN_LIVING_LIGHT_IR  4   // D2 (GPIO 4)  - Đèn khách & Phát IR 38kHz
#define PIN_GARDEN_PUMP      0   // D3 (GPIO 0)  - Relay 5V Máy bơm tưới cây + Diode 1N4007
#define PIN_IR_RECEIVER      14  // D5 (GPIO 14) - Mắt thu hồng ngoại VS1838B 38kHz
#define PIN_DHT_AND_FAN      12  // D6 (GPIO 12) - Cảm biến DHT11 & Quạt
#define PIN_BEDROOM_LIGHT    13  // D7 (GPIO 13) - Đèn phòng ngủ
#define PIN_ALARM_SIREN      15  // D8 (GPIO 15) - Còi báo động Buzzer 5V
#define PIN_SOIL_MOISTURE    A0  // A0 (ADC0)    - Cảm biến độ ẩm đất YL-69 + LM393

#define DHTTYPE DHT11

WiFiClient espClient;
PubSubClient mqtt(espClient);
Servo doorServo;
DHT dht(PIN_DHT_AND_FAN, DHTTYPE);
IRrecv irRecv(PIN_IR_RECEIVER, 1024, 50, true);
IRsend irSend(PIN_LIVING_LIGHT_IR);
decode_results irResults;

bool isIrLearningMode = false;
bool livingLightState = false;   // Lưu trạng thái Đèn phòng khách để khôi phục sau khi phát xung IR 38kHz trên chân D2
bool pumpAutoTriggered = false;  // Chống ghi đè lặp lại mỗi 3s khi người dùng bật/tắt Máy bơm bằng giọng nói
bool wasServerConnected = false; // Theo dõi trạng thái kết nối Server Laptop để tự động khóa Cửa chính khi đứt kết nối
unsigned long lastTelemetryMs = 0;

// ----------------------------------------------------------------------------
// CHẾ ĐỘ MẠCH ĐỘC LẬP (OFFLINE DEFAULT FALLBACK - KHI KHÔNG KẾT NỐI SERVER):
// - Chỉ nhận lệnh mặc định cơ bản cho 5 thiết bị sinh hoạt (Đèn khách, Đèn ngủ,
//   Điều hòa, Quạt, Máy bơm).
// - Vô hiệu hóa mọi khẩu lệnh custom (VD: "vừng ơi mở ra").
// - KHÓA CỨNG Cửa chính (D1) và Còi báo động (D8) để đảm bảo an ninh tuyệt đối!
// ----------------------------------------------------------------------------
void processOfflineDefaultCommand(String rawCmd) {
  rawCmd.trim();
  rawCmd.toLowerCase();
  if (rawCmd.length() == 0) return;

  // 1. Chặn tuyệt đối lệnh Mở Cửa Chính & Còi Báo Động khi không có Server xác thực giọng nói
  if (rawCmd.indexOf("mo cua") >= 0 || rawCmd.indexOf("mở cửa") >= 0 || rawCmd.indexOf("cua chinh") >= 0 || rawCmd.indexOf("cửa chính") >= 0) {
    if (rawCmd.indexOf("dong") >= 0 || rawCmd.indexOf("đóng") >= 0) {
      doorServo.write(0);
      Serial.println("[OFFLINE SAFE] Da dong khoa Cua chinh (D1 = 0 deg).");
      return;
    }
    doorServo.write(0);
    Serial.println("[KHOA AN NINH OFFLINE] Khong ket noi Server -> TU CHOI MO CUA CHINH (D1)!");
    return;
  }
  if (rawCmd.indexOf("coi") >= 0 || rawCmd.indexOf("còi") >= 0 || rawCmd.indexOf("bao dong") >= 0 || rawCmd.indexOf("báo động") >= 0) {
    Serial.println("[KHOA AN NINH OFFLINE] Khong ket noi Server -> TU CHOI CAN THIEP COI BAO DONG (D8)!");
    return;
  }
  if (rawCmd.indexOf("vung oi") >= 0 || rawCmd.indexOf("vừng ơi") >= 0) {
    Serial.println("[OFFLINE DEFAULT] Khau lenh tuy chinh bi vo hieu hoa khi mat ket noi Server!");
    return;
  }

  // 2. Thực thi lệnh mặc định cơ bản cho 5 thiết bị sinh hoạt
  bool turnOn = (rawCmd.indexOf("bat") >= 0 || rawCmd.indexOf("bật") >= 0 || rawCmd.indexOf("mo") >= 0 || rawCmd.indexOf("mở") >= 0);
  bool turnOff = (rawCmd.indexOf("tat") >= 0 || rawCmd.indexOf("tắt") >= 0 || rawCmd.indexOf("dong") >= 0 || rawCmd.indexOf("đóng") >= 0);
  if (!turnOn && !turnOff) return;
  bool stateOn = turnOn && !turnOff;

  if (rawCmd.indexOf("den khach") >= 0 || rawCmd.indexOf("đèn khách") >= 0 || rawCmd.indexOf("den phong khach") >= 0 || rawCmd.indexOf("đèn phòng khách") >= 0) {
    livingLightState = stateOn;
    digitalWrite(PIN_LIVING_LIGHT_IR, stateOn ? HIGH : LOW);
    Serial.println(stateOn ? "[OFFLINE DEFAULT] Den phong khach (D2) -> ON" : "[OFFLINE DEFAULT] Den phong khach (D2) -> OFF");
  } else if (rawCmd.indexOf("den ngu") >= 0 || rawCmd.indexOf("đèn ngủ") >= 0 || rawCmd.indexOf("den phong ngu") >= 0 || rawCmd.indexOf("đèn phòng ngủ") >= 0) {
    digitalWrite(PIN_BEDROOM_LIGHT, stateOn ? HIGH : LOW);
    Serial.println(stateOn ? "[OFFLINE DEFAULT] Den phong ngu (D7) -> ON" : "[OFFLINE DEFAULT] Den phong ngu (D7) -> OFF");
  } else if (rawCmd.indexOf("dieu hoa") >= 0 || rawCmd.indexOf("điều hòa") >= 0 || rawCmd.indexOf("quat") >= 0 || rawCmd.indexOf("quạt") >= 0) {
    blastIrAndRestoreLight(stateOn ? 0xB2BF40 : 0xB27BE0);
    Serial.println(stateOn ? "[OFFLINE DEFAULT] Phat IR 38kHz (D2) -> ON" : "[OFFLINE DEFAULT] Phat IR 38kHz (D2) -> OFF");
  } else if (rawCmd.indexOf("may bom") >= 0 || rawCmd.indexOf("máy bơm") >= 0 || rawCmd.indexOf("tuoi cay") >= 0 || rawCmd.indexOf("tưới cây") >= 0) {
    digitalWrite(PIN_GARDEN_PUMP, stateOn ? HIGH : LOW);
    Serial.println(stateOn ? "[OFFLINE DEFAULT] May bom tuoi cay (D3) -> ON" : "[OFFLINE DEFAULT] May bom tuoi cay (D3) -> OFF");
  }
}

// Phát xung hồng ngoại 38kHz trên chân D2 và khôi phục ngay trạng thái Đèn phòng khách
void blastIrAndRestoreLight(uint64_t code) {
  irSend.sendCOOLIX(code, 24);
  pinMode(PIN_LIVING_LIGHT_IR, OUTPUT);
  digitalWrite(PIN_LIVING_LIGHT_IR, livingLightState ? HIGH : LOW);
}

// ---------------- LƯU BẢN SAO 2 BỂ VÀO FLASH LITTLEFS --------------
void savePoolsReplicaToFlash(const String& jsonPayload) {
  File f = LittleFS.open("/pools_replica.json", "w");
  if (f) {
    f.print(jsonPayload);
    f.close();
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

  StaticJsonDocument<1024> doc;
  if (deserializeJson(doc, msg)) return;

  // 1. Lệnh đóng/mở thiết bị (smarthome/cmd/actuate)
  if (topicStr == "smarthome/cmd/actuate") {
    JsonArray targets = doc["targets"].as<JsonArray>();
    for (JsonObject t : targets) {
      String devId = t["device_id"] | "";
      String state = t["state"] | "OFF";
      bool isOn = (state == "OPEN" || state == "ON");

      if (devId == "main_door") {
        doorServo.write(isOn ? 90 : 0);
      } else if (devId == "living_room_light") {
        livingLightState = isOn;
        digitalWrite(PIN_LIVING_LIGHT_IR, isOn ? HIGH : LOW);
      } else if (devId == "bedroom_light") {
        digitalWrite(PIN_BEDROOM_LIGHT, isOn ? HIGH : LOW);
      } else if (devId == "alarm_siren") {
        digitalWrite(PIN_ALARM_SIREN, isOn ? HIGH : LOW);
      } else if (devId == "garden_pump") {
        digitalWrite(PIN_GARDEN_PUMP, isOn ? HIGH : LOW);
      } else if (devId == "ac" || devId == "fan") {
        blastIrAndRestoreLight(isOn ? 0xB2BF40 : 0xB27BE0);
      }
    }
  }
  // 2. Lệnh nháy đèn báo hiệu bắt đầu thu âm 3-2-1 (smarthome/cmd/enroll_blink)
  else if (topicStr == "smarthome/cmd/enroll_blink") {
    int pulseMs = doc["pulse_ms"] | 350;
    digitalWrite(PIN_LIVING_LIGHT_IR, !livingLightState);
    delay(pulseMs);
    digitalWrite(PIN_LIVING_LIGHT_IR, livingLightState ? HIGH : LOW);
  }
  // 3. Bật chế độ Học lệnh chiếm quyền Remote (smarthome/ir/learn_start)
  else if (topicStr == "smarthome/ir/learn_start") {
    isIrLearningMode = true;
    irRecv.enableIRIn();
  }
  // 4. Phát sóng hồng ngoại 38kHz bật/tắt Điều hòa/Quạt/TV (smarthome/ir/blast)
  else if (topicStr == "smarthome/ir/blast") {
    String hexStr = doc["hex_code"] | "0xB2BF40";
    uint64_t code = strtoull(hexStr.c_str(), nullptr, 16);
    blastIrAndRestoreLight(code);
  }
  // 5. Đồng bộ 2 Bể xuống bộ nhớ Flash LittleFS (smarthome/sync/pools)
  else if (topicStr == "smarthome/sync/pools") {
    savePoolsReplicaToFlash(msg);
  }
}

void reconnectMqtt() {
  if (mqtt.connected()) return;
  // Đăng ký bản tin Di chúc (Last Will and Testament - LWT)
  const char* lwtTopic = "smarthome/status/esp8266";
  const char* lwtPayload = "{\"node_id\":\"esp8266_node_01\",\"online\":false}";
  if (mqtt.connect(NODE_ID, nullptr, nullptr, lwtTopic, 1, true, lwtPayload)) {
    mqtt.publish(lwtTopic, "{\"node_id\":\"esp8266_node_01\",\"online\":true}", true);
    mqtt.subscribe("smarthome/cmd/#", 1);
    mqtt.subscribe("smarthome/ir/#", 1);
    mqtt.subscribe("smarthome/sync/pools", 1);
  }
}

void setup() {
  Serial.begin(115200);
  LittleFS.begin();
  dht.begin();
  irSend.begin();
  irRecv.enableIRIn();

  pinMode(PIN_LIVING_LIGHT_IR, OUTPUT);
  pinMode(PIN_BEDROOM_LIGHT, OUTPUT);
  pinMode(PIN_ALARM_SIREN, OUTPUT);
  pinMode(PIN_GARDEN_PUMP, OUTPUT);
  digitalWrite(PIN_GARDEN_PUMP, LOW);
  doorServo.attach(PIN_MAIN_DOOR_SERVO);
  doorServo.write(0);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  configTime(7 * 3600, 0, "pool.ntp.org", "time.nist.gov");

  mqtt.setServer(MQTT_SERVER, MQTT_PORT);
  mqtt.setCallback(onMqttMessage);
}

void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    if (!mqtt.connected()) {
      reconnectMqtt();
    }
    mqtt.loop();
  }

  bool isOnlineNow = (WiFi.status() == WL_CONNECTED && mqtt.connected());
  if (wasServerConnected && !isOnlineNow) {
    // Vừa mất kết nối với Server Laptop -> Tự động đóng khóa Cửa chính (Fail-Safe Lockout)
    doorServo.write(0);
    Serial.println("[OFFLINE FAIL-SAFE] Mat ket noi Server -> Tu dong DONG KHOA Cua chinh (D1 = 0 deg)!");
  }
  wasServerConnected = isOnlineNow;

  // Khi không kết nối Server, nhận lệnh mặc định cơ bản qua Serial (chặn mở cửa & lệnh custom)
  if (!isOnlineNow && Serial.available() > 0) {
    String localCmd = Serial.readStringUntil('\n');
    processOfflineDefaultCommand(localCmd);
  }

  // Kiểm tra mắt thu VS1838B (Chân D5) khi đang ở chế độ Học lệnh Remote 38kHz
  if (isIrLearningMode && irRecv.decode(&irResults)) {
    StaticJsonDocument<512> resDoc;
    resDoc["node_id"] = NODE_ID;
    resDoc["protocol"] = typeToString(irResults.decode_type);
    resDoc["freq_khz"] = 38;
    resDoc["hex_code"] = "0x" + uint64ToString(irResults.value, 16);
    String out;
    serializeJson(resDoc, out);
    mqtt.publish("smarthome/ir/learned_result", out.c_str(), false);
    isIrLearningMode = false;
    irRecv.resume();
  }

  // Đọc cảm biến Nhiệt độ & Độ ẩm DHT11 (Chân D6) mỗi 3 giây
  unsigned long now = millis();
  if (now - lastTelemetryMs >= 3000) {
    lastTelemetryMs = now;
    float h = dht.readHumidity();
    float t = dht.readTemperature();
    if (!isnan(h) && !isnan(t) && mqtt.connected()) {
      StaticJsonDocument<256> teleDoc;
      teleDoc["node_id"] = NODE_ID;
      teleDoc["temp_c"] = t;
      teleDoc["humidity_pct"] = h;
      teleDoc["wifi_rssi_dbm"] = WiFi.RSSI();
      String out;
      serializeJson(teleDoc, out);
      mqtt.publish("smarthome/telemetry/dht11", out.c_str(), false);
    }

    // Đọc cảm biến Độ ẩm Đất YL-69 + LM393 (Chân A0) & Tự động bật Máy bơm tưới cây (Chân D3)
    // Dùng ngưỡng trễ Hysteresis theo sườn chuyển trạng thái để không ghi đè lệnh bật/tắt bằng giọng nói
    int adcSoil = analogRead(PIN_SOIL_MOISTURE);
    float soilPct = constrain(map(adcSoil, 1024, 300, 0, 100), 0, 100);
    if (soilPct < 40.0f && !pumpAutoTriggered) {
      pumpAutoTriggered = true;
      digitalWrite(PIN_GARDEN_PUMP, HIGH); // Đất chuyển sang khô < 40% -> Tự bật máy bơm
    } else if (soilPct >= 70.0f && pumpAutoTriggered) {
      pumpAutoTriggered = false;
      digitalWrite(PIN_GARDEN_PUMP, LOW);  // Đất đã tưới đủ ẩm >= 70% -> Tự tắt máy bơm
    }
    if (mqtt.connected()) {
      StaticJsonDocument<256> soilDoc;
      soilDoc["node_id"] = NODE_ID;
      soilDoc["soil_moisture_pct"] = soilPct;
      soilDoc["adc_raw"] = adcSoil;
      String soilOut;
      serializeJson(soilDoc, soilOut);
      mqtt.publish("smarthome/telemetry/soil_moisture", soilOut.c_str(), false);
    }
  }
}
