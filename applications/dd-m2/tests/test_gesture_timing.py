import unittest

from src.gesture_timing import (
    run_stream,
    measure_timeout,
)


class TestGestureTiming(unittest.TestCase):

    def test_01_fps_10(self):
        r = run_stream(10)
        self.assertIsNotNone(r["confirmation_s"])

    def test_02_fps_15(self):
        r = run_stream(15)
        self.assertIsNotNone(r["confirmation_s"])

    def test_03_fps_30(self):
        r = run_stream(30)
        self.assertIsNotNone(r["confirmation_s"])

    def test_04_confirmation_10fps(self):
        r = run_stream(10)
        self.assertAlmostEqual(
            r["confirmation_s"], 0.2, places=6
        )

    def test_05_confirmation_30fps(self):
        r = run_stream(30)
        self.assertAlmostEqual(
            r["confirmation_s"], 2 / 30, places=6
        )

    def test_06_higher_fps_faster(self):
        a = run_stream(10)
        b = run_stream(30)
        self.assertLess(
            b["confirmation_s"],
            a["confirmation_s"]
        )

    def test_07_dropped_frames(self):
        r = run_stream(
            30, drop_frames={1, 5, 9}
        )
        self.assertIsNotNone(r["confirmation_s"])

    def test_08_all_frames_missing(self):
        r = run_stream(
            10, drop_frames=set(range(20))
        )
        self.assertAlmostEqual(
            r["distance_m"], 0.0
        )

    def test_09_timeout_10fps(self):
        r = measure_timeout(10)
        self.assertTrue(r["stopped"])

    def test_10_timeout_15fps(self):
        r = measure_timeout(15)
        self.assertTrue(r["stopped"])

    def test_11_timeout_30fps(self):
        r = measure_timeout(30)
        self.assertTrue(r["stopped"])

    def test_12_timeout_accuracy(self):
        for fps in (10, 15, 30):
            r = measure_timeout(fps)
            self.assertTrue(r["stopped"])
            self.assertGreaterEqual(
                r["observed_timeout_s"] + 1e-9,
                0.5
            )
            self.assertLess(
                r["observation_delay_s"],
                1 / fps + 1e-9
            )

    def test_13_invalid_fps(self):
        with self.assertRaises(ValueError):
            run_stream(0)

    def test_14_invalid_duration(self):
        with self.assertRaises(ValueError):
            run_stream(30, duration=-1)

    def test_15_speed_units(self):
        r = run_stream(30)
        s = r["status"]
        self.assertAlmostEqual(
            s["linear_km_h"],
            s["linear_m_s"] * 3.6
        )


if __name__ == "__main__":
    unittest.main()
