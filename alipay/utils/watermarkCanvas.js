var wx = require('./platform/alipayWxCompat.js');
/**
 * 图片去水印 Canvas 画笔与仿制图章核心状态管理器
 */

var history = [];
var historyIndex = -1;

var displayContext = null;
var maskContext = null;
var fullContext = null;

var displayCanvasNode = null;
var maskCanvasNode = null;
var fullCanvasNode = null;

var imgW = 0;
var imgH = 0;
var displayW = 0;
var displayH = 0;
var displayedImageWidth = 0;
var displayedImageHeight = 0;
var imageOffsetX = 0;
var imageOffsetY = 0;
var dpr = 1;
var strokeTransportOnly = false;

var originalImageObj = null; // 缓存原图 Image 对象以方便重绘
var originalImagePath = '';

function publishRuntimeState() {
  module.exports.imgW = imgW;
  module.exports.imgH = imgH;
  module.exports.displayW = displayW;
  module.exports.displayH = displayH;
  module.exports.displayedImageWidth = displayedImageWidth;
  module.exports.displayedImageHeight = displayedImageHeight;
  module.exports.imageOffsetX = imageOffsetX;
  module.exports.imageOffsetY = imageOffsetY;
  module.exports.displayContext = displayContext;
  module.exports.maskContext = maskContext;
  module.exports.fullContext = fullContext;
  module.exports.displayCanvasNode = displayCanvasNode;
  module.exports.maskCanvasNode = maskCanvasNode;
  module.exports.fullCanvasNode = fullCanvasNode;
}

/**
 * 初始化 Canvas
 */
function initCanvases(params) {
  return new Promise(function (resolve, reject) {
    displayCanvasNode = params.displayCanvas;
    originalImagePath = params.imagePath;
    var containerWidth = params.containerWidth || 320;
    var containerHeight = params.containerHeight || 0;
    dpr = params.dpr || 1;
    strokeTransportOnly = params.strokeTransportOnly === true;

    displayContext = displayCanvasNode.getContext('2d');

    console.log('[watermark] initCanvases started, imagePath:', originalImagePath);

    // 1. 获取图片尺寸信息
    wx.getImageInfo({
      src: originalImagePath,
      success: function (imgInfo) {
        console.log('[watermark] getImageInfo success:', imgInfo);
        imgW = imgInfo.width;
        imgH = imgInfo.height;

        // Fit long images inside the usable viewport while preserving aspect ratio.
        var fitted = calculateDisplaySize(imgW, imgH, containerWidth, containerHeight);
        displayW = fitted.width;
        displayH = fitted.height;
        displayedImageWidth = displayW;
        displayedImageHeight = displayH;
        imageOffsetX = 0;
        imageOffsetY = 0;

        console.log('[watermark] display dimensions calculated:', displayW, 'x', displayH);

        // 2. 设置 Canvas 宽高 (物理像素和逻辑像素适配)
        displayCanvasNode.width = displayW * dpr;
        displayCanvasNode.height = displayH * dpr;
        displayContext.scale(dpr, dpr);

        // 3. 动态创建离线 Canvas，完全避开 DOM 查询
        try {
          if (strokeTransportOnly) {
            maskCanvasNode = null;
            maskContext = null;
            fullCanvasNode = null;
            fullContext = null;
            console.log('[watermark] stroke transport mode: full-size offscreen canvases disabled');
          } else {
          console.log('[watermark] creating offscreen maskCanvas, size:', imgW, 'x', imgH);
          maskCanvasNode = wx.createOffscreenCanvas({ type: '2d', width: imgW, height: imgH });
          maskContext = maskCanvasNode.getContext('2d');

          console.log('[watermark] creating offscreen fullCanvas, size:', imgW, 'x', imgH);
          fullCanvasNode = wx.createOffscreenCanvas({ type: '2d', width: imgW, height: imgH });
          fullContext = fullCanvasNode.getContext('2d');
          }
        } catch (offscreenErr) {
          console.error('[watermark] failed to create offscreen canvas:', offscreenErr);
          reject(new Error('创建离线画布失败: ' + offscreenErr.message));
          return;
        }

        // 4. 异步加载原图并渲染到 displayCanvas 和 fullCanvas
        var img = displayCanvasNode.createImage();
        img.onload = function () {
          console.log('[watermark] original image object loaded successfully');
          originalImageObj = img;
          
          // 初始化渲染
          resetCanvases();
          console.log('[watermark] draw image success');
          
          // 清空历史
          history = [];
          historyIndex = -1;

          publishRuntimeState();

          resolve({
            imgW: imgW,
            imgH: imgH,
            displayW: displayW,
            displayH: displayH,
            displayedImageWidth: displayedImageWidth,
            displayedImageHeight: displayedImageHeight,
            imageOffsetX: imageOffsetX,
            imageOffsetY: imageOffsetY,
            scaleX: imgW / displayW,
            scaleY: imgH / displayH
          });
        };
        img.onerror = function (err) {
          console.error('[watermark] failed to load image object:', err);
          reject(new Error('加载图片对象失败'));
        };
        img.src = originalImagePath;
      },
      fail: function (err) {
        console.error('[watermark] getImageInfo failed:', err);
        reject(new Error('读取图片尺寸失败: ' + (err.errMsg || '')));
      }
    });
  });
}

