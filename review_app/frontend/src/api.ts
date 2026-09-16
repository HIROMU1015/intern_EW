import type { ImageExtractionStatus, ImageExtractionTarget, ItemDetail, ItemRow, PdfDraft, ProjectInfo, SourceInfo } from './types'

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* レスポンスがJSONでない場合はそのまま */
    }
    throw new Error(detail)
  }
  return (await response.json()) as T
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  return parseResponse<T>(response)
}

export const api = {
  health: () => request<{ status: string; product_db_available: boolean; product_db: string; review_db: string; matcher_version: string }>('/api/health'),
  sources: () => request<{ sources: SourceInfo[] }>('/api/sources'),
  imageExtractionStatus: () => request<ImageExtractionStatus>('/api/image-extraction/status'),
  uploadPdf: async (file: File) => parseResponse<PdfDraft>(await fetch(
    `/api/pdf-drafts?filename=${encodeURIComponent(file.name)}`,
    { method: 'POST', headers: { 'Content-Type': 'application/pdf' }, body: file },
  )),
  pdfDraft: (draftId: string) => request<PdfDraft>(`/api/pdf-drafts/${encodeURIComponent(draftId)}`),
  confirmPdfDraft: (draftId: string) => request<PdfDraft>(`/api/pdf-drafts/${encodeURIComponent(draftId)}/confirm`, { method: 'POST' }),
  imageExtractionTargets: (sourceKey: string) =>
    request<{ targets: ImageExtractionTarget[] }>(`/api/image-extraction/targets?source_key=${encodeURIComponent(sourceKey)}`),
  imageExtractionTargetUrl: (sourceKey: string, targetId: string) =>
    `/api/image-extraction/targets/${encodeURIComponent(targetId)}/image?source_key=${encodeURIComponent(sourceKey)}`,
  runImageExtraction: (sourceKey: string, targetIds: string[]) =>
    request<{ project: ProjectInfo; created: boolean; api_usages: { target_id: string; usage: { total_tokens?: number } | null }[] }>(
      '/api/image-extraction/runs',
      { method: 'POST', body: JSON.stringify({ source_key: sourceKey, target_ids: targetIds }) },
    ),
  projects: () => request<{ projects: ProjectInfo[] }>('/api/projects'),
  createProject: (sourceKey: string) =>
    request<{ project: ProjectInfo; created: boolean; message: string | null }>('/api/projects', {
      method: 'POST',
      body: JSON.stringify({ source_key: sourceKey }),
    }),
  project: (projectId: string) => request<{ project: ProjectInfo }>(`/api/projects/${projectId}`),
  items: (projectId: string) => request<{ items: ItemRow[] }>(`/api/projects/${projectId}/items`),
  item: (itemId: string) => request<{ item: ItemDetail }>(`/api/items/${itemId}`),
  search: (itemId: string, body: { entry_suffix?: string | null; corrections?: unknown; top_k?: number }) =>
    request<{ results: { item_id: string; entry_suffix: string; is_latest: boolean; search: any; notes: string[] }[] }>(
      `/api/items/${itemId}/search`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  saveReview: (itemId: string, body: unknown) =>
    request<{ item: ItemDetail; notes: string[]; saved_revision: number }>(`/api/items/${itemId}/review`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  imageUrl: (itemId: string, variant: string) => `/api/items/${itemId}/image?variant=${encodeURIComponent(variant)}`,
  exportJsonUrl: (projectId: string) => `/api/projects/${projectId}/export.json`,
  exportCsvUrl: (projectId: string) => `/api/projects/${projectId}/export.csv`,
}
