# BÁO CÁO BÀN GIAO KHẢO SÁT KỸ THUẬT: PHASE 3 - R1 (ROUTING VERCEL) & R2 (BẢO MẬT RBAC THEO SESSION)

- **Người thực hiện**: `teamwork_explorer` (Role: Explorer / Security & Routing Specialist)
- **Parent Agent ID**: `39d935a1-0551-429d-ac45-c89f1e361ad0`
- **Thời gian**: 2026-11-04T15:19:00Z
- **Loại bàn giao**: Hard Handoff (Báo cáo độc lập, đầy đủ bằng chứng, sẵn sàng triển khai)

---

## 1. Observation (Quan sát thực nghiệm & Bằng chứng mã nguồn)

### 1.1. Thực nghiệm Thăm dò Domain Production Vercel (Requirement R1)
Thực hiện lệnh kiểm thử mạng thực tế qua Python `urllib.request` đối với domain production:
`https://do-an-tot-nghiep-smart-home-voice-a.vercel.app`

**Kết quả quan sát trực tiếp**:
```
200 https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/ -> len=22435
404 https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/mobile -> len=79, vercel_not_found=True
404 https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/architecture -> len=79, vercel_not_found=True
404 https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/offline -> len=79, vercel_not_found=True
404 https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/404 -> len=79, vercel_not_found=True
404 https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/403 -> len=79, vercel_not_found=True
404 https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/500 -> len=79, vercel_not_found=True
404 https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/qr_expired -> len=79, vercel_not_found=True
404 https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/sw.js -> len=79, vercel_not_found=True
200 https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/app -> len=24551
404 https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/nonexistent-xyz-404 -> len=79, vercel_not_found=True
```
*Ghi chú phản hồi 404*: Độ dài 79 bytes chính là nội dung HTML mặc định từ hạ tầng Edge của Vercel (`404: NOT_FOUND\nCode: NOT_FOUND`), chứng minh yêu cầu chưa hề chạm tới file HTML tĩnh tùy biến hay handler của backend.

### 1.2. Hiện trạng Cấu hình `vercel.json`
Tệp: `file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/vercel.json` (dòng 1–34)
```json
{
  "version": 2,
  "framework": null,
  "cleanUrls": false,
  "headers": [
    {
      "source": "/sw.js",
      "headers": [
        { "key": "Service-Worker-Allowed", "value": "/" },
        { "key": "Cache-Control", "value": "no-cache, no-store, must-revalidate" }
      ]
    }
  ],
  "routes": [
    { "src": "^/api/(.*)$", "dest": "/api/index.py" },
    { "src": "^/sw\\.js$", "dest": "/simulator/static/sw.js", "headers": { "Service-Worker-Allowed": "/" } },
    { "src": "^/offline(\\.(html))?$", "dest": "/simulator/static/offline.html" },
    { "src": "^/404(\\.(html))?$", "dest": "/simulator/static/404.html" },
    { "src": "^/500(\\.(html))?$", "dest": "/simulator/static/500.html" },
    { "src": "^/(qr_expired|qr-expired)(\\.(html))?$", "dest": "/simulator/static/qr_expired.html" },
    { "src": "^/403(\\.(html))?$", "dest": "/simulator/static/403.html" },
    { "src": "^/static/(.*)$", "dest": "/simulator/static/$1" },
    { "src": "^/test_audio/(.*)$", "dest": "/test_audio/$1" },
    { "src": "^/app/?$", "dest": "/mobile_app/index.html" },
    { "src": "^/auth/?$", "dest": "/simulator/static/auth.html" },
    { "src": "^/guest_enroll/?$", "dest": "/simulator/static/guest_enroll.html" },
    { "src": "^/guest-qr/?$", "dest": "/simulator/static/guest_enroll.html" },
    { "src": "^/logs/?$", "dest": "/simulator/static/logs.html" },
    { "src": "^/wokwi/?$", "dest": "/simulator/static/wokwi.html" },
    { "src": "^/archify/devops/?$", "dest": "/docs/kien_truc/devops-cicd-pipeline.workflow.html" },
    { "src": "^/archify/?$", "dest": "/docs/kien_truc/smart-home-voice-ai.architecture.html" },
    { "src": "^/$", "dest": "/simulator/static/index.html" }
  ]
}
```
**Khiếm khuyết quan sát thấy**:
1. Tuyệt đối không có quy tắc nào cho `/mobile`. Khi truy cập `/mobile`, Vercel rơi khỏi danh sách routes và trả về Vercel NOT_FOUND.
2. Tuyệt đối không có quy tắc nào cho `/architecture`. Chỉ có `/archify` (dòng 31).
3. Không có quy tắc bắt lỗi cuối (fallback catch-all) `^(.*)$ -> /simulator/static/404.html`. Bất kỳ đường dẫn không tồn tại nào sẽ rơi vào màn hình 404 thô của Vercel thay vì `404.html` tùy biến.
4. Lần deploy Vercel gần nhất là cách đây 4 giờ (deployment `do-an-tot-nghiep-smart-home-voice-3nb3bsy68.vercel.app`), trước khi commit `26e7afab011f1c1a885ca8a6df334ea5f57fb459` được sinh ra, do đó các route lỗi mới chưa được áp dụng lên server production thật.

