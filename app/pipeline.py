"""Run all stages over a folder of keyframes and write claim_packet.json + report.html.
Every number in the packet comes from a stage output; totals come from app.totals (code, never a model)."""
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
from app.schema import (Book, BookPrice, BookStatus, ClaimPacket, Dimensions, Item, ItemPrice, ItemStatus,
                        Room, Sweep, UsedPrice)
from app.stages import dedup, item_price, measure, price, resolve, room, scale, vision
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


def _book_price(p, cls):
    if not p:
        return cls()
    fields = {k: p.get(k) for k in cls.model_fields if k in p}
    return cls(**fields)


def _measure(spine, markers, w, h):
    """Spine height/thickness on the nearest shelf marker's plane (perspective corrected). None without a marker."""
    box = vision.to_pixels(spine.box_2d, w, h)
    height, thick, marker_id = measure.spine_dims(markers, box, spine.orientation)
    return height, thick, marker_id


def unit_letter(marker_id):
    return chr(ord("A") + marker_id) if marker_id is not None and 0 <= marker_id < 10 else None


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


def _book_fields(book_id, frame_ref, position, spine, markers, w, h, r):
    """Everything about a book except its price. Returns (fields, status, wants_price)."""
    height, thick, marker_id = _measure(spine, markers, w, h)
    f = dict(id=book_id, shelf=unit_letter(marker_id), position=position, frame_ref=frame_ref, spine_text_raw=spine.text or None,
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


def _make_item(item_id, frame_ref, it, markers, w, h):
    box = vision.to_pixels(it.box_2d, w, h)
    m = (measure.nearest_marker(markers, box, config.SHELF_MARKER_CM)
         or measure.nearest_marker(markers, box, config.WALL_MARKER_CM))
    if m:
        width_cm, height_cm = measure.box_size_cm(box, scale.image_to_plane(m), "flat")  # (horizontal, vertical)
        dims = Dimensions(w=round(width_cm, 1), h=round(height_cm, 1))
    else:
        dims = Dimensions()
    status = ItemStatus.needs_appraisal if is_art(f"{it.category} {it.description}") else ItemStatus.range
    return Item(id=item_id, category=it.category, description=it.description or None,
                brand_model=it.visible_text or None, material=getattr(it, "material", "") or None,
                frame_ref=frame_ref, dimensions_cm=dims, status=status)


def _not_claimable(it, markers, w, h):
    """Reason an item must not be claimed, else None. Real failure (Neptunes v2): our printed ArUco sheets were
    listed as 'decor' items, and a book lying on the sofa was listed as an item (books are counted as books)."""
    text = f"{it.category} {it.description}".lower()
    if any(k in text for k in config.NOT_ITEM_WORDS):
        return "measuring marker"
    if re.fullmatch(r"\s*books?\s*", it.category.lower()):
        return "book (counted with the books, not as an item)"
    x1, y1, x2, y2 = vision.to_pixels(it.box_2d, w, h)
    for m in markers:
        cx, cy = m["corners_px"].mean(axis=0)
        side = m["size_cm"] * m["px_per_cm"]
        if x1 <= cx <= x2 and y1 <= cy <= y2 and (x2 - x1) * (y2 - y1) < 9 * side * side:
            return "measuring marker"
    return None


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
    spines = []  # (frame_ref, position, spine, markers, w, h, frame_name, voice_notes, frame_index)
    reg_frames, walls = [], []  # small grey copies + boxes for de-duplication; wall measurements for the room
    thick_factor = {}  # (frame index, position) -> overlap correction for spine thickness
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
        markers = scale.detect_markers(image)
        name = os.path.basename(path)
        fspines = res.spines
        if name.lower().startswith(config.ITEMS_ONLY_PREFIX):  # items-only frame: books here are outside the claim
            telemetry.setdefault("items_only_frames", []).append(name)
            fspines = []
        centre = _centre_index(fspines)
        notes = ov.get("book_notes", {}).get(name, [])
        spines += [(frame_ref, si + 1, sp, markers, w, h, name, notes if si == centre else [], len(reg_frames))
                   for si, sp in enumerate(fspines)]
        pboxes = [vision.to_pixels(sp.box_2d, w, h) for sp in fspines]
        for si, k in enumerate(measure.thickness_factors(pboxes, [sp.orientation for sp in fspines])):
            thick_factor[(len(reg_frames), si + 1)] = k
        small, s_ = dedup._gray_small(image)
        reg_frames.append({"image": small, "texts": [sp.text for sp in fspines],
                           "boxes": [tuple(v * s_ for v in b) for b in pboxes]})
        walls.append(room.measure_wall(markers, getattr(res, "wall", None), w, h))
        for it in res.items:
            why = _not_claimable(it, markers, w, h)
            if why:  # our own measuring markers and loose books are not contents to claim as items
                telemetry.setdefault("items_dropped", []).append(f"{it.category}: {why}")
                continue
            item = _make_item(f"i{len(packet.items) + 1:03d}", frame_ref, it, markers, w, h)
            if item.status == ItemStatus.needs_appraisal and name in ov.get("art_print", ()):
                item.status = ItemStatus.range  # policyholder says it is a print -> priced like any item
                item.description = f"{item.description or item.category} (print, per policyholder)"
            item.excluded_by_user = name in excluded
            packet.items.append(item)
    telemetry["vision_s"] = time.time() - t_stage

    # Stage 1b - the same book seen in two overlapping keyframes is counted once (Layer 9).
    t_stage = time.time()
    groups, registered = dedup.duplicate_groups(reg_frames)
    index = {(s_[8], s_[1] - 1): k for k, s_ in enumerate(spines)}
    keep = []
    for g in groups:
        members = [index[m] for m in g if m in index]
        # representative: a readable member with the longest text (best evidence), else the first seen
        best = max(members, key=lambda k: (_readable(spines[k][2]), len(spines[k][2].text), -k))
        keep.append(best)
    telemetry.update(spines_seen=len(spines), duplicates_removed=len(spines) - len(keep),
                     frame_pairs_registered=registered, dedup_s=round(time.time() - t_stage, 2))
    spines = [spines[k] for k in sorted(keep)]

    # Stage 2 - identify every readable spine in parallel (network-bound, so threads help).
    t_stage = time.time()
    readable = [i for i, sp in enumerate(spines) if _readable(sp[2]) and sp[6] not in excluded]
    with ThreadPoolExecutor(max_workers=config.IDENTIFY_WORKERS) as ex:
        found = dict(zip(readable, ex.map(_safe_resolve, [spines[i][2] for i in readable])))
    telemetry["identify_s"] = time.time() - t_stage

    drafts = []
    for i, (frame_ref, pos, sp, markers, w, h, name, notes, _fi) in enumerate(spines):
        fields, status, wants_price = _book_fields(f"b{i + 1:03d}", frame_ref, pos, sp, markers, w, h, found.get(i))
        if fields.get("spine_thickness_cm"):
            fields["spine_thickness_cm"] = round(fields["spine_thickness_cm"] * thick_factor.get((_fi, pos), 1.0), 1)
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

    # Room (Layer 10): wall markers + vision-located wall corners, measured in code. Same sweep, no extra pass.
    shelving = [it for it in packet.items if "shelv" in it.category.lower() or "bookcase" in it.category.lower()]
    packet.room = Room(**room.room_from_walls(room.best_per_wall(walls), shelving))
    telemetry["walls_measured"] = len(room.best_per_wall(walls))

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
