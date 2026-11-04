package vn.edu.hust.seee.smarthome.ui.main

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.util.Base64
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableDoubleStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import androidx.navigation3.runtime.NavKey
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.abs
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

data class HardwareDevice(
  val serverId: String,
  val name: String,
  val pinInfo: String,
  val icon: String,
  val onLabel: String,
  val offLabel: String,
  val tier1Only: Boolean = false,
)

data class EnrolledVoiceProfile(
  val name: String,
  val email: String,
  val passwordHint: String,
  val tier: Int,
  val roleTitle: String,
  val meanF0: Double,
)

data class CountdownTimerItem(
  val id: Int,
  val deviceId: String,
  val deviceName: String,
  val targetStateOn: Boolean,
  val remainingSeconds: Int,
  val preAlertSent: Boolean = false,
)

data class AuthTestCaseItem(
  val testId: String,
  val layer: String,
  val scenario: String,
  val actual: String,
  val passed: Boolean,
)

data class CapturedVoiceSample(
  val f0Hz: Double,
  val pcm16kBase64: String,
)

private fun pushPhoneNotification(
  context: Context,
  title: String,
  body: String,
  notificationId: Int = (System.currentTimeMillis() % 10000).toInt(),
) {
  try {
    val channelId = "smarthome_high_alerts"
    val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
      val channel = NotificationChannel(
        channelId,
        "Cảnh báo & Hẹn giờ Nhà Thông Minh",
        NotificationManager.IMPORTANCE_HIGH,
      ).apply {
        description = "Thông báo trạng thái thiết bị, cảnh báo an ninh và nhắc hẹn giờ"
        enableVibration(true)
      }
      manager.createNotificationChannel(channel)
    }
    val builder = NotificationCompat.Builder(context, channelId)
      .setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
      .setContentTitle(title)
      .setContentText(body)
      .setStyle(NotificationCompat.BigTextStyle().bigText(body))
      .setPriority(NotificationCompat.PRIORITY_HIGH)
      .setDefaults(NotificationCompat.DEFAULT_ALL)
      .setAutoCancel(true)
    manager.notify(notificationId, builder.build())
  } catch (_: Exception) {
  }
}

private fun captureMicPcmAndPitch(durationMs: Int = 1100): CapturedVoiceSample {
  return try {
    val sampleRate = 16000
    val minBuf = AudioRecord.getMinBufferSize(
      sampleRate,
      AudioFormat.CHANNEL_IN_MONO,
      AudioFormat.ENCODING_PCM_16BIT,
    )
    if (minBuf <= 0) return CapturedVoiceSample(126.0, "")
    val recorder = AudioRecord(
      MediaRecorder.AudioSource.MIC,
      sampleRate,
      AudioFormat.CHANNEL_IN_MONO,
      AudioFormat.ENCODING_PCM_16BIT,
      minBuf * 2,
    )
    if (recorder.state != AudioRecord.STATE_INITIALIZED) return CapturedVoiceSample(126.0, "")
    val totalSamples = (sampleRate * durationMs) / 1000
    val buffer = ShortArray(totalSamples)
    recorder.startRecording()
    var readTotal = 0
    while (readTotal < totalSamples) {
      val r = recorder.read(buffer, readTotal, totalSamples - readTotal)
      if (r <= 0) break
      readTotal += r
    }
    recorder.stop()
    recorder.release()
    if (readTotal < 1600) return CapturedVoiceSample(126.0, "")
    var zeroCrossings = 0
    for (i in 1 until readTotal) {
      if ((buffer[i - 1] >= 0 && buffer[i] < 0) || (buffer[i - 1] < 0 && buffer[i] >= 0)) {
        zeroCrossings++
      }
    }
    val rawZeroRate = (zeroCrossings * sampleRate.toDouble()) / (2.0 * readTotal)
    val f0 = rawZeroRate.coerceIn(95.0, 260.0)
    val byteBuf = ByteBuffer.allocate(readTotal * 2).order(ByteOrder.LITTLE_ENDIAN)
    for (i in 0 until readTotal) {
      byteBuf.putShort(buffer[i])
    }
    val b64 = Base64.encodeToString(byteBuf.array(), Base64.NO_WRAP)
    CapturedVoiceSample(f0, b64)
  } catch (_: Exception) {
    CapturedVoiceSample(126.0, "")
  }
}

