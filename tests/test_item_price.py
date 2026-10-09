from app.stages import item_price as IP


def _l(title, price, used=None):
    return {"title": title, "extracted_price": price, "second_hand_condition": used, "link": f"https://x/{price}"}


def _fake(results):
    calls = []
    def search(params):
        calls.append(params["q"])
        return {"shopping_results": results}
    return search, calls


def test_no_brand_gives_sourced_range(monkeypatch):
    search, calls = _fake([_l("Wooden Bookshelf 5 tier", p) for p in (2000, 3000, 4000, 5000, 9000)]
                          + [_l("Bookshelf cover", 300), _l("Used bookshelf", 800, "pre-owned")])
    monkeypatch.setattr(IP.serp, "search", search)
    price, status = IP.price_item("shelving", "light wooden bookshelf with shelves holding books", "", "IN")
    assert status == "range" and (price["low"], price["high"]) == (3000.0, 5000.0)   # cover + used dropped
    assert price["currency"] == "INR" and "25th-75th" in price["source"] and price["url"]
    assert calls == ["shelving light wooden bookshelf shelves"]


def test_brand_must_appear_in_listing(monkeypatch):
    search, _ = _fake([_l("Philips LED Desk Lamp 5W", 1499), _l("Generic desk lamp", 299), _l("Philips desk lamp white", 1699)])
    monkeypatch.setattr(IP.serp, "search", search)
    price, status = IP.price_item("lamp", "desk lamp", "PHILIPS", "IN")
    assert status == "priced" and price["low"] == price["high"] == 1699.0       # median of the 2 Philips listings


def test_too_little_evidence_is_not_priced(monkeypatch):
    search, _ = _fake([_l("Wall clock", 500), _l("Wall clock round", 700)])
    monkeypatch.setattr(IP.serp, "search", search)
    price, why = IP.price_item("clock", "wall clock", "", "IN")
    assert price is None and "only 2" in why