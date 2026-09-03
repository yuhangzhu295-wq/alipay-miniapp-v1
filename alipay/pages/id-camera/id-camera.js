var wx = require('../../utils/platform/alipayWxCompat.js');
var specs = require('../../utils/specs.js');
var idPhotoEntry = require('../../utils/idPhotoEntry.js');

function resolveSpec(specId, isCustom) {
  if (isCustom) {
    var app = getApp();
    var custom = app && app.globalData && app.globalData.customSpec;
    if (custom) return custom;
  }
  var spec = specs.getSpecById(specId);
  if (!spec) {
    var matches = (specs.idPhotoSpecsV2 || []).filter(function(item) { return item.id === specId; });
    spec = matches[0];
  }
  return spec || { id: specId, name: '证件照', widthPx: 295, heightPx: 413 };
}

function computeGuideLayout(guideWidthVw, windowWidth, windowHeight, safeAreaBottom) {
  var sys = {};
  if (typeof wx !== 'undefined' && wx.getSystemInfoSync) {
    try { sys = wx.getSystemInfoSync() || {}; } catch(e) {}
  }
  var wWidth = windowWidth || sys.windowWidth || 375;
  var wHeight = windowHeight || sys.windowHeight || 667;

  var bottomInset = safeAreaBottom;
  if (bottomInset === undefined) {
    if (sys.safeArea && sys.safeArea.bottom && sys.windowHeight) {
      bottomInset = Math.max(0, sys.windowHeight - sys.safeArea.bottom);
    } else {
      bottomInset = 0;
    }
  }

  var controlsHeightPx = Math.round(190 * wWidth / 750) + bottomInset;
  var cameraHeightPx = Math.max(200, wHeight - controlsHeightPx);

  var vw = guideWidthVw || 70;
  var guideWidthPx = Math.round(wWidth * (vw / 100));
  var maxWidthPx = Math.round(560 * wWidth / 750);
  if (guideWidthPx > maxWidthPx) {
    guideWidthPx = maxWidthPx;
  }
  var guideHeightPx = Math.round(guideWidthPx * 1.4375);

  var maxGuideHeightPx = Math.round(cameraHeightPx * 0.85);
  if (guideHeightPx > maxGuideHeightPx) {
    guideHeightPx = maxGuideHeightPx;
    guideWidthPx = Math.round(guideHeightPx / 1.4375);
  }

  var guideLeftPx = Math.round((wWidth - guideWidthPx) / 2);
  var targetCenterY = Math.round(cameraHeightPx * 0.54);
  var guideTopPx = Math.round(targetCenterY - guideHeightPx / 2);

  var eyeLabelTopPx = guideTopPx + Math.round(guideHeightPx * 0.37) - 10;

  return {
    guideWidthPx: guideWidthPx,
    guideHeightPx: guideHeightPx,
    guideLeftPx: guideLeftPx,
    guideTopPx: guideTopPx,
    eyeLabelTopPx: eyeLabelTopPx
  };
}

function isoNow() {
  return new Date().toISOString();
}

function afterViewCommit(callback) {
  if (wx.nextTick) {
    wx.nextTick(callback);
    return;
  }
  setTimeout(callback, 0);
}

