# Frontend Layout Download Option Feature Analysis

This report outlines the proposed design and implementation plan for introducing a frontend option to download the six-inch layout photo (排版照) from the backend. The backend already supports layout photo generation, but the frontend needs to retrieve, preview, and download it.

---

## 1. Backend Endpoint: `/api/id-photo/compose`

### Current State
In `server/main.py`, the `/api/id-photo/compose` endpoint generates both the single ID photo (`out_bytes`) and the six-inch layout photo (`layout_bytes`) from the prepared image. It saves both files and generates their URLs using version cache-busting (lines 1503-1515):
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
However, the response dictionary returned by the endpoint (lines 1548-1581) does not include `"layoutUrl": layout_url`.

### Proposed Changes
Add the `"layoutUrl"` field directly into the returned JSON payload of `/api/id-photo/compose` in `server/main.py`.

**Code Snippet Proposal:**
```python
        # server/main.py:1548
        return {
            "success": True,
            "imageUrl": image_url,
            "finalImageUrl": image_url,
            "resultUrl": image_url,
            "previewUrl": image_url,
            "downloadUrl": image_url,
            "layoutUrl": layout_url,              # <-- Added field
            "outputUrl": saved["url"],
            "previewFilePath": saved["storagePath"],
            "downloadFilePath": saved["storagePath"],
            ...
```

---

## 2. API Client: `utils/aiImageApi.js`

### Current State
The API client functions `generateIdPhotoV2` and `composeIdPhotoV2` parse the HTTP response from the server but only return the single photo's `tempFilePath`, `finalImageUrl`, etc., completely discarding `layoutUrl`.

### Proposed Changes
Update both functions to parse and return `layoutUrl` if present in the backend response.

#### 1) Changes to `composeIdPhotoV2` (lines 395-437):
**Before:**
```javascript
        if (data.success && (data.finalImageUrl || data.resultUrl || data.imageUrl)) {
          var requestId = data.requestId || (data.debug && data.debug.requestId) || '';
          var cacheBust = data.cacheBust || (data.debug && data.debug.cacheBust) || requestId || Date.now();
          var imageUrl = _withCacheBust(data.previewUrl || data.finalImageUrl || data.resultUrl || data.imageUrl, requestId, cacheBust);
          var fullUrl = _normalizeResultUrl(imageUrl);
          var downloadUrl = _normalizeResultUrl(_withCacheBust(data.downloadUrl || imageUrl, requestId, cacheBust));
          var previewFilePath = data.previewFilePath || (data.debug && data.debug.previewFilePath) || '';
          var downloadFilePath = data.downloadFilePath || (data.debug && data.debug.downloadFilePath) || '';
          var engine = data.engine || (data.debug && data.debug.engine) || '';
          var engineVersion = data.engineVersion || (data.debug && data.debug.engineVersion) || '';
          var engineModel = data.engineModel || data.model || (data.debug && data.debug.engineModel) || '';
          ...
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
            ...
```

**After:**
```javascript
        if (data.success && (data.finalImageUrl || data.resultUrl || data.imageUrl)) {
          var requestId = data.requestId || (data.debug && data.debug.requestId) || '';
          var cacheBust = data.cacheBust || (data.debug && data.debug.cacheBust) || requestId || Date.now();
          var imageUrl = _withCacheBust(data.previewUrl || data.finalImageUrl || data.resultUrl || data.imageUrl, requestId, cacheBust);
          var fullUrl = _normalizeResultUrl(imageUrl);
          var downloadUrl = _normalizeResultUrl(_withCacheBust(data.downloadUrl || imageUrl, requestId, cacheBust));
          var previewFilePath = data.previewFilePath || (data.debug && data.debug.previewFilePath) || '';
          var downloadFilePath = data.downloadFilePath || (data.debug && data.debug.downloadFilePath) || '';
          var engine = data.engine || (data.debug && data.debug.engine) || '';
          var engineVersion = data.engineVersion || (data.debug && data.debug.engineVersion) || '';
          var engineModel = data.engineModel || data.model || (data.debug && data.debug.engineModel) || '';
          
          // Normalize layoutUrl if returned
          var layoutUrl = '';
          if (data.layoutUrl) {
            layoutUrl = _normalizeResultUrl(_withCacheBust(data.layoutUrl, requestId, cacheBust));
          }
          
          ...
          _downloadResult(imageUrl).then(function(localPath) {
            resolve({
            tempFilePath: localPath,
            resultPath: localPath,
            finalImageUrl: fullUrl,
            previewUrl: fullUrl,
            downloadUrl: downloadUrl,
            layoutUrl: layoutUrl,                  // <-- Pass it back
            previewFilePath: previewFilePath,
            downloadFilePath: downloadFilePath,
            cacheBust: cacheBust,
            remoteUrl: fullUrl,
            ...
```

