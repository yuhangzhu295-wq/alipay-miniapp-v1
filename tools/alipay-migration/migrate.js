const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const ROOT = path.resolve(__dirname, '..', '..');
const OUT = path.join(ROOT, 'alipay');
const REPORT_DIR = path.join(ROOT, 'reports', 'alipay-migration');
const ALIPAY_APP_ID = process.env.ALIPAY_APP_ID || '';

const COPY_ROOTS = ['images', 'pages', 'utils'];
const EXCLUDED_DIRS = new Set([
  '.git',
  '.agents',
  'backups',
  'deploy',
  'docs',
  'logs',
  'mockups',
  'reports',
  'server',
  'third_party',
  'tools',
  'alipay',
]);

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function writeFile(file, content) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, content);
}

function sha(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

function listFiles(dir) {
  const result = [];
  if (!fs.existsSync(dir)) return result;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      result.push(...listFiles(full));
    } else {
      result.push(full);
    }
  }
  return result;
}

function cleanOutputDir() {
  const resolved = path.resolve(OUT);
  if (!resolved.startsWith(ROOT + path.sep) || path.basename(resolved) !== 'alipay') {
    throw new Error('Refusing to clean unexpected path: ' + resolved);
  }
  fs.rmSync(resolved, { recursive: true, force: true });
  fs.mkdirSync(resolved, { recursive: true });
}

function convertMarkup(input, rel) {
  let text = input;
  const replacements = [
    [/\bwx:if=/g, 'a:if='],
    [/\bwx:elif=/g, 'a:elif='],
    [/\bwx:else\b/g, 'a:else'],
    [/\bwx:for=/g, 'a:for='],
    [/\bwx:for-item=/g, 'a:for-item='],
    [/\bwx:for-index=/g, 'a:for-index='],
    [/\bwx:key=/g, 'key='],
    [/\bbindtap=/g, 'onTap='],
    [/\bcatchtap=/g, 'catchTap='],
    [/\bbindinput=/g, 'onInput='],
    [/\bbindchange=/g, 'onChange='],
    [/\bbindconfirm=/g, 'onConfirm='],
    [/\bbindsubmit=/g, 'onSubmit='],
    [/\bbindreset=/g, 'onReset='],
    [/\bbindscroll=/g, 'onScroll='],
    [/\bbindscrolltolower=/g, 'onScrollToLower='],
    [/\bbindscrolltoupper=/g, 'onScrollToUpper='],
    [/\bbindtouchstart=/g, 'onTouchStart='],
    [/\bbindtouchmove=/g, 'onTouchMove='],
    [/\bbindtouchend=/g, 'onTouchEnd='],
    [/\bbindlongpress=/g, 'onLongTap='],
    [/\bbindinitdone=/g, 'onInitDone='],
    [/\bbinderror=/g, 'onError='],
    [/\bbindchooseavatar=/g, 'onTap='],
    [/\bcatchtouchstart=/g, 'catchTouchStart='],
    [/\bcatchtouchmove=/g, 'catchTouchMove='],
    [/\bcatchtouchend=/g, 'catchTouchEnd='],
  ];
  for (const [from, to] of replacements) text = text.replace(from, to);
  text = text.replace(/\sopen-type="chooseAvatar"/g, '');
  return enhanceAlipayHomeMarkup(wrapDirectViewText(text), rel || '');
}

function findTagEnd(text, start) {
  let quote = null;
  for (let i = start; i < text.length; i += 1) {
    const ch = text[i];
    if (quote) {
      if (ch === quote) quote = null;
    } else if (ch === '"' || ch === "'") {
      quote = ch;
    } else if (ch === '>') {
      return i;
    }
  }
  return -1;
}

function findMatchingViewClose(text, contentStart) {
  let depth = 1;
  let i = contentStart;
  while (i < text.length) {
    const nextOpen = text.indexOf('<view', i);
    const nextClose = text.indexOf('</view>', i);
    if (nextClose < 0) return -1;
    if (nextOpen >= 0 && nextOpen < nextClose) {
      const afterName = text[nextOpen + 5];
      if (!afterName || /[\s>/]/.test(afterName)) {
        depth += 1;
        const openEnd = findTagEnd(text, nextOpen);
        if (openEnd < 0) return -1;
        i = openEnd + 1;
        continue;
      }
    }
    depth -= 1;
    if (depth === 0) return nextClose;
    i = nextClose + '</view>'.length;
  }
  return -1;
}

function isPlainTextNode(inner) {
  if (!inner || !inner.trim()) return false;
  return !/<[a-zA-Z/!]/.test(inner);
}

