"""A3 scoring: confidence, direction, completeness, corroboration."""
import logging

log = logging.getLogger(__name__)

TIER_WEIGHTS = {"T1": 1.0, "T2": 0.75, "T3": 0.5, "T4": 0.25}
REQUIRED_CATEGORIES = ("customer_history", "beneficiary", "velocity", "profile", "previous_alerts")


def confidence(reliability_tier="T1", completeness=1.0, recency_days=0, corroboration=1) -> float:
    try:
        w = TIER_WEIGHTS.get(str(reliability_tier or "T1").upper(), 0.5)
        comp = max(0.0, min(1.0, float(completeness)))
        try:
            rd = max(0.0, float(recency_days or 0))
        except (TypeError, ValueError):
            rd = 0.0
        recency_factor = max(0.5, 1.0 - rd / 180.0)
        try:
            cor = max(0, int(corroboration or 0))
        except (TypeError, ValueError):
            cor = 1
        cor_factor = min(1.0, 0.7 + 0.15 * cor)
        score = w * (0.6 + 0.4 * comp) * recency_factor * cor_factor
        return round(max(0.0, min(1.0, score)), 3)
    except Exception:
        log.exception("confidence failed")
        return 0.5


def assign_direction(evidence_type: str, values: dict | None = None) -> str:
    try:
        v = values or {}
        if v.get("status") == "UNAVAILABLE":
            return "NEUTRAL"
        t = str(evidence_type or "").upper()
        if t in ("BEHAVIORAL_DEVIATION", "BEHAVIORAL", "AMOUNT_DEVIATION", "CUSTOMER_HISTORY"):
            return "SUPPORTING" if bool(v.get("is_deviation")) else "CONTRADICTING"
        if t in ("BENEFICIARY_HISTORY", "BENEFICIARY"):
            return "SUPPORTING" if bool(v.get("is_new")) else "CONTRADICTING"
        if t in ("VELOCITY",):
            hv = v.get("is_high_velocity", v.get("is_high", False))
            return "SUPPORTING" if bool(hv) else "CONTRADICTING"
        if t in ("PROFILE_CONSISTENCY", "PROFILE"):
            return "SUPPORTING" if bool(v.get("is_inconsistent", v.get("inconsistent", False))) else "CONTRADICTING"
        if t in ("PREVIOUS_ALERTS", "PREVIOUS", "HISTORY_ALERTS"):
            cnt = int(v.get("prior_count", v.get("count", 0)) or 0)
            if cnt > 0 or bool(v.get("has_prior")):
                return "SUPPORTING"
            return "CONTRADICTING"
        if t in ("RULE", "RULE_EVIDENCE"):
            try:
                rs = int(v.get("rule_score", 0) or 0)
            except (TypeError, ValueError):
                rs = 0
            typos = v.get("possible_typologies") or []
            if rs >= 20 or (rs > 0 and len(typos) > 0):
                return "SUPPORTING"
            return "CONTRADICTING" if rs <= 0 else "NEUTRAL"
        if t in ("MODEL", "MODEL_EVIDENCE"):
            try:
                risk = float(v.get("risk_score", 0) or 0)
            except (TypeError, ValueError):
                risk = 0.0
            lvl = str(v.get("risk_level", "") or "").upper()
            if risk >= 60 or lvl in ("HIGH", "CRITICAL", "VERY_HIGH"):
                return "SUPPORTING"
            if risk <= 40 or lvl in ("LOW", "MINIMAL", "VERY_LOW"):
                return "CONTRADICTING"
            return "NEUTRAL"
        if t in ("DEVICE", "LOCATION"):
            return "NEUTRAL"
        return "NEUTRAL"
    except Exception:
        log.exception("assign_direction failed")
        return "NEUTRAL"


def completeness(status_map: dict) -> float:
    try:
        if not isinstance(status_map, dict):
            return 0.0
        avail = 0
        for cat in REQUIRED_CATEGORIES:
            s = status_map.get(cat)
            if s is True or s == "AVAILABLE" or s == 1:
                avail += 1
            elif isinstance(s, dict) and s.get("status") == "AVAILABLE":
                avail += 1
        return round(avail / len(REQUIRED_CATEGORIES), 3)
    except Exception:
        log.exception("completeness failed")
        return 0.0


def corroboration_count(items: list, finding_key: str) -> int:
    try:
        n = 0
        for it in items:
            try:
                d = it.model_dump() if hasattr(it, "model_dump") else dict(it)
            except Exception:
                continue
            if str(d.get("finding_key", d.get("type", ""))) == str(finding_key):
                n += 1
            elif d.get("finding_key") is None and str(d.get("type", "")).upper() == str(finding_key).upper():
                n += 1
        return int(n)
    except Exception:
        log.exception("corroboration_count failed")
        return 0
