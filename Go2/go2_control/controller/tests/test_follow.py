"""Follow mode: controller math, target tracking, lost-person stop, manual override.

Run: .venv/bin/python -m unittest discover -s controller/tests -t . -v
"""
import threading
import time
import unittest

from controller.ai import follow as F
from controller.ai.detector import Box, Detections
from controller.tests.test_robot import FakeRobot

CFG = F.clamp_config({})


def person(cx, h, w=None, cy=0.5, conf=0.9):
    w = w if w is not None else h * 0.4
    return Box(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, "person", conf)


class ControlMathTest(unittest.TestCase):
    def test_centered_person_no_turn(self):
        self.assertEqual(F.control(0.5, 0.3, CFG)[1], 0.0)
        self.assertEqual(F.control(0.54, 0.3, CFG)[1], 0.0)  # inside ±0.05 deadzone
        self.assertEqual(F.control(0.46, 0.3, CFG)[1], 0.0)

    def test_person_left_turns_left_positive(self):
        vx, vyaw = F.control(0.2, 0.3, CFG)
        self.assertGreater(vyaw, 0)
        self.assertAlmostEqual(vyaw, CFG["k_yaw"] * 0.3, places=3)

    def test_person_right_turns_right_negative(self):
        self.assertLess(F.control(0.8, 0.3, CFG)[1], 0)

    def test_yaw_clamped(self):
        cfg = F.clamp_config({"k_yaw": 3.0})
        self.assertEqual(F.control(0.0, 0.3, cfg)[1], 0.6)
        self.assertEqual(F.control(1.0, 0.3, cfg)[1], -0.6)

    def test_close_person_vx_zero(self):
        self.assertEqual(F.control(0.5, 0.95, CFG)[0], 0.0)  # above 0.92: too close
        self.assertEqual(F.control(0.5, 0.80, CFG)[0], 0.0)  # past TARGET_H 0.75: never backwards

    def test_box_touching_top_and_bottom_is_too_close(self):
        # a 0.70 box alone would still ask to move forward; touching both edges means too close
        self.assertGreater(F.control(0.5, 0.70, CFG, y1=0.10, y2=0.80)[0], 0)
        self.assertEqual(F.control(0.5, 0.70, CFG, y1=0.01, y2=0.99)[0], 0.0)
        self.assertTrue(F.is_too_close(0.70, 0.0, 1.0))
        self.assertFalse(F.is_too_close(0.70, 0.0, 0.70))   # touches only the top
        self.assertTrue(F.is_too_close(0.93))

    def test_defaults_for_robot_camera(self):
        self.assertEqual((CFG["target_h"], CFG["max_vx"]), (0.75, 0.6))
        self.assertEqual(F.TOO_CLOSE_H, 0.92)

    def test_far_person_forward_capped(self):
        self.assertEqual(F.control(0.5, 0.05, CFG)[0], 0.6)
        self.assertGreaterEqual(F.control(0.5, 0.50, CFG)[0], 0.55)  # ~3 m (box ~0.5): close to max
        self.assertAlmostEqual(F.control(0.5, 0.60, CFG)[0], CFG["k_x"] * 0.15, places=3)

    def test_minimum_forward_speed(self):
        self.assertEqual(F.control(0.5, 0.70, CFG)[0], F.MIN_VX)   # 2.5 * 0.05 = 0.125 -> 0.25
        self.assertEqual(F.control(0.5, 0.73, CFG)[0], 0.0)         # inside the forward deadzone
        for h in [i / 100 for i in range(0, 100)]:
            vx = F.control(0.5, h, CFG)[0]
            self.assertTrue(vx == 0.0 or F.MIN_VX <= vx <= 0.6, (h, vx))

    def test_slow_detector_caps_vx(self):
        self.assertEqual(F.control(0.5, 0.05, CFG, slow=True)[0], F.SLOW_MAX_VX)
        self.assertEqual(F.SLOW_MAX_VX, F.MIN_VX)  # never below the walking minimum

    def test_config_is_clamped(self):
        cfg = F.clamp_config({"max_vx": 5, "max_yaw": -1, "target_h": "x", "k_x": 99})
        self.assertEqual(cfg["max_vx"], 0.6)
        self.assertEqual(cfg["max_yaw"], 0.0)
        self.assertEqual(cfg["k_x"], 5.0)
        self.assertEqual(cfg["target_h"], F.DEFAULTS["target_h"])
        self.assertEqual(F.clamp_config({"max_vx": 0.1})["max_vx"], F.MIN_VX)  # slider floor


