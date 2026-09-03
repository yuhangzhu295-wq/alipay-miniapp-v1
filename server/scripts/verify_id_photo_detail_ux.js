const path = require('path')
const Module = require('module')

const ROOT = path.resolve(__dirname, '..', '..')
const generatePath = path.join(ROOT, 'pages', 'generate', 'generate.js')
const originalLoad = Module._load
let page
let scenario
let calls

function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)) }
function assert(value, message) { if (!value) throw new Error(message) }

function resetScenario(mode) {
  scenario = { mode, detailPolls: 0 }
  calls = { prepare: [], compose: [], create: [], poll: [] }
}

const aiMock = {
  prepareIdPhotoV2(imagePath, payload) {
    calls.prepare.push({ imagePath, payload })
    if (scenario.mode.indexOf('block') === 0) {
      const error = new Error('FAST block')
      error.code = 'ID_PHOTO_FAST_BLOCKED'
      error.sourceId = 'source-fast-block'
      return Promise.reject(error)
    }
    return Promise.resolve({ preparedId: 'prepared-fast', sourceId: 'source-fast' })
  },
  composeIdPhotoV2(payload) {
    calls.compose.push(payload)
    const detail = payload.preparedId === 'prepared-detail'
    return Promise.resolve({
      tempFilePath: detail ? 'tmp://detail-result.jpg' : 'tmp://fast-result.jpg',
      finalImageUrl: detail ? 'https://example.test/detail.jpg' : 'https://example.test/fast.jpg',
      quality: { qualityReport: { passed: true } }
    })
  },
  createIdPhotoDetailJob(payload) {
    calls.create.push(payload)
    return Promise.resolve({ jobId: 'detail-job', status: 'queued' })
  },
  getIdPhotoDetailJob(jobId) {
    calls.poll.push(jobId)
    scenario.detailPolls += 1
    if (scenario.mode === 'detail-fail') {
      return Promise.resolve({ jobId, status: 'failed', message: 'model failed' })
    }
    return Promise.resolve({ jobId, status: 'completed', preparedId: 'prepared-detail' })
  },
  cancelIdPhotoDetailJob() { return Promise.resolve({ status: 'cancelled' }) }
}

Module._load = function(request, parent, isMain) {
  if (request.includes('utils/aiImageApi.js')) return aiMock
  if (request.includes('utils/image.js')) {
    return { generateLayoutPhoto() { return Promise.resolve('tmp://layout.jpg') } }
  }
  if (request.includes('utils/imageService.js')) return { savePhotoRecord() {} }
  return originalLoad.apply(this, arguments)
}

global.getApp = () => ({ globalData: {} })
global.getCurrentPages = () => [{ route: 'pages/generate/generate' }]
global.Page = def => {
  page = def
  page.data = JSON.parse(JSON.stringify(def.data || {}))
  page.setData = function(next, callback) {
    Object.assign(this.data, next || {})
    if (callback) callback.call(this)
  }
}
global.wx = {
  setNavigationBarTitle() {},
  showToast() {},
  navigateTo() {},
  getFileSystemManager() { return { access(opts) { if (opts && opts.success) opts.success() } } }
}

function loadPage() {
  delete require.cache[require.resolve(generatePath)]
  require(generatePath)
  page.onLoad({ specId: 'yicun' })
  page.data.photoSrc = 'tmp://portrait.jpg'
  return page
}

async function run() {
  const checks = {}

  resetScenario('fast-pass')
  loadPage().generatePhoto()
  await sleep(30)
  checks.ordinarySendsFalse = calls.prepare[0].payload.hairRetouch === false
  checks.ordinaryUsesFastOnly = calls.create.length === 0 && page.data.resultImage === 'tmp://fast-result.jpg'

  resetScenario('block-ordinary')
  loadPage().generatePhoto()
  await sleep(30)
  checks.fastBlockIsFriendly = page.data.failureKind === 'fastBlocked'
    && page.data.failureMessage.includes('更清晰的正面照片')
    && calls.create.length === 0
  checks.fastBlockKeepsDetailSource = page.data.sourceId === 'source-fast-block'
  page.useHairRetouch()
  await sleep(40)
  checks.failureActionRunsRealDetail = calls.create.length === 1
    && calls.create[0].sourceId === 'source-fast-block'
    && page.data.detailJobStatus === 'completed'
    && page.data.resultImage === 'tmp://detail-result.jpg'

  resetScenario('fast-pass-hair')
  const hairPage = loadPage()
  hairPage.data.hairRetouch = true
  hairPage.generatePhoto()
  await sleep(50)
  checks.hairIntentSentTrue = calls.prepare[0].payload.hairRetouch === true
  checks.hairSuccessReplacesPreview = calls.create.length === 1
    && page.data.preparedId === 'prepared-detail'
    && page.data.resultImage === 'tmp://detail-result.jpg'

  resetScenario('block-hair')
  const autoPage = loadPage()
  autoPage.data.hairRetouch = true
  autoPage.generatePhoto()
  await sleep(50)
  checks.fastBlockAutoSwitches = calls.prepare[0].payload.hairRetouch === true
    && calls.create.length === 1
    && calls.create[0].sourceId === 'source-fast-block'
    && page.data.detailJobStatus === 'completed'
    && page.data.resultImage === 'tmp://detail-result.jpg'

  resetScenario('detail-fail')
  const failPage = loadPage()
  failPage.data.sourceId = 'source-detail-fail'
  failPage.startDetailRetouch('', { automatic: true })
  await sleep(30)
  checks.detailFailureIsProfessional = page.data.failureKind === 'detailFailed'
    && page.data.failureMessage.includes('清晰正面照片')
    && page.data.canDownload === false

  for (const [name, passed] of Object.entries(checks)) assert(passed, `${name} failed`)
  process.stdout.write(JSON.stringify({ status: 'PASS', checks }, null, 2))
}

run().catch(error => {
  process.stderr.write(error.stack || String(error))
  process.exitCode = 1
})
