package vn.edu.hust.seee.smarthome.ui.main.tabs

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.util.Locale
import vn.edu.hust.seee.smarthome.ui.main.LineIcon
import vn.edu.hust.seee.smarthome.ui.main.models.AutomationRuleItem
import vn.edu.hust.seee.smarthome.ui.main.models.ClockScheduleItem
import vn.edu.hust.seee.smarthome.ui.main.models.CountdownTimerItem
import vn.edu.hust.seee.smarthome.ui.main.models.CustomSceneItem
import vn.edu.hust.seee.smarthome.ui.main.models.formatDeviceActionLabel

@Composable
fun HomeScreenTab(
  temperature: Double,
  humidity: Int,
  soilMoisture: Int,
  soundDetected: Boolean,
  soundEventCount: Int,
  isAuthenticated: Boolean,
  selectedTier: Int,
  visibleDevicesCount: Int,
  visibleDeviceIds: Set<String> = emptySet(),
  deviceStates: Map<String, Boolean>,
  activeTimers: List<CountdownTimerItem>,
  accentCyan: Color,
  cardBg: Color,
  cardBorder: Color,
  bgDark: Color,
  textPrimary: Color,
  textSecondary: Color,
  onOpenVoiceSheet: () -> Unit,
  onNavigateToDevices: () -> Unit,
  onNavigateToAuth: () -> Unit = {},
  onNavigateToQr: () -> Unit = {},
  modifier: Modifier = Modifier,
  clockSchedules: List<ClockScheduleItem> = emptyList(),
  automationRules: List<AutomationRuleItem> = emptyList(),
  customScenes: List<CustomSceneItem> = emptyList(),
  onRunScene: (CustomSceneItem) -> Unit = {},
  boardOnline: Boolean = true,
  boardLastSeenVi: String = "",
) {
  Column(
    modifier = modifier.fillMaxWidth(),
    verticalArrangement = Arrangement.spacedBy(10.dp),
  ) {
    if (!isAuthenticated) {
      Column(
        modifier = Modifier
          .fillMaxWidth()
          .clip(RoundedCornerShape(16.dp))
          .background(cardBg)
          .border(1.dp, cardBorder, RoundedCornerShape(16.dp))
          .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
      ) {
        Text(
          text = "Chưa đăng nhập",
          color = textPrimary,
          fontSize = 16.sp,
          fontWeight = FontWeight.SemiBold,
        )
        Text(
          text = "Vui lòng đăng nhập bằng tài khoản được cấp quyền hoặc quét mã QR mời khách để xem trạng thái và điều khiển ngôi nhà.",
          color = textSecondary,
          fontSize = 13.sp,
        )
        Row(
          modifier = Modifier.fillMaxWidth(),
          horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
          Button(
            onClick = onNavigateToAuth,
            colors = ButtonDefaults.buttonColors(containerColor = accentCyan),
            shape = RoundedCornerShape(10.dp),
            modifier = Modifier.weight(1f).height(44.dp),
          ) {
            Text("Đăng nhập", color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Medium)
          }
          Button(
            onClick = onNavigateToQr,
            colors = ButtonDefaults.buttonColors(containerColor = cardBg, contentColor = textPrimary),
            shape = RoundedCornerShape(10.dp),
            modifier = Modifier
              .weight(1f)
              .height(44.dp)
              .border(1.dp, cardBorder, RoundedCornerShape(10.dp)),
          ) {
            Text("Quét mã QR", fontSize = 13.sp, fontWeight = FontWeight.Medium)
          }
        }
      }
      return@Column
    }

    // 1. Card "Ngôi nhà" (tổng quan không gian và số thiết bị đang hoạt động)
    val activeDevicesCount = if (visibleDeviceIds.isNotEmpty()) {
      deviceStates.count { (id, on) -> on && id in visibleDeviceIds }
    } else {
      deviceStates.values.count { it }
    }
    val totalDevs = if (visibleDevicesCount > 0) visibleDevicesCount else deviceStates.size
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .clip(RoundedCornerShape(16.dp))
        .background(cardBg)
        .border(1.dp, cardBorder, RoundedCornerShape(16.dp))
        .padding(12.dp),
      verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
      ) {
        Text(
          text = "Ngôi nhà",
          color = textPrimary,
          fontSize = 15.sp,
          fontWeight = FontWeight.SemiBold,
        )
        Text(
          text = if (boardOnline) "$activeDevicesCount/$totalDevs đang bật" else "Mất kết nối",
          color = if (boardOnline) accentCyan else Color(0xFFC83E3B),
          fontSize = 12.sp,
          fontWeight = FontWeight.Medium,
          modifier = Modifier
            .clip(RoundedCornerShape(999.dp))
            .background(if (boardOnline) Color(0xFFE6F3F2) else Color(0xFFFDECEC))
            .padding(horizontal = 10.dp, vertical = 3.dp),
        )
      }

      if (!boardOnline) {
        Box(
          modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(Color(0xFFFEF5F5))
            .border(1.dp, Color(0xFFEBC8C7), RoundedCornerShape(10.dp))
            .padding(horizontal = 10.dp, vertical = 7.dp),
        ) {
          Text(
            text = "Mạch ESP8266 đang mất kết nối · Lần cuối: ${boardLastSeenVi.ifBlank { "--" }}",
            color = Color(0xFFC83E3B),
            fontSize = 11.sp,
            fontWeight = FontWeight.Medium,
          )
        }
      }

      Column(
        modifier = Modifier
          .fillMaxWidth()
          .clip(RoundedCornerShape(12.dp))
          .background(Color(0xFFF4F9F9))
          .border(1.dp, Color(0xFFD4E5E6), RoundedCornerShape(12.dp))
          .clickable { onNavigateToDevices() }
          .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
      ) {
        Text(
          text = "Tổng quan khu vực hoạt động",
          color = textPrimary,
          fontSize = 13.sp,
          fontWeight = FontWeight.SemiBold,
        )
        Row(
          modifier = Modifier.fillMaxWidth(),
          horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
          val roomChips = buildList {
            add("Phòng khách" to (deviceStates["living_room_light"] == true || deviceStates["speaker_amp"] == true))
            add("Phòng ngủ" to (deviceStates["bedroom_light"] == true))
            if (selectedTier == 1) {
              add("Lối vào" to (deviceStates["main_door"] == true || deviceStates["alarm_siren"] == true))
            }
            if (selectedTier <= 2) {
              add("Sân vườn" to (deviceStates["garden_pump"] == true))
            }
          }
          roomChips.forEach { (roomName, isActive) ->
            Column(
              modifier = Modifier
                .weight(1f)
                .clip(RoundedCornerShape(10.dp))
                .background(if (isActive) Color(0xFFE6F3F2) else cardBg)
                .border(1.dp, if (isActive) accentCyan else cardBorder, RoundedCornerShape(10.dp))
                .padding(horizontal = 6.dp, vertical = 8.dp),
              horizontalAlignment = Alignment.CenterHorizontally,
              verticalArrangement = Arrangement.spacedBy(2.dp),
            ) {
              Text(
                text = roomName,
                color = textPrimary,
                fontSize = 11.sp,
                fontWeight = FontWeight.Medium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
              )
              Text(
                text = if (isActive) "Đang bật" else "Đang nghỉ",
                color = if (isActive) accentCyan else textSecondary,
                fontSize = 10.sp,
                fontWeight = FontWeight.SemiBold,
              )
            }
          }
        }
      }
    }

    // 2. Card "Cảm biến" 2x2 grid: Nhiệt độ DHT11, Độ ẩm DHT11, Độ ẩm đất A0, Âm thanh KY-037
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .clip(RoundedCornerShape(16.dp))
        .background(cardBg)
        .border(1.dp, cardBorder, RoundedCornerShape(16.dp))
        .padding(12.dp),
      verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
      Text(
        text = "Cảm biến môi trường",
        color = textPrimary,
        fontSize = 15.sp,
        fontWeight = FontWeight.SemiBold,
      )

      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
      ) {
        // Ô 1: Nhiệt độ DHT11
        Column(
          modifier = Modifier
            .weight(1f)
            .clip(RoundedCornerShape(12.dp))
            .background(cardBg)
            .border(1.dp, cardBorder, RoundedCornerShape(12.dp))
            .padding(10.dp),
          verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
          Text(text = "Nhiệt độ · DHT11", color = textSecondary, fontSize = 12.sp)
          Text(
            text = "${String.format(Locale.US, "%.1f", temperature)}°C",
            color = textPrimary,
            fontSize = 18.sp,
            fontWeight = FontWeight.SemiBold,
          )
          Text(text = "Trong nhà · D2", color = textSecondary, fontSize = 11.sp)
        }

        // Ô 2: Độ ẩm không khí DHT11
        Column(
          modifier = Modifier
            .weight(1f)
            .clip(RoundedCornerShape(12.dp))
            .background(cardBg)
            .border(1.dp, cardBorder, RoundedCornerShape(12.dp))
            .padding(10.dp),
          verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
          Text(text = "Độ ẩm · DHT11", color = textSecondary, fontSize = 12.sp)
          Text(
            text = "$humidity%",
            color = textPrimary,
            fontSize = 18.sp,
            fontWeight = FontWeight.SemiBold,
          )
          Text(text = "Không khí · D2", color = textSecondary, fontSize = 11.sp)
        }
      }

      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
      ) {
        // Ô 3: Độ ẩm đất A0
        Column(
          modifier = Modifier
            .weight(1f)
            .clip(RoundedCornerShape(12.dp))
            .background(cardBg)
            .border(1.dp, cardBorder, RoundedCornerShape(12.dp))
            .padding(10.dp),
          verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
          Text(text = "Độ ẩm đất · A0", color = textSecondary, fontSize = 12.sp)
          Text(
            text = "$soilMoisture%",
            color = textPrimary,
            fontSize = 18.sp,
            fontWeight = FontWeight.SemiBold,
          )
          Text(text = "Sân vườn · A0", color = textSecondary, fontSize = 11.sp)
        }

        // Ô 4: Âm thanh KY-037
        Column(
          modifier = Modifier
            .weight(1f)
            .clip(RoundedCornerShape(12.dp))
            .background(cardBg)
            .border(1.dp, cardBorder, RoundedCornerShape(12.dp))
            .padding(10.dp),
          verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
          Text(text = "Âm thanh · KY-037", color = textSecondary, fontSize = 12.sp)
          Text(
            text = if (soundDetected) "Có tiếng động" else "Yên tĩnh",
            color = if (soundDetected) accentCyan else textPrimary,
            fontSize = 16.sp,
            fontWeight = FontWeight.SemiBold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
          )
          Text(text = "D5 · $soundEventCount sự kiện", color = textSecondary, fontSize = 11.sp)
        }
      }
    }

    // 3. Card "Trạng thái an toàn": chỉ hiển thị cho Chủ nhà (Cấp 1)
    if (selectedTier == 1) {
      Column(
        modifier = Modifier
          .fillMaxWidth()
          .clip(RoundedCornerShape(16.dp))
          .background(cardBg)
          .border(1.dp, cardBorder, RoundedCornerShape(16.dp))
          .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
      ) {
        Text(
          text = "Trạng thái an toàn",
          color = textPrimary,
          fontSize = 15.sp,
          fontWeight = FontWeight.SemiBold,
        )

        Row(
          modifier = Modifier.fillMaxWidth(),
          horizontalArrangement = Arrangement.SpaceBetween,
          verticalAlignment = Alignment.CenterVertically,
        ) {
          Text(text = "Cửa chính", color = textPrimary, fontSize = 14.sp)
          Text(
            text = if (deviceStates["main_door"] == true) "Đang mở" else "Đang khóa",
            color = textPrimary,
            fontSize = 14.sp,
            fontWeight = FontWeight.SemiBold,
          )
        }

        Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(cardBorder))

        Row(
          modifier = Modifier.fillMaxWidth(),
          horizontalArrangement = Arrangement.SpaceBetween,
          verticalAlignment = Alignment.CenterVertically,
        ) {
          Text(text = "Còi báo động", color = textPrimary, fontSize = 14.sp)
          Text(
            text = if (deviceStates["alarm_siren"] == true) "Đang bật" else "Đang tắt",
            color = textPrimary,
            fontSize = 14.sp,
            fontWeight = FontWeight.SemiBold,
          )
        }
      }
    }

    // 3b. Card ngữ cảnh nhanh (Multi-step scenes)
    val enabledScenes = customScenes.filter { it.enabled }
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .clip(RoundedCornerShape(16.dp))
        .background(cardBg)
        .border(1.dp, cardBorder, RoundedCornerShape(16.dp))
        .padding(12.dp),
      verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
      ) {
        Text(
          text = "Ngữ cảnh nhanh",
          color = textPrimary,
          fontSize = 15.sp,
          fontWeight = FontWeight.SemiBold,
        )
        Text(
          text = "Quản lý",
          color = accentCyan,
          fontSize = 12.sp,
          fontWeight = FontWeight.Medium,
          modifier = Modifier
            .clip(RoundedCornerShape(8.dp))
            .clickable { onNavigateToDevices() }
            .padding(horizontal = 6.dp, vertical = 2.dp),
        )
      }

      if (enabledScenes.isEmpty()) {
        Text(
          text = "Chưa có ngữ cảnh. Mở tab Thiết bị để tạo lệnh nhiều bước.",
          color = textSecondary,
          fontSize = 12.sp,
        )
      } else {
        enabledScenes.take(4).forEach { scene ->
          Row(
            modifier = Modifier
              .fillMaxWidth()
              .clip(RoundedCornerShape(12.dp))
              .background(bgDark)
              .border(1.dp, cardBorder, RoundedCornerShape(12.dp))
              .padding(horizontal = 12.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
          ) {
            Column(
              modifier = Modifier.weight(1f).padding(end = 8.dp),
              verticalArrangement = Arrangement.spacedBy(2.dp),
            ) {
              Text(
                text = scene.phrase,
                color = textPrimary,
                fontSize = 13.sp,
                fontWeight = FontWeight.Medium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
              )
              if (scene.stepsSummary.isNotBlank()) {
                Text(
                  text = scene.stepsSummary,
                  color = textSecondary,
                  fontSize = 11.sp,
                  maxLines = 1,
                  overflow = TextOverflow.Ellipsis,
                )
              }
            }
            Button(
              onClick = { onRunScene(scene) },
              colors = ButtonDefaults.buttonColors(containerColor = accentCyan),
              shape = RoundedCornerShape(8.dp),
              contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp),
              modifier = Modifier.height(32.dp),
            ) {
              Text(
                text = "Chạy",
                color = Color.White,
                fontSize = 12.sp,
                fontWeight = FontWeight.Medium,
              )
            }
          }
        }
      }
    }

    // Card lịch & tự động hóa sắp tới (nếu có)
    val activeSchedules = clockSchedules.filter { it.enabled }
    val activeRules = automationRules.filter { it.enabled }
    if (activeTimers.isNotEmpty() || activeSchedules.isNotEmpty() || activeRules.isNotEmpty()) {
      Column(
        modifier = Modifier
          .fillMaxWidth()
          .clip(RoundedCornerShape(16.dp))
          .background(cardBg)
          .border(1.dp, cardBorder, RoundedCornerShape(16.dp))
          .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
      ) {
        Row(
          modifier = Modifier.fillMaxWidth(),
          horizontalArrangement = Arrangement.SpaceBetween,
          verticalAlignment = Alignment.CenterVertically,
        ) {
          Text(
            text = "Lịch & Tự động hóa",
            color = textPrimary,
            fontSize = 15.sp,
            fontWeight = FontWeight.SemiBold,
          )
          Text(
            text = "Chi tiết",
            color = accentCyan,
            fontSize = 12.sp,
            fontWeight = FontWeight.Medium,
            modifier = Modifier
              .clip(RoundedCornerShape(8.dp))
              .clickable { onNavigateToDevices() }
              .padding(horizontal = 6.dp, vertical = 2.dp),
          )
        }
        activeTimers.forEach { t ->
          Row(
            modifier = Modifier
              .fillMaxWidth()
              .clip(RoundedCornerShape(12.dp))
              .background(bgDark)
              .border(1.dp, cardBorder, RoundedCornerShape(12.dp))
              .padding(horizontal = 12.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
          ) {
            Text(
              text = formatDeviceActionLabel(t.deviceId, t.deviceName, t.action),
              color = textPrimary,
              fontSize = 13.sp,
              fontWeight = FontWeight.Normal,
              modifier = Modifier.weight(1f).padding(end = 8.dp),
              maxLines = 1,
              overflow = TextOverflow.Ellipsis,
            )
            Text(
              text = "Còn ${t.remainingLabel.ifBlank { "${t.remainingSeconds} giây" }}",
              color = accentCyan,
              fontSize = 12.sp,
              fontWeight = FontWeight.Medium,
            )
          }
        }
        activeSchedules.take(3).forEach { sc ->
          Row(
            modifier = Modifier
              .fillMaxWidth()
              .clip(RoundedCornerShape(12.dp))
              .background(bgDark)
              .border(1.dp, cardBorder, RoundedCornerShape(12.dp))
              .padding(horizontal = 12.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
          ) {
            Text(
              text = "${sc.timeHhmm} - ${sc.label.ifBlank { formatDeviceActionLabel(sc.deviceId, sc.deviceName, sc.action) }}",
              color = textPrimary,
              fontSize = 13.sp,
              fontWeight = FontWeight.Normal,
              modifier = Modifier.weight(1f).padding(end = 8.dp),
              maxLines = 1,
              overflow = TextOverflow.Ellipsis,
            )
            Text(
              text = if (sc.scheduleType == "daily") "Hằng ngày" else "Một lần",
              color = textSecondary,
              fontSize = 12.sp,
              fontWeight = FontWeight.Medium,
            )
          }
        }
        if (activeRules.isNotEmpty()) {
          Text(
            text = "${activeRules.size} luật liên kết thiết bị đang hoạt động",
            color = textSecondary,
            fontSize = 12.sp,
          )
        }
      }
    }

    // 4. Bottom CTA: "Nói lệnh" (primary) & "Xem thiết bị" (secondary)
    Row(
      modifier = Modifier
        .fillMaxWidth()
        .padding(top = 2.dp),
      horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
      Button(
        onClick = onOpenVoiceSheet,
        colors = ButtonDefaults.buttonColors(containerColor = accentCyan),
        shape = RoundedCornerShape(10.dp),
        modifier = Modifier.weight(1f).height(44.dp),
      ) {
        Row(
          verticalAlignment = Alignment.CenterVertically,
          horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
          LineIcon("mic", Color.White, 18)
          Text(
            text = "Nói lệnh",
            color = Color.White,
            fontSize = 14.sp,
            fontWeight = FontWeight.Medium,
          )
        }
      }

      Button(
        onClick = onNavigateToDevices,
        colors = ButtonDefaults.buttonColors(containerColor = cardBg, contentColor = textPrimary),
        shape = RoundedCornerShape(10.dp),
        modifier = Modifier
          .weight(1f)
          .height(44.dp)
          .border(1.dp, cardBorder, RoundedCornerShape(10.dp)),
      ) {
        Text(
          text = "Xem thiết bị",
          fontSize = 14.sp,
          fontWeight = FontWeight.Medium,
        )
      }
    }
  }
}
