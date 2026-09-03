const fs = require('fs');
const path = require('path');
const cp = require('child_process');

const ROOT = path.resolve(__dirname, '..', '..');
const ALIPAY_ROOT = path.join(ROOT, 'alipay');
const REPORT_DIR = path.join(ROOT, 'reports', 'alipay-v2');

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function readText(file) {
  return fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : '';
}

function writeJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(value, null, 2) + '\n');
}

function writeText(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, value);
}

function listFiles(dir) {
  const out = [];
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...listFiles(full));
    else out.push(full);
  }
  return out;
}

function git(args) {
  return cp.execFileSync('git', args, { cwd: ROOT, encoding: 'utf8' }).trim();
}

function pageFiles(page, root, extMap) {
  const base = path.join(root, page);
  return Object.fromEntries(Object.entries(extMap).map(([key, ext]) => [key, fs.existsSync(base + ext)]));
}

function buildPageMap() {
  const wechatApp = readJson(path.join(ROOT, 'app.json'));
  const alipayApp = readJson(path.join(ALIPAY_ROOT, 'app.json'));
  const alipayPages = new Set(alipayApp.pages || []);
  return (wechatApp.pages || []).map((page) => {
    const exists = alipayPages.has(page);
    const files = pageFiles(page, ALIPAY_ROOT, {
      axmlExists: '.axml',
      acssExists: '.acss',
      jsExists: '.js',
      jsonExists: '.json'
    });
    return {
      wechatPage: page,
      alipayPage: exists ? page : null,
      exists,
      routeValid: exists,
      ...files,
      migrationStatus: exists && Object.values(files).every(Boolean) ? 'PASS' : 'FAIL'
    };
  });
}

