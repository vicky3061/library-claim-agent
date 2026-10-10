import re
import sys
import time

from google.genai import types

from app import config
from app.stages import vision


def run(image_bytes, model, thinking):
    t0 = time.time()
    resp = vision._get_client().models.generate_content(
        model=model,
        contents=[types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"), vision.PROMPT],
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=vision.FrameOut,
                                           temperature=0, thinking_config=thinking),
    )
    out = vision.FrameOut.model_validate_json(resp.text)
    u = resp.usage_metadata
    return round(time.time() - t0, 1), len(out.spines), getattr(u, "candidates_token_count", None), getattr(u, "thoughts_token_count", None)


def explain(err):
    """Pull out which quota was hit (per minute or per day) and when to retry."""
    msg = str(err)
    quota = re.findall(r"quotaId'?:\s*'([^']+)'", msg)
    retry = re.findall(r"retryDelay'?:\s*'([^']+)'", msg)
    return f"{msg[:60]} | quota={quota or '?'} retry_after={retry or '?'}"


if __name__ == "__main__":
    image = open(sys.argv[1], "rb").read()
    for model in config.VISION_MODELS:
        try:
            secs, spines, out_tok, think_tok = run(image, model, types.ThinkingConfig(thinking_level="LOW"))
            print(f"{model:18s} {secs:6.1f}s  spines={spines}  output_tokens={out_tok}  thinking_tokens={think_tok}")
        except Exception as e:
            print(f"{model:18s} ERROR {explain(e)}")