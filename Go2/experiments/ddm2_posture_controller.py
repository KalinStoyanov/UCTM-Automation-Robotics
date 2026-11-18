"""Experimental DD-M2 posture controller (v3, intermediate standing state).

Run from the Go2 repository root:
    PYTHONPATH=. python experiments/ddm2_posture_controller.py

This file is version controlled as part of the common Go2/DD-M2 build.

Rotation commands A/D use closed-loop IMU yaw feedback. They are
experimental and must be validated on the physical robot.
LIVE robot commands require supervision and physical pose verification.
"""
import asyncio
import math
import time
from core.communication import go2_webrtc
from unitree_webrtc_connect.constants import RTC_TOPIC

go2_webrtc.LIVE_ENABLED = True


class PostureController:

    def __init__(self):
        self.robot = go2_webrtc.Go2WebRTC()
        self.pose = "UNKNOWN"
        self.yaw = None
        self.yaw_updated = 0.0

    def on_sport_state(self, message):
        try:
            yaw = float(message["data"]["imu_state"]["rpy"][2])
            if math.isfinite(yaw):
                self.yaw = yaw
                self.yaw_updated = time.monotonic()
        except (KeyError, IndexError, TypeError, ValueError):
            pass

    def yaw_fresh(self):
        return (self.yaw is not None and
                time.monotonic() - self.yaw_updated <= 0.5)

    @staticmethod
    def angle_step(previous, current):
        return (current - previous + math.pi) % (2 * math.pi) - math.pi

    @staticmethod
    def api_code(response):
        return response["data"]["header"]["status"]["code"]

    async def send(self, command, target):
        response = await self.robot.send_sport_command(command)
        code = response["data"]["header"]["status"]["code"]

        print(f"{command}: {'PASS' if code == 0 else 'FAIL'} ({code})")

        if code != 0:
            self.pose = "UNKNOWN"
            return False

        self.pose = target
        return True

    async def standing(self):
        if self.pose == "STANDING":
            return True

        if self.pose == "SITTING":
            command = "RiseSit"
        else:
            command = "StandUp"

        return await self.send(command, "STANDING")

    async def move_to(self, target):
        if target == self.pose:
            print("ALREADY IN TARGET POSE")
            return True

        already_standing = self.pose == "STANDING"

        if not await self.standing():
            return False

        if target == "STANDING":
            return True

        if not already_standing:
            answer = await asyncio.to_thread(
                input,
                "Confirm STANDING [Enter=yes, Q=abort]> "
            )

            if answer.strip().upper() != "":
                print("TRANSITION ABORTED")
                return False

        if target == "LYING":
            return await self.send("StandDown", "LYING")

        if target == "SITTING":
            return await self.send("Sit", "SITTING")

        return False

    async def turn_15(self, direction):
        """Feedback-controlled 15-degree yaw; stop on fault or timeout.

        Direction: +1 = left, -1 = right. Requires a fresh IMU yaw
        stream and supervised operation on a clear, level floor.
        """
        if self.pose != "STANDING":
            print("TURN REJECTED: ROBOT MUST BE STANDING")
            return False

        confirmation = await asyncio.to_thread(
            input, "Confirm robot STANDING and area clear [Enter=yes]> "
        )
        if confirmation.strip():
            print("TURN ABORTED")
            return False

        start_wait = time.monotonic()
        while not self.yaw_fresh() and time.monotonic() - start_wait < 3.0:
            await asyncio.sleep(0.05)
        if not self.yaw_fresh():
            print("TURN REJECTED: NO FRESH IMU YAW")
            return False

        # Small rotational velocity; movement is closed-loop on yaw,
        # not estimated by elapsed time.
        yaw_previous = self.yaw
        rotated = 0.0
        target = direction * math.radians(15.0)
        speed = direction * 0.12  # rad/s (approximately 6.88 deg/s)
        deadline = time.monotonic() + 5.0
        result = False
        stop_ok = False

        try:
            while time.monotonic() < deadline:
                if not self.yaw_fresh():
                    raise RuntimeError("IMU yaw stream stale")

                yaw_current = self.yaw
                rotated += self.angle_step(yaw_previous, yaw_current)
                yaw_previous = yaw_current

                if direction * rotated >= math.radians(14.0):
                    result = True
                    break

                response = await asyncio.wait_for(
                    self.robot.send_move(0.0, 0.0, speed),
                    timeout=1.5,
                )
                code = self.api_code(response)
                if code != 0:
                    print(f"TURN MOVE API RESPONSE: {response!r}")
                    raise RuntimeError(f"TURN Move command rejected (code={code})")
                await asyncio.sleep(0.07)

            if not result:
                raise TimeoutError("TURN timeout before target yaw")

        except Exception as exc:
            self.pose = "UNKNOWN"
            print("TURN FAULT:", exc)

        finally:
            # A StopMove request is mandatory, including on failure.
            try:
                response = await asyncio.wait_for(self.robot.stop(), timeout=1.5)
                stop_ok = self.api_code(response) == 0
                print("TURN STOP:", self.api_code(response))
            except Exception as exc:
                print("TURN STOP FAILED:", exc)
            if not stop_ok:
                self.pose = "UNKNOWN"

        print(f"TURN MEASURED: {math.degrees(rotated):+.1f} deg")
        return result and stop_ok

    async def quit(self):
        print("Q: RETURN TO LYING")

        try:
            success = await self.move_to("LYING")

            if success:
                print("LYING COMMAND ACCEPTED")
            else:
                print("WARNING: LYING NOT CONFIRMED")

        except Exception as exc:
            print("POSTURE FAULT:", exc)

    async def run(self):
        try:
            await self.robot.connect()
            print("CONNECTED")
            self.robot.connection.datachannel.pub_sub.subscribe(
                RTC_TOPIC["LF_SPORT_MOD_STATE"], self.on_sport_state
            )
            print("U=Stand L=Lie S=Sit R=RiseSit A=Left15 D=Right15 Q=Lie+Quit")

            while True:
                key = (await asyncio.to_thread(
                    input, "COMMAND> "
                )).strip().upper()

                if key in ("A", "D"):
                    await self.turn_15(+1 if key == "A" else -1)
                    continue

                if key == "Q":
                    await self.quit()
                    break

                targets = {
                    "U": "STANDING",
                    "L": "LYING",
                    "S": "SITTING",
                    "R": "STANDING",
                }

                if key not in targets:
                    print("UNKNOWN COMMAND")
                    continue

                try:
                    success = await self.move_to(targets[key])

                    if not success:
                        print("TRANSITION INCOMPLETE")
                        print("CHECK ROBOT POSE BEFORE CONTINUING")
                        self.pose = "UNKNOWN"

                except Exception as exc:
                    self.pose = "UNKNOWN"
                    print("FAULT:", exc)
                    print("ENDING SESSION")
                    break

        finally:
            if self.robot.connection is not None:
                try:
                    response = await self.robot.stop()
                    code = response["data"]["header"]["status"]["code"]
                    print("FINAL STOP:", code)
                except Exception as exc:
                    print("FINAL STOP FAILED:", exc)

                await self.robot.disconnect()

            print("DISCONNECTED")


if __name__ == "__main__":
    asyncio.run(PostureController().run())
