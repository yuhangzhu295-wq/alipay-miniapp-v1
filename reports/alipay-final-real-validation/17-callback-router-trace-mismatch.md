# Async content-safety loop: staging trace mismatch (2026-10-06)

After syncing the staging engine byte-for-byte with the WeChat production
release (6/6 core files SAME, model routing env identical), the full
business flow was re-tested with real photos. Result: content-safety
submit succeeds (202 PENDING, registry record written with traceId),
WeChat's async callback ARRIVES and passes signature validation, but the
callback-router reports UNKNOWN_TRACE - the decrypted callback trace_id
does not equal the traceId stored by staging at submit time.

Evidence:
- staging registry: /var/lib/photo-generator/alipay-staging/
  content_security_registry.json contains records with traceId
  6ac3ce98-... / 6ac3d4fa-... (sha256[:16] = 9f83..., 7e08...)
- router log: traceIdHash 9f8c0c6a45aa4c68 / 76e8c5b780331 /
  38b916cfd06aa1 with signatureValid=true, taskMatched=false,
  result=UNKNOWN_TRACE (near-collision patterns suggest a formatting
  difference in what WeChat echoes back vs what was stored)

Fixed along the way: the router's STAGING registry path pointed at
/root/photo-generator-staging-edge-v1-runtime/... while the staging
backend writes to /var/lib/photo-generator/alipay-staging/... (patched,
backup kept). With that fix the router now READS the right file, but the
trace VALUES still mismatch.

## Why this matters

- WeChat PRODUCTION uses the same wechat_security.py + same callback
  router and demonstrably completes (historical 20/20 content-security
  PASS in acceptance runs). So the async design is sound in prod.
- The staging gap is one of two things: (a) staging submits with the
  PROD WeChat app credentials copied into staging env, and WeChat's
  callback for that app arrives with a trace_id variant that the
  staging registry doesn't hold; or (b) a submit-time code path writes
  a different trace than what was sent.

## What was verified end-to-end TODAY (real photos, real HTTP)

- Synced-engine staging: content-safety submit 202 + registry record +
  WeChat callback received (signature valid) - the async plumbing is
  wired; only the trace match fails.
- WeChat production engine (untouched, same code): previously verified
  with 68 real photos / 35 downloaded outputs / per-image quality
  judgment PASS (acceptance/outputs/wechat, alipay, all-specs).

## Honest bottom line for "does the business flow work"

The processing algorithm is now byte-identical to WeChat production and
was exercised with real images end-to-end before the sync (35 judged
outputs PASS) and re-exercised after the sync up to the async
content-safety gate. The remaining blocker for a green staging E2E is
the trace-match integration above - a focused next step, not an
algorithm problem.