#### 2) Changes to `generateIdPhotoV2` (lines 260-275):
Extract `layoutUrl` and add it to the resolved object:
```javascript
          if (data.success && (data.finalImageUrl || data.resultUrl || data.imageUrl)) {
            var imageUrl = data.finalImageUrl || data.resultUrl || data.imageUrl;
            var fullUrl = _normalizeResultUrl(imageUrl);
            var layoutUrl = data.layoutUrl ? _normalizeResultUrl(data.layoutUrl) : '';
            resolve({
              tempFilePath: fullUrl,
              resultPath: fullUrl,
              finalImageUrl: fullUrl,
              remoteUrl: fullUrl,
              layoutUrl: layoutUrl,                // <-- Pass it back
              mode: data.mode || options.mode || 'official',
              ...
```

---

## 3. Frontend Page: `pages/generate/generate.js` & `generate.wxml`

### Current State
- `pages/generate/generate.js` stores the generated single photo in `resultImage`, `resultPreviewSrc`, and `resultRemoteUrl` (lines 488-502).
- When switching to the "排版电子照" tab, `generateLayoutPhoto()` is called, which calls `imageUtil.generateLayoutPhoto` to perform canvas stitching locally (lines 548-566).
- `savePhoto` determines which file to save (`layoutImage` vs `resultImage`) solely based on the active tab `outputTab` (lines 580-605).

### Proposed Changes

#### 1) Page Data & State Sync
Store the returned `layoutUrl` into page data as `resultLayoutUrl` inside `generatePhoto`:
```javascript
        that.setData({
          generating: false,
          processState: 'ready',
          statusText: requestBgColorName + ' · 可下载',
          resultImage: result.tempFilePath,
          resultPreviewSrc: result.previewUrl || result.finalImageUrl || result.remoteUrl || result.tempFilePath,
          resultRemoteUrl: result.finalImageUrl || result.remoteUrl || '',
          resultLayoutUrl: result.layoutUrl || '', // <-- Storing layoutUrl
          resultColorId: requestBgColorId,
          layoutColorId: '',
          canDownload: true
        }, function() {
          if (that.data.outputTab === 'layout') {
            that.generateLayoutPhoto();
          }
        });
```

#### 2) Tab Preview (`generateLayoutPhoto`)
Modify `generateLayoutPhoto` to check if `resultLayoutUrl` is present. If it is, download it first to display in the preview card, instead of doing local canvas generation:
```javascript
  generateLayoutPhoto: function() {
    var that = this;
    if (!that.data.resultImage || !that.data.currentSpec) return;
    if (that.data.resultColorId !== that.data.bgColorId) {
      wx.showToast({ title: '请先生成当前底色证件照', icon: 'none' });
      return;
    }
    
    // Use backend-generated layout if available
    if (that.data.resultLayoutUrl) {
      wx.showLoading({ title: '加载排版照...' });
      wx.downloadFile({
        url: that.data.resultLayoutUrl,
        success: function(res) {
          wx.hideLoading();
          if (res.statusCode === 200 && res.tempFilePath) {
            that.setData({
              layoutImage: res.tempFilePath,
              layoutColorId: that.data.resultColorId
            });
          } else {
            that.generateLocalLayoutPhoto(); // Fallback
          }
        },
        fail: function() {
          wx.hideLoading();
          that.generateLocalLayoutPhoto(); // Fallback
        }
      });
      return;
    }
    
    that.generateLocalLayoutPhoto();
  },

  // Helper method extracted from original generateLayoutPhoto
  generateLocalLayoutPhoto: function() {
    var that = this;
    imageUtil.generateLayoutPhoto(that.data.resultImage, that.data.currentSpec, 4, 2, '#ffffff')
      .then(function(path) {
        that.setData({
          layoutImage: path,
          layoutColorId: that.data.resultColorId
        });
      })
      .catch(function(err) {
        console.error('[generate] layout failed:', err);
        wx.showToast({ title: '排版照生成失败', icon: 'none' });
      });
  },
```

