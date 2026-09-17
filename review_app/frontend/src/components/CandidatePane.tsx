import { Fragment, useEffect, useMemo, useState } from 'react'
import Accordion from '@mui/material/Accordion'
import AccordionDetails from '@mui/material/AccordionDetails'
import AccordionSummary from '@mui/material/AccordionSummary'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Checkbox from '@mui/material/Checkbox'
import Chip from '@mui/material/Chip'
import Collapse from '@mui/material/Collapse'
import Divider from '@mui/material/Divider'
import FormControlLabel from '@mui/material/FormControlLabel'
import MenuItem from '@mui/material/MenuItem'
import Radio from '@mui/material/Radio'
import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import CompareDialog from './CompareDialog'
import { candidateSpecValues, computeCandidateDiff, diffKeySet } from '../lib/candidateDiff'
import { machineSummary, routeText } from '../lib/machineReason'
import { AVAILABILITY_LABELS, DECISION_LABELS, MACHINE_STATUS_LABELS, RELATION_LABELS, STATUS_LABELS } from '../labels'
import type { Draft } from '../views/ReviewView'
import type {
  Candidate,
  EntryDecisionName,
  FilterOptions,
  ItemDetail,
  ItemStatus,
  QuantityStatus,
  SearchFilters,
  SearchResult,
} from '../types'
import { api } from '../api'

export const CANDIDATE_SURFACE = '#f5f3f0'
const HEADER_BAND = '#e5e0d8'
const SELECTED_BG = '#eaf2fb'

/** 機械が返す一致項目のキーを、担当者向けの日本語にする。 */
const MATCH_FIELD_LABELS: Record<string, string> = {
  identifier: '品番一致',
  identifier_similarity: '品番が近い',
  category: 'カテゴリ',
  style: '形状',
  key_hint: '商品名の手がかり',
  brightness: '明るさ区分',
  fixture_size: '器具寸法',
  cutout_size: '埋込穴',
  mounting: '取付方式',
  waterproof: '防湿・防雨',
  dimming: '調光',
  luminous_flux_lm: '光束',
  color_temperature_k: '色温度',
  power_consumption_w: '消費電力',
  cri_ra: '演色性',
  y_toukyu: '等級',
  y_toritsuke: '取付（用途）',
  y_hyoujimen: '表示面',
  y_kinou: '機能',
}

/** 販売状況のまとめ方。常備在庫品は実データで3件しかないため販売中にまとめる。 */
const AVAILABILITY_GROUPS = [
  { key: 'on_sale', label: '販売中（工場在庫・常備在庫・受注）', values: ['factory_stock', 'stock', 'made_to_order'] },
  { key: 'planned_discontinued', label: '生産終了予定', values: ['planned_discontinued'] },
  { key: 'discontinued', label: '生産終了', values: ['discontinued'] },
  { key: 'unknown', label: '未登録', values: ['unknown'] },
]
const ALL_AVAILABILITY = AVAILABILITY_GROUPS.flatMap((group) => group.values)

function numberOrNull(text: string): number | null {
  const trimmed = text.trim()
  if (trimmed === '') return null
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : null
}

/** 通常表示に出す仕様。候補を選ぶ判断に効くものだけに絞る。 */
const CARD_SPEC_KEYS = ['akarusa', 'luminous_flux', 'size', 'mounting']

/** 品番がどう一致したか。内部の match_type は見せず、日本語だけにする。 */
const IDENTIFIER_MATCH_LABELS: Record<string, string> = {
  'hinban+kidou': '完全一致',
  full_code: '完全一致',
  hinban: '品番本体が一致',
  public_model_code: '公共施設型番が一致',
  relaxed_identifier: '記号の違いを除いて一致',
  partial_identifier: '一部が一致',
}

function identifierMatchText(candidate: Candidate): string | null {
  const matched = candidate.matched_fields.find((value) => value.field === 'identifier')
  if (!matched) return null
  const kind = (matched.match_type ?? '').split(':')[0]
  return IDENTIFIER_MATCH_LABELS[kind] ?? null
}

/** 品番以外で一致した項目の名前。 */
function matchedSpecLabels(candidate: Candidate): string[] {
  return candidate.matched_fields
    .filter((matched) => matched.field !== 'identifier' && matched.field !== 'identifier_similarity')
    .map((matched) => MATCH_FIELD_LABELS[matched.field] ?? matched.field)
}

function conflictLabels(candidate: Candidate): string[] {
  return candidate.conflicts.map((conflict) => MATCH_FIELD_LABELS[conflict.field] ?? conflict.field)
}

/** 税抜価格。0はDBの未登録値なので0円として見せない。 */
function priceText(value: number | null): string | null {
  if (value == null || value <= 0) return null
  return `¥${value.toLocaleString('ja-JP')}`
}

function plainValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (Array.isArray(value)) return value.map((entry) => plainValue(entry)).join('・')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

