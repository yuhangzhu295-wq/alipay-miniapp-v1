/**
 * AI 图像处理 API 封装
 *
 * 所有方法通过 wx.uploadFile 上传图片到后端，下载处理后结果。
 * 失败时不返回原图，必须返回明确的错误。
 *
 * 使用方式：
 *   var aiApi = require('../../utils/aiImageApi.js');
 *   aiApi.changeBg(imagePath, 'blue').then(function(resultPath) { ... });
 */

var config = require('./apiConfig.js');
var imageSafetyApi = require('./imageSafetyApi.js');
var edgeCompute = require('./edgeCompute.js');
var ID_PHOTO_PREPARE_TIMEOUT_MS = 30000;
var ID_PHOTO_COMPOSE_TIMEOUT_MS = 60000;
var ID_PHOTO_UPLOAD_MAX_SIDE = 1600;
var ID_PHOTO_UPLOAD_QUALITY = 88;

function _safetyPurposeForEndpoint(url) {
  var endpoint = String(url || '');
  if (endpoint.indexOf('/api/id-photo/') >= 0) return 'id_photo';
  if (endpoint.indexOf('/api/watermark/') >= 0 || endpoint.indexOf('/api/inpaint') >= 0) return 'watermark_removal';
  if (endpoint.indexOf('/api/professional-photo') >= 0) return 'professional_photo';
  if (endpoint.indexOf('/api/change-bg') >= 0 || endpoint.indexOf('/api/remove-bg') >= 0) return 'background_processing';
  if (endpoint.indexOf('/api/compress') >= 0) return 'image_compress';
  if (endpoint.indexOf('/api/verify-photo') >= 0 || endpoint.indexOf('/api/portrait/') >= 0) return 'portrait_inspection';
  return 'image_processing';
}

function _safeUploadFile(options) {
  return imageSafetyApi.uploadWithSafety(options, _safetyPurposeForEndpoint(options.url));
}

/**
 * 健康检查 — 判断后端是否启动
 * @returns {Promise<boolean>}
 */
function checkApiAvailable() {
  return new Promise(function (resolve) {
    if (!config.ENABLE_AI || !config.API_BASE_URL) {
      resolve(false);
      return;
    }
    wx.request({
      url: config.API_BASE_URL + '/api/health',
      method: 'GET',
      timeout: 5000,
      success: function (res) {
        resolve(res.statusCode === 200 && res.data && res.data.success);
      },
      fail: function () {
        resolve(false);
      }
    });
  });
}

/**
 * AI 抠图 — 返回透明 PNG
 * @param {string} imagePath — 图片临时路径
 * @returns {Promise<string>} 处理后图片临时路径
 */
function removeBg(imagePath, model) {
  return new Promise(function (resolve, reject) {
    if (!_checkConfig()) { reject(new Error('AI 服务未配置')); return; }

    wx.showLoading({ title: 'AI抠图中...' });

    var formData = {};
    if (model) {
      formData.model = model;
    }

    _safeUploadFile({
      url: config.API_BASE_URL + '/api/remove-bg',
      filePath: imagePath,
      name: 'file',
      formData: formData,
      timeout: 60000,
      success: function (res) {
        wx.hideLoading();
        try {
          var data = JSON.parse(res.data);
          if (data.success && data.imageUrl) {
            _downloadResult(data.imageUrl).then(resolve).catch(reject);
          } else {
            reject(new Error(data.message || '抠图失败'));
          }
        } catch (e) {
          reject(new Error('后端返回异常: ' + (res.data || '').substring(0, 100)));
        }
      },
      fail: function (err) {
        wx.hideLoading();
        reject(new Error('连接后端失败，请确保服务已启动: ' + (err.errMsg || '')));
      }
    });
  });
}

/**
 * AI 换底色 — 抠图后合成新背景
 * @param {string} imagePath — 图片临时路径
 * @param {string} bgColor — blue | white | red | lightBlue | gray
 * @param {string} model — 抠图模型名称 (u2net_human_seg | isnet-anime)
 * @returns {Promise<string>} 处理后图片临时路径
 */
function changeBg(imagePath, bgColor, model) {
  return new Promise(function (resolve, reject) {
    if (!_checkConfig()) { reject(new Error('AI 服务未配置')); return; }

    wx.showLoading({ title: 'AI换底色中...' });

    var formData = { bgColor: bgColor };
    if (model) {
      formData.model = model;
    }

    _safeUploadFile({
      url: config.API_BASE_URL + '/api/change-bg',
      filePath: imagePath,
      name: 'file',
      formData: formData,
      timeout: 90000,
      success: function (res) {
        wx.hideLoading();
        try {
          var data = JSON.parse(res.data);
          if (data.success && data.imageUrl) {
            _downloadResult(data.imageUrl).then(resolve).catch(reject);
          } else {
            reject(_makeApiError(data, '换底色失败'));
          }
        } catch (e) {
          reject(new Error('后端返回异常: ' + (res.data || '').substring(0, 100)));
        }
      },
      fail: function (err) {
        wx.hideLoading();
        reject(new Error('连接后端失败，请确保服务已启动: ' + (err.errMsg || '')));
      }
    });
  });
}

