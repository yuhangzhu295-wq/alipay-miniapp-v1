const assert = require('assert')
const fs = require('fs')
const path = require('path')
const vm = require('vm')

const ROOT = path.resolve(__dirname, '..', '..')
const mode = process.argv[2] || 'full'
const checks = []

function read(relativePath) {
  return fs.readFileSync(path.join(ROOT, relativePath), 'utf8')
}

function check(name, condition, details) {
  const passed = Boolean(condition)
  checks.push({ name, passed, details: details || '' })
  if (!passed) throw new Error(name + (details ? ': ' + details : ''))
}

function makePage(definition) {
  const page = Object.assign({}, definition)
  page.data = JSON.parse(JSON.stringify(definition.data || {}))
  page.setData = function(update, callback) {
    Object.assign(this.data, update)
    if (callback) callback.call(this)
  }
  return page
}

function loadPage(relativePath, environment) {
  let definition
  const env = environment || {}
  const sandbox = {
    Page(value) { definition = value },
    require(request) {
      if (env.modules && env.modules[request]) return env.modules[request]
      return require(path.resolve(path.dirname(path.join(ROOT, relativePath)), request))
    },
    wx: env.wx || {},
    getApp: env.getApp || (() => ({ globalData: {} })),
    getCurrentPages: env.getCurrentPages || (() => []),
    console,
    Date,
    Math,
    Promise,
    setTimeout,
    clearTimeout
  }
  vm.runInNewContext(read(relativePath), sandbox, { filename: relativePath })
  assert(definition, relativePath + ' did not register a Page')
  return makePage(definition)
}

