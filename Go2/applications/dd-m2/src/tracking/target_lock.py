class TargetLock:
    def __init__(self):
        self.target_id = None

    def lock(self, person_id):
        if self.target_id is not None:
            return False

        self.target_id = int(person_id)
        return True

    def update(self, persons):
        if self.target_id is None:
            return {
                "status": "IDLE",
                "target_id": None,
                "target": None,
            }

        for person in persons:
            if person["id"] == self.target_id:
                return {
                    "status": "TRACKING",
                    "target_id": self.target_id,
                    "target": person,
                }

        lost_id = self.target_id
        self.target_id = None

        return {
            "status": "STOP",
            "target_id": lost_id,
            "target": None,
        }

    def reset(self):
        self.target_id = None
