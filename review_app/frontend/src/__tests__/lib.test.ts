import { describe, expect, it } from 'vitest'
import { fieldView } from '../lib/fieldState'
import { computeCandidateDiff } from '../lib/candidateDiff'
import { machineSummary } from '../lib/machineReason'
import type { Candidate, FieldValue } from '../types'

function field(overrides: Partial<FieldValue>): FieldValue {
  return {
    key: 'color_temperature_k',
    label: '色温度(K)',
    raw: null,
    value: null,
    origin: 'unknown',
    used_in_search: false,
    notes: [],
    ...overrides,
  }
}

describe('読み取り項目の状態', () => {
  it('値がなければ未取得。要確認にはしない', () => {
    const view = fieldView(field({}), {})
    expect(view.status).toBe('missing')
    expect(view.statusLabel).toBe('未取得')
    expect(view.displayValue).toBe('未取得')
  })

  it('原図から読めた値は読取あり', () => {
    const view = fieldView(field({ raw: '3000K', origin: 'drawing' }), {})
    expect(view.status).toBe('read')
    expect(view.statusLabel).toBe('読取あり')
    expect(view.originLabel).toBe('原図')
  })

  it('部分一致では原図と断定しない', () => {
    const view = fieldView(field({ raw: '3000K', origin: 'partial' }), {})
    expect(view.originLabel).toBe('原図（一部一致）')
  })

  it('出所が分からなければ出所不明', () => {
    const view = fieldView(field({ raw: '3000K', origin: 'unknown' }), {})
    expect(view.originLabel).toBe('出所不明')
  })

  it('読み取りが不確かな値は要確認', () => {
    const view = fieldView(field({ raw: '211?lm', origin: 'drawing', notes: ['uncertain_marker'] }), {})
    expect(view.status).toBe('attention')
    expect(view.statusLabel).toBe('要確認')
    expect(view.noteLabels).toContain('読み取りが不確か')
  })

  it('AIの補完は推定', () => {
    const view = fieldView(field({ raw: '3000K', origin: 'inferred' }), {})
    expect(view.status).toBe('inferred')
    expect(view.statusLabel).toBe('推定')
  })

  it('記載なしは、その旨が読み取れているときだけ', () => {
    expect(fieldView(field({ raw: '記載なし', origin: 'drawing' }), {}).status).toBe('not_stated')
    expect(fieldView(field({ raw: '', origin: 'drawing' }), {}).status).toBe('missing')
  })

  it('取り込み層の内部表現を画面に出さない', () => {
    // {"raw": null} や空オブジェクトは値なしとして扱う。
    for (const raw of [{ raw: null }, {}, { raw: '' }, null, undefined]) {
      const view = fieldView(field({ key: 'cutout_size', label: '埋込穴', raw, origin: 'drawing' }), {})
      expect(view.status).toBe('missing')
      expect(view.displayValue).toBe('未取得')
    }
  })

  it('原文がオブジェクトでも中身を取り出して表示する', () => {
    const view = fieldView(
      field({ key: 'cutout_size', label: '埋込穴', raw: { raw: 'φ100?' }, origin: 'drawing', notes: ['uncertain_marker'] }),
      {},
    )
    expect(view.displayValue).toBe('φ100?')
    expect(view.statusLabel).toBe('要確認')
  })

  it('原文から値を取り出せないときは正規化値を使う', () => {
    const view = fieldView(
      field({ key: 'cutout_size', label: '埋込穴', raw: { raw: null }, value: 'φ100', origin: 'drawing' }),
      {},
    )
    expect(view.displayValue).toBe('φ100')
    expect(view.statusLabel).toBe('読取あり')
  })

  it('担当者の修正は修正済みとして値を主役にする', () => {
    const view = fieldView(field({ raw: '3000K', origin: 'drawing' }), { specifications: { color_temperature_k: 5000 } })
    expect(view.status).toBe('corrected')
    expect(view.statusLabel).toBe('修正済み')
    expect(view.displayValue).toBe('5000')
    expect(view.originalValue).toBe('3000K')
  })

  it('不明へ戻した修正は0やfalseにしない', () => {
    const view = fieldView(field({ raw: '3000K' }), { specifications: { color_temperature_k: null } })
    expect(view.correctedToUnknown).toBe(true)
    expect(view.displayValue).toBe('不明')
  })

  it('防湿・防雨の修正は日本語で表示する', () => {
    const view = fieldView(field({ key: 'waterproof', label: '防湿・防雨' }), { specifications: { waterproof: 'none' } })
    expect(view.displayValue).toBe('非対応・該当なし')
  })
})

