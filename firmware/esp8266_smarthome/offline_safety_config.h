#ifndef SMARTHOME_OFFLINE_SAFETY_CONFIG_H
#define SMARTHOME_OFFLINE_SAFETY_CONFIG_H

/*
 * ============================================================================
 * Single Source of Truth (SSOT) cho chính sách an toàn & ngoại tuyến ESP8266.
 * Thuần C++ (không include thư viện Arduino) để kiểm thử độc lập trên host.
 * Đồng bộ 100% với:
 *   - hardware/wiring_contract.py (6 thiết bị + 3 cảm biến, 10 chân khóa cứng)
 *   - backend/engine/constants_and_time.py (DEFAULT_DEVICES)
 *   - backend/engine/offline_contract.py (Addendum A1..A4)
 * ============================================================================
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

namespace smarthome {
namespace offline {

// ---------------- DANH MỤC 6 THIẾT BỊ CHUẨN (KHÔNG QUẠT / ĐIỀU HÒA / IR) ---
enum DeviceIndex : uint8_t {
  DEV_MAIN_DOOR = 0,
  DEV_LIVING_ROOM_LIGHT = 1,
  DEV_BEDROOM_LIGHT = 2,
  DEV_GARDEN_PUMP = 3,
  DEV_ALARM_SIREN = 4,
  DEV_SPEAKER_AMP = 5,
  DEV_COUNT = 6
};

struct DeviceOfflinePolicy {
  uint8_t index;
  const char* id;
  const char* name_vi;
  const char* on_state;
  const char* off_state;
  bool allow_offline_on_or_open;
  bool allow_offline_off_or_close;
  bool force_safe_off_on_disconnect;
};

// Addendum A2 & A3:
// - Không phân quyền Cấp 1/2/3 khi ngoại tuyến.
// - Không hỗ trợ lệnh tùy chỉnh / đặt lịch / luật tự động khi ngoại tuyến.
// - Mở cửa chính (main_door -> OPEN / 90 deg) TUYỆT ĐỐI BỊ CẤM khi ngoại tuyến.
static constexpr bool OFFLINE_ROLE_CHECK_ENABLED = false;
static constexpr bool OFFLINE_CUSTOM_COMMANDS_ALLOWED = false;
static constexpr bool OFFLINE_AUTOMATION_MUTATION_ALLOWED = false;
static constexpr bool OFFLINE_STATUS_QUERY_ALLOWED = true;
static constexpr bool OFFLINE_MAIN_DOOR_OPEN_ALLOWED = false;

static constexpr DeviceOfflinePolicy DEVICE_POLICIES[DEV_COUNT] = {
    {DEV_MAIN_DOOR, "main_door", "cửa chính", "OPEN", "CLOSED", false, true, true},
    {DEV_LIVING_ROOM_LIGHT, "living_room_light", "đèn phòng khách", "ON", "OFF", true, true, false},
    {DEV_BEDROOM_LIGHT, "bedroom_light", "đèn phòng ngủ", "ON", "OFF", true, true, false},
    {DEV_GARDEN_PUMP, "garden_pump", "máy bơm tưới cây", "ON", "OFF", true, true, false},
    {DEV_ALARM_SIREN, "alarm_siren", "còi báo động", "ON", "OFF", true, true, false},
    {DEV_SPEAKER_AMP, "speaker_amp", "nguồn mạch loa PAM8403", "ON", "OFF", true, true, false},
};

// ---------------- THAM SỐ KẾT NỐI LẠI THEO HÀM MŨ (NON-BLOCKING) -----------
static constexpr unsigned long WIFI_BACKOFF_INITIAL_MS = 1000UL;
static constexpr unsigned long WIFI_BACKOFF_MAX_MS = 30000UL;
static constexpr uint8_t WIFI_BACKOFF_MULTIPLIER = 2U;

static constexpr unsigned long SERVER_BACKOFF_INITIAL_MS = 1000UL;
static constexpr unsigned long SERVER_BACKOFF_MAX_MS = 30000UL;
static constexpr uint8_t SERVER_BACKOFF_MULTIPLIER = 2U;

static constexpr unsigned long HEARTBEAT_INTERVAL_MS = 3000UL;
static constexpr unsigned long HTTP_POLL_INTERVAL_MS = 450UL;
static constexpr unsigned long TELEMETRY_INTERVAL_MS = 3000UL;
static constexpr unsigned long HTTP_REQUEST_TIMEOUT_MS = 600UL;

// ---------------- ADDENDUM A1: LOCAL LAN SERVER & SOFTAP FALLBACK ----------
static constexpr uint16_t OFFLINE_HTTP_PORT = 80U;
static constexpr unsigned long WIFI_AP_FALLBACK_AFTER_MS = 15000UL;
static constexpr const char* OFFLINE_MDNS_HOST = "smarthome-esp8266";
static constexpr const char* OFFLINE_AP_SSID = "SmartHome-Offline-AP";
#ifndef SMARTHOME_OFFLINE_AP_PASSWORD
#define SMARTHOME_OFFLINE_AP_PASSWORD ""
#endif
static constexpr const char* OFFLINE_AP_PASSWORD = SMARTHOME_OFFLINE_AP_PASSWORD;

// ---------------- BỘ HẸN GIỜ AN TOÀN CỤC BỘ & NGƯỠNG ĐỘ ẨM ĐẤT ------------
static constexpr unsigned long PUMP_MAX_CONTINUOUS_RUN_MS = 120000UL;
static constexpr unsigned long SIREN_MAX_OFFLINE_RUN_MS = 30000UL;
static constexpr unsigned long SPEAKER_AMP_IDLE_TAIL_DEFAULT_MS = 1500UL;

static constexpr float SOIL_PUMP_ON_THRESHOLD_PCT = 40.0f;
static constexpr float SOIL_PUMP_OFF_THRESHOLD_PCT = 70.0f;

// ---------------- CHỈ BÁO NGOẠI TUYẾN CỤC BỘ (LED + BÍP 1 LẦN) -------------
static constexpr unsigned long OFFLINE_LED_CYCLE_MS = 4000UL;
static constexpr unsigned long OFFLINE_LED_PULSE_MS = 120UL;
static constexpr unsigned long OFFLINE_LED_GAP_MS = 160UL;
static constexpr uint8_t OFFLINE_LED_PULSES_PER_CYCLE = 2U;

static constexpr unsigned long OFFLINE_DISCONNECT_BEEP_MS = 80UL;
static constexpr unsigned long OFFLINE_DISCONNECT_BEEP_GAP_MS = 100UL;
static constexpr uint8_t OFFLINE_DISCONNECT_BEEP_COUNT = 2U;

// ---------------- ADDENDUM A4: HÀNG ĐỢI SỰ KIỆN ĐỒNG BỘ LẠI ----------------
static constexpr size_t OFFLINE_EVENT_RING_CAPACITY = 16U;

// ---------------- MÃ LÝ DO & PHẢN HỒI TIẾNG VIỆT CHUẨN ---------------------
static constexpr const char* REASON_OK = "OK";
static constexpr const char* REASON_STATUS_OK = "STATUS_OK";
static constexpr const char* REASON_DOOR_OPEN_FORBIDDEN = "DOOR_OPEN_FORBIDDEN_OFFLINE";
static constexpr const char* REASON_CUSTOM_FORBIDDEN = "CUSTOM_OR_ADVANCED_FORBIDDEN_OFFLINE";

static constexpr const char* REPLY_DOOR_OPEN_FORBIDDEN_VI =
    "Đang mất kết nối máy chủ, tuyệt đối không được phép mở cửa chính.";
static constexpr const char* REPLY_CUSTOM_FORBIDDEN_VI =
    "Đang ngoại tuyến, chỉ hỗ trợ các lệnh bật tắt cơ bản cố định, không hỗ trợ lệnh tùy chỉnh hay đặt lịch.";
static constexpr const char* REPLY_DOOR_CLOSED_OFFLINE_VI =
    "Đã đóng khóa cửa chính ở chế độ ngoại tuyến.";

inline const DeviceOfflinePolicy* getDevicePolicy(uint8_t idx) {
  if (idx >= DEV_COUNT) return nullptr;
  return &DEVICE_POLICIES[idx];
}

inline const char* getDeviceStateString(uint8_t idx, bool state_on) {
  if (idx >= DEV_COUNT) return "OFF";
  return state_on ? DEVICE_POLICIES[idx].on_state : DEVICE_POLICIES[idx].off_state;
}

}  // namespace offline
}  // namespace smarthome

#endif  // SMARTHOME_OFFLINE_SAFETY_CONFIG_H
