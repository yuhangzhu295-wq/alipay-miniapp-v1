/**
 * 证件照换底色 — 边缘连通 flood-fill 算法
 * 只替换与图像边缘连通的背景区域，不触碰中间人物主体
 */

var MODES = {
  blue:  { color: [26, 115, 232], tolerance: 50 },
  white: { color: [220, 220, 220], tolerance: 75 },
  red:   { color: [210, 50, 50],   tolerance: 50 },
  auto:  { color: null,            tolerance: 55 }
};

/**
 * 边缘连通背景替换
 * @param {object} opts
 * @param {string} opts.imagePath     — 原图路径
 * @param {string} opts.sourceMode    — 'auto' | 'blue' | 'white' | 'red'
 * @param {object} opts.targetColor   — { r, g, b, hex }
 * @param {number} opts.maxDim        — 最大边尺寸 (性能限制，默认 800)
 * @returns {Promise<object>} { tempFilePath, actualW, actualH }
 */
function replaceBackgroundByFloodFill(opts) {
  var imagePath  = opts.imagePath;
  var sourceMode = opts.sourceMode || 'auto';
  var targetColor= opts.targetColor || { r: 229, g: 57, b: 53, hex: '#e53935' };
  var maxDim     = opts.maxDim || 800;

  return new Promise(function(resolve, reject) {
    wx.getImageInfo({
      src: imagePath,
      success: function(info) {
        var scale = Math.min(1, maxDim / Math.max(info.width, info.height));
        var cw = Math.max(10, Math.floor(info.width * scale));
        var ch = Math.max(10, Math.floor(info.height * scale));

        try {
          var canvas = wx.createOffscreenCanvas({ type: '2d', width: cw, height: ch });
          var ctx = canvas.getContext('2d');
          var imgObj = canvas.createImage();

          imgObj.onload = function() {
            ctx.drawImage(imgObj, 0, 0, cw, ch);

            // Step 1: Get detect color
            var detectColor, tolerance;
            var allSamples = sampleEdgePixels(ctx, cw, ch, 8);
            
            if (allSamples.length > 0) {
              // 边缘像素色彩方差检测 — 过滤复杂背景与生活照，防止人物染色
              var rVals = allSamples.map(function(s) { return s[0]; });
              var gVals = allSamples.map(function(s) { return s[1]; });
              var bVals = allSamples.map(function(s) { return s[2]; });
              
              function getStdDev(arr) {
                var n = arr.length;
                if (n === 0) return 0;
                var mean = arr.reduce(function(a, b) { return a + b; }, 0) / n;
                var sqSum = arr.map(function(x) { return Math.pow(x - mean, 2); }).reduce(function(a, b) { return a + b; }, 0);
                return Math.sqrt(sqSum / n);
              }
              
              var rStd = getStdDev(rVals);
              var gStd = getStdDev(gVals);
              var bStd = getStdDev(bVals);
              var maxStd = Math.max(rStd, gStd, bStd);
              
              if (maxStd > 25) {
                reject(new Error('检测到复杂背景，本地模式易将主体染色，请切换至 AI 抠图模式！'));
                return;
              }
            }

            if (sourceMode !== 'auto' && MODES[sourceMode]) {
              detectColor = MODES[sourceMode].color;
              tolerance = MODES[sourceMode].tolerance;
            } else {
              // Auto-detect from corners + edges
              if (allSamples.length > 0) {
                var sr = 0, sg = 0, sb = 0;
                for (var s = 0; s < allSamples.length; s++) { sr += allSamples[s][0]; sg += allSamples[s][1]; sb += allSamples[s][2]; }
                detectColor = [Math.floor(sr / allSamples.length), Math.floor(sg / allSamples.length), Math.floor(sb / allSamples.length)];
              } else {
                detectColor = [26, 115, 232];
              }
              tolerance = MODES.auto.tolerance;
            }

            // Step 2: Flood-fill from edges
            var imgData, px;
            try { imgData = ctx.getImageData(0, 0, cw, ch); px = imgData.data; }
            catch(e) { reject(new Error('getImageData 失败')); return; }

            var totalPx = cw * ch;
            var visited = new Uint8Array(totalPx); // 0=unknown, 1=bg, 2=fg
            var queue = [];
            var qHead = 0;

            function isBgColor(pi) {
              var dr = Math.abs(px[pi] - detectColor[0]);
              var dg = Math.abs(px[pi + 1] - detectColor[1]);
              var db = Math.abs(px[pi + 2] - detectColor[2]);
              return dr < tolerance && dg < tolerance && db < tolerance;
            }

            function pushIfBg(x, y) {
              if (x < 0 || x >= cw || y < 0 || y >= ch) return;
              var idx = y * cw + x;
              if (visited[idx] !== 0) return;
              if (isBgColor(idx * 4)) {
                visited[idx] = 1;
                queue.push(x, y);
              } else {
                visited[idx] = 2;
              }
            }

            // Seed from all four edges
            for (var ex = 0; ex < cw; ex++) { pushIfBg(ex, 0); pushIfBg(ex, ch - 1); }
            for (var ey = 0; ey < ch; ey++) { pushIfBg(0, ey); pushIfBg(cw - 1, ey); }

            // BFS
            while (qHead < queue.length) {
              var qx = queue[qHead++];
              var qy = queue[qHead++];
              pushIfBg(qx + 1, qy);
              pushIfBg(qx - 1, qy);
              pushIfBg(qx, qy + 1);
              pushIfBg(qx, qy - 1);
            }

            // Step 3: Count how many bg pixels were found
            var bgCount = 0;
            for (var i = 0; i < totalPx; i++) { if (visited[i] === 1) bgCount++; }

            if (bgCount < totalPx * 0.03) {
              // Very few bg pixels — means the background can't be reached from edges
              reject(new Error('无法检测到连通的纯色背景'));
              return;
            }

            // Step 4: Replace bg pixels with target color
            for (var j = 0; j < totalPx; j++) {
              if (visited[j] === 1) {
                var pi2 = j * 4;
                px[pi2] = targetColor.r;
                px[pi2 + 1] = targetColor.g;
                px[pi2 + 2] = targetColor.b;
              }
            }
            ctx.putImageData(imgData, 0, 0);

            // Step 5: Feather 1-2px around the boundary
            featherBoundary(ctx, visited, targetColor, cw, ch);

            // Step 6: Export
            wx.canvasToTempFilePath({
              canvas: canvas, fileType: 'jpg', quality: 0.95,
              success: function(r) {
                resolve({ tempFilePath: r.tempFilePath, actualW: cw, actualH: ch, bgPixelCount: bgCount });
              },
              fail: function() { reject(new Error('导出失败')); }
            });
          };

          imgObj.onerror = function() { reject(new Error('图片渲染失败')); };
          imgObj.src = imagePath;
        } catch(e) {
          reject(new Error('Canvas 初始化失败: ' + (e.message || e)));
        }
      },
      fail: function() { reject(new Error('图片加载失败')); }
    });
  });
}

