import argparse
import time

import cv2

from src.demo.complete_controller import (
    CompleteDemoController,
)
from src.demo.display import draw_overlay
from src.demo.gesture_association import (
    associate_gesture,
)
from src.demo.hand_gestures import HandGestures
from src.demo.arm_recognition import recognize_arms
from src.tracking.person_pose import PersonPose
from src.robot.motion_bridge import MotionBridge


def run(source, show=True, mode="simulation"):
    cap = cv2.VideoCapture(source)

    if not cap.isOpened():
        raise RuntimeError(
            f"Cannot open video source: {source}"
        )

    vision = None
    hands = None

    controller = CompleteDemoController()
    bridge = MotionBridge(mode=mode)

    try:
        if show:
            print("DISPLAY: creating window", flush=True)
            cv2.namedWindow("DD-M2 Demo", cv2.WINDOW_NORMAL)
            print("DISPLAY: window created", flush=True)

        bridge.start()
        vision = PersonPose()
        hands = HandGestures()

        fps = cap.get(cv2.CAP_PROP_FPS)

        if fps <= 0:
            fps = 30.0

        dt = 1.0 / fps
        previous_time = time.monotonic()

        print("DD-M2 DEMO")
        print(f"MODE: {mode.upper()}")
        print("Keys: Q=quit, R=reset, S=stop")
        print("      1=stand, 2=sit, 3=lie")
        print("      A=left 90, D=right 90")

        while True:
            ok, frame = cap.read()

            if not ok:
                break

            # Skip frames for faster video playback.
            if not isinstance(source, int):
                cap.grab()

            now = time.monotonic()

            if isinstance(source, int):
                dt = max(
                    0.001,
                    min(0.2, now - previous_time),
                )

            previous_time = now

            height, width = frame.shape[:2]

            t0 = time.monotonic()
            persons = vision.process(frame)
            t1 = time.monotonic()
            gestures = hands.process(frame)
            wrists = hands.detect_wrists(frame)
            arms = recognize_arms(persons, wrists)
            t2 = time.monotonic()
            print(
                f"TIMING: pose={t1-t0:.3f}s "
                f"hands+arms={t2-t1:.3f}s "
                f"total={t2-t0:.3f}s",
                flush=True,
            )

            for person in persons:
                states = [
                    arm["state"]
                    for arm in arms
                    if arm["person_id"] == person["id"]
                ]

                person["arm_above_head"] = (
                    "ABOVE_HEAD" in states
                )
                person["arm_raised"] = any(
                    state in ("RAISED", "ABOVE_HEAD")
                    for state in states
                )

            print(
                "PERSONS:",
                [
                    (p["id"], p["arm_above_head"], p["arm_raised"])
                    for p in persons
                ],
                flush=True,
            )

            # Target association uses the target locked
            # before processing the current frame.
            command = associate_gesture(
                gestures,
                persons,
                controller.target_id,
            )

            # Raised arm takes priority over Open_Palm STOP.
            if command == "STOP":
                target = next(
                    (
                        person for person in persons
                        if person["id"] == controller.target_id
                    ),
                    None,
                )

                if target and target.get("arm_raised"):
                    command = None

            result = controller.update(
                persons,
                width,
                height,
                dt=dt,
                command=command,
            )

            print(
                f"CONTROLLER: state={result['state']} "
                f"target={result['target_id']} "
                f"posture={result['posture']}",
                flush=True,
            )
            bridge.update(result)

            if show:
                output = draw_overlay(
                    frame,
                    persons,
                    gestures,
                    result,
                )

                # Display arm positions next to detected wrists.
                colors = {
                    "LOWERED": (0, 0, 255),
                    "RAISED": (0, 255, 255),
                    "ABOVE_HEAD": (0, 255, 0),
                }

                for arm in arms:
                    x = int(arm["wrist_x"])
                    y = int(arm["wrist_y"])
                    state = arm["state"]
                    color = colors[state]

                    cv2.circle(
                        output, (x, y), 9, color, -1
                    )
                    cv2.putText(
                        output,
                        state,
                        (x + 12, y - 12),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.65, color, 2,
                    )

                # Display pose reference points.
                for person in persons:
                    for name, point in person.get(
                        "pose_points", {}
                    ).items():
                        x = int(point["x"])
                        y = int(point["y"])
                        cv2.circle(
                            output, (x, y), 6,
                            (255, 0, 0), -1,
                        )
                        cv2.putText(
                            output, name, (x + 8, y),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.45, (255, 0, 0), 1,
                        )

                print(
                    "OUTPUT:",
                    "type=", type(output),
                    "shape=", getattr(output, "shape", None),
                    "dtype=", getattr(output, "dtype", None),
                    "contiguous=", getattr(
                        getattr(output, "flags", None),
                        "c_contiguous", None
                    ),
                    flush=True,
                )
                print("DISPLAY: before imshow", flush=True)
                cv2.imshow("DD-M2 Demo", output)
                print("DISPLAY: after imshow", flush=True)

                print("DISPLAY: before waitKey", flush=True)
                key = cv2.waitKey(1) & 0xFF
                print("DISPLAY: after waitKey", flush=True)

                if key in (ord("q"), 27):
                    break

                if cv2.getWindowProperty(
                    "DD-M2 Demo",
                    cv2.WND_PROP_VISIBLE,
                ) < 1:
                    break

                key_commands = {
                    ord("1"): "STAND_UP",
                    ord("2"): "SIT",
                    ord("3"): "LIE_DOWN",
                    ord("a"): "TURN_LEFT_90",
                    ord("d"): "TURN_RIGHT_90",
                }

                if key == ord("s"):
                    key_result = controller.stop()
                    bridge.update(key_result)

                elif key == ord("r"):
                    key_result = controller.reset()
                    bridge.reset_stop()
                    bridge.update(key_result)

                elif key in key_commands:
                    key_result = controller.update(
                        persons,
                        width,
                        height,
                        dt=dt,
                        command=key_commands[key],
                    )
                    bridge.update(key_result)

    finally:
        bridge.close()
        cap.release()

        if vision is not None:
            vision.close()

        if hands is not None:
            hands.close()

        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--source",
        default="data/videos/vtest.avi",
    )

    parser.add_argument(
        "--no-display",
        action="store_true",
    )

    parser.add_argument(
        "--mode",
        choices=("simulation", "robot"),
        default="simulation",
    )

    args = parser.parse_args()

    source = (
        int(args.source)
        if args.source.isdigit()
        else args.source
    )

    run(
        source,
        show=not args.no_display,
        mode=args.mode,
    )


if __name__ == "__main__":
    main()