function calculateDisplaySize(width, height, maxWidth, maxHeight) {
  var safeWidth = Math.max(1, Number(width) || 1);
  var safeHeight = Math.max(1, Number(height) || 1);
  var widthScale = Math.max(1, Number(maxWidth) || 320) / safeWidth;
  var heightScale = Number(maxHeight) > 0 ? Number(maxHeight) / safeHeight : widthScale;
  var scale = Math.min(widthScale, heightScale);
  return {
    width: Math.max(1, Math.round(safeWidth * scale)),
    height: Math.max(1, Math.round(safeHeight * scale))
  };
}

/**
 * 重置/初始化所有画布的基础内容
 */
function defReset() {
  if (!displayContext) return;

  // 原图渲染到展示画布
  displayContext.clearRect(0, 0, displayW, displayH);
  if (originalImageObj) {
    displayContext.drawImage(originalImageObj, 0, 0, displayW, displayH);
  }

  // mask 画布初始画为全黑
  if (maskContext) {
    maskContext.fillStyle = '#000000';
    maskContext.fillRect(0, 0, imgW, imgH);
  }

  // fullCanvas 渲染原尺寸原图
  if (fullContext) {
    fullContext.clearRect(0, 0, imgW, imgH);
  }
  if (fullContext && originalImageObj) {
    fullContext.drawImage(originalImageObj, 0, 0, imgW, imgH);
  }
}

function resetCanvases() {
  defReset();
}

/**
 * 重绘所有历史笔迹，用于撤销和恢复
 */
function redrawHistory() {
  if (!displayContext) return;

  resetCanvases();

  var scaleX = imgW / displayedImageWidth;
  var scaleY = imgH / displayedImageHeight;

  // 渲染直到当前 historyIndex 的笔画
  for (var i = 0; i <= historyIndex; i++) {
    var stroke = history[i];
    if (stroke.type === 'brush') {
      drawBrushStroke(stroke, scaleX, scaleY);
    } else if (stroke.type === 'stamp') {
      drawStampStroke(stroke, scaleX, scaleY);
    } else if (stroke.type === 'maskRect') {
      drawMaskRectStroke(stroke);
    }
  }
}

/**
 * 绘制手动涂抹笔画
 */
