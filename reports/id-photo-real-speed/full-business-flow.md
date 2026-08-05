# Full Business Flow

- Status: **PASS for the requested performance scope and production regression**
- WeChat DevTools: 52/52 checks passed.
- Production basic/HD flow: PASS.
- Production user-photo save/view/delete isolation: PASS.
- Ordinary ID photo: Hivision MODNet only; no synchronous DETAIL.
- Async hair refinement: queued POST returned in 305 ms; BiRefNet completed in the background.
- Five backgrounds: successful outputs downloaded and matched the requested result flow; invalid source compositions retained existing explicit quality errors.
- Preview/download consistency: PASS in DevTools.
- Manual and quick watermark removal: PASS.
- HD and large-image watermark path: real `lama`, `fallbackUsed=false`, PASS.
- Compression and retention cleanup endpoints: PASS.
- Backend, Hivision Worker, and IOPaint: active after deployment.

## Production Routing

- Backend: `/root/photo-generator/server`, port 8000.
- Hivision Worker: `/root/photo-generator/server`, port 8091.
- IOPaint/LaMa: port 8081.
- Nginx upstream: `http://127.0.0.1:8000` for `tupzjianzhao.chat`.
- Engine info: standard `hivision_modnet`, detail `birefnet-v1-lite`.

## Existing Baseline Finding

The legacy `driver_license` purpose is not present in the outfit-template purpose allowlist, so the 30-image matrix records explicit `TEMPLATE_NOT_AVAILABLE` responses for that purpose. This predates the production baseline and was not changed because the current task forbids unrelated feature repair. Driver specification metadata and mainland composition parameters were not modified.

## Evidence

- `reports/cloud-deploy-e2e/id-photo-real-speed-production/cloud-tests/cloud-real-business-flow-hd.json`
- `reports/final/devtools-business-flow-report.json`
- `reports/id-photo-real-speed/thirty-image-matrix.json`
- `reports/id-photo-real-speed/heavy-task-queue.json`