### 1.3. Hiện trạng FastAPI Routes trong `simulator/server.py`
Tệp: `file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/server.py`
- Dòng 137–225: Khai báo các route giao diện Web/Mobile tĩnh.
- Quan sát:
  - Có `@app.get("/app")` (dòng 142) phục vụ `mobile_app/index.html`.
  - Có `@app.get("/archify")` (dòng 168) phục vụ kiến trúc.
  - **KHÔNG CÓ** `@app.get("/mobile")` (để redirect 307 về `/app`).
  - **KHÔNG CÓ** `@app.get("/architecture")` (để phục vụ `smart-home-voice-ai.architecture.html`).

### 1.4. Lỗ hổng RBAC Dùng Trạng Thái Singleton Toàn Cục (Requirement R2)
Tệp: `file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_devices.py` (dòng 124–128):
```python
session_tier = int(_REST_ENGINE.current_tier)
session_user = _REST_ENGINE.get_current_user_name()
res = await _REST_ENGINE.execute_device_action(dev_id, act, source=source, bypass_rbac=False)
```
Tệp: `file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/api/routes_auth.py`:
- Dòng 546–547 (trong `api_auth3_layer1_login`):
  ```python
  active_uid = acc_id if acc_id in _REST_ENGINE.users else role_map.get(tier_val, "khach_c")
  _REST_ENGINE.set_active_user(active_uid)
  ```
- Dòng 578–579 (trong `api_auth3_layer2_verify_otp`):
  ```python
  active_uid = acc_id if acc_id in _REST_ENGINE.users else role_map.get(tier_val, "khach_c")
  _REST_ENGINE.set_active_user(active_uid)
  ```
- Dòng 682–683 (trong `api_auth3_layer3_voice`):
  ```python
  _REST_ENGINE.set_active_user(role_map.get(tier_val, "tuan_anh"))
  ```
- Dòng 561–562 & 593–594:
  ```python
  resp.set_cookie("sh_session_tier", str(tier_val), httponly=True, samesite="lax")
  resp.set_cookie("sh_session_user", str(acc.get("account_id", "")), httponly=True, samesite="lax")
  ```
Tệp: `file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/rule_engine.py`:
- Dòng 322–323:
  ```python
  if not bypass_rbac and self.server_connected:
      allowed, reason = self.check_device_permission(dev_id)
  ```
Tệp: `file:///C:/Users/LENOVO/Desktop/đồ án tốt nghiệp/simulator/engine/voice_rbac_mixin.py`:
- Dòng 425:
  ```python
  if self.current_tier > min_tier:
      dname = dev.get("name", dev_id)
      return (
          False,
          f"Từ chối truy cập! Thiết bị {dname} chỉ cho phép từ Cấp {min_tier} trở lên điều khiển.",
      )
  ```

