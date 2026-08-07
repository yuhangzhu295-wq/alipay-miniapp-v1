import re
import threading
import time
import uuid


_LOCK = threading.Lock()
_STATES = {}
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,80}$")
_TERMINAL_TTL_SECONDS = 600


def normalize_request_id(value):
    candidate = str(value or "").strip()
    if _REQUEST_ID_PATTERN.match(candidate):
        return candidate
    return uuid.uuid4().hex


def _cleanup_locked(now):
    expired = [
        request_id
        for request_id, state in _STATES.items()
        if state.get("status") != "active" and now - float(state.get("updatedAtEpoch") or now) > _TERMINAL_TTL_SECONDS
    ]
    for request_id in expired:
        _STATES.pop(request_id, None)


def begin_request(request_id):
    now = time.time()
    with _LOCK:
        _cleanup_locked(now)
        current = _STATES.get(request_id)
        if current and current.get("status") == "active":
            return False
        _STATES[request_id] = {
            "requestId": request_id,
            "status": "active",
            "stage": "received",
            "startedAtEpoch": now,
            "updatedAtEpoch": now,
            "elapsedMs": 0,
        }
    return True


def update_request(request_id, stage, **details):
    now = time.time()
    with _LOCK:
        state = _STATES.get(request_id)
        if not state:
            return
        state.update(details)
        state["stage"] = str(stage)
        state["updatedAtEpoch"] = now
        state["elapsedMs"] = int((now - float(state["startedAtEpoch"])) * 1000)


def finish_request(request_id, success, **details):
    update_request(request_id, "done" if success else "failed", **details)
    with _LOCK:
        if request_id in _STATES:
            _STATES[request_id]["status"] = "completed" if success else "failed"


def get_request(request_id):
    now = time.time()
    with _LOCK:
        _cleanup_locked(now)
        state = _STATES.get(request_id)
        if not state:
            return None
        payload = dict(state)
        if payload.get("status") == "active":
            payload["elapsedMs"] = int((now - float(payload["startedAtEpoch"])) * 1000)
        payload.pop("startedAtEpoch", None)
        payload.pop("updatedAtEpoch", None)
        return payload
