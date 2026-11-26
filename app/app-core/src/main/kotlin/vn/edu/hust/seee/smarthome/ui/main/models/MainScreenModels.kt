package vn.edu.hust.seee.smarthome.ui.main.models

data class HardwareDevice(
  val serverId: String,
  val name: String,
  val pinInfo: String,
  val icon: String,
  val onLabel: String,
  val offLabel: String,
  val tier1Only: Boolean = (serverId == "main_door" || serverId == "alarm_siren"),
)

data class EnrolledVoiceProfile(
  val name: String,
  val email: String,
  val rolePasswordSeed: String,
  val tier: Int,
  val roleLabel: String,
  val targetF0Hz: Double,
)

data class CountdownTimerItem(
  val id: String,
  val deviceId: String,
  val deviceName: String,
  val targetStateOn: Boolean,
  val remainingSeconds: Int,
  val action: String = if (targetStateOn) "turn_on" else "turn_off",
  val actionVi: String = if (targetStateOn) "Bật" else "Tắt",
  val remainingLabel: String = "",
  val repeat: String = "once",
  val targetVnTime: String = "",
  val reason: String = "",
  val label: String = "",
  val ownerId: String = "",
  val ownerName: String = "",
  val ownerTier: Int = 1,
)

data class ClockScheduleItem(
  val id: String,
  val scheduleId: String = id,
  val deviceId: String,
  val deviceName: String,
  val action: String,
  val actionVi: String = "",
  val timeHhmm: String,
  val scheduleType: String = "once",
  val runDateVn: String = "",
  val timezone: String = "Asia/Saigon",
  val enabled: Boolean = true,
  val lastFiredDateVn: String = "",
  val label: String = "",
  val ownerUserId: String = "",
  val ownerName: String = "",
  val ownerTier: Int = 1,
)

data class AutomationRuleItem(
  val id: String,
  val ruleId: String = id,
  val whenDeviceId: String,
  val whenDeviceName: String,
  val whenState: String,
  val thenDeviceId: String,
  val thenDeviceName: String,
  val thenAction: String,
  val elseDeviceId: String = "",
  val elseDeviceName: String = "",
  val elseAction: String = "",
  val delaySeconds: Double = 0.0,
  val enabled: Boolean = true,
  val label: String = "",
  val ownerUserId: String = "",
  val ownerName: String = "",
  val ownerTier: Int = 1,
)

data class CustomSceneStep(
  val deviceId: String,
  val action: String,
)

data class CustomSceneItem(
  val id: String,
  val commandId: String = id,
  val phrase: String,
  val phraseNorm: String = "",
  val steps: List<CustomSceneStep> = emptyList(),
  val stepsSummary: String = "",
  val enabled: Boolean = true,
  val ownerUserId: String = "",
  val ownerName: String = "",
  val ownerTier: Int = 1,
)

data class AutomationSnapshotState(
  val activeTimers: List<CountdownTimerItem> = emptyList(),
  val clockSchedules: List<ClockScheduleItem> = emptyList(),
  val automationRules: List<AutomationRuleItem> = emptyList(),
  val customScenes: List<CustomSceneItem> = emptyList(),
)

fun canonicalDeviceAction(deviceId: String, turnOn: Boolean): String {
  return if (deviceId == "main_door") {
    if (turnOn) "open" else "close"
  } else {
    if (turnOn) "turn_on" else "turn_off"
  }
}

fun canonicalWhenState(deviceId: String, active: Boolean): String {
  return if (deviceId == "main_door") {
    if (active) "OPEN" else "CLOSED"
  } else {
    if (active) "ON" else "OFF"
  }
}

fun formatDeviceActionLabel(deviceId: String, deviceName: String, action: String): String {
  val normAction = action.trim().lowercase()
  val verb = when {
    deviceId == "main_door" && (normAction == "open" || normAction == "turn_on") -> "Mở"
    deviceId == "main_door" -> "Khóa"
    normAction == "open" || normAction == "turn_on" -> "Bật"
    else -> "Tắt"
  }
  return "$verb ${deviceName.ifBlank { deviceId }}"
}

data class AuthTestCaseItem(
  val testId: String,
  val title: String,
  val description: String,
  val resultText: String,
  val passed: Boolean,
)

data class CapturedVoiceSample(
  val f0Hz: Double,
  val pcm16kBase64: String,
)

data class BoardHealthState(
  val nodeId: String = "esp8266_node_01",
  val online: Boolean = true,
  val statusVi: String = "Đang kết nối",
  val lastSeenVi: String = "",
  val offlineResyncCount: Int = 0,
)
