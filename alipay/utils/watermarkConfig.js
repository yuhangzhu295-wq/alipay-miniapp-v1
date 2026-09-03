var wx = require('./platform/alipayWxCompat.js');
/**
 * 图片去水印 OpenCV 服务配置。
 *
 * WATERMARK_API_MODE:
 * - local: 微信开发者工具本机调试
 * - lan: 手机真机调试，改 WATERMARK_LAN_BASE_URL 为电脑局域网 IP
 * - online: 线上 HTTPS 服务
 *
 * ENABLE_HD_REPAIR:
 * - true: 显示“高清修复”选项，实际可用性以 /health 的 hdAvailable 为准
 * - false: 隐藏“高清修复”选项，仅保留 OpenCV 快速模式
 */

var apiConfig = require('./apiConfig.js');

var WATERMARK_API_MODE = 'same-as-api';

var WATERMARK_LOCAL_BASE_URL = apiConfig.LOCAL_API_BASE_URL || 'http://127.0.0.1:8000';
var WATERMARK_LAN_BASE_URL = apiConfig.API_BASE_URL;
var WATERMARK_ONLINE_BASE_URL = apiConfig.CLOUD_API_BASE_URL || 'https://tupzjianzhao.chat';
var ENABLE_HD_REPAIR = true;
var HD_REPAIR_ENGINE = 'lama';

function getStoredBaseUrl() {
  try {
    if (typeof wx !== 'undefined' && wx.getStorageSync) {
      return wx.getStorageSync('WATERMARK_API_BASE_URL') || '';
    }
  } catch (e) {}
  return '';
}

function getWatermarkApiBaseUrl() {
  return apiConfig.getApiBaseUrl ? apiConfig.getApiBaseUrl() : apiConfig.API_BASE_URL;
}

function setWatermarkApiBaseUrl(url) {
  try {
    if (typeof wx !== 'undefined' && wx.setStorageSync) {
      wx.setStorageSync('WATERMARK_API_BASE_URL', url || '');
    }
  } catch (e) {}
}

function isHdRepairEnabled() {
  return ENABLE_HD_REPAIR === true;
}

function getHdRepairEngine() {
  return HD_REPAIR_ENGINE || 'lama';
}

module.exports = {
  WATERMARK_API_MODE: WATERMARK_API_MODE,
  WATERMARK_LOCAL_BASE_URL: WATERMARK_LOCAL_BASE_URL,
  WATERMARK_LAN_BASE_URL: WATERMARK_LAN_BASE_URL,
  WATERMARK_ONLINE_BASE_URL: WATERMARK_ONLINE_BASE_URL,
  ENABLE_HD_REPAIR: ENABLE_HD_REPAIR,
  HD_REPAIR_ENGINE: HD_REPAIR_ENGINE,
  getWatermarkApiBaseUrl: getWatermarkApiBaseUrl,
  setWatermarkApiBaseUrl: setWatermarkApiBaseUrl,
  isHdRepairEnabled: isHdRepairEnabled,
  getHdRepairEngine: getHdRepairEngine
};
