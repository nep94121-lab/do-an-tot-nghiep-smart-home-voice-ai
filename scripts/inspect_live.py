import urllib.request
import re

url = "https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/"
with urllib.request.urlopen(url) as r:
    html = r.read().decode("utf-8", errors="ignore")

print("nep94121 in root:", "nep94121" in html)
print("Mật khẩu mặc định in root:", "Mật khẩu mặc định" in html)
print("All inputs on root:")
for m in re.finditer(r'<input[^>]+>', html, re.I):
    print("  ", m.group(0))

app_url = "https://do-an-tot-nghiep-smart-home-voice-a.vercel.app/app"
with urllib.request.urlopen(app_url) as r:
    app_html = r.read().decode("utf-8", errors="ignore")

print("\nnep94121 in /app:", "nep94121" in app_html)
print("Mật khẩu mặc định in /app:", "Mật khẩu mặc định" in app_html)
print("All inputs on /app:")
for m in re.finditer(r'<input[^>]+>', app_html, re.I):
    print("  ", m.group(0))
