from app import fx
from app.stages import price as P

AMZ_IN = {"title": "Atomic Habits: Tiny Changes", "extracted_price": 472, "rating": 4.6, "reviews": 1.1}
USED_IN = [
    {"title": "Atomic Habits by James Clear", "extracted_price": 250, "second_hand_condition": "pre-owned",
     "source": "A", "product_link": "u1"},
    {"title": "Atomic Habits", "extracted_price": 300, "second_hand_condition": "used", "source": "B", "product_link": "u2"},
    {"title": "Atomic Habits", "extracted_price": 900, "second_hand_condition": "used", "source": "C", "product_link": "u3"},
    {"title": "Atomic Habits", "extracted_price": 200, "second_hand_condition": None, "source": "D"},       # new, not used
    {"title": "The Atomic Habits Workbook", "extracted_price": 100, "second_hand_condition": "used", "source": "E"},  # wrong book
]


def fake(amazon=None, shopping=None):
    amazon, shopping = amazon or {}, shopping or {}
    def search(params):
        if params["engine"] == "amazon":
            return {"organic_results": amazon.get(params["amazon_domain"], [])}
        return {"shopping_results": shopping.get(params["gl"], [])}
    return search


def test_used_value_is_the_median_real_used_listing(monkeypatch):
    monkeypatch.setattr(P.serp, "search", fake(shopping={"in": USED_IN}))
    p, _ = P.used_value("Atomic Habits", "James Clear", "IN")
    assert p["amount"] == 300 and p["url"] == "u2"
    assert p["used_listings_matched"] == 3
    assert p["condition_assumed"].startswith("Good")


def test_used_value_falls_back_to_converted_us(monkeypatch):
    us = [{"title": "Atomic Habits", "extracted_price": 8.0, "second_hand_condition": "used"}]
    monkeypatch.setattr(P.serp, "search", fake(shopping={"us": us}))
    monkeypatch.setattr(fx, "rate", lambda a, b: {"rate": 90.0, "source": "test", "as_of": "today"})
    p, _ = P.used_value("Atomic Habits", "James Clear", "IN")
    assert p["converted"] is True and p["amount"] == 720.0


def test_signed_book_is_not_priced_and_spends_no_search(monkeypatch):
    def no_search(params):
        raise AssertionError("should not search for a book going to appraisal")
    monkeypatch.setattr(P.serp, "search", no_search)
    r = P.price_book("Atomic Habits", "James Clear", "IN", spine_text="SIGNED FIRST EDITION")
    assert r["status"] == "needs_appraisal" and r["replacement"] is None


def test_old_book_needs_appraisal():
    assert "1923" in P.appraisal_reason(published="1923-05-01")


def test_expensive_book_is_flagged_and_price_not_used(monkeypatch):
    monkeypatch.setattr(P.serp, "search", fake(amazon={"amazon.in": [dict(AMZ_IN, extracted_price=7500)]}))
    r = P.price_book("Atomic Habits", "James Clear", "IN")
    assert r["status"] == "needs_appraisal" and r["replacement"] is None
    assert r["observed_price"]["amount"] == 7500



def test_normal_book_gets_both_prices(monkeypatch):
    monkeypatch.setattr(P.serp, "search", fake(amazon={"amazon.in": [AMZ_IN]}, shopping={"in": USED_IN}))
    r = P.price_book("Atomic Habits", "James Clear", "IN", published="2018")
    assert r["status"] == "identified"
    assert r["replacement"]["amount"] == 472
    # 900 is above the new-price ceiling (472); of 250 and 300, the lower-middle median is 250
    assert r["used"]["amount"] == 250

def test_used_listing_above_new_price_is_excluded(monkeypatch):
    # Real failure: a $151 collectible copy was used as "used value" for a $18.88 book
    us = [{"title": "Atomic Habits", "extracted_price": 151.0, "second_hand_condition": "pre-owned"},
          {"title": "Atomic Habits", "extracted_price": 9.0, "second_hand_condition": "used"}]
    monkeypatch.setattr(P.serp, "search", fake(shopping={"us": us}))
    p, _ = P.used_value("Atomic Habits", "James Clear", "US", new_price={"amount": 18.88, "currency": "USD"})
    assert p["amount"] == 9.0 and p["used_listings_matched"] == 1


def test_us_used_price_above_indian_new_price_gives_no_used_value(monkeypatch):
    us = [{"title": "Atomic Habits", "extracted_price": 8.0, "second_hand_condition": "used"}]
    monkeypatch.setattr(P.serp, "search", fake(shopping={"us": us}))
    monkeypatch.setattr(P.fx, "rate",
                        lambda a, b: {"rate": 1 / 96.88 if a == "INR" else 96.88, "source": "t", "as_of": "d"})
    p, notes = P.used_value("Atomic Habits", "James Clear", "IN", new_price={"amount": 472.0, "currency": "INR"})
    assert p is None
    assert "no price found in any market" in notes

