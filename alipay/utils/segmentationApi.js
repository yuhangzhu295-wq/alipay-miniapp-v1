/**
 * AI 人像分割 / 抠图 API
 *
 * 委托给 aiImageApi.js 调用后端 rembg 服务。
 *
 * 使用方式：
 *   var segApi = require('../../utils/segmentationApi.js');
 *   segApi.segmentPortrait(imagePath).then(function(maskedImagePath) { ... });
 */

var aiApi = require('./aiImageApi.js');

/**
 * 人像分割 — 返回透明背景 PNG
 * @param {string} imagePath — 图片临时路径
 * @returns {Promise<string>} 透明背景人物图本地路径，失败 reject
 */
function segmentPortrait(imagePath) {
  return aiApi.removeBg(imagePath);
}

module.exports = {
  segmentPortrait: segmentPortrait
};