function wrapDirectViewText(input) {
  let output = '';
  let i = 0;
  while (i < input.length) {
    const open = input.indexOf('<view', i);
    if (open < 0) {
      output += input.slice(i);
      break;
    }
    const afterName = input[open + 5];
    if (afterName && !/[\s>/]/.test(afterName)) {
      output += input.slice(i, open + 5);
      i = open + 5;
      continue;
    }
    const openEnd = findTagEnd(input, open);
    if (openEnd < 0) {
      output += input.slice(i);
      break;
    }
    const close = findMatchingViewClose(input, openEnd + 1);
    if (close < 0) {
      output += input.slice(i);
      break;
    }
    const openTag = input.slice(open, openEnd + 1);
    const inner = input.slice(openEnd + 1, close);
    output += input.slice(i, open);
    if (isPlainTextNode(inner)) {
      output += openTag + '<text>' + inner + '</text></view>';
    } else {
      output += openTag + wrapDirectViewText(inner) + '</view>';
    }
    i = close + '</view>'.length;
  }
  return output;
}

const CSS_VARS = {
  '--primary-hue': '228',
  '--secondary-hue': '269',
  '--primary': '#667eea',
  '--secondary': '#764ba2',
  '--primary-light': '#eef2ff',
  '--gradient-main': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
  '--gradient-glass': '#ffffff',
  '--gradient-glow': '#eef2ff',
  '--bg-main': '#f4f6fc',
  '--text-primary': '#1a1a2e',
  '--text-secondary': '#7e7e9a',
  '--text-light': '#b5b5c9',
  '--border-light': 'rgba(224, 229, 242, 0.8)',
  '--shadow-sm': '0 4rpx 10rpx rgba(102, 126, 234, 0.05)',
  '--shadow-md': '0 10rpx 30rpx rgba(102, 126, 234, 0.08)',
  '--shadow-lg': '0 20rpx 50rpx rgba(26, 26, 46, 0.06)',
  '--shadow-glass': '0 8rpx 32rpx rgba(102, 126, 234, 0.05)'
};

function isAlipaySimpleSelector(selector) {
  const text = selector.trim();
  if (!text || text.startsWith('@')) return false;
  if (text.includes(':') || /\s/.test(text)) return false;
  return /^\.[A-Za-z0-9_-]+$/.test(text);
}

function stripUnsupportedCssBlocks(css) {
  const cleanCss = css.replace(/\/\*[\s\S]*?\*\//g, '');
  let output = '';
  let i = 0;
  while (i < cleanCss.length) {
    const open = cleanCss.indexOf('{', i);
    if (open < 0) break;
    const selector = cleanCss.slice(i, open);
    let depth = 1;
    let j = open + 1;
    while (j < cleanCss.length && depth > 0) {
      if (cleanCss[j] === '{') depth += 1;
      else if (cleanCss[j] === '}') depth -= 1;
      j += 1;
    }
    const block = cleanCss.slice(open + 1, j - 1);
    const simpleSelectors = selector.split(',').map((item) => item.trim()).filter(isAlipaySimpleSelector);
    if (simpleSelectors.length) {
      output += simpleSelectors.join(',\n') + ' {\n' + sanitizeDeclarations(block) + '}\n\n';
    }
    i = j;
  }
  return output;
}

function sanitizeDeclarations(block) {
  const dropProps = /^(--|gap$|grid-|backdrop-filter$|background-clip$|-webkit-|animation$|transition$|content$|inset$|filter$|text-transform$|pointer-events$|object-fit$|letter-spacing$|word-break$|font$|vertical-align$|overflow-x$)/;
  return block
    .split(';')
    .map((decl) => decl.trim())
    .filter(Boolean)
    .map((decl) => {
      const colon = decl.indexOf(':');
      if (colon < 0) return '';
      const prop = decl.slice(0, colon).trim();
      let value = decl.slice(colon + 1).trim();
      if (dropProps.test(prop)) return '';
      if (prop === 'display' && value === 'grid') value = 'flex';
      if (prop === 'display' && value === 'inline-flex') value = 'flex';
      if (prop === 'display' && (value === 'block' || value === '-webkit-box')) return '';
      if (prop === 'flex' && /\s/.test(value)) return value.startsWith('1 ') ? '  flex: 1' : '';
      if (prop === 'box-shadow' && value.replace(/\s*!important$/, '').trim() === 'none') return '';
      if (value === 'inherit' || value === 'normal') return '';
      if (prop === 'width' && value === 'fit-content') return '';
      if (/radial-gradient|inset /.test(value)) return '';
      if ((prop === 'border' || prop.endsWith('-border')) && value === '0') value = 'none';
      value = value.replace(/calc\(\s*([^()+]+?)\s*\+\s*env\([^)]+\)\s*\)/g, '$1');
      value = value.replace(/calc\(\s*([^()+]+?)\s*\+\s*0rpx\s*\)/g, '$1');
      value = value.replace(/env\([^)]+\)/g, '0rpx');
      return '  ' + prop + ': ' + value;
    })
    .filter(Boolean)
    .join(';\n') + (block.trim() ? ';\n' : '');
}

