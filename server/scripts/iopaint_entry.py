"""Start IOPaint with scoped CPU threads and request-level LaMa telemetry."""
from __future__ import annotations

import json
import os
import sys
import threading
import time

import torch


TORCH_THREADS = max(1, int(os.environ.get("IOPAINT_TORCH_THREADS", "4")))
INTEROP_THREADS = max(1, int(os.environ.get("IOPAINT_TORCH_INTEROP_THREADS", "1")))
RUNTIME_PATH = os.environ.get("IOPAINT_RUNTIME_PATH", "/run/iopaint-lama-runtime.json")
WARM_PATH = os.environ.get("IOPAINT_WARM_PATH", "/run/iopaint-lama-warm.json")
_TELEMETRY = threading.local()


torch.set_num_threads(TORCH_THREADS)
torch.set_num_interop_threads(INTEROP_THREADS)


def _write_json(path, payload):
    temp_path = f"{path}.{os.getpid()}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, separators=(",", ":"))
    os.replace(temp_path, path)


def _memory_status():
    values = {"rssMb": 0.0, "swapMb": 0.0}
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    values["rssMb"] = round(int(line.split()[1]) / 1024.0, 1)
                elif line.startswith("VmSwap:"):
                    values["swapMb"] = round(int(line.split()[1]) / 1024.0, 1)
    except Exception:
        pass
    return values


def _model_warm():
    try:
        with open(WARM_PATH, "r", encoding="utf-8") as handle:
            state = json.load(handle)
        return bool(int(state.get("pid") or 0) == os.getpid() and state.get("modelWarm") is True)
    except Exception:
        return False


def _install_telemetry():
    import iopaint.api as api_module
    from iopaint.api import Api
    from iopaint.model_manager import ModelManager

    original_init = ModelManager.__init__
    original_call = ModelManager.__call__
    original_api_inpaint = Api.api_inpaint
    original_pil_to_bytes = api_module.pil_to_bytes

    def timed_init(self, *args, **kwargs):
        started = time.perf_counter()
        original_init(self, *args, **kwargs)
        model_load_ms = int((time.perf_counter() - started) * 1000)
        _write_json(RUNTIME_PATH, {
            "pid": os.getpid(),
            "model": str(getattr(self, "name", "lama")),
            "device": str(getattr(self, "device", "cpu")),
            "modelLoadMs": model_load_ms,
            "torchThreads": torch.get_num_threads(),
            "interopThreads": torch.get_num_interop_threads(),
            "startedAtEpoch": time.time(),
        })
        print(
            "[watermark-hd-iopaint-start] "
            + json.dumps({
                "pid": os.getpid(),
                "model": str(getattr(self, "name", "lama")),
                "modelLoadMs": model_load_ms,
                "torchThreads": torch.get_num_threads(),
                "interopThreads": torch.get_num_interop_threads(),
            }, separators=(",", ":")),
            flush=True,
        )

    def timed_call(self, image, mask, config):
        started = time.perf_counter()
        result = original_call(self, image, mask, config)
        _TELEMETRY.current = {
            "inputWidth": int(image.shape[1]),
            "inputHeight": int(image.shape[0]),
            "inferenceMs": int((time.perf_counter() - started) * 1000),
            "outputEncodeMs": 0,
        }
        return result

    def timed_pil_to_bytes(*args, **kwargs):
        started = time.perf_counter()
        result = original_pil_to_bytes(*args, **kwargs)
        current = getattr(_TELEMETRY, "current", {})
        current["outputEncodeMs"] = int((time.perf_counter() - started) * 1000)
        _TELEMETRY.current = current
        return result

    def timed_api_inpaint(self, req):
        started = time.perf_counter()
        response = original_api_inpaint(self, req)
        total_ms = int((time.perf_counter() - started) * 1000)
        current = dict(getattr(_TELEMETRY, "current", {}) or {})
        memory = _memory_status()
        request_id = str(getattr(req, "prompt", "") or "")
        model_name = str(getattr(self.model_manager, "name", "lama"))
        payload = {
            "requestId": request_id,
            "modelName": model_name,
            "modelLoadMs": 0,
            "modelWarm": _model_warm(),
            "inputWidth": int(current.get("inputWidth") or 0),
            "inputHeight": int(current.get("inputHeight") or 0),
            "torchThreads": torch.get_num_threads(),
            "interopThreads": torch.get_num_interop_threads(),
            "inferenceMs": int(current.get("inferenceMs") or 0),
            "outputEncodeMs": int(current.get("outputEncodeMs") or 0),
            "totalMs": total_ms,
            **memory,
        }
        response.headers["X-IOPaint-Inference-Ms"] = str(payload["inferenceMs"])
        response.headers["X-IOPaint-Output-Encode-Ms"] = str(payload["outputEncodeMs"])
        response.headers["X-IOPaint-Total-Ms"] = str(payload["totalMs"])
        response.headers["X-IOPaint-Model-Warm"] = "true" if payload["modelWarm"] else "false"
        response.headers["X-IOPaint-Torch-Threads"] = str(payload["torchThreads"])
        response.headers["X-IOPaint-Interop-Threads"] = str(payload["interopThreads"])
        print("[watermark-hd-iopaint] " + json.dumps(payload, separators=(",", ":")), flush=True)
        _TELEMETRY.current = {}
        return response

    ModelManager.__init__ = timed_init
    ModelManager.__call__ = timed_call
    api_module.pil_to_bytes = timed_pil_to_bytes
    timed_api_inpaint.__annotations__ = dict(getattr(original_api_inpaint, "__annotations__", {}))
    Api.api_inpaint = timed_api_inpaint


def main():
    _install_telemetry()
    from iopaint import entry_point

    return entry_point()


if __name__ == "__main__":
    sys.exit(main())
