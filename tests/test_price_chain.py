from app import fx
from app.stages import price as P

GOOD_IN = {"title": "Atomic Habits: Tiny Changes", "extracted_price": 472, "rating": 4.6, "reviews": 1.1,
           "link": "https://www.amazon.in/example"}
GOOD_US = {"title": "Atomic Habits", "extracted_price": 12.0, "rating": 4.8, "reviews": 90000,
           "link": "https://www.amazon.com/example"}


def fake_search(results_by_domain):
    def search(params):
        return {"organic_results": results_by_domain.get(params["amazon_domain"], [])}
    return search


def test_local_price_is_used(monkeypatch):
    monkeypatch.setattr(P.serp, "search", fake_search({"amazon.in": [GOOD_IN]}))
    p, _ = P.replacement_cost("Atomic Habits", "James Clear", "IN")
    assert p["amount"] == 472 and p["currency"] == "INR"
    assert p["converted"] is False and p["url"]


def test_falls_back_to_converted_us_price(monkeypatch):
    monkeypatch.setattr(P.serp, "search", fake_search({"amazon.com": [GOOD_US]}))
    monkeypatch.setattr(fx, "rate", lambda a, b: {"rate": 85.0, "source": "test", "as_of": "today"})
    p, notes = P.replacement_cost("Atomic Habits", "James Clear", "IN")
    assert p["converted"] is True and p["amount"] == 1020.0
    assert p["original_amount"] == 12.0 and p["fx_rate"] == 85.0


def test_no_price_anywhere_returns_none(monkeypatch):
    monkeypatch.setattr(P.serp, "search", fake_search({}))
    p, notes = P.replacement_cost("Atomic Habits", "James Clear", "IN")
    assert p is None
    assert "no price found in any market" in notes


def test_us_market_prices_in_dollars_without_conversion(monkeypatch):
    monkeypatch.setattr(P.serp, "search", fake_search({"amazon.com": [GOOD_US]}))
    p, _ = P.replacement_cost("Atomic Habits", "James Clear", "US")
    assert p["currency"] == "USD" and p["converted"] is False
    