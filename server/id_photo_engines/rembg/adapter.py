from services.portrait_matting import matting_status


def rembg_available() -> tuple[bool, str, str]:
    status = matting_status()
    model = status.get("rembgModel") or "u2net_human_seg"
    if status.get("rembgAvailable"):
        return True, str(model), "available"
    return False, str(model), status.get("rembgError") or "rembg unavailable"

