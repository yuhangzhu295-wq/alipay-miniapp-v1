var wx = require('../../utils/platform/alipayWxCompat.js');
// ====== 统一工具详情页 ======
var specs = require('../../utils/specs.js');
var imgSvc = require('../../utils/imageService.js');
var segApi = require('../../utils/segmentationApi.js');
var inpaintApi = require('../../utils/inpaintApi.js');
var compress = require('../../utils/compressImage.js');
var bgReplace = require('../../utils/backgroundReplace.js');
var watermarkApi = require('../../utils/watermarkApi.js');
var apiConfig = require('../../utils/apiConfig.js');
var aiImageApi = require('../../utils/aiImageApi.js');
var professionalApi = require('../../utils/professionalApi.js');
var idPhotoEntry = require('../../utils/idPhotoEntry.js');
var edgeCompute = require('../../utils/edgeCompute.js');

var TOOL_CONFIGS = {
  verifyPhoto: { title: 'AI 证件照质检', icon: '🔍' },
  changeBg: { title: '证件照更换底色', icon: '🎨' },
  customSize: { title: '自定义尺寸', icon: '📐' },
  editImage: { title: '图片编辑', icon: '✏️' },
  formatConvert: { title: '图片格式转换', icon: '🔄' },
  colorize: { title: '黑白图片上色', icon: '🎭' },
  addWatermark: { title: '图片加水印', icon: '💧' },
  removeWatermark: { title: '图片去水印', icon: '🧹' },
  layout: { title: '自定义排版', icon: '🧩' },
  professional: { title: '职业形象照', icon: '👔' },
  collect: { title: '证件照采集', icon: '📷' }
};