function verifyEntryPoints() {
  const app = JSON.parse(read('app.json'))
  check('capture-guide page registered', app.pages.includes('pages/capture-guide/capture-guide'))
  check('id-camera page registered', app.pages.includes('pages/id-camera/id-camera'))
  check('camera permission declared', Boolean(app.permission && app.permission['scope.camera']))

  const expected = [
    ['pages/index/index.js', /openCaptureGuide\(id\)/],
    ['pages/specs/specs.js', /openCaptureGuide\(specId \|\| id\)/],
    ['pages/photos/photos.js', /openCaptureGuide\('yicun'\)/],
    ['pages/tool-detail/tool-detail.js', /openCaptureGuide\('custom_pass', \{ custom: true \}\)/]
  ]
  expected.forEach(([file, pattern]) => {
    check(file + ' uses the shared first-entry helper', pattern.test(read(file)))
  })

  const firstEntryFiles = expected.map((row) => row[0])
  firstEntryFiles.forEach((file) => {
    check(file + ' has no direct first-entry generate URL', !/pages\/generate\/generate\?specId=/.test(read(file)))
  })
  check('generate retake opens custom camera', /openCustomCamera\(this\.data\.currentSpecId/.test(read('pages/generate/generate.js')))
  check('generate reupload is album-only', /sourceType:\s*\['album'\]/.test(read('pages/generate/generate.js')))
}

function verifyGuide() {
  const specs = require(path.join(ROOT, 'utils', 'specs.js'))
  let navigation
  let mediaOptions
  const helper = {
    openGenerateWithPhoto(specId, photo, source) { navigation = { specId, photo, source } },
    openCustomCamera(specId) { navigation = { cameraSpecId: specId } }
  }
  const wx = {
    setNavigationBarTitle() {},
    showToast() {},
    chooseMedia(options) {
      mediaOptions = options
      options.success({ tempFiles: [{ tempFilePath: 'wxfile://guide-album.jpg' }] })
      options.complete()
    }
  }
  const page = loadPage('pages/capture-guide/capture-guide.js', {
    wx,
    modules: {
      '../../utils/specs.js': specs,
      '../../utils/idPhotoEntry.js': helper
    }
  })
  const visibleSpecs = specs.getSpecsByCategory('all').filter((spec, index, list) => {
    return spec.enabled !== false && spec.active !== false && list.findIndex((item) => item.id === spec.id) === index
  })
  check('all visible specifications are included in guide verification', visibleSpecs.length >= 90, 'count=' + visibleSpecs.length)
  visibleSpecs.forEach((spec) => {
    page.onLoad({ specId: spec.id })
    check('guide preserves ' + spec.id, page.data.specId === spec.id)
    check(
      'guide resolves exact dimensions for ' + spec.id,
      page.data.pixelSizeText === spec.widthPx + ' × ' + spec.heightPx + 'px',
      page.data.pixelSizeText
    )
    check('guide resolves colors for ' + spec.id, page.data.colors.length > 0)
    page.chooseFromAlbum()
    check('guide album preserves ' + spec.id, navigation.specId === spec.id && navigation.source === 'album')
    page.openCamera()
    check('guide camera preserves ' + spec.id, navigation.cameraSpecId === spec.id)
    page.onShow()
  })
  page.onLoad({ specId: 'yicun' })
  page.chooseFromAlbum()
  check('guide album opens album only', JSON.stringify(mediaOptions.sourceType) === JSON.stringify(['album']))
  check('guide album transfers a real temp path', navigation.photo === 'wxfile://guide-album.jpg')
  check('guide album preserves selected spec', navigation.specId === 'yicun')
  check('guide exposes exactly two source actions', (read('pages/capture-guide/capture-guide.wxml').match(/class="action-button/g) || []).length === 2)
  check('guide has purpose-sensitive advice', /护照|身份证|passport|id\.card/.test(read('pages/capture-guide/capture-guide.js')))
  check('guide reads shared specification module', /utils\/specs\.js/.test(read('pages/capture-guide/capture-guide.js')))
}

function verifyCamera() {
  let takeCount = 0
  let transferred
  let cameraContextCreated = 0
  const helper = {
    createPhotoTransfer(photo, source, specId) { return { token: 'camera-token', tempFilePath: photo, source, specId, createdAt: Date.now() } },
    openGenerateWithPhoto(specId, photo, source) { transferred = { specId, photo, source } }
  }
  const wx = {
    createCameraContext() {
      cameraContextCreated += 1
      return {
        takePhoto(options) {
          takeCount += 1
          options.success({ tempImagePath: 'wxfile://camera.jpg' })
        }
      }
    },
    getSetting(options) { options.success({ authSetting: { 'scope.camera': true } }) },
    showToast() {},
    navigateBack() {},
    chooseMedia() {}
  }
  const specs = { getSpecById() { return { id: 'yicun', name: '一寸' } }, idPhotoSpecsV2: [] }
  const page = loadPage('pages/id-camera/id-camera.js', {
    wx,
    modules: {
      '../../utils/specs.js': specs,
      '../../utils/idPhotoEntry.js': helper
    }
  })
  page.onLoad({ specId: 'yicun' })
  page.onReady()
  page.onCameraReady()
  page.takePhoto()
  page.takePhoto()
  check('camera context is created', cameraContextCreated === 1)
  check('rapid shutter taps produce one capture', takeCount === 1)
  check('camera enters confirmation state', page.data.cameraMode === 'confirm' && page.data.capturedImage === 'wxfile://camera.jpg')
  page.retakePhoto()
  check('retake returns to live state and clears old photo', page.data.cameraMode === 'live' && page.data.capturedImage === '')
  page.onCameraReady()
  page.switchCamera()
  check('camera switches back to front', page.data.cameraPosition === 'front')
  page.onCameraReady()
  page.takePhoto()
  page.usePhoto()
  check('confirmed camera photo enters existing flow', transferred && transferred.photo === 'wxfile://camera.jpg' && transferred.specId === 'yicun')

  const wxml = read('pages/id-camera/id-camera.wxml')
  const js = read('pages/id-camera/id-camera.js')
  const svg = read('images/id-photo-camera-guide.svg')
  check('native camera component is used', /<camera[\s>]/.test(wxml))
  check('CameraContext.takePhoto is used', /createCameraContext\(\)/.test(js) && /\.takePhoto\(\{/.test(js))
  check('portrait guide is overlaid', /id-photo-camera-guide\.svg/.test(wxml) && /<path|<ellipse/.test(svg))
  check('eye reference line is present', /stroke-dasharray/.test(svg) && /eye-label/.test(wxml))
}

function verifyTransfer() {
  const transfer = {
    token: 'transfer-once',
    tempFilePath: 'wxfile://real-temp-photo.jpg',
    source: 'camera',
    specId: 'yicun',
    createdAt: Date.now()
  }
  let channelHandler
  let generateCount = 0
  let pending = transfer
  const idEntry = {
    consumePendingPhoto() { const value = pending; pending = null; return value },
    clearPendingPhoto() {},
    createPhotoTransfer(photo, source, specId) { return { token: 'local', tempFilePath: photo, source, specId } },
    openCustomCamera() {}
  }
  const spec = {
    id: 'yicun', name: '一寸', displayName: '一寸', widthPx: 295, heightPx: 413,
    widthMm: 25, heightMm: 35, defaultBg: 'blue', colors: ['blue', 'white', 'red', 'lightBlue', 'gray']
  }
  const specs = {
    getSpecById(id) { return id === 'yicun' ? spec : null },
    getColorById(id) { return { id, name: id, hex: id === 'white' ? '#ffffff' : '#1a73e8' } },
    formatSpecSize() { return '25x35mm | 295x413px' }
  }
  const wx = {
    setNavigationBarTitle() {},
    showToast() {},
    getFileSystemManager() { return { access(options) { options.success() } } }
  }
  const page = loadPage('pages/generate/generate.js', {
    wx,
    modules: {
      '../../utils/specs.js': specs,
      '../../utils/image.js': {},
      '../../utils/aiImageApi.js': {},
      '../../utils/apiConfig.js': { API_BASE_URL: 'https://tupzjianzhao.chat' },
      '../../utils/imageService.js': {},
      '../../utils/idPhotoEntry.js': idEntry
    }
  })
  page.getOpenerEventChannel = () => ({ on(name, callback) { if (name === 'idPhotoSource') channelHandler = callback } })
  page.generatePhoto = function() { generateCount += 1 }
  page.onLoad({ specId: 'yicun', transferToken: 'transfer-once' })
  channelHandler(transfer)
  check('generate receives actual temporary photo path', page.data.photoSrc === 'wxfile://real-temp-photo.jpg')
  check('incoming source is recorded', page.data.incomingSource === 'camera')
  check('incoming photo clears prepared state', page.data.preparedId === '' && page.data.preparedKey === '')
  check('event plus fallback generates exactly once', generateCount === 1, 'count=' + generateCount)
}

function verifyPermission() {
  let openedSettings = 0
  const wx = {
    createCameraContext() { return {} },
    getSetting(options) { options.success({ authSetting: { 'scope.camera': false } }) },
    openSetting(options) { openedSettings += 1; options.success({ authSetting: { 'scope.camera': true } }) },
    showToast() {}
  }
  const page = loadPage('pages/id-camera/id-camera.js', {
    wx,
    modules: {
      '../../utils/specs.js': { getSpecById() { return { id: 'yicun', name: '一寸' } }, idPhotoSpecsV2: [] },
      '../../utils/idPhotoEntry.js': {}
    }
  })
  page.onLoad({ specId: 'yicun' })
  page.onCameraError({ detail: { errMsg: 'authorize:fail auth deny', errCode: 10001 } })
  check('permission rejection has an actionable state', page.data.permissionDenied && page.data.cameraError)
  check('permission rejection message is explicit', page.data.cameraErrorText === '需要相机权限才能直接拍摄证件照。')
  page.openCameraSettings()
  check('permission settings are opened', openedSettings === 1)
  check('camera remounts after authorization', page.data.cameraVisible === true && page.data.permissionDenied === false)
  const js = read('pages/id-camera/id-camera.js')
  ;['errMsg', 'errCode', 'cameraPosition', 'route', 'specId'].forEach((field) => {
    check('camera errors log ' + field, new RegExp(field + ':').test(js))
  })
}

const runners = {
  entry: verifyEntryPoints,
  guide: verifyGuide,
  camera: verifyCamera,
  transfer: verifyTransfer,
  permission: verifyPermission,
  full() {
    verifyEntryPoints()
    verifyGuide()
    verifyCamera()
    verifyTransfer()
    verifyPermission()
  }
}

try {
  assert(runners[mode], 'unknown mode: ' + mode)
  runners[mode]()
  const result = { mode, passed: true, checks, passedCount: checks.length }
  process.stdout.write(JSON.stringify(result, null, 2) + '\n')
} catch (error) {
  const result = { mode, passed: false, checks, error: error.stack || String(error) }
  process.stderr.write(JSON.stringify(result, null, 2) + '\n')
  process.exit(1)
}
