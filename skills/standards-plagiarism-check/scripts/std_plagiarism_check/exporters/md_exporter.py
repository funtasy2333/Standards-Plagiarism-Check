"""Markdown report generator for Appendix B standard duplication results."""

from __future__ import annotations

from pathlib import Path

from ..models import ClauseVerdict, ObjectConsistency, PlagiarismReportResult

VERDICT_LABELS: dict[ClauseVerdict, str] = {
    ClauseVerdict.DUPLICATE_EXACT: "完全重复（计 1）",
    ClauseVerdict.DUPLICATE_EQUIVALENT: "实质等同/同义改写（计 1）",
    ClauseVerdict.DUPLICATE_PARTIAL: "部分内容重复",
    ClauseVerdict.NON_DUPLICATE_DIRECT_REF: "规范性直接引用（不重复，计 0）",
    ClauseVerdict.NON_DUPLICATE_UPGRADED: "指标提升/实质改进（不重复，计 0）",
    ClauseVerdict.NON_DUPLICATE_UNIQUE: "独创/无对应条款（不重复，计 0）",
}

CONSISTENCY_LABELS: dict[ObjectConsistency, str] = {
    ObjectConsistency.IDENTICAL: "一致（纳入比对）",
    ObjectConsistency.SIMILAR: "相似（纳入比对）",
    ObjectConsistency.INCONSISTENT: "不一致（不适用比对，已剔除）",
}


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", "<br/>").strip()


