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


def thickness_factors(boxes, orientations):
    """Books cannot overlap each other. Model boxes of neighbouring spines usually do (padding), which made every
    thickness come out too big (Neptunes v1: 13 of 17 thicknesses +30% to +135%; heights were fine).
    Within each run of touching upright spines, and within each stack of flat books, scale thickness by
    span / sum-of-thicknesses, so the books exactly fill the space they occupy. Never enlarges (gaps are real)."""
    f = [1.0] * len(boxes)

    def shrink(run, lo, hi):
        if len(run) < 2:
            return
        span = max(boxes[i][hi] for i in run) - min(boxes[i][lo] for i in run)
        total = sum(boxes[i][hi] - boxes[i][lo] for i in run)
        k = min(1.0, span / total) if total > 0 else 1.0
        for i in run:
            f[i] = k

    up = sorted((i for i, o in enumerate(orientations) if o != "flat"), key=lambda i: boxes[i][0])
    if up:
        med = float(np.median([boxes[i][2] - boxes[i][0] for i in up]))
        run = [up[0]]
        for i in up[1:]:
            if boxes[i][0] > max(boxes[j][2] for j in run) + 0.5 * med:  # a real gap: new run
                shrink(run, 0, 2)
                run = []
            run.append(i)
        shrink(run, 0, 2)
    stacks = []
    for i in sorted((i for i, o in enumerate(orientations) if o == "flat"), key=lambda i: boxes[i][0]):
        for st in stacks:
            j = st[0]
            ov = min(boxes[i][2], boxes[j][2]) - max(boxes[i][0], boxes[j][0])
            if ov > 0.5 * min(boxes[i][2] - boxes[i][0], boxes[j][2] - boxes[j][0]):
                st.append(i)
                break
        else:
            stacks.append([i])
    for st in stacks:
        shrink(st, 1, 3)
    return f
