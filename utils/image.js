/**
 * 图片处理工具
 * 主要功能：背景替换、尺寸裁剪、规格调整
 * 
 * 使用新版 Canvas 2D API（基础库 2.16.1+）
 */

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function parseHexColor(hex) {
  var value = (hex || '#1a73e8').replace('#', '');
  if (value.length === 3) {
    value = value.split('').map(function(ch) { return ch + ch; }).join('');
  }
  var num = parseInt(value, 16);
  if (isNaN(num)) return { r: 26, g: 115, b: 232 };
  return {
    r: (num >> 16) & 255,
    g: (num >> 8) & 255,
    b: num & 255
  };
}

function colorDistance(r, g, b, target) {
  var dr = r - target.r;
  var dg = g - target.g;
  var db = b - target.b;
  return Math.sqrt(dr * dr + dg * dg + db * db);
}

function estimateCornerColor(data, w, h) {
  var points = [
    [2, 2],
    [w - 3, 2],
    [2, h - 3],
    [w - 3, h - 3]
  ];
  var r = 0;
  var g = 0;
  var b = 0;
  var count = 0;
  points.forEach(function(p) {
    var x = clamp(p[0], 0, w - 1);
    var y = clamp(p[1], 0, h - 1);
    var index = (y * w + x) * 4;
    r += data[index];
    g += data[index + 1];
    b += data[index + 2];
    count += 1;
  });
  return { r: r / count, g: g / count, b: b / count };
}

function detectSubjectBox(img, imgW, imgH, bgColor) {
  try {
    var maxSide = 360;
    var scale = Math.min(1, maxSide / Math.max(imgW, imgH));
    var sampleW = Math.max(32, Math.round(imgW * scale));
    var sampleH = Math.max(32, Math.round(imgH * scale));
    var canvas = wx.createOffscreenCanvas({ type: '2d', width: sampleW, height: sampleH });
    var ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0, sampleW, sampleH);
    var imageData = ctx.getImageData(0, 0, sampleW, sampleH);
    var data = imageData.data;
    var bg = parseHexColor(bgColor);
    var corner = estimateCornerColor(data, sampleW, sampleH);
    var minX = sampleW;
    var minY = sampleH;
    var maxX = 0;
    var maxY = 0;
    var count = 0;
    var step = sampleW > 220 ? 2 : 1;

    for (var y = 0; y < sampleH; y += step) {
      for (var x = 0; x < sampleW; x += step) {
        var i = (y * sampleW + x) * 4;
        var a = data[i + 3];
        if (a < 20) continue;
        var r = data[i];
        var g = data[i + 1];
        var b = data[i + 2];
        var dBg = colorDistance(r, g, b, bg);
        var dCorner = colorDistance(r, g, b, corner);
        if (Math.min(dBg, dCorner) > 38) {
          minX = Math.min(minX, x);
          minY = Math.min(minY, y);
          maxX = Math.max(maxX, x);
          maxY = Math.max(maxY, y);
          count += 1;
        }
      }
    }

    var sampleArea = sampleW * sampleH / (step * step);
    if (count < sampleArea * 0.01 || count > sampleArea * 0.82) return null;
    var inv = 1 / scale;
    return {
      x: minX * inv,
      y: minY * inv,
      width: Math.max(1, (maxX - minX + step) * inv),
      height: Math.max(1, (maxY - minY + step) * inv)
    };
  } catch (err) {
    console.warn('[generate] subject box fallback:', err);
    return null;
  }
}

