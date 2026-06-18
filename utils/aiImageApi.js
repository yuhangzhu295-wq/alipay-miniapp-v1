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

    wx.uploadFile({
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

    wx.uploadFile({
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
    wx.uploadFile({
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
    wx.uploadFile({
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
      outputType: options.outputType || 'jpg'
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
    wx.uploadFile({
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

function prepareIdPhotoV2(imagePath, options) {
  options = options || {};
  return new Promise(function(resolve, reject) {
    var endpoint = config.API_BASE_URL + '/api/id-photo/prepare';
    var formData = {
      purpose: options.purpose || 'official_id_photo',
      specId: options.specId || '',
      widthPx: options.widthPx ? String(options.widthPx) : '',
      heightPx: options.heightPx ? String(options.heightPx) : '',
      widthMm: options.widthMm ? String(options.widthMm) : '',
      heightMm: options.heightMm ? String(options.heightMm) : '',
      imageType: options.imageType || '',
      mode: options.mode || 'official',
      composition: options.composition || ''
    };
    console.log('[id-photo-api] prepare endpoint:', endpoint);
    console.log('[id-photo-fe] prepare endpoint=' + endpoint);
    console.log('[id-photo-api] prepare request:', {
      specId: formData.specId,
      widthPx: formData.widthPx,
      heightPx: formData.heightPx,
      composition: formData.composition
    });
    wx.uploadFile({
      url: endpoint,
      filePath: imagePath,
      name: 'image',
      formData: formData,
      timeout: 35000,
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
          if (data && data.success && data.preparedId) {
            resolve(data);
          } else {
            reject(_makeApiError(data, '人像预处理失败，请重新上传清晰正面照片。'));
          }
        } catch (e) {
          var err = new Error('生成服务暂不可用，请稍后重试。');
          err.code = 'SERVICE_UNAVAILABLE';
          reject(err);
        }
      },
      fail: function(err) {
        console.error('[id-photo-api] prepare upload failed:', err);
        var apiErr = new Error('生成服务暂不可用，请稍后重试。');
        apiErr.code = 'SERVICE_UNAVAILABLE';
        reject(apiErr);
      }
    });
  });
}

function composeIdPhotoV2(options) {
  options = options || {};
  return new Promise(function(resolve, reject) {
    var endpoint = config.API_BASE_URL + '/api/id-photo/compose';
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
      timeout: 25000,
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

    wx.uploadFile({
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

    wx.uploadFile({
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

    wx.uploadFile({
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
  prepareIdPhotoV2: prepareIdPhotoV2,
  composeIdPhotoV2: composeIdPhotoV2,
  generateIdPhotoV2: generateIdPhotoV2,
  inpaint: inpaint,
  compressByServer: compressByServer,
  verifyPhoto: verifyPhoto
};
