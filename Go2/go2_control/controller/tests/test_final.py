"""Demo sequence (order, no Move, cancellation), speed presets, posture limits.

Run: .venv/bin/python -m unittest discover -s controller/tests -t . -v
"""
import time
import unittest

from controller import demo as D
from controller import robot as R
from controller.tests.test_follow import FakeDetector
from controller.tests.test_robot import FakeRobot

FAST = [("Hello", 0.2), ("Stretch", 0.2), ("Sit", 0.2), ("RiseSit", 0.2)]


class DemoSequenceTest(unittest.TestCase):
    def make(self, silent=False, steps=FAST):
        self.r = FakeRobot(silent=silent).start()
        self.r.connect().result(timeout=2)
        return D.DemoSequence(self.r, steps)

    def tearDown(self):
        self.r.close()

    def test_full_run_order_and_never_moves(self):
        d = self.make()
        self.assertTrue(d.start())
        self.assertFalse(d.start())  # only one at a time
        d.join(5)
        self.assertEqual(self.r.names(), ["Hello", "Stretch", "Sit", "RiseSit"])
        self.assertNotIn("Move", self.r.names())
        st = d.state()
        self.assertFalse(st["running"])
        self.assertEqual(st["phase"], "done")

    def test_each_step_waits_for_reply_or_timeout_plus_pause(self):
        d = self.make(silent=True, steps=[("Hello", 0.3), ("Stretch", 0.3)])
        d.start()
        d.join(6)
        t = {n: ts for ts, n, _ in self.r.sent}
        # silent robot: ~1 s reply timeout + 0.3 s pause between the two steps
        self.assertTrue(1.25 <= t["Stretch"] - t["Hello"] <= 1.6, t["Stretch"] - t["Hello"])

    def test_cancel_during_pause_sends_nothing_more(self):
        d = self.make(steps=[("Hello", 1.0), ("Stretch", 1.0), ("Sit", 1.0)])
        d.start()
        time.sleep(0.3)  # Hello sent, now in its pause
        t0 = time.monotonic()
        self.assertTrue(d.cancel("manual"))
        self.assertLess(time.monotonic() - t0, 0.05)  # immediate
        d.join(1)
        self.assertFalse(d._thread.is_alive())
        time.sleep(1.2)
        self.assertEqual(self.r.names(), ["Hello"])
        self.assertEqual(d.state()["phase"], "cancelled")
        self.assertFalse(d.state()["running"])

    def test_cancel_while_waiting_for_reply(self):
        d = self.make(silent=True, steps=[("Hello", 0.1), ("Stretch", 0.1)])
        d.start()
        time.sleep(0.2)  # Hello sent, reply never comes
        d.cancel("stop")
        d.join(0.5)
        self.assertFalse(d._thread.is_alive())  # did not sit out the 1 s timeout
        time.sleep(1.5)
        self.assertEqual(self.r.names(), ["Hello"])

    def test_cancel_when_idle_is_noop(self):
        d = self.make()
        self.assertFalse(d.cancel())


