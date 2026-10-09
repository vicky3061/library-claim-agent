import argparse
import io

import cv2
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

DICTIONARY = cv2.aruco.DICT_4X4_50  # simple 4x4 patterns: easiest to detect reliably


def marker_image(marker_id: int) -> ImageReader:
    d = cv2.aruco.getPredefinedDictionary(DICTIONARY)
    img = cv2.aruco.generateImageMarker(d, marker_id, 800)  # 800 px source, scaled when drawn
    ok, png = cv2.imencode(".png", img)
    return ImageReader(io.BytesIO(png.tobytes()))


def draw_ruler(c):
    c.setLineWidth(1.5)
    c.line(2 * cm, 1.8 * cm, 12 * cm, 1.8 * cm)
    for i in range(11):
        tick = 2.4 if i % 5 == 0 else 2.1
        c.line((2 + i) * cm, 1.8 * cm, (2 + i) * cm, tick * cm)
    c.setFont("Helvetica", 9)
    c.drawString(2 * cm, 1.2 * cm, "This line must measure exactly 10.0 cm. Print at 100% / Actual size.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="markers_A4.pdf")
    a = ap.parse_args()

    width, height = A4
    c = canvas.Canvas(a.out, pagesize=A4)

    # Pages 1-2: shelf markers, 10 cm, two per page (IDs 0-3)
    size = 10 * cm
    for page_ids in ([0, 1], [2, 3]):
        for slot, mid in enumerate(page_ids):
            x = (width - size) / 2
            y = height - 2 * cm - size - slot * (size + 3 * cm)
            c.drawImage(marker_image(mid), x, y, size, size)
            c.setFont("Helvetica-Bold", 12)
            c.drawString(x, y - 0.6 * cm, f"SHELF marker ID {mid}  (black square = 10.0 cm)")
        draw_ruler(c)
        c.showPage()

    # Pages 3-6: wall markers, 18 cm, one per page (IDs 10-13)
    size = 18 * cm
    for mid in [10, 11, 12, 13]:
        x = (width - size) / 2
        y = height - 3 * cm - size
        c.drawImage(marker_image(mid), x, y, size, size)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x, y - 0.6 * cm, f"WALL marker ID {mid}  (black square = 18.0 cm)")
        draw_ruler(c)
        c.showPage()

    c.save()
    print("wrote", a.out)


if __name__ == "__main__":
    main()