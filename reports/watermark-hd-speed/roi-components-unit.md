# 高清 ROI 单元验证

- 状态：PASS

- single-small: PASS; components=1; rois=1; calls=1; sizes=['218x173']
- two-near: PASS; components=2; rois=1; calls=1; sizes=['283x178']
- two-far: PASS; components=2; rois=2; calls=2; sizes=['198x173', '208x178']
- top-bottom: PASS; components=2; rois=2; calls=2; sizes=['208x168', '208x168']
- many-small: PASS; components=5; rois=2; calls=2; sizes=['946x656', '168x158']
- one-large: PASS; components=1; rois=1; calls=1; sizes=['1016x686']

## 静态契约
- normalizedStrokeTransportRetained: PASS
- realStageLabelsPresent: PASS
- elapsedWithoutFakePercent: PASS
- duplicateHdSubmissionGuard: PASS
- progressEndpointPresent: PASS
- pageReceivesHdStatus: PASS
- quickQualityMappingUnchanged: PASS
