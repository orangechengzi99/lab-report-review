import test from 'node:test'
import assert from 'node:assert/strict'

import {
  batchReviewItem,
  draftFromAnalyte,
  isNumericText,
  payloadFromDraft,
  qualitativeResultText,
  referenceFromAnalyte,
  resultKind,
} from '../src/reviewDraft.js'

test('unchecked draft keeps the report text instead of inferred values', () => {
  const draft = draftFromAnalyte({
    status: 'unchecked',
    name: '白细胞计数',
    category: '血常规',
    value: null,
    raw_value: '9.2',
    unit: null,
    raw_unit: '10^9/L',
    ref_low: null,
    ref_high: null,
    raw_ref_range: '3.5-9.5',
  })
  assert.deepEqual(draft, {
    name: '白细胞计数',
    category: '血常规',
    value: '9.2',
    unit: '10^9/L',
    ref: '3.5-9.5',
  })
})

test('reference text supports one-sided confirmed bounds', () => {
  assert.equal(referenceFromAnalyte({ status: 'confirmed', ref_low: 3.5, ref_high: null }), '>=3.5')
  assert.equal(referenceFromAnalyte({ status: 'confirmed', ref_low: null, ref_high: 9.5 }), '<=9.5')
})

test('confirmed reference keeps the reviewed strict operator', () => {
  const draft = draftFromAnalyte({
    status: 'confirmed', name: '总胆固醇', category: '生化全项', value: 5.2,
    result_text: null, raw_value: '5.2', unit: 'mmol/L', raw_unit: 'mmol/L',
    ref_low: null, ref_high: 5.2, ref_text: '<5.2', raw_ref_range: '<5.2',
  })
  assert.equal(draft.ref, '<5.2')
})

test('confirmed qualitative drafts use the reviewed text and qualitative reference', () => {
  const draft = draftFromAnalyte({
    status: 'confirmed', name: '尿胆红素', category: '尿常规', value: null,
    result_text: '阴性', raw_value: '阳性', unit: null, raw_unit: null,
    ref_low: null, ref_high: null, ref_text: '阴性', raw_ref_range: '阴性',
  })
  assert.equal(draft.value, '阴性')
  assert.equal(draft.ref, '阴性')
})

test('numeric validation rejects blanks and qualitative text', () => {
  assert.equal(isNumericText(' 9.2 '), true)
  assert.equal(isNumericText('20.2 ↑'), true)
  assert.equal(isNumericText('0.07↓'), true)
  assert.equal(isNumericText(''), false)
  assert.equal(isNumericText('阴性'), false)
  assert.equal(isNumericText('约 9.2'), false)
})

test('qualitative validation accepts only explicit laboratory result formats', () => {
  assert.equal(qualitativeResultText(' 阴性 '), '阴性')
  assert.equal(qualitativeResultText('弱阳性'), '弱阳性')
  assert.equal(qualitativeResultText('2+'), '2+')
  assert.equal(qualitativeResultText('±'), '±')
  assert.equal(qualitativeResultText('阴性（-）'), '阴性（-）')
  assert.equal(qualitativeResultText('疑似阴性结果'), null)
  assert.equal(resultKind('阴性'), 'qualitative')
  assert.equal(resultKind('9.2'), 'numeric')
  assert.equal(resultKind('约 9.2'), null)
})

test('payload trims fields and preserves an explicit review status', () => {
  assert.deepEqual(
    payloadFromDraft({ name: ' 白细胞 ', category: '', value: ' 9.2 ', unit: ' ', ref: ' 3.5-9.5 ' }, 'unclear'),
    {
      name: '白细胞',
      category: '其他',
      value: '9.2',
      unit: null,
      ref_range: '3.5-9.5',
      status: 'unclear',
    },
  )
})

test('batch review accepts safe numeric and qualitative source rows', () => {
  const base = {
    status: 'unchecked', name: '白细胞计数', category: '血常规', raw_value: '9.2',
    raw_unit: '10^9/L', raw_ref_range: '3.5-9.5', ref_low: 3.5, ref_high: 9.5,
  }
  assert.equal(batchReviewItem(base).eligible, true)
  assert.deepEqual(batchReviewItem({ ...base, status: 'unclear' }), {
    eligible: false,
    reason: '已标记存疑，需单独处理',
    draft: { name: '白细胞计数', category: '血常规', value: '9.2', unit: '10^9/L', ref: '3.5-9.5' },
  })
  assert.equal(batchReviewItem({ ...base, raw_unit: null }).reason, '报告原文缺少单位')
  assert.equal(batchReviewItem({ ...base, raw_value: '阴性', raw_unit: null, raw_ref_range: '阴性', ref_low: null, ref_high: null }).eligible, true)
  assert.equal(batchReviewItem({ ...base, raw_value: '阴性', raw_unit: null, raw_ref_range: '复杂描述', ref_low: null, ref_high: null }).reason, '定性参考值需要单独核对')
  assert.equal(batchReviewItem({ ...base, raw_value: '无法辨认' }).reason, '结果不是可确认的数值或定性结果')
  assert.equal(batchReviewItem({ ...base, raw_ref_range: '复杂范围', ref_low: null, ref_high: null }).eligible, false)
})
