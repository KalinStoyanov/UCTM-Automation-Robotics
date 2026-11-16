from src.gesture_pipeline import GesturePipeline


def run_stream(fps, duration=2.0, required=3,
               timeout=0.5, drop_frames=None):
    if fps <= 0 or duration <= 0:
        raise ValueError("Invalid stream parameters")

    drop_frames = set(drop_frames or [])
    dt = 1.0 / fps
    frames = round(duration * fps)

    p = GesturePipeline(required=required, timeout=timeout)
    first_command_time = None

    for i in range(frames):
        raw = None if i in drop_frames else "FORWARD"
        command = p.detect(raw)

        if command == "FORWARD" and first_command_time is None:
            first_command_time = p.controller.time

        p.step(dt)

    return {
        "fps": fps,
        "frames": frames,
        "confirmation_s": first_command_time,
        "distance_m": p.controller.robot.x,
        "timed_out": p.controller.timed_out,
        "status": p.status(),
    }


def measure_timeout(fps=30, timeout=0.5):
    p = GesturePipeline(required=3, timeout=timeout)
    dt = 1.0 / fps

    for _ in range(5):
        p.detect("FORWARD")
        p.step(dt)

    last_detection = p.controller.last_detection
    deadline = last_detection + timeout

    while not p.controller.timed_out:
        p.detect(None)
        p.step(dt)

    observed = p.controller.time - last_detection

    return {
        "fps": fps,
        "configured_timeout_s": timeout,
        "stop_deadline_s": deadline,
        "observed_timeout_s": observed,
        "observation_delay_s": observed - timeout,
        "stopped": p.controller.robot.v == 0,
        "status": p.status(),
    }


def main():
    print("=== FPS COMPARISON ===")
    print("FPS | Confirmation (s) | Distance (m)")

    for fps in (10, 15, 30):
        r = run_stream(fps)
        print(
            f'{fps:3} | '
            f'{r["confirmation_s"]:16.4f} | '
            f'{r["distance_m"]:12.4f}'
        )

    print("\n=== DROPPED FRAMES ===")

    for fps in (10, 15, 30):
        r = run_stream(
            fps,
            drop_frames={1, 5, 9}
        )
        print(
            f'FPS={fps:2} '
            f'confirmation={r["confirmation_s"]} '
            f'distance={r["distance_m"]:.4f} m'
        )

    print("\n=== TIMEOUT ===")

    for fps in (10, 15, 30):
        r = measure_timeout(fps)
        print(
            f'FPS={fps:2} '
            f'timeout={r["observed_timeout_s"]:.4f} s '
            f'stopped={r["stopped"]}'
        )

    print("\n=== SPEED UNITS ===")
    p = GesturePipeline()
    for _ in range(3):
        p.detect("FORWARD")
        p.step(0.1)

    s = p.status()
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
