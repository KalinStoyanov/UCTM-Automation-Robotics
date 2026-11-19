"""Built-in obstacle avoidance (rt/api/obstacles_avoid/request) and the АВАРИЙНО Damp path.

Run: .venv/bin/python -m unittest discover -s controller/tests -t . -v
"""
import time
import unittest

from controller import robot as R

from controller.tests.test_follow import FakeDetector, person
from controller.tests.test_robot import FakeRobot


class AvoidRobotTest(unittest.TestCase):
    def setUp(self):
        self.r = FakeRobot().start()
        self.r.connect().result(timeout=2)

    def tearDown(self):
        self.r.close()

    def hold(self, vx, vy, vyaw, seconds, every=0.05):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.r.set_velocity(vx, vy, vyaw)
            time.sleep(every)

    def sent(self, name):
        return [p for _, n, p in self.r.sent if n == name]

    def test_api_ids_match_the_library(self):
        self.assertEqual(R.AVOID_CMD, {"AvoidSwitch": 1001, "AvoidGet": 1002, "AvoidMove": 1003, "AvoidRemote": 1004})

    def test_enable_is_confirmed_step_by_step(self):
        self.assertEqual(self.r.set_avoidance(True).result(timeout=3), 0)
        self.assertEqual(self.r.names(), ["AvoidSwitch", "AvoidGet", "AvoidRemote"])
        self.assertEqual(self.sent("AvoidSwitch"), [{"enable": True}])
        self.assertEqual(self.sent("AvoidRemote"), [{"is_remote_commands_from_api": True}])
        st = self.r.telemetry()["avoid"]
        self.assertEqual((st["state"], st["active"], st["code"]), ("on", True, 0))
        self.assertIn("Избягване на препятствия: ВКЛ (роботът потвърди, код 0)", self.r.events.texts())

    def test_moves_go_through_avoidance_at_10hz_and_deadman_still_stops(self):
        self.r.set_avoidance(True).result(timeout=3)
        self.r.clear()
        self.hold(0.3, 0.0, -0.4, 1.0)
        time.sleep(0.6)  # input stops -> deadman
        names = self.r.names()
        self.assertNotIn("Move", names)
        moves = self.sent("AvoidMove")
        nonzero = [m for m in moves if m["x"]]
        self.assertTrue(10 <= len(nonzero) <= 14, len(nonzero))  # 1.0 s of input + 0.3 s deadman
        self.assertEqual(nonzero[0], {"x": 0.3, "y": 0.0, "yaw": -0.4, "mode": 0})
        # deadman: zero to the avoidance service, then StopMove, exactly once
        self.assertEqual(names.count("StopMove"), 1, names)
        i = names.index("StopMove")
        self.assertEqual(names[i - 1], "AvoidMove")
        self.assertEqual(self.r.sent[i - 1][2], R.AVOID_ZERO)
        self.assertTrue(any(t.startswith("Deadman") for t in self.r.events.texts()))

    def test_stop_never_waits_for_avoidance(self):
        self.r.delays = {"AvoidSwitch": 5.0}  # robot slow / silent on the avoidance topic
        self.r.set_avoidance(True)
        time.sleep(0.05)
        self.r.set_velocity(0.3, 0, 0)
        t0 = time.monotonic()
        self.assertEqual(self.r.stop().result(timeout=2), 0)
        self.assertLess(time.monotonic() - t0, 0.3)
        self.assertEqual(self.r.names()[-1], "StopMove")

    def test_stop_with_avoidance_zeroes_it_first(self):
        self.r.set_avoidance(True).result(timeout=3)
        self.hold(0.3, 0, 0, 0.4)
        self.r.clear()
        self.assertEqual(self.r.stop().result(timeout=2), 0)
        self.assertEqual(self.r.names(), ["AvoidMove", "StopMove"])
        self.assertEqual(self.r.sent[0][2], R.AVOID_ZERO)

    def test_rejected_by_firmware_is_red_and_moves_stay_on_sport(self):
        self.r.codes = {"AvoidSwitch": 3203}
        self.assertEqual(self.r.set_avoidance(True).result(timeout=3), 3203)
        self.assertEqual(self.r.names(), ["AvoidSwitch"])  # nothing else is tried
        st = self.r.telemetry()["avoid"]
        self.assertEqual((st["state"], st["active"], st["code"]), ("failed", False, 3203))
        self.assertIn("3203", st["error"])
        ev = [e for e in self.r.events.recent(10) if e["text"].startswith("Избягването не работи")]
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["level"], "danger")
        self.assertIn("код 3203", ev[0]["text"])
        self.r.clear()
        self.hold(0.3, 0, 0, 0.3)
        self.assertIn("Move", self.r.names())
        self.assertNotIn("AvoidMove", self.r.names())

    def test_no_reply_counts_as_failure(self):
        self.r.silent = True
        self.assertEqual(self.r.set_avoidance(True).result(timeout=3), "timeout")
        self.assertEqual(self.r.telemetry()["avoid"]["state"], "failed")

    def test_robot_reporting_disabled_is_a_failure(self):
        self.r.data["AvoidGet"] = {"enable": False}
        self.r.set_avoidance(True).result(timeout=3)
        st = self.r.telemetry()["avoid"]
        self.assertEqual(st["state"], "failed")
        self.assertIn("enable=False", st["error"])
        self.assertNotIn("AvoidRemote", self.r.names())

    def test_refused_api_control_is_a_failure(self):
        self.r.codes = {"AvoidRemote": 3203}
        self.r.set_avoidance(True).result(timeout=3)
        self.assertEqual(self.r.telemetry()["avoid"]["state"], "failed")

    def test_disable_hands_control_back_and_moves_return_to_sport(self):
        self.r.set_avoidance(True).result(timeout=3)
        self.r.clear()
        self.assertEqual(self.r.set_avoidance(False).result(timeout=3), 0)
        self.assertEqual(self.r.names(), ["AvoidMove", "AvoidRemote", "AvoidSwitch"])  # zero first
        self.assertEqual(self.r.sent[0][2], R.AVOID_ZERO)
        self.assertEqual(self.sent("AvoidRemote"), [{"is_remote_commands_from_api": False}])
        self.assertEqual(self.sent("AvoidSwitch"), [{"enable": False}])
        self.assertEqual(self.r.telemetry()["avoid"]["state"], "off")
        self.r.clear()
        self.hold(0.3, 0, 0, 0.3)
        self.assertIn("Move", self.r.names())
        self.assertNotIn("AvoidMove", self.r.names())

    def test_reconnect_switches_it_on_again(self):
        self.r.set_avoidance(True).result(timeout=3)
        self.r.disconnect().result(timeout=3)
        self.assertEqual(self.r.telemetry()["avoid"]["state"], "off")
        self.assertTrue(self.r.telemetry()["avoid"]["want"])
        self.r.clear()
        self.r.connect().result(timeout=2)
        time.sleep(0.2)
        self.assertEqual(self.r.names(), ["AvoidSwitch", "AvoidGet", "AvoidRemote"])
        self.assertEqual(self.r.telemetry()["avoid"]["state"], "on")