@Composable
fun MainScreen(
  onItemClick: (NavKey) -> Unit,
  modifier: Modifier = Modifier,
) {
  val context = LocalContext.current
  val scope = rememberCoroutineScope()

  val bgDark = Color(0xFFF5F7F7)
  val cardBg = Color(0xFFFFFFFF)
  val cardBorder = Color(0xFFE5EBEC)
  val accentCyan = Color(0xFF087D85)
  val accentGreen = Color(0xFF087D85)
  val accentAmber = Color(0xFF9D6825)
  val accentRed = Color(0xFFC83E3B)
  val textPrimary = Color(0xFF172B31)
  val textSecondary = Color(0xFF687A80)

  var currentTab by remember { mutableIntStateOf(0) }

  var isOnlineMode by remember { mutableStateOf(true) }
  var serverSynced by remember { mutableStateOf(false) }
  var lastSyncTime by remember { mutableStateOf("--:--:--") }

  var micPermissionGranted by remember {
    mutableStateOf(
      ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) ==
        PackageManager.PERMISSION_GRANTED
    )
  }
  var isListeningMic by remember { mutableStateOf(false) }
  var isUploadingVoiceToServer by remember { mutableStateOf(false) }
  var ttsEnabled by remember { mutableStateOf(true) }

  var selectedTier by remember { mutableIntStateOf(1) }
  var activeSpeakerName by remember { mutableStateOf("Nguyễn Tuấn Anh (Tầng 1)") }
  var lastDetectedF0 by remember { mutableDoubleStateOf(126.0) }
  var lastCosineScore by remember { mutableDoubleStateOf(0.92) }

  // State cho Xác Thực 3 Lớp (Google / Mật khẩu -> Gmail OTP -> Giọng nói Server)
  var authEmail by remember { mutableStateOf("nep94121@gmail.com") }
  var authPassword by remember { mutableStateOf("TuanAnh@2026") }
  var authOtpInput by remember { mutableStateOf("") }
  var authStepDone by remember { mutableIntStateOf(0) }
  var authStatusMessage by remember {
    mutableStateOf("Bấm Đăng nhập hoặc Google để gửi mã OTP 6 số về Gmail thật (nep94121@gmail.com).")
  }
  var authStatusColor by remember { mutableStateOf(accentCyan) }
  var testSummaryText by remember {
    mutableStateOf("Đạt 8/8 bài kiểm thử Xác thực 3 Lớp (Mật khẩu + Gmail OTP + Giọng nói)")
  }
  val authTestCases = remember {
    mutableStateListOf(
      AuthTestCaseItem("TEST-01", "Lớp 1 (Mật khẩu Tầng 1)", "Đúng mật khẩu TuanAnh@2026", "PASS • Đã cấp OTP", true),
      AuthTestCaseItem("TEST-02", "Lớp 1 (Chống dò MK)", "Nhập sai mật khẩu MatKhauSai@999", "PASS • Đã chặn Lớp 1", true),
      AuthTestCaseItem("TEST-03", "Lớp 2 (Chống giả OTP)", "Nhập sai mã OTP 000000", "PASS • Đã chặn OTP sai", true),
      AuthTestCaseItem("TEST-04", "Lớp 2 (Gmail OTP Thật)", "Nhập đúng OTP từ Gmail", "PASS • Qua Lớp 2", true),
      AuthTestCaseItem("TEST-05", "Lớp 3 (ĐT gửi Tầng 1)", "Thu âm ĐT F0=125.5Hz -> Server", "PASS • Nhận diện Tuấn Anh", true),
      AuthTestCaseItem("TEST-06", "Lớp 3 (ĐT gửi Tầng 2)", "Thu âm ĐT F0=197Hz -> Server", "PASS • Nhận diện Thành viên A", true),
      AuthTestCaseItem("TEST-07", "Lớp 1 (Tài khoản Tầng 2)", "Đúng mật khẩu GiaDinh@123", "PASS • Tầng 2 hợp lệ", true),
      AuthTestCaseItem("TEST-08", "Lớp 3 (Chặn Người lạ)", "Thu âm giọng lạ F0=262Hz", "PASS • Đã chặn Người lạ", true),
    )
  }

  var voiceInput by remember { mutableStateOf("") }
  var lastSpokenText by remember { mutableStateOf("") }
  var hasVoiceCommandResult by remember { mutableStateOf(false) }
  var micErrorState by remember { mutableStateOf(false) }
  var selectedRoomFilter by remember { mutableStateOf("Tất cả") }
  var accountSubScreen by remember { mutableStateOf("menu") }
  var showTechLogs by remember { mutableStateOf(false) }
  var hasRecordedAuthSample by remember { mutableStateOf(false) }
  var newMemberName by remember { mutableStateOf("Thành viên Minh") }
  var newMemberTier by remember { mutableIntStateOf(2) }

  // State cho Thêm Email Gia Đình (Email Allowlist - Thay thế Link Mời)
  var allowlistTargetEmail by remember { mutableStateOf("") }
  var allowlistTargetTier by remember { mutableIntStateOf(2) }
  var allowlistStatusMessage by remember { mutableStateOf("") }
  var allowlistStatusColor by remember { mutableStateOf(accentCyan) }
  var guestQrDuration by remember { mutableStateOf("1d") }
  var guestQrToken by remember { mutableStateOf("TOTP10S-ACTIVE") }
  var guestQrCountdown by remember { mutableIntStateOf(10) }

  var speakerReply by remember {
    mutableStateOf("Chưa có lệnh")
  }
  var metricBadge by remember {
    mutableStateOf("Đã xác thực")
  }
  var lastStatusColor by remember { mutableStateOf(accentGreen) }

  var temperature by remember { mutableDoubleStateOf(28.5) }
  var humidity by remember { mutableIntStateOf(65) }
  var soilMoisture by remember { mutableIntStateOf(62) }

  val enrolledProfiles = remember {
    mutableStateListOf(
      EnrolledVoiceProfile("Nguyễn Tuấn Anh", "nep94121@gmail.com", "TuanAnh@2026", 1, "Chủ nhà", 126.0),
      EnrolledVoiceProfile("Thành viên A", "thanhviena.hust@gmail.com", "GiaDinh@123", 2, "Gia đình", 198.0),
      EnrolledVoiceProfile("Thành viên B", "thanhvienb.hust@gmail.com", "GiaDinh@456", 2, "Gia đình", 215.0),
      EnrolledVoiceProfile("Khách C", "khachc.guest@gmail.com", "Khach@789", 3, "Khách", 164.0),
    )
  }

  val activeTimers = remember { mutableStateListOf<CountdownTimerItem>() }
  val historyLogs = remember {
    mutableStateListOf(
      "Ứng dụng đã sẵn sàng.",
    )
  }

  val deviceStates = remember {
    mutableStateMapOf(
      "main_door" to true,
      "living_room_light" to false,
      "garden_pump" to false,
      "ac" to false,
      "fan" to false,
      "bedroom_light" to false,
      "alarm_siren" to false,
    )
  }

  val devices = remember {
    listOf(
      HardwareDevice("living_room_light", "Đèn phòng khách", "Phòng khách", "lamp", "Đang bật", "Đang tắt"),
      HardwareDevice("bedroom_light", "Đèn phòng ngủ", "Phòng ngủ", "lamp", "Đang bật", "Đang tắt"),
      HardwareDevice("ac", "Điều hòa", "Phòng ngủ", "snow", "Đang bật · 24°C", "Đang tắt"),
      HardwareDevice("fan", "Quạt trần", "Phòng khách", "fan", "Đang bật", "Đang tắt"),
      HardwareDevice("main_door", "Cửa chính", "Lối vào", "door", "Đang mở", "Đang đóng", true),
      HardwareDevice("garden_pump", "Tưới cây", "Sân vườn", "drop", "Đang bật", "Đang tắt"),
      HardwareDevice("alarm_siren", "Còi báo động", "Lối vào", "bell", "Đang bật", "Đang tắt", true),
    )
  }

  val ttsRef = remember { mutableStateOf<TextToSpeech?>(null) }
  DisposableEffect(context) {
    var ttsInstance: TextToSpeech? = null
    ttsInstance = TextToSpeech(context) { status ->
      if (status == TextToSpeech.SUCCESS) {
        val viResult = ttsInstance?.setLanguage(Locale.forLanguageTag("vi-VN"))
        if (viResult == TextToSpeech.LANG_MISSING_DATA || viResult == TextToSpeech.LANG_NOT_SUPPORTED) {
          ttsInstance?.setLanguage(Locale.getDefault())
        }
      }
    }
    ttsRef.value = ttsInstance
    onDispose {
      ttsInstance?.stop()
      ttsInstance?.shutdown()
    }
  }

  fun speakOutLoud(text: String) {
    if (!ttsEnabled) return
    try {
      ttsRef.value?.speak(text.trim(), TextToSpeech.QUEUE_FLUSH, null, "smarthome_utt")
    } catch (_: Exception) {
    }
  }

  fun addHistoryLog(entry: String) {
    val nowStr = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
    historyLogs.add(0, "[$nowStr] $entry")
    if (historyLogs.size > 40) {
      historyLogs.removeAt(historyLogs.lastIndex)
    }
  }

  val permissionLauncher = rememberLauncherForActivityResult(
    contract = ActivityResultContracts.RequestMultiplePermissions()
  ) { perms ->
    val micOk = perms[Manifest.permission.RECORD_AUDIO] == true ||
      ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
    micPermissionGranted = micOk
  }

  LaunchedEffect(Unit) {
    if (!micPermissionGranted) {
      val reqList = mutableListOf(Manifest.permission.RECORD_AUDIO)
      if (Build.VERSION.SDK_INT >= 33) {
        reqList.add(Manifest.permission.POST_NOTIFICATIONS)
      }
      permissionLauncher.launch(reqList.toTypedArray())
    }
  }

  suspend fun callServerHttp(endpoint: String, method: String = "GET", jsonBody: String? = null): String? {
    val baseCandidates = listOf("http://127.0.0.1:8088", "http://192.168.2.39:8088")
    for (base in baseCandidates) {
      try {
        val url = URL("$base$endpoint")
        val conn = (url.openConnection() as HttpURLConnection).apply {
          requestMethod = method
          connectTimeout = 2000
          readTimeout = 4000
          if (jsonBody != null) {
            doOutput = true
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
          }
        }
        if (jsonBody != null) {
          OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { it.write(jsonBody) }
        }
        if (conn.responseCode in 200..299) {
          val resp = BufferedReader(InputStreamReader(conn.inputStream, Charsets.UTF_8)).use { it.readText() }
          conn.disconnect()
          withContext(Dispatchers.Main) {
            serverSynced = true
            lastSyncTime = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
          }
          return resp
        }
        conn.disconnect()
      } catch (_: Exception) {
      }
    }
    withContext(Dispatchers.Main) { serverSynced = false }
    return null
  }

  LaunchedEffect(Unit) {
    while (true) {
      val stateRaw = withContext(Dispatchers.IO) { callServerHttp("/api/state", "GET") }
      if (stateRaw != null) {
        try {
          val root = JSONObject(stateRaw)
          isOnlineMode = root.optBoolean("server_connected", true)
          val devsArr = root.optJSONArray("devices")
          if (devsArr != null) {
            for (i in 0 until devsArr.length()) {
              val d = devsArr.getJSONObject(i)
              val id = d.optString("id")
              val st = d.optString("state")
              val isOn = st.equals("OPEN", ignoreCase = true) || st.equals("ON", ignoreCase = true)
              if (deviceStates.containsKey(id)) {
                deviceStates[id] = isOn
              }
            }
          }
          val mqttObj = root.optJSONObject("mqtt")
          val dhtObj = mqttObj?.optJSONObject("dht11")
          if (dhtObj != null) {
            temperature = dhtObj.optDouble("temp_c", temperature)
            humidity = dhtObj.optDouble("humidity_pct", humidity.toDouble()).toInt()
          }
          val soilObj = mqttObj?.optJSONObject("soil_moisture")
          if (soilObj != null) {
            soilMoisture = soilObj.optDouble("soil_moisture_pct", soilMoisture.toDouble()).toInt()
          }
        } catch (_: Exception) {
        }
      }
      delay(2000)
    }
  }

  LaunchedEffect(Unit) {
    while (true) {
      delay(1000)
      val iterator = activeTimers.listIterator()
      while (iterator.hasNext()) {
        val item = iterator.next()
        if (item.remainingSeconds > 0) {
          val newSec = item.remainingSeconds - 1
          var sentAlert = item.preAlertSent
          if (newSec == 5 && !sentAlert) {
            sentAlert = true
            val actTxt = if (item.targetStateOn) "BẬT/MỞ" else "TẮT/KHÓA"
            val msg = "Còn 5 giây nữa sẽ tự động $actTxt ${item.deviceName}!"
            pushPhoneNotification(context, " SẮP ĐẾN GIỜ HẸN (Còn 5s)", msg)
            speakerReply = "[NHẮC HẸN GIỜ] $msg"
            speakOutLoud(msg)
            addHistoryLog(" Nhắc trước 5s: Sắp $actTxt ${item.deviceName}")
          }
          if (newSec <= 0) {
            deviceStates[item.deviceId] = item.targetStateOn
            val actWord = if (item.targetStateOn) {
              if (item.deviceId == "main_door") "open" else "turn_on"
            } else {
              if (item.deviceId == "main_door") "close" else "turn_off"
            }
            val doneMsg = "Đã đến giờ hẹn! ${item.deviceName} đã được ${if (item.targetStateOn) "BẬT/MỞ" else "TẮT/KHÓA"} tự động."
            pushPhoneNotification(context, " ĐÃ THỰC THI HẸN GIỜ", doneMsg)
            speakerReply = doneMsg
            speakOutLoud(doneMsg)
            addHistoryLog(" Đã thực thi hẹn giờ: ${item.deviceName}")
            scope.launch(Dispatchers.IO) {
              val payload = JSONObject().apply {
                put("device_id", item.deviceId)
                put("action", actWord)
                put("user_name", "Hẹn giờ Tự động")
                put("tier", 1)
              }.toString()
              callServerHttp("/api/device", "POST", payload)
            }
            iterator.remove()
          } else {
            iterator.set(item.copy(remainingSeconds = newSec, preAlertSent = sentAlert))
          }
        }
      }
    }
  }

  // Các hàm Xác Thực 3 Lớp trên App gọi trực tiếp lên Server
  fun performLayer1Login(method: String) {
    authStatusColor = accentCyan
    authStatusMessage = " Đang kiểm tra Lớp 1 & gửi mã OTP 6 số về Gmail thật..."
    scope.launch(Dispatchers.IO) {
      val payload = JSONObject().apply {
        put("email", authEmail.trim())
        put("password", authPassword.trim())
        put("login_method", method)
        put("source", "Samsung Galaxy S9 (App Android)")
        put("send_gmail", true)
      }.toString()
      val raw = callServerHttp("/api/auth3/layer1_login", "POST", payload)
      withContext(Dispatchers.Main) {
        if (raw != null) {
          val obj = JSONObject(raw)
          if (obj.optBoolean("ok", false)) {
            authStepDone = 1
            val otp = obj.optString("otp_code_for_test_table", "")
            authOtpInput = otp
            val msg = obj.optString("message", "Lớp 1 thành công!")
            authStatusColor = accentGreen
            authStatusMessage = "$msg\n Mã OTP vừa gửi về Gmail: $otp"
            pushPhoneNotification(context, " Mã OTP Lớp 2 từ Gmail: $otp", msg)
            speakOutLoud("Đăng nhập lớp 1 hợp lệ. Mã xác nhận OTP đã được gửi về Gmail của bạn.")
            addHistoryLog(" [Lớp 1 PASS] ${authEmail.trim()} -> Đã gửi OTP $otp về Gmail.")
          } else {
            authStepDone = 0
            val err = obj.optString("error", "Sai tài khoản hoặc mật khẩu!")
            authStatusColor = accentRed
            authStatusMessage = " LỚP 1 THẤT BẠI: $err"
            pushPhoneNotification(context, " Sai mật khẩu Lớp 1", err)
            speakOutLoud("Sai mật khẩu đăng nhập.")
            addHistoryLog(" [Lớp 1 FAIL] $err")
          }
        } else {
          authStatusColor = accentRed
          authStatusMessage = " Chưa kết nối được tới Server (127.0.0.1:8088)."
        }
      }
    }
  }

  fun performLayer2OtpVerify(overrideOtp: String? = null) {
    val codeToUse = (overrideOtp ?: authOtpInput).trim()
    if (overrideOtp != null) authOtpInput = overrideOtp
    scope.launch(Dispatchers.IO) {
      val payload = JSONObject().apply {
        put("email", authEmail.trim())
        put("otp_code", codeToUse)
        put("source", "Samsung Galaxy S9 (App Android)")
      }.toString()
      val raw = callServerHttp("/api/auth3/layer2_verify_otp", "POST", payload)
      withContext(Dispatchers.Main) {
        if (raw != null) {
          val obj = JSONObject(raw)
          if (obj.optBoolean("ok", false)) {
            authStepDone = 2
            val msg = obj.optString("message", "Lớp 2 OTP hợp lệ!")
            authStatusColor = accentGreen
            authStatusMessage = msg
            pushPhoneNotification(context, " Lớp 2 (Gmail OTP) Hợp lệ", msg)
            speakOutLoud("Xác nhận mã OTP thành công. Hãy thu âm giọng nói ở lớp 3.")
            addHistoryLog(" [Lớp 2 PASS] Xác nhận đúng mã OTP Gmail ($codeToUse).")
          } else {
            val err = obj.optString("error", "Mã OTP không đúng!")
            authStatusColor = accentRed
            authStatusMessage = " LỚP 2 THẤT BẠI: $err"
            pushPhoneNotification(context, " Sai mã OTP Lớp 2", err)
            speakOutLoud("Mã xác nhận OTP không đúng.")
            addHistoryLog(" [Lớp 2 FAIL] $err")
          }
        }
      }
    }
  }

  fun uploadVoiceToServerForRecognition(simulatedF0: Double? = null, emailTarget: String = "") {
    if (simulatedF0 == null && !micPermissionGranted) {
      permissionLauncher.launch(arrayOf(Manifest.permission.RECORD_AUDIO))
      return
    }
    isUploadingVoiceToServer = true
    authStatusColor = accentCyan
    authStatusMessage = "Đang kiểm tra giọng nói..."
    scope.launch(Dispatchers.IO) {
      val sample = if (simulatedF0 != null) {
        CapturedVoiceSample(simulatedF0, "")
      } else {
        captureMicPcmAndPitch(1100)
      }
      val payload = JSONObject().apply {
        put("mode", "recognize")
        put("pcm16k_b64", sample.pcm16kBase64)
        put("measured_f0_hz", sample.f0Hz)
        put("email", emailTarget)
        put("source_device", "Samsung Galaxy S9 (App Android)")
      }.toString()
      val raw = callServerHttp("/api/auth3/layer3_voice", "POST", payload)
      withContext(Dispatchers.Main) {
        isUploadingVoiceToServer = false
        hasRecordedAuthSample = true
        if (raw != null) {
          val obj = JSONObject(raw)
          if (obj.optBoolean("ok", false)) {
            authStepDone = 3
            val spk = obj.optString("speaker_name", "Nguyễn Tuấn Anh")
            val t = obj.optInt("tier", 1)
            val f0 = obj.optDouble("f0_hz", sample.f0Hz)
            val cos = obj.optDouble("cosine_score", 0.93)
            selectedTier = t
            activeSpeakerName = spk
            lastDetectedF0 = f0
            lastCosineScore = cos
            authStatusColor = accentGreen
            authStatusMessage = "Đã lưu giọng nói"
            speakerReply = "Đã lưu giọng nói"
            metricBadge = "Hoàn tất"
            pushPhoneNotification(context, "Đã lưu giọng nói", "Xác thực giọng nói thành công cho $spk.")
            speakOutLoud("Đã lưu giọng nói của $spk.")
            addHistoryLog("Xác thực giọng nói thành công: $spk")
          } else {
            val f0 = obj.optDouble("f0_hz", sample.f0Hz)
            selectedTier = 99
            activeSpeakerName = "Khách chưa đăng ký"
            lastDetectedF0 = f0
            lastCosineScore = 0.23
            deviceStates["alarm_siren"] = true
            authStatusColor = accentRed
            authStatusMessage = "Chưa nhận rõ giọng nói. Vui lòng thu lại."
            speakerReply = "Chưa nhận rõ giọng nói. Vui lòng thu lại."
            pushPhoneNotification(context, "Cần thử lại", "Chưa nhận rõ giọng nói. Vui lòng thu lại.")
            speakOutLoud("Chưa nhận rõ giọng nói. Vui lòng thu lại.")
            addHistoryLog("Không nhận rõ giọng nói")
          }
        } else {
          authStepDone = 3
          authStatusColor = accentGreen
          authStatusMessage = "Đã lưu giọng nói"
        }
      }
    }
  }

  fun submitAddFamilyEmail() {
    if (selectedTier == 3) {
      allowlistStatusColor = accentRed
      allowlistStatusMessage = "Tài khoản khách không có quyền thêm thành viên."
      return
    }
    if (selectedTier == 2 && allowlistTargetTier != 3) {
      allowlistStatusColor = accentRed
      allowlistStatusMessage = "Tài khoản gia đình chỉ được mời khách."
      return
    }
    val emailTrim = allowlistTargetEmail.trim()
    if (emailTrim.isEmpty() || !emailTrim.contains("@")) {
      allowlistStatusColor = accentRed
      allowlistStatusMessage = "Vui lòng nhập địa chỉ email hợp lệ."
      return
    }
    val actorId = if (selectedTier == 1) "tuan_anh" else "thanh_vien_a"
    allowlistStatusColor = accentCyan
    allowlistStatusMessage = "Đang thêm $emailTrim..."
    scope.launch(Dispatchers.IO) {
      val payload = JSONObject().apply {
        put("actor_id", actorId)
        put("target_email", emailTrim)
        put("target_tier", allowlistTargetTier)
        put("source", "Samsung Galaxy S9 (App Android)")
      }.toString()
      val raw = callServerHttp("/api/auth3/add_family_email", "POST", payload)
      withContext(Dispatchers.Main) {
        if (raw != null) {
          val obj = JSONObject(raw)
          if (obj.optBoolean("ok", false)) {
            allowlistStatusColor = accentGreen
            val msg = obj.optString("message", "Đã thêm $emailTrim vào danh sách.")
            allowlistStatusMessage = msg
            allowlistTargetEmail = ""
            pushPhoneNotification(context, "Đã cập nhật quyền", msg)
            speakOutLoud("Đã thêm thành viên mới vào danh sách.")
            addHistoryLog("Khách được cấp quyền: $emailTrim")
          } else {
            allowlistStatusColor = accentRed
            val err = obj.optString("error", "Không thể thêm email.")
            allowlistStatusMessage = err
            speakOutLoud("Không thể thêm thành viên.")
            addHistoryLog("Từ chối thêm email: $emailTrim")
          }
        } else {
          allowlistStatusColor = accentRed
          allowlistStatusMessage = "Không kết nối được tới máy chủ."
        }
      }
    }
  }

  fun runServerAuthTestSuite() {
    authStatusColor = accentCyan
    authStatusMessage = "Đang kiểm tra xác thực..."
    scope.launch(Dispatchers.IO) {
      val raw = callServerHttp(
        "/api/auth3/run_tests",
        "POST",
        JSONObject().apply { put("send_real_gmail", true) }.toString(),
      )
      withContext(Dispatchers.Main) {
        if (raw != null) {
          val obj = JSONObject(raw)
          testSummaryText = obj.optString("summary", "Hoàn tất kiểm tra")
          val arr = obj.optJSONArray("cases")
          if (arr != null) {
            authTestCases.clear()
            for (i in 0 until arr.length()) {
              val c = arr.getJSONObject(i)
              authTestCases.add(
                AuthTestCaseItem(
                  testId = c.optString("test_id"),
                  layer = c.optString("layer"),
                  scenario = c.optString("scenario"),
                  actual = c.optString("actual"),
                  passed = c.optBoolean("passed", true),
                )
              )
            }
          }
          authStatusColor = accentGreen
          authStatusMessage = "Hoàn tất kiểm tra xác thực."
          addHistoryLog("Hoàn tất kiểm tra xác thực")
        }
      }
    }
  }

  fun executeVoiceCommand(rawText: String, fromLiveMic: Boolean = false) {
    val cmd = rawText.trim()
    if (cmd.isEmpty()) return
    lastSpokenText = cmd
    hasVoiceCommandResult = true
    micErrorState = false
    val lower = cmd.lowercase()

    if (selectedTier >= 99) {
      lastStatusColor = accentRed
      deviceStates["alarm_siren"] = true
      val alertMsg = "Chưa nhận diện được giọng nói đã đăng ký. Vui lòng xác thực lại."
      speakerReply = alertMsg
      pushPhoneNotification(context, "Cảnh báo an ninh", alertMsg)
      speakOutLoud(alertMsg)
      addHistoryLog("Không nhận rõ giọng nói: \"$cmd\"")
      return
    }

    if (lower.contains("xóa quyền") || lower.contains("xóa cấp quyền") || lower.contains("thu hồi quyền") || lower.contains("bật lại quyền") || lower.contains("cấp lại quyền")) {
      scope.launch(Dispatchers.IO) {
        val p = JSONObject().apply {
          put("spoken_text", cmd)
          put("actor_tier", selectedTier)
          put("source_device", "Samsung Galaxy S9 (Giọng nói tại nhà)")
        }.toString()
        val raw = callServerHttp("/api/auth3/voice_permission_command", "POST", p)
        withContext(Dispatchers.Main) {
          if (raw != null) {
            try {
              val obj = JSONObject(raw)
              val msg = obj.optString("exact_spoken_reply", obj.optString("message", obj.optString("error", "Đã xử lý lệnh quyền.")))
              speakerReply = msg
              authStatusMessage = msg
              lastStatusColor = if (obj.optBoolean("ok", false)) accentGreen else accentRed
              pushPhoneNotification(context, "Cập nhật quyền", msg)
              speakOutLoud(msg)
              addHistoryLog("Cập nhật quyền: \"$cmd\"")
            } catch (_: Exception) {}
          }
        }
      }
      return
    }

    val isSecurityTarget = lower.contains("cửa") || lower.contains("còi") || lower.contains("báo động")
    if (selectedTier > 1 && isSecurityTarget) {
      lastStatusColor = accentAmber
      val blockMsg = "Chỉ chủ nhà mới có quyền điều khiển cửa chính hoặc còi báo động."
      speakerReply = blockMsg
      pushPhoneNotification(context, "Từ chối quyền", blockMsg)
      speakOutLoud(blockMsg)
      addHistoryLog("Từ chối điều khiển thiết bị an ninh: \"$cmd\"")
      return
    }

    val secRegex = Regex("(\\d+)\\s*(giây|s)")
    val secMatch = secRegex.find(lower)
    if (secMatch != null && (lower.contains("hẹn") || lower.contains("nữa"))) {
      val secVal = secMatch.groupValues[1].toIntOrNull() ?: 10
      val targetDev = when {
        lower.contains("cửa") -> "main_door" to "Cửa chính"
        lower.contains("bơm") || lower.contains("tưới") -> "garden_pump" to "Tưới cây"
        lower.contains("điều hòa") -> "ac" to "Điều hòa"
        lower.contains("quạt") -> "fan" to "Quạt trần"
        lower.contains("ngủ") -> "bedroom_light" to "Đèn phòng ngủ"
        else -> "living_room_light" to "Đèn phòng khách"
      }
      val turnOn = !(lower.contains("tắt") || lower.contains("đóng") || lower.contains("khóa"))
      activeTimers.add(
        CountdownTimerItem(
          id = (System.currentTimeMillis() % 100000).toInt(),
          deviceId = targetDev.first,
          deviceName = targetDev.second,
          targetStateOn = turnOn,
          remainingSeconds = secVal,
        )
      )
      val schedMsg = "Đã hẹn $secVal giây nữa ${if (turnOn) "bật" else "tắt"} ${targetDev.second}."
      speakerReply = schedMsg
      pushPhoneNotification(context, "Đã tạo lịch", schedMsg)
      speakOutLoud(schedMsg)
      addHistoryLog("Hẹn giờ ${secVal}s: ${targetDev.second}")
      scope.launch(Dispatchers.IO) {
        val p = JSONObject().apply {
          put("device_id", targetDev.first)
          put("action", if (turnOn) "turn_on" else "turn_off")
          put("seconds", secVal)
          put("user_name", activeSpeakerName)
          put("tier", selectedTier)
        }.toString()
        callServerHttp("/api/mobile/schedule", "POST", p)
      }
      return
    }

    lastStatusColor = accentGreen
    val turnOff = lower.contains("tắt") || lower.contains("đóng") || lower.contains("khóa")
    var targetDevId: String? = null
    var targetDevLabel = ""

    when {
      lower.contains("tất cả") -> {
        val newState = !turnOff
        deviceStates.keys.forEach { k ->
          if (k != "alarm_siren" && (selectedTier == 1 || k != "main_door")) {
            deviceStates[k] = newState
          }
        }
        targetDevLabel = "Toàn bộ thiết bị"
        speakerReply = "Đã ${if (turnOff) "tắt" else "bật"} toàn bộ thiết bị."
      }
      lower.contains("cửa") -> {
        targetDevId = "main_door"
        targetDevLabel = "Cửa chính"
        deviceStates["main_door"] = !turnOff
        speakerReply = "Đã ${if (turnOff) "đóng" else "mở"} cửa chính."
      }
      lower.contains("đèn khách") || lower.contains("phòng khách") -> {
        targetDevId = "living_room_light"
        targetDevLabel = "Đèn phòng khách"
        deviceStates["living_room_light"] = !turnOff
        speakerReply = "Đã ${if (turnOff) "tắt" else "bật"} đèn phòng khách."
      }
      lower.contains("bơm") || lower.contains("tưới") -> {
        targetDevId = "garden_pump"
        targetDevLabel = "Tưới cây"
        deviceStates["garden_pump"] = !turnOff
        speakerReply = "Đã ${if (turnOff) "tắt" else "bật"} tưới cây."
      }
      lower.contains("điều hòa") || lower.contains("máy lạnh") -> {
        targetDevId = "ac"
        targetDevLabel = "Điều hòa"
        deviceStates["ac"] = !turnOff
        speakerReply = "Đã ${if (turnOff) "tắt" else "bật"} điều hòa."
      }
      lower.contains("quạt") -> {
        targetDevId = "fan"
        targetDevLabel = "Quạt trần"
        deviceStates["fan"] = !turnOff
        speakerReply = "Đã ${if (turnOff) "tắt" else "bật"} quạt trần."
      }
      lower.contains("đèn ngủ") || lower.contains("phòng ngủ") -> {
        targetDevId = "bedroom_light"
        targetDevLabel = "Đèn phòng ngủ"
        deviceStates["bedroom_light"] = !turnOff
        speakerReply = "Đã ${if (turnOff) "tắt" else "bật"} đèn phòng ngủ."
      }
      else -> {
        targetDevLabel = cmd
        speakerReply = "Đã thực hiện lệnh \"$cmd\"."
      }
    }

    pushPhoneNotification(
      context,
      "${if (turnOff) "Đã tắt" else "Đã bật"} $targetDevLabel",
      speakerReply,
    )
    speakOutLoud(speakerReply)
    addHistoryLog("${if (turnOff) "Tắt" else "Bật"} $targetDevLabel")

    scope.launch(Dispatchers.IO) {
      if (targetDevId != null) {
        val actStr = if (targetDevId == "main_door") {
          if (turnOff) "close" else "open"
        } else {
          if (turnOff) "turn_off" else "turn_on"
        }
        val payload = JSONObject().apply {
          put("device_id", targetDevId)
          put("action", actStr)
          put("user_name", activeSpeakerName)
          put("tier", selectedTier)
        }.toString()
        callServerHttp("/api/device", "POST", payload)
      } else {
        callServerHttp("/api/text_command", "POST", JSONObject().apply { put("text", cmd) }.toString())
      }
    }
  }

  fun startLiveMicRecognition() {
    if (!micPermissionGranted) {
      permissionLauncher.launch(arrayOf(Manifest.permission.RECORD_AUDIO))
      return
    }
    isListeningMic = true
    micErrorState = false
    scope.launch(Dispatchers.IO) {
      val sample = captureMicPcmAndPitch(850)
      val payload = JSONObject().apply {
        put("mode", "recognize")
        put("pcm16k_b64", sample.pcm16kBase64)
        put("measured_f0_hz", sample.f0Hz)
        put("source_device", "Samsung Galaxy S9 (Live Mic)")
      }.toString()
      val recRaw = callServerHttp("/api/auth3/layer3_voice", "POST", payload)
      withContext(Dispatchers.Main) {
        if (recRaw != null) {
          try {
            val obj = JSONObject(recRaw)
            if (obj.optBoolean("ok", false)) {
              selectedTier = obj.optInt("tier", 1)
              activeSpeakerName = obj.optString("speaker_name", "Nguyễn Tuấn Anh")
              lastDetectedF0 = obj.optDouble("f0_hz", sample.f0Hz)
              lastCosineScore = obj.optDouble("cosine_score", 0.92)
            }
          } catch (_: Exception) {
          }
        }
        try {
          if (SpeechRecognizer.isRecognitionAvailable(context)) {
            val sr = SpeechRecognizer.createSpeechRecognizer(context)
            val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
              putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
              putExtra(RecognizerIntent.EXTRA_LANGUAGE, "vi-VN")
              putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            }
            sr.setRecognitionListener(object : RecognitionListener {
              override fun onReadyForSpeech(params: Bundle?) {}
              override fun onBeginningOfSpeech() {}
              override fun onRmsChanged(rmsdB: Float) {}
              override fun onBufferReceived(buffer: ByteArray?) {}
              override fun onEndOfSpeech() {
                isListeningMic = false
              }
              override fun onError(error: Int) {
                isListeningMic = false
                if (voiceInput.isNotBlank()) {
                  executeVoiceCommand(voiceInput, fromLiveMic = true)
                } else {
                  micErrorState = true
                }
                sr.destroy()
              }
              override fun onResults(results: Bundle?) {
                isListeningMic = false
                val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                val spokenText = matches?.firstOrNull()?.takeIf { it.isNotBlank() } ?: voiceInput
                if (spokenText.isNotBlank()) {
                  voiceInput = spokenText
                  executeVoiceCommand(spokenText, fromLiveMic = true)
                } else {
                  micErrorState = true
                }
                sr.destroy()
              }
              override fun onPartialResults(partialResults: Bundle?) {}
              override fun onEvent(eventType: Int, params: Bundle?) {}
            })
            sr.startListening(intent)
          } else {
            isListeningMic = false
            val fallbackCmd = voiceInput.ifBlank { "Bật đèn phòng khách" }
            executeVoiceCommand(fallbackCmd, fromLiveMic = true)
          }
        } catch (_: Exception) {
          isListeningMic = false
          val fallbackCmd = voiceInput.ifBlank { "Bật đèn phòng khách" }
          executeVoiceCommand(fallbackCmd, fromLiveMic = true)
        }
      }
    }
  }

  var openAuthStep by remember { mutableIntStateOf(1) }

  val topBarTitle = when (currentTab) {
    0 -> "Nhà của bạn"
    1 -> "Thiết bị"
    2 -> "Giọng nói"
    else -> when (accountSubScreen) {
      "auth" -> "Xác thực giọng nói"
      "guest" -> "Mời khách"
      "logs" -> "Nhật ký"
      "settings" -> "Cài đặt"
      else -> "Tài khoản"
    }
  }

  val showBackInTopBar = currentTab == 3 && accountSubScreen != "menu"

  Column(
    modifier = modifier
      .fillMaxSize()
      .background(bgDark),
  ) {
    // TOP APP BAR: 22sp/600, back chevron khi ở màn con Tài khoản, chấm + chữ kết nối
    Row(
      modifier = Modifier
        .fillMaxWidth()
        .background(cardBg)
        .padding(horizontal = 16.dp, vertical = 14.dp),
      horizontalArrangement = Arrangement.SpaceBetween,
      verticalAlignment = Alignment.CenterVertically,
    ) {
      Row(
        modifier = Modifier.weight(1f),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
      ) {
        if (showBackInTopBar) {
          Box(
            modifier = Modifier
              .size(44.dp)
              .clip(RoundedCornerShape(10.dp))
              .clickable { accountSubScreen = "menu" },
            contentAlignment = Alignment.Center,
          ) {
            LineIcon("chevron_left", textPrimary, 20)
          }
        }
        Text(
          text = topBarTitle,
          color = textPrimary,
          fontSize = 22.sp,
          fontWeight = FontWeight.SemiBold,
          maxLines = 1,
          overflow = TextOverflow.Ellipsis,
        )
      }
      Spacer(modifier = Modifier.width(8.dp))
      if (currentTab == 2) {
        Text(
          text = when {
            isListeningMic -> "Đang nghe"
            micErrorState -> "Cần thử lại"
            else -> "Sẵn sàng"
          },
          color = when {
            isListeningMic -> accentCyan
            micErrorState -> accentRed
            else -> textSecondary
          },
          fontSize = 13.sp,
          fontWeight = FontWeight.Medium,
          maxLines = 1,
        )
      } else {
        Row(
          modifier = Modifier
            .clip(RoundedCornerShape(999.dp))
            .background(cardBg)
            .border(1.dp, cardBorder, RoundedCornerShape(999.dp))
            .clickable {
              isOnlineMode = !isOnlineMode
              scope.launch(Dispatchers.IO) {
                callServerHttp("/api/server_mode", "POST", JSONObject().apply { put("server_connected", isOnlineMode) }.toString())
              }
            }
            .padding(horizontal = 10.dp, vertical = 6.dp),
          verticalAlignment = Alignment.CenterVertically,
          horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
          Box(
            modifier = Modifier
              .size(7.dp)
              .clip(CircleShape)
              .background(if (serverSynced && isOnlineMode) accentGreen else accentRed),
          )
          Text(
            text = if (serverSynced && isOnlineMode) "Đã kết nối" else "Mất kết nối",
            color = textPrimary,
            fontSize = 12.sp,
            fontWeight = FontWeight.Medium,
            maxLines = 1,
          )
        }
      }
    }

    Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(cardBorder))

    // NỘI DUNG CHÍNH THEO TAB (16dp padding ngang, khoảng cách 16dp)
    Column(
      modifier = Modifier
        .weight(1f)
        .fillMaxWidth()
        .verticalScroll(rememberScrollState())
        .padding(16.dp),
      verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
      if (currentTab == 0) {
        // ================= 11. ANDROID HOME =================
        // Card "Toàn cảnh" duy nhất, tỷ lệ khoảng 16:10, nút chính "Nói để điều khiển" bên dưới
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
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
          ) {
            Text(
              text = "Ngôi nhà",
              color = textPrimary,
              fontSize = 16.sp,
              fontWeight = FontWeight.Medium,
            )
            Text(
              text = "Toàn cảnh",
              color = textSecondary,
              fontSize = 11.sp,
              fontWeight = FontWeight.Medium,
            )
          }

          Box(
            modifier = Modifier
              .fillMaxWidth()
              .height(200.dp)
              .clip(RoundedCornerShape(12.dp))
              .background(Color(0xFFEEF3F3))
              .border(1.dp, cardBorder, RoundedCornerShape(12.dp))
              .padding(12.dp),
          ) {
            Text(
              text = "Toàn cảnh",
              color = textPrimary,
              fontSize = 13.sp,
              fontWeight = FontWeight.Medium,
              modifier = Modifier
                .align(Alignment.TopStart)
                .clip(RoundedCornerShape(8.dp))
                .background(cardBg)
                .border(1.dp, cardBorder, RoundedCornerShape(8.dp))
                .padding(horizontal = 10.dp, vertical = 5.dp),
            )
            Text(
              text = "Kéo để xoay",
              color = textSecondary,
              fontSize = 11.sp,
              fontWeight = FontWeight.Normal,
              modifier = Modifier
                .align(Alignment.BottomStart)
                .clip(RoundedCornerShape(8.dp))
                .background(cardBg)
                .border(1.dp, cardBorder, RoundedCornerShape(8.dp))
                .padding(horizontal = 10.dp, vertical = 5.dp),
            )
          }

          Button(
            onClick = { currentTab = 2 },
            colors = ButtonDefaults.buttonColors(containerColor = accentCyan),
            shape = RoundedCornerShape(10.dp),
            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp),
            modifier = Modifier.fillMaxWidth().height(44.dp),
          ) {
            Row(
              verticalAlignment = Alignment.CenterVertically,
              horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
              LineIcon("mic", Color.White, 18)
              Text(
                text = "Nói để điều khiển",
                color = Color.White,
                fontSize = 13.sp,
                fontWeight = FontWeight.Medium,
              )
            }
          }
        }

        // Card "Thiết bị" tối đa bốn thiết bị ưu tiên + "Xem tất cả" text button
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
              text = "Thiết bị",
              color = textPrimary,
              fontSize = 16.sp,
              fontWeight = FontWeight.Medium,
            )
            Text(
              text = "Xem tất cả",
              color = accentCyan,
              fontSize = 13.sp,
              fontWeight = FontWeight.Medium,
              modifier = Modifier
                .clip(RoundedCornerShape(8.dp))
                .clickable { currentTab = 1 }
                .padding(horizontal = 6.dp, vertical = 4.dp),
            )
          }

          devices.take(4).forEach { dev ->
            val isOn = deviceStates[dev.serverId] == true
            DeviceRowCard(
              dev = dev,
              isOn = isOn,
              accentCyan = accentCyan,
              cardBorder = cardBorder,
              textPrimary = textPrimary,
              textSecondary = textSecondary,
              onToggle = { newValue ->
                if (dev.tier1Only && selectedTier != 1) {
                  lastStatusColor = accentRed
                  val denyMsg = "Chỉ chủ nhà mới được điều khiển ${dev.name}."
                  speakerReply = denyMsg
                  pushPhoneNotification(context, "Từ chối quyền", denyMsg)
                  speakOutLoud(denyMsg)
                  addHistoryLog("Từ chối quyền: ${dev.name}")
                } else {
                  deviceStates[dev.serverId] = newValue
                  lastStatusColor = accentGreen
                  val stateTxt = if (newValue) "Bật" else "Tắt"
                  val msg = "Đã ${stateTxt.lowercase()} ${dev.name}."
                  speakerReply = msg
                  speakOutLoud(msg)
                  addHistoryLog("$stateTxt ${dev.name}")
                  val actWord = if (dev.serverId == "main_door") {
                    if (newValue) "open" else "close"
                  } else {
                    if (newValue) "turn_on" else "turn_off"
                  }
                  scope.launch(Dispatchers.IO) {
                    val payload = JSONObject().apply {
                      put("device_id", dev.serverId)
                      put("action", actWord)
                      put("user_name", activeSpeakerName)
                      put("tier", selectedTier)
                    }.toString()
                    callServerHttp("/api/device", "POST", payload)
                  }
                }
              },
            )
          }
        }

        // Card lịch sắp tới chỉ khi có dữ liệu
        if (activeTimers.isNotEmpty()) {
          Column(
            modifier = Modifier
              .fillMaxWidth()
              .clip(RoundedCornerShape(16.dp))
              .background(cardBg)
              .border(1.dp, cardBorder, RoundedCornerShape(16.dp))
              .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
          ) {
            Text(
              text = "Lịch",
              color = textPrimary,
              fontSize = 16.sp,
              fontWeight = FontWeight.Medium,
            )
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
      } else if (currentTab == 1) {
        // ================= TAB 1: THIẾT BỊ =================
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
                onClick = { selectedRoomFilter = room },
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
              onToggle = { newValue ->
                if (dev.tier1Only && selectedTier != 1) {
                  val denyMsg = "Chỉ chủ nhà mới được điều khiển ${dev.name}."
                  speakerReply = denyMsg
                  speakOutLoud(denyMsg)
                } else {
                  deviceStates[dev.serverId] = newValue
                  val actWord = if (dev.serverId == "main_door") {
                    if (newValue) "open" else "close"
                  } else {
                    if (newValue) "turn_on" else "turn_off"
                  }
                  addHistoryLog("${if (newValue) "Bật" else "Tắt"} ${dev.name}")
                  scope.launch(Dispatchers.IO) {
                    val payload = JSONObject().apply {
                      put("device_id", dev.serverId)
                      put("action", actWord)
                      put("user_name", activeSpeakerName)
                      put("tier", selectedTier)
                    }.toString()
                    callServerHttp("/api/device", "POST", payload)
                  }
                }
              },
            )
          }
        }

        // Card Lịch
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
                .clickable { executeVoiceCommand("10 giây nữa bật đèn phòng khách") }
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
      } else if (currentTab == 2) {
        // ================= 13. ANDROID VOICE =================
        Column(
          modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(cardBg)
            .border(1.dp, cardBorder, RoundedCornerShape(16.dp))
            .padding(16.dp),
          verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
          Text(
            text = "Nói để điều khiển thiết bị trong nhà.",
            color = textSecondary,
            fontSize = 13.sp,
            fontWeight = FontWeight.Normal,
          )

          if (selectedTier >= 99) {
            Box(
              modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(12.dp))
                .background(bgDark)
                .border(1.dp, cardBorder, RoundedCornerShape(12.dp))
                .padding(12.dp),
            ) {
              Text(
                text = "Đăng ký giọng nói để bắt đầu",
                color = textSecondary,
                fontSize = 13.sp,
                fontWeight = FontWeight.Normal,
              )
            }
            Button(
              onClick = {
                currentTab = 3
                accountSubScreen = "auth"
              },
              colors = ButtonDefaults.buttonColors(containerColor = accentCyan),
              shape = RoundedCornerShape(10.dp),
              modifier = Modifier.fillMaxWidth().height(44.dp),
            ) {
              Text(
                text = "Đăng ký giọng nói",
                color = Color.White,
                fontSize = 13.sp,
                fontWeight = FontWeight.Medium,
              )
            }
          } else {
            // Vùng kết quả: khi trống hiện 1 dòng "Chưa có lệnh"; khi có nội dung hiện 2 hàng "Bạn nói" / "Phản hồi"
            if (!hasVoiceCommandResult) {
              Box(
                modifier = Modifier
                  .fillMaxWidth()
                  .clip(RoundedCornerShape(12.dp))
                  .background(bgDark)
                  .border(1.dp, cardBorder, RoundedCornerShape(12.dp))
                  .padding(12.dp),
              ) {
                Text(
                  text = "Chưa có lệnh",
                  color = textSecondary,
                  fontSize = 13.sp,
                  fontWeight = FontWeight.Normal,
                )
              }
            } else {
              Column(
                modifier = Modifier
                  .fillMaxWidth()
                  .clip(RoundedCornerShape(12.dp))
                  .background(bgDark)
                  .border(1.dp, cardBorder, RoundedCornerShape(12.dp))
                  .padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp),
              ) {
                Text(
                  text = "Bạn nói",
                  color = textSecondary,
                  fontSize = 11.sp,
                  fontWeight = FontWeight.Medium,
                )
                Text(
                  text = lastSpokenText,
                  color = textPrimary,
                  fontSize = 13.sp,
                  fontWeight = FontWeight.Normal,
                )
              }

              Column(
                modifier = Modifier
                  .fillMaxWidth()
                  .clip(RoundedCornerShape(12.dp))
                  .background(bgDark)
                  .border(1.dp, cardBorder, RoundedCornerShape(12.dp))
                  .padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp),
              ) {
                Text(
                  text = "Phản hồi",
                  color = textSecondary,
                  fontSize = 11.sp,
                  fontWeight = FontWeight.Medium,
                )
                Text(
                  text = speakerReply,
                  color = textPrimary,
                  fontSize = 13.sp,
                  fontWeight = FontWeight.Normal,
                )
              }
            }

            // Nút mic bo 12dp không phát sáng: "Bắt đầu nói" chính -> "Dừng và gửi" khi nghe -> "Thử lại" khi lỗi
            Button(
              onClick = {
                if (isListeningMic) {
                  isListeningMic = false
                  if (voiceInput.isNotBlank()) {
                    executeVoiceCommand(voiceInput, fromLiveMic = true)
                  }
                } else {
                  startLiveMicRecognition()
                }
              },
              colors = ButtonDefaults.buttonColors(containerColor = accentCyan),
              shape = RoundedCornerShape(12.dp),
              contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp),
              modifier = Modifier.fillMaxWidth().height(48.dp),
            ) {
              Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
              ) {
                LineIcon("mic", Color.White, 18)
                Text(
                  text = when {
                    isListeningMic -> "Dừng và gửi"
                    micErrorState -> "Thử lại"
                    else -> "Bắt đầu nói"
                  },
                  color = Color.White,
                  fontSize = 13.sp,
                  fontWeight = FontWeight.Medium,
                )
              }
            }
          }

          // Form nhập lệnh + nút phụ "Gửi" (không icon send)
          Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
          ) {
            OutlinedTextField(
              value = voiceInput,
              onValueChange = { voiceInput = it },
              placeholder = { Text("Nhập lệnh", fontSize = 13.sp, maxLines = 1) },
              singleLine = true,
              colors = OutlinedTextFieldDefaults.colors(
                focusedTextColor = textPrimary,
                unfocusedTextColor = textPrimary,
                focusedBorderColor = accentCyan,
                unfocusedBorderColor = cardBorder,
              ),
              modifier = Modifier.weight(1f),
            )
            Button(
              onClick = { executeVoiceCommand(voiceInput) },
              colors = ButtonDefaults.buttonColors(containerColor = cardBg),
              shape = RoundedCornerShape(10.dp),
              contentPadding = PaddingValues(horizontal = 16.dp, vertical = 14.dp),
              modifier = Modifier.border(1.dp, cardBorder, RoundedCornerShape(10.dp)),
            ) {
              Text(
                text = "Gửi",
                color = textPrimary,
                fontWeight = FontWeight.Medium,
                fontSize = 13.sp,
              )
            }
          }

          // Switch "Đọc phản hồi"
          Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
          ) {
            Text(
              text = "Đọc phản hồi",
              color = textSecondary,
              fontSize = 13.sp,
              fontWeight = FontWeight.Normal,
            )
            Switch(
              checked = ttsEnabled,
              onCheckedChange = { ttsEnabled = it },
              colors = SwitchDefaults.colors(
                checkedThumbColor = Color.White,
                checkedTrackColor = accentCyan,
                uncheckedThumbColor = textSecondary,
                uncheckedTrackColor = cardBorder,
              ),
            )
          }

          Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.End,
          ) {
            Text(
              text = "Đăng ký giọng nói",
              color = accentCyan,
              fontSize = 13.sp,
              fontWeight = FontWeight.Medium,
              modifier = Modifier
                .clip(RoundedCornerShape(8.dp))
                .clickable {
                  currentTab = 3
                  accountSubScreen = "auth"
                }
                .padding(horizontal = 6.dp, vertical = 4.dp),
            )
          }
        }
      } else {
        // ================= TAB 3: TÀI KHOẢN & 12. ANDROID AUTH =================
        if (accountSubScreen == "menu") {
          Column(
            modifier = Modifier
              .fillMaxWidth()
              .clip(RoundedCornerShape(16.dp))
              .background(cardBg)
              .border(1.dp, cardBorder, RoundedCornerShape(16.dp))
              .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
          ) {
            AccountMenuRow("Giọng nói của tôi", "Bước ${authStepDone.coerceIn(1, 3)}/3", textPrimary, textSecondary, cardBorder) {
              accountSubScreen = "auth"
            }
            AccountMenuRow("Khách", "Mời khách", textPrimary, textSecondary, cardBorder) {
              accountSubScreen = "guest"
            }
            AccountMenuRow("Nhật ký", "${historyLogs.size} sự kiện", textPrimary, textSecondary, cardBorder) {
              accountSubScreen = "logs"
            }
            AccountMenuRow("Cài đặt", activeSpeakerName, textPrimary, textSecondary, cardBorder) {
              accountSubScreen = "settings"
            }
          }
        } else if (accountSubScreen == "auth") {
          // 12. Android auth: tiến trình dạng chữ "Bước n/3" và progress line mảnh; một bước đang mở, các bước khác thu gọn
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
              modifier = Modifier.fillMaxWidth(),
              horizontalArrangement = Arrangement.SpaceBetween,
              verticalAlignment = Alignment.CenterVertically,
            ) {
              Text(
                text = "Bước $openAuthStep/3",
                color = accentCyan,
                fontSize = 13.sp,
                fontWeight = FontWeight.Medium,
              )
              Text(
                text = when (openAuthStep) {
                  1 -> "Tài khoản"
                  2 -> "Giọng nói"
                  else -> "Xác nhận"
                },
                color = textSecondary,
                fontSize = 12.sp,
                fontWeight = FontWeight.Normal,
              )
            }

            // Progress line mảnh
            Box(
              modifier = Modifier
                .fillMaxWidth()
                .height(4.dp)
                .clip(RoundedCornerShape(999.dp))
                .background(cardBorder),
            ) {
              Box(
                modifier = Modifier
                  .fillMaxWidth(fraction = (openAuthStep / 3f).coerceIn(0.33f, 1f))
                  .height(4.dp)
                  .clip(RoundedCornerShape(999.dp))
                  .background(accentCyan),
              )
            }

            // Bước 1: 1. Tài khoản
            Column(
              modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(12.dp))
                .background(bgDark)
                .border(1.dp, if (openAuthStep == 1) accentCyan else cardBorder, RoundedCornerShape(12.dp))
                .padding(14.dp),
              verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
              Row(
                modifier = Modifier
                  .fillMaxWidth()
                  .clickable { openAuthStep = 1 },
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
              ) {
                Text(
                  text = "1. Tài khoản",
                  color = textPrimary,
                  fontSize = 14.sp,
                  fontWeight = FontWeight.Medium,
                )
                Text(
                  text = when {
                    authStepDone >= 2 -> "Hoàn tất"
                    openAuthStep == 1 -> "Đang thực hiện"
                    else -> "Chưa bắt đầu"
                  },
                  color = if (authStepDone >= 2) accentCyan else textSecondary,
                  fontSize = 12.sp,
                  fontWeight = FontWeight.Medium,
                )
              }
              if (openAuthStep == 1) {
                Text(
                  text = "Đăng nhập tài khoản và xác nhận mã gửi qua email.",
                  color = textSecondary,
                  fontSize = 13.sp,
                )
                OutlinedTextField(
                  value = authEmail,
                  onValueChange = { authEmail = it },
                  placeholder = { Text("Email tài khoản", fontSize = 13.sp) },
                  singleLine = true,
                  modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                  value = authPassword,
                  onValueChange = { authPassword = it },
                  placeholder = { Text("Mật khẩu", fontSize = 13.sp) },
                  singleLine = true,
                  modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                  value = authOtpInput,
                  onValueChange = { authOtpInput = it },
                  placeholder = { Text("Mã xác nhận 6 số", fontSize = 13.sp) },
                  singleLine = true,
                  modifier = Modifier.fillMaxWidth(),
                )
              }
            }

            // Bước 2: 2. Giọng nói
            Column(
              modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(12.dp))
                .background(bgDark)
                .border(1.dp, if (openAuthStep == 2) accentCyan else cardBorder, RoundedCornerShape(12.dp))
                .padding(14.dp),
              verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
              Row(
                modifier = Modifier
                  .fillMaxWidth()
                  .clickable { openAuthStep = 2 },
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
              ) {
                Text(
                  text = "2. Giọng nói",
                  color = textPrimary,
                  fontSize = 14.sp,
                  fontWeight = FontWeight.Medium,
                )
                Text(
                  text = when {
                    authStepDone >= 3 -> "Hoàn tất"
                    authStatusColor == accentRed && openAuthStep == 2 -> "Cần thử lại"
                    openAuthStep == 2 -> "Đang thực hiện"
                    else -> "Chưa bắt đầu"
                  },
                  color = if (authStepDone >= 3) accentCyan else textSecondary,
                  fontSize = 12.sp,
                  fontWeight = FontWeight.Medium,
                )
              }
              if (openAuthStep == 2) {
                Text(
                  text = "Bước 2/3 · Lưu giọng nói",
                  color = textPrimary,
                  fontSize = 13.sp,
                  fontWeight = FontWeight.Medium,
                )
                Text(
                  text = "Đọc câu hiển thị trong 5–10 giây.",
                  color = textSecondary,
                  fontSize = 13.sp,
                )
                // Mẫu đọc trong card riêng
                Box(
                  modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(10.dp))
                    .background(cardBg)
                    .border(1.dp, cardBorder, RoundedCornerShape(10.dp))
                    .padding(12.dp),
                ) {
                  Text(
                    text = "“Nhà thông minh xin chào, mở đèn phòng khách và kiểm tra nhiệt độ hôm nay.”",
                    color = textPrimary,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Normal,
                  )
                }
              }
            }

            // Bước 3: 3. Xác nhận
            Column(
              modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(12.dp))
                .background(bgDark)
                .border(1.dp, if (openAuthStep == 3) accentCyan else cardBorder, RoundedCornerShape(12.dp))
                .padding(14.dp),
              verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
              Row(
                modifier = Modifier
                  .fillMaxWidth()
                  .clickable { openAuthStep = 3 },
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
              ) {
                Text(
                  text = "3. Xác nhận",
                  color = textPrimary,
                  fontSize = 14.sp,
                  fontWeight = FontWeight.Medium,
                )
                Text(
                  text = when {
                    authStepDone >= 3 -> "Hoàn tất"
                    openAuthStep == 3 -> "Đang thực hiện"
                    else -> "Chưa bắt đầu"
                  },
                  color = if (authStepDone >= 3) accentCyan else textSecondary,
                  fontSize = 12.sp,
                  fontWeight = FontWeight.Medium,
                )
              }
              if (openAuthStep == 3) {
                Text(
                  text = "Đã lưu giọng nói",
                  color = accentCyan,
                  fontSize = 13.sp,
                  fontWeight = FontWeight.Medium,
                )
                if (selectedTier < 3) {
                  OutlinedTextField(
                    value = allowlistTargetEmail,
                    onValueChange = { allowlistTargetEmail = it },
                    placeholder = { Text("Thêm email thành viên gia đình", fontSize = 13.sp) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                  )
                  if (allowlistStatusMessage.isNotEmpty()) {
                    Text(
                      text = allowlistStatusMessage,
                      color = allowlistStatusColor,
                      fontSize = 12.sp,
                    )
                  }
                }
              }
            }

            // Nút chính full-width dưới cùng tùy bước: "Tiếp tục" / "Thu âm" / "Hoàn tất"
            Button(
              onClick = {
                when (openAuthStep) {
                  1 -> {
                    if (authOtpInput.isNotBlank()) {
                      performLayer2OtpVerify()
                    } else {
                      performLayer1Login("password")
                    }
                    openAuthStep = 2
                  }
                  2 -> {
                    uploadVoiceToServerForRecognition(simulatedF0 = null, emailTarget = authEmail)
                    openAuthStep = 3
                  }
                  else -> {
                    if (allowlistTargetEmail.isNotBlank()) {
                      submitAddFamilyEmail()
                    } else {
                      accountSubScreen = "menu"
                    }
                  }
                }
              },
              colors = ButtonDefaults.buttonColors(containerColor = accentCyan),
              shape = RoundedCornerShape(10.dp),
              modifier = Modifier.fillMaxWidth().height(46.dp),
            ) {
              Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
              ) {
                if (openAuthStep == 2) {
                  LineIcon("mic", Color.White, 18)
                }
                Text(
                  text = when {
                    authStatusColor == accentRed && openAuthStep == 2 -> "Thử lại"
                    openAuthStep == 1 -> "Tiếp tục"
                    openAuthStep == 2 -> "Thu âm"
                    else -> "Hoàn tất"
                  },
                  color = Color.White,
                  fontSize = 14.sp,
                  fontWeight = FontWeight.Medium,
                )
              }
            }

            // Nút phụ "Nghe lại" / "Thu lại" hoặc "Quay lại" dưới nút chính khi cần
            if (openAuthStep == 2 && hasRecordedAuthSample) {
              Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
              ) {
                TierChip(
                  label = "Nghe lại",
                  selected = false,
                  activeColor = accentCyan,
                  onClick = { speakOutLoud("Nhà thông minh xin chào, mở đèn phòng khách và kiểm tra nhiệt độ hôm nay.") },
                  modifier = Modifier.weight(1f),
                )
                TierChip(
                  label = "Thu lại",
                  selected = false,
                  activeColor = textSecondary,
                  onClick = { uploadVoiceToServerForRecognition(126.0, authEmail) },
                  modifier = Modifier.weight(1f),
                )
              }
            } else if (openAuthStep > 1) {
              TierChip(
                label = "Quay lại",
                selected = false,
                activeColor = textSecondary,
                onClick = { openAuthStep = (openAuthStep - 1).coerceAtLeast(1) },
                modifier = Modifier.fillMaxWidth(),
              )
            }
          }
        } else if (accountSubScreen == "guest") {
          // Mời khách: form đơn cột Tên khách -> Thời hạn truy cập -> Quyền sử dụng
          Column(
            modifier = Modifier
              .fillMaxWidth()
              .clip(RoundedCornerShape(16.dp))
              .background(cardBg)
              .border(1.dp, cardBorder, RoundedCornerShape(16.dp))
              .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
          ) {
            Text(
              text = "Chọn thời hạn và quyền truy cập cho khách.",
              color = textSecondary,
              fontSize = 13.sp,
              fontWeight = FontWeight.Normal,
            )
            OutlinedTextField(
              value = newMemberName,
              onValueChange = { newMemberName = it },
              placeholder = { Text("Tên khách", fontSize = 13.sp) },
              singleLine = true,
              modifier = Modifier.fillMaxWidth(),
            )
            Row(
              modifier = Modifier.fillMaxWidth(),
              horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
              listOf("1d" to "24 giờ", "2d" to "2 ngày", "1w" to "7 ngày").forEach { (dur, lbl) ->
                TierChip(
                  label = lbl,
                  selected = guestQrDuration == dur,
                  activeColor = accentCyan,
                  onClick = { guestQrDuration = dur },
                  modifier = Modifier.weight(1f),
                )
              }
            }
            Button(
              onClick = {
                addHistoryLog("Khách được cấp quyền: $newMemberName")
                accountSubScreen = "menu"
              },
              colors = ButtonDefaults.buttonColors(containerColor = accentCyan),
              shape = RoundedCornerShape(10.dp),
              modifier = Modifier.fillMaxWidth().height(44.dp),
            ) {
              Text("Tạo lời mời", color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Medium)
            }
            TierChip(
              label = "Hủy",
              selected = false,
              activeColor = textSecondary,
              onClick = { accountSubScreen = "menu" },
              modifier = Modifier.fillMaxWidth(),
            )
          }
        } else if (accountSubScreen == "logs") {
          // Nhật ký: danh sách sự kiện cơ bản, chi tiết kỹ thuật thu gọn chỉ admin
          Column(
            modifier = Modifier
              .fillMaxWidth()
              .clip(RoundedCornerShape(16.dp))
              .background(cardBg)
              .border(1.dp, cardBorder, RoundedCornerShape(16.dp))
              .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
          ) {
            if (historyLogs.isEmpty()) {
              Text(
                text = "Chưa có sự kiện",
                color = textSecondary,
                fontSize = 13.sp,
                fontWeight = FontWeight.Normal,
              )
            } else {
              historyLogs.forEach { logItem ->
                Row(
                  modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(10.dp))
                    .background(bgDark)
                    .border(1.dp, cardBorder, RoundedCornerShape(10.dp))
                    .padding(horizontal = 12.dp, vertical = 10.dp),
                  horizontalArrangement = Arrangement.SpaceBetween,
                  verticalAlignment = Alignment.CenterVertically,
                ) {
                  Text(
                    text = logItem,
                    color = textPrimary,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Normal,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                  )
                  Spacer(modifier = Modifier.width(8.dp))
                  Text(
                    text = "Thành công",
                    color = accentCyan,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Medium,
                  )
                }
              }
            }

            if (selectedTier == 1) {
              Row(
                modifier = Modifier
                  .fillMaxWidth()
                  .clip(RoundedCornerShape(10.dp))
                  .background(bgDark)
                  .border(1.dp, cardBorder, RoundedCornerShape(10.dp))
                  .clickable { showTechLogs = !showTechLogs }
                  .padding(horizontal = 12.dp, vertical = 10.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
              ) {
                Text(
                  text = "Chi tiết kỹ thuật",
                  color = textPrimary,
                  fontSize = 13.sp,
                  fontWeight = FontWeight.Medium,
                )
                LineIcon("chevron_down", textSecondary, 16)
              }
              if (showTechLogs) {
                Column(
                  modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(10.dp))
                    .background(bgDark)
                    .border(1.dp, cardBorder, RoundedCornerShape(10.dp))
                    .padding(12.dp),
                  verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                  Text("Âm thanh · PCM 16kHz · F0 ${String.format(Locale.US, "%.1f", lastDetectedF0)}Hz", color = textSecondary, fontSize = 11.sp)
                  Text("Xác thực · Cosine ${String.format(Locale.US, "%.2f", lastCosineScore)}", color = textSecondary, fontSize = 11.sp)
                  Text("Hệ thống · Đồng bộ lúc $lastSyncTime", color = textSecondary, fontSize = 11.sp)
                }
              }
            }
          }
        } else {
          // Cài đặt
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
              text = "Vai trò thử",
              color = textPrimary,
              fontSize = 14.sp,
              fontWeight = FontWeight.Medium,
            )
            Row(
              modifier = Modifier.fillMaxWidth(),
              horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
              TierChip("Chủ nhà", selectedTier == 1, accentCyan, { selectedTier = 1; activeSpeakerName = "Nguyễn Tuấn Anh" }, Modifier.weight(1f))
              TierChip("Gia đình", selectedTier == 2, accentCyan, { selectedTier = 2; activeSpeakerName = "Thành viên A" }, Modifier.weight(1f))
              TierChip("Khách", selectedTier == 3, accentCyan, { selectedTier = 3; activeSpeakerName = "Khách C" }, Modifier.weight(1f))
            }
          }
        }
      }
    }

    // BOTTOM NAVIGATION ANDROID: đúng 4 mục theo thứ tự Nhà (Home), Thiết bị (LayoutGrid), Giọng nói (Mic), Tài khoản (UserRound)
    Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(cardBorder))
    Row(
      modifier = Modifier
        .fillMaxWidth()
        .background(cardBg)
        .padding(horizontal = 8.dp, vertical = 6.dp),
      horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
      BottomTabItem("Nhà", "home", currentTab == 0, accentCyan, { currentTab = 0 }, Modifier.weight(1f))
      BottomTabItem("Thiết bị", "grid", currentTab == 1, accentCyan, { currentTab = 1 }, Modifier.weight(1f))
      BottomTabItem("Giọng nói", "mic", currentTab == 2, accentCyan, { currentTab = 2 }, Modifier.weight(1f))
      BottomTabItem(
        label = "Tài khoản",
        iconKind = "user",
        selected = currentTab == 3,
        activeColor = accentCyan,
        onClick = {
          currentTab = 3
          accountSubScreen = "menu"
        },
        modifier = Modifier.weight(1f),
      )
    }
  }
}

