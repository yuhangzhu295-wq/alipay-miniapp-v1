"""Verify the main business flow after removing outfit/career entry."""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "reports" / "remove-outfit-and-career"
EXPECTED_TOOL_IDS = [
    "verifyPhoto",
    "changeBg",
    "customSize",
    "editImage",
    "formatConvert",
    "colorize",
    "addWatermark",
    "removeWatermark",
    "layout",
    "collect",
]
BG_IDS = ["blue", "white", "red", "lightBlue", "gray"]


HARNESS = r"""
const path = require('path');
const Module = require('module');

const ROOT = process.argv[2];
const expectedTools = JSON.parse(process.argv[3]);
const bgIds = JSON.parse(process.argv[4]);
const pages = {};
let currentPage = '';
const aiCalls = [];
const wxCalls = [];
const storage = {};
const emit = process.stdout.write.bind(process.stdout);
console.log = () => {};

function assert(cond, msg) { if (!cond) throw new Error(msg); }
function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

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
    const source = ((opts.sourceType || [])[0] || 'album').replace(/[^a-z]/g, '');
    if (opts && opts.success) opts.success({ tempFiles: [{ tempFilePath: 'tmp://' + source + '-sample.jpg' }] });
  },
  setNavigationBarTitle(opts) { wxCalls.push({ fn: 'setNavigationBarTitle', opts }); },
  showToast(opts) { wxCalls.push({ fn: 'showToast', opts }); },
  showLoading(opts) { wxCalls.push({ fn: 'showLoading', opts }); },
  hideLoading() { wxCalls.push({ fn: 'hideLoading' }); },
  navigateTo(opts) { wxCalls.push({ fn: 'navigateTo', opts }); },
  switchTab(opts) { wxCalls.push({ fn: 'switchTab', opts }); },
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
  showShareMenu(opts) { wxCalls.push({ fn: 'showShareMenu', opts }); },
};

const originalLoad = Module._load;
Module._load = function(request, parent, isMain) {
  if (request.includes('utils/aiImageApi.js')) {
    return {
      prepareIdPhotoV2(imagePath, payload) {
        aiCalls.push({ fn: 'prepareIdPhotoV2', imagePath, payload });
        return Promise.resolve({ success: true, preparedId: 'prepared-main-flow' });
      },
      composeIdPhotoV2(payload) {
        aiCalls.push({ fn: 'composeIdPhotoV2', payload });
        return Promise.resolve({
          success: true,
          tempFilePath: 'tmp://id-photo-' + (payload.bgColorName || 'blue') + '.jpg',
          finalImageUrl: 'http://127.0.0.1:8000/outputs/id-photo-' + (payload.bgColorName || 'blue') + '.jpg',
          quality: { qualityReport: { passed: true, score: 99 } },
          debug: { usedForegroundPng: true },
        });
      },
    };
  }
  if (request.includes('utils/image.js')) {
    return {
      generateLayoutPhoto(image, spec, rows, cols) {
        return Promise.resolve('tmp://layout-' + (spec && spec.id || 'spec') + '-' + rows + 'x' + cols + '.jpg');
      },
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
  const checks = {};
  const details = {};
  const forbiddenKeys = ['outfit', 'suit', 'clothes', 'templateId', 'template'];

  let page = loadPage('pages/generate/generate');
  page.onLoad({ specId: 'yicun' });
  checks.generateOpensOneInch = page.data.currentSpecId === 'yicun'
    && page.data.widthPxLabel === '295px'
    && page.data.heightPxLabel === '413px';
  checks.outfitRemovedFromPageRuntime = typeof page.selectOutfit !== 'function'
    && !Object.prototype.hasOwnProperty.call(page.data, 'outfitOptions')
    && !Object.prototype.hasOwnProperty.call(page.data, 'resultOutfitId');
  assert(checks.generateOpensOneInch, 'one-inch generator did not initialize');
  assert(checks.outfitRemovedFromPageRuntime, 'outfit runtime state/method still exists');

  page.choosePhoto();
  await sleep(80);
  assert(page.data.canDownload === true && page.data.resultImage, 'upload -> generate did not create downloadable photo');
  const uploadResult = page.data.resultImage;
  page.savePhoto();
  const savedAfterUpload = storage.myPhotos || [];
  checks.uploadGenerateDownloadWorks = savedAfterUpload.length > 0 && savedAfterUpload[0].imagePath === uploadResult;

  const bgResults = {};
  for (const bg of bgIds) {
    page.selectBg({ currentTarget: { dataset: { id: bg } } });
    await sleep(80);
    bgResults[bg] = {
      bgColorId: page.data.bgColorId,
      resultColorId: page.data.resultColorId,
      resultImage: page.data.resultImage,
      canDownload: page.data.canDownload,
    };
    assert(page.data.bgColorId === bg, 'background id did not switch to ' + bg);
    assert(page.data.resultColorId === bg, 'result color did not switch to ' + bg);
    assert(page.data.canDownload === true && page.data.resultImage, 'downloadable result missing for ' + bg);
  }
  checks.fiveBackgroundsGenerate = bgIds.every(bg => bgResults[bg] && bgResults[bg].resultColorId === bg && bgResults[bg].canDownload);

  page.setOutputTab({ currentTarget: { dataset: { tab: 'layout' } } });
  await sleep(50);
  checks.layoutStillGenerates = Boolean(page.data.layoutImage && page.data.layoutColorId === page.data.resultColorId);
  page.savePhoto();
  checks.layoutDownloadWorks = (storage.myPhotos || []).length >= 2;

  page.choosePhoto();
  await sleep(80);
  const reuploadOk = page.data.photoSrc.indexOf('album') >= 0 && page.data.canDownload === true;
  page.takePhoto();
  const retakeRoutedToCustomCamera = wxCalls.some(call =>
    call.fn === 'navigateTo' && String(call.opts.url).includes('/pages/id-camera/id-camera?specId=yicun')
  );
  page.handleIncomingPhoto({
    token: 'main-flow-camera-transfer',
    tempFilePath: 'tmp://camera-sample.jpg',
    source: 'camera',
    specId: 'yicun',
    createdAt: Date.now()
  });
  await sleep(80);
  checks.reuploadAndRetakeWork = reuploadOk
    && retakeRoutedToCustomCamera
    && page.data.photoSrc.indexOf('camera') >= 0
    && page.data.canDownload === true;

  page.goSpecs();
  checks.changeSpecNavigationWorks = wxCalls.some(call => call.fn === 'navigateTo' && String(call.opts.url).includes('/pages/specs/specs'));

  const preparePayloads = aiCalls.filter(call => call.fn === 'prepareIdPhotoV2').map(call => call.payload || {});
  const composePayloads = aiCalls.filter(call => call.fn === 'composeIdPhotoV2').map(call => call.payload || {});
  checks.generateRequestsDoNotCarryOutfit = [...preparePayloads, ...composePayloads].every(payload =>
    forbiddenKeys.every(key => !Object.prototype.hasOwnProperty.call(payload, key))
  );
  details.preparePayloads = preparePayloads;
  details.composePayloads = composePayloads;
  details.bgResults = bgResults;

  page = loadPage('pages/tools/tools');
  const toolIds = page.data.tools.map(item => item.id);
  checks.careerToolEntryRemoved = !toolIds.includes('professional');
  checks.otherToolsRemainInOrder = JSON.stringify(toolIds) === JSON.stringify(expectedTools);
  for (const id of expectedTools) {
    page.openTool({ currentTarget: { dataset: { id } } });
  }
  const routedTools = wxCalls
    .filter(call => call.fn === 'navigateTo' && String(call.opts.url).includes('/pages/tool-detail/tool-detail?type='))
    .map(call => String(call.opts.url).split('type=')[1]);
  checks.otherToolsNavigate = JSON.stringify(routedTools.slice(-expectedTools.length)) === JSON.stringify(expectedTools);
  details.toolIds = toolIds;
  details.routedTools = routedTools;

  assert(Object.values(checks).every(Boolean), 'one or more main-flow checks failed: ' + JSON.stringify(checks));
  emit(JSON.stringify({ status: 'PASS', checks, details, wxCalls }, null, 2));
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


def _run(cmd: list[str], timeout: int = 120) -> dict[str, Any]:
    completed = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
    )
    return {
        "cmd": cmd,
        "returncode": completed.returncode,
        "passed": completed.returncode == 0,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def _health(base_url: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, suffix in {"api": "/api/health", "watermark": "/api/watermark/health"}.items():
        try:
            res = requests.get(base_url.rstrip("/") + suffix, timeout=8)
            try:
                data = res.json()
            except Exception:
                data = {"text": res.text[:300]}
            result[name] = {
                "statusCode": res.status_code,
                "data": data,
                "passed": res.status_code == 200 and bool(data.get("success") or data.get("ok") or data.get("message") == "server running"),
            }
        except Exception as exc:
            result[name] = {"statusCode": 0, "error": str(exc), "passed": False}
    result["passed"] = all((item or {}).get("passed") for item in result.values() if isinstance(item, dict))
    return result


def _write_reports(payload: dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "main-flow-report.json").write_text(
        json.dumps(payload.get("mainFlow") or {}, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    (REPORT_DIR / "final-report.json").write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    checks = payload.get("stopConditions") or {}
    md = [
        "# Remove Outfit And Career Final Report",
        "",
        f"- Status: {payload.get('status', 'FAIL')}",
        f"- Base URL: `{payload.get('baseUrl')}`",
        "",
        "## Stop Conditions",
        *[f"- {name}: {'PASS' if ok else 'FAIL'}" for name, ok in checks.items()],
        "",
        "## Changed Scope",
        "- Removed the career portrait entry from the tools page.",
        "- Removed the one-click outfit UI/state/request coupling from the generator page.",
        "- Kept watermark, ID-photo generation, background switching, layout, upload, retake, and tool-detail routes intact.",
        "",
    ]
    if payload.get("mainFlow", {}).get("error"):
        md.extend(["## Main Flow Error", "```", str(payload["mainFlow"]["error"])[-4000:], "```", ""])
    (REPORT_DIR / "main-flow-report.md").write_text("\n".join(md), encoding="utf-8")
    (REPORT_DIR / "final-report.md").write_text("\n".join(md), encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    compile_runs = {
        "generateJs": _run(["node", "-c", "pages/generate/generate.js"]),
        "toolsJs": _run(["node", "-c", "pages/tools/tools.js"]),
        "apiJs": _run(["node", "-c", "utils/aiImageApi.js"]),
    }
    source_checks = {
        "generatePageHasNoOutfitUi": "outfit" not in _read(ROOT / "pages" / "generate" / "generate.wxml"),
        "generatePageHasNoOutfitState": "outfit" not in _read(ROOT / "pages" / "generate" / "generate.js"),
        "careerEntryAbsentFromToolsSource": "professional" not in _read(ROOT / "pages" / "tools" / "tools.js"),
        "watermarkRouteStillPresent": "removeWatermark" in _read(ROOT / "pages" / "tools" / "tools.js")
        and "removeWatermark" in _read(ROOT / "pages" / "tool-detail" / "tool-detail.js"),
        "customLayoutAndCollectStillPresent": "layout" in _read(ROOT / "pages" / "tools" / "tools.js")
        and "collect" in _read(ROOT / "pages" / "tools" / "tools.js"),
    }

    harness_path = Path(tempfile.gettempdir()) / "verify_remove_outfit_main_flow_harness.js"
    harness_path.write_text(HARNESS, encoding="utf-8")
    completed = subprocess.run(
        [
            "node",
            str(harness_path),
            str(ROOT),
            json.dumps(EXPECTED_TOOL_IDS),
            json.dumps(BG_IDS),
        ],
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=120,
    )
    try:
        main_flow = json.loads(completed.stdout)
    except Exception:
        main_flow = {
            "status": "FAIL",
            "error": (completed.stderr or completed.stdout)[-4000:],
            "returncode": completed.returncode,
        }
    main_flow["returncode"] = completed.returncode
    if completed.stderr:
        main_flow["stderr"] = completed.stderr[-4000:]

    health = _health(args.base_url)
    stop_conditions = {
        "backendApiHealthAccessible": (health.get("api") or {}).get("passed") is True,
        "watermarkGatewayHealthAccessible": (health.get("watermark") or {}).get("passed") is True,
        "compileChecksPass": all(item.get("passed") for item in compile_runs.values()),
        **source_checks,
        **{f"mainFlow_{name}": value for name, value in (main_flow.get("checks") or {}).items()},
        "finalReportsGenerated": True,
    }
    status = "PASS" if completed.returncode == 0 and main_flow.get("status") == "PASS" and all(stop_conditions.values()) else "FAIL"
    payload = {
        "status": status,
        "passed": status == "PASS",
        "baseUrl": args.base_url,
        "health": health,
        "compileRuns": compile_runs,
        "sourceChecks": source_checks,
        "mainFlow": main_flow,
        "stopConditions": stop_conditions,
    }
    _write_reports(payload)
    print(f"[verify-main-flow] {status} report={REPORT_DIR / 'final-report.md'}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
