import cv2

from src.demo.hand_gestures import HandGestures
from src.tracking.person_pose import PersonPose


def main():
    cap = cv2.VideoCapture("data/videos/gesture_test2.mp4")
    if not cap.isOpened():
        raise RuntimeError("Cannot open video")

    pose = PersonPose()
    hands = HandGestures()

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            persons = pose.process(frame)
            wrists = hands.detect_wrists(frame)

            for person in persons:
                points = person.get("pose_points")
                if not points:
                    continue

                nose = points["nose"]
                shoulders = [
                    points["left_shoulder"],
                    points["right_shoulder"],
                ]

                for name, point in points.items():
                    x, y = int(point["x"]), int(point["y"])
                    cv2.circle(frame, (x, y), 6, (255, 0, 0), -1)
                    cv2.putText(
                        frame, name, (x + 8, y),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.45, (255, 0, 0), 1,
                    )

                x1, y1, x2, y2 = person["bbox"]

                for wrist in wrists:
                    x = wrist["wrist_x"]
                    y = wrist["wrist_y"]

                    if not (x1 <= x <= x2 and y1 <= y <= y2):
                        continue

                    shoulder_y = min(p["y"] for p in shoulders)

                    if y < nose["y"]:
                        status = "ABOVE_HEAD"
                        color = (0, 255, 0)
                    elif y < shoulder_y:
                        status = "RAISED"
                        color = (0, 255, 255)
                    else:
                        status = "LOWERED"
                        color = (0, 0, 255)

                    cv2.circle(
                        frame, (int(x), int(y)),
                        9, color, -1,
                    )
                    cv2.putText(
                        frame, status,
                        (int(x) + 12, int(y) - 12),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.65, color, 2,
                    )

            cv2.imshow("DD-M2 Arm Diagnostic", frame)

            if cv2.waitKey(30) & 0xFF in (ord("q"), 27):
                break

            if cv2.getWindowProperty(
                "DD-M2 Arm Diagnostic",
                cv2.WND_PROP_VISIBLE,
            ) < 1:
                break

    finally:
        cap.release()
        pose.close()
        hands.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
