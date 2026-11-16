"""M10 offline release validation for DDStation."""

import ast
import datetime
import hashlib
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
STAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
OUT = ROOT / "results" / "m10" / STAMP
OUT.mkdir(parents=True, exist_ok=True)

FILES = [
    "core/communication/go2_webrtc.py",
    "core/communication/go2_transport.py",
    "core/control/remote_control.py",
    "applications/dd-m2/src/robot/robot_interface.py",
]

checks = {}
details = {}


def check(name, condition, message=""):
    checks[name] = bool(condition)
    details[name] = message
    print(f"{'PASS' if condition else 'FAIL'}: {name}")
    if message and not condition:
        print(" ", message)


def run(name, args, env=None):
    result = subprocess.run(
        args,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    (OUT / f"{name}.log").write_text(
        result.stdout, encoding="utf-8"
    )
    check(name, result.returncode == 0, f"Exit: {result.returncode}")
    print(result.stdout[-2000:])
    return result


# 1. Source files and syntax.
sources = {}
for relative in FILES:
    path = ROOT / relative
    if not path.is_file():
        check(f"source:{relative}", False, "Missing file")
        continue

    try:
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=relative)
        sources[relative] = source
        check(f"syntax:{relative}", True)
    except (SyntaxError, UnicodeError) as exc:
        check(f"syntax:{relative}", False, str(exc))


# 2. Offline safety configuration.
webrtc = sources.get(FILES[0], "")
transport = sources.get(FILES[1], "")
interface = sources.get(FILES[3], "")

try:
    tree = ast.parse(webrtc)
    live_values = [
        node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "LIVE_ENABLED"
            for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
    ]
    check(
        "LIVE_DISABLED",
        live_values == [False],
        f"LIVE_ENABLED assignments: {live_values}",
    )
except SyntaxError:
    check("LIVE_DISABLED", False, "WebRTC source cannot be parsed")


try:
    tree = ast.parse(transport)
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(
            node.value, ast.Constant
        ):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = node.value.value

    check(
        "SPEED_LIMITS",
        constants.get("MAX_LINEAR_SPEED") == 0.20
        and constants.get("MAX_ANGULAR_SPEED") == 0.30,
    )
    check("SIMULATION_MODE", constants.get("MODE") == "SIMULATION")
except SyntaxError:
    check("SPEED_LIMITS", False)
    check("SIMULATION_MODE", False)


# Structural checks; behavioral safety is tested by pytest.
for name, token in {
    "FAULT_GATE": "if self.fault:",
    "RECOVERY_AUTHORIZATION": "async def authorize_recovery",
    "WATCHDOG": "async def _watchdog",
    "STOP_CONFIRMATION": "self.stop_confirmed",
}.items():
    check(name, token in interface)


# 3. Python dependency consistency.
run("dependencies", [PYTHON, "-m", "pip", "check"])


# 4. Complete regression.
env = os.environ.copy()
env["PYTHONPATH"] = os.pathsep.join(
    [
        str(ROOT / "applications/dd-m2"),
        str(ROOT),
        env.get("PYTHONPATH", ""),
    ]
)

test = run(
    "regression",
    [
        PYTHON,
        "-m",
        "pytest",
        "tests",
        "applications/dd-m2/tests",
        "-q",
        "--tb=short",
    ],
    env=env,
)


# 5. Release manifest with SHA256 checksums.
manifest = {}
for directory in ("core", "applications/dd-m2", "tests", "tools"):
    base = ROOT / directory
    if not base.exists():
        continue

    for path in sorted(base.rglob("*.py")):
        relative = str(path.relative_to(ROOT))
        manifest[relative] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()

(OUT / "manifest.json").write_text(
    json.dumps(manifest, indent=2),
    encoding="utf-8",
)


# 6. Report.
passed = all(checks.values())
report = {
    "release": "DDStation-M10",
    "timestamp": STAMP,
    "mode": "SIMULATION",
    "live_enabled": False if checks.get("LIVE_DISABLED") else "UNVERIFIED",
    "status": "PASS" if passed else "FAIL",
    "python": sys.version,
    "checks": checks,
    "details": details,
    "files_hashed": len(manifest),
    "regression_exit_code": test.returncode,
    "scope": "Offline software validation only",
    "hardware_validation": "PENDING",
}

(OUT / "report.json").write_text(
    json.dumps(report, indent=2),
    encoding="utf-8",
)


# 7. Archive only if every check passed.
if passed:
    archive = OUT / "DDStation-M10-RC.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for relative in manifest:
            tar.add(ROOT / relative, arcname=relative)
        tar.add(OUT / "report.json", arcname="M10/report.json")
        tar.add(OUT / "manifest.json", arcname="M10/manifest.json")
        tar.add(OUT / "regression.log", arcname="M10/regression.log")
        tar.add(OUT / "dependencies.log", arcname="M10/dependencies.log")

    report["archive"] = str(archive)
    (OUT / "report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

print()
print("=" * 55)
print("M10 RELEASE CANDIDATE:", report["status"])
print("REPORT:", OUT / "report.json")
print("CHECKS:", sum(checks.values()), "/", len(checks))
print("SOURCE FILES:", len(manifest))
print("HARDWARE VALIDATION: PENDING")
print("=" * 55)

sys.exit(0 if passed else 1)
