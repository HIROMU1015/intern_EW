# 照明製品 正規化・特定プロトタイプ

姿見図から既に商品単位の理想的なJSONが得られたものとして、その入力と商品DBを同じ規則で正規化し、製品候補を検索・判定するローカル実行用プロトタイプです。OCRそのものは含みません。元CSVは読み取りだけに使用し、正規化結果は別のSQLiteへ保存します。外部API・外部Webサービス・API Keyは使用しません。

## 作成済みの実データ成果物

- `data/lighting_products.sqlite`: 元CSV 176,447件を格納した正規化DB
- `validation/db_build_report.json`: 行数、重複数、元CSVのSHA-256
- `validation/sample_match_results.json`: `analysis_output/extraction_samples.json` 7件の照合結果

生成済みSQLiteは約144 MBです。元CSVを更新した場合は、同じコマンドで作り直してください。

## 処理ルート

1. `hinban + kidou` または完全品番の厳密一致
2. 品番本体 `hinban` の一致
3. 公共施設型番 `koukyou_kataban1/2` の厳密一致
4. 記号差を除いたOCR耐性一致
5. 安全な部分一致（候補提示だけで自動確定しない）
6. 品番がない場合はカテゴリ、埋込穴、器具寸法を入口に仕様検索

同じ品番に複数レコードがある場合は、`key/view_key`、明るさ、寸法、埋込穴、取付、防湿・防雨、調光などを比較します。点数は順位付け用です。曖昧一致や仕様だけの検索は、原則として人の確認なしに確定しません。

## 入力

1商品、商品配列、または `items` 配列を含むJSONを受け付けます。既存の探索スキーマもそのまま入力できます。
形式の機械可読な定義は `schemas/ideal_input.schema.json` にあります。

```json
{
  "source_file": "sample.pdf",
  "page": 1,
  "item_no": 1,
  "drawing_label": "DL1",
  "identity": {
    "manufacturer": "Panasonic",
    "category": "ダウンライト",
    "product_code_raw": "XND2532SV LE9",
    "hinban": "XND2532SV",
    "kidou": "LE9",
    "key_hint": "250形 5000K",
    "public_model_codes": []
  },
  "specifications": {
    "luminous_flux_lm": {"value": 2240, "raw": "2240lm"},
    "cutout_size": {"shape": "round", "diameter_mm": 100, "raw": "φ100"},
    "mounting_method": "ceiling_recessed",
    "waterproof": {"value": false, "raw": "防雨形ではない"},
    "dimming": {"value": false, "raw": "非調光"}
  },
  "uncertain_fields": []
}
```

入力では、品番を可能なら `hinban` と `kidou` に分離します。値は文字列だけでなく、`{"value": ..., "raw": ...}` 形式も受け付けます。OCR由来の不確かなフィールドは `uncertain_fields` にパスを記録してください。

## 実行方法

Python 3.11以上、追加ライブラリ不要です。`product_matching_system` へ移動して実行します。

```powershell
python -m lighting_matcher inspect-db --db data\lighting_products.sqlite
```

```powershell
python -m lighting_matcher match `
  --db data\lighting_products.sqlite `
  --input ..\analysis_output\extraction_samples.json `
  --output validation\sample_match_results.json `
  --top-k 10
```

元CSVから正規化DBを再生成する場合:

```powershell
python -m lighting_matcher build-db `
  --csv "..\drive-download-20260914T064948Z-1-001\品番DB\lightingDB_20240507.csv" `
  --db data\lighting_products.sqlite `
  --report validation\db_build_report.json
```

テスト:

```powershell
python -m unittest discover -s tests -v
```

## 出力の見方

`decision.status` は次のいずれかです。

| status | 意味 |
|---|---|
| `exact_unique` | 厳密な識別子でDB 1件。廃番や入力の不確かさがあれば `review_required=true` |
| `spec_filtered_unique` | 重複品番を追加仕様で分離、または仕様条件がDB 1件まで絞れた |
| `exact_multiple` | 同一識別子が複数あり、自動では一意にできない |
| `fuzzy_candidates` | OCR揺れ・部分一致の候補。人による品番確認が必要 |
| `spec_candidates` | 品番なしで仕様候補を提示。一意確定はしていない |
| `conflict` | 識別子は特定できたが、図面仕様とDBまたはDB内部に矛盾がある |
| `not_found` | 識別子がDBにない |
| `insufficient_input` | 検索に使える識別子・主要仕様がない |

各候補には `score`、`matched_fields`、`conflicts`、`db_internal_warnings`、生産状態、元DB値を含めます。`selected_id` が `null` の結果を自動見積へ流してはいけません。

## 正規化内容

- Unicode NFKC（全角英数字・空白の統一）
- 品番の大文字化・空白除去、厳密キーと記号除去キーを併存
- `hinban` と `kidou` と完全コードを別々に保持
- 公共施設型番を別キーとして保持
- カテゴリ名の代表表記への統一
- `φ125`、幅×長さなどの寸法キー化
- 取付方法の複数値コード化
- 防湿・防雨をDB主列と機能欄の両方から判定し、矛盾を保持
- 調光/非調光、生産状態、価格の型変換
- 自由記述から光束、色温度、消費電力、電圧、Raを保守的に数値抽出

元文字列はSQLite内にすべて残しており、正規化で情報を上書きしていません。

## 現時点の制約

- 元DBにメーカー列がないため、メーカーは照合条件にできません。
- DBの仕様は自由記述が多く、色温度・光束・電圧などを全レコードで完全に数値化したものではありません。
- OCRの文字置換候補（`0/O`、`1/I` など）は暴走しやすいため自動置換せず、記号差の候補提示までに制限しています。
- 仕様だけで1件になっても、DBに未格納のメーカー・外観・世代違いがあり得るため確認必須です。
- これは探索用の決定規則です。本番前には正解ラベル付きデータで閾値、再現率、誤確定率を評価する必要があります。
