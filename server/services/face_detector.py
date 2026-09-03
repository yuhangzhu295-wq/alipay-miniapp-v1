"""Face detection helpers for ID-photo composition.

Uses MediaPipe Face Detection when available, with OpenCV Haar cascade as a
fallback so the 8000 service can still start if MediaPipe is unavailable.
"""
from io import BytesIO
import importlib.util
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps


_MP_FACE_DETECTOR = None
_MP_AVAILABLE = None


def get_face_detector_status():
    model_path = Path(__file__).resolve().parents[1] / "models" / "blaze_face_short_range.tflite"
    mediapipe_importable = importlib.util.find_spec("mediapipe") is not None
    return {
        "success": True,
        "mediapipeImportable": mediapipe_importable,
        "mediapipeModelPath": str(model_path),
        "mediapipeModelExists": model_path.exists(),
        "mediapipeAvailable": bool(_MP_AVAILABLE) if _MP_AVAILABLE is not None else None,
        "opencvAvailable": True,
        "fallbackEngines": ["opencv", "classifier_quality_facebox"],
        "defaultEngine": "mediapipe" if mediapipe_importable and model_path.exists() and _MP_AVAILABLE is not False else "opencv",
        "fallbackUsedByDefault": not (mediapipe_importable and model_path.exists() and _MP_AVAILABLE is not False),
    }


def _load_rgb(image_input):
    if isinstance(image_input, bytes):
        image = Image.open(BytesIO(image_input))
    else:
        image = Image.open(image_input)
    image = ImageOps.exif_transpose(image).convert("RGB")
    return np.asarray(image), image.size


def _mediapipe_detector():
    global _MP_AVAILABLE, _MP_FACE_DETECTOR
    if _MP_AVAILABLE is False:
        return None
    if _MP_FACE_DETECTOR is not None:
        return _MP_FACE_DETECTOR
    try:
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision

        model_path = Path(__file__).resolve().parents[1] / "models" / "blaze_face_short_range.tflite"
        if not model_path.exists():
            raise FileNotFoundError(f"MediaPipe face model missing: {model_path}")
        model_bytes = model_path.read_bytes()
        options = vision.FaceDetectorOptions(
            base_options=python.BaseOptions(model_asset_buffer=model_bytes),
            min_detection_confidence=0.55,
        )
        _MP_FACE_DETECTOR = vision.FaceDetector.create_from_options(options)
        _MP_AVAILABLE = True
        print(f"[id-photo] MediaPipe face detector ready model={model_path.name}", flush=True)
        return _MP_FACE_DETECTOR
    except Exception as exc:
        _MP_AVAILABLE = False
        print(f"[id-photo] MediaPipe unavailable, fallback OpenCV: {exc}", flush=True)
        return None


def _detect_with_mediapipe(rgb):
    detector = _mediapipe_detector()
    if detector is None:
        return []
    h, w = rgb.shape[:2]
    import mediapipe as mp

    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = detector.detect(mp_image)
    detections = []
    for det in result.detections or []:
        box = det.bounding_box
        x = max(0, int(box.origin_x))
        y = max(0, int(box.origin_y))
        bw = min(w - x, int(box.width))
        bh = min(h - y, int(box.height))
        landmarks = {}
        labels = ["rightEye", "leftEye", "nose", "mouth", "rightEar", "leftEar"]
        for label, kp in zip(labels, det.keypoints or []):
            landmarks[label] = {"x": float(kp.x * w), "y": float(kp.y * h)}
        detections.append({
            "faceBox": {"x": x, "y": y, "width": max(1, bw), "height": max(1, bh)},
            "landmarks": landmarks,
            "confidence": float(det.categories[0].score) if det.categories else 0.0,
            "engine": "mediapipe",
        })
    detections.sort(key=lambda item: item["faceBox"]["width"] * item["faceBox"]["height"], reverse=True)
    return detections


