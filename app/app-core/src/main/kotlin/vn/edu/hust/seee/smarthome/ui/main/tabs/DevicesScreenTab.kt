package vn.edu.hust.seee.smarthome.ui.main.tabs

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import vn.edu.hust.seee.smarthome.ui.main.components.DeviceRowCard
import vn.edu.hust.seee.smarthome.ui.main.components.TierChip
import vn.edu.hust.seee.smarthome.ui.main.models.AutomationRuleItem
import vn.edu.hust.seee.smarthome.ui.main.models.ClockScheduleItem
import vn.edu.hust.seee.smarthome.ui.main.models.CountdownTimerItem
import vn.edu.hust.seee.smarthome.ui.main.models.CustomSceneItem
import vn.edu.hust.seee.smarthome.ui.main.models.CustomSceneStep
import vn.edu.hust.seee.smarthome.ui.main.models.HardwareDevice
import vn.edu.hust.seee.smarthome.ui.main.models.canonicalDeviceAction
import vn.edu.hust.seee.smarthome.ui.main.models.canonicalWhenState
import vn.edu.hust.seee.smarthome.ui.main.models.formatDeviceActionLabel

@Composable
fun DevicesScreenTab(
  devices: List<HardwareDevice>,
  deviceStates: Map<String, Boolean>,
  selectedRoomFilter: String,
  onSelectRoomFilter: (String) -> Unit,
  onToggleDevice: (HardwareDevice, Boolean) -> Unit,
  activeTimers: List<CountdownTimerItem>,
  onCreateTimerShortcut: () -> Unit = {},
  accentCyan: Color,
  cardBg: Color,
  cardBorder: Color,
  bgDark: Color,
  textPrimary: Color,
  textSecondary: Color,
  modifier: Modifier = Modifier,
  clockSchedules: List<ClockScheduleItem> = emptyList(),
  automationRules: List<AutomationRuleItem> = emptyList(),
  customScenes: List<CustomSceneItem> = emptyList(),
  automationStatusMessage: String = "",
  automationStatusIsError: Boolean = false,
  onClearAutomationStatus: () -> Unit = {},
  onCreateTimer: (deviceId: String, action: String, seconds: Int, repeat: String) -> Unit = { _, _, _, _ -> },
  onDeleteTimer: (timerId: String) -> Unit = {},
  onCreateSchedule: (deviceId: String, action: String, timeHhmm: String, scheduleType: String, label: String) -> Unit = { _, _, _, _, _ -> },
  onDeleteSchedule: (scheduleId: String) -> Unit = {},
  onCreateRule: (whenDeviceId: String, whenState: String, thenDeviceId: String, thenAction: String, label: String) -> Unit = { _, _, _, _, _ -> },
  onDeleteRule: (ruleId: String) -> Unit = {},
  onCreateScene: (phrase: String, stepsText: String, steps: List<CustomSceneStep>) -> Unit = { _, _, _ -> },
  onDeleteScene: (commandId: String) -> Unit = {},
  onRunScene: (CustomSceneItem) -> Unit = {},
  accentRed: Color = Color(0xFFC83E3B),
  isAuthenticated: Boolean = true,
  selectedTier: Int = 1,
  onNavigateToAuth: () -> Unit = {},
  onNavigateToQr: () -> Unit = {},
  boardOnline: Boolean = true,
  boardLastSeenVi: String = "",
  deviceBoardOnline: Map<String, Boolean> = emptyMap(),
  deviceLastSeenVi: Map<String, String> = emptyMap(),
  onDeviceOfflineTap: (HardwareDevice) -> Unit = {},
) {
  var showCreateTimerDialog by remember { mutableStateOf(false) }
  var showCreateScheduleDialog by remember { mutableStateOf(false) }
  var showCreateRuleDialog by remember { mutableStateOf(false) }
  var showCreateSceneDialog by remember { mutableStateOf(false) }

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
          text = "Yêu cầu đăng nhập",
          color = textPrimary,
          fontSize = 16.sp,
          fontWeight = FontWeight.SemiBold,
        )
        Text(
          text = "Đăng nhập hoặc quét mã QR mời khách để xem danh sách thiết bị thuộc quyền của bạn.",
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

    // 1. Device list card with room filters
    val availableRooms = remember(devices) {
      listOf("Tất cả") + devices.map { it.pinInfo }.distinct()
    }
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .clip(RoundedCornerShape(16.dp))
        .background(cardBg)
        .border(1.dp, cardBorder, RoundedCornerShape(16.dp))
        .padding(10.dp),
      verticalArrangement = Arrangement.spacedBy(5.dp),
    ) {
      Row(
        modifier = Modifier
          .fillMaxWidth()
          .horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
      ) {
        availableRooms.forEach { room ->
          TierChip(
            label = room,
            selected = selectedRoomFilter == room,
            activeColor = accentCyan,
            onClick = { onSelectRoomFilter(room) },
            modifier = Modifier.padding(end = 2.dp),
          )
        }
      }

      if (!boardOnline) {
        Box(
          modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(Color(0xFFFEF5F5))
            .border(1.dp, Color(0xFFEBC8C7), RoundedCornerShape(10.dp))
            .padding(horizontal = 10.dp, vertical = 8.dp),
        ) {
          Text(
            text = buildString {
              append("Mạch ESP8266 đang mất kết nối")
              if (boardLastSeenVi.isNotBlank()) append(" · Lần cuối: $boardLastSeenVi")
              append(". Chuyển sang tab Giọng nói để điều khiển cơ bản ngoại tuyến qua mạng LAN.")
            },
            color = accentRed,
            fontSize = 11.sp,
            fontWeight = FontWeight.Medium,
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
        val devOnline = boardOnline && (deviceBoardOnline[dev.serverId] != false)
        val devLastSeen = deviceLastSeenVi[dev.serverId].orEmpty().ifBlank { boardLastSeenVi }
        DeviceRowCard(
          dev = dev,
          isOn = isOn,
          accentCyan = accentCyan,
          cardBorder = cardBorder,
          textPrimary = textPrimary,
          textSecondary = textSecondary,
          onToggle = { newValue -> onToggleDevice(dev, newValue) },
          boardOnline = devOnline,
          lastSeenVi = devLastSeen,
          onOfflineTap = { onDeviceOfflineTap(dev) },
        )
      }
    }

    // Inline feedback banner for automation & RBAC errors
    if (automationStatusMessage.isNotBlank()) {
      Row(
        modifier = Modifier
          .fillMaxWidth()
          .clip(RoundedCornerShape(12.dp))
          .background(if (automationStatusIsError) Color(0xFFFDF2F2) else Color(0xFFE6F3F2))
          .border(
            1.dp,
            if (automationStatusIsError) accentRed else accentCyan,
            RoundedCornerShape(12.dp),
          )
          .padding(horizontal = 12.dp, vertical = 10.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
      ) {
        Text(
          text = automationStatusMessage,
          color = if (automationStatusIsError) accentRed else textPrimary,
          fontSize = 12.sp,
          fontWeight = FontWeight.Medium,
          modifier = Modifier.weight(1f).padding(end = 8.dp),
        )
        Text(
          text = "Đóng",
          color = if (automationStatusIsError) accentRed else accentCyan,
          fontSize = 12.sp,
          fontWeight = FontWeight.SemiBold,
          modifier = Modifier
            .clip(RoundedCornerShape(6.dp))
            .clickable { onClearAutomationStatus() }
            .padding(horizontal = 6.dp, vertical = 2.dp),
        )
      }
    }

    if (selectedTier in 1..2) {
    // 2. Countdown Timers & Asia/Saigon Clock Schedules Card
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .clip(RoundedCornerShape(16.dp))
        .background(cardBg)
        .border(1.dp, cardBorder, RoundedCornerShape(16.dp))
        .padding(horizontal = 12.dp, vertical = 10.dp),
      verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
      ) {
        Text(
          text = "Hẹn giờ & Lịch giờ (VN)",
          color = textPrimary,
          fontSize = 15.sp,
          fontWeight = FontWeight.SemiBold,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
          CompactActionChip(
            label = "+ Đếm ngược",
            textColor = accentCyan,
            borderColor = accentCyan,
            bgColor = Color(0xFFE6F3F2),
            onClick = { showCreateTimerDialog = true },
          )
          CompactActionChip(
            label = "+ Đặt lịch",
            textColor = accentCyan,
            borderColor = accentCyan,
            bgColor = Color(0xFFE6F3F2),
            onClick = { showCreateScheduleDialog = true },
          )
        }
      }

      if (activeTimers.isEmpty() && clockSchedules.isEmpty()) {
        Text(
          text = "Chưa có hẹn giờ đếm ngược hoặc lịch theo giờ.",
          color = textSecondary,
          fontSize = 12.sp,
        )
      } else {
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
            Column(
              modifier = Modifier.weight(1f).padding(end = 8.dp),
              verticalArrangement = Arrangement.spacedBy(2.dp),
            ) {
              Text(
                text = formatDeviceActionLabel(t.deviceId, t.deviceName, t.action),
                color = textPrimary,
                fontSize = 13.sp,
                fontWeight = FontWeight.Medium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
              )
              val sub = buildString {
                append("Còn ")
                append(t.remainingLabel.ifBlank { "${t.remainingSeconds} giây" })
                if (t.targetVnTime.isNotBlank()) {
                  append(" · Lúc ")
                  append(t.targetVnTime)
                }
                if (t.repeat == "daily") {
                  append(" · Hằng ngày")
                }
              }
              Text(
                text = sub,
                color = textSecondary,
                fontSize = 11.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
              )
            }
            CompactActionChip(
              label = "Xóa",
              textColor = accentRed,
              borderColor = Color(0xFFF1C6C5),
              bgColor = Color(0xFFFDF2F2),
              onClick = { onDeleteTimer(t.id) },
            )
          }
        }

        clockSchedules.forEach { sc ->
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
                text = "${sc.timeHhmm} · ${sc.label.ifBlank { formatDeviceActionLabel(sc.deviceId, sc.deviceName, sc.action) }}",
                color = if (sc.enabled) textPrimary else textSecondary,
                fontSize = 13.sp,
                fontWeight = FontWeight.Medium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
              )
              val modeText = when {
                !sc.enabled -> "Đã chạy"
                sc.scheduleType == "daily" -> "Hằng ngày"
                else -> "Một lần"
              }
              val ownerSuffix = if (sc.ownerName.isNotBlank()) " · ${sc.ownerName}" else ""
              Text(
                text = "$modeText (${sc.timezone})$ownerSuffix",
                color = textSecondary,
                fontSize = 11.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
              )
            }
            CompactActionChip(
              label = "Xóa",
              textColor = accentRed,
              borderColor = Color(0xFFF1C6C5),
              bgColor = Color(0xFFFDF2F2),
              onClick = { onDeleteSchedule(sc.scheduleId) },
            )
          }
        }
      }
    }

    // 3. Linked Automation Rules Card
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .clip(RoundedCornerShape(16.dp))
        .background(cardBg)
        .border(1.dp, cardBorder, RoundedCornerShape(16.dp))
        .padding(horizontal = 12.dp, vertical = 10.dp),
      verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
      ) {
        Text(
          text = "Luật liên kết",
          color = textPrimary,
          fontSize = 15.sp,
          fontWeight = FontWeight.SemiBold,
        )
        CompactActionChip(
          label = "+ Tạo luật",
          textColor = accentCyan,
          borderColor = accentCyan,
          bgColor = Color(0xFFE6F3F2),
          onClick = { showCreateRuleDialog = true },
        )
      }

      if (automationRules.isEmpty()) {
        Text(
          text = "Chưa có luật liên kết (Khi thiết bị A bật/tắt thì điều khiển thiết bị B).",
          color = textSecondary,
          fontSize = 12.sp,
        )
      } else {
        automationRules.forEach { rule ->
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
              val fallbackTitle =
                "Khi ${rule.whenDeviceName} = ${rule.whenState} -> ${formatDeviceActionLabel(rule.thenDeviceId, rule.thenDeviceName, rule.thenAction)}"
              Text(
                text = rule.label.ifBlank { fallbackTitle },
                color = textPrimary,
                fontSize = 13.sp,
                fontWeight = FontWeight.Medium,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
              )
              if (rule.ownerName.isNotBlank()) {
                Text(
                  text = "Tạo bởi ${rule.ownerName} (Tầng ${rule.ownerTier})",
                  color = textSecondary,
                  fontSize = 11.sp,
                  maxLines = 1,
                  overflow = TextOverflow.Ellipsis,
                )
              }
            }
            CompactActionChip(
              label = "Xóa",
              textColor = accentRed,
              borderColor = Color(0xFFF1C6C5),
              bgColor = Color(0xFFFDF2F2),
              onClick = { onDeleteRule(rule.ruleId) },
            )
          }
        }
      }
    }

    // 4. Custom Scenes / Multi-step Commands Card
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .clip(RoundedCornerShape(16.dp))
        .background(cardBg)
        .border(1.dp, cardBorder, RoundedCornerShape(16.dp))
        .padding(horizontal = 12.dp, vertical = 10.dp),
      verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
      ) {
        Text(
          text = "Ngữ cảnh nhiều bước",
          color = textPrimary,
          fontSize = 15.sp,
          fontWeight = FontWeight.SemiBold,
        )
        CompactActionChip(
          label = "+ Tạo ngữ cảnh",
          textColor = accentCyan,
          borderColor = accentCyan,
          bgColor = Color(0xFFE6F3F2),
          onClick = { showCreateSceneDialog = true },
        )
      }

      if (customScenes.isEmpty()) {
        Text(
          text = "Chưa có ngữ cảnh tùy chỉnh (Ví dụ: Đi ngủ -> Tắt đèn, khóa cửa).",
          color = textSecondary,
          fontSize = 12.sp,
        )
      } else {
        customScenes.forEach { scene ->
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
              Text(
                text = scene.stepsSummary.ifBlank { "${scene.steps.size} bước thiết bị" },
                color = textSecondary,
                fontSize = 11.sp,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
              )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
              Button(
                onClick = { onRunScene(scene) },
                colors = ButtonDefaults.buttonColors(containerColor = accentCyan),
                shape = RoundedCornerShape(8.dp),
                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                modifier = Modifier.height(30.dp),
              ) {
                Text(
                  text = "Chạy",
                  color = Color.White,
                  fontSize = 12.sp,
                  fontWeight = FontWeight.Medium,
                )
              }
              CompactActionChip(
                label = "Xóa",
                textColor = accentRed,
                borderColor = Color(0xFFF1C6C5),
                bgColor = Color(0xFFFDF2F2),
                onClick = { onDeleteScene(scene.commandId) },
              )
            }
          }
        }
      }
    }
    }
  }

  if (showCreateTimerDialog) {
    CreateTimerDialog(
      devices = devices,
      accentCyan = accentCyan,
      cardBg = cardBg,
      cardBorder = cardBorder,
      textPrimary = textPrimary,
      textSecondary = textSecondary,
      onDismiss = { showCreateTimerDialog = false },
      onConfirm = { devId, act, secs, rep ->
        showCreateTimerDialog = false
        onCreateTimer(devId, act, secs, rep)
      },
    )
  }

  if (showCreateScheduleDialog) {
    CreateClockScheduleDialog(
      devices = devices,
      accentCyan = accentCyan,
      accentRed = accentRed,
      cardBg = cardBg,
      cardBorder = cardBorder,
      textPrimary = textPrimary,
      textSecondary = textSecondary,
      onDismiss = { showCreateScheduleDialog = false },
      onConfirm = { devId, act, hhmm, type, lbl ->
        showCreateScheduleDialog = false
        onCreateSchedule(devId, act, hhmm, type, lbl)
      },
    )
  }

  if (showCreateRuleDialog) {
    CreateAutomationRuleDialog(
      devices = devices,
      accentCyan = accentCyan,
      accentRed = accentRed,
      cardBg = cardBg,
      cardBorder = cardBorder,
      textPrimary = textPrimary,
      textSecondary = textSecondary,
      onDismiss = { showCreateRuleDialog = false },
      onConfirm = { wDev, wState, tDev, tAct, lbl ->
        showCreateRuleDialog = false
        onCreateRule(wDev, wState, tDev, tAct, lbl)
      },
    )
  }

  if (showCreateSceneDialog) {
    CreateSceneDialog(
      devices = devices,
      accentCyan = accentCyan,
      accentRed = accentRed,
      cardBg = cardBg,
      cardBorder = cardBorder,
      textPrimary = textPrimary,
      textSecondary = textSecondary,
      onDismiss = { showCreateSceneDialog = false },
      onConfirm = { phrase, stepsText, steps ->
        showCreateSceneDialog = false
        onCreateScene(phrase, stepsText, steps)
      },
    )
  }
}

