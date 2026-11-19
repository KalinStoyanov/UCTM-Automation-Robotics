"""Unit tests: deadman, speed caps, BalanceStand rule, 10 Hz Move, forbidden actions.

Run: .venv/bin/python -m unittest discover -s controller/tests -v
"""
import asyncio
import threading
import time
import unittest

from controller import robot as R


class FakeRobot(R.BaseRobot):
    """Records every command at the moment it goes on the wire; always 'connected'.
    silent=True: the robot never answers anything (worst case)."""

    def __init__(self, silent=False, posture=R.STANDING, waits=None):
        # zero motion waits by default so timing tests stay fast; posture tests pass their own
        super().__init__(waits={k: 0.0 for k in R.ACTION_WAIT} if waits is None else waits)
        self.posture_state = posture  # as if telemetry had confirmed it
        self.sent = []
        self.silent = silent
        self.codes = {}   # command name -> reply code (default 0)
        self.delays = {}  # command name -> seconds until the reply
        self._sent_lock = threading.Lock()

    async def _open_transport(self):
        pass

    async def _close_transport(self):
        pass

    def _transmit(self, name, param, want_reply):
        with self._sent_lock:
            self.sent.append((time.monotonic(), name, dict(param) if param else None))
        if not want_reply:
            return None
        fut = self._loop.create_future()
        if not self.silent:
            code = self.codes.get(name, 0)
            reply = {"data": {"header": {"status": {"code": code}}}}
            delay = self.delays.get(name, 0)  # e.g. a trick that answers only when it finishes
            if delay:
                self._loop.call_later(delay, lambda: fut.done() or fut.set_result(reply))
            else:
                self._loop.call_soon(fut.set_result, reply)
        return fut

    def names(self):
        with self._sent_lock:
            return [n for _, n, _ in self.sent]

    def clear(self):
        with self._sent_lock:
            self.sent.clear()


class RobotTest(unittest.TestCase):
    def setUp(self):
        self.r = FakeRobot().start()
        self.r.connect().result(timeout=2)
        self.assertEqual(self.r.telemetry()["state"], "connected")

    def tearDown(self):
        self.r.close()

    def hold(self, vx, vy, vyaw, seconds, every=0.05):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.r.set_velocity(vx, vy, vyaw)
            time.sleep(every)


class SpeedCapTest(RobotTest):
    def test_clamp_function(self):
        self.assertEqual(R.clamp_velocity(5, -5, 9), (1.0, -1.0, 1.5))
        self.assertEqual(R.clamp_velocity(-1.01, 0.99, -1.6), (-1.0, 0.99, -1.5))
        self.assertEqual(R.clamp_velocity(float("nan"), float("inf"), "x"), (0.0, 0.0, 0.0))
        self.assertEqual(R.clamp_velocity(None, 0.3, -0.6), (0.0, 0.3, -0.6))

    def test_move_params_are_capped(self):
        self.hold(3.0, -2.0, 7.0, 0.35)
        moves = [p for _, n, p in self.r.sent if n == "Move"]
        self.assertTrue(moves)
        for p in moves:
            self.assertEqual(p, {"x": 1.0, "y": -1.0, "z": 1.5})


class MoveAndDeadmanTest(RobotTest):
    def test_move_rate_is_10hz(self):
        self.hold(0.3, 0, 0, 1.05)
        self.r.set_velocity(0, 0, 0)
        time.sleep(0.1)
        moves = [t for t, n, _ in self.r.sent if n == "Move"]
        self.assertTrue(9 <= len(moves) <= 12, len(moves))
        gaps = [b - a for a, b in zip(moves, moves[1:])]
        self.assertTrue(all(0.08 <= g <= 0.13 for g in gaps), gaps)

    def test_zero_velocity_sends_stopmove_once(self):
        self.hold(0.3, 0, 0, 0.3)
        self.r.set_velocity(0, 0, 0)
        t_zero = time.monotonic()
        for _ in range(5):  # client may repeat zeros; still one StopMove
            self.r.set_velocity(0, 0, 0)
        time.sleep(0.6)
        stops = [t for t, n, _ in self.r.sent if n == "StopMove"]
        self.assertEqual(len(stops), 1)
        self.assertLess(stops[0] - t_zero, 0.05)
        self.assertEqual(self.r.names()[-1], "StopMove")

    def test_deadman_stops_after_300ms(self):
        self.hold(0.3, 0, 0.2, 0.25)
        t_last = self.r._last_vel_time
        time.sleep(1.0)  # client goes silent
        stops = [t for t, n, _ in self.r.sent if n == "StopMove"]
        self.assertEqual(len(stops), 1, self.r.names())
        dt = stops[0] - t_last
        self.assertTrue(R.DEADMAN <= dt <= R.DEADMAN + 0.06, dt)
        # nothing is sent after the deadman StopMove
        self.assertEqual(self.r.names()[-1], "StopMove")
        self.assertFalse(any(n == "Move" and t > stops[0] for t, n, _ in self.r.sent))
        self.assertEqual(self.r.telemetry()["velocity"], {"vx": 0.0, "vy": 0.0, "vyaw": 0.0})

    def test_no_deadman_while_client_keeps_sending(self):
        self.hold(0.3, 0, 0, 1.0, every=0.1)  # 10 Hz client
        self.assertNotIn("StopMove", self.r.names())

    def test_stop_always_sends_stopmove(self):
        self.r.stop().result(timeout=1)
        self.assertEqual(self.r.names(), ["StopMove"])
        self.hold(0.3, 0, 0, 0.2)
        self.r.stop().result(timeout=1)
        time.sleep(0.3)
        self.assertEqual(self.r.names()[-1], "StopMove")
        self.assertEqual(self.r.names().count("StopMove"), 2)


