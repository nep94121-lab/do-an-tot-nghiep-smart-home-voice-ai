import pathlib
import re
import json

files_to_check = [
    'simulator/static/index.html',
    'mobile_app/index.html',
    'simulator/static/auth.html',
    'simulator/static/js/auth.js',
    'simulator/static/js/app.js',
    'simulator/static/js/mobile_app.js',
    'simulator/static/js/logs.js',
    'simulator/api/routes_logs.py',
    'simulator/auth_3layer.py',
    'simulator/data/accounts_3layer.json',
    'simulator/auth/constants_and_crypto.py'
]

leaks = []
for f in files_to_check:
    path = pathlib.Path(f)
    if not path.exists():
        continue
    content = path.read_text(encoding='utf-8')
    # Check for prefilled password values in HTML
    if f.endswith('.html'):
        pw_values = re.findall(r'type=["\']password["\'][^>]*value=["\']([^"\']+)["\']', content, re.IGNORECASE)
        pw_values += re.findall(r'value=["\']([^"\']+)["\'][^>]*type=["\']password["\']', content, re.IGNORECASE)
        for val in pw_values:
            if val:
                leaks.append(f'{f}: password input has value="{val}"')
        if 'Mật khẩu mặc định: 123456' in content or 'mặc định: 123456' in content:
            leaks.append(f'{f}: contains default password hint in UI')
        if '(MK: 123456)' in content or 'GiaDinhMoi@2026' in content:
            leaks.append(f'{f}: contains sensitive seed password string')

    # Check for accounts_3layer.json passwords
    if f.endswith('accounts_3layer.json'):
        accs = json.loads(content)
        for a in accs:
            if 'password' in a and a.get('password'):
                leaks.append(f'{f}: plaintext password in account {a.get("email")}')
            if not a.get('password_hash'):
                leaks.append(f'{f}: missing password_hash in account {a.get("email")}')

print(f'LEAK_CHECK_TOTAL: {len(leaks)}')
for l in leaks:
    print(' - LEAK:', l)