function validatePortraitInput(imagePath, task) {
  return new Promise(function(resolve, reject) {
    if (!_checkConfig()) { reject(new Error('AI 服务未配置')); return; }
    _safeUploadFile({
      url: config.API_BASE_URL + '/api/portrait/validate',
      filePath: imagePath,
      name: 'file',
      formData: { task: task || 'changeBg' },
      timeout: 30000,
      success: function(res) {
        try {
          var data = JSON.parse(res.data);
          if (data.success) {
            resolve(data.quality || {});
          } else {
            reject(_makeApiError(data, '当前图片不适合生成证件照/职业形象照，请上传单人正面真人照片。'));
          }
        } catch (e) {
          reject(new Error('生成失败，请重新上传符合要求的照片。'));
        }
      },
      fail: function(err) {
        console.error('[portrait] validate upload failed:', err);
        reject(new Error('生成失败，请重新上传符合要求的照片。'));
      }
    });
  });
}

function inspectPortrait(imagePath) {
  return new Promise(function(resolve, reject) {
    if (!_checkConfig()) { reject(new Error('生成服务暂不可用，请稍后重试。')); return; }
    _safeUploadFile({
      url: config.API_BASE_URL + '/api/portrait/inspect',
      filePath: imagePath,
      name: 'image',
      formData: {},
      timeout: 30000,
      success: function(res) {
        try {
          var data = JSON.parse(res.data);
          if (data.success) {
            resolve(data);
          } else {
            reject(_makeApiError(data, '未检测到清晰人物主体，请重新上传头像或半身照。'));
          }
        } catch (e) {
          reject(new Error('生成服务暂不可用，请稍后重试。'));
        }
      },
      fail: function(err) {
        console.error('[portrait] inspect failed:', err);
        reject(new Error('生成服务暂不可用，请稍后重试。'));
      }
    });
  });
}

function getIdPhotoCapabilities() {
  return new Promise(function(resolve, reject) {
    if (!_checkConfig()) { reject(new Error('生成服务暂不可用，请稍后重试。')); return; }
    wx.request({
      url: config.API_BASE_URL + '/api/id-photo/capabilities',
      method: 'GET',
      timeout: 10000,
      success: function(res) {
        var data = res.data || {};
        if (res.statusCode === 200 && data.success) {
          resolve(data);
        } else {
          reject(_makeApiError(data, '生成服务暂不可用，请稍后重试。'));
        }
      },
      fail: function(err) {
        console.error('[id-photo] capabilities failed:', err);
        reject(new Error('生成服务暂不可用，请稍后重试。'));
      }
    });
  });
}

function generateIdPhotoV2(imagePath, options) {
  options = options || {};
  return new Promise(function(resolve, reject) {
    if (!_checkConfig()) { reject(new Error('生成服务暂不可用，请稍后重试。')); return; }

    wx.showLoading({ title: '生成中...' });
    var endpoint = config.API_BASE_URL + '/api/id-photo/generate-v2';
    var formData = {
      purpose: options.purpose || 'official_id_photo',
      specId: options.specId || '',
      widthPx: options.widthPx ? String(options.widthPx) : '',
      heightPx: options.heightPx ? String(options.heightPx) : '',
      widthMm: options.widthMm ? String(options.widthMm) : '',
      heightMm: options.heightMm ? String(options.heightMm) : '',
      bgColor: options.bgColor || '',
      bgColorName: options.bgColorName || '',
      imageType: options.imageType || '',
      mode: options.mode || 'official',
      composition: options.composition || '',
      enhanceLevel: options.enhanceLevel || 'standard',
      outputType: options.outputType || 'jpg',
      hairRetouch: options.hairRetouch ? 'true' : 'false'
    };
    console.log('[id-photo-api] API_BASE_URL:', config.API_BASE_URL);
    console.log('[id-photo-api] endpoint:', endpoint);
    console.log('[id-photo-api] request:', {
      specId: formData.specId,
      widthPx: formData.widthPx,
      heightPx: formData.heightPx,
      bgColor: formData.bgColor,
      bgColorName: formData.bgColorName
    });
    _safeUploadFile({
      url: endpoint,
      filePath: imagePath,
      name: 'image',
      formData: formData,
      timeout: 120000,
      success: function(res) {
        wx.hideLoading();
        try {
          var data = JSON.parse(res.data);
          console.log('[id-photo-api] response:', {
            statusCode: res.statusCode,
            success: !!(data && data.success),
            code: data && data.code,
            hasImageUrl: !!(data && data.imageUrl)
          });
          if (res.statusCode === 404) {
            var notFound = new Error('生成接口不可用，请检查本地服务。');
            notFound.code = 'ENDPOINT_NOT_FOUND';
            reject(notFound);
            return;
          }
          if (data.success && (data.finalImageUrl || data.resultUrl || data.imageUrl)) {
            var imageUrl = data.finalImageUrl || data.resultUrl || data.imageUrl;
            var fullUrl = _normalizeResultUrl(imageUrl);
            resolve({
              tempFilePath: fullUrl,
              resultPath: fullUrl,
              finalImageUrl: fullUrl,
              remoteUrl: fullUrl,
              mode: data.mode || options.mode || 'official',
              imageType: data.imageType || options.imageType || 'unknown',
              spec: data.spec || null,
              outfit: data.outfit || null,
              warnings: data.warnings || [],
              message: data.message || '生成成功',
              quality: data.quality || {}
            });
          } else {
            reject(_makeApiError(data, '生成失败，请重新上传清晰的人像照片后重试。'));
          }
        } catch (e) {
          var parseErr = new Error(res.statusCode === 404 ? '生成接口不可用，请检查本地服务。' : '生成服务暂不可用，请稍后重试。');
          parseErr.code = res.statusCode === 404 ? 'ENDPOINT_NOT_FOUND' : 'SERVICE_UNAVAILABLE';
          reject(parseErr);
        }
      },
      fail: function(err) {
        wx.hideLoading();
        console.error('[id-photo] generate-v2 upload failed:', err);
        var apiErr = new Error('生成服务暂不可用，请稍后重试。');
        apiErr.code = 'SERVICE_UNAVAILABLE';
        reject(apiErr);
      }
    });
  });
}

