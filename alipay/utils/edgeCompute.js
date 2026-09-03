var wx = require('./platform/alipayWxCompat.js');
var apiConfig = require('./apiConfig.js');

function getRuntimeEnvVersion() {
  var info = apiConfig.getApiRuntimeInfo ? apiConfig.getApiRuntimeInfo() : null;
  return info && info.envVersion ? info.envVersion : '';
}

function getFeatureFlags() {
  var envVersion = getRuntimeEnvVersion();
  return {
    ENABLE_EDGE_BG_COMPOSE: envVersion === 'develop',
    ENABLE_EDGE_WATERMARK_ROI: envVersion === 'develop',
    ENABLE_EDGE_MATTING_EXPERIMENTAL: false
  };
}

function getCapabilities() {
  var sys = {};
  try {
    sys = wx.getSystemInfoSync ? wx.getSystemInfoSync() : {};
  } catch (e) {}
  var totalMemory = Number(sys.memorySize || sys.totalMemory || 0);
  var memoryClass = totalMemory >= 0 ? (totalMemory >= 768 ? 'high' : (totalMemory >= 512 ? 'medium' : 'low')) : 'unknown';
  return {
    canvas: !!(wx && wx.createOffscreenCanvas),
    worker: !!(wx && wx.createWorker),
    wasm: !!(typeof WebAssembly !== 'undefined'),
    memoryClass: memoryClass,
    platform: sys.platform || '',
    system: sys.system || '',
    model: sys.model || ''
  };
}

function chooseExecutionRoute(kind) {
  var flags = getFeatureFlags();
  var caps = getCapabilities();
  if (kind === 'idPhotoBgCompose') {
    return flags.ENABLE_EDGE_BG_COMPOSE && caps.canvas ? 'edge' : 'cloud';
  }
  if (kind === 'watermarkRoi') {
    return flags.ENABLE_EDGE_WATERMARK_ROI && caps.canvas ? 'edge' : 'cloud';
  }
  if (kind === 'mattingExperiment') {
    return flags.ENABLE_EDGE_MATTING_EXPERIMENTAL && caps.wasm && caps.worker && caps.canvas ? 'edge' : 'cloud';
  }
  return 'cloud';
}

function _createCanvas(width, height) {
  if (!wx || !wx.createOffscreenCanvas) throw new Error('OffscreenCanvas unavailable');
  return wx.createOffscreenCanvas({ type: '2d', width: Math.max(1, Math.round(width)), height: Math.max(1, Math.round(height)) });
}

function _loadImage(canvas, src) {
  return new Promise(function(resolve, reject) {
    var image = canvas.createImage();
    image.onload = function() { resolve(image); };
    image.onerror = function(err) { reject(err || new Error('image load failed')); };
    image.src = src;
  });
}

function _exportCanvas(canvas, fileType, quality) {
  return new Promise(function(resolve, reject) {
    var options = {
      fileType: fileType || 'png',
      quality: quality || 1,
      success: function(res) { resolve(res.tempFilePath); },
      fail: reject
    };
    if (canvas && typeof canvas.toTempFilePath === 'function') {
      canvas.toTempFilePath(options);
      return;
    }
    if (wx.canvasToTempFilePath) {
      options.canvas = canvas;
      wx.canvasToTempFilePath(options);
      return;
    }
    reject(new Error('canvas export unsupported'));
  });
}

function composeForegroundToBackground(options) {
  options = options || {};
  var foregroundSrc = options.foregroundUrl || options.foregroundPath || '';
  var width = Math.max(1, Math.round(Number(options.widthPx || options.width || 0)));
  var height = Math.max(1, Math.round(Number(options.heightPx || options.height || 0)));
  var bg = options.bgColor || '#1a73e8';
  if (!foregroundSrc) return Promise.reject(new Error('foreground source missing'));
  var canvas = _createCanvas(width, height);
  var ctx = canvas.getContext('2d');
  return _loadImage(canvas, foregroundSrc).then(function(img) {
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, width, height);
    ctx.drawImage(img, 0, 0, width, height);
    return _exportCanvas(canvas, options.outputType || 'png', 1);
  });
}

function cropImageRegion(options) {
  options = options || {};
  var imagePath = options.imagePath || '';
  var roi = options.roi || {};
  var roiX = Math.max(0, Math.round(Number(roi.x || 0)));
  var roiY = Math.max(0, Math.round(Number(roi.y || 0)));
  var roiW = Math.max(1, Math.round(Number(roi.width || 0)));
  var roiH = Math.max(1, Math.round(Number(roi.height || 0)));
  if (!imagePath) return Promise.reject(new Error('imagePath missing'));
  var canvas = _createCanvas(roiW, roiH);
  var ctx = canvas.getContext('2d');
  return _loadImage(canvas, imagePath).then(function(img) {
    ctx.drawImage(img, roiX, roiY, roiW, roiH, 0, 0, roiW, roiH);
    return _exportCanvas(canvas, options.outputType || 'png', 1);
  });
}

