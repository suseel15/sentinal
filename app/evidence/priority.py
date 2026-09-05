"""Typology -> evidence priority map.

When A2 surfaces a typology, A3 prioritises the most relevant evidence
sources. This lets the agent pull *more* KYC for ACCOUNT_TAKEOVER
and *more* velocity / beneficiary evidence for RAPID_MOVEMENT, etc.
"""
from __future__ import annotations

PRIORITY: dict[str, list[str]] = {
    "STRUCTURING": ["transaction_history", "kyc", "previous_alerts", "amount_baseline"],
    "SMURFING_FAN_IN": ["transaction_history", "graph", "previous_alerts"],
    "SMURFING_CONSOLIDATION": ["graph", "transaction_history", "previous_alerts"],
    "MULE_PASSTHROUGH": ["graph", "velocity_features", "device_history"],
    "LAYERING": ["graph", "velocity_features", "previous_alerts", "transaction_history"],
    "ROUND_TRIPPING": ["graph", "transaction_history"],
    "SHELL_COMPANY_INVOICING": ["kyc", "transaction_history", "beneficiary_history"],
    "TRADE_BASED_ML": ["kyc", "transaction_history", "beneficiary_history"],
    "CRYPTO_OFFRAMP": ["beneficiary_history", "external_intel", "graph"],
    "ACCOUNT_TAKEOVER": ["device_history", "login_history", "previous_alerts", "kyc"],
    "RAPID_MOVEMENT": ["velocity_features", "transaction_history", "graph"],
    "HIGH_VELOCITY_TRANSFER": ["velocity_features", "transaction_history"],
    "UNUSUAL_TRANSACTION": ["transaction_history", "amount_baseline"],
    "NEW_BENEFICIARY_RISK": ["beneficiary_history", "transaction_history"],
    "POSSIBLE_LAYERING": ["graph", "velocity_features", "transaction_history"],
}


def priorities(typologies: list[str]) -> list[str]:
    seen: list[str] = []
    for t in typologies or []:
        for p in PRIORITY.get(t.upper(), []):
            if p not in seen:
                seen.append(p)
    # Always include the core categories
    for base in ("kyc", "transaction_history", "previous_alerts", "similar_cases"):
        if base not in seen:
            seen.append(base)
    return seen