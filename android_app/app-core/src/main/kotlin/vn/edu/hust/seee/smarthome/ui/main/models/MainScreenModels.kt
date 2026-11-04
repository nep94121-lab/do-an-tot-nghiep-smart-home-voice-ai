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
)

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
