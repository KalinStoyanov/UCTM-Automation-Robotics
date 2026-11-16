"""B1: Convert existing person-tracker output to AI objects."""

from ..contracts.models import DetectedObject


def normalize_persons(persons):
    return tuple(
        DetectedObject(
            object_id=int(p["id"]),
            label="person",
            bbox=tuple(float(v) for v in p["bbox"]),
            confidence=float(p["confidence"]),
        )
        for p in persons
    )
