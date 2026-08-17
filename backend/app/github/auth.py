"""
GitHub App JWT + installation token management.
"""
import time
from datetime import datetime, timedelta, timezone

import jwt
import httpx
import structlog

from app.core.config import settings

log = structlog.get_logger(__name__)

_token_cache: dict[int, tuple[str, datetime]] = {}


def _load_private_key() -> str:
    path = settings.resolve_private_key_path()
    if path.exists():
        return path.read_text(encoding="utf-8")
    # Allow raw PEM in env for cloud deployments
    return settings.GITHUB_APP_PRIVATE_KEY_PATH.replace("\\n", "\n")


def create_jwt() -> str:
    """Create a short-lived JWT for GitHub App authentication."""
    now = int(time.time())
    payload = {
        "iat": now - 60,   # issued 60s ago to account for clock skew
        "exp": now + 540,  # 9-minute expiry (max 10)
        "iss": settings.GITHUB_APP_ID,
    }
    private_key = _load_private_key()
    return jwt.encode(payload, private_key, algorithm="RS256")


async def get_installation_token(installation_id: int) -> str:
    """Fetch or return cached installation access token."""
    cached = _token_cache.get(installation_id)
    if cached:
        token, expires_at = cached
        if datetime.now(timezone.utc) < expires_at - timedelta(minutes=5):
            return token

    app_jwt = create_jwt()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    token = data["token"]
    expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
    _token_cache[installation_id] = (token, expires_at)
    log.info("installation_token_refreshed", installation_id=installation_id)
    return token