function candidate(overrides: Record<string, unknown>, price: number | null = 1000): Candidate {
  return {
    rank: 1,
    score: 100,
    matched_fields: [],
    conflicts: [],
    db_internal_warnings: [],
    lifecycle_warning: null,
    record: {
      id: 'S1',
      hinban: 'X',
      kidou: 'LE9',
      full_code: 'X LE9',
      key: '',
      view_key: '',
      kigugroup: 'ダウンライト',
      kigustyle: '',
      t_kigubunrui: '',
      t_kigugroup: '',
      price_zeinuki: price,
      hatsubai_date: '',
      seisan_end_date: '',
      zaiku: '',
      availability: 'stock',
      koukyou_kataban1: '',
      koukyou_kataban2: '',
      t_akarusa: '250形',
      kigusize: 'φ100',
      umekomi_ana: 'φ100',
      t_toritsuke: '天井埋込',
      boushitsu_bouu: '',
      t_kinou: '調光',
      dannetsusekou: '',
      y_toukyu: '',
      y_toritsuke: '',
      y_hyoujimen: '',
      y_kinou: '',
      parsed_hints: {
        luminous_flux_lm: 2000,
        color_temperature_k: 3000,
        power_consumption_w: 20,
        voltage_min_v: 100,
        voltage_max_v: 242,
        cri_ra: 83,
      },
      ...overrides,
    } as Candidate['record'],
  }
}

describe('候補同士の違い', () => {
  it('候補1件では差分を出さない', () => {
    expect(computeCandidateDiff([candidate({})]).comparable).toBe(false)
  })

  it('主要仕様の違いだけを挙げる', () => {
    const diff = computeCandidateDiff([
      candidate({ id: 'S1' }),
      candidate({ id: 'S2', parsed_hints: { color_temperature_k: 5000, luminous_flux_lm: 2000 } }),
    ])
    expect(diff.differingLabels).toContain('色温度')
    expect(diff.differingLabels).not.toContain('明るさ区分')
  })

  it('DBレコードIDやスコアの違いは仕様の違いにしない', () => {
    const first = candidate({ id: 'S1' })
    const second = candidate({ id: 'S2' })
    second.score = 55
    second.rank = 2
    expect(computeCandidateDiff([first, second]).differingLabels).toEqual([])
  })

  it('単位や空白の表記違いだけでは差分にしない', () => {
    const diff = computeCandidateDiff([candidate({ kigusize: 'φ100' }), candidate({ kigusize: 'φ 100' })])
    expect(diff.differingLabels).not.toContain('器具寸法')
  })

  it('DB情報なしは不一致にせず、欠損として分けて示す', () => {
    const diff = computeCandidateDiff([candidate({ boushitsu_bouu: '防雨型' }), candidate({ boushitsu_bouu: '' })])
    const waterproof = diff.fields.find((value) => value.key === 'waterproof')!
    expect(waterproof.differs).toBe(false)
    expect(waterproof.missingCount).toBe(1)
    expect(diff.partialLabels).toContain('防湿・防雨')
  })

  it('価格の違いは仕様の違いと分けて持つ', () => {
    const diff = computeCandidateDiff([candidate({}, 1000), candidate({}, 2000)])
    expect(diff.differingLabels).toEqual([])
    expect(diff.priceDiffers).toBe(true)
  })
})

describe('機械の判定理由の日本語化', () => {
  it('同一品番が複数', () => {
    expect(machineSummary('exact_multiple', 'exact_identifier', 4).headline).toBe(
      '同じ品番の商品が複数あります。仕様の違いを確認してください。',
    )
  })

  it('部分一致', () => {
    expect(machineSummary('fuzzy_candidates', 'partial_identifier', 20).headline).toBe(
      '品番の一部が一致する候補です。原図と照合してください。',
    )
  })

  it('仕様矛盾・情報不足・候補なし', () => {
    expect(machineSummary('conflict', 'exact_identifier', 1).headline).toContain('図面の仕様と異なる点があります')
    expect(machineSummary('insufficient_input', 'insufficient_input', 0).headline).toBe('検索に使える情報が不足しています。')
    expect(machineSummary('not_found', 'identifier_not_found', 0).headline).toBe(
      '現在の検索条件に該当する商品が見つかりませんでした。',
    )
  })
})
