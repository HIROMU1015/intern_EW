import { useCallback, useEffect, useMemo, useState } from 'react'
import Accordion from '@mui/material/Accordion'
import AccordionDetails from '@mui/material/AccordionDetails'
import AccordionSummary from '@mui/material/AccordionSummary'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Stack from '@mui/material/Stack'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { DataGrid, type GridColDef } from '@mui/x-data-grid'
import { api } from '../api'
import { STATUS_COLORS, STATUS_LABELS } from '../labels'
import type { ItemRow, ItemStatus, ProjectInfo } from '../types'

interface Props {
  project: ProjectInfo
  /** 行から確認画面へ戻るときに呼ぶ。 */
  onOpenItem: (itemId: string) => void
  onError: (message: string) => void
}

/**
 * 一覧に出す注意点をひとつの列にまとめる。
 * 問題がない対象では空にして、目を引くのは対応が要る行だけにする。
 */
function attentionText(row: ItemRow): string {
  const notes: string[] = []
  if (row.status === 'needs_recheck') notes.push('再確認が必要')
  if (row.quantity_status === 'unreadable') notes.push('数量が読み取れない')
  else if (row.quantity_status === 'unconfirmed') notes.push('数量未確認')
  if (row.relation_status === 'multiple_fixtures') notes.push('複数の器具が混在の可能性')
  else if (row.relation_status === 'unresolved') notes.push('複数品番あり')
  // 検索済みなのに候補が0件だった対象。未検索とは区別する。
  if (row.searched_entries > 0 && row.candidate_total === 0) notes.push('候補なし')
  if (!row.has_image) notes.push('図面の画像なし')
  return notes.join('・')
}

/** 省略された文字列もマウスを乗せれば全文が読めるようにする。 */
function textCell(value: unknown) {
  const text = value == null ? '' : String(value)
  if (!text) return null
  return (
    <Tooltip title={text}>
      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{text}</span>
    </Tooltip>
  )
}

const GRID_LOCALE = {
  noRowsLabel: '対象がありません',
  footerTotalRows: '全件:',
  MuiTablePagination: {
    labelRowsPerPage: '表示件数：',
    labelDisplayedRows: ({ from, to, count }: { from: number; to: number; count: number }) =>
      `${from}〜${to}件 / 全${count === -1 ? to : count}件`,
  },
}

