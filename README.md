# Library Contents Claim Agent

A live voice-and-vision agent that inventories a home library from one camera sweep and produces an insurance **claim packet**: every book counted, read from its spine, measured and priced at local market value; every non-book item identified and priced; room surface area. Uncertain lines go to a review queue instead of being guessed.

**Principle: models see; code and databases decide.** The vision model only reports what is visible. Titles come from catalogues, prices from live listings with URLs and dates, sizes from printed markers, totals from code.

## Results at a glance
Real space: **Neptunes Books, Bengaluru (with the owner's permission)** — top row of two bookcases, 73 books, 8 non-book items, hand-collected ground truth.

| Bar | Result |
|---|---|
| Book count ±5% | **PASS** — 73 / 73 |
| Titles ≥70% correct, ≤3% wrong | **PASS** — 84% correct, 1.8% wrong |
| Non-book items ≥80% | **PASS** — 8 / 8 |
| Spine dims ±15% | FAIL — 18/36 within (explained) |
| Prices ±25% | FAIL — 8/15 within (explained) |
| Floor / wall area | not scored (room not tape-measured; see Deviations) |

Details: [`docs/RESULTS.md`](docs/RESULTS.md) · root causes and fixes: [`docs/FAILURE_LOG.md`](docs/FAILURE_LOG.md) · pipeline: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · packets: [`submission/`](submission/)

## Quick start (about 10 minutes)
Requires **Python 3.12** and a **Chrome** browser (phone or laptop).

```powershell
git clone https://github.com/vicky3061/library-claim-agent library-claim-agent
cd library-claim-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env                 # macOS/Linux: cp .env.example .env
```
Open `.env` and fill in the keys listed there (a Google Gemini API key from aistudio.google.com, and a SerpAPI key from serpapi.com; the free tiers are enough to try it). Keys are never committed and never written to the cache.

Check everything works (no keys needed):
```powershell
python -m pytest -q                    # 112 tests
```

### 1. Live agent (phone or laptop)
```powershell
python -m uvicorn app.server:app --host 0.0.0.0 --port 8000
```
- **Laptop:** open http://localhost:8000 in Chrome.
- **Phone:** the camera needs HTTPS, so expose the server with a tunnel, e.g. `cloudflared tunnel --url http://localhost:8000`, and open the printed `https://…trycloudflare.com` URL in Chrome on the phone.

Press **Start sweep**, say **"yes"** to confirm country and currency, and walk slowly along the shelves. The agent speaks back (blur, glare, too fast, step closer, new shelving unit), the inventory fills in on screen, and you can correct it by voice: *"skip that shelf, those are not mine"*, *"this one is a first edition"*, *"it's a print"*, *"finish"*. The packet is written to `runs/<sweep_id>/` (`claim_packet.json`, `report.html`, `frames/`).

### 2. Offline run on a folder of frames, and scoring
```powershell
python -m app.pipeline ground_truth\neptunes\frames --sweep-id my_run --price-limit 25
python -m tools.evaluate runs\my_run\claim_packet.json ground_truth\neptunes
python -m app.pipeline ground_truth\neptunes\frames --sweep-id my_run_us --country US --currency USD --price-limit 14
```
`--price-limit` caps paid searches; unpriced books are flagged, never invented. Every external call is cached in `runs/cache/`, so a re-run costs nothing. Frames named `items_*.jpg` count non-book items only.

## Print and place the markers (metric scale)
Metric sizes come **only** from printed ArUco markers (DICT_4X4_50) of known size — never from the model.
- Printable sheets: `markers_A4.pdf` — print at **100% / actual size**, then check the black square with a ruler: **10.0 cm** for shelf markers (IDs 0–9, one per shelving unit, letter A, B, …) and **18.0 cm** for wall markers (IDs 10–13, one per wall, clockwise).
- Tape the shelf marker beside each bookcase **flush with the spines** (not on the wall behind — books further back look smaller; see failure log #1).
- Without markers the agent still counts, reads and prices; sizes and room area are left empty and flagged.

## Repository map
| Path | What |
|---|---|
| `app/server.py`, `live/index.html` | live agent: FastAPI + browser camera and speech |
| `app/pipeline.py` | stages: vision → dedup → identify → price → measure → totals |
| `app/stages/` | `vision` (Gemini), `resolve` (catalogue), `price`, `item_price`, `measure`, `room`, `dedup`, `quality`, `scale` |
| `app/totals.py`, `app/report.py`, `app/schema.py` | totals and review queue in code, HTML report, packet schema |
| `tools/evaluate.py` | scores a packet against ground truth, PASS/FAIL per bar |
| `ground_truth/neptunes/` | hand-collected ground truth (books, spines, prices, items, room) and frames |
| `submission/` | packets, reports and frames from the scored runs (India and US) and the demo sweep |
| `tests/` | 112 tests |

## Deviations from the brief (stated honestly)
1. **The shop's live sweep failed** (one vision call took 99.5 s, so the phone showed "read 0"; fixed the same evening — failure log #3). The **scored packet** was produced by the same pipeline from photos taken during that visit: 2 keyframes of the shelf row and 4 photos of non-book items. That is not one continuous sweep, and the item photos were taken one by one — both against the brief's capture rule.
2. **No demo video at submission time.** Recording failed on the night (Chrome's speech recognition holds the phone microphone, so the screen recorder captured no voice). Evidence instead: a live phone sweep at home after the fix, with my own books, in `submission/demo/` (packet, frames, screenshots; packet ready 87.4 s after Finish). It is small (2 books) and imperfect: one spine left unidentified, the same desk mat listed three times (two of them flagged for review) and no spine sizes. The video will follow by reply.
3. **Room area not validated:** the shop did not permit room measurement; at home, furniture covers the walls. The room code is unit-tested on synthetic rooms only.
4. **Frames were cropped to the claim scope (row 1)** before the run; originals are in `ground_truth/neptunes/photos/`.
5. **Ground-truth titles:** legible titles were transcribed by hand from my close-up shop photos; illegible ones were checked from the covers in the shop. Prices were hand-checked on Amazon.in on 10 Oct 2026.

## Assumptions
- "Replacement cost" = a new copy of the same title in the local market today; "used value" = a matching used listing, condition assumed *Good*. Both carry source URL and retrieval date.
- Rare, signed, antiquarian, user-declared first editions, art, and anything above the threshold in `app/config.py` go to human appraisal and are not auto-priced.
- Scope of the shop claim: top row of bookcases F-6 and F-7 only.

## Models, services and tools
- **Google Gemini Flash** (hosted, pretrained) — reads spines and items. No training or fine-tuning.
- **Browser Web Speech API** — speech recognition and synthesis.
- **OpenCV** (ArUco, homography, ORB) — scale, orientation, dedup. **rapidfuzz** — fuzzy matching.
- **Google Books, Open Library** — catalogue. **SerpAPI** (Amazon, Google Shopping) — prices. **open.er-api.com** — exchange rates.
- **Claude (Anthropic)** — used as an AI coding assistant during development. I have reviewed and can explain every line.

## Reference app: kept, changed, threw away
- **Kept:** the interaction pattern — live camera + two-way voice, a claim file that builds while the user talks, background workers that finish the packet after the sweep.
- **Changed:** the agent *measures, counts and prices* instead of describing; it directs the capture (blur, glare, too fast, step closer, new shelving unit); voice corrections are tied to the frame in view; Gemini Live was replaced by browser speech plus per-frame Gemini Flash calls so every number can be traced and tested.
- **Threw away:** the narrative notebook and policy-check agents; nothing in the packet is written by a language model.

