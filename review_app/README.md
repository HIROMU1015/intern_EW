# 照明商品候補の確認アプリ（ローカル専用）

姿図PDFから既に得られている解析結果を取り込み、原図・読み取り結果・商品候補を並べて、担当者が修正・選択・保留できるローカルアプリです。
既存の照合処理（`product_matching_system/lighting_matcher`）はコピーせず、APIから呼び出して使います。

- フロント: React + TypeScript + Vite + MUI（一覧は MUI X Data Grid Community）
- バックエンド: FastAPI（`127.0.0.1` のみ）
- 検索: 既存の `ProductMatcher`（商品SQLiteは読み取り専用）
- 作業保存: 商品DBとは別の SQLite（`review_app/data/review.sqlite`）

## 前提

| 種別 | 内容 |
|---|---|
| Python | 3.12 で確認。`fastapi` `uvicorn` `pydantic` が必要（導入済み環境で確認） |
| Node.js | v24.19.0（Codexランタイム同梱のものを使用） |
| pnpm | 11.19.0（同上） |
| 商品DB | `product_matching_system/data/lighting_products.sqlite`（既存・読み取り専用） |

Node.js はPATHに入っていないため、実行時に環境を指定します。

PowerShell:

```powershell
$env:Path = "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;$env:Path"
```

Git Bash:

```bash
export PATH="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
```

`pnpm` 本体は次のパスにあります。`pnpm` コマンドが無い場合は `node <このパス> <引数>` で実行してください。

```text
%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\pnpm\bin\pnpm.mjs
```

## 起動

1. バックエンド（別ターミナル）

```powershell
python review_app\backend\run_backend.py
```

2. フロントエンド（初回のみ依存取得）

```powershell
cd review_app\frontend
node "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\pnpm\bin\pnpm.mjs" install
node "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\pnpm\bin\pnpm.mjs" run dev
```

3. ブラウザで `http://127.0.0.1:5173/` を開く

APIは `http://127.0.0.1:8000`、Vite開発サーバーが `/api` をプロキシします。どちらもローカルホスト限定で、外部サービス登録は不要です。

環境変数で切り替えられます。

| 変数 | 既定 | 用途 |
|---|---|---|
| `REVIEW_APP_PRODUCT_DB` | `product_matching_system/data/lighting_products.sqlite` | 商品DB（読み取り専用） |
| `REVIEW_APP_DATA_DIR` | `review_app/data` | 確認結果SQLiteと出力の保存先 |
| `REVIEW_APP_SOURCES` | `review_app/backend/sources.json` | 取り込み元の定義 |

## 取り込み元

`review_app/backend/sources.json` に登録したローカルパスだけを読みます。APIのリクエストで任意の絶対パスを指定して読む機能は設けていません。
`パス#メンバー` と書くとZIP内のJSONを展開せずに読みます（元ZIPは変更しません）。

| key | 内容 |
|---|---|
| `gpt_direct_v3` | `gpt_direct_validation_image_only.zip` 内の画像解析結果（器具単位50件）＋ `analysis_output/work/preprocessed_auto_v3` の画像・マニフェスト |
| `extraction_samples` | `analysis_output/extraction_samples.json`（ideal形式7件）＋ 同じ前処理出力の画像 |

同じ解析JSON（SHA-256が同じ）を再度取り込むと、新規作成ではなく既存案件の再開になります。

## 画面

### 取り込み・再開
取り込み元の存在確認、取り込み件数、画像欠損、形式不整合（取り込み警告）、ページ別のマニフェスト枠との対応を表示します。
**未解析枠は枠IDの対応で数えており、総枠数からの差し引きでは求めていません。** 一覧は解析済み対象だけを扱い、全件確認してもPDF全体の確認完了にはなりません。