function drawBrushStroke(stroke, scaleX, scaleY) {
  if (!displayContext) return;

  var pts = stroke.points;
  if (!pts || pts.length === 0) return;

  var size = stroke.brushSize;

  // Compute robust internal scales if the passed parameters are invalid or missing
  if (!scaleX || isNaN(scaleX)) {
    scaleX = displayedImageWidth ? (imgW / displayedImageWidth) : 1;
  }
  if (!scaleY || isNaN(scaleY)) {
    scaleY = displayedImageHeight ? (imgH / displayedImageHeight) : 1;
  }

  // 1. 绘制展示画布 (半透明红线)
  displayContext.lineCap = 'round';
  displayContext.lineJoin = 'round';
  displayContext.strokeStyle = 'rgba(255, 68, 68, 0.5)';
  displayContext.lineWidth = size;

  if (pts.length === 1) {
    displayContext.beginPath();
    displayContext.arc(pts[0].x, pts[0].y, size / 2, 0, Math.PI * 2);
    displayContext.fillStyle = 'rgba(255, 68, 68, 0.5)';
    displayContext.fill();
  } else {
    displayContext.beginPath();
    displayContext.moveTo(pts[0].x, pts[0].y);
    for (var j = 1; j < pts.length; j++) {
      displayContext.lineTo(pts[j].x, pts[j].y);
    }
    displayContext.stroke();
  }

  if (!maskContext) return;

  // 2. 绘制 Mask 画布 (全白实心线)
  maskContext.lineCap = 'round';
  maskContext.lineJoin = 'round';
  maskContext.strokeStyle = '#FFFFFF';
  maskContext.lineWidth = size * scaleX;

  if (pts.length === 1) {
    maskContext.beginPath();
    var onePt = mapDisplayPointToOriginal(pts[0]);
    maskContext.arc(onePt.x, onePt.y, onePt.brushSize / 2, 0, Math.PI * 2);
    maskContext.fillStyle = '#FFFFFF';
    maskContext.fill();
  } else {
    drawMappedStrokeOnMask(maskContext, stroke);
  }
}

/**
 * 绘制仿制图章复制像素笔画
 */
function ensureFullCanvas() {
  if (fullCanvasNode && fullContext) return true;
  if (!imgW || !imgH) return false;
  try {
    fullCanvasNode = wx.createOffscreenCanvas({ type: '2d', width: imgW, height: imgH });
    fullContext = fullCanvasNode.getContext('2d');
    if (originalImageObj) fullContext.drawImage(originalImageObj, 0, 0, imgW, imgH);
    publishRuntimeState();
    return true;
  } catch (err) {
    console.error('[watermark] lazy full canvas creation failed:', err);
    return false;
  }
}

function drawStampStroke(stroke, scaleX, scaleY) {
  if (!displayContext || !ensureFullCanvas()) return;

  var pts = stroke.points;
  if (!pts || pts.length === 0) return;

  var size = stroke.brushSize;
  var sample = stroke.stampSample;
  if (!sample) return;

  // Compute robust internal scales if the passed parameters are invalid or missing
  if (!scaleX || isNaN(scaleX)) {
    scaleX = displayedImageWidth ? (imgW / displayedImageWidth) : 1;
  }
  if (!scaleY || isNaN(scaleY)) {
    scaleY = displayedImageHeight ? (imgH / displayedImageHeight) : 1;
  }

  // 计算触摸起点
  var startPt = pts[0];

  for (var i = 0; i < pts.length; i++) {
    var pt = pts[i];
    
    // 计算当前点相对于起点的偏移量
    var dx = pt.x - startPt.x;
    var dy = pt.y - startPt.y;

    // 采样点坐标
    var sx = sample.x + dx;
    var sy = sample.y + dy;

    // 1. 对 displayCanvas 进行复制
    copyPixelCirc(displayContext, displayContext, sx, sy, pt.x, pt.y, size);

    // 2. 对 fullCanvas (全尺寸) 进行复制
    var fullSize = size * scaleX;
    var fsx = sample.x * scaleX + dx * scaleX;
    var fsy = sample.y * scaleY + dy * scaleY;
    var ftx = pt.x * scaleX;
    var fty = pt.y * scaleY;
    copyPixelCirc(fullContext, fullContext, fsx, fsy, ftx, fty, fullSize);
  }
}

function drawMaskRectStroke(stroke) {
  if (!displayContext) return;
  var scaleX = displayedImageWidth ? (imgW / displayedImageWidth) : 1;
  var scaleY = displayedImageHeight ? (imgH / displayedImageHeight) : 1;
  var x = Math.max(0, Math.min(imgW, stroke.x || 0));
  var y = Math.max(0, Math.min(imgH, stroke.y || 0));
  var w = Math.max(1, Math.min(imgW - x, stroke.w || 1));
  var h = Math.max(1, Math.min(imgH - y, stroke.h || 1));

  if (maskContext) {
    maskContext.fillStyle = '#FFFFFF';
    maskContext.fillRect(x, y, w, h);
  }

  displayContext.fillStyle = 'rgba(255, 68, 68, 0.45)';
  displayContext.fillRect(x / scaleX + imageOffsetX, y / scaleY + imageOffsetY, w / scaleX, h / scaleY);
}