function _notifyIdPhotoStage(options, stage, detail) {
  if (options && typeof options.onStage === 'function') {
    options.onStage(stage, detail || {});
  }
}

function _getLocalFileSize(filePath) {
  return new Promise(function(resolve) {
    if (!wx.getFileSystemManager) { resolve(0); return; }
    wx.getFileSystemManager().getFileInfo({
      filePath: filePath,
      success: function(res) { resolve(Number(res.size || 0)); },
      fail: function() { resolve(0); }
    });
  });
}

function _getImageInfo(filePath) {
  return new Promise(function(resolve, reject) {
    if (!wx.getImageInfo) { resolve({ path: filePath, width: 0, height: 0, type: '' }); return; }
    wx.getImageInfo({ src: filePath, success: resolve, fail: reject });
  });
}

function _makeUploadPreparationError(code, cause) {
  var error = new Error('Unable to prepare a resized upload copy. Please retry or choose another photo.');
  error.code = code;
  error.cause = cause || null;
  return error;
}

function _createIdPhotoUploadWorkCopy(photoSrc, targetWidth, targetHeight) {
  return new Promise(function(resolve, reject) {
    if (!wx.createOffscreenCanvas) {
      reject(_makeUploadPreparationError('ID_PHOTO_UPLOAD_COPY_UNSUPPORTED'));
      return;
    }
    try {
      var canvas = wx.createOffscreenCanvas({ type: '2d', width: targetWidth, height: targetHeight });
      var context = canvas.getContext('2d');
      var image = canvas.createImage();
      image.onload = function() {
        context.drawImage(image, 0, 0, targetWidth, targetHeight);
        var exportOptions = {
          fileType: 'jpg',
          quality: ID_PHOTO_UPLOAD_QUALITY / 100,
          success: function(res) {
            if (res && res.tempFilePath) resolve(res.tempFilePath);
            else reject(_makeUploadPreparationError('ID_PHOTO_UPLOAD_COPY_EMPTY'));
          },
          fail: function(err) {
            reject(_makeUploadPreparationError('ID_PHOTO_UPLOAD_COPY_EXPORT_FAILED', err));
          }
        };
        if (canvas && typeof canvas.toTempFilePath === 'function') {
          canvas.toTempFilePath(exportOptions);
        } else if (wx.canvasToTempFilePath) {
          exportOptions.canvas = canvas;
          wx.canvasToTempFilePath(exportOptions);
        } else {
          reject(_makeUploadPreparationError('ID_PHOTO_UPLOAD_COPY_EXPORT_UNSUPPORTED'));
        }
      };
      image.onerror = function(err) {
        reject(_makeUploadPreparationError('ID_PHOTO_UPLOAD_COPY_DRAW_FAILED', err));
      };
      image.src = photoSrc;
    } catch (err) {
      reject(_makeUploadPreparationError('ID_PHOTO_UPLOAD_COPY_CREATE_FAILED', err));
    }
  });
}

function _readIdPhotoUploadCopy(base, uploadPath, targetWidth, targetHeight, compressFallback, startedAt) {
  return Promise.all([_getImageInfo(uploadPath), _getLocalFileSize(uploadPath)]).then(function(values) {
    var uploadInfo = values[0] || {};
    var uploadWidth = Number(uploadInfo.width || targetWidth);
    var uploadHeight = Number(uploadInfo.height || targetHeight);
    if (!uploadPath || Math.max(uploadWidth, uploadHeight) > ID_PHOTO_UPLOAD_MAX_SIDE) {
      throw _makeUploadPreparationError('ID_PHOTO_UPLOAD_COPY_DIMENSION_INVALID');
    }
    return Object.assign({}, base, {
      uploadPath: uploadPath,
      uploadWidth: uploadWidth,
      uploadHeight: uploadHeight,
      uploadBytes: Number(values[1] || 0),
      quality: ID_PHOTO_UPLOAD_QUALITY,
      compressed: true,
      compressFallback: !!compressFallback,
      compressMs: Date.now() - startedAt
    });
  });
}

