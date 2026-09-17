import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import ImportView from '../views/ImportView'
import { project } from './apiFixtures'

function jsonResponse(body: unknown): Promise<Response> {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) } as Response)
}

describe('PDFを置いて候補確認へ進む', () => {
  beforeEach(() => window.sessionStorage.clear())
  afterEach(() => { cleanup(); vi.unstubAllGlobals() })

  it('PDFを置いて決定すると案件を開く', async () => {
    const onOpen = vi.fn()
    const onError = vi.fn()
    const readyDraft = {
      id: 'draft1', filename: 'drawing.pdf', state: 'ready', page_count: 1, image_count: 2,
      pages_without_items: 0, completed_images: 0, error: null, project: null,
    }
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url === '/api/sources') return jsonResponse({ sources: [] })
      if (url === '/api/projects') return jsonResponse({ projects: [] })
      if (url === '/api/image-extraction/status') return jsonResponse({ ready: true, max_images_per_run: 10 })
      if (url.startsWith('/api/pdf-drafts?')) return jsonResponse(readyDraft)
      if (url === '/api/pdf-drafts/draft1/confirm') return jsonResponse({ ...readyDraft, state: 'completed', project })
      return jsonResponse({})
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<ImportView activeProject={null} onOpen={onOpen} onError={onError} />)

    fireEvent.click(screen.getByText('詳細設定・従来の取り込み方法'))
    expect(await screen.findByText('登録済みの旧解析データはありません。上の欄へ姿見図PDFを置いて開始してください。')).toBeTruthy()

    const file = new File(['%PDF-1.7\n'], 'drawing.pdf', { type: 'application/pdf' })
    fireEvent.drop(screen.getByRole('button', { name: '姿見図PDFをここに置く' }), { dataTransfer: { files: [file] } })
    await screen.findByText('1ページ、送信する画像2件。決定すると画像1件につきAPIを1回呼び、候補を表示します。')
    fireEvent.click(screen.getByRole('button', { name: '決定して候補を確認' }))
    await waitFor(() => expect(onOpen).toHaveBeenCalledWith(project))
    expect(onError).not.toHaveBeenCalled()
    expect(fetchMock.mock.calls.some(([url]) => String(url).startsWith('/api/pdf-drafts?filename=drawing.pdf'))).toBe(true)
  })
})