/**
 * 辅助方法：圆形区域像素克隆
 */
function copyPixelCirc(srcCtx, destCtx, sx, sy, tx, ty, radius) {
  srcCtx.save();
  destCtx.save();

  // 创建一个圆形裁剪路径在目标位置
  destCtx.beginPath();
  destCtx.arc(tx, ty, radius / 2, 0, Math.PI * 2);
  destCtx.clip();

  // 把源图片对应位置绘制到目标位置
  // sx, sy 是采样的圆心，所以它的左上角是 sx - radius/2, sy - radius/2
  var d = radius;
  destCtx.drawImage(
    srcCtx.canvas,
    sx - radius / 2,
    sy - radius / 2,
    d,
    d,
    tx - radius / 2,
    ty - radius / 2,
    d,
    d
  );

  destCtx.restore();
  srcCtx.restore();
}

/**
 * 记录一个完整的笔画
 */
function pushStroke(stroke) {
  // 如果当前 Index 小于历史总长度，说明之前执行过撤销，覆盖后续的历史
  if (historyIndex < history.length - 1) {
    history = history.slice(0, historyIndex + 1);
  }
  history.push(stroke);
  historyIndex++;
}

function getActiveBrushStrokes() {
  var strokes = [];
  for (var i = 0; i <= historyIndex; i++) {
    if (history[i] && (history[i].type === 'brush' || history[i].type === 'maskRect')) {
      strokes.push(history[i]);
    }
  }
  return strokes;
}

function getDisplayRect() {
  return {
    displayedImageWidth: displayedImageWidth,
    displayedImageHeight: displayedImageHeight,
    imageOffsetX: imageOffsetX,
    imageOffsetY: imageOffsetY
  };
}

