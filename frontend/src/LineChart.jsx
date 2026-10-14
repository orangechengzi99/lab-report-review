import { useState } from 'react'

/**
 * 折线图（零依赖手写 SVG）
 *
 * 与设计稿一致的一条关键口径：**参考范围逐点取自各自报告原文**，
 * 因此参考带是「阶梯状」的，而不是一条贯穿全图的统一阈值带。
 * 报告未提供参考范围的点，那一段就不画带 —— 信息缺失 ≠ 异常。
 */

const W = 440
const H = 196
const PAD_L = 46
const PAD_R = 14
const PAD_T = 14
const PAD_B = 26
const PLOT_W = W - PAD_L - PAD_R
const PLOT_H = H - PAD_T - PAD_B

const fmt = (v) => String(Math.round(v * 1e6) / 1e6)
const INTERPRETATION_LABELS = {
  within: '正常',
  high: '偏高',
  low: '偏低',
  no_range: '无参考范围',
  unclear_unit: '单位不明',
  not_numeric: '定性结果',
}

/** 取"整齐"刻度：步长 1/2/2.5/5/10 × 10^n */
function niceTicks(lo, hi, count = 4) {
  const span = hi - lo
  if (!(span > 0)) return [lo, hi]
  const raw = span / count
  const mag = 10 ** Math.floor(Math.log10(raw))
  const norm = raw / mag
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag
  const start = Math.floor(lo / step) * step
  const end = Math.ceil(hi / step) * step
  const out = []
  for (let v = start; v <= end + step * 0.5; v += step) out.push(Math.round(v / step) * step)
  return out.length > 9 ? [start, end] : out
}

/** 取点的参考范围：优先后端逐点给的，其次回落到指标级（最新一次） */
function rangeOf(p, metric) {
  const low = p.ref_low !== undefined ? p.ref_low : metric.ref_low
  const high = p.ref_high !== undefined ? p.ref_high : metric.ref_high
  return [low ?? null, high ?? null]
}

