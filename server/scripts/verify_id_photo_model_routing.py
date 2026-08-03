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
    legacy_path = SERVER_ROOT / "id_photo_engine_legacy" / "id_photo_v2.py"
    checks = {
        "serviceUsesTruthfulLegacyPipeline": "id_photo_engine_legacy.id_photo_v2" in service_text,
        "standardUsesBirefnet": routing["standard"] == "birefnet-v1-lite",
        "detailUsesBirefnet": routing["detail"] == "birefnet-v1-lite",
        "standardFallbacksRemain": standard_order[:3] == ["birefnet-v1-lite", "hivision_modnet", "rmbg-1.4"],
        "detailFallbacksRemain": detail_order[:3] == ["birefnet-v1-lite", "hivision_modnet", "rmbg-1.4"],
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
