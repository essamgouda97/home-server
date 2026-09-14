"""Single local bridge with runtime credentials provisioned outside Git."""
from homeassistant import config_entries
from . import DOMAIN

class CodexHomeFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    async def async_step_user(self, user_input=None):
        return await self.async_step_import({})
    async def async_step_import(self, data):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title='Codex Home', data={})
