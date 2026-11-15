"""Report exporters for Markdown, JSON, HTML, Word (.docx), and Excel (.xlsx)."""

from __future__ import annotations

from pathlib import Path

from ..models import PlagiarismReportResult
from .docx_exporter import export_docx_report
from .html_exporter import export_html_report, render_html_report
from .md_exporter import export_markdown_report, render_markdown_report
from .xlsx_exporter import export_xlsx_report


def export_json_report(report: PlagiarismReportResult, output_path: Path) -> Path:
    """Write full traceable PlagiarismReportResult JSON to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return output_path


def export_all_reports(
    report: PlagiarismReportResult,
    output_dir: Path,
    base_name: str = "plagiarism_report",
) -> dict[str, Path]:
    """Export all 5 report formats (.md, .json, .html, .docx, .xlsx) to output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    return {
        "markdown": export_markdown_report(report, output_dir / f"{base_name}.md"),
        "json": export_json_report(report, output_dir / f"{base_name}.json"),
        "html": export_html_report(report, output_dir / f"{base_name}.html"),
        "docx": export_docx_report(report, output_dir / f"{base_name}.docx"),
        "xlsx": export_xlsx_report(report, output_dir / f"{base_name}.xlsx"),
    }


__all__ = [
    "export_all_reports",
    "export_markdown_report",
    "export_json_report",
    "export_html_report",
    "export_docx_report",
    "export_xlsx_report",
    "render_markdown_report",
    "render_html_report",
]
