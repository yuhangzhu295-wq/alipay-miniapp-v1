var specs = require('../../utils/specs.js');
var idPhotoEntry = require('../../utils/idPhotoEntry.js');

function resolveSpec(specId, isCustom) {
  if (isCustom) {
    var app = getApp();
    if (app && app.globalData && app.globalData.customSpec) return app.globalData.customSpec;
  }
  var spec = specs.getSpecById(specId);
  if (spec) return spec;
  var v2 = (specs.idPhotoSpecsV2 || []).filter(function(item) { return item.id === specId; });
  return v2[0] || specs.getSpecById('yicun');
}

function getFileSizeText(spec) {
  if (spec.maxFileKB) return '不超过 ' + spec.maxFileKB + 'KB';
  var limit = spec.fileSizeLimit;
  if (limit && typeof limit === 'object') {
    if (limit.minKB && limit.maxKB) return limit.minKB + 'KB - ' + limit.maxKB + 'KB';
    if (limit.maxKB) return '不超过 ' + limit.maxKB + 'KB';
    if (limit.minKB) return '不小于 ' + limit.minKB + 'KB';
  }
  if (typeof limit === 'string' && limit && limit !== '按报名平台要求') return limit;
  return '以报名平台要求为准';
}

function getDpiText(spec) {
  if (spec.isCustom) return '以报名平台要求为准';
  if (spec.dpi) return spec.dpi + 'dpi';
  var match = (spec.sizeText || '').match(/(\d+)\s*dpi/i);
  return match ? match[1] + 'dpi' : '以报名平台要求为准';
}

function getPurposeAdvice(spec) {
  var text = [spec.id, spec.groupId, spec.category, spec.name, spec.displayName].join(' ').toLowerCase();
  if (/passport|护照|身份证|id.card|social|社保|driver|驾驶证|出入境|通行证/.test(text)) {
    return '正面免冠，面部无遮挡。';
  }
  if (/exam|考试|报名|teacher|教师|civil|公务员|accounting|会计/.test(text)) {
    return '请按当年报名公告拍摄，保持面部无遮挡。';
  }
  return '建议正面拍摄，肩颈完整可见。';
}

Page({
  data: {
    specId: 'yicun',
    isCustom: false,
    specName: '一寸',
    printSizeText: '',
    hasPrintSize: false,
    pixelSizeText: '295 × 413px',
    fileSizeText: '以报名平台要求为准',
    dpiText: '300dpi',
    purposeAdvice: '建议正面拍摄，肩颈完整可见。',
    colors: [],
    choosingAlbum: false,
    openingCamera: false
  },

  onShow: function() {
    if (this.data.openingCamera) this.setData({ openingCamera: false });
  },

  onLoad: function(options) {
    var specId = options.specId || 'yicun';
    var isCustom = options.custom === 'true';
    var spec = resolveSpec(specId, isCustom);
    var widthMm = spec.widthMm;
    var heightMm = spec.heightMm;
    var widthPx = spec.widthPx || spec.width || 295;
    var heightPx = spec.heightPx || spec.height || 413;
    var colorIds = spec.colors || spec.bgColors || [spec.defaultBg || 'blue'];
    var colorDots = colorIds.map(function(id) {
      var color = specs.getColorById(id);
      return { id: id, name: color ? color.name : id, hex: color ? color.hex : '#1a73e8' };
    });
    var specName = spec.displayName || spec.name || '证件照';
    this.currentSpec = spec;
    this.setData({
      specId: spec.id || specId,
      isCustom: isCustom,
      specName: specName,
      printSizeText: widthMm && heightMm ? (widthMm + ' × ' + heightMm + 'mm') : '',
      hasPrintSize: !!(widthMm && heightMm),
      pixelSizeText: widthPx + ' × ' + heightPx + 'px',
      fileSizeText: getFileSizeText(spec),
      dpiText: getDpiText(spec),
      purposeAdvice: getPurposeAdvice(spec),
      colors: colorDots
    });
    wx.setNavigationBarTitle({ title: specName });
  },

  chooseFromAlbum: function() {
    if (this.data.choosingAlbum) return;
    var that = this;
    this.setData({ choosingAlbum: true });
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album'],
      success: function(res) {
        var file = res.tempFiles && res.tempFiles[0];
        if (!file || !file.tempFilePath) {
          wx.showToast({ title: '未读取到照片', icon: 'none' });
          return;
        }
        idPhotoEntry.openGenerateWithPhoto(
          that.data.specId,
          file.tempFilePath,
          'album',
          { custom: that.data.isCustom }
        );
      },
      fail: function(err) {
        if (!err || (err.errMsg || '').indexOf('cancel') === -1) {
          wx.showToast({ title: '选择图片失败，请重试', icon: 'none' });
        }
      },
      complete: function() {
        that.setData({ choosingAlbum: false });
      }
    });
  },

  openCamera: function() {
    if (this.data.openingCamera) return;
    var that = this;
    this.setData({ openingCamera: true });
    idPhotoEntry.openCustomCamera(this.data.specId, {
      custom: this.data.isCustom,
      fail: function() {
        that.setData({ openingCamera: false });
        wx.showToast({ title: '相机页面打开失败，请重试', icon: 'none' });
      }
    });
  }
});

