from app.schema import (
    Book, BookPrice, BookStatus, ClaimPacket, Item, ItemPrice, ItemStatus, Sweep, UsedPrice,
)
from app.totals import compute_totals


def make_packet(books=(), items=()):
    return ClaimPacket(
        sweep=Sweep(id="t", captured_at="2026-10-09T17:00:00+05:30", country="IN", currency="INR"),
        books=list(books),
        items=list(items),
    )


def make_book(n, status=BookStatus.identified, repl=None, used=None, thick=2.0, **extra):
    return Book(
        id=f"b{n}", frame_ref=f"frames/t/{n}.jpg", status=status,
        spine_height_cm=20.0, spine_thickness_cm=thick,
        replacement_cost=BookPrice(amount=repl), used_value=UsedPrice(amount=used),
        **extra,
    )


def test_totals_add_up_from_lines():
    t = compute_totals(make_packet([make_book(1, repl=500, used=200), make_book(2, repl=300)]))
    assert t.book_count == 2
    assert t.books_replacement_cost == 800
    assert t.books_used_value == 200
    assert t.shelf_run_m == 0.04


def test_appraisal_book_never_enters_totals():
    t = compute_totals(make_packet([make_book(1, status=BookStatus.needs_appraisal, repl=99999)]))
    assert t.books_replacement_cost == 0
    assert t.excluded_from_totals == 1


def test_unpriced_book_is_counted_but_excluded():
    t = compute_totals(make_packet([make_book(1)]))
    assert t.book_count == 1
    assert t.excluded_from_totals == 1


def test_user_excluded_shelf_is_dropped():
    t = compute_totals(make_packet([make_book(1, repl=100), make_book(2, repl=100, excluded_by_user=True)]))
    assert t.book_count == 1
    assert t.books_replacement_cost == 100


def test_flat_books_do_not_add_shelf_run():
    t = compute_totals(make_packet([make_book(1, thick=3.0, orientation="flat"), make_book(2, thick=2.0)]))
    assert t.shelf_run_m == 0.02


def test_item_ranges_and_appraisal():
    items = [
        Item(id="i1", category="lamp", frame_ref="f.jpg", status=ItemStatus.range,
             replacement_cost=ItemPrice(low=1000, high=2500)),
        Item(id="i2", category="framed_art", frame_ref="f.jpg", status=ItemStatus.needs_appraisal),
    ]
    t = compute_totals(make_packet(items=items))
    assert t.items_replacement_cost_low == 1000
    assert t.items_replacement_cost_high == 2500
    assert t.excluded_from_totals == 1