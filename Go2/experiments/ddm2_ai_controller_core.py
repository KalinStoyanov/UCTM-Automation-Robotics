"""DD-M2 offline AI controller orchestration.

No robot connection or hardware command execution.
"""

from experiments.ddm2_ai_pipeline import OfflineAIPipeline
from experiments.ddm2_ai_arbitration import CommandArbiter


class AIControllerCore:
    def __init__(self, pipeline=None, arbiter=None):
        self.pipeline = (
            pipeline if pipeline is not None
            else OfflineAIPipeline()
        )
        self.arbiter = (
            arbiter if arbiter is not None
            else CommandArbiter()
        )
        self.last_timing = None

    def authorize_motion(self, authorized):
        self.arbiter.set_motion_authorized(authorized)

    def enable_ai(self):
        return self.arbiter.enable_ai()

    def manual_stop(self):
        return self.arbiter.manual_stop()

    def manual_command(self, linear, angular):
        return self.arbiter.manual_command(linear, angular)

    def reset_stop(self):
        self.arbiter.reset_stop()

    def step(self, frame, now):
        if (
            self.arbiter.stop_latched
            or self.arbiter.mode != "AI"
            or not self.arbiter.motion_authorized
        ):
            return self.arbiter.stop()

        try:
            command, timing = self.pipeline.step(frame, now)
            self.last_timing = timing

            if (
                not isinstance(timing, dict)
                or timing.get("deadline_miss") is not False
            ):
                return self.arbiter.manual_stop()

            return self.arbiter.ai_command(command)

        except Exception:
            self.last_timing = None
            return self.arbiter.manual_stop()
