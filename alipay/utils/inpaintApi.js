/**
 * AI 图像修复 / 去水印 API
 *
 * 委托给 aiImageApi.js 调用后端 IOPaint / OpenCV inpaint 服务。
 *
 * 使用方式：
 *   var inpaintApi = require('../../utils/inpaintApi.js');
 *   inpaintApi.removeWatermarkByAI({ imagePath, rect }).then(function(resultPath) { ... });
 */

var aiApi = require('./aiImageApi.js');

/**
 * AI 智能去水印
 * @param {object} params
 * @param {string} params.imagePath — 图片临时路径
 * @param {object} params.rect — { x, y, w, h } 水印区域像素坐标
 * @returns {Promise<string>} 处理后图片路径，失败 reject
 */
function removeWatermarkByAI(params) {
  var imagePath = params.imagePath;
  var rect = params.rect || { x: 0, y: 0, w: 100, h: 100 };

  return aiApi.inpaint(imagePath, {
    x: rect.x || 0,
    y: rect.y || 0,
    w: rect.w || 100,
    h: rect.h || 100
  });
}

module.exports = {
  removeWatermarkByAI: removeWatermarkByAI
};
