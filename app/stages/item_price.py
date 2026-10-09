import re
from datetime import datetime, timezone

from app import config, serp
from app.stages.price import _is_used
from app.stages.resolve import norm

MIN_LISTINGS_FOR_RANGE = 3
ACCESSORY_WORDS = ("cover", "case", "skin", "sticker", "decal", "spare", "parts", "cable", "charger", "remote",
                   "mount", "bracket", "polish", "cleaner", "toy", "miniature", "model kit", "replacement")


def item_query(category, description="", brand_model=""):
    """Brand/model text is the strongest evidence; otherwise category + a few description words."""
    brand = (brand_model or "").strip()
    if re.search(r"[A-Za-z]{2,}", brand):
        return f"{brand} {category}".strip(), brand
    words = [w for w in norm(description).split() if w not in ("with", "and", "the", "of", "holding", "books")]
    return " ".join([category, *words[:4]]).strip(), None


def _accessory(listing_title, query):
    t, q = norm(listing_title), norm(query)
    return any(w in t.split() and w not in q.split() for w in ACCESSORY_WORDS)


def _brand_ok(listing_title, brand):
    tokens = [t for t in norm(brand).split() if len(t) >= 2]
    title = norm(listing_title).split()
    return bool(tokens) and sum(t in title for t in tokens) / len(tokens) >= 0.5


def price_item(category, description, brand_model, market):
    query, brand = item_query(category, description, brand_model)
    data = serp.search({"engine": "google_shopping", "q": query, "gl": market.lower(), "hl": "en"})
    listings = [x for x in data.get("shopping_results", [])
                if (x.get("extracted_price") or 0) > 0 and not _is_used(x) and not _accessory(x.get("title"), query)
                and (brand is None or _brand_ok(x.get("title"), brand))]
    if not listings or (brand is None and len(listings) < MIN_LISTINGS_FOR_RANGE):
        return None, f"only {len(listings)} matching new listings for '{query}'"
    listings.sort(key=lambda x: x["extracted_price"])
    n = len(listings)
    mid = listings[n // 2]
    if brand:
        low = high = float(mid["extracted_price"])
    else:
        low, high = float(listings[n // 4]["extracted_price"]), float(listings[(3 * n) // 4]["extracted_price"])
    price = {"low": low, "high": high, "currency": config.MARKETS[market]["currency"],
             "source": f"Google Shopping ({market}) via SerpAPI: {n} new listings for '{query}'"
                       + ("" if brand else ", 25th-75th percentile"),
             "url": mid.get("product_link") or mid.get("link"),
             "retrieved_at": datetime.now(timezone.utc).isoformat()}
    return price, ("priced" if brand else "range")