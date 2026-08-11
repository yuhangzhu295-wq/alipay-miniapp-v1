"""证件照 / 职业形象照规格库。"""

BG_COLORS = {
    "blue": "#1a73e8",
    "white": "#ffffff",
    "red": "#e53935",
    "lightBlue": "#81d4fa",
    "gray": "#9e9e9e",
    "darkBlue": "#0b3d91",
}


def _composition_profile(**values):
    profile = {
        "standardRef": "",
        "sourceType": "",
        "headWidthRatioMin": None,
        "headWidthRatioMax": None,
        "headHeightRatioMin": None,
        "headHeightRatioMax": None,
        "topMarginRatioMin": None,
        "topMarginRatioMax": None,
        "chinBottomRatioMin": None,
        "chinBottomRatioMax": None,
        "shoulderWidthRatioMin": None,
        "shoulderWidthRatioMax": None,
        "headHeightRatioTarget": None,
        "operationalHeadHeightRatioMax": None,
        "topMarginRatioTarget": None,
        "chinBottomRatioTarget": None,
        "shoulderWidthRatioTarget": None,
        "topGapRatioMin": None,
        "topGapRatioMax": None,
        "topGapRatioTarget": None,
        "chinYRatioMin": None,
        "chinYRatioMax": None,
        "chinYRatioTarget": None,
        "horizontalCenterErrorMax": None,
        "shoulderSpanRatioSoftMin": None,
        "shoulderSpanRatioSoftMax": None,
        "foregroundBottomContact": True,
        "shoulderSideContact": True,
        "backgroundPolicy": "",
        "headwearPolicy": "",
    }
    profile.update(values)
    return profile


PROJECT_COMMON_PROFILE = _composition_profile(
    sourceType="project_common_profile",
    headHeightRatioMin=0.60,
    headHeightRatioMax=0.67,
    headHeightRatioTarget=0.63,
    topGapRatioMin=0.04,
    topGapRatioMax=0.08,
    topGapRatioTarget=0.055,
    chinYRatioMin=0.65,
    chinYRatioMax=0.74,
    chinYRatioTarget=0.685,
    shoulderSpanRatioSoftMin=0.82,
    shoulderSpanRatioSoftMax=1.00,
    shoulderWidthRatioTarget=0.90,
    horizontalCenterErrorMax=0.015,
)

