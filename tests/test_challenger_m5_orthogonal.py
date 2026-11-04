"""Bộ Kiểm Thử Đối Kháng Thực Nghiệm Độc Lập Bổ Sung (Milestone M5 Orthogonal Verification).

Thực hiện bởi: challenger_m5_2 (Role: Empirical Adversarial Challenger & Specialist)
Hạng mục kiểm định đối kháng thực nghiệm:
1. SQL Injection phá hoại vào POST /api/logs/sql_query (DROP, UPDATE, INSERT, ALTER, DELETE, ATTACH, DETACH, VACUUM, REINDEX, Stacked Queries, Subqueries).
   -> Xác nhận bị chặn 100% bởi lớp bảo vệ regex và cơ chế SQLite file URI ?mode=ro.
2. Fuzzing tham số limit và min_tier với chuỗi chữ, ký tự lạ, số siêu lớn, kiểu dữ liệu phức tạp.
   -> Xác nhận 0 unhandled HTTP 500 crash.
3. Kiểm thử POST /api/logs/clear và alias /api/clear_audit_logs.
   -> Xác nhận cả tệp .jsonl và bảng audit_logs trong SQLite smarthome.db đều được làm sạch an toàn.
4. Kiểm thử gửi audio_pcm_b64 lên POST /api/auth3/enroll_voice_sample.
   -> Xác nhận hỗ trợ alias audio_pcm_b64, kích hoạt cổng chống trùng giọng Cấp 1, và xử lý an toàn dữ liệu dị dạng.
"""

from __future__ import annotations

import base64
import json
import math
import pathlib
import sqlite3
import struct
import sys
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.auth_3layer import get_auth_3layer_manager
from simulator.database_sqlite import DATA_DIR, SQLITE_DB_PATH, get_connection, init_sqlite_database
from simulator.server import _ACTIVE_BRIDGES, _BOOT_VOICE_AUTH, app


@pytest.fixture(autouse=True)
def clean_system_state():
    """Làm sạch bộ nhớ đệm token, phiên ma active bridges và reset voice auth."""
    mgr = get_auth_3layer_manager()
    if hasattr(mgr, "used_qr_tokens"):
        mgr.used_qr_tokens.clear()
    if hasattr(mgr, "active_qr_tokens"):
        mgr.active_qr_tokens.clear()
    if hasattr(mgr, "guest_qr_sessions"):
        mgr.guest_qr_sessions.clear()
    _ACTIVE_BRIDGES.clear()
    _BOOT_VOICE_AUTH.reset_to_owner_only()
    yield
    if hasattr(mgr, "used_qr_tokens"):
        mgr.used_qr_tokens.clear()
    if hasattr(mgr, "active_qr_tokens"):
        mgr.active_qr_tokens.clear()
    if hasattr(mgr, "guest_qr_sessions"):
        mgr.guest_qr_sessions.clear()
    _ACTIVE_BRIDGES.clear()
    _BOOT_VOICE_AUTH.reset_to_owner_only()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _generate_synthetic_pcm_16k(duration_sec: float = 2.0, freq: float = 440.0) -> bytes:
    """Sinh chuỗi sóng sin 16kHz mono 16-bit PCM giả lập cho kiểm thử."""
    sample_rate = 16000
    total_samples = int(sample_rate * duration_sec)
    buf = bytearray()
    for i in range(total_samples):
        val = int(16000.0 * math.sin(2.0 * math.pi * freq * (i / sample_rate)))
        buf.extend(struct.pack("<h", val))
    return bytes(buf)


# =============================================================================
# 1. KIỂM THỬ ĐỐI KHÁNG SQL INJECTION TRÊN /api/logs/sql_query
# =============================================================================


