import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import config, pipeline, voice
from app.report import write_report
from app.stages import quality, resolve, vision

app = FastAPI(title="Library Contents Claim Agent")
os.makedirs("runs", exist_ok=True)
app.mount("/runs", StaticFiles(directory="runs"), name="runs")  # report + frames open in the browser

_vision_pool = ThreadPoolExecutor(max_workers=1)  # free-tier vision quota: one call at a time
_identify_pool = ThreadPoolExecutor(max_workers=config.IDENTIFY_WORKERS)
SWEEPS = {}
_lock = threading.Lock()


class SayIn(BaseModel):
    text: str


class StartIn(BaseModel):
    country: str = config.COUNTRY
    currency: str = config.CURRENCY


def _thumb(image):
    return cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (64, 48), interpolation=cv2.INTER_AREA).astype(np.int16)


def is_new_view(thumb, last_thumb):
    return last_thumb is None or float(np.mean(np.abs(thumb - last_thumb))) >= config.KEYFRAME_MIN_CHANGE


def unit_name(marker_id):
    return chr(ord("A") + marker_id) if 0 <= marker_id < 26 else str(marker_id)


def frame_advice(spines):
    """What to say after reading a frame: step closer if most spines are unreadable, else what was logged."""
    if len(spines) >= config.STEP_CLOSER_MIN_SPINES:
        poor = sum(sp.legibility in ("partial", "unreadable") for sp in spines) / len(spines)
        if poor >= config.STEP_CLOSER_UNREADABLE:
            return "Most spines here are hard to read. Please step closer to this shelf."
    readable = sum(bool(sp.text.strip()) and sp.legibility != "unreadable" for sp in spines)
    return f"Logged {len(spines)} books here, {readable} readable." if spines else None


def _read_in_background(sweep_id, path):
    """Vision + identification now, so Finish only has to assemble cached results."""
    s = SWEEPS[sweep_id]
    with open(path, "rb") as f:
        res, tel = vision.analyze_frame(f.read())
    with _lock:
        s["frames_read"] += 1
        if res is None:
            s["frames_failed"] += 1
            return
        s["spines_seen"] += len(res.spines)
        s["items_seen"] += [it.category for it in res.items]
        advice = frame_advice(res.spines)
        if advice:
            s["advice"].append(advice)
        art = [it for it in res.items if pipeline.is_art(f"{it.category} {it.description}")]
        if art:  # the brief: "is that portrait an original or a print?" - only the user can answer
            s["art_frame"] = os.path.basename(path)
            s["advice"].append(f"Is that {art[0].description or art[0].category} an original or a print?")
    for sp in res.spines:
        if sp.text.strip() and sp.legibility != "unreadable":
            _identify_pool.submit(_identify, sweep_id, sp)


def _identify(sweep_id, spine):
    r = resolve.resolve_spine(spine.model_dump())  # cached on disk -> reused by the final pipeline run
    if r.get("status") == "identified":
        with _lock:
            SWEEPS[sweep_id]["titles"].append(r["match"]["title"])


@app.get("/")
def index():
    return FileResponse(os.path.join("live", "index.html"))


