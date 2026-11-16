"""Tests for Appendix B calculation engine (Step a gating, direct ref = 0, partial/upgraded, 1-to-N)."""

from __future__ import annotations

from pathlib import Path

import pytest

from std_plagiarism_check.calculator import CalculationError, calculate_plagiarism_report
from std_plagiarism_check.models import (
    ChapterScopeDecision,
    ClauseComparison,
    ClauseVerdict,
    ComparisonAssessment,
    MatchedReferenceClause,
    ObjectConsistency,
    ObjectConsistencyResult,
)
from std_plagiarism_check.parser import parse_standard_markdown

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixtures():
    target = parse_standard_markdown(
        (FIXTURES_DIR / "target_group_std.md").read_text(encoding="utf-8"),
        standard_id="target",
        role="target",
    )
    ref_similar = parse_standard_markdown(
        (FIXTURES_DIR / "ref_gb_similar.md").read_text(encoding="utf-8"),
        standard_id="ref_1",
        role="reference",
    )
    ref_inconsistent = parse_standard_markdown(
        (FIXTURES_DIR / "ref_gb_inconsistent.md").read_text(encoding="utf-8"),
        standard_id="ref_2",
        role="reference",
    )
    return target, ref_similar, ref_inconsistent


def test_appendix_b_calculation_with_step_a_gating_and_direct_ref_non_duplicate() -> None:
    target, ref_similar, ref_inconsistent = _load_fixtures()

    assessment = ComparisonAssessment(
        standard_type="产品标准",
        scope_matching_results=[
            ObjectConsistencyResult(
                reference_id="ref_1",
                target_object="工业互联网边缘网关",
                reference_object="物联网感知终端及边缘接入网关",
                object_consistency=ObjectConsistency.SIMILAR,
                is_eligible_for_comparison=True,
                consistency_reasoning="标准化对象均涵盖工业边缘接入网关安全要求，适用范围相似。",
            ),
            ObjectConsistencyResult(
                reference_id="ref_2",
                target_object="工业互联网边缘网关",
                reference_object="通用电工电子产品低温环境试验方法",
                object_consistency=ObjectConsistency.INCONSISTENT,
                is_eligible_for_comparison=False,
                consistency_reasoning="ref_2 为通用环境试验方法标准，与工业边缘网关信息安全标准化对象不一致。",
            ),
        ],
        chapter_scope_decisions=[
            ChapterScopeDecision(chapter_no="4", chapter_title="分类与架构", in_comparison_scope=False, reason="分类分级说明，非核心安全技术指标"),
            ChapterScopeDecision(chapter_no="5", chapter_title="安全技术要求", in_comparison_scope=True, reason="核心安全技术要素"),
            ChapterScopeDecision(chapter_no="6", chapter_title="试验方法", in_comparison_scope=True, reason="核心验证方法"),
            ChapterScopeDecision(chapter_no="附录A", chapter_title="国密算法安全接口要求", in_comparison_scope=True, reason="规范性技术附录"),
        ],
        clause_comparisons=[
            # 5.1 -> DUPLICATE_EQUIVALENT against ref_1 (score = 1)
            ClauseComparison(
                clause_id="5.1",
                verdict=ClauseVerdict.DUPLICATE_EQUIVALENT,
                matched_clauses=[
                    MatchedReferenceClause(
                        reference_id="ref_1",
                        reference_code="GB/T 36951—2018",
                        reference_clause_id="5.1",
                        reference_clause_title="物理与硬件安全",
                        reference_excerpt="感知设备应支持防物理拆解检测机制，外壳防护应满足 IP54 要求。",
                    )
                ],
                technical_reasoning="防物理拆解、IP54 与可信芯片要求与 GB/T 36951—2018 5.1 实质等同。",
            ),
            # 5.2.1 -> NON_DUPLICATE_UPGRADED (score = 0: 128-bit & TLS 1.3 stricter than 112-bit & TLS 1.2)
            ClauseComparison(
                clause_id="5.2.1",
                verdict=ClauseVerdict.NON_DUPLICATE_UPGRADED,
                matched_clauses=[
                    MatchedReferenceClause(
                        reference_id="ref_1",
                        reference_code="GB/T 36951—2018",
                        reference_clause_id="5.2.1",
                        reference_clause_title="通信加密与认证",
                        reference_excerpt="采用 TLS 1.2，会话密钥强度不低于 112 位。",
                    )
                ],
                technical_reasoning="团标强制 TLS 1.3/SM2/SM4 双向认证及 128 位以上密钥，严于国标 112 位要求。",
            ),
            # 5.2.2 -> NON_DUPLICATE_UNIQUE (score = 0)
            ClauseComparison(
                clause_id="5.2.2",
                verdict=ClauseVerdict.NON_DUPLICATE_UNIQUE,
                technical_reasoning="工业协议深度报文过滤为团标独创条款。",
            ),
            # 5.2.3 -> DUPLICATE_PARTIAL 4/6 = 0.6667 >= 0.5 -> official score = 1, weighted = 0.6667
            ClauseComparison(
                clause_id="5.2.3",
                verdict=ClauseVerdict.DUPLICATE_PARTIAL,
                overlap_ratio=0.6667,
                matched_clauses=[
                    MatchedReferenceClause(
                        reference_id="ref_1",
                        reference_code="GB/T 36951—2018",
                        reference_clause_id="5.2.2",
                        reference_clause_title="端口与访问控制",
                        reference_excerpt="前 4 项指标一致。",
                        overlap_contribution=0.6667,
                    )
                ],
                technical_reasoning="表 1 中 6 项指标有 4 项与 GB/T 36951—2018 5.2.2 一致，占比 66.7%。",
            ),
            # 6.1 -> NON_DUPLICATE_DIRECT_REF ("按 GB/T 2423.1—2008 的规定执行" -> score = 0!)
            ClauseComparison(
                clause_id="6.1",
                verdict=ClauseVerdict.NON_DUPLICATE_DIRECT_REF,
                matched_clauses=[
                    MatchedReferenceClause(
                        reference_id="ref_2",
                        reference_code="GB/T 2423.1—2008",
                        reference_clause_id="5.1",
                        reference_clause_title="试验箱温度容差",
                        reference_excerpt="低温试验箱工作空间温度允许偏差为 ±2 ℃。",
                    )
                ],
                technical_reasoning="条款采用规范性直接引用“按 GB/T 2423.1—2008 的规定执行”，不构成内容重复，计 0。",
            ),
            # 6.2 -> NON_DUPLICATE_UNIQUE (score = 0)
            ClauseComparison(
                clause_id="6.2",
                verdict=ClauseVerdict.NON_DUPLICATE_UNIQUE,
                technical_reasoning="对应 5.2.2 的独创测试方法。",
            ),
            # A.1 -> Hypothetically marked DUPLICATE_EXACT against INCONSISTENT ref_2 -> must be gated to 0!
            ClauseComparison(
                clause_id="A.1",
                verdict=ClauseVerdict.DUPLICATE_EXACT,
                matched_clauses=[
                    MatchedReferenceClause(
                        reference_id="ref_2",
                        reference_code="GB/T 2423.1—2008",
                        reference_clause_id="5.1",
                        reference_clause_title="试验箱温度容差",
                    )
                ],
                technical_reasoning="测试校验：即使误匹配到不一致的 ref_2，也应被步骤 a 门禁剔除。",
            ),
        ],
    )

    report = calculate_plagiarism_report(target, [ref_similar, ref_inconsistent], assessment)

    # Chapter 4 (4.1) excluded by Step b -> remaining n1 = 7 clauses:
    # 5.1, 5.2.1, 5.2.2, 5.2.3, 6.1, 6.2, A.1
    assert report.n1 == 7
    # Duplicates: 5.1 (1) + 5.2.3 (1). 6.1 is direct ref (0). A.1 matched only inconsistent ref_2 (gated to 0).
    assert report.n2 == 2
    assert report.duplicate_rate_percent == round((2 / 7) * 100, 2)
    assert report.weighted_numerator == pytest.approx(1.6667, abs=1e-4)
    assert report.weighted_duplicate_rate_percent == round((1.6667 / 7) * 100, 2)

    assert report.eligible_reference_ids == ["ref_1"]
    assert report.ineligible_reference_ids == ["ref_2"]

    ref1_stats = next(s for s in report.per_reference_stats if s.reference_id == "ref_1")
    ref2_stats = next(s for s in report.per_reference_stats if s.reference_id == "ref_2")
    assert ref1_stats.is_eligible_for_comparison is True
    assert ref1_stats.n2 == 2
    assert ref2_stats.is_eligible_for_comparison is False
    assert ref2_stats.n2 == 0
    assert ref2_stats.duplicate_rate_percent == 0.0

    # Verify normative direct reference was counted as 0
    detail_61 = next(d for d in report.clause_details if d.clause_id == "6.1")
    assert detail_61.verdict == ClauseVerdict.NON_DUPLICATE_DIRECT_REF
    assert detail_61.official_duplicate_score == 0
    assert detail_61.overlap_ratio == 0.0


