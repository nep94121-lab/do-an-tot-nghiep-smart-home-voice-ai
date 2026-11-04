import subprocess

base = "https://do-an-tot-nghiep-smart-home-voice-a.vercel.app"
routes = [
    ("/", 200, "Trang chủ Dashboard máy tính"),
    ("/app", 200, "Ứng dụng di động PWA (5 màn hình M1-M5)"),
    ("/mobile", 307, "Chuyển hướng chuẩn về /app"),
    ("/architecture", 200, "Trang kiến trúc tương tác Archify v3.2.0"),
    ("/offline", 200, "Trang thông báo mất kết nối ngoại tuyến"),
    ("/404", 404, "Trang lỗi 404 tùy biến"),
    ("/403", 403, "Trang từ chối truy cập 403 Forbidden"),
    ("/500", 500, "Trang lỗi máy chủ 500 Server Error"),
    ("/qr_expired", 200, "Trang mã QR hết hạn"),
    ("/sw.js", 200, "Service Worker (Service-Worker-Allowed: /)"),
    ("/favicon.ico", 200, "Favicon binary ICO chuẩn"),
    ("/duong-dan-khong-ton-tai-404-check", 404, "Render trang 404.html tùy biến (Không lỗi thô Vercel)"),
]

print("=" * 85)
print(f"{'STT':<4} | {'Tuyến đường (Route)':<36} | {'Mã HTTP':<8} | {'Kỳ vọng':<8} | {'Kết quả'}")
print("=" * 85)

for idx, (path, exp, desc) in enumerate(routes, 1):
    url = base + path
    cmd = ["curl.exe", "-s", "-o", "NUL", "-w", "%{http_code}", url]
    out = subprocess.check_output(cmd, text=True).strip()
    status = "ĐẠT 100%" if out == str(exp) else f"FAIL ({out})"
    print(f"{idx:<4} | {path:<36} | {out:<8} | {exp:<8} | {status} ({desc})")

print("=" * 85)
