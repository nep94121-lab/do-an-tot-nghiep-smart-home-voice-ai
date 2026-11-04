package vn.edu.hust.seee.smarthome.ui.main

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp

@Composable
internal fun LineIcon(
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
      "x", "close" -> {
        drawLine(tint, Offset(w * 0.25f, h * 0.25f), Offset(w * 0.75f, h * 0.75f), strokeWidth = sw, cap = StrokeCap.Round)
        drawLine(tint, Offset(w * 0.75f, h * 0.25f), Offset(w * 0.25f, h * 0.75f), strokeWidth = sw, cap = StrokeCap.Round)
      }
      "qr_code", "scan" -> {
        val s = w * 0.28f
        drawRoundRect(tint, Offset(w * 0.14f, h * 0.14f), Size(s, s), CornerRadius(2f, 2f), stroke)
        drawRoundRect(tint, Offset(w * 0.58f, h * 0.14f), Size(s, s), CornerRadius(2f, 2f), stroke)
        drawRoundRect(tint, Offset(w * 0.14f, h * 0.58f), Size(s, s), CornerRadius(2f, 2f), stroke)
        drawLine(tint, Offset(w * 0.58f, h * 0.72f), Offset(w * 0.86f, h * 0.72f), strokeWidth = sw, cap = StrokeCap.Round)
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
      "check" -> {
        val p = Path().apply {
          moveTo(w * 0.20f, h * 0.50f)
          lineTo(w * 0.42f, h * 0.72f)
          lineTo(w * 0.80f, h * 0.28f)
        }
        drawPath(p, color = tint, style = stroke)
      }
      else -> {
        drawCircle(tint, radius = w * 0.26f, center = Offset(w * 0.50f, h * 0.42f), style = stroke)
        drawLine(tint, Offset(w * 0.38f, h * 0.78f), Offset(w * 0.62f, h * 0.78f), strokeWidth = sw, cap = StrokeCap.Round)
      }
    }
  }
}
