import numpy as np

from app.stages import dedup as D


def _shelf(seed=0):
    """A wide synthetic shelf: 40 'books' of random width/colour with textured spines."""
    rng = np.random.default_rng(seed)
    img = np.full((800, 2400, 3), 230, np.uint8)
    boxes, x = [], 20
    while x < 2350:
        w = int(rng.integers(30, 70))
        h = int(rng.integers(450, 650))
        y = 750 - h
        img[y:750, x:x + w] = rng.integers(20, 220, 3)
        noise = rng.integers(0, 60, (h, w, 3))
        img[y:750, x:x + w] = np.clip(img[y:750, x:x + w].astype(int) + noise, 0, 255)
        boxes.append((x, y, x + w, 750))
        x += w + 2
    return img, boxes


def _crop(img, boxes, x0, x1):
    """A keyframe = a window of the shelf; keep spines fully inside it, shifted into frame coordinates."""
    inside = [(a - x0, b, c - x0, d) for a, b, c, d in boxes if a >= x0 and c <= x1]
    return {"image": np.ascontiguousarray(img[:, x0:x1]), "boxes": inside, "texts": [""] * len(inside)}


def test_overlapping_frames_count_each_book_once():
    img, boxes = _shelf()
    frames = [_crop(img, boxes, 0, 1200), _crop(img, boxes, 800, 2000), _crop(img, boxes, 1600, 2400)]
    seen = sum(len(f["boxes"]) for f in frames)
    groups, registered = D.duplicate_groups(frames)
    truth = len([b for b in boxes if b[2] <= 2400])
    assert registered == 2
    assert seen > truth                         # naive count double-counts the overlaps
    assert abs(len(groups) - truth) <= 1        # de-duplicated count matches the shelf


def test_unrelated_frames_are_not_merged():
    a_img, a_boxes = _shelf(1)
    b_img, b_boxes = _shelf(2)
    frames = [_crop(a_img, a_boxes, 0, 1200), _crop(b_img, b_boxes, 0, 1200)]
    groups, registered = D.duplicate_groups(frames)
    assert registered == 0 and len(groups) == len(frames[0]["boxes"]) + len(frames[1]["boxes"])


def test_conflicting_text_is_never_merged():
    assert D._texts_conflict("Atomic Habits", "Deep Work")
    assert not D._texts_conflict("ATOMIC HABITS JAMES CLEAR", "Atomic Habits")
    assert not D._texts_conflict("", "Deep Work")
