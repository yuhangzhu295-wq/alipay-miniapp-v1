/**
 * 证件照规格统一数据源
 */
const photoSpecs = [
  {
    id: "yicun",
    name: "一寸",
    displayName: "一寸照",
    mm: "25×35mm",
    widthMm: 25,
    heightMm: 35,
    px: "295×413px",
    widthPx: 295,
    heightPx: 413,
    category: "常用寸照",
    defaultBg: "blue",
    bgColors: ["blue", "white", "red", "lightBlue", "gray"]
  },
  {
    id: "ercun",
    name: "二寸",
    displayName: "二寸照",
    mm: "35×49mm",
    widthMm: 35,
    heightMm: 49,
    px: "413×579px",
    widthPx: 413,
    heightPx: 579,
    category: "常用寸照",
    defaultBg: "blue",
    bgColors: ["blue", "white", "red", "lightBlue", "gray"]
  },
  {
    id: "dayicun",
    name: "大一寸",
    displayName: "大一寸照",
    mm: "33×48mm",
    widthMm: 33,
    heightMm: 48,
    px: "390×567px",
    widthPx: 390,
    heightPx: 567,
    category: "常用寸照",
    defaultBg: "blue",
    bgColors: ["blue", "white", "red", "lightBlue", "gray"]
  },
  {
    id: "xiaoyicun",
    name: "小一寸",
    displayName: "小一寸照",
    mm: "22×32mm",
    widthMm: 22,
    heightMm: 32,
    px: "260×378px",
    widthPx: 260,
    heightPx: 378,
    category: "常用寸照",
    defaultBg: "blue",
    bgColors: ["blue", "white", "red", "lightBlue", "gray"]
  },
  {
    id: "xiaoercun",
    name: "小二寸",
    displayName: "小二寸照",
    mm: "35×45mm",
    widthMm: 35,
    heightMm: 45,
    px: "413×531px",
    widthPx: 413,
    heightPx: 531,
    category: "常用寸照",
    defaultBg: "blue",
    bgColors: ["blue", "white", "red", "lightBlue", "gray"]
  },
  {
    id: "jianli",
    name: "简历照片",
    displayName: "简历照片",
    mm: "25×35mm",
    widthMm: 25,
    heightMm: 35,
    px: "295×413px",
    widthPx: 295,
    heightPx: 413,
    category: "求职简历",
    defaultBg: "blue",
    bgColors: ["blue", "white", "red", "lightBlue", "gray"]
  },
  {
    id: "jiaoshi",
    name: "教师资格证",
    displayName: "教师资格证报名照",
    mm: "25×35mm",
    widthMm: 25,
    heightMm: 35,
    px: "295×413px",
    widthPx: 295,
    heightPx: 413,
    category: "考试报名",
    defaultBg: "white",
    bgColors: ["white", "blue", "red", "lightBlue", "gray"]
  },
  {
    id: "computer",
    name: "计算机等级考试",
    displayName: "计算机等级考试",
    mm: "33×48mm",
    widthMm: 33,
    heightMm: 48,
    px: "390×567px",
    widthPx: 390,
    heightPx: 567,
    category: "考试报名",
    defaultBg: "blue",
    bgColors: ["blue", "white", "red"]
  },
  {
    id: "civil_service",
    name: "国家公务员考试",
    displayName: "国家公务员考试",
    mm: "35×45mm",
    widthMm: 35,
    heightMm: 45,
    px: "413×531px",
    widthPx: 413,
    heightPx: 531,
    category: "考试报名",
    defaultBg: "blue",
    bgColors: ["blue", "white", "red"]
  },
  {
    id: "cet",
    name: "英语四六级考试",
    displayName: "英语四六级考试",
    mm: "33×48mm",
    widthMm: 33,
    heightMm: 48,
    px: "390×567px",
    widthPx: 390,
    heightPx: 567,
    category: "学历/语言考试",
    defaultBg: "blue",
    bgColors: ["blue", "white", "red"]
  },
  {
    id: "student_image",
    name: "大学生图像信息采集",
    displayName: "大学生图像信息采集",
    mm: "41×54mm",
    widthMm: 41,
    heightMm: 54,
    px: "480×640px",
    widthPx: 480,
    heightPx: 640,
    category: "学历/语言考试",
    defaultBg: "blue",
    bgColors: ["blue", "white"]
  },
  {
    id: "accounting",
    name: "初级会计资格考试",
    displayName: "初级会计资格考试",
    mm: "25×35mm",
    widthMm: 25,
    heightMm: 35,
    px: "295×413px",
    widthPx: 295,
    heightPx: 413,
    category: "职业资格",
    defaultBg: "blue",
    bgColors: ["blue", "white", "red"]
  },
  {
    id: "selfstudy",
    name: "成人自考",
    displayName: "成人自考报名照",
    mm: "25×35mm",
    widthMm: 25,
    heightMm: 35,
    px: "295×413px",
    widthPx: 295,
    heightPx: 413,
    category: "学历/语言考试",
    defaultBg: "blue",
    bgColors: ["blue", "white"]
  },
  {
    id: "driver",
    name: "驾驶证",
    displayName: "驾驶证照片",
    mm: "22×32mm",
    widthMm: 22,
    heightMm: 32,
    px: "260×378px",
    widthPx: 260,
    heightPx: 378,
    category: "证件",
    defaultBg: "white",
    bgColors: ["white", "blue", "red"]
  }
];

const bgColors = [
  { id: "blue", name: "蓝色", hex: "#1a73e8" },
  { id: "white", name: "白色", hex: "#ffffff" },
  { id: "red", name: "红色", hex: "#e53935" },
  { id: "lightBlue", name: "浅蓝色", hex: "#81d4fa" },
  { id: "gray", name: "灰色", hex: "#9e9e9e" },
  { id: "darkBlue", name: "深蓝色", hex: "#0b3d91" },
  { id: "custom", name: "自定义", hex: "#1a73e8" }
];

const MAINLAND_PROVINCES = [
  "北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江",
  "上海", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南",
  "湖北", "湖南", "广东", "广西", "海南", "重庆", "四川", "贵州",
  "云南", "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆"
];

const GUANGDONG_DRIVER_CITIES = [
  "广州", "深圳", "东莞", "珠海", "佛山", "江门", "惠州", "中山",
  "汕头", "湛江", "茂名", "肇庆", "梅州", "汕尾", "河源", "阳江",
  "清远", "韶关", "潮州", "揭阳", "云浮"
];

const SOURCE_LABELS = {
  official: "官方",
  local_common: "地方",
  platform: "平台",
  deprecated: "历史",
  custom: "自定义",
  unknown: "按公告",
  official_notice: "官方",
  platform_rule: "平台",
  third_party_pending: "按公告",
  user_custom: "自定义"
};

const DEFAULT_SOURCE_NOTE = "规格可能随地区和报名平台调整，请以当年官方公告为准。";
const DEFAULT_VERIFIED_AT = "2026-05-28";
const ALLOWED_SOURCE_LEVELS = {
  official: true,
  local_common: true,
  platform: true,
  deprecated: true,
  custom: true,
  unknown: true
};

function normalizeSourceLevel(level) {
  if (level === "official_notice") return "official";
  if (level === "platform_rule") return "platform";
  if (level === "third_party_pending") return "unknown";
  if (level === "user_custom") return "custom";
  return ALLOWED_SOURCE_LEVELS[level] ? level : "unknown";
}

function isSpecEnabled(spec) {
  return spec && spec.enabled !== false && spec.active !== false;
}

function getDefaultCropComposition(data) {
  var id = data.id || "";
  var category = data.category || "";
  var type = "id_head_shoulder";
  if (id.indexOf("driver") >= 0) type = "driver_license_head";
  if (category.indexOf("考试") >= 0 || id.indexOf("exam") >= 0 || id.indexOf("teacher") >= 0) type = "exam_head_shoulder";
  if (category.indexOf("学籍") >= 0 || id.indexOf("school") >= 0 || id.indexOf("enroll") >= 0) type = "school_head_shoulder";
  if (id.indexOf("resume") >= 0 || id.indexOf("jianli") >= 0) type = "resume_avatar";
  return {
    type: type,
    headHeightRatioMin: 0.58,
    headHeightRatioMax: 0.70,
    headWidthRatioMin: 0.45,
    headWidthRatioMax: 0.65,
    topPaddingRatioMin: type === "driver_license_head" ? 0.08 : 0.07,
    topPaddingRatioMax: 0.12,
    topPaddingRatio: type === "driver_license_head" ? 0.09 : 0.08,
    faceCenterYRatio: type === "resume_avatar" ? 0.42 : 0.43,
    shoulderVisible: true,
    keepUpperChest: true,
    shoulderWidthRatioMin: 0.70,
    shoulderWidthRatioMax: 0.90,
    maxBodyBelowShoulderRatio: 0.22,
    bottomKeepRatio: type === "driver_license_head" ? 0.16 : 0.20
  };
}

