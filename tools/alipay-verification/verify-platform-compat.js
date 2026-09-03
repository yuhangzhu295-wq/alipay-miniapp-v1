const assert = require('assert');
const path = require('path');

const root = path.resolve(__dirname, '..', '..');
const storage = Object.create(null);
const calls = [];
let envVersion = 'develop';
let authCodeShouldFail = false;

global.my = {
  getAccountInfoSync() {
    return { miniProgram: { appId: '2021006186655158', envVersion } };
  },
  getStorageSync({ key }) {
    return { data: storage[key] || '' };
  },
  setStorageSync({ key, data }) {
    storage[key] = data;
  },
  removeStorageSync({ key }) {
    delete storage[key];
  },
  chooseImage(options) {
    calls.push({ method: 'chooseImage', options });
    options.success({ apFilePaths: ['/tmp/alipay-test.jpg'] });
    if (options.complete) options.complete({});
  },
  getAuthCode(options) {
    calls.push({ method: 'getAuthCode', options });
    if (authCodeShouldFail) {
      options.fail({ errMsg: 'getAuthCode:fail simulated' });
      return;
    }
    options.success({ authCode: 'alipay-simulated-auth-code' });
  },
  request(options) {
    calls.push({ method: 'request', options });
    options.success({
      statusCode: 200,
      data: {
        success: true,
        userId: 'user_platform_adapter_test',
        token: 'test-token-not-a-secret',
        provider: 'alipay_user_id',
        openidBound: false,
        identityBound: true,
        userInfo: { nickName: '支付宝测试用户', avatarUrl: '' },
      },
    });
  },
};

const compat = require(path.join(root, 'alipay/utils/platform/alipayWxCompat.js'));
const apiConfig = require(path.join(root, 'alipay/utils/apiConfig.js'));
const authService = require(path.join(root, 'alipay/utils/authService.js'));

async function main() {
  const report = { kind: 'alipay-client-compatibility', tests: {}, pass: false };

  let mediaResult = null;
  compat.chooseMedia({
    count: 1,
    sourceType: ['album'],
    success(result) { mediaResult = result; },
  });
  report.tests.chooseMediaNormalizesAlipayPath = Boolean(
    mediaResult && mediaResult.tempFiles && mediaResult.tempFiles.length === 1 &&
    mediaResult.tempFiles[0].tempFilePath === '/tmp/alipay-test.jpg'
  );

  let loginResult = null;
  compat.login({ success(result) { loginResult = result; } });
  const lastAuthCodeCall = calls.filter((item) => item.method === 'getAuthCode').at(-1);
  report.tests.loginMapsAuthCode = Boolean(
    loginResult && loginResult.code === 'alipay-simulated-auth-code' &&
    lastAuthCodeCall && lastAuthCodeCall.options.scopes === 'auth_base'
  );

  report.tests.developDefaultsToIsolatedStaging = apiConfig.getApiBaseUrl() === apiConfig.ALIPAY_STAGING_API_BASE_URL;
  storage.ID_PHOTO_API_TARGET = 'local';
  report.tests.legacyLocalDoesNotEnableLocal = apiConfig.getApiBaseUrl() === apiConfig.ALIPAY_STAGING_API_BASE_URL && !storage.ID_PHOTO_API_TARGET;
  apiConfig.setLocalDevelopmentMode(true);
  report.tests.explicitDevelopLocalModeAllowed = apiConfig.getApiBaseUrl() === apiConfig.LOCAL_API_BASE_URL;
  envVersion = 'trial';
  report.tests.trialForcesCloud = apiConfig.getApiBaseUrl() === apiConfig.CLOUD_API_BASE_URL;
  envVersion = 'release';
  report.tests.releaseForcesCloud = apiConfig.getApiBaseUrl() === apiConfig.CLOUD_API_BASE_URL;
  envVersion = 'develop';
  apiConfig.setLocalDevelopmentMode(false);

  authService.logout();
  const auth = await authService.loginWithProfile({ nickName: '支付宝测试用户' });
  const loginRequest = calls.filter((item) => item.method === 'request').at(-1);
  report.tests.boundIdentityStoredAfterLogin = Boolean(
    auth && auth.identityBound === true && auth.provider === 'alipay_user_id' &&
    loginRequest && /\/api\/auth\/alipay\/login$/.test(loginRequest.options.url)
  );

  authService.logout();
  authCodeShouldFail = true;
  const requestCountBefore = calls.filter((item) => item.method === 'request').length;
  let rejected = false;
  try {
    await authService.loginWithProfile({});
  } catch (_) {
    rejected = true;
  }
  const requestCountAfter = calls.filter((item) => item.method === 'request').length;
  report.tests.authCodeFailureNeverFallsBackAnonymous = rejected && requestCountAfter === requestCountBefore;

  report.pass = Object.values(report.tests).every(Boolean);
  console.log(JSON.stringify(report, null, 2));
  if (!report.pass) process.exitCode = 1;
}

main().catch((error) => {
  console.error(error && error.stack || String(error));
  process.exit(1);
});