Page({
  data: {
    specId: 'yicun',
    specName: '一寸',
    isCustom: false,
    returnMode: 'initial',
    cameraMode: 'live',
    cameraPosition: 'back',
    flashMode: 'off',
    cameraReady: false,
    cameraInitState: 'idle',
    cameraStatusText: '相机正在初始化',
    cameraInitAttempt: 0,
    cameraError: false,
    cameraErrorText: '',
    permissionDenied: false,
    capturing: false,
    submitting: false,
    capturedImage: '',
    pageActive: true,
    cameraVisible: true,
    guideWidthVw: 70,
    guideHeightVw: 101,
    guideWidthPx: 262,
    guideHeightPx: 377,
    guideLeftPx: 56,
    guideTopPx: 120,
    eyeLabelTopPx: 250,
    guideSvgDataUri: "data:image/svg+xml;charset=utf-8,%3Csvg%20viewBox%3D%220%200%20200%20300%22%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%3E%3Cpath%20d%3D%22M%2060%20100%20C%2060%2020%2C%20140%2020%2C%20140%20100%20C%20140%20140%2C%20120%20160%2C%20100%20160%20C%2080%20160%2C%2060%20140%2C%2060%20100%20Z%22%20fill%3D%22none%22%20stroke%3D%22white%22%20stroke-width%3D%224%22%20stroke-dasharray%3D%228%2C8%22%20%2F%3E%3Cpath%20d%3D%22M%20100%20160%20C%20100%20180%2C%20150%20200%2C%20200%20240%20L%20200%20300%20L%200%20300%20L%200%20240%20C%2050%20200%2C%20100%20180%2C%20100%20160%22%20fill%3D%22none%22%20stroke%3D%22white%22%20stroke-width%3D%224%22%20stroke-dasharray%3D%228%2C8%22%20%2F%3E%3C%2Fsvg%3E"
  },

  onLoad: function(options) {
    this._cameraInitTimer = null;
    this._cameraRestartTimer = null;
    this._cameraNeedsRestart = false;
    options = options || {};
    var specId = options.specId || 'yicun';
    var isCustom = options.custom === 'true';
    var spec = resolveSpec(specId, isCustom);
    var ratio = Number(spec.widthPx || spec.width || 295) / Number(spec.heightPx || spec.height || 413);
    var guideWidth = Math.max(65, Math.min(74, Math.round(70 + (0.72 - ratio) * 10)));
    var layout = computeGuideLayout(guideWidth);

    this.setData({
      specId: specId,
      specName: spec.displayName || spec.name || '证件照',
      isCustom: isCustom,
      returnMode: options.returnMode === 'replace' ? 'replace' : 'initial',
      guideWidthVw: guideWidth,
      guideHeightVw: Math.round(guideWidth * 1.44),
      guideWidthPx: layout.guideWidthPx,
      guideHeightPx: layout.guideHeightPx,
      guideLeftPx: layout.guideLeftPx,
      guideTopPx: layout.guideTopPx,
      eyeLabelTopPx: layout.eyeLabelTopPx
    });
    this.debugCamera('page load', { specId: specId, returnMode: options.returnMode || 'initial' });
  },

  onReady: function() {
    this.debugCamera('page ready');
    this.checkCameraPermission('page ready');
    this.beginCameraInit('page ready');
  },

  onShow: function() {
    var that = this;
    this.setData({ pageActive: true, submitting: false });
    this.debugCamera('page show');
    this.checkCameraPermission('page show', function(permission) {
      if (permission === false) return;
      if (that._cameraNeedsRestart && that.data.cameraMode === 'live') {
        that._cameraNeedsRestart = false;
        that.restartCamera('page show');
      }
    });
  },

  onHide: function() {
    this.clearCameraInitTimer();
    this._cameraNeedsRestart = true;
    this.setData({ pageActive: false, capturing: false });
    this.debugCamera('page hide');
  },

  onResize: function(res) {
    var size = res && res.size ? res.size : {};
    var layout = computeGuideLayout(this.data.guideWidthVw, size.windowWidth, size.windowHeight);
    this.setData(layout);
  },

  debugCamera: function(eventName, detail) {
    var snapshot = {
      at: isoNow(),
      cameraReady: this.data.cameraReady,
      cameraVisible: this.data.cameraVisible,
      cameraMode: this.data.cameraMode,
      cameraPosition: this.data.cameraPosition,
      initAttempt: this.data.cameraInitAttempt,
      contextExists: !!this.cameraContext
    };
    console.log('[id-camera] ' + eventName, Object.assign(snapshot, detail || {}));
  },

  clearCameraInitTimer: function() {
    if (this._cameraInitTimer) {
      clearTimeout(this._cameraInitTimer);
      this._cameraInitTimer = null;
    }
  },

  checkCameraPermission: function(reason, callback) {
    var that = this;
    if (!wx.getSetting) {
      this.debugCamera('permission', { reason: reason, supported: false });
      if (callback) callback(null);
      return;
    }
    wx.getSetting({
      success: function(res) {
        var setting = res.authSetting || {};
        var permission = setting['scope.camera'];
        that.debugCamera('permission', { reason: reason, permission: permission });
        if (permission === false) {
          that.failCameraInit('相机权限被拒绝，请在设置中开启后重新初始化。', true, 'permission denied');
        }
        if (callback) callback(permission);
      },
      fail: function(err) {
        that.debugCamera('permission', { reason: reason, queryFailed: true, error: err || {} });
        if (callback) callback(null);
      }
    });
  },

  beginCameraInit: function(reason) {
    var that = this;
    if (!this.data.pageActive || this.data.cameraMode !== 'live' || !this.data.cameraVisible || this.data.cameraError) return;
    this.clearCameraInitTimer();
    this.cameraContext = null;
    var attempt = Number(this.data.cameraInitAttempt || 0) + 1;
    this.setData({
      cameraReady: false,
      cameraError: false,
      cameraErrorText: '',
      permissionDenied: false,
      cameraInitState: 'initializing',
      cameraStatusText: '相机正在初始化',
      cameraInitAttempt: attempt
    });
    this.debugCamera('restart', { reason: reason, attempt: attempt });
    afterViewCommit(function() {
      if (!that.data.pageActive || that.data.cameraMode !== 'live' || !that.data.cameraVisible) return;
      try {
        that.cameraContext = wx.createCameraContext();
        that.debugCamera('context created', { reason: reason, attempt: attempt });
      } catch (err) {
        that.failCameraInit('无法创建相机上下文，请重新初始化或改用相册。', false, err);
        return;
      }
      that._cameraInitTimer = setTimeout(function() {
        if (!that.data.cameraReady && that.data.pageActive && that.data.cameraVisible) {
          that.failCameraInit('5秒内未收到相机就绪事件，请重新初始化或改用相册。', false, 'initdone timeout');
        }
      }, 5000);
    });
  },

  failCameraInit: function(message, permissionDenied, cause) {
    this.clearCameraInitTimer();
    this.cameraContext = null;
    this.debugCamera('ready state', { state: 'failed', cause: cause || message });
    this.setData({
      cameraReady: false,
      cameraError: true,
      permissionDenied: !!permissionDenied,
      cameraErrorText: message,
      cameraInitState: 'failed',
      cameraStatusText: message,
      capturing: false
    });
  },

  onCameraReady: function() {
    if (!this.data.cameraVisible || this.data.cameraError || this.data.cameraMode !== 'live') {
      this.debugCamera('initdone', { ignored: true });
      return;
    }
    this.clearCameraInitTimer();
    this.debugCamera('initdone');
    this.setData({
      cameraReady: true,
      cameraError: false,
      cameraErrorText: '',
      permissionDenied: false,
      cameraInitState: 'ready',
      cameraStatusText: '相机已就绪'
    });
    this.debugCamera('ready state', { state: 'ready' });
  },

  onCameraError: function(event) {
    var detail = event && event.detail ? event.detail : {};
    var errMsg = detail.errMsg || '相机初始化失败';
    var errCode = detail.errCode === undefined ? '' : detail.errCode;
    var denied = /auth|permission|deny|authorize/i.test(errMsg) || errCode === 10001;
    this.clearCameraInitTimer();
    console.error('[id-camera] error', {
      at: isoNow(),
      errMsg: errMsg,
      errCode: errCode,
      cameraPosition: this.data.cameraPosition,
      route: 'pages/id-camera/id-camera',
      specId: this.data.specId
    });
    this.failCameraInit(
      denied ? '需要相机权限才能直接拍摄证件照。' : ('相机初始化失败：' + errMsg),
      denied,
      detail
    );
  },

  openCameraSettings: function() {
    var that = this;
    wx.openSetting({
      success: function(res) {
        if (res.authSetting && res.authSetting['scope.camera']) {
          that.debugCamera('permission', { reason: 'settings returned', permission: true });
          that.restartCamera('settings returned');
        } else {
          that.failCameraInit('相机权限仍未开启，请允许后重新初始化或使用相册。', true, 'settings denied');
          wx.showToast({ title: '相机权限仍未开启', icon: 'none' });
        }
      },
      fail: function() {
        wx.showToast({ title: '无法打开设置，请稍后重试', icon: 'none' });
      }
    });
  },

  retryCamera: function() {
    this.restartCamera();
  },

  restartCamera: function(reason, overrides) {
    var that = this;
    this.clearCameraInitTimer();
    if (this._cameraRestartTimer) clearTimeout(this._cameraRestartTimer);
    this.cameraContext = null;
    var nextData = Object.assign({
      cameraError: false,
      cameraErrorText: '',
      cameraReady: false,
      permissionDenied: false,
      cameraInitState: 'restarting',
      cameraStatusText: '正在重新初始化相机',
      cameraVisible: false
    }, overrides || {});
    this.debugCamera('restart', { reason: reason || 'manual', phase: 'unmount' });
    this.setData(nextData, function() {
      afterViewCommit(function() {
        afterViewCommit(function() {
          if (!that.data.pageActive || that.data.cameraMode !== 'live') return;
          that.setData({ cameraVisible: true }, function() {
            afterViewCommit(function() {
              that.beginCameraInit(reason || 'manual');
            });
          });
        });
      });
    });
  },

  switchCamera: function() {
    if (this.data.capturing || this.data.submitting || this.data.cameraMode !== 'live') return;
    var next = this.data.cameraPosition === 'back' ? 'front' : 'back';
    this.debugCamera('switch', { from: this.data.cameraPosition, to: next });
    this.restartCamera('switch camera', { cameraPosition: next });
  },

  takePhoto: function() {
    if (this.data.capturing || this.data.submitting || this.data.cameraMode !== 'live') return;
    this.debugCamera('ready state', { action: 'takePhoto' });
    if (!this.data.cameraReady || !this.cameraContext) {
      wx.showToast({ title: this.data.cameraErrorText || '相机初始化中，请稍后', icon: 'none' });
      return;
    }
    var that = this;
    this.setData({ capturing: true });
    this.cameraContext.takePhoto({
      quality: 'high',
      success: function(res) {
        if (!res || !res.tempImagePath) {
          that.setData({ capturing: false });
          wx.showToast({ title: '未获取到照片，请重试', icon: 'none' });
          return;
        }
        that.setData({
          cameraMode: 'confirm',
          capturedImage: res.tempImagePath,
          capturing: false,
          cameraReady: false
        });
        that.clearCameraInitTimer();
      },
      fail: function(err) {
        console.error('[id-camera] takePhoto failed', err || {});
        that.setData({ capturing: false });
        wx.showToast({ title: '拍照失败，请重试', icon: 'none' });
      }
    });
  },

  retakePhoto: function() {
    if (this.data.submitting) return;
    this.restartCamera('retake photo', {
      cameraMode: 'live',
      capturedImage: '',
      capturing: false
    });
  },

  deliverReplacement: function(tempFilePath, source) {
    var transfer = idPhotoEntry.createPhotoTransfer(tempFilePath, source, this.data.specId);
    var channel = this.getOpenerEventChannel ? this.getOpenerEventChannel() : null;
    if (channel && channel.emit) channel.emit('idPhotoSource', transfer);
    wx.navigateBack();
  },

  usePhoto: function() {
    if (this.data.submitting || !this.data.capturedImage) return;
    this.setData({ submitting: true });
    if (this.data.returnMode === 'replace') {
      this.deliverReplacement(this.data.capturedImage, 'camera');
      return;
    }
    idPhotoEntry.openGenerateWithPhoto(
      this.data.specId,
      this.data.capturedImage,
      'camera',
      {
        custom: this.data.isCustom,
        fail: function() { this.setData({ submitting: false }); }.bind(this)
      }
    );
  },

  chooseFromAlbum: function() {
    if (this.data.submitting) return;
    var that = this;
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album'],
      success: function(res) {
        var file = res.tempFiles && res.tempFiles[0];
        if (!file || !file.tempFilePath) return;
        that.setData({ submitting: true });
        if (that.data.returnMode === 'replace') {
          that.deliverReplacement(file.tempFilePath, 'album');
        } else {
          idPhotoEntry.openGenerateWithPhoto(that.data.specId, file.tempFilePath, 'album', {
            custom: that.data.isCustom,
            fail: function() { that.setData({ submitting: false }); }
          });
        }
      },
      fail: function(err) {
        if (!err || (err.errMsg || '').indexOf('cancel') === -1) {
          wx.showToast({ title: '选择图片失败，请重试', icon: 'none' });
        }
      }
    });
  }
});
