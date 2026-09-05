"""A4 graph schemas."""
from typing import Any, Optional
from pydantic import BaseModel, Field


class PatternResult(BaseModel):
    pattern_detected: bool = False
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: str = "LOW"
    evidence: list[Any] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    status: str = "AVAILABLE"
    reason: Optional[str] = None


class MoneyFlow(BaseModel):
    seed: str = ""
    hop_count: int = 0
    inflow: float = 0.0
    outflow: float = 0.0
    pass_through_ratio: float = 0.0
    avg_time_between_hops_hours: float = 0.0
    split_ratio: float = 0.0
    concentration: float = 0.0
    retention: float = 0.0
    node_count: int = 0
    edge_count: int = 0


class VizNode(BaseModel):
    id: str
    degree: int = 0
    in_degree: int = 0
    out_degree: int = 0
    volume: float = 0.0
    is_hub: bool = False
    community_id: Optional[int] = None


class VizEdge(BaseModel):
    source: str
    target: str
    amount: float = 0.0
    timestamp: Optional[str] = None
    txn_id: Optional[str] = None
    via_hub: bool = False


class GraphAnalysisResult(BaseModel):
    investigation_id: str
    analysis_mode: str = "FULL"
    status: str = "COMPLETE"
    node_count: int = 0
    edge_count: int = 0
    patterns: dict[str, Any] = Field(default_factory=dict)
    graph_risk_score: float = Field(default=0.0, ge=0.0, le=100.0)
    risk_level: str = "LOW"
    communities: dict[str, Any] = Field(default_factory=dict)
    super_nodes_detected: list[str] = Field(default_factory=list)
    money_flow: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    supporting_entities: list[str] = Field(default_factory=list)
    supporting_transactions: list[str] = Field(default_factory=list)
    manual_review_required: bool = False
