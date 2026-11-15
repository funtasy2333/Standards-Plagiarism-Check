"""Pydantic domain models for OCR, clause parsing, Appendix B assessment, and reports."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class OcrResult(BaseModel):
    """Normalized result produced by a remote OCR engine."""

    source_file: str
    source_sha256: str
    engine: Literal["deepseek", "paddleocr"]
    markdown_path: str
    markdown_text: str
    page_count: int = 0
    converted_pdf_path: str | None = None
    cached: bool = False
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class ChapterOverview(BaseModel):
    """Top-level chapter summary extracted from a parsed standard."""

    chapter_no: str
    chapter_title: str
    is_normative_appendix: bool = False
    is_informative_appendix: bool = False
    auto_excluded: bool = False
    auto_exclude_reason: str | None = None
    leaf_clause_count: int = 0
    leaf_clause_ids: list[str] = Field(default_factory=list)


class LeafClause(BaseModel):
    """Smallest numbered clause unit (leaf node) per GB/T 1.1."""

    clause_id: str
    title: str = ""
    chapter_no: str
    chapter_title: str = ""
    chapter_path: str = ""
    level: int = 1
    is_normative_appendix: bool = False
    auto_excluded: bool = False
    auto_exclude_reason: str | None = None
    content: str = ""
    tables: list[str] = Field(default_factory=list)
    page_numbers: list[int] = Field(default_factory=list)
    detected_normative_refs: list[str] = Field(default_factory=list)

    @property
    def full_text(self) -> str:
        """Combined heading, content, and tables for review and reporting."""
        header = f"{self.clause_id} {self.title}".strip()
        parts = [header]
        if self.content.strip():
            parts.append(self.content.strip())
        if self.tables:
            parts.extend(t.strip() for t in self.tables if t.strip())
        return "\n\n".join(parts)


class StandardMetadata(BaseModel):
    """Metadata extracted from the front matter and introductory chapters of a standard."""

    standard_id: str
    role: Literal["target", "reference"]
    standard_code: str = ""
    standard_title: str = ""
    source_file: str = ""
    markdown_file: str = ""
    ocr_engine: str = ""
    scope_chapter_text: str = ""
    normative_references_chapter_text: str = ""
    detected_normative_ref_codes: list[str] = Field(default_factory=list)


class ParsedStandard(BaseModel):
    """Complete parsed representation of a standard Markdown document."""

    metadata: StandardMetadata
    chapters: list[ChapterOverview] = Field(default_factory=list)
    all_leaf_clauses: list[LeafClause] = Field(default_factory=list)
    candidate_leaf_clauses: list[LeafClause] = Field(default_factory=list)


class ObjectConsistency(str, Enum):
    """Appendix B Step a): Consistency of standardization object between target and reference."""

    IDENTICAL = "IDENTICAL"
    SIMILAR = "SIMILAR"
    INCONSISTENT = "INCONSISTENT"


class ObjectConsistencyResult(BaseModel):
    """Appendix B Step a): Assessment of standardization object and scope alignment."""

    reference_id: str
    reference_code: str = ""
    reference_title: str = ""
    target_object: str = Field(
        ..., description="Explicitly identified standardization object of the group standard."
    )
    reference_object: str = Field(
        ..., description="Explicitly identified standardization object of the reference standard."
    )
    target_scope_summary: str = ""
    reference_scope_summary: str = ""
    object_consistency: ObjectConsistency
    is_eligible_for_comparison: bool = Field(
        ...,
        description="Must be False when object_consistency is INCONSISTENT.",
    )
    consistency_reasoning: str = ""

    @model_validator(mode="after")
    def _enforce_eligibility_rule(self) -> "ObjectConsistencyResult":
        if self.object_consistency == ObjectConsistency.INCONSISTENT:
            self.is_eligible_for_comparison = False
        return self


class ChapterScopeDecision(BaseModel):
    """Appendix B Step b): Host Agent decision on whether a chapter belongs to core technical scope."""

    chapter_no: str
    chapter_title: str = ""
    in_comparison_scope: bool
    reason: str = ""


class ClauseVerdict(str, Enum):
    """Technical duplication verdict for a single leaf clause."""

    DUPLICATE_EXACT = "DUPLICATE_EXACT"
    DUPLICATE_EQUIVALENT = "DUPLICATE_EQUIVALENT"
    DUPLICATE_PARTIAL = "DUPLICATE_PARTIAL"
    NON_DUPLICATE_DIRECT_REF = "NON_DUPLICATE_DIRECT_REF"
    NON_DUPLICATE_UPGRADED = "NON_DUPLICATE_UPGRADED"
    NON_DUPLICATE_UNIQUE = "NON_DUPLICATE_UNIQUE"


class MatchedReferenceClause(BaseModel):
    """Reference clause matched against a target leaf clause."""

    reference_id: str
    reference_code: str = ""
    reference_clause_id: str
    reference_clause_title: str = ""
    reference_excerpt: str = ""
    overlap_contribution: float = Field(default=1.0, ge=0.0, le=1.0)
    match_note: str = ""


class ClauseComparison(BaseModel):
    """Appendix B Step c & d): Detailed technical comparison result for one leaf clause."""

    clause_id: str
    verdict: ClauseVerdict
    overlap_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    matched_clauses: list[MatchedReferenceClause] = Field(default_factory=list)
    technical_reasoning: str = ""

    @model_validator(mode="after")
    def _normalize_overlap_by_verdict(self) -> "ClauseComparison":
        if self.verdict in (
            ClauseVerdict.DUPLICATE_EXACT,
            ClauseVerdict.DUPLICATE_EQUIVALENT,
        ):
            self.overlap_ratio = 1.0
        elif self.verdict in (
            ClauseVerdict.NON_DUPLICATE_DIRECT_REF,
            ClauseVerdict.NON_DUPLICATE_UPGRADED,
            ClauseVerdict.NON_DUPLICATE_UNIQUE,
        ):
            self.overlap_ratio = 0.0
        return self


class ComparisonAssessment(BaseModel):
    """JSON payload produced by the host Agent following SKILL.md."""

    schema_version: str = "1.0"
    target_standard_id: str = "target"
    standard_type: str = Field(
        default="产品标准",
        description="Identified standard type, e.g., 产品标准, 方法标准, 管理标准, 服务标准.",
    )
    scope_matching_results: list[ObjectConsistencyResult] = Field(default_factory=list)
    chapter_scope_decisions: list[ChapterScopeDecision] = Field(default_factory=list)
    clause_comparisons: list[ClauseComparison] = Field(default_factory=list)
    overall_expert_notes: str = ""


class ReferenceDuplicateStats(BaseModel):
    """Per-reference standard duplication rate breakdown."""

    reference_id: str
    reference_code: str = ""
    reference_title: str = ""
    target_object: str = ""
    reference_object: str = ""
    object_consistency: ObjectConsistency
    is_eligible_for_comparison: bool
    consistency_reasoning: str = ""
    n1: int
    n2: int
    duplicate_rate_percent: float
    weighted_numerator: float
    weighted_duplicate_rate_percent: float


class EnrichedClauseDetail(BaseModel):
    """Combined leaf clause source content + comparison verdict + calculated score."""

    clause_id: str
    title: str
    chapter_no: str
    chapter_path: str
    target_text: str
    tables: list[str] = Field(default_factory=list)
    page_numbers: list[int] = Field(default_factory=list)
    detected_normative_refs: list[str] = Field(default_factory=list)
    verdict: ClauseVerdict
    official_duplicate_score: int = Field(description="1 if counted in n2, else 0")
    overlap_ratio: float
    matched_clauses: list[MatchedReferenceClause] = Field(default_factory=list)
    technical_reasoning: str = ""


class PlagiarismReportResult(BaseModel):
    """Final verified Appendix B calculation and report model."""

    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    )
    target_standard: StandardMetadata
    reference_standards: list[StandardMetadata] = Field(default_factory=list)
    standard_type: str
    scope_matching_results: list[ObjectConsistencyResult] = Field(default_factory=list)
    eligible_reference_ids: list[str] = Field(default_factory=list)
    ineligible_reference_ids: list[str] = Field(default_factory=list)
    chapter_scope_decisions: list[ChapterScopeDecision] = Field(default_factory=list)
    excluded_clauses_count: int = 0
    n1: int
    n2: int
    duplicate_rate_percent: float
    weighted_numerator: float
    weighted_duplicate_rate_percent: float
    per_reference_stats: list[ReferenceDuplicateStats] = Field(default_factory=list)
    verdict_counts: dict[str, int] = Field(default_factory=dict)
    clause_details: list[EnrichedClauseDetail] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    overall_expert_notes: str = ""
