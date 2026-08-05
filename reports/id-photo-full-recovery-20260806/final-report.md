# ID Photo Full Recovery Report

## Status

- Overall: PASS before cloud deployment
- Scope: ID-photo entry, capture guide, custom camera, FAST failure UX, async hair refinement, five backgrounds, specifications, preview/download/save/delete, watermark regression
- Unrelated authentication, payment, membership, profile, and watermark algorithms were not changed.

## Root Causes

1. The capture guide and custom camera implementation existed only on commit `30ba26f` and was never merged into `master`, so routes and entry wiring were absent in production.
2. The generator always sent `hairRetouch: false`, even when the UI checkbox was enabled.
3. `ID_PHOTO_FAST_BLOCKED` first rendered a generic hard error and cleared the result before starting DETAIL, which made the automatic upgrade look like a failure.
4. Neutral-gray output at larger specifications could be misclassified as retained side background solely from a low-saturation edge component.

## Implemented

- Registered `pages/capture-guide/capture-guide` and `pages/id-camera/id-camera` with camera permission text.
- Routed home hot specs, specification selection, My Photos re-create, and custom-size generation through the shared capture guide.
- Added album-only selection, direct camera entry, portrait/head-and-shoulder outline, eye line, camera switching, confirmation, retake, permission recovery, and real photo transfer into the existing generator.
- Preserved FAST-only ordinary processing and sent the real UI `hairRetouch` intent to `/api/id-photo/prepare` without restoring synchronous DETAIL.
- Added a dedicated friendly FAST failure state with `重新上传` and `使用发丝精修` actions.
- Added automatic FAST-to-DETAIL switching copy, real job creation/polling, terminal failure state, and completed-result preview replacement.
- Relaxed only the neutral-gray standalone side-component threshold; background-sheet/head-side signals and all other quality checks remain active.

## Verification

- Capture runtime harness: PASS, 62/62 checks.
- DETAIL UX runtime harness: PASS, 9/9 checks.
- Official WeChat DevTools capture flow: PASS, 39/39 checks.
- Official WeChat DevTools full business flow: PASS, 52/52 checks, 0 gaps.
- Frontend UI regression: PASS.
- Main business flow regression: PASS.
- Specification restore: PASS.
- Real FAST samples: 3/3 returned within 30 seconds; P50 14546ms, P95 15446ms, max 15446ms, synchronous DETAIL count 0.
- Real async DETAIL: create 28ms; `queued -> running -> completed`; BiRefNet result completed at 30364ms with a new `preparedId`.
- One-inch/two-inch/large-one-inch five-color matrix: PASS, 15/15 outputs.
- Watermark HD engine: PASS, IOPaint/LaMa loaded, no fallback.
- Watermark nine-sample manual/HD matrix: PASS, 9/9.
- Watermark remove-scan regression: PASS.

## Evidence

- `reports/id-photo-camera-flow/devtools-report.json`
- `reports/id-photo-camera-flow/devtools-screenshots/`
- `reports/final/devtools-business-flow-report.json`
- `reports/id-photo-full-recovery-20260806/real-fast-samples.json`
- `reports/id-photo-full-recovery-20260806/real-async-detail.json`
- `reports/id-photo-all-formats/final/spec-format-validation-report.json`
- `reports/final/watermark-hd-engine-audit.json`
- `reports/final/watermark-hd-chain-report.md`
- `reports/current-fixes/final/watermark-remove-scan-report.md`

## Deployment

- Local verification: PASS
- GitHub `master`: pending commit
- Tencent Cloud: pending deployment
- Three-way SHA check: pending deployment
