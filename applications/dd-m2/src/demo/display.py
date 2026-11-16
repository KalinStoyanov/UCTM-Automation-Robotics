import cv2
import numpy as np


def draw_overlay(frame, persons, gestures, result):
    output = frame.copy()

    target_id = result["target_id"]

    for person in persons:
        x1, y1, x2, y2 = map(
            int, person["bbox"]
        )

        selected = person["id"] == target_id

        color = (
            (0, 255, 0)
            if selected
            else (160, 160, 160)
        )

        cv2.rectangle(
            output,
            (x1, y1),
            (x2, y2),
            color,
            2,
        )

        cv2.putText(
            output,
            f"ID {person['id']}",
            (x1, max(20, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2,
        )

    for gesture in gestures:
        x = int(gesture["x"])
        y = int(gesture["y"])

        cv2.circle(
            output,
            (x, y),
            7,
            (0, 255, 255),
            -1,
        )

        cv2.putText(
            output,
            gesture["name"],
            (x + 10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 255),
            2,
        )

    motion = result["motion"]

    lines = [
        "DD-M2 | SIMULATION ONLY",
        f"STATE: {result['state']}",
        f"TARGET: {target_id}",
        f"POSTURE: {result['posture']}",
        f"MODE: {result['distance_mode']}",
        (
            f"LINEAR: {motion['linear_m_s']:.3f} m/s"
            f" | {motion['linear_km_h']:.3f} km/h"
        ),
        (
            f"ANGULAR: {motion['angular_rad_s']:.3f} rad/s"
            f" | {motion['angular_deg_s']:.2f} deg/s"
        ),
    ]


    panel_width = 390
    height, width = output.shape[:2]

    panel = np.full(
        (height, panel_width, 3),
        (25, 25, 25),
        dtype=np.uint8,
    )

    y = 30
    for line in lines:
        if line.startswith("LINEAR:"):
            parts = line.split(" | ")
        elif line.startswith("ANGULAR:"):
            parts = line.split(" | ")
        else:
            parts = [line]

        for part in parts:
            cv2.putText(
                panel,
                part,
                (12, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
            y += 27

    return np.hstack((output, panel))
