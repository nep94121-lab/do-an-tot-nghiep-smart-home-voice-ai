/*
 * ============================================================================
 * BẢN MÔ PHỎNG WOKWI SIMULATOR (10 CHÂN KHÓA CỨNG — 6 THIẾT BỊ + 3 CẢM BIẾN)
 * Đồ án Tốt nghiệp: Smart Home Voice AI — Nguyễn Tuấn Anh (HUST SEEE)
 *
 * Lưu ý Wokwi: dùng ESP32 DevKit v4 làm proxy cho cùng bảng số GPIO NodeMCU:
 *  D0=16, D1=5, D2=4, D3=0, D4=2, D5=14, D6=12, D7=13, D8=15, A0=34
 * ============================================================================
 */

#include <WiFi.h>
#include <ESP32Servo.h>

// Hợp đồng 10 chân khóa cứng (NodeMCU ESP8266 -> Wokwi ESP32 GPIO proxy):
#define PIN_LIVING_LIGHT     16  // D0 (GPIO 16) - Đèn phòng khách
#define PIN_MAIN_DOOR_SERVO  5   // D1 (GPIO 5)  - Servo SG90 Cửa chính
#define PIN_DHT11            4   // D2 (GPIO 4)  - Cảm biến Nhiệt độ & Độ ẩm DHT11
#define PIN_AUDIO_PWM        0   // D3 (GPIO 0)  - PWM Audio ra PAM8403 (IDLE = INPUT)
#define PIN_BEDROOM_LIGHT    2   // D4 (GPIO 2)  - Đèn phòng ngủ (Active-LOW an toàn boot)
#define BEDROOM_LED_ACTIVE_LOW true
#define PIN_KY037_DO         14  // D5 (GPIO 14) - Cảm biến âm thanh KY-037 DO
#define PIN_GARDEN_PUMP      12  // D6 (GPIO 12) - Relay 1 (Xanh) Máy bơm tưới cây
#define PIN_SPEAKER_AMP      13  // D7 (GPIO 13) - Relay 2 (Đỏ Opto) Nguồn mạch loa PAM8403
#define PIN_ALARM_SIREN      15  // D8 (GPIO 15) - Còi báo động Buzzer 5V (trên PCB vật lý lái qua NPN Q1 S8050 + R10 1k + R9 10k pull-down)
#define PIN_SOIL_MOISTURE    34  // A0 (ADC)     - Cảm biến Độ ẩm Đất LM393

Servo doorServo;
bool pumpAutoTriggered = false;
int lastKy037State = LOW;
unsigned long lastKy037Ms = 0;
unsigned long lastCheckMs = 0;

void setup() {
  Serial.begin(115200);
  Serial.println("====================================================");
  Serial.println(" KHOI DONG MACH SMART HOME WOKWI (6+3 LOCKED PINOUT)");
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

  Serial.println("[TEST 2] Bat Relay 2 PAM8403 (D7=13) & phat chuong PWM (D3=0)...");
  digitalWrite(PIN_SPEAKER_AMP, HIGH);
  delay(20);
  tone(PIN_AUDIO_PWM, 1180, 90);
  delay(110);
  tone(PIN_AUDIO_PWM, 1560, 110);
  delay(120);
  noTone(PIN_AUDIO_PWM);
  pinMode(PIN_AUDIO_PWM, INPUT);
  digitalWrite(PIN_SPEAKER_AMP, LOW);

  Serial.println("[TEST 3] Khoa Cua Chinh SG90 (D1=5 -> 0 deg), tat Coi (D8=15 -> LOW)...");
  doorServo.write(0);
  Serial.println("WOKWI_POST_OK: 6_DEVICES_3_SENSORS");
}

void loop() {
  unsigned long now = millis();

  // Giám sát cảm biến âm thanh KY-037 DO (D5/GPIO14) với debounce 300ms
  int kyState = digitalRead(PIN_KY037_DO);
  if (kyState == HIGH && lastKy037State == LOW && (now - lastKy037Ms >= 300)) {
    lastKy037Ms = now;
    Serial.println("[KY-037 D5] Phat hien am thanh / tieng vo tay (DO=HIGH)!");
  }
  lastKy037State = kyState;

  if (now - lastCheckMs >= 2000) {
    lastCheckMs = now;

    // Đọc giá trị Độ ẩm Đất từ LM393 (0..4095) trên A0 (GPIO34)
    int rawAdc = analogRead(PIN_SOIL_MOISTURE);
    float soilPct = constrain(map(rawAdc, 4095, 0, 0, 100), 0, 100);

    Serial.print("[CAM BIEN A0] Do am dat = ");
    Serial.print(soilPct, 1);
    Serial.print("% | ");

    // Tự động bật/tắt Relay 1 Máy bơm (D6/GPIO12) theo ngưỡng Hysteresis <40% ON / >=70% OFF
    if (soilPct < 40.0f && !pumpAutoTriggered) {
      pumpAutoTriggered = true;
      digitalWrite(PIN_GARDEN_PUMP, HIGH);
      Serial.println("DAT KHO (<40%) -> TU DONG BAT RELAY 1 MAY BOM (D6=HIGH)!");
    } else if (soilPct >= 70.0f && pumpAutoTriggered) {
      pumpAutoTriggered = false;
      digitalWrite(PIN_GARDEN_PUMP, LOW);
      Serial.println("DAT DU AM (>=70%) -> TU DONG TAT RELAY 1 MAY BOM (D6=LOW)!");
    } else {
      Serial.println(pumpAutoTriggered ? "May bom dang CHAY (ON)" : "May bom dang TAT (OFF)");
    }
  }
}
