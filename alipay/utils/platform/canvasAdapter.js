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
  createImage: createImage,
  exportCanvas: exportCanvas,
  getCanvasSize: getCanvasSize,
  release: release
};
