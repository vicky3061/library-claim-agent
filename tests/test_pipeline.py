import json, os
import cv2, numpy as np
from app import pipeline as PL
from app.stages import vision as V

FRAME = V.FrameOut(
    spines=[V.SpineOut(box_2d=[100, 100, 900, 150], orientation="upright", text="ATOMIC HABITS JAMES CLEAR",
                       title="ATOMIC HABITS", author="JAMES CLEAR", legibility="clear", cut_off=False),
            V.SpineOut(box_2d=[100, 200, 900, 240], orientation="upright", text="", legibility="unreadable", cut_off=False)],
    items=[V.ItemOut(box_2d=[0, 0, 500, 500], category="framed art", description="portrait", visible_text="")])

def test_end_to_end_packet(tmp_path, monkeypatch):
    frames = tmp_path / "frames"; frames.mkdir()
    cv2.imwrite(str(frames / "a.jpg"), np.full((400, 600, 3), 255, np.uint8))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(PL.vision, "analyze_frame", lambda b: (FRAME, {"cache_hit": False, "tokens": {"input": 10, "output": 5}}))
    monkeypatch.setattr(PL.resolve, "resolve_spine", lambda s: {"status": "identified", "confidence": 1.0, "volume": None,
        "match": {"title": "Atomic Habits", "authors": ["James Clear"], "published": "2018"}})
    monkeypatch.setattr(PL.price, "price_book", lambda *a, **k: {"status": "identified",
        "replacement": {"amount": 472.0, "currency": "INR", "source": "Amazon", "url": "u", "retrieved_at": "t", "converted": False},
        "used": None, "notes": []})
    packet, out = PL.run_sweep(str(frames), "t1", "IN", "INR")
    assert packet.totals.book_count == 2 and packet.totals.books_identified == 1
    assert packet.totals.books_replacement_cost == 472.0
    assert packet.items[0].status.value == "needs_appraisal"
    assert all(os.path.exists(os.path.join(out, b.frame_ref)) for b in packet.books)  # every frame_ref opens
    data = json.load(open(os.path.join(out, "claim_packet.json")))
    assert data["books"][1]["title"] is None and data["books"][1]["status"] == "unidentified"
    assert os.path.exists(os.path.join(out, "report.html"))
    assert packet.telemetry["vision_calls"] == 1


def test_art_is_whole_word_only():
    assert PL.is_art("framed art") and PL.is_art("oil painting") and PL.is_art("Poster")
    assert not PL.is_art("smart speaker") and not PL.is_art("printer") and not PL.is_art("cartridge")

def test_volume_author_and_age_rules():
    assert PL.clean_volume("30017") is None and PL.clean_volume("ii") == "II" and PL.clean_volume("2") == "2"
    assert PL.clean_authors(["Sven Hedin", "SVEN HEDIN", "Umberto Eco"]) == ["Sven Hedin", "Umberto Eco"]
    assert PL.copy_age_reason(["blackletter"])                       # one strong cue is enough
    assert PL.copy_age_reason(["cloth_binding"]) is None              # a cloth hardcover alone is not antique
    assert PL.copy_age_reason(["cloth_binding", "gilt_lettering"])    # two cues together
    assert PL.copy_age_reason(["looks_expensive"]) is None            # unknown cues are ignored
    assert PL.clean_authors(["Sven Hedin", "Sven Anders Hedin", "Eco Umberto", "Umberto Eco"]) == ["Sven Hedin", "Eco Umberto"]


