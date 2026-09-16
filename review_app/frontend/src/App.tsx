import { useCallback, useEffect, useState } from 'react'
import AppBar from '@mui/material/AppBar'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import Toolbar from '@mui/material/Toolbar'
import Typography from '@mui/material/Typography'
import { api } from './api'
import ImportView from './views/ImportView'
import ResultsView from './views/ResultsView'
import ReviewView from './views/ReviewView'
import type { ProjectInfo } from './types'

export default function App() {
  const [tab, setTab] = useState(0)
  const [project, setProject] = useState<ProjectInfo | null>(null)
  const [health, setHealth] = useState<{ product_db_available: boolean; product_db: string; matcher_version: string } | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .health()
      .then((value) => setHealth(value))
      .catch((reason: Error) => setError(`バックエンドに接続できません: ${reason.message}`))
  }, [])

  const refreshProject = useCallback(async (projectId: string) => {
    const { project: fresh } = await api.project(projectId)
    setProject(fresh)
  }, [])

  const openProject = useCallback((value: ProjectInfo) => {
    setProject(value)
    setTab(1)
  }, [])

  return (
    <Box sx={{ height: '100vh', display: 'flex', flexDirection: 'column', bgcolor: 'grey.100' }}>
      <AppBar position="static" color="default" elevation={1}>
        <Toolbar variant="dense" sx={{ gap: 2 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
            照明商品候補の確認
          </Typography>
          <Tabs value={tab} onChange={(_, value) => setTab(value)} sx={{ minHeight: 40 }}>
            <Tab label="取り込み・再開" sx={{ minHeight: 40 }} />
            <Tab label="確認画面" sx={{ minHeight: 40 }} disabled={!project} />
            <Tab label="結果一覧・出力" sx={{ minHeight: 40 }} disabled={!project} />
          </Tabs>
          <Box sx={{ flex: 1 }} />
          {project && (
            <Chip
              label={`案件: ${project.name}（解析済み対象 ${project.item_count}件)`}
              color="primary"
              variant="outlined"
            />
          )}
          {health && (
            <Chip
              label={health.product_db_available ? `商品DB 接続あり / ${health.matcher_version}` : '商品DBが見つかりません'}
              color={health.product_db_available ? 'default' : 'error'}
            />
          )}
        </Toolbar>
      </AppBar>

      {error && (
        <Alert severity="error" onClose={() => setError(null)} sx={{ borderRadius: 0 }}>
          {error}
        </Alert>
      )}

      <Box sx={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
        {tab === 0 && <ImportView activeProject={project} onOpen={openProject} onError={setError} />}
        {/* 確認画面は画面を移動しても取り外さない。未保存の編集をタブ切り替えで失わないため。 */}
        {project && (
          <Box sx={{ height: '100%', minHeight: 0, display: tab === 1 ? 'block' : 'none' }}>
            <ReviewView project={project} onProjectChanged={() => refreshProject(project.id)} onError={setError} />
          </Box>
        )}
        {tab === 2 && project && <ResultsView project={project} onError={setError} />}
      </Box>
    </Box>
  )
}
