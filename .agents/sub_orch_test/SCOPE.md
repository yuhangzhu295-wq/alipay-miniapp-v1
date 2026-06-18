# Scope: E2E Testing Track

## Architecture
The E2E Testing Track verifies the integration between the WeChat Mini-program frontend logic (via DevTools/mock verification) and the FastAPI backend. It also verifies core components including:
- ID Photo prepare & compose pipeline (sizes, cropping, matting engines, composition metrics)
- Watermark removal gateway (manual, quick, and HD services)
- Profile, tool-page, and spec display features

The verification runs opaque-box checks using Python verifiers triggered via node scripts, outputting structured validation reports and comparison images in the `reports/` and `reports/final/` folders.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Test Case Design & Mapping | Analyze existing verification scripts and samples, map to the 4-tier methodology | None | PLANNED |
| 2 | Document TEST_INFRA.md | Write the E2E Test Infra specification to project root | M1 | PLANNED |
| 3 | E2E Test Execution & Verification | Run the verification suite via subagent worker and record results | M2 | PLANNED |
| 4 | Document TEST_READY.md | Write E2E Test Ready report to project root | M3 | PLANNED |

## Interface Contracts
### Test Runner Interface
- Command: `npm run verify:all` or individual `npm run verify:*` commands.
- Configurable environment variable: `PORT` (default 8000), base URL (default http://127.0.0.1:8000).
- Output format: Markdown (.md) and JSON (.json) reports placed in `reports/final/`.
