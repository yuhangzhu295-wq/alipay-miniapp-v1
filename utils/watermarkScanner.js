/**
 * 扫描式去水印 — 检测重复水印并进行修复
 *
 * 适用：重复斜纹水印、满屏小文字水印、半透明水印
 * 不适用：大面积实心Logo、被水印完全遮挡的细节（需 AI inpainting）
 *
 * 核心流程：
 *   scanRepeatedWatermark(imageData) → buildWatermarkMask → localInpaintByMask
 */

/**
 * @typedef ScanResult
 * @property {Uint8Array} mask       — 水印 mask (0=clean, 1=watermark)
 * @property {string}    direction   — 'horizontal'|'vertical'|'diagonal'|'antiDiagonal'|'mixed'
 * @property {number}    coverage    — 水印覆盖率 (0-1)
 * @property {number}    confidence  — 置信度 (0-1)
 */

/**
 * 扫描重复水印
 * @param {ImageData} imageData
 * @param {object} options — { sensitivity: 0.5-2.0 (default 1.0) }
 * @returns {ScanResult}
 */
function scanRepeatedWatermark(imageData, options) {
  options = options || {};
  var sensitivity = options.sensitivity || 1.0;

  var w = imageData.width, h = imageData.height;
  var px = imageData.data;
  var gray = new Float32Array(w * h);

  // Step 1: Convert to grayscale
  for (var i = 0; i < w * h; i++) {
    var pi = i * 4;
    gray[i] = 0.299 * px[pi] + 0.587 * px[pi + 1] + 0.114 * px[pi + 2];
  }

  // Step 2: Compute local contrast
  var localAvg = new Float32Array(w * h);
  var localContrast = new Float32Array(w * h);
  var radius = 6;
  for (var y = 0; y < h; y++) {
    for (var x = 0; x < w; x++) {
      var sum = 0, cnt = 0;
      for (var dy = -radius; dy <= radius; dy++) {
        for (var dx = -radius; dx <= radius; dx++) {
          var nx = x + dx, ny = y + dy;
          if (nx >= 0 && nx < w && ny >= 0 && ny < h) { sum += gray[ny * w + nx]; cnt++; }
        }
      }
      var avg = sum / cnt;
      localAvg[y * w + x] = avg;
      localContrast[y * w + x] = Math.abs(gray[y * w + x] - avg);
    }
  }

  // Step 3: Find candidate watermark pixels
  // Watermark characteristics: slightly different from local avg, not extreme edges
  var candidates = new Uint8Array(w * h);
  var candidateCount = 0;
  var lowThreshold = 8 / sensitivity;
  var highThreshold = 35 * sensitivity;

  for (var i = 0; i < w * h; i++) {
    var c = localContrast[i];
    if (c > lowThreshold && c < highThreshold) {
      candidates[i] = 1;
      candidateCount++;
    }
  }

  // Step 4: Directional scanning
  var directions = [
    { name: 'horizontal',   dx: 1, dy: 0, stepRow: h, stepCol: w },
    { name: 'vertical',     dx: 0, dy: 1, stepRow: w, stepCol: h },
    { name: 'diagonal',     dx: 1, dy: 1, stepRow: null, stepCol: null },
    { name: 'antiDiagonal', dx: 1, dy: -1, stepRow: null, stepCol: null }
  ];

  var bestDirection = 'mixed';
  var bestPeriodicity = 0;

  for (var d = 0; d < directions.length; d++) {
    var dir = directions[d];
    var periodicity = 0;

    if (dir.name === 'horizontal') {
      // Scan rows for periodic patterns
      for (var y = 10; y < h - 10; y += 20) {
        var rowDensity = [];
        for (var x = 0; x < w; x++) {
          if (candidates[y * w + x]) rowDensity.push(1);
          else rowDensity.push(0);
        }
        // Simple autocorrelation
        var peaks = countPeriodicPeaks(rowDensity, 8, 60);
        periodicity += peaks;
      }
    } else if (dir.name === 'vertical') {
      for (var x = 10; x < w - 10; x += 20) {
        var colDensity = [];
        for (var y = 0; y < h; y++) {
          if (candidates[y * w + x]) colDensity.push(1);
          else colDensity.push(0);
        }
        periodicity += countPeriodicPeaks(colDensity, 8, 60);
      }
    } else {
      // Diagonal: sample along diagonal lines
      var diagCount = 0;
      for (var startY = 0; startY < h; startY += 30) {
        var diagDensity = [];
        var cx = 0, cy = startY;
        if (dir.name === 'antiDiagonal') cy = h - 1 - startY;
        while (cx < w && cy >= 0 && cy < h) {
          if (candidates[cy * w + cx]) diagDensity.push(1);
          else diagDensity.push(0);
          cx++;
          if (dir.name === 'antiDiagonal') cy--; else cy++;
        }
        periodicity += countPeriodicPeaks(diagDensity, 8, 80);
        diagCount++;
      }
    }

    if (periodicity > bestPeriodicity) {
      bestPeriodicity = periodicity;
      bestDirection = dir.name;
    }
  }

  // Step 5: Build mask — expand candidates based on direction
  var mask = new Uint8Array(w * h);
  var expandRadius = 2;

  for (var y = 0; y < h; y++) {
    for (var x = 0; x < w; x++) {
      if (candidates[y * w + x]) {
        for (var dy = -expandRadius; dy <= expandRadius; dy++) {
          for (var dx = -expandRadius; dx <= expandRadius; dx++) {
            var nx = x + dx, ny = y + dy;
            if (nx >= 0 && nx < w && ny >= 0 && ny < h) {
              mask[ny * w + nx] = 1;
            }
          }
        }
      }
    }
  }

  var maskedCount = 0;
  for (var ii = 0; ii < w * h; ii++) { if (mask[ii]) maskedCount++; }

  return {
    mask: mask,
    direction: bestDirection,
    coverage: maskedCount / (w * h),
    confidence: Math.min(1, bestPeriodicity / 20)
  };
}

