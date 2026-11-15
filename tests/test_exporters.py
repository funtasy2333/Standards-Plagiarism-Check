"""Integration tests for 5-format report export and CLI workflow."""

from __future__ import annotations

import json
from pathlib import Path

from docx import Document
from openpyxl import load_workbook
from typer.testing import CliRunner

from std_plagiarism_check.calculator import calculate_plagiarism_report
from std_plagiarism_check.cli import app
from std_plagiarism_check.exporters import export_all_reports
from std_plagiarism_check.models import (
    ChapterScopeDecision,
    ClauseComparison,
    ClauseVerdict,
    ComparisonAssessment,
    MatchedReferenceClause,
    ObjectConsistency,
    ObjectConsistencyResult,
    PlagiarismReportResult,
)
from std_plagiarism_check.parser import parse_standard_markdown

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_export_all_five_formats(tmp_path: Path) -> None:
    target = parse_standard_markdown(
        (FIXTURES_DIR / "target_group_std.md").read_text(encoding="utf-8"),
        standard_id="target",
        role="target",
    )
    ref_1 = parse_standard_markdown(
        (FIXTURES_DIR / "ref_gb_similar.md").read_text(encoding="utf-8"),
        standard_id="ref_1",
        role="reference",
    )

    assessment = ComparisonAssessment(
        standard_type="产品标准",
        scope_matching_results=[
            ObjectConsistencyResult(
                reference_id="ref_1",
                target_object="工业互联网边缘网关",
                reference_object="物联网感知终端及边缘接入网关",
                object_consistency=ObjectConsistency.SIMILAR,
                is_eligible_for_comparison=True,
                consistency_reasoning="对象及适用范围相近，纳入比对。",
            )
        ],
        chapter_scope_decisions=[
            ChapterScopeDecision(chapter_no="4", chapter_title="分类与架构", in_comparison_scope=False, reason="非核心技术要求"),
            ChapterScopeDecision(chapter_no="5", chapter_title="安全技术要求", in_comparison_scope=True, reason="核心技术指标"),
            ChapterScopeDecision(chapter_no="6", chapter_title="试验方法", in_comparison_scope=True, reason="核心测试方法"),
            ChapterScopeDecision(chapter_no="附录A", chapter_title="国密算法安全接口要求", in_comparison_scope=True, reason="规范性附录"),
        ],
        clause_comparisons=[
            ClauseComparison(
                clause_id="5.1",
                verdict=ClauseVerdict.DUPLICATE_EQUIVALENT,
                matched_clauses=[
                    MatchedReferenceClause(
                        reference_id="ref_1",
                        reference_code="GB/T 36951—2018",
                        reference_clause_id="5.1",
                        reference_clause_title="物理与硬件安全",
                        reference_excerpt="感知设备应支持防物理拆解检测机制。",
                    )
                ],
                technical_reasoning="硬件防拆解要求实质等同。",
            ),
            ClauseComparison(
                clause_id="6.1",
                verdict=ClauseVerdict.NON_DUPLICATE_DIRECT_REF,
                technical_reasoning="规范性直接引用 GB/T 2423.1—2008，不重复。",
            ),
        ],
        overall_expert_notes="整体创新性较高，仅个别基础硬件防护条款与现行国标重合。",
    )

    report = calculate_plagiarism_report(target, [ref_1], assessment)
    files = export_all_reports(report, tmp_path / "reports")

    assert set(files.keys()) == {"markdown", "json", "html", "docx", "xlsx"}
    for path in files.values():
        assert path.exists() and path.stat().st_size > 0

    # 1. Verify Markdown
    md_content = files["markdown"].read_text(encoding="utf-8")
    assert "T/CESA 1008—2025" in md_content
    assert "标准化对象与适用范围一致性核验" in md_content
    assert "规范性直接引用（不重复，计 0）" in md_content

    # 2. Verify JSON round-trip
    loaded_report = PlagiarismReportResult.model_validate_json(
        files["json"].read_text(encoding="utf-8")
    )
    assert loaded_report.n1 == report.n1
    assert loaded_report.n2 == report.n2

    # 3. Verify HTML
    html_content = files["html"].read_text(encoding="utf-8")
    assert "NON_DUPLICATE_DIRECT_REF" in html_content
    assert "applyFilters" in html_content

    # 4. Verify DOCX opens cleanly
    docx_doc = Document(str(files["docx"]))
    full_docx_text = "\n".join(p.text for p in docx_doc.paragraphs)
    assert "团体标准技术内容重复率审查报告" in full_docx_text
    assert len(docx_doc.tables) >= 4

    # 5. Verify XLSX has 4 expected sheets
    wb = load_workbook(str(files["xlsx"]))
    assert wb.sheetnames == [
        "汇总与对象核验",
        "比对范围界定(步骤b)",
        "逐条技术比对明细",
        "多标准分项统计",
    ]
    ws3 = wb["逐条技术比对明细"]
    assert ws3.max_row == 1 + report.n1


def test_cli_parse_and_report_smoke(tmp_path: Path) -> None:
    runner = CliRunner()
    ws = tmp_path / "ws"
    parsed_dir = ws / "parsed"
    parsed_dir.mkdir(parents=True)

    # Parse target and reference via CLI
    target_json = parsed_dir / "target.json"
    ref_json = parsed_dir / "ref_1.json"

    res1 = runner.invoke(
        app,
        [
            "parse",
            str(FIXTURES_DIR / "target_group_std.md"),
            "--role",
            "target",
            "--id",
            "target",
            "-o",
            str(target_json),
        ],
    )
    assert res1.exit_code == 0

    res2 = runner.invoke(
        app,
        [
            "parse",
            str(FIXTURES_DIR / "ref_gb_similar.md"),
            "--role",
            "reference",
            "--id",
            "ref_1",
            "-o",
            str(ref_json),
        ],
    )
    assert res2.exit_code == 0

    manifest = {
        "workspace_dir": str(ws),
        "target": {"standard_id": "target", "parsed_json": str(target_json)},
        "references": [{"standard_id": "ref_1", "parsed_json": str(ref_json)}],
    }
    (ws / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    assessment = ComparisonAssessment(
        scope_matching_results=[
            ObjectConsistencyResult(
                reference_id="ref_1",
                target_object="边缘网关",
                reference_object="物联网感知终端及网关",
                object_consistency=ObjectConsistency.SIMILAR,
                is_eligible_for_comparison=True,
                consistency_reasoning="对象相近",
            )
        ],
        clause_comparisons=[
            ClauseComparison(
                clause_id="5.1",
                verdict=ClauseVerdict.DUPLICATE_EXACT,
                matched_clauses=[
                    MatchedReferenceClause(
                        reference_id="ref_1",
                        reference_clause_id="5.1",
                    )
                ],
                technical_reasoning="完全一致",
            )
        ],
    )
    assessment_path = ws / "assessment.json"
    assessment_path.write_text(assessment.model_dump_json(indent=2), encoding="utf-8")

    out_dir = tmp_path / "out_reports"
    res3 = runner.invoke(
        app,
        [
            "report",
            "--workspace",
            str(ws),
            "--assessment",
            str(assessment_path),
            "--output-dir",
            str(out_dir),
        ],
    )
    assert res3.exit_code == 0
    assert (out_dir / "plagiarism_report.md").exists()
    assert (out_dir / "plagiarism_report.xlsx").exists()
