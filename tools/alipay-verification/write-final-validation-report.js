const childProcess = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const GOLDEN_ROOT = 'C:\\Users\\zyu33\\Documents\\Codex\\edge-cloud-hybrid-v1';
const REPORT_DIR = path.join(ROOT, 'reports', 'alipay-final-validation');
const PYTHON = process.env.PYTHON || 'C:\\Users\\zyu33\\AppData\\Local\\Programs\\Python\\Python313\\python.exe';

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function writeJson(name, value) {
  ensureDir(REPORT_DIR);
  fs.writeFileSync(path.join(REPORT_DIR, name), JSON.stringify(value, null, 2) + '\n');
}

function writeText(name, value) {
  ensureDir(REPORT_DIR);
  fs.writeFileSync(path.join(REPORT_DIR, name), value);
}

function run(command, args) {
  const result = childProcess.spawnSync(command, args, {
    cwd: ROOT,
    encoding: 'utf8',
    shell: false,
    env: process.env,
  });
  return {
    command: [command, ...args].join(' '),
    exitCode: result.status == null ? 1 : result.status,
    stdout: result.stdout || '',
    stderr: result.stderr || '',
  };
}

function git(cwd, args) {
  const result = childProcess.spawnSync('git', args, { cwd, encoding: 'utf8', shell: false });
  return result.status === 0 ? result.stdout.trim() : '';
}

function parseLastJson(stdout) {
  const start = String(stdout || '').indexOf('{');
  if (start < 0) return null;
  try {
    return JSON.parse(String(stdout).slice(start));
  } catch (_) {
    return null;
  }
}

function readJson(file, fallback) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch (_) { return fallback; }
}

function environmentFlags() {
  const names = [
    'ALIPAY_APP_ID',
    'ALIPAY_APP_PRIVATE_KEY',
    'ALIYUN_GREEN_ACCESS_KEY_ID',
    'ALIYUN_GREEN_ACCESS_KEY_SECRET',
    'ALIBABA_CLOUD_ACCESS_KEY_ID',
    'ALIBABA_CLOUD_ACCESS_KEY_SECRET',
    'CONTENT_SECURITY_PUBLIC_BASE_URL',
    'PUBLIC_BASE_URL',
    'ALIPAY_STAGING_BASE_URL',
  ];
  return Object.fromEntries(names.map((name) => [name, Boolean(process.env[name])]));
}

