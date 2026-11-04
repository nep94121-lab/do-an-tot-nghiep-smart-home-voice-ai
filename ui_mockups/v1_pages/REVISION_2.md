# Revision 2 — Nhà thông minh

## CHANGELOG

- Bỏ toàn bộ biểu tượng AI trang trí, emoji và glyph giả biểu tượng trên web, PWA, Android; chỉ giữ icon nét mảnh có chức năng.
- Mọi nơi có mô hình 3D chỉ còn **Toàn cảnh**; không còn thẻ góc nhìn theo phòng. Giữ nguyên lõi `house3d.js` và tài sản 3D.
- Đưa chỉ số xử lý giọng nói, tên mô hình và mã phần cứng ra khỏi màn hình người dùng; log/admin giữ dữ liệu chẩn đoán.
- Rút ngắn tiêu đề, nội dung và nhãn nút; sắp lại thao tác theo một hành động chính rõ ràng mỗi nhóm.

## Quy tắc áp dụng chung

**Nguồn và phạm vi.** Spec này dựa đúng vào `DESIGN_SYSTEM.md` và `CURRENT_index_snapshot.html`. Chỉ màn hình web index có snapshot chi tiết. Với phần tử hoặc luồng của màn hình khác không được mô tả dưới đây, **keep as-is**. Không suy đoán API, quyền truy cập hay trạng thái nghiệp vụ. Giữ nguyên đường dẫn và hành vi hiện có khi đổi nhãn hoặc vị trí.

**Màu và chữ.** Dùng Be Vietnam Pro; `#f5f7f7` nền, `#fff` thẻ, `#172b31` chữ, `#687a80` phụ, `#e5ebec` viền, `#087d85` chính, `#e6f3f2` chọn. Body 13px desktop, 13–14px mobile; tiêu đề trang 25–28px desktop/21–24px mobile; heading nhóm 15–17px. Chữ thường 400, nhãn/điều hướng/nút 500, chỉ trạng thái hoặc tiêu đề cần nhấn mới 600; không dùng 700. Dòng nội dung 1.5. Không viết HOA toàn bộ nhãn dài.

**Icon.** Xóa mọi sparkle, robot, brain, magic wand, ngôi sao, tia sáng AI, emoji dùng làm icon, ký tự trang trí và badge gradient/phát sáng. Chỉ dùng SVG line 24×24, `fill="none"`, nét 1.8, đầu/khớp tròn; kích thước hiển thị 18–20px. Icon chỉ đứng cạnh điều hướng chính, hành động mic, bảo mật, thiết bị hoặc thông báo quan trọng. Không thêm icon vào heading mỗi thẻ, chip, dòng chỉ số hay nút đã rõ bằng chữ. Dấu đóng dùng nút có tên truy cập “Đóng”, hình `x` line icon; không dùng ký tự `×`. Chevrons chỉ khi có mở rộng thật. Dot trạng thái 7px là tín hiệu trạng thái, không phải icon trang trí.

**3D.** Trên mọi surface, bỏ tab/ảnh minh họa/góc nhìn `Phòng khách`, `Cửa chính`, `Sân vườn`, `Phòng ngủ` và mọi biến thể góc phòng. Web giữ một viewport `#house3dViewport` cùng camera preset `overview`; bỏ dãy `.cam-Presets` vì chỉ một lựa chọn. Đặt nhãn tĩnh “Toàn cảnh” ở đầu thẻ; mockup chỉ vẽ ô placeholder có nhãn, không vẽ lại nhà. Không sửa `house3d.js`, model hoặc vendor. PWA/Android nếu đã có mô hình hoặc preview, chỉ một thẻ “Toàn cảnh”; nếu không có khu 3D thì **keep as-is**, không thêm mới.

**Thông số.** Ẩn trên màn hình người dùng: SNR, DSP ms, PCM 16kHz, ECAPA/ECAPA-TDNN, F0, RNNoise, WebRTC VAD, Gemini/model names, MQTT, SQLite, Pub/Sub, tool-call latency, audio latency, lead ms, confidence score, mã IR/NEC, chân D/A, tên cảm biến phần cứng, debug chip và raw function call. Dữ liệu có ích cho kỹ thuật chỉ ở Logs/Admin, dưới mục “Chi tiết kỹ thuật” mặc định thu gọn. Giữ trạng thái người dùng hiểu được: kết nối, bật/tắt, nhiệt độ, độ ẩm nếu quyết định tưới, lịch hẹn, quyền, kết quả xác thực. Không ẩn cảnh báo bảo mật hoặc lỗi cần người dùng xử lý.

