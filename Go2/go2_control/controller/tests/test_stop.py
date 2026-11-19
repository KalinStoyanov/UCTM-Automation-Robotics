"""СТОП: full path through the real Socket.IO handler, operator log, trick note.

Run: .venv/bin/python -m unittest discover -s controller/tests -t . -v
"""
import time
import unittest
from unittest import mock

from controller import robot as R

from controller.tests.test_follow import FakeDetector, person
from controller.tests.test_robot import FakeRobot


class RobotStopTest(unittest.TestCase):
    def setUp(self):
        self.r = FakeRobot().start()
        self.r.connect().result(timeout=2)

    def tearDown(self):
        self.r.close()

    def test_stop_logs_and_awaits_stopmove(self):
        self.r.set_velocity(0.3, 0, 0)
        code = self.r.stop().result(timeout=2)  # awaited: returns the reply code
        self.assertEqual(code, 0)
        self.assertEqual(self.r.names()[-1], "StopMove")
        self.assertEqual(self.r.telemetry()["velocity"], {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})
        texts = self.r.events.texts()
        self.assertIn("СТОП", texts)
        self.assertTrue(any(t.startswith("StopMove: OK") for t in texts), texts)

    def test_stop_during_trick_sends_stopmove_then_balance(self):
        self.r.waits["Hello"] = 5.0
        self.r.action("Hello").result(timeout=2)
        self.r.clear()
        self.r.stop().result(timeout=2)
        self.assertEqual(self.r.names(), ["StopMove", "BalanceStand"])
        texts = self.r.events.texts()
        notes = [t for t in texts if "още върви" in t]
        self.assertEqual(len(notes), 1, texts)
        self.assertIn("Здрасти", notes[0])
        self.assertTrue(any(t.startswith("StopMove: OK") for t in texts), texts)
        self.assertTrue(any(t.startswith("Баланс: OK") for t in texts), texts)

    def test_robot_fsm_1006_means_trick_running(self):
        self.r.action("Hello").result(timeout=2)   # waits are 0: the estimate says "over"
        self.r._telemetry["fsm"] = 1006            # ... but the robot says a trick runs
        self.r.clear()
        self.r.stop().result(timeout=2)
        self.assertEqual(self.r.names(), ["StopMove", "BalanceStand"])

    def test_after_stop_fsm_is_reported(self):
        self.r.waits["Hello"] = 5.0
        self.r.action("Hello").result(timeout=2)
        self.r._telemetry["fsm"] = 1006
        with mock.patch.object(R, "STOP_CHECK_AFTER", 0.2):
            self.r.stop().result(timeout=2)
            time.sleep(0.4)
        self.assertTrue(any(t.startswith("0 s след СТОП: робот FSM 1006") or "FSM 1006" in t
                            for t in self.r.events.texts()), self.r.events.texts())

    def test_no_balance_when_no_trick(self):
        self.r.waits["Hello"] = 0.1
        self.r.action("Hello").result(timeout=2)
        time.sleep(0.2)
        self.r.clear()
        self.r.stop().result(timeout=2)
        self.assertEqual(self.r.names(), ["StopMove"])
        self.assertFalse(any("още върви" in t for t in self.r.events.texts()))

    def test_late_reply_is_logged_and_ends_the_trick(self):
        self.r.waits["Dance1"] = 30.0
        self.r.delays["Dance1"] = 1.3   # robot answers when the dance is over
        self.assertEqual(self.r.action("Dance1").result(timeout=3), "timeout")
        self.assertEqual(self.r._trick_running(), "Dance1")
        time.sleep(0.6)
        self.assertTrue(any(t.startswith("Танц 1: завърши, OK") for t in self.r.events.texts()), self.r.events.texts())
        self.assertIsNone(self.r._trick_running())

    def test_emergency_damp(self):
        self.r.set_velocity(0.3, 0, 0)
        self.assertEqual(self.r.emergency_damp().result(timeout=2), 0)
        self.assertEqual(self.r.names()[-1], "Damp")
        self.assertEqual(self.r.posture_state, R.LYING)
        self.assertTrue(any(t.startswith("АВАРИЙНО Damp → робот: OK") for t in self.r.events.texts()),
                        self.r.events.texts())
        with self.assertRaises(ValueError):
            self.r.action("Damp")  # still not an ordinary action
        self.r.clear()
        self.r.action("Hello").result(timeout=3)  # posture logic stands it up again
        self.assertEqual(self.r.names(), ["StandUp", "BalanceStand", "Hello"])

    def test_upper_layer_stop_is_not_logged_as_stop_button(self):
        self.r.stop(note="Следване: няма човек → стоп").result(timeout=2)
        self.assertNotIn("СТОП", self.r.events.texts())
        self.assertEqual(self.r.names(), ["StopMove"])


