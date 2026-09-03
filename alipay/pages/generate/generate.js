var wx = require('../../utils/platform/alipayWxCompat.js');
// ====== 选择底色 / 下载证件照 ======
var specs = require('../../utils/specs.js');
var imageUtil = require('../../utils/image.js');
var aiImageApi = require('../../utils/aiImageApi.js');
var apiConfig = require('../../utils/apiConfig.js');
var edgeCompute = require('../../utils/edgeCompute.js');
var imageService = require('../../utils/imageService.js');
var idPhotoEntry = require('../../utils/idPhotoEntry.js');

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
    foregroundUrl: '',
    sourceId: '',
    detailJobId: '',
    detailJobStatus: '',
    detailProcessing: false,
    failureKind: '',
    failureMessage: '',
    elapsedSeconds: 0,
    resultImage: '',
    resultPreviewSrc: '',
    resultRemoteUrl: '',
    layoutImage: '',
    resultColorId: '',
    layoutColorId: '',
    incomingSource: ''
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

  getPreparedForegroundUrl: function(preparedId, prepared) {
    var url = prepared && prepared.foregroundUrl ? prepared.foregroundUrl : '';
    if (!url && preparedId) {
      url = '/api/id-photo/prepared/' + encodeURIComponent(preparedId) + '/foreground';
    }
    if (url && url.indexOf('http') !== 0) {
      url = apiConfig.API_BASE_URL + (url.charAt(0) === '/' ? url : '/' + url);
    }
    return url;
  },

  composePreparedResult: function(options) {
    options = options || {};
    var preparedId = options.preparedId || '';
    var foregroundUrl = options.foregroundUrl || this.data.foregroundUrl || this.getPreparedForegroundUrl(preparedId, {});
    var composeOptions = {
      preparedId: preparedId,
      foregroundUrl: foregroundUrl,
      bgColor: options.bgColor || this.data.bgColorHex,
      bgColorName: options.bgColorName || this.data.bgColorId,
      widthPx: options.widthPx || (this.data.currentSpec && this.data.currentSpec.widthPx) || 295,
      heightPx: options.heightPx || (this.data.currentSpec && this.data.currentSpec.heightPx) || 413,
      spec: this.data.currentSpec || null,
      quality: options.quality || {},
      requestId: options.requestId || ''
    };
    if (edgeCompute.chooseExecutionRoute('idPhotoBgCompose') === 'edge' && foregroundUrl) {
      return aiImageApi.composeIdPhotoEdge(composeOptions).catch(function(edgeErr) {
        console.warn('[id-photo-fe] edge compose failed, fallback to cloud:', edgeErr);
        return aiImageApi.composeIdPhotoV2({
          preparedId: preparedId,
          bgColor: composeOptions.bgColor,
          bgColorName: composeOptions.bgColorName,
          outputType: 'jpg'
        });
      });
    }
    return aiImageApi.composeIdPhotoV2({
      preparedId: preparedId,
      bgColor: composeOptions.bgColor,
      bgColorName: composeOptions.bgColorName,
      outputType: 'jpg'
    });
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
    options = options || {};
    var that = this;
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

    var channel = this.getOpenerEventChannel ? this.getOpenerEventChannel() : null;
    if (channel && channel.on) {
      channel.on('idPhotoSource', function(transfer) {
        that.handleIncomingPhoto(transfer);
      });
    }
    this.handleIncomingPhoto(idPhotoEntry.consumePendingPhoto(options.transferToken, spec.id));
  },

  onShow: function() {
    this.logCurrentPage('onShow');
    if (this.data.currentSpecId) {
      this.handleIncomingPhoto(idPhotoEntry.consumePendingPhoto('', this.data.currentSpecId));
    }
  },

  onUnload: function() {
    this.clearProcessTimer();
    this.clearElapsedTimer();
    this.stopDetailPolling();
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
      foregroundUrl: '',
      sourceId: '',
      detailJobId: '',
      detailJobStatus: '',
      detailProcessing: false,
      failureKind: '',
      failureMessage: '',
      elapsedSeconds: 0,
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

  clearElapsedTimer: function() {
    if (this.elapsedTimer) {
      clearInterval(this.elapsedTimer);
      this.elapsedTimer = null;
    }
  },

  updateProcessStage: function(processState, label) {
    var that = this;
    if (!this.processStartedAt) this.processStartedAt = Date.now();
    this.currentStageLabel = label;
    var refresh = function() {
      var elapsed = Math.max(0, Math.floor((Date.now() - that.processStartedAt) / 1000));
      that.setData({
        processState: processState,
        elapsedSeconds: elapsed,
        statusText: label + ' · 已等待' + elapsed + '秒'
      });
    };
    refresh();
    if (!this.elapsedTimer) this.elapsedTimer = setInterval(refresh, 1000);
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

  handleIncomingPhoto: function(transfer) {
    if (!transfer || !transfer.tempFilePath) return;
    if (transfer.specId && this.data.currentSpecId && transfer.specId !== this.data.currentSpecId) {
      idPhotoEntry.clearPendingPhoto(transfer.token);
      return;
    }
    var identity = transfer.token || transfer.tempFilePath;
    if (this.lastIncomingPhotoIdentity === identity) return;
    this.lastIncomingPhotoIdentity = identity;
    idPhotoEntry.clearPendingPhoto(transfer.token);
    this.acceptIncomingPhoto(transfer.tempFilePath, transfer.source, identity);
  },

  acceptIncomingPhoto: function(tempFilePath, source, identity) {
    var that = this;
    if (!tempFilePath || typeof tempFilePath !== 'string') {
      this.lastIncomingPhotoIdentity = '';
      wx.showToast({ title: '照片无效，请重新选择', icon: 'none' });
      return;
    }
    var applyPhoto = function() {
      var oldJobId = that.data.detailJobId;
      that.currentGenerateToken = 'source_changed_' + Date.now();
      that.clearProcessTimer();
      that.clearElapsedTimer();
      that.stopDetailPolling();
      if (oldJobId && that.data.detailProcessing) aiImageApi.cancelIdPhotoDetailJob(oldJobId);
      that.idPhotoCropCache = null;
      that.setData({
        photoSrc: tempFilePath,
        incomingSource: source === 'camera' ? 'camera' : 'album',
        outputTab: 'photo',
        generating: false,
        processState: 'idle',
        statusText: '照片已载入，正在制作',
        preparedId: '',
        preparedKey: '',
        sourceId: '',
        detailJobId: '',
        detailJobStatus: '',
        detailProcessing: false,
        failureKind: '',
        failureMessage: '',
        elapsedSeconds: 0,
        resultImage: '',
        resultPreviewSrc: '',
        resultRemoteUrl: '',
        layoutImage: '',
        resultColorId: '',
        layoutColorId: '',
        canDownload: false
      }, function() {
        that.generatePhoto();
      });
    };
    if (/^(https?:|wxfile:|tmp:)/.test(tempFilePath) || !wx.getFileSystemManager) {
      applyPhoto();
      return;
    }
    wx.getFileSystemManager().access({
      path: tempFilePath,
      success: applyPhoto,
      fail: function() {
        if (that.lastIncomingPhotoIdentity === identity) that.lastIncomingPhotoIdentity = '';
        wx.showToast({ title: '照片已失效，请重新选择', icon: 'none' });
      }
    });
  },

  choosePhoto: function() {
    var that = this;
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album'],
      success: function(res) {
        var file = res.tempFiles && res.tempFiles[0];
        if (!file || !file.tempFilePath) return;
        that.handleIncomingPhoto(idPhotoEntry.createPhotoTransfer(file.tempFilePath, 'album', that.data.currentSpecId));
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
    idPhotoEntry.openCustomCamera(this.data.currentSpecId, {
      custom: this.data.currentSpecId === 'custom_pass',
      returnMode: 'replace',
      success: function(res) {
        if (res && res.eventChannel && res.eventChannel.on) {
          res.eventChannel.on('idPhotoSource', function(transfer) {
            that.handleIncomingPhoto(transfer);
          });
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
    that.processStartedAt = Date.now();
    that.clearElapsedTimer();

    that.setData({
      generating: true,
      processState: hasPrepared ? 'composing' : 'optimizing',
      statusText: hasPrepared ? ((typeof statusText === 'string' ? statusText : null) || '正在生成底色') : '正在优化上传图片',
      failureKind: '',
      failureMessage: '',
      resultImage: '',
      resultPreviewSrc: '',
      resultRemoteUrl: '',
      layoutImage: '',
      resultColorId: '',
      layoutColorId: '',
      canDownload: false
    });
    that.startProcessTimer(30000);
    that.updateProcessStage(hasPrepared ? 'composing' : 'optimizing', hasPrepared ? '正在生成底色' : '正在优化上传图片');
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
      ? Promise.resolve({ preparedId: that.data.preparedId, sourceId: that.data.sourceId })
      : aiImageApi.prepareIdPhotoV2(requestPhotoSrc, Object.assign({}, requestPayload, {
          onStage: function(stage) {
            var labels = {
              optimizing: ['optimizing', '正在优化上传图片'],
              uploading: ['uploading', '正在上传照片'],
              fastMatting: ['fastMatting', '正在快速抠图']
            };
            var next = labels[stage];
            if (next) that.updateProcessStage(next[0], next[1]);
          }
        }));
    var composePayload = {
      bgColor: requestBgColorHex,
      bgColorName: requestBgColorId,
      outputType: 'jpg'
    };
    var composeWithRetry = function(preparedId, attempt) {
      that.updateProcessStage('composing', '?????????');
      return that.composePreparedResult(Object.assign({}, composePayload, {
        preparedId: preparedId,
        foregroundUrl: that.getPreparedForegroundUrl(preparedId, { foregroundUrl: that.data.foregroundUrl })
      })).catch(function(err) {
        var isExpired = err && (err.code === 'PREPARED_NOT_FOUND' || err.code === 'ID_PHOTO_PREPARED_EXPIRED' || err.code === 'PREPARED_ID_INVALID' || (err.message && (err.message.indexOf('?????') >= 0 || err.message.indexOf('???') >= 0)));
        if (isExpired && hasPrepared && attempt === 0) {
          console.warn('[id-photo-fe] preparedId expired or invalid, re-preparing source...');
          hasPrepared = false;
          that.setData({ preparedId: '', preparedKey: '', foregroundUrl: '' });
          return aiImageApi.prepareIdPhotoV2(requestPhotoSrc, Object.assign({}, requestPayload, {
            onStage: function(stage) {
              var labels = {
                optimizing: ['optimizing', 'optimizing upload'],
                uploading: ['uploading', 'uploading photo'],
                fastMatting: ['fastMatting', 'fast matting']
              };
              var next = labels[stage];
              if (next) that.updateProcessStage(next[0], next[1]);
            }
          })).then(function(newPrepared) {
            if (!newPrepared || !newPrepared.preparedId) {
              throw err;
            }
            that.setData({
              preparedId: newPrepared.preparedId,
              preparedKey: prepareKey,
              sourceId: newPrepared.sourceId || that.data.sourceId,
              foregroundUrl: that.getPreparedForegroundUrl(newPrepared.preparedId, newPrepared)
            });
            return composeWithRetry(newPrepared.preparedId, attempt + 1);
          });
        }
        var retryable = err && (err.code === 'SERVICE_TIMEOUT' || err.code === 'ID_PHOTO_TIMEOUT' || err.code === 'SERVICE_UNAVAILABLE');
        if (!retryable || attempt >= 1) {
          throw err;
        }
        console.warn('[id-photo-fe] compose retry requestId=' + (err.requestId || '') + ' attempt=' + (attempt + 1));
        that.setData({
          processState: 'composing',
          statusText: '?????????????????..'
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
        that.setData({
          preparedId: prepared.preparedId,
          preparedKey: prepareKey,
          sourceId: prepared.sourceId || that.data.sourceId,
          foregroundUrl: that.getPreparedForegroundUrl(prepared.preparedId, prepared)
        });
        that.updateProcessStage('cropping', '正在调整证件照比例');
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
        var fastWarningAccepted = result.quality && result.quality.fastWarningAccepted === true;
        if (qualityReport && qualityReport.passed === false && !fastWarningAccepted) {
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
        that.updateProcessStage('previewing', '正在加载预览');
        that.clearProcessTimer();
        that.clearElapsedTimer();
        var totalClientMs = Date.now() - that.processStartedAt;
        console.log('[id-photo-speed] composeMs=' + Number((result.performance && result.performance.composeMs) || 0));
        console.log('[id-photo-speed] previewLoadMs=' + Number((result.performance && result.performance.downloadMs) || 0));
        console.log('[id-photo-speed] totalClientMs=' + totalClientMs);
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
          if (that.data.hairRetouch) that.startDetailRetouch();
        });
      })
      .catch(function(err) {
        if (err && err.silent) return;
        that.clearProcessTimer();
        that.clearElapsedTimer();
        console.error('[id-photo-generate] failed:', err);
        console.error('[id-photo-generate] prepare endpoint:', prepareEndpoint);
        console.error('[id-photo-generate] compose endpoint:', composeEndpoint);
        console.error('[id-photo-generate] code:', err && err.code);
        console.error('[id-photo-generate] requestId:', err && err.requestId);
        console.error('[id-photo-generate] diagnostic:', err && err.diagnostic ? err.diagnostic : null);
        var message = '底色生成失败，请重新选择底色或重新上传照片。';
        var failureKind = '';
        if (err && err.code === 'CONTENT_SAFETY_REJECTED') {
          message = '图片内容不符合平台规范，请更换图片后重试。';
        } else if (err && err.code === 'CONTENT_SAFETY_PENDING') {
          message = '图片安全检测暂未完成，请稍后重试。';
        } else if (err && (err.code === 'CONTENT_SAFETY_UNAVAILABLE' || err.code === 'CONTENT_SAFETY_AUTH_REQUIRED' || err.code === 'CONTENT_SAFETY_OPENID_REQUIRED')) {
          message = '图片安全检测暂时不可用，请稍后重试。';
        } else if (err && err.code === 'SERVICE_UNAVAILABLE') {
          message = '生成服务暂不可用，请稍后重试。';
        } else if (err && err.code === 'ENDPOINT_NOT_FOUND') {
          message = '生成接口不可用，请检查本地服务。';
        } else if (err && (err.code === 'INVALID_ID_PHOTO_INPUT' || err.code === 'INVALID_INPUT_NOT_REAL_PERSON' || err.code === 'FACE_NOT_FOUND' || err.code === 'NO_FACE_DETECTED')) {
          message = '请上传清晰的真人正面照片。';
        } else if (err && err.code === 'PREPARE_FAILED') {
          message = '人像预处理失败，请重新上传清晰正面照片。';
        } else if (err && err.code === 'MASK_QUALITY_FAILED') {
          message = '人像抠图不完整，请重新上传清晰正面照片。';
        } else if (err && err.code === 'ID_PHOTO_FAST_BLOCKED') {
          if (that.data.hairRetouch && err.sourceId) {
            that.setData({
              generating: false,
              processState: 'detailSwitching',
              statusText: '已为你切换到更精细的人像处理，请稍候',
              sourceId: err.sourceId,
              failureKind: '',
              failureMessage: '',
              resultImage: '',
              resultPreviewSrc: '',
              resultRemoteUrl: '',
              layoutImage: '',
              resultColorId: '',
              layoutColorId: '',
              canDownload: false
            }, function() {
              that.startDetailRetouch(err.sourceId, { automatic: true });
            });
            return;
          }
          failureKind = 'fastBlocked';
          message = '本次照片自动优化未达到证件照标准';
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
          failureKind: failureKind,
          failureMessage: failureKind === 'fastBlocked' ? '为了尽量帮你生成合格证件照，建议更换更清晰的正面照片，或继续使用发丝精修。' : message,
          sourceId: (err && err.sourceId) || that.data.sourceId,
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
        if (failureKind !== 'fastBlocked') wx.showToast({ title: message, icon: 'none' });
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

  stopDetailPolling: function() {
    if (this.detailPollTimer) {
      clearTimeout(this.detailPollTimer);
      this.detailPollTimer = null;
    }
  },

  startDetailRetouch: function(sourceIdOverride, options) {
    var that = this;
    options = options || {};
    if (that.data.detailProcessing) return;
    var sourceId = sourceIdOverride || that.data.sourceId;
    if (!sourceId && !that.data.preparedId) {
      wx.showToast({ title: '请先上传照片完成快速处理', icon: 'none' });
      return;
    }
    that.stopDetailPolling();
    that.detailStartedAt = Date.now();
    that.setData({
      detailProcessing: true,
      detailJobStatus: 'queued',
      processState: 'detailProcessing',
      failureKind: '',
      failureMessage: '',
      statusText: options.automatic ? '已为你切换到更精细的人像处理，请稍候' : '正在进行发丝精修，请稍候'
    });
    aiImageApi.createIdPhotoDetailJob({
      preparedId: that.data.preparedId,
      sourceId: sourceId,
      fastPreviewUrl: that.data.resultRemoteUrl || ''
    }).then(function(job) {
      that.setData({ detailJobId: job.jobId, detailJobStatus: job.status || 'queued' });
      that.pollDetailRetouch(job.jobId);
    }).catch(function(err) {
      console.error('[id-photo-detail] create failed:', err);
      that.setData({
        detailProcessing: false,
        detailJobStatus: 'failed',
        processState: that.data.resultImage ? 'ready' : 'detailFailed',
        failureKind: that.data.resultImage ? '' : 'detailFailed',
        failureMessage: that.data.resultImage ? '' : '精细人像处理暂未完成，请稍后重试或更换一张清晰正面照片。',
        statusText: that.data.resultImage ? (that.data.bgColorName + ' · 快速结果可下载') : '精细人像处理暂未完成'
      });
      if (that.data.resultImage) wx.showToast({ title: '精修暂未完成，已保留快速结果', icon: 'none' });
    });
  },

  pollDetailRetouch: function(jobId) {
    var that = this;
    if (!jobId || !that.data.detailProcessing || that.data.detailJobId !== jobId) return;
    aiImageApi.getIdPhotoDetailJob(jobId).then(function(job) {
      if (!that.data.detailProcessing || that.data.detailJobId !== jobId) return;
      var elapsed = Math.max(0, Math.floor((Date.now() - that.detailStartedAt) / 1000));
      if (job.status === 'queued' || job.status === 'running') {
        that.setData({
          detailJobStatus: job.status,
          statusText: (job.status === 'queued' ? '发丝精修排队中' : '发丝精修中') + ' · 已等待' + elapsed + '秒'
        });
        that.detailPollTimer = setTimeout(function() { that.pollDetailRetouch(jobId); }, 2500);
        return;
      }
      if (job.status === 'completed' && job.preparedId) {
        that.setData({ detailJobStatus: 'completed', statusText: '正在生成精修底色' });
        return that.composePreparedResult({
          preparedId: job.preparedId,
          foregroundUrl: that.getPreparedForegroundUrl(job.preparedId, {}),
          bgColor: that.data.bgColorHex,
          bgColorName: that.data.bgColorId,
          outputType: 'jpg'
        }).then(function(result) {
          if (!that.data.detailProcessing || that.data.detailJobId !== jobId) return;
          that.setData({
            detailProcessing: false,
            detailJobStatus: 'completed',
            processState: 'ready',
            failureKind: '',
            failureMessage: '',
            preparedId: job.preparedId,
            resultImage: result.tempFilePath,
            resultPreviewSrc: result.previewUrl || result.finalImageUrl || result.tempFilePath,
            resultRemoteUrl: result.finalImageUrl || result.remoteUrl || '',
            resultColorId: that.data.bgColorId,
            layoutImage: '',
            layoutColorId: '',
            canDownload: true,
            statusText: that.data.bgColorName + ' · 发丝精修完成'
          });
        }).catch(function(err) {
          console.error('[id-photo-detail] compose failed:', err);
          that.setData({
            detailProcessing: false,
            detailJobStatus: 'failed',
            processState: that.data.resultImage ? 'ready' : 'detailFailed',
            failureKind: that.data.resultImage ? '' : 'detailFailed',
            failureMessage: that.data.resultImage ? '' : '精细人像处理结果暂未达到证件照标准，请更换一张清晰正面照片后重试。',
            statusText: that.data.resultImage ? (that.data.bgColorName + ' · 快速结果可下载') : '精细人像处理暂未达到标准'
          });
          if (that.data.resultImage) wx.showToast({ title: '精修暂未完成，已保留快速结果', icon: 'none' });
        });
      }
      that.setData({
        detailProcessing: false,
        detailJobStatus: job.status || 'failed',
        processState: that.data.resultImage ? 'ready' : 'detailFailed',
        failureKind: that.data.resultImage ? '' : 'detailFailed',
        failureMessage: that.data.resultImage ? '' : '精细人像处理暂未完成，请更换一张清晰正面照片后重试。',
        statusText: that.data.resultImage ? (that.data.bgColorName + ' · 快速结果可下载') : '精细人像处理暂未完成'
      });
      if (job.status === 'failed' && that.data.resultImage) wx.showToast({ title: '精修暂未完成，已保留快速结果', icon: 'none' });
    }).catch(function(err) {
      console.error('[id-photo-detail] poll failed:', err);
      if (!that.data.detailProcessing || that.data.detailJobId !== jobId) return;
      that.detailPollTimer = setTimeout(function() { that.pollDetailRetouch(jobId); }, 2500);
    });
  },

  onToggleHairRetouch: function() {
    var enabled = !this.data.hairRetouch;
    var jobId = this.data.detailJobId;
    var that = this;
    this.setData({ hairRetouch: enabled }, function() {
      if (enabled && that.data.photoSrc && !that.data.generating) {
        if (that.data.sourceId || that.data.preparedId) that.startDetailRetouch();
        else that.generatePhoto();
      }
    });
    if (!enabled && this.data.detailProcessing) {
      this.stopDetailPolling();
      this.setData({
        detailProcessing: false,
        detailJobStatus: 'cancelled',
        processState: this.data.resultImage ? 'ready' : 'idle',
        failureKind: '',
        failureMessage: '',
        statusText: this.data.resultImage ? (this.data.bgColorName + ' · 快速结果可下载') : '已取消发丝精修'
      });
      if (jobId) aiImageApi.cancelIdPhotoDetailJob(jobId);
    }
  },

  useHairRetouch: function() {
    if (this.data.detailProcessing) return;
    var that = this;
    this.setData({ hairRetouch: true, failureKind: '', failureMessage: '' }, function() {
      if (that.data.sourceId || that.data.preparedId) that.startDetailRetouch('', { automatic: true });
      else that.generatePhoto();
    });
  },

  retryDetailRetouch: function() {
    if (this.data.detailProcessing) return;
    this.setData({ failureKind: '', failureMessage: '' });
    this.startDetailRetouch('', { automatic: true });
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