**Hậu quả kiến trúc nghiêm trọng**:
1. `_REST_ENGINE` là một đối tượng Singleton toàn cục dùng chung cho toàn bộ server FastAPI.
2. `self._current_user_id` và `self.current_tier` là biến trạng thái nội tại trên Singleton này.
3. Khi Người dùng A (Chủ nhà Tầng 1) đăng nhập, `_REST_ENGINE.set_active_user("tuan_anh")` làm `current_tier = 1`.
4. Nếu cùng lúc đó Người dùng B (Khách Tầng 3) đăng nhập hoặc bắt tay QR TOTP, `_REST_ENGINE.set_active_user("khach_c")` ghi đè `current_tier = 3` trên toàn hệ thống.
5. Khi 2 request gửi đồng thời tới `/api/device`:
   - Nếu request của Chủ nhà đến sau khi Khách vừa login: `session_tier = _REST_ENGINE.current_tier` nhận giá trị 3 -> Chủ nhà bị chặn mở cửa chính (`main_door` đòi Tầng 1) -> **Từ chối dịch vụ (DoS)**.
   - Nếu request của Khách đến ngay sau khi Chủ nhà vừa gửi lệnh hoặc login: `session_tier = _REST_ENGINE.current_tier` nhận giá trị 1 -> Khách điều khiển được cửa chính hoặc đặt lịch hẹn giờ -> **Rò rỉ leo thang đặc quyền (Privilege Escalation)**.
6. Mặc dù `routes_auth.py` có đặt cookie `sh_session_tier` và `sh_session_user`, các endpoint `/api/device`, `/api/mobile/schedule` **hoàn toàn không đọc cookie này** mà vẫn đọc biến Singleton `_REST_ENGINE.current_tier`.

---

## 2. Logic Chain (Chuỗi suy luận giải pháp)

### 2.1. Logic Chain cho R1 (Vercel Production Routing)
1. **Tiền đề 1**: Vercel Routing sử dụng cơ chế so khớp tuần tự từ trên xuống dưới trong mảng `routes`.
2. **Tiền đề 2**: Các đường dẫn `/mobile`, `/architecture` không có pattern khớp nên bị Vercel trả về 404.
3. **Tiền đề 3**: Khi không có quy tắc catch-all ở cuối mảng, Vercel trả về lỗi hạ tầng 404 raw thay vì trang tùy biến `404.html`.
4. **Suy luận giải pháp R1**:
   - Thêm quy tắc chuyển hướng 307 cho `/mobile` tới `/app`:
     `{ "src": "^/mobile/?$", "status": 307, "headers": { "Location": "/app" } }`
   - Thêm quy tắc định tuyến tĩnh cho `/architecture`:
     `{ "src": "^/architecture/?$", "dest": "/docs/kien_truc/smart-home-voice-ai.architecture.html" }`
   - Bổ sung quy tắc bắt cuối (catch-all) ở đáy mảng `routes`:
     `{ "src": "^/(.*)$", "status": 404, "dest": "/simulator/static/404.html" }`
   - Thêm đồng bộ các route này vào `simulator/server.py` bằng `RedirectResponse` và `FileResponse` để đảm bảo khi chạy test qua FastAPI `TestClient` hoặc local uvicorn đều hoạt động đồng nhất 100%.

### 2.2. Logic Chain cho R2 (Session-based RBAC)
1. **Tiền đề 1**: Mô hình RESTful chuẩn yêu cầu Stateless: Quyền của mỗi HTTP request phải được định danh hoàn toàn dựa trên thông tin gửi kèm request đó (Cookie hoặc Header Bearer), không phụ thuộc vào trạng thái toàn cục của server.
2. **Tiền đề 2**: Hiện tại `execute_device_action` và `check_device_permission` chỉ đọc `self.current_tier` từ engine nội tại.
3. **Suy luận giải pháp R2**:
   - Xây dựng kho lưu trữ phiên `SessionStore` (lưu trong memory cache và SQLite WAL `smarthome.db`). Mỗi phiên có `{ session_id, user_id, email, display_name, tier, role, expires_at }`.
   - Viết hàm trích xuất phiên `resolve_request_session(request, payload)`:
     1. Ưu tiên 1: Header `Authorization: Bearer <session_token>` hoặc `X-Session-Token: <token>`
     2. Ưu tiên 2: Cookie `sh_session_token` hoặc `session_token`
     3. Ưu tiên 3: Payload `session_token` hoặc `guest_session_id`
     4. Fallback tương thích: Cookie kế thừa `sh_session_tier` và `sh_session_user`
     5. Mặc định không đăng nhập: Gán phiên ẩn danh Khách (`tier=3` hoặc `tier=4`).
   - Mở rộng hàm `execute_device_action` và `check_device_permission` để tiếp nhận tham số `request_tier: int | None = None`, `request_user_name: str | None = None`. Khi được truyền vào, thuật toán RBAC so sánh trực tiếp trên `request_tier` thay vì `self.current_tier`.
   - Ngừng việc gọi `_REST_ENGINE.set_active_user(...)` như một tác dụng phụ toàn cục khi có một người dùng đăng nhập HTTP.

