"""A1 schemas: raw input (any source format) + canonical SENTINEL transaction."""
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


class RawTransaction(BaseModel):
    model_config = {"extra": "allow"}
    data: dict[str, Any] = Field(default_factory=dict)
    source_system: str = "UNKNOWN"


class CanonicalTransaction(BaseModel):
    transaction_id: str
    investigation_id: str
    source_account: str
    destination_account: str
    amount: float
    currency: str = "INR"
    transaction_type: str = "TRANSFER"
    timestamp: datetime
    country: str = "IN"
    device_id: Optional[str] = None
    source_system: str = "UNKNOWN"
    tms_alert: bool = False
    fingerprint: str = ""


class TriageResult(BaseModel):
    transaction_id: str
    triage_score: float
    decision: str  # LOG_ONLY | MONITOR | FULL_INVESTIGATION
    reasons: list[str] = Field(default_factory=list)


class InvestigationResponse(BaseModel):
    transaction_id: str
    investigation_id: str
    triage: TriageResult
    duplicate: bool = False
    detection: Optional[dict[str, Any]] = None
