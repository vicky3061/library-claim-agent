# Library Contents Claim Agent

Live voice-and-vision agent that inventories and values a home library in one camera sweep and produces a traceable insurance claim packet.

> Built with Claude as a coding assistant. Design decisions, data investigation, testing and debugging were done by me; all code was reviewed and explained line by line.

## Quick start (about 15 minutes)
```bash
python3.12 -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # Windows: copy .env.example .env  -> then add your keys
python -m pytest -q           # all stages are tested offline (no keys needed)
```
Keys in `.env`: `GOOGLE_API_KEY` (Gemini), `GOOGLE_BOOKS_API_KEY`, `SERPAPI_KEY`. Locale: `COUNTRY`, `CURRENCY`.

**Markers:** print `markers_A4.pdf` at 100% / Actual size and check the 10 cm ruler line
(regenerate with `python tools/make_markers.py`). Put one 10 cm marker on each shelving unit, 18 cm markers on walls.

## Run
| What | Command |
|---|---|
| Live sweep (phone) | `python -m uvicorn app.server:app --port 8000`, then expose it over HTTPS (e.g. `cloudflared tunnel --url http://localhost:8000`) and open the URL on the phone |
| Live sweep (laptop test) | same server, open http://localhost:8000 |
| Packet from a folder of frames | `python -m app.pipeline <frames_dir> --sweep-id <id> [--country US --currency USD]` |
| Score against ground truth | `python -m tools.evaluate runs/<id>/claim_packet.json ground_truth/<space>` |
| Frame quality metrics | `python -m tools.quality_report <frames_dir>` |

Output per sweep: `runs/<id>/claim_packet.json`, `runs/<id>/report.html`, `runs/<id>/frames/` (every `frame_ref` opens).

## Design principles
1. **The model sees; code and databases decide.** Vision reads spines and finds objects. Titles come from catalogue matches, prices from stored listings, totals from Python.
2. **Unknown is null.** No field is filled without evidence. Unknown lines go to the review queue.
3. **Every number is traceable.** Books and items point to a saved frame; prices carry source, URL and retrieval time.
4. **Nothing is tuned to one room.** All thresholds live in `app/config.py`.

See `docs/ARCHITECTURE.md` for the pipeline diagram.

## Assumptions
- Default locale India / INR; second locale US / USD. Locale is a setting.
- Used value assumes condition "Good" unless the user says otherwise.
- Appraisal (not auto-priced): antiquarian appearance on the spine, signed / first / limited edition, price above ₹5,000 / $60, art.
- The catalogue's publication year describes the work, not the copy on the shelf, so it never triggers appraisal on its own.
- Wall area is gross: perimeter × ceiling height, doors and windows not subtracted.
- Placing printed markers before the sweep is allowed; they are reference objects, not a separate measuring pass.
- Books whose spines are fully hidden (double rows, closed cabinets) are out of scope and counted as missed.
- Non-book items are priced in the local market only (no conversion); without a legible brand, a sourced range (middle 50% of new listings).

## Reference app: kept / changed / threw away
TODO: final wording after re-checking the reference code (draft in NOTES.md).

## Ground truth and results
TODO: `ground_truth/` and results table from `tools/evaluate.py`.

## Models, APIs and tools used
Gemini Flash (vision), Google Books API, Open Library, SerpAPI (Amazon, Google Shopping), open.er-api.com (FX),
OpenCV (ArUco markers, quality checks), FastAPI, Pydantic, rapidfuzz, pytest. Coding assistant: Claude.

## Cost per sweep
Measured usage × list prices, reported in `telemetry.cost`. Prices are set in `app/config.py` with their date;
if a price is not set, the cost is reported as unknown rather than estimated.