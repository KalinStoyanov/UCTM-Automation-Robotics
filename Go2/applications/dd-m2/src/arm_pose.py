from enum import Enum


class ArmPose(Enum):
    RAISED = "RAISED"
    HORIZONTAL = "HORIZONTAL"
    LOWERED = "LOWERED"
    UNKNOWN = "UNKNOWN"


def classify_arm(shoulder, elbow, wrist, visibility=0.5, image_width=1, image_height=1):
    """
    Classify arm position using normalized MediaPipe landmarks.
    Image y-coordinate increases downward.
    """

    if min(
        shoulder.visibility,
        wrist.visibility
    ) < visibility:
        return ArmPose.UNKNOWN

    sx, sy = shoulder.x * image_width, shoulder.y * image_height
    ex, ey = elbow.x * image_width, elbow.y * image_height
    wx, wy = wrist.x * image_width, wrist.y * image_height

    if wy < sy:
        return ArmPose.RAISED

    length = ((wx - sx)**2 + (wy - sy)**2)**0.5

    if length < 0.08 * min(image_width, image_height):
        return ArmPose.UNKNOWN

    dx = (wx - sx) / length
    dy = (wy - sy) / length

    if abs(dx) > 0.85 and abs(dy) < 0.5:
        return ArmPose.HORIZONTAL

    if dy > 0.85 and abs(dx) < 0.5:
        return ArmPose.LOWERED

    return ArmPose.UNKNOWN