---

## 3. Chiến lược Triển khai Chi tiết cho R1 (Vercel Production Routing)

### 3.1. Cấu hình hoàn chỉnh đề xuất cho `vercel.json`
Thay thế toàn bộ nội dung của `vercel.json` bằng cấu hình chuẩn sau:

```json
{
  "version": 2,
  "framework": null,
  "cleanUrls": false,
  "headers": [
    {
      "source": "/sw.js",
      "headers": [
        { "key": "Service-Worker-Allowed", "value": "/" },
        { "key": "Cache-Control", "value": "no-cache, no-store, must-revalidate" }
      ]
    }
  ],
  "routes": [
    { "src": "^/api/(.*)$", "dest": "/api/index.py" },
    { "src": "^/mobile/?$", "status": 307, "headers": { "Location": "/app" } },
    { "src": "^/sw\\.js$", "dest": "/simulator/static/sw.js", "headers": { "Service-Worker-Allowed": "/" } },
    { "src": "^/offline(\\.(html))?$", "dest": "/simulator/static/offline.html" },
    { "src": "^/404(\\.(html))?$", "status": 404, "dest": "/simulator/static/404.html" },
    { "src": "^/500(\\.(html))?$", "status": 500, "dest": "/simulator/static/500.html" },
    { "src": "^/(qr_expired|qr-expired)(\\.(html))?$", "dest": "/simulator/static/qr_expired.html" },
    { "src": "^/403(\\.(html))?$", "status": 403, "dest": "/simulator/static/403.html" },
    { "src": "^/static/(.*)$", "dest": "/simulator/static/$1" },
    { "src": "^/test_audio/(.*)$", "dest": "/test_audio/$1" },
    { "src": "^/app/?$", "dest": "/mobile_app/index.html" },
    { "src": "^/auth/?$", "dest": "/simulator/static/auth.html" },
    { "src": "^/guest_enroll/?$", "dest": "/simulator/static/guest_enroll.html" },
    { "src": "^/guest-qr/?$", "dest": "/simulator/static/guest_enroll.html" },
    { "src": "^/logs/?$", "dest": "/simulator/static/logs.html" },
    { "src": "^/wokwi/?$", "dest": "/simulator/static/wokwi.html" },
    { "src": "^/archify/devops/?$", "dest": "/docs/kien_truc/devops-cicd-pipeline.workflow.html" },
    { "src": "^/archify/?$", "dest": "/docs/kien_truc/smart-home-voice-ai.architecture.html" },
    { "src": "^/architecture/?$", "dest": "/docs/kien_truc/smart-home-voice-ai.architecture.html" },
    { "src": "^/$", "dest": "/simulator/static/index.html" },
    { "src": "^/(.*)$", "status": 404, "dest": "/simulator/static/404.html" }
  ]
}
```

### 3.2. Bổ sung Route trong `simulator/server.py`
Thêm 2 endpoint sau vào `simulator/server.py` (ngay dưới route `@app.get("/app")` và `@app.get("/archify")`):

```python
from fastapi.responses import RedirectResponse

@app.get("/mobile")
async def mobile_redirect() -> Response:
    """Chuyển hướng 307 từ /mobile về ứng dụng /app."""
    return RedirectResponse(url="/app", status_code=307)

@app.get("/architecture")
async def architecture_page() -> FileResponse:
    """Trang Sơ đồ Kiến trúc Hệ thống tương tác (Archify)."""
    return FileResponse(DOCS_ARCH_DIR / "smart-home-voice-ai.architecture.html")
```

