import { useEffect, useRef, useState } from 'react'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import ButtonGroup from '@mui/material/ButtonGroup'
import Chip from '@mui/material/Chip'
import Dialog from '@mui/material/Dialog'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Stack from '@mui/material/Stack'
import ToggleButton from '@mui/material/ToggleButton'
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup'
import Typography from '@mui/material/Typography'
import { api } from '../api'
import type { ItemDetail } from '../types'

/**
 * 画面で切り替えられる画像。
 * item は解析に使った推奨画像（強調版が選ばれていることもある）、page は切り出し範囲つきの元ページ。
 * 原寸・強調・2値はこの2つと内容が重なるため、切替には出さない（APIは引き続き返す）。
 */
const VARIANT_LABELS: Record<string, string> = {
  item: '商品画像',
  page: '元ページ画像',
}
const VISIBLE_VARIANTS = Object.keys(VARIANT_LABELS)

/**
 * 通常表示のビューア高さ。中央カラムを占有しないように抑える。
 * 画面が低いノートPCでは、その他の仕様の表示領域を確保するためさらに縮める。
 */
const COMPACT_HEIGHT_SX = {
  height: 260,
  '@media (max-height: 900px)': { height: 220 },
  '@media (max-height: 760px)': { height: 190 },
} as const

interface Props {
  detail: ItemDetail
}

export default function ImagePane({ detail }: Props) {
  const available = detail.images.available.filter((name) => VISIBLE_VARIANTS.includes(name))
  const [variant, setVariant] = useState<string>(available[0] ?? 'item')
  const [zoomOpen, setZoomOpen] = useState(false)
  const [scale, setScale] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const dragging = useRef<{ x: number; y: number } | null>(null)

  useEffect(() => {
    // 器具を切り替えたら表示状態を初期化する（IDで対応付けているので表示順には依存しない）。
    setVariant(detail.images.available.find((name) => VISIBLE_VARIANTS.includes(name)) ?? 'item')
    setZoomOpen(false)
    setScale(1)
    setOffset({ x: 0, y: 0 })
  }, [detail.id, detail.images.available])

  /** 全体表示：画像全体が収まる倍率（等倍）に戻し、ドラッグで動かした位置も中央へ戻す。 */
  const fit = () => {
    setScale(1)
    setOffset({ x: 0, y: 0 })
  }

  const bbox = detail.images.bbox_pixels
  const showBbox = variant === 'page' && bbox && detail.images.page_width && detail.images.page_height

  const bboxOverlay = showBbox && bbox && (
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
  )

  if (available.length === 0) {
    return (
      <Box sx={{ p: 1 }}>
        <Alert severity="warning">
          この対象には画像がありません（欠損）。他の器具の確認は続けられます。
          {detail.images.missing.length > 0 && ` 参照できなかったファイル: ${detail.images.missing.join(', ')}`}
        </Alert>
      </Box>
    )
  }

  return (
    <Box
      sx={{
        p: 1,
        display: 'flex',
        flexDirection: 'column',
        gap: 0.5,
        minWidth: 0,
        '@media (max-height: 900px)': { p: 0.5, gap: 0.25 },
      }}
    >
      <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap" useFlexGap>
        <Typography variant="caption" sx={{ fontWeight: 700 }}>
          原図
        </Typography>
        <Chip
          label={`${detail.source_file ?? '元ファイル不明'} / ${detail.page ?? '?'}ページ${detail.item_no != null ? ` 器具${detail.item_no}` : ''}`}
          variant="outlined"
        />
        <Box sx={{ flex: 1 }} />
        <Button
          variant="outlined"
          onClick={() => {
            fit()
            setZoomOpen(true)
          }}
        >
          拡大表示
        </Button>
      </Stack>

      {/* 通常時は固定高さの小さなビューア。黒い余白を大きく残さない。 */}
      <Box
        sx={{
          ...COMPACT_HEIGHT_SX,
          bgcolor: 'grey.900',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
          cursor: 'zoom-in',
        }}
        onClick={() => {
          fit()
          setZoomOpen(true)
        }}
      >
        <Box sx={{ position: 'relative', maxWidth: '100%', maxHeight: '100%', display: 'flex' }}>
          <Box
            component="img"
            src={api.imageUrl(detail.id, variant)}
            alt={`${detail.display.marker} の${VARIANT_LABELS[variant] ?? variant}`}
            sx={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain', display: 'block', userSelect: 'none' }}
            draggable={false}
          />
          {bboxOverlay}
        </Box>
      </Box>

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
        sx={{ flexWrap: 'wrap' }}
      >
        {available.map((name) => (
          <ToggleButton key={name} value={name} sx={{ py: 0.2 }}>
            {VARIANT_LABELS[name] ?? name}
          </ToggleButton>
        ))}
      </ToggleButtonGroup>

      {/* 大きく見るのはモーダルの中だけ。拡大・縮小・ドラッグ移動もここで行う。 */}
      <Dialog open={zoomOpen} onClose={() => setZoomOpen(false)} fullWidth maxWidth="xl">
        <DialogTitle sx={{ py: 1 }}>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
              {detail.display.marker}
            </Typography>
            <Chip
              label={`${detail.source_file ?? '元ファイル不明'} / ${detail.page ?? '?'}ページ${detail.item_no != null ? ` 器具${detail.item_no}` : ''}`}
              variant="outlined"
            />
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
            <Box sx={{ flex: 1 }} />
            <Button onClick={() => setZoomOpen(false)}>閉じる</Button>
          </Stack>
        </DialogTitle>
        <DialogContent sx={{ p: 0 }}>
          <Box
            sx={{
              height: '72vh',
              overflow: 'hidden',
              bgcolor: 'grey.900',
              position: 'relative',
              cursor: dragging.current ? 'grabbing' : 'grab',
            }}
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
                // モーダルでは画像をビューアの中央に置き、拡大・縮小も中心を基準にする。
                alignItems: 'center',
                justifyContent: 'center',
                p: 1,
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
                  sx={{ maxWidth: '100%', maxHeight: '70vh', display: 'block', objectFit: 'contain', userSelect: 'none' }}
                  draggable={false}
                />
                {bboxOverlay}
              </Box>
            </Box>
          </Box>
          <Box sx={{ px: 1, py: 0.5, borderTop: 1, borderColor: 'divider' }}>
            <Typography variant="caption" color="text.secondary">
              画像ID対応: {detail.id} / 表示中: {(detail.images[variant as keyof typeof detail.images] as string | null) ?? '—'}
              {variant === 'page' && bbox && '（赤枠は解析時の切り出し範囲）'}
            </Typography>
          </Box>
        </DialogContent>
      </Dialog>
    </Box>
  )
}
