// ====== 选择底色 / 下载证件照 ======
var specs = require('../../utils/specs.js');
var imageUtil = require('../../utils/image.js');
var aiImageApi = require('../../utils/aiImageApi.js');
var apiConfig = require('../../utils/apiConfig.js');
var imageService = require('../../utils/imageService.js');

Page({
  data: {
    photoSrc: '',
    bgColorHex: '#1a73e8',
    bgColorId: 'blue',
    bgColorName: '蓝底',
    specName: '一寸照',
    specSize: '25×35mm | 295×413px',
    widthPxLabel: '295px',
    heightPxLabel: '413px',
    widthMmLabel: '25mm',
    heightMmLabel: '35mm',
    previewWidthRpx: 336,
    previewHeightRpx: 470,
    currentSpec: null,
    currentSpecId: '',
    availableColors: [],
    fileText: '',
    hairRetouch: false,
    outputTab: 'photo',
    generating: false,
    canDownload: false,
    processState: 'idle',
    statusText: '上传照片后自动生成',
    preparedId: '',
    preparedKey: '',
    resultImage: '',
    resultPreviewSrc: '',
    resultRemoteUrl: '',
    layoutImage: '',
    resultColorId: '',
    layoutColorId: ''
  },

  computePreviewSize: function(spec) {
    var targetW = spec.widthPx || 295;
    var targetH = spec.heightPx || 413;
    var ratio = targetW / targetH;
    var maxW = 344;
    var maxH = 470;
    var width = maxW;
    var height = Math.round(width / ratio);
    if (height > maxH) {
      height = maxH;
      width = Math.round(height * ratio);
    }
    return {
      width: Math.max(220, width),
      height: Math.max(260, height)
    };
  },

  getCurrentRouteForLog: function() {
    try {
      var pages = getCurrentPages ? getCurrentPages() : [];
      var current = pages && pages.length ? pages[pages.length - 1] : null;
      return current && current.route ? current.route : 'pages/generate/generate';
    } catch (e) {
      return 'pages/generate/generate';
    }
  },

  logCurrentPage: function(stage) {
    var route = this.getCurrentRouteForLog();
    console.log('[id-photo-page] currentRoute=' + route);
    console.log('[id-photo-page] currentFile=pages/generate/generate');
    console.log('[id-photo-fe] route=' + route + ' stage=' + (stage || 'unknown'));
  },

  onLoad: function(options) {
    this.logCurrentPage('onLoad');
    var specId = options.specId;
    var spec = null;

    if (specId === 'custom_pass' || options.custom === 'true') {
      var app = getApp();
      if (app && app.globalData && app.globalData.customSpec) {
        spec = app.globalData.customSpec;
      }
    }
    if (!spec && specId) {
      spec = specs.getSpecById(specId);
    }
    if (!spec) {
      spec = specs.getSpecById('yicun');
    }
    this.applySpec(spec);
    wx.setNavigationBarTitle({ title: '选择底色' });

    if (options.mode === 'capture') {
      this.takePhoto();
    }
  },

  onShow: function() {
    this.logCurrentPage('onShow');
  },

  onUnload: function() {
    this.clearProcessTimer();
  },

  applySpec: function(spec) {
    this.idPhotoCropCache = null;
    var bgInfo = specs.getColorById(spec.defaultBg || 'blue');
    var previewSize = this.computePreviewSize(spec);
    var colors = (spec.colors || spec.bgColors || ['blue', 'white', 'red', 'lightBlue', 'gray']).map(function(id) {
      var color = specs.getColorById(id);
      return {
        id: id,
        name: color ? color.name : id,
        hex: color ? color.hex : '#1a73e8'
      };
    });
    this.setData({
      currentSpec: spec,
      currentSpecId: spec.id,
      specName: spec.displayName || (spec.name + '照'),
      specSize: specs.formatSpecSize ? specs.formatSpecSize(spec) : [spec.mm, spec.px].filter(Boolean).join(' | '),
      widthPxLabel: (spec.widthPx || 295) + 'px',
      heightPxLabel: (spec.heightPx || 413) + 'px',
      widthMmLabel: spec.widthMm ? (spec.widthMm + 'mm') : '按像素',
      heightMmLabel: spec.heightMm ? (spec.heightMm + 'mm') : '按像素',
      previewWidthRpx: previewSize.width,
      previewHeightRpx: previewSize.height,
      fileText: spec.fileText || '',
      bgColorHex: bgInfo.hex,
      bgColorId: bgInfo.id,
      bgColorName: (bgInfo.name || '蓝色') + '底',
      availableColors: colors,
      processState: 'idle',
      statusText: '上传照片后自动生成',
      preparedId: '',
      preparedKey: '',
      resultImage: '',
      resultPreviewSrc: '',
      resultRemoteUrl: '',
      layoutImage: '',
      resultColorId: '',
      layoutColorId: '',
      canDownload: false
    });
  },

  clearProcessTimer: function() {
    if (this.processTimer) {
      clearTimeout(this.processTimer);
      this.processTimer = null;
    }
  },

  startProcessTimer: function(durationMs) {
    var that = this;
    this.clearProcessTimer();
    this.processTimer = setTimeout(function() {
      if (that.data.generating) {
        that.currentGenerateToken = 'timeout_' + Date.now();
        var wasPreparing = that.data.processState === 'preparing';
        that.setData({
          generating: false,
          processState: 'timeout',
          statusText: '制作时间较长，请稍后重试或重新上传。',
          preparedId: wasPreparing ? '' : that.data.preparedId,
          preparedKey: wasPreparing ? '' : that.data.preparedKey,
          resultImage: '',
          resultPreviewSrc: '',
          resultRemoteUrl: '',
          layoutImage: '',
          resultColorId: '',
          layoutColorId: '',
          canDownload: false
        });
        wx.showToast({ title: '制作时间较长，请稍后重试或重新上传。', icon: 'none' });
      }
    }, durationMs || 30000);
  },

  choosePhoto: function() {
    var that = this;
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      success: function(res) {
        that.setData({
          photoSrc: res.tempFiles[0].tempFilePath,
          preparedId: '',
          preparedKey: '',
          resultImage: '',
          resultPreviewSrc: '',
          resultRemoteUrl: '',
          layoutImage: '',
          resultColorId: '',
          layoutColorId: '',
          canDownload: false
        }, function() {
          that.idPhotoCropCache = null;
          that.generatePhoto();
        });
      },
      fail: function(err) {
        if (err.errMsg.indexOf('cancel') === -1) {
          wx.showToast({ title: '选择图片失败', icon: 'none' });
        }
      }
    });
  },

  takePhoto: function() {
    var that = this;
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['camera'],
      success: function(res) {
        that.setData({
          photoSrc: res.tempFiles[0].tempFilePath,
          preparedId: '',
          preparedKey: '',
          resultImage: '',
          resultRemoteUrl: '',
          layoutImage: '',
          resultColorId: '',
          layoutColorId: '',
          canDownload: false
        }, function() {
          that.idPhotoCropCache = null;
          that.generatePhoto();
        });
      },
      fail: function(err) {
        if (err.errMsg.indexOf('cancel') === -1) {
          wx.showToast({ title: '拍照失败', icon: 'none' });
        }
      }
    });
  },

  selectBg: function(e) {
    var that = this;
    var colorId = e.currentTarget.dataset.id;
    var color = specs.getColorById(colorId);
    if (!color) return;
    this.setData({
      bgColorHex: color.hex,
      bgColorId: color.id,
      bgColorName: color.name + '底',
      processState: 'changingColor',
      statusText: '正在切换底色...',
      resultImage: '',
      resultPreviewSrc: '',
      resultRemoteUrl: '',
      layoutImage: '',
      resultColorId: '',
      layoutColorId: '',
      canDownload: false
    }, function() {
      if (that.data.photoSrc) {
        that.generatePhoto('正在切换底色...');
      }
    });
  },

  setOutputTab: function(e) {
    var tab = e.currentTarget.dataset.tab;
    var that = this;
    this.setData({ outputTab: tab }, function() {
      if (tab === 'layout' && that.data.resultImage && !that.data.layoutImage) {
        that.generateLayoutPhoto();
      }
    });
  },

  goSpecs: function() {
    wx.navigateTo({ url: '/pages/specs/specs' });
  },

  useAiBgColor: function() {
    return ['blue', 'white', 'red', 'lightBlue', 'gray', 'darkBlue'].indexOf(this.data.bgColorId) >= 0;
  },

  extractFaceBox: function(inspectResult) {
    if (!inspectResult) return null;
    var quality = inspectResult.quality || inspectResult;
    return quality.faceBox || inspectResult.faceBox || null;
  },

  getBackendSpecId: function(spec) {
    var map = {
      yicun: 'one-inch',
      ercun: 'two-inch',
      xiaoyicun: 'small-one-inch',
      dayicun: 'large-one-inch',
      xiaoercun: 'small-two-inch',
      daercun: 'large-two-inch',
      jiaoshi: 'teacher-exam',
      civil_service: 'civil-service-exam',
      computer: 'computer-exam',
      cet: 'cet-exam',
      driver: 'driver-license-cn',
      driver_common: 'driver-license-cn',
      jianli: 'resume-headshot'
    };
    return map[spec.id] || spec.backendSpecId || spec.id || 'one-inch';
  },

  getBackendPurpose: function(spec) {
    var id = spec.id || '';
    var groupId = spec.groupId || '';
    var category = spec.category || '';
    if (id.indexOf('teacher') >= 0 || id.indexOf('exam') >= 0 || category.indexOf('考试') >= 0) {
      return id.indexOf('civil') >= 0 ? 'civil_service_exam' : 'teacher_exam';
    }
    if (groupId === 'social_id_card' || id.indexOf('id_card') >= 0 || id.indexOf('social') >= 0) {
      return id.indexOf('social') >= 0 ? 'social_security' : 'id_card';
    }
    if (groupId === 'passport_visa' || id.indexOf('passport') >= 0) {
      return 'passport';
    }
    if (id === 'driver' || id === 'driver_common' || id === 'driver-license-cn') {
      return 'driver_license';
    }
    if (id.indexOf('resume') >= 0 || id === 'jianli') {
      return 'resume';
    }
    return 'official_id_photo';
  },

  generatePhoto: function(statusText) {
    var that = this;
    if (!that.data.photoSrc) {
      wx.showToast({ title: '请先上传照片', icon: 'none' });
      return;
    }
    if (!that.data.currentSpec) {
      wx.showToast({ title: '请选择规格', icon: 'none' });
      return;
    }

    var requestPhotoSrc = that.data.photoSrc;
    var requestSpec = that.data.currentSpec;
    var requestBgColorId = that.data.bgColorId;
    var requestBgColorHex = that.data.bgColorHex;
    var requestBgColorName = that.data.bgColorName;
    var prepareEndpoint = apiConfig.API_BASE_URL + '/api/id-photo/prepare';
    var composeEndpoint = apiConfig.API_BASE_URL + '/api/id-photo/compose';
    var requestPayload = {
      purpose: that.getBackendPurpose(requestSpec),
      specId: that.getBackendSpecId(requestSpec),
      widthPx: requestSpec.widthPx || 295,
      heightPx: requestSpec.heightPx || 413,
      widthMm: requestSpec.widthMm || '',
      heightMm: requestSpec.heightMm || '',
      bgColor: requestBgColorHex,
      bgColorName: requestBgColorId,
      mode: 'official',
      composition: requestSpec.backendComposition || requestSpec.composition || 'head_shoulder',
      enhanceLevel: 'standard',
      outputType: 'jpg',
      hairRetouch: that.data.hairRetouch || false
    };
    var requestToken = Date.now() + '_' + requestBgColorId;
    var prepareKey = [
      requestPhotoSrc,
      requestPayload.specId,
      requestPayload.widthPx,
      requestPayload.heightPx,
      requestPayload.composition,
      requestPayload.hairRetouch
    ].join('|');
    var hasPrepared = that.data.preparedId && that.data.preparedKey === prepareKey;
    var currentRoute = that.getCurrentRouteForLog();
    that.currentGenerateToken = requestToken;

    that.setData({
      generating: true,
      processState: hasPrepared ? 'composing' : 'preparing',
      statusText: hasPrepared ? ((typeof statusText === 'string' ? statusText : null) || '换底中...') : '制作中...',
      resultImage: '',
      resultPreviewSrc: '',
      resultRemoteUrl: '',
      layoutImage: '',
      resultColorId: '',
      layoutColorId: '',
      canDownload: false
    });
    // Covers one prepare plus the compose retry budget without racing wx timeouts.
    that.startProcessTimer(hasPrepared ? 135000 : 330000);
    console.log('[id-photo-generate] API_BASE_URL:', apiConfig.API_BASE_URL);
    console.log('[id-photo-generate] prepare endpoint:', prepareEndpoint);
    console.log('[id-photo-generate] compose endpoint:', composeEndpoint);
    console.log('[id-photo-generate] specId:', requestPayload.specId);
    console.log('[id-photo-generate] bgColor:', requestPayload.bgColor, requestPayload.bgColorName);
    console.log('[id-photo-fe] route=' + currentRoute);
    console.log('[id-photo-fe] API_BASE_URL=' + apiConfig.API_BASE_URL);
    console.log('[id-photo-fe] prepare endpoint=' + prepareEndpoint);
    console.log('[id-photo-fe] compose endpoint=' + composeEndpoint);
    console.log('[id-photo-fe] selectedBgColor=' + requestBgColorHex);
    console.log('[id-photo-fe] bgColorName=' + requestBgColorId);
    console.log('[id-photo-fe] specId=' + requestPayload.specId);
    console.log('[id-photo-fe] widthPx=' + requestPayload.widthPx + ' heightPx=' + requestPayload.heightPx);
    console.log('[id-photo-fe] request payload:', requestPayload);
    console.log('[id-photo-fe] hasPrepared=' + !!hasPrepared);

    var preparePromise = hasPrepared
      ? Promise.resolve({ preparedId: that.data.preparedId })
      : aiImageApi.prepareIdPhotoV2(requestPhotoSrc, requestPayload);
    var composePayload = {
      bgColor: requestBgColorHex,
      bgColorName: requestBgColorId,
      outputType: 'jpg'
    };
    var composeWithRetry = function(preparedId, attempt) {
      return aiImageApi.composeIdPhotoV2(Object.assign({}, composePayload, {
        preparedId: preparedId
      })).catch(function(err) {
        var retryable = err && (err.code === 'SERVICE_TIMEOUT' || err.code === 'ID_PHOTO_TIMEOUT' || err.code === 'SERVICE_UNAVAILABLE');
        if (!retryable || attempt >= 1) {
          throw err;
        }
        console.warn('[id-photo-fe] compose retry requestId=' + (err.requestId || '') + ' attempt=' + (attempt + 1));
        that.setData({
          processState: 'composing',
          statusText: '底色生成较慢，正在重试...'
        });
        return new Promise(function(resolve) {
          setTimeout(resolve, 800);
        }).then(function() {
          return composeWithRetry(preparedId, attempt + 1);
        });
      });
    };

    preparePromise
      .then(function(prepared) {
        if (that.currentGenerateToken !== requestToken) {
          var silent = new Error('stale request');
          silent.silent = true;
          throw silent;
        }
        if (!prepared || !prepared.preparedId) {
          var prepError = new Error('人像预处理失败，请重新上传清晰正面照片。');
          prepError.code = 'PREPARE_FAILED';
          throw prepError;
        }
        console.log('[id-photo-fe] prepare success=' + (prepared.success !== false));
        console.log('[id-photo-fe] prepare code=' + (prepared.code || ''));
        console.log('[id-photo-fe] preparedId=' + prepared.preparedId);
        console.log('[id-photo-fe] prepare engine=' + (prepared.engine || (prepared.debug && prepared.debug.engine) || ''));
        console.log('[id-photo-fe] prepare engineVersion=' + (prepared.engineVersion || (prepared.debug && prepared.debug.engineVersion) || ''));
        console.log('[id-photo-fe] prepare engineModel=' + (prepared.engineModel || (prepared.debug && prepared.debug.engineModel) || ''));
        console.log('[id-photo-fe] prepare debug:', prepared.debug || null);
        if (!hasPrepared) {
          that.setData({
            preparedId: prepared.preparedId,
            preparedKey: prepareKey,
            processState: 'composing',
            statusText: '换底中...'
          });
        }
        return composeWithRetry(prepared.preparedId, 0);
      })
      .then(function(result) {
        if (that.currentGenerateToken !== requestToken) return;
        if (!result || !result.tempFilePath) {
          var emptyError = new Error('底色生成失败，请重新选择底色或重新上传照片。');
          emptyError.code = 'ID_PHOTO_GENERATE_FAILED';
          throw emptyError;
        }
        var qualityReport = result.quality && result.quality.qualityReport;
        if (qualityReport && qualityReport.passed === false) {
          var qualityError = new Error('证件照生成质量未达标，请重新上传清晰正面照片。');
          qualityError.code = 'ID_PHOTO_QUALITY_FAILED';
          qualityError.quality = qualityReport;
          throw qualityError;
        }
        console.log('[id-photo-generate] success:', true);
        console.log('[id-photo-generate] finalImageUrl exists:', !!result.tempFilePath);
        console.log('[id-photo-fe] compose success=true');
        console.log('[id-photo-fe] compose code=' + (result.code || ''));
        console.log('[id-photo-fe] finalImageUrl=' + (result.finalImageUrl || result.tempFilePath || ''));
        console.log('[id-photo-fe] previewUrl=' + (result.previewUrl || result.finalImageUrl || ''));
        console.log('[id-photo-fe] previewFilePath=' + (result.previewFilePath || ''));
        console.log('[id-photo-fe] downloadFilePath=' + (result.downloadFilePath || ''));
        console.log('[id-photo-fe] compose engine=' + (result.engine || ''));
        console.log('[id-photo-fe] compose engineVersion=' + (result.engineVersion || ''));
        console.log('[id-photo-fe] compose engineModel=' + (result.engineModel || ''));
        console.log('[id-photo-fe] compose debug:', result.debug || null);
        that.clearProcessTimer();
        that.setData({
          generating: false,
          processState: 'ready',
          statusText: requestBgColorName + ' · 可下载',
          resultImage: result.tempFilePath,
          resultPreviewSrc: result.previewUrl || result.finalImageUrl || result.remoteUrl || result.tempFilePath,
          resultRemoteUrl: result.finalImageUrl || result.remoteUrl || '',
          resultColorId: requestBgColorId,
          layoutColorId: '',
          canDownload: true
        }, function() {
          if (that.data.outputTab === 'layout') {
            that.generateLayoutPhoto();
          }
        });
      })
      .catch(function(err) {
        if (err && err.silent) return;
        that.clearProcessTimer();
        console.error('[id-photo-generate] failed:', err);
        console.error('[id-photo-generate] prepare endpoint:', prepareEndpoint);
        console.error('[id-photo-generate] compose endpoint:', composeEndpoint);
        console.error('[id-photo-generate] code:', err && err.code);
        console.error('[id-photo-generate] requestId:', err && err.requestId);
        var message = '底色生成失败，请重新选择底色或重新上传照片。';
        if (err && err.code === 'SERVICE_UNAVAILABLE') {
          message = '生成服务暂不可用，请稍后重试。';
        } else if (err && err.code === 'ENDPOINT_NOT_FOUND') {
          message = '生成接口不可用，请检查本地服务。';
        } else if (err && (err.code === 'INVALID_ID_PHOTO_INPUT' || err.code === 'INVALID_INPUT_NOT_REAL_PERSON' || err.code === 'FACE_NOT_FOUND' || err.code === 'NO_FACE_DETECTED')) {
          message = '请上传清晰的真人正面照片。';
        } else if (err && err.code === 'PREPARE_FAILED') {
          message = '人像预处理失败，请重新上传清晰正面照片。';
        } else if (err && err.code === 'MASK_QUALITY_FAILED') {
          message = '人像抠图不完整，请重新上传清晰正面照片。';
        } else if (err && (err.code === 'ID_PHOTO_QUALITY_FAILED' || err.code === 'ID_PHOTO_BACKGROUND_NOT_PURE')) {
          message = '证件照生成质量未达标，请重新上传清晰正面照片。';
        } else if (err && (err.code === 'SERVICE_TIMEOUT' || err.code === 'ID_PHOTO_TIMEOUT')) {
          message = '制作时间较长，请稍后重试或重新上传。';
        } else if (err && err.message && err.message.indexOf('未检测到') >= 0) {
          message = err.message;
        } else if (err && err.message) {
          message = "错误: " + err.message;
        }
        that.setData({
          generating: false,
          processState: (err && (err.code === 'SERVICE_TIMEOUT' || err.code === 'ID_PHOTO_TIMEOUT')) ? 'timeout' : 'failed',
          statusText: message,
          preparedId: (err && err.code === 'PREPARE_FAILED') ? '' : that.data.preparedId,
          preparedKey: (err && err.code === 'PREPARE_FAILED') ? '' : that.data.preparedKey,
          resultImage: '',
          resultPreviewSrc: '',
          resultRemoteUrl: '',
          layoutImage: '',
          resultColorId: '',
          layoutColorId: '',
          canDownload: false
        });
        wx.showToast({ title: message, icon: 'none' });
      });
  },

  generateLayoutPhoto: function() {
    var that = this;
    if (!that.data.resultImage || !that.data.currentSpec) return;
    if (that.data.resultColorId !== that.data.bgColorId) {
      wx.showToast({ title: '请先生成当前底色证件照', icon: 'none' });
      return;
    }
    imageUtil.generateLayoutPhoto(that.data.resultImage, that.data.currentSpec, 4, 2, '#ffffff')
      .then(function(path) {
        that.setData({
          layoutImage: path,
          layoutColorId: that.data.resultColorId
        });
      })
      .catch(function(err) {
        console.error('[generate] layout failed:', err);
        wx.showToast({ title: '排版照生成失败', icon: 'none' });
      });
  },

  onToggleHairRetouch: function() {
    this.setData({ hairRetouch: !this.data.hairRetouch });
    if (this.data.photoSrc && !this.data.generating) {
      this.primaryAction('换底中...');
    }
  },

  primaryAction: function(statusText) {
    var that = this;
    if (this.data.generating) {
      wx.showToast({ title: '正在制作中', icon: 'none' });
      return;
    }
    if (this.data.resultImage && this.data.canDownload) {
      wx.showActionSheet({
        itemList: ['下载单张电子照', '下载六寸排版照'],
        success: function(res) {
          if (res.tapIndex === 0) {
            that.setData({ outputTab: 'photo' }, function() {
              that.savePhoto();
            });
          } else if (res.tapIndex === 1) {
            that.setData({ outputTab: 'layout' }, function() {
              that.savePhoto();
            });
          }
        }
      });
    } else {
      this.generatePhoto();
    }
  },

  savePhoto: function() {
    var that = this;
    var saveSrc = that.data.outputTab === 'layout' ? that.data.layoutImage : that.data.resultImage;
    if (!that.data.canDownload) {
      wx.showToast({ title: '请先生成可下载的证件照', icon: 'none' });
      return;
    }
    if (that.data.outputTab !== 'layout' && that.data.resultColorId !== that.data.bgColorId) {
      wx.showToast({ title: '请先生成当前底色证件照', icon: 'none' });
      that.generatePhoto();
      return;
    }
    if (that.data.outputTab === 'layout' && that.data.layoutColorId !== that.data.bgColorId) {
      wx.showLoading({ title: '正在生成排版照' });
      imageUtil.generateLayoutPhoto(that.data.resultImage, that.data.currentSpec, 4, 2, '#ffffff')
        .then(function(path) {
          wx.hideLoading();
          that.setData({ layoutImage: path, layoutColorId: that.data.resultColorId }, function() {
            that.savePhoto();
          });
        }).catch(function(err) {
          wx.hideLoading();
          wx.showToast({ title: '排版照生成失败', icon: 'none' });
        });
      return;
    }
    if (that.data.outputTab === 'layout' && !saveSrc && that.data.resultImage) {
      wx.showLoading({ title: '正在生成排版照' });
      imageUtil.generateLayoutPhoto(that.data.resultImage, that.data.currentSpec, 4, 2, '#ffffff')
        .then(function(path) {
          wx.hideLoading();
          that.setData({ layoutImage: path, layoutColorId: that.data.resultColorId }, function() {
            that.savePhoto();
          });
        }).catch(function(err) {
          wx.hideLoading();
          wx.showToast({ title: '排版照生成失败', icon: 'none' });
        });
      return;
    }
    if (!saveSrc) {
      wx.showToast({ title: '请先生成证件照', icon: 'none' });
      return;
    }

    console.log('[id-photo-fe] download source=' + saveSrc);
    console.log('[id-photo-fe] download uses finalImageUrl=' + !!(that.data.resultImage && that.data.canDownload));

    var doSave = function(filePath) {
      wx.saveImageToPhotosAlbum({
        filePath: filePath,
        success: function() {
          wx.showToast({ title: '已保存到相册', icon: 'success' });
          var createdAt = Date.now();
          var record = {
            id: 'photo_' + createdAt,
            imagePath: filePath,
            imageUrl: that.data.outputTab === 'layout' ? '' : that.data.resultRemoteUrl,
            remoteUrl: that.data.outputTab === 'layout' ? '' : that.data.resultRemoteUrl,
            specId: that.data.currentSpecId,
            specName: that.data.specName,
            sizeText: that.data.specSize,
            bgColorName: that.data.bgColorName,
            backgroundColor: that.data.bgColorName,
            widthPx: that.data.currentSpec ? (that.data.currentSpec.widthPx || 0) : 0,
            heightPx: that.data.currentSpec ? (that.data.currentSpec.heightPx || 0) : 0,
            type: that.data.outputTab === 'layout' ? 'layout' : 'idPhoto',
            createdAt: createdAt,
            expireAt: createdAt + 24 * 3600 * 1000
          };
          var list = wx.getStorageSync('myPhotos') || [];
          list.unshift(record);
          wx.setStorageSync('myPhotos', list);
          imageService.savePhotoRecord(record);
        },
        fail: function(err) {
          if (err.errMsg.indexOf('auth') !== -1 || err.errMsg.indexOf('deny') !== -1) {
            wx.showModal({
              title: '需要权限',
              content: '请在设置中开启保存到相册权限',
              success: function(res) { if (res.confirm) wx.openSetting(); }
            });
          } else {
            wx.showToast({ title: '保存失败，请重试', icon: 'none' });
          }
        }
      });
    };

    if (saveSrc.indexOf('http') === 0) {
      wx.showLoading({ title: '准备下载...' });
      wx.downloadFile({
        url: saveSrc,
        timeout: 60000,
        success: function(res) {
          wx.hideLoading();
          if (res.statusCode === 200 && res.tempFilePath) {
            doSave(res.tempFilePath);
          } else {
            wx.showToast({ title: '下载失败，请重试', icon: 'none' });
          }
        },
        fail: function(err) {
          wx.hideLoading();
          console.error('[generate] download before save failed:', err);
          wx.showToast({ title: '下载失败，请重试', icon: 'none' });
        }
      });
      return;
    }

    doSave(saveSrc);
  }
});
