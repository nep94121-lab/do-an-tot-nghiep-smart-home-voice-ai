"""Regression & integrity test suite for agyclean15_20261128.

Covers:
- S2: Docs integrity (active Markdown links, stale simulator/server.py removal,
      README completeness & Wi-Fi/USB link, docs/luu_tru/README.md, PROJECT.md removal,
      and zero hardcoded Wi-Fi passwords/API secrets in docs/ & README.md).
- S3: Graduation Report integrity (.docx, .pdf, build_graduation_report.py,
      LOGO_SOURCES.md, README.md; PyMuPDF validation: 70..90 pages, 0 broken cross-refs,
      all 6 chapter headings + TÀI LIỆU THAM KHẢO, >= 45 indexed figures & >= 15 indexed
      tables in front matter).
- S4: Android lightbuild.yaml minSdk=26 preservation & zero git-tracked .apk files.
- S4-L2: Backend RBAC regression for POST /api/device (routes_devices.py:365) ensuring
         the returned snapshot for a Tier-3 guest is strictly session-scoped
         (current_tier == 3, ONLY living_room_light & bedroom_light, zero leakage of
         main_door / alarm_siren / garden_pump / speaker_amp / current_tier == 1).
- Guest WAV preservation: all 30 WAV files under test_audio/ exist and are non-empty.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import wave
from urllib.parse import unquote

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
REPORT_DIR = DOCS_DIR / "bao_cao"
TEST_AUDIO_DIR = ROOT / "test_audio"

_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_FENCED_CODE_RE = re.compile(r"```.*?```", flags=re.DOTALL)


def _active_markdown_files() -> list[pathlib.Path]:
    files = [ROOT / "README.md"]
    for md in sorted(DOCS_DIR.rglob("*.md")):
        rel_parts = md.relative_to(DOCS_DIR).parts
        if "luu_tru" in rel_parts:
            continue
        if len(rel_parts) >= 2 and rel_parts[0] == "bao_cao" and rel_parts[1] == "assets":
            continue
        files.append(md)
    return files


# ==============================================================================
# S2: DOCS INTEGRITY
# ==============================================================================


class TestDocsIntegrityS2:
    def test_active_docs_zero_broken_relative_links(self) -> None:
        md_files = _active_markdown_files()
        assert len(md_files) >= 10, f"Expected >= 10 active markdown files, found {len(md_files)}"
        broken: list[tuple[str, str]] = []
        for md in md_files:
            text = md.read_text(encoding="utf-8", errors="replace")
            stripped = _FENCED_CODE_RE.sub("", text)
            for match in _LINK_RE.finditer(stripped):
                href = match.group(1).strip()
                if not href or href.startswith(("http://", "https://", "mailto:", "#", "tel:")):
                    continue
                href_path = href.split("#", 1)[0].split("?", 1)[0].strip()
                if not href_path:
                    continue
                target = (md.parent / unquote(href_path)).resolve()
                if not target.exists():
                    broken.append((md.relative_to(ROOT).as_posix(), href))
        assert broken == [], f"Broken relative Markdown links in active docs: {broken}"

    def test_active_docs_zero_stale_simulator_server_refs(self) -> None:
        hits: list[str] = []
        for md in _active_markdown_files():
            text = md.read_text(encoding="utf-8", errors="replace")
            if "simulator/server.py" in text:
                hits.append(md.relative_to(ROOT).as_posix())
        assert hits == [], f"Stale 'simulator/server.py' reference found in active docs: {hits}"

    def test_readme_prominently_links_wifi_usb_guide_and_ready_state(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        # Must prominently link the unified Wi-Fi + USB flash guide near the top
        top_section = "\n".join(readme.splitlines()[:25])
        assert "docs/huong_dan/CAI_DAT_WIFI_VA_NAP_USB.md" in top_section
        assert (ROOT / "docs" / "huong_dan" / "CAI_DAT_WIFI_VA_NAP_USB.md").is_file()
        # Must clearly state software/web/app are complete with only hardware flash remaining
        lower = readme.lower()
        assert "backend" in lower and "web" in lower and "android" in lower
        assert "hoàn thiện 100%" in lower or "hoàn thiện" in lower
        assert "chỉ còn duy nhất" in lower or "chỉ còn" in lower
        assert "nạp firmware" in lower or "usb" in lower

    def test_archive_readme_exists_and_project_md_removed(self) -> None:
        archive_readme = DOCS_DIR / "luu_tru" / "README.md"
        assert archive_readme.is_file() and archive_readme.stat().st_size > 100
        assert not (ROOT / "PROJECT.md").exists(), "Legacy PROJECT.md should be removed"

    def test_zero_hardcoded_wifi_passwords_or_secrets_in_docs(self) -> None:
        secret_patterns: list[tuple[str, re.Pattern[str]]] = [
            ("google_api_key", re.compile(r"AIza[0-9A-Za-z\-_]{35}")),
            ("openai_sk_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
            ("github_pat", re.compile(r"ghp_[A-Za-z0-9]{36}")),
            ("tailscale_authkey", re.compile(r"tskey-[A-Za-z0-9\-]{20,}")),
            (
                "hardcoded_wifi_password",
                re.compile(
                    r"""(?i)(?:wifi_pass(?:word)?|ssid_password)\s*[:=]\s*["'](?!<|\{|your|ten_|mat_|pass|nhap|example|changeme|placeholder|empty)[^\s"']{4,}["']"""
                ),
            ),
            (
                "private_key_block",
                re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
            ),
        ]
        all_md = [ROOT / "README.md"] + sorted(DOCS_DIR.rglob("*.md"))
        findings: list[tuple[str, str]] = []
        for md in all_md:
            text = md.read_text(encoding="utf-8", errors="replace")
            for pat_name, pat in secret_patterns:
                if pat.search(text):
                    findings.append((md.relative_to(ROOT).as_posix(), pat_name))
        assert findings == [], f"Potential hardcoded secret(s) detected in docs/README: {findings}"


# ==============================================================================
# S3: GRADUATION REPORT INTEGRITY
# ==============================================================================


class TestGraduationReportIntegrityS3:
    def test_required_report_files_exist(self) -> None:
        required = [
            REPORT_DIR / "Bao_Cao_DATN_Smart_Home_Voice_AI.docx",
            REPORT_DIR / "Bao_Cao_DATN_Smart_Home_Voice_AI.pdf",
            REPORT_DIR / "build_graduation_report.py",
            REPORT_DIR / "LOGO_SOURCES.md",
            REPORT_DIR / "README.md",
        ]
        for path in required:
            assert path.is_file(), f"Missing graduation report file: {path}"
            assert path.stat().st_size > 500, f"Unexpectedly small report file: {path}"

    def test_report_pdf_structure_chapters_and_front_matter_indices(self) -> None:
        pymupdf = pytest.importorskip("pymupdf")
        pdf_path = REPORT_DIR / "Bao_Cao_DATN_Smart_Home_Voice_AI.pdf"

        with pymupdf.open(str(pdf_path)) as doc:
            page_count = len(doc)
            assert 70 <= page_count <= 90, f"Expected 70 <= PDF pages <= 90, got {page_count}"

            page_texts = [page.get_text() for page in doc]
            full_text = "\n".join(page_texts)

            assert "Error! Reference source not found" not in full_text, (
                "Broken Word cross-reference detected in graduation report PDF"
            )

            for ch in range(1, 7):
                heading = f"CHƯƠNG {ch}."
                assert heading in full_text, f"Missing chapter heading {heading!r} in PDF"
            assert "TÀI LIỆU THAM KHẢO" in full_text, "Missing 'TÀI LIỆU THAM KHẢO' in PDF"

            # Locate start of main body (first page after TOC that begins with CHƯƠNG 1.)
            body_start_idx = None
            for idx, txt in enumerate(page_texts):
                lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
                if any(ln.startswith("CHƯƠNG 1.") and "...." not in ln for ln in lines[:4]):
                    body_start_idx = idx
                    break
            assert body_start_idx is not None and body_start_idx >= 10, (
                f"Could not locate body start of CHƯƠNG 1. (found idx={body_start_idx})"
            )

            front_matter_text = "\n".join(page_texts[:body_start_idx])
            assert "DANH MỤC HÌNH VẼ" in front_matter_text
            assert "DANH MỤC BẢNG BIỂU" in front_matter_text

            indexed_figures = re.findall(r"Hình\s+\d+\.\d+", front_matter_text)
            indexed_tables = re.findall(r"Bảng\s+\d+\.\d+", front_matter_text)
            assert len(indexed_figures) >= 45, (
                f"Expected >= 45 indexed figures in front matter, got {len(indexed_figures)}"
            )
            assert len(indexed_tables) >= 15, (
                f"Expected >= 15 indexed tables in front matter, got {len(indexed_tables)}"
            )


# ==============================================================================
# S4: ANDROID CONFIG & APK POLICY
# ==============================================================================


class TestAndroidConfigAndApkPolicyS4:
    @pytest.mark.parametrize(
        "rel_path",
        [
            "app/app/lightbuild.yaml",
            "app/app-core/lightbuild.yaml",
        ],
    )
    def test_android_lightbuild_preserves_minsdk_26(self, rel_path: str) -> None:
        cfg_path = ROOT / rel_path
        assert cfg_path.is_file(), f"Missing {rel_path}"
        text = cfg_path.read_text(encoding="utf-8")
        # Verify minSdk block contains apiLevel: 26
        m = re.search(r"minSdk:\s*\n(?:\s+\w+:\s*\n)*\s+apiLevel:\s*(\d+)", text)
        assert m is not None, f"Could not find minSdk -> apiLevel in {rel_path}"
        assert int(m.group(1)) == 26, f"Expected minSdk apiLevel 26 in {rel_path}, got {m.group(1)}"

    def test_no_apk_tracked_in_git(self) -> None:
        proc = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "*.apk"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
            timeout=15,
        )
        tracked_apks = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
        assert tracked_apks == [], f"APK files must NOT be tracked in git: {tracked_apks}"


# ==============================================================================
# S4-L2: BACKEND RBAC SNAPSHOT ISOLATION REGRESSION (routes_devices.py:365)
# ==============================================================================


class TestBackendRbacDeviceSnapshotIsolation:
    def test_tier3_post_api_device_snapshot_strictly_scoped(self) -> None:
        """Tier-3 guest toggling living_room_light via POST /api/device must receive
        a strictly Tier-3 scoped snapshot (only living_room_light & bedroom_light;
        never leaking main_door, alarm_siren, garden_pump, speaker_amp, users, or tier 1).
        """
        created_tmp: str | None = None
        if not os.environ.get("SMARTHOME_DATA_DIR"):
            created_tmp = tempfile.mkdtemp(prefix="clean15_rbac_test_")
            data_dir = pathlib.Path(created_tmp) / "data"
            log_dir = pathlib.Path(created_tmp) / "logs"
            data_dir.mkdir(parents=True, exist_ok=True)
            log_dir.mkdir(parents=True, exist_ok=True)
            os.environ["SMARTHOME_DATA_DIR"] = str(data_dir)
            os.environ["SMARTHOME_LOG_DIR"] = str(log_dir)
            os.environ["SMARTHOME_SQLITE_PATH"] = str(data_dir / "smarthome.db")

        try:
            from fastapi.testclient import TestClient

            from backend.auth.session_store import get_session_store
            from backend.server import app

            store = get_session_store()
            guest_sess = store.create_session(
                user_id="khach_c",
                tier=3,
                role="CHILD_GUEST",
                display_name="Khách C (Kiểm thử RBAC)",
                email="khach.c@gmail.com",
                source="test_clean15_rbac",
            )
            headers = {"X-Session-Token": guest_sess.session_id}

            forbidden_device_ids = {"main_door", "alarm_siren", "garden_pump", "speaker_amp"}
            expected_allowed_ids = {"living_room_light", "bedroom_light"}

            with TestClient(app) as client:
                # 1. Allowed light toggle -> 200 OK with strictly Tier-3 scoped snapshot
                resp = client.post(
                    "/api/device",
                    headers=headers,
                    json={"device_id": "living_room_light", "action": "on", "source": "mobile_app"},
                )
                assert resp.status_code == 200, f"Unexpected status {resp.status_code}: {resp.text}"
                body = resp.json()
                assert body.get("ok") is True
                assert body.get("tier") == 3
                assert body.get("rbac_blocked") is False

                snap = body.get("snapshot")
                assert isinstance(snap, dict), "Missing snapshot in POST /api/device response"
                assert snap.get("current_tier") == 3, (
                    f"RBAC snapshot leak: expected current_tier=3, got {snap.get('current_tier')}"
                )
                assert snap.get("current_tier") != 1
                assert "users" not in snap, "Tier-3 snapshot must not leak users list"

                devices = snap.get("devices") or []
                returned_ids = {d["id"] for d in devices if isinstance(d, dict) and d.get("id")}
                assert returned_ids == expected_allowed_ids, (
                    f"Tier-3 snapshot devices mismatch: expected {expected_allowed_ids}, got {returned_ids}"
                )
                assert returned_ids.isdisjoint(forbidden_device_ids), (
                    f"Tier-3 snapshot leaked privileged devices: {returned_ids & forbidden_device_ids}"
                )

                allowed_ids = set(snap.get("allowed_device_ids") or [])
                assert allowed_ids == expected_allowed_ids

                # 2. Forbidden Tier-1 device -> 403 RBAC blocked, snapshot STILL Tier-3 scoped
                resp_forb = client.post(
                    "/api/device",
                    headers=headers,
                    json={"device_id": "main_door", "action": "open", "source": "mobile_app"},
                )
                assert resp_forb.status_code == 403, f"Expected 403 for Tier-3 main_door, got {resp_forb.status_code}"
                body_forb = resp_forb.json()
                assert body_forb.get("ok") is False
                assert body_forb.get("rbac_blocked") is True
                snap_forb = body_forb.get("snapshot")
                assert isinstance(snap_forb, dict)
                assert snap_forb.get("current_tier") == 3
                forb_returned_ids = {
                    d["id"] for d in (snap_forb.get("devices") or []) if isinstance(d, dict) and d.get("id")
                }
                assert forb_returned_ids == expected_allowed_ids
                assert forb_returned_ids.isdisjoint(forbidden_device_ids)
        finally:
            if created_tmp:
                shutil.rmtree(created_tmp, ignore_errors=True)


# ==============================================================================
# GUEST WAV PRESERVATION
# ==============================================================================


class TestGuestWavPreservation:
    def test_all_30_wav_files_exist_and_non_empty(self) -> None:
        assert TEST_AUDIO_DIR.is_dir(), f"Missing test_audio directory: {TEST_AUDIO_DIR}"
        wav_files = sorted(TEST_AUDIO_DIR.rglob("*.wav"))
        assert len(wav_files) == 30, f"Expected exactly 30 WAV files under test_audio/, found {len(wav_files)}"
        empty_or_invalid: list[str] = []
        for wf_path in wav_files:
            if not wf_path.is_file() or wf_path.stat().st_size <= 44:
                empty_or_invalid.append(wf_path.relative_to(ROOT).as_posix())
                continue
            try:
                with wave.open(str(wf_path), "rb") as wf:
                    if wf.getnframes() <= 0:
                        empty_or_invalid.append(wf_path.relative_to(ROOT).as_posix())
            except wave.Error:
                empty_or_invalid.append(wf_path.relative_to(ROOT).as_posix())
        assert empty_or_invalid == [], f"Empty or unreadable WAV file(s): {empty_or_invalid}"
