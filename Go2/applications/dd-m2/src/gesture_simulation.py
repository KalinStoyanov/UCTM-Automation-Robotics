import sys
import types
import math

sys.modules["sounddevice"] = types.ModuleType("sounddevice")

import cv2
import mediapipe as mp

from src.gesture_commands import classify_gesture
from src.kinematic_simulator import KinematicSimulator


def recognize_image(recognizer, filename):
    image = cv2.imread(filename)
    if image is None:
        raise FileNotFoundError(filename)

    height, width = image.shape[:2]
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    result = recognizer.recognize(
        mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=rgb
        )
    )

    return classify_gesture(result, width, height)


def main():
    robot = KinematicSimulator()

    options = mp.tasks.vision.GestureRecognizerOptions(
        base_options=mp.tasks.BaseOptions(
            model_asset_path="models/gesture_recognizer.task"
        )
    )

    with mp.tasks.vision.GestureRecognizer.create_from_options(
        options
    ) as recognizer:

        # Test 1: Forward
        gesture, command = recognize_image(
            recognizer, "test_images/thumb_up.png"
        )

        assert command == "FORWARD"

        robot.command(command)
        robot.step(5.0)

        assert abs(robot.x - 1.0) < 1e-10

        print("TEST 1: Gesture -> FORWARD -> 1 m: PASS")
        print(robot.status())

        # Test 2: STOP
        gesture, command = recognize_image(
            recognizer, "test_images/open_palm.jpg"
        )

        assert command == "STOP"

        robot.command(command)
        robot.step(5.0)

        assert abs(robot.x - 1.0) < 1e-10
        assert robot.v == 0.0

        print("TEST 2: Gesture -> STOP: PASS")
        print(robot.status())

        # Test 3: Direct rotation command
        robot.command("TURN_LEFT_90")

        for _ in range(100):
            robot.step(0.1)

        assert abs(
            math.degrees(robot.heading) - 90.0
        ) < 1e-6

        assert robot.w == 0.0

        print("TEST 3: TURN_LEFT_90: PASS")
        print(robot.status())

    print("TOTAL: 3/3 PASS")


if __name__ == "__main__":
    main()
