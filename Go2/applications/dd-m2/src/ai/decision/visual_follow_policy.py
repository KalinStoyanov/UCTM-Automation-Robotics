"""B3: Visual target-centering policy."""

from ..contracts.models import ActionProposal, WorldState


class VisualFollowPolicy:
    def __init__(self, deadband=0.10, angular_speed=0.15):
        self.deadband = deadband
        self.angular_speed = angular_speed

    def predict(self, state: WorldState) -> ActionProposal:
        target_x = state.robot_state.get("target_center_x")

        if target_x is None:
            return ActionProposal(
                action="STOP",
                reason="No target position",
            )

        if not 0.0 <= target_x <= 1.0:
            return ActionProposal(
                action="STOP",
                reason="Invalid target position",
            )

        error = target_x - 0.5

        if abs(error) <= self.deadband:
            return ActionProposal(
                action="STOP",
                reason="Target centered",
            )

        direction = "TURN_RIGHT" if error > 0 else "TURN_LEFT"
        angular = self.angular_speed if error > 0 else -self.angular_speed

        return ActionProposal(
            action=direction,
            angular_rad_s=angular,
            reason="Visual target centering",
        )
