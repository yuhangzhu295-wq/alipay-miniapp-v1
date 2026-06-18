/**
 * 新版图片去水印 API
 */
var watermarkConfig = require('./watermarkConfig.js');

function getBaseUrl() {
  return watermarkConfig.getWatermarkApiBaseUrl();
}

function _checkConfig() {
  return !!getBaseUrl();
}

function isHdRepairEnabled() {
  return watermarkConfig.isHdRepairEnabled ? watermarkConfig.isHdRepairEnabled() : false;
}

function _formatNetworkError(err) {
  var msg = (err && (err.errMsg || err.message)) || String(err || '');
  console.error('[watermark] upload failed:', err);
  console.error('[watermark] API base URL:', getBaseUrl());

  if (msg.indexOf('ECONNREFUSED') >= 0 || msg.indexOf('connection refused') >= 0) {
    return '图片处理服务未启动或端口不可访问，请启动 8000 端口后端服务。';
  }
  if (msg.toLowerCase().indexOf('timeout') >= 0 || msg.indexOf('timed out') >= 0) {
    return '图片处理服务响应超时，请检查后端是否卡住。';
  }
  if (msg.toLowerCase().indexOf('domain') >= 0 || msg.indexOf('合法域名') >= 0) {
    return '当前请求域名未配置，请检查小程序开发工具本地设置或服务器域名。';
  }
  return '图片处理服务连接失败，请检查本地 OpenCV 服务是否启动。';
}

function _makeApiError(data, fallbackMessage) {
  data = data || {};
  var detailMessage = '';
  if (data.detail) {
    if (typeof data.detail === 'string') {
      detailMessage = data.detail;
    } else {
      try {
        detailMessage = JSON.stringify(data.detail);
      } catch (jsonErr) {
        detailMessage = String(data.detail);
      }
    }
  }
  var apiErr = new Error(data.message || detailMessage || fallbackMessage || '图片处理失败');
  apiErr.debug = data.debug || null;
  apiErr.fallbackAvailable = !!data.fallbackAvailable;
  return apiErr;
}

function checkHealth() {
  return new Promise(function(resolve, reject) {
    if (!_checkConfig()) {
      reject(new Error('图片处理服务地址未配置'));
      return;
    }

    wx.request({
      url: getBaseUrl() + '/api/watermark/health',
      method: 'GET',
      timeout: 5000,
      success: function(res) {
        if (res.statusCode === 200 && res.data && (res.data.success || res.data.ok)) {
          resolve(res.data);
        } else {
          reject(new Error('图片处理服务健康检查失败'));
        }
      },
      fail: function(err) {
        reject(new Error(_formatNetworkError(err)));
      }
    });
  });
}

function _downloadResult(imageUrl) {
  return new Promise(function (resolve, reject) {
    var fullUrl = imageUrl;
    if (imageUrl.indexOf('http') !== 0) {
      fullUrl = getBaseUrl() + imageUrl;
    }
    var downloadUrl = fullUrl + (fullUrl.indexOf('?') >= 0 ? '&' : '?') + 't=' + Date.now();
    wx.downloadFile({
      url: downloadUrl,
      timeout: 30000,
      success: function (res) {
        if (res.statusCode === 200) {
          resolve(res.tempFilePath);
        } else {
          reject(new Error('下载结果失败，状态码: ' + res.statusCode));
        }
      },
      fail: function (err) {
        reject(new Error(_formatNetworkError(err)));
      }
    });
  });
}

/**
 * 手动擦除去水印
 * @param {object} params
 * @param {string} params.imagePath
 * @param {string} params.maskBase64
 * @param {number} params.strength
 */