const specGroups = [
  {
    groupId: "one_inch",
    groupName: "一寸",
    displayMode: "single",
    category: "常用规格",
    description: "25×35mm | 295×413px",
    defaultSpecId: "yicun",
    colors: ["blue", "white", "red", "lightBlue", "gray"],
    icon: "👤",
    specs: []
  },
  {
    groupId: "two_inch",
    groupName: "二寸",
    displayMode: "single",
    category: "常用规格",
    description: "35×49mm | 413×579px",
    defaultSpecId: "ercun",
    colors: ["blue", "white", "red", "lightBlue", "gray"],
    icon: "👨",
    specs: []
  },
  {
    groupId: "teacher_cert",
    groupName: "教师资格证",
    displayMode: "group",
    category: "考试报名",
    description: "多种尺寸，点击选择",
    defaultSpecId: "teacher_cert_295_413",
    colors: ["white", "blue", "red"],
    icon: "📜",
    specs: [
      { id: "teacher_cert_295_413", name: "中小学教师资格证（2025笔试报名）", displayName: "中小学教师资格证（2025笔试报名）", mm: "25×35mm", widthMm: 25, heightMm: 35, px: "295×413px", widthPx: 295, heightPx: 413, category: "考试报名", defaultBg: "white", bgColors: ["white"] },
      { id: "teacher_cert_413_579", name: "教师资格证（二寸）", displayName: "教师资格证（二寸）", mm: "35×49mm", widthMm: 35, heightMm: 49, px: "413×579px", widthPx: 413, heightPx: 579, category: "考试报名", defaultBg: "blue", bgColors: ["blue", "white", "red"] },
      { id: "teacher_cert_400_600", name: "教师资格证", displayName: "教师资格证（400×600）", mm: "34×51mm", widthMm: 34, heightMm: 51, px: "400×600px", widthPx: 400, heightPx: 600, category: "考试报名", defaultBg: "white", bgColors: ["white", "blue"] },
      { id: "teacher_cert_180_240", name: "教师资格证（180×240）", displayName: "教师资格证（180×240）", mm: "15×20mm", widthMm: 15, heightMm: 20, px: "180×240px", widthPx: 180, heightPx: 240, category: "考试报名", defaultBg: "white", bgColors: ["white"] },
      { id: "teacher_cert_384_512", name: "教师资格证（384×512）", displayName: "教师资格证（384×512）", mm: "32×43mm", widthMm: 32, heightMm: 43, px: "384×512px", widthPx: 384, heightPx: 512, category: "考试报名", defaultBg: "white", bgColors: ["white", "blue"] }
    ]
  },
  {
    groupId: "civil_service_exam",
    groupName: "国考 / 公务员",
    displayMode: "group",
    category: "考试报名",
    description: "多省份规格，点击选择",
    defaultSpecId: "civil_service_common",
    colors: ["blue", "white", "red"],
    icon: "🏛️",
    specs: [
      { id: "civil_service_common", name: "通用国考", displayName: "国考通用规格", mergeName: "国考通用规格", appliesTo: "北京、天津、河北、山西、内蒙古、辽宁、吉林、黑龙江、上海、江苏、浙江、安徽、福建、江西、山东、河南、湖北、湖南、广东、广西、海南、重庆、四川、贵州、云南、陕西、甘肃、青海、宁夏、新疆", mm: "35×45mm", widthMm: 35, heightMm: 45, px: "413×531px", widthPx: 413, heightPx: 531, category: "考试报名", defaultBg: "blue", bgColors: ["blue", "white", "red"] },
      { id: "civil_service_beijing", name: "国考（北京）", displayName: "国考（北京）", mergeName: "国考通用规格", appliesTo: "北京", mm: "35×45mm", widthMm: 35, heightMm: 45, px: "413×531px", widthPx: 413, heightPx: 531, category: "考试报名", defaultBg: "blue", bgColors: ["blue", "white", "red"] },
      { id: "civil_service_tianjin", name: "国考（天津）", displayName: "国考（天津）", mergeName: "国考通用规格", appliesTo: "天津", mm: "35×45mm", widthMm: 35, heightMm: 45, px: "413×531px", widthPx: 413, heightPx: 531, category: "考试报名", defaultBg: "blue", bgColors: ["blue", "white", "red"] },
      { id: "civil_service_henan", name: "国考（河南）", displayName: "国考（河南）", mergeName: "国考通用规格", appliesTo: "河南", mm: "35×45mm", widthMm: 35, heightMm: 45, px: "413×531px", widthPx: 413, heightPx: 531, category: "考试报名", defaultBg: "blue", bgColors: ["blue", "white", "red"] },
      { id: "civil_service_413_626", name: "公务员考试（二寸）", displayName: "公务员考试（二寸）", mm: "35×53mm", widthMm: 35, heightMm: 53, px: "413×626px", widthPx: 413, heightPx: 626, category: "考试报名", defaultBg: "blue", bgColors: ["blue", "white"] }
    ]
  },
  {
    groupId: "driver_license",
    groupName: "驾驶证",
    displayMode: "group",
    category: "证件/社保",
    description: "多地区规格，点击选择",
    defaultSpecId: "driver_common",
    colors: ["white", "blue", "red"],
    icon: "🚗",
    specs: [
      { id: "driver_common", name: "驾驶证通用", displayName: "驾驶证通用规格", mm: "22×32mm", widthMm: 22, heightMm: 32, px: "260×378px", widthPx: 260, heightPx: 378, category: "证件", defaultBg: "white", bgColors: ["white", "blue", "red"] },
      { id: "driver_guangdong_common", name: "广东驾驶证通用", displayName: "广东驾驶证通用规格", mergeName: "广东驾驶证通用规格", appliesTo: "广州、深圳、东莞、珠海、佛山、江门、中山、惠州", mm: "35×49mm", widthMm: 35, heightMm: 49, px: "413×579px", widthPx: 413, heightPx: 579, category: "证件", defaultBg: "white", bgColors: ["white", "blue"] },
      { id: "driver_guangzhou", name: "广州市驾驶证", displayName: "广州市驾驶证", mergeName: "广东驾驶证通用规格", appliesTo: "广州", mm: "35×49mm", widthMm: 35, heightMm: 49, px: "413×579px", widthPx: 413, heightPx: 579, category: "证件", defaultBg: "white", bgColors: ["white", "blue"] },
      { id: "driver_shenzhen", name: "深圳市驾驶证", displayName: "深圳市驾驶证", mergeName: "广东驾驶证通用规格", appliesTo: "深圳", mm: "35×49mm", widthMm: 35, heightMm: 49, px: "413×579px", widthPx: 413, heightPx: 579, category: "证件", defaultBg: "white", bgColors: ["white", "blue"] }
    ]
  },
  {
    groupId: "accounting_title_exam",
    groupName: "会计 / 职称考试",
    displayMode: "group",
    category: "职业资格",
    description: "多种尺寸，点击选择",
    defaultSpecId: "accounting_middle_295_413",
    colors: ["blue", "white", "red"],
    icon: "🧮",
    specs: [
      { id: "accounting_middle_295_413", name: "中级会计职称考试（一寸）", displayName: "中级会计职称考试（一寸）", mm: "25×35mm", widthMm: 25, heightMm: 35, px: "295×413px", widthPx: 295, heightPx: 413, category: "职业资格", defaultBg: "blue", bgColors: ["blue", "white", "red"] },
      { id: "accounting_middle_240_320", name: "中级会计职称考试（240×320）", displayName: "中级会计职称考试（240×320）", mm: "20×27mm", widthMm: 20, heightMm: 27, px: "240×320px", widthPx: 240, heightPx: 320, category: "职业资格", defaultBg: "white", bgColors: ["white", "blue"] },
      { id: "accounting_middle_shanghai_215_300", name: "上海中级会计职称考试", displayName: "上海中级会计职称考试", mm: "18×25mm", widthMm: 18, heightMm: 25, px: "215×300px", widthPx: 215, heightPx: 300, category: "职业资格", defaultBg: "white", bgColors: ["white"] },
      { id: "accounting_middle_114_156", name: "中级会计职称考试（114×156）", displayName: "中级会计职称考试（114×156）", mm: "10×13mm", widthMm: 10, heightMm: 13, px: "114×156px", widthPx: 114, heightPx: 156, category: "职业资格", defaultBg: "white", bgColors: ["white"] }
    ]
  },
  {
    groupId: "school_enrollment",
    groupName: "学籍 / 入学报名",
    displayMode: "group",
    category: "学籍/入学",
    description: "多种尺寸，点击选择",
    defaultSpecId: "student_image",
    colors: ["blue", "white"],
    icon: "🎓",
    specs: [
      { id: "student_image", name: "大学生图像信息采集", displayName: "大学生图像信息采集", mm: "41×54mm", widthMm: 41, heightMm: 54, px: "480×640px", widthPx: 480, heightPx: 640, category: "学历/语言考试", defaultBg: "blue", bgColors: ["blue", "white"] },
      { id: "enroll_295_413", name: "入学报名照（一寸）", displayName: "入学报名照（一寸）", mm: "25×35mm", widthMm: 25, heightMm: 35, px: "295×413px", widthPx: 295, heightPx: 413, category: "学历/语言考试", defaultBg: "blue", bgColors: ["blue", "white"] }
    ]
  },
  {
    groupId: "language_computer_exam",
    groupName: "英语四六级 / 普通话 / 计算机等级",
    displayMode: "group",
    category: "考试报名",
    description: "多考试版本，点击选择",
    defaultSpecId: "cet",
    colors: ["blue", "white", "red"],
    icon: "📘",
    specs: []
  },
  {
    groupId: "professional_license_exam",
    groupName: "护士 / 医师 / 导游等资格考试",
    displayMode: "group",
    category: "职业资格",
    description: "职业资格类，点击选择",
    defaultSpecId: "nurse_exam_295_413",
    colors: ["blue", "white", "red"],
    icon: "🪪",
    specs: [
      { id: "nurse_exam_295_413", name: "护士资格考试", displayName: "护士资格考试", mm: "25×35mm", widthMm: 25, heightMm: 35, px: "295×413px", widthPx: 295, heightPx: 413, category: "职业资格", defaultBg: "white", bgColors: ["white", "blue"] },
      { id: "doctor_exam_413_531", name: "医师资格考试", displayName: "医师资格考试", mm: "35×45mm", widthMm: 35, heightMm: 45, px: "413×531px", widthPx: 413, heightPx: 531, category: "职业资格", defaultBg: "white", bgColors: ["white", "blue"] },
      { id: "guide_exam_295_413", name: "导游资格考试", displayName: "导游资格考试", mm: "25×35mm", widthMm: 25, heightMm: 35, px: "295×413px", widthPx: 295, heightPx: 413, category: "职业资格", defaultBg: "blue", bgColors: ["blue", "white", "red"] }
    ]
  },
  {
    groupId: "social_id_card",
    groupName: "社保/身份证类",
    displayMode: "group",
    category: "证件/社保",
    description: "白底证照，点击选择",
    defaultSpecId: "id_card_cn_358_441",
    colors: ["white", "blue"],
    icon: "🪪",
    specs: [
      { id: "id_card_cn_358_441", name: "二代身份证数码照", displayName: "二代身份证数码照", mm: "26×32mm", widthMm: 26, heightMm: 32, px: "358×441px", widthPx: 358, heightPx: 441, category: "证件", defaultBg: "white", bgColors: ["white"] },
      { id: "social_security_358_441", name: "社保卡数码照", displayName: "社保卡数码照", mm: "26×32mm", widthMm: 26, heightMm: 32, px: "358×441px", widthPx: 358, heightPx: 441, category: "证件", defaultBg: "white", bgColors: ["white"] }
    ]
  },
  {
    groupId: "passport_visa",
    groupName: "护照 / 签证 / 出入境类",
    displayMode: "group",
    category: "证件/社保",
    description: "出入境规格，点击选择",
    defaultSpecId: "passport_cn_390_567",
    colors: ["white", "lightBlue"],
    icon: "🛂",
    specs: []
  },
  {
    groupId: "custom_size",
    groupName: "自定义尺寸",
    displayMode: "custom",
    category: "自定义",
    description: "自定义 mm / px / 文件大小",
    defaultSpecId: "custom",
    colors: ["blue", "white", "red", "lightBlue", "gray", "darkBlue"],
    icon: "✂️",
    specs: []
  }
];

function makeSpec(data) {
  var colors = (data.colors || data.bgColors || ["blue", "white"]).slice();
  var fileFormat = (data.fileFormat || ["jpg", "jpeg"]).slice();
  var widthMm = data.widthMm;
  var heightMm = data.heightMm;
  var widthPx = data.widthPx;
  var heightPx = data.heightPx;
  var sourceLevel = normalizeSourceLevel(data.sourceLevel);
  var enabledValue = data.enabled !== false && data.active !== false;
  var fileTextParts = [];
  if (fileFormat.length) fileTextParts.push(fileFormat.join("/").toUpperCase());
  if (data.minFileKB || data.maxFileKB) {
    fileTextParts.push((data.minFileKB ? data.minFileKB + "K-" : "") + (data.maxFileKB ? data.maxFileKB + "K以内" : ""));
  }
  var fileLimit = data.fileSizeLimit || (data.minFileKB || data.maxFileKB
    ? { minKB: data.minFileKB || null, maxKB: data.maxFileKB || null }
    : "按报名平台要求");
  var notice = data.notice || data.note || DEFAULT_SOURCE_NOTE;
  return Object.assign({
    groupId: "",
    groupName: "",
    aliases: [],
    regionLevel: data.city ? "city" : (data.province ? "province" : "national"),
    dpi: 300,
    colors: colors,
    bgColors: colors,
    backgrounds: colors,
    fileFormat: fileFormat,
    fileSizeLimit: fileLimit,
    backgroundRequirement: colors.join(" / ") + "底",
    portraitRequirement: "近期免冠正面证件照，显示头部和肩部",
    composition: "head_shoulder",
    cropComposition: data.cropComposition || getDefaultCropComposition(data),
    sourceLevel: sourceLevel,
    sourceName: "内置规格库",
    sourceUrl: "",
    verifiedAt: DEFAULT_VERIFIED_AT,
    notice: notice,
    note: notice,
    enabled: enabledValue,
    active: enabledValue,
    priority: 50,
    sort: data.sort || data.priority || 50,
    defaultBg: colors[0] || "blue",
    mm: widthMm && heightMm ? (widthMm + "×" + heightMm + "mm") : (data.mm || ""),
    px: widthPx && heightPx ? (widthPx + "×" + heightPx + "px") : (data.px || ""),
    sourceLabel: SOURCE_LABELS[sourceLevel] || SOURCE_LABELS.unknown,
    sourceClass: "source-" + sourceLevel,
    fileText: fileTextParts.join(" | ")
  }, data, {
    colors: colors,
    bgColors: colors,
    backgrounds: colors,
    fileFormat: fileFormat,
    fileSizeLimit: fileLimit,
    sourceLevel: sourceLevel,
    sourceLabel: SOURCE_LABELS[sourceLevel] || SOURCE_LABELS.unknown,
    sourceClass: "source-" + sourceLevel,
    notice: notice,
    note: notice,
    enabled: enabledValue,
    active: enabledValue,
    sort: data.sort || data.priority || 50,
    fileText: fileTextParts.join(" | ")
  });
}

