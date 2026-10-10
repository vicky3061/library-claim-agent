# Failure log

> One page. The three worst errors are taken from the **submitted sweep** (filled after the run), each with its
> root cause and what I would change. Measured fixes made during the build are listed after them.

## The three worst errors in the submitted run
| # | What went wrong (with numbers) | Root cause | What I would change |
|---|---|---|---|
| 1 | TODO after the library run | | |
| 2 | TODO | | |
| 3 | TODO | | |

## Fixes made during the build, each measured
| Problem found | Root cause | Fix | Before → after |
|---|---|---|---|
| Identification 30% on the dev photo | Whole spine text sent as one noisy catalogue query | Vision splits title/author/volume; targeted `title inauthor:surname` queries | 30% → 60% |
| German titles "ambiguous" | `ß` not normalised, so "Große" ≠ "Grosse" | ß → ss before matching | 60% → 70%, 0 confidently wrong |
| Nansen (1897) auto-priced ₹2,973 | Appraisal used the catalogue year (an edition's / the work's), not the copy on the shelf | Appraisal from visible copy-age cues; catalogue year is a review note only | antique copy → needs_appraisal |
| US price $0.00 | Cheapest listing was an audiobook | Physical formats only (paperback → hardcover) | $0.00 → $18.88 |
| US price $25.80 for the wrong book | A Spanish edition matched the title | Language/script checks on listings | wrong edition rejected |
| Used value ₹14,629 for a ₹472 book | A collectible listing taken as "used" | Used price capped at new price, lower-middle median | collectible rejected (regression test) |
| Identification too slow | 4 catalogue calls per spine, one after another, + 429 back-off | Parallel calls (4 workers) + disk cache | 125.9 s → 29.1 s for 14 spines (4.3×); cached reruns 0.3 s, identical results |
| Same book counted in two keyframes | Keyframes overlap by ~1/3 | Register consecutive frames (ORB + RANSAC homography), merge boxes that land on each other | synthetic shelf: 57 → 45 (truth 45) |
| Marker paper flagged as glare | White A4 sheet around the marker | Mask the marker sheet before measuring glare | false glare removed |
| Plain wall flagged as blurry | Laplacian sharpness measures edges, a plain wall has few | Planned: measure sharpness inside the marker | open |

## Known limits (not fixed)
- Spine thickness reads ~20% high when the phone is at a strong angle: vision gives upright boxes around slanted spines. Mitigation: the agent asks to hold the phone parallel.
- Room size depends on how precisely vision locates wall corners; rectangle assumed from opposite wall pairs.
- Item price ranges are wide without a brand (e.g. bookcase ₹2,290–19,600).

## Cost per sweep and latency per stage (submitted run)
| Stage | Latency | Calls | Cost |
|---|---|---|---|
| Vision (during the sweep) | TODO | TODO frames | TODO |
| De-duplication | TODO | — | 0 |
| Identification | TODO | TODO catalogue calls | 0 (free APIs) |
| Pricing | TODO | TODO SerpAPI searches | TODO |
| Packet ready after sweep | TODO (bar: < 5 min) | | |
| **Total per sweep** | | | **TODO** |

## With two more weeks
TODO: 3–4 lines (e.g. oriented spine boxes, sharpness on the marker, size-aware item pricing, a checker agent).