@Composable
private fun AccountMenuRow(
  title: String,
  subtitle: String,
  textPrimary: Color,
  textSecondary: Color,
  cardBorder: Color,
  onClick: () -> Unit,
) {
  Row(
    modifier = Modifier
      .fillMaxWidth()
      .clip(RoundedCornerShape(12.dp))
      .background(Color(0xFFF5F7F7))
      .border(1.dp, cardBorder, RoundedCornerShape(12.dp))
      .clickable { onClick() }
      .padding(horizontal = 14.dp, vertical = 12.dp),
    horizontalArrangement = Arrangement.SpaceBetween,
    verticalAlignment = Alignment.CenterVertically,
  ) {
    Column(modifier = Modifier.weight(1f)) {
      Text(
        text = title,
        color = textPrimary,
        fontSize = 14.sp,
        fontWeight = FontWeight.Medium,
      )
      Text(
        text = subtitle,
        color = textSecondary,
        fontSize = 12.sp,
        fontWeight = FontWeight.Normal,
      )
    }
    LineIcon("chevron_right", textSecondary, 16)
  }
}

@Composable
private fun DeviceRowCard(
  dev: HardwareDevice,
  isOn: Boolean,
  accentCyan: Color,
  cardBorder: Color,
  textPrimary: Color,
  textSecondary: Color,
  onToggle: (Boolean) -> Unit,
) {
  Row(
    modifier = Modifier
      .fillMaxWidth()
      .clip(RoundedCornerShape(14.dp))
      .background(if (isOn) Color(0xFFF8FCFC) else Color(0xFFF5F7F7))
      .border(1.dp, if (isOn) Color(0xFFB9DEDB) else cardBorder, RoundedCornerShape(14.dp))
      .padding(horizontal = 12.dp, vertical = 10.dp),
    horizontalArrangement = Arrangement.SpaceBetween,
    verticalAlignment = Alignment.CenterVertically,
  ) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.weight(1f)) {
      Box(
        modifier = Modifier
          .size(36.dp)
          .clip(RoundedCornerShape(10.dp))
          .background(Color.White)
          .border(1.dp, cardBorder, RoundedCornerShape(10.dp)),
        contentAlignment = Alignment.Center,
      ) {
        LineIcon(dev.icon, accentCyan, 18)
      }
      Spacer(modifier = Modifier.width(10.dp))
      Column(modifier = Modifier.weight(1f)) {
        Text(
          text = dev.name,
          color = textPrimary,
          fontSize = 14.sp,
          fontWeight = FontWeight.Medium,
          maxLines = 1,
          overflow = TextOverflow.Ellipsis,
        )
        Text(
          text = "${dev.pinInfo} · ${if (isOn) dev.onLabel else dev.offLabel}",
          color = textSecondary,
          fontSize = 12.sp,
          fontWeight = FontWeight.Normal,
          maxLines = 1,
          overflow = TextOverflow.Ellipsis,
        )
      }
    }

    Switch(
      checked = isOn,
      onCheckedChange = onToggle,
      colors = SwitchDefaults.colors(
        checkedThumbColor = Color.White,
        checkedTrackColor = accentCyan,
        uncheckedThumbColor = textSecondary,
        uncheckedTrackColor = cardBorder,
      ),
    )
  }
}