function setGroup(groupId, patch) {
  var group = specGroups.find(function(item) { return item.groupId === groupId; });
  if (!group) {
    specGroups.push(patch);
    return patch;
  }
  Object.assign(group, patch);
  return group;
}

function markSpecs(group, list) {
  group.specs = list.map(function(item) {
    return makeSpec(Object.assign({
      groupId: group.groupId,
      groupName: group.groupName,
      category: group.category
    }, item));
  }).sort(function(a, b) {
    return (a.priority || 50) - (b.priority || 50);
  });
}

function applyRegistrySpecGroups() {
  var pending = {
    sourceLevel: "third_party_pending",
    sourceName: "待核验规格",
    sourceUrl: "",
    verifiedAt: DEFAULT_VERIFIED_AT,
    note: DEFAULT_SOURCE_NOTE
  };

  var teacher = setGroup("teacher_cert", {
    groupId: "teacher_cert",
    groupName: "教师资格证",
    displayMode: "group",
    category: "考试报名",
    description: "多种尺寸，点击选择",
    defaultSpecId: "teacher_cert_295_413",
    colors: ["white", "blue", "red"],
    icon: "📜"
  });
  markSpecs(teacher, [
    Object.assign({}, pending, { id: "teacher_cert_295_413", name: "中小学教师资格证报名", displayName: "中小学教师资格证报名", aliases: ["教师资格证", "教资报名", "教师资格证笔试"], widthMm: 25, heightMm: 35, widthPx: 295, heightPx: 413, colors: ["white"], fileFormat: ["jpg", "jpeg"], maxFileKB: 200, backgroundRequirement: "白色背景", portraitRequirement: "近期免冠正面彩色证件照，显示头部和肩部；不戴帽子、头巾、发带、墨镜", priority: 1 }),
    Object.assign({}, pending, { id: "teacher_cert_413_579", name: "教师资格证（二寸）", displayName: "教师资格证（二寸）", widthMm: 35, heightMm: 49, widthPx: 413, heightPx: 579, colors: ["blue", "white", "red"], priority: 2 }),
    Object.assign({}, pending, { id: "teacher_cert_180_240", name: "教师资格证（180×240）", displayName: "教师资格证（180×240）", widthPx: 180, heightPx: 240, colors: ["white"], priority: 3 }),
    Object.assign({}, pending, { id: "teacher_cert_150_200", name: "教师资格证（150×200）", displayName: "教师资格证（150×200）", widthPx: 150, heightPx: 200, colors: ["white"], priority: 4 }),
    Object.assign({}, pending, { id: "teacher_cert_384_512", name: "教师资格证（384×512）", displayName: "教师资格证（384×512）", widthPx: 384, heightPx: 512, colors: ["white", "blue"], priority: 5 }),
    Object.assign({}, pending, { id: "teacher_cert_province_pending", name: "各省教师资格证补充规格", displayName: "各省教师资格证补充规格", appliesTo: MAINLAND_PROVINCES.join("、"), regionLevel: "province", widthMm: 25, heightMm: 35, widthPx: 295, heightPx: 413, colors: ["white"], priority: 20 })
  ]);

  var civil = setGroup("civil_service_exam", {
    groupId: "civil_service_exam",
    groupName: "国考 / 公务员",
    displayMode: "group",
    category: "考试报名",
    description: "多省份规格，点击选择",
    defaultSpecId: "civil_service_common",
    colors: ["blue", "white", "red"],
    icon: "🏛️"
  });
  markSpecs(civil, [
    Object.assign({}, pending, { id: "civil_service_common", name: "国考 / 省考通用规格", displayName: "国考 / 省考通用规格", mergeName: "国考 / 省考通用规格", aliases: ["国考", "公务员考试", "省考"], appliesTo: MAINLAND_PROVINCES.join("、"), regionLevel: "province", widthMm: 35, heightMm: 45, widthPx: 413, heightPx: 531, colors: ["blue", "white"], priority: 1 }),
    Object.assign({}, pending, { id: "civil_service_min_295_413", name: "国考报名照（最低像素）", displayName: "国考报名照（最低像素）", aliases: ["国考报名照", "公务员报名照"], widthPx: 295, heightPx: 413, colors: ["blue", "white"], fileFormat: ["jpg", "jpeg"], portraitRequirement: "近期免冠正面电子证件照", note: "宽不低于295px，高不低于413px；请以报名平台最新要求为准", priority: 2 }),
    Object.assign({}, pending, { id: "civil_service_two_inch", name: "公务员考试（二寸）", displayName: "公务员考试（二寸）", widthMm: 35, heightMm: 53, widthPx: 413, heightPx: 626, colors: ["blue", "white"], priority: 8 })
  ].concat(MAINLAND_PROVINCES.map(function(province, index) {
    return Object.assign({}, pending, {
      id: "civil_service_province_" + index,
      name: province + "公务员 / 省考",
      displayName: province + "公务员 / 省考",
      mergeName: "国考 / 省考通用规格",
      aliases: [province + "国考", province + "省考", province + "公务员考试"],
      province: province,
      appliesTo: province,
      regionLevel: "province",
      widthMm: 35,
      heightMm: 45,
      widthPx: 413,
      heightPx: 531,
      colors: ["blue", "white"],
      priority: 30 + index
    });
  })));

  var driver = setGroup("driver_license", {
    groupId: "driver_license",
    groupName: "驾驶证",
    displayMode: "group",
    category: "证件/社保",
    description: "多地区规格，点击选择",
    defaultSpecId: "driver_common",
    colors: ["white", "blue", "red"],
    icon: "🚗"
  });
  markSpecs(driver, [
    Object.assign({}, pending, { id: "driver_common", name: "驾驶证通用", displayName: "驾驶证通用", aliases: ["驾照", "驾驶证照片"], widthMm: 22, heightMm: 32, widthPx: 260, heightPx: 378, colors: ["white", "blue", "red"], priority: 1 }),
    Object.assign({}, pending, { id: "driver_guangdong_common", name: "广东驾驶证通用规格", displayName: "广东驾驶证通用规格", mergeName: "广东驾驶证通用规格", province: "广东", appliesTo: GUANGDONG_DRIVER_CITIES.join("、"), regionLevel: "city", widthMm: 35, heightMm: 49, widthPx: 413, heightPx: 579, colors: ["white", "blue"], priority: 2 }),
    Object.assign({}, pending, { id: "driver_other_province_common", name: "其他省份驾驶证通用项", displayName: "其他省份驾驶证通用项", appliesTo: MAINLAND_PROVINCES.filter(function(p) { return p !== "广东"; }).join("、"), regionLevel: "province", widthMm: 22, heightMm: 32, widthPx: 260, heightPx: 378, colors: ["white", "blue"], priority: 5 })
  ].concat(GUANGDONG_DRIVER_CITIES.map(function(city, index) {
    return Object.assign({}, pending, {
      id: "driver_guangdong_city_" + index,
      name: city + "驾驶证",
      displayName: city + "驾驶证",
      mergeName: "广东驾驶证通用规格",
      aliases: [city + "驾照", "广东" + city + "驾驶证"],
      province: "广东",
      city: city,
      appliesTo: city,
      regionLevel: "city",
      widthMm: 35,
      heightMm: 49,
      widthPx: 413,
      heightPx: 579,
      colors: ["white", "blue"],
      priority: 20 + index
    });
  })).concat(MAINLAND_PROVINCES.filter(function(province) {
    return province !== "广东";
  }).map(function(province, index) {
    return Object.assign({}, pending, {
      id: "driver_province_" + index,
      name: province + "驾驶证",
      displayName: province + "驾驶证",
      mergeName: "其他省份驾驶证通用项",
      aliases: [province + "驾照", province + "驾驶证照片"],
      province: province,
      appliesTo: province,
      regionLevel: "province",
      widthMm: 22,
      heightMm: 32,
      widthPx: 260,
      heightPx: 378,
      colors: ["white", "blue"],
      priority: 60 + index
    });
  })));

  var accounting = setGroup("accounting_title_exam", {
    groupId: "accounting_title_exam",
    groupName: "会计 / 职称考试",
    displayMode: "group",
    category: "职业资格",
    description: "多种尺寸，点击选择",
    defaultSpecId: "accounting_junior_295_413",
    colors: ["blue", "white", "red"],
    icon: "🧮"
  });
  markSpecs(accounting, [
    Object.assign({}, pending, { id: "accounting_junior_295_413", name: "全国初级会计资格考试", displayName: "全国初级会计资格考试", aliases: ["初级会计", "初级会计资格考试"], widthMm: 25, heightMm: 35, widthPx: 295, heightPx: 413, colors: ["blue", "white", "red"], priority: 1 }),
    Object.assign({}, pending, { id: "accounting_middle_295_413", name: "中级会计职称考试（一寸）", displayName: "中级会计职称考试（一寸）", aliases: ["中级会计", "中级会计职称考试"], widthMm: 25, heightMm: 35, widthPx: 295, heightPx: 413, colors: ["blue", "white", "red"], priority: 2 }),
    Object.assign({}, pending, { id: "accounting_middle_240_320", name: "中级会计职称考试（240×320）", displayName: "中级会计职称考试（240×320）", widthPx: 240, heightPx: 320, colors: ["white", "blue"], priority: 3 }),
    Object.assign({}, pending, { id: "accounting_middle_114_156", name: "中级会计职称考试（114×156）", displayName: "中级会计职称考试（114×156）", widthPx: 114, heightPx: 156, colors: ["white"], priority: 4 }),
    Object.assign({}, pending, { id: "accounting_middle_shanghai_215_300", name: "上海中级会计职称考试", displayName: "上海中级会计职称考试", province: "上海", widthMm: 18, heightMm: 25, widthPx: 215, heightPx: 300, colors: ["white"], priority: 5 }),
    Object.assign({}, pending, { id: "economist_exam_295_413", name: "经济师考试（初级/中级/高级）", displayName: "经济师考试（初级/中级/高级）", aliases: ["经济师考试", "初级经济师", "中级经济师", "高级经济师"], widthMm: 25, heightMm: 35, widthPx: 295, heightPx: 413, colors: ["blue", "white", "red"], priority: 6 })
  ]);

  var school = setGroup("school_enrollment", {
    groupId: "school_enrollment",
    groupName: "学籍 / 入学报名",
    displayMode: "group",
    category: "学籍/入学",
    description: "多种尺寸，点击选择",
    defaultSpecId: "school_status_307_378",
    colors: ["blue", "white"],
    icon: "🎓"
  });
  markSpecs(school, [
    Object.assign({}, pending, { id: "school_status_307_378", name: "学籍照片（307×378）", displayName: "学籍照片（307×378）", aliases: ["学籍照片", "入学学籍"], widthPx: 307, heightPx: 378, colors: ["blue", "white"], priority: 1 }),
    Object.assign({}, pending, { id: "school_net_472_630", name: "学籍网", displayName: "学籍网", widthPx: 472, heightPx: 630, colors: ["blue", "white"], priority: 2 }),
    Object.assign({}, pending, { id: "school_shanghai_card_272_354", name: "上海学籍卡", displayName: "上海学籍卡", province: "上海", widthMm: 23, heightMm: 30, widthPx: 272, heightPx: 354, colors: ["blue", "white"], priority: 3 }),
    Object.assign({}, pending, { id: "school_qingdao_fushan_195_240", name: "青岛浮山路小学学籍卡", displayName: "青岛浮山路小学学籍卡", city: "青岛", regionLevel: "school", widthPx: 195, heightPx: 240, colors: ["blue", "white"], priority: 4 }),
    Object.assign({}, pending, { id: "school_lingnan_120_150", name: "广东岭南职业技术学院学籍卡", displayName: "广东岭南职业技术学院学籍卡", province: "广东", regionLevel: "school", widthPx: 120, heightPx: 150, colors: ["blue", "white"], priority: 5 }),
    Object.assign({}, pending, { id: "school_status_390_480", name: "学籍照片（390×480）", displayName: "学籍照片（390×480）", widthPx: 390, heightPx: 480, colors: ["blue", "white"], priority: 6 }),
    Object.assign({}, pending, { id: "school_status_150_200", name: "学籍照片（150×200）", displayName: "学籍照片（150×200）", widthPx: 150, heightPx: 200, colors: ["blue", "white"], priority: 7 }),
    Object.assign({}, pending, { id: "school_status_90_120", name: "学籍照片（90×120）", displayName: "学籍照片（90×120）", widthPx: 90, heightPx: 120, colors: ["blue", "white"], priority: 8 }),
    Object.assign({}, pending, { id: "school_status_300_420", name: "学籍照片（300×420）", displayName: "学籍照片（300×420）", widthPx: 300, heightPx: 420, colors: ["blue", "white"], priority: 9 }),
    Object.assign({}, pending, { id: "primary_enroll_300_420", name: "小学新生学籍", displayName: "小学新生学籍", widthMm: 25, heightMm: 36, widthPx: 300, heightPx: 420, colors: ["blue", "white"], priority: 10 }),
    Object.assign({}, pending, { id: "enroll_295_413", name: "入学报名（一寸）", displayName: "入学报名（一寸）", widthMm: 25, heightMm: 35, widthPx: 295, heightPx: 413, colors: ["blue", "white"], priority: 11 }),
    Object.assign({}, pending, { id: "college_enroll_413_531", name: "大学入学报名（小二寸）", displayName: "大学入学报名（小二寸）", widthMm: 35, heightMm: 45, widthPx: 413, heightPx: 531, colors: ["blue", "white"], priority: 12 }),
    Object.assign({}, pending, { id: "enroll_small_two_413_531", name: "入学照（小二寸）", displayName: "入学照（小二寸）", widthMm: 35, heightMm: 45, widthPx: 413, heightPx: 531, colors: ["blue", "white"], priority: 13 }),
    Object.assign({}, pending, { id: "cau_enroll_420_564", name: "中国农业大学入学报名", displayName: "中国农业大学入学报名", regionLevel: "school", widthMm: 36, heightMm: 48, widthPx: 420, heightPx: 564, colors: ["blue", "white"], priority: 14 }),
    Object.assign({}, pending, { id: "bnu_enroll_250_350", name: "北京师范大学入学报名", displayName: "北京师范大学入学报名", regionLevel: "school", widthMm: 21, heightMm: 30, widthPx: 250, heightPx: 350, colors: ["blue", "white"], priority: 15 }),
    Object.assign({}, pending, { id: "znufe_enroll_180_240", name: "中南财经政法大学入学报名", displayName: "中南财经政法大学入学报名", regionLevel: "school", widthMm: 15, heightMm: 20, widthPx: 180, heightPx: 240, colors: ["blue", "white"], priority: 16 })
  ]);

  var language = setGroup("language_computer_exam", {
    groupId: "language_computer_exam",
    groupName: "英语四六级 / 普通话 / 计算机等级",
    displayMode: "group",
    category: "考试报名",
    description: "多考试版本，点击选择",
    defaultSpecId: "cet_390_567",
    colors: ["blue", "white", "red"],
    icon: "📘"
  });
  markSpecs(language, [
    Object.assign({}, pending, { id: "cet_390_567", name: "英语四六级考试", displayName: "英语四六级考试", mergeName: "英语四六级 / 计算机等级通用规格", appliesTo: "英语四六级、计算机等级考试、全国计算机等级考试", aliases: ["四六级", "CET", "英语四级", "英语六级"], widthMm: 33, heightMm: 48, widthPx: 390, heightPx: 567, colors: ["blue", "white", "red"], priority: 1 }),
    Object.assign({}, pending, { id: "putonghua_390_567", name: "普通话水平测试", displayName: "普通话水平测试", aliases: ["普通话"], widthMm: 33, heightMm: 48, widthPx: 390, heightPx: 567, colors: ["blue", "white"], priority: 2 }),
    Object.assign({}, pending, { id: "computer_grade_390_567", name: "计算机等级考试", displayName: "计算机等级考试", mergeName: "英语四六级 / 计算机等级通用规格", appliesTo: "计算机等级考试", aliases: ["全国计算机等级考试", "NCRE"], widthMm: 33, heightMm: 48, widthPx: 390, heightPx: 567, colors: ["blue", "white", "red"], priority: 3 }),
    Object.assign({}, pending, { id: "national_computer_grade_390_567", name: "全国计算机等级考试", displayName: "全国计算机等级考试", mergeName: "英语四六级 / 计算机等级通用规格", appliesTo: "全国计算机等级考试", aliases: ["NCRE", "计算机等级考试"], widthMm: 33, heightMm: 48, widthPx: 390, heightPx: 567, colors: ["blue", "white", "red"], priority: 4 })
  ]);

  var professional = setGroup("professional_license_exam", {
    groupId: "professional_license_exam",
    groupName: "护士 / 医师 / 导游等资格考试",
    displayMode: "group",
    category: "职业资格",
    description: "职业资格类，点击选择",
    defaultSpecId: "nurse_exam_295_413",
    colors: ["blue", "white", "red"],
    icon: "🪪"
  });
  markSpecs(professional, [
    Object.assign({}, pending, { id: "nurse_exam_295_413", name: "护士执业资格考试", displayName: "护士执业资格考试", aliases: ["护士资格考试"], widthMm: 25, heightMm: 35, widthPx: 295, heightPx: 413, colors: ["white", "blue"], priority: 1 }),
    Object.assign({}, pending, { id: "doctor_exam_413_531", name: "执业医师资格考试", displayName: "执业医师资格考试", aliases: ["医师资格考试"], widthMm: 35, heightMm: 45, widthPx: 413, heightPx: 531, colors: ["white", "blue"], priority: 2 }),
    Object.assign({}, pending, { id: "guide_exam_295_413", name: "导游证", displayName: "导游证", aliases: ["导游资格考试"], widthMm: 25, heightMm: 35, widthPx: 295, heightPx: 413, colors: ["blue", "white", "red"], priority: 3 }),
    Object.assign({}, pending, { id: "insurance_practice_210_370", name: "保险执业证", displayName: "保险执业证", widthMm: 18, heightMm: 31, widthPx: 210, heightPx: 370, colors: ["white", "blue"], priority: 4 }),
    Object.assign({}, pending, { id: "judicial_exam_413_626", name: "司法考试", displayName: "司法考试", widthMm: 35, heightMm: 53, widthPx: 413, heightPx: 626, colors: ["blue", "white"], priority: 5 }),
    Object.assign({}, pending, { id: "national_judicial_exam_413_626", name: "国家司法考试", displayName: "国家司法考试", widthMm: 35, heightMm: 53, widthPx: 413, heightPx: 626, colors: ["blue", "white"], priority: 6 })
  ]);

  var social = setGroup("social_id_card", {
    groupId: "social_id_card",
    groupName: "社保 / 身份证类",
    displayMode: "group",
    category: "证件/社保",
    description: "白底证照，点击选择",
    defaultSpecId: "id_card_cn_358_441",
    colors: ["white", "blue"],
    icon: "🪪"
  });
  markSpecs(social, [
    Object.assign({}, pending, { id: "social_security_358_441", name: "社保卡", displayName: "社保卡", mergeName: "社保 / 身份证通用白底规格", appliesTo: "社保卡、身份证数码照、居住证", widthPx: 358, heightPx: 441, colors: ["white"], priority: 1 }),
    Object.assign({}, pending, { id: "id_card_cn_358_441", name: "身份证数码照", displayName: "身份证数码照", mergeName: "社保 / 身份证通用白底规格", appliesTo: "身份证数码照", widthPx: 358, heightPx: 441, colors: ["white"], priority: 2 }),
    Object.assign({}, pending, { id: "residence_permit_358_441", name: "居住证", displayName: "居住证", mergeName: "社保 / 身份证通用白底规格", appliesTo: "居住证", widthPx: 358, heightPx: 441, colors: ["white"], priority: 3 }),
    Object.assign({}, pending, { id: "general_white_id_295_413", name: "证件照通用白底", displayName: "证件照通用白底", widthMm: 25, heightMm: 35, widthPx: 295, heightPx: 413, colors: ["white"], priority: 4 })
  ]);

  var passport = setGroup("passport_visa", {
    groupId: "passport_visa",
    groupName: "护照 / 签证 / 出入境类",
    displayMode: "group",
    category: "证件/社保",
    description: "出入境规格，点击选择",
    defaultSpecId: "passport_cn_390_567",
    colors: ["white", "lightBlue"],
    icon: "🛂"
  });
  markSpecs(passport, [
    Object.assign({}, pending, { id: "passport_cn_390_567", name: "普通护照", displayName: "普通护照", mergeName: "护照 / 签证 / 出入境通用规格", appliesTo: "普通护照、签证照通用、港澳通行证、台湾通行证、出入境证件照", widthMm: 33, heightMm: 48, widthPx: 390, heightPx: 567, colors: ["white", "lightBlue"], priority: 1 }),
    Object.assign({}, pending, { id: "visa_general_390_567", name: "签证照通用", displayName: "签证照通用", mergeName: "护照 / 签证 / 出入境通用规格", appliesTo: "签证照通用", widthMm: 33, heightMm: 48, widthPx: 390, heightPx: 567, colors: ["white", "lightBlue"], priority: 2 }),
    Object.assign({}, pending, { id: "hongkong_macao_pass_390_567", name: "港澳通行证", displayName: "港澳通行证", mergeName: "护照 / 签证 / 出入境通用规格", appliesTo: "港澳通行证", widthPx: 390, heightPx: 567, colors: ["white", "lightBlue"], priority: 3 }),
    Object.assign({}, pending, { id: "taiwan_pass_390_567", name: "台湾通行证", displayName: "台湾通行证", mergeName: "护照 / 签证 / 出入境通用规格", appliesTo: "台湾通行证", widthPx: 390, heightPx: 567, colors: ["white", "lightBlue"], priority: 4 }),
    Object.assign({}, pending, { id: "entry_exit_photo_390_567", name: "出入境证件照", displayName: "出入境证件照", mergeName: "护照 / 签证 / 出入境通用规格", appliesTo: "出入境证件照", widthPx: 390, heightPx: 567, colors: ["white", "lightBlue"], priority: 5 })
  ]);
}