function pasteRoiBack(options) {
  options = options || {};
  var basePath = options.baseImagePath || '';
  var roiPath = options.roiImagePath || '';
  var roi = options.roi || {};
  var baseWidth = Math.max(1, Math.round(Number(options.baseWidth || 0)));
  var baseHeight = Math.max(1, Math.round(Number(options.baseHeight || 0)));
  var x = Math.max(0, Math.round(Number(roi.x || 0)));
  var y = Math.max(0, Math.round(Number(roi.y || 0)));
  var w = Math.max(1, Math.round(Number(roi.width || 0)));
  var h = Math.max(1, Math.round(Number(roi.height || 0)));
  if (!basePath || !roiPath) return Promise.reject(new Error('roi paste source missing'));
  var canvas = _createCanvas(baseWidth, baseHeight);
  var ctx = canvas.getContext('2d');
  return Promise.all([_loadImage(canvas, basePath), _loadImage(canvas, roiPath)]).then(function(images) {
    var baseImg = images[0];
    var roiImg = images[1];
    ctx.drawImage(baseImg, 0, 0, baseWidth, baseHeight);
    ctx.drawImage(roiImg, x, y, w, h);
    return _exportCanvas(canvas, options.outputType || 'png', 1);
  });
}

function _clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function _brushPxFromStroke(stroke, imageWidth) {
  return Math.max(1, Math.round(Number(stroke && stroke.brushSizeRatio || 0.01) * Math.max(1, imageWidth)));
}

function computeStrokeBoundingBox(strokeInfo) {
  var payload = (strokeInfo && strokeInfo.payload) || {};
  var strokes = payload.strokes || [];
  var imgW = Math.max(1, Math.round(Number(payload.originalWidth || 0)));
  var imgH = Math.max(1, Math.round(Number(payload.originalHeight || 0)));
  var minX = imgW;
  var minY = imgH;
  var maxX = 0;
  var maxY = 0;
  var maxBrush = 1;

  function includeBox(x1, y1, x2, y2) {
    minX = Math.min(minX, x1);
    minY = Math.min(minY, y1);
    maxX = Math.max(maxX, x2);
    maxY = Math.max(maxY, y2);
  }

  for (var i = 0; i < strokes.length; i++) {
    var stroke = strokes[i] || {};
    if (stroke.type === 'maskRect') {
      var rx = _clamp(Number(stroke.x || 0), 0, 1);
      var ry = _clamp(Number(stroke.y || 0), 0, 1);
      var rw = _clamp(Number(stroke.w || 0), 0, 1);
      var rh = _clamp(Number(stroke.h || 0), 0, 1);
      includeBox(rx * imgW, ry * imgH, (rx + rw) * imgW, (ry + rh) * imgH);
      continue;
    }
    var points = stroke.points || [];
    if (!points.length) continue;
    var brushPx = _brushPxFromStroke(stroke, imgW);
    maxBrush = Math.max(maxBrush, brushPx);
    var radius = brushPx / 2;
    for (var p = 0; p < points.length; p++) {
      var pt = points[p] || {};
      var ox = _clamp(Number(pt.x || 0), 0, 1) * imgW;
      var oy = _clamp(Number(pt.y || 0), 0, 1) * imgH;
      includeBox(ox - radius, oy - radius, ox + radius, oy + radius);
    }
  }

  if (maxX <= minX || maxY <= minY) {
    return null;
  }

  var baseMargin = Math.max(8, Math.round(Math.min(imgW, imgH) * 0.02));
  var brushMargin = Math.round(maxBrush * 1.4);
  var dynamicMargin = Math.max(baseMargin, brushMargin);
  var x = Math.max(0, Math.floor(minX - dynamicMargin));
  var y = Math.max(0, Math.floor(minY - dynamicMargin));
  var right = Math.min(imgW, Math.ceil(maxX + dynamicMargin));
  var bottom = Math.min(imgH, Math.ceil(maxY + dynamicMargin));
  return {
    x: x,
    y: y,
    width: Math.max(1, right - x),
    height: Math.max(1, bottom - y),
    margin: dynamicMargin,
    brushPx: maxBrush,
    imageWidth: imgW,
    imageHeight: imgH
  };
}

