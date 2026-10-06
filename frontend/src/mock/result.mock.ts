import type { MockResponse } from '../types'

export const mockAIResult: MockResponse = {
  code: 200,
  msg: 'success',
  data: {
    fault: '追尾碰撞事故：前保险杠左侧破损，左前大灯碎裂，后车未保持安全车距',
    responsibility: 'A车全责（未保持安全车距追尾）',
    confidence: 86,
    parties: [
      {
        party: 'A车（后车）',
        ratio: 100,
        reasons: [
          '未与前车保持足以采取紧急制动措施的安全距离',
          '追撞前车是事故发生的直接原因',
        ],
      },
      {
        party: 'B车（前车）',
        ratio: 0,
        reasons: [
          '正常行驶中无变道或急刹行为，无过错',
        ],
      },
    ],
    laws: [
      {
        clause: '《中华人民共和国道路交通安全法》第四十三条',
        summary: '同车道行驶的机动车，后车应当与前车保持足以采取紧急制动措施的安全距离。',
      },
      {
        clause: '《道路交通事故处理程序规定》第六十条',
        summary: '一方当事人的过错导致交通事故的，承担全部责任。',
      },
    ],
    emergency: [
      '打开双闪，在车后 50 米处放置三角警示牌',
      '人员撤离至安全区域，不要留在车内',
      '拍摄全景、碰撞点、车牌照片后快速挪车',
    ],
  },
}