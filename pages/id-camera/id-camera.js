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
    cameraError: false,
    cameraErrorText: '',
    permissionDenied: false,
    capturing: false,
    submitting: false,
    capturedImage: '',
    pageActive: true,
    cameraVisible: true,
    guideWidthVw: 70,
    guideHeightVw: 101
  },

  onLoad: function(options) {
    var specId = options.specId || 'yicun';
    var isCustom = options.custom === 'true';
    var spec = resolveSpec(specId, isCustom);
    var ratio = Number(spec.widthPx || spec.width || 295) / Number(spec.heightPx || spec.height || 413);
    var guideWidth = Math.max(65, Math.min(74, Math.round(70 + (0.72 - ratio) * 10)));
    this.setData({
      specId: specId,
      specName: spec.displayName || spec.name || '证件照',
      isCustom: isCustom,
      returnMode: options.returnMode === 'replace' ? 'replace' : 'initial',
      guideWidthVw: guideWidth,
      guideHeightVw: Math.round(guideWidth * 1.44)
    });
  },

  onReady: function() {
    this.cameraContext = wx.createCameraContext();
  },

  onShow: function() {
    var that = this;
    this.setData({ pageActive: true, submitting: false });
    if (!wx.getSetting) return;
    wx.getSetting({
      success: function(res) {
        if (res.authSetting && res.authSetting['scope.camera'] === true && that.data.permissionDenied) {
          that.restartCamera();
        }
      }
    });
  },

  onHide: function() {
    this.setData({ pageActive: false, capturing: false });
  },

  onCameraReady: function() {
    this.setData({
      cameraReady: true,
      cameraError: false,
      cameraErrorText: '',
      permissionDenied: false
    });
  },

  onCameraError: function(event) {
    var detail = event && event.detail ? event.detail : {};
    var errMsg = detail.errMsg || '相机初始化失败';
    var errCode = detail.errCode === undefined ? '' : detail.errCode;
    var denied = /auth|permission|deny|authorize/i.test(errMsg) || errCode === 10001;
    console.error('[id-camera] error', {
      errMsg: errMsg,
      errCode: errCode,
      cameraPosition: this.data.cameraPosition,
      route: 'pages/id-camera/id-camera',
      specId: this.data.specId
    });
    this.setData({
      cameraReady: false,
      cameraError: true,
      permissionDenied: denied,
      cameraErrorText: denied ? '需要相机权限才能直接拍摄证件照。' : '相机暂时无法使用，请重试或选择相册。',
      capturing: false
    });
  },

  openCameraSettings: function() {
    var that = this;
    wx.openSetting({
      success: function(res) {
        if (res.authSetting && res.authSetting['scope.camera']) {
          that.restartCamera();
        } else {
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

  restartCamera: function() {
    var that = this;
    this.setData({
      cameraError: false,
      cameraErrorText: '',
      cameraReady: false,
      permissionDenied: false,
      cameraVisible: false
    }, function() {
      that.setData({ cameraVisible: true });
    });
  },

  switchCamera: function() {
    if (this.data.capturing || this.data.submitting || this.data.cameraMode !== 'live') return;
    var next = this.data.cameraPosition === 'back' ? 'front' : 'back';
    this.setData({ cameraPosition: next, cameraReady: false });
  },

  takePhoto: function() {
    if (this.data.capturing || this.data.submitting || this.data.cameraMode !== 'live') return;
    if (!this.data.cameraReady || !this.cameraContext) {
      wx.showToast({ title: '相机正在准备，请稍后', icon: 'none' });
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
    var that = this;
    this.setData({
      cameraMode: 'live',
      capturedImage: '',
      capturing: false,
      cameraReady: false,
      cameraVisible: false
    }, function() {
      that.setData({ cameraVisible: true });
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

