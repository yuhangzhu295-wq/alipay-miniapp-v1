/**
 * AI 图片上色 API（预留接口）
 * 后续接入：DeOldify / 阿里云 aiart / 百度AI
 * 
 * 当前状态：未接入AI服务，返回 null
 * 本地 Canvas 滤镜作为 fallback
 */

/**
 * AI 智能上色
 * @param {string} imagePath - 黑白图片路径
 * @returns {Promise<string|null>} 上色后图片路径，当前返回 null
 */
function colorizeByAI(imagePath) {
  // TODO: 接入 AI 上色服务
  // 示例：
  // 1. 上传图片到云存储
  // 2. 调用 DeOldify API / 阿里云色彩迁移
  // 3. 返回上色后图片 URL

  return new Promise(function(resolve) {
    resolve(null);
  });
}

module.exports = {
  colorizeByAI: colorizeByAI
};
