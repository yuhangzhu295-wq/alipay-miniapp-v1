# ID photo under-10s resume state

Generated: 2026-08-06 21:42:05 +08:00

## Required state

| Field | Value |
| --- | --- |
| `localSha` | `495c7c90495d3e589c3869ef517de89dbf1bd711` |
| `githubMasterSha` | `495c7c90495d3e589c3869ef517de89dbf1bd711` |
| `currentBranch` | `optimize/id-photo-under-10s-20260806` |
| `dirtyFiles` | 9 modified validation/report files listed below |
| `untrackedFiles` | 4 local service logs listed below |
| `fastBImplemented` | `false` |
| `dualSessionImplemented` | `false` |
| `onnxThreadConfigImplemented` | `false` |
| `deployedToCloud` | `true` for baseline SHA `495c7c9`; the pending optimization is not deployed |
| `lastCompletedStage` | `resume_state_verification` |
| `resumeFromStage` | `rerun_fast_a_vs_photographic_modnet_ab_on_three_specified_images` |

## Local and GitHub

- Local `HEAD`, `origin/master`, GitHub `master`, and cloud deployment all resolve to `495c7c90495d3e589c3869ef517de89dbf1bd711`.
- The local optimization branch has no corresponding remote branch and no pull request.
- No FAST-B, photographic MODNet worker routing, dual resident FAST sessions, or explicit ONNX Runtime thread configuration has been committed or left as an uncommitted business-code change.
- The full working-tree diff is limited to prior validation reports and verification scripts: 9 files, 7,764 insertions, and 1,271 deletions.
- Existing modified and untracked files are preserved. No interrupted half-written business implementation was found.

## Modified files

- `reports/id-photo-all-formats/final/spec-format-validation-report.json`
- `reports/id-photo-all-formats/final/spec-format-validation-report.md`
- `reports/id-photo-camera-flow/devtools-report.json`
- `reports/id-photo-real-speed/fast-no-detail.json`
- `reports/id-photo-real-speed/fast-no-detail.md`
- `server/scripts/verify_id_photo_all_formats.py`
- `server/scripts/verify_id_photo_camera_flow.js`
- `server/scripts/verify_id_photo_capture_devtools.js`
- `server/scripts/verify_id_photo_spec_catalog.py`

## Untracked files

- `logs/local-backend-8000.err.log`
- `logs/local-backend-8000.out.log`
- `logs/local-hivision-8091.err.log`
- `logs/local-hivision-8091.out.log`

## Implementation audit

- `photographic MODNet` exists in the vendored Hivision implementation, but the resident worker supports only `hivision_modnet`, `rmbg-1.4`, and `birefnet-v1-lite`.
- The worker releases other model sessions when switching models, so dual FAST-A/FAST-B residency is not implemented.
- `human_matting.load_onnx_model` still constructs a default ONNX Runtime session without `ORT_SEQUENTIAL`, `ORT_ENABLE_ALL`, or explicit intra/inter-op thread settings.
- The ordinary ID photo path has only the existing FAST-A evaluation and `FAST_PASS`/`FAST_WARNING`/`FAST_BLOCK`; the requested four-level gate and risk-triggered FAST-B cascade are absent.
- `prepareIdPhotoUploadSource` already exists with a 1600-pixel maximum side and JPEG quality 86. The requested 1280/1600/2048 and 85/88/90 A/B is still pending.

## Cloud verification

- Working directory: `/root/photo-generator/server`
- Deployment branch: `master`
- Deployment SHA: `495c7c90495d3e589c3869ef517de89dbf1bd711`
- `photo-generator`: `active`
- `hivision-worker`: `active`
- `iopaint`: `active`

## Resume point

The next stage is to rerun the real FAST-A versus photographic MODNet FAST-B comparison on the three specified images and record complete timing, mask-quality metrics, and visual artifacts. Production routing must not change until that A/B proves FAST-B is useful.
