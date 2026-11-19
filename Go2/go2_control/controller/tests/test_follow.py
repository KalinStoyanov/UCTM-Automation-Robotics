"""Follow mode: controller math, target tracking, lost-person stop, manual override.

Run: .venv/bin/python -m unittest discover -s controller/tests -t . -v
"""
import threading
import time
import unittest
from unittest import mock

from controller.ai import follow as F
from controller.ai.detector import Box, Detections
from controller.tests.test_robot import FakeRobot

CFG = F.clamp_config({})


def person(cx, h, w=None, cy=0.5, conf=0.9, arms=0):
    """Person box; arms = arms above the head (0/1/2) or None (pose unknown)."""
    w = w if w is not None else h * 0.4
    return Box(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, "person", conf, arms)


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


def run(c, frames, t0=0.0, dt=0.1):
    """frames: list of person lists (one per 0.1 s). Returns [(t, Command)]."""
    out = []
    for n, persons in enumerate(frames):
        t = t0 + n * dt
        if persons is not None:
            c.on_detections(persons, t)
        out.append((round(t, 2), c.tick(t)))
    return out


class ArmGestureTest(unittest.TestCase):
    """Follow only starts after one arm is held above the head for RAISE_HOLD."""

    def test_armed_never_moves_without_a_raised_arm(self):
        c = F.FollowController()
        out = run(c, [[person(0.3, 0.3, arms=0)]] * 50)
        self.assertTrue(all(cmd.kind == "idle" and cmd.status == "armed" for _, cmd in out))
        self.assertEqual(c.state, F.ARMED)

    def test_one_arm_for_1s_locks(self):
        c = F.FollowController()
        out = run(c, [[person(0.3, 0.3, arms=1)]] * 12)
        kinds = [(t, cmd.kind) for t, cmd in out]
        first_move = min(t for t, k in kinds if k == "move")
        self.assertAlmostEqual(first_move, F.RAISE_HOLD, delta=0.11)
        self.assertEqual(c.state, F.FOLLOWING)
        self.assertEqual(c.events, ["lock"])

    def test_short_raise_does_not_lock(self):
        c = F.FollowController()
        frames = [[person(0.3, 0.3, arms=1)]] * 6 + [[person(0.3, 0.3, arms=0)]] * 3 + [[person(0.3, 0.3, arms=1)]] * 6
        out = run(c, frames)
        self.assertTrue(all(cmd.kind == "idle" for _, cmd in out))  # 0.6 s + 0.6 s, never 1 s in a row

    def test_unknown_pose_frame_neither_starts_nor_resets(self):
        c = F.FollowController()
        frames = [[person(0.3, 0.3, arms=1)]] * 5 + [[person(0.3, 0.3, arms=None)]] * 2 + [[person(0.3, 0.3, arms=1)]] * 5
        run(c, frames)
        self.assertEqual(c.state, F.FOLLOWING)

    def test_both_arms_is_not_a_start_signal(self):
        c = F.FollowController()
        run(c, [[person(0.3, 0.3, arms=2)]] * 20)
        self.assertEqual(c.state, F.ARMED)

    def test_locks_the_person_who_raised_the_arm(self):
        c = F.FollowController()
        other = person(0.8, 0.6, arms=0)  # larger, but not asking
        run(c, [[person(0.3, 0.3, arms=1), other]] * 12)
        self.assertAlmostEqual(c.target.cx, 0.3)

    def test_other_person_raising_arm_while_following_is_ignored(self):
        c = F.FollowController()
        run(c, [[person(0.3, 0.3, arms=1)]] * 12)
        run(c, [[person(0.3, 0.3, arms=0), person(0.8, 0.5, arms=1)]] * 15, t0=1.2)
        self.assertAlmostEqual(c.target.cx, 0.3)

    def test_both_arms_for_1s_stops_once_then_rearms(self):
        c = F.FollowController()
        run(c, [[person(0.3, 0.3, arms=1)]] * 12)
        out = run(c, [[person(0.3, 0.3, arms=2)]] * 14, t0=1.2)
        stops = [t for t, cmd in out if cmd.kind == "stop"]
        self.assertEqual(len(stops), 1)
        self.assertEqual(c.stop_reason, "both_arms")
        self.assertEqual(c.state, F.STOPPED)
        out = run(c, [[person(0.3, 0.3, arms=0)]] * 25, t0=2.6)
        self.assertEqual(c.state, F.ARMED)  # after STOPPED_SHOW
        self.assertTrue(all(cmd.kind != "move" for _, cmd in out))

    def test_open_palm_stops(self):
        c = F.FollowController()
        run(c, [[person(0.3, 0.3, arms=1)]] * 12)
        c.stop_following("palm")
        self.assertEqual(c.tick(1.3).kind, "stop")
        self.assertEqual(c.stop_reason, "palm")

    def test_lost_for_2s_stops_once_and_stands_still_meanwhile(self):
        c = F.FollowController()
        run(c, [[person(0.3, 0.3, arms=1)]] * 12)  # locked at ~1.0, last seen 1.1
        out = run(c, [[]] * 30, t0=1.2)            # nobody
        stops = [t for t, cmd in out if cmd.kind == "stop"]
        self.assertEqual(len(stops), 1)
        self.assertAlmostEqual(stops[0], 1.1 + F.LOST_TIMEOUT, delta=0.11)
        self.assertEqual(c.stop_reason, "lost")
        # not seen -> commanded speed is zero (no blind driving) until the stop
        moving = [cmd for t, cmd in out if cmd.kind == "move" and t > 1.1 + F.STALE + 0.05]
        self.assertTrue(moving and all(cmd.vx == 0 and cmd.vyaw == 0 for cmd in moving))

    def test_raise_progress(self):
        c = F.FollowController()
        run(c, [[person(0.3, 0.3, arms=1)]] * 6)
        self.assertAlmostEqual(c.raise_progress(0.5), 0.5, delta=0.01)


