# Thiết kế các trang mới — Nhà thông minh

Phạm vi: chỉ các trang và trạng thái mới trong danh sách dưới đây. HTML đi kèm là mẫu tĩnh, không thay thế luồng, API, quyền, bộ đếm hay tài sản hiện có. Mọi hành vi chưa chỉ rõ giữ nguyên. Không hiển thị mật khẩu, OTP thật, token, mã phần cứng hoặc chỉ số chẩn đoán trên giao diện. Không tự suy ra quyền từ dữ liệu phía client.

## Quy chuẩn chung

- Dùng Be Vietnam Pro; nền `#f5f7f7`, thẻ `#fff`, chữ `#172b31`, chữ phụ `#687a80`, viền `#e5ebec`, primary `#087d85`, chọn `#e6f3f2`. Cảnh báo `#d97706/#fff7ed`, nguy hiểm `#c0392b/#fdecea`, thành công `#15803d/#ecfdf5`.
- Thẻ trắng bo 16px, viền 1px, bóng `0 6px 24px rgba(31,58,62,.045)`. Desktop nội dung tối đa 560px cho trang lỗi; mobile padding 16px, gap 12px, vùng chạm tối thiểu 40px. Body 13px desktop, 14px mobile, line-height 1.5. H1 26px desktop/22px mobile, weight 600. Heading nhóm 16px/600. Nút và nhãn 500.
- Nút chính teal, nút phụ trắng viền, thao tác ít ưu tiên là chữ. Một primary mỗi nhóm; mobile full-width. Focus ring 3px `#86c9cc`; disabled có lý do gần nút. Trạng thái dùng chữ cùng chấm tròn 7px, không chỉ màu.
- Icon SVG nét Lucide 24×24, `fill=none`, stroke 1.8, đầu/khớp tròn, hiển thị 18–20px; chỉ dùng ở điều hướng, mic, bảo mật, thiết bị, thông báo quan trọng. Không emoji, glyph trang trí, robot, sparkle, gradient badge. Nút đóng có `aria-label="Đóng"` và SVG `x`.
- Tất cả copy tiếng Việt. Trang cần báo lỗi đọc được khi không có JavaScript; trạng thái động dùng `aria-live` phù hợp. Không ghi secret/OTP vào log. Nếu có 3D, đúng một thẻ “Toàn cảnh”, chỉ placeholder trong mockup; tích hợp dùng tài sản hiện hữu.
- Responsive: desktop thẻ giữa trang, có khoảng trống hai bên; dưới 600px nội dung tràn chiều ngang an toàn, nút xếp dọc. Mobile shell dùng `min-height:100dvh` với fallback `100vh`, `viewport-fit=cover`; thanh tab có `padding-bottom:env(safe-area-inset-bottom)` và nằm trong viewport động, không đặt dưới thanh công cụ Samsung Internet. Phần cuộn nằm giữa header và tab; khi bàn phím mở, form/sheet cuộn được.

## 01 · Mất kết nối — `np_01_offline.html`

