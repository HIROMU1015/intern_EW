import { useState } from 'react'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Collapse from '@mui/material/Collapse'
import MenuItem from '@mui/material/MenuItem'
import Stack from '@mui/material/Stack'
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
  onSet: (value: unknown) => void
  onClear: () => void
}

export default function ReadingFieldRow({ field, corrections, numeric, options, onSet, onClear }: Props) {
  const [editing, setEditing] = useState(false)
  const [details, setDetails] = useState(false)
  const view = fieldView(field, corrections)
  const style = STATUS_STYLE[view.status]
  const correctionValue = (corrections?.specifications ?? {})[field.key]
  const editingValue = correctionValue === null || correctionValue === undefined ? '' : String(correctionValue)

  return (
    <Box
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
        <Typography variant="caption" sx={{ minWidth: 92, color: 'text.secondary' }}>
          {field.label}
        </Typography>
        <Typography sx={{ fontWeight: view.status === 'missing' ? 400 : 700, fontSize: 14, color: style.valueColor }}>
          {view.displayValue}
        </Typography>
        <Chip label={view.statusLabel} color={style.chip} variant={style.variant} size="small" />
        <Box sx={{ flex: 1 }} />
        <Button size="small" onClick={() => setEditing((value) => !value)}>
          {editing ? '閉じる' : '修正'}
        </Button>
        <Button size="small" color="inherit" onClick={() => setDetails((value) => !value)}>
          補足
        </Button>
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

      <Collapse in={details} unmountOnExit>
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
