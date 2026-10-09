import re
from datetime import datetime, timezone

from app import config, fx, serp
from app.stages.resolve import _covered, norm
from app.stages.resolve import _covered, norm
from datetime import datetime, timezone
from app import config, fx, serp


LANGUAGES = {"tamil", "telugu", "hindi", "marathi", "punjabi", "gujarati", "malayalam",
             "kannada", "bengali", "odia", "urdu", "assamese", "sanskrit"}
DERIVATIVES = {"workbook", "summary", "analysis", "journal", "guide", "companion",
               "notebook", "planner", "notes", "study"}
BUNDLE_WORDS = {"combo", "set", "pack", "bundle", "books"}

NON_PHYSICAL = {"audiobook", "audible", "kindle", "ebook", "mp3", "audio"}

USED_MARKERS = ("used", "pre-owned", "preowned", "second hand", "secondhand")


def is_non_physical(listing):
    text = norm(f"{listing.get('title') or ''} {listing.get('link') or ''}")
    return any(w in text.split() for w in NON_PHYSICAL)


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
        if why is None and is_non_physical(x):
            why = "not a physical book (audiobook/ebook)"
        if why is None and x.get("rating") is None:
            why = "no ratings (unverified listing)"
        if why is None and not (x.get("extracted_price") or 0) > 0:
            why = "missing or zero price"
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


LANGUAGES = {"tamil", "telugu", "hindi", "marathi", "punjabi", "gujarati", "malayalam", "kannada",
             "bengali", "odia", "urdu", "assamese", "sanskrit", "spanish", "espanol", "edicion",
             "portuguese", "french", "german", "italian", "chinese", "japanese", "korean", "arabic", "russian"}
FOREIGN_FUNCTION_WORDS = {"el", "la", "los", "las", "del", "de", "para", "con", "en", "y", "una", "une",
                          "des", "le", "les", "und", "das", "il", "di", "que", "em", "um"}
NOT_THE_BOOK = {"workbook", "summary", "analysis", "journal", "guide", "companion", "notebook", "planner",
                "notes", "study", "poster", "calendar", "podcast", "canvas", "painting", "sticker"}
BUNDLE_WORDS = {"combo", "set", "pack", "bundle", "books"}
NON_PHYSICAL = {"audiobook", "audible", "kindle", "ebook", "mp3", "audio"}
PHYSICAL_FORMATS = ["paperback", "mass market paperback", "hardcover"]  # preference order


def non_latin_ratio(text):
    letters = [c for c in (text or "") if c.isalpha()]
    return sum(1 for c in letters if ord(c) > 0x24F) / len(letters) if letters else 0.0


def reject_reason(listing_title, book_title, language="english"):
    raw = listing_title or ""
    tokens = norm(raw).split()
    book_tokens = norm(book_title).split()
    if "+" in raw or any(w in tokens for w in BUNDLE_WORDS):
        return "bundle"
    if (any(w in tokens for w in LANGUAGES - {language}) or non_latin_ratio(raw) > 0.3
            or len(FOREIGN_FUNCTION_WORDS & set(tokens)) >= 2):
        return "other language"
    if any(w in tokens for w in NOT_THE_BOOK - set(book_tokens)):
        return "not the book itself"
    if not all(_covered(t, tokens) for t in book_tokens):
        return "title mismatch"
    return None


def is_non_physical(listing):
    text = norm(f"{listing.get('title') or ''} {listing.get('link') or ''}")
    return any(w in text.split() for w in NON_PHYSICAL)


def physical_offer(listing, domain="www.amazon.com"):
    """Price of a physical format: from purchase_options if present, else the listing itself."""
    opts = listing.get("purchase_options") or []
    for fmt in PHYSICAL_FORMATS:
        for o in opts:
            if (o.get("type") or "").lower() == fmt and (o.get("extracted_primary_price") or 0) > 0:
                m = re.search(r"/(?:offer-listing|dp)/([A-Z0-9]{10})", o.get("more_buying_choices_link") or "")
                return {"format": fmt, "price": float(o["extracted_primary_price"]),
                        "list_price": o.get("extracted_old_primary_price"),
                        "url": f"https://{domain}/dp/{m.group(1)}" if m else None}
    if not is_non_physical(listing) and (listing.get("extracted_price") or 0) > 0:
        return {"format": "unspecified", "price": float(listing["extracted_price"]),
                "list_price": listing.get("extracted_old_price"), "url": None}
    return None


def review_count(listing):
    v = float(listing.get("reviews") or 0)
    if v != int(v):  # Amazon shows "1.1K"/"1.1 lakh"; the API returns 1.1, so treat decimals as thousands
        v *= 1000
    return v


def pick_canonical(listings, book_title, language="english", domain="www.amazon.com"):
    kept, rejected = [], []
    for x in listings:
        why = reject_reason(x.get("title"), book_title, language)
        offer = physical_offer(x, domain) if why is None else None
        if why is None and offer is None:
            why = "no physical-format price"
        if why is None and x.get("rating") is None:
            why = "no ratings (unverified listing)"
        if why:
            rejected.append({"title": x.get("title"), "reason": why})
        else:
            kept.append((x, offer))
    if not kept:
        return None, rejected
    x, offer = max(kept, key=lambda k: review_count(k[0]))
    return {**x, "_offer": offer}, rejected


