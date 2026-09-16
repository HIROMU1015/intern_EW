import { useEffect, useState } from 'react'
import Accordion from '@mui/material/Accordion'
import AccordionDetails from '@mui/material/AccordionDetails'
import AccordionSummary from '@mui/material/AccordionSummary'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Collapse from '@mui/material/Collapse'
import MenuItem from '@mui/material/MenuItem'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import ReadingFieldRow, { type SelectOption } from './ReadingFieldRow'
import { showValue } from '../lib/fieldState'
import { ORIGIN_LABELS, RELATION_HELP, RELATION_LABELS, WARNING_LABELS } from '../labels'
import type { Draft } from '../views/ReviewView'
import type { ItemDetail, RelationStatus } from '../types'

export const EXTRACTION_SURFACE = '#eef3f9'
const HEADER_BAND = '#d7e3f0'
const CARD_SX = { bgcolor: 'common.white', border: 1, borderColor: '#c9d6e4', borderRadius: 1, p: 1, mb: 1 }

const NUMERIC_FIELDS = new Set(['luminous_flux_lm', 'color_temperature_k', 'power_consumption_w', 'cri_ra'])
const MAIN_FIELDS = [
  'luminous_flux_lm',
  'color_temperature_k',
  'power_consumption_w',
  'voltage',
  'fixture_size',
  'cutout_size',
  'mounting_method',
  'waterproof',
  'dimming',
]
const FIELD_OPTIONS: Record<string, SelectOption[]> = {
  waterproof: [
    { value: 'unknown', label: '不明（条件に使わない）' },
    { value: 'none', label: '非対応・該当なし' },
    { value: 'damp', label: '防湿型' },
    { value: 'waterproof', label: '防雨型' },
    { value: 'damp_and_waterproof', label: '防湿・防雨型' },
  ],
  dimming: [
    { value: 'unknown', label: '不明（条件に使わない）' },
    { value: 'true', label: '調光' },
    { value: 'false', label: '非調光' },
  ],
}

interface Props {
  detail: ItemDetail
  draft: Draft
  searching: boolean
  onChange: (updater: (draft: Draft) => Draft) => void
  onResearch: () => void
}

