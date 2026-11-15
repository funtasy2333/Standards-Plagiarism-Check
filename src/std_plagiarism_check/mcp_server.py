"""MCP Server (`std-check-mcp`) exposing OCR, clause parsing, workspace prep, and report generation tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:  # pragma: no cover - mcp v1 fallback
    from mcp.server.fastmcp import FastMCP as MCPServer  # type: ignore[no-redef]

from .config import load_settings
from .ocr import create_ocr_client
from .parser import parse_standard_markdown
from .workspace import generate_reports_from_workspace, prepare_workspace

mcp = MCPServer(
    "standards-plagiarism-check",
    instructions=(
        "Standards Plagiarism Check MCP Server: converts Word/PDF standards via remote OCR "
        "(DeepSeek OCR or Baidu PaddleOCR), splits GB/T 1.1 leaf clauses, validates Appendix B "
        "step-a standardization object consistency & step-b~d comparison assessments, and exports "
        "Markdown/JSON/HTML/DOCX/XLSX reports."
    ),
)


@mcp.tool()
def ocr_convert_standard(
    file_path: str,
    engine: Literal["deepseek", "paddleocr"] = "deepseek",
    purpose: str = "text_recognition",
    output_dir: str | None = None,
    use_cache: bool = True,
) -> str:
    """Convert a Word (.doc/.docx), PDF, or image standard file to Markdown using remote OCR.

    Note: When using `paddleocr` on Word documents, the file is automatically converted to PDF first.
    """
    settings = load_settings()
    client = create_ocr_client(engine, settings)
    in_path = Path(file_path)
    out_dir = Path(output_dir) if output_dir else in_path.parent
    result = client.convert_to_markdown(
        in_path, output_dir=out_dir, purpose=purpose, use_cache=use_cache
    )
    return json.dumps(
        {
            "source_file": result.source_file,
            "engine": result.engine,
            "markdown_path": result.markdown_path,
            "page_count": result.page_count,
            "cached": result.cached,
            "converted_pdf_path": result.converted_pdf_path,
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def parse_standard_clauses(
    markdown_path: str,
    standard_role: Literal["target", "reference"] = "target",
    standard_id: str | None = None,
    output_json_path: str | None = None,
) -> str:
    """Parse a standard Markdown file per GB/T 1.1 into metadata, chapter overviews, and leaf clauses.

    Automatically marks Preface, Introduction, Chapter 1 (Scope), Chapter 2 (Normative References),
    Chapter 3 (Terms and Definitions), Informative Appendices, and Bibliography as excluded from n1.
    """
    md_file = Path(markdown_path)
    md_text = md_file.read_text(encoding="utf-8")
    parsed = parse_standard_markdown(
        md_text,
        standard_id=standard_id or md_file.stem,
        role=standard_role,
        markdown_file=str(md_file.resolve()),
    )
    out_path = Path(output_json_path) if output_json_path else md_file.with_suffix(".parsed.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(parsed.model_dump_json(indent=2), encoding="utf-8")

    return json.dumps(
        {
            "parsed_json_path": str(out_path.resolve()),
            "metadata": parsed.metadata.model_dump(),
            "chapters": [c.model_dump() for c in parsed.chapters],
            "candidate_leaf_clause_count": len(parsed.candidate_leaf_clauses),
            "total_leaf_clause_count": len(parsed.all_leaf_clauses),
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def prepare_comparison_workspace(
    target_file: str,
    reference_files: list[str],
    ocr_engine: Literal["deepseek", "paddleocr"] = "deepseek",
    workspace_dir: str = "./std_check_workspace",
    purpose: str = "text_recognition",
    use_cache: bool = True,
) -> str:
    """End-to-end workspace preparation: remote OCR + GB/T 1.1 leaf-clause parsing for 1 target + N reference standards.

    Produces parsed/*.json, manifest.json, and assessment_template.json for host Agent semantic evaluation.
    """
    settings = load_settings()
    manifest = prepare_workspace(
        target_file=Path(target_file),
        reference_files=[Path(p) for p in reference_files],
        workspace_dir=Path(workspace_dir),
        ocr_engine=ocr_engine,
        purpose=purpose,
        settings=settings,
        use_cache=use_cache,
    )
    return json.dumps(manifest, ensure_ascii=False, indent=2)


@mcp.tool()
def generate_plagiarism_reports(
    workspace_dir: str,
    assessment_json_path: str,
    output_dir: str = "./reports",
    strict_clause_coverage: bool = False,
) -> str:
    """Validate host Agent assessment JSON, compute Appendix B formula R = (n2/n1)*100%, and export MD/JSON/HTML/DOCX/XLSX."""
    report, exported_files = generate_reports_from_workspace(
        workspace_dir=Path(workspace_dir),
        assessment_json_path=Path(assessment_json_path),
        output_dir=Path(output_dir),
        strict_clause_coverage=strict_clause_coverage,
    )
    return json.dumps(
        {
            "n1": report.n1,
            "n2": report.n2,
            "duplicate_rate_percent": report.duplicate_rate_percent,
            "weighted_duplicate_rate_percent": report.weighted_duplicate_rate_percent,
            "eligible_reference_ids": report.eligible_reference_ids,
            "ineligible_reference_ids": report.ineligible_reference_ids,
            "warnings": report.warnings,
            "exported_files": {k: str(v) for k, v in exported_files.items()},
        },
        ensure_ascii=False,
        indent=2,
    )


def main() -> None:
    """Run the stdio MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
