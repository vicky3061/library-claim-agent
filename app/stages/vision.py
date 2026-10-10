import hashlib
import json
import os
import time

import cv2
from google import genai
from google.genai import types
from pydantic import BaseModel

from app import config

PROMPT = """You are inventorying a home library from one photo for an insurance claim.

Return every BOOK SPINE you can see, including books lying flat or stacked.
For each spine:
- box_2d: [ymin, xmin, ymax, xmax] of the spine, each scaled 0-1000 to the image.
- orientation: "upright" or "flat".
- text: ONLY the letters and words you can actually read on that spine, exactly as printed
  (title, author, publisher, volume numbers). Do NOT guess or complete a title from memory.
  If you cannot read it, return "".
- title, author, publisher, volume: split the SAME visible words into these fields, copying them
exactly. Use "" for any part that is not printed on the spine. Never add words that are not visible.
- legibility: "clear", "partial" or "unreadable".
- cut_off: true if the spine is cut off by the edge of the photo.
- age_cues: list ONLY what you can actually see on this spine, chosen from: "blackletter" (Gothic/Fraktur typeface),
  "cloth_binding", "leather_binding", "gilt_lettering", "heavy_wear". Return [] if none or unsure.

Also return every NON-BOOK item (shelving, furniture, lamps, framed art, electronics, decor, rugs):
- box_2d as above, category (one or two words), description (short), visible_text (brand/model text you can read, else ""),
  material (main visible material: wood, metal, glass, fabric, plastic, ceramic, paper; "" if unsure).

Do not invent items. If unsure whether something is a separate book, return it once."""


class SpineOut(BaseModel):
    box_2d: list[int]
    orientation: str
    text: str            # everything readable on the spine, exactly as printed
    title: str = ""      # the words that are the title, copied exactly; "" if not visible
    author: str = ""
    publisher: str = ""
    volume: str = ""     # e.g. "I", "2", "Band 3"
    legibility: str
    cut_off: bool
    age_cues: list[str] = []


class ItemOut(BaseModel):
    box_2d: list[int]
    category: str
    description: str
    visible_text: str
    material: str = ""


class FrameOut(BaseModel):
    spines: list[SpineOut]
    items: list[ItemOut]


RETRYABLE = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "500", "INTERNAL")
_client = None
_exhausted = set()       # models whose free DAILY quota is used up: skip them for the rest of this run
_no_thinking_cfg = set()  # models that reject our thinking setting: call them without it


def _get_client():
    global _client
    if _client is None:
        # a timeout so one slow call can never block the live sweep for minutes (seen: 99.5 s per frame)
        _client = genai.Client(http_options=types.HttpOptions(timeout=int(config.VISION_TIMEOUT_S * 1000)))
    return _client


def _call_model(model, image_bytes):
    cfg = dict(response_mime_type="application/json", response_schema=FrameOut, temperature=0)
    if config.VISION_THINKING_LEVEL and model not in _no_thinking_cfg:
        # reading spines is transcription, not reasoning: low thinking cut one frame from 99.5 s to 19.3 s
        cfg["thinking_config"] = types.ThinkingConfig(thinking_level=config.VISION_THINKING_LEVEL)
    resp = _get_client().models.generate_content(
        model=model,
        contents=[types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"), PROMPT],
        config=types.GenerateContentConfig(**cfg))
    usage = resp.usage_metadata
    tokens = {"input": getattr(usage, "prompt_token_count", None), "output": getattr(usage, "candidates_token_count", None),
              "thinking": getattr(usage, "thoughts_token_count", None)}
    return FrameOut.model_validate_json(resp.text), tokens


def _cache_path(image_bytes):
    # the prompt is part of the key: if we change the prompt, old answers are not reused
    key = hashlib.sha1(image_bytes + PROMPT.encode()).hexdigest()[:16]
    return os.path.join(config.CACHE_DIR, "vision", f"{key}.json")


def analyze_frame(image_bytes, tries=3):
    """Cached wrapper: the same photo + prompt is only ever sent to the model once."""
    path = _cache_path(image_bytes)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        return FrameOut.model_validate(saved["result"]), {**saved["telemetry"], "cache_hit": True}
    out, telemetry = _analyze_uncached(image_bytes, tries)
    if out is not None:  # failures are not cached, so they are retried next time
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"result": out.model_dump(), "telemetry": telemetry}, f, ensure_ascii=False)
    return out, {**telemetry, "cache_hit": False}


def _analyze_uncached(image_bytes, tries=3):
    """Returns (FrameOut or None, telemetry).
    Overload / per-minute limit -> wait and retry the same model. Daily quota used up -> skip that model from now on.
    Model rejects the thinking setting -> retry it once without. Anything else -> next model in the list."""
    telemetry = {"attempts": [], "model": None}
    for model in config.VISION_MODELS:
        if model in _exhausted:
            continue
        delay = 2.0
        attempt = 0
        while attempt < tries:
            attempt += 1
            t0 = time.time()
            try:
                out, tokens = _call_model(model, image_bytes)
                telemetry.update(model=model, tokens=tokens, latency_s=round(time.time() - t0, 2),
                                 thinking=None if model in _no_thinking_cfg else config.VISION_THINKING_LEVEL)
                return out, telemetry
            except Exception as e:
                msg = str(e)
                telemetry["attempts"].append({"model": model, "error": msg[:200]})
                print(f"[vision] {model}: {msg[:160]}", flush=True)  # never fail silently again
                if "400" in msg and "thinking" in msg.lower() and model not in _no_thinking_cfg:
                    _no_thinking_cfg.add(model)
                    attempt -= 1  # a settings problem, not a real attempt
                    continue
                if "PerDay" in msg:
                    _exhausted.add(model)
                    break
                if "quota" in msg.lower() and "PerMinute" not in msg:
                    break  # quota of unknown scope: don't burn time retrying, try the next model
    
                if not any(code in msg for code in RETRYABLE):
                    break  # e.g. 404 retired model, timeout: retrying the same model won't help
                time.sleep(delay)
                delay *= 2
    return None, telemetry

def to_pixels(box_2d, width, height):
    ymin, xmin, ymax, xmax = box_2d
    return (round(xmin / 1000 * width), round(ymin / 1000 * height),
            round(xmax / 1000 * width), round(ymax / 1000 * height))


def annotate(image, frame_out, path):
    """Draw boxes so a human can check detections by eye."""
    h, w = image.shape[:2]
    out = image.copy()
    for i, s in enumerate(frame_out.spines):
        x1, y1, x2, y2 = to_pixels(s.box_2d, w, h)
        color = (0, 200, 0) if s.legibility == "clear" else (0, 200, 255) if s.legibility == "partial" else (0, 0, 255)
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        cv2.putText(out, str(i), (x1 + 2, y1 + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    for it in frame_out.items:
        x1, y1, x2, y2 = to_pixels(it.box_2d, w, h)
        cv2.rectangle(out, (x1, y1), (x2, y2), (255, 0, 255), 2)
    cv2.imwrite(path, out)