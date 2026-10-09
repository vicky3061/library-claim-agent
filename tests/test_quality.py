import cv2
import numpy as np

from app.stages import quality as Q


def _sharp():
    img = np.zeros((480, 640, 3), np.uint8)
    for x in range(0, 640, 20):                     # stripes: lots of crisp edges, like book spines
        img[:, x:x + 10] = (40, 120, 200)
    img = np.clip(img.astype(int) + 60, 0, 255).astype(np.uint8)  # not dark (int first: uint8 would wrap)
    return img


def test_sharp_frame_is_ok_without_marker_requirement():
    r = Q.check_frame(_sharp(), need_marker=False)
    assert r["ok"] and r["hint"] is None


def test_blur_is_detected():
    r = Q.check_frame(cv2.GaussianBlur(_sharp(), (31, 31), 12), need_marker=False)
    assert "blurry" in r["issues"] and "still" in r["hint"]


def test_glare_is_detected():
    img = _sharp(); img[100:300, 100:400] = 255     # big white colourless patch
    assert "glare" in Q.check_frame(img, need_marker=False)["issues"]


def test_dark_is_detected_first():
    r = Q.check_frame((_sharp() * 0.2).astype(np.uint8), need_marker=False)
    assert r["issues"][0] == "dark" and "light" in r["hint"]


def test_missing_marker_is_reported():
    assert "no_marker" in Q.check_frame(_sharp(), need_marker=True)["issues"]