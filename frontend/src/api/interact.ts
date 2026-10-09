/**
 * 双端联动接口（D12）：车主查看案件流转与交警下发；交警下发消息/处理意见/推进状态。
 * 交警端接口需要 police 角色，自动带上 Bearer 令牌。
 */
import { authHeaders } from './auth'
import type { CaseFlowStatus, CaseInteraction } from '../types'

async function unwrap<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    throw new Error(body?.msg || `请求失败（HTTP ${res.status}）`)
  }
  return (body?.data ?? body) as T
}

/** 车主端：查询某案件的业务状态流转与交警下发内容（不鉴权，任何设备可看）。 */
export async function fetchInteraction(taskId: string): Promise<CaseInteraction> {
  const res = await fetch(`/api/cases/${taskId}/interact`)
  return unwrap<CaseInteraction>(res)
}

/** 交警端：向车主下发消息。 */
export async function policeSendMessage(taskId: string, content: string): Promise<void> {
  const res = await fetch(`/api/cases/${taskId}/police/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ content }),
  })
  await unwrap(res)
}

/** 交警端：下发处理意见（处分），返回推进后的状态。 */
export async function policeSendDisposition(
  taskId: string,
  kind: string,
  detail: string,
  note: string,
): Promise<CaseFlowStatus> {
  const res = await fetch(`/api/cases/${taskId}/police/disposition`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ kind, detail, note }),
  })
  const data = await unwrap<{ flow_status: CaseFlowStatus }>(res)
  return data.flow_status
}

/** 交警端：推进案件状态流转（accept/approve/reject/close）。 */
export async function policeAdvanceFlow(
  taskId: string,
  action: string,
  note = '',
): Promise<CaseFlowStatus> {
  const res = await fetch(`/api/cases/${taskId}/police/flow`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ action, note }),
  })
  const data = await unwrap<{ flow_status: CaseFlowStatus }>(res)
  return data.flow_status
}
