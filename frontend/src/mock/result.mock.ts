import type { MockResponse } from '../types'

export const mockAIResult: MockResponse = {
  code: 200,
  msg: 'success',
  data: {
    fault: '前保险杠左侧破损，左前大灯碎裂',
    responsibility: 'A车全责（未保持安全车距追尾）',
    emergency: [
      '打开双闪，在车后 50 米处放置三角警示牌',
      '人员撤离至安全区域，不要留在车内',
      '拍摄全景、碰撞点、车牌照片后快速挪车',
    ],
  },
}