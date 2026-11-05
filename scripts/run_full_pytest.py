import os
import subprocess
import sys

os.environ["GEMINI_API_KEY"] = "test_dummy_key_12345"
os.environ["DISABLE_REAL_EMAIL"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

cmd = [sys.executable, "-m", "pytest", "tests", "--basetemp=.pytest_tmp", "-v"]
res = subprocess.run(cmd)
sys.exit(res.returncode)