- **Bố cục:** Trang lỗi giữa màn hình; brand nhỏ, icon `wifi-off`, H1 “Mất kết nối tới Máy chủ Nhà thông minh”, câu giải thích, thẻ trạng thái độc lập, dòng đếm thử lại, hai nút.
- **Copy/thành phần:** “Không thể cập nhật trạng thái ngôi nhà lúc này.”; nhãn “Trạng thái mạch”; nếu có trạng thái cuối được xác thực: “Mạch đang tự chạy ở Chế độ Độc lập Offline — tự động khóa Cửa chính và bật Còi báo động.” Thêm thời điểm cập nhật cuối. Nếu không có dữ liệu đáng tin: “Chưa thể xác nhận trạng thái mạch. Kiểm tra trực tiếp tại nhà.” Không mặc định khẳng định cửa/còi đã chuyển trạng thái.
- **Nút:** primary “Thử kết nối lại” gọi thử ngay; secondary “Chuyển sang Server Dự phòng” chỉ hiển thị khi có URL dự phòng đã cấu hình, điều hướng sang URL đó sau xác nhận nếu cần. Không hardcode Vercel/LAN làm đích trong mockup.
- **Trạng thái:** offline mạng, server không phản hồi, đang thử (“Đang thử lại sau 4 giây”), thành công chuyển về URL ban đầu; thất bại tăng thời gian thử. Trạng thái mạch là dữ liệu cuối, không là trạng thái thời gian thực. Empty/error: thiếu cache vẫn hiển thị trang tĩnh và câu chưa thể xác nhận.
- **sw.js:** precache phiên bản của offline HTML, CSS/font fallback nội tuyến và các tài sản shell cần thiết; navigation request same-origin dùng network-first, khi fetch lỗi trả offline page từ cache với `Content-Type:text/html; charset=utf-8`. Không cache API, HTML chứa thông tin cá nhân hoặc phản hồi auth như dữ liệu thật. Cài/activate dọn cache phiên bản cũ; không chặn luồng POST. Service Worker không thể biến lần truy cập đầu chưa cài đặt, URL/IP khác origin, hoặc server localhost tắt trước khi page/SW được cài thành trang offline; các trường hợp đó cần host/cài PWA/đường mở phù hợp. Khi page offline đã mở, dùng `online` + thử fetch same-origin nhẹ; nút thử ngay; tự thử sau 3–5 giây và tránh vòng lặp tải vô hạn.
- **Responsive/icon:** `wifi-off` duy nhất cạnh thông báo; hai nút xếp dọc mobile.

## 02 · 404 — `np_02_404.html`

- **Bố cục:** Thẻ lỗi desktop giữa trang; nhãn “404”, H1 “Không tìm thấy trang”, mô tả ngắn, hai CTA.
- **Copy:** “Trang bạn tìm không tồn tại hoặc đã chuyển địa chỉ.”
- **Nút:** primary “Về Trang chủ” tới `/`; secondary “Mở Ứng dụng Điện thoại” tới `/app`. Link thật, hoạt động không JS.
- **Trạng thái/variant:** URL lạ và route đã chuyển đều dùng cùng copy; không in đường dẫn người dùng nhập nếu có nguy cơ chứa token. Empty/error: nếu shell thiếu dữ liệu vẫn giữ CTA. Icon: `file-question` line cạnh nhãn 404, không thêm minh họa.
- **Responsive:** tối đa 560px, mobile nút full-width.

## 03 · 500/503 — `np_03_500.html`

- **Bố cục:** Cùng khung lỗi 404; icon `server-off`, status code động, H1 “Hệ thống đang bận”, mô tả và hai CTA.
- **Copy:** “Máy chủ chưa thể xử lý yêu cầu. Vui lòng thử lại sau ít phút.” Không đổ lỗi chắc chắn cho dịch vụ cụ thể. 500: “Lỗi hệ thống”; 503: “Dịch vụ tạm gián đoạn”.
- **Nút:** primary “Tải lại trang”; secondary “Điều khiển cơ bản” chỉ khi chế độ cơ bản thực sự có sẵn, tới luồng hiện hữu, không bỏ qua xác thực/quyền. Nếu không sẵn có, secondary đổi “Về Trang chủ” nếu truy cập được, hoặc ẩn với lý do “Điều khiển cơ bản chưa khả dụng”.
- **Trạng thái:** đang tải lại; lỗi lặp giữ trang, không tự reload liên tục. Empty/error: trang 500 phải render được độc lập khỏi dữ liệu ứng dụng. Icon `server-off`. Responsive như 404.

## 04 · QR hết hạn/đã dùng — `np_04_qr_expired.html`

