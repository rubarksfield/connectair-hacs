"""Auth0 PKCE and serialized renewable login for the existing Connectair client."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import math
import secrets
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import aiohttp

from .models import AuthenticationError, TransportError

AUTH_DOMAIN = "https://soler-palau-pm.eu.auth0.com"
TOKEN_URL = f"{AUTH_DOMAIN}/oauth/token"
CLIENT_ID = "lqCG3F9LYqkZb0wiQapp2QAWwNtLD8y7"
AUDIENCE = "https://connectairapp.com/api"
REDIRECT_URI = "https://www.connectairapp.com"
TOKEN_SKEW_SECONDS = 60
SaveTokens = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True, repr=False)
class AuthorizationRequest:
    """Ephemeral sign-in transaction; never log the PKCE verifier."""

    state: str
    verifier: str
    authorization_url: str


def create_authorization_request(response_mode: str = "query") -> AuthorizationRequest:
    """Create a fresh PKCE transaction using the provider-approved callback."""
    if response_mode not in {"query", "fragment"}:
        raise ValueError("Unsupported OAuth response mode")
    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "audience": AUDIENCE,
        "response_type": "code",
        "response_mode": response_mode,
        "scope": "openid profile email offline_access",
        "code_challenge": challenge.rstrip(b"=").decode(),
        "code_challenge_method": "S256",
        "state": state,
    }
    return AuthorizationRequest(state, verifier, f"{AUTH_DOMAIN}/authorize?{urlencode(params)}")


def validate_callback(request: AuthorizationRequest, callback_url: str) -> str:
    """Validate callback origin/state before using its one-time code."""
    try:
        parts = urlsplit(callback_url.strip())
        valid_origin = (
            parts.scheme == "https"
            and parts.hostname == "www.connectairapp.com"
            and parts.port in {None, 443}
            and parts.username is None
            and parts.password is None
            and parts.path in {"", "/"}
        )
    except ValueError, AttributeError:
        raise AuthenticationError("Invalid sign-in callback") from None
    if not valid_origin or (parts.query and parts.fragment):
        raise AuthenticationError("Invalid sign-in callback")
    values = parse_qs(parts.query or parts.fragment, keep_blank_values=True)
    state = values.get("state", [])
    if (
        len(state) != 1
        or not state[0].isascii()
        or not secrets.compare_digest(state[0], request.state)
    ):
        raise AuthenticationError("Sign-in state does not match; start sign-in again")
    if "error" in values:
        raise AuthenticationError("Sign-in was not completed")
    code = values.get("code", [])
    if len(code) != 1 or not code[0]:
        raise AuthenticationError("Sign-in callback has no authorization code")
    return code[0]


async def _request_tokens(session: aiohttp.ClientSession, payload: dict[str, Any]) -> dict:
    """Exchange with fixed provider, preserving TLS and avoiding reflected secrets."""
    try:
        async with session.post(
            TOKEN_URL,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=30),
            allow_redirects=False,
        ) as response:
            if response.status in {400, 401, 403}:
                raise AuthenticationError("Connectair login is invalid or expired")
            if response.status != 200:
                raise TransportError("Connectair login service is temporarily unavailable")
            try:
                result = await response.json()
            except ValueError, aiohttp.ContentTypeError:
                raise AuthenticationError("Invalid Connectair token response") from None
    except aiohttp.ClientError, TimeoutError:
        raise TransportError("Unable to reach Connectair login service") from None
    if not isinstance(result, dict):
        raise AuthenticationError("Invalid Connectair token response")
    return result


def _normalize_response(response: Mapping[str, Any], previous_refresh: str | None = None) -> dict:
    """Convert a provider token response to a bundle suitable for private HA storage."""
    access_token = response.get("access_token")
    refresh_token = response.get("refresh_token", previous_refresh)
    if not isinstance(access_token, str) or not access_token:
        raise AuthenticationError("Connectair did not provide an access token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise AuthenticationError(
            "Connectair did not allow offline access; renewable login required"
        )
    if isinstance(response.get("expires_in"), bool):
        raise AuthenticationError("Invalid Connectair token lifetime")
    try:
        lifetime = float(response["expires_in"])
    except KeyError, TypeError, ValueError:
        raise AuthenticationError("Invalid Connectair token lifetime") from None
    if not math.isfinite(lifetime) or lifetime <= 0:
        raise AuthenticationError("Invalid Connectair token lifetime")
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": time.time() + lifetime,
    }


async def async_exchange_callback(
    session: aiohttp.ClientSession,
    request: AuthorizationRequest,
    callback_url: str,
) -> dict[str, Any]:
    """Exchange one validated callback code; require renewable credentials."""
    code = validate_callback(request, callback_url)
    response = await _request_tokens(
        session,
        {
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": code,
            "code_verifier": request.verifier,
            "redirect_uri": REDIRECT_URI,
        },
    )
    return _normalize_response(response)


class Auth0Session:
    """Reuse current access and serialize refresh-token rotation."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        tokens: Mapping[str, Any],
        save_tokens: SaveTokens | None = None,
    ) -> None:
        self._session = session
        self._tokens = dict(tokens)
        self._save_tokens = save_tokens
        self._lock = asyncio.Lock()
        if not all(
            isinstance(self._tokens.get(key), str) and self._tokens[key]
            for key in ("access_token", "refresh_token")
        ):
            raise AuthenticationError("Renewable Connectair login is required")
        try:
            self._tokens["expires_at"] = float(self._tokens["expires_at"])
        except KeyError, TypeError, ValueError:
            raise AuthenticationError("Connectair token expiry is missing or invalid") from None
        if not math.isfinite(self._tokens["expires_at"]):
            raise AuthenticationError("Connectair token expiry is missing or invalid")

    @property
    def tokens(self) -> dict[str, Any]:
        """Return a copy for private config-entry persistence, never diagnostic output."""
        return dict(self._tokens)

    async def async_get_access_token(self, force_refresh: bool = False) -> str:
        """Refresh on expiry, with one exchange for simultaneous expired requests."""
        before_lock = self._tokens["access_token"]
        async with self._lock:
            changed_while_waiting = before_lock != self._tokens["access_token"]
            fresh = time.time() + TOKEN_SKEW_SECONDS < self._tokens["expires_at"]
            if fresh and (not force_refresh or changed_while_waiting):
                return self._tokens["access_token"]
            response = await _request_tokens(
                self._session,
                {
                    "grant_type": "refresh_token",
                    "client_id": CLIENT_ID,
                    "refresh_token": self._tokens["refresh_token"],
                },
            )
            self._tokens = _normalize_response(response, self._tokens["refresh_token"])
            if self._save_tokens is not None:
                await self._save_tokens(self.tokens)
            return self._tokens["access_token"]
