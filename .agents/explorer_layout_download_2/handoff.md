# Handoff Report — explorer_layout_download_2

## 1. Observation
We observed the following exact paths and lines in the codebase:
- **Backend `server/main.py`**:
  - Inside `/api/id-photo/compose` (lines 1503–1515), the backend generates `layout_url = layout_saved["urlWithVersion"]`.
  - Inside the returned JSON response of `/api/id-photo/compose` (lines 1548–1581), the key `"layoutUrl"` is missing from the dictionary:
    ```python
    return {
        "success": True,
        "imageUrl": image_url,
        "finalImageUrl": image_url,
        "resultUrl": image_url,
        "previewUrl": image_url,
        "downloadUrl": image_url,
        # missing "layoutUrl": layout_url
        "outputUrl": saved["url"],
        "previewFilePath": saved["storagePath"],
        "downloadFilePath": saved["storagePath"],
        ...
    ```
  - In `/api/id-photo/generate-v2` (lines 1259-1264, 1278), the backend generates and returns `"layoutUrl": layout_url` correctly.
- **Frontend API `utils/aiImageApi.js`**:
  - `generateIdPhotoV2` success callback (lines 260–275) resolves the promise with a payload that does not extract `data.layoutUrl`.
  - `composeIdPhotoV2` success callback (lines 395–437) resolves the promise with a payload that does not extract or cache-bust `data.layoutUrl`.
- **Frontend Generate Page `pages/generate/generate.js`**:
  - `generatePhoto` (lines 488–502) does not store the `result.layoutUrl` in the page's data.
  - `savePhoto` (lines 580–674) directly downloads and/or saves `resultImage` or `layoutImage` depending on the active tab without displaying any options or action sheet.
- **Frontend Result Page `pages/result/result.js`**:
  - Not registered in `app.json` (lines 2-12).
  - `onLoad` (lines 23-55) does not read `layoutUrl` from options or global storage.
  - `selectLayout` (lines 121-144) only calls local canvas helper `imageUtil.generateLayoutPhoto`.
  - `savePhoto` (lines 147-158) calls `imageUtil.saveImageToAlbum(path)` directly. If `path` is a remote URL starting with `http`, it fails because `wx.saveImageToPhotosAlbum` expects a local file path.
- **Test Harness `server/scripts/verify_frontend_ui.py`**:
  - `HARNESS` defines the Node.js mock WeChat runtime.
  - Mocked `utils/aiImageApi.js` -> `composeIdPhotoV2` (lines 105-111) does not return `layoutUrl`.
  - Mocked `global.wx` object (lines 60-94) does not define `showActionSheet`. Adding a call to `wx.showActionSheet` on the frontend will cause crashes during automated verification.

---

## 2. Logic Chain
1. **Backend Response**: Since `/api/id-photo/compose` does not return `layoutUrl` in its response payload, the frontend has no way of obtaining the backend-generated layout image URL during composition.
2. **API Layer**: Even if the backend returns it, `utils/aiImageApi.js` does not parse and resolve `layoutUrl` back to the calling page.
3. **Generate Page UI**: In `pages/generate/generate.js`, `savePhoto` currently downloads the active tab image. To offer the choice between "单张照片" or "六寸排版照", we must show a `wx.showActionSheet` when `layoutUrl` is set.
4. **Result Page UI**: Although `pages/result/result.js` is not in `app.json`, it also needs to receive `layoutUrl`, set it as `previewSrc` when the `4x2` layout is chosen, and use `wx.downloadFile` to fetch the remote URL before calling `saveImageToPhotosAlbum` inside `savePhoto`.
5. **Test Harness Compatibility**: Adding `wx.showActionSheet` to the frontend pages will break the automated frontend tests in `server/scripts/verify_frontend_ui.py` unless the test harness mocks `wx.showActionSheet` and `composeIdPhotoV2` provides a mock `layoutUrl`.

---

## 3. Caveats
- `pages/result/result` is currently not registered in `app.json`. The application relies primarily on `pages/generate/generate` for background switching and downloads.
- `layoutUrl` is assumed to be a standard HTTP URL, which requires a pre-download step (`wx.downloadFile`) on WeChat Mini-Programs before passing it to `wx.saveImageToPhotosAlbum`.

---

## 4. Conclusion
To support layout download options:
1. Return `layoutUrl` in `/api/id-photo/compose`'s response dict.
2. Update `utils/aiImageApi.js` to extract and resolve `layoutUrl`.
3. In `pages/generate/generate.js`, show `wx.showActionSheet` if `layoutUrl` is present during save, giving download options and handling the remote file downloading sequence.
4. Update `pages/result/result.js` to receive `layoutUrl`, render it directly for `4x2` mode, and download remote paths before saving.
5. Update `server/scripts/verify_frontend_ui.py` with mock implementations for `wx.showActionSheet` and `layoutUrl` responses to prevent test failures.

---

## 5. Verification Method
1. Run `python server/scripts/verify_frontend_ui.py` in the workspace root.
2. Run `python server/scripts/verify_all.py` to check for full backend and UI compatibility.
3. Inspect `reports/final/frontend-ui-report.json` to verify that all checks, including any added layout option checks, passed successfully.
