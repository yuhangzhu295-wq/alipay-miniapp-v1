# Handoff Report — explorer_layout_download_1

## 1. Observation
We examined several files in the codebase and observed the following:

- **Backend Endpoint: `/api/id-photo/compose`** in `server/main.py`
  - In `server/main.py` lines 1503-1515, `layout_url` is processed and saved:
    ```python
    layout_url = ""
    if "layoutPath" in result and result["layoutPath"]:
        with open(result["layoutPath"], "rb") as f:
            layout_bytes = f.read()
        _remove_temp_file(result.get("layoutPath"))
        layout_saved = save_output_with_meta(
            layout_bytes,
            ".jpg",
            asset_type="id_photo_layout",
            source_type="id_photo_compose",
            request_id=request_id,
        )
        layout_url = layout_saved["urlWithVersion"]
    ```
  - However, in lines 1548-1581, the return dictionary of `id_photo_compose` does not contain any key named `layoutUrl` or `layout_url`.

- **API Wrapper: `utils/aiImageApi.js`**
  - In `utils/aiImageApi.js` lines 260-275, `generateIdPhotoV2` resolves a promise with a response object but completely ignores `data.layoutUrl`.
  - In `utils/aiImageApi.js` lines 395-437, `composeIdPhotoV2` parses `data` and retrieves versioned image paths but does not extract `data.layoutUrl` or resolve it.

- **Generate Page: `pages/generate/generate.js`**
  - In `pages/generate/generate.js` lines 580-674, `savePhoto()` determines the image source purely based on `outputTab`:
    ```javascript
    var saveSrc = that.data.outputTab === 'layout' ? that.data.layoutImage : that.data.resultImage;
    ```
    And calls `wx.saveImageToPhotosAlbum` or downloads the source without offering any option selector.

- **Result Page: `pages/result/result.js`**
  - In `pages/result/result.js` lines 147-158, `savePhoto()` saves `previewSrc || photoSrc` directly. It does not check or offer any layout download options.

- **Automated Tests: `server/scripts/verify_frontend_ui.py`**
  - Inside the `HARNESS` constant (lines 24-322), the mocked `composeIdPhotoV2` implementation (lines 105-111) only returns:
    ```javascript
    composeIdPhotoV2: (payload) => Promise.resolve({
      success: true,
      tempFilePath: 'tmp://final-' + (payload.bgColorName || 'blue') + '.jpg',
      finalImageUrl: 'http://127.0.0.1:8000/outputs/final.jpg',
      quality: { qualityReport: { passed: true, score: 99 } },
      debug: { usedForegroundPng: true, usedOriginalImageDirectly: false }
    })
    ```
  - The mock `wx` object in the test runner (lines 60-94) does not contain a mock for `wx.showActionSheet`.

---

## 2. Logic Chain
1. **Observation**: The backend generates and saves the layout image but does not include `"layoutUrl"` in the returned JSON of `/api/id-photo/compose`.
   **Inference**: To make layout downloading possible, we must return `"layoutUrl"` in the compose route response.
2. **Observation**: `aiImageApi.js` does not parse the `layoutUrl` returned in `/api/id-photo/compose` and `/api/id-photo/generate-v2`.
   **Inference**: To make `layoutUrl` accessible to pages, the wrapper functions `generateIdPhotoV2` and `composeIdPhotoV2` must extract and normalize `layoutUrl` and include it in the resolved object.
3. **Observation**: `pages/generate/generate.js` and `pages/result/result.js` save photos directly without offering choices.
   **Inference**: If `layoutUrl` is returned in page data, `savePhoto` should call `wx.showActionSheet` with options for "单张照片" and "六寸排版照" to allow downloading either.
4. **Observation**: The test runner in `verify_frontend_ui.py` runs real JS page code but lacks mocks for `wx.showActionSheet` and `layoutUrl` response field.
   **Inference**: Adding these frontend changes without updating the test mocks will crash the test execution with `TypeError: wx.showActionSheet is not a function`. Therefore, the mocks must be updated.

---

## 3. Caveats
- **Local Generation Fallback**: When `layoutUrl` is not present (e.g. backend failed to generate or apiConfig disables AI), the frontend will fall back to its existing behavior (generating the layout locally via HTML5 canvas).
- **Result Page Status**: `pages/result/result` exists in the codebase but is not registered in the pages section of `app.json`. The design assumes that if it is ever registered or navigated to, it can store/read `layoutUrl` globally in `app.globalData.layoutUrl`.

---

## 4. Conclusion
The frontend layout download option feature requires:
1. Returning `"layoutUrl": layout_url` in the `/api/id-photo/compose` backend endpoint.
2. Parsing and resolving `layoutUrl` in `utils/aiImageApi.js`.
3. Presenting a `wx.showActionSheet` selector in both `pages/generate/generate.js` and `pages/result/result.js` when `layoutUrl` is available.
4. Updating the mocks (`wx.showActionSheet` and `layoutUrl` field) in `server/scripts/verify_frontend_ui.py`.

---

## 5. Verification Method
1. Check the backend: Run `pytest` or verify endpoint response structure to ensure `"layoutUrl"` is included.
2. Check the frontend test runner: Run `python server/scripts/verify_frontend_ui.py`. It should complete successfully with `PASS`.
3. Manual verification: Open WeChat Developer Tools, generate an ID photo, and verify that clicking "下载证件照" displays an action sheet containing:
   - "下载单张照片"
   - "下载六寸排版照"
