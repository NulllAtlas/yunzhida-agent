export type UserRole = 'owner' | 'police'

export interface AIResult {
  fault: string          // 故障判定
  responsibility: string // 责任划分
  emergency: string[]    // 应急处置步骤
}

export interface MockResponse {
  code: number
  msg: string
  data: AIResult
}

export interface CaseRecord {
  id: string
  img: string
  result: AIResult
  time: string
  status: 'processing' | 'done'
}