/** Keep RPC data JSON-only and bounded before either side allocates a clone. */
export function clonePluginMessage<T>(value: T): T {
  const serialized = JSON.stringify(value)
  if (serialized === undefined) throw new TypeError('消息没有可序列化内容')
  if (serialized.length > 1_048_576 || new TextEncoder().encode(serialized).byteLength > 1_048_576) {
    throw new TypeError('插件消息超过 1 MiB 上限')
  }
  return JSON.parse(serialized) as T
}
