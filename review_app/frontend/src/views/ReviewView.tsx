import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import LinearProgress from '@mui/material/LinearProgress'
import Snackbar from '@mui/material/Snackbar'
import Typography from '@mui/material/Typography'
import { api } from '../api'
import CandidatePane from '../components/CandidatePane'
import ExtractionPane from '../components/ExtractionPane'
import ImagePane from '../components/ImagePane'
import ItemListPane from '../components/ItemListPane'
import type {
  Corrections,
  EntryDecisionName,
  ItemDetail,
  ItemRow,
  ItemStatus,
  ProjectInfo,
  QuantityStatus,
  RelationStatus,
  SearchResult,
} from '../types'

export interface Draft {
  corrections: Corrections
  quantityValue: string
  quantityUnit: string
  status: ItemStatus
  quantityStatus: QuantityStatus
  relationStatus: RelationStatus
  holdReason: string
  memo: string
  decisions: Record<
    string,
    {
      decision: EntryDecisionName
      record_id?: string | null
      search_id?: string | null
      note?: string | null
      reaffirm?: boolean
      reaffirm_basis?: Corrections
    }
  >
  dirty: boolean
}

function createDraft(detail: ItemDetail): Draft {
  const decisions: Draft['decisions'] = {}
  for (const entry of detail.entries) {
    decisions[entry.suffix] = {
      decision: entry.decision.decision,
      record_id: entry.decision.adopted_record_id,
      search_id: entry.decision.adopted_search_id,
      note: entry.decision.note,
      reaffirm: false, // 保存後は「判断し直した」印を落とす
    }
  }
  return {
    corrections: JSON.parse(JSON.stringify(detail.review.corrections ?? {})) as Corrections,
    quantityValue: detail.review.quantity_value != null ? String(detail.review.quantity_value) : '',
    quantityUnit: detail.review.quantity_unit ?? detail.quantity.unit ?? '',
    status: detail.review.status,
    quantityStatus: detail.review.quantity_status,
    relationStatus: detail.review.relation_status,
    holdReason: detail.review.hold_reason ?? '',
    memo: detail.review.memo ?? '',
    decisions,
    dirty: false,
  }
}

interface Props {
  project: ProjectInfo
  onProjectChanged: () => void
  onError: (message: string) => void
}

