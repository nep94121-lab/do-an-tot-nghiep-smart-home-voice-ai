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
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
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
  isAuthenticated: Boolean,
  selectedTier: Int,
  onSelectTier: (Int, String) -> Unit,
  authEmail: String,
  onAuthEmailChange: (String) -> Unit,
  authPassword: String,
  onAuthPasswordChange: (String) -> Unit,
  authOtpInput: String,
  onAuthOtpInputChange: (String) -> Unit,
  authStepDone: Int,
  authStatusMessage: String = "",
  authStatusColor: Color,
  allowlistTargetEmail: String,
  onAllowlistTargetEmailChange: (String) -> Unit,
  allowlistStatusMessage: String,
  allowlistStatusColor: Color,
  newMemberName: String,
  onNewMemberNameChange: (String) -> Unit,
  guestQrDuration: String,
  onGuestQrDurationChange: (String) -> Unit,
  guestPinInput: String = "",
  onGuestPinInputChange: (String) -> Unit = {},
  guestPinConfirmInput: String = "",
  onGuestPinConfirmInputChange: (String) -> Unit = {},
  guestNeedsPinSetup: Boolean = false,
  guestInviteToken: String = "",
  guestInviteUrl: String = "",
  guestInviteStatus: String = "",
  guestInviteIsError: Boolean = false,
  onCreateGuestInvite: () -> Unit = {},
  onSendResetOtp: suspend (email: String) -> Pair<Boolean, String> = { true to "Đã gửi mã OTP." },
  onVerifyResetOtp: suspend (email: String, otp: String) -> Pair<Boolean, String> = { _, _ -> true to "Mã OTP hợp lệ." },
  onConfirmResetPassword: suspend (email: String, otp: String, newPassword: String, confirmPassword: String) -> Pair<Boolean, String> = { _, _, _, _ -> true to "Đặt lại mật khẩu thành công!" },
  historyLogs: List<String>,
  showTechLogs: Boolean,
  onToggleTechLogs: () -> Unit,
  lastDetectedF0: Double,
  lastCosineScore: Double,
  lastSyncTime: String,
  onPerformRegister: () -> Unit = {},
  onPerformLayer1Login: (String) -> Unit,
  onPerformLayer2OtpVerify: () -> Unit,
  onSubmitAddFamilyEmail: () -> Unit,
  onLogout: () -> Unit,
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
            text = if (!isAuthenticated) {
              "Chưa đăng nhập"
            } else {
              when (selectedTier) {
                1 -> "Chủ nhà"
                2 -> "Gia đình"
                else -> "Khách"
              }
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
            text = if (!isAuthenticated) "Chưa đăng nhập" else authEmail.ifBlank { "Phiên QR khách" },
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
            text = when {
              !isAuthenticated -> "Chưa kích hoạt"
              selectedTier == 3 -> "Tạm thời"
              else -> "Không giới hạn"
            },
            color = textPrimary,
            fontSize = 14.sp,
            fontWeight = FontWeight.SemiBold,
          )
        }
      }

      // Card Quản lý
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
          Text("Đăng nhập / Xác thực", color = textPrimary, fontSize = 14.sp)
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
          Text("Quét mã QR mời khách", color = textPrimary, fontSize = 14.sp)
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

        if (isAuthenticated && selectedTier == 1) {
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
              .clickable { onNavigateSubScreen("logs") }
              .padding(vertical = 2.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
          ) {
            Text("Nhật ký", color = textPrimary, fontSize = 14.sp)
            Text("›", color = textSecondary, fontSize = 16.sp)
          }
        }
      }

      if (isAuthenticated) {
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
      } else {
        Button(
          onClick = { onNavigateSubScreen("auth") },
          colors = ButtonDefaults.buttonColors(containerColor = accentCyan, contentColor = Color.White),
          shape = RoundedCornerShape(10.dp),
          modifier = Modifier
            .fillMaxWidth()
            .height(42.dp),
        ) {
          Text("Đăng nhập tài khoản", fontSize = 14.sp, fontWeight = FontWeight.Medium)
        }
      }
    } else if (accountSubScreen == "forgot_otp") {
      ForgotPasswordScreen(
        initialEmail = authEmail,
        onBack = { onNavigateSubScreen("menu") },
        onComplete = { onNavigateSubScreen("auth") },
        onSendResetOtp = onSendResetOtp,
        onVerifyResetOtp = onVerifyResetOtp,
        onConfirmResetPassword = onConfirmResetPassword,
      )
    } else if (accountSubScreen == "qr_scanner") {
      QrScannerScreen(
        onCodeScanned = onQrCodeScanned,
        onClose = { onNavigateSubScreen("menu") },
      )
    } else if (accountSubScreen == "auth") {
      Column(
        modifier = Modifier
          .fillMaxWidth()
          .clip(RoundedCornerShape(16.dp))
          .background(cardBg)
          .border(1.dp, cardBorder, RoundedCornerShape(16.dp))
          .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
      ) {
        Text(
          text = "Đăng nhập bằng Email & Mật khẩu",
          color = textPrimary,
          fontSize = 15.sp,
          fontWeight = FontWeight.SemiBold,
        )
        Text(
          text = "Nhập tài khoản đã đăng ký. Chủ nhà Cấp 1 xác nhận thêm mã OTP gửi qua Gmail khi được yêu cầu.",
          color = textSecondary,
          fontSize = 12.sp,
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

        Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(cardBorder))

        Text(
          text = "Xác thực OTP Gmail (khi hệ thống yêu cầu)",
          color = textPrimary,
          fontSize = 13.sp,
          fontWeight = FontWeight.Medium,
        )
        Row(
          modifier = Modifier.fillMaxWidth(),
          horizontalArrangement = Arrangement.spacedBy(8.dp),
          verticalAlignment = Alignment.CenterVertically,
        ) {
          OutlinedTextField(
            value = authOtpInput,
            onValueChange = onAuthOtpInputChange,
            placeholder = { Text("Mã OTP 6 số", fontSize = 13.sp) },
            singleLine = true,
            modifier = Modifier.weight(1f),
          )
          Button(
            onClick = onPerformLayer2OtpVerify,
            colors = ButtonDefaults.buttonColors(containerColor = accentCyan, contentColor = Color.White),
            shape = RoundedCornerShape(10.dp),
            modifier = Modifier.height(48.dp),
          ) {
            Text("Xác nhận", fontSize = 13.sp, fontWeight = FontWeight.Medium)
          }
        }

        Button(
          onClick = { onNavigateSubScreen("qr_scanner") },
          colors = ButtonDefaults.buttonColors(containerColor = cardBg, contentColor = textPrimary),
          shape = RoundedCornerShape(10.dp),
          modifier = Modifier
            .fillMaxWidth()
            .height(42.dp)
            .border(1.dp, cardBorder, RoundedCornerShape(10.dp)),
        ) {
          Text("Quét mã QR mời khách", fontSize = 13.sp, fontWeight = FontWeight.Medium)
        }

        if (isAuthenticated && selectedTier == 1) {
          Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(cardBorder))
          Text(
            text = "Quản trị thành viên gia đình (Chủ nhà)",
            color = textPrimary,
            fontSize = 13.sp,
            fontWeight = FontWeight.Medium,
          )
          OutlinedTextField(
            value = allowlistTargetEmail,
            onValueChange = onAllowlistTargetEmailChange,
            placeholder = { Text("Email thành viên gia đình", fontSize = 13.sp) },
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
          Button(
            onClick = onSubmitAddFamilyEmail,
            colors = ButtonDefaults.buttonColors(containerColor = accentCyan, contentColor = Color.White),
            shape = RoundedCornerShape(10.dp),
            modifier = Modifier.fillMaxWidth().height(42.dp),
          ) {
            Text("Thêm email gia đình", fontSize = 13.sp, fontWeight = FontWeight.Medium)
          }
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
        OutlinedTextField(
          value = guestPinInput,
          onValueChange = { raw -> onGuestPinInputChange(raw.filter { it.isDigit() }.take(4)) },
          placeholder = { Text("Mã PIN Chủ nhà (4 số)", fontSize = 13.sp) },
          singleLine = true,
          visualTransformation = PasswordVisualTransformation(),
          modifier = Modifier.fillMaxWidth(),
        )
        if (guestNeedsPinSetup) {
          OutlinedTextField(
            value = guestPinConfirmInput,
            onValueChange = { raw -> onGuestPinConfirmInputChange(raw.filter { it.isDigit() }.take(4)) },
            placeholder = { Text("Xác nhận mã PIN 4 số (lần đầu)", fontSize = 13.sp) },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth(),
          )
        }
        if (guestInviteStatus.isNotBlank()) {
          Text(
            text = guestInviteStatus,
            color = if (guestInviteIsError) accentRed else accentCyan,
            fontSize = 12.sp,
            fontWeight = FontWeight.Medium,
          )
        }
        if (guestInviteToken.isNotBlank()) {
          val clipboardManager = LocalClipboardManager.current
          val maskedToken = if (guestInviteToken.length > 16) {
            "${guestInviteToken.take(8)}••••••••${guestInviteToken.takeLast(6)}"
          } else {
            "••••••••"
          }
          Column(
            modifier = Modifier
              .fillMaxWidth()
              .clip(RoundedCornerShape(10.dp))
              .background(bgDark)
              .border(1.dp, accentCyan, RoundedCornerShape(10.dp))
              .padding(10.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
          ) {
            Text(
              text = "Mã mời khách (Cấp 3)",
              color = textSecondary,
              fontSize = 11.sp,
              fontWeight = FontWeight.Medium,
            )
            Text(
              text = maskedToken,
              color = textPrimary,
              fontSize = 13.sp,
              fontWeight = FontWeight.SemiBold,
            )
            Text(
              text = "Trạng thái: Đã tạo mã dùng một lần (ẩn giá trị để bảo mật)",
              color = textSecondary,
              fontSize = 11.sp,
            )
            Button(
              onClick = { clipboardManager.setText(AnnotatedString(guestInviteToken)) },
              colors = ButtonDefaults.buttonColors(containerColor = cardBg, contentColor = accentCyan),
              shape = RoundedCornerShape(8.dp),
              modifier = Modifier
                .fillMaxWidth()
                .height(38.dp)
                .border(1.dp, accentCyan, RoundedCornerShape(8.dp))
                .semantics { contentDescription = "guest_invite_ready" },
            ) {
              Text("Sao chép mã mời", fontSize = 12.sp, fontWeight = FontWeight.Medium)
            }
          }
        }
        Button(
          onClick = onCreateGuestInvite,
          colors = ButtonDefaults.buttonColors(containerColor = accentCyan),
          shape = RoundedCornerShape(10.dp),
          modifier = Modifier.fillMaxWidth().height(44.dp),
        ) {
          Text("Tạo lời mời", color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Medium)
        }
        TierChip(
          label = "Quay lại",
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
