from src.gesture_pipeline import GesturePipeline


def main():
    pipeline = GesturePipeline(required=3, timeout=0.5)

    sequence = (
        [("FORWARD", 0.1)] * 10
        + [(None, 0.1)] * 7
        + [("TURN_LEFT_90", 0.1)] * 40
        + [("STOP", 0.1)]
    )

    print("time_s | raw | filtered | x_m | y_m | heading_deg")

    for raw, dt in sequence:
        filtered = pipeline.detect(raw)
        pipeline.step(dt)
        s = pipeline.status()

        print(
            f'{s["time_s"]:6.2f} | '
            f'{str(raw):14} | '
            f'{str(filtered):14} | '
            f'{s["x_m"]:5.2f} | '
            f'{s["y_m"]:5.2f} | '
            f'{s["heading_deg"]:7.2f}'
        )

    print("FINAL STATUS:", pipeline.status())


if __name__ == "__main__":
    main()