**Bố cục hành động.** Mỗi nhóm có tối đa một nút primary teal; secondary viền trắng; tertiary dạng chữ. Nút phá hủy ở menu/đáy nhóm, không cạnh primary. Desktop đặt primary trước theo hướng đọc, secondary sau; mobile primary full-width, secondary bên dưới hoặc cạnh khi cả hai ngắn. Focus ring nhìn thấy, vùng chạm ≥40px. Trạng thái disabled phải có lý do bằng chữ gần nút khi cần.

## Web simulator

### 1. `index` / Home

| Icon/đồ họa hiện tại | Quyết định |
| --- | --- |
| Icon nhà ở brand **và** header **và** heading 3D | Giữ một `home` tại brand; bỏ ở header và heading. |
| `bolt` trước “Server: ONLINE (AI)” | Bỏ; thay bằng dot trạng thái và chữ “Đã kết nối” / “Mất kết nối”. |
| `log` trước “Prompt & Schema” | Bỏ cùng nút khỏi Home; chuyển hành động vào Logs/Admin. |
| `user` cạnh “Cấp quyền” | Bỏ; chữ “Vai trò thử” đủ rõ. |
| `refresh` cạnh “Đặt lại” | Bỏ; chuyển “Đặt lại mô phỏng” vào menu phụ. |
| `mic` tại banner thu mẫu, heading voice, nút mic | Chỉ giữ `mic` trong nút thao tác mic; bỏ hai icon trang trí. |
| `home`, `drop`, `thermo`, `snow`, `shield` trong heading/sensor/scenario | Bỏ tại heading và nhãn số liệu; giữ icon thiết bị chỉ trong card nếu nhận diện thiết bị nhanh hơn chữ. |
| `×` trong hai modal | Thay `x` line icon có `aria-label="Đóng"`. |
| Emoji/sparkle/robot/brain/wand/decorative glyph nếu được sinh bởi JS/CSS | Xóa, replacement: **none**. |
| Icon sidebar `home`, `shield`, `cpu`, `log`, `grid`, `qr` | Giữ mỗi mục một icon; bỏ `wave`, `log`, `bolt` ở nhóm tài liệu phụ nếu có. |

**Header/sidebar.** Brand “Nhà thông minh”; dưới brand bỏ “Voice AI & IoT • HUST”. Sidebar chính theo thứ tự: “Tổng quan”, “Xác thực”, “Phần cứng”, “Nhật ký”; nhóm phụ: “Ứng dụng”, “Khách”. Nhóm kiến trúc dự án đưa vào liên kết “Tài liệu” tại đáy sidebar, giữ các URL con trong trang đích hoặc menu hiện có. Bỏ `.sidefoot` chứa NodeMCU, MQTT, ECAPA, F0, Gemini. Header: h1 “Tổng quan”, dòng phụ “Theo dõi và điều khiển ngôi nhà”; phải là trạng thái kết nối. Bỏ `vnClockText`, `indexStrikeBadge`, `indexCountdownBadge` khỏi header; nếu có khóa do thử sai hoặc hẹn giờ đang chạy thì hiển thị thông báo rõ tại nhóm liên quan.

