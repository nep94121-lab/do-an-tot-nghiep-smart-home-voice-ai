# DESIGN_SYSTEM.md — Nhà thông minh (v1 light)

Nguồn khôi phục từ `REVISION_2.md` + `rev2_01_home.html` (bản gốc `ui_mockups` không còn trên đĩa). Antigravity/Codex dùng file này làm chuẩn.

## Brand & tone
- Tên sản phẩm: Nhà thông minh
- Tone: tối giản, rõ ràng, tiếng Việt, không AI-slop
- Font: Be Vietnam Pro (Google Fonts)

## Color tokens
| Token | Hex | Dùng |
| --- | --- | --- |
| `--page` | `#f5f7f7` | nền trang |
| `--card` | `#fff` | thẻ / panel |
| `--ink` | `#172b31` | chữ chính |
| `--muted` | `#687a80` | chữ phụ |
| `--line` | `#e5ebec` | viền |
| `--accent` | `#087d85` | primary / teal cổ vịt |
| `--accent-soft` | `#e6f3f2` | nền chọn / soft |
| Danger | `#c0392b` / soft `#fdecea` | lockdown / lỗi nặng |
| Warning | `#d97706` / soft `#fff7ed` | reconnect banner |
| Success | `#15803d` / soft `#ecfdf5` | khôi phục kết nối |

## Type scale
- Body: 13px desktop, 13–14px mobile; line-height 1.5
- Page title: 25–28px desktop / 21–24px mobile; weight 600
- Group heading: 15–17px; weight 600
- Labels/nav/buttons: 500
- Body: 400
- Tránh weight 700 và HOA toàn bộ nhãn dài

## Icon rules
- Chỉ SVG line 24×24, `fill="none"`, stroke 1.8, round caps; hiển thị 18–20px
- Cấm: sparkles, robot, brain, magic wand, emoji-as-icon, glyph trang trí, badge gradient
- Icon chỉ cạnh nav chính, mic, bảo mật, thiết bị, thông báo quan trọng
- Đóng = nút “Đóng” + line `x`; không dùng `×` trang trí

## 3D
- Chỉ **Toàn cảnh**; không tab góc phòng
- Giữ `house3d.js` / model; mockup dùng placeholder có nhãn nếu cần

## Components
- Panel: radius 16, border `--line`, shadow nhẹ `0 6px 24px rgba(31,58,62,.045)`
- Primary button: nền `--accent`, chữ trắng
- Secondary: viền `--line`, nền trắng
- Tertiary: chữ
- Status pill: border + dot 7px
- Focus ring: `#86c9cc` 3px
- Touch target ≥ 40px

## Error / empty / banner
- Đồng bộ light theme + accent
- Banner reconnect: vàng-cam đầu trang; success xanh lá 2s rồi ẩn
- Lockdown: modal đỏ nổi, yêu cầu mật khẩu chủ nhà / OTP
