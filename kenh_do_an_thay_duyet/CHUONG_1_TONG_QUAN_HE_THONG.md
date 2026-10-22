# CHƯƠNG 1. TỔNG QUAN HỆ THỐNG

## 1.1. Đặt vấn đề và tính cấp thiết của đề tài

Trong kỷ nguyên chuyển đổi số và sự phát triển mạnh mẽ của mạng lưới vạn vật kết nối (Internet of Things – IoT) kết hợp cùng Trí tuệ nhân tạo (Artificial Intelligence – AI), các hệ thống nhà thông minh (Smart Home) đang dần chuyển dịch từ mô hình điều khiển thủ công qua công tắc cơ học hoặc ứng dụng chạm trên màn hình sang mô hình **tương tác tự nhiên bằng giọng nói thời gian thực**. Tuy nhiên, qua khảo sát các hệ thống nhà thông minh hiện có trên thị trường, vẫn tồn tại bốn hạn chế kỹ thuật lớn cần được giải quyết:

1. **Sự cứng nhắc trong câu lệnh điều khiển và kịch bản tự động hóa:** Phần lớn các thiết bị hiện nay chỉ nhận diện được các câu lệnh cố định được lập trình sẵn, không cho phép từng thành viên trong gia đình tự định nghĩa lại từ vựng (đổi từ), gán khẩu lệnh cá nhân hóa (đổi lệnh), hoặc thiết lập các luật phản ứng có điều kiện (`IF - THEN - ELSE`) trực tiếp bằng giọng nói tự nhiên.
2. **Thiếu cơ chế phân quyền sinh trắc học giọng nói nhiều tầng (Multi-tier Voice RBAC):** Các trợ lý ảo phổ thông thường thực thi mọi mệnh lệnh từ bất kỳ ai phát ra âm thanh trong phòng (kể cả khách vãng lai hoặc trẻ nhỏ), gây rủi ro mất an toàn đối với các thiết bị quan trọng như cửa chính, còi báo động an ninh hoặc các lịch hẹn giờ ưu tiên của chủ nhà.
3. **Khó khăn khi tích hợp và mở rộng thiết bị gia dụng truyền thống:** Việc đấu nối dây dẫn vào các thiết bị có sẵn trong gia đình như máy điều hòa nhiệt độ, quạt điều khiển từ xa hay tivi rất phức tạp, đòi hỏi can thiệp vào phần cứng nội bộ của thiết bị.
4. **Độ trễ đồng bộ và phụ thuộc hoàn toàn vào máy chủ đám mây bên thứ ba:** Nhiều hệ thống phụ thuộc vào các nền tảng đóng (như Firebase, Supabase hoặc Cloud của hãng), thiếu khả năng tự trị tại biên (Edge Autonomy) trên vi điều khiển khi mất kết nối tới máy chủ trung tâm.

Xuất phát từ những yêu cầu thực tiễn trên, đề tài ***"Nghiên cứu, thiết kế và triển khai Hệ thống Nhà thông minh điều khiển bằng Giọng nói AI thời gian thực, Phân quyền sinh trắc học 3 tầng, Tự động hóa 2 Bể kết hợp Bản sao số 3D và Thu phát sóng Hồng ngoại trên Vi điều khiển ESP8266"*** được lựa chọn thực hiện nhằm giải quyết đồng bộ cả bài toán xử lý tín hiệu âm thanh, truyền thông viễn thông thời gian thực (MQTT/WebSocket) lẫn điều khiển nhúng tại biên.

---

## 1.2. Đối tượng theo dõi và điều khiển của hệ thống

Để xác định rõ bài toán kỹ thuật, hệ thống tập trung vào **04 nhóm đối tượng theo dõi và điều khiển** cụ thể trong không gian nhà thông minh:

**Bảng 1.1. Danh mục các đối tượng theo dõi và điều khiển trong hệ thống**