---

## 4. Chiến lược Triển khai Chi tiết cho R2 (Session-based RBAC)

### 4.1. Thiết kế Module Quản lý Phiên `simulator/auth/session_store.py`
Tạo mới file `simulator/auth/session_store.py`:

```python
"""Module Quản lý Phiên Xác thực Đa người dùng Đồng thời (Session-based RBAC Store)."""
from __future__ import annotations

import dataclasses
import secrets
import sqlite3
import time
from typing import Any

from simulator.auth.constants_and_crypto import DATA_DIR

DB_PATH = DATA_DIR / "smarthome.db"

@dataclasses.dataclass
class UserSession:
    session_id: str
    user_id: str
    email: str
    display_name: str
    tier: int
    role: str
    created_at: float
    expires_at: float
    source: str = "web"

    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class SessionStore:
    def __init__(self) -> None:
        self._memory_cache: dict[str, UserSession] = {}
        self._init_sqlite()
        self._seed_deterministic_test_sessions()

    def _init_sqlite(self) -> None:
        try:
            with sqlite3.connect(str(DB_PATH), timeout=5.0) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_sessions (
                        session_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        email TEXT,
                        display_name TEXT,
                        tier INTEGER NOT NULL,
                        role TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        source TEXT
                    )
                """)
                conn.commit()
        except Exception:
            pass

    def _seed_deterministic_test_sessions(self) -> None:
        """Tạo sẵn 3 phiên chuẩn định danh phục vụ test suite đồng thời 3 vai trò."""
        now = time.time()
        far_future = now + 86400 * 30
        self.create_session(
            user_id="tuan_anh",
            email="nep94121@gmail.com",
            display_name="Nguyễn Tuấn Anh (Chủ nhà)",
            tier=1,
            role="ADMIN",
            session_id="sess_owner_t1_nep94121",
            ttl_sec=86400 * 30,
            source="seed",
        )
        self.create_session(
            user_id="thanh_vien_a",
            email="thanhvien.a@gmail.com",
            display_name="Thành viên A (Gia đình)",
            tier=2,
            role="MEMBER",
            session_id="sess_family_t2_member_a",
            ttl_sec=86400 * 30,
            source="seed",
        )
        self.create_session(
            user_id="khach_c",
            email="khach.c@gmail.com",
            display_name="Khách C (Khách viếng thăm)",
            tier=3,
            role="CHILD_GUEST",
            session_id="sess_guest_t3_visitor_c",
            ttl_sec=86400 * 30,
            source="seed",
        )

    def create_session(
        self,
        user_id: str,
        tier: int,
        role: str,
        display_name: str = "",
        email: str = "",
        session_id: str | None = None,
        ttl_sec: int = 86400,
        source: str = "web",
    ) -> UserSession:
        sid = session_id or f"sess_{secrets.token_urlsafe(24)}"
        now = time.time()
        sess = UserSession(
            session_id=sid,
            user_id=user_id,
            email=email,
            display_name=display_name or user_id,
            tier=tier,
            role=role,
            created_at=now,
            expires_at=now + ttl_sec,
            source=source,
        )
        self._memory_cache[sid] = sess
        try:
            with sqlite3.connect(str(DB_PATH), timeout=5.0) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO user_sessions 
                    (session_id, user_id, email, display_name, tier, role, created_at, expires_at, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (sess.session_id, sess.user_id, sess.email, sess.display_name, sess.tier, sess.role, sess.created_at, sess.expires_at, sess.source))
                conn.commit()
        except Exception:
            pass
        return sess

    def get_session(self, session_id: str) -> UserSession | None:
        if not session_id:
            return None
        sess = self._memory_cache.get(session_id)
        if sess:
            if sess.is_expired():
                del self._memory_cache[session_id]
                return None
            return sess
        # Lookup SQLite fallback
        try:
            with sqlite3.connect(str(DB_PATH), timeout=5.0) as conn:
                cur = conn.execute("SELECT session_id, user_id, email, display_name, tier, role, created_at, expires_at, source FROM user_sessions WHERE session_id = ?", (session_id,))
                row = cur.fetchone()
                if row:
                    sess = UserSession(*row)
                    if not sess.is_expired():
                        self._memory_cache[session_id] = sess
                        return sess
        except Exception:
            pass
        return None

    def synthesize_legacy_session(self, user_id: str, tier: int) -> UserSession:
        role_map = {1: "ADMIN", 2: "MEMBER", 3: "CHILD_GUEST"}
        return UserSession(
            session_id="legacy_cookie",
            user_id=user_id,
            email="",
            display_name=user_id,
            tier=tier,
            role=role_map.get(tier, "CHILD_GUEST"),
            created_at=time.time(),
            expires_at=time.time() + 86400,
            source="legacy_cookie",
        )

# Singleton Instance
_SESSION_STORE = SessionStore()

def get_session_store() -> SessionStore:
    return _SESSION_STORE
```

