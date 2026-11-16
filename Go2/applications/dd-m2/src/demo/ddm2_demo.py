from src.demo.complete_controller import CompleteDemoController
from src.tracking.person_pose import PersonPose


class DDM2Demo:
    def __init__(self):
        self.vision = PersonPose()
        self.controller = CompleteDemoController()

    def process(self, frame, dt=1 / 30, command=None):
        height, width = frame.shape[:2]

        if command == "STOP":
            result = self.controller.stop()
            result["persons"] = []
            return result

        persons = self.vision.process(frame)

        result = self.controller.update(
            persons,
            width,
            height,
            dt=dt,
            command=command,
        )

        result["persons"] = persons
        return result

    def reset(self):
        return self.controller.reset()

    def close(self):
        self.vision.close()
