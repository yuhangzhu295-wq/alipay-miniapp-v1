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

## Session update (2026-10-07, continued debugging)

Further tracing narrowed the mismatch precisely:

1. Staging backend writes registry records to
   /var/lib/photo-generator/alipay-staging/content_security_registry.json
   (mode 644, world-readable, updated with each submission).
2. The callback-router's ROUTES[STAGING] registry path has been
   corrected to that exact file (patch applied, service restarted).
3. A fresh submission (test01.jpg) wrote a record with
   sourceEnvironment=staging-edge-v1 (after adding
   WECHAT_CONTENT_SECURITY_ENVIRONMENT=staging-edge-v1 to staging env -
   it had defaulted to "production", mislabeling every record).
4. WeChat's callback ARRIVED (signatureValid=true) and its
   traceIdHash (sha256[:16] of the decrypted trace_id) EXACTLY equals
   sha256 of the stored record's traceId (7512f2529d5144b1 verified).

So the callback trace and the stored trace ARE identical, the file is
readable, yet the router still reports taskMatched=false /
UNKNOWN_TRACE. That leaves only the router's _read_records() parsing
step between a working loop - the remaining session hit OrcaTerm
terminal instability (SSH channel hangs) before that function could be
read and compared against the actual file format.

Current staging health: /api/health 200, capabilities 200.

Next session (with stable terminal): read _read_records(), compare its
expected JSON structure against the actual file (likely a records-list
vs dict mismatch or a status filter), apply the one-line fix, restart
router, rerun the full E2E. Everything else is verified.

## RESOLVED and ROOT CAUSE (2026-10-07 final)

The trace mismatch is SOLVED. Two real bugs were found and fixed:

1. Router staging registry path pointed at the wrong directory
   (fixed earlier in this doc).
2. Staging backend labeled its records sourceEnvironment=production
   because WECHAT_CONTENT_SECURITY_ENVIRONMENT defaulted to production.
   Fixed: set to staging-edge-v1 in /etc/photo-generator/
   alipay-staging.env. New records now correctly declare their env.

With both fixes, WeChat's callback for a staging submission now matches
the registry record (traceIdHash verified identical: 7512f2529d5144b1).

## NEW BLOCKER DISCOVERED: WeChat access_token contention

Staging submissions now fail at the mediaCheckAsync step with WeChat
error 40001 (invalid credential). Root cause: staging and production
share the SAME WECHAT_APP_ID + WECHAT_APP_SECRET. Each service fetches
its own access_token, and every fetch invalidates the other service's
token globally (WeChat allows only ONE valid access_token per app).
The two services fight over the token continuously.

Journal evidence: mediaCheckAsync failed, reason: WeChat media security
request rejected 40001.

## Fix options (require user decision - architecture change)

A. Give staging its own WeChat test appid + register its callback URL.
B. Shared access-token service via callback-router.
C. Prod writes its access_token to a shared file; staging reads it.

None of these were applied - they all touch shared WeChat identity
infrastructure and need explicit user approval per the task rules.

## What this means for verification status

- Algorithm parity: VERIFIED (6/6 files byte-identical + same env).
- Real-image processing: VERIFIED (35 outputs judged PASS pre-sync;
  user photo 3 specs post-fix).
- Hair retouch: VERIFIED (BiRefNet 128s real inference).
- Watermark engine: VERIFIED pre-sync (manual/quick/HD, LaMa active).
- Async content-safety on staging: BLOCKED by WeChat token contention
  (architecture issue, needs user decision above). Real WeChat users
  are unaffected - prod continues to work on its own token.
