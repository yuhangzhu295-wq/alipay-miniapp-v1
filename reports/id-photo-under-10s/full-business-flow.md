# Production Full Business Flow

Base URL: `https://tupzjianzhao.chat`.

## ID Photo

- Thirty qualified images: 30/30 successful.
- Ordinary path: P50 `2811 ms`, P95 `4549 ms`, max `5113 ms`.
- Synchronous BiRefNet: 0.
- Four-spec matrix: 120 requests returned clear results.
- Five-color matrix: 150 attempts, 150 outputs, all successful outputs downloaded.
- Asynchronous hair DETAIL: 30 jobs created immediately, all 30 completed using
  `birefnet-v1-lite`.
- One-inch full-flow prepare: `4613 ms`; all five downloaded outputs were
  exactly `295x413`.
- The existing driver-license purpose/template mismatch returned the explicit
  `TEMPLATE_NOT_AVAILABLE` result in 30 matrix rows; it was not hidden or
  weakened in this performance-only change.

## Other Business Functions

- Health and 24-hour retention: PASS.
- Manual watermark: `708 ms`, `opencv_manual`, no fallback, changed output.
- Quick watermark: `462 ms`, `opencv_quick`, no fallback, changed output.
- HD watermark: `22630 ms`, real `lama`/IOPaint, no fallback, changed output.
- Compression and cleanup endpoint: PASS.
- Ten negative ID-photo samples: 0 false PASS.
- Preview downloads and five-color composition: PASS.
- Official WeChat DevTools full business flow: 52/52 PASS, including red
  background switch, result download, save, list view, preview, and delete.
- The first DevTools run exposed a frontend contract bug: an explicitly
  accepted `FAST_WARNING` result still tripped the legacy
  `qualityReport.passed` check. The frontend now accepts only the backend's
  explicit `fastWarningAccepted=true` signal; severe failures remain blocked.

Status: **PASS**.