interface Props {
  detail: ItemDetail
  draft: Draft
  searches: Record<string, SearchResult>
  searching: string | null
  saving: boolean
  filters: SearchFilters
  onFiltersChange: (next: SearchFilters) => void
  onChange: (updater: (draft: Draft) => Draft) => void
  onResearchEntry: (suffix: string, topK?: number) => void
  onSave: (moveNext: boolean, override?: Partial<Draft>) => void
}

export default function CandidatePane({
  detail,
  draft,
  searches,
  searching,
  saving,
  filters,
  onFiltersChange,
  onChange,
  onResearchEntry,
  onSave,
}: Props) {
  const [entryIndex, setEntryIndex] = useState(0)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [compareIds, setCompareIds] = useState<string[]>([])
  const [compareOpen, setCompareOpen] = useState(false)
  const [showSearchDetail, setShowSearchDetail] = useState(false)
  const [selectedRecordId, setSelectedRecordId] = useState<string | null>(null)
  const [filterOptions, setFilterOptions] = useState<FilterOptions | null>(null)

  useEffect(() => {
    // 分類の選択肢は商品DBの実データから作る。読み込めなくても絞り込み以外は動く。
    let cancelled = false
    api
      .filterOptions()
      .then((value) => {
        if (!cancelled) setFilterOptions(value)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  const entries = detail.entries
  const entry = entries[Math.min(entryIndex, entries.length - 1)]
  const search = entry ? searches[entry.suffix] ?? entry.search : null
  const decision = entry ? draft.decisions[entry.suffix] : undefined
  const candidates = useMemo(() => search?.candidates ?? [], [search])
  const entrySuffix = entry?.suffix

  useEffect(() => {
    setEntryIndex(0)
    setExpanded(null)
    setCompareIds([])
    setShowSearchDetail(false)
  }, [detail.id])

  useEffect(() => {
    // 品番タブを切り替えたら、すでに採用済みの商品を選択状態の初期値にする。
    const current = entrySuffix ? draft.decisions[entrySuffix] : undefined
    setSelectedRecordId(current?.decision === 'adopted' ? current.record_id ?? null : null)
    setExpanded(null)
    // 採用状態が外から変わったときだけ初期化したいので、draft全体は依存に入れない。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail.id, entrySuffix])

  // 比較するのは同じ品番タブ（同じ構成品）の候補だけ。
  const diff = useMemo(() => computeCandidateDiff(candidates), [candidates])
  const differingKeys = useMemo(() => diffKeySet(diff), [diff])
  const correctedSpecKeys = useMemo(
    () => new Set(Object.keys(draft.corrections.specifications ?? {})),
    [draft.corrections.specifications],
  )

  const compareCandidates = useMemo(
    () => candidates.filter((candidate) => compareIds.includes(candidate.record.id)),
    [candidates, compareIds],
  )

  const decisionHistory = useMemo(
    () =>
      detail.history
        .filter((event) => event.action === 'decision_changed')
        .map((event) => {
          let parsed: { before?: any; after?: any } = {}
          try {
            parsed = event.detail ? JSON.parse(event.detail) : {}
          } catch {
            parsed = {}
          }
          return { ...event, before: parsed.before, after: parsed.after }
        }),
    [detail.history],
  )

  const setDecision = (
    suffix: string,
    value: { decision: EntryDecisionName; record_id?: string | null; search_id?: string | null; note?: string | null },
  ) => {
    // 担当者が今の条件で判断した操作なので、判断時の入力の版を更新してよい。
    // どの条件で判断したかを一緒に持たせ、後から条件が変わった場合は再判断として扱わせない。
    onChange((current) => ({
      ...current,
      decisions: {
        ...current.decisions,
        [suffix]: { ...value, reaffirm: true, reaffirm_basis: JSON.parse(JSON.stringify(current.corrections)) },
      },
    }))
  }

  // 未指定は「全部対象」。バックエンドも全選択は絞り込みなしとして扱う。
  const availabilitySelection = filters.availability ?? ALL_AVAILABILITY
  const setFilter = <K extends keyof SearchFilters>(key: K, value: SearchFilters[K]) =>
    onFiltersChange({ ...filters, [key]: value })
  const toggleAvailabilityGroup = (values: string[], checked: boolean) => {
    const next = checked
      ? [...new Set([...availabilitySelection, ...values])]
      : availabilitySelection.filter((value) => !values.includes(value))
    setFilter('availability', next)
  }
  const activeFilterLabels: string[] = []
  if (filters.availability && filters.availability.length < ALL_AVAILABILITY.length) {
    activeFilterLabels.push(
      '販売状況: ' +
        (AVAILABILITY_GROUPS.filter((group) => group.values.every((value) => filters.availability?.includes(value)))
          .map((group) => group.label.split('（')[0])
          .join('・') || '一部'),
    )
  }
  if (filters.price_min != null || filters.price_max != null) {
    activeFilterLabels.push(`価格: ${filters.price_min ?? ''}～${filters.price_max ?? ''}円`)
  }
  if (filters.release_year_min != null || filters.release_year_max != null) {
    activeFilterLabels.push(`発売: ${filters.release_year_min ?? ''}～${filters.release_year_max ?? ''}年`)
  }
  if (filters.category) activeFilterLabels.push(`分類: ${filters.category}`)

  if (!entry) return null
  const summary = search ? machineSummary(search.machine_decision.status, search.search.route, search.search.candidate_count) : null
  const selectedCandidate = candidates.find((candidate) => candidate.record.id === selectedRecordId) ?? null

  const codeEntryCount = entries.filter((value) => value.kind === 'code').length
  // バックエンドが「確認済み」を拒否する条件（service.save_review）と同じ判定をここで行う。
  const relationBlocksConfirm =
    draft.relationStatus === 'multiple_fixtures' || (draft.relationStatus === 'unresolved' && codeEntryCount > 1)

  const buildDecisions = (value: {
    decision: EntryDecisionName
    record_id?: string | null
    search_id?: string | null
    note?: string | null
  }): Draft['decisions'] => ({
    ...draft.decisions,
    [entry.suffix]: { ...value, reaffirm: true, reaffirm_basis: JSON.parse(JSON.stringify(draft.corrections)) },
  })

  const statusAfter = (decisions: Draft['decisions'], forced?: ItemStatus): ItemStatus => {
    if (forced) return forced
    const allDecided = entries.every((value) => (decisions[value.suffix]?.decision ?? 'undecided') !== 'undecided')
    return !relationBlocksConfirm && allDecided ? 'confirmed' : draft.status
  }

  /**
   * 判断を確定して保存する。
   * setStateの反映を待たずに保存できるよう、保存に使う内容はoverrideで同期的に渡す。
   */
  const commit = (decisions: Draft['decisions'], status: ItemStatus, moveNext: boolean) => {
    onChange((current) => ({ ...current, decisions, status }))
    onSave(moveNext, { decisions, status })
  }

  const adoptAndNext = () => {
    if (!selectedCandidate || !search) return
    const decisions = buildDecisions({
      decision: 'adopted',
      record_id: selectedCandidate.record.id,
      search_id: search.id,
      note: decision?.note ?? null,
    })
    commit(decisions, statusAfter(decisions), true)
  }

  const markNoCandidate = () => {
    const decisions = buildDecisions({ decision: 'no_candidate', note: decision?.note ?? null })
    commit(decisions, statusAfter(decisions), true)
  }

  const holdAndNext = () => {
    commit(draft.decisions, 'on_hold', true)
  }

  return (
    <Box sx={{ height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column', bgcolor: CANDIDATE_SURFACE }}>
      <Stack
        direction="row"
        spacing={1}
        alignItems="center"
        flexWrap="wrap"
        useFlexGap
        sx={{ px: 1, py: 0.75, bgcolor: HEADER_BAND, borderBottom: 1, borderColor: '#cfc7ba' }}
      >
        <Typography variant="subtitle2" sx={{ fontWeight: 800, color: '#4a3d28' }}>
          商品候補
        </Typography>
        <Chip label={STATUS_LABELS[draft.status]} sx={{ bgcolor: 'common.white' }} />
        {entries.length > 1 && (
          <Chip
            label={RELATION_LABELS[draft.relationStatus]}
            color={['multiple_fixtures', 'unresolved'].includes(draft.relationStatus) ? 'warning' : 'default'}
            variant="outlined"
            sx={{ bgcolor: 'common.white' }}
          />
        )}
      </Stack>

      <Box sx={{ flex: 1, minHeight: 0, overflow: 'auto', p: 1 }}>
        {entries.length > 1 && (
          <Tabs
            value={Math.min(entryIndex, entries.length - 1)}
            onChange={(_, value) => setEntryIndex(value)}
            variant="scrollable"
            sx={{ minHeight: 34, mb: 0.5 }}
          >
            {entries.map((value) => (
              <Tab
                key={value.suffix}
                sx={{ minHeight: 34, textTransform: 'none' }}
                label={`${value.label}: ${value.code ?? '仕様検索'}（${DECISION_LABELS[draft.decisions[value.suffix]?.decision ?? 'undecided']}）`}
              />
            ))}
          </Tabs>
        )}

        {draft.relationStatus === 'multiple_fixtures' && (
          <Alert severity="warning" sx={{ mb: 1, py: 0 }}>
            1つの枠に複数の器具が入っている可能性があります。分けて確認してください（このままでは確認済みにできません。「あとで確認」で先に進めます）。
          </Alert>
        )}
        {draft.relationStatus === 'unresolved' && entries.length > 1 && (
          <Alert severity="warning" sx={{ mb: 1, py: 0 }}>
            複数の品番が読み取られています。同じ器具の部品か、別々の器具かを中央の「詳細」で選んでください（選ぶまで確認済みにできません）。
          </Alert>
        )}

        {/* 商品DB側の絞り込み。未入力の条件はバックエンドで無視される。 */}
        <Accordion disableGutters sx={{ bgcolor: 'common.white', border: 1, borderColor: '#d8d1c6', mb: 0.75 }}>
          <AccordionSummary>
            <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap" useFlexGap sx={{ width: '100%' }}>
              <Typography variant="caption" sx={{ fontWeight: 700 }}>
                絞り込み
              </Typography>
              {activeFilterLabels.length === 0 ? (
                <Typography variant="caption" color="text.secondary">
                  なし
                </Typography>
              ) : (
                activeFilterLabels.map((label) => <Chip key={label} label={label} color="info" variant="outlined" />)
              )}
            </Stack>
          </AccordionSummary>
          <AccordionDetails>
            <Typography variant="caption" sx={{ fontWeight: 700 }} component="div">
              販売状況
            </Typography>
            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
              {AVAILABILITY_GROUPS.map((group) => (
                <FormControlLabel
                  key={group.key}
                  control={
                    <Checkbox
                      size="small"
                      checked={group.values.every((value) => availabilitySelection.includes(value))}
                      indeterminate={
                        group.values.some((value) => availabilitySelection.includes(value)) &&
                        !group.values.every((value) => availabilitySelection.includes(value))
                      }
                      onChange={(event) => toggleAvailabilityGroup(group.values, event.target.checked)}
                    />
                  }
                  label={<Typography variant="caption">{group.label}</Typography>}
                />
              ))}
            </Stack>

            <Typography variant="caption" sx={{ fontWeight: 700 }} component="div">
              税抜価格（円）
            </Typography>
            <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mb: 0.5 }} flexWrap="wrap" useFlexGap>
              <TextField
                label="最小"
                type="number"
                value={filters.price_min ?? ''}
                onChange={(event) => setFilter('price_min', numberOrNull(event.target.value))}
                sx={{ width: 120, bgcolor: 'common.white' }}
              />
              <Typography variant="caption">～</Typography>
              <TextField
                label="最大"
                type="number"
                value={filters.price_max ?? ''}
                onChange={(event) => setFilter('price_max', numberOrNull(event.target.value))}
                sx={{ width: 120, bgcolor: 'common.white' }}
              />
              <FormControlLabel
                control={
                  <Checkbox
                    size="small"
                    checked={filters.price_include_unknown ?? false}
                    onChange={(event) => setFilter('price_include_unknown', event.target.checked)}
                  />
                }
                label={<Typography variant="caption">価格未登録も含める</Typography>}
              />
            </Stack>

            <Typography variant="caption" sx={{ fontWeight: 700 }} component="div">
              発売年
            </Typography>
            <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mb: 0.5 }} flexWrap="wrap" useFlexGap>
              <TextField
                label="から"
                type="number"
                value={filters.release_year_min ?? ''}
                onChange={(event) => setFilter('release_year_min', numberOrNull(event.target.value))}
                sx={{ width: 110, bgcolor: 'common.white' }}
              />
              <Typography variant="caption">～</Typography>
              <TextField
                label="まで"
                type="number"
                value={filters.release_year_max ?? ''}
                onChange={(event) => setFilter('release_year_max', numberOrNull(event.target.value))}
                sx={{ width: 110, bgcolor: 'common.white' }}
              />
              <FormControlLabel
                control={
                  <Checkbox
                    size="small"
                    checked={filters.release_include_unknown ?? false}
                    onChange={(event) => setFilter('release_include_unknown', event.target.checked)}
                  />
                }
                label={<Typography variant="caption">発売年未登録も含める</Typography>}
              />
            </Stack>

            <TextField
              select
              label="商品カテゴリ"
              value={filters.category ?? ''}
              onChange={(event) => setFilter('category', event.target.value || null)}
              sx={{ minWidth: 240, bgcolor: 'common.white' }}
            >
              <MenuItem value="">指定しない</MenuItem>
              {(filterOptions?.categories ?? []).map((option) => (
                <MenuItem key={option.value || '(none)'} value={option.value}>
                  {option.label}（{option.count}件）
                </MenuItem>
              ))}
            </TextField>

            <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 1 }}>
              <Button variant="contained" disabled={searching !== null} onClick={() => onResearchEntry(entry.suffix)}>
                この条件で再検索
              </Button>
              <Button disabled={searching !== null} onClick={() => onFiltersChange({})}>
                絞り込みを解除
              </Button>
            </Stack>
            <Typography variant="caption" color="text.secondary" component="div" sx={{ mt: 0.5 }}>
              未入力の条件では絞り込みません。価格0円・発売年1900年はDBの未登録値として扱い、範囲指定では除外します。
              絞り込みは表示する候補を減らすだけで、判断した条件（再確認の判定）には含めません。
            </Typography>
          </AccordionDetails>
        </Accordion>

        {!search ? (
          <Alert severity="info" sx={{ mb: 1 }}>
            この品番はまだ検索していません。
            <Button onClick={() => onResearchEntry(entry.suffix)} disabled={searching !== null}>
              検索する
            </Button>
          </Alert>
        ) : (
          <>
            {/* 候補件数と差分だけを1行に出す。説明文は「検索の詳細」を開いたときだけ。 */}
            <Stack
              direction="row"
              spacing={0.5}
              alignItems="center"
              flexWrap="wrap"
              useFlexGap
              sx={{ px: 0.75, py: 0.25, mb: 0.75, bgcolor: 'common.white', border: 1, borderColor: '#d8d1c6', borderRadius: 1 }}
            >
              <Typography variant="caption" sx={{ fontWeight: 700 }}>
                {search.search.candidate_count === 0 ? '候補なし' : `候補${search.search.returned_count}件`}
              </Typography>
              {search.search.candidate_count > search.search.returned_count && (
                <Typography variant="caption" color="text.secondary">
                  / 該当{search.search.candidate_count}件
                </Typography>
              )}
              {diff.comparable && (
                <Typography variant="caption" color="text.secondary">
                  ｜ 差分：{diff.differingLabels.length > 0 ? diff.differingLabels.join('・') : 'なし'}
                </Typography>
              )}
              {(search.search.filtered_out_count ?? 0) > 0 && (
                <Chip label={`絞り込みで除外 ${search.search.filtered_out_count}件`} color="info" variant="outlined" />
              )}
              {search.search.candidate_pool_truncated && <Chip label="打ち切り" color="warning" variant="outlined" />}
              {entry.decision_stale && <Chip label="判断時と条件が違う" color="warning" />}
              <Box sx={{ flex: 1 }} />
              {search.search.candidate_pool_truncated && (
                <Button disabled={searching !== null} onClick={() => onResearchEntry(entry.suffix, 60)}>
                  さらに取得
                </Button>
              )}
              <Button disabled={searching !== null} onClick={() => onResearchEntry(entry.suffix)}>
                この品番だけ再検索
              </Button>
              <Button color="inherit" onClick={() => setShowSearchDetail((value) => !value)}>
                検索の詳細
              </Button>
            </Stack>

            <Collapse in={showSearchDetail} unmountOnExit>
              <Box sx={{ bgcolor: 'common.white', border: 1, borderColor: '#d8d1c6', borderRadius: 1, p: 1, mb: 1 }}>
                <Typography sx={{ fontWeight: 700, fontSize: 13 }}>{summary?.headline}</Typography>
                {summary?.detail && (
                  <Typography variant="caption" color="text.secondary" component="div">
                    {summary.detail}
                  </Typography>
                )}
                {diff.comparable && (
                  <Typography variant="caption" color="text.secondary" component="div" sx={{ mt: 0.5 }}>
                    {diff.differingLabels.length === 0 &&
                      '表示している主要仕様では差を確認できません（同一商品と断定はできません）。'}
                    表示中の{candidates.length}件での比較です（該当 {search.search.candidate_count}件すべての比較ではありません）。
                    {diff.priceDiffers && ' 税抜価格にも差があります（仕様の差とは別です）。'}
                    {diff.partialLabels.length > 0 && ` 一部の候補でDB情報なし：${diff.partialLabels.join('・')}`}
                  </Typography>
                )}
                {search.search.candidate_pool_truncated && (
                  <Typography variant="caption" color="text.secondary" component="div">
                    候補が多いため一部だけを表示しています。条件を追加して再検索するか、「さらに取得」で上位60件まで取得できます。
                  </Typography>
                )}
                <Box sx={{ mt: 0.5, pl: 1, borderLeft: 2, borderColor: 'divider' }}>
                  <Typography variant="caption" component="div" color="text.secondary">
                    検索経路: {routeText(search.search.route)}（{search.search.route}） / 機械の判定: {MACHINE_STATUS_LABELS[search.machine_decision.status] ?? search.machine_decision.status}（{search.machine_decision.status}）
                  </Typography>
                  <Typography variant="caption" component="div" color="text.secondary">
                    この検索に使った識別子: 品番 {String(search.match_input?.identity?.product_code_raw ?? '—')} / hinban {String(search.match_input?.identity?.hinban ?? '—')} / kidou {String(search.match_input?.identity?.kidou ?? '—')}
                    {entry.effective_identifier?.notes?.length ? `（${entry.effective_identifier.notes.join(', ')}）` : ''}
                  </Typography>
                  <Typography variant="caption" component="div" color="text.secondary">
                    機械が選んだID: {search.machine_decision.selected_id ?? '—'}（自動確定ではありません） / 検索ID: {search.id} / 条件の版: {search.input_fingerprint.slice(0, 12)}
                  </Typography>
                  <Typography variant="caption" component="div" color="text.secondary">
                    判定理由(原文): {search.machine_decision.reason}
                  </Typography>
                </Box>
              </Box>
            </Collapse>

            {candidates.length === 0 && (
              <Alert severity="warning" sx={{ mb: 1 }}>
                候補がありません。読み取り内容を修正して再検索するか、「該当なし」として記録できます。
              </Alert>
            )}
          </>
        )}

        {compareIds.length > 0 && (
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
            <Button variant="outlined" disabled={compareIds.length < 2} onClick={() => setCompareOpen(true)}>
              選択した候補を比較（{compareIds.length}件）
            </Button>
            <Button onClick={() => setCompareIds([])}>選択を解除</Button>
          </Stack>
        )}

        <Stack spacing={0.75} sx={{ mb: 1 }}>
          {candidates.map((candidate: Candidate) => {
            const adopted = decision?.decision === 'adopted' && decision.record_id === candidate.record.id
            const selected = selectedRecordId === candidate.record.id
            const open = expanded === candidate.record.id
            const record = candidate.record
            const lifecycle = candidate.lifecycle_warning
            // 値がある項目だけ出す。空欄は並べない。
            const cardSpecs = candidateSpecValues(candidate).filter(
              (spec) => CARD_SPEC_KEYS.includes(spec.key) && spec.value !== null,
            )
            const conflicts = conflictLabels(candidate)
            const price = priceText(record.price_zeinuki)
            const identifierText = identifierMatchText(candidate)
            const specMatches = matchedSpecLabels(candidate)
            const productInfo: [string, string][] = []
            // 発売日の1900-01-01はDBの未登録値なので出さない。
            if (record.hatsubai_date && !record.hatsubai_date.startsWith('1900')) {
              productInfo.push(['発売', record.hatsubai_date])
            }
            if (record.seisan_end_date) productInfo.push(['生産終了', record.seisan_end_date])
            productInfo.push(['販売状況', AVAILABILITY_LABELS[record.availability] ?? record.availability])
            if (record.koukyou_kataban1) {
              productInfo.push(['公共施設型番', [record.koukyou_kataban1, record.koukyou_kataban2].filter(Boolean).join(' ')])
            }
            if (record.dannetsusekou) productInfo.push(['断熱施工', record.dannetsusekou])
            return (
              <Card
                key={candidate.record.id}
                variant="outlined"
                onClick={() => setSelectedRecordId(candidate.record.id)}
                sx={{
                  cursor: 'pointer',
                  borderColor: selected ? 'primary.main' : adopted ? 'success.main' : '#d8d1c6',
                  borderWidth: selected || adopted ? 2 : 1,
                  bgcolor: selected ? SELECTED_BG : 'common.white',
                }}
              >
                <CardContent sx={{ py: 0.75, '&:last-child': { pb: 0.75 } }}>
                  <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap" useFlexGap>
                    <Radio
                      checked={selected}
                      onChange={() => setSelectedRecordId(record.id)}
                      onClick={(event) => event.stopPropagation()}
                      sx={{ p: 0.25 }}
                    />
                    <Typography sx={{ fontWeight: 700, fontSize: 15 }}>{record.full_code || record.hinban}</Typography>
                    <Box sx={{ flex: 1 }} />
                    <Chip
                      label={AVAILABILITY_LABELS[record.availability] ?? record.availability}
                      color={lifecycle ? 'warning' : 'default'}
                      variant={lifecycle ? 'filled' : 'outlined'}
                    />
                  </Stack>

                  <Box sx={{ ml: 3.5 }}>
                    <Typography sx={{ fontWeight: 700, fontSize: 14, color: price ? 'text.primary' : 'text.disabled' }}>
                      {price ?? '価格未登録'}
                    </Typography>

                    {cardSpecs.length > 0 && (
                      <Box
                        sx={{
                          mt: 0.25,
                          display: 'grid',
                          gridTemplateColumns: 'max-content 1fr',
                          columnGap: 1,
                          alignItems: 'baseline',
                        }}
                      >
                        {cardSpecs.map((spec) => (
                          <Fragment key={spec.key}>
                            <Typography variant="caption" color="text.secondary">
                              {spec.label}
                            </Typography>
                            {/* 候補同士で値が割れている項目だけ太字にして、比較の手がかりにする。 */}
                            <Typography variant="caption" sx={{ fontWeight: differingKeys.has(spec.key) ? 700 : 400 }}>
                              {spec.value}
                            </Typography>
                          </Fragment>
                        ))}
                      </Box>
                    )}

                    {conflicts.length > 0 && (
                      <Typography variant="caption" component="div" sx={{ mt: 0.25, color: 'warning.dark', fontWeight: 700 }}>
                        ⚠ 差分：{conflicts.join('・')}
                        {conflicts.length > 1 && `（${conflicts.length}項目）`}
                      </Typography>
                    )}
                    {candidate.db_internal_warnings.length > 0 && (
                      <Typography variant="caption" component="div" color="error.main">
                        DB内部の矛盾あり
                      </Typography>
                    )}

                    <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.25 }}>
                      <Button
                        onClick={(event) => {
                          event.stopPropagation()
                          setExpanded(open ? null : record.id)
                        }}
                      >
                        {open ? '詳細を閉じる' : '詳細を見る'}
                      </Button>
                      <Box sx={{ flex: 1 }} />
                      <FormControlLabel
                        onClick={(event) => event.stopPropagation()}
                        sx={{ mr: 0 }}
                        control={
                          <Checkbox
                            checked={compareIds.includes(record.id)}
                            onChange={(event) =>
                              setCompareIds((current) => {
                                if (event.target.checked) return current.length >= 3 ? current : [...current, record.id]
                                return current.filter((value) => value !== record.id)
                              })
                            }
                          />
                        }
                        label={<Typography variant="caption">比較に追加</Typography>}
                      />
                    </Stack>

                    <Collapse in={open} unmountOnExit>
                      <Divider sx={{ my: 0.5 }} />
                      <Typography variant="caption" component="div" sx={{ fontWeight: 700 }}>
                        候補になった理由
                      </Typography>
                      {identifierText && (
                        <Typography variant="caption" component="div">
                          品番：{identifierText}
                        </Typography>
                      )}
                      {specMatches.length > 0 && (
                        <Typography variant="caption" component="div">
                          一致した仕様：{specMatches.join('・')}
                        </Typography>
                      )}
                      {!identifierText && specMatches.length === 0 && (
                        <Typography variant="caption" component="div" color="text.secondary">
                          仕様条件で抽出した候補です。
                        </Typography>
                      )}

                      {candidate.conflicts.length > 0 && (
                        <>
                          <Typography variant="caption" component="div" sx={{ fontWeight: 700, mt: 0.5, color: 'warning.dark' }}>
                            検索条件との差分
                          </Typography>
                          {candidate.conflicts.map((conflict, index) => (
                            <Box key={index} sx={{ mb: 0.25 }}>
                              <Typography variant="caption" component="div" sx={{ fontWeight: 700 }}>
                                {MATCH_FIELD_LABELS[conflict.field] ?? conflict.field}
                              </Typography>
                              <Typography variant="caption" component="div" color="text.secondary">
                                {correctedSpecKeys.has(conflict.field) ? '修正値' : '原図'}：{plainValue(conflict.input)}
                              </Typography>
                              <Typography variant="caption" component="div" color="text.secondary">
                                DB：{plainValue(conflict.db)}
                              </Typography>
                            </Box>
                          ))}
                        </>
                      )}

                      <Typography variant="caption" component="div" sx={{ fontWeight: 700, mt: 0.5 }}>
                        商品情報
                      </Typography>
                      {productInfo.map(([label, value]) => (
                        <Typography key={label} variant="caption" component="div">
                          {label}：{value}
                        </Typography>
                      ))}
                    </Collapse>
                  </Box>
                </CardContent>
              </Card>
            )
          })}
        </Stack>

        {/* 通常の採用作業では使わない項目は、開いたときだけ見せる。 */}
        <Accordion disableGutters sx={{ bgcolor: 'common.white', border: 1, borderColor: '#d8d1c6' }}>
          <AccordionSummary>
            <Typography variant="caption" sx={{ fontWeight: 700 }}>
              詳細設定（確認状態・数量確認・判断・保留理由・履歴）
            </Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Stack direction="row" spacing={0.5} sx={{ mb: 1 }} flexWrap="wrap" useFlexGap>
              <TextField
                select
                label="この品番の判断"
                value={decision?.decision ?? 'undecided'}
                onChange={(event) => {
                  const value = event.target.value as EntryDecisionName
                  if (value === 'adopted') return
                  setDecision(entry.suffix, { decision: value })
                }}
                sx={{ minWidth: 190, bgcolor: 'common.white' }}
              >
                {(['undecided', 'no_candidate', 'excluded'] as EntryDecisionName[]).map((value) => (
                  <MenuItem key={value} value={value}>
                    {DECISION_LABELS[value]}
                  </MenuItem>
                ))}
                <MenuItem value="adopted" disabled>
                  採用（候補から選ぶ）
                </MenuItem>
              </TextField>
              <TextField
                select
                label="確認状態"
                value={draft.status}
                onChange={(event) => onChange((current) => ({ ...current, status: event.target.value as ItemStatus }))}
                sx={{ minWidth: 170, bgcolor: 'common.white' }}
              >
                {(['unconfirmed', 'on_hold', 'confirmed', 'needs_recheck'] as ItemStatus[]).map((value) => (
                  <MenuItem key={value} value={value}>
                    {STATUS_LABELS[value]}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="数量の確認"
                value={draft.quantityStatus}
                onChange={(event) => onChange((current) => ({ ...current, quantityStatus: event.target.value as QuantityStatus }))}
                sx={{ minWidth: 170, bgcolor: 'common.white' }}
              >
                <MenuItem value="unconfirmed">数量未確認</MenuItem>
                <MenuItem value="confirmed">数量確認済み</MenuItem>
                <MenuItem value="unreadable">数量読み取り困難</MenuItem>
              </TextField>
            </Stack>
            <Stack direction="row" spacing={0.5} sx={{ mb: 1 }}>
              <TextField
                label="保留理由"
                value={draft.holdReason}
                onChange={(event) => onChange((current) => ({ ...current, holdReason: event.target.value }))}
                sx={{ flex: 1, bgcolor: 'common.white' }}
              />
              <TextField
                label="備考"
                value={draft.memo}
                onChange={(event) => onChange((current) => ({ ...current, memo: event.target.value }))}
                sx={{ flex: 1, bgcolor: 'common.white' }}
              />
            </Stack>
            {decision && ['no_candidate', 'excluded'].includes(decision.decision) && (
              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                <Button
                  variant="outlined"
                  onClick={() => setDecision(entry.suffix, { decision: decision.decision, note: decision.note })}
                  disabled={decision.reaffirm === true}
                >
                  この条件で判断し直す
                </Button>
                <Typography variant="caption" color="text.secondary">
                  {decision.reaffirm
                    ? '保存時に、判断時の検索条件をこの内容へ更新します。'
                    : '保存しても判断時の検索条件は元のままです（条件が変わっていれば再確認が必要になります）。'}
                </Typography>
              </Stack>
            )}
            <Typography variant="caption" color="text.secondary" component="div">
              機械が1件に絞った場合でも、担当者が採用するまで確認済みにはなりません。
            </Typography>

            {decisionHistory.length > 0 && (
              <Box sx={{ mt: 1 }}>
                <Typography variant="caption" sx={{ fontWeight: 700 }} component="div">
                  判断の履歴
                </Typography>
                {decisionHistory.map((event) => (
                  <Typography key={event.id} variant="caption" component="div" color="text.secondary">
                    {event.created_at} / {event.entry_suffix ?? '—'}:{' '}
                    {DECISION_LABELS[event.before?.decision as EntryDecisionName] ?? event.before?.decision}
                    {event.before?.adopted_code ? `（${event.before.adopted_code} / ${event.before.adopted_record_id}）` : ''}
                    {' → '}
                    {DECISION_LABELS[event.after?.decision as EntryDecisionName] ?? event.after?.decision}
                    {event.after?.adopted_code ? `（${event.after.adopted_code} / ${event.after.adopted_record_id}）` : ''}
                  </Typography>
                ))}
              </Box>
            )}
          </AccordionDetails>
        </Accordion>

        <CompareDialog open={compareOpen} candidates={compareCandidates} detail={detail} onClose={() => setCompareOpen(false)} />
      </Box>

      {/* 採用の操作は常に見える位置に置く。 */}
      <Box sx={{ px: 1, py: 1, borderTop: 1, borderColor: '#cfc7ba', bgcolor: 'common.white' }}>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          <Button variant="contained" size="large" disabled={saving || !selectedCandidate} onClick={adoptAndNext}>
            この商品を採用して次へ
          </Button>
          <Button variant="outlined" disabled={saving} onClick={markNoCandidate}>
            該当なし
          </Button>
          <Button variant="outlined" color="warning" disabled={saving} onClick={holdAndNext}>
            あとで確認
          </Button>
          <Box sx={{ flex: 1 }} />
          {/* 通常はこの3つで進む。編集だけ残したいときのために保存も残す（控えめに）。 */}
          <Button size="small" color="inherit" disabled={saving} onClick={() => onSave(false)}>
            編集内容を保存
          </Button>
          {draft.dirty && <Chip label="未保存の編集あり" color="warning" />}
        </Stack>
        <Typography variant="caption" color="text.secondary" component="div" sx={{ mt: 0.5 }}>
          {selectedCandidate
            ? `選択中: ${selectedCandidate.record.full_code || selectedCandidate.record.hinban}`
            : '候補カードを選ぶと採用できます。'}
          {relationBlocksConfirm
            ? ' 分割・関係の確認が必要なため、採用しても確認済みにはしません（詳細設定で変更できます）。'
            : ' すべての品番の判断がそろうと確認済みとして保存します。'}
        </Typography>
      </Box>
    </Box>
  )
}
