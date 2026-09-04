import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import jwt
from jwt import PyJWK, PyJWKClient

from app.core.config import settings

logger = logging.getLogger(__name__)

JWKS_CACHE_TTL_SECONDS = 3600
JWKS_REFRESH_COOLDOWN_SECONDS = 300
CLOCK_LEEWAY_SECONDS = 60
EXPECTED_ALGORITHM = "RS256"
EXPECTED_TOKEN_USE = "access"


class TokenVerificationError(Exception):
    """A safe, non-leaking bearer-token authentication failure."""


class AuthServiceUnavailableError(Exception):
    """The identity provider could not be reached; distinct from a bad credential."""


@dataclass(frozen=True)
class VerifiedIdentity:
    subject: str
    email: str | None


class _JWKSCache:
    """Caches Cognito signing keys by ``kid``.

    A normal TTL covers routine key rotation. An unknown ``kid`` forces a refresh, but
    that forced refresh is separately rate-limited so that tokens carrying random/unknown
    ``kid`` values cannot be used to repeatedly hit the Cognito JWKS endpoint through us.
    """

    def __init__(
        self,
        jwks_url_provider: Callable[[], str | None],
        *,
        ttl_seconds: float = JWKS_CACHE_TTL_SECONDS,
        refresh_cooldown_seconds: float = JWKS_REFRESH_COOLDOWN_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._jwks_url_provider = jwks_url_provider
        self._ttl_seconds = ttl_seconds
        self._refresh_cooldown_seconds = refresh_cooldown_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._keys_by_kid: dict[str, PyJWK] = {}
        self._last_fetch_at: float | None = None
        self._last_forced_refresh_at: float | None = None

    def get_signing_key(self, kid: str) -> PyJWK:
        now = self._clock()
        with self._lock:
            if self._last_fetch_at is None or (now - self._last_fetch_at) > self._ttl_seconds:
                self._refresh(now)

            key = self._keys_by_kid.get(kid)
            if key is not None:
                return key

            can_force_refresh = (
                self._last_forced_refresh_at is None
                or (now - self._last_forced_refresh_at) >= self._refresh_cooldown_seconds
            )
            if can_force_refresh:
                self._last_forced_refresh_at = now
                self._refresh(now)
                key = self._keys_by_kid.get(kid)

            if key is None:
                raise TokenVerificationError("Unknown signing key.")
            return key

    def _refresh(self, now: float) -> None:
        jwks_url = self._jwks_url_provider()
        if not jwks_url:
            raise AuthServiceUnavailableError("Authentication is not configured.")
        try:
            client = PyJWKClient(jwks_url, cache_keys=False)
            keys = client.get_signing_keys()
        except Exception as exc:
            if self._keys_by_kid:
                logger.warning(
                    "Could not refresh Cognito JWKS; continuing with cached signing keys."
                )
                return
            logger.warning("Could not fetch Cognito JWKS.")
            raise AuthServiceUnavailableError(
                "Authentication service is temporarily unavailable."
            ) from exc
        self._keys_by_kid = {key.key_id: key for key in keys if key.key_id}
        self._last_fetch_at = now


_jwks_cache = _JWKSCache(lambda: settings.cognito_jwks_url)


def reset_jwks_cache_for_tests(
    jwks_url_provider: Callable[[], str | None] | None = None,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    global _jwks_cache
    _jwks_cache = _JWKSCache(
        jwks_url_provider or (lambda: settings.cognito_jwks_url),
        clock=clock,
    )


def verify_access_token(token: str) -> VerifiedIdentity:
    """Verify a Cognito access token and return its subject/email.

    Only access tokens are accepted (``token_use == "access"``); Cognito access tokens
    carry no ``aud`` claim, so the client is instead verified against ``client_id``.
    Any failure raises :class:`TokenVerificationError` with a message safe to surface
    to the caller, or :class:`AuthServiceUnavailableError` when the provider itself
    could not be reached (a server-side condition, not a bad credential).
    """
    issuer = settings.cognito_issuer_url
    client_id = settings.cognito_app_client_id
    if not issuer or not client_id:
        raise AuthServiceUnavailableError("Authentication is not configured.")

    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise TokenVerificationError("The token is malformed.") from exc

    kid = unverified_header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise TokenVerificationError("The token is malformed.")

    signing_key = _jwks_cache.get_signing_key(kid)

    try:
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=[EXPECTED_ALGORITHM],
            issuer=issuer,
            leeway=CLOCK_LEEWAY_SECONDS,
            options={"verify_aud": False},
        )
    except jwt.InvalidTokenError as exc:
        raise TokenVerificationError("The token could not be verified.") from exc

    if claims.get("token_use") != EXPECTED_TOKEN_USE:
        raise TokenVerificationError("The token is not an access token.")
    if claims.get("client_id") != client_id:
        raise TokenVerificationError("The token was not issued for this application.")

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise TokenVerificationError("The token is missing a subject.")

    email = claims.get("email")
    return VerifiedIdentity(subject=subject, email=email if isinstance(email, str) else None)
