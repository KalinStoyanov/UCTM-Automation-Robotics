from src.demo.gesture_association import (
    associate_gesture,
)


PERSONS = [
    {
        "id": 5,
        "bbox": [100, 100, 300, 400],
    },
    {
        "id": 6,
        "bbox": [400, 100, 600, 400],
    },
]


def gesture(name, x, y, confidence=0.9):
    return {
        "name": name,
        "x": x,
        "y": y,
        "confidence": confidence,
    }


def test_target_thumb_up():
    result = associate_gesture(
        [gesture("Thumb_Up", 200, 200)],
        PERSONS,
        5,
    )
    assert result == "COME_TO_ME"


def test_ignore_other_person():
    result = associate_gesture(
        [gesture("Thumb_Up", 500, 200)],
        PERSONS,
        5,
    )
    assert result is None


def test_target_stop():
    result = associate_gesture(
        [gesture("Open_Palm", 200, 200)],
        PERSONS,
        5,
    )
    assert result == "STOP"


def test_low_confidence():
    result = associate_gesture(
        [
            gesture(
                "Thumb_Down",
                200,
                200,
                confidence=0.2,
            )
        ],
        PERSONS,
        5,
    )
    assert result is None


def test_conflicting_commands():
    result = associate_gesture(
        [
            gesture("Thumb_Up", 200, 200),
            gesture("Thumb_Down", 220, 220),
        ],
        PERSONS,
        5,
    )
    assert result is None


def test_stop_priority():
    result = associate_gesture(
        [
            gesture("Thumb_Up", 200, 200),
            gesture("Open_Palm", 220, 220),
        ],
        PERSONS,
        5,
    )
    assert result == "STOP"