function getStrokeTransportPayload() {
  var serializeStartedAt = Date.now();
  if (!imgW || !imgH || !displayedImageWidth || !displayedImageHeight) {
    throw new Error('原图或显示尺寸未初始化');
  }
  var active = getActiveBrushStrokes();
  var normalized = [];
  var estimatedPixels = 0;
  var minX = imgW;
  var minY = imgH;
  var maxX = 0;
  var maxY = 0;

  function clamp01(value) { return Math.max(0, Math.min(1, value)); }
  function includeBox(x1, y1, x2, y2) {
    minX = Math.min(minX, x1);
    minY = Math.min(minY, y1);
    maxX = Math.max(maxX, x2);
    maxY = Math.max(maxY, y2);
  }

  for (var i = 0; i < active.length; i++) {
    var stroke = active[i];
    if (stroke.type === 'maskRect') {
      var rx = clamp01((stroke.x || 0) / imgW);
      var ry = clamp01((stroke.y || 0) / imgH);
      var rw = clamp01((stroke.w || 0) / imgW);
      var rh = clamp01((stroke.h || 0) / imgH);
      normalized.push({ type: 'maskRect', x: rx, y: ry, w: rw, h: rh });
      var rectPixels = Math.max(0, Math.round(rw * imgW)) * Math.max(0, Math.round(rh * imgH));
      estimatedPixels += rectPixels;
      includeBox(rx * imgW, ry * imgH, (rx + rw) * imgW, (ry + rh) * imgH);
      continue;
    }

    var points = stroke.points || [];
    if (!points.length) continue;
    var mappedPoints = [];
    var originalPoints = [];
    var brushSizeRatio = Math.max(1 / imgW, (stroke.brushSize || 1) / displayedImageWidth);
    var originalBrush = brushSizeRatio * imgW;
    var radius = originalBrush / 2;
    var pathLength = 0;
    for (var p = 0; p < points.length; p++) {
      var nx = clamp01((points[p].x - imageOffsetX) / displayedImageWidth);
      var ny = clamp01((points[p].y - imageOffsetY) / displayedImageHeight);
      mappedPoints.push({ x: nx, y: ny });
      var ox = nx * imgW;
      var oy = ny * imgH;
      originalPoints.push({ x: ox, y: oy });
      includeBox(ox - radius, oy - radius, ox + radius, oy + radius);
      if (p > 0) {
        var dx = ox - originalPoints[p - 1].x;
        var dy = oy - originalPoints[p - 1].y;
        pathLength += Math.sqrt(dx * dx + dy * dy);
      }
    }
    estimatedPixels += Math.PI * radius * radius + pathLength * originalBrush;
    normalized.push({
      type: 'brush',
      brushSizeRatio: brushSizeRatio,
      points: mappedPoints
    });
  }

  var nonZeroPixels = Math.min(imgW * imgH, Math.max(0, Math.round(estimatedPixels)));
  var hasBounds = normalized.length > 0 && maxX > minX && maxY > minY;
  var payload = {
    version: 2,
    coordinateSpace: 'normalized',
    originalWidth: imgW,
    originalHeight: imgH,
    displayWidth: displayedImageWidth,
    displayHeight: displayedImageHeight,
    strokes: normalized
  };
  var strokesJson = JSON.stringify(payload);
  return {
    payload: payload,
    strokesJson: strokesJson,
    serializeMs: Date.now() - serializeStartedAt,
    transportBytes: unescape(encodeURIComponent(strokesJson)).length,
    width: imgW,
    height: imgH,
    nonZeroPixels: nonZeroPixels,
    maskRatio: nonZeroPixels / (imgW * imgH),
    strokesCount: normalized.length,
    previewPath: '',
    boundingBox: hasBounds ? {
      x: Math.max(0, Math.floor(minX)),
      y: Math.max(0, Math.floor(minY)),
      width: Math.min(imgW, Math.ceil(maxX)) - Math.max(0, Math.floor(minX)),
      height: Math.min(imgH, Math.ceil(maxY)) - Math.max(0, Math.floor(minY))
    } : null,
    displayRect: getDisplayRect()
  };
}

function mapDisplayPointToOriginal(point) {
  var scaleX = imgW / displayedImageWidth;
  var scaleY = imgH / displayedImageHeight;
  var maxScale = Math.max(scaleX, scaleY);
  var x = (point.x - imageOffsetX) * scaleX;
  var y = (point.y - imageOffsetY) * scaleY;
  x = Math.max(0, Math.min(imgW - 1, x));
  y = Math.max(0, Math.min(imgH - 1, y));
  return {
    x: x,
    y: y,
    brushSize: Math.max(1, (point.brushSize || 1) * maxScale)
  };
}

function drawMappedStrokeOnMask(ctx, stroke) {
  var pts = stroke.points || [];
  if (!ctx || pts.length === 0) return;
  var mappedSize = (stroke.brushSize || 1) * Math.max(imgW / displayedImageWidth, imgH / displayedImageHeight);

  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.strokeStyle = '#FFFFFF';
  ctx.fillStyle = '#FFFFFF';
  ctx.lineWidth = Math.max(1, mappedSize);

  if (pts.length === 1) {
    var single = mapDisplayPointToOriginal({ x: pts[0].x, y: pts[0].y, brushSize: stroke.brushSize });
    ctx.beginPath();
    ctx.arc(single.x, single.y, single.brushSize / 2, 0, Math.PI * 2);
    ctx.fill();
    return;
  }

  ctx.beginPath();
  var first = mapDisplayPointToOriginal({ x: pts[0].x, y: pts[0].y, brushSize: stroke.brushSize });
  ctx.moveTo(first.x, first.y);
  for (var i = 1; i < pts.length; i++) {
    var mapped = mapDisplayPointToOriginal({ x: pts[i].x, y: pts[i].y, brushSize: stroke.brushSize });
    ctx.lineTo(mapped.x, mapped.y);
  }
  ctx.stroke();
}

