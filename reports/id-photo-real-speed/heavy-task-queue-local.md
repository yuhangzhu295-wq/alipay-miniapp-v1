# Heavy Task Queue

- Status: PASS
- Base URL: `http://127.0.0.1:8000`
- Ten FAST: P50 721 ms, P95 801 ms, max 801 ms
- FAST during DETAIL: 14333 ms
- DETAIL create: 12 ms; final state: completed
- Resource sample: process CPU max 1396.2%, process RSS max 6748.4 MB, system CPU max 96.0%, Swap used max 4993.9 MB
- LaMa scenarios: not tested on this target

## Checks
- tenFastReturnedClearly: PASS
- tenFastNoSyncDetail: PASS
- tenFastModnetOnly: PASS
- tenFastUnder30Seconds: PASS
- fastDuringDetailUnder30Seconds: PASS
- detailIsAsync: PASS
- detailUsesBirefnet: PASS