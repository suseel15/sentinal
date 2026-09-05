"""Deterministic transaction fingerprint (SHA-256).

Canonical fingerprint string format:
    "{src}|{dst}|{amount:.2f}|{timestamp_iso}|{ttype}"
where src/dst are stripped, amount is abs float with 2 decimals,
timestamp_iso is ISO-8601 string, ttype is uppercased transaction_type.
Hex digest of its UTF-8 bytes is the fingerprint.
"""
import hashlib


def canonical_string(src: str, dst: str, amount: float, timestamp_iso: str, ttype: str) -> str:
    return (f"{str(src).strip()}|{str(dst).strip()}|{abs(float(amount)):.2f}"
            f"|{str(timestamp_iso).strip()}|{str(ttype).strip().upper()}")


def fingerprint(src: str, dst: str, amount: float, timestamp_iso: str, ttype: str) -> str:
    return hashlib.sha256(canonical_string(src, dst, amount, timestamp_iso, ttype).encode("utf-8")).hexdigest()