class TestSqlInjectionDestructiveAdversarial:
    """Thử nghiệm các vector SQL Injection phá hoại CSDL trên endpoint /api/logs/sql_query."""

    @pytest.mark.parametrize(
        "malicious_sql",
        [
            "DROP TABLE audit_logs;",
            "DROP TABLE users;",
            "DROP TABLE devices;",
            "UPDATE devices SET state = 'OFF';",
            "UPDATE users SET tier = 3 WHERE user_id = 'tuan_anh';",
            "INSERT INTO users (user_id, user_name, tier) VALUES ('hacker_m5', 'Hacker', 1);",
            "INSERT INTO audit_logs (summary) VALUES ('injected');",
            "ALTER TABLE devices ADD COLUMN hacked TEXT;",
            "DELETE FROM audit_logs;",
            "DELETE FROM users WHERE 1=1;",
            "CREATE TABLE evil_table (id INT, pwned TEXT);",
            "REPLACE INTO devices (device_id, device_name) VALUES ('door', 'pwned');",
            "ATTACH DATABASE ':memory:' AS evil;",
            "DETACH DATABASE evil;",
            "VACUUM;",
            "REINDEX;",
            # Thử nghiệm câu lệnh xếp chồng (Stacked Queries)
            "SELECT 1; DROP TABLE users;",
            "SELECT * FROM devices; UPDATE devices SET state='ON';",
            "SELECT count(*) FROM audit_logs; DELETE FROM audit_logs;",
            # Thử nghiệm chữ hoa chữ thường kết hợp khoảng trắng
            "   dRoP   TaBLe   audit_logs   ",
            "\n\tInSeRt   INTO  users VALUES('bad', 'Bad', 1)\n",
            "uPdAtE  devices  SET  state='ON'",
            # Thử nghiệm comment và subquery tricks
            "SELECT * FROM users WHERE user_id = 'tuan_anh'; -- DROP TABLE users;",
            "SELECT (SELECT count(*) FROM audit_logs); DROP TABLE devices;",
        ],
    )
    def test_sql_destructive_injection_blocked_100_pct(
        self, client: TestClient, malicious_sql: str
    ) -> None:
        """Gửi các payload SQL Injection phá hoại:

        Kỳ vọng:
        1. Tuyệt đối không gây sập HTTP 500.
        2. Bị chặn an toàn với `ok: False`.
        3. CSDL smarthome.db được bảo vệ nguyên vẹn 100%.
        """
        resp = client.post(
            "/api/logs/sql_query",
            json={"sql": malicious_sql, "limit": 10},
        )
        assert resp.status_code != 500, f"SQL '{malicious_sql}' gây sập HTTP 500!"
        data = resp.json()
        assert data.get("ok") is False, f"SQL phá hoại '{malicious_sql}' không bị chặn: {data}"
        err = data.get("error", "")
        assert (
            "Chế độ bảo vệ CSDL" in err
            or "Chỉ cho phép truy vấn đọc" in err
            or "Câu lệnh phải bắt đầu bằng" in err
            or "syntax error" in err.lower()
            or "readonly" in err.lower()
        ), f"Lỗi không chứa thông báo bảo vệ hợp lệ: {err}"

    def test_sql_database_remains_intact_after_attacks(self, client: TestClient) -> None:
        """Kiểm chứng trực tiếp trên file CSDL SQLite smarthome.db sau các đợt tấn công."""
        init_sqlite_database()
        conn = get_connection()
        try:
            # Xác nhận cả 8 bảng vẫn tồn tại nguyên vẹn
            tables = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
                ).fetchall()
            ]
            expected_tables = {
                "users",
                "voiceprints",
                "devices",
                "timers_pool",
                "rules_pool",
                "ir_remote_codes",
                "knowledge_rag",
                "audit_logs",
            }
            assert expected_tables.issubset(set(tables)), f"Bảng bị thiếu sau tấn công SQLi: {set(tables)}"

            # Xác nhận Chủ nhà Cấp 1 Nguyễn Tuấn Anh không bị sửa đổi
            owner_row = conn.execute(
                "SELECT user_id, full_name, tier FROM users WHERE user_id = 'tuan_anh';"
            ).fetchone()
            assert owner_row is not None, "Chủ nhà tuan_anh bị xóa!"
            assert owner_row[1] == "Nguyễn Tuấn Anh", f"Tên chủ nhà bị sửa: {owner_row[1]}"
            assert owner_row[2] == 1, f"Quyền Cấp 1 của chủ nhà bị hạ cấp: {owner_row[2]}"
        finally:
            conn.close()

    def test_sql_readonly_valid_queries_pass(self, client: TestClient) -> None:
        """Xác nhận các truy vấn đọc hợp lệ (SELECT, PRAGMA, EXPLAIN, WITH) vẫn hoạt động 100%."""
        valid_queries = [
            "SELECT count(*) AS total_users FROM users;",
            "SELECT device_id, device_name, state FROM devices LIMIT 5;",
            "PRAGMA table_info(audit_logs);",
            "EXPLAIN SELECT * FROM devices WHERE state = 'ON';",
            "WITH dev_count AS (SELECT count(*) AS c FROM devices) SELECT c FROM dev_count;",
        ]
        for v_sql in valid_queries:
            resp = client.post("/api/logs/sql_query", json={"sql": v_sql, "limit": 10})
            assert resp.status_code == 200, f"Query hợp lệ '{v_sql}' bị lỗi: {resp.text}"
            data = resp.json()
            assert data.get("ok") is True, f"Query hợp lệ '{v_sql}' trả về ok=False: {data}"
            assert "rows" in data


