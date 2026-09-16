import { useEffect, useRef, useState } from 'react'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import ButtonGroup from '@mui/material/ButtonGroup'
import Chip from '@mui/material/Chip'
import Stack from '@mui/material/Stack'
import ToggleButton from '@mui/material/ToggleButton'
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup'
import Typography from '@mui/material/Typography'
import { api } from '../api'
import type { ItemDetail } from '../types'

const VARIANT_LABELS: Record<string, string> = {
  item: '商品画像',
  item_original: '商品画像(原寸)',
  item_enhanced: '商品画像(強調)',
  item_binary: '商品画像(2値)',
  page: '元ページ画像',
}

interface Props {
  detail: ItemDetail
}

export default function ImagePane({ detail }: Props) {
  const available = detail.images.available
  const [variant, setVariant] = useState<string>(available[0] ?? 'item')
  const [scale, setScale] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const dragging = useRef<{ x: number; y: number } | null>(null)

  useEffect(() => {
    // 器具を切り替えたら表示状態を初期化する（IDで対応付けているので表示順には依存しない）。
    setVariant(detail.images.available[0] ?? 'item')
    setScale(1)
    setOffset({ x: 0, y: 0 })
  }, [detail.id, detail.images.available])

  const fit = () => {
    setScale(1)
    setOffset({ x: 0, y: 0 })
  }

  const bbox = detail.images.bbox_pixels
  const showBbox = variant === 'page' && bbox && detail.images.page_width && detail.images.page_height

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ p: 1, borderBottom: 1, borderColor: 'divider', bgcolor: 'background.paper' }} flexWrap="wrap" useFlexGap>
        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
          {detail.display.marker}
        </Typography>
        <Chip label={`${detail.source_file ?? '元ファイル不明'} / ${detail.page ?? '?'}ページ${detail.item_no != null ? ` 器具${detail.item_no}` : ''}`} variant="outlined" />
        <ToggleButtonGroup
          exclusive
          size="small"
          value={variant}
          onChange={(_, value) => {
            if (value) {
              setVariant(value)
              fit()
            }
          }}
        >
          {available.map((name) => (
            <ToggleButton key={name} value={name} sx={{ py: 0.2 }}>
              {VARIANT_LABELS[name] ?? name}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
        <ButtonGroup size="small">
          <Button onClick={() => setScale((value) => Math.min(value * 1.25, 12))}>拡大</Button>
          <Button onClick={() => setScale((value) => Math.max(value / 1.25, 0.1))}>縮小</Button>
          <Button onClick={fit}>全体表示</Button>
        </ButtonGroup>
        <Chip label={`表示倍率 ${(scale * 100).toFixed(0)}%`} variant="outlined" />
      </Stack>

      {available.length === 0 ? (
        <Box sx={{ p: 2 }}>
          <Alert severity="warning">
            この対象には画像がありません（欠損）。他の器具の確認は続けられます。
            {detail.images.missing.length > 0 && ` 参照できなかったファイル: ${detail.images.missing.join(', ')}`}
          </Alert>
        </Box>
      ) : (
        <Box
          sx={{ flex: 1, minHeight: 0, overflow: 'hidden', bgcolor: 'grey.900', position: 'relative', cursor: dragging.current ? 'grabbing' : 'grab' }}
          onWheel={(event) => {
            const next = event.deltaY < 0 ? scale * 1.1 : scale / 1.1
            setScale(Math.min(Math.max(next, 0.1), 12))
          }}
          onMouseDown={(event) => {
            dragging.current = { x: event.clientX - offset.x, y: event.clientY - offset.y }
          }}
          onMouseMove={(event) => {
            if (!dragging.current) return
            setOffset({ x: event.clientX - dragging.current.x, y: event.clientY - dragging.current.y })
          }}
          onMouseUp={() => {
            dragging.current = null
          }}
          onMouseLeave={() => {
            dragging.current = null
          }}
        >
          <Box
            sx={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`,
              transformOrigin: 'center center',
              transition: dragging.current ? 'none' : 'transform 80ms linear',
            }}
          >
            <Box sx={{ position: 'relative', maxWidth: '100%', maxHeight: '100%' }}>
              <Box
                component="img"
                src={api.imageUrl(detail.id, variant)}
                alt={`${detail.display.marker} の${VARIANT_LABELS[variant] ?? variant}`}
                sx={{ maxWidth: '100%', maxHeight: '100%', display: 'block', objectFit: 'contain', userSelect: 'none' }}
                draggable={false}
              />
              {showBbox && bbox && (
                <Box
                  sx={{
                    position: 'absolute',
                    border: '2px solid',
                    borderColor: 'error.main',
                    left: `${(bbox[0] / (detail.images.page_width ?? 1)) * 100}%`,
                    top: `${(bbox[1] / (detail.images.page_height ?? 1)) * 100}%`,
                    width: `${((bbox[2] - bbox[0]) / (detail.images.page_width ?? 1)) * 100}%`,
                    height: `${((bbox[3] - bbox[1]) / (detail.images.page_height ?? 1)) * 100}%`,
                    pointerEvents: 'none',
                  }}
                />
              )}
            </Box>
          </Box>
        </Box>
      )}

      <Box sx={{ px: 1, py: 0.5, borderTop: 1, borderColor: 'divider', bgcolor: 'background.paper' }}>
        <Typography variant="caption" color="text.secondary">
          画像ID対応: {detail.id} / 表示中: {detail.images[variant as keyof typeof detail.images] as string | null ?? '—'}
          {variant === 'page' && bbox && '（赤枠は解析時の切り出し範囲）'}
        </Typography>
      </Box>
    </Box>
  )
}
