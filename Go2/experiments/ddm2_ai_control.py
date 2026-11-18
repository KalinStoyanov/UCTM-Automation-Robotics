"""DD-M2 AI controller.

Manual base functions remain available.
AI execution requires explicit future activation.
"""

import argparse
import asyncio

from experiments import ddm2_manual_control as base
from experiments.ddm2_ai_controller_core import AIControllerCore
from experiments.ddm2_ai_gateway import AIExecutionGateway


AI_ENABLED = False


class AIController:
    def __init__(self, pipeline=None, executor=None):
        self.core = AIControllerCore(pipeline=pipeline)
        self.gateway = AIExecutionGateway(
            executor if executor is not None
            else self._disabled_executor
        )

    @staticmethod
    def _disabled_executor(linear, angular):
        raise RuntimeError("Live AI execution disabled")

    def manual_stop(self):
        self.core.manual_stop()
        return self.gateway.stop()

    def authorize_offline(self):
        self.core.authorize_motion(True)
        if not self.core.enable_ai():
            return False
        self.gateway.authorize()
        return True

    def step_offline(self, frame, now):
        result = self.core.step(frame, now)
        return self.gateway.execute(result)


def offline_self_test():
    commands = []
    controller = AIController(
        executor=lambda vx, wz: commands.append((vx, wz))
    )

    assert not AI_ENABLED
    assert controller.gateway.stop_latched

    controller.manual_stop()
    assert commands[-1] == (0.0, 0.0)

    print("DDA OFFLINE SELF-TEST: PASS")
    print("AI LIVE EXECUTION: DISABLED")


async def main():
    await base.main()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--offline-self-test",
        action="store_true",
    )
    args = parser.parse_args()

    if args.offline_self_test:
        offline_self_test()
    else:
        asyncio.run(main())
