"""Cross-frame de-duplication: the same physical book seen in two overlapping keyframes is counted once.

How: consecutive keyframes overlap (~1/3). We register each frame to the next with ORB features + a RANSAC
homography, map every spine box of frame i into frame i+1, and treat boxes that land on top of each other
(IoU >= threshold) as the same book. Geometry decides, not the model. If two readable spines disagree on their
text, they are never merged (a safety net against a bad registration)."""
import cv2
import numpy as np
from rapidfuzz import fuzz

from app import config
from app.stages.resolve import norm

_orb = cv2.ORB_create(nfeatures=3000)
_matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)


def _gray_small(image, width=1000):
    h, w = image.shape[:2]
    s = min(1.0, width / w)
    g = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    return (cv2.resize(g, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA) if s < 1 else g), s


def register(img_a, img_b):
    """Homography mapping full-resolution pixels of img_a onto img_b, or None if they do not overlap enough."""
    ga, sa = _gray_small(img_a)
    gb, sb = _gray_small(img_b)
    ka, da = _orb.detectAndCompute(ga, None)
    kb, db = _orb.detectAndCompute(gb, None)
    if da is None or db is None or len(ka) < 10 or len(kb) < 10:
        return None
    matches = _matcher.match(da, db)
    if len(matches) < config.DEDUP_MIN_INLIERS:
        return None
    src = np.float32([ka[m.queryIdx].pt for m in matches]) / sa
    dst = np.float32([kb[m.trainIdx].pt for m in matches]) / sb
    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
    if H is None or int(mask.sum()) < config.DEDUP_MIN_INLIERS:
        return None
    return H


def map_box(box, H):
    x1, y1, x2, y2 = box
    pts = cv2.perspectiveTransform(np.float32([[[x1, y1], [x2, y1], [x2, y2], [x1, y2]]]), H)[0]
    return (float(pts[:, 0].min()), float(pts[:, 1].min()), float(pts[:, 0].max()), float(pts[:, 1].max()))


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _texts_conflict(t1, t2):
    a, b = norm(t1), norm(t2)
    return bool(a and b) and fuzz.token_set_ratio(a, b) < 60


def duplicate_groups(frames):
    """frames: list of {"image": ndarray, "boxes": [(x1,y1,x2,y2) px], "texts": [str]} in sweep order.
    Returns (groups, pairs_registered): groups = list of [(frame_index, spine_index), ...], one group per book."""
    parent = {}

    def find(k):
        while parent.setdefault(k, k) != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    for fi, f in enumerate(frames):
        for si in range(len(f["boxes"])):
            find((fi, si))
    registered = 0
    for fi in range(len(frames) - 1):
        a, b = frames[fi], frames[fi + 1]
        if not a["boxes"] or not b["boxes"]:
            continue
        H = register(a["image"], b["image"])
        if H is None:
            continue
        registered += 1
        used = set()
        for si, box in enumerate(a["boxes"]):
            mapped = map_box(box, H)
            best, best_iou = None, config.DEDUP_IOU
            for sj, other in enumerate(b["boxes"]):
                v = iou(mapped, other)
                if sj not in used and v >= best_iou and not _texts_conflict(a["texts"][si], b["texts"][sj]):
                    best, best_iou = sj, v
            if best is not None:
                used.add(best)
                parent[find((fi, si))] = find((fi + 1, best))
    groups = {}
    for k in list(parent):
        groups.setdefault(find(k), []).append(k)
    return [sorted(g) for g in groups.values()], registered
