/* Scoped real WeChat DevTools verification for the watermark HD flow. */
const fs = require('fs')
const path = require('path')
const automator = require('miniprogram-automator')

const ROOT = path.resolve(__dirname, '..', '..')
const REPORT_DIR = path.join(ROOT, 'reports', 'watermark-hd-speed')
const SCREENSHOT_DIR = path.join(REPORT_DIR, 'devtools-screenshots')
const REPORT_PATH = path.join(REPORT_DIR, 'devtools-run.json')
const ENDPOINT = process.env.WECHAT_AUTOMATOR_ENDPOINT || 'ws://127.0.0.1:9430'
const BASE_URL = process.env.API_BASE_URL || 'https://tupzjianzhao.chat'
const SOURCE_URL = process.env.WATERMARK_HD_SOURCE_URL ||
  BASE_URL + '/uploads/watermark/hd/result_1786069190010_234f2dec63eb.png'

fs.mkdirSync(SCREENSHOT_DIR, { recursive: true })

function timeout (label, promise, ms) {
  let timer
  return Promise.race([
    promise.finally(() => clearTimeout(timer)),
    new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(label + ' timed out')), ms) })
  ])
}

function strokeInfo (rects, width, height) {
  const payload = {
    version: 1,
    coordinateSpace: 'normalized',
    strokes: rects.map((rect) => ({
      type: 'brush',
      brushSizeRatio: rect.brush,
      points: [{ x: rect.x1, y: rect.y }, { x: rect.x2, y: rect.y }]
    }))
  }
  const strokesJson = JSON.stringify(payload)
  return {
    strokesJson,
    payload: Object.assign(payload, {
      originalWidth: width,
      originalHeight: height,
      displayWidth: width,
      displayHeight: height
    }),
    transportBytes: Buffer.byteLength(strokesJson, 'utf8'),
    serializeMs: 0
  }
}

async function capture (miniProgram, name, limitations) {
  const output = path.join(SCREENSHOT_DIR, name + '.png')
  try {
    await timeout('screenshot ' + name, miniProgram.screenshot({ path: output }), 5000)
    return output
  } catch (error) {
    limitations.push({ name, error: error.message })
    return ''
  }
}

async function waitForRun (page, statusHistory, timeoutMs = 120000) {
  const started = Date.now()
  let lastText = ''
  while (Date.now() - started < timeoutMs) {
    const processing = await page.data('processing')
    const text = String((await page.data('processingText')) || '')
    if (text && text !== lastText) {
      statusHistory.push({ elapsedMs: Date.now() - started, text })
      lastText = text
    }
    const engine = await page.data('currentEngine')
    const error = await page.data('wmLastError')
    if (!processing && (engine || error)) {
      return {
        engine,
        error: error || '',
        resultImage: await page.data('resultImage'),
        resultUrl: await page.data('currentResultUrl'),
        fileHash: await page.data('currentFileHash'),
        debug: (await page.data('wmBackendDebug')) || {},
        clientPerformance: (await page.data('wmClientPerformance')) || {}
      }
    }
    await page.waitFor(180)
  }
  throw new Error('watermark HD page did not reach a terminal state')
}

async function run (page, sourcePath, width, height, quality, rects) {
  const strokes = strokeInfo(rects, width, height)
  const statusHistory = []
  await page.setData({
    photoSrc: sourcePath,
    resultImage: '',
    currentEngine: '',
    currentResultUrl: '',
    currentFileHash: '',
    wmLastError: '',
    wmHdAvailable: true,
    wmStrength: 'medium',
    processing: false,
    wmClientPerformance: {},
    wmBackendDebug: {}
  })
  const started = Date.now()
  await page.callMethod(
    'runWatermarkRemoveWithStrokes',
    { width, height, nonZeroPixels: 1, maskRatio: 0.02 },
    strokes,
    quality
  )
  const state = await waitForRun(page, statusHistory)
  return Object.assign(state, {
    quality,
    elapsedMs: Date.now() - started,
    statusHistory
  })
}

function hdPassed (item) {
  const debug = item.debug || {}
  return Boolean(
    !item.error &&
    item.resultImage &&
    item.resultUrl &&
    item.engine === 'lama' &&
    debug.actualEngine === 'lama' &&
    debug.fallbackUsed === false &&
    debug.modelWarm === true &&
    Number(debug.modelLoadMs || 0) === 0 &&
    Number(debug.lamaCallCount || 0) >= 1 &&
    Number(debug.lamaCallCount || 0) <= 2 &&
    Number(debug.outsideRoiChangedPixels) === 0 &&
    debug.outputSize === '1495x999'
  )
}

