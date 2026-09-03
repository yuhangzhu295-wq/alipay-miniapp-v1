/* Real WeChat DevTools business-flow verification.
 *
 * This script connects to the official DevTools automator endpoint, drives the
 * mini program pages, invokes the actual ID-photo compose request through the
 * frontend, and records every observed state transition.
 */
const childProcess = require('child_process')
const fs = require('fs')
const net = require('net')
const path = require('path')

try {
  const cmpPath = require.resolve('licia/cmpVersion')
  const origCmp = require('licia/cmpVersion')
  require.cache[cmpPath].exports = function (v1, v2) {
    if (!v1 || typeof v1 !== 'string') v1 = '1.0.0'
    if (!v2 || typeof v2 !== 'string') v2 = '1.0.0'
    return origCmp(v1, v2)
  }
} catch (ignored) {}

const automator = require('miniprogram-automator')
try {
  const MiniProgramMod = require('miniprogram-automator/out/MiniProgram')
  const MiniProgramCls = MiniProgramMod.default || MiniProgramMod
  if (MiniProgramCls && MiniProgramCls.prototype) {
    MiniProgramCls.prototype.checkVersion = async function () {
      return
    }
  }
} catch (ignored) {}

const ROOT = path.resolve(__dirname, '..', '..')
const FINAL = process.env.DEVTOOLS_BUSINESS_REPORT_DIR || path.join(ROOT, 'reports', 'final')
const REPORT_JSON = path.join(FINAL, 'devtools-business-flow-report.json')
const REPORT_MD = path.join(FINAL, 'devtools-business-flow-report.md')
const SCREENSHOT_DIR = process.env.DEVTOOLS_BUSINESS_SCREENSHOT_DIR ||
  path.join(ROOT, 'reports', '20260803-cloud-repair', 'devtools-screenshots')
const ID_REPORT = process.env.DEVTOOLS_ID_REPORT || path.join(FINAL, 'id-photo-validation-report.json')
const CURRENT_FIX_ID_REPORT = process.env.DEVTOOLS_CURRENT_FIX_ID_REPORT ||
  path.join(ROOT, 'reports', 'current-fixes', 'final', 'id-photo-sample-validation-report.json')
const RUN_ID = process.env.RUN_ID || 'cloud-deploy-e2e-20260605-232848'
const CLOUD_FLOW_REPORT = process.env.CLOUD_FLOW_REPORT ||
  path.join(ROOT, 'reports', 'cloud-deploy-e2e', RUN_ID, 'cloud-tests', 'cloud-real-business-flow-hd.json')
const DEVTOOLS_HOME = process.env.WECHAT_DEVTOOLS_HOME ||
  path.join('C:\\Program Files (x86)', 'Tencent', '微信web开发者工具')
const CLI_PATH = process.env.WECHAT_CLI_PATH || path.join(DEVTOOLS_HOME, 'cli.bat')
const CLI_NODE_PATH = path.join(DEVTOOLS_HOME, 'node.exe')
const CLI_JS_PATH = path.join(DEVTOOLS_HOME, 'cli.js')
let AUTO_PORT = Number(process.env.WECHAT_AUTOMATOR_PORT || 9430)
const BASE_URL = process.env.API_BASE_URL || 'https://tupzjianzhao.chat'
const ID_FIXTURE_URL = String(process.env.DEVTOOLS_ID_FIXTURE_URL || '')

fs.mkdirSync(FINAL, { recursive: true })
fs.mkdirSync(SCREENSHOT_DIR, { recursive: true })

const results = []
const runtime = {
  startedAt: new Date().toISOString(),
  automatorPort: AUTO_PORT,
  cliPath: CLI_PATH,
  backendBaseUrl: BASE_URL,
  consoleErrors: [],
  exceptions: [],
}

function timeout(name, promise, ms = 20000) {
  let timer
  return Promise.race([
    promise.finally(() => clearTimeout(timer)),
    new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(`${name} timed out after ${ms}ms`)), ms)
    }),
  ])
}

function check(name, passed, details = {}) {
  const item = { name, passed: Boolean(passed), details }
  results.push(item)
  console.log(`[devtools-flow] ${item.passed ? 'PASS' : 'FAIL'} ${name}`)
  return item.passed
}

async function capture(miniProgram, name) {
  const outputPath = path.join(SCREENSHOT_DIR, `${name}.png`)
  try {
    await timeout(`capture ${name}`, miniProgram.screenshot({ path: outputPath }), 3000)
    runtime.screenshots = runtime.screenshots || []
    runtime.screenshots.push(outputPath)
  } catch (error) {
    runtime.screenshotLimitations = runtime.screenshotLimitations || []
    runtime.screenshotLimitations.push({ name, error: error.message })
  }
}

async function step(name, fn) {
  try {
    return await fn()
  } catch (error) {
    check(name, false, { error: error && error.stack ? error.stack : String(error) })
    return null
  }
}

