"""Connectair integration constants."""

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "connectair"
PLATFORMS = (Platform.FAN, Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON)
UPDATE_INTERVAL = timedelta(seconds=30)
CONF_TOKENS = "tokens"
CONF_CALLBACK_URL = "callback_url"
