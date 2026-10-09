from app.stages.resolve import _covered, norm

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