- **Bố cục:** Thẻ hẹp giữa trang, icon `qr-code`, nhãn “Lời mời không còn hiệu lực”, H1 phản ánh lý do; hướng dẫn và CTA.
- **Copy:** khi hết hạn: “Mã QR này đã hết hạn.”; khi đã dùng: “Mã QR này đã được sử dụng.”; khi không thể phân biệt: “Mã QR này đã hết hạn hoặc đã được sử dụng một lần.” Hướng dẫn “Vui lòng nhờ Chủ nhà tạo mã mời mới rồi quét lại.”
- **Nút:** primary “Quét mã mới” mở scanner hiện hữu hoặc `/app` theo surface; secondary “Nhập mã mới” chỉ nếu luồng nhập mã đã tồn tại. Không hiện “Tạo mã mới” cho khách.
- **Trạng thái/variant:** expired, used, invalid/unknown; không hiện token, thời điểm hay người đã dùng nếu chưa có dữ liệu/quyền. Empty/error: nếu kiểm tra thất bại do mạng, chuyển trạng thái mất kết nối, không kết luận mã đã dùng. Responsive nút dọc; icon QR duy nhất.

## 05 · 403 — `np_05_403.html`

- **Bố cục:** Thẻ lỗi với icon `shield-off`, role pill “Khách · Cấp 3” lấy từ phiên đăng nhập, H1 theo nguyên nhân, lời giải thích, hành động.
- **Copy:** thiếu quyền: “Bạn không có quyền điều khiển thiết bị này.”; khách hết hạn: “Thời hạn truy cập dành cho Khách của bạn đã kết thúc.” Không nêu cấp nếu phiên không có vai trò đáng tin; khi đó chỉ “Không đủ quyền truy cập”.
- **Nút:** nếu hết hạn và có luồng yêu cầu: primary “Yêu cầu Chủ nhà gia hạn”; nếu thiếu quyền: primary “Quay về Nhà”; secondary “Đăng nhập tài khoản khác” tới login hiện hữu. Không cung cấp lối chuyển thành Chủ nhà bằng cách sửa client.
- **Trạng thái/variant:** thiếu quyền, hết hạn, chưa đăng nhập. Yêu cầu gia hạn đang gửi/thành công/lỗi nếu có API; nếu không có API, dùng hướng dẫn “Liên hệ Chủ nhà để được gia hạn” thay nút gửi. Empty/error: thiếu chi tiết quyền không bịa role hoặc thiết bị. Responsive nút dọc.

## 06 · Khóa an ninh — `np_06_lockdown.html`

- **Bố cục:** Overlay mờ che toàn màn, dialog rộng tối đa 460px, viền đỏ nhạt, icon `shield-alert`, H1 “Cảnh báo an ninh”, thông tin rõ về khóa và còi, bộ chọn phương thức, ô nhập, CTA. Không có nút đóng bỏ qua nếu hệ thống thật bắt buộc xác minh; có lối “Về Trang chủ” chỉ nếu chính sách hiện hữu cho phép, nhưng không mở lại điều khiển giọng.
- **Copy:** “Phát hiện 3 lần xác thực giọng nói thất bại. Điều khiển giọng nói đã bị khóa và còi báo động đã bật.” Chỉ hiển thị vế còi khi server xác nhận `alarm_siren=ON`; nếu không: “Đang kiểm tra trạng thái còi báo động.” Label “Mật khẩu Chủ nhà” hoặc “Mã OTP Gmail”; helper “Xác minh để mở khóa và tắt còi.”
- **Nút:** primary “Xác minh và mở khóa”; secondary chuyển “Dùng mã OTP”/“Dùng mật khẩu”; nếu OTP cần gửi, hành động “Gửi mã” theo luồng hiện hữu. Không lưu giá trị nhập trong mockup hoặc log.
- **Trạng thái/variant:** 3/3 thất bại, chờ OTP, đang xác minh, sai mã, hết hạn mã, thành công; sau thành công dialog đóng và trạng thái thiết bị đồng bộ từ server. Empty/error: nếu không gửi được OTP, cho thử lại/đổi phương thức, vẫn khóa. Khi mạng mất, giữ khóa và chuyển hướng xử lý kết nối. Responsive dialog margin 16px, nội dung cuộn, bàn phím không che CTA.

