#ifndef SMARTHOME_OFFLINE_FSM_H
#define SMARTHOME_OFFLINE_FSM_H

/*
 * ============================================================================
 * Máy trạng thái ngoại tuyến (OfflineFsm), ExponentialBackoff, chỉ báo LED/Bíp
 * không chặn và hàng đợi đồng bộ lại (Addendum A1–A4).
 * Thuần C++ (0 thư viện Arduino, 0 cấp phát heap) để kiểm thử xác định trên host.
 * ============================================================================
 */

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "offline_command_grammar.h"
#include "offline_safety_config.h"

namespace smarthome {
namespace offline {

// ---------------- 1. EXPONENTIAL BACKOFF KHÔNG CHẶN ------------------------
struct ExponentialBackoff {
  unsigned long initial_ms;
  unsigned long max_ms;
  uint8_t multiplier;
  unsigned long current_delay_ms;
  unsigned long next_attempt_ms;
  uint32_t attempts;
  bool scheduled;

  ExponentialBackoff(unsigned long init_ms = 1000UL,
                     unsigned long max_delay_ms = 30000UL,
                     uint8_t mult = 2U)
      : initial_ms(init_ms),
        max_ms(max_delay_ms),
        multiplier(mult < 1U ? 1U : mult),
        current_delay_ms(init_ms),
        next_attempt_ms(0UL),
        attempts(0U),
        scheduled(false) {}

  void reset() {
    current_delay_ms = initial_ms;
    next_attempt_ms = 0UL;
    attempts = 0U;
    scheduled = false;
  }

  bool shouldAttempt(unsigned long now_ms) const {
    if (!scheduled) return true;
    return static_cast<long>(now_ms - next_attempt_ms) >= 0;
  }

  unsigned long recordFailure(unsigned long now_ms) {
    const unsigned long wait_ms = current_delay_ms;
    next_attempt_ms = now_ms + wait_ms;
    scheduled = true;
    ++attempts;

    if (current_delay_ms < max_ms) {
      if (multiplier > 1U && current_delay_ms > (max_ms / multiplier)) {
        current_delay_ms = max_ms;
      } else {
        const unsigned long next_delay = current_delay_ms * multiplier;
        current_delay_ms = (next_delay > max_ms) ? max_ms : next_delay;
      }
    }
    return wait_ms;
  }

  void recordSuccess() { reset(); }
};

// ---------------- 2. CHỈ BÁO LED NGOẠI TUYẾN KHÔNG CHẶN --------------------
struct OfflineLedPattern {
  static bool isPulseActive(unsigned long now_ms, unsigned long offline_since_ms) {
    const unsigned long elapsed = (now_ms - offline_since_ms) % OFFLINE_LED_CYCLE_MS;
    const unsigned long pulse2_start = OFFLINE_LED_PULSE_MS + OFFLINE_LED_GAP_MS;
    const unsigned long pulse2_end = pulse2_start + OFFLINE_LED_PULSE_MS;
    if (elapsed < OFFLINE_LED_PULSE_MS) return true;
    if (elapsed >= pulse2_start && elapsed < pulse2_end) return true;
    return false;
  }

  static bool computeLedOutput(bool user_light_on,
                               bool is_online,
                               unsigned long now_ms,
                               unsigned long offline_since_ms) {
    if (is_online) return user_light_on;
    if (isPulseActive(now_ms, offline_since_ms)) {
      return !user_light_on;
    }
    return user_light_on;
  }
};

// ---------------- 3. BÍP MẤT KẾT NỐI 1 LẦN KHÔNG CHẶN ---------------------
struct OfflineDisconnectBeeper {
  bool active;
  unsigned long started_ms;

  OfflineDisconnectBeeper() : active(false), started_ms(0UL) {}

  void trigger(unsigned long now_ms) {
    active = true;
    started_ms = now_ms;
  }

  void cancel() { active = false; }

