"""Use subscription-authenticated Codex as a Home Assistant conversation agent."""
from pathlib import Path
import voluptuous as vol
from homeassistant.const import Platform

DOMAIN = 'codex_home'
PLATFORMS = [Platform.CONVERSATION]
CONFIG_SCHEMA = vol.Schema({vol.Optional(DOMAIN): vol.Schema({})}, extra=vol.ALLOW_EXTRA)

async def async_setup(hass, config):
    if DOMAIN in config and not hass.config_entries.async_entries(DOMAIN):
        hass.async_create_task(hass.config_entries.flow.async_init(DOMAIN, context={'source':'import'}, data={}))
    return True

async def async_setup_entry(hass, entry):
    token = await hass.async_add_executor_job(Path('/run/secrets/codex_home_token').read_text)
    entry.runtime_data = {'url':'http://127.0.0.1:18790', 'token':token.strip()}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
