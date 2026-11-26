#ifndef SMARTHOME_OFFLINE_COMMAND_GRAMMAR_H
#define SMARTHOME_OFFLINE_COMMAND_GRAMMAR_H

/*
 * ============================================================================
 * Bộ phân tích câu lệnh ngoại tuyến thuần C++ (không cấp phát heap, không Arduino).
 * Tuân thủ Addendum A2 & A3:
 *  - Chỉ chấp nhận tập lệnh bật/tắt cơ bản cố định cho 6 thiết bị chuẩn + hỏi trạng thái.
 *  - KHÔNG phân biệt vai trò Tầng 1/2/3 khi ngoại tuyến.
 *  - Từ chối mọi khẩu lệnh tùy chỉnh, hẹn giờ, đặt lịch, luật IF-ELSE và thiết bị ngoài danh mục.
 *  - Nhận diện rõ mọi nỗ lực mở main_door để OfflineFsm & phần cứng khóa cứng (A3).
 * ============================================================================
 */

#include <ctype.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "offline_safety_config.h"

namespace smarthome {
namespace offline {

enum class OfflineIntentKind : uint8_t {
  DEVICE_ACTION = 0,
  STATUS_QUERY = 1,
  REFUSE_CUSTOM_OR_ADVANCED = 2,
  INVALID_UNKNOWN = 3
};

enum class OfflineAction : uint8_t {
  NONE = 0,
  TURN_ON = 1,
  TURN_OFF = 2,
  OPEN = 3,
  CLOSE = 4
};

struct ParsedOfflineCommand {
  OfflineIntentKind kind;
  int8_t device_index;
  OfflineAction action;
  const char* reason_code;
  bool is_door_open_attempt;
};

inline char foldUnicodeCodepoint(uint32_t cp) {
  if (cp < 0x80U) {
    char c = static_cast<char>(cp);
    if (c >= 'A' && c <= 'Z') return static_cast<char>(c - 'A' + 'a');
    if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_') return c;
    return ' ';
  }
  // Latin-1 Supplement
  if ((cp >= 0x00C0U && cp <= 0x00C5U) || (cp >= 0x00E0U && cp <= 0x00E5U)) return 'a';
  if ((cp >= 0x00C8U && cp <= 0x00CBU) || (cp >= 0x00E8U && cp <= 0x00EBU)) return 'e';
  if ((cp >= 0x00CCU && cp <= 0x00CFU) || (cp >= 0x00ECU && cp <= 0x00EFU)) return 'i';
  if ((cp >= 0x00D2U && cp <= 0x00D6U) || (cp >= 0x00F2U && cp <= 0x00F6U)) return 'o';
  if ((cp >= 0x00D9U && cp <= 0x00DCU) || (cp >= 0x00F9U && cp <= 0x00FCU)) return 'u';
  if (cp == 0x00DDU || cp == 0x00FDU) return 'y';
  // Latin Extended-A / B (Vietnamese)
  if (cp == 0x0102U || cp == 0x0103U) return 'a';
  if (cp == 0x0110U || cp == 0x0111U) return 'd';
  if (cp == 0x0128U || cp == 0x0129U) return 'i';
  if (cp == 0x0168U || cp == 0x0169U) return 'u';
  if (cp == 0x01A0U || cp == 0x01A1U) return 'o';
  if (cp == 0x01AFU || cp == 0x01B0U) return 'u';
  // Latin Extended Additional (Vietnamese tone marks U+1EA0..U+1EF9)
  if (cp >= 0x1EA0U && cp <= 0x1EB7U) return 'a';
  if (cp >= 0x1EB8U && cp <= 0x1EC7U) return 'e';
  if (cp >= 0x1EC8U && cp <= 0x1ECBU) return 'i';
  if (cp >= 0x1ECCU && cp <= 0x1EE3U) return 'o';
  if (cp >= 0x1EE4U && cp <= 0x1EF1U) return 'u';
  if (cp >= 0x1EF2U && cp <= 0x1EF9U) return 'y';
  return ' ';
}

// Chuyển chuỗi UTF-8 tiếng Việt sang ASCII thường, không dấu, gộp khoảng trắng đơn.
inline size_t normalizeVietnameseAscii(const char* src, char* dst, size_t dst_cap) {
  if (!dst || dst_cap == 0U) return 0U;
  if (!src) {
    dst[0] = '\0';
    return 0U;
  }

  size_t out = 0U;
  bool last_space = true;
  const uint8_t* p = reinterpret_cast<const uint8_t*>(src);

  while (*p != 0U && out + 1U < dst_cap) {
    uint32_t cp = 0U;
    if ((*p & 0x80U) == 0U) {
      cp = *p++;
    } else if ((*p & 0xE0U) == 0xC0U && (p[1] & 0xC0U) == 0x80U) {
      cp = (static_cast<uint32_t>(p[0] & 0x1FU) << 6U) | static_cast<uint32_t>(p[1] & 0x3FU);
      p += 2;
    } else if ((*p & 0xF0U) == 0xE0U && (p[1] & 0xC0U) == 0x80U && (p[2] & 0xC0U) == 0x80U) {
      cp = (static_cast<uint32_t>(p[0] & 0x0FU) << 12U) |
           (static_cast<uint32_t>(p[1] & 0x3FU) << 6U) |
           static_cast<uint32_t>(p[2] & 0x3FU);
      p += 3;
    } else if ((*p & 0xF8U) == 0xF0U && (p[1] & 0xC0U) == 0x80U && (p[2] & 0xC0U) == 0x80U &&
               (p[3] & 0xC0U) == 0x80U) {
      cp = 0x20U;
      p += 4;
    } else {
      cp = 0x20U;
      ++p;
    }

    char folded = foldUnicodeCodepoint(cp);
    if (folded == ' ') {
      if (!last_space) {
        dst[out++] = ' ';
        last_space = true;
      }
    } else {
      dst[out++] = folded;
      last_space = false;
    }
  }

  while (out > 0U && dst[out - 1U] == ' ') {
    --out;
  }
  dst[out] = '\0';
  return out;
}

inline bool containsPhrase(const char* norm, const char* phrase) {
  if (!norm || !phrase || phrase[0] == '\0') return false;
  const size_t phrase_len = strlen(phrase);
  const char* p = norm;
  while ((p = strstr(p, phrase)) != nullptr) {
    const bool left_ok = (p == norm || *(p - 1) == ' ');
    const char after = p[phrase_len];
    const bool right_ok = (after == '\0' || after == ' ');
    if (left_ok && right_ok) return true;
    ++p;
  }
  return false;
}

inline int8_t resolveCanonicalDeviceId(const char* raw_id) {
  char norm[64];
  normalizeVietnameseAscii(raw_id, norm, sizeof(norm));
  if (norm[0] == '\0') return -1;

  for (uint8_t i = 0U; i < DEV_COUNT; ++i) {
    if (strcmp(norm, DEVICE_POLICIES[i].id) == 0) {
      return static_cast<int8_t>(i);
    }
  }
  // Aliases tương thích với backend/engine/constants_and_time.py
  if (strcmp(norm, "speaker_relay") == 0 || strcmp(norm, "pam8403") == 0 ||
      strcmp(norm, "speaker_power") == 0 || strcmp(norm, "audio_amp") == 0) {
    return static_cast<int8_t>(DEV_SPEAKER_AMP);
  }
  return -1;
}

inline ParsedOfflineCommand parseStructuredOfflineCommand(const char* device_id,
                                                          const char* action_raw) {
  ParsedOfflineCommand out{OfflineIntentKind::REFUSE_CUSTOM_OR_ADVANCED, -1, OfflineAction::NONE,
                           REASON_CUSTOM_FORBIDDEN, false};

  char act[48];
  normalizeVietnameseAscii(action_raw, act, sizeof(act));

  if (strcmp(act, "status") == 0 || strcmp(act, "query") == 0 || strcmp(act, "get_status") == 0) {
    out.kind = OfflineIntentKind::STATUS_QUERY;
    out.device_index = resolveCanonicalDeviceId(device_id);
    out.action = OfflineAction::NONE;
    out.reason_code = REASON_STATUS_OK;
    return out;
  }

  const int8_t dev_idx = resolveCanonicalDeviceId(device_id);
  if (dev_idx < 0) {
    return out;  // Thiết bị không tồn tại / ngoài danh mục 6 thiết bị chuẩn
  }

  OfflineAction parsed_act = OfflineAction::NONE;
  if (strcmp(act, "turn_on") == 0 || strcmp(act, "on") == 0 || strcmp(act, "1") == 0) {
    parsed_act = (dev_idx == DEV_MAIN_DOOR) ? OfflineAction::OPEN : OfflineAction::TURN_ON;
  } else if (strcmp(act, "turn_off") == 0 || strcmp(act, "off") == 0 || strcmp(act, "0") == 0) {
    parsed_act = (dev_idx == DEV_MAIN_DOOR) ? OfflineAction::CLOSE : OfflineAction::TURN_OFF;
  } else if (strcmp(act, "open") == 0) {
    parsed_act = (dev_idx == DEV_MAIN_DOOR) ? OfflineAction::OPEN : OfflineAction::TURN_ON;
  } else if (strcmp(act, "close") == 0) {
    parsed_act = (dev_idx == DEV_MAIN_DOOR) ? OfflineAction::CLOSE : OfflineAction::TURN_OFF;
  } else {
    return out;  // Hành động tùy chỉnh / nâng cao -> từ chối
  }

  out.kind = OfflineIntentKind::DEVICE_ACTION;
  out.device_index = dev_idx;
  out.action = parsed_act;
  out.is_door_open_attempt = (dev_idx == DEV_MAIN_DOOR &&
                              (parsed_act == OfflineAction::OPEN || parsed_act == OfflineAction::TURN_ON));
  out.reason_code = out.is_door_open_attempt ? REASON_DOOR_OPEN_FORBIDDEN : REASON_OK;
  return out;
}

inline bool isCustomOrScheduleText(const char* norm) {
  static const char* const FORBIDDEN_PHRASES[] = {
      "hen gio",       "dat lich",       "tao lich",       "lich trinh",
      "phut nua",      "giay nua",       "gio nua",        "tu dong",
      "tao luat",      "them luat",      "luat moi",       "luat tu dong",
      "dieu kien",     "neu",            "khi nao",        "tao lenh",
      "them lenh",     "lenh tuy chinh", "khau lenh",      "tuy chinh",
      "vung oi",       "kich ban",       "che do ngu",     "che do ra ngoai",
      "che do ve nha", "che do chieu",   "schedule",       "timer",
      "cron",          "custom",         "automation",     "rule",
      "create_timer",  "add_rule",
  };
  const size_t count = sizeof(FORBIDDEN_PHRASES) / sizeof(FORBIDDEN_PHRASES[0]);
  for (size_t i = 0U; i < count; ++i) {
    if (containsPhrase(norm, FORBIDDEN_PHRASES[i])) {
      return true;
    }
  }
  // Phát hiện mẫu "sau X phút / giây / giờ"
  if (containsPhrase(norm, "sau") &&
      (containsPhrase(norm, "phut") || containsPhrase(norm, "giay") || containsPhrase(norm, "gio"))) {
    return true;
  }
  return false;
}

inline bool isStatusQueryText(const char* norm) {
  static const char* const STATUS_PHRASES[] = {
      "trang thai", "tinh trang", "kiem tra", "bao cao",
      "nhiet do",   "do am",      "status",   "state",
  };
  const size_t count = sizeof(STATUS_PHRASES) / sizeof(STATUS_PHRASES[0]);
  for (size_t i = 0U; i < count; ++i) {
    if (containsPhrase(norm, STATUS_PHRASES[i])) {
      return true;
    }
  }
  return false;
}

inline ParsedOfflineCommand parseTextOfflineCommand(const char* raw_text) {
  ParsedOfflineCommand out{OfflineIntentKind::REFUSE_CUSTOM_OR_ADVANCED, -1, OfflineAction::NONE,
                           REASON_CUSTOM_FORBIDDEN, false};

  char norm[224];
  normalizeVietnameseAscii(raw_text, norm, sizeof(norm));
  if (norm[0] == '\0') {
    out.kind = OfflineIntentKind::INVALID_UNKNOWN;
    return out;
  }

  // Addendum A2: KHÔNG kiểm tra hay chặn tag vai trò ([tier3]/[khach]/[stranger]) khi ngoại tuyến.
  // 1. Từ chối lệnh tùy chỉnh, hẹn giờ, đặt lịch, luật IF-ELSE ngay lập tức.
  if (isCustomOrScheduleText(norm)) {
    return out;
  }

  // 2. Xác định động từ bật/mở hoặc tắt/đóng (tách riêng nhóm cửa và nhóm bật/tắt
  //    để tránh chữ "động" trong "báo động" bị hiểu nhầm thành "đóng")
  const bool has_open = containsPhrase(norm, "mo") || containsPhrase(norm, "open") ||
                        containsPhrase(norm, "unlock");
  const bool has_close = containsPhrase(norm, "dong") || containsPhrase(norm, "khoa") ||
                         containsPhrase(norm, "close") || containsPhrase(norm, "lock");
  const bool has_on_dev = containsPhrase(norm, "bat") || containsPhrase(norm, "turn_on") ||
                          containsPhrase(norm, "on") || has_open;
  const bool has_off_dev = containsPhrase(norm, "tat") || containsPhrase(norm, "ngat") ||
                           containsPhrase(norm, "dung") || containsPhrase(norm, "turn_off") ||
                           containsPhrase(norm, "off");

  // 3. Cửa chính (main_door) — kiểm tra riêng để thực thi nghiêm ngặt Addendum A3
  if (containsPhrase(norm, "cua chinh") || containsPhrase(norm, "cua") ||
      containsPhrase(norm, "main_door") || containsPhrase(norm, "door")) {
    const bool door_close = has_close || has_off_dev;
    if (door_close && !has_open) {
      out.kind = OfflineIntentKind::DEVICE_ACTION;
      out.device_index = DEV_MAIN_DOOR;
      out.action = OfflineAction::CLOSE;
      out.is_door_open_attempt = false;
      out.reason_code = REASON_OK;
      return out;
    }
    if (has_open || has_on_dev) {
      out.kind = OfflineIntentKind::DEVICE_ACTION;
      out.device_index = DEV_MAIN_DOOR;
      out.action = OfflineAction::OPEN;
      out.is_door_open_attempt = true;
      out.reason_code = REASON_DOOR_OPEN_FORBIDDEN;
      return out;
    }
    if (isStatusQueryText(norm)) {
      out.kind = OfflineIntentKind::STATUS_QUERY;
      out.device_index = DEV_MAIN_DOOR;
      out.reason_code = REASON_STATUS_OK;
      return out;
    }
    return out;
  }

  // 4. Hỏi trạng thái (chỉ khi không có hành động điều khiển trực tiếp)
  if (!has_on_dev && !has_off_dev && isStatusQueryText(norm)) {
    out.kind = OfflineIntentKind::STATUS_QUERY;
    out.device_index = -1;
    out.action = OfflineAction::NONE;
    out.reason_code = REASON_STATUS_OK;
    return out;
  }

  if (!has_on_dev && !has_off_dev) {
    return out;  // Không phải lệnh bật/tắt cơ bản cố định -> từ chối
  }

  // Nếu có cả 2 nhóm từ (hiếm gặp), ưu tiên tắt vì an toàn hơn
  const bool target_on = has_on_dev && !has_off_dev;

  // 5. Nhận diện 5 thiết bị bật/tắt cơ bản còn lại
  int8_t dev_idx = -1;
  if (containsPhrase(norm, "den phong khach") || containsPhrase(norm, "den khach") ||
      containsPhrase(norm, "phong khach") || containsPhrase(norm, "living_room_light") ||
      containsPhrase(norm, "living light")) {
    dev_idx = DEV_LIVING_ROOM_LIGHT;
  } else if (containsPhrase(norm, "den phong ngu") || containsPhrase(norm, "den ngu") ||
             containsPhrase(norm, "phong ngu") || containsPhrase(norm, "bedroom_light") ||
             containsPhrase(norm, "bedroom light")) {
    dev_idx = DEV_BEDROOM_LIGHT;
  } else if (containsPhrase(norm, "may bom") || containsPhrase(norm, "bom tuoi") ||
             containsPhrase(norm, "tuoi cay") || containsPhrase(norm, "bom nuoc") ||
             containsPhrase(norm, "bom") || containsPhrase(norm, "garden_pump") ||
             containsPhrase(norm, "pump")) {
    dev_idx = DEV_GARDEN_PUMP;
  } else if (containsPhrase(norm, "coi bao dong") || containsPhrase(norm, "bao dong") ||
             containsPhrase(norm, "chuong bao dong") || containsPhrase(norm, "coi") ||
             containsPhrase(norm, "alarm_siren") || containsPhrase(norm, "siren") ||
             containsPhrase(norm, "buzzer")) {
    dev_idx = DEV_ALARM_SIREN;
  } else if (containsPhrase(norm, "nguon mach loa") || containsPhrase(norm, "mach loa") ||
             containsPhrase(norm, "nguon loa") || containsPhrase(norm, "pam8403") ||
             containsPhrase(norm, "speaker_amp") || containsPhrase(norm, "speaker") ||
             containsPhrase(norm, "loa")) {
    dev_idx = DEV_SPEAKER_AMP;
  }

  if (dev_idx < 0) {
    return out;  // Thiết bị không nằm trong 6 thiết bị chuẩn -> từ chối (A2)
  }

  out.kind = OfflineIntentKind::DEVICE_ACTION;
  out.device_index = dev_idx;
  out.action = target_on ? OfflineAction::TURN_ON : OfflineAction::TURN_OFF;
  out.is_door_open_attempt = false;
  out.reason_code = REASON_OK;
  return out;
}

}  // namespace offline
}  // namespace smarthome

#endif  // SMARTHOME_OFFLINE_COMMAND_GRAMMAR_H
