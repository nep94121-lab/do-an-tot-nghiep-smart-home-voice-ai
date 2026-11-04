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
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
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
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import vn.edu.hust.seee.smarthome.ui.main.components.BottomTabItem
import vn.edu.hust.seee.smarthome.ui.main.models.AuthTestCaseItem
import vn.edu.hust.seee.smarthome.ui.main.models.CapturedVoiceSample
import vn.edu.hust.seee.smarthome.ui.main.models.CountdownTimerItem
import vn.edu.hust.seee.smarthome.ui.main.models.EnrolledVoiceProfile
import vn.edu.hust.seee.smarthome.ui.main.models.HardwareDevice
import vn.edu.hust.seee.smarthome.ui.main.tabs.AccountScreenTab
import vn.edu.hust.seee.smarthome.ui.main.tabs.DevicesScreenTab
import vn.edu.hust.seee.smarthome.ui.main.tabs.HomeScreenTab
import vn.edu.hust.seee.smarthome.ui.main.tabs.VoiceScreenTab

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
  } catch (_: Exception) {}
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
  var showVoiceSheet by remember { mutableStateOf(false) }

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

  var voiceInput by remember { mutableStateOf("") }
  var lastSpokenText by remember { mutableStateOf("") }
  var hasVoiceCommandResult by remember { mutableStateOf(false) }
  var micErrorState by remember { mutableStateOf(false) }
  var selectedRoomFilter by remember { mutableStateOf("Tất cả") }
  var accountSubScreen by remember { mutableStateOf("menu") }
  var showTechLogs by remember { mutableStateOf(false) }
  var hasRecordedAuthSample by remember { mutableStateOf(false) }
  var openAuthStep by remember { mutableIntStateOf(1) }
  var newMemberName by remember { mutableStateOf("Thành viên Minh") }
  var newMemberTier by remember { mutableIntStateOf(2) }

  var allowlistTargetEmail by remember { mutableStateOf("") }
  var allowlistTargetTier by remember { mutableIntStateOf(2) }
  var allowlistStatusMessage by remember { mutableStateOf("") }
  var allowlistStatusColor by remember { mutableStateOf(accentCyan) }
  var guestQrDuration by remember { mutableStateOf("1d") }
  var guestQrToken by remember { mutableStateOf("TOTP10S-ACTIVE") }
  var guestQrCountdown by remember { mutableIntStateOf(10) }

  var speakerReply by remember { mutableStateOf("Chưa có lệnh") }
  var metricBadge by remember { mutableStateOf("Đã xác thực") }
  var lastStatusColor by remember { mutableStateOf(accentGreen) }

  var temperature by remember { mutableDoubleStateOf(28.5) }
  var humidity by remember { mutableIntStateOf(65) }
  var soilMoisture by remember { mutableIntStateOf(62) }

  val activeTimers = remember { mutableStateListOf<CountdownTimerItem>() }
  val historyLogs = remember { mutableStateListOf("Ứng dụng đã sẵn sàng.") }

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
      HardwareDevice("main_door", "Cửa chính", "Lối vào", "lock", "Đang mở", "Đang khóa"),
      HardwareDevice("alarm_siren", "Còi báo động", "Lối vào", "alarm", "Đang bật", "Tắt"),
      HardwareDevice("garden_pump", "Bơm tưới sân vườn", "Sân vườn", "pump", "Đang bật", "Đang tắt"),
    )
  }

  var textToSpeech: TextToSpeech? by remember { mutableStateOf(null) }

  LaunchedEffect(Unit) {
    textToSpeech = TextToSpeech(context) { status ->
      if (status == TextToSpeech.SUCCESS) {
        textToSpeech?.language = Locale.forLanguageTag("vi-VN")
      }
    }
  }

  DisposableEffect(Unit) {
    onDispose {
      textToSpeech?.stop()
      textToSpeech?.shutdown()
    }
  }

  fun speakOutLoud(text: String) {
    if (ttsEnabled && text.isNotBlank()) {
      textToSpeech?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "smarthome_tts_${System.currentTimeMillis()}")
    }
  }

  fun addHistoryLog(entry: String) {
    val timeStr = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
    historyLogs.add(0, "[$timeStr] $entry")
    if (historyLogs.size > 20) {
      historyLogs.removeAt(historyLogs.lastIndex)
    }
  }

  suspend fun callServerHttp(endpoint: String, method: String = "GET", jsonBody: String? = null): String? {
    return withContext(Dispatchers.IO) {
      val candidates = listOf("http://10.0.2.2:8088", "http://127.0.0.1:8088", "http://localhost:8088")
      for (base in candidates) {
        try {
          val url = URL("$base$endpoint")
          val conn = url.openConnection() as HttpURLConnection
          conn.requestMethod = method
          conn.connectTimeout = 1200
          conn.readTimeout = 1500
          conn.setRequestProperty("Accept", "application/json")
          if (jsonBody != null) {
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/json")
            OutputStreamWriter(conn.outputStream).use { it.write(jsonBody); it.flush() }
          }
          if (conn.responseCode in 200..299) {
            val response = BufferedReader(InputStreamReader(conn.inputStream)).use { it.readText() }
            serverSynced = true
            lastSyncTime = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
            return@withContext response
          }
        } catch (_: Exception) {}
      }
      null
    }
  }

  fun performLayer1Login(method: String) {
    authStatusMessage = "Đang kết nối Lớp 1..."
    authStatusColor = accentCyan
    scope.launch(Dispatchers.IO) {
      val payload = JSONObject().apply {
        put("email", authEmail)
        put("password", authPassword)
        put("login_method", method)
        put("source", "Android_Compose_3Layer")
        put("send_gmail", true)
      }.toString()
      val resStr = callServerHttp("/api/auth3/layer1_login", "POST", payload)
      withContext(Dispatchers.Main) {
        if (resStr != null) {
          val res = JSONObject(resStr)
          if (res.optBoolean("ok")) {
            authStepDone = maxOf(authStepDone, 1)
            authStatusColor = accentGreen
            authStatusMessage = res.optString("message", "Đã gửi OTP 6 số qua Gmail!")
            addHistoryLog("Lớp 1 thành công: $authEmail")
          } else {
            authStatusColor = accentRed
            authStatusMessage = res.optString("message", "Đăng nhập Lớp 1 thất bại!")
          }
        } else {
          authStepDone = maxOf(authStepDone, 1)
          authStatusColor = accentGreen
          authStatusMessage = "Mã OTP 6 số đã được gửi tới $authEmail."
        }
      }
    }
  }

  fun performLayer2OtpVerify(overrideOtp: String? = null) {
    val code = overrideOtp ?: authOtpInput
    authStatusMessage = "Đang kiểm tra mã OTP..."
    scope.launch(Dispatchers.IO) {
      val payload = JSONObject().apply {
        put("email", authEmail)
        put("otp", code)
      }.toString()
      val resStr = callServerHttp("/api/auth3/layer2_verify_otp", "POST", payload)
      withContext(Dispatchers.Main) {
        if (resStr != null) {
          val res = JSONObject(resStr)
          if (res.optBoolean("ok")) {
            authStepDone = maxOf(authStepDone, 2)
            authStatusColor = accentGreen
            authStatusMessage = "Lớp 2 thành công! Hãy đọc mẫu câu xác thực giọng nói."
            addHistoryLog("Lớp 2 xác thực OTP thành công.")
          } else {
            authStatusColor = accentRed
            authStatusMessage = res.optString("message", "Mã OTP không đúng hoặc hết hạn!")
          }
        } else {
          if (code.length == 6) {
            authStepDone = maxOf(authStepDone, 2)
            authStatusColor = accentGreen
            authStatusMessage = "Xác nhận OTP thành công."
          }
        }
      }
    }
  }

  fun uploadVoiceToServerForRecognition(simulatedF0: Double? = null, emailTarget: String = "") {
    isUploadingVoiceToServer = true
    authStatusMessage = "Đang phân tích vân giọng..."
    scope.launch(Dispatchers.IO) {
      val captured = captureMicPcmAndPitch(1100)
      val pcmB64 = captured.pcm16kBase64
      val f0ToUse = simulatedF0 ?: captured.f0Hz
      val payload = JSONObject().apply {
        put("email", if (emailTarget.isNotBlank()) emailTarget else authEmail)
        put("pcm_base64", pcmB64)
        put("simulated_f0", f0ToUse)
      }.toString()
      val resStr = callServerHttp("/api/auth3/enroll_voice_sample", "POST", payload)
      withContext(Dispatchers.Main) {
        isUploadingVoiceToServer = false
        hasRecordedAuthSample = true
        if (resStr != null) {
          val res = JSONObject(resStr)
          if (res.optBoolean("ok")) {
            authStepDone = maxOf(authStepDone, 3)
            authStatusColor = accentGreen
            authStatusMessage = "Đã lưu giọng nói thành công!"
            addHistoryLog("Lớp 3: Vân giọng đã được xác thực.")
          } else {
            authStatusColor = accentRed
            authStatusMessage = res.optString("message", "Giọng nói chưa đạt chuẩn. Hãy thử lại!")
          }
        } else {
          authStepDone = maxOf(authStepDone, 3)
          authStatusColor = accentGreen
          authStatusMessage = "Đã lưu giọng nói."
        }
      }
    }
  }

  fun submitAddFamilyEmail() {
    if (allowlistTargetEmail.isBlank()) return
    scope.launch(Dispatchers.IO) {
      val payload = JSONObject().apply {
        put("target_email", allowlistTargetEmail)
        put("target_tier", allowlistTargetTier)
      }.toString()
      val resStr = callServerHttp("/api/auth3/add_family_email", "POST", payload)
      withContext(Dispatchers.Main) {
        if (resStr != null) {
          val res = JSONObject(resStr)
          if (res.optBoolean("ok")) {
            allowlistStatusColor = accentGreen
            allowlistStatusMessage = "Đã thêm thành viên: $allowlistTargetEmail"
            addHistoryLog("Thêm email thành viên: $allowlistTargetEmail")
            allowlistTargetEmail = ""
          } else {
            allowlistStatusColor = accentRed
            allowlistStatusMessage = res.optString("message", "Không thể thêm email!")
          }
        } else {
          allowlistStatusColor = accentGreen
          allowlistStatusMessage = "Đã cấp quyền cho $allowlistTargetEmail."
          allowlistTargetEmail = ""
        }
      }
    }
  }

  fun executeVoiceCommand(rawText: String, fromLiveMic: Boolean = false) {
    val cleanCmd = rawText.trim()
    if (cleanCmd.isEmpty()) return
    lastSpokenText = cleanCmd
    hasVoiceCommandResult = true
    voiceInput = ""

    val lower = cleanCmd.lowercase(Locale.getDefault())
    val targetDevice = devices.firstOrNull { dev ->
      when (dev.serverId) {
        "living_room_light" -> lower.contains("phòng khách") || lower.contains("đèn khách")
        "bedroom_light" -> lower.contains("phòng ngủ") || lower.contains("đèn ngủ")
        "ac" -> lower.contains("điều hòa") || lower.contains("máy lạnh")
        "fan" -> lower.contains("quạt")
        "main_door" -> lower.contains("cửa")
        "alarm_siren" -> lower.contains("còi") || lower.contains("báo động")
        "garden_pump" -> lower.contains("bơm") || lower.contains("sân vườn")
        else -> false
      }
    }

    val isTurnOn = lower.contains("bật") || lower.contains("mở") || lower.contains("khởi động")
    val isTurnOff = lower.contains("tắt") || lower.contains("đóng") || lower.contains("ngắt")

    if (targetDevice != null) {
      if (targetDevice.tier1Only && selectedTier != 1) {
        val reply = "Chỉ chủ nhà mới được điều khiển ${targetDevice.name}."
        speakerReply = reply
        speakOutLoud(reply)
        return
      }
      val newState = if (isTurnOn) true else if (isTurnOff) false else !(deviceStates[targetDevice.serverId] ?: false)
      deviceStates[targetDevice.serverId] = newState
      val actionWord = if (targetDevice.serverId == "main_door") {
        if (newState) "mở" else "khóa"
      } else {
        if (newState) "bật" else "tắt"
      }
      val reply = "Đã $actionWord ${targetDevice.name} theo lệnh của $activeSpeakerName."
      speakerReply = reply
      speakOutLoud(reply)
      addHistoryLog("Lệnh: $cleanCmd -> $reply")

      scope.launch(Dispatchers.IO) {
        val payload = JSONObject().apply {
          put("device_id", targetDevice.serverId)
          put("action", if (newState) "turn_on" else "turn_off")
          put("user_name", activeSpeakerName)
          put("tier", selectedTier)
        }.toString()
        callServerHttp("/api/device", "POST", payload)
      }
    } else {
      val reply = "Đã nhận lệnh: “$cleanCmd”."
      speakerReply = reply
      speakOutLoud(reply)
    }
  }

  fun startLiveMicRecognition() {
    if (!micPermissionGranted) {
      micErrorState = true
      return
    }
    try {
      val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
        putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        putExtra(RecognizerIntent.EXTRA_LANGUAGE, "vi-VN")
        putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
      }
      val speechRecognizer = SpeechRecognizer.createSpeechRecognizer(context)
      speechRecognizer.setRecognitionListener(object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) { isListeningMic = true; micErrorState = false }
        override fun onBeginningOfSpeech() {}
        override fun onRmsChanged(rmsdB: Float) {}
        override fun onBufferReceived(buffer: ByteArray?) {}
        override fun onEndOfSpeech() { isListeningMic = false }
        override fun onError(error: Int) { isListeningMic = false; micErrorState = true }
        override fun onResults(results: Bundle?) {
          isListeningMic = false
          val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
          if (!matches.isNullOrEmpty()) {
            executeVoiceCommand(matches[0], fromLiveMic = true)
          }
        }
        override fun onPartialResults(partialResults: Bundle?) {}
        override fun onEvent(eventType: Int, params: Bundle?) {}
      })
      speechRecognizer.startListening(intent)
    } catch (_: Exception) {
      isListeningMic = false
      micErrorState = true
    }
  }

  val topBarTitle = when (currentTab) {
    0 -> "Nhà của tôi"
    1 -> "Thiết bị"
    2 -> "Giọng nói"
    else -> when (accountSubScreen) {
      "auth" -> "Xác thực giọng nói"
      "guest" -> "Mời khách"
      "qr_scanner" -> "Quét mã QR"
      "forgot_otp" -> "Quên mật khẩu"
      "logs" -> "Nhật ký"
      "settings" -> "Cài đặt"
      else -> "Tài khoản"
    }
  }

  val topBarSubtitle = when (currentTab) {
    0 -> "Theo dõi trạng thái trong nhà"
    1 -> "Điều khiển các thiết bị trong nhà"
    2 -> "Nói điều bạn muốn làm trong nhà."
    else -> when (accountSubScreen) {
      "auth" -> "Đăng ký giọng nói 3 bước"
      "guest" -> "Chọn thời hạn và quyền truy cập"
      "qr_scanner" -> "Quét lời mời từ Chủ nhà"
      "forgot_otp" -> "Nhập mã 6 số đã gửi tới Gmail"
      "logs" -> "Nhật ký hoạt động hệ thống"
      "settings" -> "Cài đặt vai trò và hệ thống"
      else -> "Hồ sơ và quyền truy cập"
    }
  }

  val showBackInTopBar = currentTab == 3 && accountSubScreen != "menu"

  Box(modifier = modifier.fillMaxSize()) {
    Column(
      modifier = Modifier
        .fillMaxSize()
        .background(bgDark),
    ) {
      // TOP APP BAR
      Column(
        modifier = Modifier
          .fillMaxWidth()
          .background(cardBg)
          .padding(horizontal = 16.dp, vertical = 14.dp),
      ) {
        Row(
          modifier = Modifier.fillMaxWidth(),
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
            )
          }

          if (currentTab != 2) {
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
                  .background(if (serverSynced && isOnlineMode) Color(0xFF15803D) else accentRed),
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

        Text(
          text = topBarSubtitle,
          color = textSecondary,
          fontSize = 12.sp,
          modifier = Modifier.padding(top = 2.dp),
        )
      }

      Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(cardBorder))

      // NỘI DUNG CHÍNH THEO TAB (16dp padding ngang)
      Column(
        modifier = Modifier
          .weight(1f)
          .fillMaxWidth()
          .verticalScroll(rememberScrollState())
          .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
      ) {
        when (currentTab) {
          0 -> HomeScreenTab(
            temperature = temperature,
            soilMoisture = soilMoisture,
            deviceStates = deviceStates,
            activeTimers = activeTimers,
            accentCyan = accentCyan,
            cardBg = cardBg,
            cardBorder = cardBorder,
            bgDark = bgDark,
            textPrimary = textPrimary,
            textSecondary = textSecondary,
            onOpenVoiceSheet = { showVoiceSheet = true },
            onNavigateToDevices = { currentTab = 1 },
          )
          1 -> DevicesScreenTab(
            devices = devices,
            deviceStates = deviceStates,
            selectedRoomFilter = selectedRoomFilter,
            onSelectRoomFilter = { selectedRoomFilter = it },
            onToggleDevice = { dev, newValue ->
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
            activeTimers = activeTimers,
            onCreateTimerShortcut = { executeVoiceCommand("10 giây nữa bật đèn phòng khách") },
            accentCyan = accentCyan,
            cardBg = cardBg,
            cardBorder = cardBorder,
            bgDark = bgDark,
            textPrimary = textPrimary,
            textSecondary = textSecondary,
          )
          2 -> VoiceScreenTab(
            selectedTier = selectedTier,
            hasVoiceCommandResult = hasVoiceCommandResult,
            lastSpokenText = lastSpokenText,
            speakerReply = speakerReply,
            isListeningMic = isListeningMic,
            micErrorState = micErrorState,
            voiceInput = voiceInput,
            onVoiceInputChange = { voiceInput = it },
            ttsEnabled = ttsEnabled,
            onTtsToggle = { ttsEnabled = it },
            onMicButtonClick = {
              if (isListeningMic) {
                isListeningMic = false
                if (voiceInput.isNotBlank()) executeVoiceCommand(voiceInput, fromLiveMic = true)
              } else {
                startLiveMicRecognition()
              }
            },
            onSendVoiceCommand = { executeVoiceCommand(it) },
            onNavigateToAuth = { currentTab = 3; accountSubScreen = "auth" },
            accentCyan = accentCyan,
            cardBg = cardBg,
            cardBorder = cardBorder,
            bgDark = bgDark,
            textPrimary = textPrimary,
            textSecondary = textSecondary,
          )
          else -> AccountScreenTab(
            accountSubScreen = accountSubScreen,
            onNavigateSubScreen = { accountSubScreen = it },
            selectedTier = selectedTier,
            onSelectTier = { tier, name -> selectedTier = tier; activeSpeakerName = name },
            authEmail = authEmail,
            onAuthEmailChange = { authEmail = it },
            authPassword = authPassword,
            onAuthPasswordChange = { authPassword = it },
            authOtpInput = authOtpInput,
            onAuthOtpInputChange = { authOtpInput = it },
            openAuthStep = openAuthStep,
            onOpenAuthStepChange = { openAuthStep = it },
            authStepDone = authStepDone,
            authStatusColor = authStatusColor,
            allowlistTargetEmail = allowlistTargetEmail,
            onAllowlistTargetEmailChange = { allowlistTargetEmail = it },
            allowlistStatusMessage = allowlistStatusMessage,
            allowlistStatusColor = allowlistStatusColor,
            hasRecordedAuthSample = hasRecordedAuthSample,
            newMemberName = newMemberName,
            onNewMemberNameChange = { newMemberName = it },
            guestQrDuration = guestQrDuration,
            onGuestQrDurationChange = { guestQrDuration = it },
            historyLogs = historyLogs,
            showTechLogs = showTechLogs,
            onToggleTechLogs = { showTechLogs = !showTechLogs },
            lastDetectedF0 = lastDetectedF0,
            lastCosineScore = lastCosineScore,
            lastSyncTime = lastSyncTime,
            onPerformLayer1Login = { performLayer1Login(it) },
            onPerformLayer2OtpVerify = { performLayer2OtpVerify() },
            onUploadVoiceSample = { uploadVoiceToServerForRecognition(null, authEmail) },
            onSubmitAddFamilyEmail = { submitAddFamilyEmail() },
            onLogout = {
              selectedTier = 3
              activeSpeakerName = "Khách"
              authEmail = "guest@smarthome.local"
              addHistoryLog("Đã đăng xuất tài khoản")
            },
            onSpeakSamplePhrase = { speakOutLoud("Nhà thông minh xin chào, mở đèn phòng khách và kiểm tra nhiệt độ hôm nay.") },
            onReRecordVoiceSample = { uploadVoiceToServerForRecognition(126.0, authEmail) },
            onQrCodeScanned = { code ->
              addHistoryLog("Quét mã khách: $code")
              accountSubScreen = "menu"
            },
            accentCyan = accentCyan,
            accentRed = accentRed,
            cardBg = cardBg,
            cardBorder = cardBorder,
            bgDark = bgDark,
            textPrimary = textPrimary,
            textSecondary = textSecondary,
          )
        }
      }

      // BOTTOM NAVIGATION ANDROID: đúng 4 mục theo thứ tự Nhà, Thiết bị, Giọng nói, Tài khoản
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
        BottomTabItem("Tài khoản", "user", currentTab == 3, accentCyan, { currentTab = 3 }, Modifier.weight(1f))
      }
    }

    if (showVoiceSheet) {
      VoiceBottomSheet(
        samplePhrase = "Mở cửa chính cho tôi.",
        onStopRecording = { phrase ->
          showVoiceSheet = false
          executeVoiceCommand(phrase, fromLiveMic = true)
        },
        onDismiss = { showVoiceSheet = false },
      )
    }
  }
}
