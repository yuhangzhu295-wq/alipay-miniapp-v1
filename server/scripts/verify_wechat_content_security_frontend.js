/*
 * Verify the real mini-program shared upload Gate with a deterministic wx API
 * simulation. It checks the client coordinator, not image algorithms.
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const REPORT_DIR = path.join(ROOT, 'reports', 'wechat-content-security');
const storage = {
  userAuth: {
    userId: 'frontend-security-user',
    token: 'frontend-security-token',
    openidBound: true,
    userInfo: { nickName: '测试用户' }
  }
};
const metrics = {
  securityUploads: 0,
  businessUploads: 0,
  polls: 0,
  businessFormData: [],
  businessHeaders: []
};

function asyncCall(fn) {
  setTimeout(fn, 0);
}

global.wx = {
  getAccountInfoSync() {
    return { miniProgram: { envVersion: 'develop' } };
  },
  getStorageSync(key) { return storage[key] || ''; },
  setStorageSync(key, value) { storage[key] = value; },
  removeStorageSync(key) { delete storage[key]; },
  getFileInfo(options) { asyncCall(() => options.success({ size: 4096 })); },
  request(options) {
    if (String(options.url).indexOf('/api/content-security/images/') >= 0) {
      metrics.polls += 1;
      const isRejected = String(options.url).indexOf('reject-check') >= 0;
      asyncCall(() => options.success({
        statusCode: 200,
        data: isRejected
          ? { status: 'REJECT', securityCheckId: 'reject-check' }
          : { status: metrics.polls < 2 ? 'PENDING' : 'PASS', securityCheckId: 'pass-check', safeAssetId: 'pass-check' }
      }));
      return;
    }
    throw new Error('Unexpected wx.request: ' + options.url);
  },
  uploadFile(options) {
    if (String(options.url).indexOf('/api/content-security/images') >= 0) {
      metrics.securityUploads += 1;
      const rejected = String(options.filePath).indexOf('reject') >= 0;
      asyncCall(() => options.success({
        statusCode: 202,
        data: JSON.stringify({ status: 'PENDING', securityCheckId: rejected ? 'reject-check' : 'pass-check' })
      }));
      return { onProgressUpdate() {} };
    }
    metrics.businessUploads += 1;
    metrics.businessFormData.push(options.formData || {});
    metrics.businessHeaders.push(options.header || {});
    asyncCall(() => options.success({ statusCode: 200, data: JSON.stringify({ success: true }) }));
    return { onProgressUpdate() {} };
  }
};

function check(condition, message) {
  if (!condition) throw new Error(message);
}

async function callBusinessUpload(imageSafetyApi, filePath) {
  return new Promise((resolve) => {
    imageSafetyApi.uploadWithSafety({
      url: 'https://tupzjianzhao.chat/api/id-photo/prepare',
      filePath,
      name: 'image',
      formData: { specId: 'one-inch' },
      success: resolve,
      fail: resolve
    }, 'id_photo');
  });
}

async function main() {
  const imageSafetyApi = require(path.join(ROOT, 'utils', 'imageSafetyApi.js'));
  const checks = [];
  const add = (name, passed, detail) => checks.push({ name, passed: !!passed, detail: detail || {} });

  const sameImage = '/tmp/security-pass.jpg';
  const results = await Promise.all([
    imageSafetyApi.ensureImageSafety(sameImage, 'id_photo'),
    imageSafetyApi.ensureImageSafety(sameImage, 'id_photo'),
    imageSafetyApi.ensureImageSafety(sameImage, 'id_photo'),
    imageSafetyApi.ensureImageSafety(sameImage, 'id_photo'),
    imageSafetyApi.ensureImageSafety(sameImage, 'id_photo')
  ]);
  check(results.every((item) => item.securityCheckId === 'pass-check'), 'same image must receive the PASS security check id');
  check(metrics.securityUploads === 1, 'same image must submit only one security upload while in flight');
  add('same_image_inflight_deduplication', true, { securityUploads: metrics.securityUploads });

  const successResponse = await callBusinessUpload(imageSafetyApi, sameImage);
  check(successResponse.statusCode === 200, 'PASS image must reach business upload');
  check(metrics.businessUploads === 1, 'PASS image must start one business upload');
  check(metrics.businessFormData[0].securityCheckId === 'pass-check', 'business upload must carry securityCheckId');
  check(String(metrics.businessHeaders[0].Authorization || '').indexOf('Bearer ') === 0, 'business upload must carry authenticated user identity');
  add('pass_before_business_upload', true, {
    securityCheckId: metrics.businessFormData[0].securityCheckId,
    authorizationPresent: !!metrics.businessHeaders[0].Authorization
  });

  const beforeRejectedBusiness = metrics.businessUploads;
  const rejectedResponse = await callBusinessUpload(imageSafetyApi, '/tmp/security-reject.jpg');
  const rejectedData = JSON.parse(rejectedResponse.data || '{}');
  check(rejectedResponse.statusCode === 403, 'REJECT image must surface as HTTP 403 to existing UI handlers');
  check(rejectedData.code === 'CONTENT_SAFETY_REJECTED', 'REJECT code must be preserved');
  check(rejectedData.message === '图片内容不符合平台规范，请更换图片后重试。', 'REJECT message must be user-safe');
  check(metrics.businessUploads === beforeRejectedBusiness, 'REJECT image must not start business upload');
  add('reject_blocks_business_upload', true, { businessUploads: metrics.businessUploads });

  const report = {
    generatedAt: new Date().toISOString(),
    summary: { passed: checks.filter((item) => item.passed).length, total: checks.length, allPassed: checks.every((item) => item.passed) },
    checks,
    metrics
  };
  fs.mkdirSync(REPORT_DIR, { recursive: true });
  fs.writeFileSync(path.join(REPORT_DIR, 'frontend-gate-test.json'), JSON.stringify(report, null, 2), 'utf8');
  process.stdout.write(JSON.stringify(report.summary) + '\n');
}

main().catch((error) => {
  process.stderr.write(String(error && error.stack || error) + '\n');
  process.exitCode = 1;
});
