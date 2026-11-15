"""Configuration management for remote OCR engines and workspace paths."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Application settings loaded from environment variables and .env files."""

    default_ocr_engine: Literal["deepseek", "paddleocr"] = Field(
        default="deepseek", description="Default remote OCR backend."
    )
    cache_dir: Path = Field(
        default=Path(".std_check_cache"),
        description="Directory for caching OCR Markdown outputs.",
    )

    # DeepSeek OCR API
    deepseek_api_key: str = Field(default="")
    deepseek_ocr_api_url: str = Field(default="https://api.deepseek.com/v1/tools/ocr")
    deepseek_ocr_purpose: Literal["text_recognition", "rich_layout_recognition"] = Field(
        default="text_recognition"
    )
    deepseek_ocr_timeout_seconds: int = Field(default=180)

    # Baidu PaddleOCR
    paddleocr_mode: Literal["aistudio_api", "mcp"] = Field(default="aistudio_api")
    paddleocr_api_url: str = Field(default="")
    paddleocr_access_token: str = Field(default="")
    paddleocr_timeout_seconds: int = Field(default=180)

    # Baidu PaddleOCR MCP Client
    paddleocr_mcp_transport: Literal["stdio", "streamable_http"] = Field(default="stdio")
    paddleocr_mcp_command: str = Field(default="paddleocr_mcp")
    paddleocr_mcp_model: str = Field(default="PP-StructureV3")
    paddleocr_mcp_source: str = Field(default="aistudio")
    paddleocr_mcp_server_url: str = Field(default="")
    paddleocr_mcp_tool_name: str = Field(default="pp_structurev3")

    # Word -> PDF conversion helper (used when sending Word files to PaddleOCR)
    libreoffice_path: str = Field(default="")


def load_settings(env_file: Path | str | None = None) -> Settings:
    """Load settings from optional .env file and current process environment."""
    if env_file is not None:
        load_dotenv(dotenv_path=env_file, override=False)
    else:
        load_dotenv(override=False)

    default_engine = os.getenv("STD_CHECK_DEFAULT_OCR_ENGINE", "deepseek").strip().lower()
    if default_engine not in ("deepseek", "paddleocr"):
        default_engine = "deepseek"

    purpose = os.getenv("DEEPSEEK_OCR_PURPOSE", "text_recognition").strip()
    if purpose not in ("text_recognition", "rich_layout_recognition"):
        purpose = "text_recognition"

    paddle_mode = os.getenv("PADDLEOCR_MODE", "aistudio_api").strip().lower()
    if paddle_mode not in ("aistudio_api", "mcp"):
        paddle_mode = "aistudio_api"

    paddle_transport = os.getenv("PADDLEOCR_MCP_TRANSPORT", "stdio").strip().lower()
    if paddle_transport not in ("stdio", "streamable_http"):
        paddle_transport = "stdio"

    return Settings(
        default_ocr_engine=default_engine,  # type: ignore[arg-type]
        cache_dir=Path(os.getenv("STD_CHECK_CACHE_DIR", ".std_check_cache")),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
        deepseek_ocr_api_url=os.getenv(
            "DEEPSEEK_OCR_API_URL", "https://api.deepseek.com/v1/tools/ocr"
        ).strip(),
        deepseek_ocr_purpose=purpose,  # type: ignore[arg-type]
        deepseek_ocr_timeout_seconds=int(os.getenv("DEEPSEEK_OCR_TIMEOUT_SECONDS", "180")),
        paddleocr_mode=paddle_mode,  # type: ignore[arg-type]
        paddleocr_api_url=os.getenv("PADDLEOCR_API_URL", "").strip(),
        paddleocr_access_token=os.getenv("PADDLEOCR_ACCESS_TOKEN", "").strip(),
        paddleocr_timeout_seconds=int(os.getenv("PADDLEOCR_TIMEOUT_SECONDS", "180")),
        paddleocr_mcp_transport=paddle_transport,  # type: ignore[arg-type]
        paddleocr_mcp_command=os.getenv("PADDLEOCR_MCP_COMMAND", "paddleocr_mcp").strip(),
        paddleocr_mcp_model=os.getenv("PADDLEOCR_MCP_MODEL", "PP-StructureV3").strip(),
        paddleocr_mcp_source=os.getenv("PADDLEOCR_MCP_SOURCE", "aistudio").strip(),
        paddleocr_mcp_server_url=os.getenv("PADDLEOCR_MCP_SERVER_URL", "").strip(),
        paddleocr_mcp_tool_name=os.getenv("PADDLEOCR_MCP_TOOL_NAME", "pp_structurev3").strip(),
        libreoffice_path=os.getenv("LIBREOFFICE_PATH", "").strip(),
    )
