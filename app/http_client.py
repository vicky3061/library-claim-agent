import time
import hashlib
import json
import os
import threading
import httpx

RETRY_STATUS = {429, 500, 502, 503, 504}  # busy or temporary errors: worth retrying

cache_stats = {"calls": 0, "cache_hits": 0}
_lock = threading.Lock()

def get_json(url, params=None, tries=4, timeout=15.0):
    delay = 1.0
    last_error = None
    for attempt in range(tries):
        try:
            r = httpx.get(url, params=params, timeout=timeout, follow_redirects=True)
            if r.status_code in RETRY_STATUS:
                last_error = f"HTTP {r.status_code}"
            else:
                r.raise_for_status()  # other errors (e.g. 400, 404) fail immediately
                return r.json()
        except httpx.TransportError as e:  # network problems: timeout, connection reset
            last_error = str(e)
        if attempt < tries - 1:
            time.sleep(delay)
            delay *= 2  # wait 1 s, 2 s, 4 s
    raise RuntimeError(f"GET {url} failed after {tries} tries: {last_error}")

def cached_get_json(namespace, url, params=None, secret_params=("key",), cache_dir="runs/cache"):
    """get_json with a disk cache. Same request -> same answer, so runs are reproducible and repeat runs are fast.
    API keys (secret_params) are left out of the cache key and never written to disk. Failures are not cached."""
    public = {k: v for k, v in (params or {}).items() if k not in secret_params}
    key = hashlib.sha1(json.dumps([url, public], sort_keys=True).encode()).hexdigest()[:20]
    path = os.path.join(cache_dir, namespace, f"{key}.json")
    if os.path.exists(path):
        with _lock:
            cache_stats["cache_hits"] += 1
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    data = get_json(url, params)  # raises on failure -> nothing cached
    with _lock:
        cache_stats["calls"] += 1
    try:  # caching is best effort: a failed write must never fail the lookup
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.{threading.get_ident()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)  # atomic: a reader never sees a half-written file
    except OSError:
        pass
    return data