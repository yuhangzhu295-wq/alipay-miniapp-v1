# WeChat DevTools

The official `miniprogram-automator` endpoint on port 9430 drove the real remove-watermark page against `https://tupzjianzhao.chat`.

- Quick regression: PASS, `opencv_quick`.
- Initial HD: PASS, LaMa, 4.304 s page-observed time.
- HD retry: PASS, LaMa, 4.688 s.
- Continued local repair: PASS, LaMa, 3.488 s.
- Client timing fields: all 11 required fields present.
- Observed status text: upload, mask analysis, HD repair, preview loading, and elapsed seconds.
- Fake percentages: none.
- Console errors: 0. Runtime exceptions: 0.

Computer Use could enumerate the NW.js DevTools window but its owner validation rejected the identical returned owner string. Official screenshot calls then timed out twice at 5 seconds. These tool limitations are recorded; no screenshot PASS is claimed. Page state, network completion, result hashes, and runtime exceptions were still verified through the official automator channel.

Raw evidence: `devtools-run.json`.

Status: PASS with screenshot limitation recorded.
