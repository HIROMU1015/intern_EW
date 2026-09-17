import { useState } from 'react'
import Box from '@mui/material/Box'
import Checkbox from '@mui/material/Checkbox'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Collapse from '@mui/material/Collapse'
import MenuItem from '@mui/material/MenuItem'
import Stack from '@mui/material/Stack'
import Tooltip from '@mui/material/Tooltip'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { fieldView, showValue, type FieldStatus } from '../lib/fieldState'
import type { Corrections, FieldValue } from '../types'

const STATUS_STYLE: Record<FieldStatus, { chip: 'default' | 'info' | 'warning' | 'primary'; variant: 'filled' | 'outlined'; bg?: string; accent?: string; valueColor: string }> = {
  read: { chip: 'info', variant: 'outlined', valueColor: 'text.primary' },
  inferred: { chip: 'warning', variant: 'filled', bg: '#fff8e1', accent: '#f0b429', valueColor: 'text.primary' },
  attention: { chip: 'warning', variant: 'filled', bg: '#fff8e1', accent: '#f0b429', valueColor: 'text.primary' },
  missing: { chip: 'default', variant: 'outlined', valueColor: 'text.disabled' },
  not_stated: { chip: 'default', variant: 'outlined', valueColor: 'text.secondary' },
  corrected: { chip: 'primary', variant: 'filled', bg: '#eaf2fb', accent: '#1976d2', valueColor: 'text.primary' },
}

export interface SelectOption {
  value: string
  label: string
}

interface Props {
  field: FieldValue
  corrections: Corrections | undefined
  numeric?: boolean
  options?: SelectOption[]
  /** 原文・正規化値・出所などの［補足］を出すか。一覧を簡潔にしたい場所では false。 */
  supplement?: boolean
  /** この項目を検索条件に使うか。未指定ならチェックボックスを出さない。 */
  searchEnabled?: boolean
  onToggleSearch?: (next: boolean) => void
  onSet: (value: unknown) => void
  onClear: () => void
}

export default function ReadingFieldRow({
  field,
  corrections,
  numeric,
  options,
  supplement = true,
  searchEnabled,
  onToggleSearch,
  onSet,
  onClear,
}: Props) {
  const [editing, setEditing] = useState(false)
  const [details, setDetails] = useState(false)
  const view = fieldView(field, corrections)
  const style = STATUS_STYLE[view.status]
  const correctionValue = (corrections?.specifications ?? {})[field.key]
  // 検索条件にできるのは、取り込み時に条件へ変換できた項目か、担当者が値を入れ直した項目だけ。
  const searchable = field.used_in_search || (correctionValue !== undefined && correctionValue !== null && correctionValue !== '')
  const editingValue = correctionValue === null || correctionValue === undefined ? '' : String(correctionValue)

  return (
    <Box
      className="reading-field-row"
      sx={{
        px: 1,
        py: 0.75,
        borderBottom: 1,
        borderColor: 'divider',
        bgcolor: style.bg ?? 'transparent',
        borderLeft: style.accent ? 3 : 0,
        borderLeftColor: style.accent ?? 'transparent',
      }}
    >
      <Stack direction="row" spacing={1} alignItems="baseline" flexWrap="wrap" useFlexGap>
        {onToggleSearch && (
          <Tooltip
            title={
              searchable
                ? '検索条件に使う（外すと読み取り値は残したまま条件から除く）'
                : 'この値は検索条件に使える形で読み取れていないため、条件にできません'
            }
          >
            {/* Tooltip は disabled な要素を包めないので span を挟む。 */}
            <Box component="span" sx={{ display: 'inline-flex' }}>
              <Checkbox
                size="small"
                sx={{ p: 0 }}
                checked={searchable && searchEnabled !== false}
                disabled={!searchable}
                onChange={(event) => onToggleSearch(event.target.checked)}
                inputProps={{ 'aria-label': `${field.label}を検索条件に使う` }}
              />
            </Box>
          </Tooltip>
        )}
        <Typography variant="caption" sx={{ minWidth: 92, color: 'text.secondary' }}>
          {field.label}
        </Typography>
        {/* 1行1項目なので、値の幅を揃えて状態バッジの位置を縦にそろえる。 */}
        <Typography
          sx={{ minWidth: 120, fontWeight: view.status === 'missing' ? 400 : 700, fontSize: 14, color: style.valueColor }}
        >
          {view.displayValue}
        </Typography>
        <Chip label={view.statusLabel} color={style.chip} variant={style.variant} size="small" />
        <Box sx={{ flex: 1 }} />
        <Button size="small" onClick={() => setEditing((value) => !value)}>
          {editing ? '閉じる' : '修正'}
        </Button>
        {supplement && (
          <Button size="small" color="inherit" onClick={() => setDetails((value) => !value)}>
            補足
          </Button>
        )}
      </Stack>

      <Collapse in={editing} unmountOnExit>
        <Box sx={{ mt: 1, p: 1, bgcolor: 'common.white', border: 1, borderColor: 'primary.light', borderRadius: 1 }}>
          <Typography variant="caption" color="text.secondary" component="div">
            元の読み取り値: {view.originalValue || '未取得'}
          </Typography>
          {options ? (
            <TextField
              select
              fullWidth
              label="修正値"
              value={correctionValue === undefined ? '' : String(correctionValue)}
              onChange={(event) => (event.target.value === '' ? onClear() : onSet(event.target.value))}
              sx={{ mt: 0.5, bgcolor: 'common.white' }}
            >
              <MenuItem value="">（修正しない）</MenuItem>
              {options.map((option) => (
                <MenuItem key={option.value} value={option.value}>
                  {option.label}
                </MenuItem>
              ))}
            </TextField>
          ) : (
            <TextField
              fullWidth
              label="修正値"
              type={numeric ? 'number' : 'text'}
              value={editingValue}
              placeholder={view.originalValue || '未取得'}
              onChange={(event) => {
                const text = event.target.value
                if (text === '') {
                  onSet(null)
                  return
                }
                onSet(numeric ? Number(text) : text)
              }}
              sx={{ mt: 0.5, bgcolor: 'common.white' }}
            />
          )}
          <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
            <Button size="small" variant="outlined" onClick={onClear}>
              元の読み取り値に戻す
            </Button>
            <Button size="small" variant="outlined" color="warning" onClick={() => onSet(null)}>
              不明にする
            </Button>
          </Stack>
          {view.correctedToUnknown && (
            <Typography variant="caption" color="warning.main" component="div" sx={{ mt: 0.5 }}>
              「不明」として扱い、検索条件から外します（0やfalseにはしません）。
            </Typography>
          )}
        </Box>
      </Collapse>

      <Collapse in={supplement && details} unmountOnExit>
        <Box sx={{ mt: 0.5, pl: 1, borderLeft: 2, borderColor: 'divider' }}>
          <Typography variant="caption" color="text.secondary" component="div">
            読み取り原文: {showValue(field.raw) || '—'}
          </Typography>
          <Typography variant="caption" color="text.secondary" component="div">
            正規化値: {showValue(field.value) || '—'}
          </Typography>
          <Typography variant="caption" color="text.secondary" component="div">
            出所: {view.originLabel} / 検索条件: {field.used_in_search ? '使用' : '未使用'}
          </Typography>
          {view.noteLabels.length > 0 && (
            <Typography variant="caption" color="warning.dark" component="div">
              判定の根拠: {view.noteLabels.join(' / ')}
            </Typography>
          )}
        </Box>
      </Collapse>
    </Box>
  )
}
