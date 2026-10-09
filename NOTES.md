# Build notes (raw material for the failure log)

## 2026-10-09 17:40 — WebXR AR room measurement test
- Built live/ar_test.html: WebXR hit-test on floor corners, polygon area.
- Laptop: "AR NOT supported" (expected, no AR hardware).
- My Android phone: Play Store says ARCore "device isn't compatible".
- iPhone: Safari has no WebXR AR support.
- Decision: primary room measurement = printed markers on each wall
  (homography from marker to wall plane). Works on any phone.
  WebXR kept as an optional path for ARCore-capable phones.

## Reference app errors
- 14x 503 "model experiencing high demand"; 2x 429 image model zero free quota.
- Decision: retry with backoff; failed calls go to review queue; batch vision calls.

## 18:19 — Google Books 429 without API key
- Every Google Books call returned 429 (anonymous quota). Retries took ~7 s per book.
- Book was still identified via Open Library: second catalogue proved its value.
- Risk: 80 books x 7 s = 9+ minutes, breaks the 5-minute packet bar.
- Fix: Google Books API key; later, circuit breaker to stop calling a failing service mid-sweep.

## 18:27 — Google Books pricing check (country=IN)
- Returns INR prices only for ebooks (Atomic Habits: list ₹707.11, retail ₹353.56).
- First priced result was the TAMIL translation (₹289.10): wrong-edition price trap.
- No used prices at all.
- Decisions: physical new price from shopping search as primary; ebook list price as
  labelled fallback (flagged); only price volumes matching title, author AND language;
  used value from shopping listings.


## 18:34 — SerpAPI Google Shopping check (IN), "Atomic Habits James Clear paperback"
- 40 results. Top 10 contained ZERO plain new English copies.
- Found: workbook (pre-owned), Telugu edition, 7 multi-book bundles (₹295–₹699), import ₹2,127.
- Naive first result = ₹1,547 (used workbook); naive cheapest = ₹295 (combo). Both wrong.
- Decisions: strict filter (bundles, derivatives, languages, all title words required),
  split new/used by second_hand_condition, median of matches citing a real listing,
  cache raw responses as evidence.

- Full 40 results: 33 combos, 3 other languages, 1 workbook, 1 plain copy (import, ₹2,127).
- Google Shopping is a poor source for NEW Indian book prices (flooded by combo sellers).
- Next: test Amazon.in via SerpAPI amazon engine as the new-price source.

