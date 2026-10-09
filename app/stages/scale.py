import cv2
import numpy as np

from app import config

_detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))


def marker_size_cm(marker_id):
    if 0 <= marker_id <= 9:
        return config.SHELF_MARKER_CM
    if 10 <= marker_id <= 19:
        return config.WALL_MARKER_CM
    return None  # unknown marker: ignore it rather than guess its size


def detect_markers(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    corners, ids, _ = _detector.detectMarkers(gray)
    found = []
    if ids is None:
        return found
    for c, mid in zip(corners, ids.flatten()):
        size = marker_size_cm(int(mid))
        if size is None:
            continue
        pts = c.reshape(4, 2).astype(np.float32)  # top-left, top-right, bottom-right, bottom-left
        side_px = float(np.mean([np.linalg.norm(pts[i] - pts[(i + 1) % 4]) for i in range(4)]))
        found.append({"id": int(mid), "size_cm": size, "corners_px": pts, "px_per_cm": side_px / size})
    return found


def image_to_plane(marker):
    s = marker["size_cm"]
    plane = np.array([[0, 0], [s, 0], [s, s], [0, s]], dtype=np.float32)
    return cv2.getPerspectiveTransform(marker["corners_px"], plane)


def plane_distance_cm(H, p1, p2):
    pts = np.array([[p1, p2]], dtype=np.float32)
    out = cv2.perspectiveTransform(pts, H)[0]
    return float(np.linalg.norm(out[0] - out[1]))