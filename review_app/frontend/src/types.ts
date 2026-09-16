export type ItemStatus = 'unconfirmed' | 'on_hold' | 'confirmed' | 'needs_recheck'
export type QuantityStatus = 'unconfirmed' | 'confirmed' | 'unreadable'
export type RelationStatus = 'single' | 'components_of_one_fixture' | 'multiple_fixtures' | 'unresolved'
export type EntryDecisionName = 'undecided' | 'adopted' | 'no_candidate' | 'excluded'

export interface SourceInfo {
  key: string
  label: string
  format: string
  analysis_path: string
  manifest_path: string | null
  image_root: string | null
  note: string | null
  available: boolean
  missing_paths: string[]
}

export interface ImageExtractionStatus {
  ready: boolean
  key_configured: boolean
  sdk_available: boolean
  provider: string
  model: string
  max_images_per_run: number
}

export interface ImageExtractionTarget {
  id: string
  source_file: string
  page: number
  item_no: number
  route: string | null
  available: boolean
}

export interface PdfDraft {
  id: string
  filename: string
  state: 'preparing' | 'ready' | 'running' | 'completed' | 'failed'
  page_count: number
  image_count: number
  pages_without_items: number
  completed_images: number
  error: string | null
  project: ProjectInfo | null
}

export interface ProjectInfo {
  id: string
  name: string
  source_key: string
  format: string
  analysis_path: string
  analysis_sha256: string
  manifest_path: string | null
  image_root: string | null
  created_at: string
  item_count: number
  ingest_report: IngestReport
  status_counts: Record<ItemStatus, number>
}

export interface IngestReport {
  api_metadata?: {
    provider: string
    model: string
    image_count: number
    usages: { target_id: string; usage: { total_tokens?: number } | null }[]
  }
  source_label: string
  detected_format: string
  analysis_path: string
  analyzed_item_count: number
  image_missing_count: number
  image_missing: { item_id: string; marker: string; source_file: string; page: number; missing: string[] }[]
  warning_counts: Record<string, number>
  structure_warnings: Warning[]
  manifest_pages: {
    source_file: string
    page: number
    route: string
    manifest_frame_count: number
    analyzed_item_count: number
    frames_without_analysis: number[]
  }[]
  manifest_frame_total: number
  frames_without_analysis_count: number
  scope_note: string
}

export interface Warning {
  code: string
  severity: string
  message: string
}

export interface ItemRow {
  id: string
  ordinal: number
  marker: string
  management_symbols: string[]
  name: string
  name_origin: 'drawing' | 'partial' | 'inferred' | 'unknown'
  category: string | null
  source_file: string | null
  page: number | null
  item_no: number | null
  status: ItemStatus
  status_label: string
  quantity_status: QuantityStatus
  quantity_status_label: string
  relation_status: RelationStatus
  relation_label: string
  relation_hint: string
  entry_count: number
  decided_count: number
  adopted: { entry_suffix: string; code: string | null; record_id: string | null }[]
  searched_entries: number
  candidate_total: number
  candidate_returned: number
  candidate_truncated: boolean
  has_image: boolean
  image_missing: string[]
  warning_count: number
  quantity_value: number | null
  quantity_unit: string | null
  updated_at: string | null
}

export interface FieldValue {
  key: string
  label: string
  raw: unknown
  value: unknown
  origin: 'drawing' | 'partial' | 'inferred' | 'unknown'
  used_in_search: boolean
  notes: string[]
}

export interface DbRecord {
  id: string
  hinban: string
  kidou: string
  full_code: string
  key: string
  view_key: string
  kigugroup: string
  kigustyle: string
  t_kigubunrui: string
  t_kigugroup: string
  price_zeinuki: number | null
  hatsubai_date: string
  seisan_end_date: string
  zaiku: string
  availability: string
  koukyou_kataban1: string
  koukyou_kataban2: string
  t_akarusa: string
  kigusize: string
  umekomi_ana: string
  t_toritsuke: string
  boushitsu_bouu: string
  t_kinou: string
  dannetsusekou: string
  y_toukyu: string
  y_toritsuke: string
  y_hyoujimen: string
  y_kinou: string
  parsed_hints: Record<string, number | null>
}

export interface Candidate {
  rank: number
  score: number
  matched_fields: { field: string; match_type?: string; input?: unknown; db?: unknown; weight?: number; ratio?: number }[]
  conflicts: { field: string; input?: unknown; db?: unknown }[]
  db_internal_warnings: string[]
  lifecycle_warning: string | null
  record: DbRecord
}

export interface SearchResult {
  id: string
  created_at: string
  input_fingerprint: string
  match_input: Record<string, any>
  search: {
    route: string
    basis: string[]
    candidate_count: number
    returned_count: number
    candidate_pool_truncated: boolean
  }
  machine_decision: { status: string; selected_id: string | null; review_required: boolean; reason: string }
  candidates: Candidate[]
  normalized_input: Record<string, any>
  warnings: string[]
  matcher_version: string
}

export interface EntryDecision {
  decision: EntryDecisionName
  adopted_record_id: string | null
  adopted_code: string | null
  adopted_summary: any
  adopted_search_id: string | null
  adopted_input_fingerprint: string | null
  decision_input_fingerprint: string | null
  note: string | null
  updated_at: string | null
}

export interface ItemEntry {
  suffix: string
  label: string
  role: string
  kind: 'code' | 'specification'
  code: string | null
  code_raw: string | null
  code_note: string | null
  hinban: string | null
  kidou: string | null
  public_codes: string[]
  group: string | null
  source_field: string
  notes: string[]
  decision: EntryDecision
  decision_label: string
  search: SearchResult | null
  current_input: Record<string, any>
  current_input_fingerprint: string
  effective_identifier: { code: string | null; hinban: string | null; kidou: string | null; notes: string[] }
  decision_stale: boolean
}

export interface ItemDetail {
  id: string
  project_id: string
  ordinal: number
  source_file: string | null
  page: number | null
  item_no: number | null
  display: {
    marker: string
    management_symbols: string[]
    name: string
    name_origin: 'drawing' | 'partial' | 'inferred' | 'unknown'
    category_raw: string | null
    category_normalized: string | null
    manufacturer: string | null
  }
  relation: { hint: string; status: RelationStatus; evidence: string[] }
  relation_label: string
  fields: FieldValue[]
  quantity: { value: number | null; unit: string | null; raw: unknown; origin: string }
  images: {
    item: string | null
    item_original: string | null
    item_enhanced: string | null
    item_binary: string | null
    page: string | null
    page_width: number | null
    page_height: number | null
    bbox_pixels: number[] | null
    missing: string[]
    available: string[]
  }
  warnings: Warning[]
  raw_text: string | null
  recognition_notes: string[]
  normalized_notes: string[]
  uncertain_fields: string[]
  source_json: Record<string, any>
  entries: ItemEntry[]
  review: {
    item_id: string
    status: ItemStatus
    status_label: string
    quantity_status: QuantityStatus
    quantity_status_label: string
    relation_status: RelationStatus
    quantity_value: number | null
    quantity_unit: string | null
    corrections: Corrections
    hold_reason: string | null
    memo: string | null
    revision: number
    updated_at: string | null
  }
  history: { id: number; action: string; entry_suffix: string | null; detail: string | null; created_at: string }[]
}

export interface Corrections {
  category?: string | null
  specifications?: Record<string, any>
  entries?: Record<string, { code?: string; hinban?: string | null; kidou?: string | null }>
}
