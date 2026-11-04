package vn.edu.hust.seee.smarthome.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val V1LightColorScheme = lightColorScheme(
  primary = V1Accent,
  onPrimary = Color.White,
  primaryContainer = V1AccentSoft,
  onPrimaryContainer = V1Ink,
  secondary = V1Muted,
  onSecondary = Color.White,
  tertiary = V1Amber,
  background = V1Page,
  onBackground = V1Ink,
  surface = V1Card,
  onSurface = V1Ink,
  surfaceVariant = V1Page,
  onSurfaceVariant = V1Muted,
  outline = V1Line,
  error = V1Red,
  onError = Color.White,
)

@Composable
fun SmartHomeVoiceAITheme(
  darkTheme: Boolean = false,
  dynamicColor: Boolean = false,
  content: @Composable () -> Unit,
) {
  MaterialTheme(
    colorScheme = V1LightColorScheme,
    typography = Typography,
    content = content,
  )
}

@Composable
fun AppTheme(
  darkTheme: Boolean = false,
  dynamicColor: Boolean = false,
  content: @Composable () -> Unit,
) {
  SmartHomeVoiceAITheme(darkTheme = darkTheme, dynamicColor = dynamicColor, content = content)
}
