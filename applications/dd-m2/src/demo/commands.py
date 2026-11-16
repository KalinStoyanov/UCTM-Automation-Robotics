GESTURE_COMMANDS = {
    "Thumb_Up": "COME_TO_ME",
    "Thumb_Down": "MOVE_AWAY",
    "Open_Palm": "STOP",
}


def map_gesture(name):
    return GESTURE_COMMANDS.get(name, "NONE")
