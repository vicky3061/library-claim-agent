"""Totals and review queue, computed in code from the lines.

Brief: "Totals are computed in code from the lines, never written by a language model."
This module never calls a model. It only reads the packet's lines.
"""
from __future__ import annotations

from app import config
from app.schema import BookStatus, ClaimPacket, ItemStatus, ReviewEntry, Totals


def _round(x: float) -> float:
    return round(x, 2)


def compute_totals(p: ClaimPacket) -> Totals:
    t = Totals()
    books = [b for b in p.books if not b.excluded_by_user]
    items = [i for i in p.items if not i.excluded_by_user]

    t.book_count = len(books)
    t.books_identified = sum(b.status == BookStatus.identified for b in books)
    t.books_unidentified = sum(b.status == BookStatus.unidentified for b in books)
    t.books_needs_appraisal = sum(b.status == BookStatus.needs_appraisal for b in books)

    # Shelf run = summed thickness of upright books. Flat stacks do not consume run.
    measured = [b.spine_thickness_cm for b in books
                if b.spine_thickness_cm is not None and b.orientation != "flat"]
    t.shelf_run_m = _round(sum(measured) / 100.0) if measured else None  # unknown is None, not 0

    excluded = 0
    repl = used = 0.0
    for b in books:
        if b.status == BookStatus.needs_appraisal:
            excluded += 1
            continue
        has_any = False
        if b.replacement_cost.amount is not None:
            repl += b.replacement_cost.amount
            has_any = True
        if b.used_value.amount is not None:
            used += b.used_value.amount
            has_any = True
        if not has_any:
            excluded += 1
    t.books_replacement_cost = _round(repl)
    t.books_used_value = _round(used)

    lo = hi = 0.0
    for i in items:
        if i.status == ItemStatus.needs_appraisal or i.replacement_cost.low is None:
            excluded += 1
            if i.status == ItemStatus.needs_appraisal:
                t.items_needs_appraisal += 1
            continue
        lo += i.replacement_cost.low
        hi += i.replacement_cost.high if i.replacement_cost.high is not None else i.replacement_cost.low
    t.items_replacement_cost_low = _round(lo)
    t.items_replacement_cost_high = _round(hi)

    t.excluded_from_totals = excluded
    return t


def build_review_queue(p: ClaimPacket) -> list[ReviewEntry]:
    """Rule-based: every line we are not confident in, with the reason."""
    q: list[ReviewEntry] = []

    def add(ref, reason):
        q.append(ReviewEntry(ref_id=ref, reason=reason))

    for b in p.books:
        if b.excluded_by_user:
            continue
        if b.status == BookStatus.needs_appraisal:
            add(b.id, "Needs human appraisal (rare, signed, old or high value); not auto-priced")
        elif b.status == BookStatus.unidentified:
            add(b.id, "Spine not readable or no confident catalogue match; title left blank")
        else:
            if b.id_confidence is not None and b.id_confidence < config.ID_REVIEW_THRESHOLD:
                add(b.id, f"Identification confidence {b.id_confidence:.2f} below {config.ID_REVIEW_THRESHOLD}")
            unpriced = b.replacement_cost.amount is None and b.used_value.amount is None
            if unpriced and config.NOTE_NOT_PRICED not in b.review_notes:
                add(b.id, "No price found in any market; excluded from totals")
            if b.replacement_cost.converted or b.used_value.converted:
                add(b.id, "Price converted from another market's currency")
        if b.spine_height_cm is None:
            add(b.id, "Spine not measured (no metric scale in frame)")
        for note in b.review_notes:  # reasons recorded by the stage that made the line
            add(b.id, note)

    # One listing priced for several books (e.g. vol. I and vol. II) may be a set: double counting risk.
    by_url = {}
    for b in p.books:
        if not b.excluded_by_user and b.replacement_cost.url:
            by_url.setdefault(b.replacement_cost.url, []).append(b.id)
    for url, ids in by_url.items():
        if len(ids) > 1:
            for ref in ids:
                add(ref, f"Same listing priced for {len(ids)} books ({', '.join(ids)}); check it is not a multi-volume set")

    for i in p.items:
        if i.excluded_by_user:
            continue
        if i.status == ItemStatus.needs_appraisal:
            add(i.id, "Art/portrait or high-value item: needs appraisal")
        elif i.replacement_cost.low is None:
            add(i.id, "No sourced price found; excluded from totals")
        elif i.status == ItemStatus.range:
            add(i.id, "Brand/model unknown; priced as a sourced range")

        # The same object photographed twice would be claimed twice: flag, never auto-merge (two real chairs exist too)
    by_cat = {}
    for i in p.items:
        if not i.excluded_by_user:
            by_cat.setdefault(i.category.strip().lower(), []).append(i)
    for cat, its in by_cat.items():
        if len(its) > 1 and len({i.frame_ref for i in its}) > 1:
            for i in its:
                others = ", ".join(o.id for o in its if o is not i)
                add(i.id, f"'{cat}' also appears in another photo ({others}); confirm it is a separate object, "
                          "not the same one seen twice")

    if p.room.floor_area_m2 is None:
        add("room", "Room area could not be measured from this sweep")
    elif p.room.confidence is not None and p.room.confidence < 0.7:
        add("room", f"Room measurement confidence {p.room.confidence:.2f} (method: {p.room.scale_method})")
    return q


def finalize(p: ClaimPacket) -> ClaimPacket:
    """Fill derived fields. Call this last, after every stage has written its lines."""
    p.totals = compute_totals(p)
    p.review_queue = build_review_queue(p)
    if p.room.floor_area_m2 is not None:
        p.room.floor_area_ft2 = _round(p.room.floor_area_m2 * config.SQFT_PER_SQM)
    if p.room.wall_area_m2 is not None:
        p.room.wall_area_ft2 = _round(p.room.wall_area_m2 * config.SQFT_PER_SQM)
    return p