class DampTest(unittest.TestCase):
    def setUp(self):
        self.r = FakeRobot().start()
        self.r.connect().result(timeout=2)

    def tearDown(self):
        self.r.close()

    def test_damp_api_id(self):
        self.assertEqual(R.SPORT_CMD["Damp"], 1001)
        self.assertEqual(R.SPORT_CMD_MCF["Damp"], 1001)  # same id in the fw 1.1.12 (MCF) table

    def test_damp_is_sent_at_once_during_a_posture_chain(self):
        self.r.waits["StandUp"] = 5.0  # a chain that would block for 5 s
        r = FakeRobot(posture=R.LYING, waits=dict(self.r.waits)).start()
        try:
            r.connect().result(timeout=2)
            r.action("Hello")  # StandUp -> (5 s settle) -> BalanceStand -> Hello
            time.sleep(0.1)
            t0 = time.monotonic()
            self.assertEqual(r.emergency_damp().result(timeout=2), 0)
            self.assertLess(time.monotonic() - t0, 0.2)
            time.sleep(0.2)
            self.assertEqual(r.names(), ["StandUp", "Damp"])  # the chain is cancelled
        finally:
            r.close()

    def test_damp_while_walking_has_no_stopmove_in_front(self):
        end = time.monotonic() + 0.3
        while time.monotonic() < end:
            self.r.set_velocity(0.3, 0, 0)
            time.sleep(0.05)
        self.r.clear()
        self.r.emergency_damp().result(timeout=2)
        time.sleep(0.5)
        self.assertEqual(self.r.names(), ["Damp"])

    def test_damp_with_avoidance_zeroes_it(self):
        self.r.set_avoidance(True).result(timeout=3)
        self.r.clear()
        self.r.emergency_damp().result(timeout=2)
        self.assertEqual(self.r.names(), ["AvoidMove", "Damp"])

    def test_silent_robot_damp_returns_after_reply_timeout(self):
        self.r.silent = True
        t0 = time.monotonic()
        self.assertEqual(self.r.emergency_damp().result(timeout=3), "timeout")
        self.assertLess(time.monotonic() - t0, R.REPLY_TIMEOUT + 0.3)

    def test_reply_code_is_logged_prominently(self):
        self.r.codes = {"Damp": 3203}
        with self.assertLogs("go2", "WARNING") as cm:
            self.assertEqual(self.r.emergency_damp().result(timeout=2), 3203)
        self.assertTrue(any("EMERGENCY Damp -> code=3203" in m for m in cm.output), cm.output)
        ev = [e for e in self.r.events.recent(10) if e["text"].startswith("АВАРИЙНО Damp")]
        self.assertEqual(ev[-1]["level"], "danger")
        self.assertIn("код 3203", ev[-1]["text"])
        self.assertNotEqual(self.r.posture_state, R.LYING)  # refused: it did not go limp

    def test_after_damp_movement_does_not_stand_it_up(self):
        self.r.emergency_damp().result(timeout=2)
        self.r.clear()
        end = time.monotonic() + 0.5
        while time.monotonic() < end:
            self.r.set_velocity(0.3, 0, 0)
            time.sleep(0.05)
        self.assertEqual(self.r.names(), [])  # no StandUp, no BalanceStand, no Move
        self.assertTrue(self.r.telemetry()["damped"])
        self.assertTrue(any("след аварийно" in t.lower() for t in self.r.events.texts()))
        # an explicit action releases the latch
        self.r.action("StandUp").result(timeout=2)
        self.assertFalse(self.r.telemetry()["damped"])