def render_markdown_report(report: PlagiarismReportResult) -> str:
    """Render a comprehensive Appendix B review report in Markdown format."""
    t_meta = report.target_standard
    lines: list[str] = []

    lines.append("# 团体标准技术内容重复率检测报告（依据附录 B）")
    lines.append("")
    lines.append(f"- **生成时间**：{report.generated_at}")
    lines.append(
        f"- **待测团体标准**：`{t_meta.standard_code or t_meta.standard_id}` "
        f"{t_meta.standard_title}"
    )
    lines.append(f"- **识别标准类型**：{report.standard_type}")
    lines.append(
        f"- **有效比对标准数量**：{len(report.eligible_reference_ids)} / {len(report.reference_standards)}"
    )
    lines.append("")

    if report.warnings:
        lines.append("## 核验提醒与系统告警")
        lines.append("")
        for w in report.warnings:
            lines.append(f"> **注意**：{w}")
        lines.append("")

    # Summary KPIs
    lines.append("## 一、核心结论与公式计算汇总")
    lines.append("")
    lines.append("依据《团体标准化 第1部分：良好行为指南》附录 B（规范性）公式 (B.1)：")
    lines.append("")
    lines.append("$$R = \\frac{n_2}{n_1} \\times 100\\%$$")
    lines.append("")
    lines.append("| 指标项 | 数值 | 说明 |")
    lines.append("| :--- | :--- | :--- |")
    lines.append(
        f"| 纳入比对范围条款数 ($n_1$) | **{report.n1}** | 核心技术要素最小编号叶子条款数（已排除前置/非核心条款 {report.excluded_clauses_count} 条） |"
    )
    lines.append(
        f"| 技术内容重复条款总数 ($n_2$) | **{report.n2}** | 并集统计（含完全重复、同义改写及重复占比 $\\ge 50\\%$ 的部分重复条款；规范性直接引用计 0） |"
    )
    lines.append(
        f"| **官方内容重复率 ($R$)** | **{report.duplicate_rate_percent:.2f}%** | $R = ({report.n2} / {report.n1}) \\times 100\\%$ |"
    )
    lines.append(
        f"| 按比例折算参考重复率 ($R_{{\\text{{weighted}}}}$) | {report.weighted_duplicate_rate_percent:.2f}% | 折算分子 {report.weighted_numerator:.2f} / {report.n1}（供复合附表条款评审参考） |"
    )
    lines.append("")

    # Per-reference breakdown
    if report.per_reference_stats:
        lines.append("### 1.1 各比对标准分项统计表")
        lines.append("")
        lines.append(
            "| 比对标准编号 | 标准名称 | 标准化对象一致性 | 纳入有效计算 | 重复条款 ($n_{2,i}$) | 单标重复率 ($R_i$) | 折算参考率 |"
        )
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for st in report.per_reference_stats:
            elig_txt = "是" if st.is_eligible_for_comparison else "否（已剔除）"
            lines.append(
                f"| `{st.reference_code or st.reference_id}` | {_md_escape(st.reference_title)} | "
                f"{CONSISTENCY_LABELS[st.object_consistency]} | {elig_txt} | "
                f"{st.n2} | {st.duplicate_rate_percent:.2f}% | {st.weighted_duplicate_rate_percent:.2f}% |"
            )
        lines.append("")

    # Verdict distribution
    lines.append("### 1.2 判定类别分布")
    lines.append("")
    lines.append("| 判定类别 | 条款数 | 计入 $n_2$ 规则 |")
    lines.append("| :--- | :--- | :--- |")
    for v in ClauseVerdict:
        cnt = report.verdict_counts.get(v.value, 0)
        rule = (
            "计 1"
            if v in (ClauseVerdict.DUPLICATE_EXACT, ClauseVerdict.DUPLICATE_EQUIVALENT)
            else ("占比 ≥ 50% 计 1，否则计 0" if v == ClauseVerdict.DUPLICATE_PARTIAL else "计 0（不重复）")
        )
        lines.append(f"| {VERDICT_LABELS[v]} | {cnt} | {rule} |")
    lines.append("")

    # Step a: Standardization Object Consistency
    lines.append("## 二、附录 B 步骤 a：标准化对象与适用范围一致性核验")
    lines.append("")
    lines.append(
        "| 比对标准 | 团标标准化对象 | 比对标准标准化对象 | 一致性判定 | 核验说明 |"
    )
    lines.append("| :--- | :--- | :--- | :--- | :--- |")
    for sr in report.scope_matching_results:
        lines.append(
            f"| `{sr.reference_code or sr.reference_id}` {_md_escape(sr.reference_title)} | "
            f"{_md_escape(sr.target_object)} | {_md_escape(sr.reference_object)} | "
            f"**{CONSISTENCY_LABELS[sr.object_consistency]}** | {_md_escape(sr.consistency_reasoning)} |"
        )
    lines.append("")

    # Step b: Core technical scope decisions
    lines.append("## 三、附录 B 步骤 b：核心技术要素与比对范围界定")
    lines.append("")
    if report.chapter_scope_decisions:
        lines.append("| 章节编号 | 章节名称 | 是否纳入比对范围 | 界定依据 |")
        lines.append("| :--- | :--- | :--- | :--- |")
        for ch in report.chapter_scope_decisions:
            inc_txt = "纳入 ($n_1$)" if ch.in_comparison_scope else "排除"
            lines.append(
                f"| {ch.chapter_no} | {_md_escape(ch.chapter_title)} | {inc_txt} | {_md_escape(ch.reason)} |"
            )
        lines.append("")
    else:
        lines.append("_所有第 4 章及以后非资料性章节均默认纳入比对范围。_")
        lines.append("")

    # Step c & d: Clause-by-clause details
    lines.append("## 四、附录 B 步骤 c & d：逐条技术内容比对明细")
    lines.append("")
    lines.append(
        "| 条款号 | 所属路径 | 判定结论 | 计分 | 重复占比 | 对应比对标准条款 | 技术对比分析 |"
    )
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    for item in report.clause_details:
        verdict_label = VERDICT_LABELS[item.verdict]
        if item.verdict == ClauseVerdict.DUPLICATE_PARTIAL:
            verdict_label = (
                f"部分重复（占比 {item.overlap_ratio * 100:.0f}%，计 {item.official_duplicate_score}）"
            )

        if item.matched_clauses:
            matched_desc = "; ".join(
                f"`{m.reference_code or m.reference_id}` {m.reference_clause_id} {m.reference_clause_title}".strip()
                for m in item.matched_clauses
            )
        else:
            matched_desc = "—"

        lines.append(
            f"| `{item.clause_id}` | {_md_escape(item.chapter_path)} | {verdict_label} | "
            f"**{item.official_duplicate_score}** | {item.overlap_ratio * 100:.0f}% | "
            f"{_md_escape(matched_desc)} | {_md_escape(item.technical_reasoning)} |"
        )
    lines.append("")

    # Highlight Non-Duplicate Direct Refs & Upgraded clauses
    direct_refs = [
        c for c in report.clause_details if c.verdict == ClauseVerdict.NON_DUPLICATE_DIRECT_REF
    ]
    if direct_refs:
        lines.append("### 4.1 规范性直接引用条款（合规引用，判为不重复）")
        lines.append("")
        for c in direct_refs:
            lines.append(f"- **`{c.clause_id}` {c.title}**：{c.technical_reasoning}")
        lines.append("")

    upgraded = [
        c for c in report.clause_details if c.verdict == ClauseVerdict.NON_DUPLICATE_UPGRADED
    ]
    if upgraded:
        lines.append("### 4.2 指标提升/方法改进条款（先进性亮点，判为不重复）")
        lines.append("")
        for c in upgraded:
            lines.append(f"- **`{c.clause_id}` {c.title}**：{c.technical_reasoning}")
        lines.append("")

    if report.overall_expert_notes:
        lines.append("## 五、综合评审意见")
        lines.append("")
        lines.append(report.overall_expert_notes)
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def export_markdown_report(report: PlagiarismReportResult, output_path: Path) -> Path:
    """Write Markdown report to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_markdown_report(report), encoding="utf-8")
    return output_path