PHOTO_SPECS = {
    "one-inch": {
        "id": "one-inch",
        "name": "一寸照",
        "category": "common",
        "width": 295,
        "height": 413,
        "widthMm": 25,
        "heightMm": 35,
        "defaultBg": "blue",
        "composition": "head_shoulder",
        "mode": "official",
        "compositionProfile": dict(PROJECT_COMMON_PROFILE),
    },
    "two-inch": {
        "id": "two-inch",
        "name": "二寸照",
        "category": "common",
        "width": 413,
        "height": 579,
        "widthMm": 35,
        "heightMm": 49,
        "defaultBg": "blue",
        "composition": "head_shoulder",
        "mode": "official",
    },
    "small-one-inch": {
        "id": "small-one-inch",
        "name": "小一寸",
        "category": "common",
        "width": 260,
        "height": 378,
        "widthMm": 22,
        "heightMm": 32,
        "defaultBg": "blue",
        "composition": "head_shoulder",
        "mode": "official",
    },
    "large-one-inch": {
        "id": "large-one-inch",
        "name": "大一寸",
        "category": "common",
        "width": 390,
        "height": 567,
        "widthMm": 33,
        "heightMm": 48,
        "defaultBg": "blue",
        "composition": "head_shoulder",
        "mode": "official",
    },
    "small-two-inch": {
        "id": "small-two-inch",
        "name": "小二寸",
        "category": "common",
        "width": 413,
        "height": 531,
        "widthMm": 35,
        "heightMm": 45,
        "defaultBg": "blue",
        "composition": "head_shoulder",
        "mode": "official",
    },
    "large-two-inch": {
        "id": "large-two-inch",
        "name": "大二寸",
        "category": "common",
        "width": 413,
        "height": 626,
        "widthMm": 35,
        "heightMm": 53,
        "defaultBg": "blue",
        "composition": "head_shoulder",
        "mode": "official",
    },
    "id-card-cn": {
        "id": "id-card-cn",
        "name": "二代身份证数码照",
        "category": "id_card",
        "width": 358,
        "height": 441,
        "dpi": 350,
        "defaultBg": "white",
        "format": "JPEG",
        "composition": "head_shoulder",
        "mode": "official",
        "note": "24位RGB，正面免冠，露双肩。",
        "compositionProfile": _composition_profile(
            standardRef="GA/T 461-2019",
            sourceType="official",
            operationalHeadHeightRatioMax=0.75,
            backgroundPolicy="white_only",
            headwearPolicy="no_headwear",
        ),
    },
    "social-security-cn": {
        "id": "social-security-cn",
        "name": "社保卡数码照",
        "category": "social_security",
        "width": 358,
        "height": 441,
        "dpi": 350,
        "defaultBg": "white",
        "composition": "head_shoulder",
        "mode": "official",
    },
    "passport-cn": {
        "id": "passport-cn",
        "name": "普通护照照片",
        "category": "passport",
        "width": 390,
        "height": 567,
        "widthMm": 33,
        "heightMm": 48,
        "defaultBg": "white",
        "composition": "head_shoulder",
        "mode": "official",
        "compositionProfile": _composition_profile(
            standardRef="GA/T 1180-2014及现行护照办证要求",
            sourceType="official",
            headWidthRatioMin=15 / 33,
            headWidthRatioMax=22 / 33,
            headHeightRatioMin=28 / 48,
            headHeightRatioMax=33 / 48,
            topMarginRatioMin=3 / 48,
            topMarginRatioMax=5 / 48,
            chinBottomRatioMin=7 / 48,
            backgroundPolicy="white_only",
            headwearPolicy="no_headwear",
        ),
    },
    "driver-license-cn": {
        "id": "driver-license-cn",
        "name": "机动车驾驶证相片",
        "category": "driver_license",
        "width": 260,
        "height": 378,
        "widthMm": 22,
        "heightMm": 32,
        "defaultBg": "white",
        "composition": "head_shoulder",
        "mode": "official",
        "compositionProfile": _composition_profile(
            standardRef="公安交管部门现行机动车驾驶证办证要求",
            sourceType="official",
            headWidthRatioMin=14 / 22,
            headWidthRatioMax=16 / 22,
            headHeightRatioMin=19 / 32,
            headHeightRatioMax=22 / 32,
            backgroundPolicy="white_only",
            headwearPolicy="no_headwear",
        ),
    },
    "exit-entry-cn": {
        "id": "exit-entry-cn",
        "name": "港澳通行证/出入境证件",
        "category": "passport",
        "width": 390,
        "height": 567,
        "defaultBg": "lightBlue",
        "composition": "head_shoulder",
        "mode": "official",
    },
    "teacher-exam": {
        "id": "teacher-exam",
        "name": "教师资格证报名照",
        "category": "exam",
        "width": 295,
        "height": 413,
        "defaultBg": "white",
        "format": "JPG/JPEG",
        "maxKb": 200,
        "composition": "head_shoulder",
        "mode": "official",
        "compositionProfile": _composition_profile(sourceType="platform_profile"),
    },
    "civil-service-exam": {
        "id": "civil-service-exam",
        "name": "公务员考试报名照",
        "category": "exam",
        "width": 413,
        "height": 531,
        "defaultBg": "blue",
        "composition": "head_shoulder",
        "mode": "official",
        "compositionProfile": _composition_profile(sourceType="platform_profile"),
    },
    "postgraduate-exam": {
        "id": "postgraduate-exam",
        "name": "研究生考试报名照",
        "category": "exam",
        "width": 390,
        "height": 567,
        "defaultBg": "white",
        "composition": "head_shoulder",
        "mode": "official",
        "compositionProfile": _composition_profile(sourceType="platform_profile"),
    },
    "cet-exam": {
        "id": "cet-exam",
        "name": "英语四六级报名照",
        "category": "exam",
        "width": 390,
        "height": 567,
        "defaultBg": "blue",
        "composition": "head_shoulder",
        "mode": "official",
        "compositionProfile": _composition_profile(sourceType="platform_profile"),
    },
    "computer-exam": {
        "id": "computer-exam",
        "name": "计算机等级考试报名照",
        "category": "exam",
        "width": 390,
        "height": 567,
        "defaultBg": "blue",
        "composition": "head_shoulder",
        "mode": "official",
        "compositionProfile": _composition_profile(sourceType="platform_profile"),
    },
    "resume-headshot": {
        "id": "resume-headshot",
        "name": "简历头像",
        "category": "resume",
        "width": 295,
        "height": 413,
        "defaultBg": "gray",
        "composition": "head_shoulder",
        "mode": "creative",
    },
    "career-headshot": {
        "id": "career-headshot",
        "name": "职业形象照",
        "category": "career",
        "width": 413,
        "height": 579,
        "defaultBg": "blue",
        "composition": "head_shoulder",
        "mode": "creative",
    },
    "career-half-body": {
        "id": "career-half-body",
        "name": "半身职业照",
        "category": "career",
        "width": 413,
        "height": 579,
        "defaultBg": "blue",
        "composition": "half_body",
        "mode": "creative",
    },
    "anime-blue-headshot": {
        "id": "anime-blue-headshot",
        "name": "二次元蓝底头像照",
        "category": "anime",
        "width": 295,
        "height": 413,
        "defaultBg": "blue",
        "composition": "head_shoulder",
        "mode": "anime",
    },
    "anime-white-headshot": {
        "id": "anime-white-headshot",
        "name": "二次元白底头像照",
        "category": "anime",
        "width": 295,
        "height": 413,
        "defaultBg": "white",
        "composition": "head_shoulder",
        "mode": "anime",
    },
    "anime-red-headshot": {
        "id": "anime-red-headshot",
        "name": "二次元红底头像照",
        "category": "anime",
        "width": 295,
        "height": 413,
        "defaultBg": "red",
        "composition": "head_shoulder",
        "mode": "anime",
    },
    "anime-career": {
        "id": "anime-career",
        "name": "二次元职业形象照",
        "category": "anime",
        "width": 413,
        "height": 579,
        "defaultBg": "blue",
        "composition": "head_shoulder",
        "mode": "anime",
    },
    "creative-square-avatar": {
        "id": "creative-square-avatar",
        "name": "创意方形头像",
        "category": "creative",
        "width": 512,
        "height": 512,
        "defaultBg": "lightBlue",
        "composition": "square_avatar",
        "mode": "creative",
    },
}

