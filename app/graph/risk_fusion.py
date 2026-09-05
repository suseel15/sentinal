"""A4 risk fusion: weighted graph score, never merged with A2."""
import logging

log = logging.getLogger(__name__)


def fuse(patterns: dict, config: dict | None = None) -> tuple[float, str]:
    try:
        cfg = config or {}
        weights = dict(cfg.get("RISK_WEIGHTS") or cfg.get("risk_weights") or {
            "mule_chain": 0.25, "fan_in": 0.15, "fan_out": 0.15,
            "circular_flow": 0.20, "rapid_layering": 0.15, "shared_identity": 0.10})
        bands = dict(cfg.get("RISK_BANDS") or {"LOW": 30, "MED": 60, "HIGH": 80})
        try:
            low = float(bands.get("LOW", 30))
            med = float(bands.get("MED", 60))
            high = float(bands.get("HIGH", 80))
        except Exception:
            low, med, high = 30.0, 60.0, 80.0
        avail = {}
        try:
            for k, w in weights.items():
                try:
                    p = (patterns or {}).get(k)
                    if not isinstance(p, dict):
                        continue
                    st = str(p.get("status", "AVAILABLE"))
                    if st == "UNAVAILABLE":
                        continue
                    s = float(p.get("score", 0) or 0)
                    s = max(0.0, min(1.0, s))
                    avail[k] = (float(w), s)
                except Exception:
                    continue
        except Exception:
            log.exception("avail collect failed")
        if not avail:
            return 0.0, "LOW"
        try:
            tot_w = sum(w for w, _ in avail.values()) or 1.0
            fused = sum((w / tot_w) * s for w, s in avail.values())
            score = float(max(0.0, min(100.0, fused * 100.0)))
        except Exception:
            log.exception("fuse math failed")
            score = 0.0
        try:
            if score < low:
                level = "LOW"
            elif score < med:
                level = "MEDIUM"
            elif score < high:
                level = "HIGH"
            else:
                level = "CRITICAL"
        except Exception:
            level = "LOW"
        return score, level
    except Exception:
        log.exception("fuse failed")
        return 0.0, "LOW"
