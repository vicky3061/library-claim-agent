import time

import httpx

RETRY_STATUS = {429, 500, 502, 503, 504}  # busy or temporary errors: worth retrying


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