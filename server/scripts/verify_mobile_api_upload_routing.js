const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..', '..');

function loadApiConfig(envVersion, initialStorage) {
  const module = { exports: {} };
  const code = fs.readFileSync(path.join(ROOT, 'utils', 'apiConfig.js'), 'utf8');
  const storage = Object.assign({}, initialStorage || {});
  const wx = {
    getAccountInfoSync() { return { miniProgram: { envVersion } }; },
    getStorageSync(key) { return storage[key] || ''; },
    setStorageSync(key, value) { storage[key] = value; },
    removeStorageSync(key) { delete storage[key]; }
  };
  vm.runInNewContext(code, { module, wx }, { filename: 'utils/apiConfig.js' });
  return { config: module.exports, storage };
}

function makeWx(mode) {
  const images = {
    '/origin.jpg': { width: 4000, height: 3000, type: 'jpg' },
    '/native.jpg': { width: 1600, height: 1200, type: 'jpg' },
    '/canvas.jpg': { width: 1600, height: 1200, type: 'jpg' }
  };
  const sizes = { '/origin.jpg': 4800000, '/native.jpg': 960000, '/canvas.jpg': 940000 };
  const wx = {
    getImageInfo(options) {
      const info = images[options.src];
      if (info) options.success(Object.assign({ path: options.src }, info));
      else options.fail({ errMsg: 'missing image' });
    },
    getFileSystemManager() {
      return { getFileInfo(options) { options.success({ size: sizes[options.filePath] || 0 }); } };
    },
    createOffscreenCanvas() {
      return {
        getContext() { return { drawImage() {} }; },
        createImage() {
          const image = {};
          Object.defineProperty(image, 'src', { set() { image.onload(); } });
          return image;
        },
        toTempFilePath(options) {
          if (mode === 'canvas-fail') options.fail({ errMsg: 'export failed' });
          else options.success({ tempFilePath: '/canvas.jpg' });
        }
      };
    }
  };
  if (mode === 'native-success') {
    wx.compressImage = (options) => options.success({ tempFilePath: '/native.jpg' });
  } else if (mode === 'native-fail') {
    wx.compressImage = (options) => options.fail({ errMsg: 'compress failed' });
  }
  return wx;
}

function loadAiImageApi(wx) {
  const module = { exports: {} };
  const code = fs.readFileSync(path.join(ROOT, 'utils', 'aiImageApi.js'), 'utf8');
  const sandbox = {
    module,
    wx,
    Promise,
    Date,
    setTimeout,
    clearTimeout,
    console: { log() {}, warn() {}, error() {} },
    require(request) {
      if (request === './apiConfig.js') {
        return { API_BASE_URL: 'https://tupzjianzhao.chat', getApiRuntimeInfo() { return {}; } };
      }
      throw new Error('Unexpected module: ' + request);
    }
  };
  vm.runInNewContext(code, sandbox, { filename: 'utils/aiImageApi.js' });
  return module.exports;
}

function loadWatermarkConfig(apiConfig) {
  const module = { exports: {} };
  const code = fs.readFileSync(path.join(ROOT, 'utils', 'watermarkConfig.js'), 'utf8');
  vm.runInNewContext(code, {
    module,
    require(request) {
      if (request === './apiConfig.js') return apiConfig;
      throw new Error('Unexpected module: ' + request);
    }
  }, { filename: 'utils/watermarkConfig.js' });
  return module.exports;
}

function verifyAppStartupLog(runtimeInfo) {
  let appDefinition;
  const logs = [];
  const code = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
  vm.runInNewContext(code, {
    App(definition) { appDefinition = definition; },
    wx: { getStorageSync() { return []; } },
    console: { log(label, payload) { logs.push({ label, payload }); } },
    require(request) {
      if (request === './utils/apiConfig.js') return {
        API_BASE_URL: runtimeInfo.actualApiBaseUrl,
        getApiRuntimeInfo() { return runtimeInfo; }
      };
      if (request === './utils/authService.js') return {
        isLoggedIn() { return false; },
        getPhotoStorageKey() { return 'myPhotos'; }
      };
      throw new Error('Unexpected module: ' + request);
    }
  }, { filename: 'app.js' });
  const instance = { globalData: appDefinition.globalData };
  appDefinition.onLaunch.call(instance);
  return logs.find((entry) => entry.label === '[api-config] startup');
}

