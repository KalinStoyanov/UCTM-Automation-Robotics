"""Трикове: catalog, safety list, timings, posture, icons.

Run: .venv/bin/python -m unittest discover -s controller/tests -t . -v
"""
import re
import unittest
from pathlib import Path

from unitree_webrtc_connect.constants import SPORT_CMD

from controller import robot as R
from controller import timing as T
from controller.tests.test_robot import FakeRobot

ROOT = Path(__file__).resolve().parents[2]
TRICKS = ["Hello", "Stretch", "Dance1", "Dance2", "Content", "Scrape", "FingerHeart"]
NEVER = ["Damp", "FrontFlip", "BackFlip", "LeftFlip", "RightFlip", "FrontJump", "FrontPounce",
         "Handstand", "Bound", "MoonWalk", "StandOut", "Wallow"]


class TrickCatalogTest(unittest.TestCase):
    def test_tricks_group(self):
        acts = R.available_actions()
        self.assertEqual([a["name"] for a in acts if a["group"] == "tricks"], TRICKS)
        self.assertEqual([a["name"] for a in acts if a["group"] == "posture"],
                         ["StandUp", "StandDown", "BalanceStand", "RecoveryStand", "Sit", "RiseSit"])
        for a in acts:
            self.assertTrue(a["label"] and not a["label"].isascii(), a)  # Bulgarian label

    def test_every_trick_exists_in_library(self):
        for n in TRICKS:
            self.assertIn(n, SPORT_CMD)

    def test_dangerous_never_exposed_or_accepted(self):
        names = {a["name"] for a in R.available_actions()}
        r = FakeRobot().start()
        try:
            for n in NEVER:
                self.assertNotIn(n, names)
                with self.assertRaises(ValueError):
                    r.action(n)
        finally:
            r.close()

    def test_tricks_have_timings_and_need_standing(self):
        for n in TRICKS:
            self.assertIn(n, T.TRICKS)
            self.assertGreater(T.ACTION_WAIT[n], 0)
            self.assertIn(n, R.NEEDS_STANDING)
            self.assertEqual([c for c, _ in R.plan_steps(n, R.LYING)], ["StandUp", "BalanceStand", n])

    def test_icons_exist_in_sprite(self):
        html = (ROOT / "controller" / "static" / "index.html").read_text()
        for a in R.available_actions():
            self.assertIn(f'id="i-{a["icon"]}"', html, a)

    @unittest.skipUnless((ROOT / "ref" / "z4rtc" / "z4rtc.py").exists(), "z4rtc reference not cloned")
    def test_api_ids_match_z4rtc(self):
        src = (ROOT / "ref" / "z4rtc" / "z4rtc.py").read_text()
        ids = {int(m.group(1)) for m in re.finditer(r'"rt/api/sport/request",\s+(\d+), None', src)}
        for n in TRICKS:
            self.assertIn(SPORT_CMD[n], ids, n)  # same api_id, no parameters

    def test_trick_from_sitting_through_robot(self):
        r = FakeRobot(posture=R.SITTING).start()
        r.connect().result(timeout=2)
        try:
            self.assertEqual(r.action("FingerHeart").result(timeout=3), 0)
            self.assertEqual(r.names(), ["RiseSit", "BalanceStand", "FingerHeart"])
        finally:
            r.close()

    def test_wigglehips_removed_rejected_by_firmware(self):
        # robot log 2026-11-19: WiggleHips -> code 3203 x6, never moved; not in SPORT_CMD_MCF
        self.assertFalse(R.fw_supported("WiggleHips"))
        self.assertNotIn("WiggleHips", [a["name"] for a in R.available_actions()])
        r = FakeRobot().start()
        try:
            with self.assertRaises(ValueError):
                r.action("WiggleHips")
        finally:
            r.close()

    def test_everything_that_worked_on_the_robot_is_still_offered(self):
        worked = ["StandUp", "StandDown", "BalanceStand", "RecoveryStand", "Sit", "RiseSit",
                  "Hello", "Stretch", "Content", "Scrape", "FingerHeart", "Dance1", "Dance2"]
        offered = [a["name"] for a in R.available_actions()]
        for n in worked:
            self.assertIn(n, offered)
            self.assertTrue(R.fw_supported(n), n)


if __name__ == "__main__":
    unittest.main()
