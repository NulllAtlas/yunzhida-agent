/**
 * 任务轮询：提交后拿 task_id 轮询直到出结果。
 *
 * 车主端与交警端共用（原先这段逻辑长在 Owner.vue 里，交警端再抄一份就会漂移）。
 */
import type { AnalyzeResult, TaskInfo } from '../types'

// 后端各阶段对应的中文说明（与 backend/app/api/tasks.py 的 _STEP_MAP 对齐）
export const STAGE_LABEL: Record<string, string> = {
  pending: '排队中',
  perceiving: '视频感知（YOLO 检测 + 轨迹追踪）',
  retrieving: '检索法条与相似案例',
  judging: '责任判定中',
  responding: '生成应急处置方案',
  aggregating: '汇总研判结果',
  done: '分析完成',
}

export interface PollHandlers {
  /** 每次拿到新状态时回调（进度 0-100 与阶段中文说明） */
  onProgress?: (pct: number, stage: string) => void
}

/**
 * 轮询任务状态直到 done/failed，返回最终结果。
 *
 * 失败情形一律抛出带中文说明的 Error，交给调用方落到记录上：
 * 后端重启导致 404、任务失败、或超时。
 */
export async function pollTask(
  taskId: string,
  handlers: PollHandlers = {},
  timeoutMs = 600_000,
): Promise<AnalyzeResult | null> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const res = await fetch(`/api/tasks/${taskId}/status`)
    // 任务只活在后端内存里，重启后端就查不到了，早点讲清楚而不是白等十分钟
    if (res.status === 404) throw new Error('后端已重启，该任务的状态查不到了')
    if (res.ok) {
      const info: TaskInfo = await res.json()
      // 后端每个阶段都在回传 status 与 progress，别只拿 status 判结束、把进度丢掉
      handlers.onProgress?.(
        Math.round((info.progress ?? 0) * 100),
        STAGE_LABEL[info.status] || '分析中',
      )
      if (info.status === 'done') return info.result
      if (info.status === 'failed') throw new Error(info.error || '多智能体分析失败')
    }
    await new Promise((s) => setTimeout(s, 1500))
  }
  throw new Error('分析超时，请稍后在交警端查看案件')
}

/** 同一任务只跑一个轮询循环（列表刷新可能把同一个 id 又交进来一次）。 */
const polling = new Set<string>()

/** 能被轮询写进度的对象（车主端的记录条目、交警端的本次提交都满足） */
export interface PollEntry {
  status: 'analyzing' | 'done' | 'failed'
  progress?: number
  stage?: string
  error?: string
}

/**
 * 起一个轮询循环，进度写回 entry 本身，终态交给 onDone（由调用方决定怎么落到记录上）。
 *
 * 状态存在各自的 entry 上，所以两条记录同时分析也不会互相覆盖进度。
 */
export function startPolling<T extends PollEntry>(
  taskId: string,
  entry: T,
  onDone: (entry: T, result: AnalyzeResult | null) => void,
): void {
  if (polling.has(taskId)) return
  polling.add(taskId)
  pollTask(taskId, {
    onProgress: (pct, stage) => {
      entry.progress = pct
      entry.stage = stage
    },
  })
    .then((result) => onDone(entry, result))
    .catch((err: any) => {
      // 失败也留在记录里：演示时能看出哪一次没过，而不是悄悄消失
      entry.status = 'failed'
      entry.error = err?.message || '分析失败，请重试'
    })
    .finally(() => polling.delete(taskId))
}
