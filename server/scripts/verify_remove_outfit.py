"""Verify that one-click outfit is removed from the ID-photo generator.

The check is intentionally mixed: static source guards catch hidden UI/request
regressions, while a mocked WeChat runtime executes the real generate page
methods and inspects the actual prepare payload sent by the page.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "reports" / "remove-outfit-and-career"


HARNESS = r"""
const path = require('path');
const Module = require('module');

const ROOT = process.argv[2];
const pages = {};
let currentPage = 'pages/generate/generate';
const aiCalls = [];
const wxCalls = [];
const storage = {};
const emit = process.stdout.write.bind(process.stdout);
console.log = () => {};

function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
function assert(cond, msg) { if (!cond) throw new Error(msg); }

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
    wxCalls.push({ fn: 'chooseMedia', sourceType: opts.sourceType || [] });
    if (opts && opts.success) opts.success({ tempFiles: [{ tempFilePath: 'tmp://person.jpg' }] });
  },
  setNavigationBarTitle(opts) { wxCalls.push({ fn: 'setNavigationBarTitle', opts }); },
  showToast(opts) { wxCalls.push({ fn: 'showToast', opts }); },
  showLoading(opts) { wxCalls.push({ fn: 'showLoading', opts }); },
  hideLoading() { wxCalls.push({ fn: 'hideLoading' }); },
  navigateTo(opts) { wxCalls.push({ fn: 'navigateTo', opts }); },
  downloadFile(opts) {
    wxCalls.push({ fn: 'downloadFile', opts });
    if (opts && opts.success) opts.success({ statusCode: 200, tempFilePath: 'tmp://downloaded.jpg' });
  },
  saveImageToPhotosAlbum(opts) {
    wxCalls.push({ fn: 'saveImageToPhotosAlbum', opts });
    if (opts && opts.success) opts.success({});
  },
  getStorageSync(key) { return storage[key]; },
  setStorageSync(key, value) { storage[key] = value; },
};

