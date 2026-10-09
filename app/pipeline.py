import argparse
import os
import re
import shutil
import time
from datetime import datetime, timezone

import cv2

from app import config, serp
from app.report import write_report
from app.schema import (Book, BookPrice, BookStatus, ClaimPacket, Dimensions, Item, ItemStatus,
                        Sweep, UsedPrice)
from app.stages import price, resolve, scale, vision
from app.totals import finalize

ART_WORDS = ("art", "artwork", "painting", "portrait", "poster", "print", "picture", "sculpture", "framed")
IMAGE_EXT = (".jpg", ".jpeg", ".png")


def is_art(text):
    """Whole-word match, so 'smart speaker' or 'printer' are NOT art."""
    words = set(re.findall(r"[a-z]+", (text or "").lower()))
    return any(w in words for w in ART_WORDS)

ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
         "xi": 11, "xii": 12, "xiii": 13, "xiv": 14, "xv": 15, "xvi": 16, "xvii": 17, "xviii": 18, "xix": 19, "xx": 20}


def clean_volume(v):
    """Keep a volume only if it looks like one: 1..MAX_VOLUME_NUMBER or a roman numeral. '30017' is a series number."""
    v = (v or "").strip().rstrip(".")
    if v.isdigit() and 1 <= int(v) <= config.MAX_VOLUME_NUMBER:
        return v
    return v.upper() if v.lower() in ROMAN else None


def clean_authors(authors):
    """Drop repeats of the same person: case/accents ('SVEN HEDIN'), word order ('Eco Umberto'),
    or a fuller form of a name already listed ('Sven Anders Hedin')."""
    kept, out = [], []
    for a in authors or []:
        words = set(resolve.norm(a).split())
        if not words or any(words <= k or k <= words for k in kept):
            continue
        kept.append(words)
        out.append(a)
    return out


def copy_age_reason(cues):
    """Appraisal from evidence about THIS copy (what is visible on the spine), never from the work's catalogue year."""
    cues = [c for c in cues if c in config.AGE_CUES]
    strong = [c for c in cues if c in config.ANTIQUE_STRONG_CUES]
    if strong or len(cues) >= config.ANTIQUE_MIN_CUES:
        return f"antiquarian appearance on spine ({', '.join(cues)}); not auto-priced"
    return None


def _year(text):
    m = re.search(r"\b(1[5-9]\d\d|20\d\d)\b", text or "")
    return int(m.group(1)) if m else None

def _cm_per_px(image):
    """Simple scale from the frame's shelf marker (IDs 0-9). None if no shelf marker is visible."""
    shelf = [m for m in scale.detect_markers(image) if m["size_cm"] == config.SHELF_MARKER_CM]
    return (1.0 / shelf[0]["px_per_cm"]) if shelf else None


def _book_price(p, cls):
    if not p:
        return cls()
    fields = {k: p.get(k) for k in cls.model_fields if k in p}
    return cls(**fields)


def _make_book(book_id, frame_ref, position, spine, cm_per_px, w, h, market, telemetry, price_budget):
    x1, y1, x2, y2 = vision.to_pixels(spine.box_2d, w, h)
    long_px, short_px = (x2 - x1, y2 - y1) if spine.orientation == "flat" else (y2 - y1, x2 - x1)
    height = round(long_px * cm_per_px, 1) if cm_per_px else None
    thick = round(short_px * cm_per_px, 1) if cm_per_px else None
    base = dict(id=book_id, shelf=None, position=position, frame_ref=frame_ref, spine_text_raw=spine.text or None,
                orientation=spine.orientation, spine_height_cm=height, spine_thickness_cm=thick)

    if not spine.text.strip() or spine.legibility == "unreadable":
        return Book(**base, status=BookStatus.unidentified)

    t0 = time.time()
    r = resolve.resolve_spine(spine.model_dump())
    telemetry["identify_s"] += time.time() - t0
    if r["status"] != "identified":
        return Book(**base, status=BookStatus.unidentified, id_confidence=r["confidence"])

    m = r["match"]
    authors = clean_authors(m.get("authors"))
    volume = clean_volume(r.get("volume"))
    age_cues = [c for c in getattr(spine, "age_cues", []) if c in config.AGE_CUES]
    book = dict(base, title=m["title"], author=", ".join(authors[:2]) or None, age_cues=age_cues,
                edition=f"vol. {volume}" if volume else None, id_confidence=r["confidence"], review_notes=[])
    if r.get("volume") and not volume:
        book["review_notes"].append(f"Spine number '{r['volume']}' not used as a volume (looks like a series number)")

    reason = copy_age_reason(age_cues)
    if reason:
        book["review_notes"].append(f"Needs appraisal: {reason}")
        return Book(**book, status=BookStatus.needs_appraisal)
    year = _year(m.get("published"))
    if year and year < config.APPRAISAL_PUBLISHED_BEFORE:
        book["review_notes"].append(f"Catalogue year {year} is for the work, not this copy; no age cues on the spine, "
                                    "so priced as a current edition. Confirm it is not an old printing")

    if price_budget["left"] <= 0:
        book["review_notes"].append(config.NOTE_NOT_PRICED)
        return Book(**book, status=BookStatus.identified)
    price_budget["left"] -= 1
    t0 = time.time()
    # published=None on purpose: the catalogue year describes the work/an edition, not the copy on the shelf
    pr = price.price_book(m["title"], authors[0] if authors else "", market, spine_text=spine.text, published=None)
    telemetry["price_s"] += time.time() - t0
    if pr["status"] == "needs_appraisal":
        book["review_notes"].append(f"Needs appraisal: {pr['reason']}")
        return Book(**book, status=BookStatus.needs_appraisal)
    return Book(**book, status=BookStatus.identified,
                replacement_cost=_book_price(pr["replacement"], BookPrice),
                used_value=_book_price(pr["used"], UsedPrice))