function createBlackWhiteMaskCanvas() {
  if (!imgW || !imgH) {
    throw new Error('原图尺寸未初始化');
  }
  if (!displayedImageWidth || !displayedImageHeight) {
    throw new Error('预览图显示尺寸未初始化');
  }

  var strokes = getActiveBrushStrokes();
  var canvas = wx.createOffscreenCanvas({ type: '2d', width: imgW, height: imgH });
  var ctx = canvas.getContext('2d');
  ctx.fillStyle = '#000000';
  ctx.fillRect(0, 0, imgW, imgH);

  for (var i = 0; i < strokes.length; i++) {
    if (strokes[i].type === 'maskRect') {
      ctx.fillStyle = '#FFFFFF';
      ctx.fillRect(strokes[i].x, strokes[i].y, strokes[i].w, strokes[i].h);
    } else {
      drawMappedStrokeOnMask(ctx, strokes[i]);
    }
  }

  return { canvas: canvas, ctx: ctx, strokes: strokes };
}

function getMaskStats(ctx) {
  var imgData = ctx.getImageData(0, 0, imgW, imgH);
  var data = imgData.data;
  var nonZeroPixels = 0;
  for (var i = 0; i < data.length; i += 4) {
    if (data[i] > 10 || data[i + 1] > 10 || data[i + 2] > 10) {
      nonZeroPixels++;
    }
  }
  return {
    maskWidth: imgW,
    maskHeight: imgH,
    nonZeroPixels: nonZeroPixels,
    maskRatio: nonZeroPixels / (imgW * imgH)
  };
}

function canvasToTempPath(canvas, fileType, quality) {
  return new Promise(function(resolve, reject) {
    var successCb = function(res) { resolve(res.tempFilePath); };
    var failCb = function(err) { reject(new Error('导出画布失败: ' + (err.errMsg || ''))); };

    if (canvas && typeof canvas.toTempFilePath === 'function') {
      canvas.toTempFilePath({
        fileType: fileType || 'png',
        quality: quality || 1,
        success: successCb,
        fail: function() {
          wx.canvasToTempFilePath({
            canvas: canvas,
            fileType: fileType || 'png',
            quality: quality || 1,
            success: successCb,
            fail: failCb
          });
        }
      });
    } else {
      wx.canvasToTempFilePath({
        canvas: canvas,
        fileType: fileType || 'png',
        quality: quality || 1,
        success: successCb,
        fail: failCb
      });
    }
  });
}

function exportValidatedMask() {
  return new Promise(function(resolve, reject) {
    try {
      var generated = createBlackWhiteMaskCanvas();
      var stats = getMaskStats(generated.ctx);

      console.log('[watermark] originalSize:', imgW, imgH);
      console.log('[watermark] displayRect:', displayedImageWidth, displayedImageHeight, imageOffsetX, imageOffsetY);
      console.log('[watermark] strokes count:', generated.strokes.length);
      console.log('[watermark] mask size:', stats.maskWidth, stats.maskHeight);
      console.log('[watermark] mask nonZero pixels:', stats.nonZeroPixels);
      console.log('[watermark] mask ratio:', stats.maskRatio);

      if (generated.strokes.length === 0 || stats.nonZeroPixels <= 0) {
        reject(new Error('请先在水印位置涂抹后再处理。'));
        return;
      }

      canvasToTempPath(generated.canvas, 'png', 1).then(function(maskPath) {
        resolve({
          tempFilePath: maskPath,
          previewPath: maskPath,
          width: stats.maskWidth,
          height: stats.maskHeight,
          nonZeroPixels: stats.nonZeroPixels,
          maskRatio: stats.maskRatio,
          strokesCount: generated.strokes.length,
          displayRect: getDisplayRect()
        });
      }).catch(reject);
    } catch (err) {
      reject(err);
    }
  });
}

/**
 * 撤销
 */
function undo() {
  if (historyIndex >= 0) {
    historyIndex--;
    redrawHistory();
    return true;
  }
  return false;
}

/**
 * 重做
 */
function redo() {
  if (historyIndex < history.length - 1) {
    historyIndex++;
    redrawHistory();
    return true;
  }
  return false;
}

/**
 * 清除所有笔画
 */
