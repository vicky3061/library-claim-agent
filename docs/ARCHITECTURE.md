# Architecture: Library Contents Claim Agent

Principle: models see; code and databases decide.** A vision model reads what is visible.
Titles come from book catalogues, prices from retrievable listings, sizes from printed markers,
totals from Python. Anything without evidence stays empty and goes to the review queue.

```
 Phone browser (camera + mic)                         Server (FastAPI, Python)
 ┌──────────────────────────┐   frame every 2 s   ┌───────────────────────────────────────────────┐
 │ live/index.html          │ ──────────────────▶ │ Quality check (code): blur, glare, dark,       │
 │  - camera preview        │                     │   marker in view  ──▶ spoken hint back         │
 │  - spoken hints          │ ◀────────────────── │ Keyframe filter: keep good AND new views       │
 │  - live inventory panel  │   hint + inventory  │        │                                       │
 └──────────────────────────┘                     │        ▼  (background, DURING the sweep)       │
   TODO slice 2: Gemini Live voice in/out,        │ 1. Vision (Gemini Flash): spines + items,      │
   corrections, art question                      │    visible letters only, age cues, material    │
                                                  │ 2. Scale (OpenCV ArUco): marker → cm/px        │
                                                  │ 3. Identify: Google Books + Open Library,      │
                                                  │    field-wise fuzzy match, ambiguity margin    │
                                                  │        │                                       │
                                                  │        ▼  on Finish                            │
                                                  │ 4. Price books: Amazon IN/US (SerpAPI),        │
                                                  │    used: Google Shopping, FX: open.er-api      │
                                                  │ 5. Price items: brand price or sourced range   │
                                                  │ 6. Totals + review queue (pure Python)         │
                                                  │        ▼                                       │
                                                  │ claim_packet.json + report.html + frames/      │
                                                  └───────────────────────────────────────────────┘
```

## Which model / service does what
| Stage | Tool | Why |
|---|---|---|
| Spine + item detection, spine text | Gemini Flash (fallback list in `app/config.py`), JSON schema output, temperature 0 | Reads text well; told to transcribe only, never complete a title |
| Title / author / edition | Google Books API + Open Library (cached) | A catalogue decides, not the model → no invented titles |
| New price | Amazon.in / Amazon.com via SerpAPI | Retrievable URL + date; physical formats only |
| Used price | Google Shopping pre-owned listings via SerpAPI | Capped at the new price |
| Currency conversion | open.er-api.com (dated rate stored per price) | Only when no local listing exists; labelled "converted" |
| Quality checks, scale, totals, review queue | Python + OpenCV | Deterministic, testable, free |

## Where metric scale comes from
Printed ArUco markers (`tools/make_markers.py`): 10 cm on shelves (IDs 0–9), 18 cm on walls (IDs 10–19).
The marker's 4 corners give a homography from pixels to centimetres on the marker's plane.
Measured on a real wall: ~1.1–1.5% error. No marker in view → sizes stay empty + review entry.
TODO: room dimensions from wall markers (Layer 10); fallback scale from a known shelf height.

## Where prices come from, and what is never auto-priced
Every price stores amount, currency, source, URL, retrieval time, and (if converted) the original amount and FX rate.
Not auto-priced → "needs appraisal": antiquarian appearance on the spine (blackletter, leather, or 2+ age cues),
"signed / first edition / limited" on the spine or from the policyholder, replacement above ₹5,000 / $60, art.

## Latency and cost (measured, dev photo)
Identification 125.9 s → 29.1 s for 14 spines after parallel calls + catalogue cache (warm: 0.3 s).
Vision runs during the sweep. Cost per sweep = measured tokens and searches × list prices (`telemetry.cost`).
TODO: full-sweep numbers from the library run.