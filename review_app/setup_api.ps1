# Run once on Windows to remember the image-analysis API settings for this user.
$ErrorActionPreference = 'Stop'

$secureKey = Read-Host '画像解析APIキー（入力は表示されません）' -AsSecureString
if ($secureKey.Length -eq 0) {
    throw 'APIキーが空です。設定は保存していません。'
}

$baseUrl = (Read-Host '概要PDFに記載されたBASE/PROJECTのURL').Trim()
$uri = $null
if (-not [Uri]::TryCreate($baseUrl, [UriKind]::Absolute, [ref]$uri) -or
    $uri.Scheme -ne 'https' -or $uri.Query -or $uri.Fragment) {
    throw 'BASE/PROJECTにはhttps://で始まるURLを入力してください。設定は保存していません。'
}

$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
    [Environment]::SetEnvironmentVariable('AVILEN_LLM_API_KEY', $apiKey, 'User')
    [Environment]::SetEnvironmentVariable('AVILEN_LLM_API_KEY', $apiKey, 'Process')
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
    Remove-Variable apiKey -ErrorAction SilentlyContinue
}

[Environment]::SetEnvironmentVariable('AVILEN_LLM_BASE_URL', $baseUrl, 'User')
[Environment]::SetEnvironmentVariable('AVILEN_LLM_BASE_URL', $baseUrl, 'Process')

Write-Host 'API設定をこのWindowsユーザーに保存しました。バックエンドを再起動すると有効になります。'
