"""СТОП: full path through the real Socket.IO handler, operator log, trick note.

Run: .venv/bin/python -m unittest discover -s controller/tests -t . -v
"""
import time
import unittest

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

    def test_stop_while_trick_running_notes_it(self):
        self.r.waits["Hello"] = 5.0
        self.r.action("Hello").result(timeout=2)
        self.r.stop().result(timeout=2)
        notes = [t for t in self.r.events.texts() if "не може да прекъсне" in t]
        self.assertEqual(len(notes), 1, self.r.events.texts())
        self.assertIn("Здрасти", notes[0])

    def test_no_trick_note_when_trick_finished(self):
        self.r.waits["Hello"] = 0.1
        self.r.action("Hello").result(timeout=2)
        time.sleep(0.2)
        self.r.stop().result(timeout=2)
        self.assertFalse(any("не може да прекъсне" in t for t in self.r.events.texts()))

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

    def test_log_history_sent_on_connect(self):
        self.r.events.add("тест")
        c2 = self.sio.test_client(self.app)
        hist = [e for e in c2.get_received() if e["name"] == "log_history"]
        self.assertTrue(hist and any(x["text"] == "тест" for x in hist[0]["args"][0]))
        c2.disconnect()


if __name__ == "__main__":
    unittest.main()