function getCompositionProfile(spec) {
  var config = spec.cropComposition || {};
  var type = config.type || spec.composition || 'id_head_shoulder';
  var targetHeadRatio = (config.headHeightRatioMin || 0.58) + ((config.headHeightRatioMax || 0.70) - (config.headHeightRatioMin || 0.58)) * 0.45;
  var profile = {
    type: type,
    topPaddingRatioMin: config.topPaddingRatioMin || 0.07,
    topPaddingRatioMax: config.topPaddingRatioMax || 0.12,
    topPaddingRatio: config.topPaddingRatio || config.topPaddingRatioMin || 0.08,
    faceCenterYRatio: config.faceCenterYRatio || 0.43,
    targetHeadRatio: targetHeadRatio,
    targetFaceRatio: clamp(targetHeadRatio / 1.68, 0.34, 0.42),
    shoulderWidthRatio: ((config.shoulderWidthRatioMin || 0.70) + (config.shoulderWidthRatioMax || 0.90)) / 2,
    subjectWidthExpand: 1.14,
    fallbackCropHeightRatio: 0.64,
    fallbackTopRatio: 0.04,
    maxBodyBelowShoulderRatio: config.maxBodyBelowShoulderRatio || 0.22
  };
  if (type === 'driver_license_head') {
    profile.shoulderWidthRatio = 0.78;
    profile.fallbackCropHeightRatio = 0.58;
    profile.targetFaceRatio = 0.36;
  }
  if (type === 'school_head_shoulder' || type === 'exam_head_shoulder') {
    profile.shoulderWidthRatio = 0.80;
    profile.fallbackCropHeightRatio = 0.66;
    profile.targetFaceRatio = 0.37;
  }
  if (type === 'resume_avatar') {
    profile.shoulderWidthRatio = 0.84;
    profile.fallbackCropHeightRatio = 0.62;
    profile.targetFaceRatio = 0.38;
  }
  return profile;
}

function normalizeFaceBox(faceBox, imgW, imgH) {
  if (!faceBox) return null;
  var x = Number(faceBox.x);
  var y = Number(faceBox.y);
  var width = Number(faceBox.width);
  var height = Number(faceBox.height);
  if (!isFinite(x) || !isFinite(y) || !isFinite(width) || !isFinite(height) || width < 8 || height < 8) {
    return null;
  }
  width = clamp(width, 1, imgW);
  height = clamp(height, 1, imgH);
  return {
    x: clamp(x, 0, Math.max(0, imgW - width)),
    y: clamp(y, 0, Math.max(0, imgH - height)),
    width: width,
    height: height
  };
}

function estimateFaceBoxFromSubject(subjectBox, imgW, imgH) {
  if (!subjectBox) return null;
  var faceH = clamp(Math.min(subjectBox.width * 0.42, subjectBox.height * 0.17), imgH * 0.055, imgH * 0.28);
  var faceW = faceH * 0.78;
  var cx = subjectBox.x + subjectBox.width / 2;
  var y = subjectBox.y + Math.max(subjectBox.height * 0.075, faceH * 0.35);
  return normalizeFaceBox({
    x: cx - faceW / 2,
    y: y,
    width: faceW,
    height: faceH
  }, imgW, imgH);
}

function buildFaceCrop(imgW, imgH, targetW, targetH, faceBox, spec, faceRatioBoost) {
  var profile = getCompositionProfile(spec || {});
  var targetRatio = targetW / targetH;
  var targetFaceRatio = clamp(profile.targetFaceRatio + (faceRatioBoost || 0), 0.34, 0.43);
  var scale = (targetH * targetFaceRatio) / Math.max(1, faceBox.height);
  var cropW = targetW / scale;
  var cropH = targetH / scale;
  if (cropW > imgW) {
    cropW = imgW;
    cropH = cropW / targetRatio;
    scale = targetW / cropW;
  }
  if (cropH > imgH) {
    cropH = imgH;
    cropW = cropH * targetRatio;
    scale = targetH / cropH;
  }

  var faceCenterX = faceBox.x + faceBox.width / 2;
  var faceCenterY = faceBox.y + faceBox.height / 2;
  var cropX = faceCenterX - (targetW / 2) / scale;
  var cropY = faceCenterY - (targetH * profile.faceCenterYRatio) / scale;
  cropX = clamp(cropX, 0, Math.max(0, imgW - cropW));
  cropY = clamp(cropY, 0, Math.max(0, imgH - cropH));

  var metrics = evaluateHeadshotCrop(cropX, cropY, cropW, cropH, targetW, targetH, faceBox, profile, imgH);
  return {
    x: cropX,
    y: cropY,
    width: cropW,
    height: cropH,
    metrics: metrics,
    faceBox: faceBox,
    faceDriven: true
  };
}

