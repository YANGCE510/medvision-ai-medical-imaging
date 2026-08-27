const riskMap = {
  low: { label: "常规复核", tone: "review" },
  intermediate: { label: "建议复核", tone: "focus" },
  moderate: { label: "建议复核", tone: "focus" },
  medium: { label: "建议复核", tone: "focus" },
  high: { label: "建议重点复核", tone: "priority" }
};

const chineseRiskMap = {
  "低风险": "low",
  "中风险": "intermediate",
  "高风险": "high",
  "常规复核": "low",
  "建议复核": "intermediate",
  "建议重点复核": "high"
};

const readableLabels = {
  adrenal_gland_left: "左侧肾上腺",
  adrenal_gland_right: "右侧肾上腺",
  right_adrenal_region: "右侧肾上腺区域",
  left_adrenal_region: "左侧肾上腺区域",
  kidney_left: "左肾",
  kidney_right: "右肾",
  liver: "肝脏",
  inferior_vena_cava: "下腔静脉",
  aorta: "主动脉",
  pancreas: "胰腺",
  duodenum: "十二指肠",
  right: "右侧",
  left: "左侧"
};

function normalizeRisk(value) {
  const raw = String(value || "").trim();
  const key = (chineseRiskMap[raw] || raw).toLowerCase();
  return riskMap[key] || { label: "建议复核", tone: "focus" };
}

function parseMaybeJson(value) {
  if (!value) {
    return {};
  }
  if (typeof value === "object") {
    return value;
  }
  try {
    return JSON.parse(value);
  } catch (error) {
    return {};
  }
}

function readableLabel(value) {
  const text = String(value || "").trim();
  if (!text) {
    return "待医生确认";
  }
  return readableLabels[text.toLowerCase()] || text.replace(/_/g, " ");
}

function formatVolume(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "-";
  }
  return `${number.toFixed(3).replace(/\.?0+$/, "")} ml`;
}

function firstNumericValue(...values) {
  for (const value of values) {
    if (value === null || value === undefined || value === "") {
      continue;
    }
    const number = Number(value);
    if (Number.isFinite(number)) {
      return number;
    }
  }
  return null;
}

function formatDistance(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "-";
  }
  return `${number.toFixed(1).replace(/\.?0+$/, "")} mm`;
}

function patientReason(reason) {
  const text = String(reason || "");
  if (!text.trim()) {
    return "";
  }
  if (/inferior_vena_cava|aorta|血管|距离|贴近|重叠|abutment|overlap/i.test(text)) {
    return "病灶周围结构关系需要医生结合原始影像进一步复核。";
  }
  if (/组件|多灶|multifocal/i.test(text)) {
    return "影像中存在需要医生进一步确认的区域。";
  }
  if (/缺少|missing|临床资料/i.test(text)) {
    return "完整判断还需要结合医生问诊、检查结果和既往病史。";
  }
  return text.replace(/[A-Za-z][A-Za-z0-9_]+/g, (token) => readableLabel(token));
}

function unique(items) {
  return [...new Set(items.filter(Boolean))];
}

function buildPatientReport(raw) {
  const riskJson = parseMaybeJson(raw.riskJson);
  const metrics = parseMaybeJson(raw.metricsJson);
  const risk = normalizeRisk(raw.riskLevel || riskJson.overall_level);
  const tumorBurden = metrics.tumor_burden || {};
  const origin = metrics.origin_assessment || {};
  const location = readableLabel(origin.suspected_origin || metrics.tumor_side_by_nearest_kidney);
  const volume = formatVolume(firstNumericValue(
    raw.tumorVolumeMl,
    metrics.tumor_volume_ml,
    tumorBurden.tumor_volume_ml
  ));
  const maxDiameter = formatDistance(tumorBurden.max_diameter_mm);
  const reasons = unique((riskJson.reasons || []).map(patientReason)).slice(0, 3);

  return {
    taskId: raw.taskId,
    patientName: raw.patientName,
    originalFilename: raw.originalFilename,
    createdAt: raw.createdAt || "已生成",
    doctorReviewNote: String(raw.doctorReviewNote || "").trim(),
    riskLabel: risk.label,
    riskTone: risk.tone,
    statusText: "医生已确认",
    overview: `本次影像分析提示${location}存在需要医生复核的影像发现。请结合门诊医生意见理解报告。`,
    measurements: [
      { label: "大致位置", value: location },
      { label: "病灶体积", value: volume },
      { label: "最大径", value: maxDiameter }
    ],
    reviewPoints: reasons.length ? reasons : [
      "请医生结合原始影像进一步确认病灶位置和周围结构关系。",
      "影像分析结果需要结合病史、症状和其他检查共同判断。"
    ],
    suggestions: [
      "复诊时携带本次报告和既往检查资料。",
      "可以向医生确认是否需要结合血液或尿液相关检查。",
      "如果出现明显不适，请及时联系医生或就医。"
    ],
    disclaimer: "本页面用于帮助理解报告内容，不能替代医生诊断或治疗建议。"
  };
}

module.exports = {
  buildPatientReport,
  normalizeRisk,
  readableLabel
};
