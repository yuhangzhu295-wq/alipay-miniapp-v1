const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const childProcess = require('child_process');

const ROOT = path.resolve(__dirname, '..', '..');
const ALIPAY_ROOT = path.join(ROOT, 'alipay');
const REPORT_DIR = path.join(ROOT, 'reports', 'alipay-migration');

function listFiles(dir) {
  const result = [];
  if (!fs.existsSync(dir)) return result;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) result.push(...listFiles(full));
    else result.push(full);
  }
  return result;
}

function read(file) {
  return fs.readFileSync(file, 'utf8');
}

function write(file, content) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, content);
}

function rel(file) {
  return path.relative(ROOT, file).replace(/\\/g, '/');
}

function shaGit(ref) {
  try {
    const args = ref === '--abbrev-ref HEAD' ? ['rev-parse', '--abbrev-ref', 'HEAD'] : ['rev-parse', ref];
    return childProcess.execFileSync('git', args, { cwd: ROOT, encoding: 'utf8' }).trim();
  } catch (e) {
    return '';
  }
}

function check(name, passed, details, checks) {
  checks.push({ name, passed: !!passed, details: details || {} });
}

function fileHash(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

function scanSecrets(files) {
  const markers = [
    /WECHAT_APP_SECRET\s*[:=]\s*['"][^'"]+/,
    /WECHAT_SECRET\s*[:=]\s*['"][^'"]+/,
    /ALIPAY_APP_PRIVATE_KEY\s*[:=]\s*['"][^'"]+/,
    /ALIPAY_PRIVATE_KEY\s*[:=]\s*['"][^'"]+/,
    /EncodingAESKey\s*[:=]\s*['"][^'"]+/,
    /CALLBACK_TOKEN\s*[:=]\s*['"][^'"]+/
  ];
  const hits = [];
  for (const file of files) {
    if (!/\.(js|json|axml|acss|md)$/.test(file)) continue;
    const text = read(file);
    for (const marker of markers) {
      if (marker.test(text)) hits.push(rel(file));
    }
  }
  return Array.from(new Set(hits)).sort();
}

function main() {
  const checks = [];
  const files = listFiles(ALIPAY_ROOT);
  const appJsonPath = path.join(ALIPAY_ROOT, 'app.json');
  const miniProjectPath = path.join(ALIPAY_ROOT, 'mini.project.json');
  const appJson = fs.existsSync(appJsonPath) ? JSON.parse(read(appJsonPath)) : {};
  const miniProject = fs.existsSync(miniProjectPath) ? JSON.parse(read(miniProjectPath)) : {};
  const configuredAppId = miniProject.appid || (miniProject.unknownConfig && miniProject.unknownConfig.appid) || '';

  check('alipay project exists', fs.existsSync(ALIPAY_ROOT), { path: ALIPAY_ROOT }, checks);
  check('app.json exists and parses', !!appJson.pages, { path: rel(appJsonPath) }, checks);
  check('mini.project.json exists and parses', !!miniProject.miniprogramRoot, { path: rel(miniProjectPath) }, checks);
  check('uses Alipay page templates', files.some((f) => f.endsWith('.axml')), {}, checks);
  check('uses Alipay global stylesheet', fs.existsSync(path.join(ALIPAY_ROOT, 'app.acss')), {}, checks);
  check('no WeChat template files in package', files.filter((f) => f.endsWith('.wxml') || f.endsWith('.wxss')).length === 0, {
    offenders: files.filter((f) => f.endsWith('.wxml') || f.endsWith('.wxss')).map(rel)
  }, checks);

  const textFiles = files.filter((f) => /\.(js|json|axml|acss)$/.test(f));
  const joined = textFiles.map((f) => read(f)).join('\n');
  check('no polluted snapshot builder require', !/require\(\s*['"]C:[\\/]|C:\\snapshot|C:\/snapshot|@ali\/mini-program-builder|builder\.js/.test(joined), {}, checks);
  check('no WeChat wx: directives remain', !/\bwx:[a-z-]+/.test(joined), {}, checks);
  check('platform compat layer exists', fs.existsSync(path.join(ALIPAY_ROOT, 'utils', 'platform', 'alipayWxCompat.js')), {}, checks);

  const wxRefFiles = textFiles.filter((f) => /\bwx\./.test(read(f)) && !f.endsWith('alipayWxCompat.js'));
  const unshimmed = wxRefFiles.filter((f) => !/alipayWxCompat\.js/.test(read(f)));
  check('wx API references are shimmed through Alipay compat layer', unshimmed.length === 0, { unshimmed: unshimmed.map(rel) }, checks);

  const forbiddenRoots = ['server/', 'reports/', 'logs/', 'tools/', '.agents/', 'third_party/', 'backups/', 'mockups/'];
  const forbiddenPackaged = files.map(rel).filter((name) => forbiddenRoots.some((prefix) => name.startsWith('alipay/' + prefix)));
  check('no server reports caches or agent files packaged', forbiddenPackaged.length === 0, { forbiddenPackaged }, checks);

  const pages = appJson.pages || [];
  const missingPageFiles = [];
  for (const page of pages) {
    for (const ext of ['js', 'json', 'axml', 'acss']) {
      const file = path.join(ALIPAY_ROOT, page + '.' + ext);
      if (!fs.existsSync(file)) missingPageFiles.push(page + '.' + ext);
    }
  }
  check('all app.json pages have Alipay files', missingPageFiles.length === 0, { missingPageFiles }, checks);

  const secretHits = scanSecrets(files);
  check('no server secrets in generated Alipay package', secretHits.length === 0, { secretHits }, checks);

  const packageBytes = files.reduce((sum, file) => sum + fs.statSync(file).size, 0);
  check('generated package below 4MB source limit', packageBytes < 4 * 1024 * 1024, { packageBytes }, checks);
  check('Alipay AppID configured for upload', !!configuredAppId, { appidConfigured: !!configuredAppId }, checks);

  const result = {
    generatedAt: new Date().toISOString(),
    allPassed: checks.every((item) => item.passed),
    packageBytes,
    alipayProjectPath: ALIPAY_ROOT,
    branch: shaGit('--abbrev-ref HEAD'),
    branchSha: shaGit('HEAD'),
    baseMasterSha: shaGit('origin/master'),
    appJsonHash: fs.existsSync(appJsonPath) ? fileHash(appJsonPath) : '',
    miniProjectHash: fs.existsSync(miniProjectPath) ? fileHash(miniProjectPath) : '',
    checks
  };

  write(path.join(REPORT_DIR, 'static-verify.json'), JSON.stringify(result, null, 2) + '\n');
  write(path.join(REPORT_DIR, 'static-verify.md'), [
    '# Alipay static verification',
    '',
    `- allPassed: ${result.allPassed}`,
    `- packageBytes: ${packageBytes}`,
    `- branch: ${result.branch}`,
    `- branchSha: ${result.branchSha}`,
    `- baseMasterSha: ${result.baseMasterSha}`,
    '',
    ...checks.map((item) => `- ${item.passed ? 'PASS' : 'FAIL'} ${item.name}`)
  ].join('\n') + '\n');

  console.log(JSON.stringify(result, null, 2));
  if (!result.allPassed) process.exitCode = 1;
}

main();
