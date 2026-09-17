import type { EntryDecisionName, ItemStatus, QuantityStatus, RelationStatus } from './types'

export const STATUS_LABELS: Record<ItemStatus, string> = {
  unconfirmed: '未確認',
  on_hold: 'あとで確認',
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
  components_of_one_fixture: '1つの器具の部品',
  multiple_fixtures: '複数の器具が混ざっている可能性があります',
  unresolved: '複数の品番が読み取られています',
}

/** 状態の意味と、担当者が次に何をすればよいかを1文で書く。 */
export const RELATION_HELP: Record<RelationStatus, string> = {
  single: '品番は1件です。',
  components_of_one_fixture: '本体・ランプ・電源など、1つの器具を組み立てる部品として扱います。部品ごとに商品を選べます。',
  multiple_fixtures: '1つの枠に複数の器具が入っている可能性があります。分けて確認してください（このままでは確認済みにできません）。',
  unresolved: '同じ器具の部品か、別々の器具かを確認してください（選ぶまで確認済みにできません）。',
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

/**
 * 取り込み時の注意点。システム内部の言い方ではなく、
 * 「何が起きているか」と「次に何をすればよいか」が分かる文にする。
 */
export const WARNING_LABELS: Record<string, string> = {
  analysis_root_shape: '読み取りデータの形式が想定と違います',
  analysis_item_not_object: '読み取りデータに不正な項目があります',
  management_symbol_multiple: '管理記号が複数読み取られています',
  composite_model_number: '複数の品番が「+」でつながっています',
  slash_separated_model_number: '複数の品番が「/」で区切られています',
  model_number_absent: '品番が読み取れていません。仕様で候補を探しています',
  model_number_only_note: '品番ではなく注記だけが読み取られています',
  quantity_unknown: '数量が読み取れていません。図面で確認してください',
  page_level_extraction: 'ページ全体を1件として読み取りました。器具が混ざっていないか確認してください',
  unusable_page: '図面が読み取れませんでした。原図で確認してください',
  extractor_review_required: '読み取りが不確かです。値を確認してください',
  uncertain_fields_reported: '一部の項目が不確かです。値を確認してください',
  category_not_in_db_vocabulary: '読み取った種類と商品情報が異なります。候補を確認してください',
  image_missing: '図面の画像が見つかりません',
  manifest_item_not_found: '図面上の該当箇所が見つかりません',
  manifest_page_not_found: '図面の該当ページが見つかりません',
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
