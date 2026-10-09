"""Server-side verification of narrowly scoped, one-use identity assertions.

This is a protocol for evidence issued by an administrator-pinned Ed25519 key.
A signature proves which configured issuer made an assertion, not whether its
enrolment process was sound. Factor meaning and recovery dependencies come from
the server trust file; a browser cannot upgrade them by adding token claims.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import threading
import time
from types import MappingProxyType
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


DOMAIN = b"mirid-identity-assertion-v1\x00"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_B64 = re.compile(r"[A-Za-z0-9_-]+\Z")
_FIELDS = frozenset({"v", "iss", "sub", "aud", "challenge", "nonce", "iat", "exp", "factor", "evidence_digest"})


class EvidenceError(ValueError):
    """A proof, binding, or replay check failed. Safe to show the short code."""


def _string(value: Any, name: str, *, minimum: int = 1, maximum: int = 256) -> str:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise EvidenceError(f"invalid_{name}")
    if any(ord(c) < 32 for c in value):
        raise EvidenceError(f"invalid_{name}")
    return value


def _integer(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        raise EvidenceError(f"invalid_{name}")
    return value


def _factor_name(value: Any) -> str:
    value = _string(value, "factor")
    # Human-readable issuer/factor identifiers are unambiguous when only the
    # issuer may contain a slash (for example a provider URL or key version).
    if "/" in value:
        raise EvidenceError("invalid_factor")
    return value


def _now(value: float | None) -> float:
    value = time.time() if value is None else value
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise EvidenceError("invalid_time")
    return value


def _digest(value: Any) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise EvidenceError("invalid_evidence_digest")
    return value


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    if not isinstance(value, str) or not _B64.fullmatch(value):
        raise EvidenceError("invalid_encoding")
    try:
        decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, TypeError) as exc:
        raise EvidenceError("invalid_encoding") from exc
    if b64url(decoded) != value:
        raise EvidenceError("noncanonical_encoding")
    return decoded


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError("duplicate_json_key")
        result[key] = value
    return result


def strict_json(data: str | bytes) -> Any:
    def reject_constant(_: str) -> None:
        raise EvidenceError("nonfinite_json")

    try:
        return json.loads(data, object_pairs_hook=_unique_object, parse_constant=reject_constant)
    except EvidenceError:
        raise
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        raise EvidenceError("invalid_json") from exc


def read_admin_json(path: str | Path) -> Any:
    """Read an owner-controlled startup file, never a path from an HTTP request."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise EvidenceError("config_not_owned_regular_file")
        if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise EvidenceError("config_writable_by_other_users")
        data = stream.read(1_000_001)
        if len(data) > 1_000_000:
            raise EvidenceError("config_too_large")
    return strict_json(data)


@dataclass(frozen=True)
class FactorTrust:
    independence_group: str
    identity_bound: bool = False

    def __post_init__(self) -> None:
        _string(self.independence_group, "independence_group")
        if self.independence_group == "face" or type(self.identity_bound) is not bool:
            raise EvidenceError("invalid_factor_trust")


@dataclass(frozen=True)
class TrustedIssuer:
    public_key: Ed25519PublicKey
    factors: Mapping[str, FactorTrust]
    max_lifetime_seconds: int = 300

    def __post_init__(self) -> None:
        if not isinstance(self.public_key, Ed25519PublicKey):
            raise EvidenceError("invalid_public_key")
        if not self.factors or not 1 <= _integer(self.max_lifetime_seconds, "max_lifetime") <= 3600:
            raise EvidenceError("invalid_issuer")
        for name, factor in self.factors.items():
            _factor_name(name)
            if not isinstance(factor, FactorTrust):
                raise EvidenceError("invalid_factor_trust")
        object.__setattr__(self, "factors", MappingProxyType(dict(self.factors)))


@dataclass(frozen=True)
class TrustConfig:
    audience: str
    issuers: Mapping[str, TrustedIssuer]


