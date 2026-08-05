# ID Photo Real Speed Final Summary

- Status: **PASS**
- Production code deployment SHA: `9642a6c472b500f98742dfe31dfcefa0e3524050`
- Root cause: ordinary FAST_BLOCK synchronously launched BiRefNet; cancelled native inference continued consuming the 2-core host and delayed later requests.
- Fix: ordinary mode always uses resident `hivision_modnet`; FAST_BLOCK returns clearly without DETAIL; user-selected hair refinement is an asynchronous job.
- Upload work copy: longest edge 1600 px, JPEG quality 86, original file untouched; A/B minimum SSIM 0.989805.
- Current three slow originals, production 15 runs: P50 2361 ms, P95 3098 ms, maximum 3668 ms, over 30 seconds 0, synchronous DETAIL 0.
- Local 30-image matrix: P50 795 ms, P95 910 ms, maximum 911 ms; 30 async DETAIL jobs completed.
- Production heavy queue: ten FAST P95/max 4103 ms; FAST during DETAIL 7866 ms; FAST during LaMa 4000 ms.
- DETAIL + LaMa serialization: LaMa queue wait 162097 ms; both jobs completed; no simultaneous heavy inference.
- Production async DETAIL: create 305 ms; `queued -> running -> completed`; BiRefNet background total 155466 ms.
- Production full business flow: PASS, including real LaMa with `fallbackUsed=false`.
- WeChat DevTools: cache cleared, latest code previewed, 52/52 checks passed.
- Physical phone interaction: not executed; no script result is presented as physical-device timing.
- No specification library, mainland composition parameter, background color, watermark algorithm, login, membership, payment, or unrelated page was changed.

## Reports

- `root-cause.md/json`
- `client-upload-ab.md/json`
- `fast-no-detail.md/json`
- `async-detail.md/json`
- `heavy-task-queue.md/json`
- `production-timing.md/json`
- `real-device-report.md`
- `full-business-flow.md`
- `thirty-image-matrix.md/json`