| STT | Nhóm đối tượng | Tên đối tượng cụ thể | Thông số theo dõi / Trạng thái điều khiển | Giao tiếp phần cứng trên NodeMCU ESP8266 |
| :-: | :--- | :--- | :--- | :--- |
| **1** | **Nhóm thiết bị chấp hành đóng/mở & chiếu sáng** | 1. Cửa chính (`main_door`)<br>2. Đèn phòng khách (`living_room_light`)<br>3. Đèn phòng ngủ (`bedroom_light`)<br>4. Quạt trần (`fan`)<br>5. Còi báo động (`alarm_siren`) | - Trạng thái: `OPEN / CLOSED` (Cửa chính), `ON / OFF` (Đèn, Quạt, Còi).<br>- Thời gian cập nhật trạng thái và nguồn tác động (Giọng nói, Hẹn giờ Bể 1, Luật liên động Bể 2). | - Chân `D1` (`GPIO 5` - Xung PWM Servo SG90)<br>- Chân `D2` (`GPIO 4` - GPIO/Relay)<br>- Chân `D7` (`GPIO 13` - GPIO/Relay)<br>- Chân `D8` (`GPIO 15` / `D0` - Buzzer 5V) |
| **2** | **Nhóm thiết bị ngoại vi điều khiển bằng sóng Hồng ngoại (IR)** | 6. Điều hòa nhiệt độ (`ac`) và các thiết bị có Remote mở rộng (Tivi, Quạt điều khiển từ xa) | - Thu và giải mã chuỗi xung hồng ngoại từ Remote gốc (chế độ *IR Learning*).<br>- Phát lại chuỗi xung sóng mang 38kHz (chế độ *IR Blaster*) để chiếm quyền bật/tắt, chỉnh nhiệt độ mà không cần đấu dây. | - Mắt thu IR `VS1838B` tại chân `D5` (`GPIO 14`)<br>- Mắt phát `IR LED 940nm` tại chân `D2` (`GPIO 4`) |
| **3** | **Nhóm thông số môi trường vi khí hậu trong phòng** | Nhiệt độ môi trường ($T$) và Độ ẩm tương đối ($RH$) | - Theo dõi liên tục nhiệt độ ($^\circ\text{C}$, dải đo $0\text{--}50^\circ\text{C}$) và độ ẩm tương đối ($\%\text{RH}$, dải đo $20\text{--}90\%$).<br>- Làm đầu vào kích hoạt tự động cho các luật `IF - ELSE` theo ngưỡng môi trường. | - Cảm biến số `DHT11` / `DHT22` giao tiếp chuẩn 1-Wire tại chân `D6` (`GPIO 12`) |
| **4** | **Nhóm đối tượng người dùng & Sinh trắc học giọng nói** | Người ra lệnh giọng nói thuộc 3 tầng phân quyền:<br>- **Tầng 1:** Admin tối cao (Nguyễn Tuấn Anh)<br>- **Tầng 2:** Thành viên gia đình<br>- **Tầng 3:** Khách<br>- **Ngoài danh sách:** Người lạ | - Theo dõi tín hiệu âm thanh PCM 16kHz thu từ Micro.<br>- Đo tần số cơ bản $F_0$ ($\text{Hz}$), trọng tâm phổ (Spectral Centroid $\text{Hz}$) và vector đặc trưng phổ Mel 26 chiều.<br>- Theo dõi số lần vi phạm quyền truy cập (cơ chế chặn 2-Strike). | - Thu nhận qua Micro thiết bị đầu cuối (Điện thoại / Trạm trung tâm), đồng bộ tín hiệu đèn báo thu âm `3-2-1` xuống ESP8266. |

---

## 1.3. Các công nghệ cốt lõi sử dụng trong hệ thống

Hệ thống được xây dựng dựa trên sự kết hợp chặt chẽ của **06 công nghệ cốt lõi** thuộc chuyên ngành Kỹ thuật Điện tử – Viễn thông và Công nghệ Thông tin:

### 1.3.1. Công nghệ Vi điều khiển và Truyền thông không dây NodeMCU ESP8266 (ESP-12E)
Trạm chấp hành và thu thập dữ liệu tại biên sử dụng vi điều khiển **NodeMCU ESP8266 (module ESP-12E)** tích hợp vi xử lý 32-bit Tensilica Xtensa LX106 hoạt động ở xung nhịp $80\text{--}160\text{ MHz}$, bộ nhớ Flash ngoài dung lượng $4\text{ MB}$ (quản lý tệp bằng hệ thống file `LittleFS`) và bộ thu phát vô tuyến **Wi-Fi chuẩn IEEE 802.11 b/g/n** ở băng tần $2.4\text{ GHz}$.
- Vi điều khiển hoạt động hoàn toàn độc lập với nguồn nuôi $5\text{V DC}$ ngoài (không phụ thuộc cáp nối máy tính sau khi nạp firmware).
- Đồng bộ thời gian thực theo múi giờ Việt Nam ($\text{UTC}+7$) thông qua giao thức **NTP (Network Time Protocol)** và hỗ trợ lưu trữ bản sao cấu hình 2 Bể (Bể Hẹn giờ và Bể Luật liên động) ngay trong bộ nhớ Flash để duy trì khả năng tự vận hành khi mất kết nối mạng.

