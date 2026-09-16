import { useCallback, useEffect, useState } from 'react'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Chip from '@mui/material/Chip'
import Divider from '@mui/material/Divider'
import LinearProgress from '@mui/material/LinearProgress'
import Stack from '@mui/material/Stack'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Typography from '@mui/material/Typography'
import { api } from '../api'
import { WARNING_LABELS } from '../labels'
import type { ProjectInfo, SourceInfo } from '../types'

interface Props {
  activeProject: ProjectInfo | null
  onOpen: (project: ProjectInfo) => void
  onError: (message: string) => void
}

export default function ImportView({ activeProject, onOpen, onError }: Props) {
  const [sources, setSources] = useState<SourceInfo[]>([])
  const [projects, setProjects] = useState<ProjectInfo[]>([])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const reload = useCallback(async () => {
    try {
      const [{ sources: loadedSources }, { projects: loadedProjects }] = await Promise.all([api.sources(), api.projects()])
      setSources(loadedSources)
      setProjects(loadedProjects)
    } catch (reason) {
      onError((reason as Error).message)
    }
  }, [onError])

  useEffect(() => {
    void reload()
  }, [reload])

  const importSource = async (source: SourceInfo) => {
    setBusy(true)
    setMessage(null)
    try {
      const result = await api.createProject(source.key)
      setMessage(result.created ? '取り込みました。' : (result.message ?? '既存の案件を再開します。'))
      await reload()
      onOpen(result.project)
    } catch (reason) {
      onError((reason as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Box sx={{ p: 2, height: '100%', overflow: 'auto' }}>
      {busy && <LinearProgress sx={{ mb: 1 }} />}
      {message && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setMessage(null)}>
          {message}
        </Alert>
      )}

      <Typography variant="h6" gutterBottom>
        取り込み元（設定に登録されたローカルデータのみ）
      </Typography>
      <Stack spacing={1} sx={{ mb: 3 }}>
        {sources.map((source) => (
          <Card key={source.key} variant="outlined">
            <CardContent sx={{ py: 1.5 }}>
              <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.5 }}>
                <Typography sx={{ fontWeight: 600 }}>{source.label}</Typography>
                <Chip label={source.format} variant="outlined" />
                <Chip label={source.available ? '参照可能' : '見つからない'} color={source.available ? 'success' : 'error'} />
                <Box sx={{ flex: 1 }} />
                <Button variant="contained" disabled={!source.available || busy} onClick={() => importSource(source)}>
                  取り込む / 再開
                </Button>
              </Stack>
              <Typography variant="caption" color="text.secondary" component="div">
                解析JSON: {source.analysis_path}
              </Typography>
              <Typography variant="caption" color="text.secondary" component="div">
                マニフェスト: {source.manifest_path ?? '未設定'} / 画像: {source.image_root ?? '未設定'}
              </Typography>
              {source.note && (
                <Typography variant="caption" color="text.secondary" component="div">
                  {source.note}
                </Typography>
              )}
              {!source.available && (
                <Alert severity="warning" sx={{ mt: 1 }}>
                  見つからないパス: {source.missing_paths.join(' / ')}
                </Alert>
              )}
            </CardContent>
          </Card>
        ))}
      </Stack>

      <Typography variant="h6" gutterBottom>
        取り込み済みの案件
      </Typography>
      <Stack spacing={2}>
        {projects.length === 0 && <Typography color="text.secondary">まだ案件がありません。</Typography>}
        {projects.map((project) => {
          const report = project.ingest_report
          return (
            <Card key={project.id} variant="outlined">
              <CardContent>
                <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }} flexWrap="wrap" useFlexGap>
                  <Typography sx={{ fontWeight: 600 }}>{project.name}</Typography>
                  <Chip label={`解析済み対象 ${project.item_count}件`} color="primary" variant="outlined" />
                  <Chip label={`未確認 ${project.status_counts.unconfirmed}`} />
                  <Chip label={`保留 ${project.status_counts.on_hold}`} color="warning" variant="outlined" />
                  <Chip label={`確認済み ${project.status_counts.confirmed}`} color="success" variant="outlined" />
                  <Chip label={`再確認が必要 ${project.status_counts.needs_recheck}`} color="error" variant="outlined" />
                  <Box sx={{ flex: 1 }} />
                  {activeProject?.id === project.id && <Chip label="選択中" color="info" />}
                  <Button variant="outlined" onClick={() => onOpen(project)}>
                    確認画面を開く
                  </Button>
                </Stack>
                <Typography variant="caption" color="text.secondary" component="div">
                  取り込み日時: {project.created_at} / 解析JSON: {project.analysis_path}
                </Typography>
                <Typography variant="caption" color="text.secondary" component="div">
                  解析JSONのSHA-256: {project.analysis_sha256}
                </Typography>
                <Alert severity="info" sx={{ my: 1 }}>
                  {report.scope_note}
                </Alert>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
                  <Chip label={`取り込み件数 ${report.analyzed_item_count}`} />
                  <Chip label={`画像欠損 ${report.image_missing_count}`} color={report.image_missing_count ? 'warning' : 'default'} />
                  <Chip label={`マニフェスト枠数 ${report.manifest_frame_total}`} variant="outlined" />
                  <Chip label={`未解析の枠（枠IDで照合） ${report.frames_without_analysis_count}`} variant="outlined" />
                  <Chip label={`形式: ${report.detected_format}`} variant="outlined" />
                </Stack>
                <Divider sx={{ my: 1 }} />
                <Typography variant="subtitle2">取り込み警告</Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
                  {Object.entries(report.warning_counts).map(([code, count]) => (
                    <Chip key={code} label={`${WARNING_LABELS[code] ?? code}: ${count}`} variant="outlined" />
                  ))}
                </Stack>
                <Typography variant="subtitle2">ページ別の対応（枠IDで突き合わせ）</Typography>
                <Box sx={{ maxHeight: 220, overflow: 'auto' }}>
                  <Table size="small" stickyHeader>
                    <TableHead>
                      <TableRow>
                        <TableCell>元ファイル</TableCell>
                        <TableCell>ページ</TableCell>
                        <TableCell>処理経路</TableCell>
                        <TableCell align="right">マニフェスト枠数</TableCell>
                        <TableCell align="right">解析済み</TableCell>
                        <TableCell>未解析の枠番号</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {report.manifest_pages.map((page) => (
                        <TableRow key={`${page.source_file}-${page.page}`}>
                          <TableCell>{page.source_file}</TableCell>
                          <TableCell>{page.page}</TableCell>
                          <TableCell>{page.route}</TableCell>
                          <TableCell align="right">{page.manifest_frame_count}</TableCell>
                          <TableCell align="right">{page.analyzed_item_count}</TableCell>
                          <TableCell sx={{ fontSize: 11 }}>
                            {page.frames_without_analysis.length === 0 ? 'なし' : page.frames_without_analysis.join(', ')}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Box>
              </CardContent>
            </Card>
          )
        })}
      </Stack>
    </Box>
  )
}
