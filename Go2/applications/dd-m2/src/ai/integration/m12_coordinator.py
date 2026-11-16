"""M12 B6: Conservative multi-component coordination."""

from ..contracts.models import ActionProposal
from ..contracts.m12 import ActionEvaluation, AIResult


class M12Coordinator:
    def __init__(self, min_confidence=0.5):
        if not 0 <= min_confidence <= 1:
            raise ValueError("Invalid confidence threshold")
        self.min_confidence = min_confidence

    def coordinate(
        self,
        decision: ActionProposal,
        learned: ActionProposal,
        planned: ActionEvaluation,
    ):
        proposals = (
            decision.action,
            learned.action,
            planned.action,
        )

        confidence = min(
            decision.confidence,
            learned.confidence,
            planned.confidence,
        )

        if (
            len(set(proposals)) != 1
            or confidence < self.min_confidence
            or proposals[0] not in {
                "STOP", "TURN_LEFT", "TURN_RIGHT"
            }
        ):
            return AIResult(
                action="STOP",
                linear_m_s=0.0,
                angular_rad_s=0.0,
                confidence=confidence,
                reason="Disagreement or low confidence",
            )

        return AIResult(
            action=decision.action,
            linear_m_s=0.0,
            angular_rad_s=decision.angular_rad_s,
            confidence=confidence,
            reason="M12 components agree",
        )
