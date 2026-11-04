package vn.edu.hust.seee.smarthome.ui.main.tabs

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import vn.edu.hust.seee.smarthome.ui.main.LineIcon

@Composable
fun VoiceScreenTab(
  selectedTier: Int,
  hasVoiceCommandResult: Boolean,
  lastSpokenText: String,
  speakerReply: String,
  isListeningMic: Boolean,
  micErrorState: Boolean,
  voiceInput: String,
  onVoiceInputChange: (String) -> Unit,
  ttsEnabled: Boolean,
  onTtsToggle: (Boolean) -> Unit,
  onMicButtonClick: () -> Unit,
  onSendVoiceCommand: (String) -> Unit,
  onNavigateToAuth: () -> Unit,
  accentCyan: Color,
  cardBg: Color,
  cardBorder: Color,
  bgDark: Color,
  textPrimary: Color,
  textSecondary: Color,
  modifier: Modifier = Modifier,
) {
  Column(
    modifier = modifier.fillMaxWidth(),
    verticalArrangement = Arrangement.spacedBy(16.dp),
  ) {
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
          onClick = onNavigateToAuth,
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
          onClick = onMicButtonClick,
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

      // Form nhập lệnh + nút phụ "Gửi"
      Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
      ) {
        OutlinedTextField(
          value = voiceInput,
          onValueChange = onVoiceInputChange,
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
          onClick = { onSendVoiceCommand(voiceInput) },
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
          onCheckedChange = onTtsToggle,
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
            .clickable { onNavigateToAuth() }
            .padding(horizontal = 6.dp, vertical = 4.dp),
        )
      }
    }
  }
}
