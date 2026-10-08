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
  red_light?: string       // 是否闯红灯：是 / 否 / 无法确认
  note?: string            // 免责声明（后端 judgment.note）
  photos?: PhotoEvidenceView[]  // 随附现场照片的检测证据（没交照片时为 undefined）
  keyframes?: KeyframeView[]    // 事故车辆识别框标注帧（视频碰撞事件，无标注时为 undefined）
}

/** 一张标注了事故车辆识别框的关键帧（视频感知生成，/outputs/ 下的 URL）。 */
export interface KeyframeView {
  url: string      // 图片地址（后端 /outputs/ 静态路径）
  caption: string  // 说明，如「t≈12s · 事故车辆识别框」
}

/** 一张现场照片的检测证据（给界面看的归纳版，原始数据在 BackendPhotoEvidence）。 */
export interface PhotoEvidenceView {
  name: string         // 照片文件名
  summary: string      // 检出目标归纳，如「轿车×1、行人×2」或「未检出可辨认目标」
  trafficLight: string // 中文，如「红灯」/「未识别」
  note: string         // 局限说明（静态画面无速度/方向，或检测未运行的原因）
}

export interface MockResponse {
  code: number
  msg: string
  data: AIResult
}

// ---------- 后端多智能体链路类型（/api/videos → /api/tasks） ----------
export interface BackendResponsibility {
  party_1: string
  party_2: string
  split: string
}

export interface BackendPartyRole {
  role: string   // 后车 / 前车 / 驾驶方 / 行人 等
  type: string   // car / truck / pedestrian 等
}

export interface BackendJudgment {
  scene_id: string
  accident_type: string
  parties: BackendPartyRole[]
  red_light_violation: string  // yes / no / unknown
  responsibility: BackendResponsibility
  basis: string[]
  reasoning: string[]
  confidence: number
  note: string
}

export interface BackendResponseStep {
  order: number
  action: string
  urgent: boolean
}

export interface BackendEmergencyResponse {
  scene_id: string
  accident_type: string
  priority: number
  steps: BackendResponseStep[]
  insurance: string
}

/** 现场照片单帧检测出的一个目标（归一化 bbox，静态位置）。 */
export interface BackendPhotoTarget {
  type: string          // car / truck / pedestrian 等
  confidence: number
  bbox: number[]        // [x, y, w, h]，取值 0-1
}

/** 后端 Scene.photos 的一项：一张现场照片的检测证据。 */
export interface BackendPhotoEvidence {
  name: string
  width: number
  height: number
  targets: BackendPhotoTarget[]
  traffic_light: string  // red / green / yellow / mixed / unknown
  note: string           // 静态局限或"检测未运行"的说明
}

/** 后端 scene.events 的一项：碰撞事件（含事故车辆识别框与标注关键帧）。 */
export interface BackendSceneEvent {
  time: number
  type: string
  participants: number[]
  confidence: number
  boxes: unknown[]       // 碰撞时刻双方识别框（归一化），界面直接用标注帧，不用它
  keyframe?: string      // 标注了事故车辆识别框的关键帧 URL（无标注时缺省）
  geometry?: string
}

export interface BackendScene {
  scene_id: string
  // video = 真实视频检测；photo = 现场照片单帧检测；text_fallback = 传了视频但检测失败降级；
  // text = 文字输入；mock
  source: string
  vehicles: unknown[]
  events: BackendSceneEvent[]
  // 随附现场照片的检测证据（没交照片时为空数组/缺省）
  photos?: BackendPhotoEvidence[]
  road: string
  traffic_light: string
  confidence: number
}

export interface AnalyzeResult {
  case_id: string
  scene: BackendScene | null
  judgment: BackendJudgment | null
  response: BackendEmergencyResponse | null
}

export interface TaskInfo {
  task_id: string
  status: 'pending' | 'perceiving' | 'retrieving' | 'judging' | 'responding' | 'aggregating' | 'done' | 'failed'
  progress: number
  error: string | null
  result: AnalyzeResult | null
}

export interface ApiEnvelope<T> {
  code: number
  msg: string
  data: T
}

/** 一次提交的原始输入（车主端/交警端共用表单产出，交给后端 POST /api/submissions）。 */
export interface SubmissionPayload {
  video: File | null
  photos: File[]
  description: string
}

export interface CaseRecord {
  id: string
  img: string
  result: AIResult
  time: string
  status: 'processing' | 'done'
}

/**
 * 一次「提交研判」的记录（车主端与交警端共用）。
 *
 * 记录本身存在后端（GET /api/history），换浏览器/换设备看到的是同一份；
 * 这个类型是界面上的视图模型，额外承担"这条正在跑"的实时进度。
 */
export interface SubmissionEntry {
  id: string                              // 后端 task_id；后端不通时是本地生成的 demo id
  time: string                            // 提交时间（ISO 字符串）
  fileName: string                        // 提交标题：视频名 / 照片名 / 「文字提交」
  kinds: string                           // 输入组合，如「视频+2 张照片+文字」
  status: 'analyzing' | 'done' | 'failed'
  progress?: number                       // 分析进度 0-100（来自 TaskInfo.progress）
  stage?: string                          // 当前阶段的中文说明
  error?: string                          // 失败原因
  result?: AIResult                       // 研判结果（成功后写入）
}

/** 后端 GET /api/history 的一条记录（结果随记录一起返回，前端不必逐条再查详情）。 */
export interface HistoryRecord {
  task_id: string
  filename: string                        // 视频原始文件名；纯文字/照片提交时为空串
  input_text: string                      // 用户补充的文字描述；没写时为空串
  photos: string[]                        // 随附现场照片的存储名（仅用于显示"交了几张"）
  status: string                          // pending/perceiving/.../done/failed（后端已把中断的修成 failed）
  accident_type: string | null
  error: string | null
  created_at: string
  updated_at: string
  result: AnalyzeResult | null
}