function evaluateHeadshotCrop(cropX, cropY, cropW, cropH, targetW, targetH, faceBox, profile, imgH) {
  var scale = targetH / cropH;
  var faceHOut = faceBox.height * scale;
  var faceWOut = faceBox.width * scale;
  var faceTopOut = (faceBox.y - cropY) * scale;
  var faceCenterXOut = (faceBox.x + faceBox.width / 2 - cropX) * scale;
  var estimatedHeadTopOut = (faceBox.y - faceBox.height * 0.45 - cropY) * scale;
  var estimatedShoulderLineOut = faceTopOut + faceHOut * 2.15;
  var headHeightRatio = (faceHOut * 1.68) / targetH;
  return {
    faceHeightRatio: faceHOut / targetH,
    faceWidthRatio: faceWOut / targetW,
    headHeightRatio: headHeightRatio,
    headWidthRatio: (faceWOut * 1.28) / targetW,
    topPaddingRatio: estimatedHeadTopOut / targetH,
    faceCenterOffset: Math.abs(faceCenterXOut - targetW / 2) / targetW,
    bodyBelowShoulderRatio: Math.max(0, targetH - estimatedShoulderLineOut) / targetH,
    faceOriginalHeightRatio: faceBox.height / Math.max(1, imgH || cropH),
    distantFace: faceBox.height / Math.max(1, imgH || cropH) < 0.25
  };
}

function isCropAcceptable(crop) {
  if (!crop || !crop.metrics) return true;
  var m = crop.metrics;
  return (
    m.headHeightRatio >= 0.54 &&
    m.headHeightRatio <= 0.74 &&
    m.topPaddingRatio >= 0.035 &&
    m.topPaddingRatio <= 0.14 &&
    m.faceCenterOffset <= 0.13 &&
    m.bodyBelowShoulderRatio <= 0.26
  );
}

function computeCropRect(imgW, imgH, targetW, targetH, subjectBox, spec, faceBox) {
  var profile = getCompositionProfile(spec || {});
  var targetRatio = targetW / targetH;
  var cropW;
  var cropH;
  var cropX;
  var cropY;
  var normalizedFace = normalizeFaceBox(faceBox, imgW, imgH) || estimateFaceBoxFromSubject(subjectBox, imgW, imgH);

  if (normalizedFace) {
    var crop = buildFaceCrop(imgW, imgH, targetW, targetH, normalizedFace, spec, 0);
    if (!isCropAcceptable(crop)) {
      var secondCrop = buildFaceCrop(imgW, imgH, targetW, targetH, normalizedFace, spec, 0.035);
      if (isCropAcceptable(secondCrop) || secondCrop.metrics.headHeightRatio > crop.metrics.headHeightRatio) {
        crop = secondCrop;
        crop.adjusted = true;
      }
    }
    return crop;
  }

  if (subjectBox) {
    var effectiveSubjectW = Math.max(subjectBox.width * profile.subjectWidthExpand, imgW * 0.32);
    var scale = (targetW * profile.shoulderWidthRatio) / effectiveSubjectW;
    var minScale = targetW / imgW;
    var maxScale = Math.max(minScale, targetH / Math.max(1, imgH * 0.42));
    scale = clamp(scale, minScale, maxScale * 1.45);
    cropW = targetW / scale;
    cropH = targetH / scale;
    if (cropW > imgW) {
      cropW = imgW;
      cropH = cropW / targetRatio;
    }
    if (cropH > imgH) {
      cropH = imgH;
      cropW = cropH * targetRatio;
    }
    cropX = subjectBox.x + subjectBox.width / 2 - cropW / 2;
    cropY = subjectBox.y - cropH * profile.topPaddingRatio;
  } else {
    cropH = imgH * profile.fallbackCropHeightRatio;
    cropW = cropH * targetRatio;
    if (cropW > imgW) {
      cropW = imgW;
      cropH = cropW / targetRatio;
    }
    cropX = (imgW - cropW) / 2;
    cropY = imgH * profile.fallbackTopRatio;
  }

  cropX = clamp(cropX, 0, Math.max(0, imgW - cropW));
  cropY = clamp(cropY, 0, Math.max(0, imgH - cropH));
  return {
    x: cropX,
    y: cropY,
    width: cropW,
    height: cropH
  };
}

