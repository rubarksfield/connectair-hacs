"""Config entry creation requires a renewable, server-validated identity."""

from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from aioresponses import CallbackResult, aioresponses
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.connectair.auth import TOKEN_URL
from custom_components.connectair.models import AuthenticationError, TransportError

TOKENS = {
    "access_token": "temporary-test-access",
    "refresh_token": "test-refresh",
    "expires_at": 10,
}


@pytest.fixture(autouse=True)
def enable_custom(enable_custom_integrations):
    """Load this repository's integration in the real HA framework."""


@pytest.fixture
def account_api():
    with (
        patch("custom_components.connectair.config_flow.Auth0Session") as auth_class,
        patch("custom_components.connectair.config_flow.ConnectairClient") as client_class,
        patch("custom_components.connectair.async_setup_entry", return_value=True),
    ):
        auth = auth_class.return_value
        auth.async_get_access_token = AsyncMock(return_value="renewed-test-access")
        auth.tokens = {**TOKENS, "access_token": "renewed-test-access"}
        client = client_class.return_value
        client.async_get_user = AsyncMock(
            return_value={"id": "account-a", "email": "owner@example.com"}
        )
        yield auth, client


async def test_callback_form_masks_optional_advanced_refresh_token(hass):
    result = await hass.config_entries.flow.async_init("connectair", context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert set(result["data_schema"].schema) == {"callback_url", "refresh_token"}
    token_selector = result["data_schema"].schema["refresh_token"]
    assert token_selector.config["type"] == "password"
    assert "access_token" not in result["data_schema"].schema
    assert result["description_placeholders"]["authorization_url"].startswith(
        "https://soler-palau-pm.eu.auth0.com/authorize?"
    )


async def test_refresh_only_rest_form_verifies_account_and_stores_rotated_tokens(
    hass, hass_client, monkeypatch
):
    monkeypatch.setattr("custom_components.connectair.auth.time.time", lambda: 1000)
    assert await async_setup_component(hass, "config", {})
    client = await hass_client()
    initial = await client.post("/api/config/config_entries/flow", json={"handler": "connectair"})
    form = await initial.json()
    fields = {field["name"]: field for field in form["data_schema"]}
    assert fields["refresh_token"]["selector"]["text"]["type"] == "password"

    def refresh_response(url, **kwargs):
        assert kwargs["json"] == {
            "grant_type": "refresh_token",
            "client_id": "lqCG3F9LYqkZb0wiQapp2QAWwNtLD8y7",
            "refresh_token": "private-synthetic-refresh",
        }
        return CallbackResult(
            payload={
                "access_token": "renewed-synthetic-access",
                "refresh_token": "rotated-synthetic-refresh",
                "expires_in": 3600,
            }
        )

    def account_response(url, **kwargs):
        assert kwargs["headers"]["Authorization"] == "Bearer renewed-synthetic-access"
        return CallbackResult(payload={"id": "verified-account"})

    with (
        patch("custom_components.connectair.async_setup_entry", return_value=True),
        aioresponses(passthrough=["http://127.0.0.1"]) as http,
    ):
        http.post(TOKEN_URL, callback=refresh_response)
        http.get(
            "https://spportalwebapp-pro.azurewebsites.net/api/user/me", callback=account_response
        )
        response = await client.post(
            f"/api/config/config_entries/flow/{form['flow_id']}",
            json={"refresh_token": "private-synthetic-refresh"},
        )
        result = await response.json()
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    entry = hass.config_entries.async_entries("connectair")[0]
    assert entry.unique_id == "verified-account"
    assert entry.data["tokens"] == {
        "access_token": "renewed-synthetic-access",
        "refresh_token": "rotated-synthetic-refresh",
        "expires_at": 4600.0,
    }
    assert "private-synthetic-refresh" not in str(result)
    assert "rotated-synthetic-refresh" not in str(result)
    assert "renewed-synthetic-access" not in str(result)


@pytest.mark.parametrize("method", ["refresh", "callback"])
async def test_same_input_retry_retains_rotated_tokens_after_account_outage(
    hass, hass_client, monkeypatch, method
):
    monkeypatch.setattr("custom_components.connectair.auth.time.time", lambda: 1000)
    assert await async_setup_component(hass, "config", {})
    client = await hass_client()
    initial = await client.post("/api/config/config_entries/flow", json={"handler": "connectair"})
    form = await initial.json()
    if method == "refresh":
        submitted = {"refresh_token": "single-use-synthetic-refresh"}
    else:
        state = parse_qs(urlsplit(form["description_placeholders"]["authorization_url"]).query)[
            "state"
        ][0]
        submitted = {
            "callback_url": "https://www.connectairapp.com/?"
            + urlencode({"code": "single-use-code", "state": state})
        }
    with (
        patch("custom_components.connectair.async_setup_entry", return_value=True),
        aioresponses(passthrough=["http://127.0.0.1"]) as http,
    ):
        if method == "callback":
            http.post(
                TOKEN_URL,
                payload={
                    "access_token": "exchanged-access",
                    "refresh_token": "single-use-synthetic-refresh",
                    "expires_in": 3600,
                },
            )
        http.post(
            TOKEN_URL,
            payload={
                "access_token": "retained-access",
                "refresh_token": "retained-rotated-refresh",
                "expires_in": 3600,
            },
        )
        http.get("https://spportalwebapp-pro.azurewebsites.net/api/user/me", status=503)
        http.get(
            "https://spportalwebapp-pro.azurewebsites.net/api/user/me",
            payload={"id": "verified-account"},
        )
        first = await client.post(
            f"/api/config/config_entries/flow/{form['flow_id']}", json=submitted
        )
        error = await first.json()
        assert error["errors"] == {"base": "cannot_connect"}
        assert not hass.config_entries.async_entries("connectair")
        assert "retained-access" not in str(error)
        assert "retained-rotated-refresh" not in str(error)
        second = await client.post(
            f"/api/config/config_entries/flow/{form['flow_id']}", json=submitted
        )
        result = await second.json()
        await hass.async_block_till_done()
        grants = [
            call.kwargs["json"]["grant_type"]
            for (request_method, url), calls in http.requests.items()
            if str(url) == TOKEN_URL
            for call in calls
        ]
    assert result["type"] == "create_entry"
    assert grants == (
        ["authorization_code", "refresh_token"] if method == "callback" else ["refresh_token"]
    )
    assert hass.config_entries.async_entries("connectair")[0].data["tokens"] == {
        "access_token": "retained-access",
        "refresh_token": "retained-rotated-refresh",
        "expires_at": 4600.0,
    }


async def test_changed_credential_clears_pending_login_and_verifies_new_account(
    hass, hass_client, monkeypatch
):
    monkeypatch.setattr("custom_components.connectair.auth.time.time", lambda: 1000)
    assert await async_setup_component(hass, "config", {})
    client = await hass_client()
    form = await (
        await client.post("/api/config/config_entries/flow", json={"handler": "connectair"})
    ).json()

    def replacement_account(url, **kwargs):
        assert kwargs["headers"]["Authorization"] == "Bearer replacement-access"
        return CallbackResult(payload={"id": "replacement-account"})

    with (
        patch("custom_components.connectair.async_setup_entry", return_value=True),
        aioresponses(passthrough=["http://127.0.0.1"]) as http,
    ):
        http.post(
            TOKEN_URL,
            payload={
                "access_token": "old-access",
                "refresh_token": "old-rotated",
                "expires_in": 3600,
            },
        )
        http.get("https://spportalwebapp-pro.azurewebsites.net/api/user/me", status=503)
        first = await client.post(
            f"/api/config/config_entries/flow/{form['flow_id']}",
            json={"refresh_token": "old-refresh"},
        )
        assert (await first.json())["errors"] == {"base": "cannot_connect"}
        http.post(
            TOKEN_URL,
            payload={
                "access_token": "replacement-access",
                "refresh_token": "replacement-rotated",
                "expires_in": 3600,
            },
        )
        http.get(
            "https://spportalwebapp-pro.azurewebsites.net/api/user/me", callback=replacement_account
        )
        second = await client.post(
            f"/api/config/config_entries/flow/{form['flow_id']}",
            json={"refresh_token": "replacement-refresh"},
        )
        result = await second.json()
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    entry = hass.config_entries.async_entries("connectair")[0]
    assert entry.unique_id == "replacement-account"
    assert entry.data["tokens"]["refresh_token"] == "replacement-rotated"


async def test_account_authentication_failure_discards_pending_credentials(hass, hass_client):
    assert await async_setup_component(hass, "config", {})
    client = await hass_client()
    form = await (
        await client.post("/api/config/config_entries/flow", json={"handler": "connectair"})
    ).json()
    with aioresponses(passthrough=["http://127.0.0.1"]) as http:
        http.post(
            TOKEN_URL,
            payload={
                "access_token": "rejected-access",
                "refresh_token": "rejected-rotated",
                "expires_in": 3600,
            },
        )
        http.get("https://spportalwebapp-pro.azurewebsites.net/api/user/me", status=403)
        first = await client.post(
            f"/api/config/config_entries/flow/{form['flow_id']}",
            json={"refresh_token": "rejected-original"},
        )
        assert (await first.json())["errors"] == {"base": "invalid_auth"}
        http.post(TOKEN_URL, status=400)
        second = await client.post(
            f"/api/config/config_entries/flow/{form['flow_id']}",
            json={"refresh_token": "rejected-original"},
        )
        assert (await second.json())["errors"] == {"base": "invalid_auth"}
    assert not hass.config_entries.async_entries("connectair")


@pytest.mark.parametrize("refresh_token", ["", "   "])
async def test_blank_advanced_refresh_is_rejected_without_echoing_credentials(hass, refresh_token):
    form = await hass.config_entries.flow.async_init("connectair", context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"], {"refresh_token": refresh_token}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert "refresh_token" not in result.get("description_placeholders", {})
    assert not hass.config_entries.async_entries("connectair")


async def test_revoked_advanced_token_returns_safe_error_through_rest(hass, hass_client):
    assert await async_setup_component(hass, "config", {})
    client = await hass_client()
    initial = await client.post("/api/config/config_entries/flow", json={"handler": "connectair"})
    form = await initial.json()
    with aioresponses(passthrough=["http://127.0.0.1"]) as http:
        http.post(TOKEN_URL, status=400, payload={"error_description": "private-synthetic-revoked"})
        response = await client.post(
            f"/api/config/config_entries/flow/{form['flow_id']}",
            json={"refresh_token": "private-synthetic-revoked"},
        )
        result = await response.json()
    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}
    assert "private-synthetic-revoked" not in str(result)
    assert not hass.config_entries.async_entries("connectair")


async def test_normal_callback_login_ignores_an_empty_advanced_field(hass, account_api):
    form = await hass.config_entries.flow.async_init("connectair", context={"source": "user"})
    with patch(
        "custom_components.connectair.config_flow.async_exchange_callback", return_value=TOKENS
    ):
        result = await hass.config_entries.flow.async_configure(
            form["flow_id"],
            {
                "callback_url": "https://www.connectairapp.com/?code=test&state=test",
                "refresh_token": "",
            },
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "account-a"


async def test_advanced_refresh_reauth_retains_verified_account(hass, account_api):
    existing = MockConfigEntry(domain="connectair", unique_id="account-a", data={"tokens": TOKENS})
    existing.add_to_hass(hass)
    with patch("homeassistant.config_entries.ConfigEntries.async_reload", return_value=True):
        form = await hass.config_entries.flow.async_init(
            "connectair",
            context={"source": config_entries.SOURCE_REAUTH, "entry_id": existing.entry_id},
            data=existing.data,
        )
        result = await hass.config_entries.flow.async_configure(
            form["flow_id"], {"refresh_token": "private-synthetic-refresh"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert existing.unique_id == "account-a"
    assert existing.data["tokens"]["access_token"] == "renewed-test-access"


async def test_token_bundle_creates_account_entry_after_refresh(hass, account_api):
    auth, _client = account_api
    # Revoked or unsupported refresh grants must prevent entry creation.
    auth.async_get_access_token = AsyncMock(side_effect=AuthenticationError("refresh denied"))
    result = await hass.config_entries.flow.async_init(
        "connectair", context={"source": "user"}, data=TOKENS
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    auth.async_get_access_token = AsyncMock(return_value="renewed-test-access")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], TOKENS)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "account-a"
    assert result["data"]["tokens"]["access_token"] == "renewed-test-access"


async def test_nonrenewable_login_cannot_create_entry(hass, account_api):
    result = await hass.config_entries.flow.async_init(
        "connectair",
        context={"source": "user"},
        data={"access_token": "temporary", "expires_at": 99},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "missing_refresh_token"}


async def test_duplicate_verified_account_is_rejected(hass, account_api):
    existing = MockConfigEntry(domain="connectair", unique_id="account-a", data={"tokens": TOKENS})
    existing.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        "connectair", context={"source": "user"}, data=TOKENS
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_unreachable_identity_endpoint_does_not_accept_tokens(hass, account_api):
    _auth, client = account_api
    client.async_get_user.side_effect = TransportError("cloud unavailable")
    result = await hass.config_entries.flow.async_init(
        "connectair", context={"source": "user"}, data=TOKENS
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reauth_rejects_another_account(hass, account_api):
    existing = MockConfigEntry(
        domain="connectair", unique_id="another-account", data={"tokens": TOKENS}
    )
    existing.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        "connectair",
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": existing.entry_id},
        data=existing.data,
    )
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], TOKENS)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"


async def test_verified_reauth_updates_existing_entry(hass, account_api):
    existing = MockConfigEntry(domain="connectair", unique_id="account-a", data={"tokens": TOKENS})
    existing.add_to_hass(hass)
    with patch("homeassistant.config_entries.ConfigEntries.async_reload", return_value=True):
        result = await hass.config_entries.flow.async_init(
            "connectair",
            context={"source": config_entries.SOURCE_REAUTH, "entry_id": existing.entry_id},
            data=existing.data,
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], TOKENS)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert existing.data["tokens"]["access_token"] == "renewed-test-access"
