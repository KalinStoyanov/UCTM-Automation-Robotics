from pathlib import Path

import cv2
import mediapipe as mp

from src.gesture_commands import classify_gesture
from src.gesture_pipeline import GesturePipeline


MODEL = Path("models/gesture_recognizer.task")
FPS = 30

SEQUENCE = [
    ("test_images/thumb_up.png", 30),
    ("test_images/open_palm.jpg", 15),
    ("test_images/thumb_up.png", 30),
]


def main():
    options = mp.tasks.vision.GestureRecognizerOptions(
        base_options=mp.tasks.BaseOptions(
            model_asset_path=str(MODEL)
        ),
        running_mode=mp.tasks.vision.RunningMode.IMAGE,
    )

    pipeline = GesturePipeline()
    dt = 1.0 / FPS

    with mp.tasks.vision.GestureRecognizer.create_from_options(
        options
    ) as recognizer:

        for filename, frames in SEQUENCE:
            bgr = cv2.imread(filename)

            if bgr is None:
                raise FileNotFoundError(filename)

            height, width = bgr.shape[:2]

            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

            image = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=rgb,
            )

            for _ in range(frames):
                result = recognizer.recognize(image)

                gesture, command = classify_gesture(
                    result, width, height
                )

                pipeline.detect(
                    None if command == "NONE" else command
                )
                pipeline.step(dt)

            s = pipeline.status()

            print(
                f"\nImage: {filename}\n"
                f"Gesture: {gesture}\n"
                f"Command: {command}\n"
                f"Position: {s['x_m']:.4f} m\n"
                f"Heading: {s['heading_deg']:.2f} deg\n"
                f"Linear: {s['linear_m_s']} m/s = "
                f"{s['linear_km_h']} km/h\n"
                f"Angular: {s['angular_rad_s']} rad/s = "
                f"{s['angular_deg_s']} deg/s"
            )


if __name__ == "__main__":
    main()
