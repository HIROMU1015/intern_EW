import type { EntryDecisionName, ItemStatus, QuantityStatus, RelationStatus } from './types'

export const STATUS_LABELS: Record<ItemStatus, string> = {
  unconfirmed: '未確認',
  on_hold: '保留',
  confirmed: '確認済み',
  needs_recheck: '再確認が必要',
}

export const STATUS_COLORS: Record<ItemStatus, 'default' | 'warning' | 'success' | 'error'> = {
  unconfirmed: 'default',
  on_hold: 'warning',
  confirmed: 'success',
  needs_recheck: 'error',
}

export const QUANTITY_LABELS: Record<QuantityStatus, string> = {
  unconfirmed: '数量未確認',
  confirmed: '数量確認済み',
  unreadable: '数量読み取り困難',
}

export const RELATION_LABELS: Record<RelationStatus, string> = {
  single: '品番1件',
  components_of_one_fixture: '1器具の構成品',
  multiple_fixtures: '分割の確認が必要',
  unresolved: '品番同士の関係確認が必要',
}

export const RELATION_HELP: Record<RelationStatus, string> = {
  single: '品番は1件。',
  components_of_one_fixture: '本体・ランプ・電源など、1つの器具を構成する品番として扱う。構成品ごとに候補と採用結果を持つ。',
  multiple_fixtures: '複数の器具が1件にまとまっている可能性がある。分割の確認が必要なため確認済みにはできない。',
  unresolved: '複数の品番の関係が未確定。構成品か別器具かを選ぶまで確認済みにはできない。',
}

export const DECISION_LABELS: Record<EntryDecisionName, string> = {
  undecided: '未判断',
  adopted: '採用',
  no_candidate: '候補なし',
  excluded: '対象外',
}

export const ORIGIN_LABELS: Record<string, string> = {
  drawing: '原図',
  partial: '原図（一部）',
  inferred: '推定',
  unknown: '不明',
}

export const WARNING_LABELS: Record<string, string> = {
  analysis_root_shape: '解析JSONのルート形式',
  analysis_item_not_object: '形式不整合の要素',
  management_symbol_multiple: '管理記号が複数',
  composite_model_number: '「+」連結の構成品表記',
  slash_separated_model_number: '「/」区切りの品番表記',
  model_number_absent: '品番なし（仕様検索）',
  model_number_only_note: '注記だけの品番',
  quantity_unknown: '数量が読み取れていない',
  page_level_extraction: 'ページ全体を1件として読み取り',
  unusable_page: '判読不能ページ',
  extractor_review_required: '解析側が要確認',
  uncertain_fields_reported: '解析側の不確かな項目',
  category_not_in_db_vocabulary: 'カテゴリがDB分類に一致しない',
  image_missing: '画像欠損',
  manifest_item_not_found: 'マニフェストに該当枠なし',
  manifest_page_not_found: 'マニフェストに該当ページなし',
}

export const ROUTE_LABELS: Record<string, string> = {
  exact_identifier: '識別子の厳密一致',
  relaxed_identifier: '記号差を除いた一致',
  partial_identifier: '部分一致',
  specification_search: '仕様検索',
  identifier_not_found: '識別子が見つからない',
  insufficient_input: '検索条件が不足',
}

export const MACHINE_STATUS_LABELS: Record<string, string> = {
  exact_unique: '厳密一致1件',
  spec_filtered_unique: '仕様で1件に絞れた',
  exact_multiple: '同一識別子が複数',
  fuzzy_candidates: '曖昧一致の候補',
  spec_candidates: '仕様候補',
  conflict: '矛盾あり',
  not_found: 'DBに該当なし',
  insufficient_input: '検索条件が不足',
  review_required: '要確認',
}

export const AVAILABILITY_LABELS: Record<string, string> = {
  discontinued: '生産終了品',
  planned_discontinued: '生産終了予定品',
  factory_stock: '工場在庫品',
  made_to_order: '受注品',
  stock: '常備在庫品',
  unknown: '生産状態不明',
  other: 'その他',
}
