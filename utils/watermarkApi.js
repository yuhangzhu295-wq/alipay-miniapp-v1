/** Watermark API using compact normalized brush-stroke transport. */
var watermarkConfig = require('./watermarkConfig.js');

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

function removeV2(params) {
  return new Promise(function(resolve, reject) {
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

    wx.showLoading({ title: quality === 'hd' ? '高清修复中...' : '去水印中...' });
    checkHealth().then(function(health) {
      if (quality === 'hd' && (!health.hdAvailable || health.hdRealModelLoaded !== true || health.fallbackUsed === true)) {
        var unavailable = new Error('高清修复模型未就绪，请使用快速模式或稍后重试。');
        unavailable.fallbackAvailable = true;
        throw unavailable;
      }
      wx.uploadFile({
        url: joinApiUrl(getBaseUrl(), '/api/watermark/remove-v2'),
        filePath: params.imagePath,
        name: 'image',
        formData: {
          strokesJson: strokeInfo.strokesJson,
          originalWidth: String(payload.originalWidth),
          originalHeight: String(payload.originalHeight),
          displayWidth: String(payload.displayWidth),
          displayHeight: String(payload.displayHeight),
          quality: quality,
          strength: String(params.strength || 'medium'),
          preserveDetail: params.preserveDetail === false ? 'false' : 'true'
        },
        timeout: quality === 'hd' ? 360000 : 180000,
        success: function(res) {
          wx.hideLoading();
          try {
            var data = JSON.parse(res.data || '{}');
            var resultUrl = data.resultUrl || data.imageUrl;
            if (res.statusCode < 200 || res.statusCode >= 300 || !data.success || !resultUrl) {
              reject(_makeApiError(data, '去水印处理失败'));
              return;
            }
            if (quality === 'hd' && (data.fallbackUsed === true || data.engine !== 'lama')) {
              reject(_makeApiError(data, '高清模式未使用真实 LaMa 模型'));
              return;
            }
            _downloadResult(resultUrl).then(function(localPath) {
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
                debug: data.debug || null
              });
            }).catch(reject);
          } catch (err) {
            reject(err instanceof Error ? err : new Error('后端返回异常'));
          }
        },
        fail: function(err) {
          wx.hideLoading();
          reject(new Error(_formatNetworkError(err)));
        }
      });
    }).catch(function(err) {
      wx.hideLoading();
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
