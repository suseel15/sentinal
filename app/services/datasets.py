"""Root CSV registry: NEW transactions/accounts/customers/identity_device with fallback."""
from __future__ import annotations

import csv
import logging
from pathlib import Path

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

CSVS: dict[str, Path] = {
    "transactions": REPO_ROOT / "transactions.csv",
    "labeled": REPO_ROOT / "labeled_transactions.csv",
    "accounts": REPO_ROOT / "accounts.csv",
    "customers": REPO_ROOT / "customers.csv",
    "identity": REPO_ROOT / "identity_device.csv",
    "profiles_legacy": REPO_ROOT / "account_profiles.csv",
}

_TXN_ID_COL = "transaction_id"

_ID_COLS = {
    "device": ("device_id",),
    "phone": ("phone_hash", "phone"),
    "ip": ("ip_address", "ip"),
    "email": ("email_hash", "email"),
}
_KIND_TO_COL = {
    "device": "device", "devices": "device", "device_id": "device",
    "phone": "phone", "phones": "phone", "phone_hash": "phone",
    "ip": "ip", "ips": "ip", "ip_address": "ip",
    "email": "email", "emails": "email", "email_hash": "email",
}


def preferred_txn_csv() -> Path:
    p = CSVS["transactions"]
    return p if p.exists() else CSVS["labeled"]


def _scan_first(path: Path, match_col: str, match_val: str) -> dict | None:
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            rdr = csv.DictReader(f)
            if not rdr.fieldnames or match_col not in rdr.fieldnames:
                return None
            for row in rdr:
                try:
                    if str(row.get(match_col, "")).strip() == str(match_val):
                        return dict(row)
                except Exception:
                    continue
    except FileNotFoundError:
        return None
    except Exception:
        log.exception("csv scan failed: %s", path)
    return None


def load_txn_row(txn_id: str) -> dict | None:
    pref = preferred_txn_csv()
    row = _scan_first(pref, _TXN_ID_COL, str(txn_id)) if pref.exists() else None
    if row:
        return row
    fb = CSVS["labeled"]
    if fb != pref and fb.exists():
        return _scan_first(fb, _TXN_ID_COL, str(txn_id))
    return None


def _find_row(path: Path, col: str, val: str) -> dict | None:
    if not path.exists():
        return None
    return _scan_first(path, col, val)


def load_account_profile(account_id: str) -> dict | None:
    acct_path, cust_path = CSVS["accounts"], CSVS["customers"]
    if not acct_path.exists():
        return None
    acct = _find_row(acct_path, "account_id", str(account_id))
    if not acct:
        return None
    out: dict = {"account_id": str(account_id), "account": dict(acct)}
    for k, v in acct.items():
        out.setdefault(k, v)
    cust_id = acct.get("customer_id")
    if cust_path.exists() and cust_id:
        try:
            cust = _find_row(cust_path, "customer_id", str(cust_id))
        except Exception:
            cust = None
        if cust:
            out["customer"] = dict(cust)
            for k, v in cust.items():
                out.setdefault(k, v)
    else:
        out.setdefault("customer", None)
    return out


def _col_present(fieldnames, candidates):
    if not fieldnames:
        return None
    for c in candidates:
        if c in fieldnames:
            return c
    return None


_CACHE: dict = {}


def _identity_rows() -> list:
    rows = _CACHE.get("identity_rows")
    if rows is not None:
        return rows
    rows = []
    p = CSVS["identity"]
    try:
        if p.exists():
            with open(p, newline="", encoding="utf-8-sig") as f:
                rdr = csv.DictReader(f)
                cols = rdr.fieldnames or []
                c_acc = "account_id" if "account_id" in cols else None
                cmap = {slot: _col_present(cols, cands) for slot, cands in _ID_COLS.items()}
                if c_acc:
                    for row in rdr:
                        try:
                            rows.append({"account_id": str(row.get("account_id", "")).strip(),
                                         "device": str(row.get(cmap["device"], "") or "").strip() if cmap["device"] else "",
                                         "phone": str(row.get(cmap["phone"], "") or "").strip() if cmap["phone"] else "",
                                         "ip": str(row.get(cmap["ip"], "") or "").strip() if cmap["ip"] else "",
                                         "email": str(row.get(cmap["email"], "") or "").strip() if cmap["email"] else ""})
                        except Exception:
                            continue
    except FileNotFoundError:
        pass
    except Exception:
        log.exception("identity cache load failed")
    _CACHE["identity_rows"] = rows
    return rows


def identity_links(account_id: str) -> dict:
    empty = {"devices": [], "phones": [], "ips": [], "emails": []}
    try:
        devs, phones, ips, emails = set(), set(), set(), set()
        for row in _identity_rows():
            if row["account_id"] != str(account_id):
                continue
            if row["device"]:
                devs.add(row["device"])
            if row["phone"]:
                phones.add(row["phone"])
            if row["ip"]:
                ips.add(row["ip"])
            if row["email"]:
                emails.add(row["email"])
    except Exception:
        log.exception("identity_links failed")
        return empty
    return {"devices": sorted(devs), "phones": sorted(phones),
            "ips": sorted(ips), "emails": sorted(emails)}


def accounts_sharing(kind: str, value: str, exclude: str | None = None) -> list:
    if value is None or str(value) == "":
        return []
    slot = _KIND_TO_COL.get(str(kind or "").strip().lower())
    if not slot:
        return []
    found: set[str] = set()
    try:
        for row in _identity_rows():
            try:
                if str(row.get(slot, "")).strip() != str(value):
                    continue
                acc = str(row.get("account_id", "")).strip()
                if not acc or (exclude is not None and acc == str(exclude)):
                    continue
                found.add(acc)
            except Exception:
                continue
    except Exception:
        log.exception("accounts_sharing failed")
    return sorted(found)