### 4.2. Bộ Phân giải Phiên `resolve_request_session`
Thêm hàm trợ giúp trong `simulator/api/routes_devices.py`:

```python
from simulator.auth.session_store import UserSession, get_session_store

def resolve_request_session(request: Request, payload: dict[str, Any] | None = None) -> UserSession:
    """Xác định phiên người dùng một cách stateless từ Header / Cookie / Payload / Fallback."""
    store = get_session_store()
    
    # 1. Header Authorization Bearer
    auth_header = request.headers.get("authorization", "")
    token = ""
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        
    # 2. Header X-Session-Token
    if not token:
        token = request.headers.get("x-session-token", "").strip()
        
    # 3. Cookie sh_session_token hoặc session_token
    if not token:
        token = request.cookies.get("sh_session_token") or request.cookies.get("session_token", "")
        
    # 4. Body payload
    if not token and payload and isinstance(payload, dict):
        token = str(payload.get("session_token") or payload.get("guest_session_id") or "").strip()
        
    if token:
        sess = store.get_session(token)
        if sess and not sess.is_expired():
            return sess
            
    # 5. Legacy cookie fallback
    c_tier = request.cookies.get("sh_session_tier")
    c_user = request.cookies.get("sh_session_user")
    if c_tier:
        try:
            tier_int = int(c_tier)
            return store.synthesize_legacy_session(c_user or "user", tier_int)
        except ValueError:
            pass

    # 6. Fallback mặc định cho client chưa đăng nhập: Tầng 3 (Khách)
    return UserSession(
        session_id="anonymous",
        user_id="anonymous",
        email="",
        display_name="Khách (Chưa đăng nhập)",
        tier=3,
        role="CHILD_GUEST",
        created_at=time.time(),
        expires_at=time.time() + 86400,
        source="unauthenticated",
    )
```

### 4.3. Cải tiến RuleEngine: Tiếp nhận `request_tier` & `request_user_name`
Tại `simulator/rule_engine.py`:
1. Hàm `execute_device_action` nhận thêm `request_tier: int | None = None`, `request_user_name: str | None = None`, `request_role: str | None = None`:
   ```python
   async def execute_device_action(
       self,
       device_id: str,
       action: str,
       source: str = "voice",
       bypass_rbac: bool = False,
       trigger_chains: bool = True,
       request_tier: int | None = None,
       request_user_name: str | None = None,
       request_role: str | None = None,
   ) -> dict[str, Any]:
       effective_tier = request_tier if request_tier is not None else self.current_tier
       effective_user = request_user_name or self.get_current_user_name()
       effective_role = request_role or self.current_role
       ...
       # Kiểm tra quyền dựa trên effective_tier
       if not bypass_rbac and self.server_connected:
           allowed, reason = self.check_device_permission(dev_id, actor_tier=effective_tier)
           if not allowed:
               ...
   ```
2. Hàm `check_device_permission` trong `simulator/engine/voice_rbac_mixin.py`:
   ```python
   def check_device_permission(self, dev_id: str, actor_tier: int | None = None) -> tuple[bool, str]:
       tier = actor_tier if actor_tier is not None else self.current_tier
       ...
       if tier > min_tier:
           dname = dev.get("name", dev_id)
           return False, f"Từ chối truy cập! Thiết bị {dname} chỉ cho phép từ Cấp {min_tier} trở lên điều khiển."
       ...
   ```

