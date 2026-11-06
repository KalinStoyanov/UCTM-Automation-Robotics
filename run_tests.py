import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = Path("results/test_runner_state.json")

STAGES = [
    {
        "id": "baseline",
        "command": [
            sys.executable, "-m", "pytest", "-q",
            "tests/test_command_queue.py",
            "tests/test_command_worker.py",
            "tests/test_shutdown.py",
            "tests/test_go2_webrtc.py",
        ],
    },
    {
        "id": "webrtc_connect",
        "command": [
            sys.executable, "-m", "pytest", "-q",
            "tests/test_go2_connect.py",
        ],
    },
    {
        "id": "shutdown_inflight",
        "command": [
            sys.executable, "-m", "pytest", "-q",
            "tests/test_shutdown_inflight.py",
        ],
    },
    {
        "id": "watchdog",
        "command": [
            sys.executable, "-m", "pytest", "-q",
            "tests/test_watchdog.py",
        ],
    },
]


def save_state(index, status):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps({
            "next_stage": index,
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2) + "\n",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    start = 0

    if args.resume and STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        start = state["next_stage"]

    for index in range(start, len(STAGES)):
        stage = STAGES[index]
        print(f"\nRunning: {stage['id']}", flush=True)

        result = subprocess.run(stage["command"], check=False)

        if result.returncode != 0:
            save_state(index, "FAIL")
            print(f"STOP: {stage['id']} FAILED")
            return result.returncode

        save_state(index + 1, "PASS")
        print(f"PASS: {stage['id']}", flush=True)

    print("ALL STAGES PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