function layoutCompatFor(rel) {
  const normalized = rel.replace(/\\/g, '/');
  if (normalized === 'pages/index/index.wxss') {
    return `
/* Alipay layout compatibility: WX grid/gap fallback */
.search-row {
  display: flex;
  align-items: center;
}
.search-box {
  flex: 1;
}
.custom-size-btn {
  width: 138rpx;
  flex-shrink: 0;
  margin-left: 18rpx;
}
.section-title-left {
  margin-right: 12rpx;
}
.core-visual-id {
  border-radius: 20rpx;
  background: linear-gradient(180deg, #8fb6ff 0%, #5d7df2 100%);
}
.core-visual-wm {
  border-radius: 18rpx;
  border: 4rpx solid #fff4e3;
  background: linear-gradient(135deg, #ffd58d 0%, #ff9f45 100%);
}
.core-visual-zip {
  width: 148rpx;
  height: 104rpx;
  border-radius: 18rpx;
  background: #ffffff;
  box-shadow: 16rpx -12rpx 0 rgba(255, 255, 255, 0.45);
}
.core-id-head {
  position: absolute;
  left: 33rpx;
  top: 22rpx;
  width: 54rpx;
  height: 54rpx;
  border-radius: 50%;
  background: #f6dfcf;
}
.core-id-body {
  position: absolute;
  left: 24rpx;
  bottom: 16rpx;
  width: 72rpx;
  height: 38rpx;
  border-radius: 36rpx 36rpx 16rpx 16rpx;
  background: #ffffff;
}
.core-wm-paper {
  position: absolute;
  left: 20rpx;
  bottom: 22rpx;
  width: 80rpx;
  height: 44rpx;
  border-radius: 16rpx;
  background: rgba(255, 255, 255, 0.58);
}
.core-wm-brush {
  position: absolute;
  right: -12rpx;
  bottom: -8rpx;
  width: 50rpx;
  height: 78rpx;
  border-radius: 28rpx;
  background: #ff7d27;
  transform: rotate(42deg);
}
.core-zip-box {
  position: absolute;
  left: 24rpx;
  bottom: 22rpx;
  width: 76rpx;
  height: 44rpx;
  border-radius: 12rpx;
  background: linear-gradient(135deg, #8ce0af 0%, #42c685 100%);
}
.core-zip-badge {
  position: absolute;
  right: -18rpx;
  bottom: -18rpx;
  width: 78rpx;
  height: 78rpx;
  border-radius: 50%;
  background: #52c98b;
}
.hot-icon-head {
  position: absolute;
  left: 11rpx;
  top: 2rpx;
  width: 20rpx;
  height: 20rpx;
  border-radius: 50%;
}
.hot-icon-body {
  position: absolute;
  left: 4rpx;
  bottom: 0;
  width: 34rpx;
  height: 22rpx;
  border-radius: 22rpx 22rpx 8rpx 8rpx;
}
.hot-doc-paper {
  position: absolute;
  width: 30rpx;
  height: 36rpx;
  left: 6rpx;
  top: 3rpx;
  border-radius: 6rpx;
  background: #f2a33a;
}
.hot-doc-line {
  position: absolute;
  width: 18rpx;
  height: 4rpx;
  left: 12rpx;
  bottom: 10rpx;
  border-radius: 2rpx;
  background: #ffffff;
  box-shadow: 0 -10rpx 0 #ffffff;
}
.tool-icon-edit { background: #fff1e6; }
.tool-icon-palette { background: #fff0f4; }
.tool-icon-ruler { background: #f1f4fb; }
.tool-icon-convert { background: #e7f8ff; }
.tool-icon-color { background: #fff3df; }
.tool-icon-more { background: #f1f3f8; }
.tool-glyph-edit,
.tool-glyph-palette,
.tool-glyph-ruler,
.tool-glyph-convert,
.tool-glyph-color,
.tool-glyph-more {
  position: absolute;
}
.tool-glyph-edit {
  left: 14rpx;
  top: 14rpx;
  width: 24rpx;
  height: 24rpx;
  border-radius: 6rpx;
  background: #ff7c34;
  transform: rotate(-32deg);
}
.tool-glyph-palette {
  left: 14rpx;
  top: 14rpx;
  width: 24rpx;
  height: 24rpx;
  border-radius: 50%;
  background: #f06aa1;
}
.tool-glyph-ruler {
  left: 14rpx;
  top: 14rpx;
  width: 24rpx;
  height: 24rpx;
  border-radius: 6rpx;
  background: #9099aa;
  transform: rotate(45deg);
}
.tool-glyph-convert {
  left: 14rpx;
  top: 14rpx;
  width: 24rpx;
  height: 24rpx;
  border-radius: 6rpx;
  background: #21a8e5;
}
.tool-glyph-color {
  left: 14rpx;
  top: 14rpx;
  width: 24rpx;
  height: 24rpx;
  border-radius: 50%;
  background: #f0b52f;
}
.tool-glyph-more {
  left: 12rpx;
  top: 12rpx;
  width: 8rpx;
  height: 8rpx;
  background: #98a2b3;
  box-shadow: 18rpx 0 0 #98a2b3, 0 18rpx 0 #98a2b3, 18rpx 18rpx 0 #98a2b3;
}
.core-grid {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
}
.core-card {
  width: 49%;
  flex-shrink: 0;
  margin-bottom: 18rpx;
}
.core-card-wide {
  width: 100%;
}
.hot-scroll {
  display: flex;
  flex-direction: row;
}
.hot-card {
  flex-shrink: 0;
}
.tools-grid {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
}
.tool-card {
  width: 31.5%;
  flex-shrink: 0;
  margin-bottom: 18rpx;
}
`;
  }
  if (normalized === 'pages/tools/tools.wxss') {
    return `
/* Alipay layout compatibility: WX grid/gap fallback */
.tools-grid {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
}
.tool-card {
  width: 48%;
  flex-shrink: 0;
  margin-bottom: 24rpx;
}
`;
  }
  if (normalized === 'pages/specs/specs.wxss') {
    return `
/* Alipay layout compatibility: WX grid/gap fallback */
.search-row {
  display: flex;
  align-items: center;
}
.search-input-wrap {
  flex: 1;
}
.custom-btn {
  width: 112rpx;
  flex-shrink: 0;
  margin-left: 16rpx;
}
.spec-grid {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
}
.spec-card {
  width: 48.6%;
  flex-shrink: 0;
  margin-bottom: 18rpx;
}
`;
  }
  if (normalized === 'pages/generate/generate.wxss') {
    return `
/* Alipay layout compatibility: WX grid/gap fallback */
.mode-tabs,
.bg-grid,
.result-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
}
.mode-tab,
.result-action-btn {
  width: 48.5%;
  flex-shrink: 0;
  margin-bottom: 14rpx;
}
.bg-option {
  width: 23%;
  flex-shrink: 0;
  margin-bottom: 16rpx;
}
`;
  }
  if (normalized === 'pages/capture-guide/capture-guide.wxss') {
    return `
/* Alipay layout compatibility: WX grid/gap fallback */
.tips-card,
.spec-card,
.action-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
}
.action-btn {
  width: 48.5%;
  flex-shrink: 0;
}
`;
  }
  if (normalized === 'pages/id-camera/id-camera.wxss') {
    return `
/* Alipay layout compatibility: WX grid/gap fallback */
.confirm-actions {
  display: flex;
  justify-content: space-between;
}
.confirm-btn {
  width: 48.5%;
  flex-shrink: 0;
}
`;
  }
  return '';
}