applyRegistrySpecGroups();

function patchSpecById(id, patch) {
  function applyToList(list) {
    (list || []).forEach(function(spec, index) {
      if (spec && spec.id === id) {
        list[index] = makeSpec(Object.assign({}, spec, patch));
      }
    });
  }
  applyToList(photoSpecs);
  specGroups.forEach(function(group) {
    applyToList(group.specs);
  });
}

function patchSpecsWhere(match, patch) {
  function applyToList(list) {
    (list || []).forEach(function(spec, index) {
      if (spec && match(spec)) {
        var nextPatch = typeof patch === "function" ? patch(spec) : patch;
        list[index] = makeSpec(Object.assign({}, spec, nextPatch));
      }
    });
  }
  applyToList(photoSpecs);
  specGroups.forEach(function(group) {
    applyToList(group.specs);
  });
}

function applySpecCleanupCatalog() {
  var commonNotice = "规格可能随地区和报名平台调整，请以当年官方公告为准。";
  var platformNotice = "非全国统一通用规格，请按具体报名平台要求。";

  patchSpecsWhere(function() { return true; }, function(spec) {
    var level = normalizeSourceLevel(spec.sourceLevel);
    return {
      sourceLevel: level === "unknown" ? "platform" : level,
      notice: spec.notice || spec.note || commonNotice,
      note: spec.notice || spec.note || commonNotice,
      category: spec.category || "平台特殊 / 自定义",
      enabled: spec.enabled !== false && spec.active !== false,
      active: spec.enabled !== false && spec.active !== false
    };
  });

  patchSpecById("yicun", {
    name: "一寸",
    displayName: "一寸照",
    category: "常用证件照",
    sourceLevel: "official",
    enabled: true,
    sort: 1,
    notice: "常用一寸证件照，提交前仍需以具体平台公告为准。"
  });
  patchSpecById("xiaoyicun", {
    name: "小一寸",
    displayName: "小一寸照",
    category: "常用证件照",
    sourceLevel: "local_common",
    enabled: true,
    sort: 2,
    notice: "小一寸为常用地方/平台尺寸，请以提交平台公告为准。"
  });
  patchSpecById("ercun", {
    name: "二寸",
    displayName: "二寸照",
    category: "常用证件照",
    sourceLevel: "official",
    enabled: true,
    sort: 3,
    notice: "二寸证件照，不等同所有考试报名系统固定要求。"
  });
  patchSpecById("dayicun", {
    name: "大一寸",
    displayName: "大一寸照",
    category: "地方常用",
    sourceLevel: "local_common",
    enabled: true,
    sort: 4,
    notice: "部分事业单位、部分省份公考或地方平台可能使用，非全国统一顶级标准，请以当年公告为准。"
  });
  patchSpecById("xiaoercun", {
    name: "大二寸 / 常用报名照",
    displayName: "大二寸 / 常用报名照",
    category: "地方常用",
    sourceLevel: "local_common",
    enabled: true,
    notice: "35×45mm 常见于部分报名平台，不是全国公务员唯一标准。"
  });

  patchSpecById("jiaoshi", {
    name: "教师资格证报名照",
    displayName: "教师资格证报名照",
    category: "考试报名",
    sourceLevel: "platform",
    colors: ["white", "blue"],
    bgColors: ["white", "blue"],
    defaultBg: "white",
    enabled: true,
    notice: "各省报名系统可能调整，请以当年公告为准。"
  });
  patchSpecById("teacher_cert_295_413", {
    name: "教师资格证报名照",
    displayName: "教师资格证报名照",
    category: "考试报名",
    sourceLevel: "platform",
    colors: ["white", "blue"],
    bgColors: ["white", "blue"],
    defaultBg: "white",
    maxFileKB: null,
    fileSizeLimit: "按报名系统要求",
    enabled: true,
    sort: 1,
    notice: "各省报名系统可能调整，请以当年公告为准。"
  });
  patchSpecsWhere(function(spec) {
    return ["teacher_cert_150_200", "teacher_cert_180_240", "teacher_cert_384_512"].indexOf(spec.id) >= 0;
  }, {
    category: "平台特殊 / 自定义",
    sourceLevel: "deprecated",
    enabled: false,
    active: false,
    notice: "历史/平台特殊规格，不作为教师资格证全国官方通用默认入口。"
  });
  patchSpecById("teacher_cert_400_600", {
    category: "平台特殊 / 自定义",
    sourceLevel: "platform",
    enabled: false,
    active: false,
    notice: "平台特殊像素规格，请以对应报名系统要求为准。"
  });
  patchSpecById("teacher_cert_413_579", {
    category: "平台特殊 / 自定义",
    sourceLevel: "platform",
    enabled: false,
    active: false,
    notice: "二寸类历史/平台规格，不作为教师资格证默认官方通用入口。"
  });

  patchSpecById("civil_service", {
    name: "公务员考试报名照",
    displayName: "公务员考试报名照",
    category: "考试报名",
    widthMm: 25,
    heightMm: 35,
    widthPx: 295,
    heightPx: 413,
    colors: ["blue", "white"],
    bgColors: ["blue", "white"],
    defaultBg: "blue",
    sourceLevel: "official",
    enabled: true,
    notice: "国考/省考报名系统通常需通过照片处理工具，最终以当年公告为准。"
  });
  patchSpecById("civil_service_common", {
    name: "公务员考试报名照",
    displayName: "公务员考试报名照",
    mergeName: "公务员考试报名照",
    category: "考试报名",
    widthMm: 25,
    heightMm: 35,
    widthPx: 295,
    heightPx: 413,
    colors: ["blue", "white"],
    bgColors: ["blue", "white"],
    defaultBg: "blue",
    sourceLevel: "official",
    enabled: true,
    sort: 1,
    notice: "国考/省考报名系统通常需通过照片处理工具，最终以当年公告为准。"
  });
  patchSpecById("civil_service_min_295_413", {
    enabled: false,
    active: false,
    sourceLevel: "deprecated",
    category: "平台特殊 / 自定义",
    notice: "已合并到公务员考试报名照主规格。"
  });
  patchSpecsWhere(function(spec) {
    return spec.id === "civil_service_two_inch" || spec.id === "civil_service_413_626" || /^civil_service_province_/.test(spec.id || "");
  }, {
    category: "平台特殊 / 自定义",
    sourceLevel: "deprecated",
    enabled: false,
    active: false,
    notice: "公务员报名不再默认使用该尺寸，请以当年报名系统照片处理工具为准。"
  });

  patchSpecById("driver", {
    name: "驾驶证照片",
    displayName: "驾驶证照片",
    category: "驾驶证 / 社保 / 身份证",
    widthMm: 22,
    heightMm: 32,
    widthPx: 260,
    heightPx: 378,
    colors: ["white"],
    bgColors: ["white"],
    defaultBg: "white",
    sourceLevel: "official",
    enabled: true,
    notice: "驾驶证照片通常要求白底、正面免冠、头部宽 14mm–16mm、头部长 19mm–22mm，具体以上传平台为准。"
  });
  patchSpecById("driver_common", {
    name: "驾驶证照片",
    displayName: "驾驶证照片",
    category: "驾驶证 / 社保 / 身份证",
    widthMm: 22,
    heightMm: 32,
    widthPx: 260,
    heightPx: 378,
    colors: ["white"],
    bgColors: ["white"],
    defaultBg: "white",
    sourceLevel: "official",
    enabled: true,
    notice: "驾驶证照片通常要求白底、正面免冠、头部宽 14mm–16mm、头部长 19mm–22mm，具体以上传平台为准。"
  });
  patchSpecsWhere(function(spec) {
    return /^driver_(guangdong|province|other)/.test(spec.id || "");
  }, {
    category: "平台特殊 / 自定义",
    sourceLevel: "platform",
    enabled: false,
    active: false,
    notice: "地方/平台历史规格，不作为驾驶证默认规格。"
  });

  patchSpecsWhere(function(spec) {
    return /^accounting_/.test(spec.id || "") || spec.id === "accounting";
  }, {
    category: "考试报名",
    sourceLevel: "platform",
    notice: "会计报名系统要求可能按年份和地区变化，请以报名系统照片审核工具为准。"
  });
  patchSpecById("accounting", {
    name: "会计职称考试报名照",
    displayName: "会计职称考试报名照",
    widthMm: 25,
    heightMm: 35,
    widthPx: 295,
    heightPx: 413,
    enabled: true
  });
  patchSpecById("accounting_junior_295_413", {
    name: "会计职称考试报名照",
    displayName: "会计职称考试报名照",
    enabled: true,
    sort: 1
  });
  patchSpecById("accounting_middle_295_413", {
    name: "会计职称考试报名照",
    displayName: "会计职称考试报名照",
    enabled: true,
    sort: 2
  });
  patchSpecsWhere(function(spec) {
    return ["accounting_middle_114_156", "accounting_middle_240_320", "accounting_middle_shanghai_215_300"].indexOf(spec.id) >= 0;
  }, {
    category: "平台特殊 / 自定义",
    sourceLevel: "platform",
    enabled: false,
    active: false,
    notice: "平台特殊或低分辨率历史规格，不作为会计/职称考试主推入口。"
  });

  patchSpecsWhere(function(spec) {
    return ["nurse_exam_295_413", "doctor_exam_413_531", "guide_exam_295_413"].indexOf(spec.id) >= 0;
  }, {
    category: "考试报名",
    sourceLevel: "platform",
    enabled: true,
    notice: "具体考试公告可能调整，请以实际报名平台要求为准。"
  });
  patchSpecById("insurance_practice_210_370", {
    category: "平台特殊 / 自定义",
    sourceLevel: "unknown",
    enabled: false,
    active: false,
    notice: "非全国统一通用规格，请按具体报名平台要求。"
  });
  patchSpecsWhere(function(spec) {
    return /judicial/.test(spec.id || "");
  }, {
    category: "平台特殊 / 自定义",
    sourceLevel: "platform",
    enabled: false,
    active: false,
    notice: platformNotice
  });

  patchSpecsWhere(function(spec) {
    return ["social_security_358_441", "id_card_cn_358_441", "residence_permit_358_441"].indexOf(spec.id || "") >= 0;
  }, {
    widthMm: 26,
    heightMm: 32,
    sourceLevel: "official",
    enabled: true
  });
  patchSpecsWhere(function(spec) {
    return ["hongkong_macao_pass_390_567", "taiwan_pass_390_567", "entry_exit_photo_390_567"].indexOf(spec.id || "") >= 0;
  }, {
    widthMm: 33,
    heightMm: 48,
    sourceLevel: "local_common",
    enabled: true
  });
  patchSpecsWhere(function(spec) {
    return ["passport_cn_390_567", "visa_general_390_567", "hongkong_macao_pass_390_567", "taiwan_pass_390_567", "entry_exit_photo_390_567"].indexOf(spec.id || "") >= 0;
  }, {
    keepSeparate: true,
    enabled: true,
    active: true,
    showInSearch: true,
    showInCategory: true
  });

  patchSpecsWhere(function(spec) {
    return /^school_|^enroll_|^college_|_enroll_/.test(spec.id || "") || spec.id === "student_image";
  }, {
    category: "学籍 / 入学",
    sourceLevel: "platform",
    notice: "学校/学信网/报名平台可能有自定义像素要求，请以通知为准。"
  });
  patchSpecsWhere(function(spec) {
    return ["enroll_295_413", "college_enroll_413_531", "enroll_small_two_413_531"].indexOf(spec.id) >= 0;
  }, {
    sourceLevel: "local_common",
    enabled: true
  });
  patchSpecsWhere(function(spec) {
    return ["school_status_307_378", "school_net_472_630", "school_qingdao_fushan_195_240", "school_lingnan_120_150", "school_status_390_480", "school_status_150_200", "school_status_90_120", "school_status_300_420", "primary_enroll_300_420", "cau_enroll_420_564", "bnu_enroll_250_350", "znufe_enroll_180_240"].indexOf(spec.id) >= 0;
  }, {
    category: "平台特殊 / 自定义",
    sourceLevel: "platform",
    enabled: false,
    active: false,
    notice: "学校/平台自定义像素规格，不作为通用官方规格。"
  });

  patchSpecsWhere(function(spec) {
    return (spec.widthMm === 33 && spec.heightMm === 48) || (spec.widthPx === 390 && spec.heightPx === 567);
  }, function(spec) {
    if (spec.id === "dayicun") return {};
    return {
      sourceLevel: "local_common",
      category: spec.category === "考试报名" ? "地方常用" : (spec.category || "地方常用"),
      notice: spec.notice || "部分地方平台可能使用，非全国统一顶级标准，请以当年公告为准。"
    };
  });

  var restoreVisibleIds = {
    teacher_cert_413_579: true,
    teacher_cert_400_600: true,
    teacher_cert_180_240: true,
    teacher_cert_150_200: true,
    teacher_cert_384_512: true,
    teacher_cert_province_pending: true,
    civil_service_min_295_413: true,
    civil_service_two_inch: true,
    civil_service_413_626: true,
    driver_guangdong_common: true,
    driver_other_province_common: true,
    accounting_middle_240_320: true,
    accounting_middle_114_156: true,
    accounting_middle_shanghai_215_300: true,
    school_status_307_378: true,
    school_net_472_630: true,
    school_qingdao_fushan_195_240: true,
    school_lingnan_120_150: true,
    school_status_390_480: true,
    school_status_150_200: true,
    school_status_90_120: true,
    school_status_300_420: true,
    primary_enroll_300_420: true,
    cau_enroll_420_564: true,
    bnu_enroll_250_350: true,
    znufe_enroll_180_240: true,
    insurance_practice_210_370: true,
    judicial_exam_413_626: true,
    national_judicial_exam_413_626: true
  };
  patchSpecsWhere(function(spec) {
    return restoreVisibleIds[spec.id || ""] === true || /^civil_service_province_/.test(spec.id || "");
  }, function(spec) {
    var id = spec.id || "";
    var level = spec.sourceLevel || "platform";
    var category = spec.category || "平台特殊 / 自定义";
    var notice = spec.notice || platformNotice;
    if (/^teacher_cert_(150_200|180_240|384_512|400_600|413_579)$/.test(id)) {
      level = id === "teacher_cert_413_579" ? "platform" : "deprecated";
      category = "平台特殊 / 自定义";
      notice = "平台特殊/历史规格，按报名公告为准；不作为教师资格证全国官方通用主推入口。";
    } else if (/^civil_service_/.test(id)) {
      level = id === "civil_service_min_295_413" ? "official" : "deprecated";
      category = "平台特殊 / 自定义";
      notice = "公务员/国考历史或平台规格，按当年报名系统公告为准；不作为全国唯一默认标准。";
    } else if (/^driver_/.test(id)) {
      level = "platform";
      category = "平台特殊 / 自定义";
      notice = "地方/平台驾驶证规格，按当地上传平台要求为准；不覆盖 22x32mm 白底通用规格。";
    } else if (/^accounting_middle_/.test(id)) {
      level = "platform";
      category = "平台特殊 / 自定义";
      notice = "会计/职称平台特殊或历史规格，按报名系统照片审核工具为准，不作为主推通用规格。";
    } else if (/^school_|^primary_|_enroll_/.test(id)) {
      level = "platform";
      category = "学籍 / 入学";
      notice = "学校/平台自定义像素规格，按学校通知或报名平台要求为准。";
    } else if (id === "insurance_practice_210_370") {
      level = "platform";
      category = "平台特殊 / 自定义";
      notice = "18x31mm 平台特殊/执业证件规格，按具体报名平台要求为准。";
    } else if (/judicial/.test(id)) {
      level = "platform";
      category = "平台特殊 / 自定义";
      notice = "司法考试历史/平台规格，按具体报名平台要求为准。";
    }
    return {
      category: category,
      sourceLevel: level,
      enabled: true,
      active: true,
      showInHome: false,
      showInSearch: true,
      showInCategory: true,
      notice: notice,
      note: notice
    };
  });

  setGroup("one_inch", {
    groupId: "one_inch",
    groupName: "一寸",
    displayMode: "single",
    category: "常用证件照",
    description: "25×35mm | 295×413px",
    defaultSpecId: "yicun",
    colors: ["blue", "white", "red", "lightBlue", "gray"],
    icon: "👤",
    popular: true,
    enabled: true
  });
  setGroup("small_one_inch", {
    groupId: "small_one_inch",
    groupName: "小一寸",
    displayMode: "single",
    category: "常用证件照",
    description: "22×32mm | 260×378px",
    defaultSpecId: "xiaoyicun",
    colors: ["blue", "white", "red", "lightBlue", "gray"],
    icon: "👤",
    popular: true,
    enabled: true,
    specs: []
  });
  setGroup("two_inch", {
    groupId: "two_inch",
    groupName: "二寸",
    displayMode: "single",
    category: "常用证件照",
    description: "35×49mm | 413×579px",
    defaultSpecId: "ercun",
    colors: ["blue", "white", "red", "lightBlue", "gray"],
    icon: "👨",
    popular: true,
    enabled: true
  });
  setGroup("large_one_inch", {
    groupId: "large_one_inch",
    groupName: "大一寸",
    displayMode: "single",
    category: "地方常用",
    description: "33×48mm | 390×567px",
    defaultSpecId: "dayicun",
    colors: ["blue", "white", "red", "lightBlue", "gray"],
    icon: "👤",
    popular: true,
    enabled: true,
    specs: []
  });
  setGroup("teacher_cert", {
    groupName: "教师资格证报名照",
    category: "考试报名",
    description: "25×35mm | 295×413px",
    defaultSpecId: "teacher_cert_295_413",
    colors: ["white", "blue"],
    popular: true,
    enabled: true
  });
  setGroup("civil_service_exam", {
    groupName: "国考 / 公务员",
    category: "考试报名",
    description: "报名照按当年公告",
    defaultSpecId: "civil_service_common",
    colors: ["blue", "white"],
    popular: false,
    enabled: true
  });
  setGroup("driver_license", {
    groupName: "驾驶证照片",
    category: "驾驶证 / 社保 / 身份证",
    description: "22×32mm | 260×378px",
    defaultSpecId: "driver_common",
    colors: ["white"],
    popular: true,
    enabled: true
  });
  setGroup("accounting_title_exam", {
    groupName: "会计 / 职称考试",
    category: "考试报名",
    description: "报名照按平台审核工具",
    defaultSpecId: "accounting_junior_295_413",
    popular: false,
    enabled: true
  });
  setGroup("professional_license_exam", {
    groupName: "医护 / 导游等资格考试",
    category: "考试报名",
    description: "按具体考试公告",
    defaultSpecId: "nurse_exam_295_413",
    popular: false,
    enabled: true
  });
  setGroup("language_computer_exam", {
    category: "地方常用",
    description: "地方/平台常用报名尺寸",
    popular: false,
    enabled: true
  });
  setGroup("school_enrollment", {
    groupName: "学籍 / 入学",
    category: "学籍 / 入学",
    description: "学校/平台通知为准",
    defaultSpecId: "enroll_295_413",
    popular: false,
    enabled: true
  });
  setGroup("social_id_card", {
    category: "驾驶证 / 社保 / 身份证",
    popular: false,
    enabled: true
  });
  setGroup("passport_visa", {
    category: "驾驶证 / 社保 / 身份证",
    popular: false,
    enabled: true,
    mergeSpecs: false
  });
  setGroup("custom_size", {
    category: "平台特殊 / 自定义",
    popular: false,
    enabled: true
  });

  var order = {
    one_inch: 1,
    small_one_inch: 2,
    two_inch: 3,
    large_one_inch: 4,
    teacher_cert: 5,
    driver_license: 6,
    civil_service_exam: 20,
    accounting_title_exam: 21,
    professional_license_exam: 22,
    language_computer_exam: 30,
    school_enrollment: 40,
    social_id_card: 50,
    passport_visa: 51,
    custom_size: 90
  };
  specGroups.sort(function(a, b) {
    return (order[a.groupId] || 80) - (order[b.groupId] || 80);
  });
}

