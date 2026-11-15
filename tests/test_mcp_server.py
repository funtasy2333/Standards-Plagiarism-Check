"""Tests for MCP Server tool registration and parse/report tool execution."""

from __future__ import annotations

import json
from pathlib import Path

from std_plagiarism_check.mcp_server import (
    generate_plagiarism_reports,
    mcp,
    parse_standard_clauses,
)
from std_plagiarism_check.models import (
    ClauseComparison,
    ClauseVerdict,
    ComparisonAssessment,
    MatchedReferenceClause,
    ObjectConsistency,
    ObjectConsistencyResult,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_mcp_server_registers_expected_tools() -> None:
    tool_names = {t.name for t in mcp._tool_manager.list_tools()}
    assert tool_names == {
        "ocr_convert_standard",
        "parse_standard_clauses",
        "prepare_comparison_workspace",
        "generate_plagiarism_reports",
    }


def test_mcp_parse_and_generate_reports_roundtrip(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    parsed_dir = ws / "parsed"
    parsed_dir.mkdir(parents=True)

    target_json = parsed_dir / "target.json"
    ref_json = parsed_dir / "ref_1.json"

    res_t = json.loads(
        parse_standard_clauses(
            str(FIXTURES_DIR / "target_group_std.md"),
            standard_role="target",
            standard_id="target",
            output_json_path=str(target_json),
        )
    )
    assert res_t["candidate_leaf_clause_count"] == 8

    res_r = json.loads(
        parse_standard_clauses(
            str(FIXTURES_DIR / "ref_gb_similar.md"),
            standard_role="reference",
            standard_id="ref_1",
            output_json_path=str(ref_json),
        )
    )
    assert res_r["candidate_leaf_clause_count"] >= 3

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
                target_object="工业互联网边缘网关",
                reference_object="物联网感知终端及边缘接入网关",
                object_consistency=ObjectConsistency.SIMILAR,
                is_eligible_for_comparison=True,
                consistency_reasoning="对象及范围相近。",
            )
        ],
        clause_comparisons=[
            ClauseComparison(
                clause_id="5.1",
                verdict=ClauseVerdict.DUPLICATE_EQUIVALENT,
                matched_clauses=[
                    MatchedReferenceClause(
                        reference_id="ref_1",
                        reference_clause_id="5.1",
                    )
                ],
                technical_reasoning="实质等同。",
            ),
            ClauseComparison(
                clause_id="6.1",
                verdict=ClauseVerdict.NON_DUPLICATE_DIRECT_REF,
                technical_reasoning="规范性引用 GB/T 2423.1—2008，计 0。",
            ),
        ],
    )
    assessment_path = ws / "assessment.json"
    assessment_path.write_text(assessment.model_dump_json(indent=2), encoding="utf-8")

    out_dir = tmp_path / "mcp_reports"
    rep_summary = json.loads(
        generate_plagiarism_reports(
            workspace_dir=str(ws),
            assessment_json_path=str(assessment_path),
            output_dir=str(out_dir),
        )
    )
    assert rep_summary["n1"] == 8
    assert rep_summary["n2"] == 1
    assert rep_summary["duplicate_rate_percent"] == 12.5
    assert Path(rep_summary["exported_files"]["html"]).exists()
    assert Path(rep_summary["exported_files"]["docx"]).exists()
    assert Path(rep_summary["exported_files"]["xlsx"]).exists()
