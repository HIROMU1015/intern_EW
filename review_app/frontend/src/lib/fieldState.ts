import type { Corrections, FieldValue } from '../types'

export type FieldStatus = 'read' | 'inferred' | 'attention' | 'missing' | 'not_stated' | 'corrected'

export interface FieldView {
  status: FieldStatus
  /** 色だけに頼らないための短い状態ラベル。 */
  statusLabel: string
  /** 主役として見せる値。 */
  displayValue: string
  /** 修正前の読み取り値（修正済みのときだけ使う）。 */
  originalValue: string
  originLabel: string
  corrected: boolean
  /** 担当者が「不明」に戻した状態。 */
  correctedToUnknown: boolean
  noteLabels: string[]
}

/** 値がない・読めないことを示す注記。0やfalseへは決して変換しない。 */
const ATTENTION_NOTES: Record<string, string> = {
  uncertain_marker: '読み取りが不確か',
  multiple_values: '複数の値が読み取られた',
  no_number_found: '数値として読み取れない',
  per_meter_value: '単位が異なる（1mあたり）',
  search_unsupported_dimension: '検索に使える寸法表記ではない',
  empty_after_cleanup: '整形後に値が残らない',
  boolean_value: '真偽値として記録されている',
}

const ORIGIN_LABELS: Record<string, string> = {
  drawing: '原図',
  partial: '原図（一部一致）',
  inferred: '推定',
  unknown: '出所不明',
}

const NOT_STATED_PATTERN = /^(記載なし|なし|該当なし|非対応)$/

export function showValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return ''
  if (Array.isArray(value)) return value.map((entry) => showValue(entry)).filter(Boolean).join(' / ')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function correctionDisplay(key: string, value: unknown): string {
  if (key === 'waterproof') {
    const labels: Record<string, string> = {
      unknown: '不明',
      none: '非対応・該当なし',
      damp: '防湿型',
      waterproof: '防雨型',
      damp_and_waterproof: '防湿・防雨型',
    }
    return labels[String(value)] ?? showValue(value)
  }
  if (key === 'dimming') {
    const labels: Record<string, string> = { unknown: '不明', true: '調光', false: '非調光' }
    return labels[String(value)] ?? showValue(value)
  }
  return showValue(value)
}

/**
 * 読み取り項目の状態を決める。
 * 「未取得」と「要確認」を混同しない。記載なしは裏付けがあるときだけ使う。
 */
export function fieldView(field: FieldValue, corrections: Corrections | undefined): FieldView {
  const specs = corrections?.specifications ?? {}
  const hasCorrection = Object.prototype.hasOwnProperty.call(specs, field.key)
  const rawText = showValue(field.raw)
  const originLabel = ORIGIN_LABELS[field.origin] ?? ORIGIN_LABELS.unknown
  const noteLabels = field.notes.map((note) =>
    note.startsWith('approximate:') ? `おおよその値（${note.split(':')[1]}）` : (ATTENTION_NOTES[note] ?? note),
  )

  if (hasCorrection) {
    const value = specs[field.key]
    const toUnknown = value === null || value === ''
    return {
      status: 'corrected',
      statusLabel: toUnknown ? '修正済み（不明）' : '修正済み',
      displayValue: toUnknown ? '不明' : correctionDisplay(field.key, value),
      originalValue: rawText,
      originLabel,
      corrected: true,
      correctedToUnknown: toUnknown,
      noteLabels,
    }
  }

  if (!rawText) {
    return {
      status: 'missing',
      statusLabel: '未取得',
      displayValue: '未取得',
      originalValue: '',
      originLabel,
      corrected: false,
      correctedToUnknown: false,
      noteLabels,
    }
  }

  if (NOT_STATED_PATTERN.test(rawText.trim())) {
    return {
      status: 'not_stated',
      statusLabel: '記載なし',
      displayValue: '記載なし',
      originalValue: rawText,
      originLabel,
      corrected: false,
      correctedToUnknown: false,
      noteLabels,
    }
  }

  const needsAttention = field.notes.some((note) => note in ATTENTION_NOTES)
  if (needsAttention) {
    return {
      status: 'attention',
      statusLabel: '要確認',
      displayValue: rawText,
      originalValue: rawText,
      originLabel,
      corrected: false,
      correctedToUnknown: false,
      noteLabels,
    }
  }

  if (field.origin === 'inferred') {
    return {
      status: 'inferred',
      statusLabel: '推定',
      displayValue: rawText,
      originalValue: rawText,
      originLabel,
      corrected: false,
      correctedToUnknown: false,
      noteLabels,
    }
  }

  return {
    status: 'read',
    statusLabel: '読取あり',
    displayValue: rawText,
    originalValue: rawText,
    originLabel,
    corrected: false,
    correctedToUnknown: false,
    noteLabels,
  }
}