def _build_detection(x, y, w, h, confidence, engine):
    return {
        "faceBox": {"x": int(x), "y": int(y), "width": int(w), "height": int(h)},
        "landmarks": {
            "leftEye": {"x": float(x + w * 0.35), "y": float(y + h * 0.42)},
            "rightEye": {"x": float(x + w * 0.65), "y": float(y + h * 0.42)},
            "nose": {"x": float(x + w * 0.50), "y": float(y + h * 0.58)},
            "mouth": {"x": float(x + w * 0.50), "y": float(y + h * 0.76)},
        },
        "confidence": float(confidence),
        "engine": engine,
    }


def _merge_faces(faces):
    merged = []
    for face in faces:
        x, y, w, h = [int(v) for v in face]
        keep = True
        for existing in merged:
            ex, ey, ew, eh = existing
            ix1, iy1 = max(x, ex), max(y, ey)
            ix2, iy2 = min(x + w, ex + ew), min(y + h, ey + eh)
            inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
            union = w * h + ew * eh - inter
            if union and inter / union > 0.35:
                keep = False
                if w * h > ew * eh:
                    existing[:] = [x, y, w, h]
                break
        if keep:
            merged.append([x, y, w, h])
    return merged


def _detect_with_opencv(rgb):
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gray_eq = cv2.equalizeHist(gray)
    min_side = min(gray.shape[:2])
    min_size = max(28, int(min_side * 0.07))
    cascade_names = [
        "haarcascade_frontalface_default.xml",
        "haarcascade_frontalface_alt2.xml",
    ]
    scan_passes = [
        (gray_eq, 1.08, 5, 0.72, "opencv"),
        (gray_eq, 1.05, 4, 0.66, "opencv_relaxed"),
        (gray, 1.04, 3, 0.61, "opencv_relaxed"),
    ]
    raw_faces = []
    engine = "opencv"
    confidence = 0.72
    for scan_gray, scale, neighbors, conf, pass_engine in scan_passes:
        for name in cascade_names:
            detector = cv2.CascadeClassifier(cv2.data.haarcascades + name)
            if detector.empty():
                continue
            detected = detector.detectMultiScale(
                scan_gray,
                scaleFactor=scale,
                minNeighbors=neighbors,
                minSize=(min_size, min_size),
                flags=cv2.CASCADE_SCALE_IMAGE,
            )
            if len(detected):
                raw_faces.extend(detected)
        if raw_faces:
            engine = pass_engine
            confidence = conf
            break
    faces = _merge_faces(raw_faces)
    detections = []
    for x, y, w, h in faces:
        detections.append(_build_detection(x, y, w, h, confidence, engine))
    detections.sort(key=lambda item: item["faceBox"]["width"] * item["faceBox"]["height"], reverse=True)
    return detections


def _detect_from_classifier_quality(classifier_quality, image_width, image_height):
    if not isinstance(classifier_quality, dict):
        return []
    if classifier_quality.get("imageType") != "real_person":
        return []
    if not classifier_quality.get("realPerson"):
        return []
    if not classifier_quality.get("faceDetected") or not classifier_quality.get("singlePerson"):
        return []
    if int(classifier_quality.get("faceCount") or 0) != 1:
        return []
    box = classifier_quality.get("faceBox")
    if not isinstance(box, dict):
        return []
    try:
        x = int(box.get("x"))
        y = int(box.get("y"))
        w = int(box.get("width"))
        h = int(box.get("height"))
    except Exception:
        return []
    if w <= 0 or h <= 0:
        return []
    x = max(0, min(image_width - 1, x))
    y = max(0, min(image_height - 1, y))
    w = max(1, min(image_width - x, w))
    h = max(1, min(image_height - y, h))
    confidence = float(classifier_quality.get("faceConfidence") or 0.63)
    return [_build_detection(x, y, w, h, max(0.6, confidence), "classifier_quality_facebox")]


