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



def _with_marker(img, marker_id):
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    m = cv2.aruco.generateImageMarker(d, marker_id, 120)
    out = img.copy()
    out[20:180, 20:180] = 255                                   # white quiet zone around the marker
    out[40:160, 40:160] = cv2.cvtColor(m, cv2.COLOR_GRAY2BGR)
    return out


def test_frame_advice_step_closer_and_logging():
    sp = lambda leg, text="X": V.SpineOut(box_2d=[0, 0, 1, 1], orientation="upright", text=text, legibility=leg, cut_off=False)
    assert "step closer" in S.frame_advice([sp("unreadable", ""), sp("partial"), sp("partial"), sp("clear")])
    assert S.frame_advice([sp("clear"), sp("clear"), sp("partial")]) == "Logged 3 books here, 3 readable."
    assert S.frame_advice([]) is None


def test_live_hints_too_fast_and_new_unit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); (tmp_path / "runs").mkdir()
    monkeypatch.setattr(S.vision, "analyze_frame", lambda b: (V.FrameOut(spines=[], items=[]), {}))
    c = TestClient(S.app)
    sid = c.post("/api/sweep/start", json={}).json()["sweep_id"]
    post = lambda img: c.post(f"/api/sweep/{sid}/frame", files={"file": ("f.jpg", _jpg(img), "image/jpeg")}).json()
    base = _stripes()
    post(_with_marker(base, 0))                                  # unit A: first unit, no announcement needed
    r = post(_with_marker(base, 1))                              # small change, new marker id -> unit B
    assert r["hint"] == "New shelving unit B. Logging it now." and r["inventory"]["shelving_units"] == ["A", "B"]
    r = post(_with_marker(_stripes(10), 1))                      # shelf view jumped a lot in 2 s -> too fast
    assert r["hint"].startswith("Slow down")



def test_voice_skip_shelf_removes_it_from_the_claim(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); (tmp_path / "runs").mkdir()
    frame = V.FrameOut(spines=[V.SpineOut(box_2d=[100, 450, 900, 550], orientation="upright", text="ATOMIC HABITS",
                                          title="ATOMIC HABITS", author="", legibility="clear", cut_off=False)],
                       items=[V.ItemOut(box_2d=[0, 0, 500, 500], category="framed art", description="portrait", visible_text="")])
    monkeypatch.setattr(S.vision, "analyze_frame", lambda b: (frame, {"cache_hit": True}))
    ident = {"status": "identified", "confidence": 1.0, "volume": None,
             "match": {"title": "Atomic Habits", "authors": ["James Clear"], "published": "2018"}}
    monkeypatch.setattr(S.resolve, "resolve_spine", lambda s: ident)
    monkeypatch.setattr(S.pipeline.price, "price_book", lambda *a, **k: {"status": "identified", "replacement": None, "used": None, "notes": []})
    c = TestClient(S.app)
    sid = c.post("/api/sweep/start", json={}).json()["sweep_id"]
    say = lambda text: c.post(f"/api/sweep/{sid}/say", json={"text": text}).json()
    assert "Point the camera" in say("that is a first edition")["reply"]     # nothing in view yet
    c.post(f"/api/sweep/{sid}/frame", files={"file": ("f.jpg", _jpg(_with_marker(_stripes(), 0)), "image/jpeg")})
    for fut in S.SWEEPS[sid]["futures"]:
        fut.result()
    assert any("original or a print" in a for a in S.SWEEPS[sid]["advice"])  # agent asks about the art
    assert "unit A" in say("skip that shelf, those are not mine")["reply"]
    assert say("hmm")["reply"] is None
    done = c.post(f"/api/sweep/{sid}/finish").json()
    assert done["books"] == 0 and "0 books" in done["summary"]               # skipped shelf is not in the claim




def test_turned_frames_are_stored_upright_and_marker_tip_stops(tmp_path, monkeypatch):
    # Real failures 10 Oct: shop frames arrived turned 90 degrees, and "I can't see a shelf marker" repeated all sweep
    monkeypatch.chdir(tmp_path); (tmp_path / "runs").mkdir()
    monkeypatch.setattr(S.vision, "analyze_frame", lambda b: (V.FrameOut(spines=[], items=[]), {}))
    c = TestClient(S.app)
    sid = c.post("/api/sweep/start", json={}).json()["sweep_id"]
    post = lambda img: c.post(f"/api/sweep/{sid}/frame", files={"file": ("f.jpg", _jpg(img), "image/jpeg")}).json()
    first = post(_stripes(3))
    assert "marker" in first["hint"]                                    # before any marker: the tip is useful
    upright = _with_marker(_stripes(), 0)
    post(cv2.rotate(upright, cv2.ROTATE_90_CLOCKWISE))                  # phone sends the frame turned
    saved = cv2.imread(str(tmp_path / S.SWEEPS[sid]["folder"] / "0001.jpg"))
    assert saved.shape[:2] == upright.shape[:2]                         # stored the right way up
    later = post(cv2.rotate(_stripes(8), cv2.ROTATE_90_CLOCKWISE))       # between markers, still held turned
    assert later["hint"] is None or "marker" not in later["hint"]       # no nagging once a marker was seen
    assert cv2.imread(str(tmp_path / S.SWEEPS[sid]["folder"] / "0002.jpg")).shape[:2] == upright.shape[:2]