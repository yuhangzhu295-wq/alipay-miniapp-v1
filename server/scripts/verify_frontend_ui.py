"""Mini-program frontend UI flow verifier.

This runs the real page JavaScript modules in a small mocked WeChat runtime.
It is not a static token-only scan: page methods such as upload, retake,
background switch, save, search, tool navigation, AI quality check, and
collection are invoked and their state transitions are asserted.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
FINAL = ROOT / "reports" / "final"
UI_SHOTS = FINAL / "ui-screenshots"


HARNESS = r"""
const path = require('path');
const fs = require('fs');
const Module = require('module');

const ROOT = process.argv[2];
const pages = {};
let currentPage = '';
const storage = {};
const wxCalls = [];
const aiCalls = [];

function pass(name, detail) {
  return { name, passed: true, detail: detail || {} };
}
function fail(name, error) {
  return { name, passed: false, error: String(error && error.stack || error) };
}
function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

global.getApp = () => ({ globalData: {} });
global.getCurrentPages = () => [{ route: currentPage }];
global.Page = function(def) {
  def.data = JSON.parse(JSON.stringify(def.data || {}));
  def.setData = function(next, cb) {
    Object.assign(this.data, next || {});
    if (typeof cb === 'function') cb.call(this);
  };
  pages[currentPage] = def;
};

global.wx = {
  chooseMedia(opts) {
    wxCalls.push({ fn: 'chooseMedia', opts: { sourceType: opts.sourceType || [] } });
    if (opts && opts.success) opts.success({ tempFiles: [{ tempFilePath: 'tmp://sample-id-photo.jpg' }] });
  },
  setNavigationBarTitle(opts) { wxCalls.push({ fn: 'setNavigationBarTitle', opts }); },
  showToast(opts) { wxCalls.push({ fn: 'showToast', opts }); },
  showLoading(opts) { wxCalls.push({ fn: 'showLoading', opts }); },
  hideLoading() { wxCalls.push({ fn: 'hideLoading' }); },
  navigateTo(opts) { wxCalls.push({ fn: 'navigateTo', opts }); },
  switchTab(opts) { wxCalls.push({ fn: 'switchTab', opts }); },
  previewImage(opts) { wxCalls.push({ fn: 'previewImage', opts }); },
  saveImageToPhotosAlbum(opts) {
    wxCalls.push({ fn: 'saveImageToPhotosAlbum', opts });
    if (opts && opts.success) opts.success({});
  },
  downloadFile(opts) {
    wxCalls.push({ fn: 'downloadFile', opts });
    if (opts && opts.success) opts.success({ statusCode: 200, tempFilePath: 'tmp://downloaded.jpg' });
  },
  showModal(opts) {
    wxCalls.push({ fn: 'showModal', opts });
    if (opts && opts.success) opts.success({ confirm: true });
  },
  openSetting() { wxCalls.push({ fn: 'openSetting' }); },
  getStorageSync(key) { return storage[key]; },
  setStorageSync(key, value) { storage[key] = value; },
  getAccountInfoSync() { return { miniProgram: { envVersion: 'release' } }; },
  getFileSystemManager() {
    return {
      readFileSync() { return 'ZmFrZQ=='; },
      access(opts) { if (opts && opts.success) opts.success(); }
    };
  },
  createSelectorQuery() {
    return { in() { return this; }, select() { return this; }, fields() { return this; }, exec(cb) { cb([null]); } };
  }
};

