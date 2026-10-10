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



def test_cost_is_unknown_until_prices_are_set(monkeypatch):
    t = {"vision_tokens_in": 2_000_000, "vision_tokens_out": 500_000, "serpapi_searches": 10}
    assert PL.sweep_cost(t)["total_usd"] is None                      # never invent a cost
    monkeypatch.setattr(PL.config, "VISION_USD_PER_M_INPUT", 0.5)
    monkeypatch.setattr(PL.config, "VISION_USD_PER_M_OUTPUT", 2.0)
    monkeypatch.setattr(PL.config, "SERPAPI_USD_PER_SEARCH", 0.01)
    c = PL.sweep_cost(t)
    assert (c["vision_input_usd"], c["vision_output_usd"], c["search_usd"], c["total_usd"]) == (1.0, 1.0, 0.1, 2.1)



def test_voice_overrides_skip_shelf_first_edition_and_print(tmp_path, monkeypatch):
    centre = V.SpineOut(box_2d=[100, 450, 900, 550], orientation="upright", text="NANSEN IN NACHT UND EIS",
                        title="IN NACHT UND EIS", author="NANSEN", legibility="clear", cut_off=False)
    edge = V.SpineOut(box_2d=[100, 0, 900, 50], orientation="upright", text="NANSEN IN NACHT UND EIS",
                      title="IN NACHT UND EIS", author="NANSEN", legibility="clear", cut_off=False)
    art = V.ItemOut(box_2d=[0, 0, 500, 500], category="framed art", description="portrait", visible_text="")
    frame = V.FrameOut(spines=[edge, centre], items=[art])
    monkeypatch.setattr(PL.item_price, "price_item", lambda *a: ({"low": 500.0, "high": 900.0, "currency": "INR",
                                                                  "source": "t", "url": "u", "retrieved_at": "t"}, "range"))
    ov = {"book_notes": {"a.jpg": ["first edition"]}, "art_print": {"a.jpg"}}
    frames = tmp_path / "frames"; frames.mkdir()
    cv2.imwrite(str(frames / "a.jpg"), np.full((400, 600, 3), 255, np.uint8))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(PL.vision, "analyze_frame", lambda b: (frame, {"cache_hit": True}))
    monkeypatch.setattr(PL.resolve, "resolve_spine", lambda s: {"status": "identified", "confidence": 1.0, "volume": None,
        "match": {"title": "In Nacht und Eis", "authors": ["Fridtjof Nansen"], "published": "2012"}})
    monkeypatch.setattr(PL.price, "price_book", lambda *a, **k: {"status": "identified", "used": None, "notes": [],
        "replacement": {"amount": 300.0, "currency": "INR", "source": "A", "url": "x", "retrieved_at": "t", "converted": False}})
    packet, _ = PL.run_sweep(str(frames), "v1", "IN", "INR", overrides=ov)
    assert [b.status.value for b in packet.books] == ["identified", "needs_appraisal"]   # only the centre book
    assert packet.items[0].status.value == "range" and packet.totals.items_replacement_cost_low == 500

    packet2, _ = PL.run_sweep(str(frames), "v2", "IN", "INR", overrides={"excluded_frames": {"a.jpg"}})
    assert packet2.totals.book_count == 0 and all(b.excluded_by_user for b in packet2.books)



def test_overlapping_keyframes_are_counted_once(tmp_path, monkeypatch):
    import sys; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    from test_dedup import _shelf, _crop
    img, boxes = _shelf()
    crops = [_crop(img, boxes, 0, 1200), _crop(img, boxes, 800, 2000), _crop(img, boxes, 1600, 2400)]
    frames = tmp_path / "frames"; frames.mkdir()
    outs = []
    for k, c in enumerate(crops):
        cv2.imwrite(str(frames / f"{k}.png"), c["image"])                     # png: no compression artefacts
        h, w = c["image"].shape[:2]
        outs.append(V.FrameOut(spines=[V.SpineOut(box_2d=[round(y1 / h * 1000), round(x1 / w * 1000), round(y2 / h * 1000),
                                                         round(x2 / w * 1000)], orientation="upright", text="",
                                                  legibility="unreadable", cut_off=False)
                                       for x1, y1, x2, y2 in c["boxes"]], items=[]))
    it = iter(outs)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(PL.vision, "analyze_frame", lambda b: (next(it), {"cache_hit": True}))
    packet, _ = PL.run_sweep(str(frames), "d1", "IN", "INR")
    assert packet.telemetry["spines_seen"] == sum(len(c["boxes"]) for c in crops)
    assert abs(packet.totals.book_count - len(boxes)) <= 1                   # each real book once
    assert packet.telemetry["duplicates_removed"] > 0



def test_items_only_frame_counts_items_not_books(tmp_path, monkeypatch):
    # The sofa photo also shows shelves outside the claim: those books must not be counted
    frames = tmp_path / "frames"; frames.mkdir()
    img = np.full((400, 600, 3), 120, np.uint8)
    cv2.imwrite(str(frames / "f1.jpg"), img); cv2.imwrite(str(frames / "items_sofa.jpg"), img)
    book = V.SpineOut(box_2d=[100, 100, 900, 150], orientation="upright", text="", legibility="unreadable", cut_off=False)
    sofa = V.ItemOut(box_2d=[0, 0, 500, 500], category="sofa", description="red sofa", visible_text="")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(PL.vision, "analyze_frame", lambda b: (V.FrameOut(spines=[book, book], items=[sofa]), {"cache_hit": True}))
    monkeypatch.setattr(PL.item_price, "price_item", lambda *a: (None, "no price"))
    packet, _ = PL.run_sweep(str(frames), "io", "IN", "INR")
    assert packet.totals.book_count == 2                      # only f1.jpg's books
    assert sum(1 for it in packet.items if it.category == "sofa") == 2
    assert packet.telemetry["items_only_frames"] == ["items_sofa.jpg"]



def test_markers_and_loose_books_are_not_claimed_as_items():
    # Real failure (Neptunes v2): our ArUco sheets became 'decor' items; a book on the sofa became an item
    marker = [{"id": 0, "size_cm": 10.0, "px_per_cm": 10.0, "corners_px": np.array([[100, 100], [200, 100], [200, 200], [100, 200]], np.float32)}]
    item = lambda cat, desc, box: V.ItemOut(box_2d=box, category=cat, description=desc, visible_text="")
    assert PL._not_claimable(item("decor", "ArUco marker tag attached with tape", [0, 0, 999, 999]), [], 1000, 1000)
    assert PL._not_claimable(item("paper", "sheet", [80, 80, 220, 220]), marker, 1000, 1000) == "measuring marker"
    assert PL._not_claimable(item("book", "book on the seat", [0, 0, 100, 100]), [], 1000, 1000)
    assert PL._not_claimable(item("sofa", "red two-seater", [300, 300, 900, 900]), marker, 1000, 1000) is None


def test_same_item_category_in_two_photos_is_flagged_not_merged():
    from app import totals
    from app.schema import ClaimPacket, Sweep, Item, ItemStatus
    p = ClaimPacket(sweep=Sweep(id="d", captured_at="2026-10-10", country="IN", currency="INR"))
    p.items = [Item(id="i1", category="aquarium", frame_ref="frames/a.jpg", status=ItemStatus.range),
               Item(id="i2", category="Aquarium", frame_ref="frames/b.jpg", status=ItemStatus.range)]
    q = totals.build_review_queue(p)
    assert sum("also appears in another photo" in e.reason for e in q) == 2 and len(p.items) == 2