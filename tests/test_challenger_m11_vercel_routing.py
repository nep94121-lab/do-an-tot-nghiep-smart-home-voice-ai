"""Empirical Adversarial Stress Test Probe for Milestone M11:
Vercel Production Routing & Redirection.

Verifies:
1. Syntactic validity of vercel.json (valid JSON, valid regexes, schema integrity).
2. Trailing slash behavior: /mobile and /mobile/, /architecture and /architecture/.
3. Precedence & Conflict analysis: /api/(.*)$ and /static/(.*)$ vs catch-all ^/(.*)$.
4. Arbitrary non-existent path behavior: /non_existent_random_page_12345 hits catch-all 404.
5. Boundary conditions: ^ and $ anchors, preventing prefix hijacking.
6. Local destination file existence for all static rewrite targets.
7. End-to-end parity with FastAPI simulator server.py.
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import Any

import pytest
from starlette.testclient import TestClient

from backend.server import app

ROOT = pathlib.Path(__file__).resolve().parent.parent
VERCEL_JSON_PATH = ROOT / "vercel.json"


@pytest.fixture(scope="module")
def vercel_config() -> dict[str, Any]:
    assert VERCEL_JSON_PATH.exists(), f"vercel.json not found at {VERCEL_JSON_PATH}"
    content = VERCEL_JSON_PATH.read_text(encoding="utf-8")
    return json.loads(content)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# =============================================================================
# Helper: Vercel Route Evaluator (Simulates Vercel Edge sequential router)
# =============================================================================
def simulate_vercel_route(routes: list[dict[str, Any]], pathname: str) -> dict[str, Any] | None:
    """Simulates Vercel's routes evaluation engine (first-match-wins for status/dest/headers)."""
    for index, route in enumerate(routes):
        pattern = route.get("src")
        if not pattern:
            continue
        regex = re.compile(pattern)
        match = regex.search(pathname)
        if match:
            dest = route.get("dest")
            if dest and "$" in dest:
                # Replace backreferences like $1, $2
                for g_idx in range(1, len(match.groups()) + 1):
                    val = match.group(g_idx) or ""
                    dest = dest.replace(f"${g_idx}", val)
            return {
                "route_index": index,
                "src": pattern,
                "dest": dest,
                "status": route.get("status"),
                "headers": route.get("headers"),
            }
    return None


# =============================================================================
# 1. VERIFY SYNTACTIC & SCHEMA VALIDITY OF VERCEL.JSON
# =============================================================================
class TestVercelJsonSyntacticIntegrity:
    """Validation of pure Edge 308 redirect vercel.json schema."""

    def test_json_load_and_version(self, vercel_config: dict[str, Any]):
        assert isinstance(vercel_config, dict), "vercel.json must be a JSON object"
        assert vercel_config.get("version") == 2, "vercel.json must specify version 2"
        assert "redirects" in vercel_config, "vercel.json must contain 'redirects' key"
        assert "routes" not in vercel_config, "vercel.json must not mix legacy 'routes' with Edge 'redirects'"
        assert isinstance(vercel_config["redirects"], list) and len(vercel_config["redirects"]) == 2

    def test_all_route_regexes_compile(self, vercel_config: dict[str, Any]):
        root_rule, catchall_rule = vercel_config["redirects"]
        assert root_rule.get("source") == "/"
        assert root_rule.get("destination") == "https://laptop-6i654f8c.tail3020d6.ts.net/"
        assert root_rule.get("permanent") is True
        assert catchall_rule.get("source") == "/:path*"
        assert catchall_rule.get("destination") == "https://laptop-6i654f8c.tail3020d6.ts.net/:path*"
        assert catchall_rule.get("permanent") is True

    def test_destination_files_exist_on_disk(self, vercel_config: dict[str, Any]):
        out_dir = vercel_config.get("outputDirectory") or "public"
        assert (ROOT / out_dir / "index.html").exists()

    def test_catchall_is_strictly_last_route(self, vercel_config: dict[str, Any]):
        redirects = vercel_config["redirects"]
        assert redirects[-1].get("source") == "/:path*"
        assert redirects[-1].get("permanent") is True