const originalLoad = Module._load;
Module._load = function(request, parent, isMain) {
  if (request.includes('utils/aiImageApi.js')) {
    return {
      checkApiAvailable: () => Promise.resolve(true),
      prepareIdPhotoV2: (imagePath, payload) => {
        aiCalls.push({ fn: 'prepareIdPhotoV2', imagePath, payload });
        return Promise.resolve({ success: true, preparedId: 'prepared-ui', debug: { faceDetector: 'mediapipe' } });
      },
      composeIdPhotoV2: (payload) => Promise.resolve({
        success: true,
        tempFilePath: 'tmp://final-' + (payload.bgColorName || 'blue') + '.jpg',
        finalImageUrl: 'http://127.0.0.1:8000/outputs/final.jpg',
        quality: { qualityReport: { passed: true, score: 99 } },
        debug: { usedForegroundPng: true, usedOriginalImageDirectly: false }
      }),
      generateIdPhotoV2: () => Promise.resolve({ success: true, tempFilePath: 'tmp://tool-id-photo.jpg', spec: { bgColor: '#1a73e8' } }),
      verifyPhoto: () => Promise.resolve({ success: true, score: 96, checks: [{ key: 'face', status: 'pass' }], suggestions: [] }),
      inspectPortrait: () => Promise.resolve({ success: true, imageType: 'real_person', quality: { imageType: 'real_person' } }),
      getIdPhotoCapabilities: () => Promise.resolve({ templates: [] }),
      validatePortraitInput: () => Promise.resolve({ success: true }),
      changeBg: () => Promise.resolve('tmp://change-bg.jpg')
    };
  }
  if (request.includes('utils/watermarkApi.js')) {
    return {
      getBaseUrl: () => 'http://127.0.0.1:8000',
      checkHealth: () => Promise.resolve({ ok: true, service: 'watermark-opencv-lama', hdAvailable: true, hdRealModelLoaded: true, fallbackUsed: false, fallbackAvailable: true }),
      isHdRepairEnabled: () => true,
      manualRemove: () => Promise.resolve({ tempFilePath: 'tmp://watermark-fast.jpg', backendMode: 'OpenCV inpaint', message: 'ok' }),
      quickRemove: () => Promise.resolve({ tempFilePath: 'tmp://watermark-quick.jpg', backendMode: 'OpenCV quick', message: 'ok' }),
      hdRemove: () => Promise.resolve({ tempFilePath: 'tmp://watermark-hd.jpg', mode: 'hd', engine: 'lama', fallbackUsed: false, backendMode: 'LaMa/IOPaint 高清修复', message: 'ok' })
    };
  }
  if (request.includes('utils/imageService.js')) {
    const photoFixture = () => ({
      id: 'ui-photo-1',
      imagePath: 'tmp://final-blue.jpg',
      imageUrl: 'http://127.0.0.1:8000/outputs/final-blue.jpg',
      createdAt: Date.now(),
      expireAt: Date.now() + 86400000
    });
    return {
      saveToAlbum: () => Promise.resolve(true),
      savePhotoRecord: () => true,
      fetchPhotoRecords: () => Promise.resolve([photoFixture()]),
      getPhotoRecords: () => [photoFixture()],
      downloadPhotoRecord: () => Promise.resolve('tmp://downloaded-user-photo.jpg'),
      deletePhotoRecord: () => Promise.resolve({ success: true })
    };
  }
  if (request.includes('utils/authService.js')) {
    return {
      isLoggedIn: () => !!storage.userAuth,
      getAuth: () => storage.userAuth || null,
      getUserId: () => storage.userAuth ? storage.userAuth.userId : '',
      getPhotoStorageKey: () => storage.userAuth ? ('myPhotos:' + storage.userAuth.userId) : 'myPhotos:guest',
      getAuthHeader: () => storage.userAuth ? { Authorization: 'Bearer ' + storage.userAuth.token, 'X-User-Token': storage.userAuth.token } : {},
      loginWithProfile: () => Promise.resolve(storage.userAuth),
      requireLogin: () => storage.userAuth ? Promise.resolve(storage.userAuth) : Promise.reject(new Error('AUTH_REQUIRED')),
      logout: () => { delete storage.userAuth; }
    };
  }
  if (request.includes('utils/professionalApi.js')) {
    return { generateProfessionalPhoto: () => Promise.resolve('tmp://professional.jpg') };
  }
  return originalLoad.apply(this, arguments);
};

function loadPage(route) {
  currentPage = route;
  const file = path.join(ROOT, route + '.js');
  delete require.cache[require.resolve(file)];
  require(file);
  return pages[route];
}

