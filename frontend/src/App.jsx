import { useEffect, useMemo, useRef, useState } from 'react'
import ImportModal from './ImportModal.jsx'
import LineChart, { trendArrow } from './LineChart.jsx'
import { batchReviewItem, draftFromAnalyte, resultKind, payloadFromDraft } from './reviewDraft.js'
import {
  reportMetadataDraft,
  reportMetadataPayload,
  reportTypeOptions,
  validateReportMetadata,
} from './reportMetadata.js'
import { sortReportsByExamDateDesc } from './reportList.js'
import {
  IconBrand,
  IconSearch,
  IconHelp,
  IconChevronDown,
  IconChevronRight,
  IconDownload,
  IconPlus,
  IconCheck,
  IconRefresh,
  IconImage,
  IconInbox,
  IconClose,
} from './icons.jsx'

/* ============================================================================
   语义映射
   ----------------------------------------------------------------------------
   判读文案只在「已核对」时才出现 —— 未核对的指标一律显示"暂不判读"。
   后端 Analyte.interpretation() 对未核对项返回 "unchecked"（语义正确），
   这里再按 status 门控一次，属于双保险：即使将来有人绕过这层判断，
   "未核对"也不会被渲染成"无法比较"或任何数值结论。
   ========================================================================== */

const INTERP = {
  within: { label: '正常', cls: 'ok' },
  high: { label: '偏高', cls: 'high' },
  low: { label: '偏低', cls: 'low' },
  no_range: { label: '无法比较', cls: 'na' },
  not_numeric: { label: '定性结果', cls: 'na' },
  unclear_unit: { label: '单位不明', cls: 'na' },
  unchecked: { label: '暂不判读', cls: 'na' },
}

const STATUS = {
  unchecked: { label: '待核对', cls: 'badge--pending' },
  confirmed: { label: '已核对', cls: 'badge--neutral' },
  unclear: { label: '存疑', cls: 'badge--neutral' },
}

const CATEGORIES = [
  '血常规',
  '生化全项',
  '肝功能',
  '肾功能',
  '凝血功能',
  '甲状腺功能',
  '糖代谢',
  '免疫球蛋白与补体',
  '风湿免疫',
  '肿瘤标志物',
  '其他',
]

const SERIES_ONLY_NOTE = '趋势仅含「已核对且有数值」的点，单点不画线。'

/* ============================================================================
   视图定义
   ========================================================================== */

const HASH_TO_VIEW = {
  '#overview': 'overview',
  '#report': 'report',
  '#trends': 'trends',
  '#categories': 'categories',
  '#dashboard': 'overview', // 兼容旧链接
}

const VIEW_HASH = { overview: '#overview', report: '#report', trends: '#trends', categories: '#categories' }

/**
 * 主导航。
 * 说明：设计稿的顶栏只有「品牌 + 搜索 + 用户」，没有导航位 —— 因为设计稿是四张
 * 独立画板，不需要互相跳转。落到真实产品必须给入口，所以补在品牌与搜索之间。
 */
const NAV = [
  ['overview', '报告总览'],
  ['report', '报告核对'],
  ['trends', '指标趋势'],
  ['categories', '异常指标概览'],
]

function readViewFromHash() {
  return HASH_TO_VIEW[window.location.hash] || 'overview'
}

/* ============================================================================
   通用小件
   ========================================================================== */

function TopBar({ query, onQuery, onHelp, view, onView }) {
  return (
    <header className="topbar">
      <div className="tb-brand">
        <span className="tb-logo">
          <IconBrand />
        </span>
        <span className="tb-name">检验报告管理</span>
        <span className="tb-vsep" />
        <span className="tb-en">lab-report-review</span>
      </div>

      <nav className="tb-nav seg" aria-label="视图切换">
        {NAV.map(([k, label]) => (
          <button
            type="button"
            key={k}
            className={`seg-item${view === k ? ' is-active' : ''}`}
            onClick={() => onView(k)}
            aria-current={view === k ? 'page' : undefined}
          >
            {label}
          </button>
        ))}
      </nav>

      <div className="tb-spacer" />

      <div className="tb-search">
        <IconSearch />
        <input
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          placeholder="搜索报告、指标或医院"
          aria-label="搜索报告、指标或医院"
        />
      </div>

      <span className="tb-vsep2" />

      <button type="button" className="tb-icon" onClick={onHelp} aria-label="帮助">
        <IconHelp />
      </button>
    </header>
  )
}

function MainHead({ crumb, ops }) {
  return (
    <div className="main-head">
      <nav className="crumbs" aria-label="面包屑">
        <span>{crumb[0]}</span>
        <IconChevronRight />
        <b>{crumb[1]}</b>
      </nav>
      <div className="ops">{ops}</div>
    </div>
  )
}

