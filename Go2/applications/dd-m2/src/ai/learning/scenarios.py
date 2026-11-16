"""B4: Synthetic training scenarios for visual target centering."""


def generate_training_examples():
    examples = []

    for x in range(0, 101):
        center_x = x / 100.0

        if center_x < 0.4:
            action = "TURN_LEFT"
        elif center_x > 0.6:
            action = "TURN_RIGHT"
        else:
            action = "STOP"

        examples.append((round(center_x, 2), action))

    return examples
