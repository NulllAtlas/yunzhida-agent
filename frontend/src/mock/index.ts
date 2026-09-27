import type { Judgment, ResponsePlan, SceneItem } from '../types'

export const mockScene: SceneItem = {
  scene_id: 's_mock_rear_end',
  objects: [
    {
      id: 'obj_1', kind: 'vehicle', category: 'car',
      trajectory: [{ t: 2.3, x: 34, y: 60, w: 8, h: 12, speed: 0, heading: 0 }],
      keyframes: [2.3], confidence: 0.9,
    },
    {
      id: 'obj_2', kind: 'vehicle', category: 'car',
      trajectory: [{ t: 2.3, x: 24, y: 60, w: 8, h: 12, speed: 11, heading: 0 }],
      keyframes: [2.3], confidence: 0.88,
    },
  ],
  events: [{ type: 'collision', t: 2.3, objects: ['obj_1', 'obj_2'], impact_speed: 12, confidence: 0.82 }],
  confidence: 0.78,
  low_confidence: false,
}

export const mockJudgment: Judgment = {
  case_type: 'rear_end',
  parties: [
    { object_id: 'obj_1', role: 'A', liability_pct: 70, main_reason: '未保持安全距离' },
    { object_id: 'obj_2', role: 'B', liability_pct: 30, main_reason: '突然变道' },
  ],
  reasoning: ['A 车未保持安全距离', 'B 车突然变道'],
  laws: [{ article: '《道路交通安全法》第 43 条', summary: '同车道追尾事故责任' }],
  confidence: 0.76,
  low_confidence: false,
}

export const mockResponse: ResponsePlan = {
  emergency_level: 'low',
  level_label: '一般事故，按步骤处置',
  urgent_actions: [],
  steps: [
    { order: 1, action: '开启双闪，熄火', urgent: false, checked: false },
    { order: 2, action: '距车后方 50 米放置三角警示牌', urgent: true, checked: false },
    { order: 3, action: '人员撤离至安全区域', urgent: true, checked: false },
    { order: 4, action: '拨打 122 报警并留存证据', urgent: false, checked: false },
  ],
  insurance_note: '48 小时内报保险，保存现场照片与记录仪视频',
  confidence: 0.8,
}