function clearAll() {
  history = [];
  historyIndex = -1;
  resetCanvases();
}

/**
 * 检测当前 Mask 是否有涂抹内容
 */
function checkHasPaint() {
  return getActiveBrushStrokes().length > 0;
}

/**
 * 导出 Mask 图片文件路径
 */
function exportMask() {
  return new Promise(function (resolve, reject) {
    if (!maskCanvasNode) { reject(new Error('Canvas 未初始化')); return; }
    
    var successCb = function (res) {
      resolve(res.tempFilePath);
    };
    var failCb = function (err) {
      reject(new Error('导出遮罩图片失败: ' + (err.errMsg || '')));
    };

    if (typeof maskCanvasNode.toTempFilePath === 'function') {
      console.log('[watermark] using maskCanvasNode.toTempFilePath');
      maskCanvasNode.toTempFilePath({
        fileType: 'png',
        success: successCb,
        fail: function(err) {
          console.warn('[watermark] maskCanvasNode.toTempFilePath failed, trying wx.canvasToTempFilePath', err);
          wx.canvasToTempFilePath({
            canvas: maskCanvasNode,
            fileType: 'png',
            success: successCb,
            fail: failCb
          });
        }
      });
    } else {
      console.log('[watermark] maskCanvasNode.toTempFilePath is not a function, using wx.canvasToTempFilePath');
      wx.canvasToTempFilePath({
        canvas: maskCanvasNode,
        fileType: 'png',
        success: successCb,
        fail: failCb
      });
    }
  });
}

/**
 * 导出克隆图章处理后的结果图
 */
function exportResult() {
  return new Promise(function (resolve, reject) {
    if (!fullCanvasNode) { reject(new Error('Canvas 未初始化')); return; }
    
    var successCb = function (res) {
      resolve(res.tempFilePath);
    };
    var failCb = function (err) {
      reject(new Error('导出处理图片失败: ' + (err.errMsg || '')));
    };

    if (typeof fullCanvasNode.toTempFilePath === 'function') {
      console.log('[watermark] using fullCanvasNode.toTempFilePath');
      fullCanvasNode.toTempFilePath({
        fileType: 'jpg',
        quality: 0.95,
        success: successCb,
        fail: function(err) {
          console.warn('[watermark] fullCanvasNode.toTempFilePath failed, trying wx.canvasToTempFilePath', err);
          wx.canvasToTempFilePath({
            canvas: fullCanvasNode,
            fileType: 'jpg',
            quality: 0.95,
            success: successCb,
            fail: failCb
          });
        }
      });
    } else {
      console.log('[watermark] fullCanvasNode.toTempFilePath is not a function, using wx.canvasToTempFilePath');
      wx.canvasToTempFilePath({
        canvas: fullCanvasNode,
        fileType: 'jpg',
        quality: 0.95,
        success: successCb,
        fail: failCb
      });
    }
  });
}

module.exports = {
  calculateDisplaySize: calculateDisplaySize,
  initCanvases: initCanvases,
  pushStroke: pushStroke,
  undo: undo,
  redo: redo,
  clearAll: clearAll,
  redrawHistory: redrawHistory,
  drawBrushStroke: drawBrushStroke,
  drawStampStroke: drawStampStroke,
  checkHasPaint: checkHasPaint,
  exportMask: exportMask,
  exportValidatedMask: exportValidatedMask,
  exportResult: exportResult,
  copyPixelCirc: copyPixelCirc,
  getActiveBrushStrokes: getActiveBrushStrokes,
  getDisplayRect: getDisplayRect,
  getStrokeTransportPayload: getStrokeTransportPayload,
  getHistoryCount: function() { return historyIndex + 1; },
  getFutureCount: function() { return history.length - 1 - historyIndex; },
  displayContext: null,
  maskContext: null,
  fullContext: null,
  displayCanvasNode: null,
  maskCanvasNode: null,
  fullCanvasNode: null,
  imgW: 0,
  imgH: 0,
  displayW: 0,
  displayH: 0,
  displayedImageWidth: 0,
  displayedImageHeight: 0,
  imageOffsetX: 0,
  imageOffsetY: 0
};
