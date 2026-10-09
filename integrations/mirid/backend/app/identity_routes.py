"""Local-only Mirid Identity research API. Images live only in bounded RAM."""
from __future__ import annotations

import base64
import binascii
from dataclasses import asdict
import hashlib
import ipaddress
from pathlib import Path
import secrets
import threading

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .runtime_paths import runtime_config_root

MAX_IMAGE_BYTES = 8_000_000
MAX_BODY_BYTES = 23_000_000
SESSION_SECONDS = 300
MAX_SESSIONS = 4
PROTOCOL = "mirid-identity-v1"


def _response(value, status=200):
    return JSONResponse(value, status_code=status, headers={"Cache-Control": "no-store"})


def _local(request):
    try:
        address = ipaddress.ip_address(request.client.host)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        if not address.is_loopback:
            raise ValueError()
    except (AttributeError, ValueError):
        raise HTTPException(403, "Identity comparison is available only on this computer.") from None


async def _body(request):
    _local(request)
    if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
        raise HTTPException(415, "JSON is required.")
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_BODY_BYTES:
            raise HTTPException(413, "Choose smaller image files.")
        content.extend(chunk)
    try:
        from mirid_identity.crypto import strict_json
        value = strict_json(content)
        if not isinstance(value, dict):
            raise ValueError()
    except ImportError:
        raise HTTPException(503, "The local identity module is not installed.") from None
    except (ValueError, TypeError, RecursionError):
        raise HTTPException(400, "Invalid request.") from None
    if set(value) - {"reference_image", "probe_image", "consent", "subject", "session_id", "assertions"}:
        raise HTTPException(400, "Unknown request field.")
    return value


def _image(value):
    if not isinstance(value, str) or len(value) > 11_000_000:
        raise HTTPException(400, "Choose a JPEG, PNG or WebP image under 8 MB.")
    prefix, separator, encoded = value.partition(",")
    if not separator or prefix not in {"data:image/jpeg;base64", "data:image/png;base64", "data:image/webp;base64"}:
        raise HTTPException(400, "Choose a JPEG, PNG or WebP image.")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(400, "The image could not be decoded.") from None
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Choose an image under 8 MB.")
    return data


def _images(data):
    if data.get("consent") is not True:
        raise HTTPException(400, "Confirm permission to compare these images.")
    return _image(data.get("reference_image")), _image(data.get("probe_image"))


def evidence_digest(reference, probe):
    """A domain-separated digest of ordered input bytes, not of a face template."""
    return hashlib.sha256(b"mirid-identity-images-v1\x00" + hashlib.sha256(reference).digest()
                          + hashlib.sha256(probe).digest()).hexdigest()


