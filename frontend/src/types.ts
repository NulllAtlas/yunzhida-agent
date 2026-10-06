export interface Party {
  party: string
  ratio: number
  reasons: string[]
}

export interface Law {
  clause: string
  summary: string
}

export interface AccidentData {
  fault: string
  responsibility: string
  confidence: number
  parties: Party[]
  laws: Law[]
  emergency: string[]
}

export interface MockResponse {
  code: number
  msg: string
  data: AccidentData
}

export type AIResult = AccidentData