function sampleEdgePixels(ctx, w, h, spacing) {
  var samples = [];
  var positions = [];
  for (var x = 2; x < w - 2; x += spacing) { positions.push([x, 2]); positions.push([x, h - 3]); }
  for (var y = 2; y < h - 2; y += spacing) { positions.push([2, y]); positions.push([w - 3, y]); }
  for (var p = 0; p < positions.length; p++) {
    try {
      var d = ctx.getImageData(positions[p][0], positions[p][1], 1, 1);
      samples.push([d.data[0], d.data[1], d.data[2]]);
    } catch(e) {}
    if (samples.length >= 128) break; // cap
  }
  return samples;
}

/** Feather 1px around bg→fg boundaries */
function featherBoundary(ctx, visited, targetColor, w, h) {
  try {
    var fd = ctx.getImageData(0, 0, w, h);
    var fp = fd.data;
    for (var y = 1; y < h - 1; y++) {
      for (var x = 1; x < w - 1; x++) {
        var idx = y * w + x;
        if (visited[idx] === 1) continue;
        var cnt = 0;
        for (var dy = -1; dy <= 1; dy++)
          for (var dx = -1; dx <= 1; dx++)
            if (dx || dy)
              if (visited[(y + dy) * w + (x + dx)] === 1) cnt++;
        if (cnt >= 2) {
          var pi = idx * 4;
          fp[pi]     = Math.floor(fp[pi]     * 0.5 + targetColor.r * 0.5);
          fp[pi + 1] = Math.floor(fp[pi + 1] * 0.5 + targetColor.g * 0.5);
          fp[pi + 2] = Math.floor(fp[pi + 2] * 0.5 + targetColor.b * 0.5);
        }
      }
    }
    ctx.putImageData(fd, 0, 0);
  } catch(e) {}
}

module.exports = {
  replaceBackgroundByFloodFill: replaceBackgroundByFloodFill,
  MODES: MODES
};
