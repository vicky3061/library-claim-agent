from app.http_client import get_json

FX_URL = "https://open.er-api.com/v6/latest/{base}"
_cache = {}  # one lookup per currency per run


def rate(from_ccy, to_ccy):
    if from_ccy == to_ccy:
        return {"rate": 1.0, "source": None, "as_of": None}
    if from_ccy not in _cache:
        _cache[from_ccy] = get_json(FX_URL.format(base=from_ccy))
    data = _cache[from_ccy]
    r = data.get("rates", {}).get(to_ccy)
    if r is None:
        raise RuntimeError(f"no FX rate {from_ccy}->{to_ccy}")
    return {"rate": float(r), "source": "open.er-api.com (ExchangeRate-API)",
            "as_of": data.get("time_last_update_utc")}