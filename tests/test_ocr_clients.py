"""Tests for remote OCR clients (DeepSeek OCR & Baidu PaddleOCR) and Word->PDF routing."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx

from std_plagiarism_check.config import Settings
from std_plagiarism_check.ocr import (
    DeepSeekOcrClient,
    OcrError,
    PaddleOcrClient,
    clean_deepseek_ocr_text,
)


def test_clean_deepseek_ocr_tags() -> None:
    raw = (
        "<｜ref｜>## 5.1 硬件安全<｜/ref｜><｜box｜>[[52, 40, 948, 96]]<｜/box｜>\n"
        "<｜ref｜>设备应具备防拆解检测。<｜/ref｜><｜box｜>[[52, 120, 948, 180]]<｜/box｜>"
    )
    cleaned = clean_deepseek_ocr_text(raw)
    assert "<｜ref｜>" not in cleaned
    assert "<｜box｜>" not in cleaned
    assert "## 5.1 硬件安全" in cleaned
    assert "设备应具备防拆解检测。" in cleaned


@respx.mock
def test_deepseek_ocr_api_and_cache(tmp_path: Path) -> None:
    sample_pdf = tmp_path / "sample.pdf"
    sample_pdf.write_bytes(b"%PDF-1.4 fake pdf content")

    settings = Settings(
        deepseek_api_key="sk-test-123",
        cache_dir=tmp_path / "cache",
    )

    # Simulate keepalive newlines before JSON response
    response_body = "\n\n\n" + json.dumps(
        {
            "id": "ocr-test-1",
            "object": "ocr.result",
            "purpose": "text_recognition",
            "page_count": 2,
            "pages": [
                {
                    "index": 0,
                    "text": "<｜ref｜># 1 范围<｜/ref｜><｜box｜>[[10,10,90,20]]<｜/box｜>\n规定技术要求。",
                    "finish_reason": "stop",
                },
                {
                    "index": 1,
                    "text": "## 5.1 性能\n指标合格。",
                    "finish_reason": "stop",
                },
            ],
        }
    )

    route = respx.post("https://api.deepseek.com/v1/tools/ocr").mock(
        return_value=httpx.Response(200, text=response_body)
    )

    with httpx.Client(trust_env=False) as http_client:
        client = DeepSeekOcrClient(settings, http_client=http_client)
        out_dir = tmp_path / "out"
        res1 = client.convert_to_markdown(sample_pdf, output_dir=out_dir)

        assert route.call_count == 1
        assert res1.cached is False
        assert res1.page_count == 2
        assert "<!-- page: 1 -->" in res1.markdown_text
        assert "<!-- page: 2 -->" in res1.markdown_text
        assert "<｜box｜>" not in res1.markdown_text
        assert Path(res1.markdown_path).exists()

        # Second call should hit local SHA256 cache without making another HTTP request
        res2 = client.convert_to_markdown(sample_pdf, output_dir=out_dir)
        assert route.call_count == 1
        assert res2.cached is True
        assert res2.markdown_text == res1.markdown_text


@respx.mock
def test_paddle_ocr_aistudio_word_to_pdf_and_markdown(tmp_path: Path) -> None:
    sample_docx = tmp_path / "group_std.docx"
    sample_docx.write_bytes(b"PK\x03\x04 fake docx")
    fake_pdf = tmp_path / "converted.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 rendered")

    settings = Settings(
        paddleocr_mode="aistudio_api",
        paddleocr_api_url="https://mock.aistudio.baidu.com/layout-parsing",
        paddleocr_access_token="token-abc",
        cache_dir=tmp_path / "cache",
    )

    route = respx.post("https://mock.aistudio.baidu.com/layout-parsing").mock(
        return_value=httpx.Response(
            200,
            json={
                "logId": "log-1",
                "errorCode": 0,
                "errorMsg": "Success",
                "result": {
                    "layoutParsingResults": [
                        {"markdown": {"text": "# 1 范围\n适用工业网关。", "images": {}}},
                        {"markdown": {"text": "## 5.1 安全要求\n支持国密。", "images": {}}},
                    ]
                },
            },
        )
    )

    with httpx.Client(trust_env=False) as http_client:
        client = PaddleOcrClient(settings, http_client=http_client)
        with patch(
            "std_plagiarism_check.ocr.paddle_ocr.convert_word_to_pdf",
            return_value=fake_pdf,
        ) as mock_conv:
            res = client.convert_to_markdown(sample_docx, output_dir=tmp_path / "out")

    assert mock_conv.call_count == 1
    assert route.call_count == 1
    # Verify fileType == 0 (PDF) was sent after Word->PDF conversion
    sent_payload = json.loads(route.calls[0].request.content.decode("utf-8"))
    assert sent_payload["fileType"] == 0
    assert res.converted_pdf_path == str(fake_pdf.resolve())
    assert res.page_count == 2
    assert "## 5.1 安全要求" in res.markdown_text


def test_deepseek_requires_api_key(tmp_path: Path) -> None:
    sample_pdf = tmp_path / "doc.pdf"
    sample_pdf.write_bytes(b"%PDF-1.4")
    settings = Settings(deepseek_api_key="", cache_dir=tmp_path / "cache")
    client = DeepSeekOcrClient(settings)
    with pytest.raises(OcrError, match="DEEPSEEK_API_KEY"):
        client.convert_to_markdown(sample_pdf)
