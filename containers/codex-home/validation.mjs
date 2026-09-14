export function validateReply(result, tools) {
  if (!result || typeof result.speech !== 'string' || result.speech.length > 16000 ||
      !Array.isArray(result.tool_calls) || result.tool_calls.length > 8) throw new Error('Invalid response');
  const allowed = new Set(tools.map(tool => tool.name));
  for (const call of result.tool_calls) {
    if (!call || !allowed.has(call.name) || typeof call.arguments_json !== 'string') throw new Error('Unknown tool');
    const args = JSON.parse(call.arguments_json);
    if (!args || Array.isArray(args) || typeof args !== 'object') throw new Error('Invalid tool arguments');
  }
  return result;
}
