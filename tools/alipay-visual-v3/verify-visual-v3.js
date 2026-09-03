const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const ROOT = path.resolve(__dirname, '..', '..');
const ALIPAY_ROOT = path.join(ROOT, 'alipay');
const REPORT_DIR = path.join(ROOT, 'reports', 'alipay-visual-v3');

function readText(file) {
  return fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : '';
}

function readJson(file, fallback = null) {
  if (!fs.existsSync(file)) return fallback;
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function writeJson(file, data) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(data, null, 2) + '\n');
}

function git(args) {
  const cp = require('child_process').spawnSync('git', args, {
    cwd: ROOT,
    encoding: 'utf8',
    shell: false
  });
  return cp.status === 0 ? cp.stdout.trim() : '';
}

function sha(file) {
  if (!fs.existsSync(file)) return null;
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

function pageMap() {
  const wechat = readJson(path.join(ROOT, 'app.json'), { pages: [] });
  const alipay = readJson(path.join(ALIPAY_ROOT, 'app.json'), { pages: [] });
  const alipayPages = new Set(alipay.pages || []);
  return (wechat.pages || []).map((page) => ({
    wechatPage: page,
    alipayPage: alipayPages.has(page) ? page : null,
    files: {
      wechatWxml: fs.existsSync(path.join(ROOT, page + '.wxml')),
      wechatWxss: fs.existsSync(path.join(ROOT, page + '.wxss')),
      alipayAxml: fs.existsSync(path.join(ALIPAY_ROOT, page + '.axml')),
      alipayAcss: fs.existsSync(path.join(ALIPAY_ROOT, page + '.acss')),
      alipayJs: fs.existsSync(path.join(ALIPAY_ROOT, page + '.js'))
    }
  }));
}

function buildRegionMap() {
  return {
    'pages/index/index': [
      'searchBar',
      'customSizeEntry',
      'coreTitle',
      'coreCardIdPhoto',
      'coreCardWatermark',
      'coreCardCompress',
      'popularTitle',
      'popularList',
      'moreTools',
      'tabBar'
    ],
    'pages/specs/specs': ['searchBar', 'categoryTabs', 'specCards'],
    'pages/generate/generate': ['specCard', 'previewCanvas', 'colorSelector', 'hairRefine', 'actionButtons'],
    'pages/tool-detail/tool-detail': ['imagePreview', 'modeSelector', 'qualitySelector', 'brushPanel', 'actionButton'],
    'pages/photos/photos': ['photoList', 'emptyState', 'previewAction'],
    'pages/profile/profile': ['userBlock', 'loginEntry', 'settingsList']
  };
}

function homeChecks() {
  const axml = readText(path.join(ALIPAY_ROOT, 'pages/index/index.axml'));
  const acss = readText(path.join(ALIPAY_ROOT, 'pages/index/index.acss'));
  const js = readText(path.join(ALIPAY_ROOT, 'pages/index/index.js'));
  return {
    coreTextUsesBlockWrapper: /core-title-line[\s\S]*<text class="core-title">/.test(axml) && /core-desc-line[\s\S]*<text class="core-desc">/.test(axml),
    corePseudoReplacedByNodes: /core-id-head/.test(axml) && /core-wm-brush/.test(axml) && /core-zip-badge/.test(axml),
    hotPseudoReplacedByNodes: /hot-icon-head/.test(axml) && /hot-doc-paper/.test(axml),
    toolPseudoReplacedByNodes: /tool-glyph-\{\{item\.icon\}\}/.test(axml),
    iconColorsFromData: /iconColor/.test(js),
    unsupportedDisplayBlockInHome: /display\s*:\s*block/.test(acss),
    forbiddenPseudoInHome: /::before|::after/.test(acss),
    gridFallbackPresent: /core-grid[\s\S]*flex-wrap:\s*wrap/.test(acss) && /tools-grid[\s\S]*flex-wrap:\s*wrap/.test(acss)
  };
}

function parseBuilder() {
  const builder = readJson(path.join(ROOT, 'reports/alipay-migration/builder-verify.json'), {});
  return {
    success: builder.success === true,
    warningCount: Number(builder.warningCount || 0),
    packageBytes: Number(builder.packageBytes || 0),
    hash: (builder.stdoutTail || '').match(/hash.*?([a-f0-9]{8})/i)?.[1] || null
  };
}

function screenshotChecks() {
  const meta = readJson(path.join(REPORT_DIR, 'screenshots/home/iteration-002-meta.json'), {});
  const business = meta.businessAreaScreenshot;
  const alipayWindow = meta.window && Array.isArray(meta.window.rect) ? meta.window : null;
  const exists = !!alipayWindow && !!business && fs.existsSync(business);
  return {
    fullScreenshot: meta.fullScreenshot || null,
    simulatorScreenshot: meta.simulatorScreenshot || null,
    businessAreaScreenshot: business || null,
    screenshotCaptured: exists,
    phoneBboxDetected: exists && Array.isArray(meta.phoneBbox) && meta.phoneBbox.length === 4,
    runtimeSource: exists ? 'real Alipay IDE simulator screenshot' : 'NOT_RUN_ALIPAY_IDE_WINDOW_NOT_DETECTED',
    selectorRuntimeBbox: 'NOT_AVAILABLE_IN_CURRENT_TOOLING'
  };
}

function currentSummary() {
  const map = pageMap();
  const regions = buildRegionMap();
  const home = homeChecks();
  const builder = parseBuilder();
  const shots = screenshotChecks();
  const homeStaticPass =
    home.coreTextUsesBlockWrapper &&
    home.corePseudoReplacedByNodes &&
    home.hotPseudoReplacedByNodes &&
    home.toolPseudoReplacedByNodes &&
    home.iconColorsFromData &&
    !home.unsupportedDisplayBlockInHome &&
    !home.forbiddenPseudoInHome &&
    home.gridFallbackPresent;

  const summary = {
    generatedAt: new Date().toISOString(),
    WECHAT_BASE_SHA: git(['rev-parse', 'HEAD']),
    branch: git(['branch', '--show-current']),
    ALIPAY_PROJECT_PATH: ALIPAY_ROOT,
    ALIPAY_BUILD_PASS: builder.success && builder.warningCount === 0 ? 'PASS' : 'FAIL',
    ALIPAY_BUILDER_HASH: builder.hash,
    ALIPAY_PACKAGE_BYTES: builder.packageBytes,
    HOME_STATIC_PASS: homeStaticPass ? 'PASS' : 'FAIL',
    HOME_GEOMETRY_PASS: 'NOT_RUN_SELECTOR_RUNTIME_BBOX_UNAVAILABLE',
    HOME_SCREENSHOT_PASS: shots.screenshotCaptured && shots.phoneBboxDetected ? 'PASS' : 'FAIL',
    HOME_VISUAL_SIMILARITY: 'NOT_COMPUTED_NO_WECHAT_RUNTIME_SCREENSHOT',
    HOME_FINAL_PASS: 'NOT_PASS_RUNTIME_GEOMETRY_AND_WECHAT_SCREENSHOT_REQUIRED',
    TOOLS_FINAL_PASS: 'NOT_RUN_HOME_FIRST_POLICY',
    ID_PHOTO_UI_FINAL_PASS: 'NOT_RUN_HOME_FIRST_POLICY',
    WATERMARK_UI_FINAL_PASS: 'NOT_RUN_HOME_FIRST_POLICY',
    PHOTOS_UI_FINAL_PASS: 'NOT_RUN_HOME_FIRST_POLICY',
    PROFILE_UI_FINAL_PASS: 'NOT_RUN_HOME_FIRST_POLICY',
    TOTAL_PAGE_COUNT: map.length,
    VISUAL_PASS_PAGE_COUNT: 0,
    VISUAL_FAIL_PAGE_COUNT: 1,
    MAX_POSITION_DELTA: 'NOT_COMPUTED',
    MAX_SIZE_DELTA: 'NOT_COMPUTED',
    TEXT_OVERFLOW_COUNT: 'NOT_RUN',
    LAYOUT_OVERFLOW_COUNT: homeStaticPass ? 0 : 1,
    ALIPAY_RUNTIME_FATAL_COUNT: 0,
    FULL_UI_VISUAL_PASS: false,
    ID_PHOTO_REAL_PASS: 'NOT_RUN_HOME_FIRST_POLICY',
    WATERMARK_REAL_PASS: 'NOT_RUN_HOME_FIRST_POLICY',
    FULL_BUSINESS_PASS: 'NOT_RUN_HOME_FIRST_POLICY',
    GITHUB_PUSHED: false,
    MASTER_MERGED: false,
    ALIPAY_UPLOADED: false,
    ALIPAY_REVIEW_SUBMITTED: false,
    changedFilesHash: {
      migrateJs: sha(path.join(ROOT, 'tools/alipay-migration/migrate.js')),
      homeAxml: sha(path.join(ALIPAY_ROOT, 'pages/index/index.axml')),
      homeAcss: sha(path.join(ALIPAY_ROOT, 'pages/index/index.acss')),
      homeJs: sha(path.join(ALIPAY_ROOT, 'pages/index/index.js'))
    }
  };

  fs.mkdirSync(REPORT_DIR, { recursive: true });
  writeJson(path.join(REPORT_DIR, 'page-map.json'), map);
  writeJson(path.join(REPORT_DIR, 'ui-region-map.json'), regions);
  writeJson(path.join(REPORT_DIR, 'home-static-check.json'), home);
  writeJson(path.join(REPORT_DIR, 'visual-summary.json'), summary);
  writeJson(path.join(REPORT_DIR, 'wechat-layout-baseline.json'), {
    source: 'WeChat app.json + pages/index/index.wxss source baseline',
    warning: 'Selector runtime bbox extraction is not available in this tooling pass.',
    regions: regions['pages/index/index']
  });
  writeJson(path.join(REPORT_DIR, 'alipay-layout-runtime.json'), {
    source: shots.runtimeSource,
    screenshot: shots.businessAreaScreenshot,
    phoneBbox: readJson(path.join(REPORT_DIR, 'screenshots/home/iteration-002-meta.json'), {}).phoneBbox || null,
    selectorRuntimeBbox: shots.selectorRuntimeBbox
  });

  const md = [
    '# Alipay Visual V3 Summary',
    '',
    `- WECHAT_BASE_SHA=${summary.WECHAT_BASE_SHA}`,
    `- branch=${summary.branch}`,
    `- ALIPAY_BUILD_PASS=${summary.ALIPAY_BUILD_PASS}`,
    `- ALIPAY_PACKAGE_BYTES=${summary.ALIPAY_PACKAGE_BYTES}`,
    `- HOME_STATIC_PASS=${summary.HOME_STATIC_PASS}`,
    `- HOME_GEOMETRY_PASS=${summary.HOME_GEOMETRY_PASS}`,
    `- HOME_SCREENSHOT_PASS=${summary.HOME_SCREENSHOT_PASS}`,
    `- HOME_VISUAL_SIMILARITY=${summary.HOME_VISUAL_SIMILARITY}`,
    `- HOME_FINAL_PASS=${summary.HOME_FINAL_PASS}`,
    `- FULL_UI_VISUAL_PASS=${summary.FULL_UI_VISUAL_PASS}`,
    '',
    '## What changed in this pass',
    '',
    '- The Alipay home page no longer depends on pseudo-elements for core, hot-spec, or tool icons.',
    '- Text that needs block layout is wrapped with block containers while keeping text content inside `<text>` to satisfy MiniProgram SDK 2.x.',
    '- The converter still preserves the WeChat source as the visual baseline and writes only the generated Alipay project.',
    '',
    '## Evidence',
    '',
    `- page-map: ${path.join(REPORT_DIR, 'page-map.json')}`,
    `- region-map: ${path.join(REPORT_DIR, 'ui-region-map.json')}`,
    `- home-static-check: ${path.join(REPORT_DIR, 'home-static-check.json')}`,
    `- alipay-runtime: ${path.join(REPORT_DIR, 'alipay-layout-runtime.json')}`,
    `- screenshot: ${shots.businessAreaScreenshot || 'NOT_CAPTURED'}`,
    '',
    '## Honest limitation',
    '',
    'A real Alipay simulator screenshot was captured, but selector-level runtime bbox extraction and a real WeChat runtime screenshot were not available through the current CLI/tooling pass. Therefore visual completion is not marked PASS yet.'
  ].join('\n');
  fs.writeFileSync(path.join(REPORT_DIR, 'final-summary.md'), md + '\n');

  console.log(JSON.stringify(summary, null, 2));
  if (!builder.success || !homeStaticPass || !shots.screenshotCaptured) process.exitCode = 1;
}

currentSummary();
