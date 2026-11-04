@echo off
chcp 65001 >nul
set ADB_LIBUSB=1
set ADB=C:\Users\LENOVO\AppData\Local\Android\Sdk\platform-tools\adb.exe
"%ADB%" start-server
"%ADB%" -s 2223e8784b0c7ece reverse tcp:8088 tcp:8088
"%ADB%" -s 2223e8784b0c7ece shell input keyevent KEYCODE_WAKEUP
"%ADB%" -s 2223e8784b0c7ece shell wm dismiss-keyguard
"%ADB%" -s 2223e8784b0c7ece shell am start -n vn.edu.hust.seee.smarthome/vn.edu.hust.seee.smarthome.MainActivity
start "" "C:\Users\LENOVO\AppData\Local\scrcpy\scrcpy.exe" -s 2223e8784b0c7ece --window-title="Samsung Galaxy S9 - Smart Home Voice AI" --stay-awake
