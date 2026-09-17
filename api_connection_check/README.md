# AI API接続確認用の最小環境

AVILEN LLM API Gatewayの次の3接続先へ、`Reply with exactly OK.` という最小リクエストを1回ずつ送ります。

- `openai / openai.gpt-5.5`
- `google-ai / google-ai.gemini-3.5-flash`
- `bedrock / bedrock.claude-sonnet-5`

## 実行方法

Windowsでは `接続確認.cmd` をダブルクリックします。

初回だけ、このフォルダー内に `.venv` を作成してOpenAI Python SDKをインストールします。APIキーは、Windowsに保存済みの `AVILEN_LLM_API_KEY` を自動で読み込みます。保存されていない場合は実行時に入力します。入力値は画面に表示されず、ファイルにも保存されません。

PowerShellから実行する場合:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\api_connection_check\run.ps1
```

3回のAPI呼び出し結果、応答時間、APIが返した合計トークン数を表示します。HTTP 403の場合は、接続先には到達しているものの、APIキーに利用権限がありません。
