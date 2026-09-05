"""Normalize any of 3 source formats (plus canonical) to SENTINEL canonical dict."""
import logging
from datetime import datetime

log = logging.getLogger(__name__)

CANONICAL_KEYS = ("source_account", "destination_account", "amount", "currency",
                  "transaction_type", "timestamp", "country", "device_id", "tms_alert",
                  "ip_address", "location", "channel",
                  "sender_customer_id", "receiver_customer_id")

# raw_key -> canonical_key per source system
FIELD_MAPS: dict[str, dict[str, str]] = {
    # Format 1: sender/receiver/amount/date
    "core": {"sender": "source_account", "receiver": "destination_account",
             "amount": "amount", "date": "timestamp"},
    "legacy_csv": {"sender": "source_account", "receiver": "destination_account",
                   "amount": "amount", "date": "timestamp"},
    # Format 2: from_account/to_account/transaction_amount/timestamp
    "bank_api": {"from_account": "source_account", "to_account": "destination_account",
                 "transaction_amount": "amount", "timestamp": "timestamp"},
    "bank": {"from_account": "source_account", "to_account": "destination_account",
             "transaction_amount": "amount", "timestamp": "timestamp"},
    # Format 3: src_acc/dest_acc/amt (+ timestamp/date passthrough)
    "upi": {"src_acc": "source_account", "dest_acc": "destination_account",
            "amt": "amount"},
    "upi_gateway": {"src_acc": "source_account", "dest_acc": "destination_account",
                    "amt": "amount"},
    # Canonical / already-normalized input
    "canonical": {"source_account": "source_account",
                  "destination_account": "destination_account",
                  "amount": "amount", "timestamp": "timestamp"},
    # Format 4: NEW root transactions.csv
    "transactions": {"sender_account_id": "source_account",
                     "receiver_account_id": "destination_account",
                     "amount": "amount", "timestamp": "timestamp",
                     "transaction_type": "transaction_type",
                     "device_id": "device_id", "ip_address": "ip_address",
                     "channel": "channel", "location": "location"},
    "root_csv": {"sender_account_id": "source_account",
                 "receiver_account_id": "destination_account",
                 "amount": "amount", "timestamp": "timestamp",
                 "transaction_type": "transaction_type",
                 "device_id": "device_id", "ip_address": "ip_address",
                 "channel": "channel", "location": "location"},
    "new_csv": {"sender_account_id": "source_account",
                "receiver_account_id": "destination_account",
                "amount": "amount", "timestamp": "timestamp",
                "transaction_type": "transaction_type",
                "device_id": "device_id", "ip_address": "ip_address",
                "channel": "channel", "location": "location"},
}

# fallback alias lists (used regardless of source_system)
ALIASES: dict[str, tuple[str, ...]] = {
    "source_account": ("source_account", "sender", "from_account", "src_acc", "from", "account_id",
                       "sender_account_id"),
    "destination_account": ("destination_account", "receiver", "to_account", "dest_acc",
                            "to", "counterparty_name", "counterparty", "receiver_account_id"),
    "amount": ("amount", "transaction_amount", "amt", "value"),
    "currency": ("currency", "ccy"),
    "transaction_type": ("transaction_type", "type", "txn_type", "tx_type"),
    "timestamp": ("timestamp", "date", "transaction_date", "txn_date", "created_at"),
    "country": ("country", "country_code", "nation", "sender_country", "receiver_country"),
    "device_id": ("device_id", "device", "deviceId"),
    "ip_address": ("ip_address", "ip", "ipAddress"),
    "location": ("location", "city", "merchant_location"),
    "channel": ("channel",),
    "sender_customer_id": ("sender_customer_id", "sender_customer"),
    "receiver_customer_id": ("receiver_customer_id", "receiver_customer"),
    "tms_alert": ("tms_alert", "tmsAlert", "alert", "watchlist_hit"),
    "is_new_beneficiary": ("is_new_beneficiary", "new_beneficiary", "isNewBeneficiary"),
}


def parse_timestamp(v) -> datetime:
    if isinstance(v, datetime):
        return v
    if not isinstance(v, str):
        raise ValueError(f"unparseable timestamp: {v!r}")
    s = v.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y",
                "%Y/%m/%d", "%m/%d/%Y", "%d-%m-%Y %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(v.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"unparseable timestamp: {v!r}")


def _pick(raw: dict, canonical: str):
    for a in ALIASES[canonical]:
        if a in raw and raw[a] is not None and raw[a] != "":
            return raw[a]
    return None


def normalize(raw: dict, source_system: str) -> dict:
    """Map raw -> canonical. Raises ValueError on missing criticals."""
    if not isinstance(raw, dict) or not raw:
        raise ValueError("empty raw payload")
    _ = FIELD_MAPS.get(source_system or "", {})  # documented per-format maps; lookup is alias-based

    src = _pick(raw, "source_account")
    dst = _pick(raw, "destination_account")
    amt = _pick(raw, "amount")
    ts = _pick(raw, "timestamp")
    missing = [k for k, v in (("source_account", src), ("destination_account", dst),
                              ("amount", amt), ("timestamp", ts)) if v is None]
    if missing:
        raise ValueError(f"missing critical field(s): {missing} (source_system={source_system!r})")
    try:
        amount = abs(float(amt))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError(f"invalid amount: {amt!r}")
    if amount <= 0:
        raise ValueError(f"invalid amount: must be > 0, got {amt!r}")
    try:
        timestamp = parse_timestamp(ts)
    except ValueError as e:
        raise ValueError(str(e))

    ttype = _pick(raw, "transaction_type") or "TRANSFER"
    ttype = str(ttype).strip().upper() or "TRANSFER"
    out = {
        "source_account": str(src).strip(),
        "destination_account": str(dst).strip(),
        "amount": amount,
        "currency": str(_pick(raw, "currency") or "INR").strip().upper(),
        "transaction_type": ttype,
        "timestamp": timestamp,
        "country": str(_pick(raw, "country") or "IN").strip().upper(),
        "device_id": _pick(raw, "device_id"),
        "tms_alert": bool(_pick(raw, "tms_alert") or False),
        "source_system": source_system or "UNKNOWN",
    }
    nb = _pick(raw, "is_new_beneficiary")
    if nb is not None:
        out["is_new_beneficiary"] = bool(nb) if not isinstance(nb, bool) else nb
    ip = _pick(raw, "ip_address")
    if ip is not None:
        out["ip_address"] = str(ip).strip()
    loc = _pick(raw, "location")
    if loc is not None:
        out["location"] = str(loc).strip()
    ch = _pick(raw, "channel")
    if ch is not None:
        out["channel"] = str(ch).strip().upper()
    sc = _pick(raw, "sender_customer_id")
    if sc is not None:
        out["sender_customer_id"] = str(sc).strip()
    rc = _pick(raw, "receiver_customer_id")
    if rc is not None:
        out["receiver_customer_id"] = str(rc).strip()
    log.debug("normalized %s -> %s %.2f", source_system, out["source_account"], amount)
    return out
