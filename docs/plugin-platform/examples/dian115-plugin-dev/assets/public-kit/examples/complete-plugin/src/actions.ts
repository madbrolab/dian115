import type { PluginUIBridge } from '../../sdk/ui'

/** Save business intent before dispatch; an uncertain response retains its ID. */
export async function invokeSavedAction(
  api: Pick<PluginUIBridge, 'storage' | 'invokeAction'>,
  action: string,
  input: Record<string, unknown> = {},
  newInvocation = () => `inv_ui_${Array.from(crypto.getRandomValues(new Uint32Array(4)), value => value.toString(16).padStart(8, '0')).join('')}`,
) {
  const key = `action-intent.${action}`
  const previous = await api.storage.get<{ invocationId: string; input: Record<string, unknown> }>(key)
  if (previous && (typeof previous.invocationId !== 'string' || !/^inv_[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*$/.test(previous.invocationId) || previous.invocationId.length > 80 || JSON.stringify(previous.input) !== JSON.stringify(input))) {
    throw new Error('上次动作尚未确认，请先核对原请求及业务结果')
  }
  const intent = previous || { invocationId: newInvocation(), input }
  await api.storage.set(key, intent)
  const response = await api.invokeAction(action, intent.input, intent.invocationId)
  let confirmation_pending = false
  try { await api.storage.remove(key) }
  catch { confirmation_pending = true }
  // Cleanup can commit and lose its reply. The confirmed business result must
  // still be returned, so a storage acknowledgement never becomes a new write.
  return { ...response, confirmation_pending }
}
