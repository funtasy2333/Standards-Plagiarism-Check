"""Word (.doc/.docx) to PDF converter for OCR backends that only accept PDF/images."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .base import OcrError


class DocConversionError(OcrError):
    """Raised when a Word document cannot be rendered to PDF."""


WORD_EXTENSIONS = {".doc", ".docx", ".wps", ".rtf"}


def _find_libreoffice_binary(explicit_path: str = "") -> str | None:
    if explicit_path:
        p = Path(explicit_path)
        if p.exists():
            return str(p)
        found = shutil.which(explicit_path)
        if found:
            return found

    for candidate in ("soffice", "libreoffice"):
        found = shutil.which(candidate)
        if found:
            return found
    return None


def convert_word_to_pdf(
    word_path: Path,
    output_dir: Path,
    *,
    libreoffice_path: str = "",
    timeout_seconds: int = 120,
) -> Path:
    """Convert a .doc/.docx file to PDF so image/PDF-only OCR engines (e.g. PaddleOCR) can process it.

    Tries LibreOffice headless conversion first, then optional docx2pdf.
    """
    word_path = word_path.resolve()
    if not word_path.exists():
        raise DocConversionError(f"Word file does not exist: {word_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    expected_pdf = output_dir / f"{word_path.stem}.pdf"

    soffice = _find_libreoffice_binary(libreoffice_path)
    if soffice:
        cmd = [
            soffice,
            "--headless",
            "--norestore",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(word_path),
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.SubprocessError as exc:
            raise DocConversionError(f"LibreOffice conversion failed: {exc}") from exc

        if proc.returncode == 0 and expected_pdf.exists():
            return expected_pdf
        raise DocConversionError(
            f"LibreOffice exited with code {proc.returncode} converting {word_path.name}: "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )

    # Optional fallback: docx2pdf (Windows/macOS Microsoft Word automation)
    try:
        from docx2pdf import convert as docx2pdf_convert  # type: ignore

        docx2pdf_convert(str(word_path), str(expected_pdf))
        if expected_pdf.exists():
            return expected_pdf
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        raise DocConversionError(f"docx2pdf conversion failed: {exc}") from exc

    raise DocConversionError(
        "Baidu PaddleOCR only accepts PDF/image files, and automatic Word-to-PDF conversion "
        "requires LibreOffice (`soffice` / `libreoffice`) or `docx2pdf` to be installed. "
        "Please install LibreOffice (or set LIBREOFFICE_PATH), convert the file to PDF manually, "
        "or switch to `--engine deepseek` which natively supports .doc/.docx."
    )
