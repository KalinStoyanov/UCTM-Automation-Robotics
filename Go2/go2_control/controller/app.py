"""Go2 Control: local web controller.

Run:  .venv/bin/python -m controller.app [--sim]   then open http://localhost:8080
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from pathlib import Path

import cv2
from flask import Flask, Response, jsonify, request, send_from_directory
from flask_socketio import SocketIO

from .ai.detector import YoloDetector
from .ai.follow import FollowMode
from .ai.gestures import GestureMode
from .ai.objects import ObjectMode
from .demo import DemoSequence
from .robot import (MAX_LINEAR, MAX_YAW, POSTURE_NEUTRAL, SPEED_PRESETS, BaseRobot, RobotSession, SimRobot,
                    available_actions, available_posture, clamp_velocity)

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT.parent / "logs"
log = logging.getLogger("go2.app")


class FrameHub:
    """Encodes each new frame (with AI overlays) once, shared by all MJPEG clients."""

    def __init__(self, robot: BaseRobot, overlays) -> None:
        self.robot = robot
        self.overlays = overlays
        self._lock = threading.Lock()
        self._seq = -1
        self._jpg: bytes | None = None

    def jpeg_after(self, after_seq: int, timeout: float = 1.0) -> tuple[int, bytes | None]:
        seq, frame = self.robot.wait_frame(after_seq, timeout=timeout)
        if frame is None or seq == after_seq:
            return after_seq, None
        with self._lock:
            if seq != self._seq:
                img = frame.copy()
                for o in self.overlays:
                    o.draw(img)
                ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 75])
                if ok:
                    self._seq, self._jpg = seq, buf.tobytes()
            return self._seq, self._jpg


def setup_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s.%(msecs)03d %(levelname)-7s %(name)-14s %(message)s", "%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in (logging.StreamHandler(sys.stdout),
              logging.FileHandler(LOG_DIR / f"controller-{time.strftime('%Y%m%d')}.log", encoding="utf-8")):
        h.setFormatter(fmt)
        root.addHandler(h)
    for noisy in ("werkzeug", "engineio", "socketio", "aioice", "aiortc", "ultralytics"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


DISABLE_NOTICE = {
    "manual": "Следването е спряно: ръчно управление",
    "gesture": "Следването е спряно с жест",
    "no_client": "Следването е спряно: няма отворен контролер",
    "demo": "Следването е спряно: демо",
}


def create_app(robot: BaseRobot, detector=None, push_telemetry_task: bool = True):
    detector = detector or YoloDetector(robot)
    gestures = GestureMode(robot)
    demo = DemoSequence(robot)
    follow = FollowMode(robot, detector)
    objects = ObjectMode(detector, skip_persons=lambda: follow.enabled)
    hub = FrameHub(robot, [objects, follow, gestures])
    actions = available_actions()
    ai_modes = {"gestures": gestures, "objects": objects, "follow": follow}

    # Open_Palm while following = stop following (instead of its mapped action).
    gestures.override = lambda g: ("FollowStop", lambda: follow.disable("gesture")) \
        if g == "Open_Palm" and follow.enabled else None

    # A gesture that sits / lays the robot down also ends following: otherwise follow's next
    # Move would stand it up again through the posture logic and walk off.
    def on_gesture_action(action):
        if action in ("Sit", "StandDown") and follow.enabled:
            follow.disable("gesture")

    gestures.on_trigger = on_gesture_action

    app = Flask(__name__, static_folder=str(ROOT / "static"), static_url_path="/static")
    socketio = SocketIO(app, async_mode="threading", ping_interval=5, ping_timeout=10)

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/config")
    def config():
        return jsonify(_config())

    def _config():
        return {
            "actions": actions,
            "sim": robot.sim,
            "limits": {"linear": MAX_LINEAR, "yaw": MAX_YAW},
            "speed_presets": SPEED_PRESETS,
            "gesture_mapping": gestures.mapping,
            "posture": {"limits": available_posture(), "neutral": POSTURE_NEUTRAL},
            "demo_steps": [n for n, _ in demo.steps],
        }

    def manual_override():
        """Keyboard / joystick / СТОП / action / posture input: manual input always wins
        over follow mode and the demo sequence."""
        demo.cancel("manual")
        follow.disable("manual")

    @app.get("/video")
    def video():
        def gen():
            seq = -1
            while True:
                new_seq, jpg = hub.jpeg_after(seq, timeout=1.0)
                if jpg is None:
                    continue
                seq = new_seq
                yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                       + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
        return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame",
                        headers={"Cache-Control": "no-store"})

    @app.get("/snapshot.jpg")
    def snapshot():
        _, jpg = hub.jpeg_after(-2, timeout=2.0)
        if jpg is None:
            return "no video", 503
        return Response(jpg, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})

    def _telemetry():
        t = robot.telemetry()
        t["ai"] = {k: m.state() for k, m in ai_modes.items()}
        t["demo"] = demo.state()
        return t

    @app.get("/api/telemetry")
    def telemetry():
        return jsonify(_telemetry())

    def on_follow_disabled(reason):
        text = DISABLE_NOTICE.get(reason)
        if text:
            robot.events.add(text, "warn")
            socketio.emit("notice", {"text": text, "kind": "follow_off", "reason": reason})

    follow.on_disabled = on_follow_disabled
    robot.events.subscribe(lambda e: socketio.emit("log", e))

    driver = {"sid": None}  # the client currently commanding motion
    clients: set[str] = set()

    @socketio.on("connect")
    def on_connect(*_):
        clients.add(request.sid)
        socketio.emit("config", _config(), to=request.sid)
        socketio.emit("telemetry", _telemetry(), to=request.sid)
        socketio.emit("log_history", robot.events.recent(30), to=request.sid)

    @socketio.on("disconnect")
    def on_disconnect(*_):
        clients.discard(request.sid)
        # A vanished driver must never leave the robot walking (the deadman would also catch it).
        # Other tabs closing must not interrupt the active driver.
        if request.sid == driver["sid"]:
            driver["sid"] = None
            robot.set_velocity(0, 0, 0)
        if not clients:
            follow.disable("no_client")  # never follow autonomously with nobody watching

    @socketio.on("velocity")
    def on_velocity(data):
        data = data or {}
        vx, vy, vyaw = data.get("vx", 0), data.get("vy", 0), data.get("vyaw", 0)
        if any(clamp_velocity(vx, vy, vyaw)):
            manual_override()
        vel = robot.set_velocity(vx, vy, vyaw)
        driver["sid"] = request.sid if any(vel) else None

    @socketio.on("action")
    def on_action(data):
        name = (data or {}).get("name", "")
        if name not in robot.allowed:
            log.warning("rejected action %r", name)
            return {"ok": False, "error": f"action not allowed: {name}"}
        manual_override()
        robot.action(name)
        return {"ok": True}

    @socketio.on("stop")
    def on_stop(*_):
        # СТОП (button, Space, Esc): cancel the demo, turn follow off, zero the velocity,
        # then StopMove (awaited on the robot loop; result goes to the operator log).
        manual_override()
        fut = robot.stop()
        try:
            code = fut.result(timeout=1.5)  # StopMove is awaited (reply timeout 1 s)
        except Exception:  # noqa: BLE001
            code = None
        socketio.emit("telemetry", _telemetry())  # chain / velocity state right away
        return {"ok": True, "code": code}

    @socketio.on("ai")
    def on_ai(data):
        data = data or {}
        mode = ai_modes.get(data.get("mode"))
        if mode is None:
            return {"ok": False}
        mode.set_enabled(bool(data.get("on")))
        socketio.emit("telemetry", _telemetry())
        return {"ok": True}

    @socketio.on("follow_config")
    def on_follow_config(data):
        return {"ok": True, "config": follow.update_config(data or {})}

    @socketio.on("demo")
    def on_demo(data):
        if (data or {}).get("start"):
            if robot.telemetry()["state"] != "connected":
                return {"ok": False, "error": "not connected"}
            follow.disable("demo")  # the demo never moves the robot
            return {"ok": demo.start()}
        manual_override()  # "Спри демото"
        return {"ok": True}

    @socketio.on("posture")
    def on_posture(data):
        data = data or {}
        names = [data.get("name")] if data.get("name") else []
        if data.get("reset"):
            names = list(available_posture())
        if not names or any(n not in robot.posture_allowed for n in names):
            return {"ok": False, "error": "posture not allowed"}
        manual_override()
        for n in names:
            robot.posture(n, POSTURE_NEUTRAL[n] if data.get("reset") else data.get("param"))
        return {"ok": True}

    @socketio.on("ai_all_off")
    def on_ai_all_off(*_):
        # page load: every AI mode starts off and must be turned on by hand
        for m in ai_modes.values():
            m.set_enabled(False)
        return {"ok": True}

    @socketio.on("robot")
    def on_robot(data):
        if (data or {}).get("connect"):
            robot.connect()
        else:
            robot.disconnect()
        return {"ok": True}

    def push_telemetry():
        while True:
            socketio.sleep(0.5)
            try:
                socketio.emit("telemetry", _telemetry())
            except Exception:  # noqa: BLE001
                log.exception("telemetry")

    if push_telemetry_task:
        socketio.start_background_task(push_telemetry)
    demo.on_change = lambda: socketio.emit("telemetry", _telemetry())
    app.extensions["go2"] = {"gestures": gestures, "objects": objects, "follow": follow, "detector": detector,
                             "demo": demo}
    return app, socketio


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Go2 Control")
    ap.add_argument("--sim", action="store_true", help="no robot: Mac webcam as video, commands only logged")
    ap.add_argument("--camera", default="auto", help="webcam for --sim: auto | index | none (test pattern)")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--no-connect", action="store_true", help="do not connect on startup")
    args = ap.parse_args(argv)

    setup_logging()
    robot: BaseRobot = SimRobot(None if args.camera == "none" else args.camera) if args.sim else RobotSession()
    robot.start()
    log.info("Go2 Control %s | actions: %s", "SIM" if args.sim else "ROBOT",
             ", ".join(a["name"] for a in available_actions()))
    if not args.no_connect:
        robot.connect()

    app, socketio = create_app(robot)

    def shutdown(*_):
        log.info("shutting down: StopMove + disconnect")
        robot.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    log.info("open http://localhost:%d", args.port)
    socketio.run(app, host=args.host, port=args.port, allow_unsafe_werkzeug=True, log_output=False)


if __name__ == "__main__":
    main()
