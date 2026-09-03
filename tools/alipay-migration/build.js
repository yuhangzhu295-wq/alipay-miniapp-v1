const fs = require('fs');
const path = require('path');
const childProcess = require('child_process');

const ROOT = path.resolve(__dirname, '..', '..');
const ALIPAY_ROOT = path.join(ROOT, 'alipay');
const REPORT_DIR = path.join(ROOT, 'reports', 'alipay-migration');
const DEFAULT_BUILDER = path.join(
  process.env.LOCALAPPDATA || '',
  'Programs',
  '小程序开发者工具',
  'resources',
  'app',
  'kits',
  'mini-pkg-builder.exe'
);
const BUILDER = process.env.ALIPAY_MINI_BUILDER || DEFAULT_BUILDER;
const OUTPUT = path.join(REPORT_DIR, 'builder-dist');

function write(file, content) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, content);
}

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

function main() {
  if (!fs.existsSync(BUILDER)) {
    throw new Error('Alipay mini-pkg-builder not found: ' + BUILDER);
  }
  const args = [
    '--project', ALIPAY_ROOT,
    '--input', ALIPAY_ROOT,
    '--output', OUTPUT,
    '--project-config-path', path.join(ALIPAY_ROOT, 'mini.project.json'),
    '--target', 'native',
    '--env', 'development',
    '--no-vuerender',
    '--zrender',
  ];
  const startedAt = Date.now();
  const result = childProcess.spawnSync(BUILDER, args, {
    cwd: ROOT,
    encoding: 'utf8',
    maxBuffer: 8 * 1024 * 1024,
  });
  const durationMs = Date.now() - startedAt;
  const stdout = result.stdout || '';
  const stderr = result.stderr || '';
  const outputFiles = listFiles(OUTPUT);
  const packageBytes = listFiles(ALIPAY_ROOT).reduce((sum, file) => sum + fs.statSync(file).size, 0);
  const warningCount = (stdout.match(/warning\[/g) || []).length + (stderr.match(/warning\[/g) || []).length;
  const report = {
    generatedAt: new Date().toISOString(),
    builder: BUILDER,
    exitCode: result.status,
    success: result.status === 0,
    warningCount,
    durationMs,
    packageBytes,
    outputFileCount: outputFiles.length,
    output: OUTPUT,
    stdoutTail: stdout.slice(-4000),
    stderrTail: stderr.slice(-4000),
  };
  write(path.join(REPORT_DIR, 'builder-verify.json'), JSON.stringify(report, null, 2) + '\n');
  write(path.join(REPORT_DIR, 'builder-verify.md'), [
    '# Alipay builder verification',
    '',
    `- success: ${report.success}`,
    `- exitCode: ${report.exitCode}`,
    `- warningCount: ${report.warningCount}`,
    `- packageBytes: ${report.packageBytes}`,
    `- durationMs: ${report.durationMs}`,
    `- output: ${report.output}`,
    ''
  ].join('\n'));
  console.log(JSON.stringify(report, null, 2));
  process.exit(result.status || 0);
}

main();
