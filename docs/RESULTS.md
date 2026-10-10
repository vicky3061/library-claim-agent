# Ground truth and results

**Space:** Neptunes Books (BookZo), AECS Layout, Bengaluru — photographed **with the owner's permission**. Scope: **top row of bookcase F-6 (unit A, shelf marker 0) and F-7 (unit B, shelf marker 1)**; other rows and shelves are out of scope.
**Ground truth collected by hand before any tuning** (files in `ground_truth/neptunes/`):
- `books.csv` — all **73 books** (F-6: 30 upright + 2 flat; F-7: 29 upright + 12 flat). 23 spines not readable by a human (titles taken from the covers in the shop); 50 legible titles transcribed by hand from the close-up shop photos.
- `spine_measurements.csv` — **20 spines** measured with a tape (10 per bookcase).
- `prices.csv` — **15 prices** hand-checked on Amazon.in (first matching new paperback, URL, 2026-10-10).
- `items.csv` — **8 non-book items** with sizes and materials.
- `room.csv` — bookcase sizes only; **room not tape-measured** (shop did not permit it).

## System vs ground truth (run `neptunes_v4`, the final code)
| Bar (from the brief) | Ground truth | System | Result |
|---|---|---|---|
| Book count ±5% | 73 | 73 (0.0% off) | **PASS** |
| Titles ≥70% of legible, ≤3% confidently wrong | 50 legible | 84.0% correct, 1.8% wrong (1/57) | **PASS** |
| Spine dims ±15% (20 books) | 20 books | 18/36 dims within, median 14.9% | FAIL |
| Prices ±25% (15 books) | 15 books | 8/15 within, median 0.0% | FAIL |
| Non-book items ≥80% | 8 | 8 (100%) | **PASS** |
| Floor area ±10% | not measured | system estimate only | not scored |
| Wall area ±15% | not measured | system estimate only | not scored |
| Packet < 5 min after sweep | — | 63 s (warm cache); 604 s first cold run | see failure log |

Full per-book rows: `submission/neptunes/results.md` and `results.json` (spine rows, price rows, wrong titles).

## Progress across runs (same frames, same ground truth)
| Run | Change | Count | Titles (correct / wrong) | Spines within | Items | Total time |
|---|---|---|---|---|---|---|
| v1 | first real run | 73 | 84% / 1.8% | 17/36 | 2/8 (no item photos) | 604 s |
| v2 | thickness overlap fix + item photos | 73 | 84% / 1.8% | 18/36 | 8/8 | 457 s |
| v3 | markers/loose books not items, duplicate-item flag | 73 | 84% / 1.8% | 18/36 | 8/8 (16 items) | 65 s |
| v4 | same-title author from shelf context | 73 | 84% / 1.8% | 18/36 | 8/8 | 63 s |

## Hand-checked prices vs system (INR, Amazon.in)
| Book | Hand | System | Within 25% |
|---|---|---|---|
| The Stars Shine Down | 5129 | 141.58 | no |
| Morning, Noon & Night | 368 | 368 | yes |
| Nothing Lasts Forever | 643.13 | 141.58 | no |
| Are You Afraid of the Dark? | 1671 | 440 | no |
| A Stranger in the Mirror | 329 | 2481.74 | no |
| Jewels of the Sun | 475.11 | 475.11 | yes |
| Dance of the Gods | 693 | 693 | yes |
| Born in Fire | 473 | 2563 | no |
| The Collector | 672 | 672 | yes |
| The Next Always | 487.05 | 487.05 | yes |
| Times Change | 1627 | 1627 | yes |
| Secret Star | 799 | 4000 | no |
| Blood Magick | 828 | 828 | yes |
| Honest Illusions | 826 | 826 | yes |
| A Perfect Life | 530 | 314.21 | no |

## Same 10 books, second country (run `neptunes_us`, `--country US --currency USD`)
Native amazon.com listings, not converted (`converted: false`).
| Book | India (INR) | US (USD) | US source |
|---|---|---|---|
| The Stars Shine Down | 141.58 | 8.62 | amazon.com/dp/0446364762 |
| Morning, Noon & Night | 368.00 | 6.25 | amazon.com/dp/0688084923 |
| Nothing Lasts Forever | 141.58 | 8.70 | amazon.com/dp/0446354732 |
| Angel of the Dark | 1085.00 | 7.99 | amazon.com/dp/0062073451 |
| Are You Afraid of the Dark? | 440.00 | 5.05 | amazon.com/dp/0060559349 |
| A Stranger in the Mirror | 2481.74 | 25.62 | amazon.com/dp/0062967320 |
| Jewels of the Sun | 475.11 | 7.82 | amazon.com/dp/0425271587 |
| Dance of the Gods | 693.00 | 3.99 | amazon.com/dp/0515141666 |
| Born in Fire | 2563.00 | 20.98 | amazon.com/dp/1638493448 |
| The Collector | 672.00 | 9.31 | amazon.com/dp/0515154121 |
