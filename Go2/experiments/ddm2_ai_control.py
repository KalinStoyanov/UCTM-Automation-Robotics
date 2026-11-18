"""DD-M2 AI controller entry point.

Shares the verified manual base controller and its WebRTC/SPORT execution
path. AI autonomy is intentionally disabled until perception, planning,
arbitration, and safety contracts are implemented and validated.
"""
import asyncio

from experiments import ddm2_manual_control as base


AI_ENABLED = False


class AIController:
    """Offline-first extension point; no autonomous actuation yet."""

    def __init__(self):
        self.enabled = AI_ENABLED

    def submit_ai_command(self, command):
        raise RuntimeError(
            "AI motion is disabled pending command arbitration and safety validation"
        )


async def main():
    # Keep one command queue, one watchdog and the same manual key bindings.
    await base.main()


if __name__ == "__main__":
    asyncio.run(main())