@Composable
private fun CompactActionChip(
  label: String,
  textColor: Color,
  borderColor: Color,
  bgColor: Color,
  onClick: () -> Unit,
) {
  Box(
    modifier = Modifier
      .height(30.dp)
      .clip(RoundedCornerShape(8.dp))
      .background(bgColor)
      .border(1.dp, borderColor, RoundedCornerShape(8.dp))
      .clickable { onClick() }
      .padding(horizontal = 10.dp),
    contentAlignment = Alignment.Center,
  ) {
    Text(
      text = label,
      color = textColor,
      fontSize = 12.sp,
      fontWeight = FontWeight.Medium,
      maxLines = 1,
    )
  }
}

@Composable
private fun DeviceSelectorRow(
  devices: List<HardwareDevice>,
  selectedDeviceId: String,
  onSelectDevice: (String) -> Unit,
  accentCyan: Color,
) {
  Row(
    modifier = Modifier
      .fillMaxWidth()
      .horizontalScroll(rememberScrollState()),
    horizontalArrangement = Arrangement.spacedBy(6.dp),
  ) {
    devices.forEach { dev ->
      TierChip(
        label = dev.name,
        selected = selectedDeviceId == dev.serverId,
        activeColor = accentCyan,
        onClick = { onSelectDevice(dev.serverId) },
      )
    }
  }
}