function prepareIdPhotoUploadSource(photoSrc, options) {
  options = options || {};
  var startedAt = Date.now();
  _notifyIdPhotoStage(options, 'optimizing', {});
  return _getImageInfo(photoSrc).then(function(info) {
    return _getLocalFileSize(photoSrc).then(function(originalBytes) {
      var originalWidth = Number(info.width || 0);
      var originalHeight = Number(info.height || 0);
      var maxSide = Math.max(originalWidth, originalHeight);
      var base = {
        originalPath: photoSrc,
        uploadPath: photoSrc,
        originalWidth: originalWidth,
        originalHeight: originalHeight,
        uploadWidth: originalWidth,
        uploadHeight: originalHeight,
        originalBytes: originalBytes,
        uploadBytes: originalBytes,
        originalFormat: info.type || '',
        orientation: info.orientation || 'up',
        quality: null,
        maxSide: ID_PHOTO_UPLOAD_MAX_SIDE,
        compressed: false,
        compressFallback: false,
        compressMs: Date.now() - startedAt
      };
      if (!maxSide) {
        throw _makeUploadPreparationError('ID_PHOTO_UPLOAD_SOURCE_INFO_UNAVAILABLE');
      }
      if (maxSide <= ID_PHOTO_UPLOAD_MAX_SIDE) {
        return base;
      }
      var scale = ID_PHOTO_UPLOAD_MAX_SIDE / maxSide;
      var targetWidth = Math.max(1, Math.round(originalWidth * scale));
      var targetHeight = Math.max(1, Math.round(originalHeight * scale));
      function makeCanvasCopy() {
        return _createIdPhotoUploadWorkCopy(photoSrc, targetWidth, targetHeight).then(function(uploadPath) {
          return _readIdPhotoUploadCopy(base, uploadPath, targetWidth, targetHeight, true, startedAt);
        });
      }
      if (!wx.compressImage) {
        return makeCanvasCopy();
      }
      return new Promise(function(resolve, reject) {
        wx.compressImage({
          src: photoSrc,
          quality: ID_PHOTO_UPLOAD_QUALITY,
          compressedWidth: targetWidth,
          compressedHeight: targetHeight,
          success: function(res) {
            if (!res || !res.tempFilePath) {
              makeCanvasCopy().then(resolve).catch(reject);
              return;
            }
            _readIdPhotoUploadCopy(base, res.tempFilePath, targetWidth, targetHeight, false, startedAt).then(resolve).catch(function() {
              makeCanvasCopy().then(resolve).catch(reject);
            });
          },
          fail: function(err) {
            console.warn('[id-photo-speed] work copy fallback:', err);
            makeCanvasCopy().then(resolve).catch(reject);
          }
        });
      });
    });
  }).then(function(meta) {
    console.log('[id-photo-speed] originalWidth=' + meta.originalWidth);
    console.log('[id-photo-speed] originalHeight=' + meta.originalHeight);
    console.log('[id-photo-speed] originalBytes=' + meta.originalBytes);
    console.log('[id-photo-speed] uploadWidth=' + meta.uploadWidth);
    console.log('[id-photo-speed] uploadHeight=' + meta.uploadHeight);
    console.log('[id-photo-speed] uploadBytes=' + meta.uploadBytes);
    console.log('[id-photo-speed] compressed=' + meta.compressed);
    console.log('[id-photo-speed] compressFallback=' + meta.compressFallback);
    console.log('[id-photo-speed] compressMs=' + meta.compressMs);
    return meta;
  });
}