class BalanceStandRuleTest(RobotTest):
    # StandUp / RiseSit only make sense from lying / sitting (when standing they are skipped)
    START = {"StandUp": R.LYING, "RiseSit": R.SITTING}

    def _first_moves(self, action):
        self.r.posture_state = self.START.get(action, R.STANDING)
        self.r.action(action).result(timeout=1)
        self.hold(0.3, 0, 0, 0.25)
        self.r.set_velocity(0, 0, 0)
        time.sleep(0.1)
        return self.r.names()

    def test_standup_then_move_sends_balance_first(self):
        names = self._first_moves("StandUp")
        self.assertEqual(names[:3], ["StandUp", "BalanceStand", "Move"])
        self.assertEqual(names.count("BalanceStand"), 1)

    def test_risesit_then_move_sends_balance_first(self):
        names = self._first_moves("RiseSit")
        self.assertEqual(names[:3], ["RiseSit", "BalanceStand", "Move"])

    def test_balance_only_once(self):
        self._first_moves("StandUp")
        self.r.clear()
        self.hold(0.3, 0, 0, 0.25)
        self.assertNotIn("BalanceStand", self.r.names())

    def test_other_actions_do_not_add_balance(self):
        names = self._first_moves("Hello")
        self.assertEqual(names[:2], ["Hello", "Move"])
        self.assertNotIn("BalanceStand", names)

    def test_explicit_balance_clears_rule(self):
        self.r.posture_state = R.LYING
        self.r.action("StandUp").result(timeout=1)
        self.r.action("BalanceStand").result(timeout=1)
        self.hold(0.3, 0, 0, 0.25)
        self.assertEqual(self.r.names().count("BalanceStand"), 1)

    def test_action_while_moving_stops_first(self):
        self.hold(0.3, 0, 0, 0.25)
        self.r.action("Hello").result(timeout=1)
        time.sleep(0.2)
        names = self.r.names()
        i = names.index("Hello")
        self.assertEqual(names[i - 1], "StopMove")
        self.assertNotIn("Move", names[i:])


class SilentRobotTest(unittest.TestCase):
    """The robot never answers Move (or anything else): the loop must keep 10 Hz."""

    def setUp(self):
        self.r = FakeRobot(silent=True).start()
        self.r.connect().result(timeout=2)

    def tearDown(self):
        self.r.close()

    def hold(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.r.set_velocity(0.3, 0, 0.2)
            time.sleep(0.05)

    def test_move_keeps_10hz_without_replies(self):
        self.hold(2.05)
        moves = [t for t, n, _ in self.r.sent if n == "Move"]
        self.assertTrue(19 <= len(moves) <= 22, len(moves))
        gaps = [b - a for a, b in zip(moves, moves[1:])]
        self.assertTrue(all(0.08 <= g <= 0.13 for g in gaps), gaps)

    def test_unanswered_balance_and_stop_do_not_block_moves(self):
        self.r.posture_state = R.LYING
        f = self.r.action("StandUp")  # its reply never comes
        time.sleep(0.05)
        self.hold(1.05)
        names = self.r.names()
        self.assertEqual(names[:3], ["StandUp", "BalanceStand", "Move"])
        moves = [t for t, n, _ in self.r.sent if n == "Move"]
        self.assertTrue(9 <= len(moves) <= 12, len(moves))  # BalanceStand did not stall the loop
        self.assertEqual(f.result(timeout=2), "timeout")      # awaited command times out (~1 s)
        self.r.set_velocity(0, 0, 0)
        time.sleep(0.05)
        self.assertEqual(self.r.names()[-1], "StopMove")
        self.hold(0.35)  # moving again right after an unanswered StopMove
        self.assertEqual(self.r.names()[-1], "Move")

    def test_awaited_command_times_out_after_about_1s(self):
        t0 = time.monotonic()
        code = self.r.action("Hello").result(timeout=3)
        dt = time.monotonic() - t0
        self.assertEqual(code, "timeout")
        self.assertTrue(0.95 <= dt <= 1.3, dt)


class ActionWhitelistTest(RobotTest):
    def test_dangerous_actions_rejected(self):
        for name in ("Damp", "FrontFlip", "BackFlip", "LeftFlip", "FrontJump", "FrontPounce", "Handstand", "Nope"):
            with self.assertRaises(ValueError, msg=name):
                self.r.action(name)
        time.sleep(0.05)
        self.assertEqual(self.r.names(), [])

    def test_catalog_filters_by_sport_cmd(self):
        names = [a["name"] for a in R.available_actions()]
        self.assertIn("StandUp", names)
        self.assertFalse(set(names) & R.FORBIDDEN)
        self.assertEqual([a["name"] for a in R.available_actions({"Hello": 1, "Damp": 2})], ["Hello"])


if __name__ == "__main__":
    unittest.main()