export default function ResultsView({ project, onOpenItem, onError }: Props) {
  const [rows, setRows] = useState<ItemRow[]>([])
  const [loading, setLoading] = useState(false)
  // 上部の件数をクリックしたときの絞り込み。null はすべて表示。
  const [statusFilter, setStatusFilter] = useState<ItemStatus | null>(null)

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const { items } = await api.items(project.id)
      setRows(items)
    } catch (reason) {
      onError((reason as Error).message)
    } finally {
      setLoading(false)
    }
  }, [project.id, onError])

  useEffect(() => {
    void reload()
  }, [reload])

  const visibleRows = useMemo(
    () => (statusFilter ? rows.filter((row) => row.status === statusFilter) : rows),
    [rows, statusFilter],
  )

  const columns: GridColDef<ItemRow>[] = [
    { field: 'marker', headerName: '管理記号', width: 120, renderCell: (params) => textCell(params.value) },
    { field: 'name', headerName: '器具名', width: 170, renderCell: (params) => textCell(params.value) },
    { field: 'source_file', headerName: '元ファイル', width: 120, renderCell: (params) => textCell(params.value) },
    { field: 'page', headerName: 'ページ', width: 70, type: 'number' },
    {
      field: 'adopted',
      headerName: '採用品番',
      width: 190,
      valueGetter: (_value, row) => row.adopted.map((value) => value.code ?? value.record_id).join(' / '),
      renderCell: (params) => textCell(params.value),
    },
    {
      field: 'quantity_value',
      headerName: '数量',
      width: 80,
      valueGetter: (_value, row) => (row.quantity_value == null ? '' : `${row.quantity_value}${row.quantity_unit ?? ''}`),
    },
    {
      field: 'status_label',
      headerName: '確認状況',
      width: 120,
      renderCell: (params) => (
        <Chip
          label={STATUS_LABELS[params.row.status] ?? params.row.status_label}
          color={STATUS_COLORS[params.row.status]}
          variant={params.row.status === 'unconfirmed' ? 'outlined' : 'filled'}
        />
      ),
    },
    {
      // 数量の確認状況・品番関係・候補の有無は、問題があるときだけここにまとめる。
      field: 'attention',
      headerName: '注意',
      width: 230,
      valueGetter: (_value, row) => attentionText(row),
      renderCell: (params) =>
        params.value ? (
          <Tooltip title={String(params.value)}>
            <Typography
              variant="caption"
              sx={{ color: 'warning.dark', fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            >
              {params.value}
            </Typography>
          </Tooltip>
        ) : (
          <Typography variant="caption" color="text.disabled">
            —
          </Typography>
        ),
    },
  ]

  const counts = project.status_counts
  const statusChips: { key: ItemStatus; label: string; color: 'default' | 'warning' | 'success' | 'error'; count: number }[] = [
    { key: 'unconfirmed', label: '未確認', color: 'default', count: counts.unconfirmed },
    { key: 'on_hold', label: STATUS_LABELS.on_hold, color: 'warning', count: counts.on_hold },
    { key: 'confirmed', label: '確認済み', color: 'success', count: counts.confirmed },
    { key: 'needs_recheck', label: '再確認', color: 'error', count: counts.needs_recheck },
  ]

  return (
    <Box sx={{ p: 2, height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }} flexWrap="wrap" useFlexGap>
        <Typography variant="h6">結果一覧・出力</Typography>
        {/* 件数はそのまま絞り込みボタンとして使う。選択中は塗りつぶしで示す。 */}
        <Chip
          label={`全${project.item_count}件`}
          color="primary"
          variant={statusFilter === null ? 'filled' : 'outlined'}
          onClick={() => setStatusFilter(null)}
        />
        {statusChips.map((chip) => (
          <Chip
            key={chip.key}
            label={`${chip.label} ${chip.count}`}
            color={chip.color}
            variant={statusFilter === chip.key ? 'filled' : 'outlined'}
            onClick={() => setStatusFilter((current) => (current === chip.key ? null : chip.key))}
          />
        ))}
        <Box sx={{ flex: 1 }} />
        <Button variant="outlined" onClick={() => reload()} disabled={loading}>
          最新の状態に更新
        </Button>
        <Tooltip title="Excelでそのまま開ける形式（UTF-8 BOM付き）で保存します">
          <Button variant="contained" size="large" component="a" href={api.exportCsvUrl(project.id)} download>
            CSV出力
          </Button>
        </Tooltip>
      </Stack>

      <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
        数量未確認・複数商品の場合は、CSVの数量や合計金額が空欄になることがあります。
        {statusFilter && `（「${statusChips.find((chip) => chip.key === statusFilter)?.label}」だけ表示中）`}
      </Typography>

      {/* 毎回読む必要のない説明と、通常利用では使わない出力はここへ畳む。 */}
      <Accordion disableGutters sx={{ mb: 1 }}>
        <AccordionSummary>
          <Typography variant="body2">出力ルールを見る・その他の出力</Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Typography variant="body2" component="div" sx={{ mb: 1 }}>
            CSVは採用商品ごとに1行で、品番・個数・税抜単価・税抜合計金額を出力します。数量が不明な場合と、複数商品への個数配分が未確定の場合は合計を空欄にします。単価0は0のまま出力します。未確認・あとで確認の対象も確認状態を付けて出力します。文字コードはUTF-8（BOM付き）で、Excelでそのまま開けます。
          </Typography>
          <Button variant="outlined" component="a" href={api.exportJsonUrl(project.id)} download>
            JSON出力（候補や判断の記録を含む詳細データ）
          </Button>
        </AccordionDetails>
      </Accordion>

      <Box sx={{ flex: 1, minHeight: 0, bgcolor: 'background.paper' }}>
        <DataGrid
          rows={visibleRows}
          columns={columns}
          loading={loading}
          density="compact"
          disableRowSelectionOnClick
          localeText={GRID_LOCALE}
          // 行をクリックするとその器具の確認画面へ戻る。出力ボタン等は行の外なので影響しない。
          onRowClick={(params) => onOpenItem(String(params.id))}
          sx={{ '& .MuiDataGrid-row': { cursor: 'pointer' } }}
          initialState={{ pagination: { paginationModel: { pageSize: 50 } } }}
          pageSizeOptions={[25, 50, 100]}
        />
      </Box>
    </Box>
  )
}
