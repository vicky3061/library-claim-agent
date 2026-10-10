import cv2
import numpy as np

from app.schema import Dimensions, Item, ItemStatus
from app.stages import room as R
from app.stages.vision import WallOut

W_PX, H_PX = 1600, 1200


def _wall_photo(width_cm, height_cm, marker_id, hide=()):
    """A wall (plane in cm) seen at a mild angle; 18 cm marker at chest height. Returns (markers, WallOut)."""
    plane = np.float32([[0, 0], [width_cm, 0], [width_cm, height_cm], [0, height_cm]])
    img = np.float32([[90, 80], [1510, 110], [1490, 1110], [110, 1130]])
    P = cv2.getPerspectiveTransform(plane, img)
    to_img = lambda pts: cv2.perspectiveTransform(np.float32([pts]), P)[0]
    mx, my = width_cm / 2, height_cm - 140
    marker = {"id": marker_id, "size_cm": 18.0,
              "corners_px": to_img([[mx, my], [mx + 18, my], [mx + 18, my + 18], [mx, my + 18]]).astype(np.float32)}
    c = to_img([[0, 0], [width_cm, 0], [width_cm, height_cm], [0, height_cm]])
    as_1000 = lambda p: [int(round(p[1] / H_PX * 1000)), int(round(p[0] / W_PX * 1000))]
    names = ["top_left", "top_right", "bottom_right", "bottom_left"]
    wall = WallOut(visible=True, **{n: ([] if n in hide else as_1000(p)) for n, p in zip(names, c)})
    return [marker], wall


def test_four_walls_give_room_size_within_bars():
    walls = [R.measure_wall(*_wall_photo(w, 270, mid), W_PX, H_PX)
             for w, mid in ((400, 10), (300, 11), (404, 12), (296, 13))]
    room = R.room_from_walls(R.best_per_wall(walls))
    assert abs(room["length_m"] - 4.02) < 0.05 and abs(room["width_m"] - 2.98) < 0.05
    assert abs(room["height_m"] - 2.70) < 0.05
    true_floor, true_wall = 4.02 * 2.98, 2 * (4.02 + 2.98) * 2.70
    assert abs(room["floor_area_m2"] - true_floor) / true_floor < 0.10          # floor bar
    assert abs(room["wall_area_m2"] - true_wall) / true_wall < 0.15             # wall bar
    assert room["confidence"] == 0.85 and "Rectangle assumed" in room["shape_note"]


def test_two_adjacent_walls_are_enough_but_less_confident():
    walls = [R.measure_wall(*_wall_photo(w, 270, mid), W_PX, H_PX) for w, mid in ((400, 10), (300, 11))]
    room = R.room_from_walls(R.best_per_wall(walls))
    assert room["floor_area_m2"] is not None and room["confidence"] == 0.6


def test_one_wall_leaves_areas_empty_and_says_why():
    room = R.room_from_walls(R.best_per_wall([R.measure_wall(*_wall_photo(400, 270, 10), W_PX, H_PX)]))
    assert room["floor_area_m2"] is None and room["wall_area_m2"] is None and "need one wall" in room["shape_note"]


def test_hidden_corner_still_measures_from_the_other_edge():
    m = R.measure_wall(*_wall_photo(400, 270, 10, hide=("top_left",)), W_PX, H_PX)
    assert m["corners_seen"] == 3 and abs(m["width_cm"] - 400) < 10 and abs(m["height_cm"] - 270) < 10


def test_shelved_wall_area_from_bookcases():
    shelf = [Item(id="i1", category="shelving", frame_ref="f", status=ItemStatus.range, dimensions_cm=Dimensions(w=90, h=180)),
             Item(id="i2", category="shelving", frame_ref="f", status=ItemStatus.range, dimensions_cm=Dimensions(w=80, h=200))]
    assert R.room_from_walls({}, shelf)["shelved_wall_area_m2"] == 3.22
