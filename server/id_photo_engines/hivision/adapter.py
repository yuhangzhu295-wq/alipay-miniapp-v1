from pathlib import Path


def hivision_root() -> Path:
    return Path(__file__).resolve().parents[3] / "third_party" / "HivisionIDPhotos"


def hivision_available() -> tuple[bool, str]:
    root = hivision_root()
    if not root.exists():
        return False, "HivisionIDPhotos is not installed"
    if not (root / "inference.py").exists():
        return False, "inference.py not found"
    return True, "installed"


def hivision_runtime_ready() -> tuple[bool, str]:
    try:
        from .runner import production_ready

        return production_ready()
    except Exception as exc:
        return False, repr(exc)
