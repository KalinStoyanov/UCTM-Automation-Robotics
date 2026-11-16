import math

THUMB_MIN_ANGLE = 150.0


def classify_gesture(result, width, height):
    if not result.hand_landmarks or not result.gestures:
        return "NONE", "NONE"

    gesture = result.gestures[0][0].category_name
    hand = result.hand_landmarks[0]

    # Highest priority
    if gesture == "Open_Palm":
        return gesture, "STOP"

    if gesture not in ("Thumb_Up", "Thumb_Down"):
        return gesture, "NONE"

    a, b, c = hand[2], hand[3], hand[4]

    v1 = ((a.x - b.x) * width, (a.y - b.y) * height)
    v2 = ((c.x - b.x) * width, (c.y - b.y) * height)

    n1 = math.hypot(*v1)
    n2 = math.hypot(*v2)

    if n1 == 0 or n2 == 0:
        return gesture, "NONE"

    cosine = max(
        -1.0,
        min(1.0, (v1[0]*v2[0] + v1[1]*v2[1]) / (n1*n2))
    )

    joint_angle = math.degrees(math.acos(cosine))

    if joint_angle < THUMB_MIN_ANGLE:
        return gesture, "NONE"

    dx = (c.x - a.x) * width
    dy = (c.y - a.y) * height

    angle = math.degrees(math.atan2(-dy, dx)) % 360

    if 45 <= angle < 135:
        command = "FORWARD"
    elif 135 <= angle < 225:
        command = "TURN_LEFT_90"
    elif 225 <= angle < 315:
        command = "BACKWARD"
    else:
        command = "TURN_RIGHT_90"

    return gesture, command
