package vn.edu.hust.seee.smarthome.ui.main.tabs

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import vn.edu.hust.seee.smarthome.ui.main.components.DeviceRowCard
import vn.edu.hust.seee.smarthome.ui.main.components.TierChip
import vn.edu.hust.seee.smarthome.ui.main.models.CountdownTimerItem
import vn.edu.hust.seee.smarthome.ui.main.models.HardwareDevice

@Composable
fun DevicesScreenTab(
  devices: List<HardwareDevice>,
  deviceStates: Map<String, Boolean>,
  selectedRoomFilter: String,
  onSelectRoomFilter: (String) -> Unit,
  onToggleDevice: (HardwareDevice, Boolean) -> Unit,
  activeTimers: List<CountdownTimerItem>,
  onCreateTimerShortcut: () -> Unit,
  accentCyan: Color,
  cardBg: Color,
  cardBorder: Color,
  bgDark: Color,
  textPrimary: Color,
  textSecondary: Color,
  modifier: Modifier = Modifier,
) {
  Column(
    modifier = modifier.fillMaxWidth(),
    verticalArrangement = Arrangement.spacedBy(16.dp),
  ) {
    // 1. Device list card with room filters
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .clip(RoundedCornerShape(16.dp))
        .background(cardBg)
        .border(1.dp, cardBorder, RoundedCornerShape(16.dp))
        .padding(16.dp),
      verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
      Row(
        modifier = Modifier
          .fillMaxWidth()
          .horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
      ) {
        listOf("Tất cả", "Phòng khách", "Phòng ngủ", "Lối vào", "Sân vườn").forEach { room ->
          TierChip(
            label = room,
            selected = selectedRoomFilter == room,
            activeColor = accentCyan,
            onClick = { onSelectRoomFilter(room) },
            modifier = Modifier.padding(end = 2.dp),
          )
        }
      }

      val filteredDevices = if (selectedRoomFilter == "Tất cả") {
        devices
      } else {
        devices.filter { it.pinInfo == selectedRoomFilter }
      }

      filteredDevices.forEach { dev ->
        val isOn = deviceStates[dev.serverId] == true
        DeviceRowCard(
          dev = dev,
          isOn = isOn,
          accentCyan = accentCyan,
          cardBorder = cardBorder,
          textPrimary = textPrimary,
          textSecondary = textSecondary,
          onToggle = { newValue -> onToggleDevice(dev, newValue) },
        )
      }
    }

    // 2. Schedule Card
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .clip(RoundedCornerShape(16.dp))
        .background(cardBg)
        .border(1.dp, cardBorder, RoundedCornerShape(16.dp))
        .padding(16.dp),
      verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
      ) {
        Text(
          text = "Lịch",
          color = textPrimary,
          fontSize = 16.sp,
          fontWeight = FontWeight.Medium,
        )
        Text(
          text = "Tạo lịch",
          color = accentCyan,
          fontSize = 13.sp,
          fontWeight = FontWeight.Medium,
          modifier = Modifier
            .clip(RoundedCornerShape(8.dp))
            .clickable { onCreateTimerShortcut() }
            .padding(horizontal = 6.dp, vertical = 4.dp),
        )
      }
      if (activeTimers.isEmpty()) {
        Text(
          text = "Chưa có lịch",
          color = textSecondary,
          fontSize = 13.sp,
          fontWeight = FontWeight.Normal,
        )
      } else {
        activeTimers.forEach { t ->
          Row(
            modifier = Modifier
              .fillMaxWidth()
              .clip(RoundedCornerShape(12.dp))
              .background(bgDark)
              .border(1.dp, cardBorder, RoundedCornerShape(12.dp))
              .padding(horizontal = 12.dp, vertical = 10.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
          ) {
            Text(
              text = "${if (t.targetStateOn) "Bật" else "Tắt"} ${t.deviceName}",
              color = textPrimary,
              fontSize = 13.sp,
              fontWeight = FontWeight.Normal,
            )
            Text(
              text = "Còn ${t.remainingSeconds} giây",
              color = textSecondary,
              fontSize = 12.sp,
              fontWeight = FontWeight.Medium,
            )
          }
        }
      }
    }
  }
}
