import cv2

from src.demo.controller import DemoController
from src.tracking.person_pose import PersonPose


def run_video(video_path, max_frames=100):
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise FileNotFoundError(video_path)

    vision = PersonPose()
    controller = DemoController()

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0

    dt = 1.0 / fps
    processed = 0

    try:
        while processed < max_frames:
            ok, frame = cap.read()
            if not ok:
                break

            height, width = frame.shape[:2]
            persons = vision.process(frame)

            result = controller.update(
                persons,
                width,
                height,
                dt=dt,
            )

            processed += 1

            if processed % 10 == 0:
                m = result["motion"]
                print(
                    f"Frame {processed:03d} | "
                    f"State={result['state']} | "
                    f"Target={result['target_id']} | "
                    f"Linear={m['linear_m_s']:.3f} m/s "
                    f"({m['linear_km_h']:.3f} km/h) | "
                    f"Angular={m['angular_rad_s']:.3f} rad/s "
                    f"({m['angular_deg_s']:.2f} deg/s)"
                )

    finally:
        cap.release()
        vision.close()

    print("Processed frames:", processed)
    print("Final state:", controller.state)


if __name__ == "__main__":
    run_video("data/videos/vtest.avi")