## 18:37 — SerpAPI Amazon.in check, "Atomic Habits James Clear"
- 21 results. Much cleaner than Google Shopping: genuine listing found (#2, ₹472).
- Still: 6 other-language editions, combos, workbook, 3 look-alike titles,
  and 2 cheap exact-title listings (₹279, ₹349).
- Median of title matches = ₹349, which is 26% below ₹472: would fail the ±25% bar.
- Idea: choose the canonical listing by review count; consider MRP (old_price).

## 18:57 — BUG: US price was $0.00 (audiobook)
- replacement_cost('Atomic Habits', 'US') returned 0.0 USD: the Audible audiobook,
  "free with trial", had the most reviews, so the most-reviewed rule picked it.
- Root cause: no check for non-physical formats or zero prices. Format was only visible in the URL.
- Fix: reject audiobook/Kindle/ebook (title + link) and prices <= 0. Regression test added.

## 19:02 — US price $25.80 was the SPANISH special edition
- ISBN prefix 607 (Mexico) raised suspicion; cache inspection confirmed "Hábitos atómicos (Edición especial)".
- Root causes: language list only had Indian languages; norm() turned accented letters into spaces.
- amazon.com also returned Korean, Chinese, Portuguese editions, posters, a podcast, calendars, unrelated books.
- Genuine product (#0, 150k reviews) was shown in audiobook format; physical price likely in purchase_options.


## 20:51 — Markers printed
- A4, 100% scale; ruler checked with tape: 10.0 cm exactly. Shelf markers 10 cm, wall markers 18 cm.

## 21:28 — First real-photo scale test (green wall, 18 cm marker ID 10, crosses 100.0 cm apart)
- Preliminary on low-res screenshots (~4.8 px/cm): straight 101.9 cm (+1.9%), angled 103.0 cm (+3.0%).
- Angled is worse: corner errors amplify. Live agent should ask user to face walls roughly straight on.
- TODO: repeat on full-resolution originals with tools/measure_click.py.

## 21:34 — Real-photo scale test, corrected ground truth
- Re-measured true distance: pen crosses 100.8 cm, tape centres 101.0 cm (first assumed 100.0).
- Measured on 1599 px WhatsApp images (~8.8 px/cm):
  straight 102.1 / 102.1 cm, angled 102.3 / 102.5 cm  ->  error +1.1% to +1.5%.
- Lesson: hand-made ground truth had ~1 cm error, half of the apparent system error. Measure twice.
- Remaining consistent bias ~+1.3%: check marker square size; else lens distortion / compression.

## 21:42 — Green wall ground truth (for Layer 10 development)
- Width, corner to corner at marker height: 210.9 cm (measured in segments with a 1.5 m tape)
- Height: 199.4 cm, from floor to [ceiling / what exactly?]
- Wall marker ID 10, 18 cm, taped flat at chest height

## 22:08 — Vision first successful run (dev photo, Wikimedia, 960 px)
- 22 spines found = hand count (21 upright + 1 flat). Flat and cut-off spines: unreadable, empty text (no guessing).
- Readings accurate incl. umlauts and volume numbers; #19 possibly misread (check).
- Telemetry: 3.8-flash 429 quota x3, 3.7-flash 503 x3, 3.6-flash success. 14.2 s, ~2.5k tokens.
- Decisions: don't retry quota 429; enable billing before real sweeps (free tier exhausted after 1 photo).

## 22:15 — Decision: stay on Gemini free tier
- Billing setup required a ₹15,000 UPI autopay mandate: declined (personal budget).
- Design response: cache vision results, send keyframes only (sharp + new view), spread load across
  verified models incl. lite models. Report free-tier constraint honestly in README.

- 22:28 second vision run (fallback landed on gemini-3.5-flash): 22 spines again. Two models agree on count.

## 22:31 — Identification baseline on dev photo (shelf1, 22 spines)
- 20 readable spines: 6 identified (30%), 14 unidentified, 0 confidently wrong (all 6 checked correct).
- Root cause: full noisy spine text used as catalogue query (publisher, city, volume numbers, series codes),
  so the right book wasn't returned (e.g. NANSEN IN NACHT UND EIS I LEIPZIG F.A. BROCKHAUS -> best score 0.14).
- Secondary: scoring penalises spine words the record can't explain (publisher).
- Planned fix: field-wise reading (title/author/publisher/volume), intitle/inauthor queries, score on fields.
- Also seen: reading varies between models (#8 'Henno' vs 'Heimo'; #6 different subtitle).

## 22:42 — MEASURED FIX: identification 6/20 (30%) -> 12/20 (60%), 0 confidently wrong (all 12 verified)
- Fix: vision reads title/author/publisher/volume fields; targeted catalogue queries (title + inauthor);
  field-wise scoring; OL alternative author names (pen names); volume kept.
- Remaining: ß vs ss treated as different titles (#0 'ambiguous') -> fixed in norm, regression test.
- Correct refusals: Borges 'Erzählungen' (catalogue returned other authors), Lichtenberg 0.72.
- Vision slip: '30017' (dtv series no.) labelled as volume.
- Decision: stop tuning on this dev photo to avoid overfitting; tune only on real ground truth.

## 22:47 — After sharp-s fix: 14/20 (70%), 0 confidently wrong (dev photo)
- #0 fixed by ß->ss. #20 newly identified without a targeted change: catalogue results vary run to run.
- TODO: cache catalogue responses so evaluations are reproducible.
- Not tuning further on this dev photo (overfitting risk); official numbers from own ground truth.

dev2 telemetry: identify 125.9 s for 14 spines (~9 s/book, sequential catalogue calls + 429 backoff), price 15.3 s for 3 books (~5 s/book). Projected 60 books ≈ 14 min → fails the “<5 min after sweep” bar. Fix planned: parallel identify/price + catalogue cache. Measure before/after.

## Fri night: pipeline review (dev1 -> dev2)
- dev1: Nansen (1897) auto-priced ₹2,973. Root cause: appraisal year came from the catalogue
  (Google Books = an edition's date, Open Library = the work's first-publish year), not from the copy.
  Fix: appraisal from visible copy-age cues (blackletter/leather alone, or 2+ cues); catalogue year
  is only a review note. dev2: Hedin "Auf großer Fahrt" -> appraisal (cloth + gilt); modern books not flagged.
  Open: vision saw no cues on the Nansen spines -> under-flag rate to be measured on ground truth.
- Also fixed: "vol. 30017" series number, duplicate/alias authors, "0.0 m" for an unmeasured shelf run,
  skipped books labelled "not found", one listing used for vol. I + II (now flagged), bookcase = 3 items.
- dev2 telemetry: identify 125.9 s for 14 spines (~9 s/book), price 15.3 s for 3 books (~5 s/book).
  Projected 60 books ≈ 14 min -> FAILS "<5 min after sweep". Cause: sequential catalogue calls + 429 backoff.
  Fix planned: parallel identify/price + catalogue cache. Measure before/after.


Latency fix (Sat 00:07): parallel identification (4 workers) + catalogue disk cache. Same dev photo: identify 125.9 s → 29.1 s cold (62 catalogue calls, no 429s) → 0.28 s warm. dev3 vs dev4 titles identical → reproducible. Projected 60 books post-sweep ≈ 3–3.5 min (<5 min bar). Next bottleneck: vision ≈ 37 s/frame cold → must run during the sweep (Layer 13).


SerpAPI budget: 250 searches. Plan ≈ 210 (library ~150, US 10 books ~20, second space ~40). Cache in runs/cache must never be deleted; full pricing run once after ground truth.

Layer 11 dev5: bookcase priced as sourced range ₹2,290–19,600 (Google Shopping IN, middle 50% of new listings, 1 search). Range too wide (8.5×): the category query matches all sizes. Planned fix: add the marker-measured size and shelf count to the query and filter listings by size. No price-accuracy bar for items in the brief; reported as a limitation.

Quality check, first real numbers: shelf frame sharpness 3349 (ok); plain green wall photos 29–35 → flagged “blurry” though sharp. Root cause: Laplacian variance measures edge content, not camera shake; plain walls have few edges. Planned fix: measure sharpness inside the detected marker (fixed black/white pattern, same in every room), then calibrate on library frames.

## Fri night / Sat early: pipeline, review and fixes

### dev1 -> dev2 report review
- Nansen (1897) auto-priced ₹2,973. Root cause: the appraisal year came from the catalogue
  (Google Books = an edition's date, Open Library = the work's first-publish year), not from the copy.
  Fix: appraisal from visible copy-age cues (blackletter/leather alone, or 2+ cues); catalogue year = review note only.
  dev2: Hedin "Auf großer Fahrt" -> appraisal (cloth + gilt); modern books not flagged.
  Open: vision saw no cues on the Nansen spines -> under-flag rate to measure on ground truth.
- Also fixed: "vol. 30017" series number, duplicate/alias authors, "0.0 m" for unmeasured shelf run,
  skipped books labelled "not found", one listing used for vol. I + II (now flagged), bookcase = 3 items.

### Latency
- dev2 telemetry: identify 125.9 s for 14 spines (~9 s/book, sequential catalogue calls + 429 backoff),
  price ~5 s/book. Projected 60 books ≈ 14 min -> fails "<5 min after sweep".
- Fix: parallel identify/price (4 workers) + catalogue disk cache.
  dev3 (cold): identify 29.1 s (4.3x faster), 62 catalogue calls, no 429s. dev4 (warm): 0.28 s.
  dev3 vs dev4 titles identical -> reproducible. Projected 60 books post-sweep ≈ 3-3.5 min.
- Next bottleneck: vision ≈ 37 s/frame cold -> runs DURING the sweep in the live app.

### SerpAPI budget
- 250 searches/month. Plan ≈ 210 (library ~150, US 10 books ~20, second space ~40).
- runs/cache must never be deleted; full pricing run once after ground truth.

### Item pricing (Layer 11)
- dev5: bookcase = sourced range ₹2,290-19,600 (Google Shopping IN, middle 50% of new listings, 1 search).
- Range too wide (8.5x): category query matches all sizes. Planned: add marker-measured size to query.

### Quality checks
- Shelf frame sharpness 3349 (ok). Plain green wall photos 29-35 -> flagged "blurry" though sharp.
- Root cause: Laplacian variance measures edge content, not camera shake; plain walls have few edges.
- Planned: measure sharpness inside the detected marker (same pattern in every room), calibrate on library frames.

### Reference app: kept / changed / threw away (draft, verify against its code)
- Kept: live voice + camera pattern (browser -> FastAPI -> Gemini Live); live-updating panel (ours: inventory).
- Changed: detect + classify every spine/item; 10 cm markers for real cm; transcribe-only + catalogue decides
  (in our test session it described a cat on a cover, then corrected itself); blur/glare checked in code every frame;
  language fixed; agent directs the sweep.
- Threw away: policy/claimant intake questions; policy desk and sketch artist agents (ADK team).

### Slice 2 to-do (from brief)
voice IN + out (fallback: Chrome speech recognition), greeting + confirm country/currency, "logging N books",
slow down (frame change too large), step closer (most spines partial/unreadable), next shelf,
corrections ("first edition" -> appraisal, "skip that shelf" -> excluded_by_user), ask original/print for art,
fallback scale (ask "how tall is this bookcase?") for rooms without markers.

## Fri afternoon/evening: pricing, scale, vision, identification

### Pricing bugs (each fixed with a regression test)
- Google Shopping new prices: 39/40 results unusable -> switched to the Amazon engine (amazon.in / amazon.com).
- Amazon median ₹349 was 26% below the real price -> trust rule (ratings required) + most-reviewed listing;
  review count "1.1" means 1,100 (×1000 quirk).
- US price $0.00 = an audiobook -> use physical formats from purchase_options only (paperback -> mass market -> hardcover).
- US $25.80 = a Spanish edition (ISBN prefix 607, confirmed from cache) -> accent-aware matching, more language words,
  non-Latin script ratio, foreign function words, "not the book" words (summary, workbook, journal...).
- Used value ₹14,629 for a ₹472 book (collectible listing) -> used price capped at the new price, lower-middle median.
  Test expectation changed 300 -> 250 after asking "is the code wrong or the test wrong?".
- Results: Atomic Habits IN ₹472 (list 899), US $18.88 hardcover (list $27).

### Scale (markers)
- Printed marker measured exactly 10.0 cm. Synthetic test: 302.3×200.4 vs 300×200.
- Real wall (green wall, tape 210.9 × 199.4 cm): marker error ~1.1–1.5% after re-measuring ground truth
  (first ground truth was off by ~1 cm). Consistent ~+1.3% bias: suspect print scale or lens distortion.

### Vision
- gemini-2.5-flash -> 404 (retired); newer flash -> 503/429 quota -> model list with fallback,
  no retry on 404 or quota. Dev photo: 22/22 spines (21 upright + 1 flat), unreadable/cut-off spines not guessed,
  ~2.5k tokens/frame. Billing autopay (₹15,000) declined -> free tier + vision cache + few keyframes.

### Identification
- 30% on dev photo. Root cause: noisy full-text queries.
- Fix 1: vision splits title/author/publisher/volume; targeted queries "title inauthor:surname" -> 60%.
- Fix 2: German "ß" broke matching ("ambiguous") -> ß -> ss in normalisation -> 70% (14/20), 0 confidently wrong.
- One spine changed answer between runs without a code change -> catalogue nondeterminism -> fixed later by disk cache.
- Stopped tuning on the dev photo to avoid overfitting.

Glare check flagged the white paper around printed markers as glare (found by a test). Fix: mask a ~1.8× box around each detected marker before measuring glare.