export default function LineChart({ metric, chartId }) {
  const [hover, setHover] = useState(null)

  const points = metric.points || []
  if (points.length < 2) {
    return (
      <div className="empty" style={{ padding: '28px 16px' }}>
        该指标只有 1 个已核对数据点，不足以画趋势。
      </div>
    )
  }

  const unit = metric.unit || ''
  const values = points.map((p) => p.value)

  // ---- Y 轴范围：纳入数值与各点参考范围，留 12% 余量 ----
  let lo = Math.min(...values)
  let hi = Math.max(...values)
  points.forEach((p) => {
    const [l, h] = rangeOf(p, metric)
    if (l != null) lo = Math.min(lo, l)
    if (h != null) hi = Math.max(hi, h)
  })
  if (hi === lo) hi = lo + 1
  const pad = (hi - lo) * 0.12
  lo -= pad
  hi += pad
  if (lo < 0 && Math.min(...values) >= 0) lo = 0 // 医学指标不展示负刻度

  const ticks = niceTicks(lo, hi, 4)
  const yMin = ticks[0]
  const yMax = ticks[ticks.length - 1]
  const yOf = (v) => PAD_T + PLOT_H - ((v - yMin) / (yMax - yMin)) * PLOT_H

  // ---- X 轴：按真实日期等距 ----
  const times = points.map((p) => new Date(p.date).getTime())
  const t0 = times[0]
  const t1 = times[times.length - 1]
  const xOf = (i) => (t1 === t0 ? PAD_L + PLOT_W / 2 : PAD_L + ((times[i] - t0) / (t1 - t0)) * PLOT_W)

  const linePath = points.map((p, i) => `${i ? 'L' : 'M'} ${xOf(i).toFixed(1)} ${yOf(p.value).toFixed(1)}`).join(' ')

  const handleMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const px = ((e.clientX - rect.left) / rect.width) * W
    let best = 0
    let bestD = Infinity
    for (let i = 0; i < points.length; i++) {
      const d = Math.abs(xOf(i) - px)
      if (d < bestD) {
        bestD = d
        best = i
      }
    }
    setHover(best)
  }

  const colorOf = (interp) =>
    interp === 'high' ? 'var(--c-high)' : interp === 'low' ? 'var(--c-low)' : interp === 'within' ? 'var(--c-ok)' : 'var(--c-text-4)'

  const gradId = `grad-${chartId}`
  const hoverPoint = hover != null ? points[hover] : null
  const hoverRange = hoverPoint ? rangeOf(hoverPoint, metric) : [null, null]

  return (
    <div className="chart-wrap">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="chart"
        onMouseMove={handleMove}
        onMouseLeave={() => setHover(null)}
        role="group"
        aria-label={`${metric.name} 趋势图，共 ${points.length} 个数据点`}
      >
      <desc>按检查日期排列的数值趋势。每个数据点可用键盘聚焦，图后也提供完整数据表。</desc>
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--c-brand)" stopOpacity="0.14" />
          <stop offset="100%" stopColor="var(--c-brand)" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* 参考带（逐点阶梯） */}
      {points.map((p, i) => {
        const [low, high] = rangeOf(p, metric)
        if (low == null && high == null) return null
        const x0 = i === 0 ? PAD_L : (xOf(i - 1) + xOf(i)) / 2
        const x1 = i === points.length - 1 ? PAD_L + PLOT_W : (xOf(i) + xOf(i + 1)) / 2
        const yTop = yOf(high != null ? high : yMax)
        const yBot = yOf(low != null ? low : yMin)
        return (
          <rect
            key={`band-${i}`}
            x={x0}
            y={yTop}
            width={Math.max(0, x1 - x0)}
            height={Math.max(0, yBot - yTop)}
            fill="var(--c-ok)"
            opacity="0.08"
          />
        )
      })}

      {/* 网格线 + Y 刻度 */}
      {ticks.map((t) => (
        <g key={`t-${t}`}>
          <line x1={PAD_L} y1={yOf(t)} x2={PAD_L + PLOT_W} y2={yOf(t)} stroke="var(--c-stroke-soft)" strokeWidth="1" strokeDasharray="3 4" />
          <text x={PAD_L - 7} y={yOf(t) + 3.2} textAnchor="end" className="chart-axis">
            {fmt(t)}
          </text>
        </g>
      ))}

      {/* 面积 + 折线 */}
      <path
        d={`${linePath} L ${xOf(points.length - 1).toFixed(1)} ${PAD_T + PLOT_H} L ${xOf(0).toFixed(1)} ${PAD_T + PLOT_H} Z`}
        fill={`url(#${gradId})`}
      />
      <path d={linePath} fill="none" stroke="var(--c-brand)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />

      {/* 数据点：最后一点白心加粗，表示"最新" */}
      {points.map((p, i) => {
        const last = i === points.length - 1
        return (
          <circle
            key={`p-${i}`}
            cx={xOf(i)}
            cy={yOf(p.value)}
            r={last ? 4.4 : 3.2}
            fill={last ? 'var(--c-surface)' : colorOf(p.interpretation)}
            stroke={colorOf(p.interpretation)}
            strokeWidth={last ? 2.2 : 1.6}
            tabIndex="0"
            role="img"
            aria-label={`${p.date}，${fmt(p.value)} ${unit || '无单位'}，${INTERPRETATION_LABELS[p.interpretation] || '无法比较'}`}
            onFocus={() => setHover(i)}
            onBlur={() => setHover(null)}
          />
        )
      })}

      {/* X 轴日期：点少全显，点多只标首 / 中 / 尾，避免窄卡片里标签互相压住 */}
      {points.map((p, i) => {
        const n = points.length
        const keep =
          n <= 3 ? new Set([0, 1, 2]) : new Set([0, Math.round((n - 1) / 2), n - 1])
        if (!keep.has(i)) return null
        const anchor = i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'
        return (
          <text key={`x-${i}`} x={xOf(i)} y={H - 8} textAnchor={anchor} className="chart-axis">
            {String(p.date).slice(2, 10)}
          </text>
        )
      })}

      {/* 悬停：竖线 + 提示框 */}
      {hover != null && (
        <>
          <line x1={xOf(hover)} y1={PAD_T} x2={xOf(hover)} y2={PAD_T + PLOT_H} stroke="var(--c-stroke-btn)" strokeWidth="1" strokeDasharray="3 3" />
          <g transform={`translate(${Math.min(Math.max(xOf(hover) - 52, PAD_L), PAD_L + PLOT_W - 108)}, ${Math.max(yOf(points[hover].value) - 62, PAD_T)})`}>
            <rect width="108" height="52" rx="7" fill="var(--c-surface)" stroke="var(--c-stroke)" />
            <text x="9" y="17" className="chart-tip-k">
              {points[hover].date}
            </text>
            <text x="9" y="32" className="chart-tip">
              {fmt(points[hover].value)} {unit}
            </text>
            <text x="9" y="45" className="chart-tip-k">
              {hoverRange[0] == null && hoverRange[1] == null
                ? '报告未提供参考范围'
                : `参考 ${hoverRange[0] ?? '—'}–${hoverRange[1] ?? '—'}`}
            </text>
          </g>
        </>
      )}
      </svg>
      <details className="chart-data">
        <summary>查看趋势数据表</summary>
        <div className="chart-data-scroll">
          <table>
            <thead><tr><th>日期</th><th>数值</th><th>单位</th><th>参考范围</th><th>判读</th></tr></thead>
            <tbody>
              {points.map((point, index) => {
                const [low, high] = rangeOf(point, metric)
                const range = low == null && high == null ? '未提供' : `${low ?? '—'}–${high ?? '—'}`
                return (
                  <tr key={`row-${index}`}>
                    <td>{point.date}</td><td>{fmt(point.value)}</td><td>{unit || '—'}</td><td>{range}</td>
                    <td>{INTERPRETATION_LABELS[point.interpretation] || '无法比较'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  )
}

/** 方向箭头：只描述数值变化，不含好坏含义 */
export function trendArrow(trend) {
  return { up: '↑', down: '↓', flat: '→' }[trend] || '→'
}
