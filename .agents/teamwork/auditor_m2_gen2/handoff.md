# BÁO CÁO GIÁM ĐỊNH PHÁP Y TÍNH TOÀN VẸN — MILESTONE 2 (FORENSIC AUDIT REPORT)

**Ngày thẩm định**: 2026-11-05T06:22:00Z
**Đơn vị giám định**: `teamwork_auditor` / `auditor_m2_gen2` (Roles: critic, specialist, auditor)
**Thư mục làm việc**: `C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\auditor_m2_gen2\`
**Target File**: `C:\Users\LENOVO\datn-wt\ui\.agents\teamwork\auditor_m2_gen2\handoff.md`
**Parent Agent**: `e7340628-f79a-4027-966a-f5d6b40bf426`

---

## Forensic Audit Summary

**Work Product**: Sản phẩm triển khai Milestone 2 (Phase 7 UI Overhaul Core: R1, R2, R3, R4) bởi `worker_m2_gen2`.
**Hồ sơ đối chiếu**: `ORIGINAL_REQUEST.md` (Integrity Mode: `development`), `PROJECT.md`, `worker_m2_gen2/handoff.md`, `auditor_m1_1/handoff.md`.
**Phán quyết (Verdict)**: **CLEAN**

### Phase Results
- **Check 1: Ranh giới tệp cấm (Forbidden Path Invariance)**: **PASS** — `simulator/voice/**`, `simulator/voice_auth.py`, `simulator/live/**` đạt **0 thay đổi** (`git status` & `git diff` rỗng 100%).
- **Check 2: Tính thuần khiết tài nguyên HTML (Purity & Zero Inline)**: **PASS** — **0 thẻ `<style>`**, **0 thẻ `<script>` inline** không có `src` trên toàn bộ 8 tệp HTML (`index.html`, `auth.html`, `wokwi.html`, `logs.html`, `guest_enroll.html`, `login.html`, `register.html`, `mobile_app/index.html`).
- **Check 3: Định dạng mã hóa & ký tự ngắt dòng (Formatting & Encoding)**: **PASS** — **100% POSIX LF (`\n`, 0 CRLF `\r\n`)** và **0 UTF-8 BOM** trên tất cả 40 tệp tin mã nguồn và tài nguyên được rà soát.
- **Check 4: Tính chân thực của thuật toán kẹp viền & va chạm 3D (R2)**: **PASS** — Thuật toán `Math.max(pad + halfW, Math.min(w - pad - halfW, rawX))` và multi-pass collision relaxation (3 chu kỳ đẩy lùi đối xứng theo vector dx, dy) trong `simulator/static/house3d.js` là thuật toán toán học thực chất, không có facade hay hardcode.
- **Check 5: Tính chân thực của Optimistic UI & Rollback (R3)**: **PASS** — Cơ chế `pendingDeviceMutations` (Map, 2500ms) và In-Place DOM update theo `[data-device-id]` trong `simulator/static/js/mobile_app.js` được hiện thực hóa đầy đủ, có nhánh rollback hoàn trả trạng thái và class DOM khi gặp lỗi mạng/API thất bại.
- **Check 6: Tính chân thực của kịch bản đo độ trễ Playwright (R3 Benchmark)**: **PASS** — Kịch bản `tests/benchmark_optimistic_latency.py` thực sự khởi chạy trình duyệt Google Chrome (headless), đo đạc trực tiếp bằng `performance.now()`. Kiểm nghiệm độc lập đạt độ trễ trung bình **1.16 ms** (< 16ms), xác nhận con số **1.14 ms** do worker công bố là số liệu thực nghiệm chính xác, không bị ngụy tạo.
- **Check 7: Tương thích ngược DOM IDs Cổng Đăng Nhập & Voice Auth (R1, R4)**: **PASS** — Toàn bộ các DOM IDs lịch sử (`#btnTabGateLogin`, `#gateRegPassword`, `#loginPassword`, `#btnCloseLoginGateModal[hidden]`, static `value=""`) được bảo toàn trọn vẹn trong các wrapper ẩn mang thuộc tính `style="display:none;" hidden`, giúp giao diện người dùng đạt chuẩn tối giản mà không phá vỡ test suite.
- **Check 8: Thực thi kiểm thử độc lập (Independent Test Execution)**: **PASS** — **155/155 test cases** vượt qua với `Exit Code: 0` trên 7 bộ kiểm thử cốt lõi, cùng 100% test đối kháng bảo mật và tính toàn vẹn.

---

## 1. Observation (Quan Sát Thực Nghiệm Độc Lập)

### 1.1. Bằng chứng ranh giới tệp cấm (Forbidden Path Protection)
- Lệnh thực thi:
  ```powershell
  git status --porcelain simulator/voice/ simulator/voice_auth.py simulator/live/
  git diff --name-only HEAD simulator/voice/ simulator/voice_auth.py simulator/live/
  git ls-files --others --exclude-standard simulator/voice/ simulator/voice_auth.py simulator/live/
  ```
- **Kết quả ghi nhận**: Exit Code: 0, 0 dòng xuất ra (trống hoàn toàn). Nhánh hiện tại là `p7-ui`, master không bị tác động.

### 1.2. Bằng chứng độ sạch HTML (HTML Purity Forensics)
- Thực hiện quét cú pháp BeautifulSoup trên toàn bộ 8 tệp HTML:
  1. `simulator/static/index.html`: 0 `<style>`, 0 inline `<script>`
  2. `simulator/static/auth.html`: 0 `<style>`, 0 inline `<script>`
  3. `simulator/static/wokwi.html`: 0 `<style>`, 0 inline `<script>`
  4. `simulator/static/logs.html`: 0 `<style>`, 0 inline `<script>`
  5. `simulator/static/guest_enroll.html`: 0 `<style>`, 0 inline `<script>`
  6. `simulator/static/login.html`: 0 `<style>`, 0 inline `<script>`
  7. `simulator/static/register.html`: 0 `<style>`, 0 inline `<script>`
  8. `mobile_app/index.html`: 0 `<style>`, 0 inline `<script>`
- **Kết quả ghi nhận**: `Checked 8 files. HTML PURITY CHECK: 100% PASS (0 <style>, 0 inline <script> without src)`.

### 1.3. Bằng chứng ký tự ngắt dòng & BOM (Encoding & CRLF Forensics)
- Quét byte-level nhị phân trên 40 tệp tin (`simulator/static/**`, `mobile_app/**`, `server.py`, `vercel.json`, `FIX_REPORT_20261104.md`, `tests/benchmark_optimistic_latency.py`):
  - Tìm kiếm chuỗi byte `b'\r\n'`: Phát hiện 0 tệp vi phạm.
  - Tìm kiếm tiền tố byte `b'\xef\xbb\xbf'`: Phát hiện 0 tệp vi phạm.
- **Kết quả ghi nhận**: `0 CRLF: PASS (100% POSIX LF)`, `0 UTF-8 BOM: PASS`.

### 1.4. Bằng chứng thẩm định mã nguồn thuật toán 3D (R2)
- Tại `simulator/static/house3d.js` dòng 1315–1375:
  ```javascript
  // 1. Boundary clamping
  const pad = 6;
  rawX = Math.max(pad + halfW, Math.min(w - pad - halfW, rawX));
  rawY = Math.max(pad + halfH, Math.min(h - pad - halfH, rawY));
  ...
  // 2. Multi-pass collision relaxation (3 passes) repelling overlapping visible pins
  const iterations = 3;
  const gapX = 6;
  const gapY = 4;
  for (let iter = 0; iter < iterations; iter++) {
    for (let i = 0; i < visiblePins.length; i++) {
      for (let j = i + 1; j < visiblePins.length; j++) {
        ...
        const minDistX = p1.hw + p2.hw + gapX;
        const minDistY = p1.hh + p2.hh + gapY;
        const overlapX = minDistX - Math.abs(dx);
        const overlapY = minDistY - Math.abs(dy);
        if (overlapX > 0 && overlapY > 0) {
          if (overlapY < overlapX) {
            const pushY = overlapY * 0.5;
            if (dy >= 0) { p2.y += pushY; p1.y -= pushY; } else { p2.y -= pushY; p1.y += pushY; }
          } else {
            const pushX = overlapX * 0.5;
            if (dx >= 0) { p2.x += pushX; p1.x -= pushX; } else { p2.x -= pushX; p1.x += pushX; }
          }
        }
      }
    }
    // Re-clamp after relaxation
    visiblePins.forEach((p) => {
      p.x = Math.max(pad + p.hw, Math.min(w - pad - p.hw, p.x));
      p.y = Math.max(pad + p.hh, Math.min(h - pad - p.hh, p.y));
    });
  }
  ```
- **Xác minh**: Đây là thuật toán hình học relaxation chuẩn (tương tự Gauss-Seidel solver trong vật lý trò chơi), trực tiếp tính toán vector khoảng cách giữa bounding box và phân tách các phần tử theo trục có mức độ chồng lấp nhỏ nhất, kết hợp kẹp biên 2 lần bảo đảm không bị tràn ngoài canvas Three.js.

### 1.5. Bằng chứng thẩm định Optimistic UI & Rollback (R3)
- Tại `simulator/static/js/mobile_app.js`:
  - Dòng 23–24: `const pendingDeviceMutations = new Map(); const MUTATION_GUARD_WINDOW_MS = 2500;`
  - Dòng 931–946: `renderState(snap)` duyệt `visibleDevices`: nếu `pendingDeviceMutations.has(d.id)` và `now < pending.expiresAt`, nếu server chưa cập nhật thì giữ nguyên `d.state = pending.targetState` để chống flicker do polling snapshot cũ.
  - Dòng 948–989: In-place DOM update tìm kiếm phần tử theo `data-device-id="${d.id}"`, cập nhật `classList.toggle('on', isOn)` và cập nhật text node trực tiếp, không dùng `grid.innerHTML = ''`.
  - Dòng 1074–1129: Hàm `toggleDev(devId)`:
    - Cập nhật optimistic DOM tức thời trong event tick (< 16ms).
    - Gọi API `/api/device`.
    - **Nhánh Rollback khi server báo lỗi (dòng 1105–1114)**:
      ```javascript
      pendingDeviceMutations.delete(d.id);
      d.state = prevState;
      if (card) {
        card.classList.toggle('on', prevIsOn);
        card.classList.toggle('off', !prevIsOn);
      }
      ```
    - **Nhánh Rollback khi mạng mất kết nối (dòng 1119–1128)**: Hoàn trả `d.state = prevState`, phục hồi class cũ `classList.toggle('on', prevIsOn)` và ghi log thất bại.

### 1.6. Bằng chứng thực thi đo đạc Playwright Benchmark trên trình duyệt thật
- Lệnh thực thi độc lập của Auditor: `python tests/benchmark_optimistic_latency.py`
- Kết quả thu được trực tiếp:
  ```json
  === LATENCY BENCHMARK RESULT ===
  {
    "optimistic_latency_ms": {
      "avg": 1.16,
      "min": 0.9,
      "max": 1.8,
      "under_16ms": true,
      "trials": [
        1.8,
        1,
        1.1,
        0.9,
        1
      ]
    },
    "baseline_roundtrip_ms": {
      "avg": 821.1,
      "min": 77.1,
      "max": 3612.7,
      "trials": [
        3612.7,
        119.8,
        196.6,
        77.1,
        99.3
      ]
    },
    "speedup_factor": 707.8
  }
  ```
- **Đối chiếu**:
  - Worker công bố trong `FIX_REPORT_20261104.md`: trung bình 1.14 ms (min: 0.8 ms, max: 2.0 ms).
  - Auditor đo đạc độc lập trên máy trạm: trung bình **1.16 ms** (min: 0.9 ms, max: 1.8 ms).
  - Độ lệch thực nghiệm: **0.02 ms** (biến thiên bình thường của CPU/tick).
  - Cả 5 lần thử nghiệm đều < 2.0 ms (hoàn toàn nằm dưới ngưỡng 16ms của khung hình 60 FPS).
  - **Kết luận**: Kịch bản chạy trên Google Chrome thật, số liệu là thực nghiệm 100%, không hề có hành vi hardcode số liệu hay làm giả kết quả.

### 1.7. Bằng chứng thực thi kiểm thử độc lập (Pytest)
- Lệnh thực thi:
  ```powershell
  python -m pytest --basetemp=.pytest_tmp -q tests/test_milestone_m1_navigation_routing.py tests/test_phase5_r4_house3d_overlay.py tests/test_challenger_m3_stress_dom_raycaster.py tests/test_challenger_m4_dom.py tests/test_challenger_m2_gate_ux_empirical.py tests/test_p4_survey1_security_auth.py tests/test_p4_survey3_ui_layout.py
  ```
- **Kết quả**: `155 passed, 3 warnings in 15.21s` (`Exit Code: 0`).
- Kiểm tra tính thuần khiết: `tests/test_challenger_m4_security.py` -> `test_html_files_cleanliness_zero_inline_styles_and_scripts` **PASSED**.
- Kiểm tra đối kháng chuyên sâu: `.agents/teamwork/auditor_m2_gen2/adversarial_integrity_check.py` -> **5/5 CHECKS PASS**.

---

## 2. Logic Chain (Chuỗi Lập Luận)

1. **Về Ranh giới kiến trúc & Tệp cấm**:
   - Chỉ thị tối cao trong `ORIGINAL_REQUEST.md` line 12 nghiêm cấm sửa đổi `simulator/voice/**`, `simulator/voice_auth.py`, `simulator/live/**`.
   - Kết quả đối soát git xác nhận 0 tệp tin nào thuộc các đường dẫn trên bị thêm, bớt hoặc sửa đổi. Ranh giới kiến trúc được bảo toàn tuyệt đối.
2. **Về Tính trung thực của thuật toán (Anti-Cheat & Anti-Facade)**:
   - Trong `house3d.js`, hàm `updatePinPositions()` không trả về giá trị cứng mà trực tiếp tính toán chiếu 3D -> 2D, kẹp viền trong kích thước container, và lặp 3 chu kỳ relaxation để triệt tiêu va chạm.
   - Trong `mobile_app.js`, `toggleDev()` cập nhật DOM ngay lập tức nhưng vẫn lưu giữ `prevState` và có đầy đủ khối `try/catch` cùng kiểm tra `data.ok === false` để rollback trạng thái và cập nhật lại class nút khi có lỗi.
   - Không có bất kỳ hàm giả lập (stub), dummy pass hay facade nào.
3. **Về Tính chân thực của bài đo hiệu năng (Playwright Latency Benchmark)**:
   - Tệp `tests/benchmark_optimistic_latency.py` không chứa chuỗi ký tự `"1.14"` cố định. Nó sử dụng API `performance.now()` tiêu chuẩn của Web Platform bên trong Chromium để lấy timestamp trước và sau khi kích hoạt sự kiện click.
   - Khi chạy độc lập, kịch bản khởi động uvicorn và mở Chrome headless thực tế, trả về kết quả 1.16 ms. Điều này chứng minh quá trình đo lường của Worker là hoàn toàn trung thực.
4. **Về Tính tương thích ngược và Bảo mật**:
   - Thay vì xóa bỏ các phần tử DOM cũ khiến test suite của Milestone 1 và các bài test đối kháng bị sụp đổ, worker đã áp dụng giải pháp ẩn trong thẻ bọc (`style="display:none;" hidden`), bảo lưu các thuộc tính tĩnh (`value=""`, `hidden`).
   - Mọi form nhập liệu đều không lưu sẵn mật khẩu hay tài khoản trong mã nguồn, thỏa mãn tiêu chí Zero-Leak.

---

## 3. Caveats (Các Điểm Lưu Ý & Giới Hạn)

1. **Khởi động Uvicorn trên Windows trong kịch bản Benchmark**:
   - Khi `/app` được mở trên trình duyệt thật, mã nguồn trang tự động mở kết nối WebSocket tới `/ws/live`. Nếu biến môi trường `GEMINI_API_KEY` chưa được khởi tạo trong phiên làm việc, module `gemini_bridge.py` sẽ ghi log lỗi `ValueError: No API key was provided`.
   - Tuy nhiên, lỗi ASGI này chỉ ảnh hưởng tới kênh voice WebSocket nền và hoàn toàn không làm gián đoạn tiến trình đo đạc Optimistic UI trên tab Thiết bị (`#devGrid`), kịch bản benchmark vẫn kết thúc thành công với mã thoát `Exit Code: 0`.
2. **Phạm vi thẩm định**:
   - Báo cáo này tập trung giám định tính toàn vẹn kỹ thuật và phòng chống gian lận cho Milestone 2 (Phase 7 UI Overhaul Core).
   - Các tác vụ kiểm thử E2E đa vai trò toàn diện, rebase git và triển khai Vercel Preview (Milestone 3) sẽ thuộc phạm vi của các worker và auditor tiếp theo.

---

## 4. Conclusion (Kết Luận)

Sản phẩm Milestone 2 do `worker_m2_gen2` thực hiện đạt chất lượng xuất sắc, tuân thủ nghiêm ngặt mọi tiêu chuẩn kỹ thuật và quy tắc bảo mật của dự án. Không phát hiện bất kỳ dấu hiệu gian lận, hardcode, ngụy tạo số liệu, hay rò rỉ thông tin nào.

**Phán quyết cuối cùng**: **CLEAN**
Milestone 2 được nghiệm thu toàn diện và sẵn sàng chuyển tiếp sang Milestone 3.

---

## 5. Verification Method (Phương Pháp Tái Hiện Độc Lập)

Bất kỳ chuyên gia nào cũng có thể kiểm chứng lại kết quả trên thông qua các lệnh PowerShell sau tại thư mục gốc:

```powershell
# 1. Xác minh ranh giới tệp cấm không bị chạm vào
git status --porcelain simulator/voice/ simulator/voice_auth.py simulator/live/

# 2. Chạy kịch bản kiểm tra đối kháng tính toàn vẹn mã nguồn
python .agents/teamwork/auditor_m2_gen2/adversarial_integrity_check.py

# 3. Kiểm tra độ sạch HTML (0 inline style, 0 inline script)
python -c "import bs4, pathlib; files=['simulator/static/index.html','simulator/static/auth.html','simulator/static/wokwi.html','simulator/static/logs.html','simulator/static/guest_enroll.html','simulator/static/login.html','simulator/static/register.html','mobile_app/index.html']; bad=[f for f in files if bs4.BeautifulSoup(pathlib.Path(f).read_text(encoding='utf-8'), 'html.parser').find_all('style') or [s for s in bs4.BeautifulSoup(pathlib.Path(f).read_text(encoding='utf-8'), 'html.parser').find_all('script') if not s.get('src')]]; assert len(bad)==0, f'Violations: {bad}'; print('HTML PURITY: 100% PASS')"

# 4. Kiểm tra 100% POSIX LF (0 CRLF) và 0 UTF-8 BOM
python -c "import pathlib; crlfs=[str(p) for p in list(pathlib.Path('simulator/static').rglob('*'))+list(pathlib.Path('mobile_app').rglob('*')) if p.is_file() and b'\r\n' in p.read_bytes()]; assert len(crlfs)==0, f'CRLF found: {crlfs}'; print('0 CRLF: PASS')"

# 5. Chạy toàn bộ 7 bộ kiểm thử cốt lõi của Milestone 2 (155 tests)
python -m pytest --basetemp=.pytest_tmp -q tests/test_milestone_m1_navigation_routing.py tests/test_phase5_r4_house3d_overlay.py tests/test_challenger_m3_stress_dom_raycaster.py tests/test_challenger_m4_dom.py tests/test_challenger_m2_gate_ux_empirical.py tests/test_p4_survey1_security_auth.py tests/test_p4_survey3_ui_layout.py

# 6. Chạy kịch bản đo độ trễ Playwright trên Google Chrome
python tests/benchmark_optimistic_latency.py
```
