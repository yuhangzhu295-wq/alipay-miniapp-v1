var platform = require('./alipay.js');
var compat = require('./alipayWxCompat.js');

function getCanvas2D(page, id) {
  return new Promise(function(resolve, reject) {
    if (!platform.hasMy() || typeof my.createSelectorQuery !== 'function') {
      reject(new Error('Alipay Canvas 2D selector query is unavailable'));
      return;
    }
    try {
      my.createSelectorQuery().select('#' + id).node().exec(function(results) {
        var result = results && results[0];
        var canvas = result && result.node;
        if (!canvas || typeof canvas.getContext !== 'function') {
          reject(new Error('Alipay Canvas 2D node not ready: ' + id));
          return;
        }
        var context = canvas.getContext('2d');
        if (!context) {
          reject(new Error('Alipay Canvas 2D context unavailable: ' + id));
          return;
        }
        resolve({ canvas: canvas, context: context, width: Number(result.width || canvas.width || 0), height: Number(result.height || canvas.height || 0) });
      });
    } catch (err) {
      reject(err);
    }
  });
}

function createOffscreenCanvas(width, height) {
  if (!compat.createOffscreenCanvas) throw new Error('Alipay OffscreenCanvas is unavailable');
  var canvas = compat.createOffscreenCanvas({
    type: '2d',
    width: Math.max(1, Math.round(Number(width || 1))),
    height: Math.max(1, Math.round(Number(height || 1)))
  });
  if (!canvas || typeof canvas.getContext !== 'function') throw new Error('Alipay OffscreenCanvas creation failed');
  return canvas;
}

/**
 * Resolve a PAGE-LEVEL <canvas type="2d"> node by id and size its backing store.
 *
 * WHY THIS EXISTS (Alipay has no offscreen-export equivalent):
 *   Alipay's official API table types `my.canvasToTempFilePath`'s `canvas` parameter as
 *   `canvas?: CanvasContext` — i.e. a canvas obtained from a real page <canvas> component,
 *   NOT an OffscreenCanvas. `my.createOffscreenCanvas` is documented to return an
 *   `OffscreenCanvas` and the API table exposes NO export method on it (no
 *   `toTempFilePath`). Measured at runtime: calling `my.canvasToTempFilePath({canvas})`
 *   with an OffscreenCanvas invokes `success` with an EMPTY object (`keys: []`), so no
 *   temp path is ever produced.
 *
 *   Therefore the WeChat strategy ("wx.createOffscreenCanvas + canvas.toTempFilePath")
 *   cannot be reproduced on Alipay. The Alipay-native equivalent is to take the node of a
 *   real page canvas via `my.createSelectorQuery().select('#id').node()` (which is also
 *   exactly what the deprecated `my._createCanvas` now tells you to do) and export THAT.
 *
 * Source: <Alipay IDE>\resources\app\extensions\alipay.minicode-<v>\
 *         node_modules\@alipay\mini-language-server\dist\data\default\mini-api.json
 *
 * The canvas may be styled 1px x 1px off-screen: for a 2d canvas the backing store size is
 * set by `canvas.width` / `canvas.height`, which is independent of the CSS box.
 */
function createPageCanvas(canvasId, width, height) {
  return getCanvas2D(null, canvasId).then(function(entry) {
    var canvas = entry.canvas;
    var w = Math.max(1, Math.round(Number(width || 0) || entry.width || 1));
    var h = Math.max(1, Math.round(Number(height || 0) || entry.height || 1));
    try {
      canvas.width = w;
      canvas.height = h;
    } catch (err) {}
    var context = canvas.getContext('2d');
    if (!context) throw new Error('Alipay page Canvas 2D context unavailable: ' + canvasId);
    return { canvas: canvas, context: context, width: w, height: h, source: 'page-canvas' };
  });
}

function createImage(canvas, path) {
  return new Promise(function(resolve, reject) {
    try {
      var image = canvas.createImage();
      image.onload = function() { resolve(image); };
      image.onerror = function(err) { reject(err || new Error('Alipay Canvas image load failed')); };
      image.src = path;
    } catch (err) {
      reject(err);
    }
  });
}

