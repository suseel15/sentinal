"""A1 rule prefilter: weighted risk score -> triage decision. No ML here."""
import json
import logging
from datetime import datetime
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "a1.json"


@lru_cache(maxsize=1)
def load_config() -> dict:
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
    except FileNotFoundError:
        raise FileNotFoundError(f"A1 config missing: {CONFIG_PATH}")
    log.debug("loaded A1 config from %s", CONFIG_PATH)
    return cfg


def _hour(ts) -> int | None:
    if isinstance(ts, datetime):
        return ts.hour
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).hour
    except (ValueError, TypeError):
        return None


def score(canonical: dict, velocity: dict | None) -> tuple[float, list[str]]:
    """Weighted score in [0,1] + human-readable reasons."""
    cfg = load_config()
    w = cfg["prefilter_weights"]
    refs = cfg.get("amount_reference", {"large": 500000, "very_large": 2000000})
    large, very_large = float(refs["large"]), float(refs["very_large"])
    vref = int(cfg.get("velocity_reference", {"day_count": 10})["day_count"])
    night = set(cfg.get("night_hours", [0, 1, 2, 3, 4, 5]))
    hires = set(c.upper() for c in cfg.get("high_risk_countries", []))
    vel = velocity or {}
    reasons: list[str] = []

    amt = float(canonical.get("amount", 0) or 0)
    if amt >= very_large:
        amount_risk, r = 1.0, f"amount {amt:,.0f} >= very_large {very_large:,.0f}"
    elif amt >= large:
        amount_risk, r = 0.7, f"amount {amt:,.0f} >= large {large:,.0f}"
    elif amt >= large / 2:
        amount_risk, r = 0.4, f"amount {amt:,.0f} >= half of large ref"
    elif amt >= large / 10:
        amount_risk, r = 0.2, f"amount {amt:,.0f} elevated"
    else:
        amount_risk, r = 0.05, f"amount {amt:,.0f} normal"
    reasons.append(r)

    day_count = int(vel.get("day_count", 0) or 0)
    velocity_risk = min(max(day_count, 0) / max(vref, 1), 1.0)
    reasons.append(f"velocity day_count={day_count} (ref {vref})")

    is_new = bool(canonical.get("is_new_beneficiary", False) or vel.get("is_new_beneficiary", False))
    beneficiary_risk = 1.0 if is_new else 0.0
    reasons.append(f"{'new' if is_new else 'known'} beneficiary")

    h = _hour(canonical.get("timestamp"))
    time_risk = 1.0 if (h is not None and h in night) else 0.0
    reasons.append(f"hour={h} {'night' if time_risk else 'daytime'}")

    country = str(canonical.get("country", "IN") or "IN").upper()
    country_risk = 1.0 if country in hires else 0.0
    reasons.append(f"country={country}{' high-risk' if country_risk else ''}")

    tms = 1.0 if bool(canonical.get("tms_alert", False)) else 0.0
    if tms:
        reasons.append("TMS watchlist alert")

    total = (w["amount_risk"] * amount_risk + w["velocity_risk"] * velocity_risk
             + w["beneficiary_risk"] * beneficiary_risk + w["time_risk"] * time_risk
             + w["country_risk"] * country_risk + w["tms_alert"] * tms)
    return round(min(max(total, 0.0), 1.0), 4), reasons


def decision(score_value: float) -> str:
    bands = load_config()["triage_bands"]
    if score_value < float(bands["LOG_ONLY"]):
        return "LOG_ONLY"
    if score_value < float(bands["MONITOR"]):
        return "MONITOR"
    return "FULL_INVESTIGATION"