async function main() {
  const cloud = 'https://tupzjianzhao.chat';
  const targetKey = 'ID_PHOTO_API_TARGET';
  const modeKey = 'ID_PHOTO_LOCAL_DEVELOPMENT_MODE';
  const legacyDevelop = loadApiConfig('develop', { [targetKey]: 'local' });
  assert.strictEqual(legacyDevelop.config.API_BASE_URL, cloud, 'develop must default to cloud when only legacy local is stored');
  assert.strictEqual(legacyDevelop.storage[targetKey], undefined, 'legacy local target must be cleared');
  assert.strictEqual(loadWatermarkConfig(legacyDevelop.config).getWatermarkApiBaseUrl(), cloud, 'watermark must share the cloud-default route');

  const explicitLocal = loadApiConfig('develop', { [targetKey]: 'local', [modeKey]: 'enabled' });
  assert.strictEqual(explicitLocal.config.API_BASE_URL, 'http://127.0.0.1:8000', 'develop local requires explicit local-development mode');
  assert.strictEqual(explicitLocal.config.getApiRuntimeInfo().localDevelopmentModeEnabled, true);

  const manualMode = loadApiConfig('develop', {});
  assert.strictEqual(manualMode.config.setLocalDevelopmentMode(true), true);
  assert.strictEqual(manualMode.config.API_BASE_URL, 'http://127.0.0.1:8000');
  assert.strictEqual(manualMode.config.setLocalDevelopmentMode(false), true);
  assert.strictEqual(manualMode.config.API_BASE_URL, cloud);

  ['trial', 'release'].forEach((envVersion) => {
    const forcedCloud = loadApiConfig(envVersion, { [targetKey]: 'local', [modeKey]: 'enabled' });
    assert.strictEqual(forcedCloud.config.API_BASE_URL, cloud, envVersion + ' must ignore local mode');
    assert.strictEqual(forcedCloud.storage[targetKey], undefined, envVersion + ' must clear stale local target');
  });
  assert.strictEqual(loadApiConfig('develop', { [targetKey]: 'cloud' }).config.API_BASE_URL, cloud);

  const nativeMeta = await loadAiImageApi(makeWx('native-success')).prepareIdPhotoUploadSource('/origin.jpg');
  assert.strictEqual(nativeMeta.uploadPath, '/native.jpg');
  assert.strictEqual(nativeMeta.uploadWidth, 1600);
  assert.strictEqual(nativeMeta.compressFallback, false);

  const fallbackMeta = await loadAiImageApi(makeWx('native-fail')).prepareIdPhotoUploadSource('/origin.jpg');
  assert.strictEqual(fallbackMeta.uploadPath, '/canvas.jpg');
  assert.strictEqual(fallbackMeta.uploadWidth, 1600);
  assert.strictEqual(fallbackMeta.compressFallback, true);
  assert.notStrictEqual(fallbackMeta.uploadPath, fallbackMeta.originalPath, 'fallback must not upload the original photo');

  await assert.rejects(
    loadAiImageApi(makeWx('canvas-fail')).prepareIdPhotoUploadSource('/origin.jpg'),
    (error) => error && error.code === 'ID_PHOTO_UPLOAD_COPY_EXPORT_FAILED'
  );

  const source = fs.readFileSync(path.join(ROOT, 'utils', 'aiImageApi.js'), 'utf8');
  assert(source.includes('[id-photo-prepare] diagnostic:'), 'prepare diagnostics must be retained');
  const appSource = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
  assert(appSource.includes("[api-config] startup"), 'app startup must log API runtime diagnostics');
  assert(appSource.includes('actualApiBaseUrl'), 'app startup must log the resolved API URL');
  const startupLog = verifyAppStartupLog({
    envVersion: 'develop',
    storedApiTarget: '',
    actualApiBaseUrl: cloud
  });
  assert(startupLog, 'app startup diagnostic must be emitted');
  assert.strictEqual(startupLog.payload.envVersion, 'develop');
  assert.strictEqual(startupLog.payload.storedApiTarget, '');
  assert.strictEqual(startupLog.payload.actualApiBaseUrl, cloud);
  const devtoolsFlow = fs.readFileSync(path.join(ROOT, 'server', 'scripts', 'verify_devtools_business_flow.js'), 'utf8');
  assert(!devtoolsFlow.includes("setStorageSync', 'ID_PHOTO_API_TARGET', 'local'"), 'DevTools verification must not persist a local API target');
  console.log(JSON.stringify({
    passed: true,
    checks: {
      developDefaultsCloudAndClearsLegacyLocal: true,
      explicitLocalDevelopmentModeRequired: true,
      releaseAndTrialIgnoreStoredLocal: true,
      watermarkSharesCloudDefaultRoute: true,
      startupLogsResolvedApiRoute: true,
      devtoolsDoesNotPersistLocalTarget: true,
      nativeCompressionUsesWorkCopy: true,
      failedNativeCompressionUsesCanvasWorkCopy: true,
      failedWorkCopyRejectsInsteadOfUploadingOriginal: true,
      prepareDiagnosticLogging: true
    }
  }, null, 2));
}

main().catch((error) => {
  console.error(error.stack || error);
  process.exit(1);
});
