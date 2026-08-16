"""
Webhook signature verification and event routing.
"""
import hashlib
import hmac

from fastapi import Request, HTTPException
import structlog

from app.core.config import settings

log = structlog.get_logger(__name__)


async def verify_signature(request: Request) -> bytes:
    """Verify GitHub webhook HMAC-SHA256 signature."""
    body = await request.body()
    sig_header = request.headers.get("X-Hub-Signature-256", "")
    if not sig_header.startswith("sha256="):
        raise HTTPException(status_code=400, detail="Missing webhook signature")

    expected = hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(sig_header[7:], expected):
        log.warning("webhook_signature_mismatch")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    return body
