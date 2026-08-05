# Thirty Real Image Matrix

- Status: PASS
- Sources: 3 current user originals plus 27 archived real-person source/normalized regression images.
- Archived normalized images are disclosed as normalized regression inputs, not phone-camera originals.
- Ordinary P50/P95/max: 795/910/911 ms
- Ordinary synchronous DETAIL count: 0
- Spec requests: 120
- Async DETAIL statuses: `{'completed': 30}`
- Five-color attempts / generated downloads: 45 / 18
- Existing driver-template purpose mismatch responses: 30 (recorded, not changed in this performance scope)

## Checks
- thirtyRealImages: PASS
- currentThreeOriginalsIncluded: PASS
- ordinaryNoSyncDetail: PASS
- ordinaryUnder30Seconds: PASS
- allFourSpecsReturnedClearly: PASS
- allMattingSpecRunsModnetOnly: PASS
- allMattingSpecRunsNoSyncDetail: PASS
- allDetailCreatesImmediate: PASS
- allDetailJobsUseBirefnet: PASS
- allDetailJobsTerminal: PASS
- usableImagesHaveFiveColorAttempts: PASS
- allColorAttemptsReturnClearly: PASS
- allSuccessfulColorsDownload: PASS