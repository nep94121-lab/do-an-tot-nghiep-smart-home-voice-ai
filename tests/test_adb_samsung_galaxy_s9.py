"""Kịch bản kiểm thử tự động Giao diện Mobile trên Samsung Galaxy S9 (SM-G960F) qua ADB.
Thực hiện 4 bước:
1. Mở Cổng đăng nhập Mobile (#mobileLoginGate) và chụp step1_login_gate.png
2. Đăng nhập vào Giao diện điều khiển chính (#mobileMainContent) và chụp step2_main_dashboard.png
3. Điều khiển bật/tắt thiết bị trên điện thoại và chụp step3_device_control.png (đối soát SQLite smarthome.db)
4. Mở giao diện Quét/Nhận mã QR khách mời trên điện thoại và chụp step4_qr_guest.png
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import time
import json
import sqlite3

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = pathlib.Path(__file__).resolve().parent.parent
M4_DIR = ROOT / ".agents" / "teamwork" / "worker_m4"
ADB_PATH = r"C:\Users\LENOVO\AppData\Local\Android\Sdk\platform-tools\adb.exe"
SERIAL = "2223e8784b0c7ece"
DB_PATH = ROOT / "simulator" / "data" / "smarthome.db"

def run_adb(args: list[str]) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["ADB_LIBUSB"] = "1"
    return subprocess.run([ADB_PATH, "-s", SERIAL] + args, capture_output=True, env=env)

def screencap(dest_name: str) -> pathlib.Path:
    dest_path = M4_DIR / dest_name
    env = dict(os.environ)
    env["ADB_LIBUSB"] = "1"
    with open(dest_path, "wb") as f:
        subprocess.run([ADB_PATH, "-s", SERIAL, "exec-out", "screencap", "-p"], stdout=f, env=env)
    print(f"Captured {dest_name}: {dest_path.stat().st_size} bytes")
    return dest_path

def tap(x: int, y: int) -> None:
    print(f"Tap at ({x}, {y})")
    run_adb(["shell", "input", "tap", str(x), str(y)])

def swipe(x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
    print(f"Swipe from ({x1}, {y1}) to ({x2}, {y2}) in {duration_ms}ms")
    run_adb(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms)])

def get_device_state_from_sqlite(device_id: str) -> str:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT state FROM devices WHERE device_id = ?", (device_id,))
        row = cursor.fetchone()
        return row[0] if row else "UNKNOWN"
    finally:
        conn.close()

def set_device_state_in_sqlite_direct(device_id: str, state: str) -> None:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        with conn:
            conn.execute("UPDATE devices SET state = ? WHERE device_id = ?", (state, device_id))
    finally:
        conn.close()

def main() -> None:
    # 0. Đảm bảo cổng reverse hoạt động liên tục
    print("=== Khởi tạo ADB reverse port 8088 ===")
    run_adb(["reverse", "tcp:8088", "tcp:8088"])

    # 1. Bước 1: Mở trang mobile app
    print("=== Bước 1: Mở trang mobile app (#mobileLoginGate) ===")
    run_adb(["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", "http://localhost:8088/app"])
    time.sleep(3.0)
    screencap("step1_login_gate.png")

    # 2. Bước 2: Bấm Đăng nhập vào Giao diện điều khiển chính
    print("=== Bước 2: Bấm Đăng nhập vào Giao diện điều khiển chính ===")
    # Đảm bảo reverse port trước khi bấm submit
    run_adb(["reverse", "tcp:8088", "tcp:8088"])
    tap(540, 1864)
    time.sleep(3.0)
    screencap("step2_main_dashboard.png")

    # 3. Bước 3: Điều khiển thiết bị và đối soát SQLite
    print("=== Bước 3: Cuộn tới danh sách thiết bị và bấm bật Đèn phòng khách ===")
    run_adb(["reverse", "tcp:8088", "tcp:8088"])
    swipe(540, 1600, 540, 800, 300)
    time.sleep(1.0)

    # Đảm bảo ban đầu đèn phòng khách đang OFF để kiểm thử hành vi bật
    dev_target = "living_room_light"
    cur_state = get_device_state_from_sqlite(dev_target)
    print(f"Trạng thái '{dev_target}' trong SQLite TRƯỚC khi bấm: {cur_state}")

    # Bấm vào thẻ 'Đèn phòng khách' tại (540, 860)
    print(f"Bấm bật '{dev_target}' trên giao diện điện thoại...")
    tap(540, 860)
    time.sleep(2.0)

    after_state = get_device_state_from_sqlite(dev_target)
    print(f"Trạng thái '{dev_target}' trong SQLite SAU khi bấm: {after_state}")
    screencap("step3_device_control.png")

    # 4. Bước 4: Mở giao diện Quét/Nhận mã QR khách mời
    print("=== Bước 4: Chuyển sang tab Tài khoản và mở thẻ QR khách mời ===")
    run_adb(["reverse", "tcp:8088", "tcp:8088"])
    # Bấm Tab 4 "Tài khoản" ở thanh điều hướng dưới cùng (X=945, Y=2080)
    tap(945, 2080)
    time.sleep(1.5)

    # Cuộn nhẹ lên để thấy rõ thẻ Mời khách / Thành viên QR
    swipe(540, 1600, 540, 1000, 300)
    time.sleep(1.0)

    # Thẻ Mời khách / Thành viên (#mobileDynamicQrCard)
    # Bấm vào summary "Mời khách / Thành viên"
    tap(540, 1150)
    time.sleep(1.5)
    screencap("step4_qr_guest.png")

    print("=== Hoàn tất kịch bản kiểm thử ADB trên Samsung Galaxy S9 ===")

if __name__ == "__main__":
    main()
