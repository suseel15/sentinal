import logging

log = logging.getLogger(__name__)


def _f(r, k, d=0.0):
    try:
        v = r.get(k, d)
        return float(v) if v is not None else float(d)
    except Exception:
        return float(d)


def _i(r, k, d=0):
    try:
        return int(float(r.get(k, d) or 0))
    except Exception:
        return int(d)


def _conf(n):
    return "high" if n >= 2 else ("medium" if n == 1 else "low")


def identify_typology(row: dict, names_only: bool = False) -> list:
    try:
        r = row or {}
        sw = _i(r, "structuring_window_flag") or _i(r, "structuring_flag")
        s_band = _i(r, "structuring_flag")
        fan_in = _i(r, "fan_in_flag")
        fan_out = _i(r, "fan_out_flag")
        hv = _i(r, "high_value_flag")
        gather = _i(r, "gather_scatter_flag")
        mule = _i(r, "mule_passthrough_flag")
        rapid = _i(r, "rapid_movement_flag")
        cyc = _i(r, "cycle_flag") or _i(r, "in_cycle") or _i(r, "has_cycle")
        shell = _i(r, "shell_invoice_flag")
        trade = _i(r, "trade_ml_flag")
        crypto = _i(r, "crypto_offramp_flag") or _i(r, "crypto_flag")
        tx7 = _f(r, "txns_last_7d")
        tx1 = _f(r, "txns_last_day")
        ratio = _f(r, "amount_ratio")
        pt = _f(r, "passthrough_ratio")
        fi7 = _f(r, "fan_in_7d")
        fo7 = _f(r, "fan_out_7d")
        hv7 = _i(r, "high_velocity_7d_flag") or _i(r, "high_velocity_flag")
        burst = _i(r, "burst_flag")
        nb = _i(r, "new_beneficiary_risk") or _i(r, "new_beneficiary")
        out = []

        if sw or s_band:
            n = sum([bool(sw), bool(s_band), bool(burst), bool(hv7 or tx7 >= 3)])
            out.append({"name": "STRUCTURING", "confidence": _conf(n), "evidence": f"structuring band txn (window={sw}, single={s_band}), 7d txns={tx7:g}"})
        if fan_in:
            n = sum([bool(fi7 >= 5), bool(gather), bool(hv7), bool(nb)])
            out.append({"name": "SMURFING_FAN_IN", "confidence": _conf(n), "evidence": f"fan-in from {fi7:g} distinct senders in 7d"})
        if (fan_in and hv) or gather:
            n = sum([bool(fan_in), bool(hv), bool(gather), bool(fan_out)])
            out.append({"name": "SMURFING_CONSOLIDATION", "confidence": _conf(n), "evidence": f"gather/consolidation fan_in={fan_in} high_value={hv} gather={gather}"})
        if mule or rapid:
            n = sum([bool(mule), bool(rapid), bool(pt >= 0.8), bool(tx1 >= 2)])
            out.append({"name": "MULE_PASSTHROUGH", "confidence": _conf(n), "evidence": f"rapid pass-through pt_ratio={pt:.2f} rapid={rapid} mule={mule}"})
        if (tx7 >= 10 and ratio > 3) or (fan_out and tx7 >= 10) or (cyc and tx7 >= 5):
            n = sum([bool(tx7 >= 10), bool(ratio > 3), bool(fan_out), bool(cyc), bool(gather)])
            out.append({"name": "LAYERING", "confidence": _conf(n), "evidence": f"high velocity layering {tx7:g} txns/7d ratio={ratio:.1f}x"})
        if cyc:
            n = sum([bool(cyc), bool(tx7 >= 5), bool(fan_out or gather)])
            out.append({"name": "ROUND_TRIPPING", "confidence": _conf(n), "evidence": "2-hop funds return to origin account"})
        if shell:
            n = sum([bool(shell), bool(nb), bool(hv)])
            out.append({"name": "SHELL_COMPANY_INVOICING", "confidence": _conf(n), "evidence": "shell keyword + invoice/service with new party"})
        if trade:
            n = sum([bool(trade), bool(nb), bool(hv)])
            out.append({"name": "TRADE_BASED_ML", "confidence": _conf(n), "evidence": "trade/invoice anomaly with round amount or new party"})
        if crypto:
            n = sum([bool(crypto), bool(hv), bool(rapid or mule)])
            out.append({"name": "CRYPTO_OFFRAMP", "confidence": _conf(n), "evidence": "crypto exchange keyword in counterparty"})
        if names_only:
            return [x["name"] for x in out]
        return out
    except Exception:
        log.exception("identify_typology failed")
        raise


def identify_typology_names(row: dict) -> list:
    return identify_typology(row, names_only=True)
