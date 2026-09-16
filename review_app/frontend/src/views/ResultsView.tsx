import { useCallback, useEffect, useState } from 'react'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { DataGrid, type GridColDef } from '@mui/x-data-grid'
import { api } from '../api'
import { STATUS_COLORS } from '../labels'
import type { ItemRow, ProjectInfo } from '../types'

interface Props {
  project: ProjectInfo
  onError: (message: string) => void
}

export default function ResultsView({ project, onError }: Props) {
  const [rows, setRows] = useState<ItemRow[]>([])
  const [loading, setLoading] = useState(false)

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

  const columns: GridColDef<ItemRow>[] = [
    { field: 'marker', headerName: '管理記号', width: 130 },
    { field: 'name', headerName: '仮の器具名', width: 170 },
    {
      field: 'name_origin',
      headerName: '器具名の出所',
      width: 110,
      valueGetter: (_value, row) => ({ drawing: '原図', partial: '原図（一部）', inferred: '推定', unknown: '不明' })[row.name_origin],
    },
    { field: 'source_file', headerName: '元ファイル', width: 120 },
    { field: 'page', headerName: 'ページ', width: 70, type: 'number' },
    {
      field: 'adopted',
      headerName: '採用品番',
      width: 200,
      valueGetter: (_value, row) => row.adopted.map((value) => value.code ?? value.record_id).join(' / '),
    },
    {
      field: 'candidate_total',
      headerName: '候補件数',
      width: 150,
      valueGetter: (_value, row) =>
        row.searched_entries === 0 ? '未検索' : `${row.candidate_returned}件表示 / 総${row.candidate_total}件${row.candidate_truncated ? '(打切)' : ''}`,
    },
    {
      field: 'status_label',
      headerName: '確認状況',
      width: 120,
      renderCell: (params) => <Chip label={params.row.status_label} color={STATUS_COLORS[params.row.status]} variant={params.row.status === 'unconfirmed' ? 'outlined' : 'filled'} />,
    },
    { field: 'quantity_status_label', headerName: '数量の確認状況', width: 140 },
    {
      field: 'quantity_value',
      headerName: '数量',
      width: 90,
      valueGetter: (_value, row) => (row.quantity_value == null ? '' : `${row.quantity_value}${row.quantity_unit ?? ''}`),
    },
    { field: 'relation_label', headerName: '品番関係', width: 170 },
    { field: 'updated_at', headerName: '更新日時', width: 180 },
  ]

  const counts = project.status_counts

  return (
    <Box sx={{ p: 2, height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }} flexWrap="wrap" useFlexGap>
        <Typography variant="h6">結果一覧・出力</Typography>
        <Chip label={`解析済み対象 ${project.item_count}件`} color="primary" variant="outlined" />
        <Chip label={`未確認 ${counts.unconfirmed}`} />
        <Chip label={`保留 ${counts.on_hold}`} color="warning" variant="outlined" />
        <Chip label={`確認済み ${counts.confirmed}`} color="success" variant="outlined" />
        <Chip label={`再確認が必要 ${counts.needs_recheck}`} color="error" variant="outlined" />
        <Box sx={{ flex: 1 }} />
        <Button variant="outlined" onClick={() => reload()} disabled={loading}>
          再読み込み
        </Button>
        <Button variant="contained" component="a" href={api.exportJsonUrl(project.id)} download>
          JSON出力
        </Button>
        <Button variant="contained" component="a" href={api.exportCsvUrl(project.id)} download>
          CSV出力（UTF-8 BOM付き）
        </Button>
      </Stack>
      <Alert severity="info" sx={{ mb: 1 }}>
        CSVは今回の確認一覧です。既存見積システムへの正式な取り込み形式ではありません。未確認・保留・再確認が必要の対象も、確定済みと区別したうえで出力します。
      </Alert>
      <Box sx={{ flex: 1, minHeight: 0, bgcolor: 'background.paper' }}>
        <DataGrid
          rows={rows}
          columns={columns}
          loading={loading}
          density="compact"
          disableRowSelectionOnClick
          initialState={{ pagination: { paginationModel: { pageSize: 50 } } }}
          pageSizeOptions={[25, 50, 100]}
        />
      </Box>
    </Box>
  )
}
