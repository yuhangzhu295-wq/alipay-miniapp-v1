var wx = require('./platform/alipayWxCompat.js');
var TRANSFER_TTL_MS = 5 * 60 * 1000;

function getAppGlobalData() {
  try {
    var app = getApp();
    return app && app.globalData ? app.globalData : null;
  } catch (err) {
    return null;
  }
}

function encode(value) {
  return encodeURIComponent((value || '').toString());
}

function createPhotoTransfer(tempFilePath, source, specId) {
  var transfer = {
    token: 'id_photo_' + Date.now() + '_' + Math.random().toString(36).slice(2, 9),
    tempFilePath: tempFilePath,
    source: source === 'camera' ? 'camera' : 'album',
    specId: specId || 'yicun',
    createdAt: Date.now()
  };
  var globalData = getAppGlobalData();
  if (globalData) globalData.pendingIdPhotoSource = transfer;
  return transfer;
}

function consumePendingPhoto(expectedToken, expectedSpecId) {
  var globalData = getAppGlobalData();
  var transfer = globalData && globalData.pendingIdPhotoSource;
  if (!transfer) return null;
  var expired = !transfer.createdAt || Date.now() - transfer.createdAt > TRANSFER_TTL_MS;
  var tokenMismatch = expectedToken && transfer.token !== expectedToken;
  var specMismatch = expectedSpecId && transfer.specId && transfer.specId !== expectedSpecId;
  if (expired) globalData.pendingIdPhotoSource = null;
  if (expired || tokenMismatch || specMismatch) return null;
  globalData.pendingIdPhotoSource = null;
  return transfer;
}

function clearPendingPhoto(token) {
  var globalData = getAppGlobalData();
  var transfer = globalData && globalData.pendingIdPhotoSource;
  if (transfer && (!token || transfer.token === token)) {
    globalData.pendingIdPhotoSource = null;
  }
}

function openCaptureGuide(specId, options) {
  var opts = options || {};
  var id = specId || 'yicun';
  var url = '/pages/capture-guide/capture-guide?specId=' + encode(id);
  if (opts.custom) url += '&custom=true';
  return wx.navigateTo({ url: url });
}

function openCustomCamera(specId, options) {
  var opts = options || {};
  var id = specId || 'yicun';
  var url = '/pages/id-camera/id-camera?specId=' + encode(id);
  if (opts.custom) url += '&custom=true';
  if (opts.returnMode) url += '&returnMode=' + encode(opts.returnMode);
  return wx.navigateTo({
    url: url,
    success: opts.success,
    fail: opts.fail
  });
}

function openGenerateWithPhoto(specId, tempFilePath, source, options) {
  var opts = options || {};
  var id = specId || 'yicun';
  var transfer = createPhotoTransfer(tempFilePath, source, id);
  var url = '/pages/generate/generate?specId=' + encode(id) +
    '&source=' + encode(transfer.source) +
    '&transferToken=' + encode(transfer.token);
  if (opts.custom) url += '&custom=true';
  wx.navigateTo({
    url: url,
    success: function(res) {
      if (res && res.eventChannel) {
        res.eventChannel.emit('idPhotoSource', transfer);
      }
      if (typeof opts.success === 'function') opts.success(res, transfer);
    },
    fail: function(err) {
      clearPendingPhoto(transfer.token);
      if (typeof opts.fail === 'function') opts.fail(err);
    }
  });
  return transfer;
}

module.exports = {
  TRANSFER_TTL_MS: TRANSFER_TTL_MS,
  createPhotoTransfer: createPhotoTransfer,
  consumePendingPhoto: consumePendingPhoto,
  clearPendingPhoto: clearPendingPhoto,
  openCaptureGuide: openCaptureGuide,
  openCustomCamera: openCustomCamera,
  openGenerateWithPhoto: openGenerateWithPhoto
};

