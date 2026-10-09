/**
 * 前端会话（D7 鉴权对接）。
 *
 * 后端契约（backend/app/api/routers/auth.py）：
 *   成功 {code: 0, msg: 'ok', data: {...}}
 *   失败 {code: '<字符串错误码>', msg: '<可直接展示的说明>', data: null}
 * 所以这里统一读 msg 当错误文案，不再自己拼一套提示。
 */
import type { UserRole } from '../types'

const TOKEN_KEY = 'roadmind.token'
const USER_KEY = 'roadmind.user'

export interface SessionUser {
  username: string
  role: UserRole
}

interface Envelope<T> {
  code: number | string
  msg: string
  data: T
}

interface LoginData {
  access_token: string
  token_type: string
  role: UserRole
  expires_in: number
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const envelope: Envelope<T> | null = await res.json().catch(() => null)
  if (!res.ok) throw new Error(envelope?.msg || `请求失败（HTTP ${res.status}）`)
  if (!envelope) throw new Error('后端返回了非 JSON 响应，请确认服务已启动')
  return envelope.data
}

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function getUser(): SessionUser | null {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    const user = JSON.parse(raw) as SessionUser
    return user?.username && user?.role ? user : null
  } catch {
    // 手工改坏的 localStorage 不该让整个应用白屏
    return null
  }
}

function saveSession(token: string, username: string, role: UserRole): void {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify({ username, role }))
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

/** 供需要鉴权的接口使用（交警端 /api/police/* 走 Depends(require_role("police"))）。 */
export function authHeaders(): Record<string, string> {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/** 研判工作台（:8000 的云智达界面）的跳转地址，带令牌与账号 —— 界面端读到 URL
 *  参数后写入自己的 localStorage 静默恢复登录态，免去二次登录。 */
export function workbenchUrl(token: string, username: string): string {
  return `http://localhost:8000/?token=${encodeURIComponent(token)}`
    + `&user=${encodeURIComponent(username)}`
}

/** 登录并落地会话。后端不回显用户名，沿用入参。 */
export async function login(username: string, password: string): Promise<SessionUser> {
  const data = await post<LoginData>('/api/auth/login', { username, password })
  if (!data?.access_token) throw new Error('登录响应缺少令牌')
  saveSession(data.access_token, username, data.role)
  return { username, role: data.role }
}

/**
 * 注册。后端注册接口不签发令牌，所以注册成功后立刻用同一凭据登录一次，免去二次输入。
 *
 * 不传 role：前端把账号与身份分开——登录只解决“你是谁”，进车主端还是交警端
 * 由登录后的入口页决定。后端该字段默认 owner。
 */
export async function register(username: string, password: string): Promise<SessionUser> {
  await post<{ username: string; role: UserRole }>('/api/auth/register', {
    username,
    password,
  })
  return login(username, password)
}
