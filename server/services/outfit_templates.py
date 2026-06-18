"""职业形象照 / 证件照服装模板注册表。"""

TEMPLATE_TYPE_REAL = ["real_person"]
TEMPLATE_TYPE_ANIME = ["anime", "cartoon", "illustration"]
TEMPLATE_TYPE_ALL = TEMPLATE_TYPE_REAL + TEMPLATE_TYPE_ANIME
ADVANCED_OUTFIT_ENABLED = True
EXPERIMENTAL_DISABLED_REASON = "当前模板为实验贴图效果，暂不开放正式使用"
PRODUCTION_OUTFIT_IDS = {
    "preserve_original",
    "mist_gray_suit",
    "elegant_black_suit",
    "deep_blue_suit",
    "red_tie_suit",
    "pure_black_suit",
    "white_shirt",
    "business_blue",
    "mens_black_suit",
    "womens_black_suit",
    "student_uniform",
}

COMMON_PURPOSES = [
    "official_id_photo",
    "resume",
    "career_portrait",
    "creative_id_photo",
]
REAL_PURPOSES = COMMON_PURPOSES + [
    "id_card",
    "social_security",
    "passport",
    "teacher_exam",
    "civil_service_exam",
]
ANIME_PURPOSES = ["anime_avatar", "creative_id_photo", "resume", "career_portrait"]
COMPOSITIONS = ["head_shoulder", "shoulder_avatar", "half_body", "square_avatar"]

OUTFIT_ALIASES = {
    "": "preserve_original",
    "keep": "preserve_original",
    "preserve_original": "preserve_original",
    "blueSuit": "business_blue",
    "business_blue": "business_blue",
    "blackSuit": "mens_black_suit",
    "mens_black_suit": "mens_black_suit",
    "whiteShirt": "white_shirt",
    "white_shirt": "white_shirt",
    "studentUniform": "student_uniform",
    "student_uniform": "student_uniform",
    "animeBusiness": "anime_business",
    "anime_business": "anime_business",
    "animeSchool": "anime_school_uniform",
    "anime_school_uniform": "anime_school_uniform",
    "animeSuit": "anime_suit",
    "anime_suit": "anime_suit",
    "no_outfit": "preserve_original",
    "none": "preserve_original",
    "mistGraySuit": "mist_gray_suit",
    "mist_gray_suit": "mist_gray_suit",
    "light_suit": "mist_gray_suit",
    "elegantBlackSuit": "elegant_black_suit",
    "elegant_black_suit": "elegant_black_suit",
    "deepBlueSuit": "deep_blue_suit",
    "deep_blue_suit": "deep_blue_suit",
    "redTieSuit": "red_tie_suit",
    "red_tie_suit": "red_tie_suit",
    "pureBlackSuit": "pure_black_suit",
    "pure_black_suit": "pure_black_suit",
}

