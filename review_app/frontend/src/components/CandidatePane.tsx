import { useEffect, useMemo, useState } from 'react'
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
const DIFF_BG = '#e3efff'
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

function matchReasonText(candidate: Candidate): string {
  if (candidate.matched_fields.length === 0) return '一致項目なし（候補として提示しているだけ）'
  const labels = candidate.matched_fields.map((matched) => {
    const base = MATCH_FIELD_LABELS[matched.field] ?? matched.field
    return matched.field === 'identifier' && matched.match_type ? `${base}（${matched.match_type}）` : base
  })
  const head = labels.slice(0, 4)
  return head.join('・') + (labels.length > head.length ? ` ほか${labels.length - head.length}項目` : '')
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
            複数器具の混在の可能性があるため分割の確認が必要です。この対象は確認済みにできません（保留で先に進めます）。
          </Alert>
        )}
        {draft.relationStatus === 'unresolved' && entries.length > 1 && (
          <Alert severity="warning" sx={{ mb: 1, py: 0 }}>
            品番同士の関係（構成品か別器具か）が未確定です。読み取り結果の「詳細」で関係を選ぶまで確認済みにできません。
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
            <Chip label={`比較対象 ${compareIds.length}件`} color="info" />
            <Button disabled={compareIds.length < 2} onClick={() => setCompareOpen(true)}>
              主要仕様を横並び比較
            </Button>
            <Button onClick={() => setCompareIds([])}>選択解除</Button>
          </Stack>
        )}

        <Stack spacing={0.75} sx={{ mb: 1 }}>
          {candidates.map((candidate: Candidate) => {
            const adopted = decision?.decision === 'adopted' && decision.record_id === candidate.record.id
            const selected = selectedRecordId === candidate.record.id
            const open = expanded === candidate.record.id
            const specs = candidateSpecValues(candidate)
            const lifecycle = candidate.lifecycle_warning
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
                <CardContent sx={{ py: 1, '&:last-child': { pb: 1 } }}>
                  <Stack direction="row" spacing={0.5} alignItems="baseline" flexWrap="wrap" useFlexGap>
                    <Radio
                      checked={selected}
                      onChange={() => setSelectedRecordId(candidate.record.id)}
                      onClick={(event) => event.stopPropagation()}
                      sx={{ p: 0.25 }}
                    />
                    <Typography sx={{ fontWeight: 700, fontSize: 15 }}>
                      {candidate.record.full_code || candidate.record.hinban}
                    </Typography>
                    <Chip
                      label={AVAILABILITY_LABELS[candidate.record.availability] ?? candidate.record.availability}
                      color={lifecycle ? 'warning' : 'default'}
                      variant={lifecycle ? 'filled' : 'outlined'}
                    />
                    {adopted && <Chip label="採用中" color="success" />}
                    <Box sx={{ flex: 1 }} />
                    <Chip label={`順位 ${candidate.rank}`} variant="outlined" />
                  </Stack>

                  <Typography variant="caption" component="div" sx={{ mt: 0.25, color: 'text.primary' }}>
                    {candidate.record.key || candidate.record.view_key || '商品名の登録なし'}
                  </Typography>

                  <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
                    {specs.map((spec) => {
                      if (spec.key === 'availability') return null // 販売状態は上のチップで出している
                      const differs = differingKeys.has(spec.key)
                      if (!differs && spec.value === null) return null
                      return (
                        <Box
                          key={spec.key}
                          sx={{
                            px: 0.75,
                            py: 0.25,
                            borderRadius: 0.5,
                            border: 1,
                            borderColor: differs ? '#9fc3ea' : 'divider',
                            bgcolor: differs ? DIFF_BG : 'transparent',
                          }}
                        >
                          <Typography variant="caption" color="text.secondary">
                            {spec.label}{' '}
                          </Typography>
                          <Typography
                            variant="caption"
                            sx={{ fontWeight: differs ? 700 : 400, color: spec.value === null ? 'text.disabled' : 'text.primary' }}
                          >
                            {spec.value ?? 'DB情報なし'}
                          </Typography>
                        </Box>
                      )
                    })}
                  </Stack>

                  <Typography variant="caption" component="div" color="success.dark" sx={{ mt: 0.5 }}>
                    一致理由: {matchReasonText(candidate)}
                  </Typography>

                  <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
                    {candidate.conflicts.length > 0 && (
                      <Chip label={`検索条件との相違 ${candidate.conflicts.length}項目`} color="warning" />
                    )}
                    {candidate.db_internal_warnings.map((warning) => (
                      <Chip key={warning} label="DB内部の矛盾あり" color="error" />
                    ))}
                    {candidate.record.price_zeinuki != null && (
                      <Chip label={`税抜 ${candidate.record.price_zeinuki}`} variant="outlined" />
                    )}
                  </Stack>

                  <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.5 }}>
                    <Button
                      onClick={(event) => {
                        event.stopPropagation()
                        setExpanded(open ? null : candidate.record.id)
                      }}
                    >
                      {open ? '詳細を閉じる' : '詳細を見る'}
                    </Button>
                    <FormControlLabel
                      onClick={(event) => event.stopPropagation()}
                      control={
                        <Checkbox
                          checked={compareIds.includes(candidate.record.id)}
                          onChange={(event) =>
                            setCompareIds((current) => {
                              if (event.target.checked) return current.length >= 3 ? current : [...current, candidate.record.id]
                              return current.filter((value) => value !== candidate.record.id)
                            })
                          }
                        />
                      }
                      label={<Typography variant="caption">比較</Typography>}
                    />
                  </Stack>

                  <Collapse in={open} unmountOnExit>
                    <Divider sx={{ my: 0.5 }} />
                    <Typography variant="caption" component="div" sx={{ fontWeight: 700 }}>
                      候補になった理由・一致項目
                    </Typography>
                    {candidate.matched_fields.map((matched, index) => (
                      <Typography key={index} variant="caption" component="div" color="success.dark">
                        ・{MATCH_FIELD_LABELS[matched.field] ?? matched.field}
                        {matched.match_type ? `（${matched.match_type}）` : ''}
                        {matched.input !== undefined ? ` 条件: ${JSON.stringify(matched.input)}` : ''}
                        {matched.db !== undefined ? ` / DB: ${JSON.stringify(matched.db)}` : ''}
                      </Typography>
                    ))}
                    <Typography variant="caption" component="div" sx={{ fontWeight: 700, mt: 0.5 }}>
                      検索条件との相違点
                    </Typography>
                    {candidate.conflicts.length === 0 ? (
                      <Typography variant="caption" component="div" color="text.secondary">
                        ・相違として検出された項目はありません（未読取の項目は比較していません）。
                      </Typography>
                    ) : (
                      candidate.conflicts.map((conflict, index) => (
                        <Typography key={index} variant="caption" component="div" color="warning.dark">
                          ・{MATCH_FIELD_LABELS[conflict.field] ?? conflict.field}（
                          {correctedSpecKeys.has(conflict.field) ? '担当者の修正値との差' : '原図の読み取り値との差'}） 条件:{' '}
                          {JSON.stringify(conflict.input)} / DB: {JSON.stringify(conflict.db)}
                        </Typography>
                      ))
                    )}
                    <Typography variant="caption" component="div" sx={{ mt: 0.5 }}>
                      DBレコードID {candidate.record.id} / 順位付けスコア {candidate.score}
                    </Typography>
                    <Typography variant="caption" component="div">
                      分類 {candidate.record.kigugroup || candidate.record.t_kigugroup || '—'} / 発売 {candidate.record.hatsubai_date || '—'} / 生産終了{' '}
                      {candidate.record.seisan_end_date || '—'} / 在庫区分 {candidate.record.zaiku || '—'}
                    </Typography>
                    <Typography variant="caption" component="div">
                      公共施設型番: {candidate.record.koukyou_kataban1 || '—'} {candidate.record.koukyou_kataban2 || ''} / 断熱施工:{' '}
                      {candidate.record.dannetsusekou || '—'}
                    </Typography>
                  </Collapse>
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
            保留
          </Button>
          <Box sx={{ flex: 1 }} />
          <Button disabled={saving} onClick={() => onSave(false)}>
            保存のみ
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