function getOutputFileType(spec) {
  var list = spec && spec.fileFormat ? spec.fileFormat : ['jpg', 'jpeg'];
  var first = (list[0] || 'jpg').toLowerCase();
  return first === 'png' ? 'png' : 'jpg';
}

/**
 * 裁剪并生成最终证件照
 * @param {string} src - 源图片路径
 * @param {object} spec - 规格对象 { width, height, widthPx, heightPx }
 * @param {string} bgColor - 底色十六进制值
 * @returns {Promise<string>} - 生成图片路径
 */
function generateIDPhoto(src, spec, bgColor, options) {
  options = options || {};
  return new Promise(function(resolve, reject) {
    wx.showLoading({ title: '智能处理中...' });
    
    wx.getImageInfo({
      src: src,
      success: function(srcInfo) {
        var imgW = srcInfo.width;
        var imgH = srcInfo.height;
        
        var targetW = spec.widthPx || 295;
        var targetH = spec.heightPx || 413;
        
        // 创建离屏画布
        var canvas = wx.createOffscreenCanvas({ type: '2d', width: targetW, height: targetH });
        var ctx = canvas.getContext('2d');
        var tempImage = canvas.createImage();
        
        tempImage.onload = function() {
          // 填充底色
          ctx.fillStyle = bgColor;
          ctx.fillRect(0, 0, targetW, targetH);
          
          var cachedCrop = options.cropRect;
          var crop = null;
          if (
            cachedCrop &&
            options.cropImageWidth === imgW &&
            options.cropImageHeight === imgH
          ) {
            var cachedW = clamp(cachedCrop.width, 1, imgW);
            var cachedH = clamp(cachedCrop.height, 1, imgH);
            crop = {
              x: clamp(cachedCrop.x, 0, Math.max(0, imgW - cachedW)),
              y: clamp(cachedCrop.y, 0, Math.max(0, imgH - cachedH)),
              width: cachedW,
              height: cachedH
            };
          }
          if (!crop) {
            var subjectBox = detectSubjectBox(tempImage, imgW, imgH, bgColor);
            crop = computeCropRect(imgW, imgH, targetW, targetH, subjectBox, spec, options.faceBox);
          }
          ctx.imageSmoothingEnabled = true;
          ctx.imageSmoothingQuality = 'high';
          ctx.drawImage(
            tempImage,
            crop.x,
            crop.y,
            crop.width,
            crop.height,
            0,
            0,
            targetW,
            targetH
          );
          
          // 导出为临时文件
          wx.canvasToTempFilePath({
            canvas: canvas,
            fileType: getOutputFileType(spec),
            quality: 1,
            success: function(res) {
              wx.hideLoading();
              if (options.returnMeta) {
                resolve({
                  tempFilePath: res.tempFilePath,
                  cropRect: crop,
                  cropImageWidth: imgW,
                  cropImageHeight: imgH,
                  width: targetW,
                  height: targetH,
                  metrics: crop.metrics || {},
                  warning: crop.metrics && crop.metrics.distantFace ? '照片中人物距离较远，已自动裁切为头肩照。' : ''
                });
                return;
              }
              resolve(res.tempFilePath);
            },
            fail: function(err) {
              wx.hideLoading();
              reject(err);
            }
          });
        };
        
        tempImage.onerror = function() {
          wx.hideLoading();
          reject(new Error('图片加载失败'));
        };
        
        tempImage.src = src;
      },
      fail: function(err) {
        wx.hideLoading();
        reject(err);
      }
    });
  });
}

/**
 * 生成排版照（如一版多张用于打印）
 * @param {string} src - 证件照源图
 * @param {object} spec - 规格
 * @param {number} cols - 列数
 * @param {number} rows - 行数
 * @param {string} printBgColor - 打印纸底色
 * @returns {Promise<string>} - 排版照临时路径
 */
