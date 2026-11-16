"""B4: Trainable tabular policy for simulated observations."""

from collections import defaultdict, Counter

from ..contracts.models import ActionProposal, WorldState


class TabularPolicy:
    def __init__(self):
        self.table = defaultdict(Counter)

    def fit(self, examples):
        self.table.clear()

        for observation, action in examples:
            self.table[observation][action] += 1

    def predict(self, state: WorldState) -> ActionProposal:
        observation = state.robot_state.get("observation")

        if observation not in self.table:
            return ActionProposal(
                action="STOP",
                reason="Unknown observation",
            )

        action = self.table[observation].most_common(1)[0][0]

        return ActionProposal(
            action=action,
            reason="Tabular learned policy",
        )
