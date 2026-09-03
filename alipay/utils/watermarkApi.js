var wx = require('./platform/alipayWxCompat.js');
/** Watermark API using compact normalized brush-stroke transport.
 * Mapped endpoints: /api/watermark/manual-remove, /api/watermark/quick-remove, /api/watermark/hd-remove -> /api/watermark/remove-v2
 */
var watermarkConfig = require('./watermarkConfig.js');
var imageSafetyApi = require('./imageSafetyApi.js');
var activeHdRequests = {};

function getBaseUrl() {
  return watermarkConfig.getWatermarkApiBaseUrl();
}

function joinApiUrl(baseUrl, path) {
  var cleanBase = String(baseUrl || '').replace(/\/+$/, '');
  var cleanPath = String(path || '').replace(/^\/+/, '');
  return cleanBase + '/' + cleanPath;
}

function isHdRepairEnabled() {
  return watermarkConfig.isHdRepairEnabled ? watermarkConfig.isHdRepairEnabled() : false;
}

function _formatNetworkError(err) {
  var msg = (err && (err.errMsg || err.message)) || String(err || '');
  console.error('[watermark] request failed:', err);
  console.error('[watermark] API base URL:', getBaseUrl());
  if (msg.toLowerCase().indexOf('timeout') >= 0 || msg.indexOf('timed out') >= 0) {
    return '图片处理超时，请稍后重试或缩小涂抹区域。';
  }
  if (msg.toLowerCase().indexOf('domain') >= 0 || msg.indexOf('合法域名') >= 0) {
    return '当前请求域名未配置，请检查小程序服务器域名。';
  }
  return '图片处理服务连接失败，请稍后重试。';
}

function _makeApiError(data, fallbackMessage) {
  data = data || {};
  var detail = typeof data.detail === 'string' ? data.detail : '';
  var err = new Error(data.message || detail || fallbackMessage || '图片处理失败');
  err.debug = data.debug || null;
  err.fallbackAvailable = !!data.fallbackAvailable;
  return err;
}

function checkHealth() {
  return new Promise(function(resolve, reject) {
    if (!getBaseUrl()) { reject(new Error('图片处理服务地址未配置')); return; }
    wx.request({
      url: joinApiUrl(getBaseUrl(), '/api/watermark/health'),
      method: 'GET',
      timeout: 10000,
      success: function(res) {
        if (res.statusCode === 200 && res.data && (res.data.success || res.data.ok)) resolve(res.data);
        else reject(new Error('图片处理服务健康检查失败'));
      },
      fail: function(err) { reject(new Error(_formatNetworkError(err))); }
    });
  });
}

function _downloadResult(imageUrl) {
  return new Promise(function(resolve, reject) {
    var fullUrl = imageUrl.indexOf('http') === 0 ? imageUrl : joinApiUrl(getBaseUrl(), imageUrl);
    var downloadUrl = fullUrl + (fullUrl.indexOf('?') >= 0 ? '&' : '?') + 't=' + Date.now();
    wx.downloadFile({
      url: downloadUrl,
      timeout: 120000,
      success: function(res) {
        if (res.statusCode === 200) resolve(res.tempFilePath);
        else reject(new Error('下载结果失败，状态码: ' + res.statusCode));
      },
      fail: function(err) { reject(new Error(_formatNetworkError(err))); }
    });
  });
}

function _utf8Bytes(value) {
  try { return unescape(encodeURIComponent(String(value || ''))).length; }
  catch (err) { return String(value || '').length; }
}

function _imageFileBytes(path) {
  try {
    var stat = wx.getFileSystemManager().statSync(path);
    return Number((stat && stat.size) || 0);
  } catch (err) {
    return 0;
  }
}

function _newHdRequestId() {
  return 'wmhd-' + Date.now() + '-' + Math.random().toString(16).slice(2, 10);
}

function _statusLabel(stage) {
  var labels = {
    uploading: '正在上传图片',
    received: '正在分析涂抹区域',
    analyzing: '正在分析涂抹区域',
    repairing: '正在进行高清修复',
    compositing: '正在合成处理结果',
    encoding: '正在合成处理结果',
    preview: '正在加载预览'
  };
  return labels[stage] || labels.repairing;
}

function _emitHdStatus(params, state, stage) {
  state.stage = stage || state.stage || 'uploading';
  var elapsedSeconds = Math.max(0, Math.floor((Date.now() - state.startedAt) / 1000));
  var status = {
    stage: state.stage,
    label: _statusLabel(state.stage),
    elapsedSeconds: elapsedSeconds,
    text: _statusLabel(state.stage) + '，已等待' + elapsedSeconds + '秒'
  };
  if (typeof params.onStatus === 'function') params.onStatus(status);
  return status;
}