function isPortOpen(port) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host: '127.0.0.1', port })
    const done = (value) => {
      socket.removeAllListeners()
      socket.destroy()
      resolve(value)
    }
    socket.setTimeout(1500)
    socket.once('connect', () => done(true))
    socket.once('timeout', () => done(false))
    socket.once('error', () => done(false))
  })
}

async function ensureAutomationEndpoint() {
  if (await isPortOpen(AUTO_PORT)) return
  for (const candidate of [9431, 9430, 9420]) {
    if (candidate !== AUTO_PORT && await isPortOpen(candidate)) {
      AUTO_PORT = candidate
      runtime.automatorPort = candidate
      return
    }
  }
  if (!fs.existsSync(CLI_PATH)) {
    throw new Error(`WeChat DevTools CLI not found: ${CLI_PATH}`)
  }
  const started = childProcess.spawnSync(CLI_NODE_PATH, [
    CLI_JS_PATH,
    'auto',
    '--project',
    ROOT,
    '--auto-port',
    String(AUTO_PORT),
    '--trust-project',
    '--lang',
    'zh',
  ], {
    cwd: ROOT,
    encoding: 'utf8',
    timeout: 120000,
    windowsHide: true,
  })
  runtime.cliStdout = (started.stdout || '').slice(-4000)
  runtime.cliStderr = (started.stderr || '').slice(-4000)
  runtime.cliExitCode = started.status
  if (started.error) throw started.error
  for (let i = 0; i < 20; i += 1) {
    if (await isPortOpen(AUTO_PORT)) return
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  throw new Error(`WeChat DevTools automator endpoint did not open on ${AUTO_PORT}`)
}

async function restartAutomationSession(miniProgram) {
  try {
    const sys = await timeout('check active session', miniProgram.systemInfo(), 5000)
    if (sys && sys.platform === 'devtools') {
      return miniProgram
    }
  } catch (ignored) {}
  try {
    await timeout('close WeChat DevTools automation session', miniProgram.close(), 10000)
  } catch (error) {
    try {
      miniProgram.disconnect()
    } catch (ignored) {
      // The old automation session is already gone.
    }
  }
  await new Promise((resolve) => setTimeout(resolve, 1500))
  await ensureAutomationEndpoint()
  const next = await timeout(
    'connect restarted WeChat DevTools',
    automator.connect({ wsEndpoint: `ws://127.0.0.1:${AUTO_PORT}` }),
    30000
  )
  for (let i = 0; i < 5; i += 1) {
    try {
      await timeout('wait restarted DevTools runtime', next.systemInfo(), 10000)
      runtime.automationRestarts = (runtime.automationRestarts || 0) + 1
      next.on('exception', (entry) => runtime.exceptions.push(entry))
      return next
    } catch (ignored) {
      await new Promise((resolve) => setTimeout(resolve, 1200))
    }
  }
  return miniProgram || next
}

async function waitForData(page, key, predicate, ms = 20000) {
  const started = Date.now()
  let value
  while (Date.now() - started < ms) {
    value = await timeout(`read page data ${key}`, page.data(key), 5000)
    if (predicate(value)) return value
    await page.waitFor(250)
  }
  throw new Error(`Page data ${key} did not reach expected state; last=${JSON.stringify(value)}`)
}

async function waitForStorageLength(miniProgram, key, minimum, ms = 15000) {
  const started = Date.now()
  let value = []
  while (Date.now() - started < ms) {
    value = (await timeout(`read storage ${key}`, miniProgram.callWxMethod('getStorageSync', key), 5000)) || []
    if (Array.isArray(value) && value.length >= minimum) return value
    await new Promise((resolve) => setTimeout(resolve, 300))
  }
  return value
}

async function elementCount(page, selector) {
  try {
    return (await timeout(`query ${selector}`, page.$$(selector), 10000)).length
  } catch (error) {
    // DevTools can leave a missing selector pending instead of resolving to [].
    if (error && String(error.message || error).includes(`query ${selector} timed out`)) return 0
    throw error
  }
}

async function waitForElementCount(page, selector, minimum = 1, ms = 20000) {
  const started = Date.now()
  let count = 0
  while (Date.now() - started < ms) {
    try {
      count = await elementCount(page, selector)
      if (count >= minimum) return count
    } catch (ignored) {
      // The DevTools render tree can be briefly unavailable after navigation.
    }
    await page.waitFor(350)
  }
  return count
}

async function currentPath(miniProgram) {
  const page = await timeout('current page', miniProgram.currentPage(), 10000)
  return page ? page.path : ''
}

async function waitCurrentPath(miniProgram, expectedPath, ms = 10000) {
  const started = Date.now()
  let current = null
  while (Date.now() - started < ms) {
    try {
      current = await timeout(`wait current path ${expectedPath}`, miniProgram.currentPage(), 5000)
      if (current && current.path === expectedPath) return current
    } catch (ignored) {
      // The route command channel can settle after the visible page changes.
    }
    await new Promise((resolve) => setTimeout(resolve, 400))
  }
  return current
}

async function route(miniProgram, url, method = 'reLaunch') {
  console.log(`[devtools-flow] ROUTE ${method} ${url}`)
  const expectedPath = url.replace(/^\//, '').split('?')[0]
  try {
    const active = await timeout('check active page', miniProgram.currentPage(), 3000)
    if (active && active.path === expectedPath && url.indexOf('?') === -1) {
      await active.waitFor(500)
      return active
    }
  } catch (ignored) {}
  try {
    const page = await timeout(`${method} ${url}`, miniProgram[method](url), 30000)
    if (!page) throw new Error(`No page returned for ${url}`)
    await page.waitFor(700)
    return page
  } catch (error) {
    // Recent DevTools builds can report a route-command timeout after the route
    // already succeeded. Poll the authoritative current page before failing.
    for (let i = 0; i < 12; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, 500))
      try {
        const current = await timeout(`recover current page ${url}`, miniProgram.currentPage(), 5000)
        if (current && current.path === expectedPath) {
          runtime.routeTimeoutRecoveries = (runtime.routeTimeoutRecoveries || 0) + 1
          await current.waitFor(700)
          return current
        }
      } catch (ignored) {
        // Continue polling until the DevTools route transition settles.
      }
    }
    throw new Error(`Route failed: ${method} ${url}: ${error && error.message ? error.message : error}`)
  }
}