@Composable
private fun CreateTimerDialog(
  devices: List<HardwareDevice>,
  accentCyan: Color,
  cardBg: Color,
  cardBorder: Color,
  textPrimary: Color,
  textSecondary: Color,
  onDismiss: () -> Unit,
  onConfirm: (deviceId: String, action: String, seconds: Int, repeat: String) -> Unit,
) {
  val defaultDev = devices.firstOrNull()?.serverId ?: "living_room_light"
  var selectedDeviceId by remember { mutableStateOf(defaultDev) }
  var turnOn by remember { mutableStateOf(true) }
  var secondsInput by remember { mutableStateOf("10") }
  var repeatType by remember { mutableStateOf("once") }

  AlertDialog(
    onDismissRequest = onDismiss,
    containerColor = cardBg,
    title = {
      Text("Tạo hẹn giờ đếm ngược", color = textPrimary, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
    },
    text = {
      Column(
        modifier = Modifier.verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(8.dp),
      ) {
        Text("Chọn thiết bị", color = textSecondary, fontSize = 12.sp)
        DeviceSelectorRow(devices, selectedDeviceId, { selectedDeviceId = it }, accentCyan)

        Text("Hành động", color = textSecondary, fontSize = 12.sp)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
          val onTxt = if (selectedDeviceId == "main_door") "Mở" else "Bật"
          val offTxt = if (selectedDeviceId == "main_door") "Khóa" else "Tắt"
          TierChip(onTxt, turnOn, accentCyan, { turnOn = true })
          TierChip(offTxt, !turnOn, accentCyan, { turnOn = false })
        }

        Text("Thời gian (giây)", color = textSecondary, fontSize = 12.sp)
        Row(
          modifier = Modifier.horizontalScroll(rememberScrollState()),
          horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
          listOf("10" to "10s", "30" to "30s", "60" to "1 phút", "300" to "5 phút").forEach { (sec, lbl) ->
            TierChip(lbl, secondsInput == sec, accentCyan, { secondsInput = sec })
          }
        }
        OutlinedTextField(
          value = secondsInput,
          onValueChange = { raw -> secondsInput = raw.filter { it.isDigit() }.take(5) },
          label = { Text("Số giây", fontSize = 12.sp) },
          singleLine = true,
          keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
          colors = OutlinedTextFieldDefaults.colors(
            focusedTextColor = textPrimary,
            unfocusedTextColor = textPrimary,
            focusedBorderColor = accentCyan,
            unfocusedBorderColor = cardBorder,
          ),
          modifier = Modifier.fillMaxWidth(),
        )

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
          TierChip("Một lần", repeatType == "once", accentCyan, { repeatType = "once" })
          TierChip("Hằng ngày", repeatType == "daily", accentCyan, { repeatType = "daily" })
        }
      }
    },
    confirmButton = {
      Button(
        onClick = {
          val secs = secondsInput.toIntOrNull()?.coerceIn(1, 86400) ?: 10
          onConfirm(selectedDeviceId, canonicalDeviceAction(selectedDeviceId, turnOn), secs, repeatType)
        },
        colors = ButtonDefaults.buttonColors(containerColor = accentCyan),
      ) {
        Text("Tạo hẹn giờ", color = Color.White)
      }
    },
    dismissButton = {
      TextButton(onClick = onDismiss) {
        Text("Hủy", color = textSecondary)
      }
    },
  )
}

