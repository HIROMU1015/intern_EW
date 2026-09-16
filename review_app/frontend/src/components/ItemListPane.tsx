import { useEffect, useMemo, useState } from 'react'
import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import List from '@mui/material/List'
import ListItemButton from '@mui/material/ListItemButton'
import MenuItem from '@mui/material/MenuItem'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { ORIGIN_LABELS, STATUS_COLORS } from '../labels'
import type { ItemRow } from '../types'

type FilterKey = 'all' | 'unconfirmed' | 'on_hold' | 'confirmed' | 'needs_recheck' | 'relation' | 'image_missing'

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: 'all', label: 'すべて' },
  { key: 'unconfirmed', label: '未確認' },
  { key: 'on_hold', label: '保留' },
  { key: 'needs_recheck', label: '再確認が必要' },
  { key: 'confirmed', label: '確認済み' },
  { key: 'relation', label: '分割・関係の確認' },
  { key: 'image_missing', label: '画像欠損' },
]

interface Props {
  rows: ItemRow[]
  selectedId: string | null
  onSelect: (id: string) => void
  onFilteredChange: (ids: string[]) => void
  dirtyIds: string[]
  projectItemCount: number
}

export default function ItemListPane({ rows, selectedId, onSelect, onFilteredChange, dirtyIds, projectItemCount }: Props) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<FilterKey>('all')

  const filtered = useMemo(() => {
    const text = query.trim().toLowerCase()
    return rows.filter((row) => {
      if (filter === 'relation' && !['multiple_fixtures', 'unresolved'].includes(row.relation_status)) return false
      if (filter === 'image_missing' && row.has_image) return false
      if (['unconfirmed', 'on_hold', 'confirmed', 'needs_recheck'].includes(filter) && row.status !== filter) return false
      if (!text) return true
      const haystack = [row.marker, row.name, row.category ?? '', row.source_file ?? '', ...row.adopted.map((value) => value.code ?? '')]
        .join(' ')
        .toLowerCase()
      return haystack.includes(text)
    })
  }, [rows, query, filter])

  useEffect(() => {
    onFilteredChange(filtered.map((row) => row.id))
  }, [filtered, onFilteredChange])

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <Box sx={{ p: 1, borderBottom: 1, borderColor: 'divider' }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
          見積対象（解析済み対象 {projectItemCount}件）
        </Typography>
        <Typography variant="caption" color="text.secondary" component="div" sx={{ mb: 1 }}>
          入力PDFから読み取った器具の一覧。全件確認してもPDF全体の確認完了ではない。
        </Typography>
        <TextField
          fullWidth
          placeholder="管理記号・器具名・品番で検索"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          sx={{ mb: 1 }}
        />
        <TextField select fullWidth value={filter} onChange={(event) => setFilter(event.target.value as FilterKey)}>
          {FILTERS.map((option) => (
            <MenuItem key={option.key} value={option.key}>
              {option.label}
            </MenuItem>
          ))}
        </TextField>
        <Typography variant="caption" color="text.secondary">
          表示 {filtered.length} / {rows.length} 件
        </Typography>
      </Box>

      <List dense sx={{ flex: 1, overflow: 'auto', py: 0 }}>
        {filtered.map((row) => {
          const selected = row.id === selectedId
          return (
            <ListItemButton
              key={row.id}
              selected={selected}
              onClick={() => onSelect(row.id)}
              sx={{
                display: 'block',
                borderBottom: 1,
                borderColor: 'divider',
                borderLeft: selected ? 4 : 0,
                borderLeftColor: 'primary.main',
                pl: selected ? 1 : 1.5,
              }}
            >
              <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mb: 0.25 }}>
                <Typography sx={{ fontWeight: 700, fontSize: 13 }}>{row.marker}</Typography>
                {dirtyIds.includes(row.id) && <Chip label="未保存" color="warning" variant="outlined" />}
              </Stack>
              <Typography variant="caption" component="div" sx={{ color: 'text.primary' }}>
                {row.name}
                {row.name_origin !== 'drawing' && `（${ORIGIN_LABELS[row.name_origin] ?? row.name_origin}）`}
              </Typography>
              <Typography variant="caption" component="div" color="text.secondary">
                {row.source_file} / {row.page}ページ{row.item_no != null ? ` 器具${row.item_no}` : ''}
              </Typography>
              <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
                <Chip label={`状態: ${row.status_label}`} color={STATUS_COLORS[row.status]} variant={row.status === 'unconfirmed' ? 'outlined' : 'filled'} />
                <Chip label={row.quantity_status_label} variant="outlined" />
                <Chip
                  label={row.searched_entries === 0 ? '候補: 未検索' : `候補: ${row.candidate_returned}件表示 / 総${row.candidate_total}件${row.candidate_truncated ? '(打切)' : ''}`}
                  variant="outlined"
                />
                {row.entry_count > 1 && <Chip label={`品番${row.entry_count}件: ${row.relation_label}`} variant="outlined" color={row.relation_status === 'multiple_fixtures' || row.relation_status === 'unresolved' ? 'warning' : 'default'} />}
                {!row.has_image && <Chip label="画像欠損" color="warning" variant="outlined" />}
              </Stack>
              {row.adopted.length > 0 && (
                <Typography variant="caption" component="div" sx={{ mt: 0.5, color: 'success.dark' }}>
                  採用品番: {row.adopted.map((value) => value.code ?? value.record_id).join(' / ')}
                </Typography>
              )}
            </ListItemButton>
          )
        })}
      </List>
    </Box>
  )
}
