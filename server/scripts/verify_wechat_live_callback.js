/* Real WeChat DevTools validation for mediaCheckAsync callback delivery. */
const fs = require('fs')
const path = require('path')
const automator = require('miniprogram-automator')

try {
  const MiniProgramMod = require('miniprogram-automator/out/MiniProgram')
  const MiniProgramCls = MiniProgramMod.default || MiniProgramMod
  if (MiniProgramCls && MiniProgramCls.prototype) {
    MiniProgramCls.prototype.checkVersion = async function () {}
  }
} catch (ignored) {}

const ROOT = path.resolve(__dirname, '..', '..')
const REPORT_DIR = path.join(ROOT, 'reports', 'security-validation', 'live-callback')
const REPORT_JSON = path.join(REPORT_DIR, 'wechat-live-callback.json')
const REPORT_MD = path.join(REPORT_DIR, 'wechat-live-callback.md')
const ENDPOINT = process.env.WECHAT_AUTOMATOR_ENDPOINT || 'ws://127.0.0.1:9430'
const BASE_URL = process.env.API_BASE_URL || 'https://tupzjianzhao.chat'
const FIXTURE_BASE = String(process.env.WECHAT_LIVE_FIXTURE_BASE || '').replace(/\/$/, '')
const POLL_INTERVAL_MS = 800
const POLL_TIMEOUT_MS = 120000

fs.mkdirSync(REPORT_DIR, { recursive: true })

