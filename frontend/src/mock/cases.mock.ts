import type { CaseRecord } from '../types'

export const mockCases: CaseRecord[] = [
  {
    id: '1',
    img: 'https://via.placeholder.com/120x80?text=Case+1',
    result: {
      fault: '右后侧刮擦',
      responsibility: '双方同责',
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
      emergency: ['放置警示牌', '撤离人员'],
    },
    time: '2026-09-27 14:15',
    status: 'processing',
  },
]