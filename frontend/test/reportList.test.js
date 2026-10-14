import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { sortReportsByExamDateDesc } from '../src/reportList.js'

describe('sortReportsByExamDateDesc', () => {
  it('按检查日期倒序排列，并将缺少日期的报告放在最后', () => {
    const reports = [
      { id: 1, collected_at: '2026-01-20' },
      { id: 2, collected_at: null },
      { id: 3, collected_at: '2026-10-14' },
      { id: 4, collected_at: '2025-10-15' },
    ]

    assert.deepEqual(
      sortReportsByExamDateDesc(reports).map((report) => report.id),
      [3, 1, 4, 2],
    )
  })

  it('同一天后导入的报告在前，且不修改原数组', () => {
    const reports = [
      { id: 7, collected_at: '2026-10-14' },
      { id: 8, collected_at: '2026-10-14' },
    ]

    assert.deepEqual(
      sortReportsByExamDateDesc(reports).map((report) => report.id),
      [8, 7],
    )
    assert.deepEqual(
      reports.map((report) => report.id),
      [7, 8],
    )
  })
})
