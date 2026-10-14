/**
 * 图标集合 —— 全部为内联 SVG，描边走 currentColor，颜色随文字继承。
 * 不用 emoji / 图标字体：字形在不同系统上不一致，且无法精确控制描边粗细。
 */

const base = {
  fill: 'none',
  xmlns: 'http://www.w3.org/2000/svg',
  'aria-hidden': 'true',
  focusable: 'false',
}

/** 品牌标：报告 + 勾选 */
export function IconBrand({ size = 15 }) {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 16 16">
      <path
        d="M4 2.4h5.2L13 6.2V13a.6.6 0 0 1-.6.6H4a.6.6 0 0 1-.6-.6V3a.6.6 0 0 1 .6-.6Z"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
      <path d="M9 2.6v3.8h3.8" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
      <path
        d="m6 10.3 1.35 1.35L10.2 8.5"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function IconSearch({ size = 14 }) {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 14 14">
      <circle cx="6" cy="6" r="4.2" stroke="currentColor" strokeWidth="1.3" />
      <path d="m9.2 9.2 3 3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  )
}

export function IconHelp({ size = 16 }) {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 16 16">
      <circle cx="8" cy="8" r="6.4" stroke="currentColor" strokeWidth="1.2" />
      <path
        d="M6.5 6.4a1.6 1.6 0 1 1 2.1 1.6c-.4.15-.6.5-.6.9v.3"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
      />
      <circle cx="8" cy="11.4" r=".85" fill="currentColor" />
    </svg>
  )
}

export function IconChevronDown({ size = 12 }) {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 12 12">
      <path d="m3 4.8 3 3 3-3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function IconChevronRight({ size = 12 }) {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 12 12">
      <path d="m4.8 3 3 3-3 3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function IconDownload({ size = 12 }) {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 12 12">
      <path d="M6 1.6v6.1" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
      <path d="M3.6 5.4 6 7.8l2.4-2.4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M1.8 10.4h8.4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  )
}

export function IconPlus({ size = 13 }) {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 14 14">
      <path d="M7 2.6v8.8M2.6 7h8.8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

export function IconClose({ size = 14 }) {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 14 14">
      <path d="m3 3 8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

export function IconCheck({ size = 13 }) {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 14 14">
      <path d="m2.8 7.4 2.9 2.9 5.5-6.6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function IconRefresh({ size = 13 }) {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 14 14">
      <path
        d="M11.6 6.2a4.7 4.7 0 1 0-.6 3.6"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
      />
      <path d="M11.9 2.6v3.7H8.2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** 占位图片图标（无原图时用） */
export function IconImage({ size = 26 }) {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 26 26">
      <rect x="2.4" y="4.4" width="21.2" height="17.2" rx="3" stroke="currentColor" strokeWidth="1.4" />
      <circle cx="9.2" cy="10.6" r="1.9" stroke="currentColor" strokeWidth="1.4" />
      <path d="M3.4 18.6 9.8 13l5 4.4 3.2-2.4 4.6 3.6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** 空状态：托盘 */
export function IconInbox({ size = 30 }) {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 32 32">
      <path
        d="M4.6 18.4 7.8 8.2A2.8 2.8 0 0 1 10.5 6.3h11a2.8 2.8 0 0 1 2.7 1.9l3.2 10.2v5.4a2.4 2.4 0 0 1-2.4 2.4H6.9a2.4 2.4 0 0 1-2.3-2.4v-5.4Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <path d="M4.6 18.4h6.2l1.3 2.6h7.9l1.3-2.6h6.1" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  )
}
