"""Verify the production ID-photo model routing contract without loading weights."""
from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path


SERVER_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SERVER_ROOT.parent
sys.path.insert(0, str(SERVER_ROOT))

from id_photo_engines.hivision import runner


def _function_args(path: Path, function_name: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return [arg.arg for arg in node.args.args]
    raise AssertionError(f"function not found: {function_name}")


def main() -> int:
    original_available_models = runner.available_models
    original_standard = os.environ.get("ID_PHOTO_HIVISION_STANDARD_MODEL")
    original_detail = os.environ.get("ID_PHOTO_HIVISION_DETAIL_MODEL")
    try:
        runner.available_models = lambda: ["hivision_modnet", "birefnet-v1-lite", "rmbg-1.4"]
        os.environ.pop("ID_PHOTO_HIVISION_STANDARD_MODEL", None)
        os.environ.pop("ID_PHOTO_HIVISION_DETAIL_MODEL", None)
        routing = runner.get_model_routing()
        standard_order = runner._model_order(routing["standard"])
        detail_order = runner._model_order(routing["detail"])
    finally:
        runner.available_models = original_available_models
        if original_standard is None:
            os.environ.pop("ID_PHOTO_HIVISION_STANDARD_MODEL", None)
        else:
            os.environ["ID_PHOTO_HIVISION_STANDARD_MODEL"] = original_standard
        if original_detail is None:
            os.environ.pop("ID_PHOTO_HIVISION_DETAIL_MODEL", None)
        else:
            os.environ["ID_PHOTO_HIVISION_DETAIL_MODEL"] = original_detail

    service_text = (SERVER_ROOT / "services" / "id_photo_v2.py").read_text(encoding="utf-8")
    cloud_service_text = (PROJECT_ROOT / "deploy" / "cloud" / "photo-generator.service").read_text(encoding="utf-8")
    runner_text = (SERVER_ROOT / "id_photo_engines" / "hivision" / "runner.py").read_text(encoding="utf-8")
    worker_text = (SERVER_ROOT / "id_photo_engines" / "hivision" / "worker.py").read_text(encoding="utf-8")
    legacy_path = SERVER_ROOT / "id_photo_engine_legacy" / "id_photo_v2.py"
    checks = {
        "serviceUsesTruthfulLegacyPipeline": "id_photo_engine_legacy.id_photo_v2" in service_text,
        "standardUsesFastModnet": routing["standard"] == "hivision_modnet",
        "detailUsesBirefnet": routing["detail"] == "birefnet-v1-lite",
        "balancedCandidateUsesRmbg": routing["balancedCandidate"] == "rmbg-1.4",
        "balancedDisabledAfterAbFailure": routing["balanced"] == "" and routing["balancedEnabled"] is False,
        "standardFallbacksRemain": standard_order[:3] == ["hivision_modnet", "birefnet-v1-lite", "rmbg-1.4"],
        "detailFallbacksRemain": detail_order[:3] == ["birefnet-v1-lite", "hivision_modnet", "rmbg-1.4"],
        "inferenceIsSerialized": hasattr(runner, "_INFERENCE_LOCK"),
        "residentWorkerConfigured": "HIVISION_WORKER_URL" in cloud_service_text,
        "detailReusesReleasedWorker": (
            '"released_resident_detail_worker"' in runner_text
            and 'worker = _call_worker(input_path, model, remaining)' in runner_text
            and 'worker_attempt["detailWorkerRelease"]' in runner_text
        ),
        "detailKeepsFullWorkingCopy": "else 1600" in worker_text,
        "cloudDetailIsolationConfigured": "ID_PHOTO_HIVISION_DETAIL_ISOLATED=true" in cloud_service_text,
        "workerReleaseAndRestoreConfigured": '@app.post("/release")' in worker_text and '@app.post("/warmup")' in worker_text,
        "prepareAcceptsHairRetouch": "hair_retouch" in _function_args(legacy_path, "prepare_id_photo_v2"),
        "prepareCutoutAcceptsHairRetouch": "hair_retouch" in _function_args(legacy_path, "_prepare_cutout"),
        "generateAcceptsHairRetouch": "hair_retouch" in _function_args(legacy_path, "generate_id_photo_v2"),
    }
    payload = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "routing": routing,
        "standardOrder": standard_order,
        "detailOrder": detail_order,
    }
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
