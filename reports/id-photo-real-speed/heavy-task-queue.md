# Heavy Task Queue

- Status: PASS
- Base URL: `https://tupzjianzhao.chat`
- Ten FAST: P50 1865 ms, P95 4103 ms, max 4103 ms
- FAST during DETAIL: 7866 ms
- DETAIL create: 351 ms; final state: completed
- Production process snapshot after the run: Backend 7.5% CPU / 118724 KB RSS; FAST Worker 6.8% CPU / 329720 KB RSS; IOPaint 0.2% CPU / 504880 KB RSS.
- Production memory snapshot: 1378 MB used of 3723 MB; swap 1487 MB used of 6083 MB; load average 0.54 / 1.03 / 0.71.
- Local peak sampling is preserved in `heavy-task-queue-local.json`; remote resource values above come from `ps`, `free -m`, and `uptime` on Tencent Cloud rather than the local verifier process.
- LaMa scenarios: tested

## Checks
- tenFastReturnedClearly: PASS
- tenFastNoSyncDetail: PASS
- tenFastModnetOnly: PASS
- tenFastUnder30Seconds: PASS
- fastDuringDetailUnder30Seconds: PASS
- detailIsAsync: PASS
- detailUsesBirefnet: PASS
- fastDuringLamaUnder30Seconds: PASS
- lamaWithFastSucceeded: PASS
- lamaDuringDetailSucceeded: PASS
- detailWithLamaCompleted: PASS