function prepareIdPhotoV2(imagePath, options) {
  options = options || {};
  var runtimeInfo = config.getApiRuntimeInfo ? config.getApiRuntimeInfo() : {
    envVersion: 'unknown',
    storedApiTarget: '',
    actualApiBaseUrl: config.API_BASE_URL
  };
  return prepareIdPhotoUploadSource(imagePath, options).then(function(uploadMeta) {
    return new Promise(function(resolve, reject) {
    var endpoint = runtimeInfo.actualApiBaseUrl + '/api/id-photo/prepare';
    var formData = {
      purpose: options.purpose || 'official_id_photo',
      specId: options.specId || '',
      widthPx: options.widthPx ? String(options.widthPx) : '',
      heightPx: options.heightPx ? String(options.heightPx) : '',
      widthMm: options.widthMm ? String(options.widthMm) : '',
      heightMm: options.heightMm ? String(options.heightMm) : '',
      imageType: options.imageType || '',
      mode: options.mode || 'official',
      composition: options.composition || '',
      hairRetouch: options.hairRetouch ? 'true' : 'false'
    };
    console.log('[id-photo-api] runtime:', runtimeInfo);
    console.log('[id-photo-api] prepare endpoint:', endpoint);
    console.log('[id-photo-fe] prepare endpoint=' + endpoint);
    console.log('[id-photo-api] prepare request:', {
      specId: formData.specId,
      widthPx: formData.widthPx,
      heightPx: formData.heightPx,
      composition: formData.composition
    });
    _notifyIdPhotoStage(options, 'uploading', uploadMeta);
    var uploadStartedAt = Date.now();
    var task = _safeUploadFile({
      url: endpoint,
      filePath: uploadMeta.uploadPath,
      name: 'image',
      formData: formData,
      timeout: ID_PHOTO_PREPARE_TIMEOUT_MS,
      success: function(res) {
        try {
          var data = JSON.parse(res.data);
          console.log('[id-photo-api] prepare response:', {
            statusCode: res.statusCode,
            success: !!(data && data.success),
            code: data && data.code,
            preparedId: data && data.preparedId
          });
          console.log('[id-photo-fe] prepare response success=' + !!(data && data.success));
          console.log('[id-photo-fe] prepare response code=' + ((data && data.code) || ''));
          console.log('[id-photo-fe] prepare engine=' + ((data && (data.engine || (data.debug && data.debug.engine))) || ''));
          console.log('[id-photo-fe] prepare engineVersion=' + ((data && (data.engineVersion || (data.debug && data.debug.engineVersion))) || ''));
          console.log('[id-photo-fe] prepare engineModel=' + ((data && (data.engineModel || (data.debug && data.debug.engineModel))) || ''));
          console.log('[id-photo-fe] prepare debug:', data && data.debug ? data.debug : null);
          var uploadMs = Date.now() - uploadStartedAt;
          var serverMs = data && data.performance ? Number(data.performance.totalServerMs || 0) : 0;
          var diagnostic = {
            envVersion: runtimeInfo.envVersion,
            storedApiTarget: runtimeInfo.storedApiTarget,
            actualApiBaseUrl: runtimeInfo.actualApiBaseUrl,
            endpoint: endpoint,
            httpStatus: Number(res.statusCode || 0),
            serverResponseCode: (data && data.code) || '',
            timeout: false,
            originalWidth: uploadMeta.originalWidth,
            originalHeight: uploadMeta.originalHeight,
            originalBytes: uploadMeta.originalBytes,
            uploadWidth: uploadMeta.uploadWidth,
            uploadHeight: uploadMeta.uploadHeight,
            uploadBytes: uploadMeta.uploadBytes,
            compressed: uploadMeta.compressed,
            compressFallback: uploadMeta.compressFallback,
            compressMs: uploadMeta.compressMs,
            uploadMs: uploadMs,
            serverMs: serverMs
          };
          console.log('[id-photo-prepare] diagnostic:', diagnostic);
          console.log('[id-photo-speed] uploadMs=' + uploadMs);
          console.log('[id-photo-speed] serverMs=' + serverMs);
          if (data && data.success && data.preparedId) {
            data.uploadMeta = uploadMeta;
            data.clientPerformance = { uploadMs: uploadMs, serverMs: serverMs };
            resolve(data);
          } else {
            var apiError = _makeApiError(data, '人像预处理失败，请重新上传清晰正面照片。');
            apiError.uploadMeta = uploadMeta;
            apiError.uploadMs = uploadMs;
            apiError.diagnostic = diagnostic;
            reject(apiError);
          }
        } catch (e) {
          console.error('[id-photo-prepare] response parse failed:', {
            envVersion: runtimeInfo.envVersion,
            storedApiTarget: runtimeInfo.storedApiTarget,
            actualApiBaseUrl: runtimeInfo.actualApiBaseUrl,
            endpoint: endpoint,
            httpStatus: Number(res.statusCode || 0),
            errMsg: e && e.message,
            uploadBytes: uploadMeta.uploadBytes,
            uploadMs: Date.now() - uploadStartedAt,
            responsePreview: String(res.data || '').slice(0, 160)
          });
          var err = new Error('生成服务暂不可用，请稍后重试。');
          err.code = 'SERVICE_UNAVAILABLE';
          err.diagnostic = {
            actualApiBaseUrl: runtimeInfo.actualApiBaseUrl,
            httpStatus: Number(res.statusCode || 0),
            errMsg: e && e.message,
            uploadBytes: uploadMeta.uploadBytes,
            uploadMs: Date.now() - uploadStartedAt
          };
          reject(err);
        }
      },
      fail: function(err) {
        console.error('[id-photo-api] prepare upload failed:', err);
        var isTimeout = err && err.errMsg && err.errMsg.indexOf('timeout') >= 0;
        var uploadMs = Date.now() - uploadStartedAt;
        var diagnostic = {
          envVersion: runtimeInfo.envVersion,
          storedApiTarget: runtimeInfo.storedApiTarget,
          actualApiBaseUrl: runtimeInfo.actualApiBaseUrl,
          endpoint: endpoint,
          httpStatus: 0,
          errMsg: (err && err.errMsg) || '',
          timeout: !!isTimeout,
          uploadBytes: uploadMeta.uploadBytes,
          uploadMs: uploadMs
        };
        console.error('[id-photo-prepare] transport failed:', diagnostic);
        var apiErr = new Error('生成服务暂不可用，请稍后重试。');
        apiErr.code = isTimeout ? 'ID_PHOTO_TIMEOUT' : 'SERVICE_UNAVAILABLE';
        apiErr.uploadMeta = uploadMeta;
        apiErr.uploadMs = uploadMs;
        apiErr.diagnostic = diagnostic;
        reject(apiErr);
      }
    });
    if (task && task.onProgressUpdate) {
      task.onProgressUpdate(function(progress) {
        if (progress && progress.progress >= 100) {
          _notifyIdPhotoStage(options, 'fastMatting', { uploadMs: Date.now() - uploadStartedAt });
        }
      });
    }
    });
  }).catch(function(err) {
    var diagnostic = (err && err.diagnostic) || {
      envVersion: runtimeInfo.envVersion,
      storedApiTarget: runtimeInfo.storedApiTarget,
      actualApiBaseUrl: runtimeInfo.actualApiBaseUrl,
      errMsg: (err && err.message) || '',
      timeout: !!(err && err.code === 'ID_PHOTO_TIMEOUT'),
      uploadBytes: err && err.uploadMeta ? err.uploadMeta.uploadBytes : 0,
      uploadMs: err && err.uploadMs ? err.uploadMs : 0
    };
    if (err) err.diagnostic = diagnostic;
    console.error('[id-photo-prepare] failed:', diagnostic);
    throw err;
  });
}

