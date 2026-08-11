const fs = require('fs')
const path = require('path')

const ROOT = path.resolve(__dirname, '..', '..')
const canvas = require(path.join(ROOT, 'utils', 'watermarkCanvas.js'))
const pageSource = fs.readFileSync(path.join(ROOT, 'pages', 'tool-detail', 'tool-detail.js'), 'utf8')
const templateSource = fs.readFileSync(path.join(ROOT, 'pages', 'tool-detail', 'tool-detail.wxml'), 'utf8')
const OUT = path.join(ROOT, 'reports', 'diagnostics', 'watermark-long-image-layout.json')

const maxWidth = 320
const maxHeight = 420
const cases = [
  { name: 'long-phone-screenshot', width: 944, height: 2048 },
  { name: 'very-long-document', width: 1080, height: 6000 },
  { name: 'standard-portrait', width: 1280, height: 1707 },
  { name: 'landscape', width: 2048, height: 944 },
  { name: 'square', width: 1200, height: 1200 }
]

const rows = cases.map((item) => {
  const fitted = canvas.calculateDisplaySize(item.width, item.height, maxWidth, maxHeight)
  const sourceRatio = item.width / item.height
  const displayRatio = fitted.width / fitted.height
  const ratioError = Math.abs(sourceRatio - displayRatio) / sourceRatio
  return {
    name: item.name,
    source: `${item.width}x${item.height}`,
    display: `${fitted.width}x${fitted.height}`,
    withinViewport: fitted.width <= maxWidth && fitted.height <= maxHeight,
    aspectRatioError: Number(ratioError.toFixed(6)),
    passed: fitted.width <= maxWidth && fitted.height <= maxHeight && ratioError < 0.006
  }
})

const report = {
  cases: rows,
  pagePassesViewportHeight: /containerHeight:\s*displayContainerH/.test(pageSource),
  viewportHeightIsResponsive: /windowHeight/.test(pageSource) && /0\.52/.test(pageSource),
  processActionFollowsCanvas: templateSource.indexOf('class="wm-canvas-action"') >
    templateSource.indexOf('class="upload-section"'),
  singleWatermarkProcessAction: (templateSource.match(/bindtap="doManualRemoveWatermark"/g) || []).length === 1,
  passed: rows.every((row) => row.passed) &&
    /containerHeight:\s*displayContainerH/.test(pageSource) &&
    /windowHeight/.test(pageSource) &&
    (templateSource.match(/bindtap="doManualRemoveWatermark"/g) || []).length === 1
}

fs.mkdirSync(path.dirname(OUT), { recursive: true })
fs.writeFileSync(OUT, JSON.stringify(report, null, 2) + '\n', 'utf8')
console.log(JSON.stringify(report, null, 2))
process.exitCode = report.passed ? 0 : 1
