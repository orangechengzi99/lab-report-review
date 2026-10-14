export function sortReportsByExamDateDesc(reports) {
  return [...reports].sort((left, right) => {
    const byDate = String(right.collected_at || '').localeCompare(String(left.collected_at || ''))
    if (byDate !== 0) return byDate

    return Number(right.id || 0) - Number(left.id || 0)
  })
}
