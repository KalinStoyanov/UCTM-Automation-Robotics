from src.kinematic_simulator import KinematicSimulator


class Go2Adapter:
    COMMANDS = {
        "STOP",
        "FORWARD",
        "BACKWARD",
        "TURN_LEFT_90",
        "TURN_RIGHT_90",
    }

    def __init__(self, mode="SIMULATION"):
        if mode not in ("SIMULATION", "REAL"):
            raise ValueError("Invalid mode")

        self.mode = mode
        self.simulator = KinematicSimulator()
        self.last_command = "STOP"

        if mode == "REAL":
            raise RuntimeError(
                "REAL mode requires verified Go2 WebRTC "
                "motion API configuration"
            )

    def command(self, name):
        if name not in self.COMMANDS:
            raise ValueError(f"Unsupported command: {name}")

        self.simulator.command(name)
        self.last_command = name

    def step(self, dt):
        self.simulator.step(dt)

    def status(self):
        result = self.simulator.status()
        result["mode"] = self.mode
        result["last_command"] = self.last_command
        return result


def main():
    robot = Go2Adapter(mode="SIMULATION")

    robot.command("FORWARD")
    robot.step(1.0)

    print("=== GO2 ADAPTER ===")
    print("Mode:", robot.status()["mode"])
    print("Position:", robot.status()["x_m"], "m")

    robot.command("STOP")

    s = robot.status()

    print(
        "Linear:",
        s["linear_m_s"], "m/s =",
        s["linear_km_h"], "km/h"
    )

    print(
        "Angular:",
        s["angular_rad_s"], "rad/s =",
        s["angular_deg_s"], "deg/s"
    )


if __name__ == "__main__":
    main()
