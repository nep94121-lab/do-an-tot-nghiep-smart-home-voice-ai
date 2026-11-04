import urllib.request
import re

app_url = "https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/app"
with urllib.request.urlopen(app_url) as r:
    app_html = r.read().decode("utf-8", errors="ignore")

print("Checking Profile Tab in /app:")
for m in re.finditer(r'Đăng xuất', app_html):
    start = max(0, m.start() - 150)
    end = min(len(app_html), m.end() + 150)
    print("--- Context around Đăng xuất: ---")
    print(app_html[start:end])

print("\nChecking guest countdown in /app:")
for m in re.finditer(r'countdown|guest|mời khách|Còn', app_html, re.I):
    start = max(0, m.start() - 80)
    end = min(len(app_html), m.end() + 80)
    print("--- Match:", app_html[start:end])
