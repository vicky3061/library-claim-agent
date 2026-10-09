import argparse
import os
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import cv2

from app import config, http_client, serp
from app.report import write_report
from app.schema import (Book, BookPrice, BookStatus, ClaimPacket, Dimensions, Item, ItemPrice, ItemStatus,Sweep, UsedPrice)
from app.stages import item_price, price, resolve, scale, vision
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

def sweep_cost(t):
    """Cost per sweep from measured usage x list prices in config (USD). None for a price we have not set."""
    def usd(n, rate):
        return None if rate is None else round(n * rate, 4)
    parts = {"vision_input_usd": usd(t.get("vision_tokens_in", 0) / 1e6, config.VISION_USD_PER_M_INPUT),
             "vision_output_usd": usd(t.get("vision_tokens_out", 0) / 1e6, config.VISION_USD_PER_M_OUTPUT),
             "search_usd": usd(t.get("serpapi_searches", 0), config.SERPAPI_USD_PER_SEARCH)}
    known = [v for v in parts.values() if v is not None]
    return {**parts, "total_usd": round(sum(known), 4) if len(known) == len(parts) else None,
            "catalogue_and_fx_usd": 0.0, "price_basis": config.PRICE_BASIS}

def _cm_per_px(image):
    """Simple scale from the frame's shelf marker (IDs 0-9). None if no shelf marker is visible."""
    shelf = [m for m in scale.detect_markers(image) if m["size_cm"] == config.SHELF_MARKER_CM]
    return (1.0 / shelf[0]["px_per_cm"]) if shelf else None


def _book_price(p, cls):
    if not p:
        return cls()
    fields = {k: p.get(k) for k in cls.model_fields if k in p}
    return cls(**fields)


def _measure(spine, cm_per_px, w, h):
    x1, y1, x2, y2 = vision.to_pixels(spine.box_2d, w, h)
    long_px, short_px = (x2 - x1, y2 - y1) if spine.orientation == "flat" else (y2 - y1, x2 - x1)
    if not cm_per_px:
        return None, None
    return round(long_px * cm_per_px, 1), round(short_px * cm_per_px, 1)


def _readable(spine):
    return bool(spine.text.strip()) and spine.legibility != "unreadable"


def _safe_resolve(spine):
    try:
        return resolve.resolve_spine(spine.model_dump())
    except Exception as e:  # one bad lookup must not sink the whole packet
        return {"status": "unidentified", "confidence": None, "reason": "catalogue lookup failed", "errors": [str(e)]}


def _safe_price(args):
    title, author, market, spine_text = args
    try:
        # published=None on purpose: the catalogue year describes the work/an edition, not the copy on the shelf
        return price.price_book(title, author, market, spine_text=spine_text, published=None)
    except Exception as e:
        return {"status": "error", "reason": str(e), "replacement": None, "used": None, "notes": []}


def _book_fields(book_id, frame_ref, position, spine, cm_per_px, w, h, r):
    """Everything about a book except its price. Returns (fields, status, wants_price)."""
    height, thick = _measure(spine, cm_per_px, w, h)
    f = dict(id=book_id, shelf=None, position=position, frame_ref=frame_ref, spine_text_raw=spine.text or None,
             orientation=spine.orientation, spine_height_cm=height, spine_thickness_cm=thick, review_notes=[])
    if r is None:  # not readable: counted, measured, never guessed
        return f, BookStatus.unidentified, False
    if r["status"] != "identified":
        f["id_confidence"] = r.get("confidence")
        if r.get("reason") == "catalogue lookup failed":
            f["review_notes"].append("Catalogue services unreachable for this spine; retry before closing the claim")
        return f, BookStatus.unidentified, False

    m = r["match"]
    authors = clean_authors(m.get("authors"))
    volume = clean_volume(r.get("volume"))
    age_cues = [c for c in getattr(spine, "age_cues", []) if c in config.AGE_CUES]
    f.update(title=m["title"], author=", ".join(authors[:2]) or None, age_cues=age_cues,
             edition=f"vol. {volume}" if volume else None, id_confidence=r["confidence"])
    if r.get("volume") and not volume:
        f["review_notes"].append(f"Spine number '{r['volume']}' not used as a volume (looks like a series number)")
    reason = copy_age_reason(age_cues)
    if reason:
        f["review_notes"].append(f"Needs appraisal: {reason}")
        return f, BookStatus.needs_appraisal, False
    year = _year(m.get("published"))
    if year and year < config.APPRAISAL_PUBLISHED_BEFORE:
        f["review_notes"].append(f"Catalogue year {year} is for the work, not this copy; no age cues on the spine, "
                                 "so priced as a current edition. Confirm it is not an old printing")
    return f, BookStatus.identified, True

