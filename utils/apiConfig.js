/**
 * API 配置
 *
 * AI 功能需要后端服务支持。小程序前端不能直接调用第三方 AI API
 * （API Key 不能暴露在前端），所有 AI 请求通过后端代理。
 *
 * 配置方式：
 *   1. 部署后端服务（FastAPI），启动: cd server && uvicorn main:app --host 0.0.0.0 --port 8000
 *   2. 开发时使用 http://127.0.0.1:8000
 *   3. 真机调试/生产必须改成 HTTPS 域名
 *   4. 在微信公众平台配置合法 request/uploadFile/downloadFile 域名
 */

var LOCAL_API_BASE_URL = 'http://127.0.0.1:8000';
var CLOUD_API_BASE_URL = 'http://42.192.107.208:8000';
var API_TARGET_STORAGE_KEY = 'ID_PHOTO_API_TARGET';

function getRuntimeEnvVersion() {
  try {
    if (typeof wx !== 'undefined' && wx.getAccountInfoSync) {
      var accountInfo = wx.getAccountInfoSync();
      return accountInfo && accountInfo.miniProgram && accountInfo.miniProgram.envVersion;
    }
  } catch (e) {}
  return '';
}

function getStoredApiTarget() {
  try {
    if (typeof wx !== 'undefined' && wx.getStorageSync) {
      return wx.getStorageSync(API_TARGET_STORAGE_KEY) || '';
    }
  } catch (e) {}
  return '';
}

function getApiBaseUrl() {
  var storedTarget = getStoredApiTarget();
  if (storedTarget === 'local') return LOCAL_API_BASE_URL;
  if (storedTarget === 'cloud') return CLOUD_API_BASE_URL;

  var envVersion = getRuntimeEnvVersion();
  if (envVersion === 'release' || envVersion === 'trial') {
    return CLOUD_API_BASE_URL;
  }
  // 强制默认使用云端接口（方便本地开发者工具测试）
  return CLOUD_API_BASE_URL;
}

var API_BASE_URL = getApiBaseUrl();
var ENABLE_AI = true;                          // 启用 AI 功能

module.exports = {
  LOCAL_API_BASE_URL: LOCAL_API_BASE_URL,
  CLOUD_API_BASE_URL: CLOUD_API_BASE_URL,
  API_BASE_URL: API_BASE_URL,
  getApiBaseUrl: getApiBaseUrl,
  ENABLE_AI: ENABLE_AI
};