export default function ReviewView({ project, onProjectChanged, onError }: Props) {
  const [rows, setRows] = useState<ItemRow[]>([])
  const [filteredIds, setFilteredIds] = useState<string[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [details, setDetails] = useState<Record<string, ItemDetail>>({})
  const [drafts, setDrafts] = useState<Record<string, Draft>>({})
  const [searches, setSearches] = useState<Record<string, Record<string, SearchResult>>>({})
  const [loadingItem, setLoadingItem] = useState(false)
  const [searching, setSearching] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const searchSeq = useRef<Record<string, number>>({})

  const reloadRows = useCallback(async () => {
    try {
      const { items } = await api.items(project.id)
      setRows(items)
      setSelectedId((current) => current ?? items[0]?.id ?? null)
    } catch (reason) {
      onError((reason as Error).message)
    }
  }, [project.id, onError])

  useEffect(() => {
    setRows([])
    setDetails({})
    setDrafts({})
    setSearches({})
    setSelectedId(null)
    void reloadRows()
  }, [reloadRows])

  const loadDetail = useCallback(
    async (itemId: string) => {
      setLoadingItem(true)
      try {
        const { item } = await api.item(itemId)
        setDetails((current) => ({ ...current, [itemId]: item }))
        setDrafts((current) => (current[itemId] ? current : { ...current, [itemId]: createDraft(item) }))
        setSearches((current) => {
          const entryMap: Record<string, SearchResult> = { ...(current[itemId] ?? {}) }
          for (const entry of item.entries) {
            if (entry.search && !entryMap[entry.suffix]) entryMap[entry.suffix] = entry.search
          }
          return { ...current, [itemId]: entryMap }
        })
      } catch (reason) {
        onError((reason as Error).message)
      } finally {
        setLoadingItem(false)
      }
    },
    [onError],
  )

  useEffect(() => {
    if (selectedId && !details[selectedId]) void loadDetail(selectedId)
  }, [selectedId, details, loadDetail])

  const detail = selectedId ? details[selectedId] : undefined
  const draft = selectedId ? drafts[selectedId] : undefined

  const updateDraft = useCallback(
    (itemId: string, updater: (draft: Draft) => Draft) => {
      setDrafts((current) => {
        const base = current[itemId]
        if (!base) return current
        const next = updater(base)
        // 検索条件を変えたら、「この条件で判断し直す」の印は持ち越さない。
        const conditionsChanged = JSON.stringify(next.corrections) !== JSON.stringify(base.corrections)
        const decisions = conditionsChanged
          ? Object.fromEntries(
              Object.entries(next.decisions).map(([suffix, value]) =>
                value.reaffirm ? [suffix, { ...value, reaffirm: false, reaffirm_basis: undefined }] : [suffix, value],
              ),
            )
          : next.decisions
        return { ...current, [itemId]: { ...next, decisions, dirty: true } }
      })
    },
    [],
  )

  const runSearch = useCallback(
    async (itemId: string, entrySuffix: string | null, topK?: number) => {
      const currentDraft = drafts[itemId]
      const key = `${itemId}:${entrySuffix ?? 'all'}`
      const token = (searchSeq.current[key] ?? 0) + 1
      searchSeq.current[key] = token
      setSearching(entrySuffix ?? 'all')
      try {
        const { results } = await api.search(itemId, {
          entry_suffix: entrySuffix,
          corrections: currentDraft?.corrections ?? {},
          top_k: topK,
        })
        if (searchSeq.current[key] !== token) return // 遅れて返った結果は捨てる
        setSearches((current) => {
          const entryMap = { ...(current[itemId] ?? {}) }
          for (const result of results) {
            if (result.item_id !== itemId) continue // 別の器具には反映しない
            if (result.is_latest === false) continue // バックエンドが古いと判断した結果は表示しない
            entryMap[result.entry_suffix] = result.search
          }
          return { ...current, [itemId]: entryMap }
        })
        const notes = results.flatMap((result) => result.notes)
        if (notes.length) setNotice(notes.join(' / '))
        const { item } = await api.item(itemId)
        setDetails((current) => ({ ...current, [itemId]: item }))
        // 検索でバックエンドが「再確認が必要」にした場合は、編集中の確認状態にも反映する。
        if (item.review.status === 'needs_recheck') {
          setDrafts((current) => {
            const draft = current[itemId]
            if (!draft || draft.status === 'needs_recheck') return current
            return { ...current, [itemId]: { ...draft, status: 'needs_recheck' } }
          })
        }
        void reloadRows()
      } catch (reason) {
        onError((reason as Error).message)
      } finally {
        setSearching(null)
      }
    },
    [drafts, onError, reloadRows],
  )

  const save = useCallback(
    async (itemId: string, moveNext: boolean, override?: Partial<Draft>) => {
      const base = drafts[itemId]
      if (!base) return
      // ボタンから状態を指定された場合も、保存に使う内容と画面表示を同じにする。
      const currentDraft: Draft = override ? { ...base, ...override } : base
      if (override) setDrafts((current) => ({ ...current, [itemId]: { ...currentDraft, dirty: true } }))
      setSaving(true)
      try {
        const quantityValue = currentDraft.quantityValue.trim()
        const response = await api.saveReview(itemId, {
          status: currentDraft.status,
          quantity_status: currentDraft.quantityStatus,
          relation_status: currentDraft.relationStatus,
          quantity: { value: quantityValue === '' ? null : Number(quantityValue), unit: currentDraft.quantityUnit || null },
          corrections: currentDraft.corrections,
          hold_reason: currentDraft.holdReason || null,
          memo: currentDraft.memo || null,
          entries: currentDraft.decisions,
        })
        setDetails((current) => ({ ...current, [itemId]: response.item }))
        setDrafts((current) => ({ ...current, [itemId]: createDraft(response.item) }))
        setNotice(
          response.notes.length ? `保存しました。${response.notes.join(' / ')}` : `保存しました（版 ${response.saved_revision}）。`,
        )
        await reloadRows()
        onProjectChanged()
        if (moveNext) {
          const order = filteredIds.length ? filteredIds : rows.map((row) => row.id)
          const index = order.indexOf(itemId)
          const next = order[index + 1]
          if (next) setSelectedId(next)
        }
      } catch (reason) {
        // 保存に失敗したときは成功表示をせず、編集内容はそのまま残す。
        onError(`保存できませんでした: ${(reason as Error).message}`)
      } finally {
        setSaving(false)
      }
    },
    [drafts, filteredIds, rows, onError, onProjectChanged, reloadRows],
  )

  const dirtyCount = useMemo(() => Object.values(drafts).filter((value) => value.dirty).length, [drafts])

  return (
    <Box sx={{ height: '100%', display: 'flex', minHeight: 0 }}>
      <Box sx={{ width: 330, borderRight: 1, borderColor: 'divider', bgcolor: 'background.paper', minHeight: 0 }}>
        <ItemListPane
          rows={rows}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onFilteredChange={setFilteredIds}
          dirtyIds={Object.entries(drafts).filter(([, value]) => value.dirty).map(([key]) => key)}
          projectItemCount={project.item_count}
        />
      </Box>

      <Box sx={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        {loadingItem && <LinearProgress />}
        {detail ? (
          <ImagePane detail={detail} />
        ) : (
          <Box sx={{ p: 3 }}>
            <Typography color="text.secondary">左の一覧から見積対象を選んでください。</Typography>
          </Box>
        )}
      </Box>

      <Box
        sx={{
          width: 620,
          borderLeft: 1,
          borderColor: 'divider',
          display: 'flex',
          flexDirection: 'column',
          minHeight: 0,
          bgcolor: 'grey.300',
          gap: '6px',
        }}
      >
        {detail && draft ? (
          <>
            <Box sx={{ flex: '0 0 48%', minHeight: 0, overflow: 'auto', bgcolor: 'background.paper' }}>
              <ExtractionPane
                detail={detail}
                draft={draft}
                searching={searching !== null}
                onChange={(updater) => updateDraft(detail.id, updater)}
                onResearch={() => runSearch(detail.id, null)}
              />
            </Box>
            <Box sx={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
              <CandidatePane
                detail={detail}
                draft={draft}
                searches={searches[detail.id] ?? {}}
                searching={searching}
                saving={saving}
                onChange={(updater) => updateDraft(detail.id, updater)}
                onResearchEntry={(suffix, topK) => runSearch(detail.id, suffix, topK)}
                onSave={(moveNext, override) => save(detail.id, moveNext, override)}
              />
            </Box>
          </>
        ) : (
          <Box sx={{ p: 2 }}>
            <Alert severity="info">見積対象を選ぶと、読み取り結果と商品候補が表示されます。</Alert>
          </Box>
        )}
      </Box>

      <Snackbar
        open={notice !== null}
        autoHideDuration={6000}
        onClose={() => setNotice(null)}
        message={notice ?? ''}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      />
      {dirtyCount > 0 && (
        <Box sx={{ position: 'fixed', bottom: 8, left: 8, zIndex: 1200 }}>
          <Alert severity="warning" variant="filled" sx={{ py: 0 }}>
            未保存の編集 {dirtyCount}件（器具を切り替えても保持されます）
          </Alert>
        </Box>
      )}
    </Box>
  )
}
