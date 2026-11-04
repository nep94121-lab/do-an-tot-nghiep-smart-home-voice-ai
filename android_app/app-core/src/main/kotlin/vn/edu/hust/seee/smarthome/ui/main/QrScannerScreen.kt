package vn.edu.hust.seee.smarthome.ui.main

import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import vn.edu.hust.seee.smarthome.theme.V1Accent
import vn.edu.hust.seee.smarthome.theme.V1Card
import vn.edu.hust.seee.smarthome.theme.V1Ink
import vn.edu.hust.seee.smarthome.theme.V1Line
import vn.edu.hust.seee.smarthome.theme.V1Muted
import vn.edu.hust.seee.smarthome.theme.V1Page

/**
 * M5: QR Scanner Screen (np_m5_qr_scanner.html)
 * Viewfinder with 215x215dp 4-corner frame, "Bật camera", "Nhập mã".
 */
@Composable
fun QrScannerScreen(
  onCodeScanned: (String) -> Unit = {},
  onClose: () -> Unit = {},
  modifier: Modifier = Modifier,
) {
  var isCameraActive by remember { mutableStateOf(false) }
  var showManualInput by remember { mutableStateOf(false) }
  var manualCode by remember { mutableStateOf("") }
  var statusMessage by remember { mutableStateOf("Khi quét được mã: Đang kiểm tra mã…") }
  val scope = rememberCoroutineScope()

  // Scanning laser line animation
  val infiniteTransition = rememberInfiniteTransition(label = "scanLaserTransition")
  val laserProgress by infiniteTransition.animateFloat(
    initialValue = 0.05f,
    targetValue = 0.95f,
    animationSpec = infiniteRepeatable(
      animation = tween(1500, easing = FastOutSlowInEasing),
      repeatMode = RepeatMode.Reverse,
    ),
    label = "laserProgress",
  )

  Column(
    modifier = modifier
      .fillMaxSize()
      .background(V1Page),
  ) {
    // Top Bar: Title "Quét mã QR" + Close 'x' button
    Column(
      modifier = Modifier
        .fillMaxWidth()
        .background(V1Card)
        .padding(horizontal = 16.dp, vertical = 14.dp),
    ) {
      Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
      ) {
        Text(
          text = "Quét mã QR",
          color = V1Ink,
          fontSize = 22.sp,
          fontWeight = FontWeight.SemiBold,
        )

        Box(
          modifier = Modifier
            .size(40.dp)
            .clip(RoundedCornerShape(8.dp))
            .clickable { onClose() },
          contentAlignment = Alignment.Center,
        ) {
          LineIcon("x", V1Muted, 20)
        }
      }

      Text(
        text = "Quét lời mời từ Chủ nhà",
        color = V1Muted,
        fontSize = 12.sp,
      )
    }

    Box(
      modifier = Modifier
        .fillMaxWidth()
        .height(1.dp)
        .background(V1Line)
    )

    // Main Content
    Column(
      modifier = Modifier
        .weight(1f)
        .fillMaxWidth()
        .verticalScroll(rememberScrollState())
        .padding(16.dp),
      horizontalAlignment = Alignment.CenterHorizontally,
    ) {
      // Camera Container (background #22383D, rounded 16dp)
      Box(
        modifier = Modifier
          .fillMaxWidth()
          .height(340.dp)
          .clip(RoundedCornerShape(16.dp))
          .background(Color(0xFF22383D)),
        contentAlignment = Alignment.Center,
      ) {
        // 215x215dp Scanframe with 4 Corner Brackets
        Box(
          modifier = Modifier
            .size(215.dp),
          contentAlignment = Alignment.Center,
        ) {
          // Draw 4 corner brackets
          Canvas(modifier = Modifier.fillMaxSize()) {
            val strokeWidth = 3.dp.toPx()
            val bracketLen = 38.dp.toPx()
            val cornerRadius = 8.dp.toPx()
            val w = size.width
            val h = size.height
            val color = Color.White
            val stroke = Stroke(width = strokeWidth, cap = StrokeCap.Round, join = StrokeJoin.Round)

            // Top-Left (TL)
            val tlPath = Path().apply {
              moveTo(0f, bracketLen)
              lineTo(0f, cornerRadius)
              quadraticTo(0f, 0f, cornerRadius, 0f)
              lineTo(bracketLen, 0f)
            }
            drawPath(tlPath, color, style = stroke)

            // Top-Right (TR)
            val trPath = Path().apply {
              moveTo(w - bracketLen, 0f)
              lineTo(w - cornerRadius, 0f)
              quadraticTo(w, 0f, w, cornerRadius)
              lineTo(w, bracketLen)
            }
            drawPath(trPath, color, style = stroke)

            // Bottom-Left (BL)
            val blPath = Path().apply {
              moveTo(0f, h - bracketLen)
              lineTo(0f, h - cornerRadius)
              quadraticTo(0f, h, cornerRadius, h)
              lineTo(bracketLen, h)
            }
            drawPath(blPath, color, style = stroke)

            // Bottom-Right (BR)
            val brPath = Path().apply {
              moveTo(w - bracketLen, h)
              lineTo(w - cornerRadius, h)
              quadraticTo(w, h, w, h - cornerRadius)
              lineTo(w, h - bracketLen)
            }
            drawPath(brPath, color, style = stroke)

            // Laser scan line when camera is active
            if (isCameraActive) {
              val laserY = h * laserProgress
              drawLine(
                color = Color(0xFF087D85),
                start = Offset(10.dp.toPx(), laserY),
                end = Offset(w - 10.dp.toPx(), laserY),
                strokeWidth = 2.dp.toPx(),
                cap = StrokeCap.Round,
              )
            }
          }

          // Center Text / Indicator
          Text(
            text = if (isCameraActive) "Đang tìm mã QR..." else "Vùng camera sau",
            color = Color(0xFFC0D3D5),
            fontSize = 12.sp,
            textAlign = TextAlign.Center,
          )
        }
      }

      Spacer(modifier = Modifier.height(18.dp))

      // Instructions
      Text(
        text = "Đưa mã QR vào trong khung để quét",
        color = V1Ink,
        fontSize = 14.sp,
        fontWeight = FontWeight.Medium,
        textAlign = TextAlign.Center,
      )

      Spacer(modifier = Modifier.height(4.dp))

      Text(
        text = "Quét mã đang hiển thị trên màn hình Chủ nhà.",
        color = V1Muted,
        fontSize = 12.sp,
        textAlign = TextAlign.Center,
      )

      if (showManualInput) {
        Spacer(modifier = Modifier.height(14.dp))
        OutlinedTextField(
          value = manualCode,
          onValueChange = { manualCode = it },
          placeholder = { Text("Nhập mã lời mời...", color = V1Muted, fontSize = 13.sp) },
          singleLine = true,
          colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = V1Accent,
            unfocusedBorderColor = V1Line,
            focusedContainerColor = V1Card,
            unfocusedContainerColor = V1Card,
          ),
          modifier = Modifier.fillMaxWidth(),
        )
      }

      Spacer(modifier = Modifier.height(20.dp))

      // Action Buttons: "Bật camera" & "Nhập mã"
      Column(
        modifier = Modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(10.dp),
      ) {
        Button(
          onClick = {
            if (showManualInput && manualCode.isNotBlank()) {
              statusMessage = "Đang kiểm tra mã: $manualCode..."
              scope.launch {
                delay(800)
                statusMessage = "Mã hợp lệ! Đã cấp quyền khách."
                onCodeScanned(manualCode)
              }
            } else {
              isCameraActive = !isCameraActive
              statusMessage = if (isCameraActive) "Camera đang hoạt động. Di chuyển lại gần mã QR..." else "Khi quét được mã: Đang kiểm tra mã…"
            }
          },
          colors = ButtonDefaults.buttonColors(containerColor = V1Accent),
          shape = RoundedCornerShape(10.dp),
          modifier = Modifier.fillMaxWidth().height(44.dp),
        ) {
          Text(
            text = if (showManualInput) "Xác nhận mã" else if (isCameraActive) "Tắt camera" else "Bật camera",
            color = Color.White,
            fontSize = 14.sp,
            fontWeight = FontWeight.Medium,
          )
        }

        Button(
          onClick = {
            showManualInput = !showManualInput
          },
          colors = ButtonDefaults.buttonColors(containerColor = V1Card, contentColor = V1Ink),
          shape = RoundedCornerShape(10.dp),
          modifier = Modifier
            .fillMaxWidth()
            .height(44.dp)
            .border(1.dp, V1Line, RoundedCornerShape(10.dp)),
        ) {
          Text(
            text = if (showManualInput) "Quét qua Camera" else "Nhập mã",
            fontSize = 14.sp,
            fontWeight = FontWeight.Medium,
          )
        }
      }

      Spacer(modifier = Modifier.height(14.dp))

      Text(
        text = statusMessage,
        color = V1Muted,
        fontSize = 12.sp,
        textAlign = TextAlign.Center,
      )
    }
  }
}
