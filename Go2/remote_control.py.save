from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl

kb = KeyBindings()
status = "READY"


def update(command):
    global status
    status = command
    app.invalidate()


@kb.add("w")
def forward(event):
    update("FORWARD")


@kb.add("s")
def backward(event):
    update("BACKWARD")


@kb.add("a")
def left(event):
    update("TURN LEFT")


@kb.add("d")
def right(event):
    update("TURN RIGHT")


@kb.add("space")
def stop(event):
    update("STOP")


@kb.add("escape")
def exit_control(event):
    event.app.exit()


def screen():
    return (
        "UNITREE GO2 AIR - REMOTE CONTROL\n"
        "MODE: SIMULATION\n\n"
        "W: Forward    S: Backward\n"
        "A: Left       D: Right\n"
        "Space: Stop   Esc: Exit\n\n"
        f"Last command: {status}\n\n"
        "No commands are sent to the robot."
    )


app = Application(
    layout=Layout(Window(FormattedTextControl(screen))),
    key_bindings=kb,
    full_screen=True,
)


if __name__ == "__main__":
    app.run()
