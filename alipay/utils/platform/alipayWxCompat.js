var platform = require('./alipay.js');

function normalizeToastOptions(options) {
  options = options || {};
  return Object.assign({}, options, {
    content: options.content || options.title || '',
    type: options.type || (options.icon === 'success' ? 'success' : 'none')
  });
}

function request(options) {
  options = options || {};
  var next = Object.assign({}, options, {
    headers: options.header || options.headers || {},
    method: options.method || 'GET'
  });
  return platform.callMy('request', next);
}

function uploadFile(options) {
  options = options || {};
  var next = Object.assign({}, options, {
    fileName: options.fileName || options.name || 'file',
    fileType: options.fileType || 'image',
    headers: options.header || options.headers || {}
  });
  return platform.callMy('uploadFile', next);
}

function downloadFile(options) {
  options = options || {};
  var success = options.success;
  var next = Object.assign({}, options, {
    success: function(res) {
      if (res && res.apFilePath && !res.tempFilePath) res.tempFilePath = res.apFilePath;
      if (typeof success === 'function') success(res);
    }
  });
  return platform.callMy('downloadFile', next);
}

function chooseMedia(options) {
  options = options || {};
  return platform.callMy('chooseImage', {
    count: options.count || 1,
    sourceType: options.sourceType || ['album', 'camera'],
    success: function(res) {
      var paths = res.apFilePaths || res.tempFilePaths || [];
      var files = paths.map(function(p) { return { tempFilePath: p, path: p, size: 0 }; });
      if (typeof options.success === 'function') {
        options.success({ tempFiles: files, type: 'image' });
      }
    },
    fail: options.fail,
    complete: options.complete
  });
}

function login(options) {
  options = options || {};
  return platform.callMy('getAuthCode', {
    scopes: 'auth_base',
    success: function(res) {
      var code = (res && (res.authCode || res.auth_code)) || '';
      if (typeof options.success === 'function') options.success({ code: code, authCode: code, platform: 'alipay' });
    },
    fail: options.fail,
    complete: options.complete
  });
}

function setNavigationBarTitle(options) {
  options = options || {};
  return platform.callMy('setNavigationBar', { title: options.title || '', success: options.success, fail: options.fail, complete: options.complete });
}

function getAccountInfoSync() {
  if (platform.hasMy() && typeof my.getAccountInfoSync === 'function') return my.getAccountInfoSync();
  return { miniProgram: { appId: '', envVersion: 'develop' } };
}

module.exports = {
  request: request,
  uploadFile: uploadFile,
  downloadFile: downloadFile,
  chooseMedia: chooseMedia,
  chooseImage: function(options) { return platform.callMy('chooseImage', options); },
  login: login,
  getAuthCode: function(options) { return platform.callMy('getAuthCode', options); },
  showToast: function(options) { return platform.callMy('showToast', normalizeToastOptions(options)); },
  showLoading: function(options) { return platform.callMy('showLoading', { content: (options && (options.content || options.title)) || '' }); },
  hideLoading: function(options) { return platform.callMy('hideLoading', options); },
  showModal: function(options) { return platform.callMy('confirm', options); },
  showActionSheet: function(options) { return platform.callMy('showActionSheet', { items: options.itemList || options.items || [], success: options.success, fail: options.fail }); },
  navigateTo: function(options) { return platform.callMy('navigateTo', options); },
  navigateBack: function(options) { return platform.callMy('navigateBack', options); },
  switchTab: function(options) { return platform.callMy('switchTab', options); },
  previewImage: function(options) { return platform.callMy('previewImage', options); },
  saveImageToPhotosAlbum: function(options) { return platform.callMy('saveImageToPhotosAlbum', options); },
  setNavigationBarTitle: setNavigationBarTitle,
  showShareMenu: function(options) { return platform.callMy('showSharePanel', options, function(opts) { if (opts.success) opts.success({}); }); },
  getStorageSync: function(key) { try { return platform.hasMy() && my.getStorageSync ? my.getStorageSync({ key: key }).data : ''; } catch (e) { return ''; } },
  setStorageSync: function(key, data) { try { return platform.hasMy() && my.setStorageSync ? my.setStorageSync({ key: key, data: data }) : null; } catch (e) { return null; } },
  removeStorageSync: function(key) { try { return platform.hasMy() && my.removeStorageSync ? my.removeStorageSync({ key: key }) : null; } catch (e) { return null; } },
  getSystemInfoSync: function() { return platform.hasMy() && my.getSystemInfoSync ? my.getSystemInfoSync() : {}; },
  getAccountInfoSync: getAccountInfoSync,
  getSetting: function(options) { return platform.callMy('getSetting', options); },
  authorize: function(options) { return platform.callMy('authorize', options); },
  openSetting: function(options) { return platform.callMy('openSetting', options); },
  createCameraContext: function() { return platform.hasMy() && my.createCameraContext ? my.createCameraContext() : null; },
  createSelectorQuery: function() { return platform.hasMy() && my.createSelectorQuery ? my.createSelectorQuery() : null; },
  createWorker: function(path) { return platform.hasMy() && my.createWorker ? my.createWorker(path) : null; },
  createOffscreenCanvas: function(options) { return platform.hasMy() && my.createOffscreenCanvas ? my.createOffscreenCanvas(options) : null; },
  createCanvasContext: function(id, owner) { return platform.hasMy() && my.createCanvasContext ? my.createCanvasContext(id, owner) : null; },
  canvasToTempFilePath: function(options) { return platform.callMy('canvasToTempFilePath', options); },
  compressImage: function(options) {
    if (platform.hasMy() && typeof my.compressImage === 'function') return my.compressImage(options);
    if (options && typeof options.success === 'function') options.success({ tempFilePath: options.src });
    return null;
  },
  getImageInfo: function(options) { return platform.callMy('getImageInfo', options); },
  getFileInfo: function(options) { return platform.callMy('getFileInfo', options); },
  getFileSystemManager: function() { return platform.hasMy() && my.getFileSystemManager ? my.getFileSystemManager() : null; },
  nextTick: function(callback) { return setTimeout(callback, 0); }
};