class ArmsRaisedTest(unittest.TestCase):
    """Keypoint rule: wrist above the top of the head."""

    @staticmethod
    def kp(lw_y, rw_y, conf=0.9):
        pts = [(0, 0, 0.0)] * 17
        pts[0] = (50, 100, conf)            # nose
        pts[1] = pts[2] = (50, 95, conf)    # eyes
        pts[5] = (30, 150, conf)            # shoulders
        pts[6] = (70, 150, conf)
        pts[9] = (20, lw_y, conf)           # wrists
        pts[10] = (80, rw_y, conf)
        return pts

    def test_counts(self):
        from controller.ai.detector import arms_raised
        # head top threshold = 95 - 0.3 * (150 - 95) = 78.5
        self.assertEqual(arms_raised(self.kp(200, 200)), 0)
        self.assertEqual(arms_raised(self.kp(60, 200)), 1)
        self.assertEqual(arms_raised(self.kp(60, 50)), 2)
        self.assertEqual(arms_raised(self.kp(85, 200)), 0)  # hand beside the head is not "above"

    def test_unknown_when_head_or_shoulders_missing(self):
        from controller.ai.detector import arms_raised
        self.assertIsNone(arms_raised(self.kp(60, 200, conf=0.1)))


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

    def acquire(self, u, pose=False):
        self.users.add(u)

    def release(self, u):
        self.users.discard(u)


