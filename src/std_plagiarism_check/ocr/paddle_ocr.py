"""Baidu PaddleOCR client supporting AI Studio HTTP API and paddleocr-mcp."""

from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path
from typing import Any

import httpx

from ..config import Settings
from ..models import OcrResult
from .base import OcrError, RemoteOcrClient, build_http_client, compute_file_sha256
from .doc_converter import WORD_EXTENSIONS, convert_word_to_pdf


class PaddleOcrClient(RemoteOcrClient):
    """Remote OCR client using Baidu PaddleOCR (AI Studio API or paddleocr-mcp).

    Automatically converts Word (.doc/.docx) files to PDF before calling PaddleOCR.
    """

    engine_name = "paddleocr"

    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".tif"}
    PDF_EXTENSIONS = {".pdf"}

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

        ext = file_path.suffix.lower()
        if ext not in (WORD_EXTENSIONS | self.PDF_EXTENSIONS | self.IMAGE_EXTENSIONS):
            raise OcrError(f"Unsupported file type {ext!r} for Baidu PaddleOCR.")

        sha256 = compute_file_sha256(file_path)
        mode = self.settings.paddleocr_mode
        output_md_path = (
            (output_dir / f"{file_path.stem}.md") if output_dir is not None else None
        )

        if use_cache:
            cached = self._try_load_cache(
                file_path, sha256, mode, output_md_path=output_md_path
            )
            if cached is not None:
                return cached

        converted_pdf_path: str | None = None
        ocr_input_path = file_path

        if ext in WORD_EXTENSIONS:
            pdf_cache_dir = self.settings.cache_dir / "converted_pdfs"
            converted_pdf = convert_word_to_pdf(
                file_path,
                pdf_cache_dir,
                libreoffice_path=self.settings.libreoffice_path,
            )
            ocr_input_path = converted_pdf
            converted_pdf_path = str(converted_pdf.resolve())

        if mode == "aistudio_api":
            markdown_text, page_count, raw_meta = self._call_aistudio_api(ocr_input_path)
        elif mode == "mcp":
            markdown_text, page_count, raw_meta = self._call_paddleocr_mcp(ocr_input_path)
        else:
            raise OcrError(f"Unsupported PaddleOCR mode: {mode!r}")

        return self._save_cache_and_output(
            source_file=file_path,
            sha256=sha256,
            suffix_key=mode,
            markdown_text=markdown_text,
            page_count=page_count,
            output_md_path=output_md_path,
            converted_pdf_path=converted_pdf_path,
            raw_metadata=raw_meta,
        )

    def _call_aistudio_api(self, input_path: Path) -> tuple[str, int, dict[str, Any]]:
        if not self.settings.paddleocr_api_url:
            raise OcrError(
                "PADDLEOCR_API_URL is not configured. Obtain it from https://aistudio.baidu.com/paddleocr/task"
            )
        if not self.settings.paddleocr_access_token:
            raise OcrError(
                "PADDLEOCR_ACCESS_TOKEN is not configured. Obtain it from Baidu AI Studio."
            )

        file_bytes = input_path.read_bytes()
        file_b64 = base64.b64encode(file_bytes).decode("ascii")
        file_type = 0 if input_path.suffix.lower() == ".pdf" else 1

        headers = {
            "Authorization": f"token {self.settings.paddleocr_access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "file": file_b64,
            "fileType": file_type,
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
            "useChartRecognition": False,
        }

        timeout = httpx.Timeout(
            connect=30.0,
            write=120.0,
            read=float(self.settings.paddleocr_timeout_seconds),
            pool=30.0,
        )
        client = self._http_client or build_http_client(timeout)
        owns_client = self._http_client is None
        try:
            resp = client.post(
                self.settings.paddleocr_api_url,
                headers=headers,
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise OcrError(f"Baidu PaddleOCR HTTP request error: {exc}") from exc
        finally:
            if owns_client:
                client.close()

        if resp.status_code != 200:
            raise OcrError(
                f"Baidu PaddleOCR API failed with HTTP {resp.status_code}: {resp.text[:300]}"
            )

        data = resp.json()
        if data.get("errorCode", 0) != 0:
            raise OcrError(
                f"Baidu PaddleOCR API error ({data.get('errorCode')}): {data.get('errorMsg')}"
            )

        result = data.get("result") or {}
        pages = result.get("layoutParsingResults") or []
        chunks: list[str] = []

        for idx, page in enumerate(pages):
            md_obj = page.get("markdown") or {}
            text = (md_obj.get("text") or "").strip()
            if text:
                chunks.append(f"<!-- page: {idx + 1} -->\n{text}")

        # Fallback if PP-OCRv5 basic OCR API format is returned
        if not chunks and "ocrResults" in result:
            for idx, page in enumerate(result["ocrResults"]):
                rec_texts = (
                    page.get("prunedResult", {}).get("rec_texts")
                    or page.get("rec_texts")
                    or []
                )
                joined = "\n".join(str(t) for t in rec_texts if t)
                if joined.strip():
                    chunks.append(f"<!-- page: {idx + 1} -->\n{joined.strip()}")

        if not chunks:
            raise OcrError(
                f"Baidu PaddleOCR returned no recognizable Markdown text. logId={data.get('logId')}"
            )

        return (
            "\n\n".join(chunks).strip() + "\n",
            len(pages) or len(chunks),
            {"logId": data.get("logId"), "mode": "aistudio_api"},
        )

    def _call_paddleocr_mcp(self, input_path: Path) -> tuple[str, int, dict[str, Any]]:
        try:
            return asyncio.run(self._call_paddleocr_mcp_async(input_path))
        except RuntimeError as exc:
            # Handle case where an event loop is already running (e.g. inside async MCP server)
            if "running event loop" in str(exc):
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return pool.submit(
                        lambda: asyncio.run(self._call_paddleocr_mcp_async(input_path))
                    ).result()
            raise

    async def _call_paddleocr_mcp_async(
        self, input_path: Path
    ) -> tuple[str, int, dict[str, Any]]:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        transport = self.settings.paddleocr_mcp_transport
        tool_name = self.settings.paddleocr_mcp_tool_name
        file_type = 0 if input_path.suffix.lower() == ".pdf" else 1
        arguments: dict[str, Any] = {
            "input_data": str(input_path),
            "file_type": file_type,
        }

        if transport == "stdio":
            env = dict(os.environ)
            env["PADDLEOCR_MCP_MODEL"] = self.settings.paddleocr_mcp_model
            env["PADDLEOCR_MCP_PPOCR_SOURCE"] = self.settings.paddleocr_mcp_source
            if self.settings.paddleocr_access_token:
                env["PADDLEOCR_MCP_AISTUDIO_ACCESS_TOKEN"] = (
                    self.settings.paddleocr_access_token
                )
            if self.settings.paddleocr_api_url:
                env["PADDLEOCR_MCP_AISTUDIO_BASE_URL"] = self.settings.paddleocr_api_url

            server_params = StdioServerParameters(
                command=self.settings.paddleocr_mcp_command,
                args=[],
                env=env,
            )
            async with stdio_client(server_params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
        elif transport == "streamable_http":
            if not self.settings.paddleocr_mcp_server_url:
                raise OcrError(
                    "PADDLEOCR_MCP_SERVER_URL must be set when PADDLEOCR_MCP_TRANSPORT=streamable_http."
                )
            try:
                from mcp.client.streamable_http import streamable_http_client as http_client_cm
            except ImportError:  # pragma: no cover - mcp v1 fallback
                from mcp.client.streamable_http import streamablehttp_client as http_client_cm  # type: ignore[no-redef]

            async with http_client_cm(self.settings.paddleocr_mcp_server_url) as streams:
                read_stream, write_stream = streams[0], streams[1]
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
        else:
            raise OcrError(f"Unsupported PaddleOCR MCP transport: {transport!r}")

        texts: list[str] = []
        for item in getattr(result, "content", []) or []:
            text_val = getattr(item, "text", None)
            if text_val:
                texts.append(text_val)

        combined = "\n\n".join(texts).strip()
        if not combined:
            raise OcrError("paddleocr-mcp returned empty content.")

        # If MCP returns JSON string with markdown field, unwrap it cleanly
        try:
            parsed = json.loads(combined)
            if isinstance(parsed, dict) and "markdown" in parsed:
                combined = str(parsed["markdown"]).strip()
            elif isinstance(parsed, list):
                md_parts = [
                    p.get("markdown", str(p)) if isinstance(p, dict) else str(p)
                    for p in parsed
                ]
                combined = "\n\n".join(md_parts).strip()
        except json.JSONDecodeError:
            pass

        page_count = max(1, combined.count("<!-- page:"))
        return combined + "\n", page_count, {"mode": "mcp", "tool": tool_name}