# =============================================================================
# 2. KIỂM THỬ ĐỐI KHÁNG FUZZING THAM SỐ LIMIT VÀ MIN_TIER
# =============================================================================


class TestParameterFuzzingLimitAndMinTier:
    """Fuzzing các tham số limit và min_tier bằng các giá trị dị dạng để phòng chống HTTP 500."""

    @pytest.mark.parametrize(
        "fuzzed_limit",
        [
            "abc",
            "{}",
            "null",
            "NaN",
            "nan",
            "Infinity",
            "inf",
            "1e99",
            "-1",
            "0",
            "\x00",
            "' OR 1=1; --",
            "!@#$%^&*()",
            [1, 2, 3],
            {"limit": 50},
            "9" * 2000,  # Vượt trần giới hạn int Python 3.11+
            None,
            "",
            "   ",
            12.345,
            -999999,
            0,
            1,
            100,
        ],
    )
    def test_sql_query_limit_parameter_fuzzing(
        self, client: TestClient, fuzzed_limit: Any
    ) -> None:
        """Gửi limit dị biệt vào /api/logs/sql_query -> không được sập HTTP 500."""
        resp = client.post(
            "/api/logs/sql_query",
            json={"sql": "SELECT 1 AS num;", "limit": fuzzed_limit},
        )
        assert resp.status_code != 500, f"Limit '{fuzzed_limit}' gây crash HTTP 500!"
        assert resp.status_code in (200, 400, 422)

    @pytest.mark.parametrize(
        "fuzzed_tier",
        [
            "abc",
            "{}",
            "null",
            "NaN",
            "nan",
            "1e99",
            "-1",
            "\x00",
            "' OR 1=1; --",
            "!@#$%^&*()",
            [1, 2],
            {"nested": 1},
            "9" * 2000,
            None,
            "",
            12.345,
            9999,
        ],
    )
    def test_knowledge_add_min_tier_parameter_fuzzing(
        self, client: TestClient, fuzzed_tier: Any
    ) -> None:
        """Gửi min_tier dị biệt vào /api/logs/knowledge/add -> không được sập HTTP 500."""
        resp = client.post(
            "/api/logs/knowledge/add",
            json={
                "topic": f"orthogonal_test_topic_{uuid.uuid4().hex[:6]}",
                "content": "Nội dung kiểm thử đối kháng tham số min_tier.",
                "keywords": "fuzz, test, security",
                "min_tier": fuzzed_tier,
            },
        )
        assert resp.status_code != 500, f"Min_tier '{fuzzed_tier}' gây crash HTTP 500!"
        assert resp.status_code in (200, 400, 422)