### 確認画面（3ペイン）
- 左: 見積対象一覧。管理記号（無ければ「3ページ・器具02」など）、仮の器具名（原図/推定/種別不明を文字で表示）、元PDFのページ、候補件数、確認状態。検索と絞り込み、選択行の強調。採用後も元の目印を残し、採用品番を別行に出します。
- 中央: 原図。商品画像・強調・2値・元ページ画像の切り替え、拡大・縮小・全体表示、ドラッグ移動、元ファイル名とページ、元ページ上の切り出し範囲（赤枠）。画像が無い場合は欠損として表示し、他の対象の確認は続けられます。対応は安定ID（`i_` + ハッシュ）で行い、表示順や仮の商品名に依存しません。
- 右上: 読み取り結果（薄い青グレーの面と見出し帯）。品番原文・hinban・kidou、カテゴリ、光束・色温度・消費電力・電圧、寸法・埋込穴、取付・防湿防雨・調光、数量、注意点。
  各項目は値を主役に置き、状態を文字ラベルで示します（読取あり／推定／要確認／未取得／記載なし／修正済み）。未取得は灰色、推定・要確認は薄い黄色の面、修正済みは青系の面です。
  通常は表示だけで、［修正］を押した項目だけ入力欄が開きます（元の読み取り値・元に戻す・不明にする）。［補足］に正規化値・出所・検索条件に使用/未使用・判定の根拠をまとめています。
- 右下: 商品候補（別の面と見出し帯）。機械の判定は日本語の要約で示し、原文・検索経路・内部IDは「検索の詳細」にまとめています。
  候補が2件以上あるときは、比較操作をしなくても「表示中の候補で異なる項目」を上部に出し、各候補では異なる仕様を青系で強調します（DB情報なしは不一致と区別）。
  原図・検索条件との不一致や生産終了は黄色系の注意として別に示します。2〜3件を選ぶ横並び比較は、詳しく確認する操作として残しています。

### 結果一覧・出力
管理記号、仮の器具名、採用品番、候補件数、確認状況、数量の確認状況、品番関係などの一覧と、JSON・CSVの出力。

## 状態と保存

| 区分 | 値 |
|---|---|
| 確認状態 | 未確認 / 保留 / 確認済み / 再確認が必要 |
| 数量の確認 | 数量未確認 / 数量確認済み / 数量読み取り困難（商品の確認とは別に保持） |
| 品番関係 | 品番1件 / 1器具の構成品 / 分割の確認が必要 / 品番同士の関係確認が必要 |
| 品番ごとの判断 | 未判断 / 採用 / 候補なし / 対象外（品番ごとに別々に保持） |

- 機械の `decision.selected_id` は参考表示だけで、人の採用結果には使いません。完全一致1件でも初期は未確認です。
- 採用は「採用したDBレコードID」「根拠になった検索ID」「そのときの入力の指紋」を保存します。
- 「候補なし」「対象外」も、判断したときの入力の指紋を保存します。採用だけでなくこれらも、条件が変わると「再確認が必要」に戻ります。
- 画面は毎回すべての品番の判断を送りますが、通常の保存では判断時の版を更新しません。更新するのは「この条件で判断し直す」を押した場合と、判断そのものを変えた場合だけです（APIでは各entryの `reaffirm`）。採用の版は根拠になった検索結果のものを使います。
- 再検索や修正保存で入力が変わると、判断の履歴は残したまま「再確認が必要」にします。
- 判断を変更すると、変更前の採用品番・DBレコードIDを履歴に残し、画面の「判断の履歴」で確認できます。
- 検索の「最新」は完了順ではなく要求順で決めます。要求が古い検索が後から終わっても、新しい結果を上書きしません（応答には `is_latest` を含めます）。
- 品番を書き換えたときは、取り込み時の hinban/kidou をそのまま優先しません。品番と食い違う分解値は検索条件から外し、画面に「この検索に使った識別子」を表示します。
- 分割の確認が必要・関係が未解決の対象は、確認済みにできません（保留で先に進めます）。
- 保存に失敗したときは成功表示をせず、編集内容を画面に残します。
- 器具を切り替えても未保存の編集は保持し、未保存件数を画面下に表示します。
- 遅れて返った検索結果は、対象IDと要求の連番で判定して破棄します。

## 出力

| 形式 | 内容 |
|---|---|
| JSON | 候補（最大20件）・一致項目・相違点・機械判定・修正内容・確認結果・判断時の版・元JSON |
| CSV | 対象ごとの確認一覧（UTF-8 BOM付き。Excelで文字化けしません） |

