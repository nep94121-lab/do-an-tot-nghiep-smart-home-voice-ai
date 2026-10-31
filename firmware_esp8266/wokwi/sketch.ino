/*
 * ============================================================================
 * BẢN CHẠY TRỰC TIẾP TRÊN WOKWI.COM ONLINE SIMULATOR
 * Đồ án Tốt nghiệp: Smart Home Voice AI — Nguyễn Tuấn Anh (HUST SEEE)
 *
 * Hướng dẫn chạy trên https://wokwi.com/projects/new/esp32 :
 *  1. Dán file này vào tab `sketch.ino` trên Wokwi.com
 *  2. Dán file `diagram.json` (cùng thư mục) vào tab `diagram.json` trên Wokwi.com
 *  3. Bấm nút Play màu xanh lá (▶) trên Wokwi.com để chạy mô phỏng!
 * ============================================================================
 */

#include <WiFi.h>
#include <ESP32Servo.h>

// Ánh xạ chân tương đương NodeMCU ESP8266 -> Wokwi Simulator:
#define PIN_MAIN_DOOR_SERVO  5   // Chân D1 (GPIO 5)  - Servo SG90 Cửa chính
#define PIN_LIVING_LIGHT_IR  4   // Chân D2 (GPIO 4)  - Đèn LED Đỏ Phòng khách & Phát IR 38kHz
#define PIN_GARDEN_PUMP      0   // Chân D3 (GPIO 0)  - Relay 5V Máy bơm tưới cây + Diode 1N4007
#define PIN_IR_RECEIVER      14  // Chân D5 (GPIO 14) - Mắt thu hồng ngoại VS1838B 38kHz
#define PIN_DHT11_SENSOR     12  // Chân D6 (GPIO 12) - Cảm biến Nhiệt độ & Độ ẩm DHT
#define PIN_BEDROOM_LIGHT    13  // Chân D7 (GPIO 13) - Đèn LED Vàng Phòng ngủ
#define PIN_ALARM_SIREN      15  // Chân D8 (GPIO 15) - Còi báo động Buzzer 5V
#define PIN_SOIL_MOISTURE    34  // Chân A0 (ADC)     - Cảm biến Độ ẩm Đất YL-69 + LM393

Servo doorServo;
bool pumpAutoTriggered = false;
unsigned long lastCheckMs = 0;

void setup() {
  Serial.begin(115200);
  Serial.println("====================================================");
  Serial.println(" KHOI DONG MACH SMART HOME TREN WOKWI SIMULATOR");
  Serial.println(" Sinh vien: Nguyen Tuan Anh - HUST SEEE");
  Serial.println("====================================================");

  pinMode(PIN_LIVING_LIGHT_IR, OUTPUT);
  pinMode(PIN_BEDROOM_LIGHT, OUTPUT);
  pinMode(PIN_ALARM_SIREN, OUTPUT);
  pinMode(PIN_GARDEN_PUMP, OUTPUT);
  pinMode(PIN_IR_RECEIVER, INPUT_PULLUP);

  doorServo.attach(PIN_MAIN_DOOR_SERVO, 500, 2400);
  doorServo.write(0);

  // Tự động kiểm tra toàn bộ linh kiện khi vừa bật mạch (Power-On Self Test):
  Serial.println("[TEST 1] Bat Den Phong Khach (D2) & Den Phong Ngu (D7)...");
  digitalWrite(PIN_LIVING_LIGHT_IR, HIGH);
  digitalWrite(PIN_BEDROOM_LIGHT, HIGH);
  delay(600);

  Serial.println("[TEST 2] Che do Offline Default (Khong ket noi Server): KHOA CUNG Cua Chinh Servo SG90 (D1 = 0 do)...");
  doorServo.write(0);
  delay(800);
}

void loop() {
  unsigned long now = millis();
  if (now - lastCheckMs >= 2000) {
    lastCheckMs = now;

    // Đọc giá trị Độ ẩm Đất từ chiết áp YL-69 (0..4095)
    int rawAdc = analogRead(PIN_SOIL_MOISTURE);
    float soilPct = constrain(map(rawAdc, 4095, 0, 0, 100), 0, 100);

    Serial.print("[CAM BIEN A0] Do am dat YL-69 = ");
    Serial.print(soilPct, 1);
    Serial.print("% | ");

    // Tự động bật/tắt Máy bơm nước (Chân D3) theo ngưỡng Hysteresis 40% - 70%
    if (soilPct < 40.0f && !pumpAutoTriggered) {
      pumpAutoTriggered = true;
      digitalWrite(PIN_GARDEN_PUMP, HIGH);
      Serial.println("DAT KHO (<40%) -> TU DONG BAT RELAY MAY BOM (Chân D3 = HIGH)!");
    } else if (soilPct >= 70.0f && pumpAutoTriggered) {
      pumpAutoTriggered = false;
      digitalWrite(PIN_GARDEN_PUMP, LOW);
      Serial.println("DAT DU AM (>=70%) -> TU DONG TAT RELAY MAY BOM (Chân D3 = LOW)!");
    } else {
      Serial.println(pumpAutoTriggered ? "May bom dang CHAY (ON)" : "May bom dang TAT (OFF)");
    }
  }
}