applySpecCleanupCatalog();

const purposeOptions = [
  { id: "official_id_photo", name: "官方证件照", mode: "official" },
  { id: "teacher_exam", name: "考试报名照", mode: "official" },
  { id: "id_card", name: "社保/身份证类", mode: "official" },
  { id: "passport", name: "护照/签证类", mode: "official" },
  { id: "resume", name: "简历头像照", mode: "creative" },
  { id: "career_portrait", name: "职业形象照", mode: "creative" },
  { id: "anime_avatar", name: "二次元头像照", mode: "anime" },
  { id: "creative_id_photo", name: "创意形象照", mode: "creative" }
];

const compositionOptions = [
  { id: "head_shoulder", name: "头肩照" },
  { id: "shoulder_avatar", name: "肩宽头像" },
  { id: "half_body", name: "上半身职业照" },
  { id: "square_avatar", name: "方形头像" }
];

const enhanceOptions = [
  { id: "none", name: "自然" },
  { id: "standard", name: "标准" },
  { id: "light", name: "轻度增强" }
];

const advancedOutfitEnabled = true;
const experimentalOutfitDisabledReason = "当前模板为实验贴图效果，暂不开放正式使用";
const productionOutfitIds = {
  preserve_original: true,
  mist_gray_suit: true,
  elegant_black_suit: true,
  deep_blue_suit: true,
  red_tie_suit: true,
  pure_black_suit: true,
  white_shirt: true,
  business_blue: true,
  mens_black_suit: true,
  womens_black_suit: true,
  student_uniform: true
};