OUTFIT_TEMPLATES = [
    {
        "id": "preserve_original",
        "name": "无服装",
        "category": "base",
        "supportedImageTypes": TEMPLATE_TYPE_ALL,
        "supportedPurposes": REAL_PURPOSES + ANIME_PURPOSES,
        "available": True,
        "fallback": "preserve_original",
        "compositionSupport": COMPOSITIONS,
        "description": "不换装，仅执行抠图、换背景和裁切。",
        "anchor": {"neckX": 0.5, "neckY": 0.18, "collarTopY": 0.12, "shoulderLeftX": 0.12, "shoulderRightX": 0.88, "shoulderY": 0.32},
    },
    {
        "id": "white_shirt",
        "name": "白衬衫",
        "category": "real",
        "supportedImageTypes": TEMPLATE_TYPE_REAL,
        "supportedPurposes": REAL_PURPOSES,
        "available": True,
        "fallback": "preserve_original",
        "compositionSupport": COMPOSITIONS,
        "description": "真人白衬衫模板。",
        "anchor": {"neckX": 0.5, "neckY": 0.16, "collarTopY": 0.11, "shoulderLeftX": 0.10, "shoulderRightX": 0.90, "shoulderY": 0.34},
    },
    {
        "id": "business_blue",
        "name": "商务蓝",
        "category": "real",
        "supportedImageTypes": TEMPLATE_TYPE_REAL,
        "supportedPurposes": REAL_PURPOSES,
        "available": True,
        "fallback": "preserve_original",
        "compositionSupport": COMPOSITIONS,
        "description": "真人蓝色商务正装模板。",
        "anchor": {"neckX": 0.5, "neckY": 0.16, "collarTopY": 0.11, "shoulderLeftX": 0.10, "shoulderRightX": 0.90, "shoulderY": 0.34},
    },
    {
        "id": "mens_black_suit",
        "name": "男士黑西装",
        "category": "real",
        "supportedImageTypes": TEMPLATE_TYPE_REAL,
        "supportedPurposes": REAL_PURPOSES,
        "available": True,
        "fallback": "preserve_original",
        "compositionSupport": COMPOSITIONS,
        "description": "真人黑西装、白衬衫、领带模板。",
        "anchor": {"neckX": 0.5, "neckY": 0.16, "collarTopY": 0.11, "shoulderLeftX": 0.10, "shoulderRightX": 0.90, "shoulderY": 0.34},
    },
    {
        "id": "womens_black_suit",
        "name": "女士黑西装",
        "category": "real",
        "supportedImageTypes": TEMPLATE_TYPE_REAL,
        "supportedPurposes": REAL_PURPOSES,
        "available": True,
        "fallback": "preserve_original",
        "compositionSupport": COMPOSITIONS,
        "description": "真人女士黑西装模板。",
        "anchor": {"neckX": 0.5, "neckY": 0.16, "collarTopY": 0.11, "shoulderLeftX": 0.10, "shoulderRightX": 0.90, "shoulderY": 0.34},
    },
    {
        "id": "student_uniform",
        "name": "学生制服",
        "category": "real",
        "supportedImageTypes": TEMPLATE_TYPE_REAL,
        "supportedPurposes": REAL_PURPOSES,
        "available": True,
        "fallback": "preserve_original",
        "compositionSupport": COMPOSITIONS,
        "description": "真人学生制服模板。",
        "anchor": {"neckX": 0.5, "neckY": 0.17, "collarTopY": 0.12, "shoulderLeftX": 0.10, "shoulderRightX": 0.90, "shoulderY": 0.35},
    },
    {
        "id": "light_suit",
        "name": "浅灰西装",
        "category": "real",
        "supportedImageTypes": TEMPLATE_TYPE_REAL,
        "supportedPurposes": REAL_PURPOSES,
        "available": False,
        "reason": "模板素材未接入",
        "fallback": "preserve_original",
        "compositionSupport": COMPOSITIONS,
        "description": "浅灰西装模板，后续接入。",
    },
    {
        "id": "mist_gray_suit",
        "name": "雾灰正装",
        "category": "real",
        "supportedImageTypes": TEMPLATE_TYPE_REAL,
        "supportedPurposes": REAL_PURPOSES,
        "available": True,
        "fallback": "preserve_original",
        "compositionSupport": COMPOSITIONS,
        "description": "真实自然的浅灰正装模板，贴合颈部并保持原证件照构图。",
        "anchor": {"neckX": 0.5, "neckY": 0.16, "collarTopY": 0.11, "shoulderLeftX": 0.10, "shoulderRightX": 0.90, "shoulderY": 0.34},
    },
    {
        "id": "elegant_black_suit",
        "name": "雅黑西装",
        "category": "real",
        "supportedImageTypes": TEMPLATE_TYPE_REAL,
        "supportedPurposes": REAL_PURPOSES,
        "available": True,
        "fallback": "preserve_original",
        "compositionSupport": COMPOSITIONS,
        "description": "雅黑西装模板，适合正式证件照和职业形象照。",
        "anchor": {"neckX": 0.5, "neckY": 0.16, "collarTopY": 0.11, "shoulderLeftX": 0.10, "shoulderRightX": 0.90, "shoulderY": 0.34},
    },
    {
        "id": "deep_blue_suit",
        "name": "深蓝西装",
        "category": "real",
        "supportedImageTypes": TEMPLATE_TYPE_REAL,
        "supportedPurposes": REAL_PURPOSES,
        "available": True,
        "fallback": "preserve_original",
        "compositionSupport": COMPOSITIONS,
        "description": "深蓝西装模板，保持肩宽和领口位置稳定。",
        "anchor": {"neckX": 0.5, "neckY": 0.16, "collarTopY": 0.11, "shoulderLeftX": 0.10, "shoulderRightX": 0.90, "shoulderY": 0.34},
    },
    {
        "id": "red_tie_suit",
        "name": "红领西装",
        "category": "real",
        "supportedImageTypes": TEMPLATE_TYPE_REAL,
        "supportedPurposes": REAL_PURPOSES,
        "available": True,
        "fallback": "preserve_original",
        "compositionSupport": COMPOSITIONS,
        "description": "黑色西装配红色领带模板，适合正式报名照。",
        "anchor": {"neckX": 0.5, "neckY": 0.16, "collarTopY": 0.11, "shoulderLeftX": 0.10, "shoulderRightX": 0.90, "shoulderY": 0.34},
    },
    {
        "id": "pure_black_suit",
        "name": "纯黑西装",
        "category": "real",
        "supportedImageTypes": TEMPLATE_TYPE_REAL,
        "supportedPurposes": REAL_PURPOSES,
        "available": True,
        "fallback": "preserve_original",
        "compositionSupport": COMPOSITIONS,
        "description": "纯黑西装模板，适合通用证件照。",
        "anchor": {"neckX": 0.5, "neckY": 0.16, "collarTopY": 0.11, "shoulderLeftX": 0.10, "shoulderRightX": 0.90, "shoulderY": 0.34},
    },
    {
        "id": "anime_business",
        "name": "二次元商务装",
        "category": "anime",
        "supportedImageTypes": TEMPLATE_TYPE_ANIME,
        "supportedPurposes": ANIME_PURPOSES,
        "available": True,
        "fallback": "preserve_original",
        "compositionSupport": COMPOSITIONS,
        "description": "二次元商务装模板。",
        "anchor": {"neckX": 0.5, "neckY": 0.18, "collarTopY": 0.13, "shoulderLeftX": 0.08, "shoulderRightX": 0.92, "shoulderY": 0.36},
    },
    {
        "id": "anime_school_uniform",
        "name": "二次元校服",
        "category": "anime",
        "supportedImageTypes": TEMPLATE_TYPE_ANIME,
        "supportedPurposes": ANIME_PURPOSES,
        "available": False,
        "reason": "模板素材未接入",
        "fallback": "anime_business",
        "compositionSupport": COMPOSITIONS,
        "description": "二次元校服模板，后续接入。",
    },
    {
        "id": "anime_suit",
        "name": "二次元西装风格",
        "category": "anime",
        "supportedImageTypes": TEMPLATE_TYPE_ANIME,
        "supportedPurposes": ANIME_PURPOSES,
        "available": True,
        "fallback": "anime_business",
        "compositionSupport": COMPOSITIONS,
        "description": "二次元西装模板。",
        "anchor": {"neckX": 0.5, "neckY": 0.18, "collarTopY": 0.13, "shoulderLeftX": 0.08, "shoulderRightX": 0.92, "shoulderY": 0.36},
    },
    {
        "id": "anime_western",
        "name": "二次元西式制服",
        "category": "anime",
        "supportedImageTypes": TEMPLATE_TYPE_ANIME,
        "supportedPurposes": ANIME_PURPOSES,
        "available": False,
        "reason": "模板素材未接入",
        "fallback": "anime_business",
        "compositionSupport": COMPOSITIONS,
        "description": "二次元西式制服模板，后续接入。",
    },
    {
        "id": "anime_white_shirt",
        "name": "二次元白衬衫",
        "category": "anime",
        "supportedImageTypes": TEMPLATE_TYPE_ANIME,
        "supportedPurposes": ANIME_PURPOSES,
        "available": False,
        "reason": "模板素材未接入",
        "fallback": "anime_business",
        "compositionSupport": COMPOSITIONS,
        "description": "二次元白衬衫模板，后续接入。",
    },
    {
        "id": "creative_blue_suit",
        "name": "创意蓝色正装",
        "category": "creative",
        "supportedImageTypes": TEMPLATE_TYPE_ALL,
        "supportedPurposes": ["creative_id_photo"],
        "available": False,
        "reason": "模板素材未接入",
        "fallback": "preserve_original",
        "compositionSupport": COMPOSITIONS,
        "description": "创意正装模板，后续接入。",
    },
    {
        "id": "creative_school",
        "name": "创意学院风",
        "category": "creative",
        "supportedImageTypes": TEMPLATE_TYPE_ALL,
        "supportedPurposes": ["creative_id_photo"],
        "available": False,
        "reason": "模板素材未接入",
        "fallback": "preserve_original",
        "compositionSupport": COMPOSITIONS,
        "description": "创意学院风模板，后续接入。",
    },
]

for item in OUTFIT_TEMPLATES:
    if item["id"] in PRODUCTION_OUTFIT_IDS:
        item["available"] = True
        item["qualityLevel"] = "production"
        item["disabledReason"] = ""
    else:
        item["available"] = False
        item["qualityLevel"] = "experimental"
        item["reason"] = EXPERIMENTAL_DISABLED_REASON
        item["disabledReason"] = EXPERIMENTAL_DISABLED_REASON
        item["description"] = (item.get("description") or "") + " 实验功能，暂未开放。"


def normalize_outfit(outfit):
    return OUTFIT_ALIASES.get(outfit or "", "preserve_original")


def list_templates():
    return [dict(item) for item in OUTFIT_TEMPLATES]


def get_template(outfit):
    template_id = normalize_outfit(outfit)
    for item in OUTFIT_TEMPLATES:
        if item["id"] == template_id:
            return dict(item)
    return None
