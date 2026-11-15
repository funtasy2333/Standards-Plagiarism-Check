"""DeepSeek OCR HTTP API client (https://api-docs.deepseek.com/zh-cn/guides/ocr)."""

from __future__ import annotations

import json
import mimetypes
import re
from pathlib import Path
from typing import Any

import httpx

from ..config import Settings
from ..models import OcrResult
from .base import OcrError, RemoteOcrClient, build_http_client, compute_file_sha256

# DeepSeek OCR page-by-page recognition inserts layout tags like:
# <｜ref｜>标题<｜/ref｜><｜box｜>[[52, 40, 948, 96]]<｜/box｜>
# Note: DeepSeek uses full-width vertical bar '｜' (U+FF5C), handle ASCII '|' as well.
_DEEPSEEK_BOX_TAG_RE = re.compile(
    r"<[｜|]box[｜|]>.*?<[｜|]/box[｜|]>",
    re.DOTALL,
)
_DEEPSEEK_REF_TAG_RE = re.compile(
    r"<[｜|]/?ref[｜|]>",
)
_DEEPSEEK_GROUNDING_RE = re.compile(
    r"<[｜|]det[｜|]>.*?<[｜|]/det[｜|]>",
    re.DOTALL,
)


def clean_deepseek_ocr_text(raw_text: str) -> str:
    """Strip DeepSeek layout grounding tags while keeping clean Markdown content."""
    text = _DEEPSEEK_BOX_TAG_RE.sub("", raw_text)
    text = _DEEPSEEK_GROUNDING_RE.sub("", text)
    text = _DEEPSEEK_REF_TAG_RE.sub("", text)
    # Collapse excessive blank lines produced after tag removal
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class DeepSeekOcrClient(RemoteOcrClient):
    """Remote OCR client calling POST https://api.deepseek.com/v1/tools/ocr."""

    engine_name = "deepseek"

    SUPPORTED_EXTENSIONS = {
        ".pdf",
        ".doc",
        ".docx",
        ".ppt",
        ".pptx",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        ".bmp",
        ".tiff",
        ".tif",
    }

    def __init__(self, settings: Settings, http_client: httpx.Client | None = None) -> None:
        super().__init__(settings)
        self._http_client = http_client

    def convert_to_markdown(
        self,
        file_path: Path,
        output_dir: Path | None = None,
        *,
        purpose: str | None = None,
        use_cache: bool = True,
    ) -> OcrResult:
        file_path = file_path.resolve()
        if not file_path.exists():
            raise OcrError(f"Input file not found: {file_path}")

        if file_path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise OcrError(
                f"Unsupported file extension {file_path.suffix!r} for DeepSeek OCR. "
                f"Supported: {sorted(self.SUPPORTED_EXTENSIONS)}"
            )

        chosen_purpose = purpose or self.settings.deepseek_ocr_purpose
        if chosen_purpose not in ("text_recognition", "rich_layout_recognition"):
            raise OcrError(
                f"Invalid DeepSeek OCR purpose {chosen_purpose!r}. "
                "Must be 'text_recognition' or 'rich_layout_recognition'."
            )

        sha256 = compute_file_sha256(file_path)
        output_md_path = (
            (output_dir / f"{file_path.stem}.md") if output_dir is not None else None
        )

        if use_cache:
            cached = self._try_load_cache(
                file_path, sha256, chosen_purpose, output_md_path=output_md_path
            )
            if cached is not None:
                return cached

        if not self.settings.deepseek_api_key:
            raise OcrError(
                "DEEPSEEK_API_KEY is not configured. Set it in environment or .env file."
            )

        file_size = file_path.stat().st_size
        if file_size > 100 * 1024 * 1024:
            raise OcrError(
                f"File {file_path.name} exceeds DeepSeek OCR 100 MiB limit ({file_size} bytes)."
            )

        payload_json = self._call_api(file_path, chosen_purpose)
        markdown_text, page_count = self._format_response_markdown(payload_json)

        raw_metadata = {
            "id": payload_json.get("id"),
            "purpose": payload_json.get("purpose", chosen_purpose),
            "usage": payload_json.get("usage", {}),
            "truncated_pages": [
                p.get("index")
                for p in payload_json.get("pages", [])
                if p.get("finish_reason") == "length"
            ],
        }

        return self._save_cache_and_output(
            source_file=file_path,
            sha256=sha256,
            suffix_key=chosen_purpose,
            markdown_text=markdown_text,
            page_count=page_count,
            output_md_path=output_md_path,
            raw_metadata=raw_metadata,
        )

    def _call_api(self, file_path: Path, purpose: str) -> dict[str, Any]:
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            mime_type = "application/octet-stream"

        headers = {"Authorization": f"Bearer {self.settings.deepseek_api_key}"}
        timeout = httpx.Timeout(
            connect=30.0,
            write=120.0,
            read=float(self.settings.deepseek_ocr_timeout_seconds),
            pool=30.0,
        )

        client = self._http_client or build_http_client(timeout)
        owns_client = self._http_client is None
        try:
            with file_path.open("rb") as f:
                files = {"file": (file_path.name, f, mime_type)}
                data = {"purpose": purpose}
                resp = client.post(
                    self.settings.deepseek_ocr_api_url,
                    headers=headers,
                    data=data,
                    files=files,
                )
        except httpx.HTTPError as exc:
            raise OcrError(f"DeepSeek OCR HTTP request error: {exc}") from exc
        finally:
            if owns_client:
                client.close()

        if resp.status_code != 200:
            detail = self._extract_error_detail(resp)
            raise OcrError(
                f"DeepSeek OCR API failed with HTTP {resp.status_code}: {detail}"
            )

        # Response body may contain leading keepalive newlines before the JSON object.
        body_text = resp.text.strip()
        try:
            payload = json.loads(body_text)
        except json.JSONDecodeError as exc:
            raise OcrError(
                f"Failed to parse DeepSeek OCR JSON response: {exc}. Body preview: {body_text[:200]}"
            ) from exc

        if "error" in payload and payload["error"]:
            err = payload["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise OcrError(f"DeepSeek OCR error: {msg}")

        return payload

    @staticmethod
    def _extract_error_detail(resp: httpx.Response) -> str:
        try:
            data = resp.json()
            if isinstance(data, dict) and "error" in data:
                err = data["error"]
                if isinstance(err, dict):
                    return err.get("message", str(err))
                return str(err)
            return str(data)
        except Exception:  # noqa: BLE001
            return resp.text.strip()[:300]

    @staticmethod
    def _format_response_markdown(payload: dict[str, Any]) -> tuple[str, int]:
        pages = payload.get("pages") or []
        page_count = int(payload.get("page_count", len(pages)))
        chunks: list[str] = []

        for idx, page in enumerate(pages):
            page_num = int(page.get("index", idx)) + 1
            raw_text = page.get("text", "")
            cleaned = clean_deepseek_ocr_text(raw_text)
            if not cleaned:
                continue
            chunks.append(f"<!-- page: {page_num} -->\n{cleaned}")

        return "\n\n".join(chunks).strip() + "\n", page_count
