export function referenceFromAnalyte(analyte) {
  if (analyte.status !== 'confirmed' && analyte.raw_ref_range) return analyte.raw_ref_range
  if (analyte.status === 'confirmed' && analyte.ref_text) return analyte.ref_text
  if (analyte.ref_low != null && analyte.ref_high != null) return `${analyte.ref_low}-${analyte.ref_high}`
  if (analyte.ref_low != null) return `>=${analyte.ref_low}`
  if (analyte.ref_high != null) return `<=${analyte.ref_high}`
  return analyte.raw_ref_range || ''
}

export function draftFromAnalyte(analyte) {
  return {
    name: analyte.name || '',
    category: analyte.category || '其他',
    value:
      analyte.status === 'confirmed' && analyte.value != null
        ? String(analyte.value)
        : analyte.status === 'confirmed' && analyte.result_text
          ? String(analyte.result_text)
          : String(analyte.raw_value ?? analyte.value ?? ''),
    unit:
      analyte.status === 'confirmed'
        ? String(analyte.unit ?? '')
        : String(analyte.raw_unit ?? analyte.unit ?? ''),
    ref: referenceFromAnalyte(analyte),
  }
}

export function isNumericText(value) {
  const text = String(value ?? '').trim()
  return /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)\s*[↑↓]?$/.test(text)
}

const QUALITATIVE_TERMS = new Set([
  '阴性', '阳性', '弱阳性', '可疑阳性', '未检出', '检出', '未见', '正常', '微量', '痕量',
])
const QUALITATIVE_GRADE_RE = /^(?:[-＋+]{1,4}|[1-4][＋+]|±)$/
const QUALITATIVE_WRAPPED_RE = /^(?:阴性\s*[（(]\s*[-－]\s*[）)]|(?:弱阳性|阳性)\s*[（(]\s*[＋+]\s*[）)])$/

export function qualitativeResultText(value) {
  const text = String(value ?? '').trim()
  if (!text) return null
  if (QUALITATIVE_TERMS.has(text)) return text
  if (QUALITATIVE_GRADE_RE.test(text) || QUALITATIVE_WRAPPED_RE.test(text)) return text
  return null
}

export function resultKind(value) {
  if (isNumericText(value)) return 'numeric'
  if (qualitativeResultText(value)) return 'qualitative'
  return null
}

export function payloadFromDraft(draft, status) {
  const clean = (value) => {
    const text = String(value ?? '').trim()
    return text || null
  }

  return {
    name: clean(draft.name),
    category: clean(draft.category) || '其他',
    value: clean(draft.value),
    unit: clean(draft.unit),
    ref_range: clean(draft.ref),
    status,
  }
}

export function batchReviewItem(analyte) {
  const draft = draftFromAnalyte(analyte)
  if (analyte.status === 'confirmed') return { eligible: false, reason: '已经核对', draft }
  if (analyte.status === 'unclear') return { eligible: false, reason: '已标记存疑，需单独处理', draft }
  if (!draft.name.trim()) return { eligible: false, reason: '缺少指标名称', draft }
  const kind = resultKind(draft.value)
  if (!kind) return { eligible: false, reason: '结果不是可确认的数值或定性结果', draft }
  if (kind === 'qualitative') {
    if (draft.ref.trim() && !qualitativeResultText(draft.ref)) {
      return { eligible: false, reason: '定性参考值需要单独核对', draft }
    }
    return { eligible: true, reason: null, draft }
  }
  if (!draft.unit.trim()) return { eligible: false, reason: '报告原文缺少单位', draft }
  if (analyte.raw_ref_range && analyte.ref_low == null && analyte.ref_high == null) {
    return { eligible: false, reason: '参考范围格式需要单独核对', draft }
  }
  return { eligible: true, reason: null, draft }
}
