import { useEffect, useMemo, useState } from 'react'
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
import type { Candidate, EntryDecisionName, ItemDetail, ItemStatus, QuantityStatus, SearchResult } from '../types'

export const CANDIDATE_SURFACE = '#f5f3f0'
const HEADER_BAND = '#e5e0d8'
const DIFF_BG = '#e3efff'

interface Props {
  detail: ItemDetail
  draft: Draft
  searches: Record<string, SearchResult>
  searching: string | null
  saving: boolean
  onChange: (updater: (draft: Draft) => Draft) => void
  onResearchEntry: (suffix: string, topK?: number) => void
  onSave: (moveNext: boolean, override?: Partial<Draft>) => void
}

export default function CandidatePane({ detail, draft, searches, searching, saving, onChange, onResearchEntry, onSave }: Props) {
  const [entryIndex, setEntryIndex] = useState(0)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [compareIds, setCompareIds] = useState<string[]>([])
  const [compareOpen, setCompareOpen] = useState(false)
  const [showSearchDetail, setShowSearchDetail] = useState(false)

  useEffect(() => {
    setEntryIndex(0)
    setExpanded(null)
    setCompareIds([])
    setShowSearchDetail(false)
  }, [detail.id])

  const entries = detail.entries
  const entry = entries[Math.min(entryIndex, entries.length - 1)]
  const search = entry ? searches[entry.suffix] ?? entry.search : null
  const decision = entry ? draft.decisions[entry.suffix] : undefined
  const candidates = useMemo(() => search?.candidates ?? [], [search])

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

  if (!entry) return null
  const summary = search ? machineSummary(search.machine_decision.status, search.search.route, search.search.candidate_count) : null

  return (
    <Box sx={{ bgcolor: CANDIDATE_SURFACE, minHeight: '100%' }}>
      <Stack
        direction="row"
        spacing={1}
        alignItems="center"
        flexWrap="wrap"
        useFlexGap
        sx={{ position: 'sticky', top: 0, zIndex: 2, px: 1, py: 0.75, bgcolor: HEADER_BAND, borderBottom: 1, borderColor: '#cfc7ba' }}
      >
        <Typography variant="subtitle2" sx={{ fontWeight: 800, color: '#4a3d28' }}>
          商品候補
        </Typography>
        <Chip label={`確認状態: ${STATUS_LABELS[draft.status]}`} size="small" sx={{ bgcolor: 'common.white' }} />
        {entries.length > 1 && (
          <Chip
            label={RELATION_LABELS[draft.relationStatus]}
            size="small"
            color={['multiple_fixtures', 'unresolved'].includes(draft.relationStatus) ? 'warning' : 'default'}
            variant="outlined"
            sx={{ bgcolor: 'common.white' }}
          />
        )}
      </Stack>

      <Box sx={{ p: 1 }}>
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
            品番同士の関係（構成品か別器具か）が未確定です。読み取り結果側で関係を選ぶまで確認済みにできません。
          </Alert>
        )}

        {!search ? (
          <Alert severity="info" sx={{ mb: 1 }}>
            この品番はまだ検索していません。
            <Button size="small" onClick={() => onResearchEntry(entry.suffix)} disabled={searching !== null}>
              検索する
            </Button>
          </Alert>
        ) : (
          <>
            <Box sx={{ bgcolor: 'common.white', border: 1, borderColor: '#d8d1c6', borderRadius: 1, p: 1, mb: 1 }}>
              <Typography sx={{ fontWeight: 700, fontSize: 13 }}>{summary?.headline}</Typography>
              {summary?.detail && (
                <Typography variant="caption" color="text.secondary" component="div">
                  {summary.detail}
                </Typography>
              )}
              <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
                <Chip
                  label={search.search.candidate_count === 0 ? '候補なし' : `候補 ${search.search.returned_count}件表示 / 該当 ${search.search.candidate_count}件`}
                  size="small"
                  variant="outlined"
                />
                {search.search.candidate_pool_truncated && <Chip label="打ち切りあり" size="small" color="warning" variant="outlined" />}
                {entry.decision_stale && <Chip label="判断時と条件が違う" size="small" color="warning" />}
                <Box sx={{ flex: 1 }} />
                <Button size="small" onClick={() => onResearchEntry(entry.suffix)} disabled={searching !== null}>
                  この品番だけ再検索
                </Button>
                <Button size="small" color="inherit" onClick={() => setShowSearchDetail((value) => !value)}>
                  検索の詳細
                </Button>
              </Stack>
              <Collapse in={showSearchDetail} unmountOnExit>
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
              </Collapse>
            </Box>

            {search.search.candidate_pool_truncated && (
              <Alert severity="info" sx={{ mb: 1, py: 0 }}>
                候補が多いため一部だけを表示しています。条件を追加して再検索するか、追加取得してください。
                <Button size="small" disabled={searching !== null} onClick={() => onResearchEntry(entry.suffix, 60)}>
                  さらに取得（上位60件）
                </Button>
              </Alert>
            )}

            {diff.comparable && (
              <Box sx={{ bgcolor: DIFF_BG, border: 1, borderColor: '#9fc3ea', borderRadius: 1, p: 1, mb: 1 }}>
                <Typography variant="caption" sx={{ fontWeight: 700 }} component="div">
                  {diff.differingLabels.length > 0
                    ? `表示中の候補で異なる項目：${diff.differingLabels.join('・')}`
                    : '表示している主要仕様では差を確認できません（同一商品と断定はできません）。'}
                </Typography>
                <Typography variant="caption" color="text.secondary" component="div">
                  表示中の{candidates.length}件での比較です（該当 {search.search.candidate_count}件すべての比較ではありません）。
                  {diff.priceDiffers && ' 税抜価格にも差があります（仕様の差とは別です）。'}
                  {diff.partialLabels.length > 0 && ` 一部の候補でDB情報なし：${diff.partialLabels.join('・')}`}
                </Typography>
              </Box>
            )}

            {candidates.length === 0 && (
              <Alert severity="warning" sx={{ mb: 1 }}>
                候補がありません。読み取り内容を修正して再検索するか、「候補なし」として記録できます。
              </Alert>
            )}
          </>
        )}

        {compareIds.length > 0 && (
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
            <Chip label={`比較対象 ${compareIds.length}件`} size="small" color="info" />
            <Button size="small" disabled={compareIds.length < 2} onClick={() => setCompareOpen(true)}>
              主要仕様を横並び比較
            </Button>
            <Button size="small" onClick={() => setCompareIds([])}>
              選択解除
            </Button>
          </Stack>
        )}

        <Stack spacing={0.75} sx={{ mb: 1 }}>
          {candidates.map((candidate: Candidate) => {
            const adopted = decision?.decision === 'adopted' && decision.record_id === candidate.record.id
            const open = expanded === candidate.record.id
            const specs = candidateSpecValues(candidate)
            const lifecycle = candidate.lifecycle_warning
            return (
              <Card
                key={candidate.record.id}
                variant="outlined"
                sx={{ borderColor: adopted ? 'success.main' : '#d8d1c6', borderWidth: adopted ? 2 : 1, bgcolor: 'common.white' }}
              >
                <CardContent sx={{ py: 1, '&:last-child': { pb: 1 } }}>
                  <Stack direction="row" spacing={0.5} alignItems="baseline" flexWrap="wrap" useFlexGap>
                    <Chip label={`順位 ${candidate.rank}`} size="small" variant="outlined" />
                    <Typography sx={{ fontWeight: 700, fontSize: 14 }}>{candidate.record.full_code || candidate.record.hinban}</Typography>
                    <Typography variant="caption">{candidate.record.key || candidate.record.view_key}</Typography>
                    {adopted && <Chip label="採用中" size="small" color="success" />}
                    <Box sx={{ flex: 1 }} />
                    <Typography variant="caption" color="text.secondary">
                      ID {candidate.record.id} ／ 順位付けスコア {candidate.score}
                    </Typography>
                  </Stack>

                  <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
                    {specs.map((spec) => {
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
                            {spec.key === 'availability'
                              ? (AVAILABILITY_LABELS[candidate.record.availability] ?? candidate.record.availability)
                              : (spec.value ?? 'DB情報なし')}
                          </Typography>
                        </Box>
                      )
                    })}
                  </Stack>

                  <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
                    {lifecycle && (
                      <Chip
                        label={`注意: ${AVAILABILITY_LABELS[lifecycle] ?? lifecycle}`}
                        size="small"
                        color="warning"
                      />
                    )}
                    {candidate.conflicts.length > 0 && (
                      <Chip label={`検索条件との相違 ${candidate.conflicts.length}項目`} size="small" color="warning" />
                    )}
                    {candidate.db_internal_warnings.map((warning) => (
                      <Chip key={warning} label="DB内部の矛盾あり" size="small" color="error" />
                    ))}
                    {candidate.record.price_zeinuki != null && (
                      <Chip label={`税抜 ${candidate.record.price_zeinuki}`} size="small" variant="outlined" />
                    )}
                    <Chip label={`一致 ${candidate.matched_fields.length}項目`} size="small" variant="outlined" />
                  </Stack>

                  <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.5 }}>
                    <Button size="small" onClick={() => setExpanded(open ? null : candidate.record.id)}>
                      {open ? '詳細を閉じる' : '詳細を見る'}
                    </Button>
                    <FormControlLabel
                      control={
                        <Checkbox
                          size="small"
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
                    <Box sx={{ flex: 1 }} />
                    {adopted ? (
                      <Button size="small" color="warning" onClick={() => setDecision(entry.suffix, { decision: 'undecided' })}>
                        採用を取り消す
                      </Button>
                    ) : (
                      <Button
                        size="small"
                        variant="contained"
                        onClick={() =>
                          setDecision(entry.suffix, { decision: 'adopted', record_id: candidate.record.id, search_id: search?.id ?? null })
                        }
                      >
                        この商品を採用
                      </Button>
                    )}
                  </Stack>

                  <Collapse in={open} unmountOnExit>
                    <Divider sx={{ my: 0.5 }} />
                    <Typography variant="caption" component="div" sx={{ fontWeight: 700 }}>
                      候補になった理由・一致項目
                    </Typography>
                    {candidate.matched_fields.map((matched, index) => (
                      <Typography key={index} variant="caption" component="div" color="success.dark">
                        ・{matched.field}
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
                          ・{conflict.field}（{correctedSpecKeys.has(conflict.field) ? '担当者の修正値との差' : '原図の読み取り値との差'}） 条件:{' '}
                          {JSON.stringify(conflict.input)} / DB: {JSON.stringify(conflict.db)}
                        </Typography>
                      ))
                    )}
                    <Typography variant="caption" component="div" sx={{ mt: 0.5 }}>
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

        <Box sx={{ bgcolor: 'common.white', border: 1, borderColor: '#d8d1c6', borderRadius: 1, p: 1, mt: 1 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 0.5 }}>
            判断
          </Typography>
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
          <Stack direction="row" spacing={1}>
            <Button
              variant="outlined"
              color="warning"
              disabled={saving}
              onClick={() => {
                onChange((current) => ({ ...current, status: 'on_hold' }))
                onSave(false, { status: 'on_hold' })
              }}
            >
              保留にして保存
            </Button>
            <Button variant="outlined" disabled={saving} onClick={() => onSave(false)}>
              保存
            </Button>
            <Button variant="contained" disabled={saving} onClick={() => onSave(true)}>
              保存して次へ
            </Button>
            {draft.dirty && <Chip label="未保存の編集あり" size="small" color="warning" />}
          </Stack>
          <Typography variant="caption" color="text.secondary" component="div" sx={{ mt: 0.5 }}>
            機械が1件に絞った場合でも、担当者が採用するまで確認済みにはなりません。
          </Typography>
        </Box>

        {decisionHistory.length > 0 && (
          <Box sx={{ mt: 1, p: 1, bgcolor: 'common.white', border: 1, borderColor: '#d8d1c6', borderRadius: 1 }}>
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

        <CompareDialog open={compareOpen} candidates={compareCandidates} detail={detail} onClose={() => setCompareOpen(false)} />
      </Box>
    </Box>
  )
}
