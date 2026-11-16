"""B3: Baseline reactive decision policy."""

from ..contracts.models import WorldState, ActionProposal


class ReactivePolicy:
    def predict(self, state: WorldState) -> ActionProposal:
        if not state.objects:
            return ActionProposal(
                action="STOP",
                reason="No observations available",
            )

        return ActionProposal(
            action="STOP",
            reason="Safe baseline: no autonomous movement",
        )
