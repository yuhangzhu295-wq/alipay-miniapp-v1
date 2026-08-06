const fs = require('fs')
const path = require('path')
const automator = require('miniprogram-automator')
const specs = require('../../utils/specs.js')

const ROOT = path.resolve(__dirname, '..', '..')
const REPORT_DIR = process.env.ID_PHOTO_CAMERA_REPORT_DIR || path.join(ROOT, 'reports', 'id-photo-camera-flow')
const SCREENSHOT_DIR = path.join(REPORT_DIR, 'devtools-screenshots')
const PORT = Number(process.env.WECHAT_AUTOMATOR_PORT || 9430)
const checks = []
const runtime = { startedAt: new Date().toISOString(), port: PORT, exceptions: [], screenshots: [] }

fs.mkdirSync(SCREENSHOT_DIR, { recursive: true })

function timeout(label, promise, duration = 20000) {
  let timer
  return Promise.race([
    promise.finally(() => clearTimeout(timer)),
    new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(label + ' timed out')), duration) })
  ])
}

function check(name, passed, details) {
  const row = { name, passed: Boolean(passed), details: details || {} }
  checks.push(row)
  console.log(`[camera-devtools] ${row.passed ? 'PASS' : 'FAIL'} ${name}`)
  return row.passed
}

async function route(miniProgram, url, method = 'reLaunch') {
  const expected = url.replace(/^\//, '').split('?')[0]
  try {
    const page = await timeout(method + ' ' + url, miniProgram[method](url), 30000)
    await page.waitFor(700)
    return page
  } catch (error) {
    for (let i = 0; i < 10; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, 400))
      const page = await miniProgram.currentPage()
      if (page && page.path === expected) return page
    }
    throw error
  }
}

async function current(miniProgram, expected, duration = 12000) {
  const started = Date.now()
  let page
  while (Date.now() - started < duration) {
    page = await miniProgram.currentPage()
    if (page && page.path === expected) return page
    await new Promise((resolve) => setTimeout(resolve, 350))
  }
  return page
}

async function count(page, selector) {
  return (await page.$$(selector)).length
}

async function capture(miniProgram, name) {
  const target = path.join(SCREENSHOT_DIR, name + '.png')
  await timeout('screenshot ' + name, miniProgram.screenshot({ path: target }), 10000)
  runtime.screenshots.push(target)
}

async function main() {
  const miniProgram = await timeout(
    'connect WeChat DevTools',
    automator.connect({ wsEndpoint: `ws://127.0.0.1:${PORT}` }),
    30000
  )
  miniProgram.on('exception', (entry) => runtime.exceptions.push(entry))
  try {
    let page = await route(miniProgram, '/pages/index/index')
    check('official WeChat DevTools page channel connected', page && page.path === 'pages/index/index', { path: page && page.path })
    await page.callMethod('selectHotSpec', { currentTarget: { dataset: { id: 'yicun' } } })
    page = await current(miniProgram, 'pages/capture-guide/capture-guide')
    check('home one-inch entry opens capture guide', page && page.path === 'pages/capture-guide/capture-guide', page && page.query)
    check('home entry preserves one-inch specId', page && page.query && page.query.specId === 'yicun', page && page.query)

    const seen = new Set()
    const specifications = specs.getSpecsByCategory('all').filter((spec) => {
      if (!spec.id || spec.enabled === false || spec.active === false || seen.has(spec.id)) return false
      seen.add(spec.id)
      return true
    })
    check('all visible specifications are included in DevTools verification', specifications.length >= 90, { count: specifications.length })
    for (const spec of specifications) {
      const specId = spec.id
      const label = spec.displayName || spec.name || specId
      await timeout('load guide data for ' + specId, page.callMethod('onLoad', { specId }), 10000)
      const data = {
        specId: await page.data('specId'),
        specName: await page.data('specName'),
        pixels: await page.data('pixelSizeText'),
        colors: await page.data('colors'),
        dpi: await page.data('dpiText')
      }
      check(label + ' guide keeps specId', data.specId === specId, data)
      check(
        label + ' guide renders exact specification dimensions',
        data.pixels === spec.widthPx + ' × ' + spec.heightPx + 'px',
        Object.assign({ expected: spec.widthPx + ' × ' + spec.heightPx + 'px' }, data)
      )
      check(label + ' guide renders dynamic colors', Boolean(data.specName && data.colors.length), data)
      check(label + ' guide renders both real actions', (await count(page, '.action-button')) === 2)
    }

    page = await route(miniProgram, '/pages/capture-guide/capture-guide?specId=yicun')
    check('guide pose card renders', (await count(page, '.pose-card')) === 1)
    check('guide specification card renders', (await count(page, '.spec-card')) === 1)
    check('guide five background swatches render for one-inch', (await count(page, '.color-dot')) === 5)
    await capture(miniProgram, '01-capture-guide-yicun')
    await page.callMethod('openCamera')
    page = await current(miniProgram, 'pages/id-camera/id-camera')
    check('direct capture action opens custom camera', page && page.path === 'pages/id-camera/id-camera', page && page.query)
    check('custom camera keeps selected specId', page && page.query && page.query.specId === 'yicun', page && page.query)

    await page.setData({ cameraError: false, cameraVisible: true, cameraMode: 'live' })
    check('native camera page renders', (await count(page, '.camera-page')) === 1)
    check('portrait guide overlay renders', (await count(page, '.portrait-guide')) === 1)
    check('eye line label renders', (await count(page, '.eye-label')) === 1)
    check('camera controls render', (await count(page, '.camera-controls')) === 1)
    await capture(miniProgram, '02-id-camera-live')

    await page.callMethod('switchCamera')
    check('camera switch changes to front', (await page.data('cameraPosition')) === 'front')
    await page.setData({ cameraMode: 'confirm', capturedImage: '/images/id-photo-pose.svg', submitting: false })
    check('capture confirmation exposes retake and use actions', (await count(page, '.confirm-button')) === 2)
    await capture(miniProgram, '03-id-camera-confirm')
    await page.callMethod('retakePhoto')
    check('retake clears captured image', (await page.data('cameraMode')) === 'live' && (await page.data('capturedImage')) === '')

    await page.callMethod('onCameraError', { detail: { errMsg: 'authorize:fail auth deny', errCode: 10001 } })
    check('permission rejection renders recovery UI', (await page.data('permissionDenied')) === true && (await count(page, '.camera-error-view')) === 1)
    check('permission screen offers settings and album fallback', (await count(page, '.error-button')) === 2)
    await capture(miniProgram, '04-id-camera-permission')

    check('DevTools runtime has no uncaught page exception', runtime.exceptions.length === 0, runtime.exceptions)
  } finally {
    try { miniProgram.disconnect() } catch (ignored) {}
  }

  const payload = {
    passed: checks.every((row) => row.passed),
    checks,
    runtime: Object.assign(runtime, { finishedAt: new Date().toISOString() })
  }
  fs.writeFileSync(path.join(REPORT_DIR, 'devtools-report.json'), JSON.stringify(payload, null, 2) + '\n')
  if (!payload.passed) process.exitCode = 1
}

main().catch((error) => {
  console.error(error.stack || error)
  process.exit(1)
})