const originalLoad = Module._load;
Module._load = function(request, parent, isMain) {
  if (request.includes('utils/aiImageApi.js')) {
    return {
      prepareIdPhotoV2(imagePath, payload) {
        aiCalls.push({ fn: 'prepareIdPhotoV2', imagePath, payload });
        return Promise.resolve({ success: true, preparedId: 'prepared-remove-outfit' });
      },
      composeIdPhotoV2(payload) {
        aiCalls.push({ fn: 'composeIdPhotoV2', payload });
        return Promise.resolve({
          success: true,
          tempFilePath: 'tmp://id-photo-' + (payload.bgColorName || 'blue') + '.jpg',
          finalImageUrl: 'http://127.0.0.1:8000/outputs/id-photo.jpg',
          quality: { qualityReport: { passed: true, score: 99 } },
        });
      },
    };
  }
  if (request.includes('utils/image.js')) {
    return {
      generateLayoutPhoto() { return Promise.resolve('tmp://layout.jpg'); },
    };
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

(async () => {
  const page = loadPage('pages/generate/generate');
  page.onLoad({ specId: 'yicun' });
  assert(typeof page.selectOutfit !== 'function', 'selectOutfit method still exists');
  assert(!Object.prototype.hasOwnProperty.call(page.data, 'outfitOptions'), 'outfitOptions still exists in page data');
  assert(!Object.prototype.hasOwnProperty.call(page.data, 'outfitId'), 'outfitId still exists in page data');
  assert(!Object.prototype.hasOwnProperty.call(page.data, 'resultOutfitId'), 'resultOutfitId still exists in page data');
  page.choosePhoto();
  await sleep(80);
  assert(page.data.canDownload === true, 'generate flow did not become downloadable');
  assert(page.data.resultImage, 'result image missing after generate');
  page.selectBg({ currentTarget: { dataset: { id: 'red' } } });
  await sleep(80);
  assert(page.data.bgColorId === 'red', 'red background not selected');
  assert(page.data.resultColorId === 'red', 'red compose result not current');
  page.savePhoto();
  assert(wxCalls.some(c => c.fn === 'saveImageToPhotosAlbum'), 'save action did not run');
  const prepareCalls = aiCalls.filter(c => c.fn === 'prepareIdPhotoV2');
  const composeCalls = aiCalls.filter(c => c.fn === 'composeIdPhotoV2');
  assert(prepareCalls.length >= 1, 'prepare was not called for upload flow');
  assert(composeCalls.length >= 2, 'compose was not called for upload/background flow');
  const forbidden = ['outfit', 'suit', 'clothes', 'templateId', 'template'];
  const payloads = [...prepareCalls, ...composeCalls].map(c => c.payload || {});
  for (const payload of payloads) {
    for (const key of forbidden) {
      assert(!Object.prototype.hasOwnProperty.call(payload, key), 'forbidden generate request key remains: ' + key);
    }
  }
  emit(JSON.stringify({
    status: 'PASS',
    checks: {
      selectOutfitRemoved: true,
      outfitStateRemoved: true,
      uploadGenerateSaveWorks: true,
      preparePayloadsWithoutOutfit: true,
    },
    requestPayloads: payloads,
    wxCalls,
  }, null, 2));
})().catch(error => {
  emit(JSON.stringify({
    status: 'FAIL',
    error: error && error.stack ? error.stack : String(error),
    aiCalls,
    wxCalls,
  }, null, 2));
  process.exitCode = 1;
});
"""


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _write_report(payload: dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "remove-outfit-report.json").write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    md = [
        "# Remove Outfit Verification",
        "",
        f"- Status: {payload.get('status', 'FAIL')}",
        f"- Runtime executed: {payload.get('runtime', {}).get('executed') is True}",
        "",
        "## Checks",
    ]
    for name, value in (payload.get("checks") or {}).items():
        md.append(f"- {name}: {'PASS' if value else 'FAIL'}")
    if payload.get("error"):
        md.extend(["", "## Error", "```", str(payload["error"])[-4000:], "```"])
    (REPORT_DIR / "remove-outfit-report.md").write_text("\n".join(md), encoding="utf-8")


def main() -> int:
    generate_js = _read(ROOT / "pages" / "generate" / "generate.js")
    generate_wxml = _read(ROOT / "pages" / "generate" / "generate.wxml")
    generate_wxss = _read(ROOT / "pages" / "generate" / "generate.wxss")
    api_js = _read(ROOT / "utils" / "aiImageApi.js")

    forbidden_generate_tokens = [
        "outfit-card",
        "outfit-grid",
        "outfit-item",
        "outfitOptions",
        "outfitId",
        "resultOutfitId",
        "selectOutfit",
        "一键换装",
        "正在换装",
    ]
    static_checks = {
        "generateWxmlHasNoOutfitUi": all(token not in generate_wxml for token in forbidden_generate_tokens),
        "generateWxssHasNoOutfitStyles": ".outfit-" not in generate_wxss and "outfit" not in generate_wxss,
        "generateJsHasNoOutfitStateOrMethod": all(token not in generate_js for token in forbidden_generate_tokens),
        "generateRequestHasNoOutfitPayload": "requestPayload.outfit" not in generate_js
        and not re.search(r"\boutfit\s*:", generate_js),
        "apiPrepareRequestHasNoOutfit": "outfit: options.outfit" not in api_js
        and "outfit || 'preserve_original'" not in api_js,
    }

    harness_path = Path(tempfile.gettempdir()) / "verify_remove_outfit_harness.js"
    harness_path.write_text(HARNESS, encoding="utf-8")
    completed = subprocess.run(
        ["node", str(harness_path), str(ROOT)],
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=90,
    )
    try:
        runtime = json.loads(completed.stdout)
    except Exception:
        runtime = {
            "status": "FAIL",
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
            "returncode": completed.returncode,
        }
    runtime["executed"] = True
    runtime["returncode"] = completed.returncode
    if completed.stderr:
        runtime["stderr"] = completed.stderr[-4000:]

    checks = {**static_checks, **(runtime.get("checks") or {})}
    status = "PASS" if completed.returncode == 0 and runtime.get("status") == "PASS" and all(checks.values()) else "FAIL"
    payload = {
        "status": status,
        "passed": status == "PASS",
        "checks": checks,
        "runtime": runtime,
    }
    _write_report(payload)
    print(f"[verify-remove-outfit] {status} report={REPORT_DIR / 'remove-outfit-report.md'}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
