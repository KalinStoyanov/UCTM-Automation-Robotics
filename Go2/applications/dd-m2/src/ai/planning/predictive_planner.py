"""M12 B5: Candidate-action evaluation."""

from ..contracts.m12 import Prediction, ActionEvaluation


class PredictivePlanner:
    def __init__(self, correction_step=0.15):
        if not 0 < correction_step <= 0.5:
            raise ValueError("Invalid correction step")
        self.correction_step = correction_step

    def evaluate(self, prediction: Prediction):
        actions = {
            "TURN_LEFT": -self.correction_step,
            "STOP": 0.0,
            "TURN_RIGHT": self.correction_step,
        }

        evaluations = []

        for action, correction in actions.items():
            # Simplified image-space response model.
            resulting_x = prediction.center_x - correction
            error = abs(resulting_x - 0.5)

            evaluations.append(
                ActionEvaluation(
                    action=action,
                    score=-error,
                    confidence=prediction.confidence,
                )
            )

        return sorted(
            evaluations,
            key=lambda item: item.score,
            reverse=True,
        )

    def plan(self, prediction: Prediction):
        return self.evaluate(prediction)[0]