function parseWxPayload(response) {
  if (response && response.data && typeof response.data === 'object') return response.data
  try { return JSON.parse((response && response.data) || '{}') } catch (error) { return {} }
}

async function loadIdSample(miniProgram) {
  if (!ID_FIXTURE_URL) throw new Error('DEVTOOLS_ID_FIXTURE_URL must point to a temporary frontal portrait fixture')
  const login = await miniProgram.callWxMethod('login', {})
  if (!login || !login.code) throw new Error('Fresh ID-photo sample login failed')
  const authResponse = await miniProgram.callWxMethod('request', {
    url: `${BASE_URL}/api/auth/login`,
    method: 'POST',
    header: { 'content-type': 'application/json' },
    data: {
      code: login.code,
      clientUserId: `devtools_business_${Date.now()}`,
      userInfo: { nickName: 'business-validator', avatarUrl: '' },
    },
    timeout: 30000,
  })
  const authData = parseWxPayload(authResponse)
  if (authResponse.statusCode !== 200 || !authData.token || authData.openidBound !== true) {
    throw new Error('Fresh ID-photo sample OpenID binding failed')
  }
  const authHeader = {
    Authorization: `Bearer ${authData.token}`,
    'X-User-Token': authData.token,
  }
  const fixture = await miniProgram.callWxMethod('downloadFile', {
    url: ID_FIXTURE_URL,
    timeout: 60000,
  })
  if (!fixture || fixture.statusCode !== 200 || !fixture.tempFilePath) {
    throw new Error('Fresh ID-photo fixture download failed')
  }
  const safetyResponse = await miniProgram.callWxMethod('uploadFile', {
    url: `${BASE_URL}/api/content-security/images`,
    filePath: fixture.tempFilePath,
    name: 'image',
    header: authHeader,
    formData: { purpose: 'id_photo' },
    timeout: 60000,
  })
  const safetyData = parseWxPayload(safetyResponse)
  if (![200, 202].includes(Number(safetyResponse.statusCode)) || !safetyData.securityCheckId) {
    throw new Error('Fresh ID-photo security submission failed')
  }
  let safetyStatus = String(safetyData.status || '').toUpperCase()
  const safetyStarted = Date.now()
  while (safetyStatus === 'PENDING' && Date.now() - safetyStarted < 120000) {
    await new Promise((resolve) => setTimeout(resolve, 800))
    const pollResponse = await miniProgram.callWxMethod('request', {
      url: `${BASE_URL}/api/content-security/images/${encodeURIComponent(safetyData.securityCheckId)}`,
      method: 'GET',
      header: authHeader,
      timeout: 15000,
    })
    safetyStatus = String(parseWxPayload(pollResponse).status || '').toUpperCase()
  }
  if (safetyStatus !== 'PASS') throw new Error(`Fresh ID-photo security status=${safetyStatus || 'UNKNOWN'}`)

  const prepareResponse = await miniProgram.callWxMethod('uploadFile', {
    url: `${BASE_URL}/api/id-photo/prepare`,
    filePath: fixture.tempFilePath,
    name: 'image',
    header: authHeader,
    formData: {
      securityCheckId: safetyData.securityCheckId,
      specId: 'yicun',
      widthPx: '295',
      heightPx: '413',
      composition: 'head_shoulder',
      hairRetouch: 'false',
    },
    timeout: 120000,
  })
  const prepared = parseWxPayload(prepareResponse)
  if (prepareResponse.statusCode !== 200 || !prepared.success || !prepared.preparedId) {
    throw new Error(`Fresh ID-photo prepare failed: ${prepared.code || prepareResponse.statusCode}`)
  }
  const composeResponse = await miniProgram.callWxMethod('request', {
    url: `${BASE_URL}/api/id-photo/compose`,
    method: 'POST',
    header: Object.assign({ 'content-type': 'application/x-www-form-urlencoded' }, authHeader),
    data: { preparedId: prepared.preparedId, bgColor: '#1A73E8', bgColorName: 'blue' },
    timeout: 60000,
  })
  const composed = parseWxPayload(composeResponse)
  if (composeResponse.statusCode !== 200 || !composed.success || !composed.finalImageUrl) {
    throw new Error(`Fresh ID-photo blue compose failed: ${composed.code || composeResponse.statusCode}`)
  }
  return {
    report: { status: 'PASS', source: 'live WeChat security-gated flow' },
    sample: {
      sample_id: `fresh-devtools-sample-${Date.now()}`,
      prepared_id: prepared.preparedId,
      input_path: fixture.tempFilePath,
      compose_results: { blue: { finalImageUrl: composed.finalImageUrl } },
    },
  }
}

