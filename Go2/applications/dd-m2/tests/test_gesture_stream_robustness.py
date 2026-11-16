import unittest

from src.gesture_stream_robustness import (
    simulate_intervals,
    random_intervals,
    simulate_dropout,
    simulate_recovery,
)


class TestGestureStreamRobustness(unittest.TestCase):

    def test_01_variable_fps_10(self):
        p, _ = simulate_intervals([0.1] * 30)
        self.assertGreater(p.controller.robot.x, 0)

    def test_02_variable_fps_15(self):
        p, _ = simulate_intervals([1/15] * 30)
        self.assertGreater(p.controller.robot.x, 0)

    def test_03_variable_fps_30(self):
        p, _ = simulate_intervals([1/30] * 30)
        self.assertGreater(p.controller.robot.x, 0)

    def test_04_random_intervals(self):
        intervals = random_intervals()
        p, _ = simulate_intervals(intervals)
        self.assertGreater(p.controller.robot.x, 0)

    def test_05_reproducibility(self):
        self.assertEqual(
            random_intervals(seed=42),
            random_intervals(seed=42)
        )

    def test_06_short_dropout(self):
        r = simulate_dropout(0.2)
        self.assertFalse(r["timed_out"])

    def test_07_dropout_boundary(self):
        r = simulate_dropout(0.5)
        self.assertTrue(r["timed_out"])

    def test_08_long_dropout(self):
        r = simulate_dropout(1.0)
        self.assertTrue(r["timed_out"])

    def test_09_long_dropout_stops(self):
        r = simulate_dropout(1.0)
        self.assertEqual(
            r["status"]["linear_m_s"], 0
        )

    def test_10_no_backward_motion(self):
        r = simulate_dropout(1.0)
        self.assertGreaterEqual(
            r["x_after_m"],
            r["x_before_m"]
        )

    def test_11_recovery(self):
        r = simulate_recovery()
        self.assertTrue(r["resumed"])

    def test_12_recovery_requires_three(self):
        r = simulate_recovery()
        x = r["x_stopped"]
        self.assertAlmostEqual(r["positions"][0], x)
        self.assertAlmostEqual(r["positions"][1], x)
        self.assertGreater(r["positions"][2], x)

    def test_13_invalid_fps(self):
        with self.assertRaises(ValueError):
            random_intervals(min_fps=0)

    def test_14_invalid_dropout(self):
        with self.assertRaises(ValueError):
            simulate_dropout(-1)

    def test_15_speed_units(self):
        r = simulate_recovery()
        s = r["status"]
        self.assertAlmostEqual(
            s["linear_km_h"],
            s["linear_m_s"] * 3.6
        )


if __name__ == "__main__":
    unittest.main()
