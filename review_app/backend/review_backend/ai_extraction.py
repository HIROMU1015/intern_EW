"""登録済みの前処理画像をAVILENのOpenAI互換APIへ渡す層。"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import uuid
from pathlib import Path
from typing import Any, Callable

from .config import ResolvedSource, Settings
from .ingest import load_manifest_index

MAX_IMAGES_PER_RUN = 10
MAX_PDF_IMAGES = 120
MAX_IMAGE_BYTES = 10 * 1024 * 1024
PROVIDERS = {"openai", "google-ai", "bedrock"}

EXTRACTION_PROMPT = """あなたは照明器具の姿図から、検索前の読み取り結果だけを作成します。
渡された画像は一つの器具枠です。画像に見える内容のみを根拠に、JSONオブジェクトを一つ返してください。
商品DB、外部情報、一般知識による補完はしないでください。読めない値は null とし、曖昧な文字は raw に原文のまま残して uncertain_fields に項目名を加えてください。
複数の品番は配列に分け、主品番と構成品を区別できる場合だけ component_model_numbers に入れてください。別器具が混在している可能性があれば review_required=true としてください。
余分な説明やMarkdownは付けず、次のキーを持つJSONを返してください:
{
  "drawing_label": null,
  "identity": {
    "management_symbol": null,
    "manufacturer": null,
    "category": null,
    "product_name": null,
    "full_model_number": [],
    "hinban": null,
    "kidou": null,
    "component_model_numbers": []
  },
  "quantity": {"raw": null, "value": null, "unit": null},
  "specifications": {
    "brightness_lm": {"raw": null},
    "power_W": {"raw": null},
    "color_temperature_K": {"raw": null},
    "voltage_V": {"raw": null},
    "Ra": {"raw": null},
    "dimensions": {"raw": null},
    "cutout": {"raw": null},
    "mounting": {"raw": null},
    "dimming": {"raw": null},
    "waterproof": {"raw": null},
    "other": null
  },
  "raw_text": "",
  "uncertain_fields": [],
  "recognition_notes": [],
  "review_required": true
}
数量 value は数字が明確に読める場合だけ数値にし、見えない場合は null にしてください。"""


class ImageExtractionService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def status(self) -> dict[str, Any]:
        key_configured = bool(self.settings.ai_api_key)
        sdk_available = importlib.util.find_spec("openai") is not None
        configuration_valid = (
            self.settings.ai_provider in PROVIDERS
            and bool(self.settings.ai_model.strip())
            and self.settings.ai_base_url.startswith("https://")
        )
        return {
            "ready": key_configured and sdk_available and configuration_valid,
            "key_configured": key_configured,
            "sdk_available": sdk_available,
            "provider": self.settings.ai_provider,
            "model": self.settings.ai_model,
            "max_images_per_run": MAX_IMAGES_PER_RUN,
        }

    def _targets(self, source: ResolvedSource) -> dict[str, dict[str, Any]]:
        if source.manifest is None or source.image_root is None:
            raise ValueError("この取り込み元には画像とマニフェストが登録されていません。")
        if not source.manifest.is_file() or not source.image_root.is_dir():
            raise ValueError("前処理済み画像またはマニフェストが見つかりません。")
        index = load_manifest_index(source.manifest)
        result: dict[str, dict[str, Any]] = {}
        for page_key, page in sorted(index.items()):
            source_file, _, page_text = page_key.partition("#")
            for item_no, item in sorted(page["items"].items()):
                relative = item.get("recommended_image") or (item.get("image_variants") or {}).get("enhanced")
                if not relative and page.get("route") == "full_page_vision_review":
                    relative = page.get("rendered_page")
                raw_id = f"{source.key}|{source_file}|{page_text}|{item_no}"
                target_id = "t_" + hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:20]
                result[target_id] = {
                    "id": target_id,
                    "source_file": source_file,
                    "page": int(page_text),
                    "item_no": int(item_no),
                    "route": page.get("route"),
                    "image_path": relative,
                    "available": self._safe_image_path(source.image_root, relative) is not None,
                }
        return result

    @staticmethod
    def _safe_image_path(root: Path, relative: str | None) -> Path | None:
        if not relative or Path(relative).is_absolute():
            return None
        root = root.resolve()
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or path.suffix.lower() != ".png" or not path.is_file():
            return None
        if path.stat().st_size > MAX_IMAGE_BYTES:
            return None
        return path

    def targets(self, source: ResolvedSource) -> list[dict[str, Any]]:
        return [{key: value for key, value in target.items() if key != "image_path"} for target in self._targets(source).values()]

    def image_path(self, source: ResolvedSource, target_id: str) -> Path:
        target = self._targets(source).get(target_id)
        if target is None:
            raise ValueError("画像の対象が見つかりません。")
        assert source.image_root is not None
        path = self._safe_image_path(source.image_root, target["image_path"])
        if path is None:
            raise ValueError("画像が見つからないか、送信サイズの上限を超えています。")
        return path

    def _request_image(self, path: Path) -> tuple[dict[str, Any], dict[str, Any] | None]:
        from openai import OpenAI

        data_url = "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
        base_url = self.settings.ai_base_url.rstrip("/")
        with OpenAI(
            api_key=self.settings.ai_api_key,
            base_url=f"{base_url}/{self.settings.ai_provider}/",
            timeout=90.0,
            max_retries=0,
        ) as client:
            response = client.chat.completions.create(
                model=self.settings.ai_model,
                messages=[
                    {"role": "system", "content": EXTRACTION_PROMPT},
                    {"role": "user", "content": [{"type": "text", "text": "この器具枠を読み取ってください。"}, {"type": "image_url", "image_url": {"url": data_url}}]},
                ],
            )
        if not response.choices or response.choices[0].finish_reason != "stop":
            raise RuntimeError("画像解析APIの回答が途中で終了しました。")
        content = response.choices[0].message.content
        try:
            item = json.loads(content) if isinstance(content, str) else None
        except json.JSONDecodeError as error:
            raise RuntimeError("画像解析APIがJSONを返しませんでした。") from error
        usage = response.usage.model_dump() if response.usage is not None else None
        return item, usage

    @staticmethod
    def _validate_item(item: Any) -> dict[str, Any]:
        if not isinstance(item, dict) or not isinstance(item.get("identity"), dict) or not isinstance(item.get("specifications"), dict):
            raise RuntimeError("画像解析APIの回答形式が想定と異なります。")
        if item.get("quantity") is not None and not isinstance(item["quantity"], dict):
            raise RuntimeError("画像解析APIの数量形式が想定と異なります。")
        for name in ("uncertain_fields", "recognition_notes"):
            if item.get(name) is not None and not isinstance(item[name], list):
                raise RuntimeError("画像解析APIの回答形式が想定と異なります。")
        return item

    def run(
        self,
        source: ResolvedSource,
        target_ids: list[str],
        *,
        max_images: int = MAX_IMAGES_PER_RUN,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> tuple[ResolvedSource, list[dict[str, Any]]]:
        if not self.settings.ai_api_key:
            raise RuntimeError("APIキーが未設定です。サーバー側の設定後に実行できます。")
        if importlib.util.find_spec("openai") is None:
            raise RuntimeError("画像解析API用のPythonパッケージが未導入です。")
        if self.settings.ai_provider not in PROVIDERS or not self.settings.ai_model.strip() or not self.settings.ai_base_url.startswith("https://"):
            raise ValueError("画像解析APIの接続先、provider、model設定が不正です。")
        if not 1 <= len(target_ids) <= max_images or len(set(target_ids)) != len(target_ids):
            raise ValueError(f"画像は重複なく1～{max_images}件選択してください。")
        targets = self._targets(source)
        selected: list[tuple[dict[str, Any], Path]] = []
        for target_id in target_ids:
            target = targets.get(target_id)
            if target is None:
                raise ValueError("選択された画像が登録済みマニフェストにありません。")
            selected.append((target, self.image_path(source, target_id)))

        results: list[dict[str, Any]] = []
        usages: list[dict[str, Any]] = []
        for target, path in selected:
            try:
                item, usage = self._request_image(path)
            except RuntimeError:
                raise
            except Exception as error:
                raise RuntimeError("画像解析APIへの接続または応答に失敗しました。接続設定と対応モデルを確認してください。") from error
            item = self._validate_item(item)
            # 出所情報はモデルの出力を採用せず、登録済みマニフェストから確定する。
            item.update({
                "source_file": target["source_file"],
                "page": target["page"],
                "item_no": target["item_no"],
                "image_path": target["image_path"],
                "source_route": target["route"],
            })
            results.append(item)
            usages.append({"target_id": target["id"], "usage": usage})
            if on_progress is not None:
                on_progress(len(results), len(selected))

        run_id = uuid.uuid4().hex
        output_dir = self.settings.ai_extraction_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        analysis_path = output_dir / f"{run_id}.json"
        payload = {
            "schema_version": "gpt-direct-image-extraction-api/v1",
            "api_metadata": {"provider": self.settings.ai_provider, "model": self.settings.ai_model, "image_count": len(results), "usages": usages},
            "results": results,
        }
        analysis_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        generated = ResolvedSource(
            key=f"ai_{run_id}", label=f"API画像読取 {len(results)}件", format="gpt_direct_image_extraction",
            analysis_json=analysis_path, manifest=source.manifest, image_root=source.image_root,
            note="登録済み画像からのAPI読取結果。担当者による確認が必要。",
        )
        return generated, usages
