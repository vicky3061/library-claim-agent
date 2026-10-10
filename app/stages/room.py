"""Room size from the same sweep: an 18 cm marker on each wall gives that wall's plane in centimetres;
vision only points at where the wall's corners are (floor/ceiling/neighbouring-wall junctions);
code measures the distances through the homography. Walls are paired as opposite by marker ID
(10 opposite 12, 11 opposite 13: markers placed clockwise round the room)."""
import statistics

import numpy as np

from app import config
from app.stages import measure, scale

CORNERS = ("top_left", "top_right", "bottom_right", "bottom_left")


def _px(pt, w, h):
    y, x = pt
    return (x / 1000 * w, y / 1000 * h)


def measure_wall(markers, wall, w, h):
    """One wall photo -> {"marker_id", "width_cm", "height_cm", "corners_seen"} or None (no wall marker / no corners)."""
    if not wall or not getattr(wall, "visible", False):
        return None
    pts = {c: _px(getattr(wall, c), w, h) for c in CORNERS if len(getattr(wall, c) or []) == 2}
    if len(pts) < 2:
        return None
    centre = np.mean(list(pts.values()), axis=0)
    m = measure.nearest_marker(markers, (centre[0], centre[1], centre[0], centre[1]), config.WALL_MARKER_CM)
    if m is None:
        return None
    H = scale.image_to_plane(m)
    d = lambda a, b: scale.plane_distance_cm(H, pts[a], pts[b]) if a in pts and b in pts else None
    widths = [v for v in (d("bottom_left", "bottom_right"), d("top_left", "top_right")) if v]
    heights = [v for v in (d("top_left", "bottom_left"), d("top_right", "bottom_right")) if v]
    return {"marker_id": m["id"], "corners_seen": len(pts),
            "width_cm": round(statistics.mean(widths), 1) if widths else None,
            "height_cm": round(statistics.mean(heights), 1) if heights else None}


def best_per_wall(measurements):
    """Several photos of the same wall (same marker ID): keep the one that saw the most corners."""
    best = {}
    for m in measurements:
        if m and (m["marker_id"] not in best or m["corners_seen"] > best[m["marker_id"]]["corners_seen"]):
            best[m["marker_id"]] = m
    return best


def room_from_walls(walls, shelving_items=()):
    """walls: {marker_id: measurement}. Returns Room fields (dict). Unknown stays None."""
    out = {"scale_method": "aruco_marker_homography (18 cm wall markers) + vision-located wall corners",
           "length_m": None, "width_m": None, "height_m": None, "floor_area_m2": None, "wall_area_m2": None,
           "shelved_wall_area_m2": None, "confidence": None, "shape_note": None}
    ids = sorted(i for i, m in walls.items() if m["width_cm"])
    pairs = [(a, a + 2) for a in (10, 11)]
    sides, agreement, notes = [], [], []
    for a, b in pairs:
        vals = [walls[i]["width_cm"] for i in (a, b) if i in walls and walls[i]["width_cm"]]
        if vals:
            sides.append(statistics.mean(vals))
            if len(vals) == 2:
                agreement.append(abs(vals[0] - vals[1]) / max(vals))
                notes.append(f"walls {a}/{b} agree within {abs(vals[0] - vals[1]) / max(vals):.0%}")
    heights = [m["height_cm"] for m in walls.values() if m["height_cm"]]
    if heights:
        out["height_m"] = round(statistics.median(heights) / 100, 2)
    if len(sides) == 2:
        L, W = max(sides) / 100, min(sides) / 100
        out.update(length_m=round(L, 2), width_m=round(W, 2), floor_area_m2=round(L * W, 2))
        if out["height_m"]:
            out["wall_area_m2"] = round(2 * (L + W) * out["height_m"], 2)
        if len(agreement) == 2 and max(agreement) <= 0.10:
            out["confidence"] = 0.85
        elif agreement and max(agreement) <= 0.10:
            out["confidence"] = 0.7
        else:
            out["confidence"] = 0.6 if not agreement else 0.5
        out["shape_note"] = ("Rectangle assumed: length/width from opposite wall pairs (marker IDs 10/12, 11/13); "
                             "gross wall area = perimeter x height, doors/windows not subtracted. " + "; ".join(notes))
    else:
        out["shape_note"] = (f"Measured walls {ids}: need one wall from each pair (10 or 12, and 11 or 13) "
                             "to get length and width; floor/wall area left empty")
    shelf = [(i.dimensions_cm.w, i.dimensions_cm.h) for i in shelving_items
             if i.dimensions_cm.w and i.dimensions_cm.h]
    if shelf:
        out["shelved_wall_area_m2"] = round(sum(w * h for w, h in shelf) / 1e4, 2)
    return out
