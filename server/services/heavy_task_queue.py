import os
import threading
import time


class HeavyTaskBusyError(RuntimeError):
    pass


class HeavyTaskQueue:
    def __init__(self):
        self._slot = threading.Lock()
        self._state_lock = threading.Lock()
        self._active = None
        self._waiting = 0
        self._max_waiting = max(1, int(os.environ.get("HEAVY_TASK_MAX_WAITING", "2")))
        self._wait_timeout = max(1, int(os.environ.get("HEAVY_TASK_QUEUE_TIMEOUT_SECONDS", "300")))

    def snapshot(self):
        with self._state_lock:
            return {
                "activeTaskType": self._active,
                "waiting": self._waiting,
                "maxWaiting": self._max_waiting,
            }

    def can_accept(self):
        with self._state_lock:
            return self._waiting < self._max_waiting

    def run(self, task_type, callback, wait_timeout=None):
        with self._state_lock:
            if self._waiting >= self._max_waiting:
                raise HeavyTaskBusyError("heavy task queue is full")
            self._waiting += 1
        queued_at = time.perf_counter()
        acquired = self._slot.acquire(timeout=wait_timeout or self._wait_timeout)
        queue_wait_ms = int((time.perf_counter() - queued_at) * 1000)
        with self._state_lock:
            self._waiting = max(0, self._waiting - 1)
            if acquired:
                self._active = task_type
        if not acquired:
            raise HeavyTaskBusyError("heavy task queue wait timed out")
        try:
            result = callback()
            return result, queue_wait_ms
        finally:
            with self._state_lock:
                self._active = None
            self._slot.release()


heavy_task_queue = HeavyTaskQueue()