未確認・保留・再確認が必要も出力し、確認状態の列で確定済みと区別します。CSVは今回の確認一覧であり、既存見積システムへの正式な取り込み形式ではありません。

## 変換層の方針（`review_backend/ingest.py`）

実データで確認した差異に合わせています。

- ルートは `results` / `items` / 配列 / 単一オブジェクトを受け付ける。
- `full_model_number`（配列）・`brightness_lm`・`power_W`・`color_temperature_K` と、既存matcherの `product_code_raw`・`luminous_flux_lm`・`power_consumption_w` を対応付ける。
- `{"raw": ...}` と素の値、文字列・配列・nullの混在を吸収する。元JSONはそのまま保持する。
- 「相当品」などの注記は品番本体から分離して注記として残す。
- 複数品番は連結せず、品番ごとに別の検索単位にする。`A+B+C` は構成品として分解する。
- 読み取れない値から数値を作らない。`211?lm` のような不確か表記、`15W/m` のような単位違い、複数値は検索条件に使わず、原文と理由を残す。
- 未取得を0やfalseにしない。「不明」と「非対応・該当なし」を別の選択肢として持つ。
- 検索キーにできない寸法表記（`W28 H17 L=2,880mm` など）は条件に使わず、警告として残す。

### 品番同士の関係の判定

複数品番があるだけでは「複数器具の混在」と判定しません。

| 判定 | 根拠 |
|---|---|
| 1器具の構成品 | `+` 連結の構成品表記、または主品番1件＋構成品として記載された品番（本体＋ランプなど） |
| 分割の確認が必要 | 管理記号が複数、またはページ全体を1件として読み取った結果 |
| 品番同士の関係確認が必要 | 複数品番があるが、構成品か別器具かを判断できる根拠がない |

担当者が読み取り結果ペインで関係を選ぶと解決済みになります。器具の分割編集そのものは今回の範囲外です。

## 主要な設計判断

1. **照合処理は再実装しない。** `ProductMatcher` をスレッドごとの読み取り専用接続で呼ぶだけにし、CLIと既存テストの構成は変えていません。
2. **機械の結果と人の判断を別テーブルにした。** `searches`（機械）と `reviews` / `entry_decisions`（人）を分け、`selected_id` が人の採用に化けないようにしています。
3. **安定IDは (案件, 元ファイル, ページ, 器具No) から生成。** 表示順や仮の商品名に依存しません。器具Noが無い対象だけ取り込み順を補助的に使います。
4. **判断の版を指紋で持つ。** 検索入力を正規化JSONにしてSHA-256を取り、採用時の指紋と現在の指紋を比べて「再確認が必要」を出します。
5. **取り込み時に一括検索する。** 候補件数を最初から一覧に出せます（50件・約4秒）。
6. **画像は登録済みデータ領域の相対パスのみ。** APIは種別名（`item` / `page` など）だけを受け取り、解決後のパスがデータ領域配下であることを確認します。
7. **元データは読み取り専用。** 元PDF・CSV・解析JSON・商品DBは変更せず、ZIPも展開しません。作業データは `review_app/data/` にだけ書きます。
8. **作業DBは起動時に列を補う。** 既存の確認結果を消さずにスキーマを更新できるよう、`ReviewStore.MIGRATIONS` に定義した列だけを `ALTER TABLE` で足します。

## テスト

```powershell
cd review_app\backend
python -m unittest discover -s tests -v
```

```powershell
cd review_app\frontend
node "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\pnpm\bin\pnpm.mjs" run test
node "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\pnpm\bin\pnpm.mjs" run build
```

フロントのテストは Vitest + jsdom で、バックエンドや実データには接続しません（`src/__tests__/`）。

既存の照合処理のテストは従来どおりです。

```powershell
cd product_matching_system
python -m unittest discover -s tests -v
```

## 今回の範囲外

新たな画像解析API呼び出し、OCR精度改善、自動見積計算、見積システム接続、メール連携、PDFアップロードからの全自動処理、器具の分割編集。
PDF.jsは使っていません（全ページのレンダリング画像が前処理出力に揃っているため）。
