import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Typography from '@mui/material/Typography'
import { AVAILABILITY_LABELS } from '../labels'
import type { Candidate, ItemDetail } from '../types'

const ROWS: { key: string; label: string; get: (candidate: Candidate) => string }[] = [
  { key: 'code', label: '品番', get: (candidate) => candidate.record.full_code || candidate.record.hinban },
  { key: 'id', label: 'DBレコードID', get: (candidate) => candidate.record.id },
  { key: 'name', label: '商品名(key)', get: (candidate) => candidate.record.key || candidate.record.view_key || '—' },
  { key: 'group', label: '器具分類', get: (candidate) => candidate.record.kigugroup || candidate.record.t_kigugroup || '—' },
  { key: 'akarusa', label: '明るさ', get: (candidate) => candidate.record.t_akarusa || '—' },
  { key: 'size', label: '器具寸法', get: (candidate) => candidate.record.kigusize || '—' },
  { key: 'ana', label: '埋込穴', get: (candidate) => candidate.record.umekomi_ana || '—' },
  { key: 'toritsuke', label: '取付', get: (candidate) => candidate.record.t_toritsuke || '—' },
  { key: 'wet', label: '防湿・防雨', get: (candidate) => candidate.record.boushitsu_bouu || '—' },
  { key: 'kinou', label: '機能', get: (candidate) => candidate.record.t_kinou || '—' },
  { key: 'availability', label: '生産状態', get: (candidate) => AVAILABILITY_LABELS[candidate.record.availability] ?? candidate.record.availability },
  { key: 'price', label: '税抜価格', get: (candidate) => (candidate.record.price_zeinuki != null ? String(candidate.record.price_zeinuki) : '—') },
  { key: 'score', label: '順位付けスコア', get: (candidate) => String(candidate.score) },
  { key: 'conflicts', label: '相違点', get: (candidate) => (candidate.conflicts.length ? candidate.conflicts.map((value) => value.field).join(', ') : 'なし') },
]

interface Props {
  open: boolean
  candidates: Candidate[]
  detail: ItemDetail
  onClose: () => void
}

export default function CompareDialog({ open, candidates, detail, onClose }: Props) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle sx={{ py: 1 }}>
        主要仕様の比較 — {detail.display.marker}
        <Chip label={`${candidates.length}件`} sx={{ ml: 1 }} />
      </DialogTitle>
      <DialogContent dividers>
        <Typography variant="caption" color="text.secondary" component="div" sx={{ mb: 1 }}>
          スコアは順位付けの値です。正解率や確率ではありません。正式後継品・類似品の区別は、根拠となるデータがないため表示していません。
        </Typography>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700 }}>項目</TableCell>
              {candidates.map((candidate) => (
                <TableCell key={candidate.record.id} sx={{ fontWeight: 700 }}>
                  {candidate.record.full_code || candidate.record.hinban}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {ROWS.map((row) => {
              const values = candidates.map((candidate) => row.get(candidate))
              const differs = new Set(values).size > 1
              return (
                <TableRow key={row.key}>
                  <TableCell sx={{ fontWeight: 600, bgcolor: differs ? 'warning.light' : undefined }}>
                    {row.label}
                    {differs && <Chip label="差異" sx={{ ml: 0.5 }} />}
                  </TableCell>
                  {values.map((value, index) => (
                    <TableCell key={index} sx={{ fontSize: 12 }}>
                      {value}
                    </TableCell>
                  ))}
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>閉じる</Button>
      </DialogActions>
    </Dialog>
  )
}
