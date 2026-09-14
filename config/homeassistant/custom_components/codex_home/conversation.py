"""Map structured Codex replies onto Home Assistant's exposed Assist tools."""
import dataclasses
import json
import aiohttp
from probatio import to_openapi
from homeassistant.components import conversation
from homeassistant.const import MATCH_ALL
from homeassistant.helpers import llm, intent
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from . import DOMAIN

INSTRUCTIONS = '''You are Codex, Essam's main conversational home assistant.
Answer naturally and concisely. Use Home Assistant tools for current device facts
and requested actions. Only control devices exposed to Assist. Ask when a target
is ambiguous. Do not claim a device was changed until a tool confirms it.
Room identity and home location are unknown unless a real entity provides them.'''

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([CodexConversation(entry)])

class CodexConversation(conversation.ConversationEntity, conversation.AbstractConversationAgent):
    _attr_name = 'Codex'
    _attr_unique_id = 'codex_home_conversation'
    _attr_supported_features = conversation.ConversationEntityFeature.CONTROL
    _attr_supports_streaming = False

    def __init__(self, entry):
        self.entry = entry

    @property
    def supported_languages(self):
        return MATCH_ALL

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        conversation.async_set_agent(self.hass, self.entry, self)

    async def async_will_remove_from_hass(self):
        conversation.async_unset_agent(self.hass, self.entry)
        await super().async_will_remove_from_hass()

    async def _async_handle_message(self, user_input, chat_log):
        try:
            await chat_log.async_provide_llm_data(user_input.as_llm_context(DOMAIN),
                                                llm.LLM_API_ASSIST, INSTRUCTIONS,
                                                user_input.extra_system_prompt)
            api = chat_log.llm_api
            tools = [{'name':tool.name, 'description':tool.description or '',
                      'parameters':to_openapi(tool.parameters, custom_serializer=api.custom_serializer)}
                     for tool in api.tools]
            allowed = {tool['name'] for tool in tools}
            session = async_get_clientsession(self.hass)
            for iteration in range(5):
                messages = [dataclasses.asdict(content) for content in chat_log.content]
                # Native provider payloads and attachments are not part of this text adapter.
                for message in messages:
                    message.pop('native', None)
                    message.pop('attachments', None)
                payload = json.dumps({'messages':messages, 'tools':tools}, default=str)
                async with session.post(self.entry.runtime_data['url']+'/conversation', data=payload,
                                        headers={'Authorization':'Bearer '+self.entry.runtime_data['token'],
                                                 'Content-Type':'application/json'},
                                        timeout=aiohttp.ClientTimeout(total=135)) as response:
                    response.raise_for_status()
                    result = await response.json()
                calls = []
                for call in result['tool_calls']:
                    if call['name'] not in allowed:
                        raise ValueError('Unknown Home Assistant tool')
                    args = json.loads(call['arguments_json'])
                    if not isinstance(args, dict):
                        raise ValueError('Invalid tool arguments')
                    calls.append(llm.ToolInput(tool_name=call['name'], tool_args=args))
                content = conversation.AssistantContent(agent_id=self.entity_id,
                                                       content=result['speech'], tool_calls=calls or None)
                async for _ in chat_log.async_add_assistant_content(content):
                    pass
                if not calls:
                    return conversation.async_get_result_from_chat_log(user_input, chat_log)
            message = 'That request needed too many steps. Please ask for one action at a time.'
        except conversation.ConverseError as error:
            return error.as_conversation_result()
        except (aiohttp.ClientError, TimeoutError, ValueError, KeyError):
            message = 'Codex could not finish that request. Please retry; its login, quota or connection may need attention.'
        response = intent.IntentResponse(language=user_input.language)
        response.async_set_error(intent.IntentResponseErrorCode.UNKNOWN, message)
        return conversation.ConversationResult(response=response, conversation_id=chat_log.conversation_id)