  bool update(unsigned long now_ms) {
    if (!active) return false;
    const unsigned long elapsed = now_ms - started_ms;
    const unsigned long period = OFFLINE_DISCONNECT_BEEP_MS + OFFLINE_DISCONNECT_BEEP_GAP_MS;
    const unsigned long total_ms =
        (static_cast<unsigned long>(OFFLINE_DISCONNECT_BEEP_COUNT - 1U) * period) +
        OFFLINE_DISCONNECT_BEEP_MS;
    if (elapsed >= total_ms) {
      active = false;
      return false;
    }
    const unsigned long in_slot = elapsed % period;
    return in_slot < OFFLINE_DISCONNECT_BEEP_MS;
  }
};

// ---------------- 4. RING BUFFER SỰ KIỆN ĐỒNG BỘ LẠI (A4) ------------------
struct OfflineEvent {
  uint8_t device_index;
  bool state_on;
  char reason[24];
  unsigned long offset_ms;
};

struct OfflineEventRing {
  OfflineEvent items[OFFLINE_EVENT_RING_CAPACITY];
  size_t head;
  size_t length;

  OfflineEventRing() : head(0U), length(0U) {}

  void clear() {
    head = 0U;
    length = 0U;
  }

  void push(uint8_t device_index, bool state_on, const char* reason, unsigned long offset_ms) {
    size_t write_idx = 0U;
    if (length < OFFLINE_EVENT_RING_CAPACITY) {
      write_idx = (head + length) % OFFLINE_EVENT_RING_CAPACITY;
      ++length;
    } else {
      write_idx = head;
      head = (head + 1U) % OFFLINE_EVENT_RING_CAPACITY;
    }
    OfflineEvent& ev = items[write_idx];
    ev.device_index = device_index;
    ev.state_on = state_on;
    ev.offset_ms = offset_ms;
    if (reason) {
      strncpy(ev.reason, reason, sizeof(ev.reason) - 1U);
      ev.reason[sizeof(ev.reason) - 1U] = '\0';
    } else {
      ev.reason[0] = '\0';
    }
  }

  size_t count() const { return length; }

  const OfflineEvent* at(size_t logical_idx) const {
    if (logical_idx >= length) return nullptr;
    return &items[(head + logical_idx) % OFFLINE_EVENT_RING_CAPACITY];
  }
};

// ---------------- 5. KẾT QUẢ XỬ LÝ LỆNH NGOẠI TUYẾN -----------------------
struct OfflineCommandResult {
  bool ok;
  bool refused;
  uint16_t http_status;
  int8_t device_index;
  bool new_state_on;
  bool state_changed;
  int8_t tone_mode;  // 1=ON/OK, 2=OFF/CLOSE, 3=REFUSED
  const char* reason_code;
  char reply_vi[192];
};

struct SafetyTripResult {
  bool pump_tripped;
  bool siren_tripped;
};

struct ConnectivityTransition {
  bool transitioned;
  bool became_offline;
  bool became_online;
  bool close_door_for_safety;
  bool trigger_disconnect_beep;
  bool need_resync;
};

// ---------------- 6. MÁY TRẠNG THÁI NGOẠI TUYẾN TRUNG TÂM ------------------
class OfflineFsm {
 public:
  OfflineFsm()
      : server_online_(false),
        has_ever_been_online_(false),
        offline_since_ms_(0UL),
        last_offline_duration_ms_(0UL),
        pending_resync_(false),
        offline_dirty_mask_(0U),
        pump_timer_active_(false),
        pump_started_ms_(0UL),
        pump_safety_locked_until_wet_(false),
        siren_offline_timer_active_(false),
        siren_started_ms_(0UL),
        wifi_disconnected_since_ms_(0UL),
        wifi_disconnect_tracked_(false) {
    for (uint8_t i = 0U; i < DEV_COUNT; ++i) {
      device_states_[i] = false;
    }
  }

  void begin(unsigned long now_ms) {
    offline_since_ms_ = now_ms;
    wifi_disconnected_since_ms_ = now_ms;
    wifi_disconnect_tracked_ = true;
  }

  bool isServerOnline() const { return server_online_; }
  unsigned long offlineSinceMs() const { return offline_since_ms_; }
  unsigned long lastOfflineDurationMs() const { return last_offline_duration_ms_; }
  bool hasPendingResync() const { return pending_resync_; }
  uint8_t offlineDirtyMask() const { return offline_dirty_mask_; }
  const OfflineEventRing& events() const { return events_; }
  bool isPumpSafetyLocked() const { return pump_safety_locked_until_wet_; }