function MainTitle({ title, badge, sub, meta, action }) {
  return (
    <div className="main-title">
      <div className="title-row">
        <h1 className="page-title">{title}</h1>
        {badge}
        {action}
      </div>
      {sub && <p className="page-sub">{sub}</p>}
      {meta && (
        <div className="meta-row">
          {meta.map((m) => (
            <span className="meta" key={m.k}>
              <span className="meta-k">{m.k}</span>
              <span className="meta-v">{m.v}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function Kpi({ label, value, unit, tone }) {
  return (
    <div className="kpi">
      <span className="kpi-l">{label}</span>
      <span className="kpi-vrow">
        <span className={`kpi-v${tone ? ` is-${tone}` : ''}`}>{value}</span>
        <span className="kpi-u">{unit}</span>
      </span>
    </div>
  )
}

/* ============================================================================
   左栏
   ========================================================================== */

function Rail({ view, reports, trends, currentId, query, onPickReport, onPickSeries, onImport }) {
  const stats = useMemo(() => {
    let pending = 0
    let abnormal = 0
    reports.forEach((r) =>
      r.analytes.forEach((a) => {
        if (a.status === 'unchecked') pending += 1
        if (a.status === 'confirmed' && (a.interpretation === 'high' || a.interpretation === 'low')) abnormal += 1
      }),
    )
    return { reports: reports.length, pending, abnormal }
  }, [reports])

  const q = query.trim().toLowerCase()
  const isSeriesMode = view === 'trends'

  const shownReports = useMemo(() => {
    const filteredReports = q
      ? reports.filter((r) =>
          [r.patient_label, r.exam_type, r.collected_at, r.hospital]
            .filter(Boolean)
            .join(' ')
            .toLowerCase()
            .includes(q),
        )
      : reports

    return sortReportsByExamDateDesc(filteredReports)
  }, [reports, q])

  const shownSeries = useMemo(() => {
    if (!q) return trends
    return trends.filter((t) => [t.name, t.category, t.unit].filter(Boolean).join(' ').toLowerCase().includes(q))
  }, [trends, q])

  return (
    <aside className="rail">
      <div className="rail-top">
        <div>
          <div className="rail-eyebrow">当前工作区</div>
          <div className="rail-ws">
            我的检验报告
            <IconChevronDown />
          </div>
        </div>

        <div className="rail-stats">
          <div className="rail-stat">
            <span className="rail-stat-n">{stats.reports}</span>
            <span className="rail-stat-l">报告</span>
          </div>
          <div className="rail-stat">
            <span className="rail-stat-n">{stats.pending}</span>
            <span className="rail-stat-l">待核对</span>
          </div>
          <div className="rail-stat">
            <span className={`rail-stat-n${stats.abnormal ? ' is-high' : ''}`}>{stats.abnormal}</span>
            <span className="rail-stat-l">异常项</span>
          </div>
        </div>
      </div>

      {isSeriesMode ? (
        <div className="rail-list">
          <div className="rail-list-head">
            <span>指标序列</span>
            <em>{shownSeries.length} / {trends.length}</em>
          </div>
          {shownSeries.map((t) => (
            <button
              type="button"
              key={`${t.category}-${t.name}`}
              className="rail-item"
              onClick={() => onPickSeries(t.name)}
            >
              <span className="rail-item-top">
                <span className="rail-item-id">{t.name}</span>
                <span className="spacer" />
                <span className={`rail-val${t.latest_interpretation === 'high' ? ' is-high' : t.latest_interpretation === 'low' ? ' is-low' : ''}`}>
                  {t.latest_value}
                </span>
              </span>
              <span className="rail-item-sub">
                {t.category} · {t.unit || '单位未填'} · {t.points.length} 点
              </span>
            </button>
          ))}
          {shownSeries.length === 0 && (
            <div className="rail-empty">
              {trends.length === 0 ? '暂无趋势序列。每个指标至少要有 2 次已核对的检查。' : '没有匹配的指标序列。'}
            </div>
          )}
        </div>
      ) : (
        <div className="rail-list">
          <div className="rail-list-head">
            <span>报告列表</span>
            <em>{shownReports.length} / {reports.length}</em>
          </div>
          {shownReports.map((r) => {
            const total = r.analytes.length
            const confirmed = r.analytes.filter((a) => a.status === 'confirmed').length
            const abn = r.analytes.filter((a) => a.status === 'confirmed' && (a.interpretation === 'high' || a.interpretation === 'low')).length
            const pending = total - confirmed
            return (
              <button
                type="button"
                key={r.id}
                className={`rail-item${r.id === currentId ? ' is-active' : ''}`}
                onClick={() => onPickReport(r.id)}
              >
                <span className="rail-item-top">
                  <span className="rail-item-id">{r.patient_label}</span>
                  <span className="spacer" />
                  {abn > 0 && <span className="badge badge--high">{abn} 项异常</span>}
                </span>
                <span className="rail-item-sub">
                  {r.exam_type}
                  {r.collected_at ? ` · ${r.collected_at}` : ''}
                </span>
                <span className="rail-item-prog">
                  <span className="rail-item-prog-txt">已核对 {confirmed} / {total}</span>
                  {pending > 0 && <span className="badge badge--pending">待核对 {pending}</span>}
                </span>
              </button>
            )
          })}
          {shownReports.length === 0 && (
            <div className="rail-empty">
              {reports.length === 0 ? '还没有报告。用下方按钮导入第一份。' : '没有匹配的报告。'}
            </div>
          )}
        </div>
      )}

      <div className="rail-foot">
        <button type="button" className="btn btn--primary btn--block" onClick={onImport}>
          <IconPlus />
          导入报告
        </button>
      </div>
    </aside>
  )
}

/* ============================================================================
   指标行（01 屏表格）
   ========================================================================== */

function AnalyteRow({ a, reportId, onSaved }) {
  const [draft, setDraft] = useState(() => draftFromAnalyte(a))
  const [msg, setMsg] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setDraft(draftFromAnalyte(a))
  }, [a])

  const confirmed = a.status === 'confirmed'
  const interp = INTERP[a.interpretation] || { label: '—', cls: 'na' }
  const kind = resultKind(draft.value)
  const reviewable = kind !== null

  // 判读只在已核对时呈现
  const verdict = confirmed ? interp : { label: '暂不判读', cls: 'na' }

  const save = async (nextStatus) => {
    setMsg(null)
    if (!draft.name.trim()) {
      setMsg({ type: 'err', text: '指标名称不能为空' })
      return
    }
    if (nextStatus === 'confirmed' && !reviewable) {
      setMsg({ type: 'err', text: '请输入数值，或明确的定性结果（如阴性、阳性、1+）' })
      return
    }
    setSaving(true)
    try {
      const res = await fetch(`/api/reports/${reportId}/analytes/${a.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payloadFromDraft(draft, nextStatus)),
      })
      const data = await res.json()
      if (!res.ok) {
        setMsg({ type: 'err', text: data.detail || '保存失败' })
        return
      }
      await onSaved(data)
    } catch {
      setMsg({ type: 'err', text: '网络错误' })
    } finally {
      setSaving(false)
    }
  }

  const setField = (key, value) => setDraft((current) => ({ ...current, [key]: value }))

  // 名称下方的说明行：未核对显示识别值，信息缺失说明原因
  let hint = null
  if (a.status === 'unchecked') {
    hint = { text: `识别值 ${a.raw_value}${a.raw_unit ? ` ${a.raw_unit}` : ''}，尚未核对`, tone: 'is-pending' }
  } else if (a.status === 'unclear') {
    hint = { text: '已标记为存疑，确认后再判读', tone: 'is-pending' }
  } else if (a.interpretation === 'no_range') {
    hint = { text: '报告未提供参考范围', tone: '' }
  } else if (a.interpretation === 'not_numeric') {
    hint = { text: '定性结果，不适用数值规则', tone: '' }
  } else if (a.interpretation === 'unclear_unit') {
    hint = { text: '单位不明，无法与参考范围对齐', tone: '' }
  }

  const valTone = confirmed && a.interpretation === 'high' ? ' is-high' : confirmed && a.interpretation === 'low' ? ' is-low' : ''

  return (
    <div className={`tbl-row${hint ? ' is-tall' : ''}`}>
      <div className="col-name">
        <input
          className="inline-input is-name"
          value={draft.name}
          onChange={(e) => setField('name', e.target.value)}
          aria-label="指标名称"
        />
        {hint && <span className={`cell-hint${hint.tone ? ` ${hint.tone}` : ''}`}>{hint.text}</span>}
      </div>

      <div className="col-cat">
        <select
          className="inline-select"
          value={draft.category}
          onChange={(e) => setField('category', e.target.value)}
          aria-label="指标类别"
        >
          {CATEGORIES.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      </div>

      <div className="col-num">
        <input
          className={`inline-input is-val${valTone}${a.status === 'unchecked' ? ' is-needs' : ''}`}
          value={draft.value}
          onChange={(e) => setField('value', e.target.value)}
          inputMode={kind === 'numeric' ? 'decimal' : 'text'}
          aria-label="核对后数值"
        />
      </div>

      <div className="col-unit">
        <input
          className="inline-input is-unit"
          value={draft.unit}
          onChange={(e) => setField('unit', e.target.value)}
          placeholder="单位"
          aria-label="指标单位"
        />
      </div>

      <div className="col-ref">
        <input
          className="inline-input is-ref"
          value={draft.ref}
          onChange={(e) => setField('ref', e.target.value)}
          placeholder="如 3.5-9.5"
          aria-label="参考范围"
        />
      </div>

      <div className="col-verdict">
        {verdict.cls === 'high' || verdict.cls === 'low' ? (
          <span className={`badge badge--${verdict.cls}`}>{verdict.label}</span>
        ) : verdict.cls === 'ok' ? (
          <span className="verdict-ok">正常</span>
        ) : (
          <span className="cell-na">{verdict.label}</span>
        )}
      </div>

      <div className="col-status">
        <span className={`badge ${STATUS[a.status] ? STATUS[a.status].cls : 'badge--neutral'}`}>
          {STATUS[a.status] ? STATUS[a.status].label : a.status}
        </span>
        <span className="status-actions">
          {confirmed ? (
            <>
              <button type="button" className="mini-action" disabled={saving} onClick={() => save('confirmed')}>保存修改</button>
              <button type="button" className="mini-action is-muted" disabled={saving} onClick={() => save('unchecked')}>重新核对</button>
            </>
          ) : (
            <>
              <button type="button" className="mini-action" disabled={saving} onClick={() => save('confirmed')}>确认</button>
              <button type="button" className="mini-action is-muted" disabled={saving} onClick={() => save(a.status === 'unclear' ? 'unchecked' : 'unclear')}>
                {a.status === 'unclear' ? '返回待核对' : '存疑'}
              </button>
            </>
          )}
        </span>
      </div>

      {msg && <div className={`row-msg is-${msg.type}`} role="alert">{msg.text}</div>}
    </div>
  )
}

/* ============================================================================
   视图一：02 · 报告总览
   ========================================================================== */

function OverviewView({ reports, trends, stats, pendingTasks, onOpenReport, onImport, onExportAll }) {
  const sortedReports = useMemo(() => sortReportsByExamDateDesc(reports), [reports])

  return (
    <>
      <MainHead
        crumb={['工作区', '总览']}
        ops={
          <>
            <button type="button" className="btn btn--outline" onClick={onExportAll}>
              <IconDownload />
              导出全部
            </button>
            <button type="button" className="btn btn--primary" onClick={onImport}>
              <IconPlus />
              导入报告
            </button>
          </>
        }
      />

      <MainTitle
        title="报告总览"
        sub={`共 ${stats.reports} 份报告 · ${stats.analytes} 项指标 · ${stats.abnormal} 项超出参考范围 · ${stats.pending} 项待核对`}
      />

      <div className="content content--scroll">
        <div className="kpi-row">
          <Kpi label="报告总数" value={stats.reports} unit="份" />
          <Kpi label="指标总数" value={stats.analytes} unit="项" />
          <Kpi label="超出参考范围" value={stats.abnormal} unit="项" tone={stats.abnormal ? 'high' : undefined} />
          <Kpi label="待核对" value={stats.pending} unit="项" tone={stats.pending ? 'pending' : undefined} />
        </div>

        <div className="split-row">
          <div className="card split-main">
            <div className="card-head">
              <span className="card-head-t">
                报告清单
                <em>按检查日期倒序</em>
              </span>
              <span className="card-head-r">{reports.length} 份</span>
            </div>

            <div className="card-body scroll-y">
              <div className="tbl">
                <div className="tbl-head">
                  <span className="col-name">报告</span>
                  <span className="col-date">日期</span>
                  <span className="col-k">指标</span>
                  <span className="col-k2">超出范围</span>
                  <span className="col-k3">待核对</span>
                </div>
                {sortedReports.map((r) => {
                  const total = r.analytes.length
                  const abn = r.analytes.filter((a) => a.status === 'confirmed' && (a.interpretation === 'high' || a.interpretation === 'low')).length
                  const pending = r.analytes.filter((a) => a.status === 'unchecked').length
                  return (
                    <button type="button" key={r.id} className="tbl-row tbl-row--btn" onClick={() => onOpenReport(r.id)}>
                      <span className="col-name">
                        <span className="cell-name">{r.patient_label}</span>
                        <span className="cell-hint">
                          {r.exam_type}
                          {r.hospital ? ` · ${r.hospital}` : ''}
                        </span>
                      </span>
                      <span className="col-date">{r.collected_at || '—'}</span>
                      <span className="col-k mono">{total}</span>
                      <span className={`col-k2 mono ${abn ? 'tone-high' : 'tone-dim'}`}>{abn}</span>
                      <span className={`col-k3 mono ${pending ? 'tone-pending' : 'tone-dim'}`}>{pending}</span>
                    </button>
                  )
                })}
                {reports.length === 0 && (
                  <div className="empty">
                    <IconInbox />
                    <span>还没有报告。用右上角「导入报告」导入第一份。</span>
                  </div>
                )}
              </div>
            </div>

            <div className="card-foot">
              判读仅基于各报告自带参考范围，不代表诊断结论。
            </div>
          </div>

          <div className="card split-side">
            <div className="card-head">
              <span className="card-head-t">需要你处理</span>
              <span className={`card-head-r${pendingTasks.length ? ' tone-pending' : ''}`}>
                {pendingTasks.length} 项待核对
              </span>
            </div>

            <div className="card-body scroll-y">
              <div className="task-list">
                {pendingTasks.map((t) => (
                  <button type="button" key={`${t.reportId}-${t.id}`} className="task-item" onClick={() => onOpenReport(t.reportId)}>
                    <span className="badge badge--pending">待核对</span>
                    <b>{t.name}</b>
                    <em>{t.reportLabel}</em>
                  </button>
                ))}
                {pendingTasks.length === 0 && (
                  <div className="empty" style={{ padding: '32px 16px' }}>
                    <IconCheck size={22} />
                    <span>所有指标都已核对。</span>
                  </div>
                )}
              </div>
            </div>

            <div className="card-foot">未核对的指标不做判读，核对后才入档。</div>
          </div>
        </div>
      </div>
    </>
  )
}

/* ============================================================================
   视图二：01 · 报告核对工作台
   ========================================================================== */

function ReportMetadataModal({ report, onClose, onSaved }) {
  const dialogRef = useRef(null)
  const busyRef = useRef(false)
  const [draft, setDraft] = useState(() => reportMetadataDraft(report))
  const [errors, setErrors] = useState({})
  const [submitted, setSubmitted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)

  useEffect(() => {
    busyRef.current = busy
  }, [busy])

  useEffect(() => {
    const previouslyFocused = document.activeElement
    const dialog = dialogRef.current
    const selector = 'button:not([disabled]), input:not([disabled])'
    window.requestAnimationFrame(() => dialog?.querySelector('[data-autofocus]')?.focus())
    const onKeyDown = (event) => {
      if (event.key === 'Escape' && !busyRef.current) {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== 'Tab' || !dialog) return
      const focusable = [...dialog.querySelectorAll(selector)]
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      previouslyFocused?.focus?.()
    }
  }, [onClose])

  const updateDraft = (key, value) => {
    const next = { ...draft, [key]: value }
    setDraft(next)
    if (submitted || errors[key]) setErrors(validateReportMetadata(next))
    setMsg(null)
  }

  const validateField = () => setErrors(validateReportMetadata(draft))

  const submit = async (event) => {
    event.preventDefault()
    const nextErrors = validateReportMetadata(draft)
    setSubmitted(true)
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length) {
      window.requestAnimationFrame(() => dialogRef.current?.querySelector('[aria-invalid="true"]')?.focus())
      return
    }

    setBusy(true)
    setMsg(null)
    try {
      const response = await fetch(`/api/reports/${report.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(reportMetadataPayload(draft)),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        setMsg({ type: 'err', text: data.detail || '报告信息保存失败' })
        return
      }
      await onSaved(data)
      onClose()
    } catch {
      setMsg({ type: 'err', text: '网络错误，请稍后重试' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-mask" onClick={(event) => event.target === event.currentTarget && !busy && onClose()} role="presentation">
      <div ref={dialogRef} className="modal metadata-modal" role="dialog" aria-modal="true" aria-labelledby="metadata-title">
        <div className="modal-head">
          <div>
            <h2 id="metadata-title">编辑报告信息</h2>
            <p className="batch-subtitle">只修改报告信息，不会改变原图、指标和核对状态。</p>
          </div>
          <button type="button" className="modal-x" onClick={onClose} disabled={busy} aria-label="关闭编辑报告信息窗口">
            <IconClose />
          </button>
        </div>

        <form className="metadata-form" onSubmit={submit} noValidate>
          <div className="metadata-fields">
            <label className="field-group metadata-wide" htmlFor="metadata-label">
              <span className="field-label">报告标签 <em>必填</em></span>
              <input
                id="metadata-label"
                data-autofocus
                className={`field${errors.patientLabel ? ' is-error' : ''}`}
                value={draft.patientLabel}
                maxLength={100}
                disabled={busy}
                aria-invalid={errors.patientLabel ? 'true' : undefined}
                aria-describedby={errors.patientLabel ? 'metadata-label-error' : undefined}
                onChange={(event) => updateDraft('patientLabel', event.target.value)}
                onBlur={validateField}
              />
              {errors.patientLabel && <span id="metadata-label-error" className="field-error">{errors.patientLabel}</span>}
            </label>

            <label className="field-group" htmlFor="metadata-type">
              <span className="field-label">检查类型 <em>必填</em></span>
              <select
                id="metadata-type"
                className={`field${errors.examType ? ' is-error' : ''}`}
                value={draft.examType}
                disabled={busy}
                aria-invalid={errors.examType ? 'true' : undefined}
                aria-describedby={errors.examType ? 'metadata-type-error' : undefined}
                onChange={(event) => updateDraft('examType', event.target.value)}
                onBlur={validateField}
              >
                {reportTypeOptions(draft.examType).map((type) => <option key={type}>{type}</option>)}
              </select>
              {errors.examType && <span id="metadata-type-error" className="field-error">{errors.examType}</span>}
            </label>

            <label className="field-group" htmlFor="metadata-date">
              <span className="field-label">检查日期 <em>必填</em></span>
              <input
                id="metadata-date"
                className={`field${errors.collectedAt ? ' is-error' : ''}`}
                type="date"
                value={draft.collectedAt}
                disabled={busy}
                aria-invalid={errors.collectedAt ? 'true' : undefined}
                aria-describedby={errors.collectedAt ? 'metadata-date-error' : undefined}
                onChange={(event) => updateDraft('collectedAt', event.target.value)}
                onBlur={validateField}
              />
              {errors.collectedAt && <span id="metadata-date-error" className="field-error">{errors.collectedAt}</span>}
            </label>

            <label className="field-group metadata-wide" htmlFor="metadata-hospital">
              <span className="field-label">医院</span>
              <input
                id="metadata-hospital"
                className="field"
                value={draft.hospital}
                maxLength={200}
                placeholder="可选"
                disabled={busy}
                onChange={(event) => updateDraft('hospital', event.target.value)}
              />
            </label>
          </div>

          {submitted && Object.keys(errors).length > 0 && (
            <div className="metadata-error-summary" role="alert">请先补全标出的必填信息。</div>
          )}
          {msg && <div className={`modal-msg is-${msg.type}`} role="alert">{msg.text}</div>}

          <div className="batch-footer">
            <button type="button" className="btn" onClick={onClose} disabled={busy}>取消</button>
            <button type="submit" className="btn btn--primary" disabled={busy}>
              <IconCheck />
              {busy ? '正在保存…' : '保存报告信息'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function BatchReviewModal({ report, onClose, onComplete }) {
  const dialogRef = useRef(null)
  const busyRef = useRef(false)
  const rows = report.analytes
    .filter((a) => a.status !== 'confirmed')
    .map((analyte) => ({ analyte, ...batchReviewItem(analyte) }))
  const eligible = rows.filter((row) => row.eligible)
  const excluded = rows.filter((row) => !row.eligible)
  const [selected, setSelected] = useState(() => new Set(eligible.map((row) => row.analyte.id)))
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)

  useEffect(() => {
    busyRef.current = busy
  }, [busy])

  useEffect(() => {
    const previouslyFocused = document.activeElement
    const dialog = dialogRef.current
    const selector = 'button:not([disabled]), input:not([disabled])'
    window.requestAnimationFrame(() => dialog?.querySelector(selector)?.focus())
    const onKeyDown = (event) => {
      if (event.key === 'Escape' && !busyRef.current) {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== 'Tab' || !dialog) return
      const focusable = [...dialog.querySelectorAll(selector)]
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      previouslyFocused?.focus?.()
    }
  }, [onClose])

  const toggle = (id) => {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const selectAll = () => {
    setSelected((current) => (
      current.size === eligible.length ? new Set() : new Set(eligible.map((row) => row.analyte.id))
    ))
  }

  const submit = async () => {
    if (!selected.size) return
    setBusy(true)
    setMsg(null)
    try {
      const res = await fetch(`/api/reports/${report.id}/batch-confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ analyte_ids: [...selected] }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setMsg({ type: 'err', text: data.detail || '批量核对失败' })
        return
      }
      setMsg({ type: 'ok', text: `已确认 ${selected.size} 项，其余项目保持原状态` })
      await onComplete(data)
      window.setTimeout(onClose, 700)
    } catch {
      setMsg({ type: 'err', text: '网络错误，请稍后重试' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-mask" onClick={(event) => event.target === event.currentTarget && !busy && onClose()} role="presentation">
      <div ref={dialogRef} className="modal batch-modal" role="dialog" aria-modal="true" aria-labelledby="batch-title">
        <div className="modal-head">
          <div>
            <h2 id="batch-title">批量核对</h2>
            <p className="batch-subtitle">确认报告原文中信息完整的项目，不会补写缺失字段。</p>
          </div>
          <button type="button" className="modal-x" onClick={onClose} disabled={busy} aria-label="关闭批量核对窗口">
            <IconClose />
          </button>
        </div>

        <div className="batch-toolbar">
          <label className="batch-select-all">
            <input
              type="checkbox"
              checked={eligible.length > 0 && selected.size === eligible.length}
              onChange={selectAll}
              disabled={!eligible.length || busy}
            />
            <span>选择全部可批量项目</span>
          </label>
          <span>{selected.size} / {eligible.length} 项已选择</span>
        </div>

        <div className="batch-body">
          {eligible.length > 0 ? (
            <div className="batch-list" aria-label="可批量核对项目">
              {eligible.map(({ analyte, draft }) => (
                <label className="batch-row" key={analyte.id}>
                  <input type="checkbox" checked={selected.has(analyte.id)} disabled={busy} onChange={() => toggle(analyte.id)} />
                  <span className="batch-name">{draft.name}</span>
                  <span className="batch-value">{draft.value}{draft.unit ? ` ${draft.unit}` : ''}</span>
                  <span className="batch-ref">参考 {draft.ref || '未提供'}</span>
                </label>
              ))}
            </div>
          ) : (
            <div className="batch-empty">没有可以安全批量核对的项目。</div>
          )}

          {excluded.length > 0 && (
            <details className="batch-excluded" open={!eligible.length}>
              <summary>{excluded.length} 项需要单独处理</summary>
              <ul>
                {excluded.map(({ analyte, reason }) => <li key={analyte.id}><b>{analyte.name}</b><span>{reason}</span></li>)}
              </ul>
            </details>
          )}
        </div>

        {msg && <div className={`modal-msg is-${msg.type}`} role={msg.type === 'err' ? 'alert' : 'status'} aria-live="polite">{msg.text}</div>}
        <div className="batch-footer">
          <button type="button" className="btn" onClick={onClose} disabled={busy}>取消</button>
          <button type="button" className="btn btn--primary" onClick={submit} disabled={busy || selected.size === 0}>
            <IconCheck />
            {busy ? '正在核对…' : `确认选中的 ${selected.size} 项`}
          </button>
        </div>
      </div>
    </div>
  )
}

function ReportView({ report, onRefresh, onExportCsv, onImport, onReportUpdated }) {
  const [filter, setFilter] = useState('all')
  const [showBatch, setShowBatch] = useState(false)
  const [showMetadata, setShowMetadata] = useState(false)

  useEffect(() => {
    setShowBatch(false)
    setShowMetadata(false)
  }, [report?.id])

  if (!report) {
    return (
      <>
        <MainHead crumb={['报告', '—']} ops={<button type="button" className="btn btn--primary" onClick={onImport}><IconPlus />导入报告</button>} />
        <div className="content content--scroll">
          <div className="card">
            <div className="empty">
              <IconInbox />
              <span>左侧还没有报告可选。先导入一份，再逐项核对。</span>
            </div>
          </div>
        </div>
      </>
    )
  }

  const list = report.analytes.filter((a) => {
    if (filter === 'abnormal') return a.status === 'confirmed' && (a.interpretation === 'high' || a.interpretation === 'low')
    if (filter === 'pending') return a.status !== 'confirmed'
    return true
  })

  const total = report.analytes.length
  const confirmed = report.analytes.filter((a) => a.status === 'confirmed').length

  const tally = { 偏高: 0, 偏低: 0, 正常: 0, 无法比较: 0, 定性结果: 0, 暂不判读: 0 }
  report.analytes.forEach((a) => {
    if (a.status !== 'confirmed') {
      tally['暂不判读'] += 1
      return
    }
    const label = (INTERP[a.interpretation] || {}).label
    if (label && label in tally) tally[label] += 1
  })
  const tallyText = Object.entries(tally)
    .filter(([, n]) => n > 0)
    .map(([k, n]) => `${k} ${n}`)
    .join(' · ')

  return (
    <>
      <MainHead
        crumb={['报告', report.patient_label]}
        ops={
          <>
            <button type="button" className="btn" onClick={onRefresh}>
              <IconRefresh />
              刷新
            </button>
            <button type="button" className="btn btn--outline" onClick={onExportCsv}>
              <IconDownload />
              导出 CSV
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => setFilter('pending')}
              disabled={confirmed === total}
            >
              {confirmed === total ? '无待核对项' : `待核对 ${total - confirmed} 项`}
            </button>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => setShowBatch(true)}
              disabled={confirmed === total}
            >
              <IconCheck />
              {confirmed === total ? '已全部核对' : '批量核对'}
            </button>
          </>
        }
      />

      <MainTitle
        title={report.patient_label}
        badge={
          confirmed === total ? (
            <span className="badge badge--ok badge--lg">已核对</span>
          ) : (
            <span className="badge badge--pending badge--lg">待核对 {total - confirmed}</span>
          )
        }
        sub={report.source_note || '参考范围仅取自本报告原文，不跨报告套用统一阈值。'}
        meta={[
          { k: '医院', v: report.hospital || '—' },
          { k: '检查日期', v: report.collected_at || '—' },
          { k: '类型', v: report.exam_type },
          { k: '指标数', v: `${total} 项` },
        ]}
        action={
          <button type="button" className="title-edit-btn" onClick={() => setShowMetadata(true)}>
            编辑报告信息
          </button>
        }
      />

      <div className="work-area">
        <div className="panel panel--image">
          <div className="panel-head">
            <span className="panel-head-t">原报告图片</span>
            <span className="panel-head-meta">{report.image_url ? '100%' : '—'}</span>
          </div>
          <div className="panel-img">
            {report.image_url ? (
              <img src={report.image_url} alt={`${report.patient_label} 原报告`} />
            ) : (
              <div className="img-empty">
                <IconImage />
                <span>无原图</span>
                <span>仅「图片识别」导入的报告会保留原图</span>
              </div>
            )}
          </div>
          <div className="panel-foot">
            <span>仅图片识别结果保留原图</span>
            <button type="button" className="link-btn" onClick={onImport}>
              {report.image_url ? '替换图片' : '导入带图报告'}
            </button>
          </div>
        </div>

        <div className="panel panel--table">
          <div className="panel-head">
            <span className="panel-head-t">
              本次报告结果
              <em>{total} 项</em>
            </span>
            <div className="seg">
              {[
                ['all', '全部'],
                ['abnormal', '异常'],
                ['pending', '待核对'],
              ].map(([k, label]) => (
                <button type="button" key={k} className={`seg-item${filter === k ? ' is-active' : ''}`} onClick={() => setFilter(k)}>
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="table-scroll">
            <div className="tbl">
              <div className="tbl-head">
                <span className="col-name">指标名称</span>
                <span className="col-cat">类别</span>
                <span className="col-num al-r">结果</span>
                <span className="col-unit">单位</span>
                <span className="col-ref">参考范围</span>
                <span className="col-verdict">规则判读</span>
                <span className="col-status">核对状态</span>
              </div>

              {list.map((a) => (
                <AnalyteRow key={`${report.id}-${a.id}`} a={a} reportId={report.id} onSaved={onRefresh} />
              ))}

              {list.length === 0 && (
                <div className="empty">
                  <IconInbox />
                  <span>当前筛选下没有指标。</span>
                </div>
              )}
            </div>
          </div>

          <div className="total-row">
            <span>合计 {list.length} 项</span>
            <span>{tallyText || '—'}</span>
          </div>

          <div className="panel-foot">
            <span className="progress">
              <span className="progress-track">
                <span className="progress-fill" style={{ width: `${total ? (confirmed / total) * 100 : 0}%` }} />
              </span>
              <span className="progress-txt">
                {confirmed} / {total} 已核对
              </span>
            </span>
            <span className="save-dot">
              <i />
              点击保存或确认后入库
            </span>
          </div>
        </div>
      </div>
      {showBatch && (
        <BatchReviewModal
          key={report.id}
          report={report}
          onClose={() => setShowBatch(false)}
          onComplete={onRefresh}
        />
      )}
      {showMetadata && (
        <ReportMetadataModal
          key={report.id}
          report={report}
          onClose={() => setShowMetadata(false)}
          onSaved={onReportUpdated}
        />
      )}
    </>
  )
}

/* ============================================================================
   视图三：04 · 指标趋势
   ========================================================================== */

function TrendsView({ trends, groups, onImport, onExport }) {
  const [onlyAbnormal, setOnlyAbnormal] = useState(false)

  const shown = useMemo(() => (onlyAbnormal ? trends.filter((t) => t.abnormal) : trends), [trends, onlyAbnormal])

  const shownGroups = useMemo(() => {
    const m = new Map()
    shown.forEach((t) => {
      if (!m.has(t.category)) m.set(t.category, [])
      m.get(t.category).push(t)
    })
    return [...m.entries()].map(([cat, list]) => ({ cat, list })).sort((a, b) => b.list.length - a.list.length)
  }, [shown])

  const kpi = useMemo(() => {
    const cats = new Set(trends.map((t) => t.category))
    return {
      series: trends.length,
      cats: cats.size,
      abnormal: trends.filter((t) => t.abnormal).length,
      flat: trends.filter((t) => t.trend === 'flat').length,
    }
  }, [trends])

  return (
    <>
      <MainHead
        crumb={['工作区', '指标趋势']}
        ops={
          <>
            <button type="button" className={`btn btn--outline${onlyAbnormal ? ' is-on' : ''}`} onClick={() => setOnlyAbnormal((v) => !v)}>
              只看异常指标
            </button>
            <button type="button" className="btn btn--accent" onClick={onExport}>
              <IconDownload />
              导出趋势
            </button>
            <button type="button" className="btn btn--primary" onClick={onImport}>
              <IconPlus />
              导入报告
            </button>
          </>
        }
      />

      <MainTitle
        title="指标趋势"
        badge={<span className="badge badge--plain badge--lg">{trends.length} 条序列</span>}
        sub="同一指标跨多次检查的变化，只取「已核对且有数值」的点；方向只描述数值升降，不代表好转或恶化。"
      />

      <div className="content content--scroll">
        <div className="kpi-row">
          <Kpi label="趋势序列" value={kpi.series} unit="条" />
          <Kpi label="覆盖分类" value={kpi.cats} unit="类" />
          <Kpi label="最新异常" value={kpi.abnormal} unit="条" tone={kpi.abnormal ? 'high' : undefined} />
          <Kpi label="区间内平稳" value={kpi.flat} unit="条" />
        </div>

        <div className="legend">
          <span className="legend-i">
            <i className="legend-dot" style={{ background: 'var(--c-high)' }} />
            偏高（超出本报告上限）
          </span>
          <span className="legend-i">
            <i className="legend-dot" style={{ background: 'var(--c-low)' }} />
            偏低（低于本报告下限）
          </span>
          <span className="legend-i">
            <i className="legend-dot" style={{ background: 'var(--c-ok)' }} />
            在参考范围内
          </span>
          <span className="legend-i">
            <i className="legend-dot" style={{ background: 'var(--c-text-4)' }} />
            报告未提供参考范围
          </span>
          <span className="legend-i">
            <i className="legend-dash" />
            区间内平稳（首尾差 ±5% 以内）
          </span>
        </div>

        {shownGroups.length === 0 ? (
          <div className="card">
            <div className="empty">
              <IconInbox />
              <span>
                {trends.length === 0
                  ? '暂无趋势数据。每个指标至少需要 2 次「已核对且有数值」的检查才会成线。'
                  : '当前筛选下没有异常序列。'}
              </span>
            </div>
          </div>
        ) : (
          <div className="trend-board">
            {shownGroups.map(({ cat, list }) => {
              // 分类块最多占两列（= 看板的一整行）。
              // 不按序列条数铺满（血常规 4 条会变成 4 张细长卡，图被压扁、轴标签互压）——
              // 设计稿的口径是卡片保持可读宽度，内容变高，靠内容区滚动去看。
              const span = Math.min(list.length, 2)
              return (
                <section className="trend-grp" key={cat} style={{ gridColumn: `span ${span}` }}>
                  <div className="trend-grp-head">
                    {cat}
                    <em>{list.length} 条序列</em>
                  </div>
                  <div className="trend-cards" style={{ '--n': span }}>
                    {list.map((t) => (
                      <TrendCard key={`${t.category}-${t.name}`} t={t} />
                    ))}
                  </div>
                </section>
              )
            })}
          </div>
        )}

        <div className="cat-note">
          趋势方向仅描述数值随时间的变化，不代表好转或恶化，不构成任何医学解读。每条曲线的参考带来自各报告原文，
          <b>不跨报告套用统一阈值</b>；报告未提供范围的那一段不画带。
        </div>
      </div>
    </>
  )
}

function TrendCard({ t }) {
  const valCls = t.latest_interpretation === 'high' ? ' is-high' : t.latest_interpretation === 'low' ? ' is-low' : ''
  const missing = t.latest_interpretation === 'no_range'
  const nonNumeric = t.latest_interpretation === 'not_numeric'

  return (
    <article className="tcard">
      <div className="tcard-head">
        <div>
          <div className="tcard-name">{t.name}</div>
          <div className="tcard-sub">
            {t.category} · {t.unit || '单位未填'} · {trendArrow(t.trend)} {t.trend === 'flat' ? '平稳' : t.trend === 'up' ? '上升' : '下降'}
          </div>
        </div>
        <div className="tcard-val">
          <b className={valCls}>{t.latest_value}</b>
          <span>{t.latest_date ? String(t.latest_date).slice(2, 10) : ''}</span>
        </div>
      </div>

      <div className="tcard-chart">
        <LineChart metric={t} chartId={`${t.category}-${t.name}`} />
      </div>

      {(missing || nonNumeric) && (
        <div className="tcard-note">
          {missing
            ? '最近一次报告未提供参考范围，因此不做范围内／外判断。'
            : '最近一次结果为定性结果，数值规则不适用。'}
        </div>
      )}
    </article>
  )
}

/* ============================================================================
   视图四：05 · 异常指标概览
   ========================================================================== */

function CategoriesView({ catGroups, seriesCount, onImport, onExportOverview }) {
  const totalAbnormal = catGroups.reduce((n, g) => n + g.abnormalCount, 0)

  return (
    <>
      <MainHead
        crumb={['工作区', '异常指标概览']}
        ops={
          <>
            <button type="button" className="btn btn--outline" onClick={onExportOverview}>
              <IconDownload />
              导出概览
            </button>
            <button type="button" className="btn btn--primary" onClick={onImport}>
              <IconPlus />
              导入报告
            </button>
          </>
        }
      />

      <MainTitle
        title="异常指标概览"
        badge={<span className="badge badge--plain badge--lg">{catGroups.length} 个类别</span>}
        sub="按指标类别归集「已核对且超出参考范围」的项，取各类别最近一次检查结果；未核对的项不参与判定。"
      />

      <div className="content content--scroll">
        <div className="kpi-row">
          <Kpi label="覆盖类别" value={catGroups.length} unit="类" />
          <Kpi label="趋势序列" value={seriesCount} unit="条" />
          <Kpi label="超出参考范围" value={totalAbnormal} unit="项" tone={totalAbnormal ? 'high' : undefined} />
          <Kpi label="无异常类别" value={catGroups.filter((g) => g.abnormalCount === 0).length} unit="类" />
        </div>

        {catGroups.length === 0 ? (
          <div className="card">
            <div className="empty">
              <IconInbox />
              <span>暂无可用类别。需要至少 2 次「已核对且有数值」的检查才能形成序列。</span>
            </div>
          </div>
        ) : (
          <div className="cat-grid">
            {catGroups.map((g) => (
              <section className="card" key={g.cat}>
                <div className="card-head">
                  <span className="card-head-t">{g.cat}</span>
                  {g.abnormalCount > 0 ? (
                    <span className="badge badge--high">{g.abnormalCount} 项异常</span>
                  ) : (
                    <span className="badge badge--ok">无异常</span>
                  )}
                </div>

                <div className="cat-meta-row">
                  最近 {g.latestDate || '—'} · 共 {g.list.length} 条趋势序列
                </div>

                <div className="cat-list">
                  {g.list.map((t) => {
                    const cls = t.latest_interpretation === 'high' ? ' is-high' : t.latest_interpretation === 'low' ? ' is-low' : ''
                    const tone =
                      t.latest_interpretation === 'high'
                        ? { label: '偏高', cls: 'badge--high' }
                        : t.latest_interpretation === 'low'
                          ? { label: '偏低', cls: 'badge--low' }
                          : t.latest_interpretation === 'within'
                            ? { label: '范围内', cls: 'badge--ok' }
                            : { label: '无范围', cls: 'badge--neutral' }
                    return (
                      <div className="cat-row" key={t.name}>
                        <span className="cat-row-l">
                          <span className="cat-row-n">{t.name}</span>
                          <span className="cat-row-d">{t.latest_date || '—'}</span>
                        </span>
                        <span className="cat-row-r">
                          <span className={`cat-row-v${cls}`}>{t.latest_value}</span>
                          <span className="cat-row-u">{t.unit || ''}</span>
                          <span className={`badge ${tone.cls}`}>{tone.label}</span>
                        </span>
                      </div>
                    )
                  })}
                </div>
              </section>
            ))}
          </div>
        )}

        <div className="cat-note">
          「异常」指该指标数值超出<b>其所属报告原文</b>给出的参考范围，不代表诊断结论；未核对、或报告未提供参考范围的项不计入。
          分类依据为项目内置指标字典，与各报告原文的书写顺序无关。
        </div>
      </div>
    </>
  )
}

/* ============================================================================
   主应用
   ========================================================================== */

export default function App() {
  const [reports, setReports] = useState([])
  const [trends, setTrends] = useState([])
  const [currentId, setCurrentId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showImport, setShowImport] = useState(false)
  const [query, setQuery] = useState('')
  const [toast, setToast] = useState(null)
  const [view, setViewState] = useState(readViewFromHash)

  const setView = (v) => {
    setViewState(v)
    const target = VIEW_HASH[v] || ''
    if (window.location.hash !== target) {
      window.history.replaceState(null, '', target || window.location.pathname)
    }
  }

  const flash = (text, type = 'ok') => {
    setToast({ text, type })
    window.setTimeout(() => setToast(null), 2600)
  }

  const loadReports = async () => {
    const res = await fetch('/api/reports')
    const data = await res.json()
    setReports(data)
    if (data.length) setCurrentId((prev) => (prev != null && data.some((r) => r.id === prev) ? prev : data[0].id))
    setLoading(false)
  }

  const loadTrends = async () => {
    try {
      const res = await fetch('/api/trends')
      const data = await res.json()
      setTrends(data.items || [])
    } catch {
      setTrends([])
    }
  }

  const refreshAll = async () => {
    await Promise.all([loadReports(), loadTrends()])
  }

  useEffect(() => {
    refreshAll()
  }, [])

  // 浏览器前进/后退时同步
  useEffect(() => {
    const onHash = () => setViewState(readViewFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const current = reports.find((r) => r.id === currentId) || null

  const stats = useMemo(() => {
    let analytes = 0
    let abnormal = 0
    let pending = 0
    reports.forEach((r) =>
      r.analytes.forEach((a) => {
        analytes += 1
        if (a.status === 'confirmed' && (a.interpretation === 'high' || a.interpretation === 'low')) abnormal += 1
        if (a.status === 'unchecked') pending += 1
      }),
    )
    return { reports: reports.length, analytes, abnormal, pending }
  }, [reports])

  const pendingTasks = useMemo(() => {
    const out = []
    reports.forEach((r) =>
      r.analytes.forEach((a) => {
        if (a.status === 'unchecked') out.push({ ...a, reportId: r.id, reportLabel: r.patient_label })
      }),
    )
    return out
  }, [reports])

  const catGroups = useMemo(() => {
    const m = new Map()
    trends.forEach((t) => {
      if (!m.has(t.category)) m.set(t.category, [])
      m.get(t.category).push(t)
    })
    return [...m.entries()]
      .map(([cat, list]) => ({
        cat,
        list,
        abnormalCount: list.filter((t) => t.abnormal).length,
        latestDate: list.map((t) => t.latest_date || '').sort().slice(-1)[0] || '',
      }))
      .sort((a, b) => b.abnormalCount - a.abnormalCount || b.list.length - a.list.length || a.cat.localeCompare(b.cat, 'zh'))
  }, [trends])

  // ---- 动作 ----
  const openReport = (id) => {
    setCurrentId(id)
    setView('report')
  }

  const handleImported = (newReport) => {
    setReports((prev) => [...prev, newReport])
    setCurrentId(newReport.id)
    setView('report')
    loadTrends()
  }

  const handleReportUpdated = async (updatedReport) => {
    setReports((previous) => previous.map((report) => (
      report.id === updatedReport.id ? updatedReport : report
    )))
    await loadTrends()
    flash('报告信息已更新')
  }

  const downloadCsv = (filename, rows) => {
    const csv = rows.map((r) => r.map((c) => `"${String(c ?? '').replace(/"/g, '""')}"`).join(',')).join('\r\n')
    const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  const exportCsv = () => {
    if (!current) return
    const rows = [['报告', '指标名称', '类别', '结果', '单位', '参考范围', '规则判读', '核对状态']]
    current.analytes.forEach((a) => {
      const confirmed = a.status === 'confirmed'
      rows.push([
        current.patient_label,
        a.name,
        a.category || '其他',
        confirmed ? (a.value ?? a.result_text ?? '') : a.raw_value,
        a.unit || a.raw_unit || '',
        a.ref_low != null && a.ref_high != null ? `${a.ref_low}-${a.ref_high}` : a.ref_text || a.raw_ref_range || '',
        confirmed ? (INTERP[a.interpretation] || {}).label || '' : '暂不判读',
        (STATUS[a.status] || {}).label || a.status,
      ])
    })
    downloadCsv(`${current.patient_label}-核对结果.csv`, rows)
    flash('已导出该报告的核对结果')
  }

  const exportAll = () => {
    const rows = [['报告', '类型', '日期', '指标数', '超出参考范围', '待核对']]
    reports.forEach((r) => {
      rows.push([
        r.patient_label,
        r.exam_type,
        r.collected_at || '',
        r.analytes.length,
        r.analytes.filter((a) => a.status === 'confirmed' && (a.interpretation === 'high' || a.interpretation === 'low')).length,
        r.analytes.filter((a) => a.status === 'unchecked').length,
      ])
    })
    downloadCsv('报告总览.csv', rows)
    flash('已导出报告总览')
  }

  const exportOverview = () => {
    const rows = [['类别', '指标名称', '最新值', '单位', '判读', '最近检查日期', '序列点数']]
    catGroups.forEach((g) =>
      g.list.forEach((t) => {
        rows.push([g.cat, t.name, t.latest_value, t.unit || '', (INTERP[t.latest_interpretation] || {}).label || '', t.latest_date || '', t.points.length])
      }),
    )
    downloadCsv('异常指标概览.csv', rows)
    flash('已导出异常指标概览')
  }

  const exportTrends = () => {
    const rows = [['类别', '指标名称', '单位', '日期', '数值', '该次参考下限', '该次参考上限', '该次判读']]
    trends.forEach((t) =>
      t.points.forEach((p) => {
        rows.push([
          t.category,
          t.name,
          t.unit || '',
          p.date,
          p.value,
          p.ref_low ?? '',
          p.ref_high ?? '',
          (INTERP[p.interpretation] || {}).label || '',
        ])
      }),
    )
    downloadCsv('指标趋势明细.csv', rows)
    flash(`已导出 ${trends.length} 条序列的明细`)
  }

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner" />
      </div>
    )
  }

  const hasRail = view === 'overview' || view === 'report' || view === 'trends'

  return (
    <div className="shell">
      <TopBar
        query={query}
        onQuery={setQuery}
        view={view}
        onView={setView}
        onHelp={() => flash('参考范围只取自各报告原文，不跨报告套用统一阈值。')}
      />

      <div className="body">
        {hasRail && (
          <Rail
            view={view}
            reports={reports}
            trends={trends}
            currentId={currentId}
            query={query}
            onPickReport={openReport}
            onPickSeries={() => setView('trends')}
            onImport={() => setShowImport(true)}
          />
        )}

        <main className="main">
          {view === 'overview' && (
            <OverviewView
              reports={reports}
              trends={trends}
              stats={stats}
              pendingTasks={pendingTasks}
              onOpenReport={openReport}
              onImport={() => setShowImport(true)}
              onExportAll={exportAll}
            />
          )}

          {view === 'report' && (
            <ReportView
              report={current}
              onRefresh={refreshAll}
              onExportCsv={exportCsv}
              onImport={() => setShowImport(true)}
              onReportUpdated={handleReportUpdated}
            />
          )}

          {view === 'trends' && (
            <TrendsView trends={trends} groups={catGroups} onImport={() => setShowImport(true)} onExport={exportTrends} />
          )}

          {view === 'categories' && (
            <CategoriesView
              catGroups={catGroups}
              seriesCount={trends.length}
              onImport={() => setShowImport(true)}
              onExportOverview={exportOverview}
            />
          )}
        </main>
      </div>

      {toast && <div className={`toast is-${toast.type}`} role={toast.type === 'err' ? 'alert' : 'status'} aria-live="polite">{toast.text}</div>}

      <ImportModal open={showImport} onClose={() => setShowImport(false)} onImported={handleImported} />
    </div>
  )
}
