import json
from app import http_client as H


def test_cached_get_json_calls_once_and_never_stores_key(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(H, "get_json", lambda url, params=None: calls.append(params) or {"items": [1]})
    p = {"q": "atomic habits", "key": "SECRET123"}
    a = H.cached_get_json("gb", "https://x/books", p, cache_dir=str(tmp_path))
    b = H.cached_get_json("gb", "https://x/books", p, cache_dir=str(tmp_path))
    assert a == b == {"items": [1]} and len(calls) == 1          # second call served from disk
    files = list(tmp_path.rglob("*.json"))
    assert len(files) == 1 and "SECRET123" not in files[0].read_text()  # key never written


def test_failures_are_not_cached(tmp_path, monkeypatch):
    def boom(url, params=None):
        raise RuntimeError("HTTP 503")
    monkeypatch.setattr(H, "get_json", boom)
    try:
        H.cached_get_json("gb", "https://x/books", {"q": "x"}, cache_dir=str(tmp_path))
    except RuntimeError:
        pass
    assert list(tmp_path.rglob("*.json")) == []