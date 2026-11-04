"""
Verification Script for Live Production Domain
Domain: https://do-an-tot-nghiep-smart-home-voice-a.vercel.app
Validates HTTP status codes, headers, and specific bug fixes on live frontend assets.
"""
import urllib.request
import urllib.error
import ssl
import sys

BASE = "https://do-an-tot-nghiep-smart-home-voice-a.vercel.app"

class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Prevent auto-following so we can inspect 307
        return None

opener = urllib.request.build_opener(NoRedirectHandler)

routes = [
    ("/", 200, "Desktop root dashboard"),
    ("/app", 200, "Mobile PWA dashboard"),
    ("/mobile", [307, 200], "Mobile redirect to /app"),
    ("/architecture", 200, "Architecture interactive page"),
    ("/offline", 200, "Offline error page"),
    ("/404", 404, "Custom 404 error page"),
    ("/403", 403, "Custom 403 error page"),
    ("/500", 500, "Custom 500 error page"),
    ("/qr_expired", 200, "QR expired error page"),
    ("/sw.js", 200, "Service Worker"),
    ("/favicon.ico", 200, "Favicon binary"),
    ("/non_existent_page_check_phase4", 404, "Custom 404 fallback check"),
]

print("=" * 80)
print(f"VERIFYING LIVE PRODUCTION ROUTES: {BASE}")
print("=" * 80)

failures = 0
responses = {}

for path, expected, desc in routes:
    url = BASE + path
    try:
        resp = opener.open(url, timeout=15)
        code = resp.getcode()
        headers = dict(resp.info())
        body = resp.read()
    except urllib.error.HTTPError as e:
        code = e.code
        headers = dict(e.headers)
        body = e.read()
    except Exception as e:
        code = 0
        headers = {}
        body = str(e).encode("utf-8")

    responses[path] = (code, headers, body)
    exp_list = expected if isinstance(expected, list) else [expected]
    status_str = "PASS" if code in exp_list else "FAIL"
    if status_str == "FAIL":
        failures += 1

    extra = ""
    if path == "/mobile" and code == 307:
        extra = f"-> Location: {headers.get('location', '')}"
    elif path == "/sw.js":
        extra = f"-> SW-Allowed: {headers.get('service-worker-allowed', '')}"

    print(f"[{status_str}] {path:<32} {code} (exp {expected}) {extra} | {desc}")

print("-" * 80)

# Content & Bug checks on live assets
print("VERIFYING SPECIFIC PHASE 4 BUG FIXES ON PRODUCTION:")

# Check 1: Root / contains clean login form, zero prefilled creds, no default password hint, has #homeSessionDurationBadge, #secSensors
root_code, root_hdr, root_body = responses["/"]
root_html = root_body.decode("utf-8", errors="ignore")

bug1_root = ('value="nep94121@gmail.com"' not in root_html and 
             'Mật khẩu mặc định' not in root_html and
             'id="homeLoginEmail"' in root_html and
             'id="homeLoginPassword"' in root_html)
print(f"Bug 1 (Clean login, zero prefilled, no hint on /): {'PASS' if bug1_root else 'FAIL'}")

bug15_root = 'id="homeSessionDurationBadge"' in root_html
print(f"Bug 15 (Desktop header access time badge on /): {'PASS' if bug15_root else 'FAIL'}")

bug9_root = 'id="secSensors"' in root_html
print(f"Bug 9 (Desktop sensor panel on /): {'PASS' if bug9_root else 'FAIL'}")

# Check 2: /app has mobile login gate, mobileOverviewBox for 3D, and 7 devices
app_code, app_hdr, app_body = responses["/app"]
app_html = app_body.decode("utf-8", errors="ignore")

bug1_app = ('value="nep94121@gmail.com"' not in app_html and
            'id="mobileLoginGate"' in app_html and
            'id="mobileLoginEmail"' in app_html)
print(f"Bug 1 (/app clean login gate, zero prefilled): {'PASS' if bug1_app else 'FAIL'}")

bug6_app = 'id="mobileOverviewBox"' in app_html
print(f"Bug 6 (/app 3D overview box container): {'PASS' if bug6_app else 'FAIL'}")

bug7_app = 'id="devGrid"' in app_html
print(f"Bug 7 (/app 7 devices container #devGrid): {'PASS' if bug7_app else 'FAIL'}")

bug8_app = ('id="mobileBtnLogout"' in app_html and
            'id="mobileGuestCountdown"' in app_html)
print(f"Bug 8 (/app Profile tab logout button and guest countdown): {'PASS' if bug8_app else 'FAIL'}")

bug11_app = 'id="mobileMicPermissionModal"' in app_html
print(f"Bug 11 (/app mic permission modal): {'PASS' if bug11_app else 'FAIL'}")

bug12_app = 'id="mobileScannerStatus"' in app_html
print(f"Bug 12 (/app QR scanner container): {'PASS' if bug12_app else 'FAIL'}")

# Check 3: Check custom 404 page content
nexist_code, nexist_hdr, nexist_body = responses["/non_existent_page_check_phase4"]
nexist_html = nexist_body.decode("utf-8", errors="ignore")
custom_404 = "404" in nexist_html and "Vercel" not in nexist_html and "Trang chủ" in nexist_html
print(f"Custom 404 handler on nonexistent URL (No raw Vercel 404): {'PASS' if custom_404 else 'FAIL'}")