class TrackerTest(unittest.TestCase):
    def test_largest_person_becomes_target(self):
        c = F.FollowController()
        c.on_detections([person(0.2, 0.2), person(0.7, 0.4)], 0.0)
        self.assertAlmostEqual(c.target.cx, 0.7)

    def test_keeps_target_by_iou_even_if_other_grows(self):
        c = F.FollowController()
        c.on_detections([person(0.3, 0.3)], 0.0)
        c.on_detections([person(0.31, 0.3), person(0.8, 0.6)], 0.1)
        self.assertAlmostEqual(c.target.cx, 0.31)

    def test_switches_only_after_lost_half_second(self):
        c = F.FollowController()
        c.on_detections([person(0.3, 0.3)], 0.0)
        c.on_detections([person(0.8, 0.3)], 0.3)   # original gone 0.3 s: keep it
        self.assertAlmostEqual(c.target.cx, 0.3)
        c.on_detections([person(0.8, 0.3)], 0.6)   # gone 0.6 s: switch
        self.assertAlmostEqual(c.target.cx, 0.8)


class SwitchWithoutStopTest(unittest.TestCase):
    def test_target_jumps_but_someone_is_visible_no_stop(self):
        """Target disappears while another person stays visible: switch after 0.5 s, never stop."""
        c = F.FollowController()
        c.reset(0.0)
        kinds = []
        for i in range(30):
            t = i * 0.1
            if i < 10:
                c.on_detections([person(0.3, 0.3)], t)
            elif i % 2 == 0:                       # detections slower than the 10 Hz tick
                c.on_detections([person(0.8, 0.3)], t)
            kinds.append(c.tick(t).kind)
        self.assertNotIn("stop", kinds)
        self.assertAlmostEqual(c.target.cx, 0.8)


class LostPersonTest(unittest.TestCase):
    def test_lost_person_gives_exactly_one_stop(self):
        c = F.FollowController()
        c.reset(0.0)
        out = []
        for i in range(40):                       # 4 s at 10 Hz
            t = i * 0.1
            if t < 1.0:
                c.on_detections([person(0.3, 0.3)], t)
            elif i % 3 == 0:
                c.on_detections([], t)            # detector keeps running, nobody there
            out.append((round(t, 1), c.tick(t).kind))
        stops = [t for t, k in out if k == "stop"]
        self.assertEqual(len(stops), 1, out)
        self.assertTrue(1.4 <= stops[0] <= 1.6, stops)  # last seen at 0.9 s + 0.5 s
        moves = [t for t, k in out if k == "move"]
        self.assertTrue(1.3 <= max(moves) <= 1.4, moves)  # coasts until the timeout, then stops
        self.assertTrue(all(k != "move" for t, k in out if t > stops[0]))

    def test_no_person_from_start_gives_one_stop(self):
        c = F.FollowController()
        c.reset(10.0)
        kinds = [c.tick(10.0 + i * 0.1).kind for i in range(30)]
        self.assertEqual(kinds.count("stop"), 1)
        self.assertNotIn("move", kinds)


class OpenPalmGestureTest(unittest.TestCase):
    """Gesture thread path: Open_Palm while following -> override fires once, even in cooldown,
    and the mapped RiseSit action is NOT sent."""

    def test_open_palm_override_bypasses_cooldown(self):
        from types import SimpleNamespace

        import numpy as np

        from controller.ai.gestures import STREAK, GestureMode

        robot = FakeRobot().start()
        robot.connect().result(timeout=2)
        try:
            gm = GestureMode(robot)
            res = SimpleNamespace(gestures=[[SimpleNamespace(category_name="Open_Palm", score=0.9)]], hand_landmarks=[])
            gm._rec = SimpleNamespace(recognize_for_video=lambda img, ts: res)
            gm._mp = SimpleNamespace(Image=lambda **k: None, ImageFormat=SimpleNamespace(SRGB=1))
            calls = []
            gm.override = lambda g: ("FollowStop", lambda: calls.append(g)) if g == "Open_Palm" else None
            gm._last_sent = time.monotonic()  # a normal gesture just fired: cooldown active
            for i in range(STREAK + 5):
                gm._process(np.zeros((8, 8, 3), np.uint8), i + 1)
            time.sleep(0.1)
            self.assertEqual(calls, ["Open_Palm"])
            self.assertNotIn("RiseSit", robot.names())
            self.assertEqual(gm.state()["action"], "FollowStop")
        finally:
            robot.close()


class FakeDetector:
    def __init__(self):
        self.ready = True
        self.error = ""
        self.fps = 15.0
        self._det = Detections()
        self.users = set()

    def set_persons(self, persons):
        self._det = Detections(self._det.seq + 1, time.monotonic(), tuple(persons))

    def latest(self):
        if self._det.boxes:  # keep producing fresh detections like a running YOLO
            self._det = Detections(self._det.seq + 1, time.monotonic(), self._det.boxes)
        return self._det

    def acquire(self, u):
        self.users.add(u)

    def release(self, u):
        self.users.discard(u)


