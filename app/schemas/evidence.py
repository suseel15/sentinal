"""A3 evidence schemas."""
from typing import Any, Optional
from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    evidence_id: str
    type: str
    direction: str = Field(description="SUPPORTING | CONTRADICTING | NEUTRAL")
    title: str
    description: str
    actual_value: Optional[Any] = None
    comparison_value: Optional[Any] = None
    confidence: float = 0.0
    source: str = "UNKNOWN"
    source_tier: str = "T1"
    status: str = Field(default="AVAILABLE", description="AVAILABLE | UNAVAILABLE")


class EvidenceSummary(BaseModel):
    total: int = 0
    supporting: int = 0
    contradicting: int = 0
    avg_confidence: float = 0.0
    completeness: float = 0.0
    status: str = "PARTIAL"


class EvidencePack(BaseModel):
    investigation_id: str
    agent: str = "A3"
    status: str = "PARTIAL"
    evidence_summary: EvidenceSummary = Field(default_factory=EvidenceSummary)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    transaction_id: Optional[str] = None
