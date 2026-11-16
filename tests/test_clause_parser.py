"""Tests for GB/T 1.1 Markdown clause parser and leaf-clause splitter."""

from __future__ import annotations

from pathlib import Path

from std_plagiarism_check.parser import parse_standard_markdown

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_parse_target_group_standard_structure_and_leaf_clauses() -> None:
    md_text = (FIXTURES_DIR / "target_group_std.md").read_text(encoding="utf-8")
    parsed = parse_standard_markdown(md_text, standard_id="target", role="target")

    # Metadata extraction
    assert "T/CESA 1008—2025" in parsed.metadata.standard_code
    assert "工业互联网边缘网关安全技术要求" in parsed.metadata.standard_title
    assert "工业现场部署的边缘计算网关设备" in parsed.metadata.scope_chapter_text
    assert "GB/T 36951—2018" in parsed.metadata.detected_normative_ref_codes

    # Auto-excluded front/back/introductory chapters
    excluded_chapters = {c.chapter_no for c in parsed.chapters if c.auto_excluded}
    assert {"前言", "引言", "1", "2", "3", "附录B", "参考文献"}.issubset(
        excluded_chapters
    )

    # Candidate leaf clauses (should NOT include parent '5.2' or '5' or '6')
    candidate_ids = [c.clause_id for c in parsed.candidate_leaf_clauses]
    assert candidate_ids == ["4.1", "5.1", "5.2.1", "5.2.2", "5.2.3", "6.1", "6.2", "A.1"]
    assert "5" not in candidate_ids
    assert "5.2" not in candidate_ids
    assert "B.1" not in candidate_ids

    # Table extraction inside 5.2.3
    clause_523 = next(c for c in parsed.candidate_leaf_clauses if c.clause_id == "5.2.3")
    assert len(clause_523.tables) == 1
    assert "暴力破解锁定" in clause_523.tables[0]
    assert clause_523.chapter_path == "5 安全技术要求 > 5.2 网络与通信安全 > 5.2.3 接口物理与逻辑安全指标"

    # Normative reference hint inside 6.1
    clause_61 = next(c for c in parsed.candidate_leaf_clauses if c.clause_id == "6.1")
    assert any("GB/T 2423.1" in ref for ref in clause_61.detected_normative_refs)


def test_measurement_numbers_not_split_as_clauses() -> None:
    md = """# T/TEST 001—2025
# 测试标准

## 1 范围
规定测试要求。

## 4 技术要求

### 4.1 尺寸与偏差
4.1.1 外壳壁厚要求
壁厚应大于等于 4.2 mm，误差不超过 0.5 mm。
5.2 mm 孔径应保持平滑。
"""
    parsed = parse_standard_markdown(md, standard_id="t1", role="target")
    ids = [c.clause_id for c in parsed.candidate_leaf_clauses]
    assert ids == ["4.1.1"]
    assert "4.2 mm" in parsed.candidate_leaf_clauses[0].content
    assert "5.2 mm" in parsed.candidate_leaf_clauses[0].content


def test_body_after_toc_without_front_matter() -> None:
    parsed = parse_standard_markdown('目次\n1 范围 …… 1\n4 技术要求 …… 2\n4.1 安全 …… 2\n1 范围\n适用于设备。\n4 技术要求\n4.1 安全\n应安全。')
    assert [c.clause_id for c in parsed.candidate_leaf_clauses] == ['4.1']
    assert parsed.metadata.scope_chapter_text.endswith('适用于设备。')
    assert parsed.candidate_leaf_clauses[0].content == '应安全。'


def test_leaf_inherits_all_ancestor_constraints() -> None:
    parsed = parse_standard_markdown('4 技术要求\n温度应为20℃。\n4.1 测试\n使用方法甲。\n4.1.1 操作\n执行步骤乙。')
    content = parsed.candidate_leaf_clauses[0].content
    assert '温度应为20℃。' in content
    assert content.index('温度应为20℃。') < content.index('使用方法甲。') < content.index('执行步骤乙。')


def test_single_line_html_table_does_not_consume_following_prose() -> None:
    table = '<table><tr><td>限值</td></tr></table>'
    parsed = parse_standard_markdown(f'4 技术要求\n4.1 安全\n{table}\n表后正文\n<table>\n<tr><td>第二表</td></tr>\n</table>\n末尾正文')
    clause = parsed.candidate_leaf_clauses[0]
    assert clause.tables == [table, '<table>\n<tr><td>第二表</td></tr>\n</table>']
    assert '表后正文' in clause.content and '末尾正文' in clause.content