@app.post("/api/sweep/start")
def start(body: StartIn):
    sweep_id = time.strftime("live_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:4]
    folder = os.path.join("runs", sweep_id, "incoming")
    os.makedirs(folder, exist_ok=True)
    SWEEPS[sweep_id] = {"country": body.country.upper(), "currency": body.currency.upper(), "folder": folder,
                        "started": time.time(), "kept": 0, "seen": 0, "last_thumb": None, "frames_read": 0,
                        "frames_failed": 0, "spines_seen": 0, "items_seen": [], "titles": [], "futures": [],
                        "prev_thumb": None, "advice": [], "units_seen": [], "current_unit": None, "frame_unit": {},
                        "last_frame": None, "art_frame": None, "excluded_units": set(), "excluded_frames": set(),
                        "book_notes": {}, "art_print": set(), "art_original": set(), "heard": []}
    return {"sweep_id": sweep_id}


@app.post("/api/sweep/{sweep_id}/frame")
async def frame(sweep_id: str, file: UploadFile):
    s = SWEEPS.get(sweep_id)
    if not s:
        raise HTTPException(404, "unknown sweep")
    data = await file.read()
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(400, "not an image")
    q = quality.check_frame(image)
    s["seen"] += 1
    kept = False
    thumb = _thumb(image)
    too_fast = s["prev_thumb"] is not None and float(np.mean(np.abs(thumb - s["prev_thumb"]))) > config.TOO_FAST_CHANGE
    s["prev_thumb"] = thumb
    for m in q.get("markers", []):
        if m["id"] < 10:
            s["current_unit"] = m["id"]
        if m["id"] < 10 and m["id"] not in s["units_seen"]:  # shelf markers 0-9 = shelving units A, B, ...
            s["units_seen"].append(m["id"])
            if len(s["units_seen"]) > 1:
                s["advice"].append(f"New shelving unit {unit_name(m['id'])}. Logging it now.")
    # A frame without a marker is still useful for reading titles; only blur/dark/glare make it useless.
    usable = not any(i in q["issues"] for i in ("blurry", "dark", "glare"))
    if usable and is_new_view(thumb, s["last_thumb"]):
        path = os.path.join(s["folder"], f"{s['kept']:04d}.jpg")
        with open(path, "wb") as f:
            f.write(data)
        s["kept"] += 1
        s["last_thumb"] = thumb
        s["last_frame"] = os.path.basename(path)
        s["frame_unit"][s["last_frame"]] = s["current_unit"]
        s["futures"].append(_vision_pool.submit(_read_in_background, sweep_id, path))
        kept = True
    # Priority: a capture problem now > moving too fast > what the background reader has to say
    hint = q["hint"] if any(i in q["issues"] for i in ("blurry", "dark", "glare")) else None
    if not hint and too_fast:
        hint = "Slow down a little, I may be missing books."
    with _lock:
        if not hint and s["advice"]:
            hint = s["advice"].pop(0)
    if not hint:
        hint = q["hint"]  # e.g. no marker in view
    return {"kept": kept, "quality": {k: v for k, v in q.items() if k != "markers"}, "hint": hint,
            "inventory": inventory(sweep_id)}


@app.post("/api/sweep/{sweep_id}/say")
def say(sweep_id: str, body: SayIn):
    """A voice correction. It applies to what the camera was on when it was spoken (the last kept frame)."""
    s = SWEEPS.get(sweep_id)
    if not s:
        raise HTTPException(404, "unknown sweep")
    c = voice.parse(body.text)
    s["heard"].append({"text": body.text, "cmd": c["cmd"], "frame": s["last_frame"], "t": round(time.time() - s["started"], 1)})
    frame_now = s["last_frame"]
    if c["cmd"] == "skip_shelf":
        if s["current_unit"] is not None:
            s["excluded_units"].add(s["current_unit"])
            return {"cmd": c["cmd"], "reply": f"Okay, I will leave shelving unit {unit_name(s['current_unit'])} out of the claim."}
        if frame_now:
            s["excluded_frames"].add(frame_now)
            return {"cmd": c["cmd"], "reply": "Okay, I will leave the books in view out of the claim."}
        return {"cmd": c["cmd"], "reply": "Point the camera at the shelf you want me to skip, then say it again."}
    if c["cmd"] == "book_note":
        if not frame_now:
            return {"cmd": c["cmd"], "reply": "Point the camera at that book, then tell me again."}
        s["book_notes"].setdefault(frame_now, []).append(c["note"])
        return {"cmd": c["cmd"], "reply": f"Noted, {c['note']}. The book in the centre of the view goes to a human appraiser."}
    if c["cmd"] in ("art_print", "art_original"):
        target = s["art_frame"] or frame_now
        if not target:
            return {"cmd": c["cmd"], "reply": "Show me the picture first, please."}
        s["art_print" if c["cmd"] == "art_print" else "art_original"].add(target)
        return {"cmd": c["cmd"], "reply": "Thanks, I will price it as a print." if c["cmd"] == "art_print"
                else "Understood. An original goes to a human appraiser, not priced automatically."}
    if c["cmd"] == "locale":
        s["country"], s["currency"] = c["country"], c["currency"]
        return {"cmd": c["cmd"], "country": c["country"], "currency": c["currency"],
                "reply": f"Switched to {c['country']}. Prices will be in {c['currency']}."}
    if c["cmd"] == "yes":
        return {"cmd": c["cmd"], "reply": "Great. Start at the first shelf and move slowly along it."}
    return {"cmd": "unknown", "reply": None}


def overrides_for(s):
    """Voice corrections -> pipeline overrides, keyed by frame file name."""
    excluded = set(s["excluded_frames"]) | {f for f, u in s["frame_unit"].items() if u in s["excluded_units"]}
    return {"excluded_frames": excluded, "book_notes": s["book_notes"],
            "art_print": s["art_print"] - s["art_original"], "art_original": s["art_original"]}


@app.get("/api/sweep/{sweep_id}/inventory")
def inventory(sweep_id: str):
    s = SWEEPS.get(sweep_id)
    if not s:
        raise HTTPException(404, "unknown sweep")
    with _lock:
        return {"frames_seen": s["seen"], "frames_kept": s["kept"], "frames_read": s["frames_read"],
                "spines_seen": s["spines_seen"], "identified": len(s["titles"]), "recent_titles": s["titles"][-5:],
                "items_seen": len(s["items_seen"]),
                "shelving_units": [unit_name(i) for i in s["units_seen"]], "elapsed_s": round(time.time() - s["started"], 1)}


@app.post("/api/sweep/{sweep_id}/finish")
def finish(sweep_id: str):
    s = SWEEPS.get(sweep_id)
    if not s:
        raise HTTPException(404, "unknown sweep")
    t0 = time.time()
    for fut in s["futures"]:
        fut.result()  # wait for the last frames still being read
    waited = time.time() - t0
    packet, out_dir = pipeline.run_sweep(s["folder"], sweep_id, s["country"], s["currency"], device="phone browser",
                                         overrides=overrides_for(s))
    packet.telemetry["voice_corrections"] = s["heard"]
    packet.sweep.duration_s = round(t0 - s["started"], 1)
    packet.telemetry["after_sweep_wait_s"] = round(waited, 2)
    packet.telemetry["packet_ready_after_sweep_s"] = round(time.time() - t0, 2)
    with open(os.path.join(out_dir, "claim_packet.json"), "w", encoding="utf-8") as f:
        f.write(packet.model_dump_json(indent=2))
    write_report(packet, os.path.join(out_dir, "report.html"))
    t = packet.totals
    summary = (f"Done. I counted {t.book_count} books, {t.books_identified} identified. "
               f"Replacement value about {t.books_replacement_cost:,.0f} {s['currency']} for the books. "
               f"{len(packet.review_queue)} lines need a human check.")
    return {"summary": summary, "report": f"/runs/{sweep_id}/report.html", "packet": f"/runs/{sweep_id}/claim_packet.json",
            "books": t.book_count, "identified": t.books_identified, "review_items": len(packet.review_queue),
            "packet_ready_after_sweep_s": packet.telemetry["packet_ready_after_sweep_s"]}