var wx = require('./platform/alipayWxCompat.js');
/**
 * 目标 KB 压缩器
 * 双循环：quality ↓ → sizeFactor ↓ → 直到接近目标 KB
 */
function compressToTargetKB(opts) {
  var imagePath = opts.imagePath;
  var targetKB = opts.targetKB || 100;
  var qualityStart = opts.qualityStart || 0.92;
  var qualityMin = opts.qualityMin || 0.15;
  var maxLoop = opts.maxLoop || 25;
  var onProgress = opts.onProgress || function() {};

  return new Promise(function(resolve, reject) {
    wx.getImageInfo({
      src: imagePath,
      success: function(info) {
        var origW = info.width, origH = info.height;
        var quality = qualityStart;
        var scale = 1.0;
        var bestResult = null, bestKb = Infinity;

        function tryCompress(loop) {
          if (loop >= maxLoop) {
            if (bestResult) {
              onProgress({ phase: 'done', actualKb: bestKb });
              resolve({ tempFilePath: bestResult, actualKb: bestKb, targetKb: targetKB, finalQuality: quality, finalScale: scale });
            } else {
              reject(new Error('压缩未产生有效结果'));
            }
            return;
          }

          var cw = Math.max(10, Math.floor(origW * scale));
          var ch = Math.max(10, Math.floor(origH * scale));

          try {
            var canvas = wx.createOffscreenCanvas({ type: '2d', width: cw, height: ch });
            var ctx = canvas.getContext('2d');
            var img = canvas.createImage();

            function onLoad() {
              ctx.drawImage(img, 0, 0, cw, ch);

              wx.canvasToTempFilePath({
                canvas: canvas, fileType: 'jpg', quality: quality,
                success: function(res) {
                  wx.getFileInfo({
                    filePath: res.tempFilePath,
                    success: function(fi) {
                      var actualKb = fi.size / 1024;
                      if (actualKb < bestKb) {
                        bestResult = res.tempFilePath;
                        bestKb = actualKb;
                      }
                      onProgress({ phase: 'iterate', loop: loop, quality: quality, scale: scale, actualKb: actualKb });

                      if (actualKb <= targetKB * 1.05) {
                        // Close enough — done
                        onProgress({ phase: 'done', actualKb: actualKb });
                        resolve({ tempFilePath: res.tempFilePath, actualKb: actualKb, targetKb: targetKB, outputW: cw, outputH: ch });
                        return;
                      }

                      // Adjust: quality first, then size
                      var nextQ = quality, nextScale = scale;
                      if (quality > qualityMin) {
                        nextQ = Math.max(qualityMin, quality - 0.06);
                      } else {
                        nextQ = 0.65;
                        nextScale = Math.max(0.2, scale * 0.85);
                      }
                      quality = nextQ;
                      scale = nextScale;
                      tryCompress(loop + 1);
                    },
                    fail: function() {
                      // Fall back to result anyway
                      bestResult = res.tempFilePath;
                      bestKb = 9999;
                      tryCompress(loop + 1);
                    }
                  });
                },
                fail: function() {
                  reject(new Error('canvasToTempFilePath 失败'));
                }
              });
            }

            function onError() { reject(new Error('图片渲染失败')); }

            img.onload = onLoad;
            img.onerror = onError;
            img.src = imagePath;
          } catch(e) {
            reject(e);
          }
        }

        tryCompress(0);
      },
      fail: function() { reject(new Error('图片加载失败')); }
    });
  });
}

module.exports = { compressToTargetKB: compressToTargetKB };
