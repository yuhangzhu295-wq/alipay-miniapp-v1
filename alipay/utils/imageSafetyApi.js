var wx = require('./platform/alipayWxCompat.js');
/**
 * Shared client-side coordinator for the server-owned image-safety Gate.
 * It never decides that an image is safe locally: only a backend PASS result is
 * converted into a securityCheckId that image-processing uploads can carry.
 */
var apiConfig = require('./apiConfig.js');
var authService = require('./authService.js');

var POLL_INTERVAL_MS = 800;
var CLIENT_WAIT_TIMEOUT_MS = 30000;
var PASS_CACHE_TTL_MS = 25 * 60 * 1000;
var safetyCache = {};
var inFlight = {};

var REJECTED_MESSAGE = '图片内容不符合平台规范，请更换图片后重试。';
var UNAVAILABLE_MESSAGE = '图片安全检测暂时不可用，请稍后重试。';
var PENDING_MESSAGE = '图片安全检测暂未完成，请稍后重试。';

function getApiBaseUrl() {
  return apiConfig.getApiBaseUrl ? apiConfig.getApiBaseUrl() : apiConfig.API_BASE_URL;
}

function _makeSafetyError(code, message, status) {
  var error = new Error(message || UNAVAILABLE_MESSAGE);
  error.code = code || 'CONTENT_SAFETY_UNAVAILABLE';
  error.status = status || 'ERROR';
  error.isContentSafetyError = true;
  return error;
}

function _diagnosticError(error) {
  return {
    code: error && error.code || 'CONTENT_SAFETY_UNAVAILABLE',
    status: error && error.status || 'ERROR',
    errMsg: error && (error.errMsg || error.message) || UNAVAILABLE_MESSAGE
  };
}

function _parseUploadResponse(res) {
  if (!res) return {};
  if (typeof res.data === 'object' && res.data) return res.data;
  try { return JSON.parse(res.data || '{}'); }
  catch (err) { return {}; }
}

function _getFileSize(path) {
  return new Promise(function(resolve) {
    try {
      wx.getFileInfo({
        filePath: path,
        success: function(res) { resolve(Number((res && res.size) || 0)); },
        fail: function() { resolve(0); }
      });
    } catch (err) {
      resolve(0);
    }
  });
}

function _ensureSafetyIdentity() {
  var auth = authService.getAuth();
  if (auth && auth.identityBound === true) return Promise.resolve(auth);
  return authService.loginWithProfile(authService.getUserInfo() || {}).then(function(nextAuth) {
    if (nextAuth && nextAuth.identityBound === true) return nextAuth;
    throw _makeSafetyError('CONTENT_SAFETY_PLATFORM_IDENTITY_REQUIRED', UNAVAILABLE_MESSAGE, 'ERROR');
  }).catch(function(err) {
    if (err && err.isContentSafetyError) throw err;
    throw _makeSafetyError('CONTENT_SAFETY_AUTH_REQUIRED', UNAVAILABLE_MESSAGE, 'ERROR');
  });
}

function _cacheKey(imagePath, auth, imageBytes) {
  return [auth && auth.userId || '', imagePath || '', Number(imageBytes || 0)].join('|');
}

function _toSafetyResult(data) {
  var status = String((data && data.status) || '').toUpperCase();
  if (status === 'PASS' && data && data.securityCheckId) {
    return {
      securityCheckId: data.securityCheckId,
      safeAssetId: data.safeAssetId || data.securityCheckId,
      status: 'PASS'
    };
  }
  if (status === 'REJECT') {
    throw _makeSafetyError('CONTENT_SAFETY_REJECTED', REJECTED_MESSAGE, status);
  }
  if (status === 'PENDING') return null;
  throw _makeSafetyError((data && data.code) || 'CONTENT_SAFETY_UNAVAILABLE', UNAVAILABLE_MESSAGE, status || 'ERROR');
}

function _pollSecurityCheck(securityCheckId, auth, deadline) {
  return new Promise(function(resolve, reject) {
    var poll = function() {
      if (Date.now() >= deadline) {
        reject(_makeSafetyError('CONTENT_SAFETY_PENDING', PENDING_MESSAGE, 'PENDING'));
        return;
      }
      wx.request({
        url: getApiBaseUrl() + '/api/content-security/images/' + encodeURIComponent(securityCheckId),
        method: 'GET',
        header: authService.getAuthHeader(),
        timeout: 10000,
        success: function(res) {
          var data = res && res.data || {};
          try {
            var passed = _toSafetyResult(data);
            if (passed) {
              resolve(passed);
              return;
            }
          } catch (err) {
            reject(err);
            return;
          }
          setTimeout(poll, POLL_INTERVAL_MS);
        },
        fail: function() {
          reject(_makeSafetyError('CONTENT_SAFETY_UNAVAILABLE', UNAVAILABLE_MESSAGE, 'ERROR'));
        }
      });
    };
    poll();
  });
}

