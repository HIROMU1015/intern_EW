$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$checkRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvRoot = Join-Path $checkRoot ".venv"
$pythonExe = Join-Path $venvRoot "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonExe)) {
    Write-Host "初回準備: Python仮想環境を作成します。"
    python -m venv $venvRoot
}

if (-not (Test-Path -LiteralPath (Join-Path $venvRoot "Lib\site-packages\openai"))) {
    Write-Host "初回準備: 必要なパッケージをインストールします。"
    & $pythonExe -m pip install --disable-pip-version-check -r (Join-Path $checkRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "Pythonパッケージのインストールに失敗しました。"
    }
}

if (-not $env:AVILEN_LLM_API_KEY) {
    $savedApiKey = [Environment]::GetEnvironmentVariable("AVILEN_LLM_API_KEY", "User")
    if ($savedApiKey) {
        $env:AVILEN_LLM_API_KEY = $savedApiKey
    }
}

& $pythonExe (Join-Path $checkRoot "check_models.py")
exit $LASTEXITCODE