class FollowIntegrationTest(unittest.TestCase):
    """FollowMode thread + real Socket.IO handlers + FakeRobot (records the wire)."""

    def setUp(self):
        from controller.app import create_app

        self.patch = mock.patch.multiple(F, RAISE_HOLD=0.3, STOP_HOLD=0.3, LOST_TIMEOUT=0.8, STOPPED_SHOW=0.5)
        self.patch.start()
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
        self.patch.stop()

    def start_following(self, p):
        """Enable (armed), raise one arm for RAISE_HOLD, lower it: now following."""
        up = Box(p.x1, p.y1, p.x2, p.y2, p.name, p.conf, 1)
        self.det.set_persons([up])
        self.client.emit("ai", {"mode": "follow", "on": True}, callback=True)
        self.assertTrue(self.follow.enabled)
        time.sleep(F.RAISE_HOLD + 0.25)
        self.assertTrue(self.follow.following, self.follow.state())
        self.det.set_persons([p])
        time.sleep(0.2)

    def moves(self):
        """Velocity commands, sport Move or AvoidMove (follow turns avoidance on), as x/y/z."""
        return [p if n == "Move" else {"x": p["x"], "y": p["y"], "z": p["yaw"]}
                for _, n, p in self.robot.sent if n in ("Move", "AvoidMove")]

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

    def test_armed_mode_does_not_move_or_stop(self):
        self.det.set_persons([person(0.25, 0.25, arms=0)])
        self.client.emit("ai", {"mode": "follow", "on": True}, callback=True)
        time.sleep(1.0)
        # no Move, and no StopMove either; only the avoidance switch-on requests
        self.assertEqual(self.robot.names(), ["AvoidSwitch", "AvoidGet", "AvoidRemote"])
        self.assertEqual(self.follow.state()["phase"], "armed")
        self.assertEqual(self.follow.state()["status"], "armed")

    def test_open_palm_stops_following_but_stays_armed(self):
        self.assertIsNone(self.gestures.override("Open_Palm"))  # not following -> normal RiseSit
        self.start_following(person(0.25, 0.25))
        ov = self.gestures.override("Open_Palm")
        self.assertEqual(ov[0], "FollowStop")
        self.assertIsNone(self.gestures.override("Thumb_Up"))
        self.robot.clear()
        ov[1]()
        time.sleep(0.3)
        self.assertTrue(self.follow.enabled)
        self.assertEqual(self.follow.state()["phase"], "stopped")
        self.assertEqual(self.follow.state()["stop_reason"], "длан")
        self.assertIn("StopMove", self.robot.names())
        self.assertNotIn("Move", self.robot.names()[self.robot.names().index("StopMove"):])
        self.assertIn("Следване: спрях (длан)", self.robot.events.texts())

    def test_both_arms_stop(self):
        self.start_following(person(0.25, 0.25))
        self.det.set_persons([person(0.25, 0.25, arms=2)])
        time.sleep(F.STOP_HOLD + 0.3)
        self.assertEqual(self.follow.state()["phase"], "stopped")
        self.assertIn("Следване: спрях (двете ръце горе)", self.robot.events.texts())

    def test_person_lost_stops_once_and_stays_enabled(self):
        self.start_following(person(0.5, 0.3))
        self.det.set_persons([])
        self.det._det = Detections(self.det._det.seq + 1, time.monotonic(), ())
        time.sleep(F.LOST_TIMEOUT + 0.3)
        self.assertTrue(self.follow.enabled)
        self.assertEqual(self.follow.state()["phase"], "stopped")
        self.assertEqual(self.follow.state()["stop_reason"], "изгубих те")
        names = self.robot.names()
        last_move = max(i for i, n in enumerate(names) if n in ("Move", "AvoidMove"))
        self.assertEqual(names[last_move + 1:].count("StopMove"), 1, names[last_move:])

    def test_lock_is_logged(self):
        self.start_following(person(0.3, 0.3))
        self.assertIn("Следване: вдигната ръка, следвам (с избягване)", self.robot.events.texts())

    def test_slow_detector_warns_and_caps_vx(self):
        self.det.fps = 3.0
        self.start_following(person(0.5, 0.05))  # far away: would ask for max speed
        time.sleep(1.2)                          # warning only after 1.5 s of running
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
