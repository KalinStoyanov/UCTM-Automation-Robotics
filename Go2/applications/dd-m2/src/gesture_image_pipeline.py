from pathlib import Path

import cv2
import mediapipe as mp

from src.gesture_commands import classify_gesture
from src.gesture_pipeline import GesturePipeline


MODEL = "models/gesture_recognizer.task"


def run_image_pipeline(image_path, repetitions=5, fps=30):
    if repetitions < 1 or fps <= 0:
        raise ValueError("Invalid parameters")

    image_path = Path(image_path)

    frame = cv2.imread(str(image_path))

    if frame is None:
        raise FileNotFoundError(image_path)

    height, width = frame.shape[:2]

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    image = mp.Image(
        image_format=mp.ImageFormat.SRGB,
        data=rgb
    )

    options = mp.tasks.vision.GestureRecognizerOptions(
        base_options=mp.tasks.BaseOptions(
            model_asset_path=MODEL
        ),
        running_mode=mp.tasks.vision.RunningMode.IMAGE
    )

    pipeline = GesturePipeline()
    dt = 1.0 / fps

    with mp.tasks.vision.GestureRecognizer.create_from_options(
        options
    ) as recognizer:

        result = recognizer.recognize(image)

        gesture, command = classify_gesture(
            result, width, height
        )

        if command == "NONE":
            command = None

        for _ in range(repetitions):
            pipeline.detect(command)
            pipeline.step(dt)

    return {
        "image": str(image_path),
        "gesture": gesture,
        "command": command,
        "status": pipeline.status(),
    }


def main():
    images = (
        "test_images/open_palm.jpg",
        "test_images/thumb_up.png",
    )

    for path in images:
        print(f"\n=== {path} ===")

        result = run_image_pipeline(path)

        print("Gesture:", result["gesture"])
        print("Command:", result["command"])

        s = result["status"]

        print(
            f'Position: x={s["x_m"]:.4f} m, '
            f'y={s["y_m"]:.4f} m'
        )
        print(f'Heading: {s["heading_deg"]:.2f} deg')
        print(
            f'Linear: {s["linear_m_s"]} m/s '
            f'= {s["linear_km_h"]} km/h'
        )
        print(
            f'Angular: {s["angular_rad_s"]} rad/s '
            f'= {s["angular_deg_s"]} deg/s'
        )


if __name__ == "__main__":
    main()
