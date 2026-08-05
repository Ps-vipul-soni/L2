"""
Shared Pydantic state schemas for the compliance screening pipeline.

LOCKED for Phase 1 — Document Understanding, Chemical Normalization,
and Compliance Screening must all import from this file rather than
defining their own local shapes. This is what keeps the 3 parallel
Phase 1 agents (Chemical Identity MCP, Regulation Lookup MCP,
Document Understanding) compatible when the integration task wires
them together.

Do not redesign the DB schema (schema_v1_draft.sql) to fit these —
these models are shaped to map cleanly onto the existing 14 tables,
not the other way around.
"""

from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ============================================================
# 1. Document Understanding agent output
#    (Gemini + PyMuPDF -> structured extraction, never free text)
# ============================================================

class ExtractedIngredient(BaseModel):
    """One ingredient line as read off the source document, pre-normalization."""
    raw_name: str = Field(..., description="Ingredient name exactly as it appears in the document")
    cas_number: Optional[str] = Field(None, description="CAS number if printed on the document; null if not present")
    concentration_value: Optional[float] = Field(None, description="Numeric concentration if stated")
    concentration_unit: Optional[Literal["%", "ppm", "mg/kg"]] = Field(
        None, description="Unit for concentration_value; null if concentration not stated"
    )


class ExtractedComponent(BaseModel):
    """One component/part within the product as described by the document.
    For a single-material SDS, this will typically be a single component
    whose name mirrors the product/material name on the SDS.
    """
    component_name: str
    ingredients: list[ExtractedIngredient] = Field(default_factory=list)


class DocumentExtractionResult(BaseModel):
    """Top-level structured output of the Document Understanding agent.
    Maps to: documents (doc_type, extraction_confidence) +
    components + component_ingredients + ingredient_synonyms (raw_name).
    """
    doc_type: Literal["SDS", "BOM", "FMD", "SUPPLIER_DECLARATION"]
    product_name_hint: Optional[str] = Field(
        None, description="Product/material name as best inferred from the document, for linking to products.name"
    )
    components: list[ExtractedComponent] = Field(default_factory=list)
    extraction_confidence: float = Field(
        ..., ge=0.0, le=1.0,
        description="Agent's self-assessed confidence in the completeness/correctness of this extraction. "
                    "Below-threshold values route to review_queue in Phase 2."
    )
    extraction_notes: Optional[str] = Field(
        None, description="Free-text notes on ambiguity, illegible sections, or assumptions made — "
                           "for human review context, not for downstream logic."
    )


# ============================================================
# 2. Chemical Normalization tool node output
#    (deterministic — no LLM call — resolves raw_name -> canonical ingredient)
# ============================================================

class NormalizedIngredient(BaseModel):
    """Result of resolving one ExtractedIngredient against PubChem via the
    Chemical Identity MCP server. Maps to: ingredients + ingredient_synonyms.
    """
    raw_name: str = Field(..., description="Echoes the input raw_name, for traceability back to the source line")
    canonical_name: str
    cas_number: Optional[str] = None
    pubchem_cid: Optional[str] = None
    concentration_value: Optional[float] = None
    concentration_unit: Optional[Literal["%", "ppm", "mg/kg"]] = None
    resolution_method: Literal["exact_cas_match", "pubchem_synonym_lookup", "unresolved"] = Field(
        ..., description="How this ingredient was resolved — 'unresolved' means PubChem had no match; "
                          "the ingredient should still flow downstream with null cas_number/pubchem_cid "
                          "rather than being dropped."
    )


class NormalizedComponent(BaseModel):
    component_name: str
    ingredients: list[NormalizedIngredient] = Field(default_factory=list)


class NormalizationResult(BaseModel):
    document_id: str = Field(..., description="UUID of the source documents row this normalization ran against")
    components: list[NormalizedComponent] = Field(default_factory=list)


# ============================================================
# 3. Compliance Screening agent output
#    (per component/ingredient/regulation — maps to screening_results)
# ============================================================

ScreeningStatus = Literal[
    "RESTRICTED", "ALLOWED", "THRESHOLD_EXCEEDED", "EXEMPTION_AVAILABLE", "NEEDS_REVIEW"
]


class ScreeningResult(BaseModel):
    """One row of screening output. Maps 1:1 onto the screening_results table
    (component_id/ingredient_id/regulation_id are resolved/attached by the
    tool layer when persisting — the agent works with names/CAS numbers,
    not raw UUIDs).
    """
    component_name: str
    ingredient_cas_number: Optional[str]
    ingredient_canonical_name: str
    regulation_code: Literal["RoHS", "REACH_SVHC"]
    status: ScreeningStatus
    measured_value: Optional[float] = None
    threshold_value: Optional[float] = None
    confidence: float = Field(
        ..., ge=0.0, le=1.0,
        description="Confidence in the screening judgment itself (e.g. exemption applicability), "
                    "distinct from the source document's extraction_confidence. "
                    "Below-threshold values route to review_queue in Phase 2."
    )
    reasoning: str = Field(
        ..., description="Explainability text: why this status was assigned, citing the specific "
                          "threshold/exemption that applied. Required, never empty."
    )


class ScreeningRunResult(BaseModel):
    workflow_run_id: str
    results: list[ScreeningResult] = Field(default_factory=list)


# ============================================================
# 4. Risk & Decision agent output
#    (maps to compliance_decisions)
# ============================================================

OverallStatus = Literal["PASS", "FAIL", "WARNING", "REVIEW_REQUIRED"]


class ComplianceDecision(BaseModel):
    workflow_run_id: str
    product_id: str
    overall_status: OverallStatus
    risk_score: float = Field(..., ge=0.0, le=100.0)
    decision_rationale: str = Field(
        ..., description="Short explanation of how overall_status/risk_score were derived from the "
                          "underlying screening_results — for the executive summary and for human review."
    )


# ============================================================
# 5. Report Generation agent output
#    (maps to reports.executive_summary; file_path set after write-to-disk)
# ============================================================

class ComplianceReport(BaseModel):
    workflow_run_id: str
    compliance_decision_id: str
    executive_summary: str
    violation_summary: str
    affected_ingredients: list[str] = Field(default_factory=list)
    applicable_regulations: list[str] = Field(default_factory=list)
    risk_analysis: str
    recommended_actions: list[str] = Field(default_factory=list)