# Every existing entry exposes the same stable profile shape. Entries without
# a cited standard keep null ratios and continue using the historical project
# composition envelope.
def _build_traceable_fields(spec_id, spec):
    prof = spec.get("compositionProfile") or {}
    standard_ref = prof.get("standardRef") or spec.get("standardRef") or ""
    src = standard_ref if standard_ref else "项目通用规格定义"
    eff = (
        "2014-12-01" if "1180" in standard_ref
        else ("2019-01-01" if "461" in standard_ref
        else ("2022-04-01" if "驾驶证" in standard_ref or "162" in standard_ref
        else "2024-01-01"))
    )
    verified = bool(standard_ref and prof.get("sourceType") == "official")
    fields = []
    
    if spec.get("widthMm") and spec.get("heightMm"):
        fields.append({"field": "width", "value": spec["widthMm"], "unit": "mm", "source": src, "verified": verified, "effectiveDate": eff})
        fields.append({"field": "height", "value": spec["heightMm"], "unit": "mm", "source": src, "verified": verified, "effectiveDate": eff})
    else:
        fields.append({"field": "width", "value": spec["width"], "unit": "px", "source": src, "verified": verified, "effectiveDate": eff})
        fields.append({"field": "height", "value": spec["height"], "unit": "px", "source": src, "verified": verified, "effectiveDate": eff})

    if prof.get("headWidthRatioMin") is not None:
        val = spec["widthMm"] * prof["headWidthRatioMin"] if spec.get("widthMm") else prof["headWidthRatioMin"]
        unit = "mm" if spec.get("widthMm") else "ratio"
        fields.append({"field": "headWidthMin", "value": round(val, 2), "unit": unit, "source": src, "verified": verified, "effectiveDate": eff})
    if prof.get("headWidthRatioMax") is not None:
        val = spec["widthMm"] * prof["headWidthRatioMax"] if spec.get("widthMm") else prof["headWidthRatioMax"]
        unit = "mm" if spec.get("widthMm") else "ratio"
        fields.append({"field": "headWidthMax", "value": round(val, 2), "unit": unit, "source": src, "verified": verified, "effectiveDate": eff})
    if prof.get("headHeightRatioMin") is not None:
        val = spec["heightMm"] * prof["headHeightRatioMin"] if spec.get("heightMm") else prof["headHeightRatioMin"]
        unit = "mm" if spec.get("heightMm") else "ratio"
        fields.append({"field": "headHeightMin", "value": round(val, 2), "unit": unit, "source": src, "verified": verified, "effectiveDate": eff})
    if prof.get("headHeightRatioMax") is not None:
        val = spec["heightMm"] * prof["headHeightRatioMax"] if spec.get("heightMm") else prof["headHeightRatioMax"]
        unit = "mm" if spec.get("heightMm") else "ratio"
        fields.append({"field": "headHeightMax", "value": round(val, 2), "unit": unit, "source": src, "verified": verified, "effectiveDate": eff})
    if prof.get("topMarginRatioMin") is not None:
        val = spec["heightMm"] * prof["topMarginRatioMin"] if spec.get("heightMm") else prof["topMarginRatioMin"]
        unit = "mm" if spec.get("heightMm") else "ratio"
        fields.append({"field": "topMarginMin", "value": round(val, 2), "unit": unit, "source": src, "verified": verified, "effectiveDate": eff})
    if prof.get("topMarginRatioMax") is not None:
        val = spec["heightMm"] * prof["topMarginRatioMax"] if spec.get("heightMm") else prof["topMarginRatioMax"]
        unit = "mm" if spec.get("heightMm") else "ratio"
        fields.append({"field": "topMarginMax", "value": round(val, 2), "unit": unit, "source": src, "verified": verified, "effectiveDate": eff})
    if prof.get("chinBottomRatioMin") is not None:
        val = spec["heightMm"] * prof["chinBottomRatioMin"] if spec.get("heightMm") else prof["chinBottomRatioMin"]
        unit = "mm" if spec.get("heightMm") else "ratio"
        fields.append({"field": "chinBottomMin", "value": round(val, 2), "unit": unit, "source": src, "verified": verified, "effectiveDate": eff})
    if prof.get("backgroundPolicy"):
        fields.append({"field": "backgroundPolicy", "value": prof["backgroundPolicy"], "unit": "enum", "source": src, "verified": verified, "effectiveDate": eff})

    return fields


for _spec_id, _spec in PHOTO_SPECS.items():
    if "compositionProfile" not in _spec:
        _spec["compositionProfile"] = (
            dict(PROJECT_COMMON_PROFILE)
            if _spec.get("category") == "common" and _spec.get("composition") == "head_shoulder"
            else _composition_profile(sourceType="project_profile")
        )
    _spec["traceableFields"] = _build_traceable_fields(_spec_id, _spec)

DEFAULT_SPEC_BY_PURPOSE = {
    "official_id_photo": "one-inch",
    "id_card": "id-card-cn",
    "social_security": "social-security-cn",
    "passport": "passport-cn",
    "driver_license": "driver-license-cn",
    "teacher_exam": "teacher-exam",
    "civil_service_exam": "civil-service-exam",
    "resume": "resume-headshot",
    "career_portrait": "career-headshot",
    "anime_avatar": "anime-blue-headshot",
    "creative_id_photo": "creative-square-avatar",
}


def get_spec(spec_id=None, purpose=None):
    spec = PHOTO_SPECS.get(spec_id or "")
    if spec is None:
        spec = PHOTO_SPECS[DEFAULT_SPEC_BY_PURPOSE.get(purpose or "", "one-inch")]
    return dict(spec)

