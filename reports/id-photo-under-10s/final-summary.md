# ID Photo Under-10-Second Final Summary

- Optimization code merge: `4bc2b3210c1e91ec2db62a81a414efe75011d1c9`.
- FAST-A/FAST-B sequential routing, dual resident sessions, four-level gate,
  bounded repair, upload working copy, and ORT tuning: PASS.
- Production 30-image ordinary path: 30/30, P50 `2811 ms`, P95 `4549 ms`, max
  `5113 ms`; synchronous BiRefNet 0.
- Production matrix: 120 spec requests, 150 color outputs, 30 asynchronous
  BiRefNet jobs; all required checks PASS.
- Watermark/real LaMa, compression, cleanup, health, and download regression:
  PASS.
- WeChat DevTools: 98 specifications, 411/411 checks PASS, 0 runtime exceptions.
- WeChat DevTools full business flow: 52/52 checks PASS, including real color
  compose/download and save/view/delete.
- Backend, Worker, and IOPaint: active at the last cloud check.
- The frontend now honors the backend's explicit accepted FAST warning during
  color composition; unaccepted quality failures remain blocked.
- No filename, path, clothing-color, skin-color, or fixed-pixel sample routing was
  added. No unrelated product function was changed.

Overall status: **PENDING_PHYSICAL_DEVICE_CONFIRMATION_AND_FINAL_EVIDENCE_SHA_SYNC**.