  bool getDeviceState(uint8_t dev_idx) const {
    if (dev_idx >= DEV_COUNT) return false;
    return device_states_[dev_idx];
  }

  bool isDeviceDirtyOffline(uint8_t dev_idx) const {
    if (dev_idx >= DEV_COUNT) return false;
    return (offline_dirty_mask_ & static_cast<uint8_t>(1U << dev_idx)) != 0U;
  }

  // Addendum A3: Kiểm tra cấp firmware trước khi mở cửa chính
  bool canSetMainDoor(bool open_door) const {
    if (open_door && !server_online_) {
      return OFFLINE_MAIN_DOOR_OPEN_ALLOWED;  // Luôn false khi ngoại tuyến
    }
    return true;
  }

  // Kiểm tra điều kiện bật SoftAP dự phòng sau WIFI_AP_FALLBACK_AFTER_MS (A1)
  bool shouldEnableSoftAp(bool wifi_sta_connected, unsigned long now_ms) {
    if (wifi_sta_connected) {
      wifi_disconnect_tracked_ = false;
      return false;
    }
    if (!wifi_disconnect_tracked_) {
      wifi_disconnect_tracked_ = true;
      wifi_disconnected_since_ms_ = now_ms;
      return false;
    }
    return (now_ms - wifi_disconnected_since_ms_) >= WIFI_AP_FALLBACK_AFTER_MS;
  }

  // Cập nhật chuyển trạng thái kết nối máy chủ (ONLINE <-> OFFLINE)
  ConnectivityTransition onConnectivityChanged(bool online_now, unsigned long now_ms) {
    ConnectivityTransition tr{false, false, false, false, false, false};

    if (online_now == server_online_) {
      return tr;
    }

    tr.transitioned = true;
    if (!online_now) {
      // ONLINE -> OFFLINE
      server_online_ = false;
      offline_since_ms_ = now_ms;
      tr.became_offline = true;
      tr.close_door_for_safety = true;
      tr.trigger_disconnect_beep = has_ever_been_online_;

      if (device_states_[DEV_MAIN_DOOR]) {
        device_states_[DEV_MAIN_DOOR] = false;
        offline_dirty_mask_ |= static_cast<uint8_t>(1U << DEV_MAIN_DOOR);
        events_.push(DEV_MAIN_DOOR, false, "offline_fail_safe", 0UL);
      }
      if (device_states_[DEV_ALARM_SIREN]) {
        siren_offline_timer_active_ = true;
        siren_started_ms_ = now_ms;
      }
    } else {
      // OFFLINE -> ONLINE
      server_online_ = true;
      last_offline_duration_ms_ = now_ms - offline_since_ms_;
      siren_offline_timer_active_ = false;
      tr.became_online = true;

      // Luôn yêu cầu đồng bộ lại (A4) nếu có thay đổi ngoại tuyến hoặc vừa khôi phục từ mất kết nối
      if (offline_dirty_mask_ != 0U || events_.count() > 0U || has_ever_been_online_) {
        pending_resync_ = true;
        tr.need_resync = true;
      }
      has_ever_been_online_ = true;
    }
    return tr;
  }

  // Đồng bộ trạng thái vật lý (được gọi khi chân GPIO/Servo thực sự đổi trạng thái)
  void syncHardwareState(uint8_t dev_idx, bool state_on, unsigned long now_ms = 0UL) {
    if (dev_idx >= DEV_COUNT) return;
    const bool prev = device_states_[dev_idx];
    device_states_[dev_idx] = state_on;

    if (dev_idx == DEV_GARDEN_PUMP) {
      if (state_on && !prev) {
        pump_timer_active_ = true;
        pump_started_ms_ = now_ms;
      } else if (!state_on) {
        pump_timer_active_ = false;
      }
    } else if (dev_idx == DEV_ALARM_SIREN) {
      if (state_on && !server_online_) {
        if (!prev || !siren_offline_timer_active_) {
          siren_offline_timer_active_ = true;
          siren_started_ms_ = now_ms;
        }
      } else if (!state_on) {
        siren_offline_timer_active_ = false;
      }
    }
  }