### 1.3.2. Công nghệ Giao thức Truyền thông IoT Thời gian thực (MQTT & WebSocket)
Để đảm bảo độ trễ truyền tin thấp nhất (dưới $50\text{ ms}$ trong mạng nội bộ) và khả năng mở rộng thiết bị linh hoạt, hệ thống kết hợp hai giao thức truyền thông chuẩn:
1. **Giao thức MQTT (Message Queuing Telemetry Transport):** Hoạt động theo mô hình **Publish / Subscribe (Phát hành / Đăng ký)** thông qua bộ điều phối trung tâm (MQTT Broker). Giao thức MQTT giúp giải quyết triệt để bài toán truyền nhận bản tin điều khiển thiết bị, bản tin đo lường cảm biến nhiệt độ/độ ẩm (`DHT11`), bản tin học lệnh hồng ngoại (`IR Code`) và đồng bộ trạng thái giữa vi điều khiển **ESP8266**, **Backend Server** và **Mobile App** với băng thông tiêu thụ tối thiểu.
2. **Giao thức WebSocket song công toàn phần (Full-Duplex WebSocket):** Duy trì kênh truyền hai chiều liên tục giữa Backend Server tự xây dựng (nền tảng Python FastAPI), Giao diện Bản sao số 3D (Web Dashboard) và luồng âm thanh thời gian thực tới mô hình AI.

### 1.3.3. Kỹ thuật Xử lý tín hiệu số âm thanh (DSP) và Sinh trắc học giọng nói 3 tầng
Thay vì chỉ nhận diện văn bản đầu vào, hệ thống thực hiện phân tích trực tiếp sóng âm số hóa chuẩn **PCM 16-bit, tần số lấy mẫu $f_s = 16000\text{ Hz}$**:
- Tín hiệu âm thanh được loại bỏ thành phần một chiều (DC offset), cắt khoảng lặng đầu/cuối và chia thành các khung ngắn $32\text{ ms}$ ($N = 512$ mẫu) nhân với cửa sổ hàm Hanning để giảm rò rỉ phổ.
- **Ước lượng tần số cơ bản $F_0$ (Fundamental Frequency / Pitch):** Sử dụng hàm **Tự tương quan (Autocorrelation)** trong miền thời gian để xác định chu kỳ rung của dây thanh quản người nói (dải tìm kiếm từ $75\text{ Hz}$ đến $360\text{ Hz}$):
  $$R(k) = \sum_{n=0}^{N-1-k} x_w(n) \cdot x_w(n+k), \quad F_0 = \frac{f_s}{\arg\max_{k \in [k_{\min}, k_{\max}]} R(k)} \tag{1.1}$$
- **Biến đổi Fourier nhanh (FFT) và Vector đặc trưng 26 chiều:** Tính toán phổ biên độ qua FFT, xác định **Trọng tâm phổ (Spectral Centroid)** và trích xuất năng lượng logarit trên **24 dải băng tần thang Mel (Mel-Filterbank)** từ $80\text{ Hz}$ đến $7600\text{ Hz}$. Kết hợp $F_0$ chuẩn hóa, Spectral Centroid chuẩn hóa và 24 dải Mel tạo thành vector đặc trưng giọng nói 26 chiều chuẩn hóa $L_2$, so khớp bằng độ đo **Cosine Similarity** để xác thực quyền hạn 3 tầng và kích hoạt cơ chế khóa im lặng **2-Strike** đối với người lạ.

### 1.3.4. Công nghệ Thu – Phát và Giải điều chế Sóng Hồng ngoại 38kHz (IR Cloning)
Nhằm chiếm quyền điều khiển các thiết bị gia dụng có sẵn (Điều hòa, Quạt điều khiển, Tivi) và cho phép người dùng thêm thiết bị mới mà không cần tháo lắp hay đấu nối dây điện, hệ thống ứng dụng kỹ thuật **Học lệnh và Phát lại xung điều chế Hồng ngoại (Infrared Carrier Modulation & Cloning)**:
- Sử dụng mắt thu hồng ngoại chuyên dụng **`VS1838B`** có bộ lọc thông dải trung tâm ở tần số sóng mang $38\text{ kHz}$ để giải điều chế chùm tia hồng ngoại bước sóng $\lambda = 940\text{ nm}$ phát ra từ Remote gốc, thu nhận chính xác mảng thời gian mức cao/mức thấp (Raw Pulse Timings tính bằng micro-giây) hoặc mã giao thức chuẩn.
- Sử dụng đèn phát **`IR LED 940nm`** kết hợp mạch khuếch đại dòng bằng Transistor nối vào chân PWM tốc độ cao của ESP8266 để tái tạo lại sóng mang $38\text{ kHz}$ phát trực tiếp tới thiết bị đích.

