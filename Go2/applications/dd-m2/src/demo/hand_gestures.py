import cv2
import mediapipe as mp

from mediapipe.tasks import python
from mediapipe.tasks.python import vision


class HandGestures:
    def __init__(
        self,
        model_path="models/gesture_recognizer.task",
    ):
        options = vision.GestureRecognizerOptions(
            base_options=python.BaseOptions(
                model_asset_path=model_path
            ),
            running_mode=vision.RunningMode.IMAGE,
            num_hands=2,
        )

        self.recognizer = (
            vision.GestureRecognizer.create_from_options(
                options
            )
        )

    def process(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=rgb,
        )

        result = self.recognizer.recognize(image)

        height, width = frame.shape[:2]
        gestures = []

        for i, categories in enumerate(result.gestures):
            if not categories:
                continue

            category = categories[0]

            if category.category_name not in (
                "Thumb_Up",
                "Thumb_Down",
                "Open_Palm",
            ):
                continue

            if i >= len(result.hand_landmarks):
                continue

            landmarks = result.hand_landmarks[i]

            x = sum(p.x for p in landmarks) / len(landmarks)
            y = sum(p.y for p in landmarks) / len(landmarks)

            gestures.append({
                "name": category.category_name,
                "confidence": float(category.score),
                "x": x * width,
                "y": y * height,
                "wrist_x": landmarks[0].x * width,
                "wrist_y": landmarks[0].y * height,
            })

        return gestures

    def detect_wrists(self, frame):
        """Return wrist positions for every detected hand."""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=rgb,
        )

        result = self.recognizer.recognize(image)
        height, width = frame.shape[:2]

        return [
            {
                "wrist_x": hand[0].x * width,
                "wrist_y": hand[0].y * height,
            }
            for hand in result.hand_landmarks
        ]

    def close(self):
        self.recognizer.close()