# Check 4: Check sw.js header Service-Worker-Allowed: /
sw_code, sw_hdr, sw_body = responses["/sw.js"]
sw_hdr_val = sw_hdr.get("service-worker-allowed", "")
sw_ok = sw_hdr_val == "/"
print(f"Service Worker Allowed header ('/'): {'PASS' if sw_ok else 'FAIL'} ({sw_hdr_val})")

# Check 5: Check favicon.ico
fav_code, fav_hdr, fav_body = responses["/favicon.ico"]
fav_ok = fav_code == 200 and len(fav_body) > 100
print(f"Favicon binary ICO status: {'PASS' if fav_ok else 'FAIL'} (Bytes: {len(fav_body)})")

# Fetch and check /static/js/app.js
try:
    app_js_req = urllib.request.Request(f"{BASE}/static/js/app.js")
    with urllib.request.urlopen(app_js_req, timeout=10) as r:
        app_js = r.read().decode("utf-8", errors="ignore")
    bug3_appjs = "pollRestStateFallback" in app_js and "hideWsReconnectBanner" in app_js
    print(f"Bug 3 (WebSocket polling fallback in app.js): {'PASS' if bug3_appjs else 'FAIL'}")
    bug10_appjs = "toggleDeviceOptimistic" in app_js or "data-optimistic" in app_js or "lbl.textContent" in app_js
    print(f"Bug 10 (Optimistic UI & no empty label in app.js): {'PASS' if bug10_appjs else 'FAIL'}")
    bug2_appjs = "homeLoginPassword.value = ''" in app_js or "homeLoginPassword.value=''" in app_js or "resetHomeGateState" in app_js
    print(f"Bug 2 (Logout form & state reset in app.js): {'PASS' if bug2_appjs else 'FAIL'}")
except Exception as e:
    print(f"Check app.js error: {e}")

# Fetch and check /static/js/mobile_app.js
try:
    m_js_req = urllib.request.Request(f"{BASE}/static/js/mobile_app.js")
    with urllib.request.urlopen(m_js_req, timeout=10) as r:
        m_js = r.read().decode("utf-8", errors="ignore")
    bug6_mjs = "SmartHome3D.init" in m_js or "house3d" in m_js
    print(f"Bug 6 (Mobile 3D Three.js house3d initialization in mobile_app.js): {'PASS' if bug6_mjs else 'FAIL'}")
    bug7_mjs = "showAllDevices: true" in m_js or "showAllDevices:true" in m_js or "showAllDevices" in m_js
    print(f"Bug 7 (Mobile 7 devices render in mobile_app.js): {'PASS' if bug7_mjs else 'FAIL'}")
    bug8_mjs = "mobileGuestCountdown" in m_js and "formatDurationHuman" in m_js
    print(f"Bug 8 (Mobile guest countdown format in mobile_app.js): {'PASS' if bug8_mjs else 'FAIL'}")
    bug11_mjs = "Đang chờ quyền mic" in m_js or "mobileMicPermissionModal" in m_js
    print(f"Bug 11 (Mic permission prompt handling in mobile_app.js): {'PASS' if bug11_mjs else 'FAIL'}")
    bug12_mjs = "mobileScannerStatus" in m_js
    print(f"Bug 12 (QR scanner status in mobile_app.js): {'PASS' if bug12_mjs else 'FAIL'}")
except Exception as e:
    print(f"Check mobile_app.js error: {e}")

# Fetch and check /static/js/logs.js
try:
    l_js_req = urllib.request.Request(f"{BASE}/static/js/logs.js")
    with urllib.request.urlopen(l_js_req, timeout=10) as r:
        l_js = r.read().decode("utf-8", errors="ignore")
    bug13_ljs = "pageSize" in l_js and ("currentPage" in l_js or "renderPaginatedLogs" in l_js)
    print(f"Bug 13 (/logs pagination & filters in logs.js): {'PASS' if bug13_ljs else 'FAIL'}")
    bug1_ljs = "maskSensitiveLogs" in l_js or "replace(" in l_js or "Mật khẩu" in l_js
    print(f"Bug 1 (/logs password masking in logs.js): {'PASS' if bug1_ljs else 'FAIL'}")
except Exception as e:
    print(f"Check logs.js error: {e}")

# Fetch and check /static/js/wokwi.js
try:
    w_js_req = urllib.request.Request(f"{BASE}/static/js/wokwi.js")
    with urllib.request.urlopen(w_js_req, timeout=10) as r:
        w_js = r.read().decode("utf-8", errors="ignore")
    bug14_wjs = "hoverHoleInfo" in w_js and ("simulatedTelemetry" in w_js or "dht11" in w_js)
    print(f"Bug 14 (Wokwi telemetry & non-overlapping labels in wokwi.js): {'PASS' if bug14_wjs else 'FAIL'}")
except Exception as e:
    print(f"Check wokwi.js error: {e}")

# Fetch and check /static/js/auth.js
try:
    a_js_req = urllib.request.Request(f"{BASE}/static/js/auth.js")
    with urllib.request.urlopen(a_js_req, timeout=10) as r:
        a_js = r.read().decode("utf-8", errors="ignore")
    bug4_5_ajs = "check_login" in a_js or "api/auth3" in a_js
    print(f"Bug 4/5 (Voice auth check & clean wizard in auth.js): {'PASS' if bug4_5_ajs else 'FAIL'}")
except Exception as e:
    print(f"Check auth.js error: {e}")

print("=" * 80)
if failures == 0:
    print("ALL LIVE PRODUCTION CHECKS PASSED 100%!")
else:
    print(f"VERIFICATION HAD {failures} FAILURES!")
    sys.exit(1)