function sleep (ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function parseUploadData (response) {
  if (response && response.data && typeof response.data === 'object') return response.data
  try { return JSON.parse((response && response.data) || '{}') } catch (error) { return {} }
}

async function request (miniProgram, options) {
  return miniProgram.callWxMethod('request', Object.assign({ timeout: 30000 }, options))
}

async function upload (miniProgram, options) {
  return miniProgram.callWxMethod('uploadFile', Object.assign({ timeout: 60000 }, options))
}

async function login (miniProgram) {
  const loginResult = await miniProgram.callWxMethod('login', {})
  if (!loginResult || !loginResult.code) throw new Error('wx.login did not return a code')
  const response = await request(miniProgram, {
    url: BASE_URL + '/api/auth/login',
    method: 'POST',
    header: { 'content-type': 'application/json' },
    data: {
      code: loginResult.code,
      clientUserId: 'live_callback_' + Date.now(),
      userInfo: { nickName: 'callback-validator', avatarUrl: '' }
    }
  })
  const data = (response && response.data) || {}
  if (response.statusCode !== 200 || !data.success || !data.token || !data.openidBound) {
    throw new Error('real WeChat login did not bind OpenID')
  }
  return {
    header: {
      Authorization: 'Bearer ' + data.token,
      'X-User-Token': data.token
    },
    summary: {
      loginSuccess: true,
      openidBound: true,
      openidPresent: true,
      provider: data.provider || ''
    }
  }
}

async function downloadFixture (miniProgram, name) {
  const started = Date.now()
  const response = await miniProgram.callWxMethod('downloadFile', {
    url: FIXTURE_BASE + '/' + name,
    timeout: 60000
  })
  if (!response || response.statusCode !== 200 || !response.tempFilePath) {
    throw new Error('fixture download failed: ' + name)
  }
  const imageInfo = await miniProgram.callWxMethod('getImageInfo', { src: response.tempFilePath })
  return {
    path: response.tempFilePath,
    downloadMs: Date.now() - started,
    width: Number(imageInfo && imageInfo.width) || 0,
    height: Number(imageInfo && imageInfo.height) || 0
  }
}

async function pollSecurity (miniProgram, checkId, authHeader) {
  const started = Date.now()
  let polls = 0
  while (Date.now() - started < POLL_TIMEOUT_MS) {
    polls += 1
    const response = await request(miniProgram, {
      url: BASE_URL + '/api/content-security/images/' + encodeURIComponent(checkId),
      method: 'GET',
      header: authHeader,
      timeout: 15000
    })
    const data = (response && response.data) || {}
    const status = String(data.status || '').toUpperCase()
    if (status && status !== 'PENDING') {
      return { status, callbackWaitMs: Date.now() - started, polls }
    }
    await sleep(POLL_INTERVAL_MS)
  }
  return { status: 'TIMEOUT', callbackWaitMs: Date.now() - started, polls }
}

async function submitFixture (miniProgram, fixture, authHeader) {
  const totalStarted = Date.now()
  const downloaded = await downloadFixture(miniProgram, fixture.file)
  const submitStarted = Date.now()
  const response = await upload(miniProgram, {
    url: BASE_URL + '/api/content-security/images',
    filePath: downloaded.path,
    name: 'image',
    header: authHeader,
    formData: { purpose: fixture.purpose }
  })
  const submitMs = Date.now() - submitStarted
  const data = parseUploadData(response)
  if (![200, 202].includes(Number(response && response.statusCode)) || !data.securityCheckId) {
    throw new Error('security submission failed for ' + fixture.name + ': HTTP ' + (response && response.statusCode))
  }
  let terminal = { status: String(data.status || '').toUpperCase(), callbackWaitMs: 0, polls: 0 }
  if (terminal.status === 'PENDING') {
    terminal = await pollSecurity(miniProgram, data.securityCheckId, authHeader)
  }
  return {
    name: fixture.name,
    file: fixture.file,
    purpose: fixture.purpose,
    expected: fixture.expected,
    filePath: downloaded.path,
    width: downloaded.width || fixture.width,
    height: downloaded.height || fixture.height,
    securityCheckId: data.securityCheckId,
    downloadMs: downloaded.downloadMs,
    submitMs,
    callbackWaitMs: terminal.callbackWaitMs,
    securityTotalMs: Date.now() - totalStarted,
    polls: terminal.polls,
    status: terminal.status
  }
}

async function verifyDownstream (miniProgram, result, authHeader) {
  if (result.expected === 'REJECT') {
    const response = await upload(miniProgram, {
      url: BASE_URL + '/api/id-photo/prepare',
      filePath: result.filePath,
      name: 'image',
      header: authHeader,
      formData: { securityCheckId: result.securityCheckId, specId: 'one-inch' }
    })
    const data = parseUploadData(response)
    return {
      attempted: true,
      httpStatus: Number(response.statusCode || 0),
      code: data.code || '',
      downstreamCalls: 0,
      passed: Number(response.statusCode) === 403 && data.code === 'CONTENT_SAFETY_REJECTED'
    }
  }

  const strokesJson = JSON.stringify({
    version: 1,
    coordinateSpace: 'normalized',
    strokes: [{
      type: 'brush',
      brushSizeRatio: 0.02,
      points: [{ x: 0.02, y: 0.02 }, { x: 0.04, y: 0.04 }]
    }]
  })
  const response = await upload(miniProgram, {
    url: BASE_URL + '/api/watermark/remove-v2',
    filePath: result.filePath,
    name: 'image',
    header: authHeader,
    formData: {
      securityCheckId: result.securityCheckId,
      quality: 'quick',
      strokesJson,
      originalWidth: String(result.width),
      originalHeight: String(result.height),
      displayWidth: String(result.width),
      displayHeight: String(result.height),
      strength: 'light'
    }
  })
  const data = parseUploadData(response)
  return {
    attempted: true,
    httpStatus: Number(response.statusCode || 0),
    success: Boolean(data.success),
    code: data.code || '',
    message: data.message || '',
    passed: Number(response.statusCode) === 200 && Boolean(data.success)
  }
}

function writeReport (report) {
  fs.writeFileSync(REPORT_JSON, JSON.stringify(report, null, 2), 'utf8')
  const lines = [
    '# WeChat mediaCheckAsync live callback validation',
    '',
    `- FINAL_PASS: ${report.finalPass}`,
    `- loginSuccess: ${report.login.loginSuccess}`,
    `- openidBound: ${report.login.openidBound}`,
    `- normalPass: ${report.summary.normalPass}/3`,
    `- riskRejected: ${report.summary.riskRejected}`,
    `- rejectDownstreamCalls: ${report.summary.rejectDownstreamCalls}`,
    '',
    '| sample | expected | status | submitMs | callbackWaitMs | securityTotalMs | downstream |',
    '| --- | --- | --- | ---: | ---: | ---: | --- |',
  ]
  for (const item of report.samples) {
    lines.push(`| ${item.name} | ${item.expected} | ${item.status} | ${item.submitMs} | ${item.callbackWaitMs} | ${item.securityTotalMs} | ${item.downstream.passed ? 'PASS' : 'FAIL'} |`)
  }
  fs.writeFileSync(REPORT_MD, lines.join('\n') + '\n', 'utf8')
}

async function main () {
  if (!FIXTURE_BASE) {
    throw new Error('WECHAT_LIVE_FIXTURE_BASE must point to the temporary callback validation fixtures')
  }
  const report = {
    startedAt: new Date().toISOString(),
    endpoint: ENDPOINT,
    callbackUrl: BASE_URL + '/api/content-security/callback',
    login: {},
    samples: [],
    summary: {},
    finalPass: false
  }
  let miniProgram
  try {
    miniProgram = await automator.connect({ wsEndpoint: ENDPOINT })
    const auth = await login(miniProgram)
    report.login = auth.summary
    const fixtures = [
      { name: 'normal-1', file: 'normal-1.jpg', width: 512, height: 512, purpose: 'id_photo', expected: 'PASS' },
      { name: 'normal-2', file: 'normal-2.jpg', width: 512, height: 480, purpose: 'watermark_removal', expected: 'PASS' },
      { name: 'normal-3', file: 'normal-3.png', width: 558, height: 563, purpose: 'image_processing', expected: 'PASS' },
      { name: 'risk-fixture', file: 'risk-fixture.jpg', width: 575, height: 720, purpose: 'id_photo', expected: 'REJECT' }
    ]
    for (const fixture of fixtures) {
      const result = await submitFixture(miniProgram, fixture, auth.header)
      result.downstream = await verifyDownstream(miniProgram, result, auth.header)
      result.passed = result.status === result.expected && result.downstream.passed
      report.samples.push(result)
      console.log(JSON.stringify({
        name: result.name,
        status: result.status,
        submitMs: result.submitMs,
        callbackWaitMs: result.callbackWaitMs,
        securityTotalMs: result.securityTotalMs,
        downstreamPassed: result.downstream.passed
      }))
    }
    report.summary.normalPass = report.samples.filter((item) => item.expected === 'PASS' && item.passed).length
    const risk = report.samples.find((item) => item.expected === 'REJECT') || {}
    report.summary.riskRejected = risk.status === 'REJECT'
    report.summary.rejectDownstreamCalls = risk.downstream ? risk.downstream.downstreamCalls : null
    report.finalPass = report.summary.normalPass === 3 && report.summary.riskRejected && report.summary.rejectDownstreamCalls === 0
  } catch (error) {
    report.error = error && error.stack ? error.stack : String(error)
  } finally {
    report.finishedAt = new Date().toISOString()
    writeReport(report)
    if (miniProgram) {
      try { miniProgram.disconnect() } catch (ignored) {}
    }
  }
  console.log(JSON.stringify({ finalPass: report.finalPass, summary: report.summary, report: REPORT_JSON }))
  process.exitCode = report.finalPass ? 0 : 1
}

main()