function convertStyle(input, rel) {
  let text = input.replace(/\.wx-/g, '.a-');
  Object.keys(CSS_VARS).forEach((key) => {
    const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    text = text.replace(new RegExp('var\\(' + escaped + '\\)', 'g'), CSS_VARS[key]);
  });
  text = text.replace(/hsl\([^)]*var\([^)]*\)[^)]*\)/g, '#667eea');
  text = text.replace(/env\([^)]+\)/g, '0rpx');
  return stripUnsupportedCssBlocks(text) + layoutCompatFor(rel || '');
}

function enhanceAlipayHomeMarkup(text, rel) {
  const normalized = rel.replace(/\\/g, '/');
  if (normalized !== 'pages/index/index.wxml') return text;
  return text
    .replace(/<text class="core-title">([\s\S]*?)<\/text>/g, '<view class="core-title-line"><text class="core-title">$1</text></view>')
    .replace(/<text class="core-desc">([\s\S]*?)<\/text>/g, '<view class="core-desc-line"><text class="core-desc">$1</text></view>')
    .replace(/<text class="hot-name">([\s\S]*?)<\/text>/g, '<view class="hot-name-line"><text class="hot-name">$1</text></view>')
    .replace(/<text class="hot-size">([\s\S]*?)<\/text>/g, '<view class="hot-size-line"><text class="hot-size">$1</text></view>')
    .replace(/<text class="tool-name">([\s\S]*?)<\/text>/g, '<view class="tool-name-line"><text class="tool-name">$1</text></view>')
    .replace(
      '<view class="core-visual-inner {{item.icon}}"></view>',
      [
        '<view class="core-visual-inner core-visual-{{item.icon}}">',
        '          <view a:if="{{item.icon === \'id\'}}" class="core-id-head"></view>',
        '          <view a:if="{{item.icon === \'id\'}}" class="core-id-body"></view>',
        '          <view a:if="{{item.icon === \'wm\'}}" class="core-wm-paper"></view>',
        '          <view a:if="{{item.icon === \'wm\'}}" class="core-wm-brush"></view>',
        '          <view a:if="{{item.icon === \'zip\'}}" class="core-zip-box"></view>',
        '          <view a:if="{{item.icon === \'zip\'}}" class="core-zip-badge"></view>',
        '        </view>'
      ].join('\n')
    )
    .replace(
      '<view class="hot-thumb-icon {{item.icon}}"></view>',
      [
        '<view class="hot-thumb-icon hot-thumb-{{item.icon}}">',
        '          <view a:if="{{item.icon !== \'doc\'}}" class="hot-icon-head" style="background: {{item.iconColor}};"></view>',
        '          <view a:if="{{item.icon !== \'doc\'}}" class="hot-icon-body" style="background: {{item.iconColor}};"></view>',
        '          <view a:if="{{item.icon === \'doc\'}}" class="hot-doc-paper"></view>',
        '          <view a:if="{{item.icon === \'doc\'}}" class="hot-doc-line"></view>',
        '        </view>'
      ].join('\n')
    )
    .replace(
      '<view class="tool-icon {{item.icon}}"></view>',
      '<view class="tool-icon tool-icon-{{item.icon}}"><view class="tool-glyph-{{item.icon}}"></view></view>'
    );
}