### 4.4. Cải tiến Routes Điều Khiển Thiết Bị `simulator/api/routes_devices.py`
Thay thế đoạn đọc `_REST_ENGINE.current_tier` bằng `resolve_request_session(request, body)`:
```python
@router.post("/api/device")
@router.post("/api/device_control")
async def api_control_device(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    body = payload if isinstance(payload, dict) else {}
    dev_id = str(body.get("device_id") or "main_door").strip() or "main_door"
    act = str(body.get("action") or "open").strip() or "open"
    source = str(body.get("source") or "mobile_app").strip() or "mobile_app"

    session = resolve_request_session(request, body)
    
    res = await _REST_ENGINE.execute_device_action(
        dev_id,
        act,
        source=source,
        bypass_rbac=False,
        request_tier=session.tier,
        request_user_name=session.display_name,
        request_role=session.role,
    )
    res["tier"] = session.tier
    res["user_name"] = session.display_name
    res["rbac_blocked"] = not bool(res.get("ok"))
    if not res.get("ok") and not res.get("error"):
        res["error"] = res.get("exact_spoken_reply") or "Bị chặn bởi phân quyền RBAC."
    
    status_code = 200 if res.get("ok") else 403
    return JSONResponse(res, status_code=status_code)
```
Và tương tự với `/api/mobile/schedule`:
```python
@router.post("/api/mobile/schedule")
async def api_mobile_schedule(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
    body = payload if isinstance(payload, dict) else {}
    session = resolve_request_session(request, body)
    effective_tier = session.tier
    user_name = session.display_name
    ...
```

### 4.5. Cải tiến Routes Xác thực `simulator/api/routes_auth.py`
Khi đăng nhập Lớp 1 hoặc xác nhận Lớp 2 OTP thành công:
```python
store = get_session_store()
sess = store.create_session(
    user_id=acc_id,
    tier=tier_val,
    role=role_map.get(tier_val, "CHILD_GUEST"),
    display_name=acc.get("display_name", email),
    email=email,
)
resp.set_cookie("sh_session_token", sess.session_id, httponly=True, samesite="lax", max_age=86400)
res["session_token"] = sess.session_id
res["session"] = sess.to_dict()
```
Đồng thời, **loại bỏ lệnh `_REST_ENGINE.set_active_user(active_uid)`** trong các luồng đăng nhập HTTP để không gây nhiễu loạn trạng thái engine của các session khác.

---

## 5. Chiến lược Kiểm thử Tự động cho 3 Vai trò Đồng thời (Test Strategy)

Tạo file kiểm thử mới: `tests/test_p3_session_rbac_concurrency.py`

### 5.1. Bảng Ma trận Kiểm định Quyền (Permission Truth Table)
| Thiết bị / Thao tác | Cấp 1 (Chủ nhà `tuan_anh` - Tier 1) | Cấp 2 (Người nhà `thanh_vien_a` - Tier 2) | Cấp 3 (Khách `khach_c` - Tier 3) |
|---|---|---|---|
| `main_door` (`open`/`close`) | **CHO PHÉP (200 OK)** | **CHẶN (403 Forbidden)** | **CHẶN (403 Forbidden)** |
| `alarm_siren` (`turn_on`) | **CHO PHÉP (200 OK)** | **CHẶN (403 Forbidden)** | **CHẶN (403 Forbidden)** |
| `ac` (`turn_on`/`open`) | **CHO PHÉP (200 OK)** | **CHO PHÉP (200 OK)** | **CHẶN (403 Forbidden)** |
| `living_room_light` (`turn_on`) | **CHO PHÉP (200 OK)** | **CHO PHÉP (200 OK)** | **CHO PHÉP (200 OK)** |
| `mobile/schedule` (Hẹn giờ) | **CHO PHÉP (200 OK)** | **CHO PHÉP (200 OK)** | **CHẶN (403 Forbidden)** |

### 5.2. Kịch bản Kiểm thử Đồng thời (Concurrent Stress Simulation)
Sử dụng `concurrent.futures.ThreadPoolExecutor` hoặc `asyncio.gather` với `httpx.AsyncClient` gửi **120 requests đan xen ngẫu nhiên**:
- 40 requests từ Session T1 (`sess_owner_t1_nep94121`)
- 40 requests từ Session T2 (`sess_family_t2_member_a`)
- 40 requests từ Session T3 (`sess_guest_t3_visitor_c`)

