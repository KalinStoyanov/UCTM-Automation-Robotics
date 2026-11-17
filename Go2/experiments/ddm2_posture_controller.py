"""Experimental DD-M2 posture controller (v3, intermediate standing state).

Run from the Go2 repository root:
    PYTHONPATH=. python experiments/ddm2_posture_controller.py

This file is version controlled separately from the diagnostic controller.
LIVE robot commands require supervision and physical pose verification.
"""
import asyncio
from core.communication import go2_webrtc

go2_webrtc.LIVE_ENABLED = True


class PostureController:

    def __init__(self):
        self.robot = go2_webrtc.Go2WebRTC()
        self.pose = "UNKNOWN"

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
            print("U=Stand L=Lie S=Sit R=RiseSit Q=Lie+Quit")

            while True:
                key = (await asyncio.to_thread(
                    input, "COMMAND> "
                )).strip().upper()

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
