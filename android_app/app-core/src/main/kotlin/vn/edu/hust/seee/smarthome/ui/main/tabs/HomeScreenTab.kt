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
  soilMoisture: Int,
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
  modifier: Modifier = Modifier,
  clockSchedules: List<ClockScheduleItem> = emptyList(),
  automationRules: List<AutomationRuleItem> = emptyList(),
  customScenes: List<CustomSceneItem> = emptyList(),
  onRunScene: (CustomSceneItem) -> Unit = {},
) {
  Column(
    modifier = modifier.fillMaxWidth(),
    verticalArrangement = Arrangement.spacedBy(10.dp),
  ) {
    // 1. Card "Ngôi nhà" (badge "Toàn cảnh", placeholder 3D ~16:9)
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
          text = "Toàn cảnh",
          color = textSecondary,
          fontSize = 12.sp,
          fontWeight = FontWeight.Medium,
          modifier = Modifier
            .clip(RoundedCornerShape(999.dp))
            .border(1.dp, cardBorder, RoundedCornerShape(999.dp))
            .padding(horizontal = 8.dp, vertical = 3.dp),
        )
      }

      Box(
        modifier = Modifier
          .fillMaxWidth()
          .height(92.dp)
          .clip(RoundedCornerShape(12.dp))
          .background(Color(0xFFF4F9F9))
          .border(1.dp, Color(0xFFB9CCCE), RoundedCornerShape(12.dp)),
        contentAlignment = Alignment.Center,
      ) {
        Text(
          text = "Vùng mô hình 3D Toàn cảnh\nThay bằng viewport hiện hữu",
          color = textSecondary,
          fontSize = 12.sp,
          textAlign = TextAlign.Center,
        )
      }
    }

    // 2. Card "Cảm biến" 2-ô grid: Nhiệt độ & Độ ẩm đất (không có ô thứ 3)
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
        text = "Cảm biến",
        color = textPrimary,
        fontSize = 15.sp,
        fontWeight = FontWeight.SemiBold,
      )

      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
      ) {
        // Ô 1: Nhiệt độ
        Column(
          modifier = Modifier
            .weight(1f)
            .clip(RoundedCornerShape(12.dp))
            .background(cardBg)
            .border(1.dp, cardBorder, RoundedCornerShape(12.dp))
            .padding(10.dp),
          verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
          Text(
            text = "Nhiệt độ",
            color = textSecondary,
            fontSize = 12.sp,
          )
          Text(
            text = "${String.format(Locale.US, "%.1f", temperature)}°C",
            color = textPrimary,
            fontSize = 18.sp,
            fontWeight = FontWeight.SemiBold,
          )
          Text(
            text = "Trong nhà",
            color = textSecondary,
            fontSize = 11.sp,
          )
        }

        // Ô 2: Độ ẩm đất
        Column(
          modifier = Modifier
            .weight(1f)
            .clip(RoundedCornerShape(12.dp))
            .background(cardBg)
            .border(1.dp, cardBorder, RoundedCornerShape(12.dp))
            .padding(10.dp),
          verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
          Text(
            text = "Độ ẩm đất",
            color = textSecondary,
            fontSize = 12.sp,
          )
          Text(
            text = "$soilMoisture%",
            color = textPrimary,
            fontSize = 18.sp,
            fontWeight = FontWeight.SemiBold,
          )
          Text(
            text = "Sân vườn",
            color = textSecondary,
            fontSize = 11.sp,
          )
        }
      }
    }

    // 3. Card "Trạng thái an toàn": Cửa chính & Còi báo động
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
        Text(
          text = "Cửa chính",
          color = textPrimary,
          fontSize = 14.sp,
        )
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
        Text(
          text = "Còi báo động",
          color = textPrimary,
          fontSize = 14.sp,
        )
        Text(
          text = if (deviceStates["alarm_siren"] == true) "Đang bật" else "Tắt",
          color = textPrimary,
          fontSize = 14.sp,
          fontWeight = FontWeight.SemiBold,
        )
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