@Composable
private fun CreateClockScheduleDialog(
  devices: List<HardwareDevice>,
  accentCyan: Color,
  accentRed: Color,
  cardBg: Color,
  cardBorder: Color,
  textPrimary: Color,
  textSecondary: Color,
  onDismiss: () -> Unit,
  onConfirm: (deviceId: String, action: String, timeHhmm: String, scheduleType: String, label: String) -> Unit,
) {
  val defaultDev = devices.firstOrNull()?.serverId ?: "living_room_light"
  var selectedDeviceId by remember { mutableStateOf(defaultDev) }
  var turnOn by remember { mutableStateOf(false) }
  var timeHhmm by remember { mutableStateOf("22:00") }
  var scheduleType by remember { mutableStateOf("daily") }
  var labelInput by remember { mutableStateOf("") }
  var validationError by remember { mutableStateOf("") }

  AlertDialog(
    onDismissRequest = onDismiss,
    containerColor = cardBg,
    title = {
      Text("Đặt lịch theo giờ (Asia/Saigon)", color = textPrimary, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
    },
    text = {
      Column(
        modifier = Modifier.verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(8.dp),
      ) {
        Text("Thiết bị", color = textSecondary, fontSize = 12.sp)
        DeviceSelectorRow(devices, selectedDeviceId, { selectedDeviceId = it }, accentCyan)

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
          val onTxt = if (selectedDeviceId == "main_door") "Mở" else "Bật"
          val offTxt = if (selectedDeviceId == "main_door") "Khóa" else "Tắt"
          TierChip(onTxt, turnOn, accentCyan, { turnOn = true })
          TierChip(offTxt, !turnOn, accentCyan, { turnOn = false })
        }

        Row(
          modifier = Modifier.horizontalScroll(rememberScrollState()),
          horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
          listOf("06:30", "18:00", "22:00", "23:00").forEach { preset ->
            TierChip(preset, timeHhmm == preset, accentCyan, {
              timeHhmm = preset
              validationError = ""
            })
          }
        }

        OutlinedTextField(
          value = timeHhmm,
          onValueChange = {
            timeHhmm = it.take(5)
            validationError = ""
          },
          label = { Text("Giờ chạy (HH:mm)", fontSize = 12.sp) },
          placeholder = { Text("22:30", fontSize = 12.sp) },
          singleLine = true,
          colors = OutlinedTextFieldDefaults.colors(
            focusedTextColor = textPrimary,
            unfocusedTextColor = textPrimary,
            focusedBorderColor = accentCyan,
            unfocusedBorderColor = cardBorder,
          ),
          modifier = Modifier.fillMaxWidth(),
        )

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
          TierChip("Một lần", scheduleType == "once", accentCyan, { scheduleType = "once" })
          TierChip("Hằng ngày", scheduleType == "daily", accentCyan, { scheduleType = "daily" })
        }

        OutlinedTextField(
          value = labelInput,
          onValueChange = { labelInput = it },
          label = { Text("Nhãn (tùy chọn)", fontSize = 12.sp) },
          singleLine = true,
          colors = OutlinedTextFieldDefaults.colors(
            focusedTextColor = textPrimary,
            unfocusedTextColor = textPrimary,
            focusedBorderColor = accentCyan,
            unfocusedBorderColor = cardBorder,
          ),
          modifier = Modifier.fillMaxWidth(),
        )

        if (validationError.isNotBlank()) {
          Text(validationError, color = accentRed, fontSize = 12.sp)
        }
      }
    },
    confirmButton = {
      Button(
        onClick = {
          val normalized = timeHhmm.trim()
          val hhmmRegex = Regex("^([01]?\\d|2[0-3]):([0-5]\\d)$")
          val m = hhmmRegex.matchEntire(normalized)
          if (m == null) {
            validationError = "Vui lòng nhập giờ hợp lệ dạng HH:mm (ví dụ 22:00)."
          } else {
            val formatted = "${m.groupValues[1].padStart(2, '0')}:${m.groupValues[2]}"
            onConfirm(
              selectedDeviceId,
              canonicalDeviceAction(selectedDeviceId, turnOn),
              formatted,
              scheduleType,
              labelInput.trim(),
            )
          }
        },
        colors = ButtonDefaults.buttonColors(containerColor = accentCyan),
      ) {
        Text("Lưu lịch", color = Color.White)
      }
    },
    dismissButton = {
      TextButton(onClick = onDismiss) {
        Text("Hủy", color = textSecondary)
      }
    },
  )
}

