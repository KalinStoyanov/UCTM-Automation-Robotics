"""B4: Simple trainable discrete decision policy."""

from collections import Counter

from ..contracts.models import WorldState, ActionProposal


class ExamplePolicy:
    def __init__(self):
        self.counts = {}

    def fit(self, examples):
        """Learn action frequencies for discrete states."""
        self.counts = {}

        for state_key, action in examples:
            if state_key not in self.counts:
                self.counts[state_key] = Counter()
            self.counts[state_key][action] += 1

    def predict(self, state: WorldState) -> ActionProposal:
        key = "persons_present" if state.objects else "empty"

        if key not in self.counts:
            return ActionProposal(
                action="STOP",
                reason="Untrained state",
            )

        action = self.counts[key].most_common(1)[0][0]

        return ActionProposal(
            action=action,
            reason="Learned from examples",
        )