const outfitOptions = [
  { id: "preserve_original", name: "无服装", category: "base", available: true, supportedImageTypes: ["real_person", "anime", "cartoon", "illustration"], supportedPurposes: ["official_id_photo", "resume", "career_portrait", "creative_id_photo", "id_card", "social_security", "passport", "teacher_exam", "civil_service_exam", "anime_avatar"], compositionSupport: ["head_shoulder", "shoulder_avatar", "half_body", "square_avatar"] },
  { id: "mist_gray_suit", name: "雾灰正装", category: "real", available: true, supportedImageTypes: ["real_person"], supportedPurposes: ["official_id_photo", "resume", "career_portrait", "creative_id_photo", "id_card", "social_security", "passport", "teacher_exam", "civil_service_exam"], compositionSupport: ["head_shoulder", "shoulder_avatar", "half_body", "square_avatar"] },
  { id: "elegant_black_suit", name: "雅黑西装", category: "real", available: true, supportedImageTypes: ["real_person"], supportedPurposes: ["official_id_photo", "resume", "career_portrait", "creative_id_photo", "id_card", "social_security", "passport", "teacher_exam", "civil_service_exam"], compositionSupport: ["head_shoulder", "shoulder_avatar", "half_body", "square_avatar"] },
  { id: "deep_blue_suit", name: "深蓝西装", category: "real", available: true, supportedImageTypes: ["real_person"], supportedPurposes: ["official_id_photo", "resume", "career_portrait", "creative_id_photo", "id_card", "social_security", "passport", "teacher_exam", "civil_service_exam"], compositionSupport: ["head_shoulder", "shoulder_avatar", "half_body", "square_avatar"] },
  { id: "red_tie_suit", name: "红领西装", category: "real", available: true, supportedImageTypes: ["real_person"], supportedPurposes: ["official_id_photo", "resume", "career_portrait", "creative_id_photo", "id_card", "social_security", "passport", "teacher_exam", "civil_service_exam"], compositionSupport: ["head_shoulder", "shoulder_avatar", "half_body", "square_avatar"] },
  { id: "pure_black_suit", name: "纯黑西装", category: "real", available: true, supportedImageTypes: ["real_person"], supportedPurposes: ["official_id_photo", "resume", "career_portrait", "creative_id_photo", "id_card", "social_security", "passport", "teacher_exam", "civil_service_exam"], compositionSupport: ["head_shoulder", "shoulder_avatar", "half_body", "square_avatar"] },
  { id: "white_shirt", name: "白衬衫", category: "real", available: true, supportedImageTypes: ["real_person"], supportedPurposes: ["official_id_photo", "resume", "career_portrait", "creative_id_photo", "id_card", "social_security", "passport", "teacher_exam", "civil_service_exam"], compositionSupport: ["head_shoulder", "shoulder_avatar", "half_body", "square_avatar"] },
  { id: "business_blue", name: "商务蓝", category: "real", available: true, supportedImageTypes: ["real_person"], supportedPurposes: ["official_id_photo", "resume", "career_portrait", "creative_id_photo", "id_card", "social_security", "passport", "teacher_exam", "civil_service_exam"], compositionSupport: ["head_shoulder", "shoulder_avatar", "half_body", "square_avatar"] },
  { id: "mens_black_suit", name: "男士黑西装", category: "real", available: true, supportedImageTypes: ["real_person"], supportedPurposes: ["official_id_photo", "resume", "career_portrait", "creative_id_photo", "id_card", "social_security", "passport", "teacher_exam", "civil_service_exam"], compositionSupport: ["head_shoulder", "shoulder_avatar", "half_body", "square_avatar"] },
  { id: "womens_black_suit", name: "女士黑西装", category: "real", available: true, supportedImageTypes: ["real_person"], supportedPurposes: ["official_id_photo", "resume", "career_portrait", "creative_id_photo", "id_card", "social_security", "passport", "teacher_exam", "civil_service_exam"], compositionSupport: ["head_shoulder", "shoulder_avatar", "half_body", "square_avatar"] },
  { id: "student_uniform", name: "学生制服", category: "real", available: true, supportedImageTypes: ["real_person"], supportedPurposes: ["official_id_photo", "resume", "career_portrait", "creative_id_photo", "id_card", "social_security", "passport", "teacher_exam", "civil_service_exam"], compositionSupport: ["head_shoulder", "shoulder_avatar", "half_body", "square_avatar"] },
  { id: "light_suit", name: "浅灰西装", category: "real", available: false, reason: "模板素材未接入", supportedImageTypes: ["real_person"], supportedPurposes: ["resume", "career_portrait"], compositionSupport: ["head_shoulder", "shoulder_avatar", "half_body", "square_avatar"] },
  { id: "anime_business", name: "二次元商务装", category: "anime", available: true, supportedImageTypes: ["anime", "cartoon", "illustration"], supportedPurposes: ["anime_avatar", "creative_id_photo", "resume", "career_portrait"], compositionSupport: ["head_shoulder", "shoulder_avatar", "half_body", "square_avatar"] },
  { id: "anime_school_uniform", name: "二次元校服", category: "anime", available: false, reason: "模板素材未接入", supportedImageTypes: ["anime", "cartoon", "illustration"], supportedPurposes: ["anime_avatar", "creative_id_photo", "resume", "career_portrait"], compositionSupport: ["head_shoulder", "shoulder_avatar", "half_body", "square_avatar"] },
  { id: "anime_suit", name: "二次元西装风格", category: "anime", available: true, supportedImageTypes: ["anime", "cartoon", "illustration"], supportedPurposes: ["anime_avatar", "creative_id_photo", "resume", "career_portrait"], compositionSupport: ["head_shoulder", "shoulder_avatar", "half_body", "square_avatar"] },
  { id: "anime_western", name: "二次元西式制服", category: "anime", available: false, reason: "模板素材未接入", supportedImageTypes: ["anime", "cartoon", "illustration"], supportedPurposes: ["anime_avatar", "creative_id_photo"], compositionSupport: ["head_shoulder", "shoulder_avatar", "half_body", "square_avatar"] },
  { id: "anime_white_shirt", name: "二次元白衬衫", category: "anime", available: false, reason: "模板素材未接入", supportedImageTypes: ["anime", "cartoon", "illustration"], supportedPurposes: ["anime_avatar", "creative_id_photo"], compositionSupport: ["head_shoulder", "shoulder_avatar", "half_body", "square_avatar"] }
];

