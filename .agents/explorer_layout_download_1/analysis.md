# Analysis & Design: Frontend Layout Download Option Feature

This report details the design for implementing the frontend layout download option when generating ID photos. Since the backend can generate both a single ID photo and a 6-inch layout photo, this design enables the user to select whether they want to download the single photo or the pre-formatted 6-inch layout photo when clicking the save button.

---

## 1. Backend Endpoint: `/api/id-photo/compose` (`server/main.py`)

### Observations
- In `server/main.py`, the `/api/id-photo/compose` route (handled by `id_photo_compose`) processes the layout generation.
- It correctly saves the layout image (if present in the generator result) and obtains its versioned URL:
  ```python
  layout_url = ""
  if "layoutPath" in result and result["layoutPath"]:
      # ...
      layout_saved = save_output_with_meta(
          layout_bytes,
          ".jpg",
          asset_type="id_photo_layout",
          source_type="id_photo_compose",
          request_id=request_id,
      )
      layout_url = layout_saved["urlWithVersion"]
  ```
- However, `layoutUrl` is **not** included in the JSON response dictionary returned by `id_photo_compose` (lines 1548–1581).

### Proposed Changes
Add `"layoutUrl": layout_url` to the response payload returned by `id_photo_compose` in `server/main.py`:
```python
        return {
            "success": True,
            "imageUrl": image_url,
            "finalImageUrl": image_url,
            "resultUrl": image_url,
            "previewUrl": image_url,
            "downloadUrl": image_url,
            "outputUrl": saved["url"],
            "layoutUrl": layout_url,              # <-- Add this line
            "previewFilePath": saved["storagePath"],
            # ...
        }
```

---

## 2. API Wrapper: `utils/aiImageApi.js`

### Observations
- `generateIdPhotoV2`: parses `/api/id-photo/generate-v2` response. It extracts properties but does not parse `layoutUrl`.
- `composeIdPhotoV2`: parses `/api/id-photo/compose` response. It extracts properties and resolves a promise but completely ignores `layoutUrl` (lines 395–437).

### Proposed Changes
1. **In `generateIdPhotoV2`** (extract `layoutUrl` from response and normalize it):
   ```javascript
   if (data.success && (data.finalImageUrl || data.resultUrl || data.imageUrl)) {
     var imageUrl = data.finalImageUrl || data.resultUrl || data.imageUrl;
     var fullUrl = _normalizeResultUrl(imageUrl);
     resolve({
       tempFilePath: fullUrl,
       resultPath: fullUrl,
       finalImageUrl: fullUrl,
       remoteUrl: fullUrl,
       layoutUrl: data.layoutUrl ? _normalizeResultUrl(data.layoutUrl) : '', // <-- Add this
       // ...
     });
   }
   ```

2. **In `composeIdPhotoV2`** (extract `layoutUrl` from response, add cache-busting, normalize, and resolve):
   ```javascript
   if (data.success && (data.finalImageUrl || data.resultUrl || data.imageUrl)) {
     var requestId = data.requestId || (data.debug && data.debug.requestId) || '';
     var cacheBust = data.cacheBust || (data.debug && data.debug.cacheBust) || requestId || Date.now();
     var imageUrl = _withCacheBust(data.previewUrl || data.finalImageUrl || data.resultUrl || data.imageUrl, requestId, cacheBust);
     var fullUrl = _normalizeResultUrl(imageUrl);
     var downloadUrl = _normalizeResultUrl(_withCacheBust(data.downloadUrl || imageUrl, requestId, cacheBust));
     var layoutUrl = data.layoutUrl ? _normalizeResultUrl(_withCacheBust(data.layoutUrl, requestId, cacheBust)) : ''; // <-- Add this
     // ...
     _downloadResult(imageUrl).then(function(localPath) {
       resolve({
         tempFilePath: localPath,
         resultPath: localPath,
         finalImageUrl: fullUrl,
         previewUrl: fullUrl,
         downloadUrl: downloadUrl,
         layoutUrl: layoutUrl, // <-- Add this
         // ...
       });
     });
   }
   ```

---

## 3. Generate Page: `pages/generate/generate.js` & `generate.wxml`

