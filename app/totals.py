from app.schema import BookStatus, ClaimPacket, ItemStatus, Totals,ReviewEntry
from app import config


def compute_totals(p: ClaimPacket) -> Totals:
    t = Totals()
    books = [b for b in p.books if not b.excluded_by_user]
    items = [i for i in p.items if not i.excluded_by_user]

    # counts
    t.book_count = len(books)
    t.books_identified = sum(b.status == BookStatus.identified for b in books)
    t.books_unidentified = sum(b.status == BookStatus.unidentified for b in books)
    t.books_needs_appraisal = sum(b.status == BookStatus.needs_appraisal for b in books)

    # shelf run: thickness of upright books only (flat stacks don't use shelf length)
    run_cm = sum(
        b.spine_thickness_cm
        for b in books
        if b.spine_thickness_cm is not None and b.orientation != "flat"
    )
    t.shelf_run_m = round(run_cm / 100, 2)

    # book values
    excluded = 0
    for b in books:
        if b.status == BookStatus.needs_appraisal:
            excluded += 1  # never auto-priced
            continue
        repl = b.replacement_cost.amount
        used = b.used_value.amount
        if repl is None and used is None:
            excluded += 1  # no price anywhere
            continue
        if repl is not None:
            t.books_replacement_cost += repl
        if used is not None:
            t.books_used_value += used

    # item values
    for i in items:
        low = i.replacement_cost.low
        high = i.replacement_cost.high
        if i.status == ItemStatus.needs_appraisal or low is None:
            excluded += 1
            continue
        t.items_replacement_cost_low += low
        t.items_replacement_cost_high += high if high is not None else low

    t.books_replacement_cost = round(t.books_replacement_cost, 2)
    t.books_used_value = round(t.books_used_value, 2)
    t.items_replacement_cost_low = round(t.items_replacement_cost_low, 2)
    t.items_replacement_cost_high = round(t.items_replacement_cost_high, 2)
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
            if b.replacement_cost.amount is None and b.used_value.amount is None:
                add(b.id, "No price found in any market; excluded from totals")
            if b.replacement_cost.converted or b.used_value.converted:
                add(b.id, "Price converted from another market's currency")
        if b.spine_height_cm is None:
            add(b.id, "Spine not measured (no metric scale in frame)")

    for i in p.items:
        if i.excluded_by_user:
            continue
        if i.status == ItemStatus.needs_appraisal:
            add(i.id, "Art or high-value item: needs appraisal")
        elif i.replacement_cost.low is None:
            add(i.id, "No sourced price found; excluded from totals")
        elif i.status == ItemStatus.range:
            add(i.id, "Brand/model unknown; priced as a sourced range")

    if p.room.floor_area_m2 is None:
        add("room", "Room area could not be measured from this sweep")
    elif p.room.confidence is not None and p.room.confidence < 0.7:
        add("room", f"Room measurement confidence {p.room.confidence:.2f} ({p.room.scale_method})")
    return q


def finalize(p: ClaimPacket) -> ClaimPacket:
    """Fill every derived field. Call this last, after all stages have written their lines."""
    p.totals = compute_totals(p)
    p.review_queue = build_review_queue(p)
    if p.room.floor_area_m2 is not None:
        p.room.floor_area_ft2 = round(p.room.floor_area_m2 * config.SQFT_PER_SQM, 2)
    if p.room.wall_area_m2 is not None:
        p.room.wall_area_ft2 = round(p.room.wall_area_m2 * config.SQFT_PER_SQM, 2)
    return p