**Nội dung theo thứ tự.** (1) Thẻ “Ngôi nhà” với nhãn “Toàn cảnh”, viewport 3D và hướng dẫn ngắn “Kéo để xoay · Cuộn để phóng to” chỉ ở desktop; bỏ `house3dLabels` nếu chỉ mô tả phòng/góc nhìn, giữ nhãn thiết bị có thao tác. Bỏ OLED HUD mô phỏng và dãy preset phòng. (2) “Thiết bị” grid 7 card: tên, phòng nếu hữu ích, trạng thái Bật/Tắt, toggle; bỏ “7 thiết bị phần cứng”, MQTT/3D realtime. (3) “Giọng nói”: primary “Bắt đầu nói” có mic; secondary “Gửi ngay” chỉ hiện khi đang nghe; trạng thái “Đang nghe”/“Mic tắt”; checkbox “Đọc phản hồi” ở hàng tùy chọn. Chỉ giữ hai dòng hội thoại “Bạn nói” và “Phản hồi”; bỏ dòng `liveToolCall` khỏi Home. Trường nhập placeholder “Nhập lệnh cho ngôi nhà”, nút “Gửi”. (4) “Thử nhanh” tối đa ba lệnh thường: “Bật đèn phòng khách”, “Bật điều hòa và quạt”, “Hẹn tưới cây”; các kịch bản quyền/giọng lạ/nhiễu/chồng giọng chuyển sang trang Xác thực hoặc Logs/Admin tùy mục đích. (5) “Lịch hẹn” và “Tự động hóa” chỉ hiện khi có dữ liệu; trạng thái rỗng gộp một dòng “Chưa có lịch hoặc quy tắc”. Bỏ `eventLog` và “Xóa log” khỏi Home, chuyển sang Nhật ký.

**Cảm biến.** Trên Home chỉ giữ hai giá trị cần hành động: “Nhiệt độ 28°C” và “Độ ẩm đất 55%”; không có slider mô phỏng mặc định. Công cụ thay đổi giá trị thử nghiệm và học lệnh IR đi vào Phần cứng/Wokwi, không nằm cạnh thông tin nhà. Bỏ `sensorHumLabel` nếu ẩm không khí không phục vụ quyết định tại đây. Bỏ mã cảm biến, chân I/O, NEC hex.

**Thu mẫu giọng.** Bỏ banner thu mẫu toàn trang và hai nút giả lập đạt/chưa đạt khỏi Home. Đặt secondary “Đăng ký giọng nói” dẫn đến Xác thực. Trong modal thu mẫu hiện hữu nếu vẫn được mở từ luồng khác: h3 “Đăng ký giọng nói”; câu hướng dẫn một dòng “Đọc câu mẫu để lưu giọng nói”; câu mẫu giữ nội dung cần đọc nhưng bỏ tên server/model; primary “Thu âm”, secondary “Hủy”; thông báo kết quả “Đã lưu mẫu giọng” hoặc “Thử lại”; bỏ text-match %, F0 Hz, SNR khỏi kết quả. Hành vi gửi/kiểm tra hiện có giữ nguyên.

**Nhãn cần xóa rõ ràng.** Xóa từ mặt Home: “SmartHome 3D & Voice AI”, “NodeMCU ESP8266”, “MQTT Pub/Sub”, “Sinh trắc Giọng nói ECAPA-TDNN”, “Giờ VN”, “Sai giọng: 0/5”, “Server: ONLINE (AI)”, “Prompt & Schema”, “Mô Hình Biệt Thự Thông Minh 3D (Three.js WebGL)”, “PCM 16kHz”, “Gemini Live”, “Tool Call”, “Audio Đầu”, “Chênh lệch”, “Function Call”, “SNR Cải thiện”, “Bộ lọc”, “Số người nói”, “Độ trễ DSP”, mọi confidence `(0.xx)`, “IR (D5/D2)”, “NEC 0x…”, “A0 • YL-69”, “D6 • DHT11”. Không hiển thị metric kỹ thuật trong placeholder khi chưa có dữ liệu.

**Nút.** Header chỉ trạng thái và menu phụ. Thẻ giọng nói: `Bắt đầu nói` primary → `Gửi ngay` secondary có điều kiện → `Đọc phản hồi` toggle; dưới transcript: input → `Gửi` secondary. Thẻ nhà: không có nút preset. Dưới danh sách thiết bị: `Đăng ký giọng nói` secondary dẫn Xác thực. Menu phụ: `Đặt lại mô phỏng` destructive với xác nhận hiện có. Font 400 nội dung, 500 nút/nav, 600 h1 và tên section tối đa; không 700. Thành phần chưa đề cập: **keep as-is**.

### 2. `auth_3layer` / Xác thực

| Icon/đồ họa cần bỏ | Thay thế |
| --- | --- |
| Sparkles, robot, brain, wand, emoji hoặc huy hiệu AI ở tiêu đề/bước | **none**. |
| Icon cho từng “lớp”, số bước được vẽ như huy hiệu trang trí | Chữ bước “1. Tài khoản”, “2. Giọng nói”, “3. Quyền truy cập”; không icon. |
| Icon kỹ thuật mic/model/khóa lặp lại trong thẻ chỉ số | **none**; giữ một `mic` tại nút thu âm, `shield` tại điều hướng. |

