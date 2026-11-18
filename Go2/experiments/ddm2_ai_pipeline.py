"""Offline AI pipeline for DD-M2.

M19Runtime -> AIResult -> AICommandAdapter.
No robot transport or motor commands.
"""

import sys
from pathlib import Path

from experiments.ddm2_ai_adapter import AICommandAdapter


ROOT = Path(__file__).resolve().parents[1]
AI_ROOT = ROOT / "applications" / "dd-m2"


class OfflineAIPipeline:
    def __init__(self, runtime=None, adapter=None):
        if runtime is None:
            ai_path = str(AI_ROOT)
            if ai_path not in sys.path:
                sys.path.insert(0, ai_path)

            from src.ai.integration.m19_scheduler import M19Runtime

            runtime = M19Runtime(
                model_path=str(
                    ROOT / "results/m13/neural_policy.npz"
                )
            )

        self.runtime = runtime
        self.adapter = adapter or AICommandAdapter()

    def step(self, frame, now):
        result, timing = self.runtime.step(frame, now)
        command = self.adapter.convert(result)
        return command, timing
