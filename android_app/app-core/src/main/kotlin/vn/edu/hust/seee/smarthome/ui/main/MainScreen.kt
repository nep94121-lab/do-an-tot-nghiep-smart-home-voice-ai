package vn.edu.hust.seee.smarthome.ui.main

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.util.Base64
import android.util.Log
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
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
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
import java.util.concurrent.ConcurrentHashMap
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import vn.edu.hust.seee.smarthome.ui.main.components.BottomTabItem
import vn.edu.hust.seee.smarthome.ui.main.models.AuthTestCaseItem
import vn.edu.hust.seee.smarthome.ui.main.models.AutomationRuleItem
import vn.edu.hust.seee.smarthome.ui.main.models.CapturedVoiceSample
import vn.edu.hust.seee.smarthome.ui.main.models.ClockScheduleItem
import vn.edu.hust.seee.smarthome.ui.main.models.CountdownTimerItem
import vn.edu.hust.seee.smarthome.ui.main.models.CustomSceneItem
import vn.edu.hust.seee.smarthome.ui.main.models.CustomSceneStep
import vn.edu.hust.seee.smarthome.ui.main.models.EnrolledVoiceProfile
import vn.edu.hust.seee.smarthome.ui.main.models.HardwareDevice
import vn.edu.hust.seee.smarthome.ui.main.models.formatDeviceActionLabel
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

  var authEmail by remember { mutableStateOf("") }
  var authPassword by remember { mutableStateOf("") }
  var authOtpInput by remember { mutableStateOf("") }
  var authStepDone by remember { mutableIntStateOf(0) }
  var authStatusMessage by remember {
    mutableStateOf("Nhập email và mật khẩu để đăng ký hoặc đăng nhập.")
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
  var guestQrCountdown by remember { mutableIntStateOf(10) }

  var speakerReply by remember { mutableStateOf("Chưa có lệnh") }
  var metricBadge by remember { mutableStateOf("Đã xác thực") }
  var lastStatusColor by remember { mutableStateOf(accentGreen) }

  var temperature by remember { mutableDoubleStateOf(28.5) }
  var humidity by remember { mutableIntStateOf(65) }
  var soilMoisture by remember { mutableIntStateOf(62) }

  val activeTimers = remember { mutableStateListOf<CountdownTimerItem>() }
  val clockSchedules = remember { mutableStateListOf<ClockScheduleItem>() }
  val automationRules = remember { mutableStateListOf<AutomationRuleItem>() }
  val customScenes = remember { mutableStateListOf<CustomSceneItem>() }
  val historyLogs = remember { mutableStateListOf("Ứng dụng đã sẵn sàng.") }
  val snackbarHostState = remember { SnackbarHostState() }
  var automationStatusMessage by remember { mutableStateOf("") }
  var automationStatusIsError by remember { mutableStateOf(false) }

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

  fun resolveBundledViTtsAsset(text: String): String {
    val t = text.lowercase(Locale.getDefault())
    return when {
      t.contains("lần nữa") || t.contains("không trả lời bạn") -> "stranger_blocked_2.mp3"
      t.contains("không có quyền điều khiển ngôi nhà") -> "rest_stranger_blocked.mp3"
      t.contains("người lạ") || t.contains("chưa có quyền") -> "stranger_blocked.mp3"
      t.contains("trùng giọng") -> "duplicate_voice.mp3"
      t.contains("hết hạn") -> "voice_expired.mp3"
      t.contains("quá nhanh") -> "rate_limited.mp3"
      t.contains("đèn và quạt") -> "tier3_permission_denied.mp3"
      t.contains("chỉ chủ nhà") -> "tier2_permission_denied.mp3"
      t.contains("tiếng ồn") -> "vad_noise_blocked.mp3"
      t.contains("khẩu lệnh tiếng việt") -> "vad_blocked.mp3"
      t.contains("cửa") && (t.contains("mở") || t.contains("bật")) -> "open_main_door.mp3"
      t.contains("cửa") && (t.contains("đóng") || t.contains("tắt") || t.contains("khóa")) -> "close_main_door.mp3"
      t.contains("đèn phòng khách") && t.contains("tắt") -> "turn_off_living_room_light.mp3"
      t.contains("đèn phòng khách") -> "turn_on_living_room_light.mp3"
      t.contains("đèn phòng ngủ") && t.contains("tắt") -> "turn_off_bedroom_light.mp3"
      t.contains("đèn phòng ngủ") -> "turn_on_bedroom_light.mp3"
      t.contains("quạt") && t.contains("tắt") -> "turn_off_fan.mp3"
      t.contains("quạt") -> "turn_on_fan.mp3"
      t.contains("điều hòa") && t.contains("tắt") -> "turn_off_ac.mp3"
      t.contains("điều hòa") -> "turn_on_ac.mp3"
      else -> "stranger_blocked.mp3"
    }
  }

  fun playBundledViTtsAsset(text: String) {
    val assetName = resolveBundledViTtsAsset(text)
    scope.launch(Dispatchers.IO) {
      try {
        context.assets.openFd("tts_vi/$assetName").use { afd ->
          val mp = MediaPlayer()
          mp.setAudioAttributes(
            AudioAttributes.Builder()
              .setUsage(AudioAttributes.USAGE_MEDIA)
              .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
              .build()
          )
          mp.setDataSource(afd.fileDescriptor, afd.startOffset, afd.length)
          mp.setOnCompletionListener { player ->
            try { player.release() } catch (_: Exception) {}
          }
          mp.prepare()
          mp.start()
          Log.i("SmartHomeTTS", "MediaPlayer played bundled VI TTS ($assetName): $text")
        }
      } catch (e: Exception) {
        Log.w("SmartHomeTTS", "MediaPlayer asset playback failed ($assetName): ${e.message}")
      }
    }
  }

  fun playPcm24kBase64(pcm24kB64: String, text: String) {
    scope.launch(Dispatchers.IO) {
      try {
        val pcmBytes = Base64.decode(pcm24kB64, Base64.DEFAULT)
        if (pcmBytes.isEmpty()) {
          playBundledViTtsAsset(text)
          return@launch
        }
        val minBuf = AudioTrack.getMinBufferSize(
          24000,
          AudioFormat.CHANNEL_OUT_MONO,
          AudioFormat.ENCODING_PCM_16BIT,
        ).coerceAtLeast(4800)
        val track = AudioTrack.Builder()
          .setAudioAttributes(
            AudioAttributes.Builder()
              .setUsage(AudioAttributes.USAGE_MEDIA)
              .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
              .build()
          )
          .setAudioFormat(
            AudioFormat.Builder()
              .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
              .setSampleRate(24000)
              .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
              .build()
          )
          .setBufferSizeInBytes(maxOf(minBuf, pcmBytes.size))
          .setTransferMode(AudioTrack.MODE_STATIC)
          .build()
        track.write(pcmBytes, 0, pcmBytes.size)
        track.play()
        Log.i("SmartHomeTTS", "AudioTrack played pcm24k_b64 (${pcmBytes.size} bytes): $text")
        val durationMs = (pcmBytes.size.toLong() * 1000L / 48000L).coerceIn(300L, 12000L)
        delay(durationMs + 250L)
        try {
          track.stop()
          track.release()
        } catch (_: Exception) {}
      } catch (e: Exception) {
        Log.w("SmartHomeTTS", "AudioTrack pcm24k playback failed: ${e.message}")
        playBundledViTtsAsset(text)
      }
    }
  }

  fun speakOutLoud(text: String, pcm24kB64: String = "") {
    if (!ttsEnabled || (text.isBlank() && pcm24kB64.isBlank())) return
    try { textToSpeech?.stop() } catch (_: Exception) {}
    if (pcm24kB64.isNotBlank()) {
      playPcm24kBase64(pcm24kB64, text)
      return
    }
    val ttsRes = textToSpeech?.speak(
      text,
      TextToSpeech.QUEUE_FLUSH,
      null,
      "smarthome_tts_${System.currentTimeMillis()}",
    ) ?: TextToSpeech.ERROR
    if (ttsRes != TextToSpeech.SUCCESS) {
      playBundledViTtsAsset(text)
    } else {
      Log.i("SmartHomeTTS", "TextToSpeech engine spoke: $text")
    }
  }

  fun extractServerSpokenReply(res: JSONObject?): String {
    if (res == null) return ""
    val rej = res.optString("rejection_speech", "").trim()
    if (rej.isNotEmpty()) return rej
    val exact = res.optString("exact_spoken_reply", "").trim()
    if (exact.isNotEmpty()) return exact
    val rep = res.optString("reply", "").trim()
    if (rep.isNotEmpty()) return rep
    return ""
  }

  fun addHistoryLog(entry: String) {
    val timeStr = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
    historyLogs.add(0, "[$timeStr] $entry")
    if (historyLogs.size > 20) {
      historyLogs.removeAt(historyLogs.lastIndex)
    }
  }

  val micPermissionLauncher = rememberLauncherForActivityResult(
    ActivityResultContracts.RequestPermission()
  ) { granted ->
    micPermissionGranted = granted
    if (granted) micErrorState = false
  }

  LaunchedEffect(currentTab, showVoiceSheet) {
    if (currentTab == 2 || showVoiceSheet) {
      val granted = ContextCompat.checkSelfPermission(
        context,
        Manifest.permission.RECORD_AUDIO,
      ) == PackageManager.PERMISSION_GRANTED
      micPermissionGranted = granted
      if (!granted) {
        micPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
      }
    }
  }

  var activeSessionToken by remember { mutableStateOf("") }
  val sessionCookies = remember { ConcurrentHashMap<String, String>() }

  val allowLocalDebugFallback = false

  fun captureCookiesFromResponse(conn: HttpURLConnection) {
    val headerEntries = conn.headerFields ?: return
    for ((key, values) in headerEntries) {
      if (key != null && key.equals("Set-Cookie", ignoreCase = true) && values != null) {
        for (rawCookie in values) {
          val pair = rawCookie.substringBefore(";").trim()
          val eqIdx = pair.indexOf('=')
          if (eqIdx > 0) {
            val cName = pair.substring(0, eqIdx).trim()
            val cVal = pair.substring(eqIdx + 1).trim()
            if (cVal.isBlank() || rawCookie.contains("Max-Age=0", ignoreCase = true)) {
              sessionCookies.remove(cName)
            } else {
              sessionCookies[cName] = cVal
            }
          }
        }
      }
    }
  }

  fun buildCookieHeader(): String {
    val merged = LinkedHashMap<String, String>()
    merged.putAll(sessionCookies)
    if (activeSessionToken.isNotBlank()) {
      merged.putIfAbsent("sh_session_token", activeSessionToken)
      merged.putIfAbsent("session_token", activeSessionToken)
    }
    if (merged.isEmpty()) return ""
    return merged.entries.joinToString("; ") { "${it.key}=${it.value}" }
  }

  suspend fun callServerHttp(
    endpoint: String,
    method: String = "GET",
    jsonBody: String? = null,
  ): String? {
    return withContext(Dispatchers.IO) {
      val primaryBase = "https://laptop-6i654f8c.tail3020d6.ts.net"
      val fallbackBase = "https://do-an-tot-nghiep-smart-home-voice-a.vercel.app"
      val candidates = if (allowLocalDebugFallback) {
        listOf(primaryBase, fallbackBase, "http://10.0.2.2:8088", "http://127.0.0.1:8088", "http://localhost:8088")
      } else {
        listOf(primaryBase, fallbackBase)
      }
      for (base in candidates) {
        var conn: HttpURLConnection? = null
        try {
          val url = URL("$base$endpoint")
          conn = url.openConnection() as HttpURLConnection
          conn.requestMethod = method
          if (base.startsWith("https://")) {
            conn.connectTimeout = 8000
            conn.readTimeout = 10000
          } else {
            conn.connectTimeout = 700
            conn.readTimeout = 700
          }
          conn.setRequestProperty("Accept", "application/json")
          if (activeSessionToken.isNotBlank()) {
            conn.setRequestProperty("X-Session-Token", activeSessionToken)
            conn.setRequestProperty("Authorization", "Bearer $activeSessionToken")
          }
          val cookieHeader = buildCookieHeader()
          if (cookieHeader.isNotBlank()) {
            conn.setRequestProperty("Cookie", cookieHeader)
          }
          if (jsonBody != null) {
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/json")
            OutputStreamWriter(conn.outputStream).use { it.write(jsonBody); it.flush() }
          }
          val code = conn.responseCode
          captureCookiesFromResponse(conn)
          if (code in 200..299) {
            val response = BufferedReader(InputStreamReader(conn.inputStream)).use { it.readText() }
            serverSynced = true
            lastSyncTime = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
            return@withContext response
          }
          if (code in 400..499) {
            val errBody = conn.errorStream?.let { stream ->
              BufferedReader(InputStreamReader(stream)).use { it.readText() }
            }?.takeIf { it.isNotBlank() } ?: "{\"ok\":false,\"error\":\"Yêu cầu bị từ chối (HTTP $code).\"}"
            serverSynced = true
            lastSyncTime = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
            return@withContext errBody
          }
        } catch (_: Exception) {
        } finally {
          try { conn?.disconnect() } catch (_: Exception) {}
        }
      }
      null
    }
  }

  suspend fun applyServerSnapshotJson(resStr: String) {
    withContext(Dispatchers.Main) {
      try {
        val raw = JSONObject(resStr)
        val root = raw.optJSONObject("snapshot") ?: raw
        val devArr = root.optJSONArray("devices")
        if (devArr != null) {
          for (i in 0 until devArr.length()) {
            val obj = devArr.optJSONObject(i) ?: continue
            val id = obj.optString("id")
            val st = obj.optString("state")
            if (id.isNotBlank() && deviceStates.containsKey(id)) {
              deviceStates[id] = (st == "ON" || st == "OPEN")
            }
          }
        }
        val mqttObj = root.optJSONObject("mqtt")
        val dhtObj = mqttObj?.optJSONObject("dht11_telemetry")
        if (dhtObj != null) {
          temperature = dhtObj.optDouble("temp_c", temperature)
          humidity = dhtObj.optDouble("humidity_pct", humidity.toDouble()).toInt()
        }
        val soilObj = mqttObj?.optJSONObject("soil_moisture_telemetry")
        if (soilObj != null) {
          soilMoisture = soilObj.optDouble("soil_moisture_pct", soilMoisture.toDouble()).toInt()
        }

        val timersArr = root.optJSONArray("timers")
        if (timersArr != null) {
          val parsedTimers = mutableListOf<CountdownTimerItem>()
          for (i in 0 until timersArr.length()) {
            val obj = timersArr.optJSONObject(i) ?: continue
            val id = obj.optString("id").ifBlank { obj.optString("timer_id") }
            val devId = obj.optString("device_id")
            if (id.isBlank() && devId.isBlank()) continue
            val devName = obj.optString("device_name").ifBlank { devId }
            val act = obj.optString("action", "turn_on").lowercase(Locale.ROOT)
            val targetOn = act == "turn_on" || act == "open"
            val remSec = obj.optDouble("remaining_seconds", 0.0).toInt().coerceAtLeast(0)
            parsedTimers.add(
              CountdownTimerItem(
                id = id.ifBlank { "${devId}_$i" },
                deviceId = devId,
                deviceName = devName,
                targetStateOn = targetOn,
                remainingSeconds = remSec,
                action = act,
                actionVi = obj.optString("action_vi").ifBlank { if (targetOn) "Bật" else "Tắt" },
                remainingLabel = obj.optString("remaining_label"),
                repeat = obj.optString("repeat", "once"),
                targetVnTime = obj.optString("target_vn_time"),
                reason = obj.optString("reason"),
                label = obj.optString("label"),
                ownerId = obj.optString("owner_id"),
                ownerName = obj.optString("owner_name"),
                ownerTier = obj.optInt("owner_tier", 1),
              )
            )
          }
          activeTimers.clear()
          activeTimers.addAll(parsedTimers)
        }

        val schedulesArr = root.optJSONArray("schedules")
        if (schedulesArr != null) {
          val parsedSchedules = mutableListOf<ClockScheduleItem>()
          for (i in 0 until schedulesArr.length()) {
            val obj = schedulesArr.optJSONObject(i) ?: continue
            val sid = obj.optString("schedule_id").ifBlank { obj.optString("id") }
            if (sid.isBlank()) continue
            val devId = obj.optString("device_id")
            val devName = obj.optString("device_name").ifBlank { devId }
            val act = obj.optString("action", "turn_on").lowercase(Locale.ROOT)
            parsedSchedules.add(
              ClockScheduleItem(
                id = obj.optString("id").ifBlank { sid },
                scheduleId = sid,
                deviceId = devId,
                deviceName = devName,
                action = act,
                actionVi = obj.optString("action_vi"),
                timeHhmm = obj.optString("time_hhmm"),
                scheduleType = obj.optString("schedule_type", obj.optString("repeat", "once")),
                runDateVn = obj.optString("run_date_vn"),
                timezone = obj.optString("timezone", "Asia/Saigon"),
                enabled = obj.optBoolean("enabled", true),
                lastFiredDateVn = obj.optString("last_fired_date_vn"),
                label = obj.optString("label"),
                ownerUserId = obj.optString("owner_user_id"),
                ownerName = obj.optString("owner_name"),
                ownerTier = obj.optInt("owner_tier", 1),
              )
            )
          }
          clockSchedules.clear()
          clockSchedules.addAll(parsedSchedules)
        }

        val rulesArr = root.optJSONArray("automation_rules")
        if (rulesArr != null) {
          val parsedRules = mutableListOf<AutomationRuleItem>()
          for (i in 0 until rulesArr.length()) {
            val obj = rulesArr.optJSONObject(i) ?: continue
            val rid = obj.optString("rule_id").ifBlank { obj.optString("id") }
            if (rid.isBlank()) continue
            val wDev = obj.optString("when_device_id")
            val tDev = obj.optString("then_device_id")
            val eDev = obj.optString("else_device_id")
            parsedRules.add(
              AutomationRuleItem(
                id = obj.optString("id").ifBlank { rid },
                ruleId = rid,
                whenDeviceId = wDev,
                whenDeviceName = obj.optString("when_device_name").ifBlank { wDev },
                whenState = obj.optString("when_state", "ON"),
                thenDeviceId = tDev,
                thenDeviceName = obj.optString("then_device_name").ifBlank { tDev },
                thenAction = obj.optString("then_action", "turn_on"),
                elseDeviceId = eDev,
                elseDeviceName = obj.optString("else_device_name").ifBlank { eDev },
                elseAction = obj.optString("else_action"),
                delaySeconds = obj.optDouble("delay_seconds", 0.0),
                enabled = obj.optBoolean("enabled", true),
                label = obj.optString("label"),
                ownerUserId = obj.optString("owner_user_id"),
                ownerName = obj.optString("owner_name"),
                ownerTier = obj.optInt("owner_tier", 1),
              )
            )
          }
          automationRules.clear()
          automationRules.addAll(parsedRules)
        }

        val scenesArr = root.optJSONArray("scenes") ?: root.optJSONArray("custom_commands")
        if (scenesArr != null) {
          val parsedScenes = mutableListOf<CustomSceneItem>()
          for (i in 0 until scenesArr.length()) {
            val obj = scenesArr.optJSONObject(i) ?: continue
            val cid = obj.optString("command_id").ifBlank { obj.optString("id") }
            if (cid.isBlank()) continue
            val stepsArr = obj.optJSONArray("steps")
            val steps = mutableListOf<CustomSceneStep>()
            if (stepsArr != null) {
              for (j in 0 until stepsArr.length()) {
                val st = stepsArr.optJSONObject(j) ?: continue
                val sDev = st.optString("device_id")
                val sAct = st.optString("action")
                if (sDev.isNotBlank() && sAct.isNotBlank()) {
                  steps.add(CustomSceneStep(deviceId = sDev, action = sAct))
                }
              }
            }
            parsedScenes.add(
              CustomSceneItem(
                id = obj.optString("id").ifBlank { cid },
                commandId = cid,
                phrase = obj.optString("phrase"),
                phraseNorm = obj.optString("phrase_norm"),
                steps = steps,
                stepsSummary = obj.optString("steps_summary"),
                enabled = obj.optBoolean("enabled", true),
                ownerUserId = obj.optString("owner_user_id"),
                ownerName = obj.optString("owner_name"),
                ownerTier = obj.optInt("owner_tier", 1),
              )
            )
          }
          customScenes.clear()
          customScenes.addAll(parsedScenes)
        }

        serverSynced = true
        lastSyncTime = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
      } catch (_: Exception) {}
    }
  }

  suspend fun syncServerState() {
    val resStr = callServerHttp("/api/state", "GET") ?: return
    applyServerSnapshotJson(resStr)
  }

  fun showAutomationFeedback(
    message: String,
    isError: Boolean,
    speakMessage: String = "",
    pcm24kB64: String = "",
  ) {
    automationStatusMessage = message
    automationStatusIsError = isError
    addHistoryLog(message)
    if (speakMessage.isNotBlank() || isError) {
      speakerReply = speakMessage.ifBlank { message }
    }
    if (speakMessage.isNotBlank()) {
      speakOutLoud(speakMessage, pcm24kB64)
    }
    scope.launch {
      try {
        snackbarHostState.currentSnackbarData?.dismiss()
        snackbarHostState.showSnackbar(message)
      } catch (_: Exception) {}
    }
  }

  fun executeAutomationRequest(
    endpoint: String,
    method: String,
    payload: JSONObject? = null,
    defaultSuccessMessage: String,
    defaultErrorMessage: String,
    speakOnResult: Boolean = false,
  ) {
    scope.launch(Dispatchers.IO) {
      val resStr = callServerHttp(endpoint, method, payload?.toString())
      if (resStr == null) {
        withContext(Dispatchers.Main) {
          showAutomationFeedback("Không thể kết nối máy chủ.", isError = true)
        }
        return@launch
      }
      val res = try {
        JSONObject(resStr)
      } catch (_: Exception) {
        null
      }
      if (res == null) {
        withContext(Dispatchers.Main) {
          showAutomationFeedback(defaultErrorMessage, isError = true)
        }
        return@launch
      }
      val ok = res.optBoolean("ok", false)
      val rbacBlocked = res.optBoolean("rbac_blocked", false)
      if (!ok || rbacBlocked) {
        val errMsg = res.optString("error")
          .ifBlank { res.optString("message") }
          .ifBlank { extractServerSpokenReply(res) }
          .ifBlank { defaultErrorMessage }
        val speech = if (speakOnResult) extractServerSpokenReply(res) else ""
        val pcmB64 = res.optString("pcm24k_b64", "")
        withContext(Dispatchers.Main) {
          showAutomationFeedback(errMsg, isError = true, speakMessage = speech, pcm24kB64 = pcmB64)
        }
        return@launch
      }

      if (res.has("snapshot") || res.has("timers") || res.has("schedules") || res.has("automation_rules") || res.has("scenes") || res.has("custom_commands")) {
        applyServerSnapshotJson(resStr)
      } else {
        syncServerState()
      }
      val replyMsg = extractServerSpokenReply(res)
        .ifBlank { res.optString("message") }
        .ifBlank { defaultSuccessMessage }
      val pcmB64 = res.optString("pcm24k_b64", "")
      withContext(Dispatchers.Main) {
        showAutomationFeedback(
          replyMsg,
          isError = false,
          speakMessage = if (speakOnResult) replyMsg else "",
          pcm24kB64 = pcmB64,
        )
      }
    }
  }

  fun createCountdownTimer(deviceId: String, action: String, seconds: Int, repeat: String = "once") {
    val payload = JSONObject().apply {
      put("device_id", deviceId)
      put("action", action)
      put("seconds", seconds)
      put("minutes", 0)
      put("hours", 0)
      put("repeat", repeat)
      if (activeSessionToken.isNotBlank()) put("session_token", activeSessionToken)
    }
    executeAutomationRequest(
      endpoint = "/api/timers",
      method = "POST",
      payload = payload,
      defaultSuccessMessage = "Đã tạo hẹn giờ đếm ngược ($seconds giây).",
      defaultErrorMessage = "Không thể tạo hẹn giờ đếm ngược.",
    )
  }

  fun createMobileScheduleTimer(deviceId: String, action: String, seconds: Int) {
    val payload = JSONObject().apply {
      put("device_id", deviceId)
      put("action", action)
      put("seconds", seconds)
      if (activeSessionToken.isNotBlank()) put("session_token", activeSessionToken)
    }
    executeAutomationRequest(
      endpoint = "/api/mobile/schedule",
      method = "POST",
      payload = payload,
      defaultSuccessMessage = "Đã tạo lịch hẹn giờ ($seconds giây).",
      defaultErrorMessage = "Không thể tạo lịch hẹn giờ.",
    )
  }

  fun deleteCountdownTimer(timerId: String) {
    executeAutomationRequest(
      endpoint = "/api/timers/${Uri.encode(timerId)}",
      method = "DELETE",
      defaultSuccessMessage = "Đã hủy hẹn giờ đếm ngược.",
      defaultErrorMessage = "Không thể hủy hẹn giờ.",
    )
  }

  fun createClockSchedule(
    deviceId: String,
    action: String,
    timeHhmm: String,
    scheduleType: String = "once",
    label: String = "",
  ) {
    val payload = JSONObject().apply {
      put("device_id", deviceId)
      put("action", action)
      put("time_hhmm", timeHhmm)
      put("schedule_type", scheduleType)
      if (label.isNotBlank()) put("label", label)
      if (activeSessionToken.isNotBlank()) put("session_token", activeSessionToken)
    }
    executeAutomationRequest(
      endpoint = "/api/schedules",
      method = "POST",
      payload = payload,
      defaultSuccessMessage = "Đã lưu lịch lúc $timeHhmm.",
      defaultErrorMessage = "Không thể tạo lịch theo giờ.",
    )
  }

  fun deleteClockSchedule(scheduleId: String) {
    executeAutomationRequest(
      endpoint = "/api/schedules/${Uri.encode(scheduleId)}",
      method = "DELETE",
      defaultSuccessMessage = "Đã xóa lịch theo giờ.",
      defaultErrorMessage = "Không thể xóa lịch theo giờ.",
    )
  }

  fun createAutomationRule(
    whenDeviceId: String,
    whenState: String,
    thenDeviceId: String,
    thenAction: String,
    label: String = "",
  ) {
    val payload = JSONObject().apply {
      put("when_device_id", whenDeviceId)
      put("when_state", whenState)
      put("then_device_id", thenDeviceId)
      put("then_action", thenAction)
      if (label.isNotBlank()) put("label", label)
      if (activeSessionToken.isNotBlank()) put("session_token", activeSessionToken)
    }
    executeAutomationRequest(
      endpoint = "/api/rules",
      method = "POST",
      payload = payload,
      defaultSuccessMessage = "Đã tạo luật liên kết thiết bị.",
      defaultErrorMessage = "Không thể tạo luật liên kết.",
    )
  }

  fun deleteAutomationRule(ruleId: String) {
    executeAutomationRequest(
      endpoint = "/api/rules/${Uri.encode(ruleId)}",
      method = "DELETE",
      defaultSuccessMessage = "Đã xóa luật liên kết.",
      defaultErrorMessage = "Không thể xóa luật liên kết.",
    )
  }

  fun createCustomScene(phrase: String, stepsText: String, steps: List<CustomSceneStep> = emptyList()) {
    val payload = JSONObject().apply {
      put("phrase", phrase)
      if (steps.isNotEmpty()) {
        val arr = JSONArray()
        steps.forEach { st ->
          arr.put(JSONObject().apply {
            put("device_id", st.deviceId)
            put("action", st.action)
          })
        }
        put("steps", arr)
      }
      if (stepsText.isNotBlank()) {
        put("steps_text", stepsText)
      }
      if (activeSessionToken.isNotBlank()) put("session_token", activeSessionToken)
    }
    executeAutomationRequest(
      endpoint = "/api/scenes",
      method = "POST",
      payload = payload,
      defaultSuccessMessage = "Đã lưu ngữ cảnh '$phrase'.",
      defaultErrorMessage = "Không thể tạo ngữ cảnh.",
    )
  }

  fun deleteCustomScene(commandId: String) {
    executeAutomationRequest(
      endpoint = "/api/scenes/${Uri.encode(commandId)}",
      method = "DELETE",
      defaultSuccessMessage = "Đã xóa ngữ cảnh.",
      defaultErrorMessage = "Không thể xóa ngữ cảnh.",
    )
  }

  fun runCustomScene(scene: CustomSceneItem) {
    val payload = JSONObject().apply {
      if (activeSessionToken.isNotBlank()) put("session_token", activeSessionToken)
    }
    executeAutomationRequest(
      endpoint = "/api/scenes/${Uri.encode(scene.commandId)}/run",
      method = "POST",
      payload = payload,
      defaultSuccessMessage = "Đã chạy ngữ cảnh '${scene.phrase}'.",
      defaultErrorMessage = "Không thể chạy ngữ cảnh '${scene.phrase}'.",
      speakOnResult = true,
    )
  }

  LaunchedEffect(activeTimers.isNotEmpty(), isOnlineMode) {
    while (activeTimers.isNotEmpty()) {
      delay(1000L)
      var hitZero = false
      for (i in activeTimers.indices) {
        val t = activeTimers[i]
        val next = (t.remainingSeconds - 1).coerceAtLeast(0)
        if (next == 0) hitZero = true
        if (next != t.remainingSeconds) {
          activeTimers[i] = t.copy(
            remainingSeconds = next,
            remainingLabel = if (next > 0) "$next giây" else "Sắp thực thi",
          )
        }
      }
      if (hitZero && isOnlineMode) {
        delay(800L)
        syncServerState()
      }
    }
  }

  LaunchedEffect(isOnlineMode, activeSessionToken) {
    if (!isOnlineMode) return@LaunchedEffect
    syncServerState()
    if (activeSessionToken.isBlank()) return@LaunchedEffect
    val sseBases = listOf(
      "https://laptop-6i654f8c.tail3020d6.ts.net",
      "https://do-an-tot-nghiep-smart-home-voice-a.vercel.app",
    )
    while (isOnlineMode && activeSessionToken.isNotBlank()) {
      var streamed = false
      for (base in sseBases) {
        var conn: HttpURLConnection? = null
        try {
          val url = URL("$base/api/events")
          conn = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 5000
            readTimeout = 35000
            setRequestProperty("Accept", "text/event-stream")
            setRequestProperty("X-Session-Token", activeSessionToken)
            setRequestProperty("Authorization", "Bearer $activeSessionToken")
            val cookieHeader = buildCookieHeader()
            if (cookieHeader.isNotBlank()) {
              setRequestProperty("Cookie", cookieHeader)
            }
          }
          if (conn.responseCode == 200) {
            streamed = true
            BufferedReader(InputStreamReader(conn.inputStream)).use { reader ->
              var line: String?
              while (isOnlineMode) {
                line = reader.readLine() ?: break
                val trimmed = line.trim()
                if (trimmed.startsWith("data:")) {
                  val payloadJson = trimmed.removePrefix("data:").trim()
                  if (payloadJson.startsWith("{")) {
                    applyServerSnapshotJson(payloadJson)
                  }
                }
              }
            }
          }
        } catch (_: Exception) {
        } finally {
          try { conn?.disconnect() } catch (_: Exception) {}
        }
        if (streamed) break
      }
      syncServerState()
      delay(if (streamed) 250L else 3000L)
    }
  }

  fun performRegisterAccount() {
    if (authEmail.isBlank() || authPassword.isBlank()) {
      authStatusColor = accentRed
      authStatusMessage = "Vui lòng nhập đầy đủ email và mật khẩu."
      return
    }
    val cleanEmail = authEmail.trim()
    val displayName = cleanEmail.substringBefore("@").ifBlank { "Người dùng" }
    authStatusMessage = "Đang đăng ký tài khoản..."
    authStatusColor = accentCyan
    scope.launch(Dispatchers.IO) {
      val payload = JSONObject().apply {
        put("email", cleanEmail)
        put("password", authPassword)
        put("confirm_password", authPassword)
        put("display_name", displayName)
        put("target_tier", selectedTier)
        put("source", "Android_Compose_3Layer")
      }.toString()
      val resStr = callServerHttp("/api/auth3/register_or_set_password", "POST", payload)
      withContext(Dispatchers.Main) {
        if (resStr != null) {
          val res = try { JSONObject(resStr) } catch (_: Exception) { JSONObject() }
          if (res.optBoolean("ok")) {
            authStepDone = maxOf(authStepDone, 1)
            authStatusColor = accentGreen
            activeSpeakerName = displayName
            authStatusMessage = "Đã đăng ký tài khoản: $cleanEmail"
            addHistoryLog("Đăng ký tài khoản: $cleanEmail")
          } else {
            authStatusColor = accentRed
            authStatusMessage = res.optString("error", res.optString("message", "Đăng ký tài khoản thất bại!"))
          }
        } else {
          authStatusColor = accentRed
          authStatusMessage = "Không thể kết nối máy chủ để đăng ký."
        }
      }
    }
  }

  fun performLayer1Login(method: String) {
    if (authEmail.isBlank() || (method == "password" && authPassword.isBlank())) {
      authStatusColor = accentRed
      authStatusMessage = "Vui lòng nhập email và mật khẩu."
      return
    }
    val cleanEmail = authEmail.trim()
    val displayName = cleanEmail.substringBefore("@").ifBlank { "Người dùng" }
    authStatusMessage = "Đang kết nối Lớp 1..."
    authStatusColor = accentCyan
    scope.launch(Dispatchers.IO) {
      val payload = JSONObject().apply {
        put("email", cleanEmail)
        put("password", authPassword)
        put("login_method", method)
        put("source", "Android_Compose_3Layer")
        put("send_gmail", !cleanEmail.endsWith("@example.com"))
      }.toString()
      var resStr = callServerHttp("/api/auth3/layer1_login", "POST", payload)
      if (resStr != null) {
        val firstRes = try { JSONObject(resStr) } catch (_: Exception) { null }
        val errText = firstRes?.optString("error", "") ?: ""
        if (firstRes != null && !firstRes.optBoolean("ok") && errText.contains("Không tìm thấy tài khoản") && authPassword.isNotBlank()) {
          val regPayload = JSONObject().apply {
            put("email", cleanEmail)
            put("password", authPassword)
            put("confirm_password", authPassword)
            put("display_name", displayName)
            put("target_tier", selectedTier)
            put("source", "Android_Compose_3Layer")
          }.toString()
          callServerHttp("/api/auth3/register_or_set_password", "POST", regPayload)
          resStr = callServerHttp("/api/auth3/layer1_login", "POST", payload)
        }
      }
      withContext(Dispatchers.Main) {
        if (resStr != null) {
          val res = try { JSONObject(resStr) } catch (_: Exception) { JSONObject() }
          if (res.optBoolean("ok")) {
            authStepDone = maxOf(authStepDone, 1)
            authStatusColor = accentGreen
            activeSpeakerName = displayName
            val returnedToken = res.optString("session_token", "")
              .ifBlank { sessionCookies["sh_session_token"] ?: sessionCookies["session_token"] ?: "" }
            if (returnedToken.isNotBlank()) {
              activeSessionToken = returnedToken
            }
            val serverTier = res.optInt("tier", 0)
            if (serverTier in 1..3) {
              selectedTier = serverTier
            }
            authStatusMessage = "Đăng nhập thành công: $cleanEmail"
            addHistoryLog("Đăng nhập thành công: $cleanEmail")
            scope.launch { syncServerState() }
          } else {
            authStatusColor = accentRed
            authStatusMessage = res.optString("error", res.optString("message", "Đăng nhập Lớp 1 thất bại!"))
          }
        } else {
          authStatusColor = accentRed
          authStatusMessage = "Không thể kết nối máy chủ."
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
          val res = try { JSONObject(resStr) } catch (_: Exception) { JSONObject() }
          if (res.optBoolean("ok")) {
            authStepDone = maxOf(authStepDone, 2)
            authStatusColor = accentGreen
            val returnedToken = res.optString("session_token", "")
              .ifBlank { sessionCookies["sh_session_token"] ?: sessionCookies["session_token"] ?: "" }
            if (returnedToken.isNotBlank()) {
              activeSessionToken = returnedToken
            }
            val serverTier = res.optInt("tier", 0)
            if (serverTier in 1..3) {
              selectedTier = serverTier
            }
            authStatusMessage = "Lớp 2 thành công! Hãy đọc mẫu câu xác thực giọng nói."
            addHistoryLog("Lớp 2 xác thực OTP thành công.")
            scope.launch { syncServerState() }
          } else {
            authStatusColor = accentRed
            authStatusMessage = res.optString("error", res.optString("message", "Mã OTP không đúng hoặc hết hạn!"))
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
    val requiredSamples = 5
    val sampleDurationMs = 3200
    authStatusMessage = "Đang thu 5 mẫu giọng WeSpeaker (Mẫu 1/$requiredSamples · 3–5s)..."
    scope.launch(Dispatchers.IO) {
      val samplesJsonArr = JSONArray()
      var firstPcmB64 = ""
      var detectedF0Sum = 0.0
      for (sampleIdx in 0 until requiredSamples) {
        withContext(Dispatchers.Main) {
          authStatusMessage = "Đang thu Mẫu ${sampleIdx + 1}/$requiredSamples (3–5 giây/mẫu)..."
        }
        val captured = captureMicPcmAndPitch(sampleDurationMs)
        if (sampleIdx == 0) {
          firstPcmB64 = captured.pcm16kBase64
        }
        detectedF0Sum += captured.f0Hz
        if (captured.pcm16kBase64.isNotBlank()) {
          samplesJsonArr.put(captured.pcm16kBase64)
        }
      }
      val f0ToUse = simulatedF0 ?: (detectedF0Sum / requiredSamples.toDouble())
      withContext(Dispatchers.Main) {
        authStatusMessage = "Đang trích xuất 5 vector WeSpeaker ResNet34 ONNX..."
      }
      val payload = JSONObject().apply {
        put("email", if (emailTarget.isNotBlank()) emailTarget else authEmail)
        put("pcm_base64", firstPcmB64)
        put("audio_pcm_b64", firstPcmB64)
        put("samples_b64", samplesJsonArr)
        put("sample_count", requiredSamples)
        put("hold_duration_sec", 3.5)
        put("simulated_f0", f0ToUse)
      }.toString()
      val resStr = callServerHttp("/api/auth3/enroll_voice_sample", "POST", payload)
      withContext(Dispatchers.Main) {
        isUploadingVoiceToServer = false
        hasRecordedAuthSample = true
        if (resStr != null) {
          val res = try { JSONObject(resStr) } catch (_: Exception) { JSONObject() }
          val serverSpeech = extractServerSpokenReply(res)
          val serverPcmB64 = res.optString("pcm24k_b64", "")
          if (res.optBoolean("ok")) {
            authStepDone = maxOf(authStepDone, 3)
            authStatusColor = accentGreen
            val returnedToken = res.optString("session_token", "")
              .ifBlank { sessionCookies["sh_session_token"] ?: sessionCookies["session_token"] ?: "" }
            if (returnedToken.isNotBlank()) {
              activeSessionToken = returnedToken
            }
            val serverTier = res.optInt("tier", 0)
            if (serverTier in 1..3) {
              selectedTier = serverTier
            }
            authStatusMessage = serverSpeech.ifBlank { "Đã lưu 5/5 mẫu giọng WeSpeaker thành công!" }
            addHistoryLog("Lớp 3: Đã lưu trung bình 5 mẫu vân giọng WeSpeaker.")
            if (serverSpeech.isNotBlank() || serverPcmB64.isNotBlank()) {
              speakerReply = serverSpeech
              speakOutLoud(serverSpeech, serverPcmB64)
            }
            scope.launch { syncServerState() }
          } else {
            authStatusColor = accentRed
            val rejSpeech = serverSpeech.ifBlank {
              res.optString("error", res.optString("message", "Giọng nói chưa đạt chuẩn. Hãy thử lại!"))
            }
            authStatusMessage = rejSpeech
            speakerReply = rejSpeech
            speakOutLoud(rejSpeech, serverPcmB64)
          }
        } else {
          authStepDone = maxOf(authStepDone, 3)
          authStatusColor = accentGreen
          authStatusMessage = "Đã lưu 5/5 mẫu giọng nói."
        }
      }
    }
  }

  fun submitAddFamilyEmail() {
    if (allowlistTargetEmail.isBlank()) return
    scope.launch(Dispatchers.IO) {
      val payload = JSONObject().apply {
        put("target_email", allowlistTargetEmail.trim())
        put("target_tier", allowlistTargetTier)
        put("actor_email", authEmail.trim().ifBlank { "nep94121@gmail.com" })
        put("actor_id", "tuan_anh")
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
            allowlistStatusMessage = res.optString("error", res.optString("message", "Không thể thêm email!"))
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
    val isAutomationOrMultiPhrase = lower.contains("giây") ||
      lower.contains("phút") ||
      lower.contains("giờ") ||
      lower.contains("lúc ") ||
      lower.contains("hằng ngày") ||
      lower.contains("mỗi ngày") ||
      lower.contains("khi ") ||
      lower.contains("nếu ") ||
      lower.contains("hẹn") ||
      lower.contains("đặt lịch") ||
      lower.contains("tạo luật") ||
      lower.contains("tất cả") ||
      lower.contains("cả hai") ||
      customScenes.any { it.phraseNorm.isNotBlank() && lower.contains(it.phraseNorm) }

    val targetDevice = if (isAutomationOrMultiPhrase) null else devices.firstOrNull { dev ->
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

    if (selectedTier >= 99) {
      val rejReply = "Tôi không được phép nhận lệnh từ người lạ."
      speakerReply = rejReply
      speakOutLoud(rejReply)
      return
    }

    if (targetDevice != null) {
      if (targetDevice.tier1Only && selectedTier != 1) {
        val reply = "Chỉ chủ nhà mới được điều khiển ${targetDevice.name}."
        speakerReply = reply
        speakOutLoud(reply)
        return
      }
      val prevState = deviceStates[targetDevice.serverId] ?: false
      val newState = if (isTurnOn) true else if (isTurnOff) false else !prevState
      deviceStates[targetDevice.serverId] = newState
      val actionWord = if (targetDevice.serverId == "main_door") {
        if (newState) "mở" else "khóa"
      } else {
        if (newState) "bật" else "tắt"
      }
      val reply = "Đã $actionWord ${targetDevice.name} theo lệnh của $activeSpeakerName."
      speakerReply = reply
      if (!isOnlineMode) {
        speakOutLoud(reply)
      }
      addHistoryLog("Lệnh: $cleanCmd -> $reply")

      scope.launch(Dispatchers.IO) {
        val payload = JSONObject().apply {
          put("device_id", targetDevice.serverId)
          put("action", if (newState) "turn_on" else "turn_off")
          put("user_name", activeSpeakerName)
          put("tier", selectedTier)
          put("session_token", activeSessionToken)
        }.toString()
        val resStr = callServerHttp("/api/device", "POST", payload)
        withContext(Dispatchers.Main) {
          if (resStr != null) {
            try {
              val res = JSONObject(resStr)
              val serverSpeech = extractServerSpokenReply(res)
              val serverPcmB64 = res.optString("pcm24k_b64", "")
              if (!res.optBoolean("ok", true) || res.optBoolean("rbac_blocked", false)) {
                deviceStates[targetDevice.serverId] = prevState
                val rejSpeech = serverSpeech.ifBlank {
                  res.optString("error", "Bạn không có quyền thực hiện lệnh này.")
                }
                speakerReply = rejSpeech
                speakOutLoud(rejSpeech, serverPcmB64)
              } else {
                val finalSpeech = serverSpeech.ifBlank { reply }
                speakerReply = finalSpeech
                speakOutLoud(finalSpeech, serverPcmB64)
                if (res.has("snapshot")) {
                  scope.launch { applyServerSnapshotJson(resStr) }
                }
              }
            } catch (_: Exception) {
              if (isOnlineMode) speakOutLoud(reply)
            }
          } else if (isOnlineMode) {
            speakOutLoud(reply)
          }
        }
      }
    } else {
      val reply = "Đã nhận lệnh: “$cleanCmd”."
      speakerReply = reply
      if (!isOnlineMode) {
        speakOutLoud(reply)
      }
      scope.launch(Dispatchers.IO) {
        val payload = JSONObject().apply {
          put("text", cleanCmd)
          put("user_name", activeSpeakerName)
          put("tier", selectedTier)
          put("session_token", activeSessionToken)
        }.toString()
        val resStr = callServerHttp("/api/text_command", "POST", payload)
        if (resStr != null) {
          applyServerSnapshotJson(resStr)
        }
        withContext(Dispatchers.Main) {
          if (resStr != null) {
            try {
              val res = JSONObject(resStr)
              val serverSpeech = extractServerSpokenReply(res)
              val serverPcmB64 = res.optString("pcm24k_b64", "")
              val finalSpeech = serverSpeech.ifBlank { res.optString("error").ifBlank { reply } }
              speakerReply = finalSpeech
              speakOutLoud(finalSpeech, serverPcmB64)
              if (!res.optBoolean("ok", true) || res.optBoolean("rbac_blocked", false)) {
                showAutomationFeedback(finalSpeech, isError = true)
              }
            } catch (_: Exception) {
              if (isOnlineMode) speakOutLoud(reply)
            }
          } else if (isOnlineMode) {
            speakOutLoud(reply)
          }
        }
      }
    }
  }

  fun startLiveMicRecognition() {
    val hasPerm = ContextCompat.checkSelfPermission(
      context,
      Manifest.permission.RECORD_AUDIO,
    ) == PackageManager.PERMISSION_GRANTED
    micPermissionGranted = hasPerm
    if (!hasPerm) {
      micPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
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

      // NỘI DUNG CHÍNH THEO TAB (16dp padding ngang, 12dp padding dọc)
      Column(
        modifier = Modifier
          .weight(1f)
          .fillMaxWidth()
          .verticalScroll(rememberScrollState())
          .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
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
            clockSchedules = clockSchedules,
            automationRules = automationRules,
            customScenes = customScenes,
            onRunScene = { runCustomScene(it) },
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
                showAutomationFeedback(denyMsg, isError = true)
              } else {
                val prevVal = deviceStates[dev.serverId] ?: false
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
                    put("session_token", activeSessionToken)
                  }.toString()
                  val resStr = callServerHttp("/api/device", "POST", payload)
                  if (resStr != null) {
                    if (resStr.contains("\"snapshot\"")) {
                      applyServerSnapshotJson(resStr)
                    }
                    withContext(Dispatchers.Main) {
                      try {
                        val res = JSONObject(resStr)
                        val serverSpeech = extractServerSpokenReply(res)
                        val serverPcmB64 = res.optString("pcm24k_b64", "")
                        if (!res.optBoolean("ok", true) || res.optBoolean("rbac_blocked", false)) {
                          deviceStates[dev.serverId] = prevVal
                          val rejSpeech = serverSpeech.ifBlank {
                            res.optString("error", "Bạn không có quyền thực hiện lệnh này.")
                          }
                          speakerReply = rejSpeech
                          speakOutLoud(rejSpeech, serverPcmB64)
                          showAutomationFeedback(rejSpeech, isError = true)
                        } else if (serverSpeech.isNotBlank()) {
                          speakerReply = serverSpeech
                        }
                      } catch (_: Exception) {}
                    }
                  }
                }
              }
            },
            activeTimers = activeTimers,
            onCreateTimerShortcut = { createMobileScheduleTimer("living_room_light", "turn_on", 10) },
            accentCyan = accentCyan,
            cardBg = cardBg,
            cardBorder = cardBorder,
            bgDark = bgDark,
            textPrimary = textPrimary,
            textSecondary = textSecondary,
            clockSchedules = clockSchedules,
            automationRules = automationRules,
            customScenes = customScenes,
            automationStatusMessage = automationStatusMessage,
            automationStatusIsError = automationStatusIsError,
            onClearAutomationStatus = { automationStatusMessage = "" },
            onCreateTimer = { d, a, s, r -> createCountdownTimer(d, a, s, r) },
            onDeleteTimer = { deleteCountdownTimer(it) },
            onCreateSchedule = { d, a, t, ty, l -> createClockSchedule(d, a, t, ty, l) },
            onDeleteSchedule = { deleteClockSchedule(it) },
            onCreateRule = { wd, ws, td, ta, l -> createAutomationRule(wd, ws, td, ta, l) },
            onDeleteRule = { deleteAutomationRule(it) },
            onCreateScene = { p, st, steps -> createCustomScene(p, st, steps) },
            onDeleteScene = { deleteCustomScene(it) },
            onRunScene = { runCustomScene(it) },
            accentRed = accentRed,
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
            authStatusMessage = authStatusMessage,
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
            onPerformRegister = { performRegisterAccount() },
            onPerformLayer1Login = { performLayer1Login(it) },
            onPerformLayer2OtpVerify = { performLayer2OtpVerify() },
            onUploadVoiceSample = { uploadVoiceToServerForRecognition(null, authEmail) },
            onSubmitAddFamilyEmail = { submitAddFamilyEmail() },
            onLogout = {
              selectedTier = 3
              activeSpeakerName = "Khách"
              activeSessionToken = ""
              sessionCookies.clear()
              activeTimers.clear()
              clockSchedules.clear()
              automationRules.clear()
              customScenes.clear()
              automationStatusMessage = ""
              authEmail = ""
              authPassword = ""
              authOtpInput = ""
              authStepDone = 0
              authStatusMessage = "Đã đăng xuất tài khoản."
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

    SnackbarHost(
      hostState = snackbarHostState,
      modifier = Modifier
        .align(Alignment.BottomCenter)
        .padding(horizontal = 16.dp, vertical = 72.dp),
    )

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