### Observations
- When saving, `savePhoto()` (lines 580–674) currently inspects the active tab (`outputTab === 'layout'` vs `'photo'`) and saves either `layoutImage` or `resultImage`.
- No `wx.showActionSheet` is currently offered. If `layoutUrl` is returned from the server, we should let the user choose which option they want to download.

### Proposed Changes
1. **Page State**:
   - Initialize `layoutUrl: ''` in default page `data` and reset it in `applySpec()`, `choosePhoto()`, and `takePhoto()`.
   - Update `generatePhoto` success handler to store `layoutUrl` in page data:
     ```javascript
     that.setData({
       generating: false,
       processState: 'ready',
       statusText: requestBgColorName + ' · 可下载',
       resultImage: result.tempFilePath,
       resultPreviewSrc: result.previewUrl || result.finalImageUrl || result.remoteUrl || result.tempFilePath,
       resultRemoteUrl: result.finalImageUrl || result.remoteUrl || '',
       layoutUrl: result.layoutUrl || '', // <-- Add this
       resultColorId: requestBgColorId,
       layoutColorId: '',
       canDownload: true
     });
     ```

2. **Save Action**:
   - Update `savePhoto()` to check if `layoutUrl` is present. If it is, show a `wx.showActionSheet`.
   - Implement a shared helper `downloadAndSavePhoto(src, type)` to reduce duplicate download and storage code:
     ```javascript
     savePhoto: function() {
       var that = this;
       if (!that.data.canDownload) {
         wx.showToast({ title: '请先生成可下载的证件照', icon: 'none' });
         return;
       }
       if (that.data.layoutUrl) {
         wx.showActionSheet({
           itemList: ['下载单张照片', '下载六寸排版照'],
           success: function(res) {
             if (res.tapIndex === 0) {
               that.downloadAndSavePhoto(that.data.resultRemoteUrl || that.data.resultImage, 'idPhoto');
             } else if (res.tapIndex === 1) {
               that.downloadAndSavePhoto(that.data.layoutUrl, 'layout');
             }
           }
         });
         return;
       }
       
       // Fallback to original tab-based download
       var saveSrc = that.data.outputTab === 'layout' ? that.data.layoutImage : that.data.resultImage;
       if (!saveSrc) {
         wx.showToast({ title: '请先生成照片', icon: 'none' });
         return;
       }
       that.downloadAndSavePhoto(saveSrc, that.data.outputTab === 'layout' ? 'layout' : 'idPhoto');
     },
     ```

3. **Optimizing Layout Tab Load**:
   - In `setOutputTab`, if the user switches to the `layout` tab and `layoutUrl` is available but not yet loaded locally as `layoutImage`, download the remote layout photo to `layoutImage` so it displays instantly and can be saved directly if they don't want to use the action sheet:
     ```javascript
     setOutputTab: function(e) {
       var tab = e.currentTarget.dataset.tab;
       var that = this;
       this.setData({ outputTab: tab }, function() {
         if (tab === 'layout') {
           if (that.data.layoutUrl) {
             if (!that.data.layoutImage) {
               wx.showLoading({ title: '加载排版中...' });
               wx.downloadFile({
                 url: that.data.layoutUrl,
                 success: function(res) {
                   wx.hideLoading();
                   if (res.statusCode === 200 && res.tempFilePath) {
                     that.setData({
                       layoutImage: res.tempFilePath,
                       layoutColorId: that.data.resultColorId
                     });
                   }
                 },
                 fail: function() {
                   wx.hideLoading();
                   that.generateLayoutPhoto();
                 }
               });
             }
           } else if (that.data.resultImage && !that.data.layoutImage) {
             that.generateLayoutPhoto();
           }
         }
       });
     }
     ```

---

## 4. Result Page: `pages/result/result.js` & `pages/result/result.wxml`

### Observations
- `pages/result/result.js` is not registered in `app.json`, but exists in the workspace.
- It receives page data (photo details) from `app.globalData`.
- In `savePhoto()`, it saves the image directly. If `layoutUrl` is present, it should also allow downloading the layout photo.

### Proposed Changes
1. **Pass `layoutUrl` Globally**:
   - Store `layoutUrl` in `app.globalData.layoutUrl` during generation (in `generate.js`).