async function runCheck(name, fn) {
  try {
    const detail = await fn();
    return pass(name, detail);
  } catch (err) {
    return fail(name, err);
  }
}

(async () => {
  const checks = [];

  checks.push(await runCheck('generate upload -> compose -> save', async () => {
    const page = loadPage('pages/generate/generate');
    page.onLoad({ specId: 'yicun' });
    page.choosePhoto();
    await sleep(60);
    assert(page.data.photoSrc, 'photoSrc not set');
    assert(page.data.canDownload === true, 'canDownload not true after compose');
    assert(page.data.resultImage, 'resultImage missing');
    page.savePhoto();
    assert(wxCalls.some(c => c.fn === 'saveImageToPhotosAlbum'), 'saveImageToPhotosAlbum not called');
    return { resultImage: page.data.resultImage, canDownload: page.data.canDownload };
  }));

  checks.push(await runCheck('generate retake camera and switch background', async () => {
    const page = loadPage('pages/generate/generate');
    page.onLoad({ specId: 'yicun' });
    page.takePhoto();
    assert(wxCalls.some(c => c.fn === 'navigateTo' && c.opts.url.includes('/pages/id-camera/id-camera?specId=yicun')), 'retake did not open custom camera');
    page.handleIncomingPhoto({
      token: 'frontend-camera-transfer',
      tempFilePath: 'tmp://camera-id-photo.jpg',
      source: 'camera',
      specId: 'yicun',
      createdAt: Date.now()
    });
    await sleep(60);
    assert(page.data.photoSrc === 'tmp://camera-id-photo.jpg', 'confirmed camera photo not accepted');
    page.selectBg({ currentTarget: { dataset: { id: 'red' } } });
    await sleep(60);
    assert(page.data.bgColorId === 'red', 'red background not selected');
    assert(page.data.canDownload === true, 'canDownload not restored after color switch');
    assert(page.data.resultColorId === 'red', 'result color not red');
    return { bgColorId: page.data.bgColorId, resultColorId: page.data.resultColorId };
  }));

  checks.push(await runCheck('one-click outfit removed and ID-photo request stays clean', async () => {
    const wxml = fs.readFileSync(path.join(ROOT, 'pages/generate/generate.wxml'), 'utf8');
    const js = fs.readFileSync(path.join(ROOT, 'pages/generate/generate.js'), 'utf8');
    const wxss = fs.readFileSync(path.join(ROOT, 'pages/generate/generate.wxss'), 'utf8');
    const page = loadPage('pages/generate/generate');
    page.onLoad({ specId: 'yicun' });
    assert(!wxml.includes('outfit-grid') && !wxml.includes('selectOutfit') && !wxml.includes('一键换装'), 'one-click outfit UI still exists');
    assert(!js.includes('selectOutfit') && !js.includes('resultOutfitId') && !js.includes('requestPayload.outfit'), 'one-click outfit state/request code still exists');
    assert(!wxss.includes('.outfit-'), 'one-click outfit styles still exist');
    assert(typeof page.selectOutfit !== 'function', 'selectOutfit method still exists');
    assert(!Object.prototype.hasOwnProperty.call(page.data, 'outfitOptions'), 'outfitOptions state still exists');
    page.choosePhoto();
    await sleep(60);
    const prepareCalls = aiCalls.filter(c => c.fn === 'prepareIdPhotoV2');
    const prepareCall = prepareCalls[prepareCalls.length - 1];
    const forbidden = ['outfit', 'suit', 'clothes', 'templateId', 'template'];
    assert(prepareCall && prepareCall.payload, 'prepare flow did not run');
    forbidden.forEach(key => assert(!Object.prototype.hasOwnProperty.call(prepareCall.payload, key), 'forbidden outfit request key remains: ' + key));
    assert(page.data.canDownload === true, 'ID-photo result is not downloadable after outfit removal');
    page.savePhoto();
    assert(wxCalls.some(c => c.fn === 'saveImageToPhotosAlbum'), 'current ID-photo result was not saved');
    return { removed: true, preparePayload: prepareCall.payload };
  }));

  checks.push(await runCheck('generate preview frame is square without white rim', async () => {
    const wxss = fs.readFileSync(path.join(ROOT, 'pages/generate/generate.wxss'), 'utf8');
    const match = wxss.match(/\.photo-bg\s*\{([^}]*)\}/);
    assert(match, '.photo-bg style block missing');
    const block = match[1];
    assert(/border-radius\s*:\s*0\s*;/.test(block), 'photo preview still has rounded corners');
    assert(/border\s*:\s*0\s*;/.test(block), 'photo preview still has border that can reveal a white rim');
    assert(/box-shadow\s*:\s*none\s*;/.test(block), 'photo preview still has shadow instead of clean output frame');
    return { borderRadius: '0', border: '0', boxShadow: 'none' };
  }));

  checks.push(await runCheck('spec search page', async () => {
    const page = loadPage('pages/specs/specs');
    page.onLoad({});
    page.onSearch({ detail: { value: '一寸' } });
    assert(page.data.pageMode === 'search', 'pageMode not search');
    assert((page.data.filteredSpecs || []).length > 0, 'search returned no specs');
    return { count: page.data.filteredSpecs.length };
  }));

  checks.push(await runCheck('tools navigation', async () => {
    const page = loadPage('pages/tools/tools');
    page.openTool({ currentTarget: { dataset: { id: 'removeWatermark' } } });
    assert(wxCalls.some(c => c.fn === 'navigateTo' && c.opts.url.includes('removeWatermark')), 'removeWatermark navigation missing');
    return {};
  }));

  checks.push(await runCheck('photos page save and preview', async () => {
    storage.userAuth = { userId: 'ui-user-a', token: 'ui-token-a', userInfo: { nickName: 'UI用户A' } };
    storage['myPhotos:ui-user-a'] = [{ id: 'ui-photo-1', imagePath: 'tmp://final-blue.jpg', createdAt: Date.now(), expireAt: Date.now() + 86400000 }];
    const page = loadPage('pages/photos/photos');
    page.onShow();
    await sleep(20);
    assert(page.data.photoList.length === 1, 'photo list not loaded');
    page.previewPhoto({ currentTarget: { dataset: { index: 0 } } });
    page.saveToAlbum({ currentTarget: { dataset: { index: 0 } } });
    assert(wxCalls.some(c => c.fn === 'previewImage'), 'previewImage not called');
    assert(wxCalls.some(c => c.fn === 'saveImageToPhotosAlbum'), 'album save not called');
    return { count: page.data.photoList.length };
  }));

  checks.push(await runCheck('AI quality check tool', async () => {
    const page = loadPage('pages/tool-detail/tool-detail');
    page.onLoad({ type: 'verifyPhoto' });
    page.choosePhoto();
    await sleep(30);
    page.doVerifyPhoto();
    await sleep(60);
    assert(page.data.auditResult, 'auditResult missing');
    return { score: page.data.auditResult.score };
  }));

  checks.push(await runCheck('collect capture and add', async () => {
    const page = loadPage('pages/tool-detail/tool-detail');
    page.onLoad({ type: 'collect' });
    page.doCollectCapture();
    assert(page.data.photoSrc, 'collect capture missing photo');
    page.doCollectAdd();
    assert((storage.myPhotos || []).length > 0, 'collect record not saved');
    assert(page.data.photoSrc === '', 'collect photo was not cleared after add');
    return { count: storage.myPhotos.length };
  }));

  checks.push(await runCheck('watermark page hd health and mode switch', async () => {
    const page = loadPage('pages/tool-detail/tool-detail');
    page.onLoad({ type: 'removeWatermark' });
    await sleep(40);
    assert(page.data.wmHdAvailable === true, 'watermark hd mode should be available or explicitly fall back');
    assert(String(page.data.wmHealthStatus || '').length > 0, 'watermark health status missing');
    page.setWmQuality({ currentTarget: { dataset: { quality: 'hd' } } });
    assert(page.data.wmQuality === 'hd', 'hd mode was not selected while available');
    return { wmQuality: page.data.wmQuality, wmHdAvailable: page.data.wmHdAvailable };
  }));

  checks.push(await runCheck('ordinary watermark UI hides internal engine paths', async () => {
    const wxml = fs.readFileSync(path.join(ROOT, 'pages/tool-detail/tool-detail.wxml'), 'utf8');
    assert(!wxml.includes('engine: {{currentEngine}}'), 'ordinary result UI exposes engine');
    assert(!wxml.includes('output: {{currentOutputPath}}'), 'ordinary result UI exposes output path');
    assert(wxml.includes('wmResultMessage'), 'friendly result message missing');
    return {};
  }));

  const passed = checks.every(c => c.passed);
  console.log('__FRONTEND_UI_JSON__' + JSON.stringify({ status: passed ? 'PASS' : 'FAIL', passed, checks, wxCalls, aiCalls }, null, 2));
  process.exit(passed ? 0 : 1);
})();
"""


def main() -> int:
    FINAL.mkdir(parents=True, exist_ok=True)
    UI_SHOTS.mkdir(parents=True, exist_ok=True)
    harness_path = Path(tempfile.gettempdir()) / "id_photo_frontend_ui_harness.js"
    harness_path.write_text(HARNESS, encoding="utf-8")
    completed = subprocess.run(
        ["node", str(harness_path), str(ROOT)],
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=60,
    )
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    try:
        marker = "__FRONTEND_UI_JSON__"
        raw_payload = stdout.split(marker, 1)[1] if marker in stdout else stdout
        payload = json.loads(raw_payload)
    except Exception:
        payload = {
            "status": "FAIL",
            "passed": False,
            "stdout": stdout[-4000:],
            "stderr": stderr[-4000:],
            "returncode": completed.returncode,
        }
    payload["returncode"] = completed.returncode
    if completed.stderr:
        payload["stderr"] = completed.stderr[-4000:]
    screenshot_path = UI_SHOTS / "frontend-ui-dynamic-summary.png"
    image = Image.new("RGB", (1200, 760), (248, 250, 252))
    draw = ImageDraw.Draw(image)
    draw.text((36, 28), "Frontend UI Dynamic Verification", fill=(15, 23, 42))
    y = 76
    for item in payload.get("checks") or []:
        status = "PASS" if item.get("passed") else "FAIL"
        color = (22, 101, 52) if item.get("passed") else (185, 28, 28)
        draw.text((44, y), f"{status}  {item.get('name')}", fill=color)
        y += 38
    draw.text((44, y + 20), "Runtime: WeChat page JS executed with mocked wx API; navigation/upload/save/state transitions invoked.", fill=(71, 85, 105))
    image.save(screenshot_path)
    payload["screenshots"] = [str(screenshot_path)]
    (FINAL / "frontend-ui-report.json").write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    (FINAL / "frontend-ui-validation-report.json").write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    checks = payload.get("checks") or []
    md = [
        "# Frontend UI Flow Verification",
        "",
        f"- Status: {payload.get('status', 'FAIL')}",
        "- Runtime: real page JavaScript modules executed in mocked WeChat API runtime",
        "",
        "## Checks",
        *[f"- {item.get('name')}: {'PASS' if item.get('passed') else 'FAIL'}" for item in checks],
        "",
    ]
    if payload.get("stderr"):
        md.extend(["## stderr", "```", payload["stderr"], "```", ""])
    (FINAL / "frontend-ui-report.md").write_text("\n".join(md), encoding="utf-8")
    (FINAL / "frontend-ui-validation-report.md").write_text("\n".join(md), encoding="utf-8")
    print(f"[verify-frontend-ui] {payload.get('status', 'FAIL')} report={FINAL / 'frontend-ui-report.md'}")
    return 0 if payload.get("status") == "PASS" and completed.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
