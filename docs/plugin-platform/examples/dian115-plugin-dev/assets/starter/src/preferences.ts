export interface Storage { get<T>(key: string): Promise<T | null>; set(key: string, value: unknown): Promise<unknown> }
export async function readDisplayName(storage: Storage) {
  const value = await storage.get<unknown>('display-name')
  if (value === null) return ''
  if (typeof value !== 'string' || value.length > 120) throw new Error('已保存的显示名称格式错误')
  return value
}
export async function saveDisplayName(storage: Storage, value: string, restored: boolean) {
  if (!restored) throw new Error('请先成功读取原有偏好')
  if (value.length > 120) throw new Error('显示名称最多 120 个字符')
  await storage.set('display-name', value)
}