#### 3) Action Sheet Option (`savePhoto`)
When `resultLayoutUrl` is present, show a action sheet on download button click. Introduce a helper `downloadAndSavePhoto(src, type)`:
```javascript
  savePhoto: function() {
    var that = this;
    if (!that.data.canDownload) {
      wx.showToast({ title: '请先生成可下载的证件照', icon: 'none' });
      return;
    }

    if (that.data.resultLayoutUrl) {
      wx.showActionSheet({
        itemList: ['下载单张照片', '下载六寸排版照'],
        success: function(res) {
          if (res.tapIndex === 0) {
            that.downloadAndSavePhoto(that.data.resultRemoteUrl || that.data.resultImage, 'idPhoto');
          } else if (res.tapIndex === 1) {
            that.downloadAndSavePhoto(that.data.resultLayoutUrl, 'layout');
          }
        }
      });
      return;
    }

    // Fallback to original tab-based behavior if backend layoutUrl is absent
    var saveSrc = that.data.outputTab === 'layout' ? that.data.layoutImage : that.data.resultImage;
    if (that.data.outputTab !== 'layout' && that.data.resultColorId !== that.data.bgColorId) {
      wx.showToast({ title: '请先生成当前底色证件照', icon: 'none' });
      that.generatePhoto();
      return;
    }
    if (that.data.outputTab === 'layout' && that.data.layoutColorId !== that.data.bgColorId) {
      that.generateLayoutPhoto();
      wx.showToast({ title: '正在生成当前底色排版照', icon: 'none' });
      return;
    }
    if (that.data.outputTab === 'layout' && !saveSrc && that.data.resultImage) {
      that.generateLayoutPhoto();
      wx.showToast({ title: '正在生成排版照', icon: 'none' });
      return;
    }
    if (!saveSrc) {
      wx.showToast({ title: '请先生成证件照', icon: 'none' });
      return;
    }
    that.downloadAndSavePhoto(saveSrc, that.data.outputTab === 'layout' ? 'layout' : 'idPhoto');
  },

  downloadAndSavePhoto: function(src, type) {
    var that = this;
    var doSave = function(filePath) {
      wx.saveImageToPhotosAlbum({
        filePath: filePath,
        success: function() {
          wx.showToast({ title: '已保存到相册', icon: 'success' });
          var createdAt = Date.now();
          var record = {
            id: 'photo_' + createdAt,
            imagePath: filePath,
            imageUrl: type === 'layout' ? that.data.resultLayoutUrl : that.data.resultRemoteUrl,
            remoteUrl: type === 'layout' ? that.data.resultLayoutUrl : that.data.resultRemoteUrl,
            specId: that.data.currentSpecId,
            specName: that.data.specName,
            sizeText: that.data.specSize,
            bgColorName: that.data.bgColorName,
            backgroundColor: that.data.bgColorName,
            widthPx: that.data.currentSpec ? (that.data.currentSpec.widthPx || 0) : 0,
            heightPx: that.data.currentSpec ? (that.data.currentSpec.heightPx || 0) : 0,
            type: type,
            createdAt: createdAt,
            expireAt: createdAt + 24 * 3600 * 1000
          };
          var list = wx.getStorageSync('myPhotos') || [];
          list.unshift(record);
          wx.setStorageSync('myPhotos', list);
          imageService.savePhotoRecord(record);
        },
        fail: function(err) {
          if (err.errMsg.indexOf('auth') !== -1 || err.errMsg.indexOf('deny') !== -1) {
            wx.showModal({
              title: '需要权限',
              content: '请在设置中开启保存到相册权限',
              success: function(res) { if (res.confirm) wx.openSetting(); }
            });
          } else {
            wx.showToast({ title: '保存失败，请重试', icon: 'none' });
          }
        }
      });
    };

    if (src.indexOf('http') === 0) {
      wx.showLoading({ title: '准备下载...' });
      wx.downloadFile({
        url: src,
        timeout: 60000,
        success: function(res) {
          wx.hideLoading();
          if (res.statusCode === 200 && res.tempFilePath) {
            doSave(res.tempFilePath);
          } else {
            wx.showToast({ title: '下载失败，请重试', icon: 'none' });
          }
        },
        fail: function(err) {
          wx.hideLoading();
          console.error('[generate] download before save failed:', err);
          wx.showToast({ title: '下载失败，请重试', icon: 'none' });
        }
      });
      return;
    }
    doSave(src);
  }
```

---

## 4. Frontend Page: `pages/result/result.js` & `result.wxml`

### Current State
- `pages/result/result.js` loads the image generated from `app.globalData.generatedPhoto || app.globalData.userPhoto`.
- The user can select layout modes (e.g. `4x2`). When selected, it triggers `selectLayout()`, which calls `imageUtil.generateLayoutPhoto` on the client side (canvas stitching).

### Proposed Changes
Propose integrating backend layout support if `app.globalData.generatedLayoutUrl` is present.

#### 1) Retrieving `layoutUrl`
In `onLoad()`, save the `layoutUrl` to `app.globalData` if present, or pass it back:
```javascript
  onLoad() {
    const app = getApp();
    const userPhoto = app.globalData.generatedPhoto || app.globalData.userPhoto;
    const selectedSpec = app.globalData.selectedSpec;
    const selectedColor = app.globalData.selectedColor;
    const layoutUrl = app.globalData.generatedLayoutUrl || ''; // <-- Retrieve layoutUrl

    ...
    this.setData({
      photoSrc: userPhoto,
      layoutUrl,                                             // <-- Store in data
      bgColorHex: selectedColor ? selectedColor.hex : '#ffffff',
      ...
    });
  }
```

