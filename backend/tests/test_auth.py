import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.core.auth as auth_module
from app.core.auth import (
    AuthServiceUnavailableError,
    TokenVerificationError,
    VerifiedIdentity,
    verify_access_token,
)
from app.core.config import settings
from app.models.user import User

ISSUER = "https://cognito-idp.ca-central-1.amazonaws.com/ca-central-1_example"
CLIENT_ID = "test-client-id"
KID = "test-key-1"


def _generate_keypair() -> tuple[str, dict]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    jwk_dict = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk_dict.update(kid=KID, use="sig", alg="RS256")
    return private_pem, jwk_dict


PRIVATE_KEY_PEM, PUBLIC_JWK = _generate_keypair()
OTHER_PRIVATE_KEY_PEM, _ = _generate_keypair()


def _make_token(
    *,
    subject: str = "cognito-subject-1",
    issuer: str = ISSUER,
    client_id: str | None = CLIENT_ID,
    token_use: str = "access",
    exp_delta_seconds: int = 3600,
    kid: str | None = KID,
    signing_key: str = PRIVATE_KEY_PEM,
    email: str | None = None,
) -> str:
    now = int(time.time())
    claims: dict = {
        "sub": subject,
        "iss": issuer,
        "token_use": token_use,
        "iat": now,
        "exp": now + exp_delta_seconds,
    }
    if client_id is not None:
        claims["client_id"] = client_id
    if email is not None:
        claims["email"] = email
    headers = {"kid": kid} if kid is not None else {}
    return jwt.encode(claims, signing_key, algorithm="RS256", headers=headers)


class FakeJWKSClient:
    """Stands in for jwt.PyJWKClient so tests never contact a real network."""

    fetch_count = 0
    fail_next = False

    def __init__(self, uri: str, cache_keys: bool = False) -> None:
        self.uri = uri

    def get_signing_keys(self) -> list:
        FakeJWKSClient.fetch_count += 1
        if FakeJWKSClient.fail_next:
            raise RuntimeError("simulated JWKS network failure")
        return [jwt.PyJWK(PUBLIC_JWK, algorithm="RS256")]


