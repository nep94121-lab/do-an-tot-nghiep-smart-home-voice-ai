"""TDD Security Hardening Test Suite for Branch p7-sec.

Covers all 6 security hardening requirements:
1. Wrong password for owner (including removed fallback passwords) is rejected;
   missing password_hash requires OTP / forgot-password reset flow.
2. Owner cannot skip voice verification or duplicate-voice check.
3. Unknown / unrecognised speaker or role gets NO device control (rejected with 403 / ok=False).
4. Central config simulator/config/voice_auth.json holds owner_id, owner_email,
   role_map, threshold_mel (0.88), and threshold_deep (0.80).
5. Voiceprints are stored only server-side and never returned in any API response;
   no sample-name shortcut (owner_voice_1, user_voice_thanh_vien_a, user_voice_khach_c)
   or client-supplied voiceprint/level is trusted.
6. Codebase scan confirms zero removed fallback password literals in app source,
   frontend, docs, and data files, plus SQL query table isolation.
"""

from __future__ import annotations

import asyncio
import base64
import json
import pathlib
import secrets
import sys
import wave
from typing import Any

import numpy as np
import pytest
from starlette.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator.api import routes_devices
from simulator.auth.constants_and_crypto import hash_password
from simulator.auth_3layer import ThreeLayerAuthManager, get_auth_3layer_manager
from simulator.rule_engine import SmartHomeEngine as RuleEngine
from simulator.server import app

# Base64-encoded representations of removed fallback passwords so that
# no plaintext password literal appears anywhere in the repository.
_REMOVED_FALLBACK_B64 = (
    "MTIzNDU2",          # 6-digit numeric fallback
    "VHVhbkFuaEAyMDI2",  # legacy owner fallback
    "R2lhRGluaEAxMjM=",  # legacy tier-2 fallback A
    "R2lhRGluaEA0NTY=",  # legacy tier-2 fallback B
    "S2hhY2hAMTIz",      # legacy tier-3 fallback A
    "S2hhY2hANzg5",      # legacy tier-3 fallback B
)


def _decoded_removed_fallbacks() -> list[str]:
    return [base64.b64decode(item.encode("ascii")).decode("utf-8") for item in _REMOVED_FALLBACK_B64]


