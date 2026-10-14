export const REPORT_TYPES = [
  '血常规',
  '尿常规',
  '便常规',
  '生化全项',
  '肝功能',
  '肾功能',
  '凝血功能',
  '甲状腺功能',
  '糖代谢',
  '免疫学检查',
  '微生物检查',
  '其他',
]

export function reportTypeOptions(currentType) {
  const current = currentType?.trim()
  if (current && !REPORT_TYPES.includes(current)) return [current, ...REPORT_TYPES]
  return REPORT_TYPES
}

export function reportMetadataDraft(report) {
  return {
    patientLabel: report?.patient_label ?? '',
    examType: report?.exam_type ?? '',
    collectedAt: report?.collected_at ?? '',
    hospital: report?.hospital ?? '',
  }
}

export function validateReportMetadata(draft) {
  const errors = {}
  if (!draft.patientLabel.trim()) errors.patientLabel = '请填写报告标签'
  if (!draft.examType.trim()) errors.examType = '请填写检查类型'
  if (!draft.collectedAt) errors.collectedAt = '请选择检查日期'
  return errors
}

export function reportMetadataPayload(draft) {
  return {
    patient_label: draft.patientLabel.trim(),
    exam_type: draft.examType.trim(),
    collected_at: draft.collectedAt,
    hospital: draft.hospital.trim(),
  }
}
