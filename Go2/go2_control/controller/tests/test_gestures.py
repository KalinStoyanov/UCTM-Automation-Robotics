"""Gesture table: new gestures go through the posture logic; Sit/StandDown gestures end following.

Run: .venv/bin/python -m unittest discover -s controller/tests -t . -v
"""
import time
import unittest
from types import SimpleNamespace

import numpy as np

from controller import robot as R
from controller.ai import gestures as G
from controller.tests.test_follow import FakeDetector, person
from controller.tests.test_robot import FakeRobot


def feed(gm, gesture, frames=G.STREAK + 2):
    """Drive the gesture thread's frame step with a stub recognizer."""
    res = SimpleNamespace(gestures=[[SimpleNamespace(category_name=gesture, score=0.9)]], hand_landmarks=[])
    gm._rec = SimpleNamespace(recognize_for_video=lambda img, ts: res)
    gm._mp = SimpleNamespace(Image=lambda **k: None, ImageFormat=SimpleNamespace(SRGB=1))
    gm._last_sent = 0.0  # no cooldown from earlier gestures
    for i in range(frames):
        gm._process(np.zeros((8, 8, 3), np.uint8), int(time.monotonic() * 1000) + i)


class MappingTableTest(unittest.TestCase):
    def test_table(self):
        self.assertEqual(G.MAPPING["Pointing_Up"], "StandUp")
        self.assertEqual(G.MAPPING["Thumb_Down"], "StandDown")
        self.assertEqual(G.MAPPING["ILoveYou"], "FingerHeart")
        # unchanged entries
        self.assertEqual(G.MAPPING["Thumb_Up"], "Hello")
        self.assertEqual(G.MAPPING["Open_Palm"], "RiseSit")

    def test_only_existing_actions_are_mapped(self):
        r = FakeRobot().start()
        try:
            r.allowed = r.allowed - {"FingerHeart"}  # as if the library lacked it
            gm = G.GestureMode(r)
            self.assertNotIn("ILoveYou", gm.mapping)
            self.assertIn("Pointing_Up", gm.mapping)
        finally:
            r.close()


class GestureThroughPostureTest(unittest.TestCase):
    def run_gesture(self, posture, gesture):
        r = FakeRobot(posture=posture).start()
        r.connect().result(timeout=2)
        try:
            gm = G.GestureMode(r)
            feed(gm, gesture)
            time.sleep(0.3)
            return r.names(), r.posture_state
        finally:
            r.close()

    def test_pointing_up_from_sitting_uses_risesit(self):
        names, posture = self.run_gesture(R.SITTING, "Pointing_Up")
        self.assertEqual(names, ["RiseSit"])
        self.assertEqual(posture, R.STANDING)

    def test_pointing_up_when_standing_is_skipped(self):
        names, _ = self.run_gesture(R.STANDING, "Pointing_Up")
        self.assertEqual(names, [])

    def test_thumb_down_from_sitting(self):
        names, posture = self.run_gesture(R.SITTING, "Thumb_Down")
        self.assertEqual(names, ["RiseSit", "StandDown"])
        self.assertEqual(posture, R.LYING)

    def test_iloveyou_from_lying_stands_up_first(self):
        names, _ = self.run_gesture(R.LYING, "ILoveYou")
        self.assertEqual(names, ["StandUp", "BalanceStand", "FingerHeart"])

    def test_fires_once_per_hold(self):
        names, _ = self.run_gesture(R.STANDING, "ILoveYou")
        self.assertEqual(names.count("FingerHeart"), 1)


class GestureEndsFollowTest(unittest.TestCase):
    def setUp(self):
        from controller.app import create_app

        self.r = FakeRobot().start()
        self.r.connect().result(timeout=2)
        self.det = FakeDetector()
        self.app, self.sio = create_app(self.r, detector=self.det, push_telemetry_task=False)
        ext = self.app.extensions["go2"]
        self.follow, self.gestures = ext["follow"], ext["gestures"]
        self.c = self.sio.test_client(self.app)
        self.det.set_persons([person(0.3, 0.3)])
        self.c.emit("ai", {"mode": "follow", "on": True}, callback=True)
        time.sleep(0.3)

    def tearDown(self):
        self.follow.disable("toggle")
        self.follow.close()
        if self.c.is_connected():
            self.c.disconnect()
        self.r.close()

    def test_thumb_down_while_following(self):
        feed(self.gestures, "Thumb_Down")
        self.assertFalse(self.follow.enabled)
        self.assertEqual(self.follow.last_disable["reason"], "gesture")
        time.sleep(0.3)
        self.assertIn("StandDown", self.r.names())

    def test_closed_fist_while_following(self):
        feed(self.gestures, "Closed_Fist")
        self.assertFalse(self.follow.enabled)

    def test_other_gestures_keep_following(self):
        feed(self.gestures, "ILoveYou")
        self.assertTrue(self.follow.enabled)


if __name__ == "__main__":
    unittest.main()