## 07 · Quyền micro/HTTPS — `np_07_mic_permission.html`

- **Bố cục:** Popup/dialog trên shell, icon `mic-off`, H1 “Chưa thể dùng micro”, hướng dẫn 2 bước ngắn dạng chữ, vùng nguyên nhân, CTA.
- **Copy từ chối:** “Bạn đã chặn quyền micro. Mở cài đặt trang trong trình duyệt, chọn Micro → Cho phép, rồi thử lại.” **HTTPS:** “Trình duyệt cần kết nối an toàn để dùng micro. Mở ứng dụng qua HTTPS.” Không hướng dẫn biểu tượng ổ khóa cố định vì giao diện trình duyệt khác nhau; câu “Chạm biểu tượng cài đặt cạnh địa chỉ trang” chỉ khi phù hợp.
- **Nút:** primary “Thử lại” gọi xin quyền khi HTTPS hợp lệ; khi HTTP không an toàn, primary “Mở bản HTTPS” chỉ nếu URL tin cậy đã cấu hình, secondary “Đóng”. Không dựng URL từ host tùy ý. Empty/error: không có URL HTTPS thì hiển thị “Liên hệ Chủ nhà để nhận liên kết an toàn” và ẩn nút mở link.
- **Trạng thái:** chưa hỏi, từ chối, thiếu thiết bị, HTTP, đang yêu cầu, đã cho phép (đóng popup, tiếp tục tác vụ). Icon `mic-off` duy nhất. Mobile popup cuộn và safe-area.

## 08 · Mất WebSocket — `np_08_ws_banner.html`

- **Bố cục:** Banner ngang ở đầu vùng nội dung, nằm sau header cố định nếu có và trước mọi thẻ; trên shell tối giản có tiêu đề “Nhà của tôi”. Không che tab/mobile controls.
- **Copy:** reconnect: “Mất kết nối thời gian thực tới ngôi nhà. Đang kết nối lại (lần 1/5)…”. Hết lượt: “Chưa khôi phục kết nối. Thử lại để cập nhật trạng thái.” Thành công: “Đã khôi phục kết nối.”
- **Nút:** secondary compact “Kết nối ngay” thử lại, disable trong lúc đang thử và ghi lý do. Không dùng icon emoji; `wifi-off` cho cảnh báo, `check` cho thành công.
- **Trạng thái:** `connecting` không hiện cảnh báo trước lỗi đầu; `reconnecting` vàng cam với số lần thật; `failed` giữ banner và CTA; `restored` xanh lá 2 giây rồi ẩn, cập nhật dữ liệu; nếu offline hoàn toàn, dùng “Mất kết nối mạng” và không đếm WebSocket sai. Empty/error: giá trị thiết bị cũ có nhãn “Cập nhật lần cuối…”; không giả thời gian thực. Mobile banner stack câu và nút.

## M1 · Nhà và cảm biến — `np_m1_home_sensors.html`

