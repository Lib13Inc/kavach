"""Sensitive-data vault: detect card numbers, swap them for stand-in tokens,
and release the real value only to hosts the policy allows.

Hackathon version: in-memory. Production: KMS / HashiCorp Vault backed.
"""
from __future__ import annotations

import re
import secrets
import threading

# 13-19 digits, optionally separated by single spaces or dashes.
PAN_RE = re.compile(r"(?<![\w-])(?:\d[ -]?){12,18}\d(?![\w-])")
TOKEN_RE = re.compile(r"tok_\d{4}_[0-9a-f]{6}_\d{4}")


def luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = ord(ch) - 48
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def find_pans(text: str) -> list[str]:
    """Return the raw matches in `text` that are Luhn-valid card numbers."""
    out = []
    for m in PAN_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and luhn_ok(digits):
            out.append(m.group(0))
    return out


def contains_pan(text: str, known: set[str] | None = None) -> bool:
    """True if text holds any Luhn-valid PAN, or any of the `known` PANs
    even with separators removed."""
    if find_pans(text):
        return True
    if known:
        flat = re.sub(r"\D", "", text)
        return any(p in flat for p in known)
    return False


class Vault:
    def __init__(self) -> None:
        self._by_token: dict[str, str] = {}
        self._by_pan: dict[str, str] = {}
        self._lock = threading.Lock()

    def token_for(self, pan_digits: str) -> str:
        with self._lock:
            tok = self._by_pan.get(pan_digits)
            if tok is None:
                tok = f"tok_{pan_digits[:4]}_{secrets.token_hex(3)}_{pan_digits[-4:]}"
                self._by_pan[pan_digits] = tok
                self._by_token[tok] = pan_digits
            return tok

    def tokenize(self, text: str) -> tuple[str, int]:
        """Replace every PAN in text with its token. Returns (text, count)."""
        count = 0

        def sub(m: re.Match) -> str:
            nonlocal count
            digits = re.sub(r"\D", "", m.group(0))
            if 13 <= len(digits) <= 19 and luhn_ok(digits):
                count += 1
                return self.token_for(digits)
            return m.group(0)

        return PAN_RE.sub(sub, text), count

    def detokenize(self, text: str) -> tuple[str, int]:
        """Replace every known token with the real PAN. Call ONLY for hosts
        the policy releases cardholder data to."""
        count = 0

        def sub(m: re.Match) -> str:
            nonlocal count
            real = self._by_token.get(m.group(0))
            if real is None:
                return m.group(0)
            count += 1
            return real

        return TOKEN_RE.sub(sub, text), count

    def has_token(self, text: str) -> bool:
        return bool(TOKEN_RE.search(text))
