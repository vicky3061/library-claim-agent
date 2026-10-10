import os

import numpy as np
import pytest

from app.stages import vision as V

FAKE = V.FrameOut(spines=[V.SpineOut(box_2d=[100, 50, 900, 120], orientation="upright",
                                     text="NANSEN IN NACHT UND EIS I", legibility="clear", cut_off=False)],
                  items=[])

@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    # every test gets its own empty cache folder, so tests never share or pollute cached results
    monkeypatch.setattr(V.config, "CACHE_DIR", str(tmp_path))
    V._exhausted.clear()        # per-run model state must not leak between tests
    V._no_thinking_cfg.clear()


def test_box_to_pixels():
    assert V.to_pixels([100, 50, 900, 120], 1000, 500) == (50, 50, 120, 450)


def test_overload_then_success(monkeypatch):
    calls = []
    def fake(model, b):
        calls.append(model)
        if len(calls) == 1:
            raise RuntimeError("503 UNAVAILABLE high demand")
        return FAKE, {"input": 1, "output": 1}
    monkeypatch.setattr(V, "_call_model", fake)
    monkeypatch.setattr(V.time, "sleep", lambda s: None)  # don't actually wait in tests
    out, tel = V.analyze_frame(b"x")
    assert out.spines[0].text.startswith("NANSEN")
    assert len(tel["attempts"]) == 1


def test_falls_back_to_next_model(monkeypatch):
    def fake(model, b):
        if model == V.config.VISION_MODELS[0]:
            raise RuntimeError("503 UNAVAILABLE")
        return FAKE, {}
    monkeypatch.setattr(V, "_call_model", fake)
    monkeypatch.setattr(V.time, "sleep", lambda s: None)
    out, tel = V.analyze_frame(b"x")
    assert tel["model"] == V.config.VISION_MODELS[1]


def test_retired_model_skips_straight_to_next(monkeypatch):
    # Real failure: gemini-2.5-flash returned 404 "no longer available to new users"
    calls = []
    def fake(model, b):
        calls.append(model)
        if model == V.config.VISION_MODELS[0]:
            raise RuntimeError("404 NOT_FOUND no longer available")
        return FAKE, {}
    monkeypatch.setattr(V, "_call_model", fake)
    monkeypatch.setattr(V.time, "sleep", lambda s: None)
    out, tel = V.analyze_frame(b"x")
    assert calls.count(V.config.VISION_MODELS[0]) == 1  # a 404 is not retried


def test_total_failure_returns_none_with_every_error_recorded(monkeypatch):
    def fake(model, b):
        raise RuntimeError("503 UNAVAILABLE")
    monkeypatch.setattr(V, "_call_model", fake)
    monkeypatch.setattr(V.time, "sleep", lambda s: None)
    out, tel = V.analyze_frame(b"x")
    assert out is None
    assert len(tel["attempts"]) == 3 * len(V.config.VISION_MODELS)


def test_annotate_writes_an_image(tmp_path):
    img = np.zeros((500, 1000, 3), np.uint8)
    path = str(tmp_path / "annotated.jpg")
    V.annotate(img, FAKE, path)
    assert os.path.exists(path)

def test_quota_exhausted_is_not_retried(monkeypatch):
    # Real failure: gemini-3.8-flash returned 429 "exceeded your current quota" three times
    calls = []
    def fake(model, b):
        calls.append(model)
        if model == V.config.VISION_MODELS[0]:
            raise RuntimeError("429 RESOURCE_EXHAUSTED You exceeded your current quota")
        return FAKE, {}
    monkeypatch.setattr(V, "_call_model", fake)
    monkeypatch.setattr(V.time, "sleep", lambda s: None)
    V.analyze_frame(b"x")
    assert calls.count(V.config.VISION_MODELS[0]) == 1

def test_second_call_uses_cache_and_spends_no_quota(monkeypatch):
    calls = []
    def fake(model, b):
        calls.append(model)
        return FAKE, {"input": 1, "output": 1}
    monkeypatch.setattr(V, "_call_model", fake)
    out1, tel1 = V.analyze_frame(b"same photo")
    out2, tel2 = V.analyze_frame(b"same photo")
    assert len(calls) == 1
    assert tel1["cache_hit"] is False and tel2["cache_hit"] is True
    assert out2.spines[0].text == out1.spines[0].text


def test_failures_are_not_cached(monkeypatch):
    def broken(model, b):
        raise RuntimeError("503 UNAVAILABLE")
    monkeypatch.setattr(V, "_call_model", broken)
    monkeypatch.setattr(V.time, "sleep", lambda s: None)
    assert V.analyze_frame(b"photo")[0] is None
    monkeypatch.setattr(V, "_call_model", lambda model, b: (FAKE, {}))
    assert V.analyze_frame(b"photo")[0] is not None



def test_daily_quota_skips_that_model_for_the_rest_of_the_run(monkeypatch):
    # Real failure 10 Oct: 429 GenerateRequestsPerDayPerProjectPerModel-FreeTier on the first model
    calls = []
    first = V.config.VISION_MODELS[0]
    def fake(model, b):
        calls.append(model)
        if model == first:
            raise RuntimeError("429 RESOURCE_EXHAUSTED quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier")
        return FAKE, {}
    monkeypatch.setattr(V, "_call_model", fake)
    monkeypatch.setattr(V.time, "sleep", lambda s: None)
    V.analyze_frame(b"frame 1")
    V.analyze_frame(b"frame 2")
    assert calls.count(first) == 1  # tried once, never again


def test_per_minute_limit_waits_and_retries_same_model(monkeypatch):
    calls = []
    def fake(model, b):
        calls.append(model)
        if len(calls) == 1:
            raise RuntimeError("429 RESOURCE_EXHAUSTED GenerateRequestsPerMinutePerProjectPerModel-FreeTier")
        return FAKE, {}
    monkeypatch.setattr(V, "_call_model", fake)
    monkeypatch.setattr(V.time, "sleep", lambda s: None)
    out, tel = V.analyze_frame(b"x")
    assert calls == [V.config.VISION_MODELS[0]] * 2 and tel["model"] == V.config.VISION_MODELS[0]


def test_model_rejecting_thinking_setting_is_retried_without_it(monkeypatch):
    # Real failure 10 Oct: 400 "Thinking level MINIMAL is not supported for this model"
    seen = []
    def fake(model, b):
        seen.append(model in V._no_thinking_cfg)
        if model not in V._no_thinking_cfg:
            raise RuntimeError("400 INVALID_ARGUMENT Thinking level LOW is not supported for this model")
        return FAKE, {}
    monkeypatch.setattr(V, "_call_model", fake)
    out, tel = V.analyze_frame(b"x")
    assert out is not None and seen == [False, True]
    assert tel["model"] == V.config.VISION_MODELS[0] and tel["thinking"] is None