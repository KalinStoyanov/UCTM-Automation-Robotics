import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
errors = []

def check(name, ok):
    print(f"{'PASS' if ok else 'FAIL'}: {name}", flush=True)
    if not ok:
        errors.append(name)

print("=== DDStation Go2 Diagnostics ===", flush=True)

check("Python >= 3.11", sys.version_info >= (3, 11))
check("Virtual environment", sys.prefix != sys.base_prefix)

for name in ("pytest", "numpy", "cv2", "aiortc"):
    check(f"Module {name}", importlib.util.find_spec(name) is not None)

for name in ("run_tests.py", "remote_control.py", "go2_webrtc.py"):
    check(f"File {name}", (ROOT / name).is_file())

try:
    import go2_webrtc
    check("LIVE mode disabled", go2_webrtc.LIVE_ENABLED is False)
except Exception as exc:
    print(f"ERROR importing go2_webrtc: {exc}", flush=True)
    check("LIVE mode disabled", False)

if errors:
    print(f"ENVIRONMENT FAILED: {len(errors)} issue(s)")
    sys.exit(1)

print("\n=== Running automated tests ===", flush=True)
result = subprocess.run(
    [sys.executable, str(ROOT / "run_tests.py")],
    cwd=ROOT,
    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
)

if result.returncode:
    print("\nDDSTATION CHECK: FAIL")
    sys.exit(result.returncode)

print("\nDDSTATION CHECK: PASS")
