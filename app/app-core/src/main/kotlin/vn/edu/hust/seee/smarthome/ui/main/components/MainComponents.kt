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
) {
  Row(
    modifier = Modifier
      .fillMaxWidth()
      .clip(RoundedCornerShape(12.dp))
      .background(if (isOn) Color(0xFFF8FCFC) else Color(0xFFF5F7F7))
      .border(1.dp, if (isOn) Color(0xFFB9DEDB) else cardBorder, RoundedCornerShape(12.dp))
      .padding(horizontal = 10.dp, vertical = 3.dp),
    horizontalArrangement = Arrangement.SpaceBetween,
    verticalAlignment = Alignment.CenterVertically,
  ) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.weight(1f)) {
      Box(
        modifier = Modifier
          .size(32.dp)
          .clip(RoundedCornerShape(8.dp))
          .background(Color.White)
          .border(1.dp, cardBorder, RoundedCornerShape(8.dp)),
        contentAlignment = Alignment.Center,
      ) {
        LineIcon(dev.icon, accentCyan, 16)
      }
      Spacer(modifier = Modifier.width(8.dp))
      Column(modifier = Modifier.weight(1f)) {
        Text(
          text = dev.name,
          color = textPrimary,
          fontSize = 13.sp,
          fontWeight = FontWeight.Medium,
          maxLines = 1,
          overflow = TextOverflow.Ellipsis,
        )
        Text(
          text = "${dev.pinInfo} · ${if (isOn) dev.onLabel else dev.offLabel}",
          color = textSecondary,
          fontSize = 11.sp,
          fontWeight = FontWeight.Normal,
          maxLines = 1,
          overflow = TextOverflow.Ellipsis,
        )
      }
    }

    Switch(
      checked = isOn,
      onCheckedChange = onToggle,
      modifier = Modifier.height(34.dp),
      colors = SwitchDefaults.colors(
        checkedThumbColor = Color.White,
        checkedTrackColor = accentCyan,
        uncheckedThumbColor = textSecondary,
        uncheckedTrackColor = cardBorder,
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