def _load_wav_pcm16k(filename: str) -> bytes:
    wav_path = ROOT / "test_audio" / filename
    if not wav_path.exists():
        wav_path = ROOT / "test_audio" / "cac_cau_lenh_cua_sep" / filename
    with wave.open(str(wav_path), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
    arr = np.frombuffer(raw, dtype=np.int16)
    return np.concatenate([arr, arr, arr]).tobytes()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# ============================================================================
# 1. HARDCODED FALLBACK PASSWORDS REMOVED & OWNER HASH-ONLY LOGIN
# ============================================================================


def test_owner_wrong_and_removed_fallback_passwords_rejected(client: TestClient, tmp_path: pathlib.Path) -> None:
    """Owner login must reject wrong passwords, all removed fallback passwords,
    and passwordless login_method bypasses; must only accept stored hashed password
    set via OTP reset flow."""
    mgr = get_auth_3layer_manager()
    owner_acc = mgr.find_account("tuan_anh")
    assert owner_acc is not None
    owner_email = owner_acc["email"]

    # 1. Every removed fallback password must be rejected on /api/auth3/layer1_login
    for old_pw in _decoded_removed_fallbacks():
        resp = client.post(
            "/api/auth3/layer1_login",
            json={
                "email": owner_email,
                "password": old_pw,
                "login_method": "password",
                "send_gmail": False,
            },
        )
        data = resp.json()
        assert data.get("ok") is False, f"Removed fallback password was accepted for owner! Response: {data}"

    # 2. Arbitrary wrong password must be rejected
    resp_wrong = client.post(
        "/api/auth3/layer1_login",
        json={
            "email": owner_email,
            "password": "CompletelyWrongPassword_" + secrets.token_hex(6),
            "login_method": "password",
            "send_gmail": False,
        },
    )
    assert resp_wrong.json().get("ok") is False

    # 3. Attempting to bypass owner password check via login_method="google_oauth" must be rejected
    resp_bypass = client.post(
        "/api/auth3/layer1_login",
        json={
            "email": owner_email,
            "password": "",
            "login_method": "google_oauth",
            "send_gmail": False,
        },
    )
    assert resp_bypass.json().get("ok") is False, "Owner must not bypass password check via login_method=google_oauth"

    # 4. If stored password_hash is missing, login must fail and direct to OTP forgot-password reset
    orig_hash = owner_acc.get("password_hash", "")
    try:
        owner_acc["password_hash"] = ""
        resp_missing = client.post(
            "/api/auth3/layer1_login",
            json={
                "email": owner_email,
                "password": secrets.token_urlsafe(12),
                "login_method": "password",
                "send_gmail": False,
            },
        )
        d_missing = resp_missing.json()
        assert d_missing.get("ok") is False
        assert d_missing.get("needs_password_reset") is True

        # Use the OTP / forgot-password flow for a one-time secure reset
        otp_req = client.post(
            "/api/auth3/forgot_password_send_otp",
            json={"email": owner_email, "send_gmail": False},
        ).json()
        assert otp_req.get("ok") is True
        otp_code = mgr.pending_otps[owner_email.lower()]["otp_code"]

        ephemeral_pw = "Sec_" + secrets.token_urlsafe(14) + "!9"
        reset_res = client.post(
            "/api/auth3/forgot_password_reset",
            json={
                "email": owner_email,
                "otp_code": otp_code,
                "new_password": ephemeral_pw,
                "confirm_password": ephemeral_pw,
            },
        ).json()
        assert reset_res.get("ok") is True

        # Now login with the newly hashed password succeeds
        resp_ok = client.post(
            "/api/auth3/layer1_login",
            json={
                "email": owner_email,
                "password": ephemeral_pw,
                "login_method": "password",
                "send_gmail": False,
            },
        )
        assert resp_ok.json().get("ok") is True

        # And removed fallback passwords are still rejected
        for old_pw in _decoded_removed_fallbacks():
            r_old = client.post(
                "/api/auth3/layer1_login",
                json={
                    "email": owner_email,
                    "password": old_pw,
                    "login_method": "password",
                    "send_gmail": False,
                },
            )
            assert r_old.json().get("ok") is False
    finally:
        owner_acc["password_hash"] = orig_hash


# ============================================================================
# 2. OWNER CANNOT SKIP VOICE VERIFICATION OR DUPLICATE-VOICE CHECK
# ============================================================================


def test_owner_cannot_skip_voice_verification_or_duplicate_check(client: TestClient) -> None:
    """Owner (tuan_anh / tier 1) must not skip voice verification or duplicate-voice checks."""
    mgr = get_auth_3layer_manager()
    owner_acc = mgr.find_account("tuan_anh")
    assert owner_acc is not None
    owner_email = owner_acc["email"]

    # 1. Calling /api/auth3/layer3_voice for owner with empty audio must be rejected (no fabricated 126Hz pass)
    res_l3_empty = client.post(
        "/api/auth3/layer3_voice",
        json={
            "email": owner_email,
            "mode": "recognize",
            "audio_pcm_b64": "",
            "spoken_command": "Mở cửa chính",
        },
    )
    assert res_l3_empty.json().get("ok") is False, "Owner passed Layer 3 voice verification with empty audio!"

    # 2. Calling /api/auth3/enroll_first_page_voice for owner with empty audio must be rejected
    #    (must NOT fall back to owner_voice_1 stored embedding)
    res_enroll_empty = client.post(
        "/api/auth3/enroll_first_page_voice",
        json={
            "email": owner_email,
            "tier": 1,
            "display_name": "Nguyễn Tuấn Anh",
            "audio_pcm_b64": "",
        },
    )
    assert res_enroll_empty.json().get("ok") is False, "Owner enrolled voice with empty audio via owner_voice_1 fallback!"

    # 3. Calling /api/voice_auth/enroll_tier_pcm for owner with empty audio must be rejected
    res_tier_empty = client.post(
        "/api/voice_auth/enroll_tier_pcm",
        json={
            "email": owner_email,
            "tier": 1,
            "user_id": "tuan_anh",
            "audio_pcm_b64": "",
        },
    )
    assert res_tier_empty.json().get("ok") is False, "Owner enrolled tier PCM with empty audio!"

    # 4. Duplicate-voice check must also run for owner: if a Tier 2 member is enrolled
    #    with giong_cap2_thanh_vien_a.wav, and owner then tries to enroll with that
    #    same Tier 2 member's voice, owner must be blocked as duplicate!
    member_pcm = _load_wav_pcm16k("giong_cap2_thanh_vien_a.wav")
    member_b64 = base64.b64encode(member_pcm).decode("ascii")

    from simulator.api.routes_auth import _BOOT_VOICE_AUTH

    try:
        res_m_enroll = client.post(
            "/api/auth3/enroll_first_page_voice",
            json={
                "email": "thanhviena.hust@gmail.com",
                "tier": 2,
                "display_name": "Thành viên A",
                "audio_pcm_b64": member_b64,
            },
        )
        assert res_m_enroll.json().get("ok") is True

        res_dup = client.post(
            "/api/auth3/enroll_first_page_voice",
            json={
                "email": owner_email,
                "tier": 1,
                "display_name": "Nguyễn Tuấn Anh",
                "audio_pcm_b64": member_b64,
            },
        )
        d_dup = res_dup.json()
        assert d_dup.get("ok") is False, f"Owner skipped duplicate voice check against Tier 2 member voice! {d_dup}"
        assert d_dup.get("status") in ("DUPLICATE_VOICE_REJECTED", "TRUNG_GIONG") or d_dup.get("duplicate_blocked") is True
    finally:
        _BOOT_VOICE_AUTH.profiles.pop("user_voice_thanh_vien_a", None)


# ============================================================================
# 3. UNKNOWN / UNRECOGNISED SPEAKER GETS NO DEVICE CONTROL (REJECTED)
# ============================================================================


def test_unknown_or_unrecognised_speaker_and_role_rejected_no_device_control(client: TestClient) -> None:
    """Unknown or unrecognised speaker/role must NOT default to tuan_anh and must
    be rejected with zero device control (not even Tier 3 light/fan)."""
    # 1. /api/session/role with missing, empty, or unknown role must be rejected (HTTP 403 / ok=False)
    for bad_payload in [
        {},
        {"role": ""},
        {"role": "unknown"},
        {"role": "UNKNOWN"},
        {"role": "stranger"},
        {"role": "hacker_role_999"},
        {"email": "stranger_not_in_db@example.com"},
    ]:
        r_role = client.post("/api/session/role", json=bad_payload)
        d_role = r_role.json()
        assert r_role.status_code == 403, f"/api/session/role accepted {bad_payload} with status {r_role.status_code}: {d_role}"
        assert d_role.get("ok") is False
        assert d_role.get("active_user_id") != "tuan_anh"

    # 2. RuleEngine.set_active_user with unknown role must set role to UNKNOWN and deny all devices
    eng = RuleEngine()
    eng.set_active_user("unknown_intruder_xyz")
    assert eng.current_role == "UNKNOWN"
    assert eng.current_user_id != "tuan_anh"

    for dev_id in ("main_door", "alarm_buzzer", "light_living", "fan_bedroom"):
        perm = eng.check_device_permission(dev_id, "on")
        assert perm.get("allowed") is False, f"UNKNOWN role was allowed to control {dev_id}!"
        act = asyncio.run(eng.execute_device_action(dev_id, "on", reason="Unknown speaker test"))
        assert act.get("ok") is False, f"UNKNOWN role executed action on {dev_id}!"
        assert act.get("rbac_blocked") is True

    # 3. /api/device and /api/text_command with unknown role/speaker must be rejected (403) even for light_living
    for ep, payload in [
        ("/api/device", {"device_id": "light_living", "action": "on", "role": "UNKNOWN"}),
        ("/api/device", {"device_id": "light_living", "action": "on", "role": "stranger_voice"}),
        ("/api/device", {"device_id": "fan_bedroom", "action": "on", "user_id": "unrecognised_speaker"}),
        ("/api/text_command", {"text": "Bật đèn phòng khách", "role": "UNKNOWN"}),
        ("/api/text_command", {"text": "Bật quạt phòng ngủ", "role": "stranger"}),
    ]:
        resp = client.post(ep, json=payload)
        data = resp.json()
        assert resp.status_code == 403, f"{ep} allowed unknown role payload {payload}: {data}"
        assert data.get("ok") is False
        assert data.get("rbac_blocked") is True


# ============================================================================
# 4. CENTRAL CONFIG simulator/config/voice_auth.json
# ============================================================================


def test_central_voice_auth_config_exists_and_matches_spec() -> None:
    """simulator/config/voice_auth.json must exist and define owner_id, owner_email,
    role_map, threshold_mel (0.88), and threshold_deep (0.80)."""
    cfg_path = ROOT / "simulator" / "config" / "voice_auth.json"
    assert cfg_path.exists(), "Missing simulator/config/voice_auth.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    assert cfg.get("owner_id") == "tuan_anh"
    assert cfg.get("owner_email") == "nep94121@gmail.com"
    assert isinstance(cfg.get("role_map"), dict)
    assert cfg["role_map"].get("1") == "ADMIN"
    assert cfg["role_map"].get("2") == "MEMBER"
    assert cfg["role_map"].get("3") == "CHILD_GUEST"
    assert float(cfg.get("threshold_mel")) == pytest.approx(0.88)
    assert float(cfg.get("threshold_deep")) == pytest.approx(0.80)

    from simulator.voice_config import (
        OWNER_EMAIL,
        OWNER_ID,
        ROLE_MAP,
        THRESHOLD_DEEP,
        THRESHOLD_MEL,
    )

    assert OWNER_ID == cfg["owner_id"]
    assert OWNER_EMAIL == cfg["owner_email"]
    assert THRESHOLD_MEL == pytest.approx(0.88)
    assert THRESHOLD_DEEP == pytest.approx(0.80)
    assert ROLE_MAP[1] == "ADMIN"


# ============================================================================
# 5. VOICEPRINTS SERVER-SIDE ONLY & NO SAMPLE-NAME SHORTCUT
# ============================================================================


def _find_forbidden_biometric_keys(obj: Any, path: str = "$") -> list[str]:
    forbidden = {
        "voiceprint",
        "voiceprints",
        "embedding",
        "deep_embedding",
        "embedding_256d",
        "baseline_embedding",
        "baseline_deep_embedding",
        "baseline_embedding_256d",
        "formants_hz",
        "password_hash",
    }
    found: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            k_str = str(k)
            if k_str in forbidden:
                found.append(f"{path}.{k}")
            elif k_str in ("password_plain_hint", "password_hint") and v != "******":
                found.append(f"{path}.{k}")
            found.extend(_find_forbidden_biometric_keys(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            found.extend(_find_forbidden_biometric_keys(item, f"{path}[{idx}]"))
    return found


def test_no_api_response_contains_voiceprints_or_sample_name_shortcut(client: TestClient) -> None:
    """No API endpoint may expose voiceprint vectors/objects or password hashes,
    and no endpoint may authenticate by sample name or client-supplied voiceprint/level."""
    for get_ep in (
        "/api/server_logs_and_db",
        "/api/logs/dashboard",
        "/api/voice_auth/profiles",
        "/api/auth3/overview",
    ):
        resp = client.get(get_ep)
        assert resp.status_code == 200
        body = resp.json()
        leaks = _find_forbidden_biometric_keys(body)
        assert not leaks, f"Endpoint {get_ep} leaked forbidden biometric/credential keys: {leaks}"

    # SQL query endpoint must block access to accounts_3layer and user_sessions
    for forbidden_sql in (
        "SELECT * FROM accounts_3layer",
        "SELECT password_hash, voiceprint_json FROM accounts_3layer",
        "SELECT * FROM user_sessions",
    ):
        r_sql = client.post("/api/logs/sql_query", json={"sql": forbidden_sql})
        d_sql = r_sql.json()
        assert r_sql.status_code in (400, 403) or d_sql.get("ok") is False, (
            f"/api/logs/sql_query allowed sensitive table query: {forbidden_sql}"
        )

    # Sample-name shortcut and client-supplied voiceprint/tier/level must be rejected
    for sample_name in ("owner_voice_1", "user_voice_thanh_vien_a", "user_voice_khach_c"):
        r_vc = client.post(
            "/api/voice_command",
            json={
                "sample_id": sample_name,
                "profile_id": sample_name,
                "speaker_id": sample_name,
                "tier": 1,
                "level": 1,
                "role": "ADMIN",
                "voiceprint": {"enrolled": True, "f0_mean_hz": 126.0},
                "text": "Mở cửa chính",
                "audio_pcm_b64": "",
            },
        )
        assert r_vc.status_code in (400, 401, 403)
        assert r_vc.json().get("ok") is False

        r_l3 = client.post(
            "/api/auth3/layer3_voice",
            json={
                "sample_id": sample_name,
                "profile_id": sample_name,
                "tier": 1,
                "level": 1,
                "voiceprint": {"enrolled": True, "f0_mean_hz": 126.0},
                "spoken_command": "Mở cửa chính",
                "audio_pcm_b64": "",
            },
        )
        assert r_l3.json().get("ok") is False


# ============================================================================
# 6. GREP / SCAN TEST: ZERO REMOVED FALLBACK PASSWORD LITERALS IN APP SOURCE
# ============================================================================


def test_grep_scan_no_removed_fallback_password_literals_in_repo() -> None:
    """App source, frontend, docs, and data files must not contain any of the
    removed fallback password literals."""
    forbidden_literals = _decoded_removed_fallbacks()
    scan_roots = [
        ROOT / "simulator",
        ROOT / "api",
        ROOT / "mobile_app",
        ROOT / "android_app",
        ROOT / "docs",
    ]
    scan_exts = {".py", ".js", ".ts", ".tsx", ".kt", ".html", ".json", ".md"}
    skip_names = {"three.min.js", "wokwi-elements.bundle.js", "knowledge_embeddings_cache.json"}

    violations: list[str] = []
    for scan_root in scan_roots:
        if not scan_root.exists():
            continue
        for path in sorted(scan_root.rglob("*")):
            if not path.is_file() or path.suffix not in scan_exts:
                continue
            if path.name in skip_names or "__pycache__" in path.parts or "node_modules" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for idx, lit in enumerate(forbidden_literals):
                if lit in text:
                    rel = path.relative_to(ROOT).as_posix()
                    violations.append(f"{rel} (matched forbidden fallback pattern #{idx + 1})")

    assert not violations, f"Found removed fallback password literals in codebase: {violations}"
