from pathlib import Path
import sys

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))

from id_photo_engine_legacy.id_photo_composer import _extend_small_lower_panel_gaps


WIDTH = 295
HEIGHT = 413
FACE_BOX = {"x": 65, "y": 132, "width": 165, "height": 165}


def make_panel(left, right):
    layer = np.zeros((HEIGHT, WIDTH, 4), dtype=np.uint8)
    layer[330:, left:right, :3] = (25, 30, 38)
    layer[330:, left:right, 3] = 255
    background = np.full((HEIGHT, WIDTH, 3), (26, 115, 232), dtype=np.uint8)
    background[layer[:, :, 3] > 0] = layer[:, :, :3][layer[:, :, 3] > 0]
    return Image.fromarray(background, "RGB"), Image.fromarray(layer, "RGBA")


def gaps(layer):
    alpha = np.asarray(layer.getchannel("A"))
    ys, xs = np.where(alpha[330:] > 48)
    if not xs.size:
        return WIDTH, WIDTH
    return int(xs.min()), int(WIDTH - (xs.max() + 1))


def run_case(name, left, right, expected_before, expected_after, should_change):
    result, layer = make_panel(left, right)
    before = gaps(layer)
    _, repaired, metrics = _extend_small_lower_panel_gaps(result, layer, FACE_BOX)
    after = gaps(repaired)
    assert before == expected_before, (name, before, expected_before)
    assert after == expected_after, (name, after, expected_after)
    assert (metrics["lowerPanelContactExtendedPixels"] > 0) is should_change, (name, metrics)
    print(f"PASS {name}: before={before} after={after} metrics={metrics}")


def main():
    run_case("right-small-gap", 0, 283, (0, 12), (0, 0), True)
    run_case("left-small-gap", 10, WIDTH, (10, 0), (0, 0), True)
    run_case("two-small-gaps", 8, 285, (8, 10), (0, 0), True)
    run_case("large-gap-preserved", 0, 270, (0, 25), (0, 25), False)
    run_case("narrow-subject-preserved", 60, 235, (60, 60), (60, 60), False)
    run_case("already-contacting", 0, WIDTH, (0, 0), (0, 0), False)
    print("panel-contact repair: 6/6 PASS")


if __name__ == "__main__":
    main()
