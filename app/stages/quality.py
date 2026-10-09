import cv2
import numpy as np

from app import config
from app.stages import scale

HINTS = {
    "blurry": "Hold the phone still for a moment, the picture is blurry.",
    "glare": "There is glare. Tilt the phone slightly or step to the side.",
    "dark": "It is too dark here. Can you turn on a light?",
    "no_marker": "I can't see a shelf marker. Please include the printed square in the shot.",
}


def _small(image, width=640):
    h, w = image.shape[:2]
    return image if w <= width else cv2.resize(image, (width, int(h * width / w)), interpolation=cv2.INTER_AREA)


def _marker_sheet_mask(shape, markers, scale_factor, grow=1.8):
    """White paper around a printed marker is not glare: mask a box ~1.8x the marker around each one."""
    mask = np.zeros(shape[:2], bool)
    for m in markers:
        pts = np.array(m["corners_px"], float) * scale_factor
        cx, cy = pts.mean(axis=0)
        half = (pts.max(axis=0) - pts.min(axis=0)).max() * grow / 2
        y0, y1 = int(max(cy - half, 0)), int(min(cy + half, shape[0]))
        x0, x1 = int(max(cx - half, 0)), int(min(cx + half, shape[1]))
        mask[y0:y1, x0:x1] = True
    return mask


def check_frame(image, need_marker=True):
    img = _small(image)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    markers = scale.detect_markers(image)  # full resolution: markers are small
    blur_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    bright_white = (hsv[..., 2] >= 250) & (hsv[..., 1] <= 30)
    bright_white &= ~_marker_sheet_mask(img.shape, markers, img.shape[1] / image.shape[1])
    glare_frac = float(np.mean(bright_white))
    brightness = float(gray.mean())
    issues = []
    if brightness < config.DARK_MAX_MEAN:
        issues.append("dark")
    if blur_var < config.BLUR_MIN_VAR:
        issues.append("blurry")
    if glare_frac > config.GLARE_MAX_FRAC:
        issues.append("glare")
    if need_marker and not markers:
        issues.append("no_marker")
    return {"ok": not issues, "issues": issues, "hint": HINTS[issues[0]] if issues else None,
            "blur_var": round(blur_var, 1), "glare_frac": round(glare_frac, 4), "brightness": round(brightness, 1),
            "markers": [{"id": m["id"], "px_per_cm": m["px_per_cm"]} for m in markers]}