class FollowIntegrationTest(unittest.TestCase):
    """FollowMode thread + real Socket.IO handlers + FakeRobot (records the wire)."""

    def setUp(self):
        from controller.app import create_app

        self.robot = FakeRobot().start()
        self.robot.connect().result(timeout=2)
        self.det = FakeDetector()
        self.app, self.sio = create_app(self.robot, detector=self.det, push_telemetry_task=False)
        self.follow = self.app.extensions["go2"]["follow"]
        self.gestures = self.app.extensions["go2"]["gestures"]
        self.client = self.sio.test_client(self.app)
        self.assertTrue(self.client.is_connected())

    def tearDown(self):
        self.follow.disable("toggle")
        self.follow.close()
        if self.client.is_connected():
            self.client.disconnect()
        self.robot.close()

    def start_following(self, p):
        self.det.set_persons([p])
        self.client.emit("ai", {"mode": "follow", "on": True}, callback=True)
        self.assertTrue(self.follow.enabled)
        time.sleep(0.45)

    def moves(self):
        return [p for _, n, p in self.robot.sent if n == "Move"]

    def test_follow_drives_robot_through_set_velocity(self):
        self.start_following(person(0.25, 0.25))  # left and far
        m = self.moves()
        self.assertTrue(m, self.robot.names())
        self.assertGreater(m[-1]["x"], 0)
        self.assertGreater(m[-1]["z"], 0)          # turn left
        self.assertEqual(m[-1]["y"], 0.0)

    def test_manual_velocity_disables_follow(self):
        self.start_following(person(0.25, 0.25))
        self.client.emit("velocity", {"vx": -0.2, "vy": 0, "vyaw": 0})
        self.assertFalse(self.follow.enabled)
        self.assertEqual(self.follow.last_disable["reason"], "manual")
        time.sleep(0.35)
        self.client.emit("velocity", {"vx": -0.2, "vy": 0, "vyaw": 0})
        time.sleep(0.15)
        self.assertEqual(self.moves()[-1], {"x": -0.2, "y": 0.0, "z": 0.0})  # manual command only
        notices = [e for e in self.client.get_received() if e["name"] == "notice"]
        self.assertTrue(notices and notices[-1]["args"][0]["reason"] == "manual")

    def test_stop_button_disables_follow_and_stops(self):
        self.start_following(person(0.25, 0.25))
        self.robot.clear()
        self.client.emit("stop", callback=True)
        self.assertFalse(self.follow.enabled)
        time.sleep(0.4)
        names = self.robot.names()
        self.assertIn("StopMove", names)
        self.assertNotIn("Move", names)

    def test_action_button_disables_follow(self):
        self.start_following(person(0.25, 0.25))
        self.client.emit("action", {"name": "Hello"}, callback=True)
        self.assertFalse(self.follow.enabled)

    def test_zero_velocity_is_not_manual_input(self):
        self.start_following(person(0.25, 0.25))
        self.client.emit("velocity", {"vx": 0, "vy": 0, "vyaw": 0})
        self.assertTrue(self.follow.enabled)

    def test_open_palm_stops_following(self):
        self.start_following(person(0.25, 0.25))
        ov = self.gestures.override("Open_Palm")
        self.assertEqual(ov[0], "FollowStop")
        self.assertIsNone(self.gestures.override("Thumb_Up"))
        self.robot.clear()
        ov[1]()
        self.assertFalse(self.follow.enabled)
        self.assertEqual(self.follow.last_disable["reason"], "gesture")
        time.sleep(0.3)
        self.assertIn("StopMove", self.robot.names())
        self.assertIsNone(self.gestures.override("Open_Palm"))  # not following -> normal RiseSit

    def test_person_lost_stops_once_and_stays_enabled(self):
        self.start_following(person(0.5, 0.3))
        self.det.set_persons([])
        self.det._det = Detections(self.det._det.seq + 1, time.monotonic(), ())
        time.sleep(1.2)
        self.assertTrue(self.follow.enabled)
        self.assertEqual(self.follow.state()["status"], "searching")
        names = self.robot.names()
        last_move = max(i for i, n in enumerate(names) if n == "Move")
        self.assertEqual(names[last_move + 1:].count("StopMove"), 1, names[last_move:])

    def test_slow_detector_warns_and_caps_vx(self):
        self.det.fps = 3.0
        self.start_following(person(0.5, 0.05))  # far away: would ask for 0.3 m/s
        time.sleep(1.5)                          # warning only after 1.5 s of running
        st = self.follow.state()
        self.assertTrue(st["slow"])
        self.assertLessEqual(self.moves()[-1]["x"], F.SLOW_MAX_VX)

    def test_last_client_leaving_disables_follow(self):
        self.start_following(person(0.25, 0.25))
        self.client.disconnect()
        self.assertFalse(self.follow.enabled)
        self.assertEqual(self.follow.last_disable["reason"], "no_client")


if __name__ == "__main__":
    unittest.main()