outfitOptions.forEach(function(item) {
  if (productionOutfitIds[item.id]) {
    item.available = true;
    item.qualityLevel = "production";
    item.disabledReason = "";
    return;
  }
  item.available = false;
  item.qualityLevel = "experimental";
  item.reason = experimentalOutfitDisabledReason;
  item.disabledReason = experimentalOutfitDisabledReason;
});

const idPhotoSpecsV2 = [
  { id: "one-inch", name: "一寸照", purpose: "official_id_photo", category: "通用规格", sizeText: "25×35mm | 295×413px", widthPx: 295, heightPx: 413, defaultBg: "blue", composition: "head_shoulder", mode: "official" },
  { id: "two-inch", name: "二寸照", purpose: "official_id_photo", category: "通用规格", sizeText: "35×49mm | 413×579px", widthPx: 413, heightPx: 579, defaultBg: "blue", composition: "head_shoulder", mode: "official" },
  { id: "small-one-inch", name: "小一寸", purpose: "official_id_photo", category: "通用规格", sizeText: "22×32mm | 260×378px", widthPx: 260, heightPx: 378, defaultBg: "blue", composition: "head_shoulder", mode: "official" },
  { id: "large-one-inch", name: "大一寸", purpose: "official_id_photo", category: "通用规格", sizeText: "33×48mm | 390×567px", widthPx: 390, heightPx: 567, defaultBg: "blue", composition: "head_shoulder", mode: "official" },
  { id: "small-two-inch", name: "小二寸", purpose: "official_id_photo", category: "通用规格", sizeText: "35×45mm | 413×531px", widthPx: 413, heightPx: 531, defaultBg: "blue", composition: "head_shoulder", mode: "official" },
  { id: "large-two-inch", name: "大二寸", purpose: "official_id_photo", category: "通用规格", sizeText: "35×53mm | 413×626px", widthPx: 413, heightPx: 626, defaultBg: "blue", composition: "head_shoulder", mode: "official" },
  { id: "id-card-cn", name: "二代身份证数码照", purpose: "id_card", category: "身份证/社保卡类", sizeText: "358×441px | 350dpi | 白底", widthPx: 358, heightPx: 441, defaultBg: "white", composition: "head_shoulder", mode: "official" },
  { id: "social-security-cn", name: "社保卡数码照", purpose: "id_card", category: "身份证/社保卡类", sizeText: "358×441px | 白底 | 露双肩", widthPx: 358, heightPx: 441, defaultBg: "white", composition: "head_shoulder", mode: "official" },
  { id: "driver-license-cn", name: "机动车驾驶证相片", purpose: "driver_license", category: "身份证/社保卡类", sizeText: "22×32mm | 260×378px | 白底", widthPx: 260, heightPx: 378, defaultBg: "white", composition: "head_shoulder", mode: "official" },
  { id: "passport-cn", name: "普通护照照片", purpose: "passport", category: "护照/出入境类", sizeText: "33×48mm | 390×567px", widthPx: 390, heightPx: 567, defaultBg: "white", composition: "head_shoulder", mode: "official" },
  { id: "exit-entry-cn", name: "港澳通行证/出入境证件", purpose: "passport", category: "护照/出入境类", sizeText: "390×567px | 白/淡蓝底", widthPx: 390, heightPx: 567, defaultBg: "lightBlue", composition: "head_shoulder", mode: "official" },
  { id: "teacher-exam", name: "教师资格证报名照", purpose: "teacher_exam", category: "考试报名照", sizeText: "JPG/JPEG | 白底 | 不大于200K", widthPx: 295, heightPx: 413, defaultBg: "white", composition: "head_shoulder", mode: "official" },
  { id: "civil-service-exam", name: "公务员考试报名照", purpose: "teacher_exam", category: "考试报名照", sizeText: "413×531px | 正面免冠", widthPx: 413, heightPx: 531, defaultBg: "blue", composition: "head_shoulder", mode: "official" },
  { id: "postgraduate-exam", name: "研究生考试报名照", purpose: "teacher_exam", category: "考试报名照", sizeText: "390×567px | 白底", widthPx: 390, heightPx: 567, defaultBg: "white", composition: "head_shoulder", mode: "official" },
  { id: "cet-exam", name: "英语四六级报名照", purpose: "teacher_exam", category: "考试报名照", sizeText: "390×567px | JPG/JPEG", widthPx: 390, heightPx: 567, defaultBg: "blue", composition: "head_shoulder", mode: "official" },
  { id: "computer-exam", name: "计算机等级考试报名照", purpose: "teacher_exam", category: "考试报名照", sizeText: "390×567px", widthPx: 390, heightPx: 567, defaultBg: "blue", composition: "head_shoulder", mode: "official" },
  { id: "resume-headshot", name: "简历头像", purpose: "resume", category: "简历/职业", sizeText: "295×413px | 蓝/白/灰底", widthPx: 295, heightPx: 413, defaultBg: "gray", composition: "head_shoulder", mode: "creative" },
  { id: "career-headshot", name: "职业形象照", purpose: "career_portrait", category: "简历/职业", sizeText: "413×579px | 默认头肩照", widthPx: 413, heightPx: 579, defaultBg: "blue", composition: "head_shoulder", mode: "creative" },
  { id: "career-half-body", name: "半身职业照", purpose: "career_portrait", category: "简历/职业", sizeText: "413×579px | 上半身职业照", widthPx: 413, heightPx: 579, defaultBg: "blue", composition: "half_body", mode: "creative" },
  { id: "anime-blue-headshot", name: "二次元蓝底头像照", purpose: "anime_avatar", category: "二次元/创意", sizeText: "295×413px | 非官方用途", widthPx: 295, heightPx: 413, defaultBg: "blue", composition: "head_shoulder", mode: "anime" },
  { id: "anime-white-headshot", name: "二次元白底头像照", purpose: "anime_avatar", category: "二次元/创意", sizeText: "295×413px | 非官方用途", widthPx: 295, heightPx: 413, defaultBg: "white", composition: "head_shoulder", mode: "anime" },
  { id: "anime-red-headshot", name: "二次元红底头像照", purpose: "anime_avatar", category: "二次元/创意", sizeText: "295×413px | 非官方用途", widthPx: 295, heightPx: 413, defaultBg: "red", composition: "head_shoulder", mode: "anime" },
  { id: "anime-career", name: "二次元职业形象照", purpose: "anime_avatar", category: "二次元/创意", sizeText: "413×579px | 创意版", widthPx: 413, heightPx: 579, defaultBg: "blue", composition: "head_shoulder", mode: "anime" },
  { id: "creative-square-avatar", name: "创意方形头像", purpose: "creative_id_photo", category: "二次元/创意", sizeText: "512×512px | 头像展示", widthPx: 512, heightPx: 512, defaultBg: "lightBlue", composition: "square_avatar", mode: "creative" }
];

function cloneSpec(spec) {
  return makeSpec(Object.assign({}, spec, {
    bgColors: (spec.bgColors || spec.colors || ["blue", "white", "red"]).slice(),
    colors: (spec.colors || spec.bgColors || ["blue", "white", "red"]).slice(),
    fileFormat: (spec.fileFormat || ["jpg", "jpeg"]).slice(),
    aliases: (spec.aliases || []).slice()
  }));
}

function getColorById(id) {
  return bgColors.find(function(c) { return c.id === id; }) || bgColors[0];
}

function getGroupById(groupId) {
  return specGroups.find(function(g) { return g.groupId === groupId; }) || null;
}

function getAllGroupedSpecs() {
  var list = [];
  specGroups.forEach(function(group) {
    (group.specs || []).forEach(function(s) {
      var item = cloneSpec(s);
      item.groupId = group.groupId;
      item.groupName = group.groupName;
      item.searchText = [
        item.name,
        item.displayName,
        group.groupName,
        item.category,
        item.mm,
        item.px,
        item.widthPx && item.heightPx ? item.widthPx + "x" + item.heightPx : "",
        item.widthMm && item.heightMm ? item.widthMm + "x" + item.heightMm : "",
        item.appliesTo || "",
        item.province || "",
        item.city || "",
        (item.aliases || []).join(" "),
        item.sourceName || ""
      ].join(" ");
      list.push(item);
    });
  });
  return list;
}

