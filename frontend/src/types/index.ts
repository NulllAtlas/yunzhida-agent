export type UserRole = 'owner' | 'police'

// 单方责任：当事方 + 责任占比 + 理由分条
export interface PartyFault {
  party: string        // 当事方，如 'A车' / 'B车'
  ratio: number        // 责任占比（百分比，如 70 表示 70%）
  reasons: string[]    // 理由分条
}

// 一条法条依据
export interface LawBasis {
  clause: string       // 法条，如 '《道路交通安全法》第四十三条'
  summary: string      // 说明 / 要点
}

export interface AIResult {
  fault: string            // 事故类型 / 判定结论
  responsibility: string   // 责任划分结论文本
  parties: PartyFault[]    // 各方责任占比与理由（可多方，如 A/B 车）
  laws: LawBasis[]         // 法条依据
  confidence: number       // 置信度 0-100
  emergency: string[]      // 应急处置步骤
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