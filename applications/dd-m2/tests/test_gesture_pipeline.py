import math
import unittest

from src.gesture_filter import GestureFilter
from src.gesture_pipeline import GesturePipeline


class TestGesturePipeline(unittest.TestCase):

    def test_01_filter_confirmation(self):
        f = GestureFilter(required=3)
        self.assertIsNone(f.update("FORWARD"))
        self.assertIsNone(f.update("FORWARD"))
        self.assertEqual(f.update("FORWARD"), "FORWARD")

    def test_02_immediate_stop(self):
        f = GestureFilter(required=3)
        self.assertEqual(f.update("STOP"), "STOP")

    def test_03_unknown_resets_filter(self):
        f = GestureFilter(required=3)
        f.update("FORWARD")
        f.update("FORWARD")
        self.assertIsNone(f.update("UNKNOWN"))
        self.assertIsNone(f.update("FORWARD"))

    def test_04_missing_detection(self):
        f = GestureFilter(required=3)
        f.update("FORWARD")
        f.update(None)
        self.assertIsNone(f.update("FORWARD"))

    def test_05_forward_motion(self):
        p = GesturePipeline()
        for _ in range(10):
            p.detect("FORWARD")
            p.step(0.1)

        self.assertAlmostEqual(
            p.controller.robot.x, 0.16, places=8
        )

    def test_06_timeout(self):
        p = GesturePipeline()
        for _ in range(3):
            p.detect("FORWARD")
            p.step(0.1)

        p.step(1.0)

        self.assertTrue(p.controller.timed_out)
        self.assertEqual(p.controller.robot.v, 0)

    def test_07_stop_interrupts(self):
        p = GesturePipeline()
        for _ in range(3):
            p.detect("FORWARD")
            p.step(0.1)

        p.detect("STOP")
        self.assertEqual(p.controller.robot.v, 0)

    def test_08_single_rotation(self):
        p = GesturePipeline()
        for _ in range(40):
            p.detect("TURN_LEFT_90")
            p.step(0.1)

        self.assertAlmostEqual(
            p.controller.robot.status()["heading_deg"],
            90.0,
            places=6
        )

    def test_09_rotation_after_stop(self):
        p = GesturePipeline()

        for _ in range(40):
            p.detect("TURN_LEFT_90")
            p.step(0.1)

        p.detect("STOP")

        for _ in range(40):
            p.detect("TURN_LEFT_90")
            p.step(0.1)

        self.assertAlmostEqual(
            p.controller.robot.status()["heading_deg"],
            180.0,
            places=6
        )

    def test_10_speed_units(self):
        p = GesturePipeline()
        for _ in range(3):
            p.detect("FORWARD")
            p.step(0.1)

        s = p.status()

        self.assertAlmostEqual(
            s["linear_km_h"],
            s["linear_m_s"] * 3.6
        )

        self.assertAlmostEqual(
            s["angular_deg_s"],
            math.degrees(s["angular_rad_s"]),
            places=2
        )

    def test_11_no_detection_from_start(self):
        p = GesturePipeline()
        p.step(1.0)

        self.assertTrue(p.controller.timed_out)
        self.assertEqual(p.controller.robot.v, 0)

    def test_12_invalid_dt(self):
        p = GesturePipeline()

        with self.assertRaises(ValueError):
            p.step(-1.0)

    def test_13_timeout_requires_reconfirmation(self):
        p = GesturePipeline()

        for _ in range(3):
            p.detect("FORWARD")
            p.step(0.1)

        p.step(1.0)
        x = p.controller.robot.x

        p.detect("FORWARD")
        p.step(0.1)

        self.assertAlmostEqual(
            p.controller.robot.x, x
        )

        p.detect("FORWARD")
        p.step(0.1)

        self.assertAlmostEqual(
            p.controller.robot.x, x
        )

        p.detect("FORWARD")
        p.step(0.1)

        self.assertGreater(p.controller.robot.x, x)

    def test_14_unknown_does_not_refresh_timeout(self):
        p = GesturePipeline()

        for _ in range(3):
            p.detect("FORWARD")
            p.step(0.1)

        for _ in range(10):
            p.detect("UNKNOWN")
            p.step(0.1)

        self.assertTrue(p.controller.timed_out)
        self.assertEqual(p.controller.robot.v, 0)

    def test_15_invalid_filter_parameter(self):
        with self.assertRaises(ValueError):
            GestureFilter(required=0)


if __name__ == "__main__":
    unittest.main()
