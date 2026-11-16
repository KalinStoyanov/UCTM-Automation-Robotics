from src.tracking.person_pose import PersonPose
from src.tracking.follow_controller import FollowController


class FollowDemo:
    def __init__(self):
        self.vision = PersonPose()
        self.controller = FollowController()

    def process(self, frame):
        persons = self.vision.process(frame)
        status = self.controller.update(persons)

        command = (
            "FOLLOW"
            if status["motion_allowed"]
            else "STOP"
        )

        return {
            "command": command,
            "state": status["state"],
            "target_id": status["target_id"],
            "persons": persons,
        }

    def reset(self):
        self.controller.reset()

    def close(self):
        self.vision.close()