### 1.3.5. Công nghệ Trí tuệ nhân tạo Hội thoại Thời gian thực (Gemini Live) & Kho tri thức Vector RAG
- **Xử lý ngôn ngữ tự nhiên & Gọi hàm thời gian thực (Function Calling):** Sử dụng mô hình đa phương thức thời gian thực **`gemini-3.8-live`** xử lý trực tiếp luồng âm thanh hai chiều, cho phép hiểu chính xác các câu lệnh tự nhiên tiếng Việt (bao gồm cả câu lệnh hẹn giờ phức tạp, đổi từ, đổi khẩu lệnh, đặt luật `IF - ELSE` hoặc lệnh quản trị tối cao của Admin Cấp 1).
- **Truy xuất tăng cường tạo sinh (Retrieval-Augmented Generation – RAG):** Xây dựng kho cơ sở dữ liệu vector nội bộ sử dụng mô hình nhúng **`gemini-embedding-001`** với số chiều vector $D = 3072$ chiều. Khi người dùng đặt câu hỏi, hệ thống chuyển câu hỏi thành vector $3072$ chiều, tính tích vô hướng (Dot Product / Cosine Similarity) với các mục tri thức trong bộ nhớ và kiểm tra quyền hỏi đáp theo từng tầng (`tier_restricted` hoặc `open_all`) trước khi trả lời ngắn gọn, đúng trọng tâm.

### 1.3.6. Công nghệ Bản sao số 3D (3D Digital Twin) và Kiến trúc Server Tự Xây Dựng
- **Không phụ thuộc dịch vụ BaaS đóng (Không dùng Firebase / Supabase):** Toàn bộ máy chủ trung tâm (Backend Server), cơ sở dữ liệu lưu trữ 2 Bể, hồ sơ giọng nói và mã sóng hồng ngoại được **tự xây dựng 100%** trên nền tảng Python (`FastAPI`, `Uvicorn`, cơ sở dữ liệu nội bộ).
- **Mô hình hóa Bản sao số 3D (Digital Twin):** Sử dụng thư viện đồ họa 3D **Three.js (WebGL)** dựng mô hình ngôi nhà thông minh 3D trực quan ngay trên trình duyệt, đồng bộ trạng thái đóng/mở, góc quay cánh cửa, hiệu ứng ánh sáng đèn, cánh quạt quay và luồng gió điều hòa khớp 100% theo thời gian thực với phần cứng ESP8266.

---

## 1.4. Mục tiêu, phạm vi nghiên cứu và bố cục của Đồ án

### 1.4.1. Mục tiêu của Đồ án
1. Thiết kế và hoàn thiện trạm phần cứng nhúng trên vi điều khiển **NodeMCU ESP8266** hoạt động với nguồn độc lập, điều khiển 6 thiết bị chấp hành, đọc cảm biến nhiệt độ/độ ẩm `DHT11` và thu phát sóng hồng ngoại $38\text{ kHz}$.
2. Xây dựng thành công hệ thống **Server tự chủ**, **Giao diện Web Dashboard 3D** và **Giao diện Mobile App** kết nối qua giao thức **MQTT** và **WebSocket**.
3. Hiện thực hóa kiến trúc **Phân quyền 3 tầng (Admin / Gia đình / Khách)** kết hợp quy trình thu âm cấp quyền giọng nói (`3-2-1` nháy đèn tín hiệu), cơ chế tự động hóa **2 Bể (Bể 1 Hẹn giờ & Bể 2 Luật động chống vòng lặp DFS)**, **4 chế độ Reset cô lập** và đặc quyền Admin Cấp 1 điều chỉnh mọi quy tắc hệ thống trực tiếp bằng giọng nói.

### 1.4.2. Bố cục của Báo cáo Đồ án
Nội dung báo cáo được tổ chức thành 03 chương theo đúng quy chuẩn của Trường Điện – Điện tử, Đại học Bách khoa Hà Nội:
- **Chương 1 – Tổng quan hệ thống:** Trình bày bối cảnh, lý do chọn đề tài, xác định rõ các nhóm đối tượng theo dõi/điều khiển và nền tảng các công nghệ sử dụng trong hệ thống.
- **Chương 2 – Phân tích và thiết kế hệ thống:** Phân tích chi tiết các chức năng của hệ thống, lưu đồ quy trình làm việc của từng phân hệ và xác định quy trình thiết kế phần cứng – phần mềm.
- **Chương 3 – Triển khai và kết quả thực nghiệm:** Trình bày chi tiết thiết kế giao thức truyền thông MQTT, thiết kế chức năng giao diện (Web Dashboard 3D & Mobile App), kết quả triển khai thực tế và số liệu đánh giá hệ thống.
