"""AVILEN LLM API Gateway の3接続先を最小リクエストで確認する。"""

from __future__ import annotations

import getpass
import time
from dataclasses import dataclass

from openai import OpenAI

BASE_URL = "https://llmapi.ops.avilen.co.jp/v2/summer-intern-team-d-three"
TARGETS = (
    ("openai", "openai.gpt-5.5"),
    ("google-ai", "google-ai.gemini-3.5-flash"),
    ("bedrock", "bedrock.claude-sonnet-5"),
)


@dataclass(frozen=True)
class CheckResult:
    provider: str
    model: str
    success: bool
    detail: str
    elapsed_seconds: float
    total_tokens: int | None = None


def load_api_key() -> str:
    api_key = getpass.getpass("AVILEN_LLM_API_KEYを入力してください（画面には表示されません）: ").strip()
    if not api_key:
        raise SystemExit("APIキーが入力されていません。")
    return api_key


def check_target(api_key: str, provider: str, model: str) -> CheckResult:
    started = time.perf_counter()
    try:
        with OpenAI(
            api_key=api_key,
            base_url=f"{BASE_URL}/{provider}/",
            timeout=90.0,
            max_retries=0,
        ) as client:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Reply with exactly OK."}],
            )

        content = (response.choices[0].message.content or "").strip()
        usage = getattr(response, "usage", None)
        total_tokens = getattr(usage, "total_tokens", None) if usage else None
        return CheckResult(
            provider=provider,
            model=model,
            success=content == "OK",
            detail=content or "空の応答",
            elapsed_seconds=time.perf_counter() - started,
            total_tokens=total_tokens,
        )
    except Exception as error:
        status_code = getattr(error, "status_code", None)
        if status_code == 403:
            detail = "HTTP 403: APIキーに接続先またはモデルの利用権限がありません"
        else:
            first_line = str(error).splitlines()[0][:180]
            detail = f"{type(error).__name__}: {first_line}"
        return CheckResult(
            provider=provider,
            model=model,
            success=False,
            detail=detail,
            elapsed_seconds=time.perf_counter() - started,
        )


def main() -> int:
    api_key = load_api_key()
    print(f"接続先: {BASE_URL}")
    print("APIキー: 設定済み（値は表示しません）\n")

    results = [check_target(api_key, provider, model) for provider, model in TARGETS]
    for result in results:
        status = "OK" if result.success else "NG"
        usage = f", tokens={result.total_tokens}" if result.total_tokens is not None else ""
        print(
            f"{status}  {result.provider:10} {result.model:30} "
            f"{result.elapsed_seconds:6.2f}s{usage}  {result.detail}"
        )

    succeeded = sum(result.success for result in results)
    print(f"\n結果: {succeeded}/{len(results)} 接続成功")
    return 0 if succeeded == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
