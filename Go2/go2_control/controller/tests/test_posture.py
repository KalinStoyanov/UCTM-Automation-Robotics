"""Automatic posture transitions: planner, chains with waits, СТОП, errors, telemetry.

Run: .venv/bin/python -m unittest discover -s controller/tests -t . -v
"""
import time
import unittest

from controller import robot as R
from controller.demo import DemoSequence
from controller.robot import LYING, SITTING, STANDING, UNKNOWN, plan_steps
from controller.tests.test_robot import FakeRobot

WAITS = {k: 0.0 for k in R.ACTION_WAIT}
WAITS.update({"StandUp": 0.3, "RiseSit": 0.3, "BalanceStand": 0.2, "StandDown": 0.2, "Sit": 0.2})


def cmds(steps):
    return [c for c, _ in steps]


class PlannerTest(unittest.TestCase):
    def test_needs_standing_from_lying_and_sitting(self):
        for name in ("Hello", "Stretch", "Dance1", "Euler", "BodyHeight"):
            self.assertEqual(plan_steps(name, LYING), [("StandUp", True), ("BalanceStand", True), (name, False)])
            self.assertEqual(plan_steps(name, SITTING), [("RiseSit", True), ("BalanceStand", True), (name, False)])
            self.assertEqual(plan_steps(name, STANDING), [(name, False)])

    def test_locked_stand_gets_balance(self):  # after an explicit StandUp
        self.assertEqual(plan_steps("Hello", STANDING, balanced=False), [("BalanceStand", True), ("Hello", False)])

    def test_move(self):
        self.assertEqual(cmds(plan_steps("Move", LYING)), ["StandUp", "BalanceStand"])
        self.assertEqual(cmds(plan_steps("Move", SITTING)), ["RiseSit", "BalanceStand"])
        self.assertEqual(plan_steps("Move", STANDING, balanced=False), [("BalanceStand", True)])
        self.assertEqual(plan_steps("Move", STANDING), [])

    def test_sit(self):
        self.assertEqual(cmds(plan_steps("Sit", LYING)), ["StandUp", "BalanceStand", "Sit"])
        self.assertEqual(plan_steps("Sit", SITTING), [])

    def test_standdown(self):
        self.assertEqual(plan_steps("StandDown", SITTING), [("RiseSit", True), ("StandDown", False)])
        self.assertEqual(plan_steps("StandDown", STANDING), [("StandDown", False)])
        self.assertEqual(plan_steps("StandDown", LYING), [])

    def test_standup_risesit(self):
        for name in ("StandUp", "RiseSit"):
            self.assertEqual(plan_steps(name, STANDING), [])  # skip
        self.assertEqual(plan_steps("StandUp", SITTING), [("RiseSit", True)])  # substitute
        self.assertEqual(plan_steps("RiseSit", LYING), [("StandUp", True)])
        self.assertEqual(plan_steps("StandUp", LYING), [("StandUp", False)])

    def test_balance_stand(self):
        self.assertEqual(cmds(plan_steps("BalanceStand", LYING)), ["StandUp", "BalanceStand"])
        self.assertEqual(cmds(plan_steps("BalanceStand", SITTING)), ["RiseSit", "BalanceStand"])

    def test_unknown_normalizes_through_standup(self):
        self.assertEqual(cmds(plan_steps("Hello", UNKNOWN)), ["StandUp", "BalanceStand", "Hello"])
        self.assertEqual(cmds(plan_steps("StandUp", UNKNOWN)), ["StandUp"])

    def test_recovery_stand_has_no_precondition(self):
        self.assertEqual(plan_steps("RecoveryStand", LYING), [("RecoveryStand", False)])