- **Bố cục:** Header “Nhà của tôi” + dot kết nối; vùng cuộn riêng; một thẻ “Ngôi nhà” với nhãn “Toàn cảnh” và placeholder 3D tỉ lệ khoảng 16:9; tiếp “Cảm biến” hai ô Nhiệt độ 28.5°C, Độ ẩm đất 62%; tiếp thẻ trạng thái Cửa chính/Còi báo động và lối đến Thiết bị; tab bar 4 mục cố định trong viewport động.
- **Copy:** “Theo dõi trạng thái trong nhà”; “Mô hình Toàn cảnh” chỉ là label placeholder; “Cập nhật vừa xong” khi có dữ liệu thật. Không ghi độ ẩm không khí mặc định vì v1 Home chỉ giữ nhiệt độ/độ ẩm đất; nếu cần hiển thị 65% theo dữ liệu thực, đặt trong chi tiết cảm biến, không thành ô Home thứ ba.
- **Nút:** primary “Nói lệnh” có `mic`, secondary “Xem thiết bị”; các toggle thiết bị chỉ ở tab Thiết bị. Thẻ Toàn cảnh dùng preview/viewport cùng tài sản hiện hữu, không điều hướng về desktop. Icon `home/grid/mic/user` chỉ trong tab, `mic` trong CTA.
- **Trạng thái/variant:** đang tải skeleton chữ, cập nhật, mất kết nối với thời điểm cuối, cảm biến không có dữ liệu “Chưa có dữ liệu”; cửa/còi chỉ nêu trạng thái server trả, không suy ra. Màn 390×844, cuộn bên trong và tab luôn thấy.

## M2 · Bốn tab độc lập và Tài khoản — `np_m2_tabs_account.html`

- **Bố cục:** Một shell dùng chung: header cao khoảng 64px, `main` chiếm phần còn lại và `overflow-y:auto`, bottom nav cao 64px + safe-area. Bốn đích độc lập: “Nhà” chỉ Home M1; “Thiết bị” danh sách/thẻ thiết bị và điều khiển; “Giọng nói” trạng thái, hội thoại, nhập lệnh; “Tài khoản” hồ sơ và Logout. Chọn tab thay toàn bộ nội dung `main`, không scroll tới section của trang khác. Giữ trạng thái cuộn riêng từng tab nếu khả thi.
- **Tài khoản mockup:** H1 “Tài khoản”; thẻ hồ sơ “Chủ nhà” với email từ phiên thật, role và thời hạn. Chủ nhà: “Không giới hạn” nếu dữ liệu xác nhận; Khách: “Còn …” với thời hạn thật; không có dữ liệu: “Chưa có thông tin thời hạn”. Nhóm liên kết “Xác thực”, “Lời mời”, “Cài đặt” chỉ nếu tính năng/đích hiện có. Nút “Đăng xuất” secondary tách ở cuối nội dung; đăng xuất xóa phiên theo luồng hiện hữu và về login.
- **Nút/icon:** nav có `home`, `grid`, `mic`, `user`; active chỉ item được tô nền accent-soft. Trong Thiết bị, toggle trực tiếp và nhãn Bật/Tắt; trong Giọng nói, primary “Bắt đầu nói”. Account không có primary nếu không có thay đổi. Không thêm tab thứ năm.
- **Trạng thái/variant:** tab active, chưa đăng nhập về login, phiên hết hạn, logout đang chạy/lỗi. Empty Thiết bị “Chưa có thiết bị”; Giọng nói “Chưa có cuộc trò chuyện”; hồ sơ thiếu email ẩn dòng email. Samsung Internet: dùng `100dvh`, safe-area và tab trong grid shell, không cố định bằng `bottom:0` so với layout viewport cũ. Bàn phím mở thì cho cuộn form và tránh tab che ô nhập.

## M3 · Quên mật khẩu Gmail OTP — `np_m3_forgot_otp.html`

- **Bố cục:** Màn login riêng, header có quay lại; bước 1 email, bước 2 mã 6 số, bước 3 mật khẩu mới/xác nhận. Mockup hiển thị bước 2; tiến trình bằng chữ “Bước 2/3”. Thẻ form một cột.
- **Copy:** H1 “Quên mật khẩu”; “Nhập mã 6 số đã gửi tới Gmail của bạn”; email che một phần theo dữ liệu thật; label “Mã xác nhận”; helper “Mã có hiệu lực theo thời hạn hệ thống.” Không ghi OTP mẫu vào HTML.
- **Nút:** primary “Xác nhận mã”; secondary “Gửi lại mã” khi server cho phép, có countdown thật; tertiary “Đổi email”. Bước 1 “Gửi mã”; bước 3 “Đặt mật khẩu mới”. Không hiện mật khẩu hoặc mã trong URL/log.
- **Trạng thái/variant:** chưa gửi, đã gửi, đang xác nhận, sai/hết hạn mã, giới hạn gửi lại, thành công, lỗi mạng; error ngay dưới trường và focus phù hợp. Empty email validation; OTP chỉ sáu chữ số, paste hỗ trợ, `autocomplete=one-time-code`. Mobile keyboard numeric, form cuộn không che CTA. Icon `arrow-left` ở quay lại; không icon ở các ô.