class DemoManualInputTest(unittest.TestCase):
    """Real Socket.IO handlers: СТОП / Space, keys, joystick, action buttons cancel the demo."""

    def setUp(self):
        from controller.app import create_app

        self.r = FakeRobot().start()
        self.r.connect().result(timeout=2)
        self.app, self.sio = create_app(self.r, detector=FakeDetector(), push_telemetry_task=False)
        self.demo = self.app.extensions["go2"]["demo"]
        self.demo.steps = [("Hello", 1.0), ("Stretch", 1.0), ("Sit", 1.0)]
        self.c = self.sio.test_client(self.app)

    def tearDown(self):
        self.demo.cancel()
        if self.c.is_connected():
            self.c.disconnect()
        self.r.close()

    def start(self):
        self.assertTrue(self.c.emit("demo", {"start": True}, callback=True)["ok"])
        time.sleep(0.2)
        self.assertTrue(self.demo.running)

    def assert_cancelled_after_hello(self):
        self.assertFalse(self.demo.running)
        time.sleep(1.3)
        self.assertNotIn("Stretch", self.r.names())

    def test_stop_cancels(self):  # СТОП button and Space both emit "stop"
        self.start()
        self.c.emit("stop", callback=True)
        self.assert_cancelled_after_hello()
        self.assertIn("StopMove", self.r.names())

    def test_manual_velocity_cancels(self):
        self.start()
        self.c.emit("velocity", {"vx": 0.2, "vy": 0, "vyaw": 0})
        self.assert_cancelled_after_hello()

    def test_action_button_cancels(self):
        self.start()
        self.c.emit("action", {"name": "StandUp"}, callback=True)
        self.assert_cancelled_after_hello()

    def test_demo_stop_button_cancels(self):
        self.start()
        self.c.emit("demo", {"start": False}, callback=True)
        self.assert_cancelled_after_hello()

    def test_demo_state_in_telemetry(self):
        self.start()
        self.c.emit("velocity", {"vx": 0, "vy": 0, "vyaw": 0})  # zero velocity is not manual input
        self.assertTrue(self.demo.running)
        self.assertEqual(self.demo.state()["steps"], ["Hello", "Stretch", "Sit"])
        self.assertEqual(self.demo.state()["step"], 0)


class SpeedPresetTest(unittest.TestCase):
    def test_presets(self):
        p = {x["id"]: x for x in R.SPEED_PRESETS}
        self.assertEqual(R.SPEED_PRESETS[0]["id"], "slow")  # default on every page load
        self.assertEqual((p["slow"]["label"], p["slow"]["linear"], p["slow"]["yaw"]), ("Бавно", 0.3, 0.6))
        self.assertEqual((p["normal"]["label"], p["normal"]["linear"], p["normal"]["yaw"]), ("Нормално", 0.6, 1.0))
        self.assertEqual((p["fast"]["label"], p["fast"]["linear"], p["fast"]["yaw"]), ("Бърз", 1.0, 1.5))
        self.assertEqual([x["id"] for x in R.SPEED_PRESETS], ["slow", "normal", "fast"])

    def test_presets_within_hard_caps(self):
        for x in R.SPEED_PRESETS:
            self.assertLessEqual(x["linear"], R.MAX_LINEAR)
            self.assertLessEqual(x["yaw"], R.MAX_YAW)
        self.assertEqual((R.MAX_LINEAR, R.MAX_YAW), (1.0, 1.5))  # hard caps
        self.assertEqual(R.clamp_velocity(2.0, 0, -3.0), (1.0, 0.0, -1.5))  # Бърз is the cap, never above

    def test_config_sends_presets(self):
        from controller.app import create_app

        r = FakeRobot().start()
        try:
            app, _ = create_app(r, detector=FakeDetector(), push_telemetry_task=False)
            cfg = app.test_client().get("/api/config").get_json()
            self.assertEqual(cfg["speed_presets"], R.SPEED_PRESETS)
            self.assertNotIn("defaults", cfg)
        finally:
            r.close()


class PostureTest(unittest.TestCase):
    def test_clamped_to_small_range(self):
        self.assertEqual(R.clamp_posture("Euler", {"x": 1, "y": -1, "z": 0.5}), {"x": 0.15, "y": -0.15, "z": 0.0})
        self.assertEqual(R.clamp_posture("BodyHeight", {"data": -1}), {"data": -0.1})
        self.assertEqual(R.clamp_posture("BodyHeight", {"data": "x"}), {"data": 0.0})
        with self.assertRaises(ValueError):
            R.clamp_posture("Damp", {})

    def test_only_existing_names(self):
        self.assertEqual(set(R.available_posture({"Euler": 1})), {"Euler"})

    def test_posture_sent_as_awaited_action_with_params(self):
        r = FakeRobot().start()
        r.connect().result(timeout=2)
        try:
            self.assertEqual(r.posture("Euler", {"x": 0.5, "y": 0.05}).result(timeout=2), 0)
            self.assertEqual(r.sent[-1][1:], ("Euler", {"x": 0.15, "y": 0.05, "z": 0.0}))
            with self.assertRaises(ValueError):
                r.posture("FrontFlip", {})
        finally:
            r.close()


if __name__ == "__main__":
    unittest.main()
