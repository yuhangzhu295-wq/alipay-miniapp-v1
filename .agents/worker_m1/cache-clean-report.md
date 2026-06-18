# Cache Clean Report

## 1. Directory Footprint Summary

| Cache Directory / File Path | Size Before (MB) | Size After (MB) | Number of Files After | Status |
| :--- | :---: | :---: | :---: | :--- |
| `C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii\runtime` | 1342.89 | 0.00 | 0 | Cleared |
| `C:\Users\zyu33\AppData\Local\Temp\idphoto_hivision_ascii\standalone-output` | 1.20 | 0.00 | 0 | Cleared |
| `C:\Users\zyu33\AppData\Local\Temp\id_photo_server` | 2.54 | 0.00 | 2 | Cleared & Registry Reset |
| `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\server\outputs` | 4.53 | 0.00 | 0 | Cleared |
| `C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\logs` | 3.45 | 0.00 | 0 | Cleared |
| `watermark-iopaint-8081.err.log` (Project Root) | 0.0015 | Deleted | - | Deleted |
| `watermark-iopaint-8081.log` (Project Root) | 0.0021 | Deleted | - | Deleted |
| **Total** | **1354.61** | **0.00** | **2** | **Cleanup Successful** |

*Note: The remaining files in `id_photo_server` are the two reset registry JSON files:*
* `asset_registry.json` (reset to `[]` - 2 bytes)
* `user_photo_registry.json` (reset to `{}` - 4 bytes)

---

## 2. Root Cause of Accumulation
1. **Intermediate Image Generation**: The `HivisionIDPhotos` backend process generates intermediate matting, portrait, layout, and output images for each certificate photo request. These files are stored in the AppData local temp directories (`idphoto_hivision_ascii\runtime` and `id_photo_server\outputs`) and are not deleted post-response.
2. **Persistent Registries**: Details of all generated photo assets and user assets are saved continuously to `asset_registry.json` and `user_photo_registry.json`.
3. **Log Accumulation**: Uvicorn servers and IOPaint instances write verbose logging information during application runs. Without automated log-rotation policies, log directories (`logs/` and root log files) expand indefinitely.
4. **No Automated Invalidation**: The application lacks an automated cache invalidation daemon or cron job to clean temp outputs older than a specific threshold.

---

## 3. Verification Checks
1. **Directory Integrity**: Checked recursively using PowerShell commands to verify all files are cleared while keeping directory structures intact (preventing runtime crashes when folders are missing).
2. **Model Weight Safety**: Confirmed that all ONNX and TFLite model weights (BirefNet, MODNet, RMBG, RetinaFace) and the Torch checkpoint weights (`big-lama.pt`) are untouched and completely intact (totaling ~629.58 MB across original folders).
3. **Registry Format**: Confirmed `asset_registry.json` is set to valid JSON array `[]`, and `user_photo_registry.json` is set to valid JSON object `{}`.
