# Watermark HD Chain Validation Report

- Status: PASS
- Base URL: `http://127.0.0.1:8000`
- Generated samples: 9
- Contact sheet: `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\reports\final\watermark-comparison-contact-sheet.jpg`
- Diff images: `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\reports\final\watermark-samples\diff`

## Backend Health
- /api/health: PASS
- /api/watermark/health: PASS
- manualEngine: `opencv_manual`
- quickEngine: `opencv_quick`
- hdEngine: `lama`
- hdRealModelLoaded: `True`
- fallbackUsed: `False`

## Chain Isolation
- First manual resultUrl: `/uploads/watermark/manual/result_1785960720519_17c08825c2a6.jpg`
- First hd resultUrl: `/uploads/watermark/hd/result_1785960722740_057cce864e0e.jpg`
- First manual/hd same URL: `False`
- First manual/hd same hash: `False`

## Frontend Audit
- healthUsesWatermarkHealth: PASS
- manualEndpointPresent: PASS
- quickEndpointPresent: PASS
- hdEndpointPresent: PASS
- pageCallsQuickForScan: PASS
- pageCallsHdForHd: PASS
- separateStateManual: PASS
- separateStateQuick: PASS
- separateStateHd: PASS
- currentStateUsedForDownload: PASS
- ordinaryUiHidesEngineAndOutput: PASS
- hdHealthRequiresRealModel: PASS
- debugPanelHiddenDefault: PASS
- noAiExperimentText: PASS
- canvasUndoRedoClearPresent: PASS
- localBackendConfigured: PASS

## Sample Matrix
- 01_portrait_blue: PASS
- 02_document_diagonal: PASS
- 03_product_logo: PASS
- 04_dark_scene: PASS
- 05_light_stamp: PASS
- 06_qr_corner: PASS
- 07_wide_banner: PASS
- 08_busy_texture: PASS
- 09_diagonal_tile_wall: PASS