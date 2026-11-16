from src.demo.commands import map_gesture


def associate_gesture(
    gestures,
    persons,
    target_id,
    min_confidence=0.65,
):
    if target_id is None:
        return None

    target = next(
        (
            p for p in persons
            if p["id"] == target_id
        ),
        None,
    )

    if target is None:
        return None

    x1, y1, x2, y2 = target["bbox"]

    matches = []

    for gesture in gestures:
        if gesture["confidence"] < min_confidence:
            continue

        x = gesture["x"]
        y = gesture["y"]

        if x1 <= x <= x2 and y1 <= y <= y2:
            command = map_gesture(gesture["name"])

            if command != "NONE":
                matches.append(command)

    if "STOP" in matches:
        return "STOP"

    unique = set(matches)

    if len(unique) == 1:
        return unique.pop()

    return None
