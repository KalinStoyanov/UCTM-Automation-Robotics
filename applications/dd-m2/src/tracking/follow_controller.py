from src.tracking.target_lock import TargetLock


class FollowController:
    def __init__(self):
        self.lock = TargetLock()
        self.state = "IDLE"

    def update(self, persons):
        """
        persons: list of dictionaries:
            {"id": int, "arm_raised": bool}
        """
        if self.state == "STOP":
            return self.status()

        if self.state == "IDLE":
            candidates = [
                p for p in persons
                if p.get("arm_raised") is True
            ]

            if len(candidates) == 1:
                if self.lock.lock(candidates[0]["id"]):
                    self.state = "FOLLOW"

        elif self.state == "FOLLOW":
            result = self.lock.update(persons)

            if result["status"] != "TRACKING":
                self._stop()
            elif result["target"].get("arm_raised") is not True:
                self._stop()

        return self.status()

    def _stop(self):
        self.lock.reset()
        self.state = "STOP"

    def reset(self):
        self.lock.reset()
        self.state = "IDLE"

    def status(self):
        return {
            "state": self.state,
            "target_id": self.lock.target_id,
            "motion_allowed": self.state == "FOLLOW",
        }
