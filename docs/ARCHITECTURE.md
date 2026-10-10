# Architecture (one page)

**Principle: models see; code and databases decide.** The vision model only reports what is visible on each spine/item. Titles come from catalogues, prices from live listings with URLs, sizes from printed markers, totals from code. Anything uncertain goes to the review queue with a reason.

```
 Phone browser (camera + Web Speech in/out)
        │ frame every 2 s                ▲ spoken hints / summary
        ▼                                │
 FastAPI live server ── quality check (blur, glare, dark, marker) ── keyframe? ── turn upright (marker)
        │ background, per keyframe (3 parallel)
        ├─► 1 VISION      Gemini Flash: spines {box, text, upright/flat, legibility}, items, wall corners
        ├─► 2 IDENTIFY    Google Books + Open Library, fuzzy match, ambiguity → unidentified; shelf-context author
        └─► 3 PRICE       SerpAPI Amazon (new) + Google Shopping (used), fallback market + FX, rare → appraisal
        │ on "Finish"
        ▼
 PIPELINE (same code offline: python -m app.pipeline <frames>)
   dedup across keyframes (ORB + RANSAC homography, IoU; never merge conflicting titles)
   MEASURE spines/items/walls on marker planes (ArUco homography)
   ITEM PRICING (brand → median listing; unknown → 25–75th percentile range)
   TOTALS + REVIEW QUEUE in code → claim_packet.json + report.html + saved frames
        │
        ▼
 EVALUATE (tools/evaluate.py): packet vs hand ground truth → PASS/FAIL per pass bar
```

| Stage | What does it | Model? |
|---|---|---|
| Spine/item reading | Gemini Flash (3.6, fallbacks 3.7/3.5/3.8), structured JSON, thinking LOW, cached by image+prompt | pretrained, hosted |
| Voice in/out | Browser Web Speech API (en-IN); rule-based command parser (`app/voice.py`) | pretrained (browser) |
| Identification | Google Books + Open Library; rapidfuzz token coverage; thresholds in config | no |
| Metric scale | Printed ArUco markers (10 cm shelf, 18 cm wall); homography gives cm on the marker plane; marker orientation turns frames upright | no (OpenCV) |
| Dedup | ORB features + RANSAC homography between keyframes; union-find | no (OpenCV) |
| Prices | SerpAPI Amazon / Google Shopping; every price has source, URL, retrieval date, condition; FX via open.er-api.com, labelled converted | no |
| Totals, review queue, report | Python (`app/totals.py`, `app/report.py`) | no |

**Where metric scale comes from:** only from printed markers of known size. Shelf marker → spine height/thickness and item sizes; wall markers + model-located wall corners → room length/width/height. No marker in view → size left empty and flagged, never estimated by the model.

**Where prices come from:** live marketplace listings via SerpAPI (Amazon for new, Google Shopping for used), local market first, then a fallback market converted with a dated FX rate. The model never produces a price. Rare/signed/antiquarian cues, "first edition" said by the user, art and items above a threshold go to human appraisal.

**Separate, testable stages:** each stage has its own module and tests (112 pytest tests); every external call is cached on disk; keys only in `.env`.
