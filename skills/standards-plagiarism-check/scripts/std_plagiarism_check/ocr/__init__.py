"""Remote OCR clients (DeepSeek OCR API and Baidu PaddleOCR API/MCP)."""

from .base import OcrError, RemoteOcrClient, compute_file_sha256, create_ocr_client
from .deepseek_ocr import DeepSeekOcrClient, clean_deepseek_ocr_text
from .doc_converter import DocConversionError, convert_word_to_pdf
from .paddle_ocr import PaddleOcrClient

__all__ = [
    "OcrError",
    "RemoteOcrClient",
    "compute_file_sha256",
    "create_ocr_client",
    "DeepSeekOcrClient",
    "clean_deepseek_ocr_text",
    "DocConversionError",
    "convert_word_to_pdf",
    "PaddleOcrClient",
]
