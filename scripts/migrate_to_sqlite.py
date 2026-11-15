"""Idempotent, lossless migration of Smart Home JSON/JSONL/SQLite + GitHub CAS state into 3NF SQLite WAL."""

from __future__ import annotations

import argparse
import base64
import contextlib
import copy
import hashlib
import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
import wave
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.auth.sqlite_security_repo import (  # noqa: E402
    save_accounts_sqlite,
    save_invites_sqlite,
    save_owner_pin_sqlite,
    save_rate_limits_sqlite,
)
from simulator.db_migrations import (  # noqa: E402
    apply_schema_migrations,
    bootstrap_device_state_from_devices,
    dump_meta_json,
    open_wal_connection,
    resolve_sqlite_db_path,
    role_for_tier,
    run_write_transaction,
    table_row_counts,
)
from simulator.engine.constants_and_time import DEFAULT_DEVICES  # noqa: E402


def build_default_devices() -> dict[str, dict[str, Any]]:
    return copy.deepcopy(DEFAULT_DEVICES)


DEFAULT_ENV_PROD = pathlib.Path(r"C:\Users\LENOVO\.smarthome_server\.env.production")
DEFAULT_TARGET_DB = pathlib.Path(r"C:\Users\LENOVO\.smarthome_server\data\smarthome.db")
DEFAULT_SOURCE_DIR = ROOT / "simulator" / "data"
GITHUB_REPO_DEFAULT = "nep94121-lab/smart-home-security-state"

STATIC_ASSET_FILES: tuple[str, ...] = (
    "aoede_rejection_24k.wav",
    "aoede_repeat_24k.wav",
    "AOEDE_AUDIO_RECEIPT.json",
    "vietnamese_cohort_wespeaker.json",
    "knowledge_embeddings_cache.json",
    "knowledge_base.json",
    "ir_devices_db.json",
    "factory_default_rules.json",
    "custom_rules_overlay.json",
    "voiceprints.json",
    "esp8266_flash_replica.json",
)


def _load_env_file_if_present(env_path: pathlib.Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ and val and val != "[SENSITIVE]":
            os.environ[key] = val


def _resolve_github_token() -> str:
    tok = os.environ.get("SMARTHOME_SECURITY_TOKEN", "").strip()
    if tok and tok != "[SENSITIVE]":
        return tok
    try:
        out = subprocess.check_output(["gh", "auth", "token"], text=True, timeout=10).strip()
        if out:
            return out
    except Exception:
        pass
    return ""


def _unwrap_cas_payload(raw_bytes: bytes) -> dict[str, Any]:
    parsed = json.loads(raw_bytes.decode("utf-8"))
    if isinstance(parsed, dict) and "payload" in parsed and "revision" in parsed:
        inner = parsed["payload"]
        if isinstance(inner, str):
            try:
                decoded = json.loads(inner)
                if isinstance(decoded, dict):
                    return decoded
            except Exception:
                pass
            decoded_b64 = json.loads(base64.b64decode(inner).decode("utf-8"))
            return decoded_b64 if isinstance(decoded_b64, dict) else {}
        if isinstance(inner, dict):
            return inner
    return parsed if isinstance(parsed, dict) else {}


def _fetch_github_cas_file(repo: str, filename: str, token: str) -> dict[str, Any] | None:
    url = f"https://api.github.com/repos/{repo}/contents/{filename}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "SmartHome-SQLite-Migrator/1.0",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            meta = json.loads(resp.read().decode("utf-8"))
        content_b64 = str(meta.get("content") or "")
        if not content_b64:
            return None
        raw = base64.b64decode(content_b64)
        return _unwrap_cas_payload(raw)
    except Exception as exc:
        print(f"  [WARN] GitHub fetch {filename}: {exc}", file=sys.stderr)
        return None


def _read_wav_pcm_bytes(wav_path: pathlib.Path) -> tuple[bytes, int]:
    with wave.open(str(wav_path), "rb") as wf:
        return wf.readframes(wf.getnframes()), int(wf.getframerate())


def _copy_static_assets(source_dir: pathlib.Path, target_dir: pathlib.Path) -> list[str]:
    copied: list[str] = []
    if source_dir.resolve() == target_dir.resolve():
        return copied
    target_dir.mkdir(parents=True, exist_ok=True)
    for fname in STATIC_ASSET_FILES:
        src = source_dir / fname
        dst = target_dir / fname
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)
            copied.append(fname)
    return copied