function createIdPhotoDetailJob(options) {
  options = options || {};
  return new Promise(function(resolve, reject) {
    wx.request({
      url: config.API_BASE_URL + '/api/id-photo/detail-jobs',
      method: 'POST',
      header: { 'content-type': 'application/x-www-form-urlencoded' },
      data: {
        preparedId: options.preparedId || '',
        sourceId: options.sourceId || '',
        fastPreviewUrl: options.fastPreviewUrl || ''
      },
      timeout: 10000,
      success: function(res) {
        var data = res.data || {};
        if (res.statusCode === 200 && data.jobId) resolve(data);
        else reject(_makeApiError(data, '发丝精修任务创建失败，请稍后重试。'));
      },
      fail: function() { reject(new Error('发丝精修任务创建失败，请稍后重试。')); }
    });
  });
}

function getIdPhotoDetailJob(jobId) {
  return new Promise(function(resolve, reject) {
    wx.request({
      url: config.API_BASE_URL + '/api/id-photo/detail-jobs/' + encodeURIComponent(jobId),
      method: 'GET',
      timeout: 10000,
      success: function(res) {
        var data = res.data || {};
        if (res.statusCode === 200 && data.jobId) resolve(data);
        else reject(_makeApiError(data, '获取发丝精修状态失败。'));
      },
      fail: function() { reject(new Error('获取发丝精修状态失败。')); }
    });
  });
}

function cancelIdPhotoDetailJob(jobId) {
  return new Promise(function(resolve) {
    wx.request({
      url: config.API_BASE_URL + '/api/id-photo/detail-jobs/' + encodeURIComponent(jobId),
      method: 'DELETE',
      timeout: 10000,
      complete: function(res) { resolve((res && res.data) || { status: 'cancelled' }); }
    });
  });
}

function composeIdPhotoV2(options) {
  options = options || {};
  return new Promise(function(resolve, reject) {
    var endpoint = config.API_BASE_URL + '/api/id-photo/compose';
    var composeStartedAt = Date.now();
    console.log('[id-photo-api] compose endpoint:', endpoint);
    console.log('[id-photo-fe] compose endpoint=' + endpoint);
    console.log('[id-photo-api] compose request:', {
      preparedId: options.preparedId,
      bgColor: options.bgColor,
      bgColorName: options.bgColorName
    });
    wx.request({
      url: endpoint,
      method: 'POST',
      header: { 'content-type': 'application/x-www-form-urlencoded' },
      data: {
        preparedId: options.preparedId || '',
        bgColor: options.bgColor || '',
        bgColorName: options.bgColorName || '',
        outputType: options.outputType || 'jpg'
      },
      timeout: ID_PHOTO_COMPOSE_TIMEOUT_MS,
      success: function(res) {
        var data = res.data || {};
        console.log('[id-photo-api] compose response:', {
          statusCode: res.statusCode,
          success: !!data.success,
          code: data.code,
          finalImageUrl: data.finalImageUrl
        });
        console.log('[id-photo-fe] compose response success=' + !!data.success);
        console.log('[id-photo-fe] compose response code=' + (data.code || ''));
        console.log('[id-photo-fe] finalImageUrl=' + (data.finalImageUrl || data.resultUrl || data.imageUrl || ''));
        console.log('[id-photo-fe] compose debug:', data.debug || null);
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
          console.log('[id-photo-fe] requestId=' + requestId);
          console.log('[id-photo-fe] engine=' + engine);
          console.log('[id-photo-fe] engineVersion=' + engineVersion);
          console.log('[id-photo-fe] engineModel=' + engineModel);
          console.log('[id-photo-fe] previewUrl=' + fullUrl);
          console.log('[id-photo-fe] downloadUrl=' + downloadUrl);
          console.log('[id-photo-fe] previewFilePath=' + previewFilePath);
          console.log('[id-photo-fe] downloadFilePath=' + downloadFilePath);
          var composeMs = Number((data.performance && data.performance.composeMs) || (Date.now() - composeStartedAt));
          var downloadStartedAt = Date.now();
          _notifyIdPhotoStage(options, 'previewing', { composeMs: composeMs });
          _downloadResult(imageUrl).then(function(localPath) {
            var downloadMs = Date.now() - downloadStartedAt;
            console.log('[id-photo-speed] composeMs=' + composeMs);
            console.log('[id-photo-speed] downloadMs=' + downloadMs);
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
            performance: Object.assign({}, data.performance || {}, { composeMs: composeMs, downloadMs: downloadMs }),
            message: data.message || '生成成功'
            });
          }).catch(function(downloadErr) {
            var localErr = new Error(downloadErr && downloadErr.message ? downloadErr.message : 'ID photo result download failed');
            localErr.code = 'ID_PHOTO_DOWNLOAD_FAILED';
            localErr.requestId = data.requestId || (data.debug && data.debug.requestId) || '';
            reject(localErr);
          });
        } else {
          reject(_makeApiError(data, '底色生成失败，请重新选择底色或重新上传照片。'));
        }
      },
      fail: function(err) {
        console.error('[id-photo-api] compose failed:', err);
        var isTimeout = err && err.errMsg && err.errMsg.indexOf('timeout') >= 0;
        var apiErr = new Error(isTimeout ? '制作时间较长，请稍后重试或重新上传。' : '生成服务暂不可用，请稍后重试。');
        apiErr.code = isTimeout ? 'ID_PHOTO_TIMEOUT' : 'SERVICE_UNAVAILABLE';
        reject(apiErr);
      }
    });
  });
}