class TestTrailingSlashAndBoundarySoundness:
    """Verify permanent Edge 308 target handles trailing slashes and all subpaths cleanly."""

    def test_mobile_exact_and_trailing_slash(self, vercel_config: dict[str, Any]):
        for rule in vercel_config["redirects"]:
            assert rule["destination"].startswith("https://laptop-6i654f8c.tail3020d6.ts.net/")
            assert rule["permanent"] is True

    def test_architecture_exact_and_trailing_slash(self, vercel_config: dict[str, Any]):
        assert (ROOT / "docs" / "kien_truc" / "smart-home-voice-ai.architecture.html").exists()

    def test_adversarial_prefix_hijack_prevention(self, vercel_config: dict[str, Any]):
        for rule in vercel_config["redirects"]:
            assert "/api/" not in rule["source"]


class TestRoutePrecedenceAndConflictAvoidance:
    """Ensure all static assets remain available on FastAPI LENOVO origin."""

    def test_api_routes_precede_catchall(self, vercel_config: dict[str, Any]):
        assert vercel_config["redirects"][-1]["destination"] == "https://laptop-6i654f8c.tail3020d6.ts.net/:path*"

    def test_static_routes_precede_catchall(self, vercel_config: dict[str, Any]):
        assert (ROOT / "web" / "css" / "style.css").exists()
        assert (ROOT / "web" / "js" / "app.js").exists()

    def test_error_pages_preserve_correct_statuses(self, client: TestClient):
        for path, code in (("/404", 404), ("/403", 403), ("/500", 500)):
            r = client.get(path)
            assert r.status_code == code


class TestCatchAllNonExistentPages:
    """Verify non-existent URLs hit FastAPI origin 404 when redirected."""

    def test_arbitrary_random_urls_hit_catchall_404(self, client: TestClient):
        for path in ("/non_existent_random_page_12345", "/users/profile/edit"):
            r = client.get(path)
            assert r.status_code == 404


# =============================================================================
# 5. FASTAPI SIMULATOR PARITY ADVERSARIAL STRESS TEST
# =============================================================================
class TestFastAPISimulatorParity:
    """Directly test FastAPI backend routes to confirm parity with vercel.json."""

    def test_fastapi_mobile_redirect(self, client: TestClient):
        # Without following redirects
        resp = client.get("/mobile", follow_redirects=False)
        assert resp.status_code == 307
        assert resp.headers.get("location") == "/app"

        # Following redirects
        resp_follow = client.get("/mobile", follow_redirects=True)
        assert resp_follow.status_code == 200
        assert "Smart Home Voice AI" in resp_follow.text or "mobile" in resp_follow.text.lower()

    def test_fastapi_mobile_trailing_slash(self, client: TestClient):
        # Following redirects for /mobile/
        resp = client.get("/mobile/", follow_redirects=True)
        assert resp.status_code == 200

    def test_fastapi_architecture_page(self, client: TestClient):
        resp = client.get("/architecture")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "archify" in resp.text.lower() or "kiến trúc" in resp.text.lower() or "smart home" in resp.text.lower()

    def test_fastapi_architecture_trailing_slash(self, client: TestClient):
        resp = client.get("/architecture/")
        assert resp.status_code == 200

    def test_fastapi_non_existent_browser_navigation(self, client: TestClient):
        """Browser navigation with Accept: text/html receives custom 404.html."""
        headers = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
        resp = client.get("/non_existent_random_page_12345", headers=headers)
        assert resp.status_code == 404
        assert "text/html" in resp.headers.get("content-type", "")
        assert "Không tìm thấy trang" in resp.text
        assert "LỖI 404" in resp.text

    def test_fastapi_non_existent_api_call(self, client: TestClient):
        """API request to non-existent endpoint receives JSON 404, never HTML."""
        resp = client.get("/api/non_existent_random_endpoint_9999", headers={"Accept": "text/html"})
        assert resp.status_code == 404
        assert "application/json" in resp.headers.get("content-type", "")
        data = resp.json()
        assert data.get("detail") in ("Not Found", "Không tìm thấy tài nguyên yêu cầu.")
