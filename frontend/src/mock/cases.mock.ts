import type { CaseRecord } from '../types'

export const mockCases: CaseRecord[] = [
  {
    id: '1',
    img: 'https://via.placeholder.com/120x80?text=Case+1',
    result: {
      fault: '右后侧刮擦',
      responsibility: '双方同责',
      confidence: 72,
      parties: [
        { party: 'A车', ratio: 50, reasons: ['变更车道时未充分观察侧后方来车'] },
        { party: 'B车', ratio: 50, reasons: ['未保持安全车速，避让不及'] },
      ],
      laws: [
        { clause: '《道路交通安全法实施条例》第四十四条', summary: '变更车道不得影响相关车道内行驶的机动车的正常行驶。' },
      ],
      emergency: ['拍照取证', '联系保险'],
    },
    time: '2026-09-28 10:30',
    status: 'done',
  },
  {
    id: '2',
    img: 'https://via.placeholder.com/120x80?text=Case+2',
    result: {
      fault: '前保险杠破损',
      responsibility: '本车全责',
      confidence: 90,
      parties: [
        { party: '本车', ratio: 100, reasons: ['倒车时未观察车后情况，撞上后方车辆'] },
      ],
      laws: [
        { clause: '《道路交通安全法实施条例》第五十条', summary: '机动车倒车时，应当察明车后情况，确认安全后倒车。' },
      ],
      emergency: ['放置警示牌', '撤离人员'],
    },
    time: '2026-09-27 14:15',
    status: 'processing',
  },
]