def _run(tmp_path, monkeypatch, frame, price_limit=1000, published="2018"):
    frames = tmp_path / "frames"; frames.mkdir(exist_ok=True)
    cv2.imwrite(str(frames / "a.jpg"), np.full((400, 600, 3), 255, np.uint8))
    monkeypatch.chdir(tmp_path)
    calls = []
    monkeypatch.setattr(PL.vision, "analyze_frame", lambda b: (frame, {"cache_hit": True}))
    monkeypatch.setattr(PL.resolve, "resolve_spine", lambda s: {"status": "identified", "confidence": 1.0,
        "volume": s.get("volume"), "match": {"title": "In Nacht und Eis", "authors": ["Fridtjof Nansen"], "published": published}})
    def fake_price(*a, **k):
        calls.append(k)
        return {"status": "identified", "used": None, "notes": [], "replacement": {"amount": 2973.0, "currency": "INR",
                "source": "Amazon", "url": "https://amazon.in/dp/X", "retrieved_at": "t", "converted": False}}
    monkeypatch.setattr(PL.price, "price_book", fake_price)
    packet, _ = PL.run_sweep(str(frames), "t2", "IN", "INR", price_limit=price_limit)
    return packet, calls


def _spine(volume="", cues=()):
    return V.SpineOut(box_2d=[100, 100, 900, 150], orientation="upright", text="NANSEN IN NACHT UND EIS",
                      title="IN NACHT UND EIS", author="NANSEN", volume=volume, legibility="clear", cut_off=False,
                      age_cues=list(cues))


def test_antique_spine_goes_to_appraisal_without_pricing(tmp_path, monkeypatch):
    packet, calls = _run(tmp_path, monkeypatch, V.FrameOut(spines=[_spine(cues=["blackletter"])], items=[]))
    assert packet.books[0].status.value == "needs_appraisal" and calls == []
    assert packet.totals.books_replacement_cost == 0


def test_skipped_pricing_is_not_reported_as_not_found(tmp_path, monkeypatch):
    packet, _ = _run(tmp_path, monkeypatch, V.FrameOut(spines=[_spine()], items=[]), price_limit=0)
    reasons = [r.reason for r in packet.review_queue]
    assert any("price limit" in r for r in reasons) and not any("No price found" in r for r in reasons)
    assert packet.totals.shelf_run_m is None  # no marker -> unknown, not 0.0


def test_old_work_year_is_not_copy_evidence_and_shared_listing_flagged(tmp_path, monkeypatch):
    frame = V.FrameOut(spines=[_spine("I"), _spine("II")], items=[])
    packet, calls = _run(tmp_path, monkeypatch, frame, published="1897")
    assert all(k["published"] is None for k in calls)                      # catalogue year never passed as copy age
    assert [b.status.value for b in packet.books] == ["identified", "identified"]
    reasons = [r.reason for r in packet.review_queue]
    assert any("Catalogue year 1897" in r for r in reasons)
    assert sum("Same listing priced for 2 books" in r for r in reasons) == 2



def test_same_book_is_priced_once(tmp_path, monkeypatch):
    frame = V.FrameOut(spines=[_spine(), _spine()], items=[])   # identical spines, e.g. two copies
    packet, calls = _run(tmp_path, monkeypatch, frame)
    assert len(calls) == 1 and packet.totals.books_replacement_cost == 2 * 2973.0




def test_items_get_sourced_range_and_art_is_not_priced(tmp_path, monkeypatch):
    frame = V.FrameOut(spines=[], items=[V.ItemOut(box_2d=[0, 0, 500, 500], category="shelving", description="bookcase", visible_text=""),
                                         V.ItemOut(box_2d=[0, 0, 500, 500], category="framed art", description="oil painting", visible_text="")])
    asked = []
    def fake_item(category, description, brand_model, market):
        asked.append(category)
        return {"low": 3000.0, "high": 5000.0, "currency": "INR", "source": "test", "url": "u", "retrieved_at": "t"}, "range"
    monkeypatch.setattr(PL.item_price, "price_item", fake_item)
    packet, _ = _run(tmp_path, monkeypatch, frame)
    assert asked == ["shelving"]                                   # art never sent to pricing
    assert packet.totals.items_replacement_cost_low == 3000 and packet.totals.items_replacement_cost_high == 5000
    assert packet.totals.items_needs_appraisal == 1