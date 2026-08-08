const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..', '..');

function loadApiConfig(envVersion, storedApiTarget) {
  const module = { exports: {} };
  const code = fs.readFileSync(path.join(ROOT, 'utils', 'apiConfig.js'), 'utf8');
  const wx = {
    getAccountInfoSync() { return { miniProgram: { envVersion } }; },
    getStorageSync() { return storedApiTarget; }
  };
  vm.runInNewContext(code, { module, wx }, { filename: 'utils/apiConfig.js' });
  return module.exports;
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

async function main() {
  const cloud = 'https://tupzjianzhao.chat';
  assert.strictEqual(loadApiConfig('release', 'local').API_BASE_URL, cloud, 'release must ignore stored local');
  assert.strictEqual(loadApiConfig('trial', 'local').API_BASE_URL, cloud, 'trial must ignore stored local');
  assert.strictEqual(loadApiConfig('develop', 'local').API_BASE_URL, 'http://127.0.0.1:8000');
  assert.strictEqual(loadApiConfig('develop', 'cloud').API_BASE_URL, cloud);

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
  console.log(JSON.stringify({
    passed: true,
    checks: {
      releaseAndTrialIgnoreStoredLocal: true,
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