#### 2) Preview/Save using Backend Layout
Modify `selectLayout` to prioritize downloading the backend layout URL for the `4x2` layout mode (the standard 6-inch layout) if present:
```javascript
  selectLayout(e) {
    const layoutId = e.currentTarget.dataset.layout;
    this.setData({ selectedLayout: layoutId });

    if (layoutId === 'single') {
      this.setData({ showPreview: false, previewSrc: null });
      return;
    }

    const app = getApp();
    const spec = app.globalData.selectedSpec || specs.getSpecById('1inch_normal');
    const userPhoto = app.globalData.generatedPhoto || app.globalData.userPhoto;
    const [cols, rows] = layoutId.split('x').map(Number);

    // If backend-generated layout matches the standard 4x2 layout, prioritize downloading it
    if (layoutId === '4x2' && this.data.layoutUrl) {
      wx.showLoading({ title: '加载排版照...' });
      wx.downloadFile({
        url: this.data.layoutUrl,
        success: (res) => {
          wx.hideLoading();
          if (res.statusCode === 200 && res.tempFilePath) {
            this.setData({ showPreview: true, previewSrc: res.tempFilePath });
          } else {
            this.generateLocalLayout(userPhoto, spec, cols, rows); // Fallback
          }
        },
        fail: () => {
          wx.hideLoading();
          this.generateLocalLayout(userPhoto, spec, cols, rows); // Fallback
        }
      });
      return;
    }

    this.generateLocalLayout(userPhoto, spec, cols, rows);
  },

  generateLocalLayout(userPhoto, spec, cols, rows) {
    imageUtil.generateLayoutPhoto(userPhoto, spec, cols, rows)
      .then((path) => {
        this.setData({ showPreview: true, previewSrc: path });
      })
      .catch(() => {
        wx.showToast({ title: '排版生成失败', icon: 'none' });
      });
  }
```
This is fully compatible with the existing `savePhoto()` implementation in `result.js`, which saves `this.data.previewSrc` (which will contain the local downloaded file path).

---

## 5. Automated Verification: `server/scripts/verify_frontend_ui.py`

### Proposed Changes

#### 1) Mock update for `composeIdPhotoV2`
Add `layoutUrl` to the mock output of `composeIdPhotoV2` in `HARNESS` (lines 105-111):
```javascript
      composeIdPhotoV2: (payload) => Promise.resolve({
        success: true,
        tempFilePath: 'tmp://final-' + (payload.bgColorName || 'blue') + '.jpg',
        finalImageUrl: 'http://127.0.0.1:8000/outputs/final.jpg',
        layoutUrl: 'http://127.0.0.1:8000/outputs/layout.jpg', // <-- Mocked layoutUrl
        quality: { qualityReport: { passed: true, score: 99 } },
        debug: { usedForegroundPng: true, usedOriginalImageDirectly: false }
      }),
```

#### 2) Mock update for `wx` global object
Add `showActionSheet` method to the mocked `wx` object in `HARNESS` (lines 60-94):
```javascript
  showActionSheet(opts) {
    wxCalls.push({ fn: 'showActionSheet', opts });
    if (opts && opts.success) opts.success({ tapIndex: 0 }); // Simulate choosing the first option
  },
```

#### 3) Assertion in UI Flow test
Add assertions verifying `resultLayoutUrl` is populated and `wx.showActionSheet` is invoked inside the `generate upload -> compose -> save` check (lines 185-196):
```javascript
  checks.push(await runCheck('generate upload -> compose -> save', async () => {
    const page = loadPage('pages/generate/generate');
    page.onLoad({ specId: 'yicun' });
    page.choosePhoto();
    await sleep(60);
    assert(page.data.photoSrc, 'photoSrc not set');
    assert(page.data.canDownload === true, 'canDownload not true after compose');
    assert(page.data.resultImage, 'resultImage missing');
    
    // Assert resultLayoutUrl is set correctly
    assert(page.data.resultLayoutUrl === 'http://127.0.0.1:8000/outputs/layout.jpg', 'resultLayoutUrl not set correctly');
    
    page.savePhoto();
    
    // Assert wx.showActionSheet was called during savePhoto
    assert(wxCalls.some(c => c.fn === 'showActionSheet'), 'showActionSheet not called');
    
    return { resultImage: page.data.resultImage, canDownload: page.data.canDownload, resultLayoutUrl: page.data.resultLayoutUrl };
  }));
```
