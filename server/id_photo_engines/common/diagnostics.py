import inspect
import sys
from pathlib import Path


def module_path(module) -> str:
    try:
        return str(Path(inspect.getfile(module)).resolve())
    except Exception:
        return ""


def python_path() -> str:
    return sys.executable

