import { useCallback, useEffect, useRef, useState } from 'react'
import Accordion from '@mui/material/Accordion'
import AccordionDetails from '@mui/material/AccordionDetails'
import AccordionSummary from '@mui/material/AccordionSummary'
import Alert from '@mui/material/Alert'
import Autocomplete from '@mui/material/Autocomplete'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Chip from '@mui/material/Chip'
import Divider from '@mui/material/Divider'
import MenuItem from '@mui/material/MenuItem'
import LinearProgress from '@mui/material/LinearProgress'
import Stack from '@mui/material/Stack'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { api } from '../api'
import { WARNING_LABELS } from '../labels'
import type { ImageExtractionStatus, ImageExtractionTarget, PdfDraft, ProjectInfo, SourceInfo } from '../types'

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
  const [extractionStatus, setExtractionStatus] = useState<ImageExtractionStatus | null>(null)
  const [sourceKey, setSourceKey] = useState('')
  const [targets, setTargets] = useState<ImageExtractionTarget[]>([])
  const [selected, setSelected] = useState<ImageExtractionTarget[]>([])
  const [draft, setDraft] = useState<PdfDraft | null>(null)
  const [uploading, setUploading] = useState(false)
  const fileInput = useRef<HTMLInputElement | null>(null)
  const openedDraft = useRef<string | null>(null)

  const reload = useCallback(async () => {
    try {
      const [{ sources: loadedSources }, { projects: loadedProjects }, status] = await Promise.all([
        api.sources(), api.projects(), api.imageExtractionStatus(),
      ])
      setSources(loadedSources)
      setProjects(loadedProjects)
      setExtractionStatus(status)
      setSourceKey((current) => current || loadedSources.find((source) => source.manifest_path && source.image_root)?.key || '')
    } catch (reason) {
      onError((reason as Error).message)
    }
  }, [onError])

  useEffect(() => {
    void reload()
  }, [reload])

  useEffect(() => {
    const draftId = window.sessionStorage.getItem('review_app_pdf_draft_id')
    if (!draftId) return
    void api.pdfDraft(draftId)
      .then(setDraft)
      .catch(() => window.sessionStorage.removeItem('review_app_pdf_draft_id'))
  }, [])

  useEffect(() => {
    if (!sourceKey) return
    let cancelled = false
    setSelected([])
    void api.imageExtractionTargets(sourceKey)
      .then(({ targets: loaded }) => { if (!cancelled) setTargets(loaded) })
      .catch((reason) => { if (!cancelled) onError((reason as Error).message) })
    return () => { cancelled = true }
  }, [sourceKey, onError])

  useEffect(() => {
    if (!draft || !['preparing', 'running'].includes(draft.state)) return
    let cancelled = false
    const timer = window.setTimeout(() => {
      void api.pdfDraft(draft.id)
        .then((latest) => { if (!cancelled) setDraft(latest) })
        .catch((reason) => {
          if (!cancelled) setDraft((current) => current ? { ...current, state: 'failed', error: (reason as Error).message } : current)
        })
    }, 1000)
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [draft, onError])

  useEffect(() => {
    if (draft?.state === 'completed' && draft.project && openedDraft.current !== draft.id) {
      openedDraft.current = draft.id
      window.sessionStorage.removeItem('review_app_pdf_draft_id')
      void reload()
      onOpen(draft.project)
    }
  }, [draft, onOpen, reload])

  const uploadPdf = async (file: File | undefined) => {
    if (!file || uploading) return
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      onError('PDFファイルを選択してください。')
      return
    }
    if (file.size > 25 * 1024 * 1024) {
      onError('PDFは25MB以下にしてください。')
      return
    }
    setUploading(true)
    setDraft(null)
    try {
      const uploaded = await api.uploadPdf(file)
      window.sessionStorage.setItem('review_app_pdf_draft_id', uploaded.id)
      setDraft(uploaded)
    } catch (reason) {
      onError((reason as Error).message)
    } finally {
      setUploading(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  const confirmPdf = async () => {
    if (!draft) return
    try {
      setDraft(await api.confirmPdfDraft(draft.id))
    } catch (reason) {
      onError((reason as Error).message)
    }
  }

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

  const runExtraction = async () => {
    if (!sourceKey || selected.length === 0) return
    setBusy(true)
    setMessage(null)
    try {
      const result = await api.runImageExtraction(sourceKey, selected.map((target) => target.id))
      const total = result.api_usages.reduce((sum, row) => sum + (row.usage?.total_tokens ?? 0), 0)
      setMessage(`画像${selected.length}件を読み取り、候補を表示しました。${total ? `API使用量: ${total}トークン。` : 'API使用量は接続先から返されていません。'}`)
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
      {(busy || uploading) && <LinearProgress sx={{ mb: 1 }} />}
      {message && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setMessage(null)}>
          {message}
        </Alert>
      )}

      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>姿見図PDFから候補を確認</Typography>
          <Box
            role="button" tabIndex={0} aria-label="姿見図PDFをここに置く"
            onClick={() => fileInput.current?.click()}
            onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') fileInput.current?.click() }}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => { event.preventDefault(); void uploadPdf(event.dataTransfer.files[0]) }}
            sx={{ border: '2px dashed', borderColor: 'primary.light', borderRadius: 2, px: 3, py: 4, textAlign: 'center', bgcolor: 'grey.50', cursor: 'pointer' }}
          >
            <Typography sx={{ fontWeight: 600 }}>ここに姿見図PDFをドラッグ＆ドロップ</Typography>
            <Typography variant="body2" color="text.secondary">クリックしてファイルを選ぶこともできます</Typography>
          </Box>
          <input ref={fileInput} type="file" accept="application/pdf,.pdf" hidden onChange={(event) => void uploadPdf(event.target.files?.[0])} />
          {!draft && extractionStatus && !extractionStatus.ready && (
            <Alert severity="info" sx={{ mt: 2 }}>現在はAPIキーまたは必要なパッケージが未設定です。PDFの準備件数までは確認できます。</Alert>
          )}
          {draft && (
            <Stack spacing={1} sx={{ mt: 2 }}>
              <Typography sx={{ fontWeight: 600 }}>{draft.filename}</Typography>
              {draft.state === 'preparing' && <Alert severity="info">PDFを準備しています。器具ごとの画像を作成中です。</Alert>}
              {draft.state === 'ready' && (
                <Alert severity="info">
                  {draft.page_count}ページ、送信する画像{draft.image_count}件。決定すると画像1件につきAPIを1回呼び、候補を表示します。
                  {draft.pages_without_items > 0 && ` 読み取り対象が見つからないページが${draft.pages_without_items}件あります。`}
                </Alert>
              )}
              {draft.state === 'running' && (
                <Box>
                  <Typography variant="body2">読み取り・候補検索中: {draft.completed_images} / {draft.image_count}件</Typography>
                  <LinearProgress variant="determinate" value={draft.image_count ? draft.completed_images / draft.image_count * 100 : 0} />
                </Box>
              )}
              {draft.state === 'failed' && <Alert severity="error">{draft.error}</Alert>}
              {draft.state === 'completed' && <Alert severity="success">候補確認画面を開きます。</Alert>}
              {extractionStatus && !extractionStatus.ready && (
                <Alert severity="warning">APIキーまたは必要なパッケージが未設定です。PDFの準備はできますが、読み取りの実行は設定後に行えます。</Alert>
              )}
              <Box>
                <Button variant="contained" size="large" onClick={confirmPdf}
                  disabled={draft.state !== 'ready' || !extractionStatus?.ready}>決定して候補を確認</Button>
              </Box>
            </Stack>
          )}
        </CardContent>
      </Card>

      <Accordion variant="outlined" sx={{ mb: 3 }}>
        <AccordionSummary><Typography>詳細設定・従来の取り込み方法</Typography></AccordionSummary>
        <AccordionDetails>
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>画像から読み取り・候補を表示</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            登録済みの前処理画像を選び、社内の画像解析APIで読み取ります。結果は未確認として保存され、商品候補を検索します。
          </Typography>
          {extractionStatus && !extractionStatus.ready && (
            <Alert severity="info" sx={{ mb: 2 }}>
              {!extractionStatus.key_configured ? 'APIキーが未設定です。サーバー側に設定すると実行できます。'
                : !extractionStatus.sdk_available ? '画像解析API用のPythonパッケージが未導入です。'
                  : '画像解析APIの設定を確認してください。'}
            </Alert>
          )}
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="flex-start">
            <TextField select size="small" label="画像の取り込み元" value={sourceKey}
              onChange={(event) => setSourceKey(event.target.value)} sx={{ minWidth: 260 }}>
              {sources.filter((source) => source.manifest_path && source.image_root).map((source) => (
                <MenuItem key={source.key} value={source.key}>{source.label}</MenuItem>
              ))}
            </TextField>
            <Autocomplete multiple size="small" options={targets.filter((target) => target.available)} value={selected}
              onChange={(_, value) => setSelected(value.slice(0, extractionStatus?.max_images_per_run || 10))}
              getOptionLabel={(target) => `${target.source_file} ${target.page}ページ 器具${target.item_no}`}
              isOptionEqualToValue={(option, value) => option.id === value.id}
              renderInput={(params) => <TextField {...params} label="送信する画像（最大10件）" placeholder="PDF名・ページ・器具番号" />}
              sx={{ flex: 1, minWidth: 300 }} />
            <Button variant="contained" disabled={busy || !extractionStatus?.ready || selected.length === 0}
              onClick={runExtraction}>選択画像を読み取る</Button>
          </Stack>
          <Typography variant="caption" color="text.secondary" component="div" sx={{ mt: 1 }}>
            利用可能な画像 {targets.filter((target) => target.available).length}件 / 全{targets.length}件。実行時に選択した画像だけを送信します。
          </Typography>
          {selected[0] && (
            <Box component="img" src={api.imageExtractionTargetUrl(sourceKey, selected[0].id)} alt="選択画像のプレビュー"
              sx={{ display: 'block', mt: 1, maxWidth: 420, maxHeight: 240, objectFit: 'contain', border: '1px solid', borderColor: 'divider' }} />
          )}
        </CardContent>
      </Card>

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

        </AccordionDetails>
      </Accordion>

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
                {report.api_metadata && (
                  <Typography variant="body2" sx={{ mb: 1 }}>
                    画像解析API: {report.api_metadata.image_count}回 / {report.api_metadata.provider}・{report.api_metadata.model} / 使用量:{' '}
                    {report.api_metadata.usages.every((row) => typeof row.usage?.total_tokens === 'number')
                      ? `${report.api_metadata.usages.reduce((sum, row) => sum + (row.usage?.total_tokens ?? 0), 0)}トークン`
                      : '一部未取得'}
                  </Typography>
                )}
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