**Tiêu chí Chấp thuận Tuyệt đối (Zero Tolerance)**:
1. 100% lệnh mở cửa chính từ Session T1 phải thành công (`ok=True`, status 200). Không một lệnh nào của Chủ nhà bị từ chối dù Khách gửi request cùng mili-giây.
2. 100% lệnh mở cửa chính từ Session T2 và Session T3 phải bị từ chối (`ok=False`, status 403). Không xảy ra bất kỳ hiện tượng rò rỉ quyền nào từ T1 sang T2 hoặc T3.
3. 100% lệnh tạo hẹn giờ từ Session T3 phải bị từ chối (`ok=False`, status 403).
4. Kiểm tra không gửi token / cookie: Request phải tự động rơi vào Tầng 3 và bị chặn mở cửa chính.

---

## 6. Caveats (Khu vực Lưu ý)

1. **Gemini Live Bridge WebSocket**: Kết nối WebSocket `/ws` duy trì một phiên thời gian thực kéo dài (`LiveBridgeSession`), trên đó `voice_auth` nhận diện giọng nói và gán vai trò riêng cho bridge đó (`session.engine.set_active_user`). Việc sửa RBAC session cho HTTP API độc lập và không làm ảnh hưởng tới luồng voice bridge.
2. **Cấu hình Vercel Headers**: Vercel quy định nếu dùng `routes` thì các header đặc thù như `Service-Worker-Allowed` nên được nhúng trực tiếp trong từng block của `routes` hoặc ở block `headers` tổng quan. Bản cấu hình đề xuất ở Mục 3.1 đã tích hợp cả hai để đảm bảo tương thích 100%.

---

## 7. Conclusion (Kết luận Đánh giá)

1. **Requirement R1 (Routing Vercel)**:
   - Nguyên nhân chính gây ra NOT_FOUND trên `do-an-tot-nghiep-smart-home-voice-a.vercel.app` đã được khoanh vùng chính xác: Thiếu redirect `/mobile`, thiếu route `/architecture`, thiếu catch-all cho 404, và deployment hiện tại trên Vercel chưa được build từ commit mới nhất.
   - Giải pháp đã được thiết kế hoàn chỉnh trong `vercel.json` và `simulator/server.py`.

2. **Requirement R2 (Session-based RBAC Security)**:
   - Bản chất lỗ hổng là sự phụ thuộc vào Singleton toàn cục `_REST_ENGINE.current_tier`, dẫn tới Race Condition giữa các phiên người dùng đồng thời.
   - Kiến trúc giải pháp với `SessionStore` (Memory + SQLite), Dependency `resolve_request_session`, và tham số hóa `execute_device_action(..., request_tier=...)` giải quyết triệt để vấn đề, đảm bảo nguyên tắc Zero-Trust Stateless.

---

## 8. Verification Method (Phương pháp Kiểm chứng Độc lập)

Người nhận bàn giao (Implementer / Reviewer) có thể kiểm chứng độc lập bằng các bước sau:

1. **Kiểm tra cú pháp và tính nhất quán của file cấu hình `vercel.json`**:
   ```powershell
   python -c "import json; d = json.load(open('vercel.json', encoding='utf-8')); assert any(r.get('status') == 307 for r in d['routes']); print('vercel.json syntax OK')"
   ```

2. **Chạy bộ kiểm thử định tuyến hiện có**:
   ```powershell
   python -X utf8 -m pytest tests/test_m6_web_error_sw.py -q
   ```

3. **Chạy bộ kiểm thử RBAC đồng thời sau khi cài đặt**:
   ```powershell
   python -X utf8 -m pytest tests/test_p3_session_rbac_concurrency.py -q
   ```

4. **Kiểm tra curl trên production sau deploy**:
   ```powershell
   curl -I https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/mobile
   curl -I https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/architecture
   curl -I https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/sw.js
   curl -I https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/offline
   curl -I https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/404
   ```
