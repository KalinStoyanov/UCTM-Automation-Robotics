"""Motion timings in seconds: how long the robot needs to finish each command.

One table, shared by the demo sequence (pause after each step), the automatic posture
transitions (wait between inserted steps) and the "trick still running" note on СТОП.
Values are estimates from the Unitree app: tune them on the robot.
"""

ACTION_WAIT = {
    # posture
    "StandUp": 3.0,
    "StandDown": 3.0,
    "RiseSit": 3.0,
    "Sit": 3.0,
    "BalanceStand": 1.0,
    "RecoveryStand": 3.0,
    "Euler": 0.5,
    "Pose": 0.5,
    "BodyHeight": 0.5,
    # tricks (StopMove cannot interrupt these once started)
    "Hello": 4.0,
    "Stretch": 5.0,
    "Content": 4.0,
    "Dance1": 12.0,
    "Dance2": 12.0,
    "Scrape": 5.0,
    "WiggleHips": 6.0,
    "FingerHeart": 4.0,
}

# In-place tricks: once the robot runs one, StopMove does not interrupt it.
TRICKS = ("Hello", "Stretch", "Content", "Dance1", "Dance2", "Scrape", "WiggleHips", "FingerHeart")
