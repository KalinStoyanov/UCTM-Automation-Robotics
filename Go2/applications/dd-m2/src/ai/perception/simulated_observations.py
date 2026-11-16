"""B1: Synthetic person detections in image coordinates."""


def simulated_person(center_x, width=0.15, confidence=0.95):
    if not 0.0 <= center_x <= 1.0:
        raise ValueError("Invalid center_x")

    if width <= 0 or width > 1:
        raise ValueError("Invalid width")

    x1 = max(0.0, center_x - width / 2)
    x2 = min(1.0, center_x + width / 2)

    return {
        "id": 1,
        "bbox": [x1, 0.2, x2, 0.8],
        "confidence": confidence,
    }
