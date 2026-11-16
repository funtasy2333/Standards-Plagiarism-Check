"""Parse OCR-generated standard Markdown into GB/T 1.1 chapters and leaf clauses."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ..models import (
    ChapterOverview,
    LeafClause,
    ParsedStandard,
    StandardMetadata,
)

_PAGE_MARKER_RE = re.compile(r"<!--\s*page:\s*(\d+)\s*-->")

# Matches standard codes like GB/T 12345—2024, GB 4706.1-2005, T/CESA 1001-2023, ISO 9001:2015
_STANDARD_CODE_RE = re.compile(
    r"\b(?:GB/T|GB/Z|GB|JB/T|HG/T|YY/T|YD/T|SJ/T|QB/T|NB/T|DL/T|SH/T|NY/T|LY/T|"
    r"HJ|AQ|WS/T|GA/T|JT/T|CJ/T|JGJ|DB\d{2}(?:/T)?|T/[A-Za-z0-9]+|"
    r"ISO(?:/IEC)?|IEC|ASTM|EN)\s*[A-Za-z0-9.\-]+(?:\s*[—\-–:]\s*\d{4})?",
    re.IGNORECASE,
)

# Normative citation verbs combined with standard codes inside clauses
_NORMATIVE_REF_CONTEXT_RE = re.compile(
    r"(?:按|按照|依照|依据|参照|符合|执行|采用|见)\s*[^。；;\n]{0,30}?"
    r"((?:GB/T|GB/Z|GB|JB/T|HG/T|YY/T|YD/T|SJ/T|QB/T|NB/T|DL/T|SH/T|NY/T|LY/T|"
    r"HJ|AQ|WS/T|GA/T|JT/T|CJ/T|JGJ|DB\d{2}(?:/T)?|T/[A-Za-z0-9]+|"
    r"ISO(?:/IEC)?|IEC|ASTM|EN)\s*[A-Za-z0-9.\-]+(?:\s*[—\-–:]\s*\d{4})?)",
    re.IGNORECASE,
)

_FRONT_BACK_SECTION_RE = re.compile(
    r"^(?:#{1,6}\s*)?(?:\*{1,2})?\s*(前言|引\s*言|目\s*次|目\s*录|参考文献|索\s*引)\s*(?:\*{1,2})?$"
)

_APPENDIX_HEADER_RE = re.compile(
    r"^(?:#{1,6}\s*)?(?:\*{1,2})?\s*附\s*录\s*([A-Z])\s*"
    r"(?:[（(]\s*(规范性|资料性)(?:附录)?\s*[）)])?\s*(.*?)(?:\*{1,2})?$"
)

_APPENDIX_TYPE_LINE_RE = re.compile(
    r"^\s*[（(]\s*(规范性|资料性)(?:附录)?\s*[）)]\s*$"
)

# Top-level chapter header: e.g., "## 1 范围", "5 技术要求"
_TOP_CHAPTER_RE = re.compile(
    r"^(?:#{1,6}\s*)?(?:\*{1,2})?(\d{1,2})\s+([^\d\s].*?)(?:\*{1,2})?$"
)

# Sub-clause header: e.g., "5.1 一般要求", "5.2.1 拉伸强度", "A.1.2 试验步骤"
_SUB_CLAUSE_RE = re.compile(
    r"^(?:#{1,6}\s*)?(?:\*{1,2})?((?:\d{1,2}|[A-Z])(?:\.\d{1,3})+)\s+([^\s].*?)(?:\*{1,2})?$"
)

# Measurement / unit guards to prevent false clause matches like "5.2 mm" or "3.5 %"
_UNIT_PREFIX_RE = re.compile(
    r"^(?:%|‰|mm|cm|m|km|mg|g|kg|t|ml|L|℃|°C|K|Pa|kPa|MPa|GPa|V|kV|A|mA|W|kW|"
    r"Hz|kHz|MHz|h|min|s|ms|dB|倍|个|条|项|年|月|日|次|批|级|类|种|份|页|组)\b",
    re.IGNORECASE,
)

_TERM_CHAPTER_KEYWORDS = ("术语", "定义", "缩略语", "符号")
_SCOPE_CHAPTER_KEYWORDS = ("范围", "适用范围")
_NORM_REF_CHAPTER_KEYWORDS = ("规范性引用文件", "引用标准", "引用文件")


@dataclass
class _RawSection:
    clause_id: str
    title: str
    chapter_no: str
    chapter_title: str
    level: int
    is_normative_appendix: bool = False
    is_informative_appendix: bool = False
    auto_excluded: bool = False
    auto_exclude_reason: str | None = None
    lines: list[str] = field(default_factory=list)
    page_numbers: list[int] = field(default_factory=list)
    children: list["_RawSection"] = field(default_factory=list)
    parent: "_RawSection | None" = None


def _strip_md_formatting(text: str) -> str:
    text = re.sub(r"^#{1,6}\s*", "", text.strip())
    text = text.strip("*").strip()
    return re.sub(r"\s+", " ", text).strip()


def _extract_tables_and_body(lines: list[str]) -> tuple[str, list[str]]:
    """Separate Markdown/HTML tables from prose lines while preserving clean order."""
    tables: list[str] = []
    body_lines: list[str] = []

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Detect HTML <table>...</table> block
        if stripped.lower().startswith("<table"):
            tbl_lines = [line]
            i += 1
            while i < n and "</table>" not in tbl_lines[-1].lower():
                tbl_lines.append(lines[i])
                if "</table>" in lines[i].lower():
                    i += 1
                    break
                i += 1
            tbl_str = "\n".join(tbl_lines).strip()
            tables.append(tbl_str)
            body_lines.append(tbl_str)
            continue

        # Detect Markdown pipe table (at least 2 consecutive pipe lines with separator row)
        if stripped.startswith("|") and stripped.endswith("|") and i + 1 < n:
            next_stripped = lines[i + 1].strip()
            if next_stripped.startswith("|") and set(next_stripped.replace("|", "").replace("-", "").replace(":", "").strip()) == set():
                tbl_lines = [line, lines[i + 1]]
                i += 2
                while i < n and lines[i].strip().startswith("|"):
                    tbl_lines.append(lines[i])
                    i += 1
                tbl_str = "\n".join(tbl_lines).strip()
                tables.append(tbl_str)
                body_lines.append(tbl_str)
                continue

        body_lines.append(line)
        i += 1

    content = "\n".join(body_lines).strip()
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content, tables


def _extract_normative_refs_from_text(text: str) -> list[str]:
    matches = _NORMATIVE_REF_CONTEXT_RE.findall(text)
    seen: list[str] = []
    for m in matches:
        code = re.sub(r"\s+", " ", m).strip()
        if code and code not in seen:
            seen.append(code)
    return seen


def _extract_front_matter_metadata(
    markdown_text: str,
) -> tuple[str, str]:
    """Heuristically extract standard code and title from document header lines."""
    standard_code = ""
    standard_title = ""

    head_lines = markdown_text.splitlines()[:60]
    for raw in head_lines:
        line = _strip_md_formatting(raw)
        if not line or line.startswith("<!--"):
            continue
        if _FRONT_BACK_SECTION_RE.match(line) or _TOP_CHAPTER_RE.match(line):
            break

        if not standard_code:
            code_match = _STANDARD_CODE_RE.search(line)
            if code_match:
                standard_code = re.sub(r"\s+", " ", code_match.group(0)).strip()

        # Candidate title: Chinese characters, not just standard type label or ICS/CCS line
        if not standard_title and len(line) >= 4:
            if any(
                skip in line
                for skip in (
                    "ICS ",
                    "CCS ",
                    "中华人民共和国",
                    "团体标准",
                    "国家标准",
                    "行业标准",
                    "地方标准",
                    "发布",
                    "实施",
                    "代替",
                )
            ):
                continue
            if _STANDARD_CODE_RE.fullmatch(line):
                continue
            if re.search(r"[\u4e00-\u9fff]{2,}", line):
                standard_title = line

    return standard_code, standard_title


def _classify_top_chapter(
    chapter_no: str, chapter_title: str
) -> tuple[bool, str | None]:
    """Apply hard auto-exclusion rules for Chapters 1, 2, 3 (Terms)."""
    clean_title = chapter_title.strip()
    if chapter_no == "1" and (
        any(k in clean_title for k in _SCOPE_CHAPTER_KEYWORDS) or not clean_title
    ):
        return True, "第1章 范围（自动排除）"
    if chapter_no == "2" and (
        any(k in clean_title for k in _NORM_REF_CHAPTER_KEYWORDS) or not clean_title
    ):
        return True, "第2章 规范性引用文件（自动排除）"
    if chapter_no == "3" and any(k in clean_title for k in _TERM_CHAPTER_KEYWORDS):
        return True, "第3章 术语和定义（自动排除）"
    return False, None


def _build_section_path(sec: _RawSection) -> str:
    chain: list[str] = []
    cur: _RawSection | None = sec
    while cur is not None:
        label = f"{cur.clause_id} {cur.title}".strip()
        chain.append(label)
        cur = cur.parent
    return " > ".join(reversed(chain))


def parse_standard_markdown(
    markdown_text: str,
    *,
    standard_id: str = "target",
    role: Literal["target", "reference"] = "target",
    source_file: str = "",
    markdown_file: str = "",
    ocr_engine: str = "",
) -> ParsedStandard:
    """Parse standard Markdown into metadata, chapters overview, and GB/T 1.1 leaf clauses."""
    standard_code, standard_title = _extract_front_matter_metadata(markdown_text)

    lines = markdown_text.splitlines()
    top_sections: list[_RawSection] = []
    section_stack: list[_RawSection] = []

    current_chapter: _RawSection | None = None
    current_page = 1
    expected_next_top_no = 1

    i = 0
    total_lines = len(lines)
    while i < total_lines:
        raw_line = lines[i]
        stripped = raw_line.strip()

        page_match = _PAGE_MARKER_RE.search(stripped)
        if page_match:
            current_page = int(page_match.group(1))
            i += 1
            continue

        # 1. Front/back matter (前言, 引言, 目次, 参考文献, 索引)
        fb_match = _FRONT_BACK_SECTION_RE.match(stripped)
        if fb_match:
            sec_name = re.sub(r"\s+", "", fb_match.group(1))
            sec = _RawSection(
                clause_id=sec_name,
                title="",
                chapter_no=sec_name,
                chapter_title="",
                level=1,
                auto_excluded=True,
                auto_exclude_reason=f"{sec_name}（自动排除）",
                page_numbers=[current_page],
            )
            top_sections.append(sec)
            current_chapter = sec
            section_stack = [sec]
            i += 1
            continue

        # 2. Appendix header (附录 A（规范性）/（资料性）)
        app_match = _APPENDIX_HEADER_RE.match(stripped)
        if app_match:
            app_letter = app_match.group(1).upper()
            app_kind = app_match.group(2) or ""
            app_title = _strip_md_formatting(app_match.group(3) or "")

            # Check next non-empty line for standalone "（规范性）" or title
            lookahead = i + 1
            while lookahead < total_lines and not lines[lookahead].strip():
                lookahead += 1
            if not app_kind and lookahead < total_lines:
                type_m = _APPENDIX_TYPE_LINE_RE.match(lines[lookahead].strip())
                if type_m:
                    app_kind = type_m.group(1)
                    i = lookahead
                    # Check line after that for title if app_title is empty
                    if not app_title:
                        next_t = i + 1
                        while next_t < total_lines and not lines[next_t].strip():
                            next_t += 1
                        if next_t < total_lines and not _SUB_CLAUSE_RE.match(lines[next_t].strip()):
                            cand_title = _strip_md_formatting(lines[next_t])
                            if len(cand_title) <= 60:
                                app_title = cand_title
                                i = next_t

            is_informative = app_kind == "资料性"
            is_normative = app_kind == "规范性" or not is_informative
            sec = _RawSection(
                clause_id=f"附录 {app_letter}",
                title=f"（{app_kind}）{app_title}".strip() if app_kind else app_title,
                chapter_no=f"附录{app_letter}",
                chapter_title=app_title or f"附录 {app_letter}",
                level=1,
                is_normative_appendix=is_normative,
                is_informative_appendix=is_informative,
                auto_excluded=is_informative,
                auto_exclude_reason="资料性附录（自动排除）" if is_informative else None,
                page_numbers=[current_page],
            )
            top_sections.append(sec)
            current_chapter = sec
            section_stack = [sec]
            i += 1
            continue

        # 3. Top-level numbered chapter (1 范围, 2 规范性引用文件, ..., 5 技术要求)
        top_match = _TOP_CHAPTER_RE.match(stripped)
        if top_match:
            ch_no_str = top_match.group(1)
            ch_no_int = int(ch_no_str)
            ch_title = _strip_md_formatting(top_match.group(2))
            # Guard against false matches like "10 mm" or list lines when inside a chapter
            is_unit = bool(_UNIT_PREFIX_RE.match(ch_title))
            is_plausible_chapter = (
                1 <= ch_no_int <= 30
                and not is_unit
                and (
                    ch_no_int >= expected_next_top_no
                    or current_chapter is None
                    or current_chapter.chapter_no in ("前言", "引言", "目次", "目录")
                )
            )
            # Also skip if it's inside TOC (目次) and line ends with page number digits
            if current_chapter and current_chapter.chapter_no in ("目次", "目录"):
                # TOC entries end in a page number (often after dot leaders).
                # A chapter heading without that suffix starts the body.
                is_plausible_chapter = is_plausible_chapter and not re.search(
                    r"(?:[.．…·]{2,}\s*|\s+)\d+\s*$", ch_title
                )

            if is_plausible_chapter:
                auto_excl, excl_reason = _classify_top_chapter(ch_no_str, ch_title)
                sec = _RawSection(
                    clause_id=ch_no_str,
                    title=ch_title,
                    chapter_no=ch_no_str,
                    chapter_title=ch_title,
                    level=1,
                    auto_excluded=auto_excl,
                    auto_exclude_reason=excl_reason,
                    page_numbers=[current_page],
                )
                top_sections.append(sec)
                current_chapter = sec
                section_stack = [sec]
                expected_next_top_no = ch_no_int + 1
                i += 1
                continue

        # 4. Numbered sub-clause (e.g. 5.1, 5.2.1, A.1.1)
        sub_match = _SUB_CLAUSE_RE.match(stripped)
        if sub_match and current_chapter is not None:
            if current_chapter.chapter_no in ("目次", "目录", "参考文献", "索引"):
                sub_match = None

        if sub_match and current_chapter is not None:
            clause_id = sub_match.group(1)
            rest_text = _strip_md_formatting(sub_match.group(2))
            first_part = clause_id.split(".")[0]

            # Must match current chapter number (or appendix letter) and not be a measurement
            chapter_root = (
                current_chapter.chapter_no.replace("附录", "")
                if current_chapter.chapter_no.startswith("附录")
                else current_chapter.chapter_no
            )
            if first_part == chapter_root and not _UNIT_PREFIX_RE.match(rest_text):
                level = clause_id.count(".") + 1

                # Separate short heading vs inline clause sentence:
                # If title is short (<= 35 chars) and has no sentence-ending punctuation, treat as title.
                # Otherwise treat rest_text as inline clause content with an empty/short title.
                if len(rest_text) <= 35 and not any(p in rest_text for p in ("。", "；", "：")):
                    title = rest_text
                    initial_body: list[str] = []
                else:
                    title = ""
                    initial_body = [rest_text]

                # Find parent in section_stack whose level < level
                while section_stack and section_stack[-1].level >= level:
                    section_stack.pop()
                parent = section_stack[-1] if section_stack else current_chapter

                sec = _RawSection(
                    clause_id=clause_id,
                    title=title,
                    chapter_no=current_chapter.chapter_no,
                    chapter_title=current_chapter.chapter_title,
                    level=level,
                    is_normative_appendix=current_chapter.is_normative_appendix,
                    is_informative_appendix=current_chapter.is_informative_appendix,
                    auto_excluded=current_chapter.auto_excluded,
                    auto_exclude_reason=current_chapter.auto_exclude_reason,
                    lines=initial_body,
                    page_numbers=[current_page],
                    parent=parent,
                )
                parent.children.append(sec)
                section_stack.append(sec)
                i += 1
                continue

        # 5. Append regular content line to active section
        if section_stack:
            active = section_stack[-1]
            active.lines.append(raw_line)
            if current_page not in active.page_numbers:
                active.page_numbers.append(current_page)

        i += 1

    # Extract Scope (Chapter 1) and Normative References (Chapter 2) metadata
    scope_text = ""
    norm_refs_text = ""
    detected_ref_codes: list[str] = []

    for top in top_sections:
        if top.chapter_no == "1":
            scope_text = _collect_subtree_text(top)
        elif top.chapter_no == "2":
            norm_refs_text = _collect_subtree_text(top)
            for m in _STANDARD_CODE_RE.findall(norm_refs_text):
                code = re.sub(r"\s+", " ", m).strip()
                if code not in detected_ref_codes:
                    detected_ref_codes.append(code)

    # Flatten leaf clauses and chapter overviews
    all_leaf_clauses: list[LeafClause] = []
    candidate_leaf_clauses: list[LeafClause] = []
    chapters: list[ChapterOverview] = []

    for top in top_sections:
        leaves = _collect_leaf_sections(top)
        ch_leaf_ids: list[str] = []

        for leaf in leaves:
            content, tables = _extract_tables_and_body(leaf.lines)
            # Carry constraints from every ancestor, outermost first.
            ancestor = leaf.parent
            while ancestor is not None:
                parent_intro = "\n".join(
                    ln.strip() for ln in ancestor.lines if ln.strip()
                ).strip()
                if parent_intro:
                    content = f"[父条导语] {parent_intro}\n\n{content}".strip()
                ancestor = ancestor.parent

            detected_refs = _extract_normative_refs_from_text(
                f"{leaf.title}\n{content}"
            )
            leaf_model = LeafClause(
                clause_id=leaf.clause_id,
                title=leaf.title,
                chapter_no=leaf.chapter_no,
                chapter_title=leaf.chapter_title,
                chapter_path=_build_section_path(leaf),
                level=leaf.level,
                is_normative_appendix=leaf.is_normative_appendix,
                auto_excluded=leaf.auto_excluded,
                auto_exclude_reason=leaf.auto_exclude_reason,
                content=content,
                tables=tables,
                page_numbers=sorted(set(leaf.page_numbers)),
                detected_normative_refs=detected_refs,
            )
            all_leaf_clauses.append(leaf_model)
            ch_leaf_ids.append(leaf.clause_id)
            if not leaf_model.auto_excluded:
                candidate_leaf_clauses.append(leaf_model)

        chapters.append(
            ChapterOverview(
                chapter_no=top.chapter_no,
                chapter_title=top.chapter_title or top.title,
                is_normative_appendix=top.is_normative_appendix,
                is_informative_appendix=top.is_informative_appendix,
                auto_excluded=top.auto_excluded,
                auto_exclude_reason=top.auto_exclude_reason,
                leaf_clause_count=len(ch_leaf_ids),
                leaf_clause_ids=ch_leaf_ids,
            )
        )

    metadata = StandardMetadata(
        standard_id=standard_id,
        role=role,
        standard_code=standard_code,
        standard_title=standard_title,
        source_file=source_file,
        markdown_file=markdown_file,
        ocr_engine=ocr_engine,
        scope_chapter_text=scope_text,
        normative_references_chapter_text=norm_refs_text,
        detected_normative_ref_codes=detected_ref_codes,
    )

    return ParsedStandard(
        metadata=metadata,
        chapters=chapters,
        all_leaf_clauses=all_leaf_clauses,
        candidate_leaf_clauses=candidate_leaf_clauses,
    )


def _collect_leaf_sections(node: _RawSection) -> list[_RawSection]:
    if not node.children:
        return [node]
    leaves: list[_RawSection] = []
    for child in node.children:
        leaves.extend(_collect_leaf_sections(child))
    return leaves


def _collect_subtree_text(node: _RawSection) -> str:
    parts: list[str] = []
    header = f"{node.clause_id} {node.title}".strip()
    if header:
        parts.append(header)
    body = "\n".join(node.lines).strip()
    if body:
        parts.append(body)
    for child in node.children:
        parts.append(_collect_subtree_text(child))
    return "\n\n".join(p for p in parts if p)