async function main () {
  const report = {
    status: 'FAIL',
    endpoint: ENDPOINT,
    baseUrl: BASE_URL,
    sourceUrl: SOURCE_URL,
    startedAt: new Date().toISOString(),
    consoleErrors: [],
    exceptions: [],
    screenshotLimitations: [],
    screenshots: [],
    runs: []
  }
  const miniProgram = await timeout('connect WeChat DevTools', automator.connect({ wsEndpoint: ENDPOINT }), 30000)
  miniProgram.on('exception', (entry) => report.exceptions.push(entry))
  miniProgram.on('console', (entry) => {
    const value = JSON.stringify(entry)
    if (/error|fail|exception/i.test(value)) report.consoleErrors.push(entry)
  })
  try {
    const page = await timeout(
      'route watermark page',
      miniProgram.reLaunch('/pages/tool-detail/tool-detail?type=removeWatermark'),
      30000
    )
    await page.waitFor(1800)
    report.pagePath = page.path
    report.hdAvailable = await page.data('wmHdAvailable')
    report.healthStatus = await page.data('wmHealthStatus')
    report.uploadUrl = await page.data('wmUploadUrl')
    const readyShot = await capture(miniProgram, '01-hd-ready', report.screenshotLimitations)
    if (readyShot) report.screenshots.push(readyShot)

    const downloaded = await miniProgram.callWxMethod('downloadFile', { url: SOURCE_URL, timeout: 120000 })
    if (!downloaded || !downloaded.tempFilePath) throw new Error('DevTools source download failed')
    const farRects = [
      { x1: 0.06, x2: 0.13, y: 0.13, brush: 0.018 },
      { x1: 0.80, x2: 0.88, y: 0.80, brush: 0.020 }
    ]
    const continueRects = [{ x1: 0.28, x2: 0.38, y: 0.58, brush: 0.018 }]

    const quick = await run(page, downloaded.tempFilePath, 1495, 999, 'fast', farRects)
    report.runs.push(Object.assign({ operation: 'quick-regression' }, quick))

    const hd = await run(page, downloaded.tempFilePath, 1495, 999, 'hd', farRects)
    report.runs.push(Object.assign({ operation: 'hd' }, hd))
    const resultShot = await capture(miniProgram, '02-hd-result', report.screenshotLimitations)
    if (resultShot) report.screenshots.push(resultShot)

    const retry = await run(page, downloaded.tempFilePath, 1495, 999, 'hd', farRects)
    report.runs.push(Object.assign({ operation: 'hd-retry' }, retry))

    await page.setData({ currentResultLocalPath: hd.resultImage, resultImage: hd.resultImage })
    await page.callMethod('continueWatermarkRepair')
    await page.waitFor(250)
    const continueSource = await page.data('photoSrc')
    const continued = await run(page, continueSource, 1495, 999, 'hd', continueRects)
    report.runs.push(Object.assign({ operation: 'continue-local-repair' }, continued))

    const requiredClientFields = [
      'imageWidth', 'imageHeight', 'imageBytes', 'strokeCount', 'maskBytes',
      'clientImagePrepareMs', 'maskSerializeMs', 'uploadMs', 'waitResponseMs',
      'previewLoadMs', 'totalClientMs'
    ]
    const hdRuns = report.runs.filter((item) => item.quality === 'hd')
    report.checks = {
      pageOpened: report.pagePath === 'pages/tool-detail/tool-detail',
      cloudGatewaySelected: String(report.uploadUrl || '').endsWith('/api/watermark/remove-v2'),
      quickRegression: Boolean(quick.resultImage && !quick.error && quick.engine !== 'lama'),
      hdInitial: hdPassed(hd),
      hdRetry: hdPassed(retry),
      continueLocalRepair: hdPassed(continued),
      clientTimingComplete: hdRuns.every((item) => requiredClientFields.every((field) => Object.prototype.hasOwnProperty.call(item.clientPerformance || {}, field))),
      realStatusObserved: hdRuns.every((item) => item.statusHistory.some((entry) => entry.text.indexOf('已等待') >= 0)),
      noFakePercentage: hdRuns.every((item) => item.statusHistory.every((entry) => entry.text.indexOf('%') < 0)),
      previewDownloadHashStable: Boolean(hd.fileHash && hd.fileHash === retry.fileHash),
      noRuntimeExceptions: report.exceptions.length === 0
    }
    report.status = Object.values(report.checks).every(Boolean) ? 'PASS' : 'FAIL'
  } finally {
    report.finishedAt = new Date().toISOString()
    fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2), 'utf8')
    miniProgram.disconnect()
  }
  console.log(JSON.stringify({ status: report.status, checks: report.checks, screenshots: report.screenshots, screenshotLimitations: report.screenshotLimitations }, null, 2))
  if (report.status !== 'PASS') process.exitCode = 1
}

main().catch((error) => {
  console.error(error && error.stack ? error.stack : error)
  process.exitCode = 1
})
