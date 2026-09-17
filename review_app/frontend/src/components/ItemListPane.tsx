import { useEffect, useMemo, useState } from 'react'
import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import List from '@mui/material/List'
import ListItemButton from '@mui/material/ListItemButton'
import MenuItem from '@mui/material/MenuItem'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { STATUS_COLORS } from '../labels'
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

/**
 * 左カラムは「器具を選ぶ」ことだけに使う。
 * 管理記号・器具名・確認状態だけを出し、件数や関係などの細かい情報は中央・右のカラムに任せる。
 * 検索と絞り込みは残す（「採用して次へ」で進む順番を決めているため）。
 */
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
          見積対象 {projectItemCount}件
        </Typography>
        <TextField
          fullWidth
          placeholder="管理記号・器具名・品番"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          sx={{ mt: 1, mb: 0.75 }}
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
                // 選択中の器具は背景色で分かるようにする。
                bgcolor: selected ? 'primary.50' : 'transparent',
                '&.Mui-selected': { bgcolor: '#e3efff' },
                '&.Mui-selected:hover': { bgcolor: '#d6e7fb' },
              }}
            >
              <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap" useFlexGap>
                <Typography sx={{ fontWeight: 700, fontSize: 13, flex: 1, minWidth: 0 }} noWrap>
                  {row.marker}
                </Typography>
                <Chip
                  label={row.status_label}
                  color={STATUS_COLORS[row.status]}
                  variant={row.status === 'unconfirmed' ? 'outlined' : 'filled'}
                />
              </Stack>
              <Typography variant="caption" component="div" sx={{ color: 'text.secondary' }} noWrap>
                {row.name}
              </Typography>
              {row.adopted.length > 0 && (
                <Typography variant="caption" component="div" sx={{ color: 'success.dark' }} noWrap>
                  採用 {row.adopted.map((value) => value.code ?? value.record_id).join(' / ')}
                </Typography>
              )}
              {dirtyIds.includes(row.id) && (
                <Chip label="未保存" color="warning" variant="outlined" sx={{ mt: 0.25 }} />
              )}
            </ListItemButton>
          )
        })}
      </List>
    </Box>
  )
}