Page({
  data: {
    toolType: '',
    toolTitle: '',
    toolIcon: '',
    photoSrc: '',

    // ========== STRING INPUT MODEL (fix: never parseInt in onInput) ==========

    // VerifyPhoto
    auditResult: null,
    auditModel: 'minicpm-v:latest',

    // ChangeBg
    bgColors: [
      { id: 'blue', name: '蓝色', hex: '#1a73e8', r: 26, g: 115, b: 232 },
      { id: 'white', name: '白色', hex: '#ffffff', r: 255, g: 255, b: 255 },
      { id: 'red', name: '红色', hex: '#e53935', r: 229, g: 57, b: 53 },
      { id: 'lightBlue', name: '浅蓝色', hex: '#81d4fa', r: 129, g: 212, b: 250 },
      { id: 'gray', name: '灰色', hex: '#9e9e9e', r: 158, g: 158, b: 158 },
      { id: 'custom', name: '自定义', hex: '#1a73e8', r: 26, g: 115, b: 232 }
    ],
    detectSrcBg: 'auto',
    selBgIdx: 0,
    bgMode: 'ai', // local | ai (默认AI抠图)
    resultImage: '',
    idPhotoPurposes: specs.purposeOptions,
    idPhotoSpecs: [],
    idPhotoCompositions: specs.compositionOptions,
    idPhotoEnhanceOptions: specs.enhanceOptions,
    idPhotoAllOutfits: specs.outfitOptions,
    idPhotoOutfits: specs.outfitOptions.filter(function(item) { return item.id === 'preserve_original'; }),
    idPhotoCapabilityLoaded: false,
    advancedOutfitEnabled: specs.advancedOutfitEnabled === true,
    idPhotoPurpose: 'official_id_photo',
    idPhotoSpecId: 'one-inch',
    idPhotoSpecIndex: 0,
    idPhotoSpecName: '一寸照',
    idPhotoComposition: 'head_shoulder',
    idPhotoEnhance: 'standard',
    hairRetouch: false,
    idPhotoOutfit: 'preserve_original',
    customBgHex: '#1a73e8',
    imageTypeInfo: null,
    imageTypeLabel: '未识别',
    idPhotoResultMeta: null,

    // CustomSize — STRING INPUTS
    widthPxInput: '295',
    heightPxInput: '413',
    widthMmInput: '25',
    heightMmInput: '35',

    // EditImage — STRING INPUTS
    quality: 80,
    targetKbInput: '200',
    cropRatio: 'free',

    // FormatConvert
    targetFormat: 'jpg',

    // Colorize
    colorFilter: 'warm',

    // AddWatermark
    watermarkText: '仅限本人使用',
    watermarkOpacity: 35,
    watermarkPos: 'rightBottom',
    watermarkSize: 32,

    // RemoveWatermark — STRING INPUTS
    selXInput: '60',
    selYInput: '60',
    selWInput: '120',
    selHInput: '80',
    selectRect: null,
    removeMode: 'blur',
    wmMode: 'manual', // manual | stamp
    wmDisplayWidth: 320,
    wmDisplayHeight: 320,
    wmBrushSize: 20,
    wmStrength: 'medium',
    wmQuality: 'fast',
    wmHasMask: false,
    wmMaskPreview: '',
    wmMaskWidth: 0,
    wmMaskHeight: 0,
    wmMaskNonZeroPixels: 0,
    wmMaskRatio: '0.00',
    wmMaskRatioValue: 0,
    wmBackendDebug: {},
    wmClientPerformance: {},
    wmApiBaseUrl: watermarkApi.getBaseUrl(),
    wmHealthStatus: '未检测',
    wmHdEnabled: watermarkApi.isHdRepairEnabled(),
    wmHdAvailable: false,
    wmHdStatus: '未检测',
    wmUploadUrl: watermarkApi.getBaseUrl() + '/api/watermark/remove-v2',
    wmLastError: '-',
    wmResultQuality: '',
    wmResultModeLabel: '',
    wmResultMessage: '',
    manualResultUrl: '',
    quickResultUrl: '',
    hdResultUrl: '',
    manualResultLocalPath: '',
    quickResultLocalPath: '',
    hdResultLocalPath: '',
    currentWatermarkMode: '',
    currentResultUrl: '',
    currentResultLocalPath: '',
    currentEngine: '',
    currentOutputPath: '',
    currentFileHash: '',
    wmStampSampling: false,
    wmStampSampleSet: false,
    wmStampSampleX: -1,
    wmStampSampleY: -1,
    wmCanvasInitFailed: false,
    // Layout — MULTI IMAGE
    layoutImages: [],      // [{path, label}]
    layoutCols: 4,
    layoutRows: 2,
    layoutGap: 8,
    layoutMargin: 40,
    layoutBgColor: '#ffffff',

    // Professional
    profTemplate: 'preserve_original',

    // Compress result detail
    compressResult: null,

    // Collect
    collectSpecList: [],
    collectSelSpecId: '',
    collectList: [],

    processing: false,
    processingText: '处理中...',

    // ===== 开发诊断面板 =====
    diagApiBaseUrl: apiConfig.API_BASE_URL,
    diagEnableAi: apiConfig.ENABLE_AI,
    diagHealthStatus: '未检测',
    diagMethod: '-',
    diagUrl: '-',
    diagParams: '-',
    diagLastSuccess: '-',
    diagLastMessage: '-',
    diagScore: '-',
    diagActualKB: '-',
    diagBackendMode: '-',
    diagOriginalPath: '-',
    diagResultPath: '-',
    diagIsEqual: '-',
    diagResultDiffer: true,
    isDevelopEnv: false,
    showDebugPanel: false,
    debugTitleTapCount: 0
  },

  onLoad: function(options) {
    var type = options.type || 'changeBg';
    var config = TOOL_CONFIGS[type];
    if (!config) { config = TOOL_CONFIGS.changeBg; type = 'changeBg'; }
    var isDevelopEnv = this.isDebugPanelAllowed();
    var showDebugPanel = false;
    try {
      var storedDebugPanel = wx.getStorageSync('showDebugPanel');
      showDebugPanel = isDevelopEnv && (storedDebugPanel === true || storedDebugPanel === 'true');
      if (!isDevelopEnv && storedDebugPanel) {
        wx.removeStorageSync('showDebugPanel');
      }
    } catch (err) {
      console.error('[debug] failed to read debug panel setting:', err);
    }
    wx.setNavigationBarTitle({ title: config.title });
    this.setData({
      toolType: type,
      toolTitle: config.title,
      toolIcon: config.icon,
      isDevelopEnv: isDevelopEnv,
      showDebugPanel: showDebugPanel,
      debugTitleTapCount: 0
    });
    if (type === 'changeBg' || type === 'professional') { this.initIdPhotoOptions(type); }
    if (type === 'customSize' || type === 'collect') { this.loadSpecsForCollect(); }
    if (type === 'removeWatermark') { this.checkWatermarkHealth(); }
  },

  onShow: function() {
    var isDevelopEnv = this.isDebugPanelAllowed();
    if (!isDevelopEnv) {
      this.setData({ isDevelopEnv: false, showDebugPanel: false, debugTitleTapCount: 0 });
    } else if (!this.data.isDevelopEnv) {
      this.setData({ isDevelopEnv: true });
    }
    if (isDevelopEnv && this.data.showDebugPanel) {
      // 自动检测后端健康状态
      this.runDiagHealthCheck();
    }
    if (this.data.toolType === 'removeWatermark') {
      this.checkWatermarkHealth();
    }
  },

  // ========== 诊断面板 ==========
  runDiagHealthCheck: function() {
    if (!this.isDebugPanelAllowed()) { return; }
    var that = this;
    that.setData({ diagHealthStatus: '检测中...' });
    aiImageApi.checkApiAvailable().then(function() {
      that.setData({ diagHealthStatus: '✅ 已连接', diagLastMessage: 'server running' });
    }).catch(function(err) {
      that.setData({ diagHealthStatus: '❌ 未连接', diagLastMessage: (err && err.message) || '连接失败' });
    });
  },

  checkWatermarkHealth: function() {
    var that = this;
    var baseUrl = watermarkApi.getBaseUrl();
    that.setData({
      wmApiBaseUrl: baseUrl,
      wmUploadUrl: baseUrl + '/api/watermark/remove-v2',
      wmHealthStatus: '检测中...'
    });
    watermarkApi.checkHealth().then(function(res) {
      that._wmHealthModalShown = false;
      var hdEnabled = watermarkApi.isHdRepairEnabled();
      var hdAvailable = !!(
        hdEnabled &&
        res &&
        res.hdAvailable === true &&
        res.hdRealModelLoaded === true &&
        res.fallbackUsed !== true
      );
      var nextData = {
        wmHealthStatus: '已连接: ' + (res.service || 'watermark-opencv'),
        wmHdEnabled: hdEnabled,
        wmHdAvailable: hdAvailable,
        wmHdStatus: hdAvailable ? '已就绪' : (res && res.fallbackAvailable ? '模型未就绪' : '未启动'),
        wmLastError: '-'
      };
      if (!hdAvailable && that.data.wmQuality === 'hd') {
        nextData.wmQuality = 'fast';
      }
      that.setData({
        wmHealthStatus: nextData.wmHealthStatus,
        wmHdEnabled: nextData.wmHdEnabled,
        wmHdAvailable: nextData.wmHdAvailable,
        wmHdStatus: nextData.wmHdStatus,
        wmLastError: nextData.wmLastError,
        wmQuality: nextData.wmQuality || that.data.wmQuality
      });
    }).catch(function(err) {
      var errMsg = (err && err.message) || '图片处理服务未启动';
      console.error('[watermark] health check failed:', err);
      that.setData({
        wmHealthStatus: '未连接',
        wmHdAvailable: false,
        wmHdStatus: '未启动',
        wmQuality: that.data.wmQuality === 'hd' ? 'fast' : that.data.wmQuality,
        wmLastError: errMsg
      });
    });
  },

  isDebugPanelAllowed: function() {
    try {
      if (wx.getAccountInfoSync) {
        var accountInfo = wx.getAccountInfoSync();
        var envVersion = accountInfo && accountInfo.miniProgram && accountInfo.miniProgram.envVersion;
        return envVersion === 'develop';
      }
    } catch (err) {
      console.error('[debug] failed to read mini program env:', err);
    }
    return false;
  },

  onWatermarkTitleTap: function() {
    if (!this.isDebugPanelAllowed()) {
      if (this.data.showDebugPanel || this.data.debugTitleTapCount || this.data.isDevelopEnv) {
        this.setData({ isDevelopEnv: false, showDebugPanel: false, debugTitleTapCount: 0 });
      }
      return;
    }

    var that = this;
    var count = (that.data.debugTitleTapCount || 0) + 1;
    if (that._debugTitleTapTimer) {
      clearTimeout(that._debugTitleTapTimer);
    }

    if (count >= 5) {
      var nextVisible = !that.data.showDebugPanel;
      that.setData({
        showDebugPanel: nextVisible,
        debugTitleTapCount: 0
      });
      try {
        wx.setStorageSync('showDebugPanel', nextVisible);
      } catch (err) {
        console.error('[debug] failed to save debug panel setting:', err);
      }
      wx.showToast({
        title: nextVisible ? '调试面板已开启' : '调试面板已隐藏',
        icon: 'none'
      });
      if (nextVisible) {
        that.runDiagHealthCheck();
        if (that.data.toolType === 'removeWatermark') {
          that.checkWatermarkHealth();
        }
      }
      return;
    }

    that.setData({ debugTitleTapCount: count });
    that._debugTitleTapTimer = setTimeout(function() {
      that.setData({ debugTitleTapCount: 0 });
    }, 1200);
  },

  getWatermarkUserError: function(err, fallback) {
    var msg = (err && err.message) || String(err || '');
    var code = (err && err.code) || '';
    if (code === 'CONTENT_SAFETY_REJECTED' || msg.indexOf('图片内容不符合平台规范') >= 0) {
      return '图片内容不符合平台规范，请更换图片后重试。';
    }
    if (code === 'CONTENT_SAFETY_PENDING' || msg.indexOf('图片安全检测暂未完成') >= 0) {
      return '图片安全检测暂未完成，请稍后重试。';
    }
    if (code === 'CONTENT_SAFETY_UNAVAILABLE' || code === 'CONTENT_SAFETY_AUTH_REQUIRED' || code === 'CONTENT_SAFETY_OPENID_REQUIRED' || msg.indexOf('图片安全检测暂时不可用') >= 0) {
      return '图片安全检测暂时不可用，请稍后重试。';
    }
    var lowerMsg = msg.toLowerCase();
    if (msg.indexOf('遮罩为空') >= 0 || msg.indexOf('全黑') >= 0 || msg.indexOf('涂抹') >= 0 || msg.indexOf('mask empty') >= 0 || msg.indexOf('nonZero') >= 0) {
      return '请先涂抹需要去除的水印区域。';
    }
    if (msg.indexOf('高清修复服务') >= 0 || msg.indexOf('hd repair unavailable') >= 0 || msg.indexOf('IOPaint') >= 0) {
      return '高清修复服务暂不可用，可先使用快速模式。';
    }
    if (msg.indexOf('模型') >= 0 || msg.indexOf('model') >= 0 || msg.indexOf('lama') >= 0 || msg.indexOf('LaMa') >= 0) {
      return '高清修复模型未就绪，请检查本地高清修复服务。';
    }
    if (lowerMsg.indexOf('econnrefused') >= 0 || msg.indexOf('未启动') >= 0 || msg.indexOf('端口') >= 0 || msg.indexOf('连接失败') >= 0 || msg.indexOf('不可访问') >= 0) {
      return '图片处理服务暂不可用，请稍后重试。';
    }
    if ((msg.indexOf('高清') >= 0 || msg.indexOf('hd') >= 0) && (lowerMsg.indexOf('timeout') >= 0 || msg.indexOf('超时') >= 0)) {
      return '高清修复耗时较长，请稍后重试或切换快速模式。';
    }
    if (lowerMsg.indexOf('timeout') >= 0 || msg.indexOf('超时') >= 0) {
      return '图片处理服务响应超时，请稍后重试。';
    }
    if (lowerMsg.indexOf('uploadfile') >= 0 || msg.indexOf('上传') >= 0) {
      return '图片上传失败，请重新尝试。';
    }
    if (lowerMsg.indexOf('domain') >= 0 || msg.indexOf('域名') >= 0) {
      return '图片上传失败，请重新尝试。';
    }
    return fallback || '处理失败，请调整涂抹区域后重试。';
  },

  diagTestRemoveBg: function() {
    if (!this.isDebugPanelAllowed()) { return; }
    var that = this;
    if (!that.data.photoSrc) { wx.showToast({ title: '请先上传图片', icon: 'none' }); return; }
    that.setData({ diagLastApi: 'POST /api/remove-bg', diagLastSuccess: '请求中...' });
    aiImageApi.removeBg(that.data.photoSrc).then(function(rp) {
      var isSame = (rp === that.data.photoSrc);
      that.setData({
        diagLastSuccess: isSame ? '⚠️ 但结果=原图' : '✅ true',
        diagResultIsOriginal: isSame ? '⚠️ 是（resultPath === originalPath）' : '✅ 否（不同）',
        diagResultDiffer: !isSame
      });
    }).catch(function(err) {
      that.setData({
        diagLastSuccess: '❌ false',
        diagLastMessage: (err && err.message) || '失败',
        diagResultIsOriginal: '-'
      });
    });
  },

  diagTestChangeBg: function() {
    if (!this.isDebugPanelAllowed()) { return; }
    var that = this;
    if (!that.data.photoSrc) { wx.showToast({ title: '请先上传图片', icon: 'none' }); return; }
    that.setData({ diagLastApi: 'POST /api/change-bg', diagLastSuccess: '请求中...' });
    aiImageApi.changeBg(that.data.photoSrc, 'white').then(function(rp) {
      var isSame = (rp === that.data.photoSrc);
      that.setData({
        diagLastSuccess: isSame ? '⚠️ 但结果=原图' : '✅ true',
        diagResultIsOriginal: isSame ? '⚠️ 是（resultPath === originalPath）' : '✅ 否（不同）',
        diagResultDiffer: !isSame
      });
    }).catch(function(err) {
      that.setData({
        diagLastSuccess: '❌ false',
        diagLastMessage: (err && err.message) || '失败',
        diagResultIsOriginal: '-'
      });
    });
  },

  diagTestInpaint: function() {
    if (!this.isDebugPanelAllowed()) { return; }
    var that = this;
    if (!that.data.photoSrc) { wx.showToast({ title: '请先上传图片', icon: 'none' }); return; }
    if (!that.data.selectRect) { wx.showToast({ title: '请先框选水印区域', icon: 'none' }); return; }
    var r = that.data.selectRect;
    that.setData({ diagLastApi: 'POST /api/inpaint', diagLastSuccess: '请求中...' });

    wx.getImageInfo({
      src: that.data.photoSrc,
      success: function(info) {
        var imgW = info.width, imgH = info.height;
        var displayW = 350;
        var displayScale = imgW / displayW;

        var rx = Math.floor(Math.max(0, r.x) * displayScale);
        var ry = Math.floor(Math.max(0, r.y) * displayScale);
        var rw = Math.floor(r.w * displayScale);
        var rh = Math.floor(r.h * displayScale);

        // Clamp values
        rx = Math.min(rx, Math.max(0, imgW - 1));
        ry = Math.min(ry, Math.max(0, imgH - 1));
        rw = Math.max(1, Math.min(rw, imgW - rx));
        rh = Math.max(1, Math.min(rh, imgH - ry));

        inpaintApi.removeWatermarkByAI({
          imagePath: that.data.photoSrc,
          rect: { x: rx, y: ry, w: rw, h: rh }
        }).then(function(resObj) {
          var rp = resObj.tempFilePath;
          var isSame = (rp === that.data.photoSrc);
          that.setData({
            diagLastSuccess: isSame ? '⚠️ 但结果=原图' : '✅ true',
            diagResultIsOriginal: isSame ? '⚠️ 是（resultPath === originalPath）' : '✅ 否（不同）',
            diagResultDiffer: !isSame,
            resultImage: rp
          });
        }).catch(function(err) {
          that.setData({
            diagLastSuccess: '❌ false',
            diagLastMessage: (err && err.message) || '失败',
            diagResultIsOriginal: '-'
          });
        });
      },
      fail: function() {
        that.setData({
          diagLastSuccess: '❌ false',
          diagLastMessage: '获取图片信息失败',
          diagResultIsOriginal: '-'
        });
      }
    });
  },

  diagTestVerifyPhoto: function() {
    if (!this.isDebugPanelAllowed()) { return; }
    var that = this;
    if (!that.data.photoSrc) { wx.showToast({ title: '请先上传图片', icon: 'none' }); return; }
    that.setData({ diagLastApi: 'POST /api/verify-photo', diagLastSuccess: '请求中...' });
    aiImageApi.verifyPhoto(that.data.photoSrc, that.data.auditModel).then(function(res) {
      that.setData({
        diagLastSuccess: '✅ true',
        diagLastMessage: '评分: ' + res.score + ' | 合规: ' + res.qualified,
        diagResultIsOriginal: '否（返回质检报告JSON）'
      });
    }).catch(function(err) {
      that.setData({
        diagLastSuccess: '❌ false',
        diagLastMessage: (err && err.message) || '失败',
        diagResultIsOriginal: '-'
      });
    });
  },

  updateDiagInfo: function(opts) {
    var that = this;
    var original = opts.original || that.data.photoSrc || '-';
    var result = opts.result || '-';
    var isEqual = '否';
    var isDiffer = true;
    if (original !== '-' && result !== '-') {
      if (original === result) {
        isEqual = '是（⚠️ 结果仍为原图，处理未生效！）';
        isDiffer = false;
      } else {
        isEqual = '否（✅ 处理已生效）';
        isDiffer = true;
      }
    }
    
    that.setData({
      diagMethod: opts.method || '-',
      diagUrl: opts.url || '-',
      diagParams: opts.params ? JSON.stringify(opts.params) : '-',
      diagLastSuccess: opts.success !== undefined ? String(opts.success) : '-',
      diagLastMessage: opts.message || '-',
      diagScore: opts.score !== undefined ? String(opts.score) : '-',
      diagActualKB: opts.actualKB !== undefined ? String(opts.actualKB) : '-',
      diagBackendMode: opts.backendMode || '-',
      diagOriginalPath: original,
      diagResultPath: result,
      diagIsEqual: isEqual,
      diagResultDiffer: isDiffer
    });
  },

  // ========== UPLOAD ==========
  choosePhoto: function() {
    var that = this;
    wx.chooseMedia({
      count: 1, mediaType: ['image'], sourceType: ['album', 'camera'],
      success: function(res) {
        var path = res.tempFiles[0].tempFilePath;
        that._wmLastMaskInfo = null;
        that._wmLastStrokeInfo = null;
        that.setData({ 
          photoSrc: path, 
          resultImage: '', 
          idPhotoResultMeta: null,
          imageTypeInfo: null,
          imageTypeLabel: '识别中...',
          selectRect: null,
          auditResult: null,
          wmCanvasInitFailed: false,
          wmMaskPreview: '',
          wmMaskWidth: 0,
          wmMaskHeight: 0,
          wmMaskNonZeroPixels: 0,
          wmMaskRatio: '0.00',
          wmMaskRatioValue: 0,
          wmBackendDebug: {},
          wmResultQuality: '',
          wmResultModeLabel: '',
          wmResultMessage: '',
          manualResultUrl: '',
          quickResultUrl: '',
          hdResultUrl: '',
          manualResultLocalPath: '',
          quickResultLocalPath: '',
          hdResultLocalPath: '',
          currentWatermarkMode: '',
          currentResultUrl: '',
          currentResultLocalPath: '',
          currentEngine: '',
          currentOutputPath: '',
          currentFileHash: ''
        });
        if (that.data.toolType === 'removeWatermark') {
          setTimeout(function() {
            that.initWmCanvas();
          }, 100);
        }
        if (that.data.toolType === 'changeBg' || that.data.toolType === 'professional') {
          that.inspectPortraitType(path);
        }
      }, fail: function() {}
    });
  },

  setAuditModel: function(e) {
    this.setData({ auditModel: e.currentTarget.dataset.model });
  },

  doVerifyPhoto: function() {
    var that = this;
    if (!that.data.photoSrc) { wx.showToast({ title: '请先上传图片', icon: 'none' }); return; }

    that.setData({ processing: true, auditResult: null });

    aiImageApi.verifyPhoto(that.data.photoSrc, that.data.auditModel).then(function(res) {
      that.setData({ processing: false, auditResult: res });
      wx.showToast({ title: '质检完成', icon: 'success' });
      that.updateDiagInfo({
        method: 'POST',
        url: '/api/verify-photo',
        params: { model: that.data.auditModel },
        success: true,
        message: '质检分析成功',
        score: res.score,
        backendMode: res.is_fallback ? '高效本地质检 (Fallback)' : 'Ollama 视觉大模型质检'
      });
    }).catch(function(err) {
      that.setData({ processing: false });
      wx.showModal({
        title: '质检失败',
        content: (err && err.message) || '质检请求发生错误，请确认后端已启动且 Ollama 运行正常。',
        showCancel: false
      });
      that.updateDiagInfo({
        method: 'POST',
        url: '/api/verify-photo',
        params: { model: that.data.auditModel },
        success: false,
        message: (err && err.message) || '质检请求发生错误',
        backendMode: 'Ollama 视觉大模型质检'
      });
    });
  },

  // ====== MULTI-IMAGE UPLOAD FOR LAYOUT ======
  chooseLayoutImages: function() {
    var that = this;
    wx.chooseMedia({
      count: 9, mediaType: ['image'], sourceType: ['album', 'camera'],
      success: function(res) {
        var imgs = [];
        for (var i = 0; i < res.tempFiles.length; i++) {
          imgs.push({ path: res.tempFiles[i].tempFilePath, label: '图' + (i + 1) });
        }
        that.setData({ layoutImages: imgs });
      }, fail: function() {}
    });
  },

  removeLayoutImage: function(e) {
    var idx = e.currentTarget.dataset.idx;
    var imgs = this.data.layoutImages.slice();
    imgs.splice(idx, 1);
    this.setData({ layoutImages: imgs });
  },

  // ========== SAVE RESULT ==========
  saveResult: function() {
    var that = this;
    var src = that.data.toolType === 'removeWatermark'
      ? (that.data.currentResultLocalPath || that.data.resultImage)
      : that.data.resultImage;
    if (!src) {
      wx.showToast({ title: '请先生成结果图片', icon: 'none' });
      return;
    }
    // 确保 resultPath !== originalPath
    if (src === that.data.photoSrc) {
      wx.showToast({ title: '结果与原图相同，请重新处理', icon: 'none' });
      return;
    }
    imgSvc.saveToAlbum(src).then(function() {
      imgSvc.savePhotoRecord({
        imagePath: src,
        type: 'tool',
        title: that.data.toolTitle,
        sizeText: '工具生成'
      });
    }).catch(function() {
      wx.showToast({ title: '保存失败', icon: 'none' });
    });
  },

  // ========== CHANGE BACKGROUND ==========
  selectBg: function(e) { this.setData({ selBgIdx: parseInt(e.currentTarget.dataset.idx) }); },
  setDetectMode: function(e) { this.setData({ detectSrcBg: e.currentTarget.dataset.mode }); },
  setBgMode: function(e) { this.setData({ bgMode: e.currentTarget.dataset.mode }); },
  initIdPhotoOptions: function(type) {
    var purpose = type === 'professional' ? 'career_portrait' : 'official_id_photo';
    this.applyIdPhotoPurpose(purpose);
    this.loadIdPhotoCapabilities();
  },
  loadIdPhotoCapabilities: function() {
    var that = this;
    aiImageApi.getIdPhotoCapabilities().then(function(res) {
      var templates = res.templates || specs.outfitOptions;
      that.setData({
        idPhotoAllOutfits: templates,
        idPhotoCapabilityLoaded: true
      }, function() {
        that.refreshOutfitOptions();
      });
    }).catch(function(err) {
      console.error('[id-photo] capabilities unavailable, using local registry:', err);
      that.setData({
        idPhotoAllOutfits: specs.outfitOptions,
        idPhotoCapabilityLoaded: false
      }, function() {
        that.refreshOutfitOptions();
      });
    });
  },
  applyIdPhotoPurpose: function(purpose) {
    var that = this;
    var list = specs.getV2SpecsByPurpose(purpose);
    if (!list || !list.length) { list = specs.getV2SpecsByPurpose('official_id_photo'); }
    var first = list[0];
    var bgIdx = this.findBgIndex(first.defaultBg || 'blue');
    this.setData({
      idPhotoPurpose: purpose,
      idPhotoSpecs: list,
      idPhotoSpecId: first.id,
      idPhotoSpecIndex: 0,
      idPhotoSpecName: first.name + ' · ' + first.sizeText,
      idPhotoComposition: first.composition || 'head_shoulder',
      selBgIdx: bgIdx
    }, function() {
      that.refreshOutfitOptions();
    });
  },
  findBgIndex: function(bgId) {
    var list = this.data.bgColors || [];
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === bgId) return i;
    }
    return 0;
  },
  setIdPhotoPurpose: function(e) {
    this.applyIdPhotoPurpose(e.currentTarget.dataset.id);
    this.setData({ resultImage: '', idPhotoResultMeta: null });
  },
  onIdSpecSelect: function(e) {
    var that = this;
    var idx = parseInt(e.detail.value);
    var spec = this.data.idPhotoSpecs[idx];
    if (!spec) return;
    this.setData({
      idPhotoSpecIndex: idx,
      idPhotoSpecId: spec.id,
      idPhotoSpecName: spec.name + ' · ' + spec.sizeText,
      idPhotoComposition: spec.composition || this.data.idPhotoComposition,
      selBgIdx: this.findBgIndex(spec.defaultBg || 'blue'),
      resultImage: '',
      idPhotoResultMeta: null
    }, function() {
      that.refreshOutfitOptions();
    });
  },
  setIdPhotoComposition: function(e) {
    var that = this;
    this.setData({ idPhotoComposition: e.currentTarget.dataset.id, resultImage: '', idPhotoResultMeta: null }, function() {
      that.refreshOutfitOptions();
    });
  },
  setIdPhotoEnhance: function(e) {
    this.setData({ idPhotoEnhance: e.currentTarget.dataset.id });
  },
  onToggleHairRetouch: function() {
    this.setData({ hairRetouch: !this.data.hairRetouch });
  },
  setIdPhotoOutfit: function(e) {
    this.setData({ idPhotoOutfit: 'preserve_original' });
    wx.showToast({ title: '一键换装已移除', icon: 'none' });
  },
  onCustomBgHexInput: function(e) {
    this.setData({ customBgHex: e.detail.value || '#1a73e8' });
  },
  getImageTypeLabel: function(type) {
    var map = {
      real_person: '真人照片',
      anime: '二次元头像',
      cartoon: '卡通头像',
      illustration: '插画头像',
      object: '物体图片',
      landscape: '风景图片',
      unknown: '未知类型'
    };
    return map[type] || '未知类型';
  },
  getOutfitName: function(id) {
    var list = this.data.idPhotoOutfits || [];
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === id) return list[i].name;
    }
    return '保留原服装';
  },
  getOutfitOption: function(id) {
    var list = this.data.idPhotoOutfits || [];
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === id) return list[i];
    }
    return null;
  },
  getCompositionName: function(id) {
    var list = this.data.idPhotoCompositions || [];
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === id) return list[i].name;
    }
    return '头肩照';
  },
  isAnimeLikeType: function(type) {
    return type === 'anime' || type === 'cartoon' || type === 'illustration';
  },
  refreshOutfitOptions: function() {
    this.setData({
      idPhotoOutfits: [],
      idPhotoOutfit: 'preserve_original'
    });
  },
  getResultModeLabel: function(mode) {
    if (mode === 'official') return '官方规格版';
    if (mode === 'anime') return '二次元创意版';
    return '创意版';
  },
  inspectPortraitType: function(path) {
    var that = this;
    aiImageApi.inspectPortrait(path).then(function(res) {
      var imageType = res.imageType || (res.quality && res.quality.imageType) || 'unknown';
      that.setData({
        imageTypeInfo: res.quality || { imageType: imageType },
        imageTypeLabel: that.getImageTypeLabel(imageType)
      }, function() {
        that.refreshOutfitOptions();
      });
      if ((imageType === 'anime' || imageType === 'cartoon' || imageType === 'illustration') && that.data.idPhotoPurpose === 'official_id_photo') {
        wx.showToast({ title: '已识别为创意头像，可继续生成创意版', icon: 'none', duration: 2200 });
      }
    }).catch(function(err) {
      console.error('[portrait] inspect failed:', err);
      that.setData({ imageTypeLabel: '未识别' });
    });
  },
  buildIdPhotoPayload: function() {
    var bg = this.data.bgColors[this.data.selBgIdx] || this.data.bgColors[0];
    var purpose = specs.getPurposeById(this.data.idPhotoPurpose);
    return {
      purpose: this.data.idPhotoPurpose,
      specId: this.data.idPhotoSpecId,
      bgColor: bg.id === 'custom' ? this.data.customBgHex : bg.id,
      imageType: this.data.imageTypeInfo ? this.data.imageTypeInfo.imageType : '',
      mode: purpose.mode || 'official',
      composition: this.data.idPhotoComposition,
      outfit: this.data.advancedOutfitEnabled === true ? this.data.idPhotoOutfit : 'preserve_original',
      enhanceLevel: this.data.idPhotoEnhance,
      outputType: 'jpg',
      hairRetouch: this.data.hairRetouch || false
    };
  },
  getBgColorName: function() {
    var bg = this.data.bgColors[this.data.selBgIdx] || this.data.bgColors[0];
    return bg.name || bg.id;
  },
  generateIdPhotoV2: function(source) {
    var that = this;
    if (!that.data.photoSrc) { wx.showToast({ title: '请先上传图片', icon: 'none' }); return; }
    var payload = that.buildIdPhotoPayload();
    var outfitOption = that.getOutfitOption(payload.outfit);
    if (outfitOption && outfitOption.disabled) {
      wx.showModal({
        title: '高级换装暂未开放',
        content: outfitOption.disabledReason || '高级换装暂未开放，请使用保留原服装模式。',
        showCancel: false
      });
      return;
    }
    var imageType = payload.imageType || 'unknown';
    var isCreativeInput = imageType === 'anime' || imageType === 'cartoon' || imageType === 'illustration';
    var run = function() {
      that.setData({ processing: true, resultImage: '', idPhotoResultMeta: null });
      aiImageApi.generateIdPhotoV2(that.data.photoSrc, payload).then(function(res) {
        that.setData({
          processing: false,
          resultImage: res.tempFilePath,
          idPhotoResultMeta: {
            mode: res.mode,
            modeLabel: ((payload.purpose === 'career_portrait' || payload.purpose === 'resume') && res.imageType === 'real_person') ? '基础版' : that.getResultModeLabel(res.mode),
            imageType: res.imageType,
            imageTypeLabel: that.getImageTypeLabel(res.imageType),
            specName: res.spec ? res.spec.name : that.data.idPhotoSpecName,
            bgColor: res.spec ? res.spec.bgColor : payload.bgColor,
            bgColorName: that.getBgColorName(),
            compositionName: that.getCompositionName(payload.composition),
            outfitName: res.outfit ? res.outfit.name : that.getOutfitName(payload.outfit),
            warnings: res.warnings || []
          }
        });
        wx.showToast({ title: source === 'professional' ? '形象照生成完成' : '生成完成', icon: 'success' });
        that.updateDiagInfo({
          method: 'POST',
          url: '/api/id-photo/generate-v2',
          params: payload,
          success: true,
          message: res.message || '生成成功',
          original: that.data.photoSrc,
          result: res.tempFilePath,
          backendMode: '规格库 + 分流生成'
        });
      }).catch(function(err) {
        console.error('[id-photo] generate failed:', err);
        var userMsg = that.getPortraitUserError(err, '生成失败，请重新上传清晰的人像照片后重试。');
        that.setData({ processing: false, resultImage: '', idPhotoResultMeta: null });
        wx.showModal({ title: '生成失败', content: userMsg, showCancel: false });
      });
    };
    if (isCreativeInput && payload.mode === 'official') {
      wx.showModal({
        title: '将生成创意版',
        content: '当前为二次元/插画图片，可生成创意证件照效果，但不保证适用于官方审核。',
        confirmText: '继续生成',
        cancelText: '取消',
        success: function(res) { if (res.confirm) run(); }
      });
      return;
    }
    run();
  },

  getPortraitUserError: function(err, fallback) {
    var msg = (err && err.message) || '';
    var code = (err && err.code) || '';
    if (code === 'CONTENT_SAFETY_REJECTED' || msg.indexOf('图片内容不符合平台规范') >= 0) {
      return '图片内容不符合平台规范，请更换图片后重试。';
    }
    if (code === 'CONTENT_SAFETY_PENDING' || msg.indexOf('图片安全检测暂未完成') >= 0) {
      return '图片安全检测暂未完成，请稍后重试。';
    }
    if (code === 'CONTENT_SAFETY_UNAVAILABLE' || code === 'CONTENT_SAFETY_AUTH_REQUIRED' || code === 'CONTENT_SAFETY_OPENID_REQUIRED' || msg.indexOf('图片安全检测暂时不可用') >= 0) {
      return '图片安全检测暂时不可用，请稍后重试。';
    }
    if (code === 'INVALID_INPUT_ANIME_OR_CARTOON' || code === 'INVALID_INPUT_NOT_REAL_PERSON') {
      return '当前为二次元/插画图片，可生成创意证件照效果，但不适合作为官方证件照提交。';
    }
    if (code === 'NO_SUBJECT_DETECTED') {
      return '未检测到清晰人物主体，请重新上传头像或半身照。';
    }
    if (code === 'MULTIPLE_FACES_DETECTED') {
      return '检测到多个人脸，请上传单人照片。';
    }
    if (code === 'NO_FACE_DETECTED' || code === 'LOW_FACE_CONFIDENCE') {
      return '未检测到清晰人脸，请上传正面半身照。';
    }
    if (code === 'SHOULDER_MISSING') {
      return '照片肩部区域不足，建议上传包含头部和双肩的半身照。';
    }
    if (code === 'IMAGE_TOO_BLURRY') {
      return '图片清晰度较低，建议更换更清晰的照片。';
    }
    if (code === 'OUTFIT_TEMPLATE_DISABLED' || code === 'TEMPLATE_NOT_AVAILABLE' || code === 'TEMPLATE_ASSET_MISSING' || code === 'TEMPLATE_TYPE_MISMATCH') {
      return '高级换装暂未开放，请使用保留原服装模式。';
    }
    if (code === 'COMPOSITION_FAILED') {
      return '生成失败，请重新上传清晰的人像照片后重试。';
    }
    if (code === 'SERVICE_UNAVAILABLE') {
      return '生成服务暂不可用，请稍后重试。';
    }
    if (code === 'PRESERVE_ORIGINAL_FAILED') {
      return '基础生成失败，请重新上传图片后重试。';
    }
    if (code === 'HEADSHOT_LAYOUT_INVALID') {
      return '当前照片构图不适合生成标准头肩证件照，请上传更清晰的正面半身照片后重试。';
    }
    if (code === 'SEGMENTATION_INCOMPLETE' || code === 'MASK_TOO_SMALL' || code === 'MASK_FACE_MISSING') {
      return '主体识别不完整，可切换为手动裁剪或创意模式继续生成。';
    }
    if (msg.indexOf('当前模板') >= 0 || msg.indexOf('服装贴合失败') >= 0 || msg.indexOf('模板') >= 0) {
      return '高级换装暂未开放，请使用保留原服装模式。';
    }
    if (msg.indexOf('生成服务暂不可用') >= 0 || msg.indexOf('当前为二次元') >= 0 || msg.indexOf('未检测到清晰人物主体') >= 0 || msg.indexOf('当前图片不适合') >= 0 || msg.indexOf('当前照片构图不适合') >= 0 || msg.indexOf('检测到多个人脸') >= 0 || msg.indexOf('未检测到清晰人脸') >= 0 || msg.indexOf('肩部') >= 0 || msg.indexOf('清晰度') >= 0 || msg.indexOf('主体识别不完整') >= 0) {
      return msg;
    }
    return fallback || '生成失败，请重新上传清晰的人像照片后重试。';
  },

  doChangeBg: function() {
    this.generateIdPhotoV2('changeBg');
    return;
    var that = this;
    if (!that.data.photoSrc) { wx.showToast({ title: '请先上传图片', icon: 'none' }); return; }

    var targetBg = that.data.bgColors[that.data.selBgIdx];

    if (that.data.bgMode === 'ai') {
      // === AI 抠图换底色：调用后端 rembg + 合成 ===
      if (!apiConfig.ENABLE_AI || !apiConfig.API_BASE_URL) {
        wx.showModal({
          title: '生成失败',
          content: '生成失败，请重新上传符合要求的照片。',
          showCancel: false
        });
        return;
      }

      that.setData({ processing: true, resultImage: '' });

      aiImageApi.changeBg(that.data.photoSrc, targetBg.id).then(function (resultPath) {
        that.setData({ processing: false, resultImage: resultPath });
        wx.showToast({ title: 'AI换底完成', icon: 'success' });
        
        that.updateDiagInfo({
          method: 'POST',
          url: '/api/change-bg',
          params: { bgColor: targetBg.id },
          success: true,
          message: 'AI抠图换底成功',
          original: that.data.photoSrc,
          result: resultPath,
          backendMode: 'rembg 抠图'
        });
      }).catch(function (err) {
        console.error('[changeBg] generate failed:', err);
        var userMsg = that.getPortraitUserError(err, '生成失败，请重新上传符合要求的照片。');
        that.setData({ processing: false, resultImage: '' });
        wx.showModal({
          title: '换底失败',
          content: userMsg,
          showCancel: false
        });
        
        that.updateDiagInfo({
          method: 'POST',
          url: '/api/change-bg',
          params: { bgColor: targetBg.id },
          success: false,
          message: userMsg,
          backendMode: 'rembg 抠图'
        });
      });
    } else {
      if (!apiConfig.ENABLE_AI || !apiConfig.API_BASE_URL) {
        wx.showModal({
          title: '生成失败',
          content: '生成失败，请重新上传符合要求的照片。',
          showCancel: false
        });
        return;
      }
      that.setData({ processing: true, resultImage: '' });
      aiImageApi.validatePortraitInput(that.data.photoSrc, 'changeBg').then(function() {
        that.setData({ processing: false });
        that.doLocalChangeBg();
      }).catch(function(err) {
        console.error('[changeBg] local precheck failed:', err);
        that.setData({ processing: false, resultImage: '' });
        wx.showModal({
          title: '换底失败',
          content: that.getPortraitUserError(err, '生成失败，请重新上传符合要求的照片。'),
          showCancel: false
        });
      });
    }
  },

  doLocalChangeBg: function() {
    var that = this;
    var targetBg = that.data.bgColors[that.data.selBgIdx];

    that.setData({ processing: true, resultImage: '' });

    bgReplace.replaceBackgroundByFloodFill({
      imagePath: that.data.photoSrc,
      sourceMode: that.data.detectSrcBg,
      targetColor: targetBg,
      maxDim: 800
    }).then(function(result) {
      that.setData({ processing: false, resultImage: result.tempFilePath });
      wx.showToast({ title: '本地换底完成', icon: 'success' });
      
      that.updateDiagInfo({
        method: 'LOCAL',
        url: 'Canvas 2D FloodFill',
        params: { sourceMode: that.data.detectSrcBg, targetBg: targetBg.id },
        success: true,
        message: '本地纯色替换完成',
        original: that.data.photoSrc,
        result: result.tempFilePath,
        backendMode: 'Canvas本地替换'
      });
    }).catch(function(err) {
      that.setData({ processing: false });
      var msg = (err && err.message) || '换底失败';
      
      // Proactively block and warn on complex standard deviation detection
      if (msg.indexOf('复杂背景') >= 0 || msg.indexOf('主体染色') >= 0) {
        wx.showModal({
          title: '本地换底受限',
          content: '检测到您的图片背景比较复杂，使用本地连通算法极易把头发、衣服或皮肤染色。为了保证证件照质量，请使用“AI抠图”模式！',
          showCancel: true,
          cancelText: '知道了',
          confirmText: '切换到AI模式',
          success: function(res) {
            if (res.confirm) {
              that.setData({ bgMode: 'ai' });
              that.doChangeBg();
            }
          }
        });
      } else if (msg.indexOf('无法检测') >= 0 || msg.indexOf('连通') >= 0) {
        wx.showModal({
          title: '本地换底失败',
          content: '当前图片无法检测到明显的连通背景，建议切换至“AI抠图”模式处理。',
          showCancel: false
        });
      } else {
        wx.showToast({ title: msg, icon: 'none', duration: 2500 });
      }
      
      that.updateDiagInfo({
        method: 'LOCAL',
        url: 'Canvas 2D FloodFill',
        params: { sourceMode: that.data.detectSrcBg, targetBg: targetBg.id },
        success: false,
        message: msg,
        backendMode: 'Canvas本地替换'
      });
    });
  },

  // ========== CUSTOM SIZE — STRING INPUTS, NO parseInt IN onInput ==========
  onWidthPxInput: function(e) { this.setData({ widthPxInput: e.detail.value }); },
  onHeightPxInput: function(e) { this.setData({ heightPxInput: e.detail.value }); },
  onWidthMmInput: function(e) { this.setData({ widthMmInput: e.detail.value }); },
  onHeightMmInput: function(e) { this.setData({ heightMmInput: e.detail.value }); },

  doCustomSize: function() {
    var wPx = parseInt(this.data.widthPxInput, 10);
    var hPx = parseInt(this.data.heightPxInput, 10);
    var wMm = parseInt(this.data.widthMmInput, 10);
    var hMm = parseInt(this.data.heightMmInput, 10);

    if (!wPx || wPx < 10 || !hPx || hPx < 10) { wx.showToast({ title: '请输入有效像素尺寸(≥10)', icon: 'none' }); return; }
    if (!wMm || wMm < 1 || !hMm || hMm < 1) { wx.showToast({ title: '请输入有效毫米尺寸(≥1)', icon: 'none' }); return; }

    var customSpec = {
      id: 'custom_pass',
      name: '自定义',
      displayName: '自定义尺寸',
      mm: wMm + '×' + hMm + 'mm',
      widthMm: wMm, heightMm: hMm,
      px: wPx + '×' + hPx + 'px',
      widthPx: wPx, heightPx: hPx,
      category: '自定义', defaultBg: 'blue',
      bgColors: ['blue','white','red','lightBlue','gray'],
      isCustom: true
    };
    getApp().globalData.customSpec = customSpec;
    idPhotoEntry.openCaptureGuide('custom_pass', { custom: true });
  },

  // ========== EDIT / COMPRESS — STRING INPUT ==========
  onQualityChange: function(e) { this.setData({ quality: e.detail.value }); },
  onTargetKbInput: function(e) { this.setData({ targetKbInput: e.detail.value }); },
  setCropRatio: function(e) { this.setData({ cropRatio: e.currentTarget.dataset.r }); },

  doCompress: function() {
    var that = this;
    if (!that.data.photoSrc) { wx.showToast({ title: '请先上传图片', icon: 'none' }); return; }
    var targetKb = parseInt(that.data.targetKbInput, 10);
    if (!targetKb || targetKb < 1) { wx.showToast({ title: '请输入有效目标KB值', icon: 'none' }); return; }

    that.setData({ processing: true, compressResult: null });

    compress.compressToTargetKB({
      imagePath: that.data.photoSrc,
      targetKB: targetKb,
      qualityStart: 0.92,
      qualityMin: 0.15,
      maxLoop: 25
    }).then(function(result) {
      var actualKb = Math.round(result.actualKb * 10) / 10;
      that.setData({
        processing: false,
        resultImage: result.tempFilePath,
        compressResult: {
          targetKB: targetKb,
          actualKB: actualKb,
          method: '本地',
          width: result.outputW,
          height: result.outputH
        }
      });
      if (actualKb > targetKb * 1.3) {
        wx.showModal({
          title: '压缩结果',
          content: '目标' + targetKb + 'KB，实际' + actualKb + 'KB。\n目标体积过小，已压缩到当前清晰度下最小可用体积。',
          showCancel: false
        });
      }
    }).catch(function(err) {
      that.setData({ processing: false });
      wx.showToast({ title: (err && err.message) || '压缩失败', icon: 'none' });
    });
  },

  // ========== FORMAT CONVERT ==========
  setFormat: function(e) { this.setData({ targetFormat: e.currentTarget.dataset.fmt }); },
  doConvert: function() {
    var that = this;
    if (!that.data.photoSrc) { wx.showToast({ title: '请先上传图片', icon: 'none' }); return; }
    that.setData({ processing: true });
    wx.getImageInfo({
      src: that.data.photoSrc,
      success: function(info) {
        var c = wx.createOffscreenCanvas({ type: '2d', width: info.width, height: info.height });
        var ctx = c.getContext('2d'); var img = c.createImage();
        img.onload = function() {
          ctx.drawImage(img, 0, 0, info.width, info.height);
          wx.canvasToTempFilePath({
            canvas: c, fileType: that.data.targetFormat, quality: 0.95,
            success: function(res) { that.setData({ processing: false, resultImage: res.tempFilePath }); },
            fail: function() { that.setData({ processing: false }); wx.showToast({ title: '转换失败', icon: 'none' }); }
          });
        };
        img.src = that.data.photoSrc;
      },
      fail: function() { that.setData({ processing: false }); }
    });
  },

  // ========== COLORIZE ==========
  setColorFilter: function(e) { this.setData({ colorFilter: e.currentTarget.dataset.filter }); },
  doColorize: function() {
    var that = this;
    if (!that.data.photoSrc) { wx.showToast({ title: '请先上传图片', icon: 'none' }); return; }
    that.setData({ processing: true });
    wx.getImageInfo({
      src: that.data.photoSrc,
      success: function(info) {
        var max=800, s=Math.min(1,max/Math.max(info.width,info.height));
        var cw=Math.floor(info.width*s),ch=Math.floor(info.height*s);
        var c=wx.createOffscreenCanvas({type:'2d',width:cw,height:ch});
        var ctx=c.getContext('2d');var img=c.createImage();
        img.onload=function(){
          ctx.drawImage(img,0,0,cw,ch);
          var filters={warm:{r:1.12,g:0.95,b:0.85},cold:{r:0.88,g:0.96,b:1.15},vintage:{r:1.1,g:0.94,b:0.78},enhance:{r:1.08,g:1.05,b:1.02}};
          try{var d=ctx.getImageData(0,0,cw,ch);var px=d.data;var f=filters[that.data.colorFilter]||filters.warm;
            for(var i=0;i<px.length;i+=4){px[i]=Math.min(255,px[i]*f.r);px[i+1]=Math.min(255,px[i+1]*f.g);px[i+2]=Math.min(255,px[i+2]*f.b);}
            ctx.putImageData(d,0,0);
          }catch(e){ctx.fillStyle='rgba(255,180,80,0.1)';ctx.fillRect(0,0,cw,ch);}
          wx.canvasToTempFilePath({canvas:c,fileType:'jpg',quality:0.95,
            success:function(r){that.setData({processing:false,resultImage:r.tempFilePath});},
            fail:function(){that.setData({processing:false});}
          });
        };
        img.src=that.data.photoSrc;
      }
    });
  },

  // ========== ADD WATERMARK ==========
  onWatermarkTextInput: function(e) { this.setData({ watermarkText: e.detail.value || '证件照' }); },
  onWatermarkOpacity: function(e) { this.setData({ watermarkOpacity: e.detail.value }); },
  setWatermarkPos: function(e) { this.setData({ watermarkPos: e.currentTarget.dataset.pos }); },
  onWatermarkSize: function(e) { this.setData({ watermarkSize: parseInt(e.detail.value) || 32 }); },
  doAddWatermark: function() {
    var that = this;
    if (!that.data.photoSrc) { wx.showToast({ title: '请先上传图片', icon: 'none' }); return; }
    that.setData({ processing: true });
    wx.getImageInfo({
      src: that.data.photoSrc,
      success: function(info) {
        var w=info.width,h=info.height;
        var c=wx.createOffscreenCanvas({type:'2d',width:w,height:h});
        var ctx=c.getContext('2d');var img=c.createImage();
        img.onload=function(){
          ctx.drawImage(img,0,0,w,h);
          var alpha=that.data.watermarkOpacity/100;
          var text=that.data.watermarkText;
          var fs=that.data.watermarkSize;
          ctx.font='bold '+fs+'px sans-serif';
          var m=ctx.measureText(text);var tw=m.width,th=fs,pad=40;
          var pos=that.data.watermarkPos;
          var x,y;
          if(pos==='leftTop'){x=pad;y=pad+th;}
          else if(pos==='rightTop'){x=w-tw-pad;y=pad+th;}
          else if(pos==='leftBottom'){x=pad;y=h-pad;}
          else if(pos==='rightBottom'){x=w-tw-pad;y=h-pad;}
          else if(pos==='center'){x=(w-tw)/2;y=h/2;}
          else {x=w-tw-pad;y=h-pad;}
          function drawT(tx,ty,a){
            ctx.strokeStyle='rgba(0,0,0,'+(a*0.6)+')';ctx.lineWidth=2;ctx.strokeText(tx,ty);
            ctx.fillStyle='rgba(255,255,255,'+a+')';ctx.fillText(tx,ty);
          }
          if(pos==='tile'){var sx=tw+100,sy=th+80;
            for(var ty=sy;ty<h;ty+=sy){for(var tx=0;tx<w;tx+=sx){drawT(text,tx,ty,alpha);}}
          }else{drawT(text,x,y,alpha);}
          wx.canvasToTempFilePath({canvas:c,fileType:'jpg',quality:0.95,
            success:function(r){that.setData({processing:false,resultImage:r.tempFilePath});},
            fail:function(){that.setData({processing:false});wx.showToast({title:'生成失败',icon:'none'});}
          });
        };
        img.src=that.data.photoSrc;
      },
      fail:function(){that.setData({processing:false});}
    });
  },

  // ========== REMOVE WATERMARK — STRING INPUTS + AI MODE ==========
  onSelXInput: function(e) { this.setData({ selXInput: e.detail.value }); },
  onSelYInput: function(e) { this.setData({ selYInput: e.detail.value }); },
  onSelWInput: function(e) { this.setData({ selWInput: e.detail.value }); },
  onSelHInput: function(e) { this.setData({ selHInput: e.detail.value }); },
  resetSelection: function() { this.setData({ selectRect: null }); },
  setRemoveMode: function(e) { this.setData({ removeMode: e.currentTarget.dataset.mode }); },
  setWmMode: function(e) { 
    var mode = e.currentTarget.dataset.mode;
    if (mode !== 'manual' && mode !== 'stamp') {
      mode = 'manual';
    }
    this.setData({ wmMode: mode });
    var that = this;
    if (that.data.photoSrc && that.data.toolType === 'removeWatermark') {
      // 切换模式时重设画布
      setTimeout(function() {
        var wmCanvas = require('../../utils/watermarkCanvas.js');
        wmCanvas.clearAll();
        that._wmLastMaskInfo = null;
        that._wmLastStrokeInfo = null;
        that.setData({
          wmHasMask: false,
          wmMaskPreview: '',
          wmMaskWidth: 0,
          wmMaskHeight: 0,
          wmMaskNonZeroPixels: 0,
          wmMaskRatio: '0.00',
          wmMaskRatioValue: 0,
          wmBackendDebug: {},
          wmResultQuality: '',
          wmResultModeLabel: '',
          wmStampSampleSet: false,
          wmStampSampling: false,
          selectRect: null
        });
      }, 50);
    }
  },

  // ====== NEW WATERMARK MODES AND CANVAS INTEGRATION ======
  
  initWmCanvas: function() {
    var that = this;
    if (!that.data.photoSrc || that.data.toolType !== 'removeWatermark') {
      console.warn('[watermark] initWmCanvas skipped: photoSrc is empty or toolType is not removeWatermark');
      return;
    }
    
    console.log('[watermark] initWmCanvas started. imageSrc:', that.data.photoSrc);
    
    var sysInfo = wx.getSystemInfoSync();
    var dpr = sysInfo.pixelRatio || 1;
    var winW = sysInfo.windowWidth;
    var winH = sysInfo.windowHeight || 667;
    
    // 小程序内展示宽度，设计为 640rpx
    var displayContainerW = Math.floor(winW * 640 / 750);
    var displayContainerH = Math.min(420, Math.max(260, Math.floor(winH * 0.38)));
    
    // 重置异常状态并开启 loading
    that.setData({
      wmCanvasInitFailed: false
    });
    wx.showLoading({ title: '初始化画布...' });

    var initSucceeded = false;
    var isAborted = false;
    
    // 8 秒超时看门狗定时器，避免无限转圈
    var watchdog = setTimeout(function() {
      if (initSucceeded) return;
      isAborted = true;
      console.error('[watermark] initCanvas failed: 8s timeout triggered');
      wx.hideLoading();
      that.setData({
        wmCanvasInitFailed: true
      });
      wx.showModal({
        title: '加载超时',
        content: '画布加载超时，请点击“重新初始化”或重新选择图片。',
        showCancel: false
      });
    }, 8000);

    // 轮询查询 DOM 节点函数，避免直接递归 initWmCanvas
    function pollQuery(attempt) {
      if (isAborted || initSucceeded) return;
      
      console.log('[watermark] polling canvas node. attempt:', attempt);
      
      // Scope selector query with in(that) for absolute node location stability
      var query = wx.createSelectorQuery().in(that);
      query.select('#wmCanvas').fields({ node: true, size: true });
      query.exec(function(res) {
        if (isAborted || initSucceeded) return;

        if (res && res[0] && res[0].node) {
          console.log('[watermark] canvas node found successfully on attempt', attempt);
          initSucceeded = true;
          clearTimeout(watchdog);
          
          var displayCanvas = res[0].node;
          var wmCanvas = require('../../utils/watermarkCanvas.js');
          
          wmCanvas.initCanvases({
            displayCanvas: displayCanvas,
            imagePath: that.data.photoSrc,
            containerWidth: displayContainerW,
            containerHeight: displayContainerH,
            dpr: dpr,
            strokeTransportOnly: true
          }).then(function(canvasInfo) {
            console.log('[watermark] initCanvases resolved successfully:', canvasInfo);
            wx.hideLoading();
            that.setData({
              wmDisplayWidth: canvasInfo.displayW,
              wmDisplayHeight: canvasInfo.displayH,
              wmHasMask: false,
              wmMaskPreview: '',
              wmMaskWidth: 0,
              wmMaskHeight: 0,
              wmMaskNonZeroPixels: 0,
              wmMaskRatio: '0.00',
              wmMaskRatioValue: 0,
              wmBackendDebug: {},
              wmStampSampleSet: false,
              wmStampSampling: false,
              wmCanvasInitFailed: false,
              selectRect: null
            });
          }).catch(function(err) {
            console.error('[watermark] initCanvases promise rejected:', err);
            wx.hideLoading();
            that.setData({
              wmCanvasInitFailed: true
            });
            wx.showToast({ title: '画布渲染错误', icon: 'none' });
          });
        } else {
          // 未查到节点，在限制次数内重试
          if (attempt < 20) {
            setTimeout(function() {
              pollQuery(attempt + 1);
            }, 250);
          } else {
            // 超出重试限制
            console.error('[watermark] canvas node polling failed after 20 attempts');
            clearTimeout(watchdog);
            wx.hideLoading();
            that.setData({
              wmCanvasInitFailed: true
            });
            wx.showToast({ title: '找不到画布节点', icon: 'none' });
          }
        }
      });
    }

    // 启动轮询
    pollQuery(1);
  },

  onWmBrushSizeChange: function(e) {
    this.setData({ wmBrushSize: e.detail.value });
  },

  setWmStrength: function(e) {
    this.setData({ wmStrength: e.currentTarget.dataset.strength || 'medium' });
  },

  setWmQuality: function(e) {
    var quality = (e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.quality) || 'fast';
    if (quality === 'hd') {
      if (!watermarkApi.isHdRepairEnabled()) {
        wx.showToast({ title: '高清修复服务未启用，可先使用快速模式。', icon: 'none' });
        this.setData({ wmQuality: 'fast' });
        return;
      }
      if (!this.data.wmHdAvailable) {
        wx.showToast({ title: '高清修复服务暂不可用，可先使用快速模式。', icon: 'none' });
        this.checkWatermarkHealth();
        this.setData({ wmQuality: 'fast' });
        return;
      }
    }
    quality = quality === 'hd' ? 'hd' : 'fast';
    var endpoint = '/api/watermark/remove-v2';
    this.setData({
      wmQuality: quality,
      wmUploadUrl: watermarkApi.getBaseUrl() + endpoint
    });
  },

  getWmInpaintRadius: function() {
    if (this.data.wmStrength === 'low') return 2;
    if (this.data.wmStrength === 'high') return 5;
    return 3;
  },

  refreshWmMaskDebug: function() {
    var that = this;
    if (!that.data.photoSrc || that.data.toolType !== 'removeWatermark') return;

    var wmCanvas = require('../../utils/watermarkCanvas.js');
    if (!wmCanvas.checkHasPaint()) {
      that.setData({
        wmHasMask: false,
        wmMaskPreview: '',
        wmMaskWidth: 0,
        wmMaskHeight: 0,
        wmMaskNonZeroPixels: 0,
        wmMaskRatio: '0.00',
        wmMaskRatioValue: 0
      });
      return;
    }

    try {
      var maskInfo = wmCanvas.getStrokeTransportPayload();
      that.setData({
        wmHasMask: true,
        wmMaskPreview: '',
        wmMaskWidth: maskInfo.width,
        wmMaskHeight: maskInfo.height,
        wmMaskNonZeroPixels: maskInfo.nonZeroPixels,
        wmMaskRatio: (maskInfo.maskRatio * 100).toFixed(2),
        wmMaskRatioValue: maskInfo.maskRatio
      });
    } catch (err) {
      console.warn('[watermark] refresh mask debug failed:', err);
      that.setData({
        wmHasMask: false,
        wmMaskPreview: '',
        wmMaskWidth: 0,
        wmMaskHeight: 0,
        wmMaskNonZeroPixels: 0,
        wmMaskRatio: '0.00',
        wmMaskRatioValue: 0
      });
    }
  },

  toggleStampSampling: function() {
    var sampling = !this.data.wmStampSampling;
    this.setData({
      wmStampSampling: sampling
    });
    if (sampling) {
      wx.showToast({ title: '请在上方图片中点击采样源位置', icon: 'none', duration: 3000 });
    }
  },

  drawStampSampleTarget: function() {
    if (!this.data.wmStampSampleSet) return;
    var wmCanvas = require('../../utils/watermarkCanvas.js');
    var ctx = wmCanvas.displayContext;
    ctx.save();
    ctx.beginPath();
    ctx.arc(this.data.wmStampSampleX, this.data.wmStampSampleY, 6, 0, Math.PI * 2);
    ctx.strokeStyle = '#00E676'; // 鲜艳绿色
    ctx.lineWidth = 2;
    ctx.stroke();
    
    // 画十字中心
    ctx.beginPath();
    ctx.moveTo(this.data.wmStampSampleX - 10, this.data.wmStampSampleY);
    ctx.lineTo(this.data.wmStampSampleX + 10, this.data.wmStampSampleY);
    ctx.moveTo(this.data.wmStampSampleX, this.data.wmStampSampleY - 10);
    ctx.lineTo(this.data.wmStampSampleX, this.data.wmStampSampleY + 10);
    ctx.strokeStyle = '#00E676';
    ctx.stroke();
    ctx.restore();
  },

  onWmUndo: function() {
    var wmCanvas = require('../../utils/watermarkCanvas.js');
    var success = wmCanvas.undo();
    if (success) {
      this.setData({
        wmHasMask: wmCanvas.checkHasPaint()
      });
      this.refreshWmMaskDebug();
      if (this.data.wmMode === 'stamp') {
        this.drawStampSampleTarget();
      }
    } else {
      wx.showToast({ title: '没有历史笔迹了', icon: 'none' });
    }
  },

  onWmRedo: function() {
    var wmCanvas = require('../../utils/watermarkCanvas.js');
    var success = wmCanvas.redo();
    if (success) {
      this.setData({
        wmHasMask: wmCanvas.checkHasPaint()
      });
      this.refreshWmMaskDebug();
      if (this.data.wmMode === 'stamp') {
        this.drawStampSampleTarget();
      }
    }
  },

  onWmClear: function() {
    var wmCanvas = require('../../utils/watermarkCanvas.js');
    wmCanvas.clearAll();
    this.setData({
      wmHasMask: false,
      selectRect: null,
      wmMaskPreview: '',
      wmMaskWidth: 0,
      wmMaskHeight: 0,
      wmMaskNonZeroPixels: 0,
      wmMaskRatio: '0.00',
      wmMaskRatioValue: 0,
      wmBackendDebug: {}
    });
  },

  // Touch handlers
  onWmTouchStart: function(e) {
    if (this.data.processing || !this.data.photoSrc) return;
    var touch = (e.touches && e.touches[0]) || (e.changedTouches && e.changedTouches[0]);
    if (!touch) {
      console.warn('[watermark] touchstart event had no touch object');
      return;
    }
    var touchX = touch.x !== undefined ? touch.x : (touch.offsetX !== undefined ? touch.offsetX : touch.clientX);
    var touchY = touch.y !== undefined ? touch.y : (touch.offsetY !== undefined ? touch.offsetY : touch.clientY);
    console.log('[watermark] touch start coordinates:', touchX, touchY, 'raw x/y:', touch.x, touch.y, 'client x/y:', touch.clientX, touch.clientY);
    
    var wmCanvas = require('../../utils/watermarkCanvas.js');
    
    if (this.data.wmMode === 'manual') {
      this.currentStroke = {
        type: 'brush',
        brushSize: this.data.wmBrushSize,
        points: [{ x: touchX, y: touchY, brushSize: this.data.wmBrushSize }]
      };
      var scaleX = wmCanvas.imgW / wmCanvas.displayW;
      var scaleY = wmCanvas.imgH / wmCanvas.displayH;
      wmCanvas.drawBrushStroke(this.currentStroke, scaleX, scaleY);
    } 
    else if (this.data.wmMode === 'stamp') {
      if (this.data.wmStampSampling) {
        this.setData({
          wmStampSampleX: touchX,
          wmStampSampleY: touchY,
          wmStampSampleSet: true,
          wmStampSampling: false
        });
        wmCanvas.redrawHistory();
        this.drawStampSampleTarget();
        wx.showToast({ title: '采样点已选定，滑动开始克隆', icon: 'none' });
      } 
      else if (this.data.wmStampSampleSet) {
        this.currentStroke = {
          type: 'stamp',
          brushSize: this.data.wmBrushSize,
          stampSample: { x: this.data.wmStampSampleX, y: this.data.wmStampSampleY },
          points: [{ x: touchX, y: touchY }]
        };
        var scaleX = wmCanvas.imgW / wmCanvas.displayW;
        var scaleY = wmCanvas.imgH / wmCanvas.displayH;
        wmCanvas.drawStampStroke(this.currentStroke, scaleX, scaleY);
      }
    }
  },

  onWmTouchMove: function(e) {
    if (this.data.processing || !this.data.photoSrc) return;
    var touch = (e.touches && e.touches[0]) || (e.changedTouches && e.changedTouches[0]);
    if (!touch) return;
    var touchX = touch.x !== undefined ? touch.x : (touch.offsetX !== undefined ? touch.offsetX : touch.clientX);
    var touchY = touch.y !== undefined ? touch.y : (touch.offsetY !== undefined ? touch.offsetY : touch.clientY);
    
    var wmCanvas = require('../../utils/watermarkCanvas.js');
    var scaleX = wmCanvas.imgW / wmCanvas.displayW;
    var scaleY = wmCanvas.imgH / wmCanvas.displayH;
    
    if (this.data.wmMode === 'manual' && this.currentStroke) {
      this.currentStroke.points.push({ x: touchX, y: touchY, brushSize: this.data.wmBrushSize });
      wmCanvas.drawBrushStroke({
        type: 'brush',
        brushSize: this.data.wmBrushSize,
        points: [
          this.currentStroke.points[this.currentStroke.points.length - 2],
          this.currentStroke.points[this.currentStroke.points.length - 1]
        ]
      }, scaleX, scaleY);
    }
    else if (this.data.wmMode === 'stamp' && this.currentStroke) {
      this.currentStroke.points.push({ x: touchX, y: touchY });
      wmCanvas.drawStampStroke({
        type: 'stamp',
        brushSize: this.data.wmBrushSize,
        stampSample: this.currentStroke.stampSample,
        points: [
          this.currentStroke.points[this.currentStroke.points.length - 2],
          this.currentStroke.points[this.currentStroke.points.length - 1]
        ]
      }, scaleX, scaleY);
    }
  },

  onWmTouchEnd: function() {
    var wmCanvas = require('../../utils/watermarkCanvas.js');
    
    if (this.data.wmMode === 'manual' && this.currentStroke) {
      wmCanvas.pushStroke(this.currentStroke);
      this.setData({
        wmHasMask: true
      });
      this.currentStroke = null;
      this.refreshWmMaskDebug();
    }
    else if (this.data.wmMode === 'stamp' && this.currentStroke) {
      wmCanvas.pushStroke(this.currentStroke);
      this.currentStroke = null;
      wmCanvas.redrawHistory();
      this.drawStampSampleTarget();
    }
  },

  stopPropagation: function() {
    console.log('[watermark] touch event propagation stopped');
  },

  getWatermarkQualityLabel: function(quality) {
    return quality === 'hd' ? '高清修复' : '快速模式';
  },

  getWatermarkModeLabel: function(mode) {
    if (mode === 'hd') { return '高清修复'; }
    if (mode === 'quick') { return '快速模式'; }
    return '手动擦除';
  },

  runWatermarkRemoveWithStrokes: function(maskInfo, strokeInfo, qualityOverride) {
    var that = this;
    var quality = qualityOverride || that.data.wmQuality || 'fast';
    var wmApi = require('../../utils/watermarkApi.js');

    if (quality === 'hd') {
      if (!watermarkApi.isHdRepairEnabled() || !that.data.wmHdAvailable) {
        that.setData({ processing: false });
        wx.showModal({
          title: '高清修复暂不可用',
          content: '高清修复服务暂不可用，可先使用快速模式。',
          showCancel: false
        });
        that.checkWatermarkHealth();
        return;
      }
    } else if (maskInfo.maskRatio > 0.2) {
      wx.showToast({
        title: '快速模式处理大面积区域可能出现模糊，可切换高清修复。',
        icon: 'none',
        duration: 2600
      });
    }

    var modeKey = quality === 'hd' ? 'hd' : (quality === 'fast' ? 'quick' : 'manual');
    var apiCall = wmApi.removeV2;
    var endpoint = '/api/watermark/remove-v2';
    var backendMode = modeKey === 'hd' ? 'hd' : (modeKey === 'quick' ? 'opencv_quick' : 'opencv_manual');
    var edgeRoi = null;
    try {
      edgeRoi = edgeCompute.createWatermarkRoiPackage(strokeInfo);
      console.log('[watermark-edge-roi]', edgeRoi || {});
    } catch (roiErr) {
      console.warn('[watermark-edge-roi] compute failed:', roiErr);
    }
    that.setData({
      processing: true,
      processingText: quality === 'hd' ? '正在上传图片，已等待0秒' : '处理中...'
    });
    var edgeRoiInfo = edgeRoi && edgeRoi.route === 'edge' && edgeRoi.bbox ? edgeRoi : null;
    var edgeAttempted = false;
    var cloudAttempted = false;

    function buildPerformancePatch(clientPerformance) {
      return Object.assign({}, clientPerformance || {}, {
        edgeRoiRoute: edgeRoi && edgeRoi.route || 'cloud',
        originalPixels: edgeRoi && edgeRoi.originalPixels || 0,
        roiPixels: edgeRoi && edgeRoi.roiPixels || 0,
        pixelReductionRatio: edgeRoi && edgeRoi.pixelReductionRatio || 0
      });
    }

    function finishSuccess(res, finalTempPath, actualMode, actualEngine, remoteUrl, extraDebug) {
      var resultMessage = actualMode === 'hd'
        ? '已使用高清修复模式'
        : (actualMode === 'quick' ? '已使用快速模式' : '已使用手动擦除模式');
      var finalResultPath = finalTempPath || res.tempFilePath;
      var statePatch = {
        processing: false,
        processingText: '处理中...',
        resultImage: finalResultPath,
        wmBackendDebug: extraDebug || res.debug || {},
        wmClientPerformance: buildPerformancePatch(res.clientPerformance || {}),
        wmResultQuality: quality,
        wmResultModeLabel: that.getWatermarkModeLabel(actualMode),
        wmResultMessage: resultMessage,
        currentWatermarkMode: actualMode,
        currentResultUrl: remoteUrl,
        currentResultLocalPath: finalResultPath,
        currentEngine: actualEngine,
        currentOutputPath: res.outputPath || '',
        currentFileHash: res.fileHash || ''
      };
      statePatch[actualMode + 'ResultUrl'] = res.resultUrl || remoteUrl;
      statePatch[actualMode + 'ResultLocalPath'] = finalResultPath;
      that.setData(statePatch);
      wx.showToast({ title: actualMode === 'hd' ? '高清修复完成' : '去水印成功', icon: 'success' });
      that.updateDiagInfo({
        method: 'POST',
        url: endpoint,
        params: {
          mode: modeKey,
          quality: quality,
          strength: that.data.wmStrength,
          radius: quality === 'fast' ? that.getWmInpaintRadius() : '-',
          maskSize: maskInfo.width + 'x' + maskInfo.height,
          maskNonZeroPixels: maskInfo.nonZeroPixels,
          maskRatio: maskInfo.maskRatio,
          edgeRoiRoute: edgeRoi && edgeRoi.route || 'cloud',
          roiPixels: edgeRoi && edgeRoi.roiPixels || 0,
          pixelReductionRatio: edgeRoi && edgeRoi.pixelReductionRatio || 0
        },
        success: true,
        message: res.message || (quality === 'hd' ? '高清修复成功' : '手动去水印成功'),
        original: that.data.photoSrc,
        result: res.resultUrl || finalResultPath,
        backendMode: res.engine || res.backendMode || backendMode
      });
    }

    function finishFailure(err) {
      console.error('[watermark] removeWatermark API request failed:', err);
      var debugMsg = (err && err.message) || '处理失败，未生成结果图。';
      var userMsg = quality === 'hd'
        ? that.getWatermarkUserError(err, '高清修复服务暂不可用，可先使用快速模式。')
        : that.getWatermarkUserError(err, '处理失败，请调整涂抹区域后重试。');
      that.setData({
        processing: false,
        processingText: '处理中...',
        wmBackendDebug: err && err.debug ? err.debug : {},
        wmLastError: debugMsg
      });
      wx.showModal({
        title: quality === 'hd' ? '高清修复失败' : '去水印失败',
        content: userMsg,
        showCancel: false
      });
      that.updateDiagInfo({
        method: 'POST',
        url: endpoint,
        params: {
          mode: modeKey,
          quality: quality,
          strength: that.data.wmStrength,
          radius: quality === 'fast' ? that.getWmInpaintRadius() : '-',
          maskSize: maskInfo.width + 'x' + maskInfo.height,
          maskNonZeroPixels: maskInfo.nonZeroPixels,
          maskRatio: maskInfo.maskRatio,
          edgeRoiRoute: edgeRoi && edgeRoi.route || 'cloud',
          roiPixels: edgeRoi && edgeRoi.roiPixels || 0,
          pixelReductionRatio: edgeRoi && edgeRoi.pixelReductionRatio || 0
        },
        success: false,
        message: userMsg,
        backendMode: backendMode
      });
    }

    function submitCloudPath() {
      cloudAttempted = true;
      apiCall({
        imagePath: that.data.photoSrc,
        sourceImagePath: that.data.photoSrc,
        strokeInfo: strokeInfo,
        quality: modeKey,
        strength: that.data.wmStrength,
        preserveDetail: true,
        onStatus: quality === 'hd' ? function(status) {
          if (that.data.processing && status && status.text) {
            that.setData({ processingText: status.text });
          }
        } : null
      }).then(function(res) {
        if (!res.tempFilePath) {
          throw new Error('处理失败，未生成结果图。');
        }
        var remoteUrl = res.previewUrl || res.resultUrl || '';
        var actualMode = res.mode || modeKey;
        var actualEngine = res.engine || backendMode;
        if (quality === 'hd' && (res.fallbackUsed || actualEngine === 'opencv_hd_fallback')) {
          var fallbackErr = new Error('高清修复模型未就绪，请启动本地 IOPaint/LaMa 服务后重试。当前可先使用快速模式。');
          fallbackErr.debug = res.debug || {};
          fallbackErr.fallbackAvailable = true;
          throw fallbackErr;
        }
        finishSuccess(res, res.tempFilePath, actualMode, actualEngine, remoteUrl, res.debug || {});
      }).catch(function(err) {
        finishFailure(err);
      });
    }

    if (!edgeRoiInfo) {
      submitCloudPath();
      return;
    }

    edgeAttempted = true;
    edgeCompute.cropImageRegion({
      imagePath: that.data.photoSrc,
      roi: edgeRoiInfo.bbox,
      outputType: 'png'
    }).then(function(roiImagePath) {
      return apiCall({
        imagePath: roiImagePath,
        sourceImagePath: that.data.photoSrc,
        strokeInfo: edgeRoiInfo.roiStrokeInfo || strokeInfo,
        quality: modeKey,
        strength: that.data.wmStrength,
        preserveDetail: true,
        edgeRoiMode: true,
        roiX: edgeRoiInfo.bbox.x,
        roiY: edgeRoiInfo.bbox.y,
        roiWidth: edgeRoiInfo.bbox.width,
        roiHeight: edgeRoiInfo.bbox.height,
        sourceOriginalWidth: maskInfo.width,
        sourceOriginalHeight: maskInfo.height,
        onStatus: quality === 'hd' ? function(status) {
          if (that.data.processing && status && status.text) {
            that.setData({ processingText: status.text });
          }
        } : null
      }).then(function(res) {
        if (!res.tempFilePath) {
          throw new Error('处理失败，未生成结果图。');
        }
        var remoteUrl = res.previewUrl || res.resultUrl || '';
        var actualMode = res.mode || modeKey;
        var actualEngine = res.engine || backendMode;
        if (quality === 'hd' && (res.fallbackUsed || actualEngine === 'opencv_hd_fallback')) {
          var fallbackErr = new Error('高清修复模型未就绪，请启动本地 IOPaint/LaMa 服务后重试。当前可先使用快速模式。');
          fallbackErr.debug = res.debug || {};
          fallbackErr.fallbackAvailable = true;
          throw fallbackErr;
        }
        return edgeCompute.pasteRoiBack({
          baseImagePath: that.data.photoSrc,
          roiImagePath: res.tempFilePath,
          roi: edgeRoiInfo.bbox,
          baseWidth: maskInfo.width,
          baseHeight: maskInfo.height,
          outputType: 'png'
        }).then(function(finalTempPath) {
          finishSuccess(res, finalTempPath, actualMode, actualEngine, remoteUrl, res.debug || {});
        }).catch(function(pasteErr) {
          pasteErr = pasteErr || new Error('ROI 贴回失败');
          console.warn('[watermark-edge-roi] paste failed, fallback to cloud:', pasteErr);
          submitCloudPath();
        });
      });
    }).catch(function(err) {
      console.warn('[watermark-edge-roi] crop failed, fallback to cloud:', err);
      submitCloudPath();
    });
  },

  retryWatermarkQuality: function(e) {
    var quality = (e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.quality) || 'fast';
    if (quality === 'hd' && (!watermarkApi.isHdRepairEnabled() || !this.data.wmHdAvailable)) {
      wx.showModal({
        title: '高清修复暂不可用',
        content: '高清修复服务暂不可用，可先使用快速模式。',
        showCancel: false
      });
      this.checkWatermarkHealth();
      return;
    }
    var retryEndpoint = '/api/watermark/remove-v2';
    this.setData({
      wmQuality: quality,
      wmUploadUrl: watermarkApi.getBaseUrl() + retryEndpoint
    });
    if (this._wmLastMaskInfo && this._wmLastStrokeInfo) {
      this.runWatermarkRemoveWithStrokes(this._wmLastMaskInfo, this._wmLastStrokeInfo, quality);
      return;
    }
    this.doManualRemoveWatermark();
  },

  continueWatermarkRepair: function() {
    var that = this;
    var nextSource = that.data.currentResultLocalPath || that.data.resultImage;
    if (!nextSource) { return; }
    var wmCanvas = require('../../utils/watermarkCanvas.js');
    wmCanvas.clearAll();
    that._wmLastMaskInfo = null;
    that._wmLastStrokeInfo = null;
    that.setData({
      photoSrc: nextSource,
      resultImage: '',
      wmHasMask: false,
      wmMaskPreview: '',
      wmMaskWidth: 0,
      wmMaskHeight: 0,
      wmMaskNonZeroPixels: 0,
      wmMaskRatio: '0.00',
      wmMaskRatioValue: 0,
      wmBackendDebug: {},
      wmResultQuality: '',
      wmResultModeLabel: '',
      wmResultMessage: '',
      currentWatermarkMode: '',
      currentResultUrl: '',
      currentResultLocalPath: '',
      currentEngine: '',
      currentOutputPath: '',
      currentFileHash: ''
    });
    setTimeout(function() {
      that.initWmCanvas();
    }, 80);
  },

  // ✨ 手动去水印
  doManualRemoveWatermark: function() {
    var that = this;
    var imageSrc = that.data.photoSrc;

    if (!imageSrc) {
      console.error('[watermark] pre-check failed: imageSrc is missing');
      wx.showToast({ title: '请先上传图片', icon: 'none' });
      return;
    }

    if (that.data.wmCanvasInitFailed) {
      console.error('[watermark] pre-check failed: canvas initialization is marked as failed');
      wx.showToast({ title: '画布损坏，请先重试或重新选图', icon: 'none' });
      return;
    }

    var wmCanvas = require('../../utils/watermarkCanvas.js');

    var originalW = wmCanvas.imgW;
    var originalH = wmCanvas.imgH;
    if (!originalW || !originalH) {
      console.error('[watermark] pre-check: original dimensions missing');
      wx.showToast({ title: '原图尺寸获取失败，请刷新重试', icon: 'none' });
      return;
    }

    var strokes = wmCanvas.getActiveBrushStrokes ? wmCanvas.getActiveBrushStrokes() : [];
    if (!strokes || strokes.length === 0) {
      console.warn('[watermark] pre-check: no brush strokes');
      wx.showToast({ title: '请先涂抹需要去除的水印区域。', icon: 'none', duration: 2500 });
      return;
    }

    that.setData({ processing: true });

    try {
      var maskInfo = wmCanvas.getStrokeTransportPayload();
      if (maskInfo.width !== originalW || maskInfo.height !== originalH) {
        console.error('[watermark] mask size mismatch:', maskInfo.width, maskInfo.height, originalW, originalH);
        that.setData({ processing: false });
        wx.showModal({
          title: '遮罩尺寸异常',
          content: '遮罩尺寸 ' + maskInfo.width + 'x' + maskInfo.height + ' 与原图尺寸 ' + originalW + 'x' + originalH + ' 不一致，请重新涂抹。',
          showCancel: false
        });
        return;
      }

      if (!maskInfo.nonZeroPixels || maskInfo.nonZeroPixels <= 0) {
        that.setData({ processing: false });
        wx.showToast({ title: '请先涂抹需要去除的水印区域。', icon: 'none', duration: 2500 });
        return;
      }

      that.setData({
        wmMaskPreview: maskInfo.previewPath,
        wmMaskWidth: maskInfo.width,
        wmMaskHeight: maskInfo.height,
        wmMaskNonZeroPixels: maskInfo.nonZeroPixels,
        wmMaskRatio: (maskInfo.maskRatio * 100).toFixed(2),
        wmMaskRatioValue: maskInfo.maskRatio
      });

      if (maskInfo.maskRatio > 0.2) {
        wx.showToast({
          title: that.data.wmQuality === 'fast' ? '快速模式处理大面积区域可能出现模糊，可切换高清修复。' : '当前涂抹区域较大，建议使用高清修复，或分区域多次处理。',
          icon: 'none',
          duration: 2600
        });
      }

      try {
        var strokeInfo = maskInfo;
        that._wmLastMaskInfo = maskInfo;
        that._wmLastStrokeInfo = strokeInfo;
        that.runWatermarkRemoveWithStrokes(maskInfo, strokeInfo, that.data.wmQuality);
      } catch (err) {
        console.error('[watermark] failed to prepare stroke upload:', err);
        that.setData({ processing: false });
        wx.showToast({ title: '图片上传失败，请重新尝试。', icon: 'none' });
      }
    } catch (err) {
      console.error('[watermark] failed to build stroke payload:', err);
      that.setData({ processing: false });
      wx.showToast({
        title: that.getWatermarkUserError(err, '处理失败，请调整涂抹区域后重试。'),
        icon: 'none',
        duration: 2500
      });
    }
  },

  // 🛠️ 仿制图章保存结果
  doStampSave: function() {
    var that = this;
    if (!that.data.photoSrc) { wx.showToast({ title: '请先上传图片', icon: 'none' }); return; }
    
    var wmCanvas = require('../../utils/watermarkCanvas.js');
    if (wmCanvas.getHistoryCount() === 0) {
      wx.showToast({ title: '请先使用仿制图章克隆修改图片', icon: 'none' });
      return;
    }
    
    that.setData({ processing: true });
    
    wmCanvas.exportResult().then(function(resPath) {
      that.setData({
        processing: false,
        resultImage: resPath
      });
      wx.showToast({ title: '克隆修复完成', icon: 'success' });
      
      that.updateDiagInfo({
        method: 'LOCAL',
        url: 'Canvas 2D Pixel Clone',
        params: { historyCount: wmCanvas.getHistoryCount() },
        success: true,
        message: '仿制图章本地克隆成功',
        original: that.data.photoSrc,
        result: resPath,
        backendMode: 'Canvas仿制图章 (Pure Front-end)'
      });
    }).catch(function(err) {
      that.setData({ processing: false });
      wx.showToast({ title: '导出克隆图片失败: ' + (err.message || ''), icon: 'none' });
    });
  },

  doRemoveWatermark: function() {
    this.setData({ wmMode: 'manual', selectRect: null });
    wx.showToast({ title: '请使用手动擦除或仿制图章', icon: 'none' });
  },

  doLocalRemoveWatermark: function() {
    var that = this;
    var r = that.data.selectRect;

    wx.getImageInfo({
      src: that.data.photoSrc,
      success: function(info) {
        var imgW = info.width, imgH = info.height;
        var maxDim = 1200;
        var scale = Math.min(1, maxDim / Math.max(imgW, imgH));
        var cw = Math.floor(imgW * scale), ch = Math.floor(imgH * scale);

        // Coordinate scaling — assume preview width ~350px
        var displayW = 350;
        var displayScale = cw / displayW;
        var rx = Math.floor(Math.max(0, r.x) * displayScale);
        var ry = Math.floor(Math.max(0, r.y) * displayScale);
        var rw = Math.floor(r.w * displayScale);
        var rh = Math.floor(r.h * displayScale);
        rx = Math.min(rx, Math.max(0, cw - 1));
        ry = Math.min(ry, Math.max(0, ch - 1));
        rw = Math.max(1, Math.min(rw, cw - rx));
        rh = Math.max(1, Math.min(rh, ch - ry));

        var c = wx.createOffscreenCanvas({ type: '2d', width: cw, height: ch });
        var ctx = c.getContext('2d');
        var img = c.createImage();
        img.onload = function() {
          ctx.drawImage(img, 0, 0, cw, ch);

          if (that.data.removeMode === 'fill') {
            // Smart fill from surrounding edges
            var samples = [];
            var step = Math.max(2, Math.floor(Math.min(rw, rh) / 8));
            for (var px = rx; px < rx + rw; px += step) {
              if (ry > 0) { try{ var pd = ctx.getImageData(Math.min(px,cw-1), Math.max(0,ry-2), 1, 1); samples.push([pd.data[0],pd.data[1],pd.data[2]]); }catch(e){} }
              if (ry+rh+2 < ch) { try{ var pd = ctx.getImageData(Math.min(px,cw-1), Math.min(ry+rh+2,ch-1), 1, 1); samples.push([pd.data[0],pd.data[1],pd.data[2]]); }catch(e){} }
            }
            for (var py = ry; py < ry + rh; py += step) {
              if (rx > 0) { try{ var pd = ctx.getImageData(Math.max(0,rx-2), Math.min(py,ch-1), 1, 1); samples.push([pd.data[0],pd.data[1],pd.data[2]]); }catch(e){} }
              if (rx+rw+2 < cw) { try{ var pd = ctx.getImageData(Math.min(rx+rw+2,cw-1), Math.min(py,ch-1), 1, 1); samples.push([pd.data[0],pd.data[1],pd.data[2]]); }catch(e){} }
            }
            if (samples.length === 0) samples = [[128,128,128]];
            var sr=0,sg=0,sb=0;
            for (var i=0;i<samples.length;i++){sr+=samples[i][0];sg+=samples[i][1];sb+=samples[i][2];}
            var ar=Math.floor(sr/samples.length),ag=Math.floor(sg/samples.length),ab=Math.floor(sb/samples.length);
            ctx.fillStyle='rgb('+ar+','+ag+','+ab+')'; ctx.fillRect(rx,ry,rw,rh);
            for (var by=ry;by<ry+rh;by+=2){ctx.fillStyle='rgba('+ar+','+ag+','+ab+',0.06)';ctx.fillRect(rx-3,by,rw+6,2);}
          } else {
            // Mosaic blur
            var bs=8,samp2=[],cnt=0;
            for (var sx=Math.max(0,rx-5);sx<Math.min(cw,rx+rw+5);sx+=3){
              for(var sy=Math.max(0,ry-5);sy<Math.min(ch,ry+rh+5);sy+=3){
                if(sx>=rx&&sx<rx+rw&&sy>=ry&&sy<ry+rh)continue;
                try{var pd2=ctx.getImageData(sx,sy,1,1);samp2.push(pd2.data[0]+pd2.data[1]+pd2.data[2]);cnt++;}catch(e){}
              }
            }
            var avg=cnt>0?Math.floor(samp2.reduce(function(a,b){return a+b;},0)/(cnt*3)):160;
            for(var my=ry;my<ry+rh;my+=bs){
              for(var mx=rx;mx<rx+rw;mx+=bs){
                var v=Math.max(0,Math.min(255,avg+Math.floor(Math.random()*20-10)));
                ctx.fillStyle='rgb('+v+','+v+','+v+')';ctx.fillRect(mx,my,Math.min(bs,rx+rw-mx),Math.min(bs,ry+rh-my));
              }
            }
          }

          wx.canvasToTempFilePath({
            canvas: c, fileType: 'jpg', quality: 0.95,
            success: function(res) { that.setData({ processing: false, resultImage: res.tempFilePath }); },
            fail: function() { that.setData({ processing: false }); wx.showToast({ title: '处理失败', icon: 'none' }); }
          });
        };
        img.src = that.data.photoSrc;
      },
      fail: function() { that.setData({ processing: false }); wx.showToast({ title: '图片加载失败', icon: 'none' }); }
    });
  },

  onImageTap: function(e) {
    if (!this.data.photoSrc) return;
    var x = e.detail.x || 100, y = e.detail.y || 100;
    this.setData({
      selXInput: String(Math.max(0, x - 40)),
      selYInput: String(Math.max(0, y - 30)),
      selWInput: '80',
      selHInput: '60',
      selectRect: { x: Math.max(0, x - 40), y: Math.max(0, y - 30), w: 80, h: 60 }
    });
  },

  // ========== LAYOUT — MULTI IMAGE ==========
  setLayoutCols: function(e) { this.setData({ layoutCols: parseInt(e.currentTarget.dataset.v) }); },
  setLayoutRows: function(e) { this.setData({ layoutRows: parseInt(e.currentTarget.dataset.v) }); },

  doLayout: function() {
    var that = this;
    var images = that.data.layoutImages;

    // Fall back to single photo if multi not uploaded
    if (images.length === 0 && that.data.photoSrc) {
      images = [{ path: that.data.photoSrc, label: '照片' }];
    }

    if (images.length === 0) {
      wx.showToast({ title: '请先上传照片（点击多图上传）', icon: 'none' });
      return;
    }

    that.setData({ processing: true });

    var cols = that.data.layoutCols;
    var rows = that.data.layoutRows;
    var gap = that.data.layoutGap;
    var margin = that.data.layoutMargin;
    var totalSlots = cols * rows;

    // Use first image to determine cell size
    var firstPath = images[0].path;

    wx.getImageInfo({
      src: firstPath,
      success: function(info) {
        var cellW = info.width, cellH = info.height;
        var totalW = cols * cellW + (cols - 1) * gap + 2 * margin;
        var totalH = rows * cellH + (rows - 1) * gap + 2 * margin;

        var c = wx.createOffscreenCanvas({ type: '2d', width: totalW, height: totalH });
        var ctx = c.getContext('2d');
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, totalW, totalH);

        // Draw each image in its cell
        function drawCell(idx) {
          if (idx >= totalSlots) {
            wx.canvasToTempFilePath({
              canvas: c, fileType: 'jpg', quality: 0.95,
              success: function(res) { that.setData({ processing: false, resultImage: res.tempFilePath }); },
              fail: function() { that.setData({ processing: false }); wx.showToast({ title: '生成失败', icon: 'none' }); }
            });
            return;
          }

          var row = Math.floor(idx / cols);
          var col = idx % cols;
          var dx = margin + col * (cellW + gap);
          var dy = margin + row * (cellH + gap);

          // Cycle through images (wrap around if not enough)
          var imgIdx = idx % images.length;
          var cellImg = c.createImage();
          cellImg.onload = function() {
            ctx.drawImage(cellImg, dx, dy, cellW, cellH);
            drawCell(idx + 1);
          };
          cellImg.onerror = function() { drawCell(idx + 1); };
          cellImg.src = images[imgIdx].path;
        }

        drawCell(0);
      },
      fail: function() { that.setData({ processing: false }); wx.showToast({ title: '图片加载失败', icon: 'none' }); }
    });
  },

  // ========== PROFESSIONAL ==========
  setProfTemplate: function(e) { this.setData({ profTemplate: e.currentTarget.dataset.t }); },
  doProfessional: function() {
    this.generateIdPhotoV2('professional');
    return;
    var that = this;
    if (!that.data.photoSrc) { wx.showToast({ title: '请先上传照片', icon: 'none' }); return; }
    that.setData({ processing: true, resultImage: '' });

    professionalApi.generateProfessionalPhoto(that.data.photoSrc, that.data.profTemplate).then(function(resultPath) {
      that.setData({ processing: false, resultImage: resultPath });
      wx.showToast({ title: '形象照生成完成', icon: 'success' });
      that.updateDiagInfo({
        method: 'POST',
        url: '/api/professional-photo',
        params: { templateId: that.data.profTemplate },
        success: true,
        message: '职业形象照生成成功',
        original: that.data.photoSrc,
        result: resultPath,
        backendMode: '真人分割 + 模板合成'
      });
    }).catch(function(err) {
      console.error('[professional] generate failed:', err);
      var userMsg = that.getPortraitUserError(err, '生成失败，请重新上传符合要求的照片。');
      that.setData({ processing: false, resultImage: '' });
      wx.showModal({
        title: '生成失败',
        content: userMsg,
        showCancel: false
      });
      that.updateDiagInfo({
        method: 'POST',
        url: '/api/professional-photo',
        params: { templateId: that.data.profTemplate },
        success: false,
        message: userMsg,
        backendMode: '真人分割 + 模板合成'
      });
    });
  },

  doLocalProfessional: function() {
    var that = this;
    var templates = {
      blueSuit: { bg: '#1a73e8', bg2: '#1557b0', name: '商务蓝' },
      blackSuit: { bg: '#2c2c2c', bg2: '#1a1a1a', name: '西装黑' },
      whiteShirt: { bg: '#e8ecf2', bg2: '#d5dbe3', name: '白衬衫' }
    };
    var tpl = templates[that.data.profTemplate] || templates.blueSuit;
    var targetW = 413, targetH = 579;

    wx.getImageInfo({
      src: that.data.photoSrc,
      success: function(info) {
        var c = wx.createOffscreenCanvas({ type: '2d', width: targetW, height: targetH });
        var ctx = c.getContext('2d'); var img = c.createImage();
        img.onload = function() {
          var grad = ctx.createLinearGradient(0, 0, 0, targetH);
          grad.addColorStop(0, tpl.bg); grad.addColorStop(1, tpl.bg2);
          ctx.fillStyle = grad; ctx.fillRect(0, 0, targetW, targetH);
          var s = Math.min(targetW * 0.85 / info.width, targetH * 0.7 / info.height);
          var dw = info.width * s, dh = info.height * s;
          var dx = (targetW - dw) / 2, dy = targetH * 0.05;
          ctx.drawImage(img, dx, dy, dw, dh);
          var bgGrad = ctx.createLinearGradient(0, targetH * 0.72, 0, targetH);
          bgGrad.addColorStop(0, 'rgba(0,0,0,0)');
          bgGrad.addColorStop(0.5, 'rgba(0,0,0,0.15)');
          bgGrad.addColorStop(1, 'rgba(0,0,0,0.35)');
          ctx.fillStyle = bgGrad; ctx.fillRect(0, targetH * 0.72, targetW, targetH * 0.28);
          wx.canvasToTempFilePath({ canvas: c, fileType: 'jpg', quality: 0.95,
            success: function(res) { that.setData({ processing: false, resultImage: res.tempFilePath }); },
            fail: function() { that.setData({ processing: false }); wx.showToast({ title: '生成失败', icon: 'none' }); }
          });
        };
        img.src = that.data.photoSrc;
      },
      fail: function() { that.setData({ processing: false }); }
    });
  },

  // ========== COLLECT ==========
  loadSpecsForCollect: function() { this.setData({ collectSpecList: specs.photoSpecs }); },
  onCollectSpecSelect: function(e) {
    var spec = this.data.collectSpecList[e.detail.value];
    if (spec) { this.setData({ collectSelSpecId: spec.id }); }
  },
  doCollectCapture: function() {
    var that = this;
    wx.chooseMedia({ count: 1, mediaType: ['image'], sourceType: ['camera'],
      success: function(res) { that.setData({ photoSrc: res.tempFiles[0].tempFilePath }); }
    });
  },
  doCollectUpload: function() {
    var that = this;
    wx.chooseMedia({ count: 1, mediaType: ['image'], sourceType: ['album'],
      success: function(res) { that.setData({ photoSrc: res.tempFiles[0].tempFilePath }); }
    });
  },
  doCollectAdd: function() {
    var that = this;
    if (!that.data.photoSrc) { wx.showToast({ title: '请先拍照或上传', icon: 'none' }); return; }
    var spec = specs.getSpecById(that.data.collectSelSpecId);
    if (!spec && that.data.collectSpecList[0]) {
      spec = specs.getSpecById(that.data.collectSpecList[0].id);
    }
    if (!spec) { wx.showToast({ title: '请选择规格', icon: 'none' }); return; }
    imgSvc.savePhotoRecord({
      imagePath: that.data.photoSrc, type: 'collect', title: spec.displayName,
      specId: spec.id, specName: spec.displayName, sizeText: spec.mm + ' | ' + spec.px
    });
    wx.showToast({ title: '已添加到电子照列表', icon: 'success' });
    that.setData({ photoSrc: '' });
  }
});
