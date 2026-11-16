
from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl

kb = KeyBindings()

status = "READY"
vx = 0.0
wz = 0.0


def update(command, linear, angular):
    global status, vx, wz
    status = command
    vx = linear
    wz = angular
    app.invalidate()


@kb.add("w")
def forward(event):
    update("FORWARD", 0.20, 0.0)


@kb.add("s")
def backward(event):
    update("BACKWARD", -0.20, 0.0)


@kb.add("a")
def left(event):
    update("TURN LEFT", 0.0, 0.30)


@kb.add("d")
def right(event):
    update("TURN RIGHT", 0.0, -0.30)


@kb.add("space")
def stop(event):
    update("STOP", 0.0, 0.0)


@kb.add("escape")
def exit_control(event):
    update("STOP", 0.0, 0.0)
    event.app.exit()


def screen():
    return (
        "UNITREE GO2 AIR - REMOTE CONTROL\n"
        "MODE: SIMULATION\n\n"
        "W: Forward    S: Backward\n"
        "A: Left       D: Right\n"
        "Space: Stop   Esc: Exit\n\n"
        f"Last command: {status}\n"
        f"Linear velocity vx: {vx:+.2f} m/s\n"
        f"Angular velocity wz: {wz:+.2f} rad/s\n\n"
        "No commands are sent to the robot."
    )


app = Application(
    layout=Layout(Window(FormattedTextControl(screen))),
    key_bindings=kb,
    full_screen=True,
)


if __name__ == "__main__":
    app.run()

