var wx = require('./platform/alipayWxCompat.js');
/**
 * API 配置
 *
 * AI 功能需要后端服务支持。小程序前端不能直接调用第三方 AI API
 * （API Key 不能暴露在前端），所有 AI 请求通过后端代理。
 *
 * 配置方式：
 *   1. 部署后端服务（FastAPI），启动: cd server && uvicorn main:app --host 0.0.0.0 --port 8000
 *   2. develop 默认使用隔离的支付宝 Staging HTTPS 入口
 *   3. develop 仅在显式开启本地开发模式时使用 http://127.0.0.1:8000
 *   4. trial/release 始终使用正式 HTTPS 云端域名
 */

var LOCAL_API_BASE_URL = 'http://127.0.0.1:8000';
var CLOUD_API_BASE_URL = 'https://tupzjianzhao.chat';
var ALIPAY_STAGING_API_BASE_URL = 'https://tupzjianzhao.chat/alipay-staging-v1';
var API_TARGET_STORAGE_KEY = 'ID_PHOTO_API_TARGET';
var LOCAL_DEVELOPMENT_MODE_STORAGE_KEY = 'ID_PHOTO_LOCAL_DEVELOPMENT_MODE';

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

function getStoredLocalDevelopmentMode() {
  try {
    if (typeof wx !== 'undefined' && wx.getStorageSync) {
      return wx.getStorageSync(LOCAL_DEVELOPMENT_MODE_STORAGE_KEY) || '';
    }
  } catch (e) {}
  return '';
}

function removeStorage(key) {
  try {
    if (typeof wx !== 'undefined' && wx.removeStorageSync) {
      wx.removeStorageSync(key);
    }
  } catch (e) {}
}

function getApiRouteState() {
  var envVersion = getRuntimeEnvVersion() || 'unknown';
  var storedApiTargetBefore = getStoredApiTarget();
  var storedApiTarget = storedApiTargetBefore;
  var localDevelopmentModeEnabled = envVersion === 'develop' && getStoredLocalDevelopmentMode() === 'enabled';
  var legacyLocalTargetCleared = false;

  // Trial and release must never inherit a historical local switch.
  if (envVersion === 'trial' || envVersion === 'release') {
    if (storedApiTargetBefore) removeStorage(API_TARGET_STORAGE_KEY);
    if (getStoredLocalDevelopmentMode()) removeStorage(LOCAL_DEVELOPMENT_MODE_STORAGE_KEY);
    return {
      envVersion: envVersion,
      storedApiTargetBefore: storedApiTargetBefore,
      storedApiTarget: '',
      localDevelopmentModeEnabled: false,
      legacyLocalTargetCleared: storedApiTargetBefore === 'local',
      stagingRouteActive: false,
      actualApiBaseUrl: CLOUD_API_BASE_URL
    };
  }

  // A lone legacy "local" target must never survive as an implicit opt-in.
  if (storedApiTarget === 'local' && !localDevelopmentModeEnabled) {
    removeStorage(API_TARGET_STORAGE_KEY);
    storedApiTarget = '';
    legacyLocalTargetCleared = true;
  }

  return {
    envVersion: envVersion,
    storedApiTargetBefore: storedApiTargetBefore,
    storedApiTarget: storedApiTarget,
    localDevelopmentModeEnabled: localDevelopmentModeEnabled,
    legacyLocalTargetCleared: legacyLocalTargetCleared,
    stagingRouteActive: envVersion === 'develop' && !localDevelopmentModeEnabled,
    actualApiBaseUrl: localDevelopmentModeEnabled && storedApiTarget === 'local'
      ? LOCAL_API_BASE_URL
      : (envVersion === 'develop' ? ALIPAY_STAGING_API_BASE_URL : CLOUD_API_BASE_URL)
  };
}

function getApiBaseUrl() {
  return getApiRouteState().actualApiBaseUrl;
}

function setLocalDevelopmentMode(enabled) {
  var envVersion = getRuntimeEnvVersion();
  if (envVersion !== 'develop') {
    removeStorage(API_TARGET_STORAGE_KEY);
    removeStorage(LOCAL_DEVELOPMENT_MODE_STORAGE_KEY);
    return false;
  }

  try {
    if (typeof wx !== 'undefined' && wx.setStorageSync) {
      if (enabled === true) {
        wx.setStorageSync(LOCAL_DEVELOPMENT_MODE_STORAGE_KEY, 'enabled');
        wx.setStorageSync(API_TARGET_STORAGE_KEY, 'local');
      } else {
        removeStorage(LOCAL_DEVELOPMENT_MODE_STORAGE_KEY);
        removeStorage(API_TARGET_STORAGE_KEY);
      }
      return true;
    }
  } catch (e) {}
  return false;
}

function getApiRuntimeInfo() {
  var routeState = getApiRouteState();
  return {
    envVersion: routeState.envVersion,
    storedApiTarget: routeState.storedApiTarget,
    storedApiTargetBefore: routeState.storedApiTargetBefore,
    actualApiBaseUrl: routeState.actualApiBaseUrl,
    forcedCloud: routeState.actualApiBaseUrl === CLOUD_API_BASE_URL,
    stagingRouteActive: routeState.stagingRouteActive,
    localDevelopmentModeEnabled: routeState.localDevelopmentModeEnabled,
    legacyLocalTargetCleared: routeState.legacyLocalTargetCleared
  }
}

var ENABLE_AI = true;                          // 启用 AI 功能

module.exports = {
  LOCAL_API_BASE_URL: LOCAL_API_BASE_URL,
  CLOUD_API_BASE_URL: CLOUD_API_BASE_URL,
  ALIPAY_STAGING_API_BASE_URL: ALIPAY_STAGING_API_BASE_URL,
  API_TARGET_STORAGE_KEY: API_TARGET_STORAGE_KEY,
  LOCAL_DEVELOPMENT_MODE_STORAGE_KEY: LOCAL_DEVELOPMENT_MODE_STORAGE_KEY,
  get API_BASE_URL() { return getApiBaseUrl(); },
  getApiBaseUrl: getApiBaseUrl,
  getApiRuntimeInfo: getApiRuntimeInfo,
  setLocalDevelopmentMode: setLocalDevelopmentMode,
  ENABLE_AI: ENABLE_AI
};