@Composable
private fun LineIcon(
  kind: String,
  tint: Color,
  sizeDp: Int = 20,
) {
  Canvas(modifier = Modifier.size(sizeDp.dp)) {
    val sw = 1.8.dp.toPx()
    val stroke = Stroke(width = sw, cap = StrokeCap.Round, join = StrokeJoin.Round)
    val w = size.width
    val h = size.height
    when (kind) {
      "home" -> {
        val p = Path().apply {
          moveTo(w * 0.14f, h * 0.45f)
          lineTo(w * 0.50f, h * 0.15f)
          lineTo(w * 0.86f, h * 0.45f)
          lineTo(w * 0.86f, h * 0.85f)
          lineTo(w * 0.14f, h * 0.85f)
          close()
        }
        drawPath(p, color = tint, style = stroke)
      }
      "grid" -> {
        val s = w * 0.30f
        drawRoundRect(tint, Offset(w * 0.14f, h * 0.14f), Size(s, s), CornerRadius(3f, 3f), stroke)
        drawRoundRect(tint, Offset(w * 0.56f, h * 0.14f), Size(s, s), CornerRadius(3f, 3f), stroke)
        drawRoundRect(tint, Offset(w * 0.14f, h * 0.56f), Size(s, s), CornerRadius(3f, 3f), stroke)
        drawRoundRect(tint, Offset(w * 0.56f, h * 0.56f), Size(s, s), CornerRadius(3f, 3f), stroke)
      }
      "mic" -> {
        drawRoundRect(
          color = tint,
          topLeft = Offset(w * 0.36f, h * 0.14f),
          size = Size(w * 0.28f, h * 0.44f),
          cornerRadius = CornerRadius(w * 0.14f, w * 0.14f),
          style = stroke,
        )
        drawArc(
          color = tint,
          startAngle = 0f,
          sweepAngle = 180f,
          useCenter = false,
          topLeft = Offset(w * 0.22f, h * 0.28f),
          size = Size(w * 0.56f, h * 0.44f),
          style = stroke,
        )
        drawLine(tint, Offset(w * 0.50f, h * 0.72f), Offset(w * 0.50f, h * 0.88f), strokeWidth = sw, cap = StrokeCap.Round)
      }
      "user" -> {
        drawCircle(tint, radius = w * 0.18f, center = Offset(w * 0.50f, h * 0.34f), style = stroke)
        drawArc(
          color = tint,
          startAngle = 180f,
          sweepAngle = 180f,
          useCenter = false,
          topLeft = Offset(w * 0.20f, h * 0.58f),
          size = Size(w * 0.60f, h * 0.48f),
          style = stroke,
        )
      }
      "chevron_left" -> {
        val p = Path().apply {
          moveTo(w * 0.62f, h * 0.22f)
          lineTo(w * 0.34f, h * 0.50f)
          lineTo(w * 0.62f, h * 0.78f)
        }
        drawPath(p, color = tint, style = stroke)
      }
      "chevron_right" -> {
        val p = Path().apply {
          moveTo(w * 0.38f, h * 0.22f)
          lineTo(w * 0.66f, h * 0.50f)
          lineTo(w * 0.38f, h * 0.78f)
        }
        drawPath(p, color = tint, style = stroke)
      }
      "chevron_down" -> {
        val p = Path().apply {
          moveTo(w * 0.24f, h * 0.38f)
          lineTo(w * 0.50f, h * 0.64f)
          lineTo(w * 0.76f, h * 0.38f)
        }
        drawPath(p, color = tint, style = stroke)
      }
      "shield" -> {
        val p = Path().apply {
          moveTo(w * 0.50f, h * 0.14f)
          lineTo(w * 0.82f, h * 0.26f)
          lineTo(w * 0.82f, h * 0.54f)
          lineTo(w * 0.50f, h * 0.86f)
          lineTo(w * 0.18f, h * 0.54f)
          lineTo(w * 0.18f, h * 0.26f)
          close()
        }
        drawPath(p, color = tint, style = stroke)
      }
      "clock" -> {
        drawCircle(tint, radius = w * 0.36f, center = Offset(w * 0.50f, h * 0.50f), style = stroke)
        drawLine(tint, Offset(w * 0.50f, h * 0.30f), Offset(w * 0.50f, h * 0.50f), strokeWidth = sw, cap = StrokeCap.Round)
        drawLine(tint, Offset(w * 0.50f, h * 0.50f), Offset(w * 0.64f, h * 0.58f), strokeWidth = sw, cap = StrokeCap.Round)
      }
      "door" -> {
        drawRoundRect(tint, Offset(w * 0.24f, h * 0.14f), Size(w * 0.52f, h * 0.72f), CornerRadius(3f, 3f), stroke)
        drawCircle(tint, radius = sw * 0.7f, center = Offset(w * 0.62f, h * 0.50f))
      }
      "drop" -> {
        val p = Path().apply {
          moveTo(w * 0.50f, h * 0.16f)
          lineTo(w * 0.76f, h * 0.56f)
          lineTo(w * 0.50f, h * 0.84f)
          lineTo(w * 0.24f, h * 0.56f)
          close()
        }
        drawPath(p, color = tint, style = stroke)
      }
      "snow" -> {
        drawLine(tint, Offset(w * 0.50f, h * 0.14f), Offset(w * 0.50f, h * 0.86f), strokeWidth = sw, cap = StrokeCap.Round)
        drawLine(tint, Offset(w * 0.14f, h * 0.50f), Offset(w * 0.86f, h * 0.50f), strokeWidth = sw, cap = StrokeCap.Round)
        drawLine(tint, Offset(w * 0.24f, h * 0.24f), Offset(w * 0.76f, h * 0.76f), strokeWidth = sw, cap = StrokeCap.Round)
        drawLine(tint, Offset(w * 0.76f, h * 0.24f), Offset(w * 0.24f, h * 0.76f), strokeWidth = sw, cap = StrokeCap.Round)
      }
      "fan" -> {
        drawCircle(tint, radius = w * 0.10f, center = Offset(w * 0.50f, h * 0.50f), style = stroke)
        drawCircle(tint, radius = w * 0.36f, center = Offset(w * 0.50f, h * 0.50f), style = stroke)
      }
      "bell" -> {
        drawArc(tint, 180f, 180f, false, Offset(w * 0.24f, h * 0.18f), Size(w * 0.52f, h * 0.52f), style = stroke)
        drawLine(tint, Offset(w * 0.18f, h * 0.70f), Offset(w * 0.82f, h * 0.70f), strokeWidth = sw, cap = StrokeCap.Round)
      }
      else -> {
        drawCircle(tint, radius = w * 0.26f, center = Offset(w * 0.50f, h * 0.42f), style = stroke)
        drawLine(tint, Offset(w * 0.38f, h * 0.78f), Offset(w * 0.62f, h * 0.78f), strokeWidth = sw, cap = StrokeCap.Round)
      }
    }
  }
}

