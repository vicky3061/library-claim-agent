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
- legibility: "clear", "partial" or "unreadable".
- cut_off: true if the spine is cut off by the edge of the photo.

Also return every NON-BOOK item (shelving, furniture, lamps, framed art, electronics, decor, rugs):
- box_2d as above, category (one or two words), description (short), visible_text (brand/model text you can read, else "").

Do not invent items. If unsure whether something is a separate book, return it once."""


class SpineOut(BaseModel):
    box_2d: list[int]
    orientation: str
    text: str
    legibility: str
    cut_off: bool


class ItemOut(BaseModel):
    box_2d: list[int]
    category: str
    description: str
    visible_text: str


class FrameOut(BaseModel):
    spines: list[SpineOut]
    items: list[ItemOut]


RETRYABLE = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "500", "INTERNAL")
_client = None


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client()  # reads GOOGLE_API_KEY from the environment
    return _client


def _call_model(model, image_bytes):
    resp = _get_client().models.generate_content(
        model=model,
        contents=[types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"), PROMPT],
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=FrameOut, temperature=0),
    )
    usage = resp.usage_metadata
    tokens = {"input": getattr(usage, "prompt_token_count", None),
              "output": getattr(usage, "candidates_token_count", None)}
    return FrameOut.model_validate_json(resp.text), tokens


def analyze_frame(image_bytes, tries=3):
    """Returns (FrameOut or None, telemetry). Retries on overload, then tries the fallback model."""
    telemetry = {"attempts": [], "model": None}
    for model in config.VISION_MODELS:
        delay = 2.0
        for _ in range(tries):
            t0 = time.time()
            try:
                out, tokens = _call_model(model, image_bytes)
                telemetry.update(model=model, tokens=tokens, latency_s=round(time.time() - t0, 2))
                return out, telemetry
            except Exception as e:
                msg = str(e)
                telemetry["attempts"].append({"model": model, "error": msg[:200]})
                if "quota" in msg.lower() or not any(code in msg for code in RETRYABLE):
                    break 
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