def load_trust_config(path: str | Path) -> TrustConfig:
    data = read_admin_json(path)
    if not isinstance(data, dict) or set(data) != {"version", "audience", "issuers"} or type(data["version"]) is not int or data["version"] != 1:
        raise EvidenceError("invalid_trust_config")
    audience = _string(data["audience"], "audience")
    if not isinstance(data["issuers"], dict):
        raise EvidenceError("invalid_issuers")
    issuers = {}
    for issuer, entry in data["issuers"].items():
        _string(issuer, "issuer")
        if not isinstance(entry, dict) or set(entry) != {"public_key", "max_lifetime_seconds", "factors"}:
            raise EvidenceError("invalid_issuer_config")
        if not isinstance(entry["factors"], dict):
            raise EvidenceError("invalid_factors_config")
        factors = {}
        for name, factor in entry["factors"].items():
            if not isinstance(factor, dict) or set(factor) != {"independence_group", "identity_bound"}:
                raise EvidenceError("invalid_factor_config")
            factors[name] = FactorTrust(**factor)
        try:
            public_key = Ed25519PublicKey.from_public_bytes(_decode(entry["public_key"]))
        except ValueError as exc:
            raise EvidenceError("invalid_public_key") from exc
        issuers[issuer] = TrustedIssuer(public_key, factors, entry["max_lifetime_seconds"])
    return TrustConfig(audience, MappingProxyType(issuers))


@dataclass(frozen=True)
class VerifiedEvidence:
    issuer: str
    factor: str
    subject: str
    audience: str
    challenge: str
    evidence_digest: str
    independence_group: str
    identity_bound: bool
    issued_at: int
    expires_at: int
    assertion_id: str


class _Database:
    def __init__(self, path: str | Path = ":memory:") -> None:
        if str(path) != ":memory:":
            # Replay state contains subject identifiers; owner-only even with a
            # permissive process umask. Biometrics are never stored here.
            fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
            try:
                metadata = os.fstat(fd)
                if metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
                    raise EvidenceError("insecure_replay_database_permissions")
            finally:
                os.close(fd)
        self._connection = sqlite3.connect(str(path), check_same_thread=False, timeout=10)
        self._lock = threading.RLock()

    def close(self) -> None:
        with self._lock:
            self._connection.close()


class NonceStore(_Database):
    def __init__(self, path: str | Path = ":memory:") -> None:
        super().__init__(path)
        self._connection.execute("CREATE TABLE IF NOT EXISTS used_nonce (issuer TEXT NOT NULL, nonce TEXT NOT NULL, expires INTEGER NOT NULL, PRIMARY KEY(issuer, nonce))")
        self._connection.commit()

    def consume(self, issuer: str, nonce: str, expires_at: int, *, now: float) -> None:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM used_nonce WHERE expires <= ?", (now,))
            try:
                self._connection.execute("INSERT INTO used_nonce VALUES (?, ?, ?)", (issuer, nonce, expires_at))
            except sqlite3.IntegrityError as exc:
                raise EvidenceError("replayed_assertion") from exc


@dataclass(frozen=True)
class VerificationSession:
    challenge: str
    subject: str
    audience: str
    evidence_digest: str
    created_at: int
    expires_at: int


class SessionStore(_Database):
    def __init__(self, path: str | Path = ":memory:") -> None:
        super().__init__(path)
        self._connection.execute("CREATE TABLE IF NOT EXISTS identity_session (challenge TEXT PRIMARY KEY, subject TEXT NOT NULL, audience TEXT NOT NULL, digest TEXT NOT NULL, created INTEGER NOT NULL, expires INTEGER NOT NULL, consumed INTEGER NOT NULL DEFAULT 0)")
        self._connection.commit()

    def create(self, subject: str, evidence_digest: str, *, audience: str, ttl_seconds: int = 300, now: float | None = None) -> VerificationSession:
        current = int(_now(now))
        _string(subject, "subject")
        _string(audience, "audience")
        _digest(evidence_digest)
        if not 1 <= _integer(ttl_seconds, "ttl") <= 3600:
            raise EvidenceError("invalid_ttl")
        session = VerificationSession(secrets.token_urlsafe(32), subject, audience, evidence_digest, current, current + ttl_seconds)
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM identity_session WHERE expires <= ?", (current,))
            self._connection.execute("INSERT INTO identity_session(challenge,subject,audience,digest,created,expires) VALUES (?,?,?,?,?,?)", (session.challenge, subject, audience, evidence_digest, current, session.expires_at))
        return session

    def consume(self, challenge: str, *, now: float | None = None) -> VerificationSession:
        current = _now(now)
        _string(challenge, "challenge", minimum=32)
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                row = self._connection.execute("SELECT challenge,subject,audience,digest,created,expires,consumed FROM identity_session WHERE challenge=?", (challenge,)).fetchone()
                if row is None:
                    raise EvidenceError("unknown_session")
                if row[6]:
                    raise EvidenceError("replayed_session")
                # Burn even an expired or later-failed session; retries require
                # a newly issued challenge and new signed assertions.
                self._connection.execute("UPDATE identity_session SET consumed=1 WHERE challenge=?", (challenge,))
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
        if row[5] <= current or row[4] > current:
            raise EvidenceError("expired_session")
        return VerificationSession(*row[:6])