function composeIdPhotoEdge(options) {
  options = options || {};
  return new Promise(function(resolve, reject) {
    var flags = edgeCompute.getFeatureFlags();
    var caps = edgeCompute.getCapabilities();
    if (!flags.ENABLE_EDGE_BG_COMPOSE || !caps.canvas) {
      reject(new Error('EDGE_BG_COMPOSE_UNSUPPORTED'));
      return;
    }
    if (!options.foregroundUrl) {
      reject(new Error('EDGE_FOREGROUND_URL_MISSING'));
      return;
    }
    var startedAt = Date.now();
    var endpoint = options.foregroundUrl;
    console.log('[id-photo-edge] compose route=edge');
    console.log('[id-photo-edge] foregroundUrl=' + endpoint);
    console.log('[id-photo-edge] spec=' + (options.widthPx || options.width || 0) + 'x' + (options.heightPx || options.height || 0));
    edgeCompute.composeForegroundToBackground({
      foregroundUrl: endpoint,
      foregroundPath: options.foregroundPath || '',
      bgColor: options.bgColor || '#1a73e8',
      widthPx: options.widthPx || options.width || 0,
      heightPx: options.heightPx || options.height || 0,
      outputType: 'png'
    }).then(function(tempFilePath) {
      var composeMs = Date.now() - startedAt;
      resolve({
        tempFilePath: tempFilePath,
        resultPath: tempFilePath,
        previewUrl: tempFilePath,
        finalImageUrl: '',
        downloadUrl: '',
        remoteUrl: '',
        code: 'EDGE_BG_COMPOSE',
        preparedId: options.preparedId || '',
        bgColor: options.bgColor || '',
        bgColorName: options.bgColorName || '',
        spec: options.spec || null,
        quality: options.quality || {},
        engine: 'edge_canvas',
        engineVersion: 'edge-bg-compose-v1',
        engineModel: 'canvas',
        debug: {
          route: 'edge',
          foregroundUrl: endpoint,
          canvas: caps.canvas,
          worker: caps.worker,
          wasm: caps.wasm,
          memoryClass: caps.memoryClass
        },
        requestId: options.requestId || '',
        performance: { composeMs: composeMs, downloadMs: 0, clientComposeMs: composeMs },
        message: '生成成功'
      });
    }).catch(function(err) {
      reject(err);
    });
  });
}

/**
 * AI 去水印 / Inpainting
 * @param {string} imagePath — 图片临时路径
 * @param {object} rect — { x, y, w, h } 水印区域像素坐标
 * @param {string} maskPath — 可选 mask 图片路径
 * @returns {Promise<string>} 处理后图片临时路径
 */
function inpaint(imagePath, rect, maskPath) {
  return new Promise(function (resolve, reject) {
    if (!_checkConfig()) { reject(new Error('AI 服务未配置')); return; }

    wx.showLoading({ title: 'AI去水印中...' });

    var formData = {
      x: String(rect ? Math.round(rect.x) : 0),
      y: String(rect ? Math.round(rect.y) : 0),
      width: String(rect ? Math.round(rect.w) : 100),
      height: String(rect ? Math.round(rect.h) : 100)
    };

    _safeUploadFile({
      url: config.API_BASE_URL + '/api/inpaint',
      filePath: imagePath,
      name: 'file',
      formData: formData,
      timeout: 120000,
      success: function (res) {
        wx.hideLoading();
        try {
          var data = JSON.parse(res.data);
          if (data.success && data.imageUrl) {
            _downloadResult(data.imageUrl).then(function(localPath) {
              resolve({
                tempFilePath: localPath,
                backendMode: data.backendMode || 'OpenCV inpaint',
                message: data.message || '去水印成功'
              });
            }).catch(reject);
          } else {
            reject(new Error(data.message || '去水印失败'));
          }
        } catch (e) {
          reject(new Error('后端返回异常: ' + (res.data || '').substring(0, 100)));
        }
      },
      fail: function (err) {
        wx.hideLoading();
        reject(new Error('连接后端失败，请确保 IOPaint 服务已启动: ' + (err.errMsg || '')));
      }
    });
  });
}

/**
 * 后端压缩
 * @param {string} imagePath
 * @param {number} targetKB
 * @returns {Promise<object>} { tempFilePath, actualKB, targetKB }
 */