2. **Result Page Load**:
   - Read `layoutUrl` from `app.globalData.layoutUrl` in `onLoad()`:
     ```javascript
     const layoutUrl = app.globalData.layoutUrl || '';
     this.setData({
       layoutUrl,
       // ...
     });
     ```
3. **Save Action**:
   - Update `savePhoto` to show the action sheet if `layoutUrl` is present:
     ```javascript
     savePhoto() {
       const path = this.data.previewSrc || this.data.photoSrc;
       if (!path) {
         wx.showToast({ title: '没有可保存的照片', icon: 'none' });
         return;
       }

       if (this.data.layoutUrl && this.data.selectedLayout === 'single') {
         wx.showActionSheet({
           itemList: ['下载单张照片', '下载六寸排版照'],
           success: (res) => {
             if (res.tapIndex === 0) {
               this.downloadAndSavePhoto(this.data.photoSrc);
             } else if (res.tapIndex === 1) {
               this.downloadAndSavePhoto(this.data.layoutUrl);
             }
           }
         });
         return;
       }
       
       this.downloadAndSavePhoto(path);
     },
     ```
   - Implement `downloadAndSavePhoto(url)` to handle both remote downloads and local album saves:
     ```javascript
     downloadAndSavePhoto(url) {
       if (!url) return;
       wx.showLoading({ title: '保存中...' });
       if (url.indexOf('http') === 0) {
         wx.downloadFile({
           url: url,
           success: (res) => {
             if (res.statusCode === 200 && res.tempFilePath) {
               imageUtil.saveImageToAlbum(res.tempFilePath)
                 .then(() => wx.hideLoading())
                 .catch(() => wx.hideLoading());
             } else {
               wx.hideLoading();
               wx.showToast({ title: '下载失败', icon: 'none' });
             }
           },
           fail: () => {
             wx.hideLoading();
             wx.showToast({ title: '下载失败', icon: 'none' });
           }
         });
       } else {
         imageUtil.saveImageToAlbum(url)
           .then(() => wx.hideLoading())
           .catch(() => wx.hideLoading());
       }
     }
     ```

---

## 5. Automated Mocks/Tests: `server/scripts/verify_frontend_ui.py`

### Observations
- The automated verification script executes page Javascript modules inside a mocked WeChat runtime.
- Since `composeIdPhotoV2` mock does not return `layoutUrl`, and `wx` mock does not include `showActionSheet`, implementing the design as-is will cause test failures (methods not found or missing assertions).

### Proposed Changes
1. **Mock `layoutUrl` in `composeIdPhotoV2`** (in `HARNESS` constant):
   ```javascript
         composeIdPhotoV2: (payload) => Promise.resolve({
           success: true,
           tempFilePath: 'tmp://final-' + (payload.bgColorName || 'blue') + '.jpg',
           finalImageUrl: 'http://127.0.0.1:8000/outputs/final.jpg',
           layoutUrl: 'http://127.0.0.1:8000/outputs/layout.jpg', // <-- Add this mocked field
           quality: { qualityReport: { passed: true, score: 99 } },
           debug: { usedForegroundPng: true, usedOriginalImageDirectly: false }
         }),
   ```
2. **Mock `wx.showActionSheet`** (in `HARNESS` constant):
   ```javascript
     showActionSheet(opts) {
       wxCalls.push({ fn: 'showActionSheet', opts });
       if (opts && opts.success) opts.success({ tapIndex: 0 }); // Simulate selecting tapIndex 0
     },
   ```
3. **Add automated test check for the action sheet and layoutUrl**:
   ```javascript
     checks.push(await runCheck('generate layout download options via ActionSheet', async () => {
       const page = loadPage('pages/generate/generate');
       page.onLoad({ specId: 'yicun' });
       page.choosePhoto();
       await sleep(60);
       assert(page.data.layoutUrl, 'layoutUrl not set');
       const startIndex = wxCalls.length;
       page.savePhoto();
       assert(wxCalls.slice(startIndex).some(c => c.fn === 'showActionSheet'), 'showActionSheet not called');
       assert(wxCalls.slice(startIndex).some(c => c.fn === 'saveImageToPhotosAlbum'), 'saveImageToPhotosAlbum not called');
       return { layoutUrl: page.data.layoutUrl };
     }));
     ```
