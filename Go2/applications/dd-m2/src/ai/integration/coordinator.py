"""B6: Conservative coordination of AI action proposals."""

from ..contracts.models import ActionProposal


class AICoordinator:
    ACTIONS = {"STOP", "TURN_LEFT", "TURN_RIGHT"}

    def coordinate(self, decision, learned, plan):
        if not isinstance(decision, ActionProposal):
            raise TypeError("Invalid decision proposal")

        if not isinstance(learned, ActionProposal):
            raise TypeError("Invalid learned proposal")

        if not plan:
            return ActionProposal(
                action="STOP",
                reason="Empty plan",
            )

        actions = (decision.action, learned.action, plan[0])

        if any(a not in self.ACTIONS for a in actions):
            return ActionProposal(
                action="STOP",
                reason="Unsupported action",
            )

        if len(set(actions)) != 1:
            return ActionProposal(
                action="STOP",
                reason="AI components disagree",
            )

        return ActionProposal(
            action=decision.action,
            angular_rad_s=decision.angular_rad_s,
            reason="AI components agree",
        )
