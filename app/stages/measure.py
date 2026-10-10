"""Metric sizes from printed markers, with perspective corrected (homography), not a flat cm-per-pixel.
A marker defines a plane; a point on that plane maps to real centimetres. Spines stand in (about) the same plane
as the shelf marker taped in line with them, so spine height/thickness = distances on that plane."""
import numpy as np

from app import config
from app.stages import scale


def nearest_marker(markers, box, size_cm):
    """The marker of the given size closest to the box centre (a frame may show two bookcases)."""
    cands = [m for m in markers if m["size_cm"] == size_cm]
    if not cands:
        return None
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return min(cands, key=lambda m: float(np.hypot(*(m["corners_px"].mean(axis=0) - (cx, cy)))))


def box_size_cm(box, H, orientation="upright"):
    """(long side, short side) in cm for a pixel box, measured through the mid-lines on the marker's plane.
    Upright spine: long side is vertical. Flat (lying) book: long side is horizontal."""
    x1, y1, x2, y2 = box
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    vertical = scale.plane_distance_cm(H, (mx, y1), (mx, y2))
    horizontal = scale.plane_distance_cm(H, (x1, my), (x2, my))
    return (horizontal, vertical) if orientation == "flat" else (vertical, horizontal)


def spine_dims(markers, box, orientation="upright"):
    """(height_cm, thickness_cm, marker_id) or (None, None, None) when no shelf marker is in the frame."""
    m = nearest_marker(markers, box, config.SHELF_MARKER_CM)
    if m is None:
        return None, None, None
    long_cm, short_cm = box_size_cm(box, scale.image_to_plane(m), orientation)
    return round(long_cm, 1), round(short_cm, 1), m["id"]
