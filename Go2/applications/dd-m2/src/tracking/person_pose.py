import cv2
import mediapipe as mp

from src.arm_pose import ArmPose, classify_arm
from src.tracking.person_tracker import PersonTracker


class PersonPose:
    def __init__(self):
        self.tracker = PersonTracker()

        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(
                model_asset_path="models/pose_landmarker_lite.task"
            ),
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            num_poses=1,
        )

        self.pose = (
            mp.tasks.vision.PoseLandmarker.create_from_options(
                options
            )
        )

    def process(self, frame):
        height, width = frame.shape[:2]
        persons = self.tracker.track(frame)
        output = []

        for person in persons:
            x1, y1, x2, y2 = map(int, person["bbox"])

            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(width, x2)
            y2 = min(height, y2)

            result = dict(person)
            result["arm_raised"] = False
            result["left_arm"] = ArmPose.UNKNOWN.value
            result["right_arm"] = ArmPose.UNKNOWN.value

            if x2 <= x1 or y2 <= y1:
                output.append(result)
                continue

            crop = frame[y1:y2, x1:x2]
            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)

            image = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=rgb,
            )

            detected = self.pose.detect(image)

            if detected.pose_landmarks:
                landmarks = detected.pose_landmarks[0]
                crop_h, crop_w = crop.shape[:2]

                # Landmark positions in full-frame pixels.
                result["pose_points"] = {
                    name: {
                        "x": x1 + landmarks[index].x * crop_w,
                        "y": y1 + landmarks[index].y * crop_h,
                        "visibility": landmarks[index].visibility,
                    }
                    for name, index in {
                        "nose": 0,
                        "left_shoulder": 11,
                        "right_shoulder": 12,
                    }.items()
                }


                left = classify_arm(
                    landmarks[11],
                    landmarks[13],
                    landmarks[15],
                    image_width=crop_w,
                    image_height=crop_h,
                )

                right = classify_arm(
                    landmarks[12],
                    landmarks[14],
                    landmarks[16],
                    image_width=crop_w,
                    image_height=crop_h,
                )

                result["left_arm"] = left.value
                result["right_arm"] = right.value
                result["arm_raised"] = (
                    left == ArmPose.RAISED
                    or right == ArmPose.RAISED
                )

            output.append(result)

        return output

    def close(self):
        self.pose.close()
