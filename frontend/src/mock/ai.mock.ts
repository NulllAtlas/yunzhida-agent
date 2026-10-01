import type { AIResult } from '../types'

// D5 演示用的结构化结果。后端目前返回字符串（P0 模拟），
// 接入真实 AI 后，把 Owner.vue 里用到这个常量的地方换成后端返回的 JSON 即可。
export const MOCK_AI_RESULT: AIResult = {
  fault: '甲方车辆违规变道，与正常直行的乙方车辆发生碰撞',
  responsibility: '甲方全责',
  confidence: 88,
  parties: [
    { party: '甲方车辆', ratio: 100, reasons: ['压实线变道', '未让直行车辆先行'] },
    { party: '乙方车辆', ratio: 0, reasons: ['本车道正常直行', '无交通违法行为'] },
  ],
  laws: [
    {
      clause: '《道路交通安全法实施条例》第四十四条',
      summary: '变更车道的机动车不得影响相关车道内行驶的机动车的正常行驶。',
    },
  ],
  emergency: [
    '立即开启双闪（危险报警闪光灯）',
    '在来车方向 50–100 米外放置三角警示牌',
    '车上人员全部撤离到护栏外安全地带',
    '拨打 122 报警并拍照固定现场证据',
    '如有人员受伤，立即拨打 120',
  ],
}