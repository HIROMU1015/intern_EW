import { Fragment, useEffect, useState } from 'react'
import Accordion from '@mui/material/Accordion'
import AccordionDetails from '@mui/material/AccordionDetails'
import AccordionSummary from '@mui/material/AccordionSummary'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import Chip from '@mui/material/Chip'
import Collapse from '@mui/material/Collapse'
import MenuItem from '@mui/material/MenuItem'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import ReadingFieldRow, { type SelectOption } from './ReadingFieldRow'
import { showValue } from '../lib/fieldState'
import { RELATION_HELP, RELATION_LABELS, WARNING_LABELS } from '../labels'
import type { Draft } from '../views/ReviewView'
import type { ItemDetail, RelationStatus } from '../types'

export const EXTRACTION_SURFACE = '#eef3f9'
const CARD_SX = { bgcolor: 'common.white', border: 1, borderColor: '#c9d6e4', borderRadius: 1, p: 1, mb: 1 }
/** ラベルと値を左右に並べる。行間を詰めて縦幅を使わない。 */
const LABEL_GRID_SX = {
  display: 'grid',
  gridTemplateColumns: 'max-content 1fr',
  columnGap: 1,
  rowGap: 0.25,
  alignItems: 'baseline',
} as const

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
  /** summary: 原図の右に置く基本情報カード。specs: その下に全幅で置く仕様と詳細。 */
  section: 'summary' | 'specs'
  onChange: (updater: (draft: Draft) => Draft) => void
  onResearch: () => void
}

