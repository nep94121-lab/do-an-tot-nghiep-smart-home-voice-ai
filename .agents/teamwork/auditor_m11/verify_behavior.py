import re
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from starlette.testclient import TestClient
from simulator.server import app

def main():
    client = TestClient(app)

    # 1. /mobile
    r = client.get('/mobile', follow_redirects=False)
    assert r.status_code == 307, f"Expected 307, got {r.status_code}"
    loc = r.headers.get('location')
    assert loc == '/app', f"Expected /app, got {loc}"
    print("PASS: /mobile -> 307 to /app")

    r_follow = client.get('/mobile', follow_redirects=True)
    assert r_follow.status_code == 200, f"Expected 200, got {r_follow.status_code}"
    assert "<!DOCTYPE html>" in r_follow.text
    print("PASS: /mobile followed -> 200 OK HTML")

    # 2. /architecture
    r_arch = client.get('/architecture')
    assert r_arch.status_code == 200, f"Expected 200, got {r_arch.status_code}"
    assert "architecture" in r_arch.text.lower() or "archify" in r_arch.text.lower()
    print("PASS: /architecture -> 200 OK Architecture HTML")

    # 3. Error routes
    routes_expected = [
        ('/offline', 200),
        ('/404', 404),
        ('/500', 500),
        ('/403', 403),
        ('/qr_expired', 200),
        ('/sw.js', 200),
        ('/archify', 200),
        ('/archify/devops', 200),
        ('/archify/erd', 200),
    ]
    for path, code in routes_expected:
        res = client.get(path)
        assert res.status_code == code, f"Expected {code} for {path}, got {res.status_code}"
        print(f"PASS: {path} -> {code}")

    # 4. Content negotiation for unknown path
    r_unknown_html = client.get('/random_not_found_test_page', headers={'Accept': 'text/html'})
    assert r_unknown_html.status_code == 404
    assert 'Không tìm thấy trang' in r_unknown_html.text
    print("PASS: unknown path with text/html -> 404 HTML")

    r_unknown_json = client.get('/random_not_found_test_page', headers={'Accept': 'application/json'})
    assert r_unknown_json.status_code == 404
    assert r_unknown_json.json().get('detail') == 'Not Found'
    print("PASS: unknown path with application/json -> 404 JSON")

    # 5. Vercel route simulation
    with open('vercel.json', 'r', encoding='utf-8') as f:
        conf = json.load(f)

    test_urls = [
        ('/mobile', 307, '/app'),
        ('/mobile/', 307, '/app'),
        ('/architecture', 200, '/docs/kien_truc/smart-home-voice-ai.architecture.html'),
        ('/offline', 200, '/simulator/static/offline.html'),
        ('/404', 404, '/simulator/static/404.html'),
        ('/500', 500, '/simulator/static/500.html'),
        ('/403', 403, '/simulator/static/403.html'),
        ('/qr_expired', 200, '/simulator/static/qr_expired.html'),
        ('/sw.js', 200, '/simulator/static/sw.js'),
        ('/nonexistent/page', 404, '/simulator/static/404.html')
    ]

    for url, exp_status, exp_dest in test_urls:
        matched = None
        for r in conf['routes']:
            pattern = r['src']
            if re.search(pattern, url):
                matched = r
                break
        assert matched is not None, f"No route matched in vercel.json for {url}"
        if exp_status == 307:
            assert matched.get('status') == 307
            assert matched.get('headers', {}).get('Location') == exp_dest
        else:
            if 'status' in matched:
                assert matched['status'] == exp_status, f"{url} status {matched.get('status')} != {exp_status}"
            if exp_dest:
                assert matched.get('dest') == exp_dest, f"{url} dest {matched.get('dest')} != {exp_dest}"
        print(f"PASS Vercel route: {url} -> matched {matched['src']}")

    print("\n>>> ALL INDEPENDENT BEHAVIORAL VERIFICATIONS PASSED <<<")

if __name__ == '__main__':
    main()
