"""Experimental DD-M2 posture controller (v3, intermediate standing state).

Run from the Go2 repository root:
    PYTHONPATH=. python experiments/ddm2_posture_controller.py

This file is version controlled as part of the common Go2/DD-M2 build.

Rotation commands A/D use closed-loop IMU yaw feedback. They are
experimental and must be validated on the physical robot.
LIVE robot commands require supervision and physical pose verification.
"""
import asyncio
import json
import math
import time
from datetime import datetime
from pathlib import Path
from core.communication import go2_webrtc
from unitree_webrtc_connect.constants import RTC_TOPIC

go2_webrtc.LIVE_ENABLED = True


class PostureController:

    def __init__(self):
        self.robot = go2_webrtc.Go2WebRTC()
        self.pose = "UNKNOWN"
        self.yaw = None
        self.yaw_updated = 0.0
        self.turn_samples = None

    def on_sport_state(self, message):
        try:
            yaw = float(message["data"]["imu_state"]["rpy"][2])
            if math.isfinite(yaw):
                self.yaw = yaw
                self.yaw_updated = time.monotonic()
                if self.turn_samples is not None:
                    self.turn_samples.append((self.yaw_updated, yaw))
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

    def yaw_snapshot(self, origin, reference=None):
        now = time.monotonic()
        fresh = self.yaw_fresh()
        value = self.yaw if fresh else None
        degrees = math.degrees(value) if value is not None else None
        delta = (math.degrees(self.angle_step(reference, value))
                 if value is not None and reference is not None else None)
        return {
            "t_s": round(now - origin, 4),
            "yaw_deg": round(degrees, 4) if degrees is not None else None,
            "delta_deg": round(delta, 4) if delta is not None else None,
            "yaw_age_s": round(now - self.yaw_updated, 4),
            "fresh": fresh,
        }

    async def turn_15(self, direction):
        """Feedback-controlled turn with IMU telemetry at command/STOP boundaries."""
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

        origin = time.monotonic()
        yaw_initial = self.yaw
        yaw_previous = yaw_initial
        rotated = 0.0
        speed = direction * 0.12
        deadline = origin + 5.0
        result = False
        stop_ok = False
        observations = []
        events = []
        self.turn_samples = []

        def snapshot(stage, **fields):
            state = self.yaw_snapshot(origin, yaw_initial)
            record = {"stage": stage, **state, **fields}
            observations.append(record)
            print("TURN IMU:", json.dumps(record, ensure_ascii=False))
            return record

        snapshot("BEFORE_MOVE", commanded_wz_rad_s=speed)
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

                snapshot("MOVE_SEND")
                sent_at = time.monotonic()
                response = await asyncio.wait_for(
                    self.robot.send_move(0.0, 0.0, speed),
                    timeout=1.5,
                )
                code = self.api_code(response)
                snapshot("MOVE_RESPONSE", code=code,
                         request_duration_s=round(time.monotonic() - sent_at, 4))
                if code != 0:
                    print(f"TURN MOVE API RESPONSE: {response!r}")
                    raise RuntimeError(f"TURN Move command rejected (code={code})")
                await asyncio.sleep(0.07)

            if not result:
                raise TimeoutError("TURN timeout before target yaw")

        except Exception as exc:
            self.pose = "UNKNOWN"
            events.append(repr(exc))
            print("TURN FAULT:", exc)

        finally:
            snapshot("BEFORE_STOP")
            try:
                response = await asyncio.wait_for(self.robot.stop(), timeout=1.5)
                stop_ok = self.api_code(response) == 0
                snapshot("STOP_RESPONSE", code=self.api_code(response))
                print("TURN STOP:", self.api_code(response))
            except Exception as exc:
                self.pose = "UNKNOWN"
                events.append("STOP: " + repr(exc))
                print("TURN STOP FAILED:", exc)
            if not stop_ok:
                self.pose = "UNKNOWN"

            # Observe residual movement AFTER sending STOP; do not command motion.
            await asyncio.sleep(0.30)
            snapshot("AFTER_STOP_300MS")
            samples = self.turn_samples or []
            self.turn_samples = None
            directory = Path("results")
            directory.mkdir(exist_ok=True)
            log_file = directory / "ddm2_turn_diagnostics.jsonl"
            log_record = {
                "timestamp": datetime.now().isoformat(timespec="milliseconds"),
                "direction": "LEFT" if direction > 0 else "RIGHT",
                "target_deg": 15 * direction,
                "observations": observations,
                "imu_samples": [
                    {"t_s": round(t - origin, 4),
                     "yaw_deg": round(math.degrees(yaw), 4)}
                    for t, yaw in samples
                ],
                "errors": events,
                "stop_ok": stop_ok,
            }
            try:
                with log_file.open("a", encoding="utf-8") as file:
                    file.write(json.dumps(log_record, ensure_ascii=False) + "\n")
                print("TURN LOG:", log_file)
            except OSError as exc:
                print("TURN LOG ERROR:", exc)

        print(f"TURN CONTROL LOOP: {math.degrees(rotated):+.2f} deg")
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
