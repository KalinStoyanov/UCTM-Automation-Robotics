from ultralytics import YOLO


class PersonTracker:
    def __init__(self, model_path="yolo11n.pt"):
        self.model = YOLO(model_path)

    def track(self, frame):
        results = self.model.track(
            source=frame,
            persist=True,
            tracker="bytetrack.yaml",
            classes=[0],
            conf=0.25,
            device="cpu",
            verbose=False
        )

        persons = []
        boxes = results[0].boxes

        if boxes is None or boxes.id is None:
            return persons

        for box in boxes:
            persons.append({
                "id": int(box.id.item()),
                "bbox": [
                    round(v, 1)
                    for v in box.xyxy[0].tolist()
                ],
                "confidence": round(float(box.conf.item()), 3)
            })

        return persons
