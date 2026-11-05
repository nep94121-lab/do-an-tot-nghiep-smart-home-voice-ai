package vn.edu.hust.seee.smarthome.ui.main.tabs

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.util.Locale
import vn.edu.hust.seee.smarthome.ui.main.ForgotPasswordScreen
import vn.edu.hust.seee.smarthome.ui.main.LineIcon
import vn.edu.hust.seee.smarthome.ui.main.QrScannerScreen
import vn.edu.hust.seee.smarthome.ui.main.components.TierChip

@Composable
fun AccountScreenTab(
  accountSubScreen: String,
  onNavigateSubScreen: (String) -> Unit,
  selectedTier: Int,
  onSelectTier: (Int, String) -> Unit,
  authEmail: String,
  onAuthEmailChange: (String) -> Unit,
  authPassword: String,
  onAuthPasswordChange: (String) -> Unit,
  authOtpInput: String,
  onAuthOtpInputChange: (String) -> Unit,
  openAuthStep: Int,
  onOpenAuthStepChange: (Int) -> Unit,
  authStepDone: Int,
  authStatusMessage: String = "",
  authStatusColor: Color,
  allowlistTargetEmail: String,
  onAllowlistTargetEmailChange: (String) -> Unit,
  allowlistStatusMessage: String,
  allowlistStatusColor: Color,
  hasRecordedAuthSample: Boolean,
  newMemberName: String,
  onNewMemberNameChange: (String) -> Unit,
  guestQrDuration: String,
  onGuestQrDurationChange: (String) -> Unit,
  historyLogs: List<String>,
  showTechLogs: Boolean,
  onToggleTechLogs: () -> Unit,
  lastDetectedF0: Double,
  lastCosineScore: Double,
  lastSyncTime: String,
  onPerformRegister: () -> Unit = {},
  onPerformLayer1Login: (String) -> Unit,
  onPerformLayer2OtpVerify: () -> Unit,
  onUploadVoiceSample: () -> Unit,
  onSubmitAddFamilyEmail: () -> Unit,
  onLogout: () -> Unit,
  onSpeakSamplePhrase: () -> Unit,
  onReRecordVoiceSample: () -> Unit,
  onQrCodeScanned: (String) -> Unit,
  accentCyan: Color,
  accentRed: Color,
  cardBg: Color,
  cardBorder: Color,
  bgDark: Color,
  textPrimary: Color,
  textSecondary: Color,
  modifier: Modifier = Modifier,
) {
  Column(
    modifier = modifier.fillMaxWidth(),
    verticalArrangement = Arrangement.spacedBy(10.dp),
  ) {
    if (accountSubScreen == "menu") {
      // Card Hồ sơ (3 dòng: Vai trò, Email, Thời hạn)
      Column(
        modifier = Modifier
          .fillMaxWidth()
          .clip(RoundedCornerShape(16.dp))
          .background(cardBg)
          .border(1.dp, cardBorder, RoundedCornerShape(16.dp))
          .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(7.dp),
      ) {
        Text(
          text = "Hồ sơ",
          color = textPrimary,
          fontSize = 16.sp,
          fontWeight = FontWeight.SemiBold,
        )

        Row(
          modifier = Modifier.fillMaxWidth(),
          horizontalArrangement = Arrangement.SpaceBetween,
          verticalAlignment = Alignment.CenterVertically,
        ) {
          Text("Vai trò", color = textSecondary, fontSize = 13.sp)
          Text(
            text = when (selectedTier) {
              1 -> "Chủ nhà"
              2 -> "Gia đình"
              else -> "Khách"
            },
            color = textPrimary,
            fontSize = 14.sp,
            fontWeight = FontWeight.SemiBold,
          )
        }

        Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(cardBorder))

        Row(
          modifier = Modifier.fillMaxWidth(),
          horizontalArrangement = Arrangement.SpaceBetween,
          verticalAlignment = Alignment.CenterVertically,
        ) {
          Text("Email", color = textSecondary, fontSize = 13.sp)
          Text(
            text = authEmail.ifBlank { "Chưa đăng nhập" },
            color = textPrimary,
            fontSize = 14.sp,
            fontWeight = FontWeight.SemiBold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f, fill = false).padding(start = 12.dp),
          )
        }

        Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(cardBorder))

        Row(
          modifier = Modifier.fillMaxWidth(),
          horizontalArrangement = Arrangement.SpaceBetween,
          verticalAlignment = Alignment.CenterVertically,
        ) {
          Text("Thời hạn", color = textSecondary, fontSize = 13.sp)
          Text(
            text = if (selectedTier == 3) "Còn 24 giờ" else "Không giới hạn",
            color = textPrimary,
            fontSize = 14.sp,
            fontWeight = FontWeight.SemiBold,
          )
        }
      }

      // Card Quản lý ("Xác thực", "Lời mời", "Quét mã QR", "Quên mật khẩu", "Cài đặt")
      Column(
        modifier = Modifier
          .fillMaxWidth()
          .clip(RoundedCornerShape(16.dp))
          .background(cardBg)
          .border(1.dp, cardBorder, RoundedCornerShape(16.dp))
          .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(7.dp),
      ) {
        Text(
          text = "Quản lý",
          color = textPrimary,
          fontSize = 15.sp,
          fontWeight = FontWeight.SemiBold,
        )

        Row(
          modifier = Modifier
            .fillMaxWidth()
            .clickable { onNavigateSubScreen("auth") }
            .padding(vertical = 2.dp),
          horizontalArrangement = Arrangement.SpaceBetween,
          verticalAlignment = Alignment.CenterVertically,
        ) {
          Text("Xác thực", color = textPrimary, fontSize = 14.sp)
          Text("›", color = textSecondary, fontSize = 16.sp)
        }

        Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(cardBorder))

        Row(
          modifier = Modifier
            .fillMaxWidth()
            .clickable { onNavigateSubScreen("guest") }
            .padding(vertical = 2.dp),
          horizontalArrangement = Arrangement.SpaceBetween,
          verticalAlignment = Alignment.CenterVertically,
        ) {
          Text("Lời mời", color = textPrimary, fontSize = 14.sp)
          Text("›", color = textSecondary, fontSize = 16.sp)
        }

        Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(cardBorder))

        Row(
          modifier = Modifier
            .fillMaxWidth()
            .clickable { onNavigateSubScreen("qr_scanner") }
            .padding(vertical = 2.dp),
          horizontalArrangement = Arrangement.SpaceBetween,
          verticalAlignment = Alignment.CenterVertically,
        ) {
          Text("Quét mã QR", color = textPrimary, fontSize = 14.sp)
          Text("›", color = textSecondary, fontSize = 16.sp)
        }

        Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(cardBorder))

        Row(
          modifier = Modifier
            .fillMaxWidth()
            .clickable { onNavigateSubScreen("forgot_otp") }
            .padding(vertical = 2.dp),
          horizontalArrangement = Arrangement.SpaceBetween,
          verticalAlignment = Alignment.CenterVertically,
        ) {
          Text("Quên mật khẩu", color = textPrimary, fontSize = 14.sp)
          Text("›", color = textSecondary, fontSize = 16.sp)
        }

        Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(cardBorder))

        Row(
          modifier = Modifier
            .fillMaxWidth()
            .clickable { onNavigateSubScreen("settings") }
            .padding(vertical = 2.dp),
          horizontalArrangement = Arrangement.SpaceBetween,
          verticalAlignment = Alignment.CenterVertically,
        ) {
          Text("Cài đặt", color = textPrimary, fontSize = 14.sp)
          Text("›", color = textSecondary, fontSize = 16.sp)
        }
      }

      Text(
        text = "Mỗi tab mở một màn riêng, không cuộn tới mục khác.",
        color = textSecondary,
        fontSize = 12.sp,
      )

      Button(
        onClick = onLogout,
        colors = ButtonDefaults.buttonColors(containerColor = cardBg, contentColor = textPrimary),
        shape = RoundedCornerShape(10.dp),
        modifier = Modifier
          .fillMaxWidth()
          .height(42.dp)
          .border(1.dp, cardBorder, RoundedCornerShape(10.dp)),
      ) {
        Text("Đăng xuất", fontSize = 14.sp, fontWeight = FontWeight.Medium)
      }
    } else if (accountSubScreen == "forgot_otp") {
      ForgotPasswordScreen(
        initialEmail = authEmail,
        onBack = { onNavigateSubScreen("menu") },
        onComplete = { onNavigateSubScreen("menu") },
      )
    } else if (accountSubScreen == "qr_scanner") {
      QrScannerScreen(
        onCodeScanned = onQrCodeScanned,
        onClose = { onNavigateSubScreen("menu") },
      )
    } else if (accountSubScreen == "auth") {
      // 12. Android auth: tiến trình dạng chữ "Bước n/3" và progress line mảnh
      Column(
        modifier = Modifier
          .fillMaxWidth()
          .clip(RoundedCornerShape(16.dp))
          .background(cardBg)
          .border(1.dp, cardBorder, RoundedCornerShape(16.dp))
          .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
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
            .padding(10.dp),
          verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
          Row(
            modifier = Modifier
              .fillMaxWidth()
              .clickable { onOpenAuthStepChange(1) },
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
              onValueChange = onAuthEmailChange,
              placeholder = { Text("Email tài khoản", fontSize = 13.sp) },
              singleLine = true,
              modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
              value = authPassword,
              onValueChange = onAuthPasswordChange,
              placeholder = { Text("Mật khẩu", fontSize = 13.sp) },
              singleLine = true,
              visualTransformation = PasswordVisualTransformation(),
              modifier = Modifier.fillMaxWidth(),
            )
            Row(
              modifier = Modifier.fillMaxWidth(),
              horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
              Button(
                onClick = onPerformRegister,
                colors = ButtonDefaults.buttonColors(containerColor = cardBg, contentColor = accentCyan),
                shape = RoundedCornerShape(10.dp),
                modifier = Modifier
                  .weight(1f)
                  .height(42.dp)
                  .border(1.dp, accentCyan, RoundedCornerShape(10.dp)),
              ) {
                Text("Đăng ký", fontSize = 13.sp, fontWeight = FontWeight.Medium)
              }
              Button(
                onClick = { onPerformLayer1Login("password") },
                colors = ButtonDefaults.buttonColors(containerColor = accentCyan, contentColor = Color.White),
                shape = RoundedCornerShape(10.dp),
                modifier = Modifier
                  .weight(1f)
                  .height(42.dp),
              ) {
                Text("Đăng nhập", fontSize = 13.sp, fontWeight = FontWeight.Medium)
              }
            }
            if (authStatusMessage.isNotBlank()) {
              Text(
                text = authStatusMessage,
                color = authStatusColor,
                fontSize = 12.sp,
                fontWeight = FontWeight.Medium,
              )
            }
            OutlinedTextField(
              value = authOtpInput,
              onValueChange = onAuthOtpInputChange,
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
            .padding(horizontal = 12.dp, vertical = 9.dp),
          verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
          Row(
            modifier = Modifier
              .fillMaxWidth()
              .clickable { onOpenAuthStepChange(2) },
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
            .padding(horizontal = 12.dp, vertical = 9.dp),
          verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
          Row(
            modifier = Modifier
              .fillMaxWidth()
              .clickable { onOpenAuthStepChange(3) },
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
                onValueChange = onAllowlistTargetEmailChange,
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
                  onPerformLayer2OtpVerify()
                } else {
                  onPerformLayer1Login("password")
                }
                onOpenAuthStepChange(2)
              }
              2 -> {
                onUploadVoiceSample()
                onOpenAuthStepChange(3)
              }
              else -> {
                if (allowlistTargetEmail.isNotBlank()) {
                  onSubmitAddFamilyEmail()
                } else {
                  onNavigateSubScreen("menu")
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

        if (openAuthStep == 2 && hasRecordedAuthSample) {
          Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
          ) {
            TierChip(
              label = "Nghe lại",
              selected = false,
              activeColor = accentCyan,
              onClick = onSpeakSamplePhrase,
              modifier = Modifier.weight(1f),
            )
            TierChip(
              label = "Thu lại",
              selected = false,
              activeColor = textSecondary,
              onClick = onReRecordVoiceSample,
              modifier = Modifier.weight(1f),
            )
          }
        } else if (openAuthStep > 1) {
          TierChip(
            label = "Quay lại",
            selected = false,
            activeColor = textSecondary,
            onClick = { onOpenAuthStepChange((openAuthStep - 1).coerceAtLeast(1)) },
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
          .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
      ) {
        Text(
          text = "Chọn thời hạn và quyền truy cập cho khách.",
          color = textSecondary,
          fontSize = 13.sp,
          fontWeight = FontWeight.Normal,
        )
        OutlinedTextField(
          value = newMemberName,
          onValueChange = onNewMemberNameChange,
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
              onClick = { onGuestQrDurationChange(dur) },
              modifier = Modifier.weight(1f),
            )
          }
        }
        Button(
          onClick = { onNavigateSubScreen("menu") },
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
          onClick = { onNavigateSubScreen("menu") },
          modifier = Modifier.fillMaxWidth(),
        )
      }
    } else if (accountSubScreen == "logs") {
      // Nhật ký: danh sách sự kiện cơ bản
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
              .clickable(onClick = onToggleTechLogs)
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
          TierChip("Chủ nhà", selectedTier == 1, accentCyan, { onSelectTier(1, "Nguyễn Tuấn Anh") }, Modifier.weight(1f))
          TierChip("Gia đình", selectedTier == 2, accentCyan, { onSelectTier(2, "Thành viên A") }, Modifier.weight(1f))
          TierChip("Khách", selectedTier == 3, accentCyan, { onSelectTier(3, "Khách C") }, Modifier.weight(1f))
        }
      }
    }
  }
}