**3D:** Không có thì **keep as-is**; nếu có preview, chỉ “Toàn cảnh”, xóa preset phòng. **Bỏ:** ECAPA, F0, vector 192-D, confidence, SNR, thời gian DSP, nhãn “4 tầng” khi 3 bước hiển thị, email mẫu trong dropdown nếu chỉ là dữ liệu thử, các chip debug. Giữ tên vai trò “Chủ nhà”, “Gia đình”, “Khách”, “Người lạ” khi cần giải thích quyền. **Thiết kế:** Một thẻ tiến trình ba bước theo thứ tự trên; phần đang thực hiện mở, phần khác thu gọn. Kết quả dùng câu rõ “Đã xác thực”/“Chưa xác thực”, lý do ngắn và cách thử lại. Thông báo khóa tạm thời ở ngay bước giọng nói với thời gian còn lại nếu có. **Nút:** Mỗi bước: primary “Tiếp tục” hoặc “Xác thực giọng nói” → secondary “Thử lại” khi thất bại; “Quay lại” tertiary. Bất kỳ thao tác xóa mẫu/đặt lại nằm cuối trang dưới menu phụ. **Copy:** “Xác thực 3 lớp” → “Xác thực”; “đối chiếu sinh trắc học” → “Xác nhận giọng nói”; câu giải thích tối đa một dòng/bước. Font theo quy tắc chung; heading 600, nhãn 500, nội dung 400. Chi tiết nghiệp vụ khác: **keep as-is**.

### 3. `guest_enroll` / Khách

| Icon/đồ họa cần bỏ | Thay thế |
| --- | --- |
| Sparkles, robot, brain, wand, emoji, glyph trang trí quanh mã QR | **none**. |
| Nhiều icon QR/clock/shield trong cùng thẻ | Giữ `qr` cạnh tiêu đề hoặc CTA quét; thời hạn và quyền ghi bằng chữ, bỏ các icon còn lại. |

**3D:** Không có thì **keep as-is**; preview nếu có chỉ “Toàn cảnh”. **Bỏ:** “QR 10s” như nhãn marketing cố định nếu thời hạn thực khác, SNR/F0/ECAPA, token/ID thô, debug chip, tên backend. **Thiết kế:** Thẻ mã QR có heading “Mời khách”, một dòng “Quét mã để đăng ký”, thời hạn thực “Hết hạn sau …” và danh sách quyền người dùng hiểu được; trên màn khách dùng biểu mẫu tên và bước thu mẫu nếu luồng hiện có yêu cầu. Trạng thái hết hạn: “Mã đã hết hạn” + cách tạo lại. **Nút:** phía chủ nhà primary “Tạo mã mời” → secondary “Sao chép liên kết” sau khi tạo; “Hủy lời mời” tertiary ở cuối. Phía khách primary “Tiếp tục” → secondary “Quay lại”; nút thu âm chính chỉ ở bước thu giọng. **Copy:** bỏ đoạn mô tả cơ chế QR/giọng và số bước kỹ thuật. Font heading 600, nút/nhãn 500, body 400. Phần chưa nêu: **keep as-is**.

### 4. `logs` / Admin

| Icon/đồ họa cần bỏ | Thay thế |
| --- | --- |
| Sparkles, robot, brain, wand, emoji, glyph trạng thái trang trí | **none**. |
| Icon trên từng dòng log, từng metric và mọi chip | **none**; giữ `log` tại nav, `chevron` nếu panel chi tiết mở được. |

