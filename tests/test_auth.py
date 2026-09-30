"""Credential renewal and callback boundary tests; no real account data."""

import asyncio
import base64
import hashlib
from urllib.parse import parse_qs, urlencode, urlsplit

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.connectair.auth import (
    TOKEN_URL,
    Auth0Session,
    async_exchange_callback,
    create_authorization_request,
    validate_callback,
)
from custom_components.connectair.models import AuthenticationError


def callback(request, **overrides):
    values = {"code": "test-code", "state": request.state, **overrides}
    return "https://www.connectairapp.com/?" + urlencode(values)


def test_pkce_is_random_s256_and_uses_approved_callback():
    first, second = create_authorization_request(), create_authorization_request()
    params = parse_qs(urlsplit(first.authorization_url).query)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(first.verifier.encode()).digest())
    assert params["code_challenge"] == [challenge.rstrip(b"=").decode()]
    assert first.verifier != second.verifier and first.state != second.state
    assert params["redirect_uri"] == ["https://www.connectairapp.com"]
    assert "offline_access" in params["scope"][0].split()


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/?code=abc&state=valid",
        "https://www.connectairapp.com.evil.example/?code=abc&state=valid",
        "http://www.connectairapp.com/?code=abc&state=valid",
        "https://www.connectairapp.com:444/?code=abc&state=valid",
        "https://www.connectairapp.com/other?code=abc&state=valid",
    ],
)
def test_callback_rejects_other_destinations(url):
    request = create_authorization_request()
    with pytest.raises(AuthenticationError):
        validate_callback(request, url)


def test_callback_rejects_state_mismatch_and_duplicate_parameters():
    request = create_authorization_request()
    with pytest.raises(AuthenticationError):
        validate_callback(request, callback(request, state="different"))
    with pytest.raises(AuthenticationError):
        validate_callback(request, callback(request) + "&code=second-code")
    assert validate_callback(request, callback(request)) == "test-code"


def test_callback_rejects_nonascii_state_safely():
    request = create_authorization_request()
    with pytest.raises(AuthenticationError):
        validate_callback(request, callback(request, state="invalid-\u00e9"))


async def test_exchange_requires_refresh_token_and_sends_exact_pkce(monkeypatch):
    monkeypatch.setattr("custom_components.connectair.auth.time.time", lambda: 1000)
    request = create_authorization_request()
    async with aiohttp.ClientSession() as session:
        with aioresponses() as http:
            http.post(
                TOKEN_URL,
                payload={
                    "access_token": "access",
                    "refresh_token": "renew",
                    "expires_in": 3600,
                },
            )
            tokens = await async_exchange_callback(session, request, callback(request))
            assert tokens == {
                "access_token": "access",
                "refresh_token": "renew",
                "expires_at": 4600.0,
            }
            sent = list(http.requests.values())[0][0].kwargs["json"]
            assert sent["grant_type"] == "authorization_code"
            assert sent["code"] == "test-code"
            assert sent["code_verifier"] == request.verifier
            assert sent["redirect_uri"] == "https://www.connectairapp.com"
        with aioresponses() as http:
            http.post(TOKEN_URL, payload={"access_token": "access", "expires_in": 3600})
            with pytest.raises(AuthenticationError, match="offline"):
                await async_exchange_callback(session, request, callback(request))


async def test_refresh_rotation_is_saved_and_concurrent_calls_share_refresh(monkeypatch):
    monkeypatch.setattr("custom_components.connectair.auth.time.time", lambda: 1000)
    saved = []

    async def save(tokens):
        saved.append(tokens)

    async with aiohttp.ClientSession() as session:
        auth = Auth0Session(
            session,
            {
                "access_token": "old-access",
                "refresh_token": "old-renew",
                "expires_at": 0,
            },
            save_tokens=save,
        )
        with aioresponses() as http:
            http.post(
                TOKEN_URL,
                payload={
                    "access_token": "new-access",
                    "refresh_token": "new-renew",
                    "expires_in": 7200,
                },
            )
            result = await asyncio.gather(
                auth.async_get_access_token(),
                auth.async_get_access_token(),
            )
        assert result == ["new-access", "new-access"]
        assert saved == [
            {
                "access_token": "new-access",
                "refresh_token": "new-renew",
                "expires_at": 8200.0,
            }
        ]
        assert auth.tokens["refresh_token"] == "new-renew"


async def test_current_token_is_reused_and_force_refresh_preserves_nonrotating_refresh(monkeypatch):
    monkeypatch.setattr("custom_components.connectair.auth.time.time", lambda: 1000)
    async with aiohttp.ClientSession() as session:
        auth = Auth0Session(
            session,
            {
                "access_token": "current",
                "refresh_token": "renew",
                "expires_at": 3000,
            },
        )
        assert await auth.async_get_access_token() == "current"
        with aioresponses() as http:
            http.post(TOKEN_URL, payload={"access_token": "next", "expires_in": 3600})
            assert await auth.async_get_access_token(force_refresh=True) == "next"
        assert auth.tokens["refresh_token"] == "renew"


async def test_auth_failure_does_not_expose_provider_description():
    async with aiohttp.ClientSession() as session:
        auth = Auth0Session(
            session,
            {
                "access_token": "secret-access",
                "refresh_token": "secret-refresh",
                "expires_at": 0,
            },
        )
        with aioresponses() as http:
            http.post(
                TOKEN_URL,
                status=400,
                payload={
                    "error": "invalid_grant",
                    "error_description": "secret-refresh was rejected",
                },
            )
            with pytest.raises(AuthenticationError) as raised:
                await auth.async_get_access_token()
        assert "secret" not in str(raised.value)


@pytest.mark.parametrize("expires", [0, -1, None, "bad", float("inf"), True])
async def test_invalid_token_lifetime_is_rejected(expires):
    request = create_authorization_request()
    async with aiohttp.ClientSession() as session:
        with aioresponses() as http:
            http.post(
                TOKEN_URL,
                payload={
                    "access_token": "access",
                    "refresh_token": "refresh",
                    "expires_in": expires,
                },
            )
            with pytest.raises(AuthenticationError):
                await async_exchange_callback(session, request, callback(request))