function countPeriodicPeaks(arr, minGap, maxGap) {
  var peaks = [];
  for (var i = 1; i < arr.length - 1; i++) {
    if (arr[i] === 1 && arr[i - 1] === 0 && arr[i + 1] === 0) peaks.push(i);
  }
  if (peaks.length < 3) return 0;

  var diffs = [];
  for (var p = 1; p < peaks.length; p++) {
    var diff = peaks[p] - peaks[p - 1];
    if (diff >= minGap && diff <= maxGap) diffs.push(diff);
  }
  if (diffs.length < 2) return 0;

  // How consistent are the gaps?
  var sum = 0;
  for (var d = 0; d < diffs.length; d++) sum += diffs[d];
  var avg = sum / diffs.length;
  var variance = 0;
  for (var dd = 0; dd < diffs.length; dd++) variance += Math.pow(diffs[dd] - avg, 2);
  variance /= diffs.length;

  return variance < avg * avg * 0.3 ? diffs.length : 0;
}

/**
 * 中值邻域修复 — 对 mask 中的每个像素取周围非 mask 像素中值替换
 * @param {ImageData} imageData — 会被原地修改
 * @param {Uint8Array} mask
 * @param {number} radius — 搜索半径 (默认 5)
 */
function localInpaintByMask(imageData, mask, radius) {
  radius = radius || 5;
  var w = imageData.width, h = imageData.height;
  var px = imageData.data;
  var tmp = new Uint8ClampedArray(px); // copy

  for (var y = 0; y < h; y++) {
    for (var x = 0; x < w; x++) {
      var idx = y * w + x;
      if (!mask[idx]) continue;

      var rVals = [], gVals = [], bVals = [];
      for (var dy = -radius; dy <= radius; dy++) {
        for (var dx = -radius; dx <= radius; dx++) {
          var nx = x + dx, ny = y + dy;
          if (nx >= 0 && nx < w && ny >= 0 && ny < h) {
            var ni = ny * w + nx;
            if (!mask[ni]) {
              var npi = ni * 4;
              rVals.push(tmp[npi]);
              gVals.push(tmp[npi + 1]);
              bVals.push(tmp[npi + 2]);
            }
          }
        }
      }

      if (rVals.length > 0) {
        rVals.sort(function(a, b) { return a - b; });
        gVals.sort(function(a, b) { return a - b; });
        bVals.sort(function(a, b) { return a - b; });
        var mid = Math.floor(rVals.length / 2);
        var pi = idx * 4;
        px[pi] = rVals[mid];
        px[pi + 1] = gVals[mid];
        px[pi + 2] = bVals[mid];
      }
    }
  }
}

/**
 * 模糊遮罩边缘 — 轻微平滑
 */
function smoothMaskEdges(imageData, mask, radius) {
  radius = radius || 2;
  var w = imageData.width, h = imageData.height;
  var px = imageData.data;
  var tmp = new Uint8ClampedArray(px);

  for (var y = 0; y < h; y++) {
    for (var x = 0; x < w; x++) {
      var idx = y * w + x;
      if (!mask[idx]) continue;

      var hasCleanNeighbor = false;
      for (var dy = -1; dy <= 1; dy++) {
        for (var dx = -1; dx <= 1; dx++) {
          var nx = x + dx, ny = y + dy;
          if (nx >= 0 && nx < w && ny >= 0 && ny < h) {
            if (!mask[ny * w + nx]) hasCleanNeighbor = true;
          }
        }
      }

      if (hasCleanNeighbor) {
        var r = 0, g = 0, b = 0, cnt = 0;
        for (var dy2 = -radius; dy2 <= radius; dy2++) {
          for (var dx2 = -radius; dx2 <= radius; dx2++) {
            var nx2 = x + dx2, ny2 = y + dy2;
            if (nx2 >= 0 && nx2 < w && ny2 >= 0 && ny2 < h) {
              var npi2 = ny2 * w + nx2 * 4;
              r += tmp[npi2]; g += tmp[npi2 + 1]; b += tmp[npi2 + 2];
              cnt++;
            }
          }
        }
        var pi = idx * 4;
        px[pi] = Math.floor(r / cnt);
        px[pi + 1] = Math.floor(g / cnt);
        px[pi + 2] = Math.floor(b / cnt);
      }
    }
  }
}

module.exports = {
  scanRepeatedWatermark: scanRepeatedWatermark,
  localInpaintByMask: localInpaintByMask,
  smoothMaskEdges: smoothMaskEdges
};
