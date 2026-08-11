# WeChat mediaCheckAsync Callback Acceptance

- Evaluated at: 2026-08-11 14:33 CST
- Callback URL: `https://tupzjianzhao.chat/api/content-security/callback`
- AppID: `wx4bd1a46868d6e3a2`
- Message mode: plain text
- Message format: JSON
- Secret values recorded: no

## Verified

- Public HTTPS callback URL is reachable.
- WeChat GET URL verification reached Backend with `signatureValid=true`.
- Real WeChat POST callbacks reached Backend with `signatureValid=true`.
- Callback tasks matched by masked trace identity and changed `PENDING -> PASS`.
- Real `wx.login` succeeded with `openidBound=true` and `openidPresent=true`.
- Normal images passed content safety and entered downstream business: `3/3`.
- Normal callback timings:
  - normal-1: `submitMs=731`, `callbackWaitMs=1696`, `securityTotalMs=2532`
  - normal-2: `submitMs=428`, `callbackWaitMs=1071`, `securityTotalMs=1613`
  - normal-3: `submitMs=450`, `callbackWaitMs=5340`, `securityTotalMs=5992`
- Focused callback tests: `14/14 PASS`, including duplicate callback idempotency and invalid signature rejection.
- WeChat DevTools full business regression: `52/52 PASS`.
- DevTools console errors: `0`; runtime exceptions: `0`.
- ID-photo/watermark/model algorithm changes in this callback task: `0`.

## Unmet Condition

- Five safe risk-fixture attempts were all classified by the real WeChat provider as `PASS` (`label=100`).
- Therefore a real provider `PENDING -> REJECT` transition was not observed.
- `rejectDownstreamCalls=0` is covered by focused deterministic tests, but is not claimed as a real-provider REJECT observation.
- No REJECT callback was fabricated and no synthetic signed callback is counted as live evidence.

## Result

- Callback delivery fix: `PASS`
- Normal-image acceptance: `PASS (3/3)`
- Full business regression: `PASS (52/52)`
- Live risk-fixture acceptance: `NOT VERIFIED`
- `FINAL_PASS=false`

The sole remaining condition for `FINAL_PASS=true` is a platform-approved fixture that WeChat itself classifies as risky. The fail-closed Gate remains unchanged.

## Reproduction Commands

```powershell
python server\scripts\verify_wechat_content_security.py
$env:WECHAT_LIVE_FIXTURE_BASE = 'https://temporary-fixture-host.example/callback-fixtures'
node server\scripts\verify_wechat_live_callback.js
$env:DEVTOOLS_ID_FIXTURE_URL = 'http://127.0.0.1:18765/frontal-portrait.jpg'
node server\scripts\verify_devtools_business_flow.js
```

The two fixture environment variables are intentionally required. Temporary public fixtures were removed after validation.
