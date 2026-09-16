/**
 * 機械の判定結果を、担当者向けの日本語へ置き換える。
 * 検索結果から分からないことは書かない。原文は「検索の詳細」に残す。
 */

export interface MachineSummary {
  headline: string
  detail: string
}

const ROUTE_TEXT: Record<string, string> = {
  exact_identifier: '品番の厳密一致で検索しました。',
  relaxed_identifier: '記号の違いを除いた品番で検索しました。',
  partial_identifier: '品番の一部一致で検索しました。',
  specification_search: '品番が使えないため、仕様条件で検索しました。',
  identifier_not_found: '指定の品番はDBに見つかりませんでした。',
  insufficient_input: '検索に使える条件がありません。',
}

export function machineSummary(status: string, route: string, candidateCount: number): MachineSummary {
  switch (status) {
    case 'exact_unique':
      return {
        headline: '品番が1件に一致しました。',
        detail: '自動での確定はしていません。仕様と原図を確認してから採用してください。',
      }
    case 'spec_filtered_unique':
      return {
        headline: '仕様条件で1件に絞り込めました。',
        detail: 'DBに未収録のメーカー・世代違いがある可能性があります。原図と照合してください。',
      }
    case 'exact_multiple':
      return {
        headline: '同じ品番の商品が複数あります。仕様の違いを確認してください。',
        detail: `同じ識別子のDBレコードが${candidateCount}件あります。仕様の差で選んでください。`,
      }
    case 'fuzzy_candidates':
      return {
        headline:
          route === 'partial_identifier'
            ? '品番の一部が一致する候補です。原図と照合してください。'
            : '記号の違いを除いて一致する候補です。原図と照合してください。',
        detail: '品番が完全には一致していません。読み取り内容の修正が必要な場合があります。',
      }
    case 'spec_candidates':
      return {
        headline: '品番が読み取れていないため、仕様条件で候補を出しています。',
        detail: '候補は絞り込めていません。条件を足して再検索するか、原図で品番を確認してください。',
      }
    case 'conflict':
      return {
        headline: '品番は一致していますが、図面の仕様と異なる点があります。',
        detail: '相違点を確認し、品番と仕様のどちらが正しいかを判断してください。',
      }
    case 'not_found':
      return {
        headline: '現在の検索条件に該当する商品が見つかりませんでした。',
        detail: '品番の読み取りを修正して再検索するか、「候補なし」として記録してください。',
      }
    case 'insufficient_input':
      return {
        headline: '検索に使える情報が不足しています。',
        detail: '品番かカテゴリ・埋込穴などの条件を入力して再検索してください。',
      }
    default:
      return {
        headline: '自動では判断できませんでした。担当者の確認が必要です。',
        detail: ROUTE_TEXT[route] ?? '',
      }
  }
}

export function routeText(route: string): string {
  return ROUTE_TEXT[route] ?? route
}