# =============================================================================
# 3. KIỂM THỬ ĐỐI KHÁNG LÀM SẠCH NHẬT KÝ (POST /api/logs/clear & SQLite WAL)
# =============================================================================


class TestLogsClearSyncAndIntegrity:
    """Kiểm thử tính triệt để và an toàn của thao tác POST /api/logs/clear trên cả .jsonl và SQLite."""

    def test_clear_logs_purges_both_jsonl_and_sqlite_audit_logs(
        self, client: TestClient
    ) -> None:
        """1. Ghi thêm 5 bản ghi kiểm toán mới.

        2. Gọi POST /api/logs/clear.
        3. Xác thực cả file system_audit_logs.jsonl và bảng audit_logs trong SQLite đều được làm sạch an toàn.
        """
        # Bước 1: Ghi một số bản ghi log mẫu
        for i in range(5):
            resp_app = client.post(
                "/api/logs/append",
                json={
                    "category": "DEVICE",
                    "event": f"Orthogonal test log {i}",
                    "actor": "Tester M5",
                    "detail": f"Detail content for test item {i}",
                    "level": "INFO",
                },
            )
            assert resp_app.status_code == 200

        # Kiểm tra trước khi xóa: SQLite audit_logs có dữ liệu
        conn = get_connection()
        try:
            count_before = conn.execute("SELECT count(*) FROM audit_logs;").fetchone()[0]
            assert count_before >= 5, f"Số bản ghi trước khi xóa quá ít: {count_before}"
        finally:
            conn.close()

        # Bước 2: Gọi POST /api/logs/clear
        resp_clear = client.post("/api/logs/clear")
        assert resp_clear.status_code == 200, f"Gọi /api/logs/clear thất bại: {resp_clear.text}"
        clear_data = resp_clear.json()
        assert clear_data.get("ok") is True

        # Bước 3: Kiểm chứng SQLite smarthome.db
        conn = get_connection()
        try:
            rows = conn.execute("SELECT event_type, summary, user_name FROM audit_logs;").fetchall()
            # Sau khi clear, chỉ còn lại bản ghi ghi nhận sự kiện logs_cleared
            assert len(rows) in (1, 2), f"Bảng audit_logs không được dọn sạch! Số dòng còn lại: {len(rows)}"
            event_types = [r[0] for r in rows]
            assert "logs_cleared" in event_types, f"Thiếu bản ghi kiểm toán logs_cleared: {event_types}"
        finally:
            conn.close()

        # Bước 4: Kiểm chứng file system_audit_logs.jsonl
        jsonl_path = DATA_DIR / "system_audit_logs.jsonl"
        assert jsonl_path.exists()
        lines = [ln.strip() for ln in jsonl_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        # File jsonl sau khi xóa chỉ chứa bản ghi logs_cleared vừa tạo
        assert len(lines) in (1, 2), f"Tệp jsonl không được làm sạch! Số dòng còn lại: {len(lines)}"
        last_entry = json.loads(lines[-1])
        assert last_entry.get("event_type") == "logs_cleared" or "dọn sạch" in last_entry.get("summary", "").lower()


# =============================================================================
# 4. KIỂM THỬ THU ÂM GIỌNG NÓI VỚI ALIAS audio_pcm_b64
# =============================================================================


class TestEnrollVoiceSampleAudioPcmB64Alias:
    """Kiểm thử gửi trường `audio_pcm_b64` lên POST /api/auth3/enroll_voice_sample."""

    def test_enroll_voice_sample_accepts_audio_pcm_b64_for_new_member(
        self, client: TestClient
    ) -> None:
        """Gửi audio_pcm_b64 chứa chuỗi PCM 16kHz thật cho một email thành viên hợp lệ."""
        test_email = "member_m5_test@gmail.com"
        mgr = get_auth_3layer_manager()
        mgr.add_family_email("tuan_anh", test_email, 2)

        # Sử dụng mẫu âm thanh thật đạt chuẩn từ test_audio (lặp 3 lần để đạt độ dài >2s)
        import wave
        import numpy as np
        wav_path = ROOT / "test_audio" / "giong_cap3_khach_c.wav"
        with wave.open(str(wav_path), "rb") as w:
            pcm_raw = w.readframes(w.getnframes())
        pcm_tiled = np.tile(np.frombuffer(pcm_raw, dtype=np.int16), 3).tobytes()
        pcm_b64 = base64.b64encode(pcm_tiled).decode("ascii")

        resp = client.post(
            "/api/auth3/enroll_voice_sample",
            json={
                "email": test_email,
                "audio_pcm_b64": pcm_b64,
                "source_device": "Microphone Web Audio 16kHz",
            },
        )
        assert resp.status_code == 200, f"Enroll thất bại: {resp.text}"
        data = resp.json()
        assert "ok" in data
        assert data.get("ok") is True
        assert data.get("status") == "DA_DAT"

    def test_enroll_voice_sample_rejects_duplicate_voice_of_owner(
        self, client: TestClient
    ) -> None:
        """Gửi giọng của Chủ nhà Cấp 1 (Nguyễn Tuấn Anh) trong audio_pcm_b64 khi đăng ký tài khoản Cấp 2.

        Kỳ vọng: Cổng chống trùng giọng kích hoạt, trả HTTP 400 và DUPLICATE_VOICE_REJECTED.
        """
        import wave
        test_email_c2 = "hacker_trying_duplicate@gmail.com"
        mgr = get_auth_3layer_manager()
        mgr.add_family_email("tuan_anh", test_email_c2, 2)

        # Đọc trực tiếp mẫu giọng Chủ nhà Cấp 1 từ test_audio/giong_1_chu_nha_mo_cua.wav
        wav_owner_path = ROOT / "test_audio" / "giong_1_chu_nha_mo_cua.wav"
        with wave.open(str(wav_owner_path), "rb") as w:
            pcm_owner = w.readframes(w.getnframes())

        pcm_b64 = base64.b64encode(pcm_owner).decode("ascii")

        resp = client.post(
            "/api/auth3/enroll_voice_sample",
            json={
                "email": test_email_c2,
                "audio_pcm_b64": pcm_b64,
                "source_device": "Microphone Web Audio 16kHz",
            },
        )
        assert resp.status_code == 400, f"Không từ chối trùng giọng: status={resp.status_code}, body={resp.text}"
        data = resp.json()
        assert data.get("ok") is False
        assert data.get("status") == "DUPLICATE_VOICE_REJECTED"
        assert "trùng" in data.get("message", "").lower() or "trùng" in data.get("error", "").lower()

    def test_enroll_voice_sample_corrupted_base64_handled_gracefully(
        self, client: TestClient
    ) -> None:
        """Gửi chuỗi base64 bị hỏng, rỗng hoặc dị dạng vào audio_pcm_b64 -> Không crash 500."""
        corrupted_payloads = [
            "???===not_valid_base64===",
            "",
            "   ",
            "12345",
            "\x00\x01\x02",
        ]
        for bad_b64 in corrupted_payloads:
            resp = client.post(
                "/api/auth3/enroll_voice_sample",
                json={
                    "email": "test_corrupted@gmail.com",
                    "audio_pcm_b64": bad_b64,
                },
            )
            assert resp.status_code != 500, f"Payload '{bad_b64}' gây sập HTTP 500!"
            data = resp.json()
            assert data.get("ok") is False, f"Payload hỏng lại thành công: {data}"