export default function ExtractionPane({ detail, draft, searching, onChange, onResearch }: Props) {
  const [editingCodes, setEditingCodes] = useState(false)
  const [editingBasics, setEditingBasics] = useState(false)
  const [showRaw, setShowRaw] = useState(false)
  const corrections = draft.corrections

  useEffect(() => {
    // 器具を切り替えたら、開いていた編集欄は閉じた状態から始める（編集内容自体は保持される）。
    setEditingCodes(false)
    setEditingBasics(false)
    setShowRaw(false)
  }, [detail.id])

  const setSpec = (key: string, value: unknown) => {
    onChange((current) => ({
      ...current,
      corrections: { ...current.corrections, specifications: { ...(current.corrections.specifications ?? {}), [key]: value } },
    }))
  }
  const clearSpec = (key: string) => {
    onChange((current) => {
      const next = { ...(current.corrections.specifications ?? {}) }
      delete next[key]
      return { ...current, corrections: { ...current.corrections, specifications: next } }
    })
  }
  const setEntryCode = (suffix: string, patch: { code?: string; hinban?: string | null; kidou?: string | null }) => {
    onChange((current) => ({
      ...current,
      corrections: {
        ...current.corrections,
        entries: { ...(current.corrections.entries ?? {}), [suffix]: { ...(current.corrections.entries?.[suffix] ?? {}), ...patch } },
      },
    }))
  }

  const mainFields = detail.fields.filter((field) => MAIN_FIELDS.includes(field.key))
  const otherFields = detail.fields.filter((field) => !MAIN_FIELDS.includes(field.key))
  const codeEntries = detail.entries.filter((entry) => entry.kind === 'code')
  const categoryCorrected = corrections.category !== undefined
  const quantityText = draft.quantityValue ? `${draft.quantityValue}${draft.quantityUnit ?? ''}` : '未取得'

  return (
    <Box sx={{ bgcolor: EXTRACTION_SURFACE, minHeight: '100%' }}>
      <Stack
        direction="row"
        spacing={1}
        alignItems="center"
        flexWrap="wrap"
        useFlexGap
        sx={{ position: 'sticky', top: 0, zIndex: 2, px: 1, py: 0.75, bgcolor: HEADER_BAND, borderBottom: 1, borderColor: '#b9cade' }}
      >
        <Typography variant="subtitle2" sx={{ fontWeight: 800, color: '#1b3a5b' }}>
          読み取り結果
        </Typography>
        <Chip label={`器具名: ${detail.display.name}`} size="small" sx={{ bgcolor: 'common.white' }} />
        <Chip
          label={`出所: ${ORIGIN_LABELS[detail.display.name_origin] ?? '出所不明'}`}
          size="small"
          variant="outlined"
          sx={{ bgcolor: 'common.white' }}
        />
        <Box sx={{ flex: 1 }} />
        <Button variant="contained" disabled={searching} onClick={onResearch}>
          {searching ? '再検索中…' : 'この内容で再検索'}
        </Button>
      </Stack>

      <Box sx={{ p: 1 }}>
        {detail.warnings.length > 0 && (
          <Alert severity="warning" sx={{ mb: 1, py: 0.2 }}>
            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
              {detail.warnings.map((warning, index) => (
                <Tooltip key={`${warning.code}-${index}`} title={warning.message}>
                  <Chip label={WARNING_LABELS[warning.code] ?? warning.code} size="small" variant="outlined" />
                </Tooltip>
              ))}
            </Stack>
          </Alert>
        )}

        <Box sx={CARD_SX}>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.5 }}>
            <Typography variant="caption" sx={{ fontWeight: 700 }}>
              品番（{codeEntries.length ? `${codeEntries.length}件` : '読み取りなし・仕様検索'}）
            </Typography>
            <Box sx={{ flex: 1 }} />
            {codeEntries.length > 0 && (
              <Button size="small" onClick={() => setEditingCodes((value) => !value)}>
                {editingCodes ? '閉じる' : '修正'}
              </Button>
            )}
          </Stack>
          {codeEntries.map((entry) => {
            const override = corrections.entries?.[entry.suffix] ?? {}
            const effective = override.code ?? entry.code ?? ''
            const edited = override.code !== undefined && override.code !== entry.code
            return (
              <Box key={entry.suffix} sx={{ py: 0.5, borderTop: 1, borderColor: 'divider' }}>
                <Stack direction="row" spacing={1} alignItems="baseline" flexWrap="wrap" useFlexGap>
                  <Chip label={entry.label} size="small" color={entry.role === 'primary' ? 'primary' : 'default'} variant="outlined" />
                  <Typography sx={{ fontWeight: 700, fontSize: 14 }}>{effective || '未取得'}</Typography>
                  <Chip label={edited ? '修正済み' : '読取あり'} size="small" color={edited ? 'primary' : 'info'} variant={edited ? 'filled' : 'outlined'} />
                  {entry.code_note && <Chip label={`注記: ${entry.code_note}`} size="small" color="warning" variant="outlined" />}
                </Stack>
                <Typography variant="caption" color="text.secondary" component="div">
                  hinban {override.hinban ?? entry.hinban ?? '—'} / kidou {override.kidou ?? entry.kidou ?? '—'} ／ 原文 {entry.code_raw ?? '—'}（{entry.source_field}）
                </Typography>
                <Collapse in={editingCodes} unmountOnExit>
                  <Stack direction="row" spacing={0.5} sx={{ mt: 0.5 }}>
                    <TextField
                      label="品番"
                      value={override.code ?? entry.code ?? ''}
                      onChange={(event) => setEntryCode(entry.suffix, { code: event.target.value })}
                      sx={{ flex: 2, bgcolor: 'common.white' }}
                    />
                    <TextField
                      label="hinban"
                      value={override.hinban ?? entry.hinban ?? ''}
                      onChange={(event) => setEntryCode(entry.suffix, { hinban: event.target.value || null })}
                      sx={{ flex: 1, bgcolor: 'common.white' }}
                    />
                    <TextField
                      label="kidou"
                      value={override.kidou ?? entry.kidou ?? ''}
                      onChange={(event) => setEntryCode(entry.suffix, { kidou: event.target.value || null })}
                      sx={{ flex: 1, bgcolor: 'common.white' }}
                    />
                  </Stack>
                </Collapse>
              </Box>
            )
          })}
          {codeEntries.length > 1 && (
            <Box sx={{ mt: 1 }}>
              <TextField
                select
                fullWidth
                label="品番同士の関係（担当者の判断）"
                value={draft.relationStatus}
                onChange={(event) => onChange((current) => ({ ...current, relationStatus: event.target.value as RelationStatus }))}
                helperText={RELATION_HELP[draft.relationStatus]}
                sx={{ bgcolor: 'common.white' }}
              >
                {(['unresolved', 'components_of_one_fixture', 'multiple_fixtures'] as RelationStatus[]).map((value) => (
                  <MenuItem key={value} value={value}>
                    {RELATION_LABELS[value]}
                  </MenuItem>
                ))}
              </TextField>
              <Typography variant="caption" color="text.secondary">
                機械判定の根拠: {detail.relation.evidence.join(' / ')}
              </Typography>
            </Box>
          )}
        </Box>

        <Box sx={CARD_SX}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Typography variant="caption" sx={{ fontWeight: 700 }}>
              カテゴリ・数量
            </Typography>
            <Box sx={{ flex: 1 }} />
            <Button size="small" onClick={() => setEditingBasics((value) => !value)}>
              {editingBasics ? '閉じる' : '修正'}
            </Button>
          </Stack>
          <Stack direction="row" spacing={1} alignItems="baseline" flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
            <Typography variant="caption" sx={{ minWidth: 92, color: 'text.secondary' }}>
              カテゴリ
            </Typography>
            <Typography sx={{ fontWeight: 700, fontSize: 14, color: detail.display.category_raw || categoryCorrected ? 'text.primary' : 'text.disabled' }}>
              {corrections.category ?? detail.display.category_raw ?? '未取得'}
            </Typography>
            <Chip
              label={categoryCorrected ? '修正済み' : detail.display.category_raw ? '読取あり' : '未取得'}
              size="small"
              color={categoryCorrected ? 'primary' : detail.display.category_raw ? 'info' : 'default'}
              variant={categoryCorrected ? 'filled' : 'outlined'}
            />
          </Stack>
          <Stack direction="row" spacing={1} alignItems="baseline" flexWrap="wrap" useFlexGap>
            <Typography variant="caption" sx={{ minWidth: 92, color: 'text.secondary' }}>
              数量
            </Typography>
            <Typography sx={{ fontWeight: 700, fontSize: 14, color: draft.quantityValue ? 'text.primary' : 'text.disabled' }}>
              {quantityText}
            </Typography>
            <Chip label={draft.quantityValue ? '読取あり' : '未取得'} size="small" color={draft.quantityValue ? 'info' : 'default'} variant="outlined" />
            <Typography variant="caption" color="text.secondary">
              原文: {showValue(detail.quantity.raw) || '—'} / 正規化カテゴリ: {detail.display.category_normalized ?? '—'}
            </Typography>
          </Stack>
          <Collapse in={editingBasics} unmountOnExit>
            <Stack direction="row" spacing={0.5} sx={{ mt: 1 }}>
              <TextField
                label="カテゴリ（担当者の修正）"
                placeholder={detail.display.category_raw ?? '未取得'}
                value={corrections.category ?? ''}
                onChange={(event) =>
                  onChange((current) => ({ ...current, corrections: { ...current.corrections, category: event.target.value || null } }))
                }
                sx={{ flex: 2, bgcolor: 'common.white' }}
              />
              <TextField
                label="数量"
                type="number"
                value={draft.quantityValue}
                onChange={(event) => onChange((current) => ({ ...current, quantityValue: event.target.value }))}
                sx={{ flex: 1, bgcolor: 'common.white' }}
              />
              <TextField
                label="単位"
                value={draft.quantityUnit}
                onChange={(event) => onChange((current) => ({ ...current, quantityUnit: event.target.value }))}
                sx={{ flex: 1, bgcolor: 'common.white' }}
              />
            </Stack>
          </Collapse>
        </Box>

        <Box sx={{ ...CARD_SX, p: 0, overflow: 'hidden' }}>
          <Typography variant="caption" sx={{ fontWeight: 700, display: 'block', px: 1, py: 0.5, bgcolor: '#f3f6fa', borderBottom: 1, borderColor: 'divider' }}>
            主な読み取り項目
          </Typography>
          {mainFields.map((field) => (
            <ReadingFieldRow
              key={`${detail.id}:${field.key}`}
              field={field}
              corrections={corrections}
              numeric={NUMERIC_FIELDS.has(field.key)}
              options={FIELD_OPTIONS[field.key]}
              onSet={(value) => setSpec(field.key, value)}
              onClear={() => clearSpec(field.key)}
            />
          ))}
        </Box>

        <Accordion disableGutters sx={{ bgcolor: 'common.white', border: 1, borderColor: '#c9d6e4' }}>
          <AccordionSummary>
            <Typography variant="caption" sx={{ fontWeight: 700 }}>
              補助項目・読み取り原文・元JSON
            </Typography>
          </AccordionSummary>
          <AccordionDetails sx={{ p: 0 }}>
            {otherFields.map((field) => (
              <ReadingFieldRow
                key={`${detail.id}:${field.key}`}
                field={field}
                corrections={corrections}
                numeric={NUMERIC_FIELDS.has(field.key)}
                onSet={(value) => setSpec(field.key, value)}
                onClear={() => clearSpec(field.key)}
              />
            ))}
            <Box sx={{ p: 1 }}>
              {detail.uncertain_fields.length > 0 && (
                <Alert severity="info" sx={{ mb: 1 }}>
                  解析側の不確かな項目: {detail.uncertain_fields.join(', ')}
                </Alert>
              )}
              {[...detail.recognition_notes, ...detail.normalized_notes].map((note, index) => (
                <Typography key={index} variant="caption" component="div">
                  ・{note}
                </Typography>
              ))}
              <Typography variant="caption" component="div" sx={{ mt: 1, whiteSpace: 'pre-wrap' }}>
                読み取り原文テキスト: {detail.raw_text || '—'}
              </Typography>
              <Button sx={{ mt: 1 }} onClick={() => setShowRaw((value) => !value)}>
                {showRaw ? '元JSONを隠す' : '元JSONを表示'}
              </Button>
              {showRaw && (
                <Box component="pre" sx={{ fontSize: 10, overflow: 'auto', maxHeight: 240, bgcolor: 'grey.100', p: 1 }}>
                  {JSON.stringify(detail.source_json, null, 2)}
                </Box>
              )}
            </Box>
          </AccordionDetails>
        </Accordion>
      </Box>
    </Box>
  )
}