@Composable
private fun CreateAutomationRuleDialog(
  devices: List<HardwareDevice>,
  accentCyan: Color,
  accentRed: Color,
  cardBg: Color,
  cardBorder: Color,
  textPrimary: Color,
  textSecondary: Color,
  onDismiss: () -> Unit,
  onConfirm: (whenDeviceId: String, whenState: String, thenDeviceId: String, thenAction: String, label: String) -> Unit,
) {
  val defaultWhen = devices.firstOrNull()?.serverId ?: "main_door"
  val defaultThen = devices.firstOrNull { it.serverId != defaultWhen }?.serverId ?: "living_room_light"
  var whenDeviceId by remember { mutableStateOf(defaultWhen) }
  var whenActive by remember { mutableStateOf(true) }
  var thenDeviceId by remember { mutableStateOf(defaultThen) }
  var thenActive by remember { mutableStateOf(true) }
  var labelInput by remember { mutableStateOf("") }
  var validationError by remember { mutableStateOf("") }

  AlertDialog(
    onDismissRequest = onDismiss,
    containerColor = cardBg,
    title = {
      Text("Tạo luật liên kết thiết bị", color = textPrimary, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
    },
    text = {
      Column(
        modifier = Modifier.verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(8.dp),
      ) {
        Text("KHI thiết bị", color = textSecondary, fontSize = 12.sp)
        DeviceSelectorRow(devices, whenDeviceId, {
          whenDeviceId = it
          validationError = ""
        }, accentCyan)

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
          val onTxt = if (whenDeviceId == "main_door") "Đang mở (OPEN)" else "Đang bật (ON)"
          val offTxt = if (whenDeviceId == "main_door") "Đang khóa (CLOSED)" else "Đang tắt (OFF)"
          TierChip(onTxt, whenActive, accentCyan, { whenActive = true })
          TierChip(offTxt, !whenActive, accentCyan, { whenActive = false })
        }

        Text("THÌ điều khiển thiết bị", color = textSecondary, fontSize = 12.sp)
        DeviceSelectorRow(devices, thenDeviceId, {
          thenDeviceId = it
          validationError = ""
        }, accentCyan)

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
          val onTxt = if (thenDeviceId == "main_door") "Mở" else "Bật"
          val offTxt = if (thenDeviceId == "main_door") "Khóa" else "Tắt"
          TierChip(onTxt, thenActive, accentCyan, { thenActive = true })
          TierChip(offTxt, !thenActive, accentCyan, { thenActive = false })
        }

        OutlinedTextField(
          value = labelInput,
          onValueChange = { labelInput = it },
          label = { Text("Mô tả luật (tùy chọn)", fontSize = 12.sp) },
          singleLine = true,
          colors = OutlinedTextFieldDefaults.colors(
            focusedTextColor = textPrimary,
            unfocusedTextColor = textPrimary,
            focusedBorderColor = accentCyan,
            unfocusedBorderColor = cardBorder,
          ),
          modifier = Modifier.fillMaxWidth(),
        )

        if (validationError.isNotBlank()) {
          Text(validationError, color = accentRed, fontSize = 12.sp)
        }
      }
    },
    confirmButton = {
      Button(
        onClick = {
          if (whenDeviceId == thenDeviceId) {
            validationError = "Thiết bị điều kiện và thiết bị đích phải khác nhau."
          } else {
            onConfirm(
              whenDeviceId,
              canonicalWhenState(whenDeviceId, whenActive),
              thenDeviceId,
              canonicalDeviceAction(thenDeviceId, thenActive),
              labelInput.trim(),
            )
          }
        },
        colors = ButtonDefaults.buttonColors(containerColor = accentCyan),
      ) {
        Text("Tạo luật", color = Color.White)
      }
    },
    dismissButton = {
      TextButton(onClick = onDismiss) {
        Text("Hủy", color = textSecondary)
      }
    },
  )
}