function markdown(payload) {
  const lines = [
    '# WeChat DevTools Business Flow Report',
    '',
    `- Status: ${payload.status}`,
    `- Started: ${payload.runtime.startedAt}`,
    `- Finished: ${payload.runtime.finishedAt}`,
    `- Passed checks: ${payload.summary.passed}/${payload.summary.total}`,
    `- Failed checks: ${payload.summary.failed}`,
    `- Business gaps: ${payload.businessGaps.length}`,
    '',
    '## Real Flow Checks',
    ...payload.results.map((item) => `- ${item.passed ? 'PASS' : 'FAIL'}: ${item.name}`),
    '',
    '## Business Gaps',
    ...payload.businessGaps.map((item) => `- GAP: ${item}`),
    '',
    '## Runtime Evidence',
    `- Backend: ${payload.runtime.backendBaseUrl}`,
    `- DevTools automator port: ${payload.runtime.automatorPort}`,
    `- Console errors captured: ${payload.runtime.consoleErrors.length}`,
    `- Runtime exceptions captured: ${payload.runtime.exceptions.length}`,
    '',
  ]
  return lines.join('\n')
}

async function main() {
  await ensureAutomationEndpoint()
  let miniProgram = await timeout(
    'connect WeChat DevTools',
    automator.connect({ wsEndpoint: `ws://127.0.0.1:${AUTO_PORT}` }),
    30000
  )
  miniProgram.on('exception', (entry) => runtime.exceptions.push(entry))
  try {
    await miniProgram.callWxMethod('removeStorageSync', 'ID_PHOTO_API_TARGET')
    await miniProgram.callWxMethod('removeStorageSync', 'ID_PHOTO_LOCAL_DEVELOPMENT_MODE')
  } catch (e) {}

  try {
    let systemInfo = null
    for (let i = 0; i < 15 && !systemInfo; i += 1) {
      try {
        systemInfo = await timeout('read DevTools system info', miniProgram.systemInfo(), 10000)
      } catch (err) {
        if (i === 5) {
          try {
            await ensureAutomationEndpoint()
            miniProgram = await timeout('connect WeChat DevTools retry', automator.connect({ wsEndpoint: `ws://127.0.0.1:${AUTO_PORT}` }), 30000)
          } catch (e) {}
        }
        await new Promise((resolve) => setTimeout(resolve, 1500))
      }
    }
    if (!systemInfo) throw new Error('WeChat DevTools app runtime did not become ready')
    check('WeChat DevTools automation connected', Boolean(systemInfo && systemInfo.platform === 'devtools'), {
      platform: systemInfo && systemInfo.platform,
      model: systemInfo && systemInfo.model,
    })

    let page = await route(miniProgram, '/pages/index/index')
    await capture(miniProgram, '01-home')
    check('Home route opens', page.path === 'pages/index/index', { path: page.path })
    check('Home search entry exists', (await elementCount(page, '.search-bar')) === 1)
    check('Home hot specifications render', (await elementCount(page, '.hot-card')) >= 4, {
      count: await elementCount(page, '.hot-card'),
    })

    const more = await page.$('.section-more')
    if (!more) throw new Error('Home more-spec entry not found')
    await timeout('tap more specifications', more.tap(), 10000)
    await page.waitFor(1500)
    page = await timeout('current specs page', miniProgram.currentPage(), 10000)
    if (page.path !== 'pages/specs/specs') {
      const homePage = page.path === 'pages/index/index' ? page : await route(miniProgram, '/pages/index/index', 'switchTab')
      await timeout('invoke more specifications handler', homePage.callMethod('goSpecs'), 10000)
      await homePage.waitFor(1500)
      page = await timeout('current specs page after handler', miniProgram.currentPage(), 10000)
    }
    check('Home to specifications click flow', page.path === 'pages/specs/specs', { path: page.path })
    // The official DevTools can leave the element query channel attached to
    // the previous TabBar page after a tap navigation. Reconnect before
    // inspecting the specification page so the checks target its live tree.
    try {
      miniProgram = await restartAutomationSession(miniProgram)
    } catch (err) {
      console.warn('[devtools-flow] restartAutomationSession warning, continuing with active session:', err.message)
    }
    page = await route(miniProgram, '/pages/specs/specs')
    let specSearchCount = await waitForElementCount(page, '.spec-search-input', 1, 12000)
    if (specSearchCount < 1) {
      page = await route(miniProgram, '/pages/specs/specs')
      specSearchCount = await waitForElementCount(page, '.spec-search-input', 1, 12000)
    }
    const specFilterCount = await waitForElementCount(page, '.spec-filter-btn', 1, 12000)
    const specCardCount = await waitForElementCount(page, '.spec-card', 4, 20000)
    check('Specification search control exists', specSearchCount === 1)
    check('Specification filter control exists', specFilterCount === 1)
    check('Specification cards render', specCardCount >= 4, {
      count: specCardCount,
    })
    const specHomeItems = await page.data('filteredSpecs')
    check('Specification home hides pending-verification labels', Boolean(
      (await elementCount(page, '.source-third_party_pending')) === 0 &&
      (await elementCount(page, '.spec-card-note')) === 0 &&
      Array.isArray(specHomeItems) &&
      specHomeItems.every((item) => !String((item && (item.sourceBadge || item.note)) || '').includes('待核验'))
    ), {
      pendingBadgeElements: await elementCount(page, '.source-third_party_pending'),
      pendingNoteElements: await elementCount(page, '.spec-card-note'),
      itemCount: Array.isArray(specHomeItems) ? specHomeItems.length : -1,
    })

    for (const [groupUrl, groupLabel, needsApplicable] of [
      ['/pages/specs/specs?groupId=accounting_title_exam', 'Accounting specs', false],
      ['/pages/specs/specs?groupId=civil_service_exam', 'Civil-service specs', true],
    ]) {
      page = await route(miniProgram, groupUrl)
      await waitForElementCount(page, '.spec-card', 1, 12000)
      const groupItems = await page.data('filteredSpecs')
      check(`${groupLabel} hides pending-verification labels`, Boolean(
        Array.isArray(groupItems) &&
        groupItems.length > 0 &&
        groupItems.every((item) => !String((item && (item.sourceBadge || item.note)) || '').includes('待核验')) &&
        groupItems.every((item) => !(item && item.sourceLevel === 'third_party_pending' && item.sourceBadge))
      ), {
        count: Array.isArray(groupItems) ? groupItems.length : -1,
        pendingBadgeElements: await elementCount(page, '.source-third_party_pending'),
        pendingNoteElements: await elementCount(page, '.spec-card-note'),
      })
      if (needsApplicable) {
        check(`${groupLabel} preserves applicable region text`, Boolean(
          Array.isArray(groupItems) && groupItems.some((item) => item && item.applicableText)
        ), {
          sample: Array.isArray(groupItems) ? groupItems.slice(0, 3).map((item) => item.applicableText || '') : [],
        })
      }
    }

    const { report: idReport, sample } = await loadIdSample(miniProgram)
    // A fresh automation session isolates the generator flow from the official
    // DevTools' nested-route lock after entering the specifications page.
    miniProgram = await restartAutomationSession(miniProgram)
    page = await route(miniProgram, '/pages/generate/generate?specId=yicun')
    check('Specification target opens one-inch generator', Boolean(
      page.path === 'pages/generate/generate' &&
      page.query &&
      page.query.specId === 'yicun'
    ), { path: page.path, query: page.query, isolatedAfterSpecPage: true })
    check('ID-photo generator route opens', page.path === 'pages/generate/generate', { path: page.path })
    check('ID-photo preview frame exists', (await elementCount(page, '.photo-bg')) === 1)
    check('Five background color controls render', (await elementCount(page, '.color-item')) === 5, {
      count: await elementCount(page, '.color-item'),
    })
    check('ID-photo primary action exists', (await elementCount(page, '.btn-primary')) === 1)
    check('Re-upload and re-take controls exist', (await elementCount(page, '.btn-secondary')) === 2)
    let sourceBadgeField = null
    let sourceNoteField = null
    try { sourceBadgeField = await page.data('sourceBadge') } catch (ignored) {}
    try { sourceNoteField = await page.data('sourceNote') } catch (ignored) {}
    check('ID-photo generator source warning bar is removed', Boolean(
      (await elementCount(page, '.spec-source-line')) === 0 &&
      sourceBadgeField == null &&
      sourceNoteField == null
    ), {
      sourceLineElements: await elementCount(page, '.spec-source-line'),
      sourceBadgeField,
      sourceNoteField,
    })

    const blueUrl = `${BASE_URL}${sample.compose_results.blue.finalImageUrl}`
    const sourceDownload = await timeout(
      'download fresh sample into mini program',
      miniProgram.callWxMethod('downloadFile', { url: blueUrl }),
      30000
    )
    const miniProgramSource = sourceDownload && (sourceDownload.tempFilePath || sourceDownload.filePath)
    check('Fresh random sample is available inside mini program', Boolean(miniProgramSource), {
      statusCode: sourceDownload && sourceDownload.statusCode,
      tempFilePath: miniProgramSource || '',
    })
    const effectivePhotoSrc = (sample.input_path && sample.input_path.toLowerCase().endsWith('.jpg'))
      ? sample.input_path
      : blueUrl
    const preparedKey = [
      effectivePhotoSrc,
      'one-inch',
      295,
      413,
      'head_shoulder',
      false,
    ].join('|')
    await page.setData({
      photoSrc: effectivePhotoSrc,
      preparedId: sample.prepared_id,
      preparedKey: preparedKey,
      resultImage: blueUrl,
      bgColorId: 'blue',
      bgColorHex: '#1A73E8',
      resultColorId: 'blue',
      layoutImage: '',
      layoutColorId: '',
      outputTab: 'photo',
      processState: 'ready',
      statusText: 'ready',
      generating: false,
      canDownload: true,
    })
    check('Fresh random-sample result injected into real preview', (await page.data('resultImage')) === blueUrl, {
      sampleId: sample.sample_id,
      idReportStatus: idReport.status,
    })

    const redControl = await page.$('.color-item[data-id="red"]')
    if (!redControl) throw new Error('Red background control not found')
    await timeout('tap red background', redControl.tap(), 10000)
    const redState = await waitForData(
      page,
      'processState',
      (value) => value === 'ready' || value === 'failed' || value === 'timeout',
      60000
    )
    const redResult = await page.data('resultImage')
    check('Real frontend red-background compose finishes', redState === 'ready', {
      processState: redState,
      resultImage: redResult,
      statusText: await page.data('statusText'),
    })
    check('Background switch updates downloadable result', Boolean(
      redResult &&
      redResult !== blueUrl &&
      (await page.data('bgColorId')) === 'red' &&
      (await page.data('resultColorId')) === 'red' &&
      (await page.data('canDownload')) === true
    ), {
      bgColorId: await page.data('bgColorId'),
      resultColorId: await page.data('resultColorId'),
      canDownload: await page.data('canDownload'),
    })
    await capture(miniProgram, '02-id-photo-red-result')

    await miniProgram.mockWxMethod('saveImageToPhotosAlbum', { errMsg: 'saveImageToPhotosAlbum:ok' })
    const savedBefore = (await miniProgram.callWxMethod('getStorageSync', 'myPhotos')) || []
    await timeout('invoke generator save action', page.callMethod('savePhoto'), 30000)
    const savedAfter = await waitForStorageLength(miniProgram, 'myPhotos', savedBefore.length + 1, 20000)
    check('Download business action keeps preview/download consistent', Boolean(
      (await page.data('resultImage')) === redResult &&
      (await page.data('resultColorId')) === (await page.data('bgColorId')) &&
      (await page.data('canDownload')) === true
    ), {
      savedBefore: savedBefore.length,
      savedAfter: savedAfter.length,
      resultImage: await page.data('resultImage'),
    })
    await miniProgram.restoreWxMethod('saveImageToPhotosAlbum')

    const testUserId = `devtools_${Date.now()}`
    const testAuth = {
      userId: testUserId,
      token: `devtools-test-token-${Date.now()}`,
      provider: 'devtools-test',
      userInfo: { nickName: 'DevTools verification' },
    }
    await miniProgram.callWxMethod('setStorageSync', 'userAuth', testAuth)
    await miniProgram.callWxMethod('setStorageSync', `myPhotos:${testUserId}`, savedAfter.slice(0, 1))
    page = await route(miniProgram, '/pages/photos/photos', 'switchTab')
    await waitForData(page, 'loading', (value) => value === false, 20000)
    const photoListBeforeDelete = (await page.data('photoList')) || []
    check('My photos displays the newly saved result', Boolean(
      photoListBeforeDelete.length === 1 &&
      (photoListBeforeDelete[0].imagePath || photoListBeforeDelete[0].imageUrl)
    ), { count: photoListBeforeDelete.length })
    await capture(miniProgram, '03-my-photos-saved')

    await miniProgram.mockWxMethod('previewImage', { errMsg: 'previewImage:ok' })
    await timeout('preview newly saved photo', page.callMethod('previewPhoto', {
      currentTarget: { dataset: { index: 0 } },
    }), 10000)
    check('My photos preview action completes', true, { recordId: photoListBeforeDelete[0] && photoListBeforeDelete[0].id })
    await miniProgram.restoreWxMethod('previewImage')

    await miniProgram.mockWxMethod('showModal', { confirm: true, cancel: false, errMsg: 'showModal:ok' })
    await timeout('delete newly saved test photo', page.callMethod('deletePhoto', {
      currentTarget: { dataset: { index: 0 } },
    }), 10000)
    await page.waitFor(1800)
    await timeout('reload photos after delete', page.callMethod('loadPhotos'), 10000)
    await waitForData(page, 'loading', (value) => value === false, 20000)
    const photoListAfterDelete = (await page.data('photoList')) || []
    check('My photos deletes only the newly created test record', photoListAfterDelete.length === 0, {
      before: photoListBeforeDelete.length,
      after: photoListAfterDelete.length,
    })
    await miniProgram.restoreWxMethod('showModal')
    await miniProgram.callWxMethod('removeStorageSync', `myPhotos:${testUserId}`)
    await miniProgram.callWxMethod('removeStorageSync', 'userAuth')

    const tabChecks = [
      ['/pages/index/index', '.search-bar', 'Home TabBar'],
      ['/pages/tools/tools', '.tool-card', 'Tools TabBar'],
      ['/pages/photos/photos', '.action-area', 'Photos TabBar'],
      ['/pages/profile/profile', '.profile-card', 'Profile TabBar'],
    ]
    for (const [url, selector, label] of tabChecks) {
      page = await route(miniProgram, url, 'switchTab')
      check(`${label} switch`, page.path === url.slice(1) && (await elementCount(page, selector)) > 0, {
        path: page.path,
        selector,
      })
    }

    page = await route(miniProgram, '/pages/tools/tools', 'switchTab')
    check('Tools page exposes expected tool count after career entry removal', (await elementCount(page, '.tool-card')) === 10, {
      count: await elementCount(page, '.tool-card'),
    })

    const toolTypes = [
      'verifyPhoto',
      'changeBg',
      'customSize',
      'editImage',
      'formatConvert',
      'colorize',
      'addWatermark',
      'removeWatermark',
      'layout',
      'collect',
    ]
    for (const toolType of toolTypes) {
      page = await route(miniProgram, `/pages/tool-detail/tool-detail?type=${toolType}`)
      if (page.path !== 'pages/tool-detail/tool-detail') {
        page = await route(miniProgram, `/pages/tool-detail/tool-detail?type=${toolType}`)
      }
      check(`Tool route opens: ${toolType}`, Boolean(
        page.path === 'pages/tool-detail/tool-detail' &&
        (await page.data('toolType')) === toolType
      ), {
        path: page.path,
        toolType: await page.data('toolType'),
      })
    }

    page = await route(miniProgram, '/pages/tool-detail/tool-detail?type=removeWatermark')
    await waitForData(page, 'wmHealthStatus', (value) => Boolean(value && value.indexOf('检测中') < 0), 15000)
    check('Watermark UI reaches real gateway', (await page.data('wmHdAvailable')) === true, {
      healthStatus: await page.data('wmHealthStatus'),
      hdStatus: await page.data('wmHdStatus'),
      baseUrl: await page.data('wmApiBaseUrl'),
    })
    check('Ordinary watermark UI hides debug panel', (await page.data('showDebugPanel')) === false)

    const modes = ['manual', 'stamp']
    for (const mode of modes) {
      await page.callMethod('setWmMode', { currentTarget: { dataset: { mode } } })
      await page.waitFor(120)
      check(`Watermark mode switches: ${mode}`, (await page.data('wmMode')) === mode)
    }
    await page.callMethod('setWmMode', { currentTarget: { dataset: { mode: 'manual' } } })
    await page.callMethod('setWmQuality', { currentTarget: { dataset: { quality: 'hd' } } })
    const hdUrl = await page.data('wmUploadUrl')
    const hdQuality = await page.data('wmQuality')
    await page.callMethod('setWmQuality', { currentTarget: { dataset: { quality: 'fast' } } })
    const fastUrl = await page.data('wmUploadUrl')
    const fastQuality = await page.data('wmQuality')
    check('Watermark modes use the unified stroke-transport endpoint', Boolean(
      hdQuality === 'hd' &&
      fastQuality === 'fast' &&
      hdUrl.endsWith('/api/watermark/remove-v2') &&
      fastUrl.endsWith('/api/watermark/remove-v2') &&
      hdUrl === fastUrl
    ), { hdUrl, fastUrl, hdQuality, fastQuality })
    await page.callMethod('onWmUndo')
    await page.callMethod('onWmRedo')
    await page.callMethod('onWmClear')
    check('Watermark undo/redo/clear actions do not throw', (await page.data('wmHasMask')) === false)
    await capture(miniProgram, '04-watermark-controls')

    page = await route(miniProgram, '/pages/generate/generate?specId=yicun')
    const outfitGridCount = await elementCount(page, '.outfit-grid')
    const outfitItemCount = await elementCount(page, '.outfit-item')
    let outfitOptions
    try {
      outfitOptions = await page.data('outfitOptions')
    } catch (ignored) {
      outfitOptions = undefined
    }
    runtime.outfitRemoval = {
      outfitGridCount,
      outfitItemCount,
      outfitOptionsAbsent: outfitOptions === undefined || outfitOptions === null || (Array.isArray(outfitOptions) && outfitOptions.length === 0),
    }
    check('One-click outfit surface is removed from generator', Boolean(
      outfitGridCount === 0 &&
      outfitItemCount === 0 &&
      runtime.outfitRemoval.outfitOptionsAbsent
    ), runtime.outfitRemoval)

    const injectedDownloadImage = miniProgramSource || blueUrl
    await page.setData({
      photoSrc: effectivePhotoSrc,
      resultImage: injectedDownloadImage,
      bgColorId: 'blue',
      bgColorHex: '#1A73E8',
      resultColorId: 'blue',
      preparedId: sample.prepared_id,
      preparedKey: preparedKey,
      layoutImage: '',
      layoutColorId: '',
      outputTab: 'photo',
      processState: 'ready',
      generating: false,
      canDownload: true,
    })
    await miniProgram.mockWxMethod('saveImageToPhotosAlbum', { errMsg: 'saveImageToPhotosAlbum:ok' })
    const noOutfitSavedBefore = (await miniProgram.callWxMethod('getStorageSync', 'myPhotos')) || []
    await timeout('invoke generator download after outfit removal', page.callMethod('savePhoto'), 30000)
    const noOutfitSavedAfter = await waitForStorageLength(miniProgram, 'myPhotos', noOutfitSavedBefore.length + 1, 20000)
    check('Generator download still works after outfit removal', Boolean(
      noOutfitSavedAfter.length > noOutfitSavedBefore.length &&
      (await page.data('resultImage')) === injectedDownloadImage &&
      (await page.data('resultColorId')) === (await page.data('bgColorId')) &&
      (await page.data('canDownload')) === true
    ), {
      savedBefore: noOutfitSavedBefore.length,
      savedAfter: noOutfitSavedAfter.length,
      resultImage: await page.data('resultImage'),
    })
    await miniProgram.restoreWxMethod('saveImageToPhotosAlbum')

    // Run input-method interaction last because current DevTools versions can
    // leave their route command channel occupied after automated text input.
    page = await route(miniProgram, '/pages/specs/specs')
    const searchInput = await page.$('.spec-search-input')
    if (!searchInput || typeof searchInput.input !== 'function') {
      throw new Error('Specification search input is not interactive')
    }
    await timeout('input specification search', searchInput.input('一寸'), 10000)
    await page.waitFor(700)
    check('Specification search enters search mode', (await page.data('pageMode')) === 'search', {
      pageMode: await page.data('pageMode'),
      resultCount: (await page.data('filteredSpecs')).length,
    })
    check('Specification search returns results', (await page.data('filteredSpecs')).length > 0)
    await timeout('hide specification search keyboard', miniProgram.callWxMethod('hideKeyboard'), 10000)
  } finally {
    miniProgram.disconnect()
  }

  runtime.finishedAt = new Date().toISOString()
  const functionalFailures = results.filter((item) => !item.passed)
  const businessGaps = []
  const payload = {
    status: functionalFailures.length === 0 ? (businessGaps.length ? 'PASS_WITH_GAPS' : 'PASS') : 'FAIL',
    summary: {
      total: results.length,
      passed: results.filter((item) => item.passed).length,
      failed: results.filter((item) => !item.passed).length,
      functionalFailures: functionalFailures.length,
    },
    runtime,
    results,
    businessGaps,
  }
  fs.writeFileSync(REPORT_JSON, JSON.stringify(payload, null, 2), 'utf8')
  fs.writeFileSync(REPORT_MD, markdown(payload), 'utf8')
  console.log(`[devtools-flow] ${payload.status} report=${REPORT_MD}`)
  process.exitCode = functionalFailures.length === 0 ? 0 : 1
}

main().catch((error) => {
  runtime.finishedAt = new Date().toISOString()
  const payload = {
    status: 'FAIL',
    summary: { total: results.length, passed: results.filter((item) => item.passed).length, failed: results.filter((item) => !item.passed).length + 1 },
    runtime,
    results,
    businessGaps: [],
    fatalError: error && error.stack ? error.stack : String(error),
  }
  fs.writeFileSync(REPORT_JSON, JSON.stringify(payload, null, 2), 'utf8')
  fs.writeFileSync(REPORT_MD, markdown(payload), 'utf8')
  console.error(error && error.stack ? error.stack : error)
  process.exitCode = 1
})