export default function ExtractionPane({ detail, draft, searching, section, onChange, onResearch }: Props) {
  const [editing, setEditing] = useState(false)
  const [showRaw, setShowRaw] = useState(false)
  const corrections = draft.corrections

  useEffect(() => {
    // 器具を切り替えたら、開いていた編集欄は閉じた状態から始める（編集内容自体は保持される）。
    setEditing(false)
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
  const disabledSpecs = corrections.spec_search_disabled ?? []
  /** 読み取り値は残したまま、検索条件として使うかだけを切り替える。 */
  const toggleSearchUse = (key: string, use: boolean) => {
    onChange((current) => {
      const currentList = current.corrections.spec_search_disabled ?? []
      const next = use ? currentList.filter((value) => value !== key) : [...new Set([...currentList, key])]
      return { ...current, corrections: { ...current.corrections, spec_search_disabled: next } }
    })
  }
  const quantityText = draft.quantityValue ? `${draft.quantityValue}${draft.quantityUnit ?? ''}` : '未取得'

  if (section === 'summary') {
    return (
      <Box
        sx={{
          bgcolor: EXTRACTION_SURFACE,
          height: '100%',
          p: 1,
          // 画面が低いノートPCでは、その他の仕様の領域を残すためさらに詰める。
          '@media (max-height: 900px)': {
            p: 0.5,
            '& .summary-card': { p: 0.5 },
            '& .summary-strong': { fontSize: 14 },
          },
        }}
      >
        {/* 管理記号・器具名・品番・カテゴリ・数量を1枚にまとめる。枠線は外周だけ。 */}
        <Box className="summary-card" sx={{ bgcolor: 'common.white', border: 1, borderColor: '#c9d6e4', borderRadius: 1, p: 1 }}>
          <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mb: 0.5 }}>
            <Typography variant="caption" sx={{ fontWeight: 800, color: '#1b3a5b' }}>
              基本情報
            </Typography>
            <Box sx={{ flex: 1 }} />
            <Button onClick={() => setEditing((value) => !value)}>{editing ? '閉じる' : '修正'}</Button>
            <Button variant="contained" disabled={searching} onClick={onResearch}>
              {searching ? '再検索中…' : 'この内容で再検索'}
            </Button>
          </Stack>

          <Box sx={LABEL_GRID_SX}>
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>
              管理記号
            </Typography>
            <Typography className="summary-strong" sx={{ fontWeight: 800, fontSize: 15 }}>
              {detail.display.marker}
            </Typography>

            <Typography variant="caption" sx={{ color: 'text.secondary' }}>
              器具名
            </Typography>
            <Typography sx={{ fontWeight: 700, fontSize: 14 }}>{detail.display.name}</Typography>
          </Box>

          {/* 品番。主品番と構成品はバックエンドが付けた分類ラベルで区別する。 */}
          <Typography variant="caption" sx={{ fontWeight: 700, display: 'block', mt: 0.75 }}>
            品番{codeEntries.length === 0 && '（読み取りなし・仕様検索）'}
          </Typography>
          {codeEntries.length === 0 ? (
            <Typography sx={{ fontWeight: 700, fontSize: 14, color: 'text.disabled' }}>未取得</Typography>
          ) : (
            <Box sx={LABEL_GRID_SX}>
              {codeEntries.map((entry) => {
                const override = corrections.entries?.[entry.suffix] ?? {}
                const effective = override.code ?? entry.code ?? ''
                const edited = override.code !== undefined && override.code !== entry.code
                return (
                  <Fragment key={entry.suffix}>
                    <Typography
                      variant="caption"
                      sx={{
                        color: entry.role === 'primary' ? 'primary.dark' : 'text.secondary',
                        fontWeight: entry.role === 'primary' ? 700 : 400,
                      }}
                    >
                      {entry.label}
                    </Typography>
                    <Stack direction="row" spacing={0.5} alignItems="baseline" flexWrap="wrap" useFlexGap>
                      <Typography className="summary-strong" sx={{ fontWeight: 800, fontSize: 16, letterSpacing: 0.2 }}>
                        {effective || '未取得'}
                      </Typography>
                      {edited && <Chip label="修正済み" color="primary" />}
                      {!effective && <Chip label="未取得" />}
                      {entry.code_note && <Chip label={`注記: ${entry.code_note}`} color="warning" variant="outlined" />}
                    </Stack>
                  </Fragment>
                )
              })}
            </Box>
          )}

          {/* カテゴリと数量は最下部で横並び。 */}
          <Stack direction="row" spacing={2} alignItems="baseline" sx={{ mt: 0.75 }} flexWrap="wrap" useFlexGap>
            <Stack direction="row" spacing={0.5} alignItems="baseline" sx={{ flex: '2 1 160px', minWidth: 0 }} flexWrap="wrap" useFlexGap>
              <Tooltip title="カテゴリを検索条件に使う">
                <Box component="span" sx={{ display: 'inline-flex' }}>
                  <Checkbox
                    size="small"
                    sx={{ p: 0 }}
                    checked={!disabledSpecs.includes('category')}
                    onChange={(event) => toggleSearchUse('category', event.target.checked)}
                    inputProps={{ 'aria-label': 'カテゴリを検索条件に使う' }}
                  />
                </Box>
              </Tooltip>
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                カテゴリ
              </Typography>
              <Typography
                sx={{
                  fontWeight: 700,
                  fontSize: 14,
                  color: detail.display.category_raw || categoryCorrected ? 'text.primary' : 'text.disabled',
                }}
              >
                {corrections.category ?? detail.display.category_raw ?? '未取得'}
              </Typography>
              {categoryCorrected && <Chip label="修正済み" color="primary" />}
              {!categoryCorrected && !detail.display.category_raw && <Chip label="未取得" />}
            </Stack>
            <Stack direction="row" spacing={0.5} alignItems="baseline" sx={{ flex: '1 1 100px', minWidth: 0 }} flexWrap="wrap" useFlexGap>
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                数量
              </Typography>
              <Typography
                className="summary-strong"
                sx={{ fontWeight: 800, fontSize: 15, color: draft.quantityValue ? 'text.primary' : 'text.disabled' }}
              >
                {quantityText}
              </Typography>
              {!draft.quantityValue && <Chip label="未取得" />}
            </Stack>
          </Stack>

          {/* 修正はカードにひとつ。開いたときだけ各項目の入力欄を出す。 */}
          <Collapse in={editing} unmountOnExit>
            <Box sx={{ mt: 1, pt: 1, borderTop: 1, borderColor: 'divider' }}>
              {codeEntries.map((entry) => {
                const override = corrections.entries?.[entry.suffix] ?? {}
                return (
                  <Box key={entry.suffix} sx={{ mb: 1 }}>
                    <Typography variant="caption" color="text.secondary" component="div">
                      {entry.label} の原文 {entry.code_raw ?? '—'}（{entry.source_field}）
                    </Typography>
                    <Stack direction="row" spacing={0.5} sx={{ mt: 0.5 }} flexWrap="wrap" useFlexGap>
                      <TextField
                        label={`品番（${entry.label}）`}
                        value={override.code ?? entry.code ?? ''}
                        onChange={(event) => setEntryCode(entry.suffix, { code: event.target.value })}
                        sx={{ flex: '2 1 160px', bgcolor: 'common.white' }}
                      />
                      <TextField
                        label="hinban"
                        value={override.hinban ?? entry.hinban ?? ''}
                        onChange={(event) => setEntryCode(entry.suffix, { hinban: event.target.value || null })}
                        sx={{ flex: '1 1 90px', bgcolor: 'common.white' }}
                      />
                      <TextField
                        label="kidou"
                        value={override.kidou ?? entry.kidou ?? ''}
                        onChange={(event) => setEntryCode(entry.suffix, { kidou: event.target.value || null })}
                        sx={{ flex: '1 1 90px', bgcolor: 'common.white' }}
                      />
                    </Stack>
                  </Box>
                )
              })}
              <Typography variant="caption" color="text.secondary" component="div">
                数量の原文: {showValue(detail.quantity.raw) || '—'} / 正規化カテゴリ: {detail.display.category_normalized ?? '—'}
              </Typography>
              <Stack direction="row" spacing={0.5} sx={{ mt: 0.5 }} flexWrap="wrap" useFlexGap>
                <TextField
                  label="カテゴリ（担当者の修正）"
                  placeholder={detail.display.category_raw ?? '未取得'}
                  value={corrections.category ?? ''}
                  onChange={(event) =>
                    onChange((current) => ({ ...current, corrections: { ...current.corrections, category: event.target.value || null } }))
                  }
                  sx={{ flex: '2 1 160px', bgcolor: 'common.white' }}
                />
                <TextField
                  label="数量"
                  type="number"
                  value={draft.quantityValue}
                  onChange={(event) => onChange((current) => ({ ...current, quantityValue: event.target.value }))}
                  sx={{ flex: '1 1 80px', bgcolor: 'common.white' }}
                />
                <TextField
                  label="単位"
                  value={draft.quantityUnit}
                  onChange={(event) => onChange((current) => ({ ...current, quantityUnit: event.target.value }))}
                  sx={{ flex: '1 1 80px', bgcolor: 'common.white' }}
                />
              </Stack>
            </Box>
          </Collapse>
        </Box>
      </Box>
    )
  }

  // section === 'specs': 中央カラムの全幅で、その他の読み取り仕様と詳細を出す。
  return (
    <Box sx={{ bgcolor: EXTRACTION_SURFACE, minHeight: '100%' }}>
      <Box sx={{ p: 1 }}>
        {detail.warnings.length > 0 && (
          <Alert severity="warning" sx={{ mb: 1, py: 0.2 }}>
            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
              {detail.warnings.map((warning, index) => (
                <Tooltip key={`${warning.code}-${index}`} title={warning.message}>
                  <Chip label={WARNING_LABELS[warning.code] ?? warning.code} variant="outlined" />
                </Tooltip>
              ))}
            </Stack>
          </Alert>
        )}

        <Box sx={{ ...CARD_SX, p: 0, overflow: 'hidden' }}>
          <Typography
            variant="caption"
            sx={{ fontWeight: 700, display: 'block', px: 1, py: 0.5, bgcolor: '#f3f6fa', borderBottom: 1, borderColor: 'divider' }}
          >
            商品の絞り込み条件
          </Typography>
          <Typography variant="caption" sx={{ display: 'block', px: 1, pb: 0.5, color: 'text.secondary' }}>
            使いたい条件にチェックしてください
          </Typography>
          {/* 1項目1行。画面幅にかかわらず2列には戻さない。
              内部スクロールは持たせず、収まらない分は中央カラムのスクロールで見る。 */}
          <Box
            sx={{
              '@media (max-height: 900px)': {
                '& .reading-field-row': { py: 0.25 },
              },
            }}
          >
            {mainFields.map((field) => (
              <ReadingFieldRow
                key={`${detail.id}:${field.key}`}
                field={field}
                corrections={corrections}
                numeric={NUMERIC_FIELDS.has(field.key)}
                options={FIELD_OPTIONS[field.key]}
                supplement={false}
                searchEnabled={!disabledSpecs.includes(field.key)}
                onToggleSearch={(next) => toggleSearchUse(field.key, next)}
                onSet={(value) => setSpec(field.key, value)}
                onClear={() => clearSpec(field.key)}
              />
            ))}
          </Box>
        </Box>

        {/* 内部フィールド名・原文・品番同士の関係・元JSONは、開いたときだけ見せる。 */}
        <Accordion disableGutters sx={{ bgcolor: 'common.white', border: 1, borderColor: '#c9d6e4' }}>
          <AccordionSummary>
            <Typography variant="caption" sx={{ fontWeight: 700 }}>
              詳細（補助項目・読み取り原文・品番同士の関係・元JSON）
            </Typography>
          </AccordionSummary>
          <AccordionDetails sx={{ p: 0 }}>
            {codeEntries.length > 1 && (
              <Box sx={{ p: 1, borderBottom: 1, borderColor: 'divider' }}>
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

            {codeEntries.length > 0 && (
              <Box sx={{ p: 1, borderBottom: 1, borderColor: 'divider' }}>
                <Typography variant="caption" sx={{ fontWeight: 700 }} component="div">
                  品番の内訳
                </Typography>
                {codeEntries.map((entry) => {
                  const override = corrections.entries?.[entry.suffix] ?? {}
                  return (
                    <Typography key={entry.suffix} variant="caption" color="text.secondary" component="div">
                      {entry.label}: hinban {override.hinban ?? entry.hinban ?? '—'} / kidou {override.kidou ?? entry.kidou ?? '—'} ／ 原文{' '}
                      {entry.code_raw ?? '—'}（{entry.source_field}）
                    </Typography>
                  )
                })}
              </Box>
            )}

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