function getAllSpecs() {
  var map = {};
  var list = [];
  photoSpecs.concat(getAllGroupedSpecs()).forEach(function(spec) {
    if (!map[spec.id] && isSpecEnabled(spec)) {
      map[spec.id] = true;
      list.push(cloneSpec(spec));
    }
  });
  return list;
}

function getSpecById(id) {
  return getAllSpecs().find(function(s) { return s.id === id; }) || null;
}

function specKey(spec) {
  return [
    spec.widthMm || "",
    spec.heightMm || "",
    spec.widthPx || "",
    spec.heightPx || "",
    (spec.colors || spec.bgColors || []).join(","),
    (spec.fileFormat || []).join(","),
    spec.minFileKB || "",
    spec.maxFileKB || ""
  ].join("|");
}

function mergeSameSpecs(list, groupName) {
  var merged = [];
  var map = {};
  list.forEach(function(spec) {
    var key = specKey(spec);
    if (!map[key]) {
      var item = cloneSpec(spec);
      item.name = spec.mergeName || spec.displayName || spec.name;
      item.displayName = item.name;
      item.aliases = [];
      item.applicableList = [];
      item._applicableMap = {};
      item.applicableText = spec.appliesTo ? ("适用：" + spec.appliesTo) : "";
      map[key] = item;
      merged.push(item);
    }
    var target = map[key];
    target.aliases.push(spec.displayName || spec.name);
    if (spec.appliesTo) {
      spec.appliesTo.split("、").forEach(function(name) {
        if (name && !target._applicableMap[name]) {
          target._applicableMap[name] = true;
          target.applicableList.push(name);
        }
      });
    }
    if ((target.sourceLevel || "third_party_pending") === "third_party_pending" && spec.sourceLevel && spec.sourceLevel !== "third_party_pending") {
      target.sourceLevel = spec.sourceLevel;
      target.sourceName = spec.sourceName;
      target.sourceUrl = spec.sourceUrl;
      target.sourceLabel = SOURCE_LABELS[spec.sourceLevel] || target.sourceLabel;
      target.sourceClass = "source-" + spec.sourceLevel;
    }
  });
  merged.forEach(function(item) {
    if (!item.applicableText && item.aliases.length > 1) {
      item.applicableText = "包含：" + item.aliases.slice(0, 6).join("、") + (item.aliases.length > 6 ? "等" : "");
    }
    if (item.applicableList.length > 1) {
      item.applicableText = "适用：" + item.applicableList.join("、");
    }
    delete item._applicableMap;
    item.groupName = groupName;
  });
  return merged;
}

function getGroupSpecs(groupId) {
  var group = getGroupById(groupId);
  if (!group) return [];
  var inlineSpecs = (group.specs || []).map(cloneSpec);
  var refs = (group.specIds || []).map(getSpecById).filter(Boolean);
  var combined = refs.concat(inlineSpecs);
  var visibleSpecs = group.mergeSpecs === false ? combined : mergeSameSpecs(combined, group.groupName);
  return visibleSpecs.filter(isSpecEnabled).sort(function(a, b) {
    return (a.sort || a.priority || 50) - (b.sort || b.priority || 50);
  });
}

function colorDots(colorIds) {
  return (colorIds || ["blue", "white", "red"]).map(function(cid) {
    var c = getColorById(cid);
    return { id: cid, hex: c ? c.hex : "#1a73e8" };
  });
}

function formatSpecSize(spec) {
  return [spec.mm, spec.px].filter(Boolean).join(" | ");
}

function getVisibleSourceBadge(sourceLevel) {
  var level = normalizeSourceLevel(sourceLevel || "unknown");
  return SOURCE_LABELS[level] || SOURCE_LABELS.unknown;
}

function getVisibleSpecNote(spec) {
  var note = (spec && spec.note ? spec.note : "").toString();
  if (!note || note.indexOf("待核验") >= 0) return "";
  return note;
}

function getShortApplicableText(spec) {
  var text = "";
  if (spec) {
    text = spec.applicableText || (spec.appliesTo ? ("适用：" + spec.appliesTo) : "");
  }
  text = (text || "").toString().replace(/\s+/g, " ").trim();
  return text.length > 38 ? text.slice(0, 38) + "..." : text;
}

function getSpecGroupCards(category) {
  return specGroups.filter(function(group) {
    if (group.enabled === false) return false;
    if (!category) return group.popular === true;
    return category === "全部" || group.category === category;
  }).map(function(group) {
    return {
      id: group.groupId,
      type: group.displayMode === "single" ? "spec" : group.displayMode,
      specId: group.defaultSpecId,
      groupId: group.groupId,
      name: group.groupName,
      size: group.description,
      category: group.category,
      icon: group.icon || "📷",
      thumbBg: "#e8f0fe",
      colors: colorDots(group.colors),
      badge: group.displayMode === "group" ? "选择" : ""
    };
  });
}

function toSpecCard(spec) {
  var sourceLevel = normalizeSourceLevel(spec.sourceLevel || "unknown");
  return {
    id: spec.id,
    type: "spec",
    specId: spec.id,
    groupId: spec.groupId || "",
    name: spec.displayName || spec.name,
    size: formatSpecSize(spec),
    category: spec.category || "",
    icon: spec.groupName && spec.groupName.indexOf("驾驶") >= 0 ? "🚗" : "📷",
    thumbBg: "#e8f0fe",
    colors: colorDots(spec.colors || spec.bgColors),
    badge: "",
    applicableText: "",
    sourceLevel: sourceLevel,
    sourceBadge: getVisibleSourceBadge(sourceLevel),
    sourceClass: "source-" + sourceLevel,
    fileText: spec.fileText || ((spec.fileFormat || ["jpg", "jpeg"]).join("/").toUpperCase()),
    note: "",
    applicableText: getShortApplicableText(spec),
    priority: spec.sort || spec.priority || 50
  };
}

function normalizeSearchText(value) {
  return (value || "").toString().toLowerCase().replace(/[×＊*]/g, "x").replace(/\s+/g, " ").trim();
}

function sourceRank(level) {
  var ranks = {
    official: 5,
    local_common: 4,
    platform: 3,
    deprecated: 1,
    unknown: 0,
    custom: 0
  };
  return ranks[normalizeSourceLevel(level)] || 0;
}

function searchSpecEntries(keyword) {
  var kw = normalizeSearchText(keyword);
  if (!kw) return [];
  var seen = {};
  var tokens = kw.split(/\s+/).filter(Boolean);
  return getAllSpecs().map(function(spec) {
    var text = normalizeSearchText([
      spec.name,
      spec.displayName,
      spec.groupName,
      spec.category,
      spec.mm,
      spec.px,
      spec.widthPx && spec.heightPx ? spec.widthPx + "x" + spec.heightPx : "",
      spec.widthMm && spec.heightMm ? spec.widthMm + "x" + spec.heightMm : "",
      spec.appliesTo || "",
      spec.province || "",
      spec.city || "",
      (spec.aliases || []).join(" "),
      spec.sourceName || ""
    ].join(" "));
    var score = 0;
    if (text.indexOf(kw) >= 0) score += 100;
    if (normalizeSearchText(spec.name).indexOf(kw) >= 0) score += 60;
    if (normalizeSearchText(spec.displayName).indexOf(kw) >= 0) score += 60;
    if (normalizeSearchText(spec.province).indexOf(kw) >= 0 || normalizeSearchText(spec.city).indexOf(kw) >= 0) score += 40;
    var matchedTokens = 0;
    tokens.forEach(function(part) {
      if (part && text.indexOf(part) >= 0) {
        matchedTokens += 1;
        score += 10;
      }
    });
    if (tokens.length > 1 && matchedTokens < tokens.length && text.indexOf(kw) < 0) score = 0;
    if (kw.indexOf("入学") >= 0 && kw.indexOf("学籍") >= 0 && (text.indexOf("入学") >= 0 || text.indexOf("学籍") >= 0)) score += 80;
    return { spec: spec, score: score };
  }).filter(function(item) {
    return item.score > 0;
  }).sort(function(a, b) {
    if (b.score !== a.score) return b.score - a.score;
    if (sourceRank(b.spec.sourceLevel) !== sourceRank(a.spec.sourceLevel)) {
      return sourceRank(b.spec.sourceLevel) - sourceRank(a.spec.sourceLevel);
    }
    return (a.spec.priority || 50) - (b.spec.priority || 50);
  }).filter(function(item) {
    var key = item.spec.keepSeparate
      ? ((item.spec.id || item.spec.displayName || item.spec.name) + "|" + specKey(item.spec))
      : ((item.spec.mergeName || item.spec.displayName || item.spec.name) + "|" + specKey(item.spec));
    if (seen[key]) return false;
    seen[key] = true;
    return true;
  }).map(function(item) {
    return toSpecCard(item.spec);
  });
}

function searchSpecs(keyword) {
  return searchSpecEntries(keyword).map(function(item) {
    return getSpecById(item.specId);
  }).filter(Boolean);
}

function getSpecsByCategory(cat) {
  if (!cat || cat === 'all') return getAllSpecs();
  return getAllSpecs().filter(function(s) { return s.category === cat || s.groupName === cat; });
}

function getV2SpecsByPurpose(purpose) {
  return idPhotoSpecsV2.filter(function(s) { return s.purpose === purpose; });
}

function getV2SpecById(id) {
  return idPhotoSpecsV2.find(function(s) { return s.id === id; }) || idPhotoSpecsV2[0];
}

function getPurposeById(id) {
  return purposeOptions.find(function(p) { return p.id === id; }) || purposeOptions[0];
}

function createCustomSpec(widthMm, heightMm, widthPx, heightPx) {
  return makeSpec({
    id: 'custom_' + Date.now(),
    name: '自定义',
    displayName: '自定义尺寸',
    mm: (widthMm || '?') + '×' + (heightMm || '?') + 'mm',
    widthMm: widthMm || 25,
    heightMm: heightMm || 35,
    px: (widthPx || '?') + '×' + (heightPx || '?') + 'px',
    widthPx: widthPx || 295,
    heightPx: heightPx || 413,
    category: "自定义",
    defaultBg: "blue",
    bgColors: ["blue", "white", "red", "lightBlue", "gray", "darkBlue"],
    colors: ["blue", "white", "red", "lightBlue", "gray", "darkBlue"],
    sourceLevel: "custom",
    sourceName: "用户自定义尺寸",
    note: "自定义尺寸，请按实际提交平台要求核对",
    isCustom: true
  });
}

module.exports = {
  photoSpecs: photoSpecs,
  specGroups: specGroups,
  bgColors: bgColors,
  sourceLabels: SOURCE_LABELS,
  getSpecById: getSpecById,
  getColorById: getColorById,
  searchSpecs: searchSpecs,
  searchSpecEntries: searchSpecEntries,
  getSpecGroupCards: getSpecGroupCards,
  getGroupById: getGroupById,
  getGroupSpecs: getGroupSpecs,
  formatSpecSize: formatSpecSize,
  getVisibleSourceBadge: getVisibleSourceBadge,
  getVisibleSpecNote: getVisibleSpecNote,
  getSpecsByCategory: getSpecsByCategory,
  createCustomSpec: createCustomSpec,
  purposeOptions: purposeOptions,
  compositionOptions: compositionOptions,
  enhanceOptions: enhanceOptions,
  outfitOptions: outfitOptions,
  advancedOutfitEnabled: advancedOutfitEnabled,
  idPhotoSpecsV2: idPhotoSpecsV2,
  getV2SpecsByPurpose: getV2SpecsByPurpose,
  getV2SpecById: getV2SpecById,
  getPurposeById: getPurposeById
};
