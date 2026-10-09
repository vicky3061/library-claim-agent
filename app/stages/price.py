from app.stages.resolve import _covered, norm
from datetime import datetime, timezone
from app import config, fx, serp


LANGUAGES = {"tamil", "telugu", "hindi", "marathi", "punjabi", "gujarati", "malayalam",
             "kannada", "bengali", "odia", "urdu", "assamese", "sanskrit"}
DERIVATIVES = {"workbook", "summary", "analysis", "journal", "guide", "companion",
               "notebook", "planner", "notes", "study"}
BUNDLE_WORDS = {"combo", "set", "pack", "bundle", "books"}


def reject_reason(listing_title, book_title, language="english"):
    raw = listing_title or ""
    tokens = norm(raw).split()
    book_tokens = norm(book_title).split()
    if "+" in raw or any(w in tokens for w in BUNDLE_WORDS):
        return "bundle"
    if any(w in tokens for w in LANGUAGES - {language}):
        return "other language"
    if any(w in tokens for w in DERIVATIVES - set(book_tokens)):
        return "derivative work"
    if not all(_covered(t, tokens) for t in book_tokens):
        return "title mismatch"
    return None


def review_count(listing):
    v = float(listing.get("reviews") or 0)
    if v != int(v):   # Amazon shows "1.1K"/"1.1 lakh"; the API returns 1.1, so treat decimals as thousands
        v *= 1000
    return v


def pick_canonical(listings, book_title, language="english"):
    kept, rejected = [], []
    for x in listings:
        why = reject_reason(x.get("title"), book_title, language)
        if why is None and x.get("rating") is None:
            why = "no ratings (unverified listing)"
        if why is None and x.get("extracted_price") is None:
            why = "no price"
        if why:
            rejected.append({"title": x.get("title"), "reason": why})
        else:
            kept.append(x)
    best = max(kept, key=review_count) if kept else None
    return best, rejected

def _now():
    return datetime.now(timezone.utc).isoformat()


def amazon_new_price(title, author, market):
    m = config.MARKETS[market]
    data = serp.search({"engine": "amazon", "amazon_domain": m["amazon_domain"],
                        "k": f"{title} {author}".strip()})
    best, rejected = pick_canonical(data.get("organic_results", []), title)
    if not best:
        return None, rejected
    return {"amount": float(best["extracted_price"]), "currency": m["currency"],
            "source": f"Amazon ({m['amazon_domain']}) via SerpAPI",
            "url": best.get("link_clean") or best.get("link"), "retrieved_at": _now(),
            "list_price": best.get("extracted_old_price"), "converted": False}, rejected


def convert(price, to_ccy):
    fxr = fx.rate(price["currency"], to_ccy)
    return {**price, "converted": True,
            "original_amount": price["amount"], "original_currency": price["currency"],
            "amount": round(price["amount"] * fxr["rate"], 2), "currency": to_ccy,
            "fx_rate": fxr["rate"], "fx_source": fxr["source"], "fx_as_of": fxr["as_of"]}


def replacement_cost(title, author, market):
    notes = []
    try:
        p, _ = amazon_new_price(title, author, market)
    except Exception as e:
        p = None
        notes.append(f"local lookup failed: {e}")
    if p:
        return p, notes
    fb = config.FALLBACK_MARKET
    if fb != market:
        try:
            p, _ = amazon_new_price(title, author, fb)
            if p:
                return convert(p, config.MARKETS[market]["currency"]), notes + ["no local listing; converted"]
        except Exception as e:
            notes.append(f"fallback lookup failed: {e}")
    return None, notes + ["no price found in any market"]