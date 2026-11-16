import argparse
import json

from src.gesture_image_pipeline import run_image_pipeline
from src.unitree.gesture_go2_bridge import GestureGo2Bridge
from src.unitree.go2_webrtc import Go2WebRTC


def main():
    parser = argparse.ArgumentParser(description="DD-M2 control")
    parser.add_argument(
        "--mode",
        choices=("simulation", "real"),
        default="simulation"
    )
    args = parser.parse_args()

    with open("config/ddm2.json", encoding="utf-8") as f:
        cfg = json.load(f)

    if cfg["robot"]["mode"] != "SIMULATION":
        raise SystemExit("Configuration requires SIMULATION mode.")

    if cfg["robot"]["motion_enabled"]:
        raise SystemExit("Motion must remain disabled.")

    if args.mode == "real":
        raise SystemExit(
            "REAL mode is disabled until robot commissioning."
        )

    print("=== DD-M2 ===")
    print("Robot:", cfg["robot"]["model"])
    print("Mode:", cfg["robot"]["mode"])
    print("Gesture FPS:", cfg["gesture"]["fps"])
    print("Configured linear speed:",
          cfg["motion"]["linear_speed_m_s"], "m/s =",
          cfg["motion"]["linear_speed_m_s"] * 3.6, "km/h")
    print("Configured angular speed:",
          cfg["motion"]["angular_speed_rad_s"], "rad/s =",
          cfg["motion"]["angular_speed_rad_s"] * 180 / 3.141592653589793,
          "deg/s")
    print("WebRTC:", Go2WebRTC().status())

    bridge = GestureGo2Bridge()

    for image_path in (
        "test_images/thumb_up.png",
        "test_images/open_palm.jpg",
    ):
        result = run_image_pipeline(image_path)
        command = result["command"]

        print(
            f"Image: {image_path}, "
            f"Gesture: {result['gesture']}, "
            f"Command: {command}"
        )

        for _ in range(5):
            bridge.detect(
                None if command == "NONE" else command
            )
            bridge.step(1.0 / 30.0)

    status = bridge.status()

    print("\n=== FINAL STATUS ===")
    print("Last command:", status["last_sent"])

    s = status["pipeline"]

    print(f"Position: {s['x_m']:.4f} m")
    print(f"Heading: {s['heading_deg']:.2f} deg")
    print(
        f"Linear: {s['linear_m_s']} m/s = "
        f"{s['linear_km_h']} km/h"
    )
    print(
        f"Angular: {s['angular_rad_s']} rad/s = "
        f"{s['angular_deg_s']} deg/s"
    )


if __name__ == "__main__":
    main()
