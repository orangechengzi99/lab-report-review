import { useEffect, useRef, useState } from 'react'
import { IconClose } from './icons.jsx'
import { REPORT_TYPES } from './reportMetadata.js'

const today = () => {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

/** 三条导入路径都只创建待核对草稿，日期用于真实趋势排序。 */
export default function ImportModal({ open, onClose, onImported }) {
  const dialogRef = useRef(null)
  const [tab, setTab] = useState('deepseek')
  const [csvText, setCsvText] = useState('')
  const [reportText, setReportText] = useState('')
  const [patientLabel, setPatientLabel] = useState('')
  const [examType, setExamType] = useState('血常规')
  const [collectedAt, setCollectedAt] = useState(today)
  const [hospital, setHospital] = useState('')
  const [file, setFile] = useState(null)
  const [ocrStatus, setOcrStatus] = useState(null)
  const [dsStatus, setDsStatus] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)

  useEffect(() => {
    if (!open) return undefined
    setMsg(null)
    fetch('/api/import/ocr-status')
      .then((r) => r.json())
      .then(setOcrStatus)
      .catch(() => setOcrStatus({ configured: false }))
    fetch('/api/import/deepseek-status')
      .then((r) => r.json())
      .then(setDsStatus)
      .catch(() => setDsStatus({ configured: false }))

    const previouslyFocused = document.activeElement
    const dialog = dialogRef.current
    const selector = 'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled])'
    window.requestAnimationFrame(() => dialog?.querySelector(selector)?.focus())

    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
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
  }, [open, onClose])

  if (!open) return null

  const metadata = {
    patient_label: patientLabel.trim() || '导入报告',
    exam_type: examType,
    collected_at: collectedAt,
    hospital: hospital.trim(),
  }

  const readResponse = async (res) => {
    try {
      return await res.json()
    } catch {
      return { detail: '服务器返回了无法识别的响应' }
    }
  }

  const complete = (data, verb) => {
    setMsg({ type: 'ok', text: `已${verb}「${data.exam_type}」${data.analytes.length} 项，待逐项核对` })
    onImported(data)
    window.setTimeout(onClose, 800)
  }

  const post = async (endpoint, body) => {
    if (!collectedAt) {
      setMsg({ type: 'err', text: '请选择检查日期' })
      return
    }
    setBusy(true)
    setMsg(null)
    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await readResponse(res)
      if (!res.ok) {
        setMsg({ type: 'err', text: data.detail || '操作失败' })
        return
      }
      complete(data, '解析')
    } catch {
      setMsg({ type: 'err', text: '网络错误' })
    } finally {
      setBusy(false)
    }
  }

  const doOcr = async () => {
    if (!file || !collectedAt) {
      setMsg({ type: 'err', text: !collectedAt ? '请选择检查日期' : '请选择报告图片' })
      return
    }
    setBusy(true)
    setMsg(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      Object.entries(metadata).forEach(([key, value]) => fd.append(key, value))
      const res = await fetch('/api/import/ocr', { method: 'POST', body: fd })
      const data = await readResponse(res)
      if (!res.ok) {
        setMsg({ type: 'err', text: data.detail || '识别失败' })
        return
      }
      complete(data, '识别')
    } catch {
      setMsg({ type: 'err', text: '网络错误' })
    } finally {
      setBusy(false)
    }
  }

  const dsOff = dsStatus && !dsStatus.configured
  const ocrOff = ocrStatus && !ocrStatus.configured

  return (
    <div className="modal-mask" onClick={(e) => e.target === e.currentTarget && !busy && onClose()} role="presentation">
      <div ref={dialogRef} className="modal" role="dialog" aria-modal="true" aria-labelledby="import-title">
        <div className="modal-head">
          <h2 id="import-title">导入检验报告</h2>
          <button type="button" className="modal-x" onClick={onClose} disabled={busy} aria-label="关闭导入窗口">
            <IconClose />
          </button>
        </div>

        <div className="modal-tabs" role="tablist" aria-label="导入方式">
          {[
            ['deepseek', '文本解析（AI）'],
            ['table', '表格导入'],
            ['ocr', '图片识别'],
          ].map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={tab === key}
              aria-controls={`import-panel-${key}`}
              className={tab === key ? 'tab is-active' : 'tab'}
              onClick={() => { setTab(key); setMsg(null) }}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="modal-fields">
          <label className="field-group field-grow" htmlFor="import-label">
            <span className="field-label">报告标签</span>
            <input id="import-label" className="field" placeholder="例如 DEMO-003（可选）" value={patientLabel} onChange={(e) => setPatientLabel(e.target.value)} />
          </label>
          <label className="field-group" htmlFor="import-type">
            <span className="field-label">检查类型</span>
            <select id="import-type" className="field" value={examType} onChange={(e) => setExamType(e.target.value)}>
              {REPORT_TYPES.map((type) => <option key={type}>{type}</option>)}
            </select>
          </label>
          <label className="field-group" htmlFor="import-date">
            <span className="field-label">检查日期 <em>必填</em></span>
            <input id="import-date" className="field" type="date" required value={collectedAt} onChange={(e) => setCollectedAt(e.target.value)} />
          </label>
          <label className="field-group field-grow" htmlFor="import-hospital">
            <span className="field-label">医院</span>
            <input id="import-hospital" className="field" placeholder="可选" value={hospital} onChange={(e) => setHospital(e.target.value)} />
          </label>
        </div>

        <div className="modal-body" id={`import-panel-${tab}`} role="tabpanel">
          {tab === 'deepseek' && (
            <>
              {dsOff && <p className="modal-warn" role="status">文本解析未配置密钥，该入口当前不可用。</p>}
              <p className="privacy-note">粘贴的报告文字会发送给已配置的 AI 服务进行解析；请先确认数据使用要求，避免提交不必要的个人身份信息。</p>
              <label className="field-group" htmlFor="import-report-text">
                <span className="field-label">报告文字</span>
                <textarea id="import-report-text" rows={7} placeholder={'粘贴报告文字内容，AI 解析成待核对草稿\n\n例如：\n白细胞计数 9.2 10^9/L 参考范围 3.5-9.5'} value={reportText} onChange={(e) => setReportText(e.target.value)} />
              </label>
              <button type="button" className="modal-btn" disabled={busy || !reportText.trim() || !collectedAt || !!dsOff} onClick={() => post('/api/import/deepseek', { text: reportText, ...metadata })}>
                {busy ? '解析中…' : 'AI 解析'}
              </button>
            </>
          )}

          {tab === 'table' && (
            <>
              <label className="field-group" htmlFor="import-table-text">
                <span className="field-label">表格内容</span>
                <textarea id="import-table-text" rows={7} placeholder={'每行一条：指标名,结果,单位,参考范围\n\n白细胞计数,9.2,10^9/L,3.5-9.5'} value={csvText} onChange={(e) => setCsvText(e.target.value)} />
              </label>
              <button type="button" className="modal-btn" disabled={busy || !csvText.trim() || !collectedAt} onClick={() => post('/api/import/table', { csv_text: csvText, ...metadata })}>
                {busy ? '导入中…' : '导入'}
              </button>
            </>
          )}

          {tab === 'ocr' && (
            <>
              {ocrOff && <p className="modal-warn" role="status">图片识别未配置密钥，该入口当前不可用。</p>}
              <p className="privacy-note">图片会发送给已配置的 AI 服务进行识别，并保存在本机私有运行目录；请勿把真实报告图片提交到 Git。</p>
              <label className="field-group" htmlFor="import-image">
                <span className="field-label">报告图片（PNG、JPEG、GIF 或 WebP，最大 10 MB）</span>
                <input id="import-image" type="file" accept="image/png,image/jpeg,image/gif,image/webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              </label>
              {file && <span className="selected-file">已选择：{file.name}</span>}
              <button type="button" className="modal-btn" disabled={busy || !file || !collectedAt || !!ocrOff} onClick={doOcr}>
                {busy ? '识别中…' : '识别图片'}
              </button>
            </>
          )}
        </div>

        {msg && <div className={`modal-msg is-${msg.type}`} role={msg.type === 'err' ? 'alert' : 'status'} aria-live="polite">{msg.text}</div>}
      </div>
    </div>
  )
}
