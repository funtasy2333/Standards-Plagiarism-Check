"""Excel (.xlsx) multi-sheet comparison workbook exporter using openpyxl."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..models import ClauseVerdict, ObjectConsistency, PlagiarismReportResult
from .md_exporter import CONSISTENCY_LABELS, VERDICT_LABELS

_HEADER_FILL = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
_HEADER_FONT = Font(color="FFFFFF", bold=True, size=10)
_BOLD_FONT = Font(bold=True, size=10)
_THIN_BORDER = Border(
    left=Side(style="thin", color="CBD5E1"),
    right=Side(style="thin", color="CBD5E1"),
    top=Side(style="thin", color="CBD5E1"),
    bottom=Side(style="thin", color="CBD5E1"),
)

_VERDICT_FILLS: dict[ClauseVerdict, PatternFill] = {
    ClauseVerdict.DUPLICATE_EXACT: PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid"),
    ClauseVerdict.DUPLICATE_EQUIVALENT: PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid"),
    ClauseVerdict.DUPLICATE_PARTIAL: PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid"),
    ClauseVerdict.NON_DUPLICATE_DIRECT_REF: PatternFill(start_color="E0F2FE", end_color="E0F2FE", fill_type="solid"),
    ClauseVerdict.NON_DUPLICATE_UPGRADED: PatternFill(start_color="EDE9FE", end_color="EDE9FE", fill_type="solid"),
    ClauseVerdict.NON_DUPLICATE_UNIQUE: PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid"),
}


def _style_header_row(ws, row_idx: int, col_count: int) -> None:
    for col in range(1, col_count + 1):
        cell = ws.cell(row=row_idx, column=col)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        cell.border = _THIN_BORDER


def _auto_fit_columns(ws, max_widths: dict[int, int] | None = None) -> None:
    max_widths = max_widths or {}
    for col in ws.columns:
        col_idx = col[0].column
        col_letter = get_column_letter(col_idx)
        longest = 10
        for cell in col:
            val = str(cell.value or "")
            line_max = max((len(line) for line in val.splitlines()), default=0)
            if line_max > longest:
                longest = line_max
        limit = max_widths.get(col_idx, 50)
        ws.column_dimensions[col_letter].width = min(max(longest + 4, 12), limit)


def export_xlsx_report(report: PlagiarismReportResult, output_path: Path) -> Path:
    """Export a 4-sheet Excel workbook containing Appendix B metrics and clause details."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()

    # ------------------------------------------------------------------
    # Sheet 1: 汇总与标准化对象核验 (步骤 a)
    # ------------------------------------------------------------------
    ws1 = wb.active
    ws1.title = "汇总与对象核验"
    t_meta = report.target_standard

    summary_rows = [
        ["团体标准技术内容重复率检测汇总表（依据附录 B）", ""],
        ["待测团体标准编号", t_meta.standard_code or t_meta.standard_id],
        ["待测团体标准名称", t_meta.standard_title],
        ["识别标准类型", report.standard_type],
        ["生成时间", report.generated_at],
        ["纳入比对条款数 (n1)", report.n1],
        ["技术内容重复条款总数 (n2)", report.n2],
        ["官方内容重复率 R = (n2/n1)×100%", f"{report.duplicate_rate_percent:.2f}%"],
        ["按比例折算参考重复率", f"{report.weighted_duplicate_rate_percent:.2f}%"],
    ]
    for r_i, row in enumerate(summary_rows, start=1):
        ws1.append(row)
        ws1.cell(row=r_i, column=1).font = _BOLD_FONT
        for c_i in (1, 2):
            ws1.cell(row=r_i, column=c_i).border = _THIN_BORDER
            ws1.cell(row=r_i, column=c_i).alignment = Alignment(vertical="center", wrap_text=True)

    ws1.append([])
    start_row = len(summary_rows) + 2
    ws1.append(
        [
            "比对标准编号",
            "比对标准名称",
            "团标标准化对象",
            "比对标准标准化对象",
            "一致性判定",
            "是否纳入比对",
            "核验分析说明",
        ]
    )
    _style_header_row(ws1, start_row, 7)

    for sr in report.scope_matching_results:
        ws1.append(
            [
                sr.reference_code or sr.reference_id,
                sr.reference_title,
                sr.target_object,
                sr.reference_object,
                CONSISTENCY_LABELS[sr.object_consistency],
                "是" if sr.is_eligible_for_comparison else "否（不一致剔除）",
                sr.consistency_reasoning,
            ]
        )
        r_idx = ws1.max_row
        fill_color = (
            "FEE2E2"
            if sr.object_consistency == ObjectConsistency.INCONSISTENT
            else "D1FAE5"
        )
        ws1.cell(row=r_idx, column=5).fill = PatternFill(
            start_color=fill_color, end_color=fill_color, fill_type="solid"
        )
        for c_i in range(1, 8):
            ws1.cell(row=r_idx, column=c_i).border = _THIN_BORDER
            ws1.cell(row=r_idx, column=c_i).alignment = Alignment(vertical="top", wrap_text=True)

    _auto_fit_columns(ws1, {1: 26, 2: 36, 3: 28, 4: 28, 5: 24, 6: 18, 7: 48})

    # ------------------------------------------------------------------
    # Sheet 2: 比对范围界定 (步骤 b)
    # ------------------------------------------------------------------
    ws2 = wb.create_sheet("比对范围界定(步骤b)")
    ws2.append(["章节编号", "章节名称", "是否纳入 n1", "界定理由"])
    _style_header_row(ws2, 1, 4)
    ws2.freeze_panes = "A2"

    for ch in report.chapter_scope_decisions:
        ws2.append(
            [
                ch.chapter_no,
                ch.chapter_title,
                "纳入" if ch.in_comparison_scope else "排除",
                ch.reason,
            ]
        )
        r_idx = ws2.max_row
        for c_i in range(1, 5):
            ws2.cell(row=r_idx, column=c_i).border = _THIN_BORDER
            ws2.cell(row=r_idx, column=c_i).alignment = Alignment(vertical="top", wrap_text=True)
    _auto_fit_columns(ws2, {1: 16, 2: 32, 3: 16, 4: 55})

    # ------------------------------------------------------------------
    # Sheet 3: 逐条技术比对明细 (步骤 c-d)
    # ------------------------------------------------------------------
    ws3 = wb.create_sheet("逐条技术比对明细")
    ws3.append(
        [
            "条款号",
            "所属章节路径",
            "团标条款原文",
            "判定类别",
            "计入 n2 (0/1)",
            "重复占比",
            "对应比对标准条款",
            "技术对比分析理由",
        ]
    )
    _style_header_row(ws3, 1, 8)
    ws3.freeze_panes = "A2"

    for item in report.clause_details:
        v_text = VERDICT_LABELS[item.verdict]
        matched_str = "\n".join(
            f"[{m.reference_code or m.reference_id}] {m.reference_clause_id} {m.reference_clause_title}: {m.reference_excerpt}"
            for m in item.matched_clauses
        ) or "—"

        ws3.append(
            [
                item.clause_id,
                item.chapter_path,
                item.target_text,
                v_text,
                item.official_duplicate_score,
                f"{item.overlap_ratio * 100:.0f}%",
                matched_str,
                item.technical_reasoning,
            ]
        )
        r_idx = ws3.max_row
        v_fill = _VERDICT_FILLS.get(item.verdict)
        if v_fill:
            ws3.cell(row=r_idx, column=4).fill = v_fill
            ws3.cell(row=r_idx, column=5).fill = v_fill
        for c_i in range(1, 9):
            ws3.cell(row=r_idx, column=c_i).border = _THIN_BORDER
            ws3.cell(row=r_idx, column=c_i).alignment = Alignment(vertical="top", wrap_text=True)

    _auto_fit_columns(ws3, {1: 14, 2: 30, 3: 55, 4: 28, 5: 14, 6: 12, 7: 45, 8: 50})

    # ------------------------------------------------------------------
    # Sheet 4: 多标准分项统计表
    # ------------------------------------------------------------------
    ws4 = wb.create_sheet("多标准分项统计")
    ws4.append(
        [
            "比对标准ID",
            "标准编号",
            "标准名称",
            "对象一致性",
            "是否有效比对",
            "n1",
            "单标重复条款 n2,i",
            "单标重复率 Ri",
            "折算参考率",
        ]
    )
    _style_header_row(ws4, 1, 9)
    ws4.freeze_panes = "A2"

    for st in report.per_reference_stats:
        ws4.append(
            [
                st.reference_id,
                st.reference_code,
                st.reference_title,
                CONSISTENCY_LABELS[st.object_consistency],
                "是" if st.is_eligible_for_comparison else "否",
                st.n1,
                st.n2,
                f"{st.duplicate_rate_percent:.2f}%",
                f"{st.weighted_duplicate_rate_percent:.2f}%",
            ]
        )
        r_idx = ws4.max_row
        for c_i in range(1, 10):
            ws4.cell(row=r_idx, column=c_i).border = _THIN_BORDER
            ws4.cell(row=r_idx, column=c_i).alignment = Alignment(vertical="center", wrap_text=True)
    _auto_fit_columns(ws4, {1: 16, 2: 24, 3: 36, 4: 24, 5: 14, 6: 10, 7: 18, 8: 16, 9: 16})

    wb.save(str(output_path))
    return output_path