class StopButtonEndToEndTest(unittest.TestCase):
    """emit('stop') is exactly what the СТОП button, Space and Esc send."""

    def setUp(self):
        from controller.app import create_app

        self.r = FakeRobot().start()
        self.r.connect().result(timeout=2)
        self.det = FakeDetector()
        self.app, self.sio = create_app(self.r, detector=self.det, push_telemetry_task=False)
        ext = self.app.extensions["go2"]
        self.demo, self.follow = ext["demo"], ext["follow"]
        self.demo.steps = [("Hello", 1.0), ("Stretch", 1.0)]
        self.c = self.sio.test_client(self.app)

    def tearDown(self):
        self.demo.cancel()
        self.follow.disable("toggle")
        self.follow.close()
        if self.c.is_connected():
            self.c.disconnect()
        self.r.close()

    def test_stop_cancels_demo_follow_and_velocity(self):
        self.det.set_persons([person(0.3, 0.3)])
        self.c.emit("ai", {"mode": "follow", "on": True}, callback=True)
        time.sleep(0.3)
        self.assertTrue(self.follow.enabled)
        self.assertTrue(self.c.emit("demo", {"start": True}, callback=True)["ok"])  # turns follow off
        self.c.emit("ai", {"mode": "follow", "on": True}, callback=True)            # and on again
        time.sleep(0.2)
        self.assertTrue(self.demo.running and self.follow.enabled)
        self.c.get_received()
        self.r.clear()

        self.assertEqual(self.c.emit("stop", callback=True), {"ok": True, "code": 0})
        self.assertFalse(self.demo.running)
        self.assertFalse(self.follow.enabled)
        time.sleep(0.4)
        names = self.r.names()
        self.assertIn("StopMove", names)
        self.assertNotIn("Move", names[names.index("StopMove"):])
        self.assertNotIn("Stretch", names)
        self.assertEqual(self.r.telemetry()["velocity"], {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})
        logs = [e["args"][0]["text"] for e in self.c.get_received() if e["name"] == "log"]
        self.assertIn("СТОП", logs)
        self.assertTrue(any(t.startswith("StopMove: OK") for t in logs), logs)

    def test_emergency_needs_the_hold(self):
        self.assertEqual(self.c.emit("emergency", {"held_ms": 300}, callback=True), {"ok": False, "error": "hold"})
        self.assertEqual(self.c.emit("emergency", {}, callback=True)["ok"], False)
        self.assertNotIn("Damp", self.r.names())

    def test_emergency_cancels_demo_and_follow_and_damps(self):
        self.assertTrue(self.c.emit("demo", {"start": True}, callback=True)["ok"])
        self.c.emit("ai", {"mode": "follow", "on": True}, callback=True)
        res = self.c.emit("emergency", {"held_ms": 1520}, callback=True)
        self.assertEqual(res, {"ok": True, "code": 0})
        self.assertFalse(self.demo.running)
        self.assertFalse(self.follow.enabled)
        motion = [n for n in self.r.names() if not n.startswith("Avoid")]  # avoidance config may finish later
        self.assertEqual(motion[-1], "Damp")

    def test_log_history_sent_on_connect(self):
        self.r.events.add("тест")
        c2 = self.sio.test_client(self.app)
        hist = [e for e in c2.get_received() if e["name"] == "log_history"]
        self.assertTrue(hist and any(x["text"] == "тест" for x in hist[0]["args"][0]))
        c2.disconnect()


if __name__ == "__main__":
    unittest.main()
