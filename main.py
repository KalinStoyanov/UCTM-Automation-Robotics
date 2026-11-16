"""DDStation — DD-M2 / Unitree Go2 Air application."""

import cv2
import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DDM2 = ROOT / "applications" / "dd-m2"


def main():
    parser = argparse.ArgumentParser(
        description="DDStation — DD-M2 / Go2 Air"
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        help="Camera index (default: 0)",
    )
    parser.add_argument("--source", type=str, default=None)
    args = parser.parse_args()

    if not DDM2.is_dir():
        raise SystemExit("DD-M2 application directory missing")

    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(DDM2))

    from core.communication import go2_webrtc

    if go2_webrtc.LIVE_ENABLED:
        raise SystemExit("LIVE mode must remain disabled")

    from src.demo.app import run

    print("=== DDStation / Go2 Air ===", flush=True)
    print("MODE: SIMULATION", flush=True)
    print(f"VIDEO SOURCE: {args.source if args.source else args.camera}", flush=True)
    print("LIVE COMMANDS: DISABLED", flush=True)

    run(
        source=args.source if args.source else args.camera,
        show=True,
        mode="simulation",
    )


if __name__ == "__main__":
    main()
