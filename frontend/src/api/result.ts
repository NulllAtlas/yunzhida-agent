/**
 * 后端结果 → 界面视图模型。
 *
 * 这套映射原先写死在 Owner.vue 里；交警端现在也要展示同一条链路的结果，
 * 各写一份迟早漂移（两边判定的显示口径必须一致），所以抽出来共用。
 */
import type {
  AIResult,
  AnalyzeResult,
  BackendPhotoEvidence,
  BackendSceneEvent,
  HistoryRecord,
  KeyframeView,
  PartyFault,
  PhotoEvidenceView,
  SubmissionEntry,
  SubmissionPayload,
} from '../types'
import { STAGE_LABEL, startPolling } from './tasks'

const PARTY_LABEL: Record<string, string> = {
  primary: '主要责任',
  secondary: '次要责任',
  equal: '同等责任',
  none: '无责任',
  unknown: '待补充认定',
}

// 后端 basis 形如 "《道交法》第43条 同车道行驶后车应与前车保持安全距离"，
// 法条名与说明之间是空格分隔（并非全角冒号），早先只按 '：' 拆会让 summary 恒为空。
const LAW_RE = /^(《[^》]*》[^\s：:]*)\s*[：:]?\s*(.*)$/

function splitLaw(item: string): { clause: string; summary: string } {
  const m = item.match(LAW_RE)
  return m ? { clause: m[1], summary: m[2] } : { clause: item, summary: '' }
}

const RLV_LABEL: Record<string, string> = { yes: '是', no: '否', unknown: '无法确认' }

/** 把后端 AnalyzeResult 转成界面渲染用的 AIResult；缺判定数据时返回 null。 */
export function toAIResult(r: AnalyzeResult | null): AIResult | null {
  const j = r?.judgment
  if (!r || !j) return null
  const split = j.responsibility.split || ''
  const isNonAccident =
    j.accident_type === '非事故' ||
    (split === '' && j.responsibility.party_1 === 'unknown')
  // split 为空时 '' .split('/') 只有一个元素，不写默认值会让 b 变成 undefined，
  // 界面上就会渲染出 "undefined%"
  const [a = 0, b = 0] = split.split('/').map((x) => parseInt(x, 10) || 0)
  const primaryFirst = a >= b
  const partyName = (i: number, fallback: string) => {
    const p = j.parties?.[i]
    if (p && (p.role || p.type)) {
      const role = p.role ? p.role : fallback
      return p.type ? `${role}（${p.type}）` : role
    }
    return fallback
  }
  const parties: PartyFault[] = isNonAccident
    ? []
    : [
        { party: partyName(0, '当事方一'), ratio: a, reasons: primaryFirst ? j.reasoning : [] },
        { party: partyName(1, '当事方二'), ratio: b, reasons: primaryFirst ? [] : j.reasoning },
      ]
  const laws = j.basis.map(splitLaw)
  const emergency = (r.response?.steps || [])
    .slice()
    .sort((x, y) => x.order - y.order)
    .map((s) => s.action)
  if (r.response?.insurance) emergency.push(`保险指引：${r.response.insurance}`)

  const source = r.scene?.source
  // 用户传了视频但检测失败（source=text_fallback）：必须明示，
  // 否则会把文字推断的结论当成视频检测结果展示
  const degraded = source === 'text_fallback'
  // 只有现场照片、没有视频：判定依据是静态证据 + 用户描述，同样要说清楚
  const photoBased = source === 'photo'
  const prefix = degraded
    ? '⚠️ 视频解析失败，以下为文字推断结果，仅供参考 —— '
    : photoBased
      ? '📷 基于现场照片检测与用户描述 —— '
      : ''

  return {
    fault:
      prefix +
      (isNonAccident
        ? '未检测到明显事故特征（可能为误报，请确认上传的是事故视频）'
        : j.accident_type || '交通事故研判完成'),
    responsibility: isNonAccident
      ? '未认定责任（疑似非事故，或现场要素不足）'
      : `当事方一：${PARTY_LABEL[j.responsibility.party_1] || '待补充认定'}` +
        `；当事方二：${PARTY_LABEL[j.responsibility.party_2] || '待补充认定'}` +
        `（责任比例 ${split || '待定'}）`,
    parties,
    laws,
    confidence: Math.round(j.confidence * 100),
    emergency,
    red_light: isNonAccident ? undefined : RLV_LABEL[j.red_light_violation],
    // 免责声明是法务要求，单独透传，不能混进应急步骤里当可勾选的操作项
    note: j.note,
    photos: toPhotoViews(r.scene?.photos),
    keyframes: toKeyframeViews(r.scene?.events),
  }
}