function convertPageJson(input) {
  const json = JSON.parse(input);
  const next = {};
  Object.keys(json).forEach((key) => {
    if (key === 'navigationBarTitleText') next.defaultTitle = json[key];
    else if (key === 'navigationBarBackgroundColor') next.titleBarColor = json[key];
    else if (key === 'navigationBarTextStyle') next.titleBarColor = next.titleBarColor || '#ffffff';
    else next[key] = json[key];
  });
  return JSON.stringify(next, null, 2) + '\n';
}

function convertAppJson() {
  const source = readJson(path.join(ROOT, 'app.json'));
  const window = source.window || {};
  const next = {
    pages: source.pages || [],
    window: {
      defaultTitle: window.navigationBarTitleText || '证件照生成器',
      titleBarColor: window.navigationBarBackgroundColor || '#ffffff',
      backgroundColor: window.backgroundColor || '#f5f7fa',
    },
    tabBar: source.tabBar
      ? Object.assign({}, source.tabBar, {
          textColor: source.tabBar.color || source.tabBar.textColor || '#999',
          items: (source.tabBar.list || source.tabBar.items || []).map((item) => ({
            pagePath: item.pagePath,
            name: item.name || item.text || '',
            icon: item.icon || item.iconPath || '',
            activeIcon: item.activeIcon || item.selectedIconPath || ''
          }))
        })
      : undefined,
    networkTimeout: source.networkTimeout || undefined,
  };
  if (next.tabBar) {
    delete next.tabBar.color;
    delete next.tabBar.list;
  }
  Object.keys(next).forEach((key) => next[key] === undefined && delete next[key]);
  return JSON.stringify(next, null, 2) + '\n';
}

function compatPathFor(file) {
  const rel = path.relative(path.dirname(file), path.join(OUT, 'utils', 'platform', 'alipayWxCompat.js'));
  return rel.replace(/\\/g, '/').replace(/^(?!\.)/, './');
}

function needsWxCompat(text) {
  return /\bwx\./.test(text) && !/\b(var|let|const)\s+wx\b/.test(text);
}

function convertJs(input, dest) {
  let text = input;
  if (needsWxCompat(text)) {
    text = "var wx = require('" + compatPathFor(dest) + "');\n" + text;
  }

  // Alipay must not ask the WeChat login endpoint to exchange an Alipay authCode.
  if (dest.endsWith(path.join('utils', 'authService.js'))) {
    text = text.replace(
      /url:\s*apiConfig\.API_BASE_URL\s*\+\s*'\/api\/auth\/login'/g,
      "url: (apiConfig.getApiBaseUrl ? apiConfig.getApiBaseUrl() : apiConfig.API_BASE_URL) + '/api/auth/alipay/login'"
    );
    text = text.replace(/'微信用户'/g, "'支付宝用户'");
  }
  if (dest.endsWith(path.join('pages', 'login', 'login.js'))) {
    text = text.replace(/微信昵称/g, '支付宝昵称');
    text = text.replace(/微信用户/g, '支付宝用户');
    text = text.replace(
      /chooseAvatar\(e\)\s*\{[\s\S]*?\n  \},\n\n  onNicknameInput/,
      `chooseAvatar(e) {
    var that = this;
    wx.chooseImage({
      count: 1,
      sourceType: ['album'],
      success: function(res) {
        var paths = res.tempFilePaths || res.apFilePaths || [];
        var avatarUrl = paths[0] || '';
        if (!avatarUrl) return;
        var userInfo = Object.assign({}, that.data.userInfo || {}, {
          avatarUrl: avatarUrl
        });
        that.setData({ userInfo: userInfo });
      },
      fail: function() {
        wx.showToast({ title: '头像选择已取消', icon: 'none' });
      }
    });
  },

  onNicknameInput`
    );
  }
  if (dest.endsWith(path.join('pages', 'index', 'index.js'))) {
    text = text
      .replace("{ id: 'yicun', name: '一寸', size: '25×35mm', icon: 'person', thumbBg: '#eef3ff' }", "{ id: 'yicun', name: '一寸', size: '25×35mm', icon: 'person', iconColor: '#2d7cf2', thumbBg: '#eef3ff' }")
      .replace("{ id: 'ercun', name: '二寸', size: '35×49mm', icon: 'person2', thumbBg: '#fff4e7' }", "{ id: 'ercun', name: '二寸', size: '35×49mm', icon: 'person2', iconColor: '#f6a52c', thumbBg: '#fff4e7' }")
      .replace("{ id: 'dayicun', name: '大一寸', size: '33×48mm', icon: 'person3', thumbBg: '#ecfbf2' }", "{ id: 'dayicun', name: '大一寸', size: '33×48mm', icon: 'person3', iconColor: '#27b673', thumbBg: '#ecfbf2' }")
      .replace("{ id: 'xiaoyicun', name: '小一寸', size: '22×32mm', icon: 'person4', thumbBg: '#fff7df' }", "{ id: 'xiaoyicun', name: '小一寸', size: '22×32mm', icon: 'person4', iconColor: '#f6a52c', thumbBg: '#fff7df' }")
      .replace("{ id: 'jianli', name: '简历照片', size: '25×35mm', icon: 'doc', thumbBg: '#edf5ff' }", "{ id: 'jianli', name: '简历照片', size: '25×35mm', icon: 'doc', iconColor: '#f2a33a', thumbBg: '#edf5ff' }");
  }
  if (dest.endsWith(path.join('pages', 'profile', 'profile.js'))) {
    text = text.replace(/微信用户/g, '支付宝用户');
    text = text.replace(/小程序反馈留言/g, '支付宝小程序反馈留言');
  }
  return text;
}