function makeExportError(message, code, raw) {
  var error = new Error(message);
  error.code = code;
  error.rawResultType = raw === null ? 'null' : typeof raw;
  error.rawResultKeys = raw && typeof raw === 'object' ? Object.keys(raw) : [];
  error.errMsg = raw && typeof raw === 'object' ? String(raw.errMsg || raw.errorMessage || raw.message || '') : '';
  return error;
}

function exportCanvas(canvas, options) {
  options = options || {};
  return new Promise(function(resolve, reject) {
    var next = Object.assign({}, options, {
      success: function(result) {
        var normalized = compat.normalizeTempFileResult(result);
        if (!normalized.tempFilePath) {
          reject(makeExportError(
            'Alipay Canvas export returned no temporary path',
            'ALIPAY_CANVAS_EXPORT_PATH_MISSING',
            result
          ));
          return;
        }
        resolve(normalized);
      },
      fail: function(err) {
        reject(makeExportError(
          'Alipay Canvas export failed',
          'ALIPAY_CANVAS_EXPORT_FAILED',
          err
        ));
      }
    });
    // my.canvasToTempFilePath declares x/y/width/height/destWidth/destHeight as REQUIRED
    // (optional:false) in the official API table. Supply them from the canvas backing store
    // when the caller did not, so the export is always fully specified.
    try {
      var cw = Math.max(1, Math.round(Number(canvas && canvas.width || 0) || 1));
      var ch = Math.max(1, Math.round(Number(canvas && canvas.height || 0) || 1));
      if (next.x === undefined) next.x = 0;
      if (next.y === undefined) next.y = 0;
      if (next.width === undefined) next.width = cw;
      if (next.height === undefined) next.height = ch;
      if (next.destWidth === undefined) next.destWidth = next.width;
      if (next.destHeight === undefined) next.destHeight = next.height;
      if (next.fileType === undefined) next.fileType = 'png';
      if (next.quality === undefined) next.quality = 1;
    } catch (err) {}
    try {
      if (canvas && typeof canvas.toTempFilePath === 'function') {
        canvas.toTempFilePath(next);
        return;
      }
      compat.canvasToTempFilePath(Object.assign({}, next, { canvas: canvas }));
    } catch (err) {
      reject(err);
    }
  });
}

/**
 * Create a canvas suitable for a one-shot render + export, preferring an Alipay-native
 * page-level canvas node (the only exportable canvas on this platform) and falling back to
 * an offscreen canvas only when no page canvas is reachable.
 *
 * @param {Object}  opts
 * @param {string=} opts.pageCanvasId  id of a <canvas type="2d"> declared on the CURRENT page
 * @param {number}  opts.width         target backing-store width
 * @param {number}  opts.height        target backing-store height
 */
function resolveWorkCanvas(opts) {
  opts = opts || {};
  var width = Math.max(1, Math.round(Number(opts.width || 1)));
  var height = Math.max(1, Math.round(Number(opts.height || 1)));
  var pageCanvasId = opts.pageCanvasId;
  if (pageCanvasId && platform.hasMy() && typeof my.createSelectorQuery === 'function') {
    return createPageCanvas(pageCanvasId, width, height).catch(function(err) {
      // Page canvas unreachable (wrong page, not yet rendered, or selector query refused).
      // Record why, then degrade to the offscreen path so the caller sees one consistent
      // error shape instead of two different failure modes.
      var fallback = createOffscreenCanvas(width, height);
      fallback.__pageCanvasError = err;
      return { canvas: fallback, context: fallback.getContext('2d'), width: width, height: height, source: 'offscreen-fallback' };
    });
  }
  var offscreen = createOffscreenCanvas(width, height);
  return Promise.resolve({ canvas: offscreen, context: offscreen.getContext('2d'), width: width, height: height, source: 'offscreen' });
}

function getCanvasSize(canvas) {
  return { width: Number(canvas && canvas.width || 0), height: Number(canvas && canvas.height || 0) };
}

function release(canvas) {
  if (!canvas) return;
  try { canvas.width = 0; canvas.height = 0; } catch (err) {}
}

module.exports = {
  getCanvas2D: getCanvas2D,
  createOffscreenCanvas: createOffscreenCanvas,
  createPageCanvas: createPageCanvas,
  createImage: createImage,
  exportCanvas: exportCanvas,
  resolveWorkCanvas: resolveWorkCanvas,
  getCanvasSize: getCanvasSize,
  release: release
};
