from app.schema import BookStatus, ClaimPacket, ItemStatus, Totals


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