class ChainTest(unittest.TestCase):
    def make(self, posture, silent=False):
        self.r = FakeRobot(silent=silent, posture=posture, waits=WAITS).start()
        self.r.connect().result(timeout=2)
        return self.r

    def tearDown(self):
        self.r.close()

    def times(self):
        return {n: t for t, n, _ in reversed(self.r.sent)}  # first occurrence

    def test_hello_from_lying_inserts_steps_with_waits(self):
        r = self.make(LYING)
        self.assertEqual(r.action("Hello").result(timeout=5), 0)
        self.assertEqual(r.names(), ["StandUp", "BalanceStand", "Hello"])
        t = self.times()
        self.assertGreaterEqual(t["BalanceStand"] - t["StandUp"], 0.29)
        self.assertGreaterEqual(t["Hello"] - t["BalanceStand"], 0.19)
        self.assertEqual(r.posture_state, STANDING)
        self.assertIn("Авто: Стани → Баланс преди Здрасти", r.events.texts())
        self.assertEqual(r.telemetry()["posture_label"], "Стои")

    def test_hello_from_sitting(self):
        r = self.make(SITTING)
        r.action("Hello").result(timeout=5)
        self.assertEqual(r.names(), ["RiseSit", "BalanceStand", "Hello"])

    def test_standdown_from_sitting(self):
        r = self.make(SITTING)
        r.action("StandDown").result(timeout=5)
        self.assertEqual(r.names(), ["RiseSit", "StandDown"])
        self.assertEqual(r.posture_state, LYING)

    def test_standup_when_standing_is_skipped(self):
        r = self.make(STANDING)
        self.assertEqual(r.action("StandUp").result(timeout=2), 0)
        self.assertEqual(r.names(), [])
        self.assertTrue(any("пропуснато" in t for t in r.events.texts()))

    def test_standup_from_sitting_becomes_risesit(self):
        r = self.make(SITTING)
        r.action("StandUp").result(timeout=2)
        self.assertEqual(r.names(), ["RiseSit"])
        self.assertTrue(any("вместо Стани" in t for t in r.events.texts()), r.events.texts())

    def test_move_from_lying_stands_up_first_and_holds_moves(self):
        r = self.make(LYING)
        end = time.monotonic() + 1.2
        while time.monotonic() < end:
            r.set_velocity(0.3, 0, 0)
            time.sleep(0.05)
        names = r.names()
        self.assertEqual(names[:3], ["StandUp", "BalanceStand", "Move"])
        t = self.times()
        # no Move before StandUp + BalanceStand motions are done
        self.assertGreaterEqual(t["Move"] - t["StandUp"], 0.49)
        self.assertIn("Авто: Стани → Баланс преди движение", r.events.texts())

    def test_stop_cancels_pending_chain(self):
        r = self.make(LYING)
        r.waits["StandUp"] = 0.6
        f = r.action("Hello")
        time.sleep(0.15)  # StandUp sent, waiting for the motion
        r.stop().result(timeout=2)
        self.assertEqual(f.result(timeout=2), "cancelled")
        time.sleep(0.8)
        self.assertEqual(r.names(), ["StandUp", "StopMove"])
        self.assertIn("Авто-веригата е отменена", r.events.texts())
        self.assertFalse(r.telemetry()["chain"])

    def test_stop_cancels_move_chain(self):
        r = self.make(LYING)
        r.waits["StandUp"] = 0.6
        r.set_velocity(0.3, 0, 0)
        time.sleep(0.15)
        r.stop().result(timeout=2)
        time.sleep(0.8)
        self.assertNotIn("BalanceStand", r.names())
        self.assertNotIn("Move", r.names())

    def test_refused_step_aborts_chain_and_keeps_posture(self):
        r = self.make(LYING)
        r.codes["StandUp"] = 3104
        code = r.action("Hello").result(timeout=5)
        self.assertEqual(code, 3104)
        self.assertNotIn("Hello", r.names())
        self.assertEqual(r.posture_state, LYING)
        self.assertTrue(any(t.startswith("Авто-веригата спря") for t in r.events.texts()))

    def test_refused_final_command_reverts_posture(self):
        r = self.make(STANDING)
        r.codes["Sit"] = 3104
        r.action("Sit").result(timeout=2)
        self.assertEqual(r.posture_state, STANDING)

    def test_unanswered_steps_do_not_block_but_still_wait(self):
        r = self.make(LYING, silent=True)
        t0 = time.monotonic()
        code = r.action("Hello").result(timeout=5)
        self.assertEqual(code, "timeout")  # only the final command is awaited
        self.assertEqual(r.names(), ["StandUp", "BalanceStand", "Hello"])
        self.assertLess(time.monotonic() - t0, 0.5 + 1.3)  # waits + one 1 s reply timeout

    def test_new_action_replaces_preparing_chain(self):
        r = self.make(LYING)
        r.waits["StandUp"] = 0.5
        f1 = r.action("Hello")
        time.sleep(0.1)
        f2 = r.action("Stretch")
        self.assertEqual(f1.result(timeout=3), "cancelled")
        self.assertEqual(f2.result(timeout=3), 0)
        # StandUp was already sent; the new plan continues from the inferred posture
        self.assertEqual(r.names(), ["StandUp", "BalanceStand", "Stretch"])


class TelemetryPostureTest(unittest.TestCase):
    def setUp(self):
        self.r = FakeRobot(posture=UNKNOWN, waits=WAITS).start()
        self.r.connect().result(timeout=2)

    def tearDown(self):
        self.r.close()

    def on_mode(self, m):
        self.r._submit(self._call(m)).result(timeout=1)

    async def _call(self, m):
        self.r._on_mode(m)

    def test_clear_modes_set_posture(self):
        self.on_mode(10)
        self.assertEqual(self.r.posture_state, SITTING)
        self.on_mode(5)
        self.assertEqual(self.r.posture_state, LYING)
        self.on_mode(1)
        self.assertEqual(self.r.posture_state, STANDING)
        self.assertFalse(self.r._needs_balance)

    def test_unclear_modes_ignored(self):
        for m in (0, 2, 6, 7, 8, None):
            self.on_mode(m)
        self.assertEqual(self.r.posture_state, UNKNOWN)

    def test_ignored_right_after_a_posture_command(self):
        self.r.posture_state = LYING
        self.r.action("StandUp").result(timeout=2)
        self.on_mode(5)  # robot still reports lying while it stands up
        self.assertEqual(self.r.posture_state, STANDING)


class DemoWithPostureTest(unittest.TestCase):
    def test_demo_from_lying_stands_up_first(self):
        r = FakeRobot(posture=LYING, waits=WAITS).start()
        r.connect().result(timeout=2)
        try:
            d = DemoSequence(r, [("Hello", 0.1), ("Sit", 0.1), ("RiseSit", 0.1)])
            d.start()
            d.join(10)
            self.assertEqual(r.names(), ["StandUp", "BalanceStand", "Hello", "Sit", "RiseSit"])
            self.assertNotIn("Move", r.names())
            self.assertEqual(d.state()["phase"], "done")
        finally:
            r.close()


if __name__ == "__main__":
    unittest.main()
