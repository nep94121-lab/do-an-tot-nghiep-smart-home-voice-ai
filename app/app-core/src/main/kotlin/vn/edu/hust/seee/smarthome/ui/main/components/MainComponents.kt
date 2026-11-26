package vn.edu.hust.seee.smarthome.ui.main.components

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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import vn.edu.hust.seee.smarthome.ui.main.LineIcon
import vn.edu.hust.seee.smarthome.ui.main.models.HardwareDevice

@Composable
fun AccountMenuRow(
  title: String,
  subtitle: String,
  textPrimary: Color,
  textSecondary: Color,
  cardBorder: Color,
  onClick: () -> Unit,
) {
  Row(
    modifier = Modifier
      .fillMaxWidth()
      .clip(RoundedCornerShape(12.dp))
      .background(Color(0xFFF5F7F7))
      .border(1.dp, cardBorder, RoundedCornerShape(12.dp))
      .clickable { onClick() }
      .padding(horizontal = 14.dp, vertical = 12.dp),
    horizontalArrangement = Arrangement.SpaceBetween,
    verticalAlignment = Alignment.CenterVertically,
  ) {
    Column(modifier = Modifier.weight(1f)) {
      Text(
        text = title,
        color = textPrimary,
        fontSize = 14.sp,
        fontWeight = FontWeight.Medium,
      )
      Text(
        text = subtitle,
        color = textSecondary,
        fontSize = 12.sp,
        fontWeight = FontWeight.Normal,
      )
    }
    LineIcon("chevron_right", textSecondary, 16)
  }
}

@Composable
fun DeviceRowCard(
  dev: HardwareDevice,
  isOn: Boolean,
  accentCyan: Color,
  cardBorder: Color,
  textPrimary: Color,
  textSecondary: Color,
  onToggle: (Boolean) -> Unit,
  boardOnline: Boolean = true,
  lastSeenVi: String = "",
  onOfflineTap: () -> Unit = {},
) {
  val offlineRed = Color(0xFFC83E3B)
  val offlineBg = Color(0xFFFEF5F5)
  val offlineBorder = Color(0xFFEBC8C7)
  val rowBg = when {
    !boardOnline -> offlineBg
    isOn -> Color(0xFFF8FCFC)
    else -> Color(0xFFF5F7F7)
  }
  val rowBorder = when {
    !boardOnline -> offlineBorder
    isOn -> Color(0xFFB9DEDB)
    else -> cardBorder
  }
  Row(
    modifier = Modifier
      .fillMaxWidth()
      .clip(RoundedCornerShape(12.dp))
      .background(rowBg)
      .border(1.dp, rowBorder, RoundedCornerShape(12.dp))
      .then(if (!boardOnline) Modifier.clickable { onOfflineTap() } else Modifier)
      .padding(horizontal = 10.dp, vertical = 5.dp),
    horizontalArrangement = Arrangement.SpaceBetween,
    verticalAlignment = Alignment.CenterVertically,
  ) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.weight(1f)) {
      Box(
        modifier = Modifier
          .size(32.dp)
          .clip(RoundedCornerShape(8.dp))
          .background(Color.White)
          .border(1.dp, rowBorder, RoundedCornerShape(8.dp)),
        contentAlignment = Alignment.Center,
      ) {
        LineIcon(dev.icon, if (boardOnline) accentCyan else offlineRed, 16)
      }
      Spacer(modifier = Modifier.width(8.dp))
      Column(modifier = Modifier.weight(1f)) {
        Row(
          verticalAlignment = Alignment.CenterVertically,
          horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
          Text(
            text = dev.name,
            color = textPrimary,
            fontSize = 13.sp,
            fontWeight = FontWeight.Medium,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f, fill = false),
          )
          if (!boardOnline) {
            Text(
              text = "Mất kết nối",
              color = offlineRed,
              fontSize = 10.sp,
              fontWeight = FontWeight.SemiBold,
              maxLines = 1,
              modifier = Modifier
                .clip(RoundedCornerShape(999.dp))
                .background(Color(0xFFFDECEC))
                .border(1.dp, offlineBorder, RoundedCornerShape(999.dp))
                .padding(horizontal = 6.dp, vertical = 1.dp),
            )
          }
        }
        Text(
          text = "${dev.pinInfo} · ${if (isOn) dev.onLabel else dev.offLabel}",
          color = textSecondary,
          fontSize = 11.sp,
          fontWeight = FontWeight.Normal,
          maxLines = 1,
          overflow = TextOverflow.Ellipsis,
        )
        if (!boardOnline) {
          Text(
            text = "Lần cuối: ${lastSeenVi.ifBlank { "--" }}",
            color = offlineRed,
            fontSize = 10.sp,
            fontWeight = FontWeight.Normal,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
          )
        }
      }
    }

    Switch(
      checked = isOn,
      onCheckedChange = { newVal ->
        if (boardOnline) onToggle(newVal) else onOfflineTap()
      },
      enabled = boardOnline,
      modifier = Modifier.height(34.dp),
      colors = SwitchDefaults.colors(
        checkedThumbColor = Color.White,
        checkedTrackColor = accentCyan,
        uncheckedThumbColor = textSecondary,
        uncheckedTrackColor = cardBorder,
        disabledCheckedThumbColor = Color.White.copy(alpha = 0.7f),
        disabledCheckedTrackColor = accentCyan.copy(alpha = 0.35f),
        disabledUncheckedThumbColor = textSecondary.copy(alpha = 0.55f),
        disabledUncheckedTrackColor = cardBorder.copy(alpha = 0.6f),
      ),
    )
  }
}

@Composable
fun BottomTabItem(
  label: String,
  iconKind: String,
  selected: Boolean,
  activeColor: Color,
  onClick: () -> Unit,
  modifier: Modifier = Modifier,
) {
  Column(
    modifier = modifier
      .clip(RoundedCornerShape(12.dp))
      .background(if (selected) Color(0xFFE6F3F2) else Color.Transparent)
      .clickable { onClick() }
      .padding(vertical = 6.dp, horizontal = 4.dp),
    horizontalAlignment = Alignment.CenterHorizontally,
    verticalArrangement = Arrangement.spacedBy(3.dp),
  ) {
    LineIcon(
      kind = iconKind,
      tint = if (selected) activeColor else Color(0xFF687A80),
      sizeDp = 20,
    )
    Text(
      text = label,
      color = if (selected) activeColor else Color(0xFF687A80),
      fontSize = 11.sp,
      fontWeight = FontWeight.Medium,
      maxLines = 1,
    )
  }
}

@Composable
fun TierChip(
  label: String,
  selected: Boolean,
  activeColor: Color,
  onClick: () -> Unit,
  modifier: Modifier = Modifier,
) {
  Box(
    modifier = modifier
      .height(34.dp)
      .clip(RoundedCornerShape(10.dp))
      .background(if (selected) Color(0xFFE6F3F2) else Color(0xFFF5F7F7))
      .border(1.dp, if (selected) activeColor else Color(0xFFE5EBEC), RoundedCornerShape(10.dp))
      .clickable { onClick() }
      .padding(horizontal = 10.dp),
    contentAlignment = Alignment.Center,
  ) {
    Text(
      text = label,
      color = if (selected) activeColor else Color(0xFF687A80),
      fontSize = 12.sp,
      fontWeight = FontWeight.Medium,
      maxLines = 1,
    )
  }
}