function generateLayoutPhoto(src, spec, cols, rows, printBgColor) {
  cols = cols || 4;
  rows = rows || 2;
  printBgColor = printBgColor || '#ffffff';
  
  return new Promise(function(resolve, reject) {
    wx.showLoading({ title: '生成排版照...' });
    
    wx.getImageInfo({
      src: src,
      success: function(info) {
        // 6寸打印纸尺寸：152×102mm ≈ 1795×1205px @300dpi
        var printW = 1795;
        var printH = 1205;
        var specW = spec.widthPx || 295;
        var specH = spec.heightPx || 413;
        var gapX = 30;
        var gapY = 30;
        
        var canvas = wx.createOffscreenCanvas({ type: '2d', width: printW, height: printH });
        var ctx = canvas.getContext('2d');
        var tempImage = canvas.createImage();
        
        tempImage.onload = function() {
          // 填充打印纸底色
          ctx.fillStyle = printBgColor;
          ctx.fillRect(0, 0, printW, printH);
          
          // 计算每张照片的起始位置（居中）
          var totalW = cols * (specW + gapX) - gapX;
          var totalH = rows * (specH + gapY) - gapY;
          var startX = (printW - totalW) / 2;
          var startY = (printH - totalH) / 2;
          
          for (var r = 0; r < rows; r++) {
            for (var c = 0; c < cols; c++) {
              var x = startX + c * (specW + gapX);
              var y = startY + r * (specH + gapY);
              ctx.drawImage(tempImage, x, y, specW, specH);
            }
          }
          
          wx.canvasToTempFilePath({
            canvas: canvas,
            fileType: getOutputFileType(spec),
            quality: 1,
            success: function(res) {
              wx.hideLoading();
              resolve(res.tempFilePath);
            },
            fail: function(err) {
              wx.hideLoading();
              reject(err);
            }
          });
        };
        
        tempImage.onerror = function() {
          wx.hideLoading();
          reject(new Error('图片加载失败'));
        };
        
        tempImage.src = src;
      },
      fail: function(err) {
        wx.hideLoading();
        reject(err);
      }
    });
  });
}

/**
 * 保存图片到系统相册
 * @param {string} filePath - 图片临时路径
 * @returns {Promise}
 */
function saveImageToAlbum(filePath) {
  return new Promise(function(resolve, reject) {
    wx.getSetting({
      success: function(res) {
        var auth = res.authSetting['scope.writePhotosAlbum'];
        if (auth === undefined) {
          // 未授权，弹出授权
          wx.authorize({
            scope: 'scope.writePhotosAlbum',
            success: function() {
              doSaveImage(filePath).then(resolve).catch(reject);
            },
            fail: function() {
              wx.showModal({
                title: '需要保存权限',
                content: '请在设置中开启保存到相册权限',
                confirmText: '去设置',
                success: function(modalRes) {
                  if (modalRes.confirm) {
                    wx.openSetting();
                  }
                }
              });
              reject(new Error('未授权'));
            }
          });
        } else if (!auth) {
          wx.showModal({
            title: '需要保存权限',
            content: '请在设置中开启保存到相册权限',
            confirmText: '去设置',
            success: function(modalRes) {
              if (modalRes.confirm) {
                wx.openSetting();
              }
            }
          });
          reject(new Error('未授权'));
        } else {
          doSaveImage(filePath).then(resolve).catch(reject);
        }
      }
    });
  });
}

function doSaveImage(filePath) {
  return new Promise(function(resolve, reject) {
    wx.saveImageToPhotosAlbum({
      filePath: filePath,
      success: function() {
        wx.showToast({ title: '已保存到相册', icon: 'success' });
        resolve();
      },
      fail: function(err) {
        wx.showToast({ title: '保存失败', icon: 'none' });
        reject(err);
      }
    });
  });
}

module.exports = {
  generateIDPhoto: generateIDPhoto,
  generateLayoutPhoto: generateLayoutPhoto,
  saveImageToAlbum: saveImageToAlbum
};