def _make_item(item_id, frame_ref, it, cm_per_px, w, h):
    x1, y1, x2, y2 = vision.to_pixels(it.box_2d, w, h)
    dims = Dimensions(w=round((x2 - x1) * cm_per_px, 1), h=round((y2 - y1) * cm_per_px, 1)) if cm_per_px else Dimensions()
    return Item(id=item_id, category=it.category, description=it.description or None,
                brand_model=it.visible_text or None, frame_ref=frame_ref, dimensions_cm=dims,
                status=ItemStatus.needs_appraisal if is_art(f"{it.category} {it.description}") else ItemStatus.range)  # pricing: Layer 11


def run_sweep(frames_dir, sweep_id, country, currency, device=None, price_limit=1000):
    out_dir = os.path.join("runs", sweep_id)
    frames_out = os.path.join(out_dir, "frames")
    os.makedirs(frames_out, exist_ok=True)
    telemetry = {"vision_s": 0.0, "identify_s": 0.0, "price_s": 0.0, "vision_tokens_in": 0,
                 "vision_tokens_out": 0, "vision_calls": 0, "vision_cache_hits": 0, "frames_failed": []}
    price_budget = {"left": price_limit}
    started = time.time()
    packet = ClaimPacket(sweep=Sweep(id=sweep_id, captured_at=datetime.now(timezone.utc).isoformat(),
                                     device=device, country=country, currency=currency))
    paths = sorted(os.path.join(frames_dir, n) for n in os.listdir(frames_dir) if n.lower().endswith(IMAGE_EXT))
    # NOTE: each keyframe is treated as showing different books. Cross-frame de-duplication is Layer 9.
    for fi, path in enumerate(paths):
        frame_ref = f"frames/{fi:04d}_{os.path.basename(path)}"
        shutil.copy(path, os.path.join(out_dir, frame_ref))  # every frame_ref opens
        image = cv2.imread(path)
        h, w = image.shape[:2]
        t0 = time.time()
        with open(path, "rb") as f:
            res, tel = vision.analyze_frame(f.read())
        telemetry["vision_s"] += time.time() - t0
        telemetry["vision_cache_hits" if tel.get("cache_hit") else "vision_calls"] += 1
        tokens = tel.get("tokens") or {}
        telemetry["vision_tokens_in"] += tokens.get("input") or 0
        telemetry["vision_tokens_out"] += tokens.get("output") or 0
        if res is None:
            telemetry["frames_failed"].append({"frame": frame_ref, "errors": tel.get("attempts", [])[-2:]})
            continue
        cm_per_px = _cm_per_px(image)
        for si, spine in enumerate(res.spines):
            packet.books.append(_make_book(f"b{len(packet.books) + 1:03d}", frame_ref, si + 1, spine, cm_per_px,
                                           w, h, country, telemetry, price_budget))
        for it in res.items:
            packet.items.append(_make_item(f"i{len(packet.items) + 1:03d}", frame_ref, it, cm_per_px, w, h))

    packet.sweep.duration_s = None  # filled by the live app from the real sweep
    telemetry.update({k: round(v, 2) for k, v in telemetry.items() if isinstance(v, float)})
    telemetry.update(serpapi_searches=serp.stats["searches"], serpapi_cache_hits=serp.stats["cache_hits"],
                     total_s=round(time.time() - started, 2))
    packet.telemetry = telemetry
    finalize(packet)
    with open(os.path.join(out_dir, "claim_packet.json"), "w", encoding="utf-8") as f:
        f.write(packet.model_dump_json(indent=2))
    write_report(packet, os.path.join(out_dir, "report.html"))
    return packet, out_dir


def main():
    ap = argparse.ArgumentParser(description="Build a claim packet from a folder of keyframes")
    ap.add_argument("frames_dir")
    ap.add_argument("--sweep-id", default=datetime.now().strftime("sweep_%Y%m%d_%H%M%S"))
    ap.add_argument("--country", default=config.COUNTRY)
    ap.add_argument("--currency", default=config.CURRENCY)
    ap.add_argument("--price-limit", type=int, default=1000, help="price at most N books (saves search quota)")
    a = ap.parse_args()
    packet, out_dir = run_sweep(a.frames_dir, a.sweep_id, a.country, a.currency, price_limit=a.price_limit)
    t = packet.totals
    print(f"wrote {out_dir}: {t.book_count} books ({t.books_identified} identified, "
          f"{t.books_unidentified} unidentified), {len(packet.items)} items, "
          f"{len(packet.review_queue)} review entries")


if __name__ == "__main__":
    main()