def create_identity_router(config_root=None, *, comparator=None, status_provider=None):
    router = APIRouter(prefix="/identity", tags=["identity"])
    root = Path(config_root) if config_root is not None else runtime_config_root() / "identity"
    pending = {}
    pending_lock = threading.RLock()
    comparison_lock = threading.BoundedSemaphore(1)
    stores = {}

    def core():
        try:
            from mirid_identity import crypto, policy, face, models
        except ImportError:
            raise HTTPException(503, "The local identity module is not installed.") from None
        if not stores:
            with pending_lock:
                if not stores:
                    stores.update(sessions=crypto.SessionStore(":memory:"), nonces=crypto.NonceStore(":memory:"))
        return crypto, policy, face, models

    def configuration():
        crypto, policy, _, _ = core()
        try:
            trust = crypto.load_trust_config(root / "trust.json") if (root / "trust.json").exists() else crypto.TrustConfig(PROTOCOL, {})
            decision_policy = policy.load_policy_config(root / "policy.json") if (root / "policy.json").exists() else policy.DecisionPolicy()
            return trust, decision_policy
        except (OSError, ValueError):
            raise HTTPException(503, "The local identity trust or calibration configuration needs attention.") from None

    def discard(session_id):
        with pending_lock:
            item = pending.pop(session_id, None)
            if item:
                item["timer"].cancel()
                item.pop("reference", None)
                item.pop("probe", None)

    def compare(reference, probe, evidence=(), decision_policy=None):
        _, policy, face, _ = core()
        if decision_policy is None:
            _, decision_policy = configuration()
        if not comparison_lock.acquire(blocking=False):
            raise HTTPException(429, "A comparison is already running. Try again when it finishes.")
        try:
            result = (comparator or face.compare_images)(reference, probe)
            decision = policy.evaluate_identity(
                result.get("cosine_similarity"), evidence, decision_policy,
                model_id=result.get("model_id", "opencv-sface-2021dec"),
                model_sha256=result.get("model_sha256", ""),
                quality_passed=result.get("quality_passed", False),
            )
            return {"protocol": PROTOCOL, "research_mode": True, "face": result,
                    "decision": asdict(decision), "evidence_verified": len(evidence)}
        except HTTPException:
            raise
        except (ValueError, RuntimeError):
            raise HTTPException(422, "The images could not be compared. Check the images and installed models.") from None
        finally:
            comparison_lock.release()

    @router.get("/status")
    async def status(request: Request):
        _local(request)
        _, _, _, models = core()
        trust, decision_policy = configuration()
        state = await run_in_threadpool(status_provider or models.model_status)
        return _response({"available": True, "models_ready": state["ready"], "models": state["models"],
                          "research_mode": True, "trust_configured": bool(trust.issuers),
                          "calibration_configured": bool(decision_policy.face_calibration),
                          "engine": "OpenCV YuNet + SFace", "protocol": PROTOCOL,
                          "limits": {"max_image_bytes": MAX_IMAGE_BYTES, "max_pixels": 16_000_000},
                          "source_url": "https://github.com/mirid-ai/mirid-identity"})

    @router.post("/compare")
    async def compare_request(request: Request):
        reference, probe = _images(await _body(request))
        result = await run_in_threadpool(compare, reference, probe)
        return _response(result)

    @router.post("/challenge")
    async def challenge(request: Request):
        data = await _body(request)
        reference, probe = _images(data)
        subject = data.get("subject")
        if not isinstance(subject, str) or not 1 <= len(subject.strip()) <= 256 or any(ord(c) < 32 for c in subject):
            raise HTTPException(400, "Enter the subject identifier recognised by your evidence issuer.")
        trust, _ = configuration()
        digest = evidence_digest(reference, probe)
        with pending_lock:
            if len(pending) >= MAX_SESSIONS:
                raise HTTPException(429, "Too many pending comparisons. Clear a challenge or wait five minutes.")
            session = stores["sessions"].create(subject.strip(), digest, audience=trust.audience, ttl_seconds=SESSION_SECONDS)
            session_id = secrets.token_urlsafe(32)
            timer = threading.Timer(SESSION_SECONDS, discard, args=(session_id,))
            timer.daemon = True
            pending[session_id] = {"session": session, "reference": reference, "probe": probe, "timer": timer}
            timer.start()
        return _response({**asdict(session), "session_id": session_id, "protocol": PROTOCOL,
                          "research_mode": True, "image_retention_seconds": SESSION_SECONDS})

    @router.delete("/session")
    async def clear_session(request: Request):
        data = await _body(request)
        session_id = data.get("session_id")
        if not isinstance(session_id, str) or len(session_id) > 256:
            raise HTTPException(400, "Invalid session.")
        discard(session_id)
        return _response({"cleared": True})

    @router.post("/verify")
    async def verify(request: Request):
        data = await _body(request)
        session_id, assertions = data.get("session_id"), data.get("assertions")
        if not isinstance(session_id, str) or len(session_id) > 256 or not isinstance(assertions, list) or not 1 <= len(assertions) <= 8:
            raise HTTPException(400, "Provide a session and one to eight signed assertions.")
        if any(not isinstance(token, str) or len(token) > 8192 for token in assertions):
            raise HTTPException(400, "Invalid signed assertion.")
        crypto, _, _, _ = core()
        with pending_lock:
            item = pending.pop(session_id, None)
        if not item:
            raise HTTPException(409, "This challenge has expired or was already used. Prepare a new one.")
        item["timer"].cancel()
        try:
            session = stores["sessions"].consume(item["session"].challenge)
            trust, decision_policy = configuration()
            if trust.audience != session.audience:
                raise crypto.EvidenceError("trust_configuration_changed")
            verifier = crypto.AssertionVerifier(trust.issuers, stores["nonces"], trust.audience)
            proofs = [verifier.verify(token, subject=session.subject, challenge=session.challenge,
                                      evidence_digest=session.evidence_digest) for token in assertions]
            result = await run_in_threadpool(compare, item["reference"], item["probe"], proofs, decision_policy)
            return _response(result)
        except crypto.EvidenceError as error:
            return _response({"protocol": PROTOCOL, "research_mode": True,
                              "decision": {"status": "review_required", "reasons": [str(error)]},
                              "evidence_verified": 0}, 400)
        finally:
            item.clear()

    return router


identity_router = create_identity_router()