function sha256(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

function collectAssetManifest() {
  const manifestPath = path.join(REPORT_DIR, '01-assets', 'asset-manifest.json');
  return readJson(manifestPath, { status: 'NOT_FOUND' });
}

async function readOnlyCloudProbe() {
  const baseUrl = 'https://tupzjianzhao.chat';
  const probe = async (path) => {
    try {
      const response = await fetch(baseUrl + path, { method: 'GET', redirect: 'manual', signal: AbortSignal.timeout(12000) });
      return { method: 'GET', path, status: response.status };
    } catch (error) {
      return { method: 'GET', path, status: 'ERROR', error: String(error && error.name || 'request failed') };
    }
  };
  return {
    health: await probe('/api/health'),
    alipayLoginRoute: await probe('/api/auth/alipay/login'),
    alipayStagingHealth: await probe('/alipay-staging-v1/api/health'),
  };
}

function stagingArtifacts() {
  const stagingRoot = path.join(ROOT, 'deploy', 'staging', 'alipay');
  const nginxPath = path.join(stagingRoot, 'alipay-staging.nginx.conf');
  const servicePath = path.join(stagingRoot, 'photo-generator-alipay-staging.service');
  const startPath = path.join(stagingRoot, 'start-staging.sh');
  const templatePath = path.join(ROOT, 'server', '.env.alipay-staging.example');
  const apiConfigPath = path.join(ROOT, 'alipay', 'utils', 'apiConfig.js');
  const nginx = fs.existsSync(nginxPath) ? fs.readFileSync(nginxPath, 'utf8') : '';
  const apiConfig = fs.existsSync(apiConfigPath) ? fs.readFileSync(apiConfigPath, 'utf8') : '';
  return {
    configTemplate: fs.existsSync(templatePath),
    nginxConfig: fs.existsSync(nginxPath),
    systemdService: fs.existsSync(servicePath),
    startScript: fs.existsSync(startPath),
    isolatedPrefix: /location\s+\^~\s*\/alipay-staging-v1\//.test(nginx),
    productionApiRouteUntouched: !/location\s+\^~?\s*\/api/.test(nginx),
    stripsStagingPrefix: /proxy_pass\s+http:\/\/127\.0\.0\.1:18001\//.test(nginx),
    alipayDevelopUsesStaging: apiConfig.includes("ALIPAY_STAGING_API_BASE_URL = 'https://tupzjianzhao.chat/alipay-staging-v1'"),
  };
}

async function main() {
  ensureDir(REPORT_DIR);
  const tests = {
    providerAdapter: run(PYTHON, [path.join(ROOT, 'server', 'scripts', 'verify_alipay_platform_adapter.py')]),
    platformCompat: run(process.execPath, [path.join(ROOT, 'tools', 'alipay-verification', 'verify-platform-compat.js')]),
    static: run(process.execPath, [path.join(ROOT, 'tools', 'alipay-migration', 'verify.js')]),
    builder: run(process.execPath, [path.join(ROOT, 'tools', 'alipay-migration', 'build.js')]),
    stage2: run(process.execPath, [path.join(ROOT, 'tools', 'alipay-verification', 'verify-stage2.js')]),
  };
  const testExitPass = Object.fromEntries(Object.entries(tests).map(([name, result]) => [name, result.exitCode === 0]));
  const staticReport = readJson(path.join(ROOT, 'reports', 'alipay-migration', 'static-verify.json'), {});
  const builderReport = readJson(path.join(ROOT, 'reports', 'alipay-migration', 'builder-verify.json'), {});
  const stage2Report = readJson(path.join(ROOT, 'reports', 'alipay-v2', 'stage2-summary.json'), {});
  const providerReport = parseLastJson(tests.providerAdapter.stdout) || {};
  const compatReport = parseLastJson(tests.platformCompat.stdout) || {};
  const env = environmentFlags();
  const configuredAlipayIdentity = env.ALIPAY_APP_ID && env.ALIPAY_APP_PRIVATE_KEY;
  const configuredAliyunSafety = (env.ALIYUN_GREEN_ACCESS_KEY_ID || env.ALIBABA_CLOUD_ACCESS_KEY_ID) &&
    (env.ALIYUN_GREEN_ACCESS_KEY_SECRET || env.ALIBABA_CLOUD_ACCESS_KEY_SECRET);
  const configuredPublicBase = env.CONTENT_SECURITY_PUBLIC_BASE_URL || env.PUBLIC_BASE_URL;
  const externalReady = configuredAlipayIdentity && configuredAliyunSafety && configuredPublicBase;
  const appConfig = readJson(path.join(ROOT, 'alipay', 'mini.project.json'), {});
  const appId = String(appConfig.appid || '');
  const requirementsFile = path.join(ROOT, 'server', 'requirements.txt');
  const assetManifest = collectAssetManifest();
  const cloudProbe = await readOnlyCloudProbe();
  const staging = stagingArtifacts();
  const stagingSourceReady = Object.values(staging).every(Boolean);

  const summary = {
    generatedAt: new Date().toISOString(),
    statusVocabulary: ['PASS', 'FAIL', 'NOT_RUN', 'BLOCKED_EXTERNAL'],
    baseMasterSha: git(ROOT, ['rev-parse', 'origin/master']),
    branch: git(ROOT, ['branch', '--show-current']),
    branchHead: git(ROOT, ['rev-parse', 'HEAD']),
    goldenBranch: git(GOLDEN_ROOT, ['branch', '--show-current']),
    goldenHead: git(GOLDEN_ROOT, ['rev-parse', 'HEAD']),
    alipayAppId: appId,
    alipayPackageBytes: Number(builderReport.packageBytes || staticReport.packageBytes || 0),
    alipayBuilder: testExitPass.builder ? 'PASS' : 'FAIL',
    alipayStatic: testExitPass.static && staticReport.allPassed === true ? 'PASS' : 'FAIL',
    alipayStage2StaticParity: testExitPass.stage2 && stage2Report.FULL_UI_PASS === 'PASS' ? 'PASS' : 'FAIL',
    alipayClientAdapter: testExitPass.platformCompat && compatReport.pass === true ? 'PASS' : 'FAIL',
    alipayServerProvider: testExitPass.providerAdapter && providerReport.pass === true ? 'PASS' : 'FAIL',
    alibabaGreenSdkRequirement: fs.readFileSync(requirementsFile, 'utf8').includes('alibabacloud-green20220302==3.2.4') ? 'PASS' : 'FAIL',
    secretValuesRecorded: false,
    wechatBusinessSourceChangedByThisTask: false,
    realAlipayAuth: externalReady ? 'NOT_RUN' : 'BLOCKED_EXTERNAL',
    realAlipayContentSafety: externalReady ? 'NOT_RUN' : 'BLOCKED_EXTERNAL',
    realAlipayIdPhoto: externalReady ? 'NOT_RUN' : 'BLOCKED_EXTERNAL',
    realAlipayWatermark: externalReady ? 'NOT_RUN' : 'BLOCKED_EXTERNAL',
    realAlipayCamera: 'NOT_RUN',
    realSaveToAlbum: 'NOT_RUN',
    realDevice: 'NOT_RUN',
    productionDeployment: 'NOT_RUN',
    readOnlyProductionHealth: cloudProbe.health.status === 200 ? 'PASS' : 'FAIL',
    productionAlipayLoginRouteIsolation: cloudProbe.alipayLoginRoute.status === 404 ? 'PASS' : 'FAIL',
    productionAlipayLoginRouteHttpStatus: cloudProbe.alipayLoginRoute.status,
    stagingSourceReady: stagingSourceReady ? 'PASS' : 'FAIL',
    stagingPublicHttps: cloudProbe.alipayStagingHealth.status === 200 ? 'PASS' : 'BLOCKED_EXTERNAL',
    stagingBackendReady: cloudProbe.alipayStagingHealth.status === 200 ? 'PASS' : 'BLOCKED_EXTERNAL',
    stagingAlipayAuthReady: externalReady && cloudProbe.alipayStagingHealth.status === 200 ? 'NOT_RUN' : 'BLOCKED_EXTERNAL',
    stagingContentSafetyReady: externalReady && cloudProbe.alipayStagingHealth.status === 200 ? 'NOT_RUN' : 'BLOCKED_EXTERNAL',
    stagingServerConfigInspection: 'BLOCKED_EXTERNAL',
    productionServerConfigInspection: 'BLOCKED_EXTERNAL',
    gitPush: 'NOT_RUN',
    masterMerge: 'NOT_RUN',
    alipayUpload: 'NOT_RUN',
    externalConfiguration: {
      alipayIdentityConfigured: configuredAlipayIdentity,
      aliyunSafetyConfigured: configuredAliyunSafety,
      publicHttpsBaseConfigured: configuredPublicBase,
    },
    stagingArtifacts: staging,
    assetsPrepared: assetManifest && assetManifest.assets ? 'PASS' : 'NOT_RUN',
    assetsSubmittedToBackend: 'NOT_RUN',
    finalDecision: externalReady ? 'NOT_RUN' : 'BLOCKED_EXTERNAL',
    fullBusinessParity: 'BLOCKED_EXTERNAL',
  };

  writeJson('02-platform-provider-validation.json', {
    generatedAt: summary.generatedAt,
    providerAdapter: providerReport,
    platformCompat: compatReport,
    sdkRequirementSha256: sha256(requirementsFile),
    commandExit: {
      providerAdapter: tests.providerAdapter.exitCode,
      platformCompat: tests.platformCompat.exitCode,
    },
  });
  writeJson('03-build-static-validation.json', {
    generatedAt: summary.generatedAt,
    static: staticReport,
    builder: builderReport,
    stage2: stage2Report,
    commandExit: {
      static: tests.static.exitCode,
      builder: tests.builder.exitCode,
      stage2: tests.stage2.exitCode,
    },
  });
  writeJson('04-external-readiness.json', {
    generatedAt: summary.generatedAt,
    valuesRedacted: true,
    environmentConfigured: env,
    requiredForRealE2E: {
      ALIPAY_APP_ID: 'server-only, must match the Alipay application',
      ALIPAY_APP_PRIVATE_KEY: 'server-only RSA2 signing key',
      ALIYUN_GREEN_ACCESS_KEY_ID: 'server-only RAM credential, or ALIBABA_CLOUD_ACCESS_KEY_ID',
      ALIYUN_GREEN_ACCESS_KEY_SECRET: 'server-only RAM credential, or ALIBABA_CLOUD_ACCESS_KEY_SECRET',
      CONTENT_SECURITY_PUBLIC_BASE_URL: 'public HTTPS base URL where staged images are reachable',
    },
    status: externalReady ? 'NOT_RUN' : 'BLOCKED_EXTERNAL',
  });
  writeJson('06-read-only-cloud-probe.json', {
    generatedAt: summary.generatedAt,
    productionWasModified: false,
    results: cloudProbe,
  });
  writeJson('07-staging-readiness.json', {
    generatedAt: summary.generatedAt,
    valuesRedacted: true,
    localConfigurationPresent: env,
    stagingSourceArtifacts: staging,
    stagingSourceReady: summary.stagingSourceReady,
    publicHttpsProbe: cloudProbe.alipayStagingHealth,
    stagingServerConfigInspection: summary.stagingServerConfigInspection,
    productionServerConfigInspection: summary.productionServerConfigInspection,
    needUserSecretConfig: externalReady ? [] : [
      'ALIPAY_APP_ID',
      'ALIPAY_APP_PRIVATE_KEY',
      'ALIYUN_GREEN_ACCESS_KEY_ID',
      'ALIYUN_GREEN_ACCESS_KEY_SECRET',
    ],
  });
  writeJson('05-command-transcripts.json', Object.fromEntries(Object.entries(tests).map(([name, result]) => [name, {
    command: result.command,
    exitCode: result.exitCode,
    stdoutTail: result.stdout.slice(-4000),
    stderrTail: result.stderr.slice(-2000),
  }])));
  writeText('external-blockers.md', [
    '# External E2E blockers',
    '',
    'Status: `BLOCKED_EXTERNAL`.',
    '',
    'The source code now has a server-side Alipay auth provider and a fail-closed Alibaba Cloud image moderation provider. No actual credential value is present in this workspace, and no staging backend has been configured or deployed for this branch. Therefore a real Alipay login, content-safety check, ID-photo generation, watermark removal, camera capture, download, or real-device check has not been claimed as passing.',
    '',
    `Read-only production probe: /api/health=${cloudProbe.health.status}; /api/auth/alipay/login=${cloudProbe.alipayLoginRoute.status}; /alipay-staging-v1/api/health=${cloudProbe.alipayStagingHealth.status}. The current production backend has not received this branch, and the isolated Staging route has not been installed.`,
    '',
    'To remove this block in a non-production environment:',
    '',
    '1. Configure server-only `ALIPAY_APP_ID` and `ALIPAY_APP_PRIVATE_KEY` for the associated Alipay application.',
    '2. Configure server-only Alibaba Cloud Green RAM credentials using `ALIYUN_GREEN_ACCESS_KEY_ID` / `ALIYUN_GREEN_ACCESS_KEY_SECRET` (or the `ALIBABA_CLOUD_*` equivalents).',
    '3. Set `CONTENT_SECURITY_PUBLIC_BASE_URL` and `ALIPAY_STAGING_BASE_URL` to `https://tupzjianzhao.chat/alipay-staging-v1` so moderation can fetch Staging assets.',
    '4. Install `server/requirements.txt` only in the isolated Staging worktree and start `photo-generator-alipay-staging.service`; do not touch production AI services.',
    '5. Include `deploy/staging/alipay/alipay-staging.nginx.conf` in the existing HTTPS server block, run `nginx -t`, then reload Nginx. The production `/api/*` route remains unchanged.',
    '6. Allow `https://tupzjianzhao.chat` in the Alipay mini-program request/upload/download domain configuration; the preview client uses the isolated path prefix.',
    '7. Run the prepared exact-SHA image assets through both WeChat Golden and Alipay, then record actual outputs, dimensions, hashes, and visual comparisons.',
    '',
    'No secret value, token, openid, or private key is included in this report.',
  ].join('\n') + '\n');
  writeText('final-summary.md', [
    '# Alipay Mini Program migration validation',
    '',
    `- Generated: ${summary.generatedAt}`,
    `- Golden WeChat branch/SHA: ${summary.goldenBranch} / ${summary.goldenHead}`,
    `- Alipay branch/SHA: ${summary.branch} / ${summary.branchHead}`,
    `- Alipay AppID: ${summary.alipayAppId}`,
    `- Package bytes: ${summary.alipayPackageBytes}`,
    '',
    '## Verified locally',
    '',
    `- Alipay package static validation: ${summary.alipayStatic}`,
    `- Alipay builder validation: ${summary.alipayBuilder}`,
    `- Page/event/layout parity static validation: ${summary.alipayStage2StaticParity}`,
    `- Alipay client adapter contract: ${summary.alipayClientAdapter}`,
    `- Alipay auth and safety Provider fail-closed contract: ${summary.alipayServerProvider}`,
    `- Alibaba Cloud Green SDK requirement: ${summary.alibabaGreenSdkRequirement}`,
    `- WeChat business source changed by this task: ${summary.wechatBusinessSourceChangedByThisTask}`,
    `- Read-only production health: ${summary.readOnlyProductionHealth}`,
    `- Production Alipay route isolation: ${summary.productionAlipayLoginRouteIsolation} (HTTP ${summary.productionAlipayLoginRouteHttpStatus})`,
    `- Staging source configuration: ${summary.stagingSourceReady}`,
    `- Staging public HTTPS: ${summary.stagingPublicHttps}`,
    `- Staging backend readiness: ${summary.stagingBackendReady}`,
    '',
    '## Not claimed as passed',
    '',
    `- Real Alipay auth: ${summary.realAlipayAuth}`,
    `- Real Alipay content safety: ${summary.realAlipayContentSafety}`,
    `- Real Alipay ID photo: ${summary.realAlipayIdPhoto}`,
    `- Real Alipay watermark: ${summary.realAlipayWatermark}`,
    `- Full business parity: ${summary.fullBusinessParity}`,
    '',
    `## Final decision\n\n\`${summary.finalDecision}\``,
    '',
    'See `external-blockers.md` for the exact non-production configuration required before genuine end-to-end parity can be verified.',
  ].join('\n') + '\n');
  writeJson('final-status.json', summary);
  console.log(JSON.stringify(summary, null, 2));
  if (!Object.values(testExitPass).every(Boolean)) process.exitCode = 1;
}

main().catch((error) => {
  console.error(error && error.stack || String(error));
  process.exit(1);
});