**3D:** Không thêm. Nếu hiện có preview, chỉ “Toàn cảnh”. **Bỏ khỏi phần tổng quan:** bộ đếm lặp, chip debug, raw payload, tên model và các trường latency/codec. **Giữ trong “Chi tiết kỹ thuật” mặc định thu gọn:** SNR, DSP ms, PCM 16kHz, ECAPA, F0, model, tool call, MQTT, SQLite, cảm biến/mã IR, request/response và trace hiện có. Dữ liệu lịch sử, quyền, thời gian và kết quả vẫn hiển thị trong bảng chính. **Thiết kế:** tiêu đề “Nhật ký”; hàng lọc `Tất cả / Thiết bị / Giọng nói / Bảo mật`, ô tìm kiếm, bảng `Thời gian | Sự kiện | Kết quả`; mở dòng để đọc chi tiết dễ hiểu, rồi mới tới “Chi tiết kỹ thuật”. Giữ dữ liệu thật, không bịa số. **Nút:** lọc và tìm trước → “Xuất nhật ký” secondary nếu tính năng đã có → “Xóa nhật ký” destructive ở menu phụ, dùng xác nhận hiện có. “Prompt & Schema” đặt trong khu admin/chi tiết kỹ thuật nếu hành động hiện có; label “Cấu hình trợ lý”. **Copy:** tránh “MQTT / Tool Call / Phân quyền” trong heading; dùng loại sự kiện trên filter. Font bảng 400, header 500, tiêu đề 600. Phần chưa nêu: **keep as-is**.

### 5. `wokwi` / Phần cứng

| Icon/đồ họa cần bỏ | Thay thế |
| --- | --- |
| Sparkles, robot, brain, wand, emoji hoặc icon trang trí trên mô phỏng | **none**. |
| Icon CPU/bolt lặp ở mọi heading/chip | Giữ một `cpu` tại nav; heading bằng chữ. |

**3D:** Nếu có link/preview nhà, nhãn “Toàn cảnh” duy nhất; không góc phòng. Giữ `#circuitStage` placeholder trong mockup và phần mô phỏng mạch hiện có. **Bỏ khỏi header:** ESP8266, pin D/A, NEC hex, MQTT, tần số lấy mẫu, latency, debug chips. **Giữ trong panel “Thông số kỹ thuật” thu gọn:** tên chân, mã IR, dữ liệu cảm biến thô, trạng thái kết nối giao thức, các điều khiển giả lập cần cho demo. **Thiết kế:** heading “Phần cứng”, thẻ “Mạch mô phỏng”, bên cạnh “Thiết bị kết nối” với trạng thái dễ hiểu; cảm biến thể hiện nhiệt độ/độ ẩm đất, không hiện mã linh kiện. **Nút:** primary “Chạy mô phỏng” nếu có thao tác hiện hữu → secondary “Dừng” khi chạy → tertiary “Thông số kỹ thuật”; học lệnh IR nằm trong panel kỹ thuật. **Copy:** “Mạch phần cứng ESP” → “Phần cứng”; “Đồng bộ MQTT” → “Đã kết nối” khi đúng trạng thái. Font theo quy tắc chung. Phần chưa nêu: **keep as-is**.

## PWA `mobile_app`

### 6. Home

| Icon/đồ họa cần bỏ | Thay thế |
| --- | --- |
| Sparkles/robot/brain/wand/emoji AI trong greeting, trợ lý, trạng thái | **none**. |
| Icon mỗi heading, chip và metric | **none**; giữ `home` ở bottom nav và icon line riêng cho thiết bị có lợi cho nhận diện. |
| Nhiều mic trên cùng màn | Một `mic` trong primary “Nói lệnh”. |

**3D:** Nếu có thẻ nhà, chỉ “Toàn cảnh”, một preview/placeholder; bỏ carousel phòng. Nếu không có 3D, **keep as-is**. **Bỏ:** SNR, DSP ms, PCM, ECAPA, model, debug chips, số metric kỹ thuật trên Home. **Thiết kế:** header “Nhà của tôi” + trạng thái kết nối; thẻ 3D nếu có; “Thiết bị” dạng card 2 cột; trạng thái nhiệt độ và độ ẩm đất một dòng nếu dữ liệu có; lịch sắp tới chỉ khi có. **Nút:** primary full-width “Nói lệnh”; secondary “Nhập lệnh” ngay dưới; toggle trong card thiết bị. **Copy:** subtitle tối đa một câu, không lặp “AI”, “thông minh” nhiều lần. Font h1 600, section 600 tối đa, button 500, body 400. Còn lại **keep as-is**.

### 7. Thiết bị và chi tiết thiết bị

| Icon/đồ họa cần bỏ | Thay thế |
| --- | --- |
| Emoji đồ gia dụng, sparkle, icon kép trên card | Một icon line đúng thiết bị (`lamp`, `fan`, `snow`, `door`, `drop`) hoặc **none** nếu tên đủ rõ. |
| Icon ở từng hàng thông số | **none**. |

