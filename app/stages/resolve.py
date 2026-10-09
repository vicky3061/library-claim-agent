import re
import unicodedata
from datetime import datetime, timezone

from rapidfuzz import fuzz

from app import config
from app.http_client import cached_get_json

GOOGLE_BOOKS = "https://www.googleapis.com/books/v1/volumes"
OPEN_LIBRARY = "https://openlibrary.org/search.json"


# ---------- text helpers ----------

def norm(text):
    text = (text or "").replace("ß", "ss").replace("ẞ", "SS")  # German sharp s: standard equivalent is "ss"
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _covered(token, tokens):
    return any(fuzz.ratio(token, t) >= 80 for t in tokens)


def _coverage(a_tokens, b_tokens):
    """Fraction of a_tokens that appear (fuzzily) in b_tokens."""
    return sum(_covered(t, b_tokens) for t in a_tokens) / len(a_tokens) if a_tokens else 0.0


def _name_tokens(text):
    return [t for t in norm(text).split() if len(t) >= 2]  # drop initials like "j", "l"


# ---------- scoring: full spine text (fallback when fields are missing) ----------

def score_candidate(spine_text, cand):
    spine_tokens = norm(spine_text).split()
    title_tokens = norm(cand["title"]).split()
    if not spine_tokens or not title_tokens:
        return 0.0
    cand_tokens = norm(" ".join([cand["title"], *cand.get("authors", []), cand.get("publisher") or ""])).split()
    title_on_spine = _coverage(title_tokens, spine_tokens)
    spine_explained = _coverage(spine_tokens, cand_tokens)
    return round(0.6 * title_on_spine + 0.4 * spine_explained, 3)


# ---------- scoring: fields read from the spine ----------

def score_fields(title, author, cand):
    st, ct = norm(title).split(), norm(cand["title"]).split()
    if not st or not ct:
        return 0.0
    # whole candidate title must be on the spine (blocks partial guesses like "Harry Potter"),
    # and the spine title must be mostly explained (blocks short-title traps like "Habits")
    title_score = 0.7 * _coverage(ct, st) + 0.3 * _coverage(st, ct)
    spine_author = _name_tokens(author)
    if not spine_author:
        return round(title_score, 3)
    cand_author = _name_tokens(" ".join(cand.get("authors", [])))
    author_score = _coverage(spine_author, cand_author) if cand_author else 0.0
    return round(0.65 * title_score + 0.35 * author_score, 3)


def _decide(scored):
    scored = sorted(scored, key=lambda x: x[0], reverse=True)
    if not scored or scored[0][0] < config.ID_ACCEPT_THRESHOLD:
        best = scored[0][0] if scored else 0.0
        return {"status": "unidentified", "confidence": best, "match": None, "reason": "no confident match"}
    best_score, best = scored[0]
    for s, c in scored[1:]:
        if norm(c["title"]) != norm(best["title"]) and s >= best_score - config.ID_AMBIGUITY_MARGIN:
            return {"status": "unidentified", "confidence": best_score, "match": None, "reason": "ambiguous"}
    return {"status": "identified", "confidence": best_score, "match": best, "reason": None}


def choose(spine_text, candidates):
    return _decide([(score_candidate(spine_text, c), c) for c in candidates])


def choose_fields(title, author, candidates):
    return _decide([(score_fields(title, author, c), c) for c in candidates])


# ---------- catalogue lookups ----------

def _gb(q, max_results=5):
    params = {"q": q, "maxResults": max_results, "printType": "books"}
    if config.GOOGLE_BOOKS_API_KEY:
        params["key"] = config.GOOGLE_BOOKS_API_KEY
    out = []
    for item in cached_get_json("google_books", GOOGLE_BOOKS, params).get("items", []):
        v = item.get("volumeInfo", {})
        isbns = [i["identifier"] for i in v.get("industryIdentifiers", []) if i.get("type") in ("ISBN_13", "ISBN_10")]
        out.append({"title": v.get("title", ""), "authors": v.get("authors", []), "publisher": v.get("publisher"),
                    "published": v.get("publishedDate"), "isbns": isbns, "language": v.get("language"),
                    "source": "Google Books", "source_id": item.get("id"), "url": v.get("infoLink")})
    return out


def _ol(params, limit=5):
    fields = "key,title,author_name,author_alternative_name,publisher,first_publish_year,isbn,language"
    out = []
    for d in cached_get_json("open_library", OPEN_LIBRARY, {**params, "limit": limit, "fields": fields}).get("docs", []):
        key = d.get("key")
        out.append({"title": d.get("title", ""),
                    # alternative names include pen names (e.g. Sonnleitner = Alois Tlučhoř)
                    "authors": d.get("author_name", []) + d.get("author_alternative_name", [])[:5],
                    "publisher": (d.get("publisher") or [None])[0], "published": str(d.get("first_publish_year") or ""),
                    "isbns": (d.get("isbn") or [])[:5], "language": (d.get("language") or [None])[0],
                    "source": "Open Library", "source_id": key, "url": f"https://openlibrary.org{key}" if key else None})
    return out


def google_books_candidates(text, max_results=5):
    return _gb(text, max_results)


def open_library_candidates(text, limit=5):
    return _ol({"q": text}, limit)


def field_candidates(title, author):
    """Targeted queries: title + author surname first, then title only. No publisher/volume noise."""
    surname = (_name_tokens(author) or [""])[-1]
    queries = []
    if surname:
        queries += [("gb", f"{title} inauthor:{surname}"), ("ol", {"title": title, "author": surname})]
    queries += [("gb", title), ("ol", {"title": title})]
    out, errors, seen = [], [], set()
    for kind, q in queries:
        try:
            cands = _gb(q) if kind == "gb" else _ol(q)
        except Exception as e:
            errors.append(f"{kind} {q}: {e}")
            continue
        for c in cands:
            if (c["source"], c["source_id"]) not in seen:
                seen.add((c["source"], c["source_id"]))
                out.append(c)
        if len(out) >= 10:
            break  # enough candidates: stop early to save calls
    return out, errors


# ---------- stage entry points ----------

def _stamp(result, **extra):
    result.update(extra)
    result["retrieved_at"] = datetime.now(timezone.utc).isoformat()
    return result


def resolve(spine_text):
    """Fallback path: only the full spine text is available."""
    candidates, errors = [], []
    for fetch in (google_books_candidates, open_library_candidates):
        try:
            candidates += fetch(spine_text)
        except Exception as e:
            errors.append(f"{fetch.__name__}: {e}")
    result = choose(spine_text, candidates)
    if not candidates and errors:
        result["reason"] = "catalogue lookup failed"
    return _stamp(result, spine_text=spine_text, errors=errors)


def resolve_spine(spine):
    """Main path: use the fields read from the spine (title/author/volume)."""
    if not norm(spine.get("title")):
        return resolve(spine.get("text", ""))
    candidates, errors = field_candidates(spine["title"], spine.get("author", ""))
    result = choose_fields(spine["title"], spine.get("author", ""), candidates)
    if not candidates and errors:
        result["reason"] = "catalogue lookup failed"
    return _stamp(result, spine_text=spine.get("text", ""), volume=spine.get("volume") or None, errors=errors,
                  candidates_seen=len(candidates))