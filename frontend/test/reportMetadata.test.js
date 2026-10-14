import test from 'node:test'
import assert from 'node:assert/strict'

import {
  reportMetadataDraft,
  reportMetadataPayload,
  reportTypeOptions,
  validateReportMetadata,
} from '../src/reportMetadata.js'

test('报告信息草稿保留当前值，未填写医院时使用空字符串', () => {
  assert.deepEqual(
    reportMetadataDraft({
      patient_label: '报告-001',
      exam_type: '尿常规',
      collected_at: '2026-07-13',
    }),
    {
      patientLabel: '报告-001',
      examType: '尿常规',
      collectedAt: '2026-07-13',
      hospital: '',
    },
  )
})

test('报告信息提交前会去除首尾空格', () => {
  assert.deepEqual(
    reportMetadataPayload({
      patientLabel: '  尿检复查  ',
      examType: '  尿常规 ',
      collectedAt: '2026-07-13',
      hospital: ' 市中心医院 ',
    }),
    {
      patient_label: '尿检复查',
      exam_type: '尿常规',
      collected_at: '2026-07-13',
      hospital: '市中心医院',
    },
  )
})

test('标签、类型和日期必填，医院可留空', () => {
  assert.deepEqual(
    validateReportMetadata({ patientLabel: ' ', examType: '', collectedAt: '', hospital: '' }),
    {
      patientLabel: '请填写报告标签',
      examType: '请填写检查类型',
      collectedAt: '请选择检查日期',
    },
  )
  assert.deepEqual(
    validateReportMetadata({ patientLabel: '报告', examType: '尿常规', collectedAt: '2026-07-13', hospital: '' }),
    {},
  )
})

test('检查类型下拉保留旧报告中的自定义类型且不重复标准类型', () => {
  const custom = reportTypeOptions('随访复查')
  assert.equal(custom[0], '随访复查')
  assert.equal(custom.filter((type) => type === '随访复查').length, 1)

  const standard = reportTypeOptions('尿常规')
  assert.equal(standard.filter((type) => type === '尿常规').length, 1)
})
