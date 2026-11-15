"""Base remote OCR interface, SHA256 file hashing, and local Markdown caching."""

from __future__ import annotations

import hashlib
import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Literal

import httpx

from ..config import Settings
from ..models import OcrResult


class OcrError(RuntimeError):
    """Raised when a remote OCR operation fails or configuration is invalid."""


def build_http_client(timeout: httpx.Timeout) -> httpx.Client:
    """Create an httpx.Client, gracefully handling malformed NO_PROXY entries like [::1]."""
    try:
        return httpx.Client(timeout=timeout)
    except httpx.InvalidURL:
        proxy_url = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
        return httpx.Client(timeout=timeout, trust_env=False, proxy=proxy_url or None)


def compute_file_sha256(file_path: Path) -> str:
    """Compute SHA256 hex digest of a file."""
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


class RemoteOcrClient(ABC):
    """Abstract base class for remote OCR document converters."""

    engine_name: Literal["deepseek", "paddleocr"]

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @abstractmethod
    def convert_to_markdown(
        self,
        file_path: Path,
        output_dir: Path | None = None,
        *,
        purpose: str | None = None,
        use_cache: bool = True,
    ) -> OcrResult:
        """Convert a Word/PDF/image standard document to Markdown via remote OCR."""

    def _cache_paths(
        self, sha256: str, engine: str, suffix_key: str, cache_root: Path
    ) -> tuple[Path, Path]:
        cache_dir = cache_root / engine
        cache_dir.mkdir(parents=True, exist_ok=True)
        base = cache_dir / f"{sha256[:16]}_{suffix_key}"
        return base.with_suffix(".md"), base.with_suffix(".meta.json")

    def _try_load_cache(
        self,
        source_file: Path,
        sha256: str,
        suffix_key: str,
        output_md_path: Path | None = None,
    ) -> OcrResult | None:
        md_cache, meta_cache = self._cache_paths(
            sha256, self.engine_name, suffix_key, self.settings.cache_dir
        )
        if not md_cache.exists() or not meta_cache.exists():
            return None

        md_text = md_cache.read_text(encoding="utf-8")
        meta = json.loads(meta_cache.read_text(encoding="utf-8"))

        final_md_path = output_md_path or md_cache
        if output_md_path is not None:
            output_md_path.parent.mkdir(parents=True, exist_ok=True)
            output_md_path.write_text(md_text, encoding="utf-8")

        return OcrResult(
            source_file=str(source_file.resolve()),
            source_sha256=sha256,
            engine=self.engine_name,
            markdown_path=str(final_md_path.resolve()),
            markdown_text=md_text,
            page_count=int(meta.get("page_count", 0)),
            converted_pdf_path=meta.get("converted_pdf_path"),
            cached=True,
            raw_metadata=meta.get("raw_metadata", {}),
        )

    def _save_cache_and_output(
        self,
        source_file: Path,
        sha256: str,
        suffix_key: str,
        markdown_text: str,
        page_count: int,
        output_md_path: Path | None = None,
        converted_pdf_path: str | None = None,
        raw_metadata: dict | None = None,
    ) -> OcrResult:
        md_cache, meta_cache = self._cache_paths(
            sha256, self.engine_name, suffix_key, self.settings.cache_dir
        )
        md_cache.write_text(markdown_text, encoding="utf-8")
        meta_payload = {
            "source_file": str(source_file.resolve()),
            "source_sha256": sha256,
            "engine": self.engine_name,
            "page_count": page_count,
            "converted_pdf_path": converted_pdf_path,
            "raw_metadata": raw_metadata or {},
        }
        meta_cache.write_text(
            json.dumps(meta_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        final_md_path = output_md_path or md_cache
        if output_md_path is not None:
            output_md_path.parent.mkdir(parents=True, exist_ok=True)
            output_md_path.write_text(markdown_text, encoding="utf-8")

        return OcrResult(
            source_file=str(source_file.resolve()),
            source_sha256=sha256,
            engine=self.engine_name,
            markdown_path=str(final_md_path.resolve()),
            markdown_text=markdown_text,
            page_count=page_count,
            converted_pdf_path=converted_pdf_path,
            cached=False,
            raw_metadata=raw_metadata or {},
        )


def create_ocr_client(
    engine: Literal["deepseek", "paddleocr"] | None,
    settings: Settings,
) -> RemoteOcrClient:
    """Factory returning the requested remote OCR client."""
    from .deepseek_ocr import DeepSeekOcrClient
    from .paddle_ocr import PaddleOcrClient

    chosen = (engine or settings.default_ocr_engine).lower()
    if chosen == "deepseek":
        return DeepSeekOcrClient(settings)
    if chosen == "paddleocr":
        return PaddleOcrClient(settings)
    raise OcrError(f"Unsupported OCR engine: {chosen!r}. Expected 'deepseek' or 'paddleocr'.")
