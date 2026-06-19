# Handoff Report

## 1. Observation

Direct code observations from the codebase:

- **Backend `id_photo_compose` endpoint in `server/main.py`** (line 1548):
  It calculates `layout_url = layout_saved["urlWithVersion"]` at line 1515, but fails to include `"layoutUrl"` in the returned JSON object:
  ```python
  return {
      "success": True,
      "imageUrl": image_url,
      "finalImageUrl": image_url,
      "resultUrl": image_url,
      ...
  }
  ```
- **API client in `utils/aiImageApi.js`** (lines 395-437):
  The response parsing in `composeIdPhotoV2` resolves without extracting or returning the layoutUrl:
  ```javascript
  _downloadResult(imageUrl).then(function(localPath) {
    resolve({
      tempFilePath: localPath,
      resultPath: localPath,
      finalImageUrl: fullUrl,
      previewUrl: fullUrl,
      downloadUrl: downloadUrl,
      previewFilePath: previewFilePath,
      downloadFilePath: downloadFilePath,
      cacheBust: cacheBust,
      remoteUrl: fullUrl,
      code: data.code || '',
      preparedId: data.preparedId || options.preparedId,
      bgColor: data.bgColor || options.bgColor,
      bgColorName: data.bgColorName || options.bgColorName,
      spec: data.spec || null,
      quality: data.quality || {},
      engine: engine,
      engineVersion: engineVersion,
      engineModel: engineModel,
      debug: data.debug || null,
      requestId: requestId,
      message: data.message || '生成成功'
    });
  })
  ```
- **Page Generate in `pages/generate/generate.js`** (lines 548-566 & 580-605):
  It does not save `layoutUrl` to page state. In `generateLayoutPhoto`, it immediately triggers local canvas-based stiching (`imageUtil.generateLayoutPhoto`). The `savePhoto` method saves depending on `outputTab`:
  ```javascript
  savePhoto: function() {
    var that = this;
    var saveSrc = that.data.outputTab === 'layout' ? that.data.layoutImage : that.data.resultImage;
    ...
  ```
- **Page Result in `pages/result/result.js`** (lines 122-144):
  `selectLayout` also generates layout photos on the client side without checking if a backend layout photo exists:
  ```javascript
  imageUtil.generateLayoutPhoto(userPhoto, spec, cols, rows)
    .then((path) => {
      this.setData({ showPreview: true, previewSrc: path });
    })
  ```
- **Verification Script in `server/scripts/verify_frontend_ui.py`** (lines 60-94 & 105-111):
  The `HARNESS` mocks `wx` but does not include `wx.showActionSheet`. The `composeIdPhotoV2` mock does not return a `layoutUrl`.

---

## 2. Logic Chain

1. **Backend Return (`server/main.py`)**: Since the backend generates a cache-busted layout URL but does not return it in `/api/id-photo/compose` response, we must add `"layoutUrl": layout_url` to the response dictionary.
2. **API Client Support (`utils/aiImageApi.js`)**: Since the API client does not parse `layoutUrl`, we must extract, normalize, and include `layoutUrl` in the resolved objects of `composeIdPhotoV2` and `generateIdPhotoV2`.
3. **Generate Page Option (`pages/generate/generate.js` & `.wxml`)**:
   - Since the layout tab currently generates stitching locally, we must change `generateLayoutPhoto` to check for `resultLayoutUrl`, download it via `wx.downloadFile` if present, and only fallback to local generation if it fails or is absent.
   - Since the user needs options to download both, we must check if `resultLayoutUrl` is present in `savePhoto`. If it is, show `wx.showActionSheet` to select between Single and Layout download, and trigger the download/save code for the selected URL.
4. **Result Page Support (`pages/result/result.js` & `.wxml`)**: Since `pages/result/result.js` has a layout selector, we can retrieve `app.globalData.generatedLayoutUrl` in `onLoad` and update `selectLayout` to download it for `4x2` layout mode, ensuring a higher-quality layout photo is shown/saved.
5. **Test Validation (`server/scripts/verify_frontend_ui.py`)**: Since `savePhoto` will now invoke `wx.showActionSheet` if `layoutUrl` is mocked, the test harness will crash unless we mock `wx.showActionSheet`. Updating the harness mocks and adding assertions on `resultLayoutUrl` ensures the entire flow is validated automatically.

---

## 3. Caveats

- **Network and Caching**: The layout photo is downloaded from the backend using `wx.downloadFile`. If the user is offline or the backend server is shut down after photo composition, it will gracefully fallback to the local canvas-based layout generation.
- **Result Page Redo**: Redoing (changing color or spec) on the result page calls the client-side `imageUtil.generateIDPhoto` and does not call the backend APIs. Therefore, for redone photos on the result page, only local canvas layout generation will be available, which is normal.

---

## 4. Conclusion

The implementation design for frontend layout download options is complete. The changes consist of returning `layoutUrl` from the backend, passing it through the API client, checking and using it in `pages/generate/generate.js` and `pages/result/result.js`, and extending the automated test mocks in `verify_frontend_ui.py`.

---

## 5. Verification Method

To verify the correct functionality:
1. Propose implementing the changes detailed in `analysis.md`.
2. Run the automated WeChat UI validation script:
   ```bash
   python server/scripts/verify_frontend_ui.py
   ```
3. A successful run (`PASS`) with all checks green verifies the entire frontend UI state flow including composition, ActionSheet display, and download.