  // Ghi nhận thay đổi thiết bị kèm đánh dấu dirty + sự kiện A4 nếu đang ngoại tuyến
  void recordDeviceChange(uint8_t dev_idx,
                          bool state_on,
                          unsigned long now_ms,
                          const char* reason,
                          bool clear_pump_safety_lock = false) {
    if (dev_idx >= DEV_COUNT) return;
    if (dev_idx == DEV_GARDEN_PUMP && clear_pump_safety_lock) {
      pump_safety_locked_until_wet_ = false;
    }
    syncHardwareState(dev_idx, state_on, now_ms);
    if (!server_online_) {
      offline_dirty_mask_ |= static_cast<uint8_t>(1U << dev_idx);
      events_.push(dev_idx, state_on, reason, now_ms - offline_since_ms_);
    }
  }

  // Xóa khóa bảo vệ bơm khi độ ẩm đất đã phục hồi >= 70%
  void notifySoilMoistureWet() { pump_safety_locked_until_wet_ = false; }

  // Đếm ngược bộ hẹn giờ an toàn bơm (120s) và còi báo động ngoại tuyến (30s)
  SafetyTripResult tickSafetyTimers(unsigned long now_ms) {
    SafetyTripResult res{false, false};

    if (device_states_[DEV_GARDEN_PUMP] && pump_timer_active_ &&
        (now_ms - pump_started_ms_ >= PUMP_MAX_CONTINUOUS_RUN_MS)) {
      device_states_[DEV_GARDEN_PUMP] = false;
      pump_timer_active_ = false;
      pump_safety_locked_until_wet_ = true;
      res.pump_tripped = true;
      if (!server_online_) {
        offline_dirty_mask_ |= static_cast<uint8_t>(1U << DEV_GARDEN_PUMP);
        events_.push(DEV_GARDEN_PUMP, false, "pump_max_runtime", now_ms - offline_since_ms_);
      }
    }

    if (!server_online_ && device_states_[DEV_ALARM_SIREN] && siren_offline_timer_active_ &&
        (now_ms - siren_started_ms_ >= SIREN_MAX_OFFLINE_RUN_MS)) {
      device_states_[DEV_ALARM_SIREN] = false;
      siren_offline_timer_active_ = false;
      res.siren_tripped = true;
      offline_dirty_mask_ |= static_cast<uint8_t>(1U << DEV_ALARM_SIREN);
      events_.push(DEV_ALARM_SIREN, false, "siren_max_runtime", now_ms - offline_since_ms_);
    }

    return res;
  }

  void markResyncCompleted() {
    pending_resync_ = false;
    offline_dirty_mask_ = 0U;
    events_.clear();
  }

  OfflineCommandResult handleOfflineTextCommand(const char* raw_text,
                                                unsigned long now_ms,
                                                const char* source_reason = "offline_voice") {
    const ParsedOfflineCommand parsed = parseTextOfflineCommand(raw_text);
    return executeParsedCommand(parsed, now_ms, source_reason);
  }

  OfflineCommandResult handleOfflineStructuredCommand(const char* device_id,
                                                      const char* action,
                                                      unsigned long now_ms,
                                                      const char* source_reason = "offline_voice") {
    const ParsedOfflineCommand parsed = parseStructuredOfflineCommand(device_id, action);
    return executeParsedCommand(parsed, now_ms, source_reason);
  }

