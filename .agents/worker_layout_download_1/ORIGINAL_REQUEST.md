## 2026-06-19T14:49:21+08:00
You are worker_layout_download_1. Your working directory is C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\.agents\worker_layout_download_1.
Your task is to implement the frontend layout download option feature in the backend and frontend codebase.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Please implement the following changes precisely:

1. **Backend Route (`server/main.py`)**:
   - In `/api/id-photo/compose` endpoint (around line 1548), include `"layoutUrl": layout_url` in the returned JSON dictionary.

2. **API Wrapper (`utils/aiImageApi.js`)**:
   - In `composeIdPhotoV2`, parse `data.layoutUrl` if present, normalize it using `_normalizeResultUrl(_withCacheBust(data.layoutUrl, requestId, cacheBust))`, and return it as `layoutUrl: layoutUrl` in the resolved promise object.
   - In `generateIdPhotoV2`, parse `data.layoutUrl` if present, normalize it using `_normalizeResultUrl(data.layoutUrl)`, and return it as `layoutUrl: layoutUrl` in the resolved promise object.

3. **Page Generate (`pages/generate/generate.js`)**:
   - Add `resultLayoutUrl: ''` to `data` in `pages/generate/generate.js`.
   - Make sure to clear `resultLayoutUrl: ''` in all `setData` blocks where `resultImage` is cleared (e.g. lines 141, 171, 195, 226, 256, 378, 536).
   - In `generatePhoto`'s success handler, set `resultLayoutUrl: result.layoutUrl || ''` and save it to `app.globalData.generatedLayoutUrl = result.layoutUrl || ''`.
   - In `generateLayoutPhoto`, check if `this.data.resultLayoutUrl` is present. If it is, download it using `wx.downloadFile` and set the local path to `layoutImage` (with `layoutColorId: this.data.resultColorId`). If download fails or it's not present, fallback to local canvas stitching (original behavior).
   - In `savePhoto`, check if `this.data.resultLayoutUrl` is present. If it is, show a `wx.showActionSheet` with options `['下载单张照片', '下载六寸排版照']`.
     - Clicking the first option (index 0) should download and save the single photo URL (`this.data.resultRemoteUrl || this.data.resultImage`, type 'idPhoto').
     - Clicking the second option (index 1) should download and save the layout photo URL (`this.data.resultLayoutUrl`, type 'layout').
     - Implement a helper `downloadAndSavePhoto(src, type)` that does `wx.downloadFile` if it is a remote URL, and then saves it via `wx.saveImageToPhotosAlbum` (which saves and updates local storage history).

4. **Page Result (`pages/result/result.js`)**:
   - Retrieve `layoutUrl` from `app.globalData.generatedLayoutUrl` (or options) in `onLoad` and save to `this.data.layoutUrl`.
   - In `selectLayout`, if `layoutId === '4x2'` and `this.data.layoutUrl` is present, download it using `wx.downloadFile` and set `previewSrc: res.tempFilePath`. If it fails or is absent, fallback to local canvas layout generation.
   - In `savePhoto()`, if `this.data.layoutUrl` is present, present a `wx.showActionSheet` choosing between "下载单张照片" and "下载六寸排版照". Download/save the corresponding photo using `wx.downloadFile` and `imageUtil.saveImageToAlbum`.

5. **Automated Test Mocks (`server/scripts/verify_frontend_ui.py`)**:
   - In the mock of `composeIdPhotoV2`, return `layoutUrl: 'http://127.0.0.1:8000/outputs/layout.jpg'`.
   - In the `wx` mock object, add a mock implementation of `showActionSheet` that registers the call and automatically executes success callback with `tapIndex: 0`.
   - In the `generate upload -> compose -> save` check, assert that `page.data.resultLayoutUrl === 'http://127.0.0.1:8000/outputs/layout.jpg'` and that `wx.showActionSheet` was invoked.

6. **Verify and Run Tests**:
   - Start the backend server if not running.
   - Run: `npm run verify:frontend-ui` to verify the frontend UI test suite.
   - Run: `npm run verify:full-business-flow` and other business verification scripts to ensure no regressions.
   - Run: `node server/scripts/verify_devtools_business_flow.js` if applicable.

Report back with the files modified, commands run, and test output results.
When done, report back using send_message to orchestrator (ID: 5f758f22-cb05-4822-bdcd-35b830bf9313).
