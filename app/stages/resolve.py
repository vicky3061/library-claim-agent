import re
import unicodedata
from datetime import datetime, timezone

from rapidfuzz import fuzz

from app import config
from app.http_client import get_json


GOOGLE_BOOKS = "https://www.googleapis.com/books/v1/volumes"
OPEN_LIBRARY = "https://openlibrary.org/search.json"



def norm(text):
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _covered(token, tokens):
    return any(fuzz.ratio(token, t) >= 80 for t in tokens)


def score_candidate(spine_text, cand):
    spine_tokens = norm(spine_text).split()
    title_tokens = norm(cand["title"]).split()
    if not spine_tokens or not title_tokens:
        return 0.0
    cand_tokens = norm(" ".join([cand["title"], *cand.get("authors", []), cand.get("publisher") or ""])).split()
    title_on_spine = sum(_covered(t, spine_tokens) for t in title_tokens) / len(title_tokens)
    spine_explained = sum(_covered(t, cand_tokens) for t in spine_tokens) / len(spine_tokens)
    return round(0.6 * title_on_spine + 0.4 * spine_explained, 3)


def choose(spine_text, candidates):
    scored = sorted(((score_candidate(spine_text, c), c) for c in candidates),
                    key=lambda x: x[0], reverse=True)
    if not scored or scored[0][0] < config.ID_ACCEPT_THRESHOLD:
        best = scored[0][0] if scored else 0.0
        return {"status": "unidentified", "confidence": best, "match": None, "reason": "no confident match"}
    best_score, best = scored[0]
    for s, c in scored[1:]:
        if norm(c["title"]) != norm(best["title"]) and s >= best_score - config.ID_AMBIGUITY_MARGIN:
            return {"status": "unidentified", "confidence": best_score, "match": None, "reason": "ambiguous"}
    return {"status": "identified", "confidence": best_score, "match": best, "reason": None}

def google_books_candidates(text, max_results=5):
    params = {"q": text, "maxResults": max_results, "printType": "books"}
    if config.GOOGLE_BOOKS_API_KEY:
        params["key"] = config.GOOGLE_BOOKS_API_KEY
    data = get_json(GOOGLE_BOOKS, params)
    out = []
    for item in data.get("items", []):
        v = item.get("volumeInfo", {})
        isbns = [i["identifier"] for i in v.get("industryIdentifiers", [])
                 if i.get("type") in ("ISBN_13", "ISBN_10")]
        out.append({"title": v.get("title", ""), "authors": v.get("authors", []),
                    "publisher": v.get("publisher"), "published": v.get("publishedDate"),
                    "isbns": isbns, "source": "Google Books",
                    "source_id": item.get("id"), "url": v.get("infoLink")})
    return out


def open_library_candidates(text, limit=5):
    data = get_json(OPEN_LIBRARY, {"q": text, "limit": limit,
                                   "fields": "key,title,author_name,publisher,first_publish_year,isbn"})
    out = []
    for d in data.get("docs", []):
        key = d.get("key")
        out.append({"title": d.get("title", ""), "authors": d.get("author_name", []),
                    "publisher": (d.get("publisher") or [None])[0],
                    "published": str(d.get("first_publish_year") or ""),
                    "isbns": (d.get("isbn") or [])[:5], "source": "Open Library",
                    "source_id": key, "url": f"https://openlibrary.org{key}" if key else None})
    return out


def resolve(spine_text):
    candidates, errors = [], []
    for fetch in (google_books_candidates, open_library_candidates):
        try:
            candidates += fetch(spine_text)
        except Exception as e:
            errors.append(f"{fetch.__name__}: {e}")
    result = choose(spine_text, candidates)
    if not candidates and errors:
        result["reason"] = "catalogue lookup failed"
    result["spine_text"] = spine_text
    result["retrieved_at"] = datetime.now(timezone.utc).isoformat()
    result["errors"] = errors
    return result

