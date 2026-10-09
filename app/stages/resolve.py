import re

from rapidfuzz import fuzz

from app import config


def norm(text):
    text = re.sub(r"[^a-z0-9 ]", " ", (text or "").lower())
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