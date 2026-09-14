import { test } from 'node:test';
import assert from 'node:assert/strict';
import { validateReply } from './validation.mjs';

test('reject model-invented tools before Home Assistant receives them', () => {
  assert.throws(() => validateReply({speech: '', tool_calls: [
    {name: 'run_shell', arguments_json: '{"command":"id"}'}
  ]}, [{name: 'HassTurnOn'}]));
});
test('reject malformed argument shapes', () => {
  for (const arguments_json of ['null', '[]', '"text"', '{broken']) {
    assert.throws(() => validateReply({speech: '', tool_calls: [
      {name: 'HassTurnOn', arguments_json}
    ]}, [{name: 'HassTurnOn'}]));
  }
});
test('accept only declared calls with object arguments; HA validates their schema', () => {
  const result = {speech: '', tool_calls: [
    {name: 'HassTurnOn', arguments_json: '{"name":"Codex demo switch"}'}
  ]};
  assert.deepEqual(validateReply(result, [{name: 'HassTurnOn'}]), result);
});
