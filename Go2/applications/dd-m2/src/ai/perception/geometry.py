"""B1: Image-space geometry of detected objects."""


def bbox_geometry(bbox, image_width, image_height):
    if image_width <= 0 or image_height <= 0:
        raise ValueError("Invalid image dimensions")

    x1, y1, x2, y2 = map(float, bbox)

    if not (0 <= x1 < x2 <= image_width):
        raise ValueError("Invalid horizontal bounding box")

    if not (0 <= y1 < y2 <= image_height):
        raise ValueError("Invalid vertical bounding box")

    return {
        "center_x": ((x1 + x2) / 2) / image_width,
        "center_y": ((y1 + y2) / 2) / image_height,
        "width": (x2 - x1) / image_width,
        "height": (y2 - y1) / image_height,
        "area": ((x2 - x1) * (y2 - y1))
                / (image_width * image_height),
    }
