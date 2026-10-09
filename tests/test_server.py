import cv2
import numpy as np
from fastapi.testclient import TestClient

from app import server as S
from app.stages import vision as V


def _jpg(img):
    return cv2.imencode(".jpg", img)[1].tobytes()


def _stripes(shift=0):
    img = np.full((480, 640, 3), 90, np.uint8)
    for x in range(shift, 640, 20):
        img[:, x:x + 10] = (40, 160, 220)
    return img


def test_live_sweep_end_to_end(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "runs").mkdir()
    frame = V.FrameOut(spines=[V.SpineOut(box_2d=[100, 100, 900, 150], orientation="upright", text="ATOMIC HABITS",
                                          title="ATOMIC HABITS", author="", legibility="clear", cut_off=False)], items=[])
    monkeypatch.setattr(S.vision, "analyze_frame", lambda b: (frame, {"cache_hit": False}))
    monkeypatch.setattr(S.pipeline.vision, "analyze_frame", lambda b: (frame, {"cache_hit": True}))
    ident = {"status": "identified", "confidence": 1.0, "volume": None,
             "match": {"title": "Atomic Habits", "authors": ["James Clear"], "published": "2018"}}
    monkeypatch.setattr(S.resolve, "resolve_spine", lambda s: ident)
    monkeypatch.setattr(S.pipeline.resolve, "resolve_spine", lambda s: ident)
    monkeypatch.setattr(S.pipeline.price, "price_book", lambda *a, **k: {"status": "identified", "replacement": None, "used": None, "notes": []})
    c = TestClient(S.app)
    sid = c.post("/api/sweep/start", json={"country": "in", "currency": "inr"}).json()["sweep_id"]

    r1 = c.post(f"/api/sweep/{sid}/frame", files={"file": ("f.jpg", _jpg(_stripes()), "image/jpeg")}).json()
    assert r1["kept"] and "no_marker" in r1["quality"]["issues"]          # usable for titles, marker hint spoken
    r2 = c.post(f"/api/sweep/{sid}/frame", files={"file": ("f.jpg", _jpg(_stripes()), "image/jpeg")}).json()
    assert not r2["kept"]                                                   # same view -> not stored twice
    blurry = cv2.GaussianBlur(_stripes(7), (31, 31), 12)
    r3 = c.post(f"/api/sweep/{sid}/frame", files={"file": ("f.jpg", _jpg(blurry), "image/jpeg")}).json()
    assert not r3["kept"] and "still" in r3["hint"]                         # blurry -> rejected with a hint

    done = c.post(f"/api/sweep/{sid}/finish").json()
    assert done["books"] == 1 and done["identified"] == 1
    assert c.get(done["report"]).status_code == 200                         # report opens from the server
    assert S.SWEEPS[sid]["country"] == "IN"


def test_new_view_rule():
    a = S._thumb(_stripes()); b = S._thumb(_stripes(10))
    assert S.is_new_view(a, None) and not S.is_new_view(a, a) and S.is_new_view(b, a)