def _copy_legacy_sqlite_data(source_db: pathlib.Path, target_conn: sqlite3.Connection) -> dict[str, int]:
    stats: dict[str, int] = {}
    if not source_db.exists() or source_db.resolve() == pathlib.Path(target_conn.execute("PRAGMA database_list").fetchone()[2]).resolve():
        return stats

    src_conn = open_wal_connection(source_db, readonly=True)
    try:
        src_tables = {
            str(r[0])
            for r in src_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }

        def _tx(c: sqlite3.Connection) -> None:
            now_ts = time.time()
            # 1. users
            if "users" in src_tables:
                cols = {r[1] for r in src_conn.execute("PRAGMA table_info(users)").fetchall()}
                rows = src_conn.execute("SELECT * FROM users").fetchall()
                cnt = 0
                for r in rows:
                    row_d = dict(r)
                    uid = str(row_d.get("user_id") or "").strip()
                    if not uid:
                        continue
                    tier = int(row_d.get("tier") or 3)
                    if tier not in (1, 2, 3):
                        tier = 3
                    rc = str(row_d.get("role_code") or row_d.get("role") or role_for_tier(tier))
                    if rc not in ("ADMIN", "MEMBER", "CHILD_GUEST"):
                        rc = role_for_tier(tier)
                    email = str(row_d.get("email") or "").strip().lower()
                    if email:
                        c.execute("UPDATE users SET email = '' WHERE lower(email) = ? AND user_id != ?", (email, uid))
                    c.execute(
                        """
                        INSERT INTO users (
                            user_id, full_name, role, tier, offline_allowed, created_by, updated_at,
                            email, role_code, password_salt, password_hash, password_updated_at,
                            permission_active, permission_status, is_allowlisted, is_active, created_at, account_meta_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(user_id) DO NOTHING
                        """,
                        (
                            uid,
                            str(row_d.get("full_name") or uid),
                            str(row_d.get("role") or rc),
                            tier,
                            int(row_d.get("offline_allowed") or 0),
                            str(row_d.get("created_by") or "SYSTEM"),
                            str(row_d.get("updated_at") or ""),
                            email if "email" in cols else "",
                            rc,
                            str(row_d.get("password_salt") or ""),
                            str(row_d.get("password_hash") or ""),
                            float(row_d.get("password_updated_at") or 0.0),
                            int(row_d.get("permission_active", 1)),
                            str(row_d.get("permission_status") or "ACTIVE"),
                            int(row_d.get("is_allowlisted", 1)),
                            int(row_d.get("is_active", 1)),
                            str(row_d.get("created_at") or row_d.get("updated_at") or ""),
                            str(row_d.get("account_meta_json") or "{}"),
                        ),
                    )
                    cnt += 1
                stats["copied_users"] = cnt

            valid_users = {str(r[0]) for r in c.execute("SELECT user_id FROM users").fetchall()}

            # 2. devices + device_state
            if "devices" in src_tables:
                d_rows = src_conn.execute("SELECT * FROM devices").fetchall()
                cnt = 0
                for r in d_rows:
                    rd = dict(r)
                    did = str(rd.get("device_id") or "")
                    if not did:
                        continue
                    tier = int(rd.get("min_tier_required") or 3)
                    c.execute(
                        """
                        INSERT INTO devices (
                            device_id, device_name, gpio_pin, state, min_tier_required,
                            offline_controllable, updated_at, min_role, room, device_type
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(device_id) DO UPDATE SET
                            state = excluded.state,
                            updated_at = excluded.updated_at
                        """,
                        (
                            did,
                            str(rd.get("device_name") or did),
                            str(rd.get("gpio_pin") or "GPIO"),
                            str(rd.get("state") or "OFF"),
                            tier,
                            int(rd.get("offline_controllable", 1)),
                            str(rd.get("updated_at") or ""),
                            str(rd.get("min_role") or role_for_tier(tier)),
                            str(rd.get("room") or "home"),
                            str(rd.get("device_type") or "switch"),
                        ),
                    )
                    c.execute(
                        """
                        INSERT OR IGNORE INTO device_state (device_id, state, version, updated_at)
                        VALUES (?, ?, 1, ?)
                        """,
                        (did, str(rd.get("state") or "OFF"), now_ts),
                    )
                    cnt += 1
                stats["copied_devices"] = cnt

            valid_devices = {str(r[0]) for r in c.execute("SELECT device_id FROM devices").fetchall()}

            # 3. voiceprints
            if "voiceprints" in src_tables:
                vp_rows = src_conn.execute("SELECT * FROM voiceprints").fetchall()
                cnt = 0
                for r in vp_rows:
                    rd = dict(r)
                    if str(rd.get("user_id") or "") not in valid_users:
                        continue
                    c.execute(
                        """
                        INSERT OR IGNORE INTO voiceprints (
                            voiceprint_id, user_id, f0_hz, centroid_hz,
                            embedding_26d_json, embedding_64d_json, sample_duration_sec, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(rd["voiceprint_id"]),
                            str(rd["user_id"]),
                            float(rd.get("f0_hz") or 0.0),
                            float(rd.get("centroid_hz") or 0.0),
                            str(rd.get("embedding_26d_json") or "[]"),
                            str(rd.get("embedding_64d_json") or "[]"),
                            float(rd.get("sample_duration_sec") or 5.0),
                            str(rd.get("updated_at") or ""),
                        ),
                    )
                    cnt += 1
                stats["copied_voiceprints"] = cnt

            # 4. knowledge_rag
            if "knowledge_rag" in src_tables:
                k_rows = src_conn.execute("SELECT * FROM knowledge_rag").fetchall()
                cnt = 0
                for r in k_rows:
                    rd = dict(r)
                    ub = rd.get("updated_by_user_id")
                    if ub and str(ub) not in valid_users:
                        ub = None
                    c.execute(
                        """
                        INSERT OR IGNORE INTO knowledge_rag (
                            doc_id, category, title, content, keywords_json, updated_by_user_id, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(rd["doc_id"]),
                            str(rd.get("category") or "general"),
                            str(rd.get("title") or ""),
                            str(rd.get("content") or ""),
                            str(rd.get("keywords_json") or "[]"),
                            ub,
                            str(rd.get("updated_at") or ""),
                        ),
                    )
                    cnt += 1
                stats["copied_knowledge_rag"] = cnt

            # 5. timers_pool & rules_pool & ir_remote_codes
            if "timers_pool" in src_tables:
                cnt = 0
                for r in src_conn.execute("SELECT * FROM timers_pool").fetchall():
                    rd = dict(r)
                    if str(rd.get("owner_user_id") or "") not in valid_users or str(rd.get("device_id") or "") not in valid_devices:
                        continue
                    c.execute(
                        """
                        INSERT OR IGNORE INTO timers_pool (
                            timer_id, owner_user_id, device_id, action, schedule_mode,
                            target_time_vn, repeat_rule, label_summary, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(rd["timer_id"]),
                            str(rd["owner_user_id"]),
                            str(rd["device_id"]),
                            str(rd.get("action") or ""),
                            str(rd.get("schedule_mode") or "once"),
                            str(rd.get("target_time_vn") or ""),
                            str(rd.get("repeat_rule") or "once"),
                            str(rd.get("label_summary") or ""),
                            str(rd.get("updated_at") or ""),
                        ),
                    )
                    cnt += 1
                stats["copied_timers_pool"] = cnt

            if "rules_pool" in src_tables:
                cnt = 0
                for r in src_conn.execute("SELECT * FROM rules_pool").fetchall():
                    rd = dict(r)
                    if str(rd.get("owner_user_id") or "") not in valid_users:
                        continue
                    tdid = rd.get("target_device_id")
                    if tdid and str(tdid) not in valid_devices:
                        tdid = None
                    c.execute(
                        """
                        INSERT OR IGNORE INTO rules_pool (
                            rule_id, owner_user_id, rule_category, trigger_expr,
                            target_device_id, target_action, bidirectional, else_action, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(rd["rule_id"]),
                            str(rd["owner_user_id"]),
                            str(rd.get("rule_category") or "custom"),
                            str(rd.get("trigger_expr") or ""),
                            tdid,
                            str(rd.get("target_action") or ""),
                            int(rd.get("bidirectional") or 0),
                            str(rd.get("else_action") or ""),
                            str(rd.get("updated_at") or ""),
                        ),
                    )
                    cnt += 1
                stats["copied_rules_pool"] = cnt

            if "ir_remote_codes" in src_tables:
                cnt = 0
                for r in src_conn.execute("SELECT * FROM ir_remote_codes").fetchall():
                    rd = dict(r)
                    did = rd.get("device_id")
                    if did and str(did) not in valid_devices:
                        did = None
                    c.execute(
                        """
                        INSERT OR IGNORE INTO ir_remote_codes (
                            ir_code_id, device_id, appliance_name, command_action,
                            protocol, hex_code, freq_khz, learned_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(rd["ir_code_id"]),
                            did,
                            str(rd.get("appliance_name") or ""),
                            str(rd.get("command_action") or ""),
                            str(rd.get("protocol") or "NEC"),
                            str(rd.get("hex_code") or ""),
                            int(rd.get("freq_khz") or 38),
                            str(rd.get("learned_at") or ""),
                        ),
                    )
                    cnt += 1
                stats["copied_ir_remote_codes"] = cnt

            # 6. user_sessions -> both user_sessions & sessions
            if "user_sessions" in src_tables:
                cnt = 0
                for r in src_conn.execute("SELECT * FROM user_sessions").fetchall():
                    rd = dict(r)
                    sid = str(rd.get("session_id") or "")
                    if not sid:
                        continue
                    tier = int(rd.get("tier") or 3)
                    if tier not in (1, 2, 3, 4):
                        tier = 3
                    c.execute(
                        """
                        INSERT OR IGNORE INTO user_sessions (
                            session_id, user_id, email, display_name, tier, role, created_at, expires_at, source
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            sid,
                            str(rd.get("user_id") or ""),
                            str(rd.get("email") or ""),
                            str(rd.get("display_name") or ""),
                            tier,
                            str(rd.get("role") or role_for_tier(tier)),
                            float(rd.get("created_at") or 0.0),
                            float(rd.get("expires_at") or 0.0),
                            str(rd.get("source") or "legacy"),
                        ),
                    )
                    c.execute(
                        """
                        INSERT OR IGNORE INTO sessions (
                            session_id, token_hash, user_id, email, display_name,
                            role_code, tier, source, invite_jti, created_at, expires_at, revoked_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?, NULL)
                        """,
                        (
                            sid,
                            hashlib.sha256(sid.encode("utf-8")).hexdigest(),
                            str(rd.get("user_id") or ""),
                            str(rd.get("email") or ""),
                            str(rd.get("display_name") or str(rd.get("user_id") or "")),
                            role_for_tier(tier),
                            tier,
                            str(rd.get("source") or "legacy"),
                            float(rd.get("created_at") or 0.0),
                            float(rd.get("expires_at") or 0.0),
                        ),
                    )
                    cnt += 1
                stats["copied_user_sessions"] = cnt

            # 7. audit_logs (preserve original log_id losslessly)
            if "audit_logs" in src_tables:
                cnt = 0
                for r in src_conn.execute("SELECT * FROM audit_logs ORDER BY log_id ASC").fetchall():
                    rd = dict(r)
                    uid = rd.get("user_id")
                    if uid and str(uid) not in valid_users:
                        uid = None
                    c.execute(
                        """
                        INSERT OR IGNORE INTO audit_logs (
                            log_id, ts_iso, time_vn, category, event_type,
                            user_id, user_name, tier, summary, details_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            int(rd["log_id"]),
                            str(rd.get("ts_iso") or ""),
                            str(rd.get("time_vn") or ""),
                            str(rd.get("category") or "SYSTEM_EVENT"),
                            str(rd.get("event_type") or "event"),
                            uid,
                            str(rd.get("user_name") or "Hệ thống"),
                            int(rd.get("tier") or 1),
                            str(rd.get("summary") or ""),
                            str(rd.get("details_json") or "{}"),
                        ),
                    )
                    cnt += 1
                stats["copied_audit_logs"] = cnt

        run_write_transaction(target_conn, _tx)
    finally:
        src_conn.close()
    return stats


def _import_local_json_and_jsonl(source_dir: pathlib.Path, target_conn: sqlite3.Connection, target_data_dir: pathlib.Path) -> dict[str, int]:
    stats: dict[str, int] = {}

    # 1. Local accounts_3layer.json (overlaid later by GitHub if newer)
    acc_file = source_dir / "accounts_3layer.json"
    if acc_file.exists():
        raw = json.loads(acc_file.read_text(encoding="utf-8"))
        accs = raw.get("accounts", []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
        if accs:
            _merge_accounts_into_conn(target_conn, accs)
            stats["local_accounts_merged"] = len(accs)

    # 2. Local system_audit_logs.jsonl (idempotent: only add rows not matching existing signature)
    jsonl_file = source_dir / "system_audit_logs.jsonl"
    if jsonl_file.exists():
        def _tx_logs(c: sqlite3.Connection) -> int:
            existing = {
                (str(r[0]), str(r[1]), str(r[2]), str(r[3]))
                for r in c.execute("SELECT ts_iso, event_type, user_name, summary FROM audit_logs").fetchall()
            }
            valid_users = {str(r[0]) for r in c.execute("SELECT user_id FROM users").fetchall()}
            added = 0
            for raw_line in jsonl_file.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                if not isinstance(item, dict):
                    continue
                ts_iso = str(item.get("ts_iso") or "")
                ev = str(item.get("event_type") or item.get("category") or "event")
                uname = str(item.get("user") or item.get("user_name") or "Hệ thống")
                summ = str(item.get("summary") or "")
                sig = (ts_iso, ev, uname, summ)
                if sig in existing:
                    continue
                existing.add(sig)
                uid = item.get("user_id")
                if uid and str(uid) not in valid_users:
                    uid = None
                c.execute(
                    """
                    INSERT INTO audit_logs (
                        ts_iso, time_vn, category, event_type, user_id, user_name, tier, summary, details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ts_iso,
                        str(item.get("time_vn") or ""),
                        str(item.get("category") or "SYSTEM_EVENT"),
                        ev,
                        uid,
                        uname,
                        int(item.get("tier") or 1),
                        summ,
                        json.dumps(item.get("details") if isinstance(item.get("details"), dict) else {}, ensure_ascii=False),
                    ),
                )
                added += 1
            return added

        stats["jsonl_audit_logs_added"] = run_write_transaction(target_conn, _tx_logs)

    # 3. Pre-populate ir_remote_codes from ir_devices_db.json
    ir_file = source_dir / "ir_devices_db.json"
    if ir_file.exists():
        ir_obj = json.loads(ir_file.read_text(encoding="utf-8"))
        if isinstance(ir_obj, dict):
            def _tx_ir(c: sqlite3.Connection) -> int:
                valid_devices = {str(r[0]) for r in c.execute("SELECT device_id FROM devices").fetchall()}
                added = 0
                now_iso = time.strftime("%Y-%m-%dT%H:%M:%S+07:00", time.localtime())
                for app_key, app_data in ir_obj.items():
                    if not isinstance(app_data, dict):
                        continue
                    did = app_data.get("device_id")
                    if did and str(did) not in valid_devices:
                        did = None
                    cmds = app_data.get("commands") or {}
                    freq = int(app_data.get("carrier_khz") or 38)
                    if isinstance(cmds, dict):
                        for cmd_name, cmd_val in cmds.items():
                            code_id = f"ir_{app_key}_{cmd_name}"
                            proto = str(cmd_val.get("protocol") or "NEC") if isinstance(cmd_val, dict) else "NEC"
                            hex_c = str(cmd_val.get("hex") or cmd_val.get("hex_code") or json.dumps(cmd_val, ensure_ascii=False)) if isinstance(cmd_val, dict) else str(cmd_val)
                            c.execute(
                                """
                                INSERT OR IGNORE INTO ir_remote_codes (
                                    ir_code_id, device_id, appliance_name, command_action, protocol, hex_code, freq_khz, learned_at
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                (code_id, did, str(app_data.get("device_name") or app_key), str(cmd_name), proto, hex_c, freq, now_iso),
                            )
                            added += 1
                return added

            stats["ir_codes_seeded"] = run_write_transaction(target_conn, _tx_ir)

    # 4. Pre-populate aoede_audio_cache with local verified Aoede WAVs
    receipt_file = source_dir / "AOEDE_AUDIO_RECEIPT.json"
    if receipt_file.exists():
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
        phrases = receipt.get("phrases") or {}
        if isinstance(phrases, dict):
            def _tx_aoede(c: sqlite3.Connection) -> int:
                added = 0
                now_ts = time.time()
                for pinfo in phrases.values():
                    if not isinstance(pinfo, dict):
                        continue
                    phrase_txt = str(pinfo.get("phrase_text") or "").strip()
                    fname = str(pinfo.get("filename") or "").strip()
                    wav_p = source_dir / fname
                    if not phrase_txt or not wav_p.exists():
                        continue
                    pcm_bytes, sr = _read_wav_pcm_bytes(wav_p)
                    if not pcm_bytes:
                        continue
                    norm = " ".join(phrase_txt.lower().split())
                    cache_key = hashlib.sha256(f"Aoede:{norm}".encode("utf-8")).hexdigest()[:32]
                    c.execute(
                        """
                        INSERT INTO aoede_audio_cache (
                            cache_key, phrase_norm, voice_name, model_id, sample_rate, pcm_bytes, created_at
                        ) VALUES (?, ?, 'Aoede', ?, ?, ?, ?)
                        ON CONFLICT(cache_key) DO UPDATE SET
                            pcm_bytes = excluded.pcm_bytes,
                            sample_rate = excluded.sample_rate
                        """,
                        (cache_key, norm, str(receipt.get("generator_model") or "gemini-3.8-live"), sr, sqlite3.Binary(pcm_bytes), now_ts),
                    )
                    added += 1
                return added

            stats["aoede_cache_seeded"] = run_write_transaction(target_conn, _tx_aoede)

    # 5. Archive local metadata JSONs in system_kv_meta (no secrets)
    meta_files = (
        "voiceprints.json",
        "invite_links_3layer.json",
        "auth_3layer_events.json",
        "custom_rules_overlay.json",
        "factory_default_rules.json",
        "esp8266_flash_replica.json",
        "AOEDE_AUDIO_RECEIPT.json",
    )
    def _tx_meta(c: sqlite3.Connection) -> int:
        cnt = 0
        for fn in meta_files:
            p = source_dir / fn
            if p.exists():
                with contextlib.suppress(Exception):
                    dump_meta_json(c, f"migrated_{fn}", json.loads(p.read_text(encoding="utf-8")))
                    cnt += 1
        return cnt

    stats["meta_docs_archived"] = run_write_transaction(target_conn, _tx_meta)
    return stats


def _merge_accounts_into_conn(conn: sqlite3.Connection, accounts: list[dict[str, Any]]) -> int:
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S+07:00", time.localtime())
    now_ts = time.time()

    def _tx(c: sqlite3.Connection) -> int:
        cnt = 0
        for acc in accounts:
            if not isinstance(acc, dict):
                continue
            uid = str(acc.get("account_id") or acc.get("user_id") or acc.get("id") or "").strip()
            if not uid:
                continue
            tier = int(acc.get("tier") or 3)
            if tier not in (1, 2, 3):
                tier = 3
            rc = role_for_tier(tier)
            email = str(acc.get("email") or "").strip().lower()
            if email:
                c.execute("UPDATE users SET email = '' WHERE lower(email) = ? AND user_id != ?", (email, uid))
            c.execute(
                """
                INSERT INTO users (
                    user_id, full_name, role, tier, offline_allowed, created_by, updated_at,
                    email, role_code, password_salt, password_hash, password_updated_at,
                    permission_active, permission_status, is_allowlisted, is_active, created_at, account_meta_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    full_name = excluded.full_name,
                    role = excluded.role,
                    tier = excluded.tier,
                    offline_allowed = excluded.offline_allowed,
                    updated_at = excluded.updated_at,
                    email = excluded.email,
                    role_code = excluded.role_code,
                    password_salt = CASE WHEN excluded.password_salt != '' THEN excluded.password_salt ELSE users.password_salt END,
                    password_hash = CASE WHEN excluded.password_hash != '' THEN excluded.password_hash ELSE users.password_hash END,
                    password_updated_at = CASE WHEN excluded.password_updated_at > 0 THEN excluded.password_updated_at ELSE users.password_updated_at END,
                    permission_active = excluded.permission_active,
                    permission_status = excluded.permission_status,
                    account_meta_json = excluded.account_meta_json
                """,
                (
                    uid,
                    str(acc.get("display_name") or acc.get("full_name") or uid),
                    rc,
                    tier,
                    1 if tier in (1, 2) else 0,
                    str(acc.get("invited_by") or "SYSTEM"),
                    now_iso,
                    email,
                    rc,
                    str(acc.get("password_salt") or ""),
                    str(acc.get("password_hash") or ""),
                    float(acc.get("password_updated_at") or now_ts),
                    1 if acc.get("permission_active", True) else 0,
                    str(acc.get("permission_status") or ("ACTIVE" if acc.get("permission_active", True) else "REVOKED")),
                    str(acc.get("created_at") or now_iso),
                    json.dumps(acc, ensure_ascii=False),
                ),
            )
            p_otp = acc.get("pending_otp")
            if email and isinstance(p_otp, dict) and p_otp.get("otp_hash"):
                chal_id = str(p_otp.get("challenge_id") or f"login_{email}")
                c.execute(
                    """
                    INSERT INTO otp_challenges (
                        challenge_id, email, purpose, otp_salt, otp_hash,
                        issued_at, expires_at, used, failed_attempts, meta_json
                    ) VALUES (?, ?, 'login', ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(challenge_id) DO UPDATE SET
                        otp_salt = excluded.otp_salt,
                        otp_hash = excluded.otp_hash,
                        issued_at = excluded.issued_at,
                        expires_at = excluded.expires_at,
                        used = excluded.used,
                        failed_attempts = excluded.failed_attempts
                    """,
                    (
                        chal_id,
                        email,
                        str(p_otp.get("otp_salt") or ""),
                        str(p_otp.get("otp_hash") or ""),
                        float(p_otp.get("created_at") or now_ts),
                        float(p_otp.get("expires_at") or now_ts + 300.0),
                        1 if p_otp.get("used") else 0,
                        int(len(acc.get("otp_failed_verify_attempts") or [])),
                        json.dumps({"account_id": uid}, ensure_ascii=False),
                    ),
                )
            cnt += 1
        return cnt

    return run_write_transaction(conn, _tx)


def _apply_github_device_state(conn: sqlite3.Connection, shared_doc: dict[str, Any]) -> int:
    devices_map = shared_doc.get("devices") if isinstance(shared_doc.get("devices"), dict) else {}
    now_ts = time.time()
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S+07:00", time.localtime())
    defaults = build_default_devices()

    def _tx(c: sqlite3.Connection) -> int:
        cnt = 0
        for did, raw_entry in devices_map.items():
            if not isinstance(raw_entry, dict):
                continue
            dflt = defaults.get(did, {})
            st = str(raw_entry.get("state") or dflt.get("state") or "OFF")
            ver = int(raw_entry.get("version") or 1)
            upd = float(raw_entry.get("updated_at") or now_ts)
            c.execute(
                """
                INSERT INTO devices (
                    device_id, device_name, gpio_pin, state, min_tier_required,
                    offline_controllable, updated_at, min_role, room, device_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    state = excluded.state,
                    updated_at = excluded.updated_at
                """,
                (
                    did,
                    str(dflt.get("name") or did),
                    "GPIO",
                    st,
                    1 if did in ("main_door", "alarm_siren") else (2 if did in ("ac", "garden_pump") else 3),
                    0 if did in ("main_door", "alarm_siren") else 1,
                    now_iso,
                    role_for_tier(1 if did in ("main_door", "alarm_siren") else (2 if did in ("ac", "garden_pump") else 3)),
                    str(dflt.get("room") or "home"),
                    str(dflt.get("type") or "switch"),
                ),
            )
            c.execute(
                """
                INSERT INTO device_state (
                    device_id, state, version, updated_at,
                    last_client_id, last_client_seq, last_client_ts_ms,
                    last_request_id, last_requested_state, client_seqs_json, extra_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    state = excluded.state,
                    version = CASE WHEN excluded.version > device_state.version THEN excluded.version ELSE device_state.version END,
                    updated_at = excluded.updated_at,
                    last_client_id = excluded.last_client_id,
                    last_client_seq = excluded.last_client_seq,
                    last_client_ts_ms = excluded.last_client_ts_ms,
                    last_request_id = excluded.last_request_id,
                    last_requested_state = excluded.last_requested_state,
                    client_seqs_json = excluded.client_seqs_json,
                    extra_json = excluded.extra_json
                """,
                (
                    did,
                    st,
                    ver,
                    upd,
                    str(raw_entry.get("last_client_id") or ""),
                    int(raw_entry.get("last_client_seq") or 0),
                    int(raw_entry.get("last_client_ts_ms") or 0),
                    str(raw_entry.get("last_request_id") or ""),
                    str(raw_entry.get("last_requested_state") or ""),
                    json.dumps(raw_entry.get("client_seqs") or {}, ensure_ascii=False),
                    json.dumps({k: v for k, v in raw_entry.items() if k not in {
                        "state", "version", "updated_at", "last_client_id", "last_client_seq",
                        "last_client_ts_ms", "last_request_id", "last_requested_state", "client_seqs"
                    }}, ensure_ascii=False),
                ),
            )
            cnt += 1

        dht = shared_doc.get("dht11_telemetry") if isinstance(shared_doc.get("dht11_telemetry"), dict) else {}
        soil = shared_doc.get("soil_moisture_telemetry") if isinstance(shared_doc.get("soil_moisture_telemetry"), dict) else {}
        rev_seq = int(shared_doc.get("revision_seq") or 0)
        rev_ts = int(shared_doc.get("revision_ts_ns") or 0)
        c.execute(
            """
            INSERT INTO system_state_meta (
                id, revision_seq, revision_ts_ns, server_connected, pump_manual_override_off,
                dht_temp_c, dht_hum_pct, soil_moisture_pct, dht11_json, soil_moisture_json, updated_at
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                revision_seq = CASE WHEN excluded.revision_seq > system_state_meta.revision_seq THEN excluded.revision_seq ELSE system_state_meta.revision_seq END,
                revision_ts_ns = CASE WHEN excluded.revision_ts_ns > system_state_meta.revision_ts_ns THEN excluded.revision_ts_ns ELSE system_state_meta.revision_ts_ns END,
                server_connected = excluded.server_connected,
                pump_manual_override_off = excluded.pump_manual_override_off,
                dht_temp_c = excluded.dht_temp_c,
                dht_hum_pct = excluded.dht_hum_pct,
                soil_moisture_pct = excluded.soil_moisture_pct,
                dht11_json = excluded.dht11_json,
                soil_moisture_json = excluded.soil_moisture_json,
                updated_at = excluded.updated_at
            """,
            (
                rev_seq,
                rev_ts,
                1 if shared_doc.get("server_connected", True) else 0,
                1 if shared_doc.get("pump_manual_override_off", False) else 0,
                dht.get("temperature_c"),
                dht.get("humidity_pct"),
                soil.get("moisture_pct"),
                json.dumps(dht, ensure_ascii=False),
                json.dumps(soil, ensure_ascii=False),
                now_ts,
            ),
        )
        return cnt

    return run_write_transaction(conn, _tx)


def migrate_all(
    target_db: pathlib.Path,
    source_dir: pathlib.Path,
    *,
    fetch_github: bool = True,
    seed_assets: bool = True,
    upgrade_repo_db: bool = True,
) -> dict[str, Any]:
    if fetch_github and "pytest" not in sys.modules and not os.environ.get("PYTEST_CURRENT_TEST"):
        _load_env_file_if_present(DEFAULT_ENV_PROD)
    target_db = pathlib.Path(target_db)
    target_dir = target_db.parent
    source_dir = pathlib.Path(source_dir)
    source_db = source_dir / "smarthome.db"

    before_source_counts: dict[str, int] = {}
    if source_db.exists():
        s_conn = open_wal_connection(source_db, readonly=True)
        try:
            before_source_counts = table_row_counts(s_conn)
        finally:
            s_conn.close()

    before_target_counts: dict[str, int] = {}
    if target_db.exists():
        t_ro = open_wal_connection(target_db, readonly=True)
        try:
            before_target_counts = table_row_counts(t_ro)
        finally:
            t_ro.close()

    copied_assets = _copy_static_assets(source_dir, target_dir) if seed_assets else []

    conn = open_wal_connection(target_db, readonly=False)
    try:
        schema_version = apply_schema_migrations(conn)
        run_write_transaction(conn, lambda c: bootstrap_device_state_from_devices(c, build_default_devices()))
        sqlite_copy_stats = _copy_legacy_sqlite_data(source_db, conn)
        local_json_stats = _import_local_json_and_jsonl(source_dir, conn, target_dir)
    finally:
        conn.close()

    github_stats: dict[str, Any] = {}
    if fetch_github:
        repo = os.environ.get("SMARTHOME_SECURITY_REPO", GITHUB_REPO_DEFAULT).strip() or GITHUB_REPO_DEFAULT
        token = _resolve_github_token()

        # Overlay auth accounts (preserving seed users not listed)
        gh_accounts = _fetch_github_cas_file(repo, "auth3_accounts_state.json", token)
        if gh_accounts and isinstance(gh_accounts.get("accounts"), list):
            c2 = open_wal_connection(target_db, readonly=False)
            try:
                github_stats["auth3_accounts_merged"] = _merge_accounts_into_conn(c2, gh_accounts["accounts"])
            finally:
                c2.close()

        gh_invites = _fetch_github_cas_file(repo, "guest_invites.json", token)
        if gh_invites:
            invs = gh_invites.get("invites") if isinstance(gh_invites.get("invites"), list) else []
            save_invites_sqlite(json.dumps({"invites": invs}, ensure_ascii=False).encode("utf-8"), data_dir=target_dir)
            github_stats["guest_invites_synced"] = len(invs)

        gh_limits = _fetch_github_cas_file(repo, "login_rate_limit.json", token)
        if gh_limits:
            buckets = gh_limits.get("buckets") if isinstance(gh_limits.get("buckets"), dict) else {}
            save_rate_limits_sqlite(json.dumps({"buckets": buckets}, ensure_ascii=False).encode("utf-8"), data_dir=target_dir)
            github_stats["rate_limit_buckets_synced"] = len(buckets)

        gh_pin = _fetch_github_cas_file(repo, "owner_pin.json", token)
        if gh_pin:
            save_owner_pin_sqlite(json.dumps(gh_pin, ensure_ascii=False).encode("utf-8"), data_dir=target_dir)
            github_stats["owner_pin_synced"] = 1

        gh_shared = _fetch_github_cas_file(repo, "shared_device_state.json", token)
        if gh_shared:
            c3 = open_wal_connection(target_db, readonly=False)
            try:
                github_stats["shared_devices_synced"] = _apply_github_device_state(c3, gh_shared)
                github_stats["shared_revision_seq"] = int(gh_shared.get("revision_seq") or 0)
            finally:
                c3.close()

    if upgrade_repo_db and source_db.exists():
        src_rw = open_wal_connection(source_db, readonly=False)
        try:
            apply_schema_migrations(src_rw)
            run_write_transaction(src_rw, lambda c: bootstrap_device_state_from_devices(c, build_default_devices()))
        finally:
            src_rw.close()

    # Final verification on target DB
    vconn = open_wal_connection(target_db, readonly=False)
    try:
        vconn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        integrity = str(vconn.execute("PRAGMA integrity_check;").fetchone()[0])
        fk_errors = [dict(r) for r in vconn.execute("PRAGMA foreign_key_check;").fetchall()]
        journal_mode = str(vconn.execute("PRAGMA journal_mode;").fetchone()[0]).upper()
        after_target_counts = table_row_counts(vconn)
    finally:
        vconn.close()

    return {
        "ok": integrity.lower() == "ok" and len(fk_errors) == 0,
        "target_db": str(target_db),
        "schema_version": schema_version,
        "journal_mode": journal_mode,
        "integrity_check": integrity,
        "foreign_key_errors": fk_errors,
        "copied_static_assets": copied_assets,
        "before_source_counts": before_source_counts,
        "before_target_counts": before_target_counts,
        "sqlite_copy_stats": sqlite_copy_stats,
        "local_json_stats": local_json_stats,
        "github_stats": github_stats,
        "after_target_counts": after_target_counts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate Smart Home state into normalized 3NF SQLite WAL.")
    parser.add_argument("--target-db", type=pathlib.Path, default=DEFAULT_TARGET_DB)
    parser.add_argument("--source-dir", type=pathlib.Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--no-fetch-github", action="store_true")
    parser.add_argument("--no-seed-assets", action="store_true")
    parser.add_argument("--no-upgrade-repo-db", action="store_true")
    parser.add_argument("--verify-out", type=pathlib.Path, default=None)
    args = parser.parse_args()

    report = migrate_all(
        target_db=args.target_db,
        source_dir=args.source_dir,
        fetch_github=not args.no_fetch_github,
        seed_assets=not args.no_seed_assets,
        upgrade_repo_db=not args.no_upgrade_repo_db,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.verify_out is not None:
        args.verify_out.parent.mkdir(parents=True, exist_ok=True)
        args.verify_out.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