def _safe_item_price(args):
    category, description, brand_model, market = args
    try:
        return item_price.price_item(category, description, brand_model, market)
    except Exception as e:
        return None, f"pricing failed: {e}"
    
def _make_item(item_id, frame_ref, it, cm_per_px, w, h):
    x1, y1, x2, y2 = vision.to_pixels(it.box_2d, w, h)
    dims = Dimensions(w=round((x2 - x1) * cm_per_px, 1), h=round((y2 - y1) * cm_per_px, 1)) if cm_per_px else Dimensions()
    status = ItemStatus.needs_appraisal if is_art(f"{it.category} {it.description}") else ItemStatus.range
    return Item(id=item_id, category=it.category, description=it.description or None,
                brand_model=it.visible_text or None, material=getattr(it, "material", "") or None,
                frame_ref=frame_ref, dimensions_cm=dims, status=status)

def _centre_index(spines):
    """The spine nearest the centre of the frame: the book the user is pointing the camera at."""
    if not spines:
        return None
    def dist(sp):
        y0, x0, y1, x1 = sp.box_2d
        return ((x0 + x1) / 2 - 500) ** 2 + ((y0 + y1) / 2 - 500) ** 2
    return min(range(len(spines)), key=lambda i: dist(spines[i]))


def run_sweep(frames_dir, sweep_id, country, currency, device=None, price_limit=1000, overrides=None):
    """overrides (from voice corrections), keyed by frame file name:
    excluded_frames: {name}  -> books/items there are excluded_by_user ("skip that shelf")
    book_notes: {name: [note]} -> the centre book gets the note ("first edition" -> appraisal)
    art_print: {name} / art_original: {name} -> the user's answer to "original or print?" """
    out_dir = os.path.join("runs", sweep_id)
    frames_out = os.path.join(out_dir, "frames")
    os.makedirs(frames_out, exist_ok=True)
    telemetry = {"vision_s": 0.0, "identify_s": 0.0, "price_s": 0.0, "vision_tokens_in": 0,
                 "vision_tokens_out": 0, "vision_calls": 0, "vision_cache_hits": 0, "frames_failed": []}
    ov = overrides or {}
    excluded = set(ov.get("excluded_frames", ()))
    started = time.time()
    packet = ClaimPacket(sweep=Sweep(id=sweep_id, captured_at=datetime.now(timezone.utc).isoformat(),
                                     device=device, country=country, currency=currency))
    paths = sorted(os.path.join(frames_dir, n) for n in os.listdir(frames_dir) if n.lower().endswith(IMAGE_EXT))

    # Stage 1 - vision, frame by frame (free-tier quota: one call at a time).
    # NOTE: each keyframe is treated as showing different books. Cross-frame de-duplication is Layer 9.
    spines = []  # (frame_ref, position, spine, cm_per_px, w, h, frame_name, voice_notes)
    t_stage = time.time()
    for fi, path in enumerate(paths):
        frame_ref = f"frames/{fi:04d}_{os.path.basename(path)}"
        shutil.copy(path, os.path.join(out_dir, frame_ref))  # every frame_ref opens
        image = cv2.imread(path)
        h, w = image.shape[:2]
        with open(path, "rb") as f:
            res, tel = vision.analyze_frame(f.read())
        telemetry["vision_cache_hits" if tel.get("cache_hit") else "vision_calls"] += 1
        tokens = tel.get("tokens") or {}
        telemetry["vision_tokens_in"] += tokens.get("input") or 0
        telemetry["vision_tokens_out"] += tokens.get("output") or 0
        if res is None:
            telemetry["frames_failed"].append({"frame": frame_ref, "errors": tel.get("attempts", [])[-2:]})
            continue
        cm_per_px = _cm_per_px(image)
        name = os.path.basename(path)
        centre = _centre_index(res.spines)
        notes = ov.get("book_notes", {}).get(name, [])
        spines += [(frame_ref, si + 1, sp, cm_per_px, w, h, name, notes if si == centre else [])
                   for si, sp in enumerate(res.spines)]
        for it in res.items:
            item = _make_item(f"i{len(packet.items) + 1:03d}", frame_ref, it, cm_per_px, w, h)
            if item.status == ItemStatus.needs_appraisal and name in ov.get("art_print", ()):
                item.status = ItemStatus.range  # policyholder says it is a print -> priced like any item
                item.description = f"{item.description or item.category} (print, per policyholder)"
            item.excluded_by_user = name in excluded
            packet.items.append(item)
    telemetry["vision_s"] = time.time() - t_stage

    # Stage 2 - identify every readable spine in parallel (network-bound, so threads help).
    t_stage = time.time()
    readable = [i for i, s in enumerate(spines) if _readable(s[2]) and s[6] not in excluded]
    with ThreadPoolExecutor(max_workers=config.IDENTIFY_WORKERS) as ex:
        found = dict(zip(readable, ex.map(_safe_resolve, [spines[i][2] for i in readable])))
    telemetry["identify_s"] = time.time() - t_stage

    drafts = []
    for i, (frame_ref, pos, sp, cm_per_px, w, h, name, notes) in enumerate(spines):
        fields, status, wants_price = _book_fields(f"b{i + 1:03d}", frame_ref, pos, sp, cm_per_px, w, h, found.get(i))
        if name in excluded:
            fields["excluded_by_user"] = True  # "skip that shelf, those are not mine": not priced, not counted
            wants_price = False
        elif notes:
            fields["review_notes"].append(f"Policyholder said '{', '.join(notes)}' with this book in the centre of the "
                                          "frame; confirm it is the right book")
            # Every phrase the voice parser accepts here (first edition, signed, rare...) means "do not auto-price".
            # Not added to the spine keyword list on purpose: a title like "Rare Earth" must not trigger appraisal.
            if status == BookStatus.identified:
                fields["review_notes"].append(f"Needs appraisal: policyholder said '{', '.join(notes)}'")
                status, wants_price = BookStatus.needs_appraisal, False
        drafts.append([fields, status, wants_price, sp])

    # Stage 3 - price in parallel. Same title+author is priced once (saves quota, avoids duplicate cache writes).
    t_stage = time.time()
    jobs = {}
    for d in drafts:
        fields, _, wants_price, sp = d
        if not wants_price:
            continue
        key = (fields["title"], (fields["author"] or "").split(", ")[0], country, sp.text)
        if key not in jobs and len(jobs) >= price_limit:
            fields["review_notes"].append(config.NOTE_NOT_PRICED)
            d[2] = False
            continue
        jobs.setdefault(key, None)
        d.append(key)
    with ThreadPoolExecutor(max_workers=config.PRICE_WORKERS) as ex:
        priced = dict(zip(jobs, ex.map(_safe_price, list(jobs))))
    telemetry["price_s"] = time.time() - t_stage

    for d in drafts:
        fields, status, wants_price, sp = d[:4]
        if wants_price:
            pr = priced[d[4]]
            if pr["status"] == "needs_appraisal":
                fields["review_notes"].append(f"Needs appraisal: {pr['reason']}")
                status = BookStatus.needs_appraisal
            else:
                if pr["status"] == "error":
                    fields["review_notes"].append(f"Pricing failed ({pr['reason'][:80]}); excluded from totals")
                fields["replacement_cost"] = _book_price(pr["replacement"], BookPrice)
                fields["used_value"] = _book_price(pr["used"], UsedPrice)
        packet.books.append(Book(**fields, status=status))

    # Stage 4 - non-book items (art already went to appraisal). One search per distinct item, local market only.
    t_stage = time.time()
    todo = [it for it in packet.items if it.status == ItemStatus.range and not it.excluded_by_user]
    keys = list(dict.fromkeys((it.category, it.description or "", it.brand_model or "", country) for it in todo))[:price_limit]
    with ThreadPoolExecutor(max_workers=config.PRICE_WORKERS) as ex:
        item_results = dict(zip(keys, ex.map(_safe_item_price, keys)))
    for it in todo:
        found, how = item_results.get((it.category, it.description or "", it.brand_model or "", country), (None, None))
        if found:
            it.replacement_cost = ItemPrice(**found)
            it.status = ItemStatus.priced if how == "priced" else ItemStatus.range
    telemetry["item_price_s"] = time.time() - t_stage

    packet.sweep.duration_s = None  # filled by the live app from the real sweep
    telemetry.update({k: round(v, 2) for k, v in telemetry.items() if isinstance(v, float)})
    telemetry.update(serpapi_searches=serp.stats["searches"], serpapi_cache_hits=serp.stats["cache_hits"],
                     catalogue_calls=http_client.cache_stats["calls"], catalogue_cache_hits=http_client.cache_stats["cache_hits"],
                     total_s=round(time.time() - started, 2))
    telemetry["cost"] = sweep_cost(telemetry)
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