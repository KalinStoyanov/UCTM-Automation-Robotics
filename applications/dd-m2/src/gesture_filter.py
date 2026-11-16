class GestureFilter:
    VALID = {
        "FORWARD",
        "BACKWARD",
        "TURN_LEFT_90",
        "TURN_RIGHT_90",
    }

    def __init__(self, required=3):
        if type(required) is not int or required < 1:
            raise ValueError("required must be a positive integer")

        self.required = required
        self.candidate = None
        self.count = 0
        self.stable = None

    def update(self, command):
        if command == "STOP":
            self.reset()
            self.stable = "STOP"
            return "STOP"

        if command not in self.VALID:
            self.reset()
            return None

        if command == self.candidate:
            self.count += 1
        else:
            self.candidate = command
            self.count = 1

        if self.count >= self.required:
            self.stable = command
            return command

        self.stable = None
        return None

    def reset(self):
        self.candidate = None
        self.count = 0
        self.stable = None
