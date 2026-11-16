import math


class RobotSimulator:
    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.heading_deg = 0.0
        self.state = "STOPPED"

    def execute(self, command):
        if command == "FORWARD":
            self.state = "MOVING_FORWARD"

        elif command == "BACKWARD":
            self.state = "MOVING_BACKWARD"

        elif command == "TURN_LEFT_90":
            self.heading_deg = (self.heading_deg + 90) % 360
            self.state = "STOPPED"

        elif command == "TURN_RIGHT_90":
            self.heading_deg = (self.heading_deg - 90) % 360
            self.state = "STOPPED"

        elif command == "STOP":
            self.state = "STOPPED"

        else:
            self.state = "STOPPED"

        return self.status()

    def status(self):
        return {
            "x_m": self.x,
            "y_m": self.y,
            "heading_deg": self.heading_deg,
            "state": self.state
        }