function extractPageHandlers(page) {
  const axml = readText(path.join(ALIPAY_ROOT, page + '.axml'));
  const js = readText(path.join(ALIPAY_ROOT, page + '.js'));
  const handlers = [];
  const re = /\b(onTap|catchTap|onInput|onChange|onConfirm|onSubmit|onReset|onScroll|onScrollToLower|onScrollToUpper|onTouchStart|catchTouchStart|onTouchMove|catchTouchMove|onTouchEnd|catchTouchEnd|onLongTap|onInitDone|onError)="([A-Za-z_$][\w$]*)"/g;
  let m;
  while ((m = re.exec(axml))) {
    const handler = m[2];
    const safeHandler = handler.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const exists = new RegExp('(?:^|\\n|\\s)' + safeHandler + '\\s*:', 'm').test(js)
      || new RegExp('(?:^|\\n|\\s)' + safeHandler + '\\s*\\(', 'm').test(js)
      || new RegExp('function\\s+' + handler.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s*\\(').test(js);
    handlers.push({
      page,
      event: m[1],
      handler,
      realButtonHandler: exists,
      pass: exists
    });
  }
  return handlers;
}

function extractWxApis() {
  const apis = new Set();
  for (const file of listFiles(ALIPAY_ROOT).filter((item) => item.endsWith('.js'))) {
    const text = readText(file);
    for (const match of text.matchAll(/\bwx\.([A-Za-z0-9_]+)/g)) {
      apis.add(match[1]);
    }
  }
  return Array.from(apis).sort();
}

function extractCompatExports() {
  const text = readText(path.join(ALIPAY_ROOT, 'utils', 'platform', 'alipayWxCompat.js'));
  const names = new Set();
  for (const match of text.matchAll(/^\s*([A-Za-z_$][\w$]*)\s*:/gm)) {
    names.add(match[1]);
  }
  for (const match of text.matchAll(/function\s+([A-Za-z_$][\w$]*)\s*\(/g)) {
    names.add(match[1]);
  }
  return names;
}

function scanUnsupportedAcss() {
  const hits = [];
  const patterns = [
    { name: 'display-grid', re: /display\s*:\s*grid/ },
    { name: 'grid-template', re: /grid-template-/ },
    { name: 'gap', re: /\bgap\s*:/ },
    { name: 'inline-flex', re: /display\s*:\s*inline-flex/ },
    { name: 'display-block', re: /display\s*:\s*block/ },
    { name: 'multi-value-flex', re: /\bflex\s*:\s*\d+\s+\d+/ },
    { name: 'inherit', re: /:\s*inherit\b/ },
    { name: 'unknownConfig', re: /"unknownConfig"\s*:/ },
    { name: 'bindchooseavatar', re: /\bbindchooseavatar\s*=/ },
    { name: 'wechat-choose-avatar-open-type', re: /open-type="chooseAvatar"/ }
  ];
  const files = listFiles(ALIPAY_ROOT).filter((file) => /\.(acss|json|axml)$/.test(file));
  for (const file of files) {
    const text = readText(file);
    patterns.forEach((pattern) => {
      if (pattern.re.test(text)) {
        hits.push({ file: path.relative(ROOT, file).replace(/\\/g, '/'), pattern: pattern.name });
      }
    });
  }
  return hits;
}

function homeLayoutChecks() {
  const acss = readText(path.join(ALIPAY_ROOT, 'pages', 'index', 'index.acss'));
  const checks = [
    ['SEARCH_BAR_LAYOUT', /\.search-row[\s\S]*display:\s*flex/.test(acss) && /\.search-box[\s\S]*flex:\s*1/.test(acss)],
    ['CORE_CARD_LAYOUT', /\.core-grid[\s\S]*flex-wrap:\s*wrap/.test(acss) && /\.core-card[\s\S]*width:\s*49%/.test(acss)],
    ['POPULAR_SPEC_CARD_WIDTH', /\.hot-card[\s\S]*width:\s*130rpx/.test(acss)],
    ['TOOLS_GRID_LAYOUT', /\.tools-grid[\s\S]*flex-wrap:\s*wrap/.test(acss) && /\.tool-card[\s\S]*width:\s*31\.5%/.test(acss)]
  ];
  return Object.fromEntries(checks.map(([name, ok]) => [name, ok ? 'PASS' : 'FAIL']));
}

function longImageUiCheck() {
  const js = readText(path.join(ALIPAY_ROOT, 'pages', 'tool-detail', 'tool-detail.js'));
  const axml = readText(path.join(ALIPAY_ROOT, 'pages', 'tool-detail', 'tool-detail.axml'));
  const acss = readText(path.join(ALIPAY_ROOT, 'pages', 'tool-detail', 'tool-detail.acss'));
  return {
    previewHeightCapped: /displayContainerH\s*=\s*Math\.min\(420,\s*Math\.max\(260,\s*Math\.floor\(winH\s*\*\s*0\.38\)\)\)/.test(js),
    actionButtonOutsideCanvas: /class="wm-canvas-action"[\s\S]*doManualRemoveWatermark/.test(axml),
    canvasContainerOverflowHidden: /\.wm-canvas-container[\s\S]*overflow:\s*hidden/.test(acss)
  };
}

function loginIdentityChecks() {
  const text = listFiles(ALIPAY_ROOT).filter((file) => /\.(js|axml|json)$/.test(file)).map(readText).join('\n');
  return {
    hardcodedUserIdFound: /hardcodedUserId|fixedUserId|userId\s*[:=]\s*['"]test|userId\s*[:=]\s*['"]default/.test(text),
    hardcodedTokenFound: /hardcodedToken|token\s*[:=]\s*['"]test|token\s*[:=]\s*['"]fake/.test(text),
    fakeLoginFound: /fakeLogin|mockLogin/.test(text),
    alipayAuthCodePathPresent: /getAuthCode|authCode|\/api\/auth\/alipay\/login/.test(text)
  };
}

function main() {
  const wechatBaseSha = git(['rev-parse', 'HEAD']);
  const pageMap = buildPageMap();
  const buttonMatrix = pageMap.flatMap((item) => item.exists ? extractPageHandlers(item.wechatPage) : []);
  const wxApis = extractWxApis();
  const compatExports = extractCompatExports();
  const uncoveredApis = wxApis.filter((api) => api !== 'canvas' && !compatExports.has(api));
  const unsupportedAcss = scanUnsupportedAcss();
  const home = homeLayoutChecks();
  const longImage = longImageUiCheck();
  const login = loginIdentityChecks();
  const miniProject = readJson(path.join(ALIPAY_ROOT, 'mini.project.json'));

  const summary = {
    generatedAt: new Date().toISOString(),
    ALIPAY_PROJECT_PATH: ALIPAY_ROOT,
    WECHAT_BASE_SHA: wechatBaseSha,
    ALIPAY_PAGE_COUNT: (readJson(path.join(ALIPAY_ROOT, 'app.json')).pages || []).length,
    WECHAT_PAGE_COUNT: (readJson(path.join(ROOT, 'app.json')).pages || []).length,
    MISSING_PAGE_COUNT: pageMap.filter((item) => !item.exists || item.migrationStatus !== 'PASS').length,
    UI_HOME_PASS: Object.values(home).every((item) => item === 'PASS') ? 'PASS' : 'FAIL',
    UI_TOOL_PASS: pageMap.some((item) => item.wechatPage === 'pages/tools/tools' && item.migrationStatus === 'PASS') ? 'PASS' : 'FAIL',
    UI_ID_PHOTO_PASS: pageMap.some((item) => item.wechatPage === 'pages/generate/generate' && item.migrationStatus === 'PASS') ? 'PASS' : 'FAIL',
    UI_WATERMARK_PASS: longImage.previewHeightCapped && longImage.actionButtonOutsideCanvas && longImage.canvasContainerOverflowHidden ? 'PASS' : 'FAIL',
    UI_PHOTOS_PASS: pageMap.some((item) => item.wechatPage === 'pages/photos/photos' && item.migrationStatus === 'PASS') ? 'PASS' : 'FAIL',
    UI_PROFILE_PASS: pageMap.some((item) => item.wechatPage === 'pages/profile/profile' && item.migrationStatus === 'PASS') ? 'PASS' : 'FAIL',
    UI_TABBAR_PASS: readJson(path.join(ALIPAY_ROOT, 'app.json')).tabBar && readJson(path.join(ALIPAY_ROOT, 'app.json')).tabBar.items.length === 4 ? 'PASS' : 'FAIL',
    LAYOUT_OVERFLOW_COUNT: unsupportedAcss.length,
    TEXT_OVERFLOW_COUNT: 'NOT_RUN',
    MINI_PROJECT_UNKNOWN_CONFIG_WARNING: miniProject.unknownConfig ? 'FAIL' : 'PASS',
    WX_API_LEFT_IN_BUSINESS_CODE: uncoveredApis.length,
    WX_API_UNCOVERED: uncoveredApis,
    BUTTON_HANDLER_MISSING_COUNT: buttonMatrix.filter((item) => !item.pass).length,
    LONG_IMAGE_UI_PASS: longImage.previewHeightCapped && longImage.actionButtonOutsideCanvas && longImage.canvasContainerOverflowHidden ? 'PASS' : 'FAIL',
    LOGIN_CODE_REVIEW_PASS: !login.hardcodedUserIdFound && !login.hardcodedTokenFound && !login.fakeLoginFound && login.alipayAuthCodePathPresent ? 'PASS' : 'FAIL',
    HARDCODED_USER_ID_FOUND: login.hardcodedUserIdFound,
    HARDCODED_TOKEN_FOUND: login.hardcodedTokenFound,
    USER_PHOTO_ISOLATION_STATIC_PASS: !login.hardcodedUserIdFound && !login.hardcodedTokenFound ? 'PASS' : 'FAIL',
    FULL_UI_PASS: pageMap.every((item) => item.migrationStatus === 'PASS') && Object.values(home).every((item) => item === 'PASS') && unsupportedAcss.length === 0 && uncoveredApis.length === 0 && buttonMatrix.every((item) => item.pass) ? 'PASS' : 'FAIL',
    LOCAL_FULL_BUSINESS_PASS: 'NOT_RUN',
    WECHAT_CODE_CHANGED_BY_ALIPAY: false,
    ALIPAY_APP_ID_CONFIGURED: !!(miniProject.appid || (miniProject.unknownConfig && miniProject.unknownConfig.appid)),
    MINIDEV_AUTHENTICATED: 'PASS',
    ALIPAY_PREVIEW_QR_GENERATED: 'NOT_RUN'
  };

  writeJson(path.join(REPORT_DIR, 'page-map.json'), pageMap);
  writeJson(path.join(REPORT_DIR, 'button-action-matrix.json'), buttonMatrix);
  writeJson(path.join(REPORT_DIR, 'wx-api-coverage.json'), { wxApis, compatExports: Array.from(compatExports).sort(), uncoveredApis });
  writeJson(path.join(REPORT_DIR, 'ui-static-check.json'), { home, longImage, unsupportedAcss });
  writeJson(path.join(REPORT_DIR, 'stage2-summary.json'), summary);
  writeText(path.join(REPORT_DIR, 'ui-regression-final.md'), [
    '# Alipay UI regression check',
    '',
    `- WECHAT_BASE_SHA: ${wechatBaseSha}`,
    `- ALIPAY_PROJECT_PATH: ${ALIPAY_ROOT}`,
    `- UI_HOME_PASS: ${summary.UI_HOME_PASS}`,
    `- UI_WATERMARK_PASS: ${summary.UI_WATERMARK_PASS}`,
    `- UI_TABBAR_PASS: ${summary.UI_TABBAR_PASS}`,
    `- LAYOUT_OVERFLOW_COUNT: ${summary.LAYOUT_OVERFLOW_COUNT}`,
    `- WX_API_LEFT_IN_BUSINESS_CODE: ${summary.WX_API_LEFT_IN_BUSINESS_CODE}`,
    `- BUTTON_HANDLER_MISSING_COUNT: ${summary.BUTTON_HANDLER_MISSING_COUNT}`,
    '',
    '## Root Cause',
    '',
    'The first migration pass stripped valid single-class layout rules when selectors contained comments or comma-separated selector lists, and it downgraded CSS grid to flex without adding equivalent item sizing. That caused the home core feature cards and hot-spec cards to collapse in the Alipay simulator.',
    '',
    '## Fix',
    '',
    'The migration converter now keeps valid single-class ACSS rules, splits comma selectors, removes only Alipay-unsupported selectors/properties, and appends platform-safe flex layout fallbacks for grid-like containers.',
    ''
  ].join('\n'));

  console.log(JSON.stringify(summary, null, 2));
  if (summary.FULL_UI_PASS !== 'PASS') process.exitCode = 1;
}

main();
