"""DD-M2 posture controller with per-command JSONL diagnostic logging.

Run from the Go2 repository root:
    PYTHONPATH=. python -u experiments/ddm2_posture_logged.py

Logs are written to results/ddm2_posture_<timestamp>.jsonl.
Experimental LIVE controller; does not modify core/control/remote_control.py.
"""
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from core.communication import go2_webrtc

go2_webrtc.LIVE_ENABLED = True

OUT = Path("results")
OUT.mkdir(exist_ok=True)

SESSION = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG = OUT / f"ddm2_posture_{SESSION}.jsonl"

COMMANDS = {
    "U": "STANDING",
    "L": "LYING",
    "S": "SITTING",
    "R": "STANDING",
}


class Controller:
    def __init__(self):
        self.robot = go2_webrtc.Go2WebRTC()
        self.pose = "UNKNOWN"
        self.step = 0
        self.active = False

    def log(self, event, **data):
        record = {
            "time": datetime.now().isoformat(timespec="milliseconds"),
            "monotonic": time.monotonic(),
            "session": SESSION,
            "step": self.step,
            "event": event,
            "pose": self.pose,
            **data,
        }
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    async def send(self, command, target):
        self.step += 1
        before = self.pose

        self.log(
            "COMMAND_SENT",
            command=command,
            from_pose=before,
            target_pose=target,
        )

        start = time.monotonic()

        try:
            response = await self.robot.send_sport_command(command)
            duration = time.monotonic() - start
            code = response["data"]["header"]["status"]["code"]

            self.log(
                "API_RESPONSE",
                command=command,
                code=code,
                duration_s=round(duration, 4),
                response=response,
            )

            print(f"{command}: {'PASS' if code == 0 else 'FAIL'} ({code})")

            if code != 0:
                self.pose = "UNKNOWN"
                return False

            observation = await asyncio.to_thread(
                input,
                "REACTION [Enter=correct, text=problem]> ",
            )

            self.log(
                "PHYSICAL_OBSERVATION",
                command=command,
                observation=observation or "CORRECT",
            )

            if observation.strip():
                print("OBSERVATION RECORDED - TRANSITION STOPPED")
                self.pose = "UNKNOWN"
                return False

            self.pose = target
            self.log("POSE_CONFIRMED", pose_confirmed=target)
            return True

        except Exception as exc:
            self.pose = "UNKNOWN"
            self.log(
                "COMMAND_FAULT",
                command=command,
                error=repr(exc),
            )
            print("FAULT:", exc)
            return False

    async def standing(self):
        if self.pose == "STANDING":
            self.log("STANDING_ALREADY_CONFIRMED")
            return True

        command = "RiseSit" if self.pose == "SITTING" else "StandUp"
        return await self.send(command, "STANDING")

    async def move_to(self, target):
        self.log("TARGET_REQUESTED", target=target)

        if self.pose == target:
            print("ALREADY IN TARGET POSE")
            self.log("TARGET_ALREADY_REACHED", target=target)
            return True

        if not await self.standing():
            return False

        if target == "STANDING":
            return True

        command = {
            "LYING": "StandDown",
            "SITTING": "Sit",
        }[target]

        return await self.send(command, target)

    async def shutdown(self):
        self.log("SHUTDOWN_STARTED")

        if self.active:
            try:
                response = await self.robot.stop()
                code = response["data"]["header"]["status"]["code"]
                self.log("FINAL_STOP", code=code, response=response)
                print("FINAL STOP:", code)
            except Exception as exc:
                self.log("FINAL_STOP_FAULT", error=repr(exc))
                print("FINAL STOP FAILED:", exc)

        if self.robot.connection is not None:
            try:
                await self.robot.disconnect()
                self.log("DISCONNECTED")
            except Exception as exc:
                self.log("DISCONNECT_FAULT", error=repr(exc))

        print("LOG FILE:", LOG)

    async def run(self):
        self.log("SESSION_STARTED")

        try:
            await self.robot.connect()
            self.active = True
            self.log("CONNECTED")
            print("CONNECTED")
            print("U=Stand L=Lie S=Sit R=RiseSit Q=Lie+Quit")

            while True:
                raw = await asyncio.to_thread(input, "COMMAND> ")
                key = raw.strip().upper()

                self.log("KEY_INPUT", raw=raw, key=key)

                if not key:
                    continue

                if key == "Q":
                    self.log("QUIT_REQUESTED")
                    success = await self.move_to("LYING")
                    self.log("QUIT_POSTURE_RESULT", success=success)
                    if not success:
                        print("WARNING: LYING NOT CONFIRMED")
                    break

                if key not in COMMANDS:
                    print("UNKNOWN COMMAND")
                    self.log("UNKNOWN_COMMAND", key=key)
                    continue

                success = await self.move_to(COMMANDS[key])

                self.log(
                    "TRANSITION_RESULT",
                    key=key,
                    success=success,
                )

                if not success:
                    print("TRANSITION INCOMPLETE - ENDING SESSION")
                    break

        except Exception as exc:
            self.log("SESSION_FAULT", error=repr(exc))
            print("SESSION FAULT:", exc)

        finally:
            await self.shutdown()


if __name__ == "__main__":
    asyncio.run(Controller().run())