/** 视频碰撞事件的标注关键帧 → 界面视图（只有真带图的才进列表）。 */
export function toKeyframeViews(events?: BackendSceneEvent[]): KeyframeView[] {
  return (events || [])
    .filter((e) => !!e.keyframe)
    .map((e) => ({
      url: e.keyframe as string,
      caption: `t≈${e.time}s · 事故车辆识别框`,
    }))
}

// 照片检出目标类型的中文名（与 backend/app/algo/scene_summary.py 的 _PHOTO_TYPE_LABEL 对齐）
const PHOTO_TYPE_LABEL: Record<string, string> = {
  car: '轿车', truck: '货车', bus: '客车', motorcycle: '摩托车',
  bicycle: '自行车', pedestrian: '行人', other: '其它目标',
}

const PHOTO_LIGHT_LABEL: Record<string, string> = {
  red: '红灯', green: '绿灯', yellow: '黄灯', mixed: '红绿灯并存', unknown: '未识别',
}

/** 照片检测证据 → 界面视图（归纳目标数量 + 信号灯中文 + 局限说明）。 */
export function toPhotoViews(photos?: BackendPhotoEvidence[]): PhotoEvidenceView[] {
  return (photos || []).map((photo) => {
    const counts: Record<string, number> = {}
    for (const t of photo.targets || []) {
      const label = PHOTO_TYPE_LABEL[t.type] || t.type || '目标'
      counts[label] = (counts[label] || 0) + 1
    }
    const kinds = Object.keys(counts)
    return {
      name: photo.name,
      summary: kinds.length
        ? kinds.sort().map((k) => `${k}×${counts[k]}`).join('、')
        : '未检出可辨认目标',
      trafficLight: PHOTO_LIGHT_LABEL[photo.traffic_light] || '未识别',
      note: photo.note || '',
    }
  })
}

/** 输入组合的短标签，如「视频+2 张照片+文字」。 */
export function describeInputs(kinds: {
  video?: boolean
  photoCount?: number
  hasText?: boolean
}): string {
  const parts: string[] = []
  if (kinds.video) parts.push('视频')
  if (kinds.photoCount) parts.push(`${kinds.photoCount} 张照片`)
  if (kinds.hasText) parts.push('文字')
  return parts.length ? parts.join('+') : '无输入'
}

/** 记录标题：有视频用视频名，否则按交了几张照片说清楚。 */
export function entryTitle(videoName: string, photoCount: number): string {
  if (videoName) return videoName
  return photoCount ? `现场照片 ${photoCount} 张` : '补充说明提交'
}

/** 提交成功后的本地条目：先显示"研判中"，结果由轮询补上。 */
export function entryFromPayload(
  payload: SubmissionPayload,
  taskId: string,
  now: Date = new Date(),
): SubmissionEntry {
  return {
    id: taskId,
    time: now.toISOString(),
    fileName: entryTitle(payload.video?.name || '', payload.photos.length),
    kinds: describeInputs({
      video: !!payload.video,
      photoCount: payload.photos.length,
      hasText: !!payload.description,
    }),
    status: 'analyzing',
    progress: 0,
    stage: '排队中',
  }
}

/**
 * 后端记录 → 界面条目。
 *
 * 后端把上次进程死掉留下的半截任务已经修成 failed 了，所以这里只认三种状态：
 * done / failed / 仍在跑（其余阶段一律当"研判中"，交给轮询去推进）。
 */
export function entryFromRecord(record: HistoryRecord): SubmissionEntry {
  const base = {
    id: record.task_id,
    time: record.created_at,
    fileName: entryTitle(record.filename, (record.photos || []).length),
    kinds: describeInputs({
      video: !!record.filename,
      photoCount: (record.photos || []).length,
      hasText: !!record.input_text,
    }),
    flowStatus: record.flow_status || 'submitted',
  }

  if (record.status === 'failed') {
    return { ...base, status: 'failed', error: record.error || '分析失败，请重试' }
  }
  if (record.status === 'done') {
    const result = toAIResult(record.result)
    return result
      ? { ...base, status: 'done', result }
      : { ...base, status: 'failed', error: '分析结果缺少判定数据' }
  }
  return {
    ...base,
    status: 'analyzing',
    progress: 0,
    stage: STAGE_LABEL[record.status] || '分析中',
  }
}

/**
 * 起轮询并在终态把结果写回条目。
 *
 * 车主端与交警端共用同一套口径，免得两边对"结果长什么样、失败怎么显示"产生分歧。
 */
export function pollEntry(entry: SubmissionEntry, taskId: string): void {
  startPolling(taskId, entry, (target, outcome) => {
    const converted = toAIResult(outcome)
    if (!converted) {
      target.status = 'failed'
      target.error = '分析结果缺少判定数据'
      return
    }
    target.result = converted
    target.status = 'done'
  })
}
