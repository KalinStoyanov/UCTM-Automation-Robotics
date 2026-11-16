from src.gesture_pipeline import GesturePipeline
from src.unitree.go2_adapter import Go2Adapter


class GestureGo2Bridge:
    def __init__(self):
        self.pipeline = GesturePipeline()
        self.robot = Go2Adapter(mode="SIMULATION")
        self.last_sent = "STOP"

    def detect(self, gesture):
        command = self.pipeline.detect(gesture)

        if command is not None:
            self._send(command)

        return command

    def step(self, dt):
        self.pipeline.step(dt)

        if self.pipeline.controller.timed_out:
            self._send("STOP")

    def _send(self, command):
        if command != self.last_sent:
            self.robot.command(command)
            self.last_sent = command

    def status(self):
        return {
            "pipeline": self.pipeline.status(),
            "robot": self.robot.status(),
            "last_sent": self.last_sent,
        }


def main():
    bridge = GestureGo2Bridge()

    dt = 1.0 / 30

    print("=== GESTURE TO GO2 BRIDGE ===")

    for gesture, frames in (
        ("FORWARD", 30),
        ("STOP", 5),
        ("FORWARD", 30),
    ):
        for _ in range(frames):
            bridge.detect(gesture)
            bridge.step(dt)

        s = bridge.status()

        print(
            f"Gesture={gesture:8} "
            f"Sent={s['last_sent']:8} "
            f"Pipeline x={s['pipeline']['x_m']:.4f} m "
            f"Robot mode={s['robot']['mode']}"
        )

    print("\n=== TIMEOUT ===")

    for _ in range(20):
        bridge.detect(None)
        bridge.step(dt)

    s = bridge.status()

    print("Last command:", s["last_sent"])
    print("Timed out:", s["pipeline"]["timed_out"])
    print(
        "Linear:",
        s["pipeline"]["linear_m_s"], "m/s =",
        s["pipeline"]["linear_km_h"], "km/h"
    )
    print(
        "Angular:",
        s["pipeline"]["angular_rad_s"], "rad/s =",
        s["pipeline"]["angular_deg_s"], "deg/s"
    )


if __name__ == "__main__":
    main()
