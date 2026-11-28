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
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.AutomaticGainControl
import android.media.audiofx.NoiseSuppressor
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

private const val ANDROID_ECHO_TAIL_HOLD_MS = 400L
@Volatile
private var androidAiPlaybackUntilMs: Long = 0L

private fun captureMicPcmAndPitch(durationMs: Int = 1100): CapturedVoiceSample {
  return try {
    val nowMs = System.currentTimeMillis()
    if (nowMs < androidAiPlaybackUntilMs + ANDROID_ECHO_TAIL_HOLD_MS) {
      return CapturedVoiceSample(126.0, "")
    }
    val sampleRate = 16000
    val minBuf = AudioRecord.getMinBufferSize(
      sampleRate,
      AudioFormat.CHANNEL_IN_MONO,
      AudioFormat.ENCODING_PCM_16BIT,
    )
    if (minBuf <= 0) return CapturedVoiceSample(126.0, "")
    val recorder = AudioRecord(
      MediaRecorder.AudioSource.VOICE_COMMUNICATION,
      sampleRate,
      AudioFormat.CHANNEL_IN_MONO,
      AudioFormat.ENCODING_PCM_16BIT,
      minBuf * 2,
    )
    if (recorder.state != AudioRecord.STATE_INITIALIZED) return CapturedVoiceSample(126.0, "")
    var aec: AcousticEchoCanceler? = null
    var ns: NoiseSuppressor? = null
    var agc: AutomaticGainControl? = null
    try {
      val sessionId = recorder.audioSessionId
      if (AcousticEchoCanceler.isAvailable()) {
        aec = AcousticEchoCanceler.create(sessionId)?.apply { enabled = true }
      }
      if (NoiseSuppressor.isAvailable()) {
        ns = NoiseSuppressor.create(sessionId)?.apply { enabled = true }
      }
      if (AutomaticGainControl.isAvailable()) {
        agc = AutomaticGainControl.create(sessionId)?.apply { enabled = false }
      }
    } catch (_: Exception) {}
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
    try { aec?.release() } catch (_: Exception) {}
    try { ns?.release() } catch (_: Exception) {}
    try { agc?.release() } catch (_: Exception) {}
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
  var boardOnline by remember { mutableStateOf(true) }
  var boardStatusVi by remember { mutableStateOf("Đang kết nối") }
  var boardLastSeenVi by remember { mutableStateOf("") }
  var boardOfflineResyncCount by remember { mutableIntStateOf(0) }
  val deviceBoardOnline = remember { mutableStateMapOf<String, Boolean>() }
  val deviceLastSeenVi = remember { mutableStateMapOf<String, String>() }
  val offlinePrefs = remember { context.getSharedPreferences("smarthome_prefs", Context.MODE_PRIVATE) }
  var boardLanHost by remember {
    mutableStateOf(
      offlinePrefs.getString("board_lan_host", "smarthome-esp8266.local")
        ?.trim()
        ?.ifBlank { "smarthome-esp8266.local" }
        ?: "smarthome-esp8266.local"
    )
  }

  var micPermissionGranted by remember {
    mutableStateOf(
      ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) ==
        PackageManager.PERMISSION_GRANTED
    )
  }
  var isListeningMic by remember { mutableStateOf(false) }
  var isUploadingVoiceToServer by remember { mutableStateOf(false) }
  var ttsEnabled by remember { mutableStateOf(true) }

  var selectedTier by remember { mutableIntStateOf(0) }
  var activeSpeakerName by remember { mutableStateOf("Chưa đăng nhập") }
  var lastDetectedF0 by remember { mutableDoubleStateOf(126.0) }
  var lastCosineScore by remember { mutableDoubleStateOf(0.92) }

  var authEmail by remember { mutableStateOf("") }
  var authPassword by remember { mutableStateOf("") }
  var authOtpInput by remember { mutableStateOf("") }
  var authStepDone by remember { mutableIntStateOf(0) }
  var authStatusMessage by remember {
    mutableStateOf("Nhập email và mật khẩu để đăng nhập hoặc quét mã QR mời khách.")
  }
  var authStatusColor by remember { mutableStateOf(accentCyan) }

  var voiceInput by remember { mutableStateOf("") }
  var lastSpokenText by remember { mutableStateOf("") }
  var hasVoiceCommandResult by remember { mutableStateOf(false) }
  var micErrorState by remember { mutableStateOf(false) }
  var selectedRoomFilter by remember { mutableStateOf("Tất cả") }
  var accountSubScreen by remember { mutableStateOf("menu") }
  var showTechLogs by remember { mutableStateOf(false) }
  var newMemberName by remember { mutableStateOf("Thành viên Minh") }
  var newMemberTier by remember { mutableIntStateOf(2) }

  var allowlistTargetEmail by remember { mutableStateOf("") }
  var allowlistTargetTier by remember { mutableIntStateOf(2) }
  var allowlistStatusMessage by remember { mutableStateOf("") }
  var allowlistStatusColor by remember { mutableStateOf(accentCyan) }
  var guestQrDuration by remember { mutableStateOf("1d") }
  var guestQrCountdown by remember { mutableIntStateOf(10) }
  var guestPinInput by remember { mutableStateOf("") }
  var guestPinConfirmInput by remember { mutableStateOf("") }
  var guestNeedsPinSetup by remember { mutableStateOf(false) }
  var guestInviteToken by remember { mutableStateOf("") }
  var guestInviteUrl by remember { mutableStateOf("") }
  var guestInviteStatus by remember { mutableStateOf("") }
  var guestInviteIsError by remember { mutableStateOf(false) }

  var speakerReply by remember { mutableStateOf("Chưa có lệnh") }
  val voiceConversation = remember { mutableStateListOf<Pair<String, String>>() }
  var metricBadge by remember { mutableStateOf("Chưa đăng nhập") }
  var lastStatusColor by remember { mutableStateOf(accentGreen) }

  var temperature by remember { mutableDoubleStateOf(28.5) }
  var humidity by remember { mutableIntStateOf(65) }
  var soilMoisture by remember { mutableIntStateOf(62) }
  var soundDetected by remember { mutableStateOf(false) }
  var soundEventCount by remember { mutableIntStateOf(0) }

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
      "main_door" to false,
      "living_room_light" to false,
      "bedroom_light" to false,
      "garden_pump" to false,
      "alarm_siren" to false,
      "speaker_amp" to false,
    )
  }
  val allowedDeviceIds = remember { mutableStateListOf<String>() }

  val devices = remember {
    listOf(
      HardwareDevice("living_room_light", "Đèn phòng khách", "Phòng khách", "lamp", "Đang bật", "Đang tắt"),
      HardwareDevice("bedroom_light", "Đèn phòng ngủ", "Phòng ngủ", "lamp", "Đang bật", "Đang tắt"),
      HardwareDevice("speaker_amp", "Nguồn mạch loa PAM8403", "Phòng khách", "speaker", "Đang bật", "Đang tắt"),
      HardwareDevice("main_door", "Cửa chính", "Lối vào", "door", "Đang mở", "Đang khóa"),
      HardwareDevice("alarm_siren", "Còi báo động", "Lối vào", "bell", "Đang bật", "Đang tắt"),
      HardwareDevice("garden_pump", "Máy bơm tưới cây", "Sân vườn", "drop", "Đang bật", "Đang tắt"),
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
      t.contains("chỉ chủ nhà") -> "tier2_permission_denied.mp3"
      t.contains("tiếng ồn") -> "vad_noise_blocked.mp3"
      t.contains("khẩu lệnh tiếng việt") -> "vad_blocked.mp3"
      t.contains("cửa") && (t.contains("mở") || t.contains("bật")) -> "open_main_door.mp3"
      t.contains("cửa") && (t.contains("đóng") || t.contains("tắt") || t.contains("khóa")) -> "close_main_door.mp3"
      t.contains("đèn phòng khách") && t.contains("tắt") -> "turn_off_living_room_light.mp3"
      t.contains("đèn phòng khách") -> "turn_on_living_room_light.mp3"
      t.contains("đèn phòng ngủ") && t.contains("tắt") -> "turn_off_bedroom_light.mp3"
      t.contains("đèn phòng ngủ") -> "turn_on_bedroom_light.mp3"
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
        val durationMs = (pcmBytes.size.toLong() * 1000L / 48000L).coerceIn(300L, 12000L)
        androidAiPlaybackUntilMs = maxOf(androidAiPlaybackUntilMs, System.currentTimeMillis() + durationMs)
        track.play()
        Log.i("SmartHomeTTS", "AudioTrack played pcm24k_b64 (${pcmBytes.size} bytes): $text")
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
  val isAuthenticated = activeSessionToken.isNotBlank()
  val sessionCookies = remember { ConcurrentHashMap<String, String>() }

  val visibleDevices = remember(isAuthenticated, selectedTier, allowedDeviceIds.toList()) {
    if (!isAuthenticated) {
      emptyList()
    } else {
      val tierAllowed = when (selectedTier) {
        1 -> setOf("living_room_light", "bedroom_light", "speaker_amp", "main_door", "alarm_siren", "garden_pump")
        2 -> setOf("living_room_light", "bedroom_light", "garden_pump", "speaker_amp")
        3 -> setOf("living_room_light", "bedroom_light")
        else -> emptySet()
      }
      if (allowedDeviceIds.isNotEmpty()) {
        devices.filter { it.serverId in allowedDeviceIds && it.serverId in tierAllowed }
      } else {
        devices.filter { it.serverId in tierAllowed }
      }
    }
  }

  val allowLocalDebugFallback = true

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
        listOf("http://127.0.0.1:8088", primaryBase, fallbackBase, "http://10.0.2.2:8088")
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
            conn.readTimeout = 15000
          } else {
            conn.connectTimeout = 900
            conn.readTimeout = 15000
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
          if (code in 400..499 || code == 503) {
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
        if (root.has("authenticated") && !root.optBoolean("authenticated", true)) {
          return@withContext
        }
        val curTier = root.optInt("current_tier", 0)
        if (curTier in 1..3 && activeSessionToken.isNotBlank()) {
          if (selectedTier !in 1..3 || curTier >= selectedTier) {
            selectedTier = curTier
          }
        }
        val boardHealthObj = root.optJSONObject("board_health")
        if (boardHealthObj != null) {
          val prevBoardOnline = boardOnline
          val nextBoardOnline = boardHealthObj.optBoolean("online", true)
          boardOnline = nextBoardOnline
          boardStatusVi = boardHealthObj.optString("status_vi").ifBlank {
            if (nextBoardOnline) "Đang kết nối" else "Mất kết nối"
          }
          val lsVi = boardHealthObj.optString("last_seen_vi", "").trim()
          if (lsVi.isNotEmpty()) {
            boardLastSeenVi = lsVi
          }
          val resyncCnt = boardHealthObj.optInt("offline_resync_count", boardOfflineResyncCount)
          if ((!prevBoardOnline && nextBoardOnline) || resyncCnt > boardOfflineResyncCount) {
            boardOfflineResyncCount = resyncCnt
            if (automationStatusIsError && automationStatusMessage.contains("mất kết nối", ignoreCase = true)) {
              automationStatusMessage = ""
              automationStatusIsError = false
            }
            addHistoryLog("Mạch đã kết nối lại và tự động đồng bộ trạng thái thực tế.")
          }
        }
        val devArr = root.optJSONArray("devices")
        if (devArr != null && activeSessionToken.isNotBlank()) {
          val seenIds = mutableSetOf<String>()
          for (i in 0 until devArr.length()) {
            val obj = devArr.optJSONObject(i) ?: continue
            val id = obj.optString("id")
            val st = obj.optString("state")
            if (id.isNotBlank() && deviceStates.containsKey(id)) {
              seenIds.add(id)
              deviceStates[id] = (st == "ON" || st == "OPEN")
              if (obj.has("board_online")) {
                deviceBoardOnline[id] = obj.optBoolean("board_online", boardOnline)
              } else {
                deviceBoardOnline[id] = boardOnline
              }
              val devLs = obj.optString("last_seen_vi", "").trim()
              if (devLs.isNotEmpty()) {
                deviceLastSeenVi[id] = devLs
              }
            }
          }
          if (seenIds.isNotEmpty()) {
            allowedDeviceIds.clear()
            allowedDeviceIds.addAll(seenIds)
            for (k in deviceStates.keys.toList()) {
              if (k !in seenIds) {
                deviceStates[k] = false
              }
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
        val soundObj = mqttObj?.optJSONObject("sound_telemetry")
        if (soundObj != null) {
          soundDetected = soundObj.optBoolean("sound_detected", soundDetected)
          soundEventCount = soundObj.optInt("event_count", soundEventCount)
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

      var finalResStr = resStr
      var finalRes = res
      val needsConfirm = finalRes.optBoolean("requires_confirmation", false)
      val pendingId = finalRes.optString("pending_id").ifBlank { finalRes.optString("confirm_token") }
      if (needsConfirm && pendingId.isNotBlank()) {
        val confirmPayload = JSONObject().apply {
          put("pending_id", pendingId)
          put("confirm_token", pendingId)
          put("confirmed", true)
          if (activeSessionToken.isNotBlank()) put("session_token", activeSessionToken)
        }.toString()
        val confStr = callServerHttp("/api/automation/confirm", "POST", confirmPayload)
        if (confStr != null) {
          val confJson = try { JSONObject(confStr) } catch (_: Exception) { null }
          if (confJson != null) {
            finalResStr = confStr
            finalRes = confJson
            if (!finalRes.optBoolean("ok", false) || finalRes.optBoolean("rbac_blocked", false)) {
              val cErr = finalRes.optString("error")
                .ifBlank { finalRes.optString("message") }
                .ifBlank { extractServerSpokenReply(finalRes) }
                .ifBlank { defaultErrorMessage }
              withContext(Dispatchers.Main) {
                showAutomationFeedback(cErr, isError = true)
              }
              return@launch
            }
          }
        }
      }

      if (finalRes.has("snapshot") || finalRes.has("timers") || finalRes.has("schedules") || finalRes.has("automation_rules") || finalRes.has("scenes") || finalRes.has("custom_commands")) {
        applyServerSnapshotJson(finalResStr)
      } else {
        syncServerState()
      }
      val replyMsg = extractServerSpokenReply(finalRes)
        .ifBlank { finalRes.optString("message") }
        .ifBlank { defaultSuccessMessage }
      val pcmB64 = finalRes.optString("pcm24k_b64", "")
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
    if (activeSessionToken.isBlank()) {
      serverSynced = false
      return@LaunchedEffect
    }
    syncServerState()
    val sseBases = if (allowLocalDebugFallback) {
      listOf(
        "http://127.0.0.1:8088",
        "https://laptop-6i654f8c.tail3020d6.ts.net",
        "https://do-an-tot-nghiep-smart-home-voice-a.vercel.app",
      )
    } else {
      listOf(
        "https://laptop-6i654f8c.tail3020d6.ts.net",
        "https://do-an-tot-nghiep-smart-home-voice-a.vercel.app",
      )
    }
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
      val resStr = callServerHttp("/api/auth3/layer1_login", "POST", payload)
      withContext(Dispatchers.Main) {
        if (resStr != null) {
          val res = try { JSONObject(resStr) } catch (_: Exception) { JSONObject() }
          if (res.optBoolean("ok")) {
            authStepDone = maxOf(authStepDone, 1)
            activeSpeakerName = res.optJSONObject("account")?.optString("display_name")
              ?.ifBlank { displayName } ?: displayName
            val returnedToken = res.optString("session_token", "")
              .ifBlank { sessionCookies["sh_session_token"] ?: sessionCookies["session_token"] ?: "" }
            val otpRequired = res.optBoolean("otp_required", false)
            if (returnedToken.isNotBlank()) {
              activeSessionToken = returnedToken
              val serverTier = res.optInt("tier", 0).let {
                if (it in 1..3) it else res.optJSONObject("account")?.optInt("tier", 0) ?: 0
              }
              if (serverTier in 1..3) {
                selectedTier = serverTier
              }
              authStatusColor = accentGreen
              authStatusMessage = "Đăng nhập thành công: $cleanEmail"
              addHistoryLog("Đăng nhập thành công: $cleanEmail")
              scope.launch { syncServerState() }
            } else if (otpRequired) {
              authStatusColor = accentAmber
              authStatusMessage = res.optString("message").ifBlank {
                "Đã xác thực mật khẩu. Vui lòng nhập mã OTP 6 số gửi qua Gmail."
              }
              addHistoryLog("Yêu cầu OTP Lớp 2 cho: $cleanEmail")
            } else {
              authStatusColor = accentRed
              authStatusMessage = res.optString("error", "Chưa nhận được phiên đăng nhập từ máy chủ.")
            }
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
            authStatusMessage = "Xác thực OTP thành công! Đã đăng nhập."
            addHistoryLog("Xác thực OTP thành công.")
            scope.launch { syncServerState() }
          } else {
            authStatusColor = accentRed
            authStatusMessage = res.optString("error", res.optString("message", "Mã OTP không đúng hoặc hết hạn!"))
          }
        } else {
          authStatusColor = accentRed
          authStatusMessage = "Không thể kết nối máy chủ để xác thực OTP."
        }
      }
    }
  }

  fun extractInviteToken(rawCode: String): String {
    val trimmed = rawCode.trim()
    if (trimmed.isBlank()) return ""
    if (trimmed.startsWith("http://", ignoreCase = true) || trimmed.startsWith("https://", ignoreCase = true)) {
      try {
        val uri = Uri.parse(trimmed)
        val qToken = uri.getQueryParameter("token") ?: uri.getQueryParameter("invite")
        if (!qToken.isNullOrBlank()) return qToken.trim()
        val lastSeg = uri.lastPathSegment
        if (!lastSeg.isNullOrBlank() && lastSeg != "guest" && lastSeg != "guest_enroll") {
          return lastSeg.trim()
        }
      } catch (_: Exception) {}
    }
    return trimmed
  }

  fun redeemGuestQrCode(rawCode: String) {
    val token = extractInviteToken(rawCode)
    if (token.isBlank()) {
      authStatusColor = accentRed
      authStatusMessage = "Mã QR mời khách không hợp lệ."
      showAutomationFeedback(authStatusMessage, isError = true)
      return
    }
    authStatusColor = accentCyan
    authStatusMessage = "Đang xác thực mã mời QR với máy chủ..."
    scope.launch(Dispatchers.IO) {
      val payload = JSONObject().apply {
        put("token", token)
      }.toString()
      val resStr = callServerHttp("/api/guest/redeem", "POST", payload)
      withContext(Dispatchers.Main) {
        if (resStr == null) {
          authStatusColor = accentRed
          authStatusMessage = "Không thể kết nối máy chủ để đổi mã QR mời."
          showAutomationFeedback(authStatusMessage, isError = true)
          return@withContext
        }
        val res = try { JSONObject(resStr) } catch (_: Exception) { JSONObject() }
        if (res.optBoolean("ok")) {
          val returnedToken = res.optString("session_token", "")
            .ifBlank { sessionCookies["sh_session_token"] ?: sessionCookies["session_token"] ?: "" }
          val tierVal = res.optInt("tier", 3).coerceIn(1, 3)
          if (returnedToken.isNotBlank()) {
            activeSessionToken = returnedToken
          }
          selectedTier = tierVal
          activeSpeakerName = res.optString("display_name").ifBlank {
            if (tierVal == 2) "Gia đình (QR)" else "Khách mời (QR)"
          }
          authStepDone = 2
          authStatusColor = accentGreen
          authStatusMessage = "Đã kích hoạt phiên truy cập bằng mã QR (Cấp $tierVal)."
          addHistoryLog("Đổi mã QR mời thành công (Cấp $tierVal)")
          accountSubScreen = "menu"
          showAutomationFeedback(authStatusMessage, isError = false)
          scope.launch { syncServerState() }
        } else {
          val errMsg = res.optString("error", res.optString("message", "Mã mời không hợp lệ hoặc đã hết hạn."))
          authStatusColor = accentRed
          authStatusMessage = errMsg
          addHistoryLog("Đổi mã QR thất bại: $errMsg")
          showAutomationFeedback(errMsg, isError = true)
        }
      }
    }
  }

  suspend fun sendForgotPasswordOtp(email: String): Pair<Boolean, String> {
    val cleanEmail = email.trim()
    val payload = JSONObject().apply {
      put("email", cleanEmail)
      put("send_gmail", !cleanEmail.endsWith("@example.com"))
      put("source", "Android_ForgotPassword")
    }.toString()
    val resStr = callServerHttp("/api/auth3/forgot_password_send_otp", "POST", payload)
      ?: return false to "Không thể kết nối máy chủ để gửi mã OTP."
    val res = try { JSONObject(resStr) } catch (_: Exception) { JSONObject() }
    val ok = res.optBoolean("ok", false)
    val msg = if (ok) {
      res.optString("message").ifBlank { "Đã gửi mã OTP 6 số về Gmail." }
    } else {
      res.optString("error").ifBlank { res.optString("message", "Không thể gửi mã OTP.") }
    }
    return ok to msg
  }

  suspend fun verifyForgotPasswordOtp(email: String, otp: String): Pair<Boolean, String> {
    val payload = JSONObject().apply {
      put("email", email.trim())
      put("otp", otp.trim())
      put("purpose", "forgot_password")
      put("source", "Android_ForgotPassword")
    }.toString()
    val resStr = callServerHttp("/api/auth3/layer2_verify_otp", "POST", payload)
      ?: return false to "Không thể kết nối máy chủ để xác thực mã OTP."
    val res = try { JSONObject(resStr) } catch (_: Exception) { JSONObject() }
    val ok = res.optBoolean("ok", false)
    val msg = if (ok) {
      res.optString("message").ifBlank { "Xác thực mã OTP thành công." }
    } else {
      res.optString("error").ifBlank { res.optString("message", "Mã OTP không đúng hoặc đã hết hạn.") }
    }
    return ok to msg
  }

  suspend fun confirmForgotPasswordReset(
    email: String,
    otp: String,
    newPassword: String,
    confirmPassword: String,
  ): Pair<Boolean, String> {
    val payload = JSONObject().apply {
      put("email", email.trim())
      put("otp_code", otp.trim())
      put("new_password", newPassword)
      put("confirm_password", confirmPassword)
      put("source", "Android_ForgotPassword")
    }.toString()
    val resStr = callServerHttp("/api/auth3/forgot_password_reset", "POST", payload)
      ?: return false to "Không thể kết nối máy chủ để đặt lại mật khẩu."
    val res = try { JSONObject(resStr) } catch (_: Exception) { JSONObject() }
    val ok = res.optBoolean("ok", false)
    val msg = if (ok) {
      res.optString("message").ifBlank { "Đặt lại mật khẩu thành công!" }
    } else {
      res.optString("error").ifBlank { res.optString("message", "Không thể đặt lại mật khẩu.") }
    }
    return ok to msg
  }

  fun createGuestInviteFromUi() {
    if (!isAuthenticated || selectedTier != 1) {
      guestInviteIsError = true
      guestInviteStatus = "Chỉ Chủ nhà Cấp 1 mới có quyền tạo lời mời khách."
      return
    }
    if (guestPinInput.length != 4) {
      guestInviteIsError = true
      guestInviteStatus = "Vui lòng nhập mã PIN Chủ nhà gồm 4 chữ số."
      return
    }
    if (guestNeedsPinSetup && guestPinConfirmInput != guestPinInput) {
      guestInviteIsError = true
      guestInviteStatus = "Mã PIN xác nhận lần đầu không khớp."
      return
    }
    guestInviteIsError = false
    guestInviteStatus = "Đang tạo lời mời khách..."
    scope.launch(Dispatchers.IO) {
      val payload = JSONObject().apply {
        put("tier", 3)
        put("duration_code", guestQrDuration)
        put("guest_name", newMemberName.trim().ifBlank { "Khách mời" })
        put("pin", guestPinInput)
        if (guestNeedsPinSetup && guestPinConfirmInput.isNotBlank()) {
          put("pin_confirm", guestPinConfirmInput)
        }
        put("session_token", activeSessionToken)
      }.toString()
      val resStr = callServerHttp("/api/auth3/guest_invites", "POST", payload)
      withContext(Dispatchers.Main) {
        if (resStr == null) {
          guestInviteIsError = true
          guestInviteStatus = "Không thể kết nối máy chủ để tạo lời mời."
          return@withContext
        }
        val res = try { JSONObject(resStr) } catch (_: Exception) { JSONObject() }
        if (res.optBoolean("ok", false)) {
          val tok = res.optString("token", "")
          val url = res.optString("url", "")
          guestNeedsPinSetup = false
          guestPinConfirmInput = ""
          guestInviteToken = tok
          guestInviteUrl = url
          guestInviteIsError = false
          guestInviteStatus = "Đã tạo lời mời khách thành công (${res.optString("duration_label", guestQrDuration)})."
          addHistoryLog("Tạo lời mời khách: ${newMemberName.trim().ifBlank { "Khách mời" }}")
        } else {
          if (res.optBoolean("needs_pin_setup", false)) {
            guestNeedsPinSetup = true
          }
          guestInviteIsError = true
          guestInviteStatus = res.optString("error", res.optString("message", "Không thể tạo lời mời khách."))
        }
      }
    }
  }

  fun submitAddFamilyEmail() {
    if (allowlistTargetEmail.isBlank()) return
    if (!isAuthenticated) {
      allowlistStatusColor = accentRed
      allowlistStatusMessage = "Vui lòng đăng nhập tài khoản Chủ nhà trước."
      return
    }
    scope.launch(Dispatchers.IO) {
      val payload = JSONObject().apply {
        put("target_email", allowlistTargetEmail.trim())
        put("target_tier", allowlistTargetTier)
        if (authEmail.isNotBlank()) {
          put("actor_email", authEmail.trim())
        }
      }.toString()
      val resStr = callServerHttp("/api/auth3/add_family_email", "POST", payload)
      withContext(Dispatchers.Main) {
        if (resStr != null) {
          val res = try { JSONObject(resStr) } catch (_: Exception) { JSONObject() }
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
          allowlistStatusColor = accentRed
          allowlistStatusMessage = "Không thể kết nối máy chủ. Chưa thêm được email thành viên."
        }
      }
    }
  }

  fun isOfflineDoorOpenAttempt(cmdLower: String): Boolean {
    val mentionsDoor = cmdLower.contains("cửa") || cmdLower.contains("cua") || cmdLower.contains("main_door")
    if (!mentionsDoor) return false
    val wantsClose = cmdLower.contains("đóng") ||
      cmdLower.contains("dong") ||
      cmdLower.contains("khóa") ||
      cmdLower.contains("khoa") ||
      cmdLower.contains("tắt") ||
      cmdLower.contains("tat") ||
      cmdLower.contains("close")
    val wantsOpen = cmdLower.contains("mở") ||
      cmdLower.contains("mo ") ||
      cmdLower == "mo" ||
      cmdLower.contains("bật") ||
      cmdLower.contains("bat") ||
      cmdLower.contains("open")
    return wantsOpen && !wantsClose
  }

  fun sendDirectBoardOfflineCommand(cleanCmd: String) {
    val lower = cleanCmd.lowercase(Locale.getDefault())
    val doorOpenAttempt = isOfflineDoorOpenAttempt(lower)
    val doorRefusal = "Đang mất kết nối máy chủ, tuyệt đối không được phép mở cửa chính."
    val cleanHost = boardLanHost
      .trim()
      .removePrefix("http://")
      .removePrefix("https://")
      .trimEnd('/')
      .ifBlank { "smarthome-esp8266.local" }
    val lanUrls = buildList {
      add("http://$cleanHost/offline/cmd")
      if (cleanHost != "192.168.4.1") {
        add("http://192.168.4.1/offline/cmd")
      }
    }
    speakerReply = "Đang gửi lệnh ngoại tuyến tới mạch ($cleanHost)..."
    scope.launch(Dispatchers.IO) {
      val payload = JSONObject().apply {
        put("text", cleanCmd)
      }.toString()
      var responseBody: String? = null
      for (targetUrl in lanUrls) {
        var conn: HttpURLConnection? = null
        try {
          val url = URL(targetUrl)
          conn = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 2500
            readTimeout = 2500
            doOutput = true
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
          }
          OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use {
            it.write(payload)
            it.flush()
          }
          val code = conn.responseCode
          val stream = if (code in 200..299) conn.inputStream else conn.errorStream
          if (stream != null) {
            responseBody = BufferedReader(InputStreamReader(stream, Charsets.UTF_8)).use { it.readText() }
          }
          if (code in 200..299 || code == 400 || code == 403) {
            break
          }
        } catch (_: Exception) {
        } finally {
          try { conn?.disconnect() } catch (_: Exception) {}
        }
      }
      withContext(Dispatchers.Main) {
        if (responseBody.isNullOrBlank()) {
          if (doorOpenAttempt) {
            deviceStates["main_door"] = false
            speakerReply = doorRefusal
            speakOutLoud(doorRefusal)
            showAutomationFeedback(doorRefusal, isError = true)
          } else {
            val errMsg = "Không thể kết nối máy chủ hoặc mạch ESP8266 qua mạng LAN ($cleanHost)."
            speakerReply = errMsg
            speakOutLoud(errMsg)
            showAutomationFeedback(errMsg, isError = true)
          }
          return@withContext
        }
        try {
          val res = JSONObject(responseBody)
          val devicesObj = res.optJSONObject("devices")
          if (devicesObj != null) {
            val keys = devicesObj.keys()
            while (keys.hasNext()) {
              val devKey = keys.next()
              if (deviceStates.containsKey(devKey)) {
                val st = devicesObj.optString(devKey, "OFF").uppercase(Locale.ROOT)
                val isOnState = st == "ON" || st == "OPEN"
                // Addendum A3: Tuyệt đối không mở cửa chính ở chế độ ngoại tuyến
                deviceStates[devKey] = if (devKey == "main_door") false else isOnState
              }
            }
          }
          val ok = res.optBoolean("ok", false)
          val refused = res.optBoolean("refused", !ok)
          val replyVi = res.optString("reply_vi")
            .ifBlank { extractServerSpokenReply(res) }
            .ifBlank {
              if (doorOpenAttempt) doorRefusal
              else if (ok && !refused) "Đã thực hiện lệnh ở chế độ ngoại tuyến."
              else "Lệnh không được hỗ trợ ở chế độ ngoại tuyến."
            }
          speakerReply = replyVi
          speakOutLoud(replyVi)
          addHistoryLog("Ngoại tuyến LAN: $cleanCmd -> $replyVi")
          if (!ok || refused) {
            showAutomationFeedback(replyVi, isError = true)
          }
        } catch (_: Exception) {
          val fallbackErr = if (doorOpenAttempt) doorRefusal else "Phản hồi ngoại tuyến từ mạch không hợp lệ."
          speakerReply = fallbackErr
          speakOutLoud(fallbackErr)
          showAutomationFeedback(fallbackErr, isError = true)
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

    val useDirectLanOffline = !isOnlineMode || !boardOnline || (isAuthenticated && !serverSynced)
    if (useDirectLanOffline) {
      sendDirectBoardOfflineCommand(cleanCmd)
      return
    }

    if (!isAuthenticated || selectedTier <= 0 || selectedTier >= 99) {
      val rejReply = "Vui lòng đăng nhập trước khi điều khiển thiết bị."
      speakerReply = rejReply
      speakOutLoud(rejReply)
      return
    }

    val fallbackReply = "Đã nhận lệnh: “$cleanCmd”."
    speakerReply = "Đang xử lý..."
    addHistoryLog("Lệnh giọng nói: $cleanCmd")
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
            if (res.optBoolean("board_offline", false)) {
              boardOnline = false
              val ls = res.optString("last_seen_vi", "").trim()
              if (ls.isNotEmpty()) boardLastSeenVi = ls
            }
            val finalSpeech = serverSpeech.ifBlank { res.optString("error").ifBlank { fallbackReply } }
            speakerReply = finalSpeech
            voiceConversation.add(0, cleanCmd to finalSpeech)
            if (voiceConversation.size > 12) {
              voiceConversation.removeAt(voiceConversation.lastIndex)
            }
            speakOutLoud(finalSpeech, serverPcmB64)
            if (!res.optBoolean("ok", true) || res.optBoolean("rbac_blocked", false) || res.optBoolean("board_offline", false)) {
              showAutomationFeedback(finalSpeech, isError = true)
            }
          } catch (_: Exception) {
            val errMsg = "Không đọc được phản hồi từ máy chủ."
            speakerReply = errMsg
            showAutomationFeedback(errMsg, isError = true)
          }
        } else {
          serverSynced = false
          sendDirectBoardOfflineCommand(cleanCmd)
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
        putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "vi-VN")
        putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
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
      "auth" -> "Đăng nhập"
      "guest" -> "Mời khách"
      "qr_scanner" -> "Quét mã QR"
      "forgot_otp" -> "Quên mật khẩu"
      "logs" -> "Nhật ký"
      "settings" -> "Cài đặt"
      else -> "Tài khoản"
    }
  }

  val topBarSubtitle = when (currentTab) {
    0 -> if (isAuthenticated) "Theo dõi trạng thái trong nhà" else "Đăng nhập để điều khiển ngôi nhà"
    1 -> if (isAuthenticated) "Điều khiển các thiết bị trong nhà" else "Yêu cầu đăng nhập"
    2 -> "Nói điều bạn muốn làm trong nhà."
    else -> when (accountSubScreen) {
      "auth" -> "Email, mật khẩu và OTP bảo mật"
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
              fontSize = if (showBackInTopBar) 18.sp else 21.sp,
              fontWeight = FontWeight.SemiBold,
              maxLines = 1,
              overflow = TextOverflow.Ellipsis,
              modifier = Modifier.weight(1f, fill = false),
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
                  .background(
                    when {
                      !isAuthenticated -> accentAmber
                      serverSynced && isOnlineMode && boardOnline -> Color(0xFF15803D)
                      else -> accentRed
                    }
                  ),
              )
              Text(
                text = when {
                  !isAuthenticated -> "Chưa đăng nhập"
                  serverSynced && isOnlineMode && boardOnline -> "Đã kết nối"
                  else -> "Mất kết nối"
                },
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
            humidity = humidity,
            soilMoisture = soilMoisture,
            soundDetected = soundDetected,
            soundEventCount = soundEventCount,
            isAuthenticated = isAuthenticated,
            selectedTier = selectedTier,
            visibleDevicesCount = visibleDevices.size,
            visibleDeviceIds = visibleDevices.map { it.serverId }.toSet(),
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
            onNavigateToAuth = { currentTab = 3; accountSubScreen = "auth" },
            onNavigateToQr = { currentTab = 3; accountSubScreen = "qr_scanner" },
            clockSchedules = clockSchedules,
            automationRules = automationRules,
            customScenes = customScenes,
            onRunScene = { runCustomScene(it) },
            boardOnline = boardOnline && serverSynced && isOnlineMode,
            boardLastSeenVi = boardLastSeenVi,
          )
          1 -> DevicesScreenTab(
            devices = visibleDevices,
            deviceStates = deviceStates,
            selectedRoomFilter = selectedRoomFilter,
            onSelectRoomFilter = { selectedRoomFilter = it },
            onToggleDevice = { dev, newValue ->
              val devOnlineNow = boardOnline && (deviceBoardOnline[dev.serverId] != false) && serverSynced && isOnlineMode
              val devLastSeen = deviceLastSeenVi[dev.serverId].orEmpty().ifBlank { boardLastSeenVi }
              if (!isAuthenticated) {
                showAutomationFeedback("Vui lòng đăng nhập để điều khiển thiết bị.", isError = true)
              } else if (!devOnlineNow) {
                val offMsg = if (devLastSeen.isNotBlank()) {
                  "${dev.name} hiện đang mất kết nối (lần cuối: $devLastSeen), chưa thể điều khiển qua máy chủ."
                } else {
                  "${dev.name} hiện đang mất kết nối, chưa thể điều khiển qua máy chủ."
                }
                showAutomationFeedback(offMsg, isError = true)
              } else if (dev.tier1Only && selectedTier != 1) {
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
                    syncServerState()
                    withContext(Dispatchers.Main) {
                      try {
                        val res = JSONObject(resStr)
                        val serverSpeech = extractServerSpokenReply(res)
                        val serverPcmB64 = res.optString("pcm24k_b64", "")
                        val isBoardOfflineResp = res.optBoolean("board_offline", false)
                        if (isBoardOfflineResp) {
                          boardOnline = false
                          val ls = res.optString("last_seen_vi", "").trim()
                          if (ls.isNotEmpty()) boardLastSeenVi = ls
                        }
                        if (!res.optBoolean("ok", true) || res.optBoolean("rbac_blocked", false) || isBoardOfflineResp) {
                          deviceStates[dev.serverId] = prevVal
                          val rejSpeech = serverSpeech.ifBlank {
                            res.optString("error", "Không thể điều khiển thiết bị lúc này.")
                          }
                          speakerReply = rejSpeech
                          speakOutLoud(rejSpeech, serverPcmB64)
                          showAutomationFeedback(rejSpeech, isError = true)
                        } else if (serverSpeech.isNotBlank()) {
                          speakerReply = serverSpeech
                        }
                      } catch (_: Exception) {
                        deviceStates[dev.serverId] = prevVal
                        showAutomationFeedback("Phản hồi máy chủ không hợp lệ.", isError = true)
                      }
                    }
                  } else {
                    withContext(Dispatchers.Main) {
                      deviceStates[dev.serverId] = prevVal
                      serverSynced = false
                      showAutomationFeedback("Không thể kết nối máy chủ.", isError = true)
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
            isAuthenticated = isAuthenticated,
            selectedTier = selectedTier,
            onNavigateToAuth = { currentTab = 3; accountSubScreen = "auth" },
            onNavigateToQr = { currentTab = 3; accountSubScreen = "qr_scanner" },
            boardOnline = boardOnline && serverSynced && isOnlineMode,
            boardLastSeenVi = boardLastSeenVi,
            deviceBoardOnline = deviceBoardOnline,
            deviceLastSeenVi = deviceLastSeenVi,
            onDeviceOfflineTap = { dev ->
              val ls = deviceLastSeenVi[dev.serverId].orEmpty().ifBlank { boardLastSeenVi }
              val msg = if (ls.isNotBlank()) {
                "${dev.name} hiện đang mất kết nối (lần cuối: $ls), chưa thể điều khiển qua máy chủ."
              } else {
                "${dev.name} hiện đang mất kết nối, chưa thể điều khiển qua máy chủ."
              }
              showAutomationFeedback(msg, isError = true)
            },
          )
          2 -> VoiceScreenTab(
            selectedTier = selectedTier,
            hasVoiceCommandResult = hasVoiceCommandResult,
            lastSpokenText = lastSpokenText,
            speakerReply = speakerReply,
            voiceConversation = voiceConversation,
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
            isOfflineLanMode = !isOnlineMode || !boardOnline || (isAuthenticated && !serverSynced),
            boardLanHost = boardLanHost,
            onBoardLanHostChange = { newHost ->
              boardLanHost = newHost
              offlinePrefs.edit().putString("board_lan_host", newHost.trim()).apply()
            },
          )
          else -> AccountScreenTab(
            accountSubScreen = accountSubScreen,
            onNavigateSubScreen = { accountSubScreen = it },
            isAuthenticated = isAuthenticated,
            selectedTier = selectedTier,
            onSelectTier = { tier, name -> selectedTier = tier; activeSpeakerName = name },
            authEmail = authEmail,
            onAuthEmailChange = { authEmail = it },
            authPassword = authPassword,
            onAuthPasswordChange = { authPassword = it },
            authOtpInput = authOtpInput,
            onAuthOtpInputChange = { authOtpInput = it },
            authStepDone = authStepDone,
            authStatusMessage = authStatusMessage,
            authStatusColor = authStatusColor,
            allowlistTargetEmail = allowlistTargetEmail,
            onAllowlistTargetEmailChange = { allowlistTargetEmail = it },
            allowlistStatusMessage = allowlistStatusMessage,
            allowlistStatusColor = allowlistStatusColor,
            newMemberName = newMemberName,
            onNewMemberNameChange = { newMemberName = it },
            guestQrDuration = guestQrDuration,
            onGuestQrDurationChange = { guestQrDuration = it },
            guestPinInput = guestPinInput,
            onGuestPinInputChange = { guestPinInput = it },
            guestPinConfirmInput = guestPinConfirmInput,
            onGuestPinConfirmInputChange = { guestPinConfirmInput = it },
            guestNeedsPinSetup = guestNeedsPinSetup,
            guestInviteToken = guestInviteToken,
            guestInviteUrl = guestInviteUrl,
            guestInviteStatus = guestInviteStatus,
            guestInviteIsError = guestInviteIsError,
            onCreateGuestInvite = { createGuestInviteFromUi() },
            onSendResetOtp = { email -> sendForgotPasswordOtp(email) },
            onVerifyResetOtp = { email, otp -> verifyForgotPasswordOtp(email, otp) },
            onConfirmResetPassword = { email, otp, newPwd, confPwd ->
              confirmForgotPasswordReset(email, otp, newPwd, confPwd)
            },
            historyLogs = historyLogs,
            showTechLogs = showTechLogs,
            onToggleTechLogs = { showTechLogs = !showTechLogs },
            lastDetectedF0 = lastDetectedF0,
            lastCosineScore = lastCosineScore,
            lastSyncTime = lastSyncTime,
            onPerformRegister = { performRegisterAccount() },
            onPerformLayer1Login = { performLayer1Login(it) },
            onPerformLayer2OtpVerify = { performLayer2OtpVerify() },
            onSubmitAddFamilyEmail = { submitAddFamilyEmail() },
            onLogout = {
              scope.launch(Dispatchers.IO) {
                if (activeSessionToken.isNotBlank()) {
                  callServerHttp("/api/auth/logout", "POST", "{}")
                }
                withContext(Dispatchers.Main) {
                  selectedTier = 0
                  activeSpeakerName = "Chưa đăng nhập"
                  activeSessionToken = ""
                  serverSynced = false
                  sessionCookies.clear()
                  allowedDeviceIds.clear()
                  for (k in deviceStates.keys.toList()) {
                    deviceStates[k] = false
                  }
                  activeTimers.clear()
                  clockSchedules.clear()
                  automationRules.clear()
                  customScenes.clear()
                  automationStatusMessage = ""
                  authEmail = ""
                  authPassword = ""
                  authOtpInput = ""
                  authStepDone = 0
                  guestPinInput = ""
                  guestPinConfirmInput = ""
                  guestNeedsPinSetup = false
                  guestInviteToken = ""
                  guestInviteUrl = ""
                  guestInviteStatus = ""
                  guestInviteIsError = false
                  voiceConversation.clear()
                  hasVoiceCommandResult = false
                  lastSpokenText = ""
                  speakerReply = "Chưa có lệnh"
                  authStatusColor = accentCyan
                  authStatusMessage = "Đã đăng xuất tài khoản."
                  addHistoryLog("Đã đăng xuất tài khoản")
                }
              }
            },
            onQrCodeScanned = { code ->
              redeemGuestQrCode(code)
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
        BottomTabItem("Tài khoản", "user", currentTab == 3, accentCyan, { currentTab = 3; accountSubScreen = "menu" }, Modifier.weight(1f))
      }
    }

    SnackbarHost(
      hostState = snackbarHostState,
      modifier = Modifier
        .align(Alignment.BottomCenter)
        .padding(horizontal = 16.dp, vertical = 72.dp),
    )

    if (showVoiceSheet) {
      val sheetPhrase = if (selectedTier == 1) "Mở cửa chính" else "Bật đèn phòng khách"
      val sheetRole = when (selectedTier) {
        1 -> "Chủ nhà"
        2 -> "Gia đình"
        3 -> "Khách"
        else -> "Chưa đăng nhập"
      }
      VoiceBottomSheet(
        samplePhrase = sheetPhrase,
        roleLabel = sheetRole,
        onStopRecording = { phrase ->
          showVoiceSheet = false
          executeVoiceCommand(phrase, fromLiveMic = true)
        },
        onDismiss = { showVoiceSheet = false },
      )
    }
  }
}
