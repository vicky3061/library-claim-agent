# Results: sweep neptunes_v5 (IN/INR)

| Bar (from the brief) | Ground truth | System | Result |
|---|---|---|---|
| Book count ±5% | 73 | 73 (0.0% off) | PASS |
| Titles ≥70% of legible, ≤3% confidently wrong | 50 legible | 84.0% correct, 1.8% wrong (1/57) | PASS |
| Spine dims ±15% (20 books) | 20 books | 18/36 dims within, median 14.9% | FAIL |
| Prices ±25% (15 books) | 15 books | 8/14 within, median 0.0% | FAIL |
| Items ≥80% found | 8 | 8 (100.0%) | PASS |

Latency: vision 0.26 s · identify 0.14 s · price 220.95 s · total 221.61 s

Wrong titles (named by the system, not on the shelf): The MacGregors
