import hashlib, json, os, threading
from app import config
from app.http_client import get_json

SERPAPI_URL = "https://serpapi.com/search.json"
stats = {"searches": 0, "cache_hits": 0}

def search(params):
    key = hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
    path = os.path.join(config.CACHE_DIR, "serpapi", f"{key}.json")
    if os.path.exists(path):
        stats["cache_hits"] += 1
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    if not config.SERPAPI_KEY:
        raise RuntimeError("SERPAPI_KEY not set")
    data = get_json(SERPAPI_URL, {**params, "api_key": config.SERPAPI_KEY}, timeout=30, tries=2)
    data.pop("search_parameters", None)   # never store the request (it contains the API key)
    stats["searches"] += 1
    try:  # best effort + atomic: parallel pricing must never see a half-written file
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.{threading.get_ident()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        pass
    data["_cache_file"] = path
    return data