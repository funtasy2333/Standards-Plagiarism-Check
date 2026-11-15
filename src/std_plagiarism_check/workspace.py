"""Shared workspace orchestration for CLI and MCP Server."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from .calculator import calculate_plagiarism_report
from .config import Settings, load_settings
from .exporters import export_all_reports
from .models import (
    ChapterScopeDecision,
    ClauseComparison,
    ClauseVerdict,
    ComparisonAssessment,
    ObjectConsistency,
    ObjectConsistencyResult,
    ParsedStandard,
    PlagiarismReportResult,
)
from .ocr import create_ocr_client
from .parser import parse_standard_markdown


def prepare_workspace(
    target_file: Path,
    reference_files: list[Path],
    workspace_dir: Path,
    *,
    ocr_engine: Literal["deepseek", "paddleocr"] | None = None,
    purpose: str | None = None,
    settings: Settings | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Run remote OCR and GB/T 1.1 leaf-clause parsing for target + references.

    Writes structured files into `workspace_dir`:
    - markdown/*.md
    - parsed/target.json, parsed/ref_1.json, ...
    - manifest.json
    - assessment_template.json (ready for host Agent completion)
    """
    cfg = settings or load_settings()
    client = create_ocr_client(ocr_engine, cfg)

    workspace_dir = workspace_dir.resolve()
    md_dir = workspace_dir / "markdown"
    parsed_dir = workspace_dir / "parsed"
    md_dir.mkdir(parents=True, exist_ok=True)
    parsed_dir.mkdir(parents=True, exist_ok=True)

    # 1. Target group standard
    target_ocr = client.convert_to_markdown(
        target_file, output_dir=md_dir, purpose=purpose, use_cache=use_cache
    )
    target_parsed = parse_standard_markdown(
        target_ocr.markdown_text,
        standard_id="target",
        role="target",
        source_file=target_ocr.source_file,
        markdown_file=target_ocr.markdown_path,
        ocr_engine=target_ocr.engine,
    )
    target_json_path = parsed_dir / "target.json"
    target_json_path.write_text(
        target_parsed.model_dump_json(indent=2), encoding="utf-8"
    )

    # 2. Reference standards (1..N)
    ref_entries: list[dict[str, Any]] = []
    ref_parsed_list: list[ParsedStandard] = []
    for idx, ref_path in enumerate(reference_files, start=1):
        ref_id = f"ref_{idx}"
        ref_ocr = client.convert_to_markdown(
            ref_path, output_dir=md_dir, purpose=purpose, use_cache=use_cache
        )
        ref_parsed = parse_standard_markdown(
            ref_ocr.markdown_text,
            standard_id=ref_id,
            role="reference",
            source_file=ref_ocr.source_file,
            markdown_file=ref_ocr.markdown_path,
            ocr_engine=ref_ocr.engine,
        )
        ref_json_path = parsed_dir / f"{ref_id}.json"
        ref_json_path.write_text(
            ref_parsed.model_dump_json(indent=2), encoding="utf-8"
        )
        ref_parsed_list.append(ref_parsed)
        ref_entries.append(
            {
                "standard_id": ref_id,
                "source_file": ref_ocr.source_file,
                "markdown_file": ref_ocr.markdown_path,
                "parsed_json": str(ref_json_path),
                "standard_code": ref_parsed.metadata.standard_code,
                "standard_title": ref_parsed.metadata.standard_title,
                "page_count": ref_ocr.page_count,
                "candidate_clause_count": len(ref_parsed.candidate_leaf_clauses),
            }
        )

    # 3. Build assessment template pre-filled with Step a/b/c-d scaffolding
    template = ComparisonAssessment(
        target_standard_id="target",
        standard_type="待判定（请填写：产品标准/方法标准/管理标准/服务标准等）",
        scope_matching_results=[
            ObjectConsistencyResult(
                reference_id=ref.metadata.standard_id,
                reference_code=ref.metadata.standard_code,
                reference_title=ref.metadata.standard_title,
                target_object="请提取待测团体标准的标准化对象",
                reference_object="请提取该比对标准的标准化对象",
                target_scope_summary=target_parsed.metadata.scope_chapter_text[:500],
                reference_scope_summary=ref.metadata.scope_chapter_text[:500],
                object_consistency=ObjectConsistency.SIMILAR,
                is_eligible_for_comparison=True,
                consistency_reasoning="请比对双方第1章范围及标题，判定标准化对象是否一致（IDENTICAL/SIMILAR/INCONSISTENT）。",
            )
            for ref in ref_parsed_list
        ],
        chapter_scope_decisions=[
            ChapterScopeDecision(
                chapter_no=ch.chapter_no,
                chapter_title=ch.chapter_title,
                in_comparison_scope=True,
                reason="待宿主Agent依据标准类型确认是否属于核心技术要素章节。",
            )
            for ch in target_parsed.chapters
            if not ch.auto_excluded and ch.leaf_clause_count > 0
        ],
        clause_comparisons=[
            ClauseComparison(
                clause_id=cl.clause_id,
                verdict=(
                    ClauseVerdict.NON_DUPLICATE_DIRECT_REF
                    if cl.detected_normative_refs
                    else ClauseVerdict.NON_DUPLICATE_UNIQUE
                ),
                overlap_ratio=0.0,
                matched_clauses=[],
                technical_reasoning=(
                    f"检测到规范性引用提示: {', '.join(cl.detected_normative_refs)}；请核验是否为直接引用。"
                    if cl.detected_normative_refs
                    else "待宿主Agent完成逐条技术比对。"
                ),
            )
            for cl in target_parsed.candidate_leaf_clauses
        ],
        overall_expert_notes="",
    )
    template_path = workspace_dir / "assessment_template.json"
    template_path.write_text(template.model_dump_json(indent=2), encoding="utf-8")

    manifest = {
        "workspace_dir": str(workspace_dir),
        "ocr_engine": client.engine_name,
        "target": {
            "standard_id": "target",
            "source_file": target_ocr.source_file,
            "markdown_file": target_ocr.markdown_path,
            "parsed_json": str(target_json_path),
            "standard_code": target_parsed.metadata.standard_code,
            "standard_title": target_parsed.metadata.standard_title,
            "page_count": target_ocr.page_count,
            "total_leaf_clauses": len(target_parsed.all_leaf_clauses),
            "candidate_clause_count": len(target_parsed.candidate_leaf_clauses),
        },
        "references": ref_entries,
        "assessment_template_json": str(template_path),
    }
    manifest_path = workspace_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def generate_reports_from_workspace(
    workspace_dir: Path,
    assessment_json_path: Path,
    output_dir: Path,
    *,
    strict_clause_coverage: bool = False,
) -> tuple[PlagiarismReportResult, dict[str, Path]]:
    """Load parsed standards + host Agent assessment JSON, calculate Appendix B metrics, and export all 5 report formats."""
    workspace_dir = workspace_dir.resolve()
    manifest_path = workspace_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Workspace manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    target_path = Path(manifest["target"]["parsed_json"])
    target_parsed = ParsedStandard.model_validate_json(
        target_path.read_text(encoding="utf-8")
    )

    ref_parsed_list: list[ParsedStandard] = []
    for entry in manifest.get("references", []):
        ref_path = Path(entry["parsed_json"])
        ref_parsed_list.append(
            ParsedStandard.model_validate_json(ref_path.read_text(encoding="utf-8"))
        )

    assessment = ComparisonAssessment.model_validate_json(
        assessment_json_path.read_text(encoding="utf-8")
    )

    report = calculate_plagiarism_report(
        target_parsed,
        ref_parsed_list,
        assessment,
        strict_clause_coverage=strict_clause_coverage,
    )
    exported_files = export_all_reports(report, output_dir.resolve())
    return report, exported_files
