# Retry Policy

- A normal single ROI makes one LaMa call.
- A second call is allowed only when the objective residual threshold is met on a retry-eligible single ROI.
- Multiple distant components may make one call per grouped ROI, with a hard total limit of two calls.
- Multi-ROI requests do not add a residual retry after their component calls.
- Retry telemetry records `retryReason`, first residual score, retry ROI, and second inference time.

In the production matrix, ordinary small, Full HD, 4K, and actual far-ROI runs stayed within the policy. The scan/stamp fixture triggered the documented objective residual retry and passed quality comparison. Maximum observed `lamaCallCount` was two.

Status: PASS.
