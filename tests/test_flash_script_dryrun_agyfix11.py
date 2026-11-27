"""Automated tests for agyfix11 R7: hardware/flash_and_setup.ps1 encoding, syntax,
zero hardcoded secrets, -DryRun compile & COM audit, and git-ignore of hardware/wifi_local.json.
"""
from __future__ import annotations

import pathlib
import re
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
FLASH_SCRIPT = REPO_ROOT / "hardware" / "flash_and_setup.ps1"
GITIGNORE_PATH = REPO_ROOT / ".gitignore"

SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z\-_]{20,}"),
    re.compile(r"ghp_[0-9A-Za-z]{20,}"),
    re.compile(r"sk-[0-9A-Za-z]{20,}"),
    re.compile(r"BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY"),
    re.compile(r"nep94121@gmail\.com", re.IGNORECASE),
    re.compile(r"smtp_password\s*=\s*['\"][^'\"]+['\"]", re.IGNORECASE),
    re.compile(r"hardware_api_key\s*=\s*['\"][A-Za-z0-9_\-]{12,}['\"]", re.IGNORECASE),
)


class TestFlashScriptDryRun:
    def test_flash_script_has_utf8_bom_and_is_pure_ascii(self) -> None:
        assert FLASH_SCRIPT.exists(), f"Missing {FLASH_SCRIPT}"
        raw = FLASH_SCRIPT.read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf"), "flash_and_setup.ps1 must start with UTF-8 BOM (EF BB BF)"
        body = raw[3:]
        non_ascii = [(idx, b) for idx, b in enumerate(body) if b > 0x7F]
        assert non_ascii == [], f"flash_and_setup.ps1 contains non-ASCII bytes: {non_ascii[:10]}"

    def test_flash_script_parses_with_zero_powershell_syntax_errors(self) -> None:
        ps_check = (
            "$tokens = $null; $errors = $null; "
            f"[System.Management.Automation.Language.Parser]::ParseFile('{FLASH_SCRIPT}', [ref]$tokens, [ref]$errors) | Out-Null; "
            "if ($errors.Count -gt 0) { "
            "  $errors | ForEach-Object { Write-Error $_.ToString() }; exit 1 "
            "} "
            "Write-Output 'PARSE_OK'"
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_check],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert proc.returncode == 0, f"PowerShell syntax errors:\n{proc.stderr}\n{proc.stdout}"
        assert "PARSE_OK" in proc.stdout

    def test_flash_script_contains_zero_hardcoded_secrets(self) -> None:
        text = FLASH_SCRIPT.read_text(encoding="utf-8-sig")
        for pat in SECRET_PATTERNS:
            assert pat.search(text) is None, f"Potential hardcoded secret matched {pat.pattern!r}"
        # Ensure interactive prompts mask passwords/keys
        assert "-AsSecureString" in text
        # Ensure WIFI_CONFIG payload variable is cleared and secrets are never printed
        assert "secrets masked" in text.lower() or "secrets hidden" in text.lower()

    def test_wifi_local_json_is_gitignored(self) -> None:
        assert GITIGNORE_PATH.exists()
        gi_text = GITIGNORE_PATH.read_text(encoding="utf-8")
        assert "hardware/wifi_local.json" in gi_text

        proc = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "check-ignore", "-v", "hardware/wifi_local.json"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert proc.returncode == 0, f"hardware/wifi_local.json is NOT git-ignored: {proc.stdout} {proc.stderr}"

    def test_flash_script_dryrun_compiles_nodemcuv2_and_passes_without_flashing(self) -> None:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(FLASH_SCRIPT),
                "-DryRun",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        combined = f"{proc.stdout}\n{proc.stderr}"
        assert proc.returncode == 0, f"flash_and_setup.ps1 -DryRun failed (rc={proc.returncode}):\n{combined}"
        assert "RESULT: PASS" in proc.stdout
        assert "DRY-RUN" in combined.upper()
        assert "nodemcuv2" in combined.lower()
        assert "Detected COM ports" in proc.stdout
        assert "skipping USB upload" in combined
        assert "Uploading firmware" not in combined