class AvoidSocketTest(unittest.TestCase):
    """Real Socket.IO handlers: toggle, follow turns avoidance on, follow marked without it."""

    def setUp(self):
        from unittest import mock

        from controller.ai import follow as F
        from controller.app import create_app

        self.F = F
        self.patch = mock.patch.multiple(F, RAISE_HOLD=0.3, STOP_HOLD=0.3, LOST_TIMEOUT=0.8, STOPPED_SHOW=0.5)
        self.patch.start()
        self.r = FakeRobot().start()
        self.r.connect().result(timeout=2)
        self.det = FakeDetector()
        self.app, self.sio = create_app(self.r, detector=self.det, push_telemetry_task=False)
        self.follow = self.app.extensions["go2"]["follow"]
        self.c = self.sio.test_client(self.app)

    def tearDown(self):
        self.follow.disable("toggle")
        self.follow.close()
        if self.c.is_connected():
            self.c.disconnect()
        self.r.close()
        self.patch.stop()

    def test_toggle(self):
        self.assertEqual(self.c.emit("avoid", {"on": True}, callback=True), {"ok": True})
        time.sleep(0.2)
        self.assertEqual(self.r.telemetry()["avoid"]["state"], "on")
        self.c.emit("avoid", {"on": False}, callback=True)
        time.sleep(0.2)
        self.assertEqual(self.r.telemetry()["avoid"]["state"], "off")

    def test_follow_turns_avoidance_on_and_drives_through_it(self):
        from controller.ai.detector import Box

        p = person(0.25, 0.25)
        self.det.set_persons([Box(p.x1, p.y1, p.x2, p.y2, p.name, p.conf, 1)])
        self.c.emit("ai", {"mode": "follow", "on": True}, callback=True)
        time.sleep(self.F.RAISE_HOLD + 0.25)
        self.det.set_persons([p])
        time.sleep(0.4)
        self.assertEqual(self.follow.state()["avoid"], "on")
        names = self.r.names()
        self.assertEqual(names[:3], ["AvoidSwitch", "AvoidGet", "AvoidRemote"])
        self.assertIn("AvoidMove", names)
        self.assertNotIn("Move", names)
        self.assertIn("Следване: вдигната ръка, следвам (с избягване)", self.r.events.texts())

    def test_follow_without_avoidance_is_marked(self):
        from controller.ai.detector import Box

        self.r.codes = {"AvoidSwitch": 3203}
        p = person(0.25, 0.25)
        self.det.set_persons([Box(p.x1, p.y1, p.x2, p.y2, p.name, p.conf, 1)])
        self.c.emit("ai", {"mode": "follow", "on": True}, callback=True)
        time.sleep(self.F.RAISE_HOLD + 0.25)
        self.det.set_persons([p])
        time.sleep(0.4)
        self.assertEqual(self.follow.state()["avoid"], "failed")
        self.assertIn("Следване: следвам БЕЗ избягване на препятствия", self.r.events.texts())
        self.assertIn("Move", self.r.names())  # still follows, on the plain sport Move

    def test_stop_with_avoidance_on(self):
        self.c.emit("avoid", {"on": True}, callback=True)
        time.sleep(0.2)
        self.c.emit("velocity", {"vx": 0.3})
        time.sleep(0.25)
        self.r.clear()
        res = self.c.emit("stop", callback=True)
        self.assertEqual(res, {"ok": True, "code": 0})
        self.assertEqual(self.r.names(), ["AvoidMove", "StopMove"])

    def test_emergency_with_avoidance_on(self):
        self.c.emit("avoid", {"on": True}, callback=True)
        time.sleep(0.2)
        self.r.clear()
        res = self.c.emit("emergency", {"held_ms": 1510}, callback=True)
        self.assertEqual(res, {"ok": True, "code": 0})
        self.assertEqual(self.r.names(), ["AvoidMove", "Damp"])


if __name__ == "__main__":
    unittest.main()