def _measure_frontal_pose(landmarks):
    """Estimate frontal pose from detector landmarks without sample-specific rules."""
    if not isinstance(landmarks, dict):
        return {
            "frontalPoseMeasured": False,
            "frontalPosePass": None,
            "poseScore": 0.0,
        }

    right_eye = landmarks.get("rightEye")
    left_eye = landmarks.get("leftEye")
    nose = landmarks.get("nose")
    if not all(isinstance(point, dict) for point in (right_eye, left_eye, nose)):
        return {
            "frontalPoseMeasured": False,
            "frontalPosePass": None,
            "poseScore": 0.0,
        }

    try:
        eye_dx = float(left_eye["x"]) - float(right_eye["x"])
        eye_dy = float(left_eye["y"]) - float(right_eye["y"])
        eye_distance = float(np.hypot(eye_dx, eye_dy))
        if eye_distance < 1.0:
            raise ValueError("eye landmarks overlap")
        eye_mid_x = (float(right_eye["x"]) + float(left_eye["x"])) / 2.0
        yaw_ratio = abs(float(nose["x"]) - eye_mid_x) / eye_distance
        roll_ratio = abs(eye_dy) / eye_distance

        ear_balance_ratio = None
        right_ear = landmarks.get("rightEar")
        left_ear = landmarks.get("leftEar")
        if isinstance(right_ear, dict) and isinstance(left_ear, dict):
            right_span = float(nose["x"]) - float(right_ear["x"])
            left_span = float(left_ear["x"]) - float(nose["x"])
            if right_span > 0.0 and left_span > 0.0:
                ear_balance_ratio = abs(right_span - left_span) / eye_distance

        yaw_pass = yaw_ratio <= 0.18
        roll_pass = roll_ratio <= 0.14
        ear_pass = ear_balance_ratio is None or ear_balance_ratio <= 0.65
        normalized_error = min(1.0, yaw_ratio / 0.56) * 0.65 + min(1.0, roll_ratio / 0.36) * 0.20
        if ear_balance_ratio is not None:
            normalized_error += min(1.0, ear_balance_ratio / 1.70) * 0.15
        pose_score = max(0.0, 1.0 - normalized_error)
        frontal_pass = bool(yaw_pass and roll_pass and ear_pass and pose_score >= 0.68)
        return {
            "frontalPoseMeasured": True,
            "frontalPosePass": frontal_pass,
            "poseScore": round(pose_score, 4),
            "poseYawRatio": round(yaw_ratio, 6),
            "poseRollRatio": round(roll_ratio, 6),
            "poseEarBalanceRatio": round(ear_balance_ratio, 6) if ear_balance_ratio is not None else None,
        }
    except (KeyError, TypeError, ValueError):
        return {
            "frontalPoseMeasured": False,
            "frontalPosePass": None,
            "poseScore": 0.0,
        }


def detect_face(image_input, classifier_quality=None):
    rgb, (w, h) = _load_rgb(image_input)
    detections = _detect_with_mediapipe(rgb)
    if not detections:
        detections = _detect_with_opencv(rgb)
    if not detections:
        detections = _detect_from_classifier_quality(classifier_quality, w, h)

    if not detections:
        return {
            "success": False,
            "code": "FACE_NOT_FOUND",
            "message": "请上传清晰的真人正面照片。",
            "faceCount": 0,
            "imageSize": f"{w}x{h}",
        }

    main = detections[0]
    main_area = main["faceBox"]["width"] * main["faceBox"]["height"]
    large_faces = [
        item for item in detections
        if item["faceBox"]["width"] * item["faceBox"]["height"] > main_area * 0.38
    ]
    if len(large_faces) > 1:
        return {
            "success": False,
            "code": "MULTIPLE_FACES",
            "message": "检测到多个人脸，请上传单人照片。",
            "faceCount": len(large_faces),
            "imageSize": f"{w}x{h}",
        }

    face = main["faceBox"]
    if face["height"] / float(max(1, h)) < 0.055:
        return {
            "success": False,
            "code": "FACE_TOO_SMALL",
            "message": "请上传清晰的真人正面照片。",
            "faceCount": 1,
            "imageSize": f"{w}x{h}",
        }

    pose = _measure_frontal_pose(main.get("landmarks", {}))
    return {
        "success": True,
        "faceBox": face,
        "faceCenter": {
            "x": round(face["x"] + face["width"] / 2.0, 3),
            "y": round(face["y"] + face["height"] / 2.0, 3),
        },
        "landmarks": main.get("landmarks", {}),
        "faceCount": 1,
        "confidence": round(main.get("confidence", 0.0), 4),
        **pose,
        "engine": main.get("engine", "unknown"),
        "imageSize": f"{w}x{h}",
    }
