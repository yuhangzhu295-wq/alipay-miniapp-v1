import ctypes
import json
import os
import time
from pathlib import Path

from PIL import ImageGrab


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "reports" / "alipay-visual-v3"
SCREENSHOT_DIR = REPORT_DIR / "screenshots" / "home"


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


user32 = ctypes.windll.user32
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
SWP_NOZORDER = 0x0004
SWP_SHOWWINDOW = 0x0040


def list_windows():
    windows = []

    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        rect = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        windows.append(
            {
                "hwnd": int(hwnd),
                "title": title.value,
                "rect": [rect.left, rect.top, rect.right, rect.bottom],
            }
        )
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return windows


def choose_alipay_window(windows):
    candidates = [
        item
        for item in windows
        if any(
            key.lower() in item["title"].lower()
            for key in ["alipay", "支付宝", "小程序开发者工具", "Mini Program Studio"]
        )
    ]
    candidates = [
        item
        for item in candidates
        if item["rect"][2] - item["rect"][0] > 600 and item["rect"][3] - item["rect"][1] > 500
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (item["rect"][2] - item["rect"][0]) * (item["rect"][3] - item["rect"][1]), reverse=True)[0]


def detect_phone_bbox(image):
    width, height = image.size
    pix = image.convert("RGB").load()
    y0 = int(height * 0.18)
    y1 = int(height * 0.88)
    dark_ranges = []
    start = None
    for x in range(int(width * 0.55), width - 10):
        count = 0
        total = 0
        for y in range(y0, y1, 4):
            r, g, b = pix[x, y]
            total += 1
            if r < 45 and g < 45 and b < 45:
                count += 1
        if total and count > total * 0.42:
            if start is None:
                start = x
        elif start is not None:
            dark_ranges.append((start, x - 1))
            start = None
    if start is not None:
        dark_ranges.append((start, width - 1))
    vertical_borders = [(a, b) for a, b in dark_ranges if b - a >= 8]
    for i, left_range in enumerate(vertical_borders):
        for right_range in vertical_borders[i + 1 :]:
            distance = right_range[0] - left_range[1]
            if 330 <= distance <= 620:
                left = left_range[0] - 20
                right = right_range[1] + 20
                top, bottom = detect_phone_vertical_bounds(image, left, right)
                return [max(0, left), max(0, top), min(width, right), min(height, bottom)]

    xs = []
    ys = []
    x_start = int(width * 0.58)
    for y in range(int(height * 0.12), int(height * 0.92), 3):
        for x in range(x_start, width - 20, 3):
            r, g, b = pix[x, y]
            if r < 45 and g < 45 and b < 45:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    if right - left < 250 or bottom - top < 500:
        return None
    return [max(0, left - 8), max(0, top - 8), min(width, right + 8), min(height, bottom + 8)]


def detect_phone_vertical_bounds(image, left, right):
    width, height = image.size
    pix = image.convert("RGB").load()
    x0 = max(0, left)
    x1 = min(width, right)
    rows = []
    start = None
    for y in range(int(height * 0.1), int(height * 0.94)):
        count = 0
        total = 0
        for x in range(x0, x1, 4):
            r, g, b = pix[x, y]
            total += 1
            if r < 50 and g < 50 and b < 50:
                count += 1
        if total and count > total * 0.08:
            if start is None:
                start = y
        elif start is not None:
            rows.append((start, y - 1))
            start = None
    if start is not None:
        rows.append((start, int(height * 0.94)))
    tall = [(a, b) for a, b in rows if b - a > 500]
    if tall:
        return sorted(tall, key=lambda item: item[1] - item[0], reverse=True)[0]
    return int(height * 0.16), int(height * 0.9)


def inner_phone_bbox(phone_bbox):
    left, top, right, bottom = phone_bbox
    w = right - left
    h = bottom - top
    return [
        left + int(w * 0.065),
        top + int(h * 0.035),
        right - int(w * 0.065),
        bottom - int(h * 0.035),
    ]


def detect_bright_screen_bbox(image):
    width, height = image.size
    pix = image.convert("RGB").load()
    y0 = int(height * 0.18)
    y1 = int(height * 0.9)
    threshold = int((y1 - y0) * 0.42)
    ranges = []
    start = None
    for x in range(int(width * 0.55), width - 10):
        count = 0
        for y in range(y0, y1, 4):
            r, g, b = pix[x, y]
            if r > 235 and g > 235 and b > 235:
                count += 1
        if count >= threshold:
            if start is None:
                start = x
        elif start is not None:
            ranges.append((start, x - 1))
            start = None
    if start is not None:
        ranges.append((start, width - 1))
    candidates = [(a, b) for a, b in ranges if 260 <= b - a <= 620]
    if not candidates:
        return None
    left, right = sorted(candidates, key=lambda item: item[1] - item[0], reverse=True)[0]

    x0 = left + 8
    x1 = right - 8
    row_ranges = []
    start_y = None
    threshold_x = int((x1 - x0) * 0.42)
    for y in range(int(height * 0.12), int(height * 0.94)):
        count = 0
        for x in range(x0, x1, 4):
            r, g, b = pix[x, y]
            if r > 235 and g > 235 and b > 235:
                count += 1
        if count >= threshold_x:
            if start_y is None:
                start_y = y
        elif start_y is not None:
            row_ranges.append((start_y, y - 1))
            start_y = None
    if start_y is not None:
        row_ranges.append((start_y, int(height * 0.94)))
    tall = [(a, b) for a, b in row_ranges if b - a > 400]
    if not tall:
        return None
    top, bottom = sorted(tall, key=lambda item: item[1] - item[0], reverse=True)[0]
    return [x0, top, x1, bottom]


def main():
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    windows = list_windows()
    target = choose_alipay_window(windows)
    if target:
        left, top, right, bottom = target["rect"]
        if left < 0 or top < 0:
            user32.SetWindowPos(
                target["hwnd"],
                0,
                180,
                120,
                right - left,
                bottom - top,
                SWP_NOZORDER | SWP_SHOWWINDOW,
            )
        user32.ShowWindow(target["hwnd"], 9)
        time.sleep(0.3)
        user32.SetForegroundWindow(target["hwnd"])
        time.sleep(1.0)

    full = ImageGrab.grab()
    full_path = SCREENSHOT_DIR / "iteration-002-full.png"
    full.save(full_path)

    # A generic desktop screenshot is not evidence of an Alipay simulator run.
    # Only attempt simulator-region detection after locating the Alipay IDE window.
    phone_bbox = detect_phone_bbox(full) if target else None
    bright_screen_bbox = detect_bright_screen_bbox(full) if target else None
    simulator_path = None
    inner_path = None
    if phone_bbox:
        simulator = full.crop(tuple(phone_bbox))
        simulator_path = SCREENSHOT_DIR / "iteration-002-simulator.png"
        simulator.save(simulator_path)
        inner_box = bright_screen_bbox or inner_phone_bbox(phone_bbox)
        inner = full.crop(tuple(inner_box))
        inner_path = SCREENSHOT_DIR / "iteration-002-business-area.png"
        inner.save(inner_path)

    metadata = {
        "capturedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "window": target,
        "fullScreenshot": str(full_path),
        "fullSize": list(full.size),
        "phoneBbox": phone_bbox,
        "brightScreenBbox": bright_screen_bbox,
        "simulatorScreenshot": str(simulator_path) if simulator_path else None,
        "businessAreaScreenshot": str(inner_path) if inner_path else None,
        "screenshotSource": "PIL.ImageGrab + Windows user32 foreground window",
    }
    meta_path = SCREENSHOT_DIR / "iteration-002-meta.json"
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
