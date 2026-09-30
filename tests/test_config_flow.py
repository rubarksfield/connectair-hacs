"""Config entry creation requires a renewable, server-validated identity."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

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


async def test_callback_form_does_not_display_token_fields(hass):
    result = await hass.config_entries.flow.async_init("connectair", context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert set(result["data_schema"].schema) == {"callback_url"}
    assert result["description_placeholders"]["authorization_url"].startswith(
        "https://soler-palau-pm.eu.auth0.com/authorize?"
    )


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
