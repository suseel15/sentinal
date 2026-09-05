"""A1 raw validation. Never silently fix; return (ok, errors)."""
import logging
from datetime import datetime

log = logging.getLogger(__name__)

AMOUNT_KEYS = ("amount", "transaction_amount", "amt")
TS_KEYS = ("timestamp", "date", "transaction_date", "txn_date")
SRC_KEYS = ("sender", "from_account", "src_acc", "source_account", "from", "account_id")
DST_KEYS = ("receiver", "to_account", "dest_acc", "destination_account", "to", "counterparty_name")
TYPE_KEYS = ("transaction_type", "type", "txn_type")


def _first(d: dict, keys: tuple) -> tuple[str | None, object]:
    for k in keys:
        if k in d and d[k] is not None and d[k] != "":
            return k, d[k]
    # return present-but-empty key for better errors, else (None, None)
    for k in keys:
        if k in d:
            return k, d[k]
    return None, None


def _parse_ts(v: object) -> bool:
    if isinstance(v, datetime):
        return True
    if not isinstance(v, str) or not v.strip():
        return False
    s = v.strip().replace("Z", "+00:00")
    try:
        datetime.fromisoformat(s)
        return True
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y",
                "%Y/%m/%d", "%m/%d/%Y", "%d-%m-%Y %H:%M:%S"):
        try:
            datetime.strptime(v.strip(), fmt)
            return True
        except ValueError:
            continue
    return False


def validate_raw(d: dict) -> tuple[bool, list[str]]:
    """Check raw dict across all known source aliases. Returns (ok, errors)."""
    errors: list[str] = []
    if not isinstance(d, dict) or not d:
        return False, ["empty payload: expected non-empty dict"]

    # amount present & > 0
    ak, av = _first(d, AMOUNT_KEYS)
    if ak is None:
        errors.append(f"missing amount: expected one of {list(AMOUNT_KEYS)}")
    else:
        try:
            if float(av) <= 0:  # type: ignore[arg-type]
                errors.append(f"invalid amount in '{ak}': must be > 0, got {av!r}")
        except (TypeError, ValueError):
            errors.append(f"invalid amount in '{ak}': not numeric, got {av!r}")

    # timestamp parseable
    tk, tv = _first(d, TS_KEYS)
    if tk is None:
        errors.append(f"missing timestamp: expected one of {list(TS_KEYS)}")
    elif not _parse_ts(tv):
        errors.append(f"invalid timestamp in '{tk}': unparseable, got {tv!r}")

    # transaction_type known (any non-empty string passes; missing is an error)
    found_type = False
    for k in TYPE_KEYS:
        if k in d and isinstance(d[k], str) and d[k].strip():
            found_type = True
            break
        if k in d and not (isinstance(d[k], str) and d[k].strip()):
            errors.append(f"invalid transaction_type in '{k}': must be non-empty string")
            found_type = True  # counted as present-but-bad, don't double-report missing
            break
    if not found_type and not any(k in d for k in TYPE_KEYS):
        errors.append(f"missing transaction_type: expected one of {list(TYPE_KEYS)}")

    # accounts present
    sk, sv = _first(d, SRC_KEYS)
    if sk is None:
        errors.append(f"missing source account: expected one of {list(SRC_KEYS)}")
    elif not str(sv).strip():
        errors.append(f"invalid source account in '{sk}': empty")
    dk, dv = _first(d, DST_KEYS)
    if dk is None:
        errors.append(f"missing destination account: expected one of {list(DST_KEYS)}")
    elif not str(dv).strip():
        errors.append(f"invalid destination account in '{dk}': empty")

    ok = not errors
    if not ok:
        log.warning("validate_raw failed: %s", errors)
    return ok, errors