**3D:** Preview nếu có chỉ “Toàn cảnh”; không tab phòng. **Bỏ:** pin, mã IR, MQTT, debug, latency, chip “AI”. **Thiết kế:** mỗi card tên + phòng + trạng thái + toggle; chi tiết chỉ các điều khiển có thể tác động và trạng thái quan trọng. **Nút:** toggle là hành động trực tiếp; trong chi tiết, primary “Lưu” nếu có form thay đổi → secondary “Hủy”; hành động nguy hiểm tách cuối. **Copy:** “Trạng thái thiết bị” → “Thiết bị”; Bật/Tắt rõ. Font theo quy tắc chung; còn lại **keep as-is**.

### 8. Giọng nói

| Icon/đồ họa cần bỏ | Thay thế |
| --- | --- |
| Robot, brain, sparkle, waveform trang trí, emoji trợ lý | **none**. |
| Icon mic lặp ở heading/hội thoại/nút | Chỉ giữ `mic` trong nút ghi âm. |

**3D:** Không thêm; nếu preview hiện có, chỉ “Toàn cảnh”. **Bỏ:** PCM 16kHz, model names, SNR/DSP ms, confidence, function call, raw transcript debug. **Thiết kế:** trạng thái “Sẵn sàng”/“Đang nghe”/“Đang xử lý”; transcript hai nhãn “Bạn nói”, “Phản hồi”; tùy chọn “Đọc phản hồi”. Lỗi giọng nói nêu việc cần làm, không nêu thuật toán. **Nút:** primary full-width “Bắt đầu nói” → khi nghe đổi “Dừng nghe”; secondary “Nhập lệnh”; gửi text ở cuối input. **Copy:** hướng dẫn một câu “Nói điều bạn muốn làm trong nhà.” Font theo quy tắc chung; còn lại **keep as-is**.

### 9. Xác thực / Khách / Lịch sử / Cài đặt (các màn key còn lại)

| Icon/đồ họa cần bỏ | Thay thế |
| --- | --- |
| Tất cả sparkle, robot, brain, wand, emoji, glyph trang trí; icon mỗi bước hoặc dòng log | **none**. |
| Icon bottom nav dư hoặc không có đích chức năng | Chỉ giữ icon line cho `Nhà`, `Thiết bị`, `Giọng nói`, `Lịch sử`, `Tài khoản` nếu đúng các đích hiện có; mục không tồn tại **keep as-is**, không tạo route. |

**3D:** Không thêm; preview hiện có chỉ “Toàn cảnh”. **Bỏ:** toàn bộ metric kỹ thuật khỏi xác thực/khách/cài đặt; log mobile chỉ tóm tắt thời gian, sự kiện, kết quả; chi tiết kỹ thuật chỉ admin có quyền. **Thiết kế:** Xác thực dùng 3 bước và kết quả như web; Khách dùng QR + hạn + quyền; Lịch sử dùng danh sách một dòng/sự kiện; Cài đặt nhóm theo tài khoản, thông báo, quyền. **Nút:** Xác thực “Tiếp tục”/“Thử lại”; Khách “Tạo mã mời”/“Sao chép liên kết”; Lịch sử filter trước, không có CTA mặc định; Cài đặt “Lưu” chỉ khi có thay đổi. Primary full-width ở đáy form, secondary dưới primary, destructive cuối trang. **Copy:** nhãn tối đa 2–4 từ, helper tối đa 1 câu; font theo quy tắc chung. Phần chưa nêu: **keep as-is**.

## Android Compose

### 10. Home

| Icon/đồ họa cần bỏ | Thay thế |
| --- | --- |
| Sparkles, robot, brain, wand, emoji, AI badge, glyph trang trí | **none**. |
| Icon trong mọi heading/chip/card | Chỉ giữ icon line một lần cho thiết bị nếu cần; `Home` ở bottom nav. |

