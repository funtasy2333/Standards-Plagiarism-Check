"""Formal Word (.docx) review report exporter using python-docx."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Inches, Pt, RGBColor

from ..models import ClauseVerdict, PlagiarismReportResult
from .md_exporter import CONSISTENCY_LABELS, VERDICT_LABELS


def _set_cell_bg(cell, hex_color: str) -> None:
    shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    cell._tc.get_or_add_tcPr().append(shading)


def _set_table_borders(table) -> None:
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for name in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{name}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "CBD5E1")
        borders.append(el)
    tbl_pr.append(borders)


def _populate_table(doc: Document, headers: list[str], rows: list[list[str]]) -> None:
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(table)

    hdr_cells = table.rows[0].cells
    for idx, h in enumerate(headers):
        hdr_cells[idx].text = h
        _set_cell_bg(hdr_cells[idx], "1E3A8A")
        for p in hdr_cells[idx].paragraphs:
            for run in p.runs:
                run.bold = True
                run.font.size = Pt(9.5)
                run.font.color.rgb = RGBColor(255, 255, 255)

    for r_idx, row_vals in enumerate(rows):
        row_cells = table.rows[r_idx + 1].cells
        bg = "F8FAFC" if r_idx % 2 == 1 else "FFFFFF"
        for c_idx, val in enumerate(row_vals):
            row_cells[c_idx].text = val
            _set_cell_bg(row_cells[c_idx], bg)
            for p in row_cells[c_idx].paragraphs:
                for run in p.runs:
                    run.font.size = Pt(9)


def export_docx_report(report: PlagiarismReportResult, output_path: Path) -> Path:
    """Generate a formal Word (.docx) Appendix B technical review report."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()

    for section in doc.sections:
        section.top_margin = Inches(0.75)
        section.bottom_margin = Inches(0.75)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)

    title_p = doc.add_heading("团体标准技术内容重复率审查报告（依据附录 B）", level=0)
    title_p.alignment = 1  # center

    t_meta = report.target_standard
    meta_p = doc.add_paragraph()
    meta_p.add_run(f"待测团体标准：{t_meta.standard_code or t_meta.standard_id} {t_meta.standard_title}\n").bold = True
    meta_p.add_run(f"识别标准类型：{report.standard_type}    生成时间：{report.generated_at}")

    if report.warnings:
        doc.add_heading("核验提醒", level=1)
        for w in report.warnings:
            p = doc.add_paragraph(f"• {w}")
            for run in p.runs:
                run.font.color.rgb = RGBColor(180, 83, 9)

    doc.add_heading("一、公式计算结果汇总", level=1)
    doc.add_paragraph("计算公式：R = (n2 / n1) × 100%（规范性直接引用“按 GB/T XXX 执行”计 0，不计入 n2）")
    _populate_table(
        doc,
        ["指标名称", "数值", "说明"],
        [
            ["纳入比对范围条款数 (n1)", str(report.n1), f"核心技术要素叶子条款总数（已排除前置/非核心条款 {report.excluded_clauses_count} 条）"],
            ["重复条款总数 (n2)", str(report.n2), "含完全重复、实质等同改写及重复占比 ≥ 50% 的部分重复条款"],
            ["官方内容重复率 (R)", f"{report.duplicate_rate_percent:.2f}%", f"({report.n2} / {report.n1}) × 100%"],
            ["按比例折算参考重复率", f"{report.weighted_duplicate_rate_percent:.2f}%", f"折算分子 {report.weighted_numerator:.2f} / {report.n1}"],
        ],
    )

    doc.add_heading("二、步骤 a：标准化对象与适用范围一致性核验", level=1)
    scope_rows = [
        [
            f"{st.reference_code or st.reference_id}\n{st.reference_title}",
            st.target_object,
            st.reference_object,
            CONSISTENCY_LABELS[st.object_consistency],
            f"{st.duplicate_rate_percent:.2f}% ({st.n2}/{st.n1})" if st.is_eligible_for_comparison else "不纳入计算",
            st.consistency_reasoning,
        ]
        for st in report.per_reference_stats
    ]
    _populate_table(
        doc,
        ["比对标准", "团标标准化对象", "比对标准标准化对象", "一致性判定", "单标重复率", "核验说明"],
        scope_rows or [["—", "—", "—", "—", "—", "无比对标准"]],
    )

    doc.add_heading("三、步骤 b：核心技术要素比对范围界定", level=1)
    ch_rows = [
        [ch.chapter_no, ch.chapter_title, "纳入 (n1)" if ch.in_comparison_scope else "排除", ch.reason]
        for ch in report.chapter_scope_decisions
    ]
    _populate_table(
        doc,
        ["章节号", "章节名称", "界定结论", "依据说明"],
        ch_rows or [["第4章起", "全部技术章节", "纳入 (n1)", "默认纳入核心技术要素比对范围"]],
    )

    doc.add_heading("四、步骤 c & d：逐条技术内容比对明细", level=1)
    clause_rows = []
    for item in report.clause_details:
        v_text = VERDICT_LABELS[item.verdict]
        if item.verdict == ClauseVerdict.DUPLICATE_PARTIAL:
            v_text = f"部分重复 ({item.overlap_ratio * 100:.0f}%)"
        matched = "\n".join(
            f"[{m.reference_code or m.reference_id}] {m.reference_clause_id} {m.reference_clause_title}".strip()
            for m in item.matched_clauses
        ) or "—"
        clause_rows.append(
            [
                f"{item.clause_id} {item.title}".strip(),
                item.target_text[:300] + ("..." if len(item.target_text) > 300 else ""),
                v_text,
                str(item.official_duplicate_score),
                matched,
                item.technical_reasoning,
            ]
        )
    _populate_table(
        doc,
        ["条款号", "团标条款原文", "判定结论", "计分", "对应比对标准条款", "技术对比分析"],
        clause_rows,
    )

    if report.overall_expert_notes:
        doc.add_heading("五、综合评审意见", level=1)
        doc.add_paragraph(report.overall_expert_notes)

    doc.save(str(output_path))
    return output_path