function _startHdProgress(params, requestId, state) {
  var stopped = false;
  var elapsedTimer = setInterval(function() {
    if (!stopped) _emitHdStatus(params, state, state.stage);
  }, 1000);
  var pollTimer = setInterval(function() {
    if (stopped) return;
    wx.request({
      url: joinApiUrl(getBaseUrl(), '/api/watermark/hd-progress/' + requestId),
      method: 'GET',
      timeout: 5000,
      success: function(res) {
        if (res.statusCode === 200 && res.data && res.data.stage && res.data.stage !== 'done') {
          _emitHdStatus(params, state, res.data.stage);
        }
      }
    });
  }, 900);
  return function() {
    stopped = true;
    clearInterval(elapsedTimer);
    clearInterval(pollTimer);
  };
}

function removeV2(params) {
  return new Promise(function(resolve, reject) {
    var clientStartedAt = Date.now();
    params = params || {};
    var strokeInfo = params.strokeInfo || {};
    var payload = strokeInfo.payload || {};
    var quality = params.quality === 'hd' ? 'hd' : (params.quality === 'manual' ? 'manual' : 'quick');
    if (!getBaseUrl()) { reject(new Error('图片处理服务地址未配置')); return; }
    if (!params.imagePath || !strokeInfo.strokesJson || !payload.originalWidth || !payload.originalHeight) {
      reject(new Error('原图或笔迹数据不完整，请重新涂抹。'));
      return;
    }
    if (quality === 'hd' && !isHdRepairEnabled()) {
      reject(new Error('高清修复服务暂不可用，请使用快速模式。'));
      return;
    }

    var requestId = quality === 'hd' ? _newHdRequestId() : '';
    var activeKey = params.imagePath + '|' + strokeInfo.strokesJson;
    if (quality === 'hd' && activeHdRequests[activeKey]) {
      reject(new Error('高清修复正在处理中，请勿重复提交。'));
      return;
    }
    if (quality === 'hd') activeHdRequests[activeKey] = requestId;
    var statusState = { startedAt: clientStartedAt, stage: 'uploading' };
    var stopProgress = function() {};
    var imageBytes = _imageFileBytes(params.imagePath);
    var clientImagePrepareMs = Date.now() - clientStartedAt;
    var uploadStartedAt = 0;
    var uploadCompletedAt = 0;

    function cleanupHdProgress() {
      stopProgress();
      if (quality === 'hd') delete activeHdRequests[activeKey];
    }

    wx.showLoading({ title: quality === 'hd' ? '高清修复中...' : '去水印中...' });
    if (quality === 'hd') {
      _emitHdStatus(params, statusState, 'uploading');
      stopProgress = _startHdProgress(params, requestId, statusState);
    }
    checkHealth().then(function(health) {
      if (quality === 'hd' && (!health.hdAvailable || health.hdRealModelLoaded !== true || health.fallbackUsed === true)) {
        var unavailable = new Error('高清修复模型未就绪，请使用快速模式或稍后重试。');
        unavailable.fallbackAvailable = true;
        throw unavailable;
      }
      uploadStartedAt = Date.now();
      var formData = {
        strokesJson: strokeInfo.strokesJson,
        originalWidth: String(payload.originalWidth),
        originalHeight: String(payload.originalHeight),
        displayWidth: String(payload.displayWidth),
        displayHeight: String(payload.displayHeight),
        quality: quality,
        strength: String(params.strength || 'medium'),
        preserveDetail: params.preserveDetail === false ? 'false' : 'true',
        smartExpand: params.smartExpand === true ? 'true' : 'false',
        maskDilationPx: String(Math.max(3, Math.min(12, Number(params.maskDilationPx || 5)))),
        requestId: requestId,
        edgeRoiMode: params.edgeRoiMode === true ? 'true' : 'false',
        roiX: String(params.roiX || 0),
        roiY: String(params.roiY || 0),
        roiWidth: String(params.roiWidth || payload.originalWidth || 0),
        roiHeight: String(params.roiHeight || payload.originalHeight || 0),
        sourceOriginalWidth: String(params.sourceOriginalWidth || payload.originalWidth || 0),
        sourceOriginalHeight: String(params.sourceOriginalHeight || payload.originalHeight || 0)
      };

      var startBusinessUpload = function() {
        var uploadTask = imageSafetyApi.uploadWithSafety({
        url: joinApiUrl(getBaseUrl(), '/api/watermark/remove-v2'),
        filePath: params.imagePath,
        name: 'image',
        formData: formData,
        timeout: quality === 'hd' ? 360000 : 180000,
        success: function(res) {
          wx.hideLoading();
          if (!uploadCompletedAt) uploadCompletedAt = Date.now();
          try {
            var data = JSON.parse(res.data || '{}');
            var resultUrl = data.resultUrl || data.imageUrl;
            if (res.statusCode < 200 || res.statusCode >= 300 || !data.success || !resultUrl) {
              cleanupHdProgress();
              reject(_makeApiError(data, '去水印处理失败'));
              return;
            }
            if (quality === 'hd' && (data.fallbackUsed === true || data.engine !== 'lama')) {
              cleanupHdProgress();
              reject(_makeApiError(data, '高清模式未使用真实 LaMa 模型'));
              return;
            }
            var responseAt = Date.now();
            if (quality === 'hd') _emitHdStatus(params, statusState, 'preview');
            var previewStartedAt = Date.now();
            _downloadResult(resultUrl).then(function(localPath) {
              var previewLoadMs = Date.now() - previewStartedAt;
              var clientPerformance = {
                requestId: requestId,
                imageWidth: Number(payload.originalWidth || 0),
                imageHeight: Number(payload.originalHeight || 0),
                imageBytes: imageBytes,
                strokeCount: (payload.strokes || []).length,
                maskBytes: Number(strokeInfo.transportBytes || _utf8Bytes(strokeInfo.strokesJson)),
                clientImagePrepareMs: clientImagePrepareMs,
                maskSerializeMs: Number(strokeInfo.serializeMs || 0),
                uploadMs: Math.max(0, uploadCompletedAt - uploadStartedAt),
                waitResponseMs: Math.max(0, responseAt - uploadCompletedAt),
                previewLoadMs: previewLoadMs,
                totalClientMs: Date.now() - clientStartedAt
              };
              cleanupHdProgress();
              console.log('[watermark-hd-client]', clientPerformance);
              resolve({
                tempFilePath: localPath,
                resultUrl: resultUrl,
                previewUrl: resultUrl + (resultUrl.indexOf('?') >= 0 ? '&' : '?') + 't=' + Date.now(),
                outputPath: data.outputPath || '',
                fileHash: data.fileHash || '',
                mode: data.mode || quality,
                engine: data.engine || '',
                fallbackUsed: data.fallbackUsed === true,
                backendMode: data.backendMode || '',
                message: data.message || '处理成功',
                debug: data.debug || null,
                clientPerformance: clientPerformance
              });
            }).catch(function(err) {
              cleanupHdProgress();
              reject(err);
            });
          } catch (err) {
            cleanupHdProgress();
            reject(err instanceof Error ? err : new Error('后端返回异常'));
          }
        },
        fail: function(err) {
          wx.hideLoading();
          cleanupHdProgress();
          reject(new Error(_formatNetworkError(err)));
        }
      }, 'watermark_removal');
      if (quality === 'hd' && uploadTask && uploadTask.onProgressUpdate) {
        uploadTask.onProgressUpdate(function(progress) {
          if (progress && Number(progress.progress) >= 100 && !uploadCompletedAt) {
            uploadCompletedAt = Date.now();
            _emitHdStatus(params, statusState, 'analyzing');
          }
        });
      }
      };
      if (params.sourceImagePath && params.sourceImagePath !== params.imagePath) {
        imageSafetyApi.ensureImageSafety(params.sourceImagePath, 'watermark_removal').then(function(sourceSafety) {
          formData.sourceSecurityCheckId = sourceSafety && sourceSafety.securityCheckId || '';
          startBusinessUpload();
        }).catch(function(err) {
          wx.hideLoading();
          cleanupHdProgress();
          reject(err);
        });
      } else {
        startBusinessUpload();
      }
    }).catch(function(err) {
      wx.hideLoading();
      cleanupHdProgress();
      reject(err);
    });
  });
}

function manualRemove(params) { params.quality = 'manual'; return removeV2(params); }
function quickRemove(params) { params.quality = 'quick'; return removeV2(params); }
function hdRemove(params) { params.quality = 'hd'; return removeV2(params); }

module.exports = {
  getBaseUrl: getBaseUrl,
  checkHealth: checkHealth,
  isHdRepairEnabled: isHdRepairEnabled,
  formatNetworkError: _formatNetworkError,
  removeV2: removeV2,
  manualRemove: manualRemove,
  quickRemove: quickRemove,
  hdRemove: hdRemove
};
