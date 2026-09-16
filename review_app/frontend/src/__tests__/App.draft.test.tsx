/**
 * ② 画面（タブ）を移動すると未保存の編集が消える問題の回帰テスト。
 * 実データにもバックエンドにも接続せず、fetchを差し替えて画面操作だけを確認する。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import App from '../App'
import { itemDetail, items, project } from './apiFixtures'

function jsonResponse(body: unknown) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) } as Response)
}

function stubFetch(input: RequestInfo | URL): Promise<Response> {
  const url = typeof input === 'string' ? input : input.toString()
  if (url.startsWith('/api/health')) {
    return jsonResponse({ status: 'ok', product_db_available: true, product_db: 'db', review_db: 'review', matcher_version: 'v1' })
  }
  if (url.startsWith('/api/sources')) return jsonResponse({ sources: [] })
  if (url === '/api/projects') return jsonResponse({ projects: [project] })
  if (url === `/api/projects/${project.id}`) return jsonResponse({ project })
  if (url === `/api/projects/${project.id}/items`) return jsonResponse({ items })
  const itemMatch = url.match(/^\/api\/items\/(\w+)$/)
  if (itemMatch) return jsonResponse({ item: itemDetail(itemMatch[1]) })
  return jsonResponse({})
}

/** カテゴリは表示専用で、［修正］を押したときだけ入力欄が開く。 */
async function openCategoryEditor() {
  const heading = await screen.findByText('カテゴリ・数量')
  fireEvent.click(within(heading.parentElement as HTMLElement).getByRole('button', { name: '修正' }))
  return (await screen.findByLabelText('カテゴリ（担当者の修正）')) as HTMLInputElement
}

describe('未保存の編集の保持', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(stubFetch))
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('結果一覧へ移動して確認画面に戻っても、編集した値が残る', async () => {
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '確認画面を開く' }))
    const category = await openCategoryEditor()
    fireEvent.change(category, { target: { value: 'ベースライト（修正）' } })
    expect((screen.getByLabelText('カテゴリ（担当者の修正）') as HTMLInputElement).value).toBe('ベースライト（修正）')

    fireEvent.click(screen.getByRole('tab', { name: '結果一覧・出力' }))
    await waitFor(() => expect(screen.getByText('結果一覧・出力', { selector: 'h6' })).toBeTruthy())

    fireEvent.click(screen.getByRole('tab', { name: '確認画面' }))
    await waitFor(() =>
      expect((screen.getByLabelText('カテゴリ（担当者の修正）') as HTMLInputElement).value).toBe('ベースライト（修正）'),
    )
    // 表示専用のカテゴリ行にも、修正した値が出ている。
    expect(screen.getAllByText('ベースライト（修正）').length).toBeGreaterThan(0)
  })

  it('器具を切り替えても、編集した値が残る', async () => {
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '確認画面を開く' }))
    const category = await openCategoryEditor()
    fireEvent.change(category, { target: { value: 'スポットライト（修正）' } })

    fireEvent.click(screen.getByText('A402'))
    await waitFor(() => expect(screen.getAllByText('A402').length).toBeGreaterThan(0))
    fireEvent.click(screen.getByText('A401'))
    const reopened = await openCategoryEditor()

    await waitFor(() => expect(reopened.value).toBe('スポットライト（修正）'))
  })
})
