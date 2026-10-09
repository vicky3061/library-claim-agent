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