@Composable
private fun CreateSceneDialog(
  devices: List<HardwareDevice>,
  accentCyan: Color,
  accentRed: Color,
  cardBg: Color,
  cardBorder: Color,
  textPrimary: Color,
  textSecondary: Color,
  onDismiss: () -> Unit,
  onConfirm: (phrase: String, stepsText: String, steps: List<CustomSceneStep>) -> Unit,
) {
  var phraseInput by remember { mutableStateOf("") }
  var stepsTextInput by remember { mutableStateOf("") }
  var pickerDeviceId by remember { mutableStateOf(devices.firstOrNull()?.serverId ?: "living_room_light") }
  var pickerTurnOn by remember { mutableStateOf(false) }
  val selectedSteps = remember { mutableStateListOf<CustomSceneStep>() }
  var validationError by remember { mutableStateOf("") }

  AlertDialog(
    onDismissRequest = onDismiss,
    containerColor = cardBg,
    title = {
      Text("Tạo ngữ cảnh nhiều bước", color = textPrimary, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
    },
    text = {
      Column(
        modifier = Modifier.verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(8.dp),
      ) {
        OutlinedTextField(
          value = phraseInput,
          onValueChange = {
            phraseInput = it
            validationError = ""
          },
          label = { Text("Tên ngữ cảnh / câu lệnh", fontSize = 12.sp) },
          placeholder = { Text("Ví dụ: Đi ngủ", fontSize = 12.sp) },
          singleLine = true,
          colors = OutlinedTextFieldDefaults.colors(
            focusedTextColor = textPrimary,
            unfocusedTextColor = textPrimary,
            focusedBorderColor = accentCyan,
            unfocusedBorderColor = cardBorder,
          ),
          modifier = Modifier.fillMaxWidth(),
        )

        Text("Thêm bước nhanh", color = textSecondary, fontSize = 12.sp)
        DeviceSelectorRow(devices, pickerDeviceId, { pickerDeviceId = it }, accentCyan)
        Row(
          modifier = Modifier.fillMaxWidth(),
          horizontalArrangement = Arrangement.SpaceBetween,
          verticalAlignment = Alignment.CenterVertically,
        ) {
          Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            val onTxt = if (pickerDeviceId == "main_door") "Mở" else "Bật"
            val offTxt = if (pickerDeviceId == "main_door") "Khóa" else "Tắt"
            TierChip(onTxt, pickerTurnOn, accentCyan, { pickerTurnOn = true })
            TierChip(offTxt, !pickerTurnOn, accentCyan, { pickerTurnOn = false })
          }
          CompactActionChip(
            label = "+ Thêm",
            textColor = accentCyan,
            borderColor = accentCyan,
            bgColor = Color(0xFFE6F3F2),
            onClick = {
              val step = CustomSceneStep(pickerDeviceId, canonicalDeviceAction(pickerDeviceId, pickerTurnOn))
              if (selectedSteps.none { it.deviceId == step.deviceId && it.action == step.action }) {
                selectedSteps.add(step)
                validationError = ""
              }
            },
          )
        }

        if (selectedSteps.isNotEmpty()) {
          Row(
            modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
          ) {
            selectedSteps.forEach { st ->
              val devName = devices.firstOrNull { it.serverId == st.deviceId }?.name ?: st.deviceId
              CompactActionChip(
                label = "${formatDeviceActionLabel(st.deviceId, devName, st.action)} x",
                textColor = textPrimary,
                borderColor = cardBorder,
                bgColor = Color(0xFFF5F7F7),
                onClick = { selectedSteps.remove(st) },
              )
            }
          }
        }

        OutlinedTextField(
          value = stepsTextInput,
          onValueChange = {
            stepsTextInput = it
            validationError = ""
          },
          label = { Text("Hoặc nhập chuỗi hành động", fontSize = 12.sp) },
          placeholder = { Text("Tắt đèn phòng khách, khóa cửa chính", fontSize = 12.sp) },
          singleLine = false,
          maxLines = 2,
          colors = OutlinedTextFieldDefaults.colors(
            focusedTextColor = textPrimary,
            unfocusedTextColor = textPrimary,
            focusedBorderColor = accentCyan,
            unfocusedBorderColor = cardBorder,
          ),
          modifier = Modifier.fillMaxWidth(),
        )

        if (validationError.isNotBlank()) {
          Text(validationError, color = accentRed, fontSize = 12.sp)
        }
      }
    },
    confirmButton = {
      Button(
        onClick = {
          val phrase = phraseInput.trim()
          val text = stepsTextInput.trim()
          if (phrase.isBlank()) {
            validationError = "Vui lòng nhập tên ngữ cảnh."
          } else if (selectedSteps.isEmpty() && text.isBlank()) {
            validationError = "Hãy thêm ít nhất 1 bước thiết bị hoặc nhập chuỗi hành động."
          } else {
            onConfirm(phrase, text, selectedSteps.toList())
          }
        },
        colors = ButtonDefaults.buttonColors(containerColor = accentCyan),
      ) {
        Text("Lưu ngữ cảnh", color = Color.White)
      }
    },
    dismissButton = {
      TextButton(onClick = onDismiss) {
        Text("Hủy", color = textSecondary)
      }
    },
  )
}
