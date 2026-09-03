const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..', '..');
const PAGE_PATH = path.join(ROOT, 'pages', 'tool-detail', 'tool-detail.js');
const WXML_PATH = path.join(ROOT, 'pages', 'tool-detail', 'tool-detail.wxml');
const DIAGNOSTIC_METHODS = [
  'runDiagHealthCheck',
  'diagTestRemoveBg',
  'diagTestChangeBg',
  'diagTestInpaint',
  'diagTestVerifyPhoto'
];

function createModuleStub(request, counters) {
  if (request.indexOf('specs.js') >= 0) {
    return {
      purposeOptions: [],
      compositionOptions: [],
      enhanceOptions: [],
      outfitOptions: [],
      advancedOutfitEnabled: false
    };
  }
  if (request.indexOf('aiImageApi.js') >= 0) {
    return {
      checkApiAvailable: function() {
        counters.diagnosticApiCalls += 1;
        return Promise.resolve({ ok: true });
      },
      removeBg: function() {
        counters.diagnosticApiCalls += 1;
        return Promise.resolve('/tmp/remove-bg.png');
      },
      changeBg: function() {
        counters.diagnosticApiCalls += 1;
        return Promise.resolve('/tmp/change-bg.png');
      },
      verifyPhoto: function() {
        counters.diagnosticApiCalls += 1;
        return Promise.resolve({ score: 100, qualified: true });
      }
    };
  }
  if (request.indexOf('inpaintApi.js') >= 0) {
    return {
      removeWatermarkByAI: function() {
        counters.diagnosticApiCalls += 1;
        return Promise.resolve({ tempFilePath: '/tmp/inpaint.png' });
      }
    };
  }
  if (request.indexOf('watermarkApi.js') >= 0) {
    return {
      getBaseUrl: function() { return 'https://tupzjianzhao.chat'; },
      checkHealth: function() { return Promise.resolve({}); },
      isHdRepairEnabled: function() { return true; }
    };
  }
  return new Proxy({}, {
    get: function() {
      return function() { return Promise.resolve({}); };
    }
  });
}

function loadPage(envVersion, storedPanel) {
  let definition = null;
  const counters = {
    diagnosticApiCalls: 0,
    toastCalls: 0,
    storageWrites: 0,
    storageRemovals: 0
  };
  const storage = { showDebugPanel: storedPanel };
  const sandbox = {
    Page: function(pageDefinition) { definition = pageDefinition; },
    require: function(request) { return createModuleStub(request, counters); },
    console: console,
    Promise: Promise,
    setTimeout: function() { return 1; },
    clearTimeout: function() {},
    wx: {
      getAccountInfoSync: function() {
        return { miniProgram: { envVersion: envVersion } };
      },
      getStorageSync: function(key) { return storage[key]; },
      setStorageSync: function(key, value) {
        counters.storageWrites += 1;
        storage[key] = value;
      },
      removeStorageSync: function(key) {
        counters.storageRemovals += 1;
        delete storage[key];
      },
      setNavigationBarTitle: function() {},
      showToast: function() { counters.toastCalls += 1; },
      getImageInfo: function() { counters.diagnosticApiCalls += 1; }
    }
  };
  vm.runInNewContext(fs.readFileSync(PAGE_PATH, 'utf8'), sandbox, { filename: PAGE_PATH });
  assert(definition, 'Page definition was not registered');

  const page = Object.assign({}, definition);
  page.data = JSON.parse(JSON.stringify(definition.data));
  page.setData = function(patch) { Object.assign(page.data, patch); };
  return { page: page, counters: counters, storage: storage };
}

function runEnvironment(envVersion) {
  const runtime = loadPage(envVersion, envVersion === 'develop' ? false : true);
  const page = runtime.page;
  page.onLoad({ type: 'editImage' });

  const tapCount = envVersion === 'develop' ? 5 : 20;
  for (let i = 0; i < tapCount; i += 1) {
    page.onWatermarkTitleTap();
  }
  DIAGNOSTIC_METHODS.forEach(function(method) { page[method](); });

  const develop = envVersion === 'develop';
  const result = {
    envVersion: envVersion,
    debugPanelOpened: page.data.showDebugPanel === true,
    diagnosticButtonsVisible: page.data.isDevelopEnv === true && page.data.showDebugPanel === true,
    diagnosticActionsAvailable: runtime.counters.diagnosticApiCalls > 0 || runtime.counters.toastCalls > 0,
    diagnosticApiCalls: runtime.counters.diagnosticApiCalls,
    diagnosticToastCalls: runtime.counters.toastCalls,
    staleDebugStorageRemoved: runtime.counters.storageRemovals > 0
  };

  if (develop) {
    assert.strictEqual(page.data.isDevelopEnv, true);
    assert.strictEqual(result.debugPanelOpened, true);
    assert.strictEqual(result.diagnosticButtonsVisible, true);
    assert.strictEqual(result.diagnosticActionsAvailable, true);
  } else {
    assert.strictEqual(page.data.isDevelopEnv, false);
    assert.strictEqual(result.debugPanelOpened, false);
    assert.strictEqual(result.diagnosticButtonsVisible, false);
    assert.strictEqual(result.diagnosticActionsAvailable, false);
    assert.strictEqual(runtime.counters.diagnosticApiCalls, 0);
    assert.strictEqual(runtime.counters.toastCalls, 0);
    assert.strictEqual(result.staleDebugStorageRemoved, true);
  }
  return result;
}

function verifyTemplate() {
  const wxml = fs.readFileSync(WXML_PATH, 'utf8');
  assert(wxml.includes('<view class="section-title" wx:if="{{isDevelopEnv}}" bindtap="onWatermarkTitleTap">'));
  assert(wxml.includes('<view class="section-title" wx:else>'));
  assert(wxml.includes('wx:if="{{isDevelopEnv && showDebugPanel}}"'));
  DIAGNOSTIC_METHODS.forEach(function(method) {
    assert(wxml.includes('bindtap="' + method + '"'));
  });
  return {
    titleTapBoundOnlyInDevelop: true,
    debugPanelRenderedOnlyInDevelop: true,
    diagnosticButtonCount: DIAGNOSTIC_METHODS.length
  };
}

const report = {
  generatedAt: new Date().toISOString(),
  template: verifyTemplate(),
  environments: [
    runEnvironment('develop'),
    runEnvironment('trial'),
    runEnvironment('release')
  ],
  passed: true
};

const reportDir = path.join(ROOT, 'reports', 'wechat-review');
fs.mkdirSync(reportDir, { recursive: true });
fs.writeFileSync(
  path.join(reportDir, 'debug-isolation.json'),
  JSON.stringify(report, null, 2) + '\n',
  'utf8'
);
process.stdout.write(JSON.stringify(report, null, 2) + '\n');
