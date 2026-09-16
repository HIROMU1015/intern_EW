import type { Candidate } from '../types'

export interface DiffField {
  key: string
  label: string
  /** 表示中の候補で値が割れているか。 */
  differs: boolean
  /** DBに値がない候補の件数。0やfalseとしては扱わない。 */
  missingCount: number
  values: (string | null)[]
}

export interface CandidateDiff {
  comparable: boolean
  fields: DiffField[]
  differingLabels: string[]
  /** 値は同じだが、一部の候補でDB情報が欠けている項目。 */
  partialLabels: string[]
  priceDiffers: boolean
}

function text(value: unknown): string | null {
  if (value === null || value === undefined) return null
  const normalized = String(value)
    .normalize('NFKC')
    .replace(/[\s・,，]/g, '')
    .trim()
  return normalized === '' ? null : normalized
}

function numberText(value: unknown, unit: string): string | null {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  if (Number.isNaN(parsed)) return null
  return `${parsed}${unit}`
}

/** 商品選定に効く主要仕様だけを比較する。ID・順位・スコアは対象にしない。 */
const EXTRACTORS: { key: string; label: string; get: (candidate: Candidate) => string | null }[] = [
  { key: 'akarusa', label: '明るさ区分', get: (c) => text(c.record.t_akarusa) },
  { key: 'luminous_flux', label: '光束', get: (c) => numberText(c.record.parsed_hints?.luminous_flux_lm, 'lm') },
  { key: 'color_temperature', label: '色温度', get: (c) => numberText(c.record.parsed_hints?.color_temperature_k, 'K') },
  { key: 'power', label: '消費電力', get: (c) => numberText(c.record.parsed_hints?.power_consumption_w, 'W') },
  {
    key: 'voltage',
    label: '電圧',
    get: (c) => {
      const min = c.record.parsed_hints?.voltage_min_v
      const max = c.record.parsed_hints?.voltage_max_v
      if (min === null || min === undefined) return null
      return max === null || max === undefined || max === min ? `${min}V` : `${min}〜${max}V`
    },
  },
  { key: 'size', label: '器具寸法', get: (c) => text(c.record.kigusize) },
  { key: 'cutout', label: '埋込穴', get: (c) => text(c.record.umekomi_ana) },
  { key: 'mounting', label: '取付方式', get: (c) => text(c.record.t_toritsuke) },
  { key: 'waterproof', label: '防湿・防雨', get: (c) => text(c.record.boushitsu_bouu) },
  { key: 'function', label: '機能（調光ほか）', get: (c) => text(c.record.t_kinou) },
  { key: 'availability', label: '生産状態', get: (c) => text(c.record.availability) },
]

/**
 * 同じ検索（＝同じ品番タブ＝同じ構成品）の候補だけを比較する。
 * 呼び出し側で別の構成品の候補を混ぜないこと。
 */
export function computeCandidateDiff(candidates: Candidate[]): CandidateDiff {
  if (candidates.length < 2) {
    return { comparable: false, fields: [], differingLabels: [], partialLabels: [], priceDiffers: false }
  }
  const fields = EXTRACTORS.map((extractor) => {
    const values = candidates.map((candidate) => extractor.get(candidate))
    const present = values.filter((value): value is string => value !== null)
    const distinct = new Set(present)
    return {
      key: extractor.key,
      label: extractor.label,
      differs: distinct.size > 1,
      missingCount: values.length - present.length,
      values,
    }
  })
  const prices = candidates.map((candidate) => candidate.record.price_zeinuki)
  const presentPrices = prices.filter((value) => value !== null && value !== undefined)
  return {
    comparable: true,
    fields,
    differingLabels: fields.filter((field) => field.differs).map((field) => field.label),
    partialLabels: fields.filter((field) => !field.differs && field.missingCount > 0).map((field) => field.label),
    priceDiffers: new Set(presentPrices).size > 1,
  }
}

export function diffKeySet(diff: CandidateDiff): Set<string> {
  return new Set(diff.fields.filter((field) => field.differs).map((field) => field.key))
}

export interface CandidateSpec {
  key: string
  label: string
  value: string | null
}

/** 候補カードに並べる主要仕様。値がないものは「DB情報なし」として扱う。 */
export function candidateSpecValues(candidate: Candidate): CandidateSpec[] {
  return EXTRACTORS.map((extractor) => ({ key: extractor.key, label: extractor.label, value: extractor.get(candidate) }))
}
