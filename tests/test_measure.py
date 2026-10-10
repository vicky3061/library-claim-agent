import cv2
import numpy as np

from app.stages import measure as M


def _scene(image=((100, 100), (1500, 88), (1494, 662), (106, 650))):
    """Plane in cm -> image. Default: phone held roughly parallel to the shelf (small perspective), as the
    capture guide asks. Marker 10 cm at (5,5); a 3 x 22 cm spine at (40, 2)."""
    plane = np.float32([[0, 0], [100, 0], [100, 40], [0, 40]])
    image = np.float32(image)
    P = cv2.getPerspectiveTransform(plane, image)
    to_img = lambda pts: cv2.perspectiveTransform(np.float32([pts]), P)[0]
    marker = {"id": 0, "size_cm": 10.0, "corners_px": to_img([[5, 5], [15, 5], [15, 15], [5, 15]]).astype(np.float32)}
    spine = to_img([[40, 2], [43, 2], [43, 24], [40, 24]])
    box = (spine[:, 0].min(), spine[:, 1].min(), spine[:, 0].max(), spine[:, 1].max())
    return marker, box


def test_spine_size_through_perspective():
    marker, box = _scene()
    h, t, mid = M.spine_dims([marker], box)
    assert mid == 0
    assert abs(h - 22.0) / 22.0 < 0.05      # within 5% (bar is 15%)
    assert abs(t - 3.0) / 3.0 < 0.15


def test_no_shelf_marker_means_unknown():
    assert M.spine_dims([], (0, 0, 10, 100)) == (None, None, None)
    wall = {"id": 10, "size_cm": 18.0, "corners_px": np.float32([[0, 0], [10, 0], [10, 10], [0, 10]])}
    assert M.spine_dims([wall], (0, 0, 10, 100)) == (None, None, None)   # wall marker is not the shelf plane


def test_flat_book_long_side_is_horizontal():
    marker, _ = _scene()
    H = __import__("app.stages.scale", fromlist=["x"]).image_to_plane(marker)
    long_cm, short_cm = M.box_size_cm((300, 300, 600, 330), H, "flat")
    assert long_cm > short_cm


def test_strong_angle_inflates_thickness_documented_limitation():
    """Known limit: vision gives axis-aligned boxes; at a strong angle the box around a slanted spine is wider
    than the spine, so thickness reads ~20% high while height stays ~1% off. Mitigation: shoot parallel."""
    marker, box = _scene(((100, 120), (1500, 60), (1480, 700), (130, 640)))
    h, t, _ = M.spine_dims([marker], box)
    assert abs(h - 22.0) / 22.0 < 0.05 and t > 3.0 * 1.1



def test_overlapping_boxes_do_not_inflate_thickness():
    # Real failure (Neptunes v1): padded model boxes overlapped, thickness came out +30% to +135%
    from app.stages.measure import thickness_factors
    # 4 touching books, each truly 40 px thick, boxes padded to 60 px (overlapping neighbours)
    boxes = [(100 + 40 * k - 10, 0, 100 + 40 * k + 50, 300) for k in range(4)]
    f = thickness_factors(boxes, ["upright"] * 4)
    assert all(abs(k - 0.75) < 1e-6 for k in f)   # span 180 px / sum 240 px: each padded 60 px box -> 45 px
    # a real gap starts a new run; books with gaps are never enlarged
    apart = [(0, 0, 40, 300), (200, 0, 240, 300)]
    assert thickness_factors(apart, ["upright", "upright"]) == [1.0, 1.0]


def test_flat_stack_is_corrected_vertically():
    from app.stages.measure import thickness_factors
    stack = [(0, 0, 300, 50), (5, 30, 305, 80), (0, 60, 300, 110)]   # 3 flat books, boxes overlap by 20 px
    f = thickness_factors(stack, ["flat"] * 3)
    assert f[0] == f[1] == f[2] and abs(f[0] - 110 / 150) < 1e-6