function copyConvertedFile(sourceFile, destFile, counters) {
  const ext = path.extname(sourceFile);
  const raw = fs.readFileSync(sourceFile, ext === '.png' || ext === '.jpg' || ext === '.jpeg' ? undefined : 'utf8');
  if (ext === '.wxml') {
    writeFile(destFile.replace(/\.wxml$/, '.axml'), convertMarkup(raw, path.relative(ROOT, sourceFile)));
    counters.axml += 1;
  } else if (ext === '.wxss') {
    writeFile(destFile.replace(/\.wxss$/, '.acss'), convertStyle(raw, path.relative(ROOT, sourceFile)));
    counters.acss += 1;
  } else if (ext === '.json' && sourceFile.includes(path.sep + 'pages' + path.sep)) {
    writeFile(destFile, convertPageJson(raw));
    counters.json += 1;
  } else if (ext === '.js') {
    writeFile(destFile, convertJs(raw, destFile));
    counters.js += 1;
  } else {
    fs.mkdirSync(path.dirname(destFile), { recursive: true });
    fs.copyFileSync(sourceFile, destFile);
    counters.assets += 1;
  }
}

function copyRoots() {
  const counters = { axml: 0, acss: 0, js: 0, json: 0, assets: 0 };
  for (const rootName of COPY_ROOTS) {
    const sourceRoot = path.join(ROOT, rootName);
    for (const sourceFile of listFiles(sourceRoot)) {
      const rel = path.relative(ROOT, sourceFile);
      copyConvertedFile(sourceFile, path.join(OUT, rel), counters);
    }
  }
  return counters;
}

function writeAdapters() {
  writeFile(path.join(OUT, 'utils', 'platform', 'alipay.js'), `
function hasMy() {
  return typeof my !== 'undefined' && my;
}

function callMy(name, options, fallback) {
  if (hasMy() && typeof my[name] === 'function') return my[name](options || {});
  if (typeof fallback === 'function') return fallback(options || {});
  if (options && typeof options.fail === 'function') options.fail({ errMsg: name + ':fail unavailable' });
  return null;
}

module.exports = {
  isAlipay: true,
  hasMy: hasMy,
  callMy: callMy
};
`.trimStart());

  writeFile(path.join(OUT, 'utils', 'platform', 'index.js'), `
module.exports = require('./alipay.js');
`.trimStart());

  writeFile(path.join(OUT, 'utils', 'platform', 'alipayWxCompat.js'), `
var platform = require('./alipay.js');

function normalizeToastOptions(options) {
  options = options || {};
  return Object.assign({}, options, {
    content: options.content || options.title || '',
    type: options.type || (options.icon === 'success' ? 'success' : 'none')
  });
}

function request(options) {
  options = options || {};
  var next = Object.assign({}, options, {
    headers: options.header || options.headers || {},
    method: options.method || 'GET'
  });
  return platform.callMy('request', next);
}

function uploadFile(options) {
  options = options || {};
  var next = Object.assign({}, options, {
    fileName: options.fileName || options.name || 'file',
    fileType: options.fileType || 'image',
    headers: options.header || options.headers || {}
  });
  return platform.callMy('uploadFile', next);
}

function downloadFile(options) {
  options = options || {};
  var success = options.success;
  var next = Object.assign({}, options, {
    success: function(res) {
      if (res && res.apFilePath && !res.tempFilePath) res.tempFilePath = res.apFilePath;
      if (typeof success === 'function') success(res);
    }
  });
  return platform.callMy('downloadFile', next);
}

function chooseMedia(options) {
  options = options || {};
  return platform.callMy('chooseImage', {
    count: options.count || 1,
    sourceType: options.sourceType || ['album', 'camera'],
    success: function(res) {
      var paths = res.apFilePaths || res.tempFilePaths || [];
      var files = paths.map(function(p) { return { tempFilePath: p, path: p, size: 0 }; });
      if (typeof options.success === 'function') {
        options.success({ tempFiles: files, type: 'image' });
      }
    },
    fail: options.fail,
    complete: options.complete
  });
}

function login(options) {
  options = options || {};
  return platform.callMy('getAuthCode', {
    scopes: 'auth_base',
    success: function(res) {
      var code = (res && (res.authCode || res.auth_code)) || '';
      if (typeof options.success === 'function') options.success({ code: code, authCode: code, platform: 'alipay' });
    },
    fail: options.fail,
    complete: options.complete
  });
}

function setNavigationBarTitle(options) {
  options = options || {};
  return platform.callMy('setNavigationBar', { title: options.title || '', success: options.success, fail: options.fail, complete: options.complete });
}

function getAccountInfoSync() {
  if (platform.hasMy() && typeof my.getAccountInfoSync === 'function') return my.getAccountInfoSync();
  return { miniProgram: { appId: '', envVersion: 'develop' } };
}

module.exports = {
  request: request,
  uploadFile: uploadFile,
  downloadFile: downloadFile,
  chooseMedia: chooseMedia,
  chooseImage: function(options) { return platform.callMy('chooseImage', options); },
  login: login,
  getAuthCode: function(options) { return platform.callMy('getAuthCode', options); },
  showToast: function(options) { return platform.callMy('showToast', normalizeToastOptions(options)); },
  showLoading: function(options) { return platform.callMy('showLoading', { content: (options && (options.content || options.title)) || '' }); },
  hideLoading: function(options) { return platform.callMy('hideLoading', options); },
  showModal: function(options) { return platform.callMy('confirm', options); },
  showActionSheet: function(options) { return platform.callMy('showActionSheet', { items: options.itemList || options.items || [], success: options.success, fail: options.fail }); },
  navigateTo: function(options) { return platform.callMy('navigateTo', options); },
  navigateBack: function(options) { return platform.callMy('navigateBack', options); },
  switchTab: function(options) { return platform.callMy('switchTab', options); },
  previewImage: function(options) { return platform.callMy('previewImage', options); },
  saveImageToPhotosAlbum: function(options) { return platform.callMy('saveImageToPhotosAlbum', options); },
  setNavigationBarTitle: setNavigationBarTitle,
  showShareMenu: function(options) { return platform.callMy('showSharePanel', options, function(opts) { if (opts.success) opts.success({}); }); },
  getStorageSync: function(key) { try { return platform.hasMy() && my.getStorageSync ? my.getStorageSync({ key: key }).data : ''; } catch (e) { return ''; } },
  setStorageSync: function(key, data) { try { return platform.hasMy() && my.setStorageSync ? my.setStorageSync({ key: key, data: data }) : null; } catch (e) { return null; } },
  removeStorageSync: function(key) { try { return platform.hasMy() && my.removeStorageSync ? my.removeStorageSync({ key: key }) : null; } catch (e) { return null; } },
  getSystemInfoSync: function() { return platform.hasMy() && my.getSystemInfoSync ? my.getSystemInfoSync() : {}; },
  getAccountInfoSync: getAccountInfoSync,
  getSetting: function(options) { return platform.callMy('getSetting', options); },
  authorize: function(options) { return platform.callMy('authorize', options); },
  openSetting: function(options) { return platform.callMy('openSetting', options); },
  createCameraContext: function() { return platform.hasMy() && my.createCameraContext ? my.createCameraContext() : null; },
  createSelectorQuery: function() { return platform.hasMy() && my.createSelectorQuery ? my.createSelectorQuery() : null; },
  createWorker: function(path) { return platform.hasMy() && my.createWorker ? my.createWorker(path) : null; },
  createOffscreenCanvas: function(options) { return platform.hasMy() && my.createOffscreenCanvas ? my.createOffscreenCanvas(options) : null; },
  createCanvasContext: function(id, owner) { return platform.hasMy() && my.createCanvasContext ? my.createCanvasContext(id, owner) : null; },
  canvasToTempFilePath: function(options) { return platform.callMy('canvasToTempFilePath', options); },
  compressImage: function(options) {
    if (platform.hasMy() && typeof my.compressImage === 'function') return my.compressImage(options);
    if (options && typeof options.success === 'function') options.success({ tempFilePath: options.src });
    return null;
  },
  getImageInfo: function(options) { return platform.callMy('getImageInfo', options); },
  getFileInfo: function(options) { return platform.callMy('getFileInfo', options); },
  getFileSystemManager: function() { return platform.hasMy() && my.getFileSystemManager ? my.getFileSystemManager() : null; },
  nextTick: function(callback) { return setTimeout(callback, 0); }
};
`.trimStart());
}

