"""Unitree Go2 Air transport - offline command preparation."""

import math
from dataclasses import dataclass

from unitree_webrtc_connect.constants import RTC_TOPIC, SPORT_CMD


MAX_LINEAR_SPEED = 0.20
MAX_ANGULAR_SPEED = 0.30

MODE = "SIMULATION"


@dataclass(frozen=True)
class VelocityCommand:
    vx: float = 0.0
    vy: float = 0.0
    wz: float = 0.0


def clamp(value, limit):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Velocity must be finite")
    return max(-limit, min(limit, value))


def make_move(vx=0.0, vy=0.0, wz=0.0):
    """Prepare a Go2 Move request without transmitting it."""

    command = VelocityCommand(
        vx=clamp(vx, MAX_LINEAR_SPEED),
        vy=clamp(vy, MAX_LINEAR_SPEED),
        wz=clamp(wz, MAX_ANGULAR_SPEED),
    )

    return {
        "topic": RTC_TOPIC["SPORT_MOD"],
        "options": {
            "api_id": SPORT_CMD["Move"],
            "parameter": {
                "x": command.vx,
                "y": command.vy,
                "z": command.wz,
            },
        },
    }


def make_stop():
    """Prepare a Go2 StopMove request without transmitting it."""

    return {
        "topic": RTC_TOPIC["SPORT_MOD"],
        "options": {
            "api_id": SPORT_CMD["StopMove"],
            "parameter": {},
        },
    }


def format_linear(value):
    return f"{value:+.2f} m/s | {value * 3.6:+.2f} km/h"


def format_angular(value):
    return (
        f"{value:+.2f} rad/s | "
        f"{math.degrees(value):+.2f} deg/s"
    )


if __name__ == "__main__":
    print("GO2 TRANSPORT")
    print("Mode:", MODE)
    print("No connection to robot.")
    print("No commands transmitted.")
    print()
    print("Move:", make_move(0.20, 0.0, 0.30))
    print("Stop:", make_stop())
    print()
    print("Linear limit:", format_linear(MAX_LINEAR_SPEED))
    print("Angular limit:", format_angular(MAX_ANGULAR_SPEED))
