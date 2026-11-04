package vn.edu.hust.seee.smarthome.ui.main

import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import vn.edu.hust.seee.smarthome.theme.V1Accent
import vn.edu.hust.seee.smarthome.theme.V1AccentSoft
import vn.edu.hust.seee.smarthome.theme.V1Card
import vn.edu.hust.seee.smarthome.theme.V1Ink
import vn.edu.hust.seee.smarthome.theme.V1Line
import vn.edu.hust.seee.smarthome.theme.V1Muted
import vn.edu.hust.seee.smarthome.theme.V1Page
import vn.edu.hust.seee.smarthome.theme.V1Red
import kotlin.math.sin

/**
 * M4: Voice Bottom Sheet (np_m4_voice_sheet.html)
 * Modal bottom sheet with scrim background, drag handle, wavecircle, 12-bar waveform, timer, sample phrase, and actions.
 */
@Composable
fun VoiceBottomSheet(
  samplePhrase: String = "Mở cửa chính cho tôi.",
  onStopRecording: (String) -> Unit = {},
  onDismiss: () -> Unit = {},
  modifier: Modifier = Modifier,
) {
  var recordingSeconds by remember { mutableIntStateOf(3) }
  var isRecording by remember { mutableStateOf(true) }
  var recordingResult by remember { mutableStateOf<String?>("Đạt — đã xác thực · Chủ nhà") }

  // 5-second recording countdown
  LaunchedEffect(isRecording) {
    if (isRecording) {
      while (recordingSeconds < 5) {
        delay(1000)
        recordingSeconds += 1
      }
    }
  }

  // Animation for 12 waveform bars
  val infiniteTransition = rememberInfiniteTransition(label = "waveformTransition")
  val pulseAnim by infiniteTransition.animateFloat(
    initialValue = 0.4f,
    targetValue = 1.0f,
    animationSpec = infiniteRepeatable(
      animation = tween(durationMillis = 650, easing = FastOutSlowInEasing),
      repeatMode = RepeatMode.Reverse,
    ),
    label = "pulseAnim",
  )

  val baseBarHeights = remember {
    listOf(16f, 28f, 42f, 24f, 52f, 36f, 58f, 30f, 45f, 20f, 34f, 16f)
  }

  // Scrim Overlay
  Box(
    modifier = modifier
      .fillMaxSize()
      .background(Color(0x7A0F2226))
      .clickable(
        interactionSource = remember { MutableInteractionSource() },
        indication = null,
        onClick = onDismiss,
      ),
    contentAlignment = Alignment.BottomCenter,
  ) {
    // Sheet Card
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .clip(RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp))
        .background(V1Card)
        .clickable(
          interactionSource = remember { MutableInteractionSource() },
          indication = null,
          onClick = { /* consume click */ },
        )
        .padding(horizontal = 20.dp, vertical = 14.dp),
      horizontalAlignment = Alignment.CenterHorizontally,
    ) {
      // Drag Handle
      Box(
        modifier = Modifier
          .width(36.dp)
          .height(4.dp)
          .clip(RoundedCornerShape(5.dp))
          .background(Color(0xFFC8D4D6)),
      )

      Spacer(modifier = Modifier.height(14.dp))

      // Header Row: Title & Close 'x' button
      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
      ) {
        Text(
          text = if (isRecording) "Đang thu âm" else "Hoàn tất thu âm",
          color = V1Ink,
          fontSize = 18.sp,
          fontWeight = FontWeight.SemiBold,
        )

        Box(
          modifier = Modifier
            .size(40.dp)
            .clip(RoundedCornerShape(8.dp))
            .clickable { onDismiss() },
          contentAlignment = Alignment.Center,
        ) {
          LineIcon("x", V1Muted, 20)
        }
      }

      Spacer(modifier = Modifier.height(16.dp))

      // Wavecircle (68x68dp, border #9ED4D6, bg #E6F3F2, mic icon)
      Box(
        modifier = Modifier
          .size(68.dp)
          .clip(CircleShape)
          .background(V1AccentSoft)
          .border(2.dp, Color(0xFF9ED4D6), CircleShape),
        contentAlignment = Alignment.Center,
      ) {
        LineIcon("mic", V1Accent, 28)
      }

      Spacer(modifier = Modifier.height(18.dp))

      // 12-bar Animated Waveform
      Row(
        modifier = Modifier
          .height(64.dp)
          .fillMaxWidth(),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
      ) {
        baseBarHeights.forEachIndexed { idx, baseH ->
          val phaseOffset = sin(idx.toDouble() * 0.7).toFloat() * 0.3f
          val factor = if (isRecording) (pulseAnim + phaseOffset).coerceIn(0.3f, 1.2f) else 0.35f
          val barH = (baseH * factor).coerceIn(8f, 60f)

          Box(
            modifier = Modifier
              .padding(horizontal = 2.5.dp)
              .width(5.dp)
              .height(barH.dp)
              .clip(RoundedCornerShape(4.dp))
              .background(V1Accent),
          )
        }
      }

      Spacer(modifier = Modifier.height(12.dp))

      // Timer Display (e.g. "00:03 / 00:05")
      Row(
        verticalAlignment = Alignment.Bottom,
        horizontalArrangement = Arrangement.Center,
      ) {
        Text(
          text = "00:0${recordingSeconds.coerceIn(0, 5)}",
          color = V1Ink,
          fontSize = 22.sp,
          fontWeight = FontWeight.SemiBold,
        )
        Text(
          text = " / 00:05",
          color = V1Muted,
          fontSize = 14.sp,
          fontWeight = FontWeight.Normal,
          modifier = Modifier.padding(bottom = 2.dp),
        )
      }

      Spacer(modifier = Modifier.height(8.dp))

      // Instruction
      Text(
        text = "Đọc câu mẫu để xác nhận giọng nói",
        color = V1Muted,
        fontSize = 13.sp,
        textAlign = TextAlign.Center,
      )

      Spacer(modifier = Modifier.height(8.dp))

      // Sample phrase card: “Mở cửa chính cho tôi.”
      Box(
        modifier = Modifier
          .fillMaxWidth()
          .clip(RoundedCornerShape(10.dp))
          .background(V1Page)
          .padding(vertical = 12.dp, horizontal = 16.dp),
        contentAlignment = Alignment.Center,
      ) {
        Text(
          text = "“$samplePhrase”",
          color = V1Ink,
          fontSize = 14.sp,
          fontWeight = FontWeight.Medium,
          textAlign = TextAlign.Center,
        )
      }

      Spacer(modifier = Modifier.height(16.dp))

      // Actions: Dừng thu & Hủy
      Column(
        modifier = Modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(10.dp),
      ) {
        Button(
          onClick = {
            isRecording = false
            onStopRecording(samplePhrase)
          },
          colors = ButtonDefaults.buttonColors(containerColor = V1Accent),
          shape = RoundedCornerShape(10.dp),
          modifier = Modifier.fillMaxWidth().height(44.dp),
        ) {
          Text(
            text = if (isRecording) "Dừng thu" else "Tiếp tục",
            color = Color.White,
            fontSize = 14.sp,
            fontWeight = FontWeight.Medium,
          )
        }

        Button(
          onClick = onDismiss,
          colors = ButtonDefaults.buttonColors(containerColor = V1Card, contentColor = V1Ink),
          shape = RoundedCornerShape(10.dp),
          modifier = Modifier
            .fillMaxWidth()
            .height(44.dp)
            .border(1.dp, V1Line, RoundedCornerShape(10.dp)),
        ) {
          Text(
            text = if (isRecording) "Hủy" else "Đóng",
            fontSize = 14.sp,
            fontWeight = FontWeight.Medium,
          )
        }
      }

      Spacer(modifier = Modifier.height(14.dp))

      // Result validation line
      Box(
        modifier = Modifier
          .fillMaxWidth()
          .height(1.dp)
          .background(V1Line)
      )

      Spacer(modifier = Modifier.height(10.dp))

      Column(
        modifier = Modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(4.dp),
      ) {
        Row(
          verticalAlignment = Alignment.CenterVertically,
          horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
          Box(
            modifier = Modifier
              .size(6.dp)
              .clip(CircleShape)
              .background(Color(0xFF15803D))
          )
          Text(
            text = "Đạt — đã xác thực · Chủ nhà",
            color = Color(0xFF15803D),
            fontSize = 12.sp,
            fontWeight = FontWeight.Medium,
          )
        }

        Row(
          verticalAlignment = Alignment.CenterVertically,
          horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
          Box(
            modifier = Modifier
              .size(6.dp)
              .clip(CircleShape)
              .background(V1Red)
          )
          Text(
            text = "Chưa đạt — âm thanh quá ngắn · Thu lại",
            color = V1Red,
            fontSize = 12.sp,
            fontWeight = FontWeight.Normal,
          )
        }
      }

      Spacer(modifier = Modifier.height(8.dp))
    }
  }
}