function writeRootFiles() {
  writeFile(path.join(OUT, 'app.json'), convertAppJson());
  writeFile(path.join(OUT, 'app.acss'), convertStyle(fs.readFileSync(path.join(ROOT, 'app.wxss'), 'utf8'), 'app.wxss'));
  writeFile(path.join(OUT, 'app.js'), convertJs(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8'), path.join(OUT, 'app.js')));
  writeFile(path.join(OUT, 'mini.project.json'), JSON.stringify({
    format: 2,
    compileOptions: {
      component2: true
    },
    miniprogramRoot: '.',
    compileType: 'mini',
    appid: ALIPAY_APP_ID,
    projectname: '证件照生成器-支付宝',
    axmlStrictCheck: true,
    uploadExclude: [
      'server/**',
      'reports/**',
      'logs/**',
      'tools/**',
      '.agents/**',
      'backups/**',
      'third_party/**',
      'mockups/**',
      '*.zip'
    ]
  }, null, 2) + '\n');
}

function auditSource() {
  const wxFiles = listFiles(ROOT).filter((file) => {
    const rel = path.relative(ROOT, file);
    if (!rel || rel.startsWith('alipay' + path.sep)) return false;
    if (EXCLUDED_DIRS.has(rel.split(path.sep)[0])) return false;
    return /\.(js|wxml|wxss|json)$/.test(file);
  });
  const wxApiRefs = [];
  const markupRefs = [];
  for (const file of wxFiles) {
    const text = fs.readFileSync(file, 'utf8');
    const rel = path.relative(ROOT, file).replace(/\\/g, '/');
    const apiMatches = text.match(/\bwx\.[A-Za-z0-9_]+/g) || [];
    if (apiMatches.length) wxApiRefs.push({ file: rel, count: apiMatches.length, apis: Array.from(new Set(apiMatches)).sort() });
    const markupMatches = text.match(/\bwx:[A-Za-z0-9_-]+|\bbind[a-z]+|\bcatch[a-z]+/g) || [];
    if (markupMatches.length) markupRefs.push({ file: rel, count: markupMatches.length, attrs: Array.from(new Set(markupMatches)).sort() });
  }
  return { wxApiRefs, markupRefs };
}

function writeReports(counters, audit) {
  fs.mkdirSync(REPORT_DIR, { recursive: true });
  const appJson = path.join(OUT, 'app.json');
  const miniProject = path.join(OUT, 'mini.project.json');
  const report = {
    generatedAt: new Date().toISOString(),
    alipayProjectPath: OUT,
    alipayAppIdConfigured: !!ALIPAY_APP_ID,
    counters,
    sourceAudit: {
      wxApiFiles: audit.wxApiRefs.length,
      markupFiles: audit.markupRefs.length,
      wxApiRefCount: audit.wxApiRefs.reduce((sum, item) => sum + item.count, 0),
      markupRefCount: audit.markupRefs.reduce((sum, item) => sum + item.count, 0)
    },
    generatedHashes: {
      appJson: sha(appJson),
      miniProjectJson: sha(miniProject)
    }
  };
  writeFile(path.join(REPORT_DIR, 'migration-manifest.json'), JSON.stringify(report, null, 2) + '\n');
  writeFile(path.join(REPORT_DIR, 'wx-api-inventory.json'), JSON.stringify(audit.wxApiRefs, null, 2) + '\n');
  writeFile(path.join(REPORT_DIR, 'markup-inventory.json'), JSON.stringify(audit.markupRefs, null, 2) + '\n');
  writeFile(path.join(REPORT_DIR, 'audit.md'), [
    '# Alipay migration audit',
    '',
    '- CLIENT_ALREADY_DOES: image compression, OffscreenCanvas composition, ROI/mask serialization, edge background composition when available.',
    '- SERVER_DOES: content safety, ID-photo matting/alignment, Hivision/BiRefNet fallback, LaMa/IOPaint inpainting, storage lifecycle.',
    '- DUPLICATED_COMPUTE: page-level wx API access and platform routing were WeChat-coupled; generated Alipay project now routes through a platform compatibility layer.',
    '- CAN_MOVE_TO_CLIENT: UI DSL, canvas composition, image selection/camera calls, upload/download wrappers.',
    '- MUST_STAY_CLOUD: model inference, server-owned content safety, user isolation, 24h asset lifecycle, billing/auth secrets.',
    '',
    `- ALIPAY_PROJECT_PATH: ${OUT}`,
    `- wxApiFiles: ${audit.wxApiRefs.length}`,
    `- markupFiles: ${audit.markupRefs.length}`,
    `- generatedAxml: ${counters.axml}`,
    `- generatedAcss: ${counters.acss}`,
    `- alipayAppIdConfigured: ${!!ALIPAY_APP_ID}`,
    ''
  ].join('\n'));
}

function main() {
  if (process.env.ALIPAY_MIGRATION_OVERLAY !== '1') {
    cleanOutputDir();
  } else {
    fs.mkdirSync(OUT, { recursive: true });
  }
  const audit = auditSource();
  writeRootFiles();
  const counters = copyRoots();
  writeAdapters();
  writeReports(counters, audit);
  console.log(JSON.stringify({
    success: true,
    alipayProjectPath: OUT,
    counters,
    alipayAppIdConfigured: !!ALIPAY_APP_ID
  }, null, 2));
}

main();
