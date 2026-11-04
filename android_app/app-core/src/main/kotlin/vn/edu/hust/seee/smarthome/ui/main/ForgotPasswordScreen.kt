package vn.edu.hust.seee.smarthome.ui.main

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
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
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
import vn.edu.hust.seee.smarthome.theme.V1Red

/**
 * M3: Forgot Password OTP Flow (np_m3_forgot_otp.html)
 * 3-step sequence: Email -> 6-digit OTP -> Reset password.
 */
@Composable
fun ForgotPasswordScreen(
  initialEmail: String = "t***@gmail.com",
  onBack: () -> Unit = {},
  onComplete: () -> Unit = onBack,
  modifier: Modifier = Modifier,
) {
  var currentStep by remember { mutableIntStateOf(2) } // Defaults to Step 2 to match mockup np_m3_forgot_otp.html
  var emailInput by remember { mutableStateOf(if (initialEmail.contains("***")) "nep94121@gmail.com" else initialEmail) }
  var otpInput by remember { mutableStateOf("") }
  var newPassword by remember { mutableStateOf("") }
  var confirmPassword by remember { mutableStateOf("") }

  var errorMessage by remember { mutableStateOf<String?>(null) }
  var successMessage by remember { mutableStateOf<String?>(null) }
  var resendCountdown by remember { mutableIntStateOf(60) }
  var isSubmitting by remember { mutableStateOf(false) }

  val scope = rememberCoroutineScope()

  // Countdown timer for resend OTP
  LaunchedEffect(currentStep, resendCountdown) {
    if (currentStep == 2 && resendCountdown > 0) {
      delay(1000)
      resendCountdown -= 1
    }
  }

  val maskedEmail = remember(emailInput) {
    val atIdx = emailInput.indexOf('@')
    if (atIdx > 1) {
      val prefix = emailInput.substring(0, 1)
      val domain = emailInput.substring(atIdx)
      "$prefix***$domain"
    } else {
      "t***@gmail.com"
    }
  }

  Column(
    modifier = modifier
      .fillMaxSize()
      .background(V1Page),
  ) {
    // Top bar: Back button + Progress text "Bước n/3"
    Row(
      modifier = Modifier
        .fillMaxWidth()
        .background(V1Card)
        .padding(horizontal = 16.dp, vertical = 14.dp),
      horizontalArrangement = Arrangement.SpaceBetween,
      verticalAlignment = Alignment.CenterVertically,
    ) {
      Box(
        modifier = Modifier
          .size(44.dp)
          .clip(RoundedCornerShape(10.dp))
          .clickable {
            if (currentStep > 1) {
              currentStep -= 1
              errorMessage = null
            } else {
              onBack()
            }
          },
        contentAlignment = Alignment.Center,
      ) {
        LineIcon("chevron_left", V1Ink, 20)
      }

      Text(
        text = "Bước $currentStep/3",
        color = V1Muted,
        fontSize = 13.sp,
        fontWeight = FontWeight.Medium,
      )
    }

    Box(
      modifier = Modifier
        .fillMaxWidth()
        .height(1.dp)
        .background(V1Line)
    )

    // Form content
    Column(
      modifier = Modifier
        .weight(1f)
        .fillMaxWidth()
        .verticalScroll(rememberScrollState())
        .padding(16.dp),
      verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
      // Step Title & Description
      Text(
        text = "Quên mật khẩu",
        color = V1Ink,
        fontSize = 22.sp,
        fontWeight = FontWeight.SemiBold,
      )

      Text(
        text = when (currentStep) {
          1 -> "Nhập địa chỉ email của tài khoản để nhận mã xác nhận."
          2 -> "Nhập mã 6 số đã gửi tới Gmail của bạn."
          else -> "Tạo mật khẩu mới cho tài khoản của bạn."
        },
        color = V1Muted,
        fontSize = 13.sp,
        fontWeight = FontWeight.Normal,
      )

      // Main Card for Form Step
      Column(
        modifier = Modifier
          .fillMaxWidth()
          .clip(RoundedCornerShape(16.dp))
          .background(V1Card)
          .border(1.dp, V1Line, RoundedCornerShape(16.dp))
          .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
      ) {
        when (currentStep) {
          1 -> {
            // STEP 1: Enter Email
            Text(
              text = "Địa chỉ Email",
              color = V1Ink,
              fontSize = 13.sp,
              fontWeight = FontWeight.Medium,
            )
            OutlinedTextField(
              value = emailInput,
              onValueChange = {
                emailInput = it
                errorMessage = null
              },
              placeholder = { Text("nhap_email@gmail.com", color = V1Muted, fontSize = 13.sp) },
              singleLine = true,
              keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
              colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = V1Accent,
                unfocusedBorderColor = V1Line,
                focusedContainerColor = V1Card,
                unfocusedContainerColor = V1Card,
              ),
              modifier = Modifier.fillMaxWidth(),
            )

            if (errorMessage != null) {
              Text(
                text = errorMessage!!,
                color = V1Red,
                fontSize = 12.sp,
              )
            }

            Spacer(modifier = Modifier.height(4.dp))

            Button(
              onClick = {
                if (emailInput.isBlank() || !emailInput.contains("@")) {
                  errorMessage = "Vui lòng nhập địa chỉ email hợp lệ."
                } else {
                  currentStep = 2
                  resendCountdown = 60
                  errorMessage = null
                }
              },
              colors = ButtonDefaults.buttonColors(containerColor = V1Accent),
              shape = RoundedCornerShape(10.dp),
              modifier = Modifier.fillMaxWidth().height(44.dp),
            ) {
              Text("Gửi mã OTP", color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Medium)
            }
          }

          2 -> {
            // STEP 2: Enter 6-digit OTP (MOCKUP PRIMARY VIEW)
            Text(
              text = "Đã gửi tới $maskedEmail",
              color = V1Muted,
              fontSize = 12.sp,
            )

            Text(
              text = "Mã xác nhận",
              color = V1Ink,
              fontSize = 13.sp,
              fontWeight = FontWeight.Medium,
            )

            OutlinedTextField(
              value = otpInput,
              onValueChange = {
                if (it.length <= 6 && it.all { ch -> ch.isDigit() }) {
                  otpInput = it
                  errorMessage = null
                }
              },
              placeholder = { Text("Nhập 6 chữ số", color = V1Muted, fontSize = 13.sp) },
              singleLine = true,
              keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
              colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = V1Accent,
                unfocusedBorderColor = V1Line,
                focusedContainerColor = V1Card,
                unfocusedContainerColor = V1Card,
              ),
              modifier = Modifier.fillMaxWidth(),
            )

            Text(
              text = "Mã có hiệu lực theo thời hạn hệ thống.",
              color = V1Muted,
              fontSize = 12.sp,
            )

            if (errorMessage != null) {
              Text(
                text = errorMessage!!,
                color = V1Red,
                fontSize = 12.sp,
              )
            }

            Spacer(modifier = Modifier.height(4.dp))

            // Actions
            Button(
              onClick = {
                if (otpInput.length != 6) {
                  errorMessage = "Vui lòng nhập đủ 6 chữ số mã xác nhận."
                } else {
                  isSubmitting = true
                  scope.launch {
                    delay(300)
                    isSubmitting = false
                    currentStep = 3
                    errorMessage = null
                  }
                }
              },
              colors = ButtonDefaults.buttonColors(containerColor = V1Accent),
              shape = RoundedCornerShape(10.dp),
              modifier = Modifier.fillMaxWidth().height(44.dp),
            ) {
              Text("Xác nhận mã", color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Medium)
            }

            Button(
              onClick = {
                if (resendCountdown == 0) {
                  resendCountdown = 60
                  otpInput = ""
                  errorMessage = null
                }
              },
              enabled = resendCountdown == 0,
              colors = ButtonDefaults.buttonColors(
                containerColor = V1Card,
                contentColor = if (resendCountdown == 0) V1Ink else V1Muted,
              ),
              shape = RoundedCornerShape(10.dp),
              modifier = Modifier
                .fillMaxWidth()
                .height(44.dp)
                .border(1.dp, V1Line, RoundedCornerShape(10.dp)),
            ) {
              Text(
                text = if (resendCountdown > 0) "Gửi lại mã (${resendCountdown}s)" else "Gửi lại mã",
                fontSize = 13.sp,
                fontWeight = FontWeight.Medium,
              )
            }

            Box(
              modifier = Modifier
                .fillMaxWidth()
                .clickable {
                  currentStep = 1
                  errorMessage = null
                }
                .padding(vertical = 8.dp),
              contentAlignment = Alignment.Center,
            ) {
              Text(
                text = "Đổi email",
                color = V1Accent,
                fontSize = 13.sp,
                fontWeight = FontWeight.Medium,
              )
            }
          }

          else -> {
            // STEP 3: Reset Password
            Text(
              text = "Mật khẩu mới",
              color = V1Ink,
              fontSize = 13.sp,
              fontWeight = FontWeight.Medium,
            )
            OutlinedTextField(
              value = newPassword,
              onValueChange = {
                newPassword = it
                errorMessage = null
              },
              placeholder = { Text("Nhập mật khẩu mới", color = V1Muted, fontSize = 13.sp) },
              singleLine = true,
              visualTransformation = PasswordVisualTransformation(),
              keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
              colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = V1Accent,
                unfocusedBorderColor = V1Line,
                focusedContainerColor = V1Card,
                unfocusedContainerColor = V1Card,
              ),
              modifier = Modifier.fillMaxWidth(),
            )

            Text(
              text = "Xác nhận mật khẩu",
              color = V1Ink,
              fontSize = 13.sp,
              fontWeight = FontWeight.Medium,
            )
            OutlinedTextField(
              value = confirmPassword,
              onValueChange = {
                confirmPassword = it
                errorMessage = null
              },
              placeholder = { Text("Nhập lại mật khẩu mới", color = V1Muted, fontSize = 13.sp) },
              singleLine = true,
              visualTransformation = PasswordVisualTransformation(),
              keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
              colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = V1Accent,
                unfocusedBorderColor = V1Line,
                focusedContainerColor = V1Card,
                unfocusedContainerColor = V1Card,
              ),
              modifier = Modifier.fillMaxWidth(),
            )

            if (errorMessage != null) {
              Text(
                text = errorMessage!!,
                color = V1Red,
                fontSize = 12.sp,
              )
            }

            if (successMessage != null) {
              Text(
                text = successMessage!!,
                color = Color(0xFF15803D),
                fontSize = 12.sp,
              )
            }

            Spacer(modifier = Modifier.height(4.dp))

            Button(
              onClick = {
                when {
                  newPassword.length < 6 -> errorMessage = "Mật khẩu phải có ít nhất 6 ký tự."
                  newPassword != confirmPassword -> errorMessage = "Mật khẩu xác nhận không khớp."
                  else -> {
                    successMessage = "Đặt lại mật khẩu thành công!"
                    scope.launch {
                      delay(1200)
                      onComplete()
                    }
                  }
                }
              },
              colors = ButtonDefaults.buttonColors(containerColor = V1Accent),
              shape = RoundedCornerShape(10.dp),
              modifier = Modifier.fillMaxWidth().height(44.dp),
            ) {
              Text("Đặt mật khẩu mới", color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Medium)
            }
          }
        }
      }

      Text(
        text = "Nếu mã sai hoặc hết hạn, thông báo xuất hiện ngay dưới ô nhập.",
        color = V1Muted,
        fontSize = 12.sp,
      )
    }
  }
}