class AssertionVerifier:
    def __init__(self, trusted_issuers: Mapping[str, TrustedIssuer], nonce_store: NonceStore, audience: str) -> None:
        self.issuers = MappingProxyType(dict(trusted_issuers))
        self.nonces = nonce_store
        self.audience = _string(audience, "audience")

    def verify(self, token: str, *, subject: str, challenge: str, evidence_digest: str, now: float | None = None) -> VerifiedEvidence:
        current = _now(now)
        _string(subject, "subject")
        _string(challenge, "challenge", minimum=32)
        _digest(evidence_digest)
        if not isinstance(token, str) or not 1 <= len(token) <= 8192 or token.count(".") != 1:
            raise EvidenceError("invalid_token")
        payload64, signature64 = token.split(".")
        payload, signature = _decode(payload64), _decode(signature64)
        claims = strict_json(payload)
        if not isinstance(claims, dict) or set(claims) != _FIELDS or type(claims["v"]) is not int or claims["v"] != 1:
            raise EvidenceError("invalid_claims")
        issuer_name = _string(claims["iss"], "issuer")
        issuer = self.issuers.get(issuer_name)
        if issuer is None:
            raise EvidenceError("unknown_issuer")
        try:
            issuer.public_key.verify(signature, DOMAIN + payload)
        except (InvalidSignature, ValueError) as exc:
            raise EvidenceError("invalid_signature") from exc
        factor_name = _factor_name(claims["factor"])
        factor = issuer.factors.get(factor_name)
        if factor is None:
            raise EvidenceError("untrusted_factor")
        if claims["sub"] != subject:
            raise EvidenceError("wrong_subject")
        if claims["aud"] != self.audience:
            raise EvidenceError("wrong_audience")
        if claims["challenge"] != challenge:
            raise EvidenceError("wrong_challenge")
        if claims["evidence_digest"] != evidence_digest:
            raise EvidenceError("wrong_evidence_digest")
        issued, expires = _integer(claims["iat"], "iat"), _integer(claims["exp"], "exp")
        if issued > current:
            raise EvidenceError("future_assertion")
        if expires <= current or issued >= expires:
            raise EvidenceError("expired_assertion")
        if expires - issued > issuer.max_lifetime_seconds or current - issued > issuer.max_lifetime_seconds:
            raise EvidenceError("assertion_lifetime_exceeded")
        nonce = _string(claims["nonce"], "nonce", minimum=22)
        self.nonces.consume(issuer_name, nonce, expires, now=current)
        return VerifiedEvidence(issuer_name, factor_name, subject, self.audience, challenge, evidence_digest, factor.independence_group, factor.identity_bound, issued, expires, hashlib.sha256(payload + signature).hexdigest())


def sign_assertion(private_key: Ed25519PrivateKey, *, issuer: str, subject: str, audience: str, challenge: str, evidence_digest: str, factor: str, issued_at: int, expires_at: int, nonce: str | None = None) -> str:
    """Issuer/test utility. Never expose a signing endpoint or ship private keys."""
    claims = {"v": 1, "iss": issuer, "sub": subject, "aud": audience, "challenge": challenge, "evidence_digest": evidence_digest, "factor": factor, "iat": issued_at, "exp": expires_at, "nonce": nonce or secrets.token_urlsafe(24)}
    payload = json.dumps(claims, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return b64url(payload) + "." + b64url(private_key.sign(DOMAIN + payload))