function buildRoiStrokePayload(strokeInfo, roi) {
  var payload = (strokeInfo && strokeInfo.payload) || {};
  var strokes = payload.strokes || [];
  var imgW = Math.max(1, Math.round(Number(payload.originalWidth || 0)));
  var imgH = Math.max(1, Math.round(Number(payload.originalHeight || 0)));
  var roiX = Math.max(0, Math.round(Number(roi.x || 0)));
  var roiY = Math.max(0, Math.round(Number(roi.y || 0)));
  var roiW = Math.max(1, Math.round(Number(roi.width || 0)));
  var roiH = Math.max(1, Math.round(Number(roi.height || 0)));
  var normalized = [];

  for (var i = 0; i < strokes.length; i++) {
    var stroke = strokes[i] || {};
    if (stroke.type === 'maskRect') {
      var x = _clamp(Number(stroke.x || 0), 0, 1) * imgW;
      var y = _clamp(Number(stroke.y || 0), 0, 1) * imgH;
      var w = _clamp(Number(stroke.w || 0), 0, 1) * imgW;
      var h = _clamp(Number(stroke.h || 0), 0, 1) * imgH;
      var x2 = Math.max(roiX, Math.min(roiX + roiW, x + w));
      var y2 = Math.max(roiY, Math.min(roiY + roiH, y + h));
      var x1 = Math.max(roiX, Math.min(roiX + roiW, x));
      var y1 = Math.max(roiY, Math.min(roiY + roiH, y));
      if (x2 > x1 && y2 > y1) {
        normalized.push({
          type: 'maskRect',
          x: (x1 - roiX) / roiW,
          y: (y1 - roiY) / roiH,
          w: (x2 - x1) / roiW,
          h: (y2 - y1) / roiH
        });
      }
      continue;
    }
    var points = stroke.points || [];
    if (!points.length) continue;
    var brushPx = _brushPxFromStroke(stroke, imgW);
    var roiBrushRatio = brushPx / roiW;
    var mapped = [];
    for (var p = 0; p < points.length; p++) {
      var pt = points[p] || {};
      var ox = _clamp(Number(pt.x || 0), 0, 1) * imgW;
      var oy = _clamp(Number(pt.y || 0), 0, 1) * imgH;
      mapped.push({
        x: _clamp((ox - roiX) / roiW, 0, 1),
        y: _clamp((oy - roiY) / roiH, 0, 1)
      });
    }
    normalized.push({
      type: 'brush',
      brushSizeRatio: roiBrushRatio,
      points: mapped
    });
  }

  var roiPayload = {
    version: 2,
    coordinateSpace: 'normalized',
    originalWidth: roiW,
    originalHeight: roiH,
    displayWidth: roiW,
    displayHeight: roiH,
    strokes: normalized
  };
  var roiStrokesJson = JSON.stringify(roiPayload);
  return {
    payload: roiPayload,
    strokesJson: roiStrokesJson,
    transportBytes: unescape(encodeURIComponent(roiStrokesJson)).length,
    roi: {
      x: roiX,
      y: roiY,
      width: roiW,
      height: roiH
    }
  };
}

function createWatermarkRoiPackage(strokeInfo) {
  var bbox = computeStrokeBoundingBox(strokeInfo);
  if (!bbox) return null;
  var payload = (strokeInfo && strokeInfo.payload) || {};
  var imgW = Math.max(1, Math.round(Number(payload.originalWidth || 0)));
  var imgH = Math.max(1, Math.round(Number(payload.originalHeight || 0)));
  var roiPixels = bbox.width * bbox.height;
  var originalPixels = imgW * imgH;
  if (!originalPixels || roiPixels / originalPixels > 0.62) {
    return {
      route: 'cloud',
      roiTooLarge: true,
      bbox: bbox,
      originalPixels: originalPixels,
      roiPixels: roiPixels,
      pixelReductionRatio: originalPixels ? Math.round((1 - roiPixels / originalPixels) * 1000) / 1000 : 0
    };
  }
  return {
    route: chooseExecutionRoute('watermarkRoi'),
    bbox: bbox,
    originalPixels: originalPixels,
    roiPixels: roiPixels,
    pixelReductionRatio: originalPixels ? Math.round((1 - roiPixels / originalPixels) * 1000) / 1000 : 0,
    roiStrokeInfo: buildRoiStrokePayload(strokeInfo, bbox)
  };
}

module.exports = {
  getFeatureFlags: getFeatureFlags,
  getCapabilities: getCapabilities,
  chooseExecutionRoute: chooseExecutionRoute,
  composeForegroundToBackground: composeForegroundToBackground,
  cropImageRegion: cropImageRegion,
  pasteRoiBack: pasteRoiBack,
  computeStrokeBoundingBox: computeStrokeBoundingBox,
  buildRoiStrokePayload: buildRoiStrokePayload,
  createWatermarkRoiPackage: createWatermarkRoiPackage
};
