import cv2
import numpy as np

from app.stages.scale import detect_markers, image_to_plane, plane_distance_cm


def make_wall_photo():
    # A flat 300 cm x 200 cm wall drawn at 10 px per cm, with an 18 cm wall marker (ID 10)
    wall = np.full((2000, 3000), 255, np.uint8)
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    wall[500:680, 1000:1180] = cv2.aruco.generateImageMarker(d, 10, 180)
    # Simulate a phone photo taken at an angle
    src = np.float32([[0, 0], [3000, 0], [3000, 2000], [0, 2000]])
    dst = np.float32([[200, 100], [2700, 300], [2600, 1800], [300, 1950]])
    H = cv2.getPerspectiveTransform(src, dst)
    photo = cv2.warpPerspective(wall, H, (3000, 2100), borderValue=255)
    return photo, H


def test_wall_measured_from_marker():
    photo, H = make_wall_photo()
    markers = detect_markers(photo)
    assert [m["id"] for m in markers] == [10]
    to_plane = image_to_plane(markers[0])
    # where the wall's top-left, top-right and bottom-left corners landed in the photo
    c = cv2.perspectiveTransform(np.float32([[[0, 0], [3000, 0], [0, 2000]]]), H)[0]
    width = plane_distance_cm(to_plane, c[0], c[1])
    height = plane_distance_cm(to_plane, c[0], c[2])
    print(f"width {width:.1f} cm (true 300), height {height:.1f} cm (true 200)")
    assert abs(width - 300) / 300 < 0.02
    assert abs(height - 200) / 200 < 0.02


def test_no_marker_means_no_scale():
    assert detect_markers(np.full((500, 500), 255, np.uint8)) == []