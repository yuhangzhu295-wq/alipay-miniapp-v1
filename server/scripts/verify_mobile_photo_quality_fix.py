import ast
import importlib.util
import json
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
REPORT = ROOT / "reports" / "diagnostics" / "mobile-photo-quality-fix.json"


def load_resolver():
    source_path = SERVER / "id_photo_engine_legacy" / "id_photo_v2.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_resolve_official_input_type"
    )
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source_path), "exec"), namespace)
    return namespace["_resolve_official_input_type"]


def verify_classifier_fusion():
    resolve = load_resolver()
    cases = [
        ("object_real_face", "object", "", {"success": True, "engine": "mediapipe", "confidence": 0.91}, False, ("real_person", "mediapipe_face")),
        ("landscape_real_face", "landscape", "", {"success": True, "engine": "mediapipe", "confidence": 0.65}, False, ("real_person", "mediapipe_face")),
        ("low_confidence_stays_blocked", "object", "", {"success": True, "engine": "mediapipe", "confidence": 0.64}, False, ("object", "")),
        ("illustration_stays_blocked", "object", "", {"success": True, "engine": "mediapipe", "confidence": 0.99}, True, ("illustration", "")),
        ("opencv_does_not_override", "landscape", "", {"success": True, "engine": "opencv", "confidence": 0.99}, False, ("landscape", "")),
        ("explicit_type_is_preserved", "object", "anime", {"success": True, "engine": "mediapipe", "confidence": 0.99}, False, ("anime", "")),
    ]
    rows = []
    for name, detected, explicit, face, illustration_like, expected in cases:
        actual = resolve(detected, explicit, face, illustration_like)
        rows.append({"name": name, "actual": list(actual), "expected": list(expected), "passed": actual == expected})
    return rows


def verify_async_restore():
    runner_path = SERVER / "id_photo_engines" / "hivision" / "runner.py"
    spec = importlib.util.spec_from_file_location("standalone_hivision_runner", runner_path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)

    called = threading.Event()
    original = runner._call_worker_control

    def fake_control(endpoint, timeout=30, **params):
        time.sleep(0.2)
        called.set()
        return {"success": True, "durationMs": 200, "endpoint": endpoint, "params": params}

    try:
        runner._call_worker_control = fake_control
        started = time.perf_counter()
        scheduled = runner._restore_fast_worker_async("hivision_modnet")
        return_ms = int((time.perf_counter() - started) * 1000)
        completed = called.wait(2)
        return {
            "scheduled": scheduled,
            "returnMs": return_ms,
            "backgroundCompleted": completed,
            "passed": scheduled.get("scheduled") is True and return_ms < 100 and completed,
        }
    finally:
        runner._call_worker_control = original


def main():
    fusion = verify_classifier_fusion()
    restore = verify_async_restore()
    report = {
        "classifierFusion": fusion,
        "asyncFastWorkerRestore": restore,
        "passed": all(row["passed"] for row in fusion) and restore["passed"],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
