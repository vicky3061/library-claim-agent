# Failure log

Run under test: **Neptunes Books (AECS Layout, Bengaluru), top row of bookcases F-6 and F-7, 73 books, 8 non-book items**, scored against hand-collected ground truth (`ground_truth/neptunes/`). Runs v1 → v4 are the same frames; every fix below was made *after* seeing a measured failure and is reported with its before/after number. Nothing was tuned to the ground-truth values.

## The three worst errors

### 1. Spine sizes fail the ±15% bar (18 of 36 dimensions within; median error 14.9%)
- **What happened:** heights are consistently **5–17% too small**; thicknesses were **30–135% too big** in v1.
- **Root causes (two):**
  - *Height:* the shelf marker was taped to the **front edge** of the bookcase, but the books stand **further back** on the shelf, so they appear smaller than the marker's scale says. Evidence: F-7's marker sat closer to the books' plane and F-7 heights are better (−5 to −10%) than F-6 (−11 to −17%).
  - *Thickness:* the vision model's boxes for neighbouring spines **overlap** (padding), so every book is measured fatter than it is.
- **Measured fix (v2):** books cannot overlap, so within each run of touching spines (and each flat stack) thicknesses are scaled so the books exactly fill the span they occupy (`measure.thickness_factors`). Result: 17/36 → **18/36** within, median 15.5% → **14.9%**. Real but small.
- **What I would change:** stand the marker **on the shelf, flush with the spines** (a capture-protocol fix, not a code fix); detect spine edges with image gradients inside each box instead of trusting the model's box; report a per-book size confidence.

### 2. Book prices fail the ±25% bar (8 of 15 within; median error 0%)
- **What happened:** 8 books match the hand check exactly (same Amazon.in listing); 7 are far off in both directions, e.g. *A Stranger in the Mirror* ₹2,482 vs ₹329 hand-checked, *Secret Star* ₹4,000 vs ₹799, *The Stars Shine Down* ₹142 vs ₹5,129.
- **Root cause:** Amazon lists the same title as many editions (₹300 Indian reprint, ₹2,000+ import, omnibus, collectible). The picker takes **one** listing; the human took another. The same two titles are outliers in the **US run too** (*A Stranger in the Mirror* $25.62, *Born in Fire* $20.98 vs $4–10 for the rest), so it is the edition choice, not the market. Related: **same title, different author** — *Sisters* (Danielle Steel) was priced as Raina Telgemeier's graphic novel; *The Stars Shine Down* as a book by Rachel Lawson.
- **Measured fix (v4):** when the catalogue returns the same title by several authors, the author most common among the other books **in the same frame** is chosen (shelves are grouped by author). *The Stars Shine Down* (4 copies) moved from Rachel Lawson to Sidney Sheldon. *Sisters* was **not** fixed: Danielle Steel's book was never among the catalogue candidates.
- **What I would change:** price the **median of all matching new paperback listings** and send a wide spread to review instead of picking one; re-query the catalogue with the shelf's dominant author when the spine author is unreadable; reject listings whose title contains omnibus/set words.

### 3. The live sweep in the shop read 0 frames
- **What happened:** at Neptunes the phone kept frames (35/44, both shelf markers found) but showed **"read 0"**; the agent also heard its own voice, nagged "no marker" all sweep, and frames arrived rotated 90°.
- **Root causes:** one vision call took **99.5 s** (model default "thinking") and frames were read **one at a time**; the free daily quota of that model then ran out; no timeout, and failures were not shown. Rotation: browser/phone orientation mismatch. Echo: speaker → microphone.
- **Measured fix:** thinking level LOW and model order changed — **99.5 s → 19.3 s per frame** on the same shop frame (39 vs 41 spines found); 3 frames read in parallel; 60 s timeout; daily-quota models skipped; failures printed and shown in red. Frames are turned upright from the marker's printed orientation; speech that matches the agent's own recent words is ignored; the marker tip is spoken only until the first marker is seen. After the fix the same flow at home read frames within seconds and produced the packet live (see demo video).
- **What I would change:** a streaming vision model for live hints, and the whole sweep re-tested in the shop (not possible: closed by the time the fix was ready).

## Other errors found and fixed
| Error | Fix | Measured |
|---|---|---|
| Our ArUco sheets listed as "decor" items; a book on the sofa listed as an item | items on a detected marker, described as a marker, or called "book" are dropped | 20 → 16 items, still 8/8 found |
| Same object in two photos claimed twice (aquarium, chair) | flagged in the review queue, never auto-merged | — |
| Pricing stalled (SerpAPI calls retried 4 × 30 s) | 2 tries, 8 workers, books priced live during the sweep | price stage 475 s → 62 s |
| One confidently wrong title: *The MacGregors* for a spine reading *The Magic Home* | not fixed | 1/57 = 1.8% wrong (bar ≤3%) |

## Known limits (not fixed)
- **Room area not validated:** the shop did not permit room measurement; at home furniture covers the walls, so whole-wall photos with all corners were not possible. The room code (wall-marker homography) is built and unit-tested on synthetic rooms only.
- **Scored run used photos, not one continuous sweep** (see README, "Deviations").

## Cost per sweep
| Item | Neptunes run (cold) | Unit price | Cost |
|---|---|---|---|
|Vision row, Unit price: free tier (no charge); Cost: $0 billed|
|SerpAPI row, Cost: $0 billed (free plan, 250 searches/month)|
| Catalogue (Google Books, Open Library), FX | free APIs | $0 | $0 |

Everything is cached on disk: re-running the same sweep costs nothing.

On paid tiers, cost = tokens x Google's per-token price + searches x SerpAPI plan price; usage counts per sweep are in each packet's telemetry.

## Latency per stage (seconds)
| Stage | v1 (cold) | v2 (4 new frames, model busy 503) | v4 (warm cache) |
|---|---|---|---|
| Vision | cached | 98.8 | 0.4 |
| Identify | 0.1 | 0.1 | 0.2 |
| Price books | **475.2** | 228.0 | 62.3 |
| Total to packet | **604.5** | 456.9 | **63.2** |
| Live (home, demo) | — | — | packet ready *X s* after Finish |

One vision call: 99.5 s (gemini-3.8-flash, default thinking) → 19.3 s (gemini-3.6-flash, thinking LOW).

## What I would do with two more weeks
1. **Marker-free book scale:** once a few books are identified, use their real dimensions from the catalogue (Google Books often lists height x width) to calibrate every other spine on the same shelf.
2. **Room area without wall markers:** WebXR / ARCore depth in the phone browser, which works in cluttered rooms where whole-wall photos are impossible (the reason my own room could not be measured).
3. **Price the median of all matching new paperbacks** and send a wide edition spread to review (fixes error #2).
4. **Per-camera blur calibration** from the first frames: the threshold tuned on phone photos rejected every laptop-webcam frame.
5. **Re-run the full live sweep in the shop** with the fixed latency, to replace the photo-based scored run.