def test_zero_in_scope_clauses_raises() -> None:
    target, ref_similar, _ = _load_fixtures()
    assessment = ComparisonAssessment(
        scope_matching_results=[
            ObjectConsistencyResult(
                reference_id="ref_1",
                target_object="A",
                reference_object="A",
                object_consistency=ObjectConsistency.IDENTICAL,
                is_eligible_for_comparison=True,
            )
        ],
        chapter_scope_decisions=[
            ChapterScopeDecision(chapter_no="4", in_comparison_scope=False),
            ChapterScopeDecision(chapter_no="5", in_comparison_scope=False),
            ChapterScopeDecision(chapter_no="6", in_comparison_scope=False),
            ChapterScopeDecision(chapter_no="附录A", in_comparison_scope=False),
        ],
    )
    with pytest.raises(CalculationError, match="n1 为 0"):
        calculate_plagiarism_report(target, [ref_similar], assessment)


@pytest.mark.parametrize('verdict', [ClauseVerdict.DUPLICATE_EXACT, ClauseVerdict.DUPLICATE_EQUIVALENT, ClauseVerdict.DUPLICATE_PARTIAL])
@pytest.mark.parametrize('strict', [False, True])
def test_duplicate_without_matching_evidence_is_rejected(verdict, strict) -> None:
    target = parse_standard_markdown('4 技术要求\n4.1 安全\n应安全。')
    assessment = ComparisonAssessment(clause_comparisons=[ClauseComparison(clause_id='4.1', verdict=verdict, overlap_ratio=0.8)])
    with pytest.raises(CalculationError, match='匹配'):
        calculate_plagiarism_report(target, [], assessment, strict_clause_coverage=strict)