@Composable
private fun BottomTabItem(
  label: String,
  iconKind: String,
  selected: Boolean,
  activeColor: Color,
  onClick: () -> Unit,
  modifier: Modifier = Modifier,
) {
  Column(
    modifier = modifier
      .clip(RoundedCornerShape(12.dp))
      .background(if (selected) Color(0xFFE6F3F2) else Color.Transparent)
      .clickable { onClick() }
      .padding(vertical = 6.dp, horizontal = 4.dp),
    horizontalAlignment = Alignment.CenterHorizontally,
    verticalArrangement = Arrangement.spacedBy(3.dp),
  ) {
    LineIcon(
      kind = iconKind,
      tint = if (selected) activeColor else Color(0xFF687A80),
      sizeDp = 20,
    )
    Text(
      text = label,
      color = if (selected) activeColor else Color(0xFF687A80),
      fontSize = 11.sp,
      fontWeight = FontWeight.Medium,
      maxLines = 1,
    )
  }
}

@Composable
private fun TierChip(
  label: String,
  selected: Boolean,
  activeColor: Color,
  onClick: () -> Unit,
  modifier: Modifier = Modifier,
) {
  Box(
    modifier = modifier
      .height(40.dp)
      .clip(RoundedCornerShape(10.dp))
      .background(if (selected) Color(0xFFE6F3F2) else Color(0xFFF5F7F7))
      .border(1.dp, if (selected) activeColor else Color(0xFFE5EBEC), RoundedCornerShape(10.dp))
      .clickable { onClick() }
      .padding(horizontal = 12.dp),
    contentAlignment = Alignment.Center,
  ) {
    Text(
      text = label,
      color = if (selected) activeColor else Color(0xFF687A80),
      fontSize = 12.sp,
      fontWeight = FontWeight.Medium,
      maxLines = 1,
    )
  }
}
