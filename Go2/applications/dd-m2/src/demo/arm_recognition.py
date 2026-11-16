"""Recognize arm positions using hand and pose landmarks."""


def recognize_arms(persons, wrists):
    results = []

    for person in persons:
        points = person.get("pose_points")
        if not points:
            continue

        nose = points["nose"]
        shoulder_y = min(
            points["left_shoulder"]["y"],
            points["right_shoulder"]["y"],
        )

        x1, y1, x2, y2 = person["bbox"]

        for wrist in wrists:
            x = wrist["wrist_x"]
            y = wrist["wrist_y"]

            if not (x1 <= x <= x2 and y1 <= y <= y2):
                continue

            if y < nose["y"]:
                state = "ABOVE_HEAD"
            elif y < shoulder_y:
                state = "RAISED"
            else:
                state = "LOWERED"

            results.append({
                "person_id": person["id"],
                "wrist_x": x,
                "wrist_y": y,
                "state": state,
            })

    return results