function manualRemove(params) {
  return new Promise(function (resolve, reject) {
    if (!_checkConfig()) { reject(new Error('图片处理服务地址未配置')); return; }

    wx.showLoading({ title: '去水印中...' });

    var formData = {
      maskBase64: params.maskBase64,
      mode: 'manual',
      quality: 'manual',
      engine: 'opencv_manual',
      strength: String(params.strength || 5)
    };

    checkHealth().then(function() {
      wx.uploadFile({
        url: getBaseUrl() + '/api/watermark/manual-remove',
        filePath: params.imagePath,
        name: 'image',
        formData: formData,
        timeout: 120000,
        success: function (res) {
          wx.hideLoading();
          try {
            var data = JSON.parse(res.data);
            var resultUrl = data.resultUrl || data.imageUrl;
            if (data.success && resultUrl) {
              _downloadResult(resultUrl).then(function(localPath) {
                resolve({
                  tempFilePath: localPath,
                  resultUrl: resultUrl,
                  previewUrl: resultUrl + (resultUrl.indexOf('?') >= 0 ? '&' : '?') + 't=' + Date.now(),
                  outputPath: data.outputPath || '',
                  fileHash: data.fileHash || '',
                  mode: data.mode || 'manual',
                  engine: data.engine || 'opencv_manual',
                  fallbackUsed: data.fallbackUsed === true,
                  backendMode: data.backendMode || 'OpenCV inpaint',
                  message: data.message || '去水印成功',
                  debug: data.debug || null
                });
              }).catch(reject);
            } else {
              reject(_makeApiError(data, '去水印失败'));
            }
          } catch (e) {
            reject(new Error('后端返回异常: ' + (res.data || '').substring(0, 100)));
          }
        },
        fail: function (err) {
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

function quickRemove(params) {
  return new Promise(function (resolve, reject) {
    if (!_checkConfig()) { reject(new Error('图片处理服务地址未配置')); return; }

    wx.showLoading({ title: '快速去水印中...' });

    var formData = {
      maskBase64: params.maskBase64,
      mode: 'quick',
      quality: 'quick',
      engine: 'opencv_quick',
      strength: String(params.strength || 'medium')
    };

    checkHealth().then(function() {
      wx.uploadFile({
        url: getBaseUrl() + '/api/watermark/quick-remove',
        filePath: params.imagePath,
        name: 'image',
        formData: formData,
        timeout: 120000,
        success: function (res) {
          wx.hideLoading();
          try {
            var data = JSON.parse(res.data);
            var resultUrl = data.resultUrl || data.imageUrl;
            if (data.success && resultUrl) {
              _downloadResult(resultUrl).then(function(localPath) {
                resolve({
                  tempFilePath: localPath,
                  resultUrl: resultUrl,
                  previewUrl: resultUrl + (resultUrl.indexOf('?') >= 0 ? '&' : '?') + 't=' + Date.now(),
                  outputPath: data.outputPath || '',
                  fileHash: data.fileHash || '',
                  mode: data.mode || 'quick',
                  engine: data.engine || 'opencv_quick',
                  fallbackUsed: data.fallbackUsed === true,
                  backendMode: data.backendMode || 'OpenCV quick inpaint',
                  message: data.message || '快速去水印成功',
                  debug: data.debug || null
                });
              }).catch(reject);
            } else {
              reject(_makeApiError(data, '快速去水印失败'));
            }
          } catch (e) {
            reject(new Error('后端返回异常: ' + (res.data || '').substring(0, 100)));
          }
        },
        fail: function (err) {
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

/**
 * 高清修复去水印
 * @param {object} params
 * @param {string} params.imagePath
 * @param {string} params.maskBase64
 * @param {string} params.strength
 * @param {boolean} params.preserveDetail
 */
function hdRemove(params) {
  return new Promise(function (resolve, reject) {
    if (!_checkConfig()) { reject(new Error('图片处理服务地址未配置')); return; }
    if (!isHdRepairEnabled()) { reject(new Error('高清修复服务暂不可用，请使用快速模式或稍后重试')); return; }

    wx.showLoading({ title: '高清修复中...' });

    var formData = {
      maskBase64: params.maskBase64,
      mode: 'hd',
      quality: 'hd',
      engine: 'hd',
      strength: String(params.strength || 'medium'),
      preserveDetail: params.preserveDetail === false ? 'false' : 'true'
    };

    checkHealth().then(function(health) {
      if (!health.hdAvailable || health.hdRealModelLoaded !== true || health.fallbackUsed === true) {
        wx.hideLoading();
        var unavailableErr = new Error('高清修复模型未就绪，请启动本地 IOPaint/LaMa 服务后重试。当前可先使用快速模式。');
        unavailableErr.fallbackAvailable = true;
        reject(unavailableErr);
        return;
      }

      wx.uploadFile({
        url: getBaseUrl() + '/api/watermark/hd-remove',
        filePath: params.imagePath,
        name: 'image',
        formData: formData,
        timeout: 300000,
        success: function (res) {
          wx.hideLoading();
          try {
            var data = JSON.parse(res.data);
            var resultUrl = data.resultUrl || data.imageUrl;
            if (data.success && resultUrl && data.fallbackUsed !== true) {
              _downloadResult(resultUrl).then(function(localPath) {
                resolve({
                  tempFilePath: localPath,
                  resultUrl: resultUrl,
                  previewUrl: resultUrl + (resultUrl.indexOf('?') >= 0 ? '&' : '?') + 't=' + Date.now(),
                  outputPath: data.outputPath || '',
                  fileHash: data.fileHash || '',
                  mode: data.mode || 'hd',
                  engine: data.engine || (data.debug && data.debug.engine) || 'opencv_hd_fallback',
                  fallbackUsed: data.fallbackUsed === true,
                  backendMode: data.backendMode || 'LaMa/IOPaint 高清修复',
                  message: data.message || '高清修复完成',
                  debug: data.debug || null
                });
              }).catch(reject);
            } else {
              reject(_makeApiError(data, '高清修复模型未就绪，请启动本地 IOPaint/LaMa 服务后重试。当前可先使用快速模式。'));
            }
          } catch (e) {
            reject(new Error('后端返回异常: ' + (res.data || '').substring(0, 100)));
          }
        },
        fail: function (err) {
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

module.exports = {
  getBaseUrl: getBaseUrl,
  checkHealth: checkHealth,
  isHdRepairEnabled: isHdRepairEnabled,
  formatNetworkError: _formatNetworkError,
  manualRemove: manualRemove,
  quickRemove: quickRemove,
  hdRemove: hdRemove
};