function compressByServer(imagePath, targetKB) {
  return new Promise(function (resolve, reject) {
    if (!_checkConfig()) { reject(new Error('AI 服务未配置')); return; }

    wx.showLoading({ title: '后端压缩中...' });

    _safeUploadFile({
      url: config.API_BASE_URL + '/api/compress',
      filePath: imagePath,
      name: 'file',
      formData: { targetKB: String(targetKB) },
      timeout: 30000,
      success: function (res) {
        wx.hideLoading();
        try {
          var data = JSON.parse(res.data);
          if (data.success && data.imageUrl) {
            _downloadResult(data.imageUrl).then(function (localPath) {
              wx.getFileInfo({
                filePath: localPath,
                success: function (fi) {
                  resolve({
                    tempFilePath: localPath,
                    actualKB: Math.round(fi.size / 1024 * 10) / 10,
                    targetKB: data.targetKB || targetKB
                  });
                },
                fail: function () {
                  resolve({
                    tempFilePath: localPath,
                    actualKB: data.actualKB || 0,
                    targetKB: data.targetKB || targetKB
                  });
                }
              });
            }).catch(reject);
          } else {
            reject(new Error(data.message || '压缩失败'));
          }
        } catch (e) {
          reject(new Error('后端返回异常: ' + (res.data || '').substring(0, 100)));
        }
      },
      fail: function (err) {
        wx.hideLoading();
        reject(new Error('连接后端失败: ' + (err.errMsg || '')));
      }
    });
  });
}

// ====== 内部工具方法 ======

function _checkConfig() {
  return config.ENABLE_AI && config.API_BASE_URL;
}

function _makeApiError(data, fallbackMessage) {
  data = data || {};
  var err = new Error(data.message || fallbackMessage || '生成失败，请重新上传符合要求的照片。');
  err.code = data.code || '';
  err.requestId = data.requestId || '';
  err.quality = data.quality || null;
  err.debug = data.debug || null;
  err.sourceId = data.sourceId || (data.quality && data.quality.sourceId) || '';
  err.detailRecommended = !!data.detailRecommended;
  err.detailReasons = data.detailReasons || [];
  err.performance = data.performance || null;
  return err;
}

function _normalizeResultUrl(imageUrl) {
  if (!imageUrl) return '';
  if (imageUrl.indexOf('http') === 0) return imageUrl;
  if (imageUrl.charAt(0) !== '/') imageUrl = '/' + imageUrl;
  return config.API_BASE_URL + imageUrl;
}

function _withCacheBust(imageUrl, requestId, cacheBust) {
  if (!imageUrl) return '';
  if (imageUrl.indexOf('?v=') >= 0 || imageUrl.indexOf('&v=') >= 0) return imageUrl;
  var marker = cacheBust || requestId || Date.now();
  return imageUrl + (imageUrl.indexOf('?') >= 0 ? '&' : '?') + 'v=' + encodeURIComponent(marker);
}

/**
 * 下载后端返回的图片到本地临时路径
 * @param {string} imageUrl — 如 "/outputs/xxx.jpg"
 * @returns {Promise<string>} 本地临时路径
 */
function _downloadResult(imageUrl) {
  return new Promise(function (resolve, reject) {
    var fullUrl = imageUrl;
    if (imageUrl.indexOf('http') !== 0) {
      fullUrl = config.API_BASE_URL + imageUrl;
    }
    wx.downloadFile({
      url: fullUrl,
      timeout: 30000,
      success: function (res) {
        if (res.statusCode === 200) {
          resolve(res.tempFilePath);
        } else {
          reject(new Error('下载结果失败，状态码: ' + res.statusCode));
        }
      },
      fail: function (err) {
        reject(new Error('下载结果失败: ' + (err.errMsg || '')));
      }
    });
  });
}

/**
 * AI 证件照质检 — 调用本地 Ollama 视觉模型分析
 * @param {string} imagePath — 图片临时路径
 * @param {string} modelName — 视觉模型名称 (minicpm-v:latest | moondream:latest)
 * @returns {Promise<object>} 返回质检报告 JSON 对象
 */
function verifyPhoto(imagePath, modelName) {
  return new Promise(function (resolve, reject) {
    if (!_checkConfig()) { reject(new Error('AI 服务未配置')); return; }

    wx.showLoading({ title: 'AI 质检中...' });

    _safeUploadFile({
      url: config.API_BASE_URL + '/api/verify-photo',
      filePath: imagePath,
      name: 'file',
      formData: { model: modelName || 'minicpm-v:latest' },
      timeout: 120000,
      success: function (res) {
        wx.hideLoading();
        try {
          var data = JSON.parse(res.data);
          if (data.success) {
            resolve(data);
          } else {
            reject(new Error(data.message || '质检分析失败'));
          }
        } catch (e) {
          reject(new Error('后端返回异常: ' + (res.data || '').substring(0, 100)));
        }
      },
      fail: function (err) {
        wx.hideLoading();
        reject(new Error('连接后端失败，请确保服务已启动: ' + (err.errMsg || '')));
      }
    });
  });
}

module.exports = {
  checkApiAvailable: checkApiAvailable,
  removeBg: removeBg,
  changeBg: changeBg,
  validatePortraitInput: validatePortraitInput,
  inspectPortrait: inspectPortrait,
  getIdPhotoCapabilities: getIdPhotoCapabilities,
  prepareIdPhotoUploadSource: prepareIdPhotoUploadSource,
  prepareIdPhotoV2: prepareIdPhotoV2,
  composeIdPhotoV2: composeIdPhotoV2,
  composeIdPhotoEdge: composeIdPhotoEdge,
  createIdPhotoDetailJob: createIdPhotoDetailJob,
  getIdPhotoDetailJob: getIdPhotoDetailJob,
  cancelIdPhotoDetailJob: cancelIdPhotoDetailJob,
  generateIdPhotoV2: generateIdPhotoV2,
  inpaint: inpaint,
  compressByServer: compressByServer,
  verifyPhoto: verifyPhoto
};