 private:
  OfflineCommandResult executeParsedCommand(const ParsedOfflineCommand& parsed,
                                            unsigned long now_ms,
                                            const char* source_reason) {
    OfflineCommandResult res{};
    res.ok = false;
    res.refused = true;
    res.http_status = 400U;
    res.device_index = -1;
    res.new_state_on = false;
    res.state_changed = false;
    res.tone_mode = 3;
    res.reason_code = REASON_CUSTOM_FORBIDDEN;
    strncpy(res.reply_vi, REPLY_CUSTOM_FORBIDDEN_VI, sizeof(res.reply_vi) - 1U);

    if (parsed.kind == OfflineIntentKind::STATUS_QUERY && OFFLINE_STATUS_QUERY_ALLOWED) {
      res.ok = true;
      res.refused = false;
      res.http_status = 200U;
      res.device_index = parsed.device_index;
      res.state_changed = false;
      res.tone_mode = 1;
      res.reason_code = REASON_STATUS_OK;
      snprintf(res.reply_vi,
               sizeof(res.reply_vi),
               "Trạng thái ngoại tuyến: cửa %s, đèn khách %s, đèn ngủ %s, bơm %s, còi %s, loa %s.",
               device_states_[DEV_MAIN_DOOR] ? "mở" : "đóng",
               device_states_[DEV_LIVING_ROOM_LIGHT] ? "bật" : "tắt",
               device_states_[DEV_BEDROOM_LIGHT] ? "bật" : "tắt",
               device_states_[DEV_GARDEN_PUMP] ? "bật" : "tắt",
               device_states_[DEV_ALARM_SIREN] ? "bật" : "tắt",
               device_states_[DEV_SPEAKER_AMP] ? "bật" : "tắt");
      return res;
    }

    if (parsed.kind != OfflineIntentKind::DEVICE_ACTION || parsed.device_index < 0 ||
        parsed.device_index >= DEV_COUNT) {
      return res;
    }

    const uint8_t idx = static_cast<uint8_t>(parsed.device_index);
    const DeviceOfflinePolicy* policy = getDevicePolicy(idx);
    if (!policy) return res;

    const bool target_on =
        (parsed.action == OfflineAction::TURN_ON || parsed.action == OfflineAction::OPEN);

    // Addendum A3: Tuyệt đối cấm mở cửa chính khi ngoại tuyến
    if (idx == DEV_MAIN_DOOR && target_on) {
      device_states_[DEV_MAIN_DOOR] = false;
      res.ok = false;
      res.refused = true;
      res.http_status = 403U;
      res.device_index = DEV_MAIN_DOOR;
      res.new_state_on = false;
      res.state_changed = false;
      res.tone_mode = 3;
      res.reason_code = REASON_DOOR_OPEN_FORBIDDEN;
      strncpy(res.reply_vi, REPLY_DOOR_OPEN_FORBIDDEN_VI, sizeof(res.reply_vi) - 1U);
      res.reply_vi[sizeof(res.reply_vi) - 1U] = '\0';
      return res;
    }

    // Kiểm tra bảng chính sách SSOT
    if ((target_on && !policy->allow_offline_on_or_open) ||
        (!target_on && !policy->allow_offline_off_or_close)) {
      return res;
    }

    recordDeviceChange(idx, target_on, now_ms, source_reason, /*clear_pump_safety_lock=*/true);

    res.ok = true;
    res.refused = false;
    res.http_status = 200U;
    res.device_index = static_cast<int8_t>(idx);
    res.new_state_on = target_on;
    res.state_changed = true;
    res.tone_mode = target_on ? 1 : 2;
    res.reason_code = REASON_OK;

    if (idx == DEV_MAIN_DOOR) {
      strncpy(res.reply_vi, REPLY_DOOR_CLOSED_OFFLINE_VI, sizeof(res.reply_vi) - 1U);
      res.reply_vi[sizeof(res.reply_vi) - 1U] = '\0';
    } else {
      snprintf(res.reply_vi,
               sizeof(res.reply_vi),
               "Đã %s %s ở chế độ ngoại tuyến.",
               target_on ? "bật" : "tắt",
               policy->name_vi);
    }
    return res;
  }

  bool server_online_;
  bool has_ever_been_online_;
  unsigned long offline_since_ms_;
  unsigned long last_offline_duration_ms_;
  bool pending_resync_;
  uint8_t offline_dirty_mask_;
  OfflineEventRing events_;
  bool device_states_[DEV_COUNT];

  bool pump_timer_active_;
  unsigned long pump_started_ms_;
  bool pump_safety_locked_until_wet_;

  bool siren_offline_timer_active_;
  unsigned long siren_started_ms_;

  unsigned long wifi_disconnected_since_ms_;
  bool wifi_disconnect_tracked_;
};

}  // namespace offline
}  // namespace smarthome

#endif  // SMARTHOME_OFFLINE_FSM_H