def _now():
    return datetime.now(timezone.utc).isoformat()


def amazon_new_price(title, author, market):
    m = config.MARKETS[market]
    data = serp.search({"engine": "amazon", "amazon_domain": m["amazon_domain"],
                        "k": f"{title} {author}".strip()})
    best, rejected = pick_canonical(data.get("organic_results", []), title,
                                    domain="www." + m["amazon_domain"])
    if not best:
        return None, rejected
    offer = best["_offer"]
    return {"amount": offer["price"], "currency": m["currency"], "format": offer["format"],
            "source": f"Amazon ({m['amazon_domain']}) via SerpAPI",
            "url": offer["url"] or best.get("link_clean") or best.get("link"), "retrieved_at": _now(),
            "list_price": offer["list_price"], "converted": False}, rejected


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


def _is_used(listing):
    condition = (listing.get("second_hand_condition") or "").lower()
    return any(m in condition for m in USED_MARKERS)


def shopping_used_price(title, author, market, ceiling=None):
    m = config.MARKETS[market]
    data = serp.search({"engine": "google_shopping", "q": f"{title} {author} used".strip(),
                        "gl": market.lower(), "hl": "en"})
    matches = [x for x in data.get("shopping_results", [])
               if _is_used(x) and reject_reason(x.get("title"), title) is None
               and not is_non_physical(x) and (x.get("extracted_price") or 0) > 0
               and (ceiling is None or x["extracted_price"] <= ceiling)]
    if not matches:
        return None
    matches.sort(key=lambda x: x["extracted_price"] )
    mid = matches[(len(matches) - 1) // 2]  # median listing: a real offer, robust to outliers
    return {"amount": float(mid["extracted_price"]), "currency": m["currency"],
            "source": f"Google Shopping ({market}) via SerpAPI, seller: {mid.get('source')}",
            "url": mid.get("product_link") or mid.get("link"), "retrieved_at": _now(), "converted": False,
            "condition_assumed": config.USED_CONDITION_ASSUMED,
            "listing_condition": mid.get("second_hand_condition"), "used_listings_matched": len(matches),"ceiling_new_price": ceiling}

def _with_fallback(fetch, title, author, market):
    """Try the local market, then the fallback market (converted). Same rule for new and used."""
    notes = []
    markets = [market] + ([config.FALLBACK_MARKET] if config.FALLBACK_MARKET != market else [])
    for mk in markets:
        try:
            p = fetch(title, author, mk)
        except Exception as e:
            notes.append(f"{mk} lookup failed: {e}")
            continue
        if p:
            if mk != market:
                p = convert(p, config.MARKETS[market]["currency"])
                notes.append(f"no {market} listing; converted from {mk}")
            return p, notes
    return None, notes + ["no price found in any market"]


def replacement_cost(title, author, market):
    return _with_fallback(lambda t, a, mk: amazon_new_price(t, a, mk)[0], title, author, market)


def used_value(title, author, market, new_price=None):
    def fetch(t, a, mk):
        ceiling = None
        if new_price:  # never accept a used price above the new price, in that market's currency
            ccy = config.MARKETS[mk]["currency"]
            ceiling = round(new_price["amount"] * fx.rate(new_price["currency"], ccy)["rate"], 2)
        return shopping_used_price(t, a, mk, ceiling)
    return _with_fallback(fetch, title, author, market)


def _year(published):
    m = re.search(r"\b(1[5-9]\d\d|20\d\d)\b", str(published or ""))
    return int(m.group(1)) if m else None


def appraisal_reason(spine_text="", user_notes=(), published=None, replacement=None):
    text = norm(" ".join([spine_text or "", *user_notes]))
    for k in config.APPRAISAL_KEYWORDS:
        if norm(k) in text:
            return f"'{k}' noted on spine or by policyholder"
    year = _year(published)
    if year and year < config.APPRAISAL_PUBLISHED_BEFORE:
        return f"published {year}, before {config.APPRAISAL_PUBLISHED_BEFORE}"
    if replacement:
        limit = config.APPRAISAL_PRICE_LIMIT.get(replacement["currency"])
        if limit and replacement["amount"] > limit:
            return f"replacement price {replacement['amount']} {replacement['currency']} above {limit}"
    return None


def price_book(title, author, market, spine_text="", user_notes=(), published=None):
    """Stage entry point: appraisal checks first, then replacement cost, then used value."""
    reason = appraisal_reason(spine_text, user_notes, published)
    if reason:  # decided before any search: no quota spent on books we won't auto-price
        return {"status": "needs_appraisal", "reason": reason, "replacement": None, "used": None, "notes": []}
    repl, notes = replacement_cost(title, author, market)
    reason = appraisal_reason(replacement=repl)
    if reason:  # the observed price is kept as evidence, never used as the value
        return {"status": "needs_appraisal", "reason": reason, "replacement": None, "used": None,
                "notes": notes, "observed_price": repl}
    used, used_notes = used_value(title, author, market, new_price=repl)
    return {"status": "identified", "reason": None, "replacement": repl, "used": used,
            "notes": notes + [f"used: {n}" for n in used_notes]}