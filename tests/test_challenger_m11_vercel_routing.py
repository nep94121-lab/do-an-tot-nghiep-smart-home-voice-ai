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

from simulator.server import app

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
    """Adversarial syntax & schema validation of vercel.json."""

    def test_json_load_and_version(self, vercel_config: dict[str, Any]):
        assert isinstance(vercel_config, dict), "vercel.json must be a JSON object"
        assert vercel_config.get("version") == 2, "vercel.json must specify version 2"
        assert "routes" in vercel_config, "vercel.json must contain 'routes' key"
        assert isinstance(vercel_config["routes"], list), "'routes' must be a list"
        assert len(vercel_config["routes"]) > 0, "'routes' list must not be empty"

    def test_all_route_regexes_compile(self, vercel_config: dict[str, Any]):
        """Every route pattern must be a valid, compilable regular expression."""
        for i, route in enumerate(vercel_config["routes"]):
            pattern = route.get("src")
            assert pattern is not None, f"Route #{i} is missing 'src'"
            try:
                re.compile(pattern)
            except re.error as err:
                pytest.fail(f"Route #{i} invalid regex '{pattern}': {err}")

    def test_destination_files_exist_on_disk(self, vercel_config: dict[str, Any]):
        """All static destination targets (without variables) must exist in repository."""
        for i, route in enumerate(vercel_config["routes"]):
            dest = route.get("dest")
            if dest and "$" not in dest:
                # Local path in repository
                clean_dest = dest.lstrip("/")
                target_file = ROOT / clean_dest
                assert target_file.exists(), f"Route #{i} destination '{clean_dest}' does not exist on disk"

    def test_catchall_is_strictly_last_route(self, vercel_config: dict[str, Any]):
        """The catch-all route must be the last element to prevent shadowing subsequent routes."""
        routes = vercel_config["routes"]
        last_route = routes[-1]
        assert last_route.get("src") == "^/(.*)$", "Last route must be catch-all '^/(.*)$'"
        assert last_route.get("status") == 404, "Catch-all route must return HTTP 404"
        assert last_route.get("dest") == "/simulator/static/404.html", (
            "Catch-all route must point to /simulator/static/404.html"
        )

        # Ensure no other catch-all exists earlier in the array
        for idx, route in enumerate(routes[:-1]):
            assert route.get("src") != "^/(.*)$", f"Premature catch-all detected at route index {idx}!"


# =============================================================================
# 2. ADVERSARIAL TRAILING SLASH & BOUNDARY STRESS TESTS
# =============================================================================
class TestTrailingSlashAndBoundarySoundness:
    """Stress-test trailing slashes and regex anchors (^, $)."""

    def test_mobile_exact_and_trailing_slash(self, vercel_config: dict[str, Any]):
        routes = vercel_config["routes"]

        # Exact '/mobile'
        match_clean = simulate_vercel_route(routes, "/mobile")
        assert match_clean is not None
        assert match_clean["status"] == 307
        assert match_clean["headers"] == {"Location": "/app"}

        # Trailing slash '/mobile/'
        match_slash = simulate_vercel_route(routes, "/mobile/")
        assert match_slash is not None
        assert match_slash["status"] == 307
        assert match_slash["headers"] == {"Location": "/app"}

    def test_architecture_exact_and_trailing_slash(self, vercel_config: dict[str, Any]):
        routes = vercel_config["routes"]

        # Exact '/architecture'
        match_clean = simulate_vercel_route(routes, "/architecture")
        assert match_clean is not None
        assert match_clean["dest"] == "/docs/kien_truc/smart-home-voice-ai.architecture.html"

        # Trailing slash '/architecture/'
        match_slash = simulate_vercel_route(routes, "/architecture/")
        assert match_slash is not None
        assert match_slash["dest"] == "/docs/kien_truc/smart-home-voice-ai.architecture.html"

    def test_adversarial_prefix_hijack_prevention(self, vercel_config: dict[str, Any]):
        """Ensure /mobile_extra or /architecture_hacked do NOT trigger redirect or architecture page."""
        routes = vercel_config["routes"]
        adversarial_paths = [
            "/mobile_extra",
            "/mobile/subpath",
            "/mobile.html",
            "/architecture_fake",
            "/architecture/nested/deep",
            "/architecture.php",
        ]
        for path in adversarial_paths:
            match = simulate_vercel_route(routes, path)
            assert match is not None
            # Must fall through to catch-all 404
            assert match["status"] == 404, f"Path '{path}' did not fall through to 404! Matched: {match}"
            assert match["dest"] == "/simulator/static/404.html"


# =============================================================================
# 3. ROUTE PRECEDENCE & CONFLICT ANALYSIS
# =============================================================================
class TestRoutePrecedenceAndConflictAvoidance:
    """Stress-test that catch-all does not conflict with /api/*, /static/*, or other routes."""

    def test_api_routes_precede_catchall(self, vercel_config: dict[str, Any]):
        routes = vercel_config["routes"]
        api_test_paths = [
            "/api/devices",
            "/api/devices/relay1",
            "/api/auth/login",
            "/api/qr/handshake",
            "/api/logs/all",
            "/api/v1/deep/nested/endpoint",
        ]
        for path in api_test_paths:
            match = simulate_vercel_route(routes, path)
            assert match is not None
            assert match["route_index"] == 0, f"Path '{path}' was not caught by route #0 (/api/(.*)$)"
            assert match["dest"] == "/api/index.py"
            assert match["status"] is None, "API route rewrite should not override status to 404"

    def test_static_routes_precede_catchall(self, vercel_config: dict[str, Any]):
        routes = vercel_config["routes"]
        static_test_paths = [
            "/static/app.js",
            "/static/css/style.css",
            "/static/assets/logo.png",
            "/static/models/house.glb",
        ]
        for path in static_test_paths:
            match = simulate_vercel_route(routes, path)
            assert match is not None
            # Route index for static is 8
            assert match["src"] == "^/static/(.*)$"
            assert match["dest"] == f"/simulator{path}"
            assert match["status"] is None

    def test_error_pages_preserve_correct_statuses(self, vercel_config: dict[str, Any]):
        routes = vercel_config["routes"]
        expected_statuses = {
            "/offline": 200,
            "/offline.html": 200,
            "/404": 404,
            "/404.html": 404,
            "/500": 500,
            "/500.html": 500,
            "/403": 403,
            "/403.html": 403,
            "/qr_expired": 200,
            "/qr-expired": 200,
            "/qr_expired.html": 200,
        }
        for path, expected_status in expected_statuses.items():
            match = simulate_vercel_route(routes, path)
            assert match is not None, f"Path '{path}' failed to match any route"
            assert match["status"] == expected_status, (
                f"Path '{path}' matched with status {match.get('status')}, expected {expected_status}"
            )


# =============================================================================
# 4. CATCH-ALL BEHAVIOR FOR ARBITRARY NON-EXISTENT PAGES
# =============================================================================
class TestCatchAllNonExistentPages:
    """Stress-test catch-all route for various arbitrary non-existent URLs."""

    def test_arbitrary_random_urls_hit_catchall_404(self, vercel_config: dict[str, Any]):
        routes = vercel_config["routes"]
        non_existent_paths = [
            "/non_existent_random_page_12345",
            "/wp-admin/login.php",
            "/.env",
            "/config.json",
            "/random/nested/deep/path/index.html",
            "/users/profile/edit",
            "/undefined",
            "/null",
            "/test_not_found_xyz",
        ]
        for path in non_existent_paths:
            match = simulate_vercel_route(routes, path)
            assert match is not None, f"No route matched for '{path}'"
            assert match["src"] == "^/(.*)$", f"Path '{path}' did not match catch-all rule"
            assert match["status"] == 404, f"Path '{path}' status was not 404"
            assert match["dest"] == "/simulator/static/404.html"


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
        assert data.get("detail") == "Not Found"