**3D:** Nếu Android có preview, chỉ “Toàn cảnh”; không có preview thì **keep as-is**. **Bỏ:** SNR, DSP ms, PCM, ECAPA, model name, debug chips, chip trạng thái trùng header. **Thiết kế Compose:** nền `#f5f7f7`; top bar “Nhà của tôi” + trạng thái kết nối; thẻ tổng quan nếu có; grid thiết bị; thẻ hành động giọng nói; lịch sắp tới chỉ khi có. Thẻ trắng viền 1px `#e5ebec`, radius 16dp; outer padding 16dp, gap 12dp. **Nút:** primary “Nói lệnh” full-width → secondary “Nhập lệnh”; toggle trong card. Font Be Vietnam Pro 400/500/600; h1 22sp/600, section 16sp/600, body 14sp/400, button 14sp/500. Thành phần khác: **keep as-is**.

### 11. Auth

| Icon/đồ họa cần bỏ | Thay thế |
| --- | --- |
| Sparkles/robot/brain/wand/emoji; icon trang trí cho 3 lớp; các badge mô hình | **none**; giữ `shield` trong bottom nav nếu tab này hiện có, `mic` trong nút ghi âm. |

**3D:** Không thêm; preview có sẵn chỉ “Toàn cảnh”. **Bỏ:** confidence, F0, SNR, ECAPA, DSP, tên model, debug. **Thiết kế:** tiêu đề “Xác thực”; ba bước Tài khoản → Giọng nói → Quyền truy cập, chỉ bước hiện tại mở; kết quả một câu và lời nhắc xử lý. Không hiện số lần thử liên tục; chỉ hiện khóa tạm thời khi phát sinh. **Nút:** primary “Tiếp tục” hoặc “Xác thực giọng nói” → secondary “Thử lại” khi cần → tertiary “Quay lại”; destructive cuối màn. Typography như Android Home; còn lại **keep as-is**.

### 12. Voice

| Icon/đồ họa cần bỏ | Thay thế |
| --- | --- |
| Robot avatar, sparkle, brain, waveform trang trí, emoji hội thoại | **none**. |
| Icon mic ở cả heading và nhiều CTA | Một `mic` trong primary; `volume` chỉ cạnh toggle phát phản hồi nếu chữ không đủ. |

**3D:** Không thêm; preview có sẵn chỉ “Toàn cảnh”. **Bỏ:** PCM 16kHz, ECAPA, Gemini/model, SNR/DSP ms, function call, confidence, debug. **Thiết kế:** trạng thái nghe ở đầu; hai khối “Bạn nói” và “Phản hồi”; ô nhập lệnh dưới hội thoại; switch “Đọc phản hồi”. **Nút:** primary “Bắt đầu nói”/“Dừng nghe” full-width; secondary “Gửi” chỉ cạnh ô nhập khi có text; không hiện “Gửi ngay” khi mic chưa nghe. Lỗi hiển thị bằng câu Việt ngắn. Typography như Android Home; còn lại **keep as-is**.

### Bottom navigation Android

| Mục | Icon line | Nhãn | Quy tắc |
| --- | --- | --- | --- |
| Home | `home` | Nhà | Đầu tiên, selected dùng `#e6f3f2` + `#087d85`. |
| Devices | `grid` | Thiết bị | Thứ hai. |
| Voice | `mic` | Giọng nói | Thứ ba. |
| Auth | `shield` | Xác thực | Thứ tư nếu đây là tab hiện có. |
| History/account | `clock` hoặc `user` | Lịch sử hoặc Tài khoản | Thứ năm theo đích đang tồn tại; **keep as-is** nếu app không có tab thứ năm. |

Không dùng emoji, sparkle, robot, brain, wand, badge số giả hoặc icon 3D trong bottom nav. Mỗi mục có đúng một icon 20dp và nhãn 11sp/500; nền trắng, viền trên `#e5ebec`; không tô cả thanh. Không tạo route mới chỉ để khớp bảng này. Các tab ngoài những mục nêu ở trên: **keep as-is**.

## Bàn giao mockup

`rev2_01_home.html` là mẫu desktop responsive cho Home. Nó chỉ dùng placeholder `#house3dViewport` có nhãn “Toàn cảnh”; không vẽ hoặc thay tài sản 3D. HTML là bản trình bày tĩnh với vài toggle demo, không phải mã tích hợp. Khi Antigravity triển khai, giữ các ID/hành vi thực tế cần thiết nhưng áp dụng đúng thứ tự, nhãn, trạng thái và độ ưu tiên ở trên.
