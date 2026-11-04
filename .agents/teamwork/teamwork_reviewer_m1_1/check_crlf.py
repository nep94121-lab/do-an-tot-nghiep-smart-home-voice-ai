import pathlib

files = [
    'simulator/static/index.html',
    'mobile_app/index.html',
    'simulator/static/auth.html',
    'simulator/static/js/auth.js',
    'simulator/static/js/app.js',
    'simulator/static/js/mobile_app.js',
    'simulator/auth/constants_and_crypto.py',
    'simulator/data/accounts_3layer.json',
    'simulator/auth_3layer.py',
    'simulator/api/routes_logs.py',
    'simulator/static/js/logs.js',
    'tests/test_p4_survey1_security_auth.py',
    'tests/test_p3_session_rbac_concurrency.py'
]

crlf_detected = []
for f in files:
    p = pathlib.Path(f)
    if not p.exists():
        crlf_detected.append(f'{f} NOT FOUND')
        continue
    data = p.read_bytes()
    if b'\r\n' in data:
        crlf_detected.append(f'{f} has CRLF')
    # Check UTF-8 decoding
    try:
        data.decode('utf-8')
    except Exception as e:
        crlf_detected.append(f'{f} invalid UTF-8: {e}')
    # Check BOM
    if data.startswith(b'\xef\xbb\xbf'):
        crlf_detected.append(f'{f} has UTF-8 BOM')

print(f'CRLF_CHECK_VIOLATIONS: {len(crlf_detected)}')
for v in crlf_detected:
    print(' - VIOLATION:', v)