function _submitSecurityCheck(imagePath, purpose, auth) {
  return new Promise(function(resolve, reject) {
    wx.uploadFile({
      url: getApiBaseUrl() + '/api/content-security/images',
      filePath: imagePath,
      name: 'image',
      header: authService.getAuthHeader(),
      formData: { purpose: purpose || 'image_processing' },
      timeout: 45000,
      success: function(res) {
        var data = _parseUploadResponse(res);
        try {
          var passed = _toSafetyResult(data);
          if (passed) {
            resolve(passed);
            return;
          }
          if (!data || !data.securityCheckId) {
            reject(_makeSafetyError('CONTENT_SAFETY_UNAVAILABLE', UNAVAILABLE_MESSAGE, 'ERROR'));
            return;
          }
          _pollSecurityCheck(data.securityCheckId, auth, Date.now() + CLIENT_WAIT_TIMEOUT_MS).then(resolve).catch(reject);
        } catch (err) {
          reject(err);
        }
      },
      fail: function() {
        reject(_makeSafetyError('CONTENT_SAFETY_UNAVAILABLE', UNAVAILABLE_MESSAGE, 'ERROR'));
      }
    });
  });
}

function ensureImageSafety(imagePath, purpose) {
  if (!imagePath) return Promise.reject(_makeSafetyError('CONTENT_SAFETY_EMPTY_IMAGE', UNAVAILABLE_MESSAGE, 'ERROR'));
  return _ensureSafetyIdentity().then(function(auth) {
    return _getFileSize(imagePath).then(function(imageBytes) {
      var key = _cacheKey(imagePath, auth, imageBytes);
      var cached = safetyCache[key];
      if (cached && cached.status === 'PASS' && cached.expiresAt > Date.now()) {
        return cached.result;
      }
      if (inFlight[key]) return inFlight[key];
      var started = _submitSecurityCheck(imagePath, purpose, auth).then(function(result) {
        safetyCache[key] = {
          status: 'PASS',
          result: result,
          expiresAt: Date.now() + PASS_CACHE_TTL_MS
        };
        delete inFlight[key];
        return result;
      }, function(err) {
        delete inFlight[key];
        throw err;
      });
      inFlight[key] = started;
      return started;
    });
  });
}

/**
 * Shared upload gate. The wrapped business success/fail callbacks are invoked
 * only after a backend PASS has supplied a securityCheckId. A failed gate is
 * surfaced through the original success callback as an HTTP-shaped response
 * so existing business error handling remains unchanged.
 */
function uploadWithSafety(options, purpose) {
  options = options || {};
  var listeners = [];
  var nativeTask = null;
  var originalSuccess = options.success;
  var originalFail = options.fail;
  var failSafety = function(error) {
    var status = error && error.status === 'REJECT' ? 403 : 503;
    var payload = {
      success: false,
      code: error && error.code || 'CONTENT_SAFETY_UNAVAILABLE',
      status: error && error.status || 'ERROR',
      message: error && error.message || UNAVAILABLE_MESSAGE
    };
    console.error('[content-safety-mobile] upload blocked', _diagnosticError(error));
    if (typeof originalSuccess === 'function') {
      originalSuccess({ statusCode: status, data: JSON.stringify(payload) });
    } else if (typeof originalFail === 'function') {
      originalFail({ errMsg: payload.message, contentSafetyError: error || payload });
    }
  };

  ensureImageSafety(options.filePath, purpose || 'image_processing').then(function(safety) {
    var nextOptions = Object.assign({}, options);
    nextOptions.formData = attachSafetyToFormData(options.formData, safety);
    nextOptions.header = Object.assign({}, authService.getAuthHeader(), options.header || {});
    nativeTask = wx.uploadFile(nextOptions);
    if (nativeTask && nativeTask.onProgressUpdate) {
      listeners.forEach(function(listener) { nativeTask.onProgressUpdate(listener); });
    }
  }).catch(failSafety);

  return {
    onProgressUpdate: function(listener) {
      if (typeof listener !== 'function') return;
      if (nativeTask && nativeTask.onProgressUpdate) nativeTask.onProgressUpdate(listener);
      else listeners.push(listener);
    }
  };
}

function attachSafetyToFormData(formData, safety) {
  var next = Object.assign({}, formData || {});
  next.securityCheckId = safety && safety.securityCheckId || '';
  return next;
}

function clearImageSafetyCache(imagePath) {
  Object.keys(safetyCache).forEach(function(key) {
    if (key.indexOf('|' + imagePath + '|') >= 0) delete safetyCache[key];
  });
}

module.exports = {
  REJECTED_MESSAGE: REJECTED_MESSAGE,
  UNAVAILABLE_MESSAGE: UNAVAILABLE_MESSAGE,
  PENDING_MESSAGE: PENDING_MESSAGE,
  ensureImageSafety: ensureImageSafety,
  uploadWithSafety: uploadWithSafety,
  attachSafetyToFormData: attachSafetyToFormData,
  clearImageSafetyCache: clearImageSafetyCache
};