@pytest.fixture(autouse=True)
def _cognito_test_setup(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "cognito_region", "ca-central-1")
    monkeypatch.setattr(settings, "cognito_user_pool_id", "ca-central-1_example")
    monkeypatch.setattr(settings, "cognito_app_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "cognito_issuer", None)
    monkeypatch.setattr(auth_module, "PyJWKClient", FakeJWKSClient)
    FakeJWKSClient.fetch_count = 0
    FakeJWKSClient.fail_next = False
    auth_module.reset_jwks_cache_for_tests()
    yield
    auth_module.reset_jwks_cache_for_tests()


# --- app.core.auth.verify_access_token -------------------------------------------


def test_valid_access_token_is_verified() -> None:
    token = _make_token(subject="cognito-subject-1", email="user@example.com")

    identity = verify_access_token(token)

    assert identity == VerifiedIdentity(subject="cognito-subject-1", email="user@example.com")


def test_missing_email_claim_resolves_to_none() -> None:
    identity = verify_access_token(_make_token())

    assert identity.email is None


@pytest.mark.parametrize("token", ["not-a-jwt", "a.b.c", "", "a.b.c.d.e"])
def test_malformed_token_is_rejected(token: str) -> None:
    with pytest.raises(TokenVerificationError):
        verify_access_token(token)


def test_expired_token_is_rejected() -> None:
    with pytest.raises(TokenVerificationError):
        verify_access_token(_make_token(exp_delta_seconds=-3600))


def test_wrong_issuer_is_rejected() -> None:
    with pytest.raises(TokenVerificationError):
        verify_access_token(
            _make_token(issuer="https://cognito-idp.ca-central-1.amazonaws.com/other-pool")
        )


def test_wrong_client_id_is_rejected() -> None:
    with pytest.raises(TokenVerificationError):
        verify_access_token(_make_token(client_id="a-different-client"))


def test_missing_client_id_claim_is_rejected() -> None:
    with pytest.raises(TokenVerificationError):
        verify_access_token(_make_token(client_id=None))


def test_id_token_used_in_place_of_access_token_is_rejected() -> None:
    with pytest.raises(TokenVerificationError):
        verify_access_token(_make_token(token_use="id"))


def test_wrong_signing_key_is_rejected() -> None:
    with pytest.raises(TokenVerificationError):
        verify_access_token(_make_token(signing_key=OTHER_PRIVATE_KEY_PEM))


def test_missing_kid_header_is_rejected() -> None:
    with pytest.raises(TokenVerificationError):
        verify_access_token(_make_token(kid=None))


def test_unknown_kid_forces_exactly_one_refresh_then_fails() -> None:
    with pytest.raises(TokenVerificationError):
        verify_access_token(_make_token(kid="unknown-kid"))

    assert FakeJWKSClient.fetch_count == 2


def test_unknown_kid_repeated_within_cooldown_does_not_refetch() -> None:
    token = _make_token(kid="unknown-kid")
    with pytest.raises(TokenVerificationError):
        verify_access_token(token)
    calls_after_first_attempt = FakeJWKSClient.fetch_count

    with pytest.raises(TokenVerificationError):
        verify_access_token(token)

    assert FakeJWKSClient.fetch_count == calls_after_first_attempt


def test_jwks_unavailable_with_no_cache_is_a_service_error_not_a_bad_credential() -> None:
    FakeJWKSClient.fail_next = True

    with pytest.raises(AuthServiceUnavailableError):
        verify_access_token(_make_token())


def test_jwks_refresh_failure_falls_back_to_previously_cached_keys() -> None:
    token = _make_token()
    verify_access_token(token)  # warms the cache with the real key

    FakeJWKSClient.fail_next = True
    auth_module._jwks_cache._last_fetch_at = 0.0  # force the TTL to look stale

    identity = verify_access_token(token)

    assert identity.subject == "cognito-subject-1"


def test_auth_not_configured_is_a_service_error(monkeypatch: pytest.MonkeyPatch) -> None:
    verify_access_token(_make_token())  # warm state before disabling config
    monkeypatch.setattr(settings, "cognito_app_client_id", None)

    with pytest.raises(AuthServiceUnavailableError):
        verify_access_token(_make_token())


# --- require_current_user via the full FastAPI route stack ------------------------


def test_missing_token_returns_401(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "auth_mode", "cognito")

    response = client.get("/documents")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Not authenticated."}


def test_non_bearer_scheme_returns_401(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "auth_mode", "cognito")

    response = client.get("/documents", headers={"Authorization": "Basic dXNlcjpwYXNz"})

    assert response.status_code == 401


def test_malformed_bearer_token_returns_401(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "auth_mode", "cognito")

    response = client.get("/documents", headers={"Authorization": "Bearer not-a-jwt"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated."}


def test_expired_token_returns_401(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "auth_mode", "cognito")
    token = _make_token(exp_delta_seconds=-3600)

    response = client.get("/documents", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_wrong_issuer_token_returns_401(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "auth_mode", "cognito")
    token = _make_token(issuer="https://cognito-idp.ca-central-1.amazonaws.com/other-pool")

    response = client.get("/documents", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_wrong_client_token_returns_401(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "auth_mode", "cognito")
    token = _make_token(client_id="someone-elses-client")

    response = client.get("/documents", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_id_token_as_bearer_token_returns_401(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "auth_mode", "cognito")
    token = _make_token(token_use="id")

    response = client.get("/documents", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_jwks_unavailable_returns_503_not_401(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "auth_mode", "cognito")
    FakeJWKSClient.fail_next = True
    token = _make_token()

    response = client.get("/documents", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 503
    assert "jwks" not in response.text.lower()
    assert ISSUER not in response.text


def test_valid_token_authenticates_and_provisions_local_user(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_mode", "cognito")
    token = _make_token(subject="cognito-subject-new", email="new-user@example.com")

    response = client.get("/documents", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {"items": []}
    user = db_session.scalar(select(User).where(User.cognito_sub == "cognito-subject-new"))
    assert user is not None
    assert user.email == "new-user@example.com"


def test_existing_subject_resolves_to_the_same_user_without_duplication(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_mode", "cognito")
    token = _make_token(subject="cognito-subject-existing")

    first = client.get("/documents", headers={"Authorization": f"Bearer {token}"})
    second = client.get("/documents", headers={"Authorization": f"Bearer {token}"})

    assert first.status_code == 200
    assert second.status_code == 200
    users = db_session.scalars(
        select(User).where(User.cognito_sub == "cognito-subject-existing")
    ).all()
    assert len(users) == 1


def test_auth_error_body_never_leaks_token_or_provider_internals(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "auth_mode", "cognito")
    token = _make_token(client_id="wrong-client")

    response = client.get("/documents", headers={"Authorization": f"Bearer {token}"})

    body = response.text
    assert "wrong-client" not in body
    assert CLIENT_ID not in body
    assert ISSUER not in body
    assert KID not in body
    assert token not in body


def test_health_endpoint_requires_no_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "auth_mode", "cognito")

    response = client.get("/health")

    assert response.status_code == 200