## M4 · Bottom sheet giọng nói — `np_m4_voice_sheet.html`

- **Bố cục:** Tab Giọng nói mờ phía sau; overlay và sheet từ đáy chiếm khoảng 50–65% màn, bo góc trên 20px, safe-area dưới. Sheet có nút đóng `x`, tiêu đề “Đang thu âm”, waveform mức âm lượng đơn giản (thanh CSS) và vòng sóng có mục đích phản hồi mic, timer `00:03 / 00:05`, câu mẫu, CTA.
- **Copy:** “Đọc câu mẫu để xác nhận giọng nói”; câu mẫu lấy từ luồng hiện hữu, mockup dùng “Mở cửa chính cho tôi.” Kết quả PASS: “Đạt — đã xác thực” + vai trò “Chủ nhà / Gia đình / Khách” từ server. FAIL: “Chưa đạt — âm thanh quá ngắn” hoặc “Nhiều tiếng ồn”, “Giọng nói chưa khớp”; không hiển thị confidence hay metric.
- **Nút:** đang thu primary “Dừng thu”, secondary “Hủy”; đạt primary “Tiếp tục”; chưa đạt primary “Thu lại”, secondary “Đóng”. Không có nút PASS/FAIL giả lập trong sản phẩm.
- **Trạng thái/variant:** chuẩn bị, đang thu, im lặng, đang xử lý, đạt, chưa đạt, hết quyền mic, khóa an ninh; waveform chỉ động khi có mức âm thật, tôn trọng reduced-motion. Empty/error: mic không hoạt động chuyển popup 07; request lỗi cho “Chưa thể kiểm tra giọng nói. Thử lại.” Nội dung sheet cuộn khi bàn phím/viewport thấp.

## M5 · Camera quét QR — `np_m5_qr_scanner.html`

- **Bố cục:** Màn riêng trong /app; header “Quét mã QR” + đóng/quay lại; vùng camera lớn tỉ lệ linh hoạt với khung quét line 4 góc, lời hướng dẫn dưới camera, nút ở đáy phía trên safe-area. Mockup dùng nền camera placeholder bằng CSS, không ảnh/binary.
- **Copy:** “Đưa mã QR vào trong khung để quét”; “Quét mã đang hiển thị trên màn hình Chủ nhà.” Sau quét “Đang kiểm tra mã…”, thành công dẫn luồng khách hiện hữu.
- **Nút:** primary “Bật camera” ở trạng thái chưa cấp quyền; khi camera chạy, secondary “Nhập mã” chỉ nếu luồng nhập hiện hữu; “Đóng” ở header. Không cần nút chụp nếu tự quét. Không dùng camera trước.
- **Trạng thái/variant:** chưa xin quyền, đang xem camera sau, đang nhận mã, mã hợp lệ, hết hạn/đã dùng tới trang 04, không nhận diện được “Di chuyển gần hơn hoặc tăng ánh sáng”, từ chối quyền, thiếu camera, HTTP không an toàn, lỗi mạng. Dừng camera track khi rời màn/ẩn app; không giữ ảnh hoặc token trên UI/log. Empty/error: thiếu camera cho nhập mã hoặc hướng dẫn dùng thiết bị khác. Responsive 390×844; vùng camera co theo chiều cao động, CTA không bị toolbar Samsung Internet che. Icon `scan-line` cạnh tiêu đề, `x` ở đóng.
