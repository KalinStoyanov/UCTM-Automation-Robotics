import random

from src.gesture_pipeline import GesturePipeline


def simulate_intervals(intervals, command="FORWARD",
                       required=3, timeout=0.5):
    p = GesturePipeline(required=required, timeout=timeout)
    history = []

    for dt in intervals:
        filtered = p.detect(command)
        p.step(dt)

        history.append({
            "time_s": p.controller.time,
            "filtered": filtered,
            "x_m": p.controller.robot.x,
            "timed_out": p.controller.timed_out,
        })

    return p, history


def random_intervals(n=100, min_fps=10,
                     max_fps=30, seed=42):
    if n <= 0 or min_fps <= 0 or max_fps < min_fps:
        raise ValueError("Invalid parameters")

    rng = random.Random(seed)

    return [
        1.0 / rng.uniform(min_fps, max_fps)
        for _ in range(n)
    ]


def simulate_dropout(dropout_s, fps=30):
    if dropout_s < 0 or fps <= 0:
        raise ValueError("Invalid parameters")

    p = GesturePipeline()
    dt = 1.0 / fps

    for _ in range(5):
        p.detect("FORWARD")
        p.step(dt)

    x_before = p.controller.robot.x

    # No gesture observations during dropout.
    # Simulation time continues to advance.
    if dropout_s > 0:
        p.step(dropout_s)

    return {
        "dropout_s": dropout_s,
        "x_before_m": x_before,
        "x_after_m": p.controller.robot.x,
        "timed_out": p.controller.timed_out,
        "status": p.status(),
        "pipeline": p,
    }


def simulate_recovery(fps=30):
    r = simulate_dropout(1.0, fps=fps)
    p = r["pipeline"]
    dt = 1.0 / fps

    x_stopped = p.controller.robot.x
    positions = []

    for _ in range(3):
        p.detect("FORWARD")
        p.step(dt)
        positions.append(p.controller.robot.x)

    return {
        "x_stopped": x_stopped,
        "positions": positions,
        "resumed": positions[-1] > x_stopped,
        "status": p.status(),
    }


def main():
    print("=== VARIABLE FPS ===")

    for fps in (10, 15, 30):
        intervals = [1.0 / fps] * 30
        p, history = simulate_intervals(intervals)
        s = p.status()

        print(
            f'FPS={fps:2} '
            f'time={s["time_s"]:.3f} s '
            f'x={s["x_m"]:.4f} m '
            f'timeout={s["timed_out"]}'
        )

    print("\n=== RANDOM FRAME INTERVALS ===")

    intervals = random_intervals()
    p, history = simulate_intervals(intervals)
    s = p.status()

    print(
        f'frames={len(intervals)} '
        f'time={s["time_s"]:.3f} s '
        f'x={s["x_m"]:.4f} m '
        f'timeout={s["timed_out"]}'
    )

    print("\n=== DROPOUT ===")

    for duration in (0.2, 0.5, 1.0):
        r = simulate_dropout(duration)

        print(
            f'dropout={duration:.1f} s '
            f'x_before={r["x_before_m"]:.4f} m '
            f'x_after={r["x_after_m"]:.4f} m '
            f'timeout={r["timed_out"]}'
        )

    print("\n=== RECOVERY ===")

    r = simulate_recovery()

    print(
        f'x_stopped={r["x_stopped"]:.4f} m '
        f'positions={r["positions"]} '
        f'resumed={r["resumed"]}'
    )

    print("\n=== SPEED UNITS ===")

    s = r["status"]

    print(
        f'Linear: {s["linear_m_s"]} m/s '
        f'= {s["linear_km_h"]} km/h'
    )

    print(
        f'Angular: {s["angular_rad_s"]} rad/s '
        f'= {s["angular_deg_s"]} deg/s'
    )


if __name__ == "__main__":
    main()
