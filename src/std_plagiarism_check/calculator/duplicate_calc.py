"""Appendix B duplication rate calculation engine.

Implements:
- Step a): Standardization object & scope consistency gating.
- Step b): Core technical element chapter filtering to lock n1.
- Step c & d): Leaf-clause verdict scoring (normative direct reference = 0),
  per-reference duplication rates R_i, 1-to-N union rate R_total, and weighted reference rate.
"""

from __future__ import annotations

from collections import Counter

from ..models import (
    ClauseComparison,
    ClauseVerdict,
    ComparisonAssessment,
    EnrichedClauseDetail,
    ObjectConsistency,
    ObjectConsistencyResult,
    ParsedStandard,
    PlagiarismReportResult,
    ReferenceDuplicateStats,
)


class CalculationError(ValueError):
    """Raised when input data cannot produce a valid Appendix B calculation."""


_DUPLICATE_VERDICTS = {
    ClauseVerdict.DUPLICATE_EXACT,
    ClauseVerdict.DUPLICATE_EQUIVALENT,
    ClauseVerdict.DUPLICATE_PARTIAL,
}


def calculate_plagiarism_report(
    target: ParsedStandard,
    references: list[ParsedStandard],
    assessment: ComparisonAssessment,
    *,
    strict_clause_coverage: bool = False,
) -> PlagiarismReportResult:
    """Validate host Agent assessment and compute Appendix B duplication metrics."""
    warnings: list[str] = []

    # ------------------------------------------------------------------
    # Step a): Standardization object consistency gating
    # ------------------------------------------------------------------
    scope_by_ref_id: dict[str, ObjectConsistencyResult] = {
        r.reference_id: r for r in assessment.scope_matching_results
    }
    normalized_scope_results: list[ObjectConsistencyResult] = []
    eligible_ref_ids: set[str] = set()
    ineligible_ref_ids: set[str] = set()

    for ref in references:
        ref_id = ref.metadata.standard_id
        scope_res = scope_by_ref_id.get(ref_id)
        if scope_res is None:
            warnings.append(
                f"比对标准 '{ref_id}' ({ref.metadata.standard_code or ref.metadata.standard_title}) "
                "缺少步骤 a) 标准化对象一致性核验结果，已默认标记为待核验/不纳入有效比对。"
            )
            scope_res = ObjectConsistencyResult(
                reference_id=ref_id,
                reference_code=ref.metadata.standard_code,
                reference_title=ref.metadata.standard_title,
                target_object=target.metadata.standard_title or "待测团体标准",
                reference_object=ref.metadata.standard_title or ref_id,
                object_consistency=ObjectConsistency.INCONSISTENT,
                is_eligible_for_comparison=False,
                consistency_reasoning="未提供标准化对象一致性核验结论，按前置门禁规则不纳入有效比对。",
            )
        else:
            if not scope_res.reference_code:
                scope_res.reference_code = ref.metadata.standard_code
            if not scope_res.reference_title:
                scope_res.reference_title = ref.metadata.standard_title

        normalized_scope_results.append(scope_res)
        if (
            scope_res.is_eligible_for_comparison
            and scope_res.object_consistency != ObjectConsistency.INCONSISTENT
        ):
            eligible_ref_ids.add(ref_id)
        else:
            ineligible_ref_ids.add(ref_id)
            warnings.append(
                f"比对标准 '{ref_id}' ({scope_res.reference_code or scope_res.reference_title}) "
                f"标准化对象判定为 {scope_res.object_consistency.value}（不一致/不适用），"
                "已从有效重复率计算中剔除。"
            )

    # ------------------------------------------------------------------
    # Step b): Core technical elements scope (determine denominator n1)
    # ------------------------------------------------------------------
    scope_decision_map: dict[str, bool] = {
        d.chapter_no: d.in_comparison_scope for d in assessment.chapter_scope_decisions
    }

    in_scope_clauses = []
    excluded_by_step_b = 0

    for clause in target.candidate_leaf_clauses:
        if clause.chapter_no in scope_decision_map:
            included = scope_decision_map[clause.chapter_no]
        else:
            included = True
            if assessment.chapter_scope_decisions:
                warnings.append(
                    f"章节 '{clause.chapter_no} {clause.chapter_title}' 未出现在步骤 b) 章节决策中，默认纳入核心技术比对范围。"
                )

        if included:
            in_scope_clauses.append(clause)
        else:
            excluded_by_step_b += 1

    n1 = len(in_scope_clauses)
    if n1 == 0:
        raise CalculationError(
            "纳入比对范围的叶子条款数量 n1 为 0，无法按公式 R = (n2 / n1) × 100% 计算重复率。"
        )

    # ------------------------------------------------------------------
    # Step c & d): Clause-level scoring & 1-to-N aggregation
    # ------------------------------------------------------------------
    comp_map: dict[str, ClauseComparison] = {
        c.clause_id: c for c in assessment.clause_comparisons
    }

    clause_details: list[EnrichedClauseDetail] = []
    verdict_counter: Counter[str] = Counter()

    # Track per-reference duplicate clause hits
    per_ref_hits: dict[str, list[tuple[int, float]]] = {
        ref.metadata.standard_id: [] for ref in references
    }

    total_n2 = 0
    total_weighted = 0.0

    for clause in in_scope_clauses:
        comp = comp_map.get(clause.clause_id)
        if comp is None:
            msg = f"条款 '{clause.clause_id}' 缺少逐条比对判定结果。"
            if strict_clause_coverage:
                raise CalculationError(msg)
            warnings.append(msg + " 已默认按 NON_DUPLICATE_UNIQUE（不重复）处理。")
            comp = ClauseComparison(
                clause_id=clause.clause_id,
                verdict=ClauseVerdict.NON_DUPLICATE_UNIQUE,
                overlap_ratio=0.0,
                matched_clauses=[],
                technical_reasoning="未提供比对结果，默认计为独创/不重复。",
            )

        if comp.verdict in _DUPLICATE_VERDICTS and not comp.matched_clauses:
            raise CalculationError(
                f"条款 '{clause.clause_id}' 判定为重复，但缺少匹配条款证据。"
            )

        effective_verdict = comp.verdict
        effective_ratio = comp.overlap_ratio
        reasoning = comp.technical_reasoning

        # Filter matched clauses against eligible reference standards
        eligible_matches = [
            m for m in comp.matched_clauses if m.reference_id in eligible_ref_ids
        ]
        ineligible_matches = [
            m for m in comp.matched_clauses if m.reference_id in ineligible_ref_ids
        ]

        if effective_verdict in _DUPLICATE_VERDICTS and comp.matched_clauses and not eligible_matches:
            # All matched references were rejected in Step a) due to inconsistent standardization object
            warnings.append(
                f"条款 '{clause.clause_id}' 原匹配的标准均因“标准化对象不一致”被剔除，该条款在本轮有效比对中改计为 0。"
            )
            effective_verdict = ClauseVerdict.NON_DUPLICATE_UNIQUE
            effective_ratio = 0.0
            reasoning = (
                f"{reasoning} [系统校正：所匹配的比对标准标准化对象不一致，不计入有效重复条款]"
            ).strip()
        elif ineligible_matches and eligible_matches and effective_verdict == ClauseVerdict.DUPLICATE_PARTIAL:
            # Re-aggregate only eligible contributions if partial duplicate spans multiple refs
            elig_sum = sum(m.overlap_contribution for m in eligible_matches)
            effective_ratio = min(1.0, max(0.0, round(elig_sum, 4)))

        # Compute official score (0 or 1) and weighted score
        if effective_verdict in (
            ClauseVerdict.DUPLICATE_EXACT,
            ClauseVerdict.DUPLICATE_EQUIVALENT,
        ):
            official_score = 1
            weighted_score = 1.0
        elif effective_verdict == ClauseVerdict.DUPLICATE_PARTIAL:
            weighted_score = round(effective_ratio, 4)
            official_score = 1 if effective_ratio >= 0.5 else 0
        else:
            # Includes NON_DUPLICATE_DIRECT_REF ("按 GB/T XXX 规定执行" -> 0!),
            # NON_DUPLICATE_UPGRADED, and NON_DUPLICATE_UNIQUE.
            official_score = 0
            weighted_score = 0.0

        verdict_counter[effective_verdict.value] += 1
        total_n2 += official_score
        total_weighted += weighted_score

        # Per-reference breakdown (only for eligible references)
        for ref in references:
            ref_id = ref.metadata.standard_id
            if ref_id not in eligible_ref_ids:
                continue

            if effective_verdict not in _DUPLICATE_VERDICTS:
                continue

            ref_matches = [m for m in eligible_matches if m.reference_id == ref_id]
            if not ref_matches:
                continue

            if effective_verdict in (
                ClauseVerdict.DUPLICATE_EXACT,
                ClauseVerdict.DUPLICATE_EQUIVALENT,
            ):
                per_ref_hits[ref_id].append((1, 1.0))
            else:
                # DUPLICATE_PARTIAL
                if len(eligible_matches) == 1 and len(ref_matches) == 1:
                    ref_ratio = effective_ratio
                else:
                    ref_ratio = min(
                        1.0,
                        sum(m.overlap_contribution for m in ref_matches),
                    )
                ref_official = 1 if ref_ratio >= 0.5 else 0
                per_ref_hits[ref_id].append((ref_official, ref_ratio))

        clause_details.append(
            EnrichedClauseDetail(
                clause_id=clause.clause_id,
                title=clause.title,
                chapter_no=clause.chapter_no,
                chapter_path=clause.chapter_path,
                target_text=clause.full_text,
                tables=clause.tables,
                page_numbers=clause.page_numbers,
                detected_normative_refs=clause.detected_normative_refs,
                verdict=effective_verdict,
                official_duplicate_score=official_score,
                overlap_ratio=weighted_score,
                matched_clauses=comp.matched_clauses,
                technical_reasoning=reasoning,
            )
        )

    duplicate_rate_percent = round((total_n2 / n1) * 100.0, 2)
    weighted_numerator = round(total_weighted, 4)
    weighted_rate_percent = round((weighted_numerator / n1) * 100.0, 2)

    per_reference_stats: list[ReferenceDuplicateStats] = []
    for scope_res in normalized_scope_results:
        ref_id = scope_res.reference_id
        is_elig = ref_id in eligible_ref_ids
        hits = per_ref_hits.get(ref_id, []) if is_elig else []
        ref_n2 = sum(h[0] for h in hits)
        ref_weighted = round(sum(h[1] for h in hits), 4)
        ref_rate = round((ref_n2 / n1) * 100.0, 2) if is_elig else 0.0
        ref_w_rate = round((ref_weighted / n1) * 100.0, 2) if is_elig else 0.0

        per_reference_stats.append(
            ReferenceDuplicateStats(
                reference_id=ref_id,
                reference_code=scope_res.reference_code,
                reference_title=scope_res.reference_title,
                target_object=scope_res.target_object,
                reference_object=scope_res.reference_object,
                object_consistency=scope_res.object_consistency,
                is_eligible_for_comparison=is_elig,
                consistency_reasoning=scope_res.consistency_reasoning,
                n1=n1,
                n2=ref_n2,
                duplicate_rate_percent=ref_rate,
                weighted_numerator=ref_weighted,
                weighted_duplicate_rate_percent=ref_w_rate,
            )
        )

    excluded_auto_count = len(target.all_leaf_clauses) - len(target.candidate_leaf_clauses)

    return PlagiarismReportResult(
        target_standard=target.metadata,
        reference_standards=[r.metadata for r in references],
        standard_type=assessment.standard_type,
        scope_matching_results=normalized_scope_results,
        eligible_reference_ids=sorted(eligible_ref_ids),
        ineligible_reference_ids=sorted(ineligible_ref_ids),
        chapter_scope_decisions=assessment.chapter_scope_decisions,
        excluded_clauses_count=excluded_auto_count + excluded_by_step_b,
        n1=n1,
        n2=total_n2,
        duplicate_rate_percent=duplicate_rate_percent,
        weighted_numerator=weighted_numerator,
        weighted_duplicate_rate_percent=weighted_rate_percent,
        per_reference_stats=per_reference_stats,
        verdict_counts=dict(verdict_counter),
        clause_details=clause_details,
        warnings=warnings,
        overall_expert_notes=assessment